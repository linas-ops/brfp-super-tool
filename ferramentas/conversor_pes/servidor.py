"""Conversor de Estádios PES 2021 -> FC 26 (BRFP Super Tool) — interface completa do conversor (sem comandos).

    python servidor.py [--porta 8772] [--sem-janela]

O motor continua sendo <pasta de trabalho>/conversor/converter.py (etapas em Python, Blender e texconv); esta
ferramenta cria e edita as configurações num formulário (acha os estádios do mod do PES e os mundos do export do FET),
roda as etapas, mostra o registro ao vivo, o PASSOS_FET.md como lista de conferência, as prévias, e tem as ferramentas
(modelo vazio, avaliar estádio base, marcar entrega).
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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import componentes  # noqa: E402

VERSAO = "2.0"
RAIZ = base.raiz_trabalho()
CONVERSOR = base.pasta_conversor()
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"))
LOCK = threading.Lock()
EXEC = {"rodando": False, "proc": None, "config": None, "args": [], "log": [], "etapa": None, "etapas": {}, "inicio": 0,
        "fim": 0, "codigo": None, "seq": 0}
MAX_LOG = 6000
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ler_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def etapas():
    """(nome, tipo, descrição) na ordem do converter.py."""
    try:
        with open(os.path.join(CONVERSOR, "converter.py"), encoding="utf-8") as f:
            t = f.read()
    except OSError:
        return []
    desc = {}
    doc = t.split('"""')[1] if '"""' in t else ""
    for linha in doc.splitlines():
        m = re.match(r"^  ([a-z_]+)\s{2,}(.+)$", linha)
        if m:
            desc[m.group(1)] = m.group(2).strip()
    out = []
    for m in re.finditer(r'\("([a-z_]+)",\s*(PY|BL),\s*"([^"]+)"\)', t):
        out.append({"nome": m.group(1), "tipo": "Blender" if m.group(2) == "BL" else "Python", "script": m.group(3),
                    "descricao": desc.get(m.group(1), "")})
    return out


def programas():
    """Blender (o escolhido em Componentes ou o de versão mais alta), o Python dele e o texconv do Super Tool."""
    bl = componentes.achar_blender() or {}
    return {"BRFP_BLENDER": bl.get("exe", ""), "BRFP_BLENDER_PY": bl.get("python", ""), "BRFP_TEXCONV": componentes.texconv()}


def ambiente():
    p = programas()
    itens = [("Blender " + ((componentes.achar_blender() or {}).get("versao") or "5.2"), p["BRFP_BLENDER"]),
             ("Python do Blender", p["BRFP_BLENDER_PY"]), ("texconv", p["BRFP_TEXCONV"])]
    return [{"nome": n, "ok": bool(c) and os.path.isfile(c), "caminho": c or "não encontrado"} for n, c in itens]


def configs():
    pasta = os.path.join(CONVERSOR, "configs")
    out = []
    for n in sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []:
        if not n.endswith(".json"):
            continue
        p = os.path.join(pasta, n)
        try:
            c = ler_json(p)
        except (OSError, ValueError) as ex:
            out.append({"arquivo": p, "nome": n[:-5], "erro": str(ex)})
            continue
        nome = c.get("nome") or n[:-5]
        saida = os.path.join(RAIZ, "saida", nome)
        passos = os.path.join(saida, "PASSOS_FET.md")
        out.append({
            "arquivo": p, "nome": nome, "descricao": c.get("descricao", ""), "pes": (c.get("pes") or {}).get("mod", ""),
            "fc_export": (c.get("fc") or {}).get("export", ""), "fc_estadio": (c.get("fc") or {}).get("estadio", ""),
            "modo": c.get("modo", "malha_unica"), "saida": saida, "existe_saida": os.path.isdir(saida),
            "trabalho": os.path.join(RAIZ, "work", nome),
            "passos": passos if os.path.isfile(passos) else None,
            "passos_quando": time.strftime("%d/%m/%Y %H:%M", time.localtime(os.path.getmtime(passos))) if os.path.isfile(passos) else None,
            "entregue": os.path.isfile(os.path.join(saida, "manifesto_entregue.json")),
            "entregue_quando": time.strftime("%d/%m/%Y %H:%M", time.localtime(os.path.getmtime(os.path.join(saida, "manifesto_entregue.json"))))
            if os.path.isfile(os.path.join(saida, "manifesto_entregue.json")) else None,
        })
    return out


def acha_config(arquivo):
    for c in configs():
        if os.path.normcase(c["arquivo"]) == os.path.normcase(arquivo or ""):
            return c
    raise base.ErroUsuario("Configuração não encontrada.")


def exec_payload(desde=0):
    with LOCK:
        log = EXEC["log"]
        primeiro = EXEC["seq"] - len(log)
        ini = max(desde, primeiro)
        return {"rodando": EXEC["rodando"], "config": EXEC["config"], "args": EXEC["args"], "etapa": EXEC["etapa"],
                "etapas": EXEC["etapas"], "inicio": EXEC["inicio"], "fim": EXEC["fim"], "codigo": EXEC["codigo"],
                "seq": EXEC["seq"], "linhas": log[ini - primeiro:], "desde": ini}


# ------------------------------------------------------------------ execução
def registrar(linha):
    with LOCK:
        EXEC["log"].append(linha)
        EXEC["seq"] += 1
        if len(EXEC["log"]) > MAX_LOG:
            del EXEC["log"][:len(EXEC["log"]) - MAX_LOG]


def executar(args, config_arq):
    with LOCK:
        if EXEC["rodando"]:
            raise base.ErroUsuario("O conversor já está rodando.")
        EXEC.update(rodando=True, config=config_arq, args=args, etapa=None, etapas={}, inicio=time.time(), fim=0,
                    codigo=None, log=[], seq=0)
    cmd = base.python_cmd("-u", os.path.join(CONVERSOR, "converter.py")) + args
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", BRFP_RAIZ=RAIZ,
               **{k: v for k, v in programas().items() if v})
    registrar("> python conversor\\converter.py " + " ".join(f'"{a}"' if " " in a else a for a in args))
    try:
        proc = subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=env, creationflags=SEM_JANELA)
    except OSError as ex:
        with LOCK:
            EXEC.update(rodando=False, fim=time.time(), codigo=-1)
        raise base.ErroUsuario(f"Não foi possível iniciar o conversor: {ex}")
    EXEC["proc"] = proc
    threading.Thread(target=acompanhar, args=(proc,), daemon=True).start()


def acompanhar(proc):
    t_etapa = time.time()
    for linha in proc.stdout:
        linha = linha.rstrip("\r\n")
        m = re.match(r"^== ([a-z_]+)\s*$", linha)
        with LOCK:
            if m:
                ant = EXEC["etapa"]
                if ant and EXEC["etapas"].get(ant, {}).get("estado") == "rodando":
                    EXEC["etapas"][ant] = {"estado": "ok", "s": round(time.time() - t_etapa)}
                EXEC["etapa"] = m.group(1)
                EXEC["etapas"][m.group(1)] = {"estado": "rodando"}
                t_etapa = time.time()
            mt = re.match(r"^\s+\((\d+)s\)\s*$", linha)
            if mt and EXEC["etapa"]:
                EXEC["etapas"][EXEC["etapa"]] = {"estado": "ok", "s": int(mt.group(1))}
            mf = re.search(r"etapa ([a-z_]+) falhou", linha)
            if mf:
                EXEC["etapas"][mf.group(1)] = {"estado": "erro", "s": round(time.time() - t_etapa)}
        registrar(linha)
    cod = proc.wait()
    with LOCK:
        if EXEC["etapa"] and EXEC["etapas"].get(EXEC["etapa"], {}).get("estado") == "rodando":
            EXEC["etapas"][EXEC["etapa"]] = {"estado": "ok" if cod == 0 else "erro", "s": round(time.time() - t_etapa)}
        EXEC.update(rodando=False, proc=None, fim=time.time(), codigo=cod, etapa=None)
    registrar(f"[fim: {'concluído' if cod == 0 else f'código {cod}'} em {round(EXEC['fim'] - EXEC['inicio'])} s]")


# ------------------------------------------------------------------ rotas
def api_inicio(_):
    p = PREFS.ler()
    return {"versao": VERSAO, "raiz": RAIZ, "conversor": CONVERSOR, "existe": os.path.isfile(os.path.join(CONVERSOR, "converter.py")),
            "configs": configs(), "etapas": etapas(), "ambiente": ambiente(), "ultima": p.get("ultima"),
            "exec": exec_payload()}


def api_configs(_):
    return {"configs": configs()}


def api_exec(q):
    return exec_payload(int(q.get("desde") or 0))


def api_executar(d):
    c = acha_config(d.get("config"))
    nomes = [e["nome"] for e in etapas()]
    args = [c["arquivo"]]
    modo = d.get("modo", "tudo")
    if modo in ("de", "so"):
        if d.get("etapa") not in nomes:
            raise base.ErroUsuario("Etapa desconhecida.")
        args += ["--de" if modo == "de" else "--so", d["etapa"]]
    elif modo == "entregue":
        args += ["--entregue"]
    elif modo != "tudo":
        raise base.ErroUsuario("Modo inválido.")
    PREFS.atualizar(ultima=c["arquivo"])
    executar(args, c["arquivo"])
    return exec_payload()


def api_vazio(d):
    tpl = base.dialogo("abrir", "FBX do FET que vai virar o modelo vazio (template)", d.get("inicial"),
                       tipos=[("FBX", "*.fbx"), ("Todos", "*.*")])
    if not tpl:
        return {"cancelado": True}
    saida = base.dialogo("salvar", "Salvar o modelo vazio como", os.path.dirname(tpl),
                         tipos=[("FBX", "*.fbx")], nome=os.path.splitext(os.path.basename(tpl))[0] + "_vazio.fbx", extensao=".fbx")
    if not saida:
        return {"cancelado": True}
    executar(["--vazio", tpl, saida], None)
    return exec_payload()


def api_avaliar(d):
    c = acha_config(d.get("config"))
    nuvens = base.dialogo("abrir", "Nuvens de assentos (crowd_N.xml) dos estádios candidatos", RAIZ,
                          tipos=[("crowd XML", "*.xml"), ("Todos", "*.*")], multiplo=True)
    if not nuvens:
        return {"cancelado": True}
    executar([c["arquivo"], "--avaliar-base"] + nuvens, c["arquivo"])
    return exec_payload()


def api_parar(_):
    with LOCK:
        p = EXEC.get("proc")
    if p and p.poll() is None:
        # o conversor abre o Blender como subprocesso: encerra a árvore inteira
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=SEM_JANELA)
        else:
            p.kill()
        registrar("[parado pelo usuário]")
    return exec_payload()


def api_passos(q):
    c = acha_config(q.get("config"))
    if not c["passos"]:
        raise base.ErroUsuario("Ainda não há PASSOS_FET.md: rode a conversão (a etapa “passos” gera o arquivo).")
    with open(c["passos"], encoding="utf-8") as f:
        return {"texto": f.read(), "caminho": c["passos"], "quando": c["passos_quando"]}


def api_config_texto(q):
    c = acha_config(q.get("config"))
    with open(c["arquivo"], encoding="utf-8") as f:
        return {"texto": f.read(), "caminho": c["arquivo"]}


def api_abrir(d):
    alvo = d.get("caminho")
    if d.get("o_que") == "conversor":
        alvo = CONVERSOR
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo}")
    if d.get("editar") and os.path.isfile(alvo) and os.name == "nt":
        os.startfile(alvo)  # noqa: S606 — abre no programa padrão (editor de texto / visualizador de Markdown)
        return {}
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


# ------------------------------------------------------------------ formulário: caminhos, pastas do PES e do FET
def rel_ws(c):
    """Caminho relativo à pasta de trabalho quando está dentro dela (como nos JSON do conversor); senão, absoluto."""
    c = os.path.abspath(c)
    try:
        r = os.path.relpath(c, RAIZ)
        if not r.startswith(".."):
            return r.replace("\\", "/")
    except ValueError:
        pass
    return c.replace("\\", "/")


def abs_ws(c):
    return os.path.normpath(c if os.path.isabs(c or "") else os.path.join(RAIZ, c or ""))


def api_dialogo(d):
    modo = d.get("modo") or "pasta"
    ini = abs_ws(d.get("inicial")) if d.get("inicial") else RAIZ
    tipos = [("XML", "*.xml"), ("Todos", "*.*")] if d.get("tipo") == "xml" else [("FBX", "*.fbx"), ("Todos", "*.*")] if d.get("tipo") == "fbx" else None
    c = base.dialogo(modo, d.get("titulo") or "Escolher", ini, tipos=tipos, multiplo=bool(d.get("multiplo")))
    if not c:
        return {"cancelado": True}
    if isinstance(c, list):
        return {"caminhos": [rel_ws(x) for x in c]}
    return {"caminho": rel_ws(c), "absoluto": c}


def _bgs(mod):
    """Pastas Asset/model/bg do mod (a principal e as de AddOn/*/Global)."""
    out = [os.path.join(mod, "Asset", "model", "bg")]
    addon = os.path.join(mod, "AddOn")
    if os.path.isdir(addon):
        for n in os.listdir(addon):
            out.append(os.path.join(addon, n, "Global", "Asset", "model", "bg"))
    return [b for b in out if os.path.isdir(b)]


def api_escanear_pes(q):
    """Estádios (stNNN) de uma pasta de mod do PES e as variantes (pastas irmãs com o mesmo estádio)."""
    mod = abs_ws(q.get("mod"))
    if not os.path.isdir(mod):
        raise base.ErroUsuario(f"Pasta não encontrada: {mod}")
    estadios = {}
    for b in _bgs(mod):
        for n in os.listdir(b):
            if re.fullmatch(r"st\d{3}", n, re.I) and os.path.isdir(os.path.join(b, n)):
                fpk = sum(1 for dp, _, fs in os.walk(os.path.join(b, n)) for f in fs if ".fpk" in f.lower())
                e = estadios.setdefault(n.lower(), {"id": n.lower(), "fpk": 0, "audi": False})
                e["fpk"] += fpk
                e["audi"] = e["audi"] or os.path.isdir(os.path.join(b, n, "audi"))
    if not estadios:
        raise base.ErroUsuario("Não achei estádios (pastas stNNN em Asset\\model\\bg) nessa pasta. Escolha a pasta do mod do "
                               "PES que tem a pasta Asset.")
    pai = os.path.dirname(mod)
    variantes = {}
    for irma in sorted(os.listdir(pai)) if os.path.isdir(pai) else []:
        cam = os.path.join(pai, irma)
        if os.path.normcase(cam) == os.path.normcase(mod) or not os.path.isdir(cam):
            continue
        for sid in estadios:
            if any(os.path.isdir(os.path.join(b, sid)) for b in _bgs(cam)):
                variantes.setdefault(sid, []).append(rel_ws(cam))
    return {"mod": rel_ws(mod), "nome": os.path.basename(mod), "estadios": sorted(estadios.values(), key=lambda e: -e["fpk"]),
            "variantes": variantes}


def api_escanear_fc(q):
    """Mundos (worlds/stadiums) e componentes (worlds/components/stadiums) de um export do FET; para cada mundo, os
    componentes que os XML dele citam (o primeiro é o que ele usa)."""
    exp = abs_ws(q.get("export"))
    if not os.path.isdir(exp):
        raise base.ErroUsuario(f"Pasta não encontrada: {exp}")
    if not os.path.isdir(os.path.join(exp, "worlds")) and os.path.isdir(os.path.join(os.path.dirname(exp), "worlds")):
        exp = os.path.dirname(exp)
    pm = os.path.join(exp, "worlds", "stadiums")
    pc = os.path.join(exp, "worlds", "components", "stadiums")
    if not os.path.isdir(pm):
        raise base.ErroUsuario("Essa pasta não tem worlds\\stadiums: escolha a pasta do export do FET que contém a pasta worlds.")
    comps = sorted(n for n in os.listdir(pc) if os.path.isdir(os.path.join(pc, n))) if os.path.isdir(pc) else []
    mundos = []
    for n in sorted(os.listdir(pm)):
        cam = os.path.join(pm, n)
        if not os.path.isdir(cam):
            continue
        cont = {}
        mvdb = 0
        lidos = 0
        for dp, _, fs in os.walk(cam):
            for f in fs:
                if f.lower().startswith("meshvariationdb"):
                    mvdb += 1
                if not f.lower().endswith(".xml") or lidos > 400:
                    continue
                lidos += 1
                try:
                    with open(os.path.join(dp, f), encoding="utf-8", errors="ignore") as fh:
                        txt = fh.read(4_000_000).lower()
                except OSError:
                    continue
                for c in comps:
                    k = txt.count(f"components/stadiums/{c.lower()}/")
                    if k:
                        cont[c] = cont.get(c, 0) + k
        mundos.append({"nome": n, "componentes": sorted(cont.items(), key=lambda kv: -kv[1]), "mvdb": mvdb})
    return {"export": rel_ws(exp), "mundos": mundos, "componentes": comps,
            "tem_luz": os.path.isdir(os.path.join(exp, "worlds", "lightingisenviros")) or os.path.isdir(os.path.join(exp, "content", "worlds", "lighting"))}


def _padroes():
    """DEFAULTS do motor (conversor/lib/cfg.py), para o formulário mostrar o valor padrão de cada campo."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("cfg_conversor", os.path.join(CONVERSOR, "lib", "cfg.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return json.loads(json.dumps(m.DEFAULTS))
    except Exception:  # noqa: BLE001
        return {}


def api_config_ler(q):
    c = acha_config(q.get("config"))
    return {"dados": ler_json(c["arquivo"]), "padroes": _padroes(), "arquivo": c["arquivo"]}


def _validar(dados):
    if not isinstance(dados, dict):
        raise base.ErroUsuario("Configuração inválida.")
    nome = re.sub(r"[^\w\-]+", "_", str(dados.get("nome") or "").strip()).strip("_")
    if not nome:
        raise base.ErroUsuario("Dê um nome à conversão (vira o nome das pastas work\\<nome> e saida\\<nome>).")
    dados["nome"] = nome
    pes, fc = dados.get("pes") or {}, dados.get("fc") or {}
    faltam = [r for r, v in (("pasta do mod do PES", pes.get("mod")), ("estádio do PES", pes.get("estadio")),
                             ("export do FET", fc.get("export")), ("mundo do FC", fc.get("estadio")),
                             ("componentes do FC", fc.get("componentes"))) if not v]
    if faltam:
        raise base.ErroUsuario("Falta: " + ", ".join(faltam) + ".")
    avisos = []
    for rot, c in (("pasta do mod do PES", pes.get("mod")), ("export do FET", fc.get("export"))):
        if not os.path.isdir(abs_ws(c)):
            avisos.append(f"{rot} não existe: {c}")
    for v in pes.get("variantes") or []:
        if not os.path.isdir(abs_ws(v)):
            avisos.append(f"variante não existe: {v}")
    return dados, avisos


def api_config_salvar(d):
    """Grava a configuração (nova ou a que já existe) em conversor/configs/<nome>.json."""
    dados, avisos = _validar(d.get("dados"))
    pasta = os.path.join(CONVERSOR, "configs")
    os.makedirs(pasta, exist_ok=True)
    arq = d.get("arquivo")
    novo = os.path.join(pasta, dados["nome"] + ".json")
    if arq:
        acha_config(arq)
        if os.path.normcase(os.path.abspath(novo)) != os.path.normcase(os.path.abspath(arq)) and os.path.exists(novo):
            raise base.ErroUsuario(f"Já existe uma conversão chamada {dados['nome']}.")
    elif os.path.exists(novo):
        raise base.ErroUsuario(f"Já existe uma conversão chamada {dados['nome']}: escolha outro nome.")
    with open(novo + ".tmp", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(novo + ".tmp", novo)
    if arq and os.path.normcase(os.path.abspath(novo)) != os.path.normcase(os.path.abspath(arq)):
        base.mandar_para_lixeira(arq)                      # renomeada: o arquivo antigo vai para a Lixeira
    return {"arquivo": novo, "avisos": avisos, "configs": configs()}


def api_config_texto_salvar(d):
    c = acha_config(d.get("config"))
    try:
        dados = json.loads(d.get("texto") or "")
    except ValueError as ex:
        raise base.ErroUsuario(f"JSON inválido: {ex}")
    dados, avisos = _validar(dados)
    if dados["nome"] != c["nome"]:
        raise base.ErroUsuario("Para mudar o nome, use o formulário (ele cuida do arquivo).")
    with open(c["arquivo"], "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    return {"avisos": avisos, "configs": configs()}


def api_config_excluir(d):
    c = acha_config(d.get("config"))
    base.mandar_para_lixeira(c["arquivo"])
    apagadas = []
    if d.get("pastas"):
        for x in (c["trabalho"], c["saida"]):
            if os.path.isdir(x):
                base.mandar_para_lixeira(x)
                apagadas.append(x)
    return {"configs": configs(), "apagadas": apagadas}


def _saida_de(c):
    return os.path.join(RAIZ, "saida", c["nome"])


def api_previews(q):
    c = acha_config(q.get("config"))
    pasta = os.path.join(_saida_de(c), "previews")
    out = []
    if os.path.isdir(pasta):
        for n in sorted(os.listdir(pasta)):
            if n.lower().endswith((".png", ".jpg", ".jpeg")):
                cam = os.path.join(pasta, n)
                out.append({"nome": os.path.splitext(n)[0].replace("_", " "), "caminho": cam, "tamanho": os.path.getsize(cam)})
    return {"previews": out, "pasta": pasta}


def arquivo_imagem(h, q):
    """Imagens da saída e do trabalho do conversor (prévias), servidas para a interface."""
    cam = os.path.abspath(q.get("caminho") or "")
    ok = any(os.path.normcase(cam).startswith(os.path.normcase(os.path.join(RAIZ, x)) + os.sep) for x in ("saida", "work"))
    if not ok or not cam.lower().endswith((".png", ".jpg", ".jpeg")) or not os.path.isfile(cam):
        h.enviar(404, b"", "text/plain")
        return
    with open(cam, "rb") as f:
        h.enviar(200, f.read(), "image/png" if cam.lower().endswith(".png") else "image/jpeg")


def api_passos_marcar(d):
    """Lista de conferência do PASSOS_FET: o que já foi importado (vale enquanto o PASSOS for o mesmo)."""
    c = acha_config(d.get("config"))
    p = PREFS.ler()
    feitos = p.get("passos_feitos") or {}
    reg = feitos.get(c["arquivo"]) or {}
    if reg.get("quando") != c["passos_quando"]:
        reg = {"quando": c["passos_quando"], "itens": []}
    itens = set(reg.get("itens") or [])
    for k in d.get("itens") or []:
        (itens.add if d.get("feito", True) else itens.discard)(str(k))
    reg["itens"] = sorted(itens)
    feitos[c["arquivo"]] = reg
    PREFS.atualizar(passos_feitos=feitos)
    return {"itens": reg["itens"]}


def api_passos_feitos(q):
    c = acha_config(q.get("config"))
    reg = (PREFS.ler().get("passos_feitos") or {}).get(c["arquivo"]) or {}
    return {"itens": reg.get("itens") if reg.get("quando") == c["passos_quando"] else []}


ROTAS_GET = {"inicio": api_inicio, "configs": api_configs, "exec": api_exec, "passos": api_passos,
             "config_texto": api_config_texto, "versao": lambda _: {"versao": VERSAO}, "escanear_pes": api_escanear_pes,
             "escanear_fc": api_escanear_fc, "config_ler": api_config_ler, "previews": api_previews,
             "passos_feitos": api_passos_feitos}
ROTAS_POST = {"executar": api_executar, "vazio": api_vazio, "avaliar": api_avaliar, "parar": api_parar, "abrir": api_abrir,
              "dialogo": api_dialogo, "config_salvar": api_config_salvar, "config_texto_salvar": api_config_texto_salvar,
              "config_excluir": api_config_excluir, "passos_marcar": api_passos_marcar}


def main():
    ap = argparse.ArgumentParser(description="Conversor de Estádios PES 2021 -> FC 26 (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8772)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    a = ap.parse_args()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, especiais={"/arquivo": arquivo_imagem},
                                 nome="ConversorPES/" + VERSAO)
    base.servir(handler, a.porta, "Conversor PES -> FC", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
