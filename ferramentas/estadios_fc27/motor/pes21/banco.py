"""Banco de reservas de um estádio do PES 2021 no FC 27: cadeiras, técnicos e áreas técnicas.

Três coisas do FC 27 dependem de onde fica o banco, e na duplicata do El Grandioso todas apontam para o banco dele
(|x| de 3,4 a 11 m): os reservas (choreo_seats), os marcadores dos técnicos e auxiliares (slc_manager*, slc_assistantmanager*)
e as áreas técnicas da linha do estádio no banco de dados (stadiums.stad*techzone*, em centímetros, nos eixos do mundo com
o sinal trocado: no El Grandioso, casa em x de 5,6 a 18,1 m e z de 36,6 a 38,5 m, que no mundo é -x e -z). É dentro da
área técnica que o técnico anda durante a partida. Num estádio do PES com o banco em outro lugar (no Camp Nou, um abrigo
só no meio, |x| de 0,7 a 8,7 m), os três precisam acompanhar o banco novo.

As cadeiras saem do detector do FIFA 16 (motor/fifa16/bancos.py), com duas conferências a mais: à frente de um assento de
verdade o piso é mais baixo que ele, e o banco é o grupo de fileiras mais perto do meio-campo. Sem isso, uma mureta ou um
degrau com uma parede atrás passa por fileira de cadeiras (no Camp Nou, a borda da canaleta ao lado do abrigo, de |x| 11
a 31 m, mais comprida que o banco, ganhava os reservas).
"""
from __future__ import annotations
import numpy as np

from ..fifa16 import bancos
from ..fifa16.personagens import _pontos

FRENTE = (0.40, 0.90)       # faixa à frente do assento em que o piso é conferido (m)
DESNIVEL = 0.20             # quanto o piso à frente precisa ser mais baixo que o assento (m)
LONGE_DO_MEIO = 6.0         # uma fileira que começa mais que isso além da mais próxima do meio-campo não é do banco (m)
ZONA_X = (1.0, 2.0)         # a área técnica começa 1 m depois da ponta de dentro do banco e vai até 2 m depois da de fora
ZONA_Z = (36.6, 38.5)       # distância do centro do campo (m), como no El Grandioso (2,6 a 4,5 m da linha lateral)
CAMPOS = ('stadhometechzoneminx', 'stadhometechzonemaxx', 'stadhometechzoneminz', 'stadhometechzonemaxz',
          'stadawaytechzoneminx', 'stadawaytechzonemaxx', 'stadawaytechzoneminz', 'stadawaytechzonemaxz')


def cadeiras(tris):
    """Cadeiras do banco (x, y do assento, z, y do piso, fileira), sem as fileiras que não têm o piso mais baixo à frente."""
    cad = bancos.cadeiras(tris)
    if not len(cad):
        return cad
    reg = bancos._regiao(np.asarray(tris, np.float64))
    pts = np.concatenate(list(_pontos(reg, passo=0.06))) if len(reg) else np.zeros((0, 3))
    ok = np.ones(len(cad), bool)
    for k, (x, y, z, piso, _) in enumerate(cad):
        m = (np.abs(pts[:, 0] - x) <= 0.25) & (pts[:, 2] >= z + FRENTE[0]) & (pts[:, 2] <= z + FRENTE[1]) & (pts[:, 1] <= y + 0.25) & (pts[:, 1] >= y - 1.2)
        if m.sum() >= 5 and float(np.median(pts[m, 1])) > y - DESNIVEL:
            ok[k] = False
    fica = np.zeros(len(cad), bool)
    for lado in (-1.0, 1.0):
        fileiras = {}
        for r in set(cad[:, 4].tolist()):
            m = (cad[:, 4] == r) & (np.sign(cad[:, 0]) == lado)
            if m.any() and ok[m].mean() >= 0.5:
                fileiras[r] = m
        if not fileiras:
            continue
        # o banco é o que fica mais perto do meio-campo: fileiras que começam bem mais longe são outra coisa
        dentro = {r: float(np.abs(cad[m, 0]).min()) for r, m in fileiras.items()}
        perto = min(dentro.values())
        for r, m in fileiras.items():
            if dentro[r] <= perto + LONGE_DO_MEIO:
                fica |= m
    return cad[fica]


def referencia(pontos):
    """(ponta de dentro, ponta de fora, z da fileira da frente) dos lugares dos reservas de um lado (|x| e z, em metros)."""
    p = np.asarray(pontos, np.float64).reshape(-1, 3)
    ax = np.abs(p[:, 0])
    return float(ax.min()), float(ax.max()), float(p[:, 2].max())


def tecnico(orig, lado, eg, novo, auxiliar):
    """Posição nova (x, z) de um técnico ou auxiliar: a mesma distância da ponta do banco que ele tem no El Grandioso (o
    técnico, da ponta de dentro; o auxiliar, da de fora e da fileira da frente)."""
    x, z = abs(orig[0]), orig[2]
    if auxiliar:
        return lado * (novo[1] + (x - eg[1])), z + (novo[2] - eg[2])
    return lado * max(1.5, novo[0] + (x - eg[0])), z


def zonas(casa, visitante):
    """Campos stad*techzone* (cm) das áreas técnicas para os bancos novos; casa/visitante = referencia() de cada lado (a
    casa em -x no mundo) ou None. No banco de dados os eixos têm o sinal trocado em relação ao mundo."""
    out = {}
    for nome, ref, s in (('home', casa, 1), ('away', visitante, -1)):
        if ref is None:
            continue
        x0, x1 = ref[0] + ZONA_X[0], ref[1] + ZONA_X[1]
        zf = min(ZONA_Z[1], abs(ref[2]) - 1.5)
        zn = min(ZONA_Z[0], zf - 1.5)
        if zn < 34.8 or x1 - x0 < 3.0:
            continue
        longe, perto = int(round(x1 * 100)), int(round(x0 * 100))
        out[f'stad{nome}techzoneminx'] = longe if s > 0 else -perto
        out[f'stad{nome}techzonemaxx'] = perto if s > 0 else -longe
        out[f'stad{nome}techzoneminz'] = int(round(zf * 100))
        out[f'stad{nome}techzonemaxz'] = int(round(zn * 100))
    return out
