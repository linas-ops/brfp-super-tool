"""Extração de um arquivo legacy nativo (ex.: data/db/fifa_ng_db.db) do jeito que o SDK do FET o resolve.

Reconstruído de Sdk.ChunkFile.ChunkFileManifestReader e Sdk.Legacy.LegacyFileManager: cada EBX ChunkFileCollector
aponta para um chunk de manifesto; cada registro (hash FNV-1 64 do nome em minúsculas, offsets comprimidos de início e
fim, offset, tamanho, índice no pool de GUIDs) endereça um trecho de um chunk de dados.
"""
from __future__ import annotations
import struct
import uuid

from .base import falha


def fnv1_64_lower(name):
    h = 0xcbf29ce484222325
    for b in name.lower().encode('utf8'):
        h = ((h * 0x100000001b3) & 0xffffffffffffffff) ^ b
    return h


def parse_manifest(data):
    num, _, count, position, num3 = struct.unpack_from('<IqIqI', data, 0)
    p = 4 + 8 + 4 + 8 + 4 + 8 + 4 + 8
    pool_at = struct.unpack_from('<q', data, p)[0]
    pool_size = (len(data) - (num + num3 + 6) * 4 - pool_at) // 16
    pool = [str(uuid.UUID(bytes_le=data[pool_at + 16 * i:pool_at + 16 * i + 16])) for i in range(pool_size)]
    records = []
    for j in range(count):
        h, cs, ce, off, size, gi = struct.unpack_from('<QIIIIi', data, position + 28 * j)
        if not 0 <= gi < len(pool):
            raise ValueError(f'índice de GUID inválido {gi}')
        records.append(dict(name_hash=h, compressed_start=cs, compressed_end=ce, offset=off, size=size, chunk=pool[gi]))
    return records


def framed(data):
    """True quando data é uma sequência exata de blocos CAS válidos."""
    p = 0
    while p < len(data):
        if p + 8 > len(data):
            return False
        a, b = struct.unpack_from('>II', data, p)
        if a >> 24 or ((b >> 20) & 15) != 7 or not (a & 0xffffff) or (b >> 24) not in (0, 17, 21, 25):
            return False
        p += 8 + (b & 0xfffff)
    return p == len(data)


def read_chunk_stored(cas, meta):
    if meta.get('sha1'):
        return cas.read_encoded(meta)
    # Chunks de TOC não têm SHA-1 no cache: aceita um CAS só quando o trecho inteiro é um enquadramento CAS válido,
    # e exige um candidato único.
    found = []
    for path in cas.cas_files(int(bool(meta['patch'])), meta['cas']):
        if path.stat().st_size < meta['offset'] + meta['size']:
            continue
        with path.open('rb') as f:
            f.seek(meta['offset'])
            raw = f.read(meta['size'])
        if framed(raw):
            found.append((raw, path))
    if len(found) != 1:
        raise ValueError(f'{len(found)} candidatos CAS válidos para o chunk {meta["id"]}')
    return found[0]


def decode_range(cas, stored, compressed_start, offset, size):
    out = bytearray()
    p = compressed_start
    while len(out) < offset + size:
        a, b = struct.unpack_from('>II', stored, p)
        n = b & 0xfffff
        out += cas.decompress(stored[p:p + 8 + n])
        p += 8 + n
    return bytes(out[offset:offset + size])


def extrair(amb, name):
    index = amb.indice()
    cas = amb.cas()
    target = fnv1_64_lower(name)
    chunks = index['chunk_by_id']
    found = []
    for e in index['ebx']:
        if e['type'] != 'ChunkFileCollector':
            continue
        raw, _, _ = cas.read_asset(e)
        ids = {str(uuid.UUID(bytes_le=raw[i:i + 16])) for i in range(len(raw) - 15)} & chunks.keys()
        for cid in sorted(ids):
            stored, _ = read_chunk_stored(cas, chunks[cid])
            for r in parse_manifest(cas.decompress(stored)):
                if r['name_hash'] == target:
                    found.append(dict(collector=e['name'], manifest_chunk=cid, **r))
    if len(found) != 1:
        falha(f'esperado um registro para {name}, achados {len(found)}')
    r = found[0]
    stored, _ = read_chunk_stored(cas, chunks[r['chunk']])
    return decode_range(cas, stored, r['compressed_start'], r['offset'], r['size'])
