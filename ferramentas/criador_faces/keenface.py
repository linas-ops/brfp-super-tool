"""Cliente da API v2 do KeenFace (keenface.ai, da KeenTools), só biblioteca padrão.

Caminho que o Criador de Faces usa:
  enviar_foto()    POST /v2/photos com os bytes da imagem -> ph_… (vale 24 h enquanto nenhuma cabeça usar)
  orcamento()      POST /v2/heads?dry_run=true -> custo, saldo e se dá; não cria, não guarda e não cobra nada
  criar()          POST /v2/heads com Idempotency-Key -> cabeça na fila (150 créditos, cobrados só se der certo)
  cabeca()         GET  /v2/heads/{id}?wait=… -> status e progresso
  baixar_modelo()  GET  /v2/heads/{id}/model (espera o arquivo ficar pronto) e baixa pelo link assinado, sem a chave

A chave (ak_…) é de cada usuário e fica só no computador dele (preferencias.json da ferramenta).
BRFP_KEENFACE_API troca o endereço da API (testes com um servidor falso local).
"""
import io
import json
import os
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("BRFP_KEENFACE_API", "https://api.keenface.ai").rstrip("/") + "/v2"
SITE = "https://keenface.ai"
LINKS = {"chaves": SITE + "/api-keys", "precos": SITE + "/pricing", "site": SITE,
         "termos": SITE + "/terms", "privacidade": SITE + "/privacy"}
UA = "BRFP-Super-Tool"
MAX_FOTOS = 15
LIMITE_FOTO = 67_108_864                     # JPEG, PNG e WebP: 64 MiB
LIMITE_FOTO_HEIF = 20_000_000                # HEIC, HEIF e AVIF: 20 MB
LIMITE_PIXELS = 100_000_000
LIMITE_LADO = 12_000
TIPOS_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".jfif": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
             ".heic": "image/heic", ".heif": "image/heif", ".avif": "image/avif"}
EXTENSOES = tuple(TIPOS_EXT)
RETENTAVEIS = {"rede", "service_unavailable", "internal_error", "rate_limited"}

# mensagens para a interface; o texto original do KeenFace vai junto em "original"
MENSAGENS = {
    "sem_chave": "Cole a sua chave da API do KeenFace (começa com ak_). Ela é criada em keenface.ai, em API keys.",
    "unauthorized": "O KeenFace recusou a chave da API. Confira se ela foi copiada inteira (começa com ak_) ou crie outra "
                    "em keenface.ai, em API keys.",
    "insufficient_credits": "Créditos insuficientes no KeenFace: cada cabeça custa 150 créditos. Compre créditos no site "
                            "(os arquivos não custam nada a mais).",
    "phone_verification_required": "O KeenFace pede um telefone confirmado na conta para usar os créditos grátis. Entre no "
                                   "keenface.ai, confirme o telefone no Studio e tente de novo (créditos comprados não precisam disso).",
    "legal_acceptance_required": "O KeenFace pede que a conta aceite os termos atualizados antes de criar cabeças. Aceite no "
                                 "site e tente de novo.",
    "feature_unavailable": "Este modo do KeenFace não está disponível agora para a sua conta. Tente o outro modo ou mais tarde.",
    "rate_limited": "Pedidos demais ao KeenFace em pouco tempo. Espere um minuto e tente de novo.",
    "photo_too_large": "Foto grande demais para o KeenFace: até 64 MB (20 MB em HEIC/AVIF), 100 megapixels e 12.000 pixels "
                       "no lado maior. Reduza a foto e tente de novo.",
    "unsupported_media_type": "Formato de foto que o KeenFace não aceita. Use JPG, PNG, WebP, HEIC ou AVIF.",
    "too_few_photos": "Fotos de menos: o modo Sessão de fotos (Scan) precisa de pelo menos 2 (recomendado 3 ou mais).",
    "too_many_photos": "Fotos demais: o KeenFace aceita no máximo 15 por cabeça.",
    "photo_expired": "Uma das fotos enviadas expirou no KeenFace (vale 24 h). Ela será enviada de novo.",
    "idempotency_conflict": "O KeenFace ainda está recebendo o pedido anterior. Espere alguns segundos e tente de novo.",
    "head_running": "A cabeça ainda está sendo feita: só dá para apagar depois que ela terminar.",
    "head_not_ready": "A cabeça ainda não ficou pronta no KeenFace.",
    "head_failed": "Esta cabeça falhou no KeenFace e não tem arquivos.",
    "variant_not_available": "Este formato de arquivo não está disponível para esta cabeça.",
    "not_found": "O KeenFace não achou esta cabeça na sua conta (ela pode ter sido apagada).",
    "service_unavailable": "O KeenFace está fora do ar no momento. Tente de novo em alguns minutos.",
    "internal_error": "Erro interno do KeenFace. Tente de novo em alguns minutos.",
    "invalid_request": "O KeenFace recusou o pedido.",
    "field_not_applicable": "Opção que não vale para este modo do KeenFace.",
    "rede": "Sem conexão com o KeenFace. Confira a internet e tente de novo.",
    "resposta_invalida": "Resposta inesperada do KeenFace.",
    # falhas da cabeça (Head.error.code): cabeça que falha não é cobrada
    "content_rejected": "O KeenFace recusou as fotos: elas precisam mostrar o rosto de uma pessoa só, bem visível. Troque as "
                        "fotos e tente de novo (cabeça que falha não é cobrada).",
    "reconstruction_failed": "O KeenFace não conseguiu montar a cabeça com estas fotos. Use fotos nítidas, com luz uniforme e "
                             "o rosto inteiro (cabeça que falha não é cobrada).",
    "timeout": "O KeenFace demorou demais e desistiu desta cabeça. Tente de novo mais tarde com as mesmas fotos (cabeça que "
               "falha não é cobrada).",
}
LINK_DO_ERRO = {"sem_chave": "chaves", "unauthorized": "chaves", "insufficient_credits": "precos",
                "phone_verification_required": "site", "legal_acceptance_required": "site"}


class ErroKeenFace(Exception):
    def __init__(self, codigo, original="", status=None, campo=None, sugestao=None, request_id=None, espera=None,
                 mensagem=None):
        self.codigo = codigo or "invalid_request"
        self.original = (original or "").strip()
        self.status, self.campo, self.sugestao, self.request_id, self.espera = status, campo, sugestao, request_id, espera
        msg = MENSAGENS.get(self.codigo) or self.original or f"Erro do KeenFace ({self.codigo})."
        if self.codigo in ("invalid_request", "field_not_applicable") and self.original:
            msg = f"{msg} {self.original}"
        if self.campo and self.codigo in ("invalid_request", "field_not_applicable"):
            msg += f" (campo: {self.campo})"
        msg = mensagem or msg
        self.link = LINKS.get(LINK_DO_ERRO.get(self.codigo, ""))
        if self.codigo == "legal_acceptance_required":
            achado = link_seguro(self.original)
            if achado:
                self.link = achado
        super().__init__(msg)

    def publico(self):
        return {"codigo": self.codigo, "mensagem": str(self), "original": self.original, "campo": self.campo,
                "sugestao": self.sugestao, "request_id": self.request_id, "link": self.link}


class Cancelado(Exception):
    """O usuário cancelou enquanto a ferramenta esperava."""


def link_seguro(texto):
    """Primeiro link https do texto que seja do KeenFace/KeenTools (o de aceitar os termos vem na mensagem do erro)."""
    for url in re.findall(r"https://[^\s\"'<>)\]]+", texto or ""):
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host == "keenface.ai" or host.endswith((".keenface.ai", ".keentools.io")) or host == "keentools.io":
            return url.rstrip(".,;")
    return None


def dormir(segundos, parar=None):
    if parar is None:
        time.sleep(segundos)
    elif parar.wait(segundos):
        raise Cancelado()


# ------------------------------------------------------------------ fotos
def tipo_da_foto(dados, nome=""):
    """Tipo MIME pelo conteúdo (o KeenFace também confere pelo conteúdo); senão pela extensão."""
    if dados[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    if dados[4:8] == b"ftyp":
        marcas = {dados[8:12]} | {dados[i:i + 4] for i in range(16, min(len(dados), 64), 4)}
        if marcas & {b"avif", b"avis"}:
            return "image/avif"
        if marcas & {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis"}:
            return "image/heic"
        if marcas & {b"mif1", b"msf1"}:
            return "image/heif"
    return TIPOS_EXT.get(os.path.splitext(nome)[1].lower())


def dimensoes(dados, tipo):
    """(largura, altura) de JPEG, PNG e WebP pelo cabeçalho; None se não der para ler."""
    try:
        if tipo == "image/png" and dados[12:16] == b"IHDR":
            return struct.unpack(">II", dados[16:24])
        if tipo == "image/webp":
            pedaco = dados[12:16]
            if pedaco == b"VP8 ":
                w, h = struct.unpack("<HH", dados[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if pedaco == b"VP8L":
                b = dados[21:25]
                w = 1 + (((b[1] & 0x3F) << 8) | b[0])
                h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
                return w, h
            if pedaco == b"VP8X":
                return 1 + int.from_bytes(dados[24:27], "little"), 1 + int.from_bytes(dados[27:30], "little")
        if tipo == "image/jpeg":
            i = 2
            while i + 9 < len(dados):
                if dados[i] != 0xFF:
                    i += 1
                    continue
                m = dados[i + 1]
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7 or m == 0xFF:
                    i += 1 if m == 0xFF else 2
                    continue
                tam = struct.unpack(">H", dados[i + 2:i + 4])[0]
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", dados[i + 5:i + 9])
                    return w, h
                i += 2 + tam
    except (struct.error, IndexError):
        pass
    return None


def conferir_foto(caminho):
    """Lê uma foto e confere os limites do KeenFace. -> dict(tipo, bytes, largura, altura, problema)"""
    tam = os.path.getsize(caminho)
    with open(caminho, "rb") as f:
        cab = f.read(256 * 1024)
    tipo = tipo_da_foto(cab, caminho)
    info = {"tipo": tipo, "bytes": tam, "largura": None, "altura": None, "problema": None}
    if not tipo:
        info["problema"] = "formato que o KeenFace não aceita (use JPG, PNG, WebP, HEIC ou AVIF)"
        return info
    dim = dimensoes(cab, tipo)
    if dim:
        info["largura"], info["altura"] = dim
    limite = LIMITE_FOTO_HEIF if tipo in ("image/heic", "image/heif", "image/avif") else LIMITE_FOTO
    if tam > limite:
        info["problema"] = f"arquivo grande demais ({tam / 1e6:.0f} MB; o limite é {limite / 1e6:.0f} MB)"
    elif dim and dim[0] * dim[1] > LIMITE_PIXELS:
        info["problema"] = f"{dim[0] * dim[1] / 1e6:.0f} megapixels (o limite é 100)"
    elif dim and tipo != "image/webp" and max(dim) > LIMITE_LADO:
        info["problema"] = f"{max(dim)} pixels no lado maior (o limite é 12.000)"
    return info


# ------------------------------------------------------------------ HTTP
class _Corpo(io.RawIOBase):
    """Corpo do envio em pedaços, avisando quantos bytes já saíram (barra de progresso)."""

    def __init__(self, dados, ao_ler=None):
        super().__init__()
        self._b = memoryview(dados)
        self._i = 0
        self._ao_ler = ao_ler

    def readable(self):
        return True

    def read(self, n=-1):
        fim = len(self._b) if n is None or n < 0 else min(len(self._b), self._i + n)
        pedaco = self._b[self._i:fim].tobytes()
        self._i = fim
        if self._ao_ler and pedaco:
            self._ao_ler(self._i, len(self._b))
        return pedaco


def _erro_http(status, bruto, cabecalhos):
    e = {}
    try:
        e = (json.loads((bruto or b"").decode("utf-8", "replace")) or {}).get("error") or {}
    except (ValueError, AttributeError):
        e = {}
    codigo = e.get("code") or {401: "unauthorized", 402: "insufficient_credits", 404: "not_found", 413: "photo_too_large",
                               415: "unsupported_media_type", 425: "head_not_ready", 429: "rate_limited",
                               503: "service_unavailable"}.get(status) or ("internal_error" if status >= 500 else "invalid_request")
    espera = None
    try:
        espera = float((cabecalhos or {}).get("Retry-After") or 0) or None
    except (TypeError, ValueError):
        espera = None
    original = e.get("message") or ""
    if not e and status == 413:
        original = "O pedido passou de 100 MB."
    return ErroKeenFace(codigo, original, status=status, campo=e.get("field"), sugestao=e.get("suggestion"),
                        request_id=e.get("request_id") or (cabecalhos or {}).get("X-Request-Id"), espera=espera)


class Cliente:
    def __init__(self, chave, parar=None):
        self.chave = (chave or "").strip()
        self.parar = parar          # threading.Event: cancela as esperas

    def _pedido(self, metodo, caminho, consulta=None, json_corpo=None, dados=None, tipo=None, cabecalhos=None,
                timeout=60, tentativas=4, ao_enviar=None, retentaveis=RETENTAVEIS):
        if not self.chave:
            raise ErroKeenFace("sem_chave")
        url = API + caminho + ("?" + urllib.parse.urlencode(consulta) if consulta else "")
        erro = None
        for n in range(tentativas + 1):
            h = {"Authorization": "Bearer " + self.chave, "User-Agent": UA, "Accept": "application/json"}
            corpo = None
            if json_corpo is not None:
                corpo = json.dumps(json_corpo).encode("utf-8")
                h["Content-Type"] = "application/json"
            elif dados is not None:
                corpo = _Corpo(dados, ao_enviar)
                h["Content-Type"] = tipo
                h["Content-Length"] = str(len(dados))
            h.update(cabecalhos or {})
            req = urllib.request.Request(url, data=corpo, method=metodo, headers=h)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    bruto = r.read()
                    if not bruto.strip():
                        return r.status, None
                    try:
                        return r.status, json.loads(bruto.decode("utf-8"))
                    except ValueError:
                        raise ErroKeenFace("resposta_invalida", bruto[:200].decode("utf-8", "replace"), status=r.status) from None
            except urllib.error.HTTPError as ex:
                erro = _erro_http(ex.code, ex.read(), ex.headers)
            except (urllib.error.URLError, OSError) as ex:
                motivo = getattr(ex, "reason", None) or ex
                erro = ErroKeenFace("rede", str(motivo))
            if erro.codigo not in retentaveis or n == tentativas:
                raise erro
            dormir(min(60.0, erro.espera or 2.0 * 2 ** n), self.parar)
        raise erro

    # ---------------------------------------------------------------- conta e cabeças
    def conta(self):
        """{credits, held_credits, prices: {head, file}}: credits já desconta o que está reservado."""
        return self._pedido("GET", "/account", timeout=30, tentativas=1)[1]

    def listar(self, limite=50):
        return (self._pedido("GET", "/heads", consulta={"limit": limite}, timeout=30, tentativas=1)[1] or {}).get("data") or []

    def cabeca(self, id_, espera=0):
        consulta = {"wait": int(espera)} if espera else None
        return self._pedido("GET", "/heads/" + urllib.parse.quote(id_), consulta=consulta, timeout=espera + 45)[1]

    def apagar(self, id_):
        self._pedido("DELETE", "/heads/" + urllib.parse.quote(id_), timeout=30, tentativas=2)

    # ---------------------------------------------------------------- fotos e criação
    def enviar_foto(self, caminho, ao_enviar=None):
        with open(caminho, "rb") as f:
            dados = f.read()
        tipo = tipo_da_foto(dados[:4096], caminho)
        if not tipo:
            raise ErroKeenFace("unsupported_media_type")
        r = self._pedido("POST", "/photos", dados=dados, tipo=tipo, ao_enviar=ao_enviar, timeout=120, tentativas=3)[1]
        if not r or not str(r.get("id", "")).startswith("ph_"):
            raise ErroKeenFace("resposta_invalida", json.dumps(r)[:200])
        return r["id"]

    def apagar_foto(self, ph):
        self._pedido("DELETE", "/photos/" + urllib.parse.quote(ph), timeout=20, tentativas=1)

    @staticmethod
    def corpo_criacao(ids, opcoes):
        """JSON do pedido. Padrão: só as fotos (as opções do Scan dão 400 field_not_applicable no Padrão)."""
        corpo = {"photos": list(ids)}
        if (opcoes or {}).get("modo") == "scan":
            corpo["scan_reconstruction"] = True
            corpo["texture"] = "raw" if opcoes.get("textura") == "raw" else "pbr"
            if corpo["texture"] == "pbr":
                corpo["cleanup"] = bool(opcoes.get("limpeza", True))
            lente = str(opcoes.get("lente") or "").strip().replace(",", ".")
            if lente in ("", "auto"):
                corpo["focal_length"] = "auto"
            elif lente == "auto_common":
                corpo["focal_length"] = "auto_common"
            else:
                v = float(lente)
                corpo["focal_length"] = int(v) if v.is_integer() else v
        return corpo

    def orcamento(self, ids, opcoes):
        """dry run: {credits: {cost, balance, sufficient}, photo_count, …}. Não cria nem cobra nada."""
        return self._pedido("POST", "/heads", consulta={"dry_run": "true"}, json_corpo=self.corpo_criacao(ids, opcoes),
                            timeout=60)[1]

    def criar(self, ids, opcoes, chave_idem):
        """Cria a cabeça. A mesma Idempotency-Key em até 24 h devolve a mesma cabeça sem cobrar de novo."""
        return self._pedido("POST", "/heads", json_corpo=self.corpo_criacao(ids, opcoes),
                            cabecalhos={"Idempotency-Key": chave_idem}, timeout=120, tentativas=5,
                            retentaveis=RETENTAVEIS | {"idempotency_conflict"})[1]

    # ---------------------------------------------------------------- arquivos
    def link_modelo(self, id_, formato="glb", textura="jpg", ao_esperar=None):
        """Pede o arquivo até ele ficar pronto (a 1ª vez de cada formato leva ~20–40 s). -> link assinado"""
        consulta = {"mesh_format": formato, "texture": textura}
        for _ in range(60):
            r = self._pedido("GET", f"/heads/{urllib.parse.quote(id_)}/model", consulta=consulta, timeout=60)[1] or {}
            ev, d = r.get("event"), r.get("data") or {}
            if ev == "redirect" and d.get("url"):
                return d["url"]
            if ev != "retry-after":
                raise ErroKeenFace("resposta_invalida", json.dumps(r)[:200])
            espera = max(6.0, float(d.get("time_sec") or 10))     # até 10 pedidos por minuto por cabeça
            if ao_esperar:
                ao_esperar(espera)
            dormir(espera, self.parar)
        raise ErroKeenFace("timeout", "o arquivo não ficou pronto")

    def baixar(self, url, destino, ao_baixar=None):
        """Baixa o link assinado (sem a chave) para destino (grava em .parcial e renomeia no fim)."""
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        parcial = destino + ".parcial"
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(parcial, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                feito = 0
                while True:
                    if self.parar is not None and self.parar.is_set():
                        raise Cancelado()
                    bloco = r.read(256 * 1024)
                    if not bloco:
                        break
                    f.write(bloco)
                    feito += len(bloco)
                    if ao_baixar:
                        ao_baixar(feito, total)
            os.replace(parcial, destino)
        except urllib.error.HTTPError as ex:
            raise ErroKeenFace("rede", f"download recusado (HTTP {ex.code})") from None
        except (urllib.error.URLError, OSError) as ex:
            raise ErroKeenFace("rede", str(getattr(ex, "reason", None) or ex)) from None
        finally:
            if os.path.exists(parcial):
                try:
                    os.remove(parcial)
                except OSError:
                    pass
        return destino

    def baixar_modelo(self, id_, destino, formato="glb", textura="jpg", ao_esperar=None, ao_baixar=None):
        url = self.link_modelo(id_, formato, textura, ao_esperar)
        try:
            return self.baixar(url, destino, ao_baixar)
        except ErroKeenFace as ex:
            if ex.codigo != "rede":
                raise
            # o link vale só 20 s para começar: pede outro e tenta mais uma vez
            return self.baixar(self.link_modelo(id_, formato, textura, ao_esperar), destino, ao_baixar)
