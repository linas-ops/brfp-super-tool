"""Leitor dos pacotes .fpk/.fpkd do Fox Engine (PES 2021, PC).

Layout (conferido nos arquivos do Camp Nou do PES 2021):
  0x00  'foxfpk' + tipo (0 = fpk, 'd' = fpkd) + 'win'
  0x0A  u32 tamanho do arquivo
  0x20  u32 2, u32 arquivos, u32 referências, u32 0
  0x30  entradas de 0x30 bytes: u64 deslocamento, u64 tamanho, u64 deslocamento do nome, u64 tamanho do nome, MD5 do nome
        depois as referências (u64 deslocamento do nome, u64 tamanho do nome), os nomes e os dados
Os nomes são caminhos do jogo (/Assets/pes16/model/bg/st002/scenes/...fmdl).
"""
import struct
from pathlib import Path


class Fpk:
    def __init__(self, path):
        self.path = Path(path)
        b = self.path.read_bytes()
        if b[:6] != b'foxfpk' or b[7:10] != b'win':
            raise ValueError('não é um pacote fpk do PES: ' + str(path))
        self.tipo = 'fpkd' if b[6:7] == b'd' else 'fpk'
        magic, n, nref = struct.unpack_from('<III', b, 0x20)
        if magic != 2:
            raise ValueError('versão de fpk desconhecida: ' + str(path))
        self.b = b
        self.entradas = []
        for i in range(n):
            off, size, soff, slen = struct.unpack_from('<QQQQ', b, 0x30 + 0x30 * i)
            if off + size > len(b) or soff + slen > len(b):
                raise ValueError('entrada fora do arquivo: ' + str(path))
            self.entradas.append((b[soff:soff + slen].decode('utf8', 'replace'), off, size))
        q = 0x30 + 0x30 * n
        self.referencias = []
        for i in range(nref):
            soff, slen = struct.unpack_from('<QQ', b, q + 16 * i)
            self.referencias.append(b[soff:soff + slen].decode('utf8', 'replace'))

    def nomes(self):
        return [e[0] for e in self.entradas]

    def ler(self, nome):
        for n, off, size in self.entradas:
            if n == nome:
                return self.b[off:off + size]
        raise KeyError(nome)

    def itens(self):
        for n, off, size in self.entradas:
            yield n, self.b[off:off + size]
