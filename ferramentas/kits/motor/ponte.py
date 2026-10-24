"""Ponte entre a interface do Criador de Kits (servidor) e o motor (numpy, SciPy, Pillow e OpenCV).

    python ponte.py servico        fica aberto: lê um pedido JSON por linha na entrada e responde uma linha JSON por evento

Pedido:   {"id": 1, "cmd": "previa" | "doador" | "foto" | "recorte_logo" | "exportar" | "malha" | "miniatura", "args": {...}}
Resposta: {"id": 1, "ok": true, ...}  ou  {"id": 1, "ok": false, "erro": "..."};  "exportar" manda antes
          {"id": 1, "progresso": 0.4, "msg": "..."}.
"""
import json
import os
import sys
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
SUPERTOOL = os.path.dirname(os.path.dirname(os.path.dirname(AQUI)))
sys.path.append(os.path.join(SUPERTOOL, "ferramentas", "faces", "motor"))     # leitor de FBX (cena, fbxio)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def emitir(**kw):
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def cmd_previa(a, _id):
    """Textura de cor (recolorida + padrão, sem os logos: a interface desenha os logos por cima)."""
    import numpy as np
    from PIL import Image
    import kit as K
    peca = a["peca"]
    arqs = K.arquivos_doador(a["projeto"]["doador"])
    tam = a.get("tamanho")
    if not tam:
        w, h = Image.open(arqs[peca]).size
        lim = int(a.get("max", 1024))
        f = min(1.0, lim / max(w, h))
        tam = (max(1, round(w * f)), max(1, round(h * f)))
    origem, _ = K.origem_cor(a["projeto"], peca, arqs)
    rgb = K.renderizar_cor(peca, a["projeto"]["pecas"][peca], origem, tam)
    if a.get("com_logos"):
        rgb = K.colar_logos(rgb, a["projeto"]["pecas"][peca].get("logos") or [], peca)
    os.makedirs(os.path.dirname(a["saida"]), exist_ok=True)
    Image.fromarray(np.asarray(rgb), "RGB").save(a["saida"], compress_level=1)
    return {"caminho": a["saida"], "tamanho": list(tam)}


def cmd_doador(a, _id):
    import kit as K
    d = K.analisar_doador(a["pasta"])
    return {"doador": d}


def cmd_projeto_inicial(a, _id):
    import kit as K
    return {"projeto": K.projeto_inicial(a["pasta"], **(a.get("cores") or {}))}


def cmd_foto(a, _id):
    import foto as F
    return {"analise": F.analisar(a["caminho"], a["pasta"])}


def cmd_recorte_logo(a, _id):
    """Refaz o PNG de um logo tirado da foto com outro modo de recorte: cor (só o que destoa), bloco (preenchido) ou
    foto (o retângulo inteiro)."""
    import numpy as np
    from PIL import Image, ImageFilter
    base = a["base"]            # .../logo_3  (sem extensão)
    foto = Image.open(base + "_foto.png").convert("RGBA")
    if a["modo"] == "foto":
        alfa = Image.new("L", foto.size, 255)
    else:
        alfa = Image.open(base + ("_bloco.png" if a["modo"] == "bloco" else "_cor.png")).convert("L").filter(ImageFilter.GaussianBlur(0.7))
    foto.putalpha(alfa)
    if foto.width < 256:
        f = 256 / foto.width
        foto = foto.resize((256, max(1, round(foto.height * f))), Image.LANCZOS)
    destino = a["destino"]
    foto.save(destino)
    return {"caminho": destino, "tamanho": [foto.width, foto.height], "transparente": bool((np.asarray(alfa) < 128).any())}


def cmd_importar_logo(a, _id):
    """Copia uma imagem para a pasta de logos como PNG RGBA. tirar_fundo: se a imagem não tem transparência e as bordas
    são de uma cor só, tira esse fundo (preenchendo a partir das bordas)."""
    import numpy as np
    from PIL import Image, ImageFilter
    from scipy import ndimage as nd
    im = Image.open(a["origem"])
    im.load()
    im = im.convert("RGBA")
    arr = np.asarray(im).copy()
    tirou = False
    if a.get("tirar_fundo", True) and (arr[..., 3] > 250).all():
        rgb = arr[..., :3].astype(np.int16)
        borda = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        fundo = np.median(borda, 0)
        if np.median(np.abs(borda - fundo).max(1)) < 12:
            perto = np.abs(rgb - fundo).max(-1) < 28
            rot, _ = nd.label(perto)
            ids = set(np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]]))) - {0}
            fora = np.isin(rot, list(ids))
            if 0.02 < fora.mean() < 0.95:
                arr[..., 3] = np.where(fora, 0, 255).astype(np.uint8)
                arr[..., 3] = np.asarray(Image.fromarray(arr[..., 3]).filter(ImageFilter.GaussianBlur(0.6)))
                tirou = True
    out = Image.fromarray(arr, "RGBA")
    bb = out.getchannel("A").getbbox()
    if bb:
        out = out.crop(bb)
    if max(out.size) > 2048:
        out.thumbnail((2048, 2048), Image.LANCZOS)
    os.makedirs(os.path.dirname(a["destino"]), exist_ok=True)
    out.save(a["destino"])
    return {"caminho": a["destino"], "tamanho": [out.width, out.height], "tirou_fundo": tirou}


def cmd_exportar(a, _id):
    import kit as K
    def prog(f, msg):
        emitir(id=_id, progresso=round(f, 3), msg=msg)
    return K.exportar(a["projeto"], a["saida"], prog)


def cmd_miniatura(a, _id):
    """Miniatura da camisa de um kit (biblioteca de doadores) e uma nota de 'limpeza' (desvio de cor: menor = mais lisa)."""
    import numpy as np
    from PIL import Image
    import kit as K
    arqs = K.arquivos_doador(a["pasta"])
    im = Image.open(arqs["jersey"]).convert("RGB")
    im.draft("RGB", (256, 256))
    pq = im.resize((256, 256), Image.BILINEAR)
    os.makedirs(os.path.dirname(a["saida"]), exist_ok=True)
    pq.save(a["saida"])
    arr = np.asarray(pq.crop((80, 128, 176, 240)), np.float32)       # frente
    return {"caminho": a["saida"], "desvio": round(float(arr.reshape(-1, 3).std(0).mean()), 2)}


def cmd_malha(a, _id):
    """Malha (LOD0, todas as partes) de um FBX exportado pelo FET: V, UV (v para cima) e T, para a prévia 3D."""
    import numpy as np
    from cena import Cena
    c = Cena(a["caminho"])
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
        raise ValueError("O FBX não tem malha com UV.")
    V, UV, T = np.concatenate(Vs), np.concatenate(UVs), np.concatenate(Ts)
    return {"V": [round(float(x), 5) for x in V.ravel()], "UV": [round(float(x), 5) for x in UV.ravel()],
            "T": [int(x) for x in T.ravel()]}


def cmd_molde(_a, _id):
    """Partes do molde (para a interface desenhar as linhas por cima da textura)."""
    import molde as M
    return {"molde": {"jersey": {"regioes": M.REGIOES_CAMISA, "gola": M.GOLA, "frente": M.FRENTE, "costas": M.COSTAS,
                                 "esticar": M.ESTICAR_CAMISA},
                      "shorts": {"regioes": M.REGIOES_CALCAO}, "socks": {"regioes": M.REGIOES_MEIAO}}}


def cmd_template(a, _id):
    """Partes de um template de recorte (ou de gola) já com as cores iniciais."""
    import kit as K
    return {"camadas": K.camadas_template(a["arquivo"], a.get("cores")), "template": K.analisar_template(a["arquivo"])}


def cmd_importar_template(a, _id):
    """Copia uma imagem para a pasta de templates do usuário no tamanho da peça (golas continuam transparentes)."""
    from PIL import Image
    import molde as M
    im = Image.open(a["origem"])
    im.load()
    gola = a["categoria"] == "golas"
    im = im.convert("RGBA" if gola else "RGB")
    tam = M.TAMANHOS[{"camisa": "jersey", "golas": "jersey", "calcao": "shorts", "meiao": "socks"}[a["categoria"]]]
    if im.size != tam:
        im = im.resize(tam, Image.NEAREST if max(im.size) >= max(tam) else Image.LANCZOS)
    os.makedirs(os.path.dirname(a["destino"]), exist_ok=True)
    im.save(a["destino"])
    return {"caminho": a["destino"]}


def cmd_miniatura_img(a, _id):
    """Miniatura (até 256 px, mantendo a transparência) de uma imagem qualquer, para as listas de templates."""
    from PIL import Image
    im = Image.open(a["origem"])
    im.draft("RGB", (256, 256))
    im = im.convert("RGBA")
    im.thumbnail((256, 256), Image.NEAREST if im.width >= 1024 else Image.LANCZOS)
    os.makedirs(os.path.dirname(a["saida"]), exist_ok=True)
    im.save(a["saida"])
    return {"caminho": a["saida"]}


def cmd_minikit(a, _id):
    import kit as K
    import minikit as MK
    arqs = K.arquivos_doador(a["projeto"]["doador"])
    MK.desenhar(K.composto_camisa(a["projeto"], arqs), a["saida"])
    return {"caminho": a["saida"]}


CMDS = {"miniatura_img": cmd_miniatura_img, "previa": cmd_previa, "template": cmd_template, "importar_template": cmd_importar_template, "minikit": cmd_minikit, "molde": cmd_molde, "doador": cmd_doador, "projeto_inicial": cmd_projeto_inicial, "foto": cmd_foto,
        "recorte_logo": cmd_recorte_logo, "importar_logo": cmd_importar_logo, "exportar": cmd_exportar,
        "miniatura": cmd_miniatura, "malha": cmd_malha}


def servico():
    emitir(id=0, ok=True, pronto=True)
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            p = json.loads(linha)
        except ValueError:
            continue
        _id = p.get("id")
        t = time.time()
        try:
            r = CMDS[p["cmd"]](p.get("args") or {}, _id)
            emitir(id=_id, ok=True, s=round(time.time() - t, 2), **r)
        except Exception as ex:  # noqa: BLE001
            import kit as K
            amigavel = isinstance(ex, (K.ErroKit, FileNotFoundError, ValueError))
            emitir(id=_id, ok=False, erro=str(ex) if amigavel else f"{type(ex).__name__}: {ex}",
                   rastro=traceback.format_exc(limit=6))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "servico":
        servico()
    else:
        sys.exit(__doc__)
