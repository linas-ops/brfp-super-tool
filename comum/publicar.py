"""BRFP Super Tool — publica a versão atual no GitHub (github.com/linas-ops/brfp-super-tool) para os colegas atualizarem.

    python comum\\publicar.py [--notas "texto"] [--sem-release] [--substituir]

1. cria o repositório público na primeira vez (com a conta do GitHub já salva no Git deste computador)
2. grava o código (o que o .gitignore deixa) num commit e envia (git push)
3. gera o pacote leve, sem os modelos tirados do jogo, e publica a Release v<VERSAO> com ele anexado

Antes de publicar uma versão nova: suba o VERSAO do supertool.py e escreva as novidades no começo do NOVIDADES_ST
(web/hub.js); elas viram o texto da Release se --notas não for passado. O Super Tool dos colegas avisa no Início e
atualiza com um clique (comum/atualizacao.py).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

COMUM = os.path.dirname(os.path.abspath(__file__))
SUPERTOOL = os.path.dirname(COMUM)
sys.path.insert(0, COMUM)

import atualizacao  # noqa: E402
import pacote  # noqa: E402

DONO, NOME_REPO = atualizacao.REPO.split("/")
DESCRICAO = "BRFP Super Tool: ferramentas de modding do BRFP (EA SPORTS FC 26 / FC 27) numa janela só."
# modelos e foto tirados do jogo: ficam fora do repositório e do pacote públicos
FORA_DO_PUBLICO = ("ferramentas/corpos/motor/referencia/", "ferramentas/faces/motor/referencia/",
                   "ferramentas/kits/motor/referencia/", "ferramentas/minifaces/web/referencia_p158023.png")


def git(*args, entrada=None):
    r = subprocess.run(["git", *args], cwd=SUPERTOOL, input=entrada, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} falhou:\n{r.stderr or r.stdout}")
    return r.stdout


def token():
    saida = git("credential", "fill", entrada="protocol=https\nhost=github.com\n\n")
    for linha in saida.splitlines():
        if linha.startswith("password="):
            return linha.split("=", 1)[1]
    raise SystemExit("Não achei a conta do GitHub salva no Git deste computador (faça um git push uma vez para salvar).")


def gh(metodo, url, dados=None, tk=None, binario=None, tipo="application/json"):
    corpo = binario if binario is not None else (json.dumps(dados).encode() if dados is not None else None)
    req = urllib.request.Request(url if url.startswith("http") else "https://api.github.com" + url, data=corpo, method=metodo,
                                 headers={"Authorization": f"Bearer {tk}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "BRFP-Super-Tool", "Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as ex:
        if ex.code == 404 and metodo == "GET":
            return None
        raise SystemExit(f"GitHub {metodo} {url}: {ex.code} {ex.read().decode(errors='replace')[:400]}")


def versao():
    return pacote._versao()


def notas_padrao(v):
    with open(os.path.join(SUPERTOOL, "web", "hub.js"), encoding="utf-8") as fh:
        m = re.search(r"NOVIDADES_ST = '(.*?)';", fh.read())
    texto = m.group(1) if m else ""
    m = re.search(rf"v{re.escape(v)}:\s*(.*?)(?:\s+v\d+(?:\.\d+)*:|$)", texto)
    return m.group(1).strip() if m else f"BRFP Super Tool {v}"


def zip_publico(destino, v):
    arq = os.path.join(destino, f"BRFP Super Tool {v} - leve.zip")
    with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for c, nome, _ in pacote.lista("leve"):
            rel = nome.split("/", 1)[1]
            if rel.startswith(FORA_DO_PUBLICO):
                continue
            z.write(c, nome)
    return arq


def main():
    ap = argparse.ArgumentParser(description="Publica a versão atual do BRFP Super Tool no GitHub")
    ap.add_argument("--notas", help="texto da Release (padrão: as novidades da versão no NOVIDADES_ST)")
    ap.add_argument("--sem-release", action="store_true", help="só envia o código")
    ap.add_argument("--substituir", action="store_true", help="troca o pacote de uma Release que já existe (correção rápida)")
    a = ap.parse_args()
    v = versao()
    tk = token()

    if not gh("GET", f"/repos/{DONO}/{NOME_REPO}", tk=tk):
        print(f"Criando o repositório público {DONO}/{NOME_REPO}…")
        gh("POST", "/user/repos", {"name": NOME_REPO, "description": DESCRICAO, "private": False,
                                   "homepage": f"https://github.com/{DONO}/{NOME_REPO}/releases/latest"}, tk=tk)

    if not os.path.isdir(os.path.join(SUPERTOOL, ".git")):
        git("init", "-b", "main")
    if "origin" not in git("remote").split():
        git("remote", "add", "origin", f"https://github.com/{DONO}/{NOME_REPO}.git")
    git("add", "-A")
    if git("status", "--porcelain").strip():
        git("commit", "-m", f"Versão {v}")
    git("push", "-u", "origin", "main")
    print(f"Código enviado: https://github.com/{DONO}/{NOME_REPO}")
    if a.sem_release:
        return

    tag = f"v{v}"
    rel = gh("GET", f"/repos/{DONO}/{NOME_REPO}/releases/tags/{tag}", tk=tk)
    if rel and not a.substituir:
        raise SystemExit(f"A Release {tag} já existe. Suba o VERSAO do supertool.py antes de publicar de novo "
                         "(ou use --substituir para trocar só o pacote dela).")
    with tempfile.TemporaryDirectory() as tmp:
        print("Gerando o pacote leve…")
        arq = zip_publico(tmp, v)
        if rel:
            for velho in rel.get("assets") or []:
                gh("DELETE", f"/repos/{DONO}/{NOME_REPO}/releases/assets/{velho['id']}", tk=tk)
        else:
            rel = gh("POST", f"/repos/{DONO}/{NOME_REPO}/releases", {"tag_name": tag, "target_commitish": "main",
                     "name": f"BRFP Super Tool {v}", "body": a.notas or notas_padrao(v)}, tk=tk)
        nome = os.path.basename(arq)
        with open(arq, "rb") as fh:
            gh("POST", rel["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(nome), tk=tk, binario=fh.read(),
               tipo="application/zip")
    print(f"Release publicada: {rel['html_url']}")


if __name__ == "__main__":
    main()
