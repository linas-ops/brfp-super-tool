"""Editor de Banco — camada de edição sobre o banco importado em Dados do jogo (qualquer versão, FIFA 16 … FC 27).

As mudanças ficam numa camada (linhas alteradas, novas e removidas por tabela + textos do idioma), gravada sozinha em
cache/edicao_<assinatura do banco>.json a cada operação e com desfazer. O banco original nunca é alterado: "Gravar"
escreve um banco novo (cópia do importado + as mudanças) numa pasta escolhida, com as tabelas mexidas em .txt e o idioma.

Operações: transferir, emprestar, encerrar empréstimo, liberar (Sem Contrato), trocar número, escalação (titulares,
banco, formação, capitão e cobradores, escalar sozinho), mover time de liga, criar e excluir jogador, editar qualquer
campo de qualquer tabela. Verificação: vínculos quebrados (jogador ou time que não existe), jogador em dois clubes,
números repetidos, escalação/cobradores fora do elenco, empréstimos inválidos, valores fora da faixa do meta…, cada
problema com a correção sugerida.
"""
import collections
import datetime
import json
import os
import re
import threading
import time

import dados

BASE_DATA = datetime.date(1582, 10, 14)
SEM_CONTRATO = "111592"
LIGAS_SELECOES = {"78", "2136"}
LIGAS_NAO_CLUBE = {"78", "2136", "2255", "382", "383"}
RDM = {"0": "76", "1": "2226"}
POS = {0: "GOL", 1: "LIB", 2: "ALD", 3: "LD", 4: "ZAGD", 5: "ZAG", 6: "ZAGE", 7: "LE", 8: "ALE", 9: "VOLD", 10: "VOL",
       11: "VOLE", 12: "MD", 13: "MCD", 14: "MC", 15: "MCE", 16: "ME", 17: "MEID", 18: "MEI", 19: "MEIE", 20: "SAD",
       21: "SA", 22: "SAE", 23: "PD", 24: "ATAD", 25: "ATA", 26: "ATAE", 27: "PE", 28: "RES", 29: "FORA"}
BASE_POS = {1: 5, 4: 5, 6: 5, 9: 10, 11: 10, 13: 14, 15: 14, 17: 18, 19: 18, 20: 21, 22: 21, 24: 25, 26: 25}
COORD = {0: (0, 0), 3: (1, 1), 5: (0, 1), 7: (-1, 1), 2: (1, 1.6), 8: (-1, 1.6), 10: (0, 2), 12: (1, 3), 14: (0, 3),
         16: (-1, 3), 18: (0, 4), 23: (1, 4.4), 27: (-1, 4.4), 21: (0, 4.6), 25: (0, 5)}
COBRADORES = ("captainid", "penaltytakerid", "freekicktakerid", "leftfreekicktakerid", "rightfreekicktakerid",
              "leftcornerkicktakerid", "rightcornerkicktakerid", "longkicktakerid")
MAX_ELENCO = 52


def dias(iso):
    try:
        return (datetime.date.fromisoformat(str(iso)[:10]) - BASE_DATA).days
    except (TypeError, ValueError):
        return None


def data_de(n):
    try:
        return (BASE_DATA + datetime.timedelta(days=int(n))).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


class ErroEdicao(Exception):
    pass


def _ref(r):
    """'o12' (linha 12 do banco original) ou 'n3' (3ª linha nova) -> ('o', 12)."""
    if isinstance(r, tuple):
        return r
    r = str(r)
    return (r[0], int(r[1:]))


def _rs(r):
    return f"{r[0]}{r[1]}"


class Edicao:
    def __init__(self, banco, pasta_cache):
        self.b = banco
        self.arq = os.path.join(pasta_cache, f"edicao_{banco.sig}.json")
        self.lock = threading.RLock()
        self.alt = collections.defaultdict(dict)       # tabela -> {i: {campo: valor}}
        self.rem = collections.defaultdict(set)        # tabela -> {i}
        self.novas = collections.defaultdict(list)     # tabela -> [dict | None (removida)]
        self.idioma = {}                               # chave -> texto
        self.historico = []                            # [{rotulo, mudancas: [(tab, ref, antes|None, existia)]}]
        self._indices = {}
        self._op = None
        self.carregar()

    # ------------------------------------------------------------------ persistência
    def carregar(self):
        try:
            with open(self.arq, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        for t, m in (d.get("alt") or {}).items():
            self.alt[t] = {int(i): v for i, v in m.items()}
        for t, l in (d.get("rem") or {}).items():
            self.rem[t] = set(int(i) for i in l)
        for t, l in (d.get("novas") or {}).items():
            self.novas[t] = l
        self.idioma = d.get("idioma") or {}

    def gravar_json(self):
        os.makedirs(os.path.dirname(self.arq), exist_ok=True)
        d = {"sig": self.b.sig, "banco": self.b.reg.get("caminho"), "quando": time.strftime("%d/%m/%Y %H:%M"),
             "alt": {t: {str(i): v for i, v in m.items()} for t, m in self.alt.items() if m},
             "rem": {t: sorted(s) for t, s in self.rem.items() if s},
             "novas": {t: l for t, l in self.novas.items() if any(x is not None for x in l)}, "idioma": self.idioma}
        with open(self.arq + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(self.arq + ".tmp", self.arq)

    # ------------------------------------------------------------------ leitura
    def tem(self, t):
        return self.b.tem(t)

    def tab(self, t):
        return self.b.tabela(t)

    def campos(self, t):
        return self.tab(t).campos

    def info(self, t):
        return self.tab(t).info

    def linha(self, t, ref):
        ref = _ref(ref)
        if ref[0] == "o":
            tb = self.tab(t)
            d = dict(zip(tb.campos, tb.linhas[ref[1]]))
            d.update(self.alt.get(t, {}).get(ref[1]) or {})
            return d
        d = self.novas[t][ref[1]]
        if d is None:
            raise ErroEdicao("Linha removida.")
        return dict(d)

    def refs(self, t):
        rem = self.rem.get(t, set())
        out = [("o", i) for i in range(len(self.tab(t).linhas)) if i not in rem]
        out += [("n", i) for i, d in enumerate(self.novas.get(t, [])) if d is not None]
        return out

    def indice(self, t, campo):
        k = (t, campo)
        if k not in self._indices:
            idx = collections.defaultdict(list)
            tb = self.tab(t)
            i = tb.col(campo)
            alt = self.alt.get(t, {})
            rem = self.rem.get(t, set())
            if i is not None:
                for n, l in enumerate(tb.linhas):
                    if n in rem:
                        continue
                    v = (alt.get(n) or {}).get(campo, l[i])
                    idx[str(v)].append(("o", n))
            for n, d in enumerate(self.novas.get(t, [])):
                if d is not None:
                    idx[str(d.get(campo, ""))].append(("n", n))
            self._indices[k] = idx
        return self._indices[k]

    def onde(self, t, **filtro):
        if not self.tem(t):
            return []
        if not filtro:
            return self.refs(t)
        (c0, v0), *resto = list(filtro.items())
        out = []
        for r in self.indice(t, c0).get(str(v0), []):
            if resto:
                d = self.linha(t, r)
                if not all(str(d.get(c)) == str(v) for c, v in resto):
                    continue
            out.append(r)
        return out

    def dicts(self, t, **filtro):
        return [(r, self.linha(t, r)) for r in self.onde(t, **filtro)]

    def um(self, t, **filtro):
        rs = self.onde(t, **filtro)
        return (rs[0], self.linha(t, rs[0])) if rs else (None, None)

    # ------------------------------------------------------------------ escrita (com desfazer)
    def operacao(self, rotulo):
        ed = self

        class Op:
            def __enter__(self_):
                ed.lock.acquire()
                if ed._op is None:
                    ed._op = {"rotulo": rotulo, "mudancas": [], "idioma": {}}
                    self_.raiz = True
                else:
                    self_.raiz = False
                return ed

            def __exit__(self_, tipo, valor, tb):
                try:
                    if self_.raiz:
                        op, ed._op = ed._op, None
                        if tipo is not None:              # deu erro: desfaz o que a operação já tinha mudado
                            ed._desfazer_op(op)
                        elif op["mudancas"] or op["idioma"]:
                            ed.historico.append(op)
                            del ed.historico[:-200]
                            ed.gravar_json()
                finally:
                    ed.lock.release()
                return False
        return Op()

    def _guardar(self, t, ref):
        """Estado da linha antes da primeira mudança dela nesta operação (para desfazer)."""
        if self._op is None:
            raise ErroEdicao("Mudança fora de uma operação.")
        if any(m[0] == t and m[1] == ref for m in self._op["mudancas"]):
            return
        if ref[0] == "o":
            antes = (dict(self.alt.get(t, {}).get(ref[1]) or {}), ref[1] in self.rem.get(t, set()))
        else:
            antes = (None if self.novas[t][ref[1]] is None else dict(self.novas[t][ref[1]]), None)
        self._op["mudancas"].append((t, ref, antes))

    def _sujar(self, t):
        for k in [k for k in self._indices if k[0] == t]:
            del self._indices[k]

    def alterar(self, t, ref, valores):
        ref = _ref(ref)
        self._guardar(t, ref)
        info = self.info(t)
        limpo = {}
        for c, v in valores.items():
            if c not in info and c not in self.campos(t):
                continue
            limpo[c] = "" if v is None else str(v)
        if ref[0] == "o":
            orig = dict(zip(self.campos(t), self.tab(t).linhas[ref[1]]))
            m = self.alt[t].setdefault(ref[1], {})
            for c, v in limpo.items():
                if orig.get(c) == v:
                    m.pop(c, None)
                else:
                    m[c] = v
            if not m:
                self.alt[t].pop(ref[1], None)
        else:
            self.novas[t][ref[1]].update(limpo)
        self._sujar(t)

    def inserir(self, t, valores, modelo=None):
        """Linha nova: os valores dados + os da linha modelo (ou zeros/vazios pelo meta)."""
        base = dict(modelo) if modelo else {c: ("" if "string" in (self.info(t).get(c, {}).get("tipo") or "").lower() else
                                               str(max(0, self.info(t).get(c, {}).get("low", 0)))) for c in self.campos(t)}
        base.update({c: str(v) for c, v in valores.items()})
        self.novas[t].append(base)
        ref = ("n", len(self.novas[t]) - 1)
        if self._op is None:
            raise ErroEdicao("Mudança fora de uma operação.")
        self._op["mudancas"].append((t, ref, ("nova", None)))
        self._sujar(t)
        return ref

    def remover(self, t, ref):
        ref = _ref(ref)
        self._guardar(t, ref)
        if ref[0] == "o":
            self.rem[t].add(ref[1])
        else:
            self.novas[t][ref[1]] = None
        self._sujar(t)

    def texto(self, chave, valor):
        if self._op is not None and chave not in self._op["idioma"]:
            self._op["idioma"][chave] = self.idioma.get(chave)
        if valor in (None, ""):
            self.idioma.pop(chave, None)
        else:
            self.idioma[chave] = valor

    def _desfazer_op(self, op):
        for t, ref, antes in reversed(op["mudancas"]):
            if antes[0] == "nova":
                self.novas[t][ref[1]] = None
            elif ref[0] == "o":
                alt, removida = antes
                if alt:
                    self.alt[t][ref[1]] = alt
                else:
                    self.alt[t].pop(ref[1], None)
                if removida:
                    self.rem[t].add(ref[1])
                else:
                    self.rem[t].discard(ref[1])
            else:
                self.novas[t][ref[1]] = antes[0]
            self._sujar(t)
        for k, v in op["idioma"].items():
            if v is None:
                self.idioma.pop(k, None)
            else:
                self.idioma[k] = v

    def desfazer(self):
        with self.lock:
            if not self.historico:
                raise ErroEdicao("Nada para desfazer.")
            op = self.historico.pop()
            self._desfazer_op(op)
            self.gravar_json()
            return op["rotulo"]

    def descartar_tudo(self):
        with self.lock:
            self.alt.clear()
            self.rem.clear()
            self.novas.clear()
            self.idioma.clear()
            self.historico.clear()
            self._indices.clear()
            self.gravar_json()

    def resumo(self):
        out = {}
        for t in set(self.alt) | set(self.rem) | set(self.novas):
            a, r, n = len(self.alt.get(t) or {}), len(self.rem.get(t) or ()), sum(1 for x in self.novas.get(t, []) if x is not None)
            if a or r or n:
                out[t] = {"alteradas": a, "removidas": r, "novas": n}
        return out

    def tabelas_mexidas(self):
        return sorted(self.resumo())

    def proximo_id(self, t, campo, inicio=1):
        inf = self.info(t).get(campo, {})
        hi = inf.get("high") or 2 ** 31
        usados = {int(v) for v in self.indice(t, campo) if str(v).lstrip("-").isdigit()}
        n = max([inicio - 1] + [u for u in usados if u < hi]) + 1
        while n in usados:
            n += 1
        if n > hi:
            n = next((x for x in range(max(1, inicio), hi + 1) if x not in usados), None)
            if n is None:
                raise ErroEdicao(f"Sem {campo} livre em {t}.")
        return n

    # ------------------------------------------------------------------ nomes
    def _nomes_tabela(self):
        if not hasattr(self, "_nt"):
            nomes = {}
            for tn in ("playernames", "dcplayernames"):
                if self.tem(tn):
                    tb = self.tab(tn)
                    i, j = tb.col("nameid"), tb.col("name")
                    if i is not None and j is not None:
                        for l in tb.linhas:
                            nomes[l[i]] = l[j]
            self._nt = nomes
        return self._nt

    def nome_jogador(self, pid, d=None):
        """{primeiro, sobrenome, comum, camisa, nome} com as edições (editedplayernames) aplicadas."""
        d = d or (self.um("players", playerid=pid)[1] or {})
        _, e = self.um("editedplayernames", playerid=pid) if self.tem("editedplayernames") else (None, None)
        if e:
            prim, sob, com, cam = e.get("firstname", ""), e.get("surname", ""), e.get("commonname", ""), e.get("playerjerseyname", "")
        else:
            n = self._nomes_tabela()
            prim, sob, com, cam = (n.get(d.get(k, ""), "") for k in ("firstnameid", "lastnameid", "commonnameid", "playerjerseynameid"))
        nome = com or " ".join(x for x in (prim, sob) if x).strip() or cam or f"Jogador {pid}"
        return {"primeiro": prim, "sobrenome": sob, "comum": com, "camisa": cam, "nome": nome}

    def nome_time(self, tid, d=None):
        k = f"TeamName_{tid}"
        if k in self.idioma:
            return self.idioma[k]
        idi = dados.idioma_atual()
        n = idi.time(tid) if idi else None
        if n:
            return n
        d = d or (self.um("teams", teamid=tid)[1] or {})
        return d.get("teamname") or f"Time {tid}"

    def nome_liga(self, lid, d=None):
        k = f"LeagueName_{lid}"
        if k in self.idioma:
            return self.idioma[k]
        idi = dados.idioma_atual()
        n = idi.liga(lid) if idi else None
        if n:
            return n
        d = d or (self.um("leagues", leagueid=lid)[1] or {})
        return d.get("leaguename") or f"Liga {lid}"

    def nome_nacao(self, nid):
        idi = dados.idioma_atual()
        n = idi.texto(f"NationName_{nid}") if idi else None
        if n:
            return n
        _, d = self.um("nations", nationid=nid) if self.tem("nations") else (None, None)
        return (d or {}).get("nationname") or (f"nação {nid}" if nid not in (None, "", "0") else "—")

    def times_livres(self):
        """Os times da liga dos livres (a do 111592): NG - FA, NG - FA Women…"""
        liga = self.liga_do_time(SEM_CONTRATO)
        out = [d["teamid"] for _, d in self.dicts("leagueteamlinks", leagueid=liga)] if liga else []
        return out or [SEM_CONTRATO]

    def time_livre_para(self, pid):
        """O time dos livres do mesmo gênero do jogador (o masculino 111592 é o padrão)."""
        _, p = self.um("players", playerid=pid)
        genero = (p or {}).get("gender", "0")
        livres = self.times_livres()
        for t in livres:                                   # pelo gênero do time (teams.gender, quando o banco tem)
            _, td = self.um("teams", teamid=t)
            if td and "gender" in td and td["gender"] == genero:
                return t
        for t in livres:                                   # senão, pelo gênero da maioria do elenco
            gs = [(self.um("players", playerid=d["playerid"])[1] or {}).get("gender", "0") for _, d in self.dicts("teamplayerlinks", teamid=t)[:20]]
            if gs and max(set(gs), key=gs.count) == genero:
                return t
        return SEM_CONTRATO

    def liga_do_time(self, tid):
        _, d = self.um("leagueteamlinks", teamid=tid)
        return d.get("leagueid") if d else None

    # ------------------------------------------------------------------ jogadores e elencos
    def clube_de(self, pid):
        for _, d in self.dicts("teamplayerlinks", playerid=pid):
            if self.liga_do_time(d["teamid"]) not in LIGAS_NAO_CLUBE:
                return d["teamid"]
        return None

    def vinculos(self, pid):
        return [(r, d) for r, d in self.dicts("teamplayerlinks", playerid=pid)]

    def elenco(self, tid):
        out = []
        emp = {d["playerid"]: d for _, d in self.dicts("playerloans")} if self.tem("playerloans") else {}
        for r, l in self.dicts("teamplayerlinks", teamid=tid):
            rp, p = self.um("players", playerid=l["playerid"])
            if not p:
                out.append({"playerid": l["playerid"], "ref_link": _rs(r), "erro": "jogador não existe em players",
                            "numero": l.get("jerseynumber"), "posicao_time": int(l.get("position") or 29)})
                continue
            n = self.nome_jogador(l["playerid"], p)
            e = emp.get(l["playerid"])
            out.append({"playerid": l["playerid"], "ref": _rs(rp), "ref_link": _rs(r), "nome": n["nome"],
                        "numero": l.get("jerseynumber"), "posicao_time": int(l.get("position") or 29),
                        "pos": int(p.get("preferredposition1") or 0), "pos_nome": POS.get(int(p.get("preferredposition1") or 0), "?"),
                        "overall": int(p.get("overallrating") or 0), "potencial": int(p.get("potential") or 0),
                        "nascimento": data_de(p.get("birthdate")), "nacao": p.get("nationality"),
                        "nacao_nome": self.nome_nacao(p.get("nationality")), "contrato": p.get("contractvaliduntil"),
                        "emprestado_de": e.get("teamidloanedfrom") if e and e.get("teamidloanedfrom") != tid else None,
                        "emprestado_de_nome": self.nome_time(e["teamidloanedfrom"]) if e and e.get("teamidloanedfrom") != tid else None,
                        "emprestado_ate": data_de(e.get("loandateend")) if e else None})
        out.sort(key=lambda j: (j.get("posicao_time", 29) >= 28, int(j["numero"]) if str(j.get("numero", "")).isdigit() else 99))
        return out

    def numero_livre(self, tid, pedido=None, pid=None):
        usados = {d.get("jerseynumber") for _, d in self.dicts("teamplayerlinks", teamid=tid) if d.get("playerid") != str(pid)}
        if pedido and str(pedido) not in usados and 1 <= int(pedido) <= 99:
            return int(pedido)
        return next((n for n in range(2, 100) if str(n) not in usados), 99)


# ====================================================================== operações
def transferir(ed, pid, para, numero=None, emprestimo=None, de=None):
    """Leva o jogador do clube atual (ou 'de') para 'para'. emprestimo: {"dono": teamid, "fim": "AAAA-MM-DD"}.
    Refaz a escalação dos dois times."""
    pid, para = str(pid), str(para)
    if not ed.um("teams", teamid=para)[1]:
        raise ErroEdicao(f"O time {para} não existe.")
    if not ed.um("players", playerid=pid)[1]:
        raise ErroEdicao(f"O jogador {pid} não existe.")
    nome = ed.nome_jogador(pid)["nome"]
    with ed.operacao(f"{nome} → {ed.nome_time(para)}" + (" (empréstimo)" if emprestimo else "")):
        origem = str(de) if de else ed.clube_de(pid)
        if not origem:                                     # livre (NG - FA…): sai do time dos livres
            livres = set(ed.times_livres())
            origem = next((d["teamid"] for _, d in ed.vinculos(pid) if d["teamid"] in livres), None)
        if origem == para:
            raise ErroEdicao("O jogador já está nesse time.")
        num = ed.numero_livre(para, numero, pid)
        lnk = ed.onde("teamplayerlinks", playerid=pid, teamid=origem) if origem else []
        if lnk:
            ed.alterar("teamplayerlinks", lnk[0], {"teamid": para, "jerseynumber": num, "position": 29})
        else:
            modelo = ed.linha("teamplayerlinks", ed.refs("teamplayerlinks")[0]) if ed.refs("teamplayerlinks") else None
            v = {c: "0" for c in ed.campos("teamplayerlinks")}
            if modelo:
                v.update({c: modelo[c] for c in ("form",) if c in modelo})
            v.update(teamid=para, playerid=pid, jerseynumber=num, position=29)
            if "artificialkey" in v:
                v["artificialkey"] = ed.proximo_id("teamplayerlinks", "artificialkey")
            ed.inserir("teamplayerlinks", v)
        _mudar_emprestimo(ed, pid, emprestimo, para)
        if "playerjointeamdate" in ed.info("players") and not emprestimo:
            rp, _ = ed.um("players", playerid=pid)
            ed.alterar("players", rp, {"playerjointeamdate": dias(datetime.date.today().isoformat())})
        livres = set(ed.times_livres())
        for t in (origem, para):
            if t and t not in livres:
                reescalar(ed, t, silencioso=True)


def _mudar_emprestimo(ed, pid, emprestimo, para):
    if not ed.tem("playerloans"):
        return
    for r in ed.onde("playerloans", playerid=pid):
        ed.remover("playerloans", r)
    if emprestimo and emprestimo.get("dono") and str(emprestimo["dono"]) != str(para):
        v = {c: "0" for c in ed.campos("playerloans")}
        v.update(playerid=pid, teamidloanedfrom=str(emprestimo["dono"]),
                 loandateend=dias(emprestimo.get("fim")) or dias(f"{datetime.date.today().year + 1}-06-30"))
        ed.inserir("playerloans", v)


def emprestar(ed, pid, para, fim, dono=None):
    dono = str(dono or ed.clube_de(pid) or "")
    if not dono:
        raise ErroEdicao("O jogador não tem clube para emprestá-lo.")
    transferir(ed, pid, para, emprestimo={"dono": dono, "fim": fim}, de=ed.clube_de(pid))


def encerrar_emprestimo(ed, pid):
    _, e = ed.um("playerloans", playerid=pid)
    if not e:
        raise ErroEdicao("O jogador não está emprestado.")
    transferir(ed, pid, e["teamidloanedfrom"], de=ed.clube_de(pid))


def liberar(ed, pid):
    """Sem Contrato (o time dos livres do mesmo gênero: 111592 no masculino), como o jogo faz."""
    if not ed.um("teams", teamid=SEM_CONTRATO)[1]:
        raise ErroEdicao("O banco não tem o time Sem Contrato (111592).")
    transferir(ed, pid, ed.time_livre_para(pid))


def trocar_numero(ed, tid, pid, numero):
    numero = int(numero)
    if not 1 <= numero <= 99:
        raise ErroEdicao("Número de 1 a 99.")
    with ed.operacao(f"{ed.nome_jogador(pid)['nome']}: camisa {numero}"):
        meu = ed.onde("teamplayerlinks", teamid=tid, playerid=pid)
        if not meu:
            raise ErroEdicao("O jogador não está nesse time.")
        antigo = ed.linha("teamplayerlinks", meu[0]).get("jerseynumber")
        for r, d in ed.dicts("teamplayerlinks", teamid=tid, jerseynumber=numero):
            if d["playerid"] != str(pid):                   # quem usava o número fica com o antigo
                ed.alterar("teamplayerlinks", r, {"jerseynumber": antigo})
        ed.alterar("teamplayerlinks", meu[0], {"jerseynumber": numero})


def mover_liga(ed, tid, liga):
    liga = str(liga)
    _, lg = ed.um("leagues", leagueid=liga)
    if not lg:
        raise ErroEdicao(f"A liga {liga} não existe.")
    with ed.operacao(f"{ed.nome_time(tid)} → {ed.nome_liga(liga)}"):
        r, d = ed.um("leagueteamlinks", teamid=tid)
        if not r:
            raise ErroEdicao("O time não está em nenhuma liga.")
        antes = d["leagueid"]
        if antes == liga:
            return
        ed.alterar("leagueteamlinks", r, {"leagueid": liga, "prevleagueid": antes})
        if ed.tem("teamnationlinks"):
            for r2 in ed.onde("teamnationlinks", teamid=tid, leagueid=antes):
                ed.remover("teamnationlinks", r2)
            if liga in RDM.values():                       # Resto do Mundo: a nação do time vai em teamnationlinks
                _, la = ed.um("leagues", leagueid=antes)
                ed.inserir("teamnationlinks", {"leagueid": liga, "teamid": tid, "nationid": (la or {}).get("countryid") or "211"})


# ------------------------------------------------------------------ escalação
def _custo(pos_jog, vaga):
    a, b = BASE_POS.get(pos_jog, pos_jog), BASE_POS.get(vaga, vaga)
    if a == b:
        return 0.0
    if 0 in (a, b):
        return 50.0
    (x1, y1), (x2, y2) = COORD.get(a, (0, 3)), COORD.get(b, (0, 3))
    return abs(x1 - x2) * 1.2 + abs(y1 - y2)


def _jogadores_do_time(ed, tid):
    out = []
    for r, l in ed.dicts("teamplayerlinks", teamid=tid):
        _, p = ed.um("players", playerid=l["playerid"])
        if not p:
            continue
        pos2 = [int(p.get(f"preferredposition{i}") or -1) for i in range(2, 5) if str(p.get(f"preferredposition{i}", "-1")) not in ("-1", "")]
        out.append({"pid": l["playerid"], "ref": r, "overall": int(p.get("overallrating") or 0), "pos": int(p.get("preferredposition1") or 0),
                    "pos2": pos2, "p": p, "posicao": int(l.get("position") or 29)})
    return out


def _vagas(ed, tid):
    _, fo = ed.um("formations", teamid=tid)
    if not fo:
        raise ErroEdicao("O time não tem formação (formations).")
    return [int(fo[f"position{i}"]) for i in range(11)], fo


def _gravar_escalacao(ed, tid, titulares, banco, vagas, cobradores):
    """titulares: 11 pids na ordem das vagas; banco: o resto na ordem (os 7–12 primeiros vão para o banco)."""
    pos_de = {pid: vagas[i] for i, pid in enumerate(titulares)}
    n_banco = 12 if len(titulares) + len(banco) >= 23 else 9
    for i, pid in enumerate(banco):
        pos_de[pid] = 28 if i < n_banco else 29
    for r, l in ed.dicts("teamplayerlinks", teamid=tid):
        p = pos_de.get(l["playerid"])
        if p is not None and str(p) != l.get("position"):
            ed.alterar("teamplayerlinks", r, {"position": p})
    ordem = list(titulares) + list(banco)
    rs, ts = ed.um("default_teamsheets", teamid=tid) if ed.tem("default_teamsheets") else (None, None)
    if rs:
        v = {}
        for k in ts:
            if k.startswith("playerid") and k[8:].isdigit():
                n = int(k[8:])
                v[k] = ordem[n] if n < len(ordem) else -1
        for k, pid in cobradores.items():
            if k in ts:
                v[k] = pid
        ed.alterar("default_teamsheets", rs, v)
    rm, _ = ed.um("default_mentalities", teamid=tid) if ed.tem("default_mentalities") else (None, None)
    if rm:
        ed.alterar("default_mentalities", rm, {f"playerid{i}": titulares[i] for i in range(11)})
    rt, t = ed.um("teams", teamid=tid)
    if rt:
        ed.alterar("teams", rt, {k: v for k, v in cobradores.items() if k in t})


def _cobradores_auto(tit, atual=None):
    a = lambda j, k: int(j["p"].get(k) or 0)  # noqa: E731
    pids = {j["pid"] for j in tit}
    atual = {k: v for k, v in (atual or {}).items() if v in pids}
    cap = atual.get("captainid") or max(tit, key=lambda j: (j["overall"], -abs(int(j["p"].get("birthdate") or 0))))["pid"]
    pen = max(tit, key=lambda j: a(j, "penalties") + a(j, "finishing"))["pid"]
    fk = max(tit, key=lambda j: a(j, "freekickaccuracy") + a(j, "curve"))["pid"]
    esc = max(tit, key=lambda j: a(j, "crossing") + a(j, "curve"))["pid"]
    gk = next((j["pid"] for j in tit if j["pos"] == 0), tit[0]["pid"])
    out = {"captainid": cap, "penaltytakerid": pen, "freekicktakerid": fk, "leftfreekicktakerid": fk, "rightfreekicktakerid": fk,
           "leftcornerkicktakerid": esc, "rightcornerkicktakerid": esc, "longkicktakerid": gk}
    out.update({k: v for k, v in atual.items() if k in out})
    return out


def escalacao(ed, tid):
    """Formação, titulares por vaga, banco e cobradores do time."""
    vagas, fo = _vagas(ed, tid)
    js = {j["pid"]: j for j in _jogadores_do_time(ed, tid)}
    _, ts = ed.um("default_teamsheets", teamid=tid) if ed.tem("default_teamsheets") else (None, None)
    _, dm = ed.um("default_mentalities", teamid=tid) if ed.tem("default_mentalities") else (None, None)
    if ts:
        ordem = [ts.get(f"playerid{i}") for i in range(MAX_ELENCO) if ts.get(f"playerid{i}") not in (None, "", "-1")]
    else:
        ordem = sorted(js, key=lambda p: (js[p]["posicao"] >= 28, js[p]["posicao"]))
    tit = (ordem + [None] * 11)[:11]
    if dm:
        tit = [dm.get(f"playerid{i}") if dm.get(f"playerid{i}") not in (None, "", "-1") else tit[i] for i in range(11)]
    banco = [p for p in ordem if p not in tit] + [p for p in js if p not in ordem and p not in tit]
    cob = {k: (ts or {}).get(k) or "" for k in COBRADORES}
    _, t = ed.um("teams", teamid=tid)
    for k in COBRADORES:
        if not cob[k] or cob[k] == "-1":
            cob[k] = (t or {}).get(k, "")

    def pub(pid):
        j = js.get(str(pid))
        if not j:
            return {"playerid": pid, "nome": f"(fora do elenco: {pid})", "fora": True}
        return {"playerid": pid, "nome": ed.nome_jogador(pid, j["p"])["nome"], "overall": j["overall"], "pos": j["pos"],
                "pos_nome": POS.get(j["pos"], "?"), "pos2": j["pos2"]}
    return {"formacao": fo.get("formationname"), "vagas": [{"pos": v, "nome": POS.get(v, "?"), "base": BASE_POS.get(v, v),
            "x": fo.get(f"offset{i}x"), "y": fo.get(f"offset{i}y")} for i, v in enumerate(vagas)],
            "titulares": [pub(p) if p else None for p in tit], "banco": [pub(p) for p in banco],
            "cobradores": cob, "taticas": {k: (dm or t or {}).get(k) for k in ("buildupplay", "defensivedepth") if k in (dm or t or {})}}


def reescalar(ed, tid, silencioso=False):
    """Escala sozinho: os 11 melhores para as vagas da formação (nota menos a distância da posição), o resto pela
    nota; capitão mantido se continuar titular, cobradores pelos atributos."""
    js = _jogadores_do_time(ed, tid)
    if len(js) < 11:
        if silencioso:
            return
        raise ErroEdicao(f"{ed.nome_time(tid)} tem {len(js)} jogador(es): precisa de 11 para escalar.")
    try:
        vagas, _ = _vagas(ed, tid)
    except ErroEdicao:
        if silencioso:
            return
        raise
    with ed.operacao(f"Escalação automática: {ed.nome_time(tid)}"):
        livres = list(js)
        escolha = [None] * 11
        ordem = sorted(range(11), key=lambda i: (0 if vagas[i] == 0 else 1, sum(1 for j in js if BASE_POS.get(j["pos"], j["pos"]) == BASE_POS.get(vagas[i], vagas[i]))))
        for i in ordem:
            melhor = max(livres, key=lambda j: j["overall"] - 4.0 * min(_custo(j["pos"], vagas[i]),
                         min([_custo(p, vagas[i]) + 0.5 for p in j["pos2"]] or [99])))
            escolha[i] = melhor
            livres.remove(melhor)
        banco = sorted(livres, key=lambda j: -j["overall"])
        _, ts = ed.um("default_teamsheets", teamid=tid) if ed.tem("default_teamsheets") else (None, None)
        cob = _cobradores_auto(escolha, {k: (ts or {}).get(k) for k in COBRADORES})
        _gravar_escalacao(ed, tid, [j["pid"] for j in escolha], [j["pid"] for j in banco], vagas, cob)


def definir_escalacao(ed, tid, titulares, banco=None, cobradores=None):
    """Escalação escolhida à mão: 11 pids (ordem das vagas), o banco na ordem e os cobradores."""
    titulares = [str(x) for x in titulares]
    if len(titulares) != 11 or len(set(titulares)) != 11:
        raise ErroEdicao("A escalação precisa de 11 jogadores diferentes.")
    js = {j["pid"]: j for j in _jogadores_do_time(ed, tid)}
    fora = [p for p in titulares if p not in js]
    if fora:
        raise ErroEdicao(f"Jogador(es) fora do elenco: {', '.join(fora)}.")
    vagas, _ = _vagas(ed, tid)
    banco = [str(x) for x in (banco or []) if str(x) in js and str(x) not in titulares]
    banco += [p for p in js if p not in titulares and p not in banco]
    with ed.operacao(f"Escalação: {ed.nome_time(tid)}"):
        atual = escalacao(ed, tid)["cobradores"]
        cob = {k: str(v) for k, v in {**atual, **(cobradores or {})}.items() if v not in (None, "")}
        tit_j = [js[p] for p in titulares]
        for k, v in list(cob.items()):
            if v not in js:                                 # cobrador que saiu: o automático
                cob[k] = _cobradores_auto(tit_j)[k]
        _gravar_escalacao(ed, tid, titulares, banco, vagas, cob)


def formacoes(ed):
    """Formações do banco (uma de cada nome) para escolher."""
    vistos, out = set(), []
    for r, d in ed.dicts("formations"):
        n = d.get("formationname")
        if n and n not in vistos and n != "-NONE-":
            vistos.add(n)
            out.append({"nome": n, "ref": _rs(r), "vagas": [POS.get(int(d[f"position{i}"]), "?") for i in range(11)]})
    return sorted(out, key=lambda x: x["nome"])


def trocar_formacao(ed, tid, ref_modelo):
    mod = ed.linha("formations", ref_modelo)
    copiar = [c for c in ed.campos("formations") if re.match(r"^(position\d+|offset\d+[xy]|pos\d+role)$", c)
              or c in ("formationname", "formationfullnameid", "formationaudioid", "defenders", "midfielders", "attackers", "offensiverating")]
    with ed.operacao(f"Formação {mod.get('formationname')}: {ed.nome_time(tid)}"):
        r, _ = ed.um("formations", teamid=tid)
        if not r:
            raise ErroEdicao("O time não tem formação.")
        ed.alterar("formations", r, {c: mod[c] for c in copiar if c in mod})
        rm, dm = ed.um("default_mentalities", teamid=tid) if ed.tem("default_mentalities") else (None, None)
        if rm:
            ed.alterar("default_mentalities", rm, {c: mod[c] for c in copiar if c in dm and c in mod})
        reescalar(ed, tid, silencioso=True)


def definir_tatica(ed, tid, valores):
    with ed.operacao(f"Tática: {ed.nome_time(tid)}"):
        for t in ("default_mentalities", "teams"):
            if ed.tem(t):
                r, d = ed.um(t, teamid=tid)
                if r:
                    ed.alterar(t, r, {k: v for k, v in valores.items() if k in d})


# ------------------------------------------------------------------ criar / excluir
def criar_jogador(ed, tid, nome="Jogador Novo"):
    """Jogador novo no time: cópia do de nota mais baixa do elenco (aparência e atributos), com ID e nome novos."""
    js = _jogadores_do_time(ed, tid)
    if not js:
        raise ErroEdicao("O time não tem jogadores para servir de modelo.")
    modelo = min(js, key=lambda j: j["overall"])["p"]
    with ed.operacao(f"Jogador novo em {ed.nome_time(tid)}"):
        pid = ed.proximo_id("players", "playerid", 460000)
        v = dict(modelo)
        v.update(playerid=pid)
        for k in ("firstnameid", "lastnameid", "commonnameid", "playerjerseynameid"):
            if k in v:
                v[k] = 0
        if "headassetid" in v:
            v["headassetid"] = pid
        if "hashighqualityhead" in v:
            v["hashighqualityhead"] = 0
        ed.inserir("players", v)
        if ed.tem("editedplayernames"):
            partes = nome.split(" ", 1)
            ed.inserir("editedplayernames", {"playerid": pid, "firstname": partes[0], "surname": partes[1] if len(partes) > 1 else "",
                                             "commonname": "", "playerjerseyname": partes[-1]})
        transferir(ed, pid, tid)
    return pid


def excluir_jogador(ed, pid):
    """Tira o jogador do banco: players, vínculos, empréstimo, nomes editados e escalações."""
    nome = ed.nome_jogador(pid)["nome"]
    with ed.operacao(f"Excluir {nome}"):
        times = [d["teamid"] for _, d in ed.vinculos(pid)]
        for t in ("teamplayerlinks", "playerloans", "editedplayernames"):
            if ed.tem(t):
                for r in ed.onde(t, playerid=pid):
                    ed.remover(t, r)
        r, _ = ed.um("players", playerid=pid)
        if r:
            ed.remover("players", r)
        for t in times:
            if t != SEM_CONTRATO:
                reescalar(ed, t, silencioso=True)


def editar_nomes(ed, pid, primeiro, sobrenome, comum, camisa):
    if not ed.tem("editedplayernames"):
        raise ErroEdicao("Este banco não tem editedplayernames.")
    with ed.operacao(f"Nomes de {ed.nome_jogador(pid)['nome']}"):
        v = {"firstname": primeiro or "", "surname": sobrenome or "", "commonname": comum or "", "playerjerseyname": camisa or ""}
        r, _ = ed.um("editedplayernames", playerid=pid)
        if r:
            ed.alterar("editedplayernames", r, v)
        else:
            ed.inserir("editedplayernames", {"playerid": pid, **v})


def renomear_time(ed, tid, nome, abrev15=None, abrev10=None, sigla=None):
    with ed.operacao(f"Nome do time {tid}: {nome}"):
        r, _ = ed.um("teams", teamid=tid)
        ed.alterar("teams", r, {"teamname": (nome or "")[:59]})
        ed.texto(f"TeamName_{tid}", nome)
        for k, v, lim in (("TeamName_Abbr15_", abrev15, 15), ("TeamName_Abbr10_", abrev10, 10), ("TeamName_Abbr3_", sigla, 3)):
            if v is not None:
                ed.texto(f"{k}{tid}", v[:lim])


def renomear_liga(ed, lid, nome, abrev15=None):
    with ed.operacao(f"Nome da liga {lid}: {nome}"):
        r, _ = ed.um("leagues", leagueid=lid)
        ed.alterar("leagues", r, {"leaguename": (nome or "")[:119]})
        ed.texto(f"LeagueName_{lid}", nome)
        if abrev15 is not None:
            ed.texto(f"LeagueName_Abbr15_{lid}", abrev15[:15])


# ====================================================================== verificação
def verificar(ed):
    """[{id, gravidade (erro|aviso|info), tipo, descricao, alvo: {tipo, id}, correcao: {acao, args, rotulo} | None}]"""
    P = []

    def add(grav, tipo, desc, alvo=None, corr=None):
        P.append({"id": f"{tipo}:{len(P)}", "gravidade": grav, "tipo": tipo, "descricao": desc, "alvo": alvo, "correcao": corr})
    jogadores = {d["playerid"] for _, d in ed.dicts("players")}
    times = {d["teamid"]: d for _, d in ed.dicts("teams")}
    ligas = {d["leagueid"] for _, d in ed.dicts("leagues")}
    liga_de = {}
    for r, d in ed.dicts("leagueteamlinks"):
        if d["teamid"] not in times:
            add("erro", "ltl_time", f"leagueteamlinks: o time {d['teamid']} não existe (liga {d['leagueid']}).", None,
                {"acao": "remover", "args": {"tabela": "leagueteamlinks", "ref": _rs(r)}, "rotulo": "Tirar o vínculo"})
        elif d["leagueid"] not in ligas:
            add("erro", "ltl_liga", f"{ed.nome_time(d['teamid'])}: a liga {d['leagueid']} não existe.", {"tipo": "time", "id": d["teamid"]},
                {"acao": "remover", "args": {"tabela": "leagueteamlinks", "ref": _rs(r)}, "rotulo": "Tirar o vínculo"})
        else:
            liga_de.setdefault(d["teamid"], d["leagueid"])
    for t in times:
        if t not in liga_de and t not in ed.times_livres():
            add("aviso", "time_sem_liga", f"{ed.nome_time(t)} não está em nenhuma liga.", {"tipo": "time", "id": t})
    clubes = collections.defaultdict(list)
    por_time = collections.defaultdict(list)
    vistos = collections.Counter()
    for r, d in ed.dicts("teamplayerlinks"):
        pid, tid = d["playerid"], d["teamid"]
        if pid not in jogadores:
            add("erro", "tpl_jogador", f"teamplayerlinks: o jogador {pid} (no {ed.nome_time(tid)}) não existe em players.", {"tipo": "time", "id": tid},
                {"acao": "remover", "args": {"tabela": "teamplayerlinks", "ref": _rs(r)}, "rotulo": "Tirar o vínculo"})
            continue
        if tid not in times:
            add("erro", "tpl_time", f"teamplayerlinks: o time {tid} (de {ed.nome_jogador(pid)['nome']}) não existe.", {"tipo": "jogador", "id": pid},
                {"acao": "remover", "args": {"tabela": "teamplayerlinks", "ref": _rs(r)}, "rotulo": "Tirar o vínculo"})
            continue
        vistos[(tid, pid)] += 1
        if vistos[(tid, pid)] > 1:
            add("erro", "tpl_dup", f"{ed.nome_jogador(pid)['nome']} aparece duas vezes no elenco do {ed.nome_time(tid)}.", {"tipo": "time", "id": tid},
                {"acao": "remover", "args": {"tabela": "teamplayerlinks", "ref": _rs(r)}, "rotulo": "Tirar a cópia"})
            continue
        por_time[tid].append((r, d))
        if liga_de.get(tid) not in LIGAS_NAO_CLUBE:
            clubes[pid].append(tid)
    # times especiais (seleções de estrelas, como o MLS All Stars): quase todo o elenco também está em outro clube
    especiais = set()
    for tid, links in por_time.items():
        if len(links) >= 11 and liga_de.get(tid) not in LIGAS_NAO_CLUBE:
            outros = sum(1 for _, d in links if len(clubes.get(d["playerid"], [])) > 1)
            if outros / len(links) >= 0.8:
                especiais.add(tid)
    for tid in especiais:
        add("info", "especial", f"{ed.nome_time(tid)}: time especial (quase todos os jogadores também estão em outros clubes, como "
            "as seleções de estrelas da EA) — fica fora da conferência de jogador em dois clubes.", {"tipo": "time", "id": tid})
    for pid in list(clubes):
        clubes[pid] = [t for t in clubes[pid] if t not in especiais]
    for pid, ts in clubes.items():
        if len(ts) > 1:
            add("erro", "dois_clubes", f"{ed.nome_jogador(pid)['nome']} está em {len(ts)} clubes: {', '.join(ed.nome_time(t) for t in ts)}.",
                {"tipo": "jogador", "id": pid})
    com_time = {d["playerid"] for _, d in ed.dicts("teamplayerlinks")}
    sem = [p for p in jogadores if p not in com_time]
    if sem:
        add("aviso", "sem_time", f"{len(sem)} jogador(es) não estão em nenhum time (nem Sem Contrato): "
            + ", ".join(ed.nome_jogador(p)["nome"] for p in sem[:8]) + ("…" if len(sem) > 8 else ""), None,
            {"acao": "sem_contrato", "args": {"pids": sem}, "rotulo": f"Mandar os {len(sem)} para Sem Contrato"})
    livres = set(ed.times_livres())
    for tid, links in por_time.items():
        if tid in livres:
            continue
        nome = ed.nome_time(tid)
        nums = collections.defaultdict(list)
        for r, d in links:
            nums[d.get("jerseynumber")].append((r, d))
        for n, ls in nums.items():
            if len(ls) > 1:
                add("aviso", "numero", f"{nome}: camisa {n} repetida ({', '.join(ed.nome_jogador(d['playerid'])['nome'] for _, d in ls)}).",
                    {"tipo": "time", "id": tid}, {"acao": "renumerar", "args": {"teamid": tid}, "rotulo": "Dar números livres aos repetidos"})
        if liga_de.get(tid) not in LIGAS_NAO_CLUBE or liga_de.get(tid) in LIGAS_SELECOES:
            if len(links) < 11:
                add("erro", "poucos", f"{nome} tem {len(links)} jogador(es) (menos de 11).", {"tipo": "time", "id": tid})
            elif len(links) > MAX_ELENCO:
                add("aviso", "muitos", f"{nome} tem {len(links)} jogadores (o jogo usa até {MAX_ELENCO}).", {"tipo": "time", "id": tid})
        elenco = {d["playerid"] for _, d in links}
        problemas = []
        _, ts = ed.um("default_teamsheets", teamid=tid) if ed.tem("default_teamsheets") else (None, None)
        if ts:
            fora = [ts[k] for k in ts if k.startswith("playerid") and k[8:].isdigit() and ts[k] not in ("-1", "", "0") and ts[k] not in elenco]
            if fora:
                problemas.append(f"{len(fora)} na escalação padrão")
            cob = [k for k in COBRADORES if ts.get(k) not in (None, "", "-1", "0") and ts.get(k) not in elenco]
            if cob:
                problemas.append(f"cobradores ({', '.join(cob)})")
        elif len(links) >= 11:
            add("aviso", "sem_folha", f"{nome} não tem escalação padrão (default_teamsheets).", {"tipo": "time", "id": tid})
        _, dm = ed.um("default_mentalities", teamid=tid) if ed.tem("default_mentalities") else (None, None)
        if dm and any(dm.get(f"playerid{i}") not in ("-1", "", "0") and dm.get(f"playerid{i}") not in elenco for i in range(11)):
            problemas.append("titulares da mentalidade")
        t = times.get(tid) or {}
        cob_t = [k for k in COBRADORES if t.get(k) not in (None, "", "-1", "0") and t.get(k) not in elenco]
        if cob_t:
            problemas.append("capitão/cobradores em teams")
        if problemas and len(links) >= 11:
            add("erro", "escalacao", f"{nome}: jogador(es) fora do elenco em " + "; ".join(problemas) + ".", {"tipo": "time", "id": tid},
                {"acao": "reescalar", "args": {"teamid": tid}, "rotulo": "Refazer a escalação"})
        if not ed.onde("formations", teamid=tid) and len(links) >= 11:
            add("aviso", "sem_formacao", f"{nome} não tem formação (formations).", {"tipo": "time", "id": tid})
    if ed.tem("playerloans"):
        for r, d in ed.dicts("playerloans"):
            pid, dono = d["playerid"], d.get("teamidloanedfrom")
            if pid not in jogadores:
                add("erro", "emp_jogador", f"playerloans: o jogador {pid} não existe.", None,
                    {"acao": "remover", "args": {"tabela": "playerloans", "ref": _rs(r)}, "rotulo": "Tirar o empréstimo"})
            elif dono not in times:
                add("erro", "emp_dono", f"{ed.nome_jogador(pid)['nome']}: emprestado por um time que não existe ({dono}).", {"tipo": "jogador", "id": pid},
                    {"acao": "remover", "args": {"tabela": "playerloans", "ref": _rs(r)}, "rotulo": "Tirar o empréstimo"})
            elif dono in clubes.get(pid, []):
                add("aviso", "emp_proprio", f"{ed.nome_jogador(pid)['nome']}: emprestado pelo próprio clube em que está ({ed.nome_time(dono)}).",
                    {"tipo": "jogador", "id": pid}, {"acao": "remover", "args": {"tabela": "playerloans", "ref": _rs(r)}, "rotulo": "Tirar o empréstimo"})
    if ed.tem("editedplayernames"):
        for r, d in ed.dicts("editedplayernames"):
            if d.get("playerid") not in jogadores:
                add("aviso", "nomes_orfaos", f"editedplayernames: nomes editados do jogador {d.get('playerid')}, que não existe.", None,
                    {"acao": "remover", "args": {"tabela": "editedplayernames", "ref": _rs(r)}, "rotulo": "Tirar a linha"})
    for tab in ("teamstadiumlinks", "teamnationlinks", "manager", "default_teamsheets", "default_mentalities", "formations", "teamkits"):
        if not ed.tem(tab) or "teamid" not in ed.campos(tab):
            continue
        for r, d in ed.dicts(tab):
            if d.get("teamid") not in times and d.get("teamid") not in ("-1", "", "0"):
                add("aviso", "orfao_time", f"{tab}: linha do time {d.get('teamid')}, que não existe.", None,
                    {"acao": "remover", "args": {"tabela": tab, "ref": _rs(r)}, "rotulo": "Tirar a linha"})
    # chaves repetidas e valores fora da faixa (nas tabelas principais e nas mexidas)
    for tab, ch in (("players", "playerid"), ("teams", "teamid"), ("leagues", "leagueid")):
        cont = collections.Counter(d[ch] for _, d in ed.dicts(tab))
        for k, n in cont.items():
            if n > 1:
                add("erro", "chave", f"{tab}: {ch} {k} aparece {n} vezes.", None)
    for tab in sorted(set(ed.tabelas_mexidas()) | {"players", "teams", "teamplayerlinks"}):
        if not ed.tem(tab):
            continue
        info = ed.info(tab)
        ints = {c: (i.get("low", 0), i.get("high", 0)) for c, i in info.items() if (i.get("t3") == 3 or "int" in (i.get("tipo") or "").lower()) and i.get("high")}
        fora = collections.Counter()
        for r, d in ed.dicts(tab):
            for c, (lo, hi) in ints.items():
                v = d.get(c)
                if v not in (None, "") and v.lstrip("-").isdigit() and not lo <= int(v) <= hi:
                    fora[c] += 1
        if fora:
            add("aviso", "faixa", f"{tab}: valores fora da faixa do meta — " + ", ".join(f"{c} ({n})" for c, n in fora.most_common(6)) + ".", None,
                {"acao": "ajustar_faixa", "args": {"tabela": tab}, "rotulo": "Levar para a borda da faixa"})
    ordem = {"erro": 0, "aviso": 1, "info": 2}
    P.sort(key=lambda p: (ordem[p["gravidade"]], p["tipo"]))
    return P


def corrigir(ed, acao, args):
    if acao == "remover":
        with ed.operacao(f"Corrigir: tirar linha de {args['tabela']}"):
            ed.remover(args["tabela"], args["ref"])
    elif acao == "reescalar":
        reescalar(ed, args["teamid"])
    elif acao == "renumerar":
        tid = args["teamid"]
        with ed.operacao(f"Números livres: {ed.nome_time(tid)}"):
            usados = set()
            for r, d in sorted(ed.dicts("teamplayerlinks", teamid=tid), key=lambda x: int(x[1].get("position") or 29)):
                n = d.get("jerseynumber")
                if n in usados:
                    novo = next(x for x in range(2, 100) if str(x) not in usados)
                    ed.alterar("teamplayerlinks", r, {"jerseynumber": novo})
                    n = str(novo)
                usados.add(n)
    elif acao == "sem_contrato":
        with ed.operacao(f"{len(args['pids'])} jogador(es) para Sem Contrato"):
            for pid in args["pids"]:
                v = {c: "0" for c in ed.campos("teamplayerlinks")}
                livre = ed.time_livre_para(pid)
                v.update(teamid=livre, playerid=pid, jerseynumber=ed.numero_livre(livre), position=29)
                if "artificialkey" in v:
                    v["artificialkey"] = ed.proximo_id("teamplayerlinks", "artificialkey")
                ed.inserir("teamplayerlinks", v)
    elif acao == "ajustar_faixa":
        tab = args["tabela"]
        info = ed.info(tab)
        ints = {c: (i.get("low", 0), i.get("high", 0)) for c, i in info.items() if (i.get("t3") == 3 or "int" in (i.get("tipo") or "").lower()) and i.get("high")}
        with ed.operacao(f"Valores na faixa: {tab}"):
            for r, d in ed.dicts(tab):
                v = {}
                for c, (lo, hi) in ints.items():
                    x = d.get(c)
                    if x not in (None, "") and x.lstrip("-").isdigit() and not lo <= int(x) <= hi:
                        v[c] = max(lo, min(hi, int(x)))
                if v:
                    ed.alterar(tab, r, v)
    else:
        raise ErroEdicao(f"Correção desconhecida: {acao}")


# ====================================================================== gravar
def gravar(ed, pasta, progresso=None):
    """Banco novo em <pasta>: db\\fifa_ng_db.db (+ meta), tabelas\\<mexidas>.txt, idioma\\ e relatorio.txt."""
    passo = progresso or (lambda m: None)
    b = ed.b
    os.makedirs(pasta, exist_ok=True)
    mexidas = ed.tabelas_mexidas()
    avisos = []
    pasta_txt = os.path.join(pasta, "tabelas")
    os.makedirs(pasta_txt, exist_ok=True)
    blobs = {}
    contagem = {}
    for i, t in enumerate(mexidas):
        passo(f"Tabela {t} ({i + 1}/{len(mexidas)})")
        tb = b.tabela(t)
        linhas = [[str(d.get(c, "")) for c in tb.campos] for d in (ed.linha(t, r) for r in ed.refs(t))]
        dados.escrever_txt(os.path.join(pasta_txt, t + ".txt"), tb.campos, linhas, "utf-16")
        contagem[t] = len(linhas)
        if b.fonte.tipo == "db":
            av = []
            blobs[t] = dados.montar_tabela(b.fonte, t, linhas, av)
            avisos += av[:10]
    arq_db = None
    if b.fonte.tipo == "db":
        passo("Banco novo")
        pdb = os.path.join(pasta, "db")
        os.makedirs(pdb, exist_ok=True)
        arq_db = os.path.join(pdb, "fifa_ng_db.db")
        if os.path.normcase(os.path.abspath(arq_db)) == os.path.normcase(os.path.abspath(b.fonte.caminho)):
            raise ErroEdicao("A pasta de saída não pode ser a do banco original.")
        dados.gravar_banco(b.fonte, blobs, arq_db)
        import shutil
        shutil.copy2(b.fonte.meta_caminho, os.path.join(pdb, "fifa_ng_db-meta.xml"))
        passo("Conferindo")
        f2 = dados.FonteDB(arq_db, b.fonte.meta_caminho)
        for t in blobs:
            if f2.tabs[t]["hdr"][5] != contagem[t]:
                raise ErroEdicao(f"Conferência falhou em {t}: {f2.tabs[t]['hdr'][5]} registros, esperado {contagem[t]}.")
    else:
        avisos.append("O banco importado é uma pasta de tabelas .txt: o resultado sai só em tabelas\\ (importe pelo RDBM).")
    # idioma
    pid = os.path.join(pasta, "idioma")
    n_idioma = 0
    if ed.idioma:
        os.makedirs(pid, exist_ok=True)
        novos = sorted(((k, v, dados._hash_idioma(k)) for k, v in ed.idioma.items()), key=lambda x: x[2])
        with open(os.path.join(pid, "LanguageStrings_novos.txt"), "w", encoding="utf-8", newline="\r\n") as f:
            f.write("stringid\tsourcetext\thashid\n")
            for k, v, h in novos:
                f.write(f"{k}\t{v}\t{h}\n")
        n_idioma = len(novos)
        idi = dados.idioma_atual()
        if idi is not None and getattr(idi, "arquivos", None) and all(a.lower().endswith(".txt") for a in idi.arquivos):
            try:
                _mesclar_idioma(idi.arquivos, novos, pid)
            except (OSError, ValueError) as ex:
                avisos.append(f"Idioma completo não gerado: {ex}")
    with open(os.path.join(pasta, "relatorio.txt"), "w", encoding="utf-8") as f:
        f.write(f"BRFP Super Tool — Editor de Banco\n{time.strftime('%d/%m/%Y %H:%M')}\n\nBanco de origem: {b.reg.get('caminho')}\n")
        f.write(f"Banco novo: {arq_db or '(só tabelas .txt)'}\n\nTabelas mexidas:\n")
        for t, r in ed.resumo().items():
            f.write(f"  {t}: {r['alteradas']} alterada(s), {r['novas']} nova(s), {r['removidas']} removida(s) — {contagem.get(t)} linhas\n")
        f.write(f"\nTextos de idioma: {n_idioma}\n\nOperações desta sessão:\n")
        for op in ed.historico:
            f.write(f"  - {op['rotulo']}\n")
        if avisos:
            f.write("\nAvisos:\n" + "".join(f"  - {a}\n" for a in avisos))
    return {"pasta": pasta, "db": arq_db, "tabelas": {t: contagem[t] for t in mexidas}, "idioma": n_idioma, "avisos": avisos}


def _mesclar_idioma(arquivos, novos, pasta):
    """LanguageStrings1/2 completos: as linhas do idioma importado com as novas no lugar (pelo hashid)."""
    linhas, limites = [], []
    for a in sorted(arquivos):
        campos, ls, _ = dados.ler_txt(a)
        ci, cs, ch = campos.index("stringid"), campos.index("sourcetext"), campos.index("hashid")
        hs = [int(l[ch]) for l in ls if len(l) > ch and l[ch].lstrip("-").isdigit()]
        limites.append(max(hs) if hs else None)
        for l in ls:
            if len(l) > ch:
                linhas.append((l[ci], l[cs], int(l[ch]) if l[ch].lstrip("-").isdigit() else 0))
    chaves = {k for k, _, _ in novos}
    linhas = [l for l in linhas if l[0] not in chaves] + list(novos)
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
