"""Banco de reservas de um estádio do PES 2021 no FC 27: cadeiras, técnicos e áreas técnicas.

Três coisas do FC 27 dependem de onde fica o banco, e na duplicata do El Grandioso todas apontam para o banco dele
(|x| de 3,4 a 11 m, em -z): os reservas (choreo_seats), os marcadores dos técnicos e auxiliares (slc_manager*,
slc_assistantmanager*) e as áreas técnicas da linha do estádio no banco de dados (stadiums.stad*techzone*), dentro das
quais o técnico anda durante a partida. Num estádio do PES com o banco em outro lugar (no Camp Nou, um abrigo só no meio,
|x| de 0,7 a 8,7 m), os três precisam acompanhar o banco novo. As áreas técnicas ficam nos eixos do mundo, no lado do
campo em que fica o banco (motor/fifa16/bancos.py, zonas()): as do El Grandioso estão com o sinal trocado, do outro lado
do campo, e até a 2.1 em teste a conversão as gravava assim, e os técnicos iam para lá.

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


def tecnico(orig, lado, eg, novo, auxiliar):
    """Posição nova (x, z) de um técnico ou auxiliar: a mesma distância da ponta do banco que ele tem no El Grandioso (o
    técnico, da ponta de dentro; o auxiliar, da de fora e da fileira da frente). eg e novo = bancos.referencia() do banco
    do El Grandioso e do banco novo, do mesmo lado."""
    x, z = abs(orig[0]), orig[2]
    if auxiliar:
        return lado * (novo[1] + (x - eg[1])), z + (novo[2] - eg[2])
    return lado * max(1.5, novo[0] + (x - eg[0])), z
