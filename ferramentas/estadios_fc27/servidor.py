"""Estádios FC 27 (BRFP Super Tool): duplicar estádios e converter estádios do FIFA 16, num servidor local.

    python servidor.py [--porta 8782] [--sem-janela]

O trabalho pesado roda no motor (motor/, python -m motor ...) num processo à parte, com o Python que tem os pacotes
do grupo "estadios_fc27" (numpy e zstandard): o embutido do Super Tool ou um do computador. A interface mostra as
etapas e o registro ao vivo. Uma tarefa por vez.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(SUPERTOOL, "comum"))

import base  # noqa: E402
import componentes  # noqa: E402

VERSAO = "1.0"
GRUPO = "estadios_fc27"
RAIZ = base.raiz_trabalho()
CACHE = os.path.join(AQUI, "cache")
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"))
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOCK = threading.Lock()
EXEC = {"rodando": False, "proc": None, "tarefa": None, "titulo": "", "log": [], "seq": 0, "etapas": [], "etapa": None,
        "progresso": 0, "texto": "", "avisos": [], "resultado": None, "erro": None, "inicio": 0, "fim": 0, "codigo": None}
MAX_LOG = 8000
BASE_FIFA16 = 181
# "-m motor" não serve: o Python embutido do Super Tool (python312._pth) não procura módulos na pasta atual. O motor é
# rodado como módulo com a pasta da ferramenta posta no sys.path, em qualquer Python.
MOTOR = ["-c", "import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); runpy.run_module('motor', run_name='__main__', alter_sys=True)", AQUI]


def python_motor():
    cmd, desc = componentes.python_para(GRUPO)
    if not cmd:
        raise base.ErroUsuario(componentes.falta_msg(GRUPO))
    return cmd, desc


def motor(args, timeout=600):
    """Roda um comando curto do motor e devolve o JSON que ele imprime."""
    cmd, _ = python_motor()
    p = subprocess.run(cmd + ["-X", "utf8"] + MOTOR + args, cwd=AQUI, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=SEM_JANELA, env=dict(os.environ, PYTHONUTF8="1"))
    linhas = [l for l in p.stdout.splitlines() if l.strip()]
    erro = next((l[7:] for l in linhas if l.startswith("@@ERRO ")), None)
    if erro or p.returncode:
        raise base.ErroUsuario(erro or (p.stderr or p.stdout)[-1500:] or f"o motor saiu com código {p.returncode}")
    for l in reversed(linhas):
        if l.startswith("{"):
            return json.loads(l)
    raise base.ErroUsuario("o motor não devolveu resposta")


# ------------------------------------------------------------------ tarefas longas
def registrar(linha):
    with LOCK:
        EXEC["log"].append(linha)
        EXEC["seq"] += 1
        if len(EXEC["log"]) > MAX_LOG:
            del EXEC["log"][:len(EXEC["log"]) - MAX_LOG]


def iniciar(tarefa, titulo, args, cfg=None):
    with LOCK:
        if EXEC["rodando"]:
            raise base.ErroUsuario("Já há uma tarefa rodando: espere terminar ou pare.")
    cmd, desc = python_motor()
    if cfg is not None:
        d = os.path.join(CACHE, "tarefas")
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, time.strftime("%Y%m%d_%H%M%S") + f"_{tarefa}.json")
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=1)
        args = args + [f]
    with LOCK:
        EXEC.update(rodando=True, tarefa=tarefa, titulo=titulo, log=[], seq=0, etapas=[], etapa=None, progresso=0, texto="",
                    avisos=[], resultado=None, erro=None, inicio=time.time(), fim=0, codigo=None, config=cfg)
    registrar(f"> {desc}: python -m motor " + " ".join(args))
    try:
        proc = subprocess.Popen(cmd + ["-X", "utf8", "-u"] + MOTOR + args, cwd=AQUI, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA,
                                env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
    except OSError as ex:
        with LOCK:
            EXEC.update(rodando=False, fim=time.time(), codigo=-1, erro=str(ex))
        raise base.ErroUsuario(f"Não foi possível iniciar o motor: {ex}")
    EXEC["proc"] = proc
    threading.Thread(target=acompanhar, args=(proc,), daemon=True).start()
    return payload()


def acompanhar(proc):
    for linha in proc.stdout:
        linha = linha.rstrip("\r\n")
        with LOCK:
            if linha.startswith("@@ETAPA "):
                ident, _, desc = linha[8:].partition("|")
                if EXEC["etapas"] and EXEC["etapas"][-1]["estado"] == "rodando":
                    EXEC["etapas"][-1].update(estado="ok", fim=time.time())
                EXEC["etapas"].append(dict(id=ident, descricao=desc, estado="rodando", inicio=time.time()))
                EXEC["etapa"], EXEC["progresso"], EXEC["texto"] = ident, 0, ""
            elif linha.startswith("@@PROGRESSO "):
                pct, _, txt = linha[12:].partition("|")
                EXEC["progresso"], EXEC["texto"] = int(pct or 0), txt
            elif linha.startswith("@@AVISO "):
                EXEC["avisos"].append(linha[8:])
            elif linha.startswith("@@RESULTADO "):
                try:
                    EXEC["resultado"] = json.loads(linha[12:])
                except ValueError:
                    EXEC["resultado"] = {"bruto": linha[12:]}
                continue
            elif linha.startswith("@@ERRO "):
                EXEC["erro"] = linha[7:]
        registrar(linha)
    cod = proc.wait()
    with LOCK:
        if EXEC["etapas"] and EXEC["etapas"][-1]["estado"] == "rodando":
            EXEC["etapas"][-1].update(estado="ok" if cod == 0 else "erro", fim=time.time())
        if cod and not EXEC["erro"]:
            EXEC["erro"] = f"o motor saiu com código {cod}"
        EXEC.update(rodando=False, proc=None, fim=time.time(), codigo=cod)
    registrar(f"[fim: {'concluído' if cod == 0 else 'erro'} em {round(EXEC['fim'] - EXEC['inicio'])} s]")


def payload(desde=0):
    with LOCK:
        log = EXEC["log"]
        primeiro = EXEC["seq"] - len(log)
        ini = max(desde, primeiro)
        d = {k: EXEC[k] for k in ("rodando", "tarefa", "titulo", "etapas", "etapa", "progresso", "texto", "avisos", "resultado", "erro",
                                  "inicio", "fim", "codigo", "seq")}
        d["linhas"] = log[ini - primeiro:]
        d["desde"] = ini
        return d


# ------------------------------------------------------------------ rotas
def api_inicio(_):
    p = PREFS.ler()
    grupo = componentes.estado_grupo(GRUPO)
    py, desc = componentes.python_para(GRUPO)
    return {"versao": VERSAO, "raiz": RAIZ, "prefs": p, "componentes": grupo, "python": desc if py else None,
            "base_fifa16": BASE_FIFA16, "exec": payload(), "ids_gerados": ids_gerados()}


def ids_gerados():
    """IDs dos estádios que esta ferramenta já criou (para não sugerir de novo)."""
    out = set()
    d = os.path.join(CACHE, "trabalho")
    for n in os.listdir(d) if os.path.isdir(d) else []:
        try:
            with open(os.path.join(d, n, "resultado.json"), encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            continue
        if r.get("novo_id"):
            out.add(int(r["novo_id"]))
        for c in r.get("copias") or []:
            if c.get("novo_id"):
                out.add(int(c["novo_id"]))
    return sorted(out)


def api_ambiente(_):
    return motor(["ambiente"], timeout=120)


def api_estadios(q):
    d = motor(["estadios"], timeout=900)
    return d


def api_exec(q):
    return payload(int(q.get("desde") or 0))


def api_preparar(_):
    return iniciar("preparar", "Preparando o ambiente (SDK do FET e índice do jogo)", ["preparar"])


def _saida(d, sugestao):
    saida = d.get("saida")
    if not saida:
        saida = base.dialogo("salvar", "Salvar o projeto do FET como", PREFS.ler().get("pasta_saida") or RAIZ,
                             tipos=[("Projeto do FET", "*.fifaproject")], nome=sugestao, extensao=".fifaproject")
        if not saida:
            return None
    if not saida.lower().endswith(".fifaproject"):
        saida += ".fifaproject"
    if os.path.exists(saida):
        raise base.ErroUsuario("Esse arquivo já existe: escolha outro nome (a ferramenta nunca sobrescreve um projeto).")
    PREFS.atualizar(pasta_saida=os.path.dirname(saida))
    return saida


def _projeto_base(d):
    pb = d.get("projeto_base")
    if d.get("modo") == "projeto":
        if not pb or not os.path.isfile(pb):
            raise base.ErroUsuario("Escolha o projeto do FET em que os estádios novos vão entrar.")
        return pb
    return None


def api_duplicar(d):
    copias = d.get("copias") or []
    if not copias:
        raise base.ErroUsuario("Escolha pelo menos um estádio e quantas cópias.")
    for c in copias:
        if not str(c.get("novo_id", "")).isdigit() or not c.get("nome"):
            raise base.ErroUsuario("Cada cópia precisa de um ID novo (número) e de um nome.")
    pb = _projeto_base(d)
    saida = _saida(d, "Estadios_duplicados.fifaproject" if len(copias) > 1 else f"Estadio_{copias[0]['novo_id']}.fifaproject")
    if not saida:
        return {"cancelado": True}
    cfg = dict(copias=[dict(origem=int(c["origem"]), novo_id=int(c["novo_id"]), nome=c["nome"]) for c in copias], saida=saida,
               projeto_base=pb)
    n = len(copias)
    return iniciar("duplicar", f"Duplicando {n} estádio{'s' if n > 1 else ''}", ["duplicar"], cfg)


def api_converter(d):
    for k, rot in (("pasta16", "a pasta do estádio do FIFA 16"), ("novo_id", "o ID novo"), ("nome", "o nome do estádio")):
        if not d.get(k):
            raise base.ErroUsuario(f"Falta {rot}.")
    pb = _projeto_base(d)
    saida = _saida(d, f"Estadio_{d['novo_id']}_{re.sub(r'[^A-Za-z0-9]+', '_', d['nome']).strip('_')}.fifaproject")
    if not saida:
        return {"cancelado": True}
    cfg = dict(pasta16=d["pasta16"], novo_id=int(d["novo_id"]), nome=d["nome"], saida=saida, projeto_base=pb,
               receita=d.get("receita") or {})
    PREFS.atualizar(pasta16=os.path.dirname(d["pasta16"]))
    return iniciar("converter", f"Convertendo {d['nome']} (FIFA 16) sobre o El Grandioso", ["converter"], cfg)


def api_analisar16(d):
    pasta = d.get("pasta")
    if not pasta:
        pasta = base.dialogo("pasta", "Pasta do estádio do FIFA 16 (a que tem data\\sceneassets)", PREFS.ler().get("pasta16") or RAIZ)
        if not pasta:
            return {"cancelado": True}
    PREFS.atualizar(pasta16=os.path.dirname(pasta))
    return motor(["analisar16", pasta, os.path.join(CACHE, "miniaturas")], timeout=300)


def api_luz16(d):
    if not d.get("pasta"):
        raise base.ErroUsuario("Escolha antes a pasta do estádio do FIFA 16.")
    return motor(["luz16", d["pasta"]], timeout=3600)


def api_parar(_):
    with LOCK:
        p = EXEC.get("proc")
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=SEM_JANELA)
        registrar("[parado pelo usuário]")
    return payload()


def api_dialogo(d):
    modo = d.get("modo") or "pasta"
    tipos = [("Projeto do FET", "*.fifaproject"), ("Todos", "*.*")] if d.get("tipo") == "projeto" else None
    c = base.dialogo(modo, d.get("titulo") or "Escolher", d.get("inicial") or PREFS.ler().get("pasta_dialogo") or RAIZ, tipos=tipos)
    if not c:
        return {"cancelado": True}
    PREFS.atualizar(pasta_dialogo=os.path.dirname(c) if os.path.isfile(c) else c)
    return {"caminho": c}


def api_ambiente_pasta(d):
    qual = d.get("qual")
    if qual not in ("fet", "jogo"):
        raise base.ErroUsuario("Opção inválida.")
    titulo = "Pasta do FIFA Editor Tool (a que tem o FIFA Editor Tool.exe)" if qual == "fet" else "Pasta do EA SPORTS FC 27 (a que tem o FC27.exe)"
    p = base.dialogo("pasta", titulo, RAIZ)
    if not p:
        return {"cancelado": True}
    exe = "FIFA Editor Tool.exe" if qual == "fet" else "FC27.exe"
    if not os.path.isfile(os.path.join(p, exe)):
        raise base.ErroUsuario(f"Essa pasta não tem o {exe}.")
    prefs_motor = os.path.join(AQUI, "preferencias.json")
    PREFS.atualizar(**{f"{qual}_dir": p})
    return api_ambiente({}) if os.path.isfile(prefs_motor) else {}


def api_abrir(d):
    alvo = d.get("caminho")
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Não encontrado: {alvo}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def api_resultados(_):
    out = []
    d = os.path.join(CACHE, "trabalho")
    for n in sorted(os.listdir(d), reverse=True)[:40] if os.path.isdir(d) else []:
        f = os.path.join(d, n, "resultado.json")
        if not os.path.isfile(f):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            continue
        out.append({"pasta": os.path.join(d, n), "saida": r.get("saida"), "ok": r.get("ok"), "tipo": r.get("tipo", "converter" if "fifa16_id" in r else "duplicar"),
                    "nome": r.get("nome"), "quando": time.strftime("%d/%m/%Y %H:%M", time.localtime(os.path.getmtime(f))),
                    "existe": bool(r.get("saida") and os.path.isfile(r["saida"]))})
    return {"resultados": out}


def arquivo_imagem(h, q):
    """Miniaturas das texturas do FIFA 16 e prévias das conversões (só de dentro da pasta cache da ferramenta)."""
    cam = os.path.abspath(q.get("caminho") or os.path.join(CACHE, "miniaturas", q.get("arq") or ""))
    if not os.path.normcase(cam).startswith(os.path.normcase(CACHE) + os.sep) or not cam.lower().endswith(".png") or not os.path.isfile(cam):
        h.enviar(404, b"", "text/plain")
        return
    with open(cam, "rb") as f:
        h.enviar(200, f.read(), "image/png")


ROTAS_GET = {"inicio": api_inicio, "ambiente": api_ambiente, "estadios": api_estadios, "exec": api_exec, "resultados": api_resultados,
             "versao": lambda _: {"versao": VERSAO}}
ROTAS_POST = {"preparar": api_preparar, "duplicar": api_duplicar, "converter": api_converter, "analisar16": api_analisar16, "luz16": api_luz16,
              "parar": api_parar, "dialogo": api_dialogo, "ambiente_pasta": api_ambiente_pasta, "abrir": api_abrir}
cg, cp = base.rotas_componentes(GRUPO)
ROTAS_GET.update(cg)
ROTAS_POST.update(cp)


def main():
    ap = argparse.ArgumentParser(description="Estádios FC 27 (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8782)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    a = ap.parse_args()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, especiais={"/imagem": arquivo_imagem},
                                 nome="EstadiosFC27/" + VERSAO)
    base.servir(handler, a.porta, "Estádios FC 27", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
