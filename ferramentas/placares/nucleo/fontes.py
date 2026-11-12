"""De onde vêm os arquivos: o jogo instalado, mods .fifamod (só leitura), arquivos .big avulsos (só leitura) e pastas
soltas (data/ui/...).

Todas as fontes falam o mesmo idioma: caminhos legacy como 'data/ui/game/overlays/Generic/overlay_9002.big'.
"""
import os
import re
import struct

from . import big, fifamod, jogo
from .rotulos import descricao_overlay

RX_OVERLAY = re.compile(r"^data/ui/game/overlays/(?:([^/]+)/)?overlay_(\d+)\.big$", re.I)
RX_COMP = re.compile(r"^data/ui/game/globalcomponents/([^/]+)/([^/]+)\.big$", re.I)


class Fonte:
    tipo = ""
    somente_leitura = True

    def __init__(self, ident, nome):
        self.id = ident
        self.nome = nome

    def info(self):
        return {"id": self.id, "tipo": self.tipo, "nome": self.nome, "somente_leitura": self.somente_leitura}


class FonteJogo(Fonte):
    tipo = "jogo"

    def __init__(self, j):
        super().__init__("jogo", "FC 26 (jogo instalado)")
        self.j = j

    def pronta(self):
        return self.j is not None and self.j.estado == "pronto"

    def lista(self, prefixo=""):
        return self.j.lista(prefixo) if self.pronta() else []

    def existe(self, nome):
        return self.pronta() and self.j.existe(nome)

    def ler(self, nome):
        self.j.esperar()
        return self.j.ler(nome)

    def info(self):
        d = super().info()
        d.update(self.j.info() if self.j else {"estado": "indisponivel"})
        return d


class FonteMod(Fonte):
    tipo = "mod"

    def __init__(self, ident, caminho, oodle_fn):
        self.mod = fifamod.Mod(caminho)
        super().__init__(ident, self.mod.titulo or os.path.basename(caminho))
        self.caminho = self.mod.caminho
        self.oodle_fn = oodle_fn

    def lista(self, prefixo=""):
        return self.mod.lista(prefixo)

    def existe(self, nome):
        return self.mod.existe(nome)

    def ler(self, nome):
        oodle = self.oodle_fn()
        if oodle is None:
            raise jogo.ErroJogo("Para ler mods .fifamod o editor usa a DLL Oodle do FC 26: configure a pasta do jogo.")
        return self.mod.ler(nome, oodle)

    def info(self):
        d = super().info()
        d.update(self.mod.info())
        d["caminho"] = self.caminho
        return d


def caminho_legacy_big(caminho):
    """Onde um .big avulso ficaria no jogo. Se ele está numa árvore data/ui/..., usa esse caminho; senão deduz pelo nome:
    overlay_<N>.big vai para data/ui/game/overlays/ (onde ficam os conjuntos de mods) e o resto vira um componente em
    data/ui/game/globalComponents/<pasta>/<nome>.big. O destino pode ser trocado depois no Salvar como."""
    partes = [x for x in os.path.abspath(caminho).replace("\\", "/").split("/") if x]
    baixas = [x.lower() for x in partes]
    for i in range(len(baixas) - 2):
        if baixas[i] == "data" and baixas[i + 1] == "ui":
            return "/".join(["data"] + partes[i + 1:])
    nome = partes[-1]
    if not nome.lower().endswith(".big"):
        nome += ".big"
    if re.match(r"^overlay_\d+\.big$", nome, re.I):
        return "data/ui/game/overlays/" + nome
    pasta = partes[-2] if len(partes) > 1 and not partes[-2].endswith(":") else "componentes"
    return f"data/ui/game/globalComponents/{pasta}/{nome}"


class FonteBig(Fonte):
    """Um arquivo .big avulso (overlay ou componente), visto no caminho legacy deduzido de onde ele está."""
    tipo = "big"

    def __init__(self, ident, caminho):
        self.caminho = os.path.abspath(caminho)
        if not os.path.isfile(self.caminho):
            raise jogo.ErroJogo("Arquivo .big não encontrado.")
        with open(self.caminho, "rb") as f:
            dados = f.read()
        try:
            itens, _ = big.ler(dados)
        except (big.ErroBig, struct.error, ValueError) as ex:
            raise jogo.ErroJogo(f"Este arquivo não é um .big válido ({ex}).")
        if not any(n == "0" for n, _ in itens):
            raise jogo.ErroJogo("Este .big não tem o filme APT (entrada 0), então não parece um placar ou overlay.")
        self.rel = caminho_legacy_big(self.caminho)
        super().__init__(ident, os.path.basename(self.caminho))

    def lista(self, prefixo=""):
        return [self.rel] if self.rel.lower().startswith(prefixo.lower()) else []

    def existe(self, nome):
        return nome.lower().replace("\\", "/") == self.rel.lower()

    def ler(self, nome):
        if not self.existe(nome):
            raise jogo.ErroJogo(f"Arquivo não encontrado: {nome}")
        with open(self.caminho, "rb") as f:
            return f.read()

    def info(self):
        d = super().info()
        d.update({"caminho": self.caminho, "rel": self.rel, "arquivos": 1})
        return d


class FontePasta(Fonte):
    """Pasta com a árvore data/ui/... (pasta mods/legacy do Live Editor, export do Legacy Explorer do FET...)."""
    tipo = "pasta"
    somente_leitura = False

    def __init__(self, ident, caminho, nome=None):
        self.raiz = os.path.abspath(caminho)
        super().__init__(ident, nome or os.path.basename(self.raiz.rstrip("\\/")) or self.raiz)
        self._mapa = None

    def _varrer(self):
        mapa = {}
        if os.path.isdir(self.raiz):
            for base, _dirs, arqs in os.walk(self.raiz):
                for a in arqs:
                    rel = os.path.relpath(os.path.join(base, a), self.raiz).replace("\\", "/")
                    if rel.lower().startswith("data/"):
                        mapa[rel.lower()] = rel
        self._mapa = mapa

    def atualizar(self):
        self._mapa = None

    def lista(self, prefixo=""):
        if self._mapa is None:
            self._varrer()
        p = prefixo.lower()
        return sorted(v for k, v in self._mapa.items() if k.startswith(p))

    def existe(self, nome):
        if self._mapa is None:
            self._varrer()
        return nome.lower().replace("\\", "/") in self._mapa

    def caminho(self, nome):
        if self._mapa is None:
            self._varrer()
        rel = self._mapa.get(nome.lower().replace("\\", "/"), nome)
        return os.path.join(self.raiz, *rel.split("/"))

    def ler(self, nome):
        with open(self.caminho(nome), "rb") as f:
            return f.read()

    def info(self):
        d = super().info()
        d["caminho"] = self.raiz
        return d


# ------------------------------------------------------------------ conjuntos de placares

def conjuntos(fonte):
    """Agrupa os overlays de uma fonte por conjunto (pasta ou número) e junta os componentes globais."""
    grupos = {}
    for nome in fonte.lista("data/ui/game/"):
        m = RX_OVERLAY.match(nome)
        if m:
            pasta, num = m.group(1), m.group(2)
            if pasta:
                chave = pasta
                n_conj = jogo.numero_conjunto(pasta)
            else:
                n_conj = int(num[:-3]) if len(num) > 3 else 0
                chave = f"#{n_conj}"
            g = grupos.setdefault(chave.lower(), {"chave": chave, "pasta": pasta or "", "numero": n_conj, "overlays": [], "componentes": []})
            tipo_num = int(num[-3:])
            g["overlays"].append({"arquivo": nome, "numero": int(num), "tipo": tipo_num, "rotulo": descricao_overlay(tipo_num)})
            continue
        m = RX_COMP.match(nome)
        if m:
            pasta = m.group(1)
            mm = re.match(r"(?:overlayComponents_|o)(\d+)", pasta, re.I)
            n_conj = int(mm.group(1)) if mm else None
            alvo = None
            if n_conj is not None:
                for g in grupos.values():
                    if g["numero"] == n_conj:
                        alvo = g
                        break
            if alvo is None:
                chave = f"#{n_conj}" if n_conj is not None else "componentes"
                alvo = grupos.setdefault(chave.lower(), {"chave": chave, "pasta": "", "numero": n_conj, "overlays": [], "componentes": []})
            alvo["componentes"].append({"arquivo": nome, "rotulo": pasta + "/" + os.path.basename(nome)})
    # os componentes podem ter sido vistos antes do overlay do mesmo número: junta grupos repetidos
    por_num = {}
    for k, g in list(grupos.items()):
        n = g["numero"]
        if n is None:
            continue
        if n in por_num and por_num[n] is not g:
            dono = por_num[n]
            if g["overlays"] and not dono["overlays"]:
                g["componentes"] += dono["componentes"]
                por_num[n] = g
                grupos = {kk: vv for kk, vv in grupos.items() if vv is not dono}
            else:
                dono["overlays"] += g["overlays"]
                dono["componentes"] += g["componentes"]
                grupos.pop(k, None)
        else:
            por_num[n] = g
    out = []
    for g in grupos.values():
        g["overlays"].sort(key=lambda x: x["numero"])
        g["componentes"].sort(key=lambda x: x["arquivo"].lower())
        if g["pasta"]:
            g["titulo"] = g["pasta"]
        elif g["numero"] is not None:
            nomes_comp = [c["rotulo"].split("/")[0] for c in g["componentes"] if re.match(r"o\d+", c["rotulo"], re.I)]
            g["titulo"] = (nomes_comp[0] if nomes_comp else f"Conjunto {g['numero']}")
        else:
            g["titulo"] = "Componentes gerais"
        out.append(g)
    out.sort(key=lambda g: (g["numero"] is None, g["numero"] if g["numero"] is not None else 0, g["titulo"].lower()))
    return out
