"""Leitor dos placares do PES 2021: os .bin de common/menu/licence (game2dPes.bin, game2dPesEnter.bin…).

Cada .bin é um pacote com um arquivo .apk dentro, e o .apk é um TXP2 da Konami (big-endian): texturas (TXDT, comprimidas
com LZSS), recortes das texturas com nome ("game2dPes-score-plateMain"…), formas vetoriais (GE2D) e as animações AFP
(o "Flash" da Konami: sprites, objetos colocados com matriz e cor, quadros). O formato foi descrito pelo projeto
bemaniutils (DragonMinded, domínio público); este leitor faz só a parte que o PES usa.

Uso direto:  python afp.py <arquivo.bin> [pasta de saída]   (lista os filmes e grava as texturas em PNG)
"""
import io
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw


class ErroAfp(Exception):
    pass


# ------------------------------------------------------------------ compressão e texturas

def lzss(src, tamanho):
    """LZSS clássico (janela de 4096, início em 0xFEE, bit 1 = literal), o 'legacy lz' do TXP2."""
    anel = bytearray(4096)
    r = 0xFEE
    out = bytearray()
    i = 0
    bandeiras = 0
    n = len(src)
    while len(out) < tamanho and i < n:
        bandeiras >>= 1
        if not bandeiras & 0x100:
            bandeiras = src[i] | 0xFF00
            i += 1
        if bandeiras & 1:
            c = src[i]
            i += 1
            out.append(c)
            anel[r] = c
            r = (r + 1) & 0xFFF
        else:
            if i + 1 >= n:
                break
            b1, b2 = src[i], src[i + 1]
            i += 2
            pos = b1 | ((b2 & 0xF0) << 4)
            for k in range((b2 & 0xF) + 3):
                c = anel[(pos + k) & 0xFFF]
                out.append(c)
                anel[r] = c
                r = (r + 1) & 0xFFF
    return bytes(out)


def _dds_dxt(w, h, fourcc, dados):
    cab = struct.pack("<4sIIIIIII44xII4sIIIIIIIIII", b"DDS ", 124, 0x81007, h, w, len(dados), 0, 1, 32, 4, fourcc,
                      0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0)
    im = Image.open(io.BytesIO(cab + dados))
    im.load()
    return im.convert("RGBA")


def tdxt(dados):
    """Textura TXDT (cabeçalho de 64 bytes): 0x15 = ARGB 8 bits, 0x1A = DXT5."""
    if dados[:4] not in (b"TXDT", b"TDXT"):
        raise ErroAfp("Textura sem o cabeçalho TXDT")
    w, h = struct.unpack(">HH", dados[0x10:0x14])
    fmt = dados[0x17]
    px = dados[0x40:]
    if fmt == 0x15:
        a = np.frombuffer(px[:w * h * 4], np.uint8).reshape(h, w, 4)[:, :, [1, 2, 3, 0]]
        return Image.fromarray(np.ascontiguousarray(a), "RGBA")
    if fmt == 0x1A:
        return _dds_dxt(w, h, b"DXT5", px[:((w + 3) // 4) * ((h + 3) // 4) * 16])
    if fmt == 0x18:
        return _dds_dxt(w, h, b"DXT1", px[:((w + 3) // 4) * ((h + 3) // 4) * 8])
    raise ErroAfp(f"Formato de textura 0x{fmt:02x} ainda não suportado")


# ------------------------------------------------------------------ formas (GE2D)

class Forma:
    """Forma vetorial: pontos, triângulos e cor (o PES usa para retângulos e cantos arredondados)."""

    def __init__(self, nome, d):
        self.nome = nome
        if d[:4] != b"GE2D":
            raise ErroAfp(f"Forma {nome} sem GE2D")
        nv, nt, nc, nl, nr, _ = struct.unpack(">HHHHHH", d[20:32])
        ov, ot, oc, ol, orr = struct.unpack(">IIIII", d[32:52])
        self.pontos = [struct.unpack(">ff", d[ov + 8 * k:ov + 8 * k + 8]) for k in range(nv)] if ov else []
        self.uv = [struct.unpack(">ff", d[ot + 8 * k:ot + 8 * k + 8]) for k in range(nt)] if ot else []
        rotulos = []
        for k in range(nl if ol else 0):
            p = struct.unpack(">I", d[ol + 4 * k:ol + 4 * k + 4])[0]
            rotulos.append(d[p:d.index(b"\0", p)].decode("latin-1"))
        self.partes = []
        for k in range(nr if orr else 0):
            modo, fl, t1, _t2, ntri, _u, rgba, otri = struct.unpack(">BBBBHHII", d[orr + 16 * k:orr + 16 * k + 16])
            tri = list(struct.unpack(f">{ntri}H", d[otri:otri + 2 * ntri])) if ntri else []
            cor = ((rgba >> 24) & 255, (rgba >> 16) & 255, (rgba >> 8) & 255, rgba & 255)
            self.partes.append({"flags": fl, "regiao": rotulos[t1] if fl & 2 and t1 < len(rotulos) else None,
                                "tri": tri, "cor": cor if fl & 8 else None})


# ------------------------------------------------------------------ o pacote TXP2

def _namp(d, o):
    if not o or d[o:o + 4] != b"NAMP":
        return {}
    n, eo = struct.unpack(">I", d[o + 16:o + 20])[0], struct.unpack(">I", d[o + 24:o + 28])[0]
    r = {}
    for k in range(n):
        _h, i, no = struct.unpack(">III", d[eo + 12 * k:eo + 12 * k + 12])
        r[i] = d[no:d.index(b"\0", no)].decode("latin-1")
    return r


class Pacote:
    """Um .bin do PES aberto: texturas, recortes com nome, formas e filmes AFP."""

    def __init__(self, caminho, cache=None):
        """'cache': pasta onde guardar as texturas já descomprimidas (PNG), para abrir de novo na hora."""
        self.caminho = caminho
        self.cache = cache
        raw = open(caminho, "rb").read()
        d = self._achar_txp2(raw)
        self.d = d
        mascara = struct.unpack(">I", d[20:24])[0]
        self.mascara = mascara
        p = 24
        tab = {}

        def u32():
            nonlocal p
            v = struct.unpack(">I", d[p:p + 4])[0]
            p += 4
            return v
        # mesma ordem dos bits do cabeçalho do TXP2
        for bit, campos in ((0x1, 2), (0x2, 1), (0x8, 2), (0x10, 1), (0x40, 2), (0x80, 1), (0x100, 2), (0x200, 1),
                            (0x400, 1), (0x800, 2), (0x1000, 1), (0x2000, 2), (0x4000, 1), (0x8000, 1),
                            (0x10000, 1), (0x20000, 1)):
            if mascara & bit:
                tab[bit] = tuple(u32() for _ in range(campos))
        self._tab = tab
        self.legado_lz = bool(mascara & 0x4)
        # texturas: só a lista; a imagem é decodificada quando alguém pede
        self.texturas = []
        n, o = tab.get(0x1, (0, 0))
        for k in range(n):
            no, tam, off = struct.unpack(">III", d[o + 12 * k:o + 12 * k + 12])
            self.texturas.append({"nome": self._txt(no), "tam": tam, "off": off})
        self._imgs = {}
        self.regioes = []
        n, o = tab.get(0x8, (0, 0))
        nomes = _namp(d, tab.get(0x10, (0,))[0])
        for k in range(n):
            t, x0, y0, x1, y1 = struct.unpack(">HHHHH", d[o + 10 * k:o + 10 * k + 10])
            # as coordenadas dos recortes ficam em dobro (o jogo divide por 2 ao carregar)
            self.regioes.append({"nome": nomes.get(k, f"regiao{k}"), "tex": t,
                                 "x0": x0 / 2, "y0": y0 / 2, "x1": x1 / 2, "y1": y1 / 2})
        self.regiao_por_nome = {r["nome"]: r for r in self.regioes}
        self.formas = {}
        n, o = tab.get(0x2000, (0, 0))
        for k in range(n):
            no, tam, off = struct.unpack(">III", d[o + 12 * k:o + 12 * k + 12])
            nome = self._txt(no)
            try:
                self.formas[nome] = Forma(nome, d[off:off + tam])
            except (ErroAfp, struct.error, ValueError, IndexError):
                pass
        self.filmes = []
        n, o = tab.get(0x800, (0, 0))
        bsi = tab.get(0x20000, (0,))[0]
        for k in range(n):
            no, tam, off = struct.unpack(">III", d[o + 12 * k:o + 12 * k + 12])
            desc = b""
            if bsi:
                _z, tl, to = struct.unpack(">III", d[bsi + 12 * k:bsi + 12 * k + 12])
                desc = d[to:to + tl]
            self.filmes.append({"nome": self._txt(no), "dados": d[off:off + tam], "bsi": desc, "swf": None})

    @staticmethod
    def _achar_txp2(raw):
        if raw[:4] == b"TXP2":
            return raw
        # pacote do PES: contagem, e para cada arquivo (tamanho do cabeçalho, deslocamento, tamanho, nome)
        if len(raw) >= 16:
            n, _x, off, tam = struct.unpack("<IIII", raw[:16])
            if 0 < n < 64 and raw[off:off + 4] == b"TXP2":
                return raw[off:off + tam]
        i = raw.find(b"TXP2")
        if i < 0:
            raise ErroAfp("Não achei um TXP2 (placar do PES) neste arquivo")
        tam = struct.unpack(">I", raw[i + 12:i + 16])[0]
        return raw[i:i + tam]

    def _txt(self, o):
        d = self.d
        return d[o:d.index(b"\0", o)].decode("latin-1") if o else ""

    def textura(self, i):
        if i not in self._imgs:
            t = self.texturas[i]
            arq = None
            if self.cache:
                import hashlib
                st = os.stat(self.caminho)
                chave = "%s|%d|%d|%d" % (os.path.abspath(self.caminho).lower(), st.st_size, int(st.st_mtime), i)
                arq = os.path.join(self.cache, hashlib.sha1(chave.encode("utf-8")).hexdigest()[:24] + ".png")
                if os.path.isfile(arq):
                    try:
                        im = Image.open(arq)
                        im.load()
                        self._imgs[i] = im.convert("RGBA")
                        return self._imgs[i]
                    except OSError:
                        pass
            d = self.d
            cheio, comp = struct.unpack(">II", d[t["off"]:t["off"] + 8])
            corpo = d[t["off"] + 8:t["off"] + 8 + comp]
            bruto = lzss(corpo, cheio) if self.legado_lz and comp < cheio else d[t["off"] + 8:t["off"] + 8 + cheio]
            self._imgs[i] = tdxt(bruto)
            if arq:
                try:
                    os.makedirs(self.cache, exist_ok=True)
                    self._imgs[i].save(arq + ".tmp", "PNG", compress_level=1)
                    os.replace(arq + ".tmp", arq)
                except OSError:
                    pass
        return self._imgs[i]

    def recorte(self, nome):
        """A imagem de um recorte com nome (sem margem), ou None."""
        r = self.regiao_por_nome.get(nome)
        if not r:
            return None
        return self.textura(r["tex"]).crop((int(r["x0"]), int(r["y0"]), int(round(r["x1"])), int(round(r["y1"]))))

    def filme(self, nome):
        for f in self.filmes:
            if f["nome"] == nome:
                if f["swf"] is None:
                    f["swf"] = Filme(f["nome"], f["dados"], f["bsi"])
                return f["swf"]
        return None


# ------------------------------------------------------------------ o filme AFP (SWF da Konami)

def _desembaralhar(dados, info):
    """O BSI diz quais trechos inverter (2, 4 ou 8 bytes): deixa o filme em little-endian."""
    d = bytearray(dados)
    pos = 0
    for i in range(0, len(info) - 1, 2):
        w = struct.unpack("<H", info[i:i + 2])[0]
        if w == 0:
            break
        pos += (w & 0x7F) * 2
        tipo = (w >> 13) & 7
        voltas = (w >> 7) & 0x3F
        if tipo == 0:
            pos += 256 * voltas
            continue
        n = {1: 2, 2: 4, 3: 8}.get(tipo)
        if not n:
            raise ErroAfp(f"BSI com tipo {tipo} desconhecido")
        for _ in range(voltas + 1):
            d[pos:pos + n] = d[pos:pos + n][::-1]
            pos += n
    return bytes(d)


# ids das tags AP2
T_FONTE, T_SPRITE, T_ACAO, T_TEXTO, T_EDIT, T_PLACE, T_REMOVE, T_IMAGEM, T_FORMA = (
    0x78, 0x79, 0x7A, 0x7D, 0x7E, 0x7F, 0x80, 0x83, 0x84)


class Filme:
    def __init__(self, nome, dados, bsi):
        self.nome = nome
        d = _desembaralhar(dados, bsi) if bsi else dados
        magia, tam, versao, p_nome, flags, esq, dir_, topo, base = struct.unpack("<4sIHHIHHHH", d[:24])
        if bytes([magia[3] & 0x7F, magia[2] & 0x7F, magia[1] & 0x7F]) != b"AP2":
            raise ErroAfp(f"Filme {nome}: não é AP2")
        self.d = d
        self.versao = magia[0]
        self.largura, self.altura = dir_ - esq, base - topo
        self.fps = struct.unpack("<i", d[24:28])[0] / 1024.0 if flags & 2 else struct.unpack("<f", d[24:28])[0]
        st_off, st_tam = struct.unpack("<II", d[48:56])
        self._strings = {}
        b = bytearray(d)
        soma = 128
        ini = 0
        atual = []
        for i in range(st_tam):
            c = (b[st_off + i] - soma) & 0xFF
            soma += 1
            if c == 0:
                if atual:
                    self._strings[ini] = bytes(atual).decode("utf-8", "replace")
                atual = []
                ini = i + 1
            else:
                atual.append(c)
        self.nome_exportado = self.s(p_nome)
        n_exp, = struct.unpack("<H", d[32:34])
        p_exp, = struct.unpack("<I", d[40:44])
        self.exportados = {}
        for k in range(n_exp):
            tid, so = struct.unpack("<HH", d[p_exp + 4 * k:p_exp + 4 * k + 4])
            self.exportados[self.s(so)] = tid
        raiz, = struct.unpack("<I", d[36:40])
        self.tags, self.quadros, self.rotulos = self._tags(raiz)

    def s(self, o):
        return self._strings.get(o, "") if o else ""

    def _tags(self, base):
        d = self.d
        _fl, nrot, nq, ntag, orot, oq, otag = struct.unpack("<HHIIIII", d[base:base + 24])
        quadros = []
        for k in range(nq):
            v, = struct.unpack("<I", d[base + oq + 4 * k:base + oq + 4 * k + 4])
            quadros.append((v & 0xFFFFF, (v >> 20) & 0xFFF))
        tags = []
        p = base + otag
        for _ in range(ntag):
            v, = struct.unpack("<I", d[p:p + 4])
            tid, tam = (v >> 22) & 0x3FF, v & 0x3FFFFF
            tags.append(self._tag(tid, tam, p + 4))
            p += ((tam + 3) & ~3) + 4
        rotulos = {}
        for k in range(nrot):
            q, so = struct.unpack("<HH", d[base + orot + 4 * k:base + orot + 4 * k + 4])
            rotulos[self.s(so)] = q
        return tags, quadros, rotulos

    def _tag(self, tid, tam, o):
        d = self.d
        if tid == T_FORMA:
            _u, sid = struct.unpack("<HH", d[o:o + 4])
            return {"t": "forma", "id": sid, "ref": f"{self.nome_exportado}_shape{sid}"}
        if tid == T_IMAGEM:
            fl, iid, so = struct.unpack("<IHH", d[o:o + 8])
            nome = self.s(so)
            return {"t": "imagem", "id": iid, "ref": ("SWFA-" + nome) if fl & 2 else nome}
        if tid == T_SPRITE:
            fl, sid = struct.unpack("<HH", d[o:o + 4])
            sub = o + 4 if not fl & 1 else struct.unpack("<I", d[o + 4:o + 8])[0] + o
            tags, quadros, rotulos = self._tags(sub)
            return {"t": "sprite", "id": sid, "tags": tags, "quadros": quadros, "rotulos": rotulos}
        if tid == T_PLACE:
            try:
                return self._place(d[o:o + tam])
            except struct.error:
                # raro (2 de ~9.000 nos placares testados): combinação de bits que este leitor não conhece
                return {"t": "outra", "tag": tid}
        if tid == T_REMOVE:
            oid, prof = struct.unpack("<HH", d[o:o + 4])
            return {"t": "remove", "id": oid, "prof": prof}
        if tid == T_EDIT:
            fl, eid, fonte, altura, _s2 = struct.unpack("<IHHHH", d[o:o + 12])
            rgba, f1, f2, f3, f4, var, padrao = struct.unpack("<IiiiiHH", d[o + 20:o + 44])
            return {"t": "texto", "id": eid, "fonte": fonte, "altura": altura,
                    "ret": (f1 / 20, f2 / 20, f3 / 20, f4 / 20),
                    "cor": (rgba & 255, (rgba >> 8) & 255, (rgba >> 16) & 255, (rgba >> 24) & 255),
                    "var": self.s(var), "padrao": self.s(padrao) if fl & 0x80 else ""}
        if tid == T_ACAO:
            return {"t": "acao", "bytes": d[o:o + tam]}
        return {"t": "outra", "tag": tid}

    def _place(self, c):
        fl, prof, oid = struct.unpack("<IHH", c[:8])
        p = 8
        if fl & 0x80000000:
            fl |= struct.unpack("<I", c[p:p + 4])[0] << 32
            p += 4
        r = {"t": "place", "prof": prof, "id": oid, "atualiza": bool(fl & 1), "fonte": None, "nome": None,
             "matriz": None, "mult": None, "soma": None, "blend": None, "origem": None}
        if fl & 0x2:
            r["fonte"], = struct.unpack("<H", c[p:p + 2])
            p += 2
        if fl & 0x10:
            p += 2
        if fl & 0x20:
            r["nome"] = self.s(struct.unpack("<H", c[p:p + 2])[0])
            p += 2
        if fl & 0x40:
            p += 2
        if fl & 0x20000:
            r["blend"] = c[p]
            p += 1
        p = (p + 3) & ~3
        a, b, cc, dd, tx, ty = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
        tem_escala = tem_rot = False
        if fl & 0x100:
            ai, di = struct.unpack("<ii", c[p:p + 8])
            a, dd = ai / 1024, di / 1024
            p += 8
            tem_escala = True
        if fl & 0x200:
            bi, ci = struct.unpack("<ii", c[p:p + 8])
            b, cc = bi / 1024, ci / 1024
            p += 8
            tem_rot = True
        if fl & 0x400:
            txi, tyi = struct.unpack("<ii", c[p:p + 8])
            tx, ty = txi / 20, tyi / 20
            p += 8
        mult = [1.0, 1.0, 1.0, 1.0]
        soma = [0.0, 0.0, 0.0, 0.0]
        if fl & 0x800:
            mult = [v / 255 for v in struct.unpack("<hhhh", c[p:p + 8])]
            p += 8
        if fl & 0x1000:
            soma = [v / 255 for v in struct.unpack("<hhhh", c[p:p + 8])]
            p += 8
        if fl & 0x2000:
            v, = struct.unpack("<I", c[p:p + 4])
            mult = [((v >> 24) & 255) / 255, ((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255]
            p += 4
        if fl & 0x4000:
            v, = struct.unpack("<I", c[p:p + 4])
            soma = [((v >> 24) & 255) / 255, ((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255]
            p += 4
        if fl & 0x80:
            _ef, tam_ev = struct.unpack("<II", c[p:p + 8])
            p += tam_ev
        if fl & 0x10000:
            _n, tam_f = struct.unpack("<HH", c[p:p + 4])
            p += tam_f
        if fl & 0x1000000:
            ox, oy = struct.unpack("<ii", c[p:p + 8])
            r["origem"] = (ox / 20, oy / 20)
            p += 8
        if fl & 0x200000000:
            p += 4
        if fl & 0x40000 and p < len(c):
            ai, di = struct.unpack("<hh", c[p:p + 4])
            a, dd = ai / 32768, di / 32768
            p += 4
            tem_escala = True
        if fl & 0x80000:
            bi, ci = struct.unpack("<hh", c[p:p + 4])
            b, cc = bi / 32768, ci / 32768
            p += 4
            tem_rot = True
        if fl & 0x100000:
            p += 2
        p = (p + 3) & ~3
        if fl & 0x8000000:
            p += 4
        if fl & 0x10000000:
            m = [v / 1024 for v in struct.unpack("<9i", c[p:p + 36])]
            if not tem_escala:
                a, dd = m[0], m[4]
            if not tem_rot:
                b, cc = m[1], m[3]
            p += 36
        if fl & (0x18000004 | 0x4000000):
            r["matriz"] = (a, b, cc, dd, tx, ty)
        if fl & 0x8:
            r["mult"], r["soma"] = mult, soma
        return r


# ------------------------------------------------------------------ montar a cena (sem rodar o código das ações)

def _mul(m, n):
    """Aplica m e depois n (convenção do Flash: x' = a·x + c·y + tx, y' = b·x + d·y + ty)."""
    a, b, c, d, tx, ty = m
    A, B, C, D, TX, TY = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, tx * A + ty * C + TX, tx * B + ty * D + TY)


IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


# ordem de preferência dos rótulos para "o placar aparecendo normal": ligado, entrada terminada, logo do PES, relógio com
# dois dígitos nos minutos ("time_disit_2", com o erro de digitação da Konami)
_PREFERIDOS = (("on",), ("_on",), ("show", "_show"), ("_usual",), ("_pes",), ("_disit_2", "_digit_2"))


def quadro_exibido(rotulos, n_quadros):
    """Quadro em que um clipe com rótulos fica 'aparecendo parado' (o jogo pula para esses rótulos por código).

    Usa o fim do trecho do rótulo preferido (o quadro antes do rótulo seguinte). Rótulos do modo transparente (quando um
    jogador passa por trás do placar) são ignorados; clipes de dígitos e outros rótulos ficam no primeiro quadro.
    """
    if not rotulos:
        return None
    validos = {n: q for n, q in rotulos.items() if "transparent" not in n.lower()}
    for sufixos in _PREFERIDOS:
        for nome, q in sorted(validos.items(), key=lambda kv: kv[1]):
            if any(nome == s or (s.startswith("_") and nome.endswith(s)) for s in sufixos):
                depois = [v for v in rotulos.values() if v > q]
                return (min(depois) - 1) if depois else n_quadros - 1
    return 0


class Cena:
    """Executa a linha do tempo de um filme e devolve as peças visíveis já na posição da tela.

    O código das ações não é rodado: cada clipe com rótulos fica no quadro em que aparece parado (quadro_exibido), os
    outros andam um quadro por quadro do pai (como no Flash) e param no último. 'quadros' força o quadro de um clipe
    pelo nome com que foi colocado: um número ({"mainGroup": 60}) ou um rótulo ({"losstime": "_off"}).
    """

    def __init__(self, filme, achar_recorte=None):
        self.f = filme
        self.achar_recorte = achar_recorte
        self.defs = {}
        self._registrar(filme.tags)

    def _registrar(self, tags):
        for t in tags:
            if t["t"] in ("forma", "imagem", "sprite", "texto"):
                self.defs.setdefault(t["id"], t)
                if t["t"] == "sprite":
                    self._registrar(t["tags"])

    def _rodar(self, tags, quadros, ate):
        """Estado da lista de exibição de um clipe após 'ate' quadros: {profundidade: objeto}."""
        lista = {}
        for q in range(min(ate, len(quadros) - 1) + 1):
            ini, n = quadros[q]
            for t in tags[ini:ini + n]:
                if t["t"] == "place":
                    ant = lista.get(t["prof"])
                    if t["atualiza"] and ant:
                        if t["fonte"] is not None and t["fonte"] != ant["fonte"]:
                            ant = dict(ant, fonte=t["fonte"], nasc=q)
                        else:
                            ant = dict(ant)
                        for k in ("matriz", "mult", "soma", "blend", "origem"):
                            if t[k] is not None:
                                ant[k] = t[k]
                        if t["nome"]:
                            ant["nome"] = t["nome"]
                        lista[t["prof"]] = ant
                    elif t["fonte"] is not None:
                        lista[t["prof"]] = {"fonte": t["fonte"], "matriz": t["matriz"] or IDENT,
                                            "mult": t["mult"] or [1, 1, 1, 1], "soma": t["soma"] or [0, 0, 0, 0],
                                            "blend": t["blend"] or 0, "nome": t["nome"], "nasc": q, "origem": t["origem"]}
                elif t["t"] == "remove":
                    lista.pop(t["prof"], None)
        return lista

    def pecas(self, quadros=None):
        """Peças visíveis em ordem de desenho: {tipo, ref, matriz (para o filme), mult, soma, caminho, ...}."""
        f = self.f
        out = []
        q = (quadros or {}).get("", quadro_exibido(f.rotulos, len(f.quadros)))
        self._achatar(f.tags, f.quadros, len(f.quadros) - 1 if q is None else q, IDENT, [1, 1, 1, 1], [0, 0, 0, 0],
                      [], out, quadros or {})
        return out

    def _achatar(self, tags, quadros, q, mat, mult, soma, caminho, out, forcar, nivel=0):
        if nivel > 24:
            return
        lista = self._rodar(tags, quadros, q)
        for prof in sorted(lista):
            o = lista[prof]
            m = o["matriz"] or IDENT
            if o.get("origem"):
                ox, oy = o["origem"]
                m = _mul((1, 0, 0, 1, -ox, -oy), m)
            mm = _mul(m, mat)
            # cor do filho primeiro, depois a do pai
            mu = [mult[i] * o["mult"][i] for i in range(4)]
            so = [o["soma"][i] * mult[i] + soma[i] for i in range(4)]
            dfn = self.defs.get(o["fonte"])
            if not dfn:
                continue
            nome = o.get("nome") or ""
            cam = caminho + [nome or f"#{o['fonte']}"]
            if dfn["t"] == "sprite":
                if nome in forcar:
                    qq = forcar[nome]
                    if isinstance(qq, str):     # pelo rótulo (basta o fim do nome: "_off")
                        qq = next((v for k, v in dfn["rotulos"].items() if k == qq or k.endswith(qq)), 0)
                else:
                    qq = quadro_exibido(dfn["rotulos"], len(dfn["quadros"]))
                    if qq is None:
                        qq = q - o.get("nasc", 0)
                self._achatar(dfn["tags"], dfn["quadros"], max(0, qq), mm, mu, so, cam, out, forcar, nivel + 1)
            else:
                out.append({"tipo": dfn["t"], "ref": dfn.get("ref") or dfn.get("var") or "", "def": dfn,
                            "matriz": mm, "mult": mu, "soma": so, "caminho": cam, "prof": prof,
                            "blend": o.get("blend") or 0})
        return out


# ------------------------------------------------------------------ desenhar

def _desenhar_textura(tela, tex, m, mult, soma, x0=0.0, y0=0.0, escala=1.0):
    """Cola 'tex' (PIL RGBA) na tela (numpy float HxWx4, pré-multiplicado não) pela matriz m."""
    a, b, c, d, tx, ty = m
    tw, th = tex.size
    cantos = [(x0, y0), (x0 + tw * escala, y0), (x0, y0 + th * escala), (x0 + tw * escala, y0 + th * escala)]
    pts = [(a * x + c * y + tx, b * x + d * y + ty) for x, y in cantos]
    H, W = tela.shape[:2]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bx0, by0 = max(0, int(np.floor(min(xs)))), max(0, int(np.floor(min(ys))))
    bx1, by1 = min(W, int(np.ceil(max(xs)))), min(H, int(np.ceil(max(ys))))
    if bx1 <= bx0 or by1 <= by0:
        return
    det = a * d - b * c
    if abs(det) < 1e-9:
        return
    # inversa: tela -> coordenadas locais -> pixel da textura
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    itx = -(tx * ia + ty * ic)
    ity = -(tx * ib + ty * id_)
    lx = lambda X, Y: ((X * ia + Y * ic + itx) - x0) / escala  # noqa: E731
    ly = lambda X, Y: ((X * ib + Y * id_ + ity) - y0) / escala  # noqa: E731
    # matriz afim para o PIL (saída -> entrada), na caixa recortada
    coef = (ia / escala, ic / escala, lx(bx0, by0), ib / escala, id_ / escala, ly(bx0, by0))
    parte = tex.transform((bx1 - bx0, by1 - by0), Image.AFFINE, coef, resample=Image.BILINEAR)
    src = np.asarray(parte, np.float32) / 255.0
    rgb = np.clip(src[..., :3] * np.array(mult[:3], np.float32) + np.array(soma[:3], np.float32), 0, 1)
    al = np.clip(src[..., 3:4] * mult[3] + soma[3], 0, 1)
    dst = tela[by0:by1, bx0:bx1]
    da = dst[..., 3:4]
    oa = al + da * (1 - al)
    with np.errstate(invalid="ignore", divide="ignore"):
        orgb = np.where(oa > 0, (rgb * al + dst[..., :3] * da * (1 - al)) / np.maximum(oa, 1e-6), 0)
    dst[..., :3] = orgb
    dst[..., 3:4] = oa


class Biblioteca:
    """Os .bin de um placar juntos: um filme de um arquivo usa recortes de outros (o logo fica no licenceTexturePes)."""

    def __init__(self, pacotes):
        self.pacotes = list(pacotes)

    def _chaves(self, nome):
        yield nome
        yield nome.replace("_", "-")
        # 'hudTexPes_logo_1' -> 'hudTexPes-logo-1'; 'game2dPes_score_plateMain' -> 'game2dPes-score-plateMain'
        partes = nome.split("_")
        if len(partes) > 1:
            yield "-".join(partes)

    def regiao(self, nome):
        for k in self._chaves(nome):
            for pk in self.pacotes:
                if k in pk.regiao_por_nome:
                    return pk, k
        return None, None

    def recorte(self, nome):
        pk, k = self.regiao(nome)
        return pk.recorte(k) if pk else None

    def forma(self, nome):
        for pk in self.pacotes:
            if nome in pk.formas:
                return pk.formas[nome]
        return None

    def filme(self, nome):
        for pk in self.pacotes:
            f = pk.filme(nome)
            if f:
                return f
        return None

    def filmes(self):
        return [(pk, f["nome"]) for pk in self.pacotes for f in pk.filmes]


def caixa(bib, p):
    """Retângulo (x0, y0, x1, y1) de uma peça na tela do filme, ou None."""
    a, b, c, d, tx, ty = p["matriz"]
    if p["tipo"] == "imagem":
        pk, k = bib.regiao(p["ref"])
        if not pk:
            return None
        r = pk.regiao_por_nome[k]
        cantos = [(0, 0), (r["x1"] - r["x0"], 0), (0, r["y1"] - r["y0"]), (r["x1"] - r["x0"], r["y1"] - r["y0"])]
    elif p["tipo"] == "forma":
        fo = bib.forma(p["ref"])
        if not fo or not fo.pontos:
            return None
        xs = [x for x, _ in fo.pontos]
        ys = [y for _, y in fo.pontos]
        cantos = [(min(xs), min(ys)), (max(xs), min(ys)), (min(xs), max(ys)), (max(xs), max(ys))]
    elif p["tipo"] == "texto":
        x0, x1, y0, y1 = p["def"]["ret"]
        cantos = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    else:
        return None
    pts = [(a * x + c * y + tx, b * x + d * y + ty) for x, y in cantos]
    return (min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts))


def inversa(m):
    a, b, c, d, tx, ty = m
    det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(tx * ia + ty * ic), -(tx * ib + ty * id_))


def ponto(m, x, y):
    a, b, c, d, tx, ty = m
    return a * x + c * y + tx, b * x + d * y + ty


def desenhar(bib, pecas, largura, altura, origem=(0.0, 0.0), escala=1.0, fundo=None, esconder=(), formas=True,
             ajuste=None):
    """Desenha as peças numa imagem largura x altura; 'origem' é o ponto do filme que vai no canto (0, 0).

    'ajuste' (matriz filme -> imagem) substitui origem/escala.
    """
    tela = np.zeros((altura, largura, 4), np.float32)
    if fundo is not None:
        tela[:] = np.array(fundo, np.float32) / 255.0
    if ajuste is None:
        ajuste = (escala, 0.0, 0.0, escala, -origem[0] * escala, -origem[1] * escala)
    for p in pecas:
        if any(e in p["caminho"] for e in esconder):
            continue
        m = _mul(p["matriz"], ajuste)
        if p["tipo"] == "imagem":
            img = bib.recorte(p["ref"])
            if img is not None:
                _desenhar_textura(tela, img, m, p["mult"], p["soma"])
        elif p["tipo"] == "forma" and formas:
            fo = bib.forma(p["ref"])
            if not fo or not fo.pontos:
                continue
            xs = [x for x, _ in fo.pontos]
            ys = [y for _, y in fo.pontos]
            for parte in fo.partes:
                if not parte["flags"] & 1 or not parte["cor"] or parte["cor"][3] == 0:
                    continue
                w, h = max(1, int(np.ceil(max(xs) - min(xs)))), max(1, int(np.ceil(max(ys) - min(ys))))
                loc = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                dr = ImageDraw.Draw(loc)
                tri = parte["tri"]
                for k in range(0, len(tri) - 2, 3):
                    dr.polygon([(fo.pontos[i][0] - min(xs), fo.pontos[i][1] - min(ys)) for i in tri[k:k + 3]],
                               fill=parte["cor"])
                _desenhar_textura(tela, loc, m, p["mult"], p["soma"], x0=min(xs), y0=min(ys))
    return Image.fromarray((np.clip(tela, 0, 1) * 255).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ linha de comando (para inspecionar um .bin)

def _arvore(tags, nivel=0):
    for t in tags:
        if t["t"] == "sprite":
            print("  " * nivel + f"sprite {t['id']}: {len(t['quadros'])} quadros, rótulos {t['rotulos']}")
            _arvore(t["tags"], nivel + 1)
        elif t["t"] in ("imagem", "forma"):
            print("  " * nivel + f"{t['t']} {t['id']}: {t['ref']}")
        elif t["t"] == "texto":
            print("  " * nivel + f"texto {t['id']}: var={t['var']!r} padrão={t['padrao']!r} ret={t['ret']} altura={t['altura']}")
        elif t["t"] == "place" and not t["atualiza"]:
            print("  " * nivel + f"place prof {t['prof']} <- {t['fonte']} nome={t['nome']!r} m={t['matriz']}")


if __name__ == "__main__":
    pk = Pacote(sys.argv[1])
    print(f"{len(pk.texturas)} texturas, {len(pk.regioes)} recortes, {len(pk.formas)} formas, {len(pk.filmes)} filmes")
    for f in pk.filmes:
        fm = pk.filme(f["nome"])
        print(f"== {fm.nome} ({fm.nome_exportado}) {fm.largura}x{fm.altura} {fm.fps:g} fps, {len(fm.quadros)} quadros, "
              f"rótulos {fm.rotulos}")
        if len(sys.argv) > 3:
            _arvore(fm.tags, 1)
    if len(sys.argv) > 2:
        os.makedirs(sys.argv[2], exist_ok=True)
        for r in pk.regioes:
            im = pk.recorte(r["nome"])
            im.save(os.path.join(sys.argv[2], r["nome"] + ".png"))
