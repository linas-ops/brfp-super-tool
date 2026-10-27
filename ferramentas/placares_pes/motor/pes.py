"""Um placar do PES 2021 já entendido: as peças do placar principal (game2d_score) separadas pelo papel de cada uma.

O placar do PES é o filme game2d_score do game2dPes.bin. O jogo escreve os textos (times, placar, relógio) em caixas
vazias com nome (teamName_home, teamScore_home, numbers_0…), pinta as placas de cor dos times e mostra/esconde os
acréscimos, o agregado e os cartões. Aqui cada peça ganha um papel:

    fundo          placas fixas (o desenho do placar)
    cor_casa/fora  placas que o jogo pinta com as cores dos times
    acrescimos     a placa dos acréscimos (aparece só no fim de cada tempo)
    agregado       placas do placar agregado
    cartoes        os cartões vermelhos
    texto:<campo>  caixas onde o jogo escreve: nome_casa, nome_fora, gols_casa, gols_fora, relogio, acrescimos
"""
import glob
import os

import numpy as np

import afp

FILME = "game2d_score"
# quadros forçados (pelo nome do clipe) para o placar sem acréscimos
SEM_ACRESCIMOS = {"losstime": "_off", "time_texts": 0}
CAMPOS = {"teamName_home": "nome_casa", "teamName_away": "nome_fora", "teamScore_home": "gols_casa",
          "teamScore_away": "gols_fora"}


def achar_bins(pasta):
    """Os .bin de um placar: aceita a pasta do placar (com common/menu/licence), a própria licence ou um .bin."""
    if os.path.isfile(pasta):
        return [pasta]
    for sub in (os.path.join("common", "menu", "licence"), os.path.join("menu", "licence"), "licence", ""):
        bins = sorted(glob.glob(os.path.join(pasta, sub, "*.bin")))
        if bins:
            return bins
    return []


def achar_placares(pasta, limite=200):
    """Pastas com placar do PES dentro de 'pasta' (um pacote pode ter vários: J1, J2, J3…)."""
    achados = []
    for raiz, dirs, arqs in os.walk(pasta):
        dirs.sort()
        if any(a.lower() == "game2dpes.bin" for a in arqs):
            base = raiz
            for _ in range(3):
                if os.path.basename(base).lower() in ("licence", "menu", "common"):
                    base = os.path.dirname(base)
            achados.append(base)
            dirs[:] = []
        if len(achados) >= limite:
            break
    return achados


def _papel(p):
    cam = p["caminho"]
    nomes = set(cam)
    if p["tipo"] == "forma":
        for k, v in CAMPOS.items():
            if k in nomes:
                return "texto:" + v
        if "time_texts" in nomes and any(n.startswith("numbers_") for n in nomes):
            return "texto:relogio"
        if "losstime" in nomes and cam[-2:-1] == ["losstime"] and "aggregate" not in nomes:
            return "texto:acrescimos"
        return None
    if p["tipo"] != "imagem":
        return None
    ref = p["ref"].lower()
    if "texfont" in ref:                       # dígitos desenhados com a fonte do PES: o FC escreve com a dele
        return None
    if "logo" in nomes or "emblemCompe" in nomes:
        return None
    if "teamColor" in nomes:
        return "cor_casa" if any(n.endswith("_home") for n in nomes) else "cor_fora"
    if "cardNum" in nomes:
        return "cartoes"
    if "aggregate" in nomes:
        return "agregado"
    if "losstime" in nomes:
        return "acrescimos"
    return "fundo"


class PlacarPes:
    def __init__(self, pasta, cache=None):
        self.pasta = pasta
        self.bins = achar_bins(pasta)
        if not self.bins:
            raise afp.ErroAfp("Não achei os arquivos do placar (common\\menu\\licence\\game2dPes.bin) nessa pasta.")
        self.bib = afp.Biblioteca(afp.Pacote(b, cache) for b in self.bins)
        self.filme = self.bib.filme(FILME)
        if not self.filme:
            raise afp.ErroAfp("Esse pacote não tem o placar da partida (game2d_score); só tem: " +
                              ", ".join(n for _, n in self.bib.filmes()))
        nome = os.path.basename(os.path.normpath(pasta))
        self.nome = os.path.splitext(nome)[0] if os.path.isfile(pasta) else nome
        cena = afp.Cena(self.filme)
        # placar normal: acréscimos escondidos (o relógio também se mexe quando eles aparecem)
        self.pecas = self._preparar(cena.pecas(SEM_ACRESCIMOS))
        # com acréscimos: só a placa e a caixa dos acréscimos vêm daqui
        com = self._preparar(cena.pecas())
        self.pecas = [p for p in self.pecas if p["papel"] not in ("acrescimos", "texto:acrescimos")] +             [p for p in com if p["papel"] in ("acrescimos", "texto:acrescimos")]

    def _preparar(self, pecas):
        for p in pecas:
            p["papel"] = _papel(p)
            p["caixa"] = afp.caixa(self.bib, p)
            if p["mult"][3] <= 0.01:
                p["papel"] = None               # escondida neste estado
        return pecas

    # ---------------------------------------------------------- caixas (coordenadas do filme do PES)

    def caixas(self, papel):
        return [p["caixa"] for p in self.pecas if p["papel"] == papel and p["caixa"]]

    def caixa_campo(self, campo):
        cx = self.caixas("texto:" + campo)
        if not cx:
            return None
        return (min(c[0] for c in cx), min(c[1] for c in cx), max(c[2] for c in cx), max(c[3] for c in cx))

    def caixa_visivel(self, papeis=("fundo",), limite=None):
        """Retângulo dos pixels visíveis das peças (as placas do PES têm muita margem transparente).

        'limite' restringe a busca a uma área (x0, y0, x1, y1) do filme.
        """
        pecas = [p for p in self.pecas if p["papel"] in papeis and p["caixa"]]
        if not pecas:
            return None
        x0 = min(p["caixa"][0] for p in pecas)
        y0 = min(p["caixa"][1] for p in pecas)
        x1 = max(p["caixa"][2] for p in pecas)
        y1 = max(p["caixa"][3] for p in pecas)
        # recortes gigantes (uma ponta da placa a 2.000 px) não entram na conta: limita a uma área razoável
        lx0, ly0, lx1, ly1 = limite or (-1000, -600, 2000, 800)
        x0, y0, x1, y1 = max(x0, lx0), max(y0, ly0), min(x1, lx1), min(y1, ly1)
        if x1 <= x0 or y1 <= y0:
            return None
        w, h = int(np.ceil(x1 - x0)) + 2, int(np.ceil(y1 - y0)) + 2
        img = self.desenhar(papeis, (1, 0, 0, 1, -x0, -y0), w, h)
        a = np.asarray(img)[..., 3]
        ys, xs = np.nonzero(a > 8)
        if not len(xs):
            return None
        return (x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1)

    def desenhar(self, papeis, ajuste, w, h, fundo=None):
        pecas = [p for p in self.pecas if p["papel"] in papeis]
        return afp.desenhar(self.bib, pecas, w, h, ajuste=ajuste, fundo=fundo, formas=False)

    def previa(self, margem=12, fundo=(26, 92, 48, 255), caixas_texto=True):
        """Imagem do placar como no PES (fundo + cores + acréscimos), com as caixas de texto marcadas."""
        from PIL import ImageDraw
        cx = self.caixa_visivel(("fundo", "cor_casa", "cor_fora", "acrescimos"))
        if not cx:
            return None
        x0, y0 = cx[0] - margem, cx[1] - margem
        w, h = int(cx[2] - cx[0]) + 2 * margem, int(cx[3] - cx[1]) + 2 * margem
        img = self.desenhar(("fundo", "cor_casa", "cor_fora", "acrescimos", "cartoes"), (1, 0, 0, 1, -x0, -y0), w, h, fundo)
        if caixas_texto:
            dr = ImageDraw.Draw(img)
            for campo in ("nome_casa", "nome_fora", "gols_casa", "gols_fora", "relogio", "acrescimos"):
                c = self.caixa_campo(campo)
                if c:
                    dr.rectangle((c[0] - x0, c[1] - y0, c[2] - x0, c[3] - y0), outline=(255, 210, 0, 255))
        return img

    def luminancia(self, caixa, papeis=("fundo",)):
        """Brilho médio (0 a 1) do fundo dentro de uma caixa: decide se o texto vai claro ou escuro."""
        x0, y0, x1, y1 = caixa
        w, h = max(2, int(x1 - x0)), max(2, int(y1 - y0))
        img = np.asarray(self.desenhar(papeis, (1, 0, 0, 1, -x0, -y0), w, h), np.float32) / 255
        a = img[..., 3]
        if a.sum() < 1:
            return None
        lum = (0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2])
        return float((lum * a).sum() / a.sum())
