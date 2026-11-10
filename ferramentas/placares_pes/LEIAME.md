# Conversor de Placares PES → FC

> Parte do **BRFP Super Tool**: abra pelo `BRFP Super Tool.bat` e clique em **Conversor de Placares PES → FC**.

Converte o placar da partida de um pacote de placares do **PES 2021** para o **EA SPORTS FC**. O desenho do placar do PES
vai para um placar do FC usado como **molde**, e os textos que o jogo escreve (nomes dos times, placar, relógio,
acréscimos), as faixas das cores dos times e os cartões vão para os lugares do PES. O resultado é gravado como um
**projeto do Editor de Placares**: abre lá, em **Editados**, para ajustar e ver a animação.

## Como usar

1. **Abra o placar do PES** (Arquivo › Abrir pasta…): a pasta do placar, com `common\menu\licence\game2dPes.bin`, ou a
   pasta de um pacote com vários placares (como o *J-League Scoreboard Package*, com J1, J2, J3…). Cada placar aparece na
   lista da esquerda. A primeira leitura de cada um leva alguns segundos (as texturas do PES são descomprimidas e ficam
   guardadas em `cache\`).
2. **Confira a prévia.** *No PES* é o placar como o PES desenha, com as caixas onde o jogo escreve os textos marcadas em
   amarelo. *No FC* é o fundo do PES no molde, com textos de exemplo, e a tela inteira de 1920×1080.
3. **Escolha o molde** (painel da direita) e a **posição na tela** (X, Y e escala; 1 = o tamanho do PES).
4. **Escolha onde gravar**: no lugar do próprio molde (a competição que usa aquele placar passa a mostrar o do PES), no
   placar *Generic* (`Generic/overlay_9002.big`) ou outro caminho `data/ui/…/….big`.
5. **Converter e gravar** (Ctrl+Enter). O arquivo vai para a **pasta de saída do Editor de Placares** (por padrão a
   `mods\legacy` do Live Editor). Abra o Editor de Placares: o placar está em *Editados*.

## O molde

O molde é um placar do FC (`…002.big`) com o fundo numa imagem grande e os textos como campos soltos:
`txtTeamNameHome`/`Away`, `txtTeamScoreHome`/`Away`, `mcClock` (com `txtTenMin`, `txtMin`, `txtColon`, `txtTenSec`,
`txtSec`), `mcExtraTime`, `mcTeamHomeColor`/`AwayColor` e os cartões. É o modelo dos placares do **pack do LTA**
(`Pack de TV Total y Switcher.fifamod`): o `overlay_35002` (Brasileirão) e mais uns 30 iguais. Os moldes vêm das fontes
do Editor de Placares: **adicione o pack do LTA como fonte no Editor de Placares** (Arquivo › Fontes) e clique em
*Atualizar a lista*.

Os moldes com fundo de 1920×1080 (35002, 31002, 32002, 37002…) aceitam o placar em qualquer lugar da tela; nos de fundo
menor (524×128, 1024×1024) o que ficar fora da imagem não aparece.

## O que a conversão faz

- **Fundo**: o desenho do PES (placas fixas, sem os textos) é desenhado na imagem de fundo do molde, na posição da tela
  escolhida. As outras imagens e decorações do molde (vidro, brilhos, faixas) ficam transparentes.
- **Nomes e placar**: os campos de texto do molde vão para as caixas do PES (`teamName_home`, `teamScore_home`…), com
  tamanho de letra pela altura da caixa e cor clara ou escura pelo fundo embaixo.
- **Relógio**: o clipe `mcClock` é escalado e movido para a caixa do relógio do PES.
- **Constantes do código**: o código do placar do LTA põe o `_x` dos gols e do relógio e o `_y` dos cartões dos expulsos
  por constantes (`SCORE_TEXT_TOTAL_OFFSET`, `PADDING_SCORE`, `FOUR_DIGIT_X`, `FIVE_DIGIT_X`,
  `Y_EJECTED_PLAYERS_DEFAULT`); a conversão muda essas constantes (pela aba Animação do Editor de Placares dá para ver e
  ajustar). Na prévia do Editor de Placares os gols podem aparecer deslocados: o simulador mede o texto de exemplo "00",
  e o jogo mede o placar de verdade.
- **Acréscimos**: a placa de acréscimos do PES vira a imagem da caixa `mcExtraTime` do molde, na posição do PES.
- **Cores dos times**: as faixas `mcTeamHomeColor`/`AwayColor` vão para as placas de cor dos times do PES.
- **Cartões**: os vermelhos logo abaixo do placar e os dos expulsos logo acima, a partir da ponta de dentro de cada nome.
- **Fonte dos números** (ligada por padrão): o PES desenha o relógio e o placar com números em imagem
  (`MatchPlate-texFont`: 0 a 9, ":" e "+"). O conversor contorna esses desenhos e monta uma fonte TrueType
  (`PES-<placar>-Numeros.ttf`, com um "-" desenhado no mesmo estilo), grava em `data/ui/fonts` da saída com família no
  `FIFA.xml` (como o *Importar fonte* do Editor de Placares) e liga na fonte dos gols do molde; o relógio passa a usar
  essa fonte, com cada dígito na caixa do dígito do PES. Os nomes continuam com a fonte do molde. O botão *Salvar o
  .ttf…* guarda a fonte onde você quiser.

## Limites

- Só o **placar da partida** (`game2d_score`) é convertido. O pacote do PES também tem escalação, substituição, gol,
  estatísticas e pênaltis (outros filmes do `game2dPes.bin`, `game2dPesEnter.bin`, `game2dPesPk.bin`).
- Os nomes são escritos pelo FC com a fonte do molde: a fonte dos nomes do PES é do próprio jogo e não vem no pacote.
  Para trocar, use a aba Fontes do Editor de Placares com um .ttf parecido.
- O logo/escudo da competição do PES (que o jogo põe por licença) não entra.
- O código das animações do PES não é rodado: o placar é montado no estado "aparecendo parado" de cada parte (rótulos
  `on`, fim do `show`), sem acréscimos.

## Como o PES 2021 guarda os placares (o que o conversor lê)

- `common\menu\licence\*.bin`: um pacote simples (contagem + entradas) com um `.apk` dentro, que é um **TXP2** da Konami
  em big-endian: texturas **TXDT** (ARGB 8 bits, ou DXT5 com as palavras de 16 bits invertidas, comprimidas com LZSS),
  recortes das texturas com nome
  (`game2dPes-score-plateMain`… em coordenadas dobradas), formas vetoriais **GE2D** e as animações **AFP** (o "Flash"
  da Konami, com sprites, objetos colocados com matriz e cor, quadros e rótulos). O AFP vem com uma tabela de inversão
  de bytes (BSI) que o deixa em little-endian.
- O placar é o filme `game2d_score` (480×129): `window › mainGroup` com as placas, `time_texts` (relógio),
  `losstime` (acréscimos), `teamColor`, `cardNum` e as caixas vazias com nome onde o jogo escreve.
- O formato AFP/TXP2 foi descrito pelo projeto **bemaniutils** (DragonMinded, domínio público); `motor\afp.py` faz só a
  parte que o PES usa.

## Arquivos

```
placares_pes\
  servidor.py        servidor local (127.0.0.1:8781) e rotas
  motor\afp.py       leitor do TXP2/AFP do PES: texturas, recortes, formas, filmes e a montagem da cena
  motor\pes.py       o placar do PES entendido: papel de cada peça (fundo, cores, acréscimos, caixas de texto)
  motor\fc.py        a conversão para o molde do FC (operações do Editor de Placares)
  motor\fonte_ttf.py fonte TrueType a partir das imagens dos números (contorno com OpenCV, tabelas escritas à mão)
  web\               interface
  cache\             texturas do PES já descomprimidas
```

A parte do FC usa os módulos do Editor de Placares (`ferramentas\placares\nucleo`), e o projeto gravado é o mesmo que o
editor grava.
