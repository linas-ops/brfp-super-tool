"""Molde de UV dos uniformes do FC 27 (o mesmo em todos os times): partes da camisa, do calção e do meião.

As costuras foram traçadas pela média das bordas das texturas de cor dos 132 kits de exemplo (mesmo molde em todos).
Coordenadas em fração da textura (u para a direita, v para baixo). Na camisa:
  - frente: em pé, embaixo no centro (gola em v ≈ 0,5, barra em v ≈ 0,945);
  - costas: de cabeça para baixo, em cima no centro (barra em v ≈ 0,045);
  - mangas curtas: quadrados nos cantos de cima (punho perto de u ≈ 0,21 / 0,79);
  - mangas longas: faixas laterais (punho na borda u ≈ 0 / 1);
  - gola: o anel em volta de (0,5; 0,507); braçadeira: faixa de baixo.
Na frente e nas costas, u > 0,5 é o lado esquerdo de quem veste (as costas estão giradas 180°).
"""
import hashlib
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

AQUI = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.join(AQUI, "referencia")
CACHE_MALHAS = os.path.join(os.path.dirname(AQUI), "cache", "malhas")
# malhas LOD0 exportadas pelo FET (opcionais): com elas as partes vêm das ilhas da UV e o padrão segue o corpo em 3D
MALHAS = {"jersey": "jersey_0_0_0_0_1_0_0_mesh.fbx", "shorts": "shorts_0_6_0_mesh.fbx", "socks": "sock_0_0_1_0_0_mesh.fbx"}
LARGURA_TRONCO = 0.36       # metros, de um lado a outro do tronco da camisa de referência (x = -0,5 … 0,5)

TAMANHOS = {"jersey": (2048, 2048), "shorts": (1024, 512), "socks": (512, 256)}

# ------------------------------------------------------------------ camisa
FRENTE = {"u0": 0.315, "u1": 0.685, "v0": 0.500, "v1": 0.945}     # caixa da frente (ombro -> barra)
COSTAS = {"u0": 0.360, "u1": 0.640, "v0": 0.045, "v1": 0.500}     # caixa das costas (barra -> ombro)
GOLA = {"cu": 0.5, "cv": 0.507, "ru": 0.060, "rv": 0.042, "ru_in": 0.040, "rv_in": 0.027}
# densidade horizontal / vertical da UV na frente (o escudo do jogo é desenhado esticado nessa proporção)
ESTICAR_CAMISA = 1.2

_MANGA_CURTA = [(0.160, 0.0), (0.332, 0.0), (0.347, 0.05), (0.350, 0.20), (0.343, 0.275), (0.312, 0.328), (0.290, 0.346),
                (0.160, 0.346)]
_MANGA_LONGA = [(0.0, 0.342), (0.335, 0.342), (0.356, 0.39), (0.364, 0.46), (0.357, 0.54), (0.338, 0.60), (0.305, 0.640),
                (0.285, 0.665), (0.0, 0.665)]
_PUNHO_CURTO = [(0.160, 0.0), (0.252, 0.0), (0.252, 0.346), (0.160, 0.346)]
_PUNHO_LONGO = [(0.0, 0.342), (0.034, 0.342), (0.034, 0.665), (0.0, 0.665)]
_BRACADEIRA = [(0.362, 0.950), (0.638, 0.950), (0.638, 1.0), (0.362, 1.0)]


def _espelho(poli):
    return [(1.0 - u, v) for u, v in poli]


REGIOES_CAMISA = {
    "manga_curta_d": _MANGA_CURTA, "manga_curta_e": _espelho(_MANGA_CURTA),      # d = direita de quem veste (u < 0,5)
    "manga_longa_d": _MANGA_LONGA, "manga_longa_e": _espelho(_MANGA_LONGA),
    "punho_curto_d": _PUNHO_CURTO, "punho_curto_e": _espelho(_PUNHO_CURTO),
    "punho_longo_d": _PUNHO_LONGO, "punho_longo_e": _espelho(_PUNHO_LONGO),
    "bracadeira": _BRACADEIRA,
}

# ------------------------------------------------------------------ calção
CALCAO = {"cos_v0": 0.385, "cos_v1": 0.472, "u0": 0.11, "u1": 0.89, "barra_v": 0.95}
REGIOES_CALCAO = {"cos": [(0.105, 0.385), (0.895, 0.385), (0.895, 0.472), (0.105, 0.472)],
                  "barra": [(0.0, 0.952), (1.0, 0.952), (1.0, 1.0), (0.0, 1.0)]}
REGIOES_MEIAO = {}


def _poligono(poli, w, h):
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).polygon([(u * w, v * h) for u, v in poli], fill=255)
    return im


def _elipse(cu, cv, ru, rv, w, h):
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).ellipse([(cu - ru) * w, (cv - rv) * h, (cu + ru) * w, (cv + rv) * h], fill=255)
    return im


# ------------------------------------------------------------------ malhas do jogo (opcionais)
_MEM = {}


def caminho_malha(peca):
    c = os.path.join(REF_DIR, MALHAS.get(peca, ""))
    return c if peca in MALHAS and os.path.isfile(c) else None


def malha(peca):
    """V (n×3, metros), T (m×3), UV (n×2, v para cima) e a ilha da UV de cada triângulo; None sem o FBX."""
    c = caminho_malha(peca)
    if not c:
        return None
    st = os.stat(c)
    chave = hashlib.sha1(f"{c}|{st.st_size}|{int(st.st_mtime)}|1".encode()).hexdigest()[:12]
    if chave in _MEM:
        return _MEM[chave]
    arq = os.path.join(CACHE_MALHAS, f"{peca}_{chave}.npz")
    if os.path.isfile(arq):
        with np.load(arq) as z:
            m = {k: z[k] for k in z.files}
    else:
        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(AQUI))), "ferramentas", "faces", "motor"))
        from cena import Cena
        cena = Cena(c)
        lod = min(x.lod for x in cena.malhas)
        partes = [x for x in cena.malhas if x.lod == lod and x.uv0 is not None]
        Vs, UVs, Ts, n = [], [], [], 0
        for x in partes:
            Vs.append(np.asarray(x.V, np.float64))
            UVs.append(np.asarray(x.uv0, np.float64))
            Ts.append(np.asarray(x.T, np.int64) + n)
            n += len(x.V)
        V, UV, T = np.concatenate(Vs), np.concatenate(UVs), np.concatenate(Ts)
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        chave_uv = np.round(UV * 4096).astype(np.int64)
        _, inv = np.unique(chave_uv[:, 0] * 10 ** 6 + chave_uv[:, 1], return_inverse=True)
        TT = inv.reshape(-1)[T]
        r = np.concatenate([TT[:, 0], TT[:, 1], TT[:, 2]])
        q = np.concatenate([TT[:, 1], TT[:, 2], TT[:, 0]])
        nn = int(inv.max()) + 1
        _, lab = connected_components(coo_matrix((np.ones(len(r)), (r, q)), shape=(nn, nn)), directed=False)
        m = {"V": V, "T": T, "UV": UV, "ilha": lab[TT[:, 0]]}
        os.makedirs(CACHE_MALHAS, exist_ok=True)
        np.savez(arq, **m)
    _MEM[chave] = m
    return m


def rasterizar(peca, w, h):
    """Mapa da textura pela malha: ilha de cada pixel (int16, -1 fora), posição 3D (float32) e a ilha mais perto; fora
    das ilhas vale o pixel de ilha mais perto (a sangria das bordas segue o padrão). None sem a malha."""
    m = malha(peca)
    if m is None:
        return None
    chave = (peca, w, h, id(m))
    if chave in _MEM:
        return _MEM[chave]
    arq = os.path.join(CACHE_MALHAS, f"raster_{peca}_{w}x{h}_{len(m['T'])}_{int(m['V'].sum() * 1000) & 0xffffff}.npz")
    if os.path.isfile(arq):
        with np.load(arq) as z:
            r = (z["ilha"], z["pos"], z["perto"])
        _MEM[chave] = r
        return r
    V, T, UV, ilha = m["V"], m["T"], m["UV"], m["ilha"]
    px = np.stack([UV[:, 0] * w - 0.5, (1.0 - UV[:, 1]) * h - 0.5], 1)
    mapa_i = np.full((h, w), -1, np.int16)
    pos = np.zeros((h, w, 3), np.float32)
    for t, il in zip(T, ilha):
        a, b, c = px[t[0]], px[t[1]], px[t[2]]
        x0, x1 = int(max(0, np.floor(min(a[0], b[0], c[0])))), int(min(w - 1, np.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, np.floor(min(a[1], b[1], c[1])))), int(min(h - 1, np.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1, dtype=np.float64), np.arange(y0, y1 + 1, dtype=np.float64))
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
        l3 = 1 - l1 - l2
        dentro = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not dentro.any():
            continue
        yy, xx = gy[dentro].astype(int), gx[dentro].astype(int)
        mapa_i[yy, xx] = il
        pos[yy, xx] = (l1[dentro, None] * V[t[0]] + l2[dentro, None] * V[t[1]] + l3[dentro, None] * V[t[2]]).astype(np.float32)
    from scipy import ndimage as nd
    _, (iy, ix) = nd.distance_transform_edt(mapa_i < 0, return_indices=True)
    r = (mapa_i, pos[iy, ix], mapa_i[iy, ix])
    os.makedirs(CACHE_MALHAS, exist_ok=True)
    np.savez(arq, ilha=r[0], pos=r[1], perto=r[2])
    _MEM[chave] = r
    return r


def densidades_tronco():
    """Metros de tecido por unidade de UV na frente e nas costas da camisa (pela malha)."""
    m = malha("jersey")
    V, T, UV = m["V"], m["T"], m["UV"]
    tronco = ~np.isin(m["ilha"], _ilhas_por_papel("jersey", m)["manga"])
    uv3 = np.concatenate([UV, np.zeros((len(UV), 1))], 1)

    def area(P):
        return 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    a3, a2 = area(V[T]), area(uv3[T])
    y = 1 - UV[T][:, :, 1].mean(1)
    out = {}
    for nome, s in (("frente", tronco & (y > 0.52)), ("costas", tronco & (y < 0.48))):
        out[nome] = float(np.sqrt(a3[s].sum() / max(a2[s].sum(), 1e-9))) if s.any() else 1.0
    return out


def _ilhas_por_papel(peca, m):
    """Ilhas da malha por papel: camisa -> mangas; meião -> canos (a faixa de cima)."""
    V, T, ilha = m["V"], m["T"], m["ilha"]
    info = {}
    for i in np.unique(ilha):
        vs = V[T[ilha == i].ravel()]
        info[int(i)] = {"x": float(vs[:, 0].mean()), "y": float(vs[:, 1].mean())}
    if peca == "jersey":
        return {"manga": [i for i, d in info.items() if abs(d["x"]) > 0.15]}
    if peca == "socks":
        ymed = float(np.mean([d["y"] for d in info.values()]))
        return {"cano": [i for i, d in info.items() if d["y"] > ymed + 0.05]}
    return {}


def _mascaras_malha(peca, w, h):
    """Partes exatas pela malha; {} sem a malha."""
    r = rasterizar(peca, w, h)
    if r is None:
        return {}
    m = malha(peca)
    _, pos, perto = r
    papeis = _ilhas_por_papel(peca, m)
    raio = max(0.6, w / 1400)

    def suave(b):
        return np.asarray(Image.fromarray((b * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(raio)), np.float32) / 255.0
    res = {}
    if peca == "jersey" and papeis.get("manga"):
        manga_b = np.isin(perto, papeis["manga"])
        res["manga"] = suave(manga_b)
        # punho: os últimos 2,5 cm da manga (o |x| mais longe do corpo)
        vs = m["V"][m["T"][np.isin(m["ilha"], papeis["manga"])].ravel()]
        lim = float(np.abs(vs[:, 0]).max()) - 0.025
        res["punho"] = suave(manga_b & (np.abs(pos[..., 0]) > lim))
    if peca == "socks" and papeis.get("cano"):
        res["cano"] = suave(np.isin(perto, papeis["cano"]))
    return res


def mascaras(peca, w, h):
    """{nome: máscara float32 0..1} das partes da peça nesse tamanho (bordas suavizadas em ~1 px)."""
    raio = max(0.6, w / 1400)
    out = {}
    if peca == "jersey":
        for nome, poli in REGIOES_CAMISA.items():
            out[nome] = _poligono(poli, w, h)
        anel = Image.fromarray(np.minimum(np.asarray(_elipse(GOLA["cu"], GOLA["cv"], GOLA["ru"], GOLA["rv"], w, h)),
                                          255 - np.asarray(_elipse(GOLA["cu"], GOLA["cv"], GOLA["ru_in"], GOLA["rv_in"], w, h))))
        out["gola"] = anel
    elif peca == "shorts":
        for nome, poli in REGIOES_CALCAO.items():
            out[nome] = _poligono(poli, w, h)
    res = {k: np.asarray(v.filter(ImageFilter.GaussianBlur(raio)), dtype=np.float32) / 255.0 for k, v in out.items()}
    pela_malha = _mascaras_malha(peca, w, h)
    if peca == "jersey":
        longa = np.maximum(res["manga_longa_d"], res["manga_longa_e"])
        punho_longo = np.minimum(np.maximum(res["punho_longo_d"], res["punho_longo_e"]), longa)
        if "manga" in pela_malha:
            # mangas curtas exatas pela malha; as faixas laterais (mangas longas, outra malha) continuam pelo traçado
            manga = np.maximum(pela_malha["manga"], longa)
            punho = np.maximum(pela_malha["punho"], punho_longo)
        else:
            curta = np.maximum(res["manga_curta_d"], res["manga_curta_e"])
            manga = np.maximum(curta, longa)
            punho = np.maximum(np.minimum(np.maximum(res["punho_curto_d"], res["punho_curto_e"]), curta), punho_longo)
        res["manga"] = manga
        res["punho"] = punho
        res["tronco"] = np.clip(1.0 - manga - res["gola"] - res["bracadeira"], 0.0, 1.0)
    elif peca == "shorts":
        res["corpo"] = np.clip(1.0 - res["cos"], 0.0, 1.0)
    else:
        res["corpo"] = np.ones((h, w), np.float32)
        if "cano" in pela_malha:
            res["cano"] = pela_malha["cano"]
    return res


def coordenadas_tronco(w, h):
    """Coordenadas do tronco da camisa em cada pixel, iguais na frente e nas costas (para o padrão continuar na costura):
    x = -0,5 (lado direito de quem veste) … +0,5 (lado esquerdo), medido na largura da frente;
    d = 0 no ombro … 1 na barra (na frente para baixo, nas costas para cima); frente = True na metade de baixo.
    Com a malha da camisa, x e d vêm da posição 3D de cada pixel (o padrão fica reto e contínuo no corpo)."""
    r = rasterizar("jersey", w, h)
    if r is not None:
        _, pos, _ = r
        m = malha("jersey")
        corpo = m["V"][m["T"][~np.isin(m["ilha"], _ilhas_por_papel("jersey", m)["manga"])].ravel()]
        ytopo, ybarra = float(corpo[:, 1].max()), float(corpo[:, 1].min())
        # x: reto na UV (como o molde de costura: listras retas em cada painel), com a escala de cada painel corrigida pela
        # densidade da malha (metros por unidade de UV), para a listra ter a mesma largura no tecido na frente e nas costas
        dens = densidades_tronco()
        u = (np.arange(w, dtype=np.float32) + 0.5) / w
        v = (np.arange(h, dtype=np.float32) + 0.5) / h
        U, Vv = np.meshgrid(u, v)
        frente = Vv >= 0.5
        esc = np.where(frente, 1.0, dens["costas"] / dens["frente"]) / (FRENTE["u1"] - FRENTE["u0"])
        x = (U - 0.5) * esc
        # d: pela altura no corpo (aros e faixas ficam na mesma altura na frente e nas costas)
        d = (ytopo - pos[..., 1]) / max(1e-6, ytopo - ybarra)
        return x.astype(np.float32), d.astype(np.float32), frente
    u = (np.arange(w, dtype=np.float32) + 0.5) / w
    v = (np.arange(h, dtype=np.float32) + 0.5) / h
    U, V = np.meshgrid(u, v)
    x = (U - 0.5) / (FRENTE["u1"] - FRENTE["u0"])
    frente = V >= 0.5
    d = np.where(frente, (V - FRENTE["v0"]) / (FRENTE["v1"] - FRENTE["v0"]), (COSTAS["v1"] - V) / (COSTAS["v1"] - COSTAS["v0"]))
    return x, d, frente


def coordenadas_planas(w, h):
    """Calção e meião: x = 0..1 na largura, d = 0..1 na altura."""
    u = (np.arange(w, dtype=np.float32) + 0.5) / w
    v = (np.arange(h, dtype=np.float32) + 0.5) / h
    U, V = np.meshgrid(u, v)
    return U - 0.5, V, np.ones_like(U, dtype=bool)


_FRENTE3D = {}


def _frente3d():
    """Pontos da frente do tronco (pela malha): posição (x, y) no corpo e (u, v) na textura, para levar a foto ao molde."""
    if "p" in _FRENTE3D:
        return _FRENTE3D
    r = rasterizar("jersey", 512, 512)
    if r is None:
        return None
    mapa_i, pos, _ = r
    m = malha("jersey")
    mangas = _ilhas_por_papel("jersey", m)["manga"]
    ys, xs = np.nonzero((mapa_i >= 0) & ~np.isin(mapa_i, mangas))
    frente = ys >= 256
    ys, xs = ys[frente], xs[frente]
    p = pos[ys, xs][:, :2].astype(np.float64)
    from scipy.spatial import cKDTree
    ytopo, ybarra = float(np.percentile(p[:, 1], 99.5)), float(p[:, 1].min())
    faixas = np.linspace(ybarra, ytopo, 40)
    meia = np.array([np.abs(p[(p[:, 1] >= a) & (p[:, 1] < b), 0]).max() if ((p[:, 1] >= a) & (p[:, 1] < b)).any() else np.nan
                     for a, b in zip(faixas[:-1], faixas[1:])])
    meia = np.where(np.isnan(meia), np.nanmedian(meia), meia)
    _FRENTE3D.update(p=p, uv=np.stack([(xs + 0.5) / 512, (ys + 0.5) / 512], 1), arvore=cKDTree(p), ytopo=ytopo, ybarra=ybarra,
                     faixas=(faixas[:-1] + faixas[1:]) / 2, meia=meia)
    return _FRENTE3D


def foto_para_uv(fx, fy, fw=0.0, fh=0.0):
    """Caixa na foto (centro fx, fy e tamanho fw, fh, em fração da caixa do tronco: x da esquerda da imagem, y do ombro
    para a barra) -> (u, v, largura, altura) na textura da camisa. Com a malha, passa pelo corpo em 3D (a frente do molde
    não é esticada por igual); sem ela, caixa para caixa."""
    f = _frente3d()
    if f is None:
        u, v = foto_para_uv_frente(fx, fy)
        return u, v, fw * (FRENTE["u1"] - FRENTE["u0"]), fh * (FRENTE["v1"] - FRENTE["v0"])

    def ponto(ax, ay):
        y = f["ytopo"] - ay * (f["ytopo"] - f["ybarra"])
        meia = float(np.interp(y, f["faixas"], f["meia"]))
        _, i = f["arvore"].query([(ax - 0.5) * 2 * meia, y])
        return f["uv"][i]
    u, v = ponto(fx, fy)
    if fw or fh:
        ue, ud = ponto(fx - fw / 2, fy)[0], ponto(fx + fw / 2, fy)[0]
        vc, vb = ponto(fx, fy - fh / 2)[1], ponto(fx, fy + fh / 2)[1]
        return float(u), float(v), float(abs(ud - ue)), float(abs(vb - vc))
    return float(u), float(v), 0.0, 0.0


def foto_para_uv_frente(fx, fy):
    """Ponto na caixa do tronco da foto (0..1, 0..1; x da esquerda da imagem, y do ombro para a barra) -> (u, v) na frente."""
    return (FRENTE["u0"] + fx * (FRENTE["u1"] - FRENTE["u0"]), FRENTE["v0"] + fy * (FRENTE["v1"] - FRENTE["v0"]))
