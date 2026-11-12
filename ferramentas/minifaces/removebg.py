"""Cliente do remove.bg (API v1.0) para o Criador de Minifaces — só biblioteca padrão.

- A chave é a da conta de cada usuário (remove.bg › Dashboard › API Keys) e fica no preferencias.json desta ferramenta
  (fora do git e do pacote).
- Cada foto vai uma vez só: o recorte volta como PNG com transparência e fica guardado em cache/removebg/, com a região da
  foto que foi mandada. Mudar zoom, posição, limpeza ou pincel não chama a API de novo.
- Manda só a região da cabeça e dos ombros, reduzida para até 0,25 megapixel (tamanho "preview"), o que basta para a
  miniface de 180 px e é o tamanho das chamadas grátis do plano gratuito.
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

URL = "https://api.remove.bg/v1.0/"
LINKS = {"chave": "https://www.remove.bg/dashboard#api-key", "precos": "https://www.remove.bg/pricing",
         "api": "https://www.remove.bg/api"}
PREVIEW_MP = 0.25e6          # tamanho "preview": até 0,25 megapixel
AGENTE = "BRFP-Super-Tool-Minifaces"


class ErroRemoveBg(Exception):
    def __init__(self, codigo, msg, status=None, espera=None):
        super().__init__(msg)
        self.codigo, self.status, self.espera = codigo, status, espera


def _multipart(campos, arquivo):
    """corpo multipart/form-data com os campos de texto e um arquivo (nome, bytes, tipo)"""
    sep = "----brfp" + uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{sep}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    nome, dados, tipo = arquivo
    partes.append(f'--{sep}\r\nContent-Disposition: form-data; name="image_file"; filename="{nome}"\r\n'
                  f"Content-Type: {tipo}\r\n\r\n".encode() + dados + b"\r\n")
    partes.append(f"--{sep}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={sep}"


def _erro_http(ex):
    """HTTPError do remove.bg -> ErroRemoveBg com mensagem em português"""
    try:
        corpo = json.loads(ex.read().decode("utf-8", "replace"))
        e0 = (corpo.get("errors") or [{}])[0]
        detalhe = e0.get("title") or e0.get("detail") or ""
        cod_api = e0.get("code") or ""
    except (ValueError, OSError, AttributeError):
        detalhe, cod_api = "", ""
    st = ex.code
    if st == 403 or cod_api in ("auth_failed", "unauthorized"):
        return ErroRemoveBg("chave", "O remove.bg recusou a chave da API. Confira em remove.bg › Dashboard › API Keys e cole de novo.", st)
    if st == 402 or cod_api == "insufficient_credits":
        return ErroRemoveBg("creditos", "Acabaram as chamadas grátis do mês e os créditos da sua conta do remove.bg.", st)
    if st == 429:
        try:
            espera = int(ex.headers.get("Retry-After") or 0)
        except (TypeError, ValueError):
            espera = 0
        return ErroRemoveBg("limite", f"O remove.bg pediu para esperar um pouco (limite de chamadas por minuto)"
                            f"{f': tente de novo em {espera} s' if espera else ''}.", st, espera)
    if st == 400:
        if "foreground" in detalhe.lower():
            return ErroRemoveBg("sem_pessoa", "O remove.bg não achou o jogador nesta foto (nada em primeiro plano).", st)
        return ErroRemoveBg("foto", f"O remove.bg não aceitou esta foto{': ' + detalhe if detalhe else ''}.", st)
    return ErroRemoveBg("servidor", f"O remove.bg respondeu com erro {st}{': ' + detalhe if detalhe else ''}. Tente de novo.", st)


def _pedir(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers
    except urllib.error.HTTPError as ex:
        raise _erro_http(ex) from None
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        motivo = getattr(ex, "reason", ex)
        raise ErroRemoveBg("conexao", f"Sem conexão com o remove.bg ({motivo}).") from None


def remover_fundo(chave, dados, nome="foto.jpg", tipo_mime="image/jpeg", tamanho="preview", timeout=90):
    """Manda a imagem e devolve (PNG com transparência, informações dos cabeçalhos)."""
    corpo, ctype = _multipart({"size": tamanho, "type": "person", "format": "png"}, (nome, dados, tipo_mime))
    req = urllib.request.Request(URL + "removebg", data=corpo, method="POST",
                                 headers={"X-Api-Key": chave, "Content-Type": ctype, "Accept": "image/png, application/json",
                                          "User-Agent": AGENTE})
    png, cab = _pedir(req, timeout)
    if not png.startswith(b"\x89PNG"):
        raise ErroRemoveBg("resposta", "O remove.bg devolveu uma resposta que não é uma imagem PNG.")
    info = {"creditos": cab.get("X-Credits-Charged"), "tipo": cab.get("X-Type"),
            "largura": cab.get("X-Width"), "altura": cab.get("X-Height")}
    return png, info


def conta(chave, timeout=20):
    """Saldo da conta: {"creditos": total, "gratis": chamadas grátis restantes, "tamanhos": ...} (o que vier)."""
    req = urllib.request.Request(URL + "account", headers={"X-Api-Key": chave, "Accept": "application/json",
                                                           "User-Agent": AGENTE})
    corpo, _ = _pedir(req, timeout)
    try:
        at = (json.loads(corpo.decode("utf-8")).get("data") or {}).get("attributes") or {}
    except ValueError:
        raise ErroRemoveBg("resposta", "Resposta estranha do remove.bg ao ler o saldo da conta.") from None
    cr, api = at.get("credits") or {}, at.get("api") or {}
    return {"creditos": cr.get("total"), "gratis": api.get("free_calls"), "tamanhos": api.get("sizes"),
            "quando": time.time()}


# ------------------------------------------------------------------ cache dos recortes
class Cache:
    """cache/removebg/<hash>.png + <hash>.json ({"foto": sha1 do arquivo, "regiao": [x, y, w, h], "escala", ...})"""

    def __init__(self, pasta):
        self.pasta = pasta
        self.lock = threading.Lock()
        self.idx = None            # sha1 da foto -> [entradas]
        self.hashes = {}           # (caminho, mtime, tamanho) -> sha1

    def hash_foto(self, caminho):
        st = os.stat(caminho)
        k = (os.path.normcase(caminho), st.st_mtime, st.st_size)
        h = self.hashes.get(k)
        if not h:
            sha = hashlib.sha1()
            with open(caminho, "rb") as f:
                for bloco in iter(lambda: f.read(1 << 20), b""):
                    sha.update(bloco)
            h = self.hashes[k] = sha.hexdigest()
        return h

    def _carregar(self):
        if self.idx is not None:
            return
        self.idx = {}
        if not os.path.isdir(self.pasta):
            return
        for n in os.listdir(self.pasta):
            if not n.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.pasta, n), encoding="utf-8") as f:
                    e = json.load(f)
            except (OSError, ValueError):
                continue
            e["arquivo"] = os.path.join(self.pasta, n[:-5] + ".png")
            if os.path.isfile(e["arquivo"]):
                self.idx.setdefault(e.get("foto"), []).append(e)

    def achar(self, foto, regiao, escala_min):
        """recorte já feito desta foto que cobre a região (com resolução suficiente)"""
        x, y, w, h = regiao
        with self.lock:
            self._carregar()
            boas = [e for e in self.idx.get(foto, []) if os.path.isfile(e["arquivo"]) and e["regiao"][0] <= x + 1 and
                    e["regiao"][1] <= y + 1 and e["regiao"][0] + e["regiao"][2] >= x + w - 1 and
                    e["regiao"][1] + e["regiao"][3] >= y + h - 1 and e.get("escala", 1) >= escala_min * 0.8]
        return max(boas, key=lambda e: e.get("quando", 0)) if boas else None

    def guardar(self, foto, regiao, escala, png, info):
        os.makedirs(self.pasta, exist_ok=True)
        nome = hashlib.sha1(json.dumps([foto, regiao, round(escala, 4)]).encode()).hexdigest()[:24]
        arq = os.path.join(self.pasta, nome + ".png")
        with open(arq + ".parcial", "wb") as f:
            f.write(png)
        os.replace(arq + ".parcial", arq)
        e = {"foto": foto, "regiao": list(regiao), "escala": escala, "quando": time.time(), **info}
        with open(os.path.join(self.pasta, nome + ".json"), "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False)
        e["arquivo"] = arq
        with self.lock:
            self._carregar()
            self.idx.setdefault(foto, []).append(e)
        return e
