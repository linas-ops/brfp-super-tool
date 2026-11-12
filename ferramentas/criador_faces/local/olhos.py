"""Olhos no padrão do jogo.

No FC 27 a malha de cada globo ocular é meia esfera e a íris é desenhada pela UV0 (centro da íris no meio da textura
dos olhos). Cada cabeça do jogo gira a malha e acerta a UV de um jeito próprio, então posição e UV precisam sair
juntas: aqui cada globo é a esfera prevista para a cabeça (centro e raio) com a orientação e a UV médias das cabeças
do jogo, o que deixa a íris apontando para a frente como nelas. A borda das pálpebras é encostada no globo quando o
ajuste às fotos a deixou longe demais (senão aparece um vão escuro no canto do olho).
"""
import numpy as np
from scipy.spatial import cKDTree

from . import caminhos
from . import modelo as MD


def globos(modelo, X):
    """centro e raio de cada globo (0 = x negativo, 1 = x positivo): média entre a esfera dos vértices dos olhos
    previstos pelo modelo e a prevista pela borda das pálpebras da cabeça ajustada"""
    e, h = modelo.secao("eyes_mat"), modelo.secao("head_mat")
    E = X[e["off"]:e["off"] + e["n"]]
    H = X[h["off"]:h["off"] + h["n"]]
    aro = modelo.aro
    out = []
    for s, lado in enumerate((e["V"][:, 0] < 0, e["V"][:, 0] >= 0)):
        c1, r1 = MD.esferas(E[lado][None])
        A = H[aro["idx"][aro["lado"] == s]]
        ca = A.mean(0)
        y = np.r_[(A - ca).ravel(), 1.0] @ aro["reg"][s]
        c2, r2 = ca + y[:3], y[3]
        out.append((0.5 * (c1[0] + c2), 0.5 * (r1[0] + r2)))
    return out


def encostar_palpebras(modelo, X, gl, sigma=0.006):
    """leva cada vértice da borda das pálpebras para a faixa de distâncias ao centro do globo que as cabeças do jogo
    têm (em raios) e espalha o deslocamento pela pele em volta; os outros LODs acompanham"""
    caminhos()
    import geometria as G
    h = modelo.secao("head_mat")
    H = X[h["off"]:h["off"] + h["n"]]
    aro = modelo.aro
    desloc = np.zeros_like(H)
    peso = np.zeros(len(H))
    maior = 0.0
    for s, (c, r) in enumerate(gl):
        sel = aro["lado"] == s
        idx = aro["idx"][sel]
        v = H[idx] - c
        dist = np.linalg.norm(v, axis=1)
        alvo = np.clip(dist / r, aro["razao_min"][sel], aro["razao_max"][sel]) * r
        d = (v / dist[:, None]) * (alvo - dist)[:, None]
        maior = max(maior, float(np.abs(alvo - dist).max()))
        # cada vértice da pele recebe o deslocamento do vértice do aro mais próximo, com queda suave pela distância
        geo = G.distancia_geodesica(H, h["T"], idx)
        perto = np.nonzero(geo < 3 * sigma)[0]
        _, j = cKDTree(H[idx]).query(H[perto])
        w = np.exp(-0.5 * (geo[perto] / sigma) ** 2)
        desloc[perto] += d[j] * w[:, None]
        peso[perto] += w
    X = X.copy()
    X[h["off"]:h["off"] + h["n"]] = H + desloc
    # LODs menores: o mesmo deslocamento do vértice do LOD0 que ocupa o mesmo lugar na cabeça base
    arv = cKDTree(h["V"])
    for s in modelo.secoes:
        if s["mat"] == "head_mat" and s["lod"] > 0:
            _, j = arv.query(s["V"])
            X[s["off"]:s["off"] + s["n"]] += desloc[j]
    return X, maior


def aplicar(modelo, X):
    """-> (posições novas, {lod: UV dos olhos}, informações)"""
    gl = globos(modelo, X)
    X, maior = encostar_palpebras(modelo, X, gl)
    uvs = {}
    for lod in (0, 1, 2):
        s = modelo.secao("eyes_mat", lod)
        ref = modelo.olhos[lod]
        P = np.zeros((s["n"], 3))
        for k, lado in enumerate((s["V"][:, 0] < 0, s["V"][:, 0] >= 0)):
            c, r = gl[k]
            P[lado] = c + ref["desloc"][k] + r * ref["raio_rel"][k] * ref["dir"][lado]
        X[s["off"]:s["off"] + s["n"]] = P
        uvs[lod] = ref["uv"].copy()
    return X, uvs, dict(centros=[g[0].tolist() for g in gl], raios=[float(g[1]) for g in gl], aro_mm=maior * 1000)
