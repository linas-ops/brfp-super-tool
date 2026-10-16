"""BRFP Super Tool — cliente da transfermarkt-api (github.com/felipeall/transfermarkt-api, MIT): dados da Transfermarkt
(elencos, perfis, valores de mercado, clubes, competições, tabelas, jogos) pela API JSON interna do site.

Onde a API roda (dados/transfermarkt.json, "modo"):
    local    o servidor instalado em Componentes (runtime/apps/transfermarkt-api + pacotes no Python embutido), ligado
             por este módulo em 127.0.0.1:8790 quando preciso — rápido e sem limite de pedidos;
    publico  transfermarkt-api.fly.dev (o autor diz que é só para testes; 2 pedidos a cada 3 s);
    outro    um endereço seu (ex.: a API rodando em Docker em outro computador).
"auto" (padrão) usa o local quando está instalado; senão o público.

Toda resposta fica em dados/tm_cache: temporadas encerradas valem para sempre; elencos atuais, 1 dia. Os dados são da
Transfermarkt: use conforme os termos dela (uso pessoal).
"""
import atexit
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import apifutebol

PUBLICO = "https://transfermarkt-api.fly.dev/"
PORTA_LOCAL = 8790
UM_DIA = 86400
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# validade do cache: (expressão da rota, segundos; None = para sempre; "temporada" = para sempre se a temporada acabou)
VALIDADE = [(r"^countries", 30 * UM_DIA), (r"^competitions/search/", 7 * UM_DIA), (r"^competitions/[^/]+/seasons", 30 * UM_DIA),
            (r"^competitions/[^/]+/(clubs|table)", "temporada"), (r"^clubs/search/", 30 * UM_DIA),
            (r"^clubs/[^/]+/profile", 7 * UM_DIA), (r"^clubs/[^/]+/players", "temporada"), (r"^players/[^/]+/profile", 7 * UM_DIA),
            (r"^players/[^/]+/market_value", 7 * UM_DIA), (r"^players/[^/]+/stats", 3 * UM_DIA),
            (r"^players/[^/]+/matches", "temporada"), (r"^players/[^/]+/transfers", UM_DIA), (r"^games/", None),
            (r"^coaches/[^/]+/profile", 30 * UM_DIA)]


class ErroTm(Exception):
    pass


def temporada_encerrada(season_id):
    return apifutebol.temporada_encerrada(season_id)


class Tm:
    def __init__(self, pasta=None):
        self.pasta = pasta or apifutebol.pasta_dados()
        self.arq = os.path.join(self.pasta, "transfermarkt.json")
        self.cache = os.path.join(self.pasta, "tm_cache")
        self.lock = threading.Lock()
        self.lock_local = threading.Lock()
        self.ultima = 0.0
        self.proc = None
        self.cfg = self._ler()
        self.feitas = 0
        atexit.register(self.parar_local)

    # ------------------------------------------------------------------ configuração
    def _ler(self):
        try:
            with open(self.arq, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"modo": "auto"}

    def _gravar(self):
        os.makedirs(self.pasta, exist_ok=True)
        with open(self.arq + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=1)
        os.replace(self.arq + ".tmp", self.arq)

    def definir(self, modo, url=None):
        if modo not in ("auto", "local", "publico", "outro"):
            raise ErroTm("Modo inválido.")
        self.cfg["modo"] = modo
        if modo == "outro":
            u = (url or "").strip()
            if not re.match(r"^https?://", u):
                raise ErroTm("Informe o endereço completo da API (ex.: http://192.168.0.10:8000/).")
            self.cfg["url"] = u if u.endswith("/") else u + "/"
        self._gravar()

    @staticmethod
    def local_instalado():
        try:
            import componentes
            e = componentes.estado_grupo("transfermarkt")
            if not e["ok"] and e["python"] and not e["faltam"] and e["faltam_projetos"] \
                    and all(componentes.projetos_instalados().get(p) for p in e["faltam_projetos"]):
                # versão nova da transfermarkt-api no manifesto (o código só, ≈1 MB): atualiza sozinho
                try:
                    componentes.instalar(["transfermarkt"])
                    e = componentes.estado_grupo("transfermarkt")
                except Exception:  # noqa: BLE001 — sem internet etc.: usa a instância pública desta vez
                    return False
            return e["ok"]
        except Exception:  # noqa: BLE001
            return False

    def modo(self):
        m = self.cfg.get("modo") or "auto"
        if m == "auto":
            return "local" if self.local_instalado() else "publico"
        return m

    def base(self):
        m = self.modo()
        if m == "local":
            return f"http://127.0.0.1:{PORTA_LOCAL}/"
        if m == "outro":
            return self.cfg.get("url") or PUBLICO
        return PUBLICO

    def intervalo(self):
        return {"publico": 1.6, "local": 0.0}.get(self.modo(), 0.2)

    def paralelo(self):
        """Quantos pedidos ao mesmo tempo: só no servidor local (o público tem limite por endereço)."""
        return 6 if self.modo() == "local" else 1

    # ------------------------------------------------------------------ servidor local
    def _saude(self, base=None, timeout=3):
        try:
            with urllib.request.urlopen((base or self.base()) + "health", timeout=timeout) as r:
                return r.status == 200
        except (OSError, ValueError):
            return False

    def garantir_local(self):
        """Liga o servidor local (Python embutido + runtime/apps/transfermarkt-api) se ele não estiver respondendo."""
        if self.modo() != "local":
            return
        with self.lock_local:
            if self._saude(timeout=2):
                return
            import componentes
            if not componentes.estado_grupo("transfermarkt")["ok"]:
                raise ErroTm("O servidor local da Transfermarkt não está instalado: instale em Componentes (Super Tool) "
                             "ou troque para a instância pública.")
            pasta = componentes.caminho_projeto("transfermarkt_api")
            codigo = ("import sys, uvicorn; sys.path.insert(0, %r); "
                      "uvicorn.run('app.main:app', host='127.0.0.1', port=%d, log_level='warning')" % (pasta, PORTA_LOCAL))
            env = dict(os.environ, RATE_LIMITING_ENABLE="false", PYTHONUTF8="1")
            os.makedirs(self.pasta, exist_ok=True)
            log = open(os.path.join(self.pasta, "tm_servidor.log"), "ab")
            self.proc = subprocess.Popen([componentes.PYEXE, "-X", "utf8", "-c", codigo], cwd=pasta, env=env, stdout=log,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
            t0 = time.time()
            while time.time() - t0 < 30:
                if self.proc.poll() is not None:
                    raise ErroTm(f"O servidor local da Transfermarkt fechou ao iniciar (veja {os.path.join(self.pasta, 'tm_servidor.log')}).")
                if self._saude(timeout=1):
                    return
                time.sleep(0.4)
            raise ErroTm("O servidor local da Transfermarkt demorou demais para iniciar.")

    def parar_local(self):
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass

    def status(self):
        m = self.modo()
        st = {"modo": m, "configurado": self.cfg.get("modo") or "auto", "url": self.base(), "local_instalado": self.local_instalado(),
              "outro_url": self.cfg.get("url"), "feitas": self.feitas}
        st["rodando"] = self._saude(timeout=2) if m != "publico" else None
        return st

    # ------------------------------------------------------------------ cache
    def _chave(self, rota, params):
        q = urllib.parse.urlencode(sorted((k, str(v)) for k, v in params.items() if v not in (None, "")))
        return rota.strip("/") + ("?" + q if q else "")

    def _arq_cache(self, chave):
        pasta = re.sub(r"[^a-z_]", "", chave.split("/")[0].lower()) or "outros"
        return os.path.join(self.cache, pasta, hashlib.sha1(chave.encode()).hexdigest()[:20] + ".json")

    def _validade(self, rota, params):
        for rx, v in VALIDADE:
            if re.match(rx, rota):
                if v == "temporada":
                    s = params.get("season_id")
                    return None if (s and temporada_encerrada(s)) else UM_DIA
                return v
        return UM_DIA

    def em_cache(self, rota, **params):
        return os.path.isfile(self._arq_cache(self._chave(rota, params)))

    def do_cache(self, rota, **params):
        try:
            with open(self._arq_cache(self._chave(rota, params)), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def chamadas_para(self, rota, **params):
        return 0 if self.em_cache(rota, **params) else 1

    # ------------------------------------------------------------------ pedidos
    def get(self, rota, usar_cache=True, **params):
        rota = rota.strip("/")
        chave = self._chave(rota, params)
        arq = self._arq_cache(chave)
        val = self._validade(rota, params)
        if usar_cache and os.path.isfile(arq):
            idade = time.time() - os.path.getmtime(arq)
            if val is None or idade < val or os.environ.get("BRFP_API_SO_CACHE"):
                with open(arq, encoding="utf-8") as f:
                    return json.load(f)
        if os.environ.get("BRFP_API_SO_CACHE"):
            raise ErroTm(f"(teste) {chave} não está no cache.")
        self.garantir_local()
        url = self.base() + urllib.parse.quote(rota, safe="/") + ("?" + chave.split("?", 1)[1] if "?" in chave else "")
        ultimo = None
        for tentativa in range(5):
            espera = 0.0
            if self.intervalo():
                with self.lock:
                    espera = self.ultima + self.intervalo() - time.time()
                    self.ultima = max(self.ultima + self.intervalo(), time.time())
            if espera > 0:
                time.sleep(espera)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "BRFP-Super-Tool", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    corpo = json.loads(r.read().decode("utf-8"))
                self.feitas += 1
                break
            except urllib.error.HTTPError as ex:
                ultimo = ex
                if ex.code == 429:                       # limite da instância pública: espera e tenta de novo
                    time.sleep(float(ex.headers.get("Retry-After") or 3) + tentativa)
                    continue
                if ex.code == 404:
                    raise ErroTm(f"A Transfermarkt não tem esse item ({rota}).")
                if ex.code == 501:
                    raise ErroTm(f"A transfermarkt-api não tem essa informação ({rota}).")
                if ex.code in (502, 503, 504):
                    if tentativa < 2:
                        time.sleep(2 + 2 * tentativa)
                        continue
                    raise ErroTm({503: "A Transfermarkt recusou o pedido (bloqueio temporário). Tente mais tarde.",
                                  504: "A Transfermarkt demorou demais para responder. Tente de novo."}.get(
                        ex.code, "A Transfermarkt respondeu de um jeito inesperado (a API interna dela pode ter mudado)."))
                raise ErroTm(f"A transfermarkt-api respondeu {ex.code}: {ex.reason}")
            except (urllib.error.URLError, OSError, ValueError) as ex:
                ultimo = ex
                if self.modo() == "local" and tentativa < 2:
                    self.garantir_local()
                    continue
                if tentativa < 1:
                    time.sleep(2)
                    continue
                onde = {"publico": "a instância pública (transfermarkt-api.fly.dev)", "local": "o servidor local",
                        "outro": self.base()}.get(self.modo(), self.base())
                raise ErroTm(f"Sem resposta da transfermarkt-api em {onde} ({getattr(ex, 'reason', ex)}).")
        else:
            raise ErroTm(f"A transfermarkt-api recusou os pedidos (limite de pedidos): {ultimo}. Espere um pouco ou use o "
                         "servidor local (Componentes).")
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        corpo["_brfp"] = {"consulta": chave, "quando": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(arq + ".tmp", "w", encoding="utf-8") as f:
            json.dump(corpo, f, ensure_ascii=False)
        os.replace(arq + ".tmp", arq)
        return corpo

    def varios(self, rotas, progresso=None):
        """{rota: resposta} de várias rotas (em paralelo no servidor local). Rotas com erro ficam com {"erro": …}."""
        out = {}
        if self.paralelo() > 1:
            import concurrent.futures as cf
            self.garantir_local()
            with cf.ThreadPoolExecutor(self.paralelo()) as ex:
                fut = {ex.submit(self._um, r): r for r in rotas}
                for n, f in enumerate(cf.as_completed(fut)):
                    out[fut[f]] = f.result()
                    if progresso:
                        progresso(n + 1, len(rotas))
        else:
            for n, r in enumerate(rotas):
                out[r] = self._um(r)
                if progresso:
                    progresso(n + 1, len(rotas))
        return out

    def _um(self, rota_com_params):
        rota, _, q = rota_com_params.partition("?")
        params = dict(urllib.parse.parse_qsl(q))
        try:
            return self.get(rota, **params)
        except ErroTm as ex:
            return {"erro": str(ex)}


IMG = "https://img.a.transfermarkt.technology/"


def escudo(clube_id, tamanho="head"):
    """Escudo do clube (head = grande; small = lista)."""
    return f"{IMG}wappen/{tamanho}/{clube_id}.png"


def logo_competicao(comp_id, tamanho="medium"):
    return f"{IMG}logo/{tamanho}/{str(comp_id).lower()}.png"
