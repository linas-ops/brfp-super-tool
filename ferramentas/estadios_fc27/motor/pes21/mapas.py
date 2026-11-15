"""Mapas normal e de coeficientes do FC 27 a partir dos materiais do PES 2021.

Cada material do FC 27 usa três texturas: a de cor, a normal (normalTexture, BC5: X no vermelho, Y no verde) e a de
coeficientes (coefficientTexture, BC1 linear). Nas texturas do El Grandioso, os canais da de coeficientes são: vermelho =
reflexo especular (128 é o padrão, quase todas usam), verde = lisura (borracha 27, concreto 75, metal pintado 182, vidro
205), azul = metal (0 nas pinturas, 170 no metal galvanizado) e alfa 255. Sem estes mapas, os materiais convertidos ficam
com o normal plano e os coeficientes padrão dos modelos do El Grandioso, e o estádio parece "limpo" demais no jogo.

Do PES vêm:
- NormalMap_Tex_NRM (_nrm): as do jogo guardam X no alfa e Y no verde (o mapa plano é 255, 128, 0, 128); muitas de mods
  guardam XYZ no RGB, com o alfa constante. O vermelho cresce para a direita da imagem nos dois jogos; o verde das do jogo
  cresce para cima da imagem, o do FC 27 (e o das RGB dos mods) para baixo. Cada mapa passa pelo teste de
  integrabilidade (o campo (-x/z, -y/z) tirado de um relevo não tem rotacional, só com o sentido certo do verde); quando o
  teste não decide, fica o sentido mais comum do tipo de mapa.
- SpecularMap_Tex_LIN (_srm, _rgm): vermelho = especular (255 quase sempre), verde = rugosidade (concreto ~200, metal ~106),
  azul = metal; MetalnessMap_Tex_LIN (_mtl): metal, em cinza.

Os quadros tangentes dos meshes nativos do FC 27 apontam para -dP/du e -dP/dv (conferido nos meshes do El Grandioso); a
preparação do PES grava os seus no mesmo sentido (motor/pes21/preparar.py), então os mapas daqui seguem a convenção das
texturas do El Grandioso sem mais trocas.
"""
from __future__ import annotations

import numpy as np

from ..fifa16 import bcn
from ..fifa16.preparar import full_chain

MAX_NORMAL = 512       # lado máximo dos mapas normal convertidos (os do El Grandioso têm de 256 a 512)
MAX_COEF = 512         # lado máximo dos mapas de coeficientes
LADO_CONSTANTE = 16    # mapas sem variação viram texturas pequenas (como as padrão do jogo, 16x16)
DECIDE = 1.5           # razão mínima do teste de integrabilidade para decidir o sentido do verde de um mapa


def imagem(tex, lado_max):
    """(h, w, 4) float32 0..255 do maior nível da textura do PES que cabe em lado_max, ou None (formato sem suporte)."""
    if tex is None:
        return None
    try:
        mips = tex.cadeia()
    except ValueError:
        return None
    if not mips:
        return None
    k = next((i for i, (w, h, _) in enumerate(mips) if max(w, h) <= lado_max), len(mips) - 1)
    w, h, d = mips[k]
    if tex.formato in ('BC1', 'BC3'):
        img = bcn.decode(d, w, h, tex.formato)
    elif tex.formato == 'BGRA8':
        img = np.frombuffer(d, np.uint8).reshape(h, w, 4)[..., [2, 1, 0, 3]].astype(np.float32)
    else:
        return None
    while max(img.shape[0], img.shape[1]) > lado_max:
        img = bcn.downsample(img)
    return np.asarray(img, np.float32)


def _rotacional(x, y):
    """Energia do rotacional de (-x/z, -y/z) com o verde no sentido das linhas da imagem (s = +1) e no contrário."""
    z = np.sqrt(np.clip(1 - x * x - y * y, 0.04, 1))
    gx, gy = -x / z, -y / z
    gx, gy = gx - gx.mean(), gy - gy.mean()
    h, w = gx.shape
    Gx, Gy = np.fft.fft2(gx), np.fft.fft2(gy)
    kr = np.fft.fftfreq(h)[:, None]
    kc = np.fft.fftfreq(w)[None, :]
    return [float((np.abs(kr * Gx - kc * s * Gy) ** 2).sum()) for s in (1, -1)]


def sentido_do_verde(x, y):
    """+1 se o verde cresce para baixo da imagem, -1 se para cima, None se o teste não decide. x, y em -1..1."""
    while max(x.shape) > 256:
        h, w = x.shape
        x = x[:h // 2 * 2, :w // 2 * 2].reshape(h // 2, 2, w // 2, 2).mean((1, 3))
        y = y[:h // 2 * 2, :w // 2 * 2].reshape(h // 2, 2, w // 2, 2).mean((1, 3))
    if min(x.shape) < 8:
        return None, 1.0
    baixo, cima = _rotacional(x, y)
    if min(baixo, cima) <= 0:
        return None, 1.0
    r = max(baixo, cima) / min(baixo, cima)
    if r < DECIDE:
        return None, r
    return (1 if baixo < cima else -1), r


def _mips_normal(x, y):
    """Cadeia BC5 completa (até 1x1) de um mapa normal: x, y em 0..255 no nível 0; os outros níveis são a média dos
    vetores renormalizada."""
    v = np.stack([x / 127.5 - 1, y / 127.5 - 1], -1).astype(np.float64)
    out = []
    while True:
        h, w = v.shape[:2]
        z = np.sqrt(np.clip(1 - (v ** 2).sum(-1), 0, 1))
        out.append((w, h, bcn.encode_bc5(np.clip((v[..., 0] + 1) * 127.5, 0, 255), np.clip((v[..., 1] + 1) * 127.5, 0, 255))))
        if max(w, h) == 1:
            return out
        n3 = np.concatenate([v, z[..., None]], -1)
        nh, nw = max(1, h // 2), max(1, w // 2)
        n3 = n3[:nh * (h // nh), :nw * (w // nw)].reshape(nh, h // nh, nw, w // nw, 3).mean((1, 3))
        n3 /= np.maximum(np.linalg.norm(n3, axis=-1, keepdims=True), 1e-6)
        v = n3[..., :2]


def normal(tex):
    """(cadeia BC5 [(w, h, bytes)], informação) do mapa normal do PES no formato do FC 27, ou (None, motivo) quando o
    mapa não serve (formato sem suporte, layout desconhecido ou plano)."""
    img = imagem(tex, MAX_NORMAL)
    if img is None:
        return None, 'formato sem suporte' if tex is not None else 'sem arquivo'
    med = img.reshape(-1, 4).astype(np.float64).mean(0)
    if med[2] > 190 and med[0] < 230:  # XYZ no RGB (o alfa, quando varia, guarda outra coisa)
        tipo, xb, yb, padrao = 'rgb', img[..., 0], img[..., 1], 1
    elif med[0] > 230 and abs(med[3] - 128) < 48:  # X no alfa, Y no verde
        tipo, xb, yb, padrao = 'ag', img[..., 3], img[..., 1], -1
    else:
        return None, f'layout desconhecido (média {np.round(med).astype(int).tolist()})'
    if max(xb.std(), yb.std()) < 1.5 and abs(xb.mean() - 127.5) < 4 and abs(yb.mean() - 127.5) < 4:
        return None, 'plano'
    sentido, razao = sentido_do_verde(xb / 127.5 - 1, yb / 127.5 - 1)
    decidido = sentido is not None
    if not decidido:
        sentido = padrao
    if sentido < 0:
        yb = 255 - yb
    return _mips_normal(xb, yb), dict(tipo=tipo, verde='invertido' if sentido < 0 else 'mantido',
                                      teste=round(razao, 2) if decidido else f'{razao:.2f} (padrão do tipo)')


def _redimensionar(img, h, w):
    """Vizinho mais próximo para (h, w)."""
    if img.shape[:2] == (h, w):
        return img
    rows = (np.arange(h) * img.shape[0] // h).clip(0, img.shape[0] - 1)
    cols = (np.arange(w) * img.shape[1] // w).clip(0, img.shape[1] - 1)
    return img[rows][:, cols]


def coeficientes(spec, metal):
    """(cadeia BC1 [(w, h, bytes)], informação) dos coeficientes do FC 27 a partir do mapa especular e do de metal do PES
    (texturas Ftex ou None), ou (None, motivo)."""
    S = imagem(spec, MAX_COEF)
    M = imagem(metal, MAX_COEF)
    if S is None and M is None:
        return None, 'sem mapas especular e de metal'
    h = max(x.shape[0] for x in (S, M) if x is not None)
    w = max(x.shape[1] for x in (S, M) if x is not None)
    out = np.zeros((h, w, 4), np.float32)
    out[..., 3] = 255
    if S is not None:
        S = _redimensionar(S, h, w)
        out[..., 0] = S[..., 0] * (128 / 255)
        out[..., 1] = 255 - S[..., 1]
        out[..., 2] = S[..., 2]
    else:
        out[..., 0], out[..., 1] = 128, 127
    if M is not None:
        out[..., 2] = _redimensionar(M, h, w)[..., 0]
    out = np.clip(np.round(out), 0, 255)
    media = out.reshape(-1, 4).astype(np.float64).mean(0)
    info = dict(reflexo=int(round(media[0])), lisura=int(round(media[1])), metal=int(round(media[2])))
    if out.reshape(-1, 4).std(0).max() < 1.0:
        out = np.broadcast_to(media, (LADO_CONSTANTE, LADO_CONSTANTE, 4)).astype(np.float32)
        info['constante'] = True
    h, w = out.shape[:2]
    return full_chain([(w, h, bcn.encode(out, 'BC1'))], 'BC1', w, h), info
