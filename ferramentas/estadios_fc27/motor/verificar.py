"""Verificação estática de um projeto gravado, lida de volta do próprio arquivo.

Para cada estádio novo (duplicado ou convertido) confere de ponta a ponta, decodificando os payloads pelo SDK:
bundles alcançáveis a partir do nível novo, imports EBX disponíveis em cada bundle, RIDs de RES, chunks, chaves de
shader e registros, shader state ids, name hashes, GUID do Enlighten, nomes do estádio de origem que sobraram,
registro no mapa de estádios e nos loaders, banco. Para o projeto inteiro: SHA-1 dos payloads, a ordem das instâncias
de todo EBX gravado (o FC 27 acha instâncias exportadas por busca binária: fora de ordem = referência nula = o jogo fecha)
e os limites que os meshes do FC 27 respeitam.
"""
from __future__ import annotations
import collections
import hashlib
import json
import uuid
from pathlib import Path

from . import base, projeto as P
from .base import PREFIX, ZERO, sha256, walk_strings

RES_MESH, RES_TEXTURE, RES_SBD = 0x49b156d4, 0x6bde20ba, 0x73312045
NATIVE_SUBSETS_MAX = 70
NATIVE_LOD_MAX = 12_040_000          # maior LOD do FC 27 (rede do gol, 11,48 MB)
NATIVE_STADIUM_TOTAL = 34_300_000    # maior LOD0 somado de um estádio do FC 27 (Everton, 32,7 MB)


def djb32(s):
    h = 5381
    for ch in s:
        h = ((h * 33) ^ (ord(ch) & 0xff)) & 0xffffffff
    return h


def djb64l(s):
    h = 5381
    for ch in s.lower():
        h = ((h * 33) ^ (ord(ch) & 0xff)) & 0xffffffffffffffff
    return h


class Leitura:
    """Projeto gravado + dumps do SDK dos EBX adicionados/modificados e info dos RES adicionados."""

    def __init__(self, amb, saida, work):
        self.amb = amb
        self.p = P.Projeto(saida, amb.cas())
        self.work = Path(work) / 'verificacao'
        self.work.mkdir(parents=True, exist_ok=True)
        self.c = amb.indice()
        pp = self.p.parsed
        self.added_ebx = [e for e in pp['ebx'] if e['flags'] & 1]
        self.mod_ebx = [e for e in pp['ebx'] if not e['flags'] & 1 and not e['flags'] & 32]
        self.added_res = [e for e in pp['resources'] if e['flags'] & 1]
        self.mod_res = [e for e in pp['resources'] if not e['flags'] & 1 and not e['flags'] & 32]
        jobs, files = [], {}
        for e in self.added_ebx + self.mod_ebx:
            k = sha256(e['name'].lower().encode())[:20]
            f = self.work / (k + '.ebx')
            f.write_bytes(self.p.raw('ebx', e['name']))
            files[e['name'].lower()] = f
            d = self.work / (k + '.json')
            if d.exists():
                d.unlink()
            jobs.append({'kind': 'dump', 'input': str(f), 'output': str(d)})
        self.ebx_files = files
        rjobs, self.rorder = [], []
        for e in self.added_res + self.mod_res:
            f = self.work / ('res_' + sha256(e['name'].encode())[:20] + '.bin')
            f.write_bytes(self.p.raw('res', e['name']))
            if e.get('restype', self.c['res_by_name'].get(e['name'], {}).get('restype')) == RES_MESH:
                rjobs.append({'kind': 'mesh_info', 'input': str(f), 'meta': e.get('resmeta') or self.c['res_by_name'][e['name']]['resmeta']})
            elif e.get('restype') == RES_TEXTURE or (not e['flags'] & 1 and self.c['res_by_name'].get(e['name'], {}).get('restype') == RES_TEXTURE):
                rjobs.append({'kind': 'texture_info', 'input': str(f)})
            elif e.get('restype') == RES_SBD or (not e['flags'] & 1 and self.c['res_by_name'].get(e['name'], {}).get('restype') == RES_SBD):
                rjobs.append({'kind': 'sbd_info', 'input': str(f), 'meta': e.get('resmeta') or self.c['res_by_name'][e['name']]['resmeta']})
            else:
                continue
            self.rorder.append(e['name'])
        self.dumps = {}
        for k in range(0, len(jobs), 400):
            amb.run_sdk(jobs[k:k + 400], self.work, 'dump')
        for e in self.added_ebx + self.mod_ebx:
            d = self.work / (sha256(e['name'].lower().encode())[:20] + '.json')
            self.dumps[e['name'].lower()] = json.loads(d.read_text(encoding='utf8'))
        self.rinfo = {}
        if rjobs:
            rows = amb.run_sdk(rjobs, self.work, 'resinfo')['rows']
            self.rinfo = dict(zip(self.rorder, rows))


def verificar_copia(L, nova, origem_token, errors, notes, sbd_native_keys=None, old_var_hashes=()):
    """Checagens de uma duplicata (estádio novo com token `nova`, feito a partir de `origem_token`)."""
    p, c, dumps, rinfo = L.p.parsed, L.c, L.dumps, L.rinfo
    NEW, OLD = nova, origem_token
    family = OLD.rsplit('_', 1)[0]
    natb = {b['hash']: b for b in c['bundles']}
    added = {_bundle_hash(L, b['name']): b for b in p['addedbundles'] if f'/{NEW}/' in b['name']}
    short = {h: b['name'][len(PREFIX):] for h, b in added.items()}
    main = [h for h, s in short.items() if s.endswith(f'{NEW}/{NEW}')]
    if len(main) != 1:
        errors.append(f'{NEW}: bundle principal do nível novo não encontrado')
        return
    main_h = main[0]
    mine = lambda e: NEW in e['name'].lower()
    added_ebx = [e for e in L.added_ebx if mine(e)]
    added_res = [e for e in L.added_res if mine(e) or set(e.get('addedbundles', [])) & set(added)]
    # bundles alcançáveis
    level_refs = collections.defaultdict(set)
    for name, d in dumps.items():
        for i in d['instances']:
            if i['type'].endswith('SubWorldReferenceObjectData') and NEW in i['fields'].get('BundleName', '').lower():
                level_refs[i['fields']['BundleName'].lower()].add(name)
    by_short = {s.lower(): h for h, s in short.items()}
    parent = {}
    for child, owners in level_refs.items():
        for o in owners:
            if o in by_short and child in by_short:
                parent[by_short[child]] = by_short[o]
    ancestors = {}
    for h in added:
        chain, x = [h], h
        while x in parent:
            x = parent[x]
            chain.append(x)
        ancestors[h] = chain
    if any(h != main_h and ancestors[h][-1] != main_h for h in added):
        errors.append(f'{NEW}: um bundle de sub-mundo novo não é alcançável a partir do nível novo')
    ebx_bundles = {e['name'].lower(): set(e.get('addedbundles', [])) for e in p['ebx']}
    part_to_name = {e['partition']: e['name'].lower() for e in L.added_ebx}
    native_part = {}
    for e in c['ebx']:
        native_part.setdefault(e['partition'], e)
    in_project = {e['name'].lower() for e in p['ebx']}

    def available(part, h):
        if part in part_to_name:
            bs = ebx_bundles[part_to_name[part]]
            return any(a in bs for a in ancestors[h]) or any(b in natb for b in bs)
        e = native_part.get(part)
        if e is None:
            return False
        name = e['name'].lower()
        if name in in_project and any(a in ebx_bundles.get(name, set()) for a in ancestors[h]):
            return True
        nb = {c['bundles'][i]['name'] for i in e['bundles']}
        return any(OLD not in n for n in nb)
    import_fail = 0
    for e in added_ebx:
        d = dumps[e['name'].lower()]
        vals = []
        walk_strings([i['fields'] for i in d['instances']], vals)
        exts = {v[8:].split('/')[0] for v in vals if v.startswith('ptr:ext:')}
        hs = [h for h in e.get('addedbundles', []) if h in added]
        for part in exts:
            for h in hs:
                if not available(part, h):
                    import_fail += 1
                    if import_fail <= 10:
                        errors.append(f"{e['name']}: import {native_part.get(part, {}).get('name', part)} indisponível em {short[h]}")
        for part, inst in ((v[8:].split('/')[0], v[8:].split('/')[1]) for v in vals if v.startswith('ptr:ext:')):
            if part in part_to_name:
                tgt = dumps[part_to_name[part]]
                if inst not in {i['guid'] for i in tgt['instances'] if i['exported']}:
                    errors.append(f"{e['name']}: importa {part}/{inst}, que o clone não exporta")
    notes[f'{NEW}.imports_falhos'] = import_fail
    cache_by_name = c['ebx_by_name']
    nk = 0
    for e in p['ebx']:
        if not e['flags'] & 32 or not set(e.get('addedbundles', [])) & set(added):
            continue
        ce = cache_by_name[e['name'].lower()]
        for dep in ce['dependencies']:
            for h in e['addedbundles']:
                if h in added and not available(dep, h):
                    nk += 1
                    if nk <= 10:
                        errors.append(f"nativo {e['name']}: import {native_part.get(dep, {}).get('name', dep)} falta em {short[h]}")
    notes[f'{NEW}.imports_nativos_falhos'] = nk
    # RES citados pelos EBX adicionados
    rid_rec = {e['resrid']: e for e in L.added_res}
    cache_rid = c['res_by_rid']
    res_bundles = {e['name']: set(e.get('addedbundles', [])) for e in p['resources']}
    rid_fail = 0
    for e in added_ebx:
        vals = []
        walk_strings([i['fields'] for i in dumps[e['name'].lower()]['instances']], vals)
        for v in vals:
            if not v.startswith('res:'):
                continue
            r = int(v[4:], 16)
            if not r:
                continue
            if r in rid_rec:
                rr = rid_rec[r]
                if rr['name'] != e['name'].lower():
                    errors.append(f"{e['name']}: RID aponta para o RES {rr['name']}")
                if not set(e['addedbundles']) <= res_bundles[rr['name']]:
                    rid_fail += 1
                    errors.append(f"{e['name']}: o RES dele não está em todos os bundles dele")
            elif r in cache_rid:
                rid_fail += 1
                errors.append(f"{e['name']}: ainda aponta para o RES nativo {cache_rid[r]['name']}")
            else:
                rid_fail += 1
                errors.append(f"{e['name']}: RID {r:x} desconhecido")
    notes[f'{NEW}.rids_falhos'] = rid_fail
    # chunks dos RES adicionados
    chunk_rec = {e['id']: e for e in p['chunks']}
    chunk_fail = 0
    for e in added_res:
        info = rinfo.get(e['name'])
        ids = []
        if info is None:
            continue
        if e['restype'] == RES_TEXTURE:
            if not info['roundtrip_identical']:
                errors.append('cabeçalho de textura não faz ida e volta ' + e['name'])
            if int(info['name_hash']) != djb64l(e['name']):
                errors.append('name hash da textura ' + e['name'])
            ids = [info['chunk']] if info['chunk'] != ZERO else []
        elif e['restype'] == RES_MESH:
            m = info['mesh']
            if not info['roundtrip_identical'] or m['name'] != e['name']:
                errors.append('RES de mesh ' + e['name'])
            owner = dumps.get(e['name'])
            if owner is not None:
                nh = owner['instances'][0]['fields']['NameHash']
                if int(m['name_hash']) != nh or nh != djb32(owner['name']):
                    errors.append('name hash do mesh ' + e['name'])
            for i, lod in enumerate(m['lods']):
                if lod['name'] != f"{e['name']}_lod{i}":
                    errors.append('nome do LOD ' + lod['name'])
                if lod['chunk'] != ZERO:
                    ids.append(lod['chunk'])
        for cid in ids:
            ch = chunk_rec.get(cid)
            if ch is None or not ch['flags'] & 1:
                chunk_fail += 1
                errors.append(f"{e['name']}: o chunk {cid} não é um chunk adicionado do projeto")
                continue
            if not set(e['addedbundles']) <= set(ch.get('addedbundles', [])):
                errors.append(f"{e['name']}: chunk fora de algum bundle do RES")
            if ch.get('h32') != djb64l(e['name']):
                errors.append(f"{e['name']}: h32 do chunk")
            if uuid.UUID(cid).bytes_le[15] != 1:
                errors.append('byte de armazenamento do chunk ' + cid)
    notes[f'{NEW}.chunks_falhos'] = chunk_fail
    # chaves de shader
    regs = {}
    shader_sources = p['shadersources']
    for e in added_res:
        if e['restype'] != RES_SBD or e['name'] not in rinfo:
            continue
        info = rinfo[e['name']]
        keys = {int(k) for k in info['entries']}
        rr = {k: shader_sources[si] for k, si in e.get('shader_registrations', [])}
        if set(rr) != keys:
            errors.append(f"{e['name']}: registros diferem das entradas do depósito")
        for k in rr:
            if k in regs:
                errors.append('chave alias registrada duas vezes')
            regs[k] = (rr[k], e)
    key_fail = 0
    native_keys = set(sbd_native_keys or ())
    for e in added_res:
        if e['restype'] != RES_MESH or e['name'] not in rinfo:
            continue
        for lod in rinfo[e['name']]['mesh']['lods']:
            for kk in lod['keys']:
                kk = int(kk)
                if not kk:
                    continue
                if kk in regs:
                    dep = regs[kk][1]
                    if not set(e['addedbundles']) <= set(dep['addedbundles']):
                        key_fail += 1
                        errors.append(f"{e['name']}: o depósito da chave alias não está no bundle do mesh")
                elif kk in native_keys:
                    key_fail += 1
                    errors.append(f"{e['name']}: ainda usa a chave nativa {kk:x} apesar do depósito duplicado")
    notes[f'{NEW}.chaves_falhas'] = key_fail
    notes[f'{NEW}.registros_alias'] = len(regs)
    # shader state ids
    per_bundle = collections.Counter()
    for e in p['resources']:
        if e['name'].endswith('_win32_shaderstateshaderstateassetid') and set(e.get('addedbundles', [])) & set(added):
            for h in e.get('addedbundles', []):
                per_bundle[h] += 1
            if e['flags'] & 1:
                raw = L.p.raw('res', e['name'])
                path = e['name'][:-len('shaderstateassetid')]
                if raw[:16] != hashlib.md5(path.lower().encode()).digest():
                    errors.append('id de caminho do shader state ' + e['name'])
                owner = str(uuid.UUID(bytes_le=raw[16:32]))
                bname = path[:-len('_win32_shaderstate')]
                own = [x for x in L.added_ebx if x['name'].lower() == bname.lower()]
                if not own or own[0]['partition'] != owner:
                    errors.append('dono do shader state ' + e['name'])
    for h in added:
        if per_bundle[h] != 1:
            errors.append(f'{short[h]} tem {per_bundle[h]} shader state ids')
    # name hashes e MVDB
    for e in added_ebx:
        if e['type'] == 'ObjectVariation':
            nh = dumps[e['name'].lower()]['instances'][0]['fields']['NameHash']
            if nh != djb32(e['name']):
                errors.append('name hash da variação ' + e['name'])
    old_var = set(old_var_hashes)
    for e in added_ebx:
        if e['type'] == 'MeshVariationDatabase':
            for ent in dumps[e['name'].lower()]['instances'][0]['fields'].get('Entries', []):
                if ent['VariationAssetNameHash'] in old_var:
                    errors.append(f"{e['name']}: entrada com hash de variação antigo")
    # Enlighten
    for e in added_res:
        if e['restype'] in (0x70c5cb3e, 0xc6cd3286):
            owner = dumps.get(e['name'])
            if owner is None:
                continue
            raw = L.p.raw('res', e['name'])
            if raw.count(uuid.UUID(owner['instances'][0]['guid']).bytes_le) != 1:
                errors.append('RES do Enlighten sem o GUID novo ' + e['name'])
    # nomes do estádio de origem que sobraram
    left = collections.Counter()
    for e in added_ebx:
        vals = []
        walk_strings([i['fields'] for i in dumps[e['name'].lower()]['instances']], vals)
        for v in vals:
            if OLD in v.lower() or (family in v.lower() and NEW not in v.lower() and not v.lower().endswith(('class', "class'", 'class_instanceclass'))):
                if v.startswith('type:'):
                    continue
                left[v] += 1
    if left:
        errors.append(f'{NEW}: nomes do estádio de origem nos EBX adicionados: ' + json.dumps(list(left)[:5]))
    # registro
    nid = int(NEW.rsplit('_', 1)[1])
    oid = int(OLD.rsplit('_', 1)[1])
    slms = [n for n in dumps if n.startswith('content/common/logic/dsub/stadiumcollectionslm')]
    for n in slms:
        items = dumps[n]['instances'][0]['fields']['SublevelItems']
        if not any(i['KeyId'] == oid for i in items):
            continue
        mine_items = [i for i in items if i['KeyId'] == nid]
        if n == 'content/common/logic/dsub/stadiumcollectionslm' or mine_items:
            if len(mine_items) != 1 or mine_items[0]['SubWorldName'].lower() != f'content/worlds/stadiums/{NEW}/{NEW}':
                errors.append(f'{NEW}: entrada no {n.split("/")[-1]}')
    if 'content/common/logic/dsub/stadiumcollectionslm' not in slms:
        errors.append('o StadiumCollectionSLM principal não foi modificado')
    for ldr in ('content/common/logic/dsub/stadiumloader', 'content/common/logic/dsub/stadiumloader_layer1', 'content/common/logic/dsub/stadiumloader_layer2'):
        d = dumps.get(ldr)
        if d is None:
            errors.append('loader não modificado ' + ldr)
            continue
        refs = [i for i in d['instances'] if i['type'].endswith('SubWorldReferenceObjectData') and i['fields']['BundleName'].lower() == f'content/worlds/stadiums/{NEW}/{NEW}']
        if len(refs) != 1:
            errors.append(f'{NEW}: referência no loader ' + ldr)
            continue
        idx = refs[0]['index']
        bp = d['instances'][0]['fields']
        if f'ptr:int:{idx}' not in bp['Objects'] or not any(pc['Target'] == f'ptr:int:{idx}' for pc in bp['PropertyConnections']):
            errors.append(f'{NEW}: listas do loader ' + ldr)
    notes[f'{NEW}.bundles'] = len(added)
    notes[f'{NEW}.ebx_adicionados'] = len(added_ebx)


def _bundle_hash(L, name):
    if not hasattr(L, '_bh'):
        L._bh = L.amb.hashes([b['name'] for b in L.p.parsed['addedbundles']], L.work, 'bundle_hashes')
    return int(L._bh[name]['xxh3_utf16_lower'])


def ordem_ebx(L, errors, notes):
    """Todo EBX gravado (adicionado ou modificado) na ordem de instâncias do FC 27."""
    jobs = [dict(kind='ebx_order', input=str(L.ebx_files[e['name'].lower()]), name=e['name']) for e in L.added_ebx + L.mod_ebx]
    bad = []
    for k in range(0, len(jobs), 500):
        rows = L.amb.run_sdk(jobs[k:k + 500], L.work, 'ordem', ferramenta='ConvertTool', allow_failures=True)['rows']
        bad += [(j['name'], r.get('order_error') or r.get('error', '')[:200]) for j, r in zip(jobs[k:k + 500], rows) if not r.get('order_ok')]
    for name, why in bad[:20]:
        errors.append(f'{name}: ordem das instâncias do EBX: {why}')
    notes['ordem_ebx'] = dict(conferidos=len(jobs), fora_de_ordem=len(bad))


def limites_mesh(L, errors, notes, so_modificados=False):
    """Meshes gravados contra o que os meshes do FC 27 fazem: nenhum subset vazio (nenhum LOD do jogo tem), no máximo
    70 subsets, LOD até o maior do jogo. Os clones byte a byte de meshes nativos só precisam da ida e volta."""
    jobs, nomes = [], []
    for e in (L.mod_res if so_modificados else L.added_res + L.mod_res):
        meta = e.get('resmeta') or L.c['res_by_name'].get(e['name'], {}).get('resmeta')
        tipo = e.get('restype', L.c['res_by_name'].get(e['name'], {}).get('restype'))
        if tipo != RES_MESH:
            continue
        f = L.work / ('res_' + sha256(e['name'].encode())[:20] + '.bin')
        o = L.work / ('lim_' + sha256(e['name'].encode())[:20] + '.json')
        if o.exists():
            o.unlink()
        jobs.append(dict(kind='mesh_dump', input=str(f), meta=meta, output=str(o)))
        nomes.append((e['name'], o))
    if jobs:
        L.amb.run_sdk(jobs, L.work, 'limites', ferramenta='ConvertTool')
    maior = 0
    for name, o in nomes:
        d = json.loads(o.read_text(encoding='utf8'))
        for li, lod in enumerate(d['lods']):
            size = lod['vertex_size'] + lod['index_size']
            maior = max(maior, size)
            empty = [k for k, s in enumerate(lod['subsets']) if s['vertices'] == 0 or s['prims'] == 0]
            if empty:
                errors.append(f'{name} lod {li}: subsets sem geometria {empty} (o FC 27 não tem nenhum)')
            if len(lod['subsets']) > NATIVE_SUBSETS_MAX:
                errors.append(f'{name} lod {li}: {len(lod["subsets"])} subsets (máximo do FC 27: {NATIVE_SUBSETS_MAX})')
            if size > NATIVE_LOD_MAX:
                errors.append(f'{name} lod {li}: {size} bytes de vértices e índices (maior LOD do FC 27: {NATIVE_LOD_MAX})')
    notes['meshes_conferidos'] = len(nomes)
    notes['maior_lod_mb'] = round(maior / 2**20, 2)


def verificar_projeto(amb, saida, work, projeto_base=None, copias=None, extra=None):
    base.etapa('verificar', 'Verificando o projeto gravado')
    errors, notes = [], collections.Counter()
    L = Leitura(amb, saida, work)
    pp = L.p.parsed
    for kind in ('ebx', 'resources', 'chunks'):
        for e in pp[kind]:
            if hashlib.sha1(L.p.encoded(e)).hexdigest() != e['sha1']:
                errors.append('sha1 do payload ' + str(e.get('name') or e.get('id')))
    base.progresso(30, 'ordem das instâncias dos EBX')
    ordem_ebx(L, errors, notes)
    base.progresso(55, 'meshes')
    limites_mesh(L, errors, notes)
    base.progresso(70, 'estádios novos')
    for cp in copias or []:
        verificar_copia(L, cp['token_novo'], cp['token_origem'], errors, notes, cp.get('chaves_nativas'), cp.get('hashes_variacao_antigos', ()))
    if extra:
        extra(L, errors, notes)
    res = dict(ok=not errors, erros=errors[:200], total_erros=len(errors), notas=dict(notes),
               registros=dict(ebx=len(pp['ebx']), res=len(pp['resources']), chunks=len(pp['chunks']), bundles=len(pp['addedbundles'])))
    base.gravar_json(Path(work) / 'verificacao.json', res)
    base.progresso(100, 'sem erros' if not errors else f'{len(errors)} erro(s)')
    return res
