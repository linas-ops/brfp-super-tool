"""BRFP Super Tool — gera o pacote para outro computador (.zip com a pasta "BRFP Super Tool").

    completo  com o Python embutido e os pacotes (numpy, SciPy, OpenCV, Pillow, servidor da Transfermarkt): abre sem internet
    leve      sem runtime: o BRFP Super Tool.bat baixa o Python na primeira vez e cada ferramenta baixa os pacotes
              de que precisa quando for aberta

O pacote leva também o motor do Conversor PES → FC e o RDBM 26 · Add-on FC 27 quando eles estão na pasta de trabalho
(ficam em ferramentas/conversor_pes/motor e ferramentas/rdbm). Nunca leva o que é deste computador: preferências,
banco e idioma importados, caches, o perfil da janela, saídas, backups, componentes_locais.json, addon.ini.

Edição (--edicao placares, ver comum/edicao.py): o Super Tool com só as ferramentas da edição, numa pasta com outro nome
e com o edicao.json que esconde o resto. O completo da edição leva só o Python (sem os pacotes que ela não usa).

    python pacote.py completo|leve [pasta de destino] [--edicao placares]
"""
import json
import os
import sys
import threading
import time
import zipfile

COMUM = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(COMUM)
sys.path.insert(0, COMUM)

import base  # noqa: E402
import componentes  # noqa: E402
import edicao  # noqa: E402

RAIZ_ZIP = "BRFP Super Tool"
# pastas e arquivos deste computador (em qualquer nível, fora de runtime/)
PASTAS_FORA = {".perfil_janela", "dados", "cache", "__pycache__", "exportados", "saida", "autosalvo", "downloads",
               "backups", "work", ".git", ".vscode", ".idea"}
ARQUIVOS_FORA = {"preferencias.json", "componentes_locais.json", "addon.ini", "addon.log", "local.json", "thumbs.db",
                 "desktop.ini"}
EXTENSOES_FORA = (".pyc", ".pyo", ".tmp", ".parcial", ".log", ".bak")
ESTADO = {"ativo": False, "tipo": None, "edicao": None, "fase": "", "feito": 0, "total": 0, "arquivo": None, "erro": None, "fim": 0,
          "tamanho": 0, "msg": ""}


def _fora(nome, eh_pasta):
    n = nome.lower()
    if eh_pasta:
        return n in PASTAS_FORA or n.startswith(".i-")
    return n in ARQUIVOS_FORA or n.endswith(EXTENSOES_FORA) or n.startswith(".instalando") or n.endswith(".tmp")


def _varrer(origem, destino_zip, excluir_pastas=(), runtime=False):
    """(caminho no disco, caminho no zip, tamanho) de tudo que entra."""
    out = []
    for dp, dn, fn in os.walk(origem):
        rel = os.path.relpath(dp, origem)
        partes = [] if rel == "." else rel.split(os.sep)
        if not partes and not runtime:
            dn[:] = [d for d in dn if d not in excluir_pastas]
        if runtime:
            dn[:] = [d for d in dn if d != "__pycache__" and not d.startswith(".i-") and d != "downloads"]
        else:
            dn[:] = [d for d in dn if not _fora(d, True) and not (not partes and d == "runtime")]
        for f in fn:
            if runtime:
                if f.endswith((".pyc", ".parcial")) or f.startswith(".instalando") or f.startswith(".teste"):
                    continue
            elif _fora(f, False):
                continue
            c = os.path.join(dp, f)
            try:
                tam = os.path.getsize(c)
            except OSError:
                continue
            out.append((c, "/".join([destino_zip] + partes + [f]), tam))
    return out


def raiz_zip(e=None):
    return f"{RAIZ_ZIP} - {e['nome']}" if e else RAIZ_ZIP


def _edicao(ed):
    if not ed:
        return None
    if ed not in edicao.EDICOES:
        raise ValueError("edição desconhecida: " + ed)
    return edicao.EDICOES[ed]


def lista(tipo, ed=None):
    """Tudo que vai no pacote (tipo 'completo' ou 'leve'; ed: id de uma edição ou None para o Super Tool inteiro)."""
    e = _edicao(ed)
    if e:
        return _lista_edicao(tipo, e)
    itens = _varrer(SUPERTOOL, RAIZ_ZIP)
    if tipo == "completo":
        g = componentes.estado_grupo
        if not componentes.python_embutido()["ok"]:
            raise componentes.ErroComponente("O Python embutido ainda não foi baixado: o pacote completo precisa dele. "
                                             "Baixe em Componentes ou gere o pacote leve.")
        # grupos opcionais (servidor da Transfermarkt) vão no pacote só se estiverem instalados
        faltam = [p for gr, d in componentes.manifesto()["grupos"].items() if not d.get("opcional") for p in g(gr)["faltam"]]
        if faltam:
            raise componentes.ErroComponente("Faltam pacotes no Python embutido (" + ", ".join(sorted(set(faltam))) +
                                             "). Instale tudo em Componentes antes de gerar o pacote completo.")
        itens += _varrer(componentes.RUNTIME, RAIZ_ZIP + "/runtime", runtime=True)
    # motor do Conversor PES e add-on do RDBM que ficam fora da pasta do Super Tool (na pasta de trabalho)
    conv = base.pasta_conversor()
    if os.path.isfile(os.path.join(conv, "converter.py")) and not _dentro(conv, SUPERTOOL):
        itens += _varrer(conv, RAIZ_ZIP + "/ferramentas/conversor_pes/motor")
    rdbm = base.pasta_rdbm()
    if os.path.isfile(os.path.join(rdbm, "RDBM26_FC27.exe")) and not _dentro(rdbm, SUPERTOOL):
        itens += _varrer(rdbm, RAIZ_ZIP + "/ferramentas/rdbm", excluir_pastas=("perfil",))
    return itens


def _lista_edicao(tipo, e):
    raiz = raiz_zip(e)
    n = len(raiz) + 1
    # sem .claude/.git* (coisas de quem desenvolve)
    itens = [i for i in _varrer(SUPERTOOL, raiz) if edicao.leva(e, i[1][n:]) and not i[1][n:].startswith(".")]
    if tipo == "completo":
        if not componentes.python_embutido()["ok"]:
            raise componentes.ErroComponente("O Python embutido ainda não foi baixado: o pacote completo precisa dele. "
                                             "Baixe em Componentes ou gere o pacote leve.")
        grupos = [g for g in componentes.manifesto()["grupos"] if g in e["ferramentas"]]
        faltam = [p for g in grupos for p in componentes.estado_grupo(g)["faltam"]]
        if faltam:
            raise componentes.ErroComponente("Faltam pacotes no Python embutido (" + ", ".join(sorted(set(faltam))) +
                                             "). Instale em Componentes antes de gerar o pacote completo.")
        py = _varrer(componentes.PYDIR, raiz + "/runtime/python", runtime=True)
        if not grupos:  # as ferramentas da edição não usam pacotes: só o Python
            py = [i for i in py if "/Lib/site-packages/" not in i[1]]
        itens += py
    return itens


def leia_me(e):
    """LEIA-ME PRIMEIRO.txt da edição (no lugar do geral, que fala de todas as ferramentas)."""
    t = f"""BRFP SUPER TOOL - {e['nome'].upper()}
{'=' * (18 + len(e['nome']))}

{e['descricao']}

COMO ABRIR
----------
1. Deixe esta pasta num lugar seu, de caminho curto (ex.: C:\\BRFP Placares ou Documentos).
2. Dê dois cliques em "BRFP Super Tool.bat".
   - Se o Windows avisar que o arquivo veio da internet: "Mais informações" > "Executar assim mesmo".
     Para não ver o aviso: antes de extrair o .zip, botão direito > Propriedades > marque "Desbloquear".
   - Pacote leve: na primeira vez ele pergunta se baixa o Python (11 MB, de python.org). Responda S.
     Precisa de internet só nessa hora; nada é instalado no Windows.
3. A janela abre direto no {e['nome']}. A janela preta precisa ficar aberta; feche-a para encerrar.

Guia completo: botão "Guia" no Início (o mesmo que o LEIAME.md da pasta ferramentas).
"""
    return "\ufeff" + t.replace("\n", "\r\n")


def _dentro(caminho, pasta):
    c, p = os.path.normcase(os.path.abspath(caminho)), os.path.normcase(os.path.abspath(pasta))
    return c == p or c.startswith(p + os.sep)


def gerar(tipo, destino, progresso=None, ed=None):
    """Grava '<destino>/BRFP Super Tool <versão> - [<edição> - ]<tipo>.zip'. Devolve o caminho."""
    if tipo not in ("completo", "leve"):
        raise ValueError("tipo: completo ou leve")
    e = _edicao(ed)
    versao = _versao()
    os.makedirs(destino, exist_ok=True)
    arquivo = os.path.join(destino, f"BRFP Super Tool {versao} - {e['nome'] + ' - ' if e else ''}{tipo}.zip")
    itens = lista(tipo, ed)
    if e:
        itens = [i for i in itens if i[1] != raiz_zip(e) + "/LEIA-ME PRIMEIRO.txt"]
    total = sum(t for _, _, t in itens) or 1
    tmp = arquivo + ".parcial"
    feito = 0
    ultimo = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for c, nome, tam in itens:
            # DLLs e .pyd grandes comprimem pouco: guardar direto é bem mais rápido
            metodo = zipfile.ZIP_STORED if nome.lower().endswith((".zip", ".png", ".jpg", ".whl")) else zipfile.ZIP_DEFLATED
            z.write(base.longo(c), nome, compress_type=metodo)
            feito += tam
            if progresso and (time.time() - ultimo > 0.25 or feito == total):
                ultimo = time.time()
                progresso(feito, total, nome)
        if e:
            z.writestr(raiz_zip(e) + "/" + edicao.ARQUIVO, json.dumps(e, ensure_ascii=False, indent=1))
            z.writestr(raiz_zip(e) + "/LEIA-ME PRIMEIRO.txt", leia_me(e))
    os.replace(tmp, arquivo)
    return arquivo


def _versao():
    import re
    with open(os.path.join(SUPERTOOL, "supertool.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSAO = "([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "?"


def iniciar(tipo, destino, ed=None):
    if ESTADO["ativo"]:
        return dict(ESTADO)
    ESTADO.update(ativo=True, tipo=tipo, edicao=ed, fase="listando", feito=0, total=0, arquivo=None, erro=None, fim=0, tamanho=0,
                  msg="Listando os arquivos…")

    def prog(feito, total, nome):
        ESTADO.update(fase="compactando", feito=feito, total=total, msg=nome.split("/", 1)[-1])

    def rodar():
        try:
            a = gerar(tipo, destino, prog, ed)
            ESTADO.update(fase="pronto", arquivo=a, tamanho=os.path.getsize(a), msg="Pacote pronto.")
        except componentes.ErroComponente as ex:
            ESTADO.update(fase="erro", erro=str(ex), msg=str(ex))
        except Exception as ex:  # noqa: BLE001
            ESTADO.update(fase="erro", erro=f"{type(ex).__name__}: {ex}", msg=str(ex))
        finally:
            ESTADO.update(ativo=False, fim=time.time())
    threading.Thread(target=rodar, daemon=True).start()
    return dict(ESTADO)


def resumo(ed=None):
    """Tamanhos estimados (sem compressão) para mostrar antes de gerar."""
    leve = sum(t for _, _, t in lista("leve", ed))
    try:
        completo = sum(t for _, _, t in lista("completo", ed))
    except componentes.ErroComponente as ex:
        completo, motivo = None, str(ex)
    else:
        motivo = None
    return {"leve": leve, "completo": completo, "motivo_completo": motivo, "versao": _versao(), "edicao": ed}


if __name__ == "__main__":
    args = sys.argv[1:]
    ed = None
    if "--edicao" in args:
        i = args.index("--edicao")
        ed = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    if not args or args[0] not in ("completo", "leve") or (ed is not None and ed not in edicao.EDICOES):
        print(__doc__)
        sys.exit(2)
    dest = args[1] if len(args) > 1 else os.path.dirname(SUPERTOOL)
    t0 = time.time()
    arq = gerar(args[0], dest, lambda f, t, n: (sys.stdout.write(f"\r  {f * 100 // t:3d}%  {n[-60:]:60s}"), sys.stdout.flush()), ed)
    print(f"\n{arq}  ({os.path.getsize(arq) / 1048576:.0f} MB, {time.time() - t0:.0f} s)")
