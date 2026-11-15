"""Colisão do chão e das paredes em volta do campo (FifaPhysics), tirada da geometria do estádio novo.

O jogo guarda, por estádio, uma "bacia" de triângulos em que a bola bate e os jogadores param: o RES FifaPhysicsResource
<token>_fifaphysicsdata36_id_b145a93b-f63d-11df-9b0e-e60342791adc/d4c7fed3-765d-45d6-83c5-12b9de3e2630 (o mesmo GUID em todos
os estádios). Formato: só os triângulos, cada vértice x, y, z, 0 em float32 (48 bytes por triângulo), e o número de
triângulos no primeiro u32 do resmeta. A do Old Trafford é o chão em volta do campo e paredes baixas (até 1 a 3 m), quase
todas viradas para o campo. A do El Grandioso vai até depois da pista de atletismo (|x| até 88 m, |z| até 60 m, paredes de
-4 a 8 m): numa duplicata com a arquibancada mais perto do campo, os jogadores atravessavam a arquibancada nova até
baterem nela (relato da Neo Química Arena do PES, na 2.1 em teste). No mesmo grupo de física ficam as placas de
publicidade (caixas, 301b7bfe-…, que continuam: as placas do El Grandioso continuam no estádio novo) e objetos soltos do
El Grandioso (caixas de 0,3 a 1 m perto dos abrigos e dos cantos: …_id_nullmaterial e db0a02d6-…), que saem.

A bacia nova: de cada direção a partir do centro do campo, a distância até o primeiro obstáculo na altura dos jogadores
(0,55 a 2,2 m acima do gramado), a partir de 2 m depois da borda do campo (mais perto que isso, um trilho de câmera ou uma
placa baixa não vira parede); sem obstáculo até 25 m depois da borda (túnel, vão entre arquibancadas), a parede fica
nesse limite. O que não passa de 0,55 m não conta: os tapetes de publicidade atrás do gol do FIFA 16 (46 cm no Allianz
Parque) punham a parede a 2,6 m da linha de fundo; as muretas da frente das arquibancadas passam de 0,6 m (Camp Nou do
PES). O contorno perde os picos estreitos (mediana de 2,5 graus: vãos entre grades, postes) e é simplificado; o
chão é um leque a partir do centro, na altura do gramado, e as paredes vão de 0,5 m abaixo a 2,5 m acima dele, viradas
para o campo.
"""
from __future__ import annotations
import struct

import numpy as np

from .personagens import _pontos

GUID_BACIA = 'd4c7fed3-765d-45d6-83c5-12b9de3e2630'
GUID_PLACAS = '301b7bfe-7cd3-427a-a09e-fa44bdacc5db'
GUID_SOLTOS = 'db0a02d6-5f46-4ddf-9898-bc55e95aa107'
RES_FIFAPHYSICS = 0xef23407c

MEIO_X, MEIO_Z = 52.5, 34.0     # metade do campo (m)
FAIXA_Y = (0.55, 2.2)           # altura dos jogadores acima do gramado (abaixo disso: tapetes de publicidade, trilhos)
CEL = 0.2                       # grade de cima (m)
DIRECOES = 720                  # meio grau
FOLGA = 2.0                     # a busca começa 2 m depois da borda do campo, e a parede nunca fica mais perto
ALCANCE = 25.0                  # sem obstáculo até 25 m depois da borda, a parede fica aí
RECUO = 0.1                     # a parede fica 10 cm antes do obstáculo
MEDIANA = 5                     # janela (direções) que tira os picos estreitos
TOLERANCIA = 0.25               # simplificação do contorno (m)
PAREDE_Y = (-0.5, 2.5)


def recursos(projeto, prefixo):
    """Nomes dos RES de física do estádio no projeto: {'bacia': nome ou None, 'placas': nome ou None, 'soltos': [...]}."""
    out = {'bacia': None, 'placas': None, 'soltos': []}
    for e in projeto.parsed['resources']:
        n = e['name'].lower()
        if e.get('restype') != RES_FIFAPHYSICS or not n.startswith(prefixo.lower()):
            continue
        if n.endswith('/' + GUID_BACIA):
            out['bacia'] = e['name']
        elif n.endswith('/' + GUID_PLACAS):
            out['placas'] = e['name']
        elif n.endswith('/' + GUID_SOLTOS) or n.endswith('_fifaphysicsdata36_id_nullmaterial'):
            out['soltos'].append(e['name'])
    return out


def ler(raw):
    """Triângulos (k, 3, 3) de um RES de física em triângulos."""
    return np.frombuffer(raw, '<f4').reshape(-1, 3, 4)[:, :, :3].astype(np.float64)


def placas(raw):
    """Caixas das placas (centro, eixos x e z, meia-extensão em x e z) de um RES de placas (registros de 96 bytes)."""
    a = np.frombuffer(raw, '<f4').reshape(-1, 24).astype(np.float64)
    return [(r[12:15], r[0:3], r[8:11], r[16], r[18]) for r in a]


def payload(tri):
    t = np.asarray(tri, np.float32).reshape(-1, 3, 3)
    return np.concatenate([t, np.zeros((len(t), 3, 1), np.float32)], axis=2).tobytes()


def resmeta(n):
    return (struct.pack('<I', int(n)) + bytes(12)).hex()


def vazio():
    """Um triângulo pequeno 100 m abaixo do piso, no lugar de um grupo de objetos que sai (nenhum RES fica vazio)."""
    return np.array([[[0.0, -100.0, 0.0], [0.0, -100.0, 0.1], [0.1, -100.0, 0.0]]])


def _borda(u):
    """Distância do centro à borda do campo na direção u (vetores unitários em x, z)."""
    with np.errstate(divide='ignore'):
        return np.minimum(MEIO_X / np.abs(u[:, 0]), MEIO_Z / np.abs(u[:, 1]))


def ocupacao(tri):
    """Grade de cima com o que fica na altura dos jogadores fora do campo: (grade booleana, origem x, origem z)."""
    tri = np.asarray(tri, np.float64)
    lim_x, lim_z = MEIO_X + ALCANCE + 5, MEIO_Z + ALCANCE + 5
    lo, hi = tri[:, :, 1].min(1), tri[:, :, 1].max(1)
    c = tri.mean(1)
    sel = (hi >= FAIXA_Y[0]) & (lo <= FAIXA_Y[1]) & (np.abs(c[:, 0]) < lim_x + 20) & (np.abs(c[:, 2]) < lim_z + 20)
    nx, nz = int(2 * lim_x / CEL) + 1, int(2 * lim_z / CEL) + 1
    grade = np.zeros((nx, nz), bool)
    if sel.any():
        for p in _pontos(tri[sel], passo=0.1):
            p = p[(p[:, 1] >= FAIXA_Y[0]) & (p[:, 1] <= FAIXA_Y[1])]
            p = p[(np.abs(p[:, 0]) > MEIO_X + 0.25) | (np.abs(p[:, 2]) > MEIO_Z + 0.25)]
            ix = np.floor((p[:, 0] + lim_x) / CEL).astype(np.int64)
            iz = np.floor((p[:, 2] + lim_z) / CEL).astype(np.int64)
            ok = (ix >= 0) & (ix < nx) & (iz >= 0) & (iz < nz)
            grade[ix[ok], iz[ok]] = True
    # fecha frestas de uma célula
    g = grade.copy()
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            g |= np.roll(np.roll(grade, dx, 0), dz, 1)
    return g, lim_x, lim_z


def contorno(tri):
    """Distância (m) do centro até a parede em cada direção, as direções (unitárias) e a distância até a borda do campo."""
    g, lim_x, lim_z = ocupacao(tri)
    ang = (np.arange(DIRECOES) + 0.5) * 2 * np.pi / DIRECOES
    u = np.c_[np.cos(ang), np.sin(ang)]
    borda = _borda(u)
    passos = np.arange(FOLGA, ALCANCE + 1e-9, CEL / 2)
    d = borda + ALCANCE
    for k in range(DIRECOES):
        r = borda[k] + passos
        ix = np.floor((u[k, 0] * r + lim_x) / CEL).astype(np.int64)
        iz = np.floor((u[k, 1] * r + lim_z) / CEL).astype(np.int64)
        bate = np.flatnonzero(g[ix, iz])
        if len(bate):
            d[k] = max(borda[k] + FOLGA, r[bate[0]] - RECUO)
    # sem picos estreitos (para dentro ou para fora)
    meia = MEDIANA // 2
    ext = np.r_[d[-meia:], d, d[:meia]]
    d = np.array([np.median(ext[k:k + MEDIANA]) for k in range(DIRECOES)])
    return d, u, borda


def _simplificar(p, tol):
    """Douglas-Peucker num contorno fechado (n, 2): índices que ficam."""
    n = len(p)
    fica = np.zeros(n, bool)
    # dois pontos fixos: o primeiro e o mais longe dele
    a, b = 0, int(np.argmax(np.linalg.norm(p - p[0], axis=1)))
    fica[[a, b]] = True
    pilha = [(a, b), (b, a)]
    while pilha:
        i, j = pilha.pop()
        idx = np.arange(i + 1, j if j > i else j + n) % n
        if not len(idx):
            continue
        A, B = p[i], p[j]
        AB = B - A
        L = np.linalg.norm(AB)
        q = p[idx] - A
        dist = np.abs(AB[0] * q[:, 1] - AB[1] * q[:, 0]) / L if L > 1e-9 else np.linalg.norm(q, axis=1)
        k = int(np.argmax(dist))
        if dist[k] > tol:
            m = int(idx[k])
            fica[m] = True
            pilha += [(i, m), (m, j)]
    return np.flatnonzero(fica)


def bacia(tri):
    """Triângulos (k, 3, 3) da bacia nova (chão em leque + paredes viradas para o campo) e o relatório."""
    d, u, borda = contorno(tri)
    pts = u * d[:, None]
    idx = _simplificar(pts, TOLERANCIA)
    P = pts[idx]
    n = len(P)
    tris = []
    for i in range(n):
        A, B = P[i], P[(i + 1) % n]
        chao = np.array([[0.0, 0.0, 0.0], [A[0], 0.0, A[1]], [B[0], 0.0, B[1]]])
        nrm = np.cross(chao[1] - chao[0], chao[2] - chao[0])
        tris.append(chao if nrm[1] > 0 else chao[[0, 2, 1]])
        a0, b0 = [A[0], PAREDE_Y[0], A[1]], [B[0], PAREDE_Y[0], B[1]]
        a1, b1 = [A[0], PAREDE_Y[1], A[1]], [B[0], PAREDE_Y[1], B[1]]
        t1, t2 = np.array([a0, b0, b1]), np.array([a0, b1, a1])
        nrm = np.cross(t1[1] - t1[0], t1[2] - t1[0])
        meio = (A + B) / 2
        if nrm[0] * -meio[0] + nrm[2] * -meio[1] < 0:  # virada para fora: inverte
            t1, t2 = t1[[0, 2, 1]], t2[[0, 2, 1]]
        tris += [t1, t2]
    folga = d - borda
    lado = np.abs(u[:, 1]) * MEIO_X > np.abs(u[:, 0]) * MEIO_Z  # direções que saem pela linha lateral
    rel = dict(triangulos=len(tris), vertices_do_contorno=n,
               linha_lateral_m=[round(float(np.percentile(folga[lado], q)), 1) for q in (5, 50, 95)],
               linha_de_fundo_m=[round(float(np.percentile(folga[~lado], q)), 1) for q in (5, 50, 95)],
               direcoes_sem_obstaculo=int((folga >= ALCANCE - 1e-6).sum()))
    return np.array(tris), rel, (d, u)


def placas_dentro(caixas, d, u):
    """Quantas placas (pelo centro das caixas) ficam além da parede nova, dentro da arquibancada."""
    ang = np.arctan2(u[:, 1], u[:, 0])
    dentro = 0
    for c, *_ in caixas:
        k = int(np.argmin(np.abs(np.angle(np.exp(1j * (ang - np.arctan2(c[2], c[0])))))))
        if float(np.hypot(c[0], c[2])) > d[k]:
            dentro += 1
    return dentro
