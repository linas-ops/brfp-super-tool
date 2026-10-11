"""stadiums.txt (tabela de estádios do banco do jogo, separada por TAB): leitura e edição da linha de um estádio.

Campos que o editor usa:
  stadiumpitchlength / stadiumpitchwidth   gramado em cm (as linhas do campo que o jogo desenha)
  ismirrored                               1 = o jogo espelha o estádio (EA usa nos estádios com os bancos em +Z)
  stad{home,away}techzone{min,max}{x,z}    área técnica de cada time em cm (onde ficam técnico e reservas)
"""
import os
import re

COLUNAS_ZONA = {"casa": ("stadhometechzoneminx", "stadhometechzonemaxx", "stadhometechzoneminz", "stadhometechzonemaxz"),
                "fora": ("stadawaytechzoneminx", "stadawaytechzonemaxx", "stadawaytechzoneminz", "stadawaytechzonemaxz")}


def localizar(pastas, raiz_workspace):
    """O stadiums.txt mais perto do export (na pasta, na pasta acima ou na raiz do workspace)."""
    locais = []
    for pasta in pastas:
        locais += [os.path.join(pasta, "stadiums.txt"), os.path.join(os.path.dirname(pasta), "stadiums.txt")]
    locais.append(os.path.join(raiz_workspace, "stadiums.txt"))
    for arq in locais:
        if os.path.isfile(arq):
            try:
                with open(arq, encoding="utf-8", errors="replace") as f:
                    if "stadiumid" in f.readline().split("\t"):
                        return os.path.abspath(arq)
            except OSError:
                continue
    return None


def id_do_mundo(mundo_asset):
    m = re.search(r"_(\d+)$", mundo_asset or "")
    return m.group(1) if m else None


def _ler(arq):
    with open(arq, "rb") as f:
        b = f.read()
    bom = b.startswith(b"\xef\xbb\xbf")
    t = (b[3:] if bom else b).decode("utf-8", errors="surrogateescape")   # sem perdas, qualquer codificação
    nl = "\r\n" if "\r\n" in t else "\n"
    return t, nl, bom


def ler(arq, sid):
    """{coluna: valor} da linha do estádio, ou None."""
    if not arq or not sid:
        return None
    t, nl, _ = _ler(arq)
    linhas = t.split(nl)
    cab = linhas[0].split("\t")
    i_id = cab.index("stadiumid")
    for l in linhas[1:]:
        c = l.split("\t")
        if len(c) > i_id and c[i_id] == str(sid):
            return dict(zip(cab, c))
    return None


def resumo(arq, sid):
    """O que o editor mostra: medidas, espelhamento e áreas técnicas (em metros)."""
    linha = ler(arq, sid)
    if not linha:
        return None

    def num(k, padrao=0.0):
        try:
            return float(linha.get(k, padrao))
        except (TypeError, ValueError):
            return padrao
    return {"id": str(sid), "nome": linha.get("name", ""), "arquivo": arq,
            "comprimento": num("stadiumpitchlength", 10500) / 100, "largura": num("stadiumpitchwidth", 6800) / 100,
            "espelhado": linha.get("ismirrored", "0") == "1",
            "zonas": {lado: [num(k) / 100 for k in cols] for lado, cols in COLUNAS_ZONA.items()}}


def trocar(texto, sid, valores):
    """Texto do arquivo com as colunas da linha do estádio trocadas (o resto fica byte a byte igual)."""
    nl = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.split(nl)
    cab = linhas[0].split("\t")
    i_id = cab.index("stadiumid")
    for k in valores:
        if k not in cab:
            raise KeyError(f"coluna {k} não existe no stadiums.txt")
    for i, l in enumerate(linhas[1:], 1):
        c = l.split("\t")
        if len(c) > i_id and c[i_id] == str(sid):
            for k, v in valores.items():
                c[cab.index(k)] = str(v)
            linhas[i] = "\t".join(c)
            return nl.join(linhas)
    raise KeyError(f"estádio {sid} não está no stadiums.txt")


def gravar(arq, sid, valores):
    t, nl, bom = _ler(arq)
    novo = trocar(t, sid, valores)
    if novo == t:
        return False
    with open(arq, "wb") as f:
        f.write((b"\xef\xbb\xbf" if bom else b"") + novo.encode("utf-8", errors="surrogateescape"))
    return True
