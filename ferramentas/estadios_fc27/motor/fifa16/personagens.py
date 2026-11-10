"""Personagens laterais do El Grandioso (gandulas, fotógrafos, câmeras, policiais, seguranças, médicos...) no estádio novo.

Os marcadores ficam nas camadas slc_* e choreo_slc_* do El Grandioso, logo atrás das placas dele (|z| de 40 a 53 m nas
laterais, |x| de 58 a 78 m atrás dos gols). Num estádio do FIFA 16 com a arquibancada mais perto do campo, eles ficariam
dentro da geometria. O ajuste usa uma grade de 25 cm da geometria preparada do FIFA 16:
- ocupado: algo na altura de uma pessoa (0,25 a 1,9 m acima do piso), com meia largura de folga (45 cm);
- coberto: algo logo acima (1,9 a 6 m), como os degraus da arquibancada;
- escondido: entre o lugar e o campo há algo na altura de uma pessoa (o muro da arquibancada, por exemplo).
Um marcador que não está em nenhum desses fica onde está. Os outros vão para a célula boa mais próxima que não fique mais
longe do campo do que eles estavam, fora das placas do El Grandioso (que continuam no estádio), a mais de 1 m das linhas e
a mais de 60 cm de outro personagem movido. Sem lugar a até 10 m, o personagem sai de vista.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np

CELULA = 0.25
X0, Z0 = -100.0, -80.0
NX, NZ = 800, 640                  # 200 x 160 m em volta do centro do campo
FAIXA = (0.25, 1.9)                # altura de uma pessoa acima do piso
TETO = 6.0                         # até onde algo acima dela a cobre
CHAO = (-0.6, 0.25)                # o que conta como piso
ALCANCE = 30.0                     # distância do campo até onde a visada é conferida
RAIO = 0.45                        # meia largura de uma pessoa
CAMPO = np.array([52.5, 34.0])     # meio comprimento e meia largura do campo
MARGEM_CAMPO = 1.0
BUSCA = 10.0
ENTRE_PESSOAS = 0.6


def _pontos(tri, passo=0.15, maxn=200, lote=20000):
    """Amostras de cada triângulo numa grade baricêntrica de ~15 cm (paredes verticais também marcam a grade)."""
    e = np.linalg.norm(tri[:, [1, 2, 0]] - tri, axis=2).max(1)
    n = np.clip(np.ceil(e / passo).astype(int), 1, maxn)
    for k in np.unique(n):
        sel = tri[n == k]
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing='ij')
        m = i + j <= k
        a, b = i[m] / k, j[m] / k
        w = np.stack([1 - a - b, a, b], 1)
        for q in range(0, len(sel), max(1, lote // len(w) + 1)):
            yield np.einsum('pv,tvk->tpk', w, sel[q:q + max(1, lote // len(w) + 1)]).reshape(-1, 3)


class Grade:
    def __init__(self):
        self.ocupado = np.zeros((NX, NZ), bool)     # geometria do FIFA 16 na altura de uma pessoa
        self.coberto = np.zeros((NX, NZ), bool)     # geometria do FIFA 16 logo acima
        self.placas = np.zeros((NX, NZ), bool)      # placas do El Grandioso
        self.piso = np.full((NX, NZ), -np.inf)

    @staticmethod
    def celula(x, z):
        return np.floor((np.asarray(x) - X0) / CELULA).astype(int), np.floor((np.asarray(z) - Z0) / CELULA).astype(int)

    @staticmethod
    def centro(i, j):
        return X0 + (np.asarray(i) + 0.5) * CELULA, Z0 + (np.asarray(j) + 0.5) * CELULA

    def _dentro(self, i, j):
        return (i >= 0) & (i < NX) & (j >= 0) & (j < NZ)

    def triangulos(self, tri):
        y0, y1 = tri[..., 1].min(1), tri[..., 1].max(1)
        x, z = tri[..., 0], tri[..., 2]
        perto = (x.max(1) > X0) & (x.min(1) < X0 + NX * CELULA) & (z.max(1) > Z0) & (z.min(1) < Z0 + NZ * CELULA)
        tri = tri[perto & (y1 >= CHAO[0]) & (y0 <= TETO)]
        for p in _pontos(tri):
            i, j = self.celula(p[:, 0], p[:, 2])
            ok = self._dentro(i, j)
            i, j, y = i[ok], j[ok], p[ok, 1]
            corpo = (y >= FAIXA[0]) & (y <= FAIXA[1])
            self.ocupado[i[corpo], j[corpo]] = True
            cima = (y > FAIXA[1]) & (y <= TETO)
            self.coberto[i[cima], j[cima]] = True
            pe = (y >= CHAO[0]) & (y < FAIXA[0])
            np.maximum.at(self.piso, (i[pe], j[pe]), y[pe])

    def segmento(self, a, b, meia_espessura=0.25):
        a, b = np.asarray(a, float), np.asarray(b, float)
        L = max(np.linalg.norm(b - a), 1e-6)
        d = (b - a) / L
        nrm = np.array([-d[1], d[0]])
        s = np.arange(0.0, L + 0.05, 0.1)
        t = np.arange(-meia_espessura, meia_espessura + 0.01, 0.1)
        P = a[None, None, :] + s[:, None, None] * d + t[None, :, None] * nrm
        i, j = self.celula(P[..., 0].ravel(), P[..., 1].ravel())
        ok = self._dentro(i, j)
        self.placas[i[ok], j[ok]] = True

    @staticmethod
    def dilatar(m, raio=RAIO):
        r = int(np.ceil(raio / CELULA))
        out = m.copy()
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if (di * di + dj * dj) * CELULA * CELULA > raio * raio + 1e-9 or (di == 0 and dj == 0):
                    continue
                src = m[max(0, -di):NX - max(0, di), max(0, -dj):NZ - max(0, dj)]
                out[max(0, di):NX - max(0, -di), max(0, dj):NZ - max(0, -dj)] |= src
        return out

    def visada(self, cx, cz, dcampo):
        """True onde a linha reta até o ponto mais perto do campo não passa por geometria na altura de uma pessoa."""
        ok = np.ones(cx.shape, bool)
        ativo = (dcampo > 0) & (dcampo <= ALCANCE)
        alvo_x, alvo_z = np.clip(cx, -CAMPO[0], CAMPO[0]), np.clip(cz, -CAMPO[1], CAMPO[1])
        dx, dz = alvo_x - cx, alvo_z - cz
        L = np.maximum(np.hypot(dx, dz), 1e-9)
        ux, uz = dx / L, dz / L
        s = 0.6  # o próprio lugar e a folga em volta já contam no "ocupado"
        while s < ALCANCE:
            m = ativo & (s < L)
            if not m.any():
                break
            i, j = self.celula(cx[m] + ux[m] * s, cz[m] + uz[m] * s)
            dentro = self._dentro(i, j)
            bate = np.zeros(len(i), bool)
            bate[dentro] = self.ocupado[i[dentro], j[dentro]]
            idx = np.flatnonzero(m)
            ok.flat[idx[bate]] = False
            ativo.flat[idx[bate]] = False
            s += CELULA * 0.8
        ok[dcampo > ALCANCE] = False
        return ok


def ler_geometria(prep):
    """Triângulos (t, 3, 3) em metros de toda a geometria preparada do FIFA 16 (prep/subsets.json + geometry.bin)."""
    prep = Path(prep)
    subs = json.loads((prep / 'subsets.json').read_text(encoding='utf8'))
    blob = (prep / 'geometry.bin').read_bytes()
    tris = []
    for s in subs['subsets']:
        n, t, o = s['vertices'], s['triangles'], s['offset']
        pos = np.frombuffer(blob, '<f4', n * 3, o).reshape(n, 3).astype(np.float64)
        idx = np.frombuffer(blob, '<u4', t * 3, o + n * 56).reshape(t, 3)
        tris.append(pos[idx])
    return np.concatenate(tris) if tris else np.zeros((0, 3, 3))


def distancia_ao_campo(x, z):
    q = np.maximum(np.abs(np.stack([np.asarray(x, float), np.asarray(z, float)], -1)) - CAMPO, 0.0)
    return np.linalg.norm(q, axis=-1)


class Ajuste:
    """grade = Grade com a geometria e as placas; ajustar(p) -> ('fica'|'movido'|'sem_lugar', posição nova)."""

    def __init__(self, grade):
        self.g = grade
        ii, jj = np.meshgrid(np.arange(NX), np.arange(NZ), indexing='ij')
        cx, cz = Grade.centro(ii, jj)
        self.cx, self.cz = cx, cz
        self.dcampo = distancia_ao_campo(cx, cz)
        fora = (np.abs(cx) > CAMPO[0] + MARGEM_CAMPO) | (np.abs(cz) > CAMPO[1] + MARGEM_CAMPO)
        # onde um personagem do El Grandioso pode ficar (as placas são do próprio El Grandioso: não contam) e onde um
        # personagem movido pode ir (fora das placas também)
        self.fica = ~Grade.dilatar(grade.ocupado) & ~grade.coberto & grade.visada(cx, cz, self.dcampo) & fora
        self.livre = self.fica & ~Grade.dilatar(grade.placas)
        self.movidos = []

    def piso(self, x, z):
        i, j = Grade.celula(x, z)
        win = self.g.piso[max(0, i - 1):i + 2, max(0, j - 1):j + 2]
        v = win[np.isfinite(win)]
        return float(v.max()) if len(v) else None

    def ajustar(self, p):
        x, y, z = (float(c) for c in p)
        i, j = Grade.celula(x, z)
        if 0 <= i < NX and 0 <= j < NZ and self.fica[i, j]:
            return 'fica', p
        r = int(np.ceil(BUSCA / CELULA))
        i0, i1, j0, j1 = max(0, i - r), min(NX, i + r + 1), max(0, j - r), min(NZ, j + r + 1)
        if i0 >= i1 or j0 >= j1:
            return 'sem_lugar', p
        cx, cz = self.cx[i0:i1, j0:j1], self.cz[i0:i1, j0:j1]
        d = np.hypot(cx - x, cz - z)
        ok = self.livre[i0:i1, j0:j1] & (d <= BUSCA) & (self.dcampo[i0:i1, j0:j1] <= distancia_ao_campo(x, z) + 0.25)
        for q in self.movidos:
            ok &= np.hypot(cx - q[0], cz - q[1]) >= ENTRE_PESSOAS
        if not ok.any():
            return 'sem_lugar', p
        k = np.unravel_index(np.argmin(np.where(ok, d, np.inf)), d.shape)
        nx, nz = float(cx[k]), float(cz[k])
        py = self.piso(nx, nz)
        self.movidos.append((nx, nz))
        return 'movido', [nx, y if py is None else max(y, py), nz]


def segmentos_de_placas(posicoes):
    """Placas (x, z) do El Grandioso -> segmentos por linha (mesma z nas laterais, mesmo x atrás dos gols), com meia
    placa de cada lado (metade do espaçamento entre elas)."""
    segs = []
    for eixo in (0, 1):
        linhas = {}
        for p in posicoes:
            fixo = p[1 - eixo]
            if (eixo == 0 and abs(fixo) > 36) or (eixo == 1 and abs(fixo) > 50):
                linhas.setdefault(round(fixo, 1), []).append(p[eixo])
        for fixo, vals in linhas.items():
            vals = sorted(vals)
            if len(vals) < 2:
                meia = 2.0
            else:
                meia = float(np.median(np.diff(vals))) / 2
            a, b = vals[0] - meia, vals[-1] + meia
            segs.append(((a, fixo), (b, fixo)) if eixo == 0 else ((fixo, a), (fixo, b)))
    return segs
