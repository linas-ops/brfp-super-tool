"""Geração do kit: recolore a textura de cor de um kit doador (ou um template de recorte, em que cada cor lisa é uma
parte), desenha o padrão do tronco, a gola e os logos, e grava a pasta no formato do jogo (texturas, escudo, marca e
hotspot). Os mapas de tecido (normal, coeff, taa, weave) vêm do doador ou genéricos (preenchidos com o valor mais comum).
"""
import glob
import json
import math
import os
import re
import shutil

import numpy as np
from PIL import Image

import cores as C
import molde as M

PECAS = ("jersey", "shorts", "socks")
TIPOS = {"home": 0, "away": 1, "goalie_home": 2, "third": 3, "fourth": 4}
SIGMA_CAMADA = 7.0          # ΔE da transição suave entre camadas do doador
_CACHE_DOADOR = {}
_CACHE_TEMPLATE = {}
# hotspots que o editor posiciona (além do escudo e da marca): grupo/nome no .hotspot
HOTSPOTS_EDITAVEIS = ("jersey/numberfront", "jersey/numberback", "jersey/name", "shorts/number")


class ErroKit(Exception):
    pass


# ------------------------------------------------------------------ doador
def arquivos_doador(pasta):
    """Acha os arquivos de um kit exportado (pasta <tipo>_<n>_<v> com jersey/, shorts/, socks/ e o .hotspot)."""
    pasta = os.path.abspath(pasta)
    hs = glob.glob(os.path.join(pasta, "hotspots_*.hotspot"))
    m = re.match(r"hotspots_(\d+)_(\d+)_(\d+)\.hotspot$", os.path.basename(hs[0])) if hs else None
    if not m:
        raise ErroKit(f"Não parece a pasta de um kit (falta o hotspots_<id>_<n>_<v>.hotspot): {pasta}")
    tid, n, v = m.groups()
    suf = f"{tid}_{n}_{v}"
    arqs = {"hotspot": hs[0], "teamid": int(tid), "n": int(n), "v": int(v), "pasta": pasta, "outros": []}
    for peca in PECAS:
        sub = os.path.join(pasta, peca)
        cor = os.path.join(sub, f"{peca}_{suf}_color.png")
        if not os.path.isfile(cor):
            raise ErroKit(f"Falta {peca}/{os.path.basename(cor)} no doador.")
        arqs[peca] = cor
        for f in sorted(glob.glob(os.path.join(sub, "*.png"))):
            if os.path.normcase(f) != os.path.normcase(cor):
                arqs["outros"].append(f)
    arqs["sufixo"] = suf
    return arqs


def _amostra_lab(img, lado=384):
    a = np.asarray(img.convert("RGB").resize((lado, max(1, lado * img.height // img.width)), Image.BILINEAR))
    return C.rgb_lab(a.reshape(-1, 3))


def analisar_doador(pasta):
    """Camadas de cor (paleta) de cada peça do doador e em que partes elas aparecem."""
    arqs = arquivos_doador(pasta)
    chave = (arqs["pasta"], os.path.getmtime(arqs["jersey"]))
    if chave in _CACHE_DOADOR:
        return _CACHE_DOADOR[chave]
    res = {"pasta": arqs["pasta"], "teamid": arqs["teamid"], "n": arqs["n"], "v": arqs["v"], "pecas": {}}
    for peca in PECAS:
        img = Image.open(arqs[peca])
        lab = _amostra_lab(img)
        centros, fr = C.agrupar(lab, k=6, juntar=11.0, minimo=0.004)
        w, h = (384, 384 * img.height // img.width)
        mas = M.mascaras(peca, w, h)
        rot = ((lab[:, None, :] - centros[None]) ** 2).sum(-1).argmin(1).reshape(h, w)
        camadas = []
        for i, c in enumerate(centros):
            m = rot == i
            partes = {}
            for nome in ("tronco", "manga", "gola", "corpo", "cos"):
                if nome in mas:
                    partes[nome] = round(float(mas[nome][m].sum() / max(1.0, mas[nome].sum())), 4)
            camadas.append({"origem": C.rgb_hex(C.lab_rgb(c)), "lab": [round(float(x), 2) for x in c],
                            "fracao": round(float(fr[i]), 4), "partes": partes})
        res["pecas"][peca] = {"camadas": camadas, "tamanho": [img.width, img.height]}
    with open(arqs["hotspot"], encoding="utf-8") as f:
        res["hotspot"] = json.load(f)
    _CACHE_DOADOR[chave] = res
    return res


def analisar_template(caminho):
    """Partes de um template de recorte: cada cor lisa da imagem é uma parte. Os nomes vêm do .json ao lado
    ({"#ff0000": "Corpo", ...}), quando existe."""
    chave = (os.path.abspath(caminho), os.path.getmtime(caminho))
    if chave in _CACHE_TEMPLATE:
        return _CACHE_TEMPLATE[chave]
    img = Image.open(caminho).convert("RGBA")
    a = np.asarray(img.resize((512, max(1, 512 * img.height // img.width)), Image.NEAREST)).astype(np.int16)
    # só pixels "lisos" (iguais aos vizinhos) e opacos: as bordas suavizadas entre duas partes não viram parte
    igual = (np.abs(a[:-1, :-1, :3] - a[1:, :-1, :3]).max(-1) < 6) & (np.abs(a[:-1, :-1, :3] - a[:-1, 1:, :3]).max(-1) < 6)
    liso = igual & (a[:-1, :-1, 3] > 200)
    px = a[:-1, :-1, :3][liso].astype(np.float32)
    if not len(px):
        raise ErroKit("O template não tem nenhuma área de cor lisa.")
    lab = C.rgb_lab(px)
    centros, fr = C.agrupar(lab[:: max(1, len(lab) // 60000)], k=10, juntar=7.0, minimo=0.002)
    nomes = {}
    j = os.path.splitext(caminho)[0] + ".json"
    if os.path.isfile(j):
        try:
            with open(j, encoding="utf-8") as f:
                nomes = {C.rgb_hex(C.hex_rgb(k)): v for k, v in json.load(f).items()}
        except (OSError, ValueError):
            nomes = {}
    camadas = []
    for i, c in enumerate(centros):
        hexa = C.rgb_hex(C.lab_rgb(c))
        nome = None
        for h, n in nomes.items():
            if float(np.linalg.norm(C.hex_lab(h) - c)) < 20:
                nome = n
                break
        camadas.append({"origem": hexa, "fracao": round(float(fr[i]), 4), "nome": nome or f"Parte {i + 1}"})
    r = {"arquivo": os.path.abspath(caminho), "camadas": camadas, "tamanho": [img.width, img.height]}
    _CACHE_TEMPLATE[chave] = r
    return r


PALETA_INICIAL = ["#f4f6f8", "#1f5fbf", "#d32f2f", "#111418", "#f2c230", "#1f9a5c", "#7b3fa0", "#ff7a1a"]


def camadas_template(caminho, cores_atuais=None):
    """Camadas (todas com cor própria) de um template, com cores iniciais: as que o projeto já tinha, na ordem, ou a
    paleta inicial."""
    t = analisar_template(caminho)
    cores_atuais = list(cores_atuais or [])
    out = []
    for i, c in enumerate(t["camadas"]):
        cor = cores_atuais[i] if i < len(cores_atuais) else PALETA_INICIAL[i % len(PALETA_INICIAL)]
        out.append({"origem": c["origem"], "papel": "fixa", "cor": cor, "nome": c["nome"]})
    return out


def origem_cor(projeto, peca, arqs):
    """(caminho da imagem de origem da cor, tamanho forçado) da peça: o template escolhido ou a cor do doador."""
    fonte = (projeto["pecas"][peca].get("fonte") or {})
    if fonte.get("tipo") == "template" and fonte.get("arquivo") and os.path.isfile(fonte["arquivo"]):
        return fonte["arquivo"], Image.open(arqs[peca]).size
    return arqs[peca], None


def caixa_hotspot(hotspot, grupo, nome):
    for h in hotspot.get("Hotspots", []):
        if h.get("Group") == grupo and h.get("Name") == nome:
            b = h["Bounds"]
            return {"x0": b["X"], "y0": b["Y"], "x1": b["Z"], "y1": b["W"]}
    return None


# ------------------------------------------------------------------ projeto padrão a partir do doador e de uma paleta
def projeto_inicial(doador, base="#ffffff", padrao="#0a6d4a", manga=None, gola=None):
    d = analisar_doador(doador)
    p = {"versao": 1, "time": {"nome": "Novo time", "teamid": 0, "pasta": "novo_time"}, "tipo": "home", "variacao": 0,
         "doador": d["pasta"], "mapas": "doador", "pecas": {}, "escudo": None, "marca": None}
    for peca in PECAS:
        cam = []
        camadas = d["pecas"][peca]["camadas"]
        principal = np.array(camadas[0]["lab"], np.float32)
        for i, c in enumerate(camadas):
            # tons da cor principal (a trama/desenho tom sobre tom do doador) seguem a peça; o resto são frisos e detalhes
            tom = i == 0 or float(np.linalg.norm(np.array(c["lab"], np.float32) - principal)) < 22 or c["fracao"] > 0.15
            cam.append({"origem": c["origem"], "papel": "base" if tom else "fixa", "cor": base if tom else padrao})
        cores = {"base": base, "padrao": padrao}
        if peca == "jersey":
            cores.update(manga=manga or base, gola=gola or padrao, punho=None)
        if peca == "shorts":
            cores.update(cos=None)
        if peca == "socks":
            cores.update(cano=None)
        p["pecas"][peca] = {"camadas": cam, "cores": cores, "detalhe": 1.0, "logos": [],
                            "padrao": {"tipo": "lisa", "periodo": 0.2, "largura": 0.5, "fase": 0.0, "angulo": 35.0}}
    hs = d["hotspot"]
    for chave, nome in (("escudo", "team"), ("marca", "brand")):
        cx = caixa_hotspot(hs, "jersey", nome)
        if cx:
            p[chave] = {"arquivo": None, "caixa": cx, "caixa_calcao": caixa_hotspot(hs, "shorts", nome)}
    p["hotspots"] = hotspots_doador(hs)
    return p


def hotspots_doador(hs):
    out = {}
    for k in HOTSPOTS_EDITAVEIS:
        g, n = k.split("/")
        cx = caixa_hotspot(hs, g, n)
        if cx:
            out[k] = cx
    return out


# ------------------------------------------------------------------ padrões do tronco
def _faixa(dist, meia, px):
    """1 dentro de |dist| < meia, com borda suave de ~1 px."""
    return np.clip((meia - np.abs(dist)) / px + 0.5, 0.0, 1.0)


def alfa_padrao(pd, x, d, frente, px):
    """Quanto do pixel é da cor do padrão (0..1). x: -0,5..0,5 na largura; d: 0 ombro … 1 barra."""
    t = pd.get("tipo", "lisa")
    per = max(0.01, float(pd.get("periodo", 0.2)))
    larg = float(pd.get("largura", 0.5))
    fase = float(pd.get("fase", 0.0))
    ang = math.radians(float(pd.get("angulo", 35.0)))
    if t == "lisa":
        return np.zeros_like(x)
    if t in ("listras_v", "listras_h", "xadrez"):
        def listras(c, passo_px):
            r = np.mod(c - fase * per + per / 2, per) - per / 2
            return _faixa(r, larg * per / 2, passo_px)
        if t == "listras_v":
            return listras(x, px)
        if t == "listras_h":
            return listras(d * 1.4, px * 1.4)
        a, b = listras(x, px), listras(d * 1.4, px * 1.4)
        return np.clip(a + b - 2 * a * b, 0, 1)
    if t == "metades":
        return np.clip((x - fase) / px + 0.5, 0, 1)
    if t == "faixa_diagonal":
        dist = (x - fase - (d * 1.4 - 0.7) * math.tan(ang)) * math.cos(ang)
        return _faixa(dist, larg / 2, px) * frente
    if t == "faixa_peito":
        return _faixa(d - (0.3 + fase), larg / 2, px * 0.9)
    if t == "v":
        return _faixa(d * 1.4 - (0.12 + fase + np.abs(x) * math.tan(ang)), larg / 2, px * 1.4) * frente
    if t == "degrade":
        z = np.clip((d - fase) / max(0.02, larg), 0, 1)
        return z * z * (3 - 2 * z)
    return np.zeros_like(x)


# ------------------------------------------------------------------ recolorir
def _campos_regiao(peca, cfg, mas, x, d, frente, px):
    """Cor (Lab) que a camada 'base' recebe em cada pixel, pelas partes da peça e o padrão."""
    cores = cfg["cores"]
    base = C.hex_lab(cores["base"])
    pad = C.hex_lab(cores.get("padrao") or cores["base"])
    a = alfa_padrao(cfg.get("padrao") or {}, x, d, frente, px)[..., None]
    if peca == "jersey":
        a = a * mas["tronco"][..., None]
    elif peca == "shorts":
        a = a * mas["corpo"][..., None]
    campo = base * (1 - a) + pad * a
    def aplicar(nome, cor):
        nonlocal campo
        if cor and nome in mas:
            k = mas[nome][..., None]
            campo = campo * (1 - k) + C.hex_lab(cor) * k
    if peca == "jersey":
        aplicar("manga", cores.get("manga"))
        aplicar("punho", cores.get("punho"))
        aplicar("gola", cores.get("gola"))
    elif peca == "shorts":
        aplicar("cos", cores.get("cos"))
    elif peca == "socks":
        aplicar("cano", cores.get("cano"))
    return campo


def renderizar_cor(peca, cfg, origem, tamanho=None):
    """Textura de cor recolorida (RGB uint8). origem = caminho da cor do doador (ou do template); tamanho = (w, h) ou
    None (o da origem)."""
    img = Image.open(origem).convert("RGB")
    if tamanho and tuple(tamanho) != img.size:
        img = img.resize(tuple(tamanho), Image.LANCZOS)
    w, h = img.size
    src = np.asarray(img)
    camadas = cfg["camadas"]
    centros = np.array([C.hex_lab(c["origem"]) for c in camadas], np.float32)
    detalhe = float(cfg.get("detalhe", 1.0))
    mas = M.mascaras(peca, w, h)
    if peca == "jersey":
        X, D, F = M.coordenadas_tronco(w, h)
        px = 1.0 / (w * (M.FRENTE["u1"] - M.FRENTE["u0"]))
    else:
        X, D, F = M.coordenadas_planas(w, h)
        px = 1.0 / w
    saida = np.empty((h, w, 3), np.uint8)
    passo = max(32, 1 << 20 // max(1, w))
    fixas = [C.hex_lab(c.get("cor") or c["origem"]) for c in camadas]
    for y0 in range(0, h, passo):
        y1 = min(h, y0 + passo)
        lab = C.rgb_lab(src[y0:y1])
        dist = np.sqrt(((lab[..., None, :] - centros) ** 2).sum(-1))           # (rows, w, K)
        wgt = np.exp(-((dist - dist.min(-1, keepdims=True)) / SIGMA_CAMADA) ** 2)
        wgt /= wgt.sum(-1, keepdims=True)
        sub = {k: v[y0:y1] for k, v in mas.items()}
        campo = None
        out = np.zeros_like(lab)
        for k, cam in enumerate(camadas):
            wk = wgt[..., k:k + 1]
            if float(wk.max()) < 1e-4:
                continue
            delta = (lab - centros[k]) * np.array([detalhe, detalhe * 0.6, detalhe * 0.6], np.float32)
            if cam.get("papel") == "base":
                if campo is None:
                    campo = _campos_regiao(peca, cfg, sub, X[y0:y1], D[y0:y1], F[y0:y1], px)
                alvo = campo
            else:
                alvo = fixas[k]
            out += wk * (alvo + delta)
        out[..., 0] = np.clip(out[..., 0], 0, 100)
        saida[y0:y1] = np.round(C.lab_rgb(out)).astype(np.uint8)
    if peca == "jersey" and (cfg.get("gola") or {}).get("arquivo"):
        saida = aplicar_gola(saida, cfg["gola"])
    return saida


def aplicar_gola(rgb, gola):
    """Cola um template de gola (PNG transparente no molde da camisa; cada cor lisa é uma parte) com as cores escolhidas."""
    if not os.path.isfile(gola["arquivo"]):
        return rgb
    h, w = rgb.shape[:2]
    im = Image.open(gola["arquivo"]).convert("RGBA")
    if im.size != (w, h):
        im = im.resize((w, h), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    alfa = a[..., 3:4] / 255.0
    if float(alfa.max()) <= 0:
        return rgb
    camadas = gola.get("camadas") or []
    if camadas:
        lab = C.rgb_lab(a[..., :3])
        centros = np.array([C.hex_lab(c["origem"]) for c in camadas], np.float32)
        alvos = np.array([C.hex_lab(c.get("cor") or c["origem"]) for c in camadas], np.float32)
        dist = np.sqrt(((lab[..., None, :] - centros) ** 2).sum(-1))
        wgt = np.exp(-((dist - dist.min(-1, keepdims=True)) / SIGMA_CAMADA) ** 2)
        wgt /= wgt.sum(-1, keepdims=True)
        cor = C.lab_rgb(np.einsum("hwk,kc->hwc", wgt, alvos))
    else:
        cor = a[..., :3]
    return np.round(rgb * (1 - alfa) + cor * alfa).astype(np.uint8)


def composto_camisa(projeto, arqs, tamanho=(1024, 1024)):
    """Textura final da camisa com logos e com o escudo e a marca desenhados na caixa do hotspot (como o jogo mostra),
    para o minikit."""
    cfg = projeto["pecas"]["jersey"]
    origem, _ = origem_cor(projeto, "jersey", arqs)
    rgb = renderizar_cor("jersey", cfg, origem, tamanho)
    rgb = colar_logos(rgb, cfg.get("logos") or [], "jersey")
    base = Image.fromarray(rgb).convert("RGBA")
    w, h = base.size
    for chave in ("escudo", "marca"):
        info = projeto.get(chave) or {}
        cx = info.get("caixa")
        if not (info.get("arquivo") and cx and os.path.isfile(info["arquivo"])):
            continue
        q = quadro_logo(info["arquivo"])
        x0, x1 = sorted((cx["x0"] * w, cx["x1"] * w))
        y0, y1 = sorted((cx["y0"] * h, cx["y1"] * h))
        q = q.resize((max(1, round(x1 - x0)), max(1, round(y1 - y0))), Image.LANCZOS)
        if cx["x1"] < cx["x0"]:
            q = q.transpose(Image.FLIP_LEFT_RIGHT)
        if cx["y1"] < cx["y0"]:
            q = q.transpose(Image.FLIP_TOP_BOTTOM)
        _colar(base, q, (x0 + x1) / 2, (y0 + y1) / 2)
    return np.asarray(base.convert("RGB"))


# ------------------------------------------------------------------ logos
def _carregar_logo(caminho):
    im = Image.open(caminho)
    return im.convert("RGBA")


def colar_logos(rgb, logos, peca):
    """Cola os logos (RGBA) na textura. Cada logo: arquivo, u, v (centro), largura, altura (fração da textura), rot (graus),
    visivel. Nas costas da camisa o logo é girado 180° sozinho (as costas estão de cabeça para baixo na textura)."""
    if not logos:
        return rgb
    h, w = rgb.shape[:2]
    base = Image.fromarray(rgb).convert("RGBA")
    for lg in logos:
        if not lg.get("visivel", True) or not lg.get("arquivo") or not os.path.isfile(lg["arquivo"]):
            continue
        im = _carregar_logo(lg["arquivo"])
        lw = max(1, int(round(float(lg["largura"]) * w)))
        lh = max(1, int(round(float(lg["altura"]) * h)))
        im = im.resize((lw, lh), Image.LANCZOS)
        rot = float(lg.get("rot", 0)) + (180.0 if rotacao_auto(peca, lg) else 0.0)
        if rot % 360:
            im = im.rotate(-rot, resample=Image.BICUBIC, expand=True)
        op = float(lg.get("opacidade", 1.0))
        if op < 1:
            a = np.asarray(im).copy()
            a[..., 3] = (a[..., 3] * op).astype(np.uint8)
            im = Image.fromarray(a)
        _colar(base, im, float(lg["u"]) * w, float(lg["v"]) * h)
    return np.asarray(base.convert("RGB"))


def _colar(base, im, cx, cy):
    """alpha_composite centrado em (cx, cy), cortando o que sair da textura."""
    x0, y0 = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
    im = im.crop((max(0, -x0), max(0, -y0), min(im.width, base.width - x0), min(im.height, base.height - y0)))
    if im.width > 0 and im.height > 0:
        base.alpha_composite(im, (max(0, x0), max(0, y0)))


def rotacao_auto(peca, lg):
    """Logo no meio das costas da camisa: gira 180° (a menos que o usuário tenha desligado)."""
    if peca != "jersey" or lg.get("rot_auto") is False:
        return False
    u, v = float(lg["u"]), float(lg["v"])
    return v < 0.5 and M.COSTAS["u0"] - 0.02 <= u <= M.COSTAS["u1"] + 0.02


# ------------------------------------------------------------------ escudo e marca (256×256 RGBA)
def quadro_logo(caminho, lado=256, margem=0.06):
    """Logo centralizado num quadrado transparente (como os crest_*/brand_* do jogo)."""
    im = _carregar_logo(caminho)
    bb = im.getchannel("A").getbbox()
    if bb:
        im = im.crop(bb)
    util = int(lado * (1 - 2 * margem))
    esc = util / max(im.width, im.height)
    im = im.resize((max(1, round(im.width * esc)), max(1, round(im.height * esc))), Image.LANCZOS)
    q = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    q.alpha_composite(im, ((lado - im.width) // 2, (lado - im.height) // 2))
    return q


def normal_de_alfa(rgba, forca=2.5):
    """Mapa normal suave (relevo) a partir do alfa e do brilho do logo, no formato dos crest_*_normal (B = 0, A = 255)."""
    a = np.asarray(rgba, np.float32) / 255.0
    alt = a[..., 3] * (0.6 + 0.4 * a[..., :3].mean(-1))
    from scipy import ndimage as nd
    alt = nd.gaussian_filter(alt, 1.2)
    gx = nd.sobel(alt, axis=1) * forca / 8
    gy = nd.sobel(alt, axis=0) * forca / 8
    n = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    out = np.zeros(alt.shape + (4,), np.uint8)
    out[..., 0] = np.clip(128 + 127 * n[..., 0], 0, 255)
    out[..., 1] = np.clip(128 + 127 * n[..., 1], 0, 255)
    out[..., 3] = 255
    return Image.fromarray(out, "RGBA")


# ------------------------------------------------------------------ mapas de tecido genéricos
def _generico(caminho, destino):
    im = Image.open(caminho)
    a = np.asarray(im)
    if a.ndim == 2:
        shutil.copyfile(caminho, destino)
        return
    plano = a.reshape(-1, a.shape[-1])
    nome = os.path.basename(caminho)
    if "_taa" in nome:
        dentro = plano[:, 0] > 0
        ref = plano[dentro] if dentro.any() else plano
    else:
        ref = plano
    vals, cont = np.unique(ref[:: max(1, len(ref) // 200000)], axis=0, return_counts=True)
    moda = vals[cont.argmax()]
    out = np.empty_like(a)
    out[...] = moda
    if "_taa" in nome:
        out[plano.reshape(a.shape)[..., 0] == 0] = a[plano.reshape(a.shape)[..., 0] == 0]
    Image.fromarray(out, im.mode).save(destino)


# ------------------------------------------------------------------ exportar
def nome_pasta(nome):
    import unicodedata
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "time"


def destino_kit(projeto, saida):
    t = projeto["time"]
    tid = int(t["teamid"])
    n = TIPOS[projeto["tipo"]]
    v = int(projeto.get("variacao") or 0)
    pasta_time = f"{nome_pasta(t.get('pasta') or t.get('nome'))}_{tid}"
    rel = f"kit_{tid // 500 * 500}/{pasta_time}/{projeto['tipo']}_{n}_{v}"
    return os.path.join(saida, *rel.split("/")), rel, f"{tid}_{n}_{v}"


def exportar(projeto, saida, progresso=lambda f, m: None):
    arqs = arquivos_doador(projeto["doador"])
    pasta, rel, suf = destino_kit(projeto, saida)
    velho = arqs["sufixo"]
    feitos = []
    os.makedirs(pasta, exist_ok=True)
    for i, peca in enumerate(PECAS):
        progresso(0.05 + 0.25 * i, f"Desenhando {'a camisa' if peca == 'jersey' else 'o calção' if peca == 'shorts' else 'o meião'}")
        cfg = projeto["pecas"][peca]
        origem, tam = origem_cor(projeto, peca, arqs)
        rgb = renderizar_cor(peca, cfg, origem, tam)
        rgb = colar_logos(rgb, cfg.get("logos") or [], peca)
        os.makedirs(os.path.join(pasta, peca), exist_ok=True)
        dst = os.path.join(pasta, peca, f"{peca}_{suf}_color.png")
        Image.fromarray(rgb, "RGB").save(dst, optimize=False)
        feitos.append(dst)
    progresso(0.8, "Escudo, marca e mapas de tecido")
    trocas = {}
    for chave, prefixos in (("escudo", ("crest_", "crest_shorts_")), ("marca", ("brand_jersey_", "brand_shorts_"))):
        info = projeto.get(chave) or {}
        if info.get("arquivo") and os.path.isfile(info["arquivo"]):
            q = quadro_logo(info["arquivo"])
            nrm = normal_de_alfa(q)
            for pre in prefixos:
                trocas[pre + "color"] = q
                trocas[pre + "normal"] = nrm
    for f in arqs["outros"]:
        nome = os.path.basename(f)
        novo = nome.replace(velho, suf)
        peca = os.path.basename(os.path.dirname(f))
        dst = os.path.join(pasta, peca, novo)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tipo = re.sub(r"_" + re.escape(velho) + r"_", "_", nome).replace(".png", "")    # ex.: crest_color, jersey_taa
        if tipo in trocas:
            trocas[tipo].save(dst)
        elif projeto.get("mapas") == "generico" and re.match(r"(jersey|shorts|socks)_(coeff|taa)$", tipo):
            _generico(f, dst)
        else:
            shutil.copyfile(f, dst)
        feitos.append(dst)
    progresso(0.95, "Hotspot")
    with open(arqs["hotspot"], encoding="utf-8") as fh:
        hs = json.load(fh)
    hs["AssetName"] = f"content/character/kit/{rel}/hotspots_{suf}"
    for h in hs.get("Hotspots", []):
        for chave, nome in (("escudo", "team"), ("marca", "brand")):
            info = projeto.get(chave) or {}
            cx = info.get("caixa") if h.get("Group") == "jersey" else info.get("caixa_calcao") if h.get("Group") == "shorts" else None
            if h.get("Name") == nome and cx:
                h["Bounds"] = {"X": round(cx["x0"], 6), "Y": round(cx["y0"], 6), "Z": round(cx["x1"], 6), "W": round(cx["y1"], 6)}
        cx = (projeto.get("hotspots") or {}).get(f"{h.get('Group')}/{h.get('Name')}")
        if cx:
            h["Bounds"] = {"X": round(cx["x0"], 6), "Y": round(cx["y0"], 6), "Z": round(cx["x1"], 6), "W": round(cx["y1"], 6)}
    dst = os.path.join(pasta, f"hotspots_{suf}.hotspot")
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(hs, fh, indent=2)
    feitos.append(dst)
    minikit_arq = None
    if projeto.get("minikit", True) and M.malha("jersey") is not None:
        progresso(0.97, "Minikit")
        import minikit as MK
        n = TIPOS[projeto["tipo"]]
        minikit_arq = os.path.join(saida, "minikits", f"j{n}_{int(projeto['time']['teamid'])}_{int(projeto.get('variacao') or 0)}.png")
        MK.desenhar(composto_camisa(projeto, arqs), minikit_arq)
        feitos.append(minikit_arq)
    progresso(1.0, "Pronto")
    return {"pasta": pasta, "rel": rel, "arquivos": feitos, "minikit": minikit_arq}
