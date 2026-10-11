"""BRFP Super Tool — cliente da API-Football (api-sports.io, v3), só biblioteca padrão.

- A chave fica em dados/api_football.json (nunca vai no pacote para outro computador).
- Toda resposta é guardada em dados/api_cache/: a mesma pergunta não gasta outra chamada enquanto o cache valer
  (dados de temporadas passadas valem para sempre; elencos atuais, 1 dia).
- Respeita os limites do plano (por dia e por minuto) lendo os cabeçalhos x-ratelimit-* de cada resposta.

    api = Api()
    api.get("teams", league=71, season=2024)          -> lista "response"
    api.todas("players", team=121, season=2024)       -> junta todas as páginas
"""
import hashlib
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

COMUM = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(COMUM)
BASE = "https://v3.football.api-sports.io/"
UM_DIA = 86400
# validade do cache por rota (segundos); None = para sempre
VALIDADE = {"status": 0, "countries": 30 * UM_DIA, "leagues": 7 * UM_DIA, "teams": 7 * UM_DIA, "venues": 30 * UM_DIA,
            "players/squads": UM_DIA, "players/profiles": 30 * UM_DIA, "players/teams": 7 * UM_DIA, "coachs": 3 * UM_DIA,
            "transfers": UM_DIA, "trophies": 30 * UM_DIA, "injuries": UM_DIA, "standings": UM_DIA,
            "teams/statistics": UM_DIA, "fixtures": UM_DIA, "fixtures/lineups": None, "fixtures/players": None,
            "players": UM_DIA, "sidelined": 7 * UM_DIA, "fixtures/rounds": UM_DIA}


class ErroApi(Exception):
    pass


def temporada_encerrada(season):
    """Temporada que já terminou (calendário europeu 2024 = 2024/25; brasileiro 2024 = 2024): nos dois casos, uma
    temporada X acabou de vez quando já estamos no segundo semestre de X+1."""
    try:
        s = int(season)
    except (TypeError, ValueError):
        return False
    hoje = time.localtime()
    return s < hoje.tm_year - 1 or (s == hoje.tm_year - 1 and hoje.tm_mon >= 7)


_MOJIBAKE = re.compile("[Â-ô][\u0080-¿‘-›ŒœŠšŸŽžƒˆ˜€™]")


def consertar_texto(s):
    """Texto como deveria vir da API: alguns nomes chegam com o UTF-8 lido como Latin-1/Windows-1252 ("Ã\\x89rika",
    "LetÃ­cia") e outros com entidades HTML ("d&apos;Ascq")."""
    if not isinstance(s, str) or not s:
        return s
    if "&" in s:
        s = html.unescape(s)
    if _MOJIBAKE.search(s):
        for cod in ("latin-1", "cp1252"):
            try:
                c = s.encode(cod).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if c != s:
                return c
    return s


def consertar(obj):
    """consertar_texto() em todos os textos de uma resposta (listas e dicts aninhados)."""
    if isinstance(obj, str):
        return consertar_texto(obj)
    if isinstance(obj, list):
        return [consertar(v) for v in obj]
    if isinstance(obj, dict):
        return {k: consertar(v) for k, v in obj.items()}
    return obj


def pasta_dados():
    return os.environ.get("BRFP_DADOS") or os.path.join(SUPERTOOL, "dados")


class Api:
    def __init__(self, pasta=None):
        self.pasta = pasta or pasta_dados()
        self.arq = os.path.join(self.pasta, "api_football.json")
        self.cache = os.path.join(self.pasta, "api_cache")
        self.lock = threading.Lock()
        self.ultima = 0.0
        self.cfg = self._ler()

    # ------------------------------------------------------------------ configuração e uso
    def _ler(self):
        try:
            with open(self.arq, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _gravar(self):
        os.makedirs(self.pasta, exist_ok=True)
        tmp = self.arq + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.arq)

    @property
    def chave(self):
        return (self.cfg.get("chave") or "").strip()

    def definir_chave(self, chave):
        self.cfg["chave"] = (chave or "").strip()
        for k in ("plano", "max_paginas", "temporadas"):
            self.cfg.pop(k, None)
        self._gravar()

    def uso(self):
        """Chamadas restantes hoje (do último cabeçalho recebido; zera à meia-noite UTC)."""
        u = dict(self.cfg.get("uso") or {})
        hoje = time.strftime("%Y-%m-%d", time.gmtime())
        if u.get("dia") != hoje:
            u = {"dia": hoje, "feitas": 0, "restantes": u.get("limite") or 100, "limite": u.get("limite") or 100}
        return u

    def _anotar(self, cab):
        u = self.uso()
        try:
            u["limite"] = int(cab.get("x-ratelimit-requests-limit") or u.get("limite") or 100)
            u["restantes"] = int(cab.get("x-ratelimit-requests-remaining"))
        except (TypeError, ValueError):
            pass
        u["feitas"] = u.get("feitas", 0) + 1
        self.cfg["uso"] = u
        try:
            self.cfg["por_minuto"] = int(cab.get("x-ratelimit-limit") or self.cfg.get("por_minuto") or 10)
        except ValueError:
            pass

    # ------------------------------------------------------------------ chamadas
    def _caminho_cache(self, rota, params):
        chave = rota + "?" + urllib.parse.urlencode(sorted((k, str(v)) for k, v in params.items()))
        h = hashlib.sha1(chave.encode()).hexdigest()[:20]
        return os.path.join(self.cache, rota.replace("/", "_"), h + ".json"), chave

    def em_cache(self, rota, **params):
        arq, _ = self._caminho_cache(rota, {k: v for k, v in params.items() if v is not None and v != ""})
        return os.path.isfile(arq)

    def do_cache(self, rota, **params):
        """Resposta guardada (sem chamar a API), ou None."""
        arq, _ = self._caminho_cache(rota, {k: v for k, v in params.items() if v is not None and v != ""})
        try:
            with open(arq, encoding="utf-8") as f:
                return consertar(json.load(f))
        except (OSError, ValueError):
            return None

    def bruto(self, rota, params, usar_cache=True, validade=None):
        """Resposta completa (dict com response/paging/errors). Usa o cache quando possível."""
        params = {k: v for k, v in params.items() if v is not None and v != ""}
        arq, chave = self._caminho_cache(rota, params)
        val = VALIDADE.get(rota, UM_DIA) if validade is None else validade
        if val and temporada_encerrada(params.get("season")):
            val = None                                          # temporada que já acabou não muda mais
        if usar_cache and val != 0 and os.path.isfile(arq):
            idade = time.time() - os.path.getmtime(arq)
            if val is None or idade < val or os.environ.get("BRFP_API_SO_CACHE"):
                with open(arq, encoding="utf-8") as f:
                    return consertar(json.load(f))
        if os.environ.get("BRFP_API_SO_CACHE") and rota != "status":
            raise ErroApi(f"(teste) {chave} não está no cache.")
        if not self.chave:
            raise ErroApi("Nenhuma chave da API-Football configurada. Cole a chave em Configurações (dashboard.api-football.com).")
        with self.lock:
            u = self.uso()
            if rota != "status" and u.get("restantes") is not None and u["restantes"] <= 0:
                raise ErroApi(f"Limite diário da API atingido ({u.get('limite')} chamadas). Ele volta à meia-noite (UTC) — "
                              "ou assine um plano maior. Tudo o que já foi baixado continua no cache.")
            # espaça as chamadas para não passar do limite por minuto
            intervalo = 60.0 / max(1, int(self.cfg.get("por_minuto") or 10)) + 0.15
            espera = self.ultima + intervalo - time.time()
            if espera > 0:
                time.sleep(espera)
            url = BASE + rota + ("?" + urllib.parse.urlencode(params) if params else "")
            req = urllib.request.Request(url, headers={"x-apisports-key": self.chave, "User-Agent": "BRFP-Super-Tool"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    corpo = json.loads(r.read().decode("utf-8"))
                    cab = {k.lower(): v for k, v in r.headers.items()}
            except urllib.error.HTTPError as ex:
                raise ErroApi(f"A API respondeu {ex.code}: {ex.reason}")
            except (urllib.error.URLError, OSError, ValueError) as ex:
                raise ErroApi(f"Sem resposta da API-Football ({getattr(ex, 'reason', ex)}). Verifique a internet.")
            finally:
                self.ultima = time.time()
            if rota != "status":
                self._anotar(cab)
                self._gravar()
        erros = corpo.get("errors")
        if erros:
            msg = "; ".join(f"{v}" for v in (erros.values() if isinstance(erros, dict) else erros))
            m = re.search(r"try from (\d{4}) to (\d{4})", msg)
            if m:                                                   # temporadas que o plano libera
                self.cfg["temporadas"] = [int(m.group(1)), int(m.group(2))]
                self._gravar()
            raise ErroApi(traduzir_erro(msg))
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        corpo["_brfp"] = {"consulta": chave, "quando": time.strftime("%Y-%m-%d %H:%M:%S")}
        tmp = arq + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(corpo, f, ensure_ascii=False)
        os.replace(tmp, arq)
        return consertar(corpo)

    def get(self, rota, usar_cache=True, **params):
        return self.bruto(rota, params, usar_cache)["response"]

    def todas(self, rota, usar_cache=True, maximo=40, info=None, **params):
        """Junta todas as páginas (rota players). O plano grátis só libera 3 páginas: info["incompleto"] avisa."""
        out = []
        pagina = 1
        maximo = min(maximo, int(self.cfg.get("max_paginas") or maximo))
        while True:
            try:
                c = self.bruto(rota, dict(params, page=pagina) if pagina > 1 or rota in PAGINADAS else params, usar_cache)
            except ErroApi as ex:
                if pagina > 1 and "page" in str(ex).lower():
                    self.cfg["max_paginas"] = pagina - 1          # limite do plano: lembra para não gastar de novo
                    self._gravar()
                    if info is not None:
                        info["incompleto"] = True
                    return out
                raise
            out += c.get("response") or []
            total = (c.get("paging") or {}).get("total") or 1
            if info is not None:
                info["paginas"] = total
            if pagina >= total:
                return out
            if pagina >= maximo:
                if info is not None:
                    info["incompleto"] = True
                return out
            pagina += 1

    def chamadas_para(self, rota, paginas=1, **params):
        """Quantas chamadas uma consulta vai gastar (0 se estiver no cache)."""
        return 0 if self.em_cache(rota, **params) else paginas

    def status(self):
        r = self.bruto("status", {}, usar_cache=False)["response"]
        if isinstance(r, dict):
            self.cfg["plano"] = (r.get("subscription") or {}).get("plan")
            req = r.get("requests") or {}
            u = self.uso()
            if req.get("limit_day"):
                u["limite"] = req["limit_day"]
                u["restantes"] = max(0, req["limit_day"] - (req.get("current") or 0))
                self.cfg["uso"] = u
            self._gravar()
        return {"plano": self.cfg.get("plano"), "uso": self.uso()}


PAGINADAS = {"players"}


# ------------------------------------------------------------------ imagens (escudos, fotos): não gastam chamadas do plano
_IPS = {}
_SEM_DNS = set()          # nomes que o DNS da rede não resolve: vão direto pelo endereço obtido por HTTPS


def _resolver_doh(host):
    """Endereço pelo DNS da Cloudflare via HTTPS (para quando o DNS da rede não responde a um nome)."""
    if host in _IPS:
        return _IPS[host]
    ultimo = None
    for base in ("https://dns.google/resolve", "https://8.8.8.8/resolve", "https://1.1.1.1/dns-query",
                 "https://cloudflare-dns.com/dns-query"):
        try:
            req = urllib.request.Request(f"{base}?name={urllib.parse.quote(host)}&type=A",
                                         headers={"accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read().decode("utf-8"))
            ips = [a["data"] for a in resp.get("Answer") or [] if a.get("type") == 1]
            if ips:
                _IPS[host] = ips[0]
                return ips[0]
        except (OSError, ValueError) as ex:
            ultimo = ex
    raise OSError(f"{host}: sem endereço ({ultimo})")


def baixar(url, timeout=30):
    """Bytes da URL. Se o DNS da rede falhar, resolve pelo DNS da Cloudflare e conecta no IP com o mesmo nome (SNI e
    certificado conferidos normalmente)."""
    host = urllib.parse.urlsplit(url).hostname
    if host not in _SEM_DNS:
        req = urllib.request.Request(url, headers={"User-Agent": "BRFP-Super-Tool"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.URLError as ex:
            if not isinstance(getattr(ex, "reason", None), OSError) or "getaddrinfo" not in str(ex.reason) and "11001" not in str(ex.reason):
                raise
            _SEM_DNS.add(host)
    import http.client
    import socket
    import ssl
    u = urllib.parse.urlsplit(url)
    ip = _resolver_doh(u.hostname)

    class ConexaoIP(http.client.HTTPSConnection):
        def connect(self):
            sock = socket.create_connection((ip, self.port or 443), self.timeout)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
    c = ConexaoIP(u.hostname, u.port or 443, timeout=timeout, context=ssl.create_default_context())
    try:
        c.request("GET", u.path + ("?" + u.query if u.query else ""), headers={"User-Agent": "BRFP-Super-Tool"})
        r = c.getresponse()
        if r.status != 200:
            raise OSError(f"HTTP {r.status}")
        return r.read()
    finally:
        c.close()


def traduzir_erro(msg):
    m = msg.lower()
    if "free plans do not have access to this season" in m or ("free" in m and "season" in m):
        return "O plano grátis da API-Football não dá acesso a essa temporada (" + msg + ")."
    if "request limit" in m or "reached the request limit" in m:
        return "Limite diário da API atingido. Ele volta à meia-noite (UTC). (" + msg + ")"
    if "token" in m or "key" in m and "application" in m:
        return "Chave da API inválida ou ausente. (" + msg + ")"
    if "too many requests" in m or "ratelimit" in m.replace(" ", ""):
        return "Muitas chamadas por minuto; aguarde alguns segundos. (" + msg + ")"
    return "API-Football: " + msg
