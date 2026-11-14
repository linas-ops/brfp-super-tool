"""Linha de comando do motor (o servidor da ferramenta roda assim, com o registro ao vivo):

  python -m motor ambiente                      estado do ambiente (JSON)
  python -m motor preparar                      prepara o SDK e o índice do cache
  python -m motor estadios                      catálogo dos estádios do jogo (JSON)
  python -m motor duplicar <config.json>        duplica estádios (ver motor/duplicar.py)
  python -m motor converter <config.json>       converte um estádio do FIFA 16 (ver motor/fifa16/converter.py) ou, com
                                                "pasta_pes" na configuração, do PES 2021 (ver motor/pes21/converter.py)
  python -m motor analisar16 <pasta FIFA 16>    lê um estádio do FIFA 16 e sugere a receita da conversão
  python -m motor analisarpes <pasta PES 2021>  lê um estádio do PES 2021 e sugere a receita da conversão
  python -m motor luz16 <pasta FIFA 16>         estádios do FC 27 pela cobertura da torcida pela luz pré-calculada
"""
import json
import sys
import time
import traceback
from pathlib import Path

from . import base


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    t0 = time.time()
    try:
        from . import ambiente
        amb = ambiente.atual()
        if cmd == 'ambiente':
            print(json.dumps(amb.estado(), ensure_ascii=False))
            return 0
        if cmd == 'preparar':
            base.etapa('sdk', 'Preparando o SDK do FET para .NET 8')
            amb.preparar_sdk()
            base.etapa('indice', 'Lendo o cache do FET (índice do jogo)')
            amb.indice()
            base.etapa('catalogo', 'Catálogo dos estádios')
            from . import catalogo
            cat = catalogo.catalogo(amb)
            base.resultado(dict(ok=True, estadios=len(cat['estadios']), segundos=round(time.time() - t0)))
            return 0
        if cmd == 'estadios':
            from . import catalogo
            print(json.dumps(catalogo.catalogo(amb), ensure_ascii=False))
            return 0
        if cmd == 'duplicar':
            from . import duplicar, verificar
            cfg = base.ler_json(args[0])
            d = duplicar.Duplicacao(amb, cfg['copias'], cfg['saida'], cfg.get('projeto_base'), cfg.get('trabalho'))
            rep = d.run()
            ver = verificar.verificar_projeto(amb, rep['projeto']['saida'], d.work, cfg.get('projeto_base'),
                                              [cp.verificacao for cp in d.copias]) if cfg.get('verificar', True) else None
            res = dict(ok=not ver or ver['ok'], tipo='duplicar', saida=rep['projeto']['saida'], sha256=rep['projeto']['sha256'],
                       trabalho=str(d.work), nome=', '.join(f"{c['novo_id']} {c['nome']}" for c in cfg['copias']), copias=rep['copias'],
                       banco=rep['banco'], verificacao=ver, segundos=round(time.time() - t0))
            base.gravar_json(d.work / 'resultado.json', res)
            if res['ok']:
                base.log(f'Pasta de trabalho limpa: {base.limpar_trabalho(d.work) / 2**20:.0f} MB liberados (ficam os relatórios)')
            base.resultado(res)
            return 0
        if cmd == 'converter':
            cfg = base.ler_json(args[0])
            if cfg.get('pasta_pes'):
                from .pes21 import converter
            else:
                from .fifa16 import converter
            res = converter.converter(amb, cfg)
            res['segundos'] = round(time.time() - t0)
            res['tipo'] = 'converter'
            base.gravar_json(Path(res['trabalho']) / 'resultado.json', res)
            if res['ok']:
                base.log(f"Pasta de trabalho limpa: {base.limpar_trabalho(res['trabalho']) / 2**20:.0f} MB liberados (ficam os relatórios)")
            base.resultado(res)
            return 0
        if cmd == 'analisar16':
            from .fifa16 import analise
            an = analise.analisar(args[0], miniaturas=args[1] if len(args) > 1 else None)
            from .fifa16 import converter
            pronta = converter.receita_pronta(an['fifa16_id'])
            an['receita_pronta'] = pronta
            print(json.dumps(an, ensure_ascii=False))
            return 0
        if cmd == 'analisarpes':
            from .pes21 import analise
            try:
                an = analise.analisar(args[0], miniaturas=args[1] if len(args) > 1 else None)
            except (OSError, ValueError) as ex:
                base.falha(str(ex))
            an['receita_pronta'] = None
            print(json.dumps(an, ensure_ascii=False))
            return 0
        if cmd == 'luz16':
            from .fifa16 import luz
            print(json.dumps(luz.avaliar(amb, args[0]), ensure_ascii=False))
            return 0
        print('comando desconhecido: ' + cmd)
        return 2
    except base.Falha as ex:
        base.erro(str(ex))
        return 1
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        base.erro(f'{type(ex).__name__}: {ex}')
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
