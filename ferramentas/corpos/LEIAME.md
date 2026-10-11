# Conversor de Corpos FC 26 ↔ FC 27 — versão 1.0

Converte a textura do corpo (**bodyupper**: pele, tatuagens e mapa normal) de um jogo para o outro.

O corpo é o mesmo nos dois jogos, mas a **UV mudou toda**: no FC 26 os braços ficam nas laterais da textura, as mãos
embaixo e as costas aparecem divididas ao lado do peito; no FC 27 os braços (com as mãos) são duas colunas à esquerda e
costas e peito ficam inteiros à direita. Uma textura de tatuagem feita para um jogo fica embaralhada no outro. O
conversor refaz a textura no layout do outro jogo, com cada tatuagem no mesmo lugar do corpo.

## Usar

1. **Adicionar texturas**: `Arquivo › Adicionar texturas…` (`Ctrl+O`), `Adicionar pasta…` (`Ctrl+Shift+O`, varre as
   subpastas) ou arrastar imagens para a janela. Vale PNG, DDS, TGA, JPG, BMP e TIFF.
2. Cada textura aparece com o **layout identificado** (FC 26 ou FC 27), o destino, o tipo (cor ou normal) e o tamanho.
   O layout é identificado sozinho pelas emendas da UV; quando a identificação fica em dúvida aparece um ⚠ — escolha o
   layout no painel da direita (ou botão direito › *A textura está no layout do…*).
3. **Saída e opções** (painel da direita):
   - **Pasta de saída**: em branco, cada textura vai para `<pasta>_FC27` (ou `_FC26`) ao lado da pasta adicionada, ou
     para `Convertidos_FC27` ao lado do arquivo. A saída é sempre **PNG**, com o mesmo nome. A entrada nunca é alterada.
   - **Converter para**: o outro jogo (automático), tudo para FC 27 ou tudo para FC 26.
   - **Tamanho da saída**: igual à entrada (padrão), 1024, 2048 ou 4096. A textura do jogo tem 1024×1024.
   - **Tipo de textura**: automático (o mapa normal é reconhecido pelo nome — `…normal`, `…_n` — ou pelas cores
     azuladas), tudo cor ou tudo normal.
   - **Sobrescrever existentes**.
4. **Converter** (`Ctrl+Enter`) converte a lista; o botão direito numa textura converte só ela. Cada pasta de saída
   recebe o `relatorio_conversao_corpos.txt`.
5. A **prévia** mostra a textura **no corpo em 3D** (o corpo do jogo daquele layout) ou **plana** (`P` alterna):
   **Entrada** e, depois de converter, **Resultado** (`Tab` alterna). Arraste para girar, roda do mouse para aproximar,
   `F` enquadra. No 3D dá para conferir se a tatuagem caiu no lugar certo antes de importar no FET.

## Como funciona

Cada pixel do layout de destino é levado ao ponto correspondente do corpo em 3D; o conversor acha o ponto mais próximo
no corpo do jogo de origem e pinta o pixel com a cor da textura de origem ali (precisão típica de 0,2 mm na superfície).
Fora das ilhas da UV, a borda é repetida (sem costura escura com mipmaps).

- **Mapa normal**: as direções giram junto com a UV (as ilhas mudaram de orientação), no padrão DirectX (verde para
  baixo). Mapas de dois canais (BC5, azul constante) continuam com dois canais.
- **Topo do pescoço**: o corpo do FC 27 sobe ≈2 cm a mais no pescoço (2,2% da textura) do que o do FC 26. Essa faixa,
  que fica embaixo da cabeça, é preenchida com a cor da pele em volta.
- Os corpos de referência são o `bodyupper_0_mesh` LOD0 exportado pelo FET de cada jogo (pasta `motor/referencia`,
  não apague).
- A correspondência de cada tamanho é calculada uma vez e guardada em `cache/mapas` (≈15 s em 1024, ≈45 s em 2048; a de
  1024 é calculada sozinha na primeira vez que a ferramenta abre). Depois disso cada textura leva 1 a 2 s.

## Limitações

- Só a textura do **bodyupper** masculino (o corpo de cima com braços e mãos). Pernas e corpo feminino usam outras malhas.
- A malha (FBX) do corpo não é convertida: o corpo do jogo continua o mesmo, só a textura muda.
- Detalhe que a textura de origem não tem não aparece no destino (ex.: a faixa extra do pescoço do FC 27).
- Ainda não testado no jogo.

## Técnico

A interface (`servidor.py`) e a conversão (`motor/texturas.py`, numpy, SciPy e Pillow) rodam no Python embutido do Super
Tool (`runtime\python`); a conversão é chamada por `motor/ponte.py` (um evento JSON por linha). O FBX é lido pelo
leitor do Conversor de Faces (`ferramentas\faces\motor`). Se faltarem os pacotes, a ferramenta oferece o download — ou use
a página **Componentes** do Super Tool. DDS é lido pelo Pillow ou, se ele não souber o formato, pelo texconv que vem com o
Super Tool.

Linha de comando:
`runtime\python\python.exe ferramentas\corpos\motor\texturas.py ENTRADA [...] [--para fc27|fc26] [--de fc26|fc27]
[--saida PASTA] [--tamanho 2048] [--tipo cor|normal]`.
