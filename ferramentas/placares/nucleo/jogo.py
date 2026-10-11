"""Leitura direta dos arquivos "legacy" do FC 26 instalado (placares, fontes, temas), sem FMT nem FET.

Como o jogo guarda os arquivos legacy (data/ui/...):
- Quatro EBX "ChunkFileCollector" (core/chunkfiles/...) apontam cada um para um chunk-manifesto.
- O manifesto lista os arquivos: hash FNV-1 64 do caminho em minúsculas, faixa comprimida, posição dentro do
  chunk descomprimido, tamanho e o índice do chunk de dados; no fim vêm os GUIDs desses chunks.
- Os chunks estão nas tabelas dos .toc (superbundle win32/globals) e os dados nos CAS, em blocos do Frostbite
  comprimidos com Oodle (oo2core_9_win64.dll, na pasta do jogo).
- Os nomes não estão no jogo: vêm da lista do Live Editor (legacy_filename_hash_list.csv), de padrões
  conhecidos (overlays, componentes) e dos nomes citados dentro dos próprios arquivos (fontes do FIFA.xml).
"""
import collections
import ctypes
import glob
import json
import os
import pickle
import re
import struct
import threading
import time

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(AQUI, "cache")
VERSAO_INDICE = 2
INICIO_TOC = 556
MAGIA_MANIFESTO = 0xD68E799D
# GUIDs dos manifestos na versão atual do jogo: só um plano B se os coletores não forem achados pelo nome
COLETORES_CONHECIDOS = ["51b127f0-5100-3fef-70ee-e9e3b99a127f", "a4277a62-d166-808d-fb77-7f9c0edbdf91"]
PASTAS_OVERLAY = ["Bundesliga", "Champions", "Conmebol", "EPL", "Europa", "FUT", "Generic", "LaLiga", "SSF", "SuperCup",
                  "o05Penta", "o13Ligue1", "o14SerieA", "o17APL", "o18WSL", "o20WUCL", "o21NWSL", "o22fbundensliga",
                  "o23LigaF", "o24EFL", "FACup", "MLS", "WorldCup"]


class ErroJogo(Exception):
    pass


def fnv64(texto):
    h = 14695981039346656037
    for c in texto.lower().encode("latin-1", "replace"):
        h = ((h * 1099511628211) & 0xFFFFFFFFFFFFFFFF) ^ c
    return h


# ------------------------------------------------------------------ detecção da pasta do jogo e do Live Editor

def detectar_pasta_jogo():
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
        if pasta_valida(c):
            return os.path.abspath(c)
    return None


def pasta_valida(pasta):
    return bool(pasta) and os.path.isfile(os.path.join(pasta, "oo2core_9_win64.dll")) and \
        os.path.isfile(os.path.join(pasta, "Data", "layout.toc"))


def detectar_live_editor():
    """(pasta de dados do Live Editor — onde fica mods/legacy —, pasta do programa com a lista de nomes)."""
    dados = None
    for u in "CDEFGH":
        c = u + r":\FC 26 Live Editor"
        if os.path.isdir(c):
            dados = c
            break
    programa = None
    casa = os.path.expanduser("~")
    for base in (os.path.join(casa, "Desktop"), os.path.join(casa, "Downloads"), os.path.join(casa, "Documents"), "C:\\"):
        for c in sorted(glob.glob(os.path.join(base, "FC 26 LE*")) + glob.glob(os.path.join(base, "FC 26 Live Editor*")), reverse=True):
            if os.path.isfile(os.path.join(c, "legacy_filename_hash_list.csv")):
                programa = c
                break
        if programa:
            break
    return dados, programa


# ------------------------------------------------------------------ Oodle

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
        src = ctypes.create_string_buffer(bytes(dados), len(dados))
        dst = ctypes.create_string_buffer(tamanho)
        r = self.f(src, len(dados), dst, tamanho, 1, 0, 0, None, 0, None, None, None, 0, 3)
        if r != tamanho:
            raise ErroJogo(f"Oodle não descomprimiu ({r} de {tamanho} bytes)")
        return dst.raw


def blocos(dados, oodle):
    """Descomprime uma sequência de blocos do Frostbite (cabeçalho de 8 bytes cada)."""
    out = bytearray()
    p = 0
    n = len(dados)
    while p + 8 <= n:
        dsz = struct.unpack_from(">I", dados, p)[0] & 0xFFFFFF
        tipo = struct.unpack_from(">H", dados, p + 4)[0]
        csz = struct.unpack_from(">H", dados, p + 6)[0] | ((tipo & 0x0F) << 16)
        if (tipo & 0xF0) != 0x70:
            raise ErroJogo("Bloco comprimido inválido")
        if (tipo >> 8) == 0:
            csz = dsz
        corpo = dados[p + 8:p + 8 + csz]
        out += corpo[:dsz] if (tipo >> 8) == 0 else oodle.descomprimir(corpo, dsz)
        p += 8 + csz
    return bytes(out)


# ------------------------------------------------------------------ catálogo (.toc) — o mínimo para achar chunks

def _v7(b, p):
    r = s = 0
    while True:
        c = b[p]
        p += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, p


def _db(b, p):
    t = b[p]
    p += 1
    tipo = t & 0x1F
    if tipo == 0:
        return None, None, p
    nome = ""
    if not t & 0x80:
        f = b.index(b"\0", p)
        nome = b[p:f].decode("utf-8", "replace")
        p = f + 1
    if tipo in (1, 2):
        tam, p = _v7(b, p)
        fim = p + tam
        itens = [] if tipo == 1 else {}
        while p < fim:
            n, v, p = _db(b, p)
            if n is None:
                break
            if tipo == 1:
                itens.append(v)
            else:
                itens[n.lower()] = v
        return nome, itens, fim
    if tipo == 6:
        return nome, b[p] == 1, p + 1
    if tipo == 7:
        n, p = _v7(b, p)
        return nome, b[p:p + n].rstrip(b"\0").decode("utf-8", "replace"), p + n
    if tipo == 8:
        return nome, struct.unpack_from("<i", b, p)[0], p + 4
    if tipo in (9, 10):
        return nome, struct.unpack_from("<q", b, p)[0], p + 8
    if tipo == 11:
        return nome, struct.unpack_from("<f", b, p)[0], p + 4
    if tipo == 12:
        return nome, struct.unpack_from("<d", b, p)[0], p + 8
    if tipo == 15:
        return nome, bytes(b[p:p + 16]), p + 16
    if tipo == 16:
        return nome, bytes(b[p:p + 20]), p + 20
    if tipo == 19:
        n, p = _v7(b, p)
        return nome, bytes(b[p:p + n]), p + n
    raise ErroJogo(f"Tipo de DbObject desconhecido: {tipo}")


class Layout:
    def __init__(self, pasta_jogo):
        self.pasta = pasta_jogo
        self.superbundles = []
        self.catalogos = []
        self.por_persistente = {}
        vistos = set()
        for raiz in ("Data", "Patch"):
            arq = os.path.join(pasta_jogo, raiz, "layout.toc")
            if not os.path.isfile(arq):
                continue
            with open(arq, "rb") as f:
                b = f.read()
            p = INICIO_TOC if struct.unpack_from(">I", b, 0)[0] in (0x00D1CE00, 0x00D1CE01) else 0
            db = _db(b, p)[1]
            for sb in db.get("superbundles", []):
                nome = sb.get("name", "").lower()
                if nome and nome not in vistos:
                    vistos.add(nome)
                    self.superbundles.append(nome)
            for ic in (db.get("installmanifest") or {}).get("installchunks", []):
                if ic.get("testdlc"):
                    continue
                nome = ic.get("installbundle") or ("win32/" + ic.get("name", ""))
                pasta = nome.split("/", 1)[1] if nome.lower().startswith("win32/") else nome
                if pasta in self.catalogos:
                    continue
                self.catalogos.append(pasta)
                if "persistentindex" in ic:
                    self.por_persistente.setdefault(ic["persistentindex"], len(self.catalogos) - 1)
        if not self.superbundles:
            raise ErroJogo("layout.toc não encontrado ou vazio")

    def caminho_cas(self, catalogo, cas, patch):
        return os.path.join(self.pasta, "Patch" if patch else "Data", "Win32",
                            self.catalogos[catalogo].replace("/", os.sep), "cas_%02d.cas" % cas)

    def tocs(self, superbundle):
        rel = superbundle.replace("/", os.sep) + ".toc"
        return [c for c in (os.path.join(self.pasta, r, rel) for r in ("Patch", "Data")) if os.path.isfile(c)]


def ler_toc(caminho, layout, com_bundles=True):
    with open(caminho, "rb") as f:
        b = f.read()
    if len(b) <= INICIO_TOC + 48:
        return {"bundles": [], "chunks": []}
    m = struct.unpack_from(">12i", b, INICIO_TOC)
    _ref, bun_off, n_bun, _fl, guid_off, n_chk, chk_off, _u1, _nome, data_off, _u9, _flags = m
    pp = layout.por_persistente

    def local(p):
        patch, cat, cas = struct.unpack_from(">HiH", b, p)
        return (pp.get(cat, -1), cas, bool(patch)), p + 8

    chunks = []
    if n_chk:
        pos_guid = INICIO_TOC + guid_off
        ids = {}
        for j in range(n_chk):
            g = bytes(b[pos_guid + 20 * j:pos_guid + 20 * j + 16])[::-1]
            idx = struct.unpack_from(">I", b, pos_guid + 20 * j + 16)[0] & 0xFFFFFF
            ids[idx] = g
        p = INICIO_TOC + chk_off
        for _ in range(n_chk):
            chave = (p - INICIO_TOC - data_off) // 4
            (cat, cas, patch), p = local(p)
            off, tam = struct.unpack_from(">II", b, p)
            p += 8
            g = ids.get(chave)
            if g is not None and cat >= 0:
                chunks.append((g, (cat, cas, patch, off, tam)))
    bundles = []
    if com_bundles:
        p = INICIO_TOC + bun_off
        tabela = [struct.unpack_from(">iiq", b, p + 16 * i) for i in range(n_bun)]
        for _n, _t, off in tabela:
            q = INICIO_TOC + off
            if q + 36 > len(b):
                continue
            _a, _b2, f_off, n_ent, e_off, _hs, _c, _d, _e = struct.unpack_from(">9i", b, q)
            flags_b = b[q + f_off:q + f_off + n_ent]
            r = q + e_off
            atual = (-1, 0, False)
            locais = []
            for j in range(n_ent):
                if flags_b[j] == 0x80:
                    atual, r = local(r)
                off_e, tam_e = struct.unpack_from(">II", b, r)
                r += 8
                locais.append((atual[0], atual[1], atual[2], off_e, tam_e))
            bundles.append(locais)
    return {"bundles": bundles, "chunks": chunks}


def ler_nomes_ebx(f, offset):
    """Nomes e tamanhos dos EBX de um manifesto de bundle (no CAS)."""
    f.seek(offset)
    cab = f.read(36)
    if len(cab) < 36:
        return None
    tam, magia = struct.unpack_from(">II", cab, 0)
    if magia != MAGIA_MANIFESTO:
        return None
    total, n_ebx, n_res, n_chk, str_off, _m, _mt = struct.unpack_from("<7I", cab, 8)
    if n_ebx + n_res + n_chk != total:
        return None
    corpo = cab + f.read(max(0, tam + 4 - 36))
    p = 36 + 20 * total
    base = str_off + 4
    out = []
    for _ in range(n_ebx):
        o, t = struct.unpack_from("<II", corpo, p)
        p += 8
        q = base + o
        out.append(corpo[q:corpo.index(b"\0", q)].decode("utf-8", "replace"))
    return out


# ------------------------------------------------------------------ nomes dos arquivos legacy

def numero_conjunto(pasta):
    """Número do conjunto de placares de uma pasta de overlays (Generic = 9, o14SerieA = 14...)."""
    m = re.match(r"o(\d+)", pasta)
    if m:
        return int(m.group(1))
    return CONJUNTOS_VANILLA.get(pasta)


CONJUNTOS_VANILLA = {"LaLiga": 4, "FACup": 5, "EPL": 6, "Bundesliga": 7, "FUT": 8, "Generic": 9, "Champions": 10,
                     "Europa": 11, "SuperCup": 12, "SSF": 15, "Conmebol": 16, "MLS": 19, "WorldCup": 90}
# os números dos overlays usados pelo jogo: 001–199, 3xx (controles), 5xx, 9xx
FAIXA_OVERLAYS = list(range(0, 200)) + list(range(300, 400)) + list(range(500, 600)) + list(range(900, 1000))


def nomes_padrao():
    """Caminhos prováveis de overlays e componentes (o jogo só guarda o hash)."""
    out = []
    for n in range(1, 100):
        for k in FAIXA_OVERLAYS:
            out.append(f"data/ui/game/overlays/overlay_{n}{k:03d}.big")
    for pasta in PASTAS_OVERLAY:
        n = numero_conjunto(pasta)
        if n:
            for k in FAIXA_OVERLAYS:
                out.append(f"data/ui/game/overlays/{pasta}/overlay_{n}{k:03d}.big")
    ids = [str(i) for i in range(1, 100)] + ["EA", "WC", "GO"]
    for n in ids:
        for m in ids:
            out.append(f"data/ui/game/globalComponents/overlayComponents_{n}/overlayComponents_{m}.big")
    return out


class Nomes:
    def __init__(self):
        self.mapa = {}

    def adicionar(self, nome):
        self.mapa.setdefault(fnv64(nome), nome)

    def carregar_csv(self, caminho):
        try:
            with open(caminho, encoding="utf-8", errors="replace") as f:
                for linha in f:
                    a, _, b = linha.rstrip("\r\n").partition(";")
                    if a.isdigit() and b:
                        self.mapa.setdefault(int(a), b)
        except OSError:
            pass


# ------------------------------------------------------------------ o jogo

class Jogo:
    """Índice dos arquivos legacy do FC 26 + leitura. Carrega em segundo plano (iniciar())."""

    def __init__(self, pasta):
        self.pasta = pasta
        self.estado = "parado"
        self.mensagem = ""
        self.erro = None
        self.oodle = None
        self.layout = None
        self.arquivos = {}     # nome em minúsculas -> (nome, guid16 do chunk, offset, tamanho)
        self.sem_nome = 0
        self.lock = threading.Lock()
        self._cache_chunks = collections.OrderedDict()
        self._chunks = {}

    # ---------------------------------------------------------- carga
    def assinatura(self):
        partes = [self.pasta.lower(), str(VERSAO_INDICE)]
        for raiz in ("Data", "Patch"):
            for rel in ("layout.toc", os.path.join("Win32", "globals.toc")):
                c = os.path.join(self.pasta, raiz, rel)
                if os.path.isfile(c):
                    st = os.stat(c)
                    partes.append(f"{rel}:{st.st_size}:{int(st.st_mtime)}")
        _, prog = detectar_live_editor()
        csv = os.path.join(prog, "legacy_filename_hash_list.csv") if prog else ""
        if csv and os.path.isfile(csv):
            partes.append(f"csv:{os.path.getsize(csv)}")
        return "|".join(partes)

    def iniciar(self):
        with self.lock:
            if self.estado in ("carregando", "pronto"):
                return
            self.estado = "carregando"
        threading.Thread(target=self._carregar, daemon=True).start()

    def esperar(self, limite=120):
        t = time.time()
        while self.estado == "carregando" and time.time() - t < limite:
            time.sleep(0.05)
        if self.estado != "pronto":
            raise ErroJogo(self.erro or "O índice do jogo não ficou pronto")

    def _carregar(self):
        try:
            self.oodle = Oodle(self.pasta)
            self.layout = Layout(self.pasta)
            arq = os.path.join(CACHE_DIR, "legacy_fc26.pkl")
            ass = self.assinatura()
            salvo = None
            if os.path.isfile(arq):
                try:
                    with open(arq, "rb") as f:
                        salvo = pickle.load(f)
                    if salvo.get("assinatura") != ass:
                        salvo = None
                except (OSError, pickle.PickleError, EOFError, AttributeError):
                    salvo = None
            if salvo is None:
                self.mensagem = "Lendo o catálogo do jogo"
                salvo = self._construir()
                salvo["assinatura"] = ass
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(arq + ".tmp", "wb") as f:
                    pickle.dump(salvo, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(arq + ".tmp", arq)
            self.arquivos = salvo["arquivos"]
            self._chunks = salvo["chunks"]
            self.sem_nome = salvo["sem_nome"]
            self.estado = "pronto"
            self.mensagem = f"{len(self.arquivos)} arquivos"
        except Exception as ex:   # o editor continua funcionando com mods e pastas
            self.estado = "erro"
            self.erro = f"{type(ex).__name__}: {ex}"

    def _construir(self):
        lay = self.layout
        chunks = {}
        coletores = {}
        for toc in lay.tocs("win32/globals"):
            d = ler_toc(toc, lay)
            for g, loc in d["chunks"]:
                chunks.setdefault(g, loc)
            for locais in d["bundles"]:
                cat, cas, patch, off, _t = locais[0]
                if cat < 0:
                    continue
                try:
                    with open(lay.caminho_cas(cat, cas, patch), "rb") as f:
                        nomes = ler_nomes_ebx(f, off)
                except OSError:
                    continue
                for k, nome in enumerate(nomes or []):
                    if nome.lower().startswith("core/chunkfiles/") and nome.lower() not in coletores:
                        coletores[nome.lower()] = locais[1 + k]
        guids = []
        for nome, (cat, cas, patch, off, tam) in coletores.items():
            with open(lay.caminho_cas(cat, cas, patch), "rb") as f:
                f.seek(off)
                ebx = blocos(f.read(tam), self.oodle)
            achado = None
            for i in range(len(ebx) - 16):
                if ebx[i:i + 16] in chunks:
                    achado = ebx[i:i + 16]
                    break
            if achado is None:   # o manifesto pode estar em outro superbundle
                if not getattr(self, "_todos", False):
                    self._todos = True
                    for sb in lay.superbundles:
                        for toc in lay.tocs(sb):
                            for g, loc in ler_toc(toc, lay, com_bundles=False)["chunks"]:
                                chunks.setdefault(g, loc)
                for i in range(len(ebx) - 16):
                    if ebx[i:i + 16] in chunks:
                        achado = ebx[i:i + 16]
                        break
            if achado is not None:
                guids.append(achado)
        if not guids:
            import uuid
            guids = [uuid.UUID(g).bytes_le for g in COLETORES_CONHECIDOS if uuid.UUID(g).bytes_le in chunks]
        if not guids:
            raise ErroJogo("Não achei os coletores de arquivos legacy no jogo")
        self.mensagem = "Lendo a lista de arquivos legacy"
        entradas = {}
        for g in guids:
            man = self._ler_chunk_loc(chunks[g])
            rootc, rooto, nf, fo, bc, bo, lc, lo, go, so = struct.unpack_from("<IqiqIqIqqq", man, 0)
            regs = [struct.unpack_from("<Qiiiii", man, fo + 28 * i) for i in range(nf)]
            nidx = max((r[5] for r in regs), default=-1) + 1
            gs = [bytes(man[go + 16 * k:go + 16 * k + 16]) for k in range(nidx)]
            for h, _co, _ce, do, sz, ci in regs:
                entradas.setdefault(h, (gs[ci], do, sz))
        usados = {e[0] for e in entradas.values()}
        nomes = Nomes()
        _, prog = detectar_live_editor()
        if prog:
            nomes.carregar_csv(os.path.join(prog, "legacy_filename_hash_list.csv"))
        for n in nomes_padrao():
            nomes.adicionar(n)
        arquivos = {}
        sem = 0
        for h, (g, do, sz) in entradas.items():
            nome = nomes.mapa.get(h)
            if not nome:
                sem += 1
                nome = "desconhecido/%016x" % h
            arquivos[nome.lower()] = (nome, g, do, sz)
        self.arquivos = arquivos
        self._chunks = {g: chunks[g] for g in usados if g in chunks}
        # fontes citadas no tema: data/ui/fontes/<VALOR>.ttf
        extra = []
        try:
            tema = self.ler("data/ui/themes/FIFA.xml").decode("utf-8", "replace")
            for v in set(re.findall(r'VALUE="([^"$@]+)"', tema)):
                for ext in (".ttf", ".otf", ".TTF"):
                    extra.append(f"data/ui/fonts/{v}{ext}")
        except ErroJogo:
            pass
        for n in extra:
            h = fnv64(n)
            if h in entradas:
                chave = "desconhecido/%016x" % h
                if chave in arquivos:
                    del arquivos[chave]
                    sem -= 1
                g, do, sz = entradas[h]
                arquivos[n.lower()] = (n, g, do, sz)
        return {"arquivos": arquivos, "chunks": self._chunks, "sem_nome": sem}

    # ---------------------------------------------------------- leitura
    def _ler_chunk_loc(self, loc):
        cat, cas, patch, off, tam = loc
        with open(self.layout.caminho_cas(cat, cas, patch), "rb") as f:
            f.seek(off)
            return blocos(f.read(tam), self.oodle)

    def _chunk(self, g):
        with self.lock:
            if g in self._cache_chunks:
                self._cache_chunks.move_to_end(g)
                return self._cache_chunks[g]
        loc = self._chunks.get(g)
        if loc is None:
            raise ErroJogo("Chunk de dados não encontrado no catálogo do jogo")
        dados = self._ler_chunk_loc(loc)
        with self.lock:
            self._cache_chunks[g] = dados
            while len(self._cache_chunks) > 12:
                self._cache_chunks.popitem(last=False)
        return dados

    def existe(self, nome):
        return nome.lower().replace("\\", "/") in self.arquivos

    def ler(self, nome):
        e = self.arquivos.get(nome.lower().replace("\\", "/"))
        if e is None:
            raise ErroJogo(f"Arquivo não encontrado no jogo: {nome}")
        _n, g, do, sz = e
        return self._chunk(g)[do:do + sz]

    def lista(self, prefixo=""):
        p = prefixo.lower()
        return sorted(v[0] for k, v in self.arquivos.items() if k.startswith(p))

    def info(self):
        return {"estado": self.estado, "mensagem": self.mensagem, "erro": self.erro, "pasta": self.pasta,
                "arquivos": len(self.arquivos), "sem_nome": self.sem_nome}


_JOGO = None


def obter(pasta=None):
    global _JOGO
    pasta = pasta or detectar_pasta_jogo()
    if not pasta_valida(pasta):
        return None
    if _JOGO is None or _JOGO.pasta != pasta:
        _JOGO = Jogo(pasta)
    return _JOGO
