"""Conversor de Kits PES → FC (BRFP Super Tool) — servidor local da interface.

    python servidor.py [--porta 8780] [--sem-janela] [texturas ou pastas]

Converte kits do PES 2021 (a textura única com camisa, mangas, gola, calção e meião) em kits do FC 27: camisa, calção e
meião no layout do FC, na pasta do kit no formato do jogo (kit_<faixa>/<time>_<id>/<tipo>_<n>_<v>), com os mapas de
tecido e o hotspot de um kit base do FC 27. A interface roda em Python padrão; a conversão (numpy, SciPy e Pillow) roda
em motor/, chamada pela ponte (motor/ponte.py), que devolve um evento JSON por linha.
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
sys.path.insert(0, MOTOR)

import base  # noqa: E402
import componentes  # noqa: E402
import referencias  # noqa: E402
import kit_nomes as K  # noqa: E402

VERSAO = "1.1"
GRUPO = "corpos"                       # mesmos pacotes (numpy, SciPy e Pillow) do Conversor de Corpos
EXT = (".png", ".dds", ".tga", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "saida": "", "base": "", "escudo": "apagar", "tecido": "base", "substituir": False, "ultima_pasta": ""})
LOCK = threading.RLock()
ITENS = collections.OrderedDict()      # id -> item
JOB = {"rodando": False, "total": 0, "feitos": 0, "atual": None, "inicio": 0, "fim": 0, "proc": None, "resumo": None,
       "cancelado": False, "mensagem": None, "fracao": 0}
SEQ = itertools.count(1)
SEQ_PREVIA = itertools.count(1)
MOTOR_PY = {"cmd": None, "ok": False, "msg": "verificando…"}
PREVIAS = {}                           # (caminho, mtime) -> png reduzido
MALHAS = {}                            # jersey|shorts|socks|pes -> {V, UV, T}
BASE = {"pasta": None, "info": None, "erro": None}
TIMES = {"raiz": None, "quando": 0, "lista": []}
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# malhas dos dois jogos, só para a prévia 3D (tiradas dos jogos: não vêm no pacote leve; a conversão não precisa delas)
MALHA_ARQ = {"jersey": "jersey_0_0_0_0_1_0_0_mesh.fbx", "shorts": "shorts_0_0_0_mesh.fbx", "socks": "sock_0_0_1_0_0_mesh.fbx",
             "pes": "pes2021_kit.obj"}
REF = referencias.Referencias("Conversor de Kits PES → FC", {n: os.path.join(MOTOR, "referencia", n) for n in MALHA_ARQ.values()},
                              "mostrar os kits em 3D")


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


def ponte(comando, arg):
    if not MOTOR_PY["ok"]:
        raise base.ErroUsuario(MOTOR_PY["msg"])
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
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


# ------------------------------------------------------------------ kit base e times
def estado_base(op):
    """Confere a pasta do kit base (só os nomes dos arquivos: rápido)."""
    pasta = op.get("base") or ""
    if BASE["pasta"] != pasta:
        BASE.update(pasta=pasta, info=None, erro=None)
        if pasta:
            try:
                a = K.arquivos_base(pasta)
                BASE["info"] = {k: a[k] for k in ("pasta", "teamid", "tipo", "n", "v", "time", "sufixo")}
                BASE["info"]["arquivos"] = len(a["outros"]) + 4
            except K.ErroConversao as ex:
                BASE["erro"] = str(ex)
    return {"pasta": pasta, "ok": bool(BASE["info"]), "info": BASE["info"],
            "erro": BASE["erro"] if pasta else "Escolha a pasta de um kit do FC 27 exportado pelo FET (ex.: …\\kit\\kit_111000\\guarani_111329\\home_0_0)."}


def raiz_times(op):
    if op.get("saida"):
        return op["saida"]
    return K.raiz_kits(op.get("base")) if op.get("base") else None


def times(op):
    raiz = raiz_times(op)
    if raiz != TIMES["raiz"] or time.time() - TIMES["quando"] > 30:
        TIMES.update(raiz=raiz, quando=time.time(), lista=K.times_na_raiz(raiz) if raiz else [])
    return TIMES["lista"]


# ------------------------------------------------------------------ saída de cada item
def raiz_saida(it, op):
    if op["saida"]:
        return os.path.abspath(op["saida"])
    if it.get("recebido"):
        return None
    return os.path.join(it["raiz"] if it["de_pasta"] else os.path.dirname(it["caminho"]), "Kits FC 27")


def planejar(it, op, base_ok):
    """Pasta do kit e motivo de não converter (sem tocar no disco)."""
    p = {"saida": None, "rel": None, "raiz_saida": None, "motivo": None}
    if it.get("erro"):
        p["motivo"] = "não foi possível ler a imagem"
        return p
    rs = raiz_saida(it, op)
    if not str(it.get("teamid") or "").isdigit() or int(it["teamid"]) <= 0:
        p["motivo"] = "informe o ID do time (teamid) do FC 27"
    elif not (it.get("time") or "").strip():
        p["motivo"] = "informe o nome da pasta do time"
    elif it.get("tipo") not in K.TIPOS:
        p["motivo"] = "escolha o tipo do kit"
    if rs and str(it.get("teamid") or "").isdigit() and int(it["teamid"]) > 0 and it.get("tipo") in K.TIPOS:
        p["saida"], p["rel"], _ = K.destino_kit(rs, it["teamid"], it.get("time") or "time", it["tipo"], it.get("variacao") or 0)
        p["raiz_saida"] = rs
    if p["motivo"]:
        return p
    if not base_ok:
        p["motivo"] = "escolha o kit base do FC 27 (Saída e opções)"
    elif not rs:
        p["motivo"] = "escolha a pasta de saída (arquivo arrastado para a janela)"
    return p


def item_publico(it, op, base_ok):
    pl = planejar(it, op, base_ok)
    d = {k: it.get(k) for k in ("id", "caminho", "rel", "raiz", "de_pasta", "recebido", "largura", "altura", "quadrada", "erro",
                                "estado", "avisos", "mensagem", "segundos", "teamid", "time", "tipo", "variacao", "tipo_sugerido",
                                "saida_feita", "previas", "fracao")}
    d.update(saida=pl["saida"], rel_saida=pl["rel"], motivo=pl["motivo"], existe=bool(pl["saida"] and os.path.isdir(pl["saida"])))
    return d


def estado_payload():
    reconferir_motor()
    op = PREFS.ler()
    b = estado_base(op)
    with LOCK:
        itens = [item_publico(it, op, b["ok"]) for it in ITENS.values()]
        job = {k: JOB[k] for k in ("rodando", "total", "feitos", "atual", "inicio", "fim", "resumo", "cancelado", "mensagem", "fracao")}
    return {"itens": itens, "job": job, "opcoes": op, "base": b, "ambiente": dict(MOTOR_PY, cmd=None), "referencias": REF.estado(),
            "tipos": [{"id": k, "nome": v} for k, v in K.NOME_TIPO.items()]}


# ------------------------------------------------------------------ rotas
def api_inicio(_):
    return {"versao": VERSAO, **estado_payload()}


def api_estado(_):
    return estado_payload()


def api_times(_):
    op = PREFS.ler()
    return {"raiz": raiz_times(op), "times": times(op)}


def api_opcoes(d):
    op = PREFS.ler()
    for k in ("saida", "base", "escudo", "tecido", "substituir"):
        if k in d:
            op[k] = d[k]
    if op["escudo"] not in ("apagar", "base") or op["tecido"] not in ("base", "generico"):
        raise base.ErroUsuario("Opção inválida.")
    for k in ("saida", "base"):
        if op[k]:
            op[k] = os.path.normpath(op[k].strip().strip('"'))
    PREFS.gravar(op)
    TIMES["quando"] = 0
    return estado_payload()


def adicionar_caminhos(caminhos, recebido=False):
    caminhos = [os.path.abspath(c.strip().strip('"')) for c in caminhos if c and c.strip()]
    if not caminhos:
        return {"novos": 0, "outros": 0, **estado_payload()}
    for c in caminhos:
        if not os.path.exists(c):
            raise base.ErroUsuario(f"Não encontrado: {c}")
    proc = ponte("detectar", arquivo_temp("detectar.json", caminhos))
    novos = outros = 0
    with LOCK:
        existentes = {os.path.normcase(it["caminho"]) for it in ITENS.values()}
        ultimo = next(reversed(ITENS.values()), None)
    for ev in eventos(proc):
        if ev["tipo"] == "imagem":
            if os.path.normcase(ev["caminho"]) in existentes:
                continue
            i = next(SEQ)
            it = {"id": i, "caminho": ev["caminho"], "rel": ev["rel"], "raiz": ev["raiz"], "de_pasta": ev["de_pasta"],
                  "recebido": recebido, "largura": ev.get("largura"), "altura": ev.get("altura"), "quadrada": ev.get("quadrada"),
                  "erro": ev.get("erro"), "estado": "pronto", "avisos": [], "mensagem": None,
                  "tipo_sugerido": ev.get("tipo_sugerido"), "tipo": ev.get("tipo_sugerido") or "home", "variacao": 0,
                  # o time do último kit da lista (vários kits do mesmo time seguidos)
                  "teamid": ultimo["teamid"] if ultimo else "", "time": ultimo["time"] if ultimo else ""}
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
    modo = d.get("modo")
    if modo == "arquivos":
        r = base.dialogo("abrir", "Escolha as texturas dos kits do PES", inicial,
                         tipos=[("Imagens", "*.png;*.dds;*.tga;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff"), ("Todos", "*.*")], multiplo=True)
        return {"caminhos": r or []}
    if modo == "saida":
        r = base.dialogo("pasta", "Pasta dos kits (a pasta kit do mod, ou outra)", op.get("saida") or K.raiz_kits(op.get("base")) or inicial)
    elif modo == "base":
        r = base.dialogo("pasta", "Kit base do FC 27 exportado pelo FET (a pasta home_0_0, away_1_0…)",
                         op.get("base") or base.raiz_trabalho())
    else:
        r = base.dialogo("pasta", "Pasta com kits do PES", inicial)
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
        raise base.ErroUsuario("Arraste imagens (.png, .dds, .tga, .jpg…) da textura do kit do PES.")
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


def api_editar(d):
    """Time, tipo e variação de um ou mais kits da lista."""
    campos = {}
    if "teamid" in d:
        t = str(d["teamid"] or "").strip()
        if t and not t.isdigit():
            raise base.ErroUsuario("O ID do time é um número (teamid do banco do FC 27).")
        campos["teamid"] = t
    if "time" in d:
        campos["time"] = K.nome_pasta(d["time"]) if (d["time"] or "").strip() else ""
    if "tipo" in d:
        if d["tipo"] not in K.TIPOS:
            raise base.ErroUsuario("Tipo de kit inválido.")
        campos["tipo"] = d["tipo"]
    if "variacao" in d:
        try:
            campos["variacao"] = max(0, min(99, int(d["variacao"] or 0)))
        except (TypeError, ValueError):
            raise base.ErroUsuario("A variação é um número (0 = a normal).") from None
    with LOCK:
        if JOB["rodando"]:
            raise base.ErroUsuario("Espere a conversão terminar.")
        for i in d.get("ids") or []:
            it = ITENS.get(i)
            if it:
                it.update(campos)
                if it["estado"] in ("ok", "erro", "ignorado"):
                    it.update(estado="pronto", mensagem=None, avisos=[])
    return estado_payload()


def api_converter(d):
    op = PREFS.ler()
    b = estado_base(op)
    with LOCK:
        if JOB["rodando"]:
            raise base.ErroUsuario("Já há uma conversão em andamento.")
        if not b["ok"]:
            raise base.ErroUsuario(b["erro"] or "Escolha o kit base do FC 27.")
        ids = d.get("ids") or list(ITENS)
        fila, ignorados, destinos = [], 0, {}
        for i in ids:
            it = ITENS.get(i)
            if it is None:
                continue
            pl = planejar(it, op, True)
            if pl["motivo"]:
                it.update(estado="ignorado", mensagem=pl["motivo"])
                ignorados += 1
                continue
            chave = os.path.normcase(pl["saida"])
            if chave in destinos:
                it.update(estado="ignorado", mensagem=f"mesmo kit de destino que {ITENS[destinos[chave]]['rel']} (mude o tipo ou a variação)")
                ignorados += 1
                continue
            if os.path.isdir(pl["saida"]) and not op["substituir"]:
                it.update(estado="ignorado", mensagem="esse kit já existe na saída (ligue Substituir kits existentes)")
                ignorados += 1
                continue
            destinos[chave] = i
            it.update(estado="na_fila", mensagem=None, avisos=[], saida_feita=None, previas=None, fracao=0)
            fila.append({"id": i, "entrada": it["caminho"], "saida": pl["raiz_saida"], "teamid": int(it["teamid"]),
                         "time": it["time"], "tipo": it["tipo"], "variacao": it.get("variacao") or 0})
        if not fila:
            return {"iniciado": False, "ignorados": ignorados, **estado_payload()}
        JOB.update(rodando=True, total=len(fila), feitos=0, atual=None, inicio=time.time(), fim=0, resumo=None,
                   cancelado=False, mensagem=None, fracao=0)
    threading.Thread(target=rodar_conversao, args=(fila, op), daemon=True).start()
    return {"iniciado": True, "ignorados": ignorados, **estado_payload()}


def rodar_conversao(fila, op):
    cont = collections.Counter()
    por_raiz = collections.defaultdict(list)
    try:
        job = {"base": op["base"], "escudo": op["escudo"], "tecido": op["tecido"], "substituir": op["substituir"], "itens": fila}
        proc = ponte("converter", arquivo_temp("converter.json", job))
        JOB["proc"] = proc
        raiz_de = {f["id"]: f["saida"] for f in fila}
        for ev in eventos(proc):
            with LOCK:
                it = ITENS.get(ev.get("id"))
                if ev["tipo"] == "inicio" and it:
                    it["estado"] = "convertendo"
                    JOB.update(atual=ev["id"], mensagem=None, fracao=0)
                elif ev["tipo"] == "progresso" and it:
                    JOB.update(mensagem=ev["msg"], fracao=ev.get("f") or 0)
                    it["fracao"] = ev.get("f") or 0
                elif ev["tipo"] == "ok" and it:
                    it.update(estado="ok", saida_feita=ev["pasta"], previas=ev["previas"], avisos=ev["avisos"], segundos=ev["s"])
                    JOB.update(feitos=JOB["feitos"] + 1, mensagem=None)
                    cont["convertidos"] += 1
                    cont["avisos"] += len(ev["avisos"])
                    linhas = [f"OK        {it['rel']} -> {ev['rel']}  ({K.NOME_TIPO[it['tipo']]}, "
                              f"{ev['entrada_px'][0]}x{ev['entrada_px'][1]}, {ev['arquivos']} arquivos, {ev['s']} s)"]
                    linhas += [f"              AVISO: {a}" for a in ev["avisos"]]
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
                             mensagem="cancelado" if JOB["cancelado"] else "o motor parou antes deste kit")
    except Exception as ex:  # noqa: BLE001
        cont["erros"] += 1
        with LOCK:
            for f in fila:
                x = ITENS.get(f["id"])
                if x and x["estado"] in ("na_fila", "convertendo"):
                    x.update(estado="erro", mensagem=str(ex))
    finally:
        resumo = f"Convertidos: {cont['convertidos']}   Avisos: {cont['avisos']}   Erros: {cont['erros']}"
        for rs, linhas in por_raiz.items():
            try:
                os.makedirs(rs, exist_ok=True)
                with open(os.path.join(rs, "relatorio_conversao_kits_pes.txt"), "a", encoding="utf-8") as fh:
                    fh.write(f"Conversor de Kits PES -> FC {VERSAO} - {time.strftime('%d/%m/%Y %H:%M')}\n")
                    fh.write(f"Kit base: {op['base']}\n\n")
                    fh.write("\n".join(linhas) + "\n\n" + resumo + "\n\n")
            except OSError:
                pass
        TIMES["quando"] = 0
        with LOCK:
            JOB.update(rodando=False, atual=None, fim=time.time(), proc=None, mensagem=None, fracao=0,
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
            raise base.ErroUsuario("Sem pasta de saída definida: cada kit vai para “Kits FC 27”, ao lado da textura do PES.")
    if not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def api_relatorio(_):
    with LOCK:
        pastas = list((JOB.get("resumo") or {}).get("pastas") or [])
    for p in pastas:
        arq = os.path.join(p, "relatorio_conversao_kits_pes.txt")
        if os.path.isfile(arq):
            base.abrir_no_explorer(arq, selecionar=True)
            return {}
    raise base.ErroUsuario("Nenhum relatório ainda.")


def api_malha(q):
    qual = q.get("qual")
    if qual not in MALHA_ARQ:
        raise base.ErroUsuario("Malha inválida.")
    if qual not in MALHAS:
        if not os.path.isfile(REF.arquivos[MALHA_ARQ[qual]]):
            raise base.ErroUsuario(REF.msg([MALHA_ARQ[qual]]))
        proc = ponte("malha", qual)
        for ev in eventos(proc):
            if ev["tipo"] == "malha":
                MALHAS[qual] = {k: ev[k] for k in ("V", "UV", "T")}
            elif ev["tipo"] == "falha":
                raise base.ErroUsuario(ev["erro"])
        proc.wait()
        if qual not in MALHAS:
            raise base.ErroUsuario("Não foi possível ler a malha de referência.")
    return MALHAS[qual]


def previa_png(caminho):
    """PNG reduzido (até 1024 px) da textura, para a prévia; guardado enquanto o arquivo não muda."""
    chave = (os.path.normcase(caminho), os.path.getmtime(caminho))
    p = PREVIAS.get(chave)
    if p and os.path.isfile(p):
        return p
    n = next(SEQ_PREVIA)          # a prévia 3D pede as três peças ao mesmo tempo
    destino = os.path.join(CACHE, "previas", f"{n}_{int(time.time() * 1000)}.png")
    proc = ponte("previa", arquivo_temp(f"previa_{n}.json", {"entrada": caminho, "saida": destino}))
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
    """GET /imagem?id=&qual=entrada|jersey|shorts|socks — a textura reduzida (PNG)."""
    with LOCK:
        it = ITENS.get(int(q.get("id") or 0))
    if it is None:
        raise base.ErroUsuario("Kit não encontrado na lista.")
    qual = q.get("qual") or "entrada"
    caminho = it["caminho"] if qual == "entrada" else (it.get("previas") or {}).get(qual)
    if not caminho or not os.path.isfile(caminho):
        raise base.ErroUsuario("Arquivo não encontrado.")
    h.arquivo(previa_png(caminho))


ROTAS_GET = {"inicio": api_inicio, "estado": api_estado, "malha": api_malha, "times": api_times, "versao": lambda _: {"versao": VERSAO}}
ROTAS_POST = {"opcoes": api_opcoes, "adicionar": api_adicionar, "dialogo": api_dialogo, "receber": api_receber,
              "remover": api_remover, "editar": api_editar, "converter": api_converter, "cancelar": api_cancelar,
              "abrir": api_abrir, "relatorio": api_relatorio}
for _G, _P in (base.rotas_componentes(GRUPO, ao_concluir=verificar_python), REF.rotas(ao_importar=MALHAS.clear)):
    ROTAS_GET.update(_G)
    ROTAS_POST.update(_P)


def main():
    ap = argparse.ArgumentParser(description="Conversor de Kits PES → FC (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8780)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("entradas", nargs="*", help="texturas ou pastas para já entrar na lista")
    a = ap.parse_args()

    def preparar():
        verificar_python()
        if a.entradas and MOTOR_PY["ok"]:
            try:
                adicionar_caminhos(a.entradas)
            except base.ErroUsuario as ex:
                print(ex, flush=True)
    threading.Thread(target=preparar, daemon=True).start()   # a janela abre já; o ambiente aparece em seguida
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, especiais={"/imagem": esp_imagem},
                                 nome="ConversorKitsPES/" + VERSAO)
    base.servir(handler, a.porta, "Conversor de Kits PES → FC", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
