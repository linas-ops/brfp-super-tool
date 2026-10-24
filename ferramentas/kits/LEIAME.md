# Criador de Kits do FC 27 — versão 1.0

Monta um uniforme do FC 27 (camisa, calção, meião, escudo, marca e hotspot) a partir de um **kit doador** exportado pelo
FET. A ferramenta troca as cores do doador, desenha o padrão do tronco (listras, faixas, metades…) e coloca os logos.
Uma **foto da camisa** de frente preenche cores, padrão e logos sozinha; depois é só conferir e ajustar.

A saída é a pasta do kit no formato do jogo (`kit_<faixa>/<time>_<teamid>/<tipo>_<n>_<v>/…`), pronta para importar no FET.

## Usar

1. **Doador**: na primeira vez, escolha a pasta com os kits exportados pelo FET (a pasta `kit`, com `kit_1000`,
   `kit_111000`…). Todos os kits do FC 27 usam o mesmo molde, então qualquer um serve; prefira um **liso**, sem
   patrocinadores estampados (o tecido deles pode aparecer). O doador dá as costuras, o tecido e as posições de escudo,
   marca, números e nome.
2. **Foto** (opcional): `Arquivo › Abrir foto da camisa…` (`Ctrl+O`) ou arraste a foto para a janela. A melhor foto é de
   produto: camisa de frente, esticada, fundo liso. A ferramenta:
   - tira o fundo e acha a caixa do tronco (rosa: recorte; azul: tronco; verde: axila, na imagem de conferência);
   - acha as cores (com correção do branco azulado/amarelado da luz), o padrão (listras verticais ou horizontais, faixa,
     metades) e as cores de manga e gola;
   - recorta os logos que destoam da camisa e sugere o papel de cada um (escudo, marca, patrocinador). Mude o papel ou
     marque **Ignorar** na lista e clique em **Aplicar ao kit**.
3. **Ajustar** (painel da direita, por peça — abas Camisa, Calção e Meião, ou `1`, `2`, `3`):
   - **Cores**: base, padrão/detalhes e, na camisa, mangas, gola e punhos (desligados = cor base). **Detalhe do tecido**
     mantém dobras, costuras e o desenho tom sobre tom do doador.
   - **Padrão**: lisa, listras verticais, aros, xadrez, metades, faixa diagonal, faixa no peito, V no peito, degradê,
     com distância, espessura, posição e inclinação. Na camisa o padrão vai no tronco, contínuo da frente para as costas.
   - **Cores do doador**: cada cor do doador “segue a peça” (recebe base, padrão, manga…) ou tem **cor própria** (frisos,
     faixas e detalhes do doador numa cor escolhida). Tons da cor principal seguem a peça sozinhos.
4. **Logos** (seção à esquerda): **Adicionar logo…** (PNG com transparência; de JPG com fundo liso o fundo sai sozinho).
   No editor: arrastar move, o canto redimensiona, a alça de cima gira (`Shift`: de 15 em 15°), setas empurram
   (`Shift` ×10), `Delete` tira. Nas costas da camisa o logo gira 180° sozinho (as costas estão de cabeça para baixo na
   textura). Logos da foto podem trocar o recorte: **por cor** (só o que destoa), **em bloco** (a forma preenchida, bom
   para escudos) ou **retângulo**.
   - **Escudo** e **marca** vão em arquivos à parte (`crest_…`, `brand_…`, 256×256) que o jogo cola na caixa do hotspot
     (`team`, `brand`); a caixa pode ser movida e redimensionada (a proporção é a do doador). No calção vão o mesmo escudo e
     a mesma marca, na caixa do calção.
5. **Time** (seção à esquerda): nome, **teamid** (o do banco), uniforme (casa, fora, goleiro, terceiro, quarto) e variação.
6. **Exportar kit** (`Ctrl+E`): escolha a pasta de saída. Dentro dela fica a estrutura do jogo e o
   `relatorio_criador_kits.txt`. **Mapas de tecido**: do doador (normal, coeff, taa e trama copiados) ou **genéricos**
   (coeff e taa preenchidos com o valor mais comum do doador: tecido uniforme, sem as marcas dos patrocinadores dele).

`Ctrl+Z` / `Ctrl+Y` desfazem e refazem. O kit em andamento fica salvo sozinho (`cache/projeto.json`).

## Prévia 3D

A aba **3D** mostra a peça no corpo com a textura do editor. Ela precisa das malhas dos uniformes exportadas pelo FET do
FC 27 (FBX), que não vêm no Super Tool:

- `content/character/body/body_simhigh_0/jersey_0_round_short_noband_untucked_regular_male/jersey_0_0_0_0_1_0_0_mesh`
- `content/character/body/body_simhigh_0/shorts_regular_male/shorts_0_0_0_mesh`
- `content/character/body/body_simhigh_0/socks_regular_medium_male/sock_0_0_1_0_0_mesh`

Exporte as três e use `Arquivo › Importar malhas para o 3D…` (vão para `motor/referencia`). As golas são malhas diferentes
(27 no FC 27, escolhidas por `jerseycollargeometrytype` no `teamkits`: round = 0, vneck = 7, polo = 11…), todas com o mesmo
molde de textura.

Com as malhas, a ferramenta também fica mais precisa fora do 3D: as mangas e os punhos da camisa e o cano do meião saem das
ilhas da UV da malha (em vez do traçado), as listras ficam com a mesma largura no tecido na frente e nas costas e os aros
ficam na mesma altura do corpo, e os logos da foto são levados à textura pelo corpo em 3D (a frente do molde não é esticada
por igual). Sem as malhas vale o molde traçado.

## Como funciona

- **Molde**: os 132 kits de exemplo têm o mesmo molde e os mesmos tamanhos (camisa 2048×2048, calção 1024×512, meião
  512×256; normal/coeff/taa da camisa em 1024). As partes (frente, costas de cabeça para baixo, mangas curtas nos cantos de
  cima, mangas longas nas laterais, gola, braçadeira) foram traçadas pela média das bordas das texturas dos 132 kits
  (`motor/molde.py`). Na frente e nas costas, a direita da textura é o lado esquerdo de quem veste.
- **Recolorir**: as cores do doador são separadas em camadas (k-means em CIELAB). Cada pixel recebe a cor nova da sua
  camada mais a diferença que ele tinha para a cor da camada (sombras, costuras, trama), com transição suave entre camadas.
- **Foto**: recorte pelo fundo liso das bordas (ou transparência, ou GrabCut); caixa do tronco pelas larguras das linhas
  (a axila é onde a largura passa de 1,22× a do tronco); cores e padrão pelo tronco endireitado; logos = o que fica longe do
  segmento entre as duas cores principais (as misturas delas, como bordas de listras e trama, não contam), juntados por
  proximidade e mapeados da caixa do tronco para a frente do molde.

## Limitações

- Sem as malhas, o molde é o traçado das texturas: as divisas entre tronco e mangas podem errar alguns pixels perto da axila.
- As mangas longas (faixas laterais) continuam pelo traçado: a malha exportada é a de manga curta.
- Padrões que não são listras/faixas/metades (desenhos, degradês complexos) não são recriados da foto: escolha o mais
  parecido ou use um doador com desenho parecido (o desenho tom sobre tom dele é mantido).
- Logos pequenos na foto saem borrados; troque pelo arquivo original quando tiver. A foto só mostra a frente: costas,
  calção e meião saem das cores escolhidas.
- Ainda não testado no jogo.

## Técnico

A interface (`servidor.py`) roda no Python embutido do Super Tool; o motor (`motor/`: `kit.py`, `foto.py`, `molde.py`,
`cores.py`, com numpy, SciPy, Pillow e OpenCV) fica aberto num processo à parte (`motor/ponte.py servico`, um JSON por
linha). Se faltarem os pacotes, a ferramenta oferece o download (ou use a página **Componentes** do Super Tool). O leitor de
FBX da prévia 3D é o do Conversor de Faces.
