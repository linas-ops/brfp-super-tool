"""Câmera e rasterizador simples (numpy + OpenCV): buffer de triângulos por pintor com descarte das faces de trás.

Mundo do jogo: metros, Y para cima, Z para a frente da face. A câmera olha para um ponto de referência c0 (o centro
da cabeça): Y = R (X - c0); u = s Yx / (1 - k Yz) + tx; v = -s Yy / (1 - k Yz) + ty; profundidade = -Yz.
k = 1 / distância da câmera ao centro da cabeça, em 1/m (k = 0 é a câmera ortográfica); s = pixels por metro no
plano que passa por c0. O observador fica em +Z do espaço da câmera.
"""
import cv2
import numpy as np


def rot(yaw=0.0, pitch=0.0, roll=0.0):
    """rotação do modelo para o espaço da câmera (graus). yaw > 0 vira a face para a direita da imagem."""
    a, b, c = np.radians([yaw, pitch, roll])
    Ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    Rz = np.array([[np.cos(c), -np.sin(c), 0], [np.sin(c), np.cos(c), 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


class Camera:
    def __init__(self, R, s, t, k=0.0, c0=(0.0, 0.0, 0.0)):
        self.R = np.asarray(R, float)
        self.s = float(s)
        self.t = np.asarray(t, float)
        self.k = float(k)
        self.c0 = np.asarray(c0, float)

    def projetar(self, X):
        Y = (X - self.c0) @ self.R.T
        den = np.maximum(1.0 - self.k * Y[:, 2], 0.05)
        return np.c_[self.s * Y[:, 0] / den + self.t[0], -self.s * Y[:, 1] / den + self.t[1]], -Y[:, 2]

    def direcao_vista(self):
        """direção, no mundo, do centro da cabeça para o observador"""
        return self.R.T @ np.array([0.0, 0.0, 1.0])

    def yaw(self):
        return float(np.degrees(np.arctan2(self.R[0, 2], self.R[2, 2])))

    def distancia(self):
        return 1.0 / self.k if self.k > 1e-6 else float("inf")

    def dados(self):
        return dict(R=self.R.tolist(), s=self.s, t=self.t.tolist(), k=self.k, c0=self.c0.tolist())

    @staticmethod
    def enquadrar(X, R, W, H, margem=0.08, k=0.0, c0=None):
        c0 = X.mean(0) if c0 is None else np.asarray(c0, float)
        cam = Camera(R, 1.0, (0.0, 0.0), k, c0)
        uv, _ = cam.projetar(X)
        lo, hi = uv.min(0), uv.max(0)
        s = min(W, H) * (1 - 2 * margem) / max(hi - lo)
        c = (lo + hi) / 2 * s
        return Camera(R, s, (W / 2 - c[0], H / 2 - c[1]), k, c0)


def rasterizar(uv, z, T, W, H, cull=True):
    """-> (id do triângulo por pixel, -1 no fundo; baricêntricas por pixel)"""
    P = uv[T]
    area = (P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 1] - P[:, 0, 1]) - (P[:, 2, 0] - P[:, 0, 0]) * (P[:, 1, 1] - P[:, 0, 1])
    vis = np.abs(area) > 1e-12
    if cull:
        vis &= area < 0                         # anti-horário no mundo vira horário com v para baixo
    ordem = np.argsort(-z[T].max(1))
    ordem = ordem[vis[ordem]]
    buf = np.full((H, W), -1, np.int32)
    Pi = np.round(np.clip(P, -1e6, 1e6) * 16).astype(np.int32)
    for i in ordem:
        cv2.fillConvexPoly(buf, Pi[i], int(i), lineType=cv2.LINE_8, shift=4)
    ys, xs = np.nonzero(buf >= 0)
    tri = buf[ys, xs]
    A, B, C = P[tri, 0], P[tri, 1], P[tri, 2]
    v0, v1, v2 = B - A, C - A, np.c_[xs + 0.0, ys + 0.0] - A
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    den[np.abs(den) < 1e-18] = 1e-18
    b1 = (d11 * d20 - d01 * d21) / den
    b2 = (d00 * d21 - d01 * d20) / den
    bb = np.clip(np.c_[1 - b1 - b2, b1, b2], 0, 1)
    bb /= np.maximum(bb.sum(1), 1e-12)[:, None]
    bary = np.zeros((H, W, 3))
    bary[ys, xs] = bb
    return buf, bary


def interpolar(buf, bary, T, atributo):
    """atributo por vértice -> imagem (pixels de fundo = 0)"""
    a = np.asarray(atributo, float)
    out = np.zeros(buf.shape + a.shape[1:])
    m = buf >= 0
    tri = T[buf[m]]
    out[m] = (a[tri] * bary[m][..., None]).sum(1) if a.ndim > 1 else (a[tri] * bary[m]).sum(1)
    return out


def amostrar(img, uv, repetir=False):
    """amostra bilinear da textura (H x W x C, float) em coordenadas UV (v para cima)"""
    h, w = img.shape[:2]
    if repetir:
        uv = uv - np.floor(uv)
    mx = (uv[..., 0] * w - 0.5).astype(np.float32)
    my = ((1 - uv[..., 1]) * h - 0.5).astype(np.float32)
    return cv2.remap(img.astype(np.float32), mx, my, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_WRAP if repetir else cv2.BORDER_REFLECT)


def amostrar_px(img, xs, ys):
    """amostra bilinear em pontos soltos (o remap do OpenCV exige mapas menores que 32767)"""
    n = len(xs)
    lado = 1024
    lin = (n + lado - 1) // lado
    mx = np.zeros(lin * lado, np.float32)
    my = np.zeros(lin * lado, np.float32)
    mx[:n], my[:n] = xs, ys
    out = cv2.remap(img.astype(np.float32), mx.reshape(lin, lado), my.reshape(lin, lado), cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE)
    return out.reshape(-1, img.shape[2])[:n]
