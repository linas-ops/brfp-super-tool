"""Conversão de um estádio do FIFA 16 para o FC 27, sempre sobre a base El Grandioso (estádio 181).

Os estádios do FIFA 16 têm todos o mesmo formato, e a base é sempre a mesma: uma duplicata completa do El Grandioso com o
ID novo (o mesmo método do 703, confirmado em partida). Sobre ela, cada mudança é uma troca de registro ou um registro
novo, aplicados no modo edit (os registros não tocados ficam byte a byte) — o mesmo caminho do Morumbi v3, que
funcionou em partida em 31/10/2026:
- os materiais do FIFA 16 divididos entre os seis meshes do El Grandioso que o sub-mundo principal sempre carrega
  (arquibancada inferior e superior, teto, grades, túnel, bancos), cada LOD dentro do que os meshes do FC 27 usam (índices
  de 16 bits, poucos MB, dezenas de subsets); subsets clonados de subsets do El Grandioso que lançam a própria sombra
  (grades diffuseopaque, poste diffusealpha);
- por material: um MeshMaterial (o preset nativo do modelo), uma MeshMaterialVariation no MeshVariationDb principal e
  uma entrada no depósito de shaders (bloco do modelo, textura de cor remapeada) registrada contra a chave do modelo;
- texturas novas (EBX + RES + chunk) das cadeias de mips do FIFA 16;
- o telão com as telas do FIFA 16, o gramado do FC 27 recortado até o piso do estádio (sem a pista de atletismo do El
  Grandioso), a arquitetura do El Grandioso escondida, a torcida, os glares e os personagens laterais do estádio novo;
- os banners dos times do FC 27 no lugar das faixas do FIFA 16 (peças com o papel "banner", motor/fifa16/banners.py), os
  reservas nas cadeiras do banco (motor/fifa16/bancos.py) e as luzes da torcida acompanhando a torcida nova
  (motor/fifa16/iluminacao.py).
O pré-cálculo de luz de outro estádio (motor/fifa16/luz.py) está desativado: com ele a partida fica carregando sem fim.
Nenhum subset fica sem geometria (o FC 27 não tem nenhum): os que sobram ganham um triângulo de área zero, e os meshes que
a lógica do jogo liga e desliga vão para baixo do piso em vez de serem esvaziados. Toda partição gravada fica na ordem de
instâncias do FC 27 (exportadas primeiro, a primária no 0 e as outras pelo GUID): fora dela o jogo fecha (v1 e v2).
"""
from __future__ import annotations
import collections
import hashlib
import json
import re
import shutil
import struct
import uuid
from pathlib import Path

import numpy as np

from .. import base, projeto as P, t3db
from ..base import NS, falha, sha256
from . import analise, malha, preparar

BASE_ID = 181
FAMILIA = 'generic_south_american'
RES_MESH, RES_TEXTURE, RES_SBD = 0x49b156d4, 0x6bde20ba, 0x73312045
HOSTS = ('standslower', 'standsupper', 'roof', 'railings', 'entrancetunnel', 'playerbenches')
HOST_BUDGET = int(5.5 * 2**20)  # bytes de vértices + índices por LOD hospedeiro (LODs de estádio do FC 27 chegam a ~6 MB)
HOST_MAX_SUBSETS = 40           # os meshes do FC 27 têm no máximo 70
STRIDE = {'opaque': 36, 'alphatest': 40}
CATEGORIES = {'opaque': [0, 3, 4], 'alphatest': [0, 3, 4], 'jumbotron': [0, 3, 4]}
RECEITAS = Path(__file__).resolve().parent / 'receitas'


def receita_pronta(sid):
    """Receita guardada para o estádio do FIFA 16 (ex.: a do Morumbi v3), ou None."""
    for f in RECEITAS.glob('*.json'):
        try:
            r = json.loads(f.read_text(encoding='utf8'))
        except (OSError, ValueError):
            continue
        if int(r.get('fifa16_id', -1)) == int(sid):
            return r
    return None


class Conversao:
    def __init__(self, amb, cfg, base_proj, dup, prep, work):
        self.amb, self.cfg = amb, cfg
        self.rc = cfg['receita']
        self.N = int(cfg['novo_id'])
        self.tok = f'{FAMILIA}_{self.N}'
        self.G = f'content/worlds/components/stadiums/{self.tok}/'
        self.S = f'content/worlds/stadiums/{self.tok}/'
        self.M = self.S + self.rc.get('pasta_nome', f'fifa16_{self.rc["fifa16_id"]}') + '/'
        # identidade dos GUIDs e das chaves de shader: a da receita só no ID em que ela foi usada (Morumbi v3 = 703)
        ident = self.rc.get('identidade')
        if ident and int(self.rc.get('identidade_id', self.N)) != self.N:
            ident = f'{ident}_{self.N}'
        self.ident = ident or f'fifa16_{self.rc["fifa16_id"]}_{self.N}'
        self.POLE_MESH = self.G + 'light_south_american_stadium_pole_01_mesh'
        self.RAIL_MESH = self.G + 'railings_mesh'
        self.SCORE_MESH = self.G + 'scoreclock_mesh'
        self.MVDB = self.S + f'{self.tok}/meshvariationdb_win32'
        self.TEX_TEMPLATE = {'BC1': self.S + 'copias/worlds/textures/legacy/concrete/architecture/concrete_arch_bottomwalkway1_b_color',
                             'BC3': self.S + 'copias/worlds/textures/legacy/misc/gird_b_color'}
        self.TEMPLATE_SUBSET = {'opaque': (self.RAIL_MESH, 6), 'alphatest': (self.POLE_MESH, 0)}
        self.p = base_proj
        self.dup = dup
        self.prep = Path(prep)
        self.work = Path(work)
        for d in ('in', 'out'):
            (self.work / d).mkdir(parents=True, exist_ok=True)
        self.plano = P.Plano(base_proj, self.work)
        self.report = collections.OrderedDict(base_id=BASE_ID, novo_id=self.N, fifa16_id=self.rc['fifa16_id'], prep=str(self.prep))
        self.edits, self.res_edits, self.chunk_edits = {}, {}, {}
        self.luz = None  # pré-cálculo de luz de outro estádio (motor/fifa16/luz.py): desativado
        self.lugares = None  # lugares da torcida do FIFA 16 (m), quando o estádio tem crowd_<id>_1.dat
        self._tri16 = None

    def u5(self, *parts):
        return str(uuid.uuid5(NS, f'{self.ident}:' + ':'.join(parts)))

    # ------------------------------------------------------------ entradas
    def load(self):
        self.subsets = json.loads((self.prep / 'subsets.json').read_text(encoding='utf8'))
        self.textures = json.loads((self.prep / 'textures.json').read_text(encoding='utf8'))
        if sha256((self.prep / 'geometry.bin').read_bytes()) != self.subsets['geometry_sha256']:
            falha('geometry.bin não corresponde ao subsets.json')
        self.c = self.amb.indice()
        cp = self.dup.copias[-1]
        main_bi = next(bi for bi, m in cp.bundle_map.items() if m['new'].endswith(f'/{self.tok}/{self.tok}'))
        self.MAIN_BUNDLE = cp.bundle_map[main_bi]['hash']
        self.MAIN_SUPERBUNDLE = cp.bundle_map[main_bi]['superbundle']
        self.MAIN_DEPOT = cp.depots[main_bi]['name']
        self.sa = Path(self.subsets.get('sceneassets') or Path(self.subsets['source']) / 'data' / 'sceneassets')

    def base_raw(self, kind, name):
        b = self.p.raw(kind, name)
        f = self.work / 'in' / (kind + '__' + sha256(name.lower().encode())[:20] + '.bin')
        if not f.exists():
            f.write_bytes(b)
        return f, b

    def run(self, jobs, tag, ferramenta='ConvertTool'):
        return self.amb.run_sdk(jobs, self.work / 'sdk', tag, ferramenta=ferramenta)

    def ebx_dump(self, name, path=None):
        o = self.work / 'in' / ('dump__' + sha256(name.lower().encode())[:20] + '.json')
        if not o.exists():
            f = path or self.base_raw('ebx', name)[0]
            self.run([dict(kind='ebx_dump', input=str(f), output=str(o))], 'dump')
        return json.loads(o.read_text(encoding='utf8'))

    def mesh_dump(self, name, res_path=None, meta=None):
        o = self.work / 'in' / ('mesh__' + sha256(name.lower().encode())[:20] + '.json')
        if not o.exists():
            f = res_path or self.base_raw('res', name)[0]
            meta = meta or self.p.record('res', name)['resmeta']
            self.run([dict(kind='mesh_dump', input=str(f), meta=meta, output=str(o))], 'meshdump')
        return json.loads(o.read_text(encoding='utf8'))

    def hashes(self, names):
        return self.amb.hashes(names, self.work / 'sdk', 'hashes')

    def part_name(self, ptr):
        if not isinstance(ptr, str) or not ptr.startswith('ptr:ext:'):
            return ''
        g = ptr.split(':')[2].split('/')[0]
        if not hasattr(self, '_p_by_part'):
            self._p_by_part = {e['partition']: e['name'] for e in self.p.parsed['ebx'] if 'partition' in e}
        e = self.c['ebx_by_part'].get(g)
        return self._p_by_part.get(g) or (e['name'] if e else None) or g

    def replace(self, kind, key, data, encoding='raw', record=None):
        self.plano.editar(kind, key, data, encoding, record=record)

    def add(self, kind, key, data, record, encoding='raw'):
        self.plano.adicionar(kind, key, record, data, encoding)

    # ------------------------------------------------------------ modelos e identidades
    def templates(self):
        p = self.p
        mvdb = self.ebx_dump(self.MVDB)
        self.mvdb_dump = mvdb
        entries = mvdb['instances'][0]['fields']['Entries']

        def entry_of(mesh_name):
            rec = p.record('ebx', mesh_name)
            prim = self.ebx_dump(mesh_name)['instances'][0]['guid']
            want = f"ptr:ext:{rec['partition']}/{prim}"
            hits = [i for i, e in enumerate(entries) if e['Mesh'] == want and e['VariationAssetNameHash'] == 0]
            if len(hits) != 1:
                falha(f'entrada do MeshVariationDb para {mesh_name}: {hits}')
            return hits[0]
        self.hosts = collections.OrderedDict()
        for h in HOSTS:
            mesh = self.G + h + '_mesh'
            md = self.mesh_dump(mesh)
            if md['type'] != 'Composite' or len(md['lods']) != 1:
                falha('hospedeiro não é Composite de um LOD: ' + mesh)
            self.hosts[h] = dict(mesh=mesh, rec=p.record('ebx', mesh), dump=self.ebx_dump(mesh), mesh_dump=md, entry=entry_of(mesh),
                                 blueprint=self.G + h, world=self.S + h)
        self.score_mesh = self.mesh_dump(self.SCORE_MESH)
        dep = p.record('res', self.MAIN_DEPOT)
        src = p.parsed['shadersources']
        self.depot_regs = [(int(a), int(src[b])) for a, b in dep['shader_registrations']]
        alias_to_native = dict(self.depot_regs)
        self.tmpl = {}
        for role, (mesh, idx) in self.TEMPLATE_SUBSET.items():
            md = self.mesh_dump(mesh)
            sub = md['lods'][0]['subsets'][idx]
            lod = md['lods'][0]
            if sorted(c for c in range(5) if idx in lod['categories'][c]) != CATEGORIES[role]:
                falha(f'modelo {role} não está nas categorias {CATEGORIES[role]}')
            if sub['stride'] != STRIDE[role]:
                falha(f'modelo {role}: stride {sub["stride"]}')
            key = int(sub['key'])
            if key not in alias_to_native:
                falha(f'chave do modelo {role} não registrada no depósito principal')
            res_path, _ = self.base_raw('res', mesh)
            mat = entries[entry_of(mesh)]['Materials'][sub['material_index']]
            var_index = int(mat['MaterialVariation'].split(':')[2])
            var = mvdb['instances'][var_index]['fields']
            tex = {t['ParameterName']: t['Value'] for t in var['Shader']['TextureParameters']}
            d = self.ebx_dump(mesh)
            mm = d['instances'][int(d['instances'][0]['fields']['Materials'][sub['material_index']].split(':')[2])]
            if mm['type'] != 'Frostbite.Render.MeshMaterial':
                falha('material do modelo não é MeshMaterial: ' + role)
            self.tmpl[role] = dict(mesh=mesh, subset=idx, key=key, native_key=alias_to_native[key], res=str(res_path),
                                   meta=p.record('res', mesh)['resmeta'], material=sub['material'], material_index=sub['material_index'],
                                   variation_index=var_index, mvdb_material=mat, colour=tex.get('colorTexture'), meshmaterial=mm['fields'])
            if tex.get('colorTexture') is None or not tex['colorTexture'].startswith('ptr:ext:'):
                falha('modelo sem colorTexture externa: ' + role)
        self.report['modelos'] = {r: {k: v for k, v in t.items() if k in ('mesh', 'subset', 'key', 'native_key', 'material', 'colour')}
                                  for r, t in self.tmpl.items()}

    def identities(self):
        names = []
        self.tex = {}
        for key, t in self.textures.items():
            name = (self.M + 'textures/' + key).lower()
            self.tex[key] = dict(name=name, partition=self.u5(name, 'partition'), primary=self.u5(name, 'primary'), **t)
            names.append(name)
        by = collections.OrderedDict()
        for s in self.subsets['subsets']:
            if s['role'] not in ('opaque', 'alphatest'):
                continue
            if s['vertices'] > 65535 or s['vertices'] < 3 or s['triangles'] < 1:
                falha('subset preparado fora dos limites: ' + s['name'])
            by.setdefault(s.get('material', s['name']), []).append(s)
        self.mats = []
        for name, pieces in by.items():
            role, tex = pieces[0]['role'], pieces[0]['texture']
            if any(x['role'] != role or x['texture'] != tex for x in pieces):
                falha('peças de um material com papéis/texturas diferentes: ' + name)
            size = sum(x['vertices'] * STRIDE[role] + x['triangles'] * 6 for x in pieces)
            self.mats.append(dict(name=name, role=role, texture=tex, pieces=pieces, bytes=size))
        self.assign_hosts()
        h = self.hashes(names)
        used_rids = {e['resrid'] for e in self.c['res']} | {e['resrid'] for e in self.p.parsed['resources'] if 'resrid' in e}
        used_chunks = {e['id'] for e in self.c['chunks']} | {e['id'] for e in self.p.parsed['chunks']}
        for t in self.tex.values():
            hv = int(h[t['name']]['xxh64_utf16_lower'])
            rid = hv | 1
            while rid in used_rids:
                rid = (rid + 2) & 0xffffffffffffffff
            used_rids.add(rid)
            t['rid'] = rid
            t['h32'] = int(h[t['name']]['djb2_lower64'])
            n = 1
            while True:  # FET AssetManager.GenerateDeterministicChunkGuid
                b = bytearray(struct.pack('<QQ', hv, hv ^ n))
                b[15] = 1
                g = str(uuid.UUID(bytes_le=bytes(b)))
                if g not in used_chunks:
                    used_chunks.add(g)
                    t['chunk'] = g
                    break
                n += 1
        native_keys = {k for k, _ in self.depot_regs} | {v for _, v in self.depot_regs} | set(self.p.parsed['shadersources'])
        for m in self.mats:
            k = int.from_bytes(hashlib.sha256((f'{self.ident}:key:' + m['name']).encode()).digest()[:8], 'little')
            while k in native_keys or k == 0:
                k = (k + 1) & 0xffffffffffffffff
            native_keys.add(k)
            m['key'] = k
            m['meshmaterial'] = self.u5(self.hosts[m['host']]['mesh'], m['name'], 'meshmaterial')

    def assign_hosts(self):
        """Maior material primeiro, no hospedeiro com menos bytes que ainda tem espaço (orçamentos de bytes e subsets).
        Com o ajuste automático (padrão), se algum material não couber inteiro, a distribuição é refeita repartindo pelas
        peças os materiais que não cabem: cada parte vira um material próprio (mesma textura e papel) noutro hospedeiro.
        Os estádios que cabem sem repartir saem exatamente como antes (Morumbi v3)."""
        try:
            load, count, divididos = self.distribuir(dividir=False)
        except base.Falha:
            if not self.rc.get('ajuste_automatico', True):
                raise
            load, count, divididos = self.distribuir(dividir=True)
        self.mats.sort(key=lambda m: (HOSTS.index(m['host']), m['role'] != 'alphatest', m['name']))
        self.report['hospedeiros'] = {h: dict(materiais=sum(1 for m in self.mats if m['host'] == h), subsets=count[h], bytes=load[h]) for h in HOSTS}
        if divididos:
            self.report['materiais_repartidos'] = divididos
            for nome, partes in divididos.items():
                base.aviso(f'ajuste automático: o material {nome} foi repartido entre {len(partes)} meshes do El Grandioso '
                           f'({", ".join(partes)})')

    def distribuir(self, dividir):
        load = {h: 0 for h in HOSTS}
        count = {h: 0 for h in HOSTS}
        out, divididos = [], {}

        def cabe(h, b, n):
            return load[h] + b <= HOST_BUDGET and count[h] + n <= HOST_MAX_SUBSETS

        def por(m, h):
            m['host'] = h
            load[h] += m['bytes']
            count[h] += len(m['pieces'])
            out.append(m)
        for m in sorted(self.mats, key=lambda m: -m['bytes']):
            fit = [h for h in HOSTS if cabe(h, m['bytes'], len(m['pieces']))]
            if fit:
                por(m, min(fit, key=lambda x: (load[x], HOSTS.index(x))))
                continue
            if not dividir or len(m['pieces']) < 2:
                self.falha_tamanho(m)
            # peça a peça (maior primeiro) no hospedeiro com mais espaço que ainda a comporta; uma parte por hospedeiro
            grupos = collections.OrderedDict()
            livre = dict(load)
            ns = dict(count)
            for s in sorted(m['pieces'], key=lambda s: -self.piece_bytes(s)):
                b = self.piece_bytes(s)
                fit = [h for h in HOSTS if livre[h] + b <= HOST_BUDGET and ns[h] + 1 <= HOST_MAX_SUBSETS]
                if not fit:
                    self.falha_tamanho(m)
                h = min(fit, key=lambda x: (livre[x], HOSTS.index(x)))
                grupos.setdefault(h, []).append(s)
                livre[h] += b
                ns[h] += 1
            partes = []
            for k, h in enumerate(sorted(grupos, key=HOSTS.index)):
                pecas = sorted(grupos[h], key=lambda s: s.get('piece', 0))
                nome = f"{m['name']}_parte{k + 1}"
                por(dict(m, name=nome, pieces=pecas, bytes=sum(self.piece_bytes(s) for s in pecas)), h)
                partes.append(h)
            divididos[m['name']] = partes
        self.mats = out
        return load, count, divididos

    @staticmethod
    def piece_bytes(s):
        return s['vertices'] * STRIDE[s['role']] + s['triangles'] * 6

    def falha_tamanho(self, m):
        total = sum(x['bytes'] for x in self.mats)
        cap = HOST_BUDGET * len(HOSTS)
        maiores = sorted(self.mats, key=lambda x: -x['bytes'])[:5]
        lista = ', '.join(f"#{'/'.join(str(p) for p in sorted({p for s in x['pieces'] for p in s.get('prims', [])})) or x['name']} "
                          f"({x['bytes'] / 2**20:.1f} MB)" for x in maiores)
        if total > cap * 0.97 or self.rc.get('ajuste_automatico', True):
            falha(f"o estádio tem {total / 2**20:.1f} MB de geometria e os seis meshes do El Grandioso comportam "
                  f"{cap / 2**20:.1f} MB: descarte peças que não aparecem, marque \"1 lado\" nas que só são vistas de frente ou use "
                  f"faces \"vista\". Maiores peças: {lista}")
        falha(f"o material {m['name']} ({m['bytes'] / 2**20:.1f} MB) não cabe inteiro em nenhum mesh do El Grandioso "
              f"(até {HOST_BUDGET / 2**20:.1f} MB cada): ligue o ajuste automático de tamanho para reparti-lo entre vários meshes")

    def mats_of(self, host):
        return [m for m in self.mats if m['host'] == host]

    # ------------------------------------------------------------ texturas
    def build_textures(self):
        jobs, ebx_jobs = [], []
        tmpl_ebx = {f: self.base_raw('ebx', n)[0] for f, n in self.TEX_TEMPLATE.items()}
        tmpl_res = {f: self.base_raw('res', n)[0] for f, n in self.TEX_TEMPLATE.items()}
        self.tex_res_meta = {f: self.p.record('res', n)['resmeta'] for f, n in self.TEX_TEMPLATE.items()}
        alpha_tex = {m['texture'] for m in self.mats if m['role'] == 'alphatest'}
        for key, t in self.tex.items():
            o = self.work / 'out' / ('tex_' + key)
            jobs.append(dict(kind='texture_build', input=key, template=str(tmpl_res[t['format']]), data=str(self.prep / 'textures' / (key + '.bin')),
                             sha256=t['sha256'], format=t['format'], width=t['width'], height=t['height'], mips=t['mips'],
                             mip_sizes=t['mip_sizes'], name=t['name'], chunk=t['chunk'], alpha=key in alpha_tex,
                             output_res=str(o) + '.res', output_chunk=str(o) + '.chunk'))
            ebx_jobs.append(dict(kind='ebx_ops', input=str(tmpl_ebx[t['format']]), output=str(o) + '.ebx', expect_new_name=t['name'], ops=[
                dict(op='partition', guid=t['partition']), dict(op='primary_guid', guid=t['primary']),
                dict(op='set', target={'primary': True}, path='Name', value=t['name']),
                dict(op='set', target={'primary': True}, path='Resource', value={'res': str(t['rid'])}),
                dict(op='set', target={'primary': True}, path='AuthoredWidth', value=t['width']),
                dict(op='set', target={'primary': True}, path='AuthoredHeight', value=t['height']),
                dict(op='set', target={'primary': True}, path='CropInfo', value={'fields': {'X': 0, 'Y': 0, 'Z': t['width'], 'W': t['height']}})]))
        rows = self.run(jobs, 'textures')['rows']
        for r in rows:
            t = self.tex[r['input']]
            t['res'], t['res_meta'] = Path(r['output_res']).read_bytes(), self.tex_res_meta[t['format']]
            t['cas'] = Path(r['output_chunk']).read_bytes()
            t['chunk_rec'] = dict(logical_offset=r['logical_offset'], logical_size=r['logical_size'], original_size=r['original_size'],
                                  pixel_format=r['pixel_format'], compressed_offsets=r['compressed_offsets'], mip_base=r['mip_base'])
        for r in self.run(ebx_jobs, 'texture_ebx')['rows']:
            key = Path(r['output']).name[4:-4]
            self.tex[key]['ebx'] = Path(r['output']).read_bytes()
            if r['partition'] != self.tex[key]['partition']:
                falha('partição da textura não aplicada')
        self.report['texturas'] = len(self.tex)

    # ------------------------------------------------------------ materiais (mesh materials, MVDB, depósito)
    @staticmethod
    def ext_value(ptr):
        part, inst = ptr.split(':')[2].split('/')
        return {'ext': [part, inst]}

    def meshmaterial_ops(self, tag, role, source_fields):
        t = self.tmpl[role]['meshmaterial']
        ops = [dict(op='set', target={'tag': tag}, path='Shader.Shader', value=self.ext_value(t['Shader']['Shader']))]
        for k, v in t['Shader'].items():
            if k not in ('Shader', '$type') and v != source_fields['Shader'][k]:
                if isinstance(v, list) and not v:
                    ops.append(dict(op='list_set', target={'tag': tag}, path='Shader.' + k, items=[]))
                else:
                    falha(f'MeshMaterial modelo ({role}) tem Shader.{k} próprio')
        for k, v in t.items():
            if k in ('Shader', '$type') or v == source_fields.get(k):
                continue
            if isinstance(v, (bool, int, float)) or (isinstance(v, str) and not v.startswith('ptr:')):
                ops.append(dict(op='set', target={'tag': tag}, path=k, value=v))
            elif isinstance(v, list) and not v:
                ops.append(dict(op='list_set', target={'tag': tag}, path=k, items=[]))
            elif v == 'ptr:null':
                ops.append(dict(op='set', target={'tag': tag}, path=k, value={'null': True}))
            else:
                falha(f'MeshMaterial modelo ({role}) difere em {k}')
        return ops

    def build_mesh_ebx(self):
        self.host_ebx = {}
        for h, H in self.hosts.items():
            d = H['dump']
            src = int(d['instances'][0]['fields']['Materials'][0].split(':')[2])
            if d['instances'][src]['type'] != 'Frostbite.Render.MeshMaterial':
                falha('primeiro material do hospedeiro não é MeshMaterial: ' + h)
            ops = []
            mats = self.mats_of(h)
            for k, m in enumerate(mats):
                ops.append(dict(op='clone', source={'index': src}, tag=f'm{k}', exported=True, guid=m['meshmaterial']))
                ops += self.meshmaterial_ops(f'm{k}', m['role'], d['instances'][src]['fields'])
            ops.append(dict(op='list_set', target={'primary': True}, path='Materials', items=[{'int': {'tag': f'm{k}'}} for k in range(len(mats))]))
            f, _ = self.base_raw('ebx', H['mesh'])
            r = self.run([dict(kind='ebx_ops', input=str(f), output=str(self.work / 'out' / f'{h}_mesh.ebx'), expect_name=d['name'],
                               expect_new_name=d['name'], ops=ops)], 'host_mesh_ebx')['rows'][0]
            self.host_ebx[h] = Path(r['output']).read_bytes()

    def build_mvdb(self):
        mvdb = self.mvdb_dump
        ops = []
        k = 0
        for h, H in self.hosts.items():
            items = []
            for m in self.mats_of(h):
                t = self.tmpl[m['role']]
                var = mvdb['instances'][t['variation_index']]['fields']
                ci = [i for i, x in enumerate(var['Shader']['TextureParameters']) if x['ParameterName'] == 'colorTexture'][0]
                tex = self.tex[m['texture']]
                ops.append(dict(op='clone', source={'index': t['variation_index']}, tag=f'v{k}', exported=False))
                ops.append(dict(op='set', target={'tag': f'v{k}'}, path=f'Shader.TextureParameters[{ci}].Value', value={'ext': [tex['partition'], tex['primary']]}))
                mm = t['mvdb_material']
                items.append({'fields': {'Material': {'ext': [H['rec']['partition'], m['meshmaterial']]}, 'MaterialVariation': {'int': {'tag': f'v{k}'}},
                                         'SurfaceShaderGuid': mm['SurfaceShaderGuid'], 'SurfaceShaderId': str(int(mm['SurfaceShaderId']))}})
                k += 1
            ops.append(dict(op='list_set', target={'primary': True}, path=f"Entries[{H['entry']}].Materials", items=items))
        ops.append(dict(op='remove_unreferenced', types=['MeshMaterialVariation']))
        f, _ = self.base_raw('ebx', self.MVDB)
        r = self.run([dict(kind='ebx_ops', input=str(f), output=str(self.work / 'out' / 'mvdb.ebx'), expect_name=mvdb['name'],
                           expect_new_name=mvdb['name'], ops=ops)], 'mvdb')['rows'][0]
        self.mvdb_ebx = Path(r['output']).read_bytes()

    def build_depot(self):
        f, raw = self.base_raw('res', self.MAIN_DEPOT)
        rec = self.p.record('res', self.MAIN_DEPOT)
        entries = []
        for m in self.mats:
            t = self.tmpl[m['role']]
            part, inst = t['colour'].split(':')[2].split('/')
            tex = self.tex[m['texture']]
            entries.append(dict(template_key=str(t['key']), new_key=str(m['key']),
                                remap=[dict(old_instance=inst, new_instance=tex['primary'], old_partition=part, new_partition=tex['partition'])]))
        r = self.run([dict(kind='sbd_extend', input=str(f), meta=rec['resmeta'], output=str(self.work / 'out' / 'main_depot.res'),
                           entries=entries)], 'depot')['rows'][0]
        self.depot = dict(raw=Path(r['output']).read_bytes(), meta=r['meta'],
                          registrations=self.depot_regs + [(m['key'], self.tmpl[m['role']]['native_key']) for m in self.mats])

    # ------------------------------------------------------------ meshes
    def radiosity(self, mesh):
        """Um texel de radiosidade dos charts do Enlighten do próprio mesh (o original do El Grandioso, maior subset), usado
        em todo vértice que o mesh agora tem. Com o pré-cálculo de luz de outro estádio, um texel do atlas dele."""
        if self.luz:
            return list(self.luz['texel'])
        native = self.c['res_by_name'][mesh.replace(self.tok, FAMILIA).lower()]
        p, _ = self.amb.native('res', native['name'])
        native_dump = self.mesh_dump('nativo_' + native['name'], p, native['resmeta'])
        nl = native_dump['lods'][0]
        data, _ = self.amb.chunk_bytes(nl['chunk'])
        cand = [k for k, s in enumerate(nl['subsets']) if any(e['usage'] == 'RadiosityTexCoord' for e in s['decl0']['elements'])]
        if not cand:
            falha('sem RadiosityTexCoord: ' + mesh)
        k = max(cand, key=lambda i: nl['subsets'][i]['vertices'])
        a, idx = malha.decode_subset(nl, nl['subsets'][k], data)
        r = a['RadiosityTexCoord']
        med = np.median(r[:, :2], 0)
        i = int(np.argmin(np.sum((r[:, :2] - med) ** 2, 1)))
        return [float(r[i, 0]), float(r[i, 1]), float(r[i, 2])]

    @staticmethod
    def union_box(boxes):
        b = np.array(boxes, np.float64)
        return [float(x) for x in np.concatenate([b[:, :3].min(0), b[:, 3:].max(0)])]

    def build_host_mesh(self):
        self.host_res = {}
        self.report['meshes'] = {}
        for h, H in self.hosts.items():
            lod = H['mesh_dump']['lods'][0]
            specs = []
            mats = self.mats_of(h)
            for k, m in enumerate(mats):
                t = self.tmpl[m['role']]
                for s in m['pieces']:
                    specs.append(dict(s, material_name=m['name'], material_index=k, key=str(m['key']), part=0, categories=CATEGORIES[m['role']],
                                      template=dict(res=t['res'], meta=t['meta'], subset=t['subset'])))
            if not specs:
                falha(f'o hospedeiro {h} ficou sem material (estádio pequeno demais para seis hospedeiros?)')
            bbox = self.union_box([s['bbox'] for s in specs])
            H['bbox'] = bbox
            res_path, _ = self.base_raw('res', H['mesh'])
            out = self.work / 'out' / f'{h}_mesh'
            r = self.run([dict(kind='mesh_build', input=str(res_path), meta=self.p.record('res', H['mesh'])['resmeta'], lod_chunk=lod['chunk'],
                               geometry=str(self.prep / 'geometry.bin'), radiosity=self.radiosity(H['mesh']), subsets=specs, bbox=bbox,
                               part_boxes={'0': bbox}, output_res=str(out) + '.res', output_chunk=str(out) + '.chunk')], 'host_mesh')['rows'][0]
            if r['index_unit'] != 2 or r['vertex_size'] + r['index_size'] > HOST_BUDGET or len(r['subsets']) > HOST_MAX_SUBSETS:
                falha(f"hospedeiro {h} fora dos limites: {r['index_unit']} {r['vertex_size']} {r['index_size']} {len(r['subsets'])}")
            self.host_res[h] = dict(raw=Path(r['output_res']).read_bytes(), meta=r['meta'], chunk=Path(r['output_chunk']).read_bytes(),
                                    chunk_id=lod['chunk'])
            self.report['meshes'][h] = dict(materiais=len(mats), subsets=len(r['subsets']), mb=round((r['vertex_size'] + r['index_size']) / 2**20, 2))

    # ------------------------------------------------------------ edições de outros registros
    def ebx_edit_mais(self, name, ops, tag):
        """Como ebx_edit, mas sobre a versão já editada nesta conversão (quando houver)."""
        if name not in self.edits:
            return self.ebx_edit(name, ops, tag)
        d = self.ebx_dump(name)
        f = self.work / 'out' / ('base__' + sha256(name.lower().encode())[:20] + f'_{len(self.edits)}.ebx')
        f.write_bytes(self.edits[name])
        o = self.work / 'out' / ('edit__' + sha256(name.lower().encode())[:20] + f'_{len(self.edits)}b.ebx')
        r = self.run([dict(kind='ebx_ops', input=str(f), output=str(o), expect_name=d['name'], expect_new_name=d['name'], ops=ops)], tag)['rows'][0]
        self.edits[name] = Path(r['output']).read_bytes()
        return r

    def ebx_edit(self, name, ops, tag):
        f, _ = self.base_raw('ebx', name)
        d = self.ebx_dump(name)
        o = self.work / 'out' / ('edit__' + sha256(name.lower().encode())[:20] + f'_{len(self.edits)}.ebx')
        r = self.run([dict(kind='ebx_ops', input=str(f), output=str(o), expect_name=d['name'], expect_new_name=d['name'], ops=ops)], tag)['rows'][0]
        self.edits[name] = Path(r['output']).read_bytes()
        return r

    def triangulos16(self):
        """Triângulos (t, 3, 3) de toda a geometria preparada do FIFA 16 (lidos uma vez)."""
        if self._tri16 is None:
            from .personagens import ler_geometria
            self._tri16 = ler_geometria(self.prep)
        return self._tri16

    def geometry_of(self, subset_name):
        s = next(x for x in self.subsets['subsets'] if x['name'] == subset_name)
        blob = (self.prep / 'geometry.bin').read_bytes()
        n = s['vertices']
        pos = np.frombuffer(blob, '<f4', n * 3, s['offset']).reshape(n, 3).astype(np.float64)
        return s, pos

    @staticmethod
    def box_value(b):
        return {'fields': {'min': {'vec3': list(b[:3])}, 'max': {'vec3': list(b[3:])}}}

    def stage_hide(self):
        """Arquitetura do El Grandioso fora sem esvaziar subset: o teto fica só com o teto (um hospedeiro), os banners saem
        (e voltam nas faixas do FIFA 16, quando a receita tem peças com o papel "banner"), membros de grupos estáticos ficam
        invisíveis e os meshes que a lógica liga e desliga vão 100 m para baixo do piso."""
        S, G = self.S, self.G
        refs = ['ObjectReferenceObjectData', 'SpatialPrefabReferenceObjectData', 'ReferenceObjectData']
        done = {}
        for wp in ('roof', 'banners'):
            name = S + wp
            d = self.ebx_dump(name)
            f = d['instances'][0]['fields']
            if any(f.get(k) for k in ('EventConnections', 'PropertyConnections', 'LinkConnections')):
                falha(f'{wp} tem conexões; esvaziar quebraria a lógica')
            objs = [int(x.split(':')[2]) for x in f['Objects']]
            keep = [k for k, i in enumerate(objs) if self.part_name(d['instances'][i]['fields'].get('Blueprint')).lower() == (G + wp).lower()]
            if (wp == 'roof') != (len(keep) == 1):
                falha(f'{wp}: objeto do blueprint hospedeiro {keep}')
            if any(d['instances'][i]['exported'] for k, i in enumerate(objs) if k not in keep):
                falha(f'{wp}: objeto exportado seria removido')
            novos, tags = self.banners_novos(d, objs) if wp == 'banners' else ([], [])
            ops = novos + [dict(op='list_keep', target={'primary': True}, path='Objects', indices=keep)]
            if tags:
                ops.append(dict(op='list_append', target={'primary': True}, path='Objects', items=[{'int': {'tag': t}} for t in tags]))
            ops.append(dict(op='remove_unreferenced', types=refs))
            self.ebx_edit(name, ops, 'hide')
            done[wp] = dict(objetos=len(objs), ficaram=len(keep), **({'banners_novos': len(tags)} if tags else {}))
        for h, H in self.hosts.items():
            if h == 'roof':
                continue
            d = self.ebx_dump(H['world'])
            objs = [int(x.split(':')[2]) for x in d['instances'][0]['fields']['Objects']]
            if not any(self.part_name(d['instances'][i]['fields'].get('Blueprint')).lower() == H['blueprint'].lower() for i in objs):
                falha(f'world part {h} não coloca o blueprint hospedeiro')
        for world, words in ((S + self.tok, ('exterior_cityskirt_mesh', 'building_apartment', 'light_south_american_stadium_pole')),
                             (S + 'exterior', ('exterior_facade_mesh',))):
            d = self.ebx_dump(world)
            sg = next(i for i, x in enumerate(d['instances']) if x['type'].endswith('StaticModelGroupEntityData'))
            ops, hid = [], []
            for k, m in enumerate(d['instances'][sg]['fields']['MemberDatas']):
                nm = self.part_name(m['MeshAsset'])
                if any(w in nm for w in words):
                    ops.append(dict(op='list_set', target={'index': sg}, path=f'MemberDatas[{k}].Visible', items=[False] * int(m['InstanceCount'])))
                    hid.append(f"{nm.split('/')[-1]} x{int(m['InstanceCount'])}")
            if len(hid) != (4 if 'exterior' not in world.split('/')[-1] else 1):
                falha(f'membros esperados não encontrados em {world}: {hid}')
            self.ebx_edit(world, ops, 'hide_group')
            done[world.split('/')[-1] + ' (grupo estático)'] = hid
        if self.rc.get('placas_madeira_bancos', 'manter') == 'abaixo_do_piso':
            # Placas baixas de madeira do El Grandioso do lado dos bancos (z -40.8): ligadas ao leitor de placas, ficam e
            # vão 10 m para baixo do piso (no Morumbi, três cruzavam os bancos rebaixados).
            name = S + 'adboards'
            d = self.ebx_dump(name)
            ops, low = [], []
            for i in [int(x.split(':')[2]) for x in d['instances'][0]['fields']['Objects']]:
                f = d['instances'][i]['fields']
                if 'adboard_static_wood_thin' in self.part_name(f.get('Blueprint')) and f['BlueprintTransform']['trans']['z'] < -38:
                    t = f['BlueprintTransform']['trans']
                    ops.append(dict(op='set', target={'index': i}, path='BlueprintTransform.trans', value={'vec3': [t['x'], -10.0, t['z']]}))
                    low.append(round(t['x'], 2))
            if len(low) != 8:
                falha(f'placas de madeira esperadas: 8, achadas {low}')
            self.ebx_edit(name, ops, 'adboards')
            done['placas de madeira do lado dos bancos (abaixo do piso)'] = low
        for world, bp in ((S + 'tournament_main', G + 'tournament_main'), (S + 'tifo_player_main', G + 'tifo_net'),
                          (S + 'skinny_flags_main', G + 'regionalization/skinny_flags'),
                          (S + 'lighting_crowd_shadow', G + f'shadow_seat_{self.tok}')):
            d = self.ebx_dump(world)
            hits = [i for i, x in enumerate(d['instances']) if self.part_name(x['fields'].get('Blueprint')).lower() == bp.lower()]
            if not hits:
                falha(f'{bp} não é colocado em {world}')
            ops = []
            for i in hits:
                t = d['instances'][i]['fields']['BlueprintTransform']['trans']
                ops.append(dict(op='set', target={'index': i}, path='BlueprintTransform.trans', value={'vec3': [t['x'], t['y'] - 100.0, t['z']]}))
            self.ebx_edit(world, ops, 'sink')
            done[bp.split('/')[-1] + ' (100 m abaixo do piso)'] = len(hits)
        self.report['escondidos'] = done

    def banners_novos(self, d, objs):
        """Clones dos banners do El Grandioso (world part banners: dump d, objetos objs) nas faixas do FIFA 16 (peças com o
        papel "banner", motor/fifa16/banners.py): (ops, tags dos clones). Sem faixas, nenhum."""
        from . import banners as bn
        arq = self.prep / 'banners.json'
        pecas = json.loads(arq.read_text(encoding='utf8'))['pecas'] if arq.is_file() else []
        if not pecas:
            self.report['banners'] = 'nenhuma peça com o papel "banner": o estádio fica sem os banners dos times'
            return [], []
        tri = np.concatenate([np.array(p['triangulos'], np.float64).reshape(-1, 3, 3) for p in pecas])
        sups = bn.superficies(tri)
        col, fora = bn.colocacoes(sups)
        # um objeto do El Grandioso por blueprint, por formato (as variantes se alternam)
        modelos = collections.defaultdict(dict)
        for i in objs:
            bp = self.part_name(d['instances'][i]['fields'].get('Blueprint'))
            fm = bn.formato_do_blueprint(bp)
            if fm and bp not in modelos[fm]:
                modelos[fm][bp] = i
        ops, tags, usados = [], [], collections.Counter()
        for k, c in enumerate(col):
            fonte = [modelos[c['formato']][bp] for bp in sorted(modelos[c['formato']])]
            if not fonte:
                falha(f"o El Grandioso não tem banner {c['formato']}")
            tag = f'b{k}'
            ops.append(dict(op='clone', source={'index': fonte[usados[c['formato']] % len(fonte)]}, tag=tag, exported=False))
            usados[c['formato']] += 1
            for eixo in ('right', 'up', 'forward', 'trans'):
                ops.append(dict(op='set', target={'tag': tag}, path=f'BlueprintTransform.{eixo}', value={'vec3': [float(x) for x in c[eixo]]}))
            tags.append(tag)
        self.report['banners'] = dict(pecas=[p['prim'] for p in pecas], superficies=len(sups), banners=len(col), fora_do_limite=fora,
                                      formatos=dict(usados))
        base.aviso(f"banners dos times: {len(col)} nas faixas do FIFA 16 (peças {', '.join(str(p['prim']) for p in pecas)})"
                   + (f'; {fora} superfícies menores ficaram de fora (limite de {bn.MAXIMO})' if fora else ''))
        return ops, tags

    def stage_host_blueprint(self):
        for h, H in self.hosts.items():
            d = self.ebx_dump(H['blueprint'])
            sm = [k for k, x in enumerate(d['instances']) if x['type'].endswith('StaticModelEntityData')]
            if len(sm) != 1:
                falha(f'blueprint {h}: {len(sm)} StaticModelEntityData')
            self.ebx_edit(H['blueprint'], [dict(op='set', target={'index': sm[0]}, path='PartBoundingBoxes[0]', value=self.box_value(H['bbox']))], 'host_bp')

    def stage_scoreclock(self):
        """Telão: subset 0 = as telas do FIFA 16 (uma parte por lado); subset 1 (a moldura do El Grandioso) fica com um
        triângulo de área zero no meio da tela 0. Sem telão no FIFA 16, as duas viram triângulos de área zero."""
        md = self.score_mesh
        lod = md['lods'][0]
        jname = f"{self.rc.get('prefixo', 'fifa16')}_jumbotron"
        tem = any(s['name'] == jname for s in self.subsets['subsets'])
        res_path, _ = self.base_raw('res', self.SCORE_MESH)
        meta = self.p.record('res', self.SCORE_MESH)['resmeta']
        s0, s1 = lod['subsets'][0], lod['subsets'][1]
        cats = [sorted(c for c in range(5) if i in lod['categories'][c]) for i in (0, 1)]
        if tem:
            j, pos = self.geometry_of(jname)
            part = np.array(j['part_of_vertex'])
            boxes = {}
            for k in (0, 1):
                q = pos[part == k] if (part == k).any() else pos
                boxes[k] = [float(x) for x in np.concatenate([q.min(0), q.max(0)])]
            centre = [float(x) for x in (np.array(boxes[0][:3]) + np.array(boxes[0][3:])) / 2]
            specs = [dict(j, material_name=s0['material'], material_index=s0['material_index'], key=s0['key'], categories=cats[0],
                          template=dict(res=str(res_path), meta=meta, subset=0)),
                     dict(name='frame', degenerate=centre, vertices=3, triangles=1, part=0, bbox=centre + centre, material_name=s1['material'],
                          material_index=s1['material_index'], key=s1['key'], categories=cats[1], template=dict(res=str(res_path), meta=meta, subset=1))]
            bbox = j['bbox']
        else:
            centre = [0.0, -100.0, 0.0]
            boxes = {0: centre + centre, 1: centre + centre}
            specs = [dict(name='screen', degenerate=centre, vertices=3, triangles=1, part=0, bbox=centre + centre, material_name=s0['material'],
                          material_index=s0['material_index'], key=s0['key'], categories=cats[0], template=dict(res=str(res_path), meta=meta, subset=0)),
                     dict(name='frame', degenerate=centre, vertices=3, triangles=1, part=0, bbox=centre + centre, material_name=s1['material'],
                          material_index=s1['material_index'], key=s1['key'], categories=cats[1], template=dict(res=str(res_path), meta=meta, subset=1))]
            bbox = centre + centre
        out = self.work / 'out' / 'scoreclock'
        r = self.run([dict(kind='mesh_build', input=str(res_path), meta=meta, lod_chunk=lod['chunk'], geometry=str(self.prep / 'geometry.bin'),
                           radiosity=self.radiosity(self.SCORE_MESH), subsets=specs, bbox=bbox, part_boxes={'0': boxes[0], '1': boxes[1]},
                           output_res=str(out) + '.res', output_chunk=str(out) + '.chunk')], 'scoreclock')['rows'][0]
        if any(s['vertices'] == 0 or s['triangles'] == 0 for s in r['subsets']):
            falha('telão com subset vazio')
        self.res_edits[self.SCORE_MESH] = (Path(r['output_res']).read_bytes(), r['meta'])
        self.chunk_edits[lod['chunk']] = Path(r['output_chunk']).read_bytes()
        name = self.G + 'scoreclock'
        d = self.ebx_dump(name)
        i = next(k for k, x in enumerate(d['instances']) if x['type'].endswith('StaticModelEntityData'))
        self.ebx_edit(name, [dict(op='set', target={'index': i}, path='PartBoundingBoxes[0]', value=self.box_value(boxes[0])),
                             dict(op='set', target={'index': i}, path='PartBoundingBoxes[1]', value=self.box_value(boxes[1]))], 'score_bp')
        self.report['telao'] = dict(telas=boxes if tem else 'nenhuma no FIFA 16 (telão do El Grandioso escondido)')

    def anel_da_pista(self):
        """Raio interno, por ângulo, do piso do FIFA 16 em volta do campo (as peças da 'pista' na receita)."""
        pista = {int(x) for x in self.rc.get('pista') or []}
        nomes = [s['name'] for s in self.subsets['subsets'] if set(s['prims']) & pista]
        if not nomes:
            return None, []
        tp = np.concatenate([self.geometry_of(n)[1] for n in nomes])
        ang = np.arctan2(tp[:, 2], tp[:, 0])
        rad = np.hypot(tp[:, 0], tp[:, 2])
        bins = 720
        b = ((ang + np.pi) / (2 * np.pi) * bins).astype(int) % bins
        rin = np.full(bins, np.inf)
        np.minimum.at(rin, b, rad)
        good = np.isfinite(rin)
        xs = np.nonzero(good)[0]
        rin = np.interp(np.arange(bins), xs, rin[good], period=bins)
        rin = np.minimum.reduce([np.roll(rin, s) for s in (-2, -1, 0, 1, 2)])  # nunca passa do meio-fio entre dois bins
        return rin, nomes

    def stage_pitch(self):
        """Gramado do FC 27 até o piso do FIFA 16 em volta do campo (e antes dos bancos, se a receita pedir); plano fora do
        campo. A pista de atletismo do El Grandioso (o subset de borracha do gramado) vira um ponto abaixo do campo, a não
        ser que a receita peça para mantê-la (pista_el_grandioso: "manter", como no Morumbi v3)."""
        mesh = self.G + 'pitch_mesh'
        md = self.mesh_dump(mesh)
        lod = md['lods'][0]
        f, _ = self.base_raw('res', mesh)
        meta = self.p.record('res', mesh)['resmeta']
        rin, track = self.anel_da_pista()
        corte = self.rc.get('recorte_bancos')
        modo_pista = self.rc.get('pista_el_grandioso') or 'esconder'
        if modo_pista not in ('esconder', 'manter'):
            falha('pista_el_grandioso desconhecido: ' + str(modo_pista))
        pista_eg = [k for k, s in enumerate(lod['subsets']) if 'rubber' in s['material'].lower()] if modo_pista == 'esconder' else []
        if modo_pista == 'esconder' and len(pista_eg) != 1:
            falha(f"pista de atletismo do El Grandioso no gramado: {[s['material'] for s in lod['subsets']]}")
        if rin is None and not corte and not self.luz and not pista_eg:
            self.report['gramado'] = 'sem recorte (a receita não tem piso em volta do campo)'
            return
        inl = self.work / 'out' / 'pitch_inline.bin'
        self.run([dict(kind='mesh_edit', input=str(f), meta=meta, export_inline=str(inl))], 'pitch_inline')
        data = bytearray(inl.read_bytes())
        bins = 720
        moved = 0
        for k, s in enumerate(lod['subsets']):
            a, idx = malha.decode_subset(lod, s, bytes(data))
            Pt = a['Pos'].astype(np.float64)
            d0 = s['decl0']
            pe = next(e for e in d0['elements'] if e['usage'] == 'Pos')
            if pe['format'] != 'Float3' or pe['stream'] != 0:
                falha('posição do gramado não é Float3 no fluxo 0')
            stride = d0['streams'][0]['stride']
            Q = Pt.copy()
            if k in pista_eg:
                Q[:] = [0.0, -1.0, 0.0]  # todos os vértices no mesmo ponto: os triângulos ficam sem área
            elif corte:
                bench = (np.abs(Q[:, 0]) < float(corte['x'])) & (Q[:, 2] < float(corte['z']))
                Q[bench, 2] = float(corte['z'])
            if rin is not None:
                a2 = np.arctan2(Q[:, 2], Q[:, 0])
                r2 = np.hypot(Q[:, 0], Q[:, 2])
                lim = rin[((a2 + np.pi) / (2 * np.pi) * bins).astype(int) % bins] - 0.05
                out = r2 > lim
                Q[out, 0] *= lim[out] / r2[out]
                Q[out, 2] *= lim[out] / r2[out]
            outside_field = (np.abs(Q[:, 0]) > 53.5) | (np.abs(Q[:, 2]) > 35.0)
            Q[outside_field, 1] = np.minimum(Q[outside_field, 1], 0.0)
            ch = np.any(np.abs(Q - Pt) > 1e-6, 1)
            moved += int(ch.sum())
            for v in np.nonzero(ch)[0]:
                struct.pack_into('<3f', data, s['vertex_offset'] + int(v) * stride, *Q[v])
        if self.luz:
            from . import luz
            luz.radiosidade_gramado(self, data, lod)
        o = self.work / 'out' / 'pitch_inline_new.bin'
        o.write_bytes(bytes(data))
        r = self.run([dict(kind='mesh_edit', input=str(f), meta=meta, inline_data=str(o), output_res=str(self.work / 'out' / 'pitch.res'))], 'pitch')['rows'][0]
        self.res_edits[mesh] = (Path(r['output_res']).read_bytes(), r['meta'])
        self.report['gramado'] = dict(vertices_movidos=moved, piso=track, raio_interno=[float(rin.min()), float(rin.max())] if rin is not None else None,
                                      pista_do_el_grandioso='escondida' if pista_eg else 'mantida')

    def stage_crowd(self):
        src = self.sa / 'crowdplacement' / f'crowd_{self.rc["fifa16_id"]}_1.dat'
        if not src.is_file():
            self.report['torcida'] = 'sem crowd_<id>_1.dat: a torcida do El Grandioso fica'
            return
        b = src.read_bytes()
        if b[:4] != b'CRWD':
            falha(f'{src.name} não é CRWD')
        n = struct.unpack_from('<I', b, 6)[0]
        rec = np.frombuffer(b[10:10 + n * 32], np.uint8).reshape(n, 32)
        f = rec[:, :16].copy().view('<f4').reshape(n, 4).astype(np.float64)
        Pp, orient = f[:, :3] / 100.0, f[:, 3]
        b19, b20, b22 = rec[:, 19], rec[:, 20], rec[:, 22]
        buffer = b22 == 0                                   # nunca preenchida no FIFA 16 (faixa de segurança)
        away = (b19 == 0xFF) & (b20 == 0xFF)                # bloco da torcida visitante
        organised = (b19 == 0) & (b20 == 0) & (b22 == 0xFF)  # organizada da casa
        keep = ~buffer
        Pp, orient, away, organised, b22 = Pp[keep], orient[keep], away[keep], organised[keep], b22[keep]
        self.lugares = Pp
        rgb = rec[keep][:, 16:19].astype(np.uint32)
        cfg = self.rc.get('torcida') or {}
        seat_colour = 0xFF000000 | (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
        if cfg.get('cadeiras') and cfg['cadeiras'] != 'fifa16':
            c = int(str(cfg['cadeiras']).lstrip('#'), 16) & 0xFFFFFF
            seat_colour = np.full(len(Pp), 0xFF000000 | c, np.uint32)
        # Mapas casa/visitante do FC 27: 0 = casa, 1 = visitante (no El Grandioso, banco e torcida da casa em -X).
        sx = -1.0 if cfg.get('lado_casa', '-x') == '+x' else 1.0
        X = Pp[:, 0] * sx
        xmax = np.abs(X).max()
        neutral = np.where(away, 0.7215, 0.5 + 0.2215 * X / xmax)
        ultra = np.where(away, 1.0, np.where(organised, 0.0, 0.50196))
        fifty = np.where(away | (X >= 0), 0.85098, 0.14902)
        r = np.hypot(Pp[:, 0], Pp[:, 2])
        close = 1 - (r - r.min()) / (r.max() - r.min())
        low = 1 - (Pp[:, 1] - Pp[:, 1].min()) / (Pp[:, 1].max() - Pp[:, 1].min())
        prio = b22 / 255.0
        attendance = 0.5333 + (0.9804 - 0.5333) * np.clip(0.5 * prio + 0.3 * close + 0.2 * low, 0, 1)
        tier = np.where(Pp[:, 1] < float(cfg.get('tier2_acima_de', 14.0)), 1, 2).astype(np.uint8)
        m = len(Pp)
        out = bytearray(m * 44)
        for i in range(m):
            struct.pack_into('<4fIIB3x4f', out, i * 44, Pp[i, 0], Pp[i, 1], Pp[i, 2], orient[i], 0xFF000000, int(seat_colour[i]), int(tier[i]),
                             neutral[i], ultra[i], fifty[i], attendance[i])
        path = self.work / 'out' / 'crowd_seats.bin'
        path.write_bytes(bytes(out))
        self.ebx_edit(self.G + f'{self.tok}_crowd_0', [dict(op='crowd', data=str(path), sha256=sha256(bytes(out)))], 'crowd')
        self.report['torcida'] = dict(lugares_fifa16=int(n), lugares=int(m), faixa_tirada=int(buffer.sum()), visitantes=int(away.sum()),
                                      organizada=int(organised.sum()), anel_inferior=int((tier == 1).sum()))

    def stage_luzes(self):
        """Luzes da torcida (spots de lighting_stands_main e das torres em lighting_flood_main) acompanhando a torcida do
        FIFA 16 (motor/fifa16/iluminacao.py). Receita "luzes_torcida": "acompanhar" (padrão) ou "manter" (Morumbi v3)."""
        modo = self.rc.get('luzes_torcida') or 'acompanhar'
        if modo not in ('acompanhar', 'manter'):
            falha('luzes_torcida desconhecido: ' + str(modo))
        if modo == 'manter':
            self.report['luzes_da_torcida'] = 'nas posições do El Grandioso (receita)'
            return
        if self.lugares is None:
            self.report['luzes_da_torcida'] = 'a torcida do El Grandioso ficou: as luzes dela também'
            return
        from . import iluminacao, luz
        antigos = luz.assentos_fc27(self.amb, [BASE_ID], self.work)[BASE_ID]
        if not len(antigos):
            falha('torcida do El Grandioso não encontrada no jogo')
        luzes, onde = [], []
        for wp in ('lighting_stands_main', 'lighting_flood_main'):
            name = self.S + wp
            d = self.ebx_dump(name)
            for i, x in enumerate(d['instances']):
                f = x['fields']
                tr = f.get('Transform')
                if not x['type'].endswith('LightEntityData') or not isinstance(tr, dict) or f.get('Intensity') is None or not f.get('AttenuationRadius'):
                    continue
                fw = np.array([tr['forward'][a] for a in 'xyz'], np.float64)
                luzes.append(dict(pos=np.array([tr['trans'][a] for a in 'xyz'], np.float64), dir=-fw / np.linalg.norm(fw),
                                  intensidade=float(f['Intensity']), raio=float(f['AttenuationRadius']),
                                  angulo=float(f['OuterAngle']) if x['type'].endswith('SpotLightEntityData') else None))
                onde.append((name, i))
        if not luzes:
            falha('luzes da torcida do El Grandioso não encontradas')
        novas, rel = iluminacao.acompanhar(luzes, antigos, self.lugares)
        ops = collections.defaultdict(list)
        for (name, i), a, b in zip(onde, luzes, novas):
            if np.array_equal(a['pos'], b['pos']):
                continue
            ops[name].append(dict(op='set', target={'index': i}, path='Transform.trans', value={'vec3': [float(c) for c in b['pos']]}))
            ops[name].append(dict(op='set', target={'index': i}, path='Intensity', value=float(b['intensidade'])))
        for name, o in ops.items():
            self.ebx_edit(name, o, 'luzes')
        self.report['luzes_da_torcida'] = rel
        lt = rel['luz_na_torcida_vs_el_grandioso']
        base.aviso(f"luzes da torcida: {rel['acompanharam']} de {rel['luzes']} acompanharam a torcida nova (mediana da luz na torcida: "
                   f"{lt['antes'][1]}x a do El Grandioso antes, {lt['depois'][1]}x depois)")

    def stage_glares(self):
        """Brilhos nas lâmpadas do FIFA 16 (arquivo de dia para 1_x, de noite para 3_x), fachos das lâmpadas da noite;
        os conjuntos secundários do El Grandioso (luzes da borda do teto dele) ficam vazios."""
        fx = self.sa / 'fx'
        sid = self.rc['fifa16_id']
        variantes = ('1_0', '1_1', '1_2', '3_0', '3_1', '3_2')
        lamps = {}
        for v in variantes:
            f = fx / f'glares_{sid}_{v}.lnx'
            lamps[v] = analise.lampadas(f) if f.is_file() else np.zeros((0, 3))
        if not len(lamps['3_0']) or any(not len(x) for x in lamps.values()):
            self.report['glares'] = 'sem lâmpadas nos .lnx do FIFA 16: os glares do El Grandioso ficam'
            return
        refs = ['SpatialPrefabReferenceObjectData', 'EffectReferenceObjectData']
        report = {}
        gdir = f'content/effects/glares/{self.tok}/'
        for v in variantes:
            lv = lamps[v]
            base_ = gdir + f'layers/{v}/'
            name = base_ + f'flare_primary_{v}'
            d = self.ebx_dump(name)
            objs = [int(x.split(':')[2]) for x in d['instances'][0]['fields']['Objects']]
            n = min(len(objs), len(lv))
            ops = [dict(op='set', target={'index': objs[k]}, path='BlueprintTransform.trans', value={'vec3': [float(c) for c in lv[k]]}) for k in range(n)]
            for k in range(len(objs), len(lv)):
                ops.append(dict(op='clone', source={'index': objs[0]}, tag=f'f{k}', exported=False))
                ops.append(dict(op='set', target={'tag': f'f{k}'}, path='BlueprintTransform.trans', value={'vec3': [float(c) for c in lv[k]]}))
            ops.append(dict(op='list_keep', target={'primary': True}, path='Objects', indices=list(range(n))))
            if len(lv) > len(objs):
                ops.append(dict(op='list_append', target={'primary': True}, path='Objects',
                                items=[{'int': {'tag': f'f{k}'}} for k in range(len(objs), len(lv))]))
            ops.append(dict(op='remove_unreferenced', types=refs))
            self.ebx_edit(name, ops, 'glare')
            for kind in ('flare_secondary', 'atmos_secondary'):
                nm = base_ + f'{kind}_{v}'
                d2 = self.ebx_dump(nm)
                if any(i['exported'] for i in d2['instances'][1:]):
                    falha(nm + ' tem instâncias exportadas')
                self.ebx_edit(nm, [dict(op='list_set', target={'primary': True}, path='Objects', items=[]),
                                   dict(op='remove_unreferenced', types=refs)], 'glare2')
            report[v] = dict(lampadas=len(lv), brilhos_antes=len(objs))
        lv = lamps['3_0']
        aim = np.c_[lv[:, 0] * 0.4, np.zeros(len(lv)), lv[:, 2] * 0.4]
        dirs = lv - aim
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
        w = len(lv)
        img = np.zeros((4, w, 4), np.float32)
        img[0, :, :3], img[0, :, 3] = lv, 1
        img[1, :, :3], img[1, :, 3] = dirs, 1
        img[2:, :, 3] = 1
        data = img.tobytes()
        tex = gdir + 'positions/fximg_vbeam_trans_primary_gsa'
        resf, _ = self.base_raw('res', tex)
        dp = self.work / 'out' / 'beams.bin'
        dp.write_bytes(data)
        beam_chunk = str(uuid.UUID(bytes_le=resf.read_bytes()[40:56]))
        hdr = self.run([dict(kind='texture_build', input='beams', template=str(resf), data=str(dp), sha256=sha256(data), format='RAW',
                             bits_per_pixel=128, width=w, height=4, mips=1, mip_sizes=[len(data)], name=tex, chunk=beam_chunk,
                             output_res=str(self.work / 'out' / 'beams.res'), output_chunk=str(self.work / 'out' / 'beams.chunk'))], 'beams')['rows'][0]
        self.res_edits[tex] = (Path(hdr['output_res']).read_bytes(), self.p.record('res', tex)['resmeta'])
        self.chunk_edits[beam_chunk] = data
        self.ebx_edit(tex, [dict(op='set', target={'primary': True}, path='AuthoredWidth', value=w),
                            dict(op='set', target={'primary': True}, path='CropInfo', value={'fields': {'X': 0, 'Y': 0, 'Z': w, 'W': 4}})], 'beam_ebx')
        for v in variantes:
            nm = gdir + f'flares/flare_{v}/fx_vbeam_imgstore_primary_gsa_{v}'
            d = self.ebx_dump(nm)
            i = next(k for k, x in enumerate(d['instances']) if x['type'].endswith('EmitterGraphEntityData'))
            self.ebx_edit(nm, [dict(op='set', target={'index': i}, path=f'EmitterGraphOverrides.ParticleMaxCount.{q}', value=w + 8)
                               for q in ('Low', 'Medium', 'High', 'Ultra')], 'beam_fx')
        report['fachos'] = w
        self.report['glares'] = report

    # camadas de personagens laterais do El Grandioso: as que os marcadores slc do FIFA 16 posicionam, e as outras que o
    # ajuste automático também confere (câmeras, seguranças e os personagens da cerimônia de entrada)
    SLC_FIFA16 = ('slc_assistantmanageraway', 'slc_assistantmanagerhome', 'slc_ballboy', 'slc_generic', 'slc_manageraway',
                  'slc_managerhome', 'slc_medicalofficer', 'slc_photographer', 'slc_police', 'slc_tournamentofficial')
    SLC_OUTRAS = ('slc_camera_handheld', 'slc_camera_sitting', 'slc_camera_standing', 'slc_steward', 'choreo_slc_ballboy',
                  'choreo_slc_photographer', 'choreo_slc_police', 'choreo_slc_shouldercam', 'choreo_slc_steadycam', 'choreo_slc_steward')
    SLC_TECNICOS = ('slc_assistantmanageraway', 'slc_assistantmanagerhome', 'slc_manageraway', 'slc_managerhome')

    @staticmethod
    def slc_facing(p):
        t = np.array([np.clip(p[0], -52.5, 52.5), 0.0, np.clip(p[2], -34.0, 34.0)])
        d = t - np.array([p[0], 0.0, p[2]])
        if np.linalg.norm(d) < 0.5:
            d = -np.array([p[0], 0.0, p[2]])
        d /= np.linalg.norm(d)
        right = np.cross([0.0, 1.0, 0.0], d)
        return right, d

    def stage_slc(self):
        """Personagens laterais. Modos (receita "personagens"):
        - "ajustar" (padrão): os marcadores slc do FIFA 16 onde existirem; os personagens que ficam nas posições do El
          Grandioso são conferidos contra a geometria do estádio novo (motor/fifa16/personagens.py) e, se estiverem dentro
          dela, vão para o lugar livre mais próximo do lado do campo, ou saem de vista;
        - "esconder": técnicos e auxiliares ficam (ajustados); os outros saem de vista;
        - "fifa16": só os marcadores do FIFA 16; o resto fica nas posições do El Grandioso (a v3 do Morumbi).
        Sair de vista = 100 m abaixo do piso: só a posição muda (os marcadores são exportados; nenhum sai da camada)."""
        locs = json.loads((self.prep / 'locators.json').read_text(encoding='utf8'))
        groups = collections.defaultdict(list)
        for l in locs:
            nm = l['name']
            if nm.startswith('slc_'):
                groups[nm.rsplit('_', 1)[0]].append(l['position'])
        modo = self.rc.get('personagens') or 'ajustar'
        if modo not in ('ajustar', 'esconder', 'fifa16'):
            falha('modo de personagens desconhecido: ' + str(modo))
        if modo != 'fifa16':
            return self.slc_ajustado(groups, modo)
        if not groups:
            self.slc_bancos(groups, dict(laterais='sem marcadores slc no FIFA 16: ficam nas posições do El Grandioso'))
            return
        report = {}
        for layer in self.SLC_FIFA16:
            pts = groups.get(layer, [])
            name = self.S + layer
            d = self.ebx_dump(name)
            objs = [int(x.split(':')[2]) for x in d['instances'][0]['fields']['Objects']]
            ops = []
            for k in range(min(len(objs), len(pts))):
                p = pts[k]
                right, fwd = self.slc_facing(p)
                for axis, vec in (('right', right), ('up', [0.0, 1.0, 0.0]), ('forward', fwd), ('trans', p)):
                    ops.append(dict(op='set', target={'index': objs[k]}, path=f'BlueprintTransform.{axis}', value={'vec3': [float(c) for c in vec]}))
            if ops:
                self.ebx_edit(name, ops, 'slc')
            report[layer] = dict(fc27=len(objs), fifa16=len(pts), movidos=min(len(objs), len(pts)))
        self.slc_bancos(groups, report)

    def placas_el_grandioso(self):
        """(x, z) das placas do El Grandioso, que continuam no estádio novo (estáticas e de vídeo)."""
        out = []
        for name in (self.S + 'adboards', self.G + 'adboards_video'):
            if self.p.record('ebx', name) is None:
                continue
            for i in self.ebx_dump(name)['instances'][1:]:
                bt = i['fields'].get('BlueprintTransform')
                if i['type'].endswith('ReferenceObjectData') and bt and isinstance(bt.get('trans'), dict):
                    t = bt['trans']
                    if abs(t['y']) < 1 and (abs(t['x']) > 50 or abs(t['z']) > 36):
                        out.append((t['x'], t['z']))
        return out

    def slc_ajustado(self, groups, modo):
        from . import personagens as pe
        grade = pe.Grade()
        grade.triangulos(self.triangulos16())
        placas = self.placas_el_grandioso()
        for a, b in pe.segmentos_de_placas(placas):
            grade.segmento(a, b)
        aj = pe.Ajuste(grade)
        report = dict(modo=modo, placas_do_el_grandioso=len(placas))
        totais = collections.Counter()
        for layer in self.SLC_FIFA16 + self.SLC_OUTRAS:
            name = self.S + layer
            if self.p.record('ebx', name) is None:
                continue
            d = self.ebx_dump(name)
            objs = [int(x.split(':')[2]) for x in d['instances'][0]['fields']['Objects']]
            pts = groups.get(layer, []) if layer in self.SLC_FIFA16 else []
            ops = []
            conta = collections.Counter()
            for k, i in enumerate(objs):
                if k < len(pts):
                    p = pts[k]
                    right, fwd = self.slc_facing(p)
                    for axis, vec in (('right', right), ('up', [0.0, 1.0, 0.0]), ('forward', fwd), ('trans', p)):
                        ops.append(dict(op='set', target={'index': i}, path=f'BlueprintTransform.{axis}', value={'vec3': [float(c) for c in vec]}))
                    conta['fifa16'] += 1
                    continue
                t = d['instances'][i]['fields']['BlueprintTransform']['trans']
                p = [t['x'], t['y'], t['z']]
                if modo == 'esconder' and layer not in self.SLC_TECNICOS:
                    estado, novo = 'escondidos', [p[0], p[1] - 100.0, p[2]]
                else:
                    estado, novo = aj.ajustar(p)
                    if estado == 'sem_lugar':
                        estado, novo = 'escondidos', [p[0], p[1] - 100.0, p[2]]
                    elif estado == 'fica':
                        estado = 'no_lugar'
                conta[estado] += 1
                if novo is not p:
                    ops.append(dict(op='set', target={'index': i}, path='BlueprintTransform.trans', value={'vec3': [float(c) for c in novo]}))
            if ops:
                self.ebx_edit_mais(name, ops, 'slc')
            report[layer] = dict(total=len(objs), **conta)
            totais.update(conta)
        self.slc_bancos(groups, report)
        report['resumo'] = dict(totais)
        self.report['personagens'] = report
        partes = [f"{totais[k]} {r}" for k, r in (('fifa16', 'nos marcadores do FIFA 16'), ('no_lugar', 'no lugar do El Grandioso'),
                                                 ('movido', 'ajustados'), ('escondidos', 'fora de vista')) if totais[k]]
        base.aviso('personagens laterais: ' + ', '.join(partes))

    def slc_bancos(self, groups, report):
        """Reservas (choreo_seats, 7 de cada lado). Receita "reservas":
        - "cadeiras" (padrão): nas cadeiras do banco do FIFA 16 achadas na geometria (motor/fifa16/bancos.py);
        - "marcadores": nos marcadores slc_benchplayer* do FIFA 16 (cada autor os pôs de um jeito: confira em partida);
        - "esconder": 100 m abaixo do piso;
        - "v3": como saiu o Morumbi v3 (nos marcadores, girados 90 graus).
        Os que não têm lugar saem de vista (100 m abaixo do piso). A orientação é a do El Grandioso (o banco dele fica em
        -z, virado para +z); um banco em +z gira 180 graus."""
        from . import bancos
        modo = self.rc.get('reservas') or 'cadeiras'
        if modo not in ('cadeiras', 'marcadores', 'esconder', 'v3'):
            falha('modo de reservas desconhecido: ' + str(modo))
        name = self.S + 'choreo_seats'
        d = self.ebx_dump(name)
        objs = [int(x.split(':')[2]) for x in d['instances'][0]['fields']['Objects']]
        bt = {i: d['instances'][i]['fields']['BlueprintTransform'] for i in objs}
        trans = {i: bt[i]['trans'] for i in objs}
        ops = []
        if modo == 'v3':
            for side, key in ((-1, 'slc_benchplayerhome'), (1, 'slc_benchplayeraway')):
                mine = sorted([i for i in objs if np.sign(trans[i]['x']) == side], key=lambda i: trans[i]['x'])
                pts = sorted(groups.get(key, []), key=lambda p: p[0])
                for i, p in zip(mine, pts):
                    for axis, vec in (('right', [1.0, 0.0, 0.0]), ('up', [0.0, 1.0, 0.0]), ('forward', [0.0, 0.0, 1.0]), ('trans', p)):
                        ops.append(dict(op='set', target={'index': i}, path=f'BlueprintTransform.{axis}', value={'vec3': [float(c) for c in vec]}))
                report['reservas_' + ('casa' if side < 0 else 'visitante')] = dict(fc27=len(mine), fifa16=len(pts), movidos=min(len(mine), len(pts)))
        else:
            cad = bancos.cadeiras(self.triangulos16()) if modo == 'cadeiras' else None
            for side, key in ((-1, 'slc_benchplayerhome'), (1, 'slc_benchplayeraway')):
                mine = sorted([i for i in objs if np.sign(trans[i]['x']) == side], key=lambda i: abs(trans[i]['x']))
                if modo == 'cadeiras':
                    pts = bancos.lugares_dos_reservas(cad, len(mine), side)
                elif modo == 'marcadores':
                    pts = sorted(groups.get(key, []), key=lambda p: abs(p[0]))
                else:
                    pts = []
                for k, i in enumerate(mine):
                    t = trans[i]
                    if k < len(pts):
                        p = [float(c) for c in pts[k]]
                        if p[2] * t['z'] < 0:  # banco do outro lado do campo: meia volta
                            for axis in ('right', 'forward'):
                                ops.append(dict(op='set', target={'index': i}, path=f'BlueprintTransform.{axis}',
                                                value={'vec3': [-float(bt[i][axis][a]) for a in 'xyz']}))
                    else:
                        p = [t['x'], t['y'] - 100.0, t['z']]
                    ops.append(dict(op='set', target={'index': i}, path='BlueprintTransform.trans', value={'vec3': p}))
                report['reservas_' + ('casa' if side < 0 else 'visitante')] = dict(modo=modo, fc27=len(mine), colocados=min(len(mine), len(pts)),
                                                                                  fora_de_vista=max(0, len(mine) - len(pts)))
            if modo == 'cadeiras':
                report['cadeiras_do_banco'] = int(len(cad))
            postos = sum(report[k]['colocados'] for k in ('reservas_casa', 'reservas_visitante'))
            if modo != 'esconder' and postos < len(objs):
                base.aviso(f'reservas: {postos} de {len(objs)} no banco do FIFA 16 ({modo}); os outros saem de vista')
        if ops:
            self.ebx_edit(name, ops, 'seats')
        self.report['personagens'] = report

    def stage_db(self):
        """O estádio novo recebe o nome no banco (stadiums.name, texto UTF-8 de tamanho fixo); mais nada muda."""
        nome = self.cfg['nome']
        ch = self.p.chunk_db()
        db = self.p.raw('chunk', ch['id'])
        src = self.work / 'in' / 'fifa_ng_db.db'
        src.write_bytes(db)
        meta_xml = self.amb.meta_db()
        _, tables = t3db.read_db(str(src), str(meta_xml))
        nt = struct.unpack_from('<I', db, 16)[0]
        base0 = 0x18 + 8 * nt + 4

        def spans(blob):
            ents = [struct.unpack_from('<4sI', blob, 0x18 + 8 * i) for i in range(nt)]
            order = sorted(range(nt), key=lambda i: ents[i][1])
            return {ents[i][0].decode('latin1'): (base0 + ents[i][1], base0 + ents[order[k + 1]][1] if k + 1 < nt else len(blob))
                    for k, i in enumerate(order)}
        span = spans(db)
        t = next(x for x in tables if x.name == 'stadiums')
        start, end = span[t.sn]
        flags, recsize, nbits, strlen, nrec, nvalid, u6, u7, nf, u9, tcrc = struct.unpack_from('<IIIIHHHHIII', db, start)
        if strlen or nrec != nvalid:
            falha('stadiums: layout não suportado')
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
            falha('stadiums: autoteste de reconstrução falhou')
        idf = next(f for f in t.fields if f.name == 'stadiumid')
        namef = next(f for f in t.fields if f.name == 'name')
        ids = [t3db._get_bits(r, idf.bitoff, idf.depth) + idf.low for r in rows]
        if ids.count(self.N) != 1:
            falha(f'stadiums: linha {self.N} ausente ou repetida')
        k = ids.index(self.N)
        o, n = namef.bitoff // 8, namef.depth // 8
        old = rows[k][o:o + n].split(b'\0')[0].decode('utf8')
        if old == nome:
            self.report['banco'] = dict(estadio=self.N, nome=nome)
            return
        nb = nome.encode('utf8')
        if namef.ftype != 0 or len(nb) >= n:
            falha(f'o nome "{nome}" passa do limite do banco ({n - 1} bytes)')
        rows[k] = rows[k][:o] + nb + b'\0' * (n - len(nb)) + rows[k][o + n:]
        dest = self.work / 'out' / 'fifa_ng_db.db'
        if dest.exists():
            dest.unlink()
        t3db.write_db(db, tables, {'stadiums': build(rows)}, str(dest))
        out = dest.read_bytes()
        nspan = spans(out)
        for x in tables:
            if x.name != 'stadiums' and db[span[x.sn][0]:span[x.sn][1]] != out[nspan[x.sn][0]:nspan[x.sn][1]]:
                falha('tabela alterada sem querer: ' + x.name)
        _, t2 = t3db.read_db(str(dest), str(meta_xml))
        s2 = next(x for x in t2 if x.name == 'stadiums')
        fn = [f.name for f in t.fields]
        before = next(r for r in t.rows if r[fn.index('stadiumid')] == str(self.N))
        after = next(r for r in s2.rows if r[fn.index('stadiumid')] == str(self.N))
        diff = {fn[i]: (before[i], after[i]) for i in range(len(fn)) if before[i] != after[i]}
        if set(diff) != {'name'} or len(s2.rows) != len(t.rows):
            falha('banco: mudança diferente da esperada ' + json.dumps(diff, ensure_ascii=False))
        self.chunk_edits[ch['id']] = out
        self.report['banco'] = dict(estadio=self.N, nome_antes=old, nome=nome)

    # ------------------------------------------------------------ montagem
    def assemble(self):
        for name, data in self.edits.items():
            self.replace('ebx', name, data)
        for name, (data, meta) in self.res_edits.items():
            self.replace('res', name, data, record=dict(resmeta=meta))
        for cid, data in self.chunk_edits.items():
            self.replace('chunk', cid, data, record=dict(logical_size=len(data)))
        for h, H in self.hosts.items():
            hr = self.host_res[h]
            self.replace('ebx', H['mesh'], self.host_ebx[h])
            self.replace('res', H['mesh'], hr['raw'], record=dict(resmeta=hr['meta']))
            self.replace('chunk', hr['chunk_id'], hr['chunk'], record=dict(logical_size=len(hr['chunk'])))
        self.replace('ebx', self.MVDB, self.mvdb_ebx)
        self.replace('res', self.MAIN_DEPOT, self.depot['raw'], record=dict(resmeta=self.depot['meta'],
                     shader_registrations=[[int(a), int(b)] for a, b in self.depot['registrations']]))
        for key, t in self.tex.items():
            self.add('ebx', t['name'], t['ebx'], dict(name=t['name'], type='TextureAsset', partition=t['partition'], is_added=True,
                                                      addedbundles=[self.MAIN_BUNDLE]))
            self.add('res', t['name'], t['res'], dict(name=t['name'], is_added=True, restype=RES_TEXTURE, resrid=t['rid'], resmeta=t['res_meta'],
                                                      addedbundles=[self.MAIN_BUNDLE]))
            cr = dict(id=t['chunk'], is_added=True, addedbundles=[self.MAIN_BUNDLE], logical_size=t['chunk_rec']['logical_size'], h32=t['h32'],
                      superbundlehash=self.MAIN_SUPERBUNDLE)
            if t['chunk_rec']['logical_offset']:
                cr['logical_offset'] = t['chunk_rec']['logical_offset']
            self.add('chunk', t['chunk'], t['cas'], cr)

    def build(self):
        steps = [('modelos', self.templates), ('identidades', self.identities), ('texturas', self.build_textures),
                 ('materiais', self.build_mesh_ebx), ('mvdb', self.build_mvdb), ('deposito', self.build_depot),
                 ('meshes', self.build_host_mesh), ('caixas', self.stage_host_blueprint), ('esconder', self.stage_hide),
                 ('telao', self.stage_scoreclock), ('gramado', self.stage_pitch), ('torcida', self.stage_crowd),
                 ('luzes da torcida', self.stage_luzes), ('glares', self.stage_glares), ('personagens', self.stage_slc),
                 ('banco', self.stage_db)]
        if int(self.rc.get('luz') or BASE_ID) != BASE_ID:
            falha(f"o pré-cálculo de luz de outro estádio (estádio {self.rc['luz']}) está desativado: com ele a partida fica "
                  f"carregando sem fim. A conversão usa o do El Grandioso ({BASE_ID}).")
        base.etapa('converter', 'Aplicando o estádio do FIFA 16 sobre o El Grandioso')
        self.load()
        for k, (nome, fn) in enumerate(steps):
            base.progresso(100 * k / len(steps), nome)
            fn()
        self.assemble()
        base.progresso(100, 'pronto')
        return self.report


def receita_final(pasta16, receita=None):
    """A receita da conversão: a guardada para o estádio (ex.: Morumbi v3) ou a sugerida pela análise, com os ajustes."""
    an = analise.analisar(pasta16)
    pronta = receita_pronta(an['fifa16_id'])
    r = dict(pronta) if pronta else dict(an['receita'], prefixo=f"fifa16_{an['fifa16_id']}", pasta_nome=f"fifa16_{an['fifa16_id']}")
    if receita:
        r.update({k: v for k, v in receita.items() if v is not None})
    r['fifa16_id'] = an['fifa16_id']
    return r, an


def converter(amb, cfg):
    """cfg: pasta16, novo_id, nome, saida, projeto_base (opcional), receita (ajustes), nome_base (nome do El Grandioso
    duplicado no banco antes da conversão; padrão = o nome final)."""
    from .. import duplicar, verificar
    saida = Path(cfg['saida']).resolve()
    if saida.exists():
        falha('o arquivo de saída já existe: ' + str(saida))
    work = Path(cfg.get('trabalho') or base.pasta_trabalho('converter'))
    base.etapa('analise', 'Lendo o estádio do FIFA 16')
    rc, an = receita_final(cfg['pasta16'], cfg.get('receita'))
    cfg = dict(cfg, receita=rc)
    base.progresso(100, f"estádio {an['fifa16_id']} do FIFA 16: {an['resumo']['pecas']} peças")
    base.etapa('preparar16', 'Preparando geometria e texturas do FIFA 16')
    prep = work / 'prep'
    resumo = preparar.preparar(cfg['pasta16'], prep, rc)
    base.progresso(100, f"{resumo['subsets']} subsets, {resumo['textures']} texturas")
    base_proj = work / f'base_{BASE_ID}_{cfg["novo_id"]}.fifaproject'
    dup = duplicar.Duplicacao(amb, [dict(origem=BASE_ID, novo_id=int(cfg['novo_id']), nome=cfg.get('nome_base') or cfg['nome'])],
                              base_proj, cfg.get('projeto_base'), work / 'duplicata')
    dup.run()
    proj = P.Projeto(base_proj, amb.cas())
    conv = Conversao(amb, cfg, proj, dup, prep, work / 'conversao')
    rep = conv.build()
    base.etapa('gravar', 'Gravando o projeto do FET')
    rep['projeto'] = conv.plano.gravar(saida, P.perfil_identidade(amb))
    base.progresso(100, 'projeto gravado')
    ver = None
    if cfg.get('verificar', True):
        ver = verificar.verificar_projeto(amb, saida, work, cfg.get('projeto_base'), [cp.verificacao for cp in dup.copias])
    res = dict(ok=not ver or ver['ok'], saida=str(saida), sha256=rep['projeto']['sha256'], trabalho=str(work), fifa16_id=an['fifa16_id'],
               novo_id=int(cfg['novo_id']), nome=cfg['nome'], receita=rc, conversao=rep, verificacao=ver)
    base.gravar_json(work / 'resultado.json', res)
    return res
