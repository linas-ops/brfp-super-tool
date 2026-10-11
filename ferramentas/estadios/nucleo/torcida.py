"""Nuvem de assentos da torcida (CrowdPlacementPointCloudDataAsset): leitura e remoção de assentos.

O asset tem uma lista Data (Position de cada assento) e, em instâncias seguintes, um mapa por assento
(SeatColor, SeatTier, Attendance, Orientation, ...) com um valor por assento, na mesma ordem.
"""
import re

from . import xmlfet as X

RX_POS = re.compile(r'<field name="x">(' + X.NUM + r')</field>\s*<field name="y">(' + X.NUM + r')</field>\s*<field name="z">('
                    + X.NUM + r')</field>')
RX_MAPA = re.compile(r'<field name="Name">([^<]+)</field>\s*<array name="val" type="([^"]+)"\s*(/>|>(.*?)</array>)', re.S)


def ler(caminho):
    texto = X.ler(caminho)
    ini = texto.index('<array name="Data"')
    fim = texto.index("</array>", ini)
    pos = []
    for m in RX_POS.finditer(texto, ini, fim):
        pos += [round(float(m.group(1)), 3), round(float(m.group(2)), 3), round(float(m.group(3)), 3)]
    mapas = {}
    for m in RX_MAPA.finditer(texto, fim):
        valores = re.findall(r"<item>([^<]*)</item>", m.group(4) or "")
        if m.group(2) in ("Float32", "Float64"):
            mapas[m.group(1)] = [round(float(v), 4) for v in valores]
        else:
            mapas[m.group(1)] = [int(v) for v in valores]
    return {"posicoes": pos, "mapas": mapas, "n": len(pos) // 3}


def _fmt_valor(v, tipo):
    if tipo.startswith(("Uint", "Int")):
        return str(int(round(v)))
    return X.fmt(v)


def reescrever(texto, posicoes, mapas):
    """Substitui todos os assentos: lista Data (posições) e cada mapa por assento (mesma ordem e quantidade)."""
    n = len(posicoes) // 3
    nl = "\r\n" if "\r\n" in texto else "\n"
    ini = texto.index('<array name="Data"')
    fim_arr = X._fim_elemento(texto, ini, "array")
    its = X.itens(texto, ini, fim_arr)
    if not its:
        raise ValueError("a nuvem de assentos original está vazia; não há modelo para os itens")
    s0, e0 = its[0]
    linha0 = texto.rfind("\n", 0, s0) + 1
    modelo = texto[linha0:e0]                      # indentação + <item>...</item> do primeiro assento
    pre, pos_ = modelo.split('<field name="x">', 1)
    meio_y = pos_.split('<field name="y">', 1)
    meio_z = meio_y[1].split('<field name="z">', 1)
    corpo_x = meio_y[0][meio_y[0].index("</field>"):]
    corpo_y = meio_z[0][meio_z[0].index("</field>"):]
    corpo_z = meio_z[1][meio_z[1].index("</field>"):]
    partes = []
    for i in range(n):
        x, y, z = posicoes[i * 3:i * 3 + 3]
        partes.append(f'{pre}<field name="x">{X.fmt(x)}{corpo_x}<field name="y">{X.fmt(y)}{corpo_y}<field name="z">{X.fmt(z)}{corpo_z}')
    ult = its[-1][1]
    texto = texto[:linha0] + nl.join(partes) + texto[ult:]
    # mapas
    for nome, valores in mapas.items():
        if len(valores) != n:
            raise ValueError(f"mapa {nome} com {len(valores)} valores para {n} assentos")
        m = re.search(rf'<field name="Name">{re.escape(nome)}</field>\s*(<array name="val" type="([^"]+)"\s*(/>|>))', texto)
        if not m:
            continue
        tipo = m.group(2)
        a_ini = m.start(1)
        a_fim = X._fim_elemento(texto, a_ini, "array")
        linha = texto.rfind("\n", 0, a_ini) + 1
        recuo = texto[linha:a_ini]
        corpo = nl.join(f"{recuo}\t<item>{_fmt_valor(v, tipo)}</item>" for v in valores)
        novo = f'<array name="val" type="{tipo}">{nl}{corpo}{nl}{recuo}</array>' if valores else f'<array name="val" type="{tipo}" />'
        texto = texto[:a_ini] + novo + texto[a_fim:]
    return texto


def _sem_itens(texto, a_ini, a_fim, its, tirar):
    """Trecho [a_ini, a_fim) sem os itens de índice em tirar (leva junto a indentação e a quebra de linha antes)."""
    partes, ult = [], a_ini
    for i, (s, e) in enumerate(its):
        if i not in tirar:
            continue
        s2 = s
        while s2 > ult and texto[s2 - 1] in " \t":
            s2 -= 1
        if s2 > ult and texto[s2 - 1] == "\n":
            s2 -= 1
            if s2 > ult and texto[s2 - 1] == "\r":
                s2 -= 1
        partes.append(texto[ult:s2])
        ult = e
    partes.append(texto[ult:a_fim])
    return "".join(partes)


def remover(texto, indices):
    """Remove os assentos de índices dados da lista Data e de todos os mapas."""
    tirar = set(indices)
    ini = texto.index('<array name="Data"')
    fim_arr = X._fim_elemento(texto, ini, "array")
    its = X.itens(texto, ini, fim_arr)
    total = len(its)
    texto = texto[:ini] + _sem_itens(texto, ini, fim_arr, its, tirar) + texto[fim_arr:]
    # mapas por assento: arrays "val" com um item por assento
    mapas = []
    for m in re.finditer(r'<array name="val" type="[^"]+"\s*>', texto):
        e = X._fim_elemento(texto, m.start(), "array")
        sub = X.itens(texto, m.start(), e)
        if len(sub) == total:
            mapas.append((m.start(), e, sub))
    for a_ini, a_fim, sub in reversed(mapas):
        texto = texto[:a_ini] + _sem_itens(texto, a_ini, a_fim, sub, tirar) + texto[a_fim:]
    return texto, total - len(tirar & set(range(total)))
