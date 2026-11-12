"""Ajuste da cabeça (coeficientes do modelo estatístico) e das câmeras às fotos.

Câmera de cada foto: rotação, escala, translação e o inverso da distância (perspectiva: uma foto de perto mostra o
nariz maior e as laterais menores; sem isso o rosto sai estreito). Pontos do modelo: combinação linear dos
coeficientes. Custo: erro de reprojeção dos pontos do MediaPipe (com a tabela ponto -> cabeça base por ângulo, porque
o MediaPipe desliza os pontos quando a cabeça gira) + distância da silhueta do perfil à borda da cabeça na foto +
prior gaussiano dos coeficientes e da distância.
"""
import hashlib
import os

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from . import DADOS, Erro
from . import modelo as MD
from . import pontos as PT
from . import raster as RS
from . import silhueta as SL

RUIDO_M = 0.002          # ruído típico de um ponto do MediaPipe, em metros na cabeça
RUIDO_SIL_M = 0.0015     # ruído da borda da silhueta
K_MAX = 2.5              # câmera a 40 cm


def assinatura_malha(m):
    h, e = m.secao("head_mat"), m.secao("eyes_mat")
    return hashlib.sha1(np.ascontiguousarray(np.r_[h["T"], e["T"] + h["n"]], np.int32).tobytes()).hexdigest()[:16]


class Pontos:
    """os 478 pontos como função linear dos coeficientes (tabela única e tabelas por ângulo)"""

    def __init__(self, modelo, k):
        cal = np.load(os.path.join(DADOS, "pontos_basehead.npz"))
        yw = np.load(os.path.join(DADOS, "pontos_basehead_yaw.npz"))
        if str(cal["malha"]) != assinatura_malha(modelo):
            raise Erro("A cabeça base lida do jogo não é a que o criador conhece (o jogo mudou a malha das cabeças).")
        self.m, self.k = modelo, k
        h, e = modelo.secao("head_mat"), modelo.secao("eyes_mat")
        self.T = np.r_[h["T"], e["T"] + h["n"]]
        self.Th = h["T"]
        self.nh = h["n"] + e["n"]
        self.tri, self.bary = cal["tri"], cal["bary"]
        self.L0, self.BL = self.operador(self.T[self.tri], self.bary)
        self.yaws = yw["yaws"].astype(float)
        self.ops_yaw = []
        for b in range(len(self.yaws)):
            L0, BL = self.operador(self.T[yw["tri"][b]], yw["bary"][b])
            val = yw["valido"][b].astype(float)
            val[PT.N_ROSTO:] = 0            # íris: dependem de para onde a pessoa olha
            self.ops_yaw.append((L0, BL, val, np.maximum(yw["disp_mm"][b], 1.0) / 1000.0))

    def operador(self, idx, w):
        """pontos de superfície (vértices idx n x 3, pesos w n x 3) -> (posição média n x 3, base k x n x 3)"""
        base = self.m.base + self.m.media
        L0 = (base[idx] * w[:, :, None]).sum(1)
        Bk = self.m.B[:self.k] * self.m.sigma[:self.k, None, None]
        return L0, (Bk[:, idx] * w[None, :, :, None]).sum(2)

    def posicoes(self, c):
        return self.L0 + np.tensordot(c, self.BL, axes=1)

    def para_yaw(self, yw):
        """operador interpolado entre as duas faixas de ângulo vizinhas -> (L0, BL, válido, ruído em m)"""
        ys = self.yaws
        yw = float(np.clip(yw, ys[0], ys[-1]))
        j = int(np.clip(np.searchsorted(ys, yw) - 1, 0, len(ys) - 2))
        a = (yw - ys[j]) / (ys[j + 1] - ys[j])
        A, B = self.ops_yaw[j], self.ops_yaw[j + 1]
        return (1 - a) * A[0] + a * B[0], (1 - a) * A[1] + a * B[1], A[2] * B[2], (1 - a) * A[3] + a * B[3]

    def normais(self, c):
        X = self.m.posicoes(c)[:self.nh]
        N = MD.normais(X, self.T)
        n = (N[self.T[self.tri]] * self.bary[:, :, None]).sum(1)
        return n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]


def camera_afim(Y, u, w, c0):
    """câmera ortográfica escalada que leva Y (n x 3) em u (n x 2, pixels, y para baixo)"""
    Y = Y - c0
    up = np.c_[u[:, 0], -u[:, 1]]
    sw = w.sum()
    my, mu = (Y * w[:, None]).sum(0) / sw, (up * w[:, None]).sum(0) / sw
    Yc, Uc = (Y - my) * np.sqrt(w)[:, None], (up - mu) * np.sqrt(w)[:, None]
    A = np.linalg.lstsq(Yc, Uc, rcond=None)[0].T
    U, S, Vt = np.linalg.svd(A, full_matrices=False)
    s = S.mean()
    R2 = U @ Vt
    R = np.r_[R2, np.cross(R2[0], R2[1])[None]]
    if np.linalg.det(R) < 0:
        R[2] *= -1
    t = mu - s * (R2 @ my)
    return RS.Camera(R, s, (t[0], -t[1]), 0.0, c0)


def visibilidade(n, R):
    return np.clip(((n @ R.T)[:, 2] - 0.2) / 0.35, 0, 1)


def _resolver(P, c, cams, fotos_pontos, pesos, peso_vista, prior, sil, ops, livre_k, k0, sigma_k):
    """mínimos quadrados em (coeficientes, câmeras). sil: lista de (vista, L0, BL, alvo, normal, peso).
    ops: por vista, (L0, BL, ruído em m) dos pontos (tabela por ângulo) ou None (tabela única)"""
    k, nv = P.k, len(cams)
    c0 = cams[0].c0

    def pack(c, cams):
        x = [c]
        for cam in cams:
            x += [Rotation.from_matrix(cam.R).as_rotvec(), [np.log(cam.s)], cam.t, [cam.k]]
        return np.concatenate(x)

    def unpack(x):
        cs = []
        for i in range(nv):
            o = k + 7 * i
            kk = float(np.clip(x[o + 6], 0.0, K_MAX)) if livre_k else cams[i].k
            cs.append(RS.Camera(Rotation.from_rotvec(x[o:o + 3]).as_matrix(), np.exp(x[o + 3]), x[o + 4:o + 6], kk, c0))
        return x[:k], cs

    def residuos(x):
        c, cs = unpack(x)
        L = P.posicoes(c)
        out = []
        for i, (cam, p, w, pv) in enumerate(zip(cs, fotos_pontos, pesos, peso_vista)):
            if ops is not None and ops[i] is not None:
                L0, BL, ruido = ops[i]
                uv, _ = cam.projetar(L0 + np.tensordot(c, BL, axes=1))
            else:
                ruido = RUIDO_M
                uv, _ = cam.projetar(L)
            out.append(((uv - p[:, :2]) * (np.sqrt(w * pv) / (cam.s * ruido))[:, None]).ravel())
        for (i, L0, BL, alvo, nrm, ps) in sil:
            cam = cs[i]
            uv, _ = cam.projetar(L0 + np.tensordot(c, BL, axes=1))
            out.append(((uv - alvo) * nrm).sum(1) * np.sqrt(ps) / (cam.s * RUIDO_SIL_M))
        out.append(c * np.sqrt(prior))
        if livre_k:
            out.append(np.array([(x[k + 7 * i + 6] - k0) / sigma_k for i in range(nv)]))
        return np.concatenate(out)

    res = least_squares(residuos, pack(c, cams), loss="soft_l1", f_scale=2.0, max_nfev=200, x_scale="jac")
    return unpack(res.x)


def _erros(P, c, cams, fotos_pontos, pesos, ops):
    erro = []
    for i, (cam, p, w) in enumerate(zip(cams, fotos_pontos, pesos)):
        L = P.posicoes(c) if ops is None or ops[i] is None else ops[i][0] + np.tensordot(c, ops[i][1], axes=1)
        uv, _ = cam.projetar(L)
        d = np.linalg.norm(uv - p[:, :2], axis=1)
        erro.append(float((d * w).sum() / max(w.sum(), 1e-9) / cam.s * 1000))
    return erro


def ajustar(fotos_pontos, modelo, k=100, prior=4.0, peso_vista=None, contornos=None, tamanhos=None, peso_sil=2.0,
            iteracoes=4, iter_sil=6, perspectiva=True, k0=0.5, sigma_k=0.6, log=print, prog=lambda f: None):
    """fotos_pontos: lista de arrays 478 x 3 (pixels), a primeira é a de frente. contornos: por foto, saída de
    silhueta.contorno_foto ou None. -> dict(c, cameras, erros)"""
    P = Pontos(modelo, k)
    nv = len(fotos_pontos)
    peso_vista = np.ones(nv) if peso_vista is None else np.asarray(peso_vista, float)
    h = modelo.secao("head_mat")
    base_h = modelo.base[h["off"]:h["off"] + h["n"]]
    c0 = (base_h + modelo.media[h["off"]:h["off"] + h["n"]]).mean(0)
    c = np.zeros(k)
    L, n = P.posicoes(c), P.normais(c)
    cams = []
    for p in fotos_pontos:
        cam = camera_afim(L, p[:, :2], np.ones(len(L)), c0)
        cams.append(camera_afim(L, p[:, :2], visibilidade(n, cam.R) + 1e-3, c0))
    usar_sil = contornos is not None and any(cf is not None for cf in contornos)
    total = iteracoes + (iter_sil if usar_sil else 0)
    ops, pesos, n_sil = None, None, []
    for it in range(total):
        n = P.normais(c)
        pesos = [visibilidade(n, cam.R) for cam in cams]
        for w in pesos:
            w[PT.N_ROSTO:] = 0
        ops = None
        if it >= 1:
            ops = []
            for i, cam in enumerate(cams):
                L0, BL, val, ruido = P.para_yaw(cam.yaw())
                ops.append((L0, BL, ruido))
                pesos[i] = val
        sil, n_sil = [], []
        if usar_sil and it >= iteracoes:
            Xh = modelo.posicoes(c)[h["off"]:h["off"] + h["n"]]
            for i, (cf, cam) in enumerate(zip(contornos, cams)):
                if cf is None or abs(cam.yaw()) < 30:
                    continue
                W, H = tamanhos[i]
                tri, b = SL.pontos_silhueta(Xh, P.Th, base_h, cam, W, H)
                if len(tri) == 0:
                    continue
                L0, BL = P.operador(P.Th[tri], b)
                uv, _ = cam.projetar(L0 + np.tensordot(c, BL, axes=1))
                alvo, nrm, vale = SL.alvos(cf, uv, dist_max=0.012 * cam.s)
                if vale.sum() < 10:
                    continue
                ps = peso_sil * 20.0 / max(vale.sum(), 20)       # o perfil inteiro vale ~20 pontos
                sil.append((i, L0[vale], BL[:, vale], alvo[vale], nrm[vale], ps))
                n_sil.append(int(vale.sum()))
        c, cams = _resolver(P, c, cams, fotos_pontos, pesos, peso_vista, prior, sil, ops,
                            livre_k=perspectiva and it >= 2, k0=k0, sigma_k=sigma_k)
        log("iteração %d: erro por foto (mm) %s  yaw %s  dist (m) %s  |c| %.2f  silhueta %s" % (
            it + 1, " ".join("%.2f" % e for e in _erros(P, c, cams, fotos_pontos, pesos, ops)),
            " ".join("%.0f" % cam.yaw() for cam in cams),
            " ".join("%.1f" % cam.distancia() for cam in cams), np.linalg.norm(c), n_sil))
        prog((it + 1) / total)
    return dict(c=c, cameras=cams, erros=_erros(P, c, cams, fotos_pontos, pesos, ops), pesos=pesos)
