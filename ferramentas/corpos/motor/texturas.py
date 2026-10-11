"""Texturas do corpo (bodyupper) entre FC 26 e FC 27.

Os dois jogos usam o mesmo corpo, mas a UV mudou inteira: no FC 26 os braços ficam nas laterais e as costas aparecem
divididas ao lado do peito; no FC 27 os braços são duas colunas à esquerda e costas e peito ficam inteiros à direita.
A conversão passa cada pixel pela superfície 3D: para cada pixel da UV de destino acha o ponto do corpo, o ponto mais
próximo no corpo de origem e a cor da textura de origem naquele ponto. Os corpos de referência (FBX exportados pelo FET)
ficam em motor/referencia; a correspondência pixel a pixel é calculada uma vez por resolução e guardada em cache/mapas.

    python texturas.py ENTRADA [...] [--para fc27|fc26] [--saida PASTA] [--tamanho 2048] [--tipo cor|normal]

Requer numpy, SciPy e Pillow (o Python embutido do Super Tool). DDS é lido pelo Pillow ou, se ele não souber, pelo
texconv que vem com o Super Tool.
"""
import hashlib
import os
import subprocess
import sys
import tempfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(os.path.dirname(os.path.dirname(AQUI)))
sys.path.append(os.path.join(SUPERTOOL, "ferramentas", "faces", "motor"))   # leitor de FBX (fbxio, cena)

JOGOS = ("fc26", "fc27")
OUTRO = {"fc26": "fc27", "fc27": "fc26"}
NOME = {"fc26": "FC 26", "fc27": "FC 27"}
REF = {j: os.path.join(AQUI, "referencia", f"bodyupper_{j}.fbx") for j in JOGOS}
CACHE = os.environ.get("BRFP_CORPOS_CACHE") or os.path.join(os.path.dirname(AQUI), "cache", "mapas")
VERSAO_MAPA = 2
EXT_IMAGEM = (".png", ".dds", ".tga", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LONGE_M = 0.01          # 1 cm: ponto do destino sem equivalente na origem (topo do pescoço do FC 27)


class ErroConversao(Exception):
    pass


# ------------------------------------------------------------------ corpos de referência
_MALHAS = {}


def _chave_ref(jogo):
    st = os.stat(REF[jogo])
    return hashlib.sha1(f"{jogo}|{st.st_size}|{int(st.st_mtime)}|{VERSAO_MAPA}".encode()).hexdigest()[:10]


def malha(jogo):
    """LOD0 do corpo de referência: V (n×3, metros), T (m×3) e UV (n×2, v para cima), com os vértices já separados
    nas costuras de UV."""
    if jogo in _MALHAS:
        return _MALHAS[jogo]
    if not os.path.isfile(REF[jogo]):
        raise ErroConversao(f"Corpo de referência do {NOME[jogo]} não encontrado: {REF[jogo]} (não apague a pasta referencia).")
    arq = os.path.join(CACHE, f"malha_{jogo}_{_chave_ref(jogo)}.npz")
    if os.path.isfile(arq):
        with np.load(arq) as z:
            m = {k: z[k] for k in ("V", "T", "UV")}
    else:
        from cena import Cena
        c = Cena(REF[jogo]).malha("body_mat", 0)
        if c is None or c.uv0 is None:
            raise ErroConversao(f"O corpo de referência do {NOME[jogo]} não tem a malha body_mat LOD0 com UV.")
        m = {"V": c.V.astype(np.float64), "T": c.T.astype(np.int64), "UV": c.uv0.astype(np.float64)}
        os.makedirs(CACHE, exist_ok=True)
        np.savez(arq, **m)
    _MALHAS[jogo] = m
    return m


def rasterizar(UV, T, W, H):
    """Para cada pixel (centro) da imagem W×H: o triângulo da UV que o cobre (-1 = fora das ilhas) e as baricêntricas."""
    tri = np.full((H, W), -1, np.int32)
    bar = np.zeros((H, W, 3), np.float32)
    P = np.empty_like(UV)
    P[:, 0] = UV[:, 0] * W - 0.5
    P[:, 1] = (1 - UV[:, 1]) * H - 0.5
    eps = 1e-4
    for t, (a, b, c) in enumerate(T):
        A, B, C = P[a], P[b], P[c]
        x0 = max(int(np.floor(min(A[0], B[0], C[0]))), 0)
        x1 = min(int(np.ceil(max(A[0], B[0], C[0]))), W - 1)
        y0 = max(int(np.floor(min(A[1], B[1], C[1]))), 0)
        y1 = min(int(np.ceil(max(A[1], B[1], C[1]))), H - 1)
        if x1 < x0 or y1 < y0:
            continue
        d = (B[1] - C[1]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[1] - C[1])
        if abs(d) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        l0 = ((B[1] - C[1]) * (xs - C[0]) + (C[0] - B[0]) * (ys - C[1])) / d
        l1 = ((C[1] - A[1]) * (xs - C[0]) + (A[0] - C[0]) * (ys - C[1])) / d
        l2 = 1 - l0 - l1
        dentro = (l0 >= -eps) & (l1 >= -eps) & (l2 >= -eps)
        if not dentro.any():
            continue
        tri[ys[dentro], xs[dentro]] = t
        bar[ys[dentro], xs[dentro]] = np.stack([l0[dentro], l1[dentro], l2[dentro]], -1)
    return tri, bar


def _ponto_mais_proximo(P, A, B, C):
    """Ponto mais próximo de P em cada triângulo ABC (vetorizado): baricêntricas e distância²."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    bp, cp = P - B, P - C
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-30, 1e-30, den)
    v, w = vb / den, vc / den
    bc = np.stack([1 - v - w, v, w], -1)
    fora = (bc < 0).any(-1)
    if fora.any():   # projeção fora do triângulo: o mais próximo está numa aresta
        Pf = P[fora]
        melhor_d = np.full(len(Pf), np.inf)
        melhor_b = np.zeros((len(Pf), 3))
        for X, Y, i, j in ((A, B, 0, 1), (A, C, 0, 2), (B, C, 1, 2)):
            X, Y = X[fora], Y[fora]
            e = Y - X
            t = np.clip(((Pf - X) * e).sum(-1) / np.maximum((e * e).sum(-1), 1e-30), 0, 1)
            d = ((Pf - X - e * t[:, None]) ** 2).sum(-1)
            m = d < melhor_d
            melhor_d[m] = d[m]
            melhor_b[m] = 0
            melhor_b[m, i] = 1 - t[m]
            melhor_b[m, j] = t[m]
        bc[fora] = melhor_b
    Q = A * bc[:, :1] + B * bc[:, 1:2] + C * bc[:, 2:]
    return bc, ((P - Q) ** 2).sum(-1)


def mapa(origem, destino, W, H, progresso=None):
    """Correspondência dos pixels da UV de destino (W×H) para a UV de origem.

    Devolve tri (H×W, triângulo do destino ou -1), stri (triângulo da origem), uv (H×W×2, UV na origem), sem_par (H×W,
    pixels sem ponto da origem a menos de 1 cm) e longe (a fração deles). Guardado em cache/mapas."""
    arq = os.path.join(CACHE, f"mapa_{origem}_{destino}_{W}x{H}_{_chave_ref(origem)}{_chave_ref(destino)}.npz")
    if os.path.isfile(arq):
        with np.load(arq) as z:
            return {k: z[k] for k in ("tri", "stri", "uv", "sem_par", "longe")}
    if progresso:
        progresso(f"calculando a correspondência {NOME[origem]} → {NOME[destino]} em {W}×{H} (só na primeira vez)")
    from scipy.spatial import cKDTree
    o, d = malha(origem), malha(destino)
    tri, bar = rasterizar(d["UV"], d["T"], W, H)
    ys, xs = np.nonzero(tri >= 0)
    stri = np.full((H, W), -1, np.int32)
    uv = np.zeros((H, W, 2), np.float32)
    sem_par = np.zeros((H, W), bool)
    arvore = cKDTree(o["V"][o["T"]].mean(1))
    k = 10
    passo = 200_000
    for ini in range(0, len(ys), passo):
        yy, xx = ys[ini:ini + passo], xs[ini:ini + passo]
        tt = tri[yy, xx]
        P = (d["V"][d["T"][tt]] * bar[yy, xx][..., None]).sum(1)
        _, cand = arvore.query(P, k=k)
        melhor_d = np.full(len(P), np.inf)
        melhor_t = np.zeros(len(P), np.int64)
        melhor_b = np.zeros((len(P), 3))
        for j in range(k):
            c = cand[:, j]
            bc, dist = _ponto_mais_proximo(P, o["V"][o["T"][c, 0]], o["V"][o["T"][c, 1]], o["V"][o["T"][c, 2]])
            m = dist < melhor_d
            melhor_d[m], melhor_t[m], melhor_b[m] = dist[m], c[m], bc[m]
        stri[yy, xx] = melhor_t
        uv[yy, xx] = (o["UV"][o["T"][melhor_t]] * melhor_b[..., None]).sum(1)
        sem_par[yy, xx] = melhor_d > LONGE_M ** 2
    r = {"tri": tri, "stri": stri, "uv": uv, "sem_par": sem_par, "longe": np.float64(sem_par.sum() / max(1, len(ys)))}
    os.makedirs(CACHE, exist_ok=True)
    tmp = f"{arq}.{os.getpid()}.tmp.npz"     # outro processo pode estar calculando o mesmo mapa
    np.savez(tmp, **r)
    os.replace(tmp, arq)
    return r


def mascara(jogo, W, H):
    """Pixels cobertos pela UV do jogo (as ilhas) numa imagem W×H."""
    arq = os.path.join(CACHE, f"mascara_{jogo}_{W}x{H}_{_chave_ref(jogo)}.npz")
    if os.path.isfile(arq):
        with np.load(arq) as z:
            return z["m"]
    m = malha(jogo)
    tri, _ = rasterizar(m["UV"], m["T"], W, H)
    r = tri >= 0
    os.makedirs(CACHE, exist_ok=True)
    np.savez(arq, m=r)
    return r


# ------------------------------------------------------------------ imagens
def texconv():
    return os.path.join(SUPERTOOL, "ferramentas", "estadios", "ferramentas", "texconv.exe")


def ler_imagem(caminho):
    """Imagem como float32 H×W×C (C = 3 ou 4, 0–255). DDS pelo Pillow ou pelo texconv."""
    from PIL import Image
    try:
        im = Image.open(caminho)
        im.load()
    except Exception as ex:  # noqa: BLE001
        if not caminho.lower().endswith(".dds") or not os.path.isfile(texconv()):
            raise ErroConversao(f"Não foi possível ler a imagem: {ex}") from None
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([texconv(), "-nologo", "-y", "-ft", "png", "-f", "R8G8B8A8_UNORM", "-o", tmp, caminho],
                               capture_output=True, text=True, creationflags=SEM_JANELA)
            png = os.path.join(tmp, os.path.splitext(os.path.basename(caminho))[0] + ".png")
            if r.returncode != 0 or not os.path.isfile(png):
                raise ErroConversao("Não foi possível ler o DDS (nem pelo texconv): " + (r.stdout or r.stderr).strip()[-300:]) from None
            im = Image.open(png)
            im.load()
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        a = np.asarray(im, np.float32) / 257.0
        return np.repeat(a[..., None], 3, -1)
    temalfa = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    a = np.asarray(im.convert("RGBA" if temalfa else "RGB"), np.float32)
    if temalfa and a[..., 3].min() >= 255:   # alfa todo opaco: grava sem alfa
        a = a[..., :3]
    return a


def gravar_imagem(a, caminho):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    im = Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), "RGBA" if a.shape[2] == 4 else "RGB")
    tmp = caminho + ".tmp.png"
    im.save(tmp, optimize=False, compress_level=6)
    os.replace(tmp, caminho)


def amostrar(img, uv):
    """Bilinear em img (H×W×C) nas coordenadas UV (n×2, v para cima)."""
    h, w = img.shape[:2]
    sx = uv[:, 0] * w - 0.5
    sy = (1 - uv[:, 1]) * h - 0.5
    x0, y0 = np.floor(sx).astype(np.int64), np.floor(sy).astype(np.int64)
    fx, fy = (sx - x0)[:, None], (sy - y0)[:, None]
    x0c, x1c = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    return (img[y0c, x0c] * (1 - fx) * (1 - fy) + img[y0c, x1c] * fx * (1 - fy)
            + img[y1c, x0c] * (1 - fx) * fy + img[y1c, x1c] * fx * fy)


def preencher_fora(img, cobertos):
    """Fora das ilhas da UV, repete o pixel coberto mais próximo (evita costura escura com mipmaps e filtragem)."""
    from scipy import ndimage
    if cobertos.all() or not cobertos.any():
        return img
    idx = ndimage.distance_transform_edt(~cobertos, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def preencher_suave(img, validos, cobertos):
    """Pixels cobertos mas sem equivalente na origem (topo do pescoço do FC 27): média borrada da pele em volta, em vez
    de repetir a borda (que deixaria listras)."""
    from scipy import ndimage
    falta = cobertos & ~validos
    if not falta.any():
        return img
    out = img.copy()
    s = max(2.0, img.shape[0] / 256)
    peso = validos.astype(np.float32)
    while falta.any() and s < img.shape[0]:
        p = ndimage.gaussian_filter(peso, s)
        ok = falta & (p > 1e-3)
        for c in range(img.shape[2]):
            v = ndimage.gaussian_filter(img[..., c] * peso, s)
            out[..., c][ok] = v[ok] / p[ok]
        falta &= ~ok
        s *= 2
    return out


def redimensionar(img, W, H):
    from PIL import Image
    if img.shape[1] == W and img.shape[0] == H:
        return img
    canais = [Image.fromarray(img[..., c].astype(np.float32), "F").resize((W, H), Image.LANCZOS) for c in range(img.shape[2])]
    return np.stack([np.asarray(c, np.float32) for c in canais], -1)


# ------------------------------------------------------------------ identificação do jogo pela textura
_COSTURAS = {}


def costuras(jogo):
    """Pares de vértices na mesma posição 3D com UV diferente (as costuras) e a direção para dentro de cada ilha."""
    if jogo in _COSTURAS:
        return _COSTURAS[jogo]
    from scipy.spatial import cKDTree
    m = malha(jogo)
    V, T, UV = m["V"], m["T"], m["UV"]
    centro = np.zeros_like(UV)
    n = np.zeros(len(UV))
    ct = UV[T].mean(1)
    for j in range(3):
        np.add.at(centro, T[:, j], ct)
        np.add.at(n, T[:, j], 1)
    centro /= np.maximum(n, 1)[:, None]
    pares = np.array(sorted(cKDTree(V).query_pairs(1e-5)), np.int64).reshape(-1, 2)
    pares = pares[np.linalg.norm(UV[pares[:, 0]] - UV[pares[:, 1]], axis=1) > 0.01]
    dentro = centro - UV
    dentro /= np.maximum(np.linalg.norm(dentro, axis=1), 1e-9)[:, None]
    _COSTURAS[jogo] = (UV, dentro, pares)
    return _COSTURAS[jogo]


def detectar(img):
    """Em qual layout a textura está: nos dois lados de uma costura a cor tem que ser a mesma. Devolve
    (jogo, confiança 'alta'|'baixa', notas {jogo: diferença média nas costuras})."""
    notas = {}
    h, w = img.shape[:2]
    rgb = img[..., :3]
    for j in JOGOS:
        UV, dentro, pares = costuras(j)
        off = 3.0 / max(w, h) * max(1.0, max(w, h) / 1024)
        lados = [amostrar(rgb, UV[pares[:, k]] + dentro[pares[:, k]] * off) for k in (0, 1)]
        notas[j] = float(np.abs(lados[0] - lados[1]).mean())
    a, b = sorted(JOGOS, key=lambda j: notas[j])
    confianca = "alta" if notas[b] > 1.35 * notas[a] + 0.5 else "baixa"
    return a, confianca, {k: round(v, 2) for k, v in notas.items()}


def parece_normal(caminho, img):
    nome = os.path.splitext(os.path.basename(caminho))[0].lower()
    if "normal" in nome or nome.endswith(("_n", "_nm", "_nrm", "_norm")):
        return True
    med = img[..., :3].reshape(-1, 3).mean(0)
    return bool(abs(med[0] - 128) < 18 and abs(med[1] - 128) < 18 and med[2] > 190)


# ------------------------------------------------------------------ mapas normais (espaço tangente)
def bases_tangentes(jogo):
    """Tangente (direção +u), bitangente (+v) e normal de cada triângulo."""
    m = malha(jogo)
    V, T, UV = m["V"], m["T"], m["UV"]
    e1, e2 = V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]
    d1, d2 = UV[T[:, 1]] - UV[T[:, 0]], UV[T[:, 2]] - UV[T[:, 0]]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(det) < 1e-12, 0, 1 / np.where(np.abs(det) < 1e-12, 1, det))[:, None]
    tg = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r
    bt = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r
    n = np.cross(e1, e2)
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    tg -= n * (tg * n).sum(1, keepdims=True)
    tg /= np.maximum(np.linalg.norm(tg, axis=1), 1e-12)[:, None]
    b2 = np.cross(n, tg)
    b2 *= np.where((b2 * bt).sum(1) < 0, -1.0, 1.0)[:, None]
    return tg, b2, n


def girar_normais(cor, stri, dtri, origem, destino, verde_para_baixo=True):
    """Reescreve as normais (RGB 0–255 do espaço tangente da origem) no espaço tangente do destino."""
    to, bo, _ = bases_tangentes(origem)
    td, bd, nd = bases_tangentes(destino)
    x = cor[:, 0] / 127.5 - 1
    y = cor[:, 1] / 127.5 - 1
    azul_const = float(np.std(cor[:, 2])) < 2.0      # BC5/ATI2: só R e G, o azul é reconstruído no jogo
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1)) if azul_const else cor[:, 2] / 127.5 - 1
    s = -1.0 if verde_para_baixo else 1.0           # DirectX: verde aponta para baixo na imagem (−v)
    # só a parte tangente gira: os eixos u e v da origem, deitados no plano do triângulo de destino, escritos nos eixos
    # do destino (rotação, ou rotação com espelho). z fica como está, então uma normal lisa continua lisa.
    T, B, N = td[dtri], bd[dtri], nd[dtri]

    def no_plano(e):
        e = e - N * (e * N).sum(1, keepdims=True)
        e /= np.maximum(np.linalg.norm(e, axis=1), 1e-12)[:, None]
        return (e * T).sum(1), (e * B).sum(1)
    ux, uy = no_plano(to[stri])
    vx, vy = no_plano(bo[stri])
    y = s * y
    x2 = x * ux + y * vx
    y2 = s * (x * uy + y * vy)
    z2 = z
    n = np.maximum(np.sqrt(x2 * x2 + y2 * y2 + z2 * z2), 1e-9)
    out = cor.copy()
    out[:, 0] = (x2 / n + 1) * 127.5
    out[:, 1] = (y2 / n + 1) * 127.5
    out[:, 2] = cor[:, 2] if azul_const else (np.clip(z2 / n, 0, 1) + 1) * 127.5
    return out


# ------------------------------------------------------------------ conversão
def info(caminho):
    """Leitura rápida para a lista: tamanho, canais, jogo identificado e tipo."""
    img = ler_imagem(caminho)
    jogo, confianca, notas = detectar(img)
    return {"largura": int(img.shape[1]), "altura": int(img.shape[0]), "canais": int(img.shape[2]), "jogo": jogo,
            "confianca": confianca, "notas": notas, "tipo": "normal" if parece_normal(caminho, img) else "cor"}


def nome_saida(caminho):
    base, ext = os.path.splitext(os.path.basename(caminho))
    return base + ".png"


def converter(entrada, saida, destino=None, origem=None, tipo="auto", tamanho=0, progresso=None):
    """Converte a textura `entrada` para o layout do jogo `destino` e grava PNG em `saida`."""
    img = ler_imagem(entrada)
    avisos = []
    if origem not in JOGOS:
        origem, confianca, _ = detectar(img)
        if confianca == "baixa":
            avisos.append(f"Layout identificado como {NOME[origem]} com pouca certeza: confira o resultado "
                          "(ou escolha o jogo de origem à mão).")
    destino = destino if destino in JOGOS else OUTRO[origem]
    if destino == origem:
        raise ErroConversao(f"A textura já está no layout do {NOME[destino]}.")
    if tipo not in ("cor", "normal"):
        tipo = "normal" if parece_normal(entrada, img) else "cor"
    h, w = img.shape[:2]
    W = H = int(tamanho) if tamanho else 0
    if not W:
        W, H = w, h
    if W > 8192 or H > 8192 or W < 64 or H < 64:
        raise ErroConversao(f"Tamanho de saída inválido: {W}×{H}.")
    # fundo fora das ilhas da origem: repete a borda, para a filtragem não puxar cor de fora do corpo
    fonte = preencher_fora(img, mascara(origem, w, h))
    mp = mapa(origem, destino, W, H, progresso)
    ys, xs = np.nonzero(mp["tri"] >= 0)
    cor = amostrar(fonte, mp["uv"][ys, xs].astype(np.float64))
    if tipo == "normal":
        cor[:, :3] = girar_normais(cor[:, :3], mp["stri"][ys, xs], mp["tri"][ys, xs], origem, destino)
    out = np.zeros((H, W, img.shape[2]), np.float32)
    out[ys, xs] = cor
    cobertos = mp["tri"] >= 0
    if tipo == "normal":
        out[mp["sem_par"]] = [127.5, 127.5, 255.0, 255.0][:img.shape[2]]   # sem relevo onde a origem não tem pele
    else:
        out = preencher_suave(out, cobertos & ~mp["sem_par"], cobertos)
    out = preencher_fora(out, cobertos)
    gravar_imagem(out, saida)
    longe = float(mp["longe"])
    notas = []
    if longe > 0.005:
        notas.append(f"{100 * longe:.1f}% da área do {NOME[destino]} não existe no corpo do {NOME[origem]} "
                     f"({'topo do pescoço, que fica embaixo da cabeça' if destino == 'fc27' else 'bordas'}): "
                     "preenchido com a cor da pele em volta.")
    return {"saida": saida, "origem": origem, "destino": destino, "tipo": tipo, "entrada_px": [w, h], "saida_px": [W, H],
            "avisos": avisos, "notas": notas, "longe": round(100 * longe, 2)}


def previa(entrada, saida_png, lado=1024):
    """Cópia reduzida (PNG RGB, até `lado` px) para a interface."""
    from PIL import Image
    img = ler_imagem(entrada)
    im = Image.fromarray(np.clip(np.rint(img[..., :3]), 0, 255).astype(np.uint8), "RGB")
    if max(im.size) > lado:
        im.thumbnail((lado, lado), Image.LANCZOS)
    os.makedirs(os.path.dirname(saida_png), exist_ok=True)
    im.save(saida_png)
    return saida_png


def malha_previa(jogo):
    m = malha(jogo)
    return {"V": [round(float(x), 5) for x in m["V"].ravel()], "UV": [round(float(x), 5) for x in m["UV"].ravel()],
            "T": [int(x) for x in m["T"].ravel()]}


def main():
    import argparse
    import time
    ap = argparse.ArgumentParser(description="Texturas do corpo (bodyupper) FC 26 <-> FC 27")
    ap.add_argument("entradas", nargs="+")
    ap.add_argument("--para", choices=JOGOS)
    ap.add_argument("--de", choices=JOGOS)
    ap.add_argument("--saida")
    ap.add_argument("--tamanho", type=int, default=0)
    ap.add_argument("--tipo", choices=("auto", "cor", "normal"), default="auto")
    a = ap.parse_args()
    for ent in a.entradas:
        t = time.time()
        inf = info(ent)
        dest = a.para or OUTRO[a.de or inf["jogo"]]
        pasta = a.saida or os.path.join(os.path.dirname(os.path.abspath(ent)), "Convertidos_" + dest.upper())
        r = converter(ent, os.path.join(pasta, nome_saida(ent)), destino=dest, origem=a.de, tipo=a.tipo,
                      tamanho=a.tamanho, progresso=print)
        print(f"{ent}: {NOME[r['origem']]} -> {NOME[r['destino']]} ({inf['confianca']}, {inf['notas']}) "
              f"{r['tipo']} {r['saida_px']} em {time.time() - t:.1f} s -> {r['saida']}")
        for av in r["avisos"]:
            print("  AVISO:", av)
        for nt in r["notas"]:
            print("  NOTA:", nt)


if __name__ == "__main__":
    main()
