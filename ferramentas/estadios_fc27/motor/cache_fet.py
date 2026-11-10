"""Leitura do cache do FIFA Editor Tool (FETC v4, fc27.cache): índice de EBX, RES, chunks e bundles do jogo.

Layout conferido no FET 2.2.0 / interno 17.1.5.0: cada seção precisa terminar exatamente onde a próxima começa,
senão a leitura falha. O corpo é zstd: usa o compression.zstd do Python 3.14 ou o pacote zstandard.
"""
from __future__ import annotations
import hashlib
import uuid
from pathlib import Path


def _zstd_decompress(data, size):
    try:
        from compression import zstd  # Python 3.14+
        return zstd.decompress(data)
    except ImportError:
        pass
    try:
        import zstandard
    except ImportError as ex:
        raise RuntimeError('Falta o pacote zstandard (página Componentes do Super Tool) para ler o cache do FET.') from ex
    return zstandard.ZstdDecompressor().decompress(data, max_output_size=size)


class Reader:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError(f'bounds {self.pos}+{n}/{len(self.data)}')
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def u(self, n=1):
        return int.from_bytes(self.take(n), 'little')

    def seven(self):
        v = shift = 0
        while True:
            b = self.data[self.pos]
            self.pos += 1
            v |= (b & 127) << shift
            if b < 128:
                return v
            shift += 7
            if shift > 35:
                raise ValueError('invalid 7-bit int')

    def string(self):
        return self.take(self.seven()).decode('utf8')

    def guid(self):
        return str(uuid.UUID(bytes_le=self.take(16)))


HEADER = ['body_size', 'block_size', 'bundle_count', 'ebx_count', 'res_count', 'chunk_count', 'legacy_count',
          'brt_count', 'types_start', 'ebx_start', 'res_start', 'chunk_start', 'tail_start', 'legacy_start']


def read_header(path):
    with open(path, 'rb') as f:
        raw = f.read(64 + 4 * len(HEADER))
    r = Reader(raw)
    if r.take(4) != b'FETC' or r.u() != 4:
        raise ValueError('esperado FETC v4')
    h = {'head': r.u(3), 'exe': r.u(4), 'mvid': r.guid()}
    h.update({n: r.u(4) for n in HEADER})
    return h


def read_cache(path, raw=None):
    raw = Path(path).read_bytes() if raw is None else raw
    r = Reader(raw)
    if r.take(4) != b'FETC' or r.u() != 4:
        raise ValueError('esperado FETC v4')
    h = {'head': r.u(3), 'exe': r.u(4), 'mvid': r.guid()}
    h.update({n: r.u(4) for n in HEADER})
    for typ in ('ebx', 'res', 'chunk', 'legacy'):
        r.take(4 * ((h[typ + '_count'] + h['block_size'] - 1) // h['block_size']))
    body = _zstd_decompress(raw[r.pos:], h['body_size'])
    if len(body) != h['body_size']:
        raise ValueError('tamanho do corpo do cache não confere')
    r = Reader(body)
    bundles = [dict(index=i, name=r.string(), hash=r.u(8), superbundle=r.u(), type=r.u()) for i in range(h['bundle_count'])]
    if r.pos != h['types_start']:
        raise ValueError('fim da tabela de bundles não confere')
    types = [r.string() for _ in range(r.seven())]
    if r.pos != h['ebx_start']:
        raise ValueError('fim da tabela de tipos não confere')
    ebx = []
    for _ in range(h['ebx_count']):
        e = dict(name=r.string(), sha1=r.take(20).hex(), size=r.seven(), original_size=r.seven(), type=types[r.seven()],
                 partition=r.guid(), offset=r.seven(), installchunk=r.u(4), cas=r.u(), patch=r.u())
        e['bundles'] = [r.seven() for _ in range(r.seven())]
        e['dependencies'] = [r.guid() for _ in range(r.seven())]
        ebx.append(e)
    if r.pos != h['res_start']:
        raise ValueError('fim da tabela de EBX não confere')
    res = []
    for _ in range(h['res_count']):
        e = dict(name=r.string(), sha1=r.take(20).hex(), size=r.seven(), original_size=r.seven(), resrid=r.u(8),
                 restype=r.u(4), resmeta=r.take(16).hex(), offset=r.seven(), installchunk=r.u(4), cas=r.u(), patch=r.u())
        e['bundles'] = [r.seven() for _ in range(r.seven())]
        res.append(e)
    if r.pos != h['chunk_start']:
        raise ValueError('fim da tabela de RES não confere')
    chunks = []
    for _ in range(h['chunk_count']):
        e = dict(id=r.guid(), size=r.seven(), offset=r.seven(), installchunk=r.u(4), cas=r.u(), flags=r.u())
        e['patch'] = int(bool(e['flags'] & 1))
        if e['flags'] & 2:
            e.update(sha1=r.take(20).hex(), logical_offset=r.seven(), logical_size=r.seven(),
                     bundles=[r.seven() for _ in range(r.seven())])
        else:
            e['bundles'] = []
        chunks.append(e)
    if r.pos != h['tail_start']:
        raise ValueError('fim da tabela de chunks não confere')
    return dict(path=str(Path(path).resolve()), sha256=hashlib.sha256(raw).hexdigest(), header=h, bundles=bundles,
                types=types, ebx=ebx, res=res, chunks=chunks, tail=body[h['tail_start']:])
