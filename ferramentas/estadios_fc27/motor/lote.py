"""Conversão em lote: vários estádios do FIFA 16 e do PES 2021, um depois do outro, cada um sobre uma duplicata do El
Grandioso (o mesmo caminho da conversão de um estádio só: motor/fifa16/converter.py e motor/pes21/converter.py).

- procurar(pasta): os estádios dentro de uma pasta e das subpastas dela. FIFA 16: data\\sceneassets\\stadium\\
  stadium_<id>.rx3; PES 2021: Asset\\model\\bg\\st<número>\\#Win\\st<número>.fpk (um pacote como o "Brasil MEGA Stadium
  Pack" tem uma pasta dessas para cada estádio, e muitos usam o mesmo número). O nome sugerido é o da pasta do estádio,
  sem o prefixo de país ("BRA - "). Um estádio dentro da pasta de outro (o "AddOn" de exterior do Camp Nou, uma cópia
  esquecida dentro de outro mod) vem como não sugerido. Arquivos compactados (.rar, .zip, .7z) ficam de fora e são
  listados.
- lote(amb, cfg): converte os escolhidos.
  - modo "junto" (padrão): um projeto só. Cada estádio entra no projeto dos anteriores (o projeto parcial vira o
    projeto-base do próximo, como em "Adicionar a um projeto existente"); o primeiro parte do projeto-base escolhido ou
    do zero. É o jeito de jogar com vários estádios convertidos, porque no FET só um projeto de estádio fica ativo por
    vez (todos mexem no mapa de estádios, nos loaders e no banco).
  - modo "separados": um projeto para cada estádio, na pasta escolhida.
  Um estádio que falha (ou cujo projeto não passa na verificação) fica de fora, e os outros seguem. Os nomes de tudo o
  que a conversão cria levam o ID novo (content/worlds/stadiums/<família>_<ID>/..., GUIDs e chaves de shader), então
  dois estádios com o mesmo número no jogo de origem não colidem no mesmo projeto.

cfg: itens = [{origem: "fifa16" | "pes21", pasta, novo_id, nome, receita (opcional)}], modo, saida (junto) ou
pasta_saida (separados), projeto_base (opcional, só junto), receita (ajustes para todos: rede_gol, banners,
luzes_torcida, personagens, reservas...).
"""
from __future__ import annotations
import os
import re
import shutil
import time
import traceback
import unicodedata
from pathlib import Path

from . import base
from .base import falha

COMPACTADOS = ('.rar', '.zip', '.7z')
PROFUNDIDADE = 12      # níveis de subpastas olhados a partir da pasta escolhida
MAX_COMPACTADOS = 60   # quantos arquivos compactados entram na lista (o total vai à parte)
MAX_NOME = 63          # bytes do nome no banco (stadiums.name)


def nome_sugerido(pasta):
    """Nome do estádio a partir do nome da pasta dele: sem o prefixo de país ("BRA - Allianz Parque") e sem "_"."""
    n = re.sub(r'^[A-Za-z]{2,3}\s*-\s+', '', pasta.strip())
    n = re.sub(r'[_\s]+', ' ', n).strip() or 'Estádio'
    while len(n.encode('utf8')) > MAX_NOME:
        n = n[:-1].rstrip()
    return n


def _mod_pes(st):
    """Pasta do mod de um estádio do PES (a que tem Asset\\model\\bg\\st<número>)."""
    bg = st.parent
    if bg.name.lower() == 'bg' and bg.parent.name.lower() == 'model':
        a = bg.parent.parent
        return a.parent if a.name.lower() == 'asset' else a
    return st.parent


def _pasta_fifa16(sa):
    """Pasta a converter de um estádio do FIFA 16 a partir da pasta sceneassets (motor/fifa16/analise.localizar)."""
    if sa.name.lower() == 'sceneassets':
        return sa.parent.parent if sa.parent.name.lower() == 'data' else sa.parent
    return sa


def _relativo(p, raiz):
    try:
        r = str(p.relative_to(raiz))
    except ValueError:
        return str(p)
    return raiz.name if r == '.' else r


def procurar(raiz):
    """{raiz, estadios: [{origem, pasta, fonte_id, nome, rotulo, problema?, nota?, sugerido?}], compactados,
    total_compactados}. problema = não dá para converter; sugerido False = melhor conferir antes (nota diz por quê)."""
    raiz = Path(raiz).resolve()
    if not raiz.is_dir():
        falha('pasta não encontrada: ' + str(raiz))
    fifa, pes, compactados = {}, {}, []
    for dp, dns, fns in os.walk(raiz):
        d = Path(dp)
        if len(d.relative_to(raiz).parts) >= PROFUNDIDADE:
            dns[:] = []
        compactados += [str((d / f).relative_to(raiz)) for f in fns if f.lower().endswith(COMPACTADOS)]
        if d.name.lower() == 'stadium':
            ids = sorted({int(m.group(1)) for f in fns for m in [re.fullmatch(r'stadium_(\d+)\.rx3', f, re.I)] if m})
            if ids:
                fifa[d.parent] = (ids, {f.lower() for f in fns})
                dns[:] = []
                continue
        if re.fullmatch(r'st\d+', d.name, re.I) and d.parent.name.lower() == 'bg' and (d / '#Win' / f'{d.name}.fpk').is_file():
            pes.setdefault(_mod_pes(d), []).append(d)
            dns[:] = []
            continue
        dns[:] = sorted(x for x in dns if not x.startswith('.'))
    out = []
    for sa, (ids, arqs) in fifa.items():
        pasta = _pasta_fifa16(sa)
        for sid in ids:
            e = dict(origem='fifa16', pasta=str(pasta), fonte_id=sid, rotulo=_relativo(pasta, raiz), nome=nome_sugerido(pasta.name),
                     _mod=pasta)
            if len(ids) > 1:
                e['problema'] = (f'a pasta tem mais de um estádio do FIFA 16 ({", ".join(map(str, ids))}): separe cada um numa '
                                 'pasta própria')
            elif f'stadium_{sid}_1_textures.rx3' not in arqs:
                e['problema'] = f'falta stadium_{sid}_1_textures.rx3 (as texturas de dia)'
            out.append(e)
    for mod, sts in pes.items():
        for st in sorted(sts, key=lambda x: x.name.lower()):
            nome = nome_sugerido(mod.name)
            if len(sts) > 1:
                nome = nome_sugerido(f'{nome} ({st.name.lower()})')
            out.append(dict(origem='pes21', pasta=str(st), fonte_id=st.name.lower(), rotulo=_relativo(mod, raiz), nome=nome, _mod=mod))
    mods = {e['_mod'] for e in out}
    for e in out:
        dono = next((m for m in mods if m != e['_mod'] and m in e['_mod'].parents), None)
        if dono is not None:
            e['nota'] = f'fica dentro da pasta de outro estádio ({_relativo(dono, raiz)}): pode ser um complemento dele'
            e['sugerido'] = False
        del e['_mod']
    out.sort(key=lambda e: (e['rotulo'].lower(), str(e['fonte_id'])))
    compactados.sort(key=str.lower)
    return dict(raiz=str(raiz), estadios=out, compactados=compactados[:MAX_COMPACTADOS], total_compactados=len(compactados))


def nome_de_arquivo(novo_id, nome):
    s = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_')
    return f'Estadio_{int(novo_id)}_{s}.fifaproject' if s else f'Estadio_{int(novo_id)}.fifaproject'


def _livre(p):
    """O caminho p, ou p com _2, _3... se já existir (a ferramenta nunca sobrescreve um projeto)."""
    if not p.exists():
        return p
    k = 2
    while (p.with_name(f'{p.stem}_{k}{p.suffix}')).exists():
        k += 1
    return p.with_name(f'{p.stem}_{k}{p.suffix}')


def lote(amb, cfg):
    itens = cfg.get('itens') or []
    if not itens:
        falha('nenhum estádio no lote')
    ids = [int(i['novo_id']) for i in itens]
    rep = sorted({x for x in ids if ids.count(x) > 1})
    if rep:
        falha('IDs novos repetidos no lote: ' + ', '.join(map(str, rep)))
    junto = (cfg.get('modo') or 'junto') == 'junto'
    if junto:
        saida = Path(cfg['saida']).resolve()
        if saida.exists():
            falha('o arquivo de saída já existe: ' + str(saida))
        saida.parent.mkdir(parents=True, exist_ok=True)
    else:
        saida = Path(cfg['pasta_saida']).resolve()
        saida.mkdir(parents=True, exist_ok=True)
    work = Path(cfg.get('trabalho') or base.pasta_trabalho('lote'))
    work.mkdir(parents=True, exist_ok=True)
    comum = {k: v for k, v in (cfg.get('receita') or {}).items() if v is not None}
    atual = cfg.get('projeto_base') if junto else None   # projeto-base do próximo estádio
    parcial = None                                        # o último projeto parcial (junto), na pasta do lote
    feitos = []
    n = len(itens)
    base.log(f"Lote de {n} estádio{'s' if n > 1 else ''}: " + ('um projeto só, ' + str(saida) if junto else 'um projeto para cada, em ' + str(saida)))
    for k, it in enumerate(itens, 1):
        pes = it.get('origem') == 'pes21'
        nid = int(it['novo_id'])
        base.prefixo_das_etapas(f'e{k}_', f"{k}/{n} {it['nome']}: ")
        destino = work / f'parcial_{k:02d}_{nid}.fifaproject' if junto else _livre(saida / nome_de_arquivo(nid, it['nome']))
        item_work = base.pasta_trabalho('converter')
        c = {('pasta_pes' if pes else 'pasta16'): it['pasta'], 'novo_id': nid, 'nome': it['nome'], 'saida': str(destino),
             'projeto_base': atual, 'receita': dict(comum, **(it.get('receita') or {})), 'trabalho': str(item_work)}
        reg = dict(nome=it['nome'], novo_id=nid, origem='pes21' if pes else 'fifa16', pasta=it['pasta'], trabalho=str(item_work), ok=False)
        t = time.time()
        try:
            if pes:
                from .pes21 import converter as conv
            else:
                from .fifa16 import converter as conv
            res = conv.converter(amb, c)
        except base.Falha as ex:
            reg['erro'] = str(ex)
        except Exception as ex:  # noqa: BLE001 (um estádio com erro não para os outros)
            traceback.print_exc()
            reg['erro'] = f'{type(ex).__name__}: {ex}'
        else:
            res.update(segundos=round(time.time() - t), tipo='converter', lote=str(work))
            reg.update(ok=bool(res['ok']), sha256=res['sha256'], saida=res['saida'], fonte_id=res.get('fifa16_id'))
            if not res['ok']:
                reg['erro'] = f"a verificação do projeto gravado achou {(res.get('verificacao') or {}).get('total_erros', '?')} erro(s)"
                if junto:  # o projeto parcial com erro não entra no projeto final nem fica na lista de projetos gerados
                    res['saida'] = reg['saida'] = None
            base.gravar_json(item_work / 'resultado.json', res)
            if res['ok'] and junto:
                if parcial and parcial.exists():
                    parcial.unlink()
                parcial = atual = destino
        reg['segundos'] = round(time.time() - t)
        # a pasta de trabalho fica só com os relatórios (e some, se o estádio parou antes de gravar algum); um projeto
        # parcial que não entrou no projeto final é apagado
        base.log(f'Pasta de trabalho limpa: {base.limpar_trabalho(item_work) / 2**20:.0f} MB liberados (ficam os relatórios)')
        if not any(item_work.iterdir()):
            item_work.rmdir()
        if junto and destino != parcial and destino.exists():
            destino.unlink()
        if reg['ok']:
            base.aviso(f"pronto em {reg['segundos']} s")
        else:
            base.etapa_falhou(f"{k}/{n} {it['nome']}: ficou de fora" + (' do projeto' if junto else '') + ': ' + reg['erro'])
        feitos.append(reg)
    base.prefixo_das_etapas()
    bons = [r for r in feitos if r['ok']]
    if not bons:
        falha('nenhum estádio foi convertido: ' + ' | '.join(f"{r['nome']}: {r.get('erro')}" for r in feitos))
    sha = None
    if junto:
        base.etapa('lote_gravar', 'Gravando o projeto com todos os estádios')
        shutil.move(str(parcial), str(saida))
        sha = bons[-1]['sha256']
        for r in bons:
            r['saida'] = str(saida)
            f = Path(r['trabalho']) / 'resultado.json'
            try:
                d = base.ler_json(f)
                d['saida'] = str(saida)
                base.gravar_json(f, d)
            except (OSError, ValueError):
                pass
        base.progresso(100, f'{len(bons)} de {n} estádios em {saida.name}')
    res = dict(ok=len(bons) == n, tipo='lote', modo='junto' if junto else 'separados', saida=str(saida), sha256=sha, trabalho=str(work),
               projeto_base=cfg.get('projeto_base') if junto else None, convertidos=len(bons), falharam=n - len(bons),
               nome=', '.join(f"{r['novo_id']} {r['nome']}" for r in bons), itens=feitos)
    base.gravar_json(work / 'lote.json', res)
    return res
