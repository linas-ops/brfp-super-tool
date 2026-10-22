"""BRFP Super Tool — edições: o Super Tool com só algumas ferramentas (ex.: só o Editor de Placares), para compartilhar.

A edição é marcada pelo edicao.json na raiz da pasta do Super Tool, que só existe no .zip da edição (comum/pacote.py
grava na hora de gerar; não fica no repositório). Sem ele, o Super Tool é o completo, com todas as ferramentas.

    EDICOES     o que cada edição leva
    atual()     a edição desta pasta, ou None
"""
import json
import os

SUPERTOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO = "edicao.json"

EDICOES = {
    "placares": {
        "id": "placares",
        "nome": "Editor de Placares",
        "ferramentas": ["placares"],
        "porta": 8761,  # outra porta: dá para ter o Super Tool completo aberto ao mesmo tempo
        "descricao": "O Editor de Placares do BRFP Super Tool: abre os placares (overlays APT) do jogo e de mods, edita "
                     "textos, cores, imagens, posições, animações e fontes, e grava para o Live Editor.",
    },
}


def atual():
    try:
        with open(os.path.join(SUPERTOOL, ARQUIVO), encoding="utf-8") as f:
            e = json.load(f)
    except (OSError, ValueError):
        return None
    return e if isinstance(e, dict) and e.get("ferramentas") else None


def leva(e, caminho_rel):
    """Se o arquivo (caminho relativo à pasta do Super Tool, com /) entra na edição: das ferramentas, só as dela."""
    partes = caminho_rel.split("/")
    return not (e and len(partes) > 2 and partes[0] == "ferramentas" and partes[1] not in e["ferramentas"])
