"""Textura da face (layout UV da cabeça do FC 27), careca: a pele vem das fotos já alinhadas à cabeça ajustada e o
que as fotos não mostram (couro cabeludo, nuca, pálpebras fechadas, o que o cabelo cobre) vem de uma pele de base do
próprio jogo, com a cor acertada pela pele das fotos. Barba e sobrancelhas ficam: o segmentador as marca como pele.
"""
import os

import cv2
import numpy as np

from . import modelo as MD
from . import pontos as PT
from . import raster as RS


def raster_uv(V, T, UV, N):
    """para cada texel: posição 3D e normal (e máscara de cobertura)"""
    uv = np.c_[UV[:, 0] * N, (1 - UV[:, 1]) * N]
    buf, bary = RS.rasterizar(uv, np.zeros(len(uv)), T, N, N, cull=False)
    m = buf >= 0
    P = RS.interpolar(buf, bary, T, V)
    Nn = RS.interpolar(buf, bary, T, MD.normais(V, T))
    Nn /= np.maximum(np.linalg.norm(Nn, axis=-1), 1e-12)[..., None]
    return m, P, Nn


def mascara_aberturas(p, W, H, dilatar=0.25):
    """aberturas dos olhos e da boca na foto (polígonos dos pontos do MediaPipe, um pouco dilatados)"""
    mask = np.zeros((H, W), np.uint8)
    for idx, dil in ((PT.OLHO_DIREITO, dilatar), (PT.OLHO_ESQUERDO, dilatar), (PT.LABIOS_DENTRO, 0.0)):
        pts = p[list(idx), :2]
        c = pts.mean(0)
        pts = c + (pts - c) * (1 + dil)
        cv2.fillConvexPoly(mask, cv2.convexHull(pts.astype(np.float32)).astype(np.int32), 1)
    return mask.astype(bool)


def peso_segmentacao(seg, s):
    """peso por pixel da foto: 1 na pele, caindo a 0 perto do cabelo (longe o bastante para não levar fios nem a
    sombra deles) e perto do fundo, da roupa e dos acessórios. s = pixels por metro."""
    pele = np.isin(seg, (2, 3)).astype(np.uint8)
    cabelo = (seg == 1).astype(np.uint8)
    cabelo = cv2.morphologyEx(cabelo, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))      # entre os cachos
    d_fora = cv2.distanceTransform(pele, cv2.DIST_L2, 5)                  # distância ao que não é pele
    d_cab = cv2.distanceTransform(1 - cabelo, cv2.DIST_L2, 5)            # distância ao cabelo
    w = np.clip((d_fora - 0.002 * s) / (0.004 * s), 0, 1)
    return w * np.clip((d_cab - 0.006 * s) / (0.014 * s), 0, 1)


def projetar(modelo, X_total, fotos, cameras, pontos_fotos, segs, N=1024, frente=0):
    """-> (cor N x N x 3, peso N x N, cobertura N x N)"""
    h = modelo.secao("head_mat")
    V = X_total[h["off"]:h["off"] + h["n"]]
    T = h["T"]
    cob, P, Nn = raster_uv(V, T, h["UV"], N)
    medidas = []
    for i, (img, cam, p, seg) in enumerate(zip(fotos, cameras, pontos_fotos, segs)):
        H, W = img.shape[:2]
        uv, z = cam.projetar(V)
        buf, bary = RS.rasterizar(uv, z, T, W, H)
        zbuf = RS.interpolar(buf, bary, T, z)
        zbuf[buf < 0] = np.inf
        q, zq = cam.projetar(P[cob])
        xi = np.clip(np.round(q[:, 0]).astype(int), 0, W - 1)
        yi = np.clip(np.round(q[:, 1]).astype(int), 0, H - 1)
        dentro = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
        visivel = dentro & (zq <= zbuf[yi, xi] + 0.004)
        cosv = Nn[cob] @ cam.direcao_vista()
        w = np.clip((cosv - 0.15) / 0.6, 0, 1) ** 2 * visivel
        if p is not None:
            w[mascara_aberturas(p, W, H)[yi, xi]] = 0
        sil = (buf >= 0).astype(np.uint8)                      # borda da cabeça na foto: não pegar o fundo
        w *= np.clip(cv2.distanceTransform(sil, cv2.DIST_L2, 5)[yi, xi] / (0.01 * cam.s), 0, 1)
        if seg is not None:
            w *= peso_segmentacao(seg, cam.s)[yi, xi]
        if i != frente:
            w *= 0.6
        Ci, Wi = np.zeros((N, N, 3)), np.zeros((N, N))
        Ci[cob], Wi[cob] = RS.amostrar_px(img, q[:, 0], q[:, 1]), w
        medidas.append((Ci, Wi))
    # iguala a cor de cada foto lateral com a da frente onde as duas enxergam bem (ganho suave: corrige a luz
    # diferente entre as fotos sem apagar detalhe)
    Cf, Wf = medidas[frente]
    for i, (Ci, Wi) in enumerate(medidas):
        if i == frente:
            continue
        both = ((Wf > 0.2) & (Wi > 0.2)).astype(np.float32)
        if both.sum() > 500:
            mi = Ci[both > 0].mean(0)
            g0 = (Cf[both > 0].mean(0) + 1e-3) / (mi + 1e-3)
            sig = N / 16
            bf = cv2.GaussianBlur((Cf * both[..., None]).astype(np.float32), (0, 0), sig)
            bi = cv2.GaussianBlur((Ci * both[..., None]).astype(np.float32), (0, 0), sig)
            bm = cv2.GaussianBlur(both, (0, 0), sig)[..., None]
            ganho = (bf + 0.05 * g0 * mi) / (bi + 0.05 * mi + 1e-6)
            ganho = np.where(bm > 0.02, ganho, g0)
            ganho = cv2.GaussianBlur(np.clip(ganho, 0.3, 3.0).astype(np.float32), (0, 0), sig / 2)
            medidas[i] = (np.clip(Ci * ganho, 0, 1), Wi)
    # prioridade: cada texel vem da primeira foto (a de frente primeiro) que o enxerga bem; as outras completam
    soma, pesos, resta = np.zeros((N, N, 3)), np.zeros((N, N)), np.ones((N, N))
    for Ci, Wi in medidas:
        Wp = resta * np.clip(Wi / 0.35, 0, 1)
        Wp = cv2.GaussianBlur(Wp.astype(np.float32), (0, 0), N / 512) * (Wi > 0)
        soma += Ci * Wp[..., None]
        pesos += Wp
        resta = resta * (1 - np.clip(Wi / 0.35, 0, 1))
    return soma / np.maximum(pesos, 1e-9)[..., None], pesos, cob


def ler_pele(tom):
    img = cv2.imread(os.path.join(MD.PELES, "pele_%d.png" % tom), cv2.IMREAD_COLOR)
    return None if img is None else img[:, :, ::-1].astype(np.float32) / 255.0


def interior_da_boca(pele):
    """máscara do interior da boca e dos dentes na pele de base (faixa de baixo da textura): fica como no jogo"""
    N = pele.shape[0]
    r, g, b = pele[..., 0], pele[..., 1], pele[..., 2]
    ys = np.arange(N)[:, None] / N
    m = ((r - g > 0.16) & (g < 0.42) & (ys > 0.80)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))       # os dentes ficam dentro
    m = cv2.dilate(m, np.ones((7, 7), np.uint8))
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), 2.0)


def pele_clara(cor, pesos, limiar=0.3):
    """texels que as fotos mostram bem e que são pele lisa (sem barba, sobrancelha ou sombra forte): a cor da pele de
    base é acertada por eles"""
    ok = pesos > limiar
    if ok.sum() < 500:
        return ok
    lum = cor @ np.array([0.299, 0.587, 0.114])
    ref = np.percentile(lum[ok], 65)            # a barba puxa a mediana para baixo; a testa clara tem de contar
    return ok & (lum > 0.72 * ref)


def escolher_tom(cor, pesos, tons):
    """pele de base com a cor mais próxima da pele das fotos (no que as fotos mostram bem)"""
    ok = pele_clara(cor, pesos, 0.5)
    if ok.sum() < 1000:
        return tons[len(tons) // 2]
    alvo = cor[ok].mean(0)
    melhor, dist = tons[0], 1e9
    for t in tons:
        p = ler_pele(t)
        if p is None:
            continue
        p = cv2.resize(p, (cor.shape[1], cor.shape[0]), interpolation=cv2.INTER_AREA)
        d = float(np.linalg.norm(p[ok].mean(0) / max(p[ok].mean(), 1e-6) - alvo / max(alvo.mean(), 1e-6)))
        if d < dist:
            melhor, dist = t, d
    return melhor


def completar(cor, pesos, pele):
    """onde as fotos não mostram pele, usa a pele de base com a cor corrigida por um mapa de ganho suave (razão entre
    a cor das fotos e a da pele de base nos trechos de pele lisa, espalhada por convolução normalizada), e passa de
    uma para a outra numa faixa larga, para não deixar emenda"""
    N = cor.shape[0]
    d = cv2.resize(pele.astype(np.float32), (N, N), interpolation=cv2.INTER_AREA)
    ok = pele_clara(cor, pesos).astype(np.float32)
    n_ok = max(ok.sum(), 1)
    glob_c = (cor * ok[..., None]).sum((0, 1)) / n_ok
    glob_d = (d * ok[..., None]).sum((0, 1)) / n_ok
    ganho = None
    # da cor geral para a cor da pele mais próxima: o couro cabeludo continua a testa, a nuca continua o pescoço
    for sig, eps in ((N / 6, 0.002), (N / 14, 0.01), (N / 30, 0.03)):
        bc = cv2.GaussianBlur((cor * ok[..., None]).astype(np.float32), (0, 0), sig)
        bd = cv2.GaussianBlur((d * ok[..., None]).astype(np.float32), (0, 0), sig)
        g = (bc + eps * glob_c) / (bd + eps * glob_d + 1e-6)
        if ganho is None:
            ganho = g
        else:
            conf = np.clip(cv2.GaussianBlur(ok, (0, 0), sig) / 0.08, 0, 1)[..., None]
            ganho = ganho * (1 - conf) + g * conf
    ganho = cv2.GaussianBlur(np.clip(ganho, 0.2, 5.0).astype(np.float32), (0, 0), N / 80)
    boca = interior_da_boca(d)[..., None]
    d_aj = np.clip(d * ganho, 0, 1) * (1 - boca) + d * boca
    t = np.clip((pesos - 0.35) / 0.5, 0, 1).astype(np.float32)
    alfa = t * t * (3 - 2 * t)
    alfa = cv2.erode(alfa, np.ones((9, 9), np.uint8))
    alfa = cv2.GaussianBlur(alfa, (0, 0), N / 90)[..., None] * (1 - boca)
    # onde nenhuma foto enxerga, "cor" não vale nada (é preto): a mistura borrada não pode puxar esse preto
    tem = np.clip(pesos / 0.05, 0, 1)[..., None]
    cor = cor * tem + d_aj * (1 - tem)
    return np.clip(cor * alfa + d_aj * (1 - alfa), 0, 1)


def gerar(modelo, X_total, fotos, cameras, pontos_fotos, segs, N=1024, tom=None):
    """-> (textura N x N x 3 float, tom usado, fração da textura que veio das fotos)"""
    cor, pesos, cob = projetar(modelo, X_total, fotos, cameras, pontos_fotos, segs, N)
    tons = MD.tons_disponiveis()
    tom = tom if tom in tons else escolher_tom(cor, pesos, tons)
    tex = completar(cor, pesos, ler_pele(tom))
    return tex, tom, float((pesos > 0.25).sum() / max(cob.sum(), 1))
