# Criador de Minifaces — versão 1.2

Transforma fotos de jogadores em minifaces do jogo: **p&lt;ID&gt;.png**, 180×180, fundo transparente, com o rosto no
mesmo lugar e tamanho das minifaces originais (medido na p158023 do jogo).

## Usar

1. **Fotos**: `Arquivo › Adicionar fotos…` (`Ctrl+O`), `Adicionar pasta…` ou arrastar as imagens para a janela. Qualquer
   tamanho; PNG recortado (transparente), fundo de cor neutra ou fundo qualquer.
2. **Time**: no topo da lista, escolha o time das fotos (precisa do banco importado em **Dados do jogo**, no Super Tool).
   Cada foto é ligada ao jogador do elenco pelo nome do arquivo — `alex santana.png` → Alex Santana, `GABRIEL-BARBOSA-5-569x1536.png`
   → Gabriel Barbosa, `gh.png` → iniciais. A lista mostra o `p<ID>` e a semelhança; o painel da direita troca o jogador
   (lista do elenco) ou aceita um ID digitado.
3. **Conferir cada foto** (clique na lista):
   - à esquerda a foto original com o **quadro azul** (o que vira a miniface) e o rosto encontrado (laranja);
   - arraste o quadro para mover e use a **roda do mouse** para aproximar; ou use os controles de zoom/posição do painel;
   - **Marcar o rosto** (`R`): arraste um quadrado sobre o rosto quando a detecção errar;
   - **Pincel** verde (`B`, manter) e vermelho (`E`, apagar) para corrigir a separação do fundo; `Ctrl+Z` desfaz o traço;
   - à direita a prévia ampliada; **Comparar** (`C`) sobrepõe uma miniface do jogo para conferir o enquadramento.
4. **Saída**: escolha a pasta e clique **Exportar** (`Ctrl+E`). Fotos sem jogador ligado são puladas (ou exportadas com o
   nome do arquivo, se você escolher). O tamanho padrão é o do jogo (180).

## Fotos do Criador de Ligas e Times (novo na 1.2)

No **Criador de Ligas e Times**, depois de gravar um banco, **Fotos → Criador de Minifaces** (ou a opção "Mandar as
fotos ao Criador de Minifaces" na geração) manda as fotos dos jogadores novos para cá — o Super Tool abre esta ferramenta
sozinho. Elas entram na lista **já ligadas aos IDs novos** (os jogadores ainda não estão no banco importado, então não
precisa escolher time): confira o enquadramento e exporte. A fila fica em `dados\minifaces_fila.json` até esta
ferramenta abrir; fotos genéricas da API ("sem foto") não são mandadas.

## Fundo

- **Automático**: usa a transparência da foto quando existe; senão separa o jogador do fundo.
- **Transparência**: usa o canal alfa e limpa o halo semitransparente que alguns recortes trazem (sai pela cor do halo,
  para não comer o cabelo).
- **Remover fundo**: GrabCut do OpenCV guiado pelo rosto, pela cor do fundo (fundo neutro) e pelos traços do pincel.
- **Manter tudo**: não mexe no fundo.
- **Limpeza**: quanto do contorno semitransparente sai.

## Técnico

Interface e processamento rodam no Python embutido do Super Tool (`runtime\python`); o processamento usa OpenCV, Pillow e
numpy (a ferramenta oferece o download se faltarem, ≈ 57 MB uma vez só) e é aberto uma vez
como processo de trabalho (`motor/minifaces.py`). Rosto: detectores Haar do OpenCV (de frente; de perfil, nos dois lados;
e, sem rosto, estimativa pela silhueta). Testado com 65 fotos de jogadores do Corinthians e do Santos: todas
enquadradas, 59 ligadas sozinhas ao elenco do banco BRFP 26.
