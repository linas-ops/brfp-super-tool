"""Mesh zero: troca a geometria de um FBX do FET por um triângulo minúsculo em cada seção.

Para objetos removidos do jogo: a malha continua existindo (o FET importa sem reclamar, os materiais e o MVDB
continuam ligados), mas quase não ocupa espaço no estádio. Mantém tudo o que o FET confere no import: quantidade
e ordem das seções (Model:Mesh), LODs, nomes, camadas de UV/cor/normal e materiais. Só os arrays de cada
Geometry encolhem para 3 vértices.
"""
import os
import sys

# leitor/gravador de FBX binário do Conversor de Faces (o mesmo que os Corpos e os Kits usam)
_FACES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "faces", "motor")

LADO = 0.001        # triângulo de 1 mm na origem da malha
# componentes por item de cada array de camada (o que não está aqui fica com 1)
COMPONENTES = {"Normals": 3, "Binormals": 3, "Tangents": 3, "UV": 2, "Colors": 4}


def _fbxio():
    if _FACES not in sys.path:
        sys.path.append(_FACES)
    try:
        import fbxio
    except ImportError as ex:
        raise RuntimeError("Leitor de FBX não encontrado (ferramentas/faces/motor/fbxio.py do BRFP Super Tool).") from ex
    return fbxio


def _texto(no, nome):
    c = no.find(nome)
    return c.props[0].v if c is not None and c.props else ""


def _zerar_camada(camada):
    """Uma LayerElement*: dados viram 3 itens (por vértice / canto / aresta) ou 1 (por polígono)."""
    mapa = _texto(camada, "MappingInformationType")
    ref = _texto(camada, "ReferenceInformationType")
    itens = {"ByVertice": 3, "ByVertex": 3, "ByControlPoint": 3, "ByPolygonVertex": 3, "ByEdge": 3, "ByPolygon": 1}.get(mapa)
    if itens is None:            # AllSame / NoMappingInformation: não depende da geometria
        return
    for c in camada.children:
        if not c.props or c.props[0].t not in "dfil":
            continue
        dados = c.props[0].v
        if c.name.endswith("Index"):
            c.props[0].set([0] * itens)
            continue
        comp = COMPONENTES.get(c.name, 1)
        primeiro = list(dados[:comp]) if len(dados) >= comp else [0] * comp
        if ref == "IndexToDirect" and camada.find(c.name + "Index") is not None:
            c.props[0].set(primeiro)                 # um item só; os índices apontam todos para ele
        else:
            c.props[0].set(primeiro * itens)


def _zerar_geometria(geo):
    for c in geo.children:
        if c.name == "Vertices":
            c.props[0].set([0, 0, 0, LADO, 0, 0, 0, 0, LADO])
        elif c.name == "PolygonVertexIndex":
            c.props[0].set([0, 1, -3])
        elif c.name == "Edges":
            c.props[0].set([0, 1, 2])
        elif c.name.startswith("LayerElement"):
            _zerar_camada(c)


def _zerar_partes(f, obj):
    """As malhas do FET têm uma "parte" (osso) por pedaço, com skin: cada Skin continua com todos os clusters (o
    FET confere a quantidade de partes), mas só o primeiro fica com os 3 vértices; os outros ficam sem vértices,
    como o próprio FBX SDK grava cluster vazio (sem Indexes/Weights)."""
    con = f.root.find("Connections")
    pai = {}
    for c in con.children if con is not None else []:
        if len(c.props) >= 3 and c.props[0].v == "OO":
            pai.setdefault(c.props[1].v, c.props[2].v)
    vistos = set()
    for d in obj.findall("Deformer"):
        if len(d.props) < 3 or d.props[2].v != "Cluster":
            continue
        skin = pai.get(d.props[0].v)
        if skin not in vistos:
            vistos.add(skin)
            for nome, valores in (("Indexes", [0, 1, 2]), ("Weights", [1.0, 1.0, 1.0])):
                c = d.find(nome)
                if c is not None:
                    c.props[0].set(valores)
        else:
            d.children = [c for c in d.children if c.name not in ("Indexes", "Weights")]


def zerar(origem, destino=None):
    """Grava o FBX "zerado" em destino (padrão: por cima da origem). Retorna (bytes antes, bytes depois)."""
    fbxio = _fbxio()
    f = fbxio.read_fbx(origem)
    obj = f.root.find("Objects")
    if obj is None:
        raise ValueError("FBX sem Objects")
    geos = obj.findall("Geometry")
    if not geos:
        raise ValueError("FBX sem geometria")
    for g in geos:
        _zerar_geometria(g)
    _zerar_partes(f, obj)
    antes = os.path.getsize(origem)
    destino = destino or origem
    tmp = destino + ".tmp"
    fbxio.write_fbx(f, tmp)
    os.replace(tmp, destino)
    return antes, os.path.getsize(destino)
