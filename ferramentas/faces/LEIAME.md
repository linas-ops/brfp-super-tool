# Conversor de Faces FC 26 ↔ FC 27 — versão 1.4

Converte o FBX da cabeça exportado pelo FIFA Editor Tool (FET) de um jogo para o outro:

- **FC 26 → FC 27**: gera o FBX no formato *morph head* do FC 27 (malha `basehead_0`, 4 LODs, head/eyes/teeth), pronto
  para importar no asset `headmorphpreset_<id>_0_0` do jogador. O FET do FC 27 só aceita a malha base com a mesma
  quantidade e ordem de vértices; o conversor deforma essa malha até ela ter o formato da face do FC 26.
- **FC 27 → FC 26**: gera o FBX no formato do FC 26 (3 LODs, head/eyes, dentes e boca dentro da `head_mat`), pronto para
  o `head_<id>_0_0_mesh`.

Esqueleto, pesos, LODs e nomes vêm de uma face real de cada jogo (Messi, pasta `motor/referencia` — não apague).

## Usar

1. **Adicionar faces**: `Arquivo › Adicionar faces (.fbx)…` (`Ctrl+O`), `Adicionar pasta…` (`Ctrl+Shift+O`, varre as
   subpastas — ex.: a pasta do *Batch Import Faces* do FET, uma subpasta por jogador) ou arrastar .fbx para a janela.
2. Cada face aparece na lista com o **jogo identificado** (FC 26 ou FC 27), o destino e o ID do jogador. O painel da
   direita mostra os detalhes (malha, LODs, vértices, materiais) e o caminho onde o resultado vai ser gravado.
3. **Saída e opções** (painel da direita):
   - **Pasta de saída**: em branco, cada face vai para `<pasta>_FC27` (ou `_FC26`) ao lado da pasta adicionada, ou para
     `Convertidos_FC27` ao lado do arquivo. Com uma pasta escolhida, as pastas adicionadas mantêm as subpastas dentro dela.
     Arquivos arrastados para a janela precisam de pasta de saída (o navegador não informa de onde vieram).
   - **Converter para**: o outro jogo (automático), tudo para FC 27 ou tudo para FC 26.
   - **Layout de textura da pele**: FC 26 (padrão — as texturas de face do FC 26 servem direto no FC 27) ou FC 27.
   - **Copiar os outros arquivos**: texturas, cabelo etc. das pastas adicionadas vão junto, sem mudança (mouthbag fica de
     fora no FC 27, que não usa).
   - **Sobrescrever existentes**.
4. **Converter** (`Ctrl+Enter`) converte a lista; o botão direito numa face converte só ela. Ao terminar, cada pasta de saída
   recebe o `relatorio_conversao_faces.txt`.
5. A **prévia 3D** mostra o LOD0 da face selecionada: **Entrada** e, depois de converter, **Resultado** (`Tab` alterna).
   Arraste para girar, roda do mouse para aproximar, `F` enquadra.

## O que o conversor faz com cada parte

- Pele: segue a superfície da face de entrada (precisão típica de 0,2 mm). Detalhes finos do Messi não passam adiante.
- Olhos: seguem os da entrada; se o facemaker trocou a malha dos olhos, cada olho é encaixado na esfera do olho da
  entrada (posição e tamanho) e girado pela UV da textura, para a íris olhar para o mesmo lado que na face original.
- Boca por dentro e dentes: acompanham a boca da entrada; cada dente se move sem deformar.
- Base do pescoço: fica fixa para encaixar no corpo do jogo de destino.
- LODs: todos gerados a partir do LOD0 da entrada.

## Limitações

- Só cabeças masculinas (`basehead_0`). As femininas do FC 27 usam outra malha base.
- Cabelo e mouthbag não são convertidos. Só FBX binário (o padrão do FET e do Blender).
- Ainda não testado no FET nem no jogo.

## Técnico

A interface (`servidor.py`) e a conversão (`motor/`, numpy e SciPy) rodam no Python embutido do Super Tool
(`runtime\python`); a conversão é chamada por `motor/ponte.py` (um evento JSON por linha). Se faltarem o numpy e o SciPy, a
ferramenta oferece o download (≈ 59 MB, uma vez só) — ou use a página **Componentes** do Super Tool. A linha de comando
continua disponível: arraste arquivos/pastas para `motor\Converter faces.bat`, ou
`runtime\python\python.exe ferramentas\faces\motor\converter_faces.py ENTRADA [...] [--saida PASTA] [--para fc27|fc26]
[--textura fc26|fc27] [--copiar-outros] [--sobrescrever]`.
O resultado da interface é idêntico, byte a byte, ao da linha de comando.
