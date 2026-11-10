"""Extração de arquivos do executável do FIFA Editor Tool (bundle .NET de arquivo único), só leitura.

Layout: dotnet/runtime HostModel Bundle/Manifest.cs + FileEntry.cs.
"""
import struct
import zlib
from pathlib import Path

SIGNATURE = bytes.fromhex('8b1202b96a612038727b930214d7a03213f5b9e6efae3318ee3b2dce24b36aae')


def _read7(data, pos):
    v = shift = 0
    while True:
        b = data[pos]
        pos += 1
        v |= (b & 127) << shift
        if b < 128:
            return v, pos
        shift += 7


def manifest(data):
    p = data.find(SIGNATURE)
    if p < 8:
        raise ValueError('o executável do FET não tem a assinatura de bundle .NET')
    pos = struct.unpack_from('<q', data, p - 8)[0]
    major, minor, count = struct.unpack_from('<3I', data, pos)
    pos += 12
    n, pos = _read7(data, pos)
    pos += n
    if major >= 2:
        pos += 40
    entries = []
    for _ in range(count):
        off, size = struct.unpack_from('<qq', data, pos)
        pos += 16
        comp = 0
        if major >= 6:
            comp = struct.unpack_from('<q', data, pos)[0]
            pos += 8
        typ = data[pos]
        pos += 1
        n, pos = _read7(data, pos)
        name = data[pos:pos + n].decode('utf8')
        pos += n
        entries.append(dict(name=name, offset=off, size=size, compressed_size=comp, type=typ))
    return major, minor, entries


def extrair(exe, destino, nomes):
    """Grava em destino os arquivos pedidos (nome no bundle -> nome do arquivo). Devolve {nome: caminho}."""
    data = Path(exe).read_bytes()
    _, _, entries = manifest(data)
    por = {e['name']: e for e in entries}
    out = {}
    for nome, arquivo in nomes.items():
        e = por.get(nome)
        if e is None:
            raise ValueError(f'{nome} não está no executável do FET')
        raw = data[e['offset']:e['offset'] + (e['compressed_size'] or e['size'])]
        if e['compressed_size']:
            raw = zlib.decompress(raw, -15)
        if len(raw) != e['size']:
            raise ValueError('tamanho não confere: ' + nome)
        dest = Path(destino) / arquivo
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        out[nome] = dest
    return out
