"""Monta um placar do FC a partir de um placar do PES, usando um placar do FC como molde.

O molde é um overlay de placar (…002.big) com o fundo numa imagem grande e os textos como campos soltos — o modelo dos
placares do pack do LTA (overlay_35002 Brasileirão e os outros ~30 iguais): txtTeamNameHome/Away, txtTeamScoreHome/Away,
mcClock (txtTenMin, txtMin, txtColon, txtTenSec, txtSec), mcExtraTime, mcTeamHomeColor/AwayColor e os cartões.

O resultado é uma lista de operações do Editor de Placares (as mesmas que a interface dele grava): a imagem de fundo
trocada pelo desenho do PES, as outras decorações do molde apagadas, e os textos, o relógio, os acréscimos e as cores
dos times levados para os lugares do PES. Grava como um projeto do editor, que abre e continua editando.
"""
import os
import sys

import numpy as np

import afp

AQUI = os.path.dirname(os.path.abspath(__file__))
# o Editor de Placares do Super Tool (BRFP_EDITOR_PLACARES aponta para outra cópia, para testes)
EDITOR = os.environ.get("BRFP_EDITOR_PLACARES") or os.path.join(os.path.dirname(os.path.dirname(AQUI)), "placares")
if EDITOR not in sys.path:
    sys.path.insert(0, EDITOR)

from nucleo import apt, projetos  # noqa: E402

TEXTOS = (("nome_casa", "txtTeamNameHome"), ("nome_fora", "txtTeamNameAway"),
          ("gols_casa", "txtTeamScoreHome"), ("gols_fora", "txtTeamScoreAway"))
RELOGIO = ("txtHundredMin", "txtTenMin", "txtMin", "txtColon", "txtTenSec", "txtSec")
CORES = (("cor_casa", "mcTeamHomeColor"), ("cor_fora", "mcTeamAwayColor"))
# peças do molde que continuam (o resto do conteúdo do placar some: brilhos, vidro, faixas…)
MANTER = ("mcBar", "mcTexts", "mcClock", "mcExtraTime", "mcTeamHomeColor", "mcTeamAwayColor", "mcRedCards", "mcEject")
CARTOES_CASA = ("mcRedCardsHome", "mcEjectLeft", "mcEjectHome", "mcHomeCard")
CARTOES_FORA = ("mcRedCardsAway", "mcEjectRight", "mcEjectAway", "mcAwayCard")
ESCURO, CLARO = [24, 24, 28, 255], [255, 255, 255, 255]


class ErroMolde(Exception):
    pass


mul, inv, ponto = afp._mul, afp.inversa, afp.ponto


def _local(it):
    return (it["m"][0], it["m"][1], it["m"][2], it["m"][3], it["tx"][0], it["tx"][1])


def lugares(a):
    """Cada objeto colocado no placar: nome, caminho, item do APT, character, matrizes do pai e do mundo."""
    out = []

    def rec(char_id, pai, caminho, nivel):
        c = a.chars[char_id] if 0 <= char_id < len(a.chars) else None
        if not c or "quadros" not in c or nivel > 12:
            return
        vistos = set()
        for q in c["quadros"]:
            for it in q:
                if it.get("t") != "place" or not it["fl"] & apt.F_CHAR or it["prof"] in vistos:
                    continue
                vistos.add(it["prof"])
                mundo = mul(_local(it), pai)
                cam = caminho + [it["nome"] or ""]
                lg = {"nome": it["nome"], "caminho": cam, "item": it, "char": it["char"], "pai": pai, "mundo": mundo}
                out.append(lg)
                rec(it["char"], mundo, cam, nivel + 1)
    rec(0, afp.IDENT, [], 0)
    return out


def _caixa_vertices(itens):
    xs, ys = [], []
    for it in itens:
        if it["k"] in (0, 1, 2) and it["v"]:
            v = it["v"]
            # alguns itens têm lixo nos vértices (números de 10^31): esses não contam
            if any(abs(x) > 1e5 for x in v):
                continue
            xs += v[0::2]
            ys += v[1::2]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _transformar_caixa(m, cx):
    pts = [ponto(m, x, y) for x, y in ((cx[0], cx[1]), (cx[2], cx[1]), (cx[0], cx[3]), (cx[2], cx[3]))]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


class Molde:
    """Um overlay do FC aberto (apt.Overlay) visto como molde de placar."""

    def __init__(self, ov):
        self.ov = ov
        self.a = ov.apt
        self.lugares = lugares(self.a)
        self.por_nome = {}
        for lg in self.lugares:
            if lg["nome"]:
                self.por_nome.setdefault(lg["nome"], lg)
        falta = [n for _, n in TEXTOS if n not in self.por_nome] + ([] if "mcClock" in self.por_nome else ["mcClock"])
        if falta:
            raise ErroMolde("Esse placar do FC não serve de molde: faltam " + ", ".join(falta) +
                            ". Use um dos placares do pack do LTA com o mesmo modelo do overlay_35002 (Brasileirão).")
        # o conteúdo do placar: o clipe do primeiro nível que contém os textos
        cam = self.por_nome["txtTeamNameHome"]["caminho"]
        self.raiz_nome = cam[0]
        self.geo = {}
        for i, c in enumerate(self.a.chars):
            if c and c["t"] == "forma":
                g = ov.ent.get(str(c["geo"] + 1))
                self.geo[i] = apt.ler_geometria(g) if g else []
        self.fundo = self._achar_fundo()

    def _usos_imagem(self):
        """(lugar da forma, item da geometria, char da imagem) para cada imagem desenhada."""
        usos = []
        for lg in self.lugares:
            c = self.a.chars[lg["char"]] if 0 <= lg["char"] < len(self.a.chars) else None
            if c and c["t"] == "forma":
                for it in self.geo.get(lg["char"], []):
                    if it["k"] in (0, 1) and it.get("img") is not None:
                        usos.append((lg, it, it["img"]))
        return usos

    def info_imagem(self, char):
        return apt.dds_info(self.ov.ent.get(str(self.a.chars[char]["tex"] + 1), b"")) or {"w": 0, "h": 0}

    def _achar_fundo(self):
        melhor = None
        for lg, it, img in self._usos_imagem():
            if self.raiz_nome not in lg["caminho"]:
                continue
            inf = self.info_imagem(img)
            bv = _caixa_vertices([it])
            if not bv:
                continue
            cx = _transformar_caixa(lg["mundo"], bv)
            area = (cx[2] - cx[0]) * (cx[3] - cx[1])
            if not melhor or area > melhor["area"]:
                melhor = {"lugar": lg, "item": it, "char": img, "w": inf["w"], "h": inf["h"], "area": area, "tela": cx}
        if not melhor or melhor["area"] < 200 * 40:
            raise ErroMolde("Esse placar do FC não tem uma imagem de fundo grande para receber o desenho do PES.")
        return melhor

    def descricao(self):
        f = self.fundo
        return {"fundo": {"w": f["w"], "h": f["h"], "tela": [round(v) for v in f["tela"]]},
                "campos": [n for _, n in TEXTOS if n in self.por_nome] + [n for n in RELOGIO if n in self.por_nome]}


def constantes_do_codigo(ov, bibliotecas=(), tema=None):
    """{nome: {slot, valor}} das constantes da classe do placar (pelo simulador de ActionScript do editor)."""
    from nucleo import as2
    try:
        r = as2.simular(ov, ("AnimateIn",), bibliotecas=bibliotecas, tema=tema)
    except Exception:  # o simulador é aproximado: sem ele, a conversão só não mexe nas constantes
        return {}
    return {c["nome"]: c for c in r.get("constantes") or [] if c.get("nome") and c.get("slot")}


# ------------------------------------------------------------------ a conversão

def posicionar(pl, x=64.0, y=48.0, escala=1.0):
    """Matriz filme do PES -> tela do FC: o canto do desenho do PES em (x, y), com a escala pedida."""
    cx = pl.caixa_visivel(("fundo", "cor_casa", "cor_fora"))
    return (escala, 0.0, 0.0, escala, x - escala * cx[0], y - escala * cx[1])


def _imagem_rgba(img):
    return img.width, img.height, np.ascontiguousarray(np.asarray(img.convert("RGBA"), np.uint8)).tobytes()


def _salvar(img):
    w, h, rgba = _imagem_rgba(img)
    return projetos.salvar_imagem(w, h, rgba), w, h


def _cor_texto(pl, caixa):
    lum = pl.luminancia(caixa, ("fundo", "cor_casa", "cor_fora"))
    return ESCURO if lum is not None and lum > 0.55 else CLARO


def converter(pl, molde, S, constantes=None):
    """Operações do Editor de Placares ({chave: op}) e um resumo do que foi feito.

    'constantes' são as constantes do código do molde ({nome: {slot, valor}}, do simulador do editor): algumas posições
    (o _x dos gols e do relógio, o _y dos cartões dos expulsos) são postas pelo código e só mudam por elas.
    """
    constantes = constantes or {}
    ops = {}
    resumo = []
    a = molde.a

    def op_place(lg, **campos):
        it = lg["item"]
        chave = "place:%d" % it["off"]
        atual = ops.get(chave) or {"op": "place", "off": it["off"]}
        atual.update(campos)
        ops[chave] = atual

    def op_texto(char, **campos):
        chave = "texto:%d" % char
        atual = ops.get(chave) or {"op": "texto", "char": char}
        atual.update(campos)
        ops[chave] = atual

    def op_textura(char, img):
        ident, w, h = _salvar(img)
        ops["textura:%d" % char] = {"op": "textura", "char": char, "img": ident, "w": w, "h": h}

    def tela(cx):
        return _transformar_caixa(S, cx)

    # 1. fundo: o desenho do PES na imagem grande, no lugar da tela em que ela aparece
    f = molde.fundo
    W, T = f["lugar"]["mundo"], tuple(f["item"]["m"])
    ajuste = mul(mul(S, inv(W)), T)
    op_textura(f["char"], pl.desenhar(("fundo",), ajuste, f["w"], f["h"]))
    resumo.append("Fundo do placar desenhado na imagem %d×%d do molde." % (f["w"], f["h"]))

    # 2. o resto do molde some: decorações do primeiro nível ficam transparentes e as outras imagens do fundo, vazias
    escondidos = []
    for lg in molde.lugares:
        cam = lg["caminho"]
        if len(cam) != 2 or cam[0] != molde.raiz_nome:
            continue
        nome = lg["nome"] or ""
        if "Mask" in nome or any(nome.startswith(k) for k in MANTER):
            continue
        tint = list(lg["item"]["tint"]) if lg["item"]["fl"] & apt.F_COR else [255, 255, 255, 255]
        op_place(lg, tint=tint[:3] + [0])
        escondidos.append(nome or "#%d" % lg["char"])
    bar = [u for u in molde._usos_imagem() if u[2] != f["char"] and set(u[0]["caminho"]) & set(f["lugar"]["caminho"][:2])
           and u[0]["caminho"][:len(f["lugar"]["caminho"]) - 1] == f["lugar"]["caminho"][:-1]]
    for _lg, _it, img in bar:
        inf = molde.info_imagem(img)
        if inf["w"] and inf["h"] and "textura:%d" % img not in ops:
            from PIL import Image
            op_textura(img, Image.new("RGBA", (inf["w"], inf["h"]), (0, 0, 0, 0)))
    if escondidos:
        resumo.append("Escondidas as decorações do molde: " + ", ".join(escondidos) + ".")

    def op_const(nome, valor, minimo=0, maximo=65535):
        c = constantes.get(nome)
        if not c or not isinstance(c.get("valor"), (int, float)):
            return False
        v = int(round(max(minimo, min(maximo, valor))))
        if v != c["valor"]:
            ops["const:" + c["slot"]] = {"op": "const", "slot": c["slot"], "valor": v, "orig": c["valor"], "nome": nome}
        return True

    # 3. nomes e placar nos lugares do PES
    centros = {}
    for campo, nome in TEXTOS:
        lg = molde.por_nome.get(nome)
        cx = pl.caixa_campo(campo)
        if not lg or not cx:
            continue
        c = a.chars[lg["char"]]
        if not c or c["t"] != "texto":
            continue
        R = tela(cx)
        pa, pd = lg["pai"][0], lg["pai"][3]
        ma, md = lg["item"]["m"][0], lg["item"]["m"][3]
        wl, hl = (R[2] - R[0]) / (ma * pa), (R[3] - R[1]) / (md * pd)
        px, py = ponto(inv(lg["pai"]), R[0], R[1])
        centros[campo] = ponto(inv(lg["pai"]), (R[0] + R[2]) / 2, (R[1] + R[3]) / 2)
        gols = campo.startswith("gols")
        altura = round(hl * (0.86 if gols else 0.72), 1)
        campos = {"altura": altura, "cor": _cor_texto(pl, cx)}
        if gols:
            # o código do placar põe o _x dos gols (encostados no traço do meio): o campo fica alinhado como está e
            # largo, e as constantes abaixo levam cada número para o seu círculo
            campos["limites"] = [-2.0, -2.0, max(c["limites"][2], round(wl - 2, 2)), round(hl - 2, 2)]
            centros["altura_gols"] = altura
        else:
            campos.update(limites=[-2.0, -2.0, round(wl - 2, 2), round(hl - 2, 2)], alinh=2)
        op_place(lg, tx=[px + 2 * ma, py + 2 * md])
        op_texto(lg["char"], **campos)
    resumo.append("Nomes dos times e placar levados para as caixas do PES.")
    if "gols_casa" in centros and "gols_fora" in centros:
        # gols: o da casa termina em C - traço/2 - PADDING e o de fora começa em C + traço/2 + PADDING
        # (C = OFFSET + BOUND/2); com um dígito (~0,6 da altura) e o traço (~0,3 da altura dele), cada número fica no
        # meio do seu círculo
        hc, fc_ = centros["gols_casa"][0], centros["gols_fora"][0]
        bound = (constantes.get("WIDTH_SCORE_BOUND") or {}).get("valor", 119)
        dash = molde.por_nome.get("txtTeamScoreDash")
        alt_dash = (a.chars[dash["char"]].get("altura") if dash and a.chars[dash["char"]] else None) or 30
        pad = (fc_ - hc) / 2 - 0.3 * alt_dash / 2 - 0.6 * centros["altura_gols"] / 2
        if op_const("SCORE_TEXT_TOTAL_OFFSET", (hc + fc_) / 2 - bound / 2) and op_const("PADDING_SCORE", pad, 0, 255):
            resumo.append("Constantes do código do placar ajustadas para os gols caírem nos círculos.")

    # 4. relógio: o clipe inteiro escalado e movido para a caixa do relógio do PES
    lc = molde.por_nome.get("mcClock")
    cx = pl.caixa_campo("relogio")
    filhos = [molde.por_nome[n] for n in RELOGIO if n in molde.por_nome
              and molde.por_nome[n]["caminho"][:len(lc["caminho"])] == lc["caminho"]]
    if lc and cx and filhos:
        R = tela(cx)
        usados = [l for l in filhos if l["nome"] != "txtHundredMin"] or filhos
        alt = max(a.chars[l["char"]].get("altura", 30) for l in usados if a.chars[l["char"]])
        ex0 = min(l["item"]["tx"][0] for l in usados)
        ex1 = max(l["item"]["tx"][0] for l in usados) + 0.62 * alt
        ey0 = min(l["item"]["tx"][1] for l in usados) + 0.10 * alt
        ey1 = ey0 + 0.95 * alt
        k = min((R[2] - R[0]) / (ex1 - ex0), (R[3] - R[1]) / (ey1 - ey0))
        pa, pd = lc["pai"][0], lc["pai"][3]
        ma, md = k / pa, k / pd
        alvo = (R[0] + ((R[2] - R[0]) - k * (ex1 - ex0)) / 2, R[1] + ((R[3] - R[1]) - k * (ey1 - ey0)) / 2)
        px, py = ponto(inv(lc["pai"]), *alvo)
        tx = [float(round(px - ma * ex0)), py - md * ey0]
        op_place(lc, m=[ma, 0.0, 0.0, md], tx=tx)
        # o código põe o _x do relógio (4 ou 5 dígitos): as duas constantes vão junto
        quatro = (constantes.get("FOUR_DIGIT_X") or {}).get("valor")
        cinco = (constantes.get("FIVE_DIGIT_X") or {}).get("valor")
        if isinstance(quatro, (int, float)):
            op_const("FOUR_DIGIT_X", tx[0])
            if isinstance(cinco, (int, float)):
                op_const("FIVE_DIGIT_X", tx[0] + (cinco - quatro) * ma / (lc["item"]["m"][0] or 1))
        cor = _cor_texto(pl, cx)
        for l in filhos:
            if a.chars[l["char"]] and a.chars[l["char"]]["t"] == "texto":
                op_texto(l["char"], cor=cor)
        resumo.append("Relógio levado para a caixa do relógio do PES (escala %.2f)." % k)

    # 5. acréscimos: a placa do PES vira a imagem da caixa de acréscimos do molde
    le = molde.por_nome.get("mcExtraTime")
    cxa = pl.caixa_campo("acrescimos")
    if le and cxa:
        perto = (cxa[0] - 40, cxa[1] - 30, cxa[2] + 40, cxa[3] + 30)
        vis = pl.caixa_visivel(("acrescimos",), limite=perto) or cxa
        usos = [u for u in molde._usos_imagem() if u[0]["caminho"][:len(le["caminho"])] == le["caminho"]]
        if usos:
            lg_f, it_f, img = usos[0]
            B = _caixa_vertices([it_f])
            R = tela(vis)
            # escala uniforme pela altura; a largura da caixa do molde fica, e a placa do PES vai centrada nela
            local_f = mul(lg_f["mundo"], inv(le["mundo"]))          # forma -> espaço do mcExtraTime
            Bl = _transformar_caixa(local_f, B)
            k = (R[3] - R[1]) / (Bl[3] - Bl[1])
            pa, pd = le["pai"][0], le["pai"][3]
            ma, md = k / pa, k / pd
            cxm, cym = (R[0] + R[2]) / 2, (R[1] + R[3]) / 2
            px, py = ponto(inv(le["pai"]), cxm, cym)
            tx = [px - ma * (Bl[0] + Bl[2]) / 2, py - md * (Bl[1] + Bl[3]) / 2]
            op_place(le, m=[ma, 0.0, 0.0, md], tx=tx)
            novo_le = mul((ma, 0.0, 0.0, md, tx[0], tx[1]), le["pai"])
            Wf = mul(local_f, novo_le)
            inf = molde.info_imagem(img)
            wi, hi = max(8, int(round((B[2] - B[0]) * k * 2))), max(8, int(round((B[3] - B[1]) * k * 2)))
            Tn = mul(tuple(it_f["m"]), (wi / inf["w"], 0.0, 0.0, hi / inf["h"], 0.0, 0.0)) if inf["w"] else tuple(it_f["m"])
            op_textura(img, pl.desenhar(("acrescimos",), mul(mul(S, inv(Wf)), Tn), wi, hi))
            resumo.append("Placa dos acréscimos do PES na caixa de acréscimos do molde.")

    # 6. cores dos times: as faixas do molde no lugar das placas de cor do PES
    for papel, nome in CORES:
        lg = molde.por_nome.get(nome)
        vis = pl.caixa_visivel((papel,))
        if not lg or not vis:
            continue
        formas = [l for l in molde.lugares if l["caminho"][:len(lg["caminho"])] == lg["caminho"] and l is not lg
                  and a.chars[l["char"]] and a.chars[l["char"]]["t"] == "forma"]
        if not formas:
            continue
        caixas = [_transformar_caixa(mul(l["mundo"], inv(lg["mundo"])), _caixa_vertices(molde.geo[l["char"]]) or (0, 0, 1, 1))
                  for l in formas]
        B = (min(c[0] for c in caixas), min(c[1] for c in caixas), max(c[2] for c in caixas), max(c[3] for c in caixas))
        R = tela(vis)
        P0, P1 = ponto(inv(lg["pai"]), R[0], R[1]), ponto(inv(lg["pai"]), R[2], R[3])
        sa = 1 if lg["item"]["m"][0] >= 0 else -1
        sd = 1 if lg["item"]["m"][3] >= 0 else -1
        ma = sa * abs(P1[0] - P0[0]) / max(1e-6, B[2] - B[0])
        md = sd * abs(P1[1] - P0[1]) / max(1e-6, B[3] - B[1])
        tx = min(P0[0], P1[0]) - (ma * B[0] if ma > 0 else ma * B[2])
        ty = min(P0[1], P1[1]) - (md * B[1] if md > 0 else md * B[3])
        op_place(lg, m=[ma, 0.0, 0.0, md], tx=[tx, ty])
    resumo.append("Faixas das cores dos times nas placas de cor do PES.")

    # 7. cartões: os vermelhos logo abaixo do placar e os dos expulsos logo acima, a partir da ponta de dentro de cada
    #    nome (os da casa crescem para a esquerda, os de fora para a direita)
    fundo_tela = tela(pl.caixa_visivel(("fundo", "cor_casa", "cor_fora")))
    for campo, nomes in (("nome_casa", CARTOES_CASA), ("nome_fora", CARTOES_FORA)):
        cn = pl.caixa_campo(campo)
        if not cn:
            continue
        N = tela(cn)
        x_ref = N[2] if campo == "nome_casa" else N[0]
        for n in nomes:
            lg = molde.por_nome.get(n)
            if not lg:
                continue
            filhos_c = [l for l in molde.lugares if l["caminho"][:len(lg["caminho"])] == lg["caminho"] and l is not lg
                        and a.chars[l["char"]] and a.chars[l["char"]]["t"] == "forma"]
            cxs = [_transformar_caixa(l["mundo"], _caixa_vertices(molde.geo[l["char"]]) or (0, 0, 0, 0)) for l in filhos_c]
            alt_t = max((c[3] - c[1] for c in cxs), default=10)
            # os desenhos dos cartões têm a base no y do clipe (vão de -altura até 0)
            y_tela = fundo_tela[1] - 3 if n.startswith("mcEject") else fundo_tela[3] + 3 + alt_t
            q = ponto(inv(lg["pai"]), x_ref, y_tela)
            op_place(lg, tx=[q[0], q[1]])
            if n.startswith("mcEject"):
                op_const("Y_EJECTED_PLAYERS_DEFAULT", q[1], 0, 255)
    return ops, resumo


# ------------------------------------------------------------------ prévia (como deve ficar no FC)

def previa(pl, molde, S, largura=1920, altura=1080, recorte=True):
    """O fundo do PES na tela do FC com textos de exemplo nas caixas (o jogo escreve os de verdade)."""
    from PIL import ImageDraw, ImageFont
    img = pl.desenhar(("fundo", "cor_casa", "cor_fora"), S, largura, altura, fundo=(30, 96, 52, 255))
    dr = ImageDraw.Draw(img)
    exemplos = {"nome_casa": "KAW", "nome_fora": "YOK", "gols_casa": "2", "gols_fora": "1", "relogio": "45:00"}
    for campo, txt in exemplos.items():
        cx = pl.caixa_campo(campo)
        if not cx:
            continue
        R = _transformar_caixa(S, cx)
        tam = max(8, int((R[3] - R[1]) * 0.72))
        try:
            fonte = ImageFont.truetype("arialbd.ttf", tam)
        except OSError:
            fonte = ImageFont.load_default()
        cor = tuple(_cor_texto(pl, cx))
        dr.text(((R[0] + R[2]) / 2, (R[1] + R[3]) / 2), txt, fill=cor, font=fonte, anchor="mm")
    if recorte:
        cx = _transformar_caixa(S, pl.caixa_visivel(("fundo", "cor_casa", "cor_fora")))
        m = 24
        img = img.crop((max(0, int(cx[0]) - m), max(0, int(cx[1]) - m), min(largura, int(cx[2]) + m),
                        min(altura, int(cx[3]) + m)))
    return img
