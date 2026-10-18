"""Criador de Kits (BRFP Super Tool) — servidor local da interface.

    python servidor.py [--porta 8779] [--sem-janela] [foto]

Monta um kit do FC 27 (camisa, calção, meião, escudo, marca e hotspot) a partir de um kit doador exportado pelo FET:
recolore o doador, desenha o padrão do tronco e os logos. Uma foto da camisa preenche cores, padrão e logos sozinha.
A interface roda em Python padrão; o processamento (numpy, SciPy, Pillow e OpenCV) roda num processo do motor que fica
aberto (motor/ponte.py servico) e responde um JSON por linha.
"""
import argparse
import base64
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.join(AQUI, "motor")
CACHE = os.path.join(AQUI, "cache")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import componentes  # noqa: E402
import referencias  # noqa: E402

VERSAO = "1.0"
GRUPO = "kits"
IMG = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".tif", ".tiff", ".gif", ".dds")
PECAS = ("jersey", "shorts", "socks")
TIPOS = ("home", "away", "goalie_home", "third", "fourth")
PADROES = ("lisa", "listras_v", "listras_h", "xadrez", "metades", "faixa_diagonal", "faixa_peito", "v", "degrade")
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "biblioteca": "", "saida": "", "ultima_pasta": "", "mapas": "doador"})
LOCK = threading.RLock()
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MOTOR_PY = {"cmd": None, "ok": False, "msg": "verificando…"}
ESTADO = {"projeto": None, "doador": None, "analise": None, "foto": None}
JOB = {"rodando": False, "progresso": 0.0, "mensagem": None, "resumo": None, "erro": None, "inicio": 0, "fim": 0}
BIB = {"pasta": None, "kits": [], "lendo": False}
MALHAS = {}
ARQ_PROJETO = os.path.join(CACHE, "projeto.json")
ARQ_ANALISE = os.path.join(CACHE, "analise.json")
# malhas dos uniformes (LOD0) exportadas pelo FET do FC 27: só para a prévia 3D (não vêm no pacote leve)
MALHA_ARQ = {"jersey": "jersey_0_0_0_0_1_0_0_mesh.fbx", "shorts": "shorts_0_6_0_mesh.fbx", "socks": "sock_0_0_1_0_0_mesh.fbx"}
REF = referencias.Referencias("Criador de Kits", {n: os.path.join(MOTOR, "referencia", n) for n in MALHA_ARQ.values()},
                              "mostrar o kit em 3D")


# ------------------------------------------------------------------ motor (processo que fica aberto)
class Motor:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self.seq = 0

    def _abrir(self):
        if self.proc and self.proc.poll() is None:
            return
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        self.proc = subprocess.Popen(MOTOR_PY["cmd"] + [os.path.join(MOTOR, "ponte.py"), "servico"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     errors="replace", env=env, creationflags=SEM_JANELA, bufsize=1)
        for linha in self.proc.stdout:
            if linha.strip().startswith("{") and json.loads(linha).get("pronto"):
                return
        raise base.ErroUsuario("O motor do Criador de Kits não abriu.")

    def pedir(self, cmd, args, progresso=None):
        if not MOTOR_PY["ok"]:
            raise base.ErroUsuario(MOTOR_PY["msg"])
        with self.lock:
            self._abrir()
            self.seq += 1
            meu = self.seq
            self.proc.stdin.write(json.dumps({"id": meu, "cmd": cmd, "args": args}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            for linha in self.proc.stdout:
                linha = linha.strip()
                if not linha.startswith("{"):
                    continue
                try:
                    ev = json.loads(linha)
                except ValueError:
                    continue
                if ev.get("id") != meu:
                    continue
                if "progresso" in ev and "ok" not in ev:
                    if progresso:
                        progresso(ev["progresso"], ev.get("msg"))
                    continue
                if not ev.get("ok"):
                    raise base.ErroUsuario(ev.get("erro") or "Erro no motor.")
                return ev
            self.proc = None
            raise base.ErroUsuario("O motor do Criador de Kits fechou no meio do pedido.")

    def fechar(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()


MOT = Motor()


def verificar_python():
    cmd, desc = componentes.python_para(GRUPO, forcar=True)
    if cmd:
        try:
            r = subprocess.run(cmd + ["-c", "import numpy, scipy, PIL, cv2, sys; print(sys.version.split()[0], numpy.__version__, "
                                            "scipy.__version__, PIL.__version__, cv2.__version__)"],
                               capture_output=True, text=True, timeout=120, creationflags=SEM_JANELA)
            v = r.stdout.split()
            if r.returncode == 0 and len(v) == 5:
                MOTOR_PY.update(cmd=cmd + ["-X", "utf8"], ok=True, instalar=False,
                                msg=f"{desc} · numpy {v[1]} · SciPy {v[2]} · Pillow {v[3]} · OpenCV {v[4]}")
                MOT.fechar()
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    MOTOR_PY.update(cmd=None, ok=False, instalar=True, msg=componentes.falta_msg(GRUPO))


def reconferir_motor():
    if MOTOR_PY["ok"] or not MOTOR_PY.get("instalar") or MOTOR_PY.get("reconferindo") or not componentes.estado_grupo(GRUPO)["ok"]:
        return

    def rodar():
        try:
            verificar_python()
        finally:
            MOTOR_PY["reconferindo"] = False
    MOTOR_PY["reconferindo"] = True
    threading.Thread(target=rodar, daemon=True).start()


# ------------------------------------------------------------------ persistência
def _gravar_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def _ler_json(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def carregar_estado():
    ESTADO["projeto"] = _ler_json(ARQ_PROJETO)
    an = _ler_json(ARQ_ANALISE)
    if an and os.path.isfile(an.get("foto") or ""):
        ESTADO["analise"] = an


def salvar_projeto():
    if ESTADO["projeto"] is not None:
        _gravar_json(ARQ_PROJETO, ESTADO["projeto"])


def url_arquivo(caminho):
    if not caminho or not os.path.isfile(caminho):
        return None
    return f"arquivo?c={base64.urlsafe_b64encode(os.path.abspath(caminho).encode('utf-8')).decode()}&t={int(os.path.getmtime(caminho) * 1000)}"


def estado_payload():
    reconferir_motor()
    with LOCK:
        p = ESTADO["projeto"]
        an = ESTADO["analise"]
        job = {k: JOB[k] for k in ("rodando", "progresso", "mensagem", "resumo", "erro", "inicio", "fim")}
    return {"projeto": p, "doador": ESTADO["doador"], "analise": an, "job": job, "opcoes": PREFS.ler(),
            "ambiente": dict(MOTOR_PY, cmd=None), "referencias": REF.estado(),
            "malhas": {k: os.path.isfile(os.path.join(MOTOR, "referencia", n)) for k, n in MALHA_ARQ.items()},
            "biblioteca": {"pasta": BIB["pasta"], "lendo": BIB["lendo"], "total": len(BIB["kits"])}}


# ------------------------------------------------------------------ projeto
def _doador_analisado(pasta):
    r = MOT.pedir("doador", {"pasta": pasta})
    ESTADO["doador"] = r["doador"]
    return r["doador"]


def validar_projeto(p):
    if not isinstance(p, dict) or "pecas" not in p:
        raise base.ErroUsuario("Projeto inválido.")
    if p.get("tipo") not in TIPOS:
        raise base.ErroUsuario("Tipo de uniforme inválido.")
    t = p.setdefault("time", {})
    try:
        t["teamid"] = int(t.get("teamid") or 0)
    except (TypeError, ValueError):
        raise base.ErroUsuario("O teamid tem que ser um número.")
    p["variacao"] = max(0, int(p.get("variacao") or 0))
    for peca in PECAS:
        cfg = p["pecas"].get(peca)
        if not cfg:
            raise base.ErroUsuario(f"Falta a peça {peca} no projeto.")
        pd = cfg.setdefault("padrao", {"tipo": "lisa"})
        if pd.get("tipo") not in PADROES:
            pd["tipo"] = "lisa"
        for c in list(cfg.get("cores", {}).values()) + [c.get("cor") for c in cfg.get("camadas", [])]:
            if c is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(c)):
                raise base.ErroUsuario(f"Cor inválida: {c}")
        for lg in cfg.get("logos", []):
            if lg.get("arquivo") and not _dentro_cache(lg["arquivo"]):
                raise base.ErroUsuario("Logo fora da pasta da ferramenta: importe a imagem pelo botão de logos.")
    return p


def _dentro_cache(c):
    c = os.path.normcase(os.path.abspath(c))
    return c.startswith(os.path.normcase(os.path.abspath(CACHE)) + os.sep)


def api_inicio(_):
    return {"versao": VERSAO, "padroes": PADROES, "tipos": TIPOS, **estado_payload()}


def api_molde(_):
    if "molde" not in MALHAS:
        MALHAS["molde"] = MOT.pedir("molde", {})["molde"]
    return MALHAS["molde"]


def api_estado(_):
    return estado_payload()


def api_projeto(d):
    p = validar_projeto(copy.deepcopy(d["projeto"]))
    with LOCK:
        if ESTADO["projeto"] and p.get("doador") != ESTADO["projeto"].get("doador"):
            raise base.ErroUsuario("Para trocar o doador use Trocar doador.")
        ESTADO["projeto"] = p
        salvar_projeto()
    return {"ok": True}


def api_novo(d):
    pasta = d.get("doador") or (ESTADO["projeto"] or {}).get("doador")
    if not pasta:
        raise base.ErroUsuario("Escolha o kit doador primeiro.")
    doador = _doador_analisado(pasta)
    r = MOT.pedir("projeto_inicial", {"pasta": pasta, "cores": d.get("cores") or {}})
    p = r["projeto"]
    velho = ESTADO["projeto"]
    if velho and d.get("manter_time"):
        p["time"], p["tipo"], p["variacao"] = velho["time"], velho["tipo"], velho.get("variacao", 0)
    with LOCK:
        ESTADO["projeto"] = p
        ESTADO["doador"] = doador
        salvar_projeto()
    return estado_payload()


def api_trocar_doador(d):
    """Outro kit doador: as camadas de cor passam a ser as dele; cores, padrão e logos do projeto continuam."""
    pasta = d["pasta"]
    doador = _doador_analisado(pasta)
    r = MOT.pedir("projeto_inicial", {"pasta": pasta})
    novo = r["projeto"]
    with LOCK:
        p = ESTADO["projeto"]
        if not p:
            ESTADO["projeto"] = novo
        else:
            for peca in PECAS:
                cfg = p["pecas"][peca]
                cores = cfg["cores"]
                cam = novo["pecas"][peca]["camadas"]
                for i, c in enumerate(cam):
                    c["cor"] = cores["base"] if i == 0 else (cores.get("padrao") or cores["base"])
                cfg["camadas"] = cam
            for chave in ("escudo", "marca"):
                if novo.get(chave):
                    if not p.get(chave):
                        p[chave] = novo[chave]
                    elif not p[chave].get("caixa_calcao"):
                        p[chave]["caixa_calcao"] = novo[chave].get("caixa_calcao")
            p["doador"] = novo["doador"]
        ESTADO["doador"] = doador
        salvar_projeto()
    return estado_payload()


def garantir_doador():
    p = ESTADO["projeto"]
    if p and (not ESTADO["doador"] or ESTADO["doador"].get("pasta") != os.path.abspath(p["doador"])):
        _doador_analisado(p["doador"])


def api_previa(d):
    """Textura de cor da peça (sem logos) para o editor. A interface manda o projeto atual (pode não estar salvo)."""
    p = validar_projeto(copy.deepcopy(d.get("projeto") or ESTADO["projeto"]))
    peca = d.get("peca")
    if peca not in PECAS:
        raise base.ErroUsuario("Peça inválida.")
    chave = hashlib.sha1(json.dumps([p["doador"], p.get("mapas"), {k: v for k, v in p["pecas"][peca].items() if k != "logos"}],
                                    sort_keys=True).encode()).hexdigest()[:16]
    destino = os.path.join(CACHE, "previas", f"{peca}_{chave}.png")
    if not os.path.isfile(destino):
        MOT.pedir("previa", {"projeto": p, "peca": peca, "saida": destino, "max": 1024})
        _limpar_previas()
    return {"url": url_arquivo(destino), "chave": chave}


def _limpar_previas(manter=60):
    pasta = os.path.join(CACHE, "previas")
    try:
        arqs = sorted((os.path.join(pasta, n) for n in os.listdir(pasta)), key=os.path.getmtime)
    except OSError:
        return
    for a in arqs[:-manter]:
        try:
            os.remove(a)
        except OSError:
            pass


# ------------------------------------------------------------------ foto
def analisar_foto(caminho):
    pasta = os.path.join(CACHE, "fotos", time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    os.makedirs(pasta, exist_ok=True)
    copia = os.path.join(pasta, "foto" + os.path.splitext(caminho)[1].lower())
    with open(caminho, "rb") as fi, open(copia, "wb") as fo:
        fo.write(fi.read())
    r = MOT.pedir("foto", {"caminho": copia, "pasta": pasta})
    an = r["analise"]
    an["foto"] = copia
    an["nome_foto"] = os.path.basename(caminho)
    an["pasta"] = pasta
    with LOCK:
        ESTADO["analise"] = an
        _gravar_json(ARQ_ANALISE, an)
    return an


def api_foto(d):
    c = os.path.abspath(d["caminho"].strip().strip('"'))
    if not os.path.isfile(c):
        raise base.ErroUsuario(f"Não encontrado: {c}")
    PREFS.atualizar(ultima_pasta=os.path.dirname(c))
    analisar_foto(c)
    return estado_payload()


def _receber_arquivo(a, pasta):
    nome = os.path.basename(a["nome"])
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, nome)
    with open(destino, "wb") as f:
        f.write(base64.b64decode(a["dados"]))
    return destino


def api_receber_foto(d):
    a = d["arquivo"]
    if not a["nome"].lower().endswith(IMG):
        raise base.ErroUsuario("Arraste uma imagem (.png, .jpg, .webp…).")
    c = _receber_arquivo(a, os.path.join(CACHE, "recebidos", time.strftime("%Y%m%d_%H%M%S")))
    analisar_foto(c)
    return estado_payload()


def _caixa_hotspot(base_cx, u, v, altura):
    """Caixa do hotspot com o centro em (u, v), a proporção da caixa do doador e a altura dada."""
    w0 = abs(base_cx["x1"] - base_cx["x0"])
    h0 = abs(base_cx["y1"] - base_cx["y0"]) or 1e-3
    h = altura or h0
    w = w0 * h / h0
    sx = 1 if base_cx["x1"] >= base_cx["x0"] else -1
    sy = 1 if base_cx["y1"] >= base_cx["y0"] else -1
    return {"x0": u - sx * w / 2, "y0": v - sy * h / 2, "x1": u + sx * w / 2, "y1": v + sy * h / 2}


def api_aplicar_foto(d):
    """Passa para o projeto o que a foto deu: cores, padrão e logos (o que estiver marcado em d)."""
    an = ESTADO["analise"]
    if not an:
        raise base.ErroUsuario("Nenhuma foto analisada.")
    usar = {"cores": True, "padrao": True, "logos": True, **(d.get("usar") or {})}
    with LOCK:
        p = ESTADO["projeto"]
        if not p:
            raise base.ErroUsuario("Escolha o kit doador antes de aplicar a foto.")
        cam = p["pecas"]["jersey"]
        if usar["cores"]:
            c = an["cores"]
            cam["cores"].update(base=c["base"], padrao=c["padrao"])
            if c.get("manga"):
                cam["cores"]["manga"] = c["manga"]
            if c.get("gola"):
                cam["cores"]["gola"] = c["gola"]
            for i, camada in enumerate(cam["camadas"]):
                if camada.get("papel") != "base":
                    camada["cor"] = c["padrao"]
                elif i == 0:
                    camada["cor"] = c["base"]
            for peca in ("shorts", "socks"):
                cfg = p["pecas"][peca]
                cfg["cores"]["base"] = c["base"]
                cfg["cores"]["padrao"] = c["padrao"]
                for i, camada in enumerate(cfg["camadas"]):
                    camada["cor"] = c["base"] if i == 0 else c["padrao"]
        if usar["padrao"]:
            cam["padrao"] = {**{"periodo": 0.2, "largura": 0.5, "fase": 0.0, "angulo": 35.0}, **an["padrao"]}
            cam["padrao"].pop("nota", None)
        if usar["logos"]:
            cam["logos"] = [lg for lg in cam["logos"] if not str(lg.get("id", "")).startswith("foto")]
            for lg in an["logos"]:
                if lg.get("ignorar"):
                    continue
                if lg["papel"] in ("escudo", "marca"):
                    chave = lg["papel"]
                    info = p.get(chave) or {}
                    base_cx = info.get("caixa") or {"x0": lg["u"] - lg["largura"] / 2, "y0": lg["v"] - lg["altura"] / 2,
                                                    "x1": lg["u"] + lg["largura"] / 2, "y1": lg["v"] + lg["altura"] / 2}
                    info["caixa"] = _caixa_hotspot(base_cx, lg["u"], lg["v"], lg["altura"] * 1.08)
                    info["arquivo"] = lg["arquivo"]
                    p[chave] = info
                else:
                    cam["logos"].append({"id": lg["id"], "nome": lg["nome"], "arquivo": lg["arquivo"], "u": lg["u"], "v": lg["v"],
                                         "largura": lg["largura"], "altura": lg["altura"], "rot": 0, "visivel": True,
                                         "origem_foto": os.path.splitext(lg["arquivo"])[0], "modo": lg.get("modo", "cor")})
        salvar_projeto()
    return estado_payload()


def api_papel_logo(d):
    """Muda o papel de um logo achado na foto (escudo, marca, patrocinador ou ignorar) antes de aplicar."""
    with LOCK:
        an = ESTADO["analise"]
        for lg in (an or {}).get("logos", []):
            if lg["id"] == d["id"]:
                if d["papel"] == "ignorar":
                    lg["ignorar"] = True
                else:
                    lg["ignorar"] = False
                    if d["papel"] in ("escudo", "marca"):
                        for o in an["logos"]:
                            if o["papel"] == d["papel"]:
                                o["papel"] = "patrocinador"
                    lg["papel"] = d["papel"]
        _gravar_json(ARQ_ANALISE, an)
    return estado_payload()


def api_recorte_logo(d):
    """Refaz o recorte de um logo da foto (cor | bloco | foto). Atualiza o arquivo no projeto."""
    origem = d["origem"]
    if not _dentro_cache(origem + "_foto.png"):
        raise base.ErroUsuario("Logo inválido.")
    destino = f"{origem}_{d['modo']}_{uuid.uuid4().hex[:5]}.png"
    r = MOT.pedir("recorte_logo", {"base": origem, "modo": d["modo"], "destino": destino})
    return {"arquivo": r["caminho"], "url": url_arquivo(r["caminho"]), "tamanho": r["tamanho"]}


# ------------------------------------------------------------------ logos
def importar_logo(caminho, tirar_fundo=True):
    destino = os.path.join(CACHE, "logos", uuid.uuid4().hex[:12] + ".png")
    r = MOT.pedir("importar_logo", {"origem": caminho, "destino": destino, "tirar_fundo": tirar_fundo})
    return {"arquivo": r["caminho"], "url": url_arquivo(r["caminho"]), "tamanho": r["tamanho"], "tirou_fundo": r["tirou_fundo"],
            "nome": os.path.splitext(os.path.basename(caminho))[0]}


def api_importar_logo(d):
    """Imagem escolhida no disco (caminho) ou arrastada (arquivo base64) -> PNG na pasta de logos da ferramenta."""
    if d.get("arquivo"):
        c = _receber_arquivo(d["arquivo"], os.path.join(CACHE, "recebidos", "logos"))
    else:
        c = os.path.abspath(d["caminho"])
        if not os.path.isfile(c):
            raise base.ErroUsuario(f"Não encontrado: {c}")
        PREFS.atualizar(ultima_pasta=os.path.dirname(c))
    return importar_logo(c, d.get("tirar_fundo", True))


def api_url(d):
    return {"urls": {c: url_arquivo(c) for c in d.get("caminhos", [])}}


# ------------------------------------------------------------------ biblioteca de doadores
def ler_biblioteca(pasta):
    kits = []
    vistos = 0
    for dp, dn, fn in os.walk(pasta):
        dn[:] = [x for x in dn if x.lower() not in ("cache", ".git", "__pycache__")]
        vistos += 1
        if vistos > 20000:
            break
        for f in fn:
            m = re.match(r"hotspots_(\d+)_(\d+)_(\d+)\.hotspot$", f)
            if m and os.path.isdir(os.path.join(dp, "jersey")):
                tipo = re.sub(r"_\d+_\d+$", "", os.path.basename(dp))
                time_pasta = os.path.basename(os.path.dirname(dp))
                nome = re.sub(r"_?\d+$", "", time_pasta).replace("_", " ").strip() or f"time {m.group(1)}"
                kits.append({"pasta": dp, "teamid": int(m.group(1)), "tipo": tipo, "time": nome.title(),
                             "rel": os.path.relpath(dp, pasta)})
    kits.sort(key=lambda k: (k["time"].lower(), k["tipo"]))
    return kits


def api_biblioteca(q):
    pasta = PREFS.ler().get("biblioteca")
    if pasta and os.path.isdir(pasta) and (BIB["pasta"] != pasta or q.get("reler")):
        BIB.update(pasta=pasta, kits=ler_biblioteca(pasta))
    return {"pasta": BIB["pasta"], "kits": BIB["kits"]}


def api_definir_biblioteca(d):
    pasta = os.path.abspath(d["pasta"].strip().strip('"'))
    if not os.path.isdir(pasta):
        raise base.ErroUsuario(f"Pasta não encontrada: {pasta}")
    kits = ler_biblioteca(pasta)
    if not kits:
        raise base.ErroUsuario("Nenhum kit nessa pasta (procurei pastas com hotspots_*.hotspot e jersey/). "
                               "Escolha a pasta dos kits exportados pelo FET (ex.: …\\kit).")
    PREFS.atualizar(biblioteca=pasta)
    BIB.update(pasta=pasta, kits=kits)
    return {"pasta": pasta, "kits": kits}


def esp_miniatura(h, q):
    pasta = os.path.abspath(q.get("pasta") or "")
    if not any(os.path.normcase(k["pasta"]) == os.path.normcase(pasta) for k in BIB["kits"]) and \
            os.path.normcase(pasta) != os.path.normcase(os.path.abspath((ESTADO["projeto"] or {}).get("doador") or "")):
        raise base.ErroUsuario("Kit fora da biblioteca.")
    chave = hashlib.sha1(pasta.lower().encode()).hexdigest()[:14]
    destino = os.path.join(CACHE, "miniaturas", chave + ".png")
    if not os.path.isfile(destino):
        MOT.pedir("miniatura", {"pasta": pasta, "saida": destino})
    h.arquivo(destino)


def esp_arquivo(h, q):
    try:
        c = base64.urlsafe_b64decode(q.get("c", "").encode()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise base.ErroUsuario("Caminho inválido.")
    if not _dentro_cache(c) or not os.path.isfile(c):
        raise base.ErroUsuario("Arquivo não encontrado.")
    h.arquivo(c)


# ------------------------------------------------------------------ exportar
def api_exportar(d):
    with LOCK:
        if JOB["rodando"]:
            raise base.ErroUsuario("Já há uma exportação em andamento.")
        p = ESTADO["projeto"]
        if not p:
            raise base.ErroUsuario("Nada para exportar.")
        p = validar_projeto(copy.deepcopy(d.get("projeto") or p))
        if not (1 <= p["time"]["teamid"] <= 199999):
            raise base.ErroUsuario("Informe o teamid do time (1 a 199999), na seção Time.")
        op = PREFS.ler()
        saida = (d.get("saida") or op.get("saida") or "").strip().strip('"')
        if not saida:
            raise base.ErroUsuario("Escolha a pasta de saída.")
        saida = os.path.abspath(saida)
        PREFS.atualizar(saida=saida)
        p["mapas"] = d.get("mapas") or p.get("mapas") or "doador"
        ESTADO["projeto"] = p
        salvar_projeto()
        JOB.update(rodando=True, progresso=0.0, mensagem="Começando", resumo=None, erro=None, inicio=time.time(), fim=0)

    def rodar():
        try:
            r = MOT.pedir("exportar", {"projeto": p, "saida": saida},
                          progresso=lambda f, m: JOB.update(progresso=f, mensagem=m))
            relatorio(p, r, saida)
            JOB.update(resumo={"pasta": r["pasta"], "rel": r["rel"], "arquivos": len(r["arquivos"]), "saida": saida,
                               "segundos": round(time.time() - JOB["inicio"], 1)})
        except Exception as ex:  # noqa: BLE001
            JOB["erro"] = str(ex)
        finally:
            JOB.update(rodando=False, fim=time.time(), mensagem=None)
    threading.Thread(target=rodar, daemon=True).start()
    return estado_payload()


def relatorio(p, r, saida):
    try:
        with open(os.path.join(saida, "relatorio_criador_kits.txt"), "a", encoding="utf-8") as f:
            f.write(f"Criador de Kits {VERSAO} - {time.strftime('%d/%m/%Y %H:%M')}\n")
            f.write(f"Time: {p['time'].get('nome')} (teamid {p['time']['teamid']}) · {p['tipo']} · variação {p.get('variacao', 0)}\n")
            f.write(f"Doador: {p['doador']}\nPasta: {r['rel']}\n")
            f.write(f"Mapas de tecido: {'genéricos' if p.get('mapas') == 'generico' else 'do doador'}\n")
            f.write(f"{len(r['arquivos'])} arquivos. Importe a pasta no FET (content/character/kit/{r['rel']}).\n\n")
    except OSError:
        pass


# ------------------------------------------------------------------ diversos
def api_opcoes(d):
    op = PREFS.ler()
    for k in ("saida", "mapas"):
        if k in d:
            op[k] = d[k]
    if op["mapas"] not in ("doador", "generico"):
        raise base.ErroUsuario("Opção inválida.")
    PREFS.gravar(op)
    return estado_payload()


def api_dialogo(d):
    op = PREFS.ler()
    modo = d.get("modo")
    if modo in ("foto", "logo"):
        r = base.dialogo("abrir", "Escolha a foto da camisa (de frente)" if modo == "foto" else "Escolha a imagem do logo",
                         op.get("ultima_pasta") or base.raiz_trabalho(),
                         tipos=[("Imagens", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tga;*.tif;*.tiff;*.gif"), ("Todos", "*.*")])
        return {"caminhos": [r] if r else []}
    if modo == "biblioteca":
        r = base.dialogo("pasta", "Pasta com os kits exportados pelo FET (a pasta kit)", op.get("biblioteca") or base.raiz_trabalho())
        return {"caminhos": [r] if r else []}
    if modo == "doador":
        r = base.dialogo("pasta", "Pasta de um kit (ex.: …\\home_0_0)", op.get("biblioteca") or base.raiz_trabalho())
        return {"caminhos": [r] if r else []}
    r = base.dialogo("pasta", "Pasta de saída dos kits", op.get("saida") or base.raiz_trabalho())
    return {"caminhos": [r] if r else []}


def api_abrir(d):
    alvo = d.get("caminho") or PREFS.ler().get("saida")
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def api_malha(q):
    peca = q.get("peca")
    if peca not in MALHA_ARQ:
        raise base.ErroUsuario("Peça inválida.")
    caminho = os.path.join(MOTOR, "referencia", MALHA_ARQ[peca])
    if not os.path.isfile(caminho):
        raise base.ErroUsuario(f"Falta a malha {MALHA_ARQ[peca]} (exportada pelo FET) para a prévia 3D.")
    if peca not in MALHAS:
        r = MOT.pedir("malha", {"caminho": caminho})
        MALHAS[peca] = {k: r[k] for k in ("V", "UV", "T")}
    return MALHAS[peca]


ROTAS_GET = {"inicio": api_inicio, "estado": api_estado, "biblioteca": api_biblioteca, "malha": api_malha, "molde": api_molde,
             "versao": lambda _: {"versao": VERSAO}}
ROTAS_POST = {"projeto": api_projeto, "novo": api_novo, "trocar_doador": api_trocar_doador, "previa": api_previa,
              "foto": api_foto, "receber_foto": api_receber_foto, "aplicar_foto": api_aplicar_foto, "papel_logo": api_papel_logo,
              "recorte_logo": api_recorte_logo, "importar_logo": api_importar_logo, "url": api_url,
              "definir_biblioteca": api_definir_biblioteca, "exportar": api_exportar, "opcoes": api_opcoes,
              "dialogo": api_dialogo, "abrir": api_abrir}
for _G, _P in (base.rotas_componentes(GRUPO, ao_concluir=verificar_python), REF.rotas()):
    ROTAS_GET.update(_G)
    ROTAS_POST.update(_P)


def main():
    ap = argparse.ArgumentParser(description="Criador de Kits (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8779)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("foto", nargs="?", help="foto da camisa para já analisar")
    a = ap.parse_args()
    carregar_estado()

    def preparar():
        verificar_python()
        op = PREFS.ler()
        if op.get("biblioteca") and os.path.isdir(op["biblioteca"]):
            BIB["lendo"] = True
            try:
                BIB.update(pasta=op["biblioteca"], kits=ler_biblioteca(op["biblioteca"]))
            finally:
                BIB["lendo"] = False
        if MOTOR_PY["ok"]:
            try:
                garantir_doador()
                if a.foto:
                    analisar_foto(a.foto)
            except base.ErroUsuario as ex:
                print(ex, flush=True)
    threading.Thread(target=preparar, daemon=True).start()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST,
                                 especiais={"/arquivo": esp_arquivo, "/miniatura": esp_miniatura}, nome="CriadorKits/" + VERSAO)
    try:
        base.servir(handler, a.porta, "Criador de Kits", VERSAO, sem_janela=a.sem_janela)
    finally:
        MOT.fechar()


if __name__ == "__main__":
    main()
