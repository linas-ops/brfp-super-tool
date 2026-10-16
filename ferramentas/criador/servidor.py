"""Criador de Ligas e Times (BRFP Super Tool) — cria ligas, times, seleções e jogadores no banco do jogo a partir da
API-Football e atualiza o que já existe (elencos, participantes das ligas).

    python servidor.py [--porta 8775] [--sem-janela]

1. Navega pela API (país -> competição -> temporada -> times) e põe no projeto uma liga inteira, times avulsos (vários
   de uma vez) ou seleções.
2. Coleta os dados (estatísticas, elenco, técnico, escalações; convocação nas seleções) gastando o mínimo de
   chamadas — tudo fica no cache.
3. Gera notas e atributos calibrados no banco importado no Super Tool (notas.py) e mostra a prévia de cada time,
   onde dá para mudar todas as colunas que vão para o jogo, a tática, o técnico, o estádio e os IDs.
4. Atualizar banco: confere os elencos (transferências, empréstimos, saídas, números) e os participantes das ligas do
   banco com a API (atualizar.py).
5. Grava um banco novo (cópia do importado + linhas novas, alteradas e removidas), as tabelas em .txt, o idioma, o
   internationals.txt (seleções novas) e as imagens (saida.py); as fotos podem seguir para o Criador de Minifaces.
O projeto fica em cache\\projeto.json (sobrevive a fechar a ferramenta).
"""
import argparse
import copy
import datetime
import json
import os
import re
import sys
import threading
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import apifutebol as A  # noqa: E402
import base  # noqa: E402
import coleta as C  # noqa: E402
import coleta_tm as CT  # noqa: E402
import transfermarkt as T  # noqa: E402
import componentes  # noqa: E402
import dados  # noqa: E402

G = N = S = None
MOTOR = {"ok": False, "msg": ""}


def carregar_motor():
    """Notas e gerador usam numpy (Python embutido do Super Tool). Sem ele a ferramenta abre e oferece o download."""
    global G, N, S
    try:
        import gerador as g
        import notas as n
        import saida as s
    except ImportError:
        MOTOR.update(ok=False, msg=componentes.falta_msg("criador"))
        return False
    G, N, S = g, n, s
    MOTOR.update(ok=True, msg="")
    return True


def exige_motor():
    if not MOTOR["ok"] and not carregar_motor():
        raise base.ErroUsuario(MOTOR["msg"])


VERSAO = "2.4"
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "saida": "", "espalhamento": 1.25, "escalacoes": 5, "modo": "temporada", "perfis_faltantes": 10, "baixar_imagens": True,
    "classificacao": True, "jogador_inicio": 460000, "time_inicio": 150000, "liga_inicio": 3000, "visual": "proprio",
    "aparencia_fotos": True, "minifaces_auto": False, "fonte": "apifootball", "tm_estatisticas": False, "completar_tm": False})
ARQ_PROJETO = os.path.join(AQUI, "cache", "projeto.json")
LOCK = threading.RLock()
API = A.Api()
TM = T.Tm()
_TM_STATUS = {"t": 0, "v": None}
FONTES = {"apifootball": "API-Football", "transfermarkt": "Transfermarkt"}


def fonte_de(x):
    """"transfermarkt" ou "apifootball" de um item, liga ou time."""
    return (x or {}).get("fonte") or ((x or {}).get("liga_api") or {}).get("fonte") or ((x or {}).get("api") or {}).get("fonte") or "apifootball"


def eh_tm(x):
    return fonte_de(x) == "transfermarkt"


def _temp(fonte, v):
    """Temporada: número na API-Football, id da temporada (texto) na Transfermarkt."""
    if v in (None, ""):
        return None
    return str(v) if fonte == "transfermarkt" else int(v)


def tm_status(forcar=False):
    if forcar or time.time() - _TM_STATUS["t"] > 15:
        try:
            _TM_STATUS["v"] = TM.status()
        except Exception as ex:  # noqa: BLE001
            _TM_STATUS["v"] = {"modo": TM.modo(), "erro": str(ex)}
        _TM_STATUS["t"] = time.time()
    return _TM_STATUS["v"]
P = {"itens": [], "sel": None, "atualizacoes": [], "selecoes_pares": {}}
TAREFA = {"ativa": False, "tipo": None, "msg": "", "feito": 0, "total": 0, "erro": None, "fim": 0, "resultado": None}
_PERFIL = {"sig": None, "perfil": None, "ligas": None, "nacoes": None}
FEM = re.compile(r"\b(women|womens|feminin[oa]|femenin[oa]|fem\.?|ladies|frauen|w)\b|\(w\)|\bwfc\b|\bgirls\b", re.I)


# ------------------------------------------------------------------ projeto (persistido)
def carregar_projeto():
    try:
        with open(ARQ_PROJETO, encoding="utf-8") as f:
            d = A.consertar(json.load(f))          # projetos de antes guardaram nomes com acento quebrado pela API
        P.update(itens=d.get("itens") or [], sel=d.get("sel"), atualizacoes=d.get("atualizacoes") or [],
                 selecoes_pares=d.get("selecoes_pares") or {})
    except (OSError, ValueError):
        return
    for it in P["itens"]:
        lid_tm = (it.get("liga_api") or it.get("api") or {}).get("id")
        if eh_tm(it) and it.get("temporada") and not it.get("temporada_nome") and lid_tm:   # "2025" -> "2026" (Brasil)
            c = TM.do_cache(f"competitions/{lid_tm}/seasons") or {}
            it["temporada_nome"] = next((x.get("name") for x in c.get("seasons") or [] if str(x.get("id")) == str(it["temporada"])), None)
        antigo = "feminino" not in it
        it.setdefault("feminino", eh_feminino(it))
        it.setdefault("selecao", bool((it.get("api") or {}).get("selecao")) and it["tipo"] == "time")
        if antigo and it["feminino"] and not it.get("selecao"):   # projeto da 1.0: refaz o nível com as ligas femininas
            try:
                nv, div, motivo = nivel_sugerido(it.get("liga_api") or it.get("api") or {}, it.get("nacao"), 1)
                it.update(nivel_base=nv, nivel_motivo=motivo)
                if it["tipo"] == "liga":
                    it.update(nivel=nv, nivel_auto=nv)
                elif not it.get("liga_item") and it.get("destino") in (None, "76"):
                    it["destino"] = destino_sugerido(it.get("nacao"), it.get("divisao") or 1, 1)
            except Exception:  # noqa: BLE001
                pass
        if it["tipo"] == "time" and it.get("dados") and not it.get("selecao"):   # refaz o nível (a regra pode ter mudado)
            try:
                lig = next((x for x in P["itens"] if x["id"] == it.get("liga_item")), None)
                if eh_tm(it):
                    _nivel_pelo_valor(it, lig)
                else:
                    _nivel_pela_classificacao(it, lig)
            except Exception:  # noqa: BLE001
                pass


def gravar_projeto():
    os.makedirs(os.path.dirname(ARQ_PROJETO), exist_ok=True)
    with LOCK:
        txt = json.dumps({"itens": P["itens"], "sel": P["sel"], "atualizacoes": P["atualizacoes"],
                          "selecoes_pares": P.get("selecoes_pares") or {}}, ensure_ascii=False)
    with open(ARQ_PROJETO + ".tmp", "w", encoding="utf-8") as f:
        f.write(txt)
    os.replace(ARQ_PROJETO + ".tmp", ARQ_PROJETO)


def item(iid):
    for it in P["itens"]:
        if it["id"] == iid:
            return it
    raise base.ErroUsuario("Item não encontrado no projeto.")


def banco():
    b = dados.banco_atual()
    if not b:
        raise base.ErroUsuario("Importe o banco do jogo em Dados do jogo (Super Tool) antes: as notas são calibradas nele.")
    return b


def perfil():
    exige_motor()
    b = banco()
    with LOCK:
        if _PERFIL["sig"] != b.sig:
            _PERFIL.update(sig=b.sig, perfil=N.Perfil(b), ligas=None, nacoes=None)
        return _PERFIL["perfil"]


def ligas_db():
    exige_motor()
    b = banco()
    with LOCK:
        if _PERFIL["ligas"] is None or _PERFIL["sig"] != b.sig:
            lg = {d["leagueid"]: d for d in b.tabela("leagues").dicts()}
            idi = dados.idioma_atual()
            out = []
            for l in N.nivel_ligas(b, idi):
                d = lg.get(l["leagueid"], {})
                out.append({**l, "pais": d.get("countryid"), "divisao": int(d.get("level") or 1),
                            "feminina": d.get("iswomencompetition") == "1", "internacional": d.get("isinternationalleague") == "1"})
            nomes = {l["leagueid"] for l in out}
            for lid, d in lg.items():                         # ligas sem times fortes (resto do mundo etc.) também servem de destino
                if lid not in nomes:
                    out.append({"leagueid": lid, "nome": (idi.liga(lid) if idi else None) or d.get("leaguename") or lid,
                                "nivel": None, "times": 0, "pais": d.get("countryid"), "divisao": int(d.get("level") or 1),
                                "feminina": d.get("iswomencompetition") == "1", "internacional": d.get("isinternationalleague") == "1"})
            _PERFIL["ligas"] = out
        return _PERFIL["ligas"]


def nacoes_db():
    b = banco()
    with LOCK:
        if _PERFIL["nacoes"] is None or _PERFIL["sig"] != b.sig:
            idi = dados.idioma_atual()
            out = [{"id": d["nationid"], "nome": (idi.texto(f"NationName_{d['nationid']}") if idi else None) or d["nationname"],
                    "nome_en": d["nationname"], "iso": d.get("isocountrycode"), "confederacao": d.get("confederation")}
                   for d in b.tabela("nations").dicts()]
            _PERFIL["nacoes"] = sorted(out, key=lambda x: dados.normalizar(x["nome"]))
        return _PERFIL["nacoes"]


def nacao_de(pais_nome, codigo=None):
    exige_motor()
    pj = G.Projeto.__new__(G.Projeto)
    pj.b, pj.tabs, pj.idioma = banco(), {}, dados.idioma_atual()
    pj.nacoes = G.Projeto._nacoes(pj)
    return G.Projeto.nacao(pj, pais_nome, codigo)


def eh_feminino(it_ou_nome, nome_time=None):
    if isinstance(it_ou_nome, dict):
        it = it_ou_nome
        n = f"{(it.get('liga_api') or it.get('api') or {}).get('nome') or ''} {it.get('nome') or ''} {(it.get('api') or {}).get('nome') or ''}"
    else:
        n = f"{it_ou_nome or ''} {nome_time or ''}"
    return bool(FEM.search(n))


def _diferenca_selecao(genero):
    """Quanto a 1ª divisão de um país fica abaixo da seleção dele, no banco (mediana dos países que têm as duas)."""
    b = banco()
    nt = N.nivel_times(b)
    selecoes = {}
    liga_sel = G.LIGA_SELECOES[genero]
    for d in b.tabela("teamnationlinks").dicts():
        if d["leagueid"] == liga_sel and d["teamid"] in nt:
            selecoes[d["nationid"]] = nt[d["teamid"]]
    difs = [selecoes[l["pais"]] - l["nivel"] for l in ligas_db() if l["nivel"] and l["divisao"] == 1 and l["pais"] in selecoes
            and l["feminina"] == bool(genero) and not l["internacional"] and l["times"] >= 8]
    difs.sort()
    return (difs[len(difs) // 2] if difs else 10.0), selecoes


def nivel_sugerido(liga_api, nacao, genero=0):
    """Nível (média dos 14 mais fortes por time) da liga da API: o da liga do banco de mesmo país, gênero e divisão;
    senão a 1ª divisão do país menos 4,5 por divisão; senão o nível da seleção do país menos a diferença típica entre
    seleção e liga no banco; senão 64 (60 no feminino)."""
    div = N.divisao_pelo_nome(liga_api.get("nome"))
    mesmas = [l for l in ligas_db() if l["nivel"] and str(l["pais"]) == str(nacao) and l["times"] >= 6
              and l["feminina"] == bool(genero) and not l["internacional"]]
    exata = next((l for l in mesmas if l["divisao"] == div), None)
    if exata:
        return exata["nivel"], div, f"igual à {exata['nome']} do banco"
    d1 = next((l for l in mesmas if l["divisao"] == 1), None)
    if d1:
        return round(d1["nivel"] - 4.5 * (div - 1), 1), div, f"{d1['nome']} menos {div - 1} divisão(ões)"
    dif, selecoes = _diferenca_selecao(genero)
    if str(nacao) in selecoes:
        nv = round(selecoes[str(nacao)] - dif - 4.5 * (div - 1), 1)
        return nv, div, f"seleção do país ({selecoes[str(nacao)]}) menos {round(dif, 1)} (diferença típica seleção × liga)"
    return round((60 if genero else 64) - 4.0 * (div - 1), 1), div, "padrão (país sem liga nem seleção no banco)"


def nivel_selecao(nacao, genero):
    """Nível de uma seleção: o da que já existe no banco, ou a média dos 14 melhores jogadores da nação no banco."""
    b = banco()
    nt = N.nivel_times(b)
    for d in b.tabela("teamnationlinks").dicts():
        if d["leagueid"] == G.LIGA_SELECOES[genero] and d["nationid"] == str(nacao) and d["teamid"] in nt:
            return nt[d["teamid"]], "seleção que já existe no banco"
    pl = b.tabela("players")
    c = {n: i for i, n in enumerate(pl.campos)}
    ovs = sorted((int(l[c["overallrating"]]) for l in pl.linhas if l[c["nationality"]] == str(nacao)
                  and (l[c["gender"]] if "gender" in c else "0") == str(genero)), reverse=True)[:14]
    if len(ovs) >= 11:
        return round(sum(ovs) / len(ovs), 1), "14 melhores jogadores da nação no banco"
    return 62.0, "padrão (poucos jogadores da nação no banco)"


def destino_sugerido(nacao, div, genero=0):
    for l in ligas_db():
        if str(l["pais"]) == str(nacao) and l["divisao"] == div and l["times"] >= 4 and l["feminina"] == bool(genero) \
                and not l["internacional"]:
            return l["leagueid"]
    return G.LIGA_RDM.get(genero, "76")


# ------------------------------------------------------------------ estado público
def resumo_item(it):
    d = {k: it.get(k) for k in ("id", "tipo", "nome", "temporada", "modo", "escalacoes", "nivel", "nivel_auto", "nivel_motivo",
                                "destino", "divisao", "estado", "erro", "liga_item", "modelo", "nacao", "nivel_manual",
                                "posicao_tabela", "nivel_offset", "feminino", "selecao", "teamid", "leagueid", "tatica",
                                "tecnico", "estadio", "sel_opcoes", "temporada_nome", "nivel_valor", "menos11", "convocacao")}
    d["api"] = it.get("api")
    d["fonte"] = fonte_de(it)
    if it["tipo"] == "liga":
        d["times"] = it.get("times") or []
        d["prontos"] = sum(1 for t in P["itens"] if t.get("liga_item") == it["id"] and t.get("estado") == "pronto")
    else:
        dd = it.get("dados")
        d["jogadores"] = len(dd["jogadores"]) if dd else 0
        d["formacao"] = dd.get("formacao") if dd else None
        d["custo"] = custo_item(it)
        d["ajustados"] = len([k for k in (it.get("ajustes") or {}) if not k.startswith("_")])
        d["avisos"] = (dd or {}).get("avisos") or []
        d["fotos"] = sum(1 for v in (it.get("fotos") or {}).values() if v and v.get("alvo"))
    return d


def custo_item(it):
    if it["tipo"] != "time" or it.get("dados"):
        return 0
    try:
        if eh_tm(it):
            op = PREFS.ler()
            return CT.estimar(TM, it["api"]["id"], it.get("temporada"), "atual" if it.get("selecao") else (it.get("modo") or "temporada"),
                              {"estatisticas": op.get("tm_estatisticas"), "escalacoes": it.get("escalacoes") or 0})
        if it.get("selecao"):
            return C.estimar_selecao(API, it["api"]["id"], it["temporada"], it.get("escalacoes") or 0)
        return C.estimar(API, it["api"]["id"], it["temporada"], it.get("modo") or "temporada", it.get("escalacoes") or 0,
                         (it.get("liga_api") or {}).get("id"))
    except Exception:  # noqa: BLE001
        return 3


def estado_payload():
    with LOCK:
        itens = [resumo_item(it) for it in P["itens"]]
        tarefa = dict(TAREFA)
        atual = [{k: v for k, v in a.items() if k != "mudancas"} | {"n": len(a.get("mudancas") or []),
                  "marcadas": sum(1 for m in a.get("mudancas") or [] if m.get("aplicar"))} for a in P["atualizacoes"]]
    b = dados.banco_atual()
    est = dados.estado()
    return {"itens": itens, "sel": P["sel"], "tarefa": tarefa, "opcoes": PREFS.ler(), "atualizacoes": atual,
            "api": {"tem_chave": bool(API.chave), "chave": (API.chave[:4] + "…" + API.chave[-4:]) if API.chave else "",
                    "plano": API.cfg.get("plano"), "uso": API.uso(), "temporadas": API.cfg.get("temporadas"),
                    "max_paginas": API.cfg.get("max_paginas")},
            "banco": b.resumo() if b else None, "internationals": est.get("internationals"),
            "tm": tm_status(), "fontes": FONTES,
            "calibracao": N.carregar_coef() if MOTOR["ok"] else {}, "calibracao_tm": N.carregar_coef_tm() if MOTOR["ok"] else {},
            "motor": {"ok": MOTOR["ok"], "msg": MOTOR["msg"], "instalar": not MOTOR["ok"]},
            "fotos_ok": _aparencia_disponivel()}


def api_inicio(_):
    tem = dados.banco_atual() and MOTOR["ok"]
    return {"versao": VERSAO, **estado_payload(), "ligas_db": ligas_db() if tem else [], "nacoes": nacoes_db() if tem else [],
            "formacoes": _formacoes() if tem else [], "estadios": _estadios() if tem else []}


def api_estado(_):
    return estado_payload()


def _formacoes():
    exige_motor()
    pj = G.Projeto.__new__(G.Projeto)
    pj.b, pj.tabs = banco(), {}
    return G.Projeto.formacoes_db(pj)


def _estadios():
    exige_motor()
    pj = G.Projeto.__new__(G.Projeto)
    pj.b, pj.tabs = banco(), {}
    return sorted(({"id": d["stadiumid"], "nome": d["name"].lstrip("_"), "capacidade": int(d["capacity"])}
                   for d in G.Projeto.estadios_genericos(pj)), key=lambda x: x["capacidade"])


# ------------------------------------------------------------------ API-Football: chave e navegação
def _api(fn, *a, **k):
    try:
        return fn(*a, **k)
    except A.ErroApi as ex:
        raise base.ErroUsuario(str(ex))


def api_chave(d):
    API.definir_chave(d.get("chave") or "")
    if API.chave:
        _api(API.status)
    return estado_payload()


def api_status_api(_):
    return _api(API.status)


def _tmc(fn, *a, **k):
    try:
        return fn(*a, **k)
    except T.ErroTm as ex:
        raise base.ErroUsuario(str(ex))


def api_paises(q):
    if q.get("fonte") == "transfermarkt":
        return {"paises": _tmc(CT.paises, TM)}
    return {"paises": _api(C.paises, API)}


def api_ligas(q):
    if q.get("fonte") == "transfermarkt":
        return {"ligas": _tmc(CT.ligas, TM, q["pais"])}
    return {"ligas": _api(C.ligas, API, q["pais"])}


def api_buscar_ligas(q):
    return {"ligas": _tmc(CT.buscar_ligas, TM, q["q"])}


def api_buscar_times(q):
    """Times (clubes ou seleções) pelo nome em toda a fonte: Transfermarkt (busca de clubes) ou API-Football
    (teams?search, 1 chamada; depois cache). No formato da lista de times de uma liga."""
    termo = re.sub(r"[/?#%]+", " ", (q.get("q") or "")).strip()
    if len(termo) < 3:
        raise base.ErroUsuario("Digite pelo menos 3 letras.")
    if q.get("fonte") == "transfermarkt":
        r = _tmc(TM.get, f"clubs/search/{termo}")
        paises = {p["name"].lower() for p in _tmc(CT.paises, TM)}
        out = [{"id": str(c["id"]), "nome": c.get("name"), "sigla": None, "pais": c.get("country"), "fundacao": None,
                "logo": T.escudo(c["id"]), "selecao": (c.get("name") or "").lower() in paises, "fonte": "transfermarkt",
                "valor": c.get("marketValue"), "estadio": {"id": None, "nome": None, "cidade": None, "capacidade": None}}
               for c in r.get("results") or [] if c.get("id")]
        return {"times": out, "temporada": None}
    r = _api(API.get, "teams", search=re.sub(r"[^\w ]+", " ", termo)[:40].strip()) or []
    out = []
    for t in r:
        tm, v = t.get("team") or {}, t.get("venue") or {}
        out.append({"id": tm.get("id"), "nome": tm.get("name"), "sigla": tm.get("code"), "pais": tm.get("country"),
                    "fundacao": tm.get("founded"), "logo": tm.get("logo"), "selecao": bool(tm.get("national")), "fonte": "apifootball",
                    "estadio": {"id": v.get("id"), "nome": v.get("name"), "cidade": v.get("city"), "capacidade": v.get("capacity")}})
    return {"times": out, "temporada": int((API.cfg.get("temporadas") or [None, datetime.date.today().year])[1])}


def api_temporadas(q):
    return {"temporadas": _tmc(CT.temporadas, TM, q["liga"])}


def api_times(q):
    if q.get("fonte") == "transfermarkt":
        info = {"pais": q.get("pais"), "selecoes": q.get("selecoes") in ("1", "true")}
        return {"times": _tmc(CT.times, TM, q["liga"], q.get("temporada") or None, info)}
    return {"times": _api(C.times, API, int(q["liga"]), int(q["temporada"]))}


def api_selecao_tm(q):
    t = _tmc(CT.selecao_de, TM, q["pais"])
    if not t:
        raise base.ErroUsuario(f"Não achei a seleção de {q['pais']} na Transfermarkt.")
    return {"time": t}


def api_tm_config(d):
    try:
        TM.definir(d.get("modo") or "auto", d.get("url"))
    except T.ErroTm as ex:
        raise base.ErroUsuario(str(ex))
    tm_status(forcar=True)
    return estado_payload()


def api_tm_testar(_):
    """Liga o servidor local (se for o caso) e faz um pedido de teste."""
    t0 = time.time()
    _tmc(TM.get, "competitions/BRA1/seasons", usar_cache=False)
    st = tm_status(forcar=True)
    return {"ok": True, "segundos": round(time.time() - t0, 1), **estado_payload(), "tm": st}


# ------------------------------------------------------------------ projeto: adicionar, ajustar, remover
def _novo_time(tm, liga, temporada, modo, liga_item=None, feminino=None):
    op = PREFS.ler()
    fonte = fonte_de(liga) if fonte_de(liga) != "apifootball" else fonte_de(tm)
    pre = "TM" if fonte == "transfermarkt" else ""
    temporada = _temp(fonte, temporada)
    if fonte == "transfermarkt" and temporada and not liga.get("temporada_nome") and liga.get("id"):
        # na Transfermarkt o id da temporada é o ano em que ela começa: no Brasil, "2025" é a temporada 2026
        try:
            nome_t = next((x["nome"] for x in CT.temporadas(TM, liga["id"]) if str(x["id"]) == str(temporada)), None)
        except T.ErroTm:
            nome_t = None
        liga = {**liga, "temporada_nome": nome_t}
    fem = eh_feminino(liga.get("nome"), tm.get("nome")) if feminino is None else bool(feminino)
    gen = 1 if fem else 0
    selecao = bool(tm.get("selecao"))
    if selecao and fonte == "transfermarkt":
        nacao = nacao_de(tm.get("nome"), None) or nacao_de(tm.get("pais"))
        nivel, motivo = nivel_selecao(nacao, gen) if nacao else (62.0, "nação não encontrada")
        nome_pt = next((n["nome"] for n in nacoes_db() if n["id"] == str(nacao)), None) if nacao else None
        return {"id": f"TMS{tm['id']}", "tipo": "time", "selecao": True, "fonte": fonte, "api": tm, "liga_api": liga,
                "temporada": temporada, "temporada_nome": liga.get("temporada_nome"), "modo": "atual", "escalacoes": 0,
                "nome": nome_pt or tm["nome"], "nivel": nivel, "nivel_auto": nivel, "nivel_base": nivel, "nivel_offset": 0,
                "nivel_manual": False, "nivel_motivo": motivo, "divisao": 1, "nacao": nacao, "liga_item": None,
                "destino": G.LIGA_SELECOES[gen], "estado": "pendente", "erro": None, "dados": None, "ajustes": {}, "modelo": None,
                "feminino": fem, "sel_opcoes": {"criar_faltantes": False, "incluir": [], "excluir_db": []}}
    if selecao:
        nacao = nacao_de(re.sub(r"\s+W$", "", tm.get("nome") or ""), None) or nacao_de(tm.get("pais"))
        nivel, motivo = nivel_selecao(nacao, gen) if nacao else (62.0, "nação não encontrada")
        nome_pt = next((n["nome"] for n in nacoes_db() if n["id"] == str(nacao)), None) if nacao else None
        return {"id": f"S{tm['id']}-{temporada}", "tipo": "time", "selecao": True, "api": tm, "liga_api": liga,
                "temporada": int(temporada), "modo": "atual", "escalacoes": 0,
                "nome": (nome_pt + (" (feminina)" if fem else "")) if nome_pt else tm["nome"], "nivel": nivel,
                "nivel_auto": nivel, "nivel_base": nivel, "nivel_offset": 0, "nivel_manual": False, "nivel_motivo": motivo,
                "divisao": 1, "nacao": nacao, "liga_item": None, "destino": G.LIGA_SELECOES[gen], "estado": "pendente",
                "erro": None, "dados": None, "ajustes": {}, "modelo": None, "feminino": fem,
                "sel_opcoes": {"criar_faltantes": False, "incluir": [], "excluir_db": []}}
    nacao = nacao_de(tm.get("pais") or liga.get("pais"), liga.get("codigo_pais") if (tm.get("pais") == liga.get("pais")) else None)
    nivel, div, motivo = nivel_sugerido(liga, nacao, gen)
    return {"id": f"{pre}T{tm['id']}-{temporada}", "tipo": "time", "selecao": False, "fonte": fonte, "api": tm, "liga_api": liga,
            "temporada": temporada, "temporada_nome": liga.get("temporada_nome"), "modo": modo or op["modo"],
            "escalacoes": int(op["escalacoes"]), "nome": tm["nome"],
            "nivel": nivel, "nivel_auto": nivel, "nivel_base": nivel, "nivel_offset": 0, "nivel_manual": False,
            "nivel_motivo": motivo, "divisao": div, "nacao": nacao, "liga_item": liga_item,
            "destino": None if liga_item else destino_sugerido(nacao, div, gen), "estado": "pendente", "erro": None,
            "dados": None, "ajustes": {}, "modelo": None, "feminino": fem}


def api_adicionar_liga(d):
    """Liga inteira (ou só os times escolhidos, d["ids"]) como uma liga nova do projeto."""
    liga = d["liga"]
    fonte = fonte_de(liga)
    temporada = _temp(fonte, d["temporada"])
    if fonte == "transfermarkt":
        times = _tmc(CT.times, TM, liga["id"], temporada, liga)
    else:
        times = _api(C.times, API, liga["id"], temporada)
    if d.get("ids"):
        quer = {str(x) for x in d["ids"]}
        times = [t for t in times if str(t["id"]) in quer]
    if not times:
        raise base.ErroUsuario("A API não tem times dessa competição nessa temporada.")
    if any(t.get("selecao") for t in times):
        return api_adicionar_times({"times": times, "liga": liga, "temporada": temporada})
    pre = "TM" if fonte == "transfermarkt" else ""
    lid = f"{pre}L{liga['id']}-{temporada}"
    with LOCK:
        if any(it["id"] == lid for it in P["itens"]):
            raise base.ErroUsuario("Essa liga já está no projeto.")
        fem = eh_feminino(liga.get("nome"))
        gen = 1 if fem else 0
        nacao = nacao_de(liga.get("pais"), liga.get("codigo_pais"))
        nivel, div, motivo = nivel_sugerido(liga, nacao, gen)
        P["itens"].append({"id": lid, "tipo": "liga", "fonte": fonte, "api": liga, "temporada": temporada,
                           "temporada_nome": liga.get("temporada_nome"), "nome": liga["nome"], "nivel": nivel,
                           "nivel_auto": nivel, "nivel_motivo": motivo, "divisao": div, "nacao": nacao, "destino": "nova",
                           "times": [f"{pre}T{t['id']}-{temporada}" for t in times], "estado": "pendente", "classificacao": None,
                           "feminino": fem, "leagueid": None})
        for t in times:
            tid = f"{pre}T{t['id']}-{temporada}"
            if any(it["id"] == tid for it in P["itens"]):
                continue
            nt = _novo_time(t, liga, temporada, d.get("modo"), lid, fem)
            nt.update(nivel=nivel, nivel_auto=nivel, nivel_base=nivel, nivel_motivo="nível da liga")
            P["itens"].append(nt)
        P["sel"] = lid
    gravar_projeto()
    return estado_payload()


def api_adicionar_time(d):
    return api_adicionar_times({"times": [d["time"]], "liga": d["liga"], "temporada": d["temporada"], "modo": d.get("modo")})


def api_adicionar_times(d):
    """Vários times (ou seleções) avulsos de uma vez."""
    liga = d["liga"]
    temporada = _temp(fonte_de(liga), d["temporada"])
    novos, repetidos = [], []
    with LOCK:
        existentes = {it["id"] for it in P["itens"]}
        for tm in d.get("times") or []:
            nt = _novo_time(tm, liga, temporada, d.get("modo"))
            if nt["id"] in existentes:
                repetidos.append(tm["nome"])
                continue
            P["itens"].append(nt)
            existentes.add(nt["id"])
            novos.append(nt)
        if not novos:
            raise base.ErroUsuario("Esse(s) time(s) já estão no projeto." if repetidos else "Nenhum time escolhido.")
        P["sel"] = novos[-1]["id"] if len(novos) == 1 else P["sel"] or novos[0]["id"]
    gravar_projeto()
    return {**estado_payload(), "adicionados": len(novos), "repetidos": repetidos}


def api_remover(d):
    """Tira um item (d["id"]) ou vários (d["ids"]); uma liga leva os times dela junto."""
    with LOCK:
        tira = set()
        for iid in (d.get("ids") or [d.get("id")]):
            it = item(iid)
            tira |= {it["id"]} | (set(it.get("times") or []) if it["tipo"] == "liga" else set())
        for lig in [x for x in P["itens"] if x["tipo"] == "liga" and x["id"] not in tira]:
            lig["times"] = [t for t in lig.get("times") or [] if t not in tira]
        P["itens"] = [x for x in P["itens"] if x["id"] not in tira]
        if P["sel"] in tira:
            P["sel"] = None
    gravar_projeto()
    return estado_payload()


def api_limpar(_):
    with LOCK:
        P.update(itens=[], sel=None, atualizacoes=[])
    gravar_projeto()
    return estado_payload()


def api_selecionar(d):
    with LOCK:
        P["sel"] = d.get("id")
    gravar_projeto()
    return estado_payload()


EDITAVEIS = {"nome", "nivel", "destino", "modo", "temporada", "escalacoes", "modelo", "divisao", "feminino", "teamid", "leagueid",
             "tatica", "tecnico", "estadio", "sel_opcoes", "menos11", "convocacao"}


def _id_livre(campo, valor, it):
    """Confere um id escolhido à mão: inteiro, dentro da faixa do banco, livre no banco e nos outros itens."""
    if valor in (None, ""):
        return None
    try:
        v = int(valor)
    except (TypeError, ValueError):
        raise base.ErroUsuario("O id é um número inteiro.")
    b = banco()
    tab, col = {"teamid": ("teams", "teamid"), "leagueid": ("leagues", "leagueid"), "playerid": ("players", "playerid")}[campo]
    t = b.tabela(tab)
    info = t.info.get(col, {})
    alto = int(info.get("high") or 0) or (1 << int(info.get("bits", 16))) - 1
    if not 1 <= v <= alto:
        raise base.ErroUsuario(f"O {campo} precisa ficar entre 1 e {alto}.")
    if str(v) in set(t.valores(col)):
        raise base.ErroUsuario(f"O {campo} {v} já existe no banco.")
    if campo == "teamid" and str(v) in set(b.tabela("teamkits").valores("teamtechid")):
        raise base.ErroUsuario(f"O teamid {v} já tem uniformes no banco (teamkits): escolha outro.")
    for x in P["itens"]:
        if x is it:
            continue
        if campo in ("teamid", "leagueid") and str(x.get(campo) or "") == str(v):
            raise base.ErroUsuario(f"O {campo} {v} já foi escolhido para {x['nome']}.")
        if campo == "playerid":
            for k, a in (x.get("ajustes") or {}).items():
                if isinstance(a, dict) and str(a.get("playerid") or "") == str(v):
                    raise base.ErroUsuario(f"O playerid {v} já foi escolhido em {x['nome']}.")
    return v


def api_item(d):
    """Altera campos de um item; nível/modo/temporada/feminino de uma liga valem para os times dela."""
    with LOCK:
        it = item(d["id"])
        mudou_coleta = False
        for k, v in d.items():
            if k not in EDITAVEIS:
                continue
            if k == "nivel":
                if v in (None, ""):
                    it["nivel_manual"] = False
                    continue
                v = float(v)
                if it["tipo"] == "time":
                    it["nivel_manual"] = True
            if k in ("escalacoes", "divisao"):
                v = int(v)
            if k == "temporada":
                v = _temp(fonte_de(it), v)
            if k in ("teamid", "leagueid"):
                v = _id_livre(k, v, it)
            if k in ("tatica", "tecnico", "estadio", "sel_opcoes"):
                atual = dict(it.get(k) or {})
                for kk, vv in (v or {}).items():
                    if vv in (None, ""):
                        atual.pop(kk, None)
                    else:
                        atual[kk] = vv
                v = atual
            if k == "feminino":
                v = bool(v)
            if k == "convocacao":
                v = str(v) if v not in (None, "") else None
            if k in ("modo", "temporada", "escalacoes", "convocacao") and it.get(k) != v:
                mudou_coleta = True
            it[k] = v
        filhos = [x for x in P["itens"] if x.get("liga_item") == it["id"]] if it["tipo"] == "liga" else []
        for f in filhos:
            for k in ("modo", "temporada", "escalacoes"):
                if k in d and f.get(k) != it[k]:
                    f[k] = it[k]
                    f.update(dados=None, estado="pendente")
            if "feminino" in d:
                f["feminino"] = it["feminino"]
        if "feminino" in d:                                # o gênero muda os níveis de referência e o destino
            for x in [it] + filhos:
                if x.get("selecao"):
                    continue
                gen = 1 if x["feminino"] else 0
                nv, div, motivo = nivel_sugerido(x.get("liga_api") or x.get("api") or {}, x.get("nacao"), gen)
                x.update(nivel_base=nv, nivel_motivo=motivo)
                if x["tipo"] == "liga":
                    x.update(nivel=nv, nivel_auto=nv)
                elif not x.get("liga_item"):
                    x["destino"] = destino_sugerido(x.get("nacao"), x.get("divisao") or 1, gen)
        if mudou_coleta and it["tipo"] == "time":
            it.update(dados=None, estado="pendente")
        recalcular_niveis()
    gravar_projeto()
    return estado_payload()


CAMPOS_JOGADOR = ("overall", "pos", "pe", "potencial", "excluir", "nomes", "camisa", "nascimento", "nacao", "altura", "peso",
                  "perna_ruim", "dribles", "playerid", "posicoes2", "capitao", "playerid_banco")


def api_ajustar(d):
    """Ajuste manual de um jogador (qualquer coluna que vai para o jogo) ou do time (_time_nome…)."""
    with LOCK:
        it = item(d["id"])
        aj = it.setdefault("ajustes", {})
        chave = str(d.get("api_id") or "_time")
        if chave == "_time":
            for k in ("_time_nome", "_time_abrev15", "_time_abrev10", "_time_sigla", "_usar_db_todos"):
                if k in d:
                    if d[k]:
                        aj[k] = d[k]
                    else:
                        aj.pop(k, None)
        else:
            a = aj.setdefault(chave, {})
            if "playerid" in d and d["playerid"] not in (None, ""):
                d["playerid"] = _id_livre("playerid", d["playerid"], it)
            if d.get("capitao"):                       # um capitão só
                for k2, a2 in aj.items():
                    if isinstance(a2, dict):
                        a2.pop("capitao", None)
            for k in CAMPOS_JOGADOR:
                if k in d:
                    if d[k] in (None, "", False):
                        a.pop(k, None)
                    else:
                        a[k] = d[k]
            if "usar_db" in d:                             # jogador que já está no banco: True usa, False cria outro, None automático
                if d["usar_db"] is None:
                    a.pop("usar_db", None)
                else:
                    a["usar_db"] = bool(d["usar_db"])
            for k in ("atr", "aparencia"):                 # dicionários: mescla (valor vazio volta ao gerado)
                if k in d:
                    atual = dict(a.get(k) or {})
                    for kk, vv in (d[k] or {}).items():
                        if vv in (None, ""):
                            atual.pop(kk, None)
                        else:
                            atual[kk] = int(vv)
                    if atual:
                        a[k] = atual
                    else:
                        a.pop(k, None)
            if not a:
                aj.pop(chave, None)
        if d.get("limpar"):
            it["ajustes"] = {}
    gravar_projeto()
    return api_previa({"id": d["id"]})


def api_selecao(d):
    """Seleção: incluir/excluir jogadores do banco, casar um convocado com um jogador do banco, criar os que faltam."""
    with LOCK:
        it = item(d["id"])
        so = it.setdefault("sel_opcoes", {"criar_faltantes": False, "incluir": [], "excluir_db": []})
        if "criar_faltantes" in d:
            so["criar_faltantes"] = bool(d["criar_faltantes"])
            so["criar"] = {}                                # "criar todos"/"nenhum" desfaz as escolhas de um por um
        if "criar_um" in d:                                 # {api_id, criar}: este convocado é criado ou não
            so.setdefault("criar", {})[str(d["criar_um"]["api_id"])] = bool(d["criar_um"].get("criar"))
        if d.get("incluir"):
            pid = str(d["incluir"])
            so["incluir"] = [x for x in so.get("incluir") or [] if x != pid] + [pid]
            so["excluir_db"] = [x for x in so.get("excluir_db") or [] if x != pid]
        if d.get("excluir"):
            pid = str(d["excluir"])
            so["excluir_db"] = [x for x in so.get("excluir_db") or [] if x != pid] + [pid]
            so["incluir"] = [x for x in so.get("incluir") or [] if x != pid]
        if d.get("voltar"):
            pid = str(d["voltar"])
            so["excluir_db"] = [x for x in so.get("excluir_db") or [] if x != pid]
        if "casar" in d:                                    # {api_id, playerid}
            a = it.setdefault("ajustes", {}).setdefault(str(d["casar"]["api_id"]), {})
            if d["casar"].get("playerid"):
                a["playerid_banco"] = str(d["casar"]["playerid"])
            else:
                a.pop("playerid_banco", None)
    gravar_projeto()
    return api_previa({"id": d["id"]})


def api_times_db(_):
    """Times de clube do banco (para casar à mão um time da API)."""
    b = banco()
    especiais = {"78", "2136", "382", "383", "2255"}
    return {"times": [t for t in b.times(dados.idioma_atual()) if t.get("leagueid") not in especiais]}


def api_jogadores_db(q):
    """Busca jogadores do banco por nome (para pôr numa seleção ou casar com um convocado)."""
    exige_motor()
    b = banco()
    termo = dados.normalizar(q.get("q") or "")
    nacao, genero = q.get("nacao"), q.get("genero")
    pl = b.tabela("players")
    c = {n: i for i, n in enumerate(pl.campos)}
    nomes_time = {t["teamid"]: t["nome"] for t in b.times(dados.idioma_atual())}
    clube = {}
    for dd in b.tabela("teamplayerlinks").dicts():
        clube.setdefault(dd["playerid"], dd["teamid"])
    out = []
    for l in pl.linhas:
        if nacao and l[c["nationality"]] != str(nacao):
            continue
        if genero not in (None, "") and "gender" in c and l[c["gender"]] != str(genero):
            continue
        j = b.jogador(dict(zip(pl.campos, l)))
        alvo = dados.normalizar(f"{j['nome']} {j['primeiro']} {j['sobrenome']}")
        if termo and termo not in alvo:
            continue
        out.append({"playerid": j["playerid"], "nome": j["nome"], "overall": int(l[c["overallrating"]]),
                    "pos": int(l[c["preferredposition1"]]), "pos_nome": N.NOME_POS.get(int(l[c["preferredposition1"]]), "?"),
                    "clube": nomes_time.get(clube.get(j["playerid"])), "nacao": l[c["nationality"]]})
    out.sort(key=lambda x: -x["overall"])
    return {"jogadores": out[:60]}


# ------------------------------------------------------------------ coleta (em segundo plano)
def api_coletar(d):
    with LOCK:
        if TAREFA["ativa"]:
            raise base.ErroUsuario("Já há uma tarefa em andamento.")
        ids = d.get("ids")
        alvo = []
        for it in P["itens"]:
            if it["tipo"] != "time":
                continue
            if ids and it["id"] not in ids and it.get("liga_item") not in ids:
                continue
            if it.get("dados") and not d.get("refazer"):
                continue
            alvo.append(it["id"])
        if not alvo:
            raise base.ErroUsuario("Nada para coletar: os times escolhidos já têm os dados.")
        TAREFA.update(ativa=True, tipo="coleta", msg="Começando…", feito=0, total=len(alvo), erro=None, fim=0, resultado=None)
    threading.Thread(target=_coletar, args=(alvo, bool(d.get("refazer"))), daemon=True).start()
    return estado_payload()


def _coletar(ids, refazer):
    op = PREFS.ler()
    erros = []
    try:
        ligas_feitas = set()
        for n, iid in enumerate(ids):
            with LOCK:
                it = item(iid)
                it["estado"] = "coletando"
            TAREFA.update(feito=n, msg=f"{it['nome']}…")
            liga = it.get("liga_api") or {}
            lig_item = next((x for x in P["itens"] if x["id"] == it.get("liga_item")), None)
            if not it.get("selecao") and op.get("classificacao") and liga.get("id") and liga["id"] not in ligas_feitas:
                ligas_feitas.add(liga["id"])
                try:
                    if eh_tm(it):
                        _CLASSIF[("tm", liga["id"], it.get("temporada"))] = CT.classificacao(TM, liga["id"], it.get("temporada"))
                    else:
                        _classificacao(liga["id"], it["temporada"] if it.get("modo") != "atual" else C.ultima_temporada(API, it["temporada"]))
                except (A.ErroApi, T.ErroTm) as ex:
                    erros.append(f"Classificação de {liga.get('nome')}: {ex}")
            try:
                if eh_tm(it):
                    prog = lambda m: TAREFA.update(msg=m)  # noqa: E731
                    if it.get("selecao"):
                        dd = CT.coletar_selecao(TM, it["api"], progresso=prog, temporada=it.get("convocacao"))
                    else:
                        dd = CT.coletar_time(TM, it["api"], it.get("temporada"), it.get("modo") or "temporada",
                                             {"estatisticas": op.get("tm_estatisticas"), "escalacoes": int(it.get("escalacoes") or 0),
                                              "temporada_nome": it.get("temporada_nome")}, liga, progresso=prog)
                    with LOCK:
                        it.update(dados=dd, estado="pronto", erro=None)
                        # a lista de times da Transfermarkt não traz estádio nem sigla: vêm do perfil do clube
                        tt = dd.get("time") or {}
                        if not it.get("selecao") and it.get("nome") == it["api"].get("nome") and tt.get("nome"):
                            it["nome"] = tt["nome"]          # nome oficial da lista -> nome curto do perfil (se não foi trocado)
                        it["api"] = {**it["api"], **{k: tt[k] for k in ("estadio", "sigla", "pais", "nome") if tt.get(k)}}
                        if not it.get("selecao"):
                            _nivel_pelo_valor(it, lig_item)
                    gravar_projeto()
                    continue
                if it.get("selecao"):
                    dd = C.coletar_selecao(API, it["api"], C.ultima_temporada(API, it["temporada"]), int(it.get("escalacoes") or 0),
                                           progresso=lambda m: TAREFA.update(msg=m), convocacao=it.get("convocacao"))
                else:
                    dd = C.coletar_time(API, it["api"], it["temporada"], it.get("modo") or "temporada", int(it.get("escalacoes") or 0),
                                        int(op.get("perfis_faltantes") or 0), liga.get("id"),
                                        progresso=lambda m: TAREFA.update(msg=m))
                    if op.get("completar_tm"):                 # o que a API não dá: nascimento, pé, posição exata, altura…
                        try:
                            dd.setdefault("avisos", []).append(CT.completar_api(TM, dd, it.get("temporada"), it.get("modo") or "temporada",
                                                                                progresso=lambda m: TAREFA.update(msg=m)))
                        except T.ErroTm as ex:
                            dd.setdefault("avisos", []).append(f"Transfermarkt (completar): {ex}")
                with LOCK:
                    it.update(dados=dd, estado="pronto", erro=None)
                    if not it.get("selecao"):
                        _nivel_pela_classificacao(it, lig_item)
            except (A.ErroApi, T.ErroTm) as ex:
                with LOCK:
                    it.update(estado="erro", erro=str(ex))
                erros.append(f"{it['nome']}: {ex}")
                if "Limite diário" in str(ex):
                    break
            except Exception as ex:  # noqa: BLE001
                traceback.print_exc()
                with LOCK:
                    it.update(estado="erro", erro=f"{type(ex).__name__}: {ex}")
                erros.append(f"{it['nome']}: {ex}")
            gravar_projeto()
        TAREFA.update(feito=len(ids), msg="Coleta concluída." if not erros else f"Coleta terminou com {len(erros)} problema(s).",
                      erro="\n".join(erros) or None)
    finally:
        TAREFA.update(ativa=False, fim=time.time())
        gravar_projeto()


_CLASSIF = {}


def _classificacao(liga_id, temporada):
    r = API.get("standings", league=liga_id, season=temporada)
    tabela = {}
    for bloco in r or []:
        for grupo in (bloco.get("league") or {}).get("standings") or []:
            for linha in grupo:
                tid = (linha.get("team") or {}).get("id")
                jogos = ((linha.get("all") or {}).get("played") or 0)
                if tid and jogos:
                    tabela[tid] = {"pos": linha.get("rank"), "ppj": (linha.get("points") or 0) / jogos}
    _CLASSIF[(liga_id, temporada)] = tabela
    return tabela


def recalcular_niveis():
    """Nível de cada time = nível da liga (item da liga ou sugerido) + deslocamento da classificação, salvo ajuste manual.
    Transfermarkt: o nível pelo valor de mercado do elenco; mudar o nível da liga desloca todos os times dela."""
    for lig in [x for x in P["itens"] if x["tipo"] == "liga" and eh_tm(x)]:
        filhos = [x for x in P["itens"] if x.get("liga_item") == lig["id"] and x.get("nivel_valor") and not x.get("tm_antiga")]
        if filhos:
            media = round(sum(x["nivel_valor"] for x in filhos) / len(filhos), 1)
            lig["nivel_auto"] = media
            lig["nivel_motivo"] = f"média dos times pelo valor de mercado ({len(filhos)} com dados)"
            if not lig.get("nivel_manual"):
                lig["nivel"] = media
    for it in P["itens"]:
        if it["tipo"] != "time" or it.get("selecao"):
            continue
        lig = next((x for x in P["itens"] if x["id"] == it.get("liga_item")), None)
        if eh_tm(it) and it.get("nivel_valor") and not it.get("tm_antiga"):
            desloc = float(lig["nivel"]) - float(lig["nivel_auto"]) if lig and lig.get("nivel_manual") and lig.get("nivel_auto") else 0.0
            it["nivel_auto"] = round(it["nivel_valor"] + desloc, 1)
            if not it.get("nivel_manual"):
                it["nivel"] = it["nivel_auto"]
            continue
        base_n = float((lig or {}).get("nivel") or it.get("nivel_base") or it.get("nivel_auto") or 65)
        it["nivel_auto"] = round(base_n + float(it.get("nivel_offset") or 0), 1)
        if not it.get("nivel_manual"):
            it["nivel"] = it["nivel_auto"]


def _nivel_pelo_valor(it, lig_item):
    """Transfermarkt: nível = média das 14 maiores notas que o valor de mercado dá; a classificação só dá a força na
    tabela (tática) e a posição. Temporada antiga (terminou há mais de 2 anos): os valores de mercado de então são bem
    menores que os de hoje, então o nível vem da liga do banco + a classificação (como na API-Football) e o valor de
    mercado só distribui as notas dentro do elenco."""
    exige_motor()
    nv = G.nivel_pelo_valor(it["dados"])
    it["tm_antiga"] = bool(G.temporada_antiga_tm(it["dados"]))
    if nv:
        it["nivel_valor"] = nv
        it["nivel_motivo"] = "pelo valor de mercado do elenco (Transfermarkt)"
    tab = _CLASSIF.get(("tm", (it.get("liga_api") or {}).get("id"), it.get("temporada")))
    if tab is None:
        c = TM.do_cache(f"competitions/{(it.get('liga_api') or {}).get('id')}/table", season_id=it.get("temporada"))
        if c:
            tab = {}
            for t in c.get("tables") or []:
                for l in t.get("rows") or []:
                    if l.get("matches"):
                        tab[str(l["clubId"])] = {"pos": l.get("position"), "ppj": (l.get("points") or 0) / l["matches"]}
    if tab and str(it["api"]["id"]) in tab:
        vals = [v["ppj"] for v in tab.values()]
        media = sum(vals) / len(vals)
        dp = (sum((v - media) ** 2 for v in vals) / len(vals)) ** 0.5 or 1
        it["posicao_tabela"] = tab[str(it["api"]["id"])]["pos"]
        it["forca"] = round((tab[str(it["api"]["id"])]["ppj"] - media) / dp, 2)
    elif it.get("dados", {}).get("posse"):
        it["forca"] = round((it["dados"]["posse"] - 50) / 6.0, 2)       # sem tabela: a posse de bola dá a ideia
    it["nivel_offset"] = 0
    if it["tm_antiga"]:
        tem_tab = bool(tab and str(it["api"]["id"]) in tab)
        it["nivel_offset"] = round(max(-3.5, min(3.5, 1.2 * it.get("forca", 0))), 1) if tem_tab else 0
        sinal = "+" if it["nivel_offset"] >= 0 else ""
        it["nivel_motivo"] = (f"temporada antiga ({it.get('temporada_nome') or it.get('temporada')}): nível da liga do banco"
                              + (f" {sinal}{it['nivel_offset']} pela classificação ({it['posicao_tabela']}º)" if tem_tab else "")
                              + f"; o valor de mercado da época só distribui as notas no elenco (por ele seria {nv})")
    recalcular_niveis()


def _nivel_pela_classificacao(it, lig_item):
    """Nível do time = nível da liga + 1,2 × desvios do aproveitamento na tabela (no máximo ±3,5)."""
    liga = (it.get("liga_api") or {}).get("id")
    tp = it["temporada"] if it.get("modo") != "atual" else C.ultima_temporada(API, it["temporada"])
    tab = _CLASSIF.get((liga, tp))
    if tab is None:
        c = API.do_cache("standings", league=liga, season=tp)
        if c:
            _CLASSIF[(liga, tp)] = tab = {}
            for bloco in c.get("response") or []:
                for grupo in (bloco.get("league") or {}).get("standings") or []:
                    for linha in grupo:
                        jogos = ((linha.get("all") or {}).get("played") or 0)
                        if jogos:
                            tab[linha["team"]["id"]] = {"pos": linha.get("rank"), "ppj": (linha.get("points") or 0) / jogos}
    if not tab or it["api"]["id"] not in tab:
        it["nivel_offset"] = 0
        recalcular_niveis()
        return
    vals = [v["ppj"] for v in tab.values()]
    media = sum(vals) / len(vals)
    dp = (sum((v - media) ** 2 for v in vals) / len(vals)) ** 0.5 or 1
    z = (tab[it["api"]["id"]]["ppj"] - media) / dp
    it["posicao_tabela"] = tab[it["api"]["id"]]["pos"]
    it["forca"] = round(z, 2)
    it["nivel_offset"] = round(max(-3.5, min(3.5, 1.2 * z)), 1)   # 1,2 ponto por desvio do aproveitamento
    it["nivel_motivo"] = f"liga {('+' if it['nivel_offset'] >= 0 else '')}{it['nivel_offset']} pela classificação ({it['posicao_tabela']}º)"
    recalcular_niveis()


# ------------------------------------------------------------------ prévia e geração
def _projeto(op=None):
    exige_motor()
    op = op or PREFS.ler()
    return G.Projeto(banco(), dados.idioma_atual(), perfil(), {k: op[k] for k in ("jogador_inicio", "time_inicio", "liga_inicio", "espalhamento") if k in op})


def _genero(it):
    return 1 if it.get("feminino") else 0


def _extra(it, op=None):
    op = op or PREFS.ler()
    ex = {"modelo": it.get("modelo"), "visual": op.get("visual") or "proprio", "posicao_tabela": it.get("posicao_tabela"),
          "teamid": it.get("teamid"), "tatica": it.get("tatica") or {}, "tecnico": it.get("tecnico") or {},
          "estadio": it.get("estadio") or {}, "forca": it.get("forca"), "menos11": it.get("menos11"),
          "fotos": _alvos_foto(it) if op.get("aparencia_fotos", True) else {}}
    if it.get("selecao"):
        intl = dados.internationals_atual()
        so = it.get("sel_opcoes") or {}
        ex.update(nacao=it.get("nacao"), limites=intl.squad() if intl else None, idade_maxima=intl.idade_maxima() if intl else 35,
                  criar_faltantes=so.get("criar_faltantes"), criar=so.get("criar") or {}, incluir=so.get("incluir") or [],
                  excluir_db=so.get("excluir_db") or [],
                  forca=(float(it.get("nivel") or 76) - 76.0) / 4.0)
    return ex


def _criar(pj, it, destino):
    if it.get("selecao"):
        return pj.criar_selecao(it["dados"], float(it.get("nivel") or 70), _genero(it), it.get("ajustes") or {}, _extra(it))
    aj = dict(it.get("ajustes") or {})
    if it.get("nome") and it["nome"] != (it.get("api") or {}).get("nome"):      # nome trocado no painel do item
        aj.setdefault("_time_nome", it["nome"])
    return pj.criar_time(it["dados"], destino, float(it.get("nivel") or 65), _genero(it), aj, _extra(it))


def api_previa(q):
    it = item(q["id"])
    if it["tipo"] != "time":
        raise base.ErroUsuario("A prévia é de um time.")
    if not it.get("dados"):
        return {"id": it["id"], "time": None}
    pj = _projeto()
    destino = it.get("destino") or G.LIGA_RDM.get(_genero(it), "76")
    if it.get("liga_item"):
        lig = item(it["liga_item"])
        destino = lig.get("destino") if lig.get("destino") not in (None, "nova") else "0"
    try:
        r = _criar(pj, it, destino)
    except ValueError as ex:
        if str(ex).startswith(G.MENOS_DE_11):
            return {"id": it["id"], "time": None, "menos11": {"msg": str(ex)[len(G.MENOS_DE_11):]}}
        raise base.ErroUsuario(str(ex))
    modelo_nome = next((t["nome"] for t in banco().times(dados.idioma_atual()) if t["teamid"] == r["modelo"]), r["modelo"])
    r["modelo_nome"] = modelo_nome
    r["ajustes"] = it.get("ajustes") or {}
    r["sel_opcoes"] = it.get("sel_opcoes")
    return {"id": it["id"], "time": r}


def _reservar_manuais(pj, itens):
    """Ids escolhidos à mão entram primeiro (assim nenhum id automático cai em cima deles)."""
    for it in itens:
        if it["tipo"] == "liga" and it.get("leagueid") and it.get("destino") in (None, "nova"):
            pj.ids("liga", "leagues", "leagueid", "liga_inicio").reservar(it["leagueid"], "leagueid")
        if it["tipo"] == "time":
            if it.get("teamid") and (not it.get("selecao") or not pj.selecao_existente(it.get("nacao"), _genero(it))):
                pj.ids_time().reservar(it["teamid"], "teamid")
            for a in (it.get("ajustes") or {}).values():
                if isinstance(a, dict) and a.get("playerid"):
                    pj.ids_jogador().reservar(a["playerid"], "playerid")


def api_gerar(d):
    with LOCK:
        if TAREFA["ativa"]:
            raise base.ErroUsuario("Já há uma tarefa em andamento.")
        times = [it for it in P["itens"] if it["tipo"] == "time"]
        atual = [a for a in P["atualizacoes"] if any(m.get("aplicar") for m in a.get("mudancas") or [])]
        if not times and not atual:
            raise base.ErroUsuario("O projeto está vazio: adicione uma liga, um time ou uma seleção — ou marque mudanças em Atualizar banco.")
        sem = [it["nome"] for it in times if not it.get("dados")]
        if sem:
            raise base.ErroUsuario(f"Faltam os dados de {len(sem)} time(s) ({', '.join(sem[:4])}{'…' if len(sem) > 4 else ''}). Use Coletar primeiro.")
    op = PREFS.ler()
    pasta = d.get("pasta") or op.get("saida")
    if not pasta:
        pasta = base.dialogo("pasta", "Pasta onde gravar o banco novo", os.path.join(base.raiz_trabalho()))
        if not pasta:
            return {"cancelado": True, **estado_payload()}
        PREFS.atualizar(saida=pasta)
    nome = d.get("nome") or time.strftime("Criador %Y-%m-%d %H%M")
    with LOCK:
        TAREFA.update(ativa=True, tipo="gerar", msg="Preparando…", feito=0, total=len(times), erro=None, fim=0, resultado=None)
    threading.Thread(target=_gerar, args=(pasta, nome, copy.deepcopy(P["itens"]), copy.deepcopy(P["atualizacoes"])), daemon=True).start()
    return estado_payload()


def _gerar(pasta, nome, itens, atualizacoes):
    op = PREFS.ler()
    try:
        pj = _projeto(op)
        _reservar_manuais(pj, itens)
        # atualizações do banco (elencos, participantes) primeiro: os times novos entram por cima delas
        if any(any(m.get("aplicar") for m in a.get("mudancas") or []) for a in atualizacoes):
            import atualizar as U
            TAREFA.update(msg="Aplicando as atualizações do banco…")
            U.aplicar(pj, atualizacoes)
        ligas_novas = {}
        for it in itens:
            if it["tipo"] == "liga" and it.get("destino") in (None, "nova"):
                ligas_novas[it["id"]] = pj.criar_liga(it["nome"], it.get("nacao") or "211", int(it.get("divisao") or 1),
                                                      _genero(it), api_id=(it.get("api") or {}).get("id"), leagueid=it.get("leagueid"))
        times = [it for it in itens if it["tipo"] == "time"]
        for n, it in enumerate(times):
            TAREFA.update(feito=n, msg=f"Gerando {it['nome']}…")
            if it.get("liga_item"):
                lig = next((x for x in itens if x["id"] == it["liga_item"]), {})
                destino = ligas_novas.get(it["liga_item"]) or lig.get("destino") or G.LIGA_RDM.get(_genero(it), "76")
            else:
                destino = it.get("destino") or G.LIGA_RDM.get(_genero(it), "76")
            _criar(pj, it, destino)
        if pj.clubes_mexidos:                              # clubes do banco que perderam jogadores para os times novos
            import atualizar as U
            for tid in sorted(pj.clubes_mexidos - {G.TIME_SEM_CONTRATO}):
                U.reescalar(pj, tid)                       # com menos de 11, entram jogadores sem contrato
        TAREFA.update(msg="Gravando o banco…", feito=len(times))
        r = S.gravar(pj, pasta, nome, dados.idioma_atual(), bool(op.get("baixar_imagens")),
                     progresso=lambda m, f=None: TAREFA.update(msg=m), internationals=dados.internationals_atual())
        r["times"] = sum(1 for t in pj.resumo if not t.get("selecao"))
        r["selecoes"] = sum(1 for t in pj.resumo if t.get("selecao"))
        r["jogadores"] = sum(1 for t in pj.resumo for j in t["jogadores"] if not j.get("existente"))
        r["ligas"] = len(ligas_novas)
        if op.get("minifaces_auto") and r.get("fotos"):
            r["minifaces"] = _fila_minifaces(r)
        TAREFA.update(msg="Banco gravado.", resultado=r)
    except ValueError as ex:                               # problema explicado (não é erro do programa)
        TAREFA.update(erro=str(ex).replace(G.MENOS_DE_11, ""), msg="A geração parou.")
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        TAREFA.update(erro=f"{type(ex).__name__}: {ex}", msg="A geração falhou.")
    finally:
        TAREFA.update(ativa=False, fim=time.time())


# ------------------------------------------------------------------ aparência pelas fotos
def _aparencia_disponivel():
    try:
        import aparencia  # noqa: F401
        return aparencia.disponivel()
    except Exception:  # noqa: BLE001
        return False


def _alvos_foto(it):
    """{api_id: alvo} das fotos já analisadas deste item (campos do jogo, peso)."""
    out = {}
    for k, v in (it.get("fotos") or {}).items():
        if v and v.get("alvo"):
            out[str(k)] = {c: tuple(x) for c, x in v["alvo"].items()}
    return out


def api_analisar_fotos(d):
    """Baixa as fotos (não gasta chamadas) e lê tom de pele, cor e comprimento do cabelo e barba de cada jogador."""
    if not _aparencia_disponivel():
        raise base.ErroUsuario("A análise das fotos usa o OpenCV (componentes do Criador de Minifaces). Baixe em Componentes, no Super Tool.")
    with LOCK:
        if TAREFA["ativa"]:
            raise base.ErroUsuario("Já há uma tarefa em andamento.")
        alvo = [it["id"] for it in P["itens"] if it["tipo"] == "time" and it.get("dados")
                and (not d.get("ids") or it["id"] in d["ids"] or it.get("liga_item") in d["ids"])]
        if not alvo:
            raise base.ErroUsuario("Colete os times primeiro: as fotos vêm com os dados.")
        TAREFA.update(ativa=True, tipo="fotos", msg="Analisando as fotos…", feito=0, total=len(alvo), erro=None, fim=0, resultado=None)
    threading.Thread(target=_analisar_fotos, args=(alvo, bool(d.get("refazer"))), daemon=True).start()
    return estado_payload()


def _analisar_fotos(ids, refazer):
    import aparencia
    erros = []
    try:
        for n, iid in enumerate(ids):
            with LOCK:
                it = item(iid)
            TAREFA.update(feito=n, msg=f"Fotos de {it['nome']}…")
            fotos = dict(it.get("fotos") or {}) if not refazer else {}
            gen = _genero(it)
            pessoas = [(str(j["id"]), j.get("foto")) for j in it["dados"]["jogadores"] if j.get("foto")]
            tec = it["dados"].get("tecnico") or {}
            if tec.get("foto"):
                pessoas.append(("_tecnico", tec["foto"]))
            for k, url in pessoas:
                if k in fotos and fotos[k]:
                    continue
                try:
                    fotos[k] = aparencia.analisar_url(url, A.baixar, os.path.join(API.cache, "img"), gen)
                except Exception as ex:  # noqa: BLE001
                    fotos[k] = {"erro": str(ex)}
            with LOCK:
                it["fotos"] = fotos
            gravar_projeto()
        TAREFA.update(feito=len(ids), msg="Fotos analisadas.", erro="\n".join(erros) or None)
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        TAREFA.update(erro=f"{type(ex).__name__}: {ex}", msg="A análise das fotos falhou.")
    finally:
        TAREFA.update(ativa=False, fim=time.time())


# ------------------------------------------------------------------ Criador de Minifaces
FILA_MINIFACES = os.path.join(A.pasta_dados(), "minifaces_fila.json")


def _fila_minifaces(resultado):
    """Fotos do banco gerado -> fila do Criador de Minifaces (ele lê ao abrir ou na próxima atualização), já ligadas
    aos playerids novos."""
    fotos = resultado.get("fotos") or []
    if not fotos:
        raise base.ErroUsuario("Esse banco não tem fotos baixadas (ative \"Baixar escudos e fotos\" e gere de novo).")
    os.makedirs(os.path.dirname(FILA_MINIFACES), exist_ok=True)
    try:
        with open(FILA_MINIFACES, encoding="utf-8") as f:
            fila = json.load(f)
    except (OSError, ValueError):
        fila = {"itens": []}
    ja = {x["caminho"] for x in fila["itens"]}
    novos = [f for f in fotos if f["caminho"] not in ja]
    fila["itens"] += novos
    fila["origem"] = resultado.get("pasta")
    with open(FILA_MINIFACES + ".tmp", "w", encoding="utf-8") as f:
        json.dump(fila, f, ensure_ascii=False)
    os.replace(FILA_MINIFACES + ".tmp", FILA_MINIFACES)
    return len(novos)


def api_minifaces(d):
    r = TAREFA.get("resultado") or {}
    pasta = d.get("pasta") or r.get("pasta")
    if not r.get("fotos") and pasta:
        try:
            with open(os.path.join(pasta, "projeto.json"), encoding="utf-8") as f:
                r = {"pasta": pasta, "fotos": json.load(f).get("fotos") or []}
        except (OSError, ValueError):
            pass
    n = _fila_minifaces(r)
    return {"enviadas": n, "total": len(r.get("fotos") or [])}


# ------------------------------------------------------------------ atualizar o banco (elencos e participantes)
def _atualizar_mod():
    exige_motor()
    import atualizar as U
    return U


def api_atualizar_ligas(_):
    """Ligas do banco com o par sugerido na API (país + divisão) — ponto de partida do Atualizar banco — e as ligas de
    seleções (masculina e feminina), que se atualizam pondo as seleções no projeto."""
    U = _atualizar_mod()
    return {"ligas": U.ligas_do_banco(banco(), dados.idioma_atual(), ligas_db()),
            "selecoes": U.ligas_selecoes_do_banco(banco(), dados.idioma_atual(), ligas_db())}


def _ultima_liberada(liga):
    """A temporada mais recente que o plano da API-Football libera numa liga (a atual, se o plano liberar)."""
    t = API.cfg.get("temporadas")
    ts = [a for a in liga.get("temporadas") or [] if not t or t[0] <= a <= t[1]]
    return max(ts) if ts else liga.get("atual")


def _preparar_uma(fonte, leagueid):
    """Casa os times de uma liga do banco com a liga sugerida (mesmo país e divisão) na temporada atual da fonte."""
    U = _atualizar_mod()
    b, idi = banco(), dados.idioma_atual()
    if U.liga_sem_pais(b, leagueid):                     # Resto do Mundo, Libertadores…: cada time casado sozinho
        temporada = None if fonte == "transfermarkt" else int((API.cfg.get("temporadas") or [None, datetime.date.today().year])[1])
        r = U.preparar_individual(fonte, TM if fonte == "transfermarkt" else API, b, idi, leagueid, temporada,
                                  progresso=lambda m, f=None, t=None: TAREFA.update(msg=m))
        with LOCK:
            P["atualizacoes"] = [a for a in P["atualizacoes"] if a["id"] != r["id"]] + [r]
        return r
    if fonte == "transfermarkt":
        sg = U.sugerir_ligas_tm(TM, b, idi, leagueid, ligas_db())
        if not sg["ligas"]:
            raise ValueError(f"nenhuma liga de {sg['pais']} na Transfermarkt")
        lg = sg["ligas"][0]
        temps = CT.temporadas(TM, lg["id"])
        temporada = temps[0]["id"] if temps else None
        r = U.preparar_tm(TM, b, idi, leagueid, lg["id"], temporada, lg["nome"], sg["pais"])
        r["temporada_nome"] = temps[0]["nome"] if temps else "atual"
    else:
        sg = U.sugerir_ligas(API, b, idi, leagueid, ligas_db())
        if not sg["ligas"]:
            raise ValueError(f"nenhuma liga de {sg['pais']} na API-Football")
        lg = sg["ligas"][0]
        r = U.preparar(API, b, idi, leagueid, int(lg["id"]), int(_ultima_liberada(lg)))
    with LOCK:
        P["atualizacoes"] = [a for a in P["atualizacoes"] if a["id"] != r["id"]] + [r]
    return r


def api_atualizar_preparar_varias(d):
    """Várias ligas do banco de uma vez: cada uma casada com a liga sugerida da fonte (tarefa com progresso)."""
    ids = [str(x) for x in d.get("leagueids") or []]
    if not ids:
        raise base.ErroUsuario("Marque as ligas do banco.")
    fonte = d.get("fonte") or "apifootball"
    with LOCK:
        if TAREFA["ativa"]:
            raise base.ErroUsuario("Já há uma tarefa em andamento.")
        TAREFA.update(ativa=True, tipo="preparar", msg="Casando os times…", feito=0, total=len(ids), erro=None, fim=0, resultado=None)

    def rodar():
        feitos, erros = [], []
        try:
            nomes = {l["leagueid"]: l["nome"] for l in ligas_db()}
            for n, lid in enumerate(ids):
                TAREFA.update(feito=n, msg=f"{nomes.get(lid, lid)}: casando os times…")
                try:
                    feitos.append(_preparar_uma(fonte, lid)["id"])
                except (A.ErroApi, T.ErroTm, ValueError) as ex:
                    erros.append(f"{nomes.get(lid, lid)}: {ex}")
                gravar_projeto()
            TAREFA.update(msg=f"{len(feitos)} liga(s) casada(s)." + (f" {len(erros)} com problema." if erros else ""),
                          resultado={"ids": feitos, "erros": erros}, erro="; ".join(erros) or None)
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            TAREFA.update(erro=f"{type(ex).__name__}: {ex}", msg="Parou.")
        finally:
            TAREFA.update(ativa=False, fim=time.time(), feito=len(ids))
    threading.Thread(target=rodar, daemon=True).start()
    return estado_payload()


def api_atualizar_conferir_varias(d):
    """Confere várias atualizações (as mesmas opções para todas), uma depois da outra."""
    U = _atualizar_mod()
    with LOCK:
        if TAREFA["ativa"]:
            raise base.ErroUsuario("Já há uma tarefa em andamento.")
        quais = [a for a in P["atualizacoes"] if a["id"] in set(d.get("ids") or [])]
        if not quais:
            raise base.ErroUsuario("Marque as conferências.")
        TAREFA.update(ativa=True, tipo="atualizar", msg="Conferindo…", feito=0, total=len(quais), erro=None, fim=0, resultado=None)
    opcoes = {k: d.get(k) for k in ("elencos", "participantes", "emprestimos", "numeros", "saidas", "notas", "criar", "destino_saidas", "tatica", "tecnicos", "delta_max", "delta_min")}

    def rodar():
        erros = []
        try:
            for n, a in enumerate(quais):
                pre = f"{a['liga_nome']} ({n + 1}/{len(quais)})"
                prog = lambda m, f=None, t=None, pre=pre: TAREFA.update(msg=f"{pre}: {m}")  # noqa: E731
                TAREFA.update(feito=n, msg=f"{pre}…")
                try:
                    op = dict(opcoes, times=None)
                    if a.get("fonte") == "transfermarkt":
                        U.conferir_tm(TM, banco(), dados.idioma_atual(), a, op, progresso=prog)
                    else:
                        U.conferir(API, banco(), dados.idioma_atual(), a, op, progresso=prog)
                except (A.ErroApi, T.ErroTm) as ex:
                    erros.append(f"{a['liga_nome']}: {ex}")
                gravar_projeto()
            total = sum(len(a.get("mudancas") or []) for a in quais)
            TAREFA.update(msg=f"{len(quais)} liga(s) conferida(s): {total} mudança(s).", resultado={"ids": [a["id"] for a in quais]},
                          erro="; ".join(erros) or None)
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            TAREFA.update(erro=f"{type(ex).__name__}: {ex}", msg="A conferência falhou.")
        finally:
            TAREFA.update(ativa=False, fim=time.time(), feito=len(quais))
    threading.Thread(target=rodar, daemon=True).start()
    return estado_payload()


# ------------------------------------------------------------------ atualizar as seleções (ligas 78 e 2136)
def api_atualizar_selecoes(q):
    """Seleções de uma liga de seleções do banco + o par já achado na fonte e se já estão no projeto."""
    U = _atualizar_mod()
    fonte = q.get("fonte") or "apifootball"
    sel = U.selecoes_do_banco(banco(), dados.idioma_atual(), q["leagueid"])
    pares = (P.get("selecoes_pares") or {}).get(fonte, {})
    no_proj = {str(it.get("teamid_banco")): it["id"] for it in P["itens"] if it.get("selecao") and it.get("teamid_banco")}
    for s in sel:
        s["par"] = pares.get(s["teamid"])
        s["item"] = no_proj.get(s["teamid"])
    return {"selecoes": sel, "fonte": fonte, "feminina": q["leagueid"] == "2136"}


def api_atualizar_casar_selecoes(d):
    """Acha cada seleção marcada na fonte (Transfermarkt: busca de clubes; API-Football: teams?search, 1 chamada cada)."""
    U = _atualizar_mod()
    fonte = d.get("fonte") or "apifootball"
    fem = str(d.get("leagueid")) == "2136"
    if fonte == "transfermarkt" and fem:
        raise base.ErroUsuario("A Transfermarkt não tem futebol feminino: atualize as seleções femininas pela API-Football.")
    sel = {s["teamid"]: s for s in U.selecoes_do_banco(banco(), dados.idioma_atual(), d["leagueid"])}
    quais = [sel[str(t)] for t in d.get("teamids") or [] if str(t) in sel]
    if not quais:
        raise base.ErroUsuario("Marque as seleções.")
    with LOCK:
        if TAREFA["ativa"]:
            raise base.ErroUsuario("Já há uma tarefa em andamento.")
        TAREFA.update(ativa=True, tipo="selecoes", msg="Procurando as seleções…", feito=0, total=len(quais), erro=None, fim=0, resultado=None)

    def rodar():
        achadas, erros = 0, []
        try:
            pares = P.setdefault("selecoes_pares", {}).setdefault(fonte, {})
            for n, s in enumerate(quais):
                TAREFA.update(feito=n, msg=f"{s['nome']}…")
                try:
                    r = U.casar_selecao_tm(TM, s["nacao_en"]) if fonte == "transfermarkt" else \
                        U.casar_selecao_api(API, s["nacao_en"], s.get("iso"), fem)
                except (A.ErroApi, T.ErroTm) as ex:
                    erros.append(f"{s['nome']}: {ex}")
                    if "limite" in str(ex).lower():
                        break
                    continue
                if r:
                    pares[s["teamid"]] = r
                    achadas += 1
                else:
                    pares.pop(s["teamid"], None)
            gravar_projeto()
            TAREFA.update(msg=f"{achadas} de {len(quais)} seleção(ões) achada(s).", erro="; ".join(erros) or None,
                          resultado={"leagueid": d["leagueid"]})
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            TAREFA.update(erro=f"{type(ex).__name__}: {ex}", msg="Parou.")
        finally:
            TAREFA.update(ativa=False, fim=time.time(), feito=len(quais))
    threading.Thread(target=rodar, daemon=True).start()
    return estado_payload()


def api_atualizar_selecoes_projeto(d):
    """As seleções marcadas (já casadas) entram no projeto como seleções que já existem: o Gerar troca a convocação,
    a escalação, os cobradores e o técnico delas."""
    U = _atualizar_mod()
    fonte = d.get("fonte") or "apifootball"
    fem = str(d.get("leagueid")) == "2136"
    sel = {s["teamid"]: s for s in U.selecoes_do_banco(banco(), dados.idioma_atual(), d["leagueid"])}
    pares = (P.get("selecoes_pares") or {}).get(fonte, {})
    temporada = None if fonte == "transfermarkt" else int((API.cfg.get("temporadas") or [None, datetime.date.today().year])[1])
    novos, repetidos, sem_par = [], [], []
    with LOCK:
        existentes = {it["id"] for it in P["itens"]}
        for t in d.get("teamids") or []:
            s, par = sel.get(str(t)), pares.get(str(t))
            if not s:
                continue
            if not par:
                sem_par.append(s["nome"])
                continue
            liga = {"id": None, "nome": "Seleções" + (" femininas" if fem else ""), "fonte": fonte, "pais": s["nacao_en"]}
            nt = _novo_time(dict(par, pais=s["nacao_en"]), liga, temporada, None, feminino=fem)
            nt["teamid_banco"] = s["teamid"]
            if nt["id"] in existentes:
                repetidos.append(s["nome"])
                continue
            P["itens"].append(nt)
            existentes.add(nt["id"])
            novos.append(nt["id"])
        if novos:
            P["sel"] = novos[0]
    gravar_projeto()
    return {**estado_payload(), "adicionados": len(novos), "repetidos": repetidos, "sem_par": sem_par}


def api_atualizar_sugestao(q):
    """Ligas da API do país da liga do banco (a de mesma divisão primeiro) — 1 chamada por país, depois cache."""
    U = _atualizar_mod()
    if q.get("fonte") == "transfermarkt":
        return _tmc(U.sugerir_ligas_tm, TM, banco(), dados.idioma_atual(), q["leagueid"], ligas_db())
    r = _api(U.sugerir_ligas, API, banco(), dados.idioma_atual(), q["leagueid"], ligas_db())
    return r


def api_atualizar_preparar(d):
    """Casa os times de uma liga do banco com os da API (liga + temporada escolhidas) — custa 1 chamada (lista de times)."""
    U = _atualizar_mod()
    if d.get("fonte") == "transfermarkt":
        r = _tmc(U.preparar_tm, TM, banco(), dados.idioma_atual(), d["leagueid"], str(d["liga_api"]), d.get("temporada") or None,
                 d.get("liga_nome"), d.get("pais"))
        r["temporada_nome"] = d.get("temporada_nome") or r.get("temporada")
    else:
        r = _api(U.preparar, API, banco(), dados.idioma_atual(), d["leagueid"], int(d["liga_api"]), int(d["temporada"]))
    with LOCK:
        P["atualizacoes"] = [a for a in P["atualizacoes"] if a["id"] != r["id"]] + [r]
    gravar_projeto()
    return {**estado_payload(), "atualizacao": r}


def api_atualizacao(q):
    with LOCK:
        a = next((x for x in P["atualizacoes"] if x["id"] == q["id"]), None)
    if not a:
        raise base.ErroUsuario("Atualização não encontrada.")
    return {"atualizacao": a}


def api_atualizar_casar(d):
    """Troca à mão o time do banco de um time da API (ou tira o par)."""
    U = _atualizar_mod()
    with LOCK:
        a = next((x for x in P["atualizacoes"] if x["id"] == d["id"]), None)
        if not a:
            raise base.ErroUsuario("Atualização não encontrada.")
        U.casar_manual(a, d["api_id"], d.get("teamid"), banco(), dados.idioma_atual())
    gravar_projeto()
    return {"atualizacao": a}


def api_atualizar_conferir(d):
    """Busca os elencos (1 chamada por time; transferências: +1) e monta a lista de mudanças."""
    U = _atualizar_mod()
    with LOCK:
        if TAREFA["ativa"]:
            raise base.ErroUsuario("Já há uma tarefa em andamento.")
        a = next((x for x in P["atualizacoes"] if x["id"] == d["id"]), None)
        if not a:
            raise base.ErroUsuario("Atualização não encontrada.")
        TAREFA.update(ativa=True, tipo="atualizar", msg="Conferindo…", feito=0, total=0, erro=None, fim=0, resultado=None)
    opcoes = {k: d.get(k) for k in ("elencos", "participantes", "emprestimos", "numeros", "saidas", "notas", "criar", "destino_saidas", "tatica", "tecnicos", "delta_max", "delta_min", "times")}

    def rodar():
        try:
            prog = lambda m, f=None, t=None: TAREFA.update(msg=m, feito=f or 0, total=t or 0)  # noqa: E731
            if a.get("fonte") == "transfermarkt":
                U.conferir_tm(TM, banco(), dados.idioma_atual(), a, opcoes, progresso=prog)
            else:
                U.conferir(API, banco(), dados.idioma_atual(), a, opcoes, progresso=prog)
            gravar_projeto()
            TAREFA.update(msg=f"{len(a.get('mudancas') or [])} mudança(s) encontrada(s).", resultado={"id": a["id"]})
        except (A.ErroApi, T.ErroTm) as ex:
            TAREFA.update(erro=str(ex), msg="A conferência parou.")
            gravar_projeto()
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            TAREFA.update(erro=f"{type(ex).__name__}: {ex}", msg="A conferência falhou.")
        finally:
            TAREFA.update(ativa=False, fim=time.time())
    threading.Thread(target=rodar, daemon=True).start()
    return estado_payload()


def api_atualizar_casar_individual(d):
    """Liga sem país: casa à mão um time do banco que a busca automática não achou com um time achado na fonte."""
    U = _atualizar_mod()
    with LOCK:
        a = next((x for x in P["atualizacoes"] if x["id"] == d["id"]), None)
        if not a:
            raise base.ErroUsuario("Atualização não encontrada.")
        t = d["api"]
        U.casar_manual(a, t["id"], d["teamid"], banco(), dados.idioma_atual())
        par = next((p for p in a["pares"] if str(p["api_id"]) == str(t["id"])), None)
        if par:
            par.update(api_nome=t.get("nome") or par["api_nome"], api_logo=t.get("logo"))
        a["nao_casados"] = [x for x in a.get("nao_casados") or [] if x["teamid"] != str(d["teamid"])]
    gravar_projeto()
    return {"atualizacao": a}


def api_atualizar_marcar(d):
    with LOCK:
        a = next((x for x in P["atualizacoes"] if x["id"] == d["id"]), None)
        if not a:
            raise base.ErroUsuario("Atualização não encontrada.")
        quais = d.get("indices")
        for i, m in enumerate(a.get("mudancas") or []):
            if quais is None or i in quais or (d.get("tipo") and m["tipo"] == d["tipo"]):
                if "aplicar" in d:
                    m["aplicar"] = bool(d.get("aplicar"))
                if m["tipo"] == "tatica" and d.get("tatica"):   # formação, linha e saída de bola escolhidas à mão
                    for k in ("formacao", "profundidade", "saida"):
                        if d["tatica"].get(k) not in (None, ""):
                            m[k] = d["tatica"][k] if k == "formacao" else int(d["tatica"][k])
        a["avisos"] = _atualizar_mod()._avisos_elenco(banco(), dados.idioma_atual(), a.get("mudancas") or [])
    gravar_projeto()
    return {"atualizacao": a, **estado_payload()}


def api_atualizar_remover(d):
    with LOCK:
        P["atualizacoes"] = [a for a in P["atualizacoes"] if a["id"] != d["id"]]
    gravar_projeto()
    return estado_payload()


def api_atualizar_criar(d):
    """Times da API que não existem no banco -> itens do projeto (entram na liga do banco que foi conferida)."""
    with LOCK:
        a = next((x for x in P["atualizacoes"] if x["id"] == d["id"]), None)
        if not a:
            raise base.ErroUsuario("Atualização não encontrada.")
        novos = 0
        for t in a.get("sem_par") or []:
            if d.get("ids") and t["id"] not in d["ids"]:
                continue
            nt = _novo_time(t, {**a["liga_api_info"], "temporada_nome": a.get("temporada_nome")}, a["temporada"], None)
            if any(x["id"] == nt["id"] for x in P["itens"]):
                continue
            nt["destino"] = a["leagueid"]
            P["itens"].append(nt)
            novos += 1
    gravar_projeto()
    return {**estado_payload(), "adicionados": novos}


# ------------------------------------------------------------------ opções, diálogos, calibração
def api_opcoes(d):
    op = PREFS.ler()
    for k in ("saida", "espalhamento", "escalacoes", "modo", "perfis_faltantes", "baixar_imagens", "classificacao",
              "jogador_inicio", "time_inicio", "liga_inicio", "visual", "aparencia_fotos", "minifaces_auto", "fonte", "tm_estatisticas",
              "completar_tm"):
        if k in d:
            op[k] = d[k]
    PREFS.gravar(op)
    return estado_payload()


def api_dialogo(d):
    op = PREFS.ler()
    r = base.dialogo("pasta", "Pasta onde gravar o banco novo", op.get("saida") or base.raiz_trabalho())
    if r:
        PREFS.atualizar(saida=r)
    return {"caminho": r, **estado_payload()}


def api_abrir(d):
    alvo = d.get("caminho") or PREFS.ler().get("saida")
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo or '(sem pasta de saída)'}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def api_calibrar(_):
    exige_motor()
    import calibracao
    r = calibracao.do_cache(API, banco())
    r_tm = calibracao.tm_do_cache(TM, banco())
    if not r and not r_tm:
        raise base.ErroUsuario("Poucos jogadores do cache casados com o banco (precisa de uns 40). Colete times que já "
                               "existem no banco (ex.: uma liga do banco) e tente de novo.")
    return {"calibracao": r or N.carregar_coef(), "calibracao_tm": r_tm, **estado_payload()}


def img(h, q):
    """Imagem da API (logos, fotos) servida pela ferramenta: cache em disco e DNS de reserva (apifutebol.baixar)."""
    import hashlib
    import urllib.parse
    u = q.get("u") or ""
    if urllib.parse.urlsplit(u).hostname not in ("media.api-sports.io", "img.a.transfermarkt.technology", "tmssl.akamaized.net"):
        h.enviar(404, b"", "text/plain")
        return
    pasta = os.path.join(API.cache, "img")
    arq = os.path.join(pasta, hashlib.sha1(u.encode()).hexdigest()[:20] + os.path.splitext(urllib.parse.urlsplit(u).path)[1])
    try:
        if not os.path.isfile(arq):
            dados_img = A.baixar(u, timeout=20)
            os.makedirs(pasta, exist_ok=True)
            with open(arq, "wb") as f:
                f.write(dados_img)
        with open(arq, "rb") as f:
            corpo = f.read()
        tipo = "image/svg+xml" if arq.endswith(".svg") else "image/jpeg" if corpo[:3] == b"\xff\xd8\xff" else "image/png"
        h.enviar(200, corpo, tipo)
    except Exception:  # noqa: BLE001
        h.enviar(404, b"", "text/plain")


def _protegido(fn):
    def f(d):
        try:
            return fn(d)
        except dados.ErroDados as ex:
            raise base.ErroUsuario(str(ex))
        except (A.ErroApi, T.ErroTm) as ex:
            raise base.ErroUsuario(str(ex))
        except ValueError as ex:
            raise base.ErroUsuario(str(ex))
    return f


ROTAS_GET = {k: _protegido(v) for k, v in {
    "inicio": api_inicio, "estado": api_estado, "paises": api_paises, "ligas": api_ligas, "times": api_times,
    "status_api": api_status_api, "previa": api_previa, "versao": lambda _: {"versao": VERSAO},
    "jogadores_db": api_jogadores_db, "atualizar_ligas": api_atualizar_ligas, "atualizacao": api_atualizacao,
    "atualizar_sugestao": api_atualizar_sugestao, "times_db": api_times_db, "buscar_ligas": api_buscar_ligas,
    "temporadas": api_temporadas, "selecao_tm": api_selecao_tm, "atualizar_selecoes": api_atualizar_selecoes,
    "buscar_times": api_buscar_times}.items()}
ROTAS_POST = {k: _protegido(v) for k, v in {
    "chave": api_chave, "adicionar_liga": api_adicionar_liga, "adicionar_time": api_adicionar_time,
    "adicionar_times": api_adicionar_times, "remover": api_remover, "limpar": api_limpar, "selecionar": api_selecionar,
    "item": api_item, "ajustar": api_ajustar, "selecao": api_selecao, "coletar": api_coletar, "gerar": api_gerar,
    "opcoes": api_opcoes, "dialogo": api_dialogo, "abrir": api_abrir, "calibrar": api_calibrar,
    "analisar_fotos": api_analisar_fotos, "minifaces": api_minifaces, "atualizar_preparar": api_atualizar_preparar,
    "atualizar_casar": api_atualizar_casar, "atualizar_conferir": api_atualizar_conferir, "atualizar_marcar": api_atualizar_marcar,
    "atualizar_remover": api_atualizar_remover, "atualizar_criar": api_atualizar_criar, "tm_config": api_tm_config,
    "tm_testar": api_tm_testar, "atualizar_preparar_varias": api_atualizar_preparar_varias,
    "atualizar_conferir_varias": api_atualizar_conferir_varias, "atualizar_casar_selecoes": api_atualizar_casar_selecoes,
    "atualizar_selecoes_projeto": api_atualizar_selecoes_projeto, "atualizar_casar_individual": api_atualizar_casar_individual}.items()}
_G, _P = base.rotas_componentes("criador", ao_concluir=carregar_motor)
ROTAS_GET.update(_G)
ROTAS_POST.update(_P)
# servidor local da Transfermarkt (grupo "transfermarkt" de Componentes)
_G2, _P2 = base.rotas_componentes("transfermarkt", ao_concluir=lambda: tm_status(forcar=True))
ROTAS_GET["tm_componentes"] = _G2["componentes"]
ROTAS_POST["tm_componentes_instalar"] = _P2["componentes_instalar"]


def main():
    ap = argparse.ArgumentParser(description="Criador de Ligas e Times (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8775)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    a = ap.parse_args()
    carregar_motor()
    carregar_projeto()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, especiais={"/img": img},
                                 nome="CriadorLigasTimes/" + VERSAO)
    base.servir(handler, a.porta, "Criador de Ligas e Times", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
