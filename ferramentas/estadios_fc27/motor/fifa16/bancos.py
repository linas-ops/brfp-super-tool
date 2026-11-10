"""Reservas do El Grandioso (choreo_seats) nas cadeiras do banco do estádio do FIFA 16.

Os marcadores slc_benchplayer* dos estádios do FIFA 16 não servem: cada autor os pôs de um jeito (no Allianz Parque,
2 m atrás das cadeiras; no Morumbi, 78 cm abaixo do piso; a Neo Química Arena não tem). As cadeiras saem da geometria
do lado dos bancos (z de -50 a -34,3 m, |x| < 32 m): superfícies horizontais de 30 a 70 cm acima do piso (a superfície
mais baixa em volta) com um encosto logo atrás. Em cada lado, os reservas vão para a fileira da frente (ou para a que
tem bem mais cadeiras), a partir do meio-campo, uma cadeira sim, outra não (num banco curto, espalhados por ele). Cada
um fica como no El Grandioso: à frente do assento, virado para o campo, com o quadril na altura do assento (o pé afunda até 8 cm no piso quando o assento é mais baixo que o de lá).
"""
from __future__ import annotations
import numpy as np

from .personagens import _pontos

REGIAO_X = 32.0
REGIAO_Z = (-50.0, -34.3)
REGIAO_Y = (-2.5, 3.0)
ASSENTO_MAX_Y = 1.2              # assento mais alto que isso não é de banco de reservas
CEL = 0.1                        # grade das amostras (m)
ASSENTO = (0.3, 0.7)             # altura do assento acima do piso
ENCOSTO = (0.1, 0.7, 0.25, 1.3)  # atrás do assento: de 10 a 70 cm, subindo de 25 cm a 1,3 m acima dele
LARGURA_CADEIRA = 0.6
MIN_CADEIRAS = 4                 # por lado, numa fileira
# medidos com este detector no banco do El Grandioso: assento a 0,42 m do pé dos reservas, que ficam 0,90 m à frente do
# assento na fileira da frente e 0,54 m na de trás (que tem a outra fileira 1 m à frente: 46 cm atrás do assento dela)
ALTURA_ASSENTO_EG = 0.42
FRENTE_EG = 0.90
ATRAS_DA_FRENTE = 0.46
AFUNDA = 0.08                    # quanto o pé pode afundar no piso


def _regiao(tri):
    c = tri.mean(1)
    sel = (np.abs(c[:, 0]) < REGIAO_X) & (c[:, 2] > REGIAO_Z[0] - 1) & (c[:, 2] < REGIAO_Z[1]) & (c[:, 1] > REGIAO_Y[0]) & (c[:, 1] < REGIAO_Y[1])
    return tri[sel]


def _grupos(v, folga):
    """Índices de v agrupados onde a diferença entre valores consecutivos (ordenados) passa de `folga`."""
    o = np.argsort(v, kind='stable')
    cortes = np.flatnonzero(np.diff(v[o]) > folga) + 1
    return np.split(o, cortes)


def cadeiras(tri):
    """Assentos das cadeiras viradas para +z no lado dos bancos: array (k, 5) com x, y do assento, z, y do piso e a
    fileira (inteiro)."""
    vazio = np.zeros((0, 5))
    tri = _regiao(np.asarray(tri, np.float64))
    if not len(tri):
        return vazio
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    horiz = np.abs(n[:, 1]) > 0.9
    if not horiz.any():
        return vazio
    ph = np.concatenate(list(_pontos(tri[horiz], passo=0.05)))
    pv = np.concatenate(list(_pontos(tri[~horiz], passo=0.05))) if (~horiz).any() else np.zeros((0, 3))
    ix, iz = np.floor(ph[:, 0] / CEL).astype(np.int64), np.floor(ph[:, 2] / CEL).astype(np.int64)
    ky = np.round(ph[:, 1] / 0.02).astype(np.int64)
    alturas = {}
    for a, b, k in np.unique(np.c_[ix, iz, ky], axis=0).tolist():
        alturas.setdefault((a, b), []).append(k * 0.02)
    vert = {}
    if len(pv):
        jx, jz = np.floor(pv[:, 0] / CEL).astype(np.int64), np.floor(pv[:, 2] / CEL).astype(np.int64)
        for a, b, y in zip(jx.tolist(), jz.tolist(), pv[:, 1].tolist()):
            lo, hi = vert.get((a, b), (y, y))
            vert[(a, b)] = (min(lo, y), max(hi, y))
    assentos = []
    for (a, b), hs in alturas.items():
        z = (b + 0.5) * CEL
        if not (REGIAO_Z[0] <= z <= REGIAO_Z[1]):
            continue
        piso = min(min(alturas.get((a + da, b + db), [np.inf])) for da in (-1, 0, 1) for db in (-1, 0, 1))
        for y in hs:
            if y > ASSENTO_MAX_Y or not (ASSENTO[0] <= y - piso <= ASSENTO[1]):
                continue
            encosto = False
            for db in range(int(round(ENCOSTO[0] / CEL)), int(round(ENCOSTO[1] / CEL)) + 1):
                for da in (-1, 0, 1):
                    v = vert.get((a + da, b - db))
                    if v and v[1] >= y + ENCOSTO[2] and v[0] <= y + ENCOSTO[3]:
                        encosto = True
                        break
                if encosto:
                    break
            if encosto:
                assentos.append(((a + 0.5) * CEL, y, z, piso))
    if not assentos:
        return vazio
    A = np.array(assentos)
    saida = []
    fileira = 0
    for gy in _grupos(A[:, 1], 0.12):
        for gz in _grupos(A[gy, 2], 0.25):
            P = A[gy][gz]
            if len(P) < 3:
                continue
            achou = False
            for g in _grupos(P[:, 0], 0.2 + 1e-6):
                Q = P[g]
                x0, x1 = Q[:, 0].min() - CEL / 2, Q[:, 0].max() + CEL / 2
                larg = x1 - x0
                if larg < 0.3:
                    continue
                m = max(1, int(round(larg / LARGURA_CADEIRA)))
                for i in range(m):
                    xi = x0 + larg * (i + 0.5) / m
                    perto = Q[np.abs(Q[:, 0] - xi) <= larg / (2 * m) + 1e-6]
                    saida.append((xi, float(np.median(perto[:, 1])), float(np.median(perto[:, 2])), float(np.median(perto[:, 3])), fileira))
                    achou = True
            fileira += achou
    return np.array(saida) if saida else vazio


def lugares_dos_reservas(C, quantos, lado):
    """Até `quantos` posições dos reservas no lado (-1 = x < 0, 1 = x > 0), espalhados pela fileira escolhida; o que
    faltar vai para a seguinte."""
    C = C[np.sign(C[:, 0]) == lado]
    zs = {int(r): float(np.median(C[C[:, 4] == r, 2])) for r in set(C[:, 4].tolist())}
    conta = {r: int((C[:, 4] == r).sum()) for r in zs}
    fil = [r for r in zs if conta[r] >= MIN_CADEIRAS]
    maior = max((conta[r] for r in fil), default=0)
    # primeiro as fileiras com pelo menos 3/4 das cadeiras da maior, da frente para trás; depois as outras
    fil.sort(key=lambda r: (conta[r] < 0.75 * maior, -zs[r] if conta[r] >= 0.75 * maior else -conta[r]))
    out = []
    for r in fil:
        if len(out) >= quantos:
            break
        P = C[C[:, 4] == r]
        P = P[np.argsort(np.abs(P[:, 0]))]
        k = min(quantos - len(out), len(P))
        # a partir do meio-campo, uma cadeira sim, outra não; num banco curto, espalhados por ele todo
        if len(P) >= 2 * k - 1:
            idx = np.arange(k) * 2
        else:
            idx = np.unique(np.round(np.linspace(0, len(P) - 1, k)).astype(int)) if k > 1 else np.array([0])
        frente_livre = min((zs[q] - zs[r] for q in zs if zs[q] > zs[r] + 0.3), default=None)
        frente = FRENTE_EG if frente_livre is None else max(0.0, min(FRENTE_EG, frente_livre - ATRAS_DA_FRENTE))
        for x, y, z, piso, _ in P[idx]:
            out.append([float(x), float(max(y - ALTURA_ASSENTO_EG, piso - AFUNDA)), float(z + frente)])
    return out
