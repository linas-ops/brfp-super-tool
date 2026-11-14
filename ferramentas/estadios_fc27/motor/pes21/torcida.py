"""Torcida de um estádio do PES 2021: as áreas do audiarea.bin viram lugares, como os do crowd_<id>.dat do FIFA 16.

O PES não guarda lugar por lugar: guarda áreas (quadriláteros inclinados sobre a arquibancada) que o jogo preenche.
audiarea.bin (conferido no Camp Nou):
  0x00  u32 1, u32 1, depois 4 lados x 3 deslocamentos de bloco (0 = não tem)
  bloco  u8 lado, u8 tipo, u16 1, u32 deslocamento da caixa, caixa (6 floats), u32 áreas, e por área (96 bytes):
         u32 número, f32 escala (comprimento da rampa / 10), f32 e f32 marca (1 = comum, 5 = setor à parte: visitantes),
         4 cantos (x, y, z) e 4 UV no mapa de cores das cadeiras (audi\\sourceimages\\au_seat.png)
Cada área é preenchida por fileiras (da borda de baixo para a de cima) e lugares ao longo da fileira. As fileiras ficam no
meio dos degraus do estádio embaixo da área (achados na geometria preparada, pela linha do meio da área); sem degraus
regulares, de 80 em 80 cm. A altura de cada lugar é a do degrau embaixo dele, para ninguém ficar dentro do degrau nem no ar.
"""
from __future__ import annotations
import struct
import zlib
from pathlib import Path

import numpy as np

from . import fpk

FILEIRA = 0.80     # profundidade de uma fileira (m, na horizontal)
LUGAR = 0.50       # largura de um lugar (m)
MARGEM = 0.20      # folga nas pontas da fileira (m)
PROCURA = (0.9, 0.9)  # quanto abaixo e acima do plano da área o degrau é procurado (m)
CELULA = 2.0
DEGRAU = (0.45, 1.5)   # profundidade de um degrau que recebe uma fileira (m)
SALTO = 0.08           # subida que separa dois degraus (m)


def ler_areas(origem):
    """Áreas da torcida de um audiarea.bin (ou do pacote audiarea_st<NNN>.fpk): dict com quad (n, 4, 3), uv (n, 4, 2),
    escala, visitante, lado e tipo (n)."""
    origem = Path(origem)
    if origem.suffix.lower() == '.fpk':
        pk = fpk.Fpk(origem)
        nome = next((n for n in pk.nomes() if n.lower().endswith('audiarea.bin')), None)
        if nome is None:
            raise ValueError(f'{origem.name} não tem audiarea.bin')
        b = pk.ler(nome)
    else:
        b = origem.read_bytes()
    if len(b) < 56 or struct.unpack_from('<II', b, 0) != (1, 1):
        raise ValueError('audiarea.bin de versão desconhecida')
    quad, uv, escala, marca, lado, tipo = [], [], [], [], [], []
    for off in struct.unpack_from('<12I', b, 8):
        if not off:
            continue
        if off + 0x24 > len(b):
            raise ValueError('audiarea.bin truncado')
        ld, tp, um, caixa = struct.unpack_from('<BBHI', b, off)
        n, = struct.unpack_from('<I', b, off + 0x20)
        if caixa != off + 8 or off + 0x24 + 96 * n > len(b):
            raise ValueError('bloco de áreas da torcida com layout desconhecido')
        rec = np.frombuffer(b, '<f4', 24 * n, off + 0x24).reshape(n, 24).astype(np.float64)
        quad.append(rec[:, 4:16].reshape(n, 4, 3))
        uv.append(rec[:, 16:24].reshape(n, 4, 2))
        escala.append(rec[:, 1])
        marca.append(rec[:, 2])
        lado.append(np.full(n, ld))
        tipo.append(np.full(n, tp))
    if not quad:
        return dict(quad=np.zeros((0, 4, 3)), uv=np.zeros((0, 4, 2)), escala=np.zeros(0), visitante=np.zeros(0, bool),
                    lado=np.zeros(0, int), tipo=np.zeros(0, int))
    marca = np.concatenate(marca)
    return dict(quad=np.concatenate(quad), uv=np.concatenate(uv), escala=np.concatenate(escala), visitante=marca > 2.5,
                lado=np.concatenate(lado), tipo=np.concatenate(tipo))


def _dist_campo(p):
    q = np.maximum(np.abs(p[..., [0, 2]]) - np.array([52.5, 34.0]), 0.0)
    return np.linalg.norm(q, axis=-1)


def orientar(quad, uv):
    """Cantos na ordem (frente esquerda, frente direita, trás direita, trás esquerda): a frente é a borda de baixo (ou a
    mais perto do campo, numa área plana). Devolve (quad, uv) reordenados."""
    n = len(quad)
    q2, u2 = np.empty_like(quad), np.empty_like(uv)
    for i in range(n):
        q = quad[i]
        melhor, nota = 0, None
        for k in range(4):
            a, b = q[k], q[(k + 1) % 4]
            v = (a[1] + b[1]) / 2 + 0.02 * (_dist_campo(a) + _dist_campo(b)) / 2
            if nota is None or v < nota:
                melhor, nota = k, v
        ordem = [melhor, (melhor + 1) % 4, (melhor + 2) % 4, (melhor + 3) % 4]
        q2[i], u2[i] = q[ordem], uv[i][ordem]
    return q2, u2


def _grade(quad, fileira=FILEIRA, lugar=LUGAR):
    """Por área: (fileiras, lugares por fileira (lista), profundidade horizontal)."""
    a, b, c, d = quad[:, 0], quad[:, 1], quad[:, 2], quad[:, 3]
    prof = (np.linalg.norm((d - a)[:, [0, 2]], axis=1) + np.linalg.norm((c - b)[:, [0, 2]], axis=1)) / 2
    nf = np.maximum(1, np.round(prof / fileira).astype(int))
    return nf, prof


def estimar(areas):
    """Lugares que as áreas rendem (fileiras de 80 em 80 cm, sem conferir os degraus)."""
    quad, uv = orientar(areas['quad'], areas['uv'])
    return sum(len(x[0]) for x in _lugares(quad, uv, _fileiras(quad, None)[0]))


def _fileiras(quad, alt):
    """Por área, as frações (0 = borda da frente, 1 = a de trás) do meio de cada fileira, e em quantas áreas elas vieram
    dos degraus da geometria (alt = Alturas, ou None para fileiras de 80 em 80 cm)."""
    nf, prof = _grade(quad)
    out, dos_degraus = [], 0
    for i in range(len(quad)):
        padrao = (np.arange(nf[i]) + 0.5) / nf[i]
        H = prof[i]
        if alt is None or H < 2 * DEGRAU[0]:
            out.append(padrao)
            continue
        a, b, c, d = quad[i]
        m0, m1 = (a + b) / 2, (c + d) / 2
        s = np.arange(0.0, H + 1e-9, 0.05)
        h = alt.em(m0[None, :] + (s / H)[:, None] * (m1 - m0)[None, :], 1.2, 1.2)
        tem = ~np.isnan(h)
        if tem.mean() < 0.8:
            out.append(padrao)
            continue
        h = np.interp(s, s[tem], h[tem])
        bordas = np.concatenate([[0.0], s[np.flatnonzero(np.diff(h) > SALTO) + 1], [H]])
        larg = np.diff(bordas)
        bons = (larg >= DEGRAU[0]) & (larg <= DEGRAU[1])
        if bons.sum() >= 2 and larg[bons].sum() >= 0.7 * H:
            out.append(((bordas[:-1] + bordas[1:]) / 2)[bons] / H)
            dos_degraus += 1
        else:
            out.append(padrao)
    return out, dos_degraus


def _lugares(quad, uv, fileiras):
    """Gera, por área, (posições (k, 3), uv (k, 2), direção para o campo (2,), fileira (k,))."""
    for i in range(len(quad)):
        a, b, c, d = quad[i]
        ua, ub, uc, ud = uv[i]
        pts, uvs, fil = [], [], []
        for k, v in enumerate(fileiras[i]):
            esq, dire = a + v * (d - a), b + v * (c - b)
            L = np.linalg.norm(dire - esq)
            n = int((L - 2 * MARGEM) / LUGAR) if L > 2 * MARGEM else 0
            if n < 1:
                continue
            t = (np.arange(n) + 0.5) / n
            t = (MARGEM + t * (L - 2 * MARGEM)) / L
            pts.append(esq[None, :] + t[:, None] * (dire - esq)[None, :])
            ue, ur = ua + v * (ud - ua), ub + v * (uc - ub)
            uvs.append(ue[None, :] + t[:, None] * (ur - ue)[None, :])
            fil.append(np.full(n, k))
        desce = ((a + b) - (c + d))[[0, 2]]
        nrm = np.linalg.norm(desce)
        if nrm < 1e-6:
            m = (a + b + c + d) / 4
            alvo = np.array([np.clip(m[0], -52.5, 52.5), np.clip(m[2], -34.0, 34.0)])
            desce = alvo - m[[0, 2]]
            nrm = max(np.linalg.norm(desce), 1e-6)
        if pts:
            yield np.concatenate(pts), np.concatenate(uvs), desce / nrm, np.concatenate(fil)
        else:
            yield np.zeros((0, 3)), np.zeros((0, 2)), desce / nrm, np.zeros(0, int)


class Alturas:
    """Altura da superfície do estádio embaixo de um ponto: triângulos pouco inclinados numa grade em XZ."""

    def __init__(self, tris):
        tris = np.asarray(tris, np.float64).reshape(-1, 3, 3)
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ok = (ln > 1e-10) & (np.abs(n[:, 1]) > 0.35 * ln)
        self.t = tris[ok]
        self.celulas = {}
        if not len(self.t):
            return
        lo = np.floor(self.t[:, :, [0, 2]].min(1) / CELULA).astype(int)
        hi = np.floor(self.t[:, :, [0, 2]].max(1) / CELULA).astype(int)
        pequeno = ((hi - lo + 1).prod(1) <= 64)
        for k in np.flatnonzero(pequeno):
            for cx in range(lo[k, 0], hi[k, 0] + 1):
                for cz in range(lo[k, 1], hi[k, 1] + 1):
                    self.celulas.setdefault((cx, cz), []).append(k)
        self.grandes = np.flatnonzero(~pequeno)
        self.celulas = {k: np.array(v) for k, v in self.celulas.items()}

    def em(self, P, abaixo=PROCURA[0], acima=PROCURA[1]):
        """Para cada ponto (x, y, z): a altura da superfície mais alta entre y - abaixo e y + acima, ou NaN."""
        P = np.asarray(P, np.float64)
        out = np.full(len(P), np.nan)
        if not len(self.t) or not len(P):
            return out
        cel = np.floor(P[:, [0, 2]] / CELULA).astype(int)
        ordem = np.lexsort((cel[:, 1], cel[:, 0]))
        cortes = np.flatnonzero(np.any(np.diff(cel[ordem], axis=0) != 0, axis=1)) + 1
        for grupo in np.split(ordem, cortes):
            k = tuple(cel[grupo[0]])
            cand = self.celulas.get(k)
            cand = self.grandes if cand is None else np.concatenate([cand, self.grandes])
            if not len(cand):
                continue
            T = self.t[cand]
            a, b, c = T[:, 0], T[:, 1], T[:, 2]
            px, pz = P[grupo, 0][:, None], P[grupo, 2][:, None]
            den = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
            den = np.where(np.abs(den) < 1e-12, np.nan, den)[None, :]
            l1 = ((b[:, 2] - c[:, 2])[None, :] * (px - c[:, 0][None, :]) + (c[:, 0] - b[:, 0])[None, :] * (pz - c[:, 2][None, :])) / den
            l2 = ((c[:, 2] - a[:, 2])[None, :] * (px - c[:, 0][None, :]) + (a[:, 0] - c[:, 0])[None, :] * (pz - c[:, 2][None, :])) / den
            l3 = 1 - l1 - l2
            y = l1 * a[:, 1][None, :] + l2 * b[:, 1][None, :] + l3 * c[:, 1][None, :]
            ref = P[grupo, 1][:, None]
            dentro = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6) & (y >= ref - abaixo) & (y <= ref + acima)
            y = np.where(dentro, y, -np.inf)
            best = y.max(1)
            out[grupo] = np.where(np.isfinite(best), best, np.nan)
        return out


def lugares(areas, tris=None):
    """Lugares da torcida: dict com pos (n, 3), orient (graus, a convenção do FIFA 16: 0 = virado para +X, -90 = para +Z),
    uv (n, 2) no mapa das cadeiras, visitante (n), area (n), sem_degrau (quantos ficaram no plano da área por não haver
    geometria embaixo) e areas_com_degraus (em quantas áreas as fileiras vieram dos degraus da geometria)."""
    quad, uv = orientar(areas['quad'], areas['uv'])
    alt = Alturas(tris) if tris is not None and len(tris) else None
    fileiras, com_degraus = _fileiras(quad, alt)
    pos, uvs, ori, vis, qual = [], [], [], [], []
    for i, (p, u, desce, _) in enumerate(_lugares(quad, uv, fileiras)):
        if not len(p):
            continue
        pos.append(p)
        uvs.append(u)
        ori.append(np.full(len(p), -np.degrees(np.arctan2(desce[1], desce[0]))))
        vis.append(np.full(len(p), bool(areas['visitante'][i])))
        qual.append(np.full(len(p), i))
    if not pos:
        z = np.zeros(0)
        return dict(pos=np.zeros((0, 3)), orient=z, uv=np.zeros((0, 2)), visitante=z.astype(bool), area=z.astype(int), sem_degrau=0,
                    areas_com_degraus=0)
    pos = np.concatenate(pos)
    sem = 0
    if alt is not None:
        y = alt.em(pos)
        falta = np.isnan(y)
        sem = int(falta.sum())
        pos[:, 1] = np.where(falta, pos[:, 1], y)
    return dict(pos=pos, orient=np.concatenate(ori), uv=np.concatenate(uvs), visitante=np.concatenate(vis), area=np.concatenate(qual),
                sem_degrau=sem, areas_com_degraus=com_degraus)


# ------------------------------------------------------------------ cores das cadeiras (au_seat.png)
def ler_png(path):
    """PNG de 8 bits (RGB, RGBA, cinza ou paleta, sem entrelaçamento) -> array (h, w, 3) uint8."""
    b = Path(path).read_bytes()
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('não é PNG: ' + str(path))
    q, idat, pal = 8, [], None
    w = h = bits = tipo = entr = None
    while q + 8 <= len(b):
        n, t = struct.unpack_from('>I4s', b, q)
        d = b[q + 8:q + 8 + n]
        q += 12 + n
        if t == b'IHDR':
            w, h, bits, tipo, _, _, entr = struct.unpack('>IIBBBBB', d)
        elif t == b'PLTE':
            pal = np.frombuffer(d, np.uint8).reshape(-1, 3)
        elif t == b'IDAT':
            idat.append(d)
        elif t == b'IEND':
            break
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(tipo)
    if w is None or bits != 8 or canais is None or entr:
        raise ValueError('PNG de formato não suportado (use 8 bits sem entrelaçamento): ' + str(path))
    raw = zlib.decompress(b''.join(idat))
    passo = w * canais
    img = np.zeros((h, passo), np.uint8)
    ant = np.zeros(passo, np.int64)
    for y in range(h):
        f = raw[y * (passo + 1)]
        lin = np.frombuffer(raw, np.uint8, passo, y * (passo + 1) + 1).astype(np.int64)
        if f == 1:
            for c in range(canais):
                lin[c::canais] = np.cumsum(lin[c::canais]) & 255
        elif f == 2:
            lin = (lin + ant) & 255
        elif f in (3, 4):
            out = np.zeros(passo, np.int64)
            for x in range(passo):
                esq = out[x - canais] if x >= canais else 0
                if f == 3:
                    pred = (esq + ant[x]) >> 1
                else:
                    cima, diag = ant[x], (ant[x - canais] if x >= canais else 0)
                    p = esq + cima - diag
                    pa, pb, pc = abs(p - esq), abs(p - cima), abs(p - diag)
                    pred = esq if pa <= pb and pa <= pc else (cima if pb <= pc else diag)
                out[x] = (lin[x] + pred) & 255
            lin = out
        elif f != 0:
            raise ValueError('PNG com filtro desconhecido: ' + str(path))
        img[y] = lin
        ant = lin
    img = img.reshape(h, w, canais)
    if tipo == 3:
        if pal is None:
            raise ValueError('PNG de paleta sem paleta: ' + str(path))
        return pal[img[..., 0]]
    if tipo in (0, 4):
        return np.repeat(img[..., :1], 3, 2)
    return img[..., :3].copy()


def cores(img, uv):
    """Cor (n, 3) uint8 de cada lugar no mapa das cadeiras: u para a direita, v a partir de baixo (o mapa é a vista de
    cima do estádio, com +X à direita e +Z embaixo)."""
    h, w = img.shape[:2]
    x = np.clip(np.floor(uv[:, 0] * w).astype(int), 0, w - 1)
    y = np.clip(np.floor((1.0 - uv[:, 1]) * h).astype(int), 0, h - 1)
    return img[y, x]
