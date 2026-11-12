"""Leitor do FBMorphBlends (RES 0x675fa1b1) do FC 27: deltas de posição ou de UV por vértice, por LOD.

Layout (versão 2), tudo little-endian:
  u32 versão, u32 n_lods, u32 ?, u32 ?, depois 11 offsets u64 (seções)
  seção 0: u32[n_lods]   vértices por LOD
  seção 1: u32[n_lods]   floats por LOD
  seção 2: u32[n_lods]   quantos vértices avulsos por LOD
  seção 3: u32[n_lods]   quantas faixas (início, tamanho) por LOD
  seções 4 a 6: somas acumuladas das seções 1 a 3
  seção 7: hash
  seção 8: u32[]  vértices avulsos (todos os LODs)
  seção 9: (u32 início, u32 tamanho)[] faixas
  seção 10: float32[] deltas, xyz intercalado, na ordem: avulsos primeiro, depois as faixas

A ordem dos vértices de cada LOD é a das seções do FBX exportado pelo FET: head, eyes, teeth.
No morph de UV0 (só os olhos, LOD0 e LOD1) o V vem no sentido do jogo: no FBX do FET, UV = base + (du, -dv).
"""
import struct

import numpy as np

NVERTS = (13295, 4012, 1090, 323)


def ler(raw):
    """-> lista (um por LOD) de arrays densos n_vértices x k (zeros onde o vértice não mexe)"""
    versao, n_lods, _, _ = struct.unpack_from("<4I", raw, 0)
    if versao != 2 or not 1 <= n_lods <= 8:
        raise ValueError("FBMorphBlends de versão desconhecida (%d, %d LODs)" % (versao, n_lods))
    offs = struct.unpack_from("<11Q", raw, 16)

    def u(off, n):
        return np.frombuffer(raw, "<u4", n, off)
    nverts, nfloats, nav, nfx = u(offs[0], n_lods), u(offs[1], n_lods), u(offs[2], n_lods), u(offs[3], n_lods)
    acf, acav, acfx = u(offs[4], n_lods), u(offs[5], n_lods), u(offs[6], n_lods)
    avulsos = u(offs[8], int(nav.sum()))
    faixas = u(offs[9], int(nfx.sum()) * 2).reshape(-1, 2)
    dados = np.frombuffer(raw, "<f4", int(nfloats.sum()), offs[10])
    lods = []
    for l in range(n_lods):
        av = avulsos[acav[l]:acav[l] + nav[l]].astype(np.int64)
        fx = faixas[acfx[l]:acfx[l] + nfx[l]]
        idx_fx = np.concatenate([np.arange(s, s + n) for s, n in fx]) if len(fx) else np.zeros(0, np.int64)
        idx = np.concatenate([av, idx_fx])
        f = dados[acf[l]:acf[l] + nfloats[l]]
        k = len(f) // len(idx) if len(idx) else 3
        D = np.zeros((int(nverts[l]), k), np.float32)
        if len(idx):
            D[idx] = f.reshape(len(idx), k)
        lods.append(D)
    return lods
