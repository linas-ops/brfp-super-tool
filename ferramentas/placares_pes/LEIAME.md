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

Há dois tipos de molde, e a lista mostra os dois.

### Generic (do jogo)

O placar padrão do próprio FC (`data/ui/game/overlays/Generic/overlay_9002.big`), o primeiro da lista: não depende de
nenhum mod. É bem diferente do modelo do LTA: o desenho são caixas de cor sem imagem, os textos são componentes
MultiText que o código cria e formata, e o código põe quase tudo no lugar durante a entrada (constantes como
`ANIMATE_IN_TEAM_NAME_HOME_Y`, `INIT_SCORE_NORMAL_X_POS`, `TIMER_X_POS`, `ANIM_IN_CARD_Y_POS`). A conversão:

- desenha o placar do PES na imagem do logo do FC (`mcLogoHolder.mcLogoFc`), põe esse clipe atrás dos textos (muda a
  profundidade dele) e estica a máscara do logo para cobrir o placar inteiro — ele entra subindo, como o logo;
- esconde as caixas, o título, os escudos, o logo da liga e os ícones do Generic (os que o código volta a mostrar vão
  também para fora da tela ou da máscara deles);
- desliga, só no logo do FC e nos textos, a pintura com cor chapada que o código faz ao abrir
  (`ColorUtil.ChangeColorFlat` com as cores da competição): sem isso a arte vira uma silhueta preta ou branca e os
  textos ficam com a cor do tema. O nome do método é trocado naquelas chamadas por um que não existe, e elas não fazem
  nada; as outras (faixas das cores dos times, por exemplo) continuam;
- leva nomes, gols e os dígitos do relógio para as caixas do PES: a largura de cada MultiText é 240 × a escala dele e
  o `_y` é o meio da linha; altura, tamanho da letra, fonte e cor vão pelas constantes do código; os nomes ficam
  centralizados (`H_ALIGN_CENTER`);
- põe as faixas das cores dos times nas placas de cor do PES, os cartões numa faixa logo acima (casa) e logo abaixo
  (fora) do placar, e o placar agregado à direita, da mesma altura.

Limites do Generic: a placa dos acréscimos do PES não aparece (só o "+3", no lugar dela, ou logo abaixo do relógio
quando no PES a placa cobre o relógio); com os nomes longos (15 letras) o código alarga o placar e desalinha, então use
os nomes abreviados; no modo Ultimate Team Pro o código troca o logo do FC por outro e o desenho some.

### Modelo do LTA

O molde é um placar do FC (`…002.big`) com o fundo numa imagem grande e os textos como campos soltos:
`txtTeamNameHome`/`Away`, `txtTeamScoreHome`/`Away`, `mcClock` (com `txtTenMin`, `txtMin`, `txtColon`, `txtTenSec`,
`txtSec`), `mcExtraTime`, `mcTeamHomeColor`/`AwayColor` e os cartões. É o modelo dos placares do **pack do LTA**
(`Pack de TV Total y Switcher.fifamod`): o `overlay_35002` (Brasileirão) e mais uns 30 iguais. Os moldes vêm das fontes
do Editor de Placares: **adicione o pack do LTA como fonte no Editor de Placares** (Arquivo › Fontes) e clique em
*Atualizar a lista*.

Os moldes com fundo de 1920×1080 (35002, 31002, 32002, 37002…) aceitam o placar em qualquer lugar da tela; nos de fundo
menor (524×128, 1024×1024) o que ficar fora da imagem não aparece.

## O que a conversão faz (modelo do LTA)

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
- Alguns pacotes vêm com o `.bin` comprimido: um cabeçalho de 16 bytes com `WESYS` (tamanho comprimido e tamanho cheio)
  e um fluxo zlib. O conversor abre esses também.
- Alguns placares trazem peças soltas longe do placar (o logo da TV num canto, faixas na tela inteira). O conversor
  pega só o grupo de peças em volta dos nomes, gols e relógio; o resto fica de fora.
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
