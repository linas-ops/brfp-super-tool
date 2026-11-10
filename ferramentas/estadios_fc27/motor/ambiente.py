"""Ambiente do motor: FIFA Editor Tool, FC 27 instalado, .NET 8, SDK preparado e índice do cache do FET.

Nada do FET ou do jogo vem com a ferramenta: o SDK é tirado do executável do FET do próprio usuário e adaptado ao
.NET 8 numa cópia local (cache/sdk/<chave>); o índice e as extrações nativas ficam em cache/jogo/<chave do cache do
FET>, refeitos sozinhos quando o FET refaz o cache (atualização do jogo).
"""
from __future__ import annotations
import gzip
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import base, cache_fet, fet_bundle
from .base import Falha, falha, sha256, sha256_arquivo
from .cas import Cas

SEM_JANELA = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
SUPERTOOL = base.FERRAMENTA.parent.parent
SDK_DO_BUNDLE = {'Sdk.dll': 'Sdk.dll', 'Serilog.dll': 'Serilog.dll', 'System.IO.Hashing.dll': 'System.IO.Hashing.dll',
                 'Microsoft.IO.RecyclableMemoryStream.dll': 'Microsoft.IO.RecyclableMemoryStream.dll'}
ORDEM_RETARGET = ['Sdk.dll', 'Serilog.dll', 'System.IO.Hashing.dll', 'Microsoft.IO.RecyclableMemoryStream.dll', 'FC27SDK.dll']
FERRAMENTAS_CS = ['StadiumTool', 'ConvertTool']
JOGO_PADRAO = r'C:\Program Files\EA Games\EA SPORTS FC 27'


# ------------------------------------------------------------------ localização
def _candidatos_fet():
    home = Path.home()
    raizes = [Path(os.environ.get('BRFP_RAIZ') or SUPERTOOL.parent), SUPERTOOL.parent.parent, home / 'Downloads', home / 'Desktop',
              home / 'Documents', home / 'OneDrive' / 'Desktop', home / 'OneDrive' / 'Documentos', Path('C:/'), Path('D:/'),
              Path(os.environ.get('ProgramFiles', r'C:\Program Files')), Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))]
    vistos = set()
    for r in raizes:
        try:
            filhos = [r] + [x for x in r.iterdir() if x.is_dir()]
        except OSError:
            continue
        for d in filhos:
            k = os.path.normcase(str(d))
            if k in vistos:
                continue
            vistos.add(k)
            if (d / 'FIFA Editor Tool.exe').is_file() and (d / 'SDKs' / 'FC27SDK.dll').is_file():
                yield d


def achar_fet():
    p = base.prefs().get('fet_dir')
    if p and (Path(p) / 'FIFA Editor Tool.exe').is_file():
        return Path(p)
    achados = sorted(_candidatos_fet(), key=lambda d: (d / 'fc27.cache').stat().st_mtime if (d / 'fc27.cache').is_file() else 0, reverse=True)
    return achados[0] if achados else None


def versao_fet(fet_dir):
    for n in ('FIFA Editor Tool FC27.json', 'FIFA Editor Tool.json'):
        try:
            d = json.loads((Path(fet_dir) / n).read_text(encoding='utf-8-sig'))
            if d.get('LastSavedProgramVersion'):
                return d['LastSavedProgramVersion'], d.get('ExeChangelist')
        except (OSError, ValueError):
            pass
    return None, None


def achar_jogo(fet_dir):
    p = base.prefs().get('jogo_dir')
    if p and (Path(p) / 'FC27.exe').is_file():
        return Path(p)
    if fet_dir:
        try:
            d = json.loads((Path(fet_dir) / 'FIFA Editor Tool.json').read_text(encoding='utf-8-sig'))
            for exe in (d.get('GamesConfig') or {}).get('ExecutablePaths') or []:
                if exe.lower().endswith('fc27.exe') and Path(exe).is_file():
                    return Path(exe).parent
        except (OSError, ValueError):
            pass
    if (Path(JOGO_PADRAO) / 'FC27.exe').is_file():
        return Path(JOGO_PADRAO)
    return None


def achar_dotnet():
    """(dotnet.exe, pasta do Microsoft.NETCore.App 8.x mais novo) ou (exe, None)."""
    exe = shutil.which('dotnet') or os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'dotnet', 'dotnet.exe')
    if not os.path.isfile(exe):
        return None, None
    try:
        out = subprocess.run([exe, '--list-runtimes'], capture_output=True, text=True, timeout=60, creationflags=SEM_JANELA).stdout
    except (OSError, subprocess.TimeoutExpired):
        return exe, None
    vers = []
    for linha in out.splitlines():
        m = re.match(r'Microsoft\.NETCore\.App (8\.\d+\.\d+) \[(.+)\]', linha.strip())
        if m:
            vers.append((tuple(int(x) for x in m.group(1).split('.')), os.path.join(m.group(2), m.group(1))))
    return exe, (max(vers)[1] if vers else None)


# ------------------------------------------------------------------ ambiente
class Ambiente:
    def __init__(self, fet_dir=None, jogo_dir=None):
        self.fet = Path(fet_dir) if fet_dir else achar_fet()
        self.jogo = Path(jogo_dir) if jogo_dir else achar_jogo(self.fet)
        self.dotnet, self.net8 = achar_dotnet()
        self._indice = None
        self._cas = None
        self.versao_fet, self.exe_changelist = versao_fet(self.fet) if self.fet else (None, None)

    # ---------------------------------------------------------- estado (para a interface)
    def estado(self):
        itens = []

        def item(ident, nome, ok, detalhe, caminho=''):
            itens.append(dict(id=ident, nome=nome, ok=bool(ok), detalhe=detalhe, caminho=str(caminho or '')))
        item('fet', 'FIFA Editor Tool', self.fet, f'versão interna {self.versao_fet}' if self.fet else
             'não encontrado: escolha a pasta do FIFA Editor Tool (a que tem o FIFA Editor Tool.exe)', self.fet)
        cache = self.fet / 'fc27.cache' if self.fet else None
        item('cache', 'Cache do FC 27 no FET', cache and cache.is_file(), 'ok' if cache and cache.is_file() else
             'abra o FC 27 no FET uma vez para ele criar o fc27.cache', cache)
        item('jogo', 'EA SPORTS FC 27', self.jogo, 'ok' if self.jogo else 'não encontrado: escolha a pasta do jogo (a que tem o FC27.exe)', self.jogo)
        item('dotnet', '.NET 8 (Runtime)', self.net8, os.path.basename(self.net8) if self.net8 else
             'instale o .NET 8 Runtime (dotnet.microsoft.com/download/dotnet/8.0)', self.net8 or self.dotnet or '')
        prep = self.sdk_pronto()
        item('sdk', 'SDK do FET preparado para .NET 8', prep, 'pronto' if prep else 'é preparado na primeira vez (alguns segundos)',
             self.sdk_dir() if prep else '')
        idx = self.indice_pronto()
        item('indice', 'Índice do cache', idx, 'pronto' if idx else 'é feito na primeira vez (1 a 2 minutos)', self.pasta_jogo() if idx else '')
        return dict(itens=itens, ok=all(i['ok'] for i in itens[:4]), pronto=all(i['ok'] for i in itens))

    def exigir(self):
        if not self.fet:
            falha('FIFA Editor Tool não encontrado. Escolha a pasta dele em Ambiente.')
        if not (self.fet / 'fc27.cache').is_file():
            falha('O FET ainda não tem o fc27.cache: abra o FC 27 no FET uma vez e tente de novo.')
        if not self.jogo:
            falha('FC 27 não encontrado. Escolha a pasta do jogo em Ambiente.')
        if not self.net8:
            falha('Falta o .NET 8 Runtime (dotnet.microsoft.com/download/dotnet/8.0).')
        if not (self.jogo / 'oo2core_9_win64.dll').is_file():
            falha('A pasta do jogo não tem o oo2core_9_win64.dll.')

    # ---------------------------------------------------------- SDK
    def _chave_sdk(self):
        partes = [sha256_arquivo(self.fet / 'FIFA Editor Tool.exe'), sha256_arquivo(self.fet / 'SDKs' / 'FC27SDK.dll')]
        for n in ['PrepararSdk.dll', 'Compat.dll'] + [f'{x}.dll' for x in FERRAMENTAS_CS]:
            partes.append(sha256_arquivo(base.BIN / n))
        return sha256('|'.join(partes).encode())[:16]

    def sdk_dir(self):
        if not hasattr(self, '_sdk_dir'):
            self._sdk_dir = base.CACHE / 'sdk' / self._chave_sdk()
        return self._sdk_dir

    def sdk_pronto(self):
        try:
            return self.fet is not None and (self.sdk_dir() / 'pronto.json').is_file()
        except OSError:
            return False

    def preparar_sdk(self):
        self.exigir()
        dest = self.sdk_dir()
        if (dest / 'pronto.json').is_file():
            return dest
        base.log('Preparando o SDK do FET para .NET 8 em ' + str(dest))
        tmp = dest.with_name(dest.name + '.preparando')
        if tmp.exists():
            shutil.rmtree(tmp)
        orig = tmp / 'original'
        fet_bundle.extrair(self.fet / 'FIFA Editor Tool.exe', orig, SDK_DO_BUNDLE)
        shutil.copy2(self.fet / 'SDKs' / 'FC27SDK.dll', orig / 'FC27SDK.dll')
        out = tmp / 'sdk'
        proc = subprocess.run([self.dotnet, str(base.BIN / 'PrepararSdk.dll'), self.net8, str(base.BIN / 'Compat.dll'), str(out)]
                              + [str(orig / n) for n in ORDEM_RETARGET], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', creationflags=SEM_JANELA)
        linhas = [json.loads(l) for l in proc.stdout.splitlines() if l.startswith('{')]
        if proc.returncode or len(linhas) != len(ORDEM_RETARGET) or not all(l['ok'] for l in linhas):
            falha('Não foi possível preparar o SDK do FET para .NET 8: ' + (proc.stderr or proc.stdout)[-1500:])
        shutil.copy2(base.BIN / 'Compat.dll', out / 'Compat.dll')
        shutil.copy2(self.jogo / 'oo2core_9_win64.dll', out / 'oo2core_9_win64.dll')
        for x in FERRAMENTAS_CS:
            for ext in ('.dll', '.runtimeconfig.json'):
                shutil.copy2(base.BIN / (x + ext), out / (x + ext))
        man = dict(fet=str(self.fet), versao_fet=self.versao_fet, net8=self.net8, retarget=linhas,
                   arquivos={p.name: sha256_arquivo(p) for p in sorted(out.iterdir()) if p.is_file()})
        base.gravar_json(out / 'pronto.json', man)
        shutil.rmtree(orig)
        if dest.exists():
            shutil.rmtree(dest)
        os.replace(out, dest)
        shutil.rmtree(tmp, ignore_errors=True)
        return dest

    def run_sdk(self, jobs, pasta, tag, ferramenta='StadiumTool', allow_failures=False, extra=None):
        """Roda um lote de jobs no StadiumTool/ConvertTool. Os arquivos ficam em pasta/<tag>_<n>.*"""
        sdk = self.preparar_sdk()
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        n = 0
        while (pasta / f'{tag}_{n}.json').exists() or (pasta / f'{tag}_{n}.jobs.json').exists():
            n += 1
        jp, rp = pasta / f'{tag}_{n}.jobs.json', pasta / f'{tag}_{n}.json'
        batch = dict(extra or {})
        batch['jobs'] = jobs
        jp.write_text(json.dumps(batch, indent=1), encoding='utf8')
        proc = subprocess.run([self.dotnet, str(sdk / f'{ferramenta}.dll'), str(sdk / 'FC27SDK.dll'), str(self.jogo), str(jp), str(rp)],
                              capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=SEM_JANELA)
        if not rp.exists():
            falha(f'{ferramenta} falhou sem relatório:\n' + (proc.stdout + proc.stderr)[-3000:])
        report = json.loads(rp.read_text(encoding='utf8'))
        if report['failed'] and not allow_failures:
            bad = [r for r in report['rows'] if not r['ok']]
            falha(f"{report['failed']} job(s) do SDK falharam; primeiro: {bad[0]['input']}\n{bad[0]['error'][:3000]}")
        return report

    def hashes(self, names, pasta, tag='hashes'):
        rep = self.run_sdk([{'kind': 'hashes', 'input': '-', 'names': sorted(set(names))}], pasta, tag)
        return {h['name']: h for h in rep['rows'][0]['hashes']}

    # ---------------------------------------------------------- índice do cache
    def chave_cache(self):
        if not hasattr(self, '_chave_cache'):
            self._sha_cache = sha256_arquivo(self.fet / 'fc27.cache')
            self._chave_cache = self._sha_cache[:16]
        return self._chave_cache

    def pasta_jogo(self):
        return base.CACHE / 'jogo' / self.chave_cache()

    def indice_pronto(self):
        try:
            return self.fet is not None and (self.fet / 'fc27.cache').is_file() and (self.pasta_jogo() / 'indice.pickle').is_file()
        except OSError:
            return False

    def indice(self):
        if self._indice is None:
            self.exigir()
            p = self.pasta_jogo() / 'indice.pickle'
            if not p.is_file():
                base.log('Lendo o cache do FET (fc27.cache)...')
                c = cache_fet.read_cache(self.fet / 'fc27.cache')
                if c['sha256'] != self._sha_cache:
                    falha('o fc27.cache mudou durante a leitura')
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix('.tmp')
                with open(tmp, 'wb') as f:
                    pickle.dump(c, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp, p)
            else:
                with open(p, 'rb') as f:
                    c = pickle.load(f)
                if c['sha256'] != self._sha_cache_or_compute():
                    falha('índice guardado não corresponde ao fc27.cache')
            c['ebx_by_name'] = {e['name'].lower(): e for e in c['ebx']}
            c['ebx_by_part'] = {}
            for e in c['ebx']:
                c['ebx_by_part'].setdefault(e['partition'], e)
            c['res_by_name'] = {e['name'].lower(): e for e in c['res']}
            c['res_by_rid'] = {e['resrid']: e for e in c['res']}
            c['chunk_by_id'] = {e['id']: e for e in c['chunks']}
            c['bundle_by_name'] = {b['name']: b for b in c['bundles']}
            self._indice = c
        return self._indice

    def _sha_cache_or_compute(self):
        self.chave_cache()
        return self._sha_cache

    def cas(self):
        if self._cas is None:
            self._cas = Cas(self.jogo, self.jogo / 'oo2core_9_win64.dll')
        return self._cas

    # ---------------------------------------------------------- extrações nativas (cache/jogo/<chave>)
    def _arquivo_nativo(self, kind, name):
        return self.pasta_jogo() / 'nativo' / kind / (sha256(name.lower().encode())[:24] + '.bin')

    def native(self, kind, name):
        """(caminho, meta) do payload nativo descomprimido de um EBX/RES (conferido pelo tamanho e guardado)."""
        c = self.indice()
        meta = (c['ebx_by_name'] if kind == 'ebx' else c['res_by_name']).get(name.lower())
        if meta is None:
            falha(f'{kind.upper()} {name} não existe no jogo')
        p = self._arquivo_nativo(kind, meta['name'])
        if p.is_file() and p.stat().st_size == meta['original_size']:
            return p, meta
        raw, _, _ = self.cas().read_asset(meta)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.tmp')
        tmp.write_bytes(raw)
        os.replace(tmp, p)
        return p, meta

    def native_bytes(self, kind, name):
        p, meta = self.native(kind, name)
        return p.read_bytes(), meta

    def chunk_bytes(self, chunk_id):
        meta = self.indice()['chunk_by_id'][chunk_id]
        raw, _, _ = self.cas().read_asset(meta)
        return raw, meta

    def dumps(self, names, pasta_trabalho):
        """Dumps JSON do SDK de EBX nativos (guardados em cache/jogo/<chave>/dumps). {nome_lower: dump}."""
        c = self.indice()
        d = self.pasta_jogo() / 'dumps'
        d.mkdir(parents=True, exist_ok=True)
        todo = []
        for n in names:
            meta = c['ebx_by_name'][n.lower()]
            o = d / (sha256(meta['name'].lower().encode())[:24] + '.json')
            if not o.exists():
                p, _ = self.native('ebx', n)
                todo.append({'kind': 'dump', 'input': str(p), 'output': str(o)})
        for k in range(0, len(todo), 400):
            self.run_sdk(todo[k:k + 400], pasta_trabalho, 'dump')
        out = {}
        for n in names:
            meta = c['ebx_by_name'][n.lower()]
            dump = json.loads((d / (sha256(meta['name'].lower().encode())[:24] + '.json')).read_text(encoding='utf8'))
            if dump['name'] != meta['name'] or dump['partition'] != meta['partition']:
                falha('dump não corresponde ao cache: ' + meta['name'])
            out[n.lower()] = dump
        return out

    def fsinfo(self, pasta_trabalho):
        """Superbundles e head do sistema de arquivos do jogo (job fsinfo do StadiumTool), guardados."""
        p = self.pasta_jogo() / 'fsinfo.json'
        if p.is_file():
            return base.ler_json(p)
        rep = self.run_sdk([{'kind': 'fsinfo', 'input': '-'}], pasta_trabalho, 'fsinfo')
        info = rep['rows'][0]
        if str(info['head']) != str(self.indice()['header']['head']):
            falha('o head do sistema de arquivos do jogo difere do head do cache do FET: abra o FET para refazer o cache')
        base.gravar_json(p, info)
        return info

    # ---------------------------------------------------------- banco nativo e meta
    def meta_db(self):
        """fifa_ng_db-meta.xml do FC 27 (o esquema guardado no Super Tool, comum/esquemas/fc27-meta.xml.gz)."""
        p = base.CACHE / 'fc27-meta.xml'
        if not p.is_file():
            src = SUPERTOOL / 'comum' / 'esquemas' / 'fc27-meta.xml.gz'
            if not src.is_file():
                falha('Falta o esquema do banco do FC 27 (comum/esquemas/fc27-meta.xml.gz).')
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(gzip.decompress(src.read_bytes()))
        return p

    def db_nativo(self):
        """data/db/fifa_ng_db.db do jogo, como o SDK do FET o resolve (guardado)."""
        p = self.pasta_jogo() / 'db' / 'fifa_ng_db.db'
        if p.is_file():
            return p.read_bytes()
        from . import legado
        data = legado.extrair(self, 'data/db/fifa_ng_db.db')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return data


_AMB = None


def atual():
    global _AMB
    if _AMB is None:
        p = base.prefs()
        _AMB = Ambiente(p.get('fet_dir'), p.get('jogo_dir'))
    return _AMB
