"""ActionScript 2 dos overlays (APT 64 bits): leitura do bytecode, simulação das animações e edição de constantes.

Formato (o do OpenSAGE, com ponteiros e contagens alargados para 8 bytes):
- O arquivo de constantes ("Apt1", entrada 1 do .big) tem uma tabela de itens (tipo u64, valor u64) em
  [0x28] com [0x20] itens. Tipos: 1 texto (ponteiro), 3 nada, 4 registrador, 5 booleano, 6 float, 7 inteiro,
  8 "lookup" (índice no ConstantPool ativo).
- Instruções alinhadas (PushData, ConstantPool, desvios, DefineFunction...) começam o operando no próximo múltiplo
  de 8. PushData/ConstantPool: contagem u64 + ponteiro para índices u64 da tabela de constantes. Cada PushData tem
  as próprias entradas na tabela (dá para editar um valor sem mexer nos outros).
- DefineFunction2: nome, nº de parâmetros (u32), nº de registradores (u8), 1 byte, flags (2 bytes: this=0x01,
  arguments=0x04, super=0x10, _root=0x40, _parent=0x80; _global=0x01 no 2º), parâmetros (ponteiro para pares
  registrador/nome de 16 bytes), tamanho do corpo (u64) e 16 bytes de marcadores; o corpo vem em seguida.

As animações dos placares do FC são feitas por código: a classe do overlay chama
game.globalClasses.AnimationManager.Animate(clipe, propriedade, destino, duração, curva, callback, atraso), com
durações e atrasos em quadros. O simulador roda a classe (com "dublês" para as classes do jogo), registra as
mudanças de propriedades e as interpolações e devolve uma linha do tempo para a prévia.
"""
import math
import struct

T_TEXTO, T_NADA, T_REG, T_BOOL, T_FLOAT, T_INT, T_LOOKUP = 1, 3, 4, 5, 6, 7, 8
ALINHADOS = {0x9B, 0x8E, 0x88, 0x9D, 0x99, 0x96, 0x83, 0x8C, 0x87, 0x8B, 0x81, 0x9F, 0x94, 0xA1, 0xB8, 0xA4, 0xA6, 0xA5, 0xA7}
PROPS_MC = ["_x", "_y", "_xscale", "_yscale", "_currentframe", "_totalframes", "_alpha", "_visible", "_width",
            "_height", "_rotation", "_target", "_framesloaded", "_name"]
EXTERNOS = ("game.globalClasses", "game.globalComponents", "cafe.")
PROPS_ANIM = {"_x", "_y", "_xscale", "_yscale", "_alpha", "_visible", "_width", "_height", "_rotation", "_scale"}
LIMITE_PASSOS = 1_000_000      # por chamada (método, callback, InitAction)
LIMITE_VOLTAS = 2000          # repetições de um mesmo laço numa execução de função


class ErroAS(Exception):
    pass


class _Undef:
    def __repr__(self):
        return "undefined"

    def __bool__(self):
        return False


UNDEF = _Undef()


# ------------------------------------------------------------------ tabela de constantes (arquivo "1")

class Constantes:
    def __init__(self, dados):
        self.d = bytearray(dados)
        self.n = struct.unpack_from("<Q", self.d, 0x20)[0]
        self.base = struct.unpack_from("<Q", self.d, 0x28)[0]
        self.pend = []        # textos novos: entram todos juntos em bytes() (a tabela é copiada uma vez só)
        self.fixups = []      # (item existente, índice em pend): o item passa a apontar para o texto novo

    def item(self, i):
        if i >= self.n:
            k = i - self.n
            if k < len(self.pend):
                return (T_TEXTO, -1 - k)
            return (T_NADA, 0)
        return struct.unpack_from("<QQ", self.d, self.base + 16 * i)

    def texto(self, ptr):
        if ptr < 0:
            return self.pend[-1 - ptr]
        if not ptr or ptr >= len(self.d):
            return ""
        e = self.d.index(b"\0", ptr)
        return self.d[ptr:e].decode("latin-1")

    def valor(self, i, pool):
        t, v = self.item(i)
        if t == T_TEXTO:
            return self.texto(v)
        if t == T_LOOKUP:
            return pool[v] if v < len(pool) else UNDEF
        if t == T_INT:
            return struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFF))[0]
        if t == T_FLOAT:
            return struct.unpack("<f", struct.pack("<I", v & 0xFFFFFFFF))[0]
        if t == T_BOOL:
            return bool(v)
        if t == T_REG:
            return ("reg", v)
        if t == T_NADA:
            return None
        return UNDEF

    def tipo(self, i):
        return self.item(i)[0]

    # edição
    def definir_numero(self, i, valor):
        if i >= self.n:
            raise ErroAS("Constante inexistente")
        t, _ = self.item(i)
        if t not in (T_INT, T_FLOAT):
            raise ErroAS("Esta constante não é um número")
        if float(valor).is_integer() and abs(valor) < 2 ** 31:
            struct.pack_into("<QQ", self.d, self.base + 16 * i, T_INT, int(valor) & 0xFFFFFFFF)
        else:
            struct.pack_into("<QQ", self.d, self.base + 16 * i, T_FLOAT, struct.unpack("<I", struct.pack("<f", float(valor)))[0])

    def acrescentar_texto(self, s):
        """Novo item de texto no fim da tabela. Os novos são gravados juntos em bytes(): a tabela é copiada
        para o fim do arquivo uma vez, com os itens a mais."""
        self.pend.append(s)
        return self.n + len(self.pend) - 1

    def apontar_texto(self, slot, i):
        """O item de texto 'slot' passa a usar o texto do item i."""
        _t, v = self.item(i)
        if v < 0:
            self.fixups.append((slot, -1 - v))
            struct.pack_into("<QQ", self.d, self.base + 16 * slot, T_TEXTO, 0)
        else:
            struct.pack_into("<QQ", self.d, self.base + 16 * slot, T_TEXTO, v)

    def achar_texto(self, s):
        for i in range(self.n):
            t, v = self.item(i)
            if t == T_TEXTO and self.texto(v) == s:
                return i
        if s in self.pend:
            return self.n + self.pend.index(s)
        return None

    def bytes(self):
        if self.pend:
            ptrs = []
            while len(self.d) % 8:
                self.d.append(0)
            for txt in self.pend:
                ptrs.append(len(self.d))
                self.d += txt.encode("latin-1") + b"\0"
            while len(self.d) % 8:
                self.d.append(0)
            nova = len(self.d)
            self.d += self.d[self.base:self.base + 16 * self.n]
            for p in ptrs:
                self.d += struct.pack("<QQ", T_TEXTO, p)
            for slot, k in self.fixups:
                struct.pack_into("<QQ", self.d, nova + 16 * slot, T_TEXTO, ptrs[k])
            self.base = nova
            self.n += len(self.pend)
            struct.pack_into("<QQ", self.d, 0x20, self.n, self.base)
            self.pend, self.fixups = [], []
        return bytes(self.d)


# ------------------------------------------------------------------ decodificação das instruções

def decodificar(d, p):
    """(opcode, argumentos, próxima posição). Argumentos brutos (índices, ponteiros)."""
    op = d[p]
    p += 1
    if op in ALINHADOS:
        p = (p + 7) // 8 * 8
    if op in (0x96, 0x88):
        cnt, ptr = struct.unpack_from("<QQ", d, p)
        p += 16
        if cnt > 1_000_000:
            raise ErroAS("PushData inválido")
        return op, (ptr, cnt), p
    if op in (0x99, 0x9D, 0xB8):
        return op, struct.unpack_from("<i", d, p)[0], p + 4
    if op in (0xA1, 0xA4, 0xA5, 0xA6, 0xA7, 0x8C):
        return op, struct.unpack_from("<Q", d, p)[0], p + 8
    if op in (0x87, 0x81, 0x9F):
        return op, struct.unpack_from("<i", d, p)[0], p + 4
    if op in (0xA2, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3, 0xB5, 0xB9):
        return op, d[p], p + 1
    if op in (0xA3, 0xB6):
        return op, struct.unpack_from("<H", d, p)[0], p + 2
    if op == 0xB4:
        return op, struct.unpack_from("<f", d, p)[0], p + 4
    if op == 0xB7:
        return op, struct.unpack_from("<I", d, p)[0], p + 4
    if op == 0x8E:
        nome, npar = struct.unpack_from("<QI", d, p)
        nreg = d[p + 12]
        fl1, fl2 = d[p + 14], d[p + 15]
        ppar, corpo = struct.unpack_from("<QQ", d, p + 16)
        p += 48
        pars = [(struct.unpack_from("<i", d, ppar + 16 * k)[0], struct.unpack_from("<Q", d, ppar + 16 * k + 8)[0]) for k in range(npar)]
        return op, (nome, pars, nreg, fl1 | (fl2 << 8), corpo), p
    if op == 0x9B:
        nome, npar = struct.unpack_from("<QI", d, p)
        ppar, corpo = struct.unpack_from("<QQ", d, p + 16)
        p += 48
        pars = [struct.unpack_from("<Q", d, ppar + 8 * k)[0] for k in range(npar)]
        return op, (nome, pars, corpo), p
    if op == 0x83:
        a, b = struct.unpack_from("<QQ", d, p)
        return op, (a, b), p + 16
    return op, None, p


# ------------------------------------------------------------------ valores e objetos da simulação

class Pool(list):
    """ConstantPool ativo (lista de valores) + a posição da instrução, para poder estendê-lo ao editar."""
    pos = None


class Obj:
    __slots__ = ("props", "proto", "nome")

    def __init__(self, proto=None, nome=""):
        self.props = {}
        self.proto = proto
        self.nome = nome

    def get(self, k):
        o = self
        n = 0
        while o is not None and n < 64:
            if k in o.props:
                return o.props[k]
            o = o.proto
            n += 1
        return None

    def set(self, k, v):
        self.props[k] = v


class Funcao(Obj):
    __slots__ = ("inicio", "tam", "pars", "nreg", "flags", "pool", "escopo", "nativa", "dados", "ctx")

    def __init__(self, vm, inicio=0, tam=0, pars=(), nreg=0, flags=0, pool=None, escopo=(), nativa=None, nome=""):
        super().__init__(vm.proto_funcao, nome)
        self.inicio, self.tam, self.pars, self.nreg, self.flags = inicio, tam, pars, nreg, flags
        self.pool, self.escopo, self.nativa = pool if pool is not None else Pool(), escopo, nativa
        self.dados = None
        self.ctx = None
        if nativa is None:
            pr = Obj(vm.proto_objeto)
            pr.set("constructor", (self, None))
            self.set("prototype", (pr, None))


class Lista(Obj):
    __slots__ = ("itens",)

    def __init__(self, vm, itens=None):
        super().__init__(vm.proto_lista)
        self.itens = itens or []


class NS(Obj):
    """Namespace do jogo (game.globalClasses...): guarda o que for definido; o que não existe vira dublê."""
    __slots__ = ("caminho",)

    def __init__(self, caminho, proto=None):
        super().__init__(proto, caminho)
        self.caminho = caminho


class Duble(Obj):
    """Classe/objeto do jogo que não está no arquivo: aceita qualquer membro e chamada, lembrando o caminho."""
    __slots__ = ("caminho", "args", "slot")

    def __init__(self, caminho, args=None, slot=None):
        super().__init__(None, caminho)
        self.caminho = caminho
        self.args = args
        self.slot = slot


class Clipe(Obj):
    __slots__ = ("vm", "caminho", "char", "filhos", "estado", "pai_clipe", "limites", "classe")

    def __init__(self, vm, nome, caminho, char, limites, pai=None):
        super().__init__(vm.proto_clipe, nome)
        self.vm = vm
        self.caminho = caminho
        self.char = char
        self.filhos = {}
        self.estado = {}
        self.pai_clipe = pai
        self.limites = limites
        self.classe = None


# ------------------------------------------------------------------ a máquina

class Simulador:
    def __init__(self, apt, consts, exports, quadros_por_char, limites_char, chars):
        self.apt = apt            # bytes da entrada 0
        self.c = consts           # Constantes
        self.exports = exports    # [(nome, char)]
        self.quadros = quadros_por_char
        self.limites_char = limites_char
        self.chars = chars
        self.passos = 0
        self.tempo = 0.0
        self.eventos = []         # (t, caminho, prop, valor)
        self.tweens = []
        self.agenda = []          # (t, seq, funcao, this, args)
        self.seq = 0
        self.constantes = {}      # slot -> {classe, nome, valor}
        self.formatos = []
        self.textos = {}
        self.chamadas = []
        self.classes = {}         # símbolo -> construtor
        self.erros = []
        self.proto_objeto = Obj(None, "Object.prototype")
        self.proto_funcao = Obj(self.proto_objeto, "Function.prototype")
        self.proto_lista = Obj(self.proto_objeto, "Array.prototype")
        self.proto_clipe = Obj(self.proto_objeto, "MovieClip.prototype")
        self.glob = Obj(self.proto_objeto, "_global")
        self.tema = {}            # valores do tema (FIFA.xml) que o StyleManager devolve: ALPHA_FULL = 100...
        self._nativos()

    # ---------------------------------------------------------- ambiente
    def _nat(self, nome, fn):
        return (Funcao(self, nativa=fn, nome=nome), None)

    def _nativos(self):
        g = self.glob
        obj_ctor = Funcao(self, nativa=lambda this, args: (Obj(self.proto_objeto), None), nome="Object")
        obj_ctor.set("prototype", (self.proto_objeto, None))
        obj_ctor.set("registerClass", self._nat("registerClass", self._registrar))
        g.set("Object", (obj_ctor, None))
        arr = Funcao(self, nativa=lambda this, args: (Lista(self, [a for a in args] if len(args) != 1 else []), None), nome="Array")
        arr.set("prototype", (self.proto_lista, None))
        g.set("Array", (arr, None))
        g.set("TextFormat", (Funcao(self, nativa=self._textformat, nome="TextFormat"), None))
        g.set("ASSetPropFlags", self._nat("ASSetPropFlags", lambda t, a: (UNDEF, None)))
        g.set("setInterval", self._nat("setInterval", lambda t, a: (0, None)))
        g.set("clearInterval", self._nat("clearInterval", lambda t, a: (UNDEF, None)))
        g.set("setTimeout", self._nat("setTimeout", self._settimeout))
        g.set("parseInt", self._nat("parseInt", lambda t, a: (_num(a[0][0] if a else 0), None)))
        g.set("parseFloat", self._nat("parseFloat", lambda t, a: (_num(a[0][0] if a else 0), None)))
        g.set("isNaN", self._nat("isNaN", lambda t, a: (isinstance(_num(a[0][0] if a else UNDEF), float) and math.isnan(_num(a[0][0])), None)))
        g.set("String", self._nat("String", lambda t, a: (_str(a[0][0]) if a else "", None)))
        g.set("Number", self._nat("Number", lambda t, a: (_num(a[0][0]) if a else 0, None)))
        g.set("Boolean", self._nat("Boolean", lambda t, a: (bool(_bool(a[0][0])) if a else False, None)))
        m = Obj(self.proto_objeto, "Math")
        for nome, fn in (("round", lambda x: math.floor(x + 0.5)), ("floor", math.floor), ("ceil", math.ceil), ("abs", abs),
                         ("sqrt", lambda x: math.sqrt(max(0, x))), ("sin", math.sin), ("cos", math.cos), ("atan2", None),
                         ("random", None), ("max", None), ("min", None), ("pow", None)):
            if nome == "atan2":
                f = lambda t, a: (math.atan2(_num(a[0][0]), _num(a[1][0])) if len(a) > 1 else 0, None)
            elif nome == "random":
                f = lambda t, a: (0.5, None)
            elif nome in ("max", "min"):
                f = (lambda t, a, nm=nome: ((max if nm == "max" else min)([_num(x[0]) for x in a]) if a else 0, None))
            elif nome == "pow":
                f = lambda t, a: (_num(a[0][0]) ** _num(a[1][0]) if len(a) > 1 else 0, None)
            else:
                f = (lambda t, a, fn=fn: (_fin(_mat(fn, _num(a[0][0]))) if a else 0, None))
            m.set(nome, self._nat(nome, f))
        m.set("PI", (math.pi, None))
        g.set("Math", (m, None))
        # métodos de clipe
        cp = self.proto_clipe
        for nome in ("gotoAndStop", "gotoAndPlay", "play", "stop", "nextFrame", "prevFrame", "swapDepths", "setMask",
                     "removeMovieClip", "attachMovie", "createEmptyMovieClip", "duplicateMovieClip", "createTextField",
                     "getBounds", "localToGlobal", "globalToLocal", "hitTest", "getDepth", "getNextHighestDepth", "lineStyle",
                     "beginFill", "endFill", "moveTo", "lineTo", "clear", "getInstanceAtDepth"):
            cp.set(nome, self._nat(nome, (lambda t, a, nm=nome: self._metodo_clipe(nm, t, a))))
        # lista
        lp = self.proto_lista
        lp.set("push", self._nat("push", lambda t, a: (_push(t, a), None)))
        lp.set("pop", self._nat("pop", lambda t, a: ((t.itens.pop()[0] if isinstance(t, Lista) and t.itens else UNDEF), None)))
        lp.set("join", self._nat("join", lambda t, a: ((_str(a[0][0]) if a else ",").join(_str(x[0]) for x in t.itens) if isinstance(t, Lista) else "", None)))
        lp.set("splice", self._nat("splice", lambda t, a: (Lista(self), None)))
        lp.set("concat", self._nat("concat", lambda t, a: (Lista(self, (t.itens if isinstance(t, Lista) else []) + [x for y in a for x in (y[0].itens if isinstance(y[0], Lista) else [y])]), None)))
        # namespaces do jogo: dublês
        jogo = NS("game", self.proto_objeto)
        for k in ("globalClasses", "globalComponents", "uif", "ion"):
            jogo.set(k, (NS("game." + k, self.proto_objeto), None))
        g.set("game", (jogo, None))
        for k in ("cafe", "mx", "ion", "fc", "flash", "EAS"):
            g.set(k, (NS(k, self.proto_objeto), None))
        g.get("cafe")[0].set("utility", (NS("cafe.utility", self.proto_objeto), None))

    def _registrar(self, this, args):
        if len(args) >= 2:
            self.classes[_str(args[0][0])] = args[1][0]
        return (True, None)

    def _textformat(self, this, args):
        o = Obj(self.proto_objeto, "TextFormat")
        nomes = ["font", "size", "color", "bold", "italic", "underline", "url", "target", "align"]
        for k, (v, s) in zip(nomes, args):
            o.set(k, (v, s))
        fonte = args[0] if args else (UNDEF, None)
        tam = args[1] if len(args) > 1 else (UNDEF, None)
        reg = {"fonte_chave": fonte[0].caminho.split(".")[-1] if isinstance(fonte[0], Duble) else _str(fonte[0]),
               "fonte_slot": fonte[0].slot if isinstance(fonte[0], Duble) else fonte[1],
               "tamanho": _num(tam[0]) if tam[0] is not UNDEF else None, "tamanho_slot": tam[1],
               "constante_tamanho": self.constantes.get(tam[1], {}).get("nome") if tam[1] is not None else None}
        cor = args[2] if len(args) > 2 else (UNDEF, None)
        reg["cor"] = _int(cor[0]) if isinstance(cor[0], (int, float)) and not isinstance(cor[0], bool) else None
        o.set("__registro", (reg, None))
        if not getattr(self, "externo_nivel", 0):
            self.formatos.append(reg)
        return (o, None)

    def _settimeout(self, this, args):
        if args and isinstance(args[0][0], Funcao):
            ms = _num(args[1][0]) if len(args) > 1 else 0
            self._agendar(self.tempo + ms / 33.333, args[0][0], UNDEF, [a for a in args[2:]])
        return (0, None)

    def _agendar(self, t, fn, this, args):
        self.seq += 1
        self.agenda.append((t, self.seq, fn, this, args))

    # ---------------------------------------------------------- clipes
    def criar_clipes(self, char, nome, caminho, limites, pai=None, nivel=0):
        c = Clipe(self, nome, caminho, char, limites, pai)
        if nivel > 30:
            return c
        for it in self._lista_exibicao(char):
            filho_nome = it.get("nome") or ""
            limites_f = self.limites_char(it["char"])
            cam = (caminho + "." if caminho else "") + filho_nome if filho_nome else None
            f = self.criar_clipes(it["char"], filho_nome, cam or "", limites_f, c, nivel + 1)
            m = it["m"]
            sx = math.hypot(m[0], m[1])
            det = m[0] * m[3] - m[1] * m[2]
            sy = det / sx if sx else math.hypot(m[2], m[3])
            f.estado = {"_x": it["tx"][0], "_y": it["tx"][1], "_xscale": sx * 100, "_yscale": sy * 100,
                        "_rotation": math.degrees(math.atan2(m[1], m[0])),
                        "_alpha": (it["tint"][3] / 2.55) if it["fl"] & 8 else 100.0, "_visible": True}
            if filho_nome:
                c.filhos[filho_nome] = f
                c.set(filho_nome, (f, None))
            sim = self._classe_do_char(it["char"])
            if sim:
                f.classe = sim
        return c

    def _lista_exibicao(self, char):
        qs = self.quadros(char)
        if not qs:
            return []
        lst = {}
        for it in qs[0]:
            if it["t"] == "place":
                if (it["fl"] & 2) or it["prof"] not in lst:
                    lst[it["prof"]] = it
            elif it["t"] == "remove":
                lst.pop(it["prof"], None)
        return [lst[k] for k in sorted(lst)]

    def _classe_do_char(self, char):
        for nome, ch in self.exports:
            if ch == char and not nome.startswith("__Packages"):
                return nome
        return None

    def _metodo_clipe(self, nome, this, args):
        if isinstance(this, Clipe):
            if nome in ("gotoAndStop", "gotoAndPlay", "play", "stop"):
                self.eventos.append((self.tempo, this.caminho, "@" + nome, _str(args[0][0]) if args else ""))
            if nome in ("attachMovie", "createEmptyMovieClip", "duplicateMovieClip", "createTextField"):
                nm = _str(args[1][0]) if len(args) > 1 else "novo"
                c = Clipe(self, nm, this.caminho + "." + nm, -1, None, this)
                this.set(nm, (c, None))
                return (c, None)
            if nome == "getBounds":
                o = Obj(self.proto_objeto)
                b = this.limites or [0, 0, 0, 0]
                for k, v in zip(("xMin", "yMin", "xMax", "yMax"), b):
                    o.set(k, (v, None))
                return (o, None)
            if nome in ("getDepth", "getNextHighestDepth"):
                return (1000, None)
        return (UNDEF, None)

    def ler_prop_clipe(self, c, k):
        if k == "_scale":                   # propriedade do AnimationManager: as duas escalas juntas
            k = "_xscale"
        if k in c.estado:
            return c.estado[k]
        if k in ("_width", "_height"):
            b = c.limites
            if not b:
                return 0
            sx = c.estado.get("_xscale", 100) / 100
            sy = c.estado.get("_yscale", 100) / 100
            return (b[2] - b[0]) * abs(sx) if k == "_width" else (b[3] - b[1]) * abs(sy)
        if k == "_name":
            return c.nome
        if k == "_parent":
            return c.pai_clipe or UNDEF
        if k in ("_currentframe", "_totalframes"):
            return 1
        if k in ("_xscale", "_yscale", "_alpha"):
            return 100
        if k in ("_x", "_y", "_rotation"):
            return 0
        if k == "_visible":
            return True
        return None

    def gravar_prop_clipe(self, c, k, v, registrar=True):
        if k == "_scale":
            self.gravar_prop_clipe(c, "_xscale", v, registrar)
            self.gravar_prop_clipe(c, "_yscale", v, registrar)
            return
        if k in ("_width", "_height"):
            b = c.limites
            if b:
                base = (b[2] - b[0]) if k == "_width" else (b[3] - b[1])
                if base:
                    k2 = "_xscale" if k == "_width" else "_yscale"
                    c.estado[k2] = _num(v) / base * 100
                    if registrar and c.caminho:
                        self.eventos.append((self.tempo, c.caminho, k2, c.estado[k2]))
            return
        c.estado[k] = v
        if registrar and c.caminho and k in PROPS_ANIM:
            self.eventos.append((self.tempo, c.caminho, k, _num(v) if k != "_visible" else bool(_bool(v))))

    # ---------------------------------------------------------- acesso a membros
    def membro(self, obj, k):
        k = _str(k)
        if isinstance(obj, Clipe):
            if k in PROPS_MC or k == "_parent":
                return (self.ler_prop_clipe(obj, k), None)
            if k in obj.filhos:
                return (obj.filhos[k], None)
            if k in ("textWidth", "textHeight"):
                # campo de texto: o jogo mede o texto da partida; aqui uma estimativa pelo texto que o código pôs
                # (ou o do arquivo, ou "00"), para não encavalar o que é centralizado pela largura
                c = self.chars[obj.char] if 0 <= obj.char < len(self.chars) else None
                if c and c.get("t") == "texto":
                    t = obj.get("text") or obj.get("htmlText")
                    txt = _str(t[0]) if t and isinstance(t[0], str) else (c.get("conteudo") or "00")
                    alt = c.get("altura") or 12
                    return ((len(txt) * alt * 0.6, None) if k == "textWidth" else (alt * 1.15, None))
            r = obj.get(k)
            if r is not None:
                return r
            if obj.classe and obj.classe in self.classes:
                ctor = self.classes[obj.classe]
                pr = ctor.get("prototype") if isinstance(ctor, Obj) else None
                if pr and isinstance(pr[0], Obj):
                    r = pr[0].get(k)
                    if r is not None:
                        return r
            # componente de outro arquivo (MultiText, ImageLoader...): dublê com o nome do método
            return (Duble(obj.caminho + "." + k), None)
        if isinstance(obj, Duble):
            if k in ("prototype",):
                return (Obj(self.proto_objeto), None)
            if obj.caminho.endswith("StyleManager") and k in self.tema:
                return (self.tema[k], None)
            return (Duble(obj.caminho + "." + k), None)
        if isinstance(obj, Lista):
            if k == "length":
                return (len(obj.itens), None)
            if k.isdigit():
                i = int(k)
                return obj.itens[i] if i < len(obj.itens) else (UNDEF, None)
        if isinstance(obj, str):
            if k == "length":
                return (len(obj), None)
            return self._metodo_texto(obj, k)
        if isinstance(obj, NS):
            r = obj.get(k)
            return r if r is not None else (Duble(obj.caminho + "." + k), None)
        if isinstance(obj, Obj):
            if k == "__proto__":
                return (obj.proto or UNDEF, None)
            r = obj.get(k)
            if r is None and isinstance(obj, Funcao) and obj.nome.startswith(EXTERNOS):
                if obj.nome.endswith("StyleManager") and k in self.tema:
                    return (self.tema[k], None)            # ALPHA_FULL, COLOR_..., FONT_SIZE_... do FIFA.xml
                return (Duble(obj.nome + "." + k), None)   # ex.: StyleManager.FONT_NAME_BOLD (vem do tema)
            return r if r is not None else (UNDEF, None)
        return (UNDEF, None)

    def _metodo_texto(self, s, k):
        if k == "charAt":
            return self._nat(k, lambda t, a: ((s[_int(a[0][0])] if a and 0 <= _int(a[0][0]) < len(s) else ""), None))
        if k == "toUpperCase":
            return self._nat(k, lambda t, a: (s.upper(), None))
        if k == "toLowerCase":
            return self._nat(k, lambda t, a: (s.lower(), None))
        if k in ("substr", "substring", "slice"):
            def f(t, a):
                i = _int(a[0][0]) if a else 0
                j = _int(a[1][0]) if len(a) > 1 else None
                if k == "substr":
                    return (s[i:i + j] if j is not None else s[i:], None)
                return (s[i:j] if j is not None else s[i:], None)
            return self._nat(k, f)
        if k == "indexOf":
            return self._nat(k, lambda t, a: (s.find(_str(a[0][0])) if a else -1, None))
        if k == "split":
            return self._nat(k, lambda t, a: (Lista(self, [(x, None) for x in s.split(_str(a[0][0]))]) if a else Lista(self), None))
        return (UNDEF, None)

    def definir_membro(self, obj, k, v, slot_valor):
        k = _str(k)
        if isinstance(obj, Clipe):
            if k in PROPS_MC:
                self.gravar_prop_clipe(obj, k, v)
                return
            obj.set(k, (v, slot_valor))
            return
        if isinstance(obj, Lista) and k.isdigit():
            i = int(k)
            while len(obj.itens) <= i:
                obj.itens.append((UNDEF, None))
            obj.itens[i] = (v, slot_valor)
            return
        if isinstance(obj, Obj) and not isinstance(obj, Duble):
            if isinstance(obj, NS) and isinstance(v, Funcao) and not v.nome:
                v.nome = obj.caminho + "." + k
            obj.set(k, (v, slot_valor))
            # constante estática da classe (ANIM_NORMAL_DUR = 10...)
            if isinstance(obj, Funcao) and slot_valor is not None and not getattr(self, "externo_nivel", 0) and k.upper() == k and isinstance(v, (int, float, str)) and not isinstance(v, bool):
                self.constantes[slot_valor] = {"classe": obj.nome, "nome": k, "valor": v, "slot": slot_valor}

    # ---------------------------------------------------------- chamadas
    def chamar(self, fn, this, args, nome=""):
        if isinstance(fn, Funcao):
            if fn.nativa:
                return fn.nativa(this, args)
            return self.executar(fn, this, args)
        if isinstance(fn, Duble):
            return self._chamar_duble(fn, this, args)
        return (UNDEF, None)

    def _chamar_duble(self, fn, this, args):
        cam = fn.caminho
        fim = cam.rsplit(".", 1)[-1]
        if fim == "Animate" and "AnimationManager" in cam:
            self._animate(args)
            return (UNDEF, None)
        if fim in ("create", "Create") and "Delegate" in cam and len(args) >= 2:
            alvo, f = args[0][0], args[1][0]
            if isinstance(f, Funcao):
                ligada = Funcao(self, nativa=lambda t, a, f=f, alvo=alvo: self.chamar(f, alvo, a), nome="delegate")
                ligada.dados = f
                return (ligada, None)
        if fim in ("SetText", "setText", "SetHtmlText", "Initialize", "Init", "SetConfig", "SetTextFormat") and isinstance(this, Clipe):
            cfg = None
            texto = None
            for a in args:
                c = self._config_texto(a[0])
                if c and c.get("formato"):
                    cfg = c
                elif isinstance(a[0], str):
                    texto = a[0]
                elif isinstance(a[0], Lista) and a[0].itens and isinstance(a[0].itens[0][0], str):
                    texto = a[0].itens[0][0]
            ant = self.textos.get(this.caminho, {})
            self.textos[this.caminho] = {"texto": texto or ant.get("texto"), "config": cfg or ant.get("config")}
        self.chamadas.append(cam)
        return (Duble(cam + "()", args=args), None)

    def _config_texto(self, cfg):
        # MultiTextConfig.Base(escala, alinhamento v, alinhamento h, TextFormat...) é dublê: procura o TextFormat
        if isinstance(cfg, Duble) and cfg.args:
            out = {"partes": [a[0].caminho.split(".")[-1] if isinstance(a[0], Duble) else a[0] for a in cfg.args if not isinstance(a[0], Obj) or isinstance(a[0], Duble)]}
            for a in cfg.args:
                if isinstance(a[0], Obj) and a[0].get("__registro"):
                    out["formato"] = a[0].get("__registro")[0]
            return out
        if isinstance(cfg, Obj) and cfg.get("__registro"):
            return {"formato": cfg.get("__registro")[0]}
        return None

    def _animate(self, args, de_inicio=False, inicio=None):
        a = list(args) + [(UNDEF, None)] * 8
        clipe, prop, alvo, dur, ease, cb, atraso = (x for x in a[:7])
        if not isinstance(clipe[0], Clipe):
            if isinstance(cb[0], Funcao):     # Timer em clipe desconhecido: só o callback
                d = max(0.0, _num(dur[0]) if dur[0] is not UNDEF else 0.0)
                t0 = self.tempo + max(0.0, _num(atraso[0]) if atraso[0] not in (UNDEF, None) else 0.0)
                self._agendar(t0 + d, cb[0], UNDEF, [])
            return
        if _str(prop[0]) == "timer":           # AnimationManager.Timer: espera e chama o callback
            d = max(0.0, _num(dur[0]) if dur[0] is not UNDEF else 0.0)
            t0 = self.tempo + max(0.0, _num(atraso[0]) if atraso[0] not in (UNDEF, None) else 0.0)
            if isinstance(cb[0], Funcao):
                self._agendar(t0 + d, cb[0], UNDEF, [])
            return
        props = [x[0] for x in prop[0].itens] if isinstance(prop[0], Lista) else [prop[0]]
        alvos = [x for x in alvo[0].itens] if isinstance(alvo[0], Lista) else [alvo]
        d = max(0.0, _num(dur[0]) if dur[0] is not UNDEF else 0.0)
        t0 = self.tempo + max(0.0, _num(atraso[0]) if atraso[0] not in (UNDEF, None) else 0.0)
        nome_ease = ease[0].caminho.split(".")[-1] if isinstance(ease[0], Duble) else (_str(ease[0]) if ease[0] not in (UNDEF, None) else "Linear")
        slot_ease = ease[0].slot if isinstance(ease[0], Duble) else None
        nome_const_ease = nome_ease if isinstance(ease[0], Duble) else None
        ease_literal = False
        if isinstance(ease[1], str) and ease[1].startswith("m:"):
            slot_ease, _, nome_const_ease = ease[1][2:].partition("|")
        elif isinstance(ease[0], str) and isinstance(ease[1], str):
            slot_ease, nome_const_ease, ease_literal = ease[1], None, True
        for i, p in enumerate(props):
            p = _str(p)
            v = alvos[i] if i < len(alvos) else alvos[-1]
            if de_inicio:     # AnimateFrom: o valor dado é o de partida; o destino é o valor atual
                partida = _num(v[0])
                atual_v = self.ler_prop_clipe(clipe[0], p)
                self.gravar_prop_clipe(clipe[0], p, partida)
                v = (atual_v, None)
            elif inicio is not None and inicio[0] not in (UNDEF, None):
                self.gravar_prop_clipe(clipe[0], p, _num(inicio[0]))
            self.tweens.append({"alvo": clipe[0].caminho, "prop": p, "para": _num(v[0]) if p != "_visible" else bool(_bool(v[0])),
                                "t0": t0, "dur": d, "ease": nome_ease, "ease_slot": slot_ease, "ease_const": nome_const_ease, "ease_literal": ease_literal,
                                "atraso": max(0.0, _num(atraso[0])) if isinstance(atraso[0], (int, float)) else 0,
                                "dur_slot": dur[1], "dur_const": self.constantes.get(dur[1], {}).get("nome"),
                                "atraso_slot": atraso[1], "atraso_const": self.constantes.get(atraso[1], {}).get("nome"),
                                "para_slot": v[1], "para_const": self.constantes.get(v[1], {}).get("nome"),
                                "metodo": self.metodo_atual, "_clipe": clipe[0]})
        if isinstance(cb[0], Funcao):
            self._agendar(t0 + d, cb[0], UNDEF, [])

    # ---------------------------------------------------------- execução de uma função
    def executar(self, fn, this, args, pool_ini=None):
        regs = [(UNDEF, None)] * (max(fn.nreg, 1) + 4)
        locais = Obj(None, "locais")
        r = 1
        fl = fn.flags
        if fl & 0x01:
            regs[r] = (this, None)
            r += 1
        if fl & 0x04:
            regs[r] = (Lista(self, list(args)), None)
            r += 1
        if fl & 0x10:
            regs[r] = (self._super(fn, this), None)
            r += 1
        if fl & 0x40:
            regs[r] = (self.raiz_clipe, None)
            r += 1
        if fl & 0x80:
            regs[r] = (this.pai_clipe if isinstance(this, Clipe) and this.pai_clipe else UNDEF, None)
            r += 1
        if fl & 0x100:
            regs[r] = (self.glob, None)
            r += 1
        for i, (reg, nome) in enumerate(fn.pars):
            v = args[i] if i < len(args) else (UNDEF, None)
            if reg and reg < len(regs):
                regs[reg] = v
            else:
                locais.set(nome, v)
        locais.set("this", (this, None))
        locais.set("arguments", (Lista(self, list(args)), None))
        escopo = [locais] + list(fn.escopo)
        return self._rodar(fn.inicio, fn.inicio + fn.tam if fn.tam else None, this, regs, escopo, fn.pool, fn.ctx)

    def _super(self, fn, this):
        # super = protótipo do pai da classe de 'this'
        dono = fn.get("__dono")
        if dono:
            pr = dono[0]
            if isinstance(pr, Obj) and pr.proto:
                return SuperRef(pr.proto, this)
        return Duble("super")

    def _rodar(self, p, fim, this, regs, escopo, pool, ctx=None):
        externo = ctx is not None and ctx[0] is not self.apt
        if externo:
            self.externo_nivel = getattr(self, "externo_nivel", 0) + 1
            try:
                return self._rodar2(p, fim, this, regs, escopo, pool, ctx, True)
            finally:
                self.externo_nivel -= 1
        return self._rodar2(p, fim, this, regs, escopo, pool, ctx, False)

    def _rodar2(self, p, fim, this, regs, escopo, pool, ctx, externo):
        d, c = ctx if ctx else (self.apt, self.c)
        pilha = []
        pop = lambda: pilha.pop() if pilha else (UNDEF, None)
        voltas = {}
        while True:
            if fim is not None and p >= fim:
                return (UNDEF, None)
            self.passos += 1
            if self.passos > LIMITE_PASSOS:
                raise ErroAS("Simulação longa demais")
            op, arg, q = decodificar(d, p)
            if op == 0x00:
                return (UNDEF, None)
            if op == 0x96:
                ptr, cnt = arg
                for k in range(cnt):
                    i = struct.unpack_from("<Q", d, ptr + 8 * k)[0]
                    v = c.valor(i, pool)
                    if isinstance(v, tuple) and v and v[0] == "reg":
                        pilha.append(regs[v[1]] if v[1] < len(regs) else (UNDEF, None))
                    else:
                        pilha.append((v, None if externo else "c:%d" % i))
            elif op == 0x88:
                ptr, cnt = arg
                pool = Pool(c.valor(struct.unpack_from("<Q", d, ptr + 8 * k)[0], []) for k in range(cnt))
                pool.pos = p
            elif op == 0xA2 or op == 0xA3:
                pilha.append((pool[arg] if arg < len(pool) else UNDEF,
                               "%s:%d:%s" % ("pk" if op == 0xA2 else "pkw", p + 1, getattr(pool, "pos", None))))
            elif op == 0xA1:
                pilha.append((_txt(d, arg), None))
            elif op == 0xB4 or op == 0xB5 or op == 0xB6 or op == 0xB7:
                pilha.append((arg, "%s:%d" % ({0xB4: "pf", 0xB5: "pb", 0xB6: "ps", 0xB7: "pl"}[op], p + 1)))
            elif op == 0xB9:
                pilha.append(regs[arg] if arg < len(regs) else (UNDEF, None))
            elif op == 0x59:
                pilha.append((0, None))
            elif op == 0x5A:
                pilha.append((1, None))
            elif op == 0x73:
                pilha.append((True, None))
            elif op == 0x74:
                pilha.append((False, None))
            elif op == 0x75:
                pilha.append((None, None))
            elif op == 0x76:
                pilha.append((UNDEF, None))
            elif op == 0x56:
                pilha.append(("this", None))        # EA_PushThis: o nome (vem sempre seguido de GetVar)
            elif op == 0x58:
                pilha.append(("_global", None))     # EA_PushGlobal: idem
            elif op == 0x87:
                if arg < len(regs):
                    regs[arg] = pilha[-1] if pilha else (UNDEF, None)
            elif op == 0x17:
                pop()
            elif op == 0x4C:
                pilha.append(pilha[-1] if pilha else (UNDEF, None))
            elif op == 0x4D:
                if len(pilha) >= 2:
                    pilha[-1], pilha[-2] = pilha[-2], pilha[-1]
            elif op == 0x1C:
                nome = _str(pop()[0])
                pilha.append(self._variavel(nome, escopo, this))
            elif op == 0xAE:
                pilha.append(self._variavel(_str(pool[arg]) if arg < len(pool) else "", escopo, this))
            elif op == 0x1D:
                v = pop()
                nome = _str(pop()[0])
                self._definir_variavel(nome, v, escopo)
            elif op == 0x3C:
                v = pop()
                nome = _str(pop()[0])
                escopo[0].set(nome, v)
            elif op == 0x41:
                nome = _str(pop()[0])
                if escopo[0].get(nome) is None:
                    escopo[0].set(nome, (UNDEF, None))
            elif op == 0x4E:
                nome = pop()
                obj = pop()[0]
                v = self.membro(obj, nome[0])
                if isinstance(v[0], Duble) and v[0].slot is None and nome[1] is not None:
                    v = (Duble(v[0].caminho, v[0].args, nome[1]), v[1])
                elif isinstance(obj, Funcao) and obj.nome.startswith(EXTERNOS) and nome[1] is not None and not externo:
                    v = (v[0], "m:%s|%s" % (nome[1], _str(nome[0])))
                pilha.append(v)
            elif op == 0xAF:
                obj = pop()[0]
                v = self.membro(obj, pool[arg] if arg < len(pool) else "")
                if isinstance(v[0], Duble) and v[0].slot is None:
                    v = (Duble(v[0].caminho, v[0].args, "pk:%d:%s" % (p + 1, getattr(pool, "pos", None))), v[1])
                pilha.append(v)
            elif op == 0xA5:
                obj = pop()[0]
                pilha.append(self.membro(obj, _txt(d, arg)))
            elif op == 0x4F:
                v = pop()
                nome = _str(pop()[0])
                obj = pop()[0]
                self.definir_membro(obj, nome, v[0], v[1])
            elif op == 0xA7:
                v = pop()
                obj = pop()[0]
                self.definir_membro(obj, _txt(d, arg), v[0], v[1])
            elif op in (0x3D, 0x5C, 0x5B, 0xB0, 0xB1):
                if op in (0xB0, 0xB1):
                    nome = _str(pool[arg]) if arg < len(pool) else ""
                else:
                    nome = _str(pop()[0])
                n = _int(pop()[0])
                args = [pop() for _ in range(max(0, min(n, 64)))]
                fn = self._variavel(nome, escopo, this)[0]
                r = self.chamar(fn, UNDEF, args, nome)
                if op not in (0x5B, 0xB0):
                    pilha.append(r)
            elif op in (0x52, 0x5E, 0x5D, 0xB2, 0xB3):
                if op in (0xB2, 0xB3):
                    nome = pool[arg] if arg < len(pool) else ""
                else:
                    nome = pop()[0]
                obj = pop()[0]
                n = _int(pop()[0])
                args = [pop() for _ in range(max(0, min(n, 64)))]
                if nome in (UNDEF, None, ""):
                    fn, alvo = obj, UNDEF
                else:
                    fn = self.membro(obj, nome)[0] if not isinstance(obj, SuperRef) else obj.membro(self, nome)
                    alvo = obj.this if isinstance(obj, SuperRef) else obj
                    if isinstance(fn, Duble) and isinstance(obj, Clipe):
                        r = self._chamar_duble(fn, obj, args)
                        if op not in (0x5D, 0xB2):
                            pilha.append(r)
                        p = q
                        continue
                r = self.chamar(fn, alvo, args)
                if op not in (0x5D, 0xB2):
                    pilha.append(r)
            elif op == 0x40 or op == 0x53:
                if op == 0x53:
                    nome = pop()[0]
                    obj = pop()[0]
                    ctor = self.membro(obj, nome)[0] if nome not in (UNDEF, None, "") else obj
                else:
                    nome = _str(pop()[0])
                    ctor = self._variavel(nome, escopo, this)[0]
                n = _int(pop()[0])
                args = [pop() for _ in range(max(0, min(n, 64)))]
                pilha.append(self._novo(ctor, args))
            elif op == 0x42:
                n = _int(pop()[0])
                pilha.append((Lista(self, [pop() for _ in range(max(0, min(n, 4096)))]), None))
            elif op == 0x43:
                n = _int(pop()[0])
                o = Obj(self.proto_objeto)
                for _ in range(max(0, min(n, 4096))):
                    v = pop()
                    k = _str(pop()[0])
                    o.set(k, v)
                pilha.append((o, None))
            elif op == 0x8E or op == 0x9B:
                if op == 0x8E:
                    nome_p, pars, nreg, flags, corpo = arg
                    pars = [(rg, _txt(d, pp)) for rg, pp in pars]
                else:
                    nome_p, pars0, corpo = arg
                    pars, nreg, flags = [(0, _txt(d, pp)) for pp in pars0], 0, 0
                f = Funcao(self, q, corpo, pars, nreg, flags, pool, tuple(escopo), nome=_txt(d, nome_p))
                f.ctx = ctx
                nome = _txt(d, nome_p)
                if nome:
                    self._definir_variavel(nome, (f, None), escopo)
                else:
                    pilha.append((f, None))
                q = q + corpo
            elif op == 0x3E:
                return pop()
            elif op in (0x99, 0x9D, 0xB8):
                salta = True if op == 0x99 else (_bool(pop()[0]) if op == 0x9D else not _bool(pop()[0]))
                if salta and arg < 0:
                    # laço que depende de algo de fora do arquivo (ex.: NUM_TEAMS de outra classe) pode não terminar
                    # na simulação: depois de muitas voltas, segue adiante (sai do laço)
                    voltas[p] = voltas.get(p, 0) + 1
                    if voltas[p] > LIMITE_VOLTAS:
                        self._aviso("laço interrompido em 0x%X (valor de fora do arquivo)" % p)
                        salta = False
                if salta:
                    q = q + arg
            elif op in (0x47, 0x0A, 0x0B, 0x0C, 0x0D, 0x3F, 0x48, 0x0F, 0x49, 0x0E, 0x66, 0x67, 0x10, 0x11, 0x21, 0x13,
                        0x60, 0x61, 0x62, 0x63, 0x64, 0x65):
                b = pop()[0]
                a = pop()[0]
                pilha.append((_binario(op, a, b), None))
            elif op == 0x12:
                pilha.append((not _bool(pop()[0]), None))
            elif op == 0x50:
                pilha.append((_num(pop()[0]) + 1, None))
            elif op == 0x51:
                pilha.append((_num(pop()[0]) - 1, None))
            elif op == 0x4A:
                pilha.append((_num(pop()[0]), None))
            elif op == 0x4B:
                pilha.append((_str(pop()[0]), None))
            elif op == 0x18:
                v = _num(pop()[0])
                pilha.append((int(v) if not math.isnan(v) else 0, None))
            elif op == 0x14:
                pilha.append((len(_str(pop()[0])), None))
            elif op == 0x44:
                pilha.append((_tipo(pop()[0]), None))
            elif op == 0x54:
                pop()
                pop()
                pilha.append((False, None))
            elif op == 0x69:
                sup = pop()[0]
                sub = pop()[0]
                if isinstance(sub, Funcao):
                    pr_sup = sup.get("prototype")[0] if isinstance(sup, Obj) and sup.get("prototype") else Obj(self.proto_objeto)
                    novo = Obj(pr_sup if isinstance(pr_sup, Obj) else self.proto_objeto)
                    novo.set("constructor", (sub, None))
                    sub.set("prototype", (novo, None))
            elif op == 0x2C:
                n = _int(pop()[0])
                for _ in range(max(0, min(n, 64))):
                    pop()
                pop()
            elif op == 0x2B:
                obj = pop()
                pop()
                pilha.append(obj)
            elif op == 0x55:
                obj = pop()[0]
                pilha.append((None, None))
                if isinstance(obj, Obj):
                    for k in list(obj.props.keys())[:500]:
                        pilha.append((k, None))
            elif op == 0x3A:
                nome = _str(pop()[0])
                obj = pop()[0]
                if isinstance(obj, Obj):
                    obj.props.pop(nome, None)
                pilha.append((True, None))
            elif op == 0x3B:
                pop()
                pilha.append((True, None))
            elif op == 0x26:
                pop()
            elif op == 0x34:
                pilha.append((self.tempo * 33.333, None))
            elif op == 0x30:
                pop()
                pilha.append((0, None))
            elif op == 0x22:
                idx = _int(pop()[0])
                alvo = pop()[0]
                k = PROPS_MC[idx] if 0 <= idx < len(PROPS_MC) else ""
                pilha.append((self.ler_prop_clipe(alvo, k) if isinstance(alvo, Clipe) else UNDEF, None))
            elif op == 0x23:
                v = pop()[0]
                idx = _int(pop()[0])
                alvo = pop()[0]
                if isinstance(alvo, Clipe) and 0 <= idx < len(PROPS_MC):
                    self.gravar_prop_clipe(alvo, PROPS_MC[idx], v)
            elif op in (0x06, 0x07, 0x04, 0x05, 0x81, 0x8C, 0x9F, 0x08, 0x09):
                if op == 0x9F:
                    pop()
            elif op == 0x70:
                pilha.append((this, None))          # EA_PushThisVar: o próprio "this"
            elif op == 0x71:
                pilha.append((self.glob, None))     # EA_PushGlobalVar: o objeto global
            elif op == 0x72:
                nome = _str(pop()[0])
                self._definir_variavel(nome, (0, None), escopo)
            elif op == 0xA4:
                pilha.append(self._variavel(_txt(d, arg), escopo, this))
            elif op == 0xA6:
                self._definir_variavel(_txt(d, arg), pop(), escopo)
            elif op in (0x8F, 0x94, 0x2A):
                self._aviso("instrução 0x%02X (try/with/throw) em 0x%X" % (op, p))
                return (UNDEF, None)          # try/with/throw: fora do que o simulador entende
            else:
                self._aviso("instrução desconhecida 0x%02X em 0x%X" % (op, p))
                return (UNDEF, None)
            p = q

    def _aviso(self, msg):
        if len(self.erros) < 50 and msg not in self.erros:
            self.erros.append(msg)

    def _variavel(self, nome, escopo, this):
        if nome == "this":
            return (this, None)
        if nome == "_global":
            return (self.glob, None)
        if nome in ("_root", "_level0"):
            return (self.raiz_clipe, None)
        if "." in nome and not nome.startswith("."):
            partes = nome.split(".")
            v = self._variavel(partes[0], escopo, this)
            for p in partes[1:]:
                v = self.membro(v[0], p)
            return v
        for o in escopo:
            if isinstance(o, Obj):
                r = o.get(nome)
                if r is not None:
                    return r
        if isinstance(this, Clipe):
            r = self.membro(this, nome)
            if not (isinstance(r[0], Duble)):
                return r
        r = self.glob.get(nome)
        if r is not None:
            return r
        return (UNDEF, None)

    def _definir_variavel(self, nome, v, escopo):
        for o in escopo[:-1] if len(escopo) > 1 else escopo:
            if isinstance(o, Obj) and nome in o.props:
                o.props[nome] = v
                return
        escopo[0].set(nome, v)

    def _novo(self, ctor, args):
        if isinstance(ctor, Funcao):
            if ctor.nativa:
                return ctor.nativa(UNDEF, args)
            pr = ctor.get("prototype")
            o = Obj(pr[0] if pr and isinstance(pr[0], Obj) else self.proto_objeto)
            r = self.executar(ctor, o, args)
            return (r[0], r[1]) if isinstance(r[0], Obj) and not isinstance(r[0], Duble) else (o, None)
        if isinstance(ctor, Duble):
            return (Duble("new " + ctor.caminho, args=args), None)
        return (Obj(self.proto_objeto), None)

    # ---------------------------------------------------------- bibliotecas do jogo (AnimationManager, StyleManager)
    def carregar_biblioteca(self, apt_bytes, consts_bytes, nomes):
        """Roda os InitAction de outro arquivo que definem as classes 'nomes' (só as dessas classes)."""
        class _A:
            pass
        a = _A()
        a.d = apt_bytes
        ctx = (apt_bytes, Constantes(consts_bytes))
        try:
            exports = _exports_de(apt_bytes)
        except (struct.error, ValueError, IndexError):
            return
        alvo = {ch for nm, ch in exports if any(nm.endswith(n) for n in nomes)}
        for _t, spr, cod in _itens_quadro0(a):
            if spr not in alvo:
                continue
            try:
                self.metodo_atual = "(biblioteca)"
                self.passos = 0
                self._rodar(cod, None, UNDEF, [(UNDEF, None)] * 8, [self.glob], Pool(), ctx)
            except Exception as ex:
                self._aviso(f"biblioteca: {type(ex).__name__}: {ex}")

    def instalar_nativos_animacao(self):
        gc = self.glob.get("game")[0].get("globalClasses")
        gc = gc[0] if gc else None
        am = gc.get("AnimationManager")[0] if isinstance(gc, Obj) and gc.get("AnimationManager") else None
        if not isinstance(am, Funcao):
            return
        am.set("Animate", self._nat("Animate", lambda t, a: (self._animate(a), (UNDEF, None))[1]))
        am.set("AnimateFrom", self._nat("AnimateFrom", lambda t, a: (self._animate(a, de_inicio=True), (UNDEF, None))[1]))
        am.set("AnimateSequenced", self._nat("AnimateSequenced", lambda t, a: (self._animate([a[0], a[1], a[3], a[4], a[5], a[6], a[7]] if len(a) >= 8 else a, inicio=a[2] if len(a) > 2 else None), (UNDEF, None))[1]))
        for nome in ("ClearAnimations", "KillAnimation", "KillAnimations", "Initialize", "Update"):
            am.set(nome, self._nat(nome, lambda t, a: (UNDEF, None)))

    def curvas(self, amostras=60):
        """{valor: [amostras 0..1]} das curvas do AnimationManager e {EASE_NOME: valor}."""
        jogo = self.glob.get("game")
        gc = jogo[0].get("globalClasses") if jogo and isinstance(jogo[0], Obj) else None
        am = gc[0].get("AnimationManager") if gc and isinstance(gc[0], Obj) else None
        am = am[0] if am else None
        if not isinstance(am, Funcao):
            return {}, {}
        nomes = {k: v[0] for k, v in am.props.items() if k.startswith("EASE_") and isinstance(v[0], str)}
        pr = am.get("prototype")
        out = {}
        for valor in sorted(set(nomes.values())):
            fn = am.get("Ease" + valor) or (pr[0].get("Ease" + valor) if pr and isinstance(pr[0], Obj) else None)
            if not fn or not isinstance(fn[0], Funcao) or fn[0].nativa:
                continue
            pts = []
            try:
                for i in range(amostras + 1):
                    self.passos = 0
                    r = self.chamar(fn[0], am, [(float(i), None), (0, None), (1000, None), (float(amostras), None)])
                    pts.append(round(_num(r[0]) / 1000, 4))
            except Exception:
                continue
            if all(isinstance(x, (int, float)) and math.isfinite(x) and abs(x) < 4 for x in pts):
                out[valor] = pts
        return out, nomes

    # ---------------------------------------------------------- programa
    def rodar_init_actions(self, itens_quadro0):
        for it in itens_quadro0:
            if it[0] == "init":
                try:
                    self.metodo_atual = "(inicialização)"
                    self.passos = 0
                    self._rodar(it[2], None, self.raiz_clipe, [(UNDEF, None)] * 8, [self.glob], Pool())
                except Exception as ex:
                    self.erros.append(f"inicialização: {type(ex).__name__}: {ex}")

    def instanciar(self, clipe):
        """Liga cada clipe com classe registrada ao seu construtor e executa o construtor."""
        feitos = []

        def visitar(c):
            if c.classe and isinstance(self.classes.get(c.classe), Funcao):
                ctor = self.classes[c.classe]
                pr = ctor.get("prototype") if isinstance(ctor, Obj) else None
                if pr and isinstance(pr[0], Obj):
                    c.proto = pr[0]
                    for nome, v in pr[0].props.items():
                        if isinstance(v[0], Funcao):
                            v[0].set("__dono", (pr[0], None))
                try:
                    self.metodo_atual = "(construtor)"
                    self.passos = 0
                    self.executar(ctor, c, [])
                except Exception as ex:  # o simulador é aproximado: segue com o que conseguiu
                    self.erros.append(f"construtor: {type(ex).__name__}: {ex}")
                feitos.append(c)
            for f in c.filhos.values():
                visitar(f)
        visitar(clipe)
        return feitos

    def metodos_de(self, c):
        nomes = []
        o = c.proto
        n = 0
        while isinstance(o, Obj) and o is not self.proto_clipe and o is not self.proto_objeto and n < 10:
            for k, v in o.props.items():
                if isinstance(v[0], Funcao) and not v[0].nativa and k not in nomes:
                    nomes.append(k)
            o = o.proto
            n += 1
        return nomes

    def chamar_metodo(self, c, nome, args=()):
        r = self.membro(c, nome)
        fn = r[0]
        if not isinstance(fn, Funcao):
            return False
        self.metodo_atual = nome
        self.passos = 0
        try:
            self.chamar(fn, c, [(a, None) for a in args])
        except Exception as ex:
            self.erros.append(f"{nome}: {type(ex).__name__}: {ex}")
        return True

    def avancar(self, limite=900):
        """Roda os callbacks agendados (fim das animações, setTimeout) em ordem de tempo."""
        n = 0
        while self.agenda and n < 400:
            self.agenda.sort(key=lambda x: (x[0], x[1]))
            t, _s, fn, this, args = self.agenda.pop(0)
            if t > limite:
                break
            self.tempo = t
            n += 1
            self.passos = 0
            try:
                self.chamar(fn, this, args)
            except Exception as ex:
                self.erros.append(f"callback: {type(ex).__name__}: {ex}")


class SuperRef:
    def __init__(self, proto, this):
        self.proto = proto
        self.this = this

    def membro(self, vm, nome):
        r = self.proto.get(_str(nome)) if isinstance(self.proto, Obj) else None
        return r[0] if r else Duble("super." + _str(nome))


# ------------------------------------------------------------------ conversões

def _int(v):
    n = _num(v)
    try:
        if isinstance(n, float) and (math.isnan(n) or math.isinf(n)):
            return 0
        return int(n)
    except (TypeError, ValueError, OverflowError):
        return 0


def _fin(x):
    return x if not (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else 0


def _mat(fn, x):
    try:
        return fn(x)
    except (ValueError, OverflowError, TypeError):
        return 0


def _num(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v) if any(ch in v for ch in ".eE") else int(v, 0) if v.strip().lower().startswith("0x") else int(v)
        except ValueError:
            try:
                return float(v)
            except ValueError:
                return float("nan")
    if v is None:
        return 0
    return float("nan") if v is UNDEF else 0


def _str(v):
    if isinstance(v, str):
        return v
    if v is UNDEF:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Duble):
        return "[" + v.caminho + "]"
    return "[object]"


def _bool(v):
    if isinstance(v, str):
        return v != ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0 and not (isinstance(v, float) and math.isnan(v))
    if isinstance(v, Duble):
        return False
    if isinstance(v, Obj):
        return True
    return bool(v) if v is not UNDEF and v is not None else False


def _tipo(v):
    if isinstance(v, str):
        return "string"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, Clipe):
        return "movieclip"
    if isinstance(v, Funcao):
        return "function"
    if v is UNDEF:
        return "undefined"
    if v is None:
        return "null"
    return "object"


def _txt(d, ptr):
    if not ptr or ptr >= len(d):
        return ""
    e = d.index(b"\0", ptr)
    return bytes(d[ptr:e]).decode("latin-1")


def _push(t, a):
    if isinstance(t, Lista):
        t.itens.extend(a)
        return len(t.itens)
    return 0


def _binario(op, a, b):
    if op == 0x47:   # Add2
        if isinstance(a, str) or isinstance(b, str):
            return _str(a) + _str(b)
        return _fin(_num(a) + _num(b))
    if op == 0x21:
        return _str(a) + _str(b)
    if op == 0x13:
        return _str(a) == _str(b)
    if op in (0x49, 0x0E):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
        return a is b or a == b
    if op == 0x66:
        return type(a) is type(b) and (a is b or a == b)
    na, nb = _num(a), _num(b)
    try:
        if op == 0x0A:
            return na + nb
        if op == 0x0B:
            return na - nb
        if op == 0x0C:
            return na * nb
        if op == 0x0D:
            return na / nb if nb else 0
        if op == 0x3F:
            return math.fmod(na, nb) if nb else 0
        if op in (0x48, 0x0F):
            return na < nb
        if op == 0x67:
            return na > nb
        if op == 0x10:
            return bool(na) and bool(nb)
        if op == 0x11:
            return bool(na) or bool(nb)
        ia, ib = int(na) if not math.isnan(na) else 0, int(nb) if not math.isnan(nb) else 0
        if op == 0x60:
            return ia & ib
        if op == 0x61:
            return ia | ib
        if op == 0x62:
            return ia ^ ib
        if op == 0x63:
            return (ia << (ib & 31)) & 0xFFFFFFFF
        if op in (0x64, 0x65):
            return ia >> (ib & 31)
    except (TypeError, OverflowError, ValueError):
        return 0
    return 0


# ------------------------------------------------------------------ análise de um overlay

def _limites_char(modelo):
    """Limites (no espaço do próprio character) de cada character, quadro 0."""
    chars = modelo["chars"]
    cache = {}

    def calc(i, nivel=0):
        if i in cache:
            return cache[i]
        cache[i] = None
        c = chars[i] if 0 <= i < len(chars) else None
        r = None
        if c and c["t"] == "forma":
            r = list(c["limites"])
        elif c and c["t"] == "texto":
            r = list(c["limites"])
        elif c and c.get("quadros") and nivel < 30:
            for it in (c["quadros"][0] if c["quadros"] else []):
                if it["t"] != "place" or (it["fl"] & 64):
                    continue
                b = calc(it["char"], nivel + 1)
                if not b:
                    continue
                m, t = it["m"], it["tx"]
                for x, y in ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])):
                    px, py = m[0] * x + m[2] * y + t[0], m[1] * x + m[3] * y + t[1]
                    if r is None:
                        r = [px, py, px, py]
                    else:
                        r = [min(r[0], px), min(r[1], py), max(r[2], px), max(r[3], py)]
        cache[i] = r
        return r
    return calc


def _exports_de(apt_bytes):
    d = apt_bytes
    p = d.find(struct.pack("<QQ", 9, 0x09876543))
    q = p + 32
    nimp = struct.unpack_from("<4I", d, q + 40)[3]
    nexp, pexp = struct.unpack_from("<QQ", d, q + 64)
    return [(_txt(d, struct.unpack_from("<Q", d, pexp + 16 * i)[0]), struct.unpack_from("<Q", d, pexp + 16 * i + 8)[0]) for i in range(nexp)]


def simular(overlay, metodos=("AnimateIn",), limite=900, bibliotecas=(), tema=None):
    """Roda a classe do overlay e devolve constantes, formatos de texto, métodos e a linha do tempo."""
    modelo = overlay.modelo()
    a = overlay.apt
    consts = Constantes(overlay.entrada("1"))
    exports = [(e["nome"], e["char"]) for e in modelo["exports"]]
    calc_lim = _limites_char(modelo)
    sim = Simulador(bytes(a.d), consts, exports, lambda ch: (modelo["chars"][ch] or {}).get("quadros") if 0 <= ch < len(modelo["chars"]) else None,
                    calc_lim, modelo["chars"])
    sim.metodo_atual = ""
    sim.tema = dict(tema or {})
    raiz = sim.criar_clipes(0, "", "", calc_lim(0))
    sim.raiz_clipe = raiz
    for apt_b, consts_b, nomes in bibliotecas:
        sim.carregar_biblioteca(apt_b, consts_b, nomes)
    sim.instalar_nativos_animacao()
    itens = []
    for it in _itens_quadro0(a):
        itens.append(it)
    sim.rodar_init_actions(itens)
    sim.instalar_nativos_animacao()       # o overlay pode trazer a própria cópia do AnimationManager
    instancias = sim.instanciar(raiz)
    principal = instancias[0] if instancias else None
    resultado = {"metodos": [], "constantes": [], "formatos": [], "tweens": [], "eventos": [], "textos": {},
                 "classe": principal.classe if principal else None, "alvo": principal.caminho if principal else None,
                 "erros": sim.erros[:20], "mspf": a.mspf, "fps": 60 if a.mspf and a.mspf <= 20 else 30,
                 "curvas": {}, "curvas_nomes": {}, "inicial": [], "marcas": [], "duracao": 0}
    try:
        resultado["curvas"], resultado["curvas_nomes"] = sim.curvas()
    except Exception as ex:
        sim.erros.append(f"curvas: {type(ex).__name__}: {ex}")
    if principal is None:
        return resultado
    resultado["metodos"] = sim.metodos_de(principal)
    sim.eventos = []
    sim.tempo = 0.0
    antes = {(c.caminho, k): v for c in _todos(raiz) if c.caminho for k, v in c.estado.items()}
    for m in ("Initialize", "Init"):
        if m in resultado["metodos"]:
            sim.chamar_metodo(principal, m)
            break
    sim.agenda = []
    estado_pos_init = []
    pos_init = {(c.caminho, k): v for c in _todos(raiz) if c.caminho for k, v in c.estado.items()}
    for c in _todos(raiz):
        if c.caminho:
            for k in PROPS_ANIM:
                if k in c.estado and antes.get((c.caminho, k)) != c.estado[k]:
                    estado_pos_init.append((c.caminho, k, c.estado[k]))
    sim.eventos = []
    sim.tweens = []
    sim.tempo = 0.0
    marcas = []
    for i, m in enumerate(metodos):
        if m not in resultado["metodos"]:
            continue
        if i:
            # o próximo método começa depois de tudo terminar (+1 s), com os clipes já nas posições finais
            sim.avancar(limite)
            fim = max([tw["t0"] + tw["dur"] for tw in sim.tweens] + [e[0] for e in sim.eventos] + [sim.tempo])
            for tw in sim.tweens:
                if tw["_clipe"] is not None:
                    tw["_clipe"].estado[tw["prop"]] = tw["para"]
            sim.tempo = fim + 30
        marcas.append({"metodo": m, "t": sim.tempo})
        sim.chamar_metodo(principal, m)
    sim.avancar(limite)
    resultado["marcas"] = marcas
    # valores de partida de cada interpolação: o estado no instante em que ela começa
    linha = sorted([("set", t, cam, k, v) for (t, cam, k, v) in sim.eventos] +
                   [("tw", tw["t0"], tw["alvo"], tw["prop"], tw) for tw in sim.tweens], key=lambda x: (x[1], 0 if x[0] == "set" else 1))
    atual = dict(pos_init)
    tweens = []
    eventos = []
    for tipo, t, cam, k, v in linha:
        if tipo == "set":
            atual[(cam, k)] = v
            eventos.append({"t": round(t, 3), "alvo": cam, "prop": k, "valor": v})
        else:
            clipe = v["_clipe"]
            base_tw = {kk: vv for kk, vv in v.items() if kk != "_clipe"}
            if k == "_scale":                      # as duas escalas
                conv = [("_xscale", 1.0), ("_yscale", 1.0)]
            elif k in ("_width", "_height"):       # largura/altura = escala × tamanho do clipe
                b = clipe.limites if clipe is not None else None
                base = ((b[2] - b[0]) if k == "_width" else (b[3] - b[1])) if b else 0
                conv = [("_xscale" if k == "_width" else "_yscale", 100.0 / base)] if base else []
            else:
                conv = [(k, None)]
            for k2, fator in conv:
                tw = dict(base_tw)
                if k2 != k:
                    tw["prop"] = k2
                    tw["prop_original"] = k
                    tw["para_original"] = tw["para"]
                    tw["para"] = _num(tw["para"]) * fator
                de = atual.get((cam, k2))
                if de is None:
                    de = sim.ler_prop_clipe(clipe, k2) if clipe is not None else 0
                tw["de"] = _num(de) if k2 != "_visible" else bool(de)
                if k2 != k:
                    tw["de_original"] = tw["de"] / fator if fator else tw["de"]
                tweens.append(tw)
                atual[(cam, k2)] = tw["para"]
    resultado["inicial"] = [{"alvo": cam, "prop": k, "valor": v if k != "_visible" else bool(v)} for cam, k, v in estado_pos_init]
    resultado["eventos"] = eventos
    resultado["tweens"] = tweens
    resultado["duracao"] = max([tw["t0"] + tw["dur"] for tw in tweens] + [e["t"] for e in eventos] + [0])
    resultado["constantes"] = sorted(sim.constantes.values(), key=lambda x: x["nome"])
    resultado["formatos"] = _formatos_unicos(sim.formatos)
    resultado["textos"] = sim.textos
    resultado["erros"] = sim.erros[:20]
    return resultado


def _formatos_unicos(lst):
    vistos = set()
    out = []
    for f in lst:
        k = (f.get("fonte_slot"), f.get("tamanho_slot"))
        if k in vistos:
            continue
        vistos.add(k)
        out.append(f)
    return out


def _todos(c):
    yield c
    for f in c.filhos.values():
        yield from _todos(f)


def _itens_quadro0(apt):
    """[('init', sprite, código)] dos InitAction do quadro 0 do filme."""
    d = apt.d
    p = d.find(struct.pack("<QQ", 9, 0x09876543))
    q = p + 32
    nq, pq = struct.unpack_from("<QQ", d, q)
    if not nq:
        return []
    ni, lp = struct.unpack_from("<QQ", d, pq)
    out = []
    for j in range(ni):
        ip = struct.unpack_from("<Q", d, lp + 8 * j)[0]
        t = struct.unpack_from("<Q", d, ip)[0]
        if t == 8:
            out.append(("init", struct.unpack_from("<Q", d, ip + 8)[0], struct.unpack_from("<Q", d, ip + 16)[0]))
    return out


# ------------------------------------------------------------------ edição de textos usados pelo código

def trocar_texto_slot(apt_dados, consts, slot, novo):
    """Faz a entrada 'slot' (usada num PushData) passar a valer o texto 'novo'.

    A entrada costuma ser um "lookup" no ConstantPool. Para não mexer nos outros usos do mesmo texto, o editor
    cria um item de texto novo na tabela de constantes, copia o ConstantPool (para o fim do APT) com mais uma
    posição e aponta a entrada para essa posição — o mesmo mecanismo que o próprio jogo usa.
    Devolve os bytes novos do APT (a tabela de constantes é alterada no objeto 'consts')."""
    d = bytearray(apt_dados)
    t, v = consts.item(slot)
    if t == T_TEXTO:
        i = consts.achar_texto(novo)
        if i is None:
            i = consts.acrescentar_texto(novo)
        consts.apontar_texto(slot, i)
        return bytes(d)
    if t != T_LOOKUP:
        raise ErroAS("Esta entrada não é um texto")
    # acha o ConstantPool que vale para o PushData que usa a entrada
    pool_pos = _pool_do_slot(d, consts, slot)
    if pool_pos is None:
        raise ErroAS("Não achei o ConstantPool desse texto")
    p_cnt = (pool_pos + 1 + 7) // 8 * 8
    cnt, ptr = struct.unpack_from("<QQ", d, p_cnt)
    idx = list(struct.unpack_from("<%dQ" % cnt, d, ptr))
    item = consts.achar_texto(novo)
    if item is None:
        item = consts.acrescentar_texto(novo)
    if item in idx:
        nova_pos = idx.index(item)
    else:
        idx.append(item)
        while len(d) % 8:
            d.append(0)
        novo_ptr = len(d)
        d += struct.pack("<%dQ" % len(idx), *idx)
        struct.pack_into("<QQ", d, p_cnt, len(idx), novo_ptr)
        nova_pos = len(idx) - 1
    struct.pack_into("<QQ", consts.d, consts.base + 16 * slot, T_LOOKUP, nova_pos)
    return bytes(d)


def _pool_do_slot(d, consts, slot):
    """Varre o código de todos os InitAction até o PushData que usa 'slot'; devolve a posição do ConstantPool
    ativo naquele ponto."""
    class _A:
        pass
    a = _A()
    a.d = d
    for _tipo_it, _spr, codigo in _itens_quadro0(a):
        p = codigo
        pool_pos = None
        fins = []
        n = 0
        while n < 2_000_000:
            n += 1
            try:
                op, arg, q = decodificar(d, p)
            except (struct.error, IndexError, ErroAS):
                break
            fins = [f for f in fins if f > p]
            if op == 0x88:
                pool_pos = p
            elif op == 0x96:
                ptr, cnt = arg
                if slot in struct.unpack_from("<%dQ" % cnt, d, ptr):
                    return pool_pos
            elif op == 0x8E:
                fins.append(q + arg[4])
            elif op == 0x9B:
                fins.append(q + arg[2])
            elif op == 0x00 and not fins:
                break
            p = q
    return None


# ------------------------------------------------------------------ edição por origem ("c:123", "pb:4567"...)

def editar_numero(apt_d, consts, slot, valor):
    """Troca um número usado pelo código. apt_d é um bytearray (alterado no lugar)."""
    tipo, _, resto = slot.partition(":")
    if tipo == "c":
        consts.definir_numero(int(resto), float(valor))
        return
    pos = int(resto.split(":")[0])
    v = float(valor)
    if tipo == "pb":
        if not (0 <= v <= 255 and v.is_integer()):
            raise ErroAS("Este número fica num byte do código: use um inteiro de 0 a 255.")
        apt_d[pos] = int(v)
    elif tipo == "ps":
        if not (0 <= v <= 65535 and v.is_integer()):
            raise ErroAS("Este número fica em 2 bytes do código: use um inteiro de 0 a 65535.")
        struct.pack_into("<H", apt_d, pos, int(v))
    elif tipo == "pl":
        if not (0 <= v <= 0xFFFFFFFF and v.is_integer()):
            raise ErroAS("Use um inteiro positivo.")
        struct.pack_into("<I", apt_d, pos, int(v))
    elif tipo == "pf":
        struct.pack_into("<f", apt_d, pos, v)
    else:
        raise ErroAS("Este valor não é um número editável.")


def editar_texto(apt_d, consts, slot, novo):
    """Troca um texto usado pelo código (nome de fonte, curva de animação...) só naquele ponto.
    Devolve o bytearray do APT (pode crescer: ConstantPool estendido no fim)."""
    tipo, _, resto = slot.partition(":")
    if tipo == "c":
        return bytearray(trocar_texto_slot(bytes(apt_d), consts, int(resto), novo))
    if tipo not in ("pk", "pkw"):
        raise ErroAS("Este valor não é um texto editável.")
    pos_s, _, pool_s = resto.partition(":")
    pos = int(pos_s)
    if pool_s in ("", "None"):
        raise ErroAS("Não achei o ConstantPool deste texto.")
    pool_pos = int(pool_s)
    p_cnt = (pool_pos + 1 + 7) // 8 * 8
    cnt, ptr = struct.unpack_from("<QQ", apt_d, p_cnt)
    idx = list(struct.unpack_from("<%dQ" % cnt, apt_d, ptr))
    item = consts.achar_texto(novo)
    if item is None:
        item = consts.acrescentar_texto(novo)
    if item in idx:
        k = idx.index(item)
    else:
        idx.append(item)
        k = len(idx) - 1
        while len(apt_d) % 8:
            apt_d.append(0)
        novo_ptr = len(apt_d)
        apt_d += struct.pack("<%dQ" % len(idx), *idx)
        struct.pack_into("<QQ", apt_d, p_cnt, len(idx), novo_ptr)
    if tipo == "pk":
        if k > 255:
            raise ErroAS("Sem espaço para mais um texto neste trecho do código (limite de 256).")
        apt_d[pos] = k
    else:
        struct.pack_into("<H", apt_d, pos, k)
    return apt_d
