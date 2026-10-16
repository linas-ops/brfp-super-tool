"""Leitura e gravação dos arquivos de squad do FC 26 / FC 27 (Squads<data>, só biblioteca padrão).

Formato (little-endian):
  'FBCHUNKS', u16 1, u32 tam_cab (0x454), u32 tam_dados (= tamanho do arquivo - (0x12 + tam_cab)),
  nome no jogo (texto terminado em \\0) ... 'SaveType_Squads\\0', u32 crc, ..., u32 tam_resto, banco 'DB\\0\\x08', bloco final.
  crc = CRC-32 (zlib) de tudo a partir de tam_resto; tam_resto = tamanho do arquivo - início do banco.
Banco t3db (o mesmo dos fifa_ng_db.db, ver comum/dados.py), com três diferenças nos squads:
  - cada tabela tem capacidade (registros reservados, zerados no fim) maior que o número de registros válidos;
  - o byte baixo do campo n_campos do cabeçalho é a quantidade de campos; o bit 0x100 indica um bloco de chave depois
    dos registros: shortname da chave (4), u8 n_campos_chave, u8 1, u16 0, n x (u32 índice do campo, u32 1 = crescente);
  - flag 0x04 da tabela = registros em ordem pela chave.
Os textos são de tamanho fixo (tipo 0), em UTF-8.
"""
import os
import struct
import zlib

import dados  # comum/dados.py: ler_meta, crc32_t3db

TIPOS = {0: "string", 3: "int", 4: "real"}


class ErroSquad(Exception):
    pass


class Campo:
    __slots__ = ("tipo", "bitoff", "sn", "bits", "nome", "low", "high")

    def __init__(self, tipo, bitoff, sn, bits, m):
        self.tipo, self.bitoff, self.sn, self.bits = tipo, bitoff, sn, bits
        self.nome = m.get("nome", sn)
        self.low, self.high = m.get("low", 0), m.get("high", (1 << bits) - 1 + m.get("low", 0))


class Tabela:
    """Tabela de um squad: campos, chave e linhas (listas de int/float/str na ordem dos campos do arquivo)."""

    def __init__(self, nome, sn, hdr, campos, chave_sn, chave, bruto, ordem_offset):
        self.nome, self.sn, self.hdr, self.campos = nome, sn, hdr, campos
        self.chave_sn, self.chave = chave_sn, chave          # chave: índices dos campos
        self.bruto = bruto                                   # bytes originais (gravados de volta se não mudar)
        self.ordem_offset = ordem_offset
        self.idx = {c.nome: i for i, c in enumerate(campos)}
        self._linhas = None
        self.novas = None                                    # linhas trocadas (gravar)

    @property
    def capacidade(self):
        return self.hdr[4]

    @property
    def validos(self):
        return self.hdr[5]

    @property
    def ordenada(self):
        return bool(self.hdr[0] & 4)

    def col(self, nome):
        return self.idx.get(nome)

    @property
    def linhas(self):
        if self._linhas is None:
            self._linhas = self._decodificar()
        return self._linhas

    def _decodificar(self):
        b = self.bruto
        recsize, n = self.hdr[1], self.hdr[5]
        R = 36 + 16 * len(self.campos)
        ints = [(j, c.bitoff, (1 << c.bits) - 1, c.low) for j, c in enumerate(self.campos) if c.tipo == 3]
        reais = [(j, c.bitoff // 8) for j, c in enumerate(self.campos) if c.tipo == 4]
        textos = [(j, c.bitoff // 8, c.bits // 8) for j, c in enumerate(self.campos) if c.tipo == 0]
        nc = len(self.campos)
        fb = int.from_bytes
        out = []
        for r in range(n):
            p = R + recsize * r
            rec = b[p:p + recsize]
            v = fb(rec, "little")
            linha = [0] * nc
            for j, bo, mask, low in ints:
                linha[j] = ((v >> bo) & mask) + low
            for j, o in reais:
                linha[j] = struct.unpack_from("<f", rec, o)[0]
            for j, o, k in textos:
                linha[j] = rec[o:o + k].split(b"\0")[0].decode("utf-8", errors="replace")
            out.append(linha)
        return out

    def valor_chave(self, linha):
        """Ordem dos registros: o último campo da chave é o mais significativo (como o jogo grava)."""
        return tuple(linha[k] for k in reversed(self.chave))

    def segue_chave(self):
        """Se os registros originais estão na ordem da chave (teamplayerlinks e manager, por exemplo, não estão: o
        jogo grava na ordem do artificialkey). Tabela vazia conta como ordenada."""
        if not hasattr(self, "_segue"):
            ks = [self.valor_chave(l) for l in self.linhas] if self.chave else []
            self._segue = all(ks[i] <= ks[i + 1] for i in range(len(ks) - 1))
        return self._segue

    def dicts(self):
        nomes = [c.nome for c in self.campos]
        return [dict(zip(nomes, l)) for l in self.linhas]

    def linha_vazia(self):
        return [("" if c.tipo == 0 else 0.0 if c.tipo == 4 else max(c.low, 0) if c.low > 0 else 0) for c in self.campos]

    def codificar(self, linhas, capacidade=None, avisos=None):
        """Bytes da tabela com as linhas dadas (ordenadas pela chave quando a tabela é ordenada)."""
        avisos = avisos if avisos is not None else []
        flags, recsize, nbits = self.hdr[0], self.hdr[1], self.hdr[2]
        n = len(linhas)
        cap = max(capacidade or self.capacidade, n)
        if cap > 0xFFFF:
            raise ErroSquad(f"{self.nome}: {n} registros (o máximo é 65535).")
        if self.chave and n and self.segue_chave():
            linhas = sorted(linhas, key=self.valor_chave)
            if not self.validos:                              # tabela vazia que ganhou registros: como o RDBM grava
                flags |= 4
        regs = bytearray()
        foras = {}
        for linha in linhas:
            acc = 0
            buf = bytearray(recsize)
            for c, v in zip(self.campos, linha):
                if c.tipo == 3:
                    try:
                        raw = int(v) - c.low
                    except (TypeError, ValueError):
                        raw = 0
                    if raw < 0 or raw >= (1 << c.bits):
                        foras[c.nome] = foras.get(c.nome, 0) + 1
                        raw = max(0, min(raw, (1 << c.bits) - 1))
                    acc |= raw << c.bitoff
                elif c.tipo == 4:
                    struct.pack_into("<f", buf, c.bitoff // 8, float(v or 0))
                elif c.tipo == 0:
                    k = c.bits // 8
                    t = str(v or "").encode("utf-8")
                    if len(t) > k:
                        t = t[:k].decode("utf-8", errors="ignore").encode("utf-8")
                    buf[c.bitoff // 8:c.bitoff // 8 + len(t)] = t
            ib = acc.to_bytes(recsize, "little")
            regs += bytes(x | y for x, y in zip(ib, buf))
        for nome, q in foras.items():
            avisos.append(f"{self.nome}.{nome}: {q} valor(es) fora da faixa do campo foram ajustados")
        regs += bytes(recsize * (cap - n))
        nf8 = self.hdr[8]
        hdr = struct.pack("<IIIIHHHHII", flags, recsize, nbits, 0, cap, n, self.hdr[6], self.hdr[7], nf8, self.hdr[9])
        hdr += struct.pack("<I", dados.crc32_t3db(hdr))
        corpo = b"".join(struct.pack("<II4sI", c.tipo, c.bitoff, c.sn.encode("latin-1"), c.bits) for c in self.campos)
        corpo += bytes(regs)
        if nf8 & 0x100:
            corpo += struct.pack("<4sBBH", self.chave_sn.encode("latin-1"), len(self.chave), 1, 0)
            corpo += b"".join(struct.pack("<II", k, 1) for k in self.chave)
        return hdr + corpo + struct.pack("<I", dados.crc32_t3db(corpo))


class Squad:
    def __init__(self, caminho, meta_caminho):
        self.caminho = caminho
        with open(caminho, "rb") as f:
            d = f.read()
        if d[:8] != b"FBCHUNKS":
            raise ErroSquad(f"{os.path.basename(caminho)} não é um squad do FIFA/FC (falta o cabeçalho FBCHUNKS).")
        i = d.find(b"SaveType_", 0, 0x10000)
        if i < 0:
            raise ErroSquad("Não achei o tipo do arquivo (SaveType_) no cabeçalho.")
        fim = d.index(b"\0", i)
        self.tipo = d[i + 9:fim].decode("latin-1")
        if self.tipo != "Squads":
            raise ErroSquad(f"Este arquivo é um save do tipo {self.tipo}; só squads (SaveType_Squads) são aceitos.")
        self.pos_crc = fim + 1
        self.db_off = d.find(b"DB\x00\x08", self.pos_crc)
        if self.db_off < 0:
            raise ErroSquad("Não achei o banco (DB) dentro do squad.")
        crc = struct.unpack_from("<I", d, self.pos_crc)[0]
        if zlib.crc32(d[self.db_off - 4:]) != crc or struct.unpack_from("<I", d, self.db_off - 4)[0] != len(d) - self.db_off:
            raise ErroSquad("O squad está corrompido ou num formato desconhecido (CRC ou tamanho não confere).")
        n = d[0x12:0x12 + 64].split(b"\0")[0]
        self.nome_jogo = n.decode("utf-8", errors="replace")
        self.d = d
        self.meta = dados.ler_meta(meta_caminho)
        o = self.db_off
        self.db_tam = struct.unpack_from("<I", d, o + 8)[0]
        nt = struct.unpack_from("<I", d, o + 16)[0]
        self.entradas = [struct.unpack_from("<4sI", d, o + 0x18 + 8 * k) for k in range(nt)]
        base = o + 0x18 + 8 * nt + 4
        por_short = {v["short"]: k for k, v in dados.tabelas_meta(self.meta).items()}
        ordem = sorted(range(nt), key=lambda k: self.entradas[k][1])
        self.ordem = ordem
        self.tabelas = {}
        self.por_indice = {}
        for pos, k in enumerate(ordem):
            snb, off = self.entradas[k]
            sn = snb.decode("latin-1")
            nome = por_short.get(sn, sn)
            T = base + off
            fimt = base + self.entradas[ordem[pos + 1]][1] if pos + 1 < nt else o + self.db_tam
            hdr = list(struct.unpack_from("<IIIIHHHHIII", d, T))
            nf = hdr[8] & 0xFF
            mc = self.meta.get(nome, {}).get("campos", {})
            por_sn = {v["short"]: dict(v, nome=c) for c, v in mc.items()}
            campos = []
            for j in range(nf):
                ft, bo, fsn, dep = struct.unpack_from("<II4sI", d, T + 36 + 16 * j)
                fsn = fsn.decode("latin-1")
                if ft not in TIPOS:
                    raise ErroSquad(f"{nome}: campo {fsn} de tipo {ft} desconhecido.")
                campos.append(Campo(ft, bo, fsn, dep, por_sn.get(fsn, {})))
            chave_sn, chave = "", []
            if hdr[8] & 0x100:
                q = T + 36 + 16 * nf + hdr[1] * hdr[4]
                chave_sn = d[q:q + 4].decode("latin-1")
                nk = d[q + 4]
                chave = [struct.unpack_from("<I", d, q + 8 + 8 * j)[0] for j in range(nk)]
            t = Tabela(nome, sn, hdr, campos, chave_sn, chave, d[T:fimt], pos)
            self.tabelas[nome] = t
            self.por_indice[k] = t

    def tabela(self, nome):
        if nome not in self.tabelas:
            raise ErroSquad(f"A tabela {nome} não existe neste squad.")
        return self.tabelas[nome]

    def tem(self, nome):
        return nome in self.tabelas

    def gravar(self, destino, novas, capacidades=None, avisos=None):
        """Grava o squad trocando as tabelas em 'novas' (nome -> linhas). Devolve o tamanho gravado."""
        avisos = avisos if avisos is not None else []
        capacidades = capacidades or {}
        d = self.d
        nt = len(self.entradas)
        blobs = {}
        for k, t in self.por_indice.items():
            if t.nome in novas:
                blobs[k] = t.codificar(novas[t.nome], capacidades.get(t.nome), avisos)
            else:
                blobs[k] = t.bruto
        off, pos = {}, 0
        for k in self.ordem:
            off[k] = pos
            pos += len(blobs[k])
        ent = b"".join(struct.pack("<4sI", self.entradas[k][0], off[k]) for k in range(nt))
        base = 0x18 + 8 * nt + 4
        cab = struct.pack("<4sIIII", b"DB\x00\x08", 0, base + pos, 0, nt)
        cab += struct.pack("<I", dados.crc32_t3db(cab))
        db = bytearray(cab + ent + struct.pack("<I", dados.crc32_t3db(ent)))
        for k in self.ordem:
            db += blobs[k]
        cauda = d[self.db_off + self.db_tam:]
        out = bytearray(d[:self.db_off]) + db + cauda
        tam_cab = struct.unpack_from("<I", out, 0x0A)[0]
        struct.pack_into("<I", out, 0x0E, len(out) - (0x12 + tam_cab))
        struct.pack_into("<I", out, self.db_off - 4, len(out) - self.db_off)
        struct.pack_into("<I", out, self.pos_crc, zlib.crc32(out[self.db_off - 4:]))
        tmp = destino + ".tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, destino)
        return len(out)
