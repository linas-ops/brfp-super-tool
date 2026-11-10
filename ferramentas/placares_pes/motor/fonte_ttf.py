"""Fonte TrueType (.ttf) a partir de imagens de caracteres — para os números do placar do PES.

O PES desenha o relógio e o placar com uma "fonte" em imagem (MatchPlate-texFont-digit0…9, colon e plus, 17×26 px).
Aqui cada imagem é ampliada, cortada pela transparência e contornada (OpenCV); os contornos viram glifos de linhas retas
numa fonte TrueType mínima (cmap, glyf, head, hhea, hmtx, loca, maxp, name, OS/2, post), sem bibliotecas de fonte.
"""
import struct
import time

import numpy as np
from PIL import Image

UPM = 1000
ASC, DESC = 800, -200
ALTURA_CAPS = 720                       # altura dos números em unidades (o topo da imagem do caractere)


def _contornos(img, ampliar=8, limiar=0.5, tolerancia=0.7):
    """Contornos (lista de [(x, y)] em pixels da imagem original, y para baixo) da área opaca da imagem."""
    import cv2
    a = np.asarray(img.convert("RGBA"))[..., 3]
    h, w = a.shape
    grande = np.asarray(Image.fromarray(a).resize((w * ampliar, h * ampliar), Image.BICUBIC), np.float32) / 255.0
    masc = (grande >= limiar).astype(np.uint8)
    masc = np.pad(masc, 1)
    cs, _hier = cv2.findContours(masc, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cs:
        if cv2.contourArea(c) < 4 * ampliar:
            continue
        c = cv2.approxPolyDP(c, tolerancia * ampliar / 4, True)
        pts = [((p[0][0] - 1) / ampliar, (p[0][1] - 1) / ampliar) for p in c]
        if len(pts) >= 3:
            out.append(pts)
    return out


def _area(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) / 2


def _glifo(contornos_fu):
    """Glifo simples do 'glyf' (só pontos na curva)."""
    if not contornos_fu:
        return b""
    xs = [x for c in contornos_fu for x, _ in c]
    ys = [y for c in contornos_fu for _, y in c]
    fim, n = [], 0
    for c in contornos_fu:
        n += len(c)
        fim.append(n - 1)
    dados = struct.pack(">hhhhh", len(contornos_fu), min(xs), min(ys), max(xs), max(ys))
    dados += struct.pack(">%dH" % len(fim), *fim) + struct.pack(">H", 0)
    dados += bytes([0x01] * n)                                   # ON_CURVE, coordenadas em 2 bytes
    px = py = 0
    dx, dy = [], []
    for c in contornos_fu:
        for x, y in c:
            dx.append(x - px)
            dy.append(y - py)
            px, py = x, y
    dados += struct.pack(">%dh" % n, *dx) + struct.pack(">%dh" % n, *dy)
    return dados + b"\0" * ((-len(dados)) % 4)


def _checksum(d):
    d = d + b"\0" * ((-len(d)) % 4)
    return sum(struct.unpack(">%dI" % (len(d) // 4), d)) & 0xFFFFFFFF


def _nome(familia):
    regs = []
    textos = {1: familia, 2: "Regular", 3: familia + " (BRFP)", 4: familia, 5: "Version 1.0", 6: familia.replace(" ", "")}
    blob = b""
    for nid, txt in sorted(textos.items()):
        for plat, enc, lang, cod in ((1, 0, 0, "latin-1"), (3, 1, 0x409, "utf-16-be")):
            b = txt.encode(cod, "replace")
            regs.append((plat, enc, lang, nid, len(b), len(blob)))
            blob += b
    regs.sort()
    cab = struct.pack(">HHH", 0, len(regs), 6 + 12 * len(regs))
    return cab + b"".join(struct.pack(">6H", *r) for r in regs) + blob


def montar(caracteres, familia, altura_px=None, espaco_px=2.0, monoespaco="0123456789"):
    """caracteres: {char: imagem PIL RGBA}. Devolve (bytes do .ttf, {char: avanço em frações do em})."""
    alt = altura_px or max(im.height for im in caracteres.values())
    esc = ALTURA_CAPS / alt
    glifos = [(".notdef", b"", int(alt * 0.6 * esc), 0), ("space", b"", int(alt * 0.35 * esc), 0)]
    cmap = {32: 1}
    largura_mono = None
    tinta = {}
    for ch, im in caracteres.items():
        cs = _contornos(im)
        tinta[ch] = cs
    mono = [ch for ch in monoespaco if tinta.get(ch)]
    if mono:
        larguras = []
        for ch in mono:
            xs = [x for c in tinta[ch] for x, _ in c]
            larguras.append(max(xs) - min(xs))
        largura_mono = max(larguras) + espaco_px
    for ch, cs in tinta.items():
        if not cs:
            continue
        xs = [x for c in cs for x, _ in c]
        x0, x1 = min(xs), max(xs)
        avanco = largura_mono if (ch in monoespaco and largura_mono) else (x1 - x0) + espaco_px
        desloc = (avanco - (x1 - x0)) / 2 - x0                     # centrado no avanço
        fu = []
        for c in cs:
            fu.append([(int(round((x + desloc) * esc)), int(round((caracteres[ch].height - y) * esc))) for x, y in c])
        # TrueType: contorno de fora no sentido horário (com y para cima) e furos ao contrário; o maior é o de fora e
        # cada um que estiver dentro de outro é furo
        fu.sort(key=lambda p: -abs(_area(p)))
        orient = []
        for i, p in enumerate(fu):
            dentro = sum(1 for q in fu[:i] if _dentro(p[0], q))
            horario = dentro % 2 == 0
            a = _area(p)
            if (a < 0) != horario:                                # área < 0 = horário com y para cima
                p = p[::-1]
            orient.append(p)
        dados = _glifo(orient)
        lsb = min(x for c in orient for x, _ in c)
        cmap[ord(ch)] = len(glifos)
        glifos.append((ch, dados, int(round(avanco * esc)), lsb))
    avancos = {g[0]: g[2] / UPM for g in glifos[2:]}
    avancos[" "] = glifos[1][2] / UPM
    return _arquivo(glifos, cmap, familia), avancos


def traco(modelo):
    """Imagem de um '-' no estilo dos números: a espessura do traço do '1' e meia largura de dígito, na meia altura."""
    a = np.asarray(modelo.convert("RGBA"))[..., 3]
    h, w = a.shape
    linhas = (a > 127).sum(axis=1)               # no '1', cada linha cruza a haste: a largura dela é a espessura
    espessura = max(2, int(np.median(linhas[linhas > 0])) if (linhas > 0).any() else h // 8)
    ys = np.nonzero(linhas)[0]
    meio = (ys.min() + ys.max()) // 2 if len(ys) else h // 2
    larg = max(3, int(w * 0.5))
    img = np.zeros((h, w, 4), np.uint8)
    x0 = (w - larg) // 2
    img[meio - espessura // 2:meio - espessura // 2 + espessura, x0:x0 + larg] = 255
    return Image.fromarray(img, "RGBA")


def _dentro(pt, poli):
    x, y = pt
    d = False
    n = len(poli)
    for i in range(n):
        x1, y1 = poli[i]
        x2, y2 = poli[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1:
            d = not d
    return d


def _arquivo(glifos, cmap, familia):
    n = len(glifos)
    glyf = b""
    loca = []
    for _nome_g, dados, _adv, _lsb in glifos:
        loca.append(len(glyf))
        glyf += dados
    loca.append(len(glyf))
    loca_b = struct.pack(">%dI" % len(loca), *loca)
    todos = [struct.unpack(">hhhhh", d[:10]) for _, d, _, _ in glifos if d]
    xmin = min((b[1] for b in todos), default=0)
    ymin = min((b[2] for b in todos), default=0)
    xmax = max((b[3] for b in todos), default=0)
    ymax = max((b[4] for b in todos), default=0)
    agora = int(time.time()) + 2082844800                       # segundos desde 1904
    head = struct.pack(">IIIIHHQQhhhhHHhhh", 0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0x000B, UPM, agora, agora,
                       xmin, ymin, xmax, ymax, 0, 8, 2, 1, 0)
    max_pts = max_cont = 0
    for _, d, _, _ in glifos:
        if d:
            nc = struct.unpack(">h", d[:2])[0]
            fim = struct.unpack(">%dH" % nc, d[10:10 + 2 * nc])
            max_cont = max(max_cont, nc)
            max_pts = max(max_pts, fim[-1] + 1)
    maxp = struct.pack(">IHHHHHHHHHHHHHH", 0x00010000, n, max_pts, max_cont, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0)
    avancos = [g[2] for g in glifos]
    hhea = struct.pack(">IhhhH11hH", 0x00010000, ASC, DESC, 0, max(avancos), min(g[3] for g in glifos),
                       0, xmax, 1, 0, 0, 0, 0, 0, 0, 0, n)
    hmtx = b"".join(struct.pack(">Hh", adv, lsb) for _, _, adv, lsb in glifos)
    # cmap formato 4
    cods = sorted(cmap)
    segs = [(c, c, cmap[c]) for c in cods] + [(0xFFFF, 0xFFFF, 0)]
    ns = len(segs)
    busca = 2 ** int(np.floor(np.log2(ns))) * 2
    f4 = struct.pack(">HHHHHHH", 4, 0, 0, ns * 2, busca, int(np.log2(busca / 2)), ns * 2 - busca)
    f4 += struct.pack(">%dH" % ns, *[s[1] for s in segs]) + b"\0\0"
    f4 += struct.pack(">%dH" % ns, *[s[0] for s in segs])
    f4 += struct.pack(">%dh" % ns, *[((s[2] - s[0]) if s[2] else 1) for s in segs])
    f4 += struct.pack(">%dH" % ns, *([0] * ns))
    f4 = f4[:2] + struct.pack(">H", len(f4)) + f4[4:]
    cmap_b = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + f4
    os2 = (struct.pack(">HhHHH", 1, int(np.mean(avancos)), 400, 5, 0)
           + struct.pack(">10h", 650, 700, 0, 140, 650, 700, 0, 480, 50, 250) + struct.pack(">h", 0)
           + b"" + struct.pack(">4I", 1, 0, 0, 0) + b"BRFP"
           + struct.pack(">HHH", 0x40, 32, max(cods)) + struct.pack(">hhh", ASC, DESC, 0)
           + struct.pack(">HH", ASC, -DESC) + struct.pack(">II", 1, 0))
    post = struct.pack(">IIhhIIIII", 0x00030000, 0, -100, 50, 1 if len(set(avancos[2:])) <= 1 else 0, 0, 0, 0, 0)
    tabelas = {b"OS/2": os2, b"cmap": cmap_b, b"glyf": glyf, b"head": head, b"hhea": hhea, b"hmtx": hmtx,
               b"loca": loca_b, b"maxp": maxp, b"name": _nome(familia), b"post": post}
    nt = len(tabelas)
    busca = 2 ** int(np.floor(np.log2(nt)))
    cab = struct.pack(">IHHHH", 0x00010000, nt, busca * 16, int(np.log2(busca)), nt * 16 - busca * 16)
    pos = 12 + 16 * nt
    dir_, corpo = b"", b""
    for tag in sorted(tabelas):
        d = tabelas[tag]
        dir_ += struct.pack(">4sIII", tag, _checksum(d), pos + len(corpo), len(d))
        corpo += d + b"\0" * ((-len(d)) % 4)
    arq = bytearray(cab + dir_ + corpo)
    # checkSumAdjustment do head
    p_head = 12 + 16 * nt + sum(len(tabelas[t]) + (-len(tabelas[t])) % 4 for t in sorted(tabelas) if t < b"head")
    ajuste = (0xB1B0AFBA - _checksum(bytes(arq))) & 0xFFFFFFFF
    struct.pack_into(">I", arq, p_head + 8, ajuste)
    return bytes(arq)
