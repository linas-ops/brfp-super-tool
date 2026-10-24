"""Nomes e pastas dos kits do FC 27 (sem numpy: usado também pela interface).

Um kit exportado pelo FET fica em kit_<faixa de 500>/<time>_<teamid>/<tipo>_<n>_<v>, com jersey/, shorts/, socks/ e o
hotspots_<teamid>_<n>_<v>.hotspot; cada arquivo leva o sufixo <teamid>_<n>_<v>.
"""
import glob
import os
import re
import unicodedata

PECAS = ("jersey", "shorts", "socks")
TIPOS = {"home": 0, "away": 1, "goalie_home": 2, "third": 3, "fourth": 4}
NOME_TIPO = {"home": "1º uniforme", "away": "2º uniforme", "goalie_home": "Goleiro", "third": "3º uniforme",
             "fourth": "4º uniforme"}


class ErroConversao(Exception):
    pass


def nome_pasta(nome):
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "time"


def destino_kit(saida, teamid, time_, tipo, variacao=0):
    """(pasta, caminho relativo, sufixo) do kit no formato do jogo."""
    tid = int(teamid)
    n = TIPOS[tipo]
    v = int(variacao or 0)
    rel = f"kit_{tid // 500 * 500}/{nome_pasta(time_)}_{tid}/{tipo}_{n}_{v}"
    return os.path.join(os.path.abspath(saida), *rel.split("/")), rel, f"{tid}_{n}_{v}"


def arquivos_base(pasta):
    """Arquivos de um kit exportado (pasta <tipo>_<n>_<v> com jersey/, shorts/, socks/ e o .hotspot)."""
    pasta = os.path.abspath(pasta or "")
    if not os.path.isdir(pasta):
        raise ErroConversao(f"A pasta do kit base não existe: {pasta}")
    hs = glob.glob(os.path.join(pasta, "hotspots_*.hotspot"))
    m = re.match(r"hotspots_(\d+)_(\d+)_(\d+)\.hotspot$", os.path.basename(hs[0])) if hs else None
    if not m:
        raise ErroConversao("A pasta do kit base tem que ser a de um kit exportado pelo FET (home_0_0, away_1_0…, com "
                            f"jersey/, shorts/, socks/ e o hotspots_<id>_<n>_<v>.hotspot): {pasta}")
    tid, n, v = m.groups()
    suf = f"{tid}_{n}_{v}"
    arqs = {"hotspot": hs[0], "teamid": int(tid), "n": int(n), "v": int(v), "pasta": pasta, "sufixo": suf, "outros": [],
            "tipo": next((k for k, x in TIPOS.items() if x == int(n)), None),
            "time": re.sub(r"_\d+$", "", os.path.basename(os.path.dirname(pasta)))}
    for peca in PECAS:
        sub = os.path.join(pasta, peca)
        cor = os.path.join(sub, f"{peca}_{suf}_color.png")
        if not os.path.isfile(cor):
            raise ErroConversao(f"Falta {peca}/{os.path.basename(cor)} no kit base.")
        arqs[peca] = cor
        for f in sorted(glob.glob(os.path.join(sub, "*.png"))):
            if os.path.normcase(f) != os.path.normcase(cor):
                arqs["outros"].append(f)
    return arqs


def raiz_kits(pasta_kit):
    """A pasta kit do mod (acima de kit_<faixa>) a partir da pasta de um kit, ou None."""
    p = os.path.abspath(pasta_kit or "")
    for _ in range(4):
        if re.match(r"kit_\d+$", os.path.basename(p), re.I):
            return os.path.dirname(p)
        p = os.path.dirname(p)
    return None


def times_na_raiz(raiz, limite=6000):
    """Times que já têm pasta na raiz dos kits: [{"time", "teamid", "tipos": [...]}] (para sugerir na interface)."""
    out = []
    try:
        faixas = [d for d in os.listdir(raiz) if re.match(r"kit_\d+$", d, re.I)]
    except OSError:
        return out
    for f in faixas:
        try:
            nomes = os.listdir(os.path.join(raiz, f))
        except OSError:
            continue
        for d in nomes:
            m = re.match(r"(.+)_(\d+)$", d)
            if m and os.path.isdir(os.path.join(raiz, f, d)):
                try:
                    tipos = sorted(x for x in os.listdir(os.path.join(raiz, f, d)) if re.match(r"[a-z_]+_\d+_\d+$", x))
                except OSError:
                    tipos = []
                out.append({"time": m.group(1), "teamid": int(m.group(2)), "tipos": tipos})
                if len(out) >= limite:
                    return sorted(out, key=lambda x: x["time"])
    return sorted(out, key=lambda x: x["time"])


def tipo_pelo_nome(caminho):
    """Tipo do kit pelo nome do arquivo do PES (u0101p1 = 1º uniforme, p2 = 2º, g1 = goleiro…) ou None."""
    n = os.path.splitext(os.path.basename(caminho))[0].lower()
    m = re.search(r"(?:^|[^a-z])(?:u\d+)?([pg])([1-9])(?![0-9])", n) or re.search(r"\d([pg])([1-9])(?![0-9])", n)
    if m:
        if m.group(1) == "g":
            return "goalie_home"
        return {"1": "home", "2": "away", "3": "third", "4": "fourth"}.get(m.group(2))
    for chave, tipo in (("goalie", "goalie_home"), ("gk", "goalie_home"), ("goleiro", "goalie_home"), ("away", "away"),
                        ("third", "third"), ("fourth", "fourth"), ("home", "home")):
        if re.search(r"(?:^|[^a-z])" + chave + r"(?:[^a-z]|$)", n):
            return tipo
    return None
