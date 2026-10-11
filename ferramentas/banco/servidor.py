"""Editor de Banco (BRFP Super Tool) — edita o banco importado em Dados do jogo (FIFA 16 … FC 27).

    python servidor.py [--porta 8776] [--sem-janela]

Times, jogadores, ligas, árbitros e técnicos em formulários; transferências, empréstimos, liberar, números, escalação,
formação, capitão e cobradores; qualquer tabela numa grade; verificação de erros com correções. As mudanças ficam numa
camada salva sozinha (com desfazer) e o Gravar escreve um banco novo — o original nunca é alterado.
"""
import argparse
import os
import re
import sys
import threading
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import dados  # noqa: E402
import edicao as E  # noqa: E402

VERSAO = "1.0"
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {"saida": ""})
CACHE = os.path.join(AQUI, "cache")
LOCK = threading.RLock()
EST = {"ed": None, "sig": None, "problemas": None, "versao_prob": None, "tarefa": {"ativa": False, "msg": "", "erro": None, "resultado": None}}


def ed():
    """A edição do banco importado agora (troca sozinha se o banco do Super Tool mudar)."""
    b = dados.banco_atual()
    if not b:
        raise base.ErroUsuario("Importe o banco do jogo em Dados do jogo (Super Tool) para editar.")
    with LOCK:
        if EST["sig"] != b.sig:
            EST.update(ed=E.Edicao(b, CACHE), sig=b.sig, problemas=None)
        return EST["ed"]


def _erro(fn):
    def f(d):
        try:
            return fn(d)
        except (E.ErroEdicao, dados.ErroDados, ValueError) as ex:
            raise base.ErroUsuario(str(ex))
    return f


def estado():
    b = dados.banco_atual()
    if not b:
        return {"banco": None, "edicao": None, "tarefa": EST["tarefa"]}
    e = ed()
    return {"banco": b.resumo(), "edicao": {"resumo": e.resumo(), "historico": [o["rotulo"] for o in e.historico][-30:],
            "idioma": len(e.idioma), "mudancas": sum(sum(v.values()) for v in e.resumo().values()) + len(e.idioma)},
            "tarefa": EST["tarefa"], "saida": PREFS.ler().get("saida") or ""}


# ------------------------------------------------------------------ leitura
def api_inicio(_):
    st = estado()
    out = {"versao": VERSAO, **st, "nacoes": [], "posicoes": E.POS}
    if st["banco"]:
        e = ed()
        out["nacoes"] = sorted(({"id": d["nationid"], "nome": e.nome_nacao(d["nationid"])} for _, d in e.dicts("nations")),
                               key=lambda x: dados.normalizar(x["nome"])) if e.tem("nations") else []
    return out


def api_estado(_):
    return estado()


def api_arvore(_):
    """Países -> ligas -> times (para a lista da esquerda)."""
    e = ed()
    ligas = {}
    for _, d in e.dicts("leagues"):
        ligas[d["leagueid"]] = {"leagueid": d["leagueid"], "nome": e.nome_liga(d["leagueid"], d), "pais": d.get("countryid"),
                                "pais_nome": e.nome_nacao(d.get("countryid")), "nivel": d.get("level"),
                                "feminina": d.get("iswomencompetition") == "1", "times": []}
    n_jog = {}
    for _, d in e.dicts("teamplayerlinks"):
        n_jog[d["teamid"]] = n_jog.get(d["teamid"], 0) + 1
    sem_liga = []
    vistos = set()
    for _, d in e.dicts("leagueteamlinks"):
        if d["teamid"] in vistos:
            continue
        vistos.add(d["teamid"])
        t = {"teamid": d["teamid"], "nome": e.nome_time(d["teamid"]), "jogadores": n_jog.get(d["teamid"], 0)}
        (ligas[d["leagueid"]]["times"] if d["leagueid"] in ligas else sem_liga).append(t)
    for _, d in e.dicts("teams"):
        if d["teamid"] not in vistos:
            sem_liga.append({"teamid": d["teamid"], "nome": e.nome_time(d["teamid"], d), "jogadores": n_jog.get(d["teamid"], 0)})
    for l in ligas.values():
        l["times"].sort(key=lambda t: dados.normalizar(t["nome"]))
    lst = sorted(ligas.values(), key=lambda l: (dados.normalizar(l["pais_nome"]), int(l["nivel"] or 0), dados.normalizar(l["nome"])))
    return {"ligas": lst, "sem_liga": sorted(sem_liga, key=lambda t: dados.normalizar(t["nome"]))}


def _campos(e, t):
    """Esquema da tabela para os formulários: {campo: {tipo, low, high, bits, chave}}."""
    return {c: {k: v for k, v in i.items() if k in ("tipo", "low", "high", "bits", "chave", "t3")} for c, i in e.info(t).items()}


def api_time(q):
    e = ed()
    tid = q["id"]
    r, d = e.um("teams", teamid=tid)
    if not r:
        raise base.ErroUsuario(f"O time {tid} não existe.")
    lid = e.liga_do_time(tid)
    try:
        esc = E.escalacao(e, tid)
    except E.ErroEdicao as ex:
        esc = {"erro": str(ex)}
    tecnico = [(E._rs(rm), m) for rm, m in e.dicts("manager", teamid=tid)] if e.tem("manager") else []
    estadio = None
    if e.tem("teamstadiumlinks"):
        _, sl = e.um("teamstadiumlinks", teamid=tid)
        if sl and e.tem("stadiums"):
            _, st = e.um("stadiums", stadiumid=sl.get("stadiumid"))
            estadio = {"stadiumid": sl.get("stadiumid"), "nome": (st or {}).get("name"), "capacidade": (st or {}).get("capacity")}
    return {"ref": E._rs(r), "dados": d, "campos": _campos(e, "teams"), "nome": e.nome_time(tid, d), "liga": lid,
            "liga_nome": e.nome_liga(lid) if lid else None, "elenco": e.elenco(tid), "escalacao": esc,
            "formacoes": E.formacoes(e) if e.tem("formations") else [],
            "tecnico": [{"ref": rm, "dados": m, "nome": m.get("commonname") or f"{m.get('firstname', '')} {m.get('surname', '')}".strip()} for rm, m in tecnico],
            "campos_tecnico": _campos(e, "manager") if e.tem("manager") else {}, "estadio": estadio,
            "idioma": {k: e.idioma.get(f"{k}{tid}") for k in ("TeamName_Abbr15_", "TeamName_Abbr10_", "TeamName_Abbr3_")}}


def api_jogador(q):
    e = ed()
    pid = q["id"]
    r, d = e.um("players", playerid=pid)
    if not r:
        raise base.ErroUsuario(f"O jogador {pid} não existe.")
    _, emp = e.um("playerloans", playerid=pid) if e.tem("playerloans") else (None, None)
    vinc = [{"teamid": l["teamid"], "nome": e.nome_time(l["teamid"]), "numero": l.get("jerseynumber"), "posicao": l.get("position"),
             "liga": e.liga_do_time(l["teamid"])} for _, l in e.vinculos(pid)]
    return {"ref": E._rs(r), "dados": d, "campos": _campos(e, "players"), "nomes": e.nome_jogador(pid, d),
            "tem_nomes": e.tem("editedplayernames"), "vinculos": vinc, "clube": e.clube_de(pid),
            "emprestimo": {"dono": emp["teamidloanedfrom"], "dono_nome": e.nome_time(emp["teamidloanedfrom"]),
                           "fim": E.data_de(emp.get("loandateend"))} if emp else None,
            "nacao_nome": e.nome_nacao(d.get("nationality"))}


def api_buscar_jogadores(q):
    e = ed()
    termo = dados.normalizar(q.get("q") or "")
    if len(termo) < 2 and not termo.isdigit():
        return {"jogadores": []}
    lim = int(q.get("limite") or 60)
    out = []
    for r, d in e.dicts("players"):
        pid = d["playerid"]
        n = e.nome_jogador(pid, d)
        if termo.isdigit() and termo == pid or termo in dados.normalizar(f"{n['nome']} {n['primeiro']} {n['sobrenome']} {n['camisa']}"):
            clube = e.clube_de(pid)
            out.append({"playerid": pid, "nome": n["nome"], "overall": int(d.get("overallrating") or 0),
                        "pos": E.POS.get(int(d.get("preferredposition1") or 0), "?"), "clube": clube,
                        "clube_nome": e.nome_time(clube) if clube else "sem clube", "nascimento": E.data_de(d.get("birthdate"))})
            if len(out) >= lim * 3:
                break
    out.sort(key=lambda j: (not dados.normalizar(j["nome"]).startswith(termo), -j["overall"]))
    return {"jogadores": out[:lim]}


def api_buscar_times(q):
    e = ed()
    termo = dados.normalizar(q.get("q") or "")
    out = []
    for _, d in e.dicts("teams"):
        n = e.nome_time(d["teamid"], d)
        if not termo or termo in dados.normalizar(n) or termo == d["teamid"]:
            lid = e.liga_do_time(d["teamid"])
            out.append({"teamid": d["teamid"], "nome": n, "liga": e.nome_liga(lid) if lid else "sem liga"})
    out.sort(key=lambda t: (not dados.normalizar(t["nome"]).startswith(termo), dados.normalizar(t["nome"])))
    return {"times": out[:80]}


def api_liga(q):
    e = ed()
    lid = q["id"]
    r, d = e.um("leagues", leagueid=lid)
    if not r:
        raise base.ErroUsuario(f"A liga {lid} não existe.")
    times = [{"teamid": l["teamid"], "nome": e.nome_time(l["teamid"]), "posicao": l.get("currenttableposition")}
             for _, l in e.dicts("leagueteamlinks", leagueid=lid)]
    return {"ref": E._rs(r), "dados": d, "campos": _campos(e, "leagues"), "nome": e.nome_liga(lid, d),
            "times": sorted(times, key=lambda t: dados.normalizar(t["nome"])), "pais_nome": e.nome_nacao(d.get("countryid")),
            "idioma": {"LeagueName_Abbr15_": e.idioma.get(f"LeagueName_Abbr15_{lid}")}}


def api_pessoas(q):
    """Árbitros (referee) ou técnicos (manager): lista com busca."""
    e = ed()
    t = q.get("tabela")
    if t not in ("referee", "manager") or not e.tem(t):
        raise base.ErroUsuario("Tabela de pessoas inválida.")
    termo = dados.normalizar(q.get("q") or "")
    out = []
    for r, d in e.dicts(t):
        nome = d.get("commonname") or f"{d.get('firstname', '')} {d.get('surname', '')}".strip() or f"#{E._rs(r)}"
        if termo and termo not in dados.normalizar(nome):
            continue
        extra = e.nome_time(d["teamid"]) if t == "manager" and d.get("teamid") not in (None, "", "-1", "0") else \
            (e.nome_liga(d["leagueid"]) if t == "referee" and d.get("leagueid") not in (None, "", "-1", "0") else "")
        out.append({"ref": E._rs(r), "nome": nome, "extra": extra, "nacao": e.nome_nacao(d.get("nationality"))})
    out.sort(key=lambda x: dados.normalizar(x["nome"]))
    return {"pessoas": out[:400], "total": len(out)}


def api_pessoa(q):
    e = ed()
    t, ref = q["tabela"], q["ref"]
    d = e.linha(t, ref)
    return {"ref": ref, "tabela": t, "dados": d, "campos": _campos(e, t)}


def api_tabelas(_):
    e = ed()
    res = e.resumo()
    return {"tabelas": [{"nome": n, "linhas": len(e.refs(n)), "campos": nc, "mexida": n in res} for n, _, nc in e.b.nomes()]}


def api_tabela(q):
    """Linhas de uma tabela (página de 100), com busca num campo ou em todos."""
    e = ed()
    t = q["nome"]
    if not e.tem(t):
        raise base.ErroUsuario(f"A tabela {t} não existe.")
    campos = e.campos(t)
    termo = (q.get("q") or "").strip().lower()
    campo = q.get("campo") or ""
    pag = max(0, int(q.get("pagina") or 0))
    res = e.resumo().get(t) or {}
    alt = e.alt.get(t, {})
    linhas = []
    for r in e.refs(t):
        d = e.linha(t, r)
        if termo:
            alvo = [str(d.get(campo, ""))] if campo in campos else [str(v) for v in d.values()]
            if not any(termo in v.lower() for v in alvo):
                continue
        linhas.append((r, d))
    total = len(linhas)
    pagina = linhas[pag * 100:(pag + 1) * 100]
    return {"nome": t, "campos": campos, "info": _campos(e, t), "total": total, "pagina": pag,
            "linhas": [{"ref": E._rs(r), "valores": [d.get(c, "") for c in campos],
                        "mudados": sorted((alt.get(r[1]) or {}).keys()) if r[0] == "o" else ["*"]} for r, d in pagina],
            "resumo": res}


def api_verificar(q):
    e = ed()
    versao = (len(e.historico), sum(sum(v.values()) for v in e.resumo().values()))
    if q.get("forcar") or EST["problemas"] is None or EST["versao_prob"] != versao:
        EST["problemas"] = E.verificar(e)
        EST["versao_prob"] = versao
    return {"problemas": EST["problemas"]}


# ------------------------------------------------------------------ escrita
def _valida(e, t, valores):
    """Confere e normaliza os valores pelo meta (inteiro na faixa, texto no tamanho)."""
    info = e.info(t)
    out = {}
    for c, v in valores.items():
        i = info.get(c)
        if i is None:
            continue
        v = "" if v is None else str(v).strip()
        tipo = (i.get("tipo") or "").lower()
        if i.get("t3") == 3 or "int" in tipo:
            if not re.fullmatch(r"-?\d+", v or ""):
                raise ValueError(f"{c}: precisa ser um número inteiro.")
            n = int(v)
            if i.get("high") and not i.get("low", 0) <= n <= i["high"]:
                raise ValueError(f"{c}: {n} está fora da faixa {i.get('low', 0)}–{i['high']}.")
            out[c] = str(n)
        elif i.get("t3") == 4 or "real" in tipo or "float" in tipo:
            try:
                out[c] = repr(float(v.replace(",", "."))) if v else "0"
            except ValueError:
                raise ValueError(f"{c}: precisa ser um número.")
        else:
            lim = (i.get("bits") or 0) // 8
            if i.get("t3") in (13, 14):
                lim = 255 if i.get("t3") == 13 else 65535
            if lim and len(v.encode("utf-8")) > lim:
                raise ValueError(f"{c}: texto com mais de {lim} bytes.")
            out[c] = v
    return out


def api_linha_salvar(d):
    e = ed()
    t = d["tabela"]
    v = _valida(e, t, d.get("valores") or {})
    if not v:
        return estado()
    with e.operacao(d.get("rotulo") or f"Editar {t}"):
        e.alterar(t, d["ref"], v)
    return estado()


def api_linha_nova(d):
    e = ed()
    t = d["tabela"]
    with e.operacao(f"Linha nova em {t}"):
        modelo = e.linha(t, d["modelo"]) if d.get("modelo") else None
        valores = {}
        for c, i in e.info(t).items():                      # chave única (ex.: playerid): o próximo livre
            if i.get("chave") and c != "artificialkey" and (i.get("t3") == 3 or "int" in (i.get("tipo") or "").lower()):
                valores[c] = e.proximo_id(t, c)
        if "artificialkey" in e.campos(t):
            valores["artificialkey"] = e.proximo_id(t, "artificialkey")
        ref = e.inserir(t, valores, modelo)
    return {**estado(), "ref": E._rs(ref)}


def api_linha_remover(d):
    e = ed()
    with e.operacao(f"Tirar linha de {d['tabela']}"):
        e.remover(d["tabela"], d["ref"])
    return estado()


def _op(fn):
    """Rota de operação: roda e devolve o estado."""
    def f(d):
        fn(ed(), d)
        return estado()
    return _erro(f)


OPS = {
    "transferir": lambda e, d: E.transferir(e, d["pid"], d["para"], d.get("numero"), d.get("emprestimo")),
    "emprestar": lambda e, d: E.emprestar(e, d["pid"], d["para"], d["fim"], d.get("dono")),
    "encerrar_emprestimo": lambda e, d: E.encerrar_emprestimo(e, d["pid"]),
    "liberar": lambda e, d: E.liberar(e, d["pid"]),
    "trocar_numero": lambda e, d: E.trocar_numero(e, d["teamid"], d["pid"], d["numero"]),
    "mover_liga": lambda e, d: E.mover_liga(e, d["teamid"], d["liga"]),
    "reescalar": lambda e, d: E.reescalar(e, d["teamid"]),
    "definir_escalacao": lambda e, d: E.definir_escalacao(e, d["teamid"], d["titulares"], d.get("banco"), d.get("cobradores")),
    "trocar_formacao": lambda e, d: E.trocar_formacao(e, d["teamid"], d["ref"]),
    "definir_tatica": lambda e, d: E.definir_tatica(e, d["teamid"], d.get("valores") or {}),
    "excluir_jogador": lambda e, d: E.excluir_jogador(e, d["pid"]),
    "editar_nomes": lambda e, d: E.editar_nomes(e, d["pid"], d.get("primeiro"), d.get("sobrenome"), d.get("comum"), d.get("camisa")),
    "renomear_time": lambda e, d: E.renomear_time(e, d["teamid"], d["nome"], d.get("abrev15"), d.get("abrev10"), d.get("sigla")),
    "renomear_liga": lambda e, d: E.renomear_liga(e, d["leagueid"], d["nome"], d.get("abrev15")),
    "corrigir": lambda e, d: E.corrigir(e, d["acao"], d.get("args") or {}),
}


def api_criar_jogador(d):
    e = ed()
    pid = E.criar_jogador(e, d["teamid"], d.get("nome") or "Jogador Novo")
    return {**estado(), "pid": str(pid)}


def api_corrigir_tipo(d):
    """Aplica a correção de todos os problemas de um tipo (cada uma vira uma operação no histórico)."""
    e = ed()
    probs = [p for p in E.verificar(e) if p["tipo"] == d["tipo"] and p.get("correcao")]
    feitos = 0
    vistos = set()
    for p in probs:
        c = p["correcao"]
        chave = (c["acao"], repr(sorted((c.get("args") or {}).items())))
        if chave in vistos:
            continue
        vistos.add(chave)
        try:
            E.corrigir(e, c["acao"], c.get("args") or {})
            feitos += 1
        except E.ErroEdicao:
            pass
    EST["problemas"] = None
    return {**estado(), "feitos": feitos}


def api_desfazer(_):
    rot = ed().desfazer()
    return {**estado(), "desfeito": rot}


def api_descartar(_):
    ed().descartar_tudo()
    EST["problemas"] = None
    return estado()


def api_dialogo(d):
    c = base.dialogo("pasta", d.get("titulo") or "Pasta onde gravar o banco novo", PREFS.ler().get("saida") or base.raiz_trabalho())
    if c:
        PREFS.atualizar(saida=c)
    return {"caminho": c, **estado()}


def api_gravar(d):
    e = ed()
    pasta_base = d.get("pasta") or PREFS.ler().get("saida")
    if not pasta_base:
        raise base.ErroUsuario("Escolha a pasta onde gravar o banco novo.")
    if not e.resumo() and not e.idioma:
        raise base.ErroUsuario("Nada mudou ainda: não há o que gravar.")
    nome = re.sub(r"[^\w\- ]+", "_", d.get("nome") or f"Banco editado {time.strftime('%Y-%m-%d %H%M')}").strip()
    pasta = os.path.join(pasta_base, nome)
    with LOCK:
        if EST["tarefa"]["ativa"]:
            raise base.ErroUsuario("Já está gravando.")
        EST["tarefa"] = {"ativa": True, "msg": "Gravando…", "erro": None, "resultado": None}

    def rodar():
        try:
            r = E.gravar(e, pasta, progresso=lambda m: EST["tarefa"].update(msg=m))
            EST["tarefa"].update(msg="Banco gravado.", resultado=r)
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            EST["tarefa"].update(erro=f"{type(ex).__name__}: {ex}", msg="A gravação falhou.")
        finally:
            EST["tarefa"]["ativa"] = False
    threading.Thread(target=rodar, daemon=True).start()
    return estado()


def api_abrir(d):
    alvo = d.get("caminho")
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Não encontrado: {alvo}")
    base.abrir_no_explorer(alvo)
    return {}


ROTAS_GET = {k: _erro(v) for k, v in {
    "inicio": api_inicio, "estado": api_estado, "arvore": api_arvore, "time": api_time, "jogador": api_jogador,
    "buscar_jogadores": api_buscar_jogadores, "buscar_times": api_buscar_times, "liga": api_liga, "pessoas": api_pessoas,
    "pessoa": api_pessoa, "tabelas": api_tabelas, "tabela": api_tabela, "verificar": api_verificar,
    "versao": lambda _: {"versao": VERSAO}}.items()}
ROTAS_POST = {k: _erro(v) for k, v in {
    "linha_salvar": api_linha_salvar, "linha_nova": api_linha_nova, "linha_remover": api_linha_remover,
    "criar_jogador": api_criar_jogador, "corrigir_tipo": api_corrigir_tipo, "desfazer": api_desfazer,
    "descartar": api_descartar, "dialogo": api_dialogo, "gravar": api_gravar, "abrir": api_abrir}.items()}
ROTAS_POST.update({k: _op(fn) for k, fn in OPS.items()})


def main():
    ap = argparse.ArgumentParser(description="Editor de Banco (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8776)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    a = ap.parse_args()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, nome="EditorBanco/" + VERSAO)
    base.servir(handler, a.porta, "Editor de Banco", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
