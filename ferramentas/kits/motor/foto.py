"""Leitura da foto da camisa (frente): recorte do fundo, caixa do tronco, cores (com correção de luz), padrão do tronco,
cor das mangas e da gola, e recorte dos logos (escudo, marca e patrocinadores) com a posição deles na frente do molde.

A foto ideal é de produto: camisa de frente, esticada, fundo liso. Tudo o que sai daqui é sugestão: o editor deixa
corrigir cores, padrão e logos.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as nd

import cores as C
import molde as M

LADO_TRABALHO = 1100       # a foto é reduzida para este maior lado (velocidade)


# ------------------------------------------------------------------ recorte do fundo
def recortar(rgba):
    """Máscara bool da camisa. Usa a transparência quando há; senão o fundo liso das bordas (preenchimento a partir das
    bordas, que não come o branco de dentro da camisa); se o fundo não for liso, GrabCut (OpenCV)."""
    a = np.asarray(rgba)
    alfa = a[..., 3]
    if (alfa < 250).mean() > 0.02:
        m = alfa > 128
        metodo = "transparência"
    else:
        rgb = a[..., :3].astype(np.float32)
        h, w = alfa.shape
        b = max(2, int(0.01 * min(h, w)))
        borda = np.concatenate([rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3), rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)])
        fundo = np.median(borda, 0)
        espalhado = np.median(np.abs(borda - fundo).max(1))
        if espalhado < 10:
            lab = C.rgb_lab(rgb)
            dist = np.linalg.norm(lab - C.rgb_lab(fundo[None])[0], axis=-1)
            limiar = max(4.0, 3.0 * float(np.percentile(np.linalg.norm(C.rgb_lab(borda) - C.rgb_lab(fundo[None])[0], axis=-1), 95)) + 2.5)
            parecido = dist < limiar
            lab_b, n = nd.label(parecido)
            ids = set(np.unique(np.concatenate([lab_b[0], lab_b[-1], lab_b[:, 0], lab_b[:, -1]]))) - {0}
            fundo_m = np.isin(lab_b, list(ids))
            m = ~fundo_m
            metodo = "fundo liso"
        else:
            m = _grabcut(rgb.astype(np.uint8))
            metodo = "GrabCut"
    m = nd.binary_opening(m, iterations=2)
    lab_m, n = nd.label(m)
    if n > 1:
        tam = nd.sum(m, lab_m, range(1, n + 1))
        m = lab_m == (1 + int(np.argmax(tam)))
    m = nd.binary_fill_holes(m)
    return m, metodo


def _grabcut(rgb):
    import cv2
    h, w = rgb.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    r = (int(w * 0.03), int(h * 0.03), int(w * 0.94), int(h * 0.94))
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, r, bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
    return (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)


# ------------------------------------------------------------------ caixa do tronco
def caixa_tronco(m):
    """Caixa do tronco na foto: lados (abaixo das axilas), ombro (topo) e barra. Devolve dict com x0, x1, y0, y1, axila,
    centro e as larguras por linha (para o desenho de conferência)."""
    h, w = m.shape
    ys = np.flatnonzero(m.any(1))
    topo, fundo = int(ys[0]), int(ys[-1])
    alt = fundo - topo
    larg = np.zeros(h)
    esq = np.zeros(h)
    dir_ = np.zeros(h)
    cx_guess = w / 2
    # segmento contínuo que contém o centro estimado (o tronco), linha a linha
    meio = []
    for y in range(topo + int(0.55 * alt), fundo - int(0.04 * alt)):
        xs = np.flatnonzero(m[y])
        if len(xs):
            meio.append((xs[0] + xs[-1]) / 2)
    if meio:
        cx_guess = float(np.median(meio))
    for y in range(topo, fundo + 1):
        row = m[y]
        c = int(round(cx_guess))
        if not row[min(w - 1, max(0, c))]:
            xs = np.flatnonzero(row)
            if not len(xs):
                continue
            c = int(xs[np.argmin(np.abs(xs - c))])
        lab_r, _ = nd.label(row)
        seg = np.flatnonzero(lab_r == lab_r[c])
        esq[y], dir_[y] = seg[0], seg[-1]
        larg[y] = seg[-1] - seg[0] + 1
    faixa = slice(topo + int(0.60 * alt), fundo - int(0.06 * alt))
    lt = float(np.median(larg[faixa]))
    x0 = float(np.median(esq[faixa]))
    x1 = float(np.median(dir_[faixa]))
    # axila: subindo da barra, a primeira linha em que a largura passa de 1,22× a do tronco (as mangas)
    axila = topo + int(0.3 * alt)
    for y in range(fundo - int(0.06 * alt), topo, -1):
        if larg[y] > 1.22 * lt:
            axila = y
            break
    # barra: a última linha com pelo menos 60% da largura do tronco
    barra = fundo
    for y in range(fundo, axila, -1):
        if larg[y] >= 0.6 * lt:
            barra = y
            break
    # ombro: o alto da camisa na coluna do tronco (as golas altas ficam um pouco acima: usa o percentil 10 das colunas)
    cols = range(int(x0 + 0.15 * lt), int(x1 - 0.15 * lt))
    tops = [int(np.flatnonzero(m[:, x])[0]) for x in cols if m[:, x].any()]
    ombro = float(np.percentile(tops, 10)) if tops else float(topo)
    return {"x0": x0, "x1": x1, "y0": ombro, "y1": float(barra), "axila": float(axila), "cx": (x0 + x1) / 2,
            "largura": lt, "topo": float(topo), "fundo": float(fundo)}


# ------------------------------------------------------------------ cores
def balanco_branco(lab_px, rgb_px):
    """Ganho por canal que deixa o grupo claro e pouco saturado (o branco da camisa) neutro e claro. None se não há."""
    cent, fr = C.agrupar(lab_px[:: max(1, len(lab_px) // 40000)], k=5, juntar=9.0, minimo=0.02)
    melhores = [(c, f) for c, f in zip(cent, fr) if c[0] > 60 and math.hypot(c[1], c[2]) < 14 and f > 0.05]
    if not melhores:
        return None
    alvo = max(melhores, key=lambda cf: cf[0][0])[0]
    perto = np.linalg.norm(lab_px - alvo, axis=1) < 10
    if perto.sum() < 50:
        return None
    ref = np.percentile(rgb_px[perto], 75, axis=0)
    return np.clip(244.0 / np.maximum(ref, 1), 0.8, 1.6)


def cor_tipica(lab):
    """Cor de um grupo de pixels Lab: a/b medianos, L do lado iluminado (percentil 70)."""
    return np.array([np.percentile(lab[:, 0], 70), np.median(lab[:, 1]), np.median(lab[:, 2])], np.float32)


# ------------------------------------------------------------------ padrão
def _faixas(perfil, limiar=0.5):
    """Trechos contínuos em que perfil > limiar: [(início, fim)] em índices."""
    on = perfil > limiar
    d = np.diff(np.concatenate([[0], on.astype(int), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def detectar_padrao(rotulo, eh_b, nx, ny):
    """rotulo: imagem do tronco retificada (ny, nx) com True onde é a cor B (a segunda cor). Devolve o padrão."""
    faixa = eh_b[int(0.45 * ny):int(0.95 * ny), int(0.05 * nx):int(0.95 * nx)]
    if faixa.size == 0:
        return {"tipo": "lisa"}, 0.0
    fb = float(faixa.mean())
    if fb < 0.08 or fb > 0.92:
        return {"tipo": "lisa"}, fb
    col = eh_b[int(0.45 * ny):int(0.95 * ny)].mean(0)
    lin = eh_b[int(0.1 * ny):int(0.95 * ny), int(0.2 * nx):int(0.8 * nx)].mean(1)
    vx, vy = float(col.var()), float(lin.var())
    xs = (np.arange(nx) + 0.5) / nx - 0.5
    if vx >= vy:
        tr = _faixas(col)
        if len(tr) == 1 and abs(xs[tr[0][0]]) < 0.12 and tr[0][1] >= nx - 2:
            return {"tipo": "metades", "fase": float(xs[tr[0][0]])}, fb
        if len(tr) == 1 and tr[0][0] <= 1 and abs(xs[min(nx - 1, tr[0][1])]) < 0.12:
            return {"tipo": "metades", "fase": float(xs[min(nx - 1, tr[0][1])]), "inverter": True}, fb
        inteiras = [(a, b) for a, b in tr if a > 1 and b < nx - 1]
        if len(inteiras) >= 1:
            centros = np.array([(xs[a] + xs[b - 1]) / 2 for a, b in inteiras])
            largs = np.array([(b - a) / nx for a, b in inteiras])
            centrais = np.abs(centros) < 0.32
            if centrais.sum() >= 1:
                centros_c, largs_c = centros[centrais], largs[centrais]
            else:
                centros_c, largs_c = centros, largs
            if len(centros) >= 2:
                per = float(np.median(np.diff(np.sort(centros))))
            else:
                per = float(largs_c.mean() / max(0.2, fb))
            per = max(0.04, per)
            larg = float(np.clip(np.median(largs_c) / per, 0.08, 0.92))
            c0 = float(centros_c[np.argmin(np.abs(centros_c))])
            fase = (c0 / per) % 1.0
            if fase > 0.5:
                fase -= 1.0
            return {"tipo": "listras_v", "periodo": round(per, 4), "largura": round(larg, 3), "fase": round(fase, 3)}, fb
    else:
        tr = _faixas(lin)
        ds = (np.arange(len(lin)) + 0.5) / len(lin) * 0.85 + 0.1
        inteiras = [(a, b) for a, b in tr if a > 1 and b < len(lin) - 1]
        if len(inteiras) >= 2:
            centros = np.array([(ds[a] + ds[b - 1]) / 2 for a, b in inteiras]) * 1.4
            largs = np.array([(ds[b - 1] - ds[a]) for a, b in inteiras]) * 1.4
            per = float(np.median(np.diff(centros)))
            larg = float(np.clip(np.median(largs) / max(per, 1e-3), 0.08, 0.92))
            fase = (float(centros[0]) / per) % 1.0
            return {"tipo": "listras_h", "periodo": round(per, 4), "largura": round(larg, 3), "fase": round(fase, 3)}, fb
        if len(inteiras) == 1:
            a, b = inteiras[0]
            return {"tipo": "faixa_peito", "largura": round(float(ds[b - 1] - ds[a]), 3),
                    "fase": round(float((ds[a] + ds[b - 1]) / 2 - 0.3), 3)}, fb
    return {"tipo": "lisa", "nota": "padrão não reconhecido"}, fb


# ------------------------------------------------------------------ análise completa
def analisar(caminho, pasta_saida):
    os.makedirs(pasta_saida, exist_ok=True)
    img = Image.open(caminho)
    img.load()
    rgba = img.convert("RGBA")
    esc = min(1.0, LADO_TRABALHO / max(rgba.size))
    if esc < 1:
        rgba = rgba.resize((round(rgba.width * esc), round(rgba.height * esc)), Image.LANCZOS)
    mask, metodo = recortar(rgba)
    rgb = np.asarray(rgba)[..., :3].astype(np.float32)
    H, W = mask.shape
    cx = caixa_tronco(mask)
    x0, x1, y0, y1 = cx["x0"], cx["x1"], cx["y0"], cx["y1"]
    tw, th = x1 - x0, y1 - y0

    # balanço de branco pelo tronco
    sel = mask.copy()
    sel[:, :int(x0)] = False
    sel[:, int(x1) + 1:] = False
    sel[:int(y0 + 0.08 * th)] = False
    rgb_t = rgb[sel]
    ganho = balanco_branco(C.rgb_lab(rgb_t), rgb_t)
    if ganho is not None:
        rgb = np.clip(rgb * ganho, 0, 255)
    lab = C.rgb_lab(rgb)

    # tronco retificado (caixa da foto -> retângulo)
    nx, ny = 360, int(360 * th / max(tw, 1))
    ret = np.asarray(Image.fromarray(rgb.astype(np.uint8)).transform((nx, ny), Image.EXTENT, (x0, y0, x1, y1), Image.BILINEAR))
    ret_m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).transform((nx, ny), Image.EXTENT, (x0, y0, x1, y1), Image.NEAREST)) > 127
    ret_lab = C.rgb_lab(ret)
    amostra = ret_lab[int(0.4 * ny):int(0.97 * ny)][ret_m[int(0.4 * ny):int(0.97 * ny)]]
    cent, fr = C.agrupar(amostra[:: max(1, len(amostra) // 30000)], k=5, juntar=16.0, minimo=0.03)
    # as duas cores principais; a "base" é a que domina as laterais do tronco
    principais = cent[:2] if len(cent) >= 2 else np.array([cent[0], cent[0]])
    rot = np.linalg.norm(ret_lab[..., None, :] - principais, axis=-1).argmin(-1)
    lados = np.concatenate([rot[int(0.5 * ny):int(0.95 * ny), :int(0.08 * nx)].ravel(), rot[int(0.5 * ny):int(0.95 * ny), -int(0.08 * nx):].ravel()])
    ib = 0 if (lados == 0).mean() >= 0.5 else 1
    eh_b = (rot == (1 - ib)) & ret_m
    padrao, frac_b = detectar_padrao(rot, eh_b, nx, ny)
    grupos = [cor_tipica(amostra[np.linalg.norm(amostra - c, axis=1) < 14]) if (np.linalg.norm(amostra - c, axis=1) < 14).sum() > 30 else c
              for c in principais]
    cor_base = grupos[ib]
    cor_pad = grupos[1 - ib]
    if padrao.get("inverter"):
        cor_base, cor_pad = cor_pad, cor_base
        padrao.pop("inverter", None)

    # mangas: pixels da camisa fora das colunas do tronco, entre o ombro e a axila
    sm = mask.copy()
    sm[:, int(x0 - 0.02 * tw):int(x1 + 0.02 * tw) + 1] = False
    sm[int(cx["axila"] + 0.05 * th):] = False
    cor_manga = None
    if sm.sum() > 400:
        lm = lab[sm]
        cm, fm = C.agrupar(lm[:: max(1, len(lm) // 20000)], k=4, juntar=14.0, minimo=0.05)
        cor_manga = cor_tipica(lm[np.linalg.norm(lm - cm[0], axis=1) < 14])
    # gola: faixa logo abaixo do alto da camisa, no meio
    gl = np.zeros_like(mask)
    gy0, gy1 = int(cx["topo"]), int(cx["topo"] + 0.05 * th)
    gl[gy0:gy1, int(cx["cx"] - 0.16 * tw):int(cx["cx"] + 0.16 * tw)] = True
    gl &= mask
    cor_gola = None
    if gl.sum() > 100:
        lg = lab[gl]
        longe = np.linalg.norm(lg - cor_base, axis=1) > 18
        if longe.sum() > 60:
            cg, _ = C.agrupar(lg[longe][:: max(1, longe.sum() // 10000)], k=3, juntar=14.0, minimo=0.1)
            cor_gola = cor_tipica(lg[longe][np.linalg.norm(lg[longe] - cg[0], axis=1) < 14])
        else:
            cor_gola = cor_base

    # logos: o que destoa da reconstrução (base + padrão) dentro do tronco
    logos, depura = _logos(rgb, lab, mask, cx, padrao, cor_base, cor_pad, pasta_saida)

    res = {
        "metodo_recorte": metodo, "tamanho": [W, H], "escala": esc, "balanco": ganho.round(3).tolist() if ganho is not None else None,
        "tronco": {k: round(float(v), 1) for k, v in cx.items()},
        "cores": {"base": C.rgb_hex(C.lab_rgb(cor_base)), "padrao": C.rgb_hex(C.lab_rgb(cor_pad)),
                  "manga": C.rgb_hex(C.lab_rgb(cor_manga)) if cor_manga is not None else None,
                  "gola": C.rgb_hex(C.lab_rgb(cor_gola)) if cor_gola is not None else None},
        "paleta": [C.rgb_hex(C.lab_rgb(c)) for c in cent], "padrao": padrao, "fracao_padrao": round(frac_b, 3),
        "logos": logos,
    }
    res["conferencia"] = _conferencia(rgba, mask, cx, logos, depura, os.path.join(pasta_saida, "conferencia.png"))
    rec = rgba.copy()
    rec.putalpha(Image.fromarray(mask.astype(np.uint8) * 255))
    rec.save(os.path.join(pasta_saida, "recorte.png"))
    res["recorte"] = os.path.join(pasta_saida, "recorte.png")
    return res


def _x_tronco(xs, cx):
    return (xs - cx["x0"]) / max(1.0, cx["x1"] - cx["x0"]) - 0.5


def _logos(rgb, lab, mask, cx, padrao, cor_base, cor_pad, pasta):
    H, W = mask.shape
    x0, x1, y0, y1 = cx["x0"], cx["x1"], cx["y0"], cx["y1"]
    tw, th = x1 - x0, y1 - y0
    X, Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    xn = (X - x0) / tw - 0.5
    dn = (Y - y0) / th
    # distância (Lab, com pouco peso no brilho por causa das sombras) até o segmento entre a cor base e a do padrão:
    # as misturas das duas (bordas das listras, trama do tecido) ficam perto; logos de outra cor ficam longe
    peso = np.array([0.35, 1.0, 1.0], np.float32)
    pa, pb = cor_base * peso, cor_pad * peso
    q = lab * peso
    seg = pb - pa
    t = np.clip(((q - pa) @ seg) / max(float(seg @ seg), 1e-6), 0, 1)[..., None]
    dif = np.linalg.norm(q - (pa + t * seg), axis=-1)
    zona = mask & (X > x0 + 0.01 * tw) & (X < x1 - 0.01 * tw) & (Y > y0 + 0.06 * th) & (Y < y1 - 0.02 * th)
    zona = nd.binary_erosion(zona, iterations=3) & zona
    cand = (dif > 13) & zona
    cand = nd.binary_opening(cand, iterations=1)
    junta = nd.binary_dilation(cand, iterations=max(2, int(0.012 * tw)))
    rot, n = nd.label(junta)
    logos = []
    area_min = 0.0004 * tw * th
    for i, sl in enumerate(nd.find_objects(rot)):
        if sl is None:
            continue
        reg = (rot[sl] == i + 1) & cand[sl]
        area = float(reg.sum())
        if area < area_min:
            continue
        ys, xs = sl
        bx0, bx1, by0, by1 = xs.start, xs.stop, ys.start, ys.stop
        logos.append({"bx": [bx0, by0, bx1, by1], "area": area, "i": i + 1})
    # junta caixas que se sobrepõem
    mudou = True
    while mudou:
        mudou = False
        for i in range(len(logos)):
            for j in range(i + 1, len(logos)):
                a_, b_ = logos[i]["bx"], logos[j]["bx"]
                m = 0.01 * tw
                if a_[0] - m < b_[2] and b_[0] - m < a_[2] and a_[1] - m < b_[3] and b_[1] - m < a_[3]:
                    logos[i]["bx"] = [min(a_[0], b_[0]), min(a_[1], b_[1]), max(a_[2], b_[2]), max(a_[3], b_[3])]
                    logos[i]["area"] += logos[j]["area"]
                    del logos[j]
                    mudou = True
                    break
            if mudou:
                break
    saida = []
    k = -1
    for lg in sorted(logos, key=lambda d: -d["area"]):
        bx0, by0, bx1, by1 = lg["bx"]
        pad = int(0.006 * tw) + 2
        bx0, by0, bx1, by1 = max(0, bx0 - pad), max(0, by0 - pad), min(W, bx1 + pad), min(H, by1 + pad)
        reg_c = cand[by0:by1, bx0:bx1]
        # mancha da mesma família de cor da camisa (só mais escura: dobra, sombra numa listra) não é logo
        lab_c = lab[by0:by1, bx0:bx1][reg_c]
        if len(lab_c):
            ab = np.minimum(np.linalg.norm(lab_c[:, 1:] - cor_base[1:], axis=1), np.linalg.norm(lab_c[:, 1:] - cor_pad[1:], axis=1))
            med = np.median(lab_c[:, 1:], axis=0)
            mesmo_tom = False
            for ref in (cor_base, cor_pad):
                if math.hypot(ref[1], ref[2]) > 15 and math.hypot(med[0], med[1]) > 10:
                    dh = abs((math.degrees(math.atan2(med[1], med[0])) - math.degrees(math.atan2(ref[2], ref[1])) + 180) % 360 - 180)
                    mesmo_tom |= dh < 22
            if float(np.median(ab)) < 12 or mesmo_tom:
                continue
        cheio = _casca(reg_c) & mask[by0:by1, bx0:bx1]
        solidez = float(reg_c.sum() / max(1, cheio.sum()))
        k += 1
        fx, fy = ((bx0 + bx1) / 2 - x0) / tw, ((by0 + by1) / 2 - y0) / th
        fw, fh = (bx1 - bx0) / tw, (by1 - by0) / th
        compacto = 0.55 < (bx1 - bx0) / max(1, by1 - by0) < 1.8 and fw < 0.3
        preenche = float(reg_c.sum()) / max(1, cheio.sum())
        modo = "bloco" if compacto and preenche > 0.4 and fh < 0.25 else "cor"
        alfa = cheio if modo == "bloco" else nd.binary_dilation(reg_c, iterations=1)
        alfa_img = Image.fromarray((alfa * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
        crop = Image.fromarray(rgb[by0:by1, bx0:bx1].astype(np.uint8)).convert("RGBA")
        crop.putalpha(alfa_img)
        if crop.width < 256:
            f = 256 / crop.width
            crop = crop.resize((256, max(1, round(crop.height * f))), Image.LANCZOS)
        nome = f"logo_{k + 1}.png"
        caminho = os.path.join(pasta, nome)
        crop.save(caminho)
        # máscara "por cor" e "em bloco" guardadas para o editor trocar o recorte
        Image.fromarray(rgb[by0:by1, bx0:bx1].astype(np.uint8)).save(os.path.join(pasta, f"logo_{k + 1}_foto.png"))
        Image.fromarray((cheio * 255).astype(np.uint8)).save(os.path.join(pasta, f"logo_{k + 1}_bloco.png"))
        Image.fromarray((nd.binary_dilation(reg_c, iterations=1) * 255).astype(np.uint8)).save(os.path.join(pasta, f"logo_{k + 1}_cor.png"))
        u, v = M.foto_para_uv_frente(fx, fy)
        lu = fw * (M.FRENTE["u1"] - M.FRENTE["u0"])
        lv = fh * (M.FRENTE["v1"] - M.FRENTE["v0"])
        saida.append({"id": f"foto{k + 1}", "nome": f"Logo {k + 1}", "arquivo": caminho, "papel": "patrocinador", "modo": modo,
                      "u": round(u, 5), "v": round(v, 5), "largura": round(lu, 5), "altura": round(lv, 5),
                      "foto": [int(bx0), int(by0), int(bx1), int(by1)], "solidez": round(solidez, 3),
                      "_fx": fx, "_fy": fy, "_fw": fw, "_compacto": compacto})
    # escudo: o maior compacto no peito esquerdo de quem veste (direita da imagem); marca: o mais alto do outro lado do
    # peito (perto do ombro), pequeno. O resto é patrocinador.
    esc_c = [s for s in saida if s["_fy"] < 0.42 and s["_fx"] - 0.5 > 0.06 and s["_compacto"]]
    if esc_c:
        max(esc_c, key=lambda s: s["largura"] * s["altura"])["papel"] = "escudo"
    mar_c = [s for s in saida if s["papel"] == "patrocinador" and s["_fy"] < 0.42 and s["_fx"] - 0.5 < -0.06 and s["_fw"] < 0.25]
    if mar_c:
        min(mar_c, key=lambda s: s["_fy"])["papel"] = "marca"
    for s in saida:
        for k in ("_fx", "_fy", "_fw", "_compacto"):
            s.pop(k, None)
    for s in saida:
        s["nome"] = {"escudo": "Escudo", "marca": "Marca"}.get(s["papel"], s["nome"])
    return saida, cand


def _casca(m):
    """Fecho convexo de uma máscara (a forma \"em bloco\" de um escudo: preenche o branco de dentro)."""
    ys, xs = np.nonzero(m)
    if len(xs) < 3:
        return m.copy()
    from scipy.spatial import ConvexHull
    pts = np.stack([xs, ys], 1).astype(np.float64)
    try:
        h = ConvexHull(pts)
    except Exception:  # noqa: BLE001 — pontos colineares
        return m.copy()
    im = Image.new("L", (m.shape[1], m.shape[0]), 0)
    ImageDraw.Draw(im).polygon([tuple(pts[i]) for i in h.vertices], fill=255, outline=255)
    return np.asarray(im) > 127


def _conferencia(rgba, mask, cx, logos, cand, destino):
    """Imagem de conferência: contorno do recorte, caixa do tronco, axila e os logos achados."""
    im = rgba.convert("RGB").copy()
    a = np.asarray(im).copy()
    borda = mask ^ nd.binary_erosion(mask, iterations=2)
    a[borda] = (255, 0, 200)
    a[cand] = (a[cand] * 0.4 + np.array([255, 220, 0]) * 0.6).astype(np.uint8)
    im = Image.fromarray(a)
    d = ImageDraw.Draw(im)
    d.rectangle([cx["x0"], cx["y0"], cx["x1"], cx["y1"]], outline=(0, 200, 255), width=3)
    d.line([cx["x0"] - 30, cx["axila"], cx["x1"] + 30, cx["axila"]], fill=(0, 255, 120), width=2)
    for lg in logos:
        bx = lg["foto"]
        cor = {"escudo": (255, 60, 60), "marca": (255, 160, 0)}.get(lg["papel"], (60, 255, 60))
        d.rectangle(bx, outline=cor, width=3)
        d.text((bx[0] + 3, bx[1] + 2), lg["nome"], fill=cor)
    im.save(destino)
    return destino
