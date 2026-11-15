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


# ------------------------------------------------------------------ modo "cobrir" (torcidas maiores que a do El Grandioso)
DISTANCIA = 22.0            # da luz ao trecho da torcida que ela ilumina (no El Grandioso: 16 a 38 m, mediana 20)
ELEVACAO = 55.0             # graus acima do horizonte, do lado do campo: a luz chega pela frente e por cima
NIVEL = 1.25                # luz em cada trecho, em relação à mediana do El Grandioso
RAIO_MINIMO = 45.0          # alcance mínimo de uma luz reposicionada (m)
LIMITES_INTENSIDADE = (0.1, 12.0)  # em relação à mediana das intensidades do El Grandioso


def _trechos(pontos, k, voltas=25):
    """k-means determinístico: (centros (k, 3), trecho de cada ponto)."""
    rng = np.random.default_rng(0)
    centros = [pontos[int(rng.integers(len(pontos)))]]
    d = np.linalg.norm(pontos - centros[0], axis=1)
    for _ in range(1, k):  # o ponto mais longe dos centros já escolhidos
        centros.append(pontos[int(np.argmax(d))])
        d = np.minimum(d, np.linalg.norm(pontos - centros[-1], axis=1))
    centros = np.array(centros)
    for _ in range(voltas):
        dono = np.argmin(((pontos[:, None, :] - centros[None, :, :]) ** 2).sum(2), 1)
        for j in range(k):
            m = dono == j
            if m.any():
                centros[j] = pontos[m].mean(0)
    dono = np.argmin(((pontos[:, None, :] - centros[None, :, :]) ** 2).sum(2), 1)
    return centros, dono


def cobrir(luzes, antigos, novos):
    """As luzes que iluminam a torcida do El Grandioso redistribuídas por toda a torcida nova: ela é dividida em tantos
    trechos quantas são essas luzes, e cada luz vai para a frente e para cima do seu trecho (do lado do campo), apontada para
    ele, com a intensidade ajustada para o trecho receber NIVEL vezes a luz mediana do El Grandioso. Serve às torcidas
    maiores ou mais altas que a do El Grandioso, em que só acompanhar deixa os anéis de cima no escuro.
    Devolve (luzes novas, com 'dir' e 'raio' novos nas que mudaram, relatório)."""
    antigos = np.asarray(antigos, np.float64)
    novos = np.asarray(novos, np.float64)
    cab_a = antigos + [0.0, CABECA, 0.0]
    usadas = [i for i, l in enumerate(luzes) if l.get('angulo') and contribuicao(l, cab_a).sum() > 0]
    ref = float(np.median(iluminacao(luzes, antigos)))
    saida = [dict(l) for l in luzes]
    if not usadas or ref <= 0 or len(novos) < len(usadas):
        return saida, dict(luzes=len(luzes), redistribuidas=0, motivo='sem luzes de torcida no El Grandioso ou torcida nova pequena demais')
    passo = max(1, len(novos) // 20000)
    amostra = novos[::passo]
    centros, dono = _trechos(amostra, len(usadas))
    # as luzes e os trechos em volta do campo na mesma ordem (cada luz anda o mínimo)
    ordem_l = sorted(usadas, key=lambda i: (np.arctan2(luzes[i]['pos'][2], luzes[i]['pos'][0]), luzes[i]['pos'][1]))
    ordem_c = sorted(range(len(centros)), key=lambda j: (np.arctan2(centros[j][2], centros[j][0]), centros[j][1]))
    base_i = float(np.median([luzes[i]['intensidade'] for i in usadas]))
    el = np.radians(ELEVACAO)
    for i, j in zip(ordem_l, ordem_c):
        c = centros[j] + [0.0, CABECA, 0.0]
        campo = np.array([np.clip(c[0], -52.5, 52.5), np.clip(c[2], -34.0, 34.0)])
        h = campo - c[[0, 2]]
        h = h / max(np.linalg.norm(h), 1e-6)
        u = np.array([h[0] * np.cos(el), np.sin(el), h[1] * np.cos(el)])
        saida[i].update(pos=c + u * DISTANCIA, dir=-u, raio=max(float(luzes[i]['raio']), RAIO_MINIMO), intensidade=base_i, trecho=int(j))
    # intensidade de cada luz: o trecho dela recebe NIVEL x a mediana do El Grandioso (ajuste proporcional, em voltas)
    cab = amostra + [0.0, CABECA, 0.0]
    fixas = sum(contribuicao(saida[i], cab) for i in range(len(saida)) if i not in set(usadas))
    fixas = fixas if isinstance(fixas, np.ndarray) else np.zeros(len(cab))
    unit = np.stack([contribuicao(dict(saida[i], intensidade=1.0), cab) for i in ordem_l], 1)  # (pontos, luzes)
    I = np.full(len(ordem_l), base_i)
    grupo = np.array([saida[i]['trecho'] for i in ordem_l])
    alvo = NIVEL * ref
    lo, hi = LIMITES_INTENSIDADE[0] * base_i, LIMITES_INTENSIDADE[1] * base_i
    for _ in range(40):
        e = unit @ I + fixas
        media = np.array([e[dono == g].mean() if (dono == g).any() else alvo for g in grupo])
        I = np.clip(I * np.clip(alvo / np.maximum(media, 1e-9), 0.6, 1.6), lo, hi)
    for i, v in zip(ordem_l, I):
        saida[i]['intensidade'] = float(v)
        saida[i].pop('trecho', None)
    final = iluminacao(saida, novos)
    antes = iluminacao(luzes, novos)
    pct = lambda e: [round(float(x), 2) for x in np.percentile(e / ref, [10, 50, 90])]  # noqa: E731
    rel = dict(luzes=len(luzes), redistribuidas=len(usadas), ficaram=len(luzes) - len(usadas), nivel=NIVEL,
               intensidade_vs_el_grandioso=round(float(I.sum() / sum(luzes[i]['intensidade'] for i in usadas)), 2),
               luz_na_torcida_vs_el_grandioso=dict(el_grandioso=pct(iluminacao(luzes, antigos)), antes=pct(antes), depois=pct(final)),
               sem_luz=dict(antes=round(float((antes < 0.05 * ref).mean()), 3), depois=round(float((final < 0.05 * ref).mean()), 3)))
    return saida, rel
