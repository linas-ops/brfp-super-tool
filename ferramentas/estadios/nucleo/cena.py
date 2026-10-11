"""Monta a cena de um mundo de estádio a partir do export do FET.

Hierarquia que o jogo usa e que a cena reproduz:
  mundo (DetachedSubWorldData) ─┬─ SubWorldReferenceObjectData  -> sub-mundo (outro XML, MVDB próprio)
                                ├─ WorldPartReferenceObjectData -> world part (XML com objetos)
                                ├─ LayerReferenceObjectData     -> layer (XML com objetos)
                                └─ StaticModelGroupEntityData   -> malhas com N cópias (InstanceTransforms)
  objeto (ObjectReferenceObjectData / SpatialPrefabReferenceObjectData) -> blueprint
      ObjectBlueprint        -> StaticModelEntityData -> malha (FBX de mesmo nome)
      SpatialPrefabBlueprint -> mais objetos (recursivo)
Texturas e shaders de cada seção vêm do MeshVariationDb_Win32 do sub-mundo onde a malha está.
"""
import os
import re
from collections import Counter, defaultdict

from . import estadios_txt
from . import xmlfet as X
from .indice import chave

# sub-mundos / layers sem geometria de estádio (pessoas, câmeras, coreografia, efeitos, lógica)
NAO_VISUAIS = ("choreo", "slc", "walkers", "confetti", "effects", "broadcasting", "debug", "chant", "crowd",
               "cine_interface", "communication", "stateandstreaming", "cinematic_schematic", "rendering_schematic")
BP_NAO_VISUAIS = ("/logic/", "/choreo", "/cinematic", "/sound", "/audio", "/effects/", "/fx/", "/crowd/", "/slc/",
                  "/presentation/", "/camera/", "/cameras/", "microphone", "/character")
TIPOS_REF_GRUPO = {"SubWorldReferenceObjectData": "subworld", "WorldPartReferenceObjectData": "worldpart",
                   "LayerReferenceObjectData": "layer"}
TIPOS_OBJETO = ("ObjectReferenceObjectData", "SpatialPrefabReferenceObjectData")
TIPOS_LUZ = {"PbrSpotLightEntityData": "spot", "PbrSphereLightEntityData": "esfera", "PbrTubeLightEntityData": "tubo",
             "PbrRectangularLightEntityData": "retangulo", "SpotLightEntityData": "spot", "PointLightEntityData": "esfera"}
SOMBRA = ("_shadow", "_zonly")
MAX_PROF = 16
# pessoas da lateral (slc_*) e assentos do banco de reservas (choreo_seats): viram marcadores editáveis
MARCADORES = {"slc_ballboy": "Gandula", "slc_photographer": "Fotógrafo", "slc_police": "Policial", "slc_steward": "Segurança",
              "slc_camera_handheld": "Cinegrafista (na mão)", "slc_camera_sitting": "Cinegrafista (sentado)",
              "slc_camera_standing": "Cinegrafista (em pé)", "slc_medicalofficer": "Médico", "slc_generic": "Staff",
              "slc_tournamentofficial": "Oficial", "slc_managerhome": "Técnico (casa)", "slc_manageraway": "Técnico (visitante)",
              "slc_assistantmanagerhome": "Auxiliar (casa)", "slc_assistantmanageraway": "Auxiliar (visitante)",
              "choreo_seats": "Banco de reservas"}
GRUPOS_MARCADORES = {"slc": "Pessoas da lateral", "choreo": "Banco de reservas (coreografia)"}


def raiz_trabalho():
    """Pasta de trabalho (a do BRFP Super Tool, ou a pasta acima do editor quando ele roda sozinho)."""
    r = os.environ.get("BRFP_RAIZ")
    if r and os.path.isdir(r):
        return r
    editor = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pai = os.path.dirname(editor)
    if os.path.basename(pai).lower() == "ferramentas":      # BRFP Super Tool/ferramentas/estadios
        return os.path.dirname(os.path.dirname(pai))
    return pai


def nao_visual(nome):
    n = nome.lower().split("/")[-1]
    return n.startswith(NAO_VISUAIS) or n.endswith("_schematic")


class Cena:
    def __init__(self, indice):
        self.ix = indice
        self.nos = []
        self.malhas = {}
        self.mvdbs = {}
        self.texturas = {}
        self.ligados = set()
        self.avisos = []
        self._xml = {}
        self.uso_bp = Counter()
        self.nuvens = []

    # ------------------------------------------------------------------ util
    def xml(self, caminho):
        st = os.stat(X.longo(caminho))
        c = self._xml.get(caminho)
        if c and c[0] == st.st_mtime:
            return c[1]
        raiz = X.analisar(X.ler(caminho))
        self._xml[caminho] = (st.st_mtime, raiz)
        return raiz

    def novo_no(self, **k):
        k["id"] = len(self.nos)
        self.nos.append(k)
        return k

    # ------------------------------------------------------------------ pré-passe
    def pre_passe(self, pasta_mundo):
        """Ligações de lógica (Property/Link/Event connections) e nuvens de torcida da pasta do mundo."""
        rx_arr = re.compile(r'<array name="(?:PropertyConnections|LinkConnections|EventConnections)"[^>]*>(.*?)</array>', re.S)
        rx_st = re.compile(r'<field name="(?:Source|Target)" ref="([^"]+)"')
        rx_nome = re.compile(r'<field name="Name">([^<]+)</field>')
        rx_nuvem = re.compile(r'name="PointCloudAsset" ref="([^"]+)"')
        for dp, _, ns in os.walk(pasta_mundo):
            for n in ns:
                if not n.endswith(".xml") or n.startswith("MeshVariationDb"):
                    continue
                try:
                    texto = X.ler(os.path.join(dp, n))
                except OSError:
                    continue
                if "Connection" in texto:
                    m = rx_nome.search(texto)
                    proprio = m.group(1).lower() if m else ""
                    for arr in rx_arr.finditer(texto):
                        for ref in rx_st.findall(arr.group(1)):
                            if X.BS in ref:
                                self.ligados.add((X.caminho_asset(ref).lower(), X.guid_ref(ref)))
                            else:
                                self.ligados.add((proprio, ref))
                for ref in rx_nuvem.findall(texto):
                    a = X.caminho_asset(ref)
                    if a and a not in [c["asset"] for c in self.nuvens]:
                        item = self.ix.achar(a, ".xml")
                        self.nuvens.append({"asset": a, "arq": self.ix.id_arquivo(item) if item else None,
                                            "nome": X.curto(ref)})

    # ------------------------------------------------------------------ mundo
    def carregar(self, mundo_asset):
        caminho = self.ix.arquivo(mundo_asset, ".xml")
        if not caminho:
            raise FileNotFoundError(f"XML do mundo não encontrado: {mundo_asset}")
        self.mundo_asset = mundo_asset
        self.pre_passe(os.path.dirname(caminho))
        item = self.ix.achar(mundo_asset, ".xml")
        raiz = self.novo_no(pai=-1, tipo="mundo", nome=X.curto(mundo_asset), local=X.IDENT, alvo=None, jogo=None,
                            arq=self.ix.id_arquivo(item), asset=mundo_asset)
        self.visitar_arquivo(mundo_asset, raiz["id"], mundo_asset + "/MeshVariationDb_Win32", [mundo_asset.lower()])
        self.podar()
        self.resolver_malhas()
        return self

    def visitar_arquivo(self, asset, pai, mvdb, pilha):
        item = self.ix.achar(asset, ".xml")
        if not item:
            self.avisos.append(f"Não exportado: {asset}")
            self.nos[pai]["faltando"] = "xml"
            return
        arq = self.ix.id_arquivo(item)
        raiz = self.xml(self.ix.absoluto(item))
        insts = {i.get("guid"): i for i in raiz.findall("instance")}
        prim = insts.get(raiz.get("primaryInstance"))
        ordem = self.objetos_do_primario(prim, insts) if prim is not None else list(insts.values())
        for el in ordem:
            tipo = el.get("type")
            if tipo in TIPOS_REF_GRUPO:
                self.referencia_grupo(el, tipo, arq, asset, pai, mvdb, pilha)
            elif tipo in TIPOS_OBJETO:
                self.colocacao(el, arq, asset, pai, mvdb, pilha, 1)
            elif tipo == "StaticModelGroupEntityData":
                self.grupo_estatico(el, arq, pai, mvdb)
            elif tipo in TIPOS_LUZ:
                self.luz(el, tipo, arq, pai)

    @staticmethod
    def objetos_do_primario(prim, insts):
        arr = prim.find("array[@name='Objects']")
        vistos, out = set(), []
        if arr is not None:
            for it in arr:
                g = it.get("ref")
                if g in insts and g not in vistos:
                    vistos.add(g)
                    out.append(insts[g])
        # objetos que não estão na lista Objects (sub-mundos listam referências fora dela)
        for g, el in insts.items():
            t = el.get("type")
            if g not in vistos and (t in TIPOS_REF_GRUPO or t in TIPOS_OBJETO or t in TIPOS_LUZ
                                    or t == "StaticModelGroupEntityData"):
                vistos.add(g)
                out.append(el)
        return out

    def referencia_grupo(self, el, tipo, arq, asset_arq, pai, mvdb, pilha):
        if tipo == "SubWorldReferenceObjectData":
            alvo_asset = el.findtext("field[@name='BundleName']") or ""
        else:
            alvo_asset = X.caminho_asset(el.find("field[@name='Blueprint']").get("ref"))
        curto = alvo_asset.lower().split("/")[-1]
        if curto in GRUPOS_MARCADORES or curto in MARCADORES:
            return self.referencia_marcadores(el, tipo, arq, alvo_asset, pai, mvdb, pilha)
        if not alvo_asset or alvo_asset == "null" or nao_visual(alvo_asset) or alvo_asset.lower() in pilha:
            return
        tr = el.find("field[@name='BlueprintTransform']/complex")
        no = self.novo_no(pai=pai, tipo=TIPOS_REF_GRUPO[tipo], nome=X.curto(alvo_asset), asset=alvo_asset,
                          local=X.transformacao(tr) if tr is not None else X.IDENT,
                          alvo={"arq": arq, "guid": el.get("guid"), "campo": "BlueprintTransform"},
                          jogo={"excluido": el.findtext("field[@name='Excluded']") == "true"},
                          ligado=(asset_arq.lower(), el.get("guid")) in self.ligados)
        sub_mvdb = alvo_asset + "/MeshVariationDb_Win32" if tipo == "SubWorldReferenceObjectData" else mvdb
        item = self.ix.achar(alvo_asset, ".xml")
        if item:
            no["arq"] = self.ix.id_arquivo(item)
        no["mvdb"] = sub_mvdb
        self.visitar_arquivo(alvo_asset, no["id"], sub_mvdb, pilha + [alvo_asset.lower()])

    def referencia_marcadores(self, el, tipo, arq, alvo_asset, pai, mvdb, pilha):
        """Sub-mundo slc/choreo e seus layers slc_* / choreo_seats: cada colocação vira um marcador."""
        curto = alvo_asset.lower().split("/")[-1]
        if alvo_asset.lower() in pilha:
            return
        tr = el.find("field[@name='BlueprintTransform']/complex")
        no = self.novo_no(pai=pai, tipo=TIPOS_REF_GRUPO[tipo], nome=GRUPOS_MARCADORES.get(curto) or MARCADORES[curto],
                          asset=alvo_asset, local=X.transformacao(tr) if tr is not None else X.IDENT,
                          alvo={"arq": arq, "guid": el.get("guid"), "campo": "BlueprintTransform"},
                          jogo={"excluido": el.findtext("field[@name='Excluded']") == "true"}, grupo_marcadores=True)
        item = self.ix.achar(alvo_asset, ".xml")
        if not item:
            return
        no["arq"] = self.ix.id_arquivo(item)
        raiz = self.xml(self.ix.absoluto(item))
        insts = {i.get("guid"): i for i in raiz.findall("instance")}
        prim = insts.get(raiz.get("primaryInstance"))
        for sub in (self.objetos_do_primario(prim, insts) if prim is not None else []):
            st = sub.get("type")
            if st in TIPOS_REF_GRUPO:
                if st == "SubWorldReferenceObjectData":
                    a2 = sub.findtext("field[@name='BundleName']") or ""
                else:
                    bp = sub.find("field[@name='Blueprint']")
                    a2 = X.caminho_asset(bp.get("ref", "")) if bp is not None else ""
                if a2 and a2.lower().split("/")[-1] in MARCADORES:
                    self.referencia_marcadores(sub, st, no["arq"], a2, no["id"], mvdb, pilha + [alvo_asset.lower()])
        if curto not in MARCADORES:
            return
        rotulo = MARCADORES[curto]
        n = 0
        for g, sub in insts.items():
            if sub.get("type") not in ("ReferenceObjectData", "SpatialPrefabReferenceObjectData", "ObjectReferenceObjectData"):
                continue
            t2 = sub.find("field[@name='BlueprintTransform']/complex")
            if t2 is None:
                continue
            n += 1
            self.novo_no(pai=no["id"], tipo="marcador", categoria=curto, nome=f"{rotulo} #{n}", local=X.transformacao(t2),
                         alvo={"arq": no["arq"], "guid": g, "campo": "BlueprintTransform"},
                         jogo={"excluido": sub.findtext("field[@name='Excluded']") == "true"})

    def colocacao(self, el, arq, asset_arq, pai, mvdb, pilha, prof):
        bp_el = el.find("field[@name='Blueprint']")
        bp = X.caminho_asset(bp_el.get("ref")) if bp_el is not None else ""
        tr = el.find("field[@name='BlueprintTransform']/complex")
        if not bp or bp == "null" or tr is None:
            return
        no = self.novo_no(pai=pai, tipo="ref", nome=X.curto(bp), bp=bp, local=X.transformacao(tr),
                          alvo={"arq": arq, "guid": el.get("guid"), "campo": "BlueprintTransform"},
                          jogo={"excluido": el.findtext("field[@name='Excluded']") == "true"},
                          ligado=(asset_arq.lower(), el.get("guid")) in self.ligados, mvdb=mvdb, malhas=[])
        if prof > 1:
            no["aninhado"] = True
        item = self.ix.achar(bp, ".xml")
        if not item:
            no["faltando"] = "blueprint"
            return
        if bp.lower() in pilha or prof > MAX_PROF:
            return
        self.uso_bp[bp.lower()] += 1
        bp_arq = self.ix.id_arquivo(item)
        no["bp_arq"] = bp_arq
        raiz = self.xml(self.ix.absoluto(item))
        insts = {i.get("guid"): i for i in raiz.findall("instance")}
        prim = insts.get(raiz.get("primaryInstance"))
        ptipo = prim.get("type") if prim is not None else ""
        if ptipo == "ObjectBlueprint":
            obj = insts.get((prim.find("field[@name='Object']").get("ref") or "").split(X.BS)[-1])
            if obj is not None and obj.get("type") == "StaticModelEntityData":
                self.peca_estatica(no, obj)
        elif ptipo in ("SpatialPrefabBlueprint", "PrefabBlueprint"):
            no["tipo"] = "prefab"
            for sub in self.objetos_do_primario(prim, insts):
                st = sub.get("type")
                if st in TIPOS_OBJETO:
                    self.colocacao(sub, bp_arq, bp, no["id"], mvdb, pilha + [bp.lower()], prof + 1)
                elif st == "StaticModelEntityData":
                    self.peca_estatica(no, sub)
                elif st in TIPOS_LUZ:
                    self.luz(sub, st, bp_arq, no["id"], aninhado=True)
        else:
            no["tipo_bp"] = ptipo

    def luz(self, el, tipo, arq, pai, aninhado=False):
        tr = el.find("field[@name='Transform']/complex")
        if tr is None:
            return
        cor = el.find("field[@name='Color']/complex")

        def num(nome, padrao=0.0):
            v = el.findtext(f"field[@name='{nome}']")
            try:
                return float(v)
            except (TypeError, ValueError):
                return padrao
        tipo_luz = TIPOS_LUZ[tipo]
        self.n_luzes = getattr(self, "n_luzes", 0) + 1
        no = self.novo_no(pai=pai, tipo="luz", nome=f"{tipo_luz.capitalize()} #{self.n_luzes}", local=X.transformacao(tr),
                          alvo={"arq": arq, "guid": el.get("guid"), "campo": "Transform"},
                          jogo={"habilitada": el.findtext("field[@name='Enabled']") != "false"},
                          luz={"tipo": tipo_luz, "cor": X.vec(cor) if cor is not None else [1, 1, 1],
                               "intensidade": num("Intensity", 1), "raio": num("AttenuationRadius", 10),
                               "angulo": num("OuterAngle", 0), "largura": num("Width", 0), "altura": num("Height", 0),
                               "comprimento": num("Length", 0)})
        if aninhado:
            no["aninhado"] = True

    def peca_estatica(self, no, obj):
        mesh = obj.find("field[@name='Mesh']")
        if mesh is None or not mesh.get("ref") or mesh.get("ref") == "null":
            return
        m = X.caminho_asset(mesh.get("ref"))
        tr = obj.find("field[@name='Transform']/complex")
        peca = {"m": chave(m), "t": X.transformacao(tr) if tr is not None else X.IDENT}
        if obj.findtext("field[@name='Visible']") == "false":
            peca["oculta"] = True
        caixas = obj.find("array[@name='PartBoundingBoxes']")
        if caixas is not None and len(caixas):
            lo, hi = [1e30] * 3, [-1e30] * 3
            for it in caixas:
                c = it.find("complex")
                a, b = X.vec(c.find("field[@name='min']/complex")), X.vec(c.find("field[@name='max']/complex"))
                lo = [min(x, y) for x, y in zip(lo, a)]
                hi = [max(x, y) for x, y in zip(hi, b)]
            self.registrar_malha(m, caixa=[lo, hi])
        else:
            self.registrar_malha(m)
        no["malhas"].append(peca)

    def grupo_estatico(self, el, arq, pai, mvdb):
        membros = el.find("array[@name='MemberDatas']")
        if membros is None or not len(membros):
            return
        tr = el.find("field[@name='Transform']/complex")
        g = self.novo_no(pai=pai, tipo="smg", nome="Grupo estático", local=X.transformacao(tr) if tr is not None else X.IDENT,
                         alvo=None, jogo=None, mvdb=mvdb, guid=el.get("guid"))
        for mi, it in enumerate(membros):
            c = it.find("complex")
            mesh_ref = c.find("field[@name='MeshAsset']").get("ref", "")
            m = X.caminho_asset(mesh_ref)
            tipo_ref = c.find("field[@name='MemberType']")
            nome = X.curto(tipo_ref.get("ref")) if tipo_ref is not None and tipo_ref.get("ref") not in (None, "null") else X.curto(m)
            ts = [X.transformacao(x.find("complex")) for x in c.find("array[@name='InstanceTransforms']")]
            vis_arr = c.find("array[@name='Visible']")
            vis = [x.text != "false" for x in vis_arr] if vis_arr is not None else []
            self.registrar_malha(m)
            grupo = self.novo_no(pai=g["id"], tipo="membro", nome=nome, local=X.IDENT, alvo=None, jogo=None, mvdb=mvdb)
            for ii, t in enumerate(ts):
                self.novo_no(pai=grupo["id"], tipo="inst", nome=f"{nome} #{ii + 1}", local=t,
                             alvo={"arq": arq, "guid": el.get("guid"), "membro": mi, "indice": ii},
                             jogo={"visivel": vis[ii] if ii < len(vis) else True}, mvdb=mvdb,
                             malhas=[{"m": chave(m), "t": X.IDENT}])

    def registrar_malha(self, asset, caixa=None):
        k = chave(asset)
        info = self.malhas.get(k)
        if info is None:
            info = self.malhas[k] = {"asset": asset, "nome": X.curto(asset)}
        if caixa and "caixa" not in info:
            info["caixa"] = caixa
        info["usos"] = info.get("usos", 0) + 1

    # ------------------------------------------------------------------ poda
    def podar(self):
        """Remove grupos sem nada visível e objetos não exportados que não são geometria."""
        filhos = defaultdict(list)
        for n in self.nos:
            if n["pai"] >= 0:
                filhos[n["pai"]].append(n["id"])
        manter = [False] * len(self.nos)

        def visitar(i):
            n = self.nos[i]
            tem = bool(n.get("malhas")) or n["tipo"] in ("luz", "marcador")
            if n.get("faltando") == "blueprint":
                bp = n.get("bp", "").lower()
                tem = not any(p in bp for p in BP_NAO_VISUAIS)
            for f in filhos[i]:
                tem = visitar(f) or tem
            manter[i] = tem or n["tipo"] == "mundo"
            return manter[i]
        visitar(0)
        novo_id = {}
        nos = []
        for n in self.nos:
            if manter[n["id"]]:
                novo_id[n["id"]] = len(nos)
                nos.append(n)
        for n in nos:
            n["id"] = novo_id[n["id"]]
            n["pai"] = novo_id.get(n["pai"], -1) if n["pai"] >= 0 else -1
        self.nos = nos
        # usos de blueprint compartilhado (itens dentro de prefabs usados mais de uma vez)
        for n in self.nos:
            if n.get("aninhado") and n.get("alvo"):
                pai = self.nos[n["pai"]]
                n["compartilhado"] = self.uso_bp.get(pai.get("bp", "").lower(), 1)

    # ------------------------------------------------------------------ malhas, materiais, texturas
    def resolver_malhas(self):
        usados = defaultdict(set)   # mvdb -> malhas
        for n in self.nos:
            for p in n.get("malhas") or []:
                usados[n.get("mvdb")].add(p["m"])
        for k, info in self.malhas.items():
            fbx = self.ix.achar(info["asset"], ".fbx")
            info["fbx"] = self.ix.id_arquivo(fbx) if fbx else None
            xml = self.ix.achar(info["asset"], ".xml")
            info["xml"] = self.ix.id_arquivo(xml) if xml else None
            if xml:
                self.ler_xml_malha(info, self.ix.absoluto(xml))
        for mvdb, malhas in usados.items():
            if mvdb:
                self.ler_mvdb(mvdb, malhas)
        # malhas sem entrada no MVDB do próprio sub-mundo: procura em qualquer MVDB do export
        faltam = {m for mvdb, ms in usados.items() for m in ms
                  if not (self.mvdbs.get(mvdb) and m in self.mvdbs[mvdb]["entradas"])}
        if faltam:
            for k, item in self.ix.mapa.items():
                if k.endswith("/meshvariationdb_win32.xml"):
                    asset = "content/" + k[:-4]
                    if asset not in self.mvdbs:
                        self.ler_mvdb(asset, faltam)
                    achadas = faltam & set(self.mvdbs.get(asset, {}).get("entradas", {}))
                    for m in achadas:
                        self.malhas.get(m, {}).setdefault("mvdb_extra", asset)
                    faltam -= achadas
                    if not faltam:
                        break

    def ler_xml_malha(self, info, caminho):
        raiz = self.xml(caminho)
        prim = raiz.find("instance")
        if prim is None:
            return
        info["tipo"] = prim.get("type")
        info["enlighten"] = (prim.findtext("field[@name='EnlightenType']") or "").replace("EnlightenType_", "")
        insts = {i.get("guid"): i for i in raiz.findall("instance")}
        mats = []
        arr = prim.find("array[@name='Materials']")
        for it in (arr if arr is not None else []):
            g = it.get("ref")
            mm = insts.get(g)
            mats.append(dict(guid=g, **(self.material(mm) if mm is not None else {})))
        info["materiais"] = mats

    def material(self, inst):
        """shader, texturas e vetores de um MeshMaterial / MeshMaterialVariation."""
        sh = inst.find("field[@name='Shader']/complex/field[@name='Shader']")
        shader = X.curto(sh.get("ref")).replace("_shader", "").replace("_preset", "") if sh is not None else "?"
        tex, vet = {}, {}
        for p in inst.iter("complex"):
            t = p.get("type")
            if t == "TextureShaderParameter":
                nome = p.findtext("field[@name='ParameterName']")
                ref = p.find("field[@name='Value']").get("ref", "")
                a = X.caminho_asset(ref)
                tex[nome] = a
                self.registrar_textura(a, ref, p.find("field[@name='Value']").get("partitionGuid"))
            elif t == "VectorShaderParameter":
                nome = p.findtext("field[@name='ParameterName']")
                v = p.find("field[@name='Value']/complex")
                vet[nome] = {"tipo": (p.findtext("field[@name='ParameterType']") or "").replace("ShaderParameterType_", ""),
                             "v": [float(v.findtext(f"field[@name='{a}']")) for a in "xyzw"]}
        cs = inst.find("field[@name='CastShadow']")
        out = {"shader": shader, "texturas": tex, "vetores": vet}
        if cs is not None:
            out["sombra"] = cs.text == "true"
        return out

    def registrar_textura(self, asset, ref, pguid):
        if not asset or asset == "null" or asset in self.texturas:
            return
        png = self.ix.achar(asset, ".png")
        xml = self.ix.achar(asset, ".xml")
        self.texturas[asset] = {"png": self.ix.id_arquivo(png) if png else None,
                                "xml": self.ix.id_arquivo(xml) if xml else None,
                                "ref": ref.split(X.BS)[-1], "pguid": pguid}

    def ler_mvdb(self, mvdb_asset, malhas):
        item = self.ix.achar(mvdb_asset, ".xml")
        ent = self.mvdbs.setdefault(mvdb_asset, {"arq": self.ix.id_arquivo(item) if item else None, "entradas": {}})
        if not item:
            return
        raiz = self.xml(self.ix.absoluto(item))
        insts = {i.get("guid"): i for i in raiz.findall("instance")}
        db = next((i for i in raiz.findall("instance") if i.get("type") == "MeshVariationDatabase"), None)
        if db is None:
            return
        for it in db.find("array[@name='Entries']"):
            e = it.find("complex")
            k = chave(X.caminho_asset(e.find("field[@name='Mesh']").get("ref", "")))
            if k not in malhas:
                continue
            hash_var = e.findtext("field[@name='VariationAssetNameHash']")
            if k in ent["entradas"] and hash_var != "0":
                continue
            mats = []
            for m in e.find("array[@name='Materials']"):
                mc = m.find("complex")
                vg = mc.find("field[@name='MaterialVariation']").get("ref")
                var = insts.get(vg)
                d = {"variacao": vg, "material": X.guid_ref(mc.find("field[@name='Material']").get("ref", ""))}
                if var is not None:
                    d.update(self.material(var))
                mats.append(d)
            ent["entradas"][k] = mats

    # ------------------------------------------------------------------ saída
    def campo(self):
        """Medidas do gramado, espelhamento e áreas técnicas pelo stadiums.txt (tabela do jogo), se houver um perto."""
        arq = estadios_txt.localizar(self.ix.pastas, raiz_trabalho())
        sid = estadios_txt.id_do_mundo(self.mundo_asset)
        try:
            r = estadios_txt.resumo(arq, sid)
        except (OSError, ValueError, IndexError):
            r = None
        if r:
            r["fonte"] = os.path.basename(arq)
            return r
        return {"comprimento": 105.0, "largura": 68.0, "fonte": None, "nome": "", "id": sid, "arquivo": arq,
                "espelhado": None, "zonas": None}

    def json(self):
        return {"mundo": self.mundo_asset, "campo": self.campo(), "nos": self.nos, "malhas": self.malhas, "mvdbs": self.mvdbs,
                "texturas": self.texturas, "avisos": self.avisos[:200], "nuvens": self.nuvens,
                "pastas": self.ix.pastas}


def catalogo_texturas(indice):
    """Todas as texturas que algum MVDB do export referencia (com GUIDs válidos) + texturas exportadas."""
    rx = re.compile(r'<field name="ParameterName">([^<]+)</field>\s*<field name="Value" ref="([^"]+)" partitionGuid="([^"]+)"')
    cat = {}
    for k, item in indice.mapa.items():
        if not k.endswith("meshvariationdb_win32.xml"):
            continue
        texto = X.ler(indice.absoluto(item))
        for param, ref, pg in rx.findall(texto):
            a = X.caminho_asset(ref)
            if a and a not in cat:
                cat[a] = {"asset": a, "ref": X.guid_ref(ref), "pguid": pg, "param": param}
    rx_nome = re.compile(r'<field name="Name">([^<]+)</field>')
    rx_cab = re.compile(r'<partition guid="([^"]+)" primaryInstance="([^"]+)"')
    for k, item in indice.mapa.items():
        if not k.endswith(".png"):
            continue
        xml = indice.mapa.get(k[:-4] + ".xml")
        if not xml:
            continue
        cab = X.ler(indice.absoluto(xml))[:4000]
        m, c = rx_nome.search(cab), rx_cab.search(cab)
        if m and c and "TextureAsset" in cab:
            a = m.group(1)
            cat.setdefault(a, {"asset": a, "ref": c.group(2), "pguid": c.group(1), "param": ""})
    for a, d in cat.items():
        png = indice.achar(a, ".png")
        d["png"] = indice.id_arquivo(png) if png else None
    return sorted(cat.values(), key=lambda d: d["asset"].lower())
