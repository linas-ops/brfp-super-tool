# Conversor de Kits PES → FC — versão 1.1

Converte kits do **PES 2021** em kits do **FC 27**.

O kit do PES tem tudo numa textura só: camisa (frente e costas), mangas curtas e longas, gola, calção e meião. No FC 27
cada peça tem a sua textura (`jersey` 2048×2048, `shorts` 1024×512, `socks` 512×256), com outra UV e outras proporções.
O conversor refaz as três texturas do FC a partir da do PES, com as listras, o escudo, os patrocínios, os logos das
mangas e os detalhes do calção e do meião no mesmo lugar do corpo e na mesma proporção, e grava a pasta do kit no
formato que o FET exporta e importa.

## Usar

1. **Adicionar kits**: `Arquivo › Adicionar kits do PES…` (`Ctrl+O`), `Adicionar pasta…` (`Ctrl+Shift+O`, varre as
   subpastas) ou arrastar imagens para a janela. Vale PNG, DDS, TGA, JPG, BMP e TIFF (a textura do kit do PES, quadrada,
   2048×2048 ou 1024×1024).
2. **Kit base do FC 27** (painel da direita, *Saída e opções*): a pasta de um kit qualquer exportado pelo FET — a pasta
   `home_0_0`, `away_1_0`… com `jersey/`, `shorts/`, `socks/` e o `hotspots_….hotspot`. Dele vêm o relevo e o brilho do
   tecido (`normal`, `coeff`, `taa`, `weave`), a braçadeira de capitão e o hotspot; só a cor é trocada. Prefira um kit
   liso, sem relevo de listras ou desenhos no tecido.
3. Para cada kit, no painel da direita:
   - **ID do time**: o `teamid` do banco do FC 27.
   - **Pasta do time**: o nome da pasta do time, em minúsculas (ex.: `guarani`). Ao digitar aparecem os times que já têm
     pasta na pasta dos kits; escolher um preenche o ID.
   - **Tipo**: 1º uniforme (`home`), 2º (`away`), goleiro (`goalie_home`), 3º (`third`) ou 4º (`fourth`). Vem sugerido
     pelo nome do arquivo do PES (`u0101p1` = 1º uniforme, `p2` = 2º, `g1` = goleiro…).
   - **Variação**: 0 é o kit normal.
   - **Time nos outros** copia o ID e a pasta para os kits da lista que ainda não têm time (ex.: `p1`, `p2` e `g1` do
     mesmo time).
4. **Pasta dos kits (saída)**: em branco, os kits vão para `Kits FC 27` ao lado das texturas do PES. Escolha a pasta
   `kit` do mod para gravar direto nela. Cada kit vira `kit_<faixa>\<time>_<id>\<tipo>_<n>_<v>` (ex.:
   `kit_111000\guarani_111329\home_0_0`), com os arquivos já renomeados (`jersey_111329_0_0_color.png`…) e o hotspot
   apontando para a pasta nova.
5. Opções:
   - **Escudo e marca do kit base**: *Apagar* (padrão — o kit do PES já traz escudo e marca desenhados; os do kit base
     ficam transparentes para não aparecerem duas vezes) ou *Manter*.
   - **Tecido (coeff e taa)**: do kit base ou *Liso* (o valor mais comum do kit base, sem os desenhos dele).
   - **Substituir kits existentes**: apaga e grava de novo a pasta de um kit que já existe. Desligado, ele é pulado.
6. **Converter** (`Ctrl+Enter`). Leva uns 5 s por kit. A pasta dos kits recebe o `relatorio_conversao_kits_pes.txt`.
7. A **prévia** mostra o kit do PES e, depois de converter, o kit do FC 27 (`Tab` alterna), **plano** (camisa, calção ou
   meião) ou **vestido em 3D** (`P` alterna). Arraste para girar, roda do mouse para aproximar, `F` enquadra.

## Como funciona

A correspondência entre as duas texturas foi medida uma vez nos uniformes em 3D dos dois jogos (o kit do PES 2021 com a
UV do jogo e as malhas de camisa, calção e meião do FC 27 exportadas pelo FET) e vem pronta em
`motor/mapas/mapas_pes2021_fc27.npz`: para cada pixel do FC, o ponto da textura do PES que veste o mesmo lugar do corpo.

- **Tronco, calção e meião**: as duas malhas são alinhadas parte por parte e cada ponto do FC vai ao ponto mais
  próximo da superfície do PES (do mesmo lado: frente com frente, costas com costas).
- **Pescoço e gola**: a gola do PES não tem nada a ver com a do FC, então não é copiada. O tronco do PES tem um buraco
  em T no decote (onde fica a gola e a carcela, e onde o kit do PES desenha a gola): ali o conversor continua o desenho
  do tronco, coluna por coluna, até o decote do FC, sem esticar a borda. A gola do FC sai lisa, na cor predominante da
  camisa, para pôr a gola do FC à mão.
- **Mangas**: os braços dos dois jogos têm tamanhos diferentes, então as mangas são medidas em volta do braço (da cava ao
  punho, e o ângulo em volta dele). A manga longa do FC (que não tem malha no FET) segue a volta da manga curta, e a do
  PES é lida linha a linha na UV: as listras ao longo da manga ficam retas, como nos kits do FC.
- **Braçadeira de capitão**: a faixa da braçadeira na textura da camisa fica a do kit base.
- Onde o FC encolhe a textura (calção e meião, que no FC têm menos pixels), a cor é filtrada (mipmap) para não serrilhar;
  fora das ilhas da UV do PES a borda é repetida, para o fundo não vazar.

## Limitações

- Feito para o layout do kit do **PES 2021** (o do modelo de kit do BRFP). Kits de outro PES com outra UV não saem certos.
- A camisa do FC usa a UV da malha `jersey_0_0_0_0_1_0_0`. A gola não vem do PES (sai lisa, na cor da camisa): a do FC
  (`jerseycollargeometrytype` do `teamkits`) é posta à mão.
- **Números e nomes** nas costas não vêm do kit do PES: são os do jogo (`kitnumbers`, cores no `teamkits`).
- Ainda não testado no jogo.

## Técnico

A interface (`servidor.py`) roda em Python padrão; a conversão (`motor/conversor.py`, numpy, SciPy e Pillow) roda no
Python embutido do Super Tool (`runtime\python`), chamada por `motor/ponte.py` (um evento JSON por linha). Os pacotes são
os mesmos do Conversor de Corpos; se faltarem, a ferramenta oferece o download — ou use a página **Componentes** do
Super Tool. DDS é lido pelo Pillow ou, se ele não souber o formato, pelo texconv que vem com o Super Tool.

A prévia 3D usa os modelos dos uniformes tirados dos jogos (`motor/referencia`: `pes2021_kit.obj`,
`jersey_0_0_0_0_1_0_0_mesh.fbx`, `shorts_0_0_0_mesh.fbx`, `sock_0_0_1_0_0_mesh.fbx`), que não vêm no pacote leve: sem
eles a conversão funciona igual e a prévia fica plana (`Arquivo › Importar referências…` traz do pacote completo).

Linha de comando:
`runtime\python\python.exe ferramentas\kits_pes\motor\conversor.py KIT_PES.png --base PASTA_DO_KIT_BASE --saida PASTA
--teamid 111329 --time guarani [--tipo home] [--variacao 0] [--manter-escudo] [--tecido-generico] [--substituir]`.

Para refazer os mapas (só quem desenvolve, com os modelos em `motor/referencia`):
`runtime\python\python.exe -X utf8 ferramentas\kits_pes\motor\gerar_mapas.py`.
