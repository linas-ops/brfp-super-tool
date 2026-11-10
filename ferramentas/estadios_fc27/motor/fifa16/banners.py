"""Banners dos times do FC 27 no lugar das faixas do estádio do FIFA 16.

As peças com o papel "banner" saem do modelo (motor/fifa16/preparar.py guarda os triângulos delas em banners.json): as
faixas fixas que vêm com o estádio e os lugares em que o FIFA 16 punha os banners dos times na hora do jogo. Cada
superfície plana delas recebe banners do FC 27, os mesmos objetos da world part "banners" do El Grandioso, em que o
jogo põe os banners dos times da partida.

Um banner do FC 27 é um blueprint com o canto de cima à esquerda (visto do campo) na origem: +x para a direita, -y para
baixo, +z para a frente (para o campo), em seis formatos (1x1 = 2 x 2 m, 2x1 = 2 x 1 m, 2x1_large = 4 x 1,95 m, 4x1,
6x1 e 8x1 = 4, 6 e 8 x 1 m), com escala uniforme (no El Grandioso, de 0,75 a 2,3). Cada superfície recebe o formato de
proporção mais parecida, do maior tamanho que cabe nela; as compridas (mais de 8,5 vezes a altura) viram uma fileira.
As curvas (faixas que contornam a arquibancada) são divididas em trechos planos.
"""
from __future__ import annotations
import re

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

FORMATOS = {'1x1': (2.0, 2.0), '2x1': (2.0, 1.0), '2x1_large': (4.0, 1.95), '4x1': (4.0, 1.0), '6x1': (6.0, 1.0), '8x1': (8.0, 1.0)}
MAX_PROPORCAO = 8.5
MIN_LARGURA, MIN_ALTURA = 0.6, 0.3
PROFUNDIDADE = 0.35   # m: mais que isso fora do plano, a superfície é dividida
FRENTE = 0.02         # m à frente da superfície
MAXIMO = 250          # banners por estádio (El Grandioso 90, Bombonera 246, El Monumental 543)


def formato_do_blueprint(nome):
    """'content/worlds/banner/components/banner_2x1_large_01' -> '2x1_large' (ou None)."""
    m = re.search(r'banner_(\d+x\d+(?:_large)?)_\d+$', nome or '')
    return m.group(1) if m and m.group(1) in FORMATOS else None


def superficies(tri):
    """Superfícies planas quase verticais (viradas para o campo) dos triângulos (t, 3, 3) em metros: dicts com centro,
    direita, cima e frente (unitários, frente para o campo), largura, altura e área."""
    tri = np.asarray(tri, np.float64).reshape(-1, 3, 3)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = 0.5 * np.linalg.norm(n, axis=1)
    ok = area > 1e-4
    tri, n, area = tri[ok], n[ok] / (2 * area[ok, None]), area[ok]
    c = tri.mean(1)
    vira = n[:, 0] * -c[:, 0] + n[:, 2] * -c[:, 2] < 0
    n[vira] *= -1
    ok = np.abs(n[:, 1]) < 0.5
    tri, n, area = tri[ok], n[ok], area[ok]
    if not len(tri):
        return []
    # peças conectadas (vértice comum, a 1 cm)
    _, vid = np.unique(np.round(tri.reshape(-1, 3) * 100).astype(np.int64), axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    t = len(tri)
    M = coo_matrix((np.ones(3 * t), (np.repeat(np.arange(t), 3), vid.ravel())), shape=(t, int(vid.max()) + 1)).tocsr()
    k, lab = connected_components(M @ M.T, directed=False)
    out = []
    for g in range(k):
        i = np.flatnonzero(lab == g)
        out += _planas(tri[i], n[i], area[i])
    return _sem_repetidas(out)


def _planas(tri, n, area, nivel=0):
    nm = (n * area[:, None]).sum(0)
    if np.linalg.norm(nm) < 1e-9:
        return []
    nm /= np.linalg.norm(nm)
    cima = np.array([0.0, 1.0, 0.0]) - nm[1] * nm
    if np.linalg.norm(cima) < 1e-6:
        return []
    cima /= np.linalg.norm(cima)
    direita = np.cross(cima, nm)
    P = tri.reshape(-1, 3)
    c0 = P.mean(0)
    d = P - c0
    u, h, w = d @ direita, d @ cima, d @ nm
    curva = np.ptp(w) > PROFUNDIDADE or np.degrees(np.arccos(np.clip(n @ nm, -1, 1))).max() > 45
    if curva and len(tri) > 1 and nivel < 10:
        # divide ao longo da superfície: pelo ângulo das normais em volta do campo, ou pela posição
        az = (np.arctan2(n[:, 2], n[:, 0]) - np.arctan2(nm[2], nm[0]) + np.pi) % (2 * np.pi) - np.pi
        a = az <= np.median(az)
        if a.all() or not a.any():
            cu = (tri.mean(1) - c0) @ direita
            a = cu <= np.median(cu)
            if a.all() or not a.any():
                return []
        return _planas(tri[a], n[a], area[a], nivel + 1) + _planas(tri[~a], n[~a], area[~a], nivel + 1)
    W, H = float(np.ptp(u)), float(np.ptp(h))
    if W < MIN_LARGURA or H < MIN_ALTURA or area.sum() < 0.4 * W * H:
        return []
    centro = c0 + direita * (u.min() + W / 2) + cima * (h.min() + H / 2) + nm * (w.max() + FRENTE)
    return [dict(centro=centro, direita=direita, cima=cima, frente=nm, largura=W, altura=H, area=float(area.sum()))]


def _sem_repetidas(sups):
    """Tira as superfícies repetidas (frente e verso separados da mesma faixa)."""
    out = []
    for s in sorted(sups, key=lambda s: -s['largura'] * s['altura']):
        if not any(np.linalg.norm(s['centro'] - o['centro']) < 0.3 and abs(s['largura'] - o['largura']) < 0.2 * o['largura']
                   and abs(s['altura'] - o['altura']) < 0.2 * o['altura'] and s['frente'] @ o['frente'] > 0.9 for o in out):
            out.append(s)
    return out


def colocacoes(sups, maximo=MAXIMO):
    """Banners do FC 27 para as superfícies, das maiores para as menores (até `maximo`): dicts com formato, escala e os
    eixos e a origem do BlueprintTransform (eixos já multiplicados pela escala). Devolve (lista, quantos ficaram de fora)."""
    out = []
    for s in sorted(sups, key=lambda s: -s['largura'] * s['altura']):
        W, H = s['largura'], s['altura']
        n = max(1, int(np.ceil(W / H / MAX_PROPORCAO)))
        Wt = W / n
        f = min(FORMATOS, key=lambda f: (abs(np.log(Wt / H * FORMATOS[f][1] / FORMATOS[f][0])), f))
        if f in ('2x1', '2x1_large'):
            f = '2x1_large' if H >= 1.5 else '2x1'
        bw, bh = FORMATOS[f]
        e = min(Wt / bw, H / bh)
        for i in range(n):
            ci = s['centro'] + s['direita'] * (-W / 2 + Wt * (i + 0.5))
            origem = ci - s['direita'] * (bw * e / 2) + s['cima'] * (bh * e / 2)
            out.append(dict(formato=f, escala=float(e), right=(s['direita'] * e).tolist(), up=(s['cima'] * e).tolist(),
                            forward=(s['frente'] * e).tolist(), trans=origem.tolist(), largura=float(bw * e), altura=float(bh * e)))
    return out[:maximo], max(0, len(out) - maximo)
