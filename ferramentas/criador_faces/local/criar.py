"""Criador próprio, pela linha de comando (o servidor da ferramenta roda este arquivo e lê o progresso):

    python criar.py estado [--fet PASTA] [--jogo PASTA]
    python criar.py preparar [--fet PASTA] [--jogo PASTA]         monta o modelo das cabeças a partir do jogo
    python criar.py criar --saida PASTA [--id 123456] foto1 [foto2 ...]

Cada evento sai numa linha JSON: {"tipo": "progresso", "f": 0..1, "msg": ...}, {"tipo": "registro", "msg": ...},
{"tipo": "resultado", ...} ou {"tipo": "erro", "msg": ...}.
"""
import argparse
import json
import os
import sys
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(AQUI))
    import local  # noqa: F401
    __package__ = "local"
from . import REFERENCIA, VERSAO_MOTOR, Erro  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
LADO_MAX = 1600
MAX_FOTOS = 6


def emitir(**kw):
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def progresso(f, msg):
    emitir(tipo="progresso", f=round(float(f), 4), msg=msg)


def registro(*a):
    emitir(tipo="registro", msg=" ".join(str(x) for x in a))


def estado(fet=None, jogo=None):
    from . import modelo as MD
    from . import pontos as PT
    out = {"versao": VERSAO_MOTOR, "referencia": os.path.isfile(REFERENCIA), "modelos_faltando": PT.modelos_faltando(),
           "modelo": MD.meta() if MD.pronto() else None}
    try:
        from .jogo import Jogo
        j = Jogo(fet, jogo)
        e = j.estado()
        out["jogo"] = e
        if e["ok"] and out["modelo"]:
            out["modelo_atual"] = out["modelo"].get("chave") == j.chave()
    except Erro as ex:
        out["jogo"] = {"ok": False, "itens": [], "erro": str(ex)}
    return out


def preparar(fet=None, jogo=None):
    from . import modelo as MD
    from .jogo import Jogo
    j = Jogo(fet, jogo)
    j.exigir()
    if not j.indice_pronto():
        progresso(0.0, "Lendo o cache do FET pela primeira vez (1 a 2 minutos)")
    j.indice()
    return MD.construir(j, progresso, registro)


def ler_foto(caminho):
    import cv2
    import numpy as np
    try:
        img = cv2.imdecode(np.fromfile(caminho, np.uint8), cv2.IMREAD_COLOR)
    except OSError as ex:
        raise Erro("Não consegui abrir %s: %s" % (os.path.basename(caminho), ex)) from ex
    if img is None:
        raise Erro("Não consegui ler %s. O criador próprio aceita JPG, PNG e WebP." % os.path.basename(caminho))
    h, w = img.shape[:2]
    if max(h, w) > LADO_MAX:
        f = LADO_MAX / max(h, w)
        img = cv2.resize(img, (int(round(w * f)), int(round(h * f))), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(img[:, :, ::-1])


def criar(fotos, saida, ident="0", k=100, prior=4.0, tom=None, perspectiva=True):
    import numpy as np
    from . import ajustar as AJ
    from . import modelo as MD
    from . import olhos as OL
    from . import pontos as PT
    from . import saida as SD
    from . import silhueta as SL
    from . import textura as TX
    t0 = time.time()
    if not 1 <= len(fotos) <= MAX_FOTOS:
        raise Erro("Use de 1 a %d fotos." % MAX_FOTOS)
    if not MD.pronto():
        raise Erro("O modelo das cabeças do jogo ainda não foi preparado.")
    if not os.path.isfile(REFERENCIA):
        raise Erro("Falta a face de referência do FC 27 (messi_158023_fc27.fbx).")
    os.makedirs(saida, exist_ok=True)
    progresso(0.02, "Abrindo o modelo das cabeças")
    m = MD.Modelo()
    # ---- pontos e segmentação
    imgs, pts, segs = [], [], []
    for i, f in enumerate(fotos):
        progresso(0.05 + 0.15 * i / len(fotos), "Achando o rosto em %s" % os.path.basename(f))
        img = ler_foto(f)
        p = PT.detectar(img)
        if p is None:
            raise Erro("Não achei um rosto em %s. Use fotos nítidas, com o rosto grande e inteiro." % os.path.basename(f))
        imgs.append(img)
        pts.append(p)
        segs.append(PT.segmentar(img))
    PT.fechar()
    # ---- a foto mais de frente vai primeiro
    P = AJ.Pontos(m, k)
    h = m.secao("head_mat")
    c0 = (m.base + m.media)[h["off"]:h["off"] + h["n"]].mean(0)
    yaws = [abs(AJ.camera_afim(P.L0[:PT.N_ROSTO], p[:PT.N_ROSTO, :2], np.ones(PT.N_ROSTO), c0).yaw()) for p in pts]
    ordem = np.argsort(yaws)
    fotos = [fotos[i] for i in ordem]
    imgs, pts, segs = [imgs[i] for i in ordem], [pts[i] for i in ordem], [segs[i] for i in ordem]
    if yaws[ordem[0]] > 25:
        registro("aviso: nenhuma foto está de frente (a mais de frente está a %.0f°)" % yaws[ordem[0]])
    conts = [None] + [SL.contorno_foto(sg, p) for sg, p in zip(segs[1:], pts[1:])]
    # ---- forma
    progresso(0.22, "Ajustando a forma da cabeça às fotos")
    aj = AJ.ajustar(pts, m, k=k, prior=prior, contornos=conts, tamanhos=[(im.shape[1], im.shape[0]) for im in imgs],
                    perspectiva=perspectiva, log=registro,
                    prog=lambda f: progresso(0.22 + 0.45 * f, "Ajustando a forma da cabeça às fotos"))
    cams = aj["cameras"]
    X = m.posicoes(aj["c"])
    progresso(0.68, "Acertando os olhos")
    X, uvs, info_olhos = OL.aplicar(m, X)
    # ---- textura
    progresso(0.72, "Montando a textura careca")
    fl = [im.astype(np.float32) / 255.0 for im in imgs]
    tex, tom_usado, coberta = TX.gerar(m, X, fl, cams, pts, segs, N=1024, tom=tom)
    nome_fbx = "headmorphpreset_%s_0_0.fbx" % ident
    nome_cor = "face_%s_0_0_color.png" % ident
    progresso(0.86, "Gravando os arquivos")
    png = SD.salvar_png(os.path.join(saida, nome_cor), tex)
    SD.gravar_fbx(m, X, uvs, os.path.join(saida, nome_fbx))
    dp, du = SD.conferir_fbx(m, X, uvs, os.path.join(saida, nome_fbx))
    if dp > 1e-5 or du > 1e-5:
        raise Erro("O FBX gravado não conferiu na releitura (posição %.2g m, UV %.2g)." % (dp, du))
    try:
        with open(MD.OLHO_PNG, "rb") as f:
            png_olho = f.read()
    except OSError:
        png_olho = None
    SD.gravar_glb(m, X, uvs, png, png_olho, os.path.join(saida, "previa.glb"))
    progresso(0.93, "Gerando as imagens de conferência")
    SD.previa_fotos(m, X, cams, fl, tex, uvs[0], os.path.join(saida, "previa_fotos.png"))
    SD.previa_3d(m, X, tex, uvs[0], os.path.join(saida, "previa_3d.png"))
    rel = {"motor": VERSAO_MOTOR, "id": str(ident), "fotos": [os.path.basename(f) for f in fotos],
           "yaw": [round(c.yaw(), 1) for c in cams], "distancia_m": [None if c.k < 1e-3 else round(c.distancia(), 2) for c in cams],
           "erro_pontos_mm": [round(e, 2) for e in aj["erros"]], "norma_coeficientes": round(float(np.linalg.norm(aj["c"])), 2),
           "tom_da_pele_de_base": int(tom_usado), "textura_das_fotos": round(coberta, 3), "olhos": info_olhos,
           "segundos": round(time.time() - t0, 1),
           "arquivos": {"fbx": nome_fbx, "cor": nome_cor, "glb": "previa.glb", "previa_fotos": "previa_fotos.png",
                        "previa_3d": "previa_3d.png"}}
    np.savez(os.path.join(saida, "ajuste.npz"), c=aj["c"], cameras=json.dumps([c.dados() for c in cams]))
    with open(os.path.join(saida, "relatorio.json"), "w", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=1)
    progresso(1.0, "Pronto")
    return rel


def main():
    ap = argparse.ArgumentParser(description="Criador próprio de faces do FC 27")
    ap.add_argument("comando", choices=("estado", "preparar", "criar"))
    ap.add_argument("fotos", nargs="*")
    ap.add_argument("--saida")
    ap.add_argument("--id", default="0")
    ap.add_argument("--fet")
    ap.add_argument("--jogo")
    ap.add_argument("--tom", type=int)
    ap.add_argument("--k", type=int, default=100)
    ap.add_argument("--prior", type=float, default=4.0)
    ap.add_argument("--sem-perspectiva", action="store_true")
    a = ap.parse_intermixed_args()
    try:
        if a.comando == "estado":
            emitir(tipo="resultado", **estado(a.fet, a.jogo))
        elif a.comando == "preparar":
            emitir(tipo="resultado", modelo=preparar(a.fet, a.jogo))
        else:
            if not a.saida:
                raise Erro("Falta a pasta de saída.")
            emitir(tipo="resultado", **criar(a.fotos, a.saida, a.id, a.k, a.prior, a.tom, not a.sem_perspectiva))
    except Erro as ex:
        emitir(tipo="erro", msg=str(ex))
        return 2
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        emitir(tipo="erro", msg="%s: %s" % (type(ex).__name__, ex))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
