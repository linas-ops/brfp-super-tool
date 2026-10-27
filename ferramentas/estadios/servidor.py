"""Editor de Estádios EA FC — servidor local.

    python servidor.py [--porta 8765] [--sem-janela] [pasta_do_export ...]

Abre a interface no navegador (janela de aplicativo do Edge/Chrome quando disponível). Só aceita conexões
desta máquina (127.0.0.1). Os arquivos são lidos e gravados direto nas pastas exportadas pelo FET.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import hashlib  # noqa: E402

from nucleo import edicao, jogo, meshzero, renomear, torcida  # noqa: E402
from nucleo import xmlfet as X  # noqa: E402
from nucleo.cena import Cena, catalogo_texturas  # noqa: E402
from nucleo.indice import Indice, detectar_exports  # noqa: E402

WEB = os.path.join(AQUI, "web")
PREFS = os.path.join(AQUI, "preferencias.json")
VERSAO = "3.4"
AUTOSALVO = os.path.join(AQUI, "cache", "autosalvo")


def raiz_trabalho():
    """Pasta de trabalho (exports, stadiums.txt): a do BRFP Super Tool, ou a pasta acima do editor se rodar sozinho."""
    r = os.environ.get("BRFP_RAIZ")
    if r and os.path.isdir(r):
        return r
    pai = os.path.dirname(AQUI)
    if os.path.basename(pai).lower() == "ferramentas":      # BRFP Super Tool/ferramentas/estadios
        return os.path.dirname(os.path.dirname(pai))
    return pai


RAIZ = raiz_trabalho()
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
        ".fbx": "application/octet-stream", ".xml": "text/xml; charset=utf-8", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".tga": "application/octet-stream", ".dds": "application/octet-stream",
        ".woff2": "font/woff2"}


class Estado:
    def __init__(self):
        self.indice = None
        self.cena = None
        self.lock = threading.Lock()

    def prefs(self):
        try:
            with open(PREFS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def salvar_prefs(self, p):
        with open(PREFS, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=1)


ESTADO = Estado()


def exige_indice():
    if ESTADO.indice is None:
        raise ValueError("Nenhuma pasta aberta.")
    return ESTADO.indice


# ------------------------------------------------------------------ rotas da API

def api_versao(_):
    return {"versao": VERSAO}


def api_inicio(_):
    base = RAIZ
    exports = detectar_exports(base)
    p = ESTADO.prefs()
    recentes = [r for r in p.get("recentes", []) if all(os.path.isdir(x) for x in r.get("pastas", []))]
    projetos = [x for x in p.get("projetos", []) if os.path.isfile(x)]
    return {"versao": VERSAO, "exports": exports, "recentes": recentes[:8], "base": base, "projetos": projetos[:6],
            "aberto": ESTADO.indice.pastas if ESTADO.indice else None}


def api_navegar(d):
    caminho = d.get("caminho") or ""
    if not caminho:
        if os.name == "nt":
            import string
            drives = [f"{l}:\\" for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]
            casa = os.path.expanduser("~")
            return {"caminho": "", "pai": None, "pastas": [{"nome": d, "caminho": d} for d in drives] +
                    [{"nome": "Downloads", "caminho": os.path.join(casa, "Downloads")},
                     {"nome": "Área de trabalho", "caminho": os.path.join(casa, "Desktop")}], "export": False}
        caminho = "/"
    caminho = os.path.abspath(caminho)
    pastas = []
    try:
        for n in sorted(os.listdir(caminho), key=str.lower):
            q = os.path.join(caminho, n)
            if os.path.isdir(q) and not n.startswith((".", "$")):
                pastas.append({"nome": n, "caminho": q})
    except OSError as ex:
        raise ValueError(f"Não foi possível abrir {caminho}: {ex.strerror}")
    pai = os.path.dirname(caminho)
    exp = detectar_exports(caminho, profundidade=0)
    return {"caminho": caminho, "pai": pai if pai != caminho else "", "pastas": pastas,
            "export": exp[0] if exp else None}


def api_dialogo_pasta(d):
    inicial = d.get("inicial") or RAIZ
    p = _dialogos().escolher("pasta", "Escolha a pasta exportada pelo FET", inicial)
    return {"caminho": os.path.abspath(p) if p else None}


def api_abrir(d):
    pastas = [os.path.abspath(p) for p in d.get("pastas", []) if p]
    if not pastas or not all(os.path.isdir(p) for p in pastas):
        raise ValueError("Pasta não encontrada.")
    with ESTADO.lock:
        ix = Indice(pastas)
        ESTADO.indice = ix
        ESTADO.cena = None
    mundos = ix.mundos()
    p = ESTADO.prefs()
    rec = [r for r in p.get("recentes", []) if r.get("pastas") != pastas]
    rec.insert(0, {"pastas": pastas, "nome": os.path.basename(pastas[0]), "quando": time.strftime("%d/%m/%Y %H:%M")})
    p["recentes"] = rec[:10]
    ESTADO.salvar_prefs(p)
    return {"pastas": pastas, "mundos": mundos, "arquivos": len(ix.mapa), "duplicados": ix.duplicados,
            "ultimo": p.get("ultimo_mundo", {}).get(pastas[0])}


def api_cena(d):
    ix = exige_indice()
    with ESTADO.lock:
        c = Cena(ix).carregar(d["mundo"])
        ESTADO.cena = c
    j = c.json()
    if j["campo"].get("arquivo"):   # o stadiums.txt entra na lista de alterações/restauração
        edicao.EXTRAS[os.path.abspath(j["campo"]["arquivo"])] = "stadiums.txt"
    p = ESTADO.prefs()
    p.setdefault("ultimo_mundo", {})[ix.pastas[0]] = d["mundo"]
    ESTADO.salvar_prefs(p)
    return j


def api_texturas(_):
    return {"texturas": catalogo_texturas(exige_indice())}


def api_torcida(d):
    ix = exige_indice()
    return torcida.ler(ix.de_id(d["arq"]))


def api_torcida_remover(d):
    ix = exige_indice()
    ident = d["arq"]
    caminho = ix.de_id(ident)
    texto, restantes = torcida.remover(X.ler(caminho), d["indices"])
    edicao.garantir_backup(ix, ident)
    X.gravar(caminho, texto)
    return {"restantes": restantes}


def api_salvar(d):
    ix = exige_indice()
    with ESTADO.lock:
        r = edicao.aplicar(ix, d.get("alteracoes", []))
    return r


def api_alteracoes(_):
    return {"arquivos": edicao.listar_alteracoes(exige_indice())}


def api_restaurar(d):
    return {"restaurados": edicao.restaurar(exige_indice(), d.get("ids", []))}


def api_exportar(d):
    ix = exige_indice()
    destino = d.get("destino") or (ix.pastas[0].rstrip("\\/") + "_alteracoes")
    n = edicao.exportar(ix, destino, d.get("ids"))
    return {"destino": destino, "copiados": n}


def api_explorer(d):
    ix = exige_indice() if d.get("id") else None
    caminho = ix.de_id(d["id"]) if ix else d.get("caminho")
    if not caminho or not os.path.exists(caminho):
        raise ValueError("Arquivo não encontrado.")
    if os.name == "nt":
        if os.path.isdir(caminho):
            subprocess.Popen(["explorer", caminho])
        else:
            subprocess.Popen(["explorer", "/select,", caminho])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(caminho)])
    return {"ok": True}


def api_substituir(d):
    """Substitui um arquivo binário (FBX de uma malha ou PNG de uma textura) guardando o original."""
    ix = exige_indice()
    if d.get("id"):
        ext = os.path.splitext(d["id"])[1].lower()
        if ext not in (".fbx", ".png"):
            raise ValueError("Só FBX e PNG podem ser substituídos.")
        caminho = edicao.gravar_binario(ix, d["id"], d["dados"])
        return {"id": d["id"], "caminho": caminho}
    rel = d["novo"]
    if not rel.lower().endswith(".png"):
        raise ValueError("Só PNG pode ser criado.")
    caminho = edicao.criar_arquivo(ix, rel, d["dados"])
    return {"id": f"0:{rel}", "caminho": caminho}


def api_mvdb_entrada(d):
    """Cria no MVDB do sub-mundo a entrada de uma malha que não tem (asset novo), ou o material das partições que
    faltam numa entrada que já existe, copiando shader/texturas de variações existentes; devolve a entrada lida de
    novo, no formato da cena."""
    ix = exige_indice()
    if not ESTADO.cena:
        raise ValueError("Nenhum estádio aberto.")
    chave = d["malha"]
    info = ESTADO.cena.malhas.get(chave)
    mvdb = ESTADO.cena.mvdbs.get(d["mvdb"])
    if not info or not mvdb or not mvdb.get("arq"):
        raise ValueError("MeshVariationDb deste sub-mundo não está no export.")
    with ESTADO.lock:
        edicao.entrada_mvdb(ix, mvdb["arq"], info["asset"], d.get("origens"), d.get("padrao"))
        nova = Cena(ix)
        nova.ler_mvdb(d["mvdb"], {chave})
        antes = [m.get("guid") for m in info.get("materiais") or []]
        if info.get("xml"):      # o XML da malha muda quando ganha MeshMaterial para partição nova ("null")
            nova.ler_xml_malha(info, ix.de_id(info["xml"]))
    mats = nova.mvdbs[d["mvdb"]]["entradas"].get(chave)
    if not mats:
        raise ValueError("A entrada foi gravada, mas não consegui lê-la de volta.")
    mvdb["entradas"][chave] = mats
    ESTADO.cena.texturas.update({k: v for k, v in nova.texturas.items() if k not in ESTADO.cena.texturas})
    xml_mudou = [m.get("guid") for m in info.get("materiais") or []] != antes
    return {"materiais": mats, "texturas": nova.texturas, "arq": mvdb["arq"], "malha_materiais": info.get("materiais"),
            "xml_malha": info.get("xml") if xml_mudou else None}


def api_mesh_zero(d):
    """Troca o FBX de cada malha por um "mesh zero" (um triângulo minúsculo por seção), guardando o original."""
    ix = exige_indice()
    feitos, erros = [], []
    for ident in d.get("ids", []):
        if not ident.lower().endswith(".fbx"):
            erros.append(f"{ident}: não é um FBX")
            continue
        try:
            caminho = edicao.garantir_backup(ix, ident)
            antes, depois = meshzero.zerar(X.longo(caminho))
            feitos.append({"id": ident, "antes": antes, "depois": depois})
        except (OSError, ValueError, RuntimeError) as ex:
            erros.append(f"{ident.split(':', 1)[-1]}: {ex}")
    return {"feitos": feitos, "erros": erros}


# ------------------------------------------------------------------ jogo (texturas direto do FC 26)

def jogo_atual(iniciar=True):
    p = ESTADO.prefs()
    j, faltando = jogo.obter(p)
    if j and iniciar and p.get("jogo_ativo", True):
        j.iniciar()
    return j, faltando


def api_jogo(_):
    p = ESTADO.prefs()
    j, faltando = jogo_atual()
    info = j.info() if j else {"estado": "indisponivel", "pasta": (faltando or {}).get("pasta"), "cache": (faltando or {}).get("cache")}
    info["ativo"] = p.get("jogo_ativo", True)
    info["qualidade"] = p.get("jogo_qualidade", 1024)
    info["detectado"] = {"pasta": jogo.detectar_pasta_jogo(), "cache": jogo.detectar_cache_fmt()}
    return info


def api_jogo_config(d):
    p = ESTADO.prefs()
    for k_in, k_pref in (("pasta", "jogo_pasta"), ("cache", "jogo_cache")):
        if k_in in d:
            v = (d[k_in] or "").strip()
            if v:
                p[k_pref] = os.path.abspath(v)
            else:   # em branco = detectar de novo
                p.pop(k_pref, None)
                (jogo.detectar_pasta_jogo if k_in == "pasta" else jogo.detectar_cache_fmt)(forcar=True)
    if "ativo" in d:
        p["jogo_ativo"] = bool(d["ativo"])
    if "qualidade" in d:
        p["jogo_qualidade"] = int(d["qualidade"])
    ESTADO.salvar_prefs(p)
    return api_jogo({})   # jogo.obter() troca a instância só se a pasta ou o cache mudaram


def exige_jogo():
    j, _ = jogo_atual()
    if not j:
        raise ValueError("FC 26 não configurado (pasta do jogo ou índice do FMT não encontrados).")
    j.pronto()
    return j


def api_jogo_texturas(d):
    j = exige_jogo()
    return {"texturas": j.lista(d.get("prefixo", ""))}


def api_jogo_guids(d):
    j = exige_jogo()
    nome, ref, pguid = j.guids(d["asset"])
    return {"asset": nome, "ref": ref, "pguid": pguid}


def api_jogo_detalhes(d):
    return exige_jogo().detalhes(d["asset"])


# ------------------------------------------------------------------ arquivos de projeto e salvamento automático

def api_dialogo_arquivo(d):
    modo = d.get("modo", "abrir")
    inicial = d.get("inicial") or RAIZ
    tipos = [("Projeto do Editor de Estádios", "*.estadio.json"), ("JSON", "*.json"), ("Todos", "*.*")]
    if modo == "cache":
        tipos = [("Cache do FMT (FC26.cache)", "*.cache"), ("Todos", "*.*")]
    elif modo == "imagem":
        tipos = [("Imagens", "*.png;*.jpg;*.jpeg;*.bmp;*.webp"), ("Todos", "*.*")]
    if modo == "salvar":
        p = _dialogos().escolher("salvar", "Salvar projeto", inicial, tipos, nome=d.get("nome") or "", extensao=".estadio.json")
    else:
        titulos = {"cache": "Escolha o FC26.cache do FMT", "imagem": "Escolha uma imagem"}
        p = _dialogos().escolher("abrir", titulos.get(modo, "Abrir projeto"), inicial, tipos)
    return {"caminho": os.path.abspath(p) if p else None}


def _dialogos():
    """Diálogos nativos do Windows do BRFP Super Tool (comum/dialogos.py; o Python embutido não tem tkinter)."""
    comum = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum")
    if comum not in sys.path:
        sys.path.append(comum)
    import dialogos
    return dialogos


def api_projeto_salvar(d):
    caminho = d["caminho"]
    if not caminho.lower().endswith(".json"):
        caminho += ".estadio.json"
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d["dados"], f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, caminho)
    p = ESTADO.prefs()
    rec = [x for x in p.get("projetos", []) if x != caminho]
    p["projetos"] = [caminho] + rec[:9]
    ESTADO.salvar_prefs(p)
    return {"caminho": caminho, "bytes": os.path.getsize(caminho)}


def api_projeto_ler(d):
    with open(d["caminho"], encoding="utf-8") as f:
        dados = json.load(f)
    if dados.get("formato") != "editor-estadios":
        raise ValueError("Este arquivo não é um projeto do Editor de Estádios.")
    return {"dados": dados, "caminho": os.path.abspath(d["caminho"])}


def _arq_auto(chave):
    return os.path.join(AUTOSALVO, hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16] + ".json")


def api_autosalvar(d):
    arq = _arq_auto(d["chave"])
    if d.get("dados") is None:
        if os.path.exists(arq):
            os.remove(arq)
        return {"ok": True}
    os.makedirs(AUTOSALVO, exist_ok=True)
    with open(arq + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d["dados"], f, ensure_ascii=False, separators=(",", ":"))
    os.replace(arq + ".tmp", arq)
    return {"ok": True}


def api_autosalvo(d):
    arq = _arq_auto(d["chave"])
    if not os.path.exists(arq):
        return {"dados": None}
    with open(arq, encoding="utf-8") as f:
        return {"dados": json.load(f), "quando": time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(arq)))}


# ------------------------------------------------------------------ exportar com outro nome (batch import)

def api_renomear_previa(d):
    ix = exige_indice()
    mundo = ESTADO.cena.mundo_asset if ESTADO.cena else None
    return renomear.previa(ix, d.get("trocas", []), d.get("escopo", "alterados"), mundo)


def api_renomear_exportar(d):
    ix = exige_indice()
    mundo = ESTADO.cena.mundo_asset if ESTADO.cena else None
    return renomear.exportar(ix, d.get("trocas", []), d.get("escopo", "alterados"), d["destino"], d.get("conteudo", True), mundo)


ROTAS = {"versao": api_versao, "inicio": api_inicio, "navegar": api_navegar, "dialogo_pasta": api_dialogo_pasta, "abrir": api_abrir,
         "cena": api_cena, "texturas": api_texturas, "torcida": api_torcida, "torcida_remover": api_torcida_remover,
         "salvar": api_salvar, "alteracoes": api_alteracoes, "restaurar": api_restaurar, "exportar": api_exportar,
         "explorer": api_explorer, "substituir": api_substituir, "mesh_zero": api_mesh_zero, "mvdb_entrada": api_mvdb_entrada,"jogo": api_jogo, "jogo_config": api_jogo_config,
         "jogo_texturas": api_jogo_texturas, "jogo_guids": api_jogo_guids, "jogo_detalhes": api_jogo_detalhes,
         "dialogo_arquivo": api_dialogo_arquivo, "projeto_salvar": api_projeto_salvar, "projeto_ler": api_projeto_ler,
         "autosalvar": api_autosalvar, "autosalvo": api_autosalvo, "renomear_previa": api_renomear_previa,
         "renomear_exportar": api_renomear_exportar}


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "EditorEstadios/" + VERSAO

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
            if url.path == "/api/jogo/png":
                q = urllib.parse.parse_qs(url.query)
                j = exige_jogo()
                dados = j.png(q["asset"][0], int(q.get("max", ["1024"])[0]))
                self.enviar(200, dados, "image/png", {"Cache-Control": "max-age=604800"})
                return
            if url.path == "/api/arquivo":
                q = urllib.parse.parse_qs(url.query)
                caminho = exige_indice().de_id(q["id"][0])
                self.arquivo(caminho, cache=False)
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
            self.arquivo(caminho, cache="vendor" in rel)
        except (ValueError, KeyError, PermissionError, FileNotFoundError, jogo.ErroJogo) as ex:
            self.enviar(400, {"erro": str(ex)})
        except (ConnectionError, BrokenPipeError):
            pass

    def arquivo(self, caminho, cache):
        ext = os.path.splitext(caminho)[1].lower()
        with open(X.longo(caminho), "rb") as f:
            dados = f.read()
        extra = {"Cache-Control": "max-age=86400" if cache else "no-store"}
        self.enviar(200, dados, MIME.get(ext, "application/octet-stream"), extra)

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
        except (ValueError, KeyError, PermissionError, FileNotFoundError, edicao.ErroEdicao, jogo.ErroJogo) as ex:
            self.enviar(400, {"erro": str(ex)})
        except (ConnectionError, BrokenPipeError):
            pass
        except Exception as ex:  # erro inesperado: devolve a mensagem para a interface mostrar
            traceback.print_exc()
            self.enviar(500, {"erro": f"{type(ex).__name__}: {ex}"})


def abrir_janela(url):
    """Janela de aplicativo (sem barra do navegador) no Edge ou Chrome; senão o navegador padrão."""
    candidatos = []
    if os.name == "nt":
        pf = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files"),
              os.environ.get("LOCALAPPDATA", "")]
        for base in pf:
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
    ap = argparse.ArgumentParser(description="Editor de Estádios EA FC")
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("pastas", nargs="*", help="pasta(s) exportada(s) pelo FET para abrir direto")
    args = ap.parse_args()
    if args.pastas:
        api_abrir({"pastas": args.pastas})
    jogo_atual()   # começa a ler o índice do FC 26 em segundo plano
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
    print(f"Editor de Estádios EA FC {VERSAO} — {url}")
    print("Feche esta janela para encerrar o editor.")
    if not args.sem_janela:
        threading.Timer(0.4, abrir_janela, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
