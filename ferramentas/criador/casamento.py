"""Criador de Ligas e Times — acha no banco do jogo o jogador e o time que correspondem a um da API-Football.

Jogadores: nascimento (quando a API dá) + nome; sem nascimento (elenco atual, seleções), idade + nome, com
preferência pelo time onde o jogador já está no banco. Times: nome sem as palavras genéricas (FC, Esporte Clube…)
+ país. O mapa API -> ids do jogo (dados/criador_mapa.json) vale antes de qualquer comparação de nomes.
"""
import datetime
import difflib
import json
import os
import re
import unicodedata

BASE_DATA = datetime.date(1582, 10, 14)
MAPA = os.path.join(os.environ.get("BRFP_DADOS") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dados"), "criador_mapa.json")
GENERICAS = {"fc", "sc", "ec", "ac", "cf", "cd", "ud", "sd", "afc", "club", "clube", "clubs", "esporte", "esportes", "futebol",
             "football", "futbol", "de", "da", "do", "das", "dos", "del", "la", "el", "e", "y", "and", "the", "regatas", "sport",
             "sporting", "sociedade", "esportiva", "associacao", "atletico", "athletic", "calcio", "us", "ss", "as", "ca",
             "cr", "rc", "sv", "fk", "nk", "sk", "if", "bk", "kv", "kaa", "krc", "tsg", "vfb", "vfl", "1", "w", "women",
             "feminino", "fem", "femenino", "ladies", "frauen", "wfc", "lfc", "foot", "ball", "futebol", "clube", "fútbol",
             "fussball", "verein", "spvgg", "tsv", "fsv", "esporte", "desportivo", "deportivo", "recreativo", "cultural"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def tokens(*textos):
    out = set()
    for t in textos:
        out |= {w for w in norm(t).split() if len(w) > 1}
    return out


def ler_mapa():
    try:
        with open(MAPA, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        m = {}
    for k in ("times", "jogadores", "ligas", "selecoes", "tm_times", "tm_jogadores"):
        m.setdefault(k, {})
    return m


def gravar_mapa(m):
    os.makedirs(os.path.dirname(MAPA), exist_ok=True)
    with open(MAPA + ".tmp", "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)
    os.replace(MAPA + ".tmp", MAPA)


def idade_em(dias, hoje=None):
    try:
        n = BASE_DATA + datetime.timedelta(days=int(dias))
    except (TypeError, ValueError):
        return None
    hoje = hoje or datetime.date.today()
    return hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))


# partículas e sufixos que não identificam ninguém: "da", "de", "Júnior", "Filho"… (antes, "Gabriel da Silva" e
# "João da Silva" nascidos no mesmo dia casavam só pelo "da" e pela data)
PARTICULAS = {"de", "da", "do", "das", "dos", "del", "della", "di", "du", "la", "le", "lo", "van", "von", "der", "den", "ter",
              "el", "al", "e", "y", "jr", "junior", "filho", "neto", "sobrinho", "bin", "ben", "ibn", "mc", "st", "dei", "des"}


def significativas(tk):
    return {w for w in tk if w not in PARTICULAS and len(w) >= 2}


def _parecida(a, b):
    """Mesma palavra, uma é o começo da outra ("vini"/"vinicius") ou grafia vizinha ("mohamed"/"mohammed")."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    return min(len(a), len(b)) >= 5 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.84


def _batem(de, em):
    """Quantas palavras de `de` têm uma parecida em `em`."""
    return sum(1 for a in de if any(_parecida(a, b) for b in em))


def _sem_inicial(nome):
    return re.sub(r"^[A-Za-zÀ-ÿ]{1,2}\.\s*", "", nome or "")       # "R. Rios" -> "Rios"


# nomes de países que mudam entre as fontes e o banco (nations.nationname)
ALIAS_NACOES = {"usa": "united states", "south korea": "korea republic", "korea south": "korea republic", "korea north": "korea dpr",
                "ivory coast": "cote d ivoire", "czechia": "czech republic", "bosnia": "bosnia and herzegovina",
                "bosnia herzegovina": "bosnia and herzegovina", "dr congo": "congo dr", "north macedonia": "fyr macedonia",
                "turkiye": "turkey", "tuerkiye": "turkey", "cape verde islands": "cape verde", "cabo verde": "cape verde",
                "china": "china pr", "ireland": "republic of ireland", "st kitts nevis": "st kitts and nevis",
                "holland": "netherlands"}


def mapa_nacoes(banco):
    """{nome normalizado ou "iso:XX": nationid} das nações do banco (com os apelidos das fontes)."""
    out = {}
    for d in banco.tabela("nations").dicts():
        out[norm(d["nationname"])] = d["nationid"]
        if d.get("isocountrycode"):
            out["iso:" + d["isocountrycode"].upper()] = d["nationid"]
    for apelido, nome in ALIAS_NACOES.items():
        if nome in out and apelido not in out:
            out[apelido] = out[nome]
    return out


def nacoes_de(mapa, nomes):
    """Ids de nação (sem o Resto do Mundo) dos nomes de país de um jogador da fonte."""
    out = []
    for n in nomes or []:
        i = mapa.get(norm(n)) if n else None
        if i and str(i) != "211" and i not in out:
            out.append(i)
    return out


class IndiceJogadores:
    """Jogadores do banco indexados por palavra do nome e por data de nascimento."""

    def __init__(self, banco):
        pl = banco.tabela("players")
        c = {n: i for i, n in enumerate(pl.campos)}
        self.c = c
        self.linhas = {}
        self.info = {}
        self.por_palavra = {}
        self.por_nascimento = {}
        self.times_de = {}
        for d in banco.tabela("teamplayerlinks").dicts():
            self.times_de.setdefault(d["playerid"], []).append(d["teamid"])
        hoje = datetime.date.today()
        for l in pl.linhas:
            pid = l[c["playerid"]]
            j = banco.jogador(dict(zip(pl.campos, l)))
            tk = tokens(j["comum"], j["primeiro"], j["sobrenome"], j["camisa"])
            sig = significativas(tk)
            exib = significativas(tokens(j["comum"]) or tokens(j["primeiro"], j["sobrenome"])) or sig
            self.linhas[pid] = l
            self.info[pid] = {"playerid": pid, "nome": j["nome"], "primeiro": j["primeiro"], "sobrenome": j["sobrenome"],
                              "comum": j["comum"], "camisa": j["camisa"], "tokens": tk, "sig": sig, "sig_exibido": exib,
                              "nascimento": l[c["birthdate"]], "idade": idade_em(l[c["birthdate"]], hoje),
                              "nacao": l[c["nationality"]], "genero": l[c["gender"]] if "gender" in c else "0",
                              "overall": int(l[c["overallrating"]]), "pos": int(l[c["preferredposition1"]])}
            for w in sig:
                self.por_palavra.setdefault(w, set()).add(pid)
            self.por_nascimento.setdefault(l[c["birthdate"]], set()).add(pid)

    def nome_bate(self, pid, nome, primeiro="", sobrenome=""):
        """O nome da fonte é o deste jogador do banco? Uma palavra comum nos dois lados ("Silva") não basta."""
        j = self.info[pid]
        n_nome = norm(nome)
        exibidos = {norm(j["comum"]), norm(j["camisa"]), norm(f"{j['primeiro']} {j['sobrenome']}")} - {""}
        if n_nome and n_nome in exibidos:
            return True
        a = significativas(tokens(_sem_inicial(nome)))
        f = significativas(tokens(nome, primeiro, sobrenome))
        if not a or not j["sig"]:
            return False
        m1 = _batem(a, j["sig"])
        if m1 == len(a) and (len(a) >= 2 or any(_parecida(next(iter(a)), w) for w in j["sig_exibido"])):
            return True                                    # todo o nome da fonte está no do banco
        d = j["sig_exibido"]
        m2 = _batem(d, f)
        if m2 == len(d) and (len(d) >= 2 or len(next(iter(d))) >= 4):
            return True                                    # todo o nome do banco está no da fonte ("Gabriel Jesus";
                                                           # "Isabela" no nome completo da "Belinha")
        return m1 >= 2 and m1 / len(a) >= 0.5 and m2 / max(1, len(d)) >= 0.5

    def buscar(self, nome, primeiro="", sobrenome="", nascimento=None, idade=None, nacao=None, genero=None, times_pref=(),
               minimo=0.55, so_nacao=False, nacoes=None):
        """[(nota 0..1, playerid)] dos candidatos, o melhor primeiro. A data de nascimento só confirma quem tem o mesmo
        nome; nacoes (ids do banco das nacionalidades na fonte): uma nação diferente de todas pesa contra."""
        tk_api = significativas(tokens(nome, primeiro, sobrenome))
        tk_nome = significativas(tokens(_sem_inicial(nome)))
        cand = set()
        for w in tk_api:
            cand |= self.por_palavra.get(w, set())
        nasc = None
        if nascimento:
            try:
                nasc = str((datetime.date.fromisoformat(str(nascimento)[:10]) - BASE_DATA).days)
            except ValueError:
                nasc = None
        if nasc:
            cand |= self.por_nascimento.get(nasc, set())   # grafias diferentes ("Vini Jr." / "Vinícius Júnior")
        out = []
        n_nome = norm(nome)
        pref = {str(t) for t in times_pref or ()}
        nacs = {str(x) for x in (nacoes or []) if x and str(x) != "211"}
        if nacao and not nacs:
            nacs = {str(nacao)}
        for pid in cand:
            j = self.info[pid]
            if genero is not None and str(j["genero"]) != str(genero):
                continue
            if so_nacao and nacao and str(j["nacao"]) != str(nacao):
                continue
            if not _batem(tk_api, j["sig"]):
                continue
            exibidos = {norm(j["comum"]), norm(j["camisa"]), norm(f"{j['primeiro']} {j['sobrenome']}")} - {""}
            if n_nome and n_nome in exibidos:
                sc = 0.95                                      # o mesmo nome que o jogo mostra
            elif len(tk_nome) >= 2 and _batem(tk_nome, j["sig"]) == len(tk_nome):
                sc = 0.85                                      # todas as palavras do nome da fonte
            elif len(tk_nome) == 1:
                w = next(iter(tk_nome))
                # nome de uma palavra só ("Bruno", "Arthur"): sozinho só vale se for o nome comum/da camisa no banco
                sc = 0.85 if w in {norm(j["comum"]), norm(j["camisa"])} else 0.55 if w == norm(j["primeiro"]).split(" ")[0] else 0.45
            else:
                sc = 0.7 * _batem(tk_nome, j["sig"]) / max(1, len(tk_nome))
            if primeiro or sobrenome:                          # nome completo (perfil da fonte): reforça ou enfraquece
                completo = significativas(tokens(primeiro, sobrenome))
                sc += 0.1 * (_batem(completo, j["sig"]) / max(1, len(completo)) - 0.5)
            if nasc is not None:
                if j["nascimento"] == nasc:
                    if self.nome_bate(pid, nome, primeiro, sobrenome):
                        sc = max(sc, 0.75) + 0.3
                    else:                                      # mesma data, nome diferente: no máximo "confira"
                        sc = min(sc + 0.15, 0.84)
                else:
                    d = abs(int(j["nascimento"]) - int(nasc))
                    sc -= 0.15 if d <= 400 else 0.5
            elif idade is not None and j["idade"] is not None:
                d = abs(j["idade"] - int(idade))
                sc -= 0 if d <= 1 else (0.2 if d == 2 else 0.6)
            if nacs and str(j["nacao"]) != "211":
                sc += 0.05 if str(j["nacao"]) in nacs else -0.3
            no_time = bool(pref and set(self.times_de.get(pid, ())) & pref)
            if no_time:
                sc += 0.25
            elif pref and len(tk_nome) <= 1 and nasc is None:
                sc = min(sc, 0.8)                              # nome curto em outro clube: fica para o usuário confirmar
            if sc >= minimo:
                out.append((round(min(1.0, sc), 3), pid))
        out.sort(key=lambda x: (-x[0], -self.info[x[1]]["overall"]))
        return out


# siglas que a API usa no lugar do nome (estados brasileiros, "Utd"…)
SIGLAS = {"mg": "mineiro", "pr": "paranaense", "go": "goianiense", "sp": "paulista", "rj": "carioca", "rs": "gaucho",
          "ba": "baiano", "pe": "pernambucano", "ce": "cearense", "sc": "catarinense", "pa": "paraense", "am": "amazonense",
          "mt": "matogrossense", "ms": "sulmatogrossense", "es": "capixaba", "al": "alagoano", "se": "sergipano",
          "pb": "paraibano", "rn": "potiguar", "pi": "piauiense", "ma": "maranhense", "df": "brasiliense",
          "utd": "united", "st": "saint"}


def _sig(nome):
    tk = tokens(nome)
    tk |= {SIGLAS[w] for w in tk if w in SIGLAS}
    return {w for w in tk if w not in GENERICAS and w not in SIGLAS and len(w) >= 3}, tk


def nota_time(nome_api, nome_db):
    """0..1: palavras que identificam o time (sem FC, Esporte Clube… e com as siglas de estado por extenso) em comum,
    pela média de "quantas do menor nome" e "quantas do maior" — "Atletico-MG" casa com "Atlético Mineiro" (1,0) antes
    de "América-MG" (0,75)."""
    a, ta = _sig(nome_api)
    b, tb = _sig(nome_db)
    if a and b:
        inter = len(a & b) + 0.8 * sum(1 for x in a - b for y in b - a if min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x)))
        return round(min(1.0, (inter / min(len(a), len(b)) + inter / max(len(a), len(b))) / 2), 3)
    if not ta or not tb:
        return 0.0
    seq = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return round(seq * 0.85, 3)


def casar_times(times_api, times_db, mapa=None, minimo=0.6, desempate=None):
    """times_api: [{id, nome}], times_db: [{teamid, nome}] -> {id_api: (teamid, nota, origem)} (um time do banco para
    cada time da API, os pares mais parecidos primeiro). desempate(time_api, [teamids]) -> {teamid: 0..1} (fração do
    elenco em comum) é chamado só quando há dois candidatos parecidos; o elenco pesa mais que o nome."""
    mapa = mapa or {}
    out = {}
    usados = set()
    db_ids = {t["teamid"] for t in times_db}
    for t in times_api:
        tid = mapa.get(str(t["id"]))
        if tid and tid in db_ids:
            out[t["id"]] = (tid, 1.0, "mapa")
            usados.add(tid)
    pares = []
    elenco = {}
    for t in times_api:
        if t["id"] in out:
            continue
        cands = sorted(((nota_time(t["nome"], d["nome"]), d["teamid"]) for d in times_db if d["teamid"] not in usados), reverse=True)
        cands = [c for c in cands if c[0] >= minimo]
        if desempate and len(cands) >= 2 and cands[0][0] - cands[1][0] < 0.3:
            try:
                fr = desempate(t, [tid for _, tid in cands[:4]]) or {}
            except Exception:  # noqa: BLE001 — sem o elenco, fica o nome
                fr = {}
            if any(fr.values()):
                elenco[t["id"]] = fr
                cands = [(round(n + 0.6 * fr.get(tid, 0), 3), tid) for n, tid in cands]
        pares += [(n, t["id"], tid) for n, tid in cands]
    pares.sort(key=lambda x: -x[0])
    for n, ida, tid in pares:
        if ida in out or tid in usados:
            continue
        out[ida] = (tid, min(1.0, n), "elenco" if ida in elenco and elenco[ida].get(tid) else "nome")
        usados.add(tid)
    return out
