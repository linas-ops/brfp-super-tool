"""Minikit: a camisa vista de frente (render da malha do FET com a textura final), 256×256 com fundo transparente, como os
j<tipo>_<teamid>_<variação>.png do jogo."""
import os

import numpy as np
from PIL import Image

import molde as M

LUZ = np.array([0.35, 0.45, 1.0]) / np.linalg.norm([0.35, 0.45, 1.0])


def _normais(V, T):
    n = np.zeros_like(V)
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    for k in range(3):
        np.add.at(n, T[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)


def _amostrar(tex, u, v):
    """Leitura bilinear da textura (u para a direita, v para cima, como na malha)."""
    h, w = tex.shape[:2]
    x = np.clip(u * w - 0.5, 0, w - 1.001)
    y = np.clip((1 - v) * h - 0.5, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    t = tex.astype(np.float32)
    return (t[y0, x0] * (1 - fx) * (1 - fy) + t[y0, x0 + 1] * fx * (1 - fy) + t[y0 + 1, x0] * (1 - fx) * fy
            + t[y0 + 1, x0 + 1] * fx * fy)


def renderizar(tex, lado=256, margem=0.06, super_amostra=2):
    m = M.malha("jersey")
    if m is None:
        raise ValueError("O minikit precisa da malha da camisa (jersey_0_0_0_0_1_0_0_mesh.fbx) em motor/referencia.")
    V, T, UV = m["V"], m["T"], m["UV"]
    N = _normais(V, T)
    S = lado * super_amostra
    xmin, xmax = V[:, 0].min(), V[:, 0].max()
    ymin, ymax = V[:, 1].min(), V[:, 1].max()
    esc = S * (1 - 2 * margem) / max(xmax - xmin, ymax - ymin)
    px = np.stack([(V[:, 0] - (xmin + xmax) / 2) * esc + S / 2, S / 2 - (V[:, 1] - (ymin + ymax) / 2) * esc], 1)
    zbuf = np.full((S, S), -np.inf)
    tri = np.full((S, S), -1, np.int64)
    bar = np.zeros((S, S, 3))
    for i, t in enumerate(T):
        a, b, c = px[t[0]], px[t[1]], px[t[2]]
        x0, x1 = int(max(0, np.floor(min(a[0], b[0], c[0])))), int(min(S - 1, np.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, np.floor(min(a[1], b[1], c[1])))), int(min(S - 1, np.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
        l3 = 1 - l1 - l2
        dentro = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        if not dentro.any():
            continue
        z = l1 * V[t[0], 2] + l2 * V[t[1], 2] + l3 * V[t[2], 2]
        yy, xx = np.nonzero(dentro)
        yy, xx = yy + y0, xx + x0
        zz = z[dentro]
        perto = zz > zbuf[yy, xx]
        yy, xx = yy[perto], xx[perto]
        zbuf[yy, xx] = zz[perto]
        tri[yy, xx] = i
        bar[yy, xx] = np.stack([l1[dentro][perto], l2[dentro][perto], l3[dentro][perto]], 1)
    ys, xs = np.nonzero(tri >= 0)
    ti = T[tri[ys, xs]]
    w = bar[ys, xs]
    uv = (UV[ti] * w[..., None]).sum(1)
    n = (N[ti] * w[..., None]).sum(1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    n *= np.where(n[:, 2:3] < 0, -1, 1)               # lado de dentro (gola) também iluminado
    luz = 0.58 + 0.52 * np.clip(n @ LUZ, 0, 1) - 0.12 * (1 - np.abs(n[:, 2]))
    cor = _amostrar(tex, uv[:, 0], uv[:, 1]) * luz[:, None]
    img = np.zeros((S, S, 4), np.float32)
    img[ys, xs, :3] = np.clip(cor, 0, 255)
    img[ys, xs, 3] = 255
    out = Image.fromarray(img.astype(np.uint8), "RGBA")
    if super_amostra > 1:
        pm = np.asarray(out).astype(np.float32)
        pm[..., :3] *= pm[..., 3:4] / 255.0
        pq = np.asarray(Image.fromarray(pm.astype(np.uint8), "RGBA").resize((lado, lado), Image.LANCZOS)).astype(np.float32)
        a = np.maximum(pq[..., 3:4], 1e-3)
        pq[..., :3] = np.clip(pq[..., :3] * 255.0 / a, 0, 255)
        out = Image.fromarray(pq.astype(np.uint8), "RGBA")
    return out


def desenhar(tex, destino, lado=256):
    img = renderizar(np.asarray(tex), lado)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    img.save(destino)
    return destino
