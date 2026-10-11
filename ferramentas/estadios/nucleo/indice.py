"""Índice das pastas exportadas pelo FET: caminho do asset no jogo -> arquivo no disco.

O FET exporta com ou sem o prefixo content/ (ex.: "Events 5v5\\worlds\\..." ou "...\\content\\worlds\\...").
A chave é o caminho do asset em minúsculas, sem "content/", com a extensão. A primeira pasta é a principal
(onde as edições são gravadas); as demais são pastas de apoio, só leitura.
"""
import os
import re

from . import xmlfet as X

EXTENSOES = {".xml", ".fbx", ".png", ".dds", ".tga", ".jpg", ".jpeg"}
PASTA_BACKUP = "_editor_originais"
IGNORAR = {PASTA_BACKUP, "_editor_alteracoes", ".git", "__pycache__", "node_modules"}
TIPOS_MUNDO = {"DetachedSubWorldData", "LevelData"}


def chave(caminho_asset, ext=""):
    k = caminho_asset.replace("\\", "/").lower().lstrip("/")
    if k.startswith("content/"):
        k = k[8:]
    return k + ext.lower()


class Indice:
    def __init__(self, pastas):
        self.pastas = [os.path.abspath(p) for p in pastas]
        self.mapa = {}          # chave -> (índice da pasta, caminho relativo)
        self.duplicados = 0
        for ri, raiz in enumerate(self.pastas):
            for dp, dns, ns in os.walk(raiz):
                dns[:] = [d for d in dns if d not in IGNORAR]
                for n in ns:
                    ext = os.path.splitext(n)[1].lower()
                    if ext not in EXTENSOES:
                        continue
                    rel = os.path.relpath(os.path.join(dp, n), raiz).replace("\\", "/")
                    k = chave(rel)
                    atual = self.mapa.get(k)
                    if atual is None:
                        self.mapa[k] = (ri, rel)
                        continue
                    self.duplicados += 1
                    # pasta anterior vence; na mesma pasta, o original com content/ vence
                    if atual[0] == ri and not atual[1].lower().startswith("content/") and rel.lower().startswith("content/"):
                        self.mapa[k] = (ri, rel)

    def achar(self, caminho_asset, ext):
        return self.mapa.get(chave(caminho_asset, ext))

    def absoluto(self, item):
        ri, rel = item
        return os.path.join(self.pastas[ri], *rel.split("/"))

    def arquivo(self, caminho_asset, ext):
        item = self.achar(caminho_asset, ext)
        return self.absoluto(item) if item else None

    def id_arquivo(self, item):
        return f"{item[0]}:{item[1]}"

    def de_id(self, ident):
        ri, rel = ident.split(":", 1)
        ri = int(ri)
        raiz = self.pastas[ri]
        caminho = os.path.abspath(os.path.join(raiz, *rel.split("/")))
        if not caminho.startswith(raiz + os.sep):
            raise PermissionError("caminho fora da pasta")
        return caminho

    def mundos(self):
        """Mundos de estádio (DetachedSubWorldData / LevelData) encontrados nas pastas."""
        out = []
        for k, item in self.mapa.items():
            if not k.endswith(".xml"):
                continue
            partes = k[:-4].split("/")
            # o mundo fica em <pasta>/<nome>/<nome>.xml (ex.: worlds/stadiums/events_stadium_517/events_stadium_517.xml)
            if not (len(partes) >= 2 and partes[-1] == partes[-2]):
                continue
            tipo = tipo_primario(self.absoluto(item))
            if tipo in TIPOS_MUNDO:
                out.append({"chave": k, "nome": partes[-1], "asset": "content/" + k[:-4], "tipo": tipo,
                            "pasta": self.pastas[item[0]], "principal": item[0] == 0})
        out.sort(key=lambda m: (not m["principal"], m["nome"]))
        return out


def tipo_primario(caminho, limite=8192):
    try:
        with open(X.longo(caminho), encoding="utf-8-sig", errors="replace") as f:
            cab = f.read(limite)
    except OSError:
        return None
    m = re.search(r'primaryInstance="([^"]+)"', cab)
    if not m:
        return None
    t = re.search(rf'<instance guid="{m.group(1)}" type="([^"]+)"', cab)
    return t.group(1) if t else None


def detectar_exports(base, profundidade=2):
    """Pastas de export do FET dentro de base (até 'profundidade' níveis): têm worlds/stadiums/<x>/<x>.xml."""
    achados = []
    base = os.path.abspath(base)

    def tem_mundo(p):
        for pref in ("", "content"):
            est = os.path.join(p, pref, "worlds", "stadiums")
            if os.path.isdir(est):
                for nome in os.listdir(est):
                    f = os.path.join(est, nome, nome + ".xml")
                    if os.path.isfile(f) and tipo_primario(f) in TIPOS_MUNDO:
                        yield nome

    def visitar(p, nivel):
        try:
            nomes = sorted(os.listdir(p))
        except OSError:
            return
        mundos = sorted(set(tem_mundo(p)))
        if mundos:
            achados.append({"pasta": p, "nome": os.path.basename(p), "mundos": mundos})
            return
        if nivel >= profundidade:
            return
        for n in nomes:
            q = os.path.join(p, n)
            if os.path.isdir(q) and n not in IGNORAR and not n.startswith("."):
                visitar(q, nivel + 1)

    visitar(base, 0)
    return achados
