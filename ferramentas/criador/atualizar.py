"""Criador de Ligas e Times — atualiza o banco do jogo pela API-Football: participantes das ligas (promovidos e
rebaixados) e elencos (transferências, empréstimos, saídas, números de camisa e, se pedido, um ajuste pequeno na nota
pelo desempenho recente). Independe da criação de jogadores: mexe nos que já existem; os que faltam no banco podem
ser criados (opcional) com o mesmo gerador dos times novos.

1. preparar(): casa os times de uma liga da API (temporada escolhida) com os times do banco do mesmo país — 1 chamada.
2. conferir(): elencos atuais (players/squads, 1 chamada por time) + transferências (1 por time, para os empréstimos) +
   estatísticas da última temporada liberada (até 3 por time, só se o ajuste de notas for pedido) -> lista de mudanças.
3. aplicar(): as mudanças marcadas viram alterações do Projeto (gerador.py); os times que perderam ou ganharam jogadores
   têm a escalação padrão, os cobradores e o capitão refeitos (nada fica apontando para quem saiu).
"""
import collections
import datetime

import casamento as K
import coleta as C
import notas as N

SEM_CONTRATO = "111592"
LIGAS_ESPECIAIS = {"78", "2136", "382", "383", "2255"}


def _nomes_times(banco, idioma):
    return {t["teamid"]: t for t in banco.times(idioma)}


def _nome_liga(banco, idioma, lid):
    for d in banco.tabela("leagues").dicts():
        if d["leagueid"] == str(lid):
            return (idioma.liga(lid) if idioma else None) or d.get("leaguename") or str(lid)
    return str(lid)


def ligas_do_banco(banco, idioma, ligas_db):
    """Ligas de clubes do banco com o nome do país em inglês (o da API) para sugerir a liga correspondente."""
    nac = {d["nationid"]: d for d in banco.tabela("nations").dicts()}
    out = []
    for l in ligas_db:
        if l["leagueid"] in LIGAS_ESPECIAIS or l.get("internacional") or not l.get("times"):
            continue
        n = nac.get(str(l.get("pais")), {})
        out.append({**l, "pais_en": n.get("nationname"), "iso": n.get("isocountrycode")})
    return sorted(out, key=lambda x: (x.get("pais_en") or "", x["divisao"], x["nome"]))


def ligas_selecoes_do_banco(banco, idioma, ligas_db):
    """As ligas de seleções do banco (78 masculina, 2136 feminina) com o número de seleções."""
    out = []
    for l in ligas_db:
        if l["leagueid"] in ("78", "2136") and l.get("times"):
            out.append({**l, "pais_en": "Seleções", "selecoes": True, "feminina": l["leagueid"] == "2136"})
    return out


def selecoes_do_banco(banco, idioma, leagueid):
    """Seleções de uma liga de seleções do banco: [{teamid, nome, nacao, nacao_en, iso}]."""
    nomes = _nomes_times(banco, idioma)
    nac = {d["nationid"]: d for d in banco.tabela("nations").dicts()}
    tnl = {d["teamid"]: d["nationid"] for d in banco.tabela("teamnationlinks").dicts() if d["leagueid"] == str(leagueid)}
    out = []
    for d in banco.tabela("leagueteamlinks").dicts():
        if d["leagueid"] != str(leagueid):
            continue
        tid, n = d["teamid"], tnl.get(d["teamid"])
        out.append({"teamid": tid, "nome": (nomes.get(tid) or {}).get("nome") or tid, "nacao": n,
                    "nacao_en": (nac.get(n) or {}).get("nationname"), "iso": (nac.get(n) or {}).get("isocountrycode")})
    return sorted(out, key=lambda x: K.norm(x["nome"]))


# nome da seleção na Transfermarkt quando é diferente do nome da nação no banco
_SELECAO_TM = {"korea republic": "South Korea", "korea dpr": "North Korea", "republic of ireland": "Ireland",
               "china pr": "China", "turkey": "Türkiye", "turkiye": "Türkiye", "bosnia and herzegovina": "Bosnia-Herzegovina",
               "cote d ivoire": "Ivory Coast", "ivory coast": "Ivory Coast", "congo dr": "Democratic Republic of the Congo",
               "dr congo": "Democratic Republic of the Congo", "congo": "Republic of the Congo", "fyr macedonia": "North Macedonia",
               "holland": "Netherlands", "czech republic": "Czechia", "czechia": "Czechia", "iran": "Iran", "ir iran": "Iran",
               "cape verde": "Cape Verde", "cape verde islands": "Cape Verde", "st kitts and nevis": "St. Kitts & Nevis",
               "st lucia": "St. Lucia", "st vincent and the grenadines": "St. Vincent & Grenadinen", "usa": "United States",
               "chinese taipei": "Chinese Taipei", "curacao": "Curacao", "kyrgyz republic": "Kyrgyzstan",
               "central african republic": "Central African Republic", "sao tome and principe": "Sao Tome and Principe",
               "trinidad and tobago": "Trinidad and Tobago", "antigua and barbuda": "Antigua and Barbuda",
               "hong kong": "Hongkong", "brunei darussalam": "Brunei", "timor leste": "Timor-Leste"}


def casar_selecao_tm(tm, nome_en, feminina=False):
    """A seleção principal do país na Transfermarkt (lá seleções são "clubes" com o nome do país). Sem feminino."""
    import transfermarkt as T
    if feminina or not nome_en:
        return None
    alias = _SELECAO_TM.get(K.norm(nome_en))
    alvos = {K.norm(nome_en)} | ({K.norm(alias)} if alias else set())
    for q in [x for x in (alias, nome_en) if x]:
        try:
            r = tm.get(f"clubs/search/{q}")
        except T.ErroTm:
            continue
        res = r.get("results") or []
        achou = next((c for c in res if K.norm(c.get("name")) in alvos), None)
        if not achou:                                      # pelo país da seleção (ex.: "Czechia" é da "Czech Republic")
            paises = {K.norm(nome_en), K.norm(pais_tm(nome_en))} | alvos
            achou = next((c for c in res if K.norm(c.get("country")) in paises and not _SEL_BASE.search(c.get("name") or "")
                          and K.norm(c.get("name")).split()[0] in " ".join(paises)), None)
        if achou:
            return {"id": str(achou["id"]), "nome": achou["name"], "sigla": None, "pais": nome_en, "fundacao": None,
                    "logo": T.escudo(achou["id"]), "selecao": True, "fonte": "transfermarkt",
                    "estadio": {"id": None, "nome": None, "cidade": None, "capacidade": None}}
    return None


_SEL_BASE = __import__("re").compile(r"\b(U-?\d\d|Olympic|Olympia|B|II|Amateur|Futsal|Beach|Women|W)\b", __import__("re").I)


def casar_selecao_api(api, nome_en, iso=None, feminina=False):
    """A seleção do país na API-Football (teams?search=; 1 chamada, depois cache). Feminina: o nome termina em " W"."""
    import re
    if not nome_en:
        return None
    q = pais_api(api, nome_en, iso).replace("-", " ")
    alvo = K.norm(q)
    r = api.get("teams", search=q[:40]) or []
    cands = [t["team"] for t in r if (t.get("team") or {}).get("national")]
    def base(nome):
        return K.norm(re.sub(r"\s+(W|U\d\d)$", "", nome or ""))
    certos = [t for t in cands if base(t["name"]) == alvo and bool(re.search(r"\sW$", t["name"])) == bool(feminina)
              and not re.search(r"\sU\d\d$", t["name"])]
    if not certos:
        return None
    t = certos[0]
    return {"id": t["id"], "nome": t["name"], "sigla": t.get("code"), "pais": t.get("country") or nome_en,
            "fundacao": t.get("founded"), "logo": t.get("logo"), "selecao": True, "fonte": "apifootball",
            "estadio": {"id": None, "nome": None, "cidade": None, "capacidade": None}}


def pais_api(api, nome_en, iso=None):
    """Nome do país na API ("Saudi Arabia" -> "Saudi-Arabia", "Korea Republic" -> "South-Korea"…)."""
    try:
        paises = C.paises(api)
    except Exception:  # noqa: BLE001
        return (nome_en or "").replace(" ", "-")
    alvo = K.norm(nome_en)
    for p in paises:
        if K.norm(p["name"]) == alvo:
            return p["name"]
    if iso:
        for p in paises:
            if (p.get("code") or "").upper() in (iso.upper(), f"GB-{iso.upper()}"):
                return p["name"]
    apelidos = {"korea republic": "South-Korea", "united states": "USA", "republic of ireland": "Ireland",
                "cote d ivoire": "Ivory-Coast", "china pr": "China", "czech republic": "Czech-Republic"}
    return apelidos.get(alvo, (nome_en or "").replace(" ", "-"))


def sugerir_ligas(api, banco, idioma, leagueid, ligas_db):
    """Ligas da API do país da liga do banco, a de divisão igual primeiro."""
    l = next((x for x in ligas_do_banco(banco, idioma, ligas_db) if x["leagueid"] == str(leagueid)), None)
    if not l:
        raise ValueError("Liga do banco não encontrada.")
    pais = pais_api(api, l.get("pais_en"), l.get("iso"))
    ligas = [x for x in C.ligas(api, pais) if x["tipo"] == "League" and not x.get("selecao")]
    fem = bool(l.get("feminina"))
    ligas = [x for x in ligas if bool(_fem(x["nome"])) == fem] or ligas
    ligas.sort(key=lambda x: (abs(N.divisao_pelo_nome(x["nome"]) - l["divisao"]), x["id"]))
    return {"pais": pais, "ligas": ligas, "liga": l}


def _fem(nome):
    import re
    return re.search(r"\b(women|womens|feminin|femenin|frauen|ladies|w)\b", (nome or "").lower())


def _times_db_do_pais(banco, idioma, pais_id, feminino):
    """Times de clube do banco que podem corresponder: das ligas do país + do Resto do Mundo com a nação do país."""
    tm = {d["teamid"]: d for d in banco.tabela("teams").dicts()}
    ligas = {d["leagueid"]: d for d in banco.tabela("leagues").dicts()}
    liga_de = {}
    for d in banco.tabela("leagueteamlinks").dicts():
        liga_de.setdefault(d["teamid"], d["leagueid"])
    nacao_rdm = {d["teamid"]: d["nationid"] for d in banco.tabela("teamnationlinks").dicts() if d["leagueid"] in ("76", "2226")}
    nomes = _nomes_times(banco, idioma)
    out = []
    for tid, lid in liga_de.items():
        if lid in LIGAS_ESPECIAIS or tid not in tm or tm[tid].get("gender", "0") != ("1" if feminino else "0"):
            continue
        pais = ligas.get(lid, {}).get("countryid")
        if pais == str(pais_id) or nacao_rdm.get(tid) == str(pais_id):
            out.append({"teamid": tid, "nome": nomes.get(tid, {}).get("nome") or tm[tid].get("teamname"), "leagueid": lid})
    return out


def _elencos_db(banco):
    """teamid -> ({nascimento em dias}, {nomes normalizados}) dos jogadores do banco (para desempatar casamentos)."""
    pl = banco.tabela("players")
    c = {n: i for i, n in enumerate(pl.campos)}
    info = {}
    for l in pl.linhas:
        j = banco.jogador(dict(zip(pl.campos, l)))
        info[l[c["playerid"]]] = (l[c["birthdate"]], {K.norm(x) for x in (j["comum"], j["camisa"], f"{j['primeiro']} {j['sobrenome']}") if x})
    out = collections.defaultdict(lambda: (set(), set()))
    for d in banco.tabela("teamplayerlinks").dicts():
        i = info.get(d["playerid"])
        if i:
            out[d["teamid"]][0].add(i[0])
            out[d["teamid"]][1].update(i[1])
    return out


def _desempate_tm(tm, banco):
    import coleta_tm as CT
    elencos = {}

    def f(t, cands):
        if not elencos:
            elencos.update(_elencos_db(banco))
        datas = {str((datetime.date.fromisoformat(j["nascimento"][:10]) - K.BASE_DATA).days)
                 for j in CT.elenco_atual(tm, t["id"]) if j.get("nascimento")}
        if not datas:
            return {}
        return {tid: len(datas & elencos[tid][0]) / len(datas) for tid in cands}
    return f


def _desempate_api(api, banco):
    elencos = {}

    def f(t, cands):
        if not elencos:
            elencos.update(_elencos_db(banco))
        sq = api.get("players/squads", team=t["id"]) or []
        nomes = {K.norm(p.get("name")) for b in sq for p in b.get("players") or [] if p.get("name")}
        if not nomes:
            return {}
        return {tid: len(nomes & elencos[tid][1]) / len(nomes) for tid in cands}
    return f


def preparar(api, banco, idioma, leagueid, liga_api, temporada):
    lg = next((d for d in banco.tabela("leagues").dicts() if d["leagueid"] == str(leagueid)), None)
    if not lg:
        raise ValueError("Liga do banco não encontrada.")
    fem = lg.get("iswomencompetition") == "1"
    times_api = C.times(api, liga_api, temporada)
    if not times_api:
        raise ValueError("A API não tem times dessa liga nessa temporada.")
    times_db = _times_db_do_pais(banco, idioma, lg["countryid"], fem)
    mapa = K.ler_mapa()
    pares = K.casar_times(times_api, times_db, mapa.get("times"), minimo=0.62, desempate=_desempate_api(api, banco))
    por_id = {t["teamid"]: t for t in times_db}
    info_api = None
    try:
        nac = next((d for d in banco.tabela("nations").dicts() if d["nationid"] == lg["countryid"]), {})
        for l in C.ligas(api, pais_api(api, nac.get("nationname"), nac.get("isocountrycode"))):
            if l["id"] == int(liga_api):
                info_api = l
    except Exception:  # noqa: BLE001
        pass
    a = {"id": f"U{leagueid}-{liga_api}-{temporada}", "leagueid": str(leagueid), "liga_nome": _nome_liga(banco, idioma, leagueid),
         "liga_api": int(liga_api), "liga_api_nome": (info_api or {}).get("nome") or str(liga_api), "temporada": int(temporada),
         "liga_api_info": info_api or {"id": int(liga_api), "nome": str(liga_api), "pais": None}, "feminina": fem,
         "pares": [], "sem_par": [], "fora": [], "mudancas": [], "conferido": None}
    usados = set()
    for t in times_api:
        p = pares.get(t["id"])
        if p:
            tid, nota, origem = p
            usados.add(tid)
            a["pares"].append({"api_id": t["id"], "api_nome": t["nome"], "api_logo": t.get("logo"), "teamid": tid,
                               "nome_db": por_id[tid]["nome"], "nota": nota, "origem": origem, "liga_db": por_id[tid]["leagueid"],
                               "liga_db_nome": _nome_liga(banco, idioma, por_id[tid]["leagueid"])})
        else:
            a["sem_par"].append(t)
    for t in times_db:
        if t["leagueid"] == str(leagueid) and t["teamid"] not in usados:
            a["fora"].append({"teamid": t["teamid"], "nome": t["nome"]})
    return a


# ------------------------------------------------------------------ Transfermarkt (temporada atual liberada; elencos com nascimento)
_ALIAS_TM = {"korea republic": "korea south", "korea dpr": "korea north", "republic of ireland": "ireland",
             "cote d ivoire": "cote d ivoire", "united states": "united states", "china pr": "china", "turkey": "turkiye",
             "bosnia and herzegovina": "bosnia herzegovina", "czech republic": "czech republic", "congo dr": "dr congo",
             "fyr macedonia": "north macedonia", "cape verde": "cape verde"}


def pais_tm(nome_en):
    import coleta_tm as CT
    alvo = K.norm(nome_en)
    alvo = _ALIAS_TM.get(alvo, alvo)
    paises = {K.norm(c.get("pais")): c.get("pais") for c in CT.catalogo() if c.get("pais")}
    return paises.get(alvo) or paises.get(K.norm(nome_en)) or nome_en


def _divisao_tm(liga):
    import re
    m = re.search(r"(\d)$", str(liga["id"]))
    return int(m.group(1)) if m else 9


def sugerir_ligas_tm(tm, banco, idioma, leagueid, ligas_db):
    import coleta_tm as CT
    l = next((x for x in ligas_do_banco(banco, idioma, ligas_db) if x["leagueid"] == str(leagueid)), None)
    if not l:
        raise ValueError("Liga do banco não encontrada.")
    pais = pais_tm(l.get("pais_en"))
    todas = [x for x in CT.ligas(tm, pais) if x["tipo"] == "League"]
    ligas = [x for x in todas if not CT.secundaria(x["nome"])] or todas
    ligas.sort(key=lambda x: (abs(_divisao_tm(x) - l["divisao"]), -(x.get("valor") or 0)))
    return {"pais": pais, "ligas": ligas, "liga": l, "fonte": "transfermarkt"}


def preparar_tm(tm, banco, idioma, leagueid, liga_id, temporada, liga_nome=None, pais=None):
    import coleta_tm as CT
    lg = next((d for d in banco.tabela("leagues").dicts() if d["leagueid"] == str(leagueid)), None)
    if not lg:
        raise ValueError("Liga do banco não encontrada.")
    fem = lg.get("iswomencompetition") == "1"
    times_api = CT.times(tm, liga_id, temporada or None, {"pais": pais})
    if not times_api:
        raise ValueError("A Transfermarkt não tem times dessa liga nessa temporada.")
    times_db = _times_db_do_pais(banco, idioma, lg["countryid"], fem)
    pares = K.casar_times(times_api, times_db, K.ler_mapa().get("tm_times"), minimo=0.62, desempate=_desempate_tm(tm, banco))
    por_id = {t["teamid"]: t for t in times_db}
    nome_temp = temporada or "atual"
    a = {"id": f"UTM{leagueid}-{liga_id}-{nome_temp}", "fonte": "transfermarkt", "leagueid": str(leagueid),
         "liga_nome": _nome_liga(banco, idioma, leagueid), "liga_api": liga_id, "liga_api_nome": liga_nome or liga_id,
         "temporada": temporada, "liga_api_info": {"id": liga_id, "nome": liga_nome or liga_id, "fonte": "transfermarkt",
                                                   "pais": pais, "temporadas": None}, "feminina": fem,
         "pares": [], "sem_par": [], "fora": [], "mudancas": [], "conferido": None}
    usados = set()
    for t in times_api:
        p = pares.get(t["id"])
        if p:
            tid, nota, origem = p
            usados.add(tid)
            a["pares"].append({"api_id": t["id"], "api_nome": t["nome"], "api_logo": t.get("logo"), "teamid": tid,
                               "nome_db": por_id[tid]["nome"], "nota": nota, "origem": origem, "liga_db": por_id[tid]["leagueid"],
                               "liga_db_nome": _nome_liga(banco, idioma, por_id[tid]["leagueid"])})
        else:
            a["sem_par"].append(t)
    for t in times_db:
        if t["leagueid"] == str(leagueid) and t["teamid"] not in usados:
            a["fora"].append({"teamid": t["teamid"], "nome": t["nome"]})
    return a


def conferir_tm(tm, banco, idioma, a, opcoes, progresso=None):
    """Como conferir(), com os elencos da Transfermarkt: cada jogador vem com o nascimento (casamento exato com o banco);
    empréstimos pelas transferências de quem mudou de clube; notas pelo valor de mercado."""
    import coleta_tm as CT
    import gerador as G
    passo = progresso or (lambda m, f=None, t=None: None)
    opcoes = {"participantes": True, "elencos": True, "emprestimos": True, "numeros": True, "saidas": True, "notas": False,
              "criar": False, **{k: v for k, v in (opcoes or {}).items() if v is not None}}
    mud = _participantes(banco, idioma, a) if opcoes["participantes"] else []
    if opcoes["elencos"]:
        nomes = _nomes_times(banco, idioma)
        idx = K.IndiceJogadores(banco)
        mapa = K.ler_mapa()
        vinc = collections.defaultdict(list)
        clube_de = {}
        for d in banco.tabela("teamplayerlinks").dicts():
            vinc[d["teamid"]].append(d)
            if nomes.get(d["teamid"], {}).get("leagueid") not in LIGAS_ESPECIAIS:
                clube_de.setdefault(d["playerid"], d["teamid"])
        emprest = {d["playerid"]: d for d in banco.tabela("playerloans").dicts()} if banco.tem("playerloans") else {}
        tm_para_db = {str(p["api_id"]): p["teamid"] for p in a["pares"]}
        tm_para_db.update({k: v for k, v in mapa.get("tm_times", {}).items() if k not in tm_para_db})
        alvo = [p for p in a["pares"] if not opcoes.get("times") or str(p["api_id"]) in {str(x) for x in opcoes["times"]}]
        vistos = {}
        elencos = {}
        for n, p in enumerate(alvo):
            passo(f"Elenco de {p['nome_db']}…", n, len(alvo))
            elencos[p["teamid"]] = (p, CT.elenco_atual(tm, p["api_id"]))
        mudou = []                                         # (m, id na Transfermarkt) para olhar empréstimos depois
        perfis_novos = []
        casados_tm = {}                                    # id na Transfermarkt -> playerid
        coef = None
        for tid, (p, lista) in elencos.items():
            antes = {d["playerid"]: d for d in vinc.get(tid, [])}
            for jp in lista:
                pid = mapa.get("tm_jogadores", {}).get(str(jp["id"]))
                nota = 1.0
                if not pid or pid not in idx.info:
                    cand = idx.buscar(jp.get("name"), nascimento=jp.get("nascimento"), idade=jp.get("age"),
                                      genero="1" if a.get("feminina") else "0", times_pref=[tid], minimo=0.8)
                    pid, nota = (cand[0][1], cand[0][0]) if cand else (None, 0)
                if not pid:
                    m = {"tipo": "novo", "teamid": tid, "time": p["nome_db"], "nome": jp.get("name"), "idade": jp.get("age"),
                         "nascimento": jp.get("nascimento"), "nacionalidade": jp.get("nacionalidade"),
                         "nacionalidades": jp.get("nacionalidades") or [], "numero": jp.get("number"),
                         "posicao_api": CT.grupo_tm(jp.get("position"), jp.get("pos")), "posicao_tm": jp.get("pos"),
                         "foto": jp.get("photo"), "api_id": jp["id"], "fonte": "transfermarkt", "aplicar": bool(opcoes["criar"]),
                         "descricao": f"{jp.get('name')} ({jp.get('age') or '?'} anos, {N.NOME_POS.get(CT.pos_tm(jp.get('position')), jp.get('position') or '?')}) "
                                      f"não existe no banco — novo no {p['nome_db']}"}
                    mud.append(m)
                    perfis_novos.append(m)
                    continue
                vistos[pid] = tid
                casados_tm[str(jp["id"])] = pid
                info = idx.info[pid]
                atual = clube_de.get(pid)
                if atual == tid:
                    d = antes.get(pid)
                    if opcoes["numeros"] and jp.get("number") and d and str(jp["number"]) != d.get("jerseynumber"):
                        mud.append({"tipo": "numero", "teamid": tid, "playerid": pid, "nome": info["nome"], "de": d.get("jerseynumber"),
                                    "para": int(jp["number"]), "aplicar": True,
                                    "descricao": f"{info['nome']} ({p['nome_db']}): camisa {d.get('jerseynumber')} → {jp['number']}"})
                    if pid in emprest:
                        mudou.append(({"tipo": "?fim", "teamid": tid, "playerid": pid, "nome": info["nome"]}, jp["id"]))
                    continue
                de_nome = nomes.get(atual, {}).get("nome") if atual else "sem clube"
                m = {"tipo": "transferencia", "teamid": tid, "playerid": pid, "nome": info["nome"], "de": atual, "de_nome": de_nome,
                     "para": tid, "para_nome": p["nome_db"], "numero": jp.get("number"), "aplicar": nota >= 0.85, "confianca": nota,
                     "descricao": f"{info['nome']}: {de_nome} → {p['nome_db']}" + (f" (confira: {int(nota * 100)}%)" if nota < 0.85 else "")}
                mud.append(m)
                mudou.append((m, jp["id"]))
            if opcoes["saidas"]:
                for pid in antes:
                    if pid in vistos:
                        continue
                    info = idx.info.get(pid)
                    if info:
                        mud.append({"tipo": "saida", "teamid": tid, "playerid": pid, "nome": info["nome"], "de": tid, "de_nome": p["nome_db"],
                                    "para": SEM_CONTRATO, "aplicar": True,
                                    "descricao": f"{info['nome']} ({info['overall']}): não está no elenco atual do {p['nome_db']} → sem contrato"})
        # saídas de quem apareceu em outro elenco conferido: já são transferências
        mud = [m for m in mud if not (m["tipo"] == "saida" and m["playerid"] in vistos)]
        # empréstimos: a última transferência de quem mudou de clube (ou de quem estava emprestado e voltou)
        if opcoes["emprestimos"] and mudou:
            rotas = {f"players/{tid_tm}/transfers": (m, tid_tm) for m, tid_tm in mudou}
            resp = tm.varios(list(rotas), progresso=lambda n, t: passo(f"Transferências {n}/{t}…", n, t))
            for rota, (m, tid_tm) in rotas.items():
                trs = sorted([t for t in (resp.get(rota) or {}).get("transfers") or [] if t.get("date") and not t.get("upcoming")],
                             key=lambda t: t["date"])
                ult = trs[-1] if trs else None
                if m["tipo"] == "?fim":
                    if ult and ult.get("transferType") == "endOfLoan":
                        m.update(tipo="fim_emprestimo", aplicar=True, descricao=f"{m['nome']}: fim do empréstimo, fica no "
                                 f"{_nomes_times(banco, idioma).get(m['teamid'], {}).get('nome')}")
                        mud.append(m)
                    continue
                if ult and ult.get("transferType") == "loan":
                    dono = tm_para_db.get(str((ult.get("clubFrom") or {}).get("id"))) or m["de"]
                    fim = (ult.get("contractUntil") or "")[:10] or _fim_emprestimo(ult.get("date"))
                    m.update(tipo="emprestimo", dono=dono, fim=fim,
                             descricao=f"{m['nome']}: emprestado pelo {_nomes_times(banco, idioma).get(dono, {}).get('nome') or (ult.get('clubFrom') or {}).get('name')}"
                                       f" ao {m['para_nome']} até {fim}")
        # notas e jogadores novos pelo valor de mercado (1 perfil por jogador)
        if opcoes["notas"] or (opcoes["criar"] and perfis_novos):
            coef = N.carregar_coef_tm()
            quem = []
            if opcoes["notas"]:
                for tid, (p, lista) in elencos.items():
                    quem += [(tid, jp) for jp in lista]
            quem += [(m["teamid"], {"id": m["api_id"]}) for m in perfis_novos if opcoes["criar"]]
            resp = tm.varios([f"players/{jp['id']}/profile" for _, jp in quem],
                             progresso=lambda n, t: passo(f"Valores de mercado {n}/{t}…", n, t))
            for m in perfis_novos:
                pr = resp.get(f"players/{m['api_id']}/profile") or {}
                if pr.get("marketValue"):
                    m["valor"] = pr["marketValue"]
                    m["pe_tm"] = pr.get("foot")
                    m["altura"] = pr.get("height")
                    m["primeiro"], m["sobrenome"] = CT._nomes(pr.get("name"), pr.get("fullName"))
            if opcoes["notas"]:
                for tid, (p, lista) in elencos.items():
                    for jp in lista:
                        pid = casados_tm.get(str(jp["id"]))
                        pr = resp.get(f"players/{jp['id']}/profile") or {}
                        if not pid or not pr.get("marketValue"):
                            continue
                        estimada = N.overall_tm(pr["marketValue"], pr.get("age"), coef)
                        ov = idx.info[pid]["overall"]
                        if abs(estimada - ov) >= 3:            # diferença pequena é ruído do modelo: não mexe
                            delta = max(-2, min(2, estimada - ov))
                            mud.append({"tipo": "nota", "teamid": tid, "playerid": pid, "nome": idx.info[pid]["nome"], "de": ov,
                                        "para": ov + delta, "aplicar": True,
                                        "descricao": f"{idx.info[pid]['nome']}: {ov} → {ov + delta} (valor de mercado {pr['marketValue']:,} € "
                                                     f"indica {estimada})".replace(",", ".")})
        _ = G
    ordem = {"liga": 0, "transferencia": 1, "emprestimo": 2, "fim_emprestimo": 3, "saida": 4, "numero": 5, "nota": 6, "novo": 7}
    mud.sort(key=lambda m: (ordem.get(m["tipo"], 9), m.get("descricao", "")))
    a["mudancas"] = mud
    a["conferido"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    a["opcoes"] = opcoes
    return a


def _dias(data_iso):
    try:
        return (datetime.date.fromisoformat(str(data_iso)[:10]) - K.BASE_DATA).days
    except ValueError:
        return None


def _participantes(banco, idioma, a):
    mud = []
    ligas_nome = lambda lid: _nome_liga(banco, idioma, lid)  # noqa: E731
    for p in a["pares"]:
        if p["liga_db"] != a["leagueid"]:
            mud.append({"tipo": "liga", "teamid": p["teamid"], "nome": p["nome_db"], "de": p["liga_db"], "para": a["leagueid"],
                        "aplicar": True, "descricao": f"{p['nome_db']}: {ligas_nome(p['liga_db'])} → {a['liga_nome']}"})
    destino_fora = _liga_vizinha(banco, a)
    rdm = destino_fora in ("76", "2226")
    for t in a["fora"]:
        mud.append({"tipo": "liga", "teamid": t["teamid"], "nome": t["nome"], "de": a["leagueid"], "para": destino_fora, "fora": True,
                    "aplicar": bool(destino_fora),
                    "descricao": f"{t['nome']}: não está na {a['liga_api_nome']} {a.get('temporada_nome') or a.get('temporada') or 'atual'} → "
                    f"{ligas_nome(destino_fora) if destino_fora else 'escolha a liga'}"
                    + (" (não há divisão abaixo no banco; entra com a nação em teamnationlinks)" if rdm else "")})
    return mud


def casar_manual(a, api_id, teamid, banco, idioma):
    tm_fonte = a.get("fonte") == "transfermarkt"
    api_id = str(api_id) if tm_fonte else int(api_id)
    a["pares"] = [p for p in a["pares"] if p["api_id"] != api_id and (not teamid or p["teamid"] != str(teamid))]
    t_api = next((t for t in a["sem_par"] if t["id"] == api_id), None)
    if teamid:
        nomes = _nomes_times(banco, idioma)
        lid = nomes.get(str(teamid), {}).get("leagueid")
        nome_api = t_api["nome"] if t_api else str(api_id)
        a["pares"].append({"api_id": api_id, "api_nome": nome_api, "api_logo": (t_api or {}).get("logo"), "teamid": str(teamid),
                           "nome_db": nomes.get(str(teamid), {}).get("nome") or str(teamid), "nota": 1.0, "origem": "manual",
                           "liga_db": lid, "liga_db_nome": _nome_liga(banco, idioma, lid)})
        a["sem_par"] = [t for t in a["sem_par"] if t["id"] != api_id]
        a["fora"] = [t for t in a["fora"] if t["teamid"] != str(teamid)]
        m = K.ler_mapa()
        m["tm_times" if tm_fonte else "times"][str(api_id)] = str(teamid)
        K.gravar_mapa(m)
    elif t_api is None:
        a["sem_par"].append({"id": api_id, "nome": str(api_id)})
    a["mudancas"] = []
    a["conferido"] = None


# ------------------------------------------------------------------ conferir
def _fim_emprestimo(data_iso):
    """A API não dá o fim do empréstimo: o próximo 30/06 (calendário europeu) a pelo menos 5 meses, senão 31/12."""
    try:
        d = datetime.date.fromisoformat(str(data_iso)[:10])
    except ValueError:
        d = datetime.date.today()
    for cand in (datetime.date(d.year, 6, 30), datetime.date(d.year, 12, 31), datetime.date(d.year + 1, 6, 30),
                 datetime.date(d.year + 1, 12, 31)):
        if (cand - d).days >= 150:
            return cand.isoformat()
    return datetime.date(d.year + 1, 6, 30).isoformat()


def conferir(api, banco, idioma, a, opcoes, progresso=None):
    passo = progresso or (lambda m, f=None, t=None: None)
    opcoes = {"participantes": True, "elencos": True, "emprestimos": True, "numeros": True, "saidas": True, "notas": False,
              "criar": False, **{k: v for k, v in (opcoes or {}).items() if v is not None}}
    mud = []
    nomes = _nomes_times(banco, idioma)
    ligas_nome = lambda lid: _nome_liga(banco, idioma, lid)  # noqa: E731
    # ---- participantes
    if opcoes["participantes"]:
        for p in a["pares"]:
            if p["liga_db"] != a["leagueid"]:
                mud.append({"tipo": "liga", "teamid": p["teamid"], "nome": p["nome_db"], "de": p["liga_db"], "para": a["leagueid"],
                            "aplicar": True, "descricao": f"{p['nome_db']}: {ligas_nome(p['liga_db'])} → {a['liga_nome']}"})
        destino_fora = _liga_vizinha(banco, a)
        for t in a["fora"]:
            mud.append({"tipo": "liga", "teamid": t["teamid"], "nome": t["nome"], "de": a["leagueid"], "para": destino_fora,
                        "aplicar": bool(destino_fora), "descricao": f"{t['nome']}: não está na {a['liga_api_nome']} {a['temporada']} → "
                        f"{ligas_nome(destino_fora) if destino_fora else 'escolha a liga'}"})
    # ---- elencos
    if opcoes["elencos"]:
        idx = K.IndiceJogadores(banco)
        mapa = K.ler_mapa()
        pl = banco.tabela("players")
        c = {n: i for i, n in enumerate(pl.campos)}
        vinc = collections.defaultdict(list)                 # teamid -> [linha de teamplayerlinks]
        clube_de = {}
        for d in banco.tabela("teamplayerlinks").dicts():
            vinc[d["teamid"]].append(d)
            if nomes.get(d["teamid"], {}).get("leagueid") not in LIGAS_ESPECIAIS:
                clube_de.setdefault(d["playerid"], d["teamid"])
        emprest = {d["playerid"]: d for d in banco.tabela("playerloans").dicts()} if banco.tem("playerloans") else {}
        api_para_db = {str(p["api_id"]): p["teamid"] for p in a["pares"]}
        api_para_db.update({k: v for k, v in mapa.get("times", {}).items() if k not in api_para_db})
        alvo = [p for p in a["pares"] if not opcoes.get("times") or p["api_id"] in set(opcoes["times"])]
        vistos = {}                                           # playerid -> teamid onde apareceu na API
        elencos = {}
        for n, p in enumerate(alvo):
            passo(f"Elenco de {p['nome_db']}…", n, len(alvo))
            sq = api.get("players/squads", team=p["api_id"])
            elencos[p["teamid"]] = (p, sq[0]["players"] if sq else [])
        tr_por_time = {}
        if opcoes["emprestimos"]:
            for n, p in enumerate(alvo):
                passo(f"Transferências de {p['nome_db']}…", n, len(alvo))
                tr_por_time[p["teamid"]] = api.get("transfers", team=p["api_id"])
        for tid, (p, lista) in elencos.items():
            antes = {d["playerid"]: d for d in vinc.get(tid, [])}
            ultimos = _ultimas_transferencias(tr_por_time.get(tid) or [])
            for jp in lista:
                pid = mapa.get("jogadores", {}).get(str(jp["id"]))
                nota = 1.0
                if not pid or pid not in idx.info:
                    cand = idx.buscar(jp.get("name"), idade=jp.get("age"), genero="1" if a.get("feminina") else "0",
                                      times_pref=[tid], minimo=0.7)
                    pid, nota = (cand[0][1], cand[0][0]) if cand else (None, 0)
                if not pid:
                    mud.append({"tipo": "novo", "teamid": tid, "time": p["nome_db"], "nome": jp.get("name"), "idade": jp.get("age"),
                                "numero": jp.get("number"), "posicao_api": C.POS_API.get(jp.get("position") or ""), "foto": jp.get("photo"),
                                "api_id": jp["id"], "aplicar": bool(opcoes["criar"]),
                                "descricao": f"{jp.get('name')} ({jp.get('age')} anos) não existe no banco — novo no {p['nome_db']}"})
                    continue
                vistos[pid] = tid
                info = idx.info[pid]
                atual = clube_de.get(pid)
                tr = ultimos.get(jp["id"])
                if atual == tid:
                    d = antes.get(pid)
                    if opcoes["numeros"] and jp.get("number") and d and str(jp["number"]) != d.get("jerseynumber"):
                        mud.append({"tipo": "numero", "teamid": tid, "playerid": pid, "nome": info["nome"], "de": d.get("jerseynumber"),
                                    "para": int(jp["number"]), "aplicar": True,
                                    "descricao": f"{info['nome']} ({p['nome_db']}): camisa {d.get('jerseynumber')} → {jp['number']}"})
                    if pid in emprest and tr and tr["type"] in ("Back from Loan", "Return from loan"):
                        mud.append({"tipo": "fim_emprestimo", "teamid": tid, "playerid": pid, "nome": info["nome"], "aplicar": True,
                                    "descricao": f"{info['nome']}: fim do empréstimo, fica no {p['nome_db']}"})
                    continue
                # está em outro clube no banco (ou sem clube): transferência ou empréstimo
                de_nome = nomes.get(atual, {}).get("nome") if atual else "sem clube"
                m = {"teamid": tid, "playerid": pid, "nome": info["nome"], "de": atual, "de_nome": de_nome, "para": tid,
                     "para_nome": p["nome_db"], "numero": jp.get("number"), "aplicar": nota >= 0.85, "confianca": nota}
                if tr and tr["type"] == "Loan" and (tr["teams"]["in"] or {}).get("id") == p["api_id"]:
                    dono = api_para_db.get(str((tr["teams"]["out"] or {}).get("id")))
                    m.update(tipo="emprestimo", dono=dono or atual, fim=_fim_emprestimo(tr.get("date")),
                             descricao=f"{info['nome']}: emprestado pelo {nomes.get(dono or atual, {}).get('nome') or de_nome} ao {p['nome_db']}")
                else:
                    m.update(tipo="transferencia", descricao=f"{info['nome']}: {de_nome} → {p['nome_db']}")
                if nota < 0.85:
                    m["descricao"] += f" (confira: nome parecido, {int(nota * 100)}%)"
                mud.append(m)
            # quem está no time no banco e não está na API
            if opcoes["saidas"]:
                for pid, d in antes.items():
                    if pid in vistos and vistos[pid] == tid:
                        continue
                    if pid in vistos:
                        continue                              # apareceu em outro time conferido: já é uma transferência
                    info = idx.info.get(pid)
                    if not info:
                        continue
                    m_saida = {"tipo": "saida", "teamid": tid, "playerid": pid, "nome": info["nome"], "de": tid, "de_nome": p["nome_db"],
                               "para": SEM_CONTRATO, "aplicar": True,
                               "descricao": f"{info['nome']} ({info['overall']}): não está no elenco atual do {p['nome_db']} → sem contrato"}
                    mud.append(m_saida)
        # empréstimos para fora (o time conferido emprestou e o clube que recebeu está no banco)
        for tid, trs in tr_por_time.items():
            p = elencos[tid][0]
            for api_pid, tr in _ultimas_transferencias(trs).items():
                if tr["type"] != "Loan" or (tr["teams"]["out"] or {}).get("id") != p["api_id"]:
                    continue
                para = api_para_db.get(str((tr["teams"]["in"] or {}).get("id")))
                pid = mapa.get("jogadores", {}).get(str(api_pid))
                if pid not in idx.info:
                    pid = None
                if not pid:
                    nome = tr.get("_nome")
                    cand = idx.buscar(nome, times_pref=[tid], genero="1" if a.get("feminina") else "0", minimo=0.85) if nome else []
                    pid = cand[0][1] if cand else None
                if not pid or not para or pid in vistos or clube_de.get(pid) == para:
                    continue
                fim = _fim_emprestimo(tr.get("date"))
                if fim < datetime.date.today().isoformat():
                    continue
                for x in [x for x in mud if x.get("playerid") == pid and x["tipo"] == "saida"]:
                    mud.remove(x)
                info = idx.info[pid]
                mud.append({"tipo": "emprestimo", "teamid": para, "playerid": pid, "nome": info["nome"], "de": clube_de.get(pid),
                            "de_nome": nomes.get(clube_de.get(pid), {}).get("nome"), "para": para, "para_nome": nomes.get(para, {}).get("nome"),
                            "dono": tid, "fim": fim, "numero": None, "aplicar": True,
                            "descricao": f"{info['nome']}: emprestado pelo {p['nome_db']} ao {nomes.get(para, {}).get('nome')}"})
                vistos[pid] = para
        # notas pelo desempenho recente (estatísticas da última temporada liberada)
        if opcoes["notas"]:
            tp = C.ultima_temporada(api, a["temporada"])
            for n, p in enumerate(alvo):
                passo(f"Desempenho de {p['nome_db']} em {tp}…", n, len(alvo))
                try:
                    rs = api.todas("players", team=p["api_id"], season=tp)
                except Exception:  # noqa: BLE001
                    continue
                notas_t = []
                for r in rs:
                    st, _, _ = C._stats_time(r, p["api_id"])
                    if st.get("nota") and (st.get("minutos") or 0) >= 900:
                        notas_t.append((r["player"], st))
                if len(notas_t) < 6:
                    continue
                media = sum(st["nota"] for _, st in notas_t) / len(notas_t)
                for pj_api, st in notas_t:
                    cand = idx.buscar(pj_api.get("name"), pj_api.get("firstname") or "", pj_api.get("lastname") or "",
                                      (pj_api.get("birth") or {}).get("date"), pj_api.get("age"), times_pref=[p["teamid"]], minimo=0.9)
                    if not cand:
                        continue
                    pid = cand[0][1]
                    delta = int(max(-2, min(2, round((st["nota"] - media) * 2.2))))
                    if delta:
                        ov = idx.info[pid]["overall"]
                        mud.append({"tipo": "nota", "teamid": p["teamid"], "playerid": pid, "nome": idx.info[pid]["nome"], "de": ov,
                                    "para": ov + delta, "aplicar": True,
                                    "descricao": f"{idx.info[pid]['nome']}: {ov} → {ov + delta} (nota {st['nota']:.2f} na API em {tp}, "
                                                 f"média do time {media:.2f}, {st['minutos']} min)"})
    ordem = {"liga": 0, "transferencia": 1, "emprestimo": 2, "fim_emprestimo": 3, "saida": 4, "numero": 5, "nota": 6, "novo": 7}
    mud.sort(key=lambda m: (ordem.get(m["tipo"], 9), m.get("descricao", "")))
    a["mudancas"] = mud
    a["conferido"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    a["opcoes"] = opcoes
    return a


def _ultimas_transferencias(trs):
    """{api id do jogador: a transferência mais recente} (com o nome do jogador em _nome)."""
    out = {}
    for p in trs or []:
        lst = sorted((t for t in p.get("transfers") or [] if t.get("date")), key=lambda t: t["date"])
        if lst:
            t = dict(lst[-1])
            t["_nome"] = (p.get("player") or {}).get("name")
            out[(p.get("player") or {}).get("id")] = t
    return out


def _liga_vizinha(banco, a):
    """Para onde vão os times que saíram da liga: a divisão de baixo do mesmo país e gênero; sem ela no banco, o Resto do
    Mundo (76 / 2226 no feminino) — o aplicar() põe a nação do time em teamnationlinks."""
    import gerador as G
    lg = {d["leagueid"]: d for d in banco.tabela("leagues").dicts()}
    eu = lg.get(a["leagueid"])
    if not eu:
        return None
    nivel = int(eu.get("level") or 1)
    for lid, d in lg.items():
        if d["countryid"] == eu["countryid"] and int(d.get("level") or 0) == nivel + 1 \
                and d.get("iswomencompetition") == eu.get("iswomencompetition") and lid not in LIGAS_ESPECIAIS:
            return lid
    rdm = G.LIGA_RDM[1 if eu.get("iswomencompetition") == "1" else 0]
    return rdm if rdm in lg else None


# ------------------------------------------------------------------ aplicar no Projeto
def aplicar(pj, atualizacoes):
    import gerador as G
    mexidos = set()
    # conferências de várias ligas juntas: um time que saiu de uma liga (ex.: subiu da Série B) e está na lista de outra
    # (a Série A) vai para essa outra — a mudança "saiu da liga" fica de fora
    entram = {m["teamid"] for a in atualizacoes for m in a.get("mudancas") or []
              if m.get("aplicar") and m["tipo"] == "liga" and not m.get("fora")}
    entram |= {p["teamid"] for a in atualizacoes for p in a.get("pares") or []
               if any(m.get("aplicar") and m["tipo"] == "liga" for m in a.get("mudancas") or [])}
    for a in atualizacoes:
        for m in a.get("mudancas") or []:
            if not m.get("aplicar"):
                continue
            t = m["tipo"]
            if t == "liga" and m.get("fora") and m["teamid"] in entram:
                continue
            if t == "liga" and m.get("para"):
                pj.alterar("leagueteamlinks", {"leagueid": m["para"], "prevleagueid": m["de"]}, teamid=m["teamid"], leagueid=m["de"])
                if m["de"] in G.LIGA_RDM.values():
                    pj.remover("teamnationlinks", teamid=m["teamid"], leagueid=m["de"])
                if m["para"] in G.LIGA_RDM.values():
                    pais = next((d["countryid"] for d in pj.tab("leagues").dicts() if d["leagueid"] == m["de"]), "211")
                    pj.novas["teamnationlinks"].append({"leagueid": m["para"], "teamid": m["teamid"], "nationid": pais})
            elif t in ("transferencia", "emprestimo", "saida", "fim_emprestimo"):
                pid = m["playerid"]
                para = m["para"] if t != "fim_emprestimo" else m["teamid"]
                origem = _clube_atual(pj, pid)
                if origem is None:
                    continue
                num = _numero_livre(pj, para, m.get("numero"), pid) if para != SEM_CONTRATO else 99
                pj.alterar("teamplayerlinks", {"teamid": para, "jerseynumber": num, "position": 29}, playerid=pid, teamid=origem)
                mexidos |= {origem, para}
                if pj.tem_tabela("playerloans"):
                    pj.remover("playerloans", playerid=pid)
                    pj.novas["playerloans"] = [x for x in pj.novas.get("playerloans", []) if x["playerid"] != str(pid)]
                    if t == "emprestimo" and m.get("dono") and m["dono"] != para:
                        linha = pj.linha_vazia("playerloans")
                        linha.update(playerid=str(pid), teamidloanedfrom=str(m["dono"]), loandateend=str(N.dias(m["fim"])),
                                     isloantobuy="0", futureoptiontobuy="0")
                        pj.novas["playerloans"].append(linha)
            elif t == "numero":
                pid, tid = m["playerid"], m["teamid"]
                outro = [d for d in pj.atuais("teamplayerlinks", teamid=tid, jerseynumber=m["para"]) if d["playerid"] != str(pid)]
                if outro:                                     # quem usava o número fica com o antigo
                    pj.alterar("teamplayerlinks", {"jerseynumber": m["de"]}, teamid=tid, playerid=outro[0]["playerid"])
                pj.alterar("teamplayerlinks", {"jerseynumber": m["para"]}, teamid=tid, playerid=pid)
            elif t == "nota":
                _mudar_nota(pj, m["playerid"], int(m["para"]))
            elif t == "novo":
                _criar_jogador(pj, m, a)
                mexidos.add(m["teamid"])
    for tid in mexidos:
        if tid != SEM_CONTRATO:
            reescalar(pj, tid)
    return mexidos


def _clube_atual(pj, pid):
    lig = pj.liga_de
    for d in pj.atuais("teamplayerlinks", playerid=pid):
        if lig.get(d["teamid"]) not in ("78", "2136"):
            return d["teamid"]
    return None


def _numero_livre(pj, teamid, pedido, pid):
    usados = {d["jerseynumber"] for d in pj.atuais("teamplayerlinks", teamid=teamid) if d["playerid"] != str(pid)}
    usados |= {d["jerseynumber"] for d in pj.novas_de("teamplayerlinks", teamid=teamid)}
    if pedido and str(pedido) not in usados and 1 <= int(pedido) <= 99:
        return int(pedido)
    return next((n for n in range(2, 99) if str(n) not in usados), 99)


def _mudar_nota(pj, pid, nova):
    ns = pj.indices("players", playerid=pid)
    if not ns:
        return
    d = pj.linha("players", ns[0])
    ant = int(d["overallrating"])
    delta = nova - ant
    pos = int(d["preferredposition1"])
    gen = int(d.get("gender") or 0)
    m = pj.perfil.modelo(pos, gen)
    vals = {"overallrating": nova, "potential": max(int(d["potential"]), nova)}
    for k, w in zip(pj.perfil.atr, m["pesos"]):            # mexe só nos atributos que pesam na nota da posição
        if w > 0.02:
            vals[k] = max(1, min(99, int(d[k]) + delta))
    pj.alterar_linha("players", ns[0], vals)


def _criar_jogador(pj, m, a):
    tid = m["teamid"]
    gen = 1 if a.get("feminina") else 0
    nv = pj.nivel_time_db.get(tid, 66)
    j = {"id": m["api_id"], "nome": m["nome"], "primeiro": m.get("primeiro") or "", "sobrenome": m.get("sobrenome") or "",
         "idade": m.get("idade"), "nascimento": m.get("nascimento"), "nacionalidade": m.get("nacionalidade"),
         "altura": m.get("altura"), "peso": None, "foto": m.get("foto"), "stats": {}, "numero": m.get("numero"),
         "posicao_api": m.get("posicao_api"), "posicao_tm": m.get("posicao_tm"), "pe_tm": m.get("pe_tm"), "valor": m.get("valor")}
    tm = {"id": 0, "nome": m.get("time") or "", "pais": None}
    if m.get("fonte") == "transfermarkt" and m.get("valor"):
        # nota pelo valor de mercado (o nível do time não entra: o valor já diz)
        js = pj._preparar_jogadores({"time": tm, "jogadores": [j], "fonte": "transfermarkt"}, None, gen, {})
    else:
        js = pj._preparar_jogadores({"time": tm, "jogadores": [j]}, nv - 3.5, gen, {})
    for jj in js:
        pais = next((d["countryid"] for d in pj.tab("leagues").dicts() if d["leagueid"] == pj.liga_de.get(tid)), "211")
        jj["nacao_manual"] = next((n for n in (pj.nacao(x) for x in [m.get("nacionalidade"), *(m.get("nacionalidades") or [])] if x)
                                   if n and str(n) != "211"), None) or pais
        pj._linhas_jogador(jj, tid, gen)
        tl = pj.linha_vazia("teamplayerlinks")
        tl.update(teamid=tid, playerid=str(jj["playerid"]), jerseynumber=str(_numero_livre(pj, tid, m.get("numero"), jj["playerid"])),
                  position="29", form="3", artificialkey=str(pj.ids("tpl", "teamplayerlinks", "artificialkey").novo()))
        pj.novas["teamplayerlinks"].append(tl)
        m["playerid_novo"] = jj["playerid"]


def reescalar(pj, teamid):
    """Escalação padrão, cobradores e capitão de um time do banco refeitos com o elenco atual (vínculos com as
    mudanças do projeto): ninguém que saiu fica na escalação."""
    import gerador as G
    vincs = pj.atuais("teamplayerlinks", teamid=teamid) + pj.novas_de("teamplayerlinks", teamid=teamid)
    if len(vincs) < 11:
        pj.avisos.append(f"Time {teamid}: ficou com {len(vincs)} jogadores (menos de 11) — a escalação não foi refeita.")
        return
    jogs = []
    for v in vincs:
        ns = pj.indices("players", playerid=v["playerid"])
        d = pj.linha("players", ns[0]) if ns else next((x for x in pj.novas_de("players", playerid=v["playerid"])), None)
        if not d:
            continue
        atr = {k: int(d.get(k) or 0) for k in pj.perfil.atr}
        jogs.append({"id": v["playerid"], "playerid": int(v["playerid"]), "overall": int(d["overallrating"]), "pos": int(d["preferredposition1"]),
                     "atr": atr, "idade": None, "stats": {}, "numero": int(v["jerseynumber"]) if str(v["jerseynumber"]).isdigit() else None})
    fo = pj.atuais("formations", teamid=teamid)
    if not fo:
        return
    vagas = [int(fo[0][f"position{i}"]) for i in range(11)]
    tit = pj._escalar(jogs, vagas)
    ordem = tit + sorted((j for j in jogs if j not in tit), key=lambda j: -j["overall"])
    takers = pj._cobradores(tit)
    for i, j in enumerate(ordem):
        pos = vagas[i] if i < 11 else (28 if i < 20 else 29)
        if pj.indices("teamplayerlinks", teamid=teamid, playerid=j["playerid"]):
            pj.alterar("teamplayerlinks", {"position": pos}, teamid=teamid, playerid=j["playerid"])
        else:
            for x in pj.novas_de("teamplayerlinks", teamid=teamid, playerid=j["playerid"]):
                x["position"] = str(pos)
    t = pj.atuais("teams", teamid=teamid)
    if t:
        pj.alterar("teams", {k: j["playerid"] for k, j in takers.items() if k in t[0]}, teamid=teamid)
    dm = pj.atuais("default_mentalities", teamid=teamid)
    if dm:
        pj.alterar("default_mentalities", {f"playerid{i}": tit[i]["playerid"] for i in range(11)}, teamid=teamid)
    ts = pj.atuais("default_teamsheets", teamid=teamid)
    if ts:
        nova = pj._folha(dict(ts[0]), teamid, ordem, takers)
        pj.alterar("default_teamsheets", {k: v for k, v in nova.items() if k != "teamid"}, teamid=teamid)
    notas_lin = pj._notas_time(tit, vagas)
    if t:
        pj.alterar("teams", {"overallrating": notas_lin["geral"], "attackrating": notas_lin["ataque"],
                             "midfieldrating": notas_lin["meio"], "defenserating": notas_lin["defesa"]}, teamid=teamid)
    _ = G
