"""Molde de UV dos uniformes do FC 27 (o mesmo em todos os times): partes da camisa, do calção e do meião.

As costuras foram traçadas pela média das bordas das texturas de cor dos 132 kits de exemplo (mesmo molde em todos).
Coordenadas em fração da textura (u para a direita, v para baixo). Na camisa:
  - frente: em pé, embaixo no centro (gola em v ≈ 0,5, barra em v ≈ 0,945);
  - costas: de cabeça para baixo, em cima no centro (barra em v ≈ 0,045);
  - mangas curtas: quadrados nos cantos de cima (punho perto de u ≈ 0,21 / 0,79);
  - mangas longas: faixas laterais (punho na borda u ≈ 0 / 1);
  - gola: o anel em volta de (0,5; 0,507); braçadeira: faixa de baixo.
Na frente e nas costas, u > 0,5 é o lado esquerdo de quem veste (as costas estão giradas 180°).
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

TAMANHOS = {"jersey": (2048, 2048), "shorts": (1024, 512), "socks": (512, 256)}

# ------------------------------------------------------------------ camisa
FRENTE = {"u0": 0.315, "u1": 0.685, "v0": 0.500, "v1": 0.945}     # caixa da frente (ombro -> barra)
COSTAS = {"u0": 0.360, "u1": 0.640, "v0": 0.045, "v1": 0.500}     # caixa das costas (barra -> ombro)
GOLA = {"cu": 0.5, "cv": 0.507, "ru": 0.060, "rv": 0.042, "ru_in": 0.040, "rv_in": 0.027}
# densidade horizontal / vertical da UV na frente (o escudo do jogo é desenhado esticado nessa proporção)
ESTICAR_CAMISA = 1.2

_MANGA_CURTA = [(0.160, 0.0), (0.332, 0.0), (0.347, 0.05), (0.350, 0.20), (0.343, 0.275), (0.312, 0.328), (0.290, 0.346),
                (0.160, 0.346)]
_MANGA_LONGA = [(0.0, 0.342), (0.335, 0.342), (0.356, 0.39), (0.364, 0.46), (0.357, 0.54), (0.338, 0.60), (0.305, 0.640),
                (0.285, 0.665), (0.0, 0.665)]
_PUNHO_CURTO = [(0.160, 0.0), (0.252, 0.0), (0.252, 0.346), (0.160, 0.346)]
_PUNHO_LONGO = [(0.0, 0.342), (0.034, 0.342), (0.034, 0.665), (0.0, 0.665)]
_BRACADEIRA = [(0.362, 0.950), (0.638, 0.950), (0.638, 1.0), (0.362, 1.0)]


def _espelho(poli):
    return [(1.0 - u, v) for u, v in poli]


REGIOES_CAMISA = {
    "manga_curta_d": _MANGA_CURTA, "manga_curta_e": _espelho(_MANGA_CURTA),      # d = direita de quem veste (u < 0,5)
    "manga_longa_d": _MANGA_LONGA, "manga_longa_e": _espelho(_MANGA_LONGA),
    "punho_curto_d": _PUNHO_CURTO, "punho_curto_e": _espelho(_PUNHO_CURTO),
    "punho_longo_d": _PUNHO_LONGO, "punho_longo_e": _espelho(_PUNHO_LONGO),
    "bracadeira": _BRACADEIRA,
}

# ------------------------------------------------------------------ calção
CALCAO = {"cos_v0": 0.385, "cos_v1": 0.472, "u0": 0.11, "u1": 0.89, "barra_v": 0.95}
REGIOES_CALCAO = {"cos": [(0.105, 0.385), (0.895, 0.385), (0.895, 0.472), (0.105, 0.472)],
                  "barra": [(0.0, 0.952), (1.0, 0.952), (1.0, 1.0), (0.0, 1.0)]}
REGIOES_MEIAO = {}


def _poligono(poli, w, h):
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).polygon([(u * w, v * h) for u, v in poli], fill=255)
    return im


def _elipse(cu, cv, ru, rv, w, h):
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).ellipse([(cu - ru) * w, (cv - rv) * h, (cu + ru) * w, (cv + rv) * h], fill=255)
    return im


def mascaras(peca, w, h):
    """{nome: máscara float32 0..1} das partes da peça nesse tamanho (bordas suavizadas em ~1 px)."""
    raio = max(0.6, w / 1400)
    out = {}
    if peca == "jersey":
        for nome, poli in REGIOES_CAMISA.items():
            out[nome] = _poligono(poli, w, h)
        anel = Image.fromarray(np.minimum(np.asarray(_elipse(GOLA["cu"], GOLA["cv"], GOLA["ru"], GOLA["rv"], w, h)),
                                          255 - np.asarray(_elipse(GOLA["cu"], GOLA["cv"], GOLA["ru_in"], GOLA["rv_in"], w, h))))
        out["gola"] = anel
    elif peca == "shorts":
        for nome, poli in REGIOES_CALCAO.items():
            out[nome] = _poligono(poli, w, h)
    res = {k: np.asarray(v.filter(ImageFilter.GaussianBlur(raio)), dtype=np.float32) / 255.0 for k, v in out.items()}
    if peca == "jersey":
        manga = np.maximum.reduce([res[k] for k in ("manga_curta_d", "manga_curta_e", "manga_longa_d", "manga_longa_e")])
        punho = np.maximum.reduce([res[k] for k in ("punho_curto_d", "punho_curto_e", "punho_longo_d", "punho_longo_e")])
        res["manga"] = manga
        res["punho"] = np.minimum(punho, manga)
        res["tronco"] = np.clip(1.0 - manga - res["gola"] - res["bracadeira"], 0.0, 1.0)
    elif peca == "shorts":
        res["corpo"] = np.clip(1.0 - res["cos"], 0.0, 1.0)
    else:
        res["corpo"] = np.ones((h, w), np.float32)
    return res


def coordenadas_tronco(w, h):
    """Coordenadas do tronco da camisa em cada pixel, iguais na frente e nas costas (para o padrão continuar na costura):
    x = -0,5 (lado direito de quem veste) … +0,5 (lado esquerdo), medido na largura da frente;
    d = 0 no ombro … 1 na barra (na frente para baixo, nas costas para cima); frente = True na metade de baixo."""
    u = (np.arange(w, dtype=np.float32) + 0.5) / w
    v = (np.arange(h, dtype=np.float32) + 0.5) / h
    U, V = np.meshgrid(u, v)
    x = (U - 0.5) / (FRENTE["u1"] - FRENTE["u0"])
    frente = V >= 0.5
    d = np.where(frente, (V - FRENTE["v0"]) / (FRENTE["v1"] - FRENTE["v0"]), (COSTAS["v1"] - V) / (COSTAS["v1"] - COSTAS["v0"]))
    return x, d, frente


def coordenadas_planas(w, h):
    """Calção e meião: x = 0..1 na largura, d = 0..1 na altura."""
    u = (np.arange(w, dtype=np.float32) + 0.5) / w
    v = (np.arange(h, dtype=np.float32) + 0.5) / h
    U, V = np.meshgrid(u, v)
    return U - 0.5, V, np.ones_like(U, dtype=bool)


def foto_para_uv_frente(fx, fy):
    """Ponto na caixa do tronco da foto (0..1, 0..1; x da esquerda da imagem, y do ombro para a barra) -> (u, v) na frente."""
    return (FRENTE["u0"] + fx * (FRENTE["u1"] - FRENTE["u0"]), FRENTE["v0"] + fy * (FRENTE["v1"] - FRENTE["v0"]))
