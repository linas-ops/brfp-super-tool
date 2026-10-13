"""Conversor de Corpos FC 26 <-> FC 27 (BRFP Super Tool) — servidor local da interface.

    python servidor.py [--porta 8777] [--sem-janela] [texturas ou pastas]

Converte texturas do corpo (bodyupper: pele, tatuagens, normal) entre os layouts de UV do FC 26 e do FC 27. A interface
roda em Python padrão; a conversão (numpy, SciPy e Pillow) roda em motor/, chamada pela ponte (motor/ponte.py), que
devolve um evento JSON por linha.
"""
import argparse
import base64
import collections
import itertools
import json
import os
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
import referencias  # noqa: E402

VERSAO = "1.1"
GRUPO = "corpos"
OUTRO = {"fc26": "fc27", "fc27": "fc26"}
NOME = {"fc26": "FC 26", "fc27": "FC 27"}
EXT = (".png", ".dds", ".tga", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "saida": "", "destino": "auto", "tamanho": 0, "tipo": "auto", "sobrescrever": False, "ultima_pasta": ""})
LOCK = threading.RLock()
ITENS = collections.OrderedDict()      # id -> item
JOB = {"rodando": False, "total": 0, "feitos": 0, "atual": None, "inicio": 0, "fim": 0, "proc": None, "resumo": None,
       "cancelado": False, "mensagem": None}
SEQ = itertools.count(1)
MOTOR_PY = {"cmd": None, "ok": False, "msg": "verificando…"}
PREVIAS = {}                           # (caminho, mtime) -> png reduzido
MALHAS = {}                            # jogo -> {V, UV, T}
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# corpos (bodyupper LOD0) exportados pelo FET de cada jogo: tirados do jogo, não vêm no pacote leve
REF = referencias.Referencias("Conversor de Corpos", {
    f"bodyupper_{j}.fbx": os.path.join(MOTOR, "referencia", f"bodyupper_{j}.fbx") for j in ("fc26", "fc27")},
    "identificar e converter as texturas")


# ------------------------------------------------------------------ ambiente (Python com numpy/SciPy/Pillow)
def verificar_python():
    cmd, desc = componentes.python_para(GRUPO, forcar=True)
    if cmd:
        try:
            r = subprocess.run(cmd + ["-c", "import numpy, scipy, PIL, sys; print(sys.version.split()[0], numpy.__version__, "
                                            "scipy.__version__, PIL.__version__)"],
                               capture_output=True, text=True, timeout=120, creationflags=SEM_JANELA)
            v = r.stdout.split()
            if r.returncode == 0 and len(v) == 4:
                MOTOR_PY.update(cmd=cmd + ["-X", "utf8"], ok=True, instalar=False,
                                msg=f"{desc} · numpy {v[1]} · SciPy {v[2]} · Pillow {v[3]}")
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    MOTOR_PY.update(cmd=None, ok=False, instalar=True, msg=componentes.falta_msg(GRUPO))


def preparar_mapas():
    """Primeira vez: calcula em segundo plano a correspondência FC 26 <-> FC 27 em 1024 (o tamanho do jogo), para a
    primeira conversão já sair em segundos."""
    pasta = os.path.join(CACHE, "mapas")
    if not MOTOR_PY["ok"] or REF.faltam() or (os.path.isdir(pasta) and sum(n.startswith("mapa_") and "_1024x1024_" in n
                                                         for n in os.listdir(pasta)) >= 2):
        return
    def rodar():
        try:
            proc = ponte("preparar", "1024")
            for _ in eventos(proc):
                pass
            proc.wait()
        except (OSError, base.ErroUsuario):
            pass
    threading.Thread(target=rodar, daemon=True).start()


def ponte(comando, arg):
    if not MOTOR_PY["ok"]:
        raise base.ErroUsuario(MOTOR_PY["msg"])
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", BRFP_CORPOS_CACHE=os.path.join(CACHE, "mapas"))
    return subprocess.Popen(MOTOR_PY["cmd"] + [os.path.join(MOTOR, "ponte.py"), comando, arg], stdout=subprocess.PIPE,
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


def reconferir_motor():
    """Pacotes instalados por outra janela (Super Tool ou outra ferramenta): reconfere o motor uma vez."""
    if MOTOR_PY["ok"] or not MOTOR_PY.get("instalar") or MOTOR_PY.get("reconferindo") or not componentes.estado_grupo(GRUPO)["ok"]:
        return

    def rodar():
        try:
            verificar_python()
        finally:
            MOTOR_PY["reconferindo"] = False
    MOTOR_PY["reconferindo"] = True
    threading.Thread(target=rodar, daemon=True).start()


# ------------------------------------------------------------------ saída de cada item
def jogo_de(it):
    return it.get("jogo_forcado") or it.get("jogo")


def planejar(it, op):
    """Origem, destino, caminho de saída e motivo de ignorar (sem tocar no disco)."""
    p = {"origem": None, "destino": None, "saida": None, "raiz_saida": None, "motivo": None}
    if it.get("erro"):
        p["motivo"] = "não foi possível ler a imagem"
        return p
    o = jogo_de(it)
    p["origem"] = o
    d = op["destino"] if op["destino"] in OUTRO else OUTRO[o]
    p["destino"] = d
    if d == o:
        p["motivo"] = f"já está no layout do {NOME[d]}"
        return p
    if op["saida"]:
        rs = os.path.abspath(op["saida"])
    elif it.get("recebido"):
        p["motivo"] = "escolha a pasta de saída (arquivo arrastado para a janela)"
        return p
    elif it["de_pasta"]:
        rs = it["raiz"].rstrip("\\/") + "_" + d.upper()
    else:
        rs = os.path.join(os.path.dirname(it["caminho"]), "Convertidos_" + d.upper())
    rel_dir = os.path.dirname(it["rel"]) if it["de_pasta"] else ""
    p["raiz_saida"] = rs
    p["saida"] = os.path.normpath(os.path.join(rs, rel_dir, it["nome_saida"]))
    if os.path.normcase(p["saida"]) == os.path.normcase(os.path.abspath(it["caminho"])):
        p["motivo"] = "a saída seria o próprio arquivo de entrada: escolha outra pasta de saída"
    elif it["de_pasta"]:
        raiz = os.path.abspath(it["raiz"])
        if os.path.normcase(os.path.commonpath([os.path.abspath(rs), raiz])) == os.path.normcase(raiz):
            p["motivo"] = "a pasta de saída não pode ficar dentro da pasta de entrada"
    return p


def item_publico(it, op):
    pl = planejar(it, op)
    d = {k: it.get(k) for k in ("id", "caminho", "rel", "raiz", "de_pasta", "recebido", "jogo", "jogo_forcado", "confianca",
                                "notas", "tipo", "largura", "altura", "canais", "erro", "estado", "avisos", "mensagem",
                                "segundos", "saida_feita", "feito", "notas_saida")}
    d.update(origem=pl["origem"], destino=pl["destino"], saida=pl["saida"], motivo=pl["motivo"],
             existe=bool(pl["saida"] and os.path.exists(pl["saida"])))
    return d


def estado_payload():
    reconferir_motor()
    op = PREFS.ler()
    with LOCK:
        itens = [item_publico(it, op) for it in ITENS.values()]
        job = {k: JOB[k] for k in ("rodando", "total", "feitos", "atual", "inicio", "fim", "resumo", "cancelado", "mensagem")}
    return {"itens": itens, "job": job, "opcoes": op, "ambiente": dict(MOTOR_PY, cmd=None), "referencias": REF.estado()}


# ------------------------------------------------------------------ rotas
def api_inicio(_):
    return {"versao": VERSAO, **estado_payload()}


def api_estado(_):
    return estado_payload()


def api_opcoes(d):
    op = PREFS.ler()
    for k in ("saida", "destino", "tamanho", "tipo", "sobrescrever"):
        if k in d:
            op[k] = d[k]
    op["tamanho"] = int(op.get("tamanho") or 0)
    if op["destino"] not in ("auto", "fc26", "fc27") or op["tipo"] not in ("auto", "cor", "normal") \
            or op["tamanho"] not in (0, 1024, 2048, 4096):
        raise base.ErroUsuario("Opção inválida.")
    if op["saida"]:
        op["saida"] = os.path.normpath(op["saida"].strip().strip('"'))
    PREFS.gravar(op)
    return estado_payload()


def adicionar_caminhos(caminhos, recebido=False):
    caminhos = [os.path.abspath(c.strip().strip('"')) for c in caminhos if c and c.strip()]
    if not caminhos:
        return {"novos": 0, "outros": 0, **estado_payload()}
    for c in caminhos:
        if not os.path.exists(c):
            raise base.ErroUsuario(f"Não encontrado: {c}")
    REF.exigir()     # a identificação do layout usa as costuras dos corpos de referência
    proc = ponte("detectar", arquivo_temp("detectar.json", caminhos))
    novos = outros = 0
    with LOCK:
        existentes = {os.path.normcase(it["caminho"]) for it in ITENS.values()}
    for ev in eventos(proc):
        if ev["tipo"] == "imagem":
            if os.path.normcase(ev["caminho"]) in existentes:
                continue
            i = next(SEQ)
            it = {"id": i, "caminho": ev["caminho"], "rel": ev["rel"], "raiz": ev["raiz"], "de_pasta": ev["de_pasta"],
                  "recebido": recebido, "jogo": ev.get("jogo"), "jogo_forcado": None, "confianca": ev.get("confianca"),
                  "notas": ev.get("notas"), "tipo": ev.get("tipo_tex"), "largura": ev.get("largura"), "altura": ev.get("altura"),
                  "canais": ev.get("canais"), "nome_saida": ev.get("nome_saida") or os.path.basename(ev["caminho"]),
                  "erro": ev.get("erro"), "estado": "pronto", "avisos": [], "mensagem": None}
            with LOCK:
                ITENS[i] = it
            existentes.add(os.path.normcase(ev["caminho"]))
            novos += 1
        elif ev["tipo"] == "pasta":
            outros += len(ev["outros"])
        elif ev["tipo"] == "falha":
            raise base.ErroUsuario("Falha ao ler as texturas: " + ev["erro"])
    proc.wait()
    if not recebido:
        PREFS.atualizar(ultima_pasta=os.path.dirname(caminhos[0]) if os.path.isfile(caminhos[0]) else caminhos[0])
    return {"novos": novos, "outros": outros, **estado_payload()}


def api_adicionar(d):
    return adicionar_caminhos(d.get("caminhos") or [])


def api_dialogo(d):
    op = PREFS.ler()
    inicial = d.get("inicial") or op.get("ultima_pasta") or base.raiz_trabalho()
    if d.get("modo") == "arquivos":
        r = base.dialogo("abrir", "Escolha as texturas do corpo (bodyupper)", inicial,
                         tipos=[("Imagens", "*.png;*.dds;*.tga;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff"), ("Todos", "*.*")], multiplo=True)
        return {"caminhos": r or []}
    titulo = "Pasta de saída das texturas convertidas" if d.get("modo") == "saida" else "Pasta com texturas do corpo"
    r = base.dialogo("pasta", titulo, op.get("saida") if d.get("modo") == "saida" and op.get("saida") else inicial)
    return {"caminhos": [r] if r else []}


def api_receber(d):
    """Arquivos arrastados para a janela: o navegador não informa o caminho, então são gravados numa pasta de recebidos."""
    pasta = os.path.join(CACHE, "recebidos", time.strftime("%Y%m%d_%H%M%S"))
    caminhos = []
    for a in d.get("arquivos", []):
        nome = os.path.basename(a["nome"])
        if not nome.lower().endswith(EXT):
            continue
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, nome)
        with open(destino, "wb") as f:
            f.write(base64.b64decode(a["dados"]))
        caminhos.append(destino)
    if not caminhos:
        raise base.ErroUsuario("Arraste imagens (.png, .dds, .tga…) da textura do corpo.")
    return adicionar_caminhos(caminhos, recebido=True)


def api_remover(d):
    with LOCK:
        if JOB["rodando"]:
            raise base.ErroUsuario("Espere a conversão terminar.")
        ids = set(d.get("ids") or [])
        for i in list(ITENS):
            if d.get("todos") or i in ids:
                del ITENS[i]
    return estado_payload()


def api_forcar_jogo(d):
    """O usuário diz em qual layout a textura está (quando a identificação automática erra ou fica em dúvida)."""
    jogo = d.get("jogo")
    if jogo not in (None, "fc26", "fc27"):
        raise base.ErroUsuario("Jogo inválido.")
    with LOCK:
        for i in d.get("ids") or []:
            it = ITENS.get(i)
            if it and not it.get("erro"):
                it["jogo_forcado"] = jogo if jogo != it.get("jogo") else None
                if it["estado"] in ("ok", "erro", "ignorado"):
                    it.update(estado="pronto", mensagem=None, avisos=[])
    return estado_payload()


def api_converter(d):
    REF.exigir()
    op = PREFS.ler()
    with LOCK:
        if JOB["rodando"]:
            raise base.ErroUsuario("Já há uma conversão em andamento.")
        ids = d.get("ids") or list(ITENS)
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
            it.update(estado="na_fila", mensagem=None, avisos=[], notas_saida=[], saida_feita=None, feito=None)
            fila.append({"id": i, "entrada": it["caminho"], "saida": pl["saida"], "origem": pl["origem"],
                         "destino": pl["destino"], "tipo": op["tipo"], "_raiz_saida": pl["raiz_saida"]})
        if not fila:
            return {"iniciado": False, "ignorados": ignorados, **estado_payload()}
        JOB.update(rodando=True, total=len(fila), feitos=0, atual=None, inicio=time.time(), fim=0, resumo=None,
                   cancelado=False, mensagem=None)
    threading.Thread(target=rodar_conversao, args=(fila, op), daemon=True).start()
    return {"iniciado": True, "ignorados": ignorados, **estado_payload()}


def rodar_conversao(fila, op):
    cont = collections.Counter()
    por_raiz = collections.defaultdict(list)
    try:
        job = {"tamanho": op["tamanho"], "itens": [{k: v for k, v in f.items() if not k.startswith("_")} for f in fila]}
        proc = ponte("converter", arquivo_temp("converter.json", job))
        JOB["proc"] = proc
        raiz_de = {f["id"]: f["_raiz_saida"] for f in fila}
        for ev in eventos(proc):
            with LOCK:
                it = ITENS.get(ev.get("id"))
                if ev["tipo"] == "inicio" and it:
                    it["estado"] = "convertendo"
                    JOB.update(atual=ev["id"], mensagem=None)
                elif ev["tipo"] == "progresso" and it:
                    JOB["mensagem"] = ev["msg"]
                elif ev["tipo"] == "ok" and it:
                    it.update(estado="ok", saida_feita=ev["saida"], avisos=ev["avisos"], notas_saida=ev.get("notas", []), segundos=ev["s"],
                              feito={"origem": ev["origem"], "destino": ev["destino"], "tipo": ev["tipo_tex"],
                                     "entrada_px": ev["entrada_px"], "saida_px": ev["saida_px"]})
                    JOB.update(feitos=JOB["feitos"] + 1, mensagem=None)
                    cont["convertidos"] += 1
                    cont["avisos"] += len(ev["avisos"])
                    linhas = [f"OK        {it['rel']} -> {os.path.relpath(ev['saida'], raiz_de[it['id']])}  "
                              f"({NOME[ev['origem']]} -> {NOME[ev['destino']]}, {'normal' if ev['tipo_tex'] == 'normal' else 'cor'}, "
                              f"{ev['entrada_px'][0]}x{ev['entrada_px'][1]} -> {ev['saida_px'][0]}x{ev['saida_px'][1]}, {ev['s']} s)"]
                    linhas += [f"              AVISO: {a}" for a in ev["avisos"]]
                    linhas += [f"              nota: {a}" for a in ev.get("notas", [])]
                    por_raiz[raiz_de[it["id"]]] += linhas
                elif ev["tipo"] == "erro" and it:
                    it.update(estado="erro", mensagem=ev["erro"], segundos=ev["s"])
                    JOB.update(feitos=JOB["feitos"] + 1, mensagem=None)
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
    except Exception as ex:  # noqa: BLE001
        cont["erros"] += 1
        with LOCK:
            for f in fila:
                x = ITENS.get(f["id"])
                if x and x["estado"] in ("na_fila", "convertendo"):
                    x.update(estado="erro", mensagem=str(ex))
    finally:
        resumo = f"Convertidas: {cont['convertidos']}   Avisos: {cont['avisos']}   Erros: {cont['erros']}"
        for rs, linhas in por_raiz.items():
            try:
                os.makedirs(rs, exist_ok=True)
                with open(os.path.join(rs, "relatorio_conversao_corpos.txt"), "a", encoding="utf-8") as fh:
                    fh.write(f"Conversor de Corpos FC 26 <-> FC 27 {VERSAO} - {time.strftime('%d/%m/%Y %H:%M')}\n\n")
                    fh.write("\n".join(linhas) + "\n\n" + resumo + "\n\n")
            except OSError:
                pass
        with LOCK:
            JOB.update(rodando=False, atual=None, fim=time.time(), proc=None, mensagem=None,
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
        alvo = PREFS.ler()["saida"]
        if not alvo:
            raise base.ErroUsuario("Sem pasta de saída definida: cada textura vai para a pasta ao lado da entrada.")
    if not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def api_relatorio(_):
    with LOCK:
        pastas = list((JOB.get("resumo") or {}).get("pastas") or [])
    for p in pastas:
        arq = os.path.join(p, "relatorio_conversao_corpos.txt")
        if os.path.isfile(arq):
            base.abrir_no_explorer(arq, selecionar=True)
            return {}
    raise base.ErroUsuario("Nenhum relatório ainda.")


def api_malha(q):
    jogo = q.get("jogo")
    if jogo not in OUTRO:
        raise base.ErroUsuario("Jogo inválido.")
    if jogo not in MALHAS:
        REF.exigir()
        proc = ponte("malha", jogo)
        for ev in eventos(proc):
            if ev["tipo"] == "malha":
                MALHAS[jogo] = {k: ev[k] for k in ("V", "UV", "T")}
            elif ev["tipo"] == "falha":
                raise base.ErroUsuario(ev["erro"])
        proc.wait()
        if jogo not in MALHAS:
            raise base.ErroUsuario("Não foi possível ler o corpo de referência.")
    return MALHAS[jogo]


def previa_png(caminho):
    """PNG reduzido (até 1024 px) da textura, para a prévia; guardado enquanto o arquivo não muda."""
    chave = (os.path.normcase(caminho), os.path.getmtime(caminho))
    p = PREVIAS.get(chave)
    if p and os.path.isfile(p):
        return p
    destino = os.path.join(CACHE, "previas", f"{len(PREVIAS) + 1}_{int(time.time() * 1000)}.png")
    proc = ponte("previa", arquivo_temp("previa.json", {"entrada": caminho, "saida": destino}))
    erro = None
    for ev in eventos(proc):
        if ev["tipo"] == "falha":
            erro = ev["erro"]
    proc.wait()
    if erro or not os.path.isfile(destino):
        raise base.ErroUsuario(erro or "Não foi possível gerar a prévia.")
    PREVIAS[chave] = destino
    return destino


def esp_imagem(h, q):
    """GET /imagem?id=&qual=entrada|saida — a textura reduzida (PNG)."""
    with LOCK:
        it = ITENS.get(int(q.get("id") or 0))
    if it is None:
        raise base.ErroUsuario("Textura não encontrada na lista.")
    caminho = it.get("saida_feita") if q.get("qual") == "saida" else it["caminho"]
    if not caminho or not os.path.isfile(caminho):
        raise base.ErroUsuario("Arquivo não encontrado.")
    h.arquivo(previa_png(caminho))


ROTAS_GET = {"inicio": api_inicio, "estado": api_estado, "malha": api_malha, "versao": lambda _: {"versao": VERSAO}}
ROTAS_POST = {"opcoes": api_opcoes, "adicionar": api_adicionar, "dialogo": api_dialogo, "receber": api_receber,
              "remover": api_remover, "forcar_jogo": api_forcar_jogo, "converter": api_converter, "cancelar": api_cancelar,
              "abrir": api_abrir, "relatorio": api_relatorio}
for _G, _P in (base.rotas_componentes(GRUPO, ao_concluir=verificar_python), REF.rotas(ao_importar=preparar_mapas)):
    ROTAS_GET.update(_G)
    ROTAS_POST.update(_P)


def main():
    ap = argparse.ArgumentParser(description="Conversor de Corpos FC 26 <-> FC 27 (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8777)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("entradas", nargs="*", help="texturas ou pastas para já entrar na lista")
    a = ap.parse_args()

    def preparar():
        verificar_python()
        preparar_mapas()
        if a.entradas and MOTOR_PY["ok"]:
            try:
                adicionar_caminhos(a.entradas)
            except base.ErroUsuario as ex:
                print(ex, flush=True)
    threading.Thread(target=preparar, daemon=True).start()   # a janela abre já; o ambiente aparece em seguida
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, especiais={"/imagem": esp_imagem},
                                 nome="ConversorCorpos/" + VERSAO)
    base.servir(handler, a.porta, "Conversor de Corpos", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
