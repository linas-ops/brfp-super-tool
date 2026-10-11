"""BRFP Super Tool — janela única com todas as ferramentas de modding do BRFP.

    python supertool.py [--porta 8760] [--sem-janela] [--abrir <id>]

Cada ferramenta web (Estádios, Placares, Compdata, Faces, Corpos, Minifaces, Tabelas, Criador, Conversor PES) é um servidor local próprio, iniciado
sob demanda e mostrado dentro da janela do Super Tool. Fechar o Super Tool encerra todas elas (Job Object do Windows).
O RDBM 26 · Add-on FC 27 é um programa nativo: o Super Tool só o abre e passa os comandos de linha.
Banco de dados e idioma do jogo são importados uma vez aqui (página "Dados do jogo") e valem para todas as ferramentas
(comum/dados.py, registro em dados/fontes.json).
Componentes (página "Componentes"): o Python embutido em runtime/python, os pacotes de cada ferramenta (comum/componentes.py)
e o pacote .zip para levar o Super Tool a outro computador (comum/pacote.py).
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "comum"))

import atualizacao  # noqa: E402
import base  # noqa: E402
import componentes  # noqa: E402
import dados  # noqa: E402
import pacote  # noqa: E402

VERSAO = "2.7"
NOME = "BRFP Super Tool"
RAIZ = base.raiz_trabalho()
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"))

FERRAMENTAS = [
    {"id": "estadios", "nome": "Editor de Estádios", "icone": "estadio", "tipo": "web", "porta": 8765,
     "pasta": os.path.join(AQUI, "ferramentas", "estadios"), "guia": "LEIAME.md",
     "descricao": "Abre os exports do FET e mostra o estádio em 3D: ocultar e mover peças, texturas do jogo, luzes, "
                  "torcida, banco de reservas e a linha do stadiums.txt."},
    {"id": "placares", "nome": "Editor de Placares", "icone": "placar", "tipo": "web", "porta": 8766,
     "pasta": os.path.join(AQUI, "ferramentas", "placares"), "guia": "LEIAME.md",
     "descricao": "Abre os placares (overlays APT) do jogo e de mods: edita textos, cores, imagens, posições, animações "
                  "e fontes, e grava para o Live Editor."},
    {"id": "compdata", "nome": "Editor de Compdata", "icone": "trofeu", "tipo": "web", "porta": 8770,
     "pasta": os.path.join(AQUI, "ferramentas", "compdata"), "guia": "README.md",
     "descricao": "Competições, estágios e grupos do compdata: cria, copia e reordena com renumeração automática dos nós "
                  "nos dez arquivos, com validação e backup."},
    {"id": "faces", "nome": "Conversor de Faces", "icone": "rosto", "tipo": "web", "porta": 8771,
     "pasta": os.path.join(AQUI, "ferramentas", "faces"), "guia": "LEIAME.md",
     "descricao": "Converte cabeças (FBX do FET) entre FC 26 e FC 27: identifica o jogo de cada face, escolhe a pasta "
                  "de saída e mostra a prévia 3D da entrada e do resultado."},
    {"id": "corpos", "nome": "Conversor de Corpos", "icone": "pessoa", "tipo": "web", "porta": 8777,
     "pasta": os.path.join(AQUI, "ferramentas", "corpos"), "guia": "LEIAME.md",
     "descricao": "Converte a textura do corpo (pele e tatuagens do bodyupper) entre FC 26 e FC 27: identifica o layout de "
                  "cada imagem, refaz a UV do outro jogo e mostra a entrada e o resultado no corpo em 3D."},
    {"id": "minifaces", "nome": "Criador de Minifaces", "icone": "miniface", "tipo": "web", "porta": 8773,
     "pasta": os.path.join(AQUI, "ferramentas", "minifaces"), "guia": "LEIAME.md",
     "descricao": "Transforma fotos de jogadores em minifaces do jogo: tira o fundo, enquadra o rosto como as originais "
                  "e liga cada foto ao ID do jogador (pID) pelo time do banco importado."},
    {"id": "banco", "nome": "Editor de Banco", "icone": "bancoDados", "tipo": "web", "porta": 8776,
     "pasta": os.path.join(AQUI, "ferramentas", "banco"), "guia": "LEIAME.md",
     "descricao": "Edita o banco importado (FIFA 16 … FC 27): times, jogadores, ligas, árbitros, técnicos e qualquer tabela; "
                  "transferências, empréstimos, escalação e cobradores; verificação de erros com correção."},
    {"id": "tabelas", "nome": "Conversor de Tabelas", "icone": "tabela", "tipo": "web", "porta": 8774,
     "pasta": os.path.join(AQUI, "ferramentas", "tabelas"), "guia": "LEIAME.md",
     "descricao": "Converte tabelas do banco entre jogos (FIFA 16, 21, 22, 23, FC 24, 26 e 27): colunas novas e renomeadas, "
                  "escalas e faixas; grava .txt ou um .db novo. O destino pode ser o esquema guardado de uma versão."},
    {"id": "criador", "nome": "Criador de Ligas e Times", "icone": "escudo", "tipo": "web", "porta": 8775,
     "pasta": os.path.join(AQUI, "ferramentas", "criador"), "guia": "LEIAME.md",
     "descricao": "Cria ligas, times, seleções e jogadores a partir da API-Football ou da Transfermarkt (notas calibradas no "
                  "banco do jogo) e atualiza o banco: elencos, empréstimos, saídas, participantes das ligas e seleções."},
    {"id": "conversor_pes", "nome": "Conversor PES → FC", "icone": "converter", "tipo": "web", "porta": 8772,
     "pasta": os.path.join(AQUI, "ferramentas", "conversor_pes"), "guia": os.path.join(base.pasta_conversor(), "LEIAME.md"),
     "descricao": "Converte estádios do PES 2021 para um estádio base do FC 26 (Blender + texconv), sem comandos: assistente "
                  "de nova conversão, configuração em formulário, etapas explicadas e a lista do que importar no FET."},
    {"id": "rdbm", "nome": "RDBM 26 · Add-on FC 27", "icone": "pacote", "tipo": "nativo",
     "pasta": base.pasta_rdbm(), "exe": "RDBM26_FC27.exe", "guia": "LEIA-ME.txt",
     "descricao": "Abre e edita squads do FC 27 no RDBM 26 sem mexer na instalação do RDBM (programa à parte)."},
]
POR_ID = {f["id"]: f for f in FERRAMENTAS}


def versao_de(f):
    try:
        if f["tipo"] == "web":
            with open(os.path.join(f["pasta"], "servidor.py"), encoding="utf-8") as fh:
                m = re.search(r'^VERSAO = "([^"]+)"', fh.read(), re.M)
            return m.group(1) if m else "?"
        with open(os.path.join(f["pasta"], "src", "RDBM26_FC27.csproj"), encoding="utf-8") as fh:
            m = re.search(r"<Version>([^<]+)</Version>", fh.read())
        return m.group(1) if m else "?"
    except OSError:
        return "?"


# ------------------------------------------------------------------ Job Object: fechar o Super Tool fecha as ferramentas
class Job:
    def __init__(self):
        self.h = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateJobObjectW.restype = wintypes.HANDLE
            h = k.CreateJobObjectW(None, None)

            class IO(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rt", "wt", "ot")]

            class BASICA(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

            class ESTENDIDA(ctypes.Structure):
                _fields_ = [("Basic", BASICA), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            info = ESTENDIDA()
            info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if h and k.SetInformationJobObject(wintypes.HANDLE(h), 9, ctypes.byref(info), ctypes.sizeof(info)):
                self.h, self.k, self.wt = h, k, wintypes
        except Exception:  # noqa: BLE001 — sem o Job, as ferramentas fecham pelo atexit
            self.h = None

    def associar(self, proc):
        if self.h:
            self.k.AssignProcessToJobObject(self.wt.HANDLE(self.h), self.wt.HANDLE(int(proc._handle)))


JOB = Job()


def matar_arvore(proc):
    if proc and proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, creationflags=SEM_JANELA)
        else:
            proc.kill()


class Filho:
    """Servidor de uma ferramenta web."""

    def __init__(self, f):
        self.f = f
        self.proc = None
        self.url = None
        self.estado = "parado"     # parado | iniciando | rodando | erro
        self.erro = None
        self.log = collections.deque(maxlen=600)
        self.inicio = 0
        self.lock = threading.Lock()

    def iniciar(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
            self.url, self.erro, self.estado, self.inicio = None, None, "iniciando", time.time()
            self.log.clear()
            env = dict(os.environ, BRFP_RAIZ=RAIZ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", BRFP_SUPERTOOL="1")
            cmd = base.python_cmd("-u", os.path.join(self.f["pasta"], "servidor.py"), "--sem-janela", "--porta", str(self.f["porta"]))
            try:
                self.proc = subprocess.Popen(cmd, cwd=self.f["pasta"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=env,
                                             creationflags=SEM_JANELA)
            except OSError as ex:
                self.estado, self.erro = "erro", f"Não foi possível iniciar: {ex}"
                return
            JOB.associar(self.proc)
            threading.Thread(target=self._ler, args=(self.proc,), daemon=True).start()

    def _ler(self, proc):
        for linha in proc.stdout:
            linha = linha.rstrip("\r\n")
            self.log.append(linha)
            if self.url is None:
                m = re.search(r"https?://127\.0\.0\.1:\d+/", linha)
                if m:
                    self.url = m.group(0)
                    self.estado = "rodando"
        cod = proc.wait()
        if proc is self.proc:
            if self.estado != "parado":
                self.estado = "erro"
                self.erro = f"A ferramenta fechou (código {cod})." if self.url else f"A ferramenta não abriu (código {cod})."
            self.url = None

    def parar(self):
        with self.lock:
            p = self.proc
            self.estado = "parado"
            self.url = None
        matar_arvore(p)

    def publico(self):
        return {"estado": self.estado, "url": self.url, "erro": self.erro, "desde": self.inicio,
                "log": list(self.log)[-40:] if self.estado == "erro" else []}


FILHOS = {f["id"]: Filho(f) for f in FERRAMENTAS if f["tipo"] == "web"}


# ------------------------------------------------------------------ rotas
def info_ferramenta(f):
    d = {k: f.get(k) for k in ("id", "nome", "icone", "tipo", "descricao")}
    d["versao"] = versao_de(f)
    d["pasta"] = f["pasta"]
    d["existe"] = os.path.isfile(os.path.join(f["pasta"], "servidor.py" if f["tipo"] == "web" else f.get("exe", "")))
    if f["tipo"] == "web":
        d.update(FILHOS[f["id"]].publico())
    return d


def api_ferramentas(_):
    return {"ferramentas": [info_ferramenta(f) for f in FERRAMENTAS]}


def api_inicio(_):
    p = PREFS.ler()
    return {"versao": VERSAO, "app": NOME, "raiz": RAIZ, "pasta": AQUI, "ultima": p.get("ultima"),
            "ferramentas": [info_ferramenta(f) for f in FERRAMENTAS]}


def exige_web(d):
    f = POR_ID.get(d.get("id"))
    if not f or f["tipo"] != "web":
        raise base.ErroUsuario("Ferramenta desconhecida.")
    return FILHOS[f["id"]]


def api_iniciar(d):
    fl = exige_web(d)
    fl.iniciar()
    PREFS.atualizar(ultima=d["id"])
    return info_ferramenta(fl.f)


def api_parar(d):
    fl = exige_web(d)
    fl.parar()
    return info_ferramenta(fl.f)


def api_reiniciar(d):
    fl = exige_web(d)
    fl.parar()
    time.sleep(0.4)
    fl.iniciar()
    return info_ferramenta(fl.f)


def api_lembrar(d):
    if d.get("id") in POR_ID or d.get("id") == "inicio":
        PREFS.atualizar(ultima=d["id"])
    return {}


def api_log(q):
    fl = exige_web(q)
    return {"linhas": list(fl.log)}


def api_abrir_pasta(d):
    f = POR_ID.get(d.get("id"))
    alvo = f["pasta"] if f else (AQUI if d.get("id") == "supertool" else RAIZ)
    base.abrir_no_explorer(alvo)
    return {}


def caminho_guia(f):
    g = f.get("guia") or ""
    if f["id"] == "faces" and not os.path.isfile(os.path.join(f["pasta"], g)):
        g = os.path.join("motor", "LEIA-ME.txt")
    return g if os.path.isabs(g) else os.path.join(f["pasta"], g)


def api_guia(q):
    if q.get("id") == "supertool":
        caminho = os.path.join(AQUI, "LEIAME.md")
    else:
        f = POR_ID.get(q.get("id"))
        if not f:
            raise base.ErroUsuario("Ferramenta desconhecida.")
        caminho = caminho_guia(f)
    if not os.path.isfile(caminho):
        raise base.ErroUsuario("Guia não encontrado.")
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        return {"texto": fh.read(), "caminho": caminho, "markdown": caminho.lower().endswith(".md")}


# ------------------------------------------------------------------ RDBM 26 · Add-on FC 27 (programa nativo)
def rdbm():
    return POR_ID["rdbm"]


def api_rdbm_info(_):
    f = rdbm()
    ini = {}
    try:
        with open(os.path.join(f["pasta"], "addon.ini"), encoding="utf-8-sig") as fh:
            for linha in fh:
                if "=" in linha and not linha.lstrip().startswith("#"):
                    k, v = linha.split("=", 1)
                    ini[k.strip()] = v.strip()
    except OSError:
        pass
    log = []
    try:
        with open(os.path.join(f["pasta"], "addon.log"), encoding="utf-8", errors="replace") as fh:
            log = fh.read().splitlines()[-60:]
    except OSError:
        pass
    backups = os.path.join(f["pasta"], "backups")
    nb = len(os.listdir(backups)) if os.path.isdir(backups) else 0
    return {**info_ferramenta(f), "ini": ini, "log": log, "backups": nb, "rdbm_ok": bool(componentes.achar_rdbm(f["pasta"])),
            "dotnet": componentes.dotnet48()}


def api_rdbm(d):
    f = rdbm()
    exe = os.path.join(f["pasta"], f["exe"])
    if not os.path.isfile(exe):
        raise base.ErroUsuario(f"Não encontrei {exe}")
    acao = d.get("acao")
    args = []
    if acao == "abrir_modo":
        args = ["--abrir"]
    elif acao == "verificar":
        arq = base.dialogo("abrir", "Squad para verificar (FC 26 ou FC 27)", d.get("inicial") or os.path.expandvars(r"%LOCALAPPDATA%\EA SPORTS FC 27\settings"))
        if not arq:
            return {"cancelado": True}
        args = ["--verificar", arq] + (["--teste-gravacao"] if d.get("teste") else [])
    elif acao in ("importar_banco", "importar_idioma"):
        pasta = base.dialogo("pasta", "Pasta com o fifa_ng_db.db e o meta do FC 27" if acao == "importar_banco"
                             else "Pasta com LanguageStrings1.txt e LanguageStrings2.txt do FC 27", d.get("inicial") or RAIZ)
        if not pasta:
            return {"cancelado": True}
        args = ["--importar-banco" if acao == "importar_banco" else "--importar-idioma", pasta]
    elif acao != "abrir":
        raise base.ErroUsuario("Ação desconhecida.")
    # o RDBM não entra no Job: continua aberto mesmo se o Super Tool for fechado
    p = subprocess.Popen([exe] + args, cwd=f["pasta"])
    if acao in ("verificar", "importar_banco", "importar_idioma"):
        try:
            p.wait(timeout=600)
        except subprocess.TimeoutExpired:
            pass
    return api_rdbm_info({})


# ------------------------------------------------------------------ dados do jogo (banco e idioma compartilhados)
def api_dados(_):
    return dados.estado()


def _dados(fn, *a, **k):
    try:
        return fn(*a, **k)
    except dados.ErroDados as ex:
        raise base.ErroUsuario(str(ex))


def api_dados_banco(d):
    caminho = d.get("caminho")
    if not caminho:
        if d.get("modo") == "pasta":
            caminho = base.dialogo("pasta", "Pasta com as tabelas .txt exportadas do banco", d.get("inicial") or RAIZ)
        else:
            caminho = base.dialogo("abrir", "Banco do jogo (fifa_ng_db.db — o meta .xml precisa estar na mesma pasta)",
                                   d.get("inicial") or RAIZ, tipos=[("Banco t3db", "*.db"), ("Todos", "*.*")])
        if not caminho:
            return {"cancelado": True, **dados.estado()}
    return _dados(dados.importar_banco, caminho, jogo=d.get("jogo"))


def api_dados_idioma(d):
    caminhos = d.get("caminhos")
    if not caminhos:
        if d.get("modo") == "pasta":
            p = base.dialogo("pasta", "Pasta com LanguageStrings1.txt e LanguageStrings2.txt", d.get("inicial") or RAIZ)
            caminhos = [p] if p else None
        else:
            caminhos = base.dialogo("abrir", "LanguageStrings*.txt (exportados pelo FET) ou o .db de idioma", d.get("inicial") or RAIZ,
                                    tipos=[("Idioma", "*.txt *.db"), ("Todos", "*.*")], multiplo=True)
        if not caminhos:
            return {"cancelado": True, **dados.estado()}
    return _dados(dados.importar_idioma, caminhos)


def api_dados_jogo(d):
    if d.get("jogo") not in ("fc26", "fc27"):
        raise base.ErroUsuario("Jogo inválido.")
    return _dados(dados.definir_jogo, d["jogo"])


def api_dados_internationals(d):
    caminho = d.get("caminho")
    if not caminho:
        caminho = base.dialogo("abrir", "internationals.txt do jogo (seleções do modo carreira)", d.get("inicial") or RAIZ,
                               tipos=[("internationals", "*.txt *.ini"), ("Todos", "*.*")])
        if not caminho:
            return {"cancelado": True, **dados.estado()}
    return _dados(dados.importar_internationals, caminho)


def api_dados_remover(d):
    if d.get("qual") not in ("banco", "idioma", "internationals"):
        raise base.ErroUsuario("Opção inválida.")
    return dados.remover(d["qual"])


def api_dados_tabelas(_):
    b = dados.banco_atual()
    if not b:
        raise base.ErroUsuario("Nenhum banco importado.")
    return {"tabelas": [{"nome": n, "registros": r, "campos": c} for n, r, c in b.nomes()]}


def api_dados_tabela(q):
    b = dados.banco_atual()
    if not b:
        raise base.ErroUsuario("Nenhum banco importado.")
    t = _dados(b.tabela, q["nome"])
    linhas = t.linhas
    busca = (q.get("busca") or "").strip().lower()
    if busca:
        linhas = [l for l in linhas if any(busca in v.lower() for v in l)]
    ini, n = int(q.get("ini") or 0), min(500, int(q.get("n") or 200))
    return {"nome": t.nome, "campos": t.campos, "total": len(t.linhas), "achadas": len(linhas), "ini": ini,
            "linhas": linhas[ini:ini + n], "info": t.info}


def api_dados_times(_):
    b = dados.banco_atual()
    if not b:
        raise base.ErroUsuario("Nenhum banco importado.")
    return {"times": _dados(b.times, dados.idioma_atual())}


def api_dados_jogadores(q):
    b = dados.banco_atual()
    if not b:
        raise base.ErroUsuario("Nenhum banco importado.")
    return {"jogadores": _dados(b.jogadores_do_time, q["teamid"])}


# ------------------------------------------------------------------ componentes (Python embutido, pacotes, programas) e pacote
def api_componentes(_):
    e = componentes.estado(addon_dir=rdbm()["pasta"])
    e["pacote"] = dict(pacote.ESTADO)
    e["supertool"] = AQUI
    return e


def api_componentes_instalar(d):
    tipo = d.get("tipo") or "pacotes"
    if tipo not in ("pacotes", "python"):
        raise base.ErroUsuario("Tipo inválido.")
    try:
        return {"tarefa": componentes.iniciar(d.get("ids") or ["tudo"], tipo=tipo, forcar=bool(d.get("forcar")))}
    except componentes.ErroComponente as ex:
        raise base.ErroUsuario(str(ex))


def api_componentes_local(d):
    """Escolher (ou esquecer) o caminho de um programa: Blender (componentes_locais.json) ou RDBM 26 (addon.ini do add-on)."""
    prog = d.get("programa")
    if prog == "blender":
        if d.get("limpar"):
            componentes.gravar_locais(blender=None)
        else:
            atual = (componentes.achar_blender() or {}).get("exe")
            exe = base.dialogo("abrir", "Escolha o blender.exe (Blender 5.2)", atual or os.environ.get("ProgramFiles", RAIZ),
                               tipos=[("Blender", "blender.exe"), ("Programas", "*.exe")])
            if not exe:
                return {"cancelado": True}
            if os.path.basename(exe).lower() != "blender.exe":
                raise base.ErroUsuario("Escolha o blender.exe da pasta do Blender.")
            componentes.gravar_locais(blender=exe)
    elif prog == "rdbm":
        pasta = base.dialogo("pasta", "Pasta do RDBM 26 (a que tem o RDBM26.exe)",
                             componentes.achar_rdbm(rdbm()["pasta"]) or os.environ.get("ProgramFiles(x86)", RAIZ))
        if not pasta:
            return {"cancelado": True}
        if not os.path.isfile(os.path.join(pasta, "RDBM26.exe")):
            raise base.ErroUsuario("Essa pasta não tem o RDBM26.exe.")
        gravar_ini_rdbm("rdbm_dir", pasta)
    else:
        raise base.ErroUsuario("Programa desconhecido.")
    return api_componentes({})


def gravar_ini_rdbm(chave, valor):
    """Troca uma linha do addon.ini do add-on (o add-on cria o resto com os padrões dele)."""
    ini = os.path.join(rdbm()["pasta"], "addon.ini")
    linhas = []
    try:
        with open(ini, encoding="utf-8-sig") as fh:
            linhas = fh.read().splitlines()
    except OSError:
        linhas = ["# RDBM 26 - Add-on FC 27"]
    feito = False
    for i, l in enumerate(linhas):
        if l.strip().lower().startswith(chave + "="):
            linhas[i] = f"{chave}={valor}"
            feito = True
    if not feito:
        linhas.append(f"{chave}={valor}")
    with open(ini, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n")


def api_pacote_resumo(_):
    try:
        return pacote.resumo()
    except componentes.ErroComponente as ex:
        raise base.ErroUsuario(str(ex))


def api_pacote_gerar(d):
    tipo = d.get("tipo")
    if tipo not in ("completo", "leve"):
        raise base.ErroUsuario("Tipo de pacote inválido.")
    destino = base.dialogo("pasta", f"Onde gravar o pacote {tipo} do BRFP Super Tool (.zip)", PREFS.ler().get("pacote_destino") or RAIZ)
    if not destino:
        return {"cancelado": True, "pacote": dict(pacote.ESTADO)}
    if os.path.normcase(os.path.abspath(destino) + os.sep).startswith(os.path.normcase(AQUI + os.sep)):
        raise base.ErroUsuario("Escolha uma pasta fora da pasta do Super Tool (o pacote não pode ficar dentro dele mesmo).")
    PREFS.atualizar(pacote_destino=destino)
    return {"pacote": pacote.iniciar(tipo, destino)}


def api_pacote_abrir(_):
    a = pacote.ESTADO.get("arquivo")
    if not a or not os.path.isfile(a):
        raise base.ErroUsuario("Nenhum pacote gerado ainda.")
    base.abrir_no_explorer(a, selecionar=True)
    return {}


# ------------------------------------------------------------------ atualização (Releases do GitHub)
def api_atualizacao(q):
    return atualizacao.verificar(VERSAO, forcar=bool(q.get("forcar")))


def api_atualizar(_):
    try:
        return {"estado": atualizacao.iniciar()}
    except RuntimeError as ex:
        raise base.ErroUsuario(str(ex))


def api_atualizar_estado(_):
    return {"estado": dict(atualizacao.ESTADO)}


# ------------------------------------------------------------------ servidorROTAS_GET = {"componentes": api_componentes, "pacote_resumo": api_pacote_resumo, "dados": api_dados, "dados_tabelas": api_dados_tabelas, "dados_tabela": api_dados_tabela,
             "dados_times": api_dados_times, "dados_jogadores": api_dados_jogadores, "inicio": api_inicio, "ferramentas": api_ferramentas, "log": api_log, "guia": api_guia,
             "rdbm": api_rdbm_info, "atualizacao": api_atualizacao, "atualizar_estado": api_atualizar_estado, "versao": lambda _: {"versao": VERSAO, "app": NOME}}
ROTAS_POST = {"componentes_instalar": api_componentes_instalar, "componentes_local": api_componentes_local,
              "pacote_gerar": api_pacote_gerar, "pacote_abrir": api_pacote_abrir, "dados_banco": api_dados_banco, "dados_idioma": api_dados_idioma, "dados_internationals": api_dados_internationals, "dados_jogo": api_dados_jogo,
              "dados_remover": api_dados_remover, "iniciar": api_iniciar, "parar": api_parar, "reiniciar": api_reiniciar, "abrir_pasta": api_abrir_pasta,
              "rdbm": api_rdbm, "lembrar": api_lembrar, "atualizar": api_atualizar}


def ja_aberto(porta):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/versao", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == NOME
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser(description=NOME)
    ap.add_argument("--porta", type=int, default=8760)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("--abrir", help="id da ferramenta para abrir direto (estadios, placares, compdata, faces, corpos, conversor_pes)")
    a = ap.parse_args()
    url_extra = f"#{a.abrir}" if a.abrir else ""
    if not a.sem_janela and ja_aberto(a.porta):
        # já está aberto: só mostra outra janela
        base.abrir_janela(f"http://127.0.0.1:{a.porta}/{url_extra}", os.path.join(AQUI, ".perfil_janela"))
        print(f"{NOME} já está aberto em http://127.0.0.1:{a.porta}/ — abri outra janela.")
        return
    import atexit
    atexit.register(lambda: [fl.parar() for fl in FILHOS.values()])
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, nome="BRFPSuperTool/" + VERSAO)
    print(f"Pasta de trabalho: {RAIZ}", flush=True)
    py = componentes.python_embutido()
    print(f"Python: {sys.version.split()[0]} ({'embutido' if py['em_uso'] else sys.executable})", flush=True)
    base.servir(handler, a.porta, NOME, VERSAO, sem_janela=a.sem_janela, perfil=os.path.join(AQUI, ".perfil_janela"),
                sufixo=url_extra)


if __name__ == "__main__":
    main()
