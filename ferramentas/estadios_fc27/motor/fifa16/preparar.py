"""Preparação da geometria e das texturas de um estádio do FIFA 16 para a conversão (Python 3.12 + numpy).

A receita (motor/fifa16/analise.py sugere uma, a interface ajusta) diz o papel de cada peça (primitiva do RX3):
descartar, opaco, alpha, telão, grama ou banner, a ordem das camadas do chão e as peças que ficam com um lado só.
Grava, sem sobrescrever:
  subsets.json / geometry.bin   um subset por material: metros, soldado, com normais/tangentes/binormais e UV0.
                                faces "vista": cada face opaca do lado para onde apontam as normais do FIFA 16, mais o
                                verso só onde ele é visto do campo (ou onde as normais discordam); faces "dupla": os dois
                                lados (o FIFA 16 desenhava os dois). Subsets acima de max_vertices viram peças do mesmo
                                material (índices de 16 bits). As telas do telão vão num subset próprio, uma parte por lado.
  textures.json / textures/*.bin  cadeias de mips BC1/BC3: os mips do FIFA 16 byte a byte, os que faltam são gerados
  locators.json                 marcadores (slc, confete, bandeiras) em metros
  banners.json                  triângulos (m) das peças com o papel "banner", que saem do modelo: no lugar delas vão os
                                banners dos times do FC 27 (motor/fifa16/banners.py)
  report.json                   o que entrou, o que saiu e por quê
Coordenadas: o FIFA 16 usa centímetros, Y para cima, X ao longo do campo, Z na largura, bancos em -Z; o FC 27 usa os
mesmos eixos em metros, então a única transformação é a escala. Face da frente no FC 27: cross(v1-v0, v2-v0)·n > 0.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

from . import bcn, rx3

ALPHA_OFFSET = 0.015  # decalques alpha saem da superfície onde estão, na direção da normal da face
GRASS_TINT = np.array([0.42, 0.62, 0.26], np.float32)
VIEW_REF = np.array([0.0, 5.0, 0.0])  # faces "vista": o verso fica quando este ponto (acima do centro do campo) o vê

PADRAO = dict(faces='view', sombra_mesclada=False, max_vertices=60000, um_lado=[], chao={}, telao=[], grama=[], descartar={},
              papel={}, prefixo='fifa16', tom_grama=GRASS_TINT.tolist(), vista=VIEW_REF.tolist(), deslocamento_alpha=ALPHA_OFFSET)


def face_normals(p):
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    ln = np.linalg.norm(n, axis=1)
    return n, ln


def expand_double_sided(pos, nrm, uv, has_normals):
    """Triangle soup (t,3,...) -> both faces, each with normals that face its own side."""
    n, ln = face_normals(pos)
    ok = ln > 1e-10
    pos, nrm, uv, n, ln = pos[ok], nrm[ok], uv[ok], n[ok], ln[ok]
    fn = n / ln[:, None]
    out = []
    for sign, order in ((1.0, [0, 1, 2]), (-1.0, [0, 2, 1])):
        f = fn * sign
        p = pos[:, order]
        t = uv[:, order]
        if has_normals:
            vn = nrm[:, order]
            l = np.linalg.norm(vn, axis=2, keepdims=True)
            vnn = vn / np.maximum(l, 1e-12)
            good = (l[..., 0] > 0.5) & (np.einsum('tvk,tk->tv', vnn, f) > 0.3)
            vnorm = np.where(good[..., None], vnn, f[:, None, :])
        else:
            vnorm = np.repeat(f[:, None, :], 3, 1)
        out.append((p, vnorm, t))
    return [np.concatenate(x) for x in zip(*out)]


def expand_view_sided(pos, nrm, uv, has_normals, single=False, view_ref=None):
    """Triangle soup (t,3,...) -> the side its FIFA 16 corner normals face; the other side too where the reference
    point above the pitch sees the back (unless single) or where the corners disagree. No normals: both sides."""
    if not has_normals:
        return expand_double_sided(pos, nrm, uv, False)
    n, ln = face_normals(pos)
    ok = ln > 1e-10
    pos, nrm, uv, n, ln = pos[ok], nrm[ok], uv[ok], n[ok], ln[ok]
    fn = n / ln[:, None]
    l = np.linalg.norm(nrm, axis=2, keepdims=True)
    vnn = nrm / np.maximum(l, 1e-12)
    d = np.einsum('tvk,tk->tv', vnn, fn)
    agree, disagree = (d > 0.3).all(1), (d < -0.3).all(1)
    mixed = ~(agree | disagree)
    front = np.where(disagree[:, None], -fn, fn)
    ref = VIEW_REF if view_ref is None else np.asarray(view_ref, np.float64)
    back_seen = (np.einsum('tk,tk->t', front, ref[None, :] - pos.mean(1)) < 0) & (not single)
    emit = {1.0: agree | mixed | (disagree & back_seen), -1.0: disagree | mixed | (agree & back_seen)}
    out = []
    for sign, order in ((1.0, [0, 1, 2]), (-1.0, [0, 2, 1])):
        k = emit[sign]
        f = fn[k] * sign
        vn, vl = vnn[k][:, order], l[k][:, order]
        good = (vl[..., 0] > 0.5) & (np.einsum('tvk,tk->tv', vn, f) > 0.3)
        out.append((pos[k][:, order], np.where(good[..., None], vn, f[:, None, :]), uv[k][:, order]))
    return [np.concatenate(x) for x in zip(*out)]


def split_pieces(P, N, U, T, B, I, max_v):
    """Welded subset -> pieces of at most max_v vertices (triangles ordered along the longest axis, re-indexed)."""
    if max_v is None or len(P) <= max_v:
        return [(P, N, U, T, B, I)]
    c = P[I].mean(1)
    axis = int(np.argmax(P.max(0) - P.min(0)))
    order = np.argsort(c[:, axis], kind='stable')
    pieces, cur, used = [], [], set()
    for t in order:
        tri = I[t]
        add = {int(v) for v in tri} - used
        if len(used) + len(add) > max_v:
            pieces.append(cur)
            cur, used = [], set()
            add = {int(v) for v in tri}
        used |= add
        cur.append(t)
    pieces.append(cur)
    out = []
    for tris in pieces:
        sub = I[np.array(tris)]
        verts, local = np.unique(sub.reshape(-1), return_inverse=True)
        out.append((P[verts], N[verts], U[verts], T[verts], B[verts], local.reshape(-1, 3).astype(np.uint32)))
    if sum(len(x[5]) for x in out) != len(I) or max(len(x[0]) for x in out) > max_v:
        raise ValueError('split lost triangles or exceeded the vertex limit')
    return out


def tangents(p, n, t):
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    d1, d2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(det) > 1e-12, 1.0 / np.where(np.abs(det) > 1e-12, det, 1), 0)
    T = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r[:, None]
    B = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r[:, None]
    T = np.repeat(T[:, None, :], 3, 1)
    B = np.repeat(B[:, None, :], 3, 1)
    # Gram-Schmidt against the vertex normal; fall back to any perpendicular axis.
    T = T - n * np.sum(T * n, -1, keepdims=True)
    lt = np.linalg.norm(T, axis=-1, keepdims=True)
    alt = np.cross(n, np.where(np.abs(n[..., 1:2]) < 0.9, [0, 1, 0], [1, 0, 0]))
    T = np.where(lt > 1e-8, T / np.maximum(lt, 1e-12), alt / np.linalg.norm(alt, axis=-1, keepdims=True))
    sign = np.where(np.sum(np.cross(n, T) * B, -1, keepdims=True) < 0, -1.0, 1.0)
    return T, np.cross(n, T) * sign


def weld(p, n, uv, tg, bn):
    """Merge corners with the same position, normal, UV and tangent-frame handedness; tangents are averaged."""
    flat = lambda a: a.reshape(-1, a.shape[-1])
    P, N, U, T, Bn = flat(p), flat(n), flat(uv), flat(tg), flat(bn)
    hand = np.sign(np.sum(np.cross(N, T) * Bn, 1, keepdims=True))
    key = np.concatenate([np.round(P * 1e4), np.round(N * 1e3), np.round(U * 1e5), hand], 1).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    acc = np.zeros((len(first), 3))
    np.add.at(acc, inv, T)
    Nw = N[first]
    acc = acc - Nw * np.sum(acc * Nw, 1, keepdims=True)
    ln = np.linalg.norm(acc, axis=1, keepdims=True)
    Tw = np.where(ln > 1e-8, acc / np.maximum(ln, 1e-12), T[first])
    Bw = np.cross(Nw, Tw) * hand[first]
    return P[first], Nw, U[first], Tw, Bw, inv.reshape(-1, 3).astype(np.uint32)


def bbox(p):
    return [float(x) for x in np.concatenate([p.min(0), p.max(0)])]


def stats(p, uv, idx):
    a, b, c = p[idx[:, 0]], p[idx[:, 1]], p[idx[:, 2]]
    wa = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    ta, tb, tc = uv[idx[:, 0]], uv[idx[:, 1]], uv[idx[:, 2]]
    ua = 0.5 * np.abs((tb - ta)[:, 0] * (tc - ta)[:, 1] - (tb - ta)[:, 1] * (tc - ta)[:, 0])
    return float(wa.sum()), float(np.sqrt(ua.sum() / wa.sum())) if wa.sum() > 0 else 0.0


def full_chain(mips, fmt, w, h):
    """FIFA 16 mips byte for byte, then generated ones down to 1x1."""
    out = [(mw, mh, bytes(d)) for mw, mh, d in mips]
    img = None
    while max(out[-1][0], out[-1][1]) > 1:
        lw, lh, ld = out[-1]
        if img is None:
            img = bcn.decode(ld, lw, lh, fmt)
        img = bcn.downsample(img)
        nw, nh = max(1, lw // 2), max(1, lh // 2)
        out.append((nw, nh, bcn.encode(img, fmt)))
    for i, (mw, mh, d) in enumerate(out):
        if (mw, mh) != (max(1, w >> i), max(1, h >> i)) or len(d) != bcn.mip_size(mw, mh, fmt):
            raise ValueError(f'bad mip {i}: {mw}x{mh} {len(d)}')
    return out


def recolour_chain(mips, fmt, fn):
    """Decode every mip, apply fn to RGBA, re-encode (used for the tinted grass and the blank panel)."""
    out = []
    for mw, mh, d in mips:
        out.append((mw, mh, bcn.encode(fn(bcn.decode(d, mw, mh, fmt)), fmt)))
    return out


def preparar(pasta16, out, receita):
    """Prepara o estádio da pasta do FIFA 16 em out (pasta nova) conforme a receita. Devolve o resumo."""
    from .analise import localizar
    r = dict(PADRAO, **receita)
    sa, sid = localizar(pasta16)
    if int(r.get('fifa16_id', sid)) != sid:
        raise ValueError(f'a receita é do estádio {r["fifa16_id"]}, a pasta é do {sid}')
    out = Path(out)
    if out.exists():
        raise ValueError('a pasta de preparação já existe: ' + str(out))
    drop = {int(k): v for k, v in r['descartar'].items()}
    papel = {int(k): v for k, v in r['papel'].items()}
    ground_dy = {int(k): float(v) for k, v in r['chao'].items()}
    single = {int(x) for x in r['um_lado']}
    jumbo_prims = {int(x) for x in r['telao']}
    grass_prims = {int(x) for x in r['grama']}
    tint = np.array(r['tom_grama'], np.float32)
    view_ref = np.array(r['vista'], np.float64)
    alpha_offset = float(r['deslocamento_alpha'])
    sides = r['faces']
    prefix = r['prefixo']
    model = rx3.RX3(sa / 'stadium' / f'stadium_{sid}.rx3')
    day = rx3.RX3(sa / 'stadium' / f'stadium_{sid}_1_textures.rx3')
    night_path = sa / 'stadium' / f'stadium_{sid}_3_textures.rx3'
    night = rx3.RX3(night_path) if night_path.is_file() else day
    tex_by_name = {t['name']: t for t in day.textures()}
    night_by_name = {t['name']: t for t in night.textures()}
    names = model.names_of(rx3.TEX)
    prims = model.primitives()
    (out / 'textures').mkdir(parents=True)
    report = dict(source=str(pasta16), fifa16_id=sid, kept=[], dropped=[], textures={}, notes=[])

    textures = {}  # key -> meta

    def add_texture(key, chain, fmt, sources, note=None):
        if key in textures:
            textures[key]['sources'] += sources
            return key
        blob = b''.join(d for _, _, d in chain)
        (out / 'textures' / (key + '.bin')).write_bytes(blob)
        textures[key] = dict(key=key, format=fmt, width=chain[0][0], height=chain[0][1], mips=len(chain), bytes=len(blob),
                             mip_sizes=[len(d) for _, _, d in chain], sha256=hashlib.sha256(blob).hexdigest(), sources=list(sources),
                             fifa_mips=None, note=note)
        return key

    def texture_for(prim):
        tex = prim['material']['textures']
        name = names[tex[0][1]] if tex and tex[0][1] < len(names) else ''
        t = tex_by_name.get(name)
        if t is None:
            # O FIFA 16 preenchia esta superfície na hora do jogo: um painel escuro fica no lugar.
            img = np.full((4, 4, 4), [24, 24, 26, 255], np.float32)
            chain = [(4, 4, bcn.encode(img, 'BC1'))]
            for w in (2, 1):
                chain.append((w, w, bcn.encode(img[:w, :w], 'BC1')))
            return add_texture('panel_dark', chain, 'BC1', [f"prim {prim['index']}: '{name}' sem textura no arquivo"]), None
        fmt = 'BC1' if t['format'] == 0 else 'BC3'
        mips = day.texture_mips(t, strict=False)
        if prim['index'] in grass_prims:
            chain = full_chain(mips, fmt, t['width'], t['height'])

            def tinge(img):
                lum = img[:, :, :3].mean(2, keepdims=True)
                rgb = np.clip(lum * tint[None, None, :] * 1.25, 0, 255)
                return np.concatenate([rgb, np.full_like(lum, 255)], 2)
            chain = recolour_chain(chain, 'BC1', tinge) if fmt == 'BC1' else recolour_chain(chain, fmt, tinge)
            key = 'grass_tinted_' + hashlib.sha256(b''.join(d for _, _, d in mips)).hexdigest()[:12]
            return add_texture(key, chain, fmt, [name], note='tinted with the FIFA 16 grass colour'), name
        digest = hashlib.sha256(b''.join(d for _, _, d in mips)).hexdigest()[:16]
        key = f'{name}_{digest[:8]}'.lower()
        if key not in textures:
            chain = full_chain(mips, fmt, t['width'], t['height'])
            add_texture(key, chain, fmt, [name])
            textures[key]['fifa_mips'] = len(mips)
            nt = night_by_name.get(name)
            if nt is not None and night.read(nt['offset'], nt['size']) != day.read(t['offset'], t['size']):
                textures[key]['note'] = 'night version differs (day version used: FC27 lights the stadium at run time)'
        else:
            textures[key]['sources'].append(name)
        return key, name

    geo = bytearray()
    subsets = []

    def emit(name, role, prim_ids, tex_key, P, N, U, T, B, I, extra=None):
        rec = dict(name=name, role=role, prims=prim_ids, texture=tex_key, vertices=int(len(P)), triangles=int(len(I)),
                   bbox=bbox(P), offset=len(geo))
        for arr in (P, N, T, B):
            geo.extend(np.ascontiguousarray(arr, '<f4').tobytes())
        geo.extend(np.ascontiguousarray(U, '<f4').tobytes())
        geo.extend(np.ascontiguousarray(I, '<u4').tobytes())
        rec['bytes'] = len(geo) - rec['offset']
        rec['area'], rec['texel_density'] = stats(P.astype(np.float64), U.astype(np.float64), I.astype(np.int64))
        if extra:
            rec.update(extra)
        subsets.append(rec)

    groups = {}  # (role, texture key) -> list of (prim, arrays)
    shadow = []
    jumbo = []
    faixas = []  # peças com o papel "banner": saem do modelo e recebem os banners dos times do FC 27 (motor/fifa16/banners.py)
    for p in prims:
        i = p['index']
        if i in drop:
            report['dropped'].append(dict(prim=i, name=p['name'], shader=p['material']['shader'], layer=p['layer'], reason=drop[i]))
            continue
        a = rx3.decode_vertices(p)
        idx = rx3.decode_indices(p)
        if p['primitive_type'] != 4 or len(idx) % 3:
            raise ValueError(f'a primitiva {i} não é uma lista de triângulos')
        pos = a['p0'][idx].reshape(-1, 3, 3).astype(np.float64) / 100.0
        if papel.get(i) == 'banner':
            faixas.append(dict(prim=i, nome=p['name'], camada=p['layer'], triangulos=np.round(pos, 3).reshape(-1).tolist()))
            report['dropped'].append(dict(prim=i, name=p['name'], shader=p['material']['shader'], layer=p['layer'], reason='banner dos times do FC 27'))
            continue
        has_n = 'n0' in a
        nrm = (a['n0'][idx] if has_n else np.zeros((len(idx), 3))).reshape(-1, 3, 3).astype(np.float64)
        uv = a['t0'][idx].reshape(-1, 3, 2).astype(np.float64)
        dy = ground_dy.get(i)
        if dy is not None:
            ground = np.abs(pos[..., 1]) < 0.05
            pos[..., 1] = np.where(ground, pos[..., 1] + dy, pos[..., 1])
        shader = p['material']['shader']
        if i in jumbo_prims:
            role = 'jumbotron'
        elif papel.get(i) in ('alpha', 'alphatest') or (papel.get(i) is None and shader == 'diffusealpha'):
            role = 'alphatest'
        else:
            role = 'opaque'
        if sides == 'view' and role == 'opaque':
            P, N, U = expand_view_sided(pos, nrm, uv, has_n, single=i in single, view_ref=view_ref)
        else:
            P, N, U = expand_double_sided(pos, nrm, uv, has_n)
        if role == 'alphatest':
            fn, ln = face_normals(P)
            P = P + (fn / ln[:, None])[:, None, :] * alpha_offset
        if role == 'jumbotron':
            # Só o lado virado para o campo (o material de telão do FC 27 tem um lado só e é desenhado ao vivo).
            fn, ln = face_normals(P)
            c = P.mean(1)
            keep = np.sum(fn * -c, 1) > 0
            jumbo.append((i, P[keep], N[keep], U[keep]))
            report['kept'].append(dict(prim=i, name=p['name'], shader=shader, layer=p['layer'], role=role, triangles=int(keep.sum())))
            continue
        T, B = tangents(P, N, U)
        tex_key, tex_name = texture_for(p)
        groups.setdefault((role, tex_key), []).append((i, P, N, U, T, B))
        report['kept'].append(dict(prim=i, name=p['name'], shader=shader, layer=p['layer'], role=role, texture=tex_name, texture_key=tex_key,
                                   triangles_fifa=int(len(idx) // 3), triangles_out=int(len(P)), ground_dy=dy,
                                   sides='normal side only' if sides == 'view' and role == 'opaque' and i in single else None))
        if role == 'opaque':
            shadow.append(P)

    max_v = r['max_vertices']
    for (role, tex_key), items in sorted(groups.items(), key=lambda kv: (kv[0][0], min(x[0] for x in kv[1]))):
        P = np.concatenate([x[1] for x in items]); N = np.concatenate([x[2] for x in items]); U = np.concatenate([x[3] for x in items])
        T = np.concatenate([x[4] for x in items]); B = np.concatenate([x[5] for x in items])
        Pw, Nw, Uw, Tw, Bw, I = weld(P, N, U, T, B)
        prims_in = sorted(x[0] for x in items)
        name = f"{prefix}_{'diffusealpha' if role == 'alphatest' else 'diffuseopaque'}_{prims_in[0]:03d}"
        pieces = split_pieces(Pw, Nw, Uw, Tw, Bw, I, max_v)
        for k, (Pp, Np, Up, Tp, Bp, Ip) in enumerate(pieces):
            emit(name if len(pieces) == 1 else f'{name}_p{k}', role, prims_in, tex_key, Pp, Np, Up, Tp, Bp, Ip,
                 extra=dict(material=name, piece=k, pieces=len(pieces)))

    if r['sombra_mesclada'] and shadow:
        S = np.concatenate(shadow).reshape(-1, 3)
        key = np.round(S * 1e4).astype(np.int64)
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        Sp = S[first]
        z = np.zeros_like(Sp)
        emit(f'{prefix}_shadow', 'shadow', [], None, Sp, z, np.zeros((len(Sp), 2)), z, z, inv.reshape(-1, 3).astype(np.uint32))

    if jumbo:
        P = np.concatenate([x[1] for x in jumbo]); N = np.concatenate([x[2] for x in jumbo]); U = np.concatenate([x[3] for x in jumbo])
        T, B = tangents(P, N, U)
        # Uma parte por lado do estádio: o eixo (x ou z) em que as telas ficam mais afastadas do centro.
        cen = P.mean(1)
        axis = 2 if np.abs(cen[:, 2]).mean() >= np.abs(cen[:, 0]).mean() else 0
        side = np.where(cen[:, axis] < 0, 0, 1)
        Pw, Nw, Uw, Tw, Bw, I = weld(P, N, U, T, B)
        part = np.zeros(len(Pw), np.int64)
        part[I.reshape(-1)] = np.repeat(side, 3)
        emit(f'{prefix}_jumbotron', 'jumbotron', sorted(x[0] for x in jumbo), None, Pw, Nw, Uw, Tw, Bw, I,
             extra=dict(part_of_vertex=part.tolist(), uv_range=[float(Uw.min()), float(Uw.max())]))

    (out / 'geometry.bin').write_bytes(bytes(geo))
    allp = np.concatenate([np.array(s['bbox']).reshape(2, 3) for s in subsets if s['role'] != 'shadow'])
    meta = dict(source=str(pasta16), sceneassets=str(sa), fifa16_id=sid, units='m',
                options=dict(sides=sides, shadow=bool(r['sombra_mesclada']), max_vertices=max_v, single=sorted(single), view_ref=view_ref.tolist()),
                subsets=subsets, bbox=[float(x) for x in np.concatenate([allp.min(0), allp.max(0)])],
                geometry_sha256=hashlib.sha256(bytes(geo)).hexdigest(),
                layout='per subset: pos f32x3, normal f32x3, tangent f32x3, binormal f32x3 (per vertex), uv0 f32x2, indices u32x3')
    (out / 'subsets.json').write_text(json.dumps(meta, indent=1), encoding='utf8')
    (out / 'textures.json').write_text(json.dumps(textures, indent=1), encoding='utf8')
    locs = [dict(name=l['name'].replace('_0_0_0_0_0_0', ''), position=[l['values'][0] / 100, l['values'][1] / 100, l['values'][2] / 100],
                 values=l['values'][3:]) for l in model.locators()]
    (out / 'locators.json').write_text(json.dumps(locs, indent=1), encoding='utf8')
    (out / 'banners.json').write_text(json.dumps(dict(unidade='m', pecas=faixas)), encoding='utf8')
    report['subsets'] = len(subsets)
    report['textures'] = {k: dict(sources=v['sources'], size=f"{v['width']}x{v['height']}", format=v['format'], mips=v['mips'],
                                  fifa_mips=v['fifa_mips'], note=v['note']) for k, v in textures.items()}
    (out / 'report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    return dict(subsets=len(subsets), textures=len(textures), vertices=sum(s['vertices'] for s in subsets),
                triangles=sum(s['triangles'] for s in subsets), geometry_mb=round(len(geo) / 2**20, 1),
                texture_mb=round(sum(v['bytes'] for v in textures.values()) / 2**20, 1), bbox=meta['bbox'], jumbotron=bool(jumbo))
