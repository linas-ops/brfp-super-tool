"""Fontes do tema da interface do FC (data/ui/themes/FIFA.xml + data/ui/fonts).

Como o jogo acha a fonte de um texto do placar:
- o código do placar faz new TextFormat(StyleManager.FONT_NAME_X, tamanho, cor);
- FONT_NAME_X é uma "família" do tema: <font_family NAME="FONT_NAME_X" VALUE="Face" .../> no FIFA.xml;
- "Face" é o nome do arquivo data/ui/fonts/Face.ttf (o nome interno do TTF não importa — o pack do LTA usa
  arquivos como Brasilerao-A.ttf com fontes "Assemblage W00");
- data/ui/fonts/font_extents.txt tem um bloco de medidas por face; o LTA copia o mesmo bloco para todas as fontes
  novas (o do EuropaNuova) e algumas nem têm bloco.

O editor grava FIFA.xml e font_extents.txt na pasta de saída montados a partir da versão em uso (mods antes do
jogo) mais as famílias definidas pelo usuário, guardadas em projetos/tema_<saída>.json para poder refazer quando a
base muda (ex.: o pack do LTA adicionado como fonte depois).
"""
import hashlib
import json
import os
import re
import shutil
import time

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(AQUI, "projetos")
XML = "data/ui/themes/FIFA.xml"
EXTENTS = "data/ui/fonts/font_extents.txt"
PASTA_FONTES = "data/ui/fonts/"
MODELO_EXTENTS = ("EuropaNuovaRegular", "EABold")

RX_FAMILIA = re.compile(r'<font_family\s+NAME="([^"]+)"\s+VALUE="([^"]*)"[^>]*/>')
RX_BLOCO = re.compile(r'\{\s*"([^"]+)"\s*((?:\[[^\]]*\]\s*)+)\}')


class ErroTema(Exception):
    pass


def limpar_face(nome):
    return re.sub(r"[^A-Za-z0-9_\-]", "", nome or "")[:60]


def limpar_chave(nome):
    k = re.sub(r"[^A-Z0-9_]", "", (nome or "").upper().replace(" ", "_").replace("-", "_"))
    if not k:
        return ""
    return k if k.startswith("FONT_NAME_") else "FONT_NAME_" + k


def _texto(dados):
    if dados.startswith(b"\xef\xbb\xbf"):
        return dados[3:].decode("utf-8", "replace"), b"\xef\xbb\xbf"
    return dados.decode("utf-8", "replace"), b""


def familias(xml):
    return RX_FAMILIA.findall(xml)


def definir_familia(xml, chave, face):
    """Troca o VALUE de uma família ou cria a linha no fim do <font_family_set>."""
    rx = re.compile(r'(<font_family\s+NAME="%s"\s+VALUE=")([^"]*)(")' % re.escape(chave))
    if rx.search(xml):
        return rx.sub(lambda m: m.group(1) + face + m.group(3), xml, count=1)
    fim = xml.find("</font_family_set>")
    if fim < 0:
        raise ErroTema("O FIFA.xml não tem <font_family_set>.")
    nl = "\r\n" if "\r\n" in xml else "\n"
    ini_linha = xml.rfind("\n", 0, fim) + 1
    recuo = re.match(r"[ \t]*", xml[ini_linha:fim]).group(0) or "    "
    linha = f'{recuo}  <font_family NAME="{chave}" VALUE="{face}" CACHE="TRUE"/> <!-- Editor de Placares -->{nl}'
    return xml[:ini_linha] + linha + xml[ini_linha:]


RX_VALOR = re.compile(r'<(alpha|color|font_size)\s+NAME="([A-Z0-9_]+)"\s+VALUE="([^"]*)"')


def valores(xml):
    """{NOME: número} das transparências, cores e tamanhos de letra do tema (o que StyleManager.ALPHA_FULL,
    COLOR_..., FONT_SIZE_... valem no jogo). As famílias de fonte ficam de fora: o editor trata pelo nome."""
    brutos = {n: v.strip() for _t, n, v in RX_VALOR.findall(xml)}
    out = {}

    def resolver(n, nivel=0):
        if n in out:
            return out[n]
        v = brutos.get(n)
        if v is None or nivel > 20:
            return None
        if v.startswith("@"):
            r = resolver(v[1:], nivel + 1)
        else:
            try:
                r = int(v, 16) if v.lower().startswith("0x") else (float(v) if "." in v else int(v))
            except ValueError:
                r = None
        if r is not None:
            out[n] = r
        return r
    for n in brutos:
        resolver(n)
    return out


def faces_extents(ext):
    return [n for n, _ in RX_BLOCO.findall(ext)]


def acrescentar_extents(ext, face):
    if face in faces_extents(ext):
        return ext
    blocos = dict(RX_BLOCO.findall(ext))
    modelo = next((blocos[m] for m in MODELO_EXTENTS if m in blocos), None) or (next(iter(blocos.values())) if blocos else None)
    if modelo is None:
        raise ErroTema("O font_extents.txt não tem nenhum bloco para copiar.")
    nl = "\r\n" if "\r\n" in ext else "\n"
    corpo = modelo.rstrip()
    novo = "{" + nl + '\t"' + face + '"' + nl + "\t" + corpo + nl + "}" + nl
    if ext and not ext.endswith(("\n", "\r")):
        ext += nl
    return ext + novo


# ------------------------------------------------------------------ projeto do tema (por pasta de saída)

def _arq_projeto(saida):
    h = hashlib.sha1(os.path.abspath(saida).lower().encode("utf-8")).hexdigest()[:16]
    return os.path.join(PASTA, f"tema_{h}.json")


def carregar(saida):
    try:
        with open(_arq_projeto(saida), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"saida": os.path.abspath(saida), "familias": [], "faces_copiadas": []}


def _gravar_projeto(saida, proj):
    os.makedirs(PASTA, exist_ok=True)
    arq = _arq_projeto(saida)
    proj["quando"] = time.strftime("%d/%m/%Y %H:%M")
    with open(arq + ".tmp", "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=1)
    os.replace(arq + ".tmp", arq)


def _caminho(saida, rel):
    return os.path.join(os.path.abspath(saida), *rel.split("/"))


def _sha(d):
    return hashlib.sha1(d).hexdigest()[:16] if d is not None else None


def base_de(saida, ler_efetivo, rel, proj):
    """(origem, bytes) da versão usada como base: cópia de segurança de um arquivo que já estava na saída
    (não feito pelo editor) ou a versão em uso nas fontes (mods antes do jogo)."""
    bk = (proj.get("backups") or {}).get(rel)
    if bk and os.path.isfile(bk):
        with open(bk, "rb") as f:
            return "arquivo que já estava na saída", f.read()
    return ler_efetivo(rel)


def regenerar(saida, ler_efetivo, proj=None):
    """Grava FIFA.xml e font_extents.txt na saída: base + famílias do usuário. Sem famílias, apaga os dois
    (ou devolve os que estavam lá antes)."""
    proj = proj or carregar(saida)
    proj.setdefault("backups", {})
    alvo_xml, alvo_ext = _caminho(saida, XML), _caminho(saida, EXTENTS)
    # arquivo que já estava na saída e não foi o editor que gravou: guarda uma cópia para usar como base
    for rel, alvo in ((XML, alvo_xml), (EXTENTS, alvo_ext)):
        if os.path.isfile(alvo) and rel not in proj["backups"] and not proj.get("gerado", {}).get(rel):
            os.makedirs(os.path.join(PASTA, "backup"), exist_ok=True)
            bk = os.path.join(PASTA, "backup", "tema_" + hashlib.sha1(alvo.lower().encode()).hexdigest()[:12] + "_" + os.path.basename(alvo))
            shutil.copy2(alvo, bk)
            proj["backups"][rel] = bk
    if not proj.get("familias"):
        for rel, alvo in ((XML, alvo_xml), (EXTENTS, alvo_ext)):
            bk = proj["backups"].get(rel)
            if bk and os.path.isfile(bk):
                shutil.copy2(bk, alvo)
            elif os.path.isfile(alvo) and proj.get("gerado", {}).get(rel):
                os.remove(alvo)
        proj["gerado"] = {}
        proj["base"] = {}
        _gravar_projeto(saida, proj)
        return proj
    origem_xml, dados_xml = base_de(saida, ler_efetivo, XML, proj)
    if dados_xml is None:
        raise ErroTema("Não achei o FIFA.xml (nem no jogo nem nos mods). Configure a pasta do FC 26.")
    xml, bom = _texto(dados_xml)
    for fam in proj["familias"]:
        xml = definir_familia(xml, fam["chave"], fam["face"])
    origem_ext, dados_ext = base_de(saida, ler_efetivo, EXTENTS, proj)
    ext, bom_e = _texto(dados_ext) if dados_ext is not None else ("", b"")
    for fam in proj["familias"]:
        ext = acrescentar_extents(ext, fam["face"])
    for rel, alvo, txt, b in ((XML, alvo_xml, xml, bom), (EXTENTS, alvo_ext, ext, bom_e)):
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        with open(alvo + ".tmp", "wb") as f:
            f.write(b + txt.encode("utf-8"))
        os.replace(alvo + ".tmp", alvo)
    proj["gerado"] = {XML: True, EXTENTS: True}
    proj["base"] = {"xml": origem_xml, "xml_sha": _sha(dados_xml), "ext": origem_ext}
    _gravar_projeto(saida, proj)
    return proj


def definir(saida, ler_efetivo, chave, face, ttf=None, nome_ttf=None):
    """Liga a família 'chave' à face 'face'; com 'ttf' (bytes), grava data/ui/fonts/<face>.ttf na saída."""
    chave, face = limpar_chave(chave), limpar_face(face)
    if not chave or not face:
        raise ErroTema("Nome de família ou de fonte inválido.")
    proj = carregar(saida)
    if ttf is not None:
        ext = os.path.splitext(nome_ttf or "")[1].lower()
        ext = ext if ext in (".ttf", ".otf") else ".ttf"
        destino = _caminho(saida, PASTA_FONTES + face + ext)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino + ".tmp", "wb") as f:
            f.write(ttf)
        os.replace(destino + ".tmp", destino)
        copiadas = set(proj.get("faces_copiadas") or [])
        copiadas.add(face + ext)
        proj["faces_copiadas"] = sorted(copiadas)
    fams = [f for f in proj.get("familias", []) if f["chave"] != chave]
    fams.append({"chave": chave, "face": face})
    proj["familias"] = fams
    return regenerar(saida, ler_efetivo, proj)


def remover(saida, ler_efetivo, chave):
    proj = carregar(saida)
    proj["familias"] = [f for f in proj.get("familias", []) if f["chave"] != chave]
    usadas = {f["face"].lower() for f in proj["familias"]}
    restantes = []
    for arq in proj.get("faces_copiadas") or []:
        if os.path.splitext(arq)[0].lower() in usadas:
            restantes.append(arq)
            continue
        alvo = _caminho(saida, PASTA_FONTES + arq)
        if os.path.isfile(alvo):
            os.remove(alvo)
    proj["faces_copiadas"] = restantes
    return regenerar(saida, ler_efetivo, proj)


def validar_ttf(dados):
    if len(dados) < 12 or dados[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise ErroTema("Esse arquivo não é uma fonte TrueType/OpenType (.ttf/.otf).")
    if len(dados) > 40 << 20:
        raise ErroTema("Fonte grande demais.")
