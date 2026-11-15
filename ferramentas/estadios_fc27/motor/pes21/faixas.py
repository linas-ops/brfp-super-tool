"""Muretas para os banners dos times do FC 27 num estádio do PES 2021.

O PES não marca onde ficam os banners dos times (no FIFA 16 são peças próprias do modelo, motor/fifa16/banners.py). Aqui
eles vão para a frente dos anéis da torcida, como no El Grandioso (na mureta do anel de baixo, a uns 2 m do chão, e na
frente dos anéis de cima): faces quase verticais viradas para o campo, fora do campo, com lugares da torcida logo atrás e
acima delas e nenhum lugar na frente da face (o que descarta os espelhos dos degraus, as costas de cadeiras e as paredes
do fundo dos anéis). A parte da face abaixo das placas de publicidade do FC 27 não conta, nem o meio do lado dos bancos
(-z na conversão), onde ficam o túnel e os bancos. As superfícies planas dessas faces (motor/fifa16/banners.superficies)
recebem fileiras de banners de ~2 m de altura, alternando os formatos.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from ..fifa16 import banners as bn

CAMPO = (54.5, 36.0)       # meia largura e meio comprimento do campo com 2 m de folga (m)
VERTICAL = 0.3             # |normal y| máximo
PARA_O_CAMPO = 0.7         # cosseno mínimo entre a normal e a direção do centro do campo
ACIMA_DAS_PLACAS = 1.2     # m: a parte da face abaixo disso fica escondida pelas placas de publicidade do FC 27
ATRAS = (0.1, 8.0)         # m: lugares atrás da face (na direção contrária à normal)
ACIMA = (-1.5, 6.0)        # m: altura desses lugares em relação ao topo da face
NA_FRENTE = (0.3, 12.0)    # m: lugares na frente da face que a tapam (acima da base dela)
LATERAL = 5.0              # m: distância lateral dos lugares considerados
ALTURA = 2.0               # m: altura dos banners (no El Grandioso, ~1,9 m)
ALTURA_MIN = 1.0           # m: altura mínima de uma mureta para receber banners
VAO = 3.0                  # m entre dois banners
TUNEL = (20.0, 6.0)        # m: no meio do lado dos bancos (|x| e altura até), o túnel e os bancos ficam sem banners
CICLO = ('4x1', '2x1', '6x1', '2x1', '8x1', '1x1', '4x1', '2x1')
MAXIMO = 160


def geometria(prep):
    """Triângulos (t, 3, 3) dos subsets opacos e com recorte da preparação."""
    prep = Path(prep)
    subs = json.loads((prep / 'subsets.json').read_text(encoding='utf8'))
    blob = (prep / 'geometry.bin').read_bytes()
    out = []
    for s in subs['subsets']:
        if s['role'] not in ('opaque', 'alphatest'):
            continue
        n, t, o = s['vertices'], s['triangles'], s['offset']
        pos = np.frombuffer(blob, '<f4', n * 3, o).reshape(n, 3).astype(np.float64)
        out.append(pos[np.frombuffer(blob, '<u4', t * 3, o + n * 56).reshape(t, 3)])
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def muretas(tri, lugares):
    """Triângulos (t, 3, 3) das faces que podem receber banners: tri = geometria do estádio (m), lugares = (n, 3)."""
    tri = np.asarray(tri, np.float64).reshape(-1, 3, 3)
    lugares = np.asarray(lugares, np.float64).reshape(-1, 3)
    if not len(tri) or not len(lugares):
        return np.zeros((0, 3, 3))
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 2e-4
    tri, n = tri[ok], n[ok] / ln[ok, None]
    c = tri.mean(1)
    rc = np.hypot(c[:, 0], c[:, 2])
    dirc = -c[:, [0, 2]] / np.maximum(rc, 1e-6)[:, None]
    nh = n[:, [0, 2]]
    lh = np.linalg.norm(nh, axis=1)
    topo, base = tri[:, :, 1].max(1), tri[:, :, 1].min(1)
    ok = ((np.abs(n[:, 1]) < VERTICAL) & ((nh * dirc).sum(1) > PARA_O_CAMPO * np.maximum(lh, 1e-9))
          & ((np.abs(c[:, 0]) > CAMPO[0]) | (np.abs(c[:, 2]) > CAMPO[1])) & (topo > ACIMA_DAS_PLACAS + 0.3) & (base < 60)
          & ~((np.abs(c[:, 0]) < TUNEL[0]) & (c[:, 2] < 0) & (c[:, 1] < TUNEL[1])))
    tri, c, nh, topo, base = tri[ok], c[ok], nh[ok] / lh[ok, None], topo[ok], base[ok]
    if not len(tri):
        return tri
    arvore = cKDTree(lugares[:, [0, 2]])
    vizinhos = arvore.query_ball_point(c[:, [0, 2]], r=max(ATRAS[1], NA_FRENTE[1]) + LATERAL)
    fica = np.zeros(len(tri), bool)
    for k, idx in enumerate(vizinhos):
        if not idx:
            continue
        s = lugares[idx]
        d = s[:, [0, 2]] - c[k, [0, 2]]
        dn = d @ nh[k]
        dt = np.abs(d @ np.array([-nh[k, 1], nh[k, 0]]))
        lado = dt < LATERAL
        frente = lado & (dn > NA_FRENTE[0]) & (dn < NA_FRENTE[1]) & (s[:, 1] > base[k] - 0.3)
        if frente.any():
            continue
        atras = lado & (dn < -ATRAS[0]) & (dn > -ATRAS[1]) & (s[:, 1] > topo[k] + ACIMA[0]) & (s[:, 1] < topo[k] + ACIMA[1])
        fica[k] = atras.any()
    return tri[fica]


def acima_das_placas(sups):
    """Corta a parte das superfícies abaixo das placas de publicidade (ACIMA_DAS_PLACAS); tira as que ficam baixas demais."""
    out = []
    for s in sups:
        topo = s['centro'][1] + s['altura'] / 2 * s['cima'][1]
        base = s['centro'][1] - s['altura'] / 2 * s['cima'][1]
        if base < ACIMA_DAS_PLACAS:
            h = (topo - ACIMA_DAS_PLACAS) / max(s['cima'][1], 1e-6)
            if h < ALTURA_MIN:
                continue
            s = dict(s, centro=s['centro'] + s['cima'] * (s['altura'] - h) / 2, altura=float(h))
        if s['altura'] >= ALTURA_MIN:
            out.append(s)
    return out


def colocacoes(sups, maximo=MAXIMO):
    """Fileiras de banners do FC 27 nas superfícies, das mais baixas para as mais altas (até `maximo`), com a altura ALTURA
    (ou a da mureta, se for menor) e os formatos alternados. Mesmo formato de motor/fifa16/banners.colocacoes."""
    out = []
    k = 0
    for s in sorted(sups, key=lambda s: (round(float(s['centro'][1]) / 3), -s['largura'])):
        W, H = s['largura'], s['altura']
        hb = min(ALTURA, H * 0.9)
        x = -W / 2 + VAO / 2
        while True:
            for tent in range(len(CICLO)):
                f = CICLO[(k + tent) % len(CICLO)]
                bw, bh = bn.FORMATOS[f]
                e = hb / bh if f != '1x1' else hb / bh * 0.9
                if x + bw * e <= W / 2 - VAO / 2:
                    break
            else:
                break
            k += tent + 1
            ci = s['centro'] + s['direita'] * (x + bw * e / 2)
            origem = ci - s['direita'] * (bw * e / 2) + s['cima'] * (bh * e / 2)
            out.append(dict(formato=f, escala=float(e), right=(s['direita'] * e).tolist(), up=(s['cima'] * e).tolist(),
                            forward=(s['frente'] * e).tolist(), trans=origem.tolist(), largura=float(bw * e), altura=float(bh * e)))
            x += bw * e + VAO
    return out[:maximo], max(0, len(out) - maximo)


def planejar(prep, lugares):
    """(colocações, quantas ficaram de fora, resumo) dos banners automáticos do estádio preparado em prep."""
    tri = muretas(geometria(prep), lugares)
    sups = acima_das_placas(bn.superficies(tri)) if len(tri) else []
    col, fora = colocacoes(sups)
    alturas = sorted({round(float(s['centro'][1])) for s in sups})
    return col, fora, dict(triangulos=int(len(tri)), superficies=len(sups), alturas_m=alturas[:20])
