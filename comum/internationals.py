"""BRFP Super Tool — internationals.txt (arquivo do jogo, fora do banco: seleções do modo carreira).

Seções entre colchetes ([TIER_AND_OBJECTIVES], [SQUAD_SELECTION]…), uma linha por registro, valores separados por
vírgula. As que as ferramentas usam:
    TIER_AND_OBJECTIVES   nível (1–7), nationid, teamid, confederação, 4 objetivos, MALE/FEMALE
                          (as masculinas primeiro; uma linha em branco; depois as femininas)
    SQUAD_SELECTION       grupo de posição (GK, LB, CB, RB, LM, CM, RM, ST), mínimo, máximo de convocados
    SQUAD_SELECTION_SETTINGS   "Age Cutoff,35" etc.
O texto original é mantido como está; só as linhas novas entram (no fim do bloco do gênero certo).
"""
import collections
import os
import re

GRUPOS = ("GK", "LB", "CB", "RB", "LM", "CM", "RM", "ST")
PADRAO_SQUAD = {"GK": (3, 5), "LB": (2, 4), "CB": (6, 8), "RB": (2, 4), "LM": (2, 4), "CM": (6, 10), "RM": (2, 4), "ST": (5, 8)}


class Internationals:
    def __init__(self, texto, caminho=None):
        self.caminho = caminho
        self.texto = texto
        self.nl = "\r\n" if "\r\n" in texto else "\n"
        self.brutas = texto.splitlines(True)             # com o fim de linha original (o arquivo pode misturar CRLF e LF)
        self.linhas = [l.rstrip("\r\n") for l in self.brutas]
        self.secoes = collections.OrderedDict()          # nome -> (início, fim) em self.linhas (sem o cabeçalho)
        atual, ini = None, 0
        for i, l in enumerate(self.linhas):
            m = re.match(r"^\s*\[([A-Z0-9_]+)\]\s*$", l)
            if m:
                if atual:
                    self.secoes[atual] = (ini, i)
                atual, ini = m.group(1), i + 1
        if atual:
            self.secoes[atual] = (ini, len(self.linhas))

    @classmethod
    def ler(cls, caminho):
        with open(caminho, "rb") as f:
            b = f.read()
        for cod in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                t = b.decode(cod)
                if cod == "utf-16" and not b[:2] in (b"\xff\xfe", b"\xfe\xff"):
                    continue
                break
            except UnicodeDecodeError:
                continue
        else:
            t = b.decode("latin-1")
        if "[TIER_AND_OBJECTIVES]" not in t:
            raise ValueError("Isso não parece um internationals.txt (falta a seção [TIER_AND_OBJECTIVES]).")
        return cls(t, caminho)

    def registros(self, secao):
        if secao not in self.secoes:
            return []
        a, b = self.secoes[secao]
        return [[x.strip() for x in l.split(",")] for l in self.linhas[a:b] if l.strip() and not l.strip().startswith(("//", ";", "#"))]

    # ---- leitura
    def selecoes(self):
        """[{tier, nationid, teamid, confederacao, objetivos, genero}] de TIER_AND_OBJECTIVES."""
        out = []
        for r in self.registros("TIER_AND_OBJECTIVES"):
            if len(r) >= 9 and r[0].isdigit():
                out.append({"tier": int(r[0]), "nationid": r[1], "teamid": r[2], "confederacao": r[3], "objetivos": r[4:8],
                            "genero": 1 if r[8].upper().startswith("F") else 0})
        return out

    def squad(self):
        out = dict(PADRAO_SQUAD)
        for r in self.registros("SQUAD_SELECTION"):
            if len(r) >= 3 and r[0] in GRUPOS and r[1].isdigit() and r[2].isdigit():
                out[r[0]] = (int(r[1]), int(r[2]))
        return out

    def ajuste(self, nome, padrao=None):
        for r in self.registros("SQUAD_SELECTION_SETTINGS"):
            if len(r) >= 2 and r[0].lower() == nome.lower():
                try:
                    return int(r[1])
                except ValueError:
                    return padrao
        return padrao

    def idade_maxima(self):
        return self.ajuste("Age Cutoff", 35)

    def tem_time(self, teamid):
        return any(s["teamid"] == str(teamid) for s in self.selecoes())

    def tier_sugerido(self, nivel, genero, niveis):
        """Nível do internationals para uma seleção nova: o das seleções do mesmo gênero com força mais parecida
        (niveis = {teamid: nível no banco})."""
        pares = [(abs(niveis[s["teamid"]] - nivel), s["tier"]) for s in self.selecoes() if s["genero"] == genero and s["teamid"] in niveis]
        if not pares:
            return 7 if nivel < 72 else 5 if nivel < 76 else 3 if nivel < 80 else 2 if nivel < 84 else 1
        pares.sort()
        perto = [t for _, t in pares[:3]]
        return int(round(sum(perto) / len(perto)))

    def objetivos_do_tier(self, tier, genero):
        cont = collections.Counter(tuple(s["objetivos"]) for s in self.selecoes() if s["tier"] == tier and s["genero"] == genero)
        if cont:
            return list(cont.most_common(1)[0][0])
        return ["KNOCKOUT", "KNOCKOUT", "QUALIFY", "QUALIFY"] if genero == 0 else ["QUARTER", "QUARTER", "N/A", "N/A"]

    # ---- escrita
    def com_selecoes(self, novas):
        """Texto do arquivo com linhas novas em TIER_AND_OBJECTIVES. novas: [{tier, nationid, teamid, confederacao,
        objetivos, genero}] (as que já estão no arquivo, pelo teamid, ficam de fora)."""
        if "TIER_AND_OBJECTIVES" not in self.secoes:
            raise ValueError("O internationals.txt não tem a seção [TIER_AND_OBJECTIVES].")
        existentes = {s["teamid"] for s in self.selecoes()}
        novas = [n for n in novas if str(n["teamid"]) not in existentes]
        a, b = self.secoes["TIER_AND_OBJECTIVES"]
        bloco = self.linhas[a:b]
        # fim do bloco masculino e do feminino (a seção pode ter linhas em branco entre os dois e no fim)
        ult = {0: None, 1: None}
        for i, l in enumerate(bloco):
            p = [x.strip() for x in l.split(",")]
            if len(p) >= 9:
                ult[1 if p[8].upper().startswith("F") else 0] = i
        linhas_novas = {0: [], 1: []}
        for n in sorted(novas, key=lambda n: (n["genero"], n["tier"])):
            gen = "FEMALE" if n["genero"] else "MALE"
            linhas_novas[n["genero"]].append(",".join([str(n["tier"]), str(n["nationid"]), str(n["teamid"]), str(n["confederacao"]),
                                                       *[str(o) for o in n["objetivos"]], gen]))
        bloco = list(self.brutas[a:b])
        if bloco and not bloco[-1].endswith(("\n", "\r")):
            bloco[-1] += self.nl
        # insere de baixo para cima para não mexer nos índices
        for g in (1, 0):
            if not linhas_novas[g]:
                continue
            if ult[g] is not None:
                pos = ult[g] + 1
            elif g == 1:
                pos = (ult[0] + 1 if ult[0] is not None else 0)
            else:
                pos = 0
            bloco[pos:pos] = [l + self.nl for l in linhas_novas[g]]
        return "".join(self.brutas[:a] + bloco + self.brutas[b:]), novas

    def gravar(self, caminho, novas):
        texto, entraram = self.com_selecoes(novas)
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        return entraram
