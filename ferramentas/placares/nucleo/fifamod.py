"""Leitura de mods do FIFA Editor Tool (.fifamod, formato novo "FETM") — só leitura.

Layout (o mesmo que o FMT lê em FrostySdk.ModsAndProjects.FET.FIFAModReaderV2):
  "FETM", versão (u8), jogo, versão do jogo (u24), título, autor, categorias, versão, descrição, links, ícone,
  screenshots, locale.ini, initfs, lua, kit lua, base dos dados (u32), bundles, EBX, RES, chunks, coletores.
  Arquivos legacy são chunks com a flag IsLegacy (0x02) e trazem o caminho (ex.: data/ui/game/overlays/...).
  Os dados de cada recurso ficam em base + offset, em blocos do Frostbite (Oodle).
"""
import os
import struct
import uuid

from .jogo import ErroJogo, blocos


class _R:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def u16(self):
        v = struct.unpack_from("<H", self.b, self.p)[0]
        self.p += 2
        return v

    def u24(self):
        v = int.from_bytes(self.b[self.p:self.p + 3], "little")
        self.p += 3
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]
        self.p += 4
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.b, self.p)[0]
        self.p += 8
        return v

    def v7(self):
        n = s = 0
        while True:
            c = self.u8()
            n |= (c & 0x7F) << s
            s += 7
            if not c & 0x80:
                return n

    def s(self):
        n = self.v7()
        v = bytes(self.b[self.p:self.p + n]).decode("utf-8", "replace")
        self.p += n
        return v

    def pular(self, n):
        self.p += n

    def guid(self):
        v = str(uuid.UUID(bytes_le=bytes(self.b[self.p:self.p + 16])))
        self.p += 16
        return v


class Mod:
    def __init__(self, caminho):
        self.caminho = os.path.abspath(caminho)
        self.legacy = {}       # nome em minúsculas -> (nome, offset, tamanho comprimido)
        self.ebx = []
        self._ler_indice()

    def _ler_indice(self):
        with open(self.caminho, "rb") as f:
            cab = f.read(4)
            if cab != b"FETM":
                raise ErroJogo("Este arquivo não é um .fifamod do FIFA Editor Tool (formato novo).")
            f.seek(0)
            # o índice vem antes dos dados; lemos em pedaços crescentes até caber
            tam = 4 << 20
            while True:
                f.seek(0)
                b = f.read(tam)
                try:
                    self._parse(b)
                    return
                except (IndexError, struct.error):
                    if len(b) < tam:
                        raise ErroJogo("Arquivo .fifamod incompleto ou corrompido.")
                    tam *= 4

    def _parse(self, b):
        r = _R(memoryview(b))
        r.u32()
        self.versao_mod = r.u8()
        self.jogo = r.s()
        r.u24()
        self.titulo = r.s()
        self.autor = r.s()
        r.u8()
        r.u8()
        self.categoria = r.s()
        self.subcategoria = r.s()
        self.versao = r.s()
        self.descricao = r.s()
        for _ in range(8):
            r.s()
        r.pular(r.v7())                 # ícone
        for _ in range(r.v7()):         # screenshots
            r.pular(r.v7())
        for _ in range(r.v7()):         # locale.ini
            r.s()
            r.s()
        for _ in range(r.v7()):         # initfs
            r.s()
            r.pular(r.v7())
        for _ in range(2):              # lua e kit lua
            for _ in range(r.v7()):
                r.s()
                for _ in range(r.v7()):
                    r.s()
        base = r.u32()
        for _ in range(r.u24()):        # bundles adicionados
            r.s()
            r.pular(12)
        ebx = []
        for _ in range(r.u24()):
            nome = r.s()
            fl = r.u8()
            r.pular(20)
            off = r.v7()
            ln = r.v7()
            r.v7()
            if fl & 4:
                r.u32()
                r.s()
                if fl & 0x40:
                    r.s()
            if fl & 0x10:
                r.pular(8 * r.v7())
            ebx.append((nome, base + off, ln))
        for _ in range(r.u24()):        # res
            r.s()
            r.u8()
            r.pular(20)
            r.v7()
            r.v7()
            r.v7()
            r.pular(8 * r.v7())
            r.pular(4 + 8 + 16)
        legacy = {}
        for _ in range(r.u24()):        # chunks
            r.pular(16 + 20)
            fl = r.u16()
            off = r.v7()
            ln = r.v7()
            if fl & 0x08:
                r.v7()
            if fl & 0x10:
                r.v7()
            if fl & 0x20:
                r.u64()
            nome = None
            if fl & 0x02:
                r.u64()
                nome = r.s()
            if fl & 0x80:
                r.pular(8 * r.v7())
            if fl & 0x04:
                r.u32()
            if nome:
                legacy[nome.lower().replace("\\", "/")] = (nome.replace("\\", "/"), base + off, ln)
        self.ebx = ebx
        self.legacy = legacy

    def existe(self, nome):
        return nome.lower().replace("\\", "/") in self.legacy

    def lista(self, prefixo=""):
        p = prefixo.lower()
        return sorted(v[0] for k, v in self.legacy.items() if k.startswith(p))

    def ler(self, nome, oodle):
        e = self.legacy.get(nome.lower().replace("\\", "/"))
        if e is None:
            raise ErroJogo(f"Arquivo não encontrado no mod: {nome}")
        with open(self.caminho, "rb") as f:
            f.seek(e[1])
            dados = f.read(e[2])
        return blocos(dados, oodle)

    def info(self):
        return {"titulo": self.titulo, "autor": self.autor, "versao": self.versao, "categoria": self.categoria,
                "subcategoria": self.subcategoria, "arquivos": len(self.legacy), "ebx": len(self.ebx)}
