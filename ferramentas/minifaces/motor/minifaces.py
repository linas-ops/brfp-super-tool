"""Motor do Criador de Minifaces (Python 3.12 + OpenCV, Pillow, numpy).

Processo de trabalho: lê um pedido JSON por linha na entrada padrão e responde um JSON por linha:
  {"id": 1, "cmd": "analisar", "caminho": "..."}
  {"id": 2, "cmd": "gerar", "caminho": "...", "params": {...}}            -> PNG em base64
  {"id": 3, "cmd": "exportar", "caminho": "...", "params": {...}, "saida": "...", "formato": "png"}
  {"id": 4, "cmd": "recorte_removebg", "caminho": "...", "params": {...}, "escala": 0.5}   -> região (e JPG) para o remove.bg

Enquadramento: igual às minifaces do jogo (180×180, p<ID>.png). O rosto e 5 pontos (olhos, nariz e cantos da boca) vêm do
detector YuNet do OpenCV (modelos/); o meio dos olhos vai para um lugar fixo do quadro, a escala sai da distância entre os
olhos (corrigida quando o rosto está virado) e dos olhos à boca, e a cabeça é endireitada (olhos na horizontal). As
medidas-alvo são a mediana de 600 minifaces do BRFP 24 e batem com a miniface original do jogo (p158023). Sem os pontos
(rosto marcado à mão longe de um rosto, ou foto em que o YuNet não acha nada) vale o retângulo do rosto dos detectores Haar
do OpenCV, que fica em x=41,5 y=38,5 com 98,5 px de lado (medido na p158023).
Fundo: usa a transparência da foto quando existe (limpando o halo semitransparente); senão separa o jogador do fundo com o
GrabCut, guiado pelo rosto, pela cor do fundo (fundo neutro) e pelos traços de pincel do usuário; ou usa o recorte que o
remove.bg devolveu (o servidor chama a API e passa o arquivo em params["removebg"]).
"""
import base64
import hashlib
import io
import json
import math
import os
import sys
import traceback

import cv2
import numpy as np
from PIL import Image

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
ALVO = (41.5, 38.5, 98.5)       # retângulo do rosto (Haar) na miniface 180×180 do jogo
LADO_REF = 180
# pontos do YuNet no quadro 180: meio dos olhos, distância entre os olhos e dos olhos à boca (mediana de 600 minifaces do
# BRFP 24, conferida com os 478 pontos do MediaPipe nas saídas)
OLHOS_ALVO = (88.3, 78.2)
IOD_ALVO = 38.85
EM_ALVO = 40.06
GIRO_MAX = 20.0                 # endireita no máximo isto (graus); mais que isso é a pose da foto
YUNET = os.path.join(AQUI, "modelos", "face_detection_yunet_2023mar.onnx")
HC = cv2.data.haarcascades
FRENTE = [cv2.CascadeClassifier(HC + n) for n in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
                                                   "haarcascade_frontalface_alt.xml")]
PERFIL = cv2.CascadeClassifier(HC + "haarcascade_profileface.xml")
OLHO = cv2.CascadeClassifier(HC + "haarcascade_eye.xml")
FOTOS = {}      # caminho -> (mtime, rgba)
MASCARAS = {}   # chave -> (x0, y0, L, alfa float32)
ROSTOS = {}     # (caminho, mtime, rosto manual) -> análise do rosto
RECORTES = {}   # arquivo do remove.bg -> (mtime, alfa float32)
_YN = {}


# ------------------------------------------------------------------ fotos
def carregar(caminho):
    mt = os.path.getmtime(caminho)
    f = FOTOS.get(caminho)
    if f and f[0] == mt:
        return f[1]
    im = Image.open(caminho)
    im.load()
    rgba = np.asarray(im.convert("RGBA")).copy()
    if len(FOTOS) > 40:
        FOTOS.clear()
        MASCARAS.clear()
        ROSTOS.clear()
        RECORTES.clear()
    FOTOS[caminho] = (mt, rgba)
    return rgba


def tem_transparencia(rgba):
    a = rgba[..., 3]
    borda = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return bool((borda < 250).mean() > 0.3 or (a < 250).mean() > 0.05)


def silhueta(rgba, transparente):
    if transparente:
        return rgba[..., 3] > 128
    return None


def rgb_opaco(rgba, transparente, fundo=200):
    if not transparente:
        return rgba[..., :3].copy()
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * a + fundo * (1 - a)).astype(np.uint8)


# ------------------------------------------------------------------ rosto: YuNet (5 pontos)
def _yunet():
    if "d" not in _YN:
        d = None
        try:
            # pelo conteúdo: o caminho do Super Tool pode ter acentos, que o leitor de ONNX do OpenCV não abre
            buf = np.fromfile(YUNET, np.uint8)
            d = cv2.FaceDetectorYN.create("onnx", buf, np.array([], np.uint8), (320, 320), 0.6, 0.3, 50)
        except (OSError, cv2.error, AttributeError, TypeError):
            try:
                d = cv2.FaceDetectorYN.create(YUNET, "", (320, 320), 0.6, 0.3, 50)
            except (cv2.error, AttributeError):
                d = None
        _YN["d"] = d
    return _YN["d"]


def _yunet_detectar(rgb, regiao=None):
    """Rostos do YuNet: [(pontos 5×2, caixa x,y,w,h, nota)] em coordenadas da foto. Pontos: olho da esquerda da imagem,
    olho da direita, ponta do nariz, canto esquerdo e canto direito da boca."""
    d = _yunet()
    if d is None:
        return []
    H, W = rgb.shape[:2]
    ox = oy = 0
    if regiao:
        x0, y0, x1, y1 = [int(round(v)) for v in regiao]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 - x0 < 16 or y1 - y0 < 16:
            return []
        rgb, ox, oy = rgb[y0:y1, x0:x1], x0, y0
    h, w = rgb.shape[:2]
    esc = min(1.0, 1024 / max(h, w))
    if regiao and max(h, w) < 400:
        esc = min(4.0, 400 / max(h, w))      # rosto pequeno marcado à mão: amplia para o detector
    img = cv2.resize(rgb, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA if esc < 1 else cv2.INTER_CUBIC) if esc != 1 else rgb
    # margem: rosto encostado na borda (cabeça cortada no alto da foto) ainda é achado
    m = int(max(img.shape[:2]) * 0.08)
    img = cv2.copyMakeBorder(img, m, m, m, m, cv2.BORDER_REPLICATE)
    d.setInputSize((img.shape[1], img.shape[0]))
    try:
        _, f = d.detect(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    except cv2.error:
        return []
    if f is None:
        return []
    res = []
    for r in f:
        pts = (r[4:14].reshape(5, 2) - m) / esc + (ox, oy)
        caixa = [(r[0] - m) / esc + ox, (r[1] - m) / esc + oy, r[2] / esc, r[3] / esc]
        res.append((pts.astype(np.float64), [float(v) for v in caixa], float(r[14])))
    return res


def geometria_pontos(p, giro=None):
    """meio dos olhos, tamanho do rosto (px da foto por px do quadro 180) e inclinação (rad) pelos 5 pontos (ou a
    inclinação medida pelas pupilas, em graus)"""
    p = np.asarray(p, np.float64)
    re, le, n, mr, ml = p
    E, M = (re + le) / 2, (mr + ml) / 2
    iod = max(1e-3, float(np.linalg.norm(le - re)))
    em = float(np.linalg.norm(M - E))
    u = (le - re) / iod
    # rosto virado: o nariz sai do meio dos olhos e a distância entre os olhos encolhe (cosseno da guinada)
    t = float(np.dot(n - E, u) / iod)
    c = math.sqrt(max(0.5, 1 - (1.6 * t) ** 2))
    tam = (iod / c / IOD_ALVO + em / EM_ALVO) / 2
    return E, tam, math.radians(giro) if giro is not None else math.atan2(u[1], u[0])


def _centro_pupila(cinza, cx, cy, iod):
    """centro da pupila perto do ponto do olho (gradientes apontando para fora de um centro escuro, Timm & Barth 2011)"""
    w, h = 0.30 * iod, 0.20 * iod
    x0, x1, y0, y1 = int(cx - w), int(cx + w), int(cy - h), int(cy + h)
    if x0 < 0 or y0 < 0 or x1 > cinza.shape[1] or y1 > cinza.shape[0] or x1 - x0 < 6 or y1 - y0 < 4:
        return None
    p = cinza[y0:y1, x0:x1].astype(np.float32)
    e = 48.0 / p.shape[1]
    p = cv2.resize(p, None, fx=e, fy=e, interpolation=cv2.INTER_AREA if e < 1 else cv2.INTER_CUBIC)
    p = cv2.GaussianBlur(p, (0, 0), 0.8)
    gy, gx = np.gradient(p)
    mag = np.hypot(gx, gy)
    ys, xs = np.where(mag > mag.mean() + 0.3 * mag.std())
    if len(xs) < 10:
        return None
    gxn, gyn = gx[ys, xs] / mag[ys, xs], gy[ys, xs] / mag[ys, xs]
    H, W = p.shape
    cyg, cxg = np.mgrid[0:H, 0:W]
    cxs, cys = cxg.ravel().astype(np.float32), cyg.ravel().astype(np.float32)
    dx = xs[None, :] - cxs[:, None]
    dy = ys[None, :] - cys[:, None]
    dot = np.maximum(0, (dx * gxn[None, :] + dy * gyn[None, :]) / (np.hypot(dx, dy) + 1e-6))
    sc = (dot ** 2).mean(1) * cv2.GaussianBlur(255 - p, (0, 0), 2).ravel()
    # preferência pelo ponto do YuNet (centro do recorte): não pula para a sobrancelha
    sig = 0.25 * iod * e
    sc *= np.exp(-((cxs - (cx - x0) * e) ** 2 + (cys - (cy - y0) * e) ** 2) / (2 * sig * sig))
    sc[(cxs < 3) | (cxs > W - 4) | (cys < 3) | (cys > H - 4)] = 0
    i = int(np.argmax(sc))
    return x0 + cxs[i] / e, y0 + cys[i] / e


def inclinacao(rgb, p):
    """inclinação da cabeça (graus) pelas pupilas; o ponto dos olhos do YuNet quase não acompanha a inclinação.
    Pupila duvidosa (longe do ponto do olho, distância estranha entre as duas): fica a inclinação do YuNet."""
    p = np.asarray(p, np.float64)
    iod = float(np.linalg.norm(p[1] - p[0]))
    yunet = math.degrees(math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0]))
    if iod < 12:
        return yunet
    cinza = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    a, b = _centro_pupila(cinza, *p[0], iod), _centro_pupila(cinza, *p[1], iod)
    if not a or not b:
        return yunet
    oa, ob = (np.array(a) - p[0]) / iod, (np.array(b) - p[1]) / iod
    dist = math.hypot(b[0] - a[0], b[1] - a[1]) / iod
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    if max(abs(oa[0]), abs(ob[0])) > 0.2 or max(abs(oa[1]), abs(ob[1])) > 0.16 or not 0.8 <= dist <= 1.2 or abs(ang) > 25:
        return yunet
    return ang


def caixa_dos_pontos(p, giro=None):
    """retângulo do rosto (como o do Haar, em ALVO) equivalente aos pontos: é o que a máscara do fundo usa"""
    E, tam, ang = geometria_pontos(p, giro)
    d = (np.array([ALVO[0] + ALVO[2] / 2, ALVO[1] + ALVO[2] / 2]) - OLHOS_ALVO) * tam
    c, s = math.cos(ang), math.sin(ang)
    cx, cy = E + np.array([c * d[0] - s * d[1], s * d[0] + c * d[1]])
    lado = ALVO[2] * tam
    return [float(cx - lado / 2), float(cy - lado / 2), float(lado)]


# ------------------------------------------------------------------ rosto: Haar e silhueta (sem os pontos)
def _pele(rgb):
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    cr, cb = ycc[..., 1].astype(int), ycc[..., 2].astype(int)
    return ((cr > 133) & (cr < 180) & (cb > 75) & (cb < 135)).mean()


def faixa_da_cabeca(rgba, transparente):
    """linhas da foto onde a cabeça pode estar (alto da silhueta, quando a foto é recortada)"""
    h = rgba.shape[0]
    sil = silhueta(rgba, transparente)
    if sil is None or not sil.any():
        return 0, h, sil
    ys, xs = np.where(sil)
    y0, bw = ys.min(), xs.max() - xs.min() + 1
    return max(0, y0 - 10), min(h, y0 + int(max(bw * 0.95, (ys.max() - y0) * 0.22))), sil


def detectar_haar(rgba, transparente):
    """(x, y, lado) do rosto na foto, a origem da detecção e a confiança (detectores Haar e, sem rosto, silhueta)."""
    rgb = rgb_opaco(rgba, transparente)
    topo, fundo, sil = faixa_da_cabeca(rgba, transparente)
    reg = rgb[topo:fundo]
    g = cv2.equalizeHist(cv2.cvtColor(reg, cv2.COLOR_RGB2GRAY))
    esc = min(1.0, 900 / max(g.shape))
    if esc < 1:
        g = cv2.resize(g, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
    cands = []

    def avaliar(x, y, s, origem):
        X, Y, Sz = x / esc, y / esc + topo, s / esc
        crop = rgb[int(Y):int(Y + Sz), int(X):int(X + Sz)]
        if crop.size == 0:
            return
        gp = cv2.equalizeHist(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY))
        olhos = OLHO.detectMultiScale(gp[: gp.shape[0] // 2], 1.05, 3, minSize=(max(6, int(Sz * 0.1)),) * 2)
        rel = (Y - topo) / max(1, fundo - topo)
        sc = _pele(crop) * 2 + min(len(olhos), 2) * 0.6 - rel * 1.5 + (0.2 if origem == "frente" else 0)
        cands.append((sc, X, Y, Sz, origem))

    minimo = max(24, int(g.shape[1] * 0.12)) if sil is not None else max(24, int(min(g.shape) * 0.06))
    for viz in (4, 3):
        for c in FRENTE:
            for (x, y, s, _) in c.detectMultiScale(g, 1.05, viz, minSize=(minimo, minimo)):
                avaliar(x, y, s, "frente")
        if cands:
            break
    if not cands:
        # perfil (o detector só olha para um lado: tenta a imagem espelhada também)
        for (x, y, s, _) in PERFIL.detectMultiScale(g, 1.05, 3, minSize=(minimo, minimo)):
            avaliar(x, y, s, "perfil")
        gf = cv2.flip(g, 1)
        for (x, y, s, _) in PERFIL.detectMultiScale(gf, 1.05, 3, minSize=(minimo, minimo)):
            avaliar(g.shape[1] - x - s, y, s, "perfil")
    if cands:
        cands.sort(reverse=True)
        b = cands[0]
        grupo = [c for c in cands if abs(c[1] - b[1]) < b[3] * 0.3 and abs(c[2] - b[2]) < b[3] * 0.3]
        r = [float(np.mean([c[i] for c in grupo])) for i in (1, 2, 3)]
        if b[4] == "perfil":   # o retângulo de perfil é menor e deslocado para a nuca: aproxima do frontal
            r = [r[0] - r[2] * 0.04, r[1] + r[2] * 0.02, r[2] * 1.06]
        return r, b[4], round(float(min(1.0, max(0.2, b[0] / 2.5))), 2)
    # plano B: silhueta (cabeça = parte de cima da silhueta)
    if sil is not None and sil.any():
        ys, xs = np.where(sil)
        y0 = ys.min()
        larg = []
        for dy in range(0, int((ys.max() - y0) * 0.25)):
            row = np.where(sil[y0 + dy])[0]
            if len(row):
                larg.append((dy, row.min(), row.max()))
        if larg:
            # largura da cabeça: mediana das linhas entre 15% e 45% da altura da cabeça estimada
            cab = [l for l in larg[: max(5, len(larg) // 2)]]
            lw = np.median([l[2] - l[1] for l in cab[len(cab) // 4:]])
            cx = np.median([(l[1] + l[2]) / 2 for l in cab])
            s = lw * 0.82
            return [float(cx - s / 2), float(y0 + lw * 0.28), float(s)], "silhueta", 0.2
    return None, "nenhum", 0.0


# ------------------------------------------------------------------ rosto: análise (com cache)
def _escolher(rostos, rgba, transparente):
    """o rosto do jogador quando o YuNet acha mais de um: o maior e mais nítido, na parte de cima da silhueta"""
    topo, fundo, _ = faixa_da_cabeca(rgba, transparente)

    def nota(r):
        pts, cx, sc = r
        y = pts[:2, 1].mean()
        dentro = 1.0 if topo <= y <= fundo else 0.35
        return sc * math.sqrt(max(1.0, cx[2] * cx[3])) * dentro
    return max(rostos, key=nota)


def analisar_rosto(caminho, rgba, transparente, manual=None):
    """{"rosto": [x, y, lado], "pontos": 5×2 ou None, "origem", "confianca"} — da foto inteira ou do rosto marcado à mão"""
    chave = (caminho, FOTOS.get(caminho, (0,))[0], tuple(round(v, 1) for v in manual) if manual else None)
    if chave in ROSTOS:
        return ROSTOS[chave]
    rgb = rgb_opaco(rgba, transparente)
    if manual:
        x, y, s = manual
        # procura os pontos perto do quadro marcado: valem se o rosto achado tiver o centro dentro dele e tamanho parecido
        achados = [r for r in _yunet_detectar(rgb, (x - s, y - s, x + 2 * s, y + 2 * s))
                   if x <= r[0][:, 0].mean() <= x + s and y <= r[0][:, 1].mean() <= y + s and 0.35 < r[1][2] / s < 2.5]
        if achados:
            pts = max(achados, key=lambda r: r[2])[0]
            info = {"rosto": [float(v) for v in manual], "pontos": pts.tolist(), "giro": round(inclinacao(rgb, pts), 2),
                    "origem": "manual", "confianca": 1.0}
        else:
            info = {"rosto": [float(v) for v in manual], "pontos": None, "giro": 0.0, "origem": "manual", "confianca": 1.0}
    else:
        achados = _yunet_detectar(rgb)
        if achados:
            pts, _, sc = _escolher(achados, rgba, transparente)
            giro = round(inclinacao(rgb, pts), 2)
            info = {"rosto": caixa_dos_pontos(pts, giro), "pontos": pts.tolist(), "giro": giro, "origem": "pontos",
                    "confianca": round(min(1.0, max(0.2, sc)), 2)}
        else:
            r, origem, conf = detectar_haar(rgba, transparente)
            info = {"rosto": r, "pontos": None, "giro": 0.0, "origem": origem, "confianca": conf}
    ROSTOS[chave] = info
    return info


# ------------------------------------------------------------------ fundo
def janela_da_mascara(r, fator=2.7):
    """Janela fixa (independe do zoom do usuário) onde a máscara é calculada: ~2,7× o rosto (3,2× sem o GrabCut)."""
    x, y, s = r
    L = s * fator
    x0 = int(x + s / 2 - L / 2)
    y0 = int(y + s * 0.45 - L * 0.42)
    return x0, y0, int(L)


def fator_da_janela(modo, transparente):
    usar_grabcut = modo == "remover" or (modo == "auto" and not transparente)
    return 2.7 if usar_grabcut else 3.2


def recorte(rgba, x0, y0, L):
    h, w = rgba.shape[:2]
    pad = max(0, -x0, -y0, x0 + L - w, y0 + L - h)
    src = cv2.copyMakeBorder(rgba, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0)) if pad else rgba
    return src[y0 + pad:y0 + pad + L, x0 + pad:x0 + pad + L], pad


def mascara(rgba, r, modo, limpeza, tracos, transparente, removebg=None):
    """alfa (0..1) na janela da máscara + origem da janela."""
    x0, y0, L = janela_da_mascara(r, fator_da_janela(modo, transparente))
    extra = [removebg.get("arquivo"), removebg.get("regiao")] if (modo == "removebg" and removebg) else None
    chave = hashlib.sha1(json.dumps([id(rgba), [round(v, 1) for v in r], modo, round(limpeza, 3), tracos, transparente,
                                     extra]).encode()).hexdigest()
    if chave in MASCARAS:
        return MASCARAS[chave]
    crop, pad = recorte(rgba, x0, y0, L)
    alfa0 = crop[..., 3].astype(np.float32) / 255
    fora = alfa0 <= 0.01 if pad else np.zeros_like(alfa0, bool)   # área fora da foto
    usar_alfa = modo == "transparencia" or (modo == "auto" and transparente)
    if modo == "nenhum":
        a = alfa0
    elif modo == "removebg":
        if not removebg:
            raise ValueError("Falta o recorte do remove.bg desta foto.")
        a = _alfa_removebg(removebg, x0, y0, L)
        # limpeza: tira o contorno semitransparente que sobra (menos que na transparência da foto: o remove.bg já limpa)
        lo = 0.04 + 0.4 * limpeza
        a = np.clip((a - lo) / max(0.05, 1 - lo - 0.04), 0, 1)
        a = a * a * (3 - 2 * a)
        if transparente:
            a = np.minimum(a, alfa0)
        if tracos:
            a = _aplicar_tracos_alfa(a, tracos, x0, y0)
        a[fora] = 0
    elif usar_alfa:
        lo = 0.12 + 0.5 * limpeza
        a = np.clip((alfa0 - lo) / max(0.05, 1 - lo - 0.1), 0, 1)
        a = a * a * (3 - 2 * a)
        # halo (brilho semitransparente de cor única atrás do jogador): sai pela cor, não só pela opacidade,
        # para não comer o cabelo (que é semitransparente mas escuro)
        semi = (alfa0 > 0.03) & (alfa0 < 0.55)
        if semi.sum() > 300:
            rgbf = crop[..., :3].astype(np.float32)
            cor = np.median(rgbf[semi], axis=0)
            if float(np.median(np.linalg.norm(rgbf[semi] - cor, axis=1))) < 25:      # o halo tem uma cor só
                halo = (alfa0 < 0.88) & (np.linalg.norm(rgbf - cor, axis=2) < 30 + 50 * limpeza)
                a = np.where(halo, 0, a).astype(np.float32)
                a = cv2.GaussianBlur(a, (0, 0), 0.6)
        if tracos:
            a = _aplicar_tracos_alfa(a, tracos, x0, y0)
    else:
        a = _grabcut(crop[..., :3], (r[0] - x0, r[1] - y0, r[2]), limpeza, tracos, x0, y0)
        a[fora] = 0
    res = (x0, y0, L, a.astype(np.float32))
    MASCARAS[chave] = res
    return res


def _alfa_removebg(rb, x0, y0, L):
    """alfa do recorte do remove.bg (feito numa região da foto, talvez reduzida) levado para a janela da máscara"""
    arq = rb["arquivo"]
    mt = os.path.getmtime(arq)
    c = RECORTES.get(arq)
    if not c or c[0] != mt:
        im = Image.open(arq)
        im.load()
        al = np.asarray(im.convert("RGBA"))[..., 3].astype(np.float32) / 255
        RECORTES[arq] = c = (mt, al)
    al = c[1]
    rx, ry, rw, rh = rb["regiao"]
    sx, sy = al.shape[1] / rw, al.shape[0] / rh
    M = np.array([[1 / sx, 0, rx - x0], [0, 1 / sy, ry - y0]], np.float32)
    return cv2.warpAffine(al, M, (L, L), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def regiao_removebg(r, W, H, fator=3.6):
    """região da foto mandada ao remove.bg: a janela da máscara (3,2× o rosto) com folga, para o recorte servir mesmo se
    o quadro do rosto mudar um pouco; só a parte dentro da foto. Com fator=3.2: a região que a máscara precisa."""
    x0, y0, L = janela_da_mascara(r, fator)
    x1, y1 = min(W, x0 + L), min(H, y0 + L)
    x0, y0 = max(0, x0), max(0, y0)
    return [int(x0), int(y0), int(max(1, x1 - x0)), int(max(1, y1 - y0))]


def _aplicar_tracos_alfa(a, tracos, x0, y0):
    m = np.full(a.shape, 127, np.uint8)
    for t in tracos:
        pts = [(int(p[0] - x0), int(p[1] - y0)) for p in t["pontos"]]
        cor = 255 if t["manter"] else 0
        for p, q in zip(pts[:-1], pts[1:] or pts):
            cv2.line(m, p, q, cor, max(1, int(t["raio"] * 2)))
        if len(pts) == 1:
            cv2.circle(m, pts[0], max(1, int(t["raio"])), cor, -1)
    a = a.copy()
    a[m == 255] = 1
    a[m == 0] = 0
    return a


def _grabcut(rgb, r, limpeza, tracos, x0, y0):
    H, W = rgb.shape[:2]
    esc = min(1.0, 520 / max(H, W))
    small = cv2.resize(rgb, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA) if esc < 1 else rgb.copy()
    h, w = small.shape[:2]
    x, y, s = (v * esc for v in r)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
    bw = max(3, int(min(h, w) * 0.04))
    borda = np.concatenate([lab[:bw].reshape(-1, 3), lab[: int(h * 0.6), :bw].reshape(-1, 3), lab[: int(h * 0.6), -bw:].reshape(-1, 3)])
    med = np.median(borda, 0)
    disp = float(np.median(np.linalg.norm(borda - med, axis=1)))
    neutro = disp < 6 + 8 * limpeza
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    cx, cy = x + s / 2, y + s / 2
    cv2.ellipse(mask, (int(cx), int(cy - s * 0.05)), (int(s * 0.62), int(s * 0.80)), 0, 0, 360, cv2.GC_PR_FGD, -1)
    pts = np.array([[cx - s * 0.35, y + s * 1.0], [cx + s * 0.35, y + s * 1.0], [cx + s * 1.5, h], [cx - s * 1.5, h]], np.int32)
    cv2.fillPoly(mask, [pts], cv2.GC_PR_FGD)
    cv2.ellipse(mask, (int(cx), int(cy + s * 0.05)), (int(s * 0.3), int(s * 0.38)), 0, 0, 360, cv2.GC_FGD, -1)
    if neutro:
        d = np.linalg.norm(lab - med, axis=2)
        mask[(d < 6 + 10 * limpeza) & (mask != cv2.GC_FGD)] = cv2.GC_BGD
    else:
        mask[:bw] = np.where(mask[:bw] == cv2.GC_PR_BGD, cv2.GC_BGD, mask[:bw])
    for t in tracos or []:
        p = [(int((q[0] - x0) * esc), int((q[1] - y0) * esc)) for q in t["pontos"]]
        cor = cv2.GC_FGD if t["manter"] else cv2.GC_BGD
        rr = max(1, int(t["raio"] * esc))
        for a_, b_ in zip(p[:-1], p[1:]):
            cv2.line(mask, a_, b_, cor, rr * 2)
        for q in p:
            cv2.circle(mask, q, rr, cor, -1)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), mask, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        pass
    fg = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.uint8)
    n, cc = cv2.connectedComponents(fg)
    idc = cc[int(min(h - 1, max(0, cy))), int(min(w - 1, max(0, cx)))]
    if idc:
        fg = (cc == idc).astype(np.uint8)
    inv = (1 - fg).astype(np.uint8)
    n2, cc2 = cv2.connectedComponents(inv)
    for i in range(1, n2):
        reg = cc2 == i
        ys, xs = np.where(reg)
        if ys.min() > 0 and xs.min() > 0 and xs.max() < w - 1 and reg.sum() < h * w * 0.02:
            fg[reg] = 1
    a = cv2.GaussianBlur(fg.astype(np.float32), (0, 0), max(0.7, s * 0.006))
    if esc < 1:
        a = cv2.resize(a, (W, H), interpolation=cv2.INTER_LINEAR)
    return np.clip(a, 0, 1)


# ------------------------------------------------------------------ gerar a miniface
def matriz(info, ajuste, lado, endireitar=True):
    """foto -> miniface: matriz 2×3, escala e giro (graus) da foto dentro do quadro"""
    zoom = float(ajuste.get("zoom", 1.0))
    ref = lado / LADO_REF
    if info.get("pontos") is not None:
        centro, tam, ang = geometria_pontos(info["pontos"], info.get("giro"))
        ang = max(-math.radians(GIRO_MAX), min(math.radians(GIRO_MAX), ang)) if endireitar else 0.0
        alvo = np.array(OLHOS_ALVO) * ref
    else:
        x, y, s = info["rosto"]
        centro, tam, ang = np.array([x + s / 2, y + s / 2]), s / ALVO[2], 0.0
        alvo = np.array([ALVO[0] + ALVO[2] / 2, ALVO[1] + ALVO[2] / 2]) * ref
    k = ref / tam * zoom
    c, s_ = math.cos(-ang) * k, math.sin(-ang) * k
    A = np.array([[c, -s_], [s_, c]])
    t = alvo + np.array([float(ajuste.get("dx", 0)), float(ajuste.get("dy", 0))]) * ref - A @ centro
    return np.hstack([A, t[:, None]]).astype(np.float32), k, math.degrees(ang)


def gerar(caminho, p):
    rgba = carregar(caminho)
    transp = tem_transparencia(rgba)
    info = analisar_rosto(caminho, rgba, transp, p.get("rosto"))
    if info["rosto"] is None:
        raise ValueError("Rosto não encontrado: marque o rosto na foto (arraste o quadro) e gere de novo.")
    r = info["rosto"]
    lado = int(p.get("lado", 180))
    modo = p.get("fundo", "auto")
    x0, y0, L, a = mascara(rgba, r, modo, float(p.get("limpeza", 0.35)), p.get("tracos") or [], transp, p.get("removebg"))
    crop, _ = recorte(rgba, x0, y0, L)
    M, k, giro = matriz(info, p.get("ajuste") or {}, lado, p.get("endireitar", True))
    M2 = M.copy()
    M2[:, 2] += M[:, :2] @ np.array([x0, y0], np.float32)      # coordenadas da janela -> saída
    pm = np.dstack([crop[..., :3].astype(np.float32) * a[..., None], a * 255])
    out = cv2.warpAffine(pm, M2, (lado, lado), flags=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    al = np.clip(out[..., 3:4], 1e-3, 255)
    out[..., :3] = np.where(out[..., 3:4] > 0.5, out[..., :3] * 255 / al, 0)
    out = np.clip(out, 0, 255).astype(np.uint8)
    # janela da miniface na foto (para o quadro na interface): canto de cima à esquerda, lado e giro
    inv = cv2.invertAffineTransform(M)
    c0 = inv @ np.array([0, 0, 1], np.float32)
    return out, info, [float(c0[0]), float(c0[1]), float(lado / k), round(giro, 2)]


def png_b64(arr):
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "PNG", optimize=False)
    return base64.b64encode(b.getvalue()).decode()


def miniatura(rgba, maximo=900):
    h, w = rgba.shape[:2]
    esc = min(1.0, maximo / max(h, w))
    im = Image.fromarray(rgba)
    if esc < 1:
        im = im.resize((max(1, int(w * esc)), max(1, int(h * esc))), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode(), esc


# ------------------------------------------------------------------ comandos
def cmd_analisar(q):
    rgba = carregar(q["caminho"])
    transp = tem_transparencia(rgba)
    info = analisar_rosto(q["caminho"], rgba, transp)
    mini, esc = miniatura(rgba, int(q.get("maximo", 900)))
    return {"largura": int(rgba.shape[1]), "altura": int(rgba.shape[0]), "transparente": bool(transp),
            "rosto": info["rosto"], "pontos": info["pontos"], "origem": info["origem"], "confianca": info["confianca"],
            "foto": mini, "escala_foto": esc}


def cmd_gerar(q):
    out, info, janela = gerar(q["caminho"], q.get("params") or {})
    return {"png": png_b64(out), "rosto": info["rosto"], "pontos": info["pontos"], "janela": janela}


def cmd_exportar(q):
    out, _, _ = gerar(q["caminho"], q.get("params") or {})
    destino = q["saida"]
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    Image.fromarray(out).save(destino, "PNG")
    return {"saida": destino}


def cmd_recorte_removebg(q):
    """Região da foto para o remove.bg e quantos px da foto viram 1 px da miniface; com "escala", também a imagem (JPG
    reduzido por essa escala, sobre fundo claro quando a foto já tem transparência)."""
    caminho, p = q["caminho"], q.get("params") or {}
    rgba = carregar(caminho)
    transp = tem_transparencia(rgba)
    info = analisar_rosto(caminho, rgba, transp, p.get("rosto"))
    if info["rosto"] is None:
        raise ValueError("Rosto não encontrado: marque o rosto na foto antes de usar o remove.bg.")
    H, W = rgba.shape[:2]
    reg = regiao_removebg(info["rosto"], W, H)
    _, k, _ = matriz(info, {}, int(p.get("lado", 180)), p.get("endireitar", True))
    res = {"regiao": reg, "necessaria": regiao_removebg(info["rosto"], W, H, 3.2), "k": float(k), "foto": [int(W), int(H)]}
    if q.get("escala"):
        e = float(q["escala"])
        x, y, w, h = reg
        crop = rgb_opaco(rgba[y:y + h, x:x + w], transp, 242)
        tw, th = max(1, int(round(w * e))), max(1, int(round(h * e)))
        if (tw, th) != (w, h):
            crop = cv2.resize(crop, (tw, th), interpolation=cv2.INTER_AREA if e < 1 else cv2.INTER_CUBIC)
        b = io.BytesIO()
        Image.fromarray(crop).save(b, "JPEG", quality=95)
        res.update(jpg=base64.b64encode(b.getvalue()).decode(), tamanho=[tw, th])
    return res


COMANDOS = {"analisar": cmd_analisar, "gerar": cmd_gerar, "exportar": cmd_exportar, "recorte_removebg": cmd_recorte_removebg,
            "ping": lambda q: {"ok": True, "yunet": _yunet() is not None}}


def main():
    sys.stdout.write(json.dumps({"pronto": True, "opencv": cv2.__version__, "yunet": _yunet() is not None}) + "\n")
    sys.stdout.flush()
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        q = {}
        try:
            q = json.loads(linha)
            r = COMANDOS[q["cmd"]](q)
            r["id"] = q.get("id")
        except Exception as ex:  # noqa: BLE001
            r = {"id": q.get("id"), "erro": str(ex) if isinstance(ex, (ValueError, FileNotFoundError, KeyError)) else
                 f"{type(ex).__name__}: {ex}", "rastro": traceback.format_exc(limit=5)}
        sys.stdout.write(json.dumps(r) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
