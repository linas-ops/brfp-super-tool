"""Edições salvas: cada arquivo gravado na pasta de saída tem um projeto (fonte original + operações), para
reabrir e continuar editando, refazer a partir do original ou desfazer tudo.

Também guarda as imagens importadas (RGBA cru) e as cópias de segurança de arquivos que já estavam na saída.
"""
import hashlib
import json
import os
import shutil
import struct
import time
import zlib

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(AQUI, "projetos")
IMAGENS = os.path.join(PASTA, "imagens")
BACKUP = os.path.join(PASTA, "backup")


def _chave(saida, alvo):
    return hashlib.sha1((os.path.abspath(saida).lower() + "|" + alvo.lower().replace("\\", "/")).encode("utf-8")).hexdigest()[:20]


def caminho_saida(saida, alvo):
    return os.path.join(os.path.abspath(saida), *alvo.replace("\\", "/").split("/"))


def carregar(saida, alvo):
    arq = os.path.join(PASTA, _chave(saida, alvo) + ".json")
    if not os.path.isfile(arq):
        return None
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def gravar_saida(saida, alvo, dados, fonte, arquivo, ops):
    """Grava o .big na saída (com cópia de segurança do que já existia lá) e o projeto."""
    destino = caminho_saida(saida, alvo)
    proj = carregar(saida, alvo) or {}
    backup = proj.get("backup")
    if not proj and os.path.isfile(destino):   # arquivo que não fomos nós que gravamos: guarda
        os.makedirs(BACKUP, exist_ok=True)
        backup = os.path.join(BACKUP, _chave(saida, alvo) + "_" + os.path.basename(destino))
        shutil.copy2(destino, backup)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + ".tmp"
    with open(tmp, "wb") as f:
        f.write(dados)
    os.replace(tmp, destino)
    proj = {"formato": "editor-placares", "saida": os.path.abspath(saida), "alvo": alvo, "arquivo": arquivo,
            "fonte": fonte, "ops": ops, "backup": backup, "quando": time.strftime("%d/%m/%Y %H:%M"),
            "criado": proj.get("criado") or time.strftime("%d/%m/%Y %H:%M")}
    os.makedirs(PASTA, exist_ok=True)
    arq = os.path.join(PASTA, _chave(saida, alvo) + ".json")
    with open(arq + ".tmp", "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=1)
    os.replace(arq + ".tmp", arq)
    return destino


def descartar(saida, alvo):
    """Apaga o arquivo gravado (ou devolve o que existia antes) e o projeto."""
    destino = caminho_saida(saida, alvo)
    proj = carregar(saida, alvo)
    if proj and proj.get("backup") and os.path.isfile(proj["backup"]):
        shutil.copy2(proj["backup"], destino)
        restaurado = True
    else:
        restaurado = False
        if proj and os.path.isfile(destino):
            os.remove(destino)
    arq = os.path.join(PASTA, _chave(saida, alvo) + ".json")
    if os.path.isfile(arq):
        os.remove(arq)
    return restaurado


def listar(saida=None):
    out = []
    if not os.path.isdir(PASTA):
        return out
    for n in os.listdir(PASTA):
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(PASTA, n), encoding="utf-8") as f:
                p = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(p, dict) or p.get("formato") != "editor-placares":    # tema_*.json e outros
            continue
        if saida and os.path.abspath(saida).lower() != p.get("saida", "").lower():
            continue
        p["existe"] = os.path.isfile(caminho_saida(p["saida"], p["alvo"]))
        p["n_ops"] = len(p.get("ops") or {})
        p.pop("ops", None)
        out.append(p)
    out.sort(key=lambda p: time.mktime(time.strptime(p.get("quando", "01/01/2000 00:00"), "%d/%m/%Y %H:%M")), reverse=True)
    return out


# ------------------------------------------------------------------ imagens importadas

def salvar_imagem(w, h, rgba):
    if len(rgba) != w * h * 4:
        raise ValueError("Imagem com tamanho inconsistente")
    ident = hashlib.sha1(struct.pack("<II", w, h) + rgba).hexdigest()[:24]
    os.makedirs(IMAGENS, exist_ok=True)
    arq = os.path.join(IMAGENS, ident + ".rgba")
    if not os.path.isfile(arq):
        with open(arq, "wb") as f:
            f.write(struct.pack("<II", w, h) + zlib.compress(rgba, 6))
    return ident


def ler_imagem(ident):
    if not ident.isalnum():
        raise ValueError("Imagem inválida")
    with open(os.path.join(IMAGENS, ident + ".rgba"), "rb") as f:
        b = f.read()
    w, h = struct.unpack_from("<II", b, 0)
    return w, h, zlib.decompress(b[8:])


def png(w, h, rgba):
    linhas = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def bloco(tipo, dados):
        c = struct.pack(">I", len(dados)) + tipo + dados
        return c + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            bloco(b"IDAT", zlib.compress(linhas, 6)) + bloco(b"IEND", b""))
