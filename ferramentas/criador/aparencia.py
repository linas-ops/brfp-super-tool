"""Criador de Ligas e Times — aparência dos jogadores pela foto (OpenCV, quando os componentes do Criador de Minifaces
estão instalados; sem eles a aparência vem só da nacionalidade).

As fotos da API-Football são padronizadas (150×150, fundo branco, cabeça e ombros). Do rosto (detector Haar) saem:
    pele      cor mediana das bochechas e da testa (Lab)            -> skintonecode (10…100)
    cabelo    pixels acima da testa que não são fundo nem pele     -> cor (haircolorcode), volume e comprimento
    barba     queixo e mandíbula mais escuros que a pele            -> com/sem barba (facialhairtypecode)
Os códigos do jogo vêm de referências: jogadores da API casados com os mesmos jogadores do banco (aparencia_ref.json,
refeito com o que estiver no cache em "Recalibrar"): a pele por regressão, o resto pelos vizinhos mais parecidos.
"""
import json
import math
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(AQUI, "aparencia_ref.json")
REF_TM = os.path.join(AQUI, "aparencia_ref_tm.json")     # fotos da Transfermarkt: retrato fechado, fundo qualquer
_CV = {}


def disponivel():
    try:
        _cv()
        return True
    except Exception:  # noqa: BLE001
        return False


def _cv():
    if not _CV:
        import cv2
        import numpy as np
        _CV.update(cv2=cv2, np=np, rosto=cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml"),
                   rosto2=cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"))
    return _CV


def ler_imagem(dados_img):
    c = _cv()
    np, cv2 = c["np"], c["cv2"]
    if not dados_img:
        raise ValueError("imagem vazia")
    arr = np.frombuffer(dados_img, np.uint8)
    im = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise ValueError("imagem ilegível")
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.shape[2] == 4:                                   # transparente: fundo branco, como as fotos da API
        a = im[..., 3:4].astype(np.float32) / 255
        im = (im[..., :3] * a + 255 * (1 - a)).astype(np.uint8)
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def _rosto(rgb):
    c = _cv()
    cv2, np = c["cv2"], c["np"]
    h, w = rgb.shape[:2]
    g = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    achados = []
    for cl in (c["rosto"], c["rosto2"]):
        for viz in (5, 3):
            achados = list(cl.detectMultiScale(g, 1.05, viz, minSize=(int(w * 0.22), int(w * 0.22))))
            if achados:
                break
        if achados:
            break
    if not achados:
        # enquadramento típico das fotos da API (medido nas próprias fotos)
        s = int(w * 0.40)
        return (w - s) // 2, int(h * 0.27), s, False
    x, y, s, _ = max(achados, key=lambda r: r[2] * (1.0 - abs((r[0] + r[2] / 2) / w - 0.5)))
    return int(x), int(y), int(s), True


def medir(rgb, estilo="api"):
    """Medidas da foto: pele (Lab), cabelo (Lab, quantidade, volume, comprimento), barba e o rosto achado.
    estilo "tm" (Transfermarkt): o fundo não é branco — vem da cor das bordas da foto — e o cabelo é lido só numa faixa
    logo acima da testa (o retrato corta o alto da cabeça; volume e comprimento não valem)."""
    c = _cv()
    cv2, np = c["cv2"], c["np"]
    h, w = rgb.shape[:2]
    if max(h, w) != 150:                                   # tudo é medido na escala das fotos da API
        esc = 150.0 / max(h, w)
        rgb = cv2.resize(rgb, (max(1, int(w * esc)), max(1, int(h * esc))), interpolation=cv2.INTER_AREA)
        h, w = rgb.shape[:2]
    x, y, s, achou = _rosto(rgb)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    L, A, B = lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128
    fundo = (rgb.astype(int).min(axis=2) > 232) & (np.abs(rgb.astype(int).max(axis=2) - rgb.astype(int).min(axis=2)) < 18)
    if estilo == "tm":
        bw = max(3, int(min(h, w) * 0.06))
        borda = np.concatenate([lab[:bw, :].reshape(-1, 3), lab[:int(h * 0.5), :bw].reshape(-1, 3), lab[:int(h * 0.5), -bw:].reshape(-1, 3)])
        cor_fundo = np.median(borda, axis=0)
        fundo = np.linalg.norm(lab - cor_fundo, axis=2) < 14

    def reg(x0, y0, x1, y1):
        X0, Y0, X1, Y1 = int(x + x0 * s), int(y + y0 * s), int(x + x1 * s), int(y + y1 * s)
        X0, Y0, X1, Y1 = max(0, X0), max(0, Y0), min(w, X1), min(h, Y1)
        m = np.zeros((h, w), bool)
        if X1 > X0 and Y1 > Y0:
            m[Y0:Y1, X0:X1] = True
        return m
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb).astype(int)
    pele_cor = (ycc[..., 1] > 128) & (ycc[..., 1] < 182) & (ycc[..., 2] > 70) & (ycc[..., 2] < 135)
    rosto = reg(0.15, 0.15, 0.85, 0.75) & ~fundo
    m = rosto & pele_cor
    if m.sum() < 30:
        m = rosto
    if m.any():                                            # sem reflexos nem sombras: só o meio da distribuição do L*
        lo, hi = np.percentile(L[m], [25, 75])
        m = m & (L >= lo) & (L <= hi)
    sL, sA, sB = (float(np.median(v[m])) if m.any() else 0.0 for v in (L, A, B))
    # cabelo: acima da testa e nas laterais, o que não é fundo nem parecido com a pele
    dE = np.sqrt((L - sL) ** 2 + (A - sA) ** 2 + (B - sB) ** 2)
    nao_pele = (dE > 14) | (L < sL - 18)
    topo = reg(0.22, -0.22, 0.78, 0.06) if estilo == "tm" else reg(0.05, -0.55, 0.95, 0.10)
    cab_topo = topo & ~fundo & nao_pele
    lados = (reg(-0.35, 0.25, 0.02, 1.15) | reg(0.98, 0.25, 1.35, 1.15))
    cab_lados = lados & ~fundo & nao_pele & (L < max(55.0, sL - 5))
    area_topo = max(1, int(topo.sum()))
    cab = cab_topo | cab_lados
    if cab.sum() >= 25:
        hL, hA, hB = (float(np.median(v[cab])) for v in (L, A, B))
    else:
        hL, hA, hB = sL, sA, sB
    # altura do volume: primeira linha (de cima) com cabelo sobre a cabeça
    colunas = slice(max(0, int(x + 0.2 * s)), min(w, int(x + 0.8 * s)))
    linhas_cab = np.where((~fundo[:, colunas]).sum(axis=1) > 0.15 * s)[0]
    alto = int(linhas_cab.min()) if len(linhas_cab) else y
    volume = (y - alto) / float(s)
    # barba: queixo/mandíbula e buço comparados com a pele das bochechas
    queixo = reg(0.22, 0.80, 0.78, 1.04) & ~fundo
    buco = reg(0.34, 0.69, 0.66, 0.77) & ~fundo
    escuro = (L < sL - 12) & (np.abs(A) < 22)
    barba = float((escuro & queixo).sum()) / max(1, int(queixo.sum()))
    bigode = float((escuro & buco).sum()) / max(1, int(buco.sum()))
    if estilo == "tm":
        cab_lados = np.zeros_like(cab_lados)
        volume = 0.0
    return {"rosto": [x, y, s], "achou_rosto": achou, "estilo": estilo,
            "pele": [round(sL, 1), round(sA, 1), round(sB, 1)], "ita": round(math.degrees(math.atan2(sL - 50, sB if sB else 0.01)), 1),
            "cabelo": [round(hL, 1), round(hA, 1), round(hB, 1)], "cabelo_topo": round(float(cab_topo.sum()) / area_topo, 3),
            "cabelo_lados": round(float(cab_lados.sum()) / max(1, int(lados.sum())), 3), "volume": round(volume, 3),
            "barba": round(barba, 3), "bigode": round(bigode, 3)}


# ------------------------------------------------------------------ medidas -> códigos do jogo
_REF = {}


def carregar_ref(estilo="api"):
    arq = REF_TM if estilo == "tm" else REF
    try:
        mt = os.path.getmtime(arq)
        if _REF.get(arq, (None,))[0] != mt:
            with open(arq, encoding="utf-8") as f:
                _REF[arq] = (mt, json.load(f))
        return _REF[arq][1]
    except (OSError, ValueError):
        return None if estilo == "api" else carregar_ref("api")


def _vet_cabelo(md):
    return [md["cabelo_topo"] * 3, md["cabelo_lados"] * 4, md["volume"] * 3, md["cabelo"][0] / 25.0]


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def alvo(md, genero=0, ref=None):
    """{campo do jogo: [valor, peso]} para escolher o doador da aparência e corrigir pele/cabelo/barba."""
    estilo = md.get("estilo") or "api"
    ref = ref or carregar_ref(estilo) or {}
    out = {}
    # pele: regressão skintonecode ~ L*, a*, b* da pele, esticada para manter as pontas (pele bem clara/bem escura)
    k = ref.get("pele") or {"w": [99.9, -0.982, -0.39, 0.497], "media": 50.0, "f": 1.6}
    bruto = k["w"][0] + k["w"][1] * md["pele"][0] + k["w"][2] * md["pele"][1] + k["w"][3] * md["pele"][2]
    tom = k["media"] + (bruto - k["media"]) * k["f"]
    out["skintonecode"] = [int(max(10, min(100, round(tom / 10.0) * 10))), 3.0]
    refs = [r for r in ref.get("refs") or [] if int(r.get("genero", 0)) == int(genero)]
    if refs:
        # cor do cabelo: vizinhos na cor do cabelo (Lab) entre as referências do mesmo gênero
        cab = md["cabelo"]
        viz = sorted(refs, key=lambda r: _dist(cab, r["cabelo"]))[:7]
        cont = {}
        for i, r in enumerate(viz):
            cont[r["haircolorcode"]] = cont.get(r["haircolorcode"], 0) + (7 - i)
        out["haircolorcode"] = [int(max(cont, key=cont.get)), 1.5]
        # penteado: o das referências genéricas mais parecidas em volume e comprimento (não nas fotos da Transfermarkt,
        # que cortam o alto da cabeça: lá o penteado fica o do doador)
        if estilo != "tm":
            gen = [r for r in refs if r.get("generico")] or refs
            vc = _vet_cabelo(md)
            perto = min(gen, key=lambda r: _dist(vc, _vet_cabelo(r)))
            out["hairtypecode"] = [int(perto["hairtypecode"]), 1.0]
    if not genero:
        lim = ref.get("barba_limite", 0.28)
        tem = md["barba"] >= lim or md["bigode"] >= lim * 1.3
        out["facialhairtypecode"] = [1 if tem else 0, 2.0]
        if tem and refs:
            com = [r for r in refs if r.get("generico") and int(r.get("facialhairtypecode") or 0)]
            if com:
                perto = min(com, key=lambda r: abs(r["barba"] - md["barba"]) + abs(r["bigode"] - md["bigode"]))
                out["_barba_codigo"] = [int(perto["facialhairtypecode"]), 0.0]
    return out


def resumo(md, al):
    """Texto curto para a prévia."""
    tom = al.get("skintonecode", [None])[0]
    comp = "careca/raspado" if md["cabelo_topo"] < 0.12 else "longo" if md["cabelo_lados"] > 0.25 else \
        "volumoso" if md["volume"] > 0.42 else "médio" if md["cabelo_topo"] > 0.45 else "curto"
    L = md["cabelo"][0]
    cor = "preto" if L < 22 else "castanho-escuro" if L < 34 else "castanho" if L < 48 else "claro/loiro" if md["cabelo"][2] > 12 else "grisalho/claro"
    return {"pele": tom, "cabelo": cor if md["cabelo_topo"] >= 0.12 else "—", "comprimento": comp,
            "barba": bool(al.get("facialhairtypecode", [0])[0])}


def generica(rgb):
    """Foto "NO PHOTO YET" da API (silhueta cinza): sem cor nenhuma."""
    c = _cv()
    hsv = c["cv2"].cvtColor(rgb, c["cv2"].COLOR_RGB2HSV)
    return float(hsv[..., 1].mean()) < 6.0


def analisar(dados_img, genero=0, estilo="api"):
    rgb = ler_imagem(dados_img)
    if generica(rgb):
        return {"erro": "a API não tem foto desta pessoa (imagem genérica)"}
    md = medir(rgb, estilo)
    al = alvo(md, genero)
    if not md["achou_rosto"]:                              # rosto não achado: só a pele (o resto seria chute)
        al = {"skintonecode": [al["skintonecode"][0], 1.5]}
    return {"medidas": md, "alvo": {k: v for k, v in al.items()}, "resumo": resumo(md, al)}


def analisar_url(url, baixar, pasta_cache, genero=0, estilo=None):
    import hashlib
    import urllib.parse
    arq = os.path.join(pasta_cache, hashlib.sha1(url.encode()).hexdigest()[:20] + os.path.splitext(urllib.parse.urlsplit(url).path)[1])
    if os.path.isfile(arq):
        with open(arq, "rb") as f:
            b = f.read()
    else:
        b = baixar(url)
        os.makedirs(pasta_cache, exist_ok=True)
        with open(arq, "wb") as f:
            f.write(b)
    if estilo is None:
        estilo = "tm" if "transfermarkt" in url else "api"
    return analisar(b, genero, estilo)


# ------------------------------------------------------------------ referências (calibração com o cache)
def calibrar(pares):
    """pares: [{medidas, genero, generico, skintonecode, haircolorcode, hairtypecode, facialhairtypecode}] -> referências."""
    import numpy as np
    X = np.array([[1.0, *p["medidas"]["pele"]] for p in pares])
    y = np.array([float(p["skintonecode"]) for p in pares])
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    bruto = X @ w
    f = float(y.std() / (bruto.std() or 1.0))
    media = float(y.mean())
    pred = np.clip(np.round((media + (bruto - media) * f) / 10) * 10, 10, 100)
    erro_pele = float(np.mean(np.abs(pred - y)))
    # limite da barba que mais acerta (homens genéricos)
    hom = [p for p in pares if not p["genero"]]
    melhor, acerto = 0.28, -1
    for lim in [i / 100 for i in range(8, 60, 2)]:
        a = sum(1 for p in hom if (p["medidas"]["barba"] >= lim or p["medidas"]["bigode"] >= lim * 1.3) == bool(int(p["facialhairtypecode"])))
        if a > acerto:
            melhor, acerto = lim, a
    refs = [{"genero": int(p["genero"]), "generico": bool(p["generico"]), "cabelo": p["medidas"]["cabelo"],
             "cabelo_topo": p["medidas"]["cabelo_topo"], "cabelo_lados": p["medidas"]["cabelo_lados"],
             "volume": p["medidas"]["volume"], "barba": p["medidas"]["barba"], "bigode": p["medidas"]["bigode"],
             "haircolorcode": int(p["haircolorcode"]), "hairtypecode": int(p["hairtypecode"]),
             "facialhairtypecode": int(p["facialhairtypecode"])} for p in pares]
    return {"pele": {"w": [float(v) for v in w], "media": media, "f": f}, "erro_pele": round(erro_pele, 1),
            "perto_pele": round(float(np.mean(np.abs(pred - y) <= 20)), 2),
            "barba_limite": melhor, "acerto_barba": round(acerto / max(1, len(hom)), 3), "refs": refs, "amostra": len(pares)}
