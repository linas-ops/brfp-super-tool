"""Catálogo dos estádios do FC 27 instalado: ID, pasta, nome no banco, bundles e tamanho (guardado por versão do cache)."""
from __future__ import annotations
import collections
import re

from . import base, t3db
from .duplicar import SLM, SLM_L1, tokens_estadios

# Duplicatas que o usuário já testou em partida com esta ferramenta (o método é o mesmo para qualquer estádio).
CONFIRMADOS = {466: 'duplicado como 702 e testado em partida (30/10/2026)',
               181: 'duplicado como 703 e testado em partida (30/10/2026); base da conversão do FIFA 16'}
BASE_FIFA16 = 181


def nomes_db(amb):
    db = amb.db_nativo()
    p = amb.pasta_jogo() / 'db' / 'fifa_ng_db.db'
    _, tables = t3db.read_db(str(p), str(amb.meta_db()))
    t = next(x for x in tables if x.name == 'stadiums')
    fn = [f.name for f in t.fields]
    out = {}
    for r in t.rows:
        d = dict(zip(fn, r))
        try:
            out[int(d['stadiumid'])] = dict(nome=d.get('name', ''), time=int(d.get('hometeamid') or 0))
        except ValueError:
            continue
    return out


def catalogo(amb, forcar=False):
    p = amb.pasta_jogo() / 'catalogo.json'
    if p.is_file() and not forcar:
        return base.ler_json(p)
    c = amb.indice()
    work = base.pasta_trabalho('catalogo')
    dumps = amb.dumps([SLM, SLM_L1], work)
    slm = {int(i['KeyId']): i['SubWorldName'] for i in dumps[SLM.lower()]['instances'][0]['fields']['SublevelItems']}
    l1 = {int(i['KeyId']) for i in dumps[SLM_L1.lower()]['instances'][0]['fields']['SublevelItems']}
    toks = tokens_estadios(c)
    db = nomes_db(amb)
    por_bundle = collections.defaultdict(lambda: [0, 0, 0, 0])
    idx_tok = {}
    for b in c['bundles']:
        m = re.match(r'fc/fcgame/main/content/worlds/stadiums/([a-z0-9_]+)/', b['name'])
        if m:
            idx_tok[b['index']] = m.group(1)
    for kind, lst in (('ebx', c['ebx']), ('res', c['res']), ('chunk', c['chunks'])):
        k = {'ebx': 0, 'res': 1, 'chunk': 2}[kind]
        for e in lst:
            vistos = {idx_tok[i] for i in e['bundles'] if i in idx_tok}
            for t in vistos:
                por_bundle[t][k] += 1
                por_bundle[t][3] += e.get('original_size') or e.get('logical_size') or e.get('size', 0)
    nb = collections.Counter(idx_tok.values())
    estadios = []
    for sid, nivel in sorted(slm.items()):
        tok = toks.get(sid)
        if not tok or nivel.lower() != f'content/worlds/stadiums/{tok}/{tok}':
            continue
        st = por_bundle.get(tok, [0, 0, 0, 0])
        d = db.get(sid, {})
        estadios.append(dict(id=sid, token=tok, nivel=nivel, nome=d.get('nome') or tok, time_casa=d.get('time', 0),
                             no_banco=sid in db, layer1=sid in l1, bundles=nb.get(tok, 0), ebx=st[0], res=st[1], chunks=st[2],
                             mb=round(st[3] / 2**20, 1), confirmado=CONFIRMADOS.get(sid), base_fifa16=sid == BASE_FIFA16))
    usados = sorted(set(slm) | set(db))
    out = dict(cache=amb.chave_cache(), estadios=estadios, ids_usados=usados, base_fifa16=BASE_FIFA16)
    base.gravar_json(p, out)
    return out


def ids_livres(cat, n, a_partir=700, evitar=()):
    usados = set(cat['ids_usados']) | set(evitar)
    out, x = [], a_partir
    while len(out) < n:
        if x not in usados:
            out.append(x)
        x += 1
    return out
