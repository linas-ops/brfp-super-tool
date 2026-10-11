"""Editor de Placares EA FC — servidor local.

    python servidor.py [--porta 8766] [--sem-janela]

Abre a interface no navegador (janela de aplicativo do Edge/Chrome quando disponível). Só aceita conexões desta
máquina (127.0.0.1). Lê os placares do FC 26 instalado, de mods .fifamod e de pastas; grava os arquivos editados
na pasta de saída (por padrão a pasta mods/legacy do Live Editor, que o jogo carrega com o Live Editor ligado).
"""
import argparse
import base64
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from nucleo import apt, as2, big, fontes, jogo, projetos, tema  # noqa: E402

WEB = os.path.join(AQUI, "web")
PREFS = os.path.join(AQUI, "preferencias.json")
EXPORTADOS = os.path.join(AQUI, "exportados")
VERSAO = "2.1"
# classes do jogo que os placares usam e que ficam em outros arquivos (carregadas para simular as animações)
BIBLIOTECAS = (("data/ui/artAssets/tacticAnimations/Tactic10.big", ("StyleManager",)),
               ("data/ui/game/components/pitches/PitchAnalysis.big", ("AnimationManager",)))
OPS_SIMULACAO = ("place", "texto", "const", "const_txt", "fonte_char")
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
        ".ttf": "font/ttf", ".otf": "font/otf", ".woff2": "font/woff2"}


class ErroEditor(Exception):
    pass


# ------------------------------------------------------------------ estado

class Estado:
    def __init__(self):
        self.lock = threading.RLock()
        self.fontes = {}            # id -> Fonte
        self.sessoes = {}           # id -> dict(overlay, fonte, arquivo, ...)
        self.contador = itertools.count(1)
        self.cache_fontes_ttf = {}
        self.bibliotecas = None     # (ordem das fontes, [(apt, consts, nomes)])
        self.valores_tema = None    # (sha do FIFA.xml em uso, {ALPHA_FULL: 100, ...})

    def prefs(self):
        try:
            with open(PREFS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def salvar_prefs(self, p):
        with open(PREFS + ".tmp", "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=1)
        os.replace(PREFS + ".tmp", PREFS)


E = Estado()


def jogo_atual():
    p = E.prefs()
    j = jogo.obter(p.get("jogo_pasta"))
    if j:
        j.iniciar()
    return j


def oodle():
    j = jogo_atual()
    if not j:
        return None
    if j.oodle is None:
        try:
            j.oodle = jogo.Oodle(j.pasta)
        except jogo.ErroJogo:
            return None
    return j.oodle


def montar_fontes():
    """Recria a lista de fontes a partir das preferências (jogo + mods + pastas)."""
    p = E.prefs()
    novas = {}
    j = jogo_atual()
    if j:
        novas["jogo"] = E.fontes.get("jogo") if isinstance(E.fontes.get("jogo"), fontes.FonteJogo) and E.fontes["jogo"].j is j \
            else fontes.FonteJogo(j)
    for item in p.get("fontes", []):
        ident = id_fonte(item["tipo"], item["caminho"])
        try:
            if item["tipo"] == "mod" and os.path.isfile(item["caminho"]):
                ant = E.fontes.get(ident)
                novas[ident] = ant if isinstance(ant, fontes.FonteMod) and ant.caminho == os.path.abspath(item["caminho"]) \
                    else fontes.FonteMod(ident, item["caminho"], oodle)
            elif item["tipo"] == "pasta" and os.path.isdir(item["caminho"]):
                novas[ident] = fontes.FontePasta(ident, item["caminho"], item.get("nome"))
        except (jogo.ErroJogo, OSError) as ex:
            print("Fonte ignorada:", item.get("caminho"), ex)
    sai = saida_atual()
    if sai["caminho"] and os.path.isdir(sai["caminho"]):
        novas["saida"] = fontes.FontePasta("saida", sai["caminho"], "Saída: " + sai["nome"])
    E.fontes = novas
    return novas


def id_fonte(tipo, caminho):
    return tipo + ":" + hashlib.sha1(os.path.abspath(caminho).lower().encode("utf-8")).hexdigest()[:10]


def desc_fonte(f):
    return {"id": f.id, "tipo": f.tipo, "nome": f.nome,
            "caminho": f.caminho if isinstance(f, fontes.FonteMod) else getattr(f, "raiz", None)}


def saida_atual():
    p = E.prefs()
    le_dados, _ = jogo.detectar_live_editor()
    padrao = os.path.join(le_dados, "mods", "legacy") if le_dados else None
    caminho = p.get("saida") or padrao
    nome = "Live Editor (mods\\legacy)" if caminho and padrao and os.path.abspath(caminho).lower() == os.path.abspath(padrao).lower() \
        else (os.path.basename(caminho.rstrip("\\/")) if caminho else "")
    return {"caminho": os.path.abspath(caminho) if caminho else None, "nome": nome, "padrao_le": padrao,
            "eh_le": bool(caminho and padrao and os.path.abspath(caminho).lower() == os.path.abspath(padrao).lower())}


def fonte(ident):
    f = E.fontes.get(ident) or montar_fontes().get(ident)
    if f is None:
        raise ErroEditor("Fonte não encontrada (foi removida?).")
    return f


def sessao(ident):
    s = E.sessoes.get(str(ident))
    if s is None:
        raise ErroEditor("Este arquivo não está mais aberto. Abra de novo.")
    return s


def _ordem_fontes(incluir_saida=False):
    """A ordem em que o jogo veria um arquivo: a saída (Live Editor) por cima, depois os mods, as pastas e o jogo."""
    ordem = (["saida"] if incluir_saida else []) + [k for k in E.fontes if k.startswith("mod:")] + \
        [k for k in E.fontes if k.startswith("pasta:")] + ["jogo"]
    return [k for k in ordem if k in E.fontes]


def _nome_fonte(f):
    if f.id == "jogo":
        return "FC 26 (jogo)"
    if f.id == "saida":
        return "Pasta de saída"
    return ("Mod: " if f.tipo == "mod" else "Pasta: ") + f.nome


def ler_efetivo(rel, incluir_saida=False):
    """(nome da fonte, bytes) da versão de 'rel' que vale, ou (None, None)."""
    for k in _ordem_fontes(incluir_saida):
        f = E.fontes[k]
        try:
            if f.existe(rel):
                return _nome_fonte(f), f.ler(rel)
        except (jogo.ErroJogo, OSError):
            continue
    return None, None


def _json_seguro(v, nivel=0):
    """Resultado da simulação -> JSON válido (sem NaN, sem objetos internos)."""
    if nivel > 40:
        return None
    if isinstance(v, dict):
        return {str(k): _json_seguro(x, nivel + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_seguro(x, nivel + 1) for x in v]
    if v is None or isinstance(v, (bool, str, int)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    return None


# ------------------------------------------------------------------ rotas

def api_versao(_):
    return {"versao": VERSAO}


def api_inicio(_):
    montar_fontes()
    j = jogo_atual()
    le_dados, le_prog = jogo.detectar_live_editor()
    return {"versao": VERSAO, "jogo": j.info() if j else {"estado": "indisponivel", "pasta": E.prefs().get("jogo_pasta")},
            "live_editor": {"dados": le_dados, "programa": le_prog}, "saida": saida_atual(),
            "fontes": [f.info() for f in E.fontes.values()],
            "editados": projetos.listar(saida_atual()["caminho"])}


def api_jogo_config(d):
    p = E.prefs()
    v = (d.get("pasta") or "").strip()
    if v:
        if not jogo.pasta_valida(v):
            raise ErroEditor("Essa pasta não parece ser a do FC 26 (precisa ter oo2core_9_win64.dll e Data\\layout.toc).")
        p["jogo_pasta"] = os.path.abspath(v)
    else:
        p.pop("jogo_pasta", None)
    E.salvar_prefs(p)
    return api_inicio({})


def api_fonte_adicionar(d):
    tipo, caminho = d["tipo"], os.path.abspath(d["caminho"])
    if tipo == "mod":
        fontes.FonteMod("teste", caminho, oodle)      # valida antes de guardar
    elif tipo == "pasta":
        if not os.path.isdir(caminho):
            raise ErroEditor("Pasta não encontrada.")
        if not os.path.isdir(os.path.join(caminho, "data")) and not os.path.isdir(os.path.join(caminho, "Data")):
            achou = [x for x in ("legacy", os.path.join("mods", "legacy")) if os.path.isdir(os.path.join(caminho, x, "data"))]
            if achou:
                caminho = os.path.join(caminho, achou[0])
            else:
                raise ErroEditor("Essa pasta não tem a árvore data\\ui\\... dos arquivos legacy.")
    else:
        raise ErroEditor("Tipo de fonte inválido.")
    p = E.prefs()
    lst = [x for x in p.get("fontes", []) if os.path.abspath(x["caminho"]).lower() != caminho.lower()]
    lst.append({"tipo": tipo, "caminho": caminho})
    p["fontes"] = lst
    E.salvar_prefs(p)
    return api_inicio({})


def api_fonte_remover(d):
    p = E.prefs()
    p["fontes"] = [x for x in p.get("fontes", []) if id_fonte(x["tipo"], x["caminho"]) != d["id"]]
    E.salvar_prefs(p)
    return api_inicio({})


def api_saida(d):
    p = E.prefs()
    caminho = (d.get("caminho") or "").strip()
    if caminho:
        os.makedirs(caminho, exist_ok=True)
        p["saida"] = os.path.abspath(caminho)
    else:
        p.pop("saida", None)
    E.salvar_prefs(p)
    return api_inicio({})


def api_dialogo(d):
    modo = d.get("modo", "pasta")
    inicial = d.get("inicial") or os.path.expanduser("~")
    D = _dialogos()
    if modo == "mod":
        p = D.escolher("abrir", "Escolha um mod do FIFA Editor Tool", inicial, [("Mod do FET", "*.fifamod"), ("Todos", "*.*")])
    elif modo == "imagem":
        p = D.escolher("abrir", "Escolha uma imagem", inicial, [("Imagens", "*.png;*.jpg;*.jpeg;*.bmp;*.webp"), ("Todos", "*.*")])
    elif modo == "fonte":
        p = D.escolher("abrir", "Escolha uma fonte", inicial, [("Fontes TrueType/OpenType", "*.ttf;*.otf"), ("Todos", "*.*")])
    else:
        p = D.escolher("pasta", d.get("titulo") or "Escolha uma pasta", inicial)
    return {"caminho": os.path.abspath(p) if p else None}


def _dialogos():
    """Diálogos nativos do Windows do BRFP Super Tool (comum/dialogos.py; o Python embutido não tem tkinter)."""
    comum = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum")
    if comum not in sys.path:
        sys.path.append(comum)
    import dialogos
    return dialogos


def api_conjuntos(d):
    f = fonte(d["fonte"])
    if isinstance(f, fontes.FontePasta):
        f.atualizar()
    grupos = fontes.conjuntos(f)
    sai = saida_atual()["caminho"]
    editados = {p["alvo"].lower() for p in projetos.listar(sai)} if sai else set()
    for g in grupos:
        for o in g["overlays"] + g["componentes"]:
            o["editado"] = o["arquivo"].lower() in editados
    return {"fonte": f.info(), "conjuntos": grupos}


def _abrir_overlay(f, arquivo):
    dados = f.ler(arquivo)
    itens, marca = big.ler(dados)
    return apt.Overlay(itens, marca)


def api_abrir(d):
    f = fonte(d["fonte"])
    arquivo = d["arquivo"]
    alvo = d.get("alvo") or arquivo
    sai = saida_atual()["caminho"]
    proj = projetos.carregar(sai, alvo) if sai else None
    usar_proj = proj and d.get("continuar", True) and proj.get("fonte", {}).get("id") == f.id and \
        proj.get("arquivo", "").lower() == arquivo.lower()
    ov = _abrir_overlay(f, arquivo)
    sid = str(next(E.contador))
    with E.lock:
        E.sessoes[sid] = {"overlay": ov, "fonte": f.id, "arquivo": arquivo, "alvo": alvo, "leitura": False}
        _limpar_sessoes()
    return {"sessao": sid, "arquivo": arquivo, "alvo": alvo, "fonte": f.info(), "modelo": ov.modelo(),
            "ops": (proj or {}).get("ops", {}) if usar_proj else {}, "projeto": bool(usar_proj),
            "projeto_outro": bool(proj and not usar_proj), "saida": sai,
            "destino": projetos.caminho_saida(sai, alvo) if sai else None}


def _limpar_sessoes():
    if len(E.sessoes) > 60:
        for k in sorted(E.sessoes, key=int)[:-40]:
            E.sessoes.pop(k, None)


def _caminho_import(filme):
    """'game/globalComponents/x/y' -> 'data/ui/game/globalComponents/x/y.big'."""
    rel = filme.replace("\\", "/").strip("/")
    if not rel.lower().startswith("data/"):
        rel = "data/ui/" + rel
    if not rel.lower().endswith(".big"):
        rel += ".big"
    return rel


def api_componente(d):
    """Abre (só leitura) o filme de onde um overlay importa um símbolo, procurando na mesma fonte, na saída,
    nos mods e no jogo — a ordem em que o jogo veria os arquivos com os mods instalados."""
    s = sessao(d["sessao"])
    rel = _caminho_import(d["filme"])
    ordem = [s["fonte"], "saida"] + [k for k in E.fontes if k.startswith("mod:")] + \
        [k for k in E.fontes if k.startswith("pasta:")] + ["jogo"]
    vistos = set()
    for k in ordem:
        if k in vistos or k not in E.fontes:
            continue
        vistos.add(k)
        f = E.fontes[k]
        try:
            if not f.existe(rel):
                continue
            ov = _abrir_overlay(f, rel)
        except (jogo.ErroJogo, big.ErroBig, apt.ErroApt, OSError):
            continue
        sid = str(next(E.contador))
        with E.lock:
            E.sessoes[sid] = {"overlay": ov, "fonte": k, "arquivo": rel, "alvo": rel, "leitura": True}
        return {"sessao": sid, "arquivo": rel, "fonte": f.info(), "modelo": ov.modelo()}
    return {"sessao": None, "arquivo": rel}


def api_imagem_enviar(d):
    w, h = int(d["w"]), int(d["h"])
    if not (1 <= w <= 8192 and 1 <= h <= 8192):
        raise ErroEditor("Imagem grande demais (máximo 8192 px).")
    rgba = base64.b64decode(d["rgba"])
    return {"id": projetos.salvar_imagem(w, h, rgba), "w": w, "h": h}


def _imagens_das_ops(ops):
    imgs = {}
    for op in ops:
        if op.get("op") == "textura":
            imgs[op["img"]] = projetos.ler_imagem(op["img"])
    return imgs


def api_salvar(d):
    s = sessao(d["sessao"])
    if s["leitura"]:
        raise ErroEditor("Este arquivo foi aberto só para consulta.")
    sai = saida_atual()["caminho"]
    if not sai:
        raise ErroEditor("Escolha a pasta de saída (Arquivo › Pasta de saída).")
    alvo = (d.get("alvo") or s["alvo"]).replace("\\", "/")
    if not re.match(r"^data/ui/.+\.big$", alvo, re.I):
        raise ErroEditor("O destino precisa ser um caminho data/ui/....big")
    ops_dic = d.get("ops") or {}
    ops = list(ops_dic.values())
    f = fonte(s["fonte"])
    ov = _abrir_overlay(f, s["arquivo"])      # sempre a partir do original: as operações são o estado completo
    ov.aplicar(ops, _imagens_das_ops(ops))
    destino = projetos.gravar_saida(sai, alvo, ov.bytes(), desc_fonte(f), s["arquivo"], ops_dic)
    s["alvo"] = alvo
    if "saida" in E.fontes:
        E.fontes["saida"].atualizar()
    return {"destino": destino, "alvo": alvo, "bytes": os.path.getsize(destino)}


def api_descartar(d):
    sai = saida_atual()["caminho"]
    alvo = d["alvo"]
    restaurado = projetos.descartar(sai, alvo)
    if "saida" in E.fontes:
        E.fontes["saida"].atualizar()
    return {"restaurado": restaurado, "editados": projetos.listar(sai)}


def api_editados(_):
    return {"editados": projetos.listar(saida_atual()["caminho"])}


def api_exportar_png(d):
    nome = re.sub(r"[^\w\-. ]+", "_", d.get("nome") or "textura")[:120]
    # pasta (opcional): subpastas de exportados\ para "Exportar todas" ("placar_imagens/componentes/x")
    partes = [re.sub(r"[^\w\-. ]+", "_", x).strip(" .")[:80] for x in str(d.get("pasta") or "").replace("\\", "/").split("/")]
    destino = os.path.join(EXPORTADOS, *[x for x in partes if x and x not in (".", "..")])
    os.makedirs(destino, exist_ok=True)
    caminho = os.path.join(destino, nome if nome.lower().endswith(".png") else nome + ".png")
    with open(caminho, "wb") as f:
        f.write(base64.b64decode(d["png"]))
    if d.get("mostrar", True):
        _explorer(caminho)
    return {"caminho": caminho, "pasta": destino}


def _explorer(caminho):
    if os.name == "nt":
        if os.path.isdir(caminho):
            subprocess.Popen(["explorer", caminho])
        else:
            subprocess.Popen(["explorer", "/select,", caminho])


def api_explorer(d):
    caminho = d.get("caminho")
    if not caminho or not os.path.exists(caminho):
        alvo = os.path.dirname(caminho or "")
        if alvo and os.path.isdir(alvo):
            caminho = alvo
        else:
            raise ErroEditor("Arquivo não encontrado.")
    _explorer(caminho)
    return {"ok": True}


def api_ler_imagem_local(d):
    """Lê um arquivo de imagem do disco (escolhido no diálogo) e devolve em base64 para o navegador decodificar."""
    caminho = d["caminho"]
    if os.path.getsize(caminho) > 64 << 20:
        raise ErroEditor("Imagem grande demais.")
    with open(caminho, "rb") as f:
        return {"nome": os.path.basename(caminho), "dados": base64.b64encode(f.read()).decode("ascii")}


# ------------------------------------------------------------------ animação (simulação do ActionScript)

def bibliotecas_anim():
    """AnimationManager e StyleManager do jogo (ou de um mod que os substitua), lidos uma vez."""
    chave = tuple(_ordem_fontes())
    if E.bibliotecas and E.bibliotecas[0] == chave:
        return E.bibliotecas[1]
    out = []
    for rel, nomes in BIBLIOTECAS:
        _origem, dados = ler_efetivo(rel)
        if dados is None:
            continue
        try:
            it = dict(big.ler(dados)[0])
            out.append((it["0"], it["1"], nomes))
        except (big.ErroBig, KeyError):
            continue
    if out:
        E.bibliotecas = (chave, out)
    return out


def valores_tema():
    """Valores do FIFA.xml em uso (saída, mods, jogo) que o StyleManager devolve ao código dos placares."""
    _origem, dados = ler_efetivo(tema.XML, incluir_saida=True)
    if dados is None:
        return {}
    sha = tema._sha(dados)
    if not E.valores_tema or E.valores_tema[0] != sha:
        E.valores_tema = (sha, tema.valores(tema._texto(dados)[0]))
    return E.valores_tema[1]


def api_animacao(d):
    """Roda a classe do placar (com as alterações) e devolve a linha do tempo das animações, as constantes e os
    formatos de texto que o código usa."""
    s = sessao(d["sessao"])
    f = fonte(s["fonte"])
    ov = _abrir_overlay(f, s["arquivo"])
    ops = [op for op in (d.get("ops") or {}).values() if isinstance(op, dict) and op.get("op") in OPS_SIMULACAO]
    avisos = []
    if ops:
        try:
            ov.aplicar(ops)
        except (apt.ErroApt, as2.ErroAS, ValueError, KeyError, IndexError) as ex:
            avisos.append(f"Alterações não aplicadas na prévia: {ex}")
    metodos = tuple(m for m in (d.get("metodos") or ["AnimateIn"]) if isinstance(m, str))[:4] or ("AnimateIn",)
    bibs = bibliotecas_anim()
    try:
        r = as2.simular(ov, metodos, bibliotecas=bibs, tema=valores_tema())
    except Exception as ex:  # o simulador é aproximado: a interface mostra o erro e segue sem a prévia
        traceback.print_exc()
        r = {"metodos": [], "tweens": [], "eventos": [], "inicial": [], "constantes": [], "formatos": [], "textos": {},
             "erros": [f"{type(ex).__name__}: {ex}"], "duracao": 0, "fps": 30, "curvas": {}, "curvas_nomes": {}}
    r["erros"] = avisos + list(r.get("erros") or [])
    r["bibliotecas"] = len(bibs)
    r["pedidos"] = list(metodos)
    return _json_seguro(r)


# ------------------------------------------------------------------ fontes do tema (FIFA.xml + data/ui/fonts)

def _faces_disponiveis():
    """{face em minúsculas: {face, origem}} dos TTF/OTF em data/ui/fonts (saída, mods, pastas e jogo)."""
    faces = {}
    for k in _ordem_fontes(incluir_saida=True):
        f = E.fontes[k]
        try:
            lst = f.lista(tema.PASTA_FONTES)
        except (jogo.ErroJogo, OSError):
            continue
        for n in lst:
            resto = n[len(tema.PASTA_FONTES):]
            base, ext = os.path.splitext(resto)
            if "/" in resto or ext.lower() not in (".ttf", ".otf"):
                continue          # subpastas (Japanese/...) são as versões por idioma
            faces.setdefault(base.lower(), {"face": base, "origem": _nome_fonte(f)})
    return faces


def _saida_obrigatoria():
    sai = saida_atual()["caminho"]
    if not sai:
        raise ErroEditor("Escolha a pasta de saída (Arquivo › Pasta de saída).")
    os.makedirs(sai, exist_ok=True)
    return sai


def _depois_tema():
    E.cache_fontes_ttf.clear()
    montar_fontes()
    if "saida" in E.fontes:
        E.fontes["saida"].atualizar()


def api_fontes_tema(_d):
    montar_fontes()
    sai = saida_atual()["caminho"]
    origem_xml, dados = ler_efetivo(tema.XML, incluir_saida=True)
    fams = tema.familias(tema._texto(dados)[0]) if dados else []
    faces = _faces_disponiveis()
    proj = tema.carregar(sai) if sai else {"familias": []}
    minhas = {x["chave"]: x["face"] for x in proj.get("familias", [])}
    desatualizado = False
    base = proj.get("base") or {}
    if minhas and base.get("xml_sha") and not (proj.get("backups") or {}).get(tema.XML):
        _o, base_atual = ler_efetivo(tema.XML)
        desatualizado = base_atual is not None and tema._sha(base_atual) != base["xml_sha"]
    return {"familias": [{"chave": k, "face": v, "ttf": v.lower() in faces, "minha": k in minhas} for k, v in fams],
            "faces": sorted((x["face"] for x in faces.values()), key=str.lower),
            "faces_origem": {x["face"]: x["origem"] for x in faces.values()},
            "xml_origem": origem_xml, "base": base, "minhas": proj.get("familias", []),
            "desatualizado": desatualizado, "saida": saida_atual(),
            "mods": [x.nome for k, x in E.fontes.items() if k.startswith("mod:")]}


def api_fonte_importar(d):
    sai = _saida_obrigatoria()
    caminho = d["caminho"]
    if os.path.getsize(caminho) > 40 << 20:
        raise ErroEditor("Fonte grande demais.")
    with open(caminho, "rb") as fh:
        dados = fh.read()
    tema.validar_ttf(dados)
    face = tema.limpar_face(d.get("face") or os.path.splitext(os.path.basename(caminho))[0])
    if not face:
        raise ErroEditor("Dê um nome à fonte (letras, números, - e _).")
    existente = _faces_disponiveis().get(face.lower())
    if existente and existente["origem"] != "Pasta de saída" and not d.get("substituir"):
        raise ErroEditor(f"Já existe uma fonte \"{face}\" ({existente['origem']}). Escolha outro nome para não substituir a do jogo.")
    tema.definir(sai, ler_efetivo, d.get("chave") or face, face, ttf=dados, nome_ttf=caminho)
    _depois_tema()
    return api_fontes_tema({})


def api_fonte_tema_definir(d):
    sai = _saida_obrigatoria()
    face = d["face"]
    if face.lower() not in _faces_disponiveis():
        raise ErroEditor(f"Não achei o arquivo da fonte \"{face}\" em data/ui/fonts.")
    tema.definir(sai, ler_efetivo, d["chave"], face)
    _depois_tema()
    return api_fontes_tema({})


def api_fonte_tema_remover(d):
    sai = _saida_obrigatoria()
    tema.remover(sai, ler_efetivo, d["chave"])
    _depois_tema()
    return api_fontes_tema({})


def api_fonte_tema_atualizar(_d):
    sai = _saida_obrigatoria()
    tema.regenerar(sai, ler_efetivo)
    _depois_tema()
    return api_fontes_tema({})


ROTAS = {"versao": api_versao, "inicio": api_inicio, "jogo_config": api_jogo_config, "fonte_adicionar": api_fonte_adicionar,
         "fonte_remover": api_fonte_remover, "saida": api_saida, "dialogo": api_dialogo, "conjuntos": api_conjuntos,
         "abrir": api_abrir, "componente": api_componente, "imagem_enviar": api_imagem_enviar, "salvar": api_salvar,
         "descartar": api_descartar, "editados": api_editados, "exportar_png": api_exportar_png,
         "explorer": api_explorer, "ler_imagem_local": api_ler_imagem_local, "animacao": api_animacao,
         "fontes_tema": api_fontes_tema, "fonte_importar": api_fonte_importar,
         "fonte_tema_definir": api_fonte_tema_definir, "fonte_tema_remover": api_fonte_tema_remover,
         "fonte_tema_atualizar": api_fonte_tema_atualizar}


# ------------------------------------------------------------------ binários (GET)

def get_entrada(q):
    s = sessao(q["sessao"][0])
    d = s["overlay"].entrada(q["ent"][0])
    if d is None:
        raise ErroEditor("Entrada não encontrada")
    return d, "application/octet-stream"


def get_imagem(q):
    w, h, rgba = projetos.ler_imagem(q["id"][0])
    return projetos.png(w, h, rgba), "image/png"


def get_fonte_ttf(q):
    nome = q["nome"][0]
    if nome in E.cache_fontes_ttf:
        r = E.cache_fontes_ttf[nome]
        if r is None:
            raise ErroEditor("Fonte não encontrada")
        return r, "font/ttf"
    cands = []
    for n in {nome, nome.replace("_", "-"), nome.replace("-", "_"), nome.replace(" ", "")}:
        for ext in (".ttf", ".TTF", ".otf"):
            cands.append(f"data/ui/fonts/{n}{ext}")
    ordem = ["saida"] + [k for k in E.fontes if k.startswith(("mod:", "pasta:"))] + ["jogo"]
    for k in ordem:
        f = E.fontes.get(k)
        if not f:
            continue
        for c in cands:
            try:
                if f.existe(c):
                    dados = f.ler(c)
                    E.cache_fontes_ttf[nome] = dados
                    return dados, "font/ttf"
            except (jogo.ErroJogo, OSError):
                continue
    E.cache_fontes_ttf[nome] = None
    raise ErroEditor("Fonte não encontrada")


GETS = {"/api/entrada": get_entrada, "/api/imagem": get_imagem, "/api/fonte_ttf": get_fonte_ttf}


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "EditorPlacares/" + VERSAO

    def log_message(self, fmt, *args):
        if os.environ.get("EDITOR_LOG"):
            sys.stderr.write("%s\n" % (fmt % args))

    def enviar(self, status, corpo, tipo="application/json", extra=None):
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        try:
            if url.path in GETS:
                dados, tipo = GETS[url.path](urllib.parse.parse_qs(url.query))
                self.enviar(200, dados, tipo, {"Cache-Control": "no-store"})
                return
            if url.path.startswith("/api/"):
                nome = url.path[5:]
                if nome in ROTAS:
                    self.enviar(200, ROTAS[nome]({}))
                    return
                self.enviar(404, {"erro": "rota desconhecida"})
                return
            rel = urllib.parse.unquote(url.path).lstrip("/") or "index.html"
            caminho = os.path.abspath(os.path.join(WEB, *rel.split("/")))
            if not caminho.startswith(WEB + os.sep) or not os.path.isfile(caminho):
                self.enviar(404, b"nao encontrado", "text/plain")
                return
            with open(caminho, "rb") as f:
                dados = f.read()
            self.enviar(200, dados, MIME.get(os.path.splitext(caminho)[1].lower(), "application/octet-stream"),
                        {"Cache-Control": "no-store"})
        except (ErroEditor, ValueError, KeyError, jogo.ErroJogo, big.ErroBig, apt.ErroApt, OSError) as ex:
            self.enviar(404 if isinstance(ex, (KeyError, FileNotFoundError)) else 400, {"erro": str(ex)})
        except (ConnectionError, BrokenPipeError):
            pass

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        nome = url.path[5:] if url.path.startswith("/api/") else ""
        if nome not in ROTAS:
            self.enviar(404, {"erro": "rota desconhecida"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            self.enviar(200, ROTAS[nome](corpo))
        except (ErroEditor, ValueError, KeyError, PermissionError, FileNotFoundError, jogo.ErroJogo, big.ErroBig, apt.ErroApt,
                as2.ErroAS, tema.ErroTema) as ex:
            self.enviar(400, {"erro": str(ex)})
        except (ConnectionError, BrokenPipeError):
            pass
        except Exception as ex:
            traceback.print_exc()
            self.enviar(500, {"erro": f"{type(ex).__name__}: {ex}"})


def abrir_janela(url):
    candidatos = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("LOCALAPPDATA", "")):
            candidatos += [os.path.join(base, r"Google\Chrome\Application\chrome.exe"),
                           os.path.join(base, r"Microsoft\Edge\Application\msedge.exe")]
    else:
        candidatos += [shutil.which(n) or "" for n in ("google-chrome", "chromium", "microsoft-edge")]
    for exe in candidatos:
        if exe and os.path.isfile(exe):
            perfil = os.path.join(AQUI, ".perfil_janela")
            try:
                subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={perfil}", "--window-size=1600,940",
                                  "--no-first-run", "--no-default-browser-check"])
                return
            except OSError:
                pass
    webbrowser.open(url)


def main():
    ap = argparse.ArgumentParser(description="Editor de Placares EA FC")
    ap.add_argument("--porta", type=int, default=8766)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    args = ap.parse_args()
    montar_fontes()   # começa a ler o índice do FC 26 em segundo plano
    srv = None
    for porta in range(args.porta, args.porta + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("Nenhuma porta livre entre %d e %d." % (args.porta, args.porta + 19))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Editor de Placares EA FC {VERSAO} — {url}")
    print("Feche esta janela para encerrar o editor.")
    if not args.sem_janela:
        threading.Timer(0.4, abrir_janela, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
