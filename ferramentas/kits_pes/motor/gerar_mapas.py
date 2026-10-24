"""Gera os mapas de correspondência PES 2021 -> FC 27 (motor/mapas/mapas_pes2021_fc27.npz). Só para quem desenvolve:
a ferramenta usa o arquivo pronto e não precisa dos modelos.

    python gerar_mapas.py [--saida mapas/mapas_pes2021_fc27.npz]

Precisa dos modelos de referência em motor/referencia (tirados dos jogos, fora do repositório público):
  - pes2021_kit.obj: o kit do PES 2021 com a UV do jogo (camisa, mangas, golas, calção e meião);
  - jersey_0_0_0_0_1_0_0_mesh.fbx, shorts_0_0_0_mesh.fbx, sock_0_0_1_0_0_mesh.fbx: as malhas LOD0 do FC 27 exportadas pelo FET.

Para cada pixel da textura do FC (camisa 2048×2048, calção 1024×512, meião 512×256) acha o ponto do uniforme do PES que
veste o mesmo lugar do corpo e guarda a UV do PES ali:
  - tronco, gola, calção e meião: as duas malhas são alinhadas pela caixa de cada parte e cada ponto do FC vai ao ponto
    mais próximo da superfície do PES com a normal do mesmo lado;
  - mangas: coordenadas do braço (s = 0 na cava … 1 no punho, medido em cada ângulo entre os laços da cava e do punho;
    θ = ângulo em volta do braço, 0 no lado de fora, 90° na frente), iguais nos dois jogos mesmo com braços e mangas de
    tamanhos diferentes. A manga longa do FC (sem malha) segue o molde da curta: mesma volta em v, punho na borda.
Requer numpy, SciPy e Pillow.
"""
import argparse
import os
import sys
import time

import numpy as np
from scipy import ndimage as nd
from scipy.spatial import cKDTree

AQUI = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(AQUI, "referencia")
SUPERTOOL = os.path.dirname(os.path.dirname(os.path.dirname(AQUI)))
PES_OBJ = os.path.join(REF, "pes2021_kit.obj")
FC_FBX = {"jersey": "jersey_0_0_0_0_1_0_0_mesh.fbx", "shorts": "shorts_0_0_0_mesh.fbx", "socks": "sock_0_0_1_0_0_mesh.fbx"}
TAMANHOS = {"jersey": (2048, 2048), "shorts": (1024, 512), "socks": (512, 256)}
# partes gravadas no mapa (para a prévia e para o kit base preencher o que o PES não tem)
FORA, TRONCO, MANGA_CURTA, MANGA_LONGA, GOLA, DO_BASE = 0, 1, 2, 3, 4, 9
# manga longa do FC 27 (sem malha no FET): molde traçado pelas texturas dos kits do jogo (Criador de Kits)
MOLDE_LONGA = [(0.0, 0.342), (0.335, 0.342), (0.356, 0.39), (0.364, 0.46), (0.357, 0.54), (0.338, 0.60), (0.305, 0.640),
               (0.285, 0.665), (0.0, 0.665)]
BRACADEIRA = (0.362, 0.950, 0.638, 1.0)       # faixa da braçadeira de capitão na camisa (u0, v0, u1, v1): fica a do kit base
PES_PARTES = {"tronco": ["Shirt_Out_mesh_id_1.006"], "manga_curta": ["Sleeves_Short_MESH_sleeve_short_001"],
              "manga_longa": ["Sleeves_Long_mesh_id_0.007"], "gola": ["Collar_01_MESH_collar_901"],
              "calcao": ["Shorts_With_Shirt_Out_MESH_pants_out_sub", "Shorts_Base_MESH_pants_001"],
              "meiao": ["Socks_MESH_socks_middle"]}


# ------------------------------------------------------------------ leitura dos modelos
def ler_obj(caminho):
    """Objetos do OBJ: {nome: (P (m,3,3) posições dos triângulos, UV (m,3,2) v para cima)}."""
    V, VT, objs, cur = [], [], {}, None
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for ln in f:
            if ln.startswith("v "):
                V.append([float(x) for x in ln.split()[1:4]])
            elif ln.startswith("vt "):
                VT.append([float(x) for x in ln.split()[1:3]])
            elif ln.startswith("o "):
                cur = ln[2:].strip()
                objs.setdefault(cur, [])
            elif ln.startswith("f "):
                idx = [tuple(int(a) if a else 0 for a in w.split("/")[:2]) for w in ln.split()[1:]]
                for i in range(1, len(idx) - 1):
                    objs[cur].append((idx[0], idx[i], idx[i + 1]))
    V, VT = np.array(V), np.array(VT)
    out = {}
    for k, fs in objs.items():
        if fs:
            a = np.array(fs)
            out[k] = (V[a[:, :, 0] - 1], VT[a[:, :, 1] - 1])
    return out


def malha_pes(obj, nomes):
    """Malha (V, T, UV) com os triângulos soltos (cada um com os seus 3 vértices)."""
    P = np.concatenate([obj[n][0] for n in nomes])
    U = np.concatenate([obj[n][1] for n in nomes])
    return P.reshape(-1, 3), np.arange(len(P) * 3).reshape(-1, 3), U.reshape(-1, 2)


def malha_fc(peca):
    """LOD0 do FC (V metros, T, UV v para cima) e a ilha da UV de cada triângulo (como o Criador de Kits lê)."""
    sys.path.append(os.path.join(SUPERTOOL, "ferramentas", "faces", "motor"))
    from cena import Cena
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    cena = Cena(os.path.join(REF, FC_FBX[peca]))
    lod = min(x.lod for x in cena.malhas)
    partes = [x for x in cena.malhas if x.lod == lod and x.uv0 is not None]
    Vs, UVs, Ts, n = [], [], [], 0
    for x in partes:
        Vs.append(np.asarray(x.V, np.float64))
        UVs.append(np.asarray(x.uv0, np.float64))
        Ts.append(np.asarray(x.T, np.int64) + n)
        n += len(x.V)
    V, UV, T = np.concatenate(Vs), np.concatenate(UVs), np.concatenate(Ts)
    chave = np.round(UV * 4096).astype(np.int64)
    _, inv = np.unique(chave[:, 0] * 10 ** 6 + chave[:, 1], return_inverse=True)
    TT = inv.reshape(-1)[T]
    r = np.concatenate([TT[:, 0], TT[:, 1], TT[:, 2]])
    q = np.concatenate([TT[:, 1], TT[:, 2], TT[:, 0]])
    nn = int(inv.max()) + 1
    _, lab = connected_components(coo_matrix((np.ones(len(r)), (r, q)), shape=(nn, nn)), directed=False)
    return V, T, UV, lab[TT[:, 0]]


# ------------------------------------------------------------------ geometria
def rasterizar(T, UV, w, h):
    """Triângulo (h,w; -1 fora) e baricêntricas de cada pixel da UV (v para cima)."""
    px = np.stack([UV[:, 0] * w - 0.5, (1.0 - UV[:, 1]) * h - 0.5], 1)
    tri = np.full((h, w), -1, np.int32)
    bar = np.zeros((h, w, 3), np.float32)
    for k, t in enumerate(T):
        a, b, c = px[t[0]], px[t[1]], px[t[2]]
        x0, x1 = int(max(0, np.floor(min(a[0], b[0], c[0])))), int(min(w - 1, np.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, np.floor(min(a[1], b[1], c[1])))), int(min(h - 1, np.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-14:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1, dtype=np.float64), np.arange(y0, y1 + 1, dtype=np.float64))
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
        l3 = 1 - l1 - l2
        m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not m.any():
            continue
        yy, xx = gy[m].astype(int), gx[m].astype(int)
        livre = (tri[yy, xx] < 0) | (np.minimum(np.minimum(l1[m], l2[m]), l3[m]) >= 0)
        yy, xx = yy[livre], xx[livre]
        tri[yy, xx] = k
        bar[yy, xx] = np.stack([l1[m][livre], l2[m][livre], l3[m][livre]], 1)
    return tri, bar


def normais(V, T):
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _mais_perto(p, a, b, c):
    """Baricêntricas do ponto mais próximo de p em cada triângulo (a, b, c) (Ericson, vetorizado)."""
    ab, ac = b - a, c - a
    ap, bp, cp = p - a, p - b, p - c
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    n = len(p)
    out = np.zeros((n, 3))
    feito = np.zeros(n, bool)
    eps = 1e-30

    def por(m, w0, w1, w2):
        m = m & ~feito
        for j, w in enumerate((w0, w1, w2)):
            out[m, j] = w[m] if np.ndim(w) else w
        feito[m] = True
    por((d1 <= 0) & (d2 <= 0), 1.0, 0.0, 0.0)
    por((d3 >= 0) & (d4 <= d3), 0.0, 1.0, 0.0)
    v = d1 / np.where(np.abs(d1 - d3) < eps, eps, d1 - d3)
    por((vc <= 0) & (d1 >= 0) & (d3 <= 0), 1 - v, v, 0.0)
    por((d6 >= 0) & (d5 <= d6), 0.0, 0.0, 1.0)
    w = d2 / np.where(np.abs(d2 - d6) < eps, eps, d2 - d6)
    por((vb <= 0) & (d2 >= 0) & (d6 <= 0), 1 - w, 0.0, w)
    den = (d4 - d3) + (d5 - d6)
    w = (d4 - d3) / np.where(np.abs(den) < eps, eps, den)
    por((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), 0.0, 1 - w, w)
    s = va + vb + vc
    s = np.where(np.abs(s) < eps, eps, s)
    v, w = vb / s, vc / s
    por(np.ones(n, bool), 1 - v - w, v, w)
    return out


def superficie(Q, NQ, V, T, UV, k=16, bloco=200000):
    """UV do ponto da malha mais próximo de cada Q, preferindo triângulos com a normal do mesmo lado; e a distância."""
    NT = normais(V, T)
    arvore = cKDTree(V[T].mean(1))
    uv = np.zeros((len(Q), 2))
    dist = np.zeros(len(Q))
    for i0 in range(0, len(Q), bloco):
        q, nq = Q[i0:i0 + bloco], NQ[i0:i0 + bloco]
        _, idx = arvore.query(q, k=k)
        melhor = np.full(len(q), np.inf)
        for j in range(k):
            t = idx[:, j]
            a, b, c = V[T[t, 0]], V[T[t, 1]], V[T[t, 2]]
            br = _mais_perto(q, a, b, c)
            d = np.linalg.norm(br[:, :1] * a + br[:, 1:2] * b + br[:, 2:] * c - q, axis=1)
            dn = (NT[t] * nq).sum(1)
            custo = d + np.where(dn < 0, 1e6, 0.0) + (1 - dn) * 1e-3
            m = custo < melhor
            melhor[m] = custo[m]
            uv[i0:i0 + bloco][m] = (br[:, :1] * UV[T[t, 0]] + br[:, 1:2] * UV[T[t, 1]] + br[:, 2:] * UV[T[t, 2]])[m]
        dist[i0:i0 + bloco] = melhor
    return uv, dist


def pontos_fc(V, T, UV, sel, w, h):
    """Pixels cobertos pelos triângulos `sel` da malha do FC: máscara, posição 3D e normal."""
    ids = np.nonzero(sel)[0]
    tri, bar = rasterizar(T[ids], UV, w, h)
    ok = tri >= 0
    t = ids[tri[ok]]
    b = bar[ok].astype(np.float64)
    pos = b[:, :1] * V[T[t, 0]] + b[:, 1:2] * V[T[t, 1]] + b[:, 2:] * V[T[t, 2]]
    return ok, pos, normais(V, T)[t]


def por_caixa(Pfc, Ppes):
    """Escala e deslocamento por eixo que levam a caixa de Pfc na caixa de Ppes."""
    lo1, hi1, lo2, hi2 = Pfc.min(0), Pfc.max(0), Ppes.min(0), Ppes.max(0)
    s = (hi2 - lo2) / (hi1 - lo1)
    return s, lo2 - lo1 * s


def mapa_superficie(fc, sel, w, h, pes, Vcaixa=None):
    """Mapa de uma parte pelo ponto mais próximo, com as duas partes alinhadas pela caixa."""
    V, T, UV = fc
    Vp, Tp, UVp = pes
    ok, pos, nf = pontos_fc(V, T, UV, sel, w, h)
    s, o = por_caixa(V[T[sel]].reshape(-1, 3), Vp[np.unique(Tp)] if Vcaixa is None else Vcaixa)
    nq = nf / s
    nq /= np.linalg.norm(nq, axis=1, keepdims=True)
    uv, d = superficie(pos * s + o, nq, Vp, Tp, UVp)
    return ok, uv, d


# ------------------------------------------------------------------ mangas: coordenadas do braço
def lacos(V, T, escala):
    """Laços da borda da malha (vértices soldados pela posição), maiores primeiro."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    _, inv = np.unique(np.round(V / escala).astype(np.int64), axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    TT = inv[T]
    E = np.sort(np.concatenate([TT[:, [0, 1]], TT[:, [1, 2]], TT[:, [2, 0]]]), 1)
    ue, cnt = np.unique(E, axis=0, return_counts=True)
    b = ue[cnt == 1]
    n = inv.max() + 1
    _, lab = connected_components(coo_matrix((np.ones(len(b)), (b[:, 0], b[:, 1])), shape=(n, n)), directed=False)
    pos = np.zeros((n, 3))
    pos[inv] = V
    grupos = {}
    for v in np.unique(b):
        grupos.setdefault(lab[v], []).append(v)
    return sorted((pos[np.array(g)] for g in grupos.values()), key=lambda p: -len(p))


class Braco:
    """Eixo do braço (da cava ao punho) e os limites da manga em cada ângulo."""

    def __init__(self, V, T, escala, nb=360):
        a, b = lacos(V, T, escala)[:2]
        punho, cava = (a, b) if abs(a.mean(0)[0]) > abs(b.mean(0)[0]) else (b, a)
        self.c = cava.mean(0)
        e = punho.mean(0) - self.c
        self.a = e / np.linalg.norm(e)
        up = np.array([0, 1.0, 0]) - self.a[1] * self.a
        self.up = up / np.linalg.norm(up)          # lado de fora do braço
        fr = np.cross(self.a, self.up)
        self.fr = fr if fr[2] >= 0 else -fr          # frente (+z)
        grade = (np.arange(nb) + 0.5) / nb * 2 * np.pi - np.pi
        self.lim = []
        for L in (cava, punho):
            s, th = self.param(L)
            o = np.argsort(th)
            self.lim.append(np.interp(grade, th[o], s[o], period=2 * np.pi))
        self.nb = nb

    def param(self, P):
        X = P - self.c
        s = X @ self.a
        r = X - s[:, None] * self.a
        return s, np.arctan2(r @ self.fr, r @ self.up)

    def srel(self, P):
        s, th = self.param(P)
        x = (th + np.pi) / (2 * np.pi) * self.nb - 0.5
        i0 = np.floor(x).astype(int)
        f = x - i0
        lo, hi = (L[i0 % self.nb] * (1 - f) + L[(i0 + 1) % self.nb] * f for L in self.lim)
        return (s - lo) / np.maximum(hi - lo, 1e-9), th


NS, NT = 512, 1024


def grade_manga_pes(pes, lado):
    """UV do PES em cada (s, θ) da manga desse lado (grade NS × NT)."""
    V, T, UV = pes
    T = T[np.sign(V[T].mean(1)[:, 0]) == lado]
    br = Braco(V, T, 1e-3)
    sr, th = br.srel(V)
    # desenrola θ nos triângulos que cruzam ±π e rasteriza em [-π, 3π)
    n = len(V)
    tt = th[T]
    Tw = T.copy()
    volta = (tt.max(1) - tt.min(1)) > np.pi
    for j in range(3):
        Tw[volta & (tt[:, j] < 0), j] += n
    th2, sr2, UV2 = np.concatenate([th, th + 2 * np.pi]), np.concatenate([sr, sr]), np.concatenate([UV, UV])
    G = np.stack([(th2 + np.pi) / (4 * np.pi), 1 - (sr2 + 0.1) / 1.2], 1)
    tri, bar = rasterizar(Tw, G, 2 * NT, NS)
    ok = tri >= 0
    g = np.zeros((NS, 2 * NT, 2))
    t, b = Tw[tri[ok]], bar[ok]
    g[ok] = b[:, :1] * UV2[t[:, 0]] + b[:, 1:2] * UV2[t[:, 1]] + b[:, 2:] * UV2[t[:, 2]]
    oka = ok[:, :NT]
    g = np.where(oka[..., None], g[:, :NT], g[:, NT:])
    return sangrar(g, oka | ok[:, NT:])


def manga_longa_pes(pes, lado, sr, th, n=2048):
    """UV do PES na manga longa desse lado para os pontos (s, θ) da manga longa do FC.
    A manga longa do PES é medida na própria UV: em cada linha (v) da ilha, a cava de um lado e o punho do outro, e as
    linhas são as voltas em torno do braço (as listras ao longo da manga ficam retas, como nos kits do FC). O ângulo de
    cada linha é o da malha perto da cava, onde a manga longa veste o mesmo lugar que a curta."""
    V, T, UV = pes
    T = T[np.sign(V[T].mean(1)[:, 0]) == lado]
    br = Braco(V, T, 1e-3)
    idx = np.unique(T)
    s_v, th_v = br.srel(V[idx])
    uv = UV[idx]
    tri, _ = rasterizar(T, UV, n, n)
    ilha = tri >= 0
    linhas = np.nonzero(ilha.any(1))[0]
    xs = [np.nonzero(ilha[y])[0] for y in linhas]
    umin = np.array([x.min() for x in xs]) / n
    umax = np.array([x.max() + 1 for x in xs]) / n
    vl = 1 - (linhas + 0.5) / n                          # v (para cima) de cada linha
    punho_no_max = np.corrcoef(uv[:, 0], s_v)[0, 1] > 0
    # ângulo de cada linha, perto da cava
    perto = s_v < 0.3
    nb = 48
    bordas = np.linspace(vl.min(), vl.max(), nb + 1)
    c, a = [], []
    for k in range(nb):
        m = perto & (uv[:, 1] >= bordas[k]) & (uv[:, 1] <= bordas[k + 1])
        if m.sum() >= 2:
            c.append((bordas[k] + bordas[k + 1]) / 2)
            a.append(np.angle(np.exp(1j * th_v[m]).mean()))
    c, a = np.array(c), np.unwrap(np.array(a))
    if a[-1] < a[0]:
        c, a = c[::-1], a[::-1]
    # θ do FC -> v do PES (θ deslocado de 2π para cair na faixa medida; fora dela, a costura)
    lo, hi = a[0], a[-1]
    t = lo + np.mod(th - lo, 2 * np.pi)
    fora = t > hi
    t[fora] = np.where(t[fora] - hi < lo + 2 * np.pi - t[fora], hi, lo)
    v = np.interp(t, a, c)
    o = np.argsort(vl)
    u0, u1 = np.interp(v, vl[o], umin[o]), np.interp(v, vl[o], umax[o])
    cava, punho = (u0, u1) if punho_no_max else (u1, u0)
    pad = 1.5 / n                                        # meio pixel para dentro da ilha
    cava = cava + np.sign(punho - cava) * pad
    punho = punho - np.sign(punho - cava) * pad
    return np.stack([cava + sr * (punho - cava), v], 1)


def na_grade(g, sr, th):
    iy = np.clip(np.round((sr + 0.1) / 1.2 * NS - 0.5), 0, NS - 1).astype(int)
    ix = np.round((th + np.pi) / (2 * np.pi) * NT - 0.5).astype(int) % NT
    return g[iy, ix]


def sangrar(mapa, valido):
    """Fora dos pixels válidos, copia o válido mais próximo."""
    _, (iy, ix) = nd.distance_transform_edt(~valido, return_indices=True)
    return mapa[iy, ix]


# ------------------------------------------------------------------ peças
def papeis_camisa(V, T, ilha):
    """Ilhas da camisa do FC: tronco (a maior), mangas (|x| > 15 cm, por lado) e gola (pequena, no alto do centro)."""
    info = {}
    for i in np.unique(ilha):
        p = V[T[ilha == i]].reshape(-1, 3)
        info[int(i)] = (int((ilha == i).sum()), p.mean(0))
    tronco = max(info, key=lambda i: info[i][0])
    mangas = {int(np.sign(c[0])): i for i, (n, c) in info.items() if abs(c[0]) > 0.15}
    resto = [i for i in info if i != tronco and i not in mangas.values()]
    gola = max(resto, key=lambda i: info[i][1][1]) if resto else None
    return tronco, mangas, gola


def camisa(obj, fc, log=print):
    W, H = TAMANHOS["jersey"]
    V, T, UV, ilha = fc
    tronco, mangas, gola = papeis_camisa(V, T, ilha)
    mapa = np.zeros((H, W, 2))
    parte = np.zeros((H, W), np.uint8)
    ok, uv, d = mapa_superficie((V, T, UV), ilha == tronco, W, H, malha_pes(obj, PES_PARTES["tronco"]))
    mapa[ok], parte[ok] = uv, TRONCO
    log(f"  tronco: {ok.sum()} px, distância mediana {np.median(d):.2f}")
    v_curta = {}
    for nome, tipo in (("manga_curta", MANGA_CURTA), ("manga_longa", MANGA_LONGA)):
        pes = malha_pes(obj, PES_PARTES[nome])
        for lado, i in mangas.items():
            if tipo == MANGA_CURTA:
                g = grade_manga_pes(pes, lado)
                sel = ilha == i
                ok, pos, _ = pontos_fc(V, T, UV, sel, W, H)
                br = Braco(V, T[sel], 1e-5)
                sr, th = br.srel(pos)
                mapa[ok], parte[ok] = na_grade(g, np.clip(sr, 0, 1), th), MANGA_CURTA
                # volta da manga em cada linha (v relativo), para a manga longa
                ys = np.nonzero(ok)[0]
                v = (ys + 0.5) / H
                vr = (v - v.min()) / (v.max() - v.min())
                b = np.clip((vr * 64).astype(int), 0, 63)
                med = np.unwrap([np.angle(np.exp(1j * th[b == j]).mean()) for j in range(64)])
                v_curta[lado] = ((np.arange(64) + 0.5) / 64, med)
                log(f"  manga curta {'esquerda' if lado > 0 else 'direita'}: {ok.sum()} px")
            else:
                from PIL import Image, ImageDraw
                poli = np.array(MOLDE_LONGA)
                if lado > 0:
                    poli = np.stack([1 - poli[:, 0], poli[:, 1]], 1)
                im = Image.new("L", (W, H), 0)
                ImageDraw.Draw(im).polygon([(a * W, b * H) for a, b in poli], fill=255)
                dentro = np.asarray(im) > 127
                ys, xs = np.nonzero(dentro)
                u, v = (xs + 0.5) / W, (ys + 0.5) / H
                uu = u if lado < 0 else 1 - u
                borda = np.array(MOLDE_LONGA)[1:-1]
                ua = np.interp(v, borda[:, 1], borda[:, 0])
                sr = np.clip((ua - uu) / ua, 0, 1)
                vr = (v - MOLDE_LONGA[0][1]) / (MOLDE_LONGA[-1][1] - MOLDE_LONGA[0][1])
                th = np.interp(vr, *v_curta[lado])
                livre = parte[ys, xs] == FORA
                mapa[ys[livre], xs[livre]] = manga_longa_pes(pes, lado, sr[livre], th[livre])
                parte[ys[livre], xs[livre]] = MANGA_LONGA
                log(f"  manga longa {'esquerda' if lado > 0 else 'direita'}: {livre.sum()} px")
    if gola is not None:
        Vp, Tp, UVp = malha_pes(obj, PES_PARTES["gola"])
        Tp = Tp[(1 - UVp[Tp].mean(1)[:, 1]) > 0.85]          # só a faixa da gola (a carcela fica no tronco)
        ok, uv, d = mapa_superficie((V, T, UV), ilha == gola, W, H, (Vp, Tp, UVp))
        mapa[ok], parte[ok] = uv, GOLA
        log(f"  gola: {ok.sum()} px")
    u0, v0, u1, v1 = BRACADEIRA
    parte[int(v0 * H):int(v1 * H), int(u0 * W):int(u1 * W)] = DO_BASE
    return mapa, parte


def calcao(obj, fc, log=print):
    W, H = TAMANHOS["shorts"]
    V, T, UV, _ = fc
    ok, uv, d = mapa_superficie((V, T, UV), np.ones(len(T), bool), W, H, malha_pes(obj, PES_PARTES["calcao"]))
    mapa = np.zeros((H, W, 2))
    mapa[ok] = uv
    log(f"  calção: {ok.sum()} px, distância mediana {np.median(d):.2f}")
    return mapa, ok.astype(np.uint8) * TRONCO


def meiao(obj, fc, log=print):
    W, H = TAMANHOS["socks"]
    V, T, UV, _ = fc
    Vp, Tp, UVp = malha_pes(obj, PES_PARTES["meiao"])
    mapa = np.zeros((H, W, 2))
    parte = np.zeros((H, W), np.uint8)
    for lado in (-1, 1):
        tp = Tp[np.sign(Vp[Tp].mean(1)[:, 0]) == lado]
        sel = np.sign(V[T].mean(1)[:, 0]) == lado
        ok, uv, d = mapa_superficie((V, T, UV), sel, W, H, (Vp, tp, UVp))
        mapa[ok], parte[ok] = uv, TRONCO
        log(f"  meião {'esquerdo' if lado > 0 else 'direito'}: {ok.sum()} px, distância mediana {np.median(d):.2f}")
    return mapa, parte


def escala_pes(mapa, parte):
    """Quantos pixels do PES (em 2048) cabem num pixel do FC: para filtrar (mipmap) onde a textura encolhe."""
    du = np.zeros(mapa.shape[:2])
    for eixo in (0, 1):
        dif = np.abs(np.diff(mapa, axis=eixo)).max(-1) * 2048
        mesma = (parte[1:] == parte[:-1]) if eixo == 0 else (parte[:, 1:] == parte[:, :-1])
        dif = np.where(mesma & (dif < 64), dif, 0)
        pad = ((0, 1), (0, 0)) if eixo == 0 else ((0, 0), (0, 1))
        du = np.maximum(du, np.pad(dif, pad, mode="edge"))
    return du


def gerar(saida, log=print):
    t0 = time.time()
    obj = ler_obj(PES_OBJ)
    pecas = {"jersey": camisa, "shorts": calcao, "socks": meiao}
    dados = {}
    for peca, fn in pecas.items():
        log(f"{peca}…")
        mapa, parte = fn(obj, malha_fc(peca), log)
        valido = parte != FORA
        cheio = sangrar(mapa, valido)
        esc = sangrar(escala_pes(cheio, parte), valido)
        q = np.clip(np.round(cheio * 65535), 0, 65535).astype(np.int32)
        # delta ao longo das linhas: comprime ~4×
        dados[f"{peca}_du"] = np.diff(q[..., 0], axis=1, prepend=0).astype(np.int16)
        dados[f"{peca}_dv"] = np.diff(q[..., 1], axis=1, prepend=0).astype(np.int16)
        dados[f"{peca}_parte"] = parte
        dados[f"{peca}_escala"] = np.clip(np.round(esc * 8), 0, 255).astype(np.uint8)
    # ilhas da UV do PES (onde a textura do PES é usada): fora delas o conversor repete a borda antes de filtrar
    Vp, Tp, UVp = malha_pes(obj, [n for ns in PES_PARTES.values() for n in ns])
    ilhas = nd.binary_dilation(rasterizar(Tp, UVp, 2048, 2048)[0] >= 0, iterations=2)
    dados["pes_ilhas"] = np.packbits(ilhas, axis=1)
    dados["versao"] = np.array(1)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    np.savez_compressed(saida, **dados)
    log(f"gravado {saida} ({os.path.getsize(saida) / 1e6:.1f} MB) em {time.time() - t0:.0f} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", default=os.path.join(AQUI, "mapas", "mapas_pes2021_fc27.npz"))
    gerar(ap.parse_args().saida)


if __name__ == "__main__":
    main()
