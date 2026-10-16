"""Criador de Ligas e Times — monta os registros do banco do jogo a partir dos dados coletados da API.

Cada time novo copia um time-modelo do banco (do mesmo país, gênero e nível parecido) nas tabelas que todo time precisa:
    teams, leagueteamlinks, manager, formations, default_mentalities, default_teamsheets, defaultteamdata,
    teamstadiumlinks (estádio genérico) + stadiumassignments (nome do estádio real), teamkits, broadcastleague,
    teamnationlinks (times do Resto do Mundo e seleções)
e troca o que vem da API: nome, fundação, capacidade do estádio, cores dos uniformes, técnico, formação mais usada,
tática, escalação, cobradores e capitão. Cada jogador copia os campos diversos de um jogador do banco da mesma posição
e nota (funções, estilos de jogo, salário…) e a aparência de um jogador genérico do mesmo gênero e nação (ou parecido
com a foto, quando ela foi analisada), com a linha de pele (skins); nome, nascimento, físico, nacionalidade, posições
e notas vêm da API e do modelo de notas (notas.py). Os nomes vão em editedplayernames e os de time e liga em idioma.

Seleções: o elenco são jogadores que já existem no banco (casados com a convocação da API) + os melhores da nação no
banco até cumprir o mínimo/máximo por posição do internationals.txt (SQUAD_SELECTION). Uma seleção que já existe
é atualizada (vínculos, escalação, técnico); uma nova entra na liga de seleções e no internationals.txt.

Nada é gravado aqui: Projeto junta as linhas novas, alteradas e removidas por tabela; saida.py grava o banco novo.
"""
import collections
import datetime
import re

import casamento as K
import notas as N

MAX_JOGADORES = 40
MINIMO_ELENCO, MINIMO_GOLEIROS = 18, 2            # elenco "suficiente": 18 jogadores, 2 goleiros
MENOS_DE_11 = "[menos11] "                     # começo da mensagem de erro de elenco com menos de 11 (a prévia oferece as opções)
TIME_SEM_CONTRATO = "111592"
LIGA_RDM = {0: "76", 1: "2226"}                 # Resto do Mundo (masculino, feminino)
LIGA_SELECOES = {0: "78", 1: "2136"}
LIGAS_NAO_CLUBE = {"78", "2136", "2255", "382", "383"}   # seleções, Liga Clássica e ligas especiais
NAO_MODELO_CLUBE = {"76", "78", "382", "383", "2136", "2226", "2255"}
LIGAS_LENDAS = {"2255"}                        # "Liga Clássica": versões de ídolos aposentados (XI de ligas e clubes)
APARENCIA = ["skintonecode", "skintypecode", "headtypecode", "headclasscode", "headvariation", "haircolorcode", "hairtypecode",
             "hairstylecode", "eyecolorcode", "eyebrowcode", "facialhairtypecode", "facialhaircolorcode", "sideburnscode",
             "lipcolor", "skincomplexion", "skinmakeup", "skinsurfacepack", "eyedetail", "facepsdlayer0", "facepsdlayer1",
             "faceposerpreset", "bodytypecode"]
# posição de cada vaga da formação (códigos do jogo) -> posição-base do jogador
VAGA_BASE = {0: 0, 1: 5, 2: 2, 3: 3, 4: 5, 5: 5, 6: 5, 7: 7, 8: 8, 9: 10, 10: 10, 11: 10, 12: 12, 13: 14, 14: 14, 15: 14,
             16: 16, 17: 18, 18: 18, 19: 18, 20: 21, 21: 21, 22: 21, 23: 23, 24: 25, 25: 25, 26: 25, 27: 27}
# quão bem um jogador da posição (linha) faz a vaga (coluna): 0 = igual; maior = pior
_VIZ = {0: {}, 2: {3: 1, 8: 3, 12: 3}, 3: {2: 1, 12: 4, 5: 4, 7: 4}, 5: {10: 3, 3: 4, 7: 4}, 7: {8: 1, 16: 4, 5: 4, 3: 4},
        8: {7: 1, 16: 3, 2: 3}, 10: {14: 2, 5: 3}, 12: {23: 2, 2: 3, 14: 4, 16: 4}, 14: {10: 2, 18: 2, 12: 4, 16: 4},
        16: {27: 2, 8: 3, 14: 4, 12: 4}, 18: {14: 2, 21: 2, 23: 3, 27: 3}, 21: {25: 1, 18: 2}, 23: {12: 2, 27: 3, 25: 4, 21: 3},
        25: {21: 1, 23: 4, 27: 4}, 27: {16: 2, 23: 3, 25: 4, 21: 3}}
# seleções: posição do jogo -> grupo do SQUAD_SELECTION do internationals.txt
GRUPO_SELECAO = {0: "GK", 7: "LB", 8: "LB", 5: "CB", 3: "RB", 2: "RB", 16: "LM", 27: "LM", 12: "RM", 23: "RM", 10: "CM", 14: "CM",
                 18: "CM", 21: "ST", 25: "ST"}
SELECAO_PADRAO = {"GK": (3, 5), "LB": (2, 4), "CB": (6, 8), "RB": (2, 4), "LM": (2, 4), "CM": (6, 10), "RM": (2, 4), "ST": (5, 8)}
PROFUNDIDADE = {30: "Recuada", 50: "Equilibrada", 65: "Alta", 90: "Agressiva"}
SAIDA_BOLA = {1: "Passe curto", 2: "Equilibrada", 3: "Bola longa"}
# capacidade típica do estádio pelo nível do time (mediana dos times do banco)
_CAPACIDADE = [(52, 8000), (57, 9500), (60, 10000), (63, 14000), (66, 16500), (69, 24000), (72, 32000), (75, 38000),
               (78, 40000), (81, 55000), (84, 68000), (90, 75000)]
_NAO_GENERICO = re.compile(r"youth|training|default|clubs stadium|rush|maw|wc_arena|practice", re.I)


def custo_pos(pos_jog, base_vaga):
    if pos_jog == base_vaga:
        return 0
    if pos_jog == 0 or base_vaga == 0:
        return 40
    return _VIZ.get(pos_jog, {}).get(base_vaga, 9)


def limpar(s, n):
    """Texto que cabe no campo (n bytes UTF-8)."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    while len(s.encode("utf-8")) > n:
        s = s[:-1]
    return s


def capacidade_tipica(nivel):
    pts = _CAPACIDADE
    if nivel <= pts[0][0]:
        return pts[0][1]
    for (a, ca), (b, cb) in zip(pts, pts[1:]):
        if a <= nivel <= b:
            return int(ca + (cb - ca) * (nivel - a) / (b - a))
    return pts[-1][1]


def tatica_auto(forca, formacao=None):
    """Linha defensiva e saída de bola pela força do time na liga (desvios do aproveitamento, como no nível): no banco,
    os times do alto usam passe curto e linha alta; os de baixo, bola longa e linha recuada."""
    forca = forca or 0.0
    cinco = bool(formacao) and str(formacao).startswith("5")
    saida = 1 if forca >= 0.6 else 3 if forca <= -0.7 else 2
    prof = 65 if forca >= 1.0 and not cinco else 30 if forca <= -0.8 or cinco else 50
    return {"profundidade": prof, "saida": saida}


class Ids:
    """Distribui ids livres por campo, a partir de um início escolhido e pulando os já usados."""

    def __init__(self, usados, inicio, limite, minimo=0):
        self.usados, self.prox, self.limite, self.minimo = set(usados), inicio, limite, minimo
        self.manuais = set()

    def novo(self):
        while self.prox in self.usados:
            self.prox += 1
        if self.prox > self.limite:
            raise ValueError(f"Acabaram os ids livres (limite {self.limite}).")
        v = self.prox
        self.usados.add(v)
        self.prox += 1
        return v

    def reservar(self, v, nome="id"):
        """Id escolhido à mão: precisa estar livre e dentro da faixa do campo."""
        v = int(v)
        if v in self.manuais:
            return v
        if not self.minimo <= v <= self.limite:
            raise ValueError(f"O {nome} {v} está fora da faixa do banco ({self.minimo}–{self.limite}).")
        if v in self.usados:
            raise ValueError(f"O {nome} {v} já está em uso no banco (ou em outro item do projeto).")
        self.usados.add(v)
        self.manuais.add(v)
        return v


def nomes_jogador(j):
    """(primeiro, sobrenome, nome comum, nome na camisa). O nome que a API mostra vira o nome comum, salvo quando
    vem abreviado ("R. Rios"): aí o jogo mostra primeiro nome + sobrenome."""
    nome = (j.get("nome") or "").strip()
    prim = (j.get("primeiro") or "").strip()
    sob = (j.get("sobrenome") or "").strip()
    tokens_reais = (sob + " " + prim).split()

    def com_acento(palavra):
        return next((w for w in tokens_reais if N_norm(w) == N_norm(palavra)), palavra)
    m = re.match(r"^[A-ZÀ-Ý][a-zà-ý]?\.\s*(\S.*)$", nome) or re.match(r"^[A-ZÀ-Ý]\s+(\S.*)$", nome)   # "R. Rios", "J Lingard"
    primeiro = prim.split()[0] if prim else ""
    if m:                                             # "R. Rios"
        visto = com_acento(m.group(1).split()[0]) if m.group(1).split() else ""
        sobrenome = " ".join(com_acento(w) for w in m.group(1).split()) or sob
        comum, camisa = "", visto
        if not primeiro:
            primeiro = nome.split(".")[0].split()[0]
    else:
        comum = " ".join(com_acento(w) for w in nome.split())
        sobrenome = sob or (nome.split()[-1] if nome else "")
        camisa = comum.split()[-1] if comum else (sobrenome.split()[0] if sobrenome else "")
    return limpar(primeiro, 44), limpar(sobrenome, 44), limpar(comum, 44), limpar(camisa, 44)


def cor_hex(h, padrao=(200, 200, 200)):
    try:
        h = str(h).lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError, TypeError):
        return padrao


def nivel_pelo_valor(dados):
    """Nível (média dos 14 mais fortes) de um elenco da Transfermarkt pelas notas que o valor de mercado dá."""
    if dados.get("fonte") != "transfermarkt":
        return None
    k = N.carregar_coef_tm()
    js = dados.get("jogadores") or []
    vals = [j["valor"] for j in js if j.get("valor")]
    if not vals:
        return None
    piso = min(vals) * 0.6
    ref = data_ref_tm(dados)
    idade = lambda j: (idade_de(j["nascimento"], ref) if ref and j.get("nascimento") else None) or j.get("idade")  # noqa: E731
    notas = sorted((N.overall_tm(j.get("valor") or piso, idade(j), k, arredondar=False) for j in js), reverse=True)[:14]
    return round(sum(notas) / len(notas), 1)


def aplicar_foto(p, alvo):
    """Pele, cor do cabelo, penteado e barba lidos na foto (aparencia.py) por cima da aparência do doador."""
    for k in ("skintonecode", "haircolorcode", "hairtypecode"):
        if k in alvo and k in p:
            p[k] = str(alvo[k][0])
    if "facialhairtypecode" in alvo and "facialhairtypecode" in p:
        if not alvo["facialhairtypecode"][0]:
            p["facialhairtypecode"] = "0"
        elif p["facialhairtypecode"] == "0" and "_barba_codigo" in alvo:
            p["facialhairtypecode"] = str(alvo["_barba_codigo"][0])
    if "facialhaircolorcode" in p and "haircolorcode" in alvo and p.get("facialhairtypecode", "0") != "0":
        p["facialhaircolorcode"] = str(alvo["haircolorcode"][0])


def idade_de(nascimento, data_ref=None):
    """Idade hoje ou na data de referência (ISO ou date): a de um elenco antigo é a que o jogador tinha na época."""
    try:
        n = datetime.date.fromisoformat(str(nascimento)[:10])
        hoje = datetime.date.fromisoformat(str(data_ref)[:10]) if data_ref else datetime.date.today()
    except (TypeError, ValueError):
        return None
    return hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))


def data_ref_tm(dados):
    """Fim da temporada de um elenco antigo da Transfermarkt (None no elenco atual ou na temporada em andamento)."""
    if dados.get("fonte") != "transfermarkt" or dados.get("modo") == "atual":
        return None
    if dados.get("data_ref"):
        return dados["data_ref"]
    import coleta_tm as CT
    d = CT._fim_temporada(dados.get("temporada_nome"))
    return d.isoformat() if d < datetime.date.today() else None


def temporada_antiga_tm(dados, anos=2):
    """Temporada que terminou há mais de `anos` anos: os valores de mercado de então não se comparam com os de hoje."""
    ref = data_ref_tm(dados)
    if not ref:
        return False
    return (datetime.date.today() - datetime.date.fromisoformat(ref[:10])).days > anos * 365


class Projeto:
    """Linhas novas, alteradas e removidas por tabela + ids reservados + textos de idioma."""

    def __init__(self, banco, idioma, perfil, opcoes=None):
        self.b, self.idioma, self.perfil = banco, idioma, perfil
        self.op = {"jogador_inicio": 460000, "time_inicio": 150000, "liga_inicio": 3000, "tecnico_inicio": 460000,
                   "kit_inicio": 30000, "ano": datetime.date.today().year, **(opcoes or {})}
        self.novas = collections.defaultdict(list)          # tabela -> [dict]
        self.alt = collections.defaultdict(dict)            # tabela -> {índice da linha original: {campo: valor}}
        self.rem = collections.defaultdict(set)             # tabela -> {índice da linha original}
        self._indices = {}
        self.idioma_novo = {}
        self.avisos = []
        self.tabs = {}
        self._ids = {}
        self.nacoes = self._nacoes()
        self.nivel_time_db = N.nivel_times(banco)
        self.liga_de = {}
        for d in self.tab("leagueteamlinks").dicts():
            self.liga_de.setdefault(d["teamid"], d["leagueid"])
        self.pais_liga = {d["leagueid"]: d["countryid"] for d in self.tab("leagues").dicts()}
        self.resumo = []
        self.selecoes = []             # seleções criadas/atualizadas (para o internationals.txt e o relatório)
        self.ligas_nomes = {}          # leagueid -> nome (ligas novas)
        self.ligas_criadas = {}        # id da liga na API -> leagueid
        self._indice_jog = None
        self._skins = None
        self.nivel_valor = None
        self._nomes_times = None
        self.clubes_mexidos = set()    # clubes do banco que perderam jogadores para times novos (escalação refeita)
        self.excluidos = []            # jogadores tirados do último elenco preparado (para a prévia)

    # ---- utilidades
    def tab(self, nome):
        if nome not in self.tabs:
            self.tabs[nome] = self.b.tabela(nome)
        return self.tabs[nome]

    def tem_tabela(self, nome):
        return self.b.tem(nome)

    def ids(self, chave, tabela, campo, inicio_op=None, extra=()):
        if chave not in self._ids:
            t = self.tab(tabela)
            usados = {int(v) for v in t.valores(campo) if v.lstrip("-").isdigit()}
            for tn, cn in extra:
                usados |= {int(v) for v in self.tab(tn).valores(cn) if v.lstrip("-").isdigit()}
            info = t.info.get(campo, {})
            inicio = int(self.op.get(inicio_op, 0)) if inicio_op else (max(usados) + 1 if usados else 0)
            alto = int(info.get("high") or (1 << int(info.get("bits", 16))) - 1)
            self._ids[chave] = Ids(usados, inicio, alto, max(0, int(info.get("low") or 0)))
        return self._ids[chave]

    def ids_jogador(self):
        """playerid e managerid saem do mesmo espaço: os dois viram headassetid e assetid da pele (skins), que não podem
        se repetir entre um jogador e um técnico."""
        extra = [("manager", "managerid"), ("players", "headassetid"), ("manager", "headassetid")]
        if self.tem_tabela("skins"):
            extra.append(("skins", "assetid"))
        return self.ids("jog", "players", "playerid", "jogador_inicio", extra=extra)

    def ids_time(self):
        return self.ids("time", "teams", "teamid", "time_inicio", extra=[("teamkits", "teamtechid")])

    def _nacoes(self):
        out = {}
        self.nome_nacao = {}
        self.confed = {}
        for d in self.tab("nations").dicts():
            out[N_norm(d["nationname"])] = d["nationid"]
            self.nome_nacao[d["nationid"]] = (self.idioma.texto(f"NationName_{d['nationid']}") if self.idioma else None) or d["nationname"]
            self.confed[d["nationid"]] = d.get("confederation")
            if d.get("isocountrycode"):
                out["iso:" + d["isocountrycode"].upper()] = d["nationid"]
        for apelido, nome in (("usa", "united states"), ("korea republic", "korea republic"), ("south korea", "korea republic"),
                              ("ivory coast", "cote d ivoire"), ("czech republic", "czech republic"), ("czechia", "czech republic"),
                              ("bosnia", "bosnia and herzegovina"), ("congo dr", "dr congo"), ("dr congo", "congo dr"),
                              ("north macedonia", "fyr macedonia"), ("turkiye", "turkey"), ("cape verde islands", "cape verde"),
                              ("china pr", "china pr"), ("china", "china pr"), ("ireland", "republic of ireland"),
                              ("korea south", "korea republic"), ("korea north", "korea dpr"), ("cote d ivoire", "cote d ivoire"),
                              ("bosnia herzegovina", "bosnia and herzegovina"), ("turkiye", "turkey"), ("tuerkiye", "turkey"),
                              ("dr congo", "congo dr"), ("congo", "congo"), ("cabo verde", "cape verde"),
                              ("united states", "united states"), ("st kitts nevis", "st kitts and nevis"),
                              ("chinese taipei", "chinese taipei"), ("kyrgyzstan", "kyrgyzstan"), ("curacao", "curacao")):
            if N_norm(nome) in out and N_norm(apelido) not in out:
                out[N_norm(apelido)] = out[N_norm(nome)]
        return out

    def nacao(self, nome, codigo=None):
        if codigo and "iso:" + codigo.upper() in self.nacoes:
            return self.nacoes["iso:" + codigo.upper()]
        return self.nacoes.get(N_norm(nome or ""))

    def nacao_jogador(self, j):
        """A escolhida à mão; senão a 1ª nacionalidade que existe no banco (a Transfermarkt dá todas: "Guadeloupe,
        França" -> França); senão o país de nascimento; senão Resto do Mundo (211)."""
        if j.get("nacao_manual"):
            return j["nacao_manual"]
        for nome in [j.get("nacionalidade"), *(j.get("nacionalidades") or []), j.get("pais_nascimento")]:
            n = self.nacao(nome) if nome else None
            if n and str(n) != "211":
                return n
        return "211"

    def linha_vazia(self, tabela):
        return {c: "0" for c in self.tab(tabela).campos}

    def copiar(self, tabela, campo, valor):
        """Linhas (como estão agora, com as alterações do projeto) da tabela com campo == valor (dicts novos)."""
        return [dict(d) for d in self.atuais(tabela, **{campo: valor})]

    def texto(self, chave, valor):
        self.idioma_novo[chave] = valor

    # ---- camada de edição: alterar e remover linhas que já existem no banco
    def _indice(self, tabela, campo):
        k = (tabela, campo)
        if k not in self._indices:
            t = self.tab(tabela)
            i = t.col(campo)
            idx = collections.defaultdict(list)
            if i is not None:
                for n, l in enumerate(t.linhas):
                    idx[l[i]].append(n)
            self._indices[k] = idx
        return self._indices[k]

    def indices(self, tabela, **filtro):
        t = self.tab(tabela)
        if not filtro:
            return [n for n in range(len(t.linhas)) if n not in self.rem[tabela]]
        (campo, valor), *resto = filtro.items()
        alt = self.alt.get(tabela, {})
        out = []
        cand = self._indice(tabela, campo).get(str(valor), [])
        # linhas cujo valor foi alterado pelo projeto também contam (pelo valor novo)
        extra = [n for n, a in alt.items() if a.get(campo) == str(valor)]
        for n in sorted(set(cand) | set(extra)):
            if n in self.rem[tabela]:
                continue
            d = self.linha(tabela, n)
            if all(d.get(c) == str(v) for c, v in [(campo, valor)] + resto):
                out.append(n)
        return out

    def linha(self, tabela, n):
        t = self.tab(tabela)
        d = dict(zip(t.campos, t.linhas[n]))
        d.update(self.alt.get(tabela, {}).get(n, {}))
        return d

    def atuais(self, tabela, **filtro):
        return [self.linha(tabela, n) for n in self.indices(tabela, **filtro)]

    def alterar(self, tabela, valores, **filtro):
        ns = self.indices(tabela, **filtro)
        for n in ns:
            self.alt[tabela].setdefault(n, {}).update({k: str(v) for k, v in valores.items()})
        return len(ns)

    def alterar_linha(self, tabela, n, valores):
        self.alt[tabela].setdefault(n, {}).update({k: str(v) for k, v in valores.items()})

    def remover(self, tabela, **filtro):
        ns = self.indices(tabela, **filtro)
        self.rem[tabela].update(ns)
        return len(ns)

    def novas_de(self, tabela, **filtro):
        return [d for d in self.novas.get(tabela, []) if all(d.get(c) == str(v) for c, v in filtro.items())]

    # ---- jogadores do banco (casamento)
    def nome_time(self, teamid):
        if self._nomes_times is None:
            self._nomes_times = {t["teamid"]: t["nome"] for t in self.b.times(self.idioma)}
        return self._nomes_times.get(str(teamid))

    def clube_db(self, pid):
        """Clube (não seleção, não Liga Clássica) do jogador no banco, com as mudanças do projeto."""
        for d in self.atuais("teamplayerlinks", playerid=pid):
            if self.liga_de.get(d["teamid"]) not in LIGAS_NAO_CLUBE:
                return d["teamid"]
        return None

    def ja_no_banco(self, j, genero):
        """O jogador do banco que é este (mesmo nascimento e nome; sem nascimento, o mesmo nome e a idade): None ou
        {playerid, nome, clube, clube_nome, overall, idade, forte, idolo}. O nome tem de bater (o nascimento só confirma)
        e uma nacionalidade diferente de todas as do jogador na fonte pesa contra."""
        idx = self.indice_jogadores()
        nacs = [n for n in (self.nacao(x) for x in [j.get("nacionalidade"), *(j.get("nacionalidades") or [])] if x) if n]
        cand = idx.buscar(j.get("nome"), j.get("primeiro") or "", j.get("sobrenome") or "", j.get("nascimento"),
                          None if j.get("nascimento") else j.get("idade_hoje", j.get("idade")), genero=str(genero), minimo=0.9,
                          nacoes=nacs)
        if not cand:
            return None
        nota, pid = cand[0]
        if not j.get("nascimento") and nota < 0.95:
            return None
        info = idx.info[pid]
        times = idx.times_de.get(pid, [])
        idolo = any(self.liga_de.get(t) in ("2255",) for t in times) and not self.clube_db(pid)
        clube = self.clube_db(pid)
        return {"playerid": pid, "nome": info["nome"], "clube": clube, "clube_nome": self.nome_time(clube) if clube else None,
                "overall": info["overall"], "idade": info["idade"], "nota": round(nota, 2), "idolo": idolo,
                "forte": bool(j.get("nascimento")) and nota >= 1.0 and not idolo}

    def indice_jogadores(self):
        if self._indice_jog is None:
            self._indice_jog = K.IndiceJogadores(self.b)
        return self._indice_jog

    def skins_de(self, assetid):
        if not self.tem_tabela("skins"):
            return None
        if self._skins is None:
            t = self.tab("skins")
            i = t.col("assetid")
            self._skins = {l[i]: l for l in t.linhas}
        l = self._skins.get(str(assetid))
        return dict(zip(self.tab("skins").campos, l)) if l else None

    # ---- modelos
    def time_modelo(self, nacao_id, nivel, genero=0, fixo=None, selecao=False):
        if fixo and self.copiar("teams", "teamid", fixo):
            return str(fixo)
        tg = self.tab("teams")
        ig, it = tg.col("gender"), tg.col("teamid")
        genero_de = {l[it]: l[ig] for l in tg.linhas}
        conf = self.confed.get(str(nacao_id))
        melhores = []
        for tid, nv in self.nivel_time_db.items():
            lid = self.liga_de.get(tid)
            if not lid or genero_de.get(tid) != str(genero):
                continue
            if selecao:
                if lid != LIGA_SELECOES.get(genero):
                    continue
                tn = self.atuais("teamnationlinks", teamid=tid)
                nac = tn[0]["nationid"] if tn else None
                perto = 0 if nac == str(nacao_id) else 1 if conf and self.confed.get(nac) == conf else 2
            else:
                if lid in NAO_MODELO_CLUBE:
                    continue
                perto = 0 if self.pais_liga.get(lid) == str(nacao_id) else 1
            melhores.append((perto, abs(nv - nivel), tid))
        if not melhores:
            if genero:
                return self.time_modelo(nacao_id, nivel, 0, None, selecao)
            return next(iter(self.nivel_time_db))
        return sorted(melhores)[0][2]

    def formacoes_db(self):
        nomes = collections.Counter(d["formationname"] for d in self.tab("formations").dicts() if d["formationname"] and d["formationname"] != "-NONE-")
        return [n for n, _ in nomes.most_common()]

    def modelo_formacao(self, formacao, modelo_time):
        fo = self.tab("formations")
        ifn, it = fo.col("formationname"), fo.col("teamid")
        do_modelo = [l for l in fo.linhas if l[it] == modelo_time]
        if formacao and do_modelo and do_modelo[0][ifn] == formacao:
            return modelo_time
        for l in fo.linhas:
            if formacao and l[ifn] == formacao and l[it] not in ("-1",) and self.copiar("default_mentalities", "teamid", l[it]) \
                    and self.copiar("defaultteamdata", "teamid", l[it]):
                return l[it]
        return modelo_time

    def estadios_genericos(self):
        out = []
        uso = collections.Counter(d["stadiumid"] for d in self.tab("teamstadiumlinks").dicts())
        for d in self.tab("stadiums").dicts():
            if d.get("islicensed") != "0" or d.get("isstadiumavailable", "1") != "1" or _NAO_GENERICO.search(d.get("name") or ""):
                continue
            cap = int(d.get("capacity") or 0)
            if cap < 3000 or not uso.get(d["stadiumid"]):
                continue
            out.append(d)
        return out

    def estadio_generico(self, capacidade, chave):
        """Estádio genérico com a capacidade mais parecida; entre os parecidos (±15%), varia pelo time."""
        gen = self.estadios_genericos()
        if not gen:
            return None
        cap = max(3000, int(capacidade or 20000))
        gen.sort(key=lambda d: abs(int(d["capacity"]) - cap))
        melhor = int(gen[0]["capacity"])
        perto = [d for d in gen if abs(int(d["capacity"]) - cap) <= max(abs(melhor - cap), cap * 0.15)]
        return perto[int(N.semente("estadio", chave) * len(perto)) % len(perto)]

    def capacidade_alvo(self, tm, nivel, genero, nacao):
        """Capacidade que o estádio genérico deve ter: a do estádio real (API) quando se sabe; senão a típica do nível
        no banco, ajustada pelo país (estádios do país no banco) e menor em times femininos."""
        real = (tm.get("estadio") or {}).get("capacidade")
        if real:
            return int(real), "estádio real"
        cap = capacidade_tipica(nivel - (6 if genero else 0)) * (0.6 if genero else 1.0)
        caps = []
        for lid, pais in self.pais_liga.items():
            if pais == str(nacao):
                for d in self.atuais("leagueteamlinks", leagueid=lid):
                    t = self.atuais("teams", teamid=d["teamid"])
                    nv = self.nivel_time_db.get(d["teamid"])
                    if t and nv and int(t[0]["teamstadiumcapacity"] or 0):
                        caps.append(int(t[0]["teamstadiumcapacity"]) / max(1, capacidade_tipica(nv)))
        if len(caps) >= 6:
            caps.sort()
            cap *= max(0.6, min(1.6, caps[len(caps) // 2]))
        return int(cap), "nível do time" + (" e país" if len(caps) >= 6 else "")

    # ---- liga
    def criar_liga(self, nome, nacao_id, nivel_div=1, genero=0, modelo=None, abrev=None, api_id=None, leagueid=None):
        ids = self.ids("liga", "leagues", "leagueid", "liga_inicio")
        lid = ids.reservar(leagueid, "leagueid") if leagueid else ids.novo()
        base = None
        lg = self.tab("leagues")
        for d in lg.dicts():
            if modelo and d["leagueid"] == str(modelo):
                base = d
                break
            if base is None and d["countryid"] == str(nacao_id) and d.get("iswomencompetition") == str(genero) \
                    and d.get("isinternationalleague") != "1":
                base = d
        if base is None:
            base = next((d for d in lg.dicts() if d["leagueid"] == LIGA_RDM.get(genero, "76")), None) or \
                next(d for d in lg.dicts() if d["leagueid"] == "76")
        base = dict(base)
        base.update(leagueid=str(lid), leaguename=limpar(nome, 119), countryid=str(nacao_id or base["countryid"]),
                    level=str(max(1, min(int(lg.info["level"]["high"] or 9), nivel_div))), iswomencompetition=str(genero),
                    isinternationalleague="0")
        self.novas["leagues"].append(base)
        self.ligas_nomes[str(lid)] = nome
        if api_id is not None:
            self.ligas_criadas[str(api_id)] = str(lid)
        self.texto(f"LeagueName_{lid}", nome)
        self.texto(f"LeagueName_Abbr15_{lid}", limpar(abrev or nome, 30)[:15])
        return str(lid)

    # ---- time
    def criar_time(self, dados, leagueid, nivel_time, genero=0, ajustes=None, extra=None):
        """dados: coleta.coletar_time(); ajustes: {api_id: {...}, "_time_nome"…}; extra: modelo, visual, posicao_tabela,
        teamid (manual), tatica, tecnico, estadio, forca, fotos. Devolve o resumo do time (prévia)."""
        ajustes = ajustes or {}
        ex = extra or {}
        tm = dados["time"]
        if nivel_time is None:                             # Transfermarkt no automático: o nível pelo valor de mercado
            nivel_time = nivel_pelo_valor(dados) or 65.0
            auto_tm = True
        else:
            auto_tm = False
        nacao_time = self.nacao(tm.get("pais")) or ("211" if not genero else "211")
        modelo = self.time_modelo(nacao_time, nivel_time, genero, ex.get("modelo"))
        tat = dict(ex.get("tatica") or {})
        formacao = tat.get("formacao") or dados.get("formacao")
        mod_form = self.modelo_formacao(formacao, modelo)
        teamid = str(self.ids_time().reservar(ex["teamid"], "teamid") if ex.get("teamid") else self.ids_time().novo())
        # jogadores: posição, nota, atributos
        jogs = self._preparar_jogadores(dados, None if auto_tm else nivel_time, genero, ajustes, ex.get("fotos") or {})
        fo_mod = self.copiar("formations", "teamid", mod_form)[0]
        vagas = [int(fo_mod[f"position{i}"]) for i in range(11)]
        insuficiente = len(jogs) < MINIMO_ELENCO or sum(1 for j in jogs if j["pos"] == 0) < MINIMO_GOLEIROS
        menos11 = self._menos_de_11(jogs, ex.get("menos11"), tm["nome"], nivel_time, nacao_time, genero) if insuficiente else None
        titulares, reservas, ordem = self._escalacao(jogs, vagas, parcial=menos11 == "assim")
        escolha = self.ultima_escolha
        vagas_tit = [v for v, j in zip(vagas, escolha) if j]
        afetados = self.clubes_afetados(ordem)             # antes de tirar os jogadores dos clubes antigos
        for j in ordem:
            self._linhas_jogador(j, teamid, genero)
            self.novas["teamplayerlinks"].append(self._vinculo(teamid, j, titulares, reservas, vagas_tit))
        takers = self._cobradores(titulares)
        # tática: formação (a mais usada nas escalações ou a escolhida), linha defensiva e saída de bola
        auto = tatica_auto(ex.get("forca"), fo_mod.get("formationname"))
        prof = int(tat.get("profundidade") or auto["profundidade"])
        saida = int(tat.get("saida") or auto["saida"])
        # time
        notas_lin = self._notas_time(titulares, vagas_tit)
        cores = self._cores(dados)
        t = dict(self.copiar("teams", "teamid", modelo)[0])
        nome = limpar(ajustes.get("_time_nome") or tm["nome"], 59)
        cap_alvo, cap_motivo = self.capacidade_alvo(tm, nivel_time, genero, nacao_time)
        est_aj = ex.get("estadio") or {}
        if est_aj.get("capacidade"):
            cap_alvo, cap_motivo = int(est_aj["capacidade"]), "escolhida"
        t.update(teamid=teamid, assetid=teamid if ex.get("visual", "proprio") == "proprio" else t["assetid"], teamname=nome,
                 foundationyear=str(tm.get("fundacao") or t["foundationyear"]),
                 teamstadiumcapacity=str(cap_alvo or t["teamstadiumcapacity"]),
                 overallrating=str(notas_lin["geral"]), attackrating=str(notas_lin["ataque"]),
                 midfieldrating=str(notas_lin["meio"]), defenserating=str(notas_lin["defesa"]),
                 matchdayoverallrating=str(notas_lin["geral"]), matchdayattackrating=str(notas_lin["ataque"]),
                 matchdaymidfieldrating=str(notas_lin["meio"]), matchdaydefenserating=str(notas_lin["defesa"]),
                 domesticprestige=str(int(max(1, min(10, round((nivel_time - 58) / 2.2))))),
                 internationalprestige=str(int(max(1, min(10, round((nivel_time - 66) / 2.0))))),
                 popularity=str(int(max(1, min(10, round((nivel_time - 56) / 2.4))))),
                 leaguetitles="0", domesticcups="0", uefa_cl_wins="0", uefa_el_wins="0", uefa_uecl_wins="0",
                 uefa_consecutive_wins="0", prev_el_champ="0", rivalteam="1", gender=str(genero))
        if "buildupplay" in t:
            t["buildupplay"] = str(saida)
        if "defensivedepth" in t:
            t["defensivedepth"] = str(prof)
        for k, j in takers.items():
            if k in t:
                t[k] = str(j["playerid"])
        for i, c in enumerate(cores["time"][:3], start=1):
            for comp, v in zip("rgb", c):
                if f"teamcolor{i}{comp}" in t:
                    t[f"teamcolor{i}{comp}"] = str(v)
        self.novas["teams"].append(t)
        # vínculo com a liga (+ nação, quando a liga é a do Resto do Mundo)
        lt = dict(self.copiar("leagueteamlinks", "teamid", modelo)[0])
        for k in lt:
            if k not in ("teamshortform", "teamlongform", "teamform", "objective", "highestpossible", "highestprobable", "grouping"):
                lt[k] = "0"
        lt.update(leagueid=str(leagueid), prevleagueid=str(leagueid), teamid=teamid,
                  artificialkey=str(self.ids("ltl", "leagueteamlinks", "artificialkey").novo()),
                  previousyeartableposition=str(ex.get("posicao_tabela") or 1), currenttableposition=str(ex.get("posicao_tabela") or 1),
                  unbeatenleague="1", unbeatenhome="1", unbeatenaway="1", unbeatenallcomps="1")
        self.novas["leagueteamlinks"].append(lt)
        if str(leagueid) in LIGA_RDM.values() or self.pais_liga.get(str(leagueid)) == "211":
            self.novas["teamnationlinks"].append({"leagueid": str(leagueid), "teamid": teamid, "nationid": str(nacao_time)})
        # formação, mentalidade padrão, dados padrão e escalação
        self._formacao_e_escalacao(teamid, modelo, mod_form, fo_mod, escolha, ordem, takers, prof, saida)
        # estádio genérico (capacidade do estádio real ou típica do nível) + o nome do estádio real
        est = self._estadio(teamid, modelo, tm, cap_alvo, est_aj)
        for d in self.copiar("broadcastleague", "teamid", modelo):
            d.update(teamid=teamid, artificialkey=str(self.ids("bl", "broadcastleague", "artificialkey").novo()))
            if d["leagueid"] == self.liga_de.get(modelo):
                d["leagueid"] = str(leagueid)
            self.novas["broadcastleague"].append(d)
        self._uniformes(teamid, modelo, cores)
        # técnico
        tec_aj = dict(ex.get("tecnico") or {})
        if (ex.get("fotos") or {}).get("_tecnico"):
            tec_aj["_foto"] = ex["fotos"]["_tecnico"]
        tec = self._tecnico(teamid, modelo, dados.get("tecnico"), tec_aj, nacao_time, genero)
        # idioma
        self.texto(f"TeamName_{teamid}", nome)
        self.texto(f"TeamName_Abbr15_{teamid}", limpar(ajustes.get("_time_abrev15") or nome, 30)[:15])
        self.texto(f"TeamName_Abbr10_{teamid}", limpar(ajustes.get("_time_abrev10") or nome, 20)[:10])
        self.texto(f"TeamName_Abbr3_{teamid}", (ajustes.get("_time_sigla") or tm.get("sigla") or nome[:3]).upper()[:3])
        res = {"teamid": teamid, "teamid_manual": bool(ex.get("teamid")), "nome": nome, "api_id": tm["id"], "logo": tm.get("logo"),
               "fonte": dados.get("fonte") or "apifootball", "nivel_valor": self.nivel_valor, "posse": dados.get("posse"),
               "modelo": modelo, "modelo_formacao": mod_form, "formacao": fo_mod.get("formationname"),
               "formacao_api": dados.get("formacao"), "formacoes_api": dados.get("formacoes") or {},
               "tatica": {"profundidade": prof, "saida": saida, "auto": auto, "manual": {k: v for k, v in tat.items() if v}},
               "nivel": round(nivel_time, 1), "geral": notas_lin["geral"], "genero": genero,
               "jogadores": [self._publico(j) for j in ordem], "cores": cores, "tecnico": tec,
               "estadio": est, "avisos": list(dados.get("avisos") or []), "excluidos": list(self.excluidos),
               "clubes_afetados": afetados, "menos11": menos11,
               "goleiros": sum(1 for j in ordem if j["pos"] == 0),
               "livres": sum(1 for j in ordem if j.get("origem") == "livre"),
               "usar_db_todos": bool(ajustes.get("_usar_db_todos"))}
        if menos11 == "assim":
            res["avisos"].append(f"Criado com {len(ordem)} jogador(es), menos de 11: as vagas que faltam ficam vazias na escalação. "
                                 "O jogo pode travar ao escalar este time; complete o elenco antes de jogar com ele.")
        self.resumo.append(res)
        return res

    # ---- partes do time
    def _menos_de_11(self, jogs, modo, nome, nivel, nacao_time, genero):
        """Elenco da fonte sem jogadores suficientes (menos de 18 ou de 2 goleiros): "livres" completa até 18 e 2
        goleiros com jogadores sem contrato (nota perto da média do elenco, a nação mais comum dele); "assim" cria
        como está. Sem escolha: com menos de 11 para com a explicação; com 11 ou mais cria como está (a prévia oferece
        completar)."""
        gks = sum(1 for j in jogs if j["pos"] == 0)
        if modo == "livres":
            nacs = collections.Counter(str(j.get("nacao") or self.nacao_jogador(j)) for j in jogs)
            nacs.pop("211", None)
            nacao = nacs.most_common(1)[0][0] if nacs else nacao_time
            alvo = sum(j["overall"] for j in jogs) / len(jogs) if jogs else float(nivel) - 3
            falta = max(MINIMO_ELENCO - len(jogs), MINIMO_GOLEIROS - gks)
            for pid in self.livres(falta, alvo, nacao, genero, [j["pos"] for j in jogs]):
                jogs.append(self.jogador_livre(pid))
            if len(jogs) < 11:
                raise ValueError(f"{nome}: não há jogadores sem contrato suficientes para chegar a 11 ({len(jogs)}).")
            return "livres"
        if len(jogs) >= 11:
            return "incompleto"
        if modo == "assim" and jogs:
            return "assim"
        raise ValueError(f"{MENOS_DE_11}{nome} tem só {len(jogs)} jogador(es) no elenco da fonte. Escolha na prévia: completar com "
                         "jogadores sem contrato (nota e nacionalidade parecidas com as do elenco) ou criar assim mesmo.")

    def _escalacao(self, jogs, vagas, parcial=False):
        """parcial: menos de 11 jogadores — as vagas sem ninguém ficam vazias (ultima_escolha tem None nelas)."""
        self.ultima_escolha = self._escalar(jogs, vagas, parcial)
        titulares = [j for j in self.ultima_escolha if j]
        ordem = titulares + sorted((j for j in jogs if j not in titulares), key=lambda j: -j["overall"])
        reservas = ordem[11:11 + 9]
        usados = set()
        for j in ordem:                                   # número escolhido à mão > da API > livre
            n = j.get("camisa_manual") or j.get("numero")
            j["camisa"] = n if isinstance(n, int) and 1 <= n <= 99 and n not in usados else None
            if j["camisa"]:
                usados.add(j["camisa"])
        livre = (n for n in range(1, 100) if n not in usados)
        for j in ordem:
            if not j["camisa"]:
                j["camisa"] = next(livre, 99)
        return titulares, reservas, ordem

    def _vinculo(self, teamid, j, titulares, reservas, vagas):
        tl = self.linha_vazia("teamplayerlinks")
        if j in titulares:
            posicao = vagas[titulares.index(j)]
        elif j in reservas:
            posicao = 28
        else:
            posicao = 29
        tl.update(teamid=teamid, playerid=str(j["playerid"]), jerseynumber=str(j["camisa"]), position=str(posicao), form="3",
                  artificialkey=str(self.ids("tpl", "teamplayerlinks", "artificialkey").novo()))
        return tl

    def _cobradores(self, tit):
        atr = lambda j, k: (j.get("atr") or {}).get(k, 0)  # noqa: E731
        cap = max(tit, key=lambda j: ((j.get("stats") or {}).get("capitao") or 0, j.get("idade") or 0, j["overall"]))
        if any(j.get("capitao_tm") for j in tit):
            cap = next(j for j in tit if j.get("capitao_tm"))
        if any(j.get("capitao_manual") for j in tit):
            cap = next(j for j in tit if j.get("capitao_manual"))
        pen = max(tit, key=lambda j: atr(j, "penalties") + atr(j, "finishing") + ((j.get("stats") or {}).get("penaltis") or 0) * 5)
        falta = max(tit, key=lambda j: atr(j, "freekickaccuracy") + atr(j, "curve"))
        esc = max(tit, key=lambda j: atr(j, "crossing") + atr(j, "curve"))
        longo = next((j for j in tit if j["pos"] == 0), tit[0])
        return {"captainid": cap, "penaltytakerid": pen, "freekicktakerid": falta, "leftfreekicktakerid": falta,
                "rightfreekicktakerid": falta, "leftcornerkicktakerid": esc, "rightcornerkicktakerid": esc, "longkicktakerid": longo}

    def _formacao_e_escalacao(self, teamid, modelo, mod_form, fo_mod, titulares, ordem, takers, prof, saida):
        fo = dict(fo_mod)
        fo.update(formationid=str(self.ids("form", "formations", "formationid").novo()), teamid=teamid)
        self.novas["formations"].append(fo)
        dm = dict(self.copiar("default_mentalities", "teamid", mod_form)[0])
        dm.update(teamid=teamid, mentalityid=str(self.ids("ment", "default_mentalities", "mentalityid").novo()))
        for i in range(11):                                # vaga sem jogador (time criado com menos de 11): -1
            dm[f"playerid{i}"] = str(titulares[i]["playerid"]) if i < len(titulares) and titulares[i] else "-1"
        if "buildupplay" in dm:
            dm["buildupplay"] = str(saida)
        if "defensivedepth" in dm:
            dm["defensivedepth"] = str(prof)
        self.novas["default_mentalities"].append(dm)
        dd = dict(self.copiar("defaultteamdata", "teamid", mod_form)[0])
        dd["teamid"] = teamid
        if "defensivedepth" in dd:
            dd["defensivedepth"] = str(prof)
        self.novas["defaultteamdata"].append(dd)
        ts = dict(self.copiar("default_teamsheets", "teamid", modelo)[0])
        self.novas["default_teamsheets"].append(self._folha(ts, teamid, ordem, takers))

    def _folha(self, ts, teamid, ordem, takers):
        for k in ts:
            if k.startswith("playerid") or k.startswith("customsub"):
                ts[k] = "-1"
        for i, j in enumerate(ordem[:52]):
            ts[f"playerid{i}"] = str(j["playerid"])
        for k, j in takers.items():
            if k in ts:
                ts[k] = str(j["playerid"])
        ts["teamid"] = teamid
        return ts

    def _estadio(self, teamid, modelo, tm, cap_alvo, est_aj):
        nome_real = (est_aj.get("nome") or (tm.get("estadio") or {}).get("nome") or "").strip()
        escolhido = None
        if est_aj.get("stadiumid"):
            escolhido = next((d for d in self.tab("stadiums").dicts() if d["stadiumid"] == str(est_aj["stadiumid"])), None)
        if escolhido is None:
            escolhido = self.estadio_generico(cap_alvo, teamid)
        links = self.copiar("teamstadiumlinks", "teamid", modelo) or [dict(self.linha_vazia("teamstadiumlinks"))]
        for d in links[:1]:
            d.update(teamid=teamid, stadiumid=(escolhido or {}).get("stadiumid") or d.get("stadiumid") or "-1")
            self.novas["teamstadiumlinks"].append(d)
        if nome_real and self.tem_tabela("stadiumassignments"):
            self.novas["stadiumassignments"].append({"stadiumcustomname": limpar(nome_real, 51), "teamid": teamid})
        return {"nome": nome_real or None, "cidade": (tm.get("estadio") or {}).get("cidade"),
                "capacidade_real": (tm.get("estadio") or {}).get("capacidade"), "capacidade": cap_alvo,
                "generico": (escolhido or {}).get("name"), "generico_id": (escolhido or {}).get("stadiumid"),
                "generico_capacidade": int((escolhido or {}).get("capacity") or 0)}

    def _uniformes(self, teamid, modelo, cores):
        for d in self.copiar("teamkits", "teamtechid", modelo):
            tipo = d.get("teamkittypetechid")
            d.update(teamkitid=str(self.ids("kit", "teamkits", "teamkitid", "kit_inicio").novo()), teamtechid=teamid)
            par = {"0": cores["casa"], "1": cores["fora"], "2": cores["goleiro"], "3": cores["fora"]}.get(tipo)
            if par:
                (p, s) = par
                for comp, v in zip("rgb", p):
                    d[f"teamcolorprim{comp}"] = str(v)
                for comp, v in zip("rgb", s):
                    for k in (f"teamcolorsec{comp}", f"jerseynumbercolorprim{comp}", f"shortsnumbercolorprim{comp}", f"jerseynamecolor{comp}"):
                        if k in d:
                            d[k] = str(v)
            self.novas["teamkits"].append(d)

    def _tecnico(self, teamid, modelo, tec, aj, nacao_time, genero_time, atualizar=None):
        """Linha do técnico: a do time-modelo com nome, nascimento e nacionalidade da API (ou os escolhidos à mão) e a
        aparência de um técnico genérico do banco do mesmo gênero (nunca a cabeça de um técnico real)."""
        tec = dict(tec or {})
        nome = (aj.get("nome") or tec.get("nome") or "").strip()
        prim = (aj.get("primeiro") or tec.get("primeiro") or (nome.split()[0] if nome else "")).strip()
        prim = prim.split()[0] if prim else ""
        sob = (aj.get("sobrenome") or tec.get("sobrenome") or (" ".join(nome.split()[1:]) if nome else "")).strip()
        m = re.match(r"^[A-ZÀ-Ý][a-zà-ý]?\.\s*(\S.*)$", nome)
        if m and prim and not aj.get("nome"):            # "C. Ancelotti" -> "Carlo Ancelotti"
            nome = f"{prim} {m.group(1)}"
        if atualizar is not None and not {k for k in aj if k != "_foto"}:
            antes = self.linha("manager", atualizar)
            if K.tokens(sob, nome) & K.tokens(antes.get("surname"), antes.get("commonname")):
                tec = {**tec, "nome": antes.get("commonname") or nome}
                return {"nome": antes.get("commonname") or f"{antes.get('firstname', '')} {antes.get('surname', '')}".strip(),
                        "primeiro": antes.get("firstname"), "sobrenome": antes.get("surname"), "nascimento": tec.get("nascimento"),
                        "idade": idade_de(tec.get("nascimento")) if tec.get("nascimento") else None, "nacao": antes.get("nationality"),
                        "nacionalidade": self.nome_nacao.get(antes.get("nationality")), "genero": int(antes.get("gender") or 0),
                        "foto": tec.get("foto"), "api_id": tec.get("id"), "managerid": antes.get("managerid"), "da_api": True,
                        "mantido": True}
        nasc = aj.get("nascimento") or tec.get("nascimento")
        na = aj.get("nacao") or self.nacao(tec.get("nacionalidade")) or None
        genero = int(aj["genero"]) if aj.get("genero") not in (None, "") else 0
        if atualizar is not None:
            mg = dict(self.linha("manager", atualizar))
        else:
            base = self.copiar("manager", "teamid", modelo)
            mg = dict(base[0]) if base else self.linha_vazia("manager")
            mg.update(managerid=str(self.ids_jogador().novo()), teamid=teamid)
        if nome or prim or sob:
            mg.update(firstname=limpar(prim, 79), surname=limpar(sob, 79), commonname=limpar(nome or f"{prim} {sob}", 79), islicensed="0")
        nd = N.dias(nasc)
        if nd:
            mg["birthdate"] = str(nd)
        if na:
            mg["nationality"] = str(na)
        if "gender" in mg:
            mg["gender"] = str(genero)
        # aparência: de um técnico genérico do banco do mesmo gênero e nação (senão qualquer um do gênero)
        mudou_pessoa = atualizar is None or bool(nome)
        if mudou_pessoa:
            foto = aj.get("_foto") or {}
            alvo_doador = aj.get("aparencia") or ({k: v[0] for k, v in foto.items() if k in ("skintonecode", "haircolorcode")} or None)
            doador = self._aparencia_tecnico(mg.get("nationality"), genero, mg["managerid"], alvo_doador)
            if doador:
                for k in APARENCIA + ["height", "weight"]:
                    if k in mg and k in doador:
                        mg[k] = doador[k]
                sk = self.skins_de(doador.get("headassetid"))
                if sk:
                    sk["assetid"] = mg["managerid"]
                    self.novas["skins"].append(sk)
            mg["hashighqualityhead"] = "0"
            mg["headassetid"] = mg["managerid"]
            if foto:
                aplicar_foto(mg, foto)
            for k, v in (aj.get("aparencia") or {}).items():
                if k in mg:
                    mg[k] = str(v)
        if atualizar is not None:
            self.alterar_linha("manager", atualizar, mg)
        else:
            self.novas["manager"].append(mg)
        idade = idade_de(nasc) if nasc else None
        return {"nome": mg.get("commonname") or f"{mg.get('firstname', '')} {mg.get('surname', '')}".strip() or None,
                "primeiro": mg.get("firstname"), "sobrenome": mg.get("surname"), "nascimento": nasc, "idade": idade,
                "nacao": mg.get("nationality"), "nacionalidade": self.nome_nacao.get(mg.get("nationality")),
                "genero": genero, "foto": tec.get("foto"), "api_id": tec.get("id"), "managerid": mg["managerid"],
                "da_api": bool(tec.get("nome")), "aparencia": {k: mg.get(k) for k in ("skintonecode", "haircolorcode", "hairtypecode",
                                                                                      "facialhairtypecode", "headtypecode")},
                "aparencia_origem": "manual" if aj.get("aparencia") else "foto" if foto else "banco"}

    def _aparencia_tecnico(self, nacao, genero, chave, alvo=None):
        cands = [d for d in self.tab("manager").dicts() if d.get("hashighqualityhead") == "0" and d.get("gender", "0") == str(genero)
                 and d.get("islicensed") == "0"]
        if not cands:
            cands = [d for d in self.tab("manager").dicts() if d.get("hashighqualityhead") == "0" and d.get("gender", "0") == str(genero)]
        if not cands:
            # sem técnicos genéricos do gênero: um jogador genérico do banco (as colunas de aparência são as mesmas)
            linha = self.perfil.aparencia_de(nacao, genero, chave)
            return dict(zip(self.perfil.campos, linha)) if linha is not None else None
        mesma = [d for d in cands if d.get("nationality") == str(nacao)] or cands
        if alvo:
            def dist(d):
                return sum(abs(int(d.get(k) or 0) - int(v)) / 10.0 if k == "skintonecode" else (int(d.get(k) or 0) != int(v))
                           for k, v in alvo.items() if k in d)
            m = min(dist(d) for d in cands)
            mesma = [d for d in mesma if dist(d) <= m + 0.01] or [d for d in cands if dist(d) <= m + 0.01]
        return mesma[int(N.semente("tecnico", chave) * len(mesma)) % len(mesma)]

    # ---- jogadores
    def _preparar_jogadores(self, dados, nivel_time, genero, ajustes, fotos=None):
        ref_idade = data_ref_tm(dados)
        self.excluidos = []
        coef = N.carregar_coef()
        jogs = []
        for j0 in dados["jogadores"]:
            j = dict(j0)
            j["stats"] = j.get("stats") or {}
            aj = ajustes.get(str(j["id"])) or ajustes.get(j["id"]) or {}
            if aj.get("excluir"):
                self.excluidos.append({"api_id": j["id"], "nome": j.get("nome") or str(j["id"]), "foto": j.get("foto")})
                continue
            if aj.get("nascimento"):
                j["nascimento"] = aj["nascimento"]
                j["idade"] = idade_de(aj["nascimento"], ref_idade) or j.get("idade")
            elif ref_idade and j.get("nascimento"):            # elenco antigo: a idade que tinha na época
                j["idade"] = idade_de(j["nascimento"], ref_idade) or j.get("idade")
            if not j.get("idade") and j.get("nascimento"):
                j["idade"] = idade_de(j["nascimento"])
            j["no_banco"] = self.ja_no_banco(j, genero) if not dados.get("selecao") else None
            pos, origem = N.posicao_principal(j)
            j["pos"], j["pos_origem"] = pos, origem
            if aj.get("pos") is not None:
                j["pos"], j["pos_origem"] = int(aj["pos"]), "manual"
            if aj.get("altura"):
                j["altura"] = int(aj["altura"])
            if aj.get("peso"):
                j["peso"] = int(aj["peso"])
            jogs.append(j)
        N.distribuir_posicoes(jogs)
        tm = dados.get("fonte") == "transfermarkt"
        self.nivel_valor = None
        if tm:
            # Transfermarkt: nota pelo valor de mercado e pela idade; o nível escolhido desloca o time inteiro (no
            # automático o nível é o próprio nível pelo valor, então não desloca nada)
            coef_tm = N.carregar_coef_tm()
            vals = [j["valor"] for j in jogs if j.get("valor")]
            piso = min(vals) * 0.6 if vals else 50000
            brutos = {j["id"]: N.overall_tm(j.get("valor") or piso, j.get("idade"), coef_tm, arredondar=False) for j in jogs}
            top = sorted(brutos.values(), reverse=True)[:14]
            self.nivel_valor = round(sum(top) / max(1, len(top)), 1)
            desloc = (float(nivel_time) - self.nivel_valor) if nivel_time else 0.0
        else:
            brutos = {j["id"]: N.overall_estimado(nivel_time, j["stats"], j.get("idade"), coef, arredondar=False) for j in jogs}
        media = sum(brutos.values()) / max(1, len(brutos))
        esticar = float(self.op.get("espalhamento") or 1.25)
        ids = self.ids_jogador()
        for j in jogs:                                     # ids escolhidos à mão primeiro (não podem ir para outro)
            aj = ajustes.get(str(j["id"])) or {}
            if aj.get("playerid"):
                j["playerid"] = ids.reservar(aj["playerid"], "playerid")
                j["playerid_manual"] = True
        usar_todos = bool(ajustes.get("_usar_db_todos"))
        for j in jogs:                                     # o jogador do banco no lugar de um novo (transferência)
            aj = ajustes.get(str(j["id"])) or {}
            nb = j.get("no_banco")
            quer = aj.get("usar_db")
            if nb and (quer is True or (quer is None and usar_todos and nb["forte"])):
                j["usar_db"] = nb["playerid"]
                j["playerid"] = int(nb["playerid"])
        for j in jogs:
            aj = ajustes.get(str(j["id"])) or {}
            if j.get("usar_db"):
                self._dados_do_banco(j)
                j["camisa_manual"] = int(aj["camisa"]) if aj.get("camisa") else None
                j["capitao_manual"] = bool(aj.get("capitao"))
                continue
            if tm:
                ov = int(round(max(40, min(94, brutos[j["id"]] + desloc))))
            else:
                ov = int(round(max(40, min(92, media + esticar * (brutos[j["id"]] - media)))))
            j["overall_auto"] = ov
            j["overall"] = int(aj.get("overall") or ov)
            j["potential_auto"] = N.potencial(j["overall"], j.get("idade"), j["id"])
            j["potential"] = int(aj.get("potencial") or j["potential_auto"])
            if aj.get("pe"):
                j["pe"] = int(aj["pe"])
            elif j.get("pe_tm") in ("left", "right", "both"):
                j["pe"] = 2 if j["pe_tm"] == "left" else 1
            else:
                j["pe"] = N.pe_preferido(j)
            j["altura"], j["peso"] = N.fisico(self.perfil, j, genero)
            j["atr"] = N.gerar_atributos(self.perfil, j, j["overall"], genero)
            if j.get("pe_tm") == "both":                   # ambidestro na Transfermarkt
                j["atr"]["weakfootabilitytypecode"] = max(4, j["atr"].get("weakfootabilitytypecode", 3))
            if aj.get("perna_ruim"):
                j["atr"]["weakfootabilitytypecode"] = int(aj["perna_ruim"])
            if aj.get("dribles"):
                j["atr"]["skillmoves"] = int(aj["dribles"])
            for k, v in (aj.get("atr") or {}).items():
                if k in j["atr"] and v not in (None, ""):
                    j["atr"][k] = int(v)
            j["atr_manual"] = sorted((aj.get("atr") or {}).keys())
            j["nomes"] = nomes_jogador(j) if not aj.get("nomes") else tuple(aj["nomes"])
            j["nacao_manual"] = aj.get("nacao")
            j["camisa_manual"] = int(aj["camisa"]) if aj.get("camisa") else None
            j["capitao_manual"] = bool(aj.get("capitao"))
            j["posicoes2_manual"] = aj.get("posicoes2")
            j["aparencia_manual"] = aj.get("aparencia") or {}
            j["foto_alvo"] = (fotos or {}).get(str(j["id"]))
            if "playerid" not in j:
                j["playerid"] = ids.novo()
        jogs.sort(key=lambda j: -(j["stats"].get("minutos") or 0) - j["overall"])
        if len(jogs) > MAX_JOGADORES:
            self.avisos.append(f"{dados['time']['nome']}: {len(jogs)} jogadores; ficaram os {MAX_JOGADORES} com mais minutos.")
            jogs = jogs[:MAX_JOGADORES]
        return jogs

    def _escalar(self, jogs, vagas, parcial=False):
        """11 titulares, um por vaga, pela melhor combinação nota x posição (goleiro primeiro). parcial: com menos de 11
        jogadores, as vagas que sobram ficam None."""
        livres = list(jogs)
        escolha = [None] * 11
        ordem = sorted(range(11), key=lambda i: (0 if vagas[i] == 0 else 1, sum(1 for j in jogs if j["pos"] == VAGA_BASE.get(vagas[i]))))
        for i in ordem:
            base = VAGA_BASE.get(vagas[i], 14)
            if not livres:
                break
            melhor = max(livres, key=lambda j: j["overall"] - 3.0 * custo_pos(j["pos"], base) + ((j.get("stats") or {}).get("titular") or 0) * 0.15
                         + (40 if j.get("titular_manual") else 0))
            escolha[i] = melhor
            livres.remove(melhor)
        if any(e is None for e in escolha) and not parcial:
            raise ValueError("O time tem menos de 11 jogadores.")
        return escolha

    def _notas_time(self, tit, vagas):
        def media(js):
            return int(round(sum(j["overall"] for j in js) / len(js))) if js else 0
        defesa = [j for j, v in zip(tit, vagas) if VAGA_BASE.get(v) in (0, 2, 3, 5, 7, 8)]
        meio = [j for j, v in zip(tit, vagas) if VAGA_BASE.get(v) in (10, 12, 14, 16, 18)]
        ataque = [j for j, v in zip(tit, vagas) if VAGA_BASE.get(v) in (21, 23, 25, 27)] or meio
        return {"geral": media(tit), "defesa": media(defesa), "meio": media(meio), "ataque": media(ataque)}

    def _cores(self, dados):
        c = dados.get("cores") or {}

        def par(lista, padrao):
            if lista:
                p, s = lista[0]
                return cor_hex(p, padrao[0]), cor_hex(s, padrao[1])
            return padrao
        casa = par(c.get("casa"), ((200, 200, 200), (30, 30, 30)))
        fora = par(c.get("fora"), ((240, 240, 240), casa[0]))
        gol = par(c.get("goleiro"), ((40, 160, 70), (255, 255, 255)))
        return {"casa": casa, "fora": fora, "goleiro": gol, "time": [casa[0], casa[1], fora[0]]}

    def _dados_do_banco(self, j):
        """Nota, posição, atributos, nação e aparência do jogador do banco (ele é transferido, não criado)."""
        ns = self.indices("players", playerid=j["usar_db"])
        d = self.linha("players", ns[0]) if ns else {}
        j["existente"] = True
        j["origem"] = "banco"
        j["overall"] = j["overall_auto"] = int(d.get("overallrating") or 60)
        j["potential"] = j["potential_auto"] = int(d.get("potential") or j["overall"])
        j["pos"], j["pos_origem"] = int(d.get("preferredposition1") or j.get("pos") or 14), "banco"
        j["pe"] = int(d.get("preferredfoot") or 1)
        j["altura"], j["peso"] = int(d.get("height") or 180), int(d.get("weight") or 75)
        j["atr"] = {k: int(d.get(k) or 0) for k in self.perfil.atr if k in d}
        for k in ("weakfootabilitytypecode", "skillmoves"):
            if k in d:
                j["atr"][k] = int(d[k])
        j["nacao"] = d.get("nationality")
        j["nascimento"] = j.get("nascimento") or None
        j["aparencia"] = {k: d.get(k) for k in ("skintonecode", "haircolorcode", "hairtypecode", "facialhairtypecode",
                                                "facialhaircolorcode", "headtypecode", "eyecolorcode", "bodytypecode")}
        j["aparencia_origem"] = "banco"
        j["posicoes2"] = [int(d[f"preferredposition{i}"]) for i in range(2, 5) if str(d.get(f"preferredposition{i}", "-1")) not in ("-1", "")]
        nb = j.get("no_banco") or {}
        info = self.indice_jogadores().info.get(str(j["usar_db"]), {})
        j["nomes"] = (info.get("primeiro", ""), info.get("sobrenome", ""), info.get("comum") or info.get("nome", ""), info.get("camisa", ""))
        j["clube"] = nb.get("clube_nome")
        j["atr_manual"] = []

    def clube_por_nome(self, nome, genero=0, tm_id=None):
        """teamid do clube do banco pelo id da Transfermarkt (mapa) ou pelo nome (claro: ≥ 0,9 e nenhum outro perto),
        entre os clubes do mesmo gênero; None se não estiver no banco."""
        if tm_id:
            tid = K.ler_mapa().get("tm_times", {}).get(str(tm_id))
            if tid and self.atuais("teams", teamid=tid):
                return tid
        if not nome or re.search(r"\b(U-?\d\d|Sub-?\d\d|B|II|Youth|Reserves?|Juniors?|Academy)\b", nome, re.I):
            return None
        if self._nomes_times is None:
            self.nome_time("0")
        gen = {d["teamid"]: d.get("gender") or "0" for d in self.tab("teams").dicts()}
        cands = sorted(((K.nota_time(nome, n), tid) for tid, n in self._nomes_times.items()
                        if self.liga_de.get(tid) not in LIGAS_NAO_CLUBE and gen.get(tid) == str(genero) and tid != TIME_SEM_CONTRATO),
                       reverse=True)
        if cands and cands[0][0] >= 0.9 and (len(cands) < 2 or cands[1][0] < cands[0][0] - 0.15):
            return cands[0][1]
        return None

    def elenco_restante(self, teamid):
        """Quantos jogadores o time do banco tem agora (com as mudanças do projeto)."""
        return len(self.atuais("teamplayerlinks", teamid=teamid)) + len(self.novas_de("teamplayerlinks", teamid=teamid))

    def clubes_afetados(self, jogs):
        """Clubes do banco que perdem jogadores para este time: [{teamid, nome, saem, ficam}]."""
        saem = collections.Counter(j["no_banco"]["clube"] for j in jogs if j.get("usar_db") and (j.get("no_banco") or {}).get("clube"))
        return [{"teamid": t, "nome": self.nome_time(t), "saem": n, "ficam": self.elenco_restante(t) - n} for t, n in saem.most_common()]

    # ---- passes livres (Sem Contrato) para completar elencos com menos de 11
    def livres(self, n, alvo, nacao, genero, posicoes=()):
        """playerids de `n` jogadores sem contrato (time 111592, ou sem clube nenhum) para completar um elenco: nota perto de `alvo`, da mesma
        nação (senão da mesma confederação), até 34 anos de preferência; primeiro um goleiro e as linhas que faltam
        (posicoes: posições dos que já estão no elenco)."""
        usados = getattr(self, "_livres_usados", set())
        self._livres_usados = usados
        idx = self.indice_jogadores()
        conf = self.confed.get(str(nacao))
        cand = []
        pool = [d["playerid"] for d in self.atuais("teamplayerlinks", teamid=TIME_SEM_CONTRATO)]
        # sem vínculo com clube nenhum (no futebol feminino o Sem Contrato fica vazio: as jogadoras livres só estão na
        # seleção); ídolos da Liga Clássica não entram
        pool += [pid for pid, ts in idx.times_de.items() if TIME_SEM_CONTRATO not in ts
                 and all(self.liga_de.get(t) in LIGAS_NAO_CLUBE and self.liga_de.get(t) not in LIGAS_LENDAS for t in ts)]
        pool += [pid for pid in idx.info if pid not in idx.times_de]
        for pid in dict.fromkeys(pool):
            i = idx.info.get(pid)
            if not i or pid in usados or str(i["genero"]) != str(genero):
                continue
            if any(self.liga_de.get(t) not in LIGAS_NAO_CLUBE and t != TIME_SEM_CONTRATO for t in
                   (x["teamid"] for x in self.atuais("teamplayerlinks", playerid=pid))):
                continue                                   # já foi para um clube neste projeto
            pen = 0 if str(i["nacao"]) == str(nacao) else 3 if conf and self.confed.get(str(i["nacao"])) == conf else 6
            pen += 3 if (i["idade"] or 25) > 34 else 0
            cand.append((abs(i["overall"] - alvo) + pen, pid, i["pos"]))
        cand.sort()
        linha = lambda p: "G" if p == 0 else "D" if p in (2, 3, 5, 7, 8) else "M" if p in (10, 12, 14, 16, 18) else "A"  # noqa: E731
        tem = collections.Counter(linha(int(p)) for p in posicoes)
        precisa = {"G": MINIMO_GOLEIROS, "D": 6, "M": 6, "A": 4}  # um elenco de 18: 2 goleiros, 6 + 6 + 4 na linha
        escolha = []
        for g, q in precisa.items():                       # primeiro o que falta em cada setor (goleiros antes)
            for _, pid, p in cand:
                if len(escolha) >= n or tem[g] >= q:
                    break
                if linha(p) == g and pid not in escolha:
                    escolha.append(pid)
                    tem[g] += 1
        for _, pid, _ in cand:
            if len(escolha) >= n:
                break
            if pid not in escolha:
                escolha.append(pid)
        usados.update(escolha)
        return escolha

    def jogador_livre(self, pid):
        """Um jogador sem contrato no formato dos jogadores preparados (entra no time como os "do banco")."""
        idx = self.indice_jogadores()
        i = idx.info[str(pid)]
        j = {"id": f"livre{pid}", "nome": i["nome"], "idade": i["idade"], "stats": {}, "usar_db": str(pid), "playerid": int(pid),
             "no_banco": {"playerid": str(pid), "nome": i["nome"], "clube": TIME_SEM_CONTRATO, "clube_nome": "Sem Contrato",
                          "overall": i["overall"], "idade": i["idade"], "forte": True, "idolo": False}}
        self._dados_do_banco(j)
        j["origem"] = "livre"
        j["nascimento"] = str(N.data_de_dias(i["nascimento"])) if i["nascimento"] else None
        j["camisa_manual"] = None
        j["capitao_manual"] = False
        return j

    def completar_clube(self, teamid, minimo=MINIMO_ELENCO, goleiros=MINIMO_GOLEIROS):
        """Time do banco com menos de `minimo` jogadores ou de `goleiros` goleiros: entram jogadores sem contrato (nota
        perto da média do elenco, mesma nação do time). Devolve os nomes de quem entrou."""
        vincs = self.atuais("teamplayerlinks", teamid=teamid) + self.novas_de("teamplayerlinks", teamid=teamid)
        idx = self.indice_jogadores()
        gks = sum(1 for v in vincs if (idx.info.get(v["playerid"]) or {}).get("pos") == 0
                  or any(p.get("preferredposition1") == "0" for p in self.novas_de("players", playerid=v["playerid"])))
        falta = max(minimo - len(vincs), goleiros - gks)
        if falta <= 0:
            return []
        ovs, poss, nacs = [], [], collections.Counter()
        for v in vincs:
            i = idx.info.get(v["playerid"])
            if i:
                ovs.append(i["overall"])
                poss.append(i["pos"])
                nacs[i["nacao"]] += 1
            else:
                for p in self.novas_de("players", playerid=v["playerid"]):
                    ovs.append(int(p["overallrating"]))
                    poss.append(int(p["preferredposition1"]))
        tn = self.atuais("teamnationlinks", teamid=teamid)
        nacao = tn[0]["nationid"] if tn else (nacs.most_common(1)[0][0] if nacs else self.pais_liga.get(self.liga_de.get(teamid), "211"))
        t = self.atuais("teams", teamid=teamid)
        genero = (t[0].get("gender") or "0") if t else "0"
        alvo = (sum(ovs) / len(ovs)) if ovs else self.nivel_time_db.get(teamid, 62) - 4
        nomes = []
        for pid in self.livres(falta, alvo, nacao, genero, poss):
            usados = {d["jerseynumber"] for d in self.atuais("teamplayerlinks", teamid=teamid)} | \
                     {d["jerseynumber"] for d in self.novas_de("teamplayerlinks", teamid=teamid)}
            num = next((k for k in range(2, 99) if str(k) not in usados), 99)
            if not self.alterar("teamplayerlinks", {"teamid": teamid, "jerseynumber": num, "position": 29}, playerid=pid,
                                teamid=TIME_SEM_CONTRATO):          # sem vínculo nenhum (jogadora livre): vínculo novo
                tl = self.linha_vazia("teamplayerlinks")
                tl.update(teamid=teamid, playerid=str(pid), jerseynumber=str(num), position="29", form="3",
                          artificialkey=str(self.ids("tpl", "teamplayerlinks", "artificialkey").novo()))
                self.novas["teamplayerlinks"].append(tl)
            nomes.append(f"{idx.info[pid]['nome']} ({idx.info[pid]['overall']})")
        return nomes

    def aplicar_tatica(self, teamid, formacao=None, profundidade=None, saida=None):
        """Time do banco: troca a formação (posições, papéis e deslocamentos de um time do banco com ela), a linha
        defensiva e a saída de bola. A escalação é refeita depois (reescalar)."""
        fo = self.atuais("formations", teamid=teamid)
        if formacao and fo and fo[0]["formationname"] != formacao:
            mod_form = self.modelo_formacao(formacao, teamid)
            if mod_form != teamid:
                self._trocar_formacao(teamid, mod_form, self.copiar("formations", "teamid", mod_form)[0])
        vals = {k: v for k, v in (("buildupplay", saida), ("defensivedepth", profundidade)) if v}
        if vals:
            t = self.atuais("teams", teamid=teamid)
            if t:
                self.alterar("teams", {k: v for k, v in vals.items() if k in t[0]}, teamid=teamid)
            dm = self.atuais("default_mentalities", teamid=teamid)
            if dm:
                self.alterar("default_mentalities", {k: v for k, v in vals.items() if k in dm[0]}, teamid=teamid)
            if profundidade and self.atuais("defaultteamdata", teamid=teamid):
                self.alterar("defaultteamdata", {"defensivedepth": profundidade}, teamid=teamid)

    def _transferir_do_banco(self, j, teamid):
        """Tira o jogador do clube antigo (o vínculo com a seleção fica) e apaga o empréstimo, se houver."""
        pid = str(j["usar_db"])
        antigo = self.clube_db(pid)
        if antigo:
            self.remover("teamplayerlinks", playerid=pid, teamid=antigo)
            self.clubes_mexidos.add(antigo)
        # sem contrato (o time 111592 fica numa liga especial, então clube_db não o vê): sai de lá também
        self.remover("teamplayerlinks", playerid=pid, teamid=TIME_SEM_CONTRATO)
        if self.tem_tabela("playerloans"):
            self.remover("playerloans", playerid=pid)

    def _linhas_jogador(self, j, teamid, genero):
        if j.get("usar_db"):
            self._transferir_do_banco(j, teamid)
            return
        pf = self.perfil
        c = pf.c
        base = pf.jogador_base(j["pos"], j["overall"], genero, j["id"])
        p = dict(zip(pf.campos, base))
        pid = str(j["playerid"])
        nac = self.nacao_jogador(j)
        j["nacao"] = str(nac)
        alvo = j.get("foto_alvo") or None
        cara = pf.aparencia_de(nac, genero, j["id"], alvo=alvo)
        if cara is not None:
            for k in APARENCIA:
                if k in c:
                    p[k] = cara[c[k]]
            sk = self.skins_de(cara[c["headassetid"]]) if "headassetid" in c else None
            if sk:
                sk["assetid"] = pid
                self.novas["skins"].append(sk)
        if alvo:                                          # o que a foto mostrou vale sobre o doador
            aplicar_foto(p, alvo)
        for k, v in (j.get("aparencia_manual") or {}).items():
            if k in p:
                p[k] = str(v)
        j["aparencia"] = {k: p.get(k) for k in ("skintonecode", "haircolorcode", "hairtypecode", "facialhairtypecode",
                                                "facialhaircolorcode", "headtypecode", "eyecolorcode", "bodytypecode")}
        j["aparencia_origem"] = "manual" if j.get("aparencia_manual") else "foto" if alvo else "nação"
        nasc = N.dias(j.get("nascimento"))
        if not nasc:
            idade = j.get("idade") or 25
            nasc = N.dias(f"{self.op['ano'] - idade}-{1 + int(N.semente('mes', j['id']) * 12):02d}-15")
        p.update(playerid=pid, headassetid=pid, hashighqualityhead="0", firstnameid="0", lastnameid="0", commonnameid="0",
                 playerjerseynameid="0", birthdate=str(nasc), height=str(j["altura"]), weight=str(j["peso"]),
                 nationality=str(nac), preferredfoot=str(j["pe"]), preferredposition1=str(j["pos"]),
                 overallrating=str(j["overall"]), potential=str(j["potential"]), gender=str(genero), isretiring="0",
                 internationalrep=str(3 if j["overall"] >= 84 else 2 if j["overall"] >= 78 else 1),
                 contractvaliduntil=str(self.op["ano"] + 1 + int(N.semente("contrato", j["id"]) * 4)),
                 playerjointeamdate=str(N.dias(f"{self.op['ano'] - 1}-07-01")))
        if j.get("posicoes2_manual") is not None:
            sec = [int(x) for x in j["posicoes2_manual"] if int(x) != j["pos"]]
        else:
            sec = [int(x) for x in j.get("posicoes_tm") or [] if int(x) != j["pos"]]
            sec += [int(k) for k, _ in sorted((j.get("posicoes_escalacao") or {}).items(), key=lambda kv: -kv[1])
                    if int(k) != j["pos"] and int(k) not in sec]
        j["posicoes2"] = sec[:3]
        for i in range(2, 8):
            k = f"preferredposition{i}"
            if k in p:
                p[k] = str(sec[i - 2]) if len(sec) > i - 2 else "-1"
        for k, v in j["atr"].items():
            if k in p:
                p[k] = str(v)
        a = j["atr"]
        if j["pos"] == 0:
            resumo = [a["gkdiving"], a["gkhandling"], a["gkkicking"], a["gkreflexes"], a["sprintspeed"], a["gkpositioning"]]
        else:
            resumo = [0.45 * a["acceleration"] + 0.55 * a["sprintspeed"],
                      0.45 * a["finishing"] + 0.2 * a["longshots"] + 0.2 * a["shotpower"] + 0.05 * a["positioning"] + 0.05 * a["volleys"] + 0.05 * a["penalties"],
                      0.2 * a["vision"] + 0.2 * a["crossing"] + 0.05 * a["freekickaccuracy"] + 0.35 * a["shortpassing"] + 0.15 * a["longpassing"] + 0.05 * a["curve"],
                      0.1 * a["agility"] + 0.05 * a["balance"] + 0.05 * a["reactions"] + 0.3 * a["ballcontrol"] + 0.5 * a["dribbling"],
                      0.2 * a["interceptions"] + 0.1 * a["headingaccuracy"] + 0.3 * a["defensiveawareness"] + 0.3 * a["standingtackle"] + 0.1 * a["slidingtackle"],
                      0.05 * a["jumping"] + 0.25 * a["stamina"] + 0.5 * a["strength"] + 0.2 * a["aggression"]]
        for k, v in zip(("pacdiv", "shohan", "paskic", "driref", "defspe", "phypos"), resumo):
            if k in p:
                p[k] = str(int(round(v)))
        self.novas["players"].append(p)
        prim, sob, com, cam = j["nomes"]
        en = self.linha_vazia("editedplayernames")
        en.update(playerid=pid, firstname=prim, surname=sob, commonname=com, playerjerseyname=cam)
        self.novas["editedplayernames"].append(en)

    def _publico(self, j):
        prim, sob, com, cam = j["nomes"] if j.get("nomes") else ("", "", j.get("nome", ""), "")
        st = j.get("stats") or {}
        return {"api_id": j.get("id"), "playerid": j["playerid"], "playerid_manual": bool(j.get("playerid_manual")),
                "existente": bool(j.get("existente")), "origem": j.get("origem"), "clube": j.get("clube"),
                "nome": com or f"{prim} {sob}".strip() or j.get("nome"),
                "nome_api": j.get("nome"), "primeiro": prim, "sobrenome": sob, "comum": com, "camisa_nome": cam,
                "camisa": j.get("camisa"), "camisa_manual": bool(j.get("camisa_manual")), "pos": j["pos"],
                "pos_nome": N.NOME_POS.get(j["pos"], j["pos"]), "pos_origem": j.get("pos_origem"), "posicoes2": j.get("posicoes2") or [],
                "overall": j["overall"], "overall_auto": j.get("overall_auto", j["overall"]), "potential": j.get("potential"),
                "potential_auto": j.get("potential_auto", j.get("potential")), "idade": j.get("idade"),
                "nascimento": j.get("nascimento"), "nacionalidade": self.nome_nacao.get(j.get("nacao")) or j.get("nacionalidade"),
                "nacao": j.get("nacao"), "altura": j.get("altura"), "peso": j.get("peso"), "pe": j.get("pe"),
                "perna_ruim": (j.get("atr") or {}).get("weakfootabilitytypecode"), "dribles": (j.get("atr") or {}).get("skillmoves"),
                "foto": j.get("foto"), "minutos": st.get("minutos") or 0, "jogos": st.get("jogos") or 0,
                "nota_api": st.get("nota"), "gols": st.get("gols") or 0, "capitao": bool(j.get("capitao") or j.get("capitao_tm")),
                "valor": j.get("valor"), "no_banco": j.get("no_banco"), "usar_db": j.get("usar_db"),
                "atr": dict(j.get("atr") or {}), "atr_manual": j.get("atr_manual") or [],
                "aparencia": j.get("aparencia") or {}, "aparencia_origem": j.get("aparencia_origem")}

    # ---- seleções
    def selecao_existente(self, nacao, genero):
        liga = LIGA_SELECOES.get(genero, "78")
        for d in self.atuais("teamnationlinks", leagueid=liga, nationid=nacao):
            t = self.atuais("teams", teamid=d["teamid"])
            if t and t[0].get("gender", "0") == str(genero):
                return d["teamid"]
        return None

    def criar_selecao(self, dados, nivel, genero=0, ajustes=None, extra=None):
        """Seleção (cria ou atualiza): convocação da API casada com os jogadores do banco + os melhores da nação no
        banco até cumprir o SQUAD_SELECTION. extra: nacao, limites {grupo: (min, max)}, idade_maxima, criar_faltantes,
        tatica, tecnico, teamid (manual, só ao criar), modelo, internationals (objeto de internationals.py)."""
        ajustes = ajustes or {}
        ex = extra or {}
        tm = dados["time"]
        nacao = str(ex.get("nacao") or self.nacao(tm.get("pais") or tm.get("nome")) or "")
        if not nacao:
            raise ValueError(f"{tm['nome']}: nação não encontrada no banco (tabela nations).")
        limites = ex.get("limites") or SELECAO_PADRAO
        idade_max = int(ex.get("idade_maxima") or 35)
        existente = self.selecao_existente(nacao, genero)
        idx = self.indice_jogadores()
        pl = self.tab("players")
        c = {n: i for i, n in enumerate(pl.campos)}
        nomes_time = {t["teamid"]: t["nome"] for t in self.b.times(self.idioma)}
        clube_de = {}
        for d in self.tab("teamplayerlinks").dicts():
            lid = self.liga_de.get(d["teamid"])
            if lid not in LIGA_SELECOES.values():
                clube_de.setdefault(d["playerid"], d["teamid"])

        def jog_db(pid, origem, numero=None, api=None):
            l = idx.linhas[pid]
            info = idx.info[pid]
            g = lambda k: int(l[c[k]]) if k in c else 0  # noqa: E731
            atr = {k: g(k) for k in N.ATR if k in c}
            return {"id": (api or {}).get("id") or f"db{pid}", "playerid": int(pid), "existente": True, "origem": origem,
                    "nome": info["nome"], "nomes": (info["primeiro"], info["sobrenome"], info["comum"], info["camisa"]),
                    "overall": info["overall"], "potential": g("potential"), "pos": info["pos"], "idade": info["idade"],
                    "nascimento": str(N.data_de_dias(info["nascimento"])) if info["nascimento"] else None,
                    "nacao": info["nacao"], "altura": g("height"), "peso": g("weight"), "pe": g("preferredfoot"), "atr": atr,
                    "numero": numero, "stats": {}, "foto": (api or {}).get("foto"), "clube": nomes_time.get(clube_de.get(pid)),
                    "pos_origem": "banco"}
        # 1. convocação da API casada com o banco
        pool, faltam, usados = [], [], set()
        for a in dados.get("jogadores") or []:
            aj = ajustes.get(str(a["id"])) or {}
            if aj.get("excluir"):
                continue
            if aj.get("playerid_banco"):
                pid = str(aj["playerid_banco"])
                cand = [(1.0, pid)] if pid in idx.info else []
            else:
                cand = idx.buscar(a.get("nome"), a.get("primeiro", ""), a.get("sobrenome", ""), a.get("nascimento"), a.get("idade"),
                                  nacao, genero, minimo=0.6, so_nacao=True)
            cand = [x for x in cand if x[1] not in usados and self.liga_de.get(clube_de.get(x[1])) not in LIGAS_LENDAS]
            if cand:
                pid = cand[0][1]
                usados.add(pid)
                j = jog_db(pid, "convocado", a.get("numero"), a)
                j["casamento"] = cand[0][0]
                pool.append(j)
            else:
                faltam.append(a)
        # 2. jogadores escolhidos à mão (do banco)
        for pid in ex.get("incluir") or []:
            pid = str(pid)
            if pid in idx.info and pid not in usados:
                usados.add(pid)
                pool.append(jog_db(pid, "manual"))
        excluir_db = {str(x) for x in ex.get("excluir_db") or []}
        pool = [j for j in pool if str(j["playerid"]) not in excluir_db]
        # 3. completar pelo banco até o mínimo de cada grupo (os melhores da nação, até a idade máxima)
        grupo = lambda j: GRUPO_SELECAO.get(j["pos"], "CM")  # noqa: E731
        cont = collections.Counter(grupo(j) for j in pool)
        reserva = sorted((i for pid, i in idx.info.items() if i["nacao"] == nacao and str(i["genero"]) == str(genero)
                          and pid not in usados and pid not in excluir_db and (i["idade"] or 99) <= idade_max
                          and self.liga_de.get(clube_de.get(pid)) not in ("382", "383", *LIGAS_LENDAS)),
                         key=lambda i: -i["overall"])
        for g, (mn, mx) in limites.items():
            for i in reserva:
                if cont[g] >= mn:
                    break
                if GRUPO_SELECAO.get(i["pos"], "CM") == g and i["playerid"] not in usados:
                    usados.add(i["playerid"])
                    pool.append(jog_db(i["playerid"], "completado"))
                    cont[g] += 1
        # 4. respeitar o máximo de cada grupo (saem primeiro os completados, depois os de nota mais baixa)
        for g, (mn, mx) in limites.items():
            dos = [j for j in pool if grupo(j) == g]
            if len(dos) > mx:
                dos.sort(key=lambda j: (j["origem"] == "convocado", j["origem"] == "manual", j["overall"]))
                for j in dos[:len(dos) - mx]:
                    pool.remove(j)
        # 5. convocados que não estão no banco: criados (sem clube) os escolhidos — "criar os que faltam" marca todos e
        # cada um pode ser marcado ou desmarcado (criar = {api_id: bool})
        escolhidos = ex.get("criar") or {}
        criar = lambda a: escolhidos.get(str(a["id"]), bool(ex.get("criar_faltantes")))  # noqa: E731
        criados = []
        if any(criar(a) for a in faltam):
            base_ov = sorted((j["overall"] for j in pool), reverse=True)
            ref = base_ov[min(len(base_ov) - 1, 18)] if base_ov else int(nivel) - 6
            for a in faltam:
                if not criar(a):
                    continue
                a = dict(a, nacionalidade=self.nome_nacao.get(nacao), stats={})
                criados.append(a)
            novos = self._preparar_jogadores({"time": tm, "jogadores": criados}, ref + 1.8, genero, ajustes, ex.get("fotos"))
            for j in novos:
                j.update(origem="novo", existente=False, nacao_manual=j.get("nacao_manual") or nacao)
                pool.append(j)
        for j in pool:                                      # ajustes de nota/posição/camisa valem para a seleção
            aj = ajustes.get(str(j["id"])) or ajustes.get(f"db{j['playerid']}") or {}
            if j.get("existente"):
                if aj.get("camisa"):
                    j["camisa_manual"] = int(aj["camisa"])
                if aj.get("capitao"):
                    j["capitao_manual"] = True
        cont = collections.Counter(grupo(j) for j in pool)
        falta_grupo = {g: mn - cont[g] for g, (mn, _) in limites.items() if cont[g] < mn}
        if len(pool) < 11:
            raise ValueError(f"{tm['nome']}: só {len(pool)} jogadores — a nação tem poucos jogadores no banco.")
        # 6. time: o que já existe (atualiza) ou um novo a partir de uma seleção-modelo
        tat = dict(ex.get("tatica") or {})
        if existente:
            teamid = existente
            modelo = existente
            fo_atual = self.copiar("formations", "teamid", teamid)
            formacao = tat.get("formacao") or dados.get("formacao") or (fo_atual[0]["formationname"] if fo_atual else None)
        else:
            modelo = self.time_modelo(nacao, nivel, genero, ex.get("modelo"), selecao=True)
            formacao = tat.get("formacao") or dados.get("formacao")
            teamid = str(self.ids_time().reservar(ex["teamid"], "teamid") if ex.get("teamid") else self.ids_time().novo())
        mod_form = self.modelo_formacao(formacao, modelo)
        fo_mod = self.copiar("formations", "teamid", mod_form)[0]
        vagas = [int(fo_mod[f"position{i}"]) for i in range(11)]
        # números: da convocação; senão o que o jogador já usava na seleção
        if existente:
            antes = {d["playerid"]: int(d["jerseynumber"]) for d in self.atuais("teamplayerlinks", teamid=teamid)}
            for j in pool:
                if not j.get("numero") and str(j["playerid"]) in antes:
                    j["numero"] = antes[str(j["playerid"])]
        titulares, reservas, ordem = self._escalacao(pool, vagas)
        for j in ordem:
            if not j.get("existente"):
                # o convocado criado vai para o clube dele, se o clube estiver no banco; senão, Passes Livres (Sem Contrato)
                clube = self.clube_por_nome((j.get("clube_tm") or {}).get("nome"), genero, (j.get("clube_tm") or {}).get("id"))
                self._linhas_jogador(j, clube or TIME_SEM_CONTRATO, genero)
                if clube or genero == 0:
                    alvo = clube or TIME_SEM_CONTRATO
                    usados = {d["jerseynumber"] for d in self.atuais("teamplayerlinks", teamid=alvo)} | \
                             {d["jerseynumber"] for d in self.novas_de("teamplayerlinks", teamid=alvo)}
                    num = "99" if not clube else str(next((k for k in range(2, 99) if str(k) not in usados), 99))
                    sc = self.linha_vazia("teamplayerlinks")
                    sc.update(teamid=alvo, playerid=str(j["playerid"]), jerseynumber=num, position="29", form="3",
                              artificialkey=str(self.ids("tpl", "teamplayerlinks", "artificialkey").novo()))
                    self.novas["teamplayerlinks"].append(sc)
                    if clube:
                        self.clubes_mexidos.add(clube)          # a escalação do clube é refeita (o novo fica no banco)
                j["clube"] = (self.nome_time(clube) if clube else "Passes Livres") if (clube or genero == 0) else "sem clube"
        takers = self._cobradores(titulares)
        auto = tatica_auto(ex.get("forca"), fo_mod.get("formationname"))
        prof = int(tat.get("profundidade") or auto["profundidade"])
        saida = int(tat.get("saida") or auto["saida"])
        notas_lin = self._notas_time(titulares, vagas)
        cores = self._cores(dados)
        nome = (self.nome_nacao.get(nacao) or tm["nome"]) if not ajustes.get("_time_nome") else ajustes["_time_nome"]
        if existente:
            self.remover("teamplayerlinks", teamid=teamid)
            valores = {"overallrating": notas_lin["geral"], "attackrating": notas_lin["ataque"], "midfieldrating": notas_lin["meio"],
                       "defenserating": notas_lin["defesa"], "matchdayoverallrating": notas_lin["geral"],
                       "matchdayattackrating": notas_lin["ataque"], "matchdaymidfieldrating": notas_lin["meio"],
                       "matchdaydefenserating": notas_lin["defesa"], "buildupplay": saida, "defensivedepth": prof}
            valores.update({k: j["playerid"] for k, j in takers.items()})
            t0 = self.copiar("teams", "teamid", teamid)[0]
            self.alterar("teams", {k: v for k, v in valores.items() if k in t0}, teamid=teamid)
            if mod_form != teamid:                       # formação nova: posições, papéis e deslocamentos do modelo
                self._trocar_formacao(teamid, mod_form, fo_mod)
            dm = self.atuais("default_mentalities", teamid=teamid)
            if dm:
                v = {f"playerid{i}": titulares[i]["playerid"] for i in range(11)}
                v.update({k: x for k, x in (("buildupplay", saida), ("defensivedepth", prof)) if k in dm[0]})
                self.alterar("default_mentalities", v, teamid=teamid)
            self.alterar("defaultteamdata", {"defensivedepth": prof}, teamid=teamid)
            ts = self.atuais("default_teamsheets", teamid=teamid)
            if ts:
                nova = self._folha(dict(ts[0]), teamid, ordem, takers)
                self.alterar("default_teamsheets", {k: v for k, v in nova.items() if k != "teamid"}, teamid=teamid)
            mg = self.indices("manager", teamid=teamid)
            tec = None
            if dados.get("tecnico") or ex.get("tecnico"):
                if mg:
                    tec = self._tecnico(teamid, teamid, dados.get("tecnico"), ex.get("tecnico") or {}, nacao, genero, atualizar=mg[0])
        else:
            t = dict(self.copiar("teams", "teamid", modelo)[0])
            t.update(teamid=teamid, assetid=teamid, teamname=limpar(nome, 59), overallrating=notas_lin["geral"],
                     attackrating=notas_lin["ataque"], midfieldrating=notas_lin["meio"], defenserating=notas_lin["defesa"],
                     matchdayoverallrating=notas_lin["geral"], matchdayattackrating=notas_lin["ataque"],
                     matchdaymidfieldrating=notas_lin["meio"], matchdaydefenserating=notas_lin["defesa"], gender=genero,
                     leaguetitles=0, domesticcups=0, uefa_cl_wins=0, uefa_el_wins=0, uefa_uecl_wins=0, rivalteam=1)
            if "buildupplay" in t:
                t["buildupplay"] = saida
            if "defensivedepth" in t:
                t["defensivedepth"] = prof
            for k, j in takers.items():
                if k in t:
                    t[k] = j["playerid"]
            for i, cc in enumerate(cores["time"][:3], start=1):
                for comp, v in zip("rgb", cc):
                    if f"teamcolor{i}{comp}" in t:
                        t[f"teamcolor{i}{comp}"] = v
            self.novas["teams"].append({k: str(v) for k, v in t.items()})
            liga = LIGA_SELECOES.get(genero, "78")
            lt = dict(self.copiar("leagueteamlinks", "teamid", modelo)[0])
            for k in lt:
                if k not in ("teamshortform", "teamlongform", "teamform", "objective", "highestpossible", "highestprobable", "grouping"):
                    lt[k] = "0"
            lt.update(leagueid=liga, prevleagueid=liga, teamid=teamid, artificialkey=str(self.ids("ltl", "leagueteamlinks", "artificialkey").novo()),
                      previousyeartableposition="1", currenttableposition="1")
            self.novas["leagueteamlinks"].append(lt)
            self.novas["teamnationlinks"].append({"leagueid": liga, "teamid": teamid, "nationid": nacao})
            self._formacao_e_escalacao(teamid, modelo, mod_form, fo_mod, titulares, ordem, takers, prof, saida)
            self._estadio(teamid, modelo, {"estadio": {}}, capacidade_tipica(nivel), ex.get("estadio") or {})   # o "estádio" das seleções na API é o do último jogo
            self._uniformes(teamid, modelo, cores)
            tec = self._tecnico(teamid, modelo, dados.get("tecnico"), ex.get("tecnico") or {}, nacao, genero)
            self.texto(f"TeamName_{teamid}", nome)
            self.texto(f"TeamName_Abbr15_{teamid}", limpar(nome, 30)[:15])
            self.texto(f"TeamName_Abbr10_{teamid}", limpar(nome, 20)[:10])
            self.texto(f"TeamName_Abbr3_{teamid}", (tm.get("sigla") or nome[:3]).upper()[:3])
        for j in ordem:
            self.novas["teamplayerlinks"].append(self._vinculo(teamid, j, titulares, reservas, vagas))
        res = {"teamid": teamid, "selecao": True, "atualiza": bool(existente), "nacao": nacao, "nome": nome, "api_id": tm["id"],
               "fonte": dados.get("fonte") or "apifootball",
               "logo": tm.get("logo"), "modelo": modelo, "modelo_formacao": mod_form, "formacao": fo_mod.get("formationname"),
               "formacao_api": dados.get("formacao"), "formacoes_api": dados.get("formacoes") or {},
               "tatica": {"profundidade": prof, "saida": saida, "auto": auto, "manual": {k: v for k, v in tat.items() if v}},
               "nivel": round(nivel, 1), "geral": notas_lin["geral"], "genero": genero,
               "jogadores": [self._publico(j) for j in ordem], "cores": cores, "tecnico": tec, "estadio": None,
               "grupos": {g: {"n": cont.get(g, 0), "min": mn, "max": mx} for g, (mn, mx) in limites.items()},
               "falta_grupo": falta_grupo, "nao_encontrados": [{"id": a["id"], "nome": a.get("nome"), "idade": a.get("idade"),
                                                                "pos": a.get("posicao_api"), "criar": criar(a)} for a in faltam],
               "avisos": list(dados.get("avisos") or [])}
        if falta_grupo:
            res["avisos"].append("Abaixo do mínimo: " + ", ".join(f"{g} {cont[g]}/{limites[g][0]}" for g in falta_grupo) +
                                 " (a nação não tem mais jogadores no banco nessas posições).")
        fora = [a for a in faltam if not criar(a)]
        if fora:
            res["avisos"].append(f"{len(fora)} convocado(s) não estão no banco e não serão criados: "
                                 f"{', '.join(a.get('nome') or '?' for a in fora[:6])}{'…' if len(fora) > 6 else ''}. "
                                 "Marque quem criar ou escolha o jogador do banco.")
        self.selecoes.append({"teamid": teamid, "nacao": nacao, "nome": nome, "genero": genero, "nivel": nivel, "novo": not existente,
                              "confederacao": self.confed.get(nacao)})
        self.resumo.append(res)
        return res

    def _trocar_formacao(self, teamid, mod_form, fo_mod):
        campos_form = [k for k in fo_mod if k.startswith(("position", "offset", "pos")) or k in (
            "formationname", "formationfullnameid", "formationaudioid", "defenders", "midfielders", "attackers", "offensiverating",
            "relativeformationid")]
        self.alterar("formations", {k: fo_mod[k] for k in campos_form}, teamid=teamid)
        dm_mod = self.copiar("default_mentalities", "teamid", mod_form)
        if dm_mod:
            m = dm_mod[0]
            self.alterar("default_mentalities", {k: m[k] for k in m if k.startswith(("position", "offset")) or k.endswith("role")
                                                 or k in ("formationfullnameid", "formationaudioid")}, teamid=teamid)
        dd_mod = self.copiar("defaultteamdata", "teamid", mod_form)
        if dd_mod:
            m = dd_mod[0]
            self.alterar("defaultteamdata", {k: m[k] for k in m if k.startswith(("position", "offset")) or k == "formationfullnameid"},
                         teamid=teamid)


def N_norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
