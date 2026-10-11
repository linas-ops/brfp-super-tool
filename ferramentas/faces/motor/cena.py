"""Acesso às malhas de um FBX de cabeça (exportado pelo FET ou pelo Blender)."""
import collections
import re

import numpy as np

from fbxio import read_fbx


def props70(node):
    """Properties70 -> {nome: [valores]}"""
    out = {}
    p70 = node.find('Properties70') if node is not None else None
    if p70 is None:
        return out
    for p in p70.children:
        vals = [q.v for q in p.props]
        out[vals[0]] = vals[4:]
    return out


def _euler(deg, order=0):
    rx, ry, rz = np.radians(deg)
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    X = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    seq = {0: (Z, Y, X), 1: (Y, Z, X), 2: (Z, X, Y), 3: (X, Z, Y), 4: (Y, X, Z), 5: (X, Y, Z)}[order]
    return seq[0] @ seq[1] @ seq[2]


def _mat4(R=None, t=None, s=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if s is not None:
        M[:3, :3] = M[:3, :3] @ np.diag(s)
    if t is not None:
        M[:3, 3] = t
    return M


def cantos_triangulos(pvi):
    """PolygonVertexIndex -> trincas de índices de canto (leque para polígonos com mais de 3 lados)"""
    pvi = np.asarray(pvi)
    ends = np.where(pvi < 0)[0]
    if len(pvi) == 3 * len(ends) and np.all(ends == np.arange(2, len(pvi), 3)):
        return np.arange(len(pvi)).reshape(-1, 3)
    corners = []
    start = 0
    for e in ends:
        for k in range(start + 1, e):
            corners.append((start, k, k + 1))
        start = e + 1
    return np.array(corners, int).reshape(-1, 3)


def triangulos(pvi):
    """PolygonVertexIndex -> triângulos em índices de vértice"""
    pvi = np.asarray(pvi)
    idx = np.where(pvi < 0, ~pvi, pvi)
    return idx[cantos_triangulos(pvi)]


class Malha:
    """uma seção (material) de um LOD"""

    def __init__(self, nome, mat, lod, model_id, geom_id):
        self.nome, self.mat, self.lod = nome, mat, lod
        self.model_id, self.geom_id = model_id, geom_id

    def __repr__(self):
        return '<%s lod%d %d verts>' % (self.mat, self.lod, len(self.V))


class Cena:
    def __init__(self, caminho):
        self.caminho = caminho
        self.fbx = read_fbx(caminho)
        root = self.fbx.root
        objs = root.find('Objects')
        self.objs = {o.props[0].v: o for o in objs.children}
        self.children = collections.defaultdict(list)
        self.parent = collections.defaultdict(list)
        conns = root.find('Connections')
        for c in conns.children if conns is not None else []:
            a, b = c.props[1].v, c.props[2].v
            self.children[b].append(a)
            self.parent[a].append(b)
        self.malhas = self._ler_malhas()

    # ---- utilidades de objetos
    def nome(self, oid):
        o = self.objs.get(oid)
        if o is None:
            return ''
        return o.props[1].v.split('\x00\x01')[0]

    def classe(self, oid):
        o = self.objs.get(oid)
        if o is None:
            return None
        return o.name, (o.props[2].v if len(o.props) > 2 else '')

    def matriz_global(self, mid):
        M = np.eye(4)
        cur = mid
        chain = []
        while cur in self.objs and self.objs[cur].name == 'Model':
            chain.append(cur)
            pais = [p for p in self.parent[cur] if p in self.objs and self.objs[p].name == 'Model']
            if not pais:
                break
            cur = pais[0]
        for oid in reversed(chain):
            pr = props70(self.objs[oid])
            order = int(pr.get('RotationOrder', [0])[0])
            t = np.array(pr.get('Lcl Translation', [0, 0, 0]), float)
            r = np.array(pr.get('Lcl Rotation', [0, 0, 0]), float)
            s = np.array(pr.get('Lcl Scaling', [1, 1, 1]), float)
            pre = np.array(pr.get('PreRotation', [0, 0, 0]), float)
            post = np.array(pr.get('PostRotation', [0, 0, 0]), float)
            R = _euler(pre) @ _euler(r, order) @ np.linalg.inv(_euler(post))
            M = M @ _mat4(R, t, s)
        return M

    def matriz_geometrica(self, mid):
        pr = props70(self.objs[mid])
        t = np.array(pr.get('GeometricTranslation', [0, 0, 0]), float)
        r = np.array(pr.get('GeometricRotation', [0, 0, 0]), float)
        s = np.array(pr.get('GeometricScaling', [1, 1, 1]), float)
        return _mat4(_euler(r), t, s)

    # ---- malhas
    def _ler_malhas(self):
        out = []
        for oid, o in self.objs.items():
            if o.name != 'Model' or len(o.props) < 3 or o.props[2].v != 'Mesh':
                continue
            nome = self.nome(oid)
            m = re.match(r'^([A-Za-z0-9_]+?)(?:\.\d+)?:(.*?)[._]?lod[._]?(\d+)$', nome, re.I)
            if not m:
                continue
            geos = [c for c in self.children[oid] if self.classe(c) == ('Geometry', 'Mesh')]
            if not geos:
                continue
            mal = Malha(nome, m.group(1).lower(), int(m.group(3)), oid, geos[0])
            mal.mesh_name = m.group(2)
            self._carregar(mal)
            out.append(mal)
        out.sort(key=lambda m: (m.lod, m.mat))
        return out

    def _camada(self, geo, lename, dataname, idxname, ncomp, layer, pvi):
        le = None
        for ch in geo.children:
            if ch.name == lename and ch.props and ch.props[0].v == layer:
                le = ch
                break
        if le is None:
            return None
        mit = le.find('MappingInformationType').props[0].v
        rit = le.find('ReferenceInformationType').props[0].v
        data = np.asarray(le.find(dataname).props[0].v, float).reshape(-1, ncomp)
        idxn = le.find(idxname)
        if rit in ('IndexToDirect', 'Index') and idxn is not None:
            data = data[np.asarray(idxn.props[0].v)]
        corner_v = np.where(pvi < 0, ~pvi, pvi)
        if mit in ('ByVertice', 'ByVertex'):
            return data[corner_v]
        if mit == 'ByPolygonVertex':
            return data
        if mit == 'ByPolygon':
            return data[np.cumsum(np.r_[0, (pvi < 0)[:-1]])]
        if mit == 'AllSame':
            return np.repeat(data[:1], len(pvi), 0)
        raise ValueError('mapeamento FBX não suportado: %s' % mit)

    def _carregar(self, mal):
        geo = self.objs[mal.geom_id]
        V = np.asarray(geo.find('Vertices').props[0].v, float).reshape(-1, 3)
        pvi = np.asarray(geo.find('PolygonVertexIndex').props[0].v)
        M = self.matriz_global(mal.model_id) @ self.matriz_geometrica(mal.model_id)
        Vw = V @ M[:3, :3].T + M[:3, 3]
        corner_v = np.where(pvi < 0, ~pvi, pvi)
        cantos = cantos_triangulos(pvi)
        camadas = {}
        for chave, args in (('uv0', ('LayerElementUV', 'UV', 'UVIndex', 2, 0)),
                            ('uv1', ('LayerElementUV', 'UV', 'UVIndex', 2, 1)),
                            ('normal', ('LayerElementNormal', 'Normals', 'NormalsIndex', 3, 0))):
            camadas[chave] = self._camada(geo, *args, pvi)
        # como no jogo, um vértice com UVs diferentes em cantos diferentes (costura soldada no
        # Blender, por exemplo) vira um vértice por UV
        vert_canto = corner_v
        mal.dividida = False
        if camadas['uv0'] is not None:
            chave = np.c_[corner_v, np.round(camadas['uv0'], 5)]
            uniq, inv = np.unique(chave, axis=0, return_inverse=True)
            inv = inv.ravel()
            if len(uniq) > len(np.unique(corner_v)):
                mal.dividida = True
                vert_canto = inv
                Vw = Vw[uniq[:, 0].astype(int)]
                V = V[uniq[:, 0].astype(int)]
        mal.V_local = V
        mal.V = Vw
        mal.pvi = pvi
        mal.T = vert_canto[cantos]
        n = len(Vw)
        for chave, c in camadas.items():
            if c is None:
                setattr(mal, chave, None)
                continue
            acc = np.zeros((n, c.shape[1]))
            cnt = np.zeros(n)
            np.add.at(acc, vert_canto, c)
            np.add.at(cnt, vert_canto, 1)
            setattr(mal, chave, acc / np.maximum(cnt, 1)[:, None])
        if mal.normal is not None:
            nn = mal.normal @ M[:3, :3].T
            mal.normal = nn / np.maximum(np.linalg.norm(nn, axis=1), 1e-12)[:, None]

    def malha(self, mat, lod):
        for m in self.malhas:
            if m.mat == mat and m.lod == lod:
                return m
        return None
