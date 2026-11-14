"""Conversão de um estádio do PES 2021 para o FC 27, sempre sobre a base El Grandioso (estádio 181).

O caminho é o mesmo da conversão do FIFA 16 (motor/fifa16/converter.py, o do Morumbi v3 que funcionou em partida): uma
duplicata completa do El Grandioso no ID novo, e sobre ela os materiais do estádio repartidos entre os seis meshes
hospedeiros, as texturas novas, o telão, o gramado recortado, a torcida, os glares e os personagens laterais. Só muda de
onde vêm os dados (motor/pes21/preparar.py grava a mesma pasta de preparação):
- a torcida vem das áreas do PES (audiarea.bin), já como lugares na altura dos degraus, com as cores das cadeiras do
  au_seat.png e o setor de visitantes marcado no PES; a organizada da casa, que o PES não marca, fica atrás do gol da casa;
- as lâmpadas dos glares vêm dos brilhos do PES (effect_st<NNN>_df de dia, _nf de noite);
- o PES não tem marcadores de personagens laterais: todos partem das posições do El Grandioso e são conferidos contra a
  geometria do estádio novo.
Os estádios do PES 2021 são mais pesados que os do FIFA 16: se os materiais não couberem nos meshes do El Grandioso com
peças grandes, a preparação é refeita com peças menores (mais subsets, a mesma geometria).
"""
from __future__ import annotations
import collections
import json
from pathlib import Path

import numpy as np

from .. import base, projeto as P
from ..base import falha
from ..fifa16 import converter as C16
from . import analise, preparar

LUGAR = np.dtype([('pos', '<f4', 3), ('orient', '<f4'), ('cor', 'u1', 3), ('visitante', 'u1'), ('area', '<u4')])
COR_SEM_MAPA = 0x6E7078          # cadeiras quando o estádio não traz o au_seat.png
PECAS_MENORES = (60000, 30000, 16000, 9000)


class ConversaoPes(C16.Conversao):
    JOGO = 'PES 2021'
    ONDE_LAMPADAS = 'nos brilhos do PES 2021'

    def __init__(self, amb, cfg, base_proj, dup, prep, work):
        super().__init__(amb, cfg, base_proj, dup, prep, work)
        self.report = collections.OrderedDict(base_id=C16.BASE_ID, novo_id=self.N, origem='pes21', fonte_id=self.rc['fonte_id'], prep=str(self.prep))

    def stage_crowd(self):
        arq = self.prep / 'torcida.bin'
        lug = np.frombuffer(arq.read_bytes(), LUGAR) if arq.is_file() else np.zeros(0, LUGAR)
        if not len(lug):
            self.report['torcida'] = 'sem áreas de torcida no PES (audiarea.bin): a torcida do El Grandioso fica'
            return
        info = json.loads((self.prep / 'torcida.json').read_text(encoding='utf8'))
        Pp = lug['pos'].astype(np.float64)
        orient = lug['orient'].astype(np.float64)
        away = lug['visitante'] > 0
        cfg = self.rc.get('torcida') or {}
        # organizada da casa: o PES não a marca. Fica no anel inferior atrás do gol do lado da casa.
        sx = -1.0 if cfg.get('lado_casa', '-x') == '+x' else 1.0
        organised = ~away & (Pp[:, 0] * sx < -55.0) & (np.abs(Pp[:, 2]) < 30.0) & (Pp[:, 1] < float(cfg.get('tier2_acima_de', 14.0)))
        if info.get('cores'):
            rgb = lug['cor'].astype(np.uint32)
        else:
            rgb = np.tile(np.array([(COR_SEM_MAPA >> 16) & 255, (COR_SEM_MAPA >> 8) & 255, COR_SEM_MAPA & 255], np.uint32), (len(lug), 1))
        self.torcida_fc27(Pp, orient, away, organised, np.ones(len(lug)), rgb,
                          dict(areas_pes=int(info['areas'])), dict(sem_degrau=int(info.get('sem_degrau', 0)), cores_das_cadeiras=bool(info.get('cores'))))

    def anel_da_pista(self):
        """Raio interno, por ângulo, do piso em volta do campo (as peças "piso" da receita). No PES o pé da arquibancada tem
        trechos retos compridos com poucos vértices, então o raio sai de pontos espalhados pelos triângulos (até 1,5 m de
        altura), e não só dos vértices: o gramado do FC 27 para exatamente no pé da arquibancada, em toda a volta."""
        from ..fifa16.personagens import _pontos
        pista = {int(x) for x in self.rc.get('pista') or []}
        nomes = [s['name'] for s in self.subsets['subsets'] if set(s['prims']) & pista]
        if not nomes:
            return None, []
        blob = (self.prep / 'geometry.bin').read_bytes()
        bins = 720
        rin = np.full(bins, np.inf)
        for s in self.subsets['subsets']:
            if s['name'] not in nomes:
                continue
            n, t, o = s['vertices'], s['triangles'], s['offset']
            pos = np.frombuffer(blob, '<f4', n * 3, o).reshape(n, 3).astype(np.float64)
            tri = pos[np.frombuffer(blob, '<u4', t * 3, o + n * 56).reshape(t, 3)]
            tri = tri[(tri[..., 1].min(1) < 1.5) & (tri[..., 1].max(1) > -0.5)]
            for p in _pontos(tri, passo=0.2):
                p = p[(p[:, 1] < 1.5) & (p[:, 1] > -0.5)]
                b = ((np.arctan2(p[:, 2], p[:, 0]) + np.pi) / (2 * np.pi) * bins).astype(int) % bins
                np.minimum.at(rin, b, np.hypot(p[:, 0], p[:, 2]))
        good = np.isfinite(rin)
        if not good.any():
            return None, []
        xs = np.nonzero(good)[0]
        rin = np.interp(np.arange(bins), xs, rin[good], period=bins)
        rin = np.minimum.reduce([np.roll(rin, k) for k in (-1, 0, 1)])
        return rin, nomes

    def lampadas_das_variantes(self):
        arq = self.prep / 'lampadas.json'
        d = json.loads(arq.read_text(encoding='utf8')) if arq.is_file() else {}
        dia = np.array(d.get('dia') or [], np.float64).reshape(-1, 3)
        noite = np.array(d.get('noite') or [], np.float64).reshape(-1, 3)
        if not len(dia):
            dia = noite
        if not len(noite):
            noite = dia
        return {v: (dia if v.startswith('1_') else noite) for v in self.VARIANTES_GLARES}


def receita_final(pasta, receita=None):
    """A receita da conversão: a sugerida pela análise do PES com os ajustes da interface."""
    an = analise.analisar(pasta)
    sid = an['fonte_id']
    r = dict(an['receita'])
    if receita:
        r.update({k: v for k, v in receita.items() if v is not None})
    r.update(origem='pes21', fonte_id=sid, fifa16_id=sid, prefixo=f'pes21_{sid}', pasta_nome=f'pes21_{sid}', identidade=f'pes21_{sid}',
             identidade_id=-1)
    r['giro'] = int(r.get('giro') or 0)
    return r, an


def cabe_nos_hospedeiros(prep, rc):
    """True se os materiais preparados cabem nos seis meshes do El Grandioso (a mesma distribuição da conversão)."""
    subs = json.loads((Path(prep) / 'subsets.json').read_text(encoding='utf8'))['subsets']
    by = collections.OrderedDict()
    for s in subs:
        if s['role'] in C16.STRIDE:
            by.setdefault(s.get('material', s['name']), []).append(s)
    sim = object.__new__(ConversaoPes)
    sim.rc = rc
    sim.mats = [dict(name=k, role=v[0]['role'], texture=v[0]['texture'], pieces=v,
                     bytes=sum(x['vertices'] * C16.STRIDE[x['role']] + x['triangles'] * 6 for x in v)) for k, v in by.items()]
    total = sum(m['bytes'] for m in sim.mats)
    try:
        sim.distribuir(dividir=False)
        return True, total
    except base.Falha:
        pass
    if not rc.get('ajuste_automatico', True):
        return False, total
    try:
        sim.distribuir(dividir=True)
        return True, total
    except base.Falha:
        return False, total


def converter(amb, cfg):
    """cfg: pasta_pes, novo_id, nome, saida, projeto_base (opcional), receita (ajustes), nome_base (opcional)."""
    from .. import duplicar, verificar
    saida = Path(cfg['saida']).resolve()
    if saida.exists():
        falha('o arquivo de saída já existe: ' + str(saida))
    work = Path(cfg.get('trabalho') or base.pasta_trabalho('converter'))
    base.etapa('analise', 'Lendo o estádio do PES 2021')
    try:
        rc, an = receita_final(cfg['pasta_pes'], cfg.get('receita'))
    except (OSError, ValueError) as ex:
        falha(str(ex))
    sid = an['fonte_id']
    cfg = dict(cfg, receita=rc)
    base.progresso(100, f"estádio {sid} do PES 2021: {an['resumo']['pecas']} peças" + (', girado meia volta (bancos em +Z)' if rc['giro'] == 180 else ''))
    base.etapa('preparar_pes', 'Preparando geometria, texturas e torcida do PES 2021')
    pedido = int(rc.get('max_vertices') or 60000)
    tentativas = [pedido] + [m for m in PECAS_MENORES if m < pedido]
    prep = resumo = None
    for k, mv in enumerate(tentativas):
        prep = work / ('prep' if k == 0 else f'prep_{mv}')
        try:
            resumo = preparar.preparar(cfg['pasta_pes'], prep, dict(rc, max_vertices=mv))
        except (OSError, ValueError) as ex:
            falha(str(ex))
        ok, total = cabe_nos_hospedeiros(prep, rc)
        cap = C16.HOST_BUDGET * len(C16.HOSTS)
        ajuste = rc.get('ajuste_automatico', True)
        if not ok and (total > cap or not ajuste or k + 1 == len(tentativas)):
            # para já, antes de duplicar o El Grandioso (minutos de trabalho que acabariam no mesmo erro)
            if total > cap:
                falha(f'o estádio tem {total / 2**20:.1f} MB de geometria e os seis meshes do El Grandioso comportam {cap / 2**20:.1f} MB: '
                      'descarte peças que não aparecem (a lista de peças mostra quanto as que ficam ocupam) ou marque "1 lado" nas '
                      'que só são vistas de frente')
            falha(f'os materiais do estádio ({total / 2**20:.1f} MB) não couberam nos seis meshes do El Grandioso ({cap / 2**20:.1f} MB, '
                  f'até {C16.HOST_BUDGET / 2**20:.1f} MB cada): ' + ('descarte algumas peças que não aparecem' if ajuste
                                                                     else 'ligue o ajuste automático de tamanho'))
        if ok:
            if k:
                rc['max_vertices'] = mv
                base.aviso(f'ajuste automático: as peças passaram a ter até {mv} vértices para os materiais caberem nos meshes do El Grandioso '
                           f'({total / 2**20:.1f} de {C16.HOST_BUDGET * len(C16.HOSTS) / 2**20:.1f} MB)')
            break
        base.limpar_trabalho(prep)
    for nota in resumo['notas']:
        base.aviso(nota)
    tor = resumo.get('torcida')
    base.progresso(100, f"{resumo['subsets']} subsets, {resumo['textures']} texturas" + (f", {tor['lugares']} lugares da torcida" if tor else ''))
    base_proj = work / f'base_{C16.BASE_ID}_{cfg["novo_id"]}.fifaproject'
    dup = duplicar.Duplicacao(amb, [dict(origem=C16.BASE_ID, novo_id=int(cfg['novo_id']), nome=cfg.get('nome_base') or cfg['nome'])],
                              base_proj, cfg.get('projeto_base'), work / 'duplicata')
    dup.run()
    proj = P.Projeto(base_proj, amb.cas())
    conv = ConversaoPes(amb, cfg, proj, dup, prep, work / 'conversao')
    rep = conv.build()
    base.etapa('gravar', 'Gravando o projeto do FET')
    rep['projeto'] = conv.plano.gravar(saida, P.perfil_identidade(amb))
    base.progresso(100, 'projeto gravado')
    ver = None
    if cfg.get('verificar', True):
        ver = verificar.verificar_projeto(amb, saida, work, cfg.get('projeto_base'), [cp.verificacao for cp in dup.copias])
    res = dict(ok=not ver or ver['ok'], saida=str(saida), sha256=rep['projeto']['sha256'], trabalho=str(work), origem='pes21', fonte_id=sid,
               novo_id=int(cfg['novo_id']), nome=cfg['nome'], receita=rc, preparo=resumo, conversao=rep, verificacao=ver)
    base.gravar_json(work / 'resultado.json', res)
    return res
