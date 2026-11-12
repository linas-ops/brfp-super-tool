# Criador de Minifaces — versão 1.4

Transforma fotos de jogadores em minifaces do jogo: **p&lt;ID&gt;.png**, 180×180, fundo transparente, com o rosto no
mesmo lugar e tamanho das minifaces do BRFP e do jogo.

## Usar

1. **Fotos**: `Arquivo › Adicionar fotos…` (`Ctrl+O`), `Adicionar pasta…` ou arrastar as imagens para a janela. Qualquer
   tamanho; PNG recortado (transparente), fundo de cor neutra ou fundo qualquer.
2. **Time**: no topo da lista, escolha o time das fotos (precisa do banco importado em **Dados do jogo**, no Super Tool).
   Cada foto é ligada ao jogador do elenco pelo nome do arquivo — `alex santana.png` → Alex Santana, `GABRIEL-BARBOSA-5-569x1536.png`
   → Gabriel Barbosa, `gh.png` → iniciais. A lista mostra o `p<ID>` e a semelhança; o painel da direita troca o jogador
   (lista do elenco) ou aceita um ID digitado.
3. **Conferir cada foto** (clique na lista):
   - à esquerda a foto original com o **quadro azul** (o que vira a miniface; fica girado quando a cabeça é endireitada),
     o rosto encontrado (laranja) e os 5 pontos que guiam o enquadramento (olhos, nariz e cantos da boca);
   - arraste o quadro para mover e use a **roda do mouse** para aproximar; ou use os controles de zoom/posição do painel;
   - **Endireitar a cabeça** (ligado por padrão): gira a foto para deixar os olhos na horizontal, até 20°;
   - **Marcar o rosto** (`R`): arraste um quadrado sobre o rosto quando a detecção errar (os pontos são procurados de novo
     dentro dele);
   - **Pincel** verde (`B`, manter) e vermelho (`E`, apagar) para corrigir a separação do fundo; `Ctrl+Z` desfaz o traço;
   - à direita a prévia ampliada; **Comparar** (`C`) sobrepõe uma miniface do jogo para conferir o enquadramento.
4. **Saída**: escolha a pasta e clique **Exportar** (`Ctrl+E`). Fotos sem jogador ligado são puladas (ou exportadas com o
   nome do arquivo, se você escolher). O tamanho padrão é o do jogo (180).

## Enquadramento (novo na 1.4)

O detector **YuNet** do OpenCV (`motor/modelos/`, 230 KB, licença MIT) acha o rosto e 5 pontos. O meio dos olhos vai
sempre para o mesmo lugar do quadro; o tamanho sai da distância entre os olhos (corrigida quando o rosto está virado,
pela posição do nariz) e da distância dos olhos à boca; a inclinação sai das pupilas. As medidas-alvo são a mediana de
600 minifaces do BRFP 24 e batem com a miniface original do jogo (p158023).

Nas 65 fotos de teste (Corinthians e Santos), medindo as saídas com os 478 pontos do MediaPipe: a variação do tamanho do
rosto caiu de 8,4% para 4,1% (a das minifaces do BRFP é 7%), a dos olhos de 2,3 para 1,7 px, a do queixo de 6,7 para
2,7 px, e a inclinação que sobra caiu de até 10° para até 2,3°. Sem os pontos (o YuNet não achou rosto), valem os
detectores antigos: Haar de frente, de perfil e, por último, a silhueta.

## Fundo

- **Automático**: usa a transparência da foto quando existe; senão separa o jogador do fundo.
- **Transparência**: usa o canal alfa e limpa o halo semitransparente que alguns recortes trazem (sai pela cor do halo,
  para não comer o cabelo).
- **Remover fundo**: GrabCut do OpenCV guiado pelo rosto, pela cor do fundo (fundo neutro) e pelos traços do pincel.
- **remove.bg** (novo na 1.4): tira o fundo pelo [remove.bg](https://www.remove.bg/api), com a chave da sua conta.
- **Manter tudo**: não mexe no fundo.
- **Limpeza**: quanto do contorno semitransparente sai.
- **Usar em todas**: põe o modo de fundo da foto aberta em todas as fotos da lista e nas que entrarem depois.

### remove.bg

1. Crie uma conta no remove.bg, abra **API Keys** (botão "Criar a chave no site" na ferramenta) e crie uma chave.
2. No Criador de Minifaces, `Arquivo › Chave do remove.bg…` (ou clique em **remove.bg** no Fundo) e cole a chave. Ela é
   conferida no remove.bg e fica só neste computador (`preferencias.json` da ferramenta, fora do git e do pacote).
3. Escolha **remove.bg** no Fundo (numa foto ou em todas). O painel mostra as chamadas grátis e os créditos da conta.

Cada foto vai ao remove.bg **uma vez só**: a ferramenta manda só a região da cabeça e dos ombros, reduzida para até
0,25 megapixel (tamanho "preview", o que a miniface de 180 px precisa), e guarda o recorte em `cache\removebg\`. Zoom,
posição, limpeza, pincel e até fechar e abrir a ferramenta não gastam outra chamada; só um rosto marcado à mão bem longe
do detectado pede um recorte novo. Para minifaces maiores que 180 px, a região vai em resolução maior (tamanho "auto",
que pode gastar crédito). Chave recusada ou conta sem saldo: a ferramenta para de chamar e avisa no painel; troque a chave
ou clique **Atualizar o saldo** depois de recarregar a conta.

O remove.bg avisa que, a partir de 1º/12/2026, a remoção de fundo passa para a Leonardo.Ai (também da Canva), com a
"mesma integração". Se o endereço da API mudar, ele fica num lugar só: `URL` em `removebg.py`.

## Fotos do Criador de Ligas e Times

No **Criador de Ligas e Times**, depois de gravar um banco, **Fotos → Criador de Minifaces** (ou a opção "Mandar as
fotos ao Criador de Minifaces" na geração) manda as fotos dos jogadores novos para cá — o Super Tool abre esta ferramenta
sozinho. Elas entram na lista **já ligadas aos IDs novos** (os jogadores ainda não estão no banco importado, então não
precisa escolher time): confira o enquadramento e exporte. A fila fica em `dados\minifaces_fila.json` até esta
ferramenta abrir; fotos genéricas da API ("sem foto") não são mandadas.

## Técnico

Interface e processamento rodam no Python embutido do Super Tool (`runtime\python`); o processamento usa OpenCV, Pillow e
numpy (a ferramenta oferece o download se faltarem, ≈ 57 MB uma vez só) e é aberto uma vez
como processo de trabalho (`motor/minifaces.py`). O cliente do remove.bg (`removebg.py`) roda no servidor da interface,
só com a biblioteca padrão. Testado com 65 fotos de jogadores do Corinthians e do Santos: todas enquadradas pelos 5
pontos, 59 ligadas sozinhas ao elenco do banco BRFP 26.
