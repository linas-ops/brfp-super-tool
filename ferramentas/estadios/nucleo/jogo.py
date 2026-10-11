"""Leitura direta do FC 26 instalado: lista de todas as texturas do jogo, GUIDs e imagens (PNG).

Como funciona:
- O índice dos assets vem do próprio jogo (nucleo/toc.py: layout.toc, .toc dos superbundles e os manifestos dos
  bundles nos CAS) — nome, tamanhos e a posição de cada asset no arquivo CAS. Se isso falhar, usa o cache que o
  FMT (Frostbite Modding Tool) monta ao abrir o jogo (`_GameCaches/FC26.cache`, deflate).
- Os dados ficam em `Data|Patch/Win32/superbundlelayout/<pacote>/cas_NN.cas`, em blocos do Frostbite
  (cabeçalho de 8 bytes: tamanho descomprimido, tipo, tamanho comprimido) comprimidos com Oodle
  (`oo2core_9_win64.dll`, na pasta do jogo).
- TextureAsset (EBX RIFF): o GUID da instância principal são os 16 primeiros bytes do bloco EBXD.
- Recurso Texture (RES de mesmo nome): formato (RenderFormat), largura, altura, mips, firstMip, GUID do
  chunk de pixels e tamanho de cada mip. O chunk tem os mips a partir de um nível k (deduzido do tamanho).
- O PNG é gerado pelo texconv (DirectXTex) a partir de um DDS montado com o mip escolhido.
O índice próprio do editor (compacto) é salvo em editor/cache/ e refeito quando o jogo (ou o cache do FMT) muda.
"""
import bisect
import ctypes
import glob
import hashlib
import json
import os
import pickle
import re
import struct
import subprocess
import threading
import time
import uuid
import zlib

from . import toc as TOC
from . import xmlfet as X

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(AQUI, "cache")
TEXCONV = os.path.join(AQUI, "ferramentas", "texconv.exe")
VERSAO_INDICE = 3
RES_TEXTURE = 0x6BDE20BA
_RX_TIPO = re.compile(b"[\x70-\x7f]")   # byte baixo do tipo do bloco: 0x7N (N = bits altos do tamanho)

# RenderFormat (FC26SDK: Frostbite.RenderBase.RenderFormat) -> (DXGI, bytes por bloco 4x4 ou por pixel, é BC, sRGB)
FORMATOS = {
    54: (71, 8, True, False), 55: (72, 8, True, True), 56: (71, 8, True, False), 57: (72, 8, True, True),
    58: (74, 16, True, False), 59: (75, 16, True, True), 60: (77, 16, True, False), 61: (78, 16, True, True),
    62: (80, 8, True, False), 63: (83, 16, True, False), 64: (95, 16, True, False), 65: (96, 16, True, False),
    66: (98, 16, True, False), 67: (99, 16, True, True),
    6: (61, 1, False, False), 8: (61, 1, False, True), 11: (49, 2, False, False), 13: (49, 2, False, True),
    18: (28, 4, False, False), 20: (29, 4, False, True), 23: (87, 4, False, False), 24: (91, 4, False, True),
    30: (54, 2, False, False), 31: (56, 2, False, False), 35: (34, 4, False, False), 40: (10, 8, False, False),
    45: (41, 4, False, False),
}
NOMES_FORMATO = {54: "BC1", 55: "BC1 sRGB", 56: "BC1A", 57: "BC1A sRGB", 58: "BC2", 59: "BC2 sRGB", 60: "BC3", 61: "BC3 sRGB",
                 62: "BC4", 63: "BC5", 64: "BC6H", 65: "BC6H", 66: "BC7", 67: "BC7 sRGB", 18: "RGBA8", 20: "RGBA8 sRGB",
                 23: "BGRA8", 24: "BGRA8 sRGB", 6: "R8", 11: "RG8"}


class ErroJogo(Exception):
    pass


# ------------------------------------------------------------------ detecção

_DETECTADO = {}   # as buscas varrem pastas inteiras (segundos): faz uma vez por execução


def _memo(nome, fn, forcar):
    if forcar or nome not in _DETECTADO:
        _DETECTADO[nome] = fn()
    v = _DETECTADO[nome]
    if v and not os.path.exists(v):   # sumiu desde a última busca
        v = _DETECTADO[nome] = fn()
    return v


def detectar_pasta_jogo(forcar=False):
    return _memo("pasta", _buscar_pasta_jogo, forcar)


def detectar_cache_fmt(forcar=False):
    return _memo("cache", _buscar_cache_fmt, forcar)


def _buscar_pasta_jogo():
    cands = []
    try:
        import winreg

        def valor(raiz, sub, nome):
            try:
                with winreg.OpenKey(raiz, sub) as k:
                    return winreg.QueryValueEx(k, nome)[0]
            except OSError:
                return None
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\EA Sports\EA SPORTS FC 26", r"SOFTWARE\WOW6432Node\EA Sports\EA SPORTS FC 26",
                        r"SOFTWARE\EA Games\EA SPORTS FC 26", r"SOFTWARE\WOW6432Node\EA Games\EA SPORTS FC 26"):
                for nome in ("Install Dir", "InstallDir"):
                    v = valor(raiz, sub, nome)
                    if v:
                        cands.append(v)
            # desinstaladores (EA app, Steam, Xbox)
            for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                try:
                    with winreg.OpenKey(raiz, sub) as k:
                        for i in range(winreg.QueryInfoKey(k)[0]):
                            try:
                                filho = sub + "\\" + winreg.EnumKey(k, i)
                                nome = valor(raiz, filho, "DisplayName") or ""
                                if "FC 26" in nome or "FC26" in nome:
                                    v = valor(raiz, filho, "InstallLocation")
                                    if v:
                                        cands.append(v)
                            except OSError:
                                pass
                except OSError:
                    pass
        steam = valor(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath")
        if steam:
            bibl = [steam]
            try:
                vdf = open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace").read()
                bibl += [x.replace("\\\\", "\\") for x in re.findall(r'"path"\s+"([^"]+)"', vdf)]
            except OSError:
                pass
            cands += [os.path.join(b, "steamapps", "common", "EA SPORTS FC 26") for b in bibl]
    except ImportError:
        pass
    casa = os.path.expanduser("~")
    for cfg in glob.glob(os.path.join(casa, "Downloads", "**", "FIFA Editor Tool.json"), recursive=True)[:3]:
        try:
            j = json.load(open(cfg, encoding="utf-8-sig"))
            for exe in j.get("GamesConfig", {}).get("ExecutablePaths", []):
                if "26" in exe:
                    cands.append(os.path.dirname(exe))
        except (OSError, ValueError):
            pass
    for u in "CDEFGH":
        raiz = u + ":\\"
        if not os.path.isdir(raiz):
            continue
        for rel in (r"Program Files\EA Games\EA SPORTS FC 26", r"EA Games\EA SPORTS FC 26", r"Games\EA SPORTS FC 26",
                    r"Jogos\EA SPORTS FC 26", r"SteamLibrary\steamapps\common\EA SPORTS FC 26",
                    r"Program Files (x86)\Steam\steamapps\common\EA SPORTS FC 26", r"XboxGames\EA SPORTS FC 26\Content",
                    "EA SPORTS FC 26"):
            cands.append(os.path.join(raiz, rel))
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "oo2core_9_win64.dll")) and os.path.isdir(os.path.join(c, "Data", "Win32")):
            return os.path.abspath(c)
    return None


def _buscar_cache_fmt():
    casa = os.path.expanduser("~")
    padroes = [os.path.join(casa, "Desktop", "**", "_GameCaches", "FC26.cache"),
               os.path.join(casa, "Downloads", "**", "_GameCaches", "FC26.cache"),
               os.path.join(casa, "Documents", "**", "_GameCaches", "FC26.cache"),
               os.path.join(casa, "AppData", "**", "_GameCaches", "FC26.cache")]
    for pad in padroes:
        try:
            achados = glob.glob(pad, recursive=True)
        except OSError:
            achados = []
        achados = [a for a in achados if os.path.getsize(a) > 10_000_000]
        if achados:
            return max(achados, key=os.path.getmtime)
    return None


# ------------------------------------------------------------------ leitura binária

def _v7(b, p):
    r = s = 0
    while True:
        c = b[p]
        p += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, p


def _str(b, p):
    n, p = _v7(b, p)
    return b[p:p + n], p + n


def _loc(b, p):
    """[temCas][off u32, pacote u16, cas u16, patch u8][temSb][toc str, u32, u32][n u32][n x u32]"""
    tem = b[p]
    p += 1
    loc = None
    if tem:
        loc = struct.unpack_from("<IHHB", b, p)
        p += 9
    if b[p]:
        p += 1
        n, p = _v7(b, p)
        p += n + 8
    else:
        p += 1
    cnt = struct.unpack_from("<I", b, p)[0]
    p += 4 + 4 * cnt
    return loc, p


class Oodle:
    def __init__(self, pasta_jogo):
        dll = os.path.join(pasta_jogo, "oo2core_9_win64.dll")
        if not os.path.isfile(dll):
            raise ErroJogo("oo2core_9_win64.dll não encontrada na pasta do jogo")
        self.dll = ctypes.WinDLL(dll)
        f = self.dll.OodleLZ_Decompress
        f.restype = ctypes.c_int64
        f.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                      ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64, ctypes.c_int]
        self.f = f
        self.lock = threading.Lock()

    def descomprimir(self, dados, tamanho):
        src = ctypes.create_string_buffer(dados, len(dados))
        dst = ctypes.create_string_buffer(tamanho)
        r = self.f(src, len(dados), dst, tamanho, 1, 0, 0, None, 0, None, None, None, 0, 3)
        if r != tamanho:
            raise ErroJogo(f"Oodle não descomprimiu ({r} de {tamanho} bytes)")
        return dst.raw


# ------------------------------------------------------------------ índice

def construir_indice(caminho_cache, progresso=None):
    """Lê o FC26.cache do FMT e devolve o índice compacto do editor."""
    def prog(f, msg):
        if progresso:
            progresso(f, msg)
    with open(caminho_cache, "rb") as fh:
        bruto = fh.read()
    if bruto[4:9] != b"\x04FC26":
        raise ErroJogo("O cache do FMT não é do FC 26")
    ini = None
    for off in range(0x10, 0x60):
        try:
            d = zlib.decompressobj(-15)
            if len(d.decompress(bruto[off:off + 65536])) > 1000:
                ini = off
                break
        except zlib.error:
            continue
    if ini is None:
        raise ErroJogo("Formato do cache do FMT não reconhecido")
    d = zlib.decompressobj(-15)
    partes, passo = [], 8 << 20
    for i in range(ini, len(bruto), passo):
        partes.append(d.decompress(bruto[i:i + passo]))
        prog(0.25 * min(1, (i - ini) / max(1, len(bruto) - ini)), "Descompactando o índice do FMT")
    partes.append(d.flush())
    del bruto
    b = b"".join(partes)
    del partes
    p = 0
    # bundles
    n = struct.unpack_from("<I", b, p)[0]
    p += 4
    for _ in range(n):
        L = struct.unpack_from("<H", b, p)[0]
        p += 2 + L + 4
    # pastas
    n = struct.unpack_from("<I", b, p)[0]
    p += 4
    pastas = {}
    for _ in range(n):
        h = b[p:p + 8]
        s, p = _str(b, p + 8)
        pastas[h] = s.decode("utf-8", "replace")
    prog(0.3, "Lendo assets do jogo")
    # EBX
    n = struct.unpack_from("<I", b, p)[0]
    p += 4
    texturas = {}
    tipos = {}
    for i in range(n):
        fh = b[p:p + 8]
        nome, p = _str(b, p + 8)
        p += 20
        csz, osz = struct.unpack_from("<qq", b, p)
        p += 17                       # 2 x int64 + byte
        tipo, p = _str(b, p)
        guid = b[p:p + 16]
        p += 16
        loc, p = _loc(b, p)
        if tipo == b"TextureAsset" and loc:
            nm = pastas.get(fh, "") + nome.decode("utf-8", "replace")
            texturas[nm.lower()] = (nm, guid, loc, csz, osz)
        if i % 100000 == 0:
            prog(0.3 + 0.35 * i / n, "Lendo assets do jogo")
        tipos[tipo] = tipos.get(tipo, 0) + 1
    # RES
    n = struct.unpack_from("<I", b, p)[0]
    p += 4
    res = {}
    for i in range(n):
        fh = b[p:p + 8]
        nome, p = _str(b, p + 8)
        p += 20
        csz, osz = struct.unpack_from("<qq", b, p)
        p += 17
        _, p = _str(b, p)
        rtype = struct.unpack_from("<I", b, p + 8)[0]
        p += 12
        ml = struct.unpack_from("<H", b, p)[0]
        p += 2 + ml
        loc, p = _loc(b, p)
        if rtype == RES_TEXTURE and loc:
            res[(pastas.get(fh, "") + nome.decode("utf-8", "replace")).lower()] = (loc, csz, osz)
        if i % 100000 == 0:
            prog(0.65 + 0.15 * i / n, "Lendo recursos de textura")
    # chunks: [id 16][sha1 20][tam i64][byte][27 bytes][off u32][pacote u16][cas u16][patch u8][u32][u32][n u16][n x u32]
    n = struct.unpack_from("<I", b, p)[0]
    p += 4
    ids, regs = [], []
    for i in range(n):
        cid = b[p:p + 16]
        csz = struct.unpack_from("<q", b, p + 36)[0]
        q = p + 45
        s1, s2 = struct.unpack_from("<II", b, q + 27 + 9)
        if s2 != s1 + 4:   # layout inesperado: procura a âncora (u32, u32 = anterior + 4)
            for q2 in range(p + 45, p + 45 + 64):
                s1, s2 = struct.unpack_from("<II", b, q2 + 9)
                if s2 == s1 + 4:
                    q = q2 - 27
                    break
        off, ic, cas, patch = struct.unpack_from("<IHHB", b, q + 27)
        cnt = struct.unpack_from("<H", b, q + 27 + 17)[0]
        p = q + 27 + 19 + 4 * cnt
        ids.append(cid)
        regs.append((off, ic, cas, patch, csz))
        if i % 100000 == 0:
            prog(0.8 + 0.15 * i / n, "Lendo chunks de pixels")
    ordem = sorted(range(len(ids)), key=ids.__getitem__)
    ids_ord = b"".join(ids[i] for i in ordem)
    regs_ord = b"".join(struct.pack("<IHHBq", *regs[i]) for i in ordem)
    texturas = {k: v for k, v in texturas.items() if k in res}
    prog(1.0, "Pronto")
    return {"versao": VERSAO_INDICE, "texturas": texturas, "res": {k: res[k] for k in texturas},
            "chunk_ids": ids_ord, "chunk_regs": regs_ord, "pacotes": {}}


class Jogo:
    def __init__(self, pasta_jogo, caminho_cache=None):
        self.pasta = pasta_jogo
        self.cache_fmt = caminho_cache
        self.indice = None
        self.oodle = None
        self.estado = "parado"
        self.progresso = 0.0
        self.mensagem = ""
        self.erro = None
        self.lock = threading.Lock()
        self._travas = {}
        self._lista = None

    # ---------------------------------------------------------- estado / carga em segundo plano
    def assinatura(self, nativo=True):
        """Muda quando o jogo é atualizado (layout.toc de Data/Patch) ou, no modo FMT, quando o cache muda."""
        if nativo:
            partes = []
            for raiz in ("Data", "Patch"):
                c = os.path.join(self.pasta, raiz, "layout.toc")
                if os.path.isfile(c):
                    st = os.stat(c)
                    partes.append(f"{st.st_size}:{int(st.st_mtime)}")
            return f"{VERSAO_INDICE}|jogo|{'|'.join(partes)}|{self.pasta.lower()}"
        st = os.stat(self.cache_fmt)
        return f"{VERSAO_INDICE}|{st.st_size}|{int(st.st_mtime)}|{self.pasta.lower()}"

    def arquivo_indice(self):
        return os.path.join(CACHE_DIR, "indice_fc26.pkl")

    def iniciar(self):
        with self.lock:
            if self.estado in ("indexando", "pronto"):
                return
            self.estado = "indexando"
            self.erro = None
        threading.Thread(target=self._carregar, daemon=True).start()

    def _prog(self, f, msg):
        self.progresso, self.mensagem = f, msg

    def _carregar(self):
        try:
            self.oodle = Oodle(self.pasta)
            arq = self.arquivo_indice()
            aceitas = [self.assinatura(True)]
            if self.cache_fmt and os.path.isfile(self.cache_fmt):
                aceitas.append(self.assinatura(False))
            idx = None
            if os.path.isfile(arq):
                self._prog(0.05, "Abrindo o índice salvo")
                try:
                    with open(arq, "rb") as f:
                        salvo = pickle.load(f)
                    if salvo.get("assinatura") in aceitas:
                        idx = salvo
                except (OSError, pickle.PickleError, EOFError, AttributeError):
                    idx = None
            if idx is None:
                try:   # leitura direta dos .toc do jogo (não precisa do FMT)
                    idx = TOC.construir_indice(self.pasta, self._prog, VERSAO_INDICE)
                    idx["assinatura"] = aceitas[0]
                    self.indice = idx
                except (TOC.ErroToc, OSError, struct.error, ValueError, IndexError, KeyError) as ex:
                    if len(aceitas) < 2:
                        raise ErroJogo(f"Não consegui ler o catálogo do jogo ({ex})")
                    idx = construir_indice(self.cache_fmt, self._prog)
                    idx["assinatura"] = aceitas[1]
                    self.indice = idx
                    self._prog(0.97, "Identificando os pacotes de instalação")
                    self.mapear_pacotes()
                os.makedirs(CACHE_DIR, exist_ok=True)
                tmp = arq + ".tmp"
                with open(tmp, "wb") as f:
                    pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp, arq)
            self.indice = idx
            self._lista = None
            self.estado = "pronto"
            self._prog(1.0, f"{len(idx['texturas']):,} texturas".replace(",", "."))
        except Exception as ex:  # o editor continua funcionando sem o jogo
            self.estado = "erro"
            self.erro = f"{type(ex).__name__}: {ex}"

    def info(self):
        fonte = (self.indice or {}).get("fonte") or ("fmt" if self.indice else None)
        return {"estado": self.estado, "progresso": round(self.progresso, 3), "mensagem": self.mensagem, "erro": self.erro,
                "pasta": self.pasta, "cache": self.cache_fmt, "fonte": fonte,
                "texturas": len(self.indice["texturas"]) if self.indice and self.estado == "pronto" else 0,
                "texconv": os.path.isfile(TEXCONV)}

    # ---------------------------------------------------------- pacotes de instalação (índice -> pasta)
    def _caminho_cas(self, pasta_pacote, cas, patch):
        return os.path.join(self.pasta, "Patch" if patch else "Data", "Win32", "superbundlelayout", pasta_pacote, "cas_%02d.cas" % cas)

    def mapear_pacotes(self):
        """Descobre qual pasta superbundlelayout/<x> corresponde a cada índice de pacote, testando cabeçalhos de bloco."""
        idx = self.indice
        amostras = {}
        for nm, (_, _, loc, csz, osz) in idx["texturas"].items():
            off, ic, cas, patch = loc
            lst = amostras.setdefault(ic, [])
            if len(lst) < 6:
                lst.append((off, cas, patch, osz))
        for loc, csz, osz in idx["res"].values():
            off, ic, cas, patch = loc
            lst = amostras.setdefault(ic, [])
            if len(lst) < 6:
                lst.append((off, cas, patch, osz))
        regs = idx["chunk_regs"]
        for i in range(0, min(len(regs) // 17, 400000), 7):
            off, ic, cas, patch, csz = struct.unpack_from("<IHHBq", regs, i * 17)
            lst = amostras.setdefault(ic, [])
            if len(lst) < 6:
                lst.append((off, cas, patch, None))
        pastas = sorted({os.path.basename(p) for base in ("Data", "Patch")
                         for p in glob.glob(os.path.join(self.pasta, base, "Win32", "superbundlelayout", "*")) if os.path.isdir(p)})
        mapa = {}
        for ic, lst in amostras.items():
            for pasta in pastas:
                ok = 0
                for off, cas, patch, osz in lst:
                    c = self._caminho_cas(pasta, cas, patch)
                    try:
                        if os.path.getsize(c) < off + 8:
                            break
                        with open(c, "rb") as f:
                            f.seek(off)
                            h = f.read(8)
                    except OSError:
                        break
                    dsz = struct.unpack(">I", h[:4])[0] & 0xFFFFFF
                    tipo = struct.unpack(">H", h[4:6])[0]
                    tam_ok = osz is None or dsz == osz or (osz > dsz and dsz >= 0x10000)
                    if (tipo & 0xF0) == 0x70 and 0 < dsz <= 0x1000000 and tam_ok and (tipo >> 8) in (0, 0x02, 0x0F, 0x11, 0x15, 0x19, 0x1B):
                        ok += 1
                    else:
                        break
                if ok == len(lst):
                    mapa[ic] = pasta
                    break
        idx["pacotes"] = mapa

    # ---------------------------------------------------------- leitura
    def pronto(self):
        if self.estado != "pronto":
            raise ErroJogo(self.erro or "O índice do jogo ainda não está pronto")

    def ler(self, loc, total=None, comprimido=None):
        """Lê blocos do CAS a partir de loc até descomprimir 'total' bytes (ou consumir 'comprimido' bytes)."""
        off, ic, cas, patch = loc[:4]
        pasta = self.indice["pacotes"].get(ic)
        if pasta is None:
            raise ErroJogo(f"Pacote de instalação {ic} não identificado")
        caminho = self._caminho_cas(pasta, cas, patch)
        out = bytearray()
        lidos = 0
        with open(caminho, "rb") as f:
            f.seek(off)
            while True:
                if total is not None and len(out) >= total:
                    break
                if comprimido is not None and lidos >= comprimido:
                    break
                h = f.read(8)
                if len(h) < 8:
                    break
                dsz = struct.unpack(">I", h[:4])[0] & 0xFFFFFF
                tipo = struct.unpack(">H", h[4:6])[0]
                csz = struct.unpack(">H", h[6:8])[0] | ((tipo & 0x0F) << 16)   # bits altos no nibble baixo do tipo
                if (tipo & 0xF0) != 0x70:
                    raise ErroJogo("Bloco inválido no CAS (o cache do FMT está desatualizado? Abra o jogo no FMT para atualizar)")
                if (tipo >> 8) == 0:
                    csz = dsz
                dados = f.read(csz)
                lidos += 8 + csz
                out += dados[:dsz] if (tipo >> 8) == 0 else self.oodle.descomprimir(dados, dsz)
        return bytes(out)

    def _chunk(self, cid):
        ids = self.indice["chunk_ids"]
        n = len(ids) // 16
        lo, hi = 0, n
        while lo < hi:
            m = (lo + hi) // 2
            v = ids[m * 16:m * 16 + 16]
            if v < cid:
                lo = m + 1
            else:
                hi = m
        if lo < n and ids[lo * 16:lo * 16 + 16] == cid:
            return struct.unpack_from("<IHHBq", self.indice["chunk_regs"], lo * 17)
        return None

    def lista(self, prefixo=""):
        self.pronto()
        if self._lista is None:
            self._lista = sorted((v[0], str(uuid.UUID(bytes_le=v[1])) if v[1] else "") for v in self.indice["texturas"].values())
        if not prefixo:
            return self._lista
        pre = prefixo.lower()
        return [t for t in self._lista if t[0].lower().startswith(pre)]

    def entrada(self, asset):
        self.pronto()
        k = asset.lower().replace("\\", "/")
        e = self.indice["texturas"].get(k)
        if e is None and not k.startswith("content/"):
            k = "content/" + k
            e = self.indice["texturas"].get(k)
        if e is None:
            raise ErroJogo(f"Textura não encontrada no jogo: {asset}")
        return k, e

    def guids(self, asset):
        """(nome no jogo, GUID da instância, GUID da partição) — o par que a referência no MVDB precisa."""
        k, (nome, pguid, loc, csz, osz) = self.entrada(asset)
        ebx = self.ler(loc, total=osz)
        if ebx[:4] != b"RIFF":
            raise ErroJogo("EBX inválido (cache do FMT desatualizado?)")
        i = ebx.find(b"EBXD")
        dados = (i + 8 + 15) & ~15
        inst = uuid.UUID(bytes_le=ebx[dados:dados + 16])
        j = ebx.find(b"EFIX")
        if j < 0 and not pguid:
            raise ErroJogo("EBX sem GUID de partição")
        part = uuid.UUID(bytes_le=ebx[j + 8:j + 24]) if j > 0 else uuid.UUID(bytes_le=pguid)
        return nome, str(inst), str(part)

    def cabecalho(self, asset):
        k, _ = self.entrada(asset)
        loc, csz, osz = self.indice["res"][k]
        h = self.ler(loc, total=osz)
        fmt = struct.unpack_from("<I", h, 0x0C)[0]
        w, hh, prof, fatias = struct.unpack_from("<HHHH", h, 0x16)
        mips, primeiro = h[0x1E], h[0x1F]
        cid = h[0x28:0x38]
        tam = list(struct.unpack_from("<15I", h, 0x38))
        tipo = struct.unpack_from("<I", h, 0x08)[0]
        return {"formato": fmt, "largura": w, "altura": hh, "fatias": fatias, "mips": mips, "primeiro": primeiro,
                "chunk": cid, "tamanhos": tam[:max(1, mips)], "tipo": tipo}

    def png(self, asset, max_lado=1024):
        """PNG da textura (mip mais próximo de max_lado), com cache em disco."""
        k, _ = self.entrada(asset)
        chave = hashlib.sha1(f"{k}|{max_lado}|{self.indice['assinatura']}".encode()).hexdigest()[:20]
        pasta = os.path.join(CACHE_DIR, "texturas")
        destino = os.path.join(pasta, chave + ".png")
        if os.path.isfile(destino):
            with open(destino, "rb") as f:
                return f.read()
        c = self.cabecalho(asset)
        if c["formato"] not in FORMATOS:
            raise ErroJogo(f"Formato de textura não suportado ({c['formato']})")
        dxgi, bpb, bc, srgb = FORMATOS[c["formato"]]
        tam = c["tamanhos"]
        mips = len(tam)
        alvo = 0
        while alvo + 1 < mips and max(c["largura"] >> alvo, c["altura"] >> alvo) > max_lado:
            alvo += 1
        dados, inicio = self._pixels(c, ate=sum(tam[:alvo]))
        # primeiro mip completo disponível
        k0, acum = None, 0
        for kk in range(mips):
            if acum >= inicio:
                k0 = kk
                break
            acum += tam[kk]
        if k0 is None:
            raise ErroJogo("Não consegui localizar os mips no chunk")
        m = k0
        while m + 1 < mips and max(c["largura"] >> m, c["altura"] >> m) > max_lado:
            m += 1
        ini = sum(tam[:m]) - inicio
        w, h = max(1, c["largura"] >> m), max(1, c["altura"] >> m)
        fatia = tam[m] // max(1, c["fatias"])
        bruto = dados[ini:ini + fatia]
        if len(bruto) < fatia:
            raise ErroJogo("Dados de pixels incompletos")
        if not os.path.isfile(TEXCONV):
            raise ErroJogo("texconv.exe não encontrado em editor/ferramentas")
        with self.lock:
            trava = self._travas.setdefault(chave, threading.Lock())
        with trava:
            if os.path.isfile(destino):
                with open(destino, "rb") as f:
                    return f.read()
            tmp = os.path.join(pasta, "tmp_" + chave)
            os.makedirs(tmp, exist_ok=True)
            dds = os.path.join(tmp, chave + ".dds")
            with open(dds, "wb") as f:
                f.write(_dds(w, h, dxgi, bruto))
            args = [TEXCONV, "-nologo", "-y", "-ft", "png", "-o", tmp]
            if c["formato"] == 63:
                args += ["-f", "R8G8B8A8_UNORM", "-reconstructz"]
            elif c["formato"] in (62, 6):
                args += ["-f", "R8G8B8A8_UNORM"]
            else:
                args += ["-f", "R8G8B8A8_UNORM_SRGB" if srgb else "R8G8B8A8_UNORM"]
            r = subprocess.run(args + [dds], capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            gerado = os.path.join(tmp, chave + ".png")
            if r.returncode != 0 or not os.path.isfile(gerado):
                raise ErroJogo("texconv falhou: " + (r.stdout + r.stderr)[-200:])
            os.replace(gerado, destino)
            for arq in os.listdir(tmp):
                try:
                    os.remove(os.path.join(tmp, arq))
                except OSError:
                    pass
            try:
                os.rmdir(tmp)
            except OSError:
                pass
        with open(destino, "rb") as f:
            return f.read()

    def _pixels(self, c, ate=0):
        """(dados, deslocamento lógico do início) do chunk de pixels.

        O índice aponta para o trecho final do chunk (os mips menores, que o jogo carrega primeiro). Os mips
        maiores costumam estar nos blocos imediatamente anteriores do mesmo CAS: encadeia para trás enquanto
        houver um bloco válido que termina exatamente onde o seguinte começa (confirmado pela descompressão),
        até cobrir o deslocamento lógico 'ate' (início do mip pedido)."""
        reg = self._chunk(c["chunk"])
        if reg is None:
            raise ErroJogo("Chunk de pixels não encontrado no índice")
        off, ic, cas, patch, csz = reg
        cauda = self.ler((off, ic, cas, patch), comprimido=csz)
        total = sum(c["tamanhos"])
        inicio = total - len(cauda)
        if inicio <= ate:
            return cauda, max(0, inicio)
        caminho = self._caminho_cas(self.indice["pacotes"][ic], cas, patch)
        partes, fim = [], off
        with open(caminho, "rb") as f:
            while inicio > ate and len(partes) < 64:
                bloco = self._bloco_anterior(f, fim)
                if bloco is None or len(bloco[1]) > inicio:
                    break
                partes.insert(0, bloco[1])
                inicio -= len(bloco[1])
                fim = bloco[0]
        return b"".join(partes) + cauda, inicio

    def _bloco_anterior(self, f, fim):
        """Bloco que termina exatamente em 'fim'. Tenta primeiro tamanhos comprimidos de 16 bits (janela de 64 KB)
        e só depois os de 20 bits (janela de 1 MB)."""
        for janela in (0x10010, 0x100010):
            ini = max(0, fim - janela)
            f.seek(ini)
            buf = f.read(fim - ini)
            n = len(buf)
            for m in reversed(list(_RX_TIPO.finditer(buf, 5, n - 2))):
                x = m.start() - 5
                csz = (buf[x + 6] << 8) | buf[x + 7] | ((buf[x + 5] & 0x0F) << 16)
                if x + 8 + csz != n:
                    continue
                dsz = (buf[x + 1] << 16) | (buf[x + 2] << 8) | buf[x + 3]
                codigo = buf[x + 4]
                if not 0 < dsz <= 0x100000:
                    continue
                try:
                    if codigo == 0:
                        if csz != dsz:
                            continue
                        return ini + x, bytes(buf[x + 8:x + 8 + dsz])
                    return ini + x, self.oodle.descomprimir(bytes(buf[x + 8:]), dsz)
                except ErroJogo:
                    continue
            if ini == 0:
                break
        return None

    def detalhes(self, asset):
        c = self.cabecalho(asset)
        return {"largura": c["largura"], "altura": c["altura"], "mips": c["mips"],
                "formato": NOMES_FORMATO.get(c["formato"], str(c["formato"]))}


def _dds(w, h, dxgi, dados):
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000
    cab = struct.pack("<4sIIIIIII44xII4sIIIIIIIIII", b"DDS ", 124, flags, h, w, len(dados), 0, 1,
                      32, 0x4, b"DX10", 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0)
    return cab + struct.pack("<IIIII", dxgi, 3, 0, 1, 0) + dados


_JOGO = None


def pasta_valida(pasta):
    return bool(pasta) and os.path.isfile(os.path.join(pasta, "oo2core_9_win64.dll")) and         os.path.isfile(os.path.join(pasta, "Data", "layout.toc"))


def obter(prefs):
    """Instância única configurada pelas preferências (ou detectada). Só a pasta do jogo é obrigatória: o índice
    do FMT é um plano B."""
    global _JOGO
    pasta = prefs.get("jogo_pasta") or detectar_pasta_jogo()
    cache = prefs.get("jogo_cache") or detectar_cache_fmt()
    if cache and not os.path.isfile(cache):
        cache = None
    if not pasta_valida(pasta):
        return None, {"pasta": pasta, "cache": cache}
    if _JOGO is None or _JOGO.pasta != pasta or _JOGO.cache_fmt != cache:
        _JOGO = Jogo(pasta, cache)
    return _JOGO, None
