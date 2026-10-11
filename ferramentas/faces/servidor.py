"""Conversor de Faces FC 26 <-> FC 27 (BRFP Super Tool) — servidor local da interface.

    python servidor.py [--porta 8771] [--sem-janela]

A interface roda em Python padrão; a conversão (numpy/scipy) roda no motor/ com o Python 3.12 ("py -3.12"),
chamado pela ponte (motor/ponte.py), que devolve um evento JSON por linha.
"""
import argparse
import base64
import collections
import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.join(AQUI, "motor")
CACHE = os.path.join(AQUI, "cache")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import componentes  # noqa: E402

VERSAO = "1.2"
OUTRO = {"fc26": "fc27", "fc27": "fc26"}
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "saida": "", "destino": "auto", "textura": "fc26", "copiar_outros": False, "sobrescrever": False, "ultima_pasta": ""})
LOCK = threading.RLock()
ITENS = collections.OrderedDict()      # id -> item
RAIZES = {}                            # pasta adicionada -> {"outros": [rel, ...]}
JOB = {"rodando": False, "total": 0, "feitos": 0, "atual": None, "inicio": 0, "fim": 0, "proc": None, "resumo": None,
       "cancelado": False}
SEQ = itertools.count(1)
PY312 = {"cmd": None, "ok": False, "msg": "verificando…"}
PREVIAS = {}                           # (caminho, mtime) -> partes
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ------------------------------------------------------------------ ambiente (Python com numpy/scipy)
def verificar_python():
    """Motor: o Python embutido do Super Tool com numpy e SciPy; senão um Python do computador que os tenha."""
    cmd, desc = componentes.python_para("faces", forcar=True)
    if cmd:
        try:
            r = subprocess.run(cmd + ["-c", "import numpy, scipy, sys; print(sys.version.split()[0], numpy.__version__, scipy.__version__)"],
                               capture_output=True, text=True, timeout=120, creationflags=SEM_JANELA)
            v = r.stdout.split()
            if r.returncode == 0 and len(v) == 3:
                PY312.update(cmd=cmd + ["-X", "utf8"], ok=True, instalar=False,
                             msg=f"{desc} · numpy {v[1]} · scipy {v[2]}")
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    PY312.update(cmd=None, ok=False, instalar=True, msg=componentes.falta_msg("faces"))


def ponte(comando, arg):
    """Inicia o motor e devolve o processo (saída = um JSON por linha)."""
    if not PY312["ok"]:
        raise base.ErroUsuario(PY312["msg"])
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.Popen(PY312["cmd"] + [os.path.join(MOTOR, "ponte.py"), comando, arg], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env,
                            creationflags=SEM_JANELA)


def eventos(proc):
    for linha in proc.stdout:
        linha = linha.strip()
        if not linha.startswith("{"):
            continue
        try:
            yield json.loads(linha)
        except ValueError:
            continue


def arquivo_temp(nome, dados):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, nome)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    return p


# ------------------------------------------------------------------ saída de cada item
def destino_de(it, op):
    if not it.get("jogo"):
        return None
    if op["destino"] in OUTRO:
        return op["destino"]
    return OUTRO[it["jogo"]]


def raiz_saida(it, destino, op):
    if op["saida"]:
        return os.path.abspath(op["saida"])
    if it.get("recebido"):
        return None
    suf = "_" + destino.upper()
    if it["de_pasta"]:
        return it["raiz"].rstrip("\\/") + suf
    return os.path.join(os.path.dirname(it["caminho"]), "Convertidos" + suf)


def planejar(it, op):
    """Destino, caminho de saída e motivo de ignorar (sem tocar no disco)."""
    p = {"destino": None, "saida": None, "raiz_saida": None, "motivo": None}
    if it.get("erro"):
        p["motivo"] = "não foi possível ler o FBX"
        return p
    if not it.get("jogo"):
        p["motivo"] = "mouthbag (o FC 27 não usa)" if "mouthbag" in os.path.basename(it["caminho"]).lower() else "não é uma cabeça (sem head_mat)"
        return p
    d = destino_de(it, op)
    p["destino"] = d
    if d == it["jogo"]:
        p["motivo"] = f"já está no formato {d.upper()}"
        return p
    rs = raiz_saida(it, d, op)
    if rs is None:
        p["motivo"] = "escolha a pasta de saída (arquivo arrastado para a janela)"
        return p
    rel_dir = os.path.dirname(it["rel"]) if it["de_pasta"] else ""
    p["raiz_saida"] = rs
    p["saida"] = os.path.normpath(os.path.join(rs, rel_dir, it["nomes"][d]))
    if it["de_pasta"]:
        raiz = os.path.abspath(it["raiz"])
        if os.path.normcase(os.path.commonpath([os.path.abspath(rs), raiz])) == os.path.normcase(raiz):
            p["motivo"] = "a pasta de saída não pode ficar dentro da pasta de entrada"
    return p


def item_publico(it, op):
    pl = planejar(it, op)
    d = {k: it.get(k) for k in ("id", "caminho", "rel", "raiz", "de_pasta", "recebido", "jogo", "materiais", "lods",
                                "vertices", "id_jogador", "variacao", "malha", "erro", "estado", "avisos", "metodos",
                                "segundos", "mensagem", "saida_feita", "diferenca_cm")}
    d.update(destino=pl["destino"], saida=pl["saida"], motivo=pl["motivo"],
             existe=bool(pl["saida"] and os.path.exists(pl["saida"])))
    return d


def reconferir_motor():
    """Pacotes instalados por outra janela (Super Tool ou outra ferramenta): reconfere o motor uma vez."""
    if PY312["ok"] or not PY312.get("instalar") or PY312.get("reconferindo") or not componentes.estado_grupo("faces")["ok"]:
        return

    def rodar():
        try:
            verificar_python()
        finally:
            PY312["reconferindo"] = False
    PY312["reconferindo"] = True
    threading.Thread(target=rodar, daemon=True).start()


def estado_payload():
    reconferir_motor()
    op = PREFS.ler()
    with LOCK:
        itens = [item_publico(it, op) for it in ITENS.values()]
        job = {k: JOB[k] for k in ("rodando", "total", "feitos", "atual", "inicio", "fim", "resumo", "cancelado")}
    return {"itens": itens, "job": job, "opcoes": op, "ambiente": dict(PY312, cmd=None),
            "raizes": {r: len(v["outros"]) for r, v in RAIZES.items()}}


# ------------------------------------------------------------------ rotas
def api_inicio(_):
    return {"versao": VERSAO, **estado_payload()}


def api_estado(_):
    return estado_payload()


def api_opcoes(d):
    op = PREFS.ler()
    for k in ("saida", "destino", "textura", "copiar_outros", "sobrescrever"):
        if k in d:
            op[k] = d[k]
    if op["destino"] not in ("auto", "fc26", "fc27") or op["textura"] not in ("fc26", "fc27"):
        raise base.ErroUsuario("Opção inválida.")
    if op["saida"]:
        op["saida"] = os.path.normpath(op["saida"].strip().strip('"'))
    PREFS.gravar(op)
    return estado_payload()


def adicionar_caminhos(caminhos, recebido=False):
    caminhos = [os.path.abspath(c.strip().strip('"')) for c in caminhos if c and c.strip()]
    if not caminhos:
        return {"novos": 0, **estado_payload()}
    for c in caminhos:
        if not os.path.exists(c):
            raise base.ErroUsuario(f"Não encontrado: {c}")
    proc = ponte("detectar", arquivo_temp("detectar.json", caminhos))
    novos = 0
    with LOCK:
        existentes = {os.path.normcase(it["caminho"]) for it in ITENS.values()}
    for ev in eventos(proc):
        if ev["tipo"] == "fbx":
            if os.path.normcase(ev["caminho"]) in existentes:
                continue
            i = next(SEQ)
            it = {"id": i, "caminho": ev["caminho"], "rel": ev["rel"], "raiz": ev["raiz"], "de_pasta": ev["de_pasta"],
                  "recebido": recebido, "jogo": ev.get("jogo"), "materiais": ev.get("materiais", []),
                  "lods": ev.get("lods", 0), "vertices": ev.get("vertices", 0), "id_jogador": ev.get("id"),
                  "variacao": ev.get("variacao"), "malha": ev.get("malha", ""), "nomes": ev.get("nomes") or {},
                  "erro": ev.get("erro"), "estado": "pronto", "avisos": [], "metodos": {}}
            with LOCK:
                ITENS[i] = it
            existentes.add(os.path.normcase(ev["caminho"]))
            novos += 1
        elif ev["tipo"] == "pasta":
            with LOCK:
                RAIZES[ev["raiz"]] = {"outros": ev["outros"]}
        elif ev["tipo"] == "falha":
            raise base.ErroUsuario("Falha ao ler as faces: " + ev["erro"])
    proc.wait()
    if not recebido:
        PREFS.atualizar(ultima_pasta=os.path.dirname(caminhos[0]) if os.path.isfile(caminhos[0]) else caminhos[0])
    return {"novos": novos, **estado_payload()}


def api_adicionar(d):
    return adicionar_caminhos(d.get("caminhos") or [])


def api_dialogo(d):
    op = PREFS.ler()
    inicial = d.get("inicial") or op.get("ultima_pasta") or base.raiz_trabalho()
    if d.get("modo") == "arquivos":
        r = base.dialogo("abrir", "Escolha os FBX de cabeça (exportados pelo FET)", inicial,
                         tipos=[("FBX de cabeça", "*.fbx"), ("Todos", "*.*")], multiplo=True)
        return {"caminhos": r or []}
    titulo = "Pasta de saída das faces convertidas" if d.get("modo") == "saida" else \
        "Pasta com faces (ex.: a pasta do Batch Import Faces do FET)"
    r = base.dialogo("pasta", titulo, op.get("saida") if d.get("modo") == "saida" and op.get("saida") else inicial)
    return {"caminhos": [r] if r else []}


def api_receber(d):
    """Arquivos arrastados para a janela: o navegador não informa o caminho, então são gravados numa pasta de recebidos."""
    pasta = os.path.join(CACHE, "recebidos", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(pasta, exist_ok=True)
    caminhos = []
    for a in d.get("arquivos", []):
        nome = os.path.basename(a["nome"])
        if not nome.lower().endswith(".fbx"):
            continue
        destino = os.path.join(pasta, nome)
        with open(destino, "wb") as f:
            f.write(base64.b64decode(a["dados"]))
        caminhos.append(destino)
    if not caminhos:
        raise base.ErroUsuario("Arraste arquivos .fbx de cabeça (ou use Adicionar pasta para trazer texturas junto).")
    return adicionar_caminhos(caminhos, recebido=True)


def api_remover(d):
    with LOCK:
        if JOB["rodando"]:
            raise base.ErroUsuario("Espere a conversão terminar.")
        ids = set(d.get("ids") or [])
        for i in list(ITENS):
            if d.get("todos") or i in ids:
                del ITENS[i]
        usadas = {it["raiz"] for it in ITENS.values() if it["de_pasta"]}
        for r in list(RAIZES):
            if r not in usadas:
                del RAIZES[r]
    return estado_payload()


def api_converter(d):
    op = PREFS.ler()
    with LOCK:
        if JOB["rodando"]:
            raise base.ErroUsuario("Já há uma conversão em andamento.")
        ids = d.get("ids") or [i for i, it in ITENS.items()]
        fila, ignorados = [], 0
        for i in ids:
            it = ITENS.get(i)
            if it is None:
                continue
            pl = planejar(it, op)
            if pl["motivo"]:
                it.update(estado="ignorado", mensagem=pl["motivo"])
                ignorados += 1
                continue
            if os.path.exists(pl["saida"]) and not op["sobrescrever"]:
                it.update(estado="ignorado", mensagem="já existe na saída (ligue Sobrescrever)")
                ignorados += 1
                continue
            it.update(estado="na_fila", mensagem=None, avisos=[], metodos={}, saida_feita=None)
            fila.append({"id": i, "entrada": it["caminho"], "saida": pl["saida"], "destino": pl["destino"],
                         "_raiz_saida": pl["raiz_saida"]})
        if not fila:
            return {"iniciado": False, "ignorados": ignorados, **estado_payload()}
        JOB.update(rodando=True, total=len(fila), feitos=0, atual=None, inicio=time.time(), fim=0, resumo=None, cancelado=False)
    threading.Thread(target=rodar_conversao, args=(fila, op), daemon=True).start()
    return {"iniciado": True, "ignorados": ignorados, **estado_payload()}


def rodar_conversao(fila, op):
    cont = collections.Counter()
    por_raiz = collections.defaultdict(list)
    try:
        job = {"textura": op["textura"], "itens": [{k: v for k, v in f.items() if not k.startswith("_")} for f in fila]}
        proc = ponte("converter", arquivo_temp("converter.json", job))
        JOB["proc"] = proc
        raiz_de = {f["id"]: f["_raiz_saida"] for f in fila}
        for ev in eventos(proc):
            with LOCK:
                it = ITENS.get(ev.get("id"))
                if ev["tipo"] == "inicio" and it:
                    it["estado"] = "convertendo"
                    JOB["atual"] = ev["id"]
                elif ev["tipo"] == "ok" and it:
                    it.update(estado="ok", saida_feita=ev["saida"], avisos=ev["avisos"], metodos=ev["metodos"],
                              segundos=ev["s"], diferenca_cm=ev.get("diferenca_max_cm"))
                    JOB["feitos"] += 1
                    cont["convertidos"] += 1
                    cont["avisos"] += len(ev["avisos"])
                    linhas = [f"OK        {it['rel']} -> {os.path.relpath(ev['saida'], raiz_de[it['id']])}  "
                              f"({ev['origem'].upper()} -> {ev['destino'].upper()}, {ev['s']} s)"]
                    linhas += [f"              {k}: {v}" for k, v in ev["metodos"].items()]
                    linhas += [f"              AVISO: {a}" for a in ev["avisos"]]
                    por_raiz[raiz_de[it["id"]]] += linhas
                elif ev["tipo"] == "erro" and it:
                    it.update(estado="erro", mensagem=ev["erro"], segundos=ev["s"])
                    JOB["feitos"] += 1
                    cont["erros"] += 1
                    por_raiz[raiz_de[it["id"]]].append(f"ERRO      {it['rel']}: {ev['erro']}")
                elif ev["tipo"] == "falha":
                    cont["erros"] += 1
                    for f in fila:
                        x = ITENS.get(f["id"])
                        if x and x["estado"] in ("na_fila", "convertendo"):
                            x.update(estado="erro", mensagem=ev["erro"])
        proc.wait()
        with LOCK:
            for f in fila:   # cancelado ou motor caiu no meio
                x = ITENS.get(f["id"])
                if x and x["estado"] in ("na_fila", "convertendo"):
                    x.update(estado="pronto" if JOB["cancelado"] else "erro",
                             mensagem="cancelado" if JOB["cancelado"] else "o motor parou antes deste item")
        # arquivos que não são cabeça (texturas, cabelo...) para a pasta ficar pronta para o Batch Import Faces
        if op["copiar_outros"] and not JOB["cancelado"]:
            raizes_saida = {}
            for f in fila:
                it = ITENS.get(f["id"])
                if it and it["de_pasta"]:
                    raizes_saida[it["raiz"]] = f["_raiz_saida"]
            for raiz, rs in raizes_saida.items():
                for rel in RAIZES.get(raiz, {}).get("outros", []):
                    if "mouthbag" in rel.lower():
                        continue
                    dst = os.path.join(rs, rel)
                    if os.path.exists(dst) and not op["sobrescrever"]:
                        continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(os.path.join(raiz, rel), dst)
                    cont["copiados"] += 1
                    por_raiz[rs].append(f"COPIADO   {rel}")
    except Exception as ex:  # noqa: BLE001
        cont["erros"] += 1
        with LOCK:
            for f in fila:
                x = ITENS.get(f["id"])
                if x and x["estado"] in ("na_fila", "convertendo"):
                    x.update(estado="erro", mensagem=str(ex))
    finally:
        resumo = (f"Convertidos: {cont['convertidos']}   Copiados: {cont['copiados']}   Avisos: {cont['avisos']}   "
                  f"Erros: {cont['erros']}")
        for rs, linhas in por_raiz.items():
            try:
                os.makedirs(rs, exist_ok=True)
                with open(os.path.join(rs, "relatorio_conversao_faces.txt"), "a", encoding="utf-8") as fh:
                    fh.write(f"Conversor de Faces FC 26 <-> FC 27 {VERSAO} - {time.strftime('%d/%m/%Y %H:%M')}\n\n")
                    fh.write("\n".join(linhas) + "\n\n" + resumo + "\n\n")
            except OSError:
                pass
        with LOCK:
            JOB.update(rodando=False, atual=None, fim=time.time(), proc=None,
                       resumo={**cont, "segundos": round(time.time() - JOB["inicio"], 1), "pastas": list(por_raiz)})


def api_cancelar(_):
    with LOCK:
        p = JOB.get("proc")
        if JOB["rodando"] and p:
            JOB["cancelado"] = True
            p.kill()
    return estado_payload()


def api_abrir(d):
    if d.get("caminho"):
        alvo = d["caminho"]
    else:
        op = PREFS.ler()
        alvo = op["saida"]
        if not alvo:
            raise base.ErroUsuario("Sem pasta de saída definida: cada face vai para a pasta ao lado da entrada.")
    if not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def api_previa(q):
    with LOCK:
        it = ITENS.get(int(q["id"]))
    if it is None:
        raise base.ErroUsuario("Face não encontrada na lista.")
    caminho = it.get("saida_feita") if q.get("qual") == "saida" else it["caminho"]
    if not caminho or not os.path.isfile(caminho):
        raise base.ErroUsuario("Arquivo não encontrado.")
    chave = (caminho, os.path.getmtime(caminho))
    if chave not in PREVIAS:
        proc = ponte("previa", caminho)
        partes = None
        for ev in eventos(proc):
            if ev["tipo"] == "previa":
                partes = ev["partes"]
            elif ev["tipo"] == "falha":
                raise base.ErroUsuario(ev["erro"])
        proc.wait()
        if partes is None:
            raise base.ErroUsuario("Não foi possível ler a malha.")
        PREVIAS[chave] = partes
    return {"partes": PREVIAS[chave], "arquivo": os.path.basename(caminho)}


def api_relatorio(_):
    with LOCK:
        pastas = list((JOB.get("resumo") or {}).get("pastas") or [])
    for p in pastas:
        arq = os.path.join(p, "relatorio_conversao_faces.txt")
        if os.path.isfile(arq):
            base.abrir_no_explorer(arq, selecionar=True)
            return {}
    raise base.ErroUsuario("Nenhum relatório ainda.")


ROTAS_GET = {"inicio": api_inicio, "estado": api_estado, "previa": api_previa,
             "versao": lambda _: {"versao": VERSAO}}
ROTAS_POST = {"opcoes": api_opcoes, "adicionar": api_adicionar, "dialogo": api_dialogo, "receber": api_receber,
              "remover": api_remover, "converter": api_converter, "cancelar": api_cancelar, "abrir": api_abrir,
              "relatorio": api_relatorio}
_G, _P = base.rotas_componentes("faces", ao_concluir=verificar_python)
ROTAS_GET.update(_G)
ROTAS_POST.update(_P)


def main():
    ap = argparse.ArgumentParser(description="Conversor de Faces FC 26 <-> FC 27 (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8771)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("entradas", nargs="*", help=".fbx ou pastas para já entrar na lista")
    a = ap.parse_args()
    def preparar():
        verificar_python()
        if a.entradas and PY312["ok"]:
            try:
                adicionar_caminhos(a.entradas)
            except base.ErroUsuario as ex:
                print(ex, flush=True)
    threading.Thread(target=preparar, daemon=True).start()   # a janela abre já; o ambiente aparece em seguida
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, nome="ConversorFaces/" + VERSAO)
    base.servir(handler, a.porta, "Conversor de Faces", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
