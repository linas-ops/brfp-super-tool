"""Conversor de Placares PES → FC (BRFP Super Tool) — servidor local da interface.

    python servidor.py [--porta 8781] [--sem-janela] [pasta do placar do PES]

Lê um placar do PES 2021 (os .bin de common/menu/licence: game2dPes.bin e companhia) e monta um placar do FC num molde
do Editor de Placares (o Generic do jogo, ou um placar com o fundo numa imagem grande e os textos soltos, como os do
pack do LTA). A tela da substituição do pacote vai junto, na substituição do mesmo conjunto (o Generic/overlay_9021 do
jogo é o molde). O resultado é gravado como projetos do Editor de Placares, na pasta de saída dele: abre lá e continua
editando.

O leitor do PES (motor/afp.py e motor/pes.py) usa numpy e Pillow; a parte do FC usa os módulos do próprio Editor de
Placares (ferramentas/placares/nucleo), em Python padrão.
"""
import argparse
import base64
import io
import os
import re
import sys
import threading
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.join(AQUI, "motor")
CACHE = os.path.join(AQUI, "cache")
# o Editor de Placares do Super Tool; --editor <pasta> (ou BRFP_EDITOR_PLACARES) usa outra cópia, para testes
EDITOR = ((sys.argv[sys.argv.index("--editor") + 1] if "--editor" in sys.argv[:-1] else None)
          or os.environ.get("BRFP_EDITOR_PLACARES") or os.path.join(os.path.dirname(AQUI), "placares"))
os.environ["BRFP_EDITOR_PLACARES"] = EDITOR
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))
sys.path.insert(0, MOTOR)
sys.path.insert(0, EDITOR)

import base  # noqa: E402

VERSAO = "1.2"
GRUPO = "placares_pes"                 # numpy e Pillow
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "pasta": "", "molde": None, "x": 64, "y": 48, "escala": 1.0, "alvo": "molde", "alvo_outro": "", "fonte_pes": True,
    "subst": True})
LOCK = threading.RLock()
MOTOR_OK = {"ok": False, "msg": "verificando…"}
PLACARES = {}                          # pasta -> PlacarPes
MOLDES = {"lista": None, "quando": 0, "erro": None}
GENERIC = "data/ui/game/overlays/Generic/overlay_9002.big"
GENERIC_SUBST = "data/ui/game/overlays/Generic/overlay_9021.big"     # a substituição do Generic: molde da do PES
SUBST = {}                             # id da fonte do jogo -> (MoldeSubst, simulação)


def verificar_motor():
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        MOTOR_OK.update(ok=True, msg="numpy %s · Pillow %s" % (numpy.__version__, PIL.__version__))
    except ImportError:
        import componentes
        MOTOR_OK.update(ok=False, msg=componentes.falta_msg(GRUPO))


def motor():
    if not MOTOR_OK["ok"]:
        verificar_motor()
    if not MOTOR_OK["ok"]:
        raise base.ErroUsuario(MOTOR_OK["msg"])
    import afp
    import fc
    import pes
    return afp, pes, fc


# ------------------------------------------------------------------ o Editor de Placares (como biblioteca)

def editor():
    """O servidor do Editor de Placares importado como módulo: fontes (jogo, mods, pastas), saída e projetos."""
    import servidor as ED   # o do Editor de Placares (EDITOR vem antes no sys.path)
    if not getattr(ED, "_fontes_montadas", False):
        ED.montar_fontes()
        ED._fontes_montadas = True
    return ED


def info_editor():
    try:
        ED = editor()
        sai = ED.saida_atual()
        return {"ok": True, "saida": sai["caminho"], "saida_nome": sai["nome"], "eh_le": sai["eh_le"],
                "fontes": [ED._nome_fonte(f) for f in ED.E.fontes.values() if f.id != "saida"]}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "erro": f"Não consegui usar o Editor de Placares: {ex}"}


def listar_moldes(forcar=False):
    """Placares do FC (…002.big) das fontes do Editor de Placares que servem de molde."""
    with LOCK:
        if MOLDES["lista"] is not None and not forcar:
            return MOLDES["lista"]
        _afp, _pes, fc = motor()
        ED = editor()
        if forcar:
            ED.montar_fontes()
            SUBST.clear()
        from nucleo import fontes
        achados = []
        for k in ED._ordem_fontes():
            f = ED.E.fontes[k]
            try:
                if f.tipo == "jogo" and getattr(f, "j", None) is not None:
                    f.j.esperar()          # o índice do jogo carrega em segundo plano; sem esperar, a lista vem vazia
                grupos = fontes.conjuntos(f)
            except Exception:  # noqa: BLE001
                continue
            for g in grupos:
                for o in g["overlays"]:
                    arq = o["arquivo"]
                    if not re.search(r"002\.big$", arq, re.I):
                        continue
                    try:
                        m = fc.abrir(ED._abrir_overlay(f, arq))
                    except Exception:  # noqa: BLE001  (não é molde, ou não abriu)
                        continue
                    nome = o.get("nome") or g.get("nome") or ""
                    achados.append({"fonte": f.id, "fonte_nome": ED._nome_fonte(f), "arquivo": arq,
                                    "nome": nome, "conjunto": g.get("nome") or "", "fundo": m.descricao()["fundo"],
                                    "tipo": getattr(m, "tipo", "lta")})
        # o Generic do jogo primeiro (não depende de mod), depois o Brasileirão do LTA (o mais testado do modelo do
        # LTA) e os de fundo em tela cheia
        achados.sort(key=lambda m: (m["tipo"] != "generic", m["fonte"] != "jogo",
                                    not m["arquivo"].lower().endswith("overlay_35002.big"),
                                    m["fundo"]["w"] * m["fundo"]["h"] < 1920 * 1080, m["arquivo"]))
        MOLDES.update(lista=achados, quando=time.time())
        return achados


def abrir_molde(d):
    _afp, _pes, fc = motor()
    ED = editor()
    m = d.get("molde") or PREFS.ler().get("molde")
    if not m:
        lst = listar_moldes()
        if not lst:
            raise base.ErroUsuario("Não achei nenhum placar do FC que sirva de molde. Confira a pasta do jogo no Editor "
                                   "de Placares (o Generic vem do jogo) ou adicione o pack do LTA como fonte "
                                   "(Arquivo › Fontes).")
        m = lst[0]
    f = ED.fonte(m["fonte"])
    if f.tipo == "jogo" and getattr(f, "j", None) is not None:
        f.j.esperar()
    ov = ED._abrir_overlay(f, m["arquivo"])
    return f, m, ov, fc.abrir(ov)


def alvo_subst(alvo):
    """A substituição do mesmo conjunto de overlays do placar (…N002.big -> …N021.big), ou None."""
    m = re.match(r"^(.*overlay_\d+)002\.big$", alvo or "", re.I)
    return m.group(1) + "021.big" if m else None


def nome_classe(alvo):
    """Nome próprio para a classe de um overlay do Generic gravado em outro arquivo (ex.: overlay_35021_PES)."""
    return re.sub(r"\W+", "_", os.path.splitext(os.path.basename(alvo))[0]).strip("_") + "_PES"


def fonte_jogo(ED):
    f = ED.E.fontes.get("jogo")
    if f is None:
        raise base.ErroUsuario("A substituição usa a do Generic do jogo como molde: confira a pasta do jogo no Editor "
                               "de Placares.")
    if getattr(f, "j", None) is not None:
        f.j.esperar()
    return f


def molde_subst(ED, fc):
    """(fonte do jogo, MoldeSubst do Generic/overlay_9021, simulação dele); a simulação fica guardada."""
    f = fonte_jogo(ED)
    with LOCK:
        if f.id not in SUBST:
            ov = ED._abrir_overlay(f, GENERIC_SUBST)
            SUBST[f.id] = (fc.MoldeSubst(ov), fc.simular(ov, ED.bibliotecas_anim(), ED.valores_tema()))
        molde, sim = SUBST[f.id]
    return f, molde, sim


def placar(pasta):
    _afp, pes, _fc = motor()
    pasta = os.path.abspath(pasta)
    with LOCK:
        pl = PLACARES.get(pasta.lower())
        if pl is None:
            pl = pes.PlacarPes(pasta, cache=os.path.join(CACHE, "texturas"))
            PLACARES[pasta.lower()] = pl
            if len(PLACARES) > 12:
                PLACARES.pop(next(iter(PLACARES)))
        return pl


def png_dados(img):
    b = io.BytesIO()
    img.save(b, "PNG", compress_level=3)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode("ascii")


def _num(d, k, padrao):
    try:
        return float(d.get(k, padrao))
    except (TypeError, ValueError):
        return float(padrao)


# ------------------------------------------------------------------ rotas

def api_inicio(_):
    verificar_motor()
    return {"versao": VERSAO, "motor": MOTOR_OK, "editor": info_editor(), "prefs": PREFS.ler()}


def api_pacote(d):
    _afp, pes, _fc = motor()
    pasta = os.path.abspath((d.get("pasta") or "").strip())
    if not os.path.exists(pasta):
        raise base.ErroUsuario("Pasta não encontrada.")
    achados = pes.achar_placares(pasta) if os.path.isdir(pasta) else [pasta]
    if not achados:
        raise base.ErroUsuario("Não achei placar do PES nessa pasta (procurei common\\menu\\licence\\game2dPes.bin, "
                               "também nas subpastas).")
    PREFS.atualizar(pasta=pasta)
    return {"pasta": pasta, "placares": [{"pasta": p, "nome": os.path.basename(os.path.normpath(p))} for p in achados]}


def api_placar(d):
    pl = placar(d["pasta"])
    img = pl.previa(margem=10)
    campos = {c: [round(v, 1) for v in pl.caixa_campo(c)] for c in
              ("nome_casa", "nome_fora", "gols_casa", "gols_fora", "relogio", "acrescimos") if pl.caixa_campo(c)}
    sp = pl.substituicao()
    sub = None
    if sp:
        im = sp.previa(margem=10)
        sub = {"previa": png_dados(im) if im else None, "w": im.width if im else 0, "h": im.height if im else 0,
               "escudo": bool(sp.caixa_escudo()), "titulo": bool(sp.campo_na_placa("titulo"))}
    return {"pasta": pl.pasta, "nome": pl.nome, "arquivos": [os.path.basename(b) for b in pl.bins],
            "filmes": [n for _, n in pl.bib.filmes()], "campos": campos,
            "previa": png_dados(img) if img else None, "w": img.width if img else 0, "h": img.height if img else 0,
            "subst": sub}


def api_moldes(d):
    try:
        return {"moldes": listar_moldes(bool(d.get("atualizar"))), "atual": PREFS.ler().get("molde")}
    except base.ErroUsuario:
        raise
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        raise base.ErroUsuario(f"Não consegui ler os placares do FC: {ex}")


def _matriz(d, pl, fc):
    p = PREFS.ler()
    x, y, esc = _num(d, "x", p.get("x")), _num(d, "y", p.get("y")), _num(d, "escala", p.get("escala"))
    esc = max(0.3, min(3.0, esc))
    return fc.posicionar(pl, x, y, esc), {"x": x, "y": y, "escala": esc}


def _usar_fonte(d, pl):
    """(ttf, avanços) dos números do PES, se pedido (padrão) e se o pacote tiver os números."""
    if d.get("fonte_pes", PREFS.ler().get("fonte_pes", True)) is False:
        return None
    return pl.fonte_numeros()


def face_numeros(pl):
    nome = re.sub(r"[^A-Za-z0-9]+", "-", pl.nome).strip("-")[:40] or "Placar"
    return "PES-" + nome + "-Numeros", "FONT_NAME_PES_" + re.sub(r"[^A-Z0-9]+", "_", nome.upper()).strip("_")


def api_previa(d):
    _afp, _pes, fc = motor()
    pl = placar(d["pasta"])
    _f, m, _ov, molde = abrir_molde(d)
    S, pos = _matriz(d, pl, fc)
    num = _usar_fonte(d, pl)
    ttf = num[0] if num else None
    img = fc.previa(pl, molde, S, recorte=False, ttf_numeros=ttf)
    tela = img.resize((960, 540))
    sp = pl.substituicao()
    return {"tela": png_dados(tela), "recorte": png_dados(fc.previa(pl, molde, S, ttf_numeros=ttf)), "molde": m,
            "pos": pos, "fundo": molde.descricao()["fundo"], "subst": png_dados(fc.previa_subst(sp)) if sp else None}


def api_telas(d):
    """Todas as telas do pacote (placar, substituição, escalação…) em miniatura."""
    _afp, pes, _fc = motor()
    from PIL import Image
    pl = placar(d["pasta"])
    out = []
    for _pk, nome in pl.bib.filmes():
        img = pes.desenhar_tela(pl.bib, nome)
        if img is None:
            continue
        mini = img.copy()
        mini.thumbnail((520, 300), Image.LANCZOS)
        out.append({"nome": nome, "titulo": pes.TELAS.get(nome, nome), "w": img.width, "h": img.height,
                    "imagem": png_dados(mini)})
    return {"telas": out}


def api_exportar(d):
    """Grava em exportados/<placar>: cada tela inteira e cada recorte das texturas, em PNG (para usar no Editor de
    Placares em Trocar… ou num editor de imagem)."""
    _afp, pes, _fc = motor()
    pl = placar(d["pasta"])
    pasta = os.path.join(AQUI, "exportados", re.sub(r'[<>:"/\\|?*]+', "_", pl.nome))
    os.makedirs(os.path.join(pasta, "telas"), exist_ok=True)
    os.makedirs(os.path.join(pasta, "recortes"), exist_ok=True)
    n_telas = n_rec = 0
    for _pk, nome in pl.bib.filmes():
        img = pes.desenhar_tela(pl.bib, nome)
        if img is not None:
            img.save(os.path.join(pasta, "telas", "%s - %s.png" % (nome, pes.TELAS.get(nome, nome))))
            n_telas += 1
    for pk in pl.bib.pacotes:
        for r in pk.regioes:
            if r["x1"] - r["x0"] < 2 or r["y1"] - r["y0"] < 2:
                continue
            img = pk.recorte(r["nome"])
            if img is not None:
                img.save(os.path.join(pasta, "recortes", re.sub(r'[<>:"/\\|?*]+', "_", r["nome"]) + ".png"))
                n_rec += 1
    num = pl.fonte_numeros()
    if num:
        face, _chave = face_numeros(pl)
        with open(os.path.join(pasta, face + ".ttf"), "wb") as fh:
            fh.write(num[0])
    base.abrir_no_explorer(pasta)
    return {"pasta": pasta, "telas": n_telas, "recortes": n_rec}


def api_fonte_png(d):
    """Os números do PES escritos com a fonte gerada (para conferir) e o .ttf salvo onde o usuário quiser."""
    from PIL import Image, ImageDraw, ImageFont
    pl = placar(d["pasta"])
    num = pl.fonte_numeros()
    if not num:
        return {"tem": False}
    f = ImageFont.truetype(io.BytesIO(num[0]), 44)
    img = Image.new("RGBA", (330, 60), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((6, 52), "0123456789 45:00 +3", font=f, fill=(235, 238, 244, 255), anchor="ls")
    face, _chave = face_numeros(pl)
    if d.get("salvar"):
        destino = base.dialogo("salvar", "Salvar a fonte dos números do PES", None, [("Fonte TrueType", "*.ttf")],
                               nome=face + ".ttf", extensao="ttf")
        if destino:
            with open(destino, "wb") as fh:
                fh.write(num[0])
            return {"tem": True, "salvo": destino}
    return {"tem": True, "imagem": png_dados(img), "face": face}


def api_converter(d):
    _afp, _pes, fc = motor()
    from nucleo import projetos
    ED = editor()
    pl = placar(d["pasta"])
    f, m, ov, molde = abrir_molde(d)
    S, pos = _matriz(d, pl, fc)
    sai = ED.saida_atual()["caminho"]
    if not sai:
        raise base.ErroUsuario("O Editor de Placares ainda não tem pasta de saída: abra o Editor de Placares e escolha em "
                               "Arquivo › Pasta de saída (o padrão é a mods\\legacy do Live Editor).")
    modo = d.get("alvo") or "molde"
    alvo = {"molde": m["arquivo"], "generic": GENERIC}.get(modo) or (d.get("alvo_outro") or "").strip()
    alvo = alvo.replace("\\", "/").strip("/")
    if not re.match(r"^data/ui/.+\.big$", alvo, re.I):
        raise base.ErroUsuario("O destino precisa ser um caminho data/ui/…/….big (por exemplo "
                               "data/ui/game/overlays/overlay_35002.big).")
    sim = fc.simular(ov, ED.bibliotecas_anim(), ED.valores_tema())
    num = _usar_fonte(d, pl)
    numeros = None
    if num:
        # a fonte vai para data/ui/fonts da saída, com família no FIFA.xml (o mesmo que "Importar fonte" do editor)
        from nucleo import tema
        face, chave = face_numeros(pl)
        tema.definir(sai, ED.ler_efetivo, chave, face, ttf=num[0], nome_ttf=face + ".ttf")
        ED._depois_tema()
        numeros = {"face": face, "chave": tema.limpar_chave(chave), "avancos": num[1]}
    ops, resumo = fc.converter(pl, molde, S, sim["constantes"], numeros, sim["textos"])
    if getattr(molde, "tipo", "") == "generic" and alvo.lower() != m["arquivo"].lower():
        # o código do Generic mudou: em outro arquivo, a classe precisa de nome próprio (ver fc.ops_renomear_classe)
        ren = fc.ops_renomear_classe(ov, nome_classe(alvo))
        if ren:
            ops.update(ren)
            resumo.append("A classe do código ganhou nome próprio (%s), para não se misturar com a do Generic, que "
                          "as outras competições usam." % nome_classe(alvo))
    novo = ED._abrir_overlay(f, m["arquivo"])
    lst = list(ops.values())
    novo.aplicar(lst, ED._imagens_das_ops(lst))
    destino = projetos.gravar_saida(sai, alvo, novo.bytes(), ED.desc_fonte(f), m["arquivo"], ops)
    sub = None
    if d.get("subst", True) is not False and pl.substituicao():
        sub = converter_subst(pl, alvo, ED, sai)
    if "saida" in ED.E.fontes:
        ED.E.fontes["saida"].atualizar()
    PREFS.atualizar(molde=m, alvo=modo, alvo_outro=d.get("alvo_outro") or "",
                    fonte_pes=d.get("fonte_pes", True) is not False, subst=d.get("subst", True) is not False, **pos)
    return {"destino": destino, "alvo": alvo, "resumo": resumo, "operacoes": len(ops), "molde": m,
            "bytes": os.path.getsize(destino), "subst": sub}


def converter_subst(pl, alvo_placar, ED, sai):
    """Grava a substituição do pacote na substituição do mesmo conjunto do placar, com a do Generic do jogo como
    molde. Devolve {destino, alvo, resumo, operacoes, bytes} ou {erro} (o placar já foi gravado: um erro aqui não
    desfaz o placar)."""
    _afp, _pes, fc = motor()
    from nucleo import projetos
    alvo = alvo_subst(alvo_placar)
    if not alvo:
        return {"erro": "Não sei qual é a substituição do destino %s (o conversor acha a do mesmo conjunto trocando "
                        "…002.big por …021.big). Use o destino do molde ou o Generic." % alvo_placar}
    try:
        f, molde, sim = molde_subst(ED, fc)
        ops, resumo = fc.converter_subst(pl.substituicao(), molde, None, sim["constantes"], sim["formatos"])
        if alvo.lower() != GENERIC_SUBST.lower():
            ren = fc.ops_renomear_classe(molde.ov, nome_classe(alvo))
            if ren:
                ops.update(ren)
                resumo.append("A classe do código ganhou nome próprio (%s), para não se misturar com a do Generic, "
                              "que as outras competições usam." % nome_classe(alvo))
        novo = ED._abrir_overlay(f, GENERIC_SUBST)
        lst = list(ops.values())
        novo.aplicar(lst, ED._imagens_das_ops(lst))
        destino = projetos.gravar_saida(sai, alvo, novo.bytes(), ED.desc_fonte(f), GENERIC_SUBST, ops)
    except base.ErroUsuario as ex:
        return {"erro": str(ex), "alvo": alvo}
    except Exception as ex:  # noqa: BLE001  (o placar já está gravado: a substituição só avisa)
        traceback.print_exc()
        return {"erro": f"Não consegui converter a substituição: {ex}", "alvo": alvo}
    return {"destino": destino, "alvo": alvo, "resumo": resumo, "operacoes": len(ops),
            "bytes": os.path.getsize(destino)}


def api_abrir(d):
    base.abrir_no_explorer(d["caminho"], selecionar=os.path.isfile(d["caminho"]))
    return {"ok": True}


def api_dialogo(d):
    modo = d.get("modo") or "pasta"
    inicial = d.get("inicial") or PREFS.ler().get("pasta") or None
    if modo == "arquivo":
        p = base.dialogo("abrir", "Escolha o game2dPes.bin do placar", inicial, [("Placar do PES", "*.bin"), ("Todos", "*.*")])
    else:
        p = base.dialogo("pasta", "Escolha a pasta do placar do PES (ou do pacote com vários)", inicial)
    return {"caminho": p}


def main():
    ap = argparse.ArgumentParser(description="Conversor de Placares PES → FC")
    ap.add_argument("--porta", type=int, default=8781)
    ap.add_argument("--sem-janela", action="store_true")
    ap.add_argument("--editor", help="pasta de outra cópia do Editor de Placares (testes)")
    ap.add_argument("pasta", nargs="?")
    a = ap.parse_args()
    if a.pasta:
        PREFS.atualizar(pasta=os.path.abspath(a.pasta))
    threading.Thread(target=verificar_motor, daemon=True).start()
    comp_get, comp_post = base.rotas_componentes(GRUPO, ao_concluir=verificar_motor)
    get = {"inicio": api_inicio, **comp_get}
    post = {"pacote": api_pacote, "placar": api_placar, "moldes": api_moldes, "previa": api_previa,
            "converter": api_converter, "fonte_png": api_fonte_png, "telas": api_telas, "exportar": api_exportar,
            "abrir": api_abrir, "dialogo": api_dialogo,
            **comp_post}
    h = base.criar_handler(os.path.join(AQUI, "web"), get, post, nome="ConversorPlacaresPES")
    base.servir(h, a.porta, "Conversor de Placares PES → FC", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
