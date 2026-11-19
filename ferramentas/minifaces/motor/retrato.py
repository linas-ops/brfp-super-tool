"""Recorte local de retratos e medidas da silhueta para o quadro de 180 px."""
import atexit
import importlib.util
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "criador_faces"))
from local import pontos

atexit.register(pontos.fechar)
DISPONIVEL = (os.environ.get("BRFP_RECORTE_BASICO") != "1" and importlib.util.find_spec("mediapipe") is not None
              and "selfie_multiclass_256x256.tflite" not in pontos.modelos_faltando())

def probabilidade(rgb, centro):
    """Segmenta a região visível da foto e conserva a pessoa que contém o rosto escolhido."""
    h, w = rgb.shape[:2]
    escala = min(1.0, 640 / max(w, h))
    amostra = cv2.resize(rgb, (max(1, round(w*escala)), max(1, round(h*escala))),
                         interpolation=cv2.INTER_AREA) if escala < 1 else rgb
    try:
        p = pontos.segmentar(amostra, probabilidade_pessoa=True)
    except (pontos.Erro, ImportError, RuntimeError, OSError, ValueError) as ex:
        raise ValueError(f"Falha no segmentador local de retratos. Confira os componentes de Minifaces. {ex}") from ex
    # Refinamento da borda da rede pela luminância da foto. Mantém detalhes junto ao cabelo e às orelhas.
    guia = cv2.cvtColor(amostra, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    janela = (7, 7)
    media = cv2.blur(guia, janela)
    suave = cv2.blur(p, janela)
    variancia = cv2.blur(guia * guia, janela) - media * media
    ganho = (cv2.blur(guia * p, janela) - media * suave) / (variancia + 0.001)
    p = np.clip(cv2.blur(ganho, janela) * guia + cv2.blur(suave - ganho * media, janela), 0, 1)
    _, rotulos = cv2.connectedComponents((p > 0.22).astype(np.uint8))
    cx, cy, raio = centro
    yy, xx = np.ogrid[:p.shape[0], :p.shape[1]]
    nucleo = ((xx - cx*escala)**2 + (yy - cy*escala)**2 <= max(2, raio*escala)**2)
    ids = rotulos[nucleo]
    if np.any(ids):
        principal = np.bincount(ids[ids > 0]).argmax()
        suporte = cv2.dilate((rotulos == principal).astype(np.uint8), np.ones((5, 5), np.uint8))
        p *= suporte
    return cv2.resize(p, (w, h), interpolation=cv2.INTER_LINEAR) if escala < 1 else p


def enquadramento(alfa, matriz_janela, olhos):
    """Ajuste à projeção inicial, antes do zoom e deslocamento manuais. Medidas no quadro de 180 px."""
    margem = 48
    proj = matriz_janela.copy()
    proj[:, 2] += margem
    sil = cv2.warpAffine(alfa, proj, (180 + 2*margem,) * 2, flags=cv2.INTER_LINEAR) > 0.55
    ex, ey = olhos
    centros, larguras = [], []
    for y in range(round(ey) - 14, round(ey) + 18):
        # Intervalo contínuo da cabeça na altura das têmporas e das orelhas.
        linha = sil[y + margem]
        bordas = np.diff(np.r_[False, linha, False].astype(np.int8))
        for a, b in zip(np.flatnonzero(bordas == 1), np.flatnonzero(bordas == -1)):
            if a <= ex + margem < b:
                centros.append((a + b - 1) / 2 - margem)
                larguras.append(b - a)
                break
    if len(centros) < 16:
        return 0., 0., 1.
    centro, largura = np.median(centros), np.median(larguras)
    if not 45 < largura < 165:
        return 0., 0., 1.
    # Faixa central para medir o topo sem fios soltos e a base disponível no pescoço.
    x = round(centro) + margem
    faixa = max(3, round(largura * 0.22))
    nucleo = sil[:, x-faixa:x+faixa+1]
    linhas = np.flatnonzero(nucleo.mean(1) > 0.28) - margem
    if len(linhas) < 35:
        return 0., 0., 1.
    topo = linhas[0]
    # A borda inferior da foto pode ficar inclinada ao endireitar a cabeça.
    ultimas = len(sil) - 1 - nucleo[::-1].argmax(0)[nucleo.any(0)] - margem
    base = float(np.percentile(ultimas, 20))
    # A largura varia naturalmente com cabelo e pose. Combina a medida com a escala facial inicial.
    escala = float(np.clip((97.5 / largura)**0.55, 0.83, 1.24))
    # Foto de ação já cortada no pescoço: aproxima só o necessário para o retrato chegar à base.
    if base > ey + 32:
        escala = max(escala, min(1.38, 118 / largura, (179 - ey) / (base - ey)))
    topo_final = ey + (topo - ey) * escala
    base_final = ey + (base - ey) * escala
    dy = np.clip(16 - topo_final, -9, 10) * 0.45
    dy = max(dy, min(15., 180 - base_final))
    dx = 89.5 - (ex + (centro - ex) * escala)
    return float(np.clip(dx, -36, 36)), float(dy), escala
