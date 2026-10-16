"""Conversão de tabelas do banco entre jogos (FIFA 16 … FC 27) — motor do Conversor de Tabelas (biblioteca padrão).

Para cada tabela de origem escolhida, monta a tabela final no esquema do destino:
  - colunas com o mesmo nome: copiadas (com as regras de escala abaixo, quando o par de jogos tem regra);
  - colunas que só o destino tem: valor mais comum no destino (moda), ou o valor que o usuário fixar;
  - colunas que só a origem tem: descartadas (listadas no relatório);
  - inteiros fora da faixa do meta do destino: ajustados para a borda da faixa (contados no relatório);
  - textos maiores que o campo do destino: cortados (contados).
Regras de escala conhecidas (medidas nos bancos de cada versão; as do FC 26 -> FC 27 vêm do port BRFP 26 -> FC 27):
  qualquer -> FC 27: tom de pele ×10 (players/manager/referee.skintonecode, teams/competition.crowdskintonecode: 1..10 -> 10..100)
  FC 27 -> qualquer: tom de pele ÷10 (arredondado, 1..10)
  FIFA 21…FC 24 -> FIFA 16/FC 26/FC 27: skintypecode > 7 -> 0 (nesses jogos ele vai até ~151)
  FC 26 -> FC 27: facepsdlayer0/1 3 ou 4 -> 0
Colunas renomeadas: marking (até o FIFA 22) <-> defensiveawareness (FIFA 23 em diante).
Colunas de resumo (pacdiv, shohan, paskic, driref, defspe, phypos — FIFA 22 em diante): calculadas pelos atributos quando a
origem não tem.
"""
from collections import Counter

PESSOAS = ("players", "manager", "managers", "referee", "referees")
REGRAS = {
    ("fc26", "fc27"): [
        {"tabelas": PESSOAS, "coluna": "skintonecode", "tipo": "x10", "rotulo": "tom de pele ×10 (1..10 → 10..100)"},
        {"tabelas": ("teams", "competition"), "coluna": "crowdskintonecode", "tipo": "x10", "rotulo": "tom de pele da torcida ×10"},
        {"tabelas": PESSOAS, "coluna": "skintypecode", "tipo": "max7", "rotulo": "tipo de pele acima de 7 → 0"},
        {"tabelas": PESSOAS, "coluna": "facepsdlayer0", "tipo": "psd34", "rotulo": "camada 3/4 → 0 (quase extintas no FC 27)"},
        {"tabelas": PESSOAS, "coluna": "facepsdlayer1", "tipo": "psd34", "rotulo": "camada 3/4 → 0 (quase extintas no FC 27)"},
    ],
    ("fc27", "fc26"): [
        {"tabelas": PESSOAS, "coluna": "skintonecode", "tipo": "d10", "rotulo": "tom de pele ÷10 (10..100 → 1..10)"},
        {"tabelas": ("teams", "competition"), "coluna": "crowdskintonecode", "tipo": "d10", "rotulo": "tom de pele da torcida ÷10"},
    ],
}


SKINTYPE_LARGO = {"fifa21", "fifa22", "fifa23", "fc24", "fc25"}     # skintypecode até ~151
SKINTYPE_CURTO = {"fifa16", "fc26", "fc27"}                # 0..7
RENOMES = {"defensiveawareness": "marking", "marking": "defensiveawareness"}
RESUMO = ("pacdiv", "shohan", "paskic", "driref", "defspe", "phypos")


def _versao(j):
    return (j or "").rstrip("~")


def regras_par(jogo_o, jogo_d):
    """As regras de escala de um par de versões (qualquer combinação de FIFA 16 … FC 27)."""
    o, d = _versao(jogo_o), _versao(jogo_d)
    if (o, d) in REGRAS:
        out = list(REGRAS[(o, d)])
    else:
        out = []
        if d == "fc27" and o != "fc27":
            out += [r for r in REGRAS[("fc26", "fc27")] if r["tipo"] == "x10"]
        if o == "fc27" and d != "fc27":
            out += REGRAS[("fc27", "fc26")]
    if o in SKINTYPE_LARGO and d in SKINTYPE_CURTO and not any(r["tipo"] == "max7" for r in out):
        out.append({"tabelas": PESSOAS, "coluna": "skintypecode", "tipo": "max7", "rotulo": "tipo de pele acima de 7 → 0"})
    return out


def regras_de(tabela, jogo_o, jogo_d):
    out = {}
    for r in regras_par(jogo_o, jogo_d):
        if tabela in r["tabelas"]:
            out[r["coluna"]] = r
    return out


def _resumo_jogador(g):
    """Os 6 números de resumo do jogador (como o jogo calcula), g(coluna) -> int."""
    if g("preferredposition1") == 0:
        return {"pacdiv": g("gkdiving"), "shohan": g("gkhandling"), "paskic": g("gkkicking"), "driref": g("gkreflexes"),
                "defspe": g("sprintspeed"), "phypos": g("gkpositioning")}
    marc = g("defensiveawareness") or g("marking")
    return {"pacdiv": 0.45 * g("acceleration") + 0.55 * g("sprintspeed"),
            "shohan": 0.45 * g("finishing") + 0.2 * g("longshots") + 0.2 * g("shotpower") + 0.05 * g("positioning") + 0.05 * g("volleys") + 0.05 * g("penalties"),
            "paskic": 0.2 * g("vision") + 0.2 * g("crossing") + 0.05 * g("freekickaccuracy") + 0.35 * g("shortpassing") + 0.15 * g("longpassing") + 0.05 * g("curve"),
            "driref": 0.1 * g("agility") + 0.05 * g("balance") + 0.05 * g("reactions") + 0.3 * g("ballcontrol") + 0.5 * g("dribbling"),
            "defspe": 0.2 * g("interceptions") + 0.1 * g("headingaccuracy") + 0.3 * marc + 0.3 * g("standingtackle") + 0.1 * g("slidingtackle"),
            "phypos": 0.05 * g("jumping") + 0.25 * g("stamina") + 0.5 * g("strength") + 0.2 * g("aggression")}


def aplicar_regra(r, v, moda):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return v
    t = r["tipo"]
    if t == "x10":
        return str(n * 10) if 1 <= n <= 10 else (v if 10 <= n <= 100 and n % 10 == 0 else (moda or v))
    if t == "d10":
        return str(max(1, min(10, round(n / 10)))) if n >= 10 else v
    if t == "max7":
        return "0" if n > 7 else v
    if t == "psd34":
        return "0" if n in (3, 4) else v
    return v


def moda(valores, padrao="0"):
    c = Counter(v for v in valores if v != "")
    return c.most_common(1)[0][0] if c else padrao


def plano(origem, destino_campos, destino_info, destino_linhas, jogo_o, jogo_d, ajustes=None):
    """Plano de colunas para uma tabela. origem: dados.Tabela; destino_*: esquema e linhas da tabela final.
    ajustes: {coluna: {"modo": "coluna"|"fixo"|"moda", "valor": ..., "origem": nome}} escolhidos pelo usuário."""
    ajustes = ajustes or {}
    regras = regras_de(origem.nome, jogo_o, jogo_d)
    idx_d = {c: i for i, c in enumerate(destino_campos)}
    colunas = []
    for c in destino_campos:
        inf = destino_info.get(c, {})
        modas = moda([l[idx_d[c]] for l in destino_linhas]) if destino_linhas else None
        padrao = modas if modas is not None else _padrao_meta(inf)
        aj = ajustes.get(c) or {}
        if aj.get("modo") == "fixo":
            col = {"destino": c, "modo": "fixo", "valor": str(aj.get("valor", "")), "origem": None}
        elif aj.get("modo") == "moda":
            col = {"destino": c, "modo": "moda", "valor": padrao, "origem": None}
        elif aj.get("modo") == "coluna" and aj.get("origem") in origem.campos:
            col = {"destino": c, "modo": "coluna", "origem": aj["origem"], "valor": padrao}
        elif c in origem.campos:
            col = {"destino": c, "modo": "coluna", "origem": c, "valor": padrao}
        elif RENOMES.get(c) in origem.campos:                # mudou de nome entre as versões
            col = {"destino": c, "modo": "coluna", "origem": RENOMES[c], "valor": padrao, "renomeada": True}
        elif c in RESUMO and origem.nome == "players" and {"acceleration", "sprintspeed", "gkdiving"} <= set(origem.campos):
            col = {"destino": c, "modo": "calculado", "valor": padrao, "origem": None}
        else:
            col = {"destino": c, "modo": "moda", "valor": padrao, "origem": None, "nova": True}
        col["regra"] = regras.get(c, {}).get("rotulo") if col["modo"] == "coluna" and col.get("origem") == c else None
        if col.get("renomeada"):
            col["regra"] = f"renomeada: {col['origem']} → {c}"
        elif col["modo"] == "calculado":
            col["regra"] = "calculada pelos atributos (como o jogo faz)"
        col["info"] = {k: inf.get(k) for k in ("tipo", "low", "high", "bits", "chave")} if inf else {}
        col["nova"] = c not in origem.campos
        col["ajustado"] = c in ajustes
        colunas.append(col)
    removidas = [c for c in origem.campos if c not in idx_d and not any(x.get("origem") == c for x in colunas)]
    return {"tabela": origem.nome, "colunas": colunas, "removidas": removidas, "linhas_origem": len(origem.linhas),
            "linhas_destino": len(destino_linhas) if destino_linhas is not None else None,
            "regras": [r["rotulo"] for r in regras.values()]}


def _padrao_meta(inf):
    if not inf:
        return "0"
    t = (inf.get("tipo") or "").upper()
    if "STRING" in t:
        return ""
    lo, hi = inf.get("low", 0), inf.get("high", 0)
    return str(0 if lo <= 0 <= hi else lo)


def chave_natural(destino_info):
    ch = [c for c, inf in destino_info.items() if inf.get("chave")]
    return ch if ch and ch != ["artificialkey"] else []


def converter(origem, pl, destino_campos, destino_info, destino_linhas, jogo_o, jogo_d, modo="substituir"):
    """Linhas finais (na ordem de destino_campos) + relatório."""
    regras = regras_de(origem.nome, jogo_o, jogo_d)
    io_ = {c: i for i, c in enumerate(origem.campos)}
    rel = Counter()
    fora = Counter()
    cortados = Counter()
    getters = []
    for col in pl["colunas"]:
        c = col["destino"]
        inf = destino_info.get(c, {})
        limites = None
        if inf and "INT" in (inf.get("tipo") or "").upper():
            limites = (inf.get("low", 0), inf.get("high", 0))
        maxbytes = (inf.get("bits", 0) // 8) if inf and "STRING" in (inf.get("tipo") or "").upper() and inf.get("bits", 0) < 64000 else None
        if col["modo"] == "coluna" and col.get("origem") in io_:
            getters.append((c, io_[col["origem"]], None, regras.get(c) if col["origem"] == c else None, limites, maxbytes, col["valor"]))
        elif col["modo"] == "calculado":
            getters.append((c, "calc", None, None, limites, maxbytes, col["valor"]))
        else:
            getters.append((c, None, str(col["valor"]), None, limites, maxbytes, col["valor"]))
    calcular = any(g[1] == "calc" for g in getters)
    novas = []
    for l in origem.linhas:
        linha = []
        res = None
        if calcular:
            def g(k, l=l):
                i = io_.get(k)
                try:
                    return int(float(l[i])) if i is not None and i < len(l) and l[i] != "" else 0
                except ValueError:
                    return 0
            res = _resumo_jogador(g)
        for c, i, fixo, regra, limites, maxbytes, mod in getters:
            if i == "calc":
                v = str(int(round(res.get(c, 0))))
                rel[f"{c}: calculada pelos atributos"] += 1
            else:
                v = fixo if i is None else (l[i] if i < len(l) else "")
            if regra:
                nv = aplicar_regra(regra, v, mod)
                if nv != v:
                    rel[f"{c}: {regra['rotulo']}"] += 1
                v = nv
            if limites:
                try:
                    n = int(float(v))
                    if n < limites[0] or n > limites[1]:
                        fora[c] += 1
                        v = str(max(limites[0], min(limites[1], n)))
                except ValueError:
                    if v != "":
                        fora[c] += 1
                        v = str(mod)
            elif maxbytes and len(v.encode("utf-8")) > maxbytes:
                cortados[c] += 1
                v = v.encode("utf-8")[:maxbytes].decode("utf-8", errors="ignore")
            linha.append(v)
        novas.append(linha)
    info = {"convertidas": len(novas), "regras": dict(rel), "fora_da_faixa": dict(fora), "cortados": dict(cortados),
            "removidas": pl["removidas"], "novas": [c["destino"] for c in pl["colunas"] if c.get("nova")]}
    if modo == "mesclar" and destino_linhas is not None:
        ch = chave_natural(destino_info)
        idx = {c: i for i, c in enumerate(destino_campos)}
        if ch:
            pos = {tuple(l[idx[k]] for k in ch): n for n, l in enumerate(destino_linhas)}
            final = [list(l) for l in destino_linhas]
            subst = acresc = 0
            for l in novas:
                k = tuple(l[idx[c]] for c in ch)
                if k in pos:
                    final[pos[k]] = l
                    subst += 1
                else:
                    pos[k] = len(final)
                    final.append(l)
                    acresc += 1
            info.update(modo="mesclar", chave=ch, substituidas=subst, acrescentadas=acresc, mantidas=len(destino_linhas) - subst)
        else:
            vistos = {tuple(l) for l in destino_linhas}
            final = [list(l) for l in destino_linhas]
            acresc = 0
            for l in novas:
                if tuple(l) not in vistos:
                    final.append(l)
                    vistos.add(tuple(l))
                    acresc += 1
            info.update(modo="mesclar", chave=None, acrescentadas=acresc, mantidas=len(destino_linhas), substituidas=0)
        return final, info
    info["modo"] = "substituir"
    return novas, info
