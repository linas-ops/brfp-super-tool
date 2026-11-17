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


def simular(ov, bibliotecas=(), tema=None):
    """O que o código do placar faz ao entrar (pelo simulador de ActionScript do editor): {"constantes": {nome: {slot,
    valor}}, "textos": {caminho do clipe: {config do MultiText}}, "tweens": [...], "formatos": [TextFormat criados:
    fonte_chave, tamanho, tamanho_slot…]}. Vazio se a simulação falhar."""
    from nucleo import as2
    try:
        r = as2.simular(ov, ("AnimateIn",), bibliotecas=bibliotecas, tema=tema)
    except Exception:  # o simulador é aproximado: sem ele, a conversão só não mexe nas constantes
        return {"constantes": {}, "textos": {}, "tweens": [], "formatos": []}
    return {"constantes": {c["nome"]: c for c in r.get("constantes") or [] if c.get("nome") and c.get("slot")},
            "textos": r.get("textos") or {}, "tweens": r.get("tweens") or [], "formatos": r.get("formatos") or []}


def constantes_do_codigo(ov, bibliotecas=(), tema=None):
    """{nome: {slot, valor}} das constantes da classe do placar (pelo simulador de ActionScript do editor)."""
    return simular(ov, bibliotecas, tema)["constantes"]


def ler_chamadas(ov):
    """Leitura simbólica do código do overlay, nas duas codificações do APT (a de PushData do overlay_9002 e a compacta
    do overlay_9021, com índices do ConstantPool no próprio byte da instrução).

    Devolve (chamadas, funções). Cada chamada: {"funcao" (nome do método em que está), "nome" (método chamado),
    "slot_nome" (de onde vem o nome: troca só nessa chamada), "obj" (caminho do objeto: "<reg1>.mcA.mcB", "cafe.utility.
    ColorUtil"…), "args" ([{"v", "slot", "cam", "refs"}]: valor, de onde vem, caminho, nomes de membros usados na conta),
    "pos"}. Cada função: {"nome", "inicio", "fim", "pars" ([(registrador, nome)])}."""
    import struct
    from nucleo import as2
    d = bytes(ov.apt.d)
    c = as2.Constantes(ov.entrada("1"))
    chamadas, funcoes = [], []

    def val(v=None, slot=None, cam=None, refs=()):
        return {"v": v, "slot": slot, "cam": cam, "refs": frozenset(refs)}

    def junta(*xs):
        r = set()
        for x in xs:
            r |= x["refs"]
            if x["cam"]:
                r.add(x["cam"].split(".")[-1])
        return val(refs=r)

    def membro(obj, nome, slot):
        reg = obj["v"] if isinstance(obj["v"], tuple) and obj["v"][:1] == ("reg",) else None
        base = obj["cam"] if obj["cam"] is not None else ("<reg%d>" % reg[1] if reg else "?")
        return val(cam=base + "." + str(nome), refs=obj["refs"] | {str(nome)}, slot=slot)

    def args_de(pilha, n):
        n = n if isinstance(n, int) and 0 <= n < 64 else 0
        return [pilha.pop() if pilha else val() for _ in range(n)]

    def rodar(p, fim, pool, pool_pos, nome_funcao):
        pilha, alvos, ult_txt, n = [], {}, None, 0
        pop = lambda: pilha.pop() if pilha else val()
        while p < fim and n < 400000:
            n += 1
            if p in alvos:                          # destino de um desvio: a pilha de quando o desvio saiu
                pilha = alvos.pop(p)
            try:
                op, arg, q = as2.decodificar(d, p)
            except (struct.error, IndexError, as2.ErroAS):
                return
            if op == 0x00:
                return
            if op == 0x88:
                ptr, cnt = arg
                pool = [c.valor(i, []) for i in struct.unpack_from("<%dQ" % cnt, d, ptr)] if cnt else []
                pool_pos = p
            elif op == 0x96:
                ptr, cnt = arg
                for i in (struct.unpack_from("<%dQ" % cnt, d, ptr) if cnt else ()):
                    v = c.valor(i, pool)
                    pilha.append(val(v=v) if isinstance(v, tuple) and v[:1] == ("reg",) else val(v=v, slot="c:%d" % i))
                    if isinstance(v, str):
                        ult_txt = v
            elif op in (0xA2, 0xA3):
                v = pool[arg] if arg < len(pool) else None
                pilha.append(val(v=v, slot="%s:%d:%s" % ("pk" if op == 0xA2 else "pkw", p + 1, pool_pos)))
                if isinstance(v, str):
                    ult_txt = v
            elif op == 0xA1:
                ult_txt = as2._txt(d, arg)
                pilha.append(val(v=ult_txt))
            elif op in (0xB4, 0xB5, 0xB6, 0xB7):
                pilha.append(val(v=arg, slot="%s:%d" % ({0xB4: "pf", 0xB5: "pb", 0xB6: "ps", 0xB7: "pl"}[op], p + 1)))
            elif op == 0xB9:
                pilha.append(val(v=("reg", arg)))
            elif op in (0x59, 0x5A, 0x73, 0x74, 0x75, 0x76):
                pilha.append(val(v={0x59: 0, 0x5A: 1, 0x73: True, 0x74: False}.get(op)))
            elif op in (0x56, 0x58, 0x71):
                pilha.append(val(cam="this" if op == 0x56 else "_global"))
            elif op == 0xAE:
                pilha.append(val(cam=str(pool[arg]) if arg < len(pool) else "?"))
            elif op == 0x1C:
                pilha.append(val(cam=str(pop()["v"])))
            elif op in (0xAF, 0xA5):
                if op == 0xAF:
                    nome, slot = (pool[arg] if arg < len(pool) else "?"), "pk:%d:%s" % (p + 1, pool_pos)
                else:
                    nome, slot = as2._txt(d, arg), None
                pilha.append(membro(pop(), nome, slot))
            elif op == 0x4E:
                nm = pop()
                pilha.append(membro(pop(), nm["v"], nm["slot"]))
            elif op in (0xB2, 0xB3, 0x52, 0x5D, 0x5E):     # chamada de método (nome no byte ou na pilha)
                if op in (0xB2, 0xB3):
                    nome, slot = (pool[arg] if arg < len(pool) else None), "pk:%d:%s" % (p + 1, pool_pos)
                else:
                    nm = pop()
                    nome, slot = nm["v"], nm["slot"]
                obj = pop()
                args = args_de(pilha, pop()["v"])
                chamadas.append({"funcao": nome_funcao, "nome": nome, "slot_nome": slot, "obj": obj["cam"],
                                 "args": args, "pos": p})
                if op in (0xB3, 0x52, 0x5E):
                    pilha.append(junta(obj, *args))
            elif op in (0xB0, 0xB1, 0x3D, 0x5B, 0x5C):     # chamada de função
                nome = (pool[arg] if arg < len(pool) else None) if op in (0xB0, 0xB1) else pop()["v"]
                args = args_de(pilha, pop()["v"])
                chamadas.append({"funcao": nome_funcao, "nome": nome, "slot_nome": None, "obj": None, "args": args,
                                 "pos": p})
                if op in (0xB1, 0x3D, 0x5C):
                    pilha.append(junta(*args))
            elif op in (0x40, 0x53):
                nm = pop()
                if op == 0x53:
                    pop()
                args_de(pilha, pop()["v"])
                pilha.append(val(cam="new " + str(nm["v"])))
            elif op in (0x47, 0x0B, 0x0C, 0x0D, 0x48, 0x67, 0x49, 0x66, 0x10, 0x11, 0x3F, 0x60, 0x13, 0x0A, 0x0E, 0x0F,
                        0x54, 0x2B):
                b = pop()
                pilha.append(junta(pop(), b))
            elif op in (0x12, 0x4B, 0x4A, 0x18, 0x14, 0x44, 0x50, 0x51):
                pilha.append(junta(pop()))
            elif op in (0x17, 0x3E, 0x55):
                x = pop()
                if op == 0x55:                      # enumerate2: deixa os nomes na pilha
                    pilha.append(junta(x))
            elif op == 0x4C:
                x = pop()
                pilha += [x, dict(x)]
            elif op == 0x4D:
                b, a_ = pop(), pop()
                pilha += [b, a_]
            elif op == 0x4F:
                pop(), pop(), pop()
            elif op in (0x1D, 0xA7):
                pop(), pop()
            elif op in (0x42, 0x43):
                k = pop()["v"]
                xs = args_de(pilha, (k if op == 0x42 else 2 * k) if isinstance(k, int) and k < 2048 else 0)
                pilha.append(junta(*xs))
            elif op in (0x8E, 0x9B):
                corpo = arg[4] if op == 0x8E else arg[2]
                pars = [(r, d[pn:d.index(b"\0", pn)].decode("latin-1") if pn else "") for r, pn in arg[1]] \
                    if op == 0x8E else []
                nome_f = ult_txt or ""
                funcoes.append({"nome": nome_f, "inicio": q, "fim": q + corpo, "pars": pars})
                rodar(q, q + corpo, list(pool), pool_pos, nome_f)
                q += corpo
                pilha.append(val(cam="function " + nome_f))
            elif op in (0x9D, 0xB8):
                pop()
                alvos.setdefault(q + arg, [dict(x) for x in pilha])
            elif op == 0x99:
                alvos.setdefault(q + arg, [dict(x) for x in pilha])
                pilha = []
            p = q

    for _tipo, _spr, codigo in as2._itens_quadro0(ov.apt):
        rodar(codigo, len(d), [], None, "")
    return chamadas, funcoes


def _relativo(cam):
    """Caminho a partir do registrador do this ("<reg1>.mcA.mcB" -> "mcA.mcB")."""
    partes = (cam or "").split(".")
    return ".".join(partes[1:] if partes and partes[0].startswith("<reg") else partes)


def chamadas_pintura(ov, metodo="ChangeColorFlat", chamadas=None):
    """Onde o código do overlay chama ColorUtil.<metodo>(clipe, cor): [(caminho do clipe a partir do this, slot do
    nome do método)]. O slot ("c:N" ou "pk:pos:pool") troca o nome só naquela chamada (operação const_txt)."""
    if chamadas is None:
        chamadas = ler_chamadas(ov)[0]
    return [(_relativo(ch["args"][0]["cam"]), ch["slot_nome"]) for ch in chamadas
            if ch["nome"] == metodo and str(ch["obj"] or "").endswith("ColorUtil") and ch["args"]]


def abrir(ov):
    """O overlay como molde: o modelo do LTA (fundo numa imagem e textos soltos) ou o Generic do jogo."""
    try:
        return Molde(ov)
    except ErroMolde as e1:
        try:
            return MoldeGeneric(ov)
        except ErroMolde:
            raise e1


# ------------------------------------------------------------------ o molde Generic do jogo (overlay_9002)

G = "mcClassOverlay"
G_PRECISA = (G + ".mcTeamHolder.mcHomeTeamName", G + ".mcTeamHolder.mcAwayTeamName", G + ".mcScoreHolder.mcScoreHome",
             G + ".mcScoreHolder.mcScoreAway", G + ".mcClockText", G + ".mcLogoHolder.mcLogoFc",
             G + ".mcLogoHolder.mcLogoMask")
G_DIGITOS = ("txtTenMin", "txtMin", "txtColon", "txtTenSec", "txtSec")
# decorações do Generic que somem (as caixas de cor, a faixa do título, os escudos, os ícones de "on fire"…)
G_ESCONDER = (G + ".mcClockBg", G + ".mcTeamHolder.mcBg", G + ".mcTeamHolder.mcLines", G + ".mcHeader",
              G + ".mcRedLineHome", G + ".mcRedLineAway", G + ".mcOnFireHome", G + ".mcOnFireAway",
              G + ".mcTeamHolder.mcLogoHome", G + ".mcTeamHolder.mcLogoAway", G + ".mcLogoHolder.mcLogoBg",
              G + ".mcLogoHolder.mcLine", G + ".mcLogoHolder.mcLogo", G + ".mcLogoHolder.mcUTProLogo")
# os que o código volta a mostrar (_alpha, cor) mas nunca move num eixo: vão para longe nesse eixo. As máscaras levam
# junto o que cobrem (o fundo e o fio do logo, o logo da liga, o título, os fios entre nomes e gols).
G_AFASTAR = ((G + ".mcOnFireHome", "y"), (G + ".mcOnFireAway", "y"), (G + ".mcRedLineHome", "y"),
             (G + ".mcRedLineAway", "y"), (G + ".mcLogoHolder.mcLogoBgMask", "x"), (G + ".mcLogoHolder.mcLogoFcMask", "x"),
             (G + ".mcHeaderMask", "y"), (G + ".mcTeamHolder.mcLineMask", "x"))
# o Init do Generic pinta clipes com ColorUtil.ChangeColorFlat (cor chapada, com as cores da competição): o logo do FC
# (onde fica a arte do PES) vira uma silhueta preta ou branca e os textos ganham a cor do tema por cima da do
# TextFormat. Nessas chamadas o nome do método é trocado por um que não existe, e a chamada não faz nada.
G_SEM_PINTURA = ("m_mcLogoFc", "mcTeamHolder.mcHomeTeamName", "mcTeamHolder.mcAwayTeamName", "mcScoreHolder.mcScoreHome",
                 "mcScoreHolder.mcScoreAway", "mcClockText", "mcExtraTime")
PINTURA, PINTURA_DESLIGADA = "ChangeColorFlat", "ChangeColorFlat_PES"
MULTITEXT_LARGURA = 240        # MultiText.PROXY_BASE_WIDTH: a caixa do texto tem 240 × _xscale de largura


class MoldeCodigo:
    """Um overlay do jogo em que o código põe as peças no lugar (os Generic): os lugares por caminho, as formas e as
    chamadas do código (pintura com cor chapada, animações…)."""
    precisa = ()

    def __init__(self, ov):
        self.ov = ov
        self.a = ov.apt
        self.lugares = lugares(self.a)
        self.por_caminho = {}
        for lg in self.lugares:
            self.por_caminho.setdefault(".".join(lg["caminho"]), lg)
        falta = [c.split(".")[-1] for c in self.precisa if c not in self.por_caminho]
        if falta:
            raise ErroMolde("Esse placar do FC não serve de molde: faltam " + ", ".join(falta) + ".")
        self.geo = {}
        for i, c in enumerate(self.a.chars):
            if c and c["t"] == "forma":
                g = ov.ent.get(str(c["geo"] + 1))
                self.geo[i] = apt.ler_geometria(g) if g else []
        self._codigo = None

    def _ler_codigo(self):
        if self._codigo is None:
            try:
                self._codigo = ler_chamadas(self.ov)
            except Exception:  # noqa: BLE001  (código diferente do esperado: a conversão só avisa)
                self._codigo = ([], [])
        return self._codigo

    @property
    def chamadas(self):
        return self._ler_codigo()[0]

    @property
    def funcoes(self):
        return self._ler_codigo()[1]

    @property
    def pinturas(self):
        """[(clipe, slot)] das chamadas de ChangeColorFlat do código."""
        return chamadas_pintura(self.ov, PINTURA, self.chamadas)

    def imagem_em(self, cam):
        """A primeira forma com imagem dentro do clipe 'cam': {lugar, item, char (da imagem), w, h, caixa}."""
        lf = self.por_caminho[cam]
        for lg in self.lugares:
            c = self.a.chars[lg["char"]] if 0 <= lg["char"] < len(self.a.chars) else None
            if c and c["t"] == "forma" and lg["caminho"][:len(lf["caminho"])] == lf["caminho"] and lg is not lf:
                for it in self.geo.get(lg["char"], []):
                    if it["k"] in (0, 1) and it.get("img") is not None:
                        img = it["img"]
                        inf = apt.dds_info(self.ov.ent.get(str(self.a.chars[img]["tex"] + 1), b"")) or {"w": 0, "h": 0}
                        return {"lugar": lg, "item": it, "char": img, "w": inf["w"], "h": inf["h"],
                                "caixa": _caixa_vertices(self.geo[lg["char"]])}
        return None

    def forma_em(self, lg):
        """A forma colocada direto dentro do clipe (a de uma máscara, por exemplo) e a caixa dela: (lugar, caixa)."""
        n = len(lg["caminho"])
        for d in self.lugares:
            c = self.a.chars[d["char"]] if 0 <= d["char"] < len(self.a.chars) else None
            if d is not lg and len(d["caminho"]) == n + 1 and d["caminho"][:n] == lg["caminho"] and c and c["t"] == "forma":
                bv = _caixa_vertices(self.geo.get(d["char"], []))
                if bv:
                    return d, bv
        return None, None

    def mascara_de(self, lg):
        """O irmão que serve de máscara para o clipe (profundidade < a dele <= a do recorte): o lugar, ou None."""
        n = len(lg["caminho"]) - 1
        prof = lg["item"]["prof"]
        for d in self.lugares:
            it = d["item"]
            if len(d["caminho"]) == n + 1 and d["caminho"][:n] == lg["caminho"][:n] and it["fl"] & apt.F_RECORTE \
                    and it["prof"] < prof <= it["clip"]:
                return d
        return None

    # ---------------------------------------------------------- geometria
    def caixa_conteudo(self, lg):
        """Retângulo do que um clipe desenha (formas dentro dele), nas coordenadas do próprio clipe."""
        n = len(lg["caminho"])
        cxs = []
        for d in self.lugares:
            if d is lg or d["caminho"][:n] != lg["caminho"]:
                continue
            c = self.a.chars[d["char"]] if 0 <= d["char"] < len(self.a.chars) else None
            if c and c["t"] == "forma":
                bv = _caixa_vertices(self.geo.get(d["char"], []))
                if bv:
                    cxs.append(_transformar_caixa(mul(d["mundo"], inv(lg["mundo"])), bv))
        if not cxs:
            return None
        return (min(c[0] for c in cxs), min(c[1] for c in cxs), max(c[2] for c in cxs), max(c[3] for c in cxs))


class MoldeGeneric(MoldeCodigo):
    """O placar Generic do jogo (data/ui/game/overlays/Generic/overlay_9002.big) visto como molde.

    É bem diferente do modelo do LTA: o desenho são caixas de cor sem imagem, e os textos são componentes MultiText
    (do overlayComponents_9) que o código posiciona e formata. O MultiText desfaz a escala que recebe: a caixa do texto
    tem 240 × _xscale de largura, a letra tem o tamanho do TextFormat do código e o _y do clipe é o meio da linha.

    A conversão põe a arte do PES na imagem do logo do FC (o clipe do logo vai para trás de tudo e a máscara dele cobre
    o placar inteiro), esconde as caixas e leva nomes, gols, relógio, cores e cartões para os lugares do PES — pelos
    lugares (x e largura) e pelas constantes do código (alturas, x do relógio e dos gols, fonte, tamanho e cor)."""
    tipo = "generic"
    precisa = G_PRECISA

    def __init__(self, ov):
        super().__init__(ov)
        # a imagem do logo do FC, dentro do mcLogoFc: é onde a arte do PES vai
        self.arte = self.imagem_em(G + ".mcLogoHolder.mcLogoFc")
        if not self.arte:
            raise ErroMolde("Esse Generic não tem a imagem do logo do FC (onde vai a arte do PES).")
        lg, bv = self.arte["lugar"], self.arte["caixa"]
        # mesmo formato do "fundo" do outro modelo (para a lista de moldes)
        self.fundo = {"w": self.arte["w"], "h": self.arte["h"],
                      "tela": _transformar_caixa(lg["mundo"], bv) if bv else (0, 0, 0, 0)}

    def descricao(self):
        f = self.fundo
        return {"fundo": {"w": f["w"], "h": f["h"], "tela": [round(v) for v in f["tela"]]}, "tipo": self.tipo,
                "campos": ["mcHomeTeamName", "mcAwayTeamName", "mcScoreHome", "mcScoreAway", "mcClockText"]}


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


def converter(pl, molde, S, constantes=None, numeros=None, textos=None):
    """Operações do Editor de Placares ({chave: op}) e um resumo do que foi feito.

    'constantes' são as constantes do código do molde ({nome: {slot, valor}}, do simulador do editor): algumas posições
    (o _x dos gols e do relógio, o _y dos cartões dos expulsos) são postas pelo código e só mudam por elas.
    'numeros' ({face, chave, avancos}): a fonte dos números do PES, já gravada como data/ui/fonts/<face>.ttf (família
    'chave' no FIFA.xml), para os gols e o relógio.
    'textos' (só o Generic): os formatos dos MultiText que o código cria, da simulação.
    """
    if isinstance(molde, MoldeGeneric):
        return converter_generic(pl, molde, S, constantes, numeros, textos)
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
        desce = 0.0
        if gols and numeros:
            # fonte do PES: os números ocupam 0,72 do tamanho (de 0,08 a 0,80 abaixo do topo da linha)
            altura = round(hl, 1)
            desce = 0.06 * hl
        campos = {"altura": altura, "cor": _cor_texto(pl, cx)}
        if gols:
            # o código do placar põe o _x dos gols (encostados no traço do meio): o campo fica alinhado como está e
            # largo, e as constantes abaixo levam cada número para o seu círculo
            campos["limites"] = [-2.0, -2.0, max(c["limites"][2], round(wl - 2, 2)), round(hl - 2, 2)]
            centros["altura_gols"] = altura
        else:
            campos.update(limites=[-2.0, -2.0, round(wl - 2, 2), round(hl - 2, 2)], alinh=2)
        op_place(lg, tx=[px + 2 * ma, py + 2 * md + desce * md])
        op_texto(lg["char"], **campos)
    resumo.append("Nomes dos times e placar levados para as caixas do PES.")
    # fonte dos números do PES: vai na fonte dos gols (que no molde do LTA é outra que a dos nomes) e o relógio passa a
    # usar essa mesma fonte
    fonte_num = None
    if numeros:
        cg = a.chars[molde.por_nome["txtTeamScoreHome"]["char"]]
        cn = a.chars[molde.por_nome["txtTeamNameHome"]["char"]]
        if cg.get("fonte") is not None and cg.get("fonte") != cn.get("fonte"):
            fonte_num = cg["fonte"]
            ops["fonte_char:%d" % fonte_num] = {"op": "fonte_char", "char": fonte_num, "nome": numeros["face"]}
            resumo.append("Gols e relógio com a fonte dos números do PES (%s)." % numeros["face"])
        else:
            resumo.append("O molde usa a mesma fonte para os nomes e os números: a fonte do PES não foi aplicada.")
    if "gols_casa" in centros and "gols_fora" in centros:
        # gols: o da casa termina em C - traço/2 - PADDING e o de fora começa em C + traço/2 + PADDING
        # (C = OFFSET + BOUND/2); com um dígito (~0,6 da altura) e o traço (~0,3 da altura dele), cada número fica no
        # meio do seu círculo
        hc, fc_ = centros["gols_casa"][0], centros["gols_fora"][0]
        bound = (constantes.get("WIDTH_SCORE_BOUND") or {}).get("valor", 119)
        dash = molde.por_nome.get("txtTeamScoreDash")
        alt_dash = (a.chars[dash["char"]].get("altura") if dash and a.chars[dash["char"]] else None) or 30
        av = (numeros or {}).get("avancos") if fonte_num is not None else None
        w_traco = (av.get("-", 0.3) if av else 0.3) * alt_dash
        w_digito = (av.get("0", 0.6) if av else 0.6) * centros["altura_gols"]
        pad = (fc_ - hc) / 2 - w_traco / 2 - w_digito / 2
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
        caixas = pl.caixas_relogio()
        ordem = [n for n in ("txtTenMin", "txtMin", "txtColon", "txtTenSec", "txtSec") if n in molde.por_nome]
        if fonte_num is not None and len(caixas) == len(ordem) == 5:
            # com a fonte do PES, cada dígito vai para a caixa do dígito do PES (o desenho dele é a altura dos números)
            Wc = mul((ma, 0.0, 0.0, md, tx[0], tx[1]), lc["pai"])
            iWc = inv(Wc)
            passo = None
            for n, (_nome, cxd) in zip(ordem, caixas):
                l = molde.por_nome[n]
                c = a.chars[l["char"]]
                R = tela(cxd)
                (lx0, ly0), (_lx1, ly1) = ponto(iWc, R[0], R[1]), ponto(iWc, R[2], R[3])
                lcx = ponto(iWc, (R[0] + R[2]) / 2, 0)[0]
                sa, sd = l["item"]["m"][0], l["item"]["m"][3]
                alt_n = round((ly1 - ly0) / sd / 0.72, 1)
                lim = c["limites"]
                nx = lcx - sa * (lim[0] + lim[2]) / 2
                ny = ly0 - sd * (lim[1] + 2 + 0.08 * alt_n)
                op_place(l, tx=[nx, ny])
                op_texto(l["char"], fonte=fonte_num, altura=alt_n, alinh=2)
                if n == "txtTenMin":
                    primeiro = (nx, ny, alt_n)
                elif n == "txtMin" and passo is None:
                    passo = nx - primeiro[0]
            lh = molde.por_nome.get("txtHundredMin")
            if lh and passo:
                op_place(lh, tx=[primeiro[0] - passo, primeiro[1]])
                op_texto(lh["char"], fonte=fonte_num, altura=primeiro[2], alinh=2)

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


# ------------------------------------------------------------------ a montagem nos moldes do jogo (Generic)

class Montagem:
    """As operações do Editor de Placares de uma conversão num molde em que o código põe as peças no lugar, com a
    matriz local de cada clipe já com as mudanças (as contas seguintes usam a posição nova)."""

    def __init__(self, molde, constantes=None):
        self.molde = molde
        self.P = molde.por_caminho
        self.constantes = constantes or {}
        self.ops, self.resumo, self.avisos = {}, [], []
        self.locais = {}                 # off do PlaceObject -> matriz local já com as mudanças

    def local_de(self, lg):
        return self.locais.get(lg["item"]["off"]) or _local(lg["item"])

    def mundo_cam(self, cam):
        M = afp.IDENT
        for i in range(1, len(cam) + 1):
            M = mul(self.local_de(self.P[".".join(cam[:i])]), M)
        return M

    def mundo(self, lg):
        return mul(self.local_de(lg), self.mundo_cam(lg["caminho"][:-1]))

    def place(self, lg, **campos):
        it = lg["item"]
        chave = "place:%d" % it["off"]
        atual = self.ops.get(chave) or {"op": "place", "off": it["off"]}
        atual.update(campos)
        self.ops[chave] = atual
        if "m" in campos or "tx" in campos:
            l = list(self.local_de(lg))
            if "m" in campos:
                l[0:4] = campos["m"]
            if "tx" in campos:
                l[4:6] = campos["tx"]
            self.locais[it["off"]] = tuple(l)

    def textura(self, char, img):
        ident, w, h = _salvar(img)
        self.ops["textura:%d" % char] = {"op": "textura", "char": char, "img": ident, "w": w, "h": h}

    def num(self, slot, valor, orig, nome=""):
        if not slot or not isinstance(orig, (int, float)) or str(slot).startswith("m:"):
            return False
        v = round(float(valor), 2)
        if abs(v - orig) > 1e-6:
            self.ops["const:" + slot] = {"op": "const", "slot": slot, "valor": v, "orig": orig, "nome": nome}
        return True

    def const(self, nome, valor):
        c = self.constantes.get(nome)
        if not c or not isinstance(c.get("valor"), (int, float)):
            self.avisos.append(nome)
            return False
        return self.num(c["slot"], valor, c["valor"], nome)

    def txt(self, slot, texto, orig):
        """Troca um texto usado pelo código (nome de fonte, cor do tema, alinhamento). 'slot' pode vir como
        "m:c:5046|COLOR_SAFE_BLACK" (membro de uma classe do jogo): o texto fica no c:5046."""
        if not slot:
            return False
        if str(slot).startswith("m:"):
            slot = slot[2:].split("|")[0]
        if texto != orig:
            self.ops["const_txt:" + slot] = {"op": "const_txt", "slot": slot, "texto": texto, "orig": orig}
        return True

    def codigo(self, pos, antes, depois, nome):
        """Troca bytes de uma instrução do código (o editor confere o que havia antes de trocar)."""
        self.ops["codigo:%d" % pos] = {"op": "codigo", "pos": pos, "antes": antes, "depois": depois, "nome": nome}

    def esconder(self, lg):
        it = lg["item"]
        tint = list(it["tint"]) if it["fl"] & apt.F_COR else [255, 255, 255, 255]
        self.place(lg, tint=tint[:3] + [0])

    def afastar(self, lg, eixo):
        """Leva o clipe para longe da tela num eixo que o código nunca mexe (para os que o código volta a mostrar)."""
        l = self.local_de(lg)
        self.place(lg, tx=[l[4] - 4000, l[5]] if eixo == "x" else [l[4], l[5] + 4000])

    def mapear(self, lg, B, R):
        """Lugar do clipe para o retângulo B (dele) cair no retângulo R da tela."""
        pai = self.mundo_cam(lg["caminho"][:-1])
        p0, p1 = ponto(inv(pai), R[0], R[1]), ponto(inv(pai), R[2], R[3])
        sa = (p1[0] - p0[0]) / max(1e-6, B[2] - B[0])
        sd = (p1[1] - p0[1]) / max(1e-6, B[3] - B[1])
        self.place(lg, m=[sa, 0.0, 0.0, sd], tx=[p0[0] - sa * B[0], p0[1] - sd * B[1]])

    def mascara(self, nome, R, folga=(3, 2)):
        lg = self.P.get(nome)
        B = self.molde.caixa_conteudo(lg) if lg else None
        if lg and B:
            self.mapear(lg, B, (R[0] - folga[0], R[1] - folga[1], R[2] + folga[0], R[3] + folga[1]))

    def multitext(self, lg, R, yc):
        """Põe um MultiText na caixa R da tela: a largura vem do _xscale (240 × escala), o _y é o meio da linha."""
        pai = self.mundo_cam(lg["caminho"][:-1])
        p0, p1 = ponto(inv(pai), R[0], R[1]), ponto(inv(pai), R[2], R[3])
        yl = ponto(inv(pai), 0, yc)[1]
        self.place(lg, m=[round((p1[0] - p0[0]) / MULTITEXT_LARGURA, 5), 0.0, 0.0, lg["item"]["m"][3]], tx=[p0[0], yl])
        return p0[0], yl


# ------------------------------------------------------------------ a conversão no Generic

def converter_generic(pl, molde, S, constantes=None, numeros=None, textos=None):
    """Operações do Editor de Placares para o molde Generic (ver MoldeGeneric) e um resumo do que foi feito."""
    textos = textos or {}
    M = Montagem(molde, constantes)
    constantes, P, ops, resumo, avisos, locais = M.constantes, M.P, M.ops, M.resumo, M.avisos, M.locais
    local_de, mundo_cam, mundo = M.local_de, M.mundo_cam, M.mundo
    op_place, op_textura, op_num, op_const, op_txt = M.place, M.textura, M.num, M.const, M.txt
    esconder, afastar, mapear, mascara, multitext = M.esconder, M.afastar, M.mapear, M.mascara, M.multitext

    def tela(cx):
        return _transformar_caixa(S, cx)

    def formato(caminho):
        return ((textos.get(caminho) or {}).get("config") or {})

    def cor_clipes(cams, caixa_pes):
        # a cor do texto (clara ou escura, pelo fundo da caixa do PES) vai pela cor dos próprios clipes: multiplica por
        # 0 e soma a cor. O código não pinta mais esses clipes, e a cor do TextFormat (uma cor do StyleManager) não
        # serve: no jogo o StyleManager não tem todas as cores do tema (COLOR_PURE_WHITE deu texto preto)
        cor = _cor_texto(pl, caixa_pes)
        for cam in cams:
            if cam in P:
                op_place(P[cam], tint=[0, 0, 0, 255], soma=list(cor[:3]) + [0])

    def fonte_num(cfg):
        f = cfg.get("formato") or {}
        if numeros and numeros.get("chave") and f.get("fonte_slot"):
            op_txt(f["fonte_slot"], numeros["chave"], f.get("fonte_chave"))
            return True
        return False

    def tamanho(cfg, valor):
        f = cfg.get("formato") or {}
        return op_num(f.get("tamanho_slot"), round(valor), f.get("tamanho"), "tamanho da letra")

    fundo_pes = pl.caixa_visivel(("fundo",))
    placa_pes = pl.caixa_visivel(("fundo", "cor_casa", "cor_fora")) or fundo_pes
    if not fundo_pes:
        raise ErroMolde("O placar do PES não tem desenho de fundo.")
    Rf, Rb = tela(fundo_pes), tela(placa_pes)

    # 0. o conteúdo (mcClassOverlay) desce até a altura em que os cartões da casa (que o código põe 30 px acima
    #    dele) ficam logo acima do placar
    lr = P[G]
    op_place(lr, tx=[local_de(lr)[4], round(Rb[1] + 22)])
    WR = mundo(lr)

    # 1. a arte do PES na imagem do logo do FC; o clipe do logo vai para trás das caixas e a máscara dele cobre a arte
    lh = P[G + ".mcLogoHolder"]
    irmaos = [l for l in molde.lugares if len(l["caminho"]) == 2 and l["caminho"][0] == G]
    frente = [l["item"]["prof"] for l in irmaos if l is not lh and l["nome"] not in ("mcAggScore", "mcClockBg")]
    usadas = {l["item"]["prof"] for l in irmaos}
    faixas = [(l["item"]["prof"], l["item"]["clip"]) for l in irmaos if l["item"]["fl"] & apt.F_RECORTE]
    prof = next((d for d in range(min(frente) - 1, 0, -1)
                 if d not in usadas and not any(p < d <= c for p, c in faixas)), None) if frente else None
    if prof is None:
        raise ErroMolde("Não achei uma profundidade livre para pôr a arte do PES atrás do Generic.")
    op_place(lh, prof=prof)
    lf = P[G + ".mcLogoHolder.mcLogoFc"]
    yfc = (constantes.get("ANIM_IN_LOGO_FC_Y_POS") or {}).get("valor")
    if isinstance(yfc, (int, float)):          # onde o código deixa o logo no fim da entrada
        l = list(local_de(lf))
        l[5] = yfc
        locais[lf["item"]["off"]] = tuple(l)
    arte = molde.arte
    mapear(arte["lugar"], arte["caixa"], Rf)
    Wforma = mundo(arte["lugar"])
    k = min(2.0, 2048.0 / max(Rf[2] - Rf[0], Rf[3] - Rf[1]))
    wi, hi = max(8, int(round((Rf[2] - Rf[0]) * k))), max(8, int(round((Rf[3] - Rf[1]) * k)))
    Tn = mul(tuple(arte["item"]["m"]), (wi / arte["w"], 0.0, 0.0, hi / arte["h"], 0.0, 0.0)) if arte["w"] else \
        tuple(arte["item"]["m"])
    op_textura(arte["char"], pl.desenhar(("fundo",), mul(mul(S, inv(Wforma)), Tn), wi, hi))
    mascara(G + ".mcLogoHolder.mcLogoMask", Rf, (1, 1))
    resumo.append("Arte do PES na imagem do logo do FC (%d×%d), atrás dos textos." % (wi, hi))

    # 2. as caixas e decorações do Generic somem: transparentes e, as que o código volta a mostrar (o _alpha do "on
    #    fire", as cores dos fios), também longe da tela ou fora da máscara delas
    for cam in G_ESCONDER:
        if cam in P:
            esconder(P[cam])
    for cam, eixo in G_AFASTAR:
        if cam in P:
            afastar(P[cam], eixo)
    resumo.append("Caixas, título, escudos e ícones do Generic escondidos.")
    # o código pinta o logo do FC (a arte) e os textos com cor chapada: essas chamadas deixam de fazer efeito
    desligadas = set()
    for alvo, slot in molde.pinturas:
        if alvo in G_SEM_PINTURA and alvo != "mcExtraTime" and slot:      # os acréscimos: no passo 7
            op_txt(slot, PINTURA_DESLIGADA, PINTURA)
            desligadas.add(alvo)
    if "m_mcLogoFc" in desligadas:
        resumo.append("O código do Generic não pinta mais a arte nem os textos com a cor da competição: ficam com as "
                      "cores do PES.")
    else:
        avisos.append("Não achei no código do Generic a pintura do logo do FC: no jogo a arte pode ficar com uma cor só.")

    # 3. nomes: o x e a largura pelo lugar; a altura pelas constantes do código; centralizados
    cfg_nome = formato(G + ".mcTeamHolder.mcHomeTeamName")
    alt_nomes = [tela(c)[3] - tela(c)[1] for c in (pl.caixa_campo("nome_casa"), pl.caixa_campo("nome_fora")) if c]
    tam_nome = round(min(alt_nomes) * 0.72) if alt_nomes else None
    y_nome = {}
    for campo, nome, cte, msc in (("nome_casa", "mcHomeTeamName", "ANIMATE_IN_TEAM_NAME_HOME_Y", "mcTeamHomeMask"),
                                  ("nome_fora", "mcAwayTeamName", "ANIMATE_IN_TEAM_NAME_AWAY_Y", "mcTeamAwayMask")):
        lg = P[G + ".mcTeamHolder." + nome]
        cx = pl.caixa_campo(campo)
        if not cx:
            esconder(lg)
            continue
        R = tela(cx)
        x0, yl = multitext(lg, R, (R[1] + R[3]) / 2 + 0.06 * (tam_nome or 0))
        cor_clipes([G + ".mcTeamHolder." + nome], cx)
        op_const(cte, yl)
        y_nome[campo] = (yl, x0)
        mascara(G + ".mcTeamHolder." + msc, R)
    if "nome_casa" in y_nome:                  # nomes de 15 letras: o código põe os dois nesse x
        op_const("ANIM_IN_TEAM_NAME_X_POS", y_nome["nome_casa"][1])
    if tam_nome:
        tamanho(cfg_nome, tam_nome)
    partes = cfg_nome.get("partes") or []
    if "H_ALIGN_LEFT" in partes and cfg_nome.get("partes_slots"):
        op_txt(cfg_nome["partes_slots"][partes.index("H_ALIGN_LEFT")], "H_ALIGN_CENTER", "H_ALIGN_LEFT")
    resumo.append("Nomes dos times nas caixas do PES (letra %s px, centralizados)." % tam_nome)

    # 4. gols: o mcScoreHolder fica no x do código (INIT_SCORE_NORMAL_X_POS) e na altura que faz o _y do gol de fora —
    #    a mesma constante do nome de fora — cair no meio da caixa do gol de fora
    ls = P[G + ".mcScoreHolder"]
    cfg_gol = formato(G + ".mcScoreHolder.mcScoreHome")
    cgc, cgf = pl.caixa_campo("gols_casa"), pl.caixa_campo("gols_fora")
    if cgc and cgf:
        Rgc, Rgf = tela(cgc), tela(cgf)
        hg = min(Rgc[3] - Rgc[1], Rgf[3] - Rgf[1])
        tam_gol = round(hg if numeros else hg * 0.86)
        desce = 0.06 * tam_gol
        xs = round(min(Rgc[0], Rgf[0]) - WR[4])
        c_fora = y_nome.get("nome_fora", (None,))[0]
        if c_fora is None:
            c_fora = (constantes.get("ANIMATE_IN_TEAM_NAME_AWAY_Y") or {}).get("valor", 0)
        ys = (Rgf[1] + Rgf[3]) / 2 + desce - c_fora - WR[5]
        op_place(ls, tx=[xs, ys])
        op_const("INIT_SCORE_NORMAL_X_POS", xs)
        _x, y_casa = multitext(P[G + ".mcScoreHolder.mcScoreHome"], Rgc, (Rgc[1] + Rgc[3]) / 2 + desce)
        multitext(P[G + ".mcScoreHolder.mcScoreAway"], Rgf, (Rgf[1] + Rgf[3]) / 2 + desce)
        op_const("ANIMATE_IN_SCORE_HOME_Y", y_casa)
        mascara(G + ".mcScoreHolder.mcScoreMask", Rgc)
        mascara(G + ".mcScoreHolder.mcScoreMaskAway", Rgf)
        tamanho(cfg_gol, tam_gol)
        cor_clipes([G + ".mcScoreHolder.mcScoreHome"], cgc)
        cor_clipes([G + ".mcScoreHolder.mcScoreAway"], cgf)
        if fonte_num(cfg_gol):
            resumo.append("Gols com a fonte dos números do PES (%s)." % numeros["face"])
        resumo.append("Gols nas caixas do PES (letra %d px)." % tam_gol)

    # 5. cores dos times: as faixas do Generic (dentro do mcScoreHolder) nas placas de cor do PES
    for papel, nome in (("cor_casa", "mcColorHome"), ("cor_fora", "mcColorAway")):
        lg = P.get(G + ".mcScoreHolder." + nome)
        vis = pl.caixa_visivel((papel,))
        if not lg:
            continue
        B = molde.caixa_conteudo(lg)
        if not vis or not B:
            esconder(lg)
            continue
        mapear(lg, B, tela(vis))
    resumo.append("Faixas das cores dos times nas placas de cor do PES.")

    # 6. relógio: o mcClockText vai para a caixa do relógio do PES (o x é TIMER_X_POS, o y ANIMATE_IN_CLOCK_TEXT_Y) e
    #    cada dígito para a caixa do dígito do PES
    lk = P[G + ".mcClockText"]
    cfg_rel = formato(G + ".mcClockText.txtTenMin")
    cxr = pl.caixa_campo("relogio")
    if cxr:
        Rk = tela(cxr)
        dig = [tela(c) for _n, c in pl.caixas_relogio()]
        if numeros and len(dig) == 5:
            tam_rel = round(sorted(d[3] - d[1] for d in dig)[2] / 0.72)
        else:
            w5 = (Rk[2] - Rk[0]) / 5
            dig = [(Rk[0] + i * w5, Rk[1], Rk[0] + (i + 1) * w5, Rk[3]) for i in range(5)]
            tam_rel = round((Rk[3] - Rk[1]) * 0.72)
        desce = 0.06 * tam_rel
        xk, yk = round(Rk[0] - WR[4]), round((Rk[1] + Rk[3]) / 2 - WR[5])
        x4 = (constantes.get("TIMER_X_POS") or {}).get("valor")
        x5 = (constantes.get("TIMER_X_POS_FIVE_NUMBER") or {}).get("valor")
        op_place(lk, m=[1.0, 0.0, 0.0, 1.0], tx=[xk, yk])
        op_const("TIMER_X_POS", xk)
        op_const("ANIMATE_IN_CLOCK_TEXT_Y", yk)
        for nome, R in zip(G_DIGITOS, dig):
            if G + ".mcClockText." + nome in P:
                multitext(P[G + ".mcClockText." + nome], R, (R[1] + R[3]) / 2 + desce)
        passo = dig[1][0] - dig[0][0]
        lc = P.get(G + ".mcClockText.txtHundredMin")
        if lc:
            d0 = dig[0]
            multitext(lc, (d0[0] - passo, d0[1], d0[2] - passo, d0[3]), (d0[1] + d0[3]) / 2 + desce)
        if isinstance(x4, (int, float)) and isinstance(x5, (int, float)):
            # 5 dígitos (100 minutos ou mais): o relógio anda para a esquerda na mesma proporção do Generic
            op_const("TIMER_X_POS_FIVE_NUMBER", xk + (x5 - x4) * passo / 15.0)
        mascara(G + ".mcClockMask", (Rk[0] - passo, Rk[1], Rk[2], Rk[3]))
        tamanho(cfg_rel, tam_rel)
        cor_clipes([G + ".mcClockText"], cxr)
        if fonte_num(cfg_rel):
            resumo.append("Relógio com a fonte dos números do PES.")
        resumo.append("Relógio na caixa do relógio do PES (letra %d px)." % tam_rel)

        # 7. acréscimos: o "+3" (mesmo formato do relógio) na caixa de acréscimos do PES; a placa dos acréscimos do PES
        #    não entra (o Generic não tem onde mostrar uma imagem só nos acréscimos)
        le = P.get(G + ".mcExtraTime")
        cxa = pl.caixa_campo("acrescimos")
        if le and cxa:
            Ra = tela(cxa)
            sob = max(0, min(Ra[2], Rk[2]) - max(Ra[0], Rk[0])) * max(0, min(Ra[3], Rk[3]) - max(Ra[1], Rk[1]))
            if sob > 0.3 * (Ra[2] - Ra[0]) * (Ra[3] - Ra[1]):
                # no PES a placa dos acréscimos cobre o relógio; sem a placa, o "+3" iria em cima dos números: vai
                # logo abaixo do relógio
                Ra = (Rk[0], Rk[3] + 2, Rk[0] + (Ra[2] - Ra[0]), Rk[3] + 2 + (Rk[3] - Rk[1]))
                avisos.append("Os acréscimos do PES ficam em cima do relógio: o \"+3\" foi para logo abaixo dele.")
            av = (numeros or {}).get("avancos") or {}
            larg = (av.get("+", 0.6) + av.get("0", 0.6)) * tam_rel
            x_ini = (Ra[0] + Ra[2]) / 2 - larg / 2
            xe, ye = multitext(le, (x_ini, Ra[1], x_ini + max(larg + 8, Ra[2] - x_ini), Ra[3]),
                               (Ra[1] + Ra[3]) / 2 + desce)
            e0 = (constantes.get("EXTRA_TIME_INIT_X_POS") or {}).get("valor")
            e1 = (constantes.get("EXTRA_TIME_X_POS") or {}).get("valor")
            op_const("EXTRA_TIME_X_POS", xe)
            if isinstance(e0, (int, float)) and isinstance(e1, (int, float)):
                op_const("EXTRA_TIME_INIT_X_POS", xe + (e0 - e1))
            mascara(G + ".mcExtraTimeMask", Ra)
            avisos.append("A placa dos acréscimos do PES não aparece no Generic: só o \"+3\", no lugar dela.")
            # em cima da arte do PES, o "+3" fica com a cor do relógio (a do PES); fora dela, sobre o gramado, com a cor
            # que o código do Generic dá (a do tema da competição)
            if Rf[0] <= Ra[0] and Ra[2] <= Rf[2] and Rf[1] <= Ra[1] and Ra[3] <= Rf[3]:
                for alvo, slot in molde.pinturas:
                    if alvo == "mcExtraTime" and slot:
                        op_txt(slot, PINTURA_DESLIGADA, PINTURA)
                cor_clipes([G + ".mcExtraTime"], cxr)

    # 8. cartões: como no Generic, uma faixa de 10 px para cada time — a da casa logo acima do placar, a de fora logo
    #    abaixo —, com os vermelhos e os dos expulsos a partir do começo do nome. O código põe os da casa em -30 e -33
    #    (ANIM_INIT_SCORE_X_POS e ANIM_INIT_CARD_AWAY_Y_POS, que ficam) e os de fora em ANIM_IN_CARD_Y_POS e
    #    ANIM_INIT_CARD_Y_POS (que vão para baixo do placar)
    a_cartao = (constantes.get("ANIM_INIT_SCORE_X_POS") or {}).get("valor", 30)
    a_expulso = (constantes.get("ANIM_INIT_CARD_AWAY_Y_POS") or {}).get("valor", 33)
    y_exp_fora = Rb[3] + 2 - WR[5]
    op_const("ANIM_INIT_CARD_Y_POS", y_exp_fora)
    op_const("ANIM_IN_CARD_Y_POS", y_exp_fora + (a_expulso - a_cartao))
    for campo, cartoes, expulsos, msc, y_exp in (
            ("nome_casa", "mcHomeCard", "mcEjectHome", "mcHomeCardMask", WR[5] - a_expulso),
            ("nome_fora", "mcAwayCard", "mcEjectAway", "mcAwayCardMask", WR[5] + y_exp_fora)):
        cn = pl.caixa_campo(campo)
        if not cn:
            continue
        xn = tela(cn)[0]
        for n in (cartoes, expulsos):
            lg = P.get(G + "." + n)
            if lg:
                op_place(lg, tx=[xn - WR[4] - (1 if n == cartoes else 0), local_de(lg)[5]])
        mascara(G + "." + msc, (xn - 6, y_exp - 1, xn + 63, y_exp + 9), (0, 0))
    resumo.append("Cartões dos expulsos e vermelhos: os da casa logo acima do placar, os de fora logo abaixo.")

    # 9. placar agregado (jogos de ida e volta): à direita do placar, da mesma altura
    la = P.get(G + ".mcAggScore")
    if la:
        Bm = molde.caixa_conteudo(P[G + ".mcAggScore.mcAggMask"]) if G + ".mcAggScore.mcAggMask" in P else None
        alt = (Bm[3] - Bm[1]) * P[G + ".mcAggScore.mcAggMask"]["item"]["m"][3] if Bm else 56.0
        ka = (Rb[3] - Rb[1]) / max(1.0, alt)
        xa = round(Rb[2] + 4 - WR[4])
        op_place(la, m=[ka, 0.0, 0.0, ka], tx=[xa, Rb[1] - WR[5]])
        op_const("INIT_AGG_SCORE_NORMAL_X_POS", xa)

    falta = [n for n in dict.fromkeys(avisos) if n.isupper()]
    if falta:
        resumo.append("Constantes que o código do molde não tem (ficaram como estavam): " + ", ".join(falta) + ".")
    resumo += [n for n in dict.fromkeys(avisos) if not n.isupper()]
    return ops, resumo


# ------------------------------------------------------------------ a substituição (Generic/overlay_9021)

SU = G + ".mcMoreSubsLT"
SU_PRECISA = tuple(SU + s for s in ("", ".mcMiddleVector", ".mcVectorsMask", ".mtPlayersIn", ".mtPlayersOut",
                                    ".mtPlayersInAway", ".mtPlayersOutAway", ".mcTeamCrest", ".mcTeamCrest.mcLogo",
                                    ".mcTeamCrest.mcMask", ".mtPlayersIn.mcText", ".mtPlayersIn.mcNumber"))
# fundos do painel (pintados pelo código), o fio, a textura do Ultimate Team e as setas do FC (as do PES vêm na arte)
SU_ESCONDER = ("mcBackground", "mcWipe", "mcContainer", "mcLine", "mcTexture", "mcGreenArrow", "mcRedArrow",
               "mcTeamCrest.mcBg")
SU_AFASTAR = ("mcBackground", "mcWipe", "mcContainer", "mcLine", "mcTeamCrest.mcBg")      # o código só mexe no _y
# a pintura chapada do Init: na arte (vira silhueta) e nos fundos escondidos (a cor nova traria o alpha de volta)
SU_SEM_PINTURA = tuple("mcMoreSubsLT." + n for n in ("mcMiddleVector", "mcBackground", "mcWipe", "mcContainer",
                                                    "mcLine", "mcTeamCrest.mcBg", "mcGreenArrow.mcBGArrow",
                                                    "mcRedArrow.mcBGArrow"))
SU_LINHAS = (("entra", ("mtPlayersIn", "mtPlayersInAway"), "INIT_TEXTS_IN_POS", "ANIM_TEXTS_IN_TWO_POS"),
             ("sai", ("mtPlayersOut", "mtPlayersOutAway"), "INIT_TEXTS_OUT_POS", "ANIM_TEXTS_OUT_TWO_POS"))
ANIMATE_DESLIGADO = "Animate_PES"


class MoldeSubst(MoldeCodigo):
    """A substituição do Generic do jogo (data/ui/game/overlays/Generic/overlay_9021.big).

    Com duas ou mais trocas o código mostra o painel mcMoreSubsLT: fundos chapados que descem, a imagem
    mcMiddleVector revelada pela máscara mcVectorsMask, o escudo do time, as setas e as linhas de quem entra e de quem
    sai (mtPlayersIn/Out, instâncias do símbolo mcPlayerRowText com o número e o nome em MultiText; as outras trocas
    viram linhas novas presas nelas). Com uma troca só, ele esconde o painel e mostra duas tarjas do componente
    LowerThird, que outras telas do jogo também usam: a conversão faz o painel aparecer também nesse caso."""
    tipo = "subst"
    precisa = SU_PRECISA

    def __init__(self, ov):
        super().__init__(ov)
        self.arte = self.imagem_em(SU + ".mcMiddleVector")
        if not self.arte:
            raise ErroMolde("Essa substituição do FC não tem a imagem do painel (mcMiddleVector), onde vai a arte do PES.")
        self.fundo = {"w": self.arte["w"], "h": self.arte["h"], "tela": (0, 0, 0, 0)}

    def descricao(self):
        return {"tipo": self.tipo, "campos": ["mtPlayersIn", "mtPlayersOut", "mcTeamCrest"]}

    def _funcao(self, nome):
        return next((f for f in self.funcoes if f["nome"] == nome), None)

    def byte_uma_troca(self):
        """Posição do 1 de "nSubsCount > 1" no SetData (o que escolhe entre as tarjas e o painel), ou None."""
        from nucleo import as2
        fn = self._funcao("SetData")
        reg = next((r for r, n in (fn or {}).get("pars", ()) if n == "nSubsCount"), None)
        if not fn or not reg:
            return None
        d = self.a.d
        p, ant = fn["inicio"], []
        while p < fn["fim"]:
            op, arg, q = as2.decodificar(d, p)
            ant = (ant + [(op, arg, p)])[-3:]
            if len(ant) == 3 and ant[0][:2] == (0xB9, reg) and ant[1][0] == 0x5A and ant[2][0] == 0x67:
                return ant[1][2]
            p = q
        return None

    def rolagens(self):
        """Slots do nome do método das chamadas de Animate da entrada que rolam as linhas quando a quantidade de trocas
        não é 2 nem 3 (destino com ROW_HEIGHT): com uma troca, levariam a linha para o lugar da terceira."""
        out = []
        for ch in self.chamadas:
            if ch["funcao"] != "AnimateIn" or ch["nome"] != "Animate" or len(ch["args"]) < 3:
                continue
            alvo = str(ch["args"][0]["cam"] or "")
            if alvo.rsplit(".", 1)[-1] in ("mtPlayersIn", "mtPlayersOut", "mtPlayersInAway", "mtPlayersOutAway") and \
                    "ROW_HEIGHT" in ch["args"][2]["refs"] and ch["slot_nome"]:
                out.append(ch["slot_nome"])
        return out


def converter_subst(sp, molde, S=None, constantes=None, formatos=None):
    """Operações do Editor de Placares para a substituição do Generic (MoldeSubst) com a tela da substituição do PES
    (pes.SubstPes) e um resumo. 'S' leva o filme do PES para a tela do FC (sem ela, as mesmas coordenadas: o PES
    também desenha a substituição numa tela de 1920×1080). 'formatos': os TextFormat do código (da simulação)."""
    S = S or afp.IDENT
    M = Montagem(molde, constantes)
    P = M.P

    def tela(cx):
        return _transformar_caixa(S, cx)

    fundo, ce, cs = sp.caixa_visivel(("fundo",)), sp.caixa_campo("entra"), sp.caixa_campo("sai")
    if not fundo or not ce or not cs:
        raise ErroMolde("A substituição do PES não tem a placa ou as caixas de quem entra e de quem sai.")
    Ra, Re, Rs = tela(fundo), tela(ce), tela(cs)
    painel = P[SU]
    iWP = inv(M.mundo(painel))

    # 0. o painel também com uma troca só: o "nSubsCount > 1" do SetData vira "> 0" (com uma troca o FC mostraria as
    #    tarjas do LowerThird, um componente que as outras telas também usam)
    pos = molde.byte_uma_troca()
    if pos is None:
        raise ErroMolde("Não achei no código da substituição onde ele escolhe entre as tarjas e o painel.")
    M.codigo(pos, "5a", "59", "painel também com uma troca (nSubsCount > 0)")
    #    e a entrada não rola as linhas: com uma troca (ou mais de 3) o código chamaria um segundo Animate que leva a
    #    primeira linha para outro lugar; essas chamadas passam a chamar um método que não existe
    rol = molde.rolagens()
    for slot in rol:
        M.txt(slot, ANIMATE_DESLIGADO, "Animate")
    if len(rol) != 4:
        M.avisos.append("O código da entrada da substituição não é o esperado: com uma troca a linha pode não ficar na "
                        "caixa do PES.")

    # 1. a arte do PES (placa e setas) na imagem do mcMiddleVector, revelada pela máscara mcVectorsMask, que desce
    arte = molde.arte
    M.mapear(arte["lugar"], arte["caixa"], Ra)
    Wf = M.mundo(arte["lugar"])
    k = min(2.0, 2048.0 / max(Ra[2] - Ra[0], Ra[3] - Ra[1]))
    wi, hi = max(8, int(round((Ra[2] - Ra[0]) * k))), max(8, int(round((Ra[3] - Ra[1]) * k)))
    Tn = mul(tuple(arte["item"]["m"]), (wi / arte["w"], 0.0, 0.0, hi / arte["h"], 0.0, 0.0)) if arte["w"] else \
        tuple(arte["item"]["m"])
    M.textura(arte["char"], sp.desenhar(("fundo",), mul(mul(S, inv(Wf)), Tn), wi, hi))
    lvm, bvm = molde.forma_em(P[SU + ".mcVectorsMask"])
    if lvm:
        M.mapear(lvm, bvm, (Ra[0] - 1, Ra[1] - 1, Ra[2] + 1, Ra[3] + 1))
    alt = Ra[3] - Ra[1]
    ch = (M.constantes.get("CONTENT_HEIGHT") or {}).get("valor")
    if isinstance(ch, (int, float)) and ch < alt + 4:              # o quanto a máscara sobe antes de descer
        M.const("CONTENT_HEIGHT", round(alt + 4))
    M.resumo.append("Arte da substituição do PES (%d×%d) na imagem do painel, revelada de cima para baixo." % (wi, hi))

    # 2. o que o Generic desenha some: os fundos chapados, o fio, a textura do Ultimate Team e as setas
    for n in SU_ESCONDER:
        if SU + "." + n in P:
            M.esconder(P[SU + "." + n])
    for n in SU_AFASTAR:
        if SU + "." + n in P:
            M.afastar(P[SU + "." + n], "x")
    desligadas = set()
    for alvo, slot in molde.pinturas:
        if alvo in SU_SEM_PINTURA and slot:
            M.txt(slot, PINTURA_DESLIGADA, PINTURA)
            desligadas.add(alvo)
    if "mcMoreSubsLT.mcMiddleVector" not in desligadas:
        M.avisos.append("Não achei no código a pintura da imagem do painel: no jogo a arte pode ficar com uma cor só.")

    # 3. o escudo do time na caixa do escudo do PES: o código carrega o escudo com CREST_SIZE de lado e o faz subir
    #    até -ANIM_IN_LOGO_Y_POS; o mcTeamCrest vai para o lugar em que isso cai na caixa, e a máscara dele cobre a caixa
    lt, ll = P[SU + ".mcTeamCrest"], P[SU + ".mcTeamCrest.mcLogo"]
    cesc = sp.caixa_escudo()
    y_logo = (M.constantes.get("ANIM_IN_LOGO_Y_POS") or {}).get("valor")
    if cesc and isinstance(y_logo, (int, float)):
        R = tela(cesc)
        lado = int(round(min(R[2] - R[0], R[3] - R[1])))
        x0, y0 = (R[0] + R[2] - lado) / 2, (R[1] + R[3] - lado) / 2
        px, py = ponto(iWP, x0, y0)
        x_logo = M.local_de(ll)[4]
        M.place(lt, tx=[round(px - x_logo, 2), round(py + y_logo, 2)])
        M.const("CREST_SIZE", max(8, min(127, lado)))
        M.mascara(SU + ".mcTeamCrest.mcMask", (x0, y0, x0 + lado, y0 + lado), (1, 1))
        M.resumo.append("Escudo do time na caixa do escudo do PES (%d px)." % lado)
    else:
        M.esconder(lt)
        M.resumo.append("A substituição do PES não tem caixa de escudo: o escudo do FC fica escondido.")

    # 4. quem entra e quem sai nas caixas do PES. As linhas são instâncias do mesmo símbolo (número à direita numa
    #    caixa estreita, nome à esquerda ao lado): a origem da linha fica no começo da caixa do PES e no meio da linha;
    #    o _y das linhas vem das constantes (iguais com 1, 2 ou 3 trocas); a cor de cada grupo vai pela cor do clipe do
    #    grupo (multiplica 0 e soma a cor), por cima da pintura do código
    h = min(Re[3] - Re[1], Rs[3] - Rs[1])
    s = int(round(0.72 * h))
    wn, gap, pad = 1.3 * s, 0.4 * s, 0.2 * s
    largura = min(Re[2] - Re[0], Rs[2] - Rs[0]) - 2 * pad
    lnum, lnome = P[SU + ".mtPlayersIn.mcNumber"], P[SU + ".mtPlayersIn.mcText"]
    M.place(lnum, m=[round(wn / MULTITEXT_LARGURA, 5), 0.0, 0.0, lnum["item"]["m"][3]], tx=[0.0, 0.0])
    M.place(lnome, m=[round(max(20.0, largura - wn - gap) / MULTITEXT_LARGURA, 5), 0.0, 0.0, lnome["item"]["m"][3]],
            tx=[round(wn + gap, 2), 0.0])
    for campo, nomes, c_tres, c_duas in SU_LINHAS:
        cx = sp.caixa_campo(campo)
        R = tela(cx)
        cor = CLARO if _cor_texto_tela(sp, cx) == CLARO else ESCURO
        px, py = ponto(iWP, R[0] + pad, (R[1] + R[3]) / 2 + 0.06 * s)
        y = int(round(py))
        for n in nomes:
            M.place(P[SU + "." + n], tx=[round(px, 2), float(y)], tint=[0, 0, 0, 255], soma=cor[:3] + [0])
        M.const(c_tres, y)
        M.const(c_duas, y)
        mk = molde.mascara_de(P[SU + "." + nomes[0]])
        if mk:
            B = _caixa_vertices(molde.geo.get(mk["char"], []))
            if B:
                M.mapear(mk, B, (R[0] - 2, R[1] - 2, R[2] + 2, R[3] + 2))
    # as trocas a mais (2 ou 3 de uma vez) viram linhas abaixo da primeira: ficam fora da máscara, porque a placa do
    # PES só tem lugar para uma; ROW_HEIGHT × 3 é o quanto as linhas sobem na saída (e saem da máscara)
    M.const("ROW_COMMON_HEIGHT", min(127, int(round(h + 8))))
    M.const("CONTAINER_ROW_HEIGHT", min(127, int(round(2 * (h + 8)))))
    M.const("ROW_HEIGHT", min(127, int(round((h + 8) / 3.0)) + 1))
    nome_f = next((f for f in formatos or () if f.get("fonte_chave") == "FONT_NAME_BOLD"), None)
    num_f = next((f for f in formatos or () if "DIGITS" in str(f.get("fonte_chave") or "")), None)
    for f in (nome_f, num_f):
        if f and f.get("tamanho_slot"):
            M.num(f["tamanho_slot"], max(8, min(127, s)), f.get("tamanho"), "tamanho da letra")
    if not (nome_f and num_f):
        M.avisos.append("Não achei no código o tamanho das letras da substituição: ficou o do FC.")
    M.resumo.append("Quem entra e quem sai nas caixas do PES (letra %d px), com a cor de cada caixa." % s)
    M.resumo.append("Com 2 ou 3 trocas de uma vez, aparecem a primeira que entra e a primeira que sai (a placa do PES "
                    "tem lugar para uma).")
    if sp.campo_na_placa("titulo"):
        M.resumo.append("A faixa do título da substituição do PES fica sem texto (o FC não escreve título nessa tela).")
    falta = [n for n in dict.fromkeys(M.avisos) if n.isupper()]
    if falta:
        M.resumo.append("Constantes que o código da substituição não tem (ficaram como estavam): " + ", ".join(falta) + ".")
    M.resumo += [n for n in dict.fromkeys(M.avisos) if not n.isupper()]
    return M.ops, M.resumo


def _cor_texto_tela(tl, caixa):
    lum = tl.luminancia(caixa, ("fundo",))
    return ESCURO if lum is not None and lum > 0.55 else CLARO


def classe_do_overlay(ov):
    """Nome completo da classe do overlay (o do símbolo __Packages.… exportado), ou None."""
    for e in ov.apt.exports:
        if e["nome"].startswith("__Packages."):
            return e["nome"][len("__Packages."):]
    return None


def _item_do_slot(ov, consts, slot):
    """O item da tabela de constantes que um texto do código lê ("c:N", "pk:pos:pool" ou "pkw:pos:pool"), ou None."""
    import struct
    from nucleo import as2
    d = bytes(ov.apt.d)
    tipo, _, resto = str(slot or "").partition(":")

    def pool(pool_pos):
        p_cnt = (pool_pos + 1 + 7) // 8 * 8
        cnt, ptr = struct.unpack_from("<QQ", d, p_cnt)
        return list(struct.unpack_from("<%dQ" % cnt, d, ptr))
    try:
        if tipo == "c":
            n = int(resto)
            t, v = consts.item(n)
            if t == as2.T_TEXTO:
                return n
            if t == as2.T_LOOKUP:
                pp = as2._pool_do_slot(d, consts, n)
                return pool(pp)[v] if pp is not None else None
        elif tipo in ("pk", "pkw"):
            pos_s, _, pool_s = resto.partition(":")
            pos = int(pos_s)
            k = d[pos] if tipo == "pk" else struct.unpack_from("<H", d, pos)[0]
            return pool(int(pool_s))[k]
    except (ValueError, IndexError, struct.error):
        return None
    return None


def ops_renomear_classe(ov, novo):
    """Operações que dão o nome curto 'novo' à classe do overlay (game.overlays.Generic.<novo>).

    O jogo define cada classe uma vez só (o código pula a definição se ela já existe): uma cópia modificada de um
    overlay do jogo gravada em outro arquivo precisa de um nome próprio, senão vale a que carregar primeiro e a outra
    roda com o código errado. Mudam: o nome curto em todo o código (a definição e as constantes da classe), o nome
    completo que o registerClass usa (o do símbolo e o caminho da classe, no mesmo texto) e o nome exportado do clipe
    da classe, que precisa ser igual ao do registerClass. O nome que o construtor passa para a classe base
    (Initialize) fica como está. Devolve {} se o overlay não tiver classe ou o código não for o esperado."""
    from nucleo import as2
    cheio = classe_do_overlay(ov)
    curto = (cheio or "").rpartition(".")[2]
    if not curto or novo == curto:
        return {}
    novo_cheio = cheio[:-len(curto)] + novo
    consts = as2.Constantes(ov.entrada("1"))
    try:
        chamadas = ler_chamadas(ov)[0]
    except Exception:  # noqa: BLE001  (código diferente do esperado: fica com o nome que tem)
        return {}
    if not any(c["nome"] == "registerClass" and c["args"] and c["args"][0]["v"] == cheio for c in chamadas):
        return {}
    manter = {_item_do_slot(ov, consts, c["args"][0]["slot"]) for c in chamadas
              if c["nome"] == "Initialize" and c["args"] and c["args"][0]["v"] == cheio}
    ops = {}
    for i in range(consts.n):
        t, v = consts.item(i)
        if t != as2.T_TEXTO:
            continue
        txt = consts.texto(v)
        if txt == curto or (txt == cheio and i not in manter):
            ops["const_txt:c:%d" % i] = {"op": "const_txt", "slot": "c:%d" % i, "texto": novo if txt == curto else novo_cheio,
                                         "orig": txt, "nome": "nome da classe"}
    if not any(op["texto"] == novo for op in ops.values()) or not any(op["texto"] == novo_cheio for op in ops.values()):
        return {}
    ops["export:" + cheio] = {"op": "export", "antes": cheio, "nome": novo_cheio}
    return ops


def previa_subst(sp, S=None, largura=1920, altura=1080, recorte=True):
    """A substituição do PES na tela do FC, com nomes de exemplo nas caixas (o jogo escreve os de verdade)."""
    from PIL import ImageDraw, ImageFont
    S = S or afp.IDENT
    img = sp.desenhar(("fundo",), S, largura, altura, fundo=(30, 96, 52, 255))
    dr = ImageDraw.Draw(img)
    for campo, num, nome in (("entra", "10", "KUBO"), ("sai", "7", "NAKAMURA")):
        cx = sp.caixa_campo(campo)
        if not cx:
            continue
        R = _transformar_caixa(S, cx)
        s = max(8, int(round(0.72 * (R[3] - R[1]))))
        try:
            fonte = ImageFont.truetype("arialbd.ttf", s)
        except OSError:
            fonte = ImageFont.load_default()
        cor = tuple(_cor_texto_tela(sp, cx))
        yc = (R[1] + R[3]) / 2
        x = R[0] + 0.2 * s
        dr.text((x + 1.3 * s, yc), num, fill=cor, font=fonte, anchor="rm")
        dr.text((x + 1.7 * s, yc), nome, fill=cor, font=fonte, anchor="lm")
    if recorte:
        cx = _transformar_caixa(S, sp.caixa_visivel(("fundo",)))
        m = 24
        img = img.crop((max(0, int(cx[0]) - m), max(0, int(cx[1]) - m), min(largura, int(cx[2]) + m),
                        min(altura, int(cx[3]) + m)))
    return img


# ------------------------------------------------------------------ prévia (como deve ficar no FC)

def previa(pl, molde, S, largura=1920, altura=1080, recorte=True, ttf_numeros=None):
    """O fundo do PES na tela do FC com textos de exemplo nas caixas (o jogo escreve os de verdade).

    'ttf_numeros' (bytes): gols e relógio com a fonte dos números do PES."""
    import io
    from PIL import ImageDraw, ImageFont
    img = pl.desenhar(("fundo", "cor_casa", "cor_fora"), S, largura, altura, fundo=(30, 96, 52, 255))
    dr = ImageDraw.Draw(img)
    exemplos = {"nome_casa": "KAW", "nome_fora": "YOK", "gols_casa": "2", "gols_fora": "1", "relogio": "45:00"}
    for campo, txt in exemplos.items():
        cx = pl.caixa_campo(campo)
        if not cx:
            continue
        cor = tuple(_cor_texto(pl, cx))
        if ttf_numeros and campo == "relogio" and len(pl.caixas_relogio()) == 5:
            # cada dígito na caixa do dígito do PES, como na conversão
            for ch, (_n, cxd) in zip("45:00", pl.caixas_relogio()):
                R = _transformar_caixa(S, cxd)
                f = ImageFont.truetype(io.BytesIO(ttf_numeros), max(6, int(round((R[3] - R[1]) / 0.72))))
                dr.text(((R[0] + R[2]) / 2, R[3]), ch, fill=cor, font=f, anchor="ms")
            continue
        R = _transformar_caixa(S, cx)
        if ttf_numeros and campo.startswith("gols"):
            fonte = ImageFont.truetype(io.BytesIO(ttf_numeros), max(8, int(R[3] - R[1])))
        else:
            try:
                fonte = ImageFont.truetype("arialbd.ttf", max(8, int((R[3] - R[1]) * 0.72)))
            except OSError:
                fonte = ImageFont.load_default()
        dr.text(((R[0] + R[2]) / 2, (R[1] + R[3]) / 2), txt, fill=cor, font=fonte, anchor="mm")
    if recorte:
        cx = _transformar_caixa(S, pl.caixa_visivel(("fundo", "cor_casa", "cor_fora")))
        m = 24
        img = img.crop((max(0, int(cx[0]) - m), max(0, int(cx[1]) - m), min(largura, int(cx[2]) + m),
                        min(altura, int(cx[3]) + m)))
    return img
