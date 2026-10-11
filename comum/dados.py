"""BRFP Super Tool — banco de dados e idioma do jogo, compartilhados por todas as ferramentas (biblioteca padrão).

O usuário importa uma vez (página "Dados do jogo" do Super Tool):
  - banco: fifa_ng_db.db + fifa_ng_db-meta.xml, ou uma pasta de tabelas .txt exportadas (RDBM/DB Master/FET);
  - idioma: LanguageStrings1/2.txt exportados pelo FET, ou o .db de idioma quando não é criptografado.
O registro fica em dados/fontes.json; cada ferramenta lê com banco_atual() / idioma_atual(), que recarregam sozinhos
quando a importação muda. As tabelas são decodificadas só quando pedidas, com cache em dados/cache.

Formato t3db (little-endian), herdado de _scripts_conversao/t3db.py do BRFP 27:
  cabeçalho 'DB\\0\\x08', 0, tamanho, 0, n_tabelas, crc, n x (shortname[4], offset), crc
  tabela: 36 bytes (flags, recsize, bits, tam_strings, n_reg, n_validos, ..., n_campos, ..., crc),
          n_campos x 16 bytes (tipo, bit_offset, shortname, bits), registros, bloco de strings (Huffman), crc
  tipos: 0 string embutida, 3 inteiro (valor - rangelow), 4 real (float32), 13 string comprimida (Huffman)
"""
import hashlib
import json
import os
import pickle
import re
import struct
import threading
import time
import unicodedata

COMUM = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(COMUM)
DADOS = os.environ.get("BRFP_DADOS") or os.path.join(SUPERTOOL, "dados")
FONTES = os.path.join(DADOS, "fontes.json")
CACHE = os.path.join(DADOS, "cache")
LOCK = threading.RLock()


class ErroDados(Exception):
    pass


# ------------------------------------------------------------------ meta (esquema)
def ler_meta(caminho):
    """{nome_tabela: {"short", "campos": {nome: {short, tipo, bits, low, high, chave}}}} na ordem do meta."""
    with open(caminho, encoding="utf-8-sig", errors="replace") as f:
        txt = f.read()
    m = re.search(r'<database name="([^"]*)"', txt)
    out = {"_banco": m.group(1) if m else ""}
    for tm in re.finditer(r'<table name="([^"]+)" shortname="([^"]+)"[^>]*>(.*?)</table>', txt, re.S):
        nome, sn, corpo = tm.groups()
        campos = {}
        for fm in re.finditer(r"<field ([^>]*)/>", corpo):
            a = dict(re.findall(r'(\w+)="([^"]*)"', fm.group(1)))
            try:
                campos[a["name"]] = {"short": a["shortname"], "tipo": a.get("type", ""), "bits": int(a.get("depth", 0)),
                                     "low": int(a.get("rangelow", 0)), "high": int(a.get("rangehigh", 0)),
                                     "chave": a.get("key") == "True"}
            except (KeyError, ValueError):
                continue
        out[nome] = {"short": sn, "campos": campos}
    return out


def tabelas_meta(meta):
    return {k: v for k, v in meta.items() if not k.startswith("_")}


# ------------------------------------------------------------------ leitura t3db
def _arvore(buf, ini, tam):
    return [((buf[ini + 4 * i], buf[ini + 4 * i + 1]), (buf[ini + 4 * i + 2], buf[ini + 4 * i + 3])) for i in range(tam // 4)]


def _huffman(buf, pos, n, nos):
    out = bytearray()
    bit = pos * 8
    no = 0
    while len(out) < n:
        b = (buf[bit >> 3] >> (7 - (bit & 7))) & 1
        bit += 1
        e = nos[no][b]
        if e[0] == 0:
            out.append(e[1])
            no = 0
        else:
            no = e[0]
    return bytes(out)


class CampoT3:
    __slots__ = ("tipo", "bitoff", "sn", "bits", "nome", "low", "high", "chave", "mtipo")

    def __init__(self, tipo, bitoff, sn, bits, m):
        self.tipo, self.bitoff, self.sn, self.bits = tipo, bitoff, sn, bits
        self.nome = m.get("nome", sn)
        self.low, self.high = m.get("low", 0), m.get("high", 0)
        self.chave = m.get("chave", False)
        self.mtipo = m.get("tipo", "")


class Tabela:
    """Tabela decodificada: campos (nomes) e linhas (listas de texto, como nas tabelas exportadas)."""

    def __init__(self, nome, campos, linhas, info=None):
        self.nome, self.campos, self.linhas = nome, list(campos), linhas
        self.info = info or {}          # nome do campo -> {tipo, bits, low, high, chave}
        self._idx = {c: i for i, c in enumerate(self.campos)}

    def col(self, c):
        return self._idx.get(c)

    def dicts(self):
        return [dict(zip(self.campos, l)) for l in self.linhas]

    def indice(self, campo):
        i = self._idx[campo]
        return {l[i]: l for l in self.linhas}

    def valores(self, campo):
        i = self._idx.get(campo)
        return [] if i is None else [l[i] for l in self.linhas]


class FonteDB:
    tipo = "db"

    def __init__(self, caminho, meta_caminho):
        self.caminho, self.meta_caminho = caminho, meta_caminho
        self.meta = ler_meta(meta_caminho)
        with open(caminho, "rb") as f:
            self.d = f.read()
        if self.d[:4] != b"DB\x00\x08":
            raise ErroDados("O arquivo não é um banco t3db (fifa_ng_db.db). Bancos criptografados precisam ser exportados pelo FET/RDBM.")
        d = self.d
        nt = struct.unpack_from("<I", d, 0x10)[0]
        self.entradas = [struct.unpack_from("<4sI", d, 0x18 + 8 * i) for i in range(nt)]
        self.base = 0x18 + 8 * nt + 4
        por_short = {v["short"]: k for k, v in tabelas_meta(self.meta).items()}
        self.tabs = {}
        ordem = sorted(range(nt), key=lambda i: self.entradas[i][1])
        for k, i in enumerate(ordem):
            snb, off = self.entradas[i]
            sn = snb.decode("latin-1")
            nome = por_short.get(sn, sn)
            T = self.base + off
            hdr = list(struct.unpack_from("<IIIIHHHHIII", d, T))
            fim = self.base + self.entradas[ordem[k + 1]][1] if k + 1 < nt else len(d)
            self.tabs[nome] = {"sn": sn, "T": T, "hdr": hdr, "fim": fim, "i": i}

    def nomes(self):
        return sorted((n, t["hdr"][5], t["hdr"][8]) for n, t in self.tabs.items())

    def campos_t3(self, nome):
        t = self.tabs[nome]
        mc = self.meta.get(nome, {}).get("campos", {})
        por_sn = {v["short"]: dict(v, nome=k) for k, v in mc.items()}
        out = []
        for k in range(t["hdr"][8]):
            ft, bo, fsn, dep = struct.unpack_from("<II4sI", self.d, t["T"] + 36 + 16 * k)
            fsn = fsn.decode("latin-1")
            out.append(CampoT3(ft, bo, fsn, dep, por_sn.get(fsn, {})))
        return out

    def tabela(self, nome):
        if nome not in self.tabs:
            raise ErroDados(f"A tabela {nome} não existe neste banco.")
        t = self.tabs[nome]
        d = self.d
        flags, recsize, _, strlen, nrec, nval = t["hdr"][:6]
        campos = self.campos_t3(nome)
        R = t["T"] + 36 + 16 * len(campos)
        sbloco = R + recsize * nrec
        nos = None
        if strlen and flags & 0x40:
            offs = [struct.unpack_from("<I", d, R + recsize * r + f.bitoff // 8)[0] for r in range(nval) for f in campos if f.tipo == 13]
            offs = [o for o in offs if o != 0xFFFFFFFF]
            nos = _arvore(d, sbloco, min(offs)) if offs else None
        ints = [(j, f.bitoff, (1 << f.bits) - 1, f.low) for j, f in enumerate(campos) if f.tipo == 3]
        outros = [(j, f) for j, f in enumerate(campos) if f.tipo != 3]
        linhas = []
        n_campos = len(campos)
        fb = int.from_bytes
        for r in range(nval):
            p = R + recsize * r
            rec = d[p:p + recsize]
            v = fb(rec, "little")
            linha = [""] * n_campos
            for j, bo, mask, low in ints:
                linha[j] = str(((v >> bo) & mask) + low)
            for j, f in outros:
                if f.tipo == 4:
                    linha[j] = "%.9g" % struct.unpack_from("<f", rec, f.bitoff // 8)[0]
                elif f.tipo == 0:
                    raw = rec[f.bitoff // 8:f.bitoff // 8 + f.bits // 8]
                    linha[j] = raw.split(b"\0")[0].decode("utf-8", errors="replace")
                elif f.tipo in (13, 14):
                    o = struct.unpack_from("<I", rec, f.bitoff // 8)[0]
                    if o != 0xFFFFFFFF:
                        q = sbloco + o
                        if f.tipo == 13:
                            n, q = d[q], q + 1
                        else:
                            n, q = (d[q] << 8) | d[q + 1], q + 2
                        raw = _huffman(d, q, n, nos) if nos is not None else d[q:q + n]
                        linha[j] = raw.decode("utf-8", errors="replace")
            linhas.append(linha)
        info = {f.nome: {"tipo": f.mtipo or {0: "string", 3: "int", 4: "real", 13: "string"}.get(f.tipo, str(f.tipo)),
                         "bits": f.bits, "low": f.low, "high": f.high, "chave": f.chave, "t3": f.tipo} for f in campos}
        return Tabela(nome, [f.nome for f in campos], linhas, info)


def ler_txt(caminho):
    """Tabela exportada (.txt, tabulada): UTF-16 (RDBM/DB Master) ou UTF-8. Devolve (campos, linhas, codificação)."""
    with open(caminho, "rb") as f:
        b = f.read()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        txt, cod = b.decode("utf-16"), "utf-16"
    elif b[:3] == b"\xef\xbb\xbf":
        txt, cod = b[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    elif b[:200].count(b"\0") > 20:
        txt, cod = b.decode("utf-16-le", errors="replace"), "utf-16-le"
    else:
        try:
            txt, cod = b.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            txt, cod = b.decode("cp1252", errors="replace"), "cp1252"
    linhas = txt.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while linhas and not linhas[-1].strip():
        linhas.pop()
    if not linhas:
        return [], [], cod
    campos = linhas[0].split("\t")
    n = len(campos)
    out = []
    for l in linhas[1:]:
        p = l.split("\t")
        if len(p) < n:
            p += [""] * (n - len(p))
        out.append(p[:n])
    return campos, out, cod


class FontePasta:
    tipo = "pasta"

    def __init__(self, pasta, meta_caminho=None):
        self.caminho = pasta
        self.meta_caminho = meta_caminho
        self.meta = ler_meta(meta_caminho) if meta_caminho else {}
        self.arqs = {}
        for n in os.listdir(pasta):
            if n.lower().endswith(".txt"):
                self.arqs[n[:-4]] = os.path.join(pasta, n)
        if not self.arqs:
            raise ErroDados("A pasta não tem tabelas .txt exportadas.")
        self._n = {}

    def nomes(self):
        out = []
        for n, p in sorted(self.arqs.items()):
            if n not in self._n:
                try:
                    with open(p, "rb") as f:
                        b = f.read()
                    u16 = b[:2] in (b"\xff\xfe", b"\xfe\xff") or b[:200].count(b"\0") > 20
                    nl = b.count(b"\n\0" if u16 else b"\n")
                    cab = ler_txt(p)[0] if len(b) < 4096 else None
                    self._n[n] = (max(0, nl - 1), len(cab) if cab is not None else 0)
                except OSError:
                    self._n[n] = (0, 0)
            out.append((n, self._n[n][0], self._n[n][1]))
        return out

    def tabela(self, nome):
        if nome not in self.arqs:
            raise ErroDados(f"A tabela {nome} não está na pasta.")
        campos, linhas, _ = ler_txt(self.arqs[nome])
        mc = self.meta.get(nome, {}).get("campos", {})
        info = {c: {"tipo": mc[c]["tipo"], "bits": mc[c]["bits"], "low": mc[c]["low"], "high": mc[c]["high"],
                    "chave": mc[c]["chave"]} for c in campos if c in mc}
        return Tabela(nome, campos, linhas, info)


def achar_meta(perto):
    """fifa_ng_db-meta.xml (ou *-meta.xml de banco principal) na pasta do .db ou na pasta acima."""
    pastas = [perto if os.path.isdir(perto) else os.path.dirname(perto)]
    pastas.append(os.path.dirname(pastas[0]))
    for p in pastas:
        cand = os.path.join(p, "fifa_ng_db-meta.xml")
        if os.path.isfile(cand):
            return cand
    for p in pastas:
        try:
            for n in sorted(os.listdir(p)):
                if n.lower().endswith("-meta.xml") and "db" in n.lower() and not n.lower().startswith(("por_", "eng_", "spa_")):
                    return os.path.join(p, n)
        except OSError:
            pass
    return None


# ------------------------------------------------------------------ idioma
def _hash_idioma(chave):
    """hashid do LanguageStrings: CRC32 (init 0, sem xor final) dos bytes UTF-8 & 0xDF, gravado como valor - 2^31."""
    c = 0
    for b in chave.encode("utf-8"):
        c = _CRC_TAB[(c ^ (b & 0xDF)) & 0xFF] ^ (c >> 8)
    return (c & 0xFFFFFFFF) - 2 ** 31


_CRC_TAB = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_TAB.append(_c)


class Idioma:
    def __init__(self, textos, origem, arquivos):
        self.textos = textos          # chave -> texto
        self.origem, self.arquivos = origem, arquivos

    def texto(self, chave, padrao=None):
        if not chave:
            return padrao
        return self.textos.get(chave, padrao)

    def time(self, teamid):
        return self.texto(f"TeamName_{teamid}") or self.texto(f"TeamName_Abbr15_{teamid}")

    def competicao(self, assetid):
        return self.texto(f"TrophyName_{assetid}") or self.texto(f"TrophyName_Abbr15_{assetid}")

    def liga(self, leagueid):
        return self.texto(f"LeagueName_{leagueid}") or self.texto(f"LeagueName_Abbr15_{leagueid}")


def ler_idioma(caminhos):
    textos = {}
    arquivos = []
    for c in caminhos:
        if os.path.isdir(c):
            sub = sorted(os.path.join(c, n) for n in os.listdir(c) if re.match(r"(?i)languagestrings.*\.txt$", n))
            if not sub:
                raise ErroDados(f"Nenhum LanguageStrings*.txt em {c}")
            caminhos_arq = sub
        else:
            caminhos_arq = [c]
        for p in caminhos_arq:
            with open(p, "rb") as f:
                ini = f.read(8)
            if p.lower().endswith(".db"):
                if ini[:4] != b"DB\x00\x08":
                    raise ErroDados(f"{os.path.basename(p)} está criptografado (o FC 27 é assim). Exporte LanguageStrings1.txt e "
                                    "LanguageStrings2.txt pelo FET e importe os .txt.")
                meta = achar_meta_idioma(p)
                fonte = FonteDB(p, meta) if meta else None
                if fonte is None:
                    raise ErroDados(f"Não achei o meta (*-meta.xml) do idioma ao lado de {os.path.basename(p)}.")
                for nome, _, _ in fonte.nomes():
                    t = fonte.tabela(nome)
                    ci, cs = t.col("stringid"), t.col("sourcetext")
                    if ci is None or cs is None:
                        continue
                    for l in t.linhas:
                        textos[l[ci]] = l[cs]
            else:
                campos, linhas, _ = ler_txt(p)
                if "stringid" not in campos or "sourcetext" not in campos:
                    raise ErroDados(f"{os.path.basename(p)} não parece um LanguageStrings (faltam as colunas stringid/sourcetext).")
                ci, cs = campos.index("stringid"), campos.index("sourcetext")
                for l in linhas:
                    textos[l[ci]] = l[cs]
            arquivos.append(p)
    if not textos:
        raise ErroDados("Nenhum texto encontrado.")
    return textos, arquivos


def achar_meta_idioma(db):
    p = os.path.dirname(db)
    base = os.path.splitext(os.path.basename(db))[0]
    for n in [base + "-meta.xml"] + sorted(os.listdir(p)):
        if n.lower().endswith("-meta.xml") and (n.lower().startswith(base.lower()[:3]) or n == base + "-meta.xml"):
            if os.path.isfile(os.path.join(p, n)):
                return os.path.join(p, n)
    return None


# ------------------------------------------------------------------ registro (dados/fontes.json)
def _ler_fontes():
    try:
        with open(FONTES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _gravar_fontes(d):
    os.makedirs(DADOS, exist_ok=True)
    tmp = FONTES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FONTES)


def _assinatura(caminhos):
    h = hashlib.sha1()
    for c in caminhos:
        try:
            st = os.stat(c)
            h.update(f"{os.path.abspath(c)}|{st.st_size}|{int(st.st_mtime)}".encode())
        except OSError:
            h.update(c.encode())
    return h.hexdigest()[:14]


# ------------------------------------------------------------------ versões do jogo (esquemas guardados)
# comum/esquemas: o meta de cada versão (FIFA 16 … FC 27, tirado dos bancos do usuário) e um índice com a assinatura
# delas (tabelas e campos pelos nomes curtos do t3db e pelos nomes do meta). Serve para reconhecer a versão de um banco,
# abrir um fifa_ng_db.db sem o meta ao lado e converter tabelas para qualquer versão.
ESQUEMAS = os.path.join(COMUM, "esquemas")
_ESQ = {"indice": None}


def esquemas():
    """[{id, nome, ordem, meta, tabelas, players, curtos, campos_curtos}] das versões guardadas (da mais antiga)."""
    if _ESQ["indice"] is None:
        import gzip
        try:
            with gzip.open(os.path.join(ESQUEMAS, "indice.json.gz"), "rt", encoding="utf-8") as f:
                _ESQ["indice"] = sorted(json.load(f)["versoes"], key=lambda v: v["ordem"])
        except (OSError, ValueError, KeyError):
            _ESQ["indice"] = []
    return _ESQ["indice"]


def nome_jogo(jid):
    if jid and jid.endswith("~"):                          # versão desconhecida, parecida com uma guardada
        return f"parecido com o {nome_jogo(jid[:-1])}"
    return next((v["nome"] for v in esquemas() if v["id"] == jid), None) or {"?": "jogo não identificado"}.get(jid, jid or "?")


class _NomesJogo(dict):
    def get(self, k, padrao=None):
        return nome_jogo(k)

    def __getitem__(self, k):
        return nome_jogo(k)


NOME_JOGO = _NomesJogo()


def meta_guardado(jid):
    """Caminho de uma cópia do meta guardado da versão (descompactado em dados/cache)."""
    import gzip
    v = next((x for x in esquemas() if x["id"] == jid), None)
    if not v:
        raise ErroDados(f"Não tenho o esquema guardado de {jid}.")
    destino = os.path.join(CACHE, f"esquema_{jid}-meta.xml")
    if not os.path.isfile(destino):
        os.makedirs(CACHE, exist_ok=True)
        with gzip.open(os.path.join(ESQUEMAS, v["meta"]), "rb") as f:
            xml = f.read()
        with open(destino + ".tmp", "wb") as f:
            f.write(xml)
        os.replace(destino + ".tmp", destino)
    return destino


def assinatura_t3db(caminho):
    """(tabelas curtas, "tabela.campo" curtos) de um fifa_ng_db.db, sem precisar do meta."""
    with open(caminho, "rb") as f:
        d = f.read()
    if d[:4] != b"DB\x00\x08":
        raise ErroDados("O arquivo não é um banco t3db (fifa_ng_db.db).")
    nt = struct.unpack_from("<I", d, 0x10)[0]
    ent = [struct.unpack_from("<4sI", d, 0x18 + 8 * i) for i in range(nt)]
    base = 0x18 + 8 * nt + 4
    tabs, pares = set(), set()
    for snb, off in ent:
        sn = snb.decode("latin-1")
        tabs.add(sn)
        T = base + off
        nc = struct.unpack_from("<IIIIHHHHIII", d, T)[8]
        for k in range(nc):
            fsn = struct.unpack_from("<II4sI", d, T + 36 + 16 * k)[2].decode("latin-1")
            pares.add(f"{sn}.{fsn}")
    return tabs, pares


def _jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def detectar_versao_db(caminho):
    """(id da versão, semelhança 0..1) pelo esquema do próprio .db (nomes curtos das tabelas e dos campos).
    Semelhança abaixo de 0,97: versão que não está guardada (o id vem com "~": parecida com)."""
    tabs, pares = assinatura_t3db(caminho)
    melhor, nota = None, -1.0
    for v in esquemas():
        n = 0.3 * _jaccard(tabs, set(v["curtos"])) + 0.7 * _jaccard(pares, set(v["campos_curtos"]))
        if n > nota:
            melhor, nota = v["id"], n
    if melhor is None:
        return "?", 0.0
    return (melhor if nota >= 0.97 else melhor + "~"), round(nota, 3)


def detectar_jogo(tabelas, campos_players):
    """Versão pelos nomes das tabelas e dos campos de players (pasta de tabelas .txt ou banco com meta)."""
    tabelas, campos = set(tabelas), set(campos_players or [])
    melhor, nota = None, -1.0
    for v in esquemas():
        n = 0.4 * _jaccard(tabelas, set(v["tabelas"])) + 0.6 * _jaccard(campos, set(v["players"]))
        if n > nota:
            melhor, nota = v["id"], n
    if melhor is not None and nota >= 0.5:
        return melhor if nota >= 0.95 else melhor + "~"
    # sem esquemas: o critério antigo
    if {"vipplayers", "multiclubownership"} & tabelas or {"growthprofile", "role6", "releaseclause"} & campos:
        return "fc27"
    if "players" in tabelas and campos:
        return "fc26"
    return "?"


class Banco:
    def __init__(self, reg):
        self.reg = reg
        if reg["tipo"] == "db":
            self.fonte = FonteDB(reg["caminho"], reg["meta"])
        else:
            self.fonte = FontePasta(reg["caminho"], reg.get("meta"))
        self.sig = reg.get("sig") or _assinatura([reg["caminho"]])
        self._mem = {}
        self.lock = threading.RLock()
        self._nomes = None
        self.jogo = reg.get("jogo") or "?"

    # ---- tabelas
    def nomes(self):
        return self.fonte.nomes()

    def tem(self, nome):
        return nome in (self.fonte.tabs if self.fonte.tipo == "db" else self.fonte.arqs)

    def tabela(self, nome):
        with self.lock:
            if nome in self._mem:
                return self._mem[nome]
            pasta = os.path.join(CACHE, "banco_" + self.sig)
            arq = os.path.join(pasta, re.sub(r"[^\w.-]", "_", nome) + ".pkl")
            t = None
            if self.fonte.tipo == "db" and os.path.isfile(arq):
                try:
                    with open(arq, "rb") as f:
                        campos, linhas, info = pickle.load(f)
                    t = Tabela(nome, campos, linhas, info)
                except Exception:  # noqa: BLE001 — cache velho/corrompido: decodifica de novo
                    t = None
            if t is None:
                t = self.fonte.tabela(nome)
                if self.fonte.tipo == "db" and len(t.linhas) > 2000:
                    try:
                        os.makedirs(pasta, exist_ok=True)
                        with open(arq + ".tmp", "wb") as f:
                            pickle.dump((t.campos, t.linhas, t.info), f, protocol=4)
                        os.replace(arq + ".tmp", arq)
                    except OSError:
                        pass
            self._mem[nome] = t
            return t

    def tabela_ou_none(self, nome):
        return self.tabela(nome) if self.tem(nome) else None

    # ---- nomes de jogadores e times
    def _tab_nomes(self):
        if self._nomes is None:
            nomes = {}
            for tn in ("playernames", "dcplayernames"):
                t = self.tabela_ou_none(tn)
                if t and t.col("nameid") is not None and t.col("name") is not None:
                    i, j = t.col("nameid"), t.col("name")
                    for l in t.linhas:
                        nomes[l[i]] = l[j]
            edit = {}
            t = self.tabela_ou_none("editedplayernames")
            if t and t.col("playerid") is not None:
                for d in t.dicts():
                    edit[d["playerid"]] = d
            self._nomes = (nomes, edit)
        return self._nomes

    def jogador(self, linha_players):
        """dict do jogador (linha de players) -> {playerid, primeiro, sobrenome, comum, camisa, nome}"""
        nomes, edit = self._tab_nomes()
        p = linha_players
        pid = p.get("playerid", "")
        e = edit.get(pid)
        if e:
            prim, sob, com, cam = e.get("firstname", ""), e.get("surname", ""), e.get("commonname", ""), e.get("playerjerseyname", "")
        else:
            prim = nomes.get(p.get("firstnameid", ""), "")
            sob = nomes.get(p.get("lastnameid", ""), "")
            com = nomes.get(p.get("commonnameid", ""), "")
            cam = nomes.get(p.get("playerjerseynameid", ""), "")
        nome = com or " ".join(x for x in (prim, sob) if x).strip() or cam or f"Jogador {pid}"
        return {"playerid": pid, "primeiro": prim, "sobrenome": sob, "comum": com, "camisa": cam, "nome": nome,
                "overall": p.get("overallrating", ""), "nascimento": p.get("birthdate", ""), "nacionalidade": p.get("nationality", "")}

    def times(self, idioma=None):
        t = self.tabela_ou_none("teams")
        if not t:
            return []
        it, iname = t.col("teamid"), t.col("teamname")
        ligas = {}
        lt = self.tabela_ou_none("leagueteamlinks")
        lg = self.tabela_ou_none("leagues")
        nome_liga = {}
        if lg is not None and lg.col("leagueid") is not None:
            for d in lg.dicts():
                nome_liga[d["leagueid"]] = (idioma.liga(d["leagueid"]) if idioma else None) or d.get("leaguename", "")
        if lt is not None:
            for d in lt.dicts():
                ligas.setdefault(d["teamid"], d["leagueid"])
        out = []
        for l in t.linhas:
            tid = l[it]
            nome = (idioma.time(tid) if idioma else None) or (l[iname] if iname is not None else "") or f"Time {tid}"
            lid = ligas.get(tid)
            out.append({"teamid": tid, "nome": nome, "leagueid": lid, "liga": nome_liga.get(lid, "") if lid else ""})
        out.sort(key=lambda x: _normal(x["nome"]))
        return out

    def jogadores_do_time(self, teamid):
        tl = self.tabela("teamplayerlinks")
        pl = self.tabela("players")
        ip = pl.col("playerid")
        por_id = {l[ip]: l for l in pl.linhas}
        out = []
        for d in tl.dicts():
            if d.get("teamid") != str(teamid):
                continue
            l = por_id.get(d["playerid"])
            if l is None:
                continue
            j = self.jogador(dict(zip(pl.campos, l)))
            j.update(camisa_num=d.get("jerseynumber", ""), posicao=d.get("position", ""))
            out.append(j)
        out.sort(key=lambda j: (int(j["camisa_num"]) if str(j["camisa_num"]).isdigit() else 999, j["nome"]))
        return out

    def resumo(self):
        n = {}
        for nome in ("players", "teams", "leagues", "teamplayerlinks"):
            for (tn, regs, _) in self.nomes():
                if tn == nome:
                    n[nome] = regs
        return {"tipo": self.fonte.tipo, "caminho": self.reg["caminho"], "meta": self.reg.get("meta"), "jogo": self.jogo,
                "nome_jogo": NOME_JOGO.get(self.jogo, self.jogo), "tabelas": len(self.nomes()), "contagens": n,
                "importado_em": self.reg.get("quando"), "nome": self.reg.get("nome") or os.path.basename(self.reg["caminho"]),
                "meta_guardado": self.reg.get("meta_guardado")}


def _normal(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


normalizar = _normal

# ------------------------------------------------------------------ estado por processo (recarrega se o registro mudar)
_ATUAL = {"mtime": None, "banco": None, "idioma": None, "erro_banco": None, "erro_idioma": None}


def _recarregar():
    try:
        mt = os.path.getmtime(FONTES)
    except OSError:
        mt = 0
    if mt == _ATUAL["mtime"]:
        return
    reg = _ler_fontes()
    _ATUAL.update(mtime=mt, banco=None, idioma=None, erro_banco=None, erro_idioma=None)
    if reg.get("banco"):
        try:
            _ATUAL["banco"] = Banco(reg["banco"])
        except (OSError, ErroDados, ValueError, struct.error) as ex:
            _ATUAL["erro_banco"] = str(ex)
    if reg.get("idioma"):
        try:
            textos, arquivos = _carregar_idioma_cache(reg["idioma"])
            _ATUAL["idioma"] = Idioma(textos, reg["idioma"].get("nome", ""), arquivos)
        except (OSError, ErroDados, ValueError) as ex:
            _ATUAL["erro_idioma"] = str(ex)


def _carregar_idioma_cache(reg):
    sig = reg.get("sig") or _assinatura(reg["caminhos"])
    arq = os.path.join(CACHE, f"idioma_{sig}.pkl")
    if os.path.isfile(arq):
        try:
            with open(arq, "rb") as f:
                return pickle.load(f)
        except Exception:  # noqa: BLE001
            pass
    textos, arquivos = ler_idioma(reg["caminhos"])
    try:
        os.makedirs(CACHE, exist_ok=True)
        with open(arq + ".tmp", "wb") as f:
            pickle.dump((textos, arquivos), f, protocol=4)
        os.replace(arq + ".tmp", arq)
    except OSError:
        pass
    return textos, arquivos


def banco_atual():
    with LOCK:
        _recarregar()
        return _ATUAL["banco"]


def idioma_atual():
    with LOCK:
        _recarregar()
        return _ATUAL["idioma"]


def internationals_atual():
    """O internationals.txt importado (objeto de comum/internationals.py) ou None."""
    import internationals as INT
    reg = _ler_fontes().get("internationals")
    if not reg:
        return None
    try:
        mt = os.path.getmtime(reg["caminho"])
        if _ATUAL.get("int_chave") != (reg["caminho"], mt):
            _ATUAL["internationals"] = INT.Internationals.ler(reg["caminho"])
            _ATUAL["int_chave"] = (reg["caminho"], mt)
            _ATUAL["erro_internationals"] = None
        return _ATUAL["internationals"]
    except (OSError, ValueError) as ex:
        _ATUAL["erro_internationals"] = str(ex)
        return None


def estado():
    """Resumo do que está importado (para o Super Tool e as ferramentas)."""
    with LOCK:
        _recarregar()
        b, i = _ATUAL["banco"], _ATUAL["idioma"]
        reg = _ler_fontes()
        it = internationals_atual()
        return {
            "banco": b.resumo() if b else None, "erro_banco": _ATUAL["erro_banco"],
            "idioma": {"nome": reg.get("idioma", {}).get("nome", ""), "textos": len(i.textos), "arquivos": i.arquivos,
                       "importado_em": reg.get("idioma", {}).get("quando")} if i else None,
            "erro_idioma": _ATUAL["erro_idioma"],
            "internationals": {"caminho": it.caminho, "selecoes": len(it.selecoes()),
                               "masculinas": sum(1 for x in it.selecoes() if not x["genero"]),
                               "femininas": sum(1 for x in it.selecoes() if x["genero"]), "squad": it.squad(),
                               "idade_maxima": it.idade_maxima(),
                               "importado_em": reg.get("internationals", {}).get("quando")} if it else None,
            "erro_internationals": _ATUAL.get("erro_internationals") if reg.get("internationals") else None,
            "jogos": [{"id": v["id"], "nome": v["nome"]} for v in esquemas()],
        }


# ------------------------------------------------------------------ importar / remover (usado pela página do Super Tool)
def importar_banco(caminho, meta=None, jogo=None):
    caminho = os.path.abspath(caminho)
    if os.path.isdir(caminho):
        meta = meta or achar_meta(caminho)
        fonte = FontePasta(caminho, meta)
        reg = {"tipo": "pasta", "caminho": caminho, "meta": meta}
    elif os.path.isfile(caminho):
        meta = meta or achar_meta(caminho)
        versao = None
        if not meta:                                       # sem o meta ao lado: o guardado da versão reconhecida
            versao, nota = detectar_versao_db(caminho)
            if versao.endswith("~") or versao == "?":
                raise ErroDados("Não achei o fifa_ng_db-meta.xml ao lado do banco e a versão dele não é nenhuma das guardadas"
                                f" (a mais parecida: {nome_jogo(versao)}). Coloque o meta na mesma pasta (exporte junto pelo FET).")
            meta = meta_guardado(versao)
        fonte = FonteDB(caminho, meta)
        reg = {"tipo": "db", "caminho": caminho, "meta": meta}
        if versao:
            reg["meta_guardado"] = versao
    else:
        raise ErroDados(f"Não encontrado: {caminho}")
    nomes = [n for n, _, _ in fonte.nomes()]
    campos_pl = []
    if "players" in nomes:
        campos_pl = list(fonte.meta.get("players", {}).get("campos", {})) or fonte.tabela("players").campos
    if not jogo and reg["tipo"] == "db":
        try:
            jogo = detectar_versao_db(caminho)[0]
        except (OSError, ErroDados, struct.error):
            jogo = None
    reg.update(jogo=jogo or detectar_jogo(nomes, campos_pl), sig=_assinatura([caminho]), quando=time.strftime("%d/%m/%Y %H:%M"),
               nome=os.path.basename(os.path.dirname(caminho) if reg["tipo"] == "db" else caminho))
    faltam = [t for t in ("players", "teams", "teamplayerlinks") if t not in nomes]
    with LOCK:
        d = _ler_fontes()
        d["banco"] = reg
        _gravar_fontes(d)
    # já decodifica (e guarda em cache) as tabelas que as ferramentas mais usam
    b = banco_atual()
    for t in ("teams", "players", "playernames", "teamplayerlinks", "leagues", "leagueteamlinks", "editedplayernames"):
        if b and b.tem(t):
            b.tabela(t)
    return {"faltam": faltam, **estado()}


def importar_idioma(caminhos, nome=None):
    caminhos = [os.path.abspath(c) for c in caminhos]
    textos, arquivos = ler_idioma(caminhos)
    sig = _assinatura(arquivos)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, f"idioma_{sig}.pkl"), "wb") as f:
        pickle.dump((textos, arquivos), f, protocol=4)
    with LOCK:
        d = _ler_fontes()
        d["idioma"] = {"caminhos": arquivos, "sig": sig, "quando": time.strftime("%d/%m/%Y %H:%M"),
                       "nome": nome or os.path.basename(os.path.dirname(arquivos[0]))}
        _gravar_fontes(d)
    return estado()


def importar_internationals(caminho):
    """internationals.txt do jogo (seleções do modo carreira): o Criador de Ligas e Times acrescenta as seleções novas."""
    import internationals as INT
    caminho = os.path.abspath(caminho)
    if os.path.isdir(caminho):
        achados = [os.path.join(caminho, n) for n in os.listdir(caminho) if n.lower() == "internationals.txt"]
        if not achados:
            raise ErroDados(f"Não há internationals.txt em {caminho}.")
        caminho = achados[0]
    try:
        INT.Internationals.ler(caminho)
    except (OSError, ValueError) as ex:
        raise ErroDados(str(ex))
    with LOCK:
        d = _ler_fontes()
        d["internationals"] = {"caminho": caminho, "quando": time.strftime("%d/%m/%Y %H:%M"),
                               "nome": os.path.basename(os.path.dirname(caminho))}
        _gravar_fontes(d)
        _ATUAL.pop("int_chave", None)
    return estado()


def definir_jogo(jogo):
    with LOCK:
        d = _ler_fontes()
        if not d.get("banco"):
            raise ErroDados("Nenhum banco importado.")
        d["banco"]["jogo"] = jogo
        _gravar_fontes(d)
    return estado()


def remover(qual):
    with LOCK:
        d = _ler_fontes()
        d.pop(qual, None)
        _gravar_fontes(d)
    return estado()


# ------------------------------------------------------------------ escrita t3db (tabelas sem strings comprimidas)
_TM = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _TM.append(_c)


def crc32_t3db(b, init=0xFFFFFFFF):
    c = init
    for x in b:
        c = ((c << 8) & 0xFFFFFFFF) ^ _TM[((c >> 24) ^ x) & 0xFF]
    return c


def _huffman_montar(textos):
    """Árvore de Huffman no formato do t3db (4 bytes por nó: (filho0, filho1), cada filho (0, byte) = folha ou
    (índice do nó, 0)) e o código de cada byte (bits do mais alto para o mais baixo, como o leitor _huffman)."""
    import heapq
    freq = {}
    for t in textos:
        for x in t:
            freq[x] = freq.get(x, 0) + 1
    if not freq:
        return b"", {}
    heap = [(n, i, ("f", x)) for i, (x, n) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    if len(heap) == 1:                                     # um símbolo só: os dois filhos são a mesma folha
        x = heap[0][2][1]
        return bytes((0, x, 0, x)), {x: "0"}
    k = len(heap)
    while len(heap) > 1:
        n1, _, a1 = heapq.heappop(heap)
        n2, _, a2 = heapq.heappop(heap)
        heapq.heappush(heap, (n1 + n2, k, ("n", a1, a2)))
        k += 1
    raiz = heap[0][2]
    ordem, idx = [raiz], {id(raiz): 0}
    i = 0
    while i < len(ordem):                                  # nós internos em largura: a raiz é o 0
        no = ordem[i]
        for filho in no[1:]:
            if filho[0] == "n":
                idx[id(filho)] = len(ordem)
                ordem.append(filho)
        i += 1
    if len(ordem) > 255:
        raise ErroDados("Textos com símbolos demais para a árvore do t3db.")
    arv = bytearray()
    for no in ordem:
        for filho in no[1:]:
            arv += bytes((0, filho[1])) if filho[0] == "f" else bytes((idx[id(filho)], 0))
    codigos = {}

    def andar(no, pre):
        if no[0] == "f":
            codigos[no[1]] = pre or "0"
            return
        andar(no[1], pre + "0")
        andar(no[2], pre + "1")
    andar(raiz, "")
    return bytes(arv), codigos


def _huffman_codificar(t, codigos):
    bits = "".join(codigos[x] for x in t)
    bits += "0" * ((-len(bits)) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big") if bits else b""


def montar_tabela(fonte, nome, linhas, avisos):
    """Bytes de uma tabela do FonteDB 'fonte' com as linhas novas (listas na ordem dos campos do arquivo).
    Textos (campos 13/14) vão num bloco depois dos registros: comprimidos com uma árvore de Huffman nova quando a
    tabela original é comprimida (flag 0x40), senão crus; cada texto é o tamanho (1 byte; 2 no tipo 14) + os bytes."""
    t = fonte.tabs[nome]
    campos = fonte.campos_t3(nome)
    flags, recsize, nbits = t["hdr"][0], t["hdr"][1], t["hdr"][2]
    if len(linhas) > 0xFFFF:
        raise ErroDados(f"{nome}: {len(linhas)} registros (o máximo é 65535).")
    textos = [(j, f) for j, f in enumerate(campos) if f.tipo in (13, 14)]
    huff = bool(flags & 0x40)
    codigos = {}
    arvore = b""
    if textos:
        def bruto(v, f):
            b = str(v or "").encode("utf-8")
            lim = 255 if f.tipo == 13 else 0xFFFF
            if len(b) > lim:
                avisos.append(f"{nome}.{f.nome}: texto com mais de {lim} bytes foi cortado")
                b = b[:lim].decode("utf-8", errors="ignore").encode("utf-8")
            return b
        todos = [[bruto(l[j] if j < len(l) else "", f) for j, f in textos] for l in linhas]
        if huff:
            arvore, codigos = _huffman_montar([x for r in todos for x in r if x])
    bloco = bytearray(arvore)
    regs = []
    for n_l, linha in enumerate(linhas):
        acc = 0
        buf = bytearray(recsize)
        for f, v in zip(campos, linha):
            if f.tipo == 3:
                try:
                    raw = int(float(v or 0)) - f.low
                except ValueError:
                    raw = 0
                if raw < 0 or raw >= (1 << f.bits):
                    avisos.append(f"{nome}.{f.nome} = {v} fora do que cabe em {f.bits} bits a partir de {f.low}")
                    raw = max(0, min(raw, (1 << f.bits) - 1))
                acc |= raw << f.bitoff
            elif f.tipo == 4:
                struct.pack_into("<f", buf, f.bitoff // 8, float(v or 0))
            elif f.tipo == 0:
                n = f.bits // 8
                b = str(v).encode("utf-8")[:n]
                buf[f.bitoff // 8:f.bitoff // 8 + len(b)] = b
        for k, (j, f) in enumerate(textos):
            b = todos[n_l][k]
            if not b:
                struct.pack_into("<I", buf, f.bitoff // 8, 0xFFFFFFFF)
                continue
            struct.pack_into("<I", buf, f.bitoff // 8, len(bloco))
            bloco += bytes((len(b),)) if f.tipo == 13 else struct.pack(">H", len(b))
            bloco += _huffman_codificar(b, codigos) if huff else b
        ib = acc.to_bytes(recsize, "little")
        regs.append(bytes(x | y for x, y in zip(ib, buf)))
    n = len(regs)
    hdr = struct.pack("<IIIIHHHHII", flags, recsize, nbits, len(bloco), n, n, t["hdr"][6], t["hdr"][7], len(campos), t["hdr"][9])
    hdr += struct.pack("<I", crc32_t3db(hdr))
    corpo = b"".join(struct.pack("<II4sI", f.tipo, f.bitoff, f.sn.encode("latin-1"), f.bits) for f in campos) + b"".join(regs)
    corpo += bytes(bloco)
    corpo += b"\0" * ((-len(corpo)) % 4)
    if bloco:                                              # como o jogo grava: 4 bytes zerados depois dos textos
        corpo += b"\0" * 4
    return hdr + corpo + struct.pack("<I", crc32_t3db(corpo))


def gravar_banco(fonte, novas, destino):
    """Regrava o .db de 'fonte' trocando as tabelas em 'novas' (nome -> bytes)."""
    d = fonte.d
    ent = fonte.entradas
    nt = len(ent)
    base = fonte.base
    ordem = sorted(range(nt), key=lambda i: ent[i][1])
    blobs = {}
    for k, i in enumerate(ordem):
        ini = base + ent[i][1]
        fim = base + ent[ordem[k + 1]][1] if k + 1 < nt else len(d)
        blobs[i] = d[ini:fim]
    por_i = {t["i"]: n for n, t in fonte.tabs.items()}
    for i in range(nt):
        if por_i.get(i) in novas:
            blobs[i] = novas[por_i[i]]
    off, pos = {}, 0
    for i in ordem:
        off[i] = pos
        pos += len(blobs[i])
    tabela_ent = b"".join(struct.pack("<4sI", ent[i][0], off[i]) for i in range(nt))
    total = base + pos
    cab = struct.pack("<4sIIII", d[:4], 0, total, 0, nt)
    cab += struct.pack("<I", crc32_t3db(cab))
    out = bytearray(cab + tabela_ent + struct.pack("<I", crc32_t3db(tabela_ent)))
    for i in ordem:
        out += blobs[i]
    with open(destino, "wb") as f:
        f.write(out)
    return len(out)


def escrever_txt(caminho, campos, linhas, codificacao="utf-16"):
    """Tabela .txt tabulada com CRLF: utf-16 (com BOM, como o RDBM/DB Master exportam) ou utf-8."""
    txt = "\r\n".join(["\t".join(campos)] + ["\t".join(str(v) for v in l) for l in linhas]) + "\r\n"
    with open(caminho, "wb") as f:
        if codificacao == "utf-16":
            f.write(b"\xff\xfe" + txt.encode("utf-16-le"))
        else:
            f.write(txt.encode("utf-8"))
