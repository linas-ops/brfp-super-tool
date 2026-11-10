"""Luzes da torcida do El Grandioso levadas para a torcida do estádio novo.

À noite, a torcida é iluminada por luzes dinâmicas do El Grandioso: 145 spots em volta da arquibancada (world part
lighting_stands_main) e 4 nas torres (lighting_flood_main), todos apontados para baixo (eles iluminam ao longo de
-forward) e com alcance de 3 a 70 m. No estádio convertido, a torcida do FIFA 16 fica em outro lugar: quando ela fica
mais perto do campo que a do El Grandioso, as lâmpadas caem no meio dela (Neo Química Arena e Allianz Parque: o dobro da
luz do El Grandioso, com manchas); quando fica mais longe, partes dela ficam no escuro.

Cada luz acompanha o trecho da torcida que ilumina: o lugar da torcida do El Grandioso que ela mais ilumina vai para o
lugar equivalente da torcida nova (mesmo ângulo em volta do campo e mesma fração da profundidade da arquibancada, da
primeira fila à última), e a luz anda o mesmo tanto, sem girar. No fim, a intensidade das que andaram é ajustada para a
luz mediana na torcida nova ser a do El Grandioso. As luzes que não alcançam a torcida do El Grandioso ficam onde estão.
Nenhuma delas projeta sombra no jogo (CastShadows desligado em todas as qualidades).
"""
from __future__ import annotations
import numpy as np

SETOR = np.radians(5.0)     # meia largura do setor em volta do campo
CABECA = 1.0                # altura da cabeça acima do lugar
JANELA = 15                 # lugares de cada lado na mediana do lugar equivalente
LIMITES_ESCALA = (0.5, 2.0)


def contribuicao(luz, pontos):
    """Luz que chega a cada ponto (modelo simples: lúmens / distância², janela do raio de alcance e cone do spot)."""
    v = pontos - luz['pos']
    dist = np.linalg.norm(v, axis=1)
    if luz.get('angulo'):
        cone = (v @ luz['dir']) / np.maximum(dist, 1e-6) >= np.cos(np.radians(luz['angulo'] / 2))
    else:
        cone = np.ones(len(v), bool)
    jan = np.clip(1 - (dist / luz['raio']) ** 4, 0, 1) ** 2
    return np.where(cone, luz['intensidade'] * jan / np.maximum(dist, 0.5) ** 2, 0.0)


def iluminacao(luzes, lugares):
    cab = lugares + [0.0, CABECA, 0.0]
    return sum(contribuicao(l, cab) for l in luzes) if luzes else np.zeros(len(lugares))


def _profundidade(s):
    return np.hypot(s[:, 0], s[:, 2]) + 1.5 * s[:, 1]


def _setor(s, th):
    a = np.arctan2(s[:, 2], s[:, 0])
    da = np.abs((a - th + np.pi) % (2 * np.pi) - np.pi)
    w = SETOR
    sel = da <= w
    while sel.sum() < 30 and w < np.pi:
        w *= 1.6
        sel = da <= w
    return s[sel]


def equivalente(q, antigos, novos):
    """O lugar da torcida nova equivalente ao lugar q da torcida antiga (mesmo ângulo em volta do campo, mesma fração
    da profundidade da arquibancada)."""
    th = np.arctan2(q[2], q[0])
    sa, sn = _setor(antigos, th), _setor(novos, th)
    frac = float(np.mean(_profundidade(sa) < _profundidade(q[None])[0]))
    k = np.argsort(_profundidade(sn))
    j = int(np.clip(round(frac * (len(k) - 1)), 0, len(k) - 1))
    return np.median(sn[k[max(0, j - JANELA):j + JANELA + 1]], 0)


def acompanhar(luzes, antigos, novos):
    """Posições e intensidades novas das luzes (lista de dicts pos, dir, intensidade, raio, angulo) para a torcida
    `novos` (array (n, 3)), a partir da torcida `antigos` do El Grandioso. Devolve (luzes novas, relatório)."""
    antigos = np.asarray(antigos, np.float64)
    novos = np.asarray(novos, np.float64)
    cab = antigos + [0.0, CABECA, 0.0]
    saida, andaram = [], []
    for l in luzes:
        c = contribuicao(l, cab)
        if c.sum() <= 0:
            saida.append(dict(l))
            continue
        alvo = (antigos * c[:, None]).sum(0) / c.sum()
        q = antigos[np.argmin(np.linalg.norm(antigos - alvo, axis=1))]
        d = equivalente(q, antigos, novos) - q
        saida.append(dict(l, pos=l['pos'] + d))
        andaram.append(len(saida) - 1)
    ref = float(np.median(iluminacao(luzes, antigos)))
    depois = float(np.median(iluminacao(saida, novos)))
    escala = float(np.clip(ref / depois, *LIMITES_ESCALA)) if depois > 0 and ref > 0 else 1.0
    for i in andaram:
        saida[i]['intensidade'] = saida[i]['intensidade'] * escala
    desl = [float(np.linalg.norm(saida[i]['pos'] - luzes[i]['pos'])) for i in andaram]
    antes = iluminacao(luzes, novos)
    final = iluminacao(saida, novos)
    pct = lambda e: [round(float(x), 2) for x in np.percentile(e / ref, [10, 50, 90])] if ref > 0 else None  # noqa: E731
    rel = dict(luzes=len(luzes), acompanharam=len(andaram), ficaram=len(luzes) - len(andaram), escala_intensidade=round(escala, 3),
               deslocamento_m=[round(float(x), 1) for x in np.percentile(desl, [10, 50, 90])] if desl else None,
               luz_na_torcida_vs_el_grandioso=dict(el_grandioso=pct(iluminacao(luzes, antigos)), antes=pct(antes), depois=pct(final)))
    return saida, rel
