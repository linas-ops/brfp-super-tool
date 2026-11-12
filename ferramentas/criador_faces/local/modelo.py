"""Cabeça base do FC 27 (basehead_0) e modelo estatístico das cabeças masculinas do jogo.

O arquivo cache/modelo.npz é montado uma vez no computador de quem usa (construir), a partir do jogo instalado e da
face de referência exportada pelo FET (a mesma do Conversor de Faces), e refeito quando o jogo muda:

  - cabeça base: a face de referência menos o morph do mesmo jogador lido do jogo (posição e UV dos olhos);
  - PCA dos morphs de todas as cabeças masculinas (todos os LODs juntos: o mesmo coeficiente move tudo);
  - olhos de referência: orientação média do globo e UV média da íris nas cabeças do jogo, por LOD e por olho
    (no jogo cada cabeça gira a malha do olho e acerta a íris pela UV: as duas coisas têm de sair juntas);
  - aro das pálpebras: a que distância do centro do globo fica cada vértice da borda da pálpebra, em raios;
  - peles de base carecas (uma por tom) e a textura dos olhos, guardadas como PNG ao lado.
"""
import json
import os
import struct
import time

import numpy as np

from . import CACHE, ID_REFERENCIA, REFERENCIA, VERSAO_MOTOR, Erro, caminhos
from . import blend as BL

SECOES = [(0, "head_mat", 8353), (0, "eyes_mat", 198), (0, "teeth_mat", 4744),
          (1, "head_mat", 3058), (1, "eyes_mat", 198), (1, "teeth_mat", 756),
          (2, "head_mat", 1048), (2, "eyes_mat", 42), (3, "head_mat", 323)]
K_GUARDADO = 150
ARQUIVO = os.path.join(CACHE, "modelo.npz")
META = os.path.join(CACHE, "modelo.json")
PELES = os.path.join(CACHE, "peles")
OLHO_PNG = os.path.join(CACHE, "olho.png")
TONS = range(1, 11)
IRIS_UV = np.array([0.5, 0.512])        # centro da íris na textura dos olhos (v para cima)


def meta():
    try:
        with open(META, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def pronto(chave=None):
    """o modelo guardado serve? (mesma versão do motor e, se dada, a mesma chave do cache do FET)"""
    m = meta()
    if not m or m.get("versao") != VERSAO_MOTOR or not os.path.isfile(ARQUIVO):
        return False
    if chave is not None and m.get("chave") != chave:
        return False
    return all(os.path.isfile(os.path.join(PELES, "pele_%d.png" % t)) for t in m.get("tons", []))


def esferas(P):
    """esfera de mínimos quadrados por linha: P (n x k x 3) -> (centros n x 3, raios n)"""
    A = np.concatenate([2 * P, np.ones(P.shape[:2] + (1,))], 2)
    b = (P ** 2).sum(2)
    AtA = np.einsum("nki,nkj->nij", A, A)
    Atb = np.einsum("nki,nk->ni", A, b)
    x = np.linalg.solve(AtA, Atb[..., None])[..., 0]
    c = x[:, :3]
    return c, np.sqrt(np.maximum(x[:, 3] + (c ** 2).sum(1), 0))


def lacos_de_borda(T):
    """laços de arestas de borda (usadas por um só triângulo) -> lista de arrays de vértices"""
    E = np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1)
    u, cnt = np.unique(E, axis=0, return_counts=True)
    adj = {}
    for a, b in u[cnt == 1]:
        adj.setdefault(int(a), []).append(int(b))
        adj.setdefault(int(b), []).append(int(a))
    vistos, lacos = set(), []
    for v0 in adj:
        if v0 in vistos:
            continue
        comp, pilha = [], [v0]
        while pilha:
            v = pilha.pop()
            if v in vistos:
                continue
            vistos.add(v)
            comp.append(v)
            pilha += adj[v]
        lacos.append(np.array(sorted(comp)))
    return lacos


# ---------------------------------------------------------------------------------------------- construir
def construir(jogo, prog=lambda f, m: None, log=print):
    """Monta cache/modelo.npz e as peles de base a partir do jogo. Leva de 1 a 2 minutos."""
    caminhos()
    import cv2
    from cena import Cena
    t0 = time.time()
    os.makedirs(CACHE, exist_ok=True)
    if not os.path.isfile(REFERENCIA):
        raise Erro("Falta a face de referência do FC 27 (messi_158023_fc27.fbx), a mesma do Conversor de Faces. "
                   "Use Importar referências.")
    prog(0.01, "Lendo a face de referência")
    cena = Cena(REFERENCIA)
    nome_ref, nome_ref_uv = jogo.nome_blend(ID_REFERENCIA), jogo.nome_blend(ID_REFERENCIA, uv=True)
    if not nome_ref or not nome_ref_uv:
        raise Erro("O jogo não tem a cabeça do jogador de referência (%s)." % ID_REFERENCIA)
    dp, du = BL.ler(jogo.res(nome_ref)), BL.ler(jogo.res(nome_ref_uv))
    if tuple(len(d) for d in dp) != BL.NVERTS:
        raise Erro("O morph de referência do jogo não tem o formato esperado.")
    V, UV, T, offs = [], [], [], []
    off_lod = np.r_[0, np.cumsum(BL.NVERTS)]
    pos = {}
    for lod, mat, n in SECOES:
        m = cena.malha(mat, lod)
        if m is None or len(m.V) != n:
            raise Erro("A face de referência não é a esperada (%s LOD%d)." % (mat, lod))
        o = pos.get(lod, 0)
        pos[lod] = o + n
        g = int(off_lod[lod]) + o
        offs.append(g)
        V.append(m.V - dp[lod][o:o + n])
        uv = m.uv0.copy()
        if du[lod].shape[1] >= 2:
            uv -= du[lod][o:o + n, :2] * [1.0, -1.0]
        UV.append(uv)
        T.append(m.T.astype(np.int32))
    base = np.concatenate(V)
    n_total = len(base)
    dim = n_total * 3
    sec = {(lod, mat): (offs[i], n, i) for i, (lod, mat, n) in enumerate(SECOES)}
    # conferência: sem o morph, cada globo ocular é uma esfera exata
    o, n, i = sec[(0, "eyes_mat")]
    for lado in (V[i][:, 0] < 0, V[i][:, 0] >= 0):
        c, r = esferas(V[i][lado][None])
        desvio = np.abs(np.linalg.norm(V[i][lado] - c[0], axis=1) - r[0]).max()
        if desvio > 2e-4:
            raise Erro("A face de referência não corresponde ao jogo instalado (desvio de %.2f mm nos olhos). "
                       "Ela precisa ser a exportada do FC 27 atual." % (desvio * 1000))

    # ---- morphs de todas as cabeças masculinas (num arquivo temporário: 1 GB não cabe à vontade na memória)
    prog(0.03, "Procurando as cabeças do jogo")
    nomes = jogo.cabecas_masculinas()
    if len(nomes) < 300:
        raise Erro("Achei só %d cabeças masculinas no jogo: o cache do FET parece incompleto." % len(nomes))
    log("cabeças masculinas: %d" % len(nomes))
    tmp = os.path.join(CACHE, "morphs.tmp")
    X = np.lib.format.open_memmap(tmp, mode="w+", dtype=np.float32, shape=(len(nomes), dim))
    DUV = np.zeros((len(nomes), 2, 198, 2), np.float32)       # LOD0 e LOD1, já no sentido do FBX
    ok = np.zeros(len(nomes), bool)
    by_name = jogo.indice()["res_by_name"]
    for k, nome in enumerate(nomes):
        if k % 100 == 0:
            prog(0.04 + 0.36 * k / len(nomes), "Lendo as cabeças do jogo (%d de %d)" % (k, len(nomes)))
        try:
            d = BL.ler(jogo.res(nome))
            if tuple(len(x) for x in d) != BL.NVERTS or d[0].shape[1] != 3:
                continue
            X[k] = np.concatenate([x.ravel() for x in d])
            nu = nome.replace("/headmorphblend_", "/headmorphblenduv0_")
            if nu in by_name:
                u = BL.ler(jogo.res(nu))
                for l in (0, 1):
                    oo = sec[(l, "eyes_mat")][0] - int(off_lod[l])
                    if u[l].shape[1] >= 2:
                        DUV[k, l] = u[l][oo:oo + 198, :2] * [1.0, -1.0]
            ok[k] = True
        except (Erro, ValueError, struct.error) as ex:
            log("pulei %s: %s" % (nome.rsplit("/", 1)[-1], ex))
    idx = np.nonzero(ok)[0]
    n = len(idx)
    log("lidas %d cabeças em %.0f s" % (n, time.time() - t0))

    # ---- PCA pela matriz de Gram, em blocos
    prog(0.42, "Calculando o modelo estatístico")
    bloco = 400
    blocos = [idx[i:i + bloco] for i in range(0, n, bloco)]
    media = np.zeros(dim)
    for b in blocos:
        media += X[b].astype(np.float64).sum(0)
    media /= n
    med32 = media.astype(np.float32)
    G = np.zeros((n, n))
    for i, bi in enumerate(blocos):
        Xi = X[bi] - med32
        for j, bj in enumerate(blocos[:i + 1]):
            Xj = Xi if j == i else X[bj] - med32
            g = (Xi @ Xj.T).astype(np.float64)
            G[i * bloco:i * bloco + len(bi), j * bloco:j * bloco + len(bj)] = g
            if j != i:
                G[j * bloco:j * bloco + len(bj), i * bloco:i * bloco + len(bi)] = g.T
        prog(0.42 + 0.2 * (i + 1) / len(blocos), "Calculando o modelo estatístico")
    w, U = np.linalg.eigh(G)
    ordem = np.argsort(w)[::-1][:min(K_GUARDADO, n - 1)]
    w, U = w[ordem], U[:, ordem]
    sigma = np.sqrt(w / (n - 1))
    Uw = (U / np.sqrt(w)).astype(np.float32)
    B = np.zeros((dim, len(w)), np.float32)
    for i, bi in enumerate(blocos):
        B += (X[bi] - med32).T @ Uw[i * bloco:i * bloco + len(bi)]
    var = np.cumsum(w) / np.trace(G)
    log("variância explicada: 30=%.3f 60=%.3f 100=%.3f %d=%.3f" % (var[29], var[59], var[99], len(w), var[-1]))
    prog(0.66, "Medindo os olhos das cabeças do jogo")

    # ---- olhos de referência (por LOD e por olho) e aro das pálpebras
    extras = {}
    centros0 = raios0 = None
    for lod in (0, 1, 2):
        o, ne, i = sec[(lod, "eyes_mat")]
        Vb = V[i]
        P = np.concatenate([X[b][:, o * 3:(o + ne) * 3] for b in blocos]).astype(np.float64).reshape(n, ne, 3) + Vb
        dirs = np.zeros((ne, 3))
        uvm = UV[i].copy()
        cs, rs = np.zeros((n, 2, 3)), np.zeros((n, 2))
        for s, lado in enumerate((Vb[:, 0] < 0, Vb[:, 0] >= 0)):
            c, r = esferas(P[:, lado])
            cs[:, s], rs[:, s] = c, r
            d = ((P[:, lado] - c[:, None]) / r[:, None, None]).mean(0)
            dirs[lado] = d / np.linalg.norm(d, axis=1)[:, None]
            if lod < 2:
                F = UV[i][lado][None] + DUV[idx][:, lod][:, lado]
                cu = F[:, :, 0].mean(1)
                F[:, :, 0] -= np.round(cu - np.median(cu))[:, None]     # algumas cabeças usam outro ladrilho em U
                uvm[lado] = np.median(F, 0) * 0.5 + F.mean(0) * 0.5
        if lod == 0:
            centros0, raios0 = cs, rs
        extras["olho_dir_%d" % lod] = dirs.astype(np.float32)
        extras["olho_uv_%d" % lod] = uvm.astype(np.float32)
        extras["olho_raio_rel_%d" % lod] = np.median(rs / raios0, 0).astype(np.float32)
        extras["olho_desloc_%d" % lod] = np.median(cs - centros0, 0).astype(np.float32)
    # aro: laços de borda da pele perto de cada olho (LOD0)
    oh, nh, ih = sec[(0, "head_mat")]
    oe, ne, ie = sec[(0, "eyes_mat")]
    cb = [esferas(V[ie][lado][None])[0][0] for lado in (V[ie][:, 0] < 0, V[ie][:, 0] >= 0)]
    aro_idx, aro_lado = [], []
    for l in lacos_de_borda(T[ih]):
        cl = V[ih][l].mean(0)
        for s in (0, 1):
            if np.linalg.norm(cl - cb[s]) < 0.02 and len(l) < 80:
                aro_idx += list(l)
                aro_lado += [s] * len(l)
    aro_idx, aro_lado = np.array(aro_idx), np.array(aro_lado)
    if len(aro_idx) < 20:
        raise Erro("Não achei a borda das pálpebras na cabeça base.")
    PA = np.concatenate([X[b].reshape(len(b), n_total, 3)[:, oh + aro_idx] for b in blocos]).astype(np.float64) + V[ih][aro_idx]
    razao = np.linalg.norm(PA - centros0[:, aro_lado], axis=2) / raios0[:, aro_lado]
    extras["aro_idx"] = aro_idx.astype(np.int32)
    extras["aro_lado"] = aro_lado.astype(np.int8)
    extras["aro_razao"] = np.median(razao, 0).astype(np.float32)
    extras["aro_razao_min"] = np.percentile(razao, 5, 0).astype(np.float32)
    extras["aro_razao_max"] = np.percentile(razao, 95, 0).astype(np.float32)
    # centro e raio do globo a partir do aro (regressão linear com regularização), por olho
    for s in (0, 1):
        sel = aro_lado == s
        A = PA[:, sel]
        ca = A.mean(1)
        F = np.c_[(A - ca[:, None]).reshape(n, -1), np.ones(n)]
        Y = np.c_[centros0[:, s] - ca, raios0[:, s]]
        lam = 1e-7 * n
        W = np.linalg.solve(F.T @ F + lam * np.eye(F.shape[1]), F.T @ Y)
        extras["aro_reg_%d" % s] = W.astype(np.float32)
        err = F @ W - Y
        log("globo pelo aro (olho %d): erro do centro %.2f mm, do raio %.2f mm" %
            (s, np.sqrt((err[:, :3] ** 2).sum(1).mean()) * 1000, err[:, 3].std() * 1000))
    del X
    try:
        os.remove(tmp)
    except OSError:
        pass

    # ---- peles de base e textura dos olhos
    os.makedirs(PELES, exist_ok=True)
    tons = []
    from .jogo import OLHO_COR, PELE_BASE
    for t in TONS:
        prog(0.72 + 0.2 * (t - 1) / len(TONS), "Lendo as peles de base do jogo")
        nome = PELE_BASE % t
        if not jogo.tem(nome):
            continue
        img = jogo.textura(nome, 1024)
        cv2.imwrite(os.path.join(PELES, "pele_%d.png" % t), (img[:, :, 2::-1] * 255 + 0.5).astype(np.uint8))
        tons.append(t)
    if not tons:
        raise Erro("Não achei as peles de base (skin_base) no jogo.")
    try:                                        # só para as prévias
        img = jogo.textura(OLHO_COR, 512)
        cv2.imwrite(OLHO_PNG, (img[:, :, 2::-1] * 255 + 0.5).astype(np.uint8))
    except Erro as ex:
        log("sem a textura dos olhos para a prévia: %s" % ex)

    prog(0.94, "Gravando o modelo")
    tmpz = ARQUIVO + ".tmp.npz"
    np.savez(tmpz, versao=np.array(VERSAO_MOTOR), nverts=np.array(BL.NVERTS), media=med32, base_pca=B.T.copy(),
             sigma=sigma.astype(np.float32), secoes=np.array(["%d:%s:%d" % s for s in SECOES]),
             **{"V_%d" % i: v.astype(np.float32) for i, v in enumerate(V)},
             **{"UV_%d" % i: u.astype(np.float32) for i, u in enumerate(UV)},
             **{"T_%d" % i: t for i, t in enumerate(T)}, **extras)
    os.replace(tmpz, ARQUIVO)
    with open(META, "w", encoding="utf-8") as f:
        json.dump({"versao": VERSAO_MOTOR, "chave": jogo.chave(), "cabecas": int(n), "tons": tons,
                   "feito": time.strftime("%Y-%m-%d %H:%M:%S"), "segundos": round(time.time() - t0)}, f)
    prog(1.0, "Modelo pronto")
    return meta()


# ---------------------------------------------------------------------------------------------- usar
class Modelo:
    def __init__(self, caminho=None, k=None):
        try:
            d = np.load(caminho or ARQUIVO)
        except (OSError, ValueError) as ex:
            raise Erro("O modelo das cabeças do jogo ainda não foi preparado.") from ex
        self.nverts = [int(x) for x in d["nverts"]]
        self.secoes = []
        off_lod = np.r_[0, np.cumsum(self.nverts)]
        pos = {}
        for i, s in enumerate(d["secoes"]):
            lod, mat, n = str(s).split(":")
            lod, n = int(lod), int(n)
            o = pos.get(lod, 0)
            pos[lod] = o + n
            self.secoes.append(dict(lod=lod, mat=mat, n=n, off=int(off_lod[lod]) + o, V=d["V_%d" % i].astype(np.float64),
                                    UV=d["UV_%d" % i].astype(np.float64), T=d["T_%d" % i].astype(np.int64)))
        self.n_total = int(off_lod[-1])
        self.base = np.zeros((self.n_total, 3))
        for s in self.secoes:
            self.base[s["off"]:s["off"] + s["n"]] = s["V"]
        self.media = d["media"].astype(np.float64).reshape(-1, 3)
        B, sig = d["base_pca"], d["sigma"]
        if k is not None:
            B, sig = B[:k], sig[:k]
        self.B = B.astype(np.float64).reshape(len(B), -1, 3)
        self.sigma = sig.astype(np.float64)
        self.olhos = {lod: dict(dir=d["olho_dir_%d" % lod].astype(np.float64), uv=d["olho_uv_%d" % lod].astype(np.float64),
                                raio_rel=d["olho_raio_rel_%d" % lod].astype(np.float64),
                                desloc=d["olho_desloc_%d" % lod].astype(np.float64)) for lod in (0, 1, 2)}
        self.aro = dict(idx=d["aro_idx"].astype(np.int64), lado=d["aro_lado"].astype(np.int64),
                        razao=d["aro_razao"].astype(np.float64), razao_min=d["aro_razao_min"].astype(np.float64),
                        razao_max=d["aro_razao_max"].astype(np.float64),
                        reg=[d["aro_reg_0"].astype(np.float64), d["aro_reg_1"].astype(np.float64)])

    def secao(self, mat, lod=0):
        for s in self.secoes:
            if s["mat"] == mat and s["lod"] == lod:
                return s
        return None

    def fatia(self, mat, lod=0):
        s = self.secao(mat, lod)
        return slice(s["off"], s["off"] + s["n"])

    def delta(self, c):
        c = np.asarray(c, float)
        return self.media + np.tensordot(c * self.sigma[:len(c)], self.B[:len(c)], axes=1)

    def posicoes(self, c=None):
        return self.base + (self.media if c is None else self.delta(c))

    def projetar_delta(self, D, k=None):
        """coeficientes (em desvios) que melhor aproximam o deslocamento D (n_total x 3)"""
        B = self.B if k is None else self.B[:k]
        c = np.tensordot(B, D - self.media, axes=([1, 2], [0, 1]))
        return c / self.sigma[:len(c)]


def normais(V, T):
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], n)
    return N / np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]


def tons_disponiveis():
    m = meta() or {}
    return [t for t in m.get("tons", []) if os.path.isfile(os.path.join(PELES, "pele_%d.png" % t))]
