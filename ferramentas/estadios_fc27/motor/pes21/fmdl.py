"""Leitor dos modelos .fmdl do Fox Engine (PES 2021, versão 2.03): malhas, materiais, texturas e nomes.

Layout (conferido nos modelos do Camp Nou do PES 2021):
  cabeçalho  'FMDL', f32 versão, u64 deslocamento das tabelas (0x40), u64 e u64 máscaras dos blocos, u32 blocos da seção 0,
             u32 blocos da seção 1, u32 início e tamanho da seção 0, u32 início e tamanho da seção 1
  tabelas    seção 0: (u16 id, u16 entradas, u32 deslocamento); seção 1: (u32 id, u32 deslocamento, u32 tamanho)
  seção 0    0x00 ossos (0x30)            0x01 grupos de malha (8: nome, invisível, pai, -1)
             0x02 malhas de cada grupo (0x20: +4 grupo, +6 quantas, +8 primeira)
             0x03 malhas (0x30: +0 alpha, +1 sombra, +4 material, +6 grupo de ossos, +8 formato, +0xA vértices,
                  +0x10 primeiro índice, +0x14 quantos índices, +0x18 primeira entrada de LOD)
             0x04 materiais da malha (0x10: nome, +4 shader, +6 texturas, +7 parâmetros, +8 primeira textura, +0xA primeiro parâmetro)
             0x06 texturas (4: nome, pasta)      0x07 (4: nome do parâmetro, índice da textura ou do vetor de 4 floats)
             0x08 shaders (4: shader, técnica)   0x09 formato da malha (8: fluxos, elementos, ?, primeiro fluxo, primeiro elemento)
             0x0A fluxos (8: buffer, elementos, tamanho do vértice, tipo, deslocamento no buffer)
             0x0B elementos (4: uso, tipo, deslocamento)   0x0C textos (8: bloco, tamanho, deslocamento)
             0x0D caixas (0x20: máximo xyzw, mínimo xyzw)   0x0E buffers (0x10: 1 = índices, tamanho, deslocamento)
             0x10 LODs (u32 quantos, distâncias)           0x11 (8: primeiro índice e quantos índices de cada malha em cada LOD)
  seção 1    0 parâmetros dos materiais (vetores de 4 floats), 2 buffers de vértices e índices, 3 textos
Elementos de vértice: uso 0 posição (float3), 1 pesos, 2 normal (half4), 3 cor (4 bytes), 7 ossos, 8 a 11 UV0 a UV3 (half2),
14 tangente (half4). Unidades em metros, Y para cima.
"""
import struct

import numpy as np

USO = {0: 'pos', 1: 'pesos', 2: 'normal', 3: 'cor', 7: 'ossos', 8: 'uv0', 9: 'uv1', 10: 'uv2', 11: 'uv3', 12: 'pesos1', 13: 'ossos1',
       14: 'tangente'}
TIPO = {1: ('<f4', 3), 4: ('<u2', 1), 6: ('<f2', 4), 7: ('<f2', 2), 8: ('u1', 4), 9: ('u1', 4)}


class Fmdl:
    def __init__(self, dados, nome=''):
        b = self.b = bytes(dados)
        self.nome = nome
        if b[:4] != b'FMDL':
            raise ValueError('não é FMDL: ' + nome)
        self.versao, tabelas, _, _, n0, n1, self.s0, s0len, self.s1, s1len = struct.unpack_from('<fQQQIIIIII', b, 4)
        if self.s0 + s0len > len(b) or self.s1 + s1len > len(b):
            raise ValueError('FMDL truncado: ' + nome)
        self.blocos0, self.blocos1 = {}, {}
        q = tabelas
        for _ in range(n0):
            ident, cnt, off = struct.unpack_from('<HHI', b, q)
            self.blocos0[ident] = (cnt, self.s0 + off)
            q += 8
        for _ in range(n1):
            ident, off, ln = struct.unpack_from('<III', b, q)
            self.blocos1[ident] = (self.s1 + off, ln)
            q += 12
        self.textos = self._textos()
        self.lods = struct.unpack_from('<I', b, self.blocos0[0x10][1])[0] if 0x10 in self.blocos0 else 1

    def _itens(self, ident, fmt, tam):
        cnt, off = self.blocos0.get(ident, (0, 0))
        return [struct.unpack_from(fmt, self.b, off + tam * i) for i in range(cnt)]

    def _textos(self):
        if 0x0C not in self.blocos0 or 3 not in self.blocos1:
            return []
        base = self.blocos1[3][0]
        return [self.b[base + off:base + off + ln].decode('utf8', 'replace') for _, ln, off in self._itens(0x0C, '<HHI', 8)]

    def texto(self, i):
        return self.textos[i] if 0 <= i < len(self.textos) else ''

    def caixas(self):
        return [(c[4:7], c[0:3]) for c in self._itens(0x0D, '<8f', 0x20)]

    def grupos(self):
        """Nome do grupo de cada malha (o nome do objeto no editor de quem fez o estádio)."""
        nomes = [self.texto(g[0]) for g in self._itens(0x01, '<HHHH', 8)]
        vis = [g[1] for g in self._itens(0x01, '<HHHH', 8)]
        out = {}
        for _, grupo, quantas, primeira, _ in self._itens(0x02, '<IHHHH', 0x20):
            for k in range(primeira, primeira + quantas):
                out[k] = (nomes[grupo] if grupo < len(nomes) else '', vis[grupo] if grupo < len(vis) else 0)
        return out

    def materiais(self):
        shaders = [(self.texto(a), self.texto(b)) for a, b in self._itens(0x08, '<HH', 4)]
        texs = [(self.texto(a), self.texto(b)) for a, b in self._itens(0x06, '<HH', 4)]
        refs = self._itens(0x07, '<HH', 4)
        pbase = self.blocos1.get(0, (0, 0))
        out = []
        for nome, _, sh, ntex, npar, ptex, ppar, _ in self._itens(0x04, '<HHHBBHHI', 0x10):
            tex = {}
            for k in range(ptex, ptex + ntex):
                papel, ref = refs[k]
                arq, pasta = texs[ref] if ref < len(texs) else ('', '')
                tex[self.texto(papel)] = pasta + arq
            par = {}
            for k in range(ppar, ppar + npar):
                papel, ref = refs[k]
                if pbase[1] >= 16 * (ref + 1):
                    par[self.texto(papel)] = struct.unpack_from('<4f', self.b, pbase[0] + 16 * ref)
            out.append(dict(nome=self.texto(nome), shader=shaders[sh][0] if sh < len(shaders) else '',
                            tecnica=shaders[sh][1] if sh < len(shaders) else '', texturas=tex, parametros=par))
        return out

    def malhas(self):
        """Uma entrada por malha: material, grupo, contagens e como ler os vértices e os índices (LOD 0)."""
        fmt_malha = self._itens(0x09, '<BBHHH', 8)
        fluxos = self._itens(0x0A, '<BBBBI', 8)
        elementos = self._itens(0x0B, '<BBH', 4)
        buffers = self._itens(0x0E, '<III', 0x10)
        lods = self._itens(0x11, '<II', 8)
        grupos = self.grupos()
        mats = self.materiais()
        dados = self.blocos1[2][0]
        ibuf = next((bf for bf in buffers if bf[0] == 1), None)
        out = []
        for k, m in enumerate(self._itens(0x03, '<BBHHHHHIIIQ', 0x30)):
            alpha, sombra, _, mat, _, fm, nv, _, primeiro, quantos, lod0 = m
            nf, ne, _, pf, pe = fmt_malha[fm]
            els = []
            e = pe
            for f in range(pf, pf + nf):
                buf, n_el, passo, _, desl = fluxos[f]
                for _ in range(n_el):
                    uso, tipo, off = elementos[e]
                    e += 1
                    els.append(dict(uso=USO.get(uso, f'uso{uso}'), tipo=tipo, inicio=dados + buffers[buf][2] + desl + off, passo=passo))
            if lod0 < len(lods):
                primeiro, quantos = primeiro + lods[lod0][0], lods[lod0][1]
            out.append(dict(indice=k, alpha=alpha, sombra=sombra, material=mats[mat] if mat < len(mats) else None, material_indice=mat,
                            grupo=grupos.get(k, ('', 0))[0], invisivel=grupos.get(k, ('', 0))[1], vertices=nv, indices=quantos,
                            elementos=els, inicio_indices=dados + ibuf[2] + 2 * primeiro if ibuf else None))
        return out

    def vertices(self, malha):
        """{uso: array (n, k)} dos vértices de uma malha."""
        n = malha['vertices']
        out = {}
        for el in malha['elementos']:
            dt, k = TIPO.get(el['tipo'], (None, 0))
            if dt is None:
                continue
            tam = np.dtype(dt).itemsize * k
            if el['inicio'] + el['passo'] * (n - 1) + tam > len(self.b):
                raise ValueError('vértices fora do arquivo: ' + self.nome)
            a = np.ndarray((n, k), dt, self.b, el['inicio'], (el['passo'], np.dtype(dt).itemsize))
            out[el['uso']] = np.array(a, np.float32 if dt[1] == 'f' else None)
        return out

    def indices(self, malha):
        return np.frombuffer(self.b, '<u2', malha['indices'], malha['inicio_indices']).astype(np.int64)
