"""Grava as edições do editor nos arquivos do export (XML/FBX/PNG), guardando o original antes.

Cada arquivo alterado tem uma cópia do original em <pasta>/_editor_originais/<mesmo caminho>, feita na primeira
vez que o editor o altera (a cópia nunca é sobrescrita). "Restaurar" copia de volta.
"""
import base64
import os
import random
import re
import shutil
import time
from collections import defaultdict

from . import estadios_txt
from . import xmlfet as X
from .indice import PASTA_BACKUP, chave

# arquivos fora do export que o editor também altera (stadiums.txt): caminho absoluto -> rótulo
EXTRAS = {}

TOL = 2e-3


class ErroEdicao(Exception):
    pass


def caminho_backup(indice, ident):
    ri, rel = ident.split(":", 1)
    return os.path.join(indice.pastas[int(ri)], PASTA_BACKUP, *rel.split("/"))


def garantir_backup(indice, ident):
    orig = indice.de_id(ident)
    bk = caminho_backup(indice, ident)
    if not os.path.exists(X.longo(bk)) and os.path.exists(X.longo(orig)):
        os.makedirs(X.longo(os.path.dirname(bk)), exist_ok=True)
        shutil.copy2(X.longo(orig), X.longo(bk))
    return orig


# ---------------------------------------------------------------- operações de texto

def op_transform(texto, a):
    ini, fim = X.trecho_instancia(texto, a["guid"])
    bloco = texto[ini:fim]
    sp = X.campo_span(bloco, a.get("campo") or "BlueprintTransform")
    if not sp:
        raise ErroEdicao(f"{a['guid']}: campo {a.get('campo')} não encontrado")
    novo = bloco[:sp[0]] + X.trocar_linear(bloco[sp[0]:sp[1]], a["t"]) + bloco[sp[1]:]
    return texto[:ini] + novo + texto[fim:]


def _membro(bloco, membro):
    inicios = [m.start() for m in re.finditer(r'<complex type="StaticModelGroupMemberData">', bloco)]
    if membro >= len(inicios):
        raise ErroEdicao(f"membro {membro} não existe no grupo estático")
    ini = inicios[membro]
    fim = X._fim_elemento(bloco, ini, "complex")
    return ini, fim


def op_transform_smg(texto, a):
    ini, fim = X.trecho_instancia(texto, a["guid"])
    bloco = texto[ini:fim]
    mi, mf = _membro(bloco, a["membro"])
    membro = bloco[mi:mf]
    sp = X.array_span(membro, "InstanceTransforms")
    its = X.itens(membro, *sp)
    if a["indice"] >= len(its):
        raise ErroEdicao("cópia não existe no grupo estático")
    s, e = its[a["indice"]]
    membro = membro[:s] + X.trocar_linear(membro[s:e], a["t"]) + membro[e:]
    bloco = bloco[:mi] + membro + bloco[mf:]
    return texto[:ini] + bloco + texto[fim:]


def op_visivel_smg(texto, a):
    ini, fim = X.trecho_instancia(texto, a["guid"])
    bloco = texto[ini:fim]
    mi, mf = _membro(bloco, a["membro"])
    membro = bloco[mi:mf]
    sp = X.array_span(membro, "Visible")
    if not sp:
        raise ErroEdicao("grupo estático sem lista Visible")
    its = X.itens(membro, *sp)
    if a["indice"] >= len(its):
        raise ErroEdicao("cópia não existe na lista Visible")
    s, e = its[a["indice"]]
    membro = membro[:s] + f"<item>{'true' if a['valor'] else 'false'}</item>" + membro[e:]
    bloco = bloco[:mi] + membro + bloco[mf:]
    return texto[:ini] + bloco + texto[fim:]


def op_excluido(texto, a):
    ini, fim = X.trecho_instancia(texto, a["guid"])
    bloco = X.trocar_valor_campo(texto[ini:fim], "Excluded", "true" if a["valor"] else "false")
    return texto[:ini] + bloco + texto[fim:]


def _parametro(bloco, tipo, nome):
    for m in re.finditer(rf'<complex type="{tipo}">', bloco):
        e = X._fim_elemento(bloco, m.start(), "complex")
        trecho = bloco[m.start():e]
        if re.search(rf'<field name="ParameterName">{re.escape(nome)}</field>', trecho):
            return m.start(), e
    return None


def op_textura(texto, a):
    ini, fim = X.trecho_instancia(texto, a["variacao"])
    bloco = texto[ini:fim]
    sp = _parametro(bloco, "TextureShaderParameter", a["parametro"])
    if not sp:
        raise ErroEdicao(f"parâmetro {a['parametro']} não existe no material")
    trecho = bloco[sp[0]:sp[1]]
    novo_ref = f'ref="{a["asset"]}{X.BS}{X.BS}{a["ref"]}" partitionGuid="{a["pguid"]}"'
    trecho, n = re.subn(r'(<field name="Value" )ref="[^"]*" partitionGuid="[^"]*"', lambda m: m.group(1) + novo_ref, trecho, count=1)
    if n != 1:   # referência vazia: <field name="Value" ref="null" />
        trecho, n = re.subn(r'(<field name="Value" )ref="null"', lambda m: m.group(1) + novo_ref, trecho, count=1)
    if n != 1:
        raise ErroEdicao("referência de textura não encontrada")
    bloco = bloco[:sp[0]] + trecho + bloco[sp[1]:]
    return texto[:ini] + bloco + texto[fim:]


def op_vetor(texto, a):
    ini, fim = X.trecho_instancia(texto, a["variacao"])
    bloco = texto[ini:fim]
    sp = _parametro(bloco, "VectorShaderParameter", a["parametro"])
    if not sp:
        raise ErroEdicao(f"parâmetro {a['parametro']} não existe no material")
    trecho = bloco[sp[0]:sp[1]]
    for eixo, v in zip("xyzw", a["v"]):
        trecho = re.sub(rf'(<field name="{eixo}">)({X.NUM})(</field>)', lambda m, v=v: m.group(1) + X.fmt_mantendo(m.group(2), v) + m.group(3),
                        trecho, count=1)
    bloco = bloco[:sp[0]] + trecho + bloco[sp[1]:]
    return texto[:ini] + bloco + texto[fim:]


def op_campo(texto, a):
    """Troca o valor de um campo simples da instância (ex.: Enabled de uma luz)."""
    ini, fim = X.trecho_instancia(texto, a["guid"])
    bloco = X.trocar_valor_campo(texto[ini:fim], a["campo"], str(a["valor"]))
    return texto[:ini] + bloco + texto[fim:]


def _vec_campo(bloco, nome, valores):
    """Troca x/y/z(/w) de um campo Vec3/Vec4 da instância."""
    sp = X.campo_span(bloco, nome)
    if not sp:
        raise ErroEdicao(f"campo {nome} não encontrado")
    trecho = bloco[sp[0]:sp[1]]
    for eixo, v in zip("xyzw", valores):
        trecho = re.sub(rf'(<field name="{eixo}">)({X.NUM})(</field>)',
                        lambda m, v=v: m.group(1) + X.fmt_mantendo(m.group(2), v) + m.group(3), trecho, count=1)
    return bloco[:sp[0]] + trecho + bloco[sp[1]:]


def _campos(bloco, valores):
    """Campos que a instância não tem (ex.: Width num spot) são ignorados."""
    for nome, v in valores.items():
        if f'<field name="{nome}"' not in bloco:
            continue
        if isinstance(v, (list, tuple)):
            bloco = _vec_campo(bloco, nome, v)
        else:
            if isinstance(v, bool):
                v = "true" if v else "false"
            elif isinstance(v, float):
                v = X.fmt(v)
            bloco = X.trocar_valor_campo(bloco, nome, str(v))
    return bloco


def op_campos(texto, a):
    """Vários campos de uma instância de uma vez (ex.: Color, Intensity, AttenuationRadius, OuterAngle de uma luz)."""
    ini, fim = X.trecho_instancia(texto, a["guid"])
    return texto[:ini] + _campos(texto[ini:fim], a["valores"]) + texto[fim:]


RX_GUID_LOCAL = re.compile(r'<instance guid="00000000-0000-0000-0000-([0-9a-fA-F]{12})"')
RX_FLAGS = re.compile(r'<field name="Flags">(\d+)</field>')


def _lista_com(texto, guid):
    """Posição (início do <item>) da referência ao guid numa lista Objects (ou outra) do arquivo."""
    m = re.search(rf'\n([ \t]*)<item ref="{re.escape(guid)}" />', texto)
    return m


def op_luz_nova(texto, a):
    """Cria uma luz copiando a instância modelo (mesmo tipo e ajustes), com GUID e Flags novos, e a põe na mesma
    lista de objetos. a['_guid'] recebe o GUID criado."""
    ini, fim = X.trecho_instancia(texto, a["modelo"])
    bloco = texto[ini:fim]
    usados = [int(h, 16) for h in RX_GUID_LOCAL.findall(texto)]
    while True:
        novo = f"00000000-0000-0000-0000-{max(usados, default=0) + 1:012x}"
        if f'guid="{novo}"' not in texto:
            break
        usados.append(int(novo[-12:], 16))
    flags = set(int(x) for x in RX_FLAGS.findall(texto))
    m = RX_FLAGS.search(bloco)
    f0 = int(m.group(1)) if m else 0
    rnd = random.Random(novo + a["modelo"])
    f = f0
    while f in flags:   # mesmos 8 bits baixos do modelo; o resto novo e único no arquivo
        f = (rnd.getrandbits(24) << 8) | (f0 & 0xFF)
    clone = bloco.replace(f'<instance guid="{a["modelo"]}"', f'<instance guid="{novo}"', 1)
    if m:
        clone = RX_FLAGS.sub(f'<field name="Flags">{f}</field>', clone, count=1)
    sp = X.campo_span(clone, "Transform")
    if not sp:
        raise ErroEdicao("luz modelo sem Transform")
    clone = clone[:sp[0]] + X.trocar_linear(clone[sp[0]:sp[1]], a["t"]) + clone[sp[1]:]
    valores = dict(a.get("valores") or {})
    valores.setdefault("Enabled", True)
    clone = _campos(clone, valores)
    nl = "\r\n" if "\r\n" in texto else "\n"
    texto = texto[:fim] + nl + "\t" + clone + texto[fim:]
    ref = _lista_com(texto, a["modelo"])
    if ref:
        linha = f'{nl}{ref.group(1)}<item ref="{novo}" />'
        texto = texto[:ref.end()] + linha + texto[ref.end():]
    a["_guid"] = novo
    return texto


def op_luz_excluir(texto, a):
    """Remove a instância da luz e a referência a ela na lista de objetos (só se nada mais a usa)."""
    g = a["guid"]
    usos = len(re.findall(rf'ref="{re.escape(g)}"', texto))
    if usos > 1:
        raise ErroEdicao("a luz está ligada a outra lógica; apague no jogo (Enabled) em vez de excluir")
    ini, fim = X.trecho_instancia(texto, g)
    antes = texto.rfind("\n", 0, ini)
    texto = texto[:antes if antes >= 0 else ini] + texto[fim:]
    m = re.search(rf'\r?\n[ \t]*<item ref="{re.escape(g)}" />', texto)
    if m:
        texto = texto[:m.start()] + texto[m.end():]
    return texto


def _indent(bloco, pos):
    ini = bloco.rfind("\n", 0, pos) + 1
    return bloco[ini:pos] if bloco[ini:pos].strip() == "" else ""


def op_textura_adicionar(texto, a):
    """Acrescenta um TextureShaderParameter ao material (o shader precisa usar esse parâmetro)."""
    ini, fim = X.trecho_instancia(texto, a["variacao"])
    bloco = texto[ini:fim]
    if _parametro(bloco, "TextureShaderParameter", a["parametro"]):
        return op_textura(texto, a)
    m = re.search(r'<array name="TextureParameters" type="TextureShaderParameter"\s*(/>|>)', bloco)
    if not m:
        raise ErroEdicao("material sem lista de texturas (o shader é nulo? copie um material antes)")
    base = _indent(bloco, m.start())
    nl = "\r\n" if "\r\n" in bloco else "\n"
    ref = f'ref="{a["asset"]}{X.BS}{X.BS}{a["ref"]}" partitionGuid="{a["pguid"]}"'
    item = (f'{base}\t<item>{nl}{base}\t\t<complex type="TextureShaderParameter">{nl}'
            f'{base}\t\t\t<field name="ParameterName">{a["parametro"]}</field>{nl}'
            f'{base}\t\t\t<field name="Value" {ref} />{nl}{base}\t\t</complex>{nl}{base}\t</item>{nl}')
    if m.group(1) == "/>":
        novo = f'<array name="TextureParameters" type="TextureShaderParameter">{nl}{item}{base}</array>'
        bloco = bloco[:m.start()] + novo + bloco[m.end():]
    else:
        fim_arr = X._fim_elemento(bloco, m.start(), "array")
        fecha = bloco.rfind("</array>", m.start(), fim_arr)
        ini_linha = bloco.rfind("\n", 0, fecha) + 1
        bloco = bloco[:ini_linha] + item + bloco[ini_linha:]
    return texto[:ini] + bloco + texto[fim:]


def _shader_de(texto, variacao):
    """(bloco <field name="Shader">...</field>, SurfaceShaderId, SurfaceShaderGuid) de uma variação do MVDB."""
    ini, fim = X.trecho_instancia(texto, variacao)
    bloco = texto[ini:fim]
    sp = X.campo_span(bloco, "Shader")
    if not sp:
        raise ErroEdicao("variação sem shader")
    m = re.search(rf'name="MaterialVariation" ref="{re.escape(variacao)}" />\s*<field name="SurfaceShaderId">([^<]*)</field>\s*'
                  r'<field name="SurfaceShaderGuid">([^<]*)</field>', texto)
    return bloco[sp[0]:sp[1]], (m.group(1) if m else None), (m.group(2) if m else None)


def op_material_copiar(texto, a):
    """Copia shader + parâmetros de outra variação (a['_origem'] já lida) para a variação destino."""
    bloco_orig, sid, sguid = a["_origem"]
    ini, fim = X.trecho_instancia(texto, a["variacao"])
    bloco = texto[ini:fim]
    sp = X.campo_span(bloco, "Shader")
    if not sp:
        raise ErroEdicao("variação destino sem campo Shader")
    bloco = bloco[:sp[0]] + bloco_orig + bloco[sp[1]:]
    texto = texto[:ini] + bloco + texto[fim:]
    if sid is not None:
        rx = re.compile(rf'(name="MaterialVariation" ref="{re.escape(a["variacao"])}" />\s*<field name="SurfaceShaderId">)([^<]*)'
                        r'(</field>\s*<field name="SurfaceShaderGuid">)([^<]*)(</field>)')
        texto = rx.sub(lambda m: m.group(1) + sid + m.group(3) + sguid + m.group(5), texto)
    return texto


def op_torcida(texto, a):
    from . import torcida
    return torcida.reescrever(texto, a["posicoes"], a["mapas"])


RX_LM = re.compile(r'<complex type="LightmapGenMeshInstance">')


def op_lightmap(texto, a):
    """Atualiza a entrada LightmapGenMeshInstance (malha, transformação antiga) -> nova. Sem entrada: nada."""
    alvo = chave(a["malha"])
    for m in RX_LM.finditer(texto):
        e = X._fim_elemento(texto, m.start(), "complex")
        trecho = texto[m.start():e]
        mesh = re.search(r'<field name="Mesh" ref="([^"]*)"', trecho)
        if not mesh or chave(X.caminho_asset(mesh.group(1))) != alvo:
            continue
        sp = X.campo_span(trecho, "Transform")
        if not sp:
            continue
        nums = [float(x) for x in re.findall(rf'<field name="[xyz]">({X.NUM})</field>', trecho[sp[0]:sp[1]])[:12]]
        if len(nums) == 12 and all(abs(p - q) <= TOL * max(1.0, abs(q)) for p, q in zip(nums, a["de"])):
            novo = trecho[:sp[0]] + X.trocar_linear(trecho[sp[0]:sp[1]], a["para"]) + trecho[sp[1]:]
            return texto[:m.start()] + novo + texto[e:], True
    return texto, False


OPERACOES = {"transform": op_transform, "transform_smg": op_transform_smg, "visivel_smg": op_visivel_smg,
             "excluido": op_excluido, "textura": op_textura, "vetor": op_vetor, "campo": op_campo, "campos": op_campos,
             "textura_adicionar": op_textura_adicionar, "material_copiar": op_material_copiar, "torcida": op_torcida,
             "luz_nova": op_luz_nova, "luz_excluir": op_luz_excluir}
PRIORIDADE = {"material_copiar": 0, "textura_adicionar": 1, "luz_excluir": 8, "luz_nova": 10}


def backup_extra(caminho):
    return os.path.join(os.path.dirname(caminho), PASTA_BACKUP, os.path.basename(caminho))


def _aplicar_estadio(ops):
    """Linha do estádio no stadiums.txt (fora do export): backup ao lado, em _editor_originais/."""
    gravados, erros = [], []
    por_arq = defaultdict(dict)
    for a in ops:
        por_arq[(a["arquivo"], str(a["id"]))].update(a["valores"])
    for (arq, sid), valores in por_arq.items():
        try:
            arq = os.path.abspath(arq)
            if os.path.basename(arq).lower() != "stadiums.txt" or not os.path.isfile(arq):
                raise ErroEdicao("stadiums.txt não encontrado")
            bk = backup_extra(arq)
            texto, _, _ = estadios_txt._ler(arq)
            if estadios_txt.trocar(texto, sid, valores) == texto:
                continue
            if not os.path.exists(bk):
                os.makedirs(os.path.dirname(bk), exist_ok=True)
                shutil.copy2(arq, bk)
            estadios_txt.gravar(arq, sid, valores)
            EXTRAS[arq] = "stadiums.txt"
            gravados.append("txt:" + arq)
        except (ErroEdicao, KeyError, OSError, ValueError) as ex:
            erros.append(f"stadiums.txt: {ex}")
    return gravados, erros


def aplicar(indice, alteracoes):
    """Aplica a lista de alterações. Retorna {arquivos: [...], lightmap: n, erros: [...]}."""
    por_arquivo = defaultdict(list)
    lightmaps, estadio = [], []
    for a in alteracoes:
        if a.get("tipo") == "lightmap":
            lightmaps.append(a)
        elif a.get("tipo") == "estadio":
            estadio.append(a)
        elif a.get("tipo") in OPERACOES:
            por_arquivo[a["arq"]].append(a)
        else:
            raise ErroEdicao(f"alteração desconhecida: {a.get('tipo')}")
    textos, erros, novas = {}, [], {}

    def texto_de(ident):
        if ident not in textos:
            textos[ident] = X.ler(indice.de_id(ident))
        return textos[ident]

    # a origem de um material copiado é lida antes de qualquer alteração (pode estar em outro arquivo)
    for lista in por_arquivo.values():
        for a in lista:
            if a["tipo"] == "material_copiar":
                try:
                    a["_origem"] = _shader_de(texto_de(a.get("arq_origem") or a["arq"]), a["variacao_origem"])
                except (ErroEdicao, KeyError, OSError) as ex:
                    a["_erro"] = str(ex)
    for ident, lista in por_arquivo.items():
        t = texto_de(ident)
        lista.sort(key=lambda a: PRIORIDADE.get(a["tipo"], 9))
        for a in lista:
            if a.get("_erro"):
                erros.append(f"{ident.split(':', 1)[1]}: {a['_erro']}")
                continue
            try:
                t = OPERACOES[a["tipo"]](t, a)
                if a.get("_guid") and a.get("chave"):
                    novas[a["chave"]] = a["_guid"]
            except (ErroEdicao, KeyError, ValueError) as ex:
                erros.append(f"{ident.split(':', 1)[1]}: {ex}")
        textos[ident] = t
    n_lm = 0
    for a in lightmaps:
        for ident in a.get("arqs", []):
            try:
                t, ok = op_lightmap(texto_de(ident), a)
            except (OSError, ValueError):
                continue
            if ok:
                textos[ident] = t
                n_lm += 1
                break
    gravados = []
    for ident, t in textos.items():
        caminho = indice.de_id(ident)
        if X.ler(caminho) == t:
            continue
        garantir_backup(indice, ident)
        X.gravar(caminho, t)
        gravados.append(ident)
    if estadio:
        g, e = _aplicar_estadio(estadio)
        gravados += g
        erros += e
    return {"arquivos": gravados, "lightmap": n_lm, "erros": erros, "novas": novas}


def gravar_binario(indice, ident, dados_b64):
    caminho = garantir_backup(indice, ident)
    dados = base64.b64decode(dados_b64)
    with open(X.longo(caminho), "wb") as f:
        f.write(dados)
    return caminho


def criar_arquivo(indice, rel, dados_b64):
    """Cria um arquivo novo na pasta principal (ex.: PNG de uma textura que não foi exportada)."""
    raiz = indice.pastas[0]
    caminho = os.path.abspath(os.path.join(raiz, *rel.split("/")))
    if not caminho.startswith(raiz + os.sep):
        raise PermissionError("caminho fora da pasta")
    if os.path.exists(caminho):
        raise ErroEdicao("arquivo já existe")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as f:
        f.write(base64.b64decode(dados_b64))
    return caminho


# ---------------------------------------------------------------- lista de alterações / restauração

def listar_alteracoes(indice):
    out = []
    for ri, raiz in enumerate(indice.pastas):
        bk_raiz = os.path.join(raiz, PASTA_BACKUP)
        if not os.path.isdir(bk_raiz):
            continue
        for dp, _, ns in os.walk(bk_raiz):
            for n in ns:
                bk = os.path.join(dp, n)
                rel = os.path.relpath(bk, bk_raiz).replace("\\", "/")
                if os.path.abspath(os.path.join(raiz, *rel.split("/"))) in EXTRAS:
                    continue   # stadiums.txt dentro do export: já entra como item próprio
                atual = X.longo(os.path.join(raiz, *rel.split("/")))
                if not os.path.exists(atual):
                    estado = "apagado"
                elif _iguais(bk, atual):
                    continue
                else:
                    estado = "alterado"
                k = chave(rel)
                asset = "content/" + os.path.splitext(k)[0]
                out.append({"id": f"{ri}:{rel}", "rel": rel, "asset": asset, "pasta": raiz, "estado": estado,
                            "tipo": os.path.splitext(n)[1].lower().lstrip("."),
                            "quando": time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(atual)))
                            if os.path.exists(atual) else ""})
    for arq, rotulo in EXTRAS.items():
        bk = backup_extra(arq)
        if os.path.isfile(bk) and os.path.isfile(arq) and not _iguais(bk, arq):
            out.append({"id": "txt:" + arq, "rel": rotulo, "asset": "banco do jogo (tabela stadiums)", "pasta": os.path.dirname(arq),
                        "estado": "alterado", "tipo": "txt",
                        "quando": time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(arq)))})
    out.sort(key=lambda d: d["rel"].lower())
    return out


def _iguais(a, b):
    a, b = X.longo(a), X.longo(b)
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 20), fb.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def restaurar(indice, idents):
    feitos = []
    for ident in idents:
        if ident.startswith("txt:"):
            arq = ident[4:]
            bk = backup_extra(arq)
            if arq in EXTRAS and os.path.isfile(bk):
                shutil.copy2(bk, arq)
                os.remove(bk)
                feitos.append(ident)
            continue
        bk = caminho_backup(indice, ident)
        if os.path.exists(X.longo(bk)):
            destino = indice.de_id(ident)
            shutil.copy2(X.longo(bk), X.longo(destino))
            os.remove(X.longo(bk))
            feitos.append(ident)
    return feitos


def exportar(indice, destino, idents=None):
    """Copia os arquivos alterados para destino, no mesmo layout (pronto para importar no FET)."""
    lista = [a for a in listar_alteracoes(indice) if a["estado"] == "alterado" and (idents is None or a["id"] in idents)]
    for a in lista:
        if a["id"].startswith("txt:"):
            shutil.copy2(a["id"][4:], os.path.join(destino, os.path.basename(a["id"][4:])))
            continue
        orig = indice.de_id(a["id"])
        rel = a["rel"]
        alvo = X.longo(os.path.join(destino, *rel.split("/")))
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        shutil.copy2(X.longo(orig), alvo)
    return len(lista)
