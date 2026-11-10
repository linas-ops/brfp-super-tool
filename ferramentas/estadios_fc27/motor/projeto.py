"""Projetos do FET (FETP v4): leitura, plano de mudanças e gravação pelo codec da skill fet-projects (motor/fet).

O plano nunca apaga nem reescreve registros que não escolheu. Ao partir de um projeto existente:
  - um asset novo (nome/partição/RID/chunk novos) não pode existir no projeto;
  - um asset nativo que a duplicata coloca nos bundles novos e que o projeto já tem (outra duplicata do mesmo
    estádio, ou um asset que o usuário editou) fica com o payload do projeto e ganha os bundles novos;
  - registros que a duplicata precisa editar (mapa de estádios, loaders, banco) partem da versão do projeto.
"""
from __future__ import annotations
import json
import subprocess
import sys
import uuid
from collections import OrderedDict
from pathlib import Path

from . import base
from .base import falha, sha256

FET_DIR = base.MOTOR / 'fet'
sys.path.insert(0, str(FET_DIR))
import fetp_v4  # noqa: E402
import fet_project  # noqa: E402

KINDS = {'ebx': 'ebx', 'res': 'resources', 'chunk': 'chunks'}
DB_LEGACY = 'data/db/fifa_ng_db.db'
DB_LEGACY_HASH = 17350874655369348742  # FNV-1 64 de data/db/fifa_ng_db.db, como o FET grava
MODELO_VAZIO = base.MOTOR / 'modelos' / 'projeto_vazio_fet_17.1.5.0.fifaproject'


def chave(kind, value):
    return str(uuid.UUID(str(value))) if kind == 'chunk' else value.lower()


class Projeto:
    def __init__(self, path, cas=None):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.sha256 = sha256(self.data)
        self.parsed = fetp_v4.read_project_bytes(self.data)
        self.cas = cas
        self.by = {}
        for kind, section in KINDS.items():
            for e in self.parsed[section]:
                self.by[(kind, chave(kind, e['id'] if kind == 'chunk' else e['name']))] = e

    @property
    def header(self):
        return self.parsed['header']

    def vazio(self):
        return not any(self.parsed[k] for k in ('chunks', 'resources', 'ebx', 'addedbundles', 'shadersources'))

    def record(self, kind, key):
        return self.by.get((kind, chave(kind, key)))

    def record_sha(self, rec):
        return fet_project.record_sha(self.parsed, rec)

    def encoded(self, rec):
        o = rec['data_offset']
        return self.data[o:o + rec['data_size']]

    def raw(self, kind, key):
        rec = self.record(kind, key)
        if rec is None:
            raise KeyError(f'{kind}:{key} não está no projeto')
        return self.cas.decompress(self.encoded(rec))

    def bundles(self):
        return {b['name']: b for b in self.parsed['addedbundles']}

    def chunk_db(self):
        for e in self.parsed['chunks']:
            if e.get('legacyhash') == DB_LEGACY_HASH:
                return e
        return None


class Plano:
    """Mudanças sobre um projeto-fonte (o modelo vazio ou um projeto existente), na ordem em que são feitas."""

    def __init__(self, fonte: Projeto, pasta):
        self.fonte = fonte
        self.pasta = Path(pasta)
        (self.pasta / 'payloads').mkdir(parents=True, exist_ok=True)
        self.changes = OrderedDict()
        self.added_bundles = []

    def put(self, data):
        h = sha256(data)
        p = self.pasta / 'payloads' / (h + '.bin')
        if not p.exists():
            p.write_bytes(data)
        return dict(path=str(p), sha256=h)

    def payload(self, data, encoding):
        return dict(self.put(data), encoding=encoding)

    def _k(self, kind, key):
        return (kind, chave(kind, key))

    def tem(self, kind, key):
        return self._k(kind, key) in self.changes or self.fonte.record(kind, key) is not None

    def adicionar(self, kind, key, record, data, encoding):
        """Registro novo: não pode existir no projeto-fonte nem no plano."""
        k = self._k(kind, key)
        if k in self.changes or self.fonte.record(kind, key) is not None:
            falha(f'{kind.upper()} {key} já existe no projeto (o mesmo estádio novo já foi criado nele?)')
        self.changes[k] = {'kind': kind, 'action': 'add', 'key': key, 'record': record, 'payload': self.payload(data, encoding)}

    def atribuir_nativo(self, kind, key, record, data, encoding):
        """Asset nativo colocado nos bundles novos: junta os bundles se o plano ou o projeto já o tiverem."""
        k = self._k(kind, key)
        novos = list(record.get('addedbundles', []))
        if k in self.changes:
            ch = self.changes[k]
            rec = ch.setdefault('record', {})
            atuais = rec.get('addedbundles')
            if atuais is None:
                old = self.fonte.record(kind, key)
                atuais = list(old.get('addedbundles', [])) if old else []
            rec['addedbundles'] = atuais + [b for b in novos if b not in atuais]
            return
        old = self.fonte.record(kind, key)
        if old is None:
            self.changes[k] = {'kind': kind, 'action': 'add', 'key': key, 'record': record, 'payload': self.payload(data, encoding)}
            return
        atuais = list(old.get('addedbundles', []))
        self.changes[k] = {'kind': kind, 'action': 'replace', 'key': key, 'expected_record_sha256': self.fonte.record_sha(old),
                           'record': {'addedbundles': atuais + [b for b in novos if b not in atuais]}}

    def editar(self, kind, key, data, encoding='raw', record=None, original=None):
        """Nova versão de um registro: troca o do projeto-fonte ou entra como asset nativo modificado (original = record do add)."""
        k = self._k(kind, key)
        old = self.fonte.record(kind, key)
        if k in self.changes and self.changes[k]['action'] != 'replace' and old is None:
            ch = self.changes[k]
            ch['payload'] = self.payload(data, encoding)
            if record:
                ch['record'].update(record)
            return
        if old is None:
            if original is None:
                falha(f'{kind.upper()} {key} não está no projeto para ser editado')
            rec = dict(original)
            if record:
                rec.update(record)
            self.changes[k] = {'kind': kind, 'action': 'add', 'key': key, 'record': rec, 'payload': self.payload(data, encoding)}
            return
        ch = self.changes.get(k) or {'kind': kind, 'action': 'replace', 'key': key, 'expected_record_sha256': self.fonte.record_sha(old)}
        ch['payload'] = self.payload(data, encoding)
        if record:
            ch.setdefault('record', {}).update(record)
        self.changes[k] = ch

    def bundles_novos(self, bundles):
        existentes = set(self.fonte.bundles()) | {b['name'] for b in self.added_bundles}
        for b in bundles:
            if b['name'] in existentes:
                falha(f'o projeto já tem o bundle {b["name"]} (o mesmo estádio novo já foi criado nele?)')
            self.added_bundles.append(b)
            existentes.add(b['name'])

    def mover_para_inicio(self, kind, key):
        k = self._k(kind, key)
        self.changes.move_to_end(k, last=False)

    def gravar(self, saida, perfil=None):
        """Aplica o plano com o fet_project.py (modo create no modelo vazio, edit num projeto) e confere o resultado."""
        saida = Path(saida).resolve()
        if saida.exists():
            falha('o arquivo de saída já existe: ' + str(saida))
        plan = {'schema': 1, 'source_sha256': self.fonte.sha256, 'changes': list(self.changes.values())}
        if self.added_bundles:
            plan['added_bundles'] = self.added_bundles
        # o projeto-fonte e o plano ficam juntos na pasta de trabalho (o fet_project resolve caminhos relativos ao plano)
        pp = self.pasta / 'fet_plan.json'
        pp.write_text(json.dumps(plan, indent=0), encoding='utf8')
        rp = self.pasta / 'apply_result.json'
        if rp.exists():
            rp.unlink()
        modo = 'create' if self.fonte.vazio() else 'edit'
        # como script, o Python embutido do Super Tool (._pth) não acharia o fetp_v4 ao lado: a pasta entra no sys.path
        lancador = ("import sys, runpy; d = sys.argv.pop(1); sys.path.insert(0, d); "
                    "runpy.run_path(d + '/fet_project.py', run_name='__main__')")
        cmd = [sys.executable, '-E', '-s', '-c', lancador, str(FET_DIR), 'apply', str(self.fonte.path), str(saida),
               '--mode', modo, '--plan', str(pp), '--report', str(rp)]
        if perfil:
            cmd += ['--identity-profile', str(perfil['arquivo']), '--cache', str(perfil['cache']), '--sdk', str(perfil['sdk'])]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if proc.returncode or not saida.exists():
            falha('a gravação do projeto falhou: ' + (proc.stderr or proc.stdout)[-3000:])
        res = json.loads(rp.read_text(encoding='utf8'))
        v = res['validation']
        if not v['container_valid'] or not v['checks_passed']:
            falha('o projeto gravado não passou na auditoria: ' + json.dumps(v['errors'][:5], ensure_ascii=False))
        return dict(saida=res['output'], sha256=res['sha256'], modo=modo, container_valido=v['container_valid'],
                    auditoria=v['checks_passed'], contagens=v['counts'], identidades_ebx_conferidas=v['embedded_ebx_identities_checked'],
                    perfil_nomes=len(v['profile_name_checks']), avisos=v['warnings'])


def perfil_identidade(amb):
    """Perfil de identidade da skill quando o cache e o SDK do usuário são os mesmos do perfil (FC 27 / FET 17.1.5.0)."""
    p = FET_DIR / 'perfil_fc27-17.1.5.0.json'
    try:
        prof = json.loads(p.read_text(encoding='utf8'))
    except (OSError, ValueError):
        return None
    sdk = amb.fet / 'SDKs' / 'FC27SDK.dll'
    if amb._sha_cache_or_compute() != prof['cache_sha256'] or base.sha256_arquivo(sdk) != prof['sdk_sha256']:
        return None
    return dict(arquivo=p, cache=amb.fet / 'fc27.cache', sdk=sdk)


def modelo_vazio(amb):
    """O projeto vazio do FET usado para criar do zero; o cabeçalho tem de ser o do jogo e do FET atuais."""
    p = Projeto(MODELO_VAZIO)
    h = amb.indice()['header']
    if p.header['patch'] != h['head'] or p.header['exe'] != h['exe'] or not p.vazio():
        falha('O projeto vazio que vem com a ferramenta é de outra versão do jogo/FET. No FET, crie um projeto vazio '
              '(File > New Project, depois Save) e use "Adicionar a um projeto existente" com ele.')
    return p
