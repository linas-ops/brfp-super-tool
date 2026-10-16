"""Atualizador de Squads (BRFP Super Tool) — leva o que o mod acrescentou para o squad oficial mais recente da EA.

    python servidor.py [--porta 8778] [--sem-janela]

Entradas: o squad oficial mais recente da EA (a base), o squad do mod e, opcional, o squad da EA em que o mod foi feito.
Os nomes dos jogadores da EA vêm do banco do jogo (Dados do jogo do Super Tool, se for o FC 27, ou o banco do RDBM 26 ·
Add-on FC 27) para achar jogadores duplicados. A regra da mescla está em mesclar.py; a leitura e a gravação dos squads
em squad.py.
"""
import argparse
import os
import sys
import threading
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import dados  # noqa: E402
import mesclar  # noqa: E402
import squad  # noqa: E402

VERSAO = "1.0"
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"), {"ea": None, "mod": None, "base": None, "nomes": None, "ultimo": None})
SAIDA = os.path.join(AQUI, "saida")
PASTA_FC27 = os.path.expandvars(r"%LOCALAPPDATA%\EA SPORTS FC 27\settings")
LOCK = threading.RLock()
EST = {"rodando": False, "etapa": "", "frac": 0.0, "analise": None, "relatorio": None, "erro": None, "br": None, "chave": None}
_CACHE = {"nomes": None, "obj": None}


def meta_fc27():
    return dados.meta_guardado("fc27")


# ------------------------------------------------------------------ arquivos
def info_squad(caminho):
    if not caminho:
        return None
    if not os.path.isfile(caminho):
        return {"caminho": caminho, "erro": "O arquivo não existe mais."}
    chave = (caminho, os.path.getmtime(caminho), os.path.getsize(caminho))
    if chave not in _INFO:
        _INFO[chave] = _info_squad(caminho)
    return _INFO[chave]


_INFO = {}


def _info_squad(caminho):
    try:
        s = squad.Squad(caminho, meta_fc27())
    except (squad.ErroSquad, OSError, dados.ErroDados) as ex:
        return {"caminho": caminho, "erro": str(ex)}
    v = s.tabelas.get("version")
    return {"caminho": caminho, "nome": os.path.basename(caminho), "nome_jogo": s.nome_jogo,
            "tamanho": os.path.getsize(caminho), "quando": time.strftime("%d/%m/%Y %H:%M", time.localtime(os.path.getmtime(caminho))),
            "jogadores": s.tabela("players").validos if s.tem("players") else 0,
            "times": s.tabela("teams").validos if s.tem("teams") else 0,
            "versao": (dict(zip([c.nome for c in v.campos], v.linhas[0])).get("major") if v and v.linhas else None)}


# ------------------------------------------------------------------ nomes dos jogadores (banco do jogo)
def fonte_nomes():
    """(rótulo, caminho do .db, meta) do banco com a tabela playernames do FC 27."""
    p = PREFS.ler().get("nomes")
    if p and os.path.isfile(p.get("caminho", "")):
        return "escolhido aqui", p["caminho"], p.get("meta")
    b = dados.banco_atual()
    if b is not None and (b.jogo or "").rstrip("~") == "fc27" and b.tem("playernames"):
        return "Dados do jogo (Super Tool)", b.reg["caminho"], b.reg.get("meta")
    perfil = os.path.join(base.pasta_rdbm(), "perfil", "Templates", "FC 26")
    db = os.path.join(perfil, "fifa_ng_db.db")
    if os.path.isfile(db) and os.path.isfile(os.path.join(perfil, "fifa_ng_db-meta.xml")):
        return "RDBM 26 · Add-on FC 27", db, os.path.join(perfil, "fifa_ng_db-meta.xml")
    return None, None, None


def nomes_jogo():
    rot, caminho, meta = fonte_nomes()
    if not caminho:
        return {}, None
    chave = (caminho, os.path.getmtime(caminho))
    if _CACHE["nomes"] and _CACHE["nomes"][0] == chave:
        return _CACHE["nomes"][1], rot
    b = dados.banco_atual()
    if b is not None and b.reg.get("caminho") == caminho:
        t = b.tabela("playernames")
    else:
        if not meta:
            v, _ = dados.detectar_versao_db(caminho)
            meta = dados.meta_guardado(v.rstrip("~")) if v not in ("?",) else meta_fc27()
        t = dados.FonteDB(caminho, meta).tabela("playernames")
    i, n = t.col("nameid"), t.col("name")
    out = {}
    for l in t.linhas:
        try:
            out[int(l[i])] = l[n]
        except ValueError:
            pass
    _CACHE["nomes"] = (chave, out)
    return out, rot


# ------------------------------------------------------------------ estado
def payload():
    p = PREFS.ler()
    rot, caminho, _ = fonte_nomes()
    a = EST["analise"]
    br = EST["br"]
    return {"versao": VERSAO, "ea": info_squad(p.get("ea")), "mod": info_squad(p.get("mod")), "base": info_squad(p.get("base")),
            "nomes": {"fonte": rot, "caminho": caminho}, "rodando": EST["rodando"], "etapa": EST["etapa"], "frac": EST["frac"],
            "erro": EST["erro"], "analise": a, "br": sorted(br) if br is not None else None, "relatorio": EST["relatorio"],
            "ultimo": p.get("ultimo"), "pasta_fc27": PASTA_FC27}


def api_inicio(_):
    return payload()


def api_estado(_):
    return payload()


def _invalidar():
    EST.update(analise=None, relatorio=None, erro=None, br=None, chave=None)
    _CACHE["obj"] = None


def api_escolher(d):
    qual = d.get("qual")
    if qual not in ("ea", "mod", "base"):
        raise base.ErroUsuario("Opção inválida.")
    caminho = d.get("caminho")
    if not caminho:
        titulos = {"ea": "Squad oficial mais recente da EA", "mod": "Squad do mod (BRFP)",
                   "base": "Squad da EA em que o mod foi feito (opcional)"}
        atual = PREFS.ler().get(qual)
        caminho = base.dialogo("abrir", titulos[qual], atual or (PASTA_FC27 if os.path.isdir(PASTA_FC27) else base.raiz_trabalho()),
                               tipos=[("Squads", "Squads*"), ("Todos", "*.*")])
        if not caminho:
            return payload()
    caminho = os.path.abspath(caminho)
    try:
        squad.Squad(caminho, meta_fc27())
    except (squad.ErroSquad, OSError) as ex:
        raise base.ErroUsuario(str(ex))
    with LOCK:
        if EST["rodando"]:
            raise base.ErroUsuario("Espere terminar.")
        PREFS.atualizar(**{qual: caminho})
        _invalidar()
    return payload()


def api_limpar(d):
    qual = d.get("qual")
    if qual not in ("ea", "mod", "base", "nomes"):
        raise base.ErroUsuario("Opção inválida.")
    with LOCK:
        PREFS.atualizar(**{qual: None})
        _invalidar()
    return payload()


def api_nomes(_):
    c = base.dialogo("abrir", "Banco do FC 27 (fifa_ng_db.db) para os nomes dos jogadores", base.raiz_trabalho(),
                     tipos=[("Banco t3db", "*.db"), ("Todos", "*.*")])
    if not c:
        return payload()
    meta = dados.achar_meta(c)
    try:
        f = dados.FonteDB(c, meta or meta_fc27())
        if "playernames" not in f.tabs:
            raise base.ErroUsuario("Esse banco não tem a tabela playernames.")
    except dados.ErroDados as ex:
        raise base.ErroUsuario(str(ex))
    with LOCK:
        PREFS.atualizar(nomes={"caminho": c, "meta": meta or meta_fc27()})
        _invalidar()
    return payload()


# ------------------------------------------------------------------ análise e geração (em segundo plano)
def _progresso(msg, frac):
    with LOCK:
        EST.update(etapa=msg, frac=frac)


def _carregar():
    p = PREFS.ler()
    if not p.get("ea") or not p.get("mod"):
        raise base.ErroUsuario("Escolha o squad da EA e o do mod.")
    chave = (p["ea"], os.path.getmtime(p["ea"]), p["mod"], os.path.getmtime(p["mod"]), p.get("base"), str(fonte_nomes()[1]))
    if _CACHE["obj"] is not None and EST["chave"] == chave:
        return _CACHE["obj"]
    _progresso("Lendo o squad da EA", 0.02)
    ea = squad.Squad(p["ea"], meta_fc27())
    _progresso("Lendo o squad do mod", 0.04)
    mod = squad.Squad(p["mod"], meta_fc27())
    bs = squad.Squad(p["base"], meta_fc27()) if p.get("base") else None
    _progresso("Lendo os nomes dos jogadores do jogo", 0.05)
    nomes, _ = nomes_jogo()
    obj = mesclar.Atualizador(ea, mod, nomes, bs, progresso=_progresso)
    obj.resumo = obj.analisar()
    _CACHE["obj"] = obj
    EST["chave"] = chave
    return obj


def _rodar(fn):
    def f():
        try:
            fn()
        except base.ErroUsuario as ex:
            with LOCK:
                EST["erro"] = str(ex)
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            with LOCK:
                EST["erro"] = f"{type(ex).__name__}: {ex}"
        finally:
            with LOCK:
                EST.update(rodando=False, etapa="", frac=0.0)
    with LOCK:
        if EST["rodando"]:
            raise base.ErroUsuario("Já está rodando.")
        EST.update(rodando=True, erro=None, etapa="Começando", frac=0.0)
    threading.Thread(target=f, daemon=True).start()


def api_analisar(_):
    def tarefa():
        obj = _carregar()
        with LOCK:
            EST["analise"] = obj.resumo
            if EST["br"] is None:
                EST["br"] = {b["id"] for b in obj.resumo["brasileiros"]}
            EST["relatorio"] = None
    _rodar(tarefa)
    return payload()


def api_times(d):
    with LOCK:
        if EST["analise"] is None:
            raise base.ErroUsuario("Analise os squads primeiro.")
        br = EST["br"] if EST["br"] is not None else set()
        todos = {b["id"] for b in EST["analise"]["brasileiros"]}
        if d.get("todos") is not None:
            alvo = todos if d.get("so_na_ea") is None else {b["id"] for b in EST["analise"]["brasileiros"] if b["na_ea"]}
            br = (br | alvo) if d["todos"] else (br - alvo)
        else:
            tid = int(d["id"])
            br = (br | {tid}) if d.get("marcado") else (br - {tid})
        EST["br"] = br
        EST["relatorio"] = None
    return payload()


def nome_saida():
    return "Squads" + time.strftime("%Y%m%d%H%M%S")


def api_gerar(d):
    p = PREFS.ler()
    if EST["analise"] is None:
        raise base.ErroUsuario("Analise os squads primeiro.")
    destino = d.get("destino")
    if not destino:
        pasta = os.path.dirname(p.get("ultimo") or "") or os.path.dirname(p["ea"])
        destino = base.dialogo("salvar", "Onde gravar o squad atualizado", pasta, tipos=[("Squads", "Squads*"), ("Todos", "*.*")],
                               nome=nome_saida())
        if not destino:
            return payload()
    destino = os.path.abspath(destino)
    for k in ("ea", "mod", "base"):
        if p.get(k) and os.path.normcase(os.path.abspath(p[k])) == os.path.normcase(destino):
            raise base.ErroUsuario("Grave com outro nome: o squad atualizado não pode substituir um dos squads de entrada.")
    br = set(EST["br"] or ())

    def tarefa():
        t0 = time.time()
        obj = _carregar()
        _progresso("Mesclando", 0.2)
        obj.avisos = []
        rel = obj.executar(br)
        _progresso("Gravando o squad", 0.9)
        avisos = []
        tam = obj.ea.gravar(destino, obj.novas, obj.capacidades(), avisos)
        rel.update(destino=destino, tamanho=tam, avisos_gravacao=avisos, segundos=round(time.time() - t0, 1),
                   quando=time.strftime("%d/%m/%Y %H:%M"))
        _progresso("Conferindo o arquivo gravado", 0.96)
        try:
            s = squad.Squad(destino, meta_fc27())
            rel["conferido"] = {"jogadores": s.tabela("players").validos, "times": s.tabela("teams").validos,
                                "vinculos": s.tabela("teamplayerlinks").validos}
        except squad.ErroSquad as ex:
            rel["conferido"] = {"erro": str(ex)}
        rel["arquivo_relatorio"] = escrever_relatorio(rel, p, obj)
        PREFS.atualizar(ultimo=destino)
        _CACHE["obj"] = None                                 # a mescla altera o objeto: a próxima recomeça
        with LOCK:
            EST["chave"] = None
            EST["relatorio"] = rel
    _rodar(tarefa)
    return payload()


def escrever_relatorio(rel, p, obj):
    os.makedirs(SAIDA, exist_ok=True)
    nome = os.path.basename(rel["destino"])
    caminho = os.path.join(SAIDA, f"{nome}_relatorio.txt")
    L = [f"Atualizador de Squads {VERSAO} — {rel['quando']}",
         f"Squad da EA (base): {p.get('ea')}", f"Squad do mod: {p.get('mod')}",
         f"Squad base do mod: {p.get('base') or '(não informado: jogadores criados pelo mod = com nome editado)'}",
         f"Squad atualizado: {rel['destino']} ({rel['tamanho'] / 1048576:.1f} MB)", "",
         f"Times brasileiros substituídos pelo mod: {rel['times_brasileiros']} ({rel['times_brasileiros_na_ea']} já existiam na EA)",
         f"Times que só existem no mod (acrescentados): {rel['times_novos']}",
         f"Jogadores do mod acrescentados: {rel['jogadores_importados']}",
         f"Jogadores da EA com os dados do mod (estão em time brasileiro no mod): {rel['jogadores_mod_ea']}",
         f"Jogadores da EA excluídos (estavam só em times brasileiros): {rel['jogadores_excluidos']}",
         f"Jogadores da EA que foram para os sem contrato (tinham seleção): {rel['para_livres']}",
         f"Jogadores no squad final: {rel['jogadores_finais']}", ""]
    if rel["duplicados"]:
        L.append("Jogadores duplicados unidos:")
        for d in rel["duplicados"]:
            if d["tipo"] == "ea":
                L.append(f"  {d['nome']}: mod {d['mod']} = EA {d['ea']} ({d['nome_ea']}) — ficou o ID da EA com os dados "
                         + ("do mod (time brasileiro no mod)" if d["dados"] == "mod" else "da EA"))
            else:
                L.append(f"  {d['nome']}: duas vezes no mod ({d['mod']} e {d['fica']}) — ficou o {d['fica']}")
        L.append("")
    if rel["ids_trocados"]:
        L.append("IDs que a EA passou a usar para outro jogador (o do mod ganhou um ID novo):")
        L += [f"  {r['nome']}: {r['mod']} -> {r['novo']} (na EA o {r['mod']} é {r['nome_ea']})" for r in rel["ids_trocados"]]
        L.append("")
    if rel["escalacoes"]:
        L.append("Escalações refeitas (o elenco mudou):")
        L += [f"  {e['nome']}: {e['jogadores']} jogadores, {e['entraram']} entraram, {e['titulares_trocados']} titular(es) trocado(s)"
              for e in rel["escalacoes"]]
        L.append("")
    if rel["ligas_do_mod"]:
        L.append("Ligas com os dados do mod: " + ", ".join(str(x) for x in rel["ligas_do_mod"]))
    if rel["competicoes_novas"]:
        L.append("Competições acrescentadas do mod: " + ", ".join(str(x) for x in rel["competicoes_novas"]))
    L.append("")
    L.append("Tabelas alteradas (registros antes -> depois):")
    L += [f"  {n}: {a} -> {b}" for n, (a, b) in rel["tabelas"].items()]
    if rel["avisos"] or rel.get("avisos_gravacao"):
        L += ["", "Avisos:"] + [f"  {a}" for a in rel["avisos"] + rel.get("avisos_gravacao", [])]
    L += ["", "Times brasileiros (dados do mod):"]
    L += [f"  {t} {obj.nome_time(t)}" for t in sorted(obj.B, key=obj.nome_time)]
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return caminho


def api_abrir(d):
    alvo = d.get("caminho")
    if not alvo or not os.path.exists(alvo):
        raise base.ErroUsuario(f"Não existe: {alvo or '?'}")
    if alvo.lower().endswith(".txt") and not d.get("pasta"):
        os.startfile(alvo) if os.name == "nt" else base.abrir_no_explorer(alvo)
    else:
        base.abrir_no_explorer(alvo, selecionar=os.path.isfile(alvo))
    return {}


def _protegido(fn):
    def f(d):
        try:
            return fn(d)
        except (dados.ErroDados, squad.ErroSquad) as ex:
            raise base.ErroUsuario(str(ex))
    return f


ROTAS_GET = {k: _protegido(v) for k, v in {"inicio": api_inicio, "estado": api_estado,
                                          "versao": lambda _: {"versao": VERSAO}}.items()}
ROTAS_POST = {k: _protegido(v) for k, v in {"escolher": api_escolher, "limpar": api_limpar, "nomes": api_nomes,
                                           "analisar": api_analisar, "times": api_times, "gerar": api_gerar,
                                           "abrir": api_abrir}.items()}


def main():
    ap = argparse.ArgumentParser(description="Atualizador de Squads (BRFP Super Tool)")
    ap.add_argument("--porta", type=int, default=8778)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    a = ap.parse_args()
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, nome="AtualizadorSquads/" + VERSAO)
    base.servir(handler, a.porta, "Atualizador de Squads", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
