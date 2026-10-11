"""Criador de Ligas e Times — recalibra o modelo de notas com o que já está no cache da API.

Junta todas as respostas de players?team&season guardadas em dados/api_cache, casa cada jogador com o mesmo jogador no
banco (data de nascimento + nome), descobre o time do banco que corresponde ao time da API (o mais comum entre os casados)
e ajusta os coeficientes (notas.calibrar). Quanto mais times que já existem no banco forem coletados, melhor fica.
"""
import collections
import datetime
import glob
import json
import os

import coleta as C
import dados
import notas as N

BASE = datetime.date(1582, 10, 14)


def _tokens(s):
    return set(dados.normalizar(s).split())


def pares_do_cache(api, banco):
    pl = banco.tabela("players")
    c = {n: i for i, n in enumerate(pl.campos)}
    por_nasc = collections.defaultdict(list)
    for l in pl.linhas:
        por_nasc[l[c["birthdate"]]].append(l)
    time_db = {}
    for d in banco.tabela("teamplayerlinks").dicts():
        time_db.setdefault(d["playerid"], d["teamid"])
    grupos = collections.defaultdict(list)        # (team api, season) -> [respostas]
    for arq in glob.glob(os.path.join(api.cache, "players", "*.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        p = (r.get("parameters") or {})
        if not p.get("team") or not p.get("season"):
            continue
        grupos[(int(p["team"]), int(p["season"]))] += r.get("response") or []
    pares = []
    for (tid, temporada), rs in grupos.items():
        casados = []
        for r in rs:
            pj = r["player"]
            st, _, _ = C._stats_time(r, tid)
            nasc = (pj.get("birth") or {}).get("date")
            if not nasc:
                continue
            nd = str((datetime.date.fromisoformat(nasc) - BASE).days)
            nomes = _tokens(f"{pj.get('name')} {pj.get('firstname') or ''} {pj.get('lastname') or ''}")
            melhor, nota = None, 0
            for l in por_nasc.get(nd, []):
                j = banco.jogador(dict(zip(pl.campos, l)))
                s = len(nomes & _tokens(f"{j['primeiro']} {j['sobrenome']} {j['comum']} {j['camisa']}"))
                if s > nota:
                    melhor, nota = l, s
            if melhor is not None and nota >= 1:
                casados.append((melhor, st, pj.get("age")))
        if len(casados) < 8:
            continue
        votos = collections.Counter(time_db.get(m[c["playerid"]]) for m, _, _ in casados)
        time_banco, n = votos.most_common(1)[0]
        if not time_banco or n < 6:
            continue
        for m, st, idade in casados:
            if time_db.get(m[c["playerid"]]) != time_banco:
                continue                              # mudou de time depois: o nível do time não vale para ele
            pares.append({"overall": int(m[c["overallrating"]]), "time": time_banco, "st": st, "idade": idade})
    return pares


def do_cache(api, banco):
    pares = pares_do_cache(api, banco)
    r = N.calibrar(pares, N.nivel_times(banco))
    if not r:
        return None
    r["origem"] = f"cache da API: {r['amostra']} jogadores de {r['times']} times"
    r["quando"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(N.CALIBRACAO, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    try:
        r["aparencia"] = aparencia_do_cache(api, banco)
    except Exception as ex:  # noqa: BLE001 — sem OpenCV ou sem fotos: fica a referência anterior
        r["aparencia"] = {"erro": str(ex)}
    return r


def tm_do_cache(tm, banco):
    """Notas pelo valor de mercado (Transfermarkt): elencos e perfis guardados em dados/tm_cache, casados com o banco pelo
    nascimento + nome; o time do banco é o mais comum entre os casados de cada elenco."""
    import casamento as K
    idx = K.IndiceJogadores(banco)
    nt = N.nivel_times(banco)
    perfis = {}
    for arq in glob.glob(os.path.join(tm.cache, "players", "*.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if "marketValue" in d and d.get("id"):
            perfis[str(d["id"])] = d
    pares = []
    for arq in glob.glob(os.path.join(tm.cache, "clubs", "*.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                sq = json.load(f)
        except (OSError, ValueError):
            continue
        if "players" not in sq or "season_id" in (sq.get("_brfp") or {}).get("consulta", ""):
            continue                                     # só elencos atuais (o valor do perfil é o de hoje)
        casados = []
        for p in sq["players"]:
            pr = perfis.get(str(p["id"]))
            if not pr or not pr.get("marketValue") or not p.get("dateOfBirth"):
                continue
            cand = idx.buscar(p.get("name"), pr.get("fullName") or "", "", p["dateOfBirth"], None, minimo=0.9)
            if cand:
                casados.append((cand[0][1], pr))
        votos = collections.Counter(t for pid, _ in casados for t in idx.times_de.get(pid, []) if t in nt)
        if not votos:
            continue
        time_banco, n = votos.most_common(1)[0]
        if n < 8:
            continue
        for pid, pr in casados:
            if time_banco in idx.times_de.get(pid, []):
                pares.append({"overall": idx.info[pid]["overall"], "valor": pr["marketValue"], "idade": pr.get("age"), "time": time_banco})
    r = N.calibrar_tm(pares)
    if not r:
        return None
    r["origem"] = f"cache da Transfermarkt: {r['amostra']} jogadores de {r['times']} times"
    r["quando"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(N.CALIBRACAO_TM, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    return r


def aparencia_do_cache(api, banco, minimo=60):
    """Referências da aparência pela foto (aparencia_ref.json): jogadores do cache casados com o banco pelo nascimento,
    com a foto da API (baixada sem gastar chamadas) e os códigos de aparência deles no banco."""
    import aparencia as AP
    import apifutebol as A
    import casamento as K
    if not AP.disponivel():
        return {"erro": "sem OpenCV"}
    idx = K.IndiceJogadores(banco)
    pl = banco.tabela("players")
    c = {n: i for i, n in enumerate(pl.campos)}
    vistos, pares = set(), []
    pasta_img = os.path.join(api.cache, "img")
    for arq in glob.glob(os.path.join(api.cache, "players", "*.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                resp = A.consertar(json.load(f)).get("response") or []
        except (OSError, ValueError):
            continue
        for r in resp:
            p = r["player"]
            if p["id"] in vistos or not p.get("photo") or not (p.get("birth") or {}).get("date"):
                continue
            vistos.add(p["id"])
            cand = idx.buscar(p.get("name"), p.get("firstname") or "", p.get("lastname") or "", p["birth"]["date"], p.get("age"), minimo=0.9)
            if not cand:
                continue
            l = idx.linhas[cand[0][1]]
            try:
                an = AP.analisar_url(p["photo"], A.baixar, pasta_img, int(l[c["gender"]]) if "gender" in c else 0)
            except Exception:  # noqa: BLE001
                continue
            if "medidas" not in an or not an["medidas"]["achou_rosto"]:
                continue
            pares.append({"medidas": an["medidas"], "genero": int(l[c["gender"]]) if "gender" in c else 0,
                          "generico": l[c["hashighqualityhead"]] == "0", **{k: l[c[k]] for k in ("skintonecode", "haircolorcode", "hairtypecode",
                                                                                                  "facialhairtypecode")}})
    if len(pares) < minimo:
        return {"erro": f"só {len(pares)} jogadores com foto casados com o banco (precisa de {minimo}): ficou a referência anterior"}
    ref = AP.calibrar(pares)
    ref["origem"] = f"cache da API: {len(pares)} jogadores com foto"
    with open(AP.REF, "w", encoding="utf-8") as f:
        json.dump(ref, f, ensure_ascii=False)
    return {k: v for k, v in ref.items() if k != "refs"}
