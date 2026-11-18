"""Gera os mapas de correspondência PES 2021 -> FC 27 (motor/mapas/mapas_pes2021_fc27.npz). Só para quem desenvolve:
a ferramenta usa o arquivo pronto e não precisa dos modelos.

    python gerar_mapas.py [--saida mapas/mapas_pes2021_fc27.npz]

Precisa dos modelos de referência em motor/referencia (tirados dos jogos, fora do repositório público):
  - pes2021_kit.obj: o kit do PES 2021 com a UV do jogo (camisa, mangas, golas, calção e meião);
  - jersey_0_0_0_0_1_0_0_mesh.fbx, shorts_0_0_0_mesh.fbx, sock_0_0_1_0_0_mesh.fbx: as malhas LOD0 do FC 27 exportadas pelo FET.

Para cada pixel da textura do FC (camisa 2048×2048, calção 1024×512, meião 512×256) acha o ponto do uniforme do PES que
veste o mesmo lugar do corpo e guarda a UV do PES ali:
  - camisa: o molde plano do tronco e os dois comprimentos de manga compartilham a correspondência das cavas.
    As costuras vêm dos vértices 3D comuns. O centro do peito e das costas usa escala uniforme;
  - calção e meião: projeção na superfície 3D do PES, preferindo triângulos com a mesma orientação.
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
def rasterizar(T, UV, w, h, margem=0.02):
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
        m = (l1 >= -margem) & (l2 >= -margem) & (l3 >= -margem)
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


# ------------------------------------------------------------------ bordas das malhas
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


# ------------------------------------------------------------------ molde plano da camisa
def uv_plana(uv, lado):
    """Coordenadas do molde, da borda da textura para o centro e de cima para baixo."""
    return np.column_stack((uv[:, 0] if lado < 0 else 1 - uv[:, 0], 1 - uv[:, 1]))


def costura_aberta(V, T, uv, lado):
    """Pares de UV do mesmo vértice 3D nos dois lados do corte que abre a peça."""
    pares = {}
    for i in np.unique(T):
        if V[i, 0] * lado > 0:
            pares.setdefault(tuple(V[i].round(5)), set()).add(tuple(uv[i]))
    alturas, costas, frente = [], [], []
    for pos, cantos in sorted(pares.items(), key=lambda item: item[0][1]):
        a, b = min(cantos, key=lambda p: p[1]), max(cantos, key=lambda p: p[1])
        if b[1] - a[1] > 0.1:
            alturas.append(pos[1])
            costas.append(a)
            frente.append(b)
    return np.asarray(alturas), np.asarray(costas), np.asarray(frente)


def uv_na_cava(V, T, uv, laco, tolerancia):
    ids = np.unique(T)
    d, _ = cKDTree(laco).query(V[ids])
    pontos = np.unique(uv[ids[d < tolerancia]], axis=0)
    return pontos[np.argsort(pontos[:, 1])]


def molde_manga(malha, lado, tolerancia):
    V, T, UV = malha
    T = T[lado * V[T, 0].mean(1) > 0]
    uv = uv_plana(UV, lado)
    _, cava = sorted(lacos(V, T, tolerancia)[:2], key=lambda p: -abs(p[:, 0].mean()))
    _, costas, frente = costura_aberta(V, T, uv, lado)
    return (uv_na_cava(V, T, uv, cava, tolerancia), costas, frente), cava


def fracao(x, a, b):
    return np.clip((x - a) / (b - a), 0.0, 1.0)


def suave(t):
    return t * t * (3 - 2 * t)


def bordo_tronco(costura, cava):
    _, costas, frente = costura
    pontos = np.concatenate((costas, cava, frente))
    return pontos[np.argsort(pontos[:, 1])]


def x_da_borda(borda, y):
    return np.interp(y, borda[:, 1], borda[:, 0])


def mapa_tronco(x, y, cost_fc, cava_fc, cost_pes, cava_pes):
    """Centro com escala uniforme. Nas laterais a UV converge para as costuras de barra, axila e manga."""
    alt_fc, costas_fc, frente_fc = cost_fc
    alt_pes, costas_pes, frente_pes = cost_pes
    altura = fracao(alt_fc, alt_fc[0], alt_fc[-1])
    altura_pes = fracao(alt_pes, alt_pes[0], alt_pes[-1])
    # A mesma altura física nos dois lados do corte lateral, também onde o molde das costas é mais estreito.
    y_fc = np.r_[costas_fc[:, 1], frente_fc[::-1, 1]]
    y_pes = np.r_[np.interp(altura, altura_pes, costas_pes[:, 1]),
                  np.interp(altura[::-1], altura_pes, frente_pes[:, 1])]
    y_costura = np.interp(y, y_fc, y_pes)
    ombro_fc = (cava_fc[0, 1] + cava_fc[-1, 1]) / 2
    ombro_pes = (cava_pes[0, 1] + cava_pes[-1, 1]) / 2
    escala = np.where(y < ombro_fc, (ombro_pes - y_pes[0]) / (ombro_fc - y_fc[0]),
                      (y_pes[-1] - ombro_pes) / (y_fc[-1] - ombro_fc))
    bordo_fc = bordo_tronco(cost_fc, cava_fc)
    largura = 0.5 - x_da_borda(bordo_fc, y)
    r = fracao(0.5 - x, 0, largura)
    peso = suave(fracao(r, 0.48, 1))
    yp = (1 - peso) * (ombro_pes + escala * (y - ombro_fc)) + peso * y_costura
    # A largura da peça é medida na linha da costura. A altura no interior pode ser
    # diferente: usar essa altura para buscar a borda dobraria a UV junto à axila.
    largura_pes = 0.5 - x_da_borda(bordo_tronco(cost_pes, cava_pes), y_costura)
    y_central = ombro_fc + (yp - ombro_pes) / escala
    largura_central = escala * (0.5 - x_da_borda(bordo_fc, y_central))
    xp = 0.5 - (r * largura_central + peso * (largura_pes - largura_central))
    return np.column_stack((xp, yp))


def grade_manga(molde, s, t):
    """Faixas entre punho e cava. O recorte da axila é absorvido perto das bordas do molde."""
    cava, superior, inferior = molde
    superior = superior[np.argsort(superior[:, 0])]
    inferior = inferior[np.argsort(inferior[:, 0])]
    y = cava[0, 1] + t * (cava[-1, 1] - cava[0, 1])
    punho = (1 - t) * superior[0, 0] + t * inferior[0, 0]
    x = (1 - s) * punho + s * x_da_borda(cava, y)
    # Cantos de um mesmo s nas duas bordas que se fecham debaixo do braço.
    xs = (1 - s) * superior[0, 0] + s * cava[0, 0]
    xi = (1 - s) * inferior[0, 0] + s * cava[-1, 0]
    dy_sup = np.interp(xs, superior[:, 0], superior[:, 1]) - cava[0, 1]
    dy_inf = np.interp(xi, inferior[:, 0], inferior[:, 1]) - cava[-1, 1]
    y = y + dy_sup * suave(fracao(0.4 - t, 0, 0.4)) + dy_inf * suave(fracao(t - 0.6, 0, 0.4))
    return np.stack((x, y), -1)


def transferir_manga(molde_fc, molde_pes, lado, w, h):
    # Inclui cada vértice da cava para coincidir com o tronco até na ponta da axila.
    ts = [np.linspace(0, 1, 65)]
    for cava, _, _ in (molde_fc, molde_pes):
        ts.append(fracao(cava[:, 1], cava[0, 1], cava[-1, 1]))
    t = np.unique(np.round(np.concatenate(ts), 9))
    s, t = np.meshgrid(np.linspace(0, 1, 33), t)
    dst = uv_plana(grade_manga(molde_fc, s, t).reshape(-1, 2), lado)
    src = uv_plana(grade_manga(molde_pes, s, t).reshape(-1, 2), lado)
    idx = np.arange(s.size).reshape(s.shape)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    T = np.concatenate((np.stack((a, b, c), -1), np.stack((c, b, d), -1))).reshape(-1, 3)
    tri, bar = rasterizar(T, dst, w, h, margem=1e-7)
    ok = tri >= 0
    mapa = np.zeros((h, w, 2))
    mapa[ok] = (bar[ok, :, None] * src[T[tri[ok]]]).sum(1)
    return ok, mapa


def sangrar(mapa, valido):
    """Fora dos pixels válidos, copia o válido mais próximo."""
    iy, ix = nd.distance_transform_edt(~valido, return_distances=False, return_indices=True)
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
    torso_fc = T[ilha == tronco]
    Vp, Tp, UVp = malha_pes(obj, PES_PARTES["tronco"])
    mapa = np.zeros((H, W, 2))
    parte = np.zeros((H, W), np.uint8)
    corpo = rasterizar(torso_fc, UV, W, H, margem=1e-7)[0] >= 0
    parte[corpo] = TRONCO
    ys, xs = np.nonzero(corpo)
    for lado, i in mangas.items():
        manga_fc, laco_fc = molde_manga((V, T[ilha == i], UV), lado, 1e-5)
        curta, laco_pes = molde_manga(malha_pes(obj, PES_PARTES["manga_curta"]), lado, 1e-3)
        longa, _ = molde_manga(malha_pes(obj, PES_PARTES["manga_longa"]), lado, 1e-3)
        ufc, upes = uv_plana(UV, lado), uv_plana(UVp, lado)
        cava_fc = uv_na_cava(V, torso_fc, ufc, laco_fc, 1e-5)
        cava_pes = uv_na_cava(Vp, Tp, upes, laco_pes, 1e-3)
        cost_fc = costura_aberta(V, torso_fc, ufc, lado)
        cost_pes = costura_aberta(Vp, Tp, upes, lado)
        metade = (xs + 0.5 < W / 2) if lado < 0 else (xs + 0.5 >= W / 2)
        x, y = xs[metade], ys[metade]
        u = (x + 0.5) / W
        pontos = mapa_tronco(u if lado < 0 else 1 - u, (y + 0.5) / H, cost_fc, cava_fc, cost_pes, cava_pes)
        mapa[y, x] = uv_plana(pontos, lado)

        # Na textura de manga longa do FC a cava encosta no tronco. Os punhos e as duas
        # bordas sob o braço foram medidos nas texturas de referência (2048 px).
        superior = np.array([[0, 700], [600, 700]]) / 2048
        inferior = np.array([[0, 1340], [590, 1340]]) / 2048
        molde_longo = (cava_fc, np.vstack((superior, cava_fc[0])), np.vstack((inferior, cava_fc[-1])))
        for tipo, destino, origem in ((MANGA_CURTA, manga_fc, curta), (MANGA_LONGA, molde_longo, longa)):
            ok, uv = transferir_manga(destino, origem, lado, W, H)
            if tipo == MANGA_CURTA:
                exata = rasterizar(T[ilha == i], UV, W, H, margem=1e-7)[0] >= 0
                faltam = exata & ~ok
                if faltam.any():
                    uv[faltam] = sangrar(uv, ok)[faltam]
                ok = exata
            ok &= parte == FORA
            mapa[ok], parte[ok] = uv[ok], tipo
        log(f"  tronco e mangas registrados na cava do lado {lado}")
    if gola is not None:
        ok = rasterizar(T[ilha == gola], UV, W, H, margem=1e-7)[0] >= 0
        parte[ok & (parte == FORA)] = GOLA
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
        # Na camisa a sangria usa a cor final, inclusive na braçadeira e na gola.
        cheio = mapa if peca == "jersey" else sangrar(mapa, parte != FORA)
        esc = escala_pes(cheio, parte)
        if peca != "jersey":
            esc = sangrar(esc, parte != FORA)
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
    # buraco da gola no tronco do PES (decote e carcela): o conversor continua ali o desenho do tronco
    Vt, Tt, UVt = malha_pes(obj, PES_PARTES["tronco"])
    tr = nd.binary_closing(rasterizar(Tt, UVt, 2048, 2048)[0] >= 0, iterations=2)
    dados["pes_buraco"] = np.packbits(nd.binary_fill_holes(tr) & ~tr, axis=1)
    dados["versao"] = np.array(3)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    np.savez_compressed(saida, **dados)
    log(f"gravado {saida} ({os.path.getsize(saida) / 1e6:.1f} MB) em {time.time() - t0:.0f} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", default=os.path.join(AQUI, "mapas", "mapas_pes2021_fc27.npz"))
    gerar(ap.parse_args().saida)


if __name__ == "__main__":
    main()
