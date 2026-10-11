"""Criador de Ligas e Times — notas dos jogadores gerados, calibradas no próprio banco do jogo.

Tudo sai do banco importado no Super Tool (Dados do jogo):
- perfil de atributos por posição e faixa de nota (mediana dos jogadores do banco);
- a fórmula da nota geral de cada posição (regressão dos atributos -> overallrating, R² ≈ 1);
- altura, peso, dribles (skillmoves) e perna ruim típicos por posição e nota;
- o nível de cada liga do banco (média dos 14 mais fortes de cada time).

A nota geral de um jogador = nível do time + ajuste pelas estatísticas da temporada (nota média da API, minutos,
idade), com coeficientes calibrados casando jogadores da API com os mesmos jogadores no banco (calibracao.json;
refeito com tudo o que estiver no cache da API). Depois os atributos partem do perfil da posição, recebem os ajustes
das estatísticas (gols -> finalização, desarmes -> marcação…) e são acertados para dar exatamente a nota geral.
"""
import datetime
import hashlib
import json
import math
import os

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
CALIBRACAO = os.path.join(AQUI, "calibracao.json")
BASE_DATA = datetime.date(1582, 10, 14)
ATR = ["acceleration", "sprintspeed", "agility", "balance", "jumping", "stamina", "strength", "reactions", "aggression",
       "composure", "interceptions", "positioning", "vision", "ballcontrol", "crossing", "dribbling", "finishing",
       "freekickaccuracy", "headingaccuracy", "longpassing", "shortpassing", "defensiveawareness", "shotpower", "longshots",
       "standingtackle", "slidingtackle", "volleys", "curve", "penalties", "gkdiving", "gkhandling", "gkkicking",
       "gkreflexes", "gkpositioning"]
GK_ATR = ["gkdiving", "gkhandling", "gkkicking", "gkreflexes", "gkpositioning"]
BASES = [0, 2, 3, 5, 7, 8, 10, 12, 14, 16, 18, 21, 23, 25, 27]
NOME_POS = {0: "GOL", 2: "ALD", 3: "LD", 5: "ZAG", 7: "LE", 8: "ALE", 10: "VOL", 12: "MD", 14: "MC", 16: "ME", 18: "MEI",
            21: "SA", 23: "PD", 25: "ATA", 27: "PE"}
SIGLA_POS = {0: "GK", 2: "RWB", 3: "RB", 5: "CB", 7: "LB", 8: "LWB", 10: "CDM", 12: "RM", 14: "CM", 16: "LM", 18: "CAM",
             21: "CF", 23: "RW", 25: "ST", 27: "LW"}
GRUPO_POS = {0: "G", 2: "D", 3: "D", 5: "D", 7: "D", 8: "D", 10: "M", 12: "M", 14: "M", 16: "M", 18: "M", 21: "F", 23: "F",
             25: "F", 27: "F"}
# coeficientes iniciais (Série A 2024 x banco BRFP 27: erro médio 2,5 com o time de fora da amostra)
COEF_PADRAO = {"interc": -1.83, "share": 1.70, "nota": 3.26, "sem_nota": -3.60, "jovem": 1.15, "veterano": 0.16,
               "amostra": 170, "erro_medio": 2.52, "origem": "Série A 2024 (5 times)"}
# Transfermarkt: nota = a + b·log10(valor de mercado) + idade (Série A 2026, 6 times, 147 jogadores casados pelo
# nascimento com o banco BRFP 27: erro médio 1,71 com o time de fora da amostra; esticar não melhora)
CALIBRACAO_TM = os.path.join(AQUI, "calibracao_tm.json")
COEF_TM_PADRAO = {"a": 35.97, "valor": 5.67, "jovem": 2.06, "veterano": 1.30, "amostra": 147, "erro_medio": 1.71,
                  "origem": "Série A 2026 (6 times) — valor de mercado da Transfermarkt"}


def dias(data_iso):
    try:
        return (datetime.date.fromisoformat(str(data_iso)[:10]) - BASE_DATA).days
    except (TypeError, ValueError):
        return None


def data_de_dias(n):
    return BASE_DATA + datetime.timedelta(days=int(n))


def semente(*partes):
    """Número estável (0..1) para escolhas 'aleatórias' que se repetem igual a cada geração."""
    h = hashlib.sha1("|".join(str(p) for p in partes).encode()).digest()
    return int.from_bytes(h[:6], "big") / float(1 << 48)


class Perfil:
    """Estatísticas do banco usadas para gerar jogadores."""

    def __init__(self, banco):
        pl = banco.tabela("players")
        self.campos = pl.campos
        c = {n: i for i, n in enumerate(pl.campos)}
        self.c = c
        self.atr = [a for a in ATR if a in c]
        linhas = pl.linhas
        arr = np.array([[int(l[c[a]]) for a in self.atr] for l in linhas], dtype=float)
        ov = np.array([int(l[c["overallrating"]]) for l in linhas], dtype=float)
        pos = np.array([int(l[c["preferredposition1"]]) for l in linhas])
        gen = np.array([int(l[c["gender"]]) if "gender" in c else 0 for l in linhas])
        alt = np.array([int(l[c["height"]]) for l in linhas], dtype=float)
        pes = np.array([int(l[c["weight"]]) for l in linhas], dtype=float)
        sm = np.array([int(l[c["skillmoves"]]) for l in linhas], dtype=float) if "skillmoves" in c else None
        wf = np.array([int(l[c["weakfootabilitytypecode"]]) for l in linhas], dtype=float) if "weakfootabilitytypecode" in c else None
        self.linhas = linhas
        self.modelos = {}       # (genero, pos) -> dict
        for g in (0, 1):
            for p in BASES:
                m = (pos == p) & (gen == g)
                if m.sum() < 25:
                    m = pos == p
                if m.sum() < 25:
                    continue
                A, y = arr[m], ov[m]
                X = np.hstack([A, np.ones((len(A), 1))])
                w, *_ = np.linalg.lstsq(X, y, rcond=None)
                pesos = w[:-1].copy()
                pesos[np.abs(pesos) < 0.01] = 0.0
                faixas = {}
                for centro in range(40, 95, 3):
                    sel = np.abs(y - centro) <= 3
                    if sel.sum() >= 8:
                        faixas[centro] = {"atr": np.median(A[sel], axis=0), "sm": float(np.median(sm[m][sel])) if sm is not None else 2,
                                          "wf": float(np.median(wf[m][sel])) if wf is not None else 3}
                self.modelos[(g, p)] = {"pesos": pesos, "vies": float(w[-1]), "faixas": faixas,
                                        "altura": float(np.median(alt[m])), "peso": float(np.median(pes[m])),
                                        "alt_sd": float(np.std(alt[m])) or 5.0}
        # jogadores-base (campos diversos) e aparência, sem cabeça real
        self.base_por_pos = {}
        hq = c.get("hashighqualityhead")
        for l in linhas:
            if hq is not None and l[hq] == "1":
                continue
            chave = (int(l[c["gender"]]) if "gender" in c else 0, int(l[c["preferredposition1"]]))
            self.base_por_pos.setdefault(chave, []).append(l)
        for v in self.base_por_pos.values():
            v.sort(key=lambda l: int(l[c["overallrating"]]))
        # doadores de aparência: genéricos "completos" (tipo de cabeça, corpo padrão e linha de pele em skins); jogadores
        # criados à mão no banco às vezes ficam sem isso e dariam uma cabeça incompleta
        try:
            com_pele = set(banco.tabela("skins").valores("assetid")) if banco.tem("skins") else None
        except Exception:  # noqa: BLE001
            com_pele = None

        def completo(l):
            if "headtypecode" in c and l[c["headtypecode"]] == "0":
                return False
            if "bodytypecode" in c and int(l[c["bodytypecode"]] or 0) >= 100:
                return False
            return com_pele is None or "headassetid" not in c or l[c["headassetid"]] in com_pele
        self.aparencia = {}
        self.aparencia_genero = {0: [], 1: []}
        for l in linhas:
            if hq is not None and l[hq] == "1" or not completo(l):
                continue
            g = int(l[c["gender"]]) if "gender" in c else 0
            self.aparencia.setdefault((g, l[c["nationality"]]), []).append(l)
            self.aparencia_genero.setdefault(g, []).append(l)
        # confederação de cada nação (para achar uma aparência parecida quando a nação não tem jogadores genéricos)
        self.confed = {}
        try:
            for d in banco.tabela("nations").dicts():
                self.confed[d["nationid"]] = d.get("confederation")
        except Exception:  # noqa: BLE001
            pass

    # ---- consultas
    def modelo(self, pos, genero=0):
        return self.modelos.get((genero, pos)) or self.modelos.get((0, pos)) or self.modelos[(0, 14)]

    def perfil_atributos(self, pos, overall, genero=0):
        """Mediana dos atributos na faixa de nota (interpolada entre as faixas vizinhas)."""
        fx = self.modelo(pos, genero)["faixas"]
        centros = sorted(fx)
        if overall <= centros[0]:
            return fx[centros[0]], centros[0]
        if overall >= centros[-1]:
            return fx[centros[-1]], centros[-1]
        for a, b in zip(centros, centros[1:]):
            if a <= overall <= b:
                t = (overall - a) / (b - a)
                return {"atr": fx[a]["atr"] * (1 - t) + fx[b]["atr"] * t, "sm": fx[a]["sm"] * (1 - t) + fx[b]["sm"] * t,
                        "wf": fx[a]["wf"] * (1 - t) + fx[b]["wf"] * t}, overall
        return fx[centros[-1]], centros[-1]

    def overall_de(self, atributos, pos, genero=0):
        m = self.modelo(pos, genero)
        return float(np.dot(m["pesos"], atributos) + m["vies"])

    def jogador_base(self, pos, overall, genero, chave):
        lista = self.base_por_pos.get((genero, pos)) or self.base_por_pos.get((0, pos)) or self.base_por_pos[(0, 14)]
        perto = [l for l in lista if abs(int(l[self.c["overallrating"]]) - overall) <= 2] or lista
        return perto[int(semente("base", chave) * len(perto)) % len(perto)]

    def aparencia_de(self, nacao, genero, chave, reserva=None, alvo=None):
        """Linha de um jogador genérico do banco para copiar a aparência: do mesmo gênero (nunca uma cabeça masculina
        numa jogadora), da mesma nação ou, sem ninguém dela, da mesma confederação. alvo = {campo: valor} vindo da
        foto (tom de pele, cor do cabelo, barba…): entre os candidatos, fica o mais parecido."""
        c = self.c
        lista = self.aparencia.get((genero, str(nacao))) or (self.aparencia.get((genero, str(reserva))) if reserva else None)
        if not lista:
            conf = self.confed.get(str(nacao))
            lista = [l for (g, n), ls in self.aparencia.items() if g == genero and conf and self.confed.get(n) == conf for l in ls]
        if not lista:
            lista = self.aparencia_genero.get(genero) or []
        if not lista:
            return None
        if alvo:
            def dist(l):
                d = 0.0
                for campo, (valor, peso) in alvo.items():
                    if campo not in c:
                        continue
                    v = int(l[c[campo]])
                    if campo == "skintonecode":
                        d += peso * abs(v - valor) / 10.0
                    elif campo == "facialhairtypecode":
                        d += peso * ((v != 0) != bool(valor))
                    else:
                        d += peso * (v != valor)
                return d
            # candidatos da nação primeiro; se ninguém dela combina com a foto, do gênero inteiro
            todos = lista if len(lista) >= 40 else lista + (self.aparencia_genero.get(genero) or [])
            melhor = min(dist(l) for l in todos)
            perto = [l for l in lista if dist(l) <= melhor + 0.01] or [l for l in todos if dist(l) <= melhor + 0.01]
            lista = perto
        return lista[int(semente("cara", chave) * len(lista)) % len(lista)]


# ------------------------------------------------------------------ nível das ligas e dos times
def nivel_times(banco):
    """{teamid: nível} = média dos 14 jogadores mais fortes de cada time do banco."""
    pl = banco.tabela("players")
    ip, io = pl.col("playerid"), pl.col("overallrating")
    ov = {l[ip]: int(l[io]) for l in pl.linhas}
    por_time = {}
    for d in banco.tabela("teamplayerlinks").dicts():
        o = ov.get(d["playerid"])
        if o:
            por_time.setdefault(d["teamid"], []).append(o)
    return {t: round(sum(sorted(v, reverse=True)[:14]) / min(14, len(v)), 1) for t, v in por_time.items() if len(v) >= 11}


def nivel_ligas(banco, idioma=None):
    """[{leagueid, nome, nivel, times, min, max}] das ligas do banco (sem ligas de seleções e sem contrato)."""
    nt = nivel_times(banco)
    por_liga = {}
    for d in banco.tabela("leagueteamlinks").dicts():
        if d["teamid"] in nt:
            por_liga.setdefault(d["leagueid"], []).append(nt[d["teamid"]])
    nomes = {d["leagueid"]: (idioma.liga(d["leagueid"]) if idioma else None) or d.get("leaguename") or f"Liga {d['leagueid']}"
             for d in banco.tabela("leagues").dicts()}
    out = []
    for lid, v in por_liga.items():
        if len(v) < 4:
            continue
        out.append({"leagueid": lid, "nome": nomes.get(lid, lid), "nivel": round(sum(v) / len(v), 1), "times": len(v),
                    "min": min(v), "max": max(v)})
    return sorted(out, key=lambda x: -x["nivel"])


def divisao_pelo_nome(nome):
    """Divisão aproximada pelo nome da liga da API ('Serie B' -> 2, 'Paulista - A2' -> 2…)."""
    n = (nome or "").lower()
    import re
    m = re.search(r"(?:serie|série|division|liga|league|tier)\s*([a-d])\b", n)
    if m:
        return "abcd".index(m.group(1)) + 1
    m = re.search(r"(?:-\s*|\b)(?:a)?([1-5])\s*$", n) or re.search(r"\b([1-5])\.\s", n)
    if m:
        return int(m.group(1))
    for chave, d in (("championship", 2), ("league one", 3), ("league two", 4), ("segunda", 2), ("primera b", 2),
                     ("2. bundesliga", 2), ("3. liga", 3), ("ligue 2", 2), ("serie b", 2), ("national", 3)):
        if chave in n:
            return d
    return 1


# ------------------------------------------------------------------ calibração (estatística da API -> nota do jogo)
def carregar_coef():
    try:
        with open(CALIBRACAO, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("interc") is not None:
            return {**COEF_PADRAO, **d}
    except (OSError, ValueError):
        pass
    return dict(COEF_PADRAO)


def feats(st, idade, jogos_temporada=38):
    st = st or {}
    mins = st.get("minutos") or 0
    share = min(1.0, mins / (max(10, jogos_temporada) * 90.0))
    tem = 1.0 if st.get("nota") and mins >= 180 else 0.0
    nota = (st["nota"] - 6.75) if tem else 0.0
    idade = idade or 25
    return {"share": share, "nota": nota * tem, "sem_nota": 1 - tem, "jovem": min(0, idade - 23), "veterano": max(0, idade - 31)}


def overall_estimado(nivel_time, st, idade, coef=None, jogos_temporada=38, arredondar=True):
    k = coef or carregar_coef()
    f = feats(st, idade, jogos_temporada)
    v = nivel_time + k["interc"] + sum(k[n] * f[n] for n in ("share", "nota", "sem_nota", "jovem", "veterano"))
    return int(round(max(40, min(92, v)))) if arredondar else v


def carregar_coef_tm():
    try:
        with open(CALIBRACAO_TM, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("a") is not None:
            return {**COEF_TM_PADRAO, **d}
    except (OSError, ValueError):
        pass
    return dict(COEF_TM_PADRAO)


def overall_tm(valor, idade, coef=None, arredondar=True):
    """Nota pelo valor de mercado (euros) e pela idade: jovens valem mais do que jogam (potencial) e veteranos menos."""
    k = coef or carregar_coef_tm()
    idade = idade or 25
    # o bônus de veterano para nos 35 anos: quase não há jogadores mais velhos na calibração (um goleiro de 39 com valor
    # baixo ganhava +10)
    v = k["a"] + k["valor"] * math.log10(max(10000.0, float(valor or 10000))) + k["jovem"] * min(0, idade - 23) \
        + k["veterano"] * max(0, min(idade, 35) - 31)
    return int(round(max(40, min(94, v)))) if arredondar else v


def calibrar_tm(pares):
    """pares: [{overall, valor, idade, time}] -> coeficientes (mínimos quadrados) e erro deixando cada time de fora."""
    X, y, g = [], [], []
    for p in pares:
        if not p.get("valor"):
            continue
        idade = p.get("idade") or 25
        X.append([1.0, math.log10(p["valor"]), min(0, idade - 23), max(0, min(idade, 35) - 31)])
        y.append(p["overall"])
        g.append(p["time"])
    if len(X) < 40:
        return None
    X, y = np.array(X), np.array(y, float)
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    erros = []
    for t in set(g):
        tr = [i for i, x in enumerate(g) if x != t]
        te = [i for i, x in enumerate(g) if x == t]
        if len(tr) < 30:
            continue
        wt, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        erros += list(np.abs(X[te] @ wt - y[te]))
    return {"a": float(w[0]), "valor": float(w[1]), "jovem": float(w[2]), "veterano": float(w[3]), "amostra": len(X),
            "erro_medio": round(float(np.mean(erros)), 2) if erros else None, "times": len(set(g))}


def potencial(overall, idade, chave):
    idade = idade or 25
    if idade <= 19:
        ganho = 10 + 4 * semente("pot", chave)
    elif idade <= 22:
        ganho = 6 + 4 * semente("pot", chave)
    elif idade <= 25:
        ganho = 3 + 4 * semente("pot", chave)
    elif idade <= 29:
        ganho = 1 + 2 * semente("pot", chave)
    else:
        ganho = 0
    return int(min(95, round(overall + ganho)))


def calibrar(pares, niveis):
    """pares: [{overall, time, st, idade}] -> coeficientes (mínimos quadrados) e erro médio deixando cada time de fora."""
    nomes = ("share", "nota", "sem_nota", "jovem", "veterano")
    X, y, grupos = [], [], []
    for p in pares:
        if p["time"] not in niveis:
            continue
        f = feats(p["st"], p["idade"])
        X.append([1.0] + [f[n] for n in nomes])
        y.append(p["overall"] - niveis[p["time"]])
        grupos.append(p["time"])
    if len(X) < 40:
        return None
    X, y = np.array(X), np.array(y)
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    erros = []
    for g in set(grupos):
        tr = [i for i, x in enumerate(grupos) if x != g]
        te = [i for i, x in enumerate(grupos) if x == g]
        if len(tr) < 30:
            continue
        wt, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        erros += list(np.abs(X[te] @ wt - y[te]))
    out = {"interc": float(w[0]), **{n: float(v) for n, v in zip(nomes, w[1:])}, "amostra": len(X),
           "erro_medio": round(float(np.mean(erros)), 2) if erros else None, "times": len(set(grupos))}
    return out


# ------------------------------------------------------------------ posições e atributos
def posicao_principal(j):
    """Posição do jogo: a da Transfermarkt (exata); senão a mais frequente nas escalações; senão, pela posição da API e
    estatísticas."""
    if j.get("posicao_tm") is not None:
        return int(j["posicao_tm"]), "Transfermarkt"
    pe = j.get("posicoes_escalacao") or {}
    if pe:
        return int(max(pe.items(), key=lambda kv: kv[1])[0]), "escalações"
    g = j.get("posicao_api")
    st = j.get("stats") or {}
    mins = max(1, st.get("minutos") or 0)
    p90 = lambda k: (st.get(k) or 0) * 90.0 / mins  # noqa: E731
    alt = j.get("altura") or 178
    if g == "G":
        return 0, "API"
    if g == "D":
        if (st.get("minutos") or 0) >= 270:                    # lateral cria mais (passes-chave e dribles) que zagueiro
            if p90("passes_chave") >= 0.8 or p90("dribles") >= 0.9:
                return None, "estatísticas"                    # lateral: o lado é decidido no time
            return 5, "estatísticas"
        return (5 if alt >= 182 else None), "API"
    if g == "M":
        if p90("desarmes") + p90("intercept") >= 3.2 and p90("passes_chave") < 1.2:
            return 10, "estatísticas"
        if p90("passes_chave") >= 1.6 or p90("gols") >= 0.25:
            return 18, "estatísticas"
        return 14, "API"
    if g == "F":
        if alt >= 182 or p90("dribles") < 1.2:
            return 25, "API"
        return None, "API"                                     # ponta: o lado é decidido no time
    return 14, "sem dados"


def distribuir_posicoes(jogadores):
    """Completa as posições indefinidas (lateral, ponta) equilibrando os lados do elenco."""
    cont = {}
    for j in jogadores:
        if j.get("pos") is not None:
            cont[j["pos"]] = cont.get(j["pos"], 0) + 1
    for j in jogadores:
        if j.get("pos") is not None:
            continue
        g = j.get("posicao_api")
        if g == "D":
            j["pos"] = 7 if cont.get(7, 0) < cont.get(3, 0) else 3
        elif g == "F":
            j["pos"] = 27 if cont.get(27, 0) < cont.get(23, 0) else 23
        else:
            j["pos"] = 14
        cont[j["pos"]] = cont.get(j["pos"], 0) + 1


def pe_preferido(j):
    """1 = direito, 2 = esquerdo (o jogo usa 1/2). Pelo lado em que atua nas escalações e pela posição."""
    if j.get("pe"):
        return j["pe"]
    lado = j.get("lado")
    pos = j.get("pos")
    if pos in (7, 8, 16):
        return 2 if semente("pe", j["id"]) < 0.8 else 1
    if pos == 23:                                             # ponta-direita: muitos são canhotos (perna invertida)
        return 2 if semente("pe", j["id"]) < 0.55 else 1
    if pos == 5 and lado == "E":
        return 2 if semente("pe", j["id"]) < 0.55 else 1
    return 2 if semente("pe", j["id"]) < 0.12 else 1


def gerar_atributos(perfil, j, overall, genero=0):
    """Atributos (dict) com a nota geral exata da posição, a partir do perfil + estatísticas + físico."""
    pos = j["pos"]
    base, _ = perfil.perfil_atributos(pos, overall, genero)
    a = dict(zip(perfil.atr, base["atr"].astype(float)))
    st = j.get("stats") or {}
    mins = st.get("minutos") or 0
    if mins >= 270:
        p90 = lambda k: (st.get(k) or 0) * 90.0 / mins  # noqa: E731

        def ajusta(campos, valor, ref, escala, limite=6, precisa=()):
            if st.get("_parcial") and any(k not in st for k in precisa):    # estatística que a fonte não dá: não mexe
                return
            d = max(-limite, min(limite, (valor - ref) * escala))
            for k in campos:
                if k in a:
                    a[k] += d
        if pos == 0:
            ajusta(("gkreflexes", "gkdiving"), p90("defesas"), 2.6, 2.2, precisa=("defesas",))
            ajusta(("gkpositioning", "gkhandling"), -p90("sofridos"), -1.2, 3.0, precisa=("sofridos",))
        else:
            ajusta(("finishing", "positioning", "volleys"), p90("gols"), {25: 0.42, 21: 0.38, 23: 0.25, 27: 0.25, 18: 0.2}.get(pos, 0.07), 14,
                   precisa=("gols",))
            ajusta(("shotpower", "longshots"), p90("chutes"), {25: 2.4, 23: 1.8, 27: 1.8, 18: 1.6}.get(pos, 0.8), 1.6, precisa=("chutes",))
            ajusta(("dribbling", "ballcontrol", "agility"), p90("dribles_certos"), {23: 1.6, 27: 1.6, 18: 1.2, 25: 0.9}.get(pos, 0.4), 2.6,
                   precisa=("dribles_certos",))
            ajusta(("vision", "shortpassing", "longpassing"), p90("passes_chave"), {18: 1.6, 14: 1.0, 23: 1.2, 27: 1.2}.get(pos, 0.6), 3.0,
                   precisa=("passes_chave",))
            ajusta(("crossing", "curve"), p90("assist"), {3: 0.08, 7: 0.08, 12: 0.12, 16: 0.12, 23: 0.15, 27: 0.15}.get(pos, 0.08), 18, 4,
                   precisa=("assist",))
            ajusta(("standingtackle", "slidingtackle", "defensiveawareness", "interceptions"),
                   p90("desarmes") + p90("intercept"), {5: 3.4, 10: 3.6, 3: 3.4, 7: 3.4, 14: 2.6}.get(pos, 1.2), 1.6,
                   precisa=("desarmes",))
            duelos = st.get("duelos") or 0
            if duelos >= 30:
                ajusta(("strength", "headingaccuracy", "jumping"), (st.get("duelos_ganhos") or 0) / duelos, 0.5, 18, 5)
            ajusta(("aggression",), p90("faltas"), 1.2, 4, 5, precisa=("faltas",))
        ajusta(("stamina",), min(1.0, mins / 3000.0), 0.6, 8, 5)
    # físico: altura/peso e idade
    m = perfil.modelo(pos, genero)
    alt = j.get("altura") or m["altura"]
    da = (alt - m["altura"]) / max(3.0, m["alt_sd"])
    for k, f in (("headingaccuracy", 3), ("jumping", 2), ("strength", 4), ("acceleration", -3), ("agility", -3), ("balance", -3)):
        if k in a and pos != 0:
            a[k] += max(-6, min(6, da * f))
    idade = j.get("idade") or 25
    if idade >= 30:
        for k in ("acceleration", "sprintspeed", "agility", "stamina"):
            if k in a:
                a[k] -= min(10, (idade - 29) * 1.6)
        for k in ("composure", "reactions", "vision"):
            if k in a:
                a[k] += min(5, (idade - 29) * 1.0)
    elif idade <= 21:
        for k in ("acceleration", "sprintspeed"):
            if k in a:
                a[k] += 2
        for k in ("composure", "reactions"):
            if k in a:
                a[k] -= 3
    # variação individual pequena (estável por jogador)
    for i, k in enumerate(perfil.atr):
        a[k] += (semente("var", j["id"], k) - 0.5) * 6
    # acerta para a nota geral alvo, mexendo só nos atributos que pesam na posição
    vet = np.array([a[k] for k in perfil.atr])
    pesos = m["pesos"]
    soma = pesos[pesos > 0].sum() or 1.0
    for _ in range(6):
        vet = np.clip(vet, 1, 99)
        dif = overall - perfil.overall_de(vet, pos, genero)
        if abs(dif) < 0.3:
            break
        vet = vet + np.where(pesos > 0, dif / soma, 0.0)
    vet = np.clip(np.round(vet), 1, 99).astype(int)
    out = dict(zip(perfil.atr, (int(x) for x in vet)))
    if pos != 0:
        for k in GK_ATR:
            if k in out:
                out[k] = int(min(out[k], 6 + int(semente("gk", j["id"], k) * 10)))
    out["skillmoves"] = int(max(1, min(5, round(base["sm"] + (0.6 if (st.get("dribles_certos") or 0) > 40 else 0)))))
    out["weakfootabilitytypecode"] = int(max(1, min(5, round(base["wf"]))))
    return out


def fisico(perfil, j, genero=0):
    m = perfil.modelo(j["pos"], genero)
    alt = j.get("altura")
    pes = j.get("peso")
    if not alt:
        alt = int(round(m["altura"] + (semente("alt", j["id"]) - 0.5) * 8))
    if not pes:
        pes = int(round(m["peso"] + (alt - m["altura"]) * 0.9 + (semente("peso", j["id"]) - 0.5) * 4))
    return int(max(150, min(208, alt))), int(max(50, min(110, pes)))
