"""Câmeras próprias do estádio convertido: as do conjunto genérico do jogo que a arquibancada nova tapa, movidas para
onde a vista fica livre, e registradas como o jogo registra as de cada estádio.

Estádio sem conjunto próprio usa o genérico `Broadcasting/Cameras/StadiumCameras` (1317 câmeras: replays, cenas de
gol, torcida, entrada, pênalti...). Os ~230 estádios do jogo com conjunto próprio têm só as câmeras que mudam (o El
Grandioso tem 39, quase todas de torcida), casadas com as do genérico pelo CameraName (GUIDs próprios). O registro é
uma BundleRefTable (`Broadcasting/Cameras/CameraOverridesBrt`): um bundle
`broadcasting/cameras/stadiumcameras_<id>_cameraoverridesbrt` (superbundle e tipo iguais aos do El Grandioso) com três
EBX, o BundleRefTableBlueprintBundle de mesmo nome (o campo Blueprint aponta o segundo), o BundleRefTableBlueprint
`..._blueprint` e o CCCameraCollectionData `Broadcasting/Cameras/StadiumCameras_<id>`, mais os presets de lente e
corpo que as câmeras usam. Na tabela, o caminho `broadcasting/cameras/stadiumcameras_<id>` (o nome do bundle é ele
mais o nome da tabela) e o asset das câmeras pelo nome inteiro e pelo curto (FNV-1 64). A entrada nova vai no projeto
do FET como nos troféus e uniformes que o próprio FET duplica: campos brthash e brtpath do EBX das câmeras (brthash =
XxHash32 do nome da tabela em minúsculas, UTF-16LE); quem grava a tabela é o gerenciador de mods, ao aplicar o mod.

Vista tapada: um ponto da geometria nova (grade de 0,5 m, só o que fica 0,5 m acima do gramado) na linha da câmera
ao foco, entre o plano de corte da câmera (NearClip: as de torcida em alta resolução cortam os primeiros 40 a 170 m)
e os últimos 15% (a própria torcida ou o gramado); ou na linha da câmera ao ponto do campo mais perto dela (câmera
atrás ou embaixo da arquibancada nova, mesmo com o foco livre). Ficam como estão as câmeras que dependem da jogada
(DataDriven ou com posições relativas), as que filmam o estádio por fora (exterior, menus, aéreas) e as do interior
do túnel (o túnel do conjunto genérico fica onde a conversão põe a arquibancada nova: mover a câmera não traz os
jogadores para a vista). Para as outras, o menor deslocamento que libera todas as vistas da câmera entre: levar câmera
e foco juntos na direção do centro do campo (a torcida nova mais perto do campo que a do conjunto genérico: o mesmo
enquadramento, mais para dentro; só nas câmeras de torcida, porque nas outras o foco são pessoas que não mudam de
lugar, e ali só um empurrão), aproximar a câmera do foco, ou subir a câmera.
"""
from __future__ import annotations

import numpy as np

from .personagens import _pontos

GENERICO = 'Broadcasting/Cameras/StadiumCameras'
BRT_NOME = 'Broadcasting/Cameras/CameraOverridesBrt'
BRT_HASH = 0x72867CA7  # XxHash32 de 'broadcasting/cameras/cameraoverridesbrt' em UTF-16LE (chave do FET para a tabela)
MODELO_ID = 181        # El Grandioso: o bundle e os dois EBX de registro saem dos dele
# assets compartilhados que o jogo põe no bundle de câmeras de cada estádio (além dos presets que as câmeras usam)
COMPARTILHADOS = ('Broadcasting/Cameras/VE/ve_AA_BroadCast_In_Game', 'Broadcasting/Cameras/VE/ve_AA_BroadCast_SteadyCam')

VOX = 0.5             # grade da geometria (m)
ACIMA = 0.5           # só o que fica acima disto (m) tapa: o gramado e o piso em volta não
PERTO_DO_FOCO = 0.85  # o último trecho da linha (a torcida, o gramado) não conta
REGIAO = (170.0, 140.0, 90.0)  # |x|, |z| e altura (m) em que a geometria conta (mais longe só há câmeras de fora)
MEIO_X, MEIO_Z = 52.5, 34.0
POR_FORA = ('stadium exterior', 'stadium fe', 'stadium beauty', 'stadium poi', 'exterior', 'cam ext', 'onboarding',
            'blimp', 'aerial', 'skydrone')
NO_TUNEL = ('tunnel interior',)
DA_TORCIDA = ('crowd', 'tifo')  # câmeras que filmam a arquibancada
PASSO = 1.0           # passo dos ajustes (m)
MAX_CAMPO = 40.0      # câmera e foco na direção do campo: até 40 m nas de torcida
MAX_CAMPO_OUTRAS = 3.0  # e só um empurrão nas outras (bancos, jogadores, cenas: o foco não muda de lugar)
MAX_FOCO = 0.5        # câmera na direção do foco: até metade do caminho
MAX_SUBIR = 15.0      # subir a câmera: até 15 m


def nomes(i):
    """Caminho na tabela, bundle e os três EBX do conjunto de câmeras do estádio i."""
    caminho = f'broadcasting/cameras/stadiumcameras_{i}'
    return dict(caminho=caminho, bundle=caminho + '_cameraoverridesbrt', blueprint=caminho + '_cameraoverridesbrt_blueprint',
                colecao=f'Broadcasting/Cameras/StadiumCameras_{i}')


class Ocupacao:
    """Pontos ocupados da geometria nova numa grade de VOX metros (chaves int64 ordenadas, busca binária)."""

    def __init__(self, tri):
        tri = np.asarray(tri, np.float64)
        c = tri.mean(1)
        sel = (np.abs(c[:, 0]) < REGIAO[0]) & (np.abs(c[:, 2]) < REGIAO[1]) & (c[:, 1] < REGIAO[2]) & (tri[:, :, 1].max(1) > ACIMA)
        p = np.concatenate(list(_pontos(tri[sel], passo=VOX * 0.6))) if sel.any() else np.zeros((0, 3))
        p = p[p[:, 1] > ACIMA]
        if not len(p):
            p = np.full((1, 3), -1000.0)
        ijk = np.floor(p / VOX).astype(np.int64)
        self.lo = ijk.min(0) - 1
        self.dim = ijk.max(0) - self.lo + 2
        self.chaves = np.unique(self._chave(ijk))

    def _chave(self, ijk):
        q = ijk - self.lo
        return (q[:, 0] * self.dim[1] + q[:, 1]) * self.dim[2] + q[:, 2]

    def ocupado(self, pts):
        """Booleano por ponto (m)."""
        ijk = np.floor(np.asarray(pts, np.float64).reshape(-1, 3) / VOX).astype(np.int64)
        dentro = np.all((ijk >= self.lo) & (ijk < self.lo + self.dim), axis=1)
        out = np.zeros(len(ijk), bool)
        if dentro.any():
            k = self._chave(ijk[dentro])
            pos = np.minimum(np.searchsorted(self.chaves, k), len(self.chaves) - 1)
            out[dentro] = self.chaves[pos] == k
        return out

    def corta(self, P, Q, ini, fim):
        """Primeira fração (entre ini e fim) da linha de P a Q (m) que cai num ponto ocupado, ou None."""
        P, Q = np.asarray(P, np.float64), np.asarray(Q, np.float64)
        d = Q - P
        n = max(int(float(np.linalg.norm(d)) / (VOX / 2)) + 1, 2)
        s = np.arange(n + 1) / n
        s = s[(s >= ini) & (s <= fim)]
        if not len(s):
            return None
        hit = np.flatnonzero(self.ocupado(P + d * s[:, None]))
        return float(s[hit[0]]) if len(hit) else None


def ancora(P):
    """Ponto do campo mais perto da câmera, a 1,5 m de altura."""
    return np.array([np.clip(P[0], -MEIO_X, MEIO_X), 1.5, np.clip(P[2], -MEIO_Z, MEIO_Z)])


def problema(oc, P, F, near):
    """O que tapa uma vista (posição P, foco F e plano de corte near, em m): None, 'foco' ou 'campo'."""
    L = float(np.linalg.norm(F - P))
    if L > 1e-6 and oc.corta(P, F, min(near / L, PERTO_DO_FOCO), PERTO_DO_FOCO) is not None:
        return 'foco'
    A = ancora(P)
    La = float(np.linalg.norm(A - P))
    if La > near + 1.0 and oc.corta(P, A, near / La, 0.97) is not None:
        return 'campo'
    return None


def _ref(x):
    return int(x.split(':')[2]) if isinstance(x, str) and x.startswith('ptr:int:') else None


def _v3(d):
    return np.array([d['x'], d['y'], d['z']], np.float64) / 100.0


def cameras(dump):
    """Câmeras do conjunto: [{indice, guid, nome, tipo, absoluta, refs, vistas: [(índice da vista, P, F, near) em m]}]."""
    I = dump['instances']
    out = []
    for p in I[0]['fields']['Cameras']:
        k = _ref(p)
        c = I[k]
        f = c['fields']
        tipo = c['type'].split('.')[-1]
        if f.get('Viewpoints') is not None:
            refs = ('Viewpoints', [_ref(r) for r in f['Viewpoints']])
        elif f.get('Viewpoint') is not None:
            refs = ('Viewpoint', [_ref(f['Viewpoint'])])
        else:
            refs = (None, [])
        vistas = []
        for j in refs[1]:
            if j is None:
                continue
            v = I[j]['fields']
            if isinstance(v.get('Position'), dict) and isinstance(v.get('Focus'), dict):
                vistas.append((j, _v3(v['Position']), _v3(v['Focus']), float(v.get('NearClip') or 0.0) / 100.0))
        absoluta = (f.get('PositionsAbsolute') is not False and tipo != 'DataDrivenCCCameraData' and refs[0] is not None
                    and None not in refs[1] and not f.get('EditorViewpoints'))
        out.append(dict(indice=k, guid=c['guid'], nome=f.get('CameraName', ''), tipo=tipo, absoluta=absoluta, refs=refs,
                        vistas=vistas))
    return out


def _livre(oc, vistas):
    return all(problema(oc, P, F, near) is None for _, P, F, near in vistas)


def ajuste(oc, cam):
    """(modo, deslocamento em m, vistas novas) do menor ajuste que libera todas as vistas, ou None (ver o início)."""
    vistas = cam['vistas']
    centro = np.mean([P for _, P, _, _ in vistas], axis=0)
    u = -np.array([centro[0], 0.0, centro[2]])
    nu = float(np.linalg.norm(u))
    u = u / nu if nu > 1e-6 else None
    max_campo = MAX_CAMPO if da_torcida(cam['nome']) else MAX_CAMPO_OUTRAS
    t = PASSO
    while True:
        cand = []
        if u is not None and t <= min(max_campo, nu):
            cand.append(('campo', [(j, P + u * t, F + u * t, near) for j, P, F, near in vistas]))
        nv = []
        for j, P, F, near in vistas:
            L = float(np.linalg.norm(F - P))
            if L <= 0 or t / L > MAX_FOCO:
                nv = None
                break
            nv.append((j, P + (F - P) * (t / L), F, near))
        if nv:
            cand.append(('foco', nv))
        if t <= MAX_SUBIR:
            cand.append(('subir', [(j, P + np.array([0.0, t, 0.0]), F, near) for j, P, F, near in vistas]))
        if not cand:
            return None
        for modo, nv in cand:
            if _livre(oc, nv):
                return modo, round(float(t), 1), nv
        t += PASSO


def _tem(nome, partes):
    n = nome.lower().replace('_', ' ')
    return any(s in n for s in partes)


def por_fora(nome):
    return _tem(nome, POR_FORA)


def no_tunel(nome):
    return _tem(nome, NO_TUNEL)


def da_torcida(nome):
    return _tem(nome, DA_TORCIDA)


def analisar(oc, cams):
    """Câmeras tapadas e o ajuste de cada uma: (ajustadas [(cam, modo, deslocamento, vistas novas)], sem_ajuste [cam])."""
    ajustadas, sem = [], []
    for cam in cams:
        if not cam['absoluta'] or not cam['vistas'] or por_fora(cam['nome']) or no_tunel(cam['nome']):
            continue
        if _livre(oc, cam['vistas']):
            continue
        a = ajuste(oc, cam)
        if a is None:
            sem.append(cam)
        else:
            ajustadas.append((cam,) + a)
    return ajustadas, sem


# ------------------------------------------------------------------ EBX (ops do ConvertTool)
def _cm(v):
    return [round(float(x) * 100.0, 3) for x in v]


def ops_colecao(dump, ajustadas, nome_novo, guid):
    """Ops que fazem, a partir do conjunto genérico, o do estádio: só as câmeras ajustadas, com GUIDs novos
    (guid(*partes) -> GUID determinístico) e as posições novas; o resto do conjunto sai."""
    I = dump['instances']
    ops = [dict(op='partition', guid=guid('particao')), dict(op='primary_guid', guid=guid('colecao')),
           dict(op='set', target={'primary': True}, path='Name', value=nome_novo)]
    tags = []
    for k, (cam, modo, d, nv) in enumerate(ajustadas):
        novo = {j: (P, F) for j, P, F, _ in nv}
        campo, refs = cam['refs']
        vt = []
        for n, j in enumerate(refs):
            t = f'v{k}_{n}'
            ops.append(dict(op='clone', source={'guid': I[j]['guid']}, tag=t, guid=guid('vista', cam['guid'], I[j]['guid']), exported=True))
            if j in novo:
                P, F = novo[j]
                ops.append(dict(op='set', target={'tag': t}, path='Position', value={'vec3': _cm(P)}))
                ops.append(dict(op='set', target={'tag': t}, path='Focus', value={'vec3': _cm(F)}))
            vt.append(t)
        tc = f'c{k}'
        ops.append(dict(op='clone', source={'guid': cam['guid']}, tag=tc, guid=guid('camera', cam['guid']), exported=True))
        if campo == 'Viewpoints':
            ops.append(dict(op='list_set', target={'tag': tc}, path='Viewpoints', items=[{'int': {'tag': t}} for t in vt]))
        else:
            ops.append(dict(op='set', target={'tag': tc}, path='Viewpoint', value={'int': {'tag': vt[0]}}))
        tags.append(tc)
    ops.append(dict(op='list_set', target={'primary': True}, path='Cameras', items=[{'int': {'tag': t}} for t in tags]))
    ops += [dict(op='remove', target={'guid': i['guid']}) for i in I[1:]]
    return ops


def ops_registro(nome_novo, particao, blueprint=None):
    """Ops dos dois EBX de registro (cópias dos do El Grandioso): partição e instância principal com o mesmo GUID,
    como as do jogo; o BlueprintBundle aponta o Blueprint novo."""
    ops = [dict(op='partition', guid=particao), dict(op='primary_guid', guid=particao),
           dict(op='set', target={'primary': True}, path='Name', value=nome_novo)]
    if blueprint:
        ops.append(dict(op='set', target={'primary': True}, path='Blueprint', value={'ext': [blueprint, blueprint]}))
    return ops
