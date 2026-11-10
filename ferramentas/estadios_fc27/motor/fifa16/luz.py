"""Pré-cálculo de luz de outro estádio do FC 27 no estádio convertido (experimental).

A torcida, as cadeiras e o resto do estádio recebem luz rebatida do Enlighten, pré-calculado pela EA para cada estádio:
os probes ficam em volta da torcida original (no FC 26, mover volumes ou refazer o proxy da torcida não criou luz nova).
Todos os estádios do FC 27 ligam a luz do mesmo jeito que o El Grandioso:
  - nível principal: DynamicEnlightenEntityData.EnlightenData -> EnlightenDataAsset do estádio;
  - world part lighting_flux*: StaticEnlightenEntityData.EnlightenData -> StaticEnlightenData (flux da noite) e
    .DynamicEnlightenData -> o mesmo EnlightenDataAsset;
  - world part lighting_main: SpatialPrefabReferenceObjectData -> prefab de volumes (visenviros/base_volume*).
O jogo já usa o mesmo prefab de volumes em estádios diferentes (ex.: base_volumes_falmer_340 em cinco estádios); o
Enlighten de um estádio nunca é usado por outro nos dados nativos, por isso a troca dele é experimental.
A troca aponta essas três referências do El Grandioso duplicado para os assets nativos do estádio escolhido (que entram
nos bundles do estádio novo com os bytes originais, como os assets de biblioteca de uma duplicata) e passa as coordenadas
de radiosidade (o lugar no atlas do Enlighten) dos meshes para o atlas do estádio escolhido: um texel de uma
arquibancada dele para os seis hospedeiros e o telão, e o vértice mais próximo do gramado dele para cada vértice do gramado.
"""
from __future__ import annotations
import collections
import json
import re
import struct
import uuid
from pathlib import Path

import numpy as np

from .. import base
from ..base import falha, sha256
from ..duplicar import tokens_estadios
from . import analise, malha

RES_MESH, RES_TEXTURE = 0x49b156d4, 0x6bde20ba
RAIO = 2.0  # m: um lugar novo a até 2 m de um lugar do estádio do FC 27 cai na luz pré-calculada dele
MESH_TIPOS = ('RigidMeshAsset', 'CompositeMeshAsset')


# ------------------------------------------------------------------ assentos dos estádios do FC 27
def assentos_fc27(amb, ids, work):
    """{id: array (n, 3)} das posições da torcida dos estádios (CrowdPlacementPointCloudDataAsset), guardadas em .npy."""
    c = amb.indice()
    toks = tokens_estadios(c)
    pasta = amb.pasta_jogo() / 'torcidas'
    pasta.mkdir(parents=True, exist_ok=True)
    out, faltam = {}, []
    for sid in ids:
        f = pasta / f'{sid}.npy'
        if f.is_file():
            out[sid] = np.load(f)
        else:
            faltam.append(sid)
    if faltam:
        sel = {}
        idx_tok = {}
        for b in c['bundles']:
            for sid in faltam:
                if f'/{toks[sid]}/' in b['name']:
                    idx_tok[b['index']] = sid
        for e in c['ebx']:
            if e['type'] == 'CrowdPlacementPointCloudDataAsset':
                donos = {idx_tok[i] for i in e['bundles'] if i in idx_tok}
                if len(donos) == 1:
                    sel.setdefault(next(iter(donos)), []).append(e)
        tmp = Path(work) / 'torcidas'
        tmp.mkdir(parents=True, exist_ok=True)
        jobs, quem = [], []
        for sid, ebxs in sel.items():
            for k, e in enumerate(ebxs):
                p, _ = amb.native('ebx', e['name'])
                o = tmp / f'{sid}_{k}.json'
                if o.exists():
                    o.unlink()
                jobs.append({'kind': 'dump', 'input': str(p), 'output': str(o)})
                quem.append((sid, o))
        for k in range(0, len(jobs), 60):
            base.progresso(100 * k / max(1, len(jobs)), f'lendo a torcida dos estádios ({k}/{len(jobs)})')
            amb.run_sdk(jobs[k:k + 60], tmp, 'torcidas')
        pts = collections.defaultdict(list)
        for sid, o in quem:
            d = json.loads(o.read_text(encoding='utf8'))
            pts[sid].append(np.array([[x['Position']['x'], x['Position']['y'], x['Position']['z']] for x in d['instances'][0]['fields'].get('Data', [])],
                                     np.float32).reshape(-1, 3))
            o.unlink()
        for sid in faltam:
            a = np.concatenate(pts[sid]) if pts.get(sid) else np.zeros((0, 3), np.float32)
            np.save(pasta / f'{sid}.npy', a)
            out[sid] = a
    return out


def cobertura(novos, antigos, raio=RAIO):
    """Fração dos lugares novos com um lugar antigo a até `raio` metros (grade de células do tamanho do raio)."""
    if not len(novos) or not len(antigos):
        return 0.0
    cel = {}
    ca = np.floor(antigos / raio).astype(np.int64)
    chaves, inv = np.unique(ca, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    ordem = np.argsort(inv, kind='stable')
    cortes = np.searchsorted(inv[ordem], np.arange(len(chaves) + 1))
    for j, k in enumerate(map(tuple, chaves.tolist())):
        cel[k] = antigos[ordem[cortes[j]:cortes[j + 1]]]
    cn = np.floor(novos / raio).astype(np.int64)
    ok = np.zeros(len(novos), bool)
    grupos = collections.defaultdict(list)
    for i, k in enumerate(map(tuple, cn.tolist())):
        grupos[k].append(i)
    viz = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
    for k, idx in grupos.items():
        cand = [cel[(k[0] + dx, k[1] + dy, k[2] + dz)] for dx, dy, dz in viz if (k[0] + dx, k[1] + dy, k[2] + dz) in cel]
        if not cand:
            continue
        cand = np.concatenate(cand)
        p = novos[idx]
        d2 = ((p[:, None, :] - cand[None, :, :]) ** 2).sum(2).min(1)
        ok[idx] = d2 <= raio * raio
    return float(ok.mean())


def avaliar(amb, pasta16, ids=None):
    """Estádios do FC 27 ordenados pela cobertura da torcida do FIFA 16 pela luz pré-calculada de cada um."""
    from .. import catalogo
    sa, sid16 = analise.localizar(pasta16)
    f = sa / 'crowdplacement' / f'crowd_{sid16}_1.dat'
    if not f.is_file():
        falha('o estádio do FIFA 16 não tem crowd_<id>_1.dat: sem torcida, não há o que avaliar')
    t = analise.ler_torcida(f)
    keep = t['rec'][:, 22] != 0  # a faixa de segurança vazia sai, como na conversão
    novos = t['pos'][keep]
    # amostra fixa (um lugar a cada k) para ordenar os 180 e tantos estádios em segundos; erro de ~1 ponto percentual
    amostra = novos[::max(1, len(novos) // 6000)]
    cat = catalogo.catalogo(amb)
    alvo = [e for e in cat['estadios'] if ids is None or e['id'] in ids]
    work = base.pasta_trabalho('luz')
    base.etapa('luz', 'Avaliando o pré-cálculo de luz dos estádios do FC 27')
    pts = assentos_fc27(amb, [e['id'] for e in alvo], work)
    c = amb.indice()
    out = []
    for k, e in enumerate(alvo):
        base.progresso(100 * k / max(1, len(alvo)), e['nome'])
        a = pts.get(e['id'])
        if a is None or not len(a):
            continue
        r = np.hypot(a[:, 0], a[:, 2])
        ok, motivo = suporte_rapido(c, e['token'])
        out.append(dict(id=e['id'], nome=e['nome'], token=e['token'], cobertura=round(100 * cobertura(amostra, a.astype(np.float64)), 1),
                        lugares=int(len(a)), raio=[round(float(r.min())), round(float(r.max()))], altura=[round(float(a[:, 1].min()), 1), round(float(a[:, 1].max()), 1)],
                        suporta=ok, motivo=motivo))
    out.sort(key=lambda x: (-x['cobertura'], x['id']))
    rn = np.hypot(novos[:, 0], novos[:, 2])
    return dict(fifa16_id=sid16, lugares=int(len(novos)), raio=RAIO, torcida=dict(raio=[round(float(rn.min())), round(float(rn.max()))],
                altura=[round(float(novos[:, 1].min()), 1), round(float(novos[:, 1].max()), 1)]), candidatos=out)


def _indice_luz(c):
    """Por pasta de estádio: EnlightenDataAsset, StaticEnlightenData e os EBX de mundo (uma passada no índice, guardada)."""
    if '_luz' not in c:
        rx = re.compile(r'content/worlds/stadiums/([a-z0-9_]+?_\d+)/', re.I)
        por = collections.defaultdict(lambda: dict(enlighten=[], flux=[], mundo=[]))
        for e in c['ebx']:
            m = rx.match(e['name'])
            if not m:
                continue
            x = por[m.group(1).lower()]
            if e['type'] == 'EnlightenDataAsset':
                x['enlighten'].append(e)
            elif e['type'] == 'StaticEnlightenData':
                x['flux'].append(e)
            elif e['type'] in ('WorldPartData', 'SubWorldData', 'LayerData', 'DetachedSubWorldData'):
                x['mundo'].append(e)
        c['_luz'] = dict(por)
    return c['_luz']


def _volume(c, part):
    nm = (c['ebx_by_part'].get(part) or {}).get('name', '')
    return 'lighting/visenviros/base_volume' in nm.lower()


def mundos_de_luz(c, tok):
    """O nível, as world parts que usam o Enlighten do estádio e as que colocam o prefab de volumes (pelas dependências)."""
    x = _indice_luz(c).get(tok.lower())
    if not x or len(x['enlighten']) != 1:
        return None, f"{len(x['enlighten']) if x else 0} EnlightenDataAsset"
    if not x['flux']:
        return None, 'sem StaticEnlightenData'
    enl = x['enlighten'][0]['partition']
    usam = [w['name'] for w in x['mundo'] if enl in w['dependencies']]
    vol = [w['name'] for w in x['mundo'] if any(_volume(c, d) for d in w['dependencies'])]
    if len(usam) < 2:
        return None, 'Enlighten sem as world parts de sempre'
    if not vol:
        return None, 'sem prefab de volumes de luz'
    return list(dict.fromkeys(usam + vol)), ''


def suporte_rapido(c, tok):
    nomes, motivo = mundos_de_luz(c, tok)
    return nomes is not None, motivo


# ------------------------------------------------------------------ estrutura de luz de um estádio
def _ptr(v):
    if isinstance(v, str) and v.startswith('ptr:ext:'):
        p, i = v[8:].split('/')
        return p, i
    return None


def estrutura(amb, tok, work, dumps_de=None, nome_de=None):
    """As três referências de luz de um estádio: {nivel, dyn: (índice, ptr), flux: [(world, índice, ptr_flux, ptr_dyn)],
    volumes: (world, índice, ptr)} lidas dos dumps do SDK (nativos, ou do projeto com dumps_de)."""
    pref = f'content/worlds/stadiums/{tok}/'
    c = amb.indice()
    nivel = pref + tok
    if dumps_de:
        nomes = [nivel] + [n for n in dumps_de('listar') if n.lower().startswith(pref.lower() + 'lighting')]
        dumps = {n.lower(): dumps_de(n) for n in nomes}
    else:
        mundos, motivo = mundos_de_luz(c, tok)
        if mundos is None:
            falha(f'{tok}: {motivo}')
        nomes = list(dict.fromkeys([nivel] + mundos))
        dumps = amb.dumps(nomes, work)
    est = dict(nivel=nivel, dyn=None, flux=[], volumes=None)
    d = dumps[nivel.lower()]
    dyn = [(i['index'], _ptr(i['fields'].get('EnlightenData'))) for i in d['instances'] if i['type'].endswith('.DynamicEnlightenEntityData')]
    if len(dyn) != 1 or dyn[0][1] is None:
        falha(f'{tok}: esperado um DynamicEnlightenEntityData no nível, achados {len(dyn)}')
    est['dyn'] = dyn[0]
    for n, dd in dumps.items():
        if n == nivel.lower():
            continue
        for i in dd['instances']:
            t = i['type']
            if t.endswith('.StaticEnlightenEntityData'):
                est['flux'].append((dd['name'], i['index'], _ptr(i['fields'].get('EnlightenData')), _ptr(i['fields'].get('DynamicEnlightenData'))))
            if t.endswith('SpatialPrefabReferenceObjectData'):
                bp = _ptr(i['fields'].get('Blueprint'))
                nm = (nome_de(bp[0]) if nome_de else (c['ebx_by_part'].get(bp[0]) or {}).get('name', '')) if bp else ''
                nm = (nm or '').lower()
                if 'visenviros/base_volume' in nm and (est['volumes'] is None or dd['name'].lower().endswith('/lighting_main')):
                    est['volumes'] = (dd['name'], i['index'], bp, nm)
    if not est['flux']:
        falha(f'{tok}: sem StaticEnlightenEntityData')
    return est


# ------------------------------------------------------------------ preparação e aplicação na conversão
def preparar(conv):
    """Lê a luz do estádio escolhido antes de montar os meshes (os texels de radiosidade vêm do atlas dele)."""
    amb = conv.amb
    X = int(conv.rc['luz'])
    c = amb.indice()
    toks = tokens_estadios(c)
    if X not in toks:
        falha(f'estádio {X} (pré-cálculo de luz) não existe no jogo')
    tokx = toks[X]
    work = conv.work / 'luz'
    work.mkdir(parents=True, exist_ok=True)
    ex = estrutura(amb, tokx, work)
    # flux: o da noite (não o do "bootflow"), e com o Dynamic do próprio nível
    flux = [f for f in ex['flux'] if f[3] and f[3][0] == ex['dyn'][1][0]]
    flux = sorted(flux, key=lambda f: ('bootflow' in f[0].lower(), f[0]))
    if not flux:
        falha(f'{tokx}: nenhum StaticEnlightenEntityData usa o Enlighten do nível')
    if ex['volumes'] is None:
        falha(f'{tokx}: lighting_main sem prefab de volumes de luz')
    sel = {bi for bi, b in enumerate(c['bundles']) if f'/{tokx}/' in b['name']}
    # meshes do estádio escolhido com radiosidade: o maior para os hospedeiros, o gramado para o gramado
    meshes = []
    for e in c['ebx']:
        if e['type'] in MESH_TIPOS and set(e['bundles']) & sel:
            r = c['res_by_name'].get(e['name'].lower())
            if r is not None and r['restype'] == RES_MESH:
                meshes.append((e, r))
    meshes.sort(key=lambda er: -er[1]['original_size'])
    pitch = [er for er in meshes if er[0]['name'].lower().endswith('/pitch_mesh') or er[0]['name'].lower().endswith('pitch_mesh')]
    texel = None
    escolhido = None
    for e, r in [er for er in meshes if er not in pitch][:6]:
        md = conv.mesh_dump('luz_' + r['name'], amb.native('res', r['name'])[0], r['resmeta'])
        nl = md['lods'][0]
        cand = [k for k, s in enumerate(nl['subsets']) if any(el['usage'] == 'RadiosityTexCoord' for el in s['decl0']['elements'])]
        if not cand or nl['chunk'] == base.ZERO:  # dados no próprio RES (sem chunk): fica para o próximo mesh
            continue
        data, _ = amb.chunk_bytes(nl['chunk'])
        k = max(cand, key=lambda i: nl['subsets'][i]['vertices'])
        a, _ = malha.decode_subset(nl, nl['subsets'][k], data)
        rr = a['RadiosityTexCoord']
        med = np.median(rr[:, :2], 0)
        i = int(np.argmin(np.sum((rr[:, :2] - med) ** 2, 1)))
        texel = [float(rr[i, 0]), float(rr[i, 1]), float(rr[i, 2])]
        escolhido = e['name']
        break
    if texel is None:
        falha(f'{tokx}: nenhum mesh com coordenadas de radiosidade')
    gramado = None
    if pitch:
        e, r = pitch[0]
        res_path = amb.native('res', r['name'])[0]
        md = conv.mesh_dump('luz_' + r['name'], res_path, r['resmeta'])
        nl = md['lods'][0]
        if nl['chunk'] == base.ZERO:
            # vértices dentro do próprio RES (sem chunk): o ConvertTool exporta os dados inline
            inl = work / ('gramado_inline_' + sha256(r['name'].encode())[:12] + '.bin')
            if inl.exists():
                inl.unlink()
            conv.run([dict(kind='mesh_edit', input=str(res_path), meta=r['resmeta'], export_inline=str(inl))], 'luz_gramado_inline')
            data = inl.read_bytes()
        else:
            data, _ = amb.chunk_bytes(nl['chunk'])
        P, R = [], []
        for s in nl['subsets']:
            if not any(el['usage'] == 'RadiosityTexCoord' for el in s['decl0']['elements']):
                continue
            a, _ = malha.decode_subset(nl, s, data)
            P.append(a['Pos'][:, :3].astype(np.float64))
            R.append(a['RadiosityTexCoord'][:, :3].astype(np.float32))
        if P:
            gramado = (np.concatenate(P), np.concatenate(R))
    conv.luz = dict(id=X, token=tokx, estrutura=ex, flux=flux[0], texel=texel, mesh_texel=escolhido, gramado=gramado)
    conv.report['luz'] = dict(estadio=X, token=tokx, enlighten=(c['ebx_by_part'].get(ex['dyn'][1][0]) or {}).get('name'),
                              flux=(c['ebx_by_part'].get(flux[0][2][0]) or {}).get('name'), volumes=ex['volumes'][3],
                              texel_de=escolhido, gramado='vértice mais próximo do gramado dele' if gramado else 'texel único')


def radiosidade_gramado(conv, data, lod):
    """Troca a RadiosityTexCoord de cada vértice do gramado pela do vértice mais próximo (em XZ) do gramado do estádio escolhido."""
    L = conv.luz
    for s in lod['subsets']:
        el = next((e for e in s['decl0']['elements'] if e['usage'] == 'RadiosityTexCoord'), None)
        if el is None:
            continue
        if el['format'] != 'Float3' or el['offset'] != 0:
            falha('radiosidade do gramado fora do formato esperado (Float3 num fluxo próprio)')
        n = s['vertices']
        streams = s['decl0']['streams']
        off = s['vertex_offset'] + sum(streams[k]['stride'] * n for k in range(el['stream']))
        if streams[el['stream']]['stride'] != 12:
            falha('fluxo de radiosidade do gramado com stride inesperado')
        a, _ = malha.decode_subset(lod, s, bytes(data))
        if L['gramado'] is not None:
            P, R = L['gramado']
            q = a['Pos'][:, :3].astype(np.float64)
            novo = np.empty((n, 3), np.float32)
            for k0 in range(0, n, 2048):
                d2 = ((q[k0:k0 + 2048, None, [0, 2]] - P[None, :, [0, 2]]) ** 2).sum(2)
                novo[k0:k0 + 2048] = R[np.argmin(d2, 1)]
        else:
            novo = np.tile(np.array(L['texel'], np.float32), (n, 1))
        data[off:off + 12 * n] = novo.astype('<f4').tobytes()


def aplicar(conv):
    """As três referências de luz do El Grandioso duplicado passam para o estádio escolhido; os assets dele entram nos bundles."""
    amb, c, L = conv.amb, conv.amb.indice(), conv.luz
    S, tok = conv.S, conv.tok
    work = conv.work / 'luz'
    proj_dump = lambda n: conv.ebx_dump(n)
    nomes_proj = [e['name'] for e in conv.p.parsed['ebx'] if e['name'].lower().startswith((S + 'lighting').lower())]
    alvo = estrutura(amb, tok, work, dumps_de=lambda n: nomes_proj if n == 'listar' else proj_dump(n),
                     nome_de=lambda part: conv.part_name(f'ptr:ext:{part}/x'))
    ex, fx = L['estrutura'], L['flux']
    dyn_ptr = ex['dyn'][1]
    flux_ptr = fx[2]
    vol_ptr = ex['volumes'][2]
    val = lambda p: {'ext': [p[0], p[1]]}
    conv.ebx_edit_mais(alvo['nivel'], [dict(op='set', target={'index': alvo['dyn'][0]}, path='EnlightenData', value=val(dyn_ptr))], 'luz_nivel')
    for world, idx, _, _ in alvo['flux']:
        conv.ebx_edit_mais(world, [dict(op='set', target={'index': idx}, path='EnlightenData', value=val(flux_ptr)),
                                   dict(op='set', target={'index': idx}, path='DynamicEnlightenData', value=val(dyn_ptr))], 'luz_flux')
    if alvo['volumes'] is None:
        falha('lighting_main do El Grandioso sem o prefab de volumes')
    conv.ebx_edit_mais(alvo['volumes'][0], [dict(op='set', target={'index': alvo['volumes'][1]}, path='Blueprint', value=val(vol_ptr))], 'luz_volumes')
    # Assets nativos do estádio escolhido nos bundles das world parts que os citam (com dependências que só existem nos bundles dele).
    sel = {bi for bi, b in enumerate(c['bundles']) if f'/{L["token"]}/' in b['name']}
    destino = {}
    nivel_b = conv.p.record('ebx', alvo['nivel'])['addedbundles']
    destino[dyn_ptr[0]] = list(nivel_b)
    for world, _, _, _ in alvo['flux']:
        destino.setdefault(flux_ptr[0], [])
        destino[flux_ptr[0]] += [b for b in conv.p.record('ebx', world)['addedbundles'] if b not in destino[flux_ptr[0]]]
        destino[dyn_ptr[0]] += [b for b in conv.p.record('ebx', world)['addedbundles'] if b not in destino[dyn_ptr[0]]]
    destino[vol_ptr[0]] = list(conv.p.record('ebx', alvo['volumes'][0])['addedbundles'])
    so_dele = lambda e: bool(e['bundles']) and set(e['bundles']) <= sel
    fila = list(destino.items())
    vistos = {}
    while fila:
        part, bs = fila.pop()
        e = c['ebx_by_part'].get(part)
        if e is None:
            falha('asset de luz desconhecido do cache: ' + part)
        if part in vistos:
            novos = [b for b in bs if b not in vistos[part]]
            if not novos:
                continue
            vistos[part] += novos
        else:
            vistos[part] = list(bs)
        for d in e['dependencies']:
            de = c['ebx_by_part'].get(d)
            if de is not None and so_dele(de) and de['type'] not in ('ClassInfoAsset', 'SchematicsAsset'):
                fila.append((d, vistos[part]))
    cas = amb.cas()
    nres = nchunk = 0
    tex_jobs = []
    for part, bs in vistos.items():
        e = c['ebx_by_part'][part]
        _, encoded, _ = cas.read_asset(e)
        conv.plano.atribuir_nativo('ebx', e['name'], {'name': e['name'], 'is_added': False, 'original_sha1': e['sha1'], 'bundle_assignment_only': True,
                                                      'addedbundles': bs, 'original_size': e['original_size'], 'compression_level': 7}, encoded, 'cas')
        r = c['res_by_name'].get(e['name'].lower())
        if r is not None:
            _, renc, _ = cas.read_asset(r)
            conv.plano.atribuir_nativo('res', r['name'], {'name': r['name'], 'is_added': False, 'original_sha1': r['sha1'], 'bundle_assignment_only': True,
                                                          'addedbundles': bs, 'original_size': r['original_size'], 'compression_level': 7}, renc, 'cas')
            nres += 1
            if r['restype'] == RES_TEXTURE:
                tex_jobs.append((r, bs))
    if tex_jobs:
        jobs = [{'kind': 'texture_info', 'input': str(amb.native('res', r['name'])[0])} for r, _ in tex_jobs]
        rows = amb.run_sdk(jobs, work, 'luz_tex')['rows']
        h = amb.hashes([r['name'] for r, _ in tex_jobs], work, 'luz_h32')
        for (r, bs), row in zip(tex_jobs, rows):
            cid = row['chunk']
            if cid == base.ZERO:
                continue
            ch = c['chunk_by_id'].get(cid)
            if ch is None:
                falha('chunk de textura de luz fora do cache: ' + cid)
            enc, _ = cas.read_encoded(ch)
            mode = uuid.UUID(cid).bytes_le[15] & 3
            rec = {'id': cid, 'is_added': False, 'original_sha1': ch['sha1'], 'bundle_assignment_only': True, 'addedbundles': bs,
                   'logical_size': ch['logical_size'], 'h32': int(h[r['name']]['djb2_lower64']), 'compression_level': 7 if mode == 1 else 8}
            if ch['logical_offset']:
                rec['logical_offset'] = ch['logical_offset']
            conv.plano.atribuir_nativo('chunk', cid, rec, enc, 'cas')
            nchunk += 1
    conv.report['luz'].update(ebx_nativos=len(vistos), res_nativos=nres, chunks_nativos=nchunk)
