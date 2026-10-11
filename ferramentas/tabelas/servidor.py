"""Conversor de Tabelas (BRFP Super Tool) — converte tabelas do banco entre jogos (FC 26 <-> FC 27).

    python servidor.py [--porta 8774] [--sem-janela]

Origem: o banco importado no Super Tool (Dados do jogo) ou outro .db/pasta de tabelas. Destino: o banco (ou a pasta de
tabelas, ou só o meta) do jogo para onde as tabelas vão — dá o esquema final, os valores mais comuns e as linhas para
mesclar. Saída: .txt por tabela (UTF-16 como o RDBM/DB Master exportam, ou UTF-8) e, se o destino for um .db, um .db novo.
"""
import argparse
import os
import shutil
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import conversao as C  # noqa: E402
import dados  # noqa: E402

VERSAO = "1.1"
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {
    "destino": None, "origem": None, "saida": "", "formato": "utf-16", "gravar_db": False, "modo": "substituir",
    "sobrescrever": False})
LOCK = threading.RLock()
EST = {"sel": [], "mapa": {}, "rel": None, "rodando": False, "progresso": (0, 0)}
_FONTES = {}


# ------------------------------------------------------------------ origem e destino
class Fonte:
    """Banco aberto (FonteDB ou FontePasta) com jogo e cache de tabelas."""

    def __init__(self, reg):
        self.reg = reg
        t = reg["tipo"]
        if t == "db":
            self.f = dados.FonteDB(reg["caminho"], reg["meta"])
        elif t == "pasta":
            self.f = dados.FontePasta(reg["caminho"], reg.get("meta"))
        else:   # só o meta: esquema sem linhas
            self.f = None
            self.meta = dados.ler_meta(reg["meta"])
        self.cache = {}

    @property
    def tipo(self):
        return self.reg["tipo"]

    def nomes(self):
        if self.f is None:
            return [(n, 0, len(v["campos"])) for n, v in dados.tabelas_meta(self.meta).items()]
        return self.f.nomes()

    def tem(self, nome):
        return any(n == nome for n, _, _ in self.nomes())

    def tabela(self, nome):
        if nome not in self.cache:
            if self.f is None:
                mc = self.meta.get(nome, {}).get("campos", {})
                info = {c: {k: v for k, v in i.items() if k != "short"} for c, i in mc.items()}
                self.cache[nome] = dados.Tabela(nome, list(mc), [], info)
            else:
                self.cache[nome] = self.f.tabela(nome)
        return self.cache[nome]

    def jogo(self):
        if self.reg.get("jogo"):
            return self.reg["jogo"]
        nomes = [n for n, _, _ in self.nomes()]
        campos = []
        if "players" in nomes:
            meta = self.f.meta if self.f is not None else self.meta
            campos = list(meta.get("players", {}).get("campos", {})) or (self.tabela("players").campos if self.f else [])
        return dados.detectar_jogo(nomes, campos)


def reg_origem():
    p = PREFS.ler()
    return p.get("origem")


def fonte_origem():
    reg = reg_origem()
    if not reg:
        b = dados.banco_atual()
        if not b:
            return None
        chave = ("banco", b.sig)
        if chave not in _FONTES:
            _FONTES.clear() if len(_FONTES) > 6 else None
            f = Fonte({"tipo": b.fonte.tipo, "caminho": b.reg["caminho"], "meta": b.reg.get("meta"), "jogo": b.jogo})
            _FONTES[chave] = f
        return _FONTES[chave]
    chave = ("origem", reg["caminho"], reg.get("jogo"))
    if chave not in _FONTES:
        _FONTES[chave] = Fonte(reg)
    return _FONTES[chave]


def fonte_destino():
    reg = PREFS.ler().get("destino")
    if not reg:
        return None
    chave = ("destino", reg["caminho"], reg.get("meta"), reg.get("jogo"))
    if chave not in _FONTES:
        _FONTES[chave] = Fonte(reg)
    return _FONTES[chave]


def resumo(f, reg):
    if f is None:
        return None
    n = dict((nm, r) for nm, r, _ in f.nomes())
    return {"tipo": f.tipo, "caminho": reg.get("caminho") or reg.get("meta"), "meta": reg.get("meta"), "jogo": f.jogo(),
            "nome_jogo": dados.NOME_JOGO.get(f.jogo(), f.jogo()), "tabelas": len(n),
            "players": n.get("players"), "teams": n.get("teams"), "esquema": reg.get("esquema")}


def registrar(caminho, meta=None):
    caminho = os.path.abspath(caminho)
    if caminho.lower().endswith(".xml"):
        return {"tipo": "meta", "caminho": caminho, "meta": caminho}
    if os.path.isdir(caminho):
        return {"tipo": "pasta", "caminho": caminho, "meta": meta or dados.achar_meta(caminho)}
    m = meta or dados.achar_meta(caminho)
    if not m:                                              # sem o meta ao lado: o esquema guardado da versão reconhecida
        try:
            v, _ = dados.detectar_versao_db(caminho)
        except (OSError, dados.ErroDados) as ex:
            raise base.ErroUsuario(str(ex))
        if v.endswith("~") or v == "?":
            raise base.ErroUsuario("Não achei o fifa_ng_db-meta.xml ao lado do banco, e a versão dele não é nenhuma das guardadas.")
        return {"tipo": "db", "caminho": caminho, "meta": dados.meta_guardado(v), "jogo": v, "meta_guardado": v}
    return {"tipo": "db", "caminho": caminho, "meta": m}


# ------------------------------------------------------------------ tabelas e planos
def destino_de(nome):
    m = EST["mapa"].get(nome) or {}
    return m.get("destino") or nome


def esquema_destino(nome_origem):
    """(campos, info, linhas, existe) da tabela final."""
    fo, fd = fonte_origem(), fonte_destino()
    dn = destino_de(nome_origem)
    if fd is not None and fd.tem(dn):
        t = fd.tabela(dn)
        info = dict(t.info)
        if fd.f is not None and not info:
            mc = fd.f.meta.get(dn, {}).get("campos", {}) if hasattr(fd.f, "meta") else {}
            info = {c: {k: v for k, v in i.items() if k != "short"} for c, i in mc.items()}
        return t.campos, info, (t.linhas if fd.tipo != "meta" else None), True
    t = fo.tabela(nome_origem)
    return t.campos, t.info, None, False


def plano_de(nome):
    fo, fd = fonte_origem(), fonte_destino()
    if fo is None:
        raise base.ErroUsuario("Sem origem: importe o banco em Dados do jogo (Super Tool) ou escolha outra origem.")
    t = fo.tabela(nome)
    campos, info, linhas, existe = esquema_destino(nome)
    jo, jd = fo.jogo(), (fd.jogo() if fd else fo.jogo())
    pl = C.plano(t, campos, info, linhas, jo, jd, (EST["mapa"].get(nome) or {}).get("ajustes"))
    pl.update(destino=destino_de(nome), existe_no_destino=existe, jogo_origem=jo, jogo_destino=jd,
              nome_origem=dados.nome_jogo(jo), nome_destino=dados.nome_jogo(jd), chave=C.chave_natural(info))
    return pl, t, campos, info, linhas


def api_plano(q):
    nome = q["tabela"]
    with LOCK:
        pl, t, campos, info, linhas = plano_de(nome)
        fo, fd = fonte_origem(), fonte_destino()
        amostra_t = dados.Tabela(t.nome, t.campos, t.linhas[:40], t.info)
        final, rel = C.converter(amostra_t, pl, campos, info, None, pl["jogo_origem"], pl["jogo_destino"], "substituir")
        # contagens de fora da faixa na tabela inteira (rápido: só simula)
        _, rel_total = C.converter(t, pl, campos, info, None, pl["jogo_origem"], pl["jogo_destino"], "substituir")
    exemplos = {}
    io_ = {c: i for i, c in enumerate(t.campos)}
    for col in pl["colunas"]:
        if col["modo"] == "coluna" and col.get("origem") in io_:
            vals = [l[io_[col["origem"]]] for l in t.linhas[:200]]
            exemplos[col["destino"]] = sorted(set(vals), key=lambda v: (len(v), v))[:6]
    return {"plano": pl, "campos": campos, "campos_origem": t.campos, "amostra": final[:40], "relatorio": rel_total, "exemplos": exemplos,
            "tabelas_destino": [n for n, _, _ in fd.nomes()] if fd else []}


def estado_payload():
    p = PREFS.ler()
    fo, fd = fonte_origem(), fonte_destino()
    tabs = []
    if fo is not None:
        nd = {n: r for n, r, _ in fd.nomes()} if fd else {}
        for n, r, c in fo.nomes():
            dn = destino_de(n)
            tabs.append({"nome": n, "registros": r, "campos": c, "destino": dn, "existe_no_destino": dn in nd if fd else None,
                         "registros_destino": nd.get(dn) if fd else None, "ajustada": bool((EST["mapa"].get(n) or {}).get("ajustes")),
                         "sel": n in EST["sel"]})
    d = dados.estado()
    return {"origem": resumo(fo, p.get("origem") or (dados.banco_atual().reg if dados.banco_atual() else {})) if fo else None,
            "origem_e_banco": not p.get("origem"), "banco": d["banco"], "destino": resumo(fd, p.get("destino") or {}) if fd else None,
            "tabelas": tabs, "sel": EST["sel"], "opcoes": {k: p.get(k) for k in ("saida", "formato", "gravar_db", "modo", "sobrescrever")},
            "rodando": EST["rodando"], "progresso": EST["progresso"], "relatorio": EST["rel"],
            "jogos": [{"id": v["id"], "nome": v["nome"]} for v in dados.esquemas()]}


def api_inicio(_):
    return {"versao": VERSAO, **estado_payload()}


def api_estado(_):
    return estado_payload()


def api_origem(d):
    modo = d.get("modo")
    if modo == "banco":
        PREFS.atualizar(origem=None)
    else:
        if modo == "pasta":
            c = base.dialogo("pasta", "Pasta com as tabelas .txt de origem", base.raiz_trabalho())
        else:
            c = base.dialogo("abrir", "Banco de origem (fifa_ng_db.db com o meta ao lado)", base.raiz_trabalho(),
                             tipos=[("Banco t3db", "*.db"), ("Todos", "*.*")])
        if not c:
            return estado_payload()
        try:
            reg = registrar(c)
            Fonte(reg)
        except dados.ErroDados as ex:
            raise base.ErroUsuario(str(ex))
        PREFS.atualizar(origem=reg)
    with LOCK:
        EST.update(sel=[], mapa={}, rel=None)
    return estado_payload()


def api_destino(d):
    modo = d.get("modo")
    if modo == "limpar":
        PREFS.atualizar(destino=None)
        return estado_payload()
    if modo == "esquema":                                  # o esquema guardado de uma versão (sem precisar do arquivo)
        try:
            meta = dados.meta_guardado(d.get("jogo"))
        except dados.ErroDados as ex:
            raise base.ErroUsuario(str(ex))
        PREFS.atualizar(destino={"tipo": "meta", "caminho": meta, "meta": meta, "jogo": d["jogo"], "esquema": d["jogo"]})
        return estado_payload()
    if modo == "pasta":
        c = base.dialogo("pasta", "Pasta com as tabelas .txt do jogo de destino", base.raiz_trabalho())
    elif modo == "meta":
        c = base.dialogo("abrir", "Meta do banco do jogo de destino (fifa_ng_db-meta.xml)", base.raiz_trabalho(),
                         tipos=[("Meta", "*.xml"), ("Todos", "*.*")])
    else:
        c = base.dialogo("abrir", "Banco do jogo de destino (fifa_ng_db.db com o meta ao lado)", base.raiz_trabalho(),
                         tipos=[("Banco t3db", "*.db"), ("Todos", "*.*")])
    if not c:
        return estado_payload()
    try:
        reg = registrar(c)
        Fonte(reg)
    except dados.ErroDados as ex:
        raise base.ErroUsuario(str(ex))
    PREFS.atualizar(destino=reg)
    return estado_payload()


def api_jogo(d):
    qual, jogo = d.get("qual"), d.get("jogo")
    if qual not in ("origem", "destino") or (jogo or "").rstrip("~") not in {v["id"] for v in dados.esquemas()}:
        raise base.ErroUsuario("Opção inválida.")
    p = PREFS.ler()
    if qual == "origem" and not p.get("origem"):
        try:
            dados.definir_jogo(jogo)
        except dados.ErroDados as ex:
            raise base.ErroUsuario(str(ex))
        _FONTES.clear()
    else:
        reg = dict(p.get(qual) or {})
        if not reg:
            raise base.ErroUsuario("Escolha o banco primeiro.")
        reg["jogo"] = jogo
        PREFS.atualizar(**{qual: reg})
    return estado_payload()


def api_selecionar(d):
    with LOCK:
        nomes = d.get("tabelas") or []
        if d.get("todas") is not None:
            nomes = [t["nome"] for t in estado_payload()["tabelas"] if d.get("filtro", "") in t["nome"]]
        for n in nomes:
            marcar = d.get("marcado", True) if d.get("todas") is None else d["todas"]
            if marcar and n not in EST["sel"]:
                EST["sel"].append(n)
            elif not marcar and n in EST["sel"]:
                EST["sel"].remove(n)
    return estado_payload()


def api_mapear(d):
    nome = d["tabela"]
    with LOCK:
        m = EST["mapa"].setdefault(nome, {})
        if "destino" in d:
            m["destino"] = d["destino"] or None
        if "coluna" in d:
            aj = m.setdefault("ajustes", {})
            if d.get("modo") in (None, "", "auto"):
                aj.pop(d["coluna"], None)
            else:
                aj[d["coluna"]] = {"modo": d["modo"], "valor": d.get("valor", ""), "origem": d.get("origem")}
        if d.get("limpar"):
            m.pop("ajustes", None)
    return api_plano({"tabela": nome})


def api_opcoes(d):
    p = PREFS.ler()
    for k in ("saida", "formato", "gravar_db", "modo", "sobrescrever"):
        if k in d:
            p[k] = d[k]
    if p.get("saida"):
        p["saida"] = os.path.normpath(str(p["saida"]).strip().strip('"'))
    PREFS.gravar(p)
    return estado_payload()


def api_dialogo(d):
    r = base.dialogo("pasta", "Pasta de saída das tabelas convertidas", PREFS.ler().get("saida") or base.raiz_trabalho())
    return {"caminho": r}


def api_converter(d):
    p = PREFS.ler()
    with LOCK:
        if EST["rodando"]:
            raise base.ErroUsuario("Já está convertendo.")
        sel = list(d.get("tabelas") or EST["sel"])
        if not sel:
            raise base.ErroUsuario("Marque as tabelas a converter.")
        if not p.get("saida"):
            raise base.ErroUsuario("Escolha a pasta de saída.")
        if fonte_origem() is None:
            raise base.ErroUsuario("Sem origem.")
        os.makedirs(p["saida"], exist_ok=True)
        existentes = [n for n in sel if os.path.exists(os.path.join(p["saida"], destino_de(n) + ".txt"))]
        if existentes and not p.get("sobrescrever") and not d.get("forcar"):
            return {"confirmar": existentes, **estado_payload()}
        EST.update(rodando=True, progresso=(0, len(sel)), rel=None)
    threading.Thread(target=rodar, args=(sel, p), daemon=True).start()
    return estado_payload()


def rodar(sel, p):
    rel = {"tabelas": [], "erros": [], "db": None, "saida": p["saida"], "quando": time.strftime("%d/%m/%Y %H:%M")}
    blobs = {}
    fd = fonte_destino()
    try:
        for k, nome in enumerate(sel):
            try:
                with LOCK:
                    pl, t, campos, info, linhas = plano_de(nome)
                final, info_c = C.converter(t, pl, campos, info, linhas, pl["jogo_origem"], pl["jogo_destino"], p.get("modo", "substituir"))
                dn = pl["destino"]
                dados.escrever_txt(os.path.join(p["saida"], dn + ".txt"), campos, final, p.get("formato", "utf-16"))
                info_c.update(origem=nome, destino=dn, linhas_finais=len(final), existe_no_destino=pl["existe_no_destino"])
                if p.get("gravar_db") and fd is not None and fd.tipo == "db" and pl["existe_no_destino"]:
                    try:
                        avisos = []
                        ordem_arquivo = [f.nome for f in fd.f.campos_t3(dn)]
                        idx = {c: i for i, c in enumerate(campos)}
                        linhas_arq = [[l[idx[c]] if c in idx else "" for c in ordem_arquivo] for l in final]
                        blobs[dn] = dados.montar_tabela(fd.f, dn, linhas_arq, avisos)
                        info_c["avisos_db"] = avisos[:20]
                    except dados.ErroDados as ex:
                        info_c["avisos_db"] = [str(ex)]
                rel["tabelas"].append(info_c)
            except Exception as ex:  # noqa: BLE001
                rel["erros"].append(f"{nome}: {type(ex).__name__}: {ex}")
            with LOCK:
                EST["progresso"] = (k + 1, len(sel))
        if blobs:
            destino_db = os.path.join(p["saida"], "fifa_ng_db.db")
            dados.gravar_banco(fd.f, blobs, destino_db)
            shutil.copy2(fd.reg["meta"], os.path.join(p["saida"], os.path.basename(fd.reg["meta"])))
            rel["db"] = {"caminho": destino_db, "tabelas": sorted(blobs)}
        escrever_relatorio(rel, p)
    finally:
        with LOCK:
            EST.update(rodando=False, rel=rel)


def escrever_relatorio(rel, p):
    fo, fd = fonte_origem(), fonte_destino()
    linhas = [f"Conversor de Tabelas {VERSAO} — {rel['quando']}",
              f"Origem: {fo.reg.get('caminho') if fo else '?'} ({dados.NOME_JOGO.get(fo.jogo(), '?') if fo else '?'})",
              f"Destino: {fd.reg.get('caminho') if fd else '(sem destino: esquema da origem)'} ({dados.NOME_JOGO.get(fd.jogo(), '?') if fd else '-'})",
              f"Modo: {p.get('modo')} · formato {p.get('formato')}", ""]
    for t in rel["tabelas"]:
        linhas.append(f"{t['origem']} -> {t['destino']}: {t['linhas_finais']} linhas ({t['convertidas']} convertidas"
                      + (f", {t.get('substituidas', 0)} substituídas, {t.get('acrescentadas', 0)} acrescentadas, {t.get('mantidas', 0)} mantidas do destino" if t.get("modo") == "mesclar" else "") + ")")
        if not t.get("existe_no_destino"):
            linhas.append("    a tabela não existe no destino: gravada com as colunas da origem")
        if t["novas"]:
            linhas.append("    colunas novas (valor mais comum do destino): " + ", ".join(t["novas"]))
        if t["removidas"]:
            linhas.append("    colunas que o destino não tem (descartadas): " + ", ".join(t["removidas"]))
        for r, n in t["regras"].items():
            linhas.append(f"    {r}: {n}")
        for c, n in t["fora_da_faixa"].items():
            linhas.append(f"    {c}: {n} valores fora da faixa do destino (ajustados)")
        for c, n in t["cortados"].items():
            linhas.append(f"    {c}: {n} textos cortados")
        for a in t.get("avisos_db", []):
            linhas.append(f"    .db: {a}")
    for e in rel["erros"]:
        linhas.append("ERRO " + e)
    if rel.get("db"):
        linhas += ["", f"Banco novo: {rel['db']['caminho']} (tabelas trocadas: {', '.join(rel['db']['tabelas'])})"]
    with open(os.path.join(p["saida"], "relatorio_conversao_tabelas.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")


def api_abrir(d):
    alvo = d.get("caminho") or PREFS.ler().get("saida")
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Ainda não existe: {alvo or '(sem pasta de saída)'}")
    base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def _protegido(fn):
    def f(d):
        try:
            return fn(d)
        except dados.ErroDados as ex:
            raise base.ErroUsuario(str(ex))
    return f


ROTAS_GET = {k: _protegido(v) for k, v in {"inicio": api_inicio, "estado": api_estado, "plano": api_plano,
                                          "versao": lambda _: {"versao": VERSAO}}.items()}
ROTAS_POST = {k: _protegido(v) for k, v in {"origem": api_origem, "destino": api_destino, "jogo": api_jogo,
                                           "selecionar": api_selecionar, "mapear": api_mapear, "opcoes": api_opcoes,
                                           "dialogo": api_dialogo, "converter": api_converter, "abrir": api_abrir}.items()}


def main():
    ap = argparse.ArgumentParser(description="Conversor de Tabelas (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8774)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    a = ap.parse_args()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, nome="ConversorTabelas/" + VERSAO)
    base.servir(handler, a.porta, "Conversor de Tabelas", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
