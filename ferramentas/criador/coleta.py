"""Criador de Ligas e Times — coleta dos dados na API-Football (comum/apifutebol.py).

Para cada time junta, num formato só:
    time        nome, sigla, fundação, logo, estádio (nome, cidade, capacidade)
    tecnico     nome, nascimento, nacionalidade
    jogadores   nome, nome completo, nascimento, nacionalidade, altura, peso, foto, número,
                posição da API (G/D/M/F), estatísticas da temporada e posições nas escalações
    formacao    a mais usada nas escalações coletadas;  cores: uniforme de jogador e de goleiro

Elenco:
    "temporada"  os jogadores que atuaram pelo time na temporada escolhida (players?team&season)
    "atual"      o elenco de hoje (players/squads) com estatísticas da última temporada liberada no plano

O plano grátis libera só algumas temporadas e 3 páginas por consulta; estimar() diz quantas chamadas faltam (o que já
está no cache não gasta nada).
"""
import collections
import datetime

POS_API = {"Goalkeeper": "G", "Defender": "D", "Midfielder": "M", "Attacker": "F", "G": "G", "D": "D", "M": "M", "F": "F"}


def _int(v, padrao=None):
    try:
        return int(str(v).split()[0])
    except (TypeError, ValueError, IndexError):
        return padrao


def temporadas_livres(api):
    """(primeira, última) temporada liberada no plano (None = sem restrição conhecida)."""
    t = api.cfg.get("temporadas")
    return tuple(t) if t else None


def ultima_temporada(api, preferida=None):
    t = temporadas_livres(api)
    ano = preferida or datetime.date.today().year
    if t:
        return max(t[0], min(ano, t[1]))
    return ano


# ------------------------------------------------------------------ navegação (países, ligas, times)
def paises(api):
    return sorted(api.get("countries"), key=lambda p: p["name"])


def ligas(api, pais):
    out = []
    for l in api.get("leagues", country=pais):
        lg, ss = l["league"], l["seasons"]
        atual = next((s for s in ss if s.get("current")), ss[-1] if ss else {})
        cov = atual.get("coverage") or {}
        out.append({"id": lg["id"], "nome": lg["name"], "tipo": lg["type"], "logo": lg.get("logo"),
                    "pais": (l.get("country") or {}).get("name"), "codigo_pais": (l.get("country") or {}).get("code"),
                    "temporadas": [s["year"] for s in ss], "atual": atual.get("year"),
                    "jogadores": bool(cov.get("players")), "escalacoes": bool((cov.get("fixtures") or {}).get("lineups")),
                    "estatisticas": bool((cov.get("fixtures") or {}).get("statistics_players"))})
    return out


def times(api, liga, temporada):
    out = []
    for t in api.get("teams", league=liga, season=temporada):
        tm, v = t["team"], t.get("venue") or {}
        out.append({"id": tm["id"], "nome": tm["name"], "sigla": tm.get("code"), "pais": tm.get("country"),
                    "fundacao": tm.get("founded"), "logo": tm.get("logo"), "selecao": tm.get("national"),
                    "estadio": {"id": v.get("id"), "nome": v.get("name"), "cidade": v.get("city"),
                                "capacidade": v.get("capacity"), "gramado": v.get("surface"), "imagem": v.get("image")}})
    return sorted(out, key=lambda t: t["nome"])


# ------------------------------------------------------------------ custo em chamadas
def estimar(api, time_id, temporada, modo="temporada", escalacoes=3, liga=None):
    """Chamadas que coletar_time() ainda vai gastar (o cache conta zero). Perfis avulsos do modo atual não entram."""
    n = 0
    maxp = int(api.cfg.get("max_paginas") or 40)
    tp = ultima_temporada(api, temporada) if modo == "atual" else temporada
    c1 = api.do_cache("players", team=time_id, season=tp, page=1)
    if c1 is None:
        n += min(maxp, 3)                                   # sem saber o total: o típico são 2–4 páginas
    else:
        total = min(maxp, (c1.get("paging") or {}).get("total") or 1)
        n += sum(1 for p in range(2, total + 1) if not api.em_cache("players", team=time_id, season=tp, page=p))
    n += api.chamadas_para("coachs", team=time_id)
    if modo == "atual":
        n += api.chamadas_para("players/squads", team=time_id)
    if escalacoes:
        fx = api.do_cache("fixtures", team=time_id, season=tp)
        if fx is None:
            n += 1 + escalacoes
        else:
            jogos = [f for f in fx.get("response") or [] if (f.get("fixture") or {}).get("status", {}).get("short") in ("FT", "AET", "PEN")]
            if liga:
                jogos = [f for f in jogos if (f.get("league") or {}).get("id") == liga] or jogos
            jogos.sort(key=lambda f: f["fixture"]["timestamp"])
            n += sum(1 for f in jogos[-escalacoes:] if not api.em_cache("fixtures/lineups", fixture=f["fixture"]["id"]))
    return n


# ------------------------------------------------------------------ coleta de um time
def _stats_time(r, time_id, liga=None):
    """Estatísticas do jogador pelo time (soma das competições; a liga indicada pesa a nota)."""
    soma = collections.Counter()
    nota_p = nota_n = 0.0
    numero = None
    posicao = None
    for s in r.get("statistics") or []:
        if (s.get("team") or {}).get("id") != time_id:
            continue
        g = s.get("games") or {}
        mins = g.get("minutes") or 0
        soma["jogos"] += g.get("appearences") or 0
        soma["titular"] += g.get("lineups") or 0
        soma["minutos"] += mins
        for grupo, campo, chave in (("goals", "total", "gols"), ("goals", "assists", "assist"), ("goals", "saves", "defesas"),
                                    ("goals", "conceded", "sofridos"), ("shots", "total", "chutes"), ("shots", "on", "no_gol"),
                                    ("passes", "total", "passes"), ("passes", "key", "passes_chave"),
                                    ("tackles", "total", "desarmes"), ("tackles", "interceptions", "intercept"),
                                    ("tackles", "blocks", "bloqueios"), ("duels", "total", "duelos"), ("duels", "won", "duelos_ganhos"),
                                    ("dribbles", "attempts", "dribles"), ("dribbles", "success", "dribles_certos"),
                                    ("fouls", "committed", "faltas"), ("fouls", "drawn", "faltas_sofridas"),
                                    ("cards", "yellow", "amarelos"), ("cards", "red", "vermelhos"),
                                    ("penalty", "scored", "penaltis"), ("penalty", "saved", "penaltis_defendidos")):
            v = (s.get(grupo) or {}).get(campo)
            if v:
                soma[chave] += v
        if g.get("rating") and mins:
            peso = mins * (1.5 if liga and (s.get("league") or {}).get("id") == liga else 1.0)
            nota_p += float(g["rating"]) * peso
            nota_n += peso
        if g.get("captain"):
            soma["capitao"] += 1
        numero = numero or g.get("number")
        posicao = posicao or g.get("position")
    out = dict(soma)
    out["nota"] = round(nota_p / nota_n, 3) if nota_n else None
    return out, numero, posicao


def _perfil(p):
    b = p.get("birth") or {}
    return {"id": p["id"], "nome": p.get("name") or "", "primeiro": p.get("firstname") or "", "sobrenome": p.get("lastname") or "",
            "idade": p.get("age"), "nascimento": b.get("date"), "local": b.get("place"), "pais_nascimento": b.get("country"),
            "nacionalidade": p.get("nationality") or b.get("country"), "altura": _int(p.get("height")),
            "peso": _int(p.get("weight")), "foto": p.get("photo"), "lesionado": bool(p.get("injured"))}


def coletar_time(api, time, temporada, modo="temporada", escalacoes=3, perfis_faltantes=0, liga=None, progresso=None):
    """Dados de um time (dict de times()) prontos para o gerador. Não lança se algo opcional faltar: vai para 'avisos'."""
    tid = time["id"]
    avisos = []
    passo = (lambda m: progresso(m)) if progresso else (lambda m: None)
    tp = ultima_temporada(api, temporada) if modo == "atual" else temporada
    # jogadores com estatísticas (até o limite de páginas do plano)
    passo(f"{time['nome']}: jogadores de {tp}")
    info = {}
    rs = api.todas("players", team=tid, season=tp, info=info)
    if info.get("incompleto"):
        avisos.append(f"O plano só libera {len(rs)} jogadores por consulta ({info.get('paginas')} páginas no total): "
                      "os que ficaram de fora entram pelo elenco atual ou não entram.")
    por_id = {}
    for r in rs:
        st, num, pos = _stats_time(r, tid, liga)
        j = _perfil(r["player"])
        j.update(stats=st, numero=num, posicao_api=POS_API.get(pos or "", None))
        por_id[j["id"]] = j
    jogadores = []
    if modo == "atual":
        passo(f"{time['nome']}: elenco atual")
        sq = api.get("players/squads", team=tid)
        lista = sq[0]["players"] if sq else []
        faltam = []
        for p in lista:
            j = por_id.get(p["id"])
            if j is None:
                j = {"id": p["id"], "nome": p.get("name") or "", "primeiro": "", "sobrenome": "", "idade": p.get("age"),
                     "nascimento": None, "nacionalidade": None, "altura": None, "peso": None, "foto": p.get("photo"),
                     "stats": {}, "lesionado": False}
                faltam.append(j)
            j["numero"] = p.get("number") or j.get("numero")
            j["posicao_api"] = POS_API.get(p.get("position") or "", j.get("posicao_api"))
            jogadores.append(j)
        # perfis de quem não estava no time na temporada liberada (1 chamada cada)
        for j in faltam[:max(0, perfis_faltantes)]:
            try:
                pr = api.get("players/profiles", player=j["id"])
            except Exception as ex:  # noqa: BLE001 — limite diário etc.: segue com o que tem
                avisos.append(f"Perfil de {j['nome']}: {ex}")
                break
            if pr:
                p = _perfil(pr[0]["player"])
                j.update({k: v for k, v in p.items() if v not in (None, "")})
        sem = sum(1 for j in faltam if not j.get("nascimento"))
        if sem:
            avisos.append(f"{sem} jogador(es) do elenco atual sem perfil (nascimento/altura/nacionalidade estimados).")
    else:
        # quem atuou pelo time na temporada (ou estava inscrito e tem número)
        for j in por_id.values():
            if (j["stats"].get("jogos") or 0) > 0 or j.get("numero"):
                jogadores.append(j)
        if not jogadores:
            jogadores = list(por_id.values())
    # técnico
    tecnico = None
    try:
        cs = api.get("coachs", team=tid)
        atuais = [c for c in cs if any((x.get("team") or {}).get("id") == tid and not x.get("end") for x in c.get("career") or [])]
        c = (atuais or cs or [None])[0]
        if c:
            b = c.get("birth") or {}
            tecnico = {"id": c["id"], "nome": c.get("name") or "", "primeiro": c.get("firstname") or "",
                       "sobrenome": c.get("lastname") or "", "nascimento": b.get("date"), "nacionalidade": c.get("nationality"),
                       "foto": c.get("photo")}
    except Exception as ex:  # noqa: BLE001
        avisos.append(f"Técnico: {ex}")
    # escalações: posição de cada jogador, formação e cores dos uniformes
    formacoes = collections.Counter()
    cores = {"casa": collections.Counter(), "fora": collections.Counter(), "goleiro": collections.Counter()}
    pos_jog = collections.defaultdict(collections.Counter)
    lados = collections.defaultdict(collections.Counter)
    if escalacoes:
        try:
            passo(f"{time['nome']}: escalações")
            fx = [f for f in api.get("fixtures", team=tid, season=tp)
                  if (f.get("fixture") or {}).get("status", {}).get("short") in ("FT", "AET", "PEN")]
            if liga:
                fx = [f for f in fx if (f.get("league") or {}).get("id") == liga] or fx
            fx.sort(key=lambda f: f["fixture"]["timestamp"])
            for f in fx[-escalacoes:]:
                casa = f["teams"]["home"]["id"] == tid
                for t in api.get("fixtures/lineups", fixture=f["fixture"]["id"]):
                    if (t.get("team") or {}).get("id") != tid:
                        continue
                    form = t.get("formation") or ""
                    if form:
                        formacoes[form] += 1
                    cs = (t.get("team") or {}).get("colors") or {}
                    if cs.get("player"):
                        cores["casa" if casa else "fora"][(cs["player"].get("primary"), cs["player"].get("number"))] += 1
                    if cs.get("goalkeeper"):
                        cores["goleiro"][(cs["goalkeeper"].get("primary"), cs["goalkeeper"].get("number"))] += 1
                    mapa = posicoes_por_grid(form)
                    for x in t.get("startXI") or []:
                        p = x.get("player") or {}
                        base, lado = mapa.get(p.get("grid") or "", (None, None))
                        if p.get("id") and base is not None:
                            pos_jog[p["id"]][base] += 1
                            if lado:
                                lados[p["id"]][lado] += 1
        except Exception as ex:  # noqa: BLE001
            avisos.append(f"Escalações: {ex}")
    for j in jogadores:
        if pos_jog.get(j["id"]):
            j["posicoes_escalacao"] = dict(pos_jog[j["id"]])
            j["lado"] = lados[j["id"]].most_common(1)[0][0] if lados.get(j["id"]) else None
    return {"time": time, "temporada": temporada, "temporada_stats": tp, "modo": modo, "tecnico": tecnico, "jogadores": jogadores,
            "formacao": formacoes.most_common(1)[0][0] if formacoes else None, "formacoes": dict(formacoes),
            "cores": {k: [list(c) for c, _ in v.most_common(2)] for k, v in cores.items()}, "avisos": avisos}


# ------------------------------------------------------------------ seleções
def estimar_selecao(api, time_id, temporada, escalacoes=0):
    n = api.chamadas_para("players/squads", team=time_id) + api.chamadas_para("coachs", team=time_id)
    if escalacoes:
        fx = api.do_cache("fixtures", team=time_id, season=temporada)
        if fx is None:
            n += 1 + escalacoes
        else:
            jogos = [f for f in fx.get("response") or [] if (f.get("fixture") or {}).get("status", {}).get("short") in ("FT", "AET", "PEN")]
            jogos.sort(key=lambda f: f["fixture"]["timestamp"])
            n += sum(1 for f in jogos[-escalacoes:] if not api.em_cache("fixtures/lineups", fixture=f["fixture"]["id"]))
    return n


def coletar_selecao(api, time, temporada, escalacoes=0, progresso=None, convocacao=None):
    """Convocação atual (players/squads), técnico e, se pedido, as últimas escalações (formação e cores). Os jogadores
    são casados com o banco na geração (gerador.criar_selecao): a API só dá nome, idade, número e posição.
    convocacao (ano): uma convocação antiga — quem jogou pela seleção naquela temporada (players?team=&season=, com o
    nascimento: o casamento fica exato) e as escalações dela; o técnico fica o do banco."""
    tid = time["id"]
    avisos = []
    passo = (lambda m: progresso(m)) if progresso else (lambda m: None)
    jogadores = []
    if convocacao:
        passo(f"{time['nome']}: quem jogou em {convocacao}")
        for r in api.todas("players", team=tid, season=int(convocacao)):
            st, numero, posicao = _stats_time(r, tid)
            if not st.get("jogos"):
                continue
            j = _perfil(r["player"])
            j.update(stats=st, numero=numero, posicao_api=POS_API.get(posicao or ""))
            jogadores.append(j)
        if not jogadores:
            avisos.append(f"A API não tem jogadores desta seleção em {convocacao}: o elenco vem só do banco.")
        temporada = int(convocacao)
    else:
        passo(f"{time['nome']}: convocação")
        sq = api.get("players/squads", team=tid)
        for p in (sq[0]["players"] if sq else []):
            jogadores.append({"id": p["id"], "nome": p.get("name") or "", "primeiro": "", "sobrenome": "", "idade": p.get("age"),
                              "nascimento": None, "numero": p.get("number"), "posicao_api": POS_API.get(p.get("position") or ""),
                              "foto": p.get("photo"), "stats": {}})
        if not jogadores:
            avisos.append("A API não tem a convocação atual desta seleção: o elenco vem só do banco.")
    tecnico = None
    try:
        if convocacao:
            raise StopIteration                            # convocação antiga: o técnico fica o do banco
        cs = api.get("coachs", team=tid)
        atuais = [c for c in cs if any((x.get("team") or {}).get("id") == tid and not x.get("end") for x in c.get("career") or [])]
        c = (atuais or cs or [None])[0]
        if c:
            b = c.get("birth") or {}
            tecnico = {"id": c["id"], "nome": c.get("name") or "", "primeiro": c.get("firstname") or "",
                       "sobrenome": c.get("lastname") or "", "nascimento": b.get("date"), "nacionalidade": c.get("nationality"),
                       "foto": c.get("photo")}
    except StopIteration:
        pass
    except Exception as ex:  # noqa: BLE001
        avisos.append(f"Técnico: {ex}")
    formacoes = collections.Counter()
    cores = {"casa": collections.Counter(), "fora": collections.Counter(), "goleiro": collections.Counter()}
    if escalacoes:
        try:
            passo(f"{time['nome']}: escalações")
            fx = [f for f in api.get("fixtures", team=tid, season=temporada)
                  if (f.get("fixture") or {}).get("status", {}).get("short") in ("FT", "AET", "PEN")]
            fx.sort(key=lambda f: f["fixture"]["timestamp"])
            for f in fx[-escalacoes:]:
                casa = f["teams"]["home"]["id"] == tid
                for t in api.get("fixtures/lineups", fixture=f["fixture"]["id"]):
                    if (t.get("team") or {}).get("id") != tid:
                        continue
                    if t.get("formation"):
                        formacoes[t["formation"]] += 1
                    cs = (t.get("team") or {}).get("colors") or {}
                    if cs.get("player"):
                        cores["casa" if casa else "fora"][(cs["player"].get("primary"), cs["player"].get("number"))] += 1
                    if cs.get("goalkeeper"):
                        cores["goleiro"][(cs["goalkeeper"].get("primary"), cs["goalkeeper"].get("number"))] += 1
        except Exception as ex:  # noqa: BLE001
            avisos.append(f"Escalações: {ex}")
    return {"time": time, "selecao": True, "temporada": temporada, "modo": "temporada" if convocacao else "atual",
            "convocacao": convocacao, "tecnico": tecnico, "jogadores": jogadores,
            "formacao": formacoes.most_common(1)[0][0] if formacoes else None, "formacoes": dict(formacoes),
            "cores": {k: [list(c) for c, _ in v.most_common(2)] for k, v in cores.items()}, "avisos": avisos}


# ------------------------------------------------------------------ grid das escalações -> posição do jogo
# Códigos de posição do FC: 0 GOL, 2 ALD, 3 LD, 5 ZAG, 7 LE, 8 ALE, 10 VOL, 12 MD, 14 MC, 16 ME, 18 MEI, 21 SA, 23 PD, 25 ATA, 27 PE
def posicoes_formacao(formacao):
    """'4-2-3-1' -> {linha: [posição da esquerda para a direita]} (linha 1 = goleiro), como no grid da API."""
    try:
        linhas = [int(x) for x in formacao.split("-") if x]
    except (ValueError, AttributeError):
        return {}
    out = {1: [0]}
    n = len(linhas)
    tres_atras = linhas and linhas[0] == 3
    for i, k in enumerate(linhas):
        if i == 0:
            pos = {2: [5, 5], 3: [5, 5, 5], 4: [7, 5, 5, 3], 5: [8, 5, 5, 5, 2]}.get(k, [5] * k)
        elif i == n - 1:
            pos = {1: [25], 2: [25, 25], 3: [27, 25, 23]}.get(k, [27] + [25] * max(0, k - 2) + [23])
        else:
            meios, j = n - 2, i - 1
            if meios == 1:
                pos = {1: [10], 2: [14, 14], 3: [14, 14, 14], 4: [16, 14, 14, 12], 5: [16, 14, 10, 14, 12]}.get(k, [14] * k)
            elif j == 0:
                pos = {1: [10], 2: [10, 10], 3: [14, 10, 14], 4: [16, 14, 14, 12], 5: [16, 14, 10, 14, 12]}.get(k, [14] * k)
            elif j == meios - 1:
                pos = {1: [18], 2: [18, 18], 3: [27, 18, 23], 4: [16, 14, 14, 12]}.get(k, [14] * k)
            else:
                pos = {1: [14], 2: [14, 14], 3: [14, 14, 14], 4: [16, 14, 14, 12]}.get(k, [14] * k)
            if tres_atras and j == 0 and k >= 4:            # 3 zagueiros: os abertos do meio são alas
                pos = [8] + pos[1:-1] + [2]
        out[i + 2] = pos
    return out


def posicoes_por_grid(formacao):
    """{'linha:coluna': (posição, lado)} — lado 'E'/'D'/None para escolher o pé."""
    out = {}
    for linha, pos in posicoes_formacao(formacao).items():
        k = len(pos)
        for col, p in enumerate(pos, start=1):
            lado = None
            if k > 1 and col == 1:
                lado = "E"
            elif k > 1 and col == k:
                lado = "D"
            out[f"{linha}:{col}"] = (p, lado)
    return out
