"""Arquivos .big da EA (BIGF/BIG4) — o contêiner de cada overlay.

Cabeçalho: magia (4), tamanho total (u32 LE), quantidade (u32 BE), fim do cabeçalho (u32 BE); depois a tabela
(offset u32 BE, tamanho u32 BE, nome terminado em zero), a marca "L286" + 4 bytes e os dados alinhados em 64.
Os .big do jogo (BIGF) trazem ainda 16 bytes no fim, fora do tamanho total. Gravamos como os mods que funcionam
no jogo (BIG4, sem esses 16 bytes, tamanho total = tamanho do arquivo).
Num overlay: "0" = APT (Apt Data), "1" = constantes (Apt1), "N" = dados do character N-1 (geometria de um Shape
ou DDS de uma Image); "sg1"/"sg2" são marcadores vazios que separam geometria, texturas e constantes.
"""
import struct


class ErroBig(Exception):
    pass


def ler(dados):
    """[(nome, bytes)] na ordem do arquivo, mais a marca que vem depois da tabela."""
    if len(dados) < 16 or dados[:4] not in (b"BIGF", b"BIG4", b"BIGH"):
        raise ErroBig("Arquivo .big inválido")
    n, _fim_cab = struct.unpack_from(">II", dados, 8)
    p = 16
    itens = []
    for _ in range(n):
        off, tam = struct.unpack_from(">II", dados, p)
        p += 8
        e = dados.index(b"\0", p)
        nome = dados[p:e].decode("latin-1")
        p = e + 1
        if off + tam > len(dados):
            raise ErroBig(f"Entrada {nome} fora do arquivo")
        itens.append((nome, bytes(dados[off:off + tam])))
    marca = bytes(dados[p:p + 8]) if dados[p:p + 1] == b"L" else b"L286\x15\x05\x00\x00"
    return itens, marca


def gravar(itens, marca=b"L286\x15\x05\x00\x00", alinhamento=64):
    tabela = bytearray()
    for nome, _ in itens:
        tabela += b"\0" * 8 + nome.encode("latin-1") + b"\0"
    fim_tab = 16 + len(tabela)
    fim_cab = fim_tab + len(marca)
    pos = -(-fim_cab // alinhamento) * alinhamento
    offs = []
    for nome, d in itens:
        offs.append(pos)
        pos += len(d)
        if d:
            pos = -(-pos // alinhamento) * alinhamento
    total = -(-pos // alinhamento) * alinhamento
    out = bytearray(total)
    out[0:4] = b"BIG4"
    struct.pack_into("<I", out, 4, total)
    struct.pack_into(">II", out, 8, len(itens), fim_cab)
    q = 0
    for (nome, d), off in zip(itens, offs):
        struct.pack_into(">II", tabela, q, off, len(d))
        q += 8 + len(nome.encode("latin-1")) + 1
        out[off:off + len(d)] = d
    out[16:fim_tab] = tabela
    out[fim_tab:fim_cab] = marca
    return bytes(out)
