"""Leitura direta do catálogo do FC 26 instalado (sem o FMT).

Formato (o mesmo que o FMT/FET leem):
  Data/layout.toc           cabeçalho 0x00D1CE01 + assinatura (556 bytes) e um DbObject com os superbundles e os
                            "installChunks" (catálogos = pastas Data/Win32/superbundlelayout/<nome>/cas_XX.cas)
  Data/Win32/<sb>.toc       mesmo cabeçalho; depois um bloco big-endian com as tabelas de bundles e de chunks.
                            Patch/Win32/<sb>.toc, quando existe, substitui o de Data.
  bundle (dentro do .toc)   lista de locais (catálogo, cas, patch, offset, tamanho): o 1º é o manifesto do bundle
                            no CAS (sem compressão), os demais são os assets na ordem ebx, res, chunks do manifesto
  manifesto (no CAS)        u32 BE tamanho, u32 BE 0xD68E799D, contagens (LE), sha1s, entradas e tabela de nomes
"""
import os
import struct

INICIO = 556
MAGIA_MANIFESTO = 0xD68E799D


class ErroToc(Exception):
    pass


# ------------------------------------------------------------------ DbObject (formato binário do Frostbite)

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
    """(nome, valor, próxima posição) ou (None, None, p) no fim de uma lista/objeto."""
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
    raise ErroToc(f"Tipo de DbObject desconhecido: {tipo}")


def ler_db(caminho):
    with open(caminho, "rb") as f:
        b = f.read()
    p = INICIO if struct.unpack_from(">I", b, 0)[0] in (0x00D1CE00, 0x00D1CE01) else 0
    return _db(b, p)[1]


# ------------------------------------------------------------------ layout

class Layout:
    """Superbundles e catálogos (pastas de CAS) de Data e Patch."""

    def __init__(self, pasta_jogo):
        self.pasta = pasta_jogo
        self.superbundles = []
        self.catalogos = []            # nomes das pastas, na ordem do layout
        self.por_persistente = {}      # PersistentIndex -> índice em self.catalogos
        vistos = set()
        for raiz in ("Data", "Patch"):
            arq = os.path.join(pasta_jogo, raiz, "layout.toc")
            if not os.path.isfile(arq):
                continue
            db = ler_db(arq)
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
            raise ErroToc("layout.toc não encontrado ou vazio")

    def caminho_cas(self, catalogo, cas, patch):
        return os.path.join(self.pasta, "Patch" if patch else "Data", "Win32",
                            self.catalogos[catalogo].replace("/", os.sep), "cas_%02d.cas" % cas)

    def tocs(self, superbundle):
        """O .toc de Patch traz só os bundles que mudaram: lê-se o de Patch primeiro e depois o de Data
        (o primeiro local encontrado para cada asset vale)."""
        rel = superbundle.replace("/", os.sep) + ".toc"
        return [c for c in (os.path.join(self.pasta, r, rel) for r in ("Patch", "Data")) if os.path.isfile(c)]


# ------------------------------------------------------------------ .toc de um superbundle

def ler_toc(caminho, layout):
    """{'bundles': [[(cat, cas, patch, off, tam), ...], ...], 'chunks': [(guid16, (cat, cas, patch, off, tam))]}"""
    with open(caminho, "rb") as f:
        b = f.read()
    if len(b) <= INICIO + 48:
        return {"bundles": [], "chunks": []}
    m = struct.unpack_from(">12i", b, INICIO)
    ref_off, bun_off, n_bun, flag_off, guid_off, n_chk, chk_off, _u1, nome_off, data_off, _u9, flags = m
    pp = layout.por_persistente

    def local(p):
        patch, cat, cas = struct.unpack_from(">HiH", b, p)
        return (pp.get(cat, -1), cas, bool(patch)), p + 8

    # chunks do próprio superbundle
    chunks = []
    if n_chk:
        pos_guid = INICIO + guid_off
        ids = {}
        for j in range(n_chk):
            g = bytes(b[pos_guid + 20 * j:pos_guid + 20 * j + 16])[::-1]   # GUID gravado ao contrário
            idx = struct.unpack_from(">I", b, pos_guid + 20 * j + 16)[0] & 0xFFFFFF
            ids[idx] = g
        p = INICIO + chk_off
        for _ in range(n_chk):
            chave = (p - INICIO - data_off) // 4
            (cat, cas, patch), p = local(p)
            off, tam = struct.unpack_from(">II", b, p)
            p += 8
            g = ids.get(chave)
            if g is not None and cat >= 0:
                chunks.append((g, (cat, cas, patch, off, tam)))
    # bundles
    bundles = []
    p = INICIO + bun_off
    tabela = [struct.unpack_from(">iiq", b, p + 16 * i) for i in range(n_bun)]
    for _nome, _tam, off in tabela:
        q = INICIO + off
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


# ------------------------------------------------------------------ manifesto do bundle (no CAS)

def ler_manifesto(f, offset):
    """(ebx [(nome, tam_original)], res [(nome, tam_original, tipo)], chunks [(guid16, off_logico, tam_logico)])"""
    f.seek(offset)
    cab = f.read(36)
    if len(cab) < 36:
        return None
    tam, magia = struct.unpack_from(">II", cab, 0)
    if magia != MAGIA_MANIFESTO:
        return None
    total, n_ebx, n_res, n_chk, str_off, meta_off, _meta_tam = struct.unpack_from("<7I", cab, 8)
    if n_ebx + n_res + n_chk != total:
        return None
    corpo = cab + f.read(max(0, tam + 4 - 36))
    p = 36 + 20 * total
    base_nomes = str_off + 4

    def nome(o):
        q = base_nomes + o
        return corpo[q:corpo.index(b"\0", q)].decode("utf-8", "replace")
    ebx = []
    for _ in range(n_ebx):
        o, t = struct.unpack_from("<II", corpo, p)
        p += 8
        ebx.append((nome(o), t))
    res_n = []
    for _ in range(n_res):
        o, t = struct.unpack_from("<II", corpo, p)
        p += 8
        res_n.append((nome(o), t))
    tipos = struct.unpack_from("<%dI" % n_res, corpo, p) if n_res else ()
    p += 4 * n_res + 16 * n_res + 8 * n_res
    res = [(n, t, tp) for (n, t), tp in zip(res_n, tipos)]
    chunks = []
    for _ in range(n_chk):
        g = bytes(corpo[p:p + 16])
        lo, ls = struct.unpack_from("<II", corpo, p + 16)
        p += 24
        chunks.append((g, lo, ls))
    return ebx, res, chunks


# ------------------------------------------------------------------ índice do editor

RES_TEXTURA = 0x6BDE20BA


def construir_indice(pasta_jogo, progresso=None, versao=0):
    """Índice no mesmo formato do construído a partir do cache do FMT (ver jogo.construir_indice)."""
    def prog(f, msg):
        if progresso:
            progresso(f, msg)
    lay = Layout(pasta_jogo)
    prog(0.02, "Lendo o catálogo do jogo")
    ebx, res, chunks = {}, {}, {}
    por_cas = {}                      # caminho do CAS -> [(offset do manifesto, locais dos assets)]
    tocs = [(sb, c) for sb in lay.superbundles for c in lay.tocs(sb)]
    for i, (sb, caminho) in enumerate(tocs):
        try:
            d = ler_toc(caminho, lay)
        except (OSError, struct.error, ValueError):
            continue
        for g, (cat, cas, patch, off, tam) in d["chunks"]:
            chunks.setdefault(g, (off, cat, cas, int(patch), tam))
        for locais in d["bundles"]:
            cat, cas, patch, off, tam = locais[0]
            if cat < 0 or cas == 0:
                continue
            por_cas.setdefault(lay.caminho_cas(cat, cas, patch), []).append((off, locais[1:]))
        prog(0.02 + 0.18 * (i + 1) / len(tocs), "Lendo o catálogo do jogo")
    n = sum(len(v) for v in por_cas.values())
    feitos = 0
    for caminho, lista in por_cas.items():
        try:
            f = open(caminho, "rb")
        except OSError:
            feitos += len(lista)
            continue
        with f:
            for off, locais in sorted(lista, key=lambda x: x[0]):
                feitos += 1
                try:
                    m = ler_manifesto(f, off)
                except (struct.error, ValueError):
                    m = None
                if not m:
                    continue
                le, lr, lc = m
                if len(le) + len(lr) + len(lc) != len(locais):
                    continue
                k = 0
                for nome, osz in le:
                    cat, cas, patch, o, t = locais[k]
                    k += 1
                    if cat >= 0:
                        ebx.setdefault(nome.lower(), (nome, (o, cat, cas, int(patch)), t, osz))
                for nome, osz, tipo in lr:
                    cat, cas, patch, o, t = locais[k]
                    k += 1
                    if tipo == RES_TEXTURA and cat >= 0:
                        res.setdefault(nome.lower(), ((o, cat, cas, int(patch)), t, osz))
                for g, _lo, _ls in lc:
                    cat, cas, patch, o, t = locais[k]
                    k += 1
                    if cat >= 0:
                        chunks.setdefault(g, (o, cat, cas, int(patch), t))
                if feitos % 2000 == 0:
                    prog(0.2 + 0.75 * feitos / max(1, n), "Lendo os bundles do jogo")
    texturas = {}
    for k, (loc, t, osz) in res.items():
        e = ebx.get(k)
        if e:
            texturas[k] = (e[0], None, e[1], e[2], e[3])
    ordem = sorted(chunks)
    prog(1.0, "Pronto")
    pacotes = {i: (c[len("superbundlelayout/"):] if c.lower().startswith("superbundlelayout/") else c)
               for i, c in enumerate(lay.catalogos)}
    return {"versao": versao, "texturas": texturas, "res": {k: res[k] for k in texturas},
            "chunk_ids": b"".join(ordem), "chunk_regs": b"".join(struct.pack("<IHHBq", *chunks[g]) for g in ordem),
            "pacotes": pacotes, "fonte": "jogo"}
