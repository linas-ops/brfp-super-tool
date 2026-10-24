"""Conversão sRGB <-> CIELAB (D65) e k-means simples, em numpy."""
import numpy as np

_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]],
              np.float32)
_MI = np.linalg.inv(_M).astype(np.float32)
_BRANCO = np.array([0.95047, 1.0, 1.08883], np.float32)
_D = 6.0 / 29.0


def rgb_lab(rgb):
    """rgb uint8 ou float 0..255 (..., 3) -> Lab float32."""
    c = np.asarray(rgb, np.float32) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = (c @ _M.T) / _BRANCO
    f = np.where(xyz > _D ** 3, np.cbrt(xyz), xyz / (3 * _D * _D) + 4.0 / 29.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1).astype(np.float32)


def lab_rgb(lab):
    """Lab (..., 3) -> rgb float 0..255 (sem arredondar)."""
    lab = np.asarray(lab, np.float32)
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f > _D, f ** 3, 3 * _D * _D * (f - 4.0 / 29.0)) * _BRANCO
    c = np.clip(xyz @ _MI.T, 0.0, 1.0)
    c = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return np.clip(c * 255.0, 0, 255)


def hex_rgb(h):
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def rgb_hex(c):
    c = np.clip(np.round(np.asarray(c, np.float32)), 0, 255).astype(int)
    return "#%02x%02x%02x" % tuple(c[:3])


def hex_lab(h):
    return rgb_lab(hex_rgb(h)[None])[0]


def kmeans(x, k, iters=18, semente=0):
    """x (n, d) float32 -> (centros (k, d), rótulos (n,)). Inicialização k-means++ determinística."""
    rng = np.random.default_rng(semente)
    n = len(x)
    k = max(1, min(k, n))
    centros = [x[rng.integers(n)]]
    d2 = ((x - centros[0]) ** 2).sum(1)
    for _ in range(1, k):
        if float(d2.sum()) <= 1e-9:          # todos iguais aos centros já escolhidos
            break
        p = d2 / d2.sum()
        centros.append(x[rng.choice(n, p=p)])
        d2 = np.minimum(d2, ((x - centros[-1]) ** 2).sum(1))
    c = np.array(centros, np.float32)
    k = len(c)
    rot = np.zeros(n, np.int64)
    for _ in range(iters):
        dist = ((x[:, None, :] - c[None]) ** 2).sum(-1)
        rot = dist.argmin(1)
        for j in range(k):
            m = rot == j
            if m.any():
                c[j] = x[m].mean(0)
    return c, rot


def agrupar(lab, k=6, juntar=10.0, minimo=0.004):
    """Paleta de uma amostra Lab (n, 3): k-means, junta centros a menos de `juntar` ΔE e some com grupos < `minimo`.
    Devolve (centros (m, 3), frações (m,)) do maior para o menor."""
    c, rot = kmeans(lab, k)
    pesos = np.bincount(rot, minlength=len(c)).astype(np.float64)
    c = list(c)
    pesos = list(pesos)
    mudou = True
    while mudou and len(c) > 1:
        mudou = False
        melhor = None
        for i in range(len(c)):
            for j in range(i + 1, len(c)):
                dd = float(np.linalg.norm(c[i] - c[j]))
                if dd < juntar and (melhor is None or dd < melhor[0]):
                    melhor = (dd, i, j)
        tot = sum(pesos)
        if melhor is None:
            pequenos = [i for i in range(len(c)) if pesos[i] / tot < minimo]
            if pequenos:
                i = pequenos[0]
                j = min((jj for jj in range(len(c)) if jj != i), key=lambda jj: np.linalg.norm(c[i] - c[jj]))
                melhor = (0, min(i, j), max(i, j))
        if melhor is not None:
            _, i, j = melhor
            w = pesos[i] + pesos[j]
            c[i] = (c[i] * pesos[i] + c[j] * pesos[j]) / max(w, 1e-9)
            pesos[i] = w
            del c[j], pesos[j]
            mudou = True
    ordem = np.argsort(pesos)[::-1]
    c = np.array([c[i] for i in ordem], np.float32)
    p = np.array([pesos[i] for i in ordem], np.float64)
    return c, p / p.sum()
