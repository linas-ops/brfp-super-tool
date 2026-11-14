"""Preparação da geometria, das texturas, da torcida e das lâmpadas de um estádio do PES 2021 para a conversão.

Grava a mesma pasta que a preparação do FIFA 16 (motor/fifa16/preparar.py), para a conversão seguir o mesmo caminho:
  subsets.json / geometry.bin   um subset por material (papel + textura): metros, soldado, com normais/tangentes/binormais
                                e UV0; subsets acima de max_vertices viram peças do mesmo material; as telas do telão num
                                subset próprio, uma parte por lado
  textures.json / textures/*.bin  cadeias de mips BC1/BC3: os mips do PES byte a byte, os que faltam são gerados
  locators.json                 vazio (o PES não tem marcadores de personagens no modelo)
  banners.json                  triângulos das peças com o papel "banner", que saem do modelo
  torcida.json / torcida.bin    lugares da torcida gerados das áreas do PES (motor/pes21/torcida.py), na altura dos degraus
  lampadas.json                 lâmpadas dos brilhos do PES, de dia e de noite (motor/pes21/brilhos.py)
  report.json                   o que entrou, o que saiu e por quê
O PES já usa metros, Y para cima e a mão direita, como o FC 27: a única transformação é a meia volta em torno do centro do
campo quando os bancos de reservas estão em +Z (receita "giro": 180). No PES cada malha é desenhada só pelo lado das
normais, a não ser que seja marcada como de dois lados (0x20): a receita traz as outras em "um_lado".
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from ..fifa16 import bcn
from ..fifa16.preparar import (ALPHA_OFFSET, GRASS_TINT, VIEW_REF, bbox, expand_double_sided, expand_view_sided, face_normals,
                               full_chain, recolour_chain, split_pieces, stats, tangents, weld)
from . import brilhos, estadio as E, torcida as T

PADRAO = dict(faces='view', sombra_mesclada=False, max_vertices=60000, um_lado=[], chao={}, telao=[], grama=[], descartar={},
              papel={}, prefixo='pes21', tom_grama=GRASS_TINT.tolist(), vista=VIEW_REF.tolist(), deslocamento_alpha=ALPHA_OFFSET, giro=0)


def girar(v, giro):
    """Meia volta em torno do eixo vertical (x e z trocam de sinal) quando giro = 180."""
    if int(giro) % 360 == 180:
        v = np.array(v, np.float64)
        v[..., 0] *= -1
        v[..., 2] *= -1
    elif int(giro) % 360:
        raise ValueError('giro desconhecido (use 0 ou 180): ' + str(giro))
    return v


def _painel(cor):
    img = np.full((4, 4, 4), cor, np.float32)
    chain = [(4, 4, bcn.encode(img, 'BC1'))]
    for w in (2, 1):
        chain.append((w, w, bcn.encode(img[:w, :w], 'BC1')))
    return chain


def cadeia(tex):
    """(formato 'BC1'|'BC3', cadeia completa de mips, quantos mips vieram do PES) de uma textura do PES. As BC1/BC3 entram
    byte a byte; as de 32 bits sem compressão são codificadas; outros formatos não são suportados (None)."""
    mips = tex.cadeia()
    if not mips:
        return None
    w, h = mips[0][0], mips[0][1]
    if tex.formato in ('BC1', 'BC3'):
        return tex.formato, full_chain(mips, tex.formato, w, h), len(mips)
    if tex.formato == 'BGRA8':
        img = np.frombuffer(mips[0][2], np.uint8).reshape(h, w, 4)[..., [2, 1, 0, 3]].astype(np.float32)
        fmt = 'BC3' if (img[..., 3] < 250).any() else 'BC1'
        return fmt, full_chain([(w, h, bcn.encode(img, fmt))], fmt, w, h), 0
    return None


def preparar(pasta, out, receita):
    """Prepara o estádio da pasta do PES 2021 em out (pasta nova) conforme a receita. Devolve o resumo."""
    r = dict(PADRAO, **receita)
    est = E.Estadio(pasta)
    if str(r.get('fonte_id', est.sid)).lower() != est.sid:
        raise ValueError(f'a receita é do estádio {r["fonte_id"]}, a pasta é do {est.sid}')
    out = Path(out)
    if out.exists():
        raise ValueError('a pasta de preparação já existe: ' + str(out))
    giro = int(r['giro'])
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
    (out / 'textures').mkdir(parents=True)
    report = dict(source=str(pasta), fonte='pes21', fonte_id=est.sid, giro=giro, kept=[], dropped=[], textures={}, notes=[])

    textures = {}

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

    por_caminho = {}  # (caminho, grama) -> chave

    def texture_for(peca, grama):
        mat = peca['malha']['material'] or dict(texturas={})
        cam = E.textura_de_cor(mat)
        name = cam.rsplit('/', 1)[-1]
        k = (cam.lower(), grama)
        if k in por_caminho:
            textures[por_caminho[k]]['sources'].append(name)
            return por_caminho[k], name
        tex = est.textura(cam) if cam else None
        pronto = None
        if tex is not None:
            try:
                pronto = cadeia(tex)
            except ValueError as ex:
                report['notes'].append(f'{name}: {ex}')
        if pronto is None:
            motivo = 'sem textura na pasta' if tex is None else f'formato {tex.formato} não suportado'
            base_aviso = f"peça {peca['prim']}: '{name}' {motivo}; entra um painel cinza"
            report['notes'].append(base_aviso)
            key = add_texture('panel_grey', _painel([120, 120, 124, 255]), 'BC1', [base_aviso])
            return key, None
        fmt, chain, do_pes = pronto
        digest = hashlib.sha256(b''.join(d for _, _, d in chain[:max(1, do_pes)])).hexdigest()
        limpo = re.sub(r'[^a-z0-9_]+', '_', Path(name).stem.lower()).strip('_') or 'textura'
        if grama:
            def tinge(img):
                lum = img[:, :, :3].mean(2, keepdims=True)
                rgb = np.clip(lum * tint[None, None, :] * 1.25, 0, 255)
                return np.concatenate([rgb, np.full_like(lum, 255)], 2)
            chain = recolour_chain(chain, fmt, tinge)
            key = add_texture('grass_tinted_' + digest[:12], chain, fmt, [name], note='tingida com a cor da grama (como no FIFA 16)')
        else:
            key = add_texture(f'{limpo}_{digest[:8]}', chain, fmt, [name])
            textures[key]['fifa_mips'] = do_pes
        por_caminho[k] = key
        return key, name

    geo = bytearray()
    subsets = []

    def emit(name, role, prim_ids, tex_key, P, N, U, T_, B, I, extra=None):
        rec = dict(name=name, role=role, prims=prim_ids, texture=tex_key, vertices=int(len(P)), triangles=int(len(I)),
                   bbox=bbox(P), offset=len(geo))
        for arr in (P, N, T_, B):
            geo.extend(np.ascontiguousarray(arr, '<f4').tobytes())
        geo.extend(np.ascontiguousarray(U, '<f4').tobytes())
        geo.extend(np.ascontiguousarray(I, '<u4').tobytes())
        rec['bytes'] = len(geo) - rec['offset']
        rec['area'], rec['texel_density'] = stats(P.astype(np.float64), U.astype(np.float64), I.astype(np.int64))
        if extra:
            rec.update(extra)
        subsets.append(rec)

    groups = {}
    shadow, jumbo, faixas = [], [], []
    sobras = 0
    for p in est.pecas():
        i, m = p['prim'], p['malha']
        mat = m['material'] or dict(shader='', nome='', texturas={})
        shader, camada = mat['shader'], p['modelo']['nome']
        if i in drop:
            report['dropped'].append(dict(prim=i, name=m['grupo'], shader=shader, layer=camada, reason=drop[i]))
            continue
        P0, N0, U0, idx, fora = est.geometria(p)
        sobras += fora
        if not len(idx):
            report['dropped'].append(dict(prim=i, name=m['grupo'], shader=shader, layer=camada, reason='sem triângulos no estádio'))
            continue
        P0 = girar(P0, giro)
        has_n = N0 is not None
        N0 = girar(N0, giro) if has_n else np.zeros_like(P0)
        pos = P0[idx]
        if papel.get(i) == 'banner':
            faixas.append(dict(prim=i, nome=m['grupo'], camada=camada, triangulos=np.round(pos, 3).reshape(-1).tolist()))
            report['dropped'].append(dict(prim=i, name=m['grupo'], shader=shader, layer=camada, reason='banner dos times do FC 27'))
            continue
        nrm, uv = N0[idx], U0[idx]
        dy = ground_dy.get(i)
        if dy is not None:
            ground = np.abs(pos[..., 1]) < 0.05
            pos = pos.copy()
            pos[..., 1] = np.where(ground, pos[..., 1] + dy, pos[..., 1])
        if i in jumbo_prims:
            role = 'jumbotron'
        elif papel.get(i) in ('alpha', 'alphatest'):
            role = 'alphatest'
        else:
            role = 'opaque'
        if sides == 'view' and role == 'opaque':
            Pt, Nt, Ut = expand_view_sided(pos, nrm, uv, has_n, single=i in single, view_ref=view_ref)
        else:
            Pt, Nt, Ut = expand_double_sided(pos, nrm, uv, has_n)
        if not len(Pt):
            report['dropped'].append(dict(prim=i, name=m['grupo'], shader=shader, layer=camada, reason='só triângulos sem área'))
            continue
        if role == 'alphatest':
            fn, ln = face_normals(Pt)
            Pt = Pt + (fn / ln[:, None])[:, None, :] * alpha_offset
        if role == 'jumbotron':
            fn, ln = face_normals(Pt)
            c = Pt.mean(1)
            keep = np.sum(fn * -c, 1) > 0
            jumbo.append((i, Pt[keep], Nt[keep], Ut[keep]))
            report['kept'].append(dict(prim=i, name=m['grupo'], shader=shader, layer=camada, role=role, triangles=int(keep.sum())))
            continue
        Tt, Bt = tangents(Pt, Nt, Ut)
        tex_key, tex_name = texture_for(p, i in grass_prims)
        groups.setdefault((role, tex_key), []).append((i, Pt, Nt, Ut, Tt, Bt))
        report['kept'].append(dict(prim=i, name=m['grupo'], shader=shader, layer=camada, role=role, texture=tex_name, texture_key=tex_key,
                                   triangles_pes=int(len(idx)), triangles_out=int(len(Pt)), ground_dy=dy,
                                   sides='só o lado das normais' if sides == 'view' and role == 'opaque' and i in single else None))
        if role == 'opaque':
            shadow.append(Pt)
    if not groups:
        raise ValueError('nenhuma peça do estádio ficou na conversão: confira a lista de peças')

    max_v = r['max_vertices']
    for (role, tex_key), items in sorted(groups.items(), key=lambda kv: (kv[0][0], min(x[0] for x in kv[1]))):
        P = np.concatenate([x[1] for x in items]); N = np.concatenate([x[2] for x in items]); U = np.concatenate([x[3] for x in items])
        Tg = np.concatenate([x[4] for x in items]); B = np.concatenate([x[5] for x in items])
        Pw, Nw, Uw, Tw, Bw, I = weld(P, N, U, Tg, B)
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

    if jumbo and sum(len(x[1]) for x in jumbo):
        P = np.concatenate([x[1] for x in jumbo]); N = np.concatenate([x[2] for x in jumbo]); U = np.concatenate([x[3] for x in jumbo])
        Tg, B = tangents(P, N, U)
        cen = P.mean(1)
        axis = 2 if np.abs(cen[:, 2]).mean() >= np.abs(cen[:, 0]).mean() else 0
        side = np.where(cen[:, axis] < 0, 0, 1)
        Pw, Nw, Uw, Tw, Bw, I = weld(P, N, U, Tg, B)
        part = np.zeros(len(Pw), np.int64)
        part[I.reshape(-1)] = np.repeat(side, 3)
        emit(f'{prefix}_jumbotron', 'jumbotron', sorted(x[0] for x in jumbo), None, Pw, Nw, Uw, Tw, Bw, I,
             extra=dict(part_of_vertex=part.tolist(), uv_range=[float(Uw.min()), float(Uw.max())]))

    (out / 'geometry.bin').write_bytes(bytes(geo))
    allp = np.concatenate([np.array(s['bbox']).reshape(2, 3) for s in subsets if s['role'] != 'shadow'])
    meta = dict(source=str(pasta), fonte='pes21', fonte_id=est.sid, units='m',
                options=dict(sides=sides, shadow=bool(r['sombra_mesclada']), max_vertices=max_v, single=sorted(single), view_ref=view_ref.tolist(),
                             giro=giro),
                subsets=subsets, bbox=[float(x) for x in np.concatenate([allp.min(0), allp.max(0)])],
                geometry_sha256=hashlib.sha256(bytes(geo)).hexdigest(),
                layout='per subset: pos f32x3, normal f32x3, tangent f32x3, binormal f32x3 (per vertex), uv0 f32x2, indices u32x3')
    (out / 'subsets.json').write_text(json.dumps(meta, indent=1), encoding='utf8')
    (out / 'textures.json').write_text(json.dumps(textures, indent=1), encoding='utf8')
    (out / 'locators.json').write_text('[]', encoding='utf8')
    (out / 'banners.json').write_text(json.dumps(dict(unidade='m', pecas=faixas)), encoding='utf8')

    # torcida: lugares das áreas do PES, na altura dos degraus da geometria preparada
    arq = est.arquivos()
    tor = None
    if arq['torcida'].is_file():
        areas = T.ler_areas(arq['torcida'])
        areas['quad'] = girar(areas['quad'], giro)
        tris = np.concatenate(shadow) if shadow else np.zeros((0, 3, 3))
        lug = T.lugares(areas, tris)
        n = len(lug['pos'])
        cor = np.zeros((n, 3), np.uint8)
        tem_cor = False
        if n and arq['cadeiras'].is_file():
            try:
                cor = T.cores(T.ler_png(arq['cadeiras']), lug['uv'])
                tem_cor = True
            except (OSError, ValueError) as ex:
                report['notes'].append(f'au_seat.png: {ex}')
        blob = np.zeros(n, dtype=[('pos', '<f4', 3), ('orient', '<f4'), ('cor', 'u1', 3), ('visitante', 'u1'), ('area', '<u4')])
        blob['pos'], blob['orient'], blob['cor'], blob['visitante'], blob['area'] = lug['pos'], lug['orient'], cor, lug['visitante'], lug['area']
        (out / 'torcida.bin').write_bytes(blob.tobytes())
        tor = dict(lugares=n, areas=int(len(areas['quad'])), areas_com_degraus=int(lug['areas_com_degraus']),
                   visitantes=int(lug['visitante'].sum()), sem_degrau=int(lug['sem_degrau']),
                   cores=tem_cor, registro='pos f32x3, orient f32, cor u8x3 (RGB), visitante u8, area u32', bytes_por_lugar=blob.dtype.itemsize,
                   sha256=hashlib.sha256(blob.tobytes()).hexdigest())
        (out / 'torcida.json').write_text(json.dumps(tor, indent=1), encoding='utf8')
    lamp = {}
    for k, a in (('dia', 'brilhos_dia'), ('noite', 'brilhos_noite')):
        if arq[a].is_file():
            try:
                lamp[k] = np.round(girar(brilhos.lampadas(arq[a]), giro), 4).tolist()
            except (OSError, ValueError) as ex:
                report['notes'].append(f'{arq[a].name}: {ex}')
    (out / 'lampadas.json').write_text(json.dumps(lamp), encoding='utf8')
    if sobras:
        report['notes'].append(f'{sobras} triângulos a mais de {E.LIMITE:.0f} m do centro do campo ficaram de fora (sobras escondidas pelo autor)')
    report['subsets'] = len(subsets)
    report['torcida'] = tor
    report['lampadas'] = {k: len(v) for k, v in lamp.items()}
    report['textures'] = {k: dict(sources=sorted(set(v['sources'])), size=f"{v['width']}x{v['height']}", format=v['format'], mips=v['mips'],
                                  pes_mips=v['fifa_mips'], note=v['note']) for k, v in textures.items()}
    (out / 'report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf8')
    return dict(subsets=len(subsets), textures=len(textures), vertices=sum(s['vertices'] for s in subsets),
                triangles=sum(s['triangles'] for s in subsets), geometry_mb=round(len(geo) / 2**20, 1),
                texture_mb=round(sum(v['bytes'] for v in textures.values()) / 2**20, 1), bbox=meta['bbox'], jumbotron=bool(jumbo),
                torcida=tor, lampadas=report['lampadas'], notas=report['notes'])
