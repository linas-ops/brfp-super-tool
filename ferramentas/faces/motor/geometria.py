"""Rotinas geométricas usadas pelo conversor de faces."""
import collections

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree


def ilhas(T, n):
    """componentes conexas (por vértices compartilhados); rótulo 0 = maior ilha"""
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    A = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    _, lab = connected_components(A, directed=False)
    ordem = np.argsort(-np.bincount(lab))
    remap = np.empty_like(ordem)
    remap[ordem] = np.arange(len(ordem))
    return remap[lab]


def normais_triangulo(V, T):
    N = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    return N / np.maximum(np.linalg.norm(N, axis=1), 1e-20)[:, None]


def normais_vertice(V, T, soldar=True):
    """normais ponderadas por área; vértices na mesma posição (costuras de UV) compartilham a normal"""
    Nf = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for i in range(3):
        np.add.at(N, T[:, i], Nf)
    if soldar:
        _, inv = np.unique(np.round(V, 6), axis=0, return_inverse=True)
        inv = inv.ravel()
        G = np.zeros((inv.max() + 1, 3))
        np.add.at(G, inv, N)
        N = G[inv]
    return N / np.maximum(np.linalg.norm(N, axis=1), 1e-20)[:, None]


def rotacao_minima(a, b):
    """matrizes (n,3,3) que levam os vetores unitários a -> b pela menor rotação"""
    v = np.cross(a, b)
    c = (a * b).sum(1)
    K = np.zeros((len(a), 3, 3))
    K[:, 0, 1], K[:, 0, 2] = -v[:, 2], v[:, 1]
    K[:, 1, 0], K[:, 1, 2] = v[:, 2], -v[:, 0]
    K[:, 2, 0], K[:, 2, 1] = -v[:, 1], v[:, 0]
    f = 1.0 / np.maximum(1.0 + c, 1e-8)
    R = np.eye(3)[None] + K + (K @ K) * f[:, None, None]
    oposto = c < -0.999999
    R[oposto] = np.eye(3)
    return R


def ponto_mais_proximo(P, A, B, C):
    """ponto mais próximo de P em cada triângulo ABC (vetorizado, Ericson); devolve (Q, bary)"""
    AB, AC, AP = B - A, C - A, P - A
    d1, d2 = (AB * AP).sum(1), (AC * AP).sum(1)
    BP = P - B
    d3, d4 = (AB * BP).sum(1), (AC * BP).sum(1)
    CP = P - C
    d5, d6 = (AB * CP).sum(1), (AC * CP).sum(1)
    vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
    n = len(P)
    bary = np.zeros((n, 3))
    feito = np.zeros(n, bool)

    def put(mask, b):
        m = mask & ~feito
        bary[m] = b[m] if np.ndim(b) == 2 else b
        feito[m] = True

    z = np.zeros(n)
    with np.errstate(divide='ignore', invalid='ignore'):
        put((d1 <= 0) & (d2 <= 0), np.array([1.0, 0, 0]))
        put((d3 >= 0) & (d4 <= d3), np.array([0, 1.0, 0]))
        v = d1 / (d1 - d3)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), np.stack([1 - v, v, z], 1))
        put((d6 >= 0) & (d5 <= d6), np.array([0, 0, 1.0]))
        w = d2 / (d2 - d6)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), np.stack([1 - w, z, w], 1))
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), np.stack([z, 1 - w, w], 1))
        den = 1.0 / (va + vb + vc)
        v, w = vb * den, vc * den
        put(np.ones(n, bool), np.stack([1 - v - w, v, w], 1))
    bary = np.nan_to_num(bary, nan=1.0 / 3)
    Q = bary[:, :1] * A + bary[:, 1:2] * B + bary[:, 2:] * C
    return Q, bary


class Superficie:
    """consulta de ponto mais próximo numa malha triangular (subconjunto de triângulos)"""

    def __init__(self, V, T, k=24):
        self.V, self.T, self.k = V, T, min(k, len(T))
        self.Nt = normais_triangulo(V, T)
        self.arvore = cKDTree(V[T].mean(1))

    def consulta(self, P, normais=None, cos_min=0.0):
        P = np.asarray(P, float)
        _, cand = self.arvore.query(P, k=self.k)
        cand = cand.reshape(len(P), -1)
        best_d = np.full(len(P), np.inf)
        best_t = np.zeros(len(P), int)
        best_b = np.zeros((len(P), 3))
        livre_d = np.full(len(P), np.inf)
        livre_t = np.zeros(len(P), int)
        livre_b = np.zeros((len(P), 3))
        for j in range(cand.shape[1]):
            t = cand[:, j]
            Q, b = ponto_mais_proximo(P, *(self.V[self.T[t, i]] for i in range(3)))
            d = np.linalg.norm(P - Q, axis=1)
            m = d < livre_d
            livre_d[m], livre_t[m], livre_b[m] = d[m], t[m], b[m]
            if normais is not None:
                ok = (self.Nt[t] * normais).sum(1) >= cos_min
                d = np.where(ok, d, np.inf)
            m = d < best_d
            best_d[m], best_t[m], best_b[m] = d[m], t[m], b[m]
        sem = ~np.isfinite(best_d)
        best_d[sem], best_t[sem], best_b[sem] = livre_d[sem], livre_t[sem], livre_b[sem]
        return best_d, best_t, best_b


def bary2d(P, A, B, C):
    v0, v1, v2 = B - A, C - A, P - A
    d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
    d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
    den = d00 * d11 - d01 * d01
    with np.errstate(divide='ignore', invalid='ignore'):
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
    return np.nan_to_num(np.stack([1 - v - w, v, w], -1), nan=-1e9)


class LocalizadorUV:
    """encontra o triângulo (num subconjunto) que contém cada ponto UV"""

    def __init__(self, UV, T, k=32):
        self.UV, self.T, self.k = UV, T, min(k, len(T))
        self.arvore = cKDTree(UV[T].mean(1))

    def consulta(self, Q):
        Q = np.asarray(Q, float)
        _, cand = self.arvore.query(Q, k=self.k)
        cand = cand.reshape(len(Q), -1)
        best = np.full(len(Q), -np.inf)
        bt = np.zeros(len(Q), int)
        bb = np.zeros((len(Q), 3))
        for j in range(cand.shape[1]):
            t = cand[:, j]
            b = bary2d(Q, *(self.UV[self.T[t, i]] for i in range(3)))
            s = b.min(1)
            m = s > best
            best[m], bt[m], bb[m] = s[m], t[m], b[m]
        fora = best < -1e-6
        if fora.any():
            # fora de todos os triângulos: projeta no mais próximo
            P = np.c_[Q[fora], np.zeros(fora.sum())]
            dmin = np.full(fora.sum(), np.inf)
            for j in range(cand.shape[1]):
                t = cand[fora, j]
                tri = [np.c_[self.UV[self.T[t, i]], np.zeros(len(t))] for i in range(3)]
                Qc, b = ponto_mais_proximo(P, *tri)
                d = np.linalg.norm(P - Qc, axis=1)
                m = d < dmin
                dmin[m] = d[m]
                bt[np.where(fora)[0][m]] = t[m]
                bb[np.where(fora)[0][m]] = b[m]
        bb = np.clip(bb, 0, None)
        bb /= bb.sum(1, keepdims=True)
        return bt, bb, ~fora


def pesos_suaves(origem, destino, k=16, sigma_min=0.004):
    """pesos gaussianos (Shepard) de cada ponto de destino sobre os k vizinhos de origem"""
    k = min(k, len(origem))
    d, idx = cKDTree(origem).query(destino, k=k)
    d, idx = d.reshape(len(destino), -1), idx.reshape(len(destino), -1)
    sigma = np.maximum(d[:, :1] * 1.5, sigma_min)
    w = np.exp(-(d / sigma) ** 2)
    w /= w.sum(1, keepdims=True)
    return idx, w


def matriz_esparsa(linhas, cols, pesos, n_lin, n_col):
    return csr_matrix((np.asarray(pesos, float).ravel(), (np.asarray(linhas).ravel(), np.asarray(cols).ravel())),
                      shape=(n_lin, n_col))


def bordas_abertas(T):
    """vértices em arestas usadas por um único triângulo"""
    cnt = collections.Counter()
    for a, b in np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1):
        cnt[(a, b)] += 1
    return np.array(sorted({v for (a, b), c in cnt.items() if c == 1 for v in (a, b)}), int)


def anel_do_pescoco(V, T):
    """vértices do laço de borda aberta que contém o vértice de borda mais baixo (base do pescoço).
    Vértices duplicados na mesma posição (costuras de UV) são tratados como um só."""
    _, inv = np.unique(np.round(V, 6), axis=0, return_inverse=True)
    inv = inv.ravel()
    Ts = inv[T]
    cnt = collections.Counter()
    for a, b in np.sort(np.concatenate([Ts[:, [0, 1]], Ts[:, [1, 2]], Ts[:, [2, 0]]]), 1):
        if a != b:
            cnt[(a, b)] += 1
    arestas = np.array([k for k, c in cnt.items() if c == 1], int).reshape(-1, 2)
    if len(arestas) == 0:
        return np.zeros(0, int)
    ng = inv.max() + 1
    A = coo_matrix((np.ones(len(arestas)), (arestas[:, 0], arestas[:, 1])), shape=(ng, ng))
    _, lab = connected_components(A, directed=False)
    nos = np.unique(arestas)
    pos = np.zeros((ng, 3))
    pos[inv] = V
    mais_baixo = nos[np.argmin(pos[nos, 1])]
    grupo = set(nos[lab[nos] == lab[mais_baixo]])
    return np.where(np.isin(inv, list(grupo)))[0]


def distancia_geodesica(V, T, fontes):
    """distância ao longo das arestas da malha até o conjunto de vértices 'fontes'"""
    if len(fontes) == 0:
        return np.full(len(V), np.inf)
    e = np.unique(np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1), axis=0)
    # vértices duplicados na mesma posição (costuras) ficam ligados com custo zero
    _, inv = np.unique(np.round(V, 6), axis=0, return_inverse=True)
    inv = inv.ravel()
    order = np.argsort(inv, kind='stable')
    same = order[:-1][inv[order[:-1]] == inv[order[1:]]], order[1:][inv[order[:-1]] == inv[order[1:]]]
    w = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
    rows = np.r_[e[:, 0], same[0]]
    cols = np.r_[e[:, 1], same[1]]
    wts = np.r_[w, np.full(len(same[0]), 1e-9)]
    G = coo_matrix((wts, (rows, cols)), shape=(len(V), len(V))).tocsr()
    d = dijkstra(G, directed=False, indices=fontes, min_only=True)
    return d


def grupos_duplicados(V):
    """listas de índices de vértices que ocupam a mesma posição (costuras de UV)"""
    _, inv, cnt = np.unique(np.round(V, 6), axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    dup = np.where(cnt[inv] > 1)[0]
    grupos = collections.defaultdict(list)
    for i in dup:
        grupos[inv[i]].append(i)
    return list(grupos.values())


def laplaciano(T, n, V=None):
    """laplaciano uniforme (grafo das arestas); duplicados na mesma posição ficam ligados"""
    e = np.unique(np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1), axis=0)
    rows, cols = [e[:, 0], e[:, 1]], [e[:, 1], e[:, 0]]
    if V is not None:
        for g in grupos_duplicados(V):
            for a in g:
                for b in g:
                    if a != b:
                        rows.append([a])
                        cols.append([b])
    r, c = np.concatenate(rows), np.concatenate(cols)
    A = coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    return (csr_matrix((deg, (np.arange(n), np.arange(n))), shape=(n, n)) - A).tocsr()


def umeyama(X, Y, escala=True):
    """similaridade (s, R, t) que leva X em Y no sentido dos mínimos quadrados"""
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    U, S, Vt = np.linalg.svd(Yc.T @ Xc / len(X))
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt
    s = np.trace(np.diag(S) @ D) / ((Xc ** 2).sum() / len(X)) if escala else 1.0
    return s, R, my - s * R @ mx


def kabsch(X, Y):
    """rotação R (sem translação nem escala) que leva as direções X nas direções Y (mínimos quadrados)"""
    U, _, Vt = np.linalg.svd(Y.T @ X)
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    return U @ D @ Vt


def esfera(P):
    """esfera que melhor passa pelos pontos: (centro, raio, maior desvio)"""
    A = np.c_[2 * P, np.ones(len(P))]
    x = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    c = x[:3]
    r = np.sqrt(max(x[3] + c @ c, 0.0))
    return c, r, np.abs(np.linalg.norm(P - c, axis=1) - r).max()


def phong(P, N, idx, bary, alfa=0.75):
    """ponto na superfície de Phong tessellation (Boubekeur & Alexa 2008) do triângulo idx(n,3)
    com coordenadas baricêntricas bary(n,3); P/N = posições e normais dos vértices"""
    p = P[idx]                                  # (n,3,3)
    n = N[idx]
    lin = (bary[:, :, None] * p).sum(1)         # ponto linear
    proj = lin[:, None, :] - ((lin[:, None, :] - p) * n).sum(2, keepdims=True) * n
    curva = (bary[:, :, None] * proj).sum(1)
    return (1 - alfa) * lin + alfa * curva


def filtro_gaussiano(P, valores, sigma, raio=None):
    """média gaussiana de 'valores' entre pontos vizinhos (3D) até 'raio'"""
    raio = raio or 2.5 * sigma
    arv = cKDTree(P)
    pares = arv.query_pairs(raio, output_type='ndarray')
    i = np.r_[pares[:, 0], pares[:, 1], np.arange(len(P))]
    j = np.r_[pares[:, 1], pares[:, 0], np.arange(len(P))]
    w = np.exp(-(np.linalg.norm(P[i] - P[j], axis=1) / sigma) ** 2)
    W = coo_matrix((w, (i, j)), shape=(len(P), len(P))).tocsr()
    s = np.asarray(W.sum(1)).ravel()
    return (W @ valores) / s[:, None]


def suavizar(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)
