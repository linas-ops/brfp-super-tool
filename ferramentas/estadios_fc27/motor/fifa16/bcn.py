"""Vectorised BC1 (DXT1) / BC3 (DXT5) decode and a simple encoder, for completing mip chains.

Only the mips FIFA 16 does not ship are encoded here (the shipped ones are reused byte for byte).
The encoder is a bounding-box range fit per 4x4 block (min/max along the colour axis), which is
what DirectXTex's fast path does for small mips; quality matters little at those sizes.
"""
import numpy as np


def _565(c):
    r = ((c >> 11) & 31).astype(np.float32) * (255 / 31)
    g = ((c >> 5) & 63).astype(np.float32) * (255 / 63)
    b = (c & 31).astype(np.float32) * (255 / 31)
    return np.stack([r, g, b], -1)


def _blocks_to_image(px, w, h):
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    img = px.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img[:h, :w]


def decode_bc1_colour(blk, punch=True):
    """blk: (n, 8) uint8 colour blocks -> (n, 16, 4) float RGBA."""
    c0 = blk[:, 0].astype(np.uint32) | (blk[:, 1].astype(np.uint32) << 8)
    c1 = blk[:, 2].astype(np.uint32) | (blk[:, 3].astype(np.uint32) << 8)
    bits = blk[:, 4].astype(np.uint32) | (blk[:, 5].astype(np.uint32) << 8) | (blk[:, 6].astype(np.uint32) << 16) | (blk[:, 7].astype(np.uint32) << 24)
    p0, p1 = _565(c0), _565(c1)
    four = (c0 > c1) | (not punch)
    p2 = np.where(four[:, None], (2 * p0 + p1) / 3, (p0 + p1) / 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) / 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)  # n,4,3
    alpha = np.ones((len(blk), 4), np.float32) * 255
    alpha[:, 3] = np.where(four, 255, 0)
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    rgb = np.take_along_axis(pal, idx[:, :, None].astype(np.int64), 1)
    a = np.take_along_axis(alpha, idx.astype(np.int64), 1)
    return np.concatenate([rgb, a[:, :, None]], -1)


def decode_bc3_alpha(blk):
    a0 = blk[:, 0].astype(np.float32)
    a1 = blk[:, 1].astype(np.float32)
    bits = np.zeros(len(blk), np.uint64)
    for i in range(6):
        bits |= blk[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    eight = a0 > a1
    pal = np.zeros((len(blk), 8), np.float32)
    pal[:, 0], pal[:, 1] = a0, a1
    for i in range(1, 7):
        pal[:, i + 1] = np.where(eight, ((7 - i) * a0 + i * a1) / 7, 0)
    for i in range(1, 5):
        pal[:, i + 1] = np.where(eight, pal[:, i + 1], ((5 - i) * a0 + i * a1) / 5)
    pal[:, 6] = np.where(eight, pal[:, 6], 0)
    pal[:, 7] = np.where(eight, pal[:, 7], 255)
    idx = (bits[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))) & np.uint64(7)
    return np.take_along_axis(pal, idx.astype(np.int64), 1)


def decode(data, w, h, fmt):
    """fmt 'BC1' or 'BC3'; returns (h, w, 4) float32 RGBA 0..255."""
    bs = 8 if fmt == 'BC1' else 16
    n = max(1, (w + 3) // 4) * max(1, (h + 3) // 4)
    if len(data) < n * bs:
        raise ValueError(f'{fmt} {w}x{h} needs {n * bs} bytes, got {len(data)}')
    blk = np.frombuffer(data[:n * bs], np.uint8).reshape(n, bs)
    if fmt == 'BC1':
        px = decode_bc1_colour(blk)
    else:
        px = decode_bc1_colour(blk[:, 8:], punch=False)
        px[:, :, 3] = decode_bc3_alpha(blk[:, :8])
    return _blocks_to_image(px, w, h)


def downsample(img):
    h, w = img.shape[:2]
    nh, nw = max(1, h // 2), max(1, w // 2)
    if h == 1 or w == 1:  # o lado ímpar perde a última coluna/linha, como no caso 2D (5x1 -> 2x1)
        return img[:nh * (h // nh), :nw * (w // nw)].reshape(nh, h // nh, nw, w // nw, 4).mean((1, 3))
    return img[:nh * 2, :nw * 2].reshape(nh, 2, nw, 2, 4).mean((1, 3))


def _to_blocks(img):
    h, w = img.shape[:2]
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    pad = np.zeros((bh * 4, bw * 4, 4), np.float32)
    pad[:h, :w] = img
    if h < 4 or w < 4:  # replicate edges into the unused block texels
        pad[:, w:] = pad[:, w - 1:w]
        pad[h:, :] = pad[h - 1:h, :]
    return pad.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * bw, 16, 4)


def _encode_colour(px):
    rgb = px[:, :, :3]
    lo, hi = rgb.min(1), rgb.max(1)

    def q(c):
        r = np.clip(np.round(c[:, 0] * 31 / 255), 0, 31).astype(np.uint32)
        g = np.clip(np.round(c[:, 1] * 63 / 255), 0, 63).astype(np.uint32)
        b = np.clip(np.round(c[:, 2] * 31 / 255), 0, 31).astype(np.uint32)
        return (r << 11) | (g << 5) | b
    c0, c1 = q(hi), q(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _565(c0), _565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    d = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    idx = d.argmin(-1).astype(np.uint32)
    idx = np.where((c0 == c1)[:, None], 0, idx)
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros((len(px), 8), np.uint8)
    out[:, 0], out[:, 1] = c0 & 255, c0 >> 8
    out[:, 2], out[:, 3] = c1 & 255, c1 >> 8
    for i in range(4):
        out[:, 4 + i] = (bits >> (8 * i)) & 255
    return out


def _encode_alpha(px):
    a = px[:, :, 3]
    a0, a1 = np.round(a.max(1)), np.round(a.min(1))
    pal = np.stack([a0, a1] + [((7 - i) * a0 + i * a1) / 7 for i in range(1, 7)], 1)
    idx = np.abs(a[:, :, None] - pal[:, None, :]).argmin(-1).astype(np.uint64)
    idx = np.where((a0 == a1)[:, None], 0, idx).astype(np.uint64)
    bits = (idx << (np.uint64(3) * np.arange(16, dtype=np.uint64))).sum(1).astype(np.uint64)
    out = np.zeros((len(px), 8), np.uint8)
    out[:, 0], out[:, 1] = a0.astype(np.uint8), a1.astype(np.uint8)
    for i in range(6):
        out[:, 2 + i] = ((bits >> np.uint64(8 * i)) & np.uint64(255)).astype(np.uint8)
    return out


def encode(img, fmt):
    px = _to_blocks(img)
    if fmt == 'BC1':
        if (img[:, :, 3] < 128).any():  # punch-through alpha: keep it opaque here (BC1 colour mode only)
            pass
        return _encode_colour(px).tobytes()
    return np.concatenate([_encode_alpha(px), _encode_colour(px)], 1).tobytes()


def mip_size(w, h, fmt):
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == 'BC1' else 16)
