# Editor de Estádios FC

> Parte do **BRFP Super Tool**: abra pelo `BRFP Super Tool.bat` (pasta acima de `ferramentas`) e clique em **Estádios** no trilho. O `Editor de Estadios.bat` desta pasta ainda abre só este editor, numa janela própria.


Editor visual para estádios do EA FC exportados pelo **FIFA Editor Tool (FET)**. Abre a pasta exportada, monta o
estádio inteiro em 3D (mundo, world parts, sub-mundos, grupos estáticos, prefabs, luzes, malhas FBX, texturas e o
MeshVariationDb) e grava as edições direto nos XML/FBX/PNG, prontos para importar de volta no FET.

## Como abrir

1. Abra pelo **BRFP Super Tool** ou dê dois cliques em **`Editor de Estadios.bat`** (usa o Python embutido do Super Tool;
   sem ele, um Python 3.10+ instalado).
2. Abre uma janela do editor (Edge/Chrome em modo aplicativo). A janela preta do servidor precisa ficar aberta;
   feche-a para encerrar o editor.
3. Na tela inicial, clique num estádio encontrado (o editor procura exports na pasta acima dele), em
   **Abrir pasta exportada…** (a pasta raiz do export, a que contém `worlds` ou `content`) ou em **Abrir projeto…**.

Linha de comando: `python servidor.py [--porta 8765] [--sem-janela] [pasta_do_export]`.

### O que exportar do FET

- A pasta do mundo do estádio: `content/worlds/stadiums/<estadio>` (ex.: `events_stadium_517`), com o
  `MeshVariationDb_Win32` de cada sub-mundo.
- Os componentes: `content/worlds/components/stadiums/<componentes>` (FBX + XML das malhas e blueprints).
- Opcional: componentes compartilhados (`content/worlds/components/objects/...`). O que não for exportado aparece
  como **caixa tracejada roxa** (malha sem FBX) ou **losango roxo** (blueprint ausente).
- Texturas **não precisam** ser exportadas se o FC 26 estiver conectado (veja abaixo).
- Malhas/texturas de outras pastas podem entrar como **pasta de apoio** (Arquivo › Adicionar pasta de apoio): são só
  leitura; o que é gravado fica sempre na pasta principal.

## Texturas do jogo (FC 26 conectado)

O editor lê as texturas **direto da pasta do FC 26 instalado** (só leitura): ele mesmo lê o catálogo do jogo
(`layout.toc`, os `.toc` de Data/Patch e os manifestos dos bundles) — **não precisa do FMT, do FET nem de exportar a
pasta Content**. Na primeira vez leva uns 20 s; depois o índice fica em `editor/cache/indice_fc26.pkl` e é refeito
sozinho quando o jogo atualiza. Com isso:

- as malhas aparecem com as texturas reais, mesmo sem exportar PNG;
- o seletor de texturas mostra as **247 mil texturas do jogo**, com miniatura, e já preenche o GUID certo ao aplicar.

A pasta do jogo é detectada sozinha (registro do EA app, desinstaladores, bibliotecas da Steam e pastas comuns em
qualquer unidade). Para conferir ou trocar: **Arquivo › Configurações (jogo e texturas)…** (ou "Configurar…" no
resumo do estádio). Lá também ficam o tamanho das texturas na vista (512 a 4096 px) e o botão para desligar as
texturas do jogo. O índice do FMT (`FC26.cache`) virou opcional: só é usado se a leitura direta falhar.

## A interface

| Área | Para quê |
| --- | --- |
| **Estrutura** (esquerda) | Árvore do estádio: grupos (world parts, sub-mundos, grupos estáticos), objetos e luzes. Busca (`Ctrl+F`) e filtros (alterados, ocultos no jogo, não exportados, luzes). Ícone 🎮 = aparece no jogo; 👁 = visível no editor. |
| **Vista 3D** (centro) | Ferramentas à esquerda (selecionar, mover, girar, escalar, eixos, encaixe, seleção em caixa) e exibição à direita (Sólido / Material / Arame / Raio-X, texturas, sombras, luzes, linhas do campo, torcida, vistas). |
| **Propriedades** (direita) | O que está selecionado: visibilidade, transformação numérica, luz, malha, materiais e texturas, arquivo de origem. Sem seleção: resumo do estádio, texturas do jogo, ferramentas e torcida. |

### Navegação e atalhos

- **Arrastar**: girar em volta · **Shift+arrastar** ou botão do meio: mover a câmera · **Roda**: zoom no cursor.
- **Botão direito segurado**: olhar em volta; com **W A S D** voa, **Q/E** desce/sobe, **Shift** acelera.
- **F** enquadra a seleção · **Home** enquadra o estádio · teclado numérico **7 / 1 / 3 / 5** = cima, frente, lado, perspectiva.
- **H** esconde no editor · **Shift+H** esconde o resto · **Alt+H** mostra tudo · **/** isola a seleção.
- **G — mover livre**: o objeto acompanha o mouse, sem eixo. Durante o G: **X / Y / Z** travam num eixo,
  **Shift+X / Y / Z** travam num plano (**Shift+Y** = desliza no chão), **Ctrl** encaixa a cada 0,5 m,
  **clique ou Enter** confirma, **Esc ou botão direito** cancela.
- **W** volta para o gizmo de mover · **Shift** segurado enquanto arrasta a **escala** = proporcional nos três eixos.
  No painel, o **cadeado** ao lado de "Escala" (ou Shift ao digitar) faz o mesmo com os números.
- A escala parte do **chão do campo** (y = 0): o piso do estádio continua no chão. Em "Escalar a partir de" (painel
  de transformação) dá para trocar por base do objeto, centro ou origem.
- **Ctrl+D** duplica as luzes selecionadas.
- **Ctrl+S** grava nos arquivos · **Ctrl+Shift+S** salva o projeto · **?** ou **F1** mostra todos os atalhos.

## Ferramentas

### Luzes: adicionar com um clique e editar

**Ferramentas › Luzes: adicionar e editar…** (ou "Luzes…" no resumo). Clique em **Adicionar com clique** e depois
em qualquer ponto da vista (cobertura, viga, poste): a luz nasce ali, encostada na superfície, e o modo continua
até você apertar **Esc** — um clique por luz. Cada luz nova copia um **modelo** (tipo, cor, intensidade): a luz
selecionada, a escolhida em "Usar a selecionada" / "Trocar o tipo do modelo", ou um spot da cobertura.
"Apontar para" escolhe a direção: centro do campo, para baixo, para fora da superfície ou igual ao modelo.

Com luzes selecionadas: **cor, intensidade, alcance e abertura** (vale para todas), **Duplicar** (`Ctrl+D`, 1 m ao
lado), **Mover (G)**, **Apontar para o centro**, **Apontar para…** (clique no ponto) e **Excluir**. Luzes ligadas à
lógica (show de luzes) não podem ser excluídas — use "Acesa no jogo" (`Enabled = false`). "Reaproveitar luzes
apagadas" usa primeiro uma luz apagada do mesmo tipo e arquivo, em vez de criar outra.

Na vista, o botão da lâmpada mostra as luzes: cone (spot), esfera, cápsula (tubo) e placa (retangular).
**Shift+L** seleciona as do mesmo tipo no grupo.

### Remapear em anel (luzes da cobertura, refletores…)

Para levar as luzes de uma cobertura para outra sem mover uma por uma. Selecione as luzes (ou objetos) e abra
**Ferramentas › Remapear em anel…**. O editor mede o anel atual (elipse) e você ajusta o anel de destino — centro,
raios, altura e inclinação — vendo o resultado ao vivo. Modos: **proporcional** (mantém a posição relativa) ou
**borda** (leva tudo para a linha do anel). **Escolher alvo na vista** + **Anel = caixa do alvo** encaixam o anel
numa cobertura nova; **Encostar** apoia cada item acima ou abaixo da malha do alvo. Cancelar desfaz a prévia.

### Torcida: marcar, colorir e gerar assentos

- **Ferramentas › Torcida: marcar e colorir…**: mostra os assentos coloridos por cor, setor, presença ou
  mandante/visitante. Marque com **caixa** (arraste na vista), **Todos** ou **Nenhum**; depois **Aplicar cor**,
  **Por setor** (uma cor por setor) ou **Imagem…** (projeta uma imagem como a arquibancada aparece na vista — bom
  para mosaicos e escudos). **Remover marcados** apaga assentos.
- **Gerar assentos a partir de malha…**: refaz a nuvem de assentos a partir das placas do **shadow seat** (ou de
  uma malha selecionada). As medidas (largura do assento, distância entre fileiras e altura da placa) são **medidas
  na torcida atual** automaticamente. **Pré-visualizar** mostra os pontos; **Gerar** substitui ou adiciona.
  Cada assento novo herda setor, presença e cor do assento antigo mais próximo (ou uma cor única).

Os assentos gerados olham **sempre para o campo** (as setas da prévia mostram a direção). Se ainda assim a torcida
aparecer de costas no jogo, ligue **Virar todos (180°)** e gere de novo.

Tudo isso entra nas alterações pendentes, com desfazer, e vai para o arquivo `..._crowd_0.xml` ao salvar.

### Banco de reservas, área técnica e pessoas da lateral

O jogo **não** senta os reservas na malha do banco: eles vão para os **assentos do banco** (`choreo_seats`, 7 por
time) e o técnico fica na **área técnica** do `stadiums.txt`. Por isso, mexer só no banco 3D deixa os jogadores
"sentados no ar" no lugar antigo. **Ferramentas › Banco de reservas e área técnica…**: selecione na vista o banco
de um time e clique **Mapear no banco selecionado** — os assentos vão para cima dele, olhando para o campo, e a
área técnica é recalculada na frente. Os números da área também podem ser digitados.

O botão do boneco na vista mostra os assentos do banco (laranja), as áreas técnicas (mandante em azul, visitante
em vermelho) e as **pessoas da lateral** — gandulas, fotógrafos, policiais, seguranças, cinegrafistas, médicos —
que também podem ser movidas. No painel, cada grupo tem um botão para selecionar todos e **Afastar do campo** os
leva para fora a partir da linha mais próxima (bom para um estádio com pista ou fosso maior).

### Estádio no jogo (stadiums.txt): espelhamento e linhas do campo

O editor lê e altera a linha do estádio no `stadiums.txt` (pasta do export, pasta acima ou raiz do workspace),
com backup e restauração como os outros arquivos:

- **Espelhado no jogo (ismirrored)**: com 1, o jogo mostra o estádio espelhado em relação ao arquivo — as
  laterais trocam de lado, guarda-corpos aparecem invertidos e o que não está centrado parece deslocado. O 517
  herdou 1 da linha do Events Rush (518). **Exibir › Ver como no jogo** (botão do espelho na vista) mostra o
  estádio assim; desligar o espelhamento faz o jogo mostrar exatamente o que o editor mostra.
- **Comprimento e largura do campo**: o jogo desenha as linhas com essas medidas, centradas no meio do estádio
  (0, 0). **Centralizar no campo** (Ferramentas, menu do botão direito ou painel da transformação) leva o centro
  da seleção para esse ponto, sem mudar a altura.

### Materiais e texturas

No painel de um objeto, em **Materiais e texturas**:

- **Pincel**: escolhe outra textura. Filtros: usadas neste estádio (seguras), mesmo tipo, todas de estádios e
  mundos, todas do jogo, padrão (`default`), só as exportadas.
- Parâmetro **vazio** (`null`): o pincel também funciona e preenche a textura.
- **Adicionar textura**: cria um parâmetro novo que o shader do material usa (sugere os que outros materiais com o
  mesmo shader têm).
- **Copiar material de…**: o material passa a usar o shader, as texturas e os valores de outro. É o caminho para
  materiais **sem shader** (`Shader = null`), que não têm onde colocar textura.
- **Cor sólida…**: pinta com uma cor lisa — a textura de cor vira a branca padrão do jogo (`default_white_color`) e a
  cor vai para a tinta do shader (`tintColor`). Se o shader não tiver tinta, o editor copia antes um material do
  mesmo sub-mundo que tenha (ex.: `worlds_tint_multiply`). Um passo só de desfazer.

### Linhas do campo

**Exibir › Linhas do campo** desenha o campo oficial (linhas, áreas, gols) sobre o pitch, com as medidas do
`stadiums.txt` (procurado na pasta do export, na pasta acima e na raiz do workspace); sem ele, usa 105 × 68 m.
Só visualização — não altera arquivos.

### Exportar com outro nome (batch import)

**Arquivo › Exportar com outro nome…**: copia os arquivos trocando os nomes (ex.: `events_stadium_517` →
`maracana_517`) nas pastas, nos arquivos e no texto dos XML, para importar em lote no FET por cima de outro
estádio. Escopo: só os alterados, o estádio inteiro ou toda a pasta do export. Os originais não mudam.
Os GUIDs internos continuam os do estádio de origem — teste com poucos arquivos primeiro.

## Projetos e salvamento automático

- **Arquivo › Salvar projeto…** (`Ctrl+Shift+S`) guarda o trabalho em andamento num arquivo `.estadio.json`
  (todas as alterações pendentes, materiais, torcida, câmera e o que está escondido no editor) **sem tocar nos
  arquivos do jogo**. **Abrir projeto…** reabre o export e reaplica tudo.
- O editor também guarda sozinho, alguns segundos depois de cada alteração. Se a janela fechar sem salvar, ao abrir
  o mesmo estádio aparece **Recuperar**.

## O que cada edição grava

Nada é gravado até você clicar em **Salvar** (`Ctrl+S`). Tudo tem **desfazer/refazer** (`Ctrl+Z` / `Ctrl+Shift+Z`).

| Edição | Arquivo e campo |
| --- | --- |
| Ocultar objeto no jogo | `Excluded = true` na referência (world part / layer / prefab). |
| Ocultar objeto **ligado à lógica** (placar, telões, luzes do show…) | Não exclui (pode travar o jogo): o objeto desce **150 m** para baixo do chão. |
| Ocultar cópia de **grupo estático** | `Visible = false` na lista do grupo **e** 150 m para baixo (uma cópia invisível ainda projeta sombra). |
| Ocultar grupo inteiro (world part / sub-mundo) | `Excluded` da referência no mundo. Recusado se o grupo tiver objetos ligados à lógica. |
| Mover / girar / escalar | `BlueprintTransform` da referência ou `InstanceTransforms` do grupo estático, e a entrada de iluminação `LightmapGenMeshInstance` da mesma malha no mundo. Números que não mudaram de fato ficam como estavam. |
| Mover / apagar luz | `Transform` e `Enabled` da própria luz (ex.: `lighting_main.xml`). |
| Cor, intensidade, alcance, abertura da luz | `Color`, `Intensity`, `AttenuationRadius`, `OuterAngle` da luz. |
| Luz nova | Cópia da instância modelo no mesmo arquivo, com GUID e `Flags` novos, posta na mesma lista de objetos. |
| Excluir luz | Remove a instância e a referência a ela na lista de objetos. |
| Assentos do banco / pessoas da lateral | `BlueprintTransform` em `choreo_seats.xml` / `slc_*.xml`. |
| Espelhamento, área técnica, medidas do campo | Linha do estádio no `stadiums.txt` (`ismirrored`, `stad*techzone*`, `stadiumpitch*`). |
| Trocar / preencher / adicionar textura, mudar cor ou valor | O `MeshVariationDb_Win32` do sub-mundo (é o que o jogo usa; o XML da malha é ignorado). Vale para todas as cópias daquela malha no sub-mundo. |
| Copiar material | No MVDB: o bloco do shader (shader, texturas, valores) e `SurfaceShaderId` / `SurfaceShaderGuid` das entradas. |
| Torcida (cores, remover, gerar) | A nuvem `..._crowd_0.xml`: lista `Data` e todos os mapas por assento (`SeatColor`, `SeatTier`, `Orientation`…). |
| Substituir FBX de uma malha | O próprio `.fbx` (o editor compara as seções antes: o FET liga as seções **pela ordem**). |
| Substituir imagem de uma textura | O `.png` exportado (redimensionado para o tamanho original). |

"Visível no editor", modo de exibição, luzes/linhas do campo na vista, texturas ligadas/desligadas no editor e
isolamento **não** alteram arquivos.

### Originais e lista de alterações

- Na primeira vez que um arquivo é alterado, o original é copiado para **`_editor_originais/`** (mesmo caminho),
  dentro da pasta do export. Essa cópia nunca é sobrescrita.
- **Alterações** (botão no topo) lista os arquivos que diferem do original, com o caminho do asset para importar no
  FET; dá para abrir no Explorer, restaurar o original (um ou todos) e **copiar os alterados para outra pasta**.

### Importando no FET

Para cada arquivo da lista **Alterações**: no FET, localize o asset pelo caminho mostrado (ex.:
`content/worlds/stadiums/events_stadium_517/standslower`) e importe o XML/FBX/PNG por cima dele.

## Limitações conhecidas

- Sem o FC 26 conectado, texturas que não estão no export aparecem como uma **cor estimada** pelo nome.
- Trocar uma textura por outra que só **outro mundo** carrega deixa a seção **branca** no jogo — o seletor mostra
  primeiro as texturas que o estádio já usa (seguras).
- Os assentos gerados dependem das placas do shadow seat: onde não há placa, não há assento.
- Luzes novas, exclusão de luzes e o efeito exato do `ismirrored` ainda não foram testados no jogo: comece com
  poucas luzes e confira.
- Não dá para criar objetos novos nem esconder uma única seção de uma malha no jogo (isso é edição de FBX: use o
  Blender e depois **Substituir FBX…**).
- O editor mostra só o LOD0 das malhas; partes de malhas compostas aparecem na posição do FBX.
