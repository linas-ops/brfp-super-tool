"""Motor do Criador de Minifaces (Python 3.12 + OpenCV, Pillow, numpy).

Processo de trabalho: lê um pedido JSON por linha na entrada padrão e responde um JSON por linha:
  {"id": 1, "cmd": "analisar", "caminho": "..."}
  {"id": 2, "cmd": "gerar", "caminho": "...", "params": {...}}            -> PNG em base64
  {"id": 3, "cmd": "exportar", "caminho": "...", "params": {...}, "saida": "...", "formato": "png"}

Enquadramento: igual às minifaces do jogo (180×180, p<ID>.png): o retângulo do rosto (detector Haar do OpenCV)
fica em x=41,5 y=38,5 com 98,5 px de lado — medido na miniface original do jogo (p158023).
Fundo: usa a transparência da foto quando existe (limpando o halo semitransparente); senão separa o jogador do
fundo com o GrabCut, guiado pelo rosto, pela cor do fundo (fundo neutro) e pelos traços de pincel do usuário.
"""
import base64
import hashlib
import io
import json
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

ALVO = (41.5, 38.5, 98.5)       # rosto na miniface 180×180 do jogo
LADO_REF = 180
HC = cv2.data.haarcascades
FRENTE = [cv2.CascadeClassifier(HC + n) for n in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
                                                   "haarcascade_frontalface_alt.xml")]
PERFIL = cv2.CascadeClassifier(HC + "haarcascade_profileface.xml")
OLHO = cv2.CascadeClassifier(HC + "haarcascade_eye.xml")
FOTOS = {}      # caminho -> (mtime, rgba)
MASCARAS = {}   # chave -> (x0, y0, alfa float32)


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


# ------------------------------------------------------------------ rosto
def _pele(rgb):
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    cr, cb = ycc[..., 1].astype(int), ycc[..., 2].astype(int)
    return ((cr > 133) & (cr < 180) & (cb > 75) & (cb < 135)).mean()


def detectar_rosto(rgba, transparente):
    """(x, y, lado) do rosto na foto, a origem da detecção e a confiança."""
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = (rgba[..., :3] * a + 200 * (1 - a)).astype(np.uint8) if transparente else rgba[..., :3].copy()
    h, w = rgb.shape[:2]
    sil = silhueta(rgba, transparente)
    topo, fundo = 0, h
    if sil is not None and sil.any():
        ys, xs = np.where(sil)
        y0, bw = ys.min(), xs.max() - xs.min() + 1
        topo = max(0, y0 - 10)
        fundo = min(h, y0 + int(max(bw * 0.95, (ys.max() - y0) * 0.22)))
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


# ------------------------------------------------------------------ fundo
def janela_da_mascara(r, w, h):
    """Janela fixa (independe do zoom do usuário) onde a máscara é calculada: ~2,7× o rosto."""
    x, y, s = r
    L = s * 2.7
    x0 = int(x + s / 2 - L / 2)
    y0 = int(y + s * 0.45 - L * 0.42)
    return x0, y0, int(L)


def recorte(rgba, x0, y0, L):
    h, w = rgba.shape[:2]
    pad = max(0, -x0, -y0, x0 + L - w, y0 + L - h)
    src = cv2.copyMakeBorder(rgba, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0)) if pad else rgba
    return src[y0 + pad:y0 + pad + L, x0 + pad:x0 + pad + L], pad


def mascara(rgba, r, modo, limpeza, tracos, transparente):
    """alfa (0..1) na janela da máscara + origem da janela."""
    h, w = rgba.shape[:2]
    x0, y0, L = janela_da_mascara(r, w, h)
    chave = hashlib.sha1(json.dumps([id(rgba), [round(v, 1) for v in r], modo, round(limpeza, 3), tracos, transparente]).encode()).hexdigest()
    if chave in MASCARAS:
        return MASCARAS[chave]
    crop, pad = recorte(rgba, x0, y0, L)
    alfa0 = crop[..., 3].astype(np.float32) / 255
    fora = alfa0 <= 0.01 if pad else np.zeros_like(alfa0, bool)   # área fora da foto
    usar_alfa = modo == "transparencia" or (modo == "auto" and transparente)
    if modo == "nenhum":
        a = alfa0
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
def matriz(r, ajuste, lado):
    x, y, s = r
    zoom = float(ajuste.get("zoom", 1.0))
    k = ALVO[2] / s * lado / LADO_REF * zoom
    cxa, cya = (ALVO[0] + ALVO[2] / 2) * lado / LADO_REF, (ALVO[1] + ALVO[2] / 2) * lado / LADO_REF
    cx, cy = x + s / 2, y + s / 2
    dx = float(ajuste.get("dx", 0)) * lado / LADO_REF
    dy = float(ajuste.get("dy", 0)) * lado / LADO_REF
    return np.array([[k, 0, cxa - cx * k + dx], [0, k, cya - cy * k + dy]], np.float32), k


def gerar(caminho, p):
    rgba = carregar(caminho)
    transp = tem_transparencia(rgba)
    r = p.get("rosto")
    if not r:
        r, origem, conf = detectar_rosto(rgba, transp)
        if r is None:
            raise ValueError("Rosto não encontrado: marque o rosto na foto (arraste o quadro) e gere de novo.")
    lado = int(p.get("lado", 180))
    modo = p.get("fundo", "auto")
    x0, y0, L, a = mascara(rgba, r, modo, float(p.get("limpeza", 0.35)), p.get("tracos") or [], transp)
    crop, _ = recorte(rgba, x0, y0, L)
    M, k = matriz(r, p.get("ajuste") or {}, lado)
    M2 = M.copy()
    M2[:, 2] += M[:, :2] @ np.array([x0, y0], np.float32)      # coordenadas da janela -> saída
    pm = np.dstack([crop[..., :3].astype(np.float32) * a[..., None], a * 255])
    out = cv2.warpAffine(pm, M2, (lado, lado), flags=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    al = np.clip(out[..., 3:4], 1e-3, 255)
    out[..., :3] = np.where(out[..., 3:4] > 0.5, out[..., :3] * 255 / al, 0)
    out = np.clip(out, 0, 255).astype(np.uint8)
    # janela da miniface na foto (para o quadro na interface)
    inv = cv2.invertAffineTransform(M)
    cantos = (inv @ np.array([[0, 0, 1], [lado, lado, 1]], np.float32).T).T
    return out, r, [float(cantos[0][0]), float(cantos[0][1]), float(cantos[1][0] - cantos[0][0])]


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
    r, origem, conf = detectar_rosto(rgba, transp)
    mini, esc = miniatura(rgba, int(q.get("maximo", 900)))
    return {"largura": int(rgba.shape[1]), "altura": int(rgba.shape[0]), "transparente": bool(transp),
            "rosto": r, "origem": origem, "confianca": conf, "foto": mini, "escala_foto": esc}


def cmd_gerar(q):
    out, r, janela = gerar(q["caminho"], q.get("params") or {})
    return {"png": png_b64(out), "rosto": r, "janela": janela}


def cmd_exportar(q):
    out, r, _ = gerar(q["caminho"], q.get("params") or {})
    destino = q["saida"]
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    Image.fromarray(out).save(destino, "PNG")
    return {"saida": destino}


COMANDOS = {"analisar": cmd_analisar, "gerar": cmd_gerar, "exportar": cmd_exportar, "ping": lambda q: {"ok": True}}


def main():
    sys.stdout.write(json.dumps({"pronto": True, "opencv": cv2.__version__}) + "\n")
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
