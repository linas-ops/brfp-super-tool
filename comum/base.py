"""BRFP Super Tool — base comum dos servidores locais das ferramentas (só biblioteca padrão).

Cada ferramenta é um servidor HTTP em 127.0.0.1 com:
  GET  /api/<rota>?…   -> rotas_get[rota](query)  -> JSON
  POST /api/<rota>     -> rotas_post[rota](corpo) -> JSON
  GET  /comum/<arq>    -> comum/web (estilo, componentes e ícones compartilhados)
  GET  /<arq>          -> pasta web da ferramenta
e a linha "BRFP-URL <url>" na saída, que o BRFP Super Tool usa para abrir a ferramenta na própria janela.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COMUM = os.path.dirname(os.path.abspath(__file__))
WEB_COMUM = os.path.join(COMUM, "web")
SUPERTOOL = os.path.dirname(COMUM)
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
        ".woff2": "font/woff2", ".fbx": "application/octet-stream"}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


class ErroUsuario(Exception):
    """Erro com mensagem para mostrar na interface (resposta 400)."""


def raiz_trabalho():
    """Pasta de trabalho (a que contém o BRFP Super Tool, os exports e o conversor)."""
    r = os.environ.get("BRFP_RAIZ")
    if r and os.path.isdir(r):
        return r
    return os.path.dirname(SUPERTOOL)


def longo(caminho):
    """Caminho com prefixo \\\\?\\ no Windows (exports do FET passam de 260 caracteres)."""
    c = os.path.abspath(caminho)
    if os.name == "nt" and not c.startswith("\\\\?\\"):
        return "\\\\?\\" + c
    return c


class Prefs:
    def __init__(self, caminho, padrao=None):
        self.caminho = caminho
        self.padrao = padrao or {}
        self.lock = threading.Lock()

    def ler(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        return {**self.padrao, **d}

    def gravar(self, d):
        with self.lock:
            tmp = self.caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.caminho)

    def atualizar(self, **kw):
        d = self.ler()
        d.update(kw)
        self.gravar(d)
        return d


# ------------------------------------------------------------------ Python, diálogos e componentes
def python_cmd(*args):
    """Comando para rodar outro script no mesmo Python (embutido ou do computador), sempre em UTF-8."""
    return [sys.executable, "-X", "utf8", *args]


def dialogo(modo, titulo="", inicial=None, tipos=None, multiplo=False, nome="", extensao=""):
    """Diálogo nativo do Windows (comum/dialogos.py). modo: 'pasta' | 'abrir' | 'salvar'.
    Devolve caminho (ou lista, se multiplo) ou None se cancelado."""
    import dialogos
    if inicial and not os.path.isdir(inicial):
        inicial = os.path.dirname(inicial) if os.path.isdir(os.path.dirname(inicial)) else None
    return dialogos.escolher(modo, titulo, inicial or raiz_trabalho(), tipos, multiplo, nome, extensao)


def pasta_conversor():
    """Motor do Conversor PES → FC: <pasta de trabalho>/conversor (onde ele é desenvolvido) ou o que vem no pacote."""
    e = os.environ.get("BRFP_CONVERSOR")
    if e:
        return e
    pacote = os.path.join(SUPERTOOL, "ferramentas", "conversor_pes", "motor")
    for c in (os.path.join(raiz_trabalho(), "conversor"), pacote):
        if os.path.isfile(os.path.join(c, "converter.py")):
            return c
    return pacote


def pasta_rdbm():
    """RDBM 26 · Add-on FC 27: <pasta de trabalho>/RDBM26 Add-on FC27 ou ferramentas/rdbm (pacote)."""
    pacote = os.path.join(SUPERTOOL, "ferramentas", "rdbm")
    for c in (os.path.join(raiz_trabalho(), "RDBM26 Add-on FC27"), pacote):
        if os.path.isfile(os.path.join(c, "RDBM26_FC27.exe")):
            return c
    return pacote


def rotas_componentes(grupo, ao_concluir=None):
    """Rotas para a ferramenta baixar os pacotes de que precisa: GET componentes, POST componentes_instalar."""
    import componentes as C
    if ao_concluir:
        C.AO_CONCLUIR.append(lambda feitos: ao_concluir())

    def get(_):
        return {"grupo": C.estado_grupo(grupo), "tarefa": C.tarefa_publica(), "python": C.python_embutido(),
                "problema": C.problema_caminho()}

    def post(_):
        try:
            return {"tarefa": C.iniciar([grupo])}
        except C.ErroComponente as ex:
            raise ErroUsuario(str(ex))
    return {"componentes": get}, {"componentes_instalar": post}


def abrir_no_explorer(caminho, selecionar=False):
    caminho = os.path.normpath(caminho)
    if not os.path.exists(caminho):
        raise ErroUsuario(f"Não encontrado: {caminho}")
    if os.name == "nt":
        if selecionar or os.path.isfile(caminho):
            subprocess.Popen(["explorer", "/select,", caminho])
        else:
            os.startfile(caminho)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", caminho if os.path.isdir(caminho) else os.path.dirname(caminho)])


def mandar_para_lixeira(caminho):
    """Manda um arquivo ou pasta para a Lixeira do Windows (dá para restaurar). Nada é apagado de vez."""
    caminho = os.path.abspath(caminho)
    if not os.path.exists(caminho):
        raise ErroUsuario(f"Não encontrado: {caminho}")
    if os.name != "nt":
        raise ErroUsuario("A Lixeira só está disponível no Windows.")
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, caminho + "\0", None, FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
                         False, None, None)
    r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if r != 0 or op.fAnyOperationsAborted or os.path.exists(caminho):
        raise ErroUsuario(f"Não foi possível mandar para a Lixeira: {caminho} (código {r}).")


# ------------------------------------------------------------------ HTTP
def criar_handler(web, rotas_get=None, rotas_post=None, especiais=None, nome="BRFP"):
    """especiais: {caminho: fn(handler, query)} para respostas que não são JSON (arquivos, imagens)."""
    rotas_get = rotas_get or {}
    rotas_post = rotas_post or {}
    especiais = especiais or {}
    web = os.path.abspath(web)

    class Handler(BaseHTTPRequestHandler):
        server_version = nome

        def log_message(self, fmt, *args):
            if os.environ.get("BRFP_LOG"):
                sys.stderr.write("%s\n" % (fmt % args))

        def enviar(self, status, corpo, tipo="application/json", extra=None):
            if isinstance(corpo, (dict, list)):
                corpo = json.dumps(corpo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            elif isinstance(corpo, str):
                corpo = corpo.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def arquivo(self, caminho):
            ext = os.path.splitext(caminho)[1].lower()
            with open(longo(caminho), "rb") as f:
                dados = f.read()
            self.enviar(200, dados, MIME.get(ext, "application/octet-stream"))

        def _erro(self, ex):
            if isinstance(ex, (ErroUsuario, ValueError, KeyError, FileNotFoundError, PermissionError)):
                msg = str(ex) if not isinstance(ex, KeyError) else f"Campo ausente: {ex}"
                self.enviar(400, {"erro": msg})
            else:
                traceback.print_exc()
                self.enviar(500, {"erro": f"{type(ex).__name__}: {ex}"})

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            try:
                if url.path in especiais:
                    especiais[url.path](self, q)
                    return
                if url.path.startswith("/api/"):
                    nome_rota = url.path[5:]
                    if nome_rota in rotas_get:
                        self.enviar(200, rotas_get[nome_rota](q))
                    else:
                        self.enviar(404, {"erro": "rota desconhecida"})
                    return
                rel = urllib.parse.unquote(url.path).lstrip("/") or "index.html"
                base = web
                if rel.startswith("comum/"):
                    base, rel = WEB_COMUM, rel[6:]
                caminho = os.path.abspath(os.path.join(base, *rel.split("/")))
                if not caminho.startswith(base + os.sep) or not os.path.isfile(caminho):
                    self.enviar(404, b"nao encontrado", "text/plain")
                    return
                self.arquivo(caminho)
            except (ConnectionError, BrokenPipeError):
                pass
            except Exception as ex:  # noqa: BLE001
                try:
                    self._erro(ex)
                except (ConnectionError, BrokenPipeError):
                    pass

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            nome_rota = url.path[5:] if url.path.startswith("/api/") else ""
            if nome_rota not in rotas_post:
                self.enviar(404, {"erro": "rota desconhecida"})
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                corpo = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                self.enviar(200, rotas_post[nome_rota](corpo))
            except (ConnectionError, BrokenPipeError):
                pass
            except Exception as ex:  # noqa: BLE001
                try:
                    self._erro(ex)
                except (ConnectionError, BrokenPipeError):
                    pass

    return Handler


def abrir_janela(url, perfil):
    """Janela de aplicativo (sem barra do navegador) no Edge ou Chrome; senão o navegador padrão."""
    candidatos = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            candidatos += [os.path.join(base, r"Google\Chrome\Application\chrome.exe"),
                           os.path.join(base, r"Microsoft\Edge\Application\msedge.exe")]
    else:
        candidatos += [shutil.which(n) or "" for n in ("google-chrome", "chromium", "microsoft-edge")]
    for exe in candidatos:
        if exe and os.path.isfile(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={perfil}", "--window-size=1600,960",
                                  "--no-first-run", "--no-default-browser-check"])
                return
            except OSError:
                pass
    webbrowser.open(url)


def servir(handler, porta, titulo, versao, sem_janela=False, perfil=None, sufixo=""):
    """Sobe o servidor na primeira porta livre a partir de 'porta' e fica atendendo até ser encerrado."""
    srv = None
    for p in range(porta, porta + 30):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("Nenhuma porta livre entre %d e %d." % (porta, porta + 29))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"{titulo} {versao} — {url}", flush=True)
    print(f"BRFP-URL {url}", flush=True)
    if not sem_janela:
        print("Feche esta janela para encerrar.", flush=True)
        threading.Timer(0.4, abrir_janela, args=(url + sufixo, perfil or os.path.join(SUPERTOOL, ".perfil_janela"))).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return srv
