"""Criador próprio (roda no computador, sem serviço externo): o lado do servidor.

O motor fica em local/ e roda num processo à parte (Python embutido com numpy, SciPy, OpenCV e MediaPipe); aqui
ficam o estado do que falta para ele funcionar, o preparo (modelos do MediaPipe + modelo das cabeças do jogo) e a
criação de uma face, com progresso e cancelamento. Só biblioteca padrão.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

import base
import componentes
import referencias
import local

AQUI = os.path.dirname(os.path.abspath(__file__))
GRUPO = "criador_faces"
SCRIPT = os.path.join(AQUI, "local", "criar.py")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_FOTOS = 6
TIPOS = ("image/jpeg", "image/png", "image/webp")
PADRAO_SAIDA = os.path.normpath(os.path.join(base.raiz_trabalho(), "Faces criadas"))
REF = referencias.Referencias("Criador de Faces", {os.path.basename(local.REFERENCIA): local.REFERENCIA},
                              "criar faces no criador próprio")
LOCK = threading.RLock()
MOTOR = {"dados": None, "conferindo": False, "quando": 0, "erro": None}
PREPARO = {"ativa": False, "f": 0.0, "msg": "", "erro": None, "fim": 0}
PROC = {"p": None, "cancelado": False}
S = None                                # o módulo do servidor (TAREFA, FOTOS, histórico), ligado em ligar()


def ligar(servidor):
    global S
    S = servidor


def python_cmd():
    cmd, _ = componentes.python_para(GRUPO)
    return cmd + ["-X", "utf8", "-u"] if cmd else None


def rodar(args, ao_evento=None, guardar=False):
    """roda local/criar.py e lê os eventos JSON; devolve (resultado ou None, mensagem de erro ou None)"""
    cmd = python_cmd()
    if not cmd:
        return None, componentes.falta_msg(GRUPO)
    op = S.PREFS.ler()
    extra = []
    for k, flag in (("fet_dir", "--fet"), ("jogo_dir", "--jogo")):
        if op.get(k):
            extra += [flag, op[k]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        p = subprocess.Popen(cmd + [SCRIPT] + args + extra, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=env,
                             cwd=AQUI, creationflags=SEM_JANELA)
    except OSError as ex:
        return None, f"Não foi possível iniciar o motor: {ex}"
    if guardar:
        with LOCK:
            PROC["p"] = p
    cauda = []
    threading.Thread(target=lambda: cauda.extend(p.stderr.read().splitlines()[-12:]), daemon=True).start()
    resultado, erro = None, None
    for linha in p.stdout:
        try:
            ev = json.loads(linha)
        except ValueError:
            continue
        if ev.get("tipo") == "resultado":
            resultado = ev
        elif ev.get("tipo") == "erro":
            erro = ev.get("msg") or "erro"
        elif ao_evento:
            ao_evento(ev)
    cod = p.wait()
    if guardar:
        with LOCK:
            PROC["p"] = None
    if resultado is None and erro is None:
        time.sleep(0.2)
        uteis = [l for l in cauda if l.strip() and not l.startswith(("W0000", "I0000", "INFO", "WARNING"))]
        erro = f"O motor parou sem resposta (código {cod})." + (" " + uteis[-1][:300] if uteis else "")
    return resultado, erro


# ------------------------------------------------------------------ estado
def conferir(forcar=False):
    """atualiza o estado do motor (jogo, FET, modelo) em segundo plano"""
    with LOCK:
        if MOTOR["conferindo"] or (not forcar and MOTOR["dados"] is not None and time.time() - MOTOR["quando"] < 600):
            return
        if not componentes.estado_grupo(GRUPO)["ok"]:
            MOTOR.update(dados=None, erro=None, quando=0)
            return
        MOTOR["conferindo"] = True

    def tarefa():
        r, erro = rodar(["estado"])
        with LOCK:
            MOTOR.update(dados=r, erro=erro, conferindo=False, quando=time.time())
    threading.Thread(target=tarefa, daemon=True).start()


def estado():
    g = componentes.estado_grupo(GRUPO)
    conferir()
    with LOCK:
        m = dict(MOTOR)
        prep = dict(PREPARO)
    d = m["dados"] or {}
    jogo = d.get("jogo") or {}
    faltam_modelos = d.get("modelos_faltando") if d else None
    modelo = d.get("modelo")
    modelo_ok = bool(modelo) and d.get("modelo_atual", True) is not False and not faltam_modelos
    ref = REF.estado()
    return {
        "componentes": {"ok": g["ok"], "download": g["download"], "python": g["python"]},
        "referencia": ref, "jogo": jogo, "modelo": modelo, "modelo_velho": bool(modelo) and d.get("modelo_atual") is False,
        "modelos_faltando": faltam_modelos or [], "conferindo": m["conferindo"] and not d, "erro": m["erro"],
        "preparo": prep, "saida_padrao": PADRAO_SAIDA, "limite_fotos": MAX_FOTOS,
        "pronto": bool(g["ok"] and ref["ok"] and jogo.get("ok") and modelo_ok and not prep["ativa"]),
    }


def pasta_saida():
    return S.PREFS.ler().get("saida_local") or PADRAO_SAIDA


# ------------------------------------------------------------------ preparo
def api_preparar(d):
    refazer = bool((d or {}).get("refazer"))
    g = componentes.estado_grupo(GRUPO)
    if not g["ok"]:
        raise base.ErroUsuario(componentes.falta_msg(GRUPO))
    REF.exigir()
    with LOCK:
        if PREPARO["ativa"]:
            return S.estado_payload()
        if S.TAREFA["fase"] in S.ATIVAS:
            raise base.ErroUsuario("Espere a cabeça em andamento terminar.")
        PREPARO.update(ativa=True, f=0.0, msg="Preparando…", erro=None, fim=0)

    def tarefa():
        erro = None
        try:
            os.makedirs(local.PASTA_MODELOS, exist_ok=True)
            itens = [m for n, m in local.MODELOS.items()
                     if not os.path.isfile(os.path.join(local.PASTA_MODELOS, n))
                     or os.path.getsize(os.path.join(local.PASTA_MODELOS, n)) != m["tamanho"]]
            total = sum(m["tamanho"] for m in itens) or 1
            feito = 0
            for m in itens:
                def prog(n, t, feito=feito, m=m):
                    with LOCK:
                        PREPARO.update(f=0.12 * (feito + n) / total, msg=f"Baixando {m['nome']}")
                arq = componentes.baixar(m, prog)
                shutil.move(arq, os.path.join(local.PASTA_MODELOS, m["arquivo"]))
                feito += m["tamanho"]

            def ev(e):
                if e.get("tipo") == "progresso":
                    with LOCK:
                        PREPARO.update(f=0.12 + 0.88 * float(e.get("f") or 0), msg=e.get("msg") or "")
            with LOCK:
                dd = MOTOR["dados"] or {}
            if refazer or not dd.get("modelo") or dd.get("modelo_atual") is False:
                r, erro = rodar(["preparar"], ev)
        except componentes.ErroComponente as ex:
            erro = str(ex)
        except OSError as ex:
            erro = f"Não deu para guardar os modelos do MediaPipe: {ex}"
        with LOCK:
            PREPARO.update(ativa=False, erro=erro, fim=time.time(), f=0.0 if erro else 1.0, msg="" if erro else "Pronto")
        conferir(forcar=True)
    threading.Thread(target=tarefa, daemon=True).start()
    return S.estado_payload()


def api_conferir(_):
    conferir(forcar=True)
    return S.estado_payload()


def api_escolher_pasta(d):
    """pasta do FIFA Editor Tool ou do jogo, quando não foram achadas sozinhas"""
    qual = d.get("qual")
    if qual not in ("fet", "jogo"):
        raise base.ErroUsuario("Pasta desconhecida.")
    titulo = "Pasta do FIFA Editor Tool (a que tem o FIFA Editor Tool.exe)" if qual == "fet" else \
        "Pasta do EA SPORTS FC 27 (a que tem o FC27.exe)"
    r = base.dialogo("pasta", titulo)
    if not r:
        return {"cancelado": True, **S.estado_payload()}
    exe = "FIFA Editor Tool.exe" if qual == "fet" else "FC27.exe"
    if not os.path.isfile(os.path.join(r, exe)):
        raise base.ErroUsuario(f"Essa pasta não tem o {exe}.")
    S.atualizar_prefs(**{qual + "_dir": r})
    conferir(forcar=True)
    return S.estado_payload()


def api_escolher_saida(_):
    r = base.dialogo("pasta", "Pasta onde as faces criadas serão guardadas", inicial=pasta_saida())
    if r:
        S.atualizar_prefs(saida_local=r)
    return S.estado_payload()


# ------------------------------------------------------------------ criar
def api_criar(d):
    e = estado()
    if not e["componentes"]["ok"]:
        raise base.ErroUsuario(componentes.falta_msg(GRUPO))
    REF.exigir()
    if not e["pronto"]:
        raise base.ErroUsuario("O criador próprio ainda não está preparado: use Preparar no painel da direita.")
    with LOCK, S.LOCK:
        fotos = list(S.FOTOS)
    if not fotos:
        raise base.ErroUsuario("Adicione as fotos do jogador (de 1 a %d)." % MAX_FOTOS)
    if len(fotos) > MAX_FOTOS:
        raise base.ErroUsuario("O criador próprio usa até %d fotos: uma de frente e uma de cada lado bastam." % MAX_FOTOS)
    ruim = next((f for f in fotos if f["tipo"] not in TIPOS), None)
    if ruim:
        raise base.ErroUsuario(f"{ruim['nome']}: o criador próprio lê JPG, PNG e WebP.")
    sumiu = next((f for f in fotos if not os.path.isfile(f["caminho"])), None)
    if sumiu:
        raise base.ErroUsuario(f"A foto {sumiu['nome']} não existe mais no disco. Tire da lista e adicione de novo.")
    ident = str(d.get("jogador") or "").strip() or "0"
    if not ident.isdigit() or len(ident) > 9:
        raise base.ErroUsuario("O ID do jogador é só o número (o mesmo da pasta dele no FET).")
    nome = S.limpar_nome(d.get("nome")) or S.sugerir_nome()
    saida = pasta_saida()
    try:
        os.makedirs(saida, exist_ok=True)
    except OSError as ex:
        raise base.ErroUsuario(f"Não deu para usar a pasta de saída {saida}: {ex}") from None
    pasta = S.pasta_livre(os.path.join(saida, nome))
    with S.LOCK:
        if S.TAREFA["fase"] in S.ATIVAS or PREPARO["ativa"]:
            raise base.ErroUsuario("Já tem um trabalho em andamento: espere terminar.")
        PROC["cancelado"] = False
        S.TAREFA.clear()
        S.TAREFA.update(S.tarefa_nova(fase="local", titulo="Criando a face no computador", progresso=0, nome=nome, pasta=pasta,
                                      inicio=time.time(), msg="Abrindo o motor"))
    threading.Thread(target=_trabalho, args=(fotos, nome, pasta, ident), daemon=True).start()
    return S.estado_payload()


def _trabalho(fotos, nome, pasta, ident):
    registro = []

    def ev(e):
        if e.get("tipo") == "progresso":
            S.mudar_tarefa(progresso=float(e.get("f") or 0), msg=e.get("msg") or "")
        elif e.get("tipo") == "registro":
            registro.append(e.get("msg") or "")
    r, erro = rodar(["criar", "--saida", pasta, "--id", ident] + [f["caminho"] for f in fotos], ev, guardar=True)
    if PROC["cancelado"]:
        shutil.rmtree(pasta, ignore_errors=True)
        S.mudar_tarefa(fase="cancelado", titulo="Cancelado", msg="Nada foi gravado.", progresso=None, fim=time.time())
        return
    if erro or not r:
        if os.path.isdir(pasta) and not os.listdir(pasta):
            shutil.rmtree(pasta, ignore_errors=True)
        S.mudar_tarefa(fase="erro", titulo="Não deu para criar a face", progresso=None, fim=time.time(),
                       erro={"codigo": "local", "mensagem": erro or "erro", "original": "", "link": None, "request_id": None})
        return
    arqs = {k: os.path.join(pasta, v) for k, v in (r.get("arquivos") or {}).items()}
    item = {"idem": uuid.uuid4().hex, "id": None, "origem": "local", "nome": nome, "criado": S.agora(), "pasta": pasta,
            "modo": "local", "fotos": len(fotos), "nomes_fotos": [f["nome"] for f in fotos], "status": "pronta",
            "jogador": ident, "arquivos": arqs, "relatorio": {k: r.get(k) for k in ("yaw", "distancia_m", "erro_pontos_mm",
                                                                                   "textura_das_fotos", "segundos")}}
    try:
        with open(os.path.join(pasta, "registro.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(registro))
    except OSError:
        pass
    S.salvar_item(item)
    S.mudar_tarefa(fase="pronto", titulo="Face pronta", progresso=1, fim=time.time(), idem=item["idem"],
                   resultado={"idem": item["idem"], "pasta": pasta, "arquivos": arqs})


def cancelar():
    """mata o motor em andamento; devolve True se havia um"""
    with LOCK:
        p = PROC["p"]
        if p is None or p.poll() is not None:
            return False
        PROC["cancelado"] = True
    try:
        p.kill()
    except OSError:
        pass
    return True


def rotas():
    get, post = {}, {"local_preparar": api_preparar, "local_conferir": api_conferir, "local_criar": api_criar,
                     "local_pasta": api_escolher_pasta, "local_saida": api_escolher_saida}
    for g, p in (base.rotas_componentes(GRUPO, ao_concluir=lambda: conferir(forcar=True)), REF.rotas(lambda: conferir(forcar=True))):
        get.update(g)
        post.update(p)
    return get, post
