"""Criador de Ligas e Times — coleta na Transfermarkt (comum/transfermarkt.py), no mesmo formato da coleta da
API-Football (coleta.py), para o resto da ferramenta funcionar igual.

O que a Transfermarkt dá a mais: posição exata (lateral-esquerdo, ponta-direita…) e as secundárias, pé preferido,
altura, nascimento e nacionalidade de todo o elenco (atual ou de qualquer temporada), valor de mercado (a base das notas:
erro médio 1,7 contra o banco BRFP 27), cores, estádio e técnico do clube. Não tem: nota por jogo, peso e futebol
feminino. Escalações (formação, posições dos titulares e posse de bola) vêm dos jogos de um titular da temporada.

Chamadas por time: elenco + perfil do clube + técnico + 1 perfil por jogador (+1 por jogador com as estatísticas, +1 com
o valor da época numa temporada passada, + 1 + N com N escalações). No servidor local isso leva segundos.
"""
import collections
import datetime
import json
import math
import os
import re

import transfermarkt as T

AQUI = os.path.dirname(os.path.abspath(__file__))
POS_TM = {"goalkeeper": 0, "centre-back": 5, "left-back": 7, "right-back": 3, "defensive midfield": 10, "central midfield": 14,
          "attacking midfield": 18, "left midfield": 16, "right midfield": 12, "left winger": 27, "right winger": 23,
          "second striker": 21, "centre-forward": 25, "sweeper": 5, "left wing-back": 8, "right wing-back": 2,
          # siglas que aparecem nas escalações dos jogos
          "gk": 0, "cb": 5, "lb": 7, "rb": 3, "lwb": 8, "rwb": 2, "dm": 10, "cdm": 10, "cm": 14, "am": 18, "cam": 18,
          "lm": 16, "rm": 12, "lw": 27, "rw": 23, "ss": 21, "cf": 25, "st": 25}
GRUPO_TM = {"goalkeeper": "G", "defender": "D", "midfield": "M", "midfielder": "M", "attack": "F", "forward": "F", "striker": "F"}
LADO = {7: "E", 8: "E", 16: "E", 27: "E", 3: "D", 2: "D", 12: "D", 23: "D"}
_CATALOGO = {}


def pos_tm(texto):
    """Posição do jogo (código) pelo nome da posição na Transfermarkt; None se não reconhecer."""
    t = re.sub(r"\s+", " ", str(texto or "").strip().lower())
    if t in POS_TM:
        return POS_TM[t]
    for k, v in POS_TM.items():
        if len(k) > 3 and k in t:
            return v
    return None


def grupo_tm(texto, pos=None):
    if pos is not None:
        return "G" if pos == 0 else "D" if pos in (2, 3, 5, 7, 8) else "M" if pos in (10, 12, 14, 16, 18) else "F"
    t = str(texto or "").lower()
    return next((v for k, v in GRUPO_TM.items() if k in t), None)


# ------------------------------------------------------------------ catálogo e navegação
def catalogo():
    if not _CATALOGO:
        with open(os.path.join(AQUI, "competicoes_tm.json"), encoding="utf-8") as f:
            _CATALOGO["lista"] = json.load(f)["competicoes"]
    return _CATALOGO["lista"]


def _tipo(nome):
    n = (nome or "").lower()
    return "Cup" if re.search(r"\b(cup|copa|coupe|pokal|taça|taca|coppa|trophy|super|supercopa|play-?offs?|playoff|recopa|shield|beker|kupa)\b", n) else "League"


# fases de outra competição (rebaixamento, finais, troféus do estadual) e categorias de base
_FASE = re.compile(r" - |\b(relegation|rebaixamento|quadrangular|hexagonal|finals?|play-?offs?|qualifying|qualifiers)\b", re.I)
_BASE = re.compile(r"\b(u-?1\d|u-?2[0-3]|sub-?\d\d|youth|j[uú]nior|juniores|reserves?|amateur|amador)\b", re.I)


def secundaria(nome):
    """Fase ou categoria de base: fica no fim da lista e fora das sugestões do Atualizar banco."""
    return bool(_FASE.search(nome or "") or _BASE.search(nome or ""))


def _liga(c, fonte="transfermarkt"):
    pais = c.get("pais") or "Internacional"
    return {"id": c["id"], "nome": c["nome"], "tipo": _tipo(c["nome"]), "logo": T.logo_competicao(c["id"]), "pais": pais,
            "codigo_pais": None, "temporadas": None, "atual": None, "clubes": c.get("clubes"), "valor": c.get("valor"),
            "jogadores": True, "escalacoes": True, "estatisticas": True, "fonte": fonte,
            "selecoes": not c.get("pais") and bool(re.search(r"world cup|euro\b|copa am|nations|qualif|friendl|africa cup|asian cup|gold cup|olymp", c["nome"].lower()))}


def paises(tm):
    r = tm.get("countries")
    out = [{"name": c["name"], "code": c.get("fifaCode"), "id": c["id"], "confederacao": c.get("confederationId")}
           for c in r.get("countries") or [] if not c.get("isHistorical")]
    com = {c.get("pais") for c in catalogo()}
    out = [p for p in out if p["name"] in com]
    return [{"name": "Internacional", "code": None, "id": 0}] + sorted(out, key=lambda p: p["name"])


def ligas(tm, pais):
    alvo = None if pais == "Internacional" else pais
    out = [_liga(c) for c in catalogo() if (c.get("pais") or None) == alvo]
    # ligas antes das copas, fases e categorias de base no fim; dentro delas, pelo valor de mercado (a 1ª divisão primeiro)
    out.sort(key=lambda l: (secundaria(l["nome"]), l["tipo"] != "League", -(l.get("valor") or 0)))
    return out


def buscar_ligas(tm, termo):
    out, vistos = [], set()
    for pag in (1, 2):
        r = tm.get(f"competitions/search/{termo}", page_number=pag)
        for c in r.get("results") or []:
            if c["id"] in vistos:
                continue
            vistos.add(c["id"])
            out.append(_liga({"id": c["id"], "nome": c.get("name") or c["id"], "pais": c.get("country"), "clubes": c.get("clubs"),
                              "valor": c.get("totalMarketValue")}))
        if pag >= int(r.get("lastPageNumber") or 1):
            break
    return out


def temporadas(tm, liga_id):
    r = tm.get(f"competitions/{liga_id}/seasons")
    return [{"id": s["id"], "nome": s.get("name") or s["id"]} for s in r.get("seasons") or []]


def selecao_de(tm, pais):
    """Seleção principal do país (a Transfermarkt trata seleções como clubes): o clube com o nome exato do país."""
    r = tm.get(f"clubs/search/{pais}")
    for c in r.get("results") or []:
        if (c.get("name") or "").strip().lower() == pais.strip().lower():
            return {"id": c["id"], "nome": c["name"], "sigla": None, "pais": pais, "fundacao": None, "logo": T.escudo(c["id"]),
                    "selecao": True, "fonte": "transfermarkt", "estadio": {"id": None, "nome": None, "cidade": None, "capacidade": None}}
    return None


def times(tm, liga_id, temporada, liga_info=None):
    r = tm.get(f"competitions/{liga_id}/clubs", season_id=temporada)
    nomes_paises = {p["name"].lower() for p in paises(tm)}
    selecoes = bool((liga_info or {}).get("selecoes"))
    out = []
    for c in r.get("clubs") or []:
        sel = selecoes or (c.get("name") or "").lower() in nomes_paises
        out.append({"id": c["id"], "nome": c["name"], "sigla": None, "pais": (liga_info or {}).get("pais"), "fundacao": None,
                    "logo": T.escudo(c["id"]), "selecao": sel, "fonte": "transfermarkt",
                    "estadio": {"id": None, "nome": None, "cidade": None, "capacidade": None}})
    return sorted(out, key=lambda t: t["nome"])


# ------------------------------------------------------------------ custo
def estimar(tm, time_id, temporada, modo="temporada", opcoes=None):
    op = opcoes or {}
    sq_params = {"season_id": temporada} if modo != "atual" and temporada else {}
    n = tm.chamadas_para(f"clubs/{time_id}/players", **sq_params) + tm.chamadas_para(f"clubs/{time_id}/profile") + 1
    sq = tm.do_cache(f"clubs/{time_id}/players", **sq_params)
    ids = [p["id"] for p in (sq or {}).get("players") or []]
    nj = len(ids) or 30
    if ids:
        n += sum(tm.chamadas_para(f"players/{i}/profile") for i in ids)
        if op.get("estatisticas"):
            n += sum(tm.chamadas_para(f"players/{i}/stats") for i in ids)
        if _valor_da_epoca(modo, temporada, op):
            n += sum(tm.chamadas_para(f"players/{i}/market_value") for i in ids)
    else:
        n += nj * (1 + (1 if op.get("estatisticas") else 0) + (1 if _valor_da_epoca(modo, temporada, op) else 0))
    if op.get("escalacoes"):
        n += 1 + int(op["escalacoes"])
    return n


def _valor_da_epoca(modo, temporada, op):
    return modo != "atual" and temporada and T.temporada_encerrada(temporada) and op.get("valor_da_epoca", True)


# ------------------------------------------------------------------ coleta de um time
def _fim_temporada(nome):
    """Data em que a temporada termina ("2025" -> 31/12/2025; "24/25" -> 30/06/2025)."""
    m = re.match(r"^(\d{2})/(\d{2})$", str(nome or ""))
    if m:
        return datetime.date(2000 + int(m.group(2)), 6, 30)
    m = re.match(r"^(\d{4})$", str(nome or ""))
    if m:
        return datetime.date(int(m.group(1)), 12, 31)
    return datetime.date.today()


def _valor_na_data(hist, data):
    melhor = None
    for h in hist.get("marketValueHistory") or []:
        try:
            d = datetime.date.fromisoformat(h["date"][:10])
        except (KeyError, ValueError, TypeError):
            continue
        if d <= data and h.get("marketValue"):
            melhor = h["marketValue"]
    return melhor


def _nomes(nome, completo):
    """(primeiro, sobrenome) pelo nome completo ("Murilo Cerqueira Paim" -> Murilo / Cerqueira Paim)."""
    partes = (completo or nome or "").split()
    if len(partes) >= 2:
        return partes[0], " ".join(partes[1:])
    return (partes[0] if partes else ""), ""


def _stats_temporada(st, temporada, clube):
    soma = collections.Counter()
    temporadas_vistas = sorted({s.get("seasonId") for s in st.get("stats") or [] if s.get("seasonId")}, reverse=True)
    alvo = temporada or (temporadas_vistas[0] if temporadas_vistas else None)
    for s in st.get("stats") or []:
        if s.get("seasonId") != alvo or (clube and s.get("clubId") not in (None, str(clube))):
            continue
        soma["jogos"] += s.get("appearances") or 0
        soma["minutos"] += s.get("minutesPlayed") or 0
        soma["gols"] += s.get("goals") or 0
        soma["assist"] += s.get("assists") or 0
        soma["amarelos"] += (s.get("yellowCards") or 0) + (s.get("secondYellowCards") or 0)
        soma["vermelhos"] += s.get("redCards") or 0
        soma["sofridos"] += s.get("goalsConceded") or 0
        soma["jogos_sem_sofrer"] += s.get("cleanSheets") or 0
    out = dict(soma)
    out["nota"] = None
    out["_parcial"] = True          # sem chutes, dribles, desarmes…: os atributos não são mexidos por eles
    return out


def coletar_time(tm, time, temporada, modo="temporada", opcoes=None, liga=None, progresso=None):
    """Dados de um time (dict de times()) no formato do coleta.coletar_time(); opcoes: estatisticas, valor_da_epoca,
    escalacoes (n), temporada_nome."""
    op = opcoes or {}
    cid = str(time["id"])
    avisos = []
    passo = progresso or (lambda m: None)
    sq_params = {"season_id": temporada} if modo != "atual" and temporada else {}
    passo(f"{time['nome']}: elenco")
    sq = tm.get(f"clubs/{cid}/players", **sq_params)
    lista = sq.get("players") or []
    if not lista:
        raise T.ErroTm(f"A Transfermarkt não tem o elenco de {time['nome']}" + (f" em {op.get('temporada_nome') or temporada}" if sq_params else "") + ".")
    passo(f"{time['nome']}: clube e técnico")
    pc = tm.get(f"clubs/{cid}/profile")
    est = pc.get("stadium") or {}
    tm_time = dict(time)
    tm_time.update(nome=pc.get("shortName") or time["nome"], nome_oficial=pc.get("officialName") or pc.get("name"),
                   sigla=pc.get("abbreviation") or pc.get("clubCode"), logo=T.escudo(cid),
                   pais=time.get("pais") or (pc.get("league") or {}).get("countryName") or (pc.get("stadium") or {}).get("countryName"),
                   estadio={"id": est.get("id"), "nome": est.get("name") or pc.get("stadiumName"),
                            "cidade": (est.get("addressLine2") or "").split(" ", 1)[-1] or None,
                            "capacidade": est.get("capacity") or pc.get("stadiumSeats")})
    tecnico = None
    co = pc.get("coach") or {}
    if co.get("id"):
        try:
            cp = tm.get(f"coaches/{co['id']}/profile")
            prim, sob = _nomes(cp.get("name"), cp.get("nameInHomeCountry"))
            tecnico = {"id": co["id"], "nome": cp.get("name") or co.get("name"), "primeiro": prim, "sobrenome": sob,
                       "nascimento": cp.get("dateOfBirth"), "nacionalidade": (cp.get("citizenship") or [None])[0],
                       "foto": cp.get("imageUrl")}
        except T.ErroTm as ex:
            avisos.append(f"Técnico: {ex}")
            tecnico = {"id": co["id"], "nome": co.get("name"), "primeiro": "", "sobrenome": "", "nascimento": None,
                       "nacionalidade": None, "foto": None}
    # perfis (valor de mercado, posições secundárias, nome completo), estatísticas e valor da época
    rotas = [f"players/{p['id']}/profile" for p in lista]
    if op.get("estatisticas"):
        rotas += [f"players/{p['id']}/stats" for p in lista]
    epoca = _valor_da_epoca(modo, temporada, op)
    if epoca:
        rotas += [f"players/{p['id']}/market_value" for p in lista]
    resp = tm.varios(rotas, progresso=lambda n, t: passo(f"{time['nome']}: jogadores {n}/{t}"))
    data_fim = _fim_temporada(op.get("temporada_nome"))
    data_ref = data_fim if modo != "atual" and data_fim < datetime.date.today() else None
    jogadores = []
    erros = 0
    for p in lista:
        pr = resp.get(f"players/{p['id']}/profile") or {}
        if pr.get("erro"):
            erros += 1
            pr = {}
        pos = pos_tm(p.get("position") or (pr.get("position") or {}).get("main"))
        outras = [x for x in (pos_tm(o) for o in (pr.get("position") or {}).get("other") or []) if x is not None and x != pos]
        valor = pr.get("marketValue") or p.get("marketValue")
        if epoca:
            v = _valor_na_data(resp.get(f"players/{p['id']}/market_value") or {}, data_fim)
            valor = v or valor
        prim, sob = _nomes(p.get("name"), pr.get("fullName"))
        st = _stats_temporada(resp.get(f"players/{p['id']}/stats") or {}, temporada if modo != "atual" else None, cid) \
            if op.get("estatisticas") else {}
        nasc = p.get("dateOfBirth") or pr.get("dateOfBirth")
        nacs = [x for x in (p.get("nationality") or pr.get("citizenship") or []) if x]
        nac = nacs[0] if nacs else None
        idade = pr.get("age") or p.get("age")
        if data_ref and nasc:                              # elenco antigo: a idade que tinha no fim da temporada
            try:
                dn = datetime.date.fromisoformat(nasc[:10])
                idade = data_ref.year - dn.year - ((data_ref.month, data_ref.day) < (dn.month, dn.day))
            except ValueError:
                pass
        jogadores.append({"id": str(p["id"]), "nome": p.get("name") or pr.get("name") or "", "primeiro": prim, "sobrenome": sob,
                          "idade": idade, "nascimento": nasc, "nacionalidades": nacs,
                          "local": (pr.get("placeOfBirth") or {}).get("city"), "pais_nascimento": (pr.get("placeOfBirth") or {}).get("country"),
                          "nacionalidade": nac, "altura": p.get("height") or pr.get("height"), "peso": None,
                          "foto": p.get("imageUrl") or pr.get("imageUrl"), "lesionado": False, "stats": st,
                          "numero": p.get("shirtNumber"), "posicao_api": grupo_tm((pr.get("position") or {}).get("group"), pos),
                          "posicao_tm": pos, "posicoes_tm": outras, "pe_tm": p.get("foot") or pr.get("foot"), "valor": valor,
                          "capitao_tm": bool(p.get("isCaptain")),
                          "clube_tm": {"id": str((pr.get("club") or {}).get("id") or ""), "nome": (pr.get("club") or {}).get("name")}
                          if (pr.get("club") or {}).get("name") else None})
    if erros:
        avisos.append(f"{erros} perfil(is) de jogador não vieram (valor de mercado estimado pelo resto do elenco).")
    # escalações: jogos de um titular da temporada (formação, posições, posse de bola)
    formacoes = collections.Counter()
    pos_jog = collections.defaultdict(collections.Counter)
    posses = []
    if op.get("escalacoes"):
        try:
            formacoes, pos_jog, posses = _escalacoes(tm, cid, jogadores, temporada if modo != "atual" else None,
                                                     (liga or {}).get("id"), int(op["escalacoes"]), passo, time["nome"])
        except T.ErroTm as ex:
            avisos.append(f"Escalações: {ex}")
    for j in jogadores:
        if pos_jog.get(j["id"]):
            j["posicoes_escalacao"] = dict(pos_jog[j["id"]])
    # o valor de mercado do elenco (média e desvio do log) — base das notas
    vs = [math.log10(j["valor"]) for j in jogadores if j.get("valor")]
    cores = pc.get("colors") or []
    casa = [cores[0], cores[1] if len(cores) > 1 else "#FFFFFF"] if cores else None
    fora = [cores[1] if len(cores) > 1 else "#FFFFFF", cores[0]] if cores else None
    return {"fonte": "transfermarkt", "time": tm_time, "temporada": temporada, "temporada_nome": op.get("temporada_nome"),
            "data_ref": data_ref.isoformat() if data_ref else None,
            "temporada_stats": temporada, "modo": modo, "tecnico": tecnico, "jogadores": jogadores,
            "formacao": formacoes.most_common(1)[0][0] if formacoes else None, "formacoes": dict(formacoes),
            "posse": round(sum(posses) / len(posses), 1) if posses else None,
            "cores": {"casa": [casa] if casa else [], "fora": [fora] if fora else [], "goleiro": []},
            "valores": {"media_log": round(sum(vs) / len(vs), 4) if vs else None, "n": len(vs)},
            "liga_tm": pc.get("league"), "avisos": avisos}


def _escalacoes(tm, cid, jogadores, temporada, liga_id, n, passo, nome):
    goleiros = [j for j in jogadores if j.get("posicao_tm") == 0] or jogadores
    ref = min(goleiros, key=lambda j: (j.get("numero") or 99))
    params = {"season_id": temporada} if temporada else {}
    partidas = (tm.get(f"players/{ref['id']}/matches", **params).get("matches") or [])
    jogos = [m for m in partidas if (m.get("club") or {}).get("id") == cid and m.get("gameId")]
    if liga_id:
        jogos = [m for m in jogos if (m.get("competition") or {}).get("id") == liga_id] or jogos
    jogos.sort(key=lambda m: m.get("date") or "")
    formacoes = collections.Counter()
    pos_jog = collections.defaultdict(collections.Counter)
    posses = []
    ids = {j["id"] for j in jogadores}
    rotas = [f"games/{m['gameId']}" for m in jogos[-n:]]
    passo(f"{nome}: escalações")
    for g in tm.varios(rotas).values():
        if not g or g.get("erro"):
            continue
        lado = g["home"] if str((g.get("home") or {}).get("id")) == cid else g.get("away") or {}
        m = re.match(r"\d(?:-\d)+", str(lado.get("formation") or "").replace(" ", ""))     # "4-4-2 double 6" -> 4-4-2
        if m:
            formacoes[m.group(0)] += 1
        if (lado.get("stats") or {}).get("possession") is not None:
            posses.append(float(lado["stats"]["possession"]))
        for p in lado.get("startingLineup") or []:
            pos = pos_tm(p.get("position"))
            if p.get("id") in ids and pos is not None:
                pos_jog[str(p["id"])][pos] += 1
    return formacoes, pos_jog, posses


# ------------------------------------------------------------------ seleções e elencos atuais (atualizar banco)
def coletar_selecao(tm, time, progresso=None):
    """Convocação atual (com nascimento e nacionalidade: o casamento com o banco fica exato) + técnico."""
    passo = progresso or (lambda m: None)
    passo(f"{time['nome']}: convocação")
    d = coletar_time(tm, time, None, "atual", {"estatisticas": False}, None, progresso)
    d["selecao"] = True
    return d


def elenco_atual(tm, clube_id):
    """[{id, nome, idade, nascimento, numero, posicao, foto, nacionalidade}] do elenco de hoje."""
    sq = tm.get(f"clubs/{clube_id}/players")
    out = []
    for p in sq.get("players") or []:
        idade = p.get("age")
        if not idade and p.get("dateOfBirth"):
            try:
                n = datetime.date.fromisoformat(p["dateOfBirth"][:10])
                h = datetime.date.today()
                idade = h.year - n.year - ((h.month, h.day) < (n.month, n.day))
            except ValueError:
                idade = None
        out.append({"id": str(p["id"]), "name": p.get("name"), "age": idade, "nascimento": p.get("dateOfBirth"),
                    "number": p.get("shirtNumber"), "position": p.get("position"), "pos": pos_tm(p.get("position")),
                    "photo": p.get("imageUrl"), "nacionalidade": (p.get("nationality") or [None])[0],
                    "nacionalidades": [x for x in p.get("nationality") or [] if x],
                    "assinou_de": p.get("signedFrom"), "chegou": p.get("joinedOn")})
    return out


def completar_api(tm, dados, temporada=None, modo="temporada", progresso=None):
    """Completa um time coletado na API-Football com o elenco do mesmo clube na Transfermarkt (2 pedidos: a busca do
    clube e o elenco): nascimento, pé, posição exata, altura, nacionalidades e valor de mercado de quem não tem. Os
    jogadores são casados pelo nome e pela idade; nada que a API já trouxe é trocado. Devolve um resumo (texto)."""
    import casamento as K
    passo = progresso or (lambda m: None)
    tm_time = dados.get("time") or {}
    nome = tm_time.get("nome") or ""
    passo(f"{nome}: procurando na Transfermarkt")
    res = (tm.get(f"clubs/search/{re.sub(r'[/?#%]+', ' ', nome).strip()}").get("results") or [])
    pais = K.norm(tm_time.get("pais"))
    cands = sorted(((K.nota_time(nome, c.get("name")) + (0.2 if pais and K.norm(c.get("country")) == pais else 0), c) for c in res
                    if c.get("id")), key=lambda x: -x[0])
    if not cands or cands[0][0] < 0.75:
        return f"Transfermarkt: {nome} não encontrado (nada foi completado)."
    clube = cands[0][1]
    params = {"season_id": str(temporada)} if modo != "atual" and temporada else {}
    passo(f"{nome}: elenco na Transfermarkt")
    lista = tm.get(f"clubs/{clube['id']}/players", **params).get("players") or []
    if not lista:
        return f"Transfermarkt: {clube.get('name')} sem elenco nessa temporada (nada foi completado)."
    tms = []
    for p in lista:
        tk = K.significativas(K.tokens(p.get("name")))
        tms.append((p, tk))
    usados = set()
    feitos = 0
    for j in dados.get("jogadores") or []:
        tk = K.significativas(K.tokens(j.get("nome"), j.get("primeiro"), j.get("sobrenome")))
        tk_nome = K.significativas(K.tokens(K._sem_inicial(j.get("nome"))))
        melhor = None
        for p, tkp in tms:
            if p["id"] in usados or not tkp:
                continue
            casam = K._batem(tk_nome or tk, tkp)
            if not casam or (len(tk_nome) >= 2 and casam < 2 and K._batem(tkp, tk) < len(tkp)):
                continue
            idade_tm = p.get("age")
            if not idade_tm and p.get("dateOfBirth"):        # o elenco do clube às vezes vem sem a idade
                try:
                    dn, hoje = datetime.date.fromisoformat(p["dateOfBirth"][:10]), datetime.date.today()
                    idade_tm = hoje.year - dn.year - ((hoje.month, hoje.day) < (dn.month, dn.day))
                except ValueError:
                    idade_tm = None
            if j.get("idade") and idade_tm and abs(int(j["idade"]) - int(idade_tm)) > 1 + (modo != "atual"):
                continue
            nota = casam / max(1, len(tk_nome or tk)) + 0.5 * K._batem(tkp, tk) / len(tkp)
            if not melhor or nota > melhor[0]:
                melhor = (nota, p)
        if not melhor or melhor[0] < 0.75:
            continue
        p = melhor[1]
        usados.add(p["id"])
        pos = pos_tm(p.get("position"))
        nacs = [x for x in p.get("nationality") or [] if x]
        novo = {"nascimento": p.get("dateOfBirth"), "pe_tm": p.get("foot"), "posicao_tm": pos, "altura": p.get("height"),
                "nacionalidades": nacs, "valor": p.get("marketValue"), "foto": p.get("imageUrl")}
        mudou = False
        for k, v in novo.items():
            if v not in (None, "", []) and not j.get(k):
                j[k] = v
                mudou = True
        if nacs and not j.get("nacionalidade"):
            j["nacionalidade"] = nacs[0]
        j["tm_id"] = str(p["id"])
        feitos += mudou
    dados["tm_clube"] = {"id": str(clube["id"]), "nome": clube.get("name")}
    return (f"Transfermarkt ({clube.get('name')}): {feitos} de {len(dados.get('jogadores') or [])} jogadores completados "
            "(nascimento, pé, posição, altura, nacionalidades).")


def classificacao(tm, liga_id, temporada):
    r = tm.get(f"competitions/{liga_id}/table", season_id=temporada)
    tab = {}
    for t in r.get("tables") or []:
        for l in t.get("rows") or []:
            if l.get("matches"):
                tab[str(l["clubId"])] = {"pos": l.get("position"), "ppj": (l.get("points") or 0) / l["matches"]}
    return tab
