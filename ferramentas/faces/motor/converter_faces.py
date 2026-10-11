"""Conversor de faces (FBX do FIFA Editor Tool) FC 26 <-> FC 27, arquivo único ou em lote.

Uso:
  py -3.12 converter_faces.py ENTRADA [ENTRADA ...] [opções]

ENTRADA pode ser um .fbx ou uma pasta (todas as subpastas são varridas).
O jogo de origem de cada arquivo é detectado sozinho; o destino é o outro jogo.

Opções:
  --saida PASTA        pasta de saída (padrão: "<pasta>_FC27"/"<pasta>_FC26" ao lado da
                       pasta de entrada, ou "Convertidos_FC27"/"_FC26" ao lado do arquivo)
  --para fc27|fc26     força o jogo de destino (pula arquivos que já estão nele)
  --textura fc26|fc27  layout de textura que a UV da pele deve seguir (padrão fc26: as texturas
                       de face do FC 26 servem direto no FC 27; use fc27 se for usar texturas
                       já no layout do FC 27)
  --copiar-outros      copia para a saída, sem alterar, os arquivos que não são cabeças
                       (texturas, cabelo...), para a pasta ficar pronta para o Batch Import Faces
  --sobrescrever       substitui arquivos que já existem na saída
"""
import argparse
import collections
import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # o Python embutido (isolado) não põe a pasta do script
import conversor as C  # noqa: E402
from cena import Cena  # noqa: E402

OUTRO = {'fc26': 'fc27', 'fc27': 'fc26'}


def listar(entrada):
    if os.path.isfile(entrada):
        return [(entrada, os.path.basename(entrada))]
    out = []
    for raiz, _, arquivos in os.walk(entrada):
        for a in sorted(arquivos):
            caminho = os.path.join(raiz, a)
            out.append((caminho, os.path.relpath(caminho, entrada)))
    return out


def pasta_saida_padrao(entrada, destino):
    sufixo = '_' + destino.upper()
    entrada = os.path.abspath(entrada)
    if os.path.isdir(entrada):
        return entrada.rstrip('\\/') + sufixo
    return os.path.join(os.path.dirname(entrada), 'Convertidos' + sufixo)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Converte faces FBX entre FC 26 e FC 27 (FIFA Editor Tool).')
    ap.add_argument('entradas', nargs='+')
    ap.add_argument('--saida')
    ap.add_argument('--para', choices=['fc26', 'fc27'])
    ap.add_argument('--textura', choices=['fc26', 'fc27'], default='fc26')
    ap.add_argument('--copiar-outros', action='store_true')
    ap.add_argument('--sobrescrever', action='store_true')
    a = ap.parse_args(argv)

    t0 = time.time()
    relatorios = collections.defaultdict(list)
    contagem = collections.Counter()

    def log(pasta, linha, mostrar=True):
        relatorios[pasta].append(linha)
        if mostrar:
            print(linha)

    for entrada in a.entradas:
        entrada = entrada.strip('"')
        if not os.path.exists(entrada):
            print('ERRO: não encontrado: %s' % entrada)
            contagem['erros'] += 1
            continue
        arquivos = listar(entrada)
        # 1. quais FBX são cabeças e de que jogo
        jogos, nomes = {}, {}
        for caminho, rel in arquivos:
            if caminho.lower().endswith('.fbx'):
                try:
                    cena = Cena(caminho)
                    jogos[caminho] = C.detectar_jogo(cena)
                    if jogos[caminho] in OUTRO:
                        nomes[caminho] = {d: C.nome_saida(caminho, d, cena) for d in OUTRO}
                    del cena
                except Exception as e:  # FBX ASCII, corrompido...
                    jogos[caminho] = 'erro: %s' % e
        detectados = collections.Counter(j for j in jogos.values() if j in OUTRO)
        if a.para:
            destino_pasta = a.para
        elif detectados:
            destino_pasta = OUTRO[detectados.most_common(1)[0][0]]
        else:
            destino_pasta = 'fc27'
        raiz_saida = os.path.abspath(a.saida or pasta_saida_padrao(entrada, destino_pasta))
        if not a.saida and not a.para and len(detectados) > 1:
            # pasta com faces dos dois jogos: cada uma vai para o outro jogo
            raiz_saida = pasta_saida_padrao(entrada, 'fc27')[:-len('_FC27')] + '_convertido'
        if os.path.isdir(entrada) and os.path.commonpath([raiz_saida, os.path.abspath(entrada)]) == os.path.abspath(entrada):
            print('ERRO: a pasta de saída não pode ficar dentro da pasta de entrada (%s)' % raiz_saida)
            contagem['erros'] += 1
            continue
        if not detectados:
            log(raiz_saida, 'Nenhuma cabeça (head_mat) encontrada em %s' % entrada)

        # 2. converte as cabeças; o resto é ignorado ou copiado
        for caminho, rel in arquivos:
            jogo = jogos.get(caminho)
            nome = os.path.basename(caminho).lower()
            if jogo is not None and jogo.startswith('erro'):
                log(raiz_saida, 'ERRO      %s: %s' % (rel, jogo[6:]))
                contagem['erros'] += 1
                continue
            destino = a.para or (OUTRO[jogo] if jogo in OUTRO else destino_pasta)
            if jogo not in OUTRO or jogo == destino:
                if jogo in OUTRO:
                    motivo = 'já está no formato %s' % jogo.upper()
                elif 'mouthbag' in nome:
                    motivo = 'mouthbag: no FC 27 os dentes ficam dentro da cabeça e o FET não aceita mouthbag'
                else:
                    motivo = 'não é uma cabeça'
                copiar = a.copiar_outros and not ('mouthbag' in nome and destino == 'fc27')
                dst = os.path.join(raiz_saida, rel)
                if copiar and (a.sobrescrever or not os.path.exists(dst)):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(caminho, dst)
                    log(raiz_saida, 'COPIADO   %s (%s)' % (rel, motivo), mostrar=False)
                    contagem['copiados'] += 1
                elif nome.endswith('.fbx'):
                    log(raiz_saida, 'IGNORADO  %s (%s)' % (rel, motivo))
                    contagem['ignorados'] += 1
                continue
            dst = os.path.join(raiz_saida, os.path.dirname(rel), nomes[caminho][destino])
            if os.path.exists(dst) and not a.sobrescrever:
                log(raiz_saida, 'IGNORADO  %s (já existe na saída; use --sobrescrever)' % rel)
                contagem['ignorados'] += 1
                continue
            try:
                r = C.converter(caminho, dst, destino=destino, layout_textura=a.textura)
            except Exception as e:
                msg = str(e) if isinstance(e, C.ErroConversao) else traceback.format_exc(limit=4)
                log(raiz_saida, 'ERRO      %s: %s' % (rel, msg))
                contagem['erros'] += 1
                continue
            contagem['convertidos'] += 1
            log(raiz_saida, 'OK        %s -> %s  (%s -> %s)' % (
                rel, os.path.relpath(dst, raiz_saida), r['origem'].upper(), r['destino'].upper()))
            for k, v in r['metodos'].items():
                log(raiz_saida, '              %s: %s' % (k, v), mostrar=False)
            for av in r['avisos']:
                log(raiz_saida, '              AVISO: %s' % av)
                contagem['avisos'] += 1

    resumo = ('Convertidos: %d   Ignorados: %d   Copiados: %d   Avisos: %d   Erros: %d'
              % tuple(contagem[k] for k in ('convertidos', 'ignorados', 'copiados', 'avisos', 'erros')))
    print('\n' + resumo + '   (%.1f s)' % (time.time() - t0))
    for pasta, linhas in relatorios.items():
        if os.path.isdir(pasta):
            with open(os.path.join(pasta, 'relatorio_conversao_faces.txt'), 'w', encoding='utf-8') as f:
                f.write('Conversor de faces FC 26 <-> FC 27 - %s\n\n' % time.strftime('%d/%m/%Y %H:%M'))
                f.write('\n'.join(linhas) + '\n\n' + resumo + '\n')
            print('Saída e relatório em: %s' % pasta)
    return 1 if contagem['erros'] else 0


if __name__ == '__main__':
    sys.exit(main())
