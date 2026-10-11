"""Exporta arquivos do estádio com outro nome (para batch import do FET em outro estádio).

Troca os nomes nos caminhos (pastas e arquivos) e, nos XML, no texto (Name dos assets e referências).
Cada troca é "de -> para", sem diferenciar maiúsculas; as mais longas são aplicadas primeiro, para que
"events_stadium_517" vença "events_stadium". FBX e PNG só têm o caminho trocado.
"""
import os
import re
import shutil

from . import xmlfet as X
from .edicao import listar_alteracoes
from .indice import IGNORAR


def _compilar(trocas):
    pares = [(de.strip(), para.strip()) for de, para in trocas if de and de.strip()]
    pares.sort(key=lambda p: -len(p[0]))
    if not pares:
        return None, {}
    rx = re.compile("|".join(re.escape(de) for de, _ in pares), re.I)
    mapa = {de.lower(): para for de, para in pares}
    return rx, mapa


def _trocar(rx, mapa, texto):
    return rx.sub(lambda m: mapa[m.group(0).lower()], texto)


def arquivos(indice, escopo, mundo_asset=None):
    """[(id, rel)] dos arquivos no escopo: 'alterados', 'mundo' (pastas do mundo e dos componentes) ou 'tudo'."""
    raiz = indice.pastas[0]
    if escopo == "alterados":
        return [(a["id"], a["rel"]) for a in listar_alteracoes(indice) if a["estado"] == "alterado" and a["id"].startswith("0:")]
    out = []
    for dp, dns, ns in os.walk(raiz):
        dns[:] = [d for d in dns if d not in IGNORAR]
        for n in ns:
            rel = os.path.relpath(os.path.join(dp, n), raiz).replace("\\", "/")
            out.append((f"0:{rel}", rel))
    if escopo == "mundo" and mundo_asset:
        nome = mundo_asset.split("/")[-1].lower()
        pasta_mundo = "/".join(mundo_asset.lower().split("/")[1:-1]) + "/"      # worlds/stadiums/<nome>/
        comp = re.sub(r"_\d+$", "", nome)
        out = [(i, r) for i, r in out if pasta_mundo in r.lower() or f"/components/stadiums/{comp}/" in r.lower()
               or f"/stadiums/{comp}/" in r.lower()]
    return out


def previa(indice, trocas, escopo, mundo_asset=None, limite=400):
    rx, mapa = _compilar(trocas)
    lst = arquivos(indice, escopo, mundo_asset)
    out = []
    for ident, rel in lst:
        novo = _trocar(rx, mapa, rel) if rx else rel
        out.append({"de": rel, "para": novo, "muda": novo != rel})
    return {"total": len(out), "mudam": sum(1 for o in out if o["muda"]), "itens": out[:limite]}


def exportar(indice, trocas, escopo, destino, trocar_conteudo=True, mundo_asset=None):
    rx, mapa = _compilar(trocas)
    if rx is None:
        raise ValueError("Informe pelo menos uma troca de nome.")
    destino = os.path.abspath(destino)
    if os.path.commonpath([destino, indice.pastas[0]]) == indice.pastas[0]:
        raise ValueError("O destino não pode ficar dentro da pasta do export.")
    n_arq = n_txt = 0
    for ident, rel in arquivos(indice, escopo, mundo_asset):
        origem = indice.de_id(ident)
        novo_rel = _trocar(rx, mapa, rel)
        alvo = X.longo(os.path.join(destino, *novo_rel.split("/")))
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        if trocar_conteudo and rel.lower().endswith(".xml"):
            texto = X.ler(origem)
            novo = _trocar(rx, mapa, texto)
            with open(alvo, "w", encoding="utf-8-sig", newline="") as f:
                f.write(novo)
            if novo != texto:
                n_txt += 1
        else:
            shutil.copy2(X.longo(origem), alvo)
        n_arq += 1
    return {"destino": destino, "arquivos": n_arq, "xml_alterados": n_txt}
