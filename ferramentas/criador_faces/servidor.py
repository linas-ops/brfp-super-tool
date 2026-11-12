"""Criador de Faces (BRFP Super Tool): cabeças 3D por fotos com o KeenFace. Servidor local da interface.

    python servidor.py [--porta 8783] [--sem-janela]

As fotos vão para a API do KeenFace (keenface.ai, da KeenTools) com a chave da conta de cada usuário; a cabeça volta
como .glb (e, se pedido, o .zip MetaHuman com head.fbx e texturas) na pasta de saída. A conversão para o FC 27 é feita
à parte no MG Keen Converter (de MGthefacemaker), que a ferramenta só abre: ele não vem junto com o Super Tool.
Só biblioteca padrão. O histórico e a chave ficam no preferencias.json desta pasta (fora do git e do pacote).
"""
import argparse
import base64
import datetime
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, "cache")
RECEBIDAS = os.path.join(CACHE, "recebidas")   # cópias das fotos soltas na janela, só enquanto estão na lista
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))
sys.path.insert(0, AQUI)

import base  # noqa: E402
import keenface as KF  # noqa: E402
import proprio  # noqa: E402

VERSAO = "2.0"
PADRAO_SAIDA = os.path.normpath(os.path.join(base.raiz_trabalho(), "Cabeças KeenFace"))
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "chave": "", "saida": "", "modo": "padrao", "textura": "pbr", "limpeza": True, "lente": "", "imagens": "jpg",
    "metahuman": False, "aceite": False, "mg_exe": "", "ultima_pasta": "", "historico": [],
    "motor": "proprio", "saida_local": "", "fet_dir": "", "jogo_dir": ""})
OPCOES = ("modo", "textura", "limpeza", "lente", "imagens", "metahuman", "aceite", "motor")
LOCK = threading.RLock()
FOTOS = []                       # fotos da cabeça nova, na ordem
SEQ = itertools.count(1)
VALIDADE_PH = 23 * 3600          # a foto enviada vale 24 h no KeenFace enquanto nenhuma cabeça usar
ATIVAS = ("enviando", "conferindo", "confirmar", "criando", "na_fila", "processando", "baixando", "local")
CANCELAVEIS = ("enviando", "conferindo", "confirmar", "local")      # "local" = criador próprio, no computador
PARAR = threading.Event()        # cancelar antes de criar a cabeça
CONTINUAR = threading.Event()    # o usuário confirmou o gasto
TAREFA = {}
SEGUINDO = {}                    # idem -> {fase, progresso, msg, erro}: cabeças do histórico sendo acompanhadas/baixadas
MAX_HISTORICO = 200
STATUS_API = {"queued": "na_fila", "running": "processando", "completed": "pronta", "failed": "falhou", "deleted": "apagada"}
RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
FORMATOS = {"glb": ("glb", ".glb", "GLB"), "metahuman": ("metahuman", "_metahuman.zip", "MetaHuman"),
            "obj": ("obj", "_obj.zip", "OBJ")}


def agora():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def tarefa_nova(**kw):
    return {"fase": "parado", "titulo": "", "msg": "", "progresso": None, "inicio": 0, "fim": 0, "orcamento": None,
            "erro": None, "idem": None, "nome": "", "pasta": "", "resultado": None, **kw}


TAREFA.update(tarefa_nova())


def mudar_tarefa(**kw):
    with LOCK:
        TAREFA.update(kw)


# ------------------------------------------------------------------ preferências e histórico
def atualizar_prefs(**kw):
    with LOCK:
        return PREFS.atualizar(**kw)


def historico():
    return PREFS.ler().get("historico") or []


def item_por(idem):
    return next((x for x in historico() if x.get("idem") == idem), None)


def salvar_item(item):
    """Grava (ou troca) a entrada do histórico pela chave local 'idem'; a mais nova fica em cima. Se o sincronizar já tinha
    trazido a mesma cabeça como "feita em outro lugar" (o pedido daqui ficou sem resposta), fica só a daqui."""
    with LOCK:
        d = PREFS.ler()
        h = d.get("historico") or []
        if item.get("id") and not item.get("de_fora"):
            repetidas = [x.get("idem") for x in h if x.get("id") == item["id"] and x.get("de_fora") and
                         x.get("idem") != item["idem"] and not x.get("arquivos") and not ocupada(x.get("idem"))]
            h = [x for x in h if x.get("idem") not in repetidas]
            for r in repetidas:
                SEGUINDO.pop(r, None)
        for i, x in enumerate(h):
            if x.get("idem") == item["idem"]:
                h[i] = item
                break
        else:
            h.insert(0, item)
        d["historico"] = h[:MAX_HISTORICO]
        PREFS.gravar(d)


def com_head(item, head):
    """Copia da resposta do KeenFace o que importa para o histórico."""
    if not head:
        return item
    item["id"] = head.get("id") or item.get("id")
    item["status"] = STATUS_API.get(head.get("status"), item.get("status"))
    item["progresso"] = head.get("progress")
    item["creditos"] = head.get("credits") or item.get("creditos")
    item["concluido"] = head.get("completed_at") or item.get("concluido")
    item["erro"] = head.get("error") or None
    return item


def publico_item(x):
    arqs = {k: v for k, v in (x.get("arquivos") or {}).items() if v and os.path.exists(v)}
    with LOCK:
        seg = dict(SEGUINDO.get(x.get("idem")) or {})
    erro = x.get("erro")
    if erro and erro.get("code"):
        erro = KF.ErroKeenFace(erro["code"], erro.get("message")).publico()
    return {"idem": x.get("idem"), "id": x.get("id"), "nome": x.get("nome"), "pasta": x.get("pasta"), "criado": x.get("criado"),
            "modo": x.get("modo"), "fotos": x.get("fotos"), "nomes_fotos": x.get("nomes_fotos") or [], "status": x.get("status"),
            "progresso": x.get("progresso"), "creditos": x.get("creditos"), "erro": erro, "arquivos": arqs,
            "pasta_existe": bool(x.get("pasta") and os.path.isdir(x["pasta"])), "seguindo": seg or None,
            "origem": x.get("origem") or "keenface", "jogador": x.get("jogador"), "relatorio": x.get("relatorio")}


# ------------------------------------------------------------------ nomes e pastas
def limpar_nome(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip().rstrip(". ")[:60].strip()
    if s.lower() in RESERVADOS:
        s += "_"
    return s


def sugerir_nome():
    with LOCK:
        if not FOTOS:
            return ""
        n = os.path.splitext(FOTOS[0]["nome"])[0]
    n = re.sub(r"[_\-.]+", " ", n)
    n = re.sub(r"\b(frente|frontal|front|esq|esquerda|esquerdo|dir|direita|direito|left|right|lado|lateral|perfil|profile|"
               r"foto|photo|img|image|imagem|\d+)\b", " ", n, flags=re.I)
    n = limpar_nome(n)
    return n if n and not re.fullmatch(r"[0-9a-f\s]{8,}", n, re.I) else "Cabeça"


def pasta_livre(destino):
    usadas = {os.path.normcase(x.get("pasta") or "") for x in historico()}
    c, n = destino, 2
    while os.path.exists(c) or os.path.normcase(c) in usadas:
        c = f"{destino} ({n})"
        n += 1
    return c


def pasta_saida():
    return PREFS.ler().get("saida") or PADRAO_SAIDA


# ------------------------------------------------------------------ fotos
def assinatura(caminho):
    st = os.stat(caminho)
    return [st.st_size, st.st_mtime_ns]


def ph_valido(f):
    return bool(f.get("ph") and time.time() - f.get("ph_quando", 0) < VALIDADE_PH and
                os.path.isfile(f["caminho"]) and assinatura(f["caminho"]) == f.get("assinatura"))


def publica_foto(f):
    return {"id": f["id"], "nome": f["nome"], "tipo": f["tipo"], "bytes": f["bytes"], "largura": f["largura"],
            "altura": f["altura"], "problema": f["problema"], "enviada": ph_valido(f),
            "previa": f["tipo"] in ("image/jpeg", "image/png", "image/webp", "image/avif")}


def adicionar(caminhos):
    novos, recusadas = 0, []
    with LOCK:
        for c in caminhos:
            c = os.path.abspath(c)
            nome = os.path.basename(c)
            if not os.path.isfile(c):
                continue
            if not c.lower().endswith(KF.EXTENSOES):
                recusadas.append(f"{nome}: o KeenFace aceita JPG, PNG, WebP, HEIC e AVIF")
                continue
            try:
                tam = os.path.getsize(c)
            except OSError:
                continue
            if any(os.path.normcase(f["caminho"]) == os.path.normcase(c) or (f["nome"] == nome and f["bytes"] == tam)
                   for f in FOTOS):
                continue  # a mesma foto de novo (escolhida outra vez ou solta de novo na janela)
            if len(FOTOS) >= KF.MAX_FOTOS:
                recusadas.append(f"{nome}: o KeenFace aceita no máximo {KF.MAX_FOTOS} fotos por cabeça")
                continue
            try:
                info = KF.conferir_foto(c)
                ass = assinatura(c)
            except OSError as ex:
                recusadas.append(f"{nome}: {ex}")
                continue
            FOTOS.append({"id": next(SEQ), "caminho": c, "nome": nome, **info, "ph": None, "ph_quando": 0, "assinatura": ass})
            novos += 1
    return novos, recusadas


def esquecer_fotos_enviadas(chave, phs):
    """Apaga do KeenFace as fotos enviadas que nenhuma cabeça usou (senão ficam lá até 24 h)."""
    phs = [p for p in phs if p]
    if not chave or not phs:
        return

    def rodar():
        cli = KF.Cliente(chave)
        for p in phs:
            try:
                cli.apagar_foto(p)
            except KF.ErroKeenFace:
                pass
    threading.Thread(target=rodar, daemon=True).start()


# ------------------------------------------------------------------ estado para a interface
def estado_payload():
    op = PREFS.ler()
    chave = op.get("chave") or ""
    with LOCK:
        t = dict(TAREFA)
        fotos = [publica_foto(f) for f in FOTOS]
    t["decorrido"] = round((t["fim"] or time.time()) - t["inicio"]) if t["inicio"] else 0
    return {"fotos": fotos, "tarefa": t, "opcoes": {k: op.get(k) for k in OPCOES}, "saida": pasta_saida(),
            "chave": {"definida": bool(chave), "fim": chave[-4:] if len(chave) >= 12 else ""},
            "mg": bool(op.get("mg_exe") and os.path.isfile(op["mg_exe"])), "nome_sugerido": sugerir_nome(),
            "historico": [publico_item(x) for x in op.get("historico") or []],
            "local": proprio.estado(), "saida_local": proprio.pasta_saida()}


def falha(ex):
    return {"falha": ex.publico(), **estado_payload()}


def cliente(parar=None):
    chave = PREFS.ler().get("chave") or ""
    if not chave:
        raise base.ErroUsuario(KF.MENSAGENS["sem_chave"])
    return KF.Cliente(chave, parar)


# ------------------------------------------------------------------ rotas: início, chave e opções
def api_inicio(_):
    return {"versao": VERSAO, "links": KF.LINKS, "saida_padrao": PADRAO_SAIDA, "limite_fotos": KF.MAX_FOTOS,
            "limite_fotos_local": proprio.MAX_FOTOS,
            **estado_payload()}


def api_estado(_):
    return estado_payload()


def api_conta(_):
    if not PREFS.ler().get("chave"):
        return {"conta": None}
    try:
        return {"conta": cliente().conta()}
    except KF.ErroKeenFace as ex:
        return {"conta": None, "falha": ex.publico()}


def api_chave(d):
    chave = (d.get("chave") or "").strip()
    if not chave:
        raise base.ErroUsuario("Cole a chave da API do KeenFace.")
    if re.search(r"\s", chave) or len(chave) < 12:
        raise base.ErroUsuario("Isso não parece uma chave da API do KeenFace (ela começa com ak_ e não tem espaços).")
    try:
        conta = KF.Cliente(chave).conta()
    except KF.ErroKeenFace as ex:
        if ex.codigo in ("unauthorized", "sem_chave"):
            return {"conta": None, "falha": ex.publico()}
        trocar_chave(chave)                 # sem internet agora: guarda e confere depois
        return {"conta": None, "falha": ex.publico(), "guardada": True, **estado_payload()}
    trocar_chave(chave)
    threading.Thread(target=sincronizar, daemon=True).start()
    return {"conta": conta, "guardada": True, **estado_payload()}


def trocar_chave(nova):
    """As fotos já enviadas são da conta da chave antiga: apaga lá (se não viraram cabeça) e envia de novo depois."""
    antiga = PREFS.ler().get("chave") or ""
    if antiga != nova:
        with LOCK:
            if TAREFA["fase"] in ATIVAS:
                raise base.ErroUsuario("Espere a cabeça em andamento terminar antes de trocar a chave.")
            enviadas = [f["ph"] for f in FOTOS if ph_valido(f)]
            for f in FOTOS:
                f["ph"] = None
        esquecer_fotos_enviadas(antiga, enviadas)
    atualizar_prefs(chave=nova)


def api_esquecer_chave(_):
    trocar_chave("")
    return estado_payload()


def api_opcoes(d):
    mud = {}
    if d.get("motor") in ("proprio", "keenface"):
        mud["motor"] = d["motor"]
    if d.get("modo") in ("padrao", "scan"):
        mud["modo"] = d["modo"]
    if d.get("textura") in ("pbr", "raw"):
        mud["textura"] = d["textura"]
    if d.get("imagens") in ("jpg", "png"):
        mud["imagens"] = d["imagens"]
    for k in ("limpeza", "metahuman", "aceite"):
        if k in d:
            mud[k] = bool(d[k])
    if "lente" in d:
        lente = str(d.get("lente") or "").strip().replace(",", ".")
        if lente not in ("", "auto", "auto_common"):
            try:
                v = float(lente)
            except ValueError:
                raise base.ErroUsuario("Lente: deixe vazio (automática) ou um número em mm (equivalente 35 mm).") from None
            if not 1 <= v <= 2000:
                raise base.ErroUsuario("Lente: o KeenFace aceita de 1 a 2000 mm (equivalente 35 mm).")
            lente = f"{v:g}"
        mud["lente"] = lente
    if mud:
        atualizar_prefs(**mud)
    return estado_payload()


def api_escolher_saida(_):
    c = base.dialogo("pasta", "Pasta onde guardar as cabeças do KeenFace", pasta_saida())
    if c:
        atualizar_prefs(saida=c)
    return estado_payload()


def api_saida_padrao(_):
    atualizar_prefs(saida="")
    return estado_payload()


# ------------------------------------------------------------------ rotas: fotos
def api_escolher_fotos(_):
    op = PREFS.ler()
    r = base.dialogo("abrir", "Fotos do jogador (de 1 a 15; de frente e dos lados)", op.get("ultima_pasta") or None,
                     tipos=[("Fotos", "*.jpg;*.jpeg;*.jfif;*.png;*.webp;*.heic;*.heif;*.avif"), ("Todos", "*.*")], multiplo=True)
    if not r:
        return {"novos": 0, "recusadas": [], **estado_payload()}
    r = r if isinstance(r, list) else [r]
    atualizar_prefs(ultima_pasta=os.path.dirname(r[0]))
    novos, recusadas = adicionar(r)
    return {"novos": novos, "recusadas": recusadas, **estado_payload()}


def _apagar_fora_da_lista(pasta):
    with LOCK:
        em_uso = {os.path.normcase(f["caminho"]) for f in FOTOS}
    try:
        for arq in os.listdir(pasta):
            c = os.path.join(pasta, arq)
            if os.path.normcase(c) not in em_uso:
                os.remove(c)
        if not os.listdir(pasta):
            os.rmdir(pasta)
    except OSError:
        pass


def limpar_recebidas(tudo=False):
    """Apaga as cópias das fotos soltas na janela que saíram da lista: fotos de pessoas não ficam guardadas à toa."""
    if tudo:
        shutil.rmtree(RECEBIDAS, ignore_errors=True)
        return
    try:
        pastas = os.listdir(RECEBIDAS)
    except OSError:
        return
    for nome in pastas:
        p = os.path.join(RECEBIDAS, nome)
        try:
            if time.time() - os.path.getmtime(p) < 60:
                continue  # pode ser uma soltura ainda em andamento
        except OSError:
            continue
        _apagar_fora_da_lista(p)


def api_receber(d):
    pasta = os.path.join(RECEBIDAS, time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    caminhos = []
    for a in d.get("arquivos") or []:
        nome = os.path.basename(str(a.get("nome") or "")) or "foto"
        if not nome.lower().endswith(KF.EXTENSOES):
            continue
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, nome)
        with open(destino, "wb") as f:
            f.write(base64.b64decode(a.get("dados") or ""))
        caminhos.append(destino)
    if not caminhos:
        raise base.ErroUsuario("Solte fotos JPG, PNG, WebP, HEIC ou AVIF.")
    novos, recusadas = adicionar(caminhos)
    _apagar_fora_da_lista(pasta)  # as repetidas e as recusadas não ficam guardadas
    return {"novos": novos, "recusadas": recusadas, **estado_payload()}


def _tirar_fotos(manter):
    with LOCK:
        if TAREFA["fase"] in ("enviando", "conferindo", "confirmar", "criando", "local"):
            raise base.ErroUsuario("Espere terminar (ou cancele) antes de mexer nas fotos.")
        saem = [f for f in FOTOS if not manter(f)]
        FOTOS[:] = [f for f in FOTOS if manter(f)]
    esquecer_fotos_enviadas(PREFS.ler().get("chave"), [f["ph"] for f in saem if ph_valido(f)])
    for f in saem:  # a cópia de uma foto solta na janela sai junto (a foto original, escolhida numa pasta, fica)
        if os.path.normcase(f["caminho"]).startswith(os.path.normcase(RECEBIDAS) + os.sep):
            try:
                os.remove(f["caminho"])
                os.rmdir(os.path.dirname(f["caminho"]))  # só sai se ficou vazia
            except OSError:
                pass
    limpar_recebidas()


def api_remover_foto(d):
    alvo = int(d.get("id") or 0)
    _tirar_fotos(lambda f: f["id"] != alvo)
    return estado_payload()


def api_limpar_fotos(_):
    _tirar_fotos(lambda f: False)
    return estado_payload()


def api_mover_foto(d):
    alvo, passo = int(d.get("id") or 0), int(d.get("passo") or 0)
    with LOCK:
        i = next((k for k, f in enumerate(FOTOS) if f["id"] == alvo), None)
        if i is not None and passo:
            j = max(0, min(len(FOTOS) - 1, i + passo))
            FOTOS.insert(j, FOTOS.pop(i))
    return estado_payload()


def especial_foto(h, q):
    with LOCK:
        f = next((x for x in FOTOS if str(x["id"]) == q.get("id")), None)
    if not f or not os.path.isfile(f["caminho"]):
        h.enviar(404, b"nao encontrado", "text/plain")
        return
    with open(f["caminho"], "rb") as arq:
        dados = arq.read()
    h.enviar(200, dados, f["tipo"] or "application/octet-stream")


def especial_modelo(h, q):
    x = item_por(q.get("idem"))
    glb = ((x or {}).get("arquivos") or {}).get("glb")
    if not glb or not os.path.isfile(glb):
        h.enviar(404, b"nao encontrado", "text/plain")
        return
    with open(glb, "rb") as arq:
        dados = arq.read()
    h.enviar(200, dados, "model/gltf-binary")


# ------------------------------------------------------------------ criar uma cabeça
def api_criar(d):
    op = PREFS.ler()
    with LOCK:
        fotos = list(FOTOS)
    if not op.get("chave"):
        raise base.ErroUsuario(KF.MENSAGENS["sem_chave"])
    if not fotos:
        raise base.ErroUsuario("Adicione as fotos do jogador (de 1 a 15).")
    if op.get("modo") == "scan" and len(fotos) < 2:
        raise base.ErroUsuario(KF.MENSAGENS["too_few_photos"])
    ruim = next((f for f in fotos if f["problema"]), None)
    if ruim:
        raise base.ErroUsuario(f"{ruim['nome']}: {ruim['problema']}. Tire esta foto da lista ou troque por outra.")
    sumiu = next((f for f in fotos if not os.path.isfile(f["caminho"])), None)
    if sumiu:
        raise base.ErroUsuario(f"A foto {sumiu['nome']} não existe mais no disco. Tire da lista e adicione de novo.")
    if not op.get("aceite"):
        raise base.ErroUsuario("Marque a confirmação de que você pode usar estas fotos e enviá-las ao KeenFace.")
    nome = limpar_nome(d.get("nome")) or sugerir_nome()
    saida = pasta_saida()
    try:
        os.makedirs(saida, exist_ok=True)
    except OSError as ex:
        raise base.ErroUsuario(f"Não deu para usar a pasta de saída {saida}: {ex}") from None
    pasta = pasta_livre(os.path.join(saida, nome))
    opcoes = {k: op.get(k) for k in ("modo", "textura", "limpeza", "lente")}
    with LOCK:
        if TAREFA["fase"] in ATIVAS:
            raise base.ErroUsuario("Já tem uma cabeça em andamento: espere ela terminar.")
        PARAR.clear()
        CONTINUAR.clear()
        TAREFA.clear()
        TAREFA.update(tarefa_nova(fase="enviando", titulo="Enviando as fotos ao KeenFace", progresso=0, nome=nome, pasta=pasta,
                                  inicio=time.time()))
    threading.Thread(target=trabalho_criar, args=(op["chave"], fotos, opcoes, nome, pasta, op.get("imagens") or "jpg",
                                                  bool(op.get("metahuman"))), daemon=True).start()
    return estado_payload()


def api_confirmar(_):
    with LOCK:
        if TAREFA["fase"] != "confirmar":
            raise base.ErroUsuario("Não há nada esperando confirmação.")
    CONTINUAR.set()
    return estado_payload()


def api_cancelar(_):
    with LOCK:
        fase = TAREFA["fase"]
    if fase == "local":
        proprio.cancelar()
    elif fase in CANCELAVEIS:
        PARAR.set()
    elif fase in ATIVAS:
        raise base.ErroUsuario("A cabeça já foi criada no KeenFace e não dá para cancelar: espere terminar.")
    return estado_payload()


def api_fechar_tarefa(_):
    """Tira da tela o resultado (ou erro) da última cabeça."""
    with LOCK:
        if TAREFA["fase"] not in ATIVAS:
            TAREFA.clear()
            TAREFA.update(tarefa_nova())
    return estado_payload()


def enviar_fotos(cli, fotos, forcar=False):
    pendentes = [f for f in fotos if forcar or not ph_valido(f)]
    total = sum(f["bytes"] for f in pendentes) or 1
    feito = 0
    for i, f in enumerate(pendentes):
        msg = f"Foto {i + 1} de {len(pendentes)}: {f['nome']}"
        mudar_tarefa(fase="enviando", titulo="Enviando as fotos ao KeenFace", msg=msg, progresso=feito / total)

        def progresso(n, _tam, antes=feito, msg=msg):
            mudar_tarefa(progresso=min(1.0, (antes + n) / total), msg=msg)
        try:
            f["ph"] = cli.enviar_foto(f["caminho"], progresso)
        except KF.ErroKeenFace as ex:
            if ex.codigo in ("photo_too_large", "unsupported_media_type"):
                raise KF.ErroKeenFace(ex.codigo, ex.original, status=ex.status, request_id=ex.request_id,
                                      mensagem=f"{f['nome']}: {ex}") from None
            raise
        f["ph_quando"] = time.time()
        f["assinatura"] = assinatura(f["caminho"])
        feito += f["bytes"]
    return [f["ph"] for f in fotos]


def trabalho_criar(chave, fotos, opcoes, nome, pasta, imagens, metahuman):
    cli = KF.Cliente(chave, PARAR)
    criado = False
    try:
        ids = enviar_fotos(cli, fotos)
        mudar_tarefa(fase="conferindo", titulo="Conferindo com o KeenFace", msg="Custo e saldo da conta", progresso=None)
        try:
            orc = cli.orcamento(ids, opcoes)
        except KF.ErroKeenFace as ex:
            if ex.codigo not in ("photo_expired", "invalid_request") or (ex.codigo == "invalid_request" and ex.campo != "photos"):
                raise
            ids = enviar_fotos(cli, fotos, forcar=True)        # alguma foto expirou ou já foi usada: manda de novo
            mudar_tarefa(fase="conferindo", titulo="Conferindo com o KeenFace", msg="Custo e saldo da conta", progresso=None)
            orc = cli.orcamento(ids, opcoes)
        cred = (orc or {}).get("credits") or {}
        if cred.get("sufficient") is False:
            raise KF.ErroKeenFace("insufficient_credits", mensagem=(
                f"Créditos insuficientes no KeenFace: o saldo é {cred.get('balance')} e a cabeça custa {cred.get('cost')}. "
                "Compre créditos no site e crie de novo: as fotos enviadas ficam guardadas lá por 24 h."))
        mudar_tarefa(fase="confirmar", titulo="Confirme para criar a cabeça", msg="", progresso=None,
                     orcamento={"custo": cred.get("cost"), "saldo": cred.get("balance"), "fotos": orc.get("photo_count"),
                                "modo": opcoes.get("modo")})
        t0 = time.time()
        while not CONTINUAR.wait(0.4):
            if PARAR.is_set():
                raise KF.Cancelado()
            if time.time() - t0 > 3600:
                raise KF.Cancelado()
        idem = uuid.uuid4().hex
        item = {"idem": idem, "id": None, "nome": nome, "pasta": pasta, "criado": agora(), "modo": opcoes.get("modo"),
                "opcoes": opcoes, "fotos": len(ids), "nomes_fotos": [f["nome"] for f in fotos], "ph": ids,
                "status": "enviando", "imagens": imagens, "metahuman": metahuman, "arquivos": {}}
        salvar_item(item)          # antes de pedir: se a ferramenta fechar no meio, dá para recuperar a mesma cabeça
        mudar_tarefa(fase="criando", titulo="Criando a cabeça no KeenFace", msg="", idem=idem, inicio=time.time())
        cli.parar = None           # daqui em diante não se cancela mais
        head = cli.criar(ids, opcoes, idem)
        criado = True
        with LOCK:
            for f in fotos:
                f["ph"] = None     # a cabeça ficou com as fotos
        item["ph"] = None
        com_head(item, head)
        salvar_item(item)

        def ao_estado(fase, progresso=None, msg=""):
            titulos = {"na_fila": "Na fila do KeenFace", "processando": "O KeenFace está montando a cabeça",
                       "baixando": "Baixando a cabeça"}
            mudar_tarefa(fase=fase, titulo=titulos.get(fase, ""), progresso=progresso, msg=msg)
        seguir(cli, item, ao_estado)
        mudar_tarefa(fase="pronto", titulo="Cabeça pronta", msg="", progresso=1, fim=time.time(),
                     resultado={"idem": item["idem"], "pasta": item["pasta"], "arquivos": item.get("arquivos") or {}})
    except KF.Cancelado:
        mudar_tarefa(fase="cancelado", titulo="Cancelado", msg="Nada foi criado nem cobrado.", progresso=None, fim=time.time())
        if not criado:
            esquecer_fotos_enviadas(chave, [f.get("ph") for f in fotos])
            with LOCK:
                for f in fotos:
                    f["ph"] = None
    except KF.ErroKeenFace as ex:
        erro = ex.publico()
        if criado:
            erro["mensagem"] += (" A cabeça continua na sua conta do KeenFace: em Minhas cabeças, use Atualizar para "
                                 "continuar de onde parou.") if ex.codigo in ("rede", "service_unavailable", "internal_error") else ""
        mudar_tarefa(fase="erro", titulo="Não deu certo", erro=erro, progresso=None, fim=time.time())
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        mudar_tarefa(fase="erro", titulo="Não deu certo", progresso=None, fim=time.time(),
                     erro={"codigo": "interno", "mensagem": f"Erro inesperado: {type(ex).__name__}: {ex}"})


# ------------------------------------------------------------------ acompanhar e baixar
def seguir(cli, item, ao_estado):
    """Espera a cabeça terminar no KeenFace e baixa o .glb (e o MetaHuman, se pedido). Erros sobem como ErroKeenFace."""
    while True:
        head = cli.cabeca(item["id"], espera=10)
        com_head(item, head)
        salvar_item(item)
        st = (head or {}).get("status")
        if st == "queued":
            ao_estado("na_fila", 0, "Esperando a vez")
        elif st == "running":
            p = head.get("progress") or 0
            ao_estado("processando", p / 100, f"{p}%")
        elif st == "completed":
            break
        elif st == "failed":
            e = head.get("error") or {}
            raise KF.ErroKeenFace(e.get("code") or "reconstruction_failed", e.get("message"))
        else:
            raise KF.ErroKeenFace("not_found", mensagem="Esta cabeça foi apagada no KeenFace.")
    formatos = ["glb"] + (["metahuman"] if item.get("metahuman") else [])
    for fmt in formatos:
        if (item.get("arquivos") or {}).get(fmt) and os.path.exists(item["arquivos"][fmt]):
            continue
        baixar_formato(cli, item, fmt, ao_estado)


def baixar_formato(cli, item, fmt, ao_estado):
    formato, sufixo, rotulo = FORMATOS[fmt]
    pasta = item["pasta"]
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, item["nome"] + sufixo)
    ao_estado("baixando", None, f"Preparando o arquivo {rotulo} no KeenFace (a primeira vez leva uns 30 s)")

    def baixando(n, total):
        ao_estado("baixando", n / total if total else None,
                  f"{rotulo}: {n / 1e6:.1f} MB" + (f" de {total / 1e6:.1f} MB" if total else ""))
    cli.baixar_modelo(item["id"], destino, formato, item.get("imagens") or "jpg",
                      ao_esperar=lambda s: ao_estado("baixando", None, f"Preparando o arquivo {rotulo} no KeenFace…"),
                      ao_baixar=baixando)
    final = destino
    if destino.endswith(".zip"):
        final = os.path.join(pasta, "metahuman" if fmt == "metahuman" else "obj")
        extrair(destino, final)
        os.remove(destino)
    item.setdefault("arquivos", {})[fmt] = final
    salvar_item(item)
    gravar_ficha(item)
    return final


def extrair(zip_, destino):
    raiz = os.path.abspath(destino)
    with zipfile.ZipFile(zip_) as z:
        for m in z.infolist():
            alvo = os.path.abspath(os.path.join(raiz, m.filename))
            if not alvo.startswith(raiz + os.sep):
                continue                       # nome de arquivo que sairia da pasta: ignora
            if m.is_dir():
                os.makedirs(alvo, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with z.open(m) as src, open(alvo, "wb") as dst:
                while True:
                    bloco = src.read(1 << 20)
                    if not bloco:
                        break
                    dst.write(bloco)


def gravar_ficha(item):
    """keenface.json na pasta da cabeça: de onde ela veio (id no KeenFace, fotos, modo, arquivos)."""
    ficha = {k: item.get(k) for k in ("id", "nome", "criado", "concluido", "modo", "opcoes", "nomes_fotos", "creditos")}
    ficha["arquivos"] = {k: os.path.basename(v) for k, v in (item.get("arquivos") or {}).items()}
    ficha["origem"] = "KeenFace (keenface.ai) pelo Criador de Faces do BRFP Super Tool " + VERSAO
    try:
        with open(os.path.join(item["pasta"], "keenface.json"), "w", encoding="utf-8") as f:
            json.dump(ficha, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def ocupada(idem):
    with LOCK:
        return (idem in SEGUINDO and SEGUINDO[idem].get("fase") not in ("pronto", "erro")) or \
            (TAREFA.get("idem") == idem and TAREFA["fase"] in ATIVAS)


def seguir_em_segundo_plano(idem, formato=None):
    """Acompanha/baixa uma cabeça do histórico sem ocupar a tarefa principal (SEGUINDO mostra o progresso)."""
    cli = cliente()
    with LOCK:
        if ocupada(idem):
            raise base.ErroUsuario("Esta cabeça já está sendo acompanhada ou baixada.")
        SEGUINDO[idem] = {"fase": "conferindo", "progresso": None, "msg": "Conferindo no KeenFace", "erro": None}

    def ao_estado(fase, progresso=None, msg=""):
        with LOCK:
            SEGUINDO[idem] = {"fase": fase, "progresso": progresso, "msg": msg, "erro": None}

    def rodar():
        item = item_por(idem)
        try:
            if not item:
                raise KF.ErroKeenFace("not_found", mensagem="Esta cabeça não está mais na lista.")
            if not item.get("id"):
                recuperar(cli, item)
            if formato:
                head = cli.cabeca(item["id"])
                com_head(item, head)
                salvar_item(item)
                if head.get("status") != "completed":
                    seguir(cli, item, ao_estado)
                if not ((item.get("arquivos") or {}).get(formato) and os.path.exists(item["arquivos"][formato])):
                    baixar_formato(cli, item, formato, ao_estado)
            else:
                seguir(cli, item, ao_estado)
            with LOCK:
                SEGUINDO[idem] = {"fase": "pronto", "progresso": 1, "msg": "", "erro": None}
        except KF.ErroKeenFace as ex:
            with LOCK:
                SEGUINDO[idem] = {"fase": "erro", "progresso": None, "msg": "", "erro": ex.publico()}
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            with LOCK:
                SEGUINDO[idem] = {"fase": "erro", "progresso": None, "msg": "",
                                  "erro": {"codigo": "interno", "mensagem": f"{type(ex).__name__}: {ex}"}}
    threading.Thread(target=rodar, daemon=True).start()


def recuperar(cli, item):
    """A ferramenta fechou entre pedir a cabeça e receber a resposta: o mesmo pedido com a mesma Idempotency-Key devolve
    a mesma cabeça (vale 24 h) sem cobrar de novo. Se o KeenFace recusa o pedido (fotos expiradas), a cabeça não foi criada."""
    original = ""
    if item.get("ph"):
        try:
            head = cli.criar(item["ph"], item.get("opcoes") or {}, item["idem"])
        except KF.ErroKeenFace as ex:
            if ex.codigo not in ("photo_expired", "invalid_request", "not_found"):
                raise
            original = ex.original
        else:
            item["ph"] = None
            com_head(item, head)
            salvar_item(item)
            return
    item["status"] = "nao_criada"
    item["ph"] = None
    salvar_item(item)
    raise KF.ErroKeenFace("not_found", original, mensagem=(
        "O pedido desta cabeça não chegou ao KeenFace antes de a ferramenta fechar, e as fotos enviadas já expiraram, "
        "então nada foi cobrado. Crie de novo."))


def api_atualizar_item(d):
    """Confere a cabeça no KeenFace e continua de onde parou (espera terminar e baixa o .glb)."""
    seguir_em_segundo_plano(d.get("idem"))
    return estado_payload()


def api_baixar(d):
    fmt = d.get("formato") or "glb"
    if fmt not in FORMATOS:
        raise base.ErroUsuario("Formato desconhecido.")
    seguir_em_segundo_plano(d.get("idem"), fmt)
    return estado_payload()


def api_apagar_no_keenface(d):
    item = item_por(d.get("idem"))
    if not item or not item.get("id"):
        raise base.ErroUsuario("Esta cabeça não está no KeenFace.")
    try:
        cliente().apagar(item["id"])
    except KF.ErroKeenFace as ex:
        if ex.codigo != "not_found":
            return falha(ex)
    item["status"] = "apagada"
    salvar_item(item)
    return estado_payload()


def api_esquecer(d):
    """Tira a cabeça da lista (não apaga arquivos nem nada no KeenFace)."""
    with LOCK:
        if ocupada(d.get("idem")):
            raise base.ErroUsuario("Espere esta cabeça terminar de ser acompanhada ou baixada.")
        dd = PREFS.ler()
        dd["historico"] = [x for x in dd.get("historico") or [] if x.get("idem") != d.get("idem")]
        PREFS.gravar(dd)
        SEGUINDO.pop(d.get("idem"), None)
    return estado_payload()


def api_renomear(d):
    item = item_por(d.get("idem"))
    nome = limpar_nome(d.get("nome"))
    if not item or not nome:
        raise base.ErroUsuario("Nome inválido.")
    if item.get("arquivos"):
        raise base.ErroUsuario("Os arquivos desta cabeça já foram baixados com o nome atual.")
    item["nome"] = nome
    item["pasta"] = pasta_livre(os.path.join(os.path.dirname(item["pasta"]) or pasta_saida(), nome))
    salvar_item(item)
    return estado_payload()


def hora_local(iso):
    """Data do KeenFace (UTC, como '2026-11-10T16:33:17Z') no fuso deste computador, no formato do histórico."""
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso or "").replace("T", " ").replace("Z", "")[:19]
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def sincronizar():
    """Junta ao histórico as cabeças da conta feitas pela API em outro lugar e atualiza o status das que estão aqui."""
    chave = PREFS.ler().get("chave")
    if not chave:
        return 0
    try:
        heads = KF.Cliente(chave).listar(100)
    except KF.ErroKeenFace:
        return 0
    novas = 0
    with LOCK:
        d = PREFS.ler()
        h = d.get("historico") or []
        por_id = {x.get("id"): x for x in h if x.get("id")}
        for head in heads:
            x = por_id.get(head.get("id"))
            if x is None:
                if head.get("status") == "deleted":
                    continue
                criado = hora_local(head.get("created_at"))
                nome = limpar_nome("KeenFace " + criado.replace(":", "-")) or "KeenFace"
                x = {"idem": "api_" + str(head.get("id")), "id": head.get("id"), "nome": nome, "criado": criado,
                     "pasta": os.path.join(pasta_saida(), nome), "modo": "scan" if head.get("scan_reconstruction") else "padrao",
                     "fotos": head.get("photo_count"), "imagens": "jpg", "arquivos": {}, "de_fora": True}
                h.append(x)
                novas += 1
            com_head(x, head)
        h.sort(key=lambda x: x.get("criado") or "", reverse=True)
        d["historico"] = h[:MAX_HISTORICO]
        PREFS.gravar(d)
    return novas


def api_sincronizar(_):
    if not PREFS.ler().get("chave"):
        raise base.ErroUsuario(KF.MENSAGENS["sem_chave"])
    try:
        cliente().listar(1)
    except KF.ErroKeenFace as ex:
        return falha(ex)
    return {"novas": sincronizar(), **estado_payload()}


def retomar_pendentes():
    """Ao abrir: continua as cabeças que ficaram na fila/processando ou sem resposta quando a ferramenta fechou."""
    if not PREFS.ler().get("chave"):
        return
    # os pedidos que ficaram sem resposta vêm antes do sincronizar, senão ele traria a mesma cabeça como "feita em outro
    # lugar"; se der erro de rede aqui, o seguir_em_segundo_plano abaixo tenta de novo e mostra o erro
    for x in historico():
        if x.get("status") == "enviando" and not x.get("id") and x.get("ph"):
            try:
                recuperar(cliente(), x)
            except KF.ErroKeenFace as ex:
                if x.get("status") == "nao_criada":
                    with LOCK:
                        SEGUINDO[x["idem"]] = {"fase": "erro", "progresso": None, "msg": "", "erro": ex.publico()}
    sincronizar()
    for x in historico():
        st = x.get("status")
        recente = x.get("criado", "") >= time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 7 * 86400))
        if st in ("na_fila", "processando") or (st == "enviando" and x.get("ph")) or \
                (st == "pronta" and recente and not x.get("de_fora") and not (x.get("arquivos") or {}).get("glb")):
            try:
                seguir_em_segundo_plano(x["idem"])
            except base.ErroUsuario:
                pass


# ------------------------------------------------------------------ pastas, links e MG Keen Converter
def api_abrir(d):
    if d.get("idem"):
        x = item_por(d["idem"])
        alvo = (x or {}).get("pasta")
        arq = ((x or {}).get("arquivos") or {}).get(d.get("formato") or "")
        if arq and os.path.exists(arq):
            if d.get("executar"):               # abre no programa padrão (as imagens de conferência)
                os.startfile(arq)  # noqa: S606
            else:
                base.abrir_no_explorer(arq, selecionar=True)
            return {}
    else:
        alvo = pasta_saida()
        os.makedirs(alvo, exist_ok=True)
    if not alvo or not os.path.isdir(alvo):
        raise base.ErroUsuario("A pasta desta cabeça ainda não existe (os arquivos não foram baixados).")
    base.abrir_no_explorer(alvo)
    return {}


def api_abrir_link(d):
    url = KF.LINKS.get(d.get("qual") or "") or KF.link_seguro(d.get("url") or "")
    if not url:
        raise base.ErroUsuario("Link desconhecido.")
    webbrowser.open(url)
    return {}


def achar_mg():
    """MG Keen Converter.exe: o escolhido antes; senão procura na pasta de trabalho, Downloads, Documentos e Área de Trabalho."""
    exe = PREFS.ler().get("mg_exe") or ""
    if exe and os.path.isfile(exe):
        return exe
    casa = os.path.expanduser("~")
    raizes = [base.raiz_trabalho(), os.path.dirname(base.raiz_trabalho())] + [
        os.path.join(casa, *p) for p in (("Downloads",), ("Documents",), ("Desktop",), ("OneDrive", "Desktop"),
                                         ("OneDrive", "Documentos"), ("OneDrive", "Documents"), ("OneDrive", "Área de Trabalho"))]
    vistas = 0
    for raiz in raizes:
        fila = [(raiz, 0)]
        while fila and vistas < 4000:
            pasta, nivel = fila.pop(0)
            vistas += 1
            try:
                with os.scandir(pasta) as it:
                    for e in it:
                        if e.is_file() and e.name.lower() == "mg keen converter.exe":
                            return e.path
                        if nivel < 3 and e.is_dir(follow_symlinks=False) and not e.name.startswith((".", "$")):
                            fila.append((e.path, nivel + 1))
            except OSError:
                continue
    return None


def api_mg(d):
    """Abre o MG Keen Converter do usuário (ele não vem com o Super Tool). {escolher: true} se não achar."""
    exe = achar_mg()
    if not exe:
        return {"escolher": True}
    atualizar_prefs(mg_exe=exe)
    subprocess.Popen([exe], cwd=os.path.dirname(exe))  # noqa: S603
    x = item_por(d.get("idem")) if d.get("idem") else None
    glb = ((x or {}).get("arquivos") or {}).get("glb")
    return {"aberto": True, "glb": glb if glb and os.path.isfile(glb) else None}


def api_mg_escolher(_):
    c = base.dialogo("abrir", "Onde está o MG Keen Converter.exe?", PREFS.ler().get("mg_exe") or None,
                     tipos=[("MG Keen Converter", "MG Keen Converter.exe;*.exe")])
    if not c:
        return {"escolhido": False}
    if not c.lower().endswith(".exe"):
        raise base.ErroUsuario("Escolha o arquivo MG Keen Converter.exe.")
    atualizar_prefs(mg_exe=c)
    return {"escolhido": True, **estado_payload()}


ROTAS_GET = {"inicio": api_inicio, "estado": api_estado, "conta": api_conta, "versao": lambda _: {"versao": VERSAO}}
ROTAS_POST = {"chave": api_chave, "esquecer_chave": api_esquecer_chave, "opcoes": api_opcoes,
              "escolher_saida": api_escolher_saida, "saida_padrao": api_saida_padrao,
              "escolher_fotos": api_escolher_fotos, "receber": api_receber, "remover_foto": api_remover_foto,
              "limpar_fotos": api_limpar_fotos, "mover_foto": api_mover_foto,
              "criar": api_criar, "confirmar": api_confirmar, "cancelar": api_cancelar, "fechar_tarefa": api_fechar_tarefa,
              "atualizar_item": api_atualizar_item, "baixar": api_baixar, "apagar_no_keenface": api_apagar_no_keenface,
              "esquecer": api_esquecer, "renomear": api_renomear, "sincronizar": api_sincronizar,
              "abrir": api_abrir, "abrir_link": api_abrir_link, "mg": api_mg, "mg_escolher": api_mg_escolher}
ESPECIAIS = {"/foto": especial_foto, "/modelo": especial_modelo}
proprio.ligar(sys.modules[__name__])
for _G, _P in (proprio.rotas(),):
    ROTAS_GET.update(_G)
    ROTAS_POST.update(_P)


def main():
    ap = argparse.ArgumentParser(description="Criador de Faces (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8783)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    ap.add_argument("fotos", nargs="*", help="fotos para já entrar na lista")
    a = ap.parse_args()
    limpar_recebidas(tudo=True)  # a lista de fotos começa vazia: as cópias da última vez não servem mais
    if a.fotos:
        adicionar(a.fotos)
    threading.Thread(target=retomar_pendentes, daemon=True).start()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, ESPECIAIS, nome="CriadorFaces/" + VERSAO)
    base.servir(handler, a.porta, "Criador de Faces", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
