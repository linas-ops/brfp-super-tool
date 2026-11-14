"""Leitor das texturas .ftex do Fox Engine (PES 2021, PC, versões 2.03 e 2.04, com os mips dentro do arquivo).

Layout (conferido nas texturas do Camp Nou do PES 2021):
  0x00  'FTEX', f32 versão, u16 formato, u16 largura, u16 altura, u16 profundidade, u8 mips, u8, u16 marcas
  0x1C  u32 tipo (cor, linear, normal...), u8 arquivos .ftexs (0 no PES 2021 de PC)
  0x40  um registro de 16 bytes por mip: u32 deslocamento, u32 tamanho, u32 tamanho no arquivo, u8 nível, u8 arquivo, u16 blocos
        no deslocamento, com blocos: (u16 tamanho no arquivo, u16 tamanho, u32 deslocamento a partir da tabela; bit 31 = sem
        compressão) e os blocos em zlib; sem blocos: os dados, em zlib quando o tamanho no arquivo difere do tamanho
Formatos: 0 RGBA de 32 bits (B, G, R, A), 2 BC1 (DXT1), 3 BC2, 4 BC3 (DXT5), 8 BC4, 9 BC5, 10 BC6H, 11 BC7, 12 RGBA de 16 bits
em ponto flutuante.
"""
import struct
import zlib
from pathlib import Path

FORMATOS = {0: 'BGRA8', 1: 'R8', 2: 'BC1', 3: 'BC2', 4: 'BC3', 8: 'BC4', 9: 'BC5', 10: 'BC6H', 11: 'BC7', 12: 'RGBA16F', 13: 'RGBA32F',
            14: 'RGB10A2', 15: 'R11G11B10F'}
BLOCO = {'BC1': 8, 'BC2': 16, 'BC3': 16, 'BC4': 8, 'BC5': 16, 'BC6H': 16, 'BC7': 16}
PIXEL = {'BGRA8': 4, 'R8': 1, 'RGBA16F': 8, 'RGBA32F': 16, 'RGB10A2': 4, 'R11G11B10F': 4}


def tamanho_mip(w, h, fmt):
    if fmt in BLOCO:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCO[fmt]
    return w * h * PIXEL[fmt]


class Ftex:
    def __init__(self, path):
        self.path = Path(path)
        with open(self.path, 'rb') as f:
            self.b = f.read()
        b = self.b
        if b[:4] != b'FTEX' or len(b) < 0x40:
            raise ValueError('não é FTEX: ' + self.path.name)
        self.versao, pf, self.largura, self.altura, self.profundidade, self.mips, _, _ = struct.unpack_from('<fHHHHBBH', b, 4)
        self.tipo = struct.unpack_from('<I', b, 0x1C)[0]
        self.arquivos_ftexs = b[0x20]
        self.formato = FORMATOS.get(pf, f'formato{pf}')
        self.tabela = [struct.unpack_from('<IIIBBH', b, 0x40 + 16 * i) for i in range(self.mips)]

    def mip(self, nivel):
        """(largura, altura, bytes) de um nível."""
        b = self.b
        off, tam, comp, idx, arq, blocos = self.tabela[nivel]
        if arq:
            raise ValueError(f'{self.path.name}: o mip {nivel} está num arquivo .ftexs (não suportado)')
        if blocos == 0:
            dados = b[off:off + (comp or tam)]
            if comp and comp != tam:
                dados = zlib.decompress(dados)
        else:
            partes = []
            for k in range(blocos):
                c, u, o = struct.unpack_from('<HHI', b, off + 8 * k)
                bruto = bool(o & 0x80000000)
                o &= 0x7FFFFFFF
                d = b[off + o:off + o + c]
                partes.append(d if bruto else zlib.decompress(d))
            dados = b''.join(partes)
        if len(dados) != tam:
            raise ValueError(f'{self.path.name}: mip {nivel} com {len(dados)} bytes, esperado {tam}')
        return max(1, self.largura >> idx), max(1, self.altura >> idx), dados

    def cadeia(self):
        """Mips do maior para o menor: [(largura, altura, bytes)]. Para no primeiro nível que não tem o tamanho do formato."""
        out = []
        for k in sorted(range(self.mips), key=lambda i: self.tabela[i][3]):
            w, h, d = self.mip(k)
            if self.formato in BLOCO or self.formato in PIXEL:
                if len(d) != tamanho_mip(w, h, self.formato):
                    break
            out.append((w, h, d))
        return out
