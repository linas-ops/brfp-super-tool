"""BRFP Super Tool — componentes: Python embutido, pacotes do PyPI e programas externos (só biblioteca padrão).

    runtime/python/                    Python 3.12 portátil (python.org, pacote "embeddable"). Isolado: não lê
                                       variáveis PYTHON* nem pacotes do usuário (python312._pth sem "import site")
    runtime/python/Lib/site-packages/  numpy, SciPy, OpenCV e Pillow (rodas do PyPI extraídas, sem as pastas de testes)
    runtime/downloads/                 downloads em andamento (apagados ao terminar)
    comum/componentes.json             versões fixas, endereços e SHA-256 de tudo que é baixado
    componentes_locais.json            caminhos escolhidos nesta máquina (Blender) — não vai no pacote

Linha de comando:
    python componentes.py estado
    python componentes.py instalar faces corpos minifaces | numpy scipy opencv pillow | tudo
    python componentes.py python            baixa o Python embutido (se ainda não existir)
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

COMUM = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(COMUM)
RUNTIME = os.environ.get("BRFP_RUNTIME") or os.path.join(SUPERTOOL, "runtime")
PYDIR = os.path.join(RUNTIME, "python")
PYEXE = os.path.join(PYDIR, "python.exe")
SITE = os.path.join(PYDIR, "Lib", "site-packages")
DOWNLOADS = os.path.join(RUNTIME, "downloads")
TRAVA = os.path.join(RUNTIME, ".instalando")
LOCAIS = os.path.join(SUPERTOOL, "componentes_locais.json")
PTH = "python312.zip\n.\nLib\\site-packages\n"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_LOCK = threading.RLock()
_MANIFESTO = None
_PYTHON_GRUPO = {}                     # grupo -> (cmd, descrição) já verificado
TAREFA = {"ativa": False, "tipo": None, "ids": [], "fase": "", "atual": None, "baixado": 0, "total": 0, "msg": "",
          "erro": None, "fim": 0, "seq": 0}
AO_CONCLUIR = []                       # funções chamadas depois de uma instalação bem-sucedida


class ErroComponente(Exception):
    pass


def manifesto():
    global _MANIFESTO
    if _MANIFESTO is None:
        with open(os.path.join(COMUM, "componentes.json"), encoding="utf-8") as f:
            _MANIFESTO = json.load(f)
    return _MANIFESTO


def ler_locais():
    try:
        with open(LOCAIS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def gravar_locais(**kw):
    d = ler_locais()
    d.update({k: v for k, v in kw.items()})
    d = {k: v for k, v in d.items() if v}
    tmp = LOCAIS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LOCAIS)
    return d


def mb(n):
    return f"{n / 1048576:.0f} MB" if n >= 1048576 else f"{max(1, n // 1024)} KB"


# ------------------------------------------------------------------ Python embutido e pacotes
def no_embutido():
    """O processo atual roda no Python embutido do Super Tool?"""
    try:
        return os.path.normcase(os.path.abspath(sys.executable)) == os.path.normcase(os.path.abspath(PYEXE))
    except (TypeError, ValueError):
        return False


def python_embutido():
    m = manifesto()["python"]
    ok = os.path.isfile(PYEXE) and os.path.isfile(os.path.join(PYDIR, "python312.dll"))
    versao = None
    try:
        with open(os.path.join(PYDIR, "brfp-runtime.json"), encoding="utf-8") as f:
            versao = json.load(f).get("versao")
    except (OSError, ValueError):
        versao = m["versao"] if ok else None
    return {"ok": ok, "versao": versao, "caminho": PYDIR, "esperada": m["versao"], "tamanho": m["tamanho"],
            "em_uso": no_embutido()}


def pacotes_instalados():
    """{id: versão} dos pacotes do manifesto presentes em runtime/python/Lib/site-packages."""
    out = {}
    try:
        nomes = os.listdir(SITE)
    except OSError:
        return out
    for pid, p in manifesto()["pacotes"].items():
        rx = re.compile(r"^%s-(.+)\.dist-info$" % re.escape(p["distribuicao"]), re.I)
        mod = os.path.join(SITE, p["modulo"])
        for n in nomes:
            m = rx.match(n)
            if m and (os.path.isfile(mod) if p["modulo"].endswith(".py") else os.path.isdir(mod)):
                out[pid] = m.group(1)
                break
    return out


def caminho_projeto(pid):
    return os.path.join(RUNTIME, *manifesto()["projetos"][pid]["pasta"].split("/"))


def projetos_instalados():
    """{id: versão} dos projetos (código-fonte de terceiros, ex.: transfermarkt-api) extraídos em runtime/."""
    out = {}
    for pid in manifesto().get("projetos", {}):
        try:
            with open(os.path.join(caminho_projeto(pid), "brfp-projeto.json"), encoding="utf-8") as f:
                out[pid] = json.load(f).get("versao")
        except (OSError, ValueError):
            pass
    return out


def projetos_de(ids):
    proj = manifesto().get("projetos", {})
    grupos = manifesto()["grupos"]
    out = []
    for i in ids:
        lst = list(proj) if i == "tudo" else grupos[i].get("projetos", []) if i in grupos else [i] if i in proj else []
        out += [x for x in lst if x not in out]
    return out


def com_dependencias(ids):
    pac = manifesto()["pacotes"]
    grupos = manifesto()["grupos"]
    fila, out = [], []
    for i in ids:
        if i == "tudo":
            fila += list(pac)
        elif i in grupos:
            fila += grupos[i]["pacotes"]
        elif i in pac:
            fila.append(i)
        elif i in manifesto().get("projetos", {}):
            continue
        else:
            raise ErroComponente(f"Componente desconhecido: {i}")

    def add(i):
        for r in pac[i].get("requer", []):
            add(r)
        if i not in out:
            out.append(i)
    for i in fila:
        add(i)
    return out


def estado_grupo(grupo):
    g = manifesto()["grupos"][grupo]
    inst = pacotes_instalados()
    pac = manifesto()["pacotes"]
    faltam = [i for i in g["pacotes"] if i not in inst]
    velhos = [i for i in g["pacotes"] if i in inst and inst[i] != pac[i]["versao"]]
    proj = manifesto().get("projetos", {})
    pinst = projetos_instalados()
    faltam_proj = [i for i in g.get("projetos", []) if pinst.get(i) != proj[i]["versao"]]
    return {"id": grupo, "nome": g["nome"], "pacotes": g["pacotes"], "projetos": g.get("projetos", []),
            "ok": not faltam and not faltam_proj and python_embutido()["ok"], "faltam": faltam, "desatualizados": velhos,
            "faltam_projetos": faltam_proj, "resumo": g.get("resumo"), "usado_por": g.get("usado_por"),
            "download": sum(pac[i]["tamanho"] for i in faltam + velhos) + sum(proj[i]["tamanho"] for i in faltam_proj),
            "python": python_embutido()["ok"]}


def python_para(grupo, forcar=False):
    """Comando do Python que tem os pacotes do grupo: o embutido; senão um do computador (py -3.12…).
    Devolve (cmd, descrição) ou (None, ""). O teste dos Pythons do computador fica guardado até forcar=True."""
    if estado_grupo(grupo)["ok"]:
        return [PYEXE], "Python embutido " + (python_embutido()["versao"] or "")
    with _LOCK:
        if not forcar and grupo in _PYTHON_GRUPO:
            return _PYTHON_GRUPO[grupo]
        mods = [manifesto()["pacotes"][i]["modulo"] for i in manifesto()["grupos"][grupo]["pacotes"]]
        r = (None, "")
        for cmd in ([sys.executable], ["py", "-3.12"], ["python3.12"]):
            if os.path.normcase(os.path.abspath(cmd[0])) == os.path.normcase(PYEXE):
                continue
            try:
                p = subprocess.run(cmd + ["-c", "import sys, %s; print(sys.version.split()[0])" % ", ".join(mods)],
                                   capture_output=True, text=True, timeout=90, creationflags=SEM_JANELA)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if p.returncode == 0:
                r = (cmd, "Python %s do computador" % p.stdout.strip())
                break
        _PYTHON_GRUPO[grupo] = r
        return r


def falta_msg(grupo):
    g = estado_grupo(grupo)
    nomes = ", ".join(manifesto()["pacotes"][i]["nome"] for i in g["faltam"] or g["pacotes"])
    if g["ok"] and not no_embutido():
        return (f"O {g['nome']} precisa de {nomes}, que já está no Python embutido do Super Tool: abra pelo "
                "BRFP Super Tool.bat (este Python não tem).")
    return (f"O {g['nome']} precisa de {nomes} ({mb(g['download'])}). Use \"Instalar componentes\" (ou a página "
            "Componentes do Super Tool) para baixar.")


# ------------------------------------------------------------------ download e instalação
def _trava():
    """Trava entre processos (hub e ferramentas podem pedir instalações ao mesmo tempo)."""
    os.makedirs(RUNTIME, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(TRAVA, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "inicio": time.time()}).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                with open(TRAVA, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                d = {}
            if time.time() - d.get("inicio", 0) > 3600 or not _processo_vivo(d.get("pid")):
                try:
                    os.remove(TRAVA)
                except OSError:
                    pass
                continue
            raise ErroComponente("Outra instalação de componentes está em andamento. Aguarde ela terminar.")
    raise ErroComponente("Não foi possível iniciar a instalação (trava em runtime\\.instalando).")


def _processo_vivo(pid):
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k = ctypes.WinDLL("kernel32")
    h = k.OpenProcess(0x1000, False, int(pid))       # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    cod = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(cod))
    k.CloseHandle(h)
    return cod.value == 259                          # STILL_ACTIVE


_ULTIMA_TRAVA = [0.0]


def _anotar_trava(**kw):
    """Grava o progresso na trava (no máximo 3x por segundo) para outros processos mostrarem."""
    agora = time.time()
    if agora - _ULTIMA_TRAVA[0] < 0.3 and kw.get("fase") == "baixando":
        return
    _ULTIMA_TRAVA[0] = agora
    try:
        with open(TRAVA, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("pid") != os.getpid():
            return
        d.update(kw)
        with open(TRAVA, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except (OSError, ValueError):
        pass


def instalacao_externa():
    """Instalação em andamento em outro processo (hub ou outra ferramenta), lida da trava."""
    try:
        with open(TRAVA, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if d.get("pid") == os.getpid() or not _processo_vivo(d.get("pid")):
        return None
    return {"ativa": True, "externa": True, "fase": d.get("fase", "baixando"), "msg": d.get("msg", "Instalando componentes…"),
            "baixado": d.get("baixado", 0), "total": d.get("total", 0), "erro": None, "ids": d.get("ids", []),
            "tipo": d.get("tipo"), "seq": 0, "fim": 0, "atual": d.get("atual")}


def tarefa_publica():
    if TAREFA["ativa"] or TAREFA["fim"]:
        return dict(TAREFA)
    return instalacao_externa() or dict(TAREFA)


def _soltar():
    try:
        os.remove(TRAVA)
    except OSError:
        pass


def baixar(item, progresso=None):
    """Baixa item (url, arquivo, sha256, tamanho) para runtime/downloads e confere. Devolve o caminho."""
    os.makedirs(DOWNLOADS, exist_ok=True)
    final = os.path.join(DOWNLOADS, item["arquivo"])
    if os.path.isfile(final) and _sha256(final) == item["sha256"]:
        if progresso:
            progresso(item["tamanho"], item["tamanho"])
        return final
    parcial = final + ".parcial"
    ultimo = None
    for tentativa in range(3):
        try:
            req = urllib.request.Request(item["url"], headers={"User-Agent": "BRFP-Super-Tool"})
            h = hashlib.sha256()
            n = 0
            with urllib.request.urlopen(req, timeout=60) as r, open(parcial, "wb") as f:
                total = int(r.headers.get("Content-Length") or item.get("tamanho") or 0)
                while True:
                    bloco = r.read(262144)
                    if not bloco:
                        break
                    f.write(bloco)
                    h.update(bloco)
                    n += len(bloco)
                    if progresso:
                        progresso(n, total)
            if h.hexdigest() != item["sha256"]:
                raise ErroComponente(f"{item['arquivo']}: o arquivo baixado não confere (SHA-256 diferente). "
                                     "Tente de novo; se repetir, a conexão pode estar alterando o download.")
            os.replace(parcial, final)
            return final
        except ErroComponente:
            _remover(parcial)
            raise
        except (OSError, ValueError) as ex:        # urllib.error.URLError é OSError
            ultimo = ex
            _remover(parcial)
            time.sleep(1.5 * (tentativa + 1))
    raise ErroComponente(f"Não foi possível baixar {item['arquivo']}: {getattr(ultimo, 'reason', None) or ultimo}. "
                         "Verifique a conexão com a internet.")


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1048576), b""):
            h.update(bloco)
    return h.hexdigest()


def _remover(caminho):
    try:
        if os.path.isdir(caminho) and not os.path.islink(caminho):
            shutil.rmtree(caminho)
        elif os.path.exists(caminho):
            os.remove(caminho)
    except OSError:
        pass


MAIOR_MEMBRO = 100                     # maior caminho dentro dos pacotes (numpy.libs/libopenblas…dll = 95)


def _longo(caminho):
    c = os.path.abspath(caminho)
    return "\\\\?\\" + c if os.name == "nt" and not c.startswith("\\\\") else c


def caminhos_longos():
    """O Windows aceita caminhos com mais de 260 caracteres (LongPathsEnabled)?"""
    if os.name != "nt":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return int(winreg.QueryValueEx(k, "LongPathsEnabled")[0]) == 1
    except (OSError, ValueError):
        return False


def problema_caminho():
    """Mensagem se a pasta do Super Tool estiver funda demais para os pacotes (limite de 260 do Windows)."""
    n = len(os.path.abspath(SITE)) + 1 + MAIOR_MEMBRO
    if n < 260 or caminhos_longos():
        return None
    return (f"A pasta do Super Tool está num caminho longo demais ({len(os.path.abspath(RUNTIME))} caracteres até runtime) para os pacotes do "
            f"Python: o Windows limita os caminhos a 260 caracteres. Mova a pasta \"BRFP Super Tool\" para um lugar mais "
            f"curto (ex.: C:\\BRFP Super Tool ou Documentos) e abra de novo.")


def _membro_destino(nome, omitir=()):
    """Caminho relativo dentro de site-packages para um membro da roda, ou None para pular."""
    partes = nome.split("/")
    if not partes[-1]:
        return None
    if partes[0].endswith(".data"):
        if len(partes) > 2 and partes[1] in ("purelib", "platlib"):
            partes = partes[2:]
        else:
            return None                              # scripts, headers, data: não usados
    if "tests" in partes[:-1] or "__pycache__" in partes:
        return None
    rel = "/".join(partes)
    if len(partes) == 1 and rel.endswith(".whl"):     # o delvewheel deixa uma cópia vazia do nome da roda
        return None
    if any(rel.startswith(o) for o in omitir):
        return None
    return rel


def instalar_roda(roda, pid):
    """Extrai a roda em site-packages (troca a versão anterior do mesmo pacote)."""
    p = manifesto()["pacotes"][pid]
    os.makedirs(SITE, exist_ok=True)
    temp = _longo(os.path.join(SITE, f".i-{pid}"))
    _remover(temp)
    with zipfile.ZipFile(roda) as z:
        topos = set()
        for info in z.infolist():
            rel = _membro_destino(info.filename, p.get("omitir", ()))
            if not rel:
                continue
            alvo = os.path.join(temp, *rel.split("/"))
            if not os.path.normpath(alvo).startswith(temp + os.sep):
                raise ErroComponente(f"{os.path.basename(roda)}: caminho inválido dentro do pacote ({info.filename}).")
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with z.open(info) as src, open(alvo, "wb") as dst:
                shutil.copyfileobj(src, dst, 1048576)
            topos.add(rel.split("/")[0])
    # versão anterior: dist-info do mesmo pacote e as pastas de nível superior que a roda nova traz
    rx = re.compile(r"^%s-.+\.dist-info$" % re.escape(p["distribuicao"]), re.I)
    site = _longo(SITE)
    velhos = [n for n in os.listdir(site) if rx.match(n)] + [t for t in topos if os.path.exists(os.path.join(site, t))]
    for n in set(velhos):
        alvo = os.path.join(site, n)
        try:
            if os.path.isdir(alvo):
                shutil.rmtree(alvo)
            else:
                os.remove(alvo)
        except OSError as ex:
            _remover(temp)
            raise ErroComponente(f"Não foi possível trocar {n} ({ex.strerror or ex}). Feche as ferramentas que usam "
                                 f"{p['nome']} (Faces, Minifaces) e tente de novo.")
    for t in topos:
        os.replace(os.path.join(temp, t), os.path.join(site, t))
    _remover(temp)


def instalar(ids, progresso=None, forcar=False):
    """Baixa e instala os pacotes (ids = grupos, pacotes ou 'tudo'). progresso(fase, id, feito, total, msg)."""
    if not python_embutido()["ok"]:
        raise ErroComponente("O Python embutido ainda não foi baixado (runtime\\python). Abra o Super Tool pelo "
                             "BRFP Super Tool.bat, que oferece o download, ou use \"Baixar Python\" em Componentes.")
    pac = manifesto()["pacotes"]
    proj = manifesto().get("projetos", {})
    lista = com_dependencias(ids)
    projs = projetos_de(ids)
    inst = pacotes_instalados()
    pinst = projetos_instalados()
    if not forcar:
        lista = [i for i in lista if inst.get(i) != pac[i]["versao"]]
        projs = [i for i in projs if pinst.get(i) != proj[i]["versao"]]
    if not lista and not projs:
        return []
    _verificar_gravavel()
    if problema_caminho():
        raise ErroComponente(problema_caminho())
    _trava()
    try:
        total = sum(pac[i]["tamanho"] for i in lista) + sum(proj[i]["tamanho"] for i in projs)
        antes = 0
        rodas = {}
        for i in lista + projs:
            item = pac.get(i) or proj[i]

            def prog(n, t, i=i, antes=antes, item=item):
                if progresso:
                    progresso("baixando", i, antes + n, total, f"Baixando {item['nome']} {item['versao']}")
            rodas[i] = baixar(item, prog)
            antes += item["tamanho"]
        for k, i in enumerate(lista + projs):
            if progresso:
                progresso("instalando", i, k, len(lista) + len(projs), f"Instalando {(pac.get(i) or proj[i])['nome']}")
            if i in proj:
                instalar_projeto(rodas[i], i)
            else:
                instalar_roda(rodas[i], i)
        for i in lista + projs:
            _remover(rodas[i])
        if os.path.isdir(DOWNLOADS) and not os.listdir(DOWNLOADS):
            _remover(DOWNLOADS)
        _PYTHON_GRUPO.clear()
        return lista + projs
    finally:
        _soltar()


def instalar_projeto(arquivo, pid):
    """Código-fonte de um projeto (zip do GitHub, "<projeto>-<versão>/..."): só as partes listadas em "incluir" vão
    para runtime/<pasta> (troca a versão anterior inteira)."""
    p = manifesto()["projetos"][pid]
    destino = caminho_projeto(pid)
    novo = destino + ".novo"
    _remover(novo)
    with zipfile.ZipFile(arquivo) as z:
        for info in z.infolist():
            partes = info.filename.split("/", 1)
            if len(partes) < 2 or not partes[1] or info.filename.endswith("/"):
                continue
            rel = partes[1]
            if not any(rel == inc or (inc.endswith("/") and rel.startswith(inc)) for inc in p["incluir"]):
                continue
            if "__pycache__" in rel.split("/"):
                continue
            alvo = os.path.join(novo, *rel.split("/"))
            if not os.path.normpath(alvo).startswith(os.path.normpath(novo) + os.sep):
                raise ErroComponente(f"{p['arquivo']}: caminho inválido dentro do arquivo ({info.filename}).")
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with z.open(info) as src, open(alvo, "wb") as dst:
                shutil.copyfileobj(src, dst, 1048576)
    # remendos (correções pequenas no código do projeto, ex.: campos de URL que derrubavam a resposta quando vazios)
    for r in p.get("remendos") or []:
        arq = os.path.join(novo, *r["arquivo"].split("/"))
        with open(arq, encoding="utf-8") as f:
            txt = f.read()
        if r["de"] not in txt and r["para"] not in txt:
            _remover(novo)
            raise ErroComponente(f"{p['nome']}: não achei o trecho a corrigir em {r['arquivo']}.")
        with open(arq, "w", encoding="utf-8", newline="") as f:
            f.write(txt.replace(r["de"], r["para"]))
    with open(os.path.join(novo, "brfp-projeto.json"), "w", encoding="utf-8") as f:
        json.dump({"versao": p["versao"], "origem": p["url"], "sha256": p["sha256"]}, f)
    if os.path.isdir(destino):
        try:
            shutil.rmtree(destino)
        except OSError as ex:
            _remover(novo)
            raise ErroComponente(f"Não foi possível trocar {destino} ({ex.strerror or ex}). Feche o Criador de Ligas e "
                                 "Times (o servidor local da Transfermarkt usa essa pasta) e tente de novo.")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    os.replace(novo, destino)


def _verificar_gravavel():
    try:
        os.makedirs(RUNTIME, exist_ok=True)
        t = os.path.join(RUNTIME, ".teste-gravacao")
        with open(t, "w") as f:
            f.write("ok")
        os.remove(t)
    except OSError:
        raise ErroComponente(f"A pasta {SUPERTOOL} não pode ser gravada. Copie o BRFP Super Tool para uma pasta sua "
                             "(ex.: Documentos ou Área de Trabalho) e abra de lá.")


def instalar_python(progresso=None):
    """Baixa o Python embutido para runtime/python (quando o Super Tool roda num Python do computador)."""
    m = manifesto()["python"]
    if python_embutido()["ok"]:
        return False
    _verificar_gravavel()
    _trava()
    try:
        zipado = baixar(m, (lambda n, t: progresso("baixando", "python", n, t, "Baixando o Python " + m["versao"]))
                        if progresso else None)
        if progresso:
            progresso("instalando", "python", 0, 1, "Instalando o Python")
        novo = PYDIR + ".novo"
        _remover(novo)
        with zipfile.ZipFile(zipado) as z:
            z.extractall(novo)
        preparar_python(novo, m)
        if os.path.isdir(os.path.join(PYDIR, "Lib")):          # pacotes já instalados antes: mantém
            shutil.move(os.path.join(PYDIR, "Lib"), os.path.join(novo, "Lib"))
        _remover(PYDIR)
        os.replace(novo, PYDIR)
        _remover(zipado)
        return True
    finally:
        _soltar()


def preparar_python(pasta, m=None):
    """._pth isolado (sem site: nem pacotes do usuário nem PYTHONPATH) + site-packages + versão."""
    m = m or manifesto()["python"]
    with open(os.path.join(pasta, m["pth"]), "w", encoding="ascii", newline="\r\n") as f:
        f.write(PTH)
    os.makedirs(os.path.join(pasta, "Lib", "site-packages"), exist_ok=True)
    with open(os.path.join(pasta, "brfp-runtime.json"), "w", encoding="utf-8") as f:
        json.dump({"versao": m["versao"], "origem": m["url"]}, f)


# ------------------------------------------------------------------ tarefa em segundo plano (para as interfaces)
def iniciar(ids=None, tipo="pacotes", forcar=False):
    with _LOCK:
        if TAREFA["ativa"]:
            return dict(TAREFA)
        if tipo == "pacotes":
            com_dependencias(ids or [])                     # valida os ids antes de começar
        TAREFA.update(ativa=True, tipo=tipo, ids=list(ids or []), fase="iniciando", atual=None, baixado=0, total=0,
                      msg="Preparando…", erro=None, fim=0, seq=TAREFA["seq"] + 1)

    def prog(fase, atual, feito, total, msg):
        TAREFA.update(fase=fase, atual=atual, baixado=feito, total=total, msg=msg)
        _anotar_trava(fase=fase, atual=atual, baixado=feito, total=total, msg=msg, tipo=tipo, ids=list(ids or []))

    def rodar():
        try:
            feitos = []
            if tipo == "python" or not python_embutido()["ok"]:
                if instalar_python(prog):
                    feitos.append("python")
            if tipo == "pacotes":
                feitos += instalar(ids, prog, forcar=forcar)
            TAREFA.update(fase="pronto", msg="Componentes instalados." if feitos else "Já estava tudo instalado.")
            for fn in list(AO_CONCLUIR):
                try:
                    fn(feitos)
                except Exception:  # noqa: BLE001
                    pass
        except ErroComponente as ex:
            TAREFA.update(fase="erro", erro=str(ex), msg=str(ex))
        except Exception as ex:  # noqa: BLE001
            TAREFA.update(fase="erro", erro=f"{type(ex).__name__}: {ex}", msg=str(ex))
        finally:
            TAREFA.update(ativa=False, fim=time.time())
    threading.Thread(target=rodar, daemon=True).start()
    return dict(TAREFA)


# ------------------------------------------------------------------ programas externos
def _pastas_programas():
    vistos, out = set(), []
    for v in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        p = os.environ.get(v)
        if p and os.path.normcase(p) not in vistos:
            vistos.add(os.path.normcase(p))
            out.append(p)
    la = os.environ.get("LOCALAPPDATA")
    if la:
        out.append(os.path.join(la, "Programs"))
    return out


def _versao_tupla(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def achar_blender():
    """Blender instalado (o escolhido em Componentes primeiro; senão o de versão mais alta)."""
    escolhido = ler_locais().get("blender")
    cands = []
    if escolhido and os.path.isfile(escolhido):
        cands.append(((9999,), escolhido))
    for base in _pastas_programas():
        for d in glob.glob(os.path.join(base, "Blender Foundation", "Blender*")):
            exe = os.path.join(d, "blender.exe")
            if os.path.isfile(exe):
                cands.append((_versao_tupla(os.path.basename(d)), exe))
    steam = _steam()
    if steam:
        exe = os.path.join(steam, "steamapps", "common", "Blender", "blender.exe")
        if os.path.isfile(exe):
            cands.append(((0,), exe))
    if not cands:
        return None
    exe = max(cands)[1]
    pasta = os.path.dirname(exe)
    versoes = sorted((d for d in os.listdir(pasta) if re.fullmatch(r"\d+\.\d+", d)), key=_versao_tupla)
    ver = versoes[-1] if versoes else ""
    py = os.path.join(pasta, ver, "python", "bin", "python.exe") if ver else ""
    return {"exe": exe, "versao": ver, "python": py if os.path.isfile(py) else ""}


def _steam():
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return winreg.QueryValueEx(k, "SteamPath")[0]
    except OSError:
        return None


def achar_navegador():
    if os.name != "nt":
        return None
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
        for rel, nome in ((r"Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
                          (r"Google\Chrome\Application\chrome.exe", "Google Chrome")):
            exe = os.path.join(base, rel)
            if base and os.path.isfile(exe):
                return {"exe": exe, "nome": nome}
    return None


def dotnet48():
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as k:
            return int(winreg.QueryValueEx(k, "Release")[0]) >= 528040
    except (OSError, ValueError):
        return False


def vcredist():
    """Visual C++ 2015–2022 (x64): o texconv precisa (msvcp140, vcomp140). O Python embutido e os pacotes não."""
    s = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    return all(os.path.isfile(os.path.join(s, n)) for n in ("msvcp140.dll", "vcomp140.dll", "vcruntime140.dll"))


def achar_rdbm(addon_dir=None):
    cands = []
    if addon_dir:
        try:
            with open(os.path.join(addon_dir, "addon.ini"), encoding="utf-8-sig") as f:
                for linha in f:
                    if linha.strip().lower().startswith("rdbm_dir="):
                        cands.append(linha.split("=", 1)[1].strip())
        except OSError:
            pass
    for base in _pastas_programas():
        cands.append(os.path.join(base, "RDBM26"))
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "RDBM26.exe")):
            return c
    return None


def texconv():
    return os.path.join(SUPERTOOL, "ferramentas", "estadios", "ferramentas", "texconv.exe")


def programas(addon_dir=None):
    bl = achar_blender()
    nav = achar_navegador()
    rd = achar_rdbm(addon_dir)
    tx = texconv()
    return [
        {"id": "navegador", "nome": "Navegador da janela", "ok": bool(nav), "caminho": nav["exe"] if nav else "",
         "detalhe": nav["nome"] if nav else "sem Edge/Chrome: abre no navegador padrão", "usado": "Super Tool",
         "obrigatorio": False},
        {"id": "texconv", "nome": "texconv (DirectXTex)", "ok": os.path.isfile(tx), "caminho": tx, "detalhe": "embutido",
         "usado": "Editor de Estádios, Conversor PES → FC", "obrigatorio": True},
        {"id": "vcredist", "nome": "Visual C++ 2015–2022 (x64)", "ok": vcredist(), "caminho": "",
         "detalhe": "instalado" if vcredist() else "não encontrado", "usado": "texconv (texturas do Editor de Estádios e do Conversor PES)",
         "obrigatorio": False, "link": "https://aka.ms/vs/17/release/vc_redist.x64.exe"},
        {"id": "blender", "nome": "Blender 5.2", "ok": bool(bl), "caminho": bl["exe"] if bl else "",
         "detalhe": ("versão " + bl["versao"]) if bl and bl["versao"] else "não encontrado",
         "aviso": bool(bl) and _versao_tupla(bl["versao"]) < (5, 2),
         "usado": "Conversor PES → FC", "obrigatorio": False, "link": "https://www.blender.org/download/",
         "localizar": True},
        {"id": "rdbm", "nome": "RDBM 26", "ok": bool(rd), "caminho": rd or "", "detalhe": "instalado" if rd else "não encontrado",
         "usado": "RDBM 26 · Add-on FC 27", "obrigatorio": False, "localizar": True},
        {"id": "dotnet", "nome": ".NET Framework 4.8", "ok": dotnet48(), "caminho": "",
         "detalhe": "do Windows" if dotnet48() else "não encontrado", "usado": "RDBM 26 · Add-on FC 27",
         "obrigatorio": False, "link": "https://dotnet.microsoft.com/download/dotnet-framework/net48"},
    ]


def estado(addon_dir=None, com_programas=True):
    pac = manifesto()["pacotes"]
    inst = pacotes_instalados()
    return {
        "python": python_embutido(),
        "python_atual": {"caminho": sys.executable, "versao": sys.version.split()[0]},
        "pacotes": [{"id": i, "nome": p["nome"], "versao": p["versao"], "instalado": inst.get(i), "tamanho": p["tamanho"]}
                    for i, p in pac.items()],
        "projetos": [{"id": i, "nome": p["nome"], "versao": p["versao"], "instalado": projetos_instalados().get(i),
                      "tamanho": p["tamanho"], "origem": p.get("origem")} for i, p in manifesto().get("projetos", {}).items()],
        "grupos": {g: estado_grupo(g) for g in manifesto()["grupos"]},
        "programas": programas(addon_dir) if com_programas else [],
        "tarefa": tarefa_publica(),
        "runtime": RUNTIME,
        "problema": problema_caminho(),
    }


# ------------------------------------------------------------------ linha de comando
def _barra(fase, atual, feito, total, msg):
    if fase == "baixando" and total:
        pct = feito * 100 // total
        sys.stdout.write(f"\r  {msg[:46]:46s} {pct:3d}%  {mb(feito):>7s} de {mb(total)}   ")
    else:
        sys.stdout.write(f"\r  {msg[:46]:46s}{' ' * 30}\n")
    sys.stdout.flush()


def main(argv):
    if not argv or argv[0] not in ("estado", "instalar", "python"):
        print(__doc__)
        return 2
    try:
        if argv[0] == "estado":
            print(json.dumps(estado(), ensure_ascii=False, indent=1))
        elif argv[0] == "python":
            print("Python embutido:", "baixado" if instalar_python(_barra) else "já existe")
        else:
            ids = [a for a in argv[1:] if not a.startswith("--")]
            feitos = instalar(ids or ["tudo"], _barra, forcar="--forcar" in argv)
            print("\nInstalados: " + (", ".join(feitos) if feitos else "nada (já estava tudo instalado)"))
    except ErroComponente as ex:
        print("\nERRO: " + str(ex))
        return 1
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main([a for a in sys.argv[1:]]))
