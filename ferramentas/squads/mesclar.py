"""Atualizador de Squads — leva o que o mod acrescentou para o squad oficial mais recente da EA.

Regras (o squad da EA é a base; tudo que não é dito aqui fica como a EA mandou):
  - times brasileiros do mod (ligas do Brasil; a lista pode ser ajustada) e times que só existem no mod vêm inteiros do
    mod: o registro do time, liga, uniformes, estádio, técnico, formação, táticas, escalação, rivais, patrocínios e o
    elenco. Os jogadores que a EA tinha nesses times saem (genéricos e reais) e entram os do mod;
  - jogadores: o mesmo jogador nos dois squads (mesmo ID, ou nome + nascimento + nacionalidade parecidos) vira um só.
    Quem joga num time brasileiro no mod fica com os dados do mod (e sai do clube que tinha na EA); nos outros casos
    valem os dados da EA. IDs que a EA passou a usar para outro jogador ganham um ID livre;
  - jogadores criados pelo mod (com nome editado, ou fora do squad base quando ele é informado) em times da EA são
    acrescentados; jogadores que a EA tirou depois que o mod foi feito não voltam;
  - ligas do Brasil e ligas que só existem no mod, competições, árbitros, imagens e patrocinadores novos do mod entram;
  - escalações que perderam ou ganharam jogadores são refeitas (titulares, banco, capitão e cobradores).
"""
import collections
import difflib
import re
import unicodedata

PAIS_BRASIL = 54
LIGAS_INTER = {78, 2136}
LIGA_LIVRES = 382                                          # Free Agents League: "Sem contrato", "NG - FA"...
TIME_LIVRES = 111592

# tabelas com linhas por time: colunas com o ID do time
TIMES = {"teams": ["teamid"], "leagueteamlinks": ["teamid"], "teamkits": ["teamtechid"], "teamstadiumlinks": ["teamid"],
         "manager": ["teamid"], "formations": ["teamid"], "default_mentalities": ["teamid"], "default_teamsheets": ["teamid"],
         "teamnationlinks": ["teamid"], "teamsponsorlinks": ["teamid"], "stadiumassignments": ["teamid"],
         "kitrewardsmapping": ["teamid"], "mls_group_structure": ["teamid"], "multiclubownership": ["teamid"],
         "teamformationteamstylelinks": ["teamid"], "rivals": ["teamid1", "teamid2"],
         "teamcounterparts": ["maleteamid", "femaleteamid"]}
# um conjunto de linhas por time que a EA sempre tem: não completa com o mod
TIMES_COMPLETOS = {"teams", "leagueteamlinks", "default_mentalities", "default_teamsheets", "formations", "manager"}
JOGADORES = ["editedplayernames", "playerloans", "previousteam", "player_grudgelove", "ucc", "playerpronouns",
             "playerbodyrestrictions", "playersockoverride", "playersuspensions", "transfers", "playerarchetypelinks",
             "prevcompetitionstats", "playerformdiff"]
COMPETICOES = ["competition", "competitionbadges", "competitionballs", "competitionkits", "competitionmatchups",
               "competitionrefereekits", "competitionseeds", "competitionsponsorlinks", "competitionstadiumlinks",
               "competitionuefasponsors"]
POR_CHAVE = {"referee": "refereeid", "dynamicimages": "dynamicimageid", "sponsors": "adsponserid", "stadiums": "stadiumid"}
IDS_UNICOS = {"teamkits": "teamkitid", "formations": "formationid", "manager": "managerid"}
REFS_IDS = {"teamkitid": [("kitrewardsmapping", "teamkitid")], "formationid": [("default_mentalities", "sourceformationid")]}
NOMES_JOGADOR = ("firstnameid", "lastnameid", "commonnameid", "playerjerseynameid")
COBRADORES = ("captainid", "penaltytakerid", "freekicktakerid", "leftfreekicktakerid", "rightfreekicktakerid",
              "leftcornerkicktakerid", "rightcornerkicktakerid", "longkicktakerid")
RE_JOGADOR = re.compile(r"^(playerid\d*|captainid|\w+takerid|customsub\d+(in|out)|playertechid)$")
BASE_POS = {4: 5, 6: 5, 9: 10, 11: 10, 13: 14, 15: 14, 17: 18, 19: 18, 20: 21, 22: 21, 24: 25, 26: 25, 2: 3, 8: 7, 12: 16, 23: 27}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def _razao(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _grupo(p):
    p = int(p)
    return 0 if p == 0 else 1 if p <= 8 else 2 if p <= 19 else 3 if p <= 27 else 4


def _custo_pos(jog, vaga):
    a, b = BASE_POS.get(jog, jog), BASE_POS.get(vaga, vaga)
    if a == b:
        return 0
    if 0 in (a, b):
        return 9
    return 1 if _grupo(a) == _grupo(b) else 3


class Pessoa:
    __slots__ = ("pid", "primeiro", "sobrenome", "comum", "nasc", "nac", "overall", "nome")

    def __init__(self, pid, primeiro, sobrenome, comum, nasc, nac, overall):
        self.pid, self.nasc, self.nac, self.overall = pid, nasc, nac, overall
        self.primeiro, self.sobrenome, self.comum = _norm(primeiro), _norm(sobrenome), _norm(comum)
        self.nome = (comum or f"{primeiro} {sobrenome}").strip() or f"#{pid}"

    @property
    def completo(self):
        return f"{self.primeiro} {self.sobrenome}".strip()

    def tem_nome(self):
        return bool(self.completo or self.comum)


def nomes_parecidos(a, b, estrito=True):
    """Mesmo nome? Estrito: gêmeos (Anton/Aleksey Miranchuk) não passam; frouxo (mesmo ID): basta o sobrenome."""
    if a.comum and a.comum in (b.comum, b.completo) or b.comum and b.comum in (a.comum, a.completo):
        return True
    if _razao(a.completo, b.completo) >= (0.85 if estrito else 0.6):
        return True
    sa, sb = a.sobrenome, b.sobrenome
    mesmo_sobrenome = bool(sa and sb and (sa == sb or (min(len(sa), len(sb)) >= 4 and (sa in sb or sb in sa))))
    if not mesmo_sobrenome:
        return False
    if not estrito:
        return True
    pa, pb = a.primeiro, b.primeiro
    if not pa or not pb:
        return True
    return pa.split()[0] == pb.split()[0] or _razao(pa, pb) >= 0.75 or pa in pb or pb in pa


class Atualizador:
    def __init__(self, ea, mod, nomes_jogo=None, base=None, log=None, progresso=None):
        self.ea, self.mod, self.base = ea, mod, base
        self.nomes_jogo = nomes_jogo or {}
        self.log = log or (lambda *_: None)
        self.prog = progresso or (lambda *_: None)
        self._conv = {}
        self._linhas_mod = {}
        self.avisos = []

    # ------------------------------------------------------------------ acesso às tabelas
    def te(self, nome):
        return self.ea.tabela(nome)

    def c(self, nome, campo):
        return self.te(nome).col(campo)

    def linhas_ea(self, nome):
        return self.te(nome).linhas if self.ea.tem(nome) else []

    def linhas_mod(self, nome):
        """Linhas do mod já na ordem de campos da tabela da EA (campos que faltam: valor vazio)."""
        if nome not in self._linhas_mod:
            if not (self.ea.tem(nome) and self.mod.tem(nome)):
                self._linhas_mod[nome] = []
            else:
                te, tm = self.te(nome), self.mod.tabela(nome)
                pos = [tm.col(c.nome) for c in te.campos]
                vazio = te.linha_vazia()
                if pos == list(range(len(pos))) and len(tm.campos) == len(te.campos):
                    self._linhas_mod[nome] = [list(l) for l in tm.linhas]
                else:
                    self._linhas_mod[nome] = [[l[p] if p is not None else vazio[i] for i, p in enumerate(pos)] for l in tm.linhas]
        return self._linhas_mod[nome]

    # ------------------------------------------------------------------ nomes
    def _pessoas(self, sq, linhas_players, tab_players):
        dc = {}
        if sq.tem("dcplayernames"):
            t = sq.tabela("dcplayernames")
            i, n = t.col("nameid"), t.col("name")
            dc = {l[i]: l[n] for l in t.linhas}
        ed = {}
        if sq.tem("editedplayernames"):
            t = sq.tabela("editedplayernames")
            ip, fi, su, co = (t.col(x) for x in ("playerid", "firstname", "surname", "commonname"))
            ed = {l[ip]: (l[fi], l[su], l[co]) for l in t.linhas}
        nj = self.nomes_jogo

        def nm(i):
            return dc[i] if i in dc else nj.get(i, "")
        c = {k: tab_players.col(k) for k in ("playerid", "firstnameid", "lastnameid", "commonnameid", "birthdate", "nationality", "overallrating")}
        out = {}
        for l in linhas_players:
            pid = l[c["playerid"]]
            if pid in ed:
                f, s, cm = ed[pid]
            else:
                f, s = nm(l[c["firstnameid"]]), nm(l[c["lastnameid"]])
                cm = nm(l[c["commonnameid"]]) if l[c["commonnameid"]] else ""
            out[pid] = Pessoa(pid, f, s, cm, l[c["birthdate"]], l[c["nationality"]], l[c["overallrating"]] if c["overallrating"] is not None else 0)
        return out, set(ed)

    def nome_time(self, tid):
        return self.nomes_times.get(tid) or f"time {tid}"

    # ------------------------------------------------------------------ análise
    def analisar(self):
        self.prog("Lendo os times e as ligas", 0.05)
        ct, cn = self.c("teams", "teamid"), self.c("teams", "teamname")
        self.times_ea = {l[ct]: l for l in self.linhas_ea("teams")}
        self.times_mod = {l[ct]: l for l in self.linhas_mod("teams")}
        self.nomes_times = {t: l[cn] for t, l in self.times_ea.items()}
        self.nomes_times.update({t: l[cn] for t, l in self.times_mod.items()})
        lt, ll = self.c("leagueteamlinks", "teamid"), self.c("leagueteamlinks", "leagueid")
        self.liga_ea = {l[lt]: l[ll] for l in self.linhas_ea("leagueteamlinks")}
        self.liga_mod = {l[lt]: l[ll] for l in self.linhas_mod("leagueteamlinks")}
        li, lp, ln, lint = (self.c("leagues", k) for k in ("leagueid", "countryid", "leaguename", "isinternationalleague"))
        self.ligas = {}
        for l in self.linhas_ea("leagues") + self.linhas_mod("leagues"):
            if l[li] >= 0:
                self.ligas[l[li]] = {"pais": l[lp], "nome": l[ln], "inter": bool(l[lint]) if lint is not None else False}
        self.ligas_inter = LIGAS_INTER | {k for k, v in self.ligas.items() if v["inter"]}
        self.selecoes = {t for t, lg in list(self.liga_ea.items()) + list(self.liga_mod.items()) if lg in self.ligas_inter}
        self.ligas_br = {k for k, v in self.ligas.items() if v["pais"] == PAIS_BRASIL and not v["inter"]}
        self.br_auto = {t for t, lg in self.liga_mod.items() if lg in self.ligas_br and t not in self.selecoes}
        self.novos = {t for t in self.times_mod if t not in self.times_ea}
        self.times_livres = {t for t, lg in list(self.liga_ea.items()) + list(self.liga_mod.items()) if lg == LIGA_LIVRES}

        self.prog("Lendo os jogadores", 0.15)
        tp = self.te("players")
        self.cp = {c.nome: i for i, c in enumerate(tp.campos)}
        self.jog_ea = {l[self.cp["playerid"]]: l for l in tp.linhas}
        self.jog_mod = {l[self.cp["playerid"]]: l for l in self.linhas_mod("players")}
        self.pes_ea, _ = self._pessoas(self.ea, tp.linhas, tp)
        self.pes_mod, self.editados_mod = self._pessoas(self.mod, self.mod.tabela("players").linhas, self.mod.tabela("players"))
        if self.base is not None:
            tb = self.base.tabela("players")
            ib = tb.col("playerid")
            self.ids_base = {l[ib] for l in tb.linhas}
        else:
            self.ids_base = None
        self.vinc_ea = collections.defaultdict(list)
        self.vinc_mod = collections.defaultdict(list)
        cl = self.te("teamplayerlinks")
        self.ctl = {c.nome: i for i, c in enumerate(cl.campos)}
        for l in self.linhas_ea("teamplayerlinks"):
            self.vinc_ea[l[self.ctl["playerid"]]].append(l)
        for l in self.linhas_mod("teamplayerlinks"):
            self.vinc_mod[l[self.ctl["playerid"]]].append(l)
        sem_nome = sum(1 for p in self.pes_ea.values() if not p.tem_nome())
        return {
            "times_ea": len(self.times_ea), "times_mod": len(self.times_mod),
            "jogadores_ea": len(self.jog_ea), "jogadores_mod": len(self.jog_mod),
            "sem_nome_ea": sem_nome, "nomes_do_jogo": len(self.nomes_jogo),
            "brasileiros": sorted(({"id": t, "nome": self.nome_time(t), "liga": self.liga_mod.get(t),
                                    "liga_nome": self.ligas.get(self.liga_mod.get(t), {}).get("nome", ""),
                                    "na_ea": t in self.times_ea,
                                    "liga_ea": self.ligas.get(self.liga_ea.get(t), {}).get("nome", "") if t in self.times_ea else "",
                                    "auto": True} for t in self.br_auto), key=lambda x: (not x["na_ea"], x["liga"] or 0, x["nome"])),
            "novos": len(self.novos),
            "novos_por_liga": sorted(([self.ligas.get(lg, {}).get("nome") or f"liga {lg}", n] for lg, n in
                                      collections.Counter(self.liga_mod.get(t) for t in self.novos).items()), key=lambda x: -x[1]),
        }

    # ------------------------------------------------------------------ jogadores
    def _clube(self, vinculos):
        ct = self.ctl["teamid"]
        return next((l[ct] for l in vinculos if l[ct] not in self.selecoes), None)

    def _criado_pelo_mod(self, pid):
        if self.ids_base is not None:
            return pid not in self.ids_base
        return pid in self.editados_mod

    def _resolver_jogadores(self, R, B):
        ct = self.ctl["teamid"]
        ea_por_nasc = collections.defaultdict(list)
        for pid, p in self.pes_ea.items():
            ea_por_nasc[p.nasc].append(pid)
        # mod: quem entra na conta (times do mod ou criado pelo mod), primeiro quem está em time brasileiro
        candidatos = []
        for pid in self.jog_mod:
            vs = self.vinc_mod.get(pid, [])
            em_r = any(l[ct] in R for l in vs)
            if em_r or (pid not in self.jog_ea and self._criado_pelo_mod(pid)):
                clube = self._clube(vs)
                candidatos.append((0 if clube in B else 1 if em_r else 2, pid))
        candidatos.sort()
        self.casado = {}          # pid do mod -> pid da EA (mesma pessoa)
        self.dup_mod = {}         # pid do mod -> pid do mod que fica (o mesmo jogador duas vezes no mod)
        self.importar = []        # pids do mod sem par na EA
        self.relato_dups = []
        self.relato_ids = []
        ja_casado = {}
        imp_por_nasc = collections.defaultdict(list)
        for prio, pid in candidatos:
            m = self.pes_mod[pid]
            e = None
            if pid in self.pes_ea:
                pe = self.pes_ea[pid]
                if nomes_parecidos(m, pe, estrito=False) or (pe.nasc == m.nasc and pe.nac == m.nac) or not (m.tem_nome() and pe.tem_nome()) and abs(pe.nasc - m.nasc) <= 1:
                    e = pid
            if e is None:
                for d in (0, -1, 1):
                    for q in ea_por_nasc.get(m.nasc + d, ()):
                        pe = self.pes_ea[q]
                        if q != pid and (pe.nac == m.nac or pe.comum and pe.comum == m.comum) and m.tem_nome() and pe.tem_nome() and nomes_parecidos(m, pe):
                            e = q
                            break
                    if e is not None:
                        break
            if e is not None:
                if e in ja_casado:                         # duas entradas do mod para o mesmo jogador da EA
                    self.dup_mod[pid] = ja_casado[e]
                    self.relato_dups.append({"tipo": "mod", "nome": m.nome, "mod": pid, "fica": ja_casado[e]})
                    continue
                ja_casado[e] = pid
                self.casado[pid] = e
                if e != pid:
                    self.relato_dups.append({"tipo": "ea", "nome": m.nome, "mod": pid, "ea": e, "nome_ea": self.pes_ea[e].nome,
                                             "dados": "mod" if prio == 0 else "ea"})
                continue
            if pid in self.pes_ea:
                self.relato_ids.append({"mod": pid, "nome": m.nome, "nome_ea": self.pes_ea[pid].nome})
            outro = None
            for d in (0, -1, 1):
                for q in imp_por_nasc.get(m.nasc + d, ()):
                    pq = self.pes_mod[q]
                    if (pq.nac == m.nac or pq.comum and pq.comum == m.comum) and m.tem_nome() and nomes_parecidos(m, pq):
                        outro = q
                        break
                if outro:
                    break
            if outro:
                self.dup_mod[pid] = outro
                self.relato_dups.append({"tipo": "mod", "nome": m.nome, "mod": pid, "fica": outro})
                continue
            self.importar.append(pid)
            imp_por_nasc[m.nasc].append(pid)
        self.prio_mod = {self.casado[pid] for prio, pid in candidatos if prio == 0 and pid in self.casado}

    # ------------------------------------------------------------------ execução
    def executar(self, brasileiros=None):
        if not hasattr(self, "times_ea"):
            self.analisar()
        B = set(self.br_auto if brasileiros is None else brasileiros) & set(self.times_mod)
        R = B | self.novos
        self.B, self.R = B, R
        ct, cp_ = self.ctl["teamid"], self.ctl["playerid"]
        self.prog("Procurando jogadores duplicados", 0.25)
        self._resolver_jogadores(R, B)

        # EA: quem estava em time brasileiro e não aparece no mod sai (ou vai para os livres se tem seleção)
        casados_ea = set(self.casado.values())
        self.excluir, livres = set(), set()
        for pid, vs in self.vinc_ea.items():
            if any(l[ct] in R for l in vs) and pid not in casados_ea:
                if any(l[ct] not in R for l in vs):
                    if self._clube([l for l in vs if l[ct] not in R]) is None:
                        livres.add(pid)
                else:
                    self.excluir.add(pid)

        # IDs finais dos jogadores do mod
        usados = set(self.jog_ea) - self.excluir
        prox = [max(list(self.jog_ea) + list(self.jog_mod) + [0]) + 1]
        self.mapa = {}
        for pid, e in self.casado.items():
            self.mapa[pid] = e
        for pid in self.importar:
            if pid in usados:
                novo = prox[0]
                prox[0] += 1
                self.mapa[pid] = novo
            else:
                self.mapa[pid] = pid
            usados.add(self.mapa[pid])
        for pid, outro in self.dup_mod.items():
            self.mapa[pid] = self.mapa.get(outro, outro)
        for r in self.relato_ids:
            r["novo"] = self.mapa.get(r["mod"])
        fonte_mod = {self.mapa[p]: p for p in self.importar}                     # id final -> pid do mod
        fonte_mod.update({e: pid for pid, e in self.casado.items() if e in self.prio_mod})
        self.fonte_mod = fonte_mod

        self.prog("Montando os elencos", 0.4)
        self._nomes_dc()
        novas = {}
        novas["players"] = self._players(fonte_mod)
        tpl = self._elencos(R, B, livres)
        self._ids_unicos = {}
        for nome in TIMES:
            if self.ea.tem(nome):
                novas[nome] = self._tabela_times(nome, R)
        novas["teamplayerlinks"] = tpl
        self.prog("Ligas, competições e o resto", 0.6)
        for nome in JOGADORES:
            if self.ea.tem(nome):
                novas[nome] = self._tabela_jogadores(nome, fonte_mod)
        self._ligas(R, novas)
        for nome in COMPETICOES:
            if self.ea.tem(nome):
                novas[nome] = self._tabela_competicoes(nome)
        for nome, chave in POR_CHAVE.items():
            if self.ea.tem(nome):
                novas[nome] = self._tabela_chave(nome, chave, B)
        novas["dcplayernames"] = self.dc_linhas
        # tabelas que ficam da EA: tira referências a jogadores excluídos
        for nome, t in self.ea.tabelas.items():
            if nome in novas or not t.validos:
                continue
            cols = [i for i, c in enumerate(t.campos) if c.nome in ("playerid", "playertechid")]
            if cols and self.excluir:
                ls = [l for l in t.linhas if not any(l[i] in self.excluir for i in cols)]
                if len(ls) != len(t.linhas):
                    novas[nome] = ls
        self._ajustar_chaves_artificiais(novas)
        self.prog("Refazendo as escalações", 0.75)
        self.escalacoes = self._escalacoes(novas)
        # só grava as tabelas que mudaram
        self.novas = {n: ls for n, ls in novas.items() if ls != self.te(n).linhas}
        return self.relatorio()

    # ------------------------------------------------------------------ dcplayernames (nomes extras do squad)
    def _nomes_dc(self):
        t = self.te("dcplayernames")
        i, n = t.col("nameid"), t.col("name")
        self.dc_linhas = [list(l) for l in t.linhas]
        por_nome = {l[n]: l[i] for l in self.dc_linhas}
        dc_mod = {l[i]: l[n] for l in self.linhas_mod("dcplayernames")}
        prox = max([l[i] for l in self.dc_linhas] + list(dc_mod) + [45999]) + 1
        self.mapa_dc = {}
        for nid, nome in dc_mod.items():
            if nome in por_nome:
                self.mapa_dc[nid] = por_nome[nome]
            else:
                linha = t.linha_vazia()
                linha[i], linha[n] = prox, nome
                self.dc_linhas.append(linha)
                por_nome[nome] = prox
                self.mapa_dc[nid] = prox
                prox += 1

    def _linha_jogador_mod(self, l, novo_id):
        l = list(l)
        l[self.cp["playerid"]] = novo_id
        for k in NOMES_JOGADOR:
            i = self.cp.get(k)
            if i is not None and l[i] in self.mapa_dc:
                l[i] = self.mapa_dc[l[i]]
        return l

    def _players(self, fonte_mod):
        ip = self.cp["playerid"]
        out = []
        for l in self.te("players").linhas:
            pid = l[ip]
            if pid in self.excluir:
                continue
            if pid in fonte_mod:
                out.append(self._linha_jogador_mod(self.jog_mod[fonte_mod[pid]], pid))
            else:
                out.append(l)
        for pid in self.importar:
            out.append(self._linha_jogador_mod(self.jog_mod[pid], self.mapa[pid]))
        self.final_jog = {l[ip]: l for l in out}
        return out

    # ------------------------------------------------------------------ elencos
    def _elencos(self, R, B, livres):
        ct, cp_, cj, cpos = (self.ctl[k] for k in ("teamid", "playerid", "jerseynumber", "position"))
        mapa = self.mapa
        ok = set(self.final_jog)
        por_time = collections.OrderedDict()
        origem = {}

        def add(l, de):
            por_time.setdefault(l[ct], []).append(l)
            origem.setdefault((l[ct], l[cp_]), de)
        # EA, fora dos times do mod; jogadores que vieram do mod para time brasileiro saem do clube da EA
        for l in self.linhas_ea("teamplayerlinks"):
            t, p = l[ct], l[cp_]
            if t in R or p not in ok:
                continue
            if p in self.prio_mod and t not in self.selecoes:
                continue
            add(list(l), "ea")
        clube_ea = collections.defaultdict(list)            # clube de verdade (sem seleções nem "sem contrato")
        for t, ls in por_time.items():
            if t not in self.selecoes and t not in self.times_livres:
                for l in ls:
                    clube_ea[l[cp_]].append(t)
        # mod: times brasileiros e novos; jogadores criados pelo mod em times da EA
        pendentes = []
        pid_mod = {}
        importados = set(self.importar)
        for l in self.linhas_mod("teamplayerlinks"):
            t, p = l[ct], l[cp_]
            if p not in mapa or t not in self.times_mod:
                continue
            novo = mapa[p]
            if novo not in ok:
                continue
            if t in R:
                if t not in self.selecoes and novo not in self.prio_mod and clube_ea.get(novo) and novo not in self.fonte_mod:
                    pendentes.append((novo, l))             # dados da EA e já tem clube na EA: fica lá
                    continue
            elif p in importados and p not in self.dup_mod:
                if t not in self.times_ea:
                    continue
            elif not clube_ea.get(novo) and t not in self.selecoes and t in self.times_ea:
                pendentes.append((novo, l))
                continue
            else:
                continue
            l = list(l)
            l[cp_] = novo
            add(l, "mod")
            pid_mod.setdefault((t, novo), p)
        # quem ficou sem clube: o clube do mod (se existir) ou o time dos livres
        clubes = collections.defaultdict(list)
        for t, ls in por_time.items():
            if t not in self.selecoes and t not in self.times_livres:
                for l in ls:
                    clubes[l[cp_]].append(t)
        for novo, l in pendentes:
            if not clubes.get(novo):
                l = list(l)
                l[cp_] = novo
                add(l, "mod")
                clubes[novo].append(l[ct])
        livre = TIME_LIVRES if TIME_LIVRES in self.times_ea else next((t for t, lg in self.liga_ea.items() if lg == 382), None)
        livres_de = collections.defaultdict(list)          # vínculos com "sem contrato"
        for t in self.times_livres:
            for l in por_time.get(t, []):
                livres_de[l[cp_]].append(t)
        self.para_livres = []
        for pid in livres:
            if not clubes.get(pid) and not livres_de.get(pid) and pid in ok and livre is not None:
                l = self.te("teamplayerlinks").linha_vazia()
                l[ct], l[cp_], l[cpos], l[cj] = livre, pid, 29, 0
                add(l, "ea")
                clubes[pid].append(livre)
                self.para_livres.append(pid)
        # um clube por jogador; sem vínculo repetido
        for pid, ts in livres_de.items():                   # "sem contrato" da EA + clube no mod: fica o clube
            if clubes.get(pid) and any(origem.get((t, pid)) == "ea" for t in ts) and any(origem.get((x, pid)) == "mod" for x in clubes[pid]):
                clubes[pid] = clubes[pid] + [t for t in ts]
        escolhido = {}                                      # só conflitos criados pela mescla (EA x mod); times
        for pid, cs in clubes.items():                      # especiais da EA (All-Stars, XI, 5x5) ficam como estão
            reais = [x for x in cs if x not in self.times_livres]
            if len(cs) > len(reais) and reais:
                cs = reais if len(reais) > 1 else cs
                if len(reais) == 1:
                    escolhido[pid] = reais[0]
                    continue
            if len(cs) > 1 and any(pid_mod.get((x, pid)) in self.dup_mod for x in cs):
                escolhido[pid] = next((x for x in cs if pid_mod.get((x, pid)) not in self.dup_mod), cs[0])
            elif len(cs) > 1 and {origem.get((x, pid)) for x in cs} == {"ea", "mod"}:
                if pid in self.prio_mod:
                    escolhido[pid] = next((x for x in cs if x in self.B), cs[0])
                else:
                    escolhido[pid] = next((x for x in cs if origem.get((x, pid)) == "ea"), cs[0])
        self.clubes_repetidos = []
        final = []
        vistos = set()
        for t, ls in por_time.items():
            for l in ls:
                k = (l[ct], l[cp_])
                if k in vistos:
                    continue
                if l[cp_] in escolhido and t not in self.selecoes and t != escolhido[l[cp_]]:
                    self.clubes_repetidos.append((l[cp_], t, escolhido[l[cp_]]))
                    continue
                vistos.add(k)
                final.append(l)
        # camisas repetidas nos times que receberam jogadores de fora
        por_t = collections.defaultdict(list)
        for l in final:
            por_t[l[ct]].append(l)
        for t, ls in por_t.items():
            usados = collections.Counter(l[cj] for l in ls)
            if all(n <= 1 for k, n in usados.items() if k):
                continue
            livres_n = [n for n in range(1, 100) if n not in usados]
            vistos_n = set()
            for l in ls:
                if l[cj] and l[cj] in vistos_n and livres_n:
                    l[cj] = livres_n.pop(0)
                vistos_n.add(l[cj])
        ia = self.ctl.get("artificialkey")
        if ia is not None:
            for k, l in enumerate(final):
                l[ia] = k
        self.final_vinc = final
        self.elenco_origem = collections.defaultdict(set)   # elenco de cada time no squad de onde ele veio
        for l in self.linhas_ea("teamplayerlinks"):
            if l[ct] not in R:
                self.elenco_origem[l[ct]].add(l[cp_])
        for l in self.linhas_mod("teamplayerlinks"):
            if l[ct] in R:
                self.elenco_origem[l[ct]].add(mapa.get(l[cp_], -1))
        return final

    # ------------------------------------------------------------------ tabelas por time
    def _remapear_jogadores(self, nome, l):
        t = self.te(nome)
        for i, c in enumerate(t.campos):
            if RE_JOGADOR.match(c.nome) and isinstance(l[i], int) and l[i] > 0:
                l[i] = self.mapa.get(l[i], l[i] if l[i] in self.final_jog else -1)
        return l

    def _tabela_times(self, nome, R):
        t = self.te(nome)
        cols = [t.col(c) for c in TIMES[nome] if t.col(c) is not None]
        if not cols:
            return list(t.linhas)
        out = [l for l in t.linhas if not any(l[i] in R for i in cols)]
        com_ea = {l[cols[0]] for l in t.linhas}
        novas = []
        for l in self.linhas_mod(nome):
            vals = [l[i] for i in cols]
            if not all(v in self.times_mod or v in self.times_ea or v <= 0 for v in vals):
                continue
            if any(v in R for v in vals) or (nome not in TIMES_COMPLETOS and len(cols) == 1 and vals[0] not in com_ea and vals[0] in self.times_ea):
                novas.append(self._remapear_jogadores(nome, list(l)))
        idc = IDS_UNICOS.get(nome)
        if idc and novas:
            i = t.col(idc)
            usados = {l[i] for l in out}
            prox = max(usados | {l[i] for l in novas} | {0}) + 1
            remap = {}
            for l in novas:
                if l[i] in usados:
                    remap[l[i]] = prox
                    l[i] = prox
                    prox += 1
                usados.add(l[i])
            if remap:
                self._ids_unicos[idc] = remap
                if nome == "manager":
                    self.avisos.append(f"{len(remap)} técnico(s) do mod com o ID de outro técnico da EA ganharam um ID novo.")
        if nome == "default_mentalities" and "formationid" in self._ids_unicos:
            i = t.col("sourceformationid")
            for l in novas:
                l[i] = self._ids_unicos["formationid"].get(l[i], l[i])
        if nome == "kitrewardsmapping" and "teamkitid" in self._ids_unicos:
            i = t.col("teamkitid")
            for l in novas:
                l[i] = self._ids_unicos["teamkitid"].get(l[i], l[i])
        vistos, final = set(), []
        for l in out + novas:
            k = tuple(l)
            if k not in vistos:
                vistos.add(k)
                final.append(l)
        if t.chave:                                          # chave repetida: fica a última (a do mod)
            ultima = {t.valor_chave(l): k for k, l in enumerate(final)}
            final = [l for k, l in enumerate(final) if ultima[t.valor_chave(l)] == k]
        return final

    # ------------------------------------------------------------------ tabelas por jogador
    def _tabela_jogadores(self, nome, fonte_mod):
        t = self.te(nome)
        ip = t.col("playerid")
        if ip is None:
            return list(t.linhas)
        out = [l for l in t.linhas if l[ip] not in self.excluir and l[ip] not in fonte_mod]
        rev = {v: k for k, v in fonte_mod.items()}            # pid do mod -> id final
        for l in self.linhas_mod(nome):
            if l[ip] in rev:
                l = list(l)
                l[ip] = rev[l[ip]]
                out.append(l)
        if t.chave:
            vistos, final = set(), []
            for l in reversed(out):
                k = t.valor_chave(l)
                if k not in vistos:
                    vistos.add(k)
                    final.append(l)
            out = final[::-1]
        return out

    # ------------------------------------------------------------------ ligas e árbitros
    def _ligas(self, R, novas):
        lt = self.c("leagueteamlinks", "leagueid")
        it = self.c("leagueteamlinks", "teamid")
        fora = {l[lt] for l in novas["leagueteamlinks"] if l[it] not in R}
        do_mod = self.ligas_br | ({l[lt] for l in novas["leagueteamlinks"] if l[it] in R} - fora)
        self.ligas_do_mod = do_mod
        t = self.te("leagues")
        il = t.col("leagueid")
        ea_ids = {l[il] for l in t.linhas}
        mod_l = {l[il]: l for l in self.linhas_mod("leagues") if l[il] >= 0}
        out = []
        for l in t.linhas:
            out.append(mod_l[l[il]] if l[il] in do_mod and l[il] in mod_l else l)
        for k, l in mod_l.items():
            if k not in ea_ids:
                out.append(l)
        novas["leagues"] = out
        if self.ea.tem("leaguerefereelinks"):
            tr = self.te("leaguerefereelinks")
            i = tr.col("leagueid")
            ea_ligas = {l[i] for l in tr.linhas}
            ls = [l for l in tr.linhas if l[i] not in do_mod]
            ls += [l for l in self.linhas_mod("leaguerefereelinks") if l[i] in do_mod or l[i] not in ea_ligas]
            vistos = set()
            novas["leaguerefereelinks"] = [l for l in ls if not (tuple(l) in vistos or vistos.add(tuple(l)))]

    def _tabela_competicoes(self, nome):
        t = self.te(nome)
        i = t.col("competitionid")
        if i is None:
            return list(t.linhas)
        if not hasattr(self, "comp_novas"):
            ic = self.c("competition", "competitionid")
            ea_c = {l[ic] for l in self.linhas_ea("competition")}
            self.comp_novas = {l[ic] for l in self.linhas_mod("competition")} - ea_c
        return list(t.linhas) + [list(l) for l in self.linhas_mod(nome) if l[i] in self.comp_novas]

    def _tabela_chave(self, nome, chave, B):
        t = self.te(nome)
        i = t.col(chave)
        ea_ids = {l[i] for l in t.linhas}
        mod = {l[i]: l for l in self.linhas_mod(nome)}
        out = list(t.linhas)
        if nome == "stadiums":
            ih = t.col("hometeamid")
            out = [mod[l[i]] if l[ih] in B and l[i] in mod and mod[l[i]][ih] in B else l for l in out]
        out += [l for k, l in mod.items() if k not in ea_ids]
        return out

    def _ajustar_chaves_artificiais(self, novas):
        for nome, ls in novas.items():
            if nome in ("teamplayerlinks",):
                continue
            t = self.te(nome)
            ia = t.col("artificialkey")
            if ia is None or not ls:
                continue
            ls[:] = [list(l) for l in ls]
            if nome == "leagueteamlinks":
                for k, l in enumerate(ls):
                    l[ia] = k
                continue
            vistos = set()
            prox = max(l[ia] for l in ls) + 1
            for l in ls:
                if l[ia] in vistos:
                    l[ia] = prox
                    prox += 1
                vistos.add(l[ia])

    # ------------------------------------------------------------------ escalações
    def _escalacoes(self, novas):
        for n in ("default_teamsheets", "default_mentalities", "teams"):
            novas[n] = [list(l) for l in novas[n]]                # as linhas da EA não podem ser alteradas
        ct, cp_, cpos = (self.ctl[k] for k in ("teamid", "playerid", "position"))
        elenco = collections.defaultdict(list)
        for l in novas["teamplayerlinks"]:
            elenco[l[ct]].append(l)
        jog = self.final_jog
        cp = self.cp
        ts = self.te("default_teamsheets")
        tsi = {c.nome: i for i, c in enumerate(ts.campos)}
        pcols = sorted((c for c in tsi if re.fullmatch(r"playerid\d+", c)), key=lambda c: int(c[8:]))
        sheets = {l[tsi["teamid"]]: l for l in novas["default_teamsheets"]}
        tm = self.te("default_mentalities")
        tmi = {c.nome: i for i, c in enumerate(tm.campos)}
        ment = collections.defaultdict(list)
        for l in novas["default_mentalities"]:
            ment[l[tmi["teamid"]]].append(l)
        tf = self.te("formations")
        tfi = {c.nome: i for i, c in enumerate(tf.campos)}
        form = {l[tfi["teamid"]]: l for l in novas["formations"]}
        tt = self.te("teams")
        tti = {c.nome: i for i, c in enumerate(tt.campos)}
        times = {l[tti["teamid"]]: l for l in novas["teams"]}
        attr = lambda p, k: (jog[p][cp[k]] if p in jog and cp.get(k) is not None else 0)  # noqa: E731
        refeitos = []
        for tid, sheet in sheets.items():
            ls = elenco.get(tid, [])
            ros = [l[cp_] for l in ls]
            rs = set(ros)
            src = self.elenco_origem.get(tid, set())
            if rs == src:                                     # elenco igual ao de origem: escalação fica como veio
                continue
            ids = [sheet[tsi[c]] for c in pcols]
            tit = ids[:11]
            faltam = [p for p in ros if p not in src and p not in ids]
            ruins = [i for i in range(11) if tit[i] not in rs or tit.index(tit[i]) != i]
            fo = form.get(tid)
            vagas = [fo[tfi[f"position{i}"]] if fo else 28 for i in range(11)]
            usados = set(tit[i] for i in range(11) if i not in ruins)
            banco = [p for p in ids[11:] if p in rs and p not in usados]
            pool = banco + [p for p in faltam if p not in banco and p not in usados]
            promovidos = {}
            for i in ruins:
                if not pool:
                    tit[i] = -1
                    continue
                melhor = min(pool, key=lambda p: (_custo_pos(attr(p, "preferredposition1"), vagas[i]), -attr(p, "overallrating")))
                pool.remove(melhor)
                tit[i] = melhor
                promovidos[melhor] = vagas[i]
            novos_ids = tit + pool
            if len(novos_ids) > len(pcols):
                self.avisos.append(f"{self.nome_time(tid)}: {len(novos_ids)} jogadores, a escalação só guarda {len(pcols)}.")
            novos_ids = (novos_ids + [-1] * len(pcols))[:len(pcols)]
            for c, p in zip(pcols, novos_ids):
                sheet[tsi[c]] = p
            for l in ment.get(tid, []):
                for i in range(11):
                    k = tmi.get(f"playerid{i}")
                    if k is not None:
                        l[k] = tit[i]
            titulares = [p for p in tit if p in rs]
            if titulares:
                auto = {
                    "captainid": max(titulares, key=lambda p: attr(p, "overallrating")),
                    "penaltytakerid": max(titulares, key=lambda p: attr(p, "penalties") + attr(p, "finishing")),
                    "freekicktakerid": max(titulares, key=lambda p: attr(p, "freekickaccuracy") + attr(p, "curve")),
                    "leftcornerkicktakerid": max(titulares, key=lambda p: attr(p, "crossing") + attr(p, "curve")),
                    "longkicktakerid": next((p for p in titulares if attr(p, "preferredposition1") == 0), titulares[0])}
                auto["leftfreekicktakerid"] = auto["rightfreekicktakerid"] = auto["freekicktakerid"]
                auto["rightcornerkicktakerid"] = auto["leftcornerkicktakerid"]
                for k in COBRADORES:
                    if k in tsi and sheet[tsi[k]] not in rs:
                        sheet[tsi[k]] = auto[k]
                    if tid in times and k in tti and times[tid][tti[k]] not in rs:
                        times[tid][tti[k]] = sheet[tsi[k]] if k in tsi else auto[k]
            for k in tsi:
                if re.fullmatch(r"customsub\d+(in|out)", k) and sheet[tsi[k]] not in rs:
                    sheet[tsi[k]] = -1
            n_banco = 12 if len(novos_ids) >= 23 else 9
            pos_tit = {p: vagas[i] for i, p in enumerate(tit) if p in rs}
            banco_ord = [p for p in novos_ids[11:] if p in rs]
            for l in ls:
                p = l[cp_]
                if p in pos_tit:
                    l[cpos] = pos_tit[p]
                elif l[cpos] < 28 or p in faltam:
                    l[cpos] = 28 if p in banco_ord and banco_ord.index(p) < n_banco else 29
            refeitos.append({"id": tid, "nome": self.nome_time(tid), "entraram": len(faltam), "titulares_trocados": len(promovidos),
                             "jogadores": len(ros)})
            if len(rs) < 11:
                self.avisos.append(f"{self.nome_time(tid)} ficou com {len(rs)} jogador(es) (menos de 11).")
        return refeitos

    # ------------------------------------------------------------------ capacidade e relatório
    def capacidades(self):
        out = {}
        for nome, ls in self.novas.items():
            t = self.te(nome)
            folga = max(t.capacidade - t.validos, 0)
            out[nome] = min(max(t.capacidade, len(ls) + folga), 0xFFFF)
        return out

    def relatorio(self):
        R, B = self.R, self.B
        pes = self.pes_mod
        ea_br = [p for p, vs in self.vinc_ea.items() if any(l[self.ctl["teamid"]] in B for l in vs)]
        clube_novo = [r for r in self.relato_dups if r["tipo"] == "ea" and r.get("dados") == "mod"]
        return {
            "times_brasileiros": len(B), "times_brasileiros_na_ea": len(B & set(self.times_ea)), "times_novos": len(self.novos),
            "jogadores_importados": len(self.importar), "jogadores_mod_ea": len([p for p in self.fonte_mod if p in self.jog_ea]),
            "jogadores_ea_brasileiros": len(ea_br), "jogadores_excluidos": len(self.excluir), "para_livres": len(self.para_livres),
            "duplicados": self.relato_dups, "ids_trocados": [r for r in self.relato_ids if r.get("novo") not in (None, r["mod"])],
            "clube_trocado": clube_novo, "escalacoes": self.escalacoes, "avisos": self.avisos,
            "ligas_do_mod": sorted(self.ligas_do_mod), "competicoes_novas": sorted(getattr(self, "comp_novas", [])),
            "tabelas": {n: [self.te(n).validos, len(ls)] for n, ls in sorted(self.novas.items())},
            "jogadores_finais": len(self.final_jog),
            "excluidos_amostra": [self.pes_ea[p].nome for p in sorted(self.excluir)[:40]],
            "importados_amostra": [pes[p].nome for p in self.importar[:40]],
        }
