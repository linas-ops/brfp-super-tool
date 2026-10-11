"""BRFP Super Tool — gera o pacote para outro computador (.zip com a pasta "BRFP Super Tool").

    completo  com o Python embutido e os pacotes (numpy, SciPy, OpenCV, Pillow, servidor da Transfermarkt): abre sem internet
    leve      sem runtime: o BRFP Super Tool.bat baixa o Python na primeira vez e cada ferramenta baixa os pacotes
              de que precisa quando for aberta

O pacote leva também o motor do Conversor PES → FC e o RDBM 26 · Add-on FC 27 quando eles estão na pasta de trabalho
(ficam em ferramentas/conversor_pes/motor e ferramentas/rdbm). Nunca leva o que é deste computador: preferências,
banco e idioma importados, caches, o perfil da janela, saídas, backups, componentes_locais.json, addon.ini.

    python pacote.py completo|leve [pasta de destino]
"""
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

RAIZ_ZIP = "BRFP Super Tool"
# pastas e arquivos deste computador (em qualquer nível, fora de runtime/)
PASTAS_FORA = {".perfil_janela", "dados", "cache", "__pycache__", "exportados", "saida", "autosalvo", "downloads",
               "backups", "work", ".git", ".vscode", ".idea"}
ARQUIVOS_FORA = {"preferencias.json", "componentes_locais.json", "addon.ini", "addon.log", "local.json", "thumbs.db",
                 "desktop.ini"}
EXTENSOES_FORA = (".pyc", ".pyo", ".tmp", ".parcial", ".log", ".bak")
ESTADO = {"ativo": False, "tipo": None, "fase": "", "feito": 0, "total": 0, "arquivo": None, "erro": None, "fim": 0,
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


def lista(tipo):
    """Tudo que vai no pacote (tipo 'completo' ou 'leve')."""
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


def _dentro(caminho, pasta):
    c, p = os.path.normcase(os.path.abspath(caminho)), os.path.normcase(os.path.abspath(pasta))
    return c == p or c.startswith(p + os.sep)


def gerar(tipo, destino, progresso=None):
    """Grava '<destino>/BRFP Super Tool <versão> - <tipo>.zip'. Devolve o caminho."""
    if tipo not in ("completo", "leve"):
        raise ValueError("tipo: completo ou leve")
    versao = _versao()
    os.makedirs(destino, exist_ok=True)
    arquivo = os.path.join(destino, f"BRFP Super Tool {versao} - {tipo}.zip")
    itens = lista(tipo)
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
    os.replace(tmp, arquivo)
    return arquivo


def _versao():
    import re
    with open(os.path.join(SUPERTOOL, "supertool.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSAO = "([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "?"


def iniciar(tipo, destino):
    if ESTADO["ativo"]:
        return dict(ESTADO)
    ESTADO.update(ativo=True, tipo=tipo, fase="listando", feito=0, total=0, arquivo=None, erro=None, fim=0, tamanho=0,
                  msg="Listando os arquivos…")

    def prog(feito, total, nome):
        ESTADO.update(fase="compactando", feito=feito, total=total, msg=nome.split("/", 1)[-1])

    def rodar():
        try:
            a = gerar(tipo, destino, prog)
            ESTADO.update(fase="pronto", arquivo=a, tamanho=os.path.getsize(a), msg="Pacote pronto.")
        except componentes.ErroComponente as ex:
            ESTADO.update(fase="erro", erro=str(ex), msg=str(ex))
        except Exception as ex:  # noqa: BLE001
            ESTADO.update(fase="erro", erro=f"{type(ex).__name__}: {ex}", msg=str(ex))
        finally:
            ESTADO.update(ativo=False, fim=time.time())
    threading.Thread(target=rodar, daemon=True).start()
    return dict(ESTADO)


def resumo():
    """Tamanhos estimados (sem compressão) para mostrar antes de gerar."""
    leve = sum(t for _, _, t in lista("leve"))
    try:
        completo = sum(t for _, _, t in lista("completo"))
    except componentes.ErroComponente as ex:
        completo, motivo = None, str(ex)
    else:
        motivo = None
    return {"leve": leve, "completo": completo, "motivo_completo": motivo, "versao": _versao()}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("completo", "leve"):
        print(__doc__)
        sys.exit(2)
    dest = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(SUPERTOOL)
    t0 = time.time()
    arq = gerar(sys.argv[1], dest, lambda f, t, n: (sys.stdout.write(f"\r  {f * 100 // t:3d}%  {n[-60:]:60s}"), sys.stdout.flush()))
    print(f"\n{arq}  ({os.path.getsize(arq) / 1048576:.0f} MB, {time.time() - t0:.0f} s)")
