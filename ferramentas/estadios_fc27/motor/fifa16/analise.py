"""Análise de um estádio do FIFA 16 (pasta com data/sceneassets) e a receita sugerida para a conversão.

Todos os estádios do FIFA 16 têm o mesmo formato: stadium_<id>.rx3 (modelo), stadium_<id>_1/_3_textures.rx3 (dia e
noite), crowdplacement/crowd_<id>_1/_3.dat (torcida) e fx/glares_<id>_<v>.lnx (luzes). O modelo é dividido em camadas
(AdBoard, Alpha*, Banner_NoShadowCast, EnvironmentSkirt, Exterior, Jumbotron, MainStadium*, Pitch, SidelineProps, Sky),
o que dá a sugestão de cada peça: o que o FC 27 já tem (placas, gramado, céu e relógio que o FIFA 16 preenchia na hora
do jogo) sai; os lugares em que o FIFA 16 punha os banners dos times recebem os banners dos times do FC 27 (papel
"banner", que também serve para as faixas fixas do estádio, marcadas na interface); o resto entra como opaco ou alpha.
"""
from __future__ import annotations
import collections
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

import numpy as np

from . import bcn, rx3

PAPEIS = ('opaco', 'alpha', 'telao', 'grama', 'banner', 'descartar')
GRASS_TINT = [0.42, 0.62, 0.26]


def localizar(pasta):
    """(pasta sceneassets, id do FIFA 16) de uma pasta de estádio do FIFA 16."""
    p = Path(pasta)
    for cand in (p / 'data' / 'sceneassets', p / 'sceneassets', p):
        st = cand / 'stadium'
        if st.is_dir():
            ids = sorted({int(m.group(1)) for f in st.iterdir() for m in [re.fullmatch(r'stadium_(\d+)\.rx3', f.name, re.I)] if m})
            if len(ids) == 1:
                return cand, ids[0]
            if len(ids) > 1:
                raise ValueError('a pasta tem mais de um estádio: ' + ', '.join(map(str, ids)))
    raise ValueError('não achei data/sceneassets/stadium/stadium_<id>.rx3 nessa pasta')


def arquivos(sa, sid):
    st, cr, fx = sa / 'stadium', sa / 'crowdplacement', sa / 'fx'
    f = dict(modelo=st / f'stadium_{sid}.rx3', dia=st / f'stadium_{sid}_1_textures.rx3', noite=st / f'stadium_{sid}_3_textures.rx3',
             torcida=cr / f'crowd_{sid}_1.dat', torcida_noite=cr / f'crowd_{sid}_3.dat')
    f['glares'] = sorted(str(x) for x in fx.glob(f'glares_{sid}_*.lnx')) if fx.is_dir() else []
    return f


def sugestao(prim):
    """(papel, motivo) sugeridos pela camada e pelo shader do FIFA 16."""
    sh, layer = prim['material']['shader'].lower(), prim['layer']
    if layer == 'AdBoard' or sh.startswith('adboard'):
        return 'descartar', 'placas de publicidade do FIFA 16 (o FC 27 tem as próprias placas)'
    if sh == 'pitch':
        return 'descartar', 'gramado do campo (o FC 27 desenha o próprio)'
    if sh == 'sky' or layer == 'Sky':
        return 'descartar', 'céu (o FC 27 tem o próprio)'
    if sh.startswith('banner') or layer == 'Banner_NoShadowCast':
        return 'banner', f'{sh}: lugar dos banners dos times (o FIFA 16 os punha na hora do jogo); recebe os banners do FC 27'
    if sh.startswith('sclock'):
        return 'descartar', f'{sh}: dígito do relógio que o FIFA 16 desenhava na hora do jogo'
    if sh == 'simpleglow':
        return 'descartar', 'brilho (glow) do FIFA 16: o FC 27 usa os glares próprios'
    if sh == 'jumbotron':
        return 'telao', 'tela do telão (no FC 27 mostra a transmissão ao vivo)'
    if sh == 'pitchnoline':
        return 'grama', 'grama em volta do campo (tingida de verde, fica embaixo do gramado do FC 27)'
    if sh == 'diffusealpha':
        return 'alpha', 'alpha (transparência recortada)'
    return 'opaco', f'opaco ({sh})'


def _area_xz(P, idx):
    a, b, c = P[idx[:, 0]], P[idx[:, 1]], P[idx[:, 2]]
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 2] - a[:, 2]) - (c[:, 0] - a[:, 0]) * (b[:, 2] - a[:, 2]))


def _celulas(tri, celula):
    """Células (x, z) da grade cobertas pela projeção dos triângulos (centro dentro, mais vértices e centroides)."""
    cells = set()
    t2 = tri[:, :, [0, 2]]
    for x, z in np.floor(np.concatenate([t2.reshape(-1, 2), t2.mean(1)]) / celula).astype(int):
        cells.add((int(x), int(z)))
    for a, b, c in t2:
        lo = np.floor(np.minimum(np.minimum(a, b), c) / celula).astype(int)
        hi = np.floor(np.maximum(np.maximum(a, b), c) / celula).astype(int)
        if (hi - lo + 1).prod() <= 1:
            continue
        gx, gz = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
        px, pz = (gx.ravel() + 0.5) * celula, (gz.ravel() + 0.5) * celula
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (pz - c[1])) / d
        l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (pz - c[1])) / d
        dentro = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
        cells.update(zip(gx.ravel()[dentro].tolist(), gz.ravel()[dentro].tolist()))
    return cells


def camadas_do_chao(prims, papel, celula=0.5):
    """Ordem vertical das superfícies coplanares no chão (o FIFA 16 contava com a ordem de desenho; o FC 27 precisa de
    profundidades diferentes): quem fica dentro de outra superfície maior vai por cima. A grama vai 6 cm abaixo."""
    chao = {}
    for p in prims:
        i = p['index']
        if papel[i] not in ('opaco', 'alpha', 'grama'):
            continue
        a = rx3.decode_vertices(p)
        idx = rx3.decode_indices(p).reshape(-1, 3)
        P = a['p0'].astype(np.float64) / 100.0
        tri = P[idx]
        flat = (np.abs(tri[..., 1]) < 0.05).all(1)
        if flat.sum() < 1:
            continue
        cells = _celulas(tri[flat], celula)
        area = float(_area_xz(P, idx[flat]).sum())
        if area < 0.5:
            continue
        chao[i] = dict(cells=cells, area=area, alpha=papel[i] == 'alpha', grama=papel[i] == 'grama')
    dy = {}
    nivel = {}
    ordem = sorted((i for i in chao if not chao[i]['grama']), key=lambda i: (chao[i]['alpha'], -chao[i]['area'], i))
    for i in ordem:
        abaixo = [j for j in nivel if len(chao[i]['cells'] & chao[j]['cells']) >= max(2, 0.25 * min(len(chao[i]['cells']), len(chao[j]['cells'])))]
        nivel[i] = 1 + max((nivel[j] for j in abaixo), default=0)
    for i, n in nivel.items():
        dy[i] = round(min(0.002 * n, 0.012), 3)
    for i in chao:
        if chao[i]['grama']:
            dy[i] = -0.06
    return dy


def piso_em_volta(prims, papel, chao):
    """Peça do chão que envolve o campo sem cobri-lo (pista, borracha, concreto): até onde vai o gramado do FC 27.
    Entre as peças de chão opacas cujo contorno passa do campo nos quatro lados e que não têm vértices dentro do campo,
    a de maior área."""
    melhor, area_m = None, 0.0
    for p in prims:
        i = p['index']
        if i not in chao or papel[i] != 'opaco':
            continue
        a = rx3.decode_vertices(p)
        P = a['p0'].astype(np.float64) / 100.0
        chaoP = P[np.abs(P[:, 1]) < 0.05]
        if len(chaoP) < 8:
            continue
        lo, hi = chaoP.min(0), chaoP.max(0)
        if not (lo[0] < -53 and hi[0] > 53 and lo[2] < -34.5 and hi[2] > 34.5):
            continue
        dentro = (np.abs(chaoP[:, 0]) < 50) & (np.abs(chaoP[:, 2]) < 31)
        if dentro.mean() > 0.01:
            continue
        idx = rx3.decode_indices(p).reshape(-1, 3)
        area = float(_area_xz(P, idx).sum())
        if area > area_m:
            melhor, area_m = i, area
    return [melhor] if melhor is not None else []


def ler_torcida(path):
    b = Path(path).read_bytes()
    if b[:4] != b'CRWD':
        raise ValueError(f'{Path(path).name} não é CRWD')
    n = struct.unpack_from('<I', b, 6)[0]
    rec = np.frombuffer(b[10:10 + n * 32], np.uint8).reshape(n, 32)
    f = rec[:, :16].copy().view('<f4').reshape(n, 4).astype(np.float64)
    return dict(n=n, pos=f[:, :3] / 100.0, orient=f[:, 3], rec=rec)


def grupos_lnx(path):
    """{grupo: [vCenter em metros]} de um .lnx de glares (atributos em qualquer ordem)."""
    s = Path(path).read_text(encoding='latin1')
    out = {}
    for parte in re.split(r'<particleGroup\b', s)[1:]:
        m = re.match(r'[^>]*\bname="([^"]+)"', parte)
        if not m:
            continue
        pts = []
        for tag in re.findall(r'<parameter\b([^>]*)/?>', parte):
            at = dict(re.findall(r'(\w+)="([^"]*)"', tag))
            if at.get('name') == 'vCenter' and at.get('value', '').startswith('{'):
                pts.append(tuple(float(x) for x in at['value'].strip('{} ').split(',')))
        out[m.group(1)] = np.array(pts, np.float64).reshape(-1, 3) / 100.0
    return out


def grupo_das_lampadas(grupos):
    """O grupo com os brilhos das lâmpadas: fx_stadium_core (Morumbi), roof_core (Maracanã) ou outro *_core."""
    for nome in ('fx_stadium_core', 'roof_core'):
        if nome in grupos and len(grupos[nome]):
            return nome
    core = [g for g in grupos if g.lower().endswith('core') and len(grupos[g])]
    if core:
        return max(core, key=lambda g: len(grupos[g]))
    resto = [g for g in grupos if len(grupos[g]) and not re.search(r'atmos|city|bg|cone|beam|blue', g, re.I)]
    return max(resto, key=lambda g: len(grupos[g])) if resto else None


def lampadas(path):
    grupos = grupos_lnx(path)
    g = grupo_das_lampadas(grupos)
    if g is None:
        return np.zeros((0, 3))
    v = grupos[g]
    _, first = np.unique(np.round(v, 3), axis=0, return_index=True)
    return v[np.sort(first)]


def png(img):
    """PNG RGBA 8 bits de um array (h, w, 4) float 0-255."""
    a = np.clip(img, 0, 255).astype(np.uint8)
    h, w = a.shape[:2]
    raw = b''.join(b'\0' + a[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b'')


def miniatura(day, t, lado=96):
    """Miniatura PNG de uma textura do FIFA 16 (o menor mip com pelo menos `lado` pixels)."""
    mips = day.texture_mips(t, strict=False)
    if not mips:
        return None
    fmt = 'BC1' if t['format'] == 0 else 'BC3'
    k = 0
    while k + 1 < len(mips) and max(mips[k + 1][0], mips[k + 1][1]) >= lado:
        k += 1
    w, h, d = mips[k]
    try:
        return png(bcn.decode(d, w, h, fmt))
    except Exception:  # noqa: BLE001
        return None


def analisar(pasta, miniaturas=None):
    sa, sid = localizar(pasta)
    f = arquivos(sa, sid)
    faltam = [k for k in ('modelo', 'dia') if not f[k].is_file()]
    if faltam:
        raise ValueError('faltam arquivos do estádio: ' + ', '.join(str(f[k].name) for k in faltam))
    model = rx3.RX3(f['modelo'])
    day = rx3.RX3(f['dia'])
    tex = {t['name']: t for t in day.textures()}
    names = model.names_of(rx3.TEX)
    prims = model.primitives()
    papel, motivo = {}, {}
    pecas = []
    thumbs = {}
    for p in prims:
        i = p['index']
        papel[i], motivo[i] = sugestao(p)
        a = rx3.decode_vertices(p)
        idx = rx3.decode_indices(p)
        P = a['p0'].astype(np.float64) / 100.0
        tx = p['material']['textures']
        tname = names[tx[0][1]] if tx and tx[0][1] < len(names) else ''
        t = tex.get(tname)
        if t is not None and miniaturas is not None and tname not in thumbs:
            dig = hashlib.sha256(day.read(t['offset'], min(t['size'], 4096))).hexdigest()[:12]
            arq = Path(miniaturas) / f'{sid}_{dig}.png'
            if not arq.exists():
                b = miniatura(day, t)
                if b:
                    arq.parent.mkdir(parents=True, exist_ok=True)
                    arq.write_bytes(b)
            thumbs[tname] = arq.name if arq.exists() else None
        pecas.append(dict(prim=i, nome=p['name'], camada=p['layer'], shader=p['material']['shader'], material=p['material_index'],
                          textura=tname, textura_no_arquivo=t is not None, tamanho_textura=[t['width'], t['height']] if t else None,
                          miniatura=thumbs.get(tname), vertices=p['vertex_count'], triangulos=len(idx) // 3,
                          bbox=[round(float(x), 2) for x in np.concatenate([P.min(0), P.max(0)])] if len(P) else None,
                          papel=papel[i], motivo=motivo[i]))
    chao = camadas_do_chao(prims, papel)
    pista = piso_em_volta(prims, papel, chao)
    for x in pecas:
        x['chao_dy'] = chao.get(x['prim'])
        x['piso'] = x['prim'] in pista
    locs = model.locators()
    grupos = collections.Counter(re.sub(r'_\d+$', '', l['name'].replace('_0_0_0_0_0_0', '')) for l in locs)
    torcida = None
    if f['torcida'].is_file():
        c = ler_torcida(f['torcida'])
        rec = c['rec']
        torcida = dict(lugares=int(c['n']), faixa_vazia=int((rec[:, 22] == 0).sum()), visitantes=int(((rec[:, 19] == 0xFF) & (rec[:, 20] == 0xFF)).sum()),
                       organizada=int(((rec[:, 19] == 0) & (rec[:, 20] == 0) & (rec[:, 22] == 0xFF)).sum()),
                       altura=[round(float(c['pos'][:, 1].min()), 1), round(float(c['pos'][:, 1].max()), 1)],
                       raio=[round(float(np.hypot(c['pos'][:, 0], c['pos'][:, 2]).min()), 1), round(float(np.hypot(c['pos'][:, 0], c['pos'][:, 2]).max()), 1)])
    glares = {Path(g).stem.split('_', 2)[2]: len(lampadas(g)) for g in f['glares']}
    telao = [x['prim'] for x in pecas if x['papel'] == 'telao']
    receita = dict(fifa16_id=sid, descartar={str(x['prim']): x['motivo'] for x in pecas if x['papel'] == 'descartar'},
                   papel={str(x['prim']): x['papel'] for x in pecas if x['papel'] not in ('descartar',)},
                   chao={str(k): v for k, v in sorted(chao.items())}, um_lado=[], telao=telao,
                   grama=[x['prim'] for x in pecas if x['papel'] == 'grama'], pista=pista)
    return dict(pasta=str(Path(pasta)), sceneassets=str(sa), fifa16_id=sid, arquivos={k: (str(v) if not isinstance(v, list) else v) for k, v in f.items()},
                existe={k: (Path(v).is_file() if not isinstance(v, list) else bool(v)) for k, v in f.items()},
                pecas=pecas, camadas=dict(collections.Counter(x['camada'] for x in pecas)),
                localizadores=dict(grupos), torcida=torcida, glares=glares, receita=receita,
                resumo=dict(pecas=len(pecas), descartadas=sum(1 for x in pecas if x['papel'] == 'descartar'),
                            vertices=sum(x['vertices'] for x in pecas if x['papel'] != 'descartar')))


if __name__ == '__main__':
    import sys
    print(json.dumps(analisar(sys.argv[1]), ensure_ascii=False, indent=1)[:20000])
