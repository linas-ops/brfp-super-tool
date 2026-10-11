"""Criador de Ligas e Times — grava o resultado de um Projeto (gerador.py).

Na pasta de saída:
    db\\fifa_ng_db.db + fifa_ng_db-meta.xml   cópia do banco importado com as linhas novas (o original não é tocado)
    tabelas\\<tabela>.txt                      as tabelas alteradas inteiras (UTF-16, para importar pelo RDBM/DB Master)
    idioma\\LanguageStrings_novos.txt          só os textos novos (nomes de times e ligas)
    idioma\\LanguageStrings1.txt / 2.txt       os do idioma importado + os novos, já ordenados (para o FET)
    imagens\\escudos, imagens\\jogadores        escudos e fotos da API (fotos -> Criador de Minifaces)
    relatorio.txt, projeto.json                o que foi criado e o mapa API -> ids do jogo
O mapa também vai para dados\\criador_mapa.json, usado na atualização de elencos.
"""
import hashlib
import json
import os
import shutil
import threading
import time

import apifutebol
import dados

MAPA = os.path.join(os.environ.get("BRFP_DADOS") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dados"), "criador_mapa.json")


def linhas_tabela(banco, nome, novas, alteradas=None, removidas=None):
    """Linhas (listas na ordem dos campos) = originais (com as alterações, sem as removidas) + novas; reordena se a
    tabela estava ordenada pela chave."""
    t = banco.tabela(nome)
    alteradas, removidas = alteradas or {}, removidas or set()
    linhas = []
    for n, l in enumerate(t.linhas):
        if n in removidas:
            continue
        l = list(l)
        for campo, v in (alteradas.get(n) or {}).items():
            i = t.col(campo)
            if i is not None:
                l[i] = str(v)
        linhas.append(l)
    for d in novas:
        linhas.append([str(d.get(c, "0")) for c in t.campos])
    chaves = [c for c, i in t.info.items() if i.get("chave")]
    if chaves:
        i = t.col(chaves[0])
        orig = [int(l[i]) for l in t.linhas if l[i].lstrip("-").isdigit()]
        if orig == sorted(orig):
            linhas.sort(key=lambda l: int(l[i]) if l[i].lstrip("-").isdigit() else 0)
    return t.campos, linhas


def gravar(projeto, pasta, nome_saida, idioma=None, baixar_imagens=True, progresso=None, internationals=None):
    passo = progresso or (lambda m, f=None: None)
    b = projeto.b
    destino = os.path.join(pasta, nome_saida)
    os.makedirs(destino, exist_ok=True)
    avisos = list(projeto.avisos)
    feitos = {"tabelas": {}, "db": None, "idioma": None}
    # tabelas
    blobs = {}
    pasta_txt = os.path.join(destino, "tabelas")
    os.makedirs(pasta_txt, exist_ok=True)
    alt = getattr(projeto, "alt", {}) or {}
    rem = getattr(projeto, "rem", {}) or {}
    nomes_tab = sorted(n for n in set(projeto.novas) | set(alt) | set(rem) if projeto.novas.get(n) or alt.get(n) or rem.get(n))
    passo("Conferindo os vínculos", 0.02)
    problemas = integridade(projeto)
    if problemas["graves"]:
        raise RuntimeError("O banco não foi gravado — a conferência achou problemas: " + "; ".join(problemas["graves"][:8]))
    avisos += problemas["avisos"][:20]
    for i, nome in enumerate(nomes_tab):
        novas = projeto.novas.get(nome, [])
        passo(f"Tabela {nome}", i / max(1, len(nomes_tab)))
        campos, linhas = linhas_tabela(b, nome, novas, alt.get(nome), rem.get(nome))
        dados.escrever_txt(os.path.join(pasta_txt, nome + ".txt"), campos, linhas, "utf-16")
        feitos["tabelas"][nome] = {"novas": len(novas), "alteradas": len(alt.get(nome) or {}), "removidas": len(rem.get(nome) or ())}
        if b.fonte.tipo == "db":
            av = []
            blobs[nome] = dados.montar_tabela(b.fonte, nome, linhas, av)
            avisos += av[:20]
    if b.fonte.tipo == "db":
        passo("Banco novo", 0.8)
        pdb = os.path.join(destino, "db")
        os.makedirs(pdb, exist_ok=True)
        arq = os.path.join(pdb, "fifa_ng_db.db")
        dados.gravar_banco(b.fonte, blobs, arq)
        shutil.copy2(b.fonte.meta_caminho, os.path.join(pdb, os.path.basename(b.fonte.meta_caminho)))
        # confere lendo de volta
        f2 = dados.FonteDB(arq, b.fonte.meta_caminho)
        for nome in blobs:
            n = f2.tabs[nome]["hdr"][5]
            esperado = len(b.tabela(nome).linhas) + len(projeto.novas.get(nome, [])) - len(rem.get(nome) or ())
            if n != esperado:
                raise RuntimeError(f"Conferência falhou em {nome}: {n} registros, esperado {esperado}.")
        feitos["db"] = arq
    else:
        avisos.append("O banco importado é uma pasta de tabelas .txt: o resultado sai só em tabelas\\ (importe pelo RDBM).")
    # idioma
    passo("Idioma", 0.85)
    pid = os.path.join(destino, "idioma")
    os.makedirs(pid, exist_ok=True)
    novos = sorted(((k, v, dados._hash_idioma(k)) for k, v in projeto.idioma_novo.items()), key=lambda x: x[2])
    with open(os.path.join(pid, "LanguageStrings_novos.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("stringid\tsourcetext\thashid\n")
        for k, v, h in novos:
            f.write(f"{k}\t{v}\t{h}\n")
    feitos["idioma"] = len(novos)
    if idioma is not None and getattr(idioma, "arquivos", None) and all(a.lower().endswith(".txt") for a in idioma.arquivos):
        try:
            _mesclar_idioma(idioma.arquivos, novos, pid)
        except (OSError, ValueError) as ex:
            avisos.append(f"Idioma completo não gerado: {ex}")
    # internationals.txt (seleções novas no TIER_AND_OBJECTIVES)
    feitos["internationals"] = _internationals(projeto, destino, internationals, avisos)
    # imagens
    feitos["fotos"] = []
    if baixar_imagens:
        passo("Escudos e fotos", 0.9)
        av, feitos["fotos"] = _baixar_imagens(projeto, destino)
        avisos += av
    # relatório, projeto e mapa
    mapa = {"times": {}, "jogadores": {}, "ligas": {}, "tm_times": {}, "tm_jogadores": {}}
    for t in projeto.resumo:
        pre = "tm_" if t.get("fonte") == "transfermarkt" else ""      # ids de cada fonte no seu próprio espaço
        mapa[pre + "times"][str(t["api_id"])] = t["teamid"]
        for j in t["jogadores"]:
            if j.get("api_id") is not None and str(j["api_id"]).isdigit():
                mapa[pre + "jogadores"][str(j["api_id"])] = str(j["playerid"])
    for k, v in (projeto.ligas_criadas if hasattr(projeto, "ligas_criadas") else {}).items():
        mapa["ligas"][str(k)] = v
    with open(os.path.join(destino, "projeto.json"), "w", encoding="utf-8") as f:
        json.dump({"criado": time.strftime("%Y-%m-%d %H:%M"), "times": projeto.resumo, "tabelas": feitos["tabelas"],
                   "mapa": mapa, "avisos": avisos, "fotos": feitos["fotos"], "internationals": feitos["internationals"]},
                  f, ensure_ascii=False, indent=1)
    _atualizar_mapa(mapa)
    _relatorio(projeto, destino, feitos, avisos)
    passo("Pronto", 1.0)
    return {"pasta": destino, **feitos, "avisos": avisos}


def _final(projeto, nome):
    """Linhas da tabela como vão ficar (dicts), ou None se a tabela não existe no banco."""
    if not projeto.b.tem(nome):
        return None
    t = projeto.b.tabela(nome)
    campos, linhas = linhas_tabela(projeto.b, nome, projeto.novas.get(nome, []), (getattr(projeto, "alt", {}) or {}).get(nome),
                                   (getattr(projeto, "rem", {}) or {}).get(nome))
    return [dict(zip(t.campos, l)) for l in linhas]


def integridade(projeto):
    """Confere os times criados ou mexidos: elenco, escalação padrão, cobradores, números, ids repetidos.
    graves = impedem gravar (o jogo travaria); avisos = vão para o relatório."""
    graves, avisos = [], []
    mexidos = {d["teamid"] for d in projeto.novas.get("teams", [])}
    for tab in ("teamplayerlinks", "teams", "default_teamsheets", "default_mentalities", "leagueteamlinks"):
        t = projeto.b.tabela(tab) if projeto.b.tem(tab) else None
        if not t or t.col("teamid") is None:
            continue
        i = t.col("teamid")
        for n in list((getattr(projeto, "alt", {}) or {}).get(tab, {})) + list((getattr(projeto, "rem", {}) or {}).get(tab, ())):
            mexidos.add(t.linhas[n][i])
        mexidos |= {d.get("teamid") for d in projeto.novas.get(tab, [])}
    mexidos.discard(None)

    def original(nome):
        return projeto.b.tabela(nome).dicts() if projeto.b.tem(nome) else []
    # o que já estava errado no banco importado não impede gravar (só vai para o relatório)
    antes = _problemas_times(mexidos, original("teamplayerlinks"), {d["playerid"] for d in original("players")},
                             original("default_mentalities"), original("default_teamsheets"), original("teams"))
    depois = _problemas_times(mexidos, _final(projeto, "teamplayerlinks") or [], {d["playerid"] for d in (_final(projeto, "players") or [])},
                              _final(projeto, "default_mentalities") or [], _final(projeto, "default_teamsheets") or [],
                              _final(projeto, "teams") or [])
    for chave, (grave, texto) in depois.items():
        if chave in antes:
            avisos.append(texto + " (já estava assim no banco importado)")
        elif grave:
            graves.append(texto)
        else:
            avisos.append(texto)
    for tab, chave in (("players", "playerid"), ("teams", "teamid"), ("skins", "assetid"), ("manager", "managerid")):
        linhas = _final(projeto, tab)
        if linhas is None:
            continue
        cont = {}
        for d in linhas:
            cont[d[chave]] = cont.get(d[chave], 0) + 1
        rep = [k for k, n in cont.items() if n > 1]
        novos = {d[chave] for d in projeto.novas.get(tab, [])}
        rep_novos = [k for k in rep if k in novos]
        if rep_novos:
            graves.append(f"{tab}: {chave} repetido ({', '.join(rep_novos[:5])})")
    return {"graves": graves, "avisos": avisos}


def _problemas_times(times, tpl, jogadores, mentalidades, folhas, teams):
    """{chave: (grave, texto)} dos problemas de elenco/escalação dos times indicados."""
    out = {}
    elenco = {}
    vistos = set()
    for d in tpl:
        if d["teamid"] not in times:
            continue
        chave = (d["teamid"], d["playerid"])
        if chave in vistos:
            out[("dup",) + chave] = (True, f"jogador {d['playerid']} duas vezes no time {d['teamid']}")
        vistos.add(chave)
        if d["playerid"] not in jogadores:
            out[("sem", d["teamid"], d["playerid"])] = (True, f"time {d['teamid']}: vínculo com o jogador {d['playerid']}, que não existe")
        elenco.setdefault(d["teamid"], []).append(d)
    for tid, vs in elenco.items():
        if tid in ("111592", "131368", "131680"):
            continue
        nums = [v["jerseynumber"] for v in vs]
        for n in sorted({n for n in nums if nums.count(n) > 1}):
            out[("num", tid, n)] = (False, f"time {tid}: número {n} repetido")
    ids_time = {tid: {v["playerid"] for v in vs} for tid, vs in elenco.items()}
    for tab, linhas, campos in (("default_mentalities", mentalidades, [f"playerid{i}" for i in range(11)]),
                                ("default_teamsheets", folhas, [f"playerid{i}" for i in range(52)])):
        for d in linhas:
            tid = d.get("teamid")
            if tid not in times or tid not in ids_time:
                continue
            for c in campos:
                if c in d and d[c] not in ("-1", "", "0") and d[c] not in ids_time[tid]:
                    out[(tab, tid, d[c])] = (True, f"{tab} do time {tid}: jogador {d[c]} escalado fora do elenco")
    for d in teams:
        if d["teamid"] not in times or d["teamid"] not in ids_time:
            continue
        for c in ("captainid", "penaltytakerid", "freekicktakerid", "leftcornerkicktakerid", "rightcornerkicktakerid"):
            if c in d and d[c] not in ("-1", "0", "") and d[c] not in ids_time[d["teamid"]]:
                out[("cob", d["teamid"], c, d[c])] = (True, f"time {d['teamid']}: {c} = {d[c]}, que não está no elenco")
    return out


def _mesclar_idioma(arquivos, novos, pasta):
    """LanguageStrings1/2 completos: as linhas do idioma importado + as novas, ordenadas pelo hashid e divididas no mesmo
    ponto dos arquivos originais."""
    linhas = []
    limites = []
    for a in sorted(arquivos):
        campos, ls, _ = dados.ler_txt(a)
        ci, cs, ch = campos.index("stringid"), campos.index("sourcetext"), campos.index("hashid")
        hs = [int(l[ch]) for l in ls if len(l) > ch and l[ch].lstrip("-").isdigit()]
        limites.append(max(hs) if hs else None)
        for l in ls:
            if len(l) > ch:
                linhas.append((l[ci], l[cs], int(l[ch]) if l[ch].lstrip("-").isdigit() else 0))
    chaves_novas = {k for k, _, _ in novos}
    linhas = [l for l in linhas if l[0] not in chaves_novas] + list(novos)
    linhas.sort(key=lambda x: x[2])
    partes = [[] for _ in arquivos]
    for l in linhas:
        for i, lim in enumerate(limites):
            if lim is None or l[2] <= lim or i == len(limites) - 1:
                partes[i].append(l)
                break
    for i, a in enumerate(sorted(arquivos)):
        with open(os.path.join(pasta, os.path.basename(a)), "w", encoding="utf-8", newline="\r\n") as f:
            f.write("stringid\tsourcetext\thashid\n")
            for k, v, h in partes[i]:
                f.write(f"{k}\t{v}\t{h}\n")


def _baixar_imagens(projeto, destino):
    """Escudos e fotos (servidor de imagens da API: não gasta chamadas do plano)."""
    avisos = []
    pe = os.path.join(destino, "imagens", "escudos")
    pj = os.path.join(destino, "imagens", "jogadores")
    os.makedirs(pe, exist_ok=True)
    os.makedirs(pj, exist_ok=True)
    tarefas = []
    fotos = []
    for t in projeto.resumo:
        logo = t.get("logo")
        if logo and not t.get("atualiza"):
            tarefas.append((logo, os.path.join(pe, f"{t['teamid']}.png")))
        for j in t["jogadores"]:
            if j.get("foto") and not j.get("existente"):          # jogadores do banco (seleções) já têm cabeça/foto no jogo
                dst = os.path.join(pj, f"{j['playerid']}.png")
                tarefas.append((j["foto"], dst))
                fotos.append({"caminho": dst, "playerid": str(j["playerid"]), "nome": j.get("nome") or "", "time": t["nome"],
                              "camisa": j.get("camisa")})
    erros = []
    hashes = {}
    renomeados = {}
    trava = threading.Lock()

    def baixar(lote):
        for url, dst in lote:
            try:
                jpg = os.path.splitext(dst)[0] + ".jpg"
                if os.path.isfile(jpg):
                    renomeados[dst] = dst = jpg
                if os.path.isfile(dst):
                    with open(dst, "rb") as f:
                        dados_img = f.read()
                else:
                    dados_img = apifutebol.baixar(url)
                    if dados_img[:3] == b"\xff\xd8\xff":          # algumas "png" da API são JPEG
                        renomeados[dst] = dst = jpg
                    elif dados_img[:4] != b"\x89PNG":
                        continue
                    with open(dst, "wb") as f:
                        f.write(dados_img)
                    time.sleep(0.05)
                with trava:
                    hashes.setdefault(hashlib.md5(dados_img).hexdigest(), []).append(dst)
            except Exception as ex:  # noqa: BLE001
                erros.append(f"{os.path.basename(dst)}: {ex}")
    lotes = [tarefas[i::4] for i in range(4)]
    ths = [threading.Thread(target=baixar, args=(l,)) for l in lotes]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    # "sem foto" da API: a mesma imagem genérica para todo mundo que não tem foto -> fora (não vai para as minifaces)
    genericas = set()
    for h, arqs in hashes.items():
        if h in FOTOS_GENERICAS or (len(arqs) >= 3 and all(os.path.dirname(a) == pj for a in arqs)):
            genericas |= set(arqs)
    for a in genericas:
        try:
            os.remove(a)
        except OSError:
            pass
    if genericas:
        avisos.append(f"{len(genericas)} jogador(es) sem foto na API (a imagem genérica foi descartada).")
    if erros:
        avisos.append(f"{len(erros)} imagem(ns) não baixada(s) (ex.: {erros[0]}).")
    for f in fotos:
        f["caminho"] = renomeados.get(f["caminho"], f["caminho"])
    return avisos, [f for f in fotos if os.path.isfile(f["caminho"])]


FOTOS_GENERICAS = {"430d67fd79ad0a355b212d5780886e34", "f512b984f93ca6915dd623351b93b531"}


def _internationals(projeto, destino, intl, avisos):
    """Seleções novas -> linhas do TIER_AND_OBJECTIVES: nível pelo das seleções de força parecida, confederação da
    nação no banco e os objetivos mais comuns desse nível. Grava o internationals.txt importado + as linhas novas."""
    novas = [s for s in getattr(projeto, "selecoes", []) if s.get("novo")]
    if not novas:
        return None
    niveis = projeto.nivel_time_db
    linhas = []
    for s in novas:
        if intl is not None:
            tier = intl.tier_sugerido(s["nivel"], s["genero"], niveis)
            obj = intl.objetivos_do_tier(tier, s["genero"])
        else:
            tier = 7 if s["nivel"] < 72 else 5 if s["nivel"] < 76 else 3 if s["nivel"] < 80 else 2 if s["nivel"] < 84 else 1
            obj = ["KNOCKOUT", "KNOCKOUT", "QUALIFY", "QUALIFY"] if not s["genero"] else ["QUARTER", "QUARTER", "N/A", "N/A"]
        linhas.append({"tier": tier, "nationid": s["nacao"], "teamid": s["teamid"], "confederacao": s.get("confederacao") or 0,
                       "objetivos": obj, "genero": s["genero"]})
    if intl is not None:
        arq = os.path.join(destino, "internationals.txt")
        entraram = intl.gravar(arq, linhas)
        return {"arquivo": arq, "linhas": entraram}
    arq = os.path.join(destino, "internationals_linhas_novas.txt")
    with open(arq, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("[TIER_AND_OBJECTIVES]\n")
        for n in linhas:
            f.write(",".join([str(n["tier"]), str(n["nationid"]), str(n["teamid"]), str(n["confederacao"]), *n["objetivos"],
                              "FEMALE" if n["genero"] else "MALE"]) + "\n")
    avisos.append("Nenhum internationals.txt importado em Dados do jogo: as linhas das seleções novas foram para "
                  "internationals_linhas_novas.txt (copie para a seção [TIER_AND_OBJECTIVES] do seu arquivo).")
    return {"arquivo": arq, "linhas": linhas}


def _atualizar_mapa(mapa):
    try:
        with open(MAPA, encoding="utf-8") as f:
            atual = json.load(f)
    except (OSError, ValueError):
        atual = {}
    for k in ("times", "jogadores", "ligas", "tm_times", "tm_jogadores"):
        atual.setdefault(k, {}).update(mapa.get(k, {}))
    os.makedirs(os.path.dirname(MAPA), exist_ok=True)
    with open(MAPA + ".tmp", "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False)
    os.replace(MAPA + ".tmp", MAPA)


def _relatorio(projeto, destino, feitos, avisos):
    import notas as N
    L = ["BRFP Super Tool — Criador de Ligas e Times", time.strftime("%d/%m/%Y %H:%M"), ""]
    if feitos.get("db"):
        L.append(f"Banco novo: {feitos['db']}")
    def mudancas(v):
        partes = [f"+{v['novas']}" if v["novas"] else "", f"~{v['alteradas']}" if v["alteradas"] else "",
                  f"-{v['removidas']}" if v["removidas"] else ""]
        return " ".join(p for p in partes if p) or "0"
    L.append("Tabelas alteradas (+ novas, ~ alteradas, - removidas): " + ", ".join(f"{k} ({mudancas(v)})" for k, v in feitos["tabelas"].items()))
    L.append(f"Textos de idioma novos: {feitos['idioma']}")
    for lid, nome in getattr(projeto, "ligas_nomes", {}).items():
        L.append(f"Liga nova: {nome} (leagueid {lid})")
    L.append("")
    for t in projeto.resumo:
        tec = t.get("tecnico") or {}
        est = t.get("estadio") or {}
        tipo = ("seleção atualizada" if t.get("atualiza") else "seleção nova") if t.get("selecao") else "time"
        L.append(f"{t['nome']} ({tipo}) — teamid {t['teamid']} (API {t['api_id']}) · nível {t['nivel']} · geral {t['geral']} · "
                 f"{t['formacao']} · linha {t['tatica']['profundidade']} · saída {t['tatica']['saida']} · modelo {t['modelo']} · "
                 f"técnico {tec.get('nome') or '—'}")
        if est.get("generico"):
            L.append(f"   estádio: {est.get('nome') or '—'} -> genérico {est['generico']} ({est.get('generico_capacidade')} lugares)")
        for j in t["jogadores"]:
            orig = f"{j['origem']}, " if j.get("origem") else ""
            L.append(f"   {j['camisa']:>2}  {N.NOME_POS.get(j['pos'], j['pos']):4s} {j['overall']:>2}/{j['potential'] or '':<2} "
                     f"{(j['nome'] or '')[:30]:30s} {j['idade'] or '':>2} anos  {j['nacionalidade'] or '':15s} playerid {j['playerid']}"
                     f"  ({orig}API {j['api_id']}, {j['minutos']} min, nota {j['nota_api'] or '—'}, posição: {j['pos_origem']})")
        for a in t.get("avisos") or []:
            L.append(f"   ! {a}")
        L.append("")
    if avisos:
        L += ["Avisos:"] + [f"- {a}" for a in avisos]
    it = feitos.get("internationals")
    if it:
        L += ["", f"internationals: {len(it['linhas'])} seleção(ões) nova(s) em {it['arquivo']}"]
    L += ["", "Como usar:",
          "1. Banco: importe db\\fifa_ng_db.db no FET (ou as tabelas .txt pelo RDBM/DB Master).",
          "2. Idioma: importe idioma\\LanguageStrings1.txt e LanguageStrings2.txt no FET (nomes dos times e ligas).",
          "3. Escudos: imagens\\escudos\\<teamid>.png; fotos: imagens\\jogadores\\<playerid>.png (Criador de Minifaces).",
          "4. Liga nova: para o modo carreira ela também precisa entrar no compdata (Editor de Compdata)."]
    with open(os.path.join(destino, "relatorio.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
