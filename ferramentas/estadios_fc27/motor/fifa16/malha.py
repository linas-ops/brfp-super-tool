"""Decoder for FC27 MeshSet LOD vertex/index data, driven by the ConvertTool mesh_dump JSON.

Vertex data of a subset starts at its VertexOffset; each stream of its declaration is a separate
block of VertexCount * stride bytes, in stream order (as FET's FBXImporter writes it).
Indices follow the vertex data (VertexDataSize), StartIndex is in index units.
"""
import struct
import numpy as np

FMT = {  # format -> (numpy dtype, components)
    'Float': ('<f4', 1), 'Float2': ('<f4', 2), 'Float3': ('<f4', 3), 'Float4': ('<f4', 4),
    'Half': ('<f2', 1), 'Half2': ('<f2', 2), 'Half3': ('<f2', 3), 'Half4': ('<f2', 4),
    'UByte4N': ('u1', 4), 'UByte4': ('u1', 4), 'Byte4N': ('i1', 4), 'UShort2': ('<u2', 2), 'UShort4': ('<u2', 4),
    'Short2N': ('<i2', 2), 'Short4N': ('<i2', 4), 'UShort2N': ('<u2', 2), 'UShort4N': ('<u2', 4),
}


def unpack_axis_angle(ts):
    """Frostbite AxisAngle_Compact (UByte4N) -> (normal, tangent, binormal); port of FET UnpackAxisAngleFrostbite."""
    ts = ts.astype(np.float64) / 255.0
    w = np.clip((ts[:, 3] * 255 + 0.25).astype(np.int64), 0, 255)
    f1, f2, f3, f4 = (w & 1) != 0, (w & 2) != 0, (w & 4) != 0, (w & 8) != 0
    b2, b3, b4 = (w >> 4) & 1, (w >> 5) & 1, (w >> 6) & 3
    x = (ts[:, 0] + b2) * 0.70710677 - 0.70710677
    y = (ts[:, 1] + b3) * 0.70710677 - 0.70710677
    ang = (ts[:, 2] + b4) * (np.pi / 2)
    z = np.sqrt(np.maximum(0.0, 1.0 - (x * x + y * y)))
    z = np.where(f1, -z, z)
    v = np.stack([x, y, z], 1)
    n = np.where(f3[:, None], v, np.where(f2[:, None], v[:, [0, 2, 1]], v[:, [2, 1, 0]]))
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    a = np.where(f2[:, None], np.stack([-n[:, 1], n[:, 0], np.zeros(len(n))], 1), np.stack([n[:, 2], np.zeros(len(n)), -n[:, 0]], 1))
    a /= np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    t = a * np.cos(ang)[:, None] + np.cross(n, a) * np.sin(ang)[:, None]
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    b = np.cross(n, t)
    b = np.where(f4[:, None], -b, b)
    return n, t, b


def decode_subset(lod, sub, data):
    """Returns {usage: array} and the triangle index array (local to the subset's vertices)."""
    out = {}
    pos = sub['vertex_offset']
    n = sub['vertices']
    streams = sub['decl0']['streams']
    by_stream = {}
    for e in sub['decl0']['elements']:
        by_stream.setdefault(e['stream'], []).append(e)
    for si, st in enumerate(streams):
        stride = st['stride']
        block = data[pos:pos + stride * n]
        pos += stride * n
        if stride == 0:
            continue
        raw = np.frombuffer(block, dtype=np.uint8).reshape(n, stride)
        for e in by_stream.get(si, []):
            dt, c = FMT[e['format']]
            size = np.dtype(dt).itemsize * c
            arr = raw[:, e['offset']:e['offset'] + size].copy().view(dt).reshape(n, c)
            out[e['usage']] = arr
    unit = lod['index_unit'] // 8  # IndexUnitSize is in bits
    istart = lod['vertex_size'] + sub['start'] * unit
    cnt = sub['prims'] * 3
    idx = np.frombuffer(data[istart:istart + cnt * unit], dtype='<u2' if unit == 2 else '<u4').astype(np.int64)
    return out, idx.reshape(-1, 3)
