"""Conversão de malhas de cabeça (FBX do FIFA Editor Tool) entre FC 26 e FC 27.

Como funciona
-------------
FC 26: cabeça com topologia própria (3 LODs, head_mat + eyes_mat; dentes e
interior da boca dentro do head_mat).
FC 27: "morph head" - todas as cabeças masculinas usam a malha basehead_0
(4 LODs, head_mat + eyes_mat + teeth_mat) e o jogo guarda só os deltas de
posição/UV. O FET só importa se a contagem, a ordem dos vértices e os
triângulos forem exatamente os da basehead.

O par de referência (Messi exportado dos dois jogos) é a mesma cabeça nas duas
topologias. Para converter uma face X do jogo A para o jogo B:
  1. X é casada vértice a vértice com a referência de A (pela conectividade ou
     pela UV, que é padrão);
  2. D = X - refA é o quanto X difere do Messi;
  3. cada vértice da referência de B tem uma âncora na referência de A
     (pré-calculada): na pele, um ponto da superfície (pela UV no rosto, pelo
     ponto mais próximo no pescoço); nas partes internas (boca, dentes), a
     superfície mais próxima com preenchimento harmônico; nos olhos, o olho.
  4. pele: saída = superfície curva (Phong) de X na âncora + só a parte suave
     da diferença refB - refA (o detalhe fino do Messi não passa adiante);
     resto: refB + D interpolado. Dentes se movem sem deformar; duplicados
     das costuras de UV ficam soldados; a base do pescoço fica fixa (solda
     com o corpo).
A saída é a própria referência de B (esqueleto, pesos, LODs, nomes) com as
posições/normais (e a UV da pele) trocadas, então tem exatamente o formato que
o jogo B espera.
"""
import os
import re

import numpy as np
from scipy.spatial import cKDTree

import geometria as G
from cena import Cena
from fbxio import write_fbx

PASTA_REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencia')
REFERENCIAS = {'fc26': 'messi_158023_fc26.fbx', 'fc27': 'messi_158023_fc27.fbx'}
# seções de LOD0 usadas como "campo" de deslocamento de cada jogo
CAMPO = {'fc26': [('head_mat', 0), ('eyes_mat', 0)],
         'fc27': [('head_mat', 0), ('teeth_mat', 0), ('eyes_mat', 0)]}

FAIXA_PESCOCO = 0.02      # m: deslocamento vai a zero na borda do pescoço (solda com o corpo)
DIST_SUPERFICIE = 0.006   # m: acima disso a âncora vira média suave dos vizinhos
SALTO_UV = 0.08           # diferença de UV acima disso = costura; mantém a UV do modelo


class ErroConversao(Exception):
    pass


def detectar_jogo(cena):
    mats = {m.mat for m in cena.malhas}
    lods = {m.lod for m in cena.malhas}
    nomes = ' '.join(m.mesh_name for m in cena.malhas)
    if 'head_mat' not in mats:
        return None
    if 'teeth_mat' in mats or 3 in lods or 'basehead' in nomes:
        return 'fc27'
    return 'fc26'


# ----------------------------------------------------------------------------
# referências e mapas pré-calculados

class Referencia:
    def __init__(self, jogo):
        self.jogo = jogo
        self.cena = Cena(os.path.join(PASTA_REF, REFERENCIAS[jogo]))
        self.campo = []
        self.offset = {}
        n = 0
        for chave in CAMPO[jogo]:
            m = self.cena.malha(*chave)
            self.campo.append((chave, m))
            self.offset[chave] = n
            n += len(m.V)
        self.n_campo = n
        self.R = np.concatenate([m.V for _, m in self.campo])
        self.UV = np.concatenate([m.uv0 for _, m in self.campo])
        # triângulos de cada seção já em índices do campo
        self.T = {chave: m.T + self.offset[chave] for chave, m in self.campo}
        cab = self.cena.malha('head_mat', 0)
        self.ilha_cab = G.ilhas(cab.T, len(cab.V))


DIST_INTERNA = 0.004      # m: partes internas ancoram na superfície mais próxima até essa distância
SIGMA_DETALHE = 0.004     # m: detalhe do modelo mais fino que isso é descartado
DENTE_RIGIDO = 200        # ilhas de teeth_mat menores que isso (cada dente) se movem sem deformar


class Mapa:
    """para cada seção do modelo de destino: matriz W (vértice -> campo da origem), atenuação e
    matriz W_uv (âncoras na pele, sem soldar costuras) para a UV"""

    def __init__(self, ref_origem, ref_destino):
        ro = ref_origem
        self.origem, self.destino = ro, ref_destino
        Tcab = ro.T[('head_mat', 0)]
        T_princ = Tcab[ro.ilha_cab[Tcab[:, 0] - ro.offset[('head_mat', 0)]] == 0]
        sup_princ = G.Superficie(ro.R, T_princ)
        loc_uv = G.LocalizadorUV(ro.UV, T_princ)
        idx_princ = np.unique(T_princ)
        # superfície para as partes internas: cabeça inteira (pele + boca) e dentes, se houver
        T_int = [Tcab] + ([ro.T[('teeth_mat', 0)]] if ('teeth_mat', 0) in ro.T else [])
        T_int = np.concatenate(T_int)
        sup_int = G.Superficie(ro.R, T_int)
        idx_int = np.unique(T_int)
        sup_olhos = G.Superficie(ro.R, ro.T[('eyes_mat', 0)])

        self.secoes = {}
        for m in ref_destino.cena.malhas:
            if m.mat not in ('head_mat', 'teeth_mat', 'eyes_mat'):
                continue
            n = len(m.V)
            lab = G.ilhas(m.T, n)
            trip = []                       # (linhas, colunas, pesos)
            aten = np.ones(n)
            uv_ok = np.zeros(n, bool)
            trip_uv = []
            ancoras = None                  # âncoras baricêntricas da pele (para a interpolação curva)
            internas = []                   # ilhas tratadas como partes internas
            if m.mat == 'head_mat':
                pr = np.where(lab == 0)[0]
                P = m.V[pr]
                # âncora pela UV (rosto) ou pelo ponto mais próximo com normal compatível (pescoço)
                t1, b1, _ = loc_uv.consulta(m.uv0[pr])
                Q1 = (b1[:, :, None] * ro.R[T_princ[t1]]).sum(1)
                d1 = np.linalg.norm(Q1 - P, axis=1)
                d2, t2, b2 = sup_princ.consulta(P, normais=m.normal[pr], cos_min=0.3)
                usa_uv = d1 <= d2 + 0.001
                t = np.where(usa_uv, t1, t2)
                b = np.where(usa_uv[:, None], b1, b2)
                d = np.where(usa_uv, d1, d2)
                ok = d < DIST_SUPERFICIE
                for i in range(3):
                    trip.append((pr[ok], T_princ[t[ok], i], b[ok, i]))
                    trip_uv.append((pr[ok], T_princ[t[ok], i], b[ok, i]))
                ancoras = (pr[ok], T_princ[t[ok]], b[ok])
                uv_anc = (b[:, :, None] * ro.UV[T_princ[t]]).sum(1)
                uv_ok[pr[ok]] = np.abs(uv_anc[ok] - m.uv0[pr[ok]]).max(1) < SALTO_UV
                longe = pr[~ok]
                if len(longe):
                    trip.append(self._suave(longe, m.V[longe], ro.R, idx_princ))
                # atenuação perto da borda do pescoço (solda com o corpo)
                bord = G.anel_do_pescoco(m.V, m.T[lab[m.T[:, 0]] == 0])
                dist = G.distancia_geodesica(m.V, m.T, bord)
                aten[pr] = G.suavizar(dist[pr] / FAIXA_PESCOCO)
                internas = [i for i in range(1, lab.max() + 1)]
            elif m.mat == 'teeth_mat':
                internas = list(range(lab.max() + 1))
            elif m.mat == 'eyes_mat':
                d, t, b = sup_olhos.consulta(m.V, normais=m.normal, cos_min=0.3)
                T_olhos = ro.T[('eyes_mat', 0)]
                for i in range(3):
                    trip.append((np.arange(n), T_olhos[t, i], b[:, i]))

            # partes internas: âncora na superfície mais próxima (lábio, interior, dentes);
            # o que fica longe é preenchido por interpolação harmônica dentro da ilha
            livres = {}
            for il in internas:
                idx = np.where(lab == il)[0]
                d, t, b = sup_int.consulta(m.V[idx], normais=m.normal[idx], cos_min=0.3)
                anc = d < DIST_INTERNA
                for i in range(3):
                    trip.append((idx[anc], T_int[t[anc], i], b[anc, i]))
                if (~anc).any():
                    if anc.any():
                        livres[il] = (idx, anc)
                    else:
                        trip.append(self._suave(idx, m.V[idx], ro.R, idx_int))

            W = self._montar(trip, n, ro.n_campo)
            for il, (idx, anc) in livres.items():
                W = self._harmonico(W, m, idx, anc)
            if m.mat == 'teeth_mat':
                for il in range(lab.max() + 1):
                    idx = np.where(lab == il)[0]
                    if len(idx) < DENTE_RIGIDO:
                        W = self._media_linhas(W, [idx])
            # costuras: vértices duplicados recebem o mesmo deslocamento
            grupos = G.grupos_duplicados(m.V)
            W = self._media_linhas(W, grupos)
            for g in grupos:
                aten[g] = aten[g].mean()
            W_uv = self._montar(trip_uv, n, ro.n_campo) if trip_uv else None
            r_alto = None
            if ancoras is not None and len(ancoras[0]):
                # detalhe fino do modelo que não existe na referência de origem (ex.: rugas que a EA
                # esculpiu só no Messi do FC 27): é tirado para não passar para outro jogador
                lin, tri, bary = ancoras
                r = m.V[lin] - G.phong(ro.R, self._normais_cabeca(ro), tri, bary)
                r_alto = r - G.filtro_gaussiano(m.V[lin], r, SIGMA_DETALHE)
            self.secoes[(m.mat, m.lod)] = dict(W=W, aten=aten, uv_ok=uv_ok, W_uv=W_uv, ancoras=ancoras,
                                               grupos=grupos, r_alto=r_alto)

    @staticmethod
    def _normais_cabeca(ro):
        N = np.zeros_like(ro.R)
        o = ro.offset[('head_mat', 0)]
        n = len(ro.cena.malha('head_mat', 0).V)
        N[o:o + n] = G.normais_vertice(ro.R[o:o + n], ro.T[('head_mat', 0)] - o)
        return N

    @staticmethod
    def _montar(trip, n, ncol):
        r = np.concatenate([np.asarray(a, int) for a, _, _ in trip]) if trip else np.zeros(0, int)
        c = np.concatenate([np.asarray(b, int) for _, b, _ in trip]) if trip else np.zeros(0, int)
        w = np.concatenate([np.asarray(x, float) for _, _, x in trip]) if trip else np.zeros(0)
        W = G.matriz_esparsa(r, c, w, n, ncol)
        s = np.asarray(W.sum(1)).ravel()
        return W.multiply(1.0 / np.where(s > 1e-12, s, 1.0)[:, None]).tocsr()

    @staticmethod
    def _suave(destino_idx, P, R, fonte_idx, k=16):
        idx, w = G.pesos_suaves(R[fonte_idx], P, k=k)
        return np.repeat(destino_idx, idx.shape[1]), fonte_idx[idx].ravel(), w.ravel()

    @staticmethod
    def _harmonico(W, m, idx, anc):
        """linhas dos vértices livres da ilha = combinação harmônica das linhas ancoradas"""
        from scipy.sparse.linalg import splu
        local = {v: i for i, v in enumerate(idx)}
        Tl = m.T[np.isin(m.T[:, 0], idx)]
        Tl = np.vectorize(local.get)(Tl)
        L = G.laplaciano(Tl, len(idx), m.V[idx]).tocsc()
        F, C = np.where(~anc)[0], np.where(anc)[0]
        H = -splu(L[F][:, F].tocsc()).solve(L[F][:, C].toarray())
        H[np.abs(H) < 1e-6] = 0
        from scipy.sparse import csr_matrix
        Wf = csr_matrix(H) @ W[idx[C]]
        W = W.tolil()
        for k, v in enumerate(idx[F]):
            W[v] = Wf[k]
        W = W.tocsr()
        s = np.asarray(W.sum(1)).ravel()
        return W.multiply(1.0 / np.where(s > 1e-12, s, 1.0)[:, None]).tocsr()

    @staticmethod
    def _media_linhas(W, grupos):
        """substitui as linhas de cada grupo pela média do grupo"""
        if not grupos:
            return W
        n = W.shape[0]
        r, c, v = [np.arange(n)], [np.arange(n)], [np.ones(n)]
        mascara = np.ones(n, bool)
        for g in grupos:
            g = np.asarray(g)
            mascara[g] = False
            r.append(np.repeat(g, len(g)))
            c.append(np.tile(g, len(g)))
            v.append(np.full(len(g) ** 2, 1.0 / len(g)))
        r[0], c[0], v[0] = r[0][mascara], c[0][mascara], v[0][mascara]
        A = G.matriz_esparsa(np.concatenate(r), np.concatenate(c), np.concatenate(v), n, n)
        return (A @ W).tocsr()


_cache = {}


def referencia(jogo):
    if jogo not in _cache:
        _cache[jogo] = Referencia(jogo)
    return _cache[jogo]


def mapa(origem, destino):
    chave = ('mapa', origem, destino)
    if chave not in _cache:
        _cache[chave] = Mapa(referencia(origem), referencia(destino))
    return _cache[chave]


# ----------------------------------------------------------------------------
# correspondência entre a face de entrada e a referência do mesmo jogo

def _vizinhanca(T, n):
    viz = [set() for _ in range(n)]
    for a, b, c in T:
        viz[a].update((b, c))
        viz[b].update((a, c))
        viz[c].update((a, b))
    return viz


def casar_por_uv(ref, ent, tol=2e-4):
    """índice do vértice de 'ent' correspondente a cada vértice de 'ref' (-1 se não achar)"""
    if ent.uv0 is None or ref.uv0 is None:
        return np.full(len(ref.V), -1)
    arv = cKDTree(ent.uv0)
    k = min(6, len(ent.V))
    d, j = arv.query(ref.uv0, k=k)
    d, j = d.reshape(len(ref.V), -1), j.reshape(len(ref.V), -1)
    cand = [list(j[i][d[i] < tol]) for i in range(len(ref.V))]
    mapa_ = np.full(len(ref.V), -1)
    usado = np.zeros(len(ent.V), bool)
    for i, c in enumerate(cand):
        if len(c) == 1:
            mapa_[i] = c[0]
    # mais de um candidato (ex.: comissura dos lábios): decide pela vizinhança
    amb = [i for i, c in enumerate(cand) if len(c) > 1]
    if amb:
        usado[mapa_[mapa_ >= 0]] = True
        vr = _vizinhanca(ref.T, len(ref.V))
        ve = _vizinhanca(ent.T, len(ent.V))
        for _ in range(3):
            for i in amb:
                if mapa_[i] >= 0:
                    continue
                viz_mapeados = {mapa_[v] for v in vr[i] if mapa_[v] >= 0}
                livres = [c for c in cand[i] if not usado[c]]
                if not livres:
                    continue
                notas = [len(viz_mapeados & ve[c]) for c in livres]
                melhor = int(np.argmax(notas))
                if notas[melhor] > 0 and notas.count(notas[melhor]) == 1:
                    mapa_[i] = livres[melhor]
                    usado[livres[melhor]] = True
    # o mesmo vértice de entrada não pode servir dois da referência
    vals, cnt = np.unique(mapa_[mapa_ >= 0], return_counts=True)
    for v in vals[cnt > 1]:
        mapa_[mapa_ == v] = -1
    return mapa_


def casar_aproximado(ref, ent):
    """mesma topologia com UVs um pouco diferentes (ex.: morph de UV do FC 27) e outra ordem:
    vizinho mútuo mais próximo na UV, validado pelos triângulos"""
    if ent.uv0 is None or ref.uv0 is None:
        return np.full(len(ref.V), -1)
    _, j = cKDTree(ent.uv0).query(ref.uv0)
    _, i_back = cKDTree(ref.uv0).query(ent.uv0)
    mp = np.where(i_back[j] == np.arange(len(ref.V)), j, -1)
    tri_ent = set(map(tuple, np.sort(ent.T, 1)))
    Tm = mp[ref.T]
    valido = (Tm >= 0).all(1)
    ok_tri = np.array([valido[k] and tuple(sorted(Tm[k])) in tri_ent for k in range(len(Tm))])
    bom = np.zeros(len(ref.V), bool)
    bom[ref.T[ok_tri].ravel()] = True
    return np.where(bom, mp, -1)


def _meias_arestas(T):
    """aresta orientada (a,b) -> terceiro vértice do triângulo; None se não for variedade"""
    he = {}
    for a, b, c in T:
        for x, y, z in ((a, b, c), (b, c, a), (c, a, b)):
            k = (int(x), int(y))
            he[k] = None if k in he else int(z)
    return he


def casar_por_conectividade(ref, ent, semente):
    """mesma malha com outra ordem de vértices/triângulos: a partir de um triângulo-semente,
    percorre a malha aresta por aresta. Só aceita a semente se cobrir a ilha inteira sem conflito."""
    he_r = _meias_arestas(ref.T)
    he_e = _meias_arestas(ent.T)
    he_e_inv = _meias_arestas(ent.T[:, ::-1])
    lab = G.ilhas(ref.T, len(ref.V))
    mp = np.full(len(ref.V), -1)
    usado_global = np.zeros(len(ent.V), bool)

    def propagar(tri, tri2, he2):
        m = dict(zip(map(int, tri), map(int, tri2)))
        usados = set(m.values())
        pilha = [(int(tri[0]), int(tri[1])), (int(tri[1]), int(tri[2])), (int(tri[2]), int(tri[0]))]
        visto = set()
        while pilha:
            x, y = pilha.pop()
            for (p, q) in ((x, y), (y, x)):
                if (p, q) in visto:
                    continue
                visto.add((p, q))
                z, z2 = he_r.get((p, q)), he2.get((m[p], m[q]))
                if z is None and z2 is None:
                    continue
                if z is None or z2 is None:
                    return None
                if z in m:
                    if m[z] != z2:
                        return None
                    continue
                if z2 in usados or usado_global[z2]:
                    return None
                m[z] = z2
                usados.add(z2)
                pilha.extend([(q, z), (z, p)])
        return m

    for il in range(lab.max() + 1):
        vert_il = np.where(lab == il)[0]
        tris = ref.T[lab[ref.T[:, 0]] == il]
        cand = [t for t in tris if (semente[t] >= 0).all()]
        aceito = None
        for t in cand[:60]:
            t2 = semente[t]
            for he2 in (he_e, he_e_inv):
                if he2.get((int(t2[0]), int(t2[1]))) != int(t2[2]):
                    continue
                m = propagar(t, t2, he2)
                if m is not None and len(m) == len(vert_il):
                    aceito = m
                    break
            if aceito:
                break
        if aceito:
            for k, v in aceito.items():
                mp[k] = v
                usado_global[v] = True
    return mp


def completar_por_topologia(ref, ent, mp):
    """a partir dos vértices já casados, casa os vizinhos pela malha: o candidato da entrada é o
    vizinho comum dos correspondentes dos vizinhos (resolve ordem diferente com UV alterada)"""
    mp = mp.copy()
    vr = _vizinhanca(ref.T, len(ref.V))
    ve = _vizinhanca(ent.T, len(ent.V))
    usado = np.zeros(len(ent.V), bool)
    usado[mp[mp >= 0]] = True
    pend = set(np.where(mp < 0)[0])
    while pend:
        progresso = []
        for r in pend:
            viz = [mp[v] for v in vr[r] if mp[v] >= 0]
            if len(viz) < 2:
                continue
            cont = {}
            for e in viz:
                for c in ve[e]:
                    if not usado[c]:
                        cont[c] = cont.get(c, 0) + 1
            if not cont:
                continue
            melhor = max(cont.values())
            cands = [c for c, k in cont.items() if k == melhor]
            if melhor >= 2 and len(cands) == 1:
                progresso.append((r, cands[0], melhor))
        if not progresso:
            break
        progresso.sort(key=lambda x: -x[2])
        for r, c, _ in progresso:
            if not usado[c] and mp[r] < 0:
                mp[r] = c
                usado[c] = True
                pend.discard(r)
    return mp


def posicoes_por_uv(ref, ent):
    """posição de 'ent' no ponto com a mesma UV de cada vértice de 'ref'"""
    loc = G.LocalizadorUV(ent.uv0, ent.T)
    t, b, dentro = loc.consulta(ref.uv0)
    return (b[:, :, None] * ent.V[ent.T[t]]).sum(1), dentro


def _por_conectividade(ref, ent):
    """mesma malha (contagens iguais) em outra ordem: casamento exato, sementes pela UV"""
    if len(ref.V) != len(ent.V) or len(ref.T) != len(ent.T) or ent.uv0 is None:
        return None
    for semente in (casar_por_uv(ref, ent), casar_aproximado(ref, ent)):
        mpc = casar_por_conectividade(ref, ent, semente)
        if (mpc >= 0).all():
            return mpc
    return None


def correspondencia(ref, ent, avisos, nome):
    """posições da entrada para cada vértice da seção de referência (NaN = sem dado)"""
    if len(ref.V) == len(ent.V) and np.array_equal(ref.T, ent.T):
        return ent.V.copy(), 'mesma topologia', ent.uv0
    mpc = _por_conectividade(ref, ent)
    if mpc is not None:
        return ent.V[mpc], 'mesma malha em outra ordem (casada pela conectividade)', ent.uv0[mpc]
    mp = casar_por_uv(ref, ent)
    frac = (mp >= 0).mean()
    if frac < 0.5 and ent.uv0 is not None:
        # alguns programas invertem o V da UV
        ent_inv = type('M', (), {})()
        ent_inv.uv0 = ent.uv0 * [1, -1] + [0, 1]
        ent_inv.V, ent_inv.T = ent.V, ent.T
        mp2 = casar_por_uv(ref, ent_inv)
        if (mp2 >= 0).mean() > frac:
            mp, frac = mp2, (mp2 >= 0).mean()
            ent = ent_inv
    if frac < 0.98:
        mp3 = casar_aproximado(ref, ent)
        livre = ~np.isin(mp3, mp[mp >= 0])
        junta = np.where((mp < 0) & (mp3 >= 0) & livre, mp3, mp)
        vals, cnt = np.unique(junta[junta >= 0], return_counts=True)
        junta[np.isin(junta, vals[cnt > 1])] = -1
        if (junta >= 0).mean() > frac:
            mp, frac = junta, (junta >= 0).mean()
    if 0.2 <= frac < 1.0:
        mp = completar_por_topologia(ref, ent, mp)
        frac = (mp >= 0).mean()
    P = np.full((len(ref.V), 3), np.nan)
    uv = None
    if frac >= 0.9:
        P[mp >= 0] = ent.V[mp[mp >= 0]]
        if ent.uv0 is not None:
            uv = np.full((len(ref.V), 2), np.nan)
            uv[mp >= 0] = ent.uv0[mp[mp >= 0]]
        falta = mp < 0
        if falta.any():
            Q, dentro = posicoes_por_uv(ref, ent)
            P[falta & dentro] = Q[falta & dentro]
        metodo = 'casada pela UV (%d de %d vértices)' % ((mp >= 0).sum(), len(ref.V))
    else:
        Q, dentro = posicoes_por_uv(ref, ent)
        P[dentro] = Q[dentro]
        metodo = 'interpolada pela UV (topologia diferente)'
        avisos.append('%s: topologia diferente da referência; usada interpolação pela UV' % nome)
    return P, metodo, uv


def correspondencia_olhos(ref, ent, avisos):
    """olhos: casa pela UV; se o facemaker trocou os olhos, ajusta cada olho por similaridade (ICP)"""
    if len(ref.V) == len(ent.V) and np.array_equal(ref.T, ent.T):
        return ent.V.copy(), 'mesma topologia'
    mpc = _por_conectividade(ref, ent)
    if mpc is not None:
        return ent.V[mpc], 'mesma malha em outra ordem (casados pela conectividade)'
    mp = casar_por_uv(ref, ent)
    if (mp >= 0).all():
        return ent.V[mp], 'casados pela UV'
    lr = G.ilhas(ref.T, len(ref.V))
    le = G.ilhas(ent.T, len(ent.V))
    P = np.full((len(ref.V), 3), np.nan)
    partes = []
    for il in range(lr.max() + 1):
        mr = lr == il
        cx = ref.V[mr, 0].mean()
        cand = [j for j in range(le.max() + 1) if np.sign(ent.V[le == j, 0].mean()) == np.sign(cx)]
        if not cand:
            continue
        me = le == max(cand, key=lambda j: (le == j).sum())
        Xr, Xe = ref.V[mr], ent.V[me]
        # chute inicial: centróide + escala pela caixa
        s = np.ptp(Xe, 0).mean() / max(np.ptp(Xr, 0).mean(), 1e-9)
        R, t = np.eye(3), Xe.mean(0) - s * Xr.mean(0)
        arv = cKDTree(Xe)
        for _ in range(30):
            Y = (s * Xr @ R.T) + t
            _, j = arv.query(Y)
            s, R, t = G.umeyama(Xr, Xe[j])
        Y = (s * Xr @ R.T) + t
        P[mr] = Y
        partes.append('escala %.3f' % s)
    if np.isnan(P).any():
        avisos.append('olhos: não foi possível ajustar um dos olhos; ele segue a pálpebra')
    return P, 'olhos ajustados por similaridade (%s)' % ', '.join(partes)


# ----------------------------------------------------------------------------
# conversão

def _normalizar_escala(cena_ent, ref, avisos):
    cab_e = cena_ent.malha('head_mat', 0)
    cab_r = ref.cena.malha('head_mat', 0)
    h_e = np.ptp(cab_e.V[:, 1])
    h_r = np.ptp(cab_r.V[:, 1])
    fator = 1.0
    if h_e > 0 and not 0.5 < h_e / h_r < 2:
        fator = 10.0 ** round(np.log10(h_r / h_e))
        avisos.append('escala da entrada corrigida por %g' % fator)
    for m in cena_ent.malhas:
        m.V = m.V * fator
    centro_e = (cab_e.V.min(0) + cab_e.V.max(0)) / 2
    centro_r = (cab_r.V.min(0) + cab_r.V.max(0)) / 2
    if np.linalg.norm(centro_e - centro_r) > 0.05:
        avisos.append('a cabeça de entrada está deslocada %.1f cm da posição padrão'
                      % (100 * np.linalg.norm(centro_e - centro_r)))


def _id_jogador(caminho, cena=None):
    """(id, variação, ...) do jogador: nome do arquivo, nome interno da malha ou pasta do FET"""
    base = os.path.splitext(os.path.basename(caminho))[0]
    m = re.search(r'(?:head|headmorphpreset)_(\d+)_(\d+)_(\d+)', base, re.I)
    if m:
        return m.group(1), m.group(2), m.group(3)
    for mal in (cena.malhas if cena is not None else []):
        m = re.fullmatch(r'head_(\d+)_(\d+)_(\d+)_mesh', mal.mesh_name, re.I)
        if m:
            return m.group(1), m.group(2), m.group(3)
    var = '0'
    for parte in reversed(os.path.normpath(os.path.abspath(caminho)).split(os.sep)[:-1]):
        m = re.fullmatch(r'var_(\d+)', parte, re.I)
        if m:
            var = m.group(1)
            continue
        m = re.fullmatch(r'(?:player_)?(\d+)', parte)
        if m and len(m.group(1)) >= 2:
            return m.group(1), var, '0'
    return None


def nome_saida(caminho, destino, cena=None):
    """nome que o FET usa no jogo de destino (head_<id>_0_0_mesh / headmorphpreset_<id>_0_0);
    sem ID no nome do arquivo nem na malha, mantém o nome com o sufixo do jogo"""
    base, ext = os.path.splitext(os.path.basename(caminho))
    m = re.fullmatch(r'(?:head_(\d+)_(\d+)_(\d+)_mesh|headmorphpreset_(\d+)_(\d+)_(\d+))', base, re.I)
    g = [x for x in m.groups() if x is not None] if m else None
    if g is None and cena is not None:
        for mal in cena.malhas:
            mm = re.fullmatch(r'head_(\d+)_(\d+)_(\d+)_mesh', mal.mesh_name, re.I)
            if mm:
                g = list(mm.groups())
                break
    if g:
        if destino == 'fc27':
            return 'headmorphpreset_%s_%s_%s.fbx' % tuple(g)
        return 'head_%s_%s_%s_mesh.fbx' % tuple(g)
    return '%s_%s%s' % (base, destino.upper(), ext)


def converter(caminho_entrada, caminho_saida=None, destino=None, layout_textura='fc26'):
    """converte um FBX de cabeça; devolve dict com o relatório"""
    avisos = []
    cena = Cena(caminho_entrada)
    origem = detectar_jogo(cena)
    if origem is None:
        raise ErroConversao('nenhuma malha head_mat com nome no padrão "<material>:<malha>_lod.NNN"')
    if destino is None:
        destino = 'fc27' if origem == 'fc26' else 'fc26'
    if origem == destino:
        raise ErroConversao('o arquivo já está no formato %s' % origem.upper())
    ref_o, ref_d = referencia(origem), referencia(destino)
    mp = mapa(origem, destino)
    _normalizar_escala(cena, ref_o, avisos)

    # 1. posições da entrada em cada vértice do campo da referência de origem
    P = np.full((ref_o.n_campo, 3), np.nan)
    UVc = ref_o.UV.copy()      # UV da entrada no campo (só a da cabeça é usada)
    metodos = {}
    for chave, mref in ref_o.campo:
        ment = cena.malha(*chave)
        off = ref_o.offset[chave]
        if ment is None:
            avisos.append('%s LOD%d ausente na entrada; segue a pele ao redor' % chave)
            continue
        if chave[0] == 'eyes_mat':
            Pi, met = correspondencia_olhos(mref, ment, avisos)
            uvi = None
        else:
            Pi, met, uvi = correspondencia(mref, ment, avisos, '%s LOD%d' % chave)
        metodos['%s LOD%d' % chave] = met
        P[off:off + len(mref.V)] = Pi
        if uvi is not None:
            ok = ~np.isnan(uvi).any(1)
            UVc[off:off + len(mref.V)][ok] = uvi[ok]
    D = P - ref_o.R
    falta = np.isnan(D).any(1)
    if falta.all():
        raise ErroConversao('não foi possível casar a malha de entrada com a referência')
    if falta.any():
        idx, w = G.pesos_suaves(ref_o.R[~falta], ref_o.R[falta], k=8)
        D[falta] = (w[:, :, None] * D[~falta][idx]).sum(1)

    # normais suaves da pele (entrada e referência) para a interpolação curva
    Tcab = ref_o.T[('head_mat', 0)]
    Xc = ref_o.R + D
    Nx_campo = np.zeros_like(Xc)
    Nr_campo = np.zeros_like(Xc)
    sl = slice(ref_o.offset[('head_mat', 0)], ref_o.offset[('head_mat', 0)] + len(ref_o.cena.malha('head_mat', 0).V))
    Tloc = Tcab - sl.start
    Nx_campo[sl] = G.normais_vertice(Xc[sl], Tloc)
    Nr_campo[sl] = G.normais_vertice(ref_o.R[sl], Tloc)

    # 2. modelo do jogo de destino com as novas posições
    cena_d = Cena(os.path.join(PASTA_REF, REFERENCIAS[destino]))
    if any(m.dividida for m in cena_d.malhas):
        raise ErroConversao('modelo de referência %s inválido (UV por canto)' % REFERENCIAS[destino])
    desloc_max = 0.0
    for m in cena_d.malhas:
        sec = mp.secoes.get((m.mat, m.lod))
        if sec is None:
            continue
        Dm = np.asarray(sec['W'] @ D)
        if sec['ancoras'] is not None and len(sec['ancoras'][0]):
            # pele: diferença entre as superfícies curvas (Phong) da entrada e da referência,
            # para a malha mais densa não reproduzir as facetas da malha de origem
            linhas, tri, bary = sec['ancoras']
            Dm[linhas] = G.phong(Xc, Nx_campo, tri, bary) - G.phong(ref_o.R, Nr_campo, tri, bary) - sec['r_alto']
            for g in sec['grupos']:
                Dm[g] = Dm[g].mean(0)
        Dm = Dm * sec['aten'][:, None]
        Xw = m.V + Dm
        desloc_max = max(desloc_max, float(np.abs(Dm).max()))
        geo = cena_d.objs[m.geom_id]
        M = cena_d.matriz_global(m.model_id) @ cena_d.matriz_geometrica(m.model_id)
        Minv = np.linalg.inv(M)
        Xl = Xw @ Minv[:3, :3].T + Minv[:3, 3]
        geo.find('Vertices').props[0].set(Xl.ravel())
        # normais/tangentes: gira as do modelo pela mudança de forma
        Nr = G.normais_vertice(m.V, m.T)
        Nx = G.normais_vertice(Xw, m.T)
        Rm = G.rotacao_minima(Nr, Nx)
        for le_nome, dado in (('LayerElementNormal', 'Normals'), ('LayerElementBinormal', 'Binormals'),
                              ('LayerElementTangent', 'Tangents')):
            for le in geo.findall(le_nome):
                arr = le.find(dado)
                mit = le.find('MappingInformationType').props[0].v
                if arr is None or mit not in ('ByVertice', 'ByVertex'):
                    continue
                A = np.asarray(arr.props[0].v, float).reshape(-1, 3)
                if len(A) != len(m.V):
                    continue
                A = np.einsum('nij,nj->ni', Rm, A)
                A /= np.maximum(np.linalg.norm(A, axis=1), 1e-12)[:, None]
                arr.props[0].set(A.ravel())
        # UV0 da pele: segue o layout de textura escolhido. Se for o do jogo de origem, cada vértice
        # recebe a UV do ponto correspondente na face de entrada (a textura antiga serve direto);
        # se for o do jogo de destino, fica a UV padrão do modelo.
        if layout_textura == origem and m.mat == 'head_mat' and sec['W_uv'] is not None and sec['uv_ok'].any():
            uv_novo = np.asarray(sec['W_uv'] @ UVc)
            for le in geo.findall('LayerElementUV'):
                if le.props[0].v != 0:
                    continue
                mit = le.find('MappingInformationType').props[0].v
                rit = le.find('ReferenceInformationType').props[0].v
                arr = le.find('UV')
                if mit not in ('ByVertice', 'ByVertex') or rit != 'Direct':
                    continue
                U = np.asarray(arr.props[0].v, float).reshape(-1, 2)
                usar = sec['uv_ok']
                U[usar] = uv_novo[usar]
                arr.props[0].set(U.ravel())

    # nome da malha no FC 26 leva o ID do jogador
    if destino == 'fc26':
        ident = _id_jogador(caminho_entrada, cena)
        if ident:
            novo = 'head_%s_%s_%s_mesh' % ident
            for o in cena_d.objs.values():
                if o.name == 'Model' and len(o.props) > 1 and o.props[1].t == 'S' and 'head_158023_0_0_mesh' in o.props[1].v:
                    o.props[1].set(o.props[1].v.replace('head_158023_0_0_mesh', novo))
        else:
            avisos.append('ID do jogador não encontrado no nome do arquivo/pasta; a malha ficou como head_158023_0_0_mesh')

    if caminho_saida is None:
        caminho_saida = os.path.join(os.path.dirname(caminho_entrada), nome_saida(caminho_entrada, destino))
    os.makedirs(os.path.dirname(os.path.abspath(caminho_saida)), exist_ok=True)
    write_fbx(cena_d.fbx, caminho_saida)
    return dict(origem=origem, destino=destino, saida=caminho_saida, metodos=metodos, avisos=avisos,
                diferenca_max_cm=100 * desloc_max)
