# Editor de Placares FC

> Parte do **BRFP Super Tool**: abra pelo `BRFP Super Tool.bat` (pasta acima de `ferramentas`) e clique em **Placares** no trilho. O `Editor de Placares.bat` desta pasta ainda abre só este editor, numa janela própria.


Editor visual dos placares e overlays de transmissão do **EA SPORTS FC 26**. Abre os placares do jogo instalado ou de
mods `.fifamod` (como o pack de placares do LTA), mostra como ficam na tela, deixa mover/redimensionar os elementos,
mudar cores, esconder peças e trocar imagens, **toca as animações** do placar (e deixa mudar tempos, posições e
curvas), troca e **importa fontes** dos textos, e grava o placar editado numa pasta de saída — por padrão a pasta
`mods\legacy` do Live Editor, que o jogo carrega quando é aberto pelo Live Editor.

O editor **nunca altera o jogo nem os mods**: lê deles e grava só na pasta de saída.

## Como abrir

1. Abra pelo **BRFP Super Tool** ou dê dois cliques em **`Editor de Placares.bat`** (usa o Python embutido do Super Tool;
   sem ele, um Python 3.10+ instalado).
2. Abre uma janela do editor (Edge/Chrome em modo aplicativo). A janela preta do servidor precisa ficar aberta.
3. Na tela inicial: **Abrir o placar do jogo** (Generic / overlay_9002), **Ver todos os placares** ou **Abrir mod .fifamod…**.

Linha de comando: `python servidor.py [--porta 8766] [--sem-janela]`.

A pasta do FC 26 é detectada sozinha (registro do EA app, Steam, pastas comuns). Na primeira vez o editor lê o
catálogo do jogo (~3 s) e guarda um índice em `cache\legacy_fc26.pkl`; depois abre na hora.

## A interface

| Área | Para quê |
| --- | --- |
| **Arquivos** (esquerda) | Escolha a fonte (FC 26, um mod, uma pasta) e o conjunto de placares. Cada conjunto lista os overlays com nome (002 = placar principal, 018 = escalação, 005 = substituição…) e os componentes. Ponto azul = já editado. |
| **Camadas** | A árvore do overlay aberto (grupos, formas, textos, componentes). Clique para selecionar, olho = esconder só no editor. Filtro "Com nome" esconde as peças sem nome. |
| **Imagens** | Todas as imagens (texturas DDS) do arquivo, para trocar ou exportar. |
| **Animação** | A linha do tempo das animações do placar (uma barra por elemento e propriedade), com o editor de cada animação (destino, duração, atraso, curva) e as constantes de tempo/posição da classe. |
| **Fontes** | Os formatos de texto do código (família + tamanho), as fontes dos campos de texto do arquivo e as famílias do tema (`FIFA.xml`), com **Importar fonte (.ttf)**. |
| **Linha do tempo** (embaixo da prévia) | Aparece com a prévia da animação: tocar/pausar, arrastar quadro a quadro, qual animação simular (entrada, entrada e saída, outros métodos), velocidade e quadros por segundo. |
| **Prévia** (centro) | O overlay na tela 1920×1080. Fundo: campo, xadrez, escuro ou uma **captura do jogo** sua (ótimo para alinhar). |
| **Propriedades** (direita) | Posição, escala, rotação, cor (tingir/somar), opacidade, "visível no jogo", cores das formas, texto (cor, tamanho, alinhamento, fonte, caixa) e imagens usadas. |

### Navegação e atalhos

- **Clique** seleciona (o grupo com nome mais próximo) · **Alt+clique** ou duplo clique: a peça interna.
- **Arrastar** move o selecionado (Shift = só num eixo, Ctrl = sem arredondar) · **setas** 1 px (Shift: 10 px).
- **Roda** = zoom no cursor · **botão direito** ou **Espaço+arrastar** = mover a vista.
- **F** enquadra a seleção · **Home** enquadra o placar · **Esc** sobe para o grupo de cima · **H** esconde no editor.
- **Ctrl+S** salva · **Ctrl+Z / Ctrl+Shift+Z** desfaz/refaz · **F1** mostra os atalhos.
- Prévia da animação: **Espaço** toca/pausa · **← →** quadro a quadro (Shift: 10) · **Home / End** início/fim.

### O que dá para editar

- **Posição, escala, rotação e espelhar** de qualquer elemento do arquivo (os números ficam no APT, sem mudar o
  tamanho do arquivo).
- **Cor**: *Tingir* multiplica as cores (branco = original), *Somar cor* soma por cima, *Cor sólida* deixa o elemento
  exatamente daquela cor, *Opacidade* e *Visível no jogo* (transparente).
- **Formas de cor sólida** (barras, fundos, linhas): cor e opacidade direto na forma.
- **Textos** do próprio arquivo: cor, tamanho, alinhamento, fonte e a caixa.
- **Imagens**: *Exportar PNG*, editar no Photoshop/GIMP e *Trocar…*. Na aba **Imagens**, **Exportar todas** grava todas as
  imagens do placar em PNG de uma vez (em `exportados\<placar>_imagens`, que abre no fim) e **+ componentes** também as dos
  componentes usados (de outros arquivos .big), cada um numa subpasta. A nova imagem pode ter **qualquer tamanho**
  (até 4096 px): o editor ajusta as coordenadas de textura para ela ocupar o mesmo lugar da original. Dica: dobre o
  tamanho para ficar mais nítido. A imagem é gravada como DDS 32 bits sem compressão (formato que o jogo usa em
  vários overlays).
- **Animações** (aba Animação): duração, atraso, destino e curva de cada animação, e as constantes da classe
  (`ANIM_NORMAL_DUR`, `ANIM_IN_LOGO_Y_POS`…). Veja "Animações" abaixo.
- **Fontes** (aba Fontes): a família e o tamanho de cada formato de texto do código, a fonte dos campos de texto do
  arquivo e fontes novas importadas de um `.ttf`. Veja "Fontes" abaixo.
- **Salvar como outro arquivo**: grava o placar com outro caminho — por exemplo, usar o placar do Brasileirão do LTA
  (`overlay_35002`) no lugar do placar Generic (`Generic/overlay_9002`).

### Limites da prévia

- Os placares do FC são **animados por código** (ActionScript): o jogo preenche os textos (times, placar, relógio),
  carrega os escudos, aplica as cores dos times e mostra/esconde peças (cartões vermelhos, acréscimos, agregado…).
  Parada, a prévia mostra o arquivo como ele está, com **textos de exemplo** e escudos genéricos — por isso aparecem
  peças que no jogo ficam escondidas. Use o olho (H) para esconder o que atrapalha, ou a **prévia da animação**.
- **Máscaras** (botão do alvo na barra da vista): o jogo também anima os recortes; ligadas, a prévia corta como o
  arquivo está; desligadas (padrão), aparece tudo. A prévia da animação liga as máscaras (e devolve como estava ao sair).
- Componentes importados (MultiText, TextBox, ImageLoader…) vêm de outros arquivos: para mudar o que está **dentro**
  deles, use "Abrir o arquivo do componente".

## Animações

Os placares do FC **não têm animação desenhada em quadros**: a classe do placar (ActionScript) chama
`AnimationManager.Animate(clipe, propriedade, destino, duração, curva, …, atraso)` — duração e atraso em **quadros**
(60 por segundo nos placares novos, 30 nos mais antigos; o arquivo diz). Os números costumam ser constantes no fim da
classe, como `ANIM_NORMAL_DUR = 10` ou `ANIM_IN_LOGO_Y_POS = 44`.

O editor **roda esse código num simulador** (com o `AnimationManager` e o `StyleManager` de verdade, lidos dos arquivos
do jogo, e os valores do tema `FIFA.xml`) e monta a linha do tempo: o que se move, de onde para onde, quando, por quanto
tempo e com qual curva. **Ver a animação** toca o resultado sobre a prévia.

- **Clique numa barra** da aba Animação para abrir o editor daquela animação: *Destino*, *Duração*, *Atraso* e *Curva*
  (com o desenho da curva — as curvas são as do próprio jogo, amostradas das funções `EaseOutCubic`, `EaseBounce`…).
  Ao lado de cada valor o editor diz **de onde ele vem**: uma constante da classe (mudar vale para todas as animações
  que a usam — o editor mostra quantas), um número escrito naquele trecho do código, um valor do tema ou "calculado
  pelo código" (não editável).
- **Constantes usadas nas animações** e **Outras constantes da classe**: os números da classe, editáveis.
- Selecionando um elemento, o painel da direita mostra as animações dele. Se a animação leva o elemento até uma posição
  fixa (ex.: Y = 17), o editor avisa: **mover o elemento na prévia muda só a posição antes da animação** — para mudar
  onde ele termina no jogo, mude o *Destino*.
- Na linha do tempo escolha **Entrada (AnimateIn)**, **Entrada e saída** (`Remove`) ou outros métodos do placar
  (acréscimos, agregado, cartões…).
- Na prévia da animação dá para selecionar, mas não arrastar elementos: feche a prévia (✕) para voltar a mover.

Limites: o simulador é **aproximado**. Ele não sabe os textos e escudos reais da partida (posições calculadas pela
largura do texto usam uma estimativa), não roda o que vem de outros arquivos além do `AnimationManager`/`StyleManager`,
não mostra mudanças de quadro (`gotoAndStop`) e alguns laços que dependem de valores de fora são interrompidos — a aba
avisa quando isso acontece. Dos 799 overlays do jogo, 784 simulam sem aviso e 8 não têm código de animação.

Como fica no arquivo: números são trocados **no lugar** (mesmo tamanho). Trocar a curva ou a família de fonte cria um
texto novo: o editor acrescenta o texto na tabela de constantes (entrada `1` do `.big`, copiada uma vez para o fim) e
uma posição a mais no `ConstantPool` daquele trecho (no fim do APT) — o mesmo mecanismo que o código já usa, só para
aquele ponto. O arquivo cresce (~90 KB na primeira troca de texto). **Ainda não foi testado dentro do jogo.**

## Fontes

Como o jogo acha a fonte de um texto do placar:

1. O código cria `new TextFormat(StyleManager.FONT_NAME_X, tamanho, cor)` e passa ao componente de texto (MultiText).
2. `FONT_NAME_X` é uma **família** do tema: `<font_family NAME="FONT_NAME_X" VALUE="Face" CACHE="TRUE"/>` em
   `data/ui/themes/FIFA.xml`.
3. `Face` é o **nome do arquivo** `data/ui/fonts/Face.ttf` (o nome interno da fonte não importa — o LTA usa arquivos
   como `Brasilerao-A.ttf` com a fonte "Assemblage W00").
4. `data/ui/fonts/font_extents.txt` tem um bloco de medidas por face; o LTA copia o mesmo bloco (o do EuropaNuova) para
   todas as fontes novas, e o editor faz igual.

Na aba **Fontes**:

- **Textos do placar**: cada formato do código, com os elementos que o usam. Trocar a *Fonte* (família) ou o *Tamanho*
  muda só **este placar** (vai no `.big` ao salvar).
- **Campos de texto do arquivo**: alguns placares (vários do LTA) desenham textos no próprio arquivo, com o nome da face
  direto. Dá para trocar a face; prefira faces que tenham família no `FIFA.xml`.
- **Importar fonte (.ttf)**: escolha o arquivo, o nome (vira `data/ui/fonts/<nome>.ttf`) e a família
  (`FONT_NAME_…`), e marque em quais textos deste placar usar. O editor grava **na hora** na pasta de saída: o `.ttf`,
  um `FIFA.xml` e um `font_extents.txt`. Os textos do placar mudam quando você **salva o placar**.
- **Trocar a fonte de uma família** (pincel na lista do tema): muda o arquivo de fonte de uma família existente —
  vale para **todos os placares e menus** que usam essa família.
- ★ marca as famílias criadas/alteradas por você; o ✕ desfaz (tira do `FIFA.xml` da saída e apaga o `.ttf` copiado).

**Atenção ao `FIFA.xml`**: o arquivo gravado na saída **substitui** o do jogo e o dos mods (o Live Editor carrega a
pasta `mods\legacy` por cima de tudo). Por isso o editor monta o `FIFA.xml` a partir da versão em uso — se o pack do
LTA estiver na lista de fontes (Arquivo › Fontes), a base é o `FIFA.xml` dele, com as fontes, cores e escudos do LTA.
**Adicione o `.fifamod` do LTA como fonte antes de importar fontes.** Se a base mudar depois (um mod adicionado), a aba
oferece **Refazer com a base atual**. As famílias que você definiu ficam em `projetos\tema_*.json` e são reaplicadas.

## Onde é gravado

**Pasta de saída** (botão "Saída" no topo):

- **Live Editor — `C:\FC 26 Live Editor\mods\legacy`** (padrão): o arquivo vai para
  `mods\legacy\data\ui\game\overlays\...`. Abra o jogo pelo Live Editor para ver.
- **Outra pasta**: mesma árvore `data\ui\...`, para importar no FIFA Editor Tool (Legacy Explorer › importar pasta).

Cada arquivo gravado tem um projeto em `projetos\` (fonte original + edições): ao reabrir o placar, as edições
voltam; **Arquivo › Descartar edição gravada** apaga o arquivo da saída (ou devolve o que estava lá antes — o editor
guarda uma cópia em `projetos\backup` se a saída já tinha um arquivo que não era dele). Imagens importadas ficam em
`projetos\imagens`; PNGs exportados em `exportados\`.

## Fontes de placares

**Arquivo › Fontes** (ou o botão de engrenagem na aba Arquivos):

- **FC 26** — lido direto do jogo instalado (só leitura).
- **Mods .fifamod** do FET (formato novo "FETM"), só leitura — ex.: `Pack de TV Total y Switcher.fifamod` do LTA.
- **Pastas** com a árvore `data\ui\...` (a própria `mods\legacy` do Live Editor, um export do Legacy Explorer…).

Componentes importados, fontes TTF e imagens são procurados na ordem: a mesma fonte, a saída, os mods, as pastas e o
jogo — a mesma ordem em que o jogo veria os arquivos com os mods instalados.

## Como o FC 26 guarda os placares (o que o editor lê)

- Cada overlay é um arquivo **legacy** `data/ui/game/overlays/<pasta>/overlay_<conjunto><tipo>.big`. O número do
  conjunto vem antes dos 3 últimos dígitos (Generic = 9: `overlay_9002` é o placar do conjunto 9). Conjuntos do jogo:
  LaLiga 4, o05Penta 5, EPL 6, Bundesliga 7, FUT 8, Generic 9, Champions 10, Europa 11, SuperCup 12, Ligue1 13,
  SerieA 14, SSF 15, Conmebol 16, APL 17, WSL 18, WUCL 20, NWSL 21, Frauen-Bundesliga 22, Liga F 23, EFL 24.
  Conjuntos novos (de mods) ficam direto em `overlays/overlay_<N><tipo>.big`.
- Peças comuns: `data/ui/game/globalComponents/...` (MultiText, TextBox, ImageLoader…), importadas pelos overlays.
- Dentro do `.big`: entrada `0` = **APT** de 64 bits (`Apt Data:1:7:8`, o formato tipo Flash da EA: grupos, formas,
  textos, posições, cores e ActionScript), `1` = constantes (`Apt1`), `N` = geometria (formas) ou DDS (imagens) do
  character N-1.
- O jogo guarda só o **hash** (FNV-1 64) do caminho; os nomes vêm da lista do Live Editor
  (`legacy_filename_hash_list.csv`), de padrões conhecidos e das fontes citadas no `data/ui/themes/FIFA.xml`.
- **Qual conjunto cada competição usa** fica nos EBX `broadcasting/attribsys/presentation/overlays/overlays_tournament_<id>`
  (e `overlays_country_<país>[_<id>]`): número do conjunto + paleta de cores. Esses EBX só mudam pelo FET (o editor
  ainda não os altera).

## O pack de placares do LTA

`Add Ons\Marcadores\Pack de TV Total y Switcher.fifamod` (v2.5, TU 1.6.6) traz:

- **8.180 arquivos legacy**: overlays de 43 conjuntos novos (30 = Argentina A … 35 = Brasileirão A, 37 = Copa do
  Brasil, 47 = Equador, 56 = Colômbia, 61 = Liga MX, 88 = Concacaf, 90 = Copa do Mundo…), cada um com ~117 overlays
  em `overlays/overlay_<N><tipo>.big` (vários partem de placares antigos — o nome interno do placar do Brasileirão é
  `game.overlays.FACup.overlay_5002`), componentes `globalComponents/overlayComponents_<N>/` e `globalComponents/o<N><Nome>/`,
  fontes novas (`data/ui/fonts/*.ttf` + `fonts/font_extents.txt` + `themes/FIFA.xml` com os nomes `FONT_NAME_*`) e
  escudos (`imgAssets/crest...`).
- **134 EBX** `overlays_tournament_*` / `overlays_country_*` ligando as competições aos conjuntos.
- `Setpieces OFF.fifamod`: 319 overlays trocados para esconder o menu de botões nas bolas paradas.

O **script do Live Editor** (`C:\FC 26 Live Editor\lua\autorun\AdrianScriptsRunner.lua`) é um carregador: executa os
quatro scripts cifrados `lua\autorun\LTA\*.ltab` com uma chave que vem no banco de dados do mod. A lógica do
"switcher" (trocar o placar conforme a competição) está nesses scripts fechados — o editor não depende deles.

## Arquivos

```
editor de placares\
  Editor de Placares.bat   abre o editor
  servidor.py              servidor local (127.0.0.1:8766) e rotas
  nucleo\jogo.py           catálogo do FC 26: coletores de arquivos legacy, Oodle, leitura
  nucleo\fifamod.py        leitor de .fifamod (FETM)
  nucleo\big.py            .big (BIGF/BIG4)
  nucleo\apt.py            APT 64 bits: leitura, geometria, DDS e as edições
  nucleo\as2.py            ActionScript do APT: simulador das animações e edição de números/textos do código
  nucleo\tema.py           FIFA.xml e font_extents.txt: famílias de fonte e valores do tema
  nucleo\fontes.py         fontes (jogo, mods, pastas) e conjuntos
  nucleo\projetos.py       edições gravadas, imagens importadas, cópias de segurança
  web\                     interface (WebGL2); js\animacao.js = prévia da animação, js\codigo.js = abas Animação e Fontes
```
