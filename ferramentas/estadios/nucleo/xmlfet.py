"""Leitura e edição dos XML (ebx) exportados pelo FET.

As edições são trocas de texto dentro de um <instance>, para que o resto do arquivo continue idêntico
byte a byte (o FET importa o XML por cima do asset de mesmo nome).
"""
import os
import re
import xml.etree.ElementTree as ET

BS = "\\"
NUM = r"-?[0-9.]+(?:[Ee][-+]?[0-9]+)?"


def longo(caminho):
    """No Windows, caminhos com mais de 260 caracteres precisam do prefixo \\\\?\\ (o FET gera pastas longas)."""
    if os.name == "nt" and len(caminho) > 240 and not caminho.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(caminho)
    return caminho


def ler(caminho):
    with open(longo(caminho), encoding="utf-8-sig", newline="") as f:   # mantém CRLF/LF como estão
        return f.read()


def gravar(caminho, texto):
    ET.fromstring(texto.encode("utf-8"))  # continua bem formado?
    with open(longo(caminho), "w", encoding="utf-8-sig", newline="") as f:
        f.write(texto)


def analisar(texto):
    return ET.fromstring(texto.encode("utf-8"))


def fmt(v):
    s = f"{float(v):.9g}"
    return "0" if s in ("-0", "0", "-0.0") else s


def fmt_mantendo(antigo, v):
    """Como fmt, mas devolve o texto original quando o número não mudou de fato (a decomposição em
    posição/rotação/escala no editor gera ruído como 3.67e-16 no lugar de 0 ou mexe na 9ª casa)."""
    try:
        a = float(antigo)
    except ValueError:
        return fmt(v)
    return antigo if abs(a - float(v)) <= 1e-6 * max(1.0, abs(a)) else fmt(v)


def curto(ref):
    """'content/a/b/nome\\\\guid' -> 'nome'"""
    return (ref or "").split(BS)[0].split("/")[-1]


def caminho_asset(ref):
    return (ref or "").split(BS)[0]


RX_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def eh_guid(g):
    return bool(g) and bool(RX_GUID.match(g))


def guid_ref(ref):
    return (ref or "").split(BS)[-1]


def vec(no):
    return [float(no.find(f"field[@name='{a}']").text) for a in "xyz"]


def transformacao(no):
    """<complex type="LinearTransform"> -> [rx,ry,rz, ux,uy,uz, fx,fy,fz, tx,ty,tz]"""
    out = []
    for k in ("right", "up", "forward", "trans"):
        out += vec(no.find(f"field[@name='{k}']/complex"))
    return out


IDENT = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def compor(a, b):
    """Transformação a aplicada depois de b (ponto p -> a(b(p))). Formato de 12 números."""
    def ap_dir(t, v):
        return [v[0] * t[0] + v[1] * t[3] + v[2] * t[6], v[0] * t[1] + v[1] * t[4] + v[2] * t[7],
                v[0] * t[2] + v[1] * t[5] + v[2] * t[8]]
    r = ap_dir(a, b[0:3])
    u = ap_dir(a, b[3:6])
    f = ap_dir(a, b[6:9])
    t = ap_dir(a, b[9:12])
    t = [t[0] + a[9], t[1] + a[10], t[2] + a[11]]
    return r + u + f + t


def aplicar(t, p):
    return [p[0] * t[0] + p[1] * t[3] + p[2] * t[6] + t[9], p[0] * t[1] + p[1] * t[4] + p[2] * t[7] + t[10],
            p[0] * t[2] + p[1] * t[5] + p[2] * t[8] + t[11]]


# ---------------------------------------------------------------- localização no texto

def trecho_instancia(texto, guid):
    ini = texto.find(f'<instance guid="{guid}"')
    if ini < 0:
        raise KeyError(f"instância {guid} não encontrada")
    fim = texto.index("</instance>", ini) + len("</instance>")
    return ini, fim


def _fim_elemento(texto, ini, tag):
    """Fim (exclusivo) do elemento <tag ...> que começa em ini, respeitando aninhamento."""
    abre = re.compile(rf"<{tag}\b[^>]*?(/?)>")
    fecha = f"</{tag}>"
    m = abre.match(texto, ini)
    if m.group(1) == "/":
        return m.end()
    prof, pos = 1, m.end()
    while prof:
        prox_fecha = texto.index(fecha, pos)
        m2 = abre.search(texto, pos, prox_fecha)
        if m2:
            if m2.group(1) != "/":
                prof += 1
            pos = m2.end()
        else:
            prof -= 1
            pos = prox_fecha + len(fecha)
    return pos


def campo_span(bloco, nome, ini=0):
    """(início, fim) do <field name="nome"> (primeiro a partir de ini) dentro do bloco."""
    m = re.compile(rf'<field name="{re.escape(nome)}"').search(bloco, ini)
    if not m:
        return None
    return m.start(), _fim_elemento(bloco, m.start(), "field")


def array_span(bloco, nome, ini=0):
    m = re.compile(rf'<array name="{re.escape(nome)}"').search(bloco, ini)
    if not m:
        return None
    return m.start(), _fim_elemento(bloco, m.start(), "array")


def itens(bloco, ini, fim):
    """Spans dos <item> diretos dentro de [ini, fim) (o array)."""
    out = []
    pos = bloco.index(">", ini) + 1
    while True:
        m = re.compile(r"<item\b").search(bloco, pos, fim)
        if not m:
            break
        e = _fim_elemento(bloco, m.start(), "item")
        out.append((m.start(), e))
        pos = e
    return out


def trocar_linear(trecho, valores):
    """Troca os 12 números do primeiro LinearTransform do trecho."""
    nomes = ("right", "up", "forward", "trans")
    pos = 0
    out = trecho
    for i, k in enumerate(nomes):
        sp = campo_span(out, k, pos)
        if not sp:
            raise ValueError(f"LinearTransform sem {k}")
        sub = out[sp[0]:sp[1]]
        for j, eixo in enumerate("xyz"):
            sub = re.sub(rf'(<field name="{eixo}">)({NUM})(</field>)',
                         lambda m, v=valores[i * 3 + j]: m.group(1) + fmt_mantendo(m.group(2), v) + m.group(3), sub, count=1)
        out = out[:sp[0]] + sub + out[sp[1]:]
        pos = sp[0] + len(sub)
    return out


def trocar_valor_campo(trecho, nome, valor):
    novo, n = re.subn(rf'(<field name="{re.escape(nome)}">)[^<]*(</field>)', lambda m: m.group(1) + valor + m.group(2),
                      trecho, count=1)
    if n != 1:
        raise ValueError(f"campo {nome} não encontrado")
    return novo
