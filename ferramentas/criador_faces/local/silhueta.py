"""Silhueta do perfil: contorno da cabeça na foto (segmentação) x contorno da cabeça do modelo na mesma câmera.

Só entra o trecho do perfil do rosto (testa baixa, sobrancelha, nariz, boca, queixo), onde a borda da foto é pele do
rosto contra o fundo: cabelo, orelha e pescoço mudam o contorno e ficam de fora.
"""
import cv2
import numpy as np
from scipy import ndimage

from . import raster as RS


def contorno_foto(seg, pontos=None, confiaveis=(3,)):
    """seg: classes por pixel (0 = fundo). -> mapa do pixel de borda mais próximo, normal da borda e se a borda é
    confiável (pele do rosto contra o fundo)"""
    F = (seg != 0).astype(np.uint8)
    n, lab = cv2.connectedComponents(F)
    if n > 2:                                   # só a pessoa do rosto
        alvo = 0
        if pontos is not None:
            cx, cy = np.clip(pontos[:, :2].mean(0).astype(int), 0, [seg.shape[1] - 1, seg.shape[0] - 1])
            alvo = lab[cy, cx]
        if alvo == 0:
            alvo = np.argmax(np.bincount(lab.ravel())[1:]) + 1
        F = (lab == alvo).astype(np.uint8)
    F = cv2.morphologyEx(F, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    borda = F.astype(bool) & ~ndimage.binary_erosion(F.astype(bool))
    _, (iy, ix) = ndimage.distance_transform_edt(~borda, return_indices=True)
    Fs = cv2.GaussianBlur(F.astype(np.float32), (0, 0), 2.0)
    gy, gx = np.gradient(Fs)
    nrm = -np.dstack([gx, gy])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=2), 1e-9)[..., None]
    dentro = np.isin(seg, confiaveis) & F.astype(bool)
    conf = cv2.dilate(dentro.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & borda
    conf &= ~cv2.dilate(np.isin(seg, (1, 4, 5)).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    return dict(iy=iy, ix=ix, nrm=nrm, conf=conf, F=F)


def zona_perfil(P0):
    """pontos da cabeça base no perfil do rosto (testa baixa até o queixo, na frente)"""
    return (P0[:, 2] > 0.035) & (P0[:, 1] > 1.585) & (P0[:, 1] < 1.785)


def pontos_silhueta(Xh, Th, base_h, cam, W, H, passo=2):
    """pontos da malha (triângulo, baricêntricas) que caem na borda da silhueta do modelo nesta câmera"""
    uv, z = cam.projetar(Xh)
    buf, bary = RS.rasterizar(uv, z, Th, W, H)
    m = buf >= 0
    ys, xs = np.nonzero(m & ~ndimage.binary_erosion(m))
    ys, xs = ys[::passo], xs[::passo]
    tri, b = buf[ys, xs], bary[ys, xs]
    ok = zona_perfil((base_h[Th[tri]] * b[:, :, None]).sum(1))
    return tri[ok], b[ok]


def alvos(cf, uv_modelo, dist_max):
    """para cada ponto projetado do modelo: alvo na borda da foto, normal da borda, e se vale"""
    H, W = cf["F"].shape
    x = np.clip(np.round(uv_modelo[:, 0]).astype(int), 0, W - 1)
    y = np.clip(np.round(uv_modelo[:, 1]).astype(int), 0, H - 1)
    ty, tx = cf["iy"][y, x], cf["ix"][y, x]
    alvo = np.c_[tx, ty].astype(float)
    d = np.linalg.norm(alvo - uv_modelo, axis=1)
    return alvo, cf["nrm"][ty, tx], cf["conf"][ty, tx] & (d < dist_max)
