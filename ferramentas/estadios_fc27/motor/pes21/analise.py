"""Análise de um estádio do PES 2021 (pasta do mod, com Asset\\model\\bg\\st<NNN>) e a receita sugerida para a conversão.

O resultado tem a mesma forma da análise do FIFA 16 (motor/fifa16/analise.py), para a conversão seguir o mesmo caminho:
uma peça por malha dos modelos do estádio e do telão, com o papel sugerido pelo material do PES:
- o que o FC 27 já tem sai: figurantes e equipamentos de transmissão (texturas da pasta staff do PES), gramado, vidros e
  brilhos (materiais com transparência parcial, que os materiais do El Grandioso usados na conversão não têm);
- as telas do pacote tv viram o telão; a grama em volta do campo vira "grama"; o resto entra como opaco ou alpha, conforme
  a marca de transparência da malha (0x80), com um lado só a não ser que a malha seja de dois lados no PES (0x20).
O PES aceita os bancos de reservas dos dois lados do campo; o FC 27 e o El Grandioso os têm em -Z. O lado é achado pelas
cadeiras do banco (motor/fifa16/bancos.py) e, se for +Z, o estádio todo gira meia volta em torno do centro do campo.
"""
from __future__ import annotations
import collections
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from ..fifa16 import bancos, bcn
from ..fifa16.analise import _area_xz, _celulas, png
from . import brilhos, estadio as E, torcida as T

PAPEIS = ('opaco', 'alpha', 'telao', 'grama', 'banner', 'descartar')
FIGURANTES = re.compile(r'(/staff/|/scarecrow/|/static_obj/|benchm|steward|scarecrow|tvcam|cameraman|_sc20\d\d)', re.I)
GRAMA = re.compile(r'(turf|grass|pitch)', re.I)


def sugestao(peca, flat):
    """(papel, motivo) sugeridos pelo material do PES. flat: a peça é plana e fica no nível do campo."""
    m = peca['malha']
    mat = m['material'] or dict(shader='', tecnica='', nome='', texturas={})
    sh, tec = mat['shader'].lower(), mat['tecnica'].lower()
    cor = E.textura_de_cor(mat)
    nomes = ' '.join([cor, mat['nome'], m['grupo']])
    if peca['modelo']['origem'] == 'telao' or sh.endswith('_bill') or 'constant_srgb_bill' in tec:
        return 'telao', 'tela do telão (no FC 27 mostra a transmissão ao vivo)'
    if 'pitch' in sh or 'pitch' in tec:
        return 'descartar', 'gramado do campo (o FC 27 desenha o próprio)'
    if FIGURANTES.search(nomes):
        return 'descartar', 'figurantes e equipamentos de transmissão do PES (o FC 27 tem os próprios personagens)'
    if 'glass' in sh or 'glass' in tec:
        return 'descartar', 'vidro (transparência parcial, que os materiais do El Grandioso usados na conversão não têm)'
    decalque = m['alpha'] in (0x50, 0x70)
    if 'constant' in sh or (m['alpha'] & 0x10 and not decalque):
        return 'descartar', 'brilho ou transparência parcial do PES (o FC 27 usa os glares próprios)'
    if not cor:
        return 'descartar', f'material sem textura de cor ({sh})'
    if flat and ('layer' in sh or GRAMA.search(nomes)):
        return 'grama', 'grama em volta do campo (tingida de verde, fica embaixo do gramado do FC 27)'
    if m['alpha'] & 0x80 or decalque:
        return 'alpha', 'alpha (transparência recortada)'
    return 'opaco', f'opaco ({sh})'


def lado_dos_bancos(tris):
    """(giro em graus, cadeiras achadas em -Z, cadeiras achadas em +Z): 180 quando os bancos de reservas ficam em +Z."""
    c = tris.mean(1)
    perto = (np.abs(c[:, 0]) < bancos.REGIAO_X + 1) & (np.abs(c[:, 2]) > -bancos.REGIAO_Z[1] - 1) & (np.abs(c[:, 2]) < -bancos.REGIAO_Z[0] + 2) \
        & (c[:, 1] > bancos.REGIAO_Y[0]) & (c[:, 1] < bancos.REGIAO_Y[1])
    t = tris[perto]
    menos = len(bancos.cadeiras(t)) if len(t) else 0
    mais = len(bancos.cadeiras(t * np.array([-1.0, 1.0, -1.0]))) if len(t) else 0
    return (180 if mais > menos else 0), menos, mais


def camadas_do_chao(geo, papel, celula=0.5):
    """Ordem vertical das superfícies coplanares no chão, como na análise do FIFA 16: quem fica dentro de outra superfície
    maior vai por cima; a grama vai 6 cm abaixo. geo: {peça: (posições, triângulos)}."""
    chao = {}
    for i, (P, idx) in geo.items():
        if papel[i] not in ('opaco', 'alpha', 'grama') or not len(idx):
            continue
        tri = P[idx]
        flat = (np.abs(tri[..., 1]) < 0.05).all(1)
        if flat.sum() < 1:
            continue
        area = float(_area_xz(P, idx[flat]).sum())
        if area < 0.5:
            continue
        chao[i] = dict(cells=_celulas(tri[flat], celula), area=area, alpha=papel[i] == 'alpha', grama=papel[i] == 'grama')
    dy, nivel = {}, {}
    for i in sorted((i for i in chao if not chao[i]['grama']), key=lambda i: (chao[i]['alpha'], -chao[i]['area'], i)):
        abaixo = [j for j in nivel if len(chao[i]['cells'] & chao[j]['cells']) >= max(2, 0.25 * min(len(chao[i]['cells']), len(chao[j]['cells'])))]
        nivel[i] = 1 + max((nivel[j] for j in abaixo), default=0)
    for i, n in nivel.items():
        dy[i] = round(min(0.002 * n, 0.012), 3)
    for i in chao:
        if chao[i]['grama']:
            dy[i] = -0.06
    return dy


def piso_em_volta(geo, papel):
    """Peças do chão que dizem até onde vai o gramado do FC 27: as opacas com piso no nível do campo em volta dele, sem
    nada dentro do campo. No PES o piso em volta costuma vir repartido por lado, então entram todas (no FIFA 16, uma)."""
    out = []
    for i, (P, idx) in geo.items():
        if papel[i] != 'opaco' or not len(idx):
            continue
        tri = P[idx]
        flat = (np.abs(tri[..., 1]) < 0.05).all(1)
        if not flat.any():
            continue
        Q = tri[flat].reshape(-1, 3)
        fora = (np.abs(Q[:, 0]) > 53.5) | (np.abs(Q[:, 2]) > 35.0)
        dentro = (np.abs(Q[:, 0]) < 52.5) & (np.abs(Q[:, 2]) < 34.0)
        perto = fora & (np.abs(Q[:, 0]) < 75) & (np.abs(Q[:, 2]) < 55)
        if dentro.any() or not perto.any():
            continue
        area = float(_area_xz(P, idx[flat]).sum())
        if area >= 20.0:
            out.append(i)
    return out


def miniatura(tex, lado=96):
    """Miniatura PNG de uma textura do PES (o menor mip com pelo menos `lado` pixels), ou None."""
    if tex is None or tex.formato not in ('BC1', 'BC3'):
        return None
    try:
        ch = tex.cadeia()
        if not ch:
            return None
        k = 0
        while k + 1 < len(ch) and max(ch[k + 1][0], ch[k + 1][1]) >= lado:
            k += 1
        w, h, d = ch[k]
        return png(bcn.decode(d, w, h, tex.formato))
    except Exception:  # noqa: BLE001
        return None


def analisar(pasta, miniaturas=None):
    est = E.Estadio(pasta)
    f = est.arquivos()
    pecas_est = est.pecas()
    geo, pecas, papel, motivo, thumbs = {}, [], {}, {}, {}
    sobras = 0
    for p in pecas_est:
        i, m = p['prim'], p['malha']
        P, N, U, idx, fora = est.geometria(p)
        sobras += fora
        usados = np.unique(idx) if len(idx) else np.zeros(0, np.int64)
        Q = P[usados] if len(usados) else P
        flat = bool(len(Q)) and float(np.abs(Q[:, 1]).max()) < 0.3
        papel[i], motivo[i] = sugestao(p, flat)
        if not len(idx):
            papel[i], motivo[i] = 'descartar', 'peça sem triângulos no estádio (sobra que o autor escondeu)'
        geo[i] = (P, idx)
        mat = m['material'] or dict(shader='', nome='', texturas={})
        cam = E.textura_de_cor(mat)
        tname = cam.rsplit('/', 1)[-1]
        t = est.textura(cam) if cam else None
        if t is not None and miniaturas is not None and cam not in thumbs:
            dig = hashlib.sha256((cam.lower() + str(t.path.stat().st_size)).encode()).hexdigest()[:12]
            arq = Path(miniaturas) / f'pes_{est.sid}_{dig}.png'
            if not arq.exists():
                b = miniatura(t)
                if b:
                    arq.parent.mkdir(parents=True, exist_ok=True)
                    arq.write_bytes(b)
            thumbs[cam] = arq.name if arq.exists() else None
        pecas.append(dict(prim=i, nome=m['grupo'], camada=p['modelo']['nome'], shader=mat['shader'], material=mat['nome'], textura=tname,
                          textura_no_arquivo=t is not None, tamanho_textura=[t.largura, t.altura] if t else None, miniatura=thumbs.get(cam),
                          vertices=int(len(usados)), triangulos=int(len(idx)), dois_lados=bool(m['alpha'] & 0x20),
                          bbox=[round(float(x), 2) for x in np.concatenate([Q.min(0), Q.max(0)])] if len(Q) else None,
                          papel=papel[i], motivo=motivo[i]))
    ficam = [i for i in geo if papel[i] in ('opaco', 'alpha') and len(geo[i][1])]
    tris = np.concatenate([geo[i][0][geo[i][1]] for i in ficam]) if ficam else np.zeros((0, 3, 3))
    giro, cad_menos, cad_mais = lado_dos_bancos(tris)
    chao = camadas_do_chao(geo, papel)
    pista = piso_em_volta(geo, papel)
    for x in pecas:
        x['chao_dy'] = chao.get(x['prim'])
        x['piso'] = x['prim'] in pista
    torcida = None
    if f['torcida'].is_file():
        areas = T.ler_areas(f['torcida'])
        torcida = dict(areas=len(areas['quad']), lugares=int(T.estimar(areas)), visitantes_areas=int(areas['visitante'].sum()),
                       altura=[round(float(areas['quad'][..., 1].min()), 1), round(float(areas['quad'][..., 1].max()), 1)],
                       cores_das_cadeiras=f['cadeiras'].is_file())
    glares = {k: len(brilhos.lampadas(f[a])) for k, a in (('dia', 'brilhos_dia'), ('noite', 'brilhos_noite')) if f[a].is_file()}
    um_lado = [x['prim'] for x in pecas if x['papel'] == 'opaco' and not x['dois_lados']]
    receita = dict(origem='pes21', fonte_id=est.sid, giro=giro,
                   descartar={str(x['prim']): x['motivo'] for x in pecas if x['papel'] == 'descartar'},
                   papel={str(x['prim']): x['papel'] for x in pecas if x['papel'] != 'descartar'},
                   chao={str(k): v for k, v in sorted(chao.items())}, um_lado=um_lado,
                   telao=[x['prim'] for x in pecas if x['papel'] == 'telao'], grama=[x['prim'] for x in pecas if x['papel'] == 'grama'], pista=pista)
    return dict(origem='pes21', pasta=str(Path(pasta)), asset=str(est.asset), fonte_id=est.sid, fifa16_id=est.sid,
                arquivos={k: str(v) for k, v in f.items()}, existe={k: Path(v).is_file() for k, v in f.items()},
                pecas=pecas, camadas=dict(collections.Counter(x['camada'] for x in pecas)), localizadores={}, torcida=torcida, glares=glares,
                giro=giro, bancos=dict(cadeiras_em_menos_z=cad_menos, cadeiras_em_mais_z=cad_mais), sobras_longe=sobras, receita=receita,
                resumo=dict(pecas=len(pecas), descartadas=sum(1 for x in pecas if x['papel'] == 'descartar'),
                            vertices=sum(x['vertices'] for x in pecas if x['papel'] != 'descartar'),
                            triangulos=sum(x['triangulos'] for x in pecas if x['papel'] != 'descartar')))


if __name__ == '__main__':
    import sys
    print(json.dumps(analisar(sys.argv[1]), ensure_ascii=False, indent=1)[:20000])
