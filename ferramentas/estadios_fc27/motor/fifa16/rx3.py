"""Reader for FIFA 16 PC RX3 ("RX3l" v4) stadium files: geometry, materials, locators, textures.

Layout (checked on the Morumbi/Maracanã/Neo Química files):
  header  'RX3l', u32 version 4, u32 size, u32 section count, then 16-byte entries (type, offset, size, 0)
  0xC28193F0 vertex format   u32 size, u32 len, 8 pad, text 'p0:00:00:0001:3f32 n0:0C:00:0001:3s10n ...'
  0x00587AA1 vertex buffer   u32 size, u32 count, u32 stride, u32 1, data
  0x005878F4 index buffer    u32 size, u32 count, u32 index size (2|4), u32 0, data
  0xD48D7880 primitive       u32 primitive type (4 = triangle list), 12 pad
  0x075BD958 material        u32 size, u32 texture count, 8 pad, shader name, then (param name, u32 texture index) pairs
  0x28DA5CE2 locator         u32 size, 7 floats (x, y, z, ?, ?, ?, ?) in centimetres
  0x4C9B9EB2 names           u32 size, u32 count, 8 pad, then (u32 section type, u32 length, name)
  0x7A0B60DA texture         u32 size, u8 type, u8 format (0 DXT1, 2 DXT5), u16 flags, u16 w, h, depth, mips,
                             then per mip: u32 pitch, u32 lines, u32 bytes, u32 0, data
  0xF074FBB1 collision       u32 size, u32 1, 8 pad, name, u32 1, u32 triangle count, float3 triangles
  0x0DC3FFD4 layer name      u32 size, u32 1, 8 pad, name (AdBoard, Alpha*, Banner_NoShadowCast, EnvironmentSkirt, Exterior,
                             Jumbotron, MainStadium*, Pitch, SidelineProps, Sky, CollisionGeometry)
  0x7E2480EC layer nodes     u32 size, u32 1, -1, 0, 4x4 matrix, bbox min/max (vec4), then u32 count, -1 and count leaves
                             (bbox min vec4, bbox max vec4, u32 primitive, u32 material); one per layer name, in order
                             (the collision layer has none). Primitives of a layer are contiguous; materials can be shared
                             (Maracanã: 121 primitives, 116 materials), so the material of a primitive comes from its leaf.
Units are centimetres, Y up, X along the pitch length, Z across (same axes as FC27).
Vertex element codes: 3f32 float3, 3s10n signed 10:10:10 normalised, 2f16 half2.
"""
import collections, struct
from pathlib import Path

VFORMAT, VB, IB, PRIM, MATERIAL, LOCATOR, NAMES, TEXHDR, TEX, COLLISION, LAYER, LAYER_NODES = (
    0xC28193F0, 0x00587AA1, 0x005878F4, 0xD48D7880, 0x075BD958, 0x28DA5CE2, 0x4C9B9EB2, 0x6BD085DC, 0x7A0B60DA, 0xF074FBB1,
    0x0DC3FFD4, 0x7E2480EC)


class RX3:
    def __init__(self, path):
        self.path = Path(path)
        self.f = open(self.path, 'rb')
        head = self.f.read(16)
        if head[:4] != b'RX3l':
            raise ValueError('not RX3l: ' + str(path))
        self.version, self.size, n = struct.unpack_from('<III', head, 4)
        tab = self.f.read(16 * n)
        self.sections = [struct.unpack_from('<III', tab, 16 * i) for i in range(n)]
        end = self.path.stat().st_size
        for t, o, s in self.sections:
            if o + s > end:
                raise ValueError('section out of bounds')
        self.by = collections.defaultdict(list)
        for t, o, s in self.sections:
            self.by[t].append((o, s))
        self.names = []
        for o, s in self.by[NAMES]:
            b = self.read(o, s)
            _, cnt = struct.unpack_from('<II', b, 0)
            q = 16
            for _ in range(cnt):
                ty, ln = struct.unpack_from('<II', b, q)
                q += 8
                self.names.append((ty, b[q:q + ln].split(b'\0')[0].decode('latin1')))
                q += ln

    def read(self, o, s):
        self.f.seek(o)
        b = self.f.read(s)
        if len(b) != s:
            raise ValueError('short read')
        return b

    def names_of(self, typ):
        return [n for t, n in self.names if t == typ]

    def layers(self):
        """[(layer name, [(primitive, material), ...])] in file order."""
        names = []
        for o, s in self.by[LAYER]:
            b = self.read(o, s)
            names.append(b[16:].split(b'\0')[0].decode('latin1'))
        out = []
        for k, (o, s) in enumerate(self.by[LAYER_NODES]):
            b = self.read(o, s)
            count, minus = struct.unpack_from('<Ii', b, 112)
            if minus != -1 or 120 + 40 * count > s:
                raise ValueError('layer node section layout')
            leaves = [struct.unpack_from('<II', b, 120 + 40 * j + 32) for j in range(count)]
            out.append((names[k] if k < len(names) else f'layer_{k}', leaves))
        return out

    def material_of_primitive(self):
        """{primitive: (material, layer)}; identity when the file has one material per primitive and no layer table."""
        n = len(self.by[PRIM])
        out = {}
        for name, leaves in self.layers():
            for prim, mat in leaves:
                if prim in out:
                    raise ValueError(f'primitive {prim} in two layers')
                out[prim] = (mat, name)
        if len(out) != n:
            if len(self.by[MATERIAL]) == n and not out:
                return {i: (i, '') for i in range(n)}
            raise ValueError(f'layers cover {len(out)} of {n} primitives')
        if any(not 0 <= m < len(self.by[MATERIAL]) for m, _ in out.values()):
            raise ValueError('layer leaf material out of range')
        return out

    # ------------------------------------------------------------ geometry
    def primitives(self):
        """One dict per primitive: name, material, vertex format, raw vertex/index buffers."""
        n = len(self.by[VB])
        if not (len(self.by[IB]) == len(self.by[VFORMAT]) == len(self.by[PRIM]) == n):
            raise ValueError('primitive sections do not line up')
        mat_of = self.material_of_primitive()
        names = self.names_of(PRIM)
        out = []
        for i in range(n):
            fo, fs = self.by[VFORMAT][i]
            fmt = self.read(fo, fs)[16:].split(b'\0')[0].decode('ascii')
            vo, vs = self.by[VB][i]
            vb = self.read(vo, vs)
            _, vcount, stride, _ = struct.unpack_from('<IIII', vb, 0)
            io, is_ = self.by[IB][i]
            ib = self.read(io, is_)
            _, icount, isize, _ = struct.unpack_from('<IIII', ib, 0)
            po, ps = self.by[PRIM][i]
            ptype = struct.unpack_from('<I', self.read(po, ps), 0)[0]
            out.append(dict(index=i, name=names[i] if i < len(names) else str(i), format=fmt, vertex_count=vcount, stride=stride,
                            vertices=vb[16:16 + vcount * stride], index_count=icount, index_size=isize,
                            indices=ib[16:16 + icount * isize], primitive_type=ptype, material=self.material(mat_of[i][0]),
                            material_index=mat_of[i][0], layer=mat_of[i][1]))
        return out

    def material(self, i):
        o, s = self.by[MATERIAL][i]
        b = self.read(o, s)
        _, cnt = struct.unpack_from('<II', b, 0)
        q = 16

        def cstr(q):
            e = b.index(b'\0', q)
            return b[q:e].decode('latin1'), e + 1
        shader, q = cstr(q)
        tex = []
        for _ in range(cnt):
            p, q = cstr(q)
            tex.append((p, struct.unpack_from('<I', b, q)[0]))
            q += 4
        return dict(shader=shader, textures=tex)

    def locators(self):
        names = self.names_of(LOCATOR)
        out = []
        for (o, s), nm in zip(self.by[LOCATOR], names):
            v = struct.unpack_from('<7f', self.read(o, s), 4)
            out.append(dict(name=nm, values=list(v)))
        return out

    def collisions(self):
        out = []
        for o, s in self.by[COLLISION]:
            b = self.read(o, s)
            e = b.index(b'\0', 16)
            name = b[16:e].decode('latin1')
            _, count = struct.unpack_from('<II', b, e + 1)
            tris = struct.unpack_from('<%df' % (count * 9), b, e + 9)
            out.append(dict(name=name, triangles=[tris[k:k + 9] for k in range(0, len(tris), 9)]))
        return out

    # ------------------------------------------------------------ textures
    def textures(self):
        """Header of every texture section, in names-table order (name, w, h, format, mips, offset)."""
        names = self.names_of(TEX)
        out = []
        for k, (o, s) in enumerate(self.by[TEX]):
            h = self.read(o, 16)
            total, ttype, fmt, flags, w, hh, depth, mips = struct.unpack_from('<IBBHHHHH', h, 0)
            out.append(dict(name=names[k] if k < len(names) else f'tex_{k}', type=ttype, format=fmt, flags=flags, width=w,
                            height=hh, depth=depth, mips=mips, offset=o, size=s))
        return out

    def texture_mips(self, t, strict=True):
        """List of (width, height, bytes) per mip level of a texture section.

        With strict=False the chain stops at the first mip whose stored size is not the BC size
        (one Morumbi texture ends with a 6x1 mip stored uncompressed); the caller regenerates the rest.
        """
        b = self.read(t['offset'], t['size'])
        q = 16
        out = []
        w, h = t['width'], t['height']
        for _ in range(t['mips']):
            pitch, lines, size, _ = struct.unpack_from('<IIII', b, q)
            q += 16
            expect = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if t['format'] == 0 else 16)
            if size != expect and not strict:
                return out
            out.append((w, h, b[q:q + size]))
            q += size
            w, h = max(1, w // 2), max(1, h // 2)
        if not 0 <= t['size'] - q < 16:  # sections are padded to 16 bytes
            raise ValueError(f"texture {t['name']} size mismatch {q} != {t['size']}")
        return out


def decode_vertices(prim):
    """Vertex attributes of a primitive as lists: positions (cm), normals, uv0, uv1, tangents, binormals."""
    import numpy as np
    fmt = prim['format'].split()
    n, stride = prim['vertex_count'], prim['stride']
    raw = np.frombuffer(prim['vertices'], dtype=np.uint8).reshape(n, stride)
    out = {}
    for el in fmt:
        usage, off, _, _, code = el.split(':')
        off = int(off, 16)
        if code == '3f32':
            v = raw[:, off:off + 12].copy().view('<f4').reshape(n, 3)
        elif code == '2f16':
            v = raw[:, off:off + 4].copy().view('<f2').reshape(n, 2).astype(np.float32)
        elif code == '3s10n':
            u = raw[:, off:off + 4].copy().view('<u4').reshape(n)
            comps = []
            for sh in (0, 10, 20):
                c = ((u >> sh) & 0x3FF).astype(np.int32)
                c = np.where(c >= 512, c - 1024, c)
                comps.append(np.maximum(c / 511.0, -1.0))
            v = np.stack(comps, 1).astype(np.float32)
        else:
            raise ValueError('unknown vertex element ' + el)
        out[usage] = v
    return out


def decode_indices(prim):
    import numpy as np
    dt = '<u2' if prim['index_size'] == 2 else '<u4'
    return np.frombuffer(prim['indices'], dtype=dt).astype(np.int64)
