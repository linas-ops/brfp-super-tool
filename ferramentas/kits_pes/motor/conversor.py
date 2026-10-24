"""Kits do PES 2021 -> FC 27: camisa, calção e meião a partir da textura única do kit do PES.

O kit do PES tem as três peças (camisa com mangas curtas e longas, gola, calção e meião) numa textura só; no FC 27 cada
peça tem a sua (jersey 2048×2048, shorts 1024×512, socks 512×256) e outra UV. A correspondência pixel a pixel foi
calculada uma vez pela superfície 3D dos dois uniformes (gerar_mapas.py) e vem pronta em mapas/mapas_pes2021_fc27.npz:
cada pixel do FC sabe de que ponto da textura do PES ele veste o mesmo lugar do corpo, então as proporções (listras,
escudo, patrocínio, números nas mangas) saem certas. Onde o FC encolhe a textura, a cor é filtrada (mipmap) para não
serrilhar.

Os mapas de tecido (normal, coeff, taa, weave), o escudo, a marca, a braçadeira e o hotspot vêm de um kit base do FC 27
exportado pelo FET (qualquer kit: só a cor é trocada).

    python conversor.py KIT_PES.png --base PASTA_DO_KIT_BASE --saida PASTA --teamid 111329 --time guarani [--tipo home]

Requer numpy, SciPy e Pillow (o Python embutido do Super Tool). DDS é lido pelo Pillow ou, se ele não souber, pelo
texconv que vem com o Super Tool.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit_nomes import PECAS, TIPOS, ErroConversao, arquivos_base, destino_kit, tipo_pelo_nome  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(os.path.dirname(os.path.dirname(AQUI)))
MAPAS = os.path.join(AQUI, "mapas", "mapas_pes2021_fc27.npz")
REF = os.path.join(AQUI, "referencia")
NOME_PECA = {"jersey": "camisa", "shorts": "calção", "socks": "meião"}
FORA, TRONCO, MANGA_CURTA, MANGA_LONGA, GOLA, DO_BASE = 0, 1, 2, 3, 4, 9
EXT_IMAGEM = (".png", ".dds", ".tga", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BLOCO = 1 << 20                      # pixels por vez na amostragem (memória)
NORMAL_LISO = (128, 128, 0, 255)     # formato dos crest_*/brand_*_normal (B = 0, A = 255)


# ------------------------------------------------------------------ mapas prontos
_MAPAS = {}


def mapas():
    """{peca: {uv (H×W×2, v para cima), parte (H×W), escala (px do PES em 2048 por px do FC)}, "ilhas" e "buraco":
    máscaras 2048×2048 da textura do PES (onde ela é usada; buraco da gola no tronco)}."""
    if _MAPAS:
        return _MAPAS
    if not os.path.isfile(MAPAS):
        raise ErroConversao(f"Falta o arquivo de mapas da conversão ({os.path.relpath(MAPAS, SUPERTOOL)}): atualize o Super Tool.")
    with np.load(MAPAS) as z:
        for p in PECAS:
            u = np.cumsum(z[p + "_du"].astype(np.uint16), axis=1, dtype=np.uint16)
            v = np.cumsum(z[p + "_dv"].astype(np.uint16), axis=1, dtype=np.uint16)
            _MAPAS[p] = {"uv": np.stack([u, v], -1).astype(np.float32) / 65535.0, "parte": z[p + "_parte"],
                         "escala": z[p + "_escala"].astype(np.float32) / 8.0}
        _MAPAS["ilhas"] = np.unpackbits(z["pes_ilhas"], axis=1)[:, :2048].astype(bool)
        _MAPAS["buraco"] = (np.unpackbits(z["pes_buraco"], axis=1)[:, :2048].astype(bool) if "pes_buraco" in z.files
                            else np.zeros((2048, 2048), bool))
    return _MAPAS


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
    if temalfa and a[..., 3].min() >= 255:
        a = a[..., :3]
    return a


def gravar_png(a, caminho, modo=None):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    a = np.clip(np.rint(a), 0, 255).astype(np.uint8)
    im = Image.fromarray(a, modo or ("RGBA" if a.shape[2] == 4 else "RGB"))
    tmp = caminho + ".tmp.png"
    im.save(tmp, optimize=False, compress_level=6)
    os.replace(tmp, caminho)


def redimensionar(a, w, h):
    from PIL import Image
    if a.shape[1] == w and a.shape[0] == h:
        return a
    return np.stack([np.asarray(Image.fromarray(a[..., c].astype(np.float32), "F").resize((w, h), Image.LANCZOS))
                     for c in range(a.shape[2])], -1)


def preencher_fora(img, cobertos):
    """Fora das ilhas da UV, repete o pixel coberto mais próximo (a filtragem não puxa a cor do fundo)."""
    from scipy import ndimage
    if cobertos.all() or not cobertos.any():
        return img
    iy, ix = ndimage.distance_transform_edt(~cobertos, return_distances=False, return_indices=True)
    return img[iy, ix]


def tapar_buraco(img, buraco, margem=3, janela=16):
    """Buraco da gola no tronco do PES: em cima o decote (onde o kit do PES desenha a gola: sempre refeito) e embaixo
    a carcela (refeita só quando o desenho dela não é o do tronco em volta). Ali sobe o desenho do tronco da frente,
    coluna por coluna (mediana de `janela` linhas logo abaixo): as listras e a cor do tronco continuam até o decote do
    FC, sem puxar os logos da nuca."""
    larg = buraco.sum(1)
    if not larg.any():
        return img
    largas = np.nonzero(larg >= 0.75 * larg.max())[0]
    refazer = buraco.copy()
    carcela = buraco.copy()
    carcela[:largas[-1] + 1] = False
    if carcela.any():
        ys, xs = np.nonzero(carcela)
        w = xs.max() - xs.min() + 1
        lados = np.zeros_like(buraco)
        lados[ys.min():ys.max() + 1, max(0, xs.min() - w):xs.max() + 1 + w] = True
        lados &= ~buraco
        if lados.any() and np.abs(img[carcela].mean(0) - img[lados].mean(0)).max() < 30:
            refazer &= ~carcela             # a carcela já tem o desenho do tronco: fica
    out = img.copy()
    h = img.shape[0]
    for x in np.nonzero(refazer.any(0))[0]:
        ys = np.nonzero(refazer[:, x])[0]
        y0 = ys[-1] + 1 + margem
        abaixo = img[y0:y0 + janela, x] if y0 < h else img[max(0, ys[0] - margem - janela):max(0, ys[0] - margem), x]
        if len(abaixo):
            out[ys, x] = np.median(abaixo, 0)
    return out


def cor_dominante(px):
    """Cor mais comum (média dos pixels do tom mais frequente)."""
    q = np.clip(px, 0, 255).astype(np.int64) // 16
    k = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    return px[k == np.bincount(k).argmax()].mean(0)


def _na_textura(masc, h, w):
    """Máscara 2048×2048 no tamanho da textura do PES."""
    if (h, w) == masc.shape:
        return masc
    iy = np.minimum((np.arange(h) + 0.5) * masc.shape[0] / h, masc.shape[0] - 1).astype(np.int64)
    ix = np.minimum((np.arange(w) + 0.5) * masc.shape[1] / w, masc.shape[1] - 1).astype(np.int64)
    return masc[iy][:, ix]


def piramide(img, niveis=6):
    """Níveis de mipmap (média 2×2)."""
    out = [img]
    while len(out) < niveis and min(out[-1].shape[:2]) >= 8:
        a = out[-1]
        h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
        out.append(a[:h, :w].reshape(h // 2, 2, w // 2, 2, -1).mean((1, 3)))
    return out


def bilinear(img, uv):
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


def amostrar_mip(niv, uv, pegada):
    """Trilinear: `pegada` = quantos pixels da fonte (nível 0) cabem num pixel do destino."""
    lv = np.clip(np.log2(np.maximum(pegada, 1.0)), 0, len(niv) - 1)
    l0 = np.minimum(np.floor(lv).astype(np.int64), len(niv) - 1)
    f = (lv - l0)[:, None].astype(np.float32)
    out = np.zeros((len(uv), niv[0].shape[2]), np.float32)
    for k in np.unique(l0):
        m = l0 == k
        a = bilinear(niv[k], uv[m])
        if k + 1 < len(niv):
            a = a * (1 - f[m]) + bilinear(niv[k + 1], uv[m]) * f[m]
        out[m] = a
    return out


def converter_texturas(img, progresso=lambda m: None):
    """Textura do PES (H×W×3, 0–255) -> {peca: H×W×3 float32} no layout do FC 27 (sem a braçadeira)."""
    M = mapas()
    h, w = img.shape[:2]
    fator = max(w, h) / 2048.0
    rgb = tapar_buraco(img[..., :3].astype(np.float32), _na_textura(M["buraco"], h, w), max(1, round(3 * fator)), max(4, round(16 * fator)))
    niv = piramide(preencher_fora(rgb, _na_textura(M["ilhas"], h, w)))
    out = {}
    for peca in PECAS:
        progresso(f"Montando {'a' if peca == 'jersey' else 'o'} {NOME_PECA[peca]}")
        m = M[peca]
        H, W = m["parte"].shape
        uv = m["uv"].reshape(-1, 2)
        peg = m["escala"].reshape(-1) * fator
        cor = np.empty((H * W, 3), np.float32)
        for i0 in range(0, H * W, BLOCO):
            cor[i0:i0 + BLOCO] = amostrar_mip(niv, uv[i0:i0 + BLOCO].astype(np.float64), peg[i0:i0 + BLOCO])
        out[peca] = cor.reshape(H, W, 3)
        gola = m["parte"] == GOLA
        if gola.any():                 # a gola do FC não vem do PES: fica com a cor do tronco
            out[peca][gola] = cor_dominante(out[peca][m["parte"] == TRONCO])
    return out


# ------------------------------------------------------------------ kit base (exportado pelo FET)
def resumo_base(pasta):
    """Para a interface: time, tipo e tamanhos do kit base."""
    from PIL import Image
    a = arquivos_base(pasta)
    tam = {}
    for p in PECAS:
        with Image.open(a[p]) as im:
            tam[p] = list(im.size)
    return {"pasta": a["pasta"], "teamid": a["teamid"], "tipo": a["tipo"], "n": a["n"], "v": a["v"], "tamanhos": tam,
            "time": a["time"]}


def _generico(caminho, destino):
    """Mapa de tecido sem os desenhos do kit base: o valor mais comum em tudo (no taa, só dentro das ilhas)."""
    from PIL import Image
    im = Image.open(caminho)
    a = np.asarray(im)
    if a.ndim == 2:
        shutil.copyfile(caminho, destino)
        return
    plano = a.reshape(-1, a.shape[-1])
    taa = "_taa" in os.path.basename(caminho)
    ref = plano[plano[:, 0] > 0] if taa and (plano[:, 0] > 0).any() else plano
    vals, cont = np.unique(ref[:: max(1, len(ref) // 200000)], axis=0, return_counts=True)
    out = np.empty_like(a)
    out[...] = vals[cont.argmax()]
    if taa:
        fora = a[..., 0] == 0
        out[fora] = a[fora]
    Image.fromarray(out, im.mode).save(destino)


# ------------------------------------------------------------------ conversão do kit
def converter(entrada, base, saida, teamid, time_, tipo="home", variacao=0, escudo="apagar", tecido="base",
              substituir=False, progresso=lambda f, m: None):
    """Converte a textura do PES `entrada` e grava a pasta do kit do FC 27 em `saida` (raiz dos kits).
    escudo: "apagar" (o escudo e a marca já vêm desenhados no kit do PES) ou "base" (mantém os do kit base);
    tecido: "base" (normal, coeff e taa do kit base) ou "generico" (coeff e taa lisos, sem os desenhos do kit base);
    substituir: a pasta do kit, se já existir, é apagada antes (senão é erro)."""
    t0 = time.time()
    if tipo not in TIPOS:
        raise ErroConversao(f"Tipo de kit inválido: {tipo}")
    if not str(teamid).strip().isdigit() or int(teamid) <= 0:
        raise ErroConversao("Informe o ID do time (teamid) do FC 27.")
    arqs = arquivos_base(base)
    pasta, rel, suf = destino_kit(saida, teamid, time_, tipo, variacao)
    if os.path.normcase(os.path.abspath(pasta)) == os.path.normcase(arqs["pasta"]):
        raise ErroConversao("O destino é a própria pasta do kit base: escolha outro time, tipo ou pasta de saída.")
    if os.path.isdir(pasta):
        if not substituir:
            raise ErroConversao(f"Já existe o kit {rel} na saída (ligue Substituir kits existentes).")
        shutil.rmtree(pasta)
    progresso(0.02, "Lendo a textura do PES")
    img = ler_imagem(entrada)
    h, w = img.shape[:2]
    avisos = []
    if abs(w / h - 1) > 0.02:
        avisos.append(f"A textura tem {w}×{h}: a do kit do PES é quadrada (2048×2048 ou 1024×1024). Confira o resultado.")
    elif max(w, h) < 1024:
        avisos.append(f"Textura pequena ({w}×{h}): o resultado fica borrado (o FC usa a camisa em 2048×2048).")
    cores = converter_texturas(img, lambda m: progresso(0.1, m))
    feitos, previas = [], {}
    os.makedirs(pasta, exist_ok=True)
    for i, peca in enumerate(PECAS):
        progresso(0.55 + 0.1 * i, f"Gravando {'a' if peca == 'jersey' else 'o'} {NOME_PECA[peca]}")
        rgb = cores[peca]
        if peca == "jersey":
            parte = mapas()[peca]["parte"]
            do_base = parte == DO_BASE
            if do_base.any():          # braçadeira de capitão: fica a do kit base
                b = redimensionar(ler_imagem(arqs[peca])[..., :3], rgb.shape[1], rgb.shape[0])
                rgb[do_base] = b[do_base]
        dst = os.path.join(pasta, peca, f"{peca}_{suf}_color.png")
        gravar_png(rgb, dst)
        feitos.append(dst)
        previas[peca] = dst
    progresso(0.88, "Mapas de tecido, escudo e marca")
    velho = arqs["sufixo"]
    for f in arqs["outros"]:
        nome = os.path.basename(f)
        peca = os.path.basename(os.path.dirname(f))
        dst = os.path.join(pasta, peca, nome.replace(velho, suf))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        papel = re.sub(r"_" + re.escape(velho) + r"_", "_", nome).replace(".png", "")    # ex.: crest_color, jersey_taa
        logo = re.match(r"(crest|crest_shorts|brand_jersey|brand_shorts)_(color|normal)$", papel)
        if escudo == "apagar" and logo:
            from PIL import Image
            with Image.open(f) as im:
                tam = im.size
            if logo.group(2) == "color":
                Image.new("RGBA", tam, (0, 0, 0, 0)).save(dst)
            else:
                Image.new("RGBA", tam, NORMAL_LISO).save(dst)
        elif tecido == "generico" and re.match(r"(jersey|shorts|socks)_(coeff|taa)$", papel):
            _generico(f, dst)
        else:
            shutil.copyfile(f, dst)
        feitos.append(dst)
    with open(arqs["hotspot"], encoding="utf-8") as fh:
        hs = json.load(fh)
    hs["AssetName"] = f"content/character/kit/{rel}/hotspots_{suf}"
    dst = os.path.join(pasta, f"hotspots_{suf}.hotspot")
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(hs, fh, indent=2)
    feitos.append(dst)
    progresso(1.0, "Pronto")
    return {"pasta": pasta, "rel": rel, "sufixo": suf, "arquivos": feitos, "previas": previas, "avisos": avisos,
            "entrada_px": [w, h], "s": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ para a lista e a prévia
def info(caminho):
    from PIL import Image
    try:
        with Image.open(caminho) as im:
            w, h = im.size
    except Exception:  # noqa: BLE001 — DDS que o Pillow não lê
        a = ler_imagem(caminho)
        h, w = a.shape[:2]
    return {"largura": int(w), "altura": int(h), "quadrada": abs(w / h - 1) <= 0.02, "tipo_sugerido": tipo_pelo_nome(caminho)}


def previa(entrada, saida_png, lado=1024):
    """Cópia reduzida (PNG RGB, até `lado` px) para a interface."""
    from PIL import Image
    a = ler_imagem(entrada)
    im = Image.fromarray(np.clip(np.rint(a[..., :3]), 0, 255).astype(np.uint8), "RGB")
    if max(im.size) > lado:
        im.thumbnail((lado, lado), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(saida_png)), exist_ok=True)
    im.save(saida_png)
    return saida_png


FC_FBX = {"jersey": "jersey_0_0_0_0_1_0_0_mesh.fbx", "shorts": "shorts_0_0_0_mesh.fbx", "socks": "sock_0_0_1_0_0_mesh.fbx"}
PES_OBJ = "pes2021_kit.obj"
PES_PREVIA = ["Shirt_Out_mesh_id_1.006", "Sleeves_Short_MESH_sleeve_short_001", "Collar_01_MESH_collar_901",
              "Shorts_With_Shirt_Out_MESH_pants_out_sub", "Socks_MESH_socks_middle"]


def _lista(V, UV, T):
    return {"V": [round(float(x), 5) for x in np.asarray(V).ravel()], "UV": [round(float(x), 5) for x in np.asarray(UV).ravel()],
            "T": [int(x) for x in np.asarray(T).ravel()]}


def malha_previa(qual):
    """Malha da prévia 3D: qual = jersey | shorts | socks (FC 27, do FET) ou pes (o kit inteiro do PES 2021)."""
    if qual == "pes":
        caminho = os.path.join(REF, PES_OBJ)
        V, VT, objs, cur = [], [], {}, None
        with open(caminho, encoding="utf-8", errors="replace") as f:
            for ln in f:
                if ln.startswith("v "):
                    V.append(ln.split()[1:4])
                elif ln.startswith("vt "):
                    VT.append(ln.split()[1:3])
                elif ln.startswith("o "):
                    cur = ln[2:].strip()
                elif ln.startswith("f ") and cur in PES_PREVIA:
                    idx = [w.split("/")[:2] for w in ln.split()[1:]]
                    for i in range(1, len(idx) - 1):
                        objs.setdefault(cur, []).append((idx[0], idx[i], idx[i + 1]))
        V, VT = np.array(V, np.float64), np.array(VT, np.float64)
        fs = np.array([t for n in PES_PREVIA for t in objs.get(n, [])], np.int64)     # (m, 3, 2)
        par, inv = np.unique(fs.reshape(-1, 2), axis=0, return_inverse=True)
        P, U = V[par[:, 0] - 1], VT[par[:, 1] - 1]
        alt = P[:, 1].max() - P[:, 1].min()
        P = P / alt * 1.0 if alt > 10 else P          # em metros, como o FC (só para enquadrar)
        return _lista(P, U, inv.reshape(-1, 3))
    sys.path.append(os.path.join(SUPERTOOL, "ferramentas", "faces", "motor"))
    from cena import Cena
    c = Cena(os.path.join(REF, FC_FBX[qual]))
    lod = min((m.lod for m in c.malhas), default=0)
    Vs, UVs, Ts, n = [], [], [], 0
    for m in c.malhas:
        if m.lod != lod or getattr(m, "uv0", None) is None:
            continue
        Vs.append(np.asarray(m.V, np.float64))
        UVs.append(np.asarray(m.uv0, np.float64))
        Ts.append(np.asarray(m.T, np.int64) + n)
        n += len(m.V)
    if not Vs:
        raise ErroConversao("O FBX não tem malha com UV.")
    return _lista(np.concatenate(Vs), np.concatenate(UVs), np.concatenate(Ts))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("entrada", help="textura do kit do PES (PNG, DDS, TGA, JPG)")
    ap.add_argument("--base", required=True, help="pasta de um kit do FC 27 exportado pelo FET (…/home_0_0)")
    ap.add_argument("--saida", required=True, help="raiz dos kits (a pasta kit do mod)")
    ap.add_argument("--teamid", required=True, type=int)
    ap.add_argument("--time", required=True, help="nome da pasta do time (ex.: guarani)")
    ap.add_argument("--tipo", default=None, choices=list(TIPOS))
    ap.add_argument("--variacao", type=int, default=0)
    ap.add_argument("--manter-escudo", action="store_true", help="mantém o escudo e a marca do kit base")
    ap.add_argument("--tecido-generico", action="store_true", help="coeff e taa lisos, sem os desenhos do kit base")
    ap.add_argument("--substituir", action="store_true", help="apaga a pasta do kit, se já existir")
    a = ap.parse_args()
    r = converter(a.entrada, a.base, a.saida, a.teamid, a.time, a.tipo or tipo_pelo_nome(a.entrada) or "home", a.variacao,
                  "base" if a.manter_escudo else "apagar", "generico" if a.tecido_generico else "base",
                  a.substituir, lambda f, m: print(f"{int(100 * f):3d}% {m}", flush=True))
    for x in r["avisos"]:
        print("AVISO:", x)
    print(f"gravado {r['pasta']} ({r['s']} s)")


if __name__ == "__main__":
    main()
