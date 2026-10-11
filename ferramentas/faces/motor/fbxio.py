"""Leitura/gravação de FBX binário (7.x), sem dependências além de numpy.

O gravador refaz o arquivo byte a byte: propriedades não alteradas são
regravadas com os bytes originais, então só os arrays trocados mudam.
"""
import struct
import zlib

import numpy as np

_ARRAY_FMT = {'f': 'f4', 'd': 'f8', 'l': 'i8', 'i': 'i4', 'b': 'u1'}


class Prop:
    __slots__ = ('t', '_v', 'raw', 'enc')

    def __init__(self, t, v=None, raw=None, enc=0):
        self.t = t        # código de tipo FBX
        self._v = v       # valor decodificado (preguiçoso para arrays)
        self.raw = raw    # bytes originais da propriedade (sem o código de tipo)
        self.enc = enc    # 1 = array comprimido com zlib

    @property
    def v(self):
        if self._v is None and self.t in _ARRAY_FMT:
            n, enc, clen = struct.unpack_from('<III', self.raw, 0)
            body = self.raw[12:12 + clen]
            if enc == 1:
                body = zlib.decompress(body)
            self._v = np.frombuffer(body, dtype='<' + _ARRAY_FMT[self.t], count=n).copy()
        return self._v

    def set(self, value):
        """troca o valor (o tipo continua o mesmo) e descarta os bytes originais"""
        if self.t in _ARRAY_FMT:
            value = np.ascontiguousarray(value, dtype='<' + _ARRAY_FMT[self.t]).ravel()
        self._v = value
        self.raw = None


class Node:
    __slots__ = ('name', 'props', 'children', 'null_term')

    def __init__(self, name, props=None, children=None, null_term=False):
        self.name = name
        self.props = props or []
        self.children = children or []
        self.null_term = null_term

    def find(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def findall(self, name):
        return [c for c in self.children if c.name == name]

    def __repr__(self):
        return 'Node(%s, %d props, %d children)' % (self.name, len(self.props), len(self.children))


class FBXFile:
    def __init__(self, version, root, footer_id, header):
        self.version = version
        self.root = root
        self.footer_id = footer_id
        self.header = header


def read_fbx(path):
    data = open(path, 'rb').read()
    if not data.startswith(b'Kaydara FBX Binary  \x00'):
        raise ValueError('não é um FBX binário: %s' % path)
    version = struct.unpack_from('<I', data, 23)[0]
    wide = version >= 7500
    hdr_size = 25 if wide else 13

    def read_prop(pos):
        t = chr(data[pos])
        pos += 1
        if t == 'Y':
            return Prop(t, struct.unpack_from('<h', data, pos)[0], data[pos:pos + 2]), pos + 2
        if t == 'C':
            return Prop(t, data[pos], data[pos:pos + 1]), pos + 1
        if t == 'I':
            return Prop(t, struct.unpack_from('<i', data, pos)[0], data[pos:pos + 4]), pos + 4
        if t == 'F':
            return Prop(t, struct.unpack_from('<f', data, pos)[0], data[pos:pos + 4]), pos + 4
        if t == 'D':
            return Prop(t, struct.unpack_from('<d', data, pos)[0], data[pos:pos + 8]), pos + 8
        if t == 'L':
            return Prop(t, struct.unpack_from('<q', data, pos)[0], data[pos:pos + 8]), pos + 8
        if t in _ARRAY_FMT:
            n, enc, clen = struct.unpack_from('<III', data, pos)
            raw = data[pos:pos + 12 + clen]
            return Prop(t, None, raw, enc), pos + 12 + clen
        if t in 'SR':
            ln = struct.unpack_from('<I', data, pos)[0]
            raw = data[pos:pos + 4 + ln]
            v = data[pos + 4:pos + 4 + ln]
            if t == 'S':
                v = v.decode('utf-8', 'replace')
            return Prop(t, v, raw), pos + 4 + ln
        raise ValueError('tipo de propriedade FBX desconhecido %r em %d' % (t, pos))

    def read_node(pos):
        if wide:
            end, nprop, _plen = struct.unpack_from('<QQQ', data, pos)
            pos += 24
        else:
            end, nprop, _plen = struct.unpack_from('<III', data, pos)
            pos += 12
        nlen = data[pos]
        pos += 1
        if end == 0:
            return None, pos
        name = data[pos:pos + nlen].decode('ascii', 'replace')
        pos += nlen
        props = []
        for _ in range(nprop):
            p, pos = read_prop(pos)
            props.append(p)
        children = []
        null_term = False
        while pos < end:
            if end - pos == hdr_size and data[pos:end] == b'\0' * hdr_size:
                null_term = True
                break
            c, pos = read_node(pos)
            if c is None:
                null_term = True
                break
            children.append(c)
        return Node(name, props, children, null_term), end

    pos = 27
    top = []
    while pos < len(data):
        n, pos = read_node(pos)
        if n is None:
            break
        top.append(n)
    footer_id = data[pos:pos + 16]
    return FBXFile(version, Node('root', [], top), footer_id, data[:27])


def _prop_bytes(p):
    if p.raw is not None:
        return p.t.encode() + p.raw
    t, v = p.t, p._v
    if t == 'Y':
        return b'Y' + struct.pack('<h', v)
    if t == 'C':
        return b'C' + struct.pack('<B', 1 if v else 0)
    if t == 'I':
        return b'I' + struct.pack('<i', v)
    if t == 'F':
        return b'F' + struct.pack('<f', v)
    if t == 'D':
        return b'D' + struct.pack('<d', v)
    if t == 'L':
        return b'L' + struct.pack('<q', v)
    if t in _ARRAY_FMT:
        body = np.ascontiguousarray(v, dtype='<' + _ARRAY_FMT[t]).tobytes()
        n = len(v)
        if n * np.dtype(_ARRAY_FMT[t]).itemsize > 128:
            comp = zlib.compress(body)
            return t.encode() + struct.pack('<III', n, 1, len(comp)) + comp
        return t.encode() + struct.pack('<III', n, 0, len(body)) + body
    if t in 'SR':
        b = v.encode('utf-8') if isinstance(v, str) else v
        return t.encode() + struct.pack('<I', len(b)) + b
    raise ValueError(t)


def write_fbx(fbx, path):
    wide = fbx.version >= 7500
    hdr_size = 25 if wide else 13
    out = bytearray(fbx.header)

    def write_node(n):
        start = len(out)
        pbytes = b''.join(_prop_bytes(p) for p in n.props)
        name = n.name.encode('ascii')
        if wide:
            out.extend(struct.pack('<QQQ', 0, len(n.props), len(pbytes)))
        else:
            out.extend(struct.pack('<III', 0, len(n.props), len(pbytes)))
        out.append(len(name))
        out.extend(name)
        out.extend(pbytes)
        for c in n.children:
            write_node(c)
        if n.children or n.null_term:
            out.extend(b'\0' * hdr_size)
        end = len(out)
        if wide:
            struct.pack_into('<Q', out, start, end)
        else:
            struct.pack_into('<I', out, start, end)

    for n in fbx.root.children:
        write_node(n)
    out.extend(b'\0' * hdr_size)
    out.extend(fbx.footer_id)
    pad = (16 - (len(out) % 16)) % 16
    if pad == 0:
        pad = 16
    out.extend(b'\0' * pad)
    out.extend(b'\0' * 4)
    out.extend(struct.pack('<I', fbx.version))
    out.extend(b'\0' * 120)
    out.extend(bytes.fromhex('f85a8c6adef5d97eece90ce3758f290b'))
    with open(path, 'wb') as f:
        f.write(out)
