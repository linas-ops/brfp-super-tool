"""Gera os templates de recorte iniciais do Criador de Kits (pasta templates/): cada cor lisa é uma parte do uniforme e
o .json ao lado dá o nome de cada parte. Usa o molde (e as malhas do FET, se estiverem em motor/referencia, para as mangas
e o cano do meião ficarem exatos).

    python gerar_templates.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import kit as K  # noqa: E402
import molde as M  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(os.path.dirname(AQUI), "templates")
VERMELHO, VERDE, AZUL, AMARELO, MAGENTA, CIANO = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255),
                                                 (0, 255, 255))


def _hex(c):
    return "#%02x%02x%02x" % c


def gravar(pasta, nome, camadas, nomes, tamanho):
    """camadas: [(máscara 0..1, cor)] pintadas em ordem sobre a primeira."""
    w, h = tamanho
    img = np.zeros((h, w, 3), np.float32)
    for mask, cor in camadas:
        m = mask[..., None] if np.ndim(mask) == 2 else np.full((h, w, 1), float(mask), np.float32)
        img = img * (1 - m) + np.array(cor, np.float32) * m
    os.makedirs(os.path.join(SAIDA, pasta), exist_ok=True)
    Image.fromarray(np.round(img).astype(np.uint8), "RGB").save(os.path.join(SAIDA, pasta, nome + ".png"), optimize=True)
    with open(os.path.join(SAIDA, pasta, nome + ".json"), "w", encoding="utf-8") as f:
        json.dump({_hex(c): n for c, n in nomes}, f, ensure_ascii=False, indent=1)


def camisas():
    w, h = M.TAMANHOS["jersey"]
    mas = M.mascaras("jersey", w, h)
    X, D, F = M.coordenadas_tronco(w, h)
    px = 1.0 / (w * (M.FRENTE["u1"] - M.FRENTE["u0"]))
    tronco, manga, punho = mas["tronco"], mas["manga"], mas["punho"]
    um = np.ones((h, w), np.float32)
    uso = M.usado("jersey", w, h)
    uso = um if uso is None else uso

    def pad(**pd):
        return K.alfa_padrao(pd, X, D, F, px) * tronco * uso
    base = [(um, VERMELHO), (manga, VERDE), (punho, AMARELO)]
    nomes = [(VERMELHO, "Corpo"), (VERDE, "Mangas"), (AMARELO, "Punhos")]
    gravar("camisa", "01 Liso", [(um, VERMELHO)], [(VERMELHO, "Uniforme")], (w, h))
    gravar("camisa", "02 Mangas", base, nomes, (w, h))
    padroes = [
        ("03 Listras verticais", dict(tipo="listras_v", periodo=0.2, largura=0.5, fase=0.0), "Listras"),
        ("04 Listras finas", dict(tipo="listras_v", periodo=0.08, largura=0.3, fase=0.0), "Listras"),
        ("05 Aros", dict(tipo="listras_h", periodo=0.22, largura=0.5, fase=0.0), "Aros"),
        ("06 Metades", dict(tipo="metades", fase=0.0), "Metade esquerda"),
        ("07 Faixa diagonal", dict(tipo="faixa_diagonal", largura=0.2, angulo=35.0, fase=0.0), "Faixa"),
        ("08 Faixa no peito", dict(tipo="faixa_peito", largura=0.12, fase=0.0), "Faixa"),
        ("09 V no peito", dict(tipo="v", largura=0.08, angulo=35.0, fase=0.0), "V"),
        ("10 Xadrez", dict(tipo="xadrez", periodo=0.14, largura=0.5, fase=0.0), "Quadrados"),
    ]
    for nome, pd, parte in padroes:
        gravar("camisa", nome, base + [(pad(**pd), AZUL)], nomes + [(AZUL, parte)], (w, h))
    laterais = np.clip((np.abs(X) - 0.36) / px + 0.5, 0, 1) * tronco * F * uso
    gravar("camisa", "11 Laterais", base + [(laterais, AZUL)], nomes + [(AZUL, "Laterais")], (w, h))
    ombros = np.clip((0.16 - D) / (px * 1.4) + 0.5, 0, 1) * tronco * uso
    gravar("camisa", "12 Ombros", base + [(ombros, AZUL)], nomes + [(AZUL, "Ombros")], (w, h))


def calcoes():
    w, h = M.TAMANHOS["shorts"]
    mas = M.mascaras("shorts", w, h)
    um = np.ones((h, w), np.float32)
    U = (np.arange(w) + 0.5)[None, :] / w * np.ones((h, 1))
    Vv = (np.arange(h) + 0.5)[:, None] / h * np.ones((1, w))
    cos = mas["cos"]
    gravar("calcao", "01 Liso", [(um, VERMELHO)], [(VERMELHO, "Calção")], (w, h))
    base = [(um, VERMELHO), (cos, VERDE)]
    nomes = [(VERMELHO, "Corpo"), (VERDE, "Cós")]
    gravar("calcao", "02 Cós", base, nomes, (w, h))
    faixa = ((np.abs(U - 0.305) < 0.018) | (np.abs(U - 0.695) < 0.018)) & (Vv > M.CALCAO["cos_v1"])
    gravar("calcao", "03 Faixa lateral", base + [(faixa.astype(np.float32), AZUL)], nomes + [(AZUL, "Faixa lateral")], (w, h))
    barra = (Vv > 0.915).astype(np.float32) * (1 - cos)
    gravar("calcao", "04 Barra", base + [(barra, AZUL)], nomes + [(AZUL, "Barra")], (w, h))


def meioes():
    w, h = M.TAMANHOS["socks"]
    mas = M.mascaras("socks", w, h)
    um = np.ones((h, w), np.float32)
    gravar("meiao", "01 Liso", [(um, VERMELHO)], [(VERMELHO, "Meião")], (w, h))
    if "cano" not in mas:
        return
    cano = mas["cano"]
    gravar("meiao", "02 Cano", [(um, VERMELHO), (cano, VERDE)], [(VERMELHO, "Meião"), (VERDE, "Cano")], (w, h))
    r = M.rasterizar("socks", w, h)
    ilha, pos, _ = r
    ytopo = float(pos[..., 1][(ilha >= 0) & (mas["cano"] < 0.5)].max())
    y = pos[..., 1]
    uso = M.usado("socks", w, h)
    listras = (((ytopo - y > 0.015) & (ytopo - y < 0.03)) | ((ytopo - y > 0.045) & (ytopo - y < 0.06))).astype(np.float32) * (1 - cano) * uso
    gravar("meiao", "03 Listras no alto", [(um, VERMELHO), (cano, VERDE), (listras, AZUL)],
           [(VERMELHO, "Meião"), (VERDE, "Cano"), (AZUL, "Listras")], (w, h))


def _elipse(cu, cv, ru, rv, w, h):
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).ellipse([(cu - ru) * w, (cv - rv) * h, (cu + ru) * w, (cv + rv) * h], fill=255)
    return np.asarray(im, np.float32) / 255.0


def gravar_gola(nome, partes, nomes):
    """partes: [(máscara 0..1, cor)] — o PNG é transparente fora delas."""
    w, h = M.TAMANHOS["jersey"]
    rgba = np.zeros((h, w, 4), np.float32)
    for m, cor in partes:
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255.0
        rgba[..., :3] = rgba[..., :3] * (1 - m[..., None]) + np.array(cor, np.float32) * m[..., None]
        rgba[..., 3] = np.maximum(rgba[..., 3], m)
    rgba[..., 3] *= 255
    os.makedirs(os.path.join(SAIDA, "golas"), exist_ok=True)
    Image.fromarray(np.round(rgba).astype(np.uint8), "RGBA").save(os.path.join(SAIDA, "golas", nome + ".png"), optimize=True)
    with open(os.path.join(SAIDA, "golas", nome + ".json"), "w", encoding="utf-8") as f:
        json.dump({_hex(c): n for c, n in nomes}, f, ensure_ascii=False, indent=1)


def golas():
    w, h = M.TAMANHOS["jersey"]
    g = M.GOLA
    fora = _elipse(g["cu"], g["cv"], g["ru"], g["rv"], w, h)
    dentro = _elipse(g["cu"], g["cv"], g["ru_in"], g["rv_in"], w, h)
    anel = np.clip(fora - dentro, 0, 1)
    meio_r = (g["ru"] + g["ru_in"]) / 2
    meio_v = (g["rv"] + g["rv_in"]) / 2
    medio = _elipse(g["cu"], g["cv"], meio_r, meio_v, w, h)
    friso = np.clip(fora - _elipse(g["cu"], g["cv"], g["ru"] - 0.006, g["rv"] - 0.004, w, h), 0, 1)
    gravar_gola("01 Redonda", [(anel, VERMELHO)], [(VERMELHO, "Gola")])
    gravar_gola("02 Redonda com friso", [(anel, VERMELHO), (friso, VERDE)], [(VERMELHO, "Gola"), (VERDE, "Friso")])
    gravar_gola("03 Redonda dupla", [(np.clip(fora - medio, 0, 1), VERMELHO), (np.clip(medio - dentro, 0, 1), VERDE)],
                [(VERMELHO, "Gola (fora)"), (VERDE, "Gola (dentro)")])
    # V: duas faixas da gola até o peito, na frente (v > 0,5)
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    cu, topo, ponta, lado, larg = 0.5, g["cv"] + g["rv_in"] * 0.6, 0.605, g["ru_in"] * 1.05, 0.013
    d.line([((cu - lado) * w, topo * h), (cu * w, ponta * h), ((cu + lado) * w, topo * h)], fill=255, width=int(larg * w), joint="curve")
    v = np.asarray(im, np.float32) / 255.0
    frente = np.zeros((h, w), np.float32)
    frente[int(0.5 * h):] = 1
    gravar_gola("04 Gola V", [(np.clip(anel * (1 - frente) + v, 0, 1), VERMELHO)], [(VERMELHO, "Gola")])
    pe = np.zeros((h, w), np.float32)
    pe[int((g["cv"] + g["rv_in"]) * h):int(0.62 * h), int((cu - 0.012) * w):int((cu + 0.012) * w)] = 1
    gravar_gola("05 Polo", [(anel, VERMELHO), (pe, VERDE)], [(VERMELHO, "Gola"), (VERDE, "Carcela")])


if __name__ == "__main__":
    camisas()
    calcoes()
    meioes()
    golas()
    for r, _, fs in os.walk(SAIDA):
        for f in sorted(fs):
            if f.endswith(".png"):
                print(os.path.relpath(os.path.join(r, f), SAIDA), os.path.getsize(os.path.join(r, f)) // 1024, "KB")
