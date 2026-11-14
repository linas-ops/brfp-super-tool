"""Um estádio do PES 2021 (Fox Engine) numa pasta: onde ficam os arquivos, os modelos, as peças e as texturas.

Todos os estádios do PES 2021 têm o mesmo formato (a pasta do mod, com Asset\\model\\bg\\st<NNN>):
  #Win\\st<NNN>.fpk/.fpkd           os modelos do estádio (scenes\\*.fmdl) e a cena que os coloca (StadiumModel)
  tv\\#Win\\tv_st<NNN>.fpk           as telas do telão
  audi\\#Win\\audiarea_st<NNN>.fpk   as áreas da torcida (audiarea.bin) e audi\\sourceimages\\au_seat.png (cores das cadeiras)
  effect\\#Win\\effect_st<NNN>_df/_nf.fpk   os brilhos das lâmpadas, de dia e de noite (locstar_*.model)
  sourceimages\\tga\\#windx11\\*.ftex   as texturas (o modelo aponta para /Assets/pes16/.../x.tga)
Os outros pacotes (placas, figurantes, bandeiras, gramado, luzes, variações de dia e de noite com vidros e brilhos) não
entram: o FC 27 tem os próprios. Unidades em metros, Y para cima, sistema de mão direita, como o FC 27; só o lado dos
bancos pode ser o contrário (o PES aceita os bancos em +Z), e aí o estádio gira meia volta (motor/pes21/analise.py).
"""
from __future__ import annotations
import re
from pathlib import Path

import numpy as np

from . import fmdl, fox2, fpk, ftex

RAIZ_JOGO = re.compile(r'^/?assets/[^/]+/', re.I)  # /Assets/pes16/ no começo dos caminhos do jogo
LIMITE = 400.0  # triângulos mais longe que isso do centro do campo são sobras que o autor escondeu (m)


def localizar(pasta):
    """(pasta Asset, 'st<NNN>') de uma pasta de estádio do PES 2021."""
    p = Path(pasta)
    cands = [p / 'Asset' / 'model' / 'bg', p / 'model' / 'bg', p / 'bg', p, p.parent]
    achados = []
    for bg in cands:
        if not bg.is_dir():
            continue
        for d in sorted(bg.iterdir()):
            if d.is_dir() and re.fullmatch(r'st\d+', d.name, re.I) and (d / '#Win' / f'{d.name}.fpk').is_file():
                if bg == p.parent and d != p:
                    continue
                achados.append(d)
        if achados:
            break
    if not achados:
        raise ValueError('não achei Asset\\model\\bg\\st<número>\\#Win\\st<número>.fpk nessa pasta')
    if len(achados) > 1:
        raise ValueError('a pasta tem mais de um estádio: ' + ', '.join(d.name for d in achados))
    d = achados[0]
    return d.parent.parent.parent, d.name.lower()


def _matriz(escala, quat, trans):
    x, y, z, w = quat
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]], np.float64)
    m = np.eye(4)
    m[:3, :3] = r * np.array(escala, np.float64)[None, :]
    m[:3, 3] = trans
    return m


def colocacoes(cena):
    """{caminho do modelo em minúsculas: matriz 4x4} das entidades de uma cena fox2 que colocam modelos."""
    out = {}
    for e in cena.entidades:
        arq = e.um('modelFile')
        if not arq:
            continue
        t = cena.ref(e.um('transform'))
        if t is None:
            out[arq.lower()] = np.eye(4)
            continue
        out[arq.lower()] = _matriz(t.um('transform_scale', (1, 1, 1)), t.um('transform_rotation_quat', (0, 0, 0, 1)),
                                   t.um('transform_translation', (0, 0, 0)))
    return out


class Estadio:
    def __init__(self, pasta):
        self.asset, self.sid = localizar(pasta)
        self.pasta = Path(pasta)
        self.bg = self.asset / 'model' / 'bg' / self.sid
        self._modelos = None
        self._pecas = None
        self._tex = {}

    # ------------------------------------------------------------ arquivos
    def arquivos(self):
        s = self.sid
        f = dict(modelo=self.bg / '#Win' / f'{s}.fpk', cena=self.bg / '#Win' / f'{s}.fpkd', telao=self.bg / 'tv' / '#Win' / f'tv_{s}.fpk',
                 cena_telao=self.bg / 'tv' / '#Win' / f'tv_{s}.fpkd', torcida=self.bg / 'audi' / '#Win' / f'audiarea_{s}.fpk',
                 cadeiras=self.bg / 'audi' / 'sourceimages' / 'au_seat.png',
                 brilhos_dia=self.bg / 'effect' / '#Win' / f'effect_{s}_df.fpk', brilhos_noite=self.bg / 'effect' / '#Win' / f'effect_{s}_nf.fpk')
        return f

    def _cena(self, arq):
        out = {}
        if arq.is_file():
            for nome, dados in fpk.Fpk(arq).itens():
                if nome.lower().endswith('.fox2'):
                    out.update(colocacoes(fox2.Fox2(dados, nome)))
        return out

    def modelos(self):
        """Os modelos do estádio e do telão: [dict(nome, caminho, origem, fmdl, matriz)], na ordem dos pacotes."""
        if self._modelos is None:
            f = self.arquivos()
            out = []
            for origem, pacote, cena in (('estadio', f['modelo'], f['cena']), ('telao', f['telao'], f['cena_telao'])):
                if not pacote.is_file():
                    continue
                onde = self._cena(cena)
                for nome, dados in fpk.Fpk(pacote).itens():
                    if not nome.lower().endswith('.fmdl'):
                        continue
                    out.append(dict(nome=nome.rsplit('/', 1)[-1][:-5], caminho=nome, origem=origem, fmdl=fmdl.Fmdl(dados, nome),
                                    matriz=onde.get(nome.lower(), np.eye(4))))
            if not any(m['origem'] == 'estadio' for m in out):
                raise ValueError(f'o pacote {f["modelo"].name} não tem modelos (.fmdl)')
            self._modelos = out
        return self._modelos

    def pecas(self):
        """Uma peça por malha de cada modelo, numerada na ordem dos pacotes: dict(prim, modelo, malha)."""
        if self._pecas is None:
            out = []
            for mod in self.modelos():
                for m in mod['fmdl'].malhas():
                    out.append(dict(prim=len(out), modelo=mod, malha=m))
            self._pecas = out
        return self._pecas

    # ------------------------------------------------------------ geometria
    def geometria(self, peca):
        """(posições (n, 3), normais (n, 3) ou None, UV0 (n, 2), triângulos (t, 3), triângulos tirados por estarem longe)
        de uma peça, em metros, já no lugar em que a cena põe o modelo."""
        fm, m, mat = peca['modelo']['fmdl'], peca['malha'], peca['modelo']['matriz']
        a = fm.vertices(m)
        if 'pos' not in a or m['indices'] % 3:
            raise ValueError(f"a peça {peca['prim']} não é uma lista de triângulos com posições")
        P = a['pos'].astype(np.float64)
        N = a['normal'][:, :3].astype(np.float64) if 'normal' in a else None
        U = a['uv0'].astype(np.float64) if 'uv0' in a else np.zeros((len(P), 2))
        idx = fm.indices(m).reshape(-1, 3)
        if len(idx) and idx.max() >= len(P):
            raise ValueError(f"a peça {peca['prim']} tem índices fora dos vértices")
        if not np.allclose(mat, np.eye(4)):
            P = P @ mat[:3, :3].T + mat[:3, 3]
            if N is not None:
                N = N @ np.linalg.inv(mat[:3, :3])
                N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
        longe = (np.abs(P) > LIMITE).any(1) | ~np.isfinite(P).all(1)
        fora = longe[idx].any(1)
        return P, N, U, idx[~fora], int(fora.sum())

    # ------------------------------------------------------------ texturas
    def arquivo_textura(self, caminho):
        """O .ftex de um caminho de textura do modelo (/Assets/pes16/.../x.tga), ou None se a pasta não o tem."""
        c = RAIZ_JOGO.sub('', caminho.replace('\\', '/')).lstrip('/')
        if not c:
            return None
        rel = Path(c)
        for f in (self.asset / rel.parent / '#windx11' / (rel.stem + '.ftex'), self.asset / rel.parent / (rel.stem + '.ftex')):
            if f.is_file():
                return f
        return None

    def textura(self, caminho):
        """Ftex aberto (guardado) de um caminho de textura do modelo, ou None."""
        k = caminho.lower()
        if k not in self._tex:
            f = self.arquivo_textura(caminho)
            try:
                self._tex[k] = ftex.Ftex(f) if f else None
            except (OSError, ValueError):
                self._tex[k] = None
        return self._tex[k]


def textura_de_cor(material):
    """O caminho da textura de cor de um material do PES (o papel dela muda com o shader), ou ''."""
    t = material['texturas']
    for papel in ('Base_Tex_SRGB', 'Base_Tex_LIN', 'Base_Tex_SRGB_1', 'Layer_Tex_SRGB'):
        if t.get(papel):
            return t[papel]
    for papel, cam in t.items():
        if 'base' in papel.lower() and cam:
            return cam
    return ''
