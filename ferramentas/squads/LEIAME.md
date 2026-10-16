# Atualizador de Squads — versão 1.0

Quando a EA solta uma atualização de elencos, o squad do mod fica velho. O Atualizador pega o **squad oficial mais
recente da EA** e coloca nele o que o **mod** acrescentou, sem jogadores duplicados. Os squads de entrada nunca são
alterados: sai um arquivo novo.

## Como usar

1. **Squad da EA (mais recente)**: no jogo, baixe a atualização de elencos e salve (o arquivo novo é o `Squads<data>`
   mais novo de `%LOCALAPPDATA%\EA SPORTS FC 27\settings`).
2. **Squad do mod**: o squad do BRFP (ex.: `SquadsBRFP`).
3. Opcional: **squad em que o mod foi feito** (o squad da EA que o mod usou de ponto de partida). Com ele a ferramenta
   sabe com certeza o que o mod criou; sem ele, conta como criado pelo mod o jogador com nome editado no mod.
4. **Analisar**: mostra os times brasileiros do mod (marcados; dá para desmarcar), os que já existem na EA e os times que
   só existem no mod.
5. **Gerar squad atualizado**: escolha onde gravar (o nome sugerido é `Squads<data e hora>`, na pasta do squad da EA,
   para o jogo listar). No fim o arquivo é relido e conferido, e o relatório completo fica em `squads\saida`.

Para achar o mesmo jogador com IDs diferentes a ferramenta precisa dos nomes dos jogadores da EA, que ficam no banco do
jogo (tabela `playernames`): ela usa o banco do FC 27 importado em **Dados do jogo** ou, se não houver, o do
**RDBM 26 · Add-on FC 27**; dá para escolher outro `fifa_ng_db.db` no painel da esquerda.

## Regras da mescla

- **Base**: o squad da EA. Tudo que não está abaixo fica como a EA mandou (times, jogadores, escalações e competições
  de fora do Brasil, ligas que a EA já tem, estádios, uniformes de competição etc.).
- **Times brasileiros** (times das ligas do Brasil no mod — país 54, sem as seleções): vêm inteiros do mod — o registro do
  time, a liga, uniformes, estádio, nome do estádio, técnico, formação, tática, escalação, cobradores, rivais,
  patrocínios e o elenco. Os jogadores que a EA tinha nesses times saem (genéricos e reais); quem também estava numa
  seleção vai para os **Sem contrato** em vez de ser excluído.
- **Times que só existem no mod** entram como estão no mod, com elenco e escalação.
- **Ligas** do Brasil e ligas que só os times do mod usam ficam com os dados do mod; **competições**, **árbitros**,
  **imagens** e **patrocinadores** que só existem no mod entram.
- **Jogadores duplicados**: o mesmo jogador nos dois squads vira um só, sempre com o **ID da EA**.
  - Mesmo ID: é o mesmo jogador se o nome bate (basta o sobrenome) ou se nascimento e nacionalidade batem.
  - IDs diferentes: nascimento até 1 dia de diferença, mesma nacionalidade (ou mesmo nome comum) e nome parecido — o
    mesmo sobrenome com o primeiro nome parecido, ou o nome completo quase igual. Gêmeos (Anton e Aleksey Miranchuk)
    não passam.
  - Se no mod ele está num time brasileiro, ficam os **dados do mod** e ele sai do clube que tinha na EA; senão ficam os
    **dados da EA** (e o vínculo com o clube novo do mod só é usado se ele não tiver clube na EA).
  - O mesmo jogador duas vezes no mod também vira um só (fica o primeiro, no clube dele).
- **ID reusado**: se a EA passou a usar o ID de um jogador do mod para outro jogador, o do mod ganha um ID livre (os nomes,
  vínculos, escalações e empréstimos dele acompanham).
- **Jogadores criados pelo mod** em times da EA (nome editado no mod, ou fora do squad base) entram. Jogadores que a EA
  tirou depois que o mod foi feito **não** voltam.
- **Nomes**: os nomes extras do mod (`dcplayernames`) ganham IDs livres no squad da EA quando a EA usa o mesmo ID para
  outro nome; os nomes editados (`editedplayernames`) acompanham os jogadores.
- **Escalações**: os times cujo elenco mudou têm a escalação refeita — titulares que saíram são trocados pelo reserva que
  melhor joga na posição, quem entrou vai para o fim do banco e capitão/cobradores fora do elenco são escolhidos de novo
  pelos atributos. Times com o elenco igual ao de origem ficam como vieram (inclusive os times especiais da EA).
- **Técnicos** do mod com o ID de um técnico da EA ganham um ID novo.

## O arquivo gravado

O squad (`FBCHUNKS` + banco `DB`) é regravado com o mesmo cabeçalho do squad da EA: os tamanhos e o CRC-32 do arquivo e
os CRCs de cada tabela são recalculados. As tabelas que não mudam são copiadas byte a byte; as que mudam guardam a
capacidade (registros reservados) da EA com a mesma folga para o modo carreira. A leitura e a gravação estão em
`squad.py` (testado: o squad da EA relido e regravado sai idêntico, byte a byte) e a mescla em `mesclar.py`.

Teste sempre no jogo. Para uma segunda conferência, o **RDBM 26 · Add-on FC 27** tem *Verificar squad…*, que lê o
arquivo com a mesma biblioteca do RDBM e faz um teste de gravação.

## Versões

- **1.0** — primeira versão (FC 27; o formato do squad é o mesmo do FC 26).
