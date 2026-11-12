"""Arquivos de saída: headmorphpreset FBX (a face de referência exportada pelo FET com as posições novas em todos os
LODs e seções e a UV nova dos olhos), prévia .glb (pele e olhos com textura) e imagens de conferência."""
import json
import os
import struct

import cv2
import numpy as np

from . import REFERENCIA, caminhos
from . import modelo as MD
from . import raster as RS


def gravar_fbx(modelo, X_total, uvs_olhos, caminho, referencia=REFERENCIA):
    caminhos()
    from cena import Cena
    from fbxio import write_fbx
    import geometria as G
    cena = Cena(referencia)
    for s in modelo.secoes:
        m = cena.malha(s["mat"], s["lod"])
        assert m is not None and len(m.V) == s["n"], (s["mat"], s["lod"])
        Xw = X_total[s["off"]:s["off"] + s["n"]]
        geo = cena.objs[m.geom_id]
        Minv = np.linalg.inv(cena.matriz_global(m.model_id) @ cena.matriz_geometrica(m.model_id))
        geo.find("Vertices").props[0].set((Xw @ Minv[:3, :3].T + Minv[:3, 3]).ravel())
        # normais, binormais e tangentes giradas pela mudança de forma
        Rm = G.rotacao_minima(G.normais_vertice(m.V, m.T), G.normais_vertice(Xw, m.T))
        for le_nome, dado in (("LayerElementNormal", "Normals"), ("LayerElementBinormal", "Binormals"),
                              ("LayerElementTangent", "Tangents")):
            for le in geo.findall(le_nome):
                arr = le.find(dado)
                if arr is None or le.find("MappingInformationType").props[0].v not in ("ByVertice", "ByVertex"):
                    continue
                A = np.asarray(arr.props[0].v, float).reshape(-1, 3)
                if len(A) != len(m.V):
                    continue
                A = np.einsum("nij,nj->ni", Rm, A)
                arr.props[0].set((A / np.maximum(np.linalg.norm(A, axis=1), 1e-12)[:, None]).ravel())
        if s["mat"] == "eyes_mat" and s["lod"] in uvs_olhos:
            gravou = False
            for le in geo.findall("LayerElementUV"):
                if le.props[0].v != 0:
                    continue
                arr = le.find("UV")
                if le.find("MappingInformationType").props[0].v in ("ByVertice", "ByVertex") and \
                        le.find("ReferenceInformationType").props[0].v == "Direct" and len(arr.props[0].v) == s["n"] * 2:
                    arr.props[0].set(np.asarray(uvs_olhos[s["lod"]], float).ravel())
                    gravou = True
            if not gravou:
                raise ValueError("a face de referência guarda a UV dos olhos de um jeito inesperado")
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    write_fbx(cena.fbx, caminho)
    return caminho


def conferir_fbx(modelo, X_total, uvs_olhos, caminho):
    """relê o FBX gravado e devolve a maior diferença de posição (m) e de UV dos olhos"""
    caminhos()
    from cena import Cena
    cena = Cena(caminho)
    dp = du = 0.0
    for s in modelo.secoes:
        m = cena.malha(s["mat"], s["lod"])
        dp = max(dp, float(np.abs(m.V - X_total[s["off"]:s["off"] + s["n"]]).max()))
        if s["mat"] == "eyes_mat" and s["lod"] in uvs_olhos:
            du = max(du, float(np.abs(m.uv0 - uvs_olhos[s["lod"]]).max()))
    return dp, du


# ------------------------------------------------------------------------------------------------ prévia .glb
def gravar_glb(modelo, X_total, uvs_olhos, png_pele, png_olho, caminho):
    """cabeça LOD0 (pele + olhos) em glTF binário, Y para cima, com as texturas embutidas"""
    partes, views, accs = [], [], []

    def view(dados, alvo=None):
        off = sum(len(p) for p in partes)
        partes.append(dados + b"\x00" * (-len(dados) % 4))
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(dados)}
        if alvo:
            v["target"] = alvo
        views.append(v)
        return len(views) - 1

    def acc(arr, tipo, comp, alvo, minmax=False):
        a = np.ascontiguousarray(arr)
        d = {"bufferView": view(a.tobytes(), alvo), "componentType": comp, "count": len(a), "type": tipo}
        if minmax:
            d["min"], d["max"] = a.min(0).tolist(), a.max(0).tolist()
        accs.append(d)
        return len(accs) - 1

    h, e = modelo.secao("head_mat"), modelo.secao("eyes_mat")
    centro = X_total[h["off"]:h["off"] + h["n"]].mean(0)
    prims, imagens, texturas, materiais = [], [], [], []
    for nome, s, uv, png in (("pele", h, h["UV"], png_pele), ("olhos", e, uvs_olhos[0], png_olho)):
        V = (X_total[s["off"]:s["off"] + s["n"]] - centro).astype(np.float32)
        N = MD.normais(V.astype(np.float64), s["T"]).astype(np.float32)
        uvg = np.c_[uv[:, 0], 1 - uv[:, 1]].astype(np.float32)
        mat = {"name": nome, "pbrMetallicRoughness": {"metallicFactor": 0, "roughnessFactor": 0.55 if nome == "pele" else 0.25}}
        if png:
            imagens.append({"bufferView": view(png), "mimeType": "image/png"})
            texturas.append({"source": len(imagens) - 1, "sampler": 0})
            mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(texturas) - 1}
        materiais.append(mat)
        prims.append({"attributes": {"POSITION": acc(V, "VEC3", 5126, 34962, True), "NORMAL": acc(N, "VEC3", 5126, 34962),
                                     "TEXCOORD_0": acc(uvg, "VEC2", 5126, 34962)},
                      "indices": acc(s["T"].astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": len(materiais) - 1})
    bin_ = b"".join(partes)
    doc = {"asset": {"version": "2.0", "generator": "BRFP Super Tool - Criador de Faces"}, "scene": 0,
           "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "cabeca"}],
           "meshes": [{"primitives": prims}], "materials": materiais, "accessors": accs, "bufferViews": views,
           "buffers": [{"byteLength": len(bin_)}],
           "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]}
    if imagens:
        doc["images"], doc["textures"] = imagens, texturas
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(caminho, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bin_)
    return caminho


# ------------------------------------------------------------------------------------------------ imagens
class Renderizador:
    """cabeça LOD0 (pele com textura + olhos com a textura do jogo) para as imagens de conferência"""

    def __init__(self, modelo):
        self.m = modelo
        h, e = modelo.secao("head_mat"), modelo.secao("eyes_mat")
        self.h, self.e = h, e
        self.nh = h["n"]
        self.T = np.r_[h["T"], e["T"] + h["n"]]
        self.nth = len(h["T"])
        olho = cv2.imread(MD.OLHO_PNG, cv2.IMREAD_COLOR)
        self.tex_olho = None if olho is None else olho[:, :, ::-1].astype(np.float32) / 255.0

    def render(self, X_total, cam, W, H, textura=None, uv_olhos=None, fundo=(0.16, 0.17, 0.2), cor_pele=(0.62, 0.62, 0.62),
               ambiente=0.55):
        h, e = self.h, self.e
        X = np.r_[X_total[h["off"]:h["off"] + h["n"]], X_total[e["off"]:e["off"] + e["n"]]]
        uv, z = cam.projetar(X)
        buf, bary = RS.rasterizar(uv, z, self.T, W, H)
        Ni = RS.interpolar(buf, bary, self.T, MD.normais(X, self.T))
        Ni /= np.maximum(np.linalg.norm(Ni, axis=-1), 1e-9)[..., None]
        L = cam.R.T @ (np.array([0.3, 0.4, 1.0]) / np.linalg.norm([0.3, 0.4, 1.0]))
        lamb = np.clip((Ni * L).sum(-1), 0, 1)
        m = buf >= 0
        olho = m & (buf >= self.nth)
        pele = m & ~olho
        img = np.zeros((H, W, 3))
        img[:] = fundo
        if textura is not None:
            cor = RS.amostrar(textura, RS.interpolar(buf, bary, self.T, np.r_[h["UV"], np.zeros((e["n"], 2))]))
        else:
            cor = np.broadcast_to(np.asarray(cor_pele, float), (H, W, 3))
        img[pele] = cor[pele] * (ambiente + (1 - ambiente) * lamb[pele])[:, None]
        if olho.any():
            if self.tex_olho is not None and uv_olhos is not None:
                co = RS.amostrar(self.tex_olho, RS.interpolar(buf, bary, self.T, np.r_[np.zeros((self.nh, 2)), uv_olhos]),
                                 repetir=True)
                img[olho] = co[olho] * (0.75 + 0.25 * lamb[olho])[:, None]
            else:
                img[olho] = np.array([0.9, 0.9, 0.88]) * (0.7 + 0.3 * lamb[olho])[:, None]
        return np.clip(img, 0, 1), buf


def _lado_a_lado(imgs, altura):
    out = []
    for im in imgs:
        hh, ww = im.shape[:2]
        out.append(cv2.resize(im, (max(1, int(ww * altura / hh)), altura), interpolation=cv2.INTER_AREA))
    return np.concatenate(out, 1)


def salvar_png(caminho, img):
    ok, buf = cv2.imencode(".png", (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)[:, :, ::-1])
    if not ok:
        raise OSError("não consegui gerar o PNG")
    with open(caminho, "wb") as f:           # o imwrite do OpenCV não aceita acentos no caminho
        f.write(buf.tobytes())
    return buf.tobytes()


def previa_fotos(modelo, X, cams, fotos, tex, uv_olhos, caminho, altura=380):
    """por foto: a foto, a cabeça na mesma pose e as duas sobrepostas"""
    r = Renderizador(modelo)
    linhas = []
    for img, cam in zip(fotos, cams):
        H, W = img.shape[:2]
        ren, buf = r.render(X, cam, W, H, tex, uv_olhos, ambiente=0.8)
        sob = img.copy()
        sob[buf >= 0] = 0.5 * img[buf >= 0] + 0.5 * ren[buf >= 0]
        linhas.append(_lado_a_lado([img, ren, sob], altura))
    larg = max(l.shape[1] for l in linhas)
    salvar_png(caminho, np.concatenate([np.pad(l, ((0, 0), (0, larg - l.shape[1]), (0, 0))) for l in linhas], 0))


def previa_3d(modelo, X, tex, uv_olhos, caminho, lado=460):
    r = Renderizador(modelo)
    Xh = X[modelo.fatia("head_mat")]
    c0 = Xh.mean(0)
    cima, baixo = [], []
    for yaw in (0, 35, 80):
        cam = RS.Camera.enquadrar(Xh, RS.rot(yaw, 0), lado, lado, k=0.6, c0=c0)
        cima.append(r.render(X, cam, lado, lado, tex, uv_olhos, ambiente=0.75)[0])
        baixo.append(r.render(X, cam, lado, lado, None, uv_olhos)[0])
    salvar_png(caminho, np.concatenate([np.concatenate(cima, 1), np.concatenate(baixo, 1)], 0))
