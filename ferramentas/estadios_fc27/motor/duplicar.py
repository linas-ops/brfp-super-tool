"""Duplicação completa de estádios do FC 27 com ID próprio (o método das duplicatas 702 e 703, confirmadas em partida).

Cada cópia ganha bundles novos e identidade própria em tudo o que é do estádio, como o DuplicationHelper do FET:
- EBX que só o estádio carrega (os bundles dele) ou que levam o nome dele: mundo (DetachedSubWorldData, SubWorldData,
  LayerData, WorldPartData), meshes, texturas, blueprints, prefabs, variações, decalques, efeitos, torcida, física,
  Enlighten, MeshVariationDb, NetworkRegistry, registro de torcida e descrição do nível;
- as texturas que os shaders dos meshes clonados e os assets clonados usam;
- os RES (nome e RID novos) e chunks (GUID novos do GenerateDeterministicChunkGuid, bytes guardados reaproveitados);
- por bundle com meshes clonados: depósito de shaders próprio com chaves alias registradas contra as originais, texturas
  remapeadas e ShaderStateAssetId do bundle novo.
Ficam nativos e compartilhados: definições de tipo (ClassInfoAsset, SchematicsAsset), SurfaceShaderPreset e assets de
biblioteca que outros estádios também usam. Registro: StadiumCollectionSLM (e o mapa Layer1, quando o original está nele),
os três StadiumLoader e as linhas stadiums + audiostadium do banco.

Regras de identidade (conferidas nos dados nativos): partição = MD5(nome em minúsculas) quando o nativo segue essa regra,
senão UUID5; instância primária = a partição quando o nativo é assim, senão UUID5; as outras instâncias exportadas mantêm
os GUIDs (como o DuplicationHelper.DuplicateEbx); referências remapeadas pelo par (partição, instância).
Várias cópias (do mesmo estádio ou de estádios diferentes) entram num projeto só; partindo de um projeto existente, o
mapa de estádios, os loaders e o banco partem da versão do projeto.
"""
from __future__ import annotations
import collections
import hashlib
import json
import re
import struct
import uuid
from pathlib import Path

from . import base, projeto as P, t3db
from .base import NS, PREFIX, ZERO, falha, md5_guid, sha256, walk_strings

STRUCTURAL_DESC_BUNDLES = ['fc/fc_gameconfig', 'sandbox/craniumui/brt/craniumviewfallbackconfig']
SLM = 'content/common/Logic/DSub/StadiumCollectionSLM'
SLM_L1 = 'content/common/Logic/dsub/StadiumCollectionSLM_Layer1'
LOADERS = ['content/common/Logic/DSub/StadiumLoader', 'content/common/Logic/dsub/StadiumLoader_Layer1',
           'content/common/Logic/dsub/StadiumLoader_Layer2']
KEEP_TYPES = {'ClassInfoAsset', 'SchematicsAsset', 'SurfaceShaderPreset'}
MESH_TYPES = {'RigidMeshAsset', 'CompositeMeshAsset'}
RES_MESH, RES_TEXTURE, RES_SBD, RES_SHADERSTATE = 0x49b156d4, 0x6bde20ba, 0x73312045, 0x2fec6526
RES_ENLIGHTEN = {0x70c5cb3e, 0xc6cd3286}
RES_PHYSICS = {0x41759364, 0xef23407c}
PHYSICS_TYPES = {'FifaPhysicsResourceAsset', 'PhysicsAsset'}
DB_GLOBALS_SUPERBUNDLE = 'globals'


def tokens_estadios(c):
    """{id: token} dos estádios do jogo, pelos bundles principais fc/fcgame/main/content/worlds/stadiums/<token>/<token>."""
    out = {}
    for b in c['bundles']:
        m = re.fullmatch(r'fc/fcgame/main/content/worlds/stadiums/([a-z0-9_]+)/\1', b['name'])
        if m:
            t = re.search(r'_(\d+)$', m.group(1))
            if t:
                out.setdefault(int(t.group(1)), m.group(1))
    return out


# ------------------------------------------------------------------ uma cópia
class Copia:
    def __init__(self, dup, origem, novo_id, nome_db, fisica_nativa=False):
        self.dup, self.amb, self.c = dup, dup.amb, dup.amb.indice()
        self.old_id, self.new_id, self.db_name = int(origem), int(novo_id), nome_db
        self.share_physics = fisica_nativa
        tok = tokens_estadios(self.c).get(self.old_id)
        if not tok:
            falha(f'estádio {self.old_id} não encontrado no jogo')
        self.old_token = tok
        self.family = tok[:-len(f'_{self.old_id}')]
        self.new_token = f'{self.family}_{self.new_id}'
        self.work = dup.work / f'copia_{self.old_id}_{self.new_id}'
        self.work.mkdir(parents=True, exist_ok=True)
        self.report = collections.OrderedDict(origem=self.old_id, novo_id=self.new_id, token_origem=tok, token_novo=self.new_token,
                                              nome=nome_db)
        self.ebx_by_name = self.c['ebx_by_name']
        self.bundles = self.c['bundles']
        self.bundle_by_name = self.c['bundle_by_name']
        self.ebx_parts = dup.ebx_parts

    # ---------------------------------------------------------- nomes
    def rename(self, s):
        if self.old_token not in s.lower():
            falha('nome sem o token do estádio: ' + s)
        out = re.sub(re.escape(self.old_token), self.new_token, s, flags=re.I)
        if re.search(rf'(?<![0-9]){self.old_id}(?![0-9])', out):
            falha(f'sobrou {self.old_id} no nome renomeado: ' + out)
        return out

    def new_name_for(self, name):
        """Nomes do estádio trocam o token no lugar; os outros vão para a pasta do estádio novo com o nome intacto."""
        if re.search(re.escape(self.family), name, re.I):
            out = re.sub(rf'{re.escape(self.family)}(_{self.old_id}(?![0-9]))?', self.new_token, name, flags=re.I)
        else:
            rest = name[len('content/'):] if name.lower().startswith('content/') else name
            out = f'content/worlds/stadiums/{self.new_token}/copias/{rest}'
        if re.search(rf'(?<![0-9]){self.old_id}(?![0-9])', out):
            falha(f'sobrou {self.old_id} em ' + out)
        return out

    def native_res(self, e):
        p, _ = self.amb.native('res', e['name'])
        raw = p.read_bytes()
        if len(raw) != e['original_size']:
            falha('extração nativa mudou: ' + e['name'])
        return p, raw

    def sdk_hashes(self, names, tag):
        return self.amb.hashes(names, self.work, 'hash_' + tag)

    # ---------------------------------------------------------- plano
    def plan(self):
        c = self.c
        src_bundles = [b for b in self.bundles if f'/{self.old_token}/' in b['name']]
        if not src_bundles:
            falha(f'estádio {self.old_id} sem bundles')
        self.main_old = next(b for b in src_bundles if b['name'].endswith(f'/{self.old_token}/{self.old_token}'))
        self.selected = src_bundles
        sel = {b['index'] for b in src_bundles}
        self.sel = sel
        self.bundle_map = {}
        hash_names = []
        for b in src_bundles:
            new = self.rename(b['name'])
            if new in self.bundle_by_name:
                falha('o bundle novo já existe no jogo: ' + new)
            sb = self.dup.superbundles[b['superbundle']]
            self.bundle_map[b['index']] = dict(old=b['name'], new=new, short=new[len(PREFIX):], superbundle=sb['hash'],
                                               superbundle_name=sb['name'], type=b['type'])
            hash_names.append(new)
        h = self.sdk_hashes(hash_names + [b['name'] for b in src_bundles], 'bundles')
        for b in src_bundles:
            if int(h[b['name']]['xxh3_utf16_lower']) != b['hash']:
                falha('a fórmula do hash de bundle falhou num bundle nativo')
        native_hashes = {b['hash'] for b in self.bundles}
        for i, m in self.bundle_map.items():
            m['hash'] = int(h[m['new']]['xxh3_utf16_lower'])
            if m['hash'] in native_hashes:
                falha('hash de bundle novo colide com um nativo')
        self.added_bundles = [{'name': m['new'], 'superbundle': m['superbundle'], 'type': m['type']} for m in self.bundle_map.values()]
        desc_hashes = [self.bundle_by_name[n]['hash'] for n in STRUCTURAL_DESC_BUNDLES]

        own = lambda n: self.family in n.lower()
        excl = lambda e: bool(set(e['bundles'])) and set(e['bundles']) <= sel
        level_old = f'content/worlds/stadiums/{self.old_token}/{self.old_token}'
        desc = self.ebx_by_name[(level_old + '/description').lower()]
        clone = {e['partition']: e for e in c['ebx'] if set(e['bundles']) & sel and (excl(e) or own(e['name'])) and e['type'] not in KEEP_TYPES}
        if self.share_physics:
            clone = {p: e for p, e in clone.items() if e['type'] not in PHYSICS_TYPES}
        clone[desc['partition']] = desc
        dumps = self.dumps_for(list(clone.values()))
        part_meta = self.dup.part_meta
        self.part_meta = part_meta
        rid_meta = c['res_by_rid']
        self.rid_meta = rid_meta

        def rids_of(d):
            vals = []
            walk_strings([i['fields'] for i in d['instances']], vals)
            return [int(v[4:], 16) for v in vals if v.startswith('res:') and int(v[4:], 16)]
        mesh_res = {}
        for p, e in clone.items():
            if e['type'] in MESH_TYPES:
                rs = [r for r in rids_of(dumps[e['name']]) if rid_meta[r]['restype'] == RES_MESH]
                if len(rs) != 1:
                    falha('mesh sem um único RES MeshSet: ' + e['name'])
                mesh_res[p] = rid_meta[rs[0]]
        sbd = {}
        for e in c['res']:
            if e['restype'] == RES_SBD and set(e['bundles']) & sel:
                for bi in e['bundles']:
                    if bi in sel:
                        if bi in sbd:
                            falha('bundle com mais de um depósito de shaders nativo')
                        sbd[bi] = e
        jobs = []
        for p, r in mesh_res.items():
            path, _ = self.native_res(r)
            jobs.append({'kind': 'mesh_info', 'input': str(path), 'meta': r['resmeta']})
        for bi, r in sbd.items():
            path, _ = self.native_res(r)
            jobs.append({'kind': 'sbd_info', 'input': str(path), 'meta': r['resmeta']})
        rows = self.amb.run_sdk(jobs, self.work, 'info')['rows'] if jobs else []
        mesh_info = {}
        for (p, r), row in zip(mesh_res.items(), rows[:len(mesh_res)]):
            if not row['roundtrip_identical'] or row['mesh']['name'] != r['name']:
                falha('MeshSet não faz ida e volta: ' + r['name'])
            mesh_info[p] = row['mesh']
        sbd_info = {}
        for (bi, r), row in zip(sbd.items(), rows[len(mesh_res):]):
            if not row['roundtrip_identical']:
                falha('depósito não faz ida e volta: ' + r['name'])
            sbd_info[bi] = row
        self.mesh_res, self.mesh_info, self.sbd, self.sbd_info = mesh_res, mesh_info, sbd, sbd_info

        extra = {}
        usage = collections.defaultdict(set)
        for p, info in mesh_info.items():
            e = clone[p]
            for bi in e['bundles']:
                if bi not in sel:
                    continue
                entries = sbd_info.get(bi, {}).get('entry_texture_refs', {})
                for lod in info['lods']:
                    for k in lod['keys']:
                        for ref in entries.get(k, []):
                            usage[ref.split('/')[0]].add(bi)
        mesh_parts = set(mesh_res)
        for p, e in clone.items():
            d = dumps[e['name']]
            if e['type'] == 'MeshVariationDatabase':
                by_index = {i['index']: i for i in d['instances']}
                for ent in d['instances'][0]['fields'].get('Entries', []):
                    m = ent.get('Mesh', '')
                    if not (m.startswith('ptr:ext:') and m[8:].split('/')[0] in mesh_parts):
                        continue
                    todo, seen, vals = [ent], set(), []
                    while todo:
                        node = todo.pop()
                        found = []
                        walk_strings(node, found)
                        vals += found
                        for v in found:
                            if v.startswith('ptr:int:'):
                                k = int(v[8:])
                                if k not in seen and k in by_index:
                                    seen.add(k)
                                    todo.append(by_index[k]['fields'])
                    for v in vals:
                        if v.startswith('ptr:ext:'):
                            tp = v[8:].split('/')[0]
                            if part_meta.get(tp, {}).get('type') == 'TextureAsset':
                                usage[tp].update(bi for bi in e['bundles'] if bi in sel)
                continue
            vals = []
            walk_strings([i['fields'] for i in d['instances']], vals)
            for v in vals:
                if v.startswith('ptr:ext:'):
                    tp = v[8:].split('/')[0]
                    if part_meta.get(tp, {}).get('type') == 'TextureAsset':
                        usage[tp].update(bi for bi in e['bundles'] if bi in sel)
        for tp in usage:
            if tp not in clone:
                t = part_meta.get(tp)
                if t is None:
                    falha('partição de textura desconhecida do cache: ' + tp)
                extra[tp] = t
        clone.update(extra)
        dumps.update(self.dumps_for(list(extra.values())))
        self.texture_usage = usage
        self.report['texturas_de_biblioteca'] = len(extra)

        names_new = {}
        for p, e in clone.items():
            nn = self.new_name_for(e['name'])
            if nn.lower() in self.ebx_by_name:
                falha('o nome novo já existe no jogo: ' + nn)
            names_new[p] = nn
        if len({n.lower() for n in names_new.values()}) != len(names_new):
            falha('nomes novos colidem entre os clones')
        clones = []
        for p, e in clone.items():
            d = dumps[e['name']]
            x = dict(src=e, new_name=names_new[p])
            md5 = e['partition'] == md5_guid(e['name'])
            x['rule'] = 'md5-name' if md5 else 'uuid5'
            x['partition'] = md5_guid(x['new_name']) if md5 else str(uuid.uuid5(NS, 'partition:' + x['new_name'].lower()))
            prim = d['instances'][0]
            if not prim['exported']:
                falha('instância primária não exportada em ' + e['name'])
            x['old_primary'] = prim['guid']
            x['primary'] = x['partition'] if prim['guid'] == e['partition'] else str(uuid.uuid5(NS, 'instance:' + x['new_name'].lower()))
            x['primary_rule'] = 'partition' if prim['guid'] == e['partition'] else 'uuid5'
            x['exports'] = [i['guid'] for i in d['instances'] if i['exported']]
            if e['partition'] == desc['partition']:
                x['bundle_idx'] = []
                x['addedbundles'] = desc_hashes
            else:
                bs = {bi for bi in e['bundles'] if bi in sel} | usage.get(p, set())
                if not bs:
                    falha('clone sem bundle: ' + e['name'])
                x['bundle_idx'] = sorted(bs)
                x['addedbundles'] = [self.bundle_map[bi]['hash'] for bi in x['bundle_idx']]
            clones.append(x)
        parts = [x['partition'] for x in clones]
        if len(set(parts)) != len(parts) or any(self.ebx_parts.get(q) for q in parts):
            falha('colisão de partição')
        self.clones, self.dumps = clones, dumps
        self.clone_by_part = {x['src']['partition']: x for x in clones}
        self.widen_for_references(clones, dumps, sel)
        pairs, guids = [], {}
        for x in clones:
            op = x['src']['partition']
            for g in x['exports']:
                pairs.append([op, g, x['partition'], x['primary'] if g == x['old_primary'] else g])
            guids[x['old_primary']] = x['primary']
            guids[op] = x['partition']
        self.pairs, self.guids = pairs, guids

        renamable = {x['src']['name'].lower(): x['new_name'] for x in clones}
        for m in self.bundle_map.values():
            renamable[m['old'].lower()] = m['new']
            renamable[m['old'][len(PREFIX):].lower()] = m['new'][len(PREFIX):]
        strings, unexpected = {}, []
        for x in clones:
            vals = []
            walk_strings([i['fields'] for i in dumps[x['src']['name']]['instances']], vals)
            for v in vals:
                if v.startswith(('ptr:', 'guid:', 'res:', 'type:')):
                    continue
                if v.lower() in renamable:
                    strings[v] = self.new_name_for(v)
                    if strings[v].lower() != renamable[v.lower()].lower():
                        falha(f'regra de nome diverge para {v}')
                elif self.family in v.lower():
                    unexpected.append((x['src']['name'], v))
        if unexpected:
            falha('textos com o token do estádio fora do mapa de nomes: ' + json.dumps(unexpected[:10]))
        self.strings = strings
        self.report['clones'] = dict(collections.Counter(x['src']['type'] for x in clones))
        self.report['bundles'] = len(self.bundle_map)

    def dumps_for(self, ebx_list):
        got = self.amb.dumps([e['name'] for e in ebx_list], self.work)
        return {e['name']: got[e['name'].lower()] for e in ebx_list}

    def widen_for_references(self, clones, dumps, sel):
        """Um clone tem de estar em todo bundle novo cujos clones apontam para ele, a menos que um bundle que carrega
        esse (o sub-mundo pai) já o tenha."""
        by_short = {m['old'][len(PREFIX):].lower(): bi for bi, m in self.bundle_map.items()}
        parent = collections.defaultdict(set)
        for x in clones:
            for i in dumps[x['src']['name']]['instances']:
                if i['type'].endswith('SubWorldReferenceObjectData'):
                    child = by_short.get(i['fields'].get('BundleName', '').lower())
                    if child is not None:
                        parent[child].update(bi for bi in x['src']['bundles'] if bi in sel)

        def lineage(b):
            seen, todo = {b}, [b]
            while todo:
                for q in parent.get(todo.pop(), ()):
                    if q not in seen:
                        seen.add(q)
                        todo.append(q)
            return seen
        lineages = {bi: lineage(bi) for bi in self.bundle_map}
        refs = {}
        for x in clones:
            vals = []
            walk_strings([i['fields'] for i in dumps[x['src']['name']]['instances']], vals)
            refs[x['src']['partition']] = {v[8:].split('/')[0] for v in vals if v.startswith('ptr:ext:')} & self.clone_by_part.keys()
        widened = collections.Counter()
        changed = True
        while changed:
            changed = False
            for x in clones:
                for p in refs[x['src']['partition']]:
                    y = self.clone_by_part[p]
                    if not y['bundle_idx']:
                        continue
                    for b in x['bundle_idx']:
                        if not lineages[b] & set(y['bundle_idx']):
                            y['bundle_idx'] = sorted(set(y['bundle_idx']) | {b})
                            widened[y['src']['type']] += 1
                            changed = True
        for x in clones:
            if x['bundle_idx']:
                x['addedbundles'] = [self.bundle_map[bi]['hash'] for bi in x['bundle_idx']]
        if widened:
            self.report['bundles_ampliados_por_referencia'] = dict(widened)

    # ---------------------------------------------------------- RES, chunks, shaders
    def resources(self):
        c = self.c
        all_rids = self.dup.used_rids
        chunk_meta = c['chunk_by_id']
        res_clones = []
        for x in self.clones:
            vals = []
            walk_strings([i['fields'] for i in self.dumps[x['src']['name']]['instances']], vals)
            for v in vals:
                if not v.startswith('res:'):
                    continue
                r = int(v[4:], 16)
                if not r:
                    continue
                e = self.rid_meta[r]
                if e['name'] != x['src']['name'].lower():
                    falha(f"RES {e['name']} não tem o nome do seu EBX {x['src']['name']}")
                res_clones.append(dict(src=e, owner=x, new_name=x['new_name'].lower(), bundle_idx=x['bundle_idx']))
        if len({r['src']['resrid'] for r in res_clones}) != len(res_clones):
            falha('RES citado duas vezes')
        names = [r['new_name'] for r in res_clones]
        chunk_ident = []
        tex_jobs = {}
        for r in res_clones:
            if r['src']['restype'] == RES_TEXTURE:
                path, raw = self.native_res(r['src'])
                tex_jobs[r['src']['name']] = path
                chunk_ident.append(r['owner']['new_name'])
            elif r['src']['restype'] == RES_MESH:
                info = self.mesh_info[r['owner']['src']['partition']]
                for i, lod in enumerate(info['lods']):
                    chunk_ident.append(f"{r['owner']['new_name']}_lod{i}")
        hashes = self.sdk_hashes(names + chunk_ident + [m['short'] + '_win32_shaderblockdepot' for m in self.bundle_map.values()], 'res')
        for r in res_clones:
            rid = int(hashes[r['new_name']]['xxh64_utf16_lower']) | 1
            while rid in all_rids:
                rid = (rid + 2) & 0xffffffffffffffff
            all_rids.add(rid)
            r['rid'] = rid
            r['h32'] = int(hashes[r['new_name']]['djb2_lower64'])
        used_chunks = self.dup.used_chunks

        def chunk_guid(identity):
            hv = int(hashes[identity]['xxh64_utf16_lower'])
            n = 1
            while True:
                b = bytearray(struct.pack('<QQ', hv, hv ^ n))
                b[15] = 1
                g = str(uuid.UUID(bytes_le=bytes(b)))
                if g not in used_chunks:
                    used_chunks.add(g)
                    return g
                n += 1
        jobs = [{'kind': 'texture_info', 'input': str(p)} for p in tex_jobs.values()]
        tinfo = {name: row for name, row in zip(tex_jobs, self.amb.run_sdk(jobs, self.work, 'tex_info')['rows'])} if jobs else {}
        chunk_clones = []
        for r in res_clones:
            if r['src']['restype'] == RES_TEXTURE:
                row = tinfo[r['src']['name']]
                if not row['roundtrip_identical']:
                    falha('cabeçalho de textura não faz ida e volta: ' + r['src']['name'])
                old = row['chunk']
                if old == ZERO:
                    r['chunks'] = {}
                    continue
                if old not in chunk_meta:
                    falha('chunk de textura fora do cache: ' + old)
                new = chunk_guid(r['owner']['new_name'])
                r['chunks'] = {old: new}
                chunk_clones.append(dict(src=chunk_meta[old], id=new, res=r, superbundle=True))
            elif r['src']['restype'] == RES_MESH:
                info = self.mesh_info[r['owner']['src']['partition']]
                r['chunks'] = {}
                for i, lod in enumerate(info['lods']):
                    if lod['chunk'] == ZERO:
                        continue
                    if lod['chunk'] not in chunk_meta:
                        falha('chunk de mesh fora do cache: ' + lod['chunk'])
                    new = chunk_guid(f"{r['owner']['new_name']}_lod{i}")
                    r['chunks'][lod['chunk']] = new
                    chunk_clones.append(dict(src=chunk_meta[lod['chunk']], id=new, res=r, superbundle=False))
            else:
                r['chunks'] = {}
        if len({cc['src']['id'] for cc in chunk_clones}) != len(chunk_clones):
            falha('um chunk pertence a dois RES clonados')
        for cc in chunk_clones:
            if uuid.UUID(cc['src']['id']).bytes_le[15] & 3 != 1:
                falha('modo de armazenamento do chunk difere do GUID novo')
        self.res_clones, self.chunk_clones = res_clones, chunk_clones
        self.resource_map = {str(r['src']['resrid']): str(r['rid']) for r in res_clones}

        depots = {}
        for r in res_clones:
            if r['src']['restype'] != RES_MESH:
                continue
            info = self.mesh_info[r['owner']['src']['partition']]
            for bi in r['bundle_idx']:
                src = self.sbd.get(bi)
                entries = set(self.sbd_info[bi]['entries']) if src else set()
                for lod in info['lods']:
                    for k in lod['keys']:
                        if k != '0' and k in entries:
                            depots.setdefault(bi, set()).add(int(k))
        multi = [r for r in res_clones if r['src']['restype'] == RES_MESH and len(r['bundle_idx']) > 1]
        if multi:
            falha('mesh clonado em mais de um bundle: as chaves alias por bundle entrariam em conflito')
        alias_jobs = []
        self.depots = {}
        existing_res = self.dup.used_res_names
        for bi, keys in depots.items():
            short = self.bundle_map[bi]['short']
            num = int(hashes[short + '_win32_shaderblockdepot']['xxh3_utf16_exact'])
            name = f'expressionshader/shaderblockdepot/sb{num}'
            while name in existing_res:
                num = (num + 1) & 0xffffffffffffffff
                name = f'expressionshader/shaderblockdepot/sb{num}'
            existing_res.add(name)
            self.depots[bi] = dict(name=name, source=self.sbd[bi], keys=sorted(keys))
            alias_jobs.append({'kind': 'alias_keys', 'input': '-', 'depot_name': name, 'keys': [str(k) for k in sorted(keys)]})
        rows = self.amb.run_sdk(alias_jobs, self.work, 'alias')['rows'] if alias_jobs else []
        native_keys = {int(k) for bi in self.sbd_info for k in self.sbd_info[bi]['entries']}
        for (bi, dep), row in zip(self.depots.items(), rows):
            dep['map'] = {int(k): int(v) for k, v in row['keys'].items()}
            for v in dep['map'].values():
                if v in self.dup.used_keys or v in native_keys or v == 0:
                    falha('colisão de chave alias de shader')
                self.dup.used_keys.add(v)
        self.key_map_by_bundle = {bi: dep['map'] for bi, dep in self.depots.items()}
        self.report['depositos'] = len(self.depots)

    # ---------------------------------------------------------- SDK
    def sdk(self):
        n = 1
        while (self.work / f'sdk_run{n}').exists():
            n += 1
        out = self.work / f'sdk_run{n}'
        out.mkdir()
        jobs = []
        nh = self.sdk_hashes([x['new_name'] for x in self.clones if x['src']['type'] in MESH_TYPES | {'ObjectVariation'}]
                             + [x['src']['name'] for x in self.clones if x['src']['type'] in MESH_TYPES | {'ObjectVariation'}], 'namehash')
        var_map = {}
        for x in self.clones:
            t = x['src']['type']
            if t in MESH_TYPES | {'ObjectVariation'}:
                old = self.dumps[x['src']['name']]['instances'][0]['fields']['NameHash']
                if int(nh[x['src']['name']]['djb2_32']) != old:
                    falha('regra nativa do NameHash falhou para ' + x['src']['name'])
                x['name_hash'] = int(nh[x['new_name']]['djb2_32'])
                x['src_name_hash'] = old
                if t == 'ObjectVariation':
                    var_map[str(old)] = str(x['name_hash'])
        for x in self.clones:
            x['output'] = out / (x['partition'] + '.bin')
            p, _ = self.amb.native('ebx', x['src']['name'])
            job = dict(kind='clone', input=str(p), output=str(x['output']), expect_name=x['src']['name'],
                       expect_type=x['src']['type'], expect_partition=x['src']['partition'], partition=x['partition'],
                       new_name=x['new_name'])
            if 'name_hash' in x:
                job['set_primary'] = {'NameHash': str(x['name_hash'])}
            jobs.append(job)
        res_out = out / 'res'
        res_out.mkdir(exist_ok=True)
        for r in self.res_clones:
            path, raw = self.native_res(r['src'])
            r['output'] = res_out / (str(r['rid']) + '.bin')
            t = r['src']['restype']
            if t == RES_MESH:
                keys = {}
                for bi in r['bundle_idx']:
                    keys.update(self.key_map_by_bundle.get(bi, {}))
                jobs.append(dict(kind='mesh_res', input=str(path), meta=r['src']['resmeta'], output=str(r['output']),
                                 new_name=r['owner']['new_name'], name_hash=str(r['owner']['name_hash']),
                                 chunks=r['chunks'], keys={str(k): str(v) for k, v in keys.items()}))
            elif t == RES_TEXTURE:
                old, new = (next(iter(r['chunks'].items())) if r['chunks'] else (ZERO, ZERO))
                jobs.append(dict(kind='texture_res', input=str(path), output=str(r['output']), new_name=r['new_name'],
                                 old_chunk=old, chunk=new))
        inst_map = {x['old_primary']: x['primary'] for x in self.clones}
        part_map = {x['src']['partition']: x['partition'] for x in self.clones}
        for bi, dep in self.depots.items():
            path, raw = self.native_res(dep['source'])
            dep['output'] = res_out / ('depot_' + str(bi) + '.bin')
            jobs.append(dict(kind='sbd_alias', input=str(path), meta=dep['source']['resmeta'], output=str(dep['output']),
                             keys={str(k): str(v) for k, v in dep['map'].items()}, instances=inst_map, partitions=part_map))
        extra = dict(pairs=self.pairs, strings=self.strings, guids=self.guids, watch=[self.family],
                     resources=self.resource_map, uint_fields={'VariationAssetNameHash': var_map})
        rep = self.amb.run_sdk(jobs, self.work, 'sdk', extra=extra)
        rows = iter(rep['rows'])
        watched = collections.Counter()
        unmapped_rids = []
        for x in self.clones:
            row = next(rows)
            if row['partition'] != x['partition'] or row['root_name'] != x['new_name']:
                falha('identidade do SDK não confere: ' + x['new_name'])
            for w in row['watched_strings']:
                watched[w.split(': ', 1)[1]] += 1
            unmapped_rids += [(x['new_name'], v) for v in row['unmapped_resource_refs']]
            x['raw'] = Path(row['output']).read_bytes()
            x['imports'] = row['imports']
        for r in self.res_clones:
            if r['src']['restype'] in (RES_MESH, RES_TEXTURE):
                row = next(rows)
                r['raw'] = Path(row['output']).read_bytes()
                r['meta'] = row.get('meta', r['src']['resmeta'])
        for bi, dep in self.depots.items():
            row = next(rows)
            dep['raw'] = Path(row['output']).read_bytes()
            dep['meta'] = row['meta']
        if unmapped_rids:
            falha('clones citam RES que não foram clonados: ' + json.dumps(unmapped_rids[:5]))
        allowed = {x for x in watched if re.search(r'class(_instanceclass)?\'?$', x)}
        left = {k: v for k, v in watched.items() if k not in allowed}
        if left:
            falha('o token do estádio sobrou nos clones: ' + json.dumps(list(left.items())[:10]))
        for r in self.res_clones:
            t = r['src']['restype']
            if t in (RES_MESH, RES_TEXTURE):
                continue
            path, raw = self.native_res(r['src'])
            if t in RES_ENLIGHTEN:
                old = uuid.UUID(r['owner']['old_primary']).bytes_le
                if raw.count(old) != 1:
                    falha('RES do Enlighten não tem o GUID do EBX exatamente uma vez: ' + r['src']['name'])
                raw = raw.replace(old, uuid.UUID(r['owner']['primary']).bytes_le)
            elif t not in RES_PHYSICS:
                falha(f"tipo de RES não tratado {t:#x} em {r['src']['name']}")
            r['raw'], r['meta'] = raw, r['src']['resmeta']

    # ---------------------------------------------------------- registros
    def payloads(self, plano):
        c = self.c
        cas = self.amb.cas()
        sel = self.sel
        bh = {bi: m['hash'] for bi, m in self.bundle_map.items()}
        cloned_parts = {x['src']['partition'] for x in self.clones}
        in_bundles = [e for e in c['ebx'] if set(e['bundles']) & sel]
        kept = {e['partition'] for e in in_bundles if e['partition'] not in cloned_parts}
        keep_originals = set()
        changed = True
        while changed:
            changed = False
            for e in in_bundles:
                if e['partition'] not in kept and e['partition'] not in keep_originals:
                    continue
                for d in e['dependencies']:
                    if d in cloned_parts and d not in keep_originals and set(self.part_meta[d]['bundles']) & sel:
                        keep_originals.add(d)
                        changed = True
        cloned_ebx = {x['src']['name'].lower() for x in self.clones if x['src']['partition'] not in keep_originals}
        cloned_res = {r['src']['name'] for r in self.res_clones if r['owner']['src']['partition'] not in keep_originals}
        cloned_chunks = {old for r in self.res_clones if r['owner']['src']['partition'] not in keep_originals for old in r['chunks']}
        replaced_shaderstate = set()
        self.shaderstates = []
        for bi, dep in self.depots.items():
            m = self.bundle_map[bi]
            path = m['short'] + '_win32_shaderstate'
            owner = next(x for x in self.clones if x['new_name'].lower() == m['short'].lower()
                         or (x['src']['type'] in ('DetachedSubWorldData', 'SubWorldData') and x['new_name'].lower() == m['short'].lower()))
            payload = hashlib.md5(path.lower().encode('utf8')).digest() + uuid.UUID(owner['partition']).bytes_le
            name = path + 'shaderstateassetid'
            if name in self.dup.used_res_names:
                falha('shader state id já existe: ' + name)
            native = [e for e in c['res'] if e['restype'] == RES_SHADERSTATE and bi in e['bundles']]
            if len(native) != 1:
                falha('bundle sem um único shader state id nativo')
            replaced_shaderstate.add((native[0]['name'], bi))
            rid = int(self.sdk_hashes([name], 'ss_' + str(bi))[name]['xxh64_utf16_lower']) | 1
            if rid in self.dup.used_rids:
                falha('colisão de RID do shader state')
            self.dup.used_rids.add(rid)
            self.dup.used_res_names.add(name)
            self.shaderstates.append(dict(name=name, rid=rid, payload=payload, bundle=bi, owner=owner['new_name']))
        n = collections.Counter()
        for e in c['chunks']:
            hit = [bh[i] for i in e['bundles'] if i in sel]
            if not hit or e['id'] in cloned_chunks:
                continue
            encoded, _ = cas.read_encoded(e)
            mode = uuid.UUID(e['id']).bytes_le[15] & 3
            rec = {'id': e['id'], 'is_added': False, 'original_sha1': e['sha1'], 'bundle_assignment_only': True, 'addedbundles': hit,
                   'logical_size': e['logical_size'], 'h32': self.chunk_h32(e['id']), 'compression_level': 7 if mode == 1 else 8}
            if e['logical_offset']:
                rec['logical_offset'] = e['logical_offset']
            plano.atribuir_nativo('chunk', e['id'], rec, encoded, 'cas')
            n['chunks_nativos'] += 1
        for cc in self.chunk_clones:
            e = cc['src']
            encoded, _ = cas.read_encoded(e)
            rec = {'id': cc['id'], 'is_added': True, 'addedbundles': [bh[bi] for bi in cc['res']['bundle_idx']],
                   'logical_size': e['logical_size'], 'h32': cc['res']['h32'], 'compression_level': 7}
            if e['logical_offset']:
                rec['logical_offset'] = e['logical_offset']
            if cc['superbundle']:
                rec['superbundlehash'] = self.bundle_map[cc['res']['bundle_idx'][0]]['superbundle']
            plano.adicionar('chunk', cc['id'], rec, encoded, 'cas')
        for e in c['res']:
            hit = [bh[i] for i in e['bundles'] if i in sel and (e['name'], i) not in replaced_shaderstate]
            if not hit or e['name'] in cloned_res:
                continue
            raw, encoded, _ = cas.read_asset(e)
            rec = {'name': e['name'], 'is_added': False, 'original_sha1': e['sha1'], 'bundle_assignment_only': True,
                   'addedbundles': hit, 'original_size': e['original_size'], 'compression_level': 7}
            plano.atribuir_nativo('res', e['name'], rec, encoded, 'cas')
            n['res_nativos'] += 1
        for r in self.res_clones:
            rec = {'name': r['new_name'], 'is_added': True, 'restype': r['src']['restype'], 'resrid': r['rid'], 'resmeta': r['meta'],
                   'addedbundles': [bh[bi] for bi in r['bundle_idx']]}
            plano.adicionar('res', r['new_name'], rec, r['raw'], 'raw')
        for bi, dep in self.depots.items():
            rid = int(self.sdk_hashes([dep['name']], 'dep_' + str(bi))[dep['name']]['xxh64_utf16_lower']) | 1
            if rid in self.dup.used_rids:
                falha('colisão de RID do depósito')
            self.dup.used_rids.add(rid)
            dep['rid'] = rid
            rec = {'name': dep['name'], 'is_added': True, 'restype': RES_SBD, 'resrid': rid, 'resmeta': dep['meta'], 'addedbundles': [bh[bi]],
                   'shader_registrations': [[v, k] for k, v in sorted(dep['map'].items(), key=lambda kv: kv[1])]}
            plano.adicionar('res', dep['name'], rec, dep['raw'], 'raw')
        for s in self.shaderstates:
            rec = {'name': s['name'], 'is_added': True, 'restype': RES_SHADERSTATE, 'resrid': s['rid'], 'resmeta': '00' * 16,
                   'addedbundles': [bh[s['bundle']]]}
            plano.adicionar('res', s['name'], rec, s['payload'], 'raw')
        replaced = cloned_parts - keep_originals
        broken = []
        for e in c['ebx']:
            hit = [bh[i] for i in e['bundles'] if i in sel]
            if not hit or e['name'].lower() in cloned_ebx:
                continue
            dep = [d for d in e['dependencies'] if d in replaced and set(self.part_meta[d]['bundles']) & sel]
            if dep:
                broken.append((e['name'], [self.part_meta[d]['name'] for d in dep][:3]))
            raw, encoded, _ = cas.read_asset(e)
            rec = {'name': e['name'], 'is_added': False, 'original_sha1': e['sha1'], 'bundle_assignment_only': True,
                   'addedbundles': hit, 'original_size': e['original_size'], 'compression_level': 7}
            plano.atribuir_nativo('ebx', e['name'], rec, encoded, 'cas')
            n['ebx_nativos'] += 1
        if broken:
            falha(f'{len(broken)} assets nativos mantidos importam originais clonados, ex.: {broken[:5]}')
        for x in self.clones:
            rec = {'name': x['new_name'], 'is_added': True, 'type': x['src']['type'], 'partition': x['partition'], 'addedbundles': x['addedbundles']}
            plano.adicionar('ebx', x['new_name'], rec, x['raw'], 'raw')
        self.report['registros'] = dict(n, chunks_clonados=len(self.chunk_clones), res_clonados=len(self.res_clones),
                                        depositos=len(self.depots), shader_states=len(self.shaderstates), ebx_clonados=len(self.clones))
        self.verificacao = dict(token_novo=self.new_token, token_origem=self.old_token,
                                chaves_nativas=sorted({int(k) for bi in self.sbd_info for k in self.sbd_info[bi]['entries']}),
                                hashes_variacao_antigos=sorted(x['src_name_hash'] for x in self.clones if 'src_name_hash' in x))

    def chunk_h32(self, chunk_id):
        if not hasattr(self, '_owner_h32'):
            want = {uuid.UUID(e['id']).bytes_le: e['id'] for e in self.c['chunks'] if set(e['bundles']) & self.sel}
            owners = collections.defaultdict(set)
            for e in self.c['res']:
                if not set(e['bundles']) & self.sel or e['restype'] not in (RES_MESH, RES_TEXTURE):
                    continue
                _, raw = self.native_res(e)
                for i in range(len(raw) - 15):
                    k = raw[i:i + 16]
                    if k in want:
                        owners[want[k]].add(e['name'])
            if any(len(v) != 1 for v in owners.values()) or len(owners) != len(want):
                falha('donos dos chunks nativos não são únicos')
            names = sorted({next(iter(v)) for v in owners.values()})
            h = self.sdk_hashes(names, 'h32')
            self._owner_h32 = {cid: int(h[next(iter(v))]['djb2_lower64']) for cid, v in owners.items()}
        return self._owner_h32[chunk_id]

    def run(self, plano):
        base.etapa(f'copia_{self.new_id}', f'Cópia {self.new_id} ({self.old_token}): plano')
        self.plan()
        base.progresso(25, 'recursos')
        self.resources()
        base.progresso(45, 'SDK (clones, RES e depósitos)')
        self.sdk()
        base.progresso(80, 'registros do projeto')
        plano.bundles_novos(self.added_bundles)
        self.payloads(plano)
        base.progresso(100, 'cópia pronta')
        self.level_old = f'content/worlds/stadiums/{self.old_token}/{self.old_token}'
        self.level_new = self.rename(self.level_old)
        return self.report


# ------------------------------------------------------------------ duplicação (uma ou várias cópias)
class Duplicacao:
    def __init__(self, amb, copias, saida, projeto_base=None, work=None):
        self.amb = amb
        self.saida = Path(saida).resolve()
        if self.saida.exists():
            falha('o arquivo de saída já existe: ' + str(self.saida))
        self.copias_cfg = copias
        self.projeto_base = projeto_base
        self.work = Path(work) if work else base.pasta_trabalho('duplicar')
        self.report = collections.OrderedDict(saida=str(self.saida), projeto_base=str(projeto_base) if projeto_base else None)

    def load(self):
        base.etapa('preparar', 'Preparando o SDK do FET e o índice do jogo')
        amb = self.amb
        amb.preparar_sdk()
        c = amb.indice()
        self.c = c
        fs = amb.fsinfo(self.work)
        self.superbundles = {s['index']: s for s in fs['superbundles']}
        self.part_meta = {}
        for e in c['ebx']:
            self.part_meta.setdefault(e['partition'], e)
        self.ebx_parts = collections.Counter(e['partition'] for e in c['ebx'])
        self.used_rids = {e['resrid'] for e in c['res']}
        self.used_chunks = {e['id'] for e in c['chunks']}
        self.used_res_names = {e['name'] for e in c['res']}
        self.used_keys = set()
        if self.projeto_base:
            self.fonte = P.Projeto(self.projeto_base, amb.cas())
            h = self.fonte.header
            if h['game'] != 'FC27':
                falha('o projeto não é do FC 27')
            if h['patch'] != c['header']['head']:
                base.aviso(f"o projeto foi salvo para outra versão do jogo (patch {h['patch']}, jogo atual {c['header']['head']}); "
                           'o FET pode avisar ao abrir')
            self.ebx_parts.update(e['partition'] for e in self.fonte.parsed['ebx'] if 'partition' in e)
            self.used_rids |= {e['resrid'] for e in self.fonte.parsed['resources'] if 'resrid' in e}
            self.used_chunks |= {e['id'] for e in self.fonte.parsed['chunks']}
            self.used_res_names |= {e['name'] for e in self.fonte.parsed['resources']}
            self.used_keys |= {int(k) for k in self.fonte.parsed['shadersources']}
        else:
            self.fonte = P.modelo_vazio(amb)
            self.fonte.cas = amb.cas()
        self.plano = P.Plano(self.fonte, self.work)
        base.progresso(100, 'pronto')

    def conferir_ids(self):
        """IDs novos livres no mapa de estádios (do jogo ou do projeto) e no banco."""
        slm = self.registro_atual(SLM)
        dump = self.amb.run_sdk([{'kind': 'dump', 'input': str(slm), 'output': str(self.work / 'slm_atual.json')}], self.work, 'slm_dump')
        d = base.ler_json(self.work / 'slm_atual.json')
        usados = {int(i['KeyId']) for i in d['instances'][0]['fields']['SublevelItems']}
        novos = [int(x['novo_id']) for x in self.copias_cfg]
        if len(set(novos)) != len(novos):
            falha('IDs novos repetidos: ' + ', '.join(map(str, novos)))
        ocupados = sorted(set(novos) & usados)
        if ocupados:
            falha('IDs já usados por estádios do jogo ou do projeto: ' + ', '.join(map(str, ocupados)))
        self.slm_ids = sorted(usados)

    def registro_atual(self, name):
        """Arquivo com a versão atual de um EBX de registro: a do projeto-base, senão a nativa."""
        rec = self.fonte.record('ebx', name)
        if rec is not None:
            f = self.work / ('base_' + sha256(name.lower().encode())[:16] + '.bin')
            f.write_bytes(self.fonte.raw('ebx', name))
            return f
        p, _ = self.amb.native('ebx', name)
        return p

    def registrar(self):
        base.etapa('registro', 'Registrando os estádios novos (mapa de estádios e loaders)')
        l1 = self.amb.dumps([SLM_L1], self.work)[SLM_L1.lower()]
        in_l1 = {int(i['KeyId']) for i in l1['instances'][0]['fields']['SublevelItems']}
        out = self.work / 'registro'
        out.mkdir(exist_ok=True)
        jobs, finais = [], {}
        for name in [SLM, SLM_L1] + LOADERS:
            atual = self.registro_atual(name)
            k = 0
            for cp in self.copias:
                if name == SLM_L1 and cp.old_id not in in_l1:
                    continue
                o = out / f'{sha256(name.lower().encode())[:12]}_{k}.bin'
                if o.exists():
                    o.unlink()
                if name in (SLM, SLM_L1):
                    jobs.append(dict(kind='slm_add', input=str(atual), output=str(o), key=cp.new_id, model_key=cp.old_id, name=cp.level_new))
                else:
                    ident = 'loader:' + name.lower() + ':' + cp.level_new.lower()
                    jobs.append(dict(kind='loader_register', input=str(atual), output=str(o), model=cp.level_old, name=cp.level_new,
                                     instance_guid=str(uuid.uuid5(NS, ident))))
                atual = o
                k += 1
            if k:
                finais[name] = atual
        rep = self.amb.run_sdk(jobs, self.work, 'registro')
        self.report['registro'] = [{k: r[k] for k in ('kind', 'sha256', 'items_before', 'items_after', 'appended_lists',
                                                       'copied_connections', 'model_flags', 'new_flags') if k in r} for r in rep['rows']]
        for name, f in finais.items():
            e = self.c['ebx_by_name'][name.lower()]
            self.plano.editar('ebx', e['name'], Path(f).read_bytes(), 'raw',
                              original={'name': e['name'], 'is_added': False, 'original_sha1': e['sha1']})
        base.progresso(100, f'{len(jobs)} registros')

    # ---------------------------------------------------------- banco
    def banco(self):
        base.etapa('banco', 'Banco de dados: linhas stadiums e audiostadium')
        meta_path = self.amb.meta_db()
        ch = self.fonte.chunk_db()
        if ch is not None:
            db = self.amb.cas().decompress(self.fonte.encoded(ch))
            origem_db = 'projeto'
        else:
            db = self.amb.db_nativo()
            origem_db = 'jogo'
        src = self.work / 'fifa_ng_db_entrada.db'
        src.write_bytes(db)
        _, tables = t3db.read_db(str(src), str(meta_path))
        by = {t.name: t for t in tables}
        nt = struct.unpack_from('<I', db, 16)[0]
        base0 = 0x18 + 8 * nt + 4
        entries = [struct.unpack_from('<4sI', db, 0x18 + 8 * i) for i in range(nt)]
        order = sorted(range(nt), key=lambda i: entries[i][1])
        span = {}
        for k, i in enumerate(order):
            span[entries[i][0].decode('latin1')] = (base0 + entries[i][1], base0 + entries[order[k + 1]][1] if k + 1 < nt else len(db))

        def field(t, name):
            return next(f for f in t.fields if f.name == name)

        def set_int(rec, f, value):
            raw = value - f.low
            if not 0 <= raw < (1 << f.depth):
                falha(f'{f.name}={value} fora da faixa do banco')
            v = int.from_bytes(rec, 'little')
            v = (v & ~(((1 << f.depth) - 1) << f.bitoff)) | (raw << f.bitoff)
            return v.to_bytes(len(rec), 'little')

        def get_int(rec, f):
            return t3db._get_bits(rec, f.bitoff, f.depth) + f.low

        def table_blob(t, edit):
            start, end = span[t.sn]
            hdr = list(struct.unpack_from('<IIIIHHHHIII', db, start))
            flags, recsize, nbits, strlen, nrec, nvalid, u6, u7, nf, u9, tcrc = hdr
            if strlen or nrec != nvalid:
                falha(f'{t.name}: layout não suportado (strings {strlen}, registros {nrec}/{nvalid})')
            R = start + 36 + 16 * nf
            rows = [db[R + i * recsize:R + (i + 1) * recsize] for i in range(nrec)]
            fdesc = db[start + 36:R]

            def build(rws):
                h = struct.pack('<IIIIHHHHII', flags, recsize, nbits, strlen, len(rws), len(rws), u6, u7, nf, u9)
                h += struct.pack('<I', t3db.crc32_msb(h))
                body = fdesc + b''.join(rws)
                body += b'\0' * ((-len(body)) % 4)
                return h + body + struct.pack('<I', t3db.crc32_msb(body))
            if build(rows) != db[start:end]:
                falha(f'{t.name}: autoteste de reconstrução falhou')
            new_rows, pos = edit(t, rows)
            if len(new_rows) > 0xFFFF:
                falha('capacidade da tabela')
            return build(new_rows), rows, new_rows, pos

        def insert(rows, ids, rec, new_id):
            pos = sum(1 for i in ids if i < new_id) if ids == sorted(ids) else len(rows)
            ids.insert(pos, new_id)
            rows.insert(pos, rec)
            return pos

        def edit_stadiums(t, rows):
            idf, namef, homef = field(t, 'stadiumid'), field(t, 'name'), field(t, 'hometeamid')
            rows = list(rows)
            ids = [get_int(r, idf) for r in rows]
            pos = []
            for cp in self.copias:
                if cp.new_id in ids:
                    falha(f'o banco já tem o estádio {cp.new_id}')
                if ids.count(cp.old_id) != 1:
                    falha(f'stadiums: estádio {cp.old_id} ausente ou repetido no banco')
                rec = rows[ids.index(cp.old_id)]
                rec = set_int(rec, idf, cp.new_id)
                rec = set_int(rec, homef, 0)
                nb = cp.db_name.encode('utf8')
                o, n = namef.bitoff // 8, namef.depth // 8
                if namef.ftype != 0 or len(nb) >= n:
                    falha(f'o nome "{cp.db_name}" passa do limite do banco ({n - 1} bytes)')
                rec = rec[:o] + nb + b'\0' * (n - len(nb)) + rec[o + n:]
                pos.append(insert(rows, ids, rec, cp.new_id))
            return rows, pos

        def edit_audio(t, rows):
            idf = field(t, 'stadiumid')
            rows = list(rows)
            ids = [get_int(r, idf) for r in rows]
            pos = []
            for cp in self.copias:
                if cp.new_id in ids:
                    falha(f'o banco (audiostadium) já tem o estádio {cp.new_id}')
                if ids.count(cp.old_id) != 1:
                    falha(f'audiostadium: estádio {cp.old_id} ausente ou repetido')
                rec = set_int(rows[ids.index(cp.old_id)], idf, cp.new_id)
                pos.append(insert(rows, ids, rec, cp.new_id))
            return rows, pos

        blobs, checks = {}, {}
        for tname, fn in (('stadiums', edit_stadiums), ('audiostadium', edit_audio)):
            blob, old_rows, new_rows, pos = table_blob(by[tname], fn)
            blobs[tname] = blob
            checks[tname] = dict(linhas_antes=len(old_rows), linhas_depois=len(new_rows), posicoes=pos)
        dest = self.work / 'fifa_ng_db.db'
        if dest.exists():
            dest.unlink()
        t3db.write_db(db, tables, blobs, str(dest))
        out = dest.read_bytes()
        _, t2 = t3db.read_db(str(dest), str(meta_path))
        b2 = {t.name: t for t in t2}
        ne = [struct.unpack_from('<4sI', out, 0x18 + 8 * i) for i in range(nt)]
        no = sorted(range(nt), key=lambda i: ne[i][1])
        nspan = {}
        for k, i in enumerate(no):
            nspan[ne[i][0].decode('latin1')] = (base0 + ne[i][1], base0 + ne[no[k + 1]][1] if k + 1 < nt else len(out))
        same = 0
        for t in tables:
            if t.name in blobs:
                continue
            a, b = span[t.sn], nspan[t.sn]
            if db[a[0]:a[1]] != out[b[0]:b[1]]:
                falha('tabela alterada sem querer: ' + t.name)
            same += 1
        for tname in blobs:
            old_rows, new_rows = by[tname].rows, b2[tname].rows
            fnames = [f.name for f in by[tname].fields]
            ins = list(new_rows)
            for r in old_rows:
                ins.remove(r)
            if len(new_rows) != len(old_rows) + len(self.copias) or len(ins) != len(self.copias):
                falha(tname + ': comparação de linhas falhou')
            for row in ins:
                new = dict(zip(fnames, row))
                cp = next(x for x in self.copias if str(x.new_id) == new['stadiumid'])
                src = dict(zip(fnames, next(r for r in old_rows if r[fnames.index('stadiumid')] == str(cp.old_id))))
                checks[tname].setdefault('campos_mudados', {})[str(cp.new_id)] = {k: (src[k], new[k]) for k in fnames if src[k] != new[k]}
            if [r for r in new_rows if r not in ins] != old_rows:
                falha(tname + ': linhas originais fora de ordem')
        checks['outras_tabelas_identicas'] = same
        checks['origem'] = origem_db
        checks['sha256'] = sha256(out)
        self.report['banco'] = checks
        h = P.DB_LEGACY_HASH
        if ch is not None:
            self.plano.editar('chunk', ch['id'], out, 'raw', record={'logical_size': len(out)})
        else:
            g = bytearray(struct.pack('<QQ', h, h ^ 1))
            g[15] = 1
            db_chunk_id = str(uuid.UUID(bytes_le=bytes(g)))
            if db_chunk_id in self.c['chunk_by_id']:
                falha('o id do chunk do banco colide')
            self.plano.adicionar('chunk', db_chunk_id, {'id': db_chunk_id, 'is_added': True, 'legacyhash': h,
                                                        'superbundlehash': next(s['hash'] for s in self.superbundles.values() if s['name'] == DB_GLOBALS_SUPERBUNDLE),
                                                        'logical_size': len(out)}, out, 'raw')
            self.plano.mover_para_inicio('chunk', db_chunk_id)
        base.progresso(100, f"{len(self.copias)} estádio(s) no banco")

    # ---------------------------------------------------------- tudo
    def run(self, gravar=True):
        self.load()
        self.copias = [Copia(self, x['origem'], x['novo_id'], x['nome'], x.get('fisica_nativa', False)) for x in self.copias_cfg]
        self.conferir_ids()
        self.report['copias'] = []
        for cp in self.copias:
            self.report['copias'].append(cp.run(self.plano))
        self.registrar()
        self.banco()
        if not gravar:
            return self.report
        base.etapa('gravar', 'Gravando o projeto do FET')
        perfil = P.perfil_identidade(self.amb)
        if perfil is None:
            base.aviso('o cache ou o SDK do FET são de outra versão que a do perfil de identidade conferido; a auditoria de '
                       'nomes por MD5 fica a cargo da verificação da ferramenta')
        self.report['projeto'] = self.plano.gravar(self.saida, perfil)
        base.progresso(100, 'projeto gravado')
        base.gravar_json(self.work / 'relatorio.json', self.report)
        return self.report
