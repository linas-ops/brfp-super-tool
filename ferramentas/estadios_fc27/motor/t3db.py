"""Leitura e escrita de bancos t3db (fifa_ng_db.db) do FIFA/FC.

Estrutura (little-endian):
  cabeçalho do arquivo: 'DB\\0\\x08', 0, tamanho_arquivo, 0, n_tabelas, crc_cabeçalho(?),
      n_tabelas x (shortname[4], offset), crc
  cada tabela (offset relativo ao fim do cabeçalho):
      36 bytes: flags, recsize, bits_por_registro(recsize*8-1), tam_bloco_strings, n_registros(u16),
                n_validos(u16), 0(u16), 0xffff(u16), n_campos, 0, crc
      n_campos x 16 bytes: tipo, bit_offset, shortname[4], profundidade(bits)
      registros (recsize bytes cada), bloco de strings comprimidas (árvore Huffman + dados), crc
  tipos: 0 = string embutida, 3 = inteiro (valor gravado - rangelow), 4 = real (float32),
         13 = string comprimida (Huffman, deslocamento no bloco de strings)
"""
import re
import struct


def load_meta(meta_path):
    meta = open(meta_path, encoding='utf-8').read()
    tables = {}
    for m in re.finditer(r'<table name="([^"]+)" shortname="([^"]+)"[^>]*>(.*?)</table>', meta, re.S):
        name, sn, body = m.groups()
        fields = {}
        for fm in re.finditer(r'<field ([^>]*)/>', body):
            a = dict(re.findall(r'(\w+)="([^"]*)"', fm.group(1)))
            fields[a['shortname']] = dict(name=a['name'], type=a['type'], depth=int(a['depth']),
                                          low=int(a['rangelow']), high=int(a['rangehigh']))
        tables[sn] = dict(name=name, fields=fields)
    return tables


class Field:
    __slots__ = ('ftype', 'bitoff', 'sn', 'depth', 'name', 'low', 'mtype')

    def __init__(self, ftype, bitoff, sn, depth, meta):
        self.ftype, self.bitoff, self.sn, self.depth = ftype, bitoff, sn, depth
        m = meta.get(sn, {})
        self.name = m.get('name', sn)
        self.low = m.get('low', 0)
        self.mtype = m.get('type')


class DbTable:
    def __init__(self):
        self.sn = self.name = None
        self.hdr = None
        self.fields = []
        self.rows = []          # listas de valores (str) na ordem de self.fields
        self.raw_tail = b''


def _huff_tree(buf, start, size):
    return [((buf[start + 4 * i], buf[start + 4 * i + 1]), (buf[start + 4 * i + 2], buf[start + 4 * i + 3]))
            for i in range(size // 4)]


def _huff_decode(buf, pos, n, nodes):
    out = bytearray()
    bit = pos * 8
    node = 0
    while len(out) < n:
        b = (buf[bit >> 3] >> (7 - (bit & 7))) & 1
        bit += 1
        e = nodes[node][b]
        if e[0] == 0:
            out.append(e[1])
            node = 0
        else:
            node = e[0]
    return bytes(out)


def _get_bits(rec, bitoff, depth):
    # bits em ordem little-endian: bit 0 do registro = bit menos significativo do byte 0
    v = int.from_bytes(rec, 'little')
    return (v >> bitoff) & ((1 << depth) - 1)


def read_db(path, meta_path):
    meta = load_meta(meta_path)
    d = open(path, 'rb').read()
    ntab = struct.unpack_from('<I', d, 0x10)[0]
    entries = [struct.unpack_from('<4sI', d, 0x18 + 8 * i) for i in range(ntab)]
    base = 0x18 + 8 * ntab + 4
    order = sorted(range(ntab), key=lambda i: entries[i][1])
    ends = {}
    for k, i in enumerate(order):
        ends[i] = base + entries[order[k + 1]][1] if k + 1 < ntab else len(d)
    tables = []
    for i, (snb, off) in enumerate(entries):
        sn = snb.decode('latin-1')
        T = base + off
        hdr = list(struct.unpack_from('<IIIIHHHHIII', d, T))
        flags, recsize, nbits, strlen, nrec, nvalid, u6, u7, nf, u9, tcrc = hdr
        t = DbTable()
        t.sn, t.hdr = sn, hdr
        t.name = meta.get(sn, {}).get('name', sn)
        mfields = meta.get(sn, {}).get('fields', {})
        for k in range(nf):
            ft, bo, fsn, dep = struct.unpack_from('<II4sI', d, T + 36 + 16 * k)
            t.fields.append(Field(ft, bo, fsn.decode('latin-1'), dep, mfields))
        R = T + 36 + 16 * nf
        sblock = R + recsize * nrec
        nodes = None
        tree_size = None
        if strlen and flags & 0x40:
            # strings comprimidas (Huffman); tamanho da árvore = menor deslocamento de string usado
            offs = []
            for r in range(nvalid):
                rec = d[R + recsize * r:R + recsize * (r + 1)]
                for f in t.fields:
                    if f.ftype == 13:
                        o = struct.unpack_from('<I', rec, f.bitoff // 8)[0]
                        if o != 0xFFFFFFFF:
                            offs.append(o)
            tree_size = min(offs) if offs else 0
            nodes = _huff_tree(d, sblock, tree_size)
        for r in range(nvalid):
            rec = d[R + recsize * r:R + recsize * (r + 1)]
            vals = []
            for f in t.fields:
                if f.ftype == 3:
                    vals.append(str(_get_bits(rec, f.bitoff, f.depth) + f.low))
                elif f.ftype == 4:
                    vals.append(repr_float(struct.unpack_from('<f', rec, f.bitoff // 8)[0]))
                elif f.ftype == 0:
                    raw = rec[f.bitoff // 8:f.bitoff // 8 + f.depth // 8]
                    vals.append(raw.split(b'\0')[0].decode('utf-8', errors='replace'))
                elif f.ftype == 13:
                    o = struct.unpack_from('<I', rec, f.bitoff // 8)[0]
                    if o == 0xFFFFFFFF:
                        vals.append('')
                    else:
                        p = sblock + o
                        n = d[p]
                        raw = _huff_decode(d, p + 1, n, nodes) if nodes is not None else d[p + 1:p + 1 + n]
                        vals.append(raw.decode('utf-8', errors='replace'))
                else:
                    raise ValueError('tipo de campo desconhecido %d' % f.ftype)
            t.rows.append(vals)
        t.tree_size = tree_size
        t.raw_end = ends[i] - (sblock + strlen)
        tables.append(t)
    return d, tables


def repr_float(x):
    s = '%.9g' % x
    return s


# ------------------------------------------------------------------ escrita
_TM = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xffffffff if _c & 0x80000000 else (_c << 1) & 0xffffffff
    _TM.append(_c)


def crc32_msb(b, init=0xffffffff):
    """CRC32 do t3db: polinômio 0x04C11DB7, MSB primeiro, init 0xFFFFFFFF, sem xor final."""
    c = init
    tm = _TM
    for x in b:
        c = ((c << 8) & 0xffffffff) ^ tm[((c >> 24) ^ x) & 0xff]
    return c


class RangeError(ValueError):
    pass


def encode_record(fields, values, recsize, errors=None, table=''):
    acc = 0
    buf = bytearray(recsize)
    for f, v in zip(fields, values):
        if f.ftype == 3:
            raw = int(v) - f.low
            if raw < 0 or raw >= (1 << f.depth):
                msg = '%s.%s = %s fora da faixa (%d bits a partir de %d)' % (table, f.name, v, f.depth, f.low)
                if errors is None:
                    raise RangeError(msg)
                errors.append(msg)
                raw = max(0, min(raw, (1 << f.depth) - 1))
            acc |= raw << f.bitoff
        elif f.ftype == 4:
            struct.pack_into('<f', buf, f.bitoff // 8, float(v))
        elif f.ftype == 0:
            n = f.depth // 8
            b = v.encode('utf-8')
            if len(b) > n:
                msg = '%s.%s texto longo demais (%d bytes, máx %d): %r' % (table, f.name, len(b), n, v)
                if errors is None:
                    raise RangeError(msg)
                errors.append(msg)
                b = b[:n]
            buf[f.bitoff // 8:f.bitoff // 8 + len(b)] = b
        else:
            raise ValueError('escrita de campo tipo %d não suportada (%s.%s)' % (f.ftype, table, f.name))
    ib = acc.to_bytes(recsize, 'little')
    return bytes(x | y for x, y in zip(ib, buf))


def build_table(t, rows, errors=None):
    """Monta os bytes de uma tabela sem bloco de strings, com os registros 'rows' (listas na ordem de t.fields)."""
    if any(f.ftype == 13 for f in t.fields):
        raise ValueError('tabela com strings comprimidas não suportada: ' + t.name)
    flags, recsize, nbits = t.hdr[0], t.hdr[1], t.hdr[2]
    n = len(rows)
    if n > 0xFFFF:
        raise ValueError('%s: %d registros (máximo 65535)' % (t.name, n))
    hdr = struct.pack('<IIIIHHHHII', flags, recsize, nbits, 0, n, n, t.hdr[6], t.hdr[7], len(t.fields), t.hdr[9])
    hdr += struct.pack('<I', crc32_msb(hdr))
    body = b''.join(struct.pack('<II4sI', f.ftype, f.bitoff, f.sn.encode('latin-1'), f.depth) for f in t.fields)
    body += b''.join(encode_record(t.fields, r, recsize, errors, t.name) for r in rows)
    body += b'\0' * ((-len(body)) % 4)
    return hdr + body + struct.pack('<I', crc32_msb(body))


def write_db(orig_bytes, tables, new_blobs, out_path):
    """Regrava o arquivo: tabelas em new_blobs (nome -> bytes) substituem as originais; as demais são copiadas."""
    d = orig_bytes
    ntab = struct.unpack_from('<I', d, 0x10)[0]
    entries = [struct.unpack_from('<4sI', d, 0x18 + 8 * i) for i in range(ntab)]
    base = 0x18 + 8 * ntab + 4
    order = sorted(range(ntab), key=lambda i: entries[i][1])
    blobs = {}
    for k, i in enumerate(order):
        start = base + entries[i][1]
        end = base + entries[order[k + 1]][1] if k + 1 < ntab else len(d)
        blobs[i] = d[start:end]
    by_sn = {t.sn: t for t in tables}
    for i, (snb, off) in enumerate(entries):
        name = by_sn[snb.decode('latin-1')].name
        if name in new_blobs:
            blobs[i] = new_blobs[name]
    new_off = {}
    pos = 0
    for i in order:
        new_off[i] = pos
        pos += len(blobs[i])
    ent = b''.join(struct.pack('<4sI', entries[i][0], new_off[i]) for i in range(ntab))
    total = base + pos
    head = struct.pack('<4sIIII', d[:4], 0, total, 0, ntab)
    head += struct.pack('<I', crc32_msb(head))
    out = bytearray(head + ent + struct.pack('<I', crc32_msb(ent)))
    for i in order:
        out += blobs[i]
    assert len(out) == total
    with open(out_path, 'wb') as fh:
        fh.write(out)
    return total
