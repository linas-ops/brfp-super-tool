"""Criador de Ligas e Times — fichas do mesmo jogador em outros jogos (sofifa e PES).

sofifa (FIFA 15 a FC 24): o site e a API do sofifa.com ficam atrás do Cloudflare ("confirme que é humano") e recusam
programas, então a busca usa a base pública raspada do próprio sofifa ("EA Sports FC 24 complete player dataset": 180 mil
fichas, uma por jogador e edição, com o ID da EA, posições, pé, perna ruim, dribles, físico e os 34 atributos). Ela é
baixada uma vez (96 MB, conferida pelo SHA-256), vira um SQLite em dados\\sofifa e a busca roda no computador, sem limite.
Dá para juntar outras edições importando um CSV no mesmo formato (ex.: os do Kaggle, players_22.csv…).

PES (pesdb.net: eFootball e PES 2016 a 2021): busca pelo nome no site, da edição mais nova para a mais velha, até achar.
Cada busca e cada ficha ficam em dados\\pes_cache. Os atributos do PES viram os do FC por uma conversão calibrada com o
mesmo jogador no PES 2021 e no FIFA 21 (calibracao_pes.json).

Uma ficha encontrada vira, no jogador novo: o playerid da EA (sofifa, se estiver livre no banco), posição e posições
secundárias, pé, perna ruim, dribles, altura, peso e os atributos. A nota é a da ficha quando ela é recente (até 1 ano);
numa ficha antiga, a nota estimada pelo Criador com o perfil de atributos da ficha (forças e fraquezas do jogador).
"""
import csv
import datetime
import gzip
import hashlib
import html
import io
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import casamento as K

AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.environ.get("BRFP_DADOS") or os.path.join(os.path.dirname(os.path.dirname(AQUI)), "dados")
PASTA_SOFIFA = os.path.join(DADOS, "sofifa")
BASE_SOFIFA = os.path.join(PASTA_SOFIFA, "sofifa.sqlite")
PASTA_PES = os.path.join(DADOS, "pes_cache")
BASE_PES = os.path.join(DADOS, "pes", "pes2021.sqlite")
CALIBRACAO_PES = os.path.join(AQUI, "calibracao_pes.json")
UA = "BRFP-Super-Tool"

# a base pública do sofifa (CSV do Kaggle "EA Sports FC 24 complete player dataset", espelhado no Hugging Face). A 2ª
# fonte é o mesmo autor, FIFA 15 a 23, caso a 1ª saia do ar.
FONTES_SOFIFA = [
    {"nome": "FIFA 15 a FC 24 (EA Sports FC 24 complete player dataset, raspado do sofifa.com)",
     "url": "https://huggingface.co/datasets/Belkin7/fifa24-player-values/resolve/main/male_players.csv",
     "sha256": "fd788f7809a62e9715f0cfa4e45c92a97dd716bd6d64dc48a71a0e86369a0a7e", "tamanho": 96336675},
    {"nome": "FIFA 15 a 23 (FIFA 23 complete player dataset, raspado do sofifa.com)",
     "url": "https://huggingface.co/datasets/jsulz/FIFA23/resolve/main/male_players%20(legacy).csv",
     "sha256": None, "tamanho": 90933390},
]

# atributo do banco -> coluna do CSV do sofifa
ATR_SOFIFA = {
    "acceleration": "movement_acceleration", "sprintspeed": "movement_sprint_speed", "agility": "movement_agility",
    "balance": "movement_balance", "jumping": "power_jumping", "stamina": "power_stamina", "strength": "power_strength",
    "reactions": "movement_reactions", "aggression": "mentality_aggression", "composure": "mentality_composure",
    "interceptions": "mentality_interceptions", "positioning": "mentality_positioning", "vision": "mentality_vision",
    "ballcontrol": "skill_ball_control", "crossing": "attacking_crossing", "dribbling": "skill_dribbling",
    "finishing": "attacking_finishing", "freekickaccuracy": "skill_fk_accuracy", "headingaccuracy": "attacking_heading_accuracy",
    "longpassing": "skill_long_passing", "shortpassing": "attacking_short_passing",
    "defensiveawareness": "defending_marking_awareness", "shotpower": "power_shot_power", "longshots": "power_long_shots",
    "standingtackle": "defending_standing_tackle", "slidingtackle": "defending_sliding_tackle", "volleys": "attacking_volleys",
    "curve": "skill_curve", "penalties": "mentality_penalties", "gkdiving": "goalkeeping_diving",
    "gkhandling": "goalkeeping_handling", "gkkicking": "goalkeeping_kicking", "gkreflexes": "goalkeeping_reflexes",
    "gkpositioning": "goalkeeping_positioning"}
ATR = list(ATR_SOFIFA)
# posição no sofifa -> código do jogo
POS_SIGLA = {"GK": 0, "SW": 5, "RWB": 2, "RB": 3, "CB": 5, "LB": 7, "LWB": 8, "CDM": 10, "RM": 12, "CM": 14, "LM": 16,
             "CAM": 18, "CF": 21, "RF": 21, "LF": 21, "RW": 23, "ST": 25, "RS": 25, "LS": 25, "LW": 27}
GK_ATR = {"gkdiving", "gkhandling", "gkkicking", "gkreflexes", "gkpositioning"}


def rotulo_sofifa(ver):
    ver = int(ver)
    return f"FIFA {ver:02d}" if ver < 24 else f"FC {ver}"


def _dias(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None


def idade_na(nasc, data):
    n, d = _dias(nasc), _dias(data) if not isinstance(data, datetime.date) else data
    if not n or not d:
        return None
    return d.year - n.year - ((d.month, d.day) < (n.month, n.day))


def _int(v):
    try:
        return int(float(str(v).split("+")[0].split("-")[0])) if str(v).strip() not in ("", "nan") else None
    except ValueError:
        return None


# ------------------------------------------------------------------ nomes
def _tk(*textos):
    return K.significativas(K.tokens(*textos))


def _iniciais(*textos):
    """Iniciais soltas ("R. Veiga" -> {"r"})."""
    out = set()
    for t in textos:
        out |= {w for w in K.norm(t).split() if len(w) == 1}
    return out


def nome_compativel(nome_outro, j):
    """Força (0..1) de o nome da ficha ("R. Veiga", "Raphael Cavalcante Veiga", "EVERTON RIBEIRO") ser o do jogador da
    fonte (nome, primeiro, sobrenome). Toda palavra da ficha tem de ter uma parecida no nome da fonte; as iniciais têm de
    bater com o começo de alguma palavra; uma palavra comum só ("Silva") não basta."""
    fonte = _tk(j.get("nome"), j.get("primeiro"), j.get("sobrenome"), j.get("nome_completo"))
    exib = _tk(K._sem_inicial(j.get("nome") or ""))
    if not fonte:
        return 0.0
    outro = _tk(K._sem_inicial(nome_outro))
    inic = _iniciais(nome_outro)
    if not outro:
        return 0.0
    bate = K._batem(outro, fonte)
    if bate < len(outro):                          # sobra palavra na ficha que não está no nome da fonte
        if len(outro) >= 3 and bate >= len(outro) - 1 and exib and K._batem(exib, outro) == len(exib):
            return 0.75                                # nome completo da ficha com um sobrenome a mais
        return 0.0
    if inic and not all(any(w.startswith(i) for w in K.tokens(j.get("nome"), j.get("primeiro"), j.get("nome_completo"))) for i in inic):
        return 0.0
    exib_bate = K._batem(exib, outro) if exib else 0
    if len(outro) >= 2:
        return 0.95 if exib and exib_bate == len(exib) else 0.85
    w = next(iter(outro))
    if exib and exib == {w} or (len(exib) == 1 and K._parecida(next(iter(exib)), w)):
        return 0.85 if len(w) >= 4 else 0.7            # nome de uma palavra só: o mesmo que a fonte mostra
    return 0.6 if inic else 0.45


def _nac_igual(a, b):
    na, nb = K.norm(a), K.norm(b)
    na, nb = K.ALIAS_NACOES.get(na, na), K.ALIAS_NACOES.get(nb, nb)
    return bool(na) and na == nb


def nacoes_fonte(j):
    return [x for x in [j.get("nacionalidade"), *(j.get("nacionalidades") or []), j.get("pais_nascimento")] if x]


# ------------------------------------------------------------------ sofifa
class BaseSofifa:
    """A base do sofifa em SQLite: uma linha por jogador e edição + o índice de palavras do nome."""

    def __init__(self, caminho=BASE_SOFIFA):
        self.caminho = caminho
        self._con = None
        self._estado = None
        self._lock = threading.RLock()

    # ---- estado e instalação
    def existe(self):
        return os.path.isfile(self.caminho)

    def con(self):
        with self._lock:
            if self._con is None:
                if not self.existe():
                    return None
                self._con = sqlite3.connect(self.caminho, check_same_thread=False)
            return self._con

    def fechar(self):
        with self._lock:
            if self._con is not None:
                self._con.close()
                self._con = None
            self._estado = None

    def estado(self):
        if self._estado is not None:
            return self._estado
        c = self.con()
        if c is None:
            return {"baixada": False}
        try:
            with self._lock:
                vs = c.execute("SELECT ver, COUNT(*) FROM fichas GROUP BY ver ORDER BY ver").fetchall()
                nj = c.execute("SELECT COUNT(*) FROM jogadores").fetchone()[0]
                meta = dict(c.execute("SELECT chave, valor FROM meta").fetchall())
        except sqlite3.Error as ex:
            return {"baixada": False, "erro": str(ex)}
        self._estado = {"baixada": True, "versoes": [{"ver": v, "nome": rotulo_sofifa(v), "fichas": n} for v, n in vs],
                        "fichas": sum(n for _, n in vs), "jogadores": nj, "origem": meta.get("origem"),
                        "tamanho": os.path.getsize(self.caminho)}
        return self._estado

    def baixar(self, progresso=None):
        """Baixa a base (a 1ª fonte que responder), confere o SHA-256 e monta o SQLite."""
        os.makedirs(PASTA_SOFIFA, exist_ok=True)
        erros = []
        for f in FONTES_SOFIFA:
            tmp = os.path.join(PASTA_SOFIFA, "download.csv.part")
            try:
                h = hashlib.sha256()
                feito = 0
                req = urllib.request.Request(f["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as out:
                    total = int(r.headers.get("Content-Length") or f.get("tamanho") or 0)
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        out.write(b)
                        h.update(b)
                        feito += len(b)
                        if progresso:
                            progresso(f"Baixando a base do sofifa… {feito / 1e6:.0f} de {total / 1e6:.0f} MB", feito, total)
                if f.get("sha256") and h.hexdigest() != f["sha256"]:
                    raise ValueError("o arquivo baixado não confere (SHA-256 diferente)")
                if progresso:
                    progresso("Montando a base do sofifa…", 0, 0)
                n = self.montar([tmp], f["nome"], substituir=True)
                return {"fichas": n, "origem": f["nome"]}
            except (OSError, ValueError, urllib.error.URLError) as ex:
                erros.append(f"{f['nome']}: {ex}")
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        raise ValueError("Não consegui baixar a base do sofifa. " + " · ".join(erros))

    def montar(self, csvs, origem, substituir=False):
        """CSV(s) no formato do sofifa (player_id ou sofifa_id; fifa_version ou o número no nome do arquivo:
        players_22.csv) -> SQLite. substituir=False junta à base que já existe (a mesma edição é trocada)."""
        os.makedirs(os.path.dirname(self.caminho), exist_ok=True)
        novo = self.caminho + ".novo"
        if os.path.exists(novo):
            os.remove(novo)
        if not substituir and self.existe():
            self.fechar()
            with open(self.caminho, "rb") as a, open(novo, "wb") as b:
                b.write(a.read())
        con = sqlite3.connect(novo)
        con.executescript(f"""
            CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE IF NOT EXISTS fichas (pid INTEGER, ver INTEGER, data TEXT, curto TEXT, longo TEXT, nasc TEXT,
                nac TEXT, clube TEXT, liga TEXT, pos TEXT, ov INTEGER, pot INTEGER, pe INTEGER, pr INTEGER, dri INTEGER,
                alt INTEGER, peso INTEGER, rep INTEGER, {", ".join(a + " INTEGER" for a in ATR)}, PRIMARY KEY (pid, ver));
            CREATE TABLE IF NOT EXISTS jogadores (pid INTEGER PRIMARY KEY, nasc TEXT, nomes TEXT);
            CREATE TABLE IF NOT EXISTS palavras (palavra TEXT, pid INTEGER);
        """)
        cols = ["pid", "ver", "data", "curto", "longo", "nasc", "nac", "clube", "liga", "pos", "ov", "pot", "pe", "pr", "dri",
                "alt", "peso", "rep"] + ATR
        sql = f"INSERT OR REPLACE INTO fichas ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        n = 0
        for caminho in csvs:
            m = re.search(r"(?:players|fifa)_?(\d\d)\b", os.path.basename(caminho), re.I)
            ver_arq = int(m.group(1)) if m else None
            with open(caminho, encoding="utf-8", newline="") as f:
                r = csv.DictReader(f)
                campos = set(r.fieldnames or [])
                if not ({"player_id", "sofifa_id"} & campos) or "overall" not in campos:
                    raise ValueError(f"{os.path.basename(caminho)} não está no formato do sofifa (faltam player_id/sofifa_id e overall).")
                lote = []
                for d in r:
                    if (d.get("gender") or "").lower() in ("female", "f", "1"):
                        continue
                    pid = _int(d.get("player_id") or d.get("sofifa_id"))
                    ver = _int(d.get("fifa_version")) or ver_arq
                    if not pid or not ver:
                        continue
                    data = (d.get("update_as_of") or d.get("fifa_update_date") or "")[:10] or f"{2000 + ver - 1}-09-15"
                    pe = 2 if (d.get("preferred_foot") or "").lower().startswith("l") else 1
                    lote.append([pid, ver, data, d.get("short_name") or "", d.get("long_name") or "", (d.get("dob") or "")[:10],
                                 d.get("nationality_name") or d.get("nationality") or "", d.get("club_name") or "",
                                 d.get("league_name") or "", d.get("player_positions") or "", _int(d.get("overall")),
                                 _int(d.get("potential")), pe, _int(d.get("weak_foot")), _int(d.get("skill_moves")),
                                 _int(d.get("height_cm")), _int(d.get("weight_kg")), _int(d.get("international_reputation"))]
                                + [_int(d.get(ATR_SOFIFA[a])) for a in ATR])
                    if len(lote) >= 5000:
                        con.executemany(sql, lote)
                        n += len(lote)
                        lote = []
                con.executemany(sql, lote)
                n += len(lote)
        # índice de nomes: um registro por jogador (nascimento + todas as grafias do nome nas edições)
        con.executescript("DELETE FROM jogadores; DELETE FROM palavras;")
        nomes = {}
        for pid, nasc, curto, longo in con.execute("SELECT pid, nasc, curto, longo FROM fichas ORDER BY ver"):
            a = nomes.setdefault(pid, [nasc, set()])
            a[0] = nasc or a[0]
            a[1].update(x for x in (curto, longo) if x)
        con.executemany("INSERT INTO jogadores VALUES (?, ?, ?)", ((pid, a[0], " | ".join(sorted(a[1]))) for pid, a in nomes.items()))
        con.executemany("INSERT INTO palavras VALUES (?, ?)", ((w, pid) for pid, a in nomes.items() for w in _tk(*a[1])))
        con.executescript("""
            CREATE INDEX IF NOT EXISTS i_palavra ON palavras (palavra);
            CREATE INDEX IF NOT EXISTS i_nasc ON jogadores (nasc);
        """)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('origem', ?)", (origem,))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('montada', ?)", (datetime.datetime.now().isoformat(timespec="seconds"),))
        con.commit()
        con.close()
        self.fechar()
        os.replace(novo, self.caminho)
        return n

    # ---- busca
    def buscar(self, j, clube=None, hoje=None, ref=None):
        """[(nota, pid, ficha)] dos jogadores do sofifa que podem ser este, o melhor primeiro. A ficha é a mais recente;
        num elenco antigo (ref = fim da temporada), a da edição daquela época.

        Com o nascimento: o mesmo dia e o nome compatível (forte); um nome bem parecido com o nascimento a até 1 ano
        (dia e mês trocados, erro de digitação) fica "confira". Sem nascimento: o nome forte + a idade na edição (±1) e
        a mesma nacionalidade."""
        c = self.con()
        if c is None:
            return []
        hoje = hoje or datetime.date.today()
        tks = _tk(j.get("nome"), j.get("primeiro"), j.get("sobrenome"), j.get("nome_completo"))
        nasc = (j.get("nascimento") or "")[:10] or None
        with self._lock:
            pids = set()
            for w in tks:
                pids |= {p for (p,) in c.execute("SELECT pid FROM palavras WHERE palavra = ?", (w,))}
            if nasc:
                pids |= {p for (p,) in c.execute("SELECT pid FROM jogadores WHERE nasc = ?", (nasc,))}
            if not pids:
                return []
            info = {}
            for pid_lote in _lotes(sorted(pids), 500):
                for pid, jn, nomes in c.execute(f"SELECT pid, nasc, nomes FROM jogadores WHERE pid IN ({','.join('?' * len(pid_lote))})", pid_lote):
                    info[pid] = (jn, nomes)
        nacs = nacoes_fonte(j)
        out = []
        for pid, (jn, nomes) in info.items():
            fn = max((nome_compativel(n, j) for n in nomes.split(" | ")), default=0.0)
            if nasc and jn:
                if jn == nasc:
                    if fn < 0.45:
                        continue                               # mesmo dia, nome de outra pessoa
                    sc = 0.9 + 0.1 * fn
                else:
                    d = abs((_dias(jn) - _dias(nasc)).days) if _dias(jn) and _dias(nasc) else 9999
                    if fn < 0.85 or d > 400:
                        continue
                    sc = 0.7
            else:
                if fn < 0.85:
                    continue
                sc = 0.6 + 0.2 * fn
            out.append([sc, pid])
        if not out:
            return []
        res = []
        for sc, pid in sorted(out, reverse=True)[:6]:
            f = self.ficha(pid, ref=ref)
            if not f:
                continue
            if nacs and f["nacionalidade"]:
                sc += 0.05 if any(_nac_igual(f["nacionalidade"], x) for x in nacs) else -0.2
            if not nasc:                                     # idade na edição tem de bater
                idade = j.get("idade_hoje", j.get("idade"))
                if idade is None or f.get("idade") is None:
                    sc -= 0.2
                else:
                    anos = ((ref or hoje) - _dias(f["data"])).days / 365.25 if _dias(f["data"]) else 0
                    if abs(f["idade"] + anos - idade) > 1.6:
                        continue
            if clube and f.get("clube") and K.nota_time(clube, f["clube"]) >= 0.8:
                sc += 0.05
            sc = round(min(1.0, sc), 3)
            f["nota"], f["forte"] = sc, sc >= 0.9 and bool(nasc)
            if sc >= 0.6:
                res.append((sc, pid, f))
        res.sort(key=lambda x: -x[0])
        return res

    def ficha(self, pid, ver=None, ref=None):
        """A ficha do jogador numa edição (sem ver: a mais recente; com ref, a mais nova lançada até ~4 meses depois
        dessa data, ou a mais antiga), com a lista das edições em que ele aparece."""
        c = self.con()
        if c is None:
            return None
        with self._lock:
            cur = c.execute("SELECT * FROM fichas WHERE pid = ? ORDER BY ver DESC", (int(pid),))
            cols = [x[0] for x in cur.description]
            linhas = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not linhas:
            return None
        d = next((x for x in linhas if ver and x["ver"] == int(ver)), None)
        if d is None and ref and not ver:
            ate = ref + datetime.timedelta(days=120)
            d = next((x for x in linhas if _dias(x["data"]) and _dias(x["data"]) <= ate), linhas[-1])
        d = d or linhas[0]
        posicoes = [POS_SIGLA[p.strip()] for p in (d["pos"] or "").split(",") if p.strip() in POS_SIGLA]
        posicoes = list(dict.fromkeys(posicoes))
        atr = {a: d[a] for a in ATR if d.get(a) is not None}
        return {"fonte": "sofifa", "versao": rotulo_sofifa(d["ver"]), "ver": d["ver"], "data": d["data"], "id": int(pid),
                "nome": d["curto"] or d["longo"], "nome_completo": d["longo"], "nascimento": d["nasc"] or None,
                "idade": idade_na(d["nasc"], d["data"]), "nacionalidade": d["nac"], "clube": d["clube"], "liga": d["liga"],
                "overall": d["ov"], "potential": d["pot"], "pos": posicoes[0] if posicoes else None, "posicoes2": posicoes[1:4],
                "pe": d["pe"], "perna_ruim": d["pr"], "dribles": d["dri"], "altura": d["alt"], "peso": d["peso"],
                "atr": atr, "url": f"https://sofifa.com/player/{pid}",
                "versoes": [{"ver": x["ver"], "versao": rotulo_sofifa(x["ver"]), "overall": x["ov"], "clube": x["clube"]} for x in linhas]}


def _lotes(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


_SOFIFA = BaseSofifa()


def sofifa():
    return _SOFIFA


# ------------------------------------------------------------------ PES (pesdb.net)
# edições com o modelo de atributos de hoje (o PES 2015 e os de antes medem outras coisas), da mais nova à mais velha;
# data: quando a idade e o elenco da edição valem
VERSOES_PES = [("efootball", "eFootball", None), ("pes2021", "PES 2021", "2020-09-15"), ("pes2020", "PES 2020", "2019-09-10"),
               ("pes2019", "PES 2019", "2018-08-30"), ("pes2018", "PES 2018", "2017-09-12"), ("pes2017", "PES 2017", "2016-09-15"),
               ("pes2016", "PES 2016", "2015-09-15")]
NOME_VERSAO_PES = {k: n for k, n, _ in VERSOES_PES}
DATA_VERSAO_PES = {k: d for k, _, d in VERSOES_PES}
# nome do atributo no pesdb (todas as edições) -> chave única
CANON_PES = {
    "offensive awareness": "ataque", "attacking awareness": "ataque", "attacking prowess": "ataque",
    "ball control": "controle", "dribbling": "drible", "tight possession": "conducao", "low pass": "passe_baixo",
    "lofted pass": "passe_alto", "finishing": "finalizacao", "heading": "cabeceio", "header": "cabeceio",
    "place kicking": "bola_parada", "set piece taking": "bola_parada", "curl": "curva", "swerve": "curva",
    "defensive awareness": "defesa", "defensive prowess": "defesa", "ball winning": "desarme", "tackling": "desarme",
    "aggression": "agressividade", "defensive engagement": "engajamento", "gk awareness": "gk_consciencia",
    "goalkeeping": "gk_consciencia", "gk catching": "gk_pegada", "gk catch": "gk_pegada", "catching": "gk_pegada",
    "gk clearing": "gk_afastar", "clearing": "gk_afastar", "gk parrying": "gk_afastar", "gk reflexes": "gk_reflexos",
    "reflexes": "gk_reflexos", "gk reach": "gk_alcance", "coverage": "gk_alcance", "speed": "velocidade",
    "acceleration": "aceleracao", "explosive power": "aceleracao", "kicking power": "potencia", "jump": "impulsao",
    "jumping": "impulsao", "physical contact": "contato", "balance": "equilibrio", "unwavering balance": "equilibrio",
    "body control": "equilibrio", "body balance": "equilibrio", "stamina": "resistencia", "weak foot usage": "pr_uso",
    "weak foot accuracy": "pr_precisao", "form": "forma", "injury resistance": "lesao"}
POS_PES = {"GK": 0, "CB": 5, "LB": 7, "RB": 3, "DMF": 10, "CMF": 14, "LMF": 16, "RMF": 12, "AMF": 18, "LWF": 27, "RWF": 23,
           "SS": 21, "CF": 25}
# habilidades de drible do PES (contam para as estrelas de dribles)
TRUQUES_PES = {"scissors feint", "double touch", "flip flap", "marseille turn", "sombrero", "chop turn", "cut behind turn",
               "cut behind & turn", "scotch move", "step on skill control", "sole control", "rabona", "cross over turn",
               "heel trick", "no look pass", "sole flick turn", "dummy run", "flip flap", "cut behind and turn"}


class ErroPes(Exception):
    pass


class PesDb:
    """Busca e fichas do pesdb.net, com cache e um intervalo entre os pedidos. O site aguenta rajadas curtas (~1 pedido
    por segundo por uns minutos), mas depois de ~150 seguidos responde 429 por vários minutos; com 2 s entre os pedidos
    ele não bloqueia. O 429 traz o tempo de espera (Retry-After), que é respeitado."""
    INTERVALO = 2.0
    ESPERA_MAX = 600                                          # mais que isso: para e avisa (a busca continua depois)

    def __init__(self, pasta=PASTA_PES):
        self.pasta = pasta
        self._ultimo = 0.0
        self._lock = threading.Lock()
        self.pedidos = 0
        self.ao_esperar = None                               # avisa a tela quando o site pede para esperar

    def _cache(self, url, validade_dias):
        arq = os.path.join(self.pasta, hashlib.sha1(url.encode()).hexdigest()[:24] + ".json")
        if os.path.isfile(arq) and (validade_dias is None or time.time() - os.path.getmtime(arq) < validade_dias * 86400):
            try:
                with open(arq, encoding="utf-8") as f:
                    return arq, json.load(f)
            except (OSError, ValueError):
                pass
        return arq, None

    def _gravar(self, arq, v):
        os.makedirs(self.pasta, exist_ok=True)
        with open(arq + ".tmp", "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False)
        os.replace(arq + ".tmp", arq)

    def _get(self, url):
        for tentativa in range(4):
            with self._lock:
                espera = self.INTERVALO - (time.time() - self._ultimo)
                if espera > 0:
                    time.sleep(espera)
                self._ultimo = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    self.pedidos += 1
                    return r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as ex:
                if ex.code == 404:
                    return ""
                if ex.code == 429 and tentativa < 3:          # muitos pedidos: espera o que o site pede
                    try:
                        espera = int(ex.headers.get("Retry-After") or 0) + 2
                    except ValueError:
                        espera = 0
                    espera = max(espera, 60 * (tentativa + 1))
                    if espera > self.ESPERA_MAX:
                        raise ErroPes(f"o pesdb.net pediu uma pausa de {espera // 60} min (limite de pedidos); "
                                      "o que já foi achado fica, e a busca continua de onde parou depois") from None
                    if self.ao_esperar:
                        self.ao_esperar(espera)
                    with self._lock:
                        time.sleep(espera)
                        self._ultimo = time.time()
                    continue
                if ex.code == 429:
                    raise ErroPes("o pesdb.net continua recusando (limite de pedidos); o que já foi achado fica, e a busca "
                                  "continua de onde parou depois") from None
                if ex.code in (500, 502, 503, 504) and tentativa < 3:
                    time.sleep(3 * (tentativa + 1))
                    continue
                raise ErroPes(f"pesdb.net respondeu {ex.code}") from None
            except (urllib.error.URLError, OSError) as ex:
                if tentativa < 3:
                    time.sleep(2 * (tentativa + 1))
                    continue
                raise ErroPes(f"pesdb.net não respondeu: {ex}") from None
        raise ErroPes("pesdb.net não respondeu")

    # ---- páginas
    def busca(self, versao, nome, extra=None):
        """[{id, url, nome, pos, nacionalidade, clube, overall}] da busca por nome (até 24, os de nota maior primeiro)."""
        q = {"name": nome, **(extra or {})}
        if versao == "efootball":
            q["type"] = "standard"                           # a carta "normal" do jogador (sem as especiais)
        url = f"https://pesdb.net/{versao}/players/?{urllib.parse.urlencode(q)}"
        arq, v = self._cache(url, 7 if versao == "efootball" else 60)
        if v is not None:
            return v
        h = self._get(url)
        out = []
        for m in re.finditer(r'<a class="player-result-link" href="(/' + versao + r'/players/[^"]+-(\d+))">(.*?)</article>', h, re.S):
            bloco = m.group(3)
            meta = [html.unescape(x).strip() for x in re.findall(r'<span class="meta-item">([^<]*)</span>', bloco)]
            nm = re.search(r"<h3>([^<]*)</h3>", bloco)
            ps = re.search(r'<span class="position">([^<]*)</span>', bloco)
            ov = re.search(r"<span>OVR</span><strong>(\d+)</strong>", bloco)
            out.append({"id": m.group(2), "url": "https://pesdb.net" + m.group(1), "nome": html.unescape(nm.group(1)).strip() if nm else "",
                        "pos": ps.group(1).strip() if ps else "", "nacionalidade": meta[0] if meta else "",
                        "clube": meta[1] if len(meta) > 1 else "", "overall": int(ov.group(1)) if ov else None})
        total = re.search(r'<p aria-live="polite">([\d,]+) results?</p>', h)
        res = {"jogadores": out, "total": int(total.group(1).replace(",", "")) if total else len(out)}
        self._gravar(arq, res)
        return res

    def jogador(self, url):
        """Ficha do pesdb: nome, posição, posições, nação, clube, nota, altura, peso, idade, pé, atributos (chaves de
        CANON_PES), habilidades."""
        efoot = "/efootball/" in url
        arq, v = self._cache(url, 7 if efoot else None)
        if v is not None:
            return v
        h = self._get(url)
        if not h:
            return None
        d = {"url": url, "id": re.search(r"-(\d+)$", url).group(1), "versao": url.split("/")[3]}
        nm = re.search(r'<h1 id="player-name">([^<]*)</h1>', h)
        d["nome"] = html.unescape(nm.group(1)).strip() if nm else ""
        det = {}
        for k, val in re.findall(r"<dt>([^<]+)</dt>\s*<dd[^>]*>(.*?)</dd>", h, re.S):
            k = html.unescape(k).strip().lower()
            if k not in det:
                det[k] = html.unescape(re.sub(r"<[^>]+>", "", val)).strip()
        d["nacionalidade"] = det.get("nationality") or ""
        d["clube"] = det.get("club") or ""
        d["overall"] = _int(det.get("overall rating"))
        d["altura"] = _int(re.sub(r"\D", "", det.get("height") or ""))
        d["peso"] = _int(re.sub(r"\D", "", det.get("weight") or ""))
        d["idade"] = _int(det.get("age"))
        d["pe"] = 2 if (det.get("stronger foot") or "").lower().startswith("left") else 1
        d["tipo_carta"] = det.get("card type")
        pri = det.get("primary position") or ""
        sec = [x.strip() for x in (det.get("secondary positions") or "").split(",") if x.strip()]
        d["posicao"] = pri.strip()
        d["posicoes2"] = [x for x in sec if x != d["posicao"]]
        atr = {}
        # só os "Base Stats" (no eFootball, a progressão vem depois e repete os nomes)
        base = h.split('data-player-mode="progression"')[0] if efoot else h
        base_ini = base.find("ability-group")
        for k, val in re.findall(r'<div class="ability-row">\s*<span>([^<]+)</span>\s*<strong[^>]*>(.*?)</strong>', base[base_ini:], re.S):
            ck = CANON_PES.get(html.unescape(k).strip().lower())
            if not ck or ck in atr:
                continue
            num = re.search(r"\?[a-z_]+=(\d+)", val)               # características: o número está no link
            txt = re.sub(r"<[^>]+>", "", val).strip()
            atr[ck] = int(num.group(1)) if num and not txt.isdigit() else _int(txt)
        for k in ("pr_uso", "pr_precisao", "forma", "lesao"):          # eFootball dá as características por extenso
            if k not in atr:
                kk = {"pr_uso": "weak foot usage", "pr_precisao": "weak foot accuracy", "forma": "form", "lesao": "injury resistance"}[k]
                m = re.search(r"<dt>" + kk.title() + r"</dt>\s*<dd[^>]*>.*?\?[a-z_]+=(\d+)", h, re.S | re.I)
                if m:
                    atr[k] = int(m.group(1)) + 1                     # eFootball conta de 0
        d["atr"] = {k: v for k, v in atr.items() if v is not None}
        sk = re.search(r"<h2>Player Skills</h2>(.*?)</section>", h, re.S)
        d["habilidades"] = [html.unescape(x).strip() for x in re.findall(r">([^<>]+)</a>", sk.group(1))] if sk else []
        self._gravar(arq, d)
        return d

    # ---- casamento
    MAX_VERSOES = 3                                           # edições tentadas por jogador

    def buscar(self, j, versoes=None, clube=None, hoje=None, progresso=None, ref=None):
        """A ficha do jogador numa das edições escolhidas: as mais próximas da temporada do elenco (ref; sem ela, hoje)
        primeiro, no máximo MAX_VERSOES, parando na primeira que bate com segurança. Por edição, 1 busca pelo nome
        (2 se a primeira não achar ninguém) e a página dos candidatos. {"ficha": dict|None, "buscado": [versões]}."""
        hoje = hoje or datetime.date.today()
        ref = ref or hoje
        versoes = [v for v, _, _ in VERSOES_PES if v in (versoes or NOME_VERSAO_PES)]
        versoes.sort(key=lambda v: abs(((_dias(DATA_VERSAO_PES[v]) or hoje) - ref).days))
        versoes = versoes[:self.MAX_VERSOES]
        nome = (j.get("nome") or "").strip()
        tks = [w for w in K.norm(K._sem_inicial(nome)).split() if len(w) >= 2 and w not in K.PARTICULAS]
        if not tks:
            tks = [w for w in K.norm(f"{j.get('primeiro') or ''} {j.get('sobrenome') or ''}").split() if len(w) >= 2]
        if not tks:
            return {"ficha": None, "buscado": []}
        nacs = nacoes_fonte(j)
        buscado = []
        talvez = None
        for v in versoes:
            if progresso:
                progresso(NOME_VERSAO_PES[v])
            buscado.append(v)
            # eFootball: o nome inteiro ("Samuel Lino"); PES antigo ("S. LINO"): o sobrenome, só entre os da nação
            # (sem ninguém: em todas). Sem ninguém ainda, o primeiro nome ("EVERTON" de "Everton Ribeiro").
            if v == "efootball":
                pedidos = [(" ".join(tks), None), (tks[-1], None)]
            else:
                pedidos = ([(tks[-1], {"nationality": nacs[0].upper()})] if nacs else []) + [(tks[-1], None)]
            if len(tks) >= 2:
                pedidos.append((tks[0], {"nationality": nacs[0].upper()} if nacs and v != "efootball" else None))
            vistos, feitos = {}, set()
            for termo, extra in pedidos:                  # no máximo 2 buscas por edição
                if (termo, repr(extra)) in feitos or len(feitos) >= 2:
                    continue
                feitos.add((termo, repr(extra)))
                for x in self.busca(v, termo, extra)["jogadores"]:
                    vistos.setdefault(x["url"], x)
                if any(nome_compativel(x["nome"], j) >= 0.6 for x in vistos.values()):
                    break
            cands = []
            for x in vistos.values():
                fn = nome_compativel(x["nome"], j)
                if fn < 0.6:
                    continue
                sc = 0.45 + 0.35 * fn
                if nacs and x.get("nacionalidade"):
                    sc += 0.08 if any(_nac_igual(x["nacionalidade"], n) for n in nacs) else -0.25
                if clube and x.get("clube") and K.nota_time(clube, x["clube"]) >= 0.8:
                    sc += 0.08
                cands.append((sc, x))
            cands.sort(key=lambda c: -c[0])
            for sc, x in cands[:3]:
                if sc < 0.6:
                    break
                p = self.jogador(x["url"])
                if not p:
                    continue
                data = _dias(DATA_VERSAO_PES[v]) or hoje
                if j.get("nascimento") and p.get("idade") is not None:
                    esperada = idade_na(j["nascimento"], data)
                    if esperada is None or abs(esperada - p["idade"]) > 1:
                        continue
                    sc += 0.15
                elif p.get("idade") is not None and j.get("idade") is not None:
                    anos = (hoje - data).days / 365.25
                    if abs(p["idade"] + anos - j.get("idade_hoje", j["idade"])) > 1.6:
                        continue
                    sc += 0.05
                sc = round(min(1.0, sc), 3)
                f = ficha_pes(p, v, data)
                f["nota"], f["forte"] = sc, sc >= 0.9 and bool(j.get("nascimento"))
                if sc >= 0.8:
                    return {"ficha": f, "buscado": buscado}
                if not talvez or sc > talvez["nota"]:
                    talvez = f
        return {"ficha": talvez, "buscado": buscado}


# ------------------------------------------------------------------ PES 2021 no computador (patch VirtuaRED)
# Todos os jogadores do PES 2021 com o patch VirtuaRED (elencos da temporada atual), do projeto PESXplorer (licença MIT):
# um JSON de ~95 MB, baixado uma vez e guardado em SQLite. Sem nascimento (só a idade na data do patch).
REPO_PES = "xyzsteven/PESXplorer"
FONTE_PES = {"sha": "4661012e0080f8282e13f3c9c09e4612109aee49", "data": "2026-10-18", "patch": "v10.3",
             "sha256": "0958c0522e7d359d8c7828ac0503a51997f02c2666850e2b7ae699aed2dcdf9a"}
VR_CANON = {"offensive_awareness": "ataque", "ball_control": "controle", "dribbling": "drible", "tight_possession": "conducao",
            "low_pass": "passe_baixo", "lofted_pass": "passe_alto", "finishing": "finalizacao", "heading": "cabeceio",
            "place_kicking": "bola_parada", "curl": "curva", "speed": "velocidade", "acceleration": "aceleracao",
            "kicking_power": "potencia", "jump": "impulsao", "physical_contact": "contato", "balance": "equilibrio",
            "stamina": "resistencia", "defensive_awareness": "defesa", "ball_winning": "desarme", "aggression": "agressividade",
            "gk_awareness": "gk_consciencia", "gk_catching": "gk_pegada", "gk_clearing": "gk_afastar",
            "gk_reflexes": "gk_reflexos", "gk_reach": "gk_alcance", "weak_foot_usage": "pr_uso",
            "weak_foot_acc": "pr_precisao", "form": "forma", "injury_resistance": "lesao"}
VR_POS = ["GK", "CB", "LB", "RB", "DMF", "CMF", "LMF", "RMF", "AMF", "LWF", "RWF", "SS", "CF"]
VERSAO_VR = "pes2021vr"
NOME_VERSAO_PES[VERSAO_VR] = "PES 2021 VR"                 # VR: o patch VirtuaRED


class BasePes:
    """O PES 2021 (patch VirtuaRED) em SQLite: uma linha por jogador + o índice de palavras do nome."""

    def __init__(self, caminho=BASE_PES):
        self.caminho = caminho
        self._con = None
        self._estado = None
        self._meta = None
        self._lock = threading.RLock()

    def existe(self):
        return os.path.isfile(self.caminho)

    def con(self):
        with self._lock:
            if self._con is None:
                if not self.existe():
                    return None
                self._con = sqlite3.connect(self.caminho, check_same_thread=False)
            return self._con

    def fechar(self):
        with self._lock:
            if self._con is not None:
                self._con.close()
                self._con = None
            self._estado = self._meta = None

    def meta(self):
        if self._meta is None:
            c = self.con()
            if c is None:
                return {}
            with self._lock:
                self._meta = dict(c.execute("SELECT chave, valor FROM meta").fetchall())
        return self._meta

    def estado(self):
        if self._estado is not None:
            return self._estado
        c = self.con()
        if c is None:
            return {"baixada": False}
        try:
            with self._lock:
                n = c.execute("SELECT COUNT(*) FROM jogadores WHERE lenda = 0").fetchone()[0]
                nt = c.execute("SELECT COUNT(DISTINCT clube) FROM jogadores WHERE lenda = 0").fetchone()[0]
            m = self.meta()
        except sqlite3.Error as ex:
            return {"baixada": False, "erro": str(ex)}
        self._estado = {"baixada": True, "jogadores": n, "times": nt, "patch": m.get("patch"), "data": m.get("data"),
                        "origem": m.get("origem"), "tamanho": os.path.getsize(self.caminho)}
        return self._estado

    def baixar(self, progresso=None):
        """Baixa a versão mais nova do players.json do PESXplorer (sem a API do GitHub: a fixada, conferida pelo
        SHA-256) e monta o SQLite."""
        fonte = dict(FONTE_PES)
        try:                                                  # a versão mais nova do arquivo (o patch é atualizado)
            req = urllib.request.Request(f"https://api.github.com/repos/{REPO_PES}/commits?path=players.json&per_page=1",
                                         headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                c = json.load(r)[0]
            if c["sha"] != fonte["sha"]:
                m = re.search(r"v\d+(?:\.\d+)*", c["commit"]["message"])
                fonte = {"sha": c["sha"], "data": c["commit"]["committer"]["date"][:10], "patch": m.group(0) if m else "",
                         "sha256": None}
        except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError):
            pass
        os.makedirs(os.path.dirname(self.caminho), exist_ok=True)
        tmp = self.caminho + ".json.part"
        try:
            h = hashlib.sha256()
            feito = 0
            url = f"https://raw.githubusercontent.com/{REPO_PES}/{fonte['sha']}/players.json"
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r, open(tmp, "wb") as out:
                total = int(r.headers.get("Content-Length") or 95_400_000)
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    out.write(b)
                    h.update(b)
                    feito += len(b)
                    if progresso:
                        progresso(f"Baixando a base do PES… {feito / 1e6:.0f} de {total / 1e6:.0f} MB", feito, total)
            if fonte.get("sha256") and h.hexdigest() != fonte["sha256"]:
                raise ValueError("o arquivo baixado não confere (SHA-256 diferente)")
            if progresso:
                progresso("Montando a base do PES…", 0, 0)
            origem = f"PES 2021 + patch VirtuaRED {fonte['patch']} (PESXplorer, {fonte['data']})".replace("  ", " ")
            n = self.montar(tmp, origem, fonte["data"], fonte["patch"])
            return {"jogadores": n, "origem": origem}
        except (OSError, urllib.error.URLError) as ex:
            raise ValueError(f"Não consegui baixar a base do PES: {ex}") from None
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def montar(self, arq_json, origem, data, patch=""):
        """players.json do PESXplorer -> SQLite (cada jogador vira uma tupla enquanto o JSON é lido: pouca memória)."""
        def compacto(d):
            if "player_id" not in d or "player_name" not in d:
                return d
            atr = {VR_CANON[k]: d[k] for k in VR_CANON if isinstance(d.get(k), int) and not isinstance(d.get(k), bool)}
            hab = [k.replace("_", " ") for k, v in d.items() if v is True and k not in ("foot", "legend", "hand")]
            rp = d.get("registered_position")
            pos = d.get("position_name") or (VR_POS[rp] if isinstance(rp, int) and 0 <= rp < len(VR_POS) else "")
            sec = [p for p in VR_POS if d.get(p.lower()) == 2 and p != pos]
            return (int(d["player_id"]), d["player_name"], d.get("team_name") or "", d.get("country_name") or "",
                    _int(d.get("age")), pos, ",".join(sec), _int(d.get("overall_rating")), 2 if d.get("foot") is True else 1,
                    _int(d.get("height")), _int(d.get("weight")), 1 if d.get("legend") else 0,
                    json.dumps(atr, separators=(",", ":")), "|".join(hab))
        with open(arq_json, encoding="utf-8") as f:
            linhas = json.load(f, object_hook=compacto)
        if not isinstance(linhas, list) or not linhas or not isinstance(linhas[0], tuple):
            raise ValueError("o arquivo não está no formato do PESXplorer (lista de jogadores com player_id)")
        os.makedirs(os.path.dirname(self.caminho), exist_ok=True)
        novo = self.caminho + ".novo"
        if os.path.exists(novo):
            os.remove(novo)
        con = sqlite3.connect(novo)
        con.executescript("""
            CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE jogadores (pid INTEGER PRIMARY KEY, nome TEXT, clube TEXT, nac TEXT, idade INTEGER, pos TEXT,
                sec TEXT, ovr INTEGER, pe INTEGER, alt INTEGER, peso INTEGER, lenda INTEGER, atr TEXT, hab TEXT);
            CREATE TABLE palavras (palavra TEXT, pid INTEGER);
        """)
        con.executemany("INSERT OR REPLACE INTO jogadores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", linhas)
        con.executemany("INSERT INTO palavras VALUES (?, ?)", ((w, x[0]) for x in linhas if not x[11] for w in _tk(x[1])))
        con.execute("CREATE INDEX i_palavra ON palavras (palavra)")
        con.executemany("INSERT INTO meta VALUES (?, ?)", [("origem", origem), ("data", data), ("patch", patch),
                                                            ("data_idade", self._data_idade(con, data)),
                                                            ("montada", datetime.datetime.now().isoformat(timespec="seconds"))])
        con.commit()
        con.close()
        self.fechar()
        os.replace(novo, self.caminho)
        return len(linhas)

    @staticmethod
    def _data_idade(con, data):
        """A data em que valem as idades do PES (no patch 10.x, 1º de janeiro de 2026, mesmo no de outubro): o 1º do mês
        em que mais idades batem com os nascimentos do sofifa (mesmo nome e nação); sem o sofifa, 1º de janeiro do ano."""
        ano = (_dias(data) or datetime.date.today()).year
        sf = sofifa().con()
        if sf is None:
            return f"{ano}-01-01"
        try:
            nasc = {}
            with sofifa()._lock:
                for curto, ns, nac in sf.execute("SELECT curto, nasc, nac FROM fichas WHERE nasc != '' AND ver = (SELECT MAX(ver) FROM fichas)"):
                    nasc.setdefault((K.norm(curto), K.norm(nac)), set()).add(ns)
            datas = []
            for nome, nac, idade in con.execute("SELECT nome, nac, idade FROM jogadores WHERE lenda = 0 AND idade IS NOT NULL"):
                v = nasc.get((K.norm(nome), K.norm(nac)))
                if v and len(v) == 1 and _dias(next(iter(v))):
                    datas.append((_dias(next(iter(v))), idade))
            if len(datas) < 300:
                return f"{ano}-01-01"
            melhor = max((datetime.date(ano - 1 + m // 12, m % 12 + 1, 1) for m in range(24)),
                         key=lambda ref: sum(1 for d, i in datas if idade_na(d.isoformat(), ref) == i))
            return melhor.isoformat()
        except sqlite3.Error:
            return f"{ano}-01-01"

    def buscar(self, j, clube=None, hoje=None, ref=None):
        """[(nota, pid, ficha)] dos jogadores do PES que podem ser este (sem as lendas), o melhor primeiro. Sem
        nascimento no PES: nome compatível + idade na data do patch (±1, pelo nascimento da fonte) + nação + clube.
        Elenco de mais de 2 anos antes do patch: nada (o PES de hoje não diz como o jogador era)."""
        c = self.con()
        if c is None:
            return []
        hoje = hoje or datetime.date.today()
        data = _dias(self.meta().get("data")) or hoje
        data_idade = _dias(self.meta().get("data_idade")) or data
        if ref and (data - ref).days > 730:
            return []
        tks = _tk(j.get("nome"), j.get("primeiro"), j.get("sobrenome"), j.get("nome_completo"))
        with self._lock:
            pids = set()
            for w in tks:
                pids |= {p for (p,) in c.execute("SELECT pid FROM palavras WHERE palavra = ?", (w,))}
            if not pids:
                return []
            linhas = []
            for lote in _lotes(sorted(pids), 500):
                linhas += c.execute(f"SELECT * FROM jogadores WHERE lenda = 0 AND pid IN ({','.join('?' * len(lote))})", lote).fetchall()
        nacs = nacoes_fonte(j)
        res = []
        for x in linhas:
            p = self._jogador(x)
            fn = nome_compativel(p["nome"], j)
            if fn < 0.6:
                continue
            sc = 0.45 + 0.35 * fn
            if nacs and p["nacionalidade"]:
                sc += 0.08 if any(_nac_igual(p["nacionalidade"], n) for n in nacs) else -0.25
            if clube and p["clube"] and K.nota_time(clube, p["clube"]) >= 0.8:
                sc += 0.15                                 # mesmo clube: desempata xarás da mesma idade e nação
            if j.get("nascimento") and p["idade"] is not None:
                esperada = idade_na(j["nascimento"], data_idade)
                if esperada is None or abs(esperada - p["idade"]) > 1:
                    continue
                sc += 0.15 if esperada == p["idade"] else 0.08
            elif p["idade"] is not None and j.get("idade") is not None:
                anos = ((ref or hoje) - data_idade).days / 365.25
                if abs(p["idade"] + anos - j.get("idade_hoje", j["idade"])) > 1.6:
                    continue
                sc += 0.05
            if sc < 0.6:
                continue
            f = ficha_pes(p, VERSAO_VR, data)
            f["nota"], f["forte"] = round(min(1.0, sc), 3), sc >= 0.9 and bool(j.get("nascimento"))
            res.append((round(sc, 3), p["id"], f))                # sem o teto de 1: o clube ainda desempata
        res.sort(key=lambda r: -r[0])
        return res

    def ficha(self, pid):
        c = self.con()
        if c is None:
            return None
        with self._lock:
            x = c.execute("SELECT * FROM jogadores WHERE pid = ?", (int(pid),)).fetchone()
        if not x:
            return None
        data = _dias(self.meta().get("data")) or datetime.date.today()
        return ficha_pes(self._jogador(x), VERSAO_VR, data)

    @staticmethod
    def _jogador(x):
        """Linha do SQLite -> o formato das fichas do pesdb (o que ficha_pes e converter_pes leem)."""
        pid, nome, clube, nac, idade, pos, sec, ovr, pe, alt, peso, lenda, atr, hab = x
        return {"id": pid, "nome": nome, "clube": "" if clube == "FREE AGENT" else clube, "nacionalidade": nac,
                "idade": idade, "posicao": pos, "posicoes2": [s for s in (sec or "").split(",") if s], "overall": ovr,
                "pe": pe, "altura": alt, "peso": peso, "atr": json.loads(atr or "{}"),
                "habilidades": [h for h in (hab or "").split("|") if h], "url": None}


_PES = BasePes()


def pes_local():
    return _PES


def ficha_pes(p, versao, data):
    """Ficha do pesdb -> o formato das fichas (atributos já convertidos para os do FC)."""
    conv = converter_pes(p)
    pos = POS_PES.get(p.get("posicao") or "")
    sec = list(dict.fromkeys(POS_PES[x] for x in p.get("posicoes2") or [] if x in POS_PES and POS_PES[x] != pos))
    return {"fonte": "pes", "versao": NOME_VERSAO_PES.get(versao, versao), "ver": versao, "data": data.isoformat(),
            "id": int(p["id"]), "nome": p.get("nome"), "nome_completo": p.get("nome"), "nascimento": None, "idade": p.get("idade"),
            "nacionalidade": (p.get("nacionalidade") or "").title(), "clube": p.get("clube"), "overall": conv["overall"],
            "overall_pes": p.get("overall"), "potential": None, "pos": pos, "posicoes2": sec[:3], "pe": p.get("pe"),
            "perna_ruim": conv["perna_ruim"], "dribles": conv["dribles"], "altura": p.get("altura"), "peso": p.get("peso"),
            "atr": conv["atr"], "url": p.get("url"), "atr_pes": p.get("atr")}


# ------------------------------------------------------------------ PES -> FC
# quais atributos do PES explicam cada atributo do FC (a conversão de cada um é calibrada: calibracao_pes.json)
# (todos com a nota geral do PES, "ovr": dá o nível do jogador)
FEATS_PES = {
    "acceleration": ["aceleracao", "ovr"], "sprintspeed": ["velocidade", "ovr"],
    "agility": ["aceleracao", "equilibrio", "drible", "controle", "ovr"],
    "balance": ["equilibrio", "aceleracao", "contato", "ovr"], "jumping": ["impulsao", "ovr"],
    "stamina": ["resistencia", "ovr"], "strength": ["contato", "ovr"],
    "reactions": ["ataque", "defesa", "ovr", "controle", "passe_baixo"],
    "aggression": ["agressividade", "desarme", "contato", "defesa", "ovr"],
    "composure": ["controle", "finalizacao", "ovr", "passe_baixo", "defesa"],
    "interceptions": ["defesa", "desarme", "agressividade", "ovr"],
    "positioning": ["ataque", "finalizacao", "controle", "ovr"],
    "vision": ["passe_baixo", "passe_alto", "ataque", "controle", "ovr"], "ballcontrol": ["controle", "ovr"],
    "crossing": ["passe_alto", "curva", "passe_baixo", "ovr"], "dribbling": ["drible", "ovr"],
    "finishing": ["finalizacao", "ovr"], "freekickaccuracy": ["bola_parada", "curva", "passe_alto", "ovr"],
    "headingaccuracy": ["cabeceio", "ovr"], "longpassing": ["passe_alto", "ovr"],
    "shortpassing": ["passe_baixo", "ovr"], "defensiveawareness": ["defesa", "ovr"],
    "shotpower": ["potencia", "ovr"], "longshots": ["potencia", "finalizacao", "curva", "ovr"],
    "standingtackle": ["desarme", "defesa", "ovr"], "slidingtackle": ["desarme", "defesa", "ovr"],
    "volleys": ["finalizacao", "ataque", "potencia", "ovr"], "curve": ["curva", "passe_alto", "bola_parada", "ovr"],
    "penalties": ["finalizacao", "bola_parada", "potencia", "ovr"], "gkdiving": ["gk_alcance", "gk_reflexos", "ovr"],
    "gkhandling": ["gk_pegada", "ovr"], "gkkicking": ["passe_alto", "potencia", "gk_afastar", "ovr"],
    "gkreflexes": ["gk_reflexos", "ovr"], "gkpositioning": ["gk_consciencia", "ovr"]}
_COEF_PES = {"v": None}


def carregar_coef_pes():
    if _COEF_PES["v"] is None:
        try:
            with open(CALIBRACAO_PES, encoding="utf-8") as f:
                _COEF_PES["v"] = json.load(f)
        except (OSError, ValueError):
            _COEF_PES["v"] = {}
    return _COEF_PES["v"]


def calibrar_pes(pares, origem=""):
    """pares: [(ficha do pesdb, ficha do sofifa)] do mesmo jogador na mesma temporada (PES 2021 x FIFA 21) ->
    coeficientes da conversão (mínimos quadrados por atributo; linha e goleiros separados) e o erro médio com 5 partes
    (cada parte fora da amostra)."""
    import numpy as np
    out = {"origem": origem, "amostra": len(pares), "linha": {}, "goleiro": {}, "erro_medio": {}}
    grupos = {"linha": [(p, f) for p, f in pares if p.get("posicao") != "GK"], "goleiro": [(p, f) for p, f in pares if p.get("posicao") == "GK"]}

    def ajusta(X, y):
        X1 = np.hstack([X, np.ones((len(X), 1))])
        w, *_ = np.linalg.lstsq(X1, y, rcond=None)
        erros = []
        idx = np.arange(len(X))
        for k in range(5):                                # erro fora da amostra (5 partes)
            te, tr = idx[idx % 5 == k], idx[idx % 5 != k]
            if len(tr) < 8 or not len(te):
                continue
            wk, *_ = np.linalg.lstsq(X1[tr], y[tr], rcond=None)
            erros += list(np.abs(X1[te] @ wk - y[te]))
        return w, (float(np.mean(erros)) if erros else None)

    for g, ps in grupos.items():
        if len(ps) < 15:
            continue
        for k, feats in FEATS_PES.items():
            linhas = [(_completar_pes(p["atr"], p.get("overall")), f["atr"].get(k)) for p, f in ps]
            linhas = [(a, v) for a, v in linhas if v is not None]
            if len(linhas) < 15:
                continue
            X = np.array([[a.get(x, 50) for x in feats] for a, _ in linhas], dtype=float)
            y = np.array([v for _, v in linhas], dtype=float)
            w, e = ajusta(X, y)
            out[g][k] = {"x": feats, "w": [round(float(v), 4) for v in w[:-1]], "b": round(float(w[-1]), 3)}
            out["erro_medio"][f"{g}:{k}"] = round(e, 2) if e is not None else None
    # nota geral: a do PES (uma reta, com o goleiro à parte)
    X = np.array([[p.get("overall") or 60, 1.0 if p.get("posicao") == "GK" else 0.0] for p, f in pares], dtype=float)
    y = np.array([f["overall"] for p, f in pares], dtype=float)
    w, e = ajusta(X, y)
    out["overall"] = {"w": round(float(w[0]), 4), "gk": round(float(w[1]), 3), "b": round(float(w[2]), 3)}
    out["erro_medio"]["overall"] = round(e, 2)
    # perna ruim e dribles
    ok = [(p, f) for p, f in pares if f.get("perna_ruim")]
    X = np.array([[p["atr"].get("pr_precisao", 2), p["atr"].get("pr_uso", 2)] for p, f in ok], dtype=float)
    w, e = ajusta(X, np.array([f["perna_ruim"] for p, f in ok], dtype=float))
    out["perna_ruim"] = {"w_prec": round(float(w[0]), 4), "w_uso": round(float(w[1]), 4), "b": round(float(w[2]), 3)}
    out["erro_medio"]["perna_ruim"] = round(e, 2)
    ok = [(p, f) for p, f in pares if f.get("dribles") and p.get("posicao") != "GK"]
    X = np.array([[p["atr"].get("drible", 60), sum(1 for h in p.get("habilidades") or [] if h.lower() in TRUQUES_PES)] for p, f in ok], dtype=float)
    w, e = ajusta(X, np.array([f["dribles"] for p, f in ok], dtype=float))
    out["dribles"] = {"w_drible": round(float(w[0]), 4), "w_truques": round(float(w[1]), 4), "b": round(float(w[2]), 3)}
    out["erro_medio"]["dribles"] = round(e, 2)
    vals = [v for k, v in out["erro_medio"].items() if ":" in k and v is not None]
    out["erro_atributos"] = round(sum(vals) / len(vals), 2) if vals else None
    return out


def _completar_pes(a, ovr):
    """Atributos que algumas edições não têm, estimados pelos vizinhos."""
    a = dict(a)
    a.setdefault("conducao", a.get("drible", 60))
    a.setdefault("agressividade", round((a.get("desarme", 50) + a.get("contato", 60)) / 2))
    a.setdefault("contato", a.get("equilibrio", 60))
    for k in ("gk_pegada", "gk_afastar", "gk_reflexos", "gk_alcance"):
        a.setdefault(k, a.get("gk_consciencia", 40))
    a["ovr"] = ovr or 60
    return a


def converter_pes(p):
    """Atributos do PES (chaves de CANON_PES) -> {atr, overall, perna_ruim, dribles} no FC."""
    coef = carregar_coef_pes()
    goleiro = (p.get("posicao") or "") == "GK"
    a = _completar_pes(p.get("atr") or {}, p.get("overall"))
    grupo = (coef.get("goleiro") if goleiro else coef.get("linha")) or {}
    atr = {}
    for k, feats in FEATS_PES.items():
        c = grupo.get(k)
        if c:
            v = c["b"] + sum(w * a.get(f, 50) for w, f in zip(c["w"], c["x"]))
        else:                                             # sem calibração: o atributo do PES mais parecido
            fs = [f for f in feats if f != "ovr"]
            v = sum(a.get(f, 50) for f in fs) / len(fs) - 5
        atr[k] = int(max(1, min(99, round(v))))
    if not goleiro:
        for k in GK_ATR:
            atr[k] = min(atr[k], 15)
    o = coef.get("overall") or {}
    ovr = p.get("overall") or 60
    overall = int(round(o.get("b", -8.0) + o.get("w", 1.0) * ovr + (o.get("gk", 0.0) if goleiro else 0.0)))
    pr_c = coef.get("perna_ruim") or {}
    pr = pr_c.get("b", 0.6) + pr_c.get("w_prec", 0.7) * a.get("pr_precisao", 2) + pr_c.get("w_uso", 0.25) * a.get("pr_uso", 2)
    truques = sum(1 for h in p.get("habilidades") or [] if h.lower() in TRUQUES_PES)
    dr_c = coef.get("dribles") or {}
    dr = dr_c.get("b", -2.4) + dr_c.get("w_drible", 0.055) * a.get("drible", 60) + dr_c.get("w_truques", 0.3) * truques
    return {"atr": atr, "overall": int(max(40, min(95, overall))), "perna_ruim": int(max(1, min(5, round(pr)))),
            "dribles": 1 if goleiro else int(max(1, min(5, round(dr))))}
