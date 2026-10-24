"""BRFP Super Tool — atualização pela última Release do GitHub (github.com/linas-ops/brfp-super-tool).

verificar(versao)  consulta a Release mais nova (guardada por algumas horas) e diz se ela é mais nova que esta
iniciar()          baixa o pacote leve da Release e copia por cima da pasta do Super Tool, em segundo plano

O pacote leve só leva o código das ferramentas (comum/pacote.py): banco e idioma importados, preferências, o Python
embutido (runtime/), o perfil da janela e as saídas deste computador ficam como estão. Depois é só reabrir o Super Tool.
Numa edição (comum/edicao.py, ex.: só o Editor de Placares), só entram as ferramentas da edição e o LEIA-ME dela fica.
"""
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile

import edicao

REPO = "linas-ops/brfp-super-tool"
PAGINA = f"https://github.com/{REPO}/releases/latest"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RAIZ_ZIP = "BRFP Super Tool/"
SUPERTOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARDA = 6 * 3600
_CACHE = {"quando": 0, "release": None, "erro": None}
ESTADO = {"ativo": False, "fase": "", "feito": 0, "total": 0, "erro": None, "msg": "", "versao": None, "falhas": []}


def _numeros(v):
    return tuple(int(n) for n in re.findall(r"\d+", v or "")) or (0,)


def _baixar_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BRFP-Super-Tool", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def _release(forcar=False):
    if forcar or time.time() - _CACHE["quando"] > GUARDA:
        try:
            _CACHE.update(release=_baixar_json(API), erro=None)
        except Exception as ex:  # noqa: BLE001 — sem internet ou sem Release: só não avisa
            _CACHE.update(release=None, erro=str(ex))
        _CACHE["quando"] = time.time()
    return _CACHE["release"]


def _zip_leve(rel):
    for a in rel.get("assets") or []:
        if a.get("name", "").lower().endswith(".zip") and "leve" in a["name"].lower():
            return a
    return None


def verificar(versao, forcar=False):
    rel = _release(forcar)
    if not rel:
        return {"nova": False, "atual": versao, "erro": _CACHE["erro"], "pagina": PAGINA}
    ultima = (rel.get("tag_name") or "").lstrip("vV")
    zipa = _zip_leve(rel)
    return {"nova": bool(zipa) and _numeros(ultima) > _numeros(versao), "atual": versao, "ultima": ultima,
            "notas": (rel.get("body") or "").strip(), "pagina": rel.get("html_url") or PAGINA,
            "tamanho": zipa.get("size") if zipa else None, "estado": dict(ESTADO)}


def _aplicar(caminho_zip):
    falhas = []
    e = edicao.atual()
    with zipfile.ZipFile(caminho_zip) as z:
        itens = [i for i in z.infolist() if i.filename.startswith(RAIZ_ZIP) and not i.is_dir()
                 and (not e or (edicao.leva(e, i.filename[len(RAIZ_ZIP):]) and i.filename != RAIZ_ZIP + "LEIA-ME PRIMEIRO.txt"))]
        ESTADO.update(fase="copiando", feito=0, total=len(itens))
        for n, i in enumerate(itens, 1):
            rel = i.filename[len(RAIZ_ZIP):]
            partes = rel.split("/")
            if not rel or ".." in partes or os.path.isabs(rel):
                continue
            destino = os.path.join(SUPERTOOL, *partes)
            try:
                novo = z.read(i)
                if os.path.isfile(destino):
                    with open(destino, "rb") as fh:
                        if fh.read() == novo:
                            ESTADO.update(feito=n)
                            continue
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                tmp = destino + ".novo"
                with open(tmp, "wb") as fh:
                    fh.write(novo)
                os.replace(tmp, destino)
            except OSError as ex:  # arquivo em uso (ex.: o add-on do RDBM aberto)
                falhas.append(f"{rel}: {ex.strerror or ex}")
            ESTADO.update(feito=n, msg=rel)
    return falhas


def iniciar():
    if ESTADO["ativo"]:
        return dict(ESTADO)
    rel = _release(forcar=True)
    zipa = _zip_leve(rel) if rel else None
    if not zipa:
        raise RuntimeError("Não encontrei o pacote da versão nova no GitHub. Tente de novo mais tarde ou baixe em " + PAGINA)
    ESTADO.update(ativo=True, fase="baixando", feito=0, total=zipa.get("size") or 0, erro=None, falhas=[],
                  versao=(rel.get("tag_name") or "").lstrip("vV"), msg="Baixando a versão nova…")

    def rodar():
        pasta = tempfile.mkdtemp(prefix="brfp-atualizacao-")
        try:
            arq = os.path.join(pasta, "leve.zip")
            # pelo id do arquivo na API (o link pelo nome pode ficar em cache apontando para um arquivo trocado)
            req = urllib.request.Request(zipa["url"], headers={"User-Agent": "BRFP-Super-Tool", "Accept": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=30) as r, open(arq, "wb") as fh:
                while True:
                    bloco = r.read(256 * 1024)
                    if not bloco:
                        break
                    fh.write(bloco)
                    ESTADO["feito"] += len(bloco)
            falhas = _aplicar(arq)
            ESTADO.update(fase="pronto", falhas=falhas,
                          msg="Atualizado. Feche e abra o Super Tool para usar a versão nova." if not falhas else
                          "Atualizado em parte: feche os programas abertos e atualize de novo.")
        except Exception as ex:  # noqa: BLE001
            ESTADO.update(fase="erro", erro=f"{type(ex).__name__}: {ex}", msg=str(ex))
        finally:
            shutil.rmtree(pasta, ignore_errors=True)
            ESTADO["ativo"] = False
    threading.Thread(target=rodar, daemon=True).start()
    return dict(ESTADO)
