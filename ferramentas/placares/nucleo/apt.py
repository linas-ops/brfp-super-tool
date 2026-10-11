"""APT de 64 bits do FC ("Apt Data:1:7:8") — o formato tipo Flash dos overlays (placares).

Estrutura (como o APT de 32 bits documentado pelo OpenSAGE, com cada campo alargado para 8 bytes):
- Character: tipo (u64), assinatura 0x09876543 (u64), 16 bytes, campos do tipo.
  Movie (9): quadros (n, ptr), ?, characters (n, ptr), largura/altura/ms por quadro/nº imports (u32), imports
  (ptr), exports (n, ptr). Sprite (5): quadros (n, ptr). Shape (1): limites (4 floats), geometria (u64).
  Image (7): textura (u64). Text (2): limites, fonte, alinhamento, cor RGBA, altura, só leitura, multilinha,
  quebra, conteúdo (ptr), variável (ptr). Font (3): nome (ptr).
- Quadro: (nº de itens, ptr para lista de ptrs). Item: tipo (u64) — 3 = PlaceObject (80 bytes):
  flags u32 @8, profundidade @12, character @16, matriz a b c d @20, translação x y @36, cor multiplicada RGBA
  @44, cor somada RGBA @48, ratio @52, nome (ptr) @56, profundidade do recorte @64, ações @72.
- No .big, a entrada "N" guarda a geometria (Shape) ou o DDS (Image) do character N-1.
- Geometria: tamanho, nº de itens, 0, offsets; cada item: tamanho, tipo (1 = desenho), 0, 16, tamanho-16,
  espécie @0x14 (0 textura, 2 cor sólida, 3 linhas), espessura @0x1C, cor ARGB @0x20, imagem @0x24 (character),
  matriz da textura a b c d tx ty @0x30 (em pixels da textura), nº de triângulos/segmentos @0x48, offset dos
  vértices @0x4C (a partir de item+0x10). Vértice de triângulo: 32 bytes (x, y, ...); de linha: 16 bytes.
"""
import struct

SIG = 0x09876543
TIPOS = {1: "forma", 2: "texto", 3: "fonte", 4: "botao", 5: "sprite", 7: "imagem", 9: "filme"}
PLACE_TAM = 80
# flags do PlaceObject
F_MOVE, F_CHAR, F_MATRIZ, F_COR, F_RATIO, F_NOME, F_RECORTE, F_ACAO = 1, 2, 4, 8, 16, 32, 64, 128


class ErroApt(Exception):
    pass


class Apt:
    def __init__(self, dados):
        if not dados.startswith(b"Apt Data"):
            raise ErroApt("A entrada 0 do .big não é um APT")
        if b":8" not in dados[:16]:
            raise ErroApt("APT de 32 bits (jogos antigos) não é suportado")
        self.d = bytearray(dados)
        self._ler()

    # ---------------------------------------------------------- leitura
    def u32(self, p): return struct.unpack_from("<I", self.d, p)[0]
    def i32(self, p): return struct.unpack_from("<i", self.d, p)[0]
    def u64(self, p): return struct.unpack_from("<Q", self.d, p)[0]
    def f32(self, p): return struct.unpack_from("<f", self.d, p)[0]

    def txt(self, p):
        if not p or p >= len(self.d):
            return ""
        e = self.d.index(b"\0", p)
        return self.d[p:e].decode("latin-1")

    def _quadros(self, n, ptr):
        out = []
        if n > 100000 or not ptr:
            return out
        for i in range(n):
            ni, lp = self.u64(ptr + 16 * i), self.u64(ptr + 16 * i + 8)
            itens = []
            for j in range(min(ni, 100000)):
                it = self._item(self.u64(lp + 8 * j))
                if it:
                    itens.append(it)
            out.append(itens)
        return out

    def _item(self, p):
        t = self.u64(p)
        if t == 3:
            fl = self.u32(p + 8)
            return {"t": "place", "off": p, "fl": fl, "prof": self.i32(p + 12), "char": self.i32(p + 16),
                    "m": list(struct.unpack_from("<4f", self.d, p + 20)), "tx": list(struct.unpack_from("<2f", self.d, p + 36)),
                    "tint": list(self.d[p + 44:p + 48]), "soma": list(self.d[p + 48:p + 52]),
                    "nome": self.txt(self.u64(p + 56)) if fl & F_NOME else "", "clip": self.i32(p + 64)}
        if t == 4:
            return {"t": "remove", "prof": self.i32(p + 8)}
        if t == 2:
            return {"t": "rotulo", "nome": self.txt(self.u64(p + 8))}
        return None

    def _char(self, i, p):
        if not p:
            return None
        t = self.u64(p)
        if self.u32(p + 8) != SIG:
            raise ErroApt(f"Character {i} com assinatura inválida")
        c = {"t": TIPOS.get(t, "outro"), "off": p}
        q = p + 32
        if t == 9:
            c["quadros"] = self._quadros(self.u64(q), self.u64(q + 8))
        elif t == 5:
            c["quadros"] = self._quadros(self.u64(q), self.u64(q + 8))
        elif t == 1:
            c["limites"] = list(struct.unpack_from("<4f", self.d, q))
            c["geo"] = self.u64(q + 16)
        elif t == 7:
            c["tex"] = self.u64(q)
        elif t == 2:
            c.update({"limites": list(struct.unpack_from("<4f", self.d, q)), "fonte": self.u32(q + 16),
                      "alinh": self.u32(q + 20), "cor": list(self.d[q + 24:q + 28]), "altura": self.f32(q + 28),
                      "so_leitura": bool(self.u32(q + 32)), "multilinha": bool(self.u32(q + 36)),
                      "quebra": bool(self.u32(q + 40)), "conteudo": self.txt(self.u64(q + 48)),
                      "variavel": self.txt(self.u64(q + 56))})
        elif t == 3:
            c["nome"] = self.txt(self.u64(q))
        return c

    def _ler(self):
        p = self.d.find(struct.pack("<QQ", 9, SIG))
        if p < 0:
            raise ErroApt("Movie não encontrado no APT")
        q = p + 32
        self.quadros_raiz = self._quadros(self.u64(q), self.u64(q + 8))
        nchars, pchars = self.u64(q + 24), self.u64(q + 32)
        self.largura, self.altura, self.mspf, nimp = struct.unpack_from("<4I", self.d, q + 40)
        pimp, nexp, pexp = self.u64(q + 56), self.u64(q + 64), self.u64(q + 72)
        self.imports = []
        for i in range(nimp):
            b = pimp + 32 * i
            self.imports.append({"filme": self.txt(self.u64(b)), "nome": self.txt(self.u64(b + 8)), "char": self.u64(b + 16)})
        self.exports = [{"nome": self.txt(self.u64(pexp + 16 * i)), "char": self.u64(pexp + 16 * i + 8)} for i in range(nexp)]
        self.chars = []
        for i in range(nchars):
            ptr = self.u64(pchars + 8 * i)
            self.chars.append(self._char(i, ptr) if i else {"t": "filme", "off": p, "quadros": self.quadros_raiz})
        for imp in self.imports:
            k = imp["char"]
            if k < len(self.chars) and self.chars[k] is None:
                self.chars[k] = {"t": "import", "filme": imp["filme"], "nome": imp["nome"]}

    # ---------------------------------------------------------- edição (no lugar: nada muda de tamanho)
    def editar_place(self, off, m=None, tx=None, tint=None, soma=None):
        if self.u64(off) != 3:
            raise ErroApt("Posição de PlaceObject inválida")
        fl = self.u32(off + 8)
        if m is not None:
            struct.pack_into("<4f", self.d, off + 20, *m)
            fl |= F_MATRIZ
        if tx is not None:
            struct.pack_into("<2f", self.d, off + 36, *tx)
            fl |= F_MATRIZ
        if tint is not None:
            self.d[off + 44:off + 48] = bytes(int(max(0, min(255, round(v)))) for v in tint)
            fl |= F_COR
        if soma is not None:
            self.d[off + 48:off + 52] = bytes(int(max(0, min(255, round(v)))) for v in soma)
            fl |= F_COR
        struct.pack_into("<I", self.d, off + 8, fl)

    def editar_texto(self, char, limites=None, fonte=None, alinh=None, cor=None, altura=None):
        c = self.chars[char]
        if not c or c["t"] != "texto":
            raise ErroApt(f"O character {char} não é um texto")
        q = c["off"] + 32
        if limites is not None:
            struct.pack_into("<4f", self.d, q, *limites)
        if fonte is not None:
            if not (0 <= fonte < len(self.chars)) or not self.chars[fonte] or self.chars[fonte]["t"] != "fonte":
                raise ErroApt("Fonte inválida")
            struct.pack_into("<I", self.d, q + 16, fonte)
        if alinh is not None:
            struct.pack_into("<I", self.d, q + 20, int(alinh))
        if cor is not None:
            self.d[q + 24:q + 28] = bytes(int(max(0, min(255, round(v)))) for v in cor)
        if altura is not None:
            struct.pack_into("<f", self.d, q + 28, float(altura))

    def bytes(self):
        return bytes(self.d)


# ------------------------------------------------------------------ geometria

def ler_geometria(g):
    if len(g) < 16:
        return []
    tam, n, _z = struct.unpack_from("<3I", g, 0)
    if n > 10000:
        return []
    offs = struct.unpack_from("<%dI" % n, g, 12)
    itens = []
    for o in offs:
        isz, ityp = struct.unpack_from("<2I", g, o)
        if ityp != 1:
            itens.append({"k": -1, "off": o})
            continue
        kind = struct.unpack_from("<I", g, o + 0x14)[0]
        larg = struct.unpack_from("<f", g, o + 0x1C)[0]
        a, r, gg, b = g[o + 0x20:o + 0x24]
        img = struct.unpack_from("<i", g, o + 0x24)[0]
        mat = list(struct.unpack_from("<6f", g, o + 0x30))
        cnt, voff = struct.unpack_from("<2I", g, o + 0x48)
        base = o + 0x10 + voff
        v = []
        if kind == 3:   # linhas: segmentos de 2 pontos de 16 bytes
            for k in range(min(cnt * 2, 200000)):
                v += struct.unpack_from("<2f", g, base + 16 * k)
        else:
            for k in range(min(cnt * 3, 300000)):
                v += struct.unpack_from("<2f", g, base + 32 * k)
        itens.append({"k": kind, "off": o, "cor": [r, gg, b, a], "img": img if (kind != 2 and img > 0) else None,
                      "m": mat, "v": [round(x, 3) for x in v], "larg": larg})
    return itens


def editar_cor_geometria(g, item_off, cor):
    g = bytearray(g)
    r, gg, b, a = (int(max(0, min(255, round(x)))) for x in cor)
    g[item_off + 0x20:item_off + 0x24] = bytes((a, r, gg, b))
    return bytes(g)


def escalar_uv(g, img, sx, sy):
    """Ajusta as matrizes de textura dos itens que usam a imagem 'img' quando ela muda de tamanho."""
    g = bytearray(g)
    for it in ler_geometria(bytes(g)):
        if it["k"] in (0, 1) and it["img"] == img:
            a, b, c, d, tx, ty = it["m"]
            struct.pack_into("<6f", g, it["off"] + 0x30, a * sx, b * sy, c * sx, d * sy, tx * sx, ty * sy)
    return bytes(g)


# ------------------------------------------------------------------ DDS

def dds_info(d):
    if len(d) < 128 or d[:4] != b"DDS ":
        return None
    h, w = struct.unpack_from("<II", d, 12)
    fl = struct.unpack_from("<I", d, 80)[0]
    if fl & 4:
        fmt = d[84:88].decode("latin-1")
    else:
        fmt = "RGBA%d" % struct.unpack_from("<I", d, 88)[0]
    return {"w": w, "h": h, "fmt": fmt}


def dds_bgra(w, h, rgba):
    """DDS sem compressão (B8G8R8A8), o mesmo formato que vários overlays do jogo usam."""
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<7I", cab, 4, 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x8, h, w, w * 4, 0, 0)
    struct.pack_into("<2I", cab, 76, 32, 0x41)                  # tamanho do pixel format, RGB | ALPHAPIXELS
    struct.pack_into("<5I", cab, 84, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF)
    struct.pack_into("<I", cab, 104, 0xFF000000)
    struct.pack_into("<I", cab, 108, 0x1000)                    # TEXTURE
    px = bytearray(rgba)
    px[0::4], px[2::4] = rgba[2::4], rgba[0::4]                 # RGBA -> BGRA
    return bytes(cab) + bytes(px)


# ------------------------------------------------------------------ overlay inteiro (o .big)

class Overlay:
    """Um .big de overlay aberto: APT + geometrias + texturas, com o modelo para a interface."""

    def __init__(self, itens, marca=b"L286\x15\x05\x00\x00"):
        self.itens = list(itens)
        self.marca = marca
        self.ent = {n: d for n, d in self.itens}
        if "0" not in self.ent:
            raise ErroApt("Este .big não tem um APT (entrada 0)")
        self.apt = Apt(self.ent["0"])

    def entrada(self, nome):
        return self.ent.get(nome)

    def trocar_entrada(self, nome, dados):
        self.ent[nome] = dados
        for i, (n, _d) in enumerate(self.itens):
            if n == nome:
                self.itens[i] = (n, dados)
                return
        # entrada nova: texturas ficam antes do marcador sg2
        pos = next((i for i, (n, _) in enumerate(self.itens) if n == "sg2"), len(self.itens) - 1)
        self.itens.insert(pos, (nome, dados))

    def modelo(self):
        a = self.apt
        chars = []
        for i, c in enumerate(a.chars):
            if c is None:
                chars.append(None)
                continue
            m = {k: v for k, v in c.items() if k != "off"}
            if c["t"] == "forma":
                g = self.ent.get(str(c["geo"] + 1))
                m["itens"] = [{k: v for k, v in it.items()} for it in ler_geometria(g)] if g else []
                m["ent"] = str(c["geo"] + 1)
            elif c["t"] == "imagem":
                ent = str(c["tex"] + 1)
                m["ent"] = ent
                m.update(dds_info(self.ent.get(ent, b"")) or {"w": 0, "h": 0, "fmt": "?"})
            elif c["t"] == "fonte":
                pass
            chars.append(m)
        return {"w": a.largura, "h": a.altura, "mspf": a.mspf, "imports": a.imports, "exports": a.exports,
                "chars": chars}

    def aplicar(self, ops, imagens=None):
        """Aplica uma lista de operações (as edições da interface). 'imagens' traduz id -> (w, h, rgba)."""
        a = self.apt
        consts = None
        for op in ops:
            tipo = op.get("op")
            if tipo == "place":
                a.editar_place(int(op["off"]), op.get("m"), op.get("tx"), op.get("tint"), op.get("soma"))
            elif tipo == "texto":
                a.editar_texto(int(op["char"]), op.get("limites"), op.get("fonte"), op.get("alinh"), op.get("cor"), op.get("altura"))
            elif tipo == "cor_forma":
                c = a.chars[int(op["char"])]
                ent = str(c["geo"] + 1)
                self.trocar_entrada(ent, editar_cor_geometria(self.ent[ent], int(op["item"]), op["cor"]))
            elif tipo == "textura":
                i = int(op["char"])
                c = a.chars[i]
                if not c or c["t"] != "imagem":
                    raise ErroApt(f"O character {i} não é uma imagem")
                ent = str(c["tex"] + 1)
                antes = dds_info(self.ent.get(ent, b"")) or {"w": 0, "h": 0}
                w, h, rgba = imagens[op["img"]]
                self.trocar_entrada(ent, dds_bgra(w, h, rgba))
                if antes["w"] and antes["h"] and (antes["w"] != w or antes["h"] != h):
                    sx, sy = w / antes["w"], h / antes["h"]
                    for j, cj in enumerate(a.chars):
                        if cj and cj["t"] == "forma":
                            eg = str(cj["geo"] + 1)
                            if eg in self.ent:
                                self.trocar_entrada(eg, escalar_uv(self.ent[eg], i, sx, sy))
            elif tipo in ("const", "const_txt"):
                from . import as2
                if consts is None:
                    consts = as2.Constantes(self.ent["1"])
                slot = str(op["slot"])
                if slot.isdigit():
                    slot = "c:" + slot
                if tipo == "const":
                    as2.editar_numero(a.d, consts, slot, float(op["valor"]))
                else:
                    a.d = as2.editar_texto(a.d, consts, slot, str(op["texto"]))
            elif tipo == "fonte_char":
                c = a.chars[int(op["char"])]
                if not c or c["t"] != "fonte":
                    raise ErroApt("Esse character não é uma fonte")
                a.d += b"\0" * ((-len(a.d)) % 8)
                p_txt = len(a.d)
                a.d += str(op["nome"]).encode("latin-1") + b"\0"
                struct.pack_into("<Q", a.d, c["off"] + 32, p_txt)
            else:
                raise ErroApt(f"Operação desconhecida: {tipo}")
        if consts is not None:
            self.trocar_entrada("1", consts.bytes())
        self.trocar_entrada("0", a.bytes())

    def bytes(self):
        from . import big
        return big.gravar(self.itens, self.marca)
