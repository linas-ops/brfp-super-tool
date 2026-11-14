"""Lâmpadas de um estádio do PES 2021: os marcadores dos brilhos (LightBillboard) do pacote effect_st<NNN>_df/_nf.fpk.

O effect_config.xml do pacote lista os brilhos e o arquivo de marcadores de cada um (locator\\locstar_*.model). Um arquivo
desses ('MODEL') traz um bloco com u32 quantos, o nome em 8 bytes ('star') e uma matriz 3x4 de floats por marcador, por
linhas, com a posição na quarta coluna, em metros.
"""
from __future__ import annotations
import re
import struct

import numpy as np

from . import fpk

_NOME = re.compile(rb'[A-Za-z_][A-Za-z0-9_]{0,7}')


def marcadores(dados):
    """Posições (n, 3) dos marcadores de um arquivo .model de marcadores do PES."""
    b = bytes(dados)
    if b[:5] != b'MODEL':
        return np.zeros((0, 3))
    melhor = np.zeros((0, 3))
    for q in range(8, len(b) - 60, 4):
        n, = struct.unpack_from('<I', b, q)
        if not 0 < n <= 20000 or q + 12 + 48 * n > len(b):
            continue
        nome = b[q + 4:q + 12]
        m = _NOME.match(nome)
        if not m or nome[m.end():].strip(b'\0'):
            continue
        mat = np.frombuffer(b, '<f4', 12 * n, q + 12).reshape(n, 3, 4).astype(np.float64)
        if not np.isfinite(mat).all() or np.abs(mat[:, :, :3]).max() > 100 or np.abs(mat[:, :, 3]).max() > 2000:
            continue
        if (np.linalg.norm(mat[:, :, :3], axis=2) < 1e-3).any():
            continue
        if n > len(melhor):
            melhor = mat[:, :, 3]
    return melhor


def lampadas(pacote):
    """Posições (n, 3) das lâmpadas de um pacote de efeitos (os marcadores dos brilhos), sem repetidas."""
    pk = fpk.Fpk(pacote)
    xml = next((d for n, d in pk.itens() if n.lower().endswith('effect_config.xml')), b'').decode('utf8', 'replace')
    usados = set()
    for bloco in re.split(r'<setting\b', xml)[1:]:
        if not re.match(r'[^>]*type="LightBillboard"', bloco):
            continue
        for cam in re.findall(r'id="locatorPath"[^>]*value="([^"]+)"', bloco):
            usados.add(cam.lower())
    pts = []
    for nome, dados in pk.itens():
        if nome.lower().endswith('.model') and (not usados or nome.lower() in usados):
            p = marcadores(dados)
            if len(p):
                pts.append(p)
    if not pts:
        return np.zeros((0, 3))
    v = np.concatenate(pts)
    _, first = np.unique(np.round(v, 3), axis=0, return_index=True)
    return v[np.sort(first)]
