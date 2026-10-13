"""Criador de Minifaces (BRFP Super Tool) — servidor local da interface.

    python servidor.py [--porta 8773] [--sem-janela]

A interface roda em Python padrão; o processamento de imagem (OpenCV) roda em motor/minifaces.py com o Python 3.12
("py -3.12"), aberto uma vez como processo de trabalho (um pedido JSON por linha). Os times e jogadores vêm do banco
importado no Super Tool (Dados do jogo): cada foto é ligada a um jogador do time escolhido e exportada como p<ID>.png.
"""
import argparse
import base64
import collections
import difflib
import itertools
import json
import os
import re
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, "cache")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import componentes  # noqa: E402
import dados  # noqa: E402
import referencias  # noqa: E402

VERSAO = "1.3"
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "saida": "", "lado": 180, "sobrescrever": False, "sem_ligacao": "pular", "teamid": None, "fundo_padrao": "auto",
    "ultima_pasta": ""})
EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
# miniface do Messi tirada do jogo (comparação sobreposta): não vem no pacote leve
REF = referencias.Referencias("Criador de Minifaces", {
    "referencia_p158023.png": os.path.join(AQUI, "web", "referencia_p158023.png")}, "comparar com uma miniface do jogo")
LOCK = threading.RLock()
ITENS = collections.OrderedDict()
SEQ = itertools.count(1)
FILA = []                       # ids a analisar
EXPORT = {"rodando": False, "total": 0, "feitos": 0, "erros": 0, "fim": 0, "pasta": None, "resumo": None}
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PARAMS_PADRAO = {"rosto": None, "ajuste": {"zoom": 1.0, "dx": 0, "dy": 0}, "fundo": "auto", "limpeza": 0.35, "tracos": []}


# ------------------------------------------------------------------ motor (Python 3.12 + OpenCV)
class Motor:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self.ok = False
        self.instalar = False
        self.msg = "verificando…"
        self.seq = itertools.count(1)

    def iniciar(self):
        """Motor: o Python embutido do Super Tool com OpenCV/Pillow/numpy; senão um Python do computador que os tenha."""
        cmd, desc = componentes.python_para("minifaces")
        for cmd in [cmd] if cmd else []:
            try:
                p = subprocess.Popen(cmd + ["-X", "utf8", os.path.join(AQUI, "motor", "minifaces.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     errors="replace", creationflags=SEM_JANELA)
            except OSError:
                continue
            linha = p.stdout.readline()
            try:
                info = json.loads(linha)
            except ValueError:
                p.kill()
                continue
            if info.get("pronto"):
                self.proc, self.ok, self.instalar = p, True, False
                self.msg = f"OpenCV {info.get('opencv')} · {desc}"
                return True
        self.ok, self.instalar = False, True
        self.msg = componentes.falta_msg("minifaces")
        return False

    def reiniciar(self):
        """Depois de instalar os componentes: sobe o motor e reanalisa as fotos que falharam por falta dele."""
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
            self.proc = None
            componentes.python_para("minifaces", forcar=True)
            self.iniciar()
        if self.ok:
            with LOCK:
                for it in ITENS.values():
                    if it["estado"] == "erro" and it["id"] not in FILA:
                        it.update(estado="analisando", erro=None)
                        FILA.append(it["id"])
            disparar_analise()

    def pedir(self, q, tentativas=2):
        with self.lock:
            for _ in range(tentativas):
                if not self.proc or self.proc.poll() is not None:
                    if not self.iniciar():
                        raise base.ErroUsuario(self.msg)
                q = dict(q, id=next(self.seq))
                try:
                    self.proc.stdin.write(json.dumps(q) + "\n")
                    self.proc.stdin.flush()
                    r = json.loads(self.proc.stdout.readline())
                except (OSError, ValueError):
                    self.proc = None
                    continue
                if "erro" in r:
                    raise base.ErroUsuario(r["erro"])
                return r
            raise base.ErroUsuario("O motor de imagem parou. Tente de novo.")


MOTOR = Motor()
_RECONF = {"ativo": False}


def reconferir_motor():
    """Pacotes instalados por outra janela (Super Tool ou outra ferramenta): sobe o motor uma vez."""
    if MOTOR.ok or not MOTOR.instalar or _RECONF["ativo"] or not componentes.estado_grupo("minifaces")["ok"]:
        return

    def rodar():
        try:
            MOTOR.reiniciar()
        finally:
            _RECONF["ativo"] = False
    _RECONF["ativo"] = True
    threading.Thread(target=rodar, daemon=True).start()


# ------------------------------------------------------------------ itens
def novo_item(caminho, recebido=False):
    i = next(SEQ)
    it = {"id": i, "caminho": caminho, "nome": os.path.basename(caminho), "recebido": recebido, "estado": "analisando",
          "analise": None, "foto": None, "params": json.loads(json.dumps(PARAMS_PADRAO)), "jogador": None, "erro": None,
          "exportado": None, "previa": None}
    it["params"]["fundo"] = PREFS.ler().get("fundo_padrao", "auto")
    ITENS[i] = it
    FILA.append(i)
    return it


def analisar_fila():
    while True:
        with LOCK:
            if not FILA:
                return
            i = FILA.pop(0)
            it = ITENS.get(i)
        if not it:
            continue
        try:
            a = MOTOR.pedir({"cmd": "analisar", "caminho": it["caminho"], "maximo": 900})
            foto = a.pop("foto")
            with LOCK:
                it.update(analise=a, foto=foto, estado="pronto" if a["rosto"] else "sem_rosto", erro=None)
                if not a["rosto"]:
                    it["erro"] = "Rosto não encontrado: arraste o quadro sobre o rosto na foto."
            g = MOTOR.pedir({"cmd": "gerar", "caminho": it["caminho"], "params": params_motor(it)}) if a["rosto"] else None
            if g:
                with LOCK:
                    it["previa"] = g["png"]
                    it["janela"] = g["janela"]
        except base.ErroUsuario as ex:
            with LOCK:
                it.update(estado="erro", erro=str(ex))
        ligar_auto_um(it)


_ANALISADOR = {"t": None}


def disparar_analise():
    t = _ANALISADOR["t"]
    if t is None or not t.is_alive():
        _ANALISADOR["t"] = threading.Thread(target=analisar_fila, daemon=True)
        _ANALISADOR["t"].start()


def params_motor(it):
    p = it["params"]
    return {"rosto": p["rosto"], "ajuste": p["ajuste"], "fundo": p["fundo"], "limpeza": p["limpeza"], "tracos": p["tracos"],
            "lado": int(PREFS.ler().get("lado", 180))}


def publico(it, com_foto=False):
    d = {k: it.get(k) for k in ("id", "caminho", "nome", "recebido", "estado", "analise", "params", "jogador", "erro",
                                "exportado", "previa", "janela")}
    if com_foto:
        d["foto"] = it.get("foto")
    d["saida"] = nome_saida(it)
    return d


def nome_saida(it):
    op = PREFS.ler()
    if not op["saida"]:
        return None
    if it.get("jogador"):
        return os.path.join(op["saida"], f"p{it['jogador']['playerid']}.png")
    if op["sem_ligacao"] == "nome":
        return os.path.join(op["saida"], os.path.splitext(it["nome"])[0] + ".png")
    return None


# ------------------------------------------------------------------ ligação com os jogadores (nome do arquivo x elenco)
PALAVRAS_FORA = {"de", "da", "do", "dos", "das", "e", "fundo", "poluido", "foto", "png", "jpg", "final", "copy", "copia", "novo"}


def tokens_arquivo(nome):
    s = os.path.splitext(nome)[0]
    s = re.sub(r"\d{2,4}x\d{2,4}", " ", s)          # ARTHUR-569x1536
    s = dados.normalizar(s)
    return [t for t in s.split() if not t.isdigit() and t not in PALAVRAS_FORA and len(t) > 1]


def pontuar(tk, j):
    """Semelhança (0..1) entre o nome do arquivo e o jogador. Nome exato completo/de camisa vale mais que só o primeiro
    nome ("matheuzinho" -> Matheuzinho, não Matheus Pereira); iniciais também contam ("gh" -> Gustavo Henrique)."""
    alvo = " ".join(tk)
    if not alvo:
        return 0.0
    prim, sob = j.get("primeiro", "") or "", j.get("sobrenome", "") or ""
    nomes = [(j.get("comum"), 1.0), (j.get("nome"), 1.0), (f"{prim} {sob}", 1.0), (j.get("camisa"), 0.98), (sob, 0.96), (prim, 0.92)]
    melhor = 0.0
    for n, peso in nomes:
        n = dados.normalizar(n or "")
        if not n:
            continue
        cn = n.split()
        r = difflib.SequenceMatcher(None, alvo, n).ratio() * 0.95
        inter = len(set(tk) & set(cn))
        if inter:
            r = max(r, 0.6 + 0.35 * inter / max(len(tk), len(cn)))
        if len(alvo) >= 4 and min(len(alvo), len(n)) >= 4 and (n.startswith(alvo) or alvo.startswith(n)):
            r = max(r, 0.8)
        if n == alvo:
            r = 1.0
        melhor = max(melhor, r * peso)
    # iniciais (gh, jp, rb…)
    if len(tk) == 1 and 2 <= len(tk[0]) <= 3:
        completo = dados.normalizar(f"{prim} {sob}").split()
        if len(completo) >= 2 and "".join(p[0] for p in completo) == tk[0]:
            melhor = max(melhor, 0.75)
    return melhor


def elenco_atual():
    op = PREFS.ler()
    b = dados.banco_atual()
    if not b or not op.get("teamid"):
        return []
    try:
        return b.jogadores_do_time(op["teamid"])
    except (dados.ErroDados, KeyError):
        return []


def ligar_auto(manter_manual=True):
    """Liga cada foto ao jogador mais parecido do time escolhido (cada jogador uma vez só)."""
    elenco = elenco_atual()
    with LOCK:
        itens = [it for it in ITENS.values() if not (manter_manual and it.get("jogador") and it["jogador"].get("manual"))]
        usados = {it["jogador"]["playerid"] for it in ITENS.values() if it.get("jogador") and it["jogador"].get("manual")}
        for it in itens:
            it["jogador"] = None
        pares = []
        for it in itens:
            tk = tokens_arquivo(it["nome"])
            for j in elenco:
                sc = pontuar(tk, j)
                if sc >= 0.55:
                    pares.append((sc, it["id"], j))
        pares.sort(key=lambda x: -x[0])
        feitos = set()
        for sc, iid, j in pares:
            if iid in feitos or j["playerid"] in usados:
                continue
            ITENS[iid]["jogador"] = {"playerid": j["playerid"], "nome": j["nome"], "confianca": round(sc, 2), "manual": False,
                                     "camisa": j.get("camisa_num", "")}
            feitos.add(iid)
            usados.add(j["playerid"])
    return len(feitos)


def ligar_auto_um(it):
    if it.get("jogador") or not PREFS.ler().get("teamid"):
        return
    elenco = elenco_atual()
    with LOCK:
        usados = {x["jogador"]["playerid"] for x in ITENS.values() if x.get("jogador")}
        tk = tokens_arquivo(it["nome"])
        melhor = max(((pontuar(tk, j), j) for j in elenco if j["playerid"] not in usados), key=lambda x: x[0], default=(0, None))
        if melhor[1] is not None and melhor[0] >= 0.55:
            j = melhor[1]
            it["jogador"] = {"playerid": j["playerid"], "nome": j["nome"], "confianca": round(melhor[0], 2), "manual": False,
                             "camisa": j.get("camisa_num", "")}


# ------------------------------------------------------------------ rotas
def estado_payload():
    reconferir_motor()
    recebidas = consumir_fila_criador()
    op = PREFS.ler()
    with LOCK:
        itens = [publico(it) for it in ITENS.values()]
        exp = dict(EXPORT)
        analisando = len(FILA) + sum(1 for it in ITENS.values() if it["estado"] == "analisando")
    d = dados.estado()
    time_sel = None
    b = dados.banco_atual()
    if b and op.get("teamid"):
        time_sel = next((t for t in b.times(dados.idioma_atual()) if t["teamid"] == str(op["teamid"])), None)
    return {"itens": itens, "opcoes": op, "export": exp, "analisando": analisando, "motor": {"ok": MOTOR.ok, "msg": MOTOR.msg, "instalar": MOTOR.instalar},
            "banco": d["banco"], "time": time_sel, "do_criador": recebidas}


def api_inicio(_):
    return {"versao": VERSAO, **estado_payload()}


def api_estado(_):
    return estado_payload()


def api_item(q):
    with LOCK:
        it = ITENS.get(int(q["id"]))
        if not it:
            raise base.ErroUsuario("Foto não encontrada na lista.")
        return publico(it, com_foto=True)


def adicionar(caminhos, recebido=False):
    novos = 0
    with LOCK:
        existentes = {os.path.normcase(it["caminho"]) for it in ITENS.values()}
        for c in caminhos:
            c = os.path.abspath(c.strip().strip('"'))
            arqs = []
            if os.path.isdir(c):
                for raiz, _, nomes in os.walk(c):
                    arqs += [os.path.join(raiz, n) for n in sorted(nomes) if n.lower().endswith(EXT)]
            elif os.path.isfile(c) and c.lower().endswith(EXT):
                arqs = [c]
            for a in arqs:
                if os.path.normcase(a) in existentes:
                    continue
                novo_item(a, recebido)
                existentes.add(os.path.normcase(a))
                novos += 1
    if caminhos and not recebido:
        c0 = os.path.abspath(caminhos[0])
        PREFS.atualizar(ultima_pasta=c0 if os.path.isdir(c0) else os.path.dirname(c0))
    disparar_analise()
    return {"novos": novos, **estado_payload()}


def api_adicionar(d):
    return adicionar(d.get("caminhos") or [])


# ------------------------------------------------------------------ fotos vindas do Criador de Ligas e Times
FILA_CRIADOR = os.path.join(os.environ.get("BRFP_DADOS") or os.path.join(os.path.dirname(os.path.dirname(AQUI)), "dados"),
                            "minifaces_fila.json")


def consumir_fila_criador():
    """O Criador de Ligas e Times deixa as fotos dos jogadores novos (já com o playerid) em dados/minifaces_fila.json:
    elas entram na lista ligadas a esses ids (os jogadores novos ainda não estão no banco importado)."""
    if not os.path.isfile(FILA_CRIADOR):
        return 0
    try:
        with open(FILA_CRIADOR, encoding="utf-8") as f:
            fila = json.load(f)
        os.remove(FILA_CRIADOR)
    except (OSError, ValueError):
        return 0
    novos = 0
    with LOCK:
        existentes = {os.path.normcase(it["caminho"]): it for it in ITENS.values()}
        for x in fila.get("itens") or []:
            c = os.path.abspath(x.get("caminho") or "")
            if not os.path.isfile(c) or not c.lower().endswith(EXT):
                continue
            it = existentes.get(os.path.normcase(c)) or novo_item(c)
            if os.path.normcase(c) not in existentes:
                novos += 1
            pid = str(x.get("playerid") or "")
            if pid.isdigit():
                for y in ITENS.values():
                    if y is not it and y.get("jogador") and y["jogador"]["playerid"] == pid:
                        y["jogador"] = None
                it["jogador"] = {"playerid": pid, "nome": x.get("nome") or f"ID {pid}", "confianca": 1.0, "manual": True,
                                 "camisa": str(x.get("camisa") or ""), "origem": x.get("time") or "Criador de Ligas e Times"}
            existentes[os.path.normcase(c)] = it
    if novos:
        disparar_analise()
    return novos


def api_dialogo(d):
    op = PREFS.ler()
    ini = op.get("ultima_pasta") or base.raiz_trabalho()
    if d.get("modo") == "arquivos":
        r = base.dialogo("abrir", "Fotos dos jogadores", ini, tipos=[("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Todos", "*.*")], multiplo=True)
        return {"caminhos": r or []}
    if d.get("modo") == "saida":
        r = base.dialogo("pasta", "Pasta de saída das minifaces (p<ID>.png)", op.get("saida") or ini)
        return {"caminhos": [r] if r else []}
    r = base.dialogo("pasta", "Pasta com as fotos dos jogadores", ini)
    return {"caminhos": [r] if r else []}


def api_receber(d):
    pasta = os.path.join(CACHE, "recebidos", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(pasta, exist_ok=True)
    caminhos = []
    for a in d.get("arquivos", []):
        nome = os.path.basename(a["nome"])
        if not nome.lower().endswith(EXT):
            continue
        destino = os.path.join(pasta, nome)
        with open(destino, "wb") as f:
            f.write(base64.b64decode(a["dados"]))
        caminhos.append(destino)
    if not caminhos:
        raise base.ErroUsuario("Arraste imagens (.png, .jpg, .webp…).")
    return adicionar(caminhos, recebido=True)


def api_remover(d):
    with LOCK:
        for i in list(ITENS):
            if d.get("todos") or i in set(d.get("ids") or []):
                del ITENS[i]
                if i in FILA:
                    FILA.remove(i)
    return estado_payload()


def api_params(d):
    """Atualiza os ajustes de uma foto (ou de várias) e devolve a prévia nova."""
    ids = d.get("ids") or [d["id"]]
    mudanca = d.get("params") or {}
    with LOCK:
        for i in ids:
            it = ITENS.get(int(i))
            if not it:
                continue
            for k, v in mudanca.items():
                if k == "ajuste":
                    it["params"]["ajuste"].update(v)
                elif k in PARAMS_PADRAO:
                    it["params"][k] = v
            if mudanca.get("rosto"):
                it["estado"] = "pronto"
                it["erro"] = None
    return api_gerar({"id": ids[0]}) if len(ids) == 1 else estado_payload()


def api_gerar(d):
    with LOCK:
        it = ITENS.get(int(d["id"]))
        if not it:
            raise base.ErroUsuario("Foto não encontrada na lista.")
        p = params_motor(it)
        if not p["rosto"] and not (it.get("analise") or {}).get("rosto"):
            raise base.ErroUsuario("Rosto não encontrado: arraste o quadro sobre o rosto na foto.")
        if not p["rosto"]:
            p["rosto"] = it["analise"]["rosto"]
    g = MOTOR.pedir({"cmd": "gerar", "caminho": it["caminho"], "params": p})
    with LOCK:
        it.update(previa=g["png"], janela=g["janela"])
        if it["estado"] in ("sem_rosto", "erro"):
            it["estado"], it["erro"] = "pronto", None
    return {"previa": g["png"], "janela": g["janela"], "rosto": g["rosto"], "item": publico(it)}


def api_restaurar(d):
    with LOCK:
        it = ITENS.get(int(d["id"]))
        if not it:
            raise base.ErroUsuario("Foto não encontrada na lista.")
        it["params"] = json.loads(json.dumps(PARAMS_PADRAO))
        it["params"]["fundo"] = PREFS.ler().get("fundo_padrao", "auto")
    return api_gerar(d)


def api_opcoes(d):
    op = PREFS.ler()
    for k in ("saida", "lado", "sobrescrever", "sem_ligacao", "fundo_padrao"):
        if k in d:
            op[k] = d[k]
    if op["saida"]:
        op["saida"] = os.path.normpath(str(op["saida"]).strip().strip('"'))
    op["lado"] = max(64, min(1024, int(op.get("lado") or 180)))
    PREFS.gravar(op)
    return estado_payload()


def api_times(_):
    b = dados.banco_atual()
    if not b:
        return {"times": [], "sem_banco": True}
    return {"times": b.times(dados.idioma_atual())}


def api_jogadores(q):
    b = dados.banco_atual()
    if not b:
        raise base.ErroUsuario("Importe o banco do jogo em Dados do jogo (Super Tool).")
    teamid = q.get("teamid") or PREFS.ler().get("teamid")
    return {"jogadores": b.jogadores_do_time(teamid) if teamid else []}


def api_time(d):
    PREFS.atualizar(teamid=d.get("teamid"))
    n = ligar_auto(manter_manual=False) if d.get("teamid") else 0
    if not d.get("teamid"):
        with LOCK:
            for it in ITENS.values():
                it["jogador"] = None
    return {"ligadas": n, **estado_payload()}


def api_ligar(d):
    with LOCK:
        it = ITENS.get(int(d["id"]))
        if not it:
            raise base.ErroUsuario("Foto não encontrada na lista.")
        pid = str(d.get("playerid") or "").strip()
        if not pid:
            it["jogador"] = None
        else:
            if not pid.isdigit():
                raise base.ErroUsuario("O ID do jogador é um número.")
            nome = d.get("nome") or ""
            if not nome:
                nome = next((j["nome"] for j in elenco_atual() if j["playerid"] == pid), "")
            for x in ITENS.values():      # um jogador só numa foto
                if x is not it and x.get("jogador") and x["jogador"]["playerid"] == pid:
                    x["jogador"] = None
            it["jogador"] = {"playerid": pid, "nome": nome or f"ID {pid}", "confianca": 1.0, "manual": True, "camisa": d.get("camisa", "")}
    return estado_payload()


def api_ligar_auto(_):
    n = ligar_auto(manter_manual=True)
    return {"ligadas": n, **estado_payload()}


def api_exportar(d):
    op = PREFS.ler()
    if not op["saida"]:
        raise base.ErroUsuario("Escolha a pasta de saída das minifaces.")
    with LOCK:
        if EXPORT["rodando"]:
            raise base.ErroUsuario("Já está exportando.")
        ids = d.get("ids") or list(ITENS)
        fila, pulados = [], []
        for i in ids:
            it = ITENS.get(i)
            if not it:
                continue
            dst = nome_saida(it)
            if it["estado"] not in ("pronto",):
                pulados.append((it["nome"], "sem rosto marcado" if it["estado"] == "sem_rosto" else it.get("erro") or it["estado"]))
            elif not dst:
                pulados.append((it["nome"], "sem jogador ligado"))
            elif os.path.exists(dst) and not op["sobrescrever"]:
                pulados.append((it["nome"], f"{os.path.basename(dst)} já existe"))
            else:
                fila.append((it, dst))
        EXPORT.update(rodando=bool(fila), total=len(fila), feitos=0, erros=0, fim=0, pasta=op["saida"], resumo=None)
    if fila:
        threading.Thread(target=rodar_export, args=(fila, pulados), daemon=True).start()
    else:
        EXPORT["resumo"] = {"exportadas": 0, "pulados": pulados, "erros": []}
    return {"iniciado": bool(fila), "pulados": pulados, **estado_payload()}


def rodar_export(fila, pulados):
    erros = []
    for it, dst in fila:
        try:
            p = params_motor(it)
            if not p["rosto"]:
                p["rosto"] = it["analise"]["rosto"]
            MOTOR.pedir({"cmd": "exportar", "caminho": it["caminho"], "params": p, "saida": dst})
            with LOCK:
                it["exportado"] = dst
                EXPORT["feitos"] += 1
        except base.ErroUsuario as ex:
            erros.append((it["nome"], str(ex)))
            with LOCK:
                EXPORT["erros"] += 1
                EXPORT["feitos"] += 1
    with LOCK:
        EXPORT.update(rodando=False, fim=time.time(),
                      resumo={"exportadas": len(fila) - len(erros), "pulados": pulados, "erros": erros})


def api_abrir(d):
    alvo = d.get("caminho") or PREFS.ler().get("saida")
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo or '(sem pasta de saída)'}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


ROTAS_GET = {"inicio": api_inicio, "estado": api_estado, "item": api_item, "times": api_times, "jogadores": api_jogadores,
             "versao": lambda _: {"versao": VERSAO}}
ROTAS_POST = {"adicionar": api_adicionar, "dialogo": api_dialogo, "receber": api_receber, "remover": api_remover,
              "params": api_params, "gerar": api_gerar, "restaurar": api_restaurar, "opcoes": api_opcoes, "time": api_time,
              "ligar": api_ligar, "ligar_auto": api_ligar_auto, "exportar": api_exportar, "abrir": api_abrir}
for _G, _P in (base.rotas_componentes("minifaces", ao_concluir=lambda: MOTOR.reiniciar()), REF.rotas()):
    ROTAS_GET.update(_G)
    ROTAS_POST.update(_P)


def main():
    ap = argparse.ArgumentParser(description="Criador de Minifaces (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8773)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("entradas", nargs="*", help="fotos ou pastas para já entrar na lista")
    a = ap.parse_args()

    def preparar():
        MOTOR.iniciar()
        if a.entradas:
            adicionar(a.entradas)
    threading.Thread(target=preparar, daemon=True).start()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, nome="CriadorMinifaces/" + VERSAO)
    base.servir(handler, a.porta, "Criador de Minifaces", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
