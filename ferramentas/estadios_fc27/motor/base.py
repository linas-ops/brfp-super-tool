"""Base do motor: pastas, mensagens de progresso, erros e utilitários comuns.

Protocolo de progresso (lido pelo servidor.py, uma linha por evento, sempre com flush):
  @@ETAPA <id>|<descrição>       começa uma etapa
  @@PROGRESSO <0-100>|<texto>     andamento da etapa atual
  @@AVISO <texto>                 algo que o usuário deve saber, sem parar
  @@RESULTADO <json>              resultado final (uma vez, no fim)
  @@ERRO <texto>                  falha que parou o trabalho
Linhas sem prefixo são registro técnico.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

MOTOR = Path(__file__).resolve().parent
FERRAMENTA = MOTOR.parent
BIN = MOTOR / 'bin'
CACHE = FERRAMENTA / 'cache'
PREFS = FERRAMENTA / 'preferencias.json'
ZERO = '00000000-0000-0000-0000-000000000000'
PREFIX = 'fc/fcgame/main/'
NS = uuid.UUID('6f1a3c52-4d1e-5b0a-9c7e-466702466702')  # o mesmo das duplicatas 702 e 703 confirmadas em partida

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


class Falha(Exception):
    """Erro com mensagem para o usuário: o trabalho para e nada é publicado."""


def falha(msg):
    raise Falha(msg)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def sha256_arquivo(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def md5_guid(name):
    return str(uuid.UUID(bytes_le=hashlib.md5(name.lower().encode('utf8')).digest()))


def ler_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def gravar_json(p, d, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(d, indent=indent, ensure_ascii=False, default=str), encoding='utf8')
    os.replace(tmp, p)


def walk_strings(v, out):
    if isinstance(v, dict):
        for y in v.values():
            walk_strings(y, out)
    elif isinstance(v, list):
        for y in v:
            walk_strings(y, out)
    elif isinstance(v, str):
        out.append(v)


# ------------------------------------------------------------------ progresso
_t0 = {}


def etapa(ident, descricao):
    _t0['etapa'] = time.time()
    print(f'@@ETAPA {ident}|{descricao}', flush=True)


def progresso(pct, texto=''):
    print(f'@@PROGRESSO {max(0, min(100, int(pct)))}|{texto}', flush=True)


def aviso(texto):
    print(f'@@AVISO {texto}', flush=True)


def log(texto):
    print(texto, flush=True)


def resultado(d):
    print('@@RESULTADO ' + json.dumps(d, ensure_ascii=False, default=str), flush=True)


def erro(texto):
    print('@@ERRO ' + str(texto).replace('\n', ' | '), flush=True)


def prefs():
    try:
        return ler_json(PREFS)
    except (OSError, ValueError):
        return {}


def gravar_prefs(**kw):
    d = prefs()
    d.update(kw)
    gravar_json(PREFS, d)
    return d


RELATORIOS = {'resultado.json', 'relatorio.json', 'verificacao.json', 'apply_result.json', 'report.json', 'subsets.json',
              'textures.json', 'locators.json'}


def limpar_trabalho(pasta):
    """Depois de um trabalho que deu certo: apaga o que só serviu para montar o projeto (payloads, projeto intermediário,
    saídas do SDK, geometria e texturas preparadas, extrações). Ficam os relatórios. Devolve os bytes liberados."""
    pasta = Path(pasta)
    livres = 0
    for p in sorted(pasta.rglob('*'), key=lambda x: -len(x.parts)):
        try:
            if p.is_file():
                if p.name in RELATORIOS:
                    continue
                livres += p.stat().st_size
                p.unlink()
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except OSError:
            pass
    return livres


def pasta_trabalho(nome):
    """Pasta nova em cache/trabalho para um trabalho (nunca reaproveitada)."""
    base = CACHE / 'trabalho'
    base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    n = 0
    while True:
        p = base / f'{stamp}_{nome}' if n == 0 else base / f'{stamp}_{nome}_{n}'
        try:
            p.mkdir()
            return p
        except FileExistsError:
            n += 1
