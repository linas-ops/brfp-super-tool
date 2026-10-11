# Conversor de Tabelas — versão 1.1

Converte tabelas do banco do jogo (fifa_ng_db) entre versões: **FIFA 16, 21, 22, 23, FC 24, 26 e 27**, em qualquer
direção.

## Usar

1. **Origem** (painel da direita): por padrão, o banco importado no Super Tool (**Dados do jogo**). Também dá para usar outro
   `.db` (com o meta ao lado) ou uma pasta de tabelas `.txt` só aqui.
2. **Destino (tabelas finais)**: o banco do jogo para onde as tabelas vão — ex.: o `fifa_ng_db.db` do FC 27. Ele dá as
   colunas finais, as faixas do meta, os valores mais comuns e as linhas para mesclar. Uma pasta de tabelas, só o meta
   (`.xml`) ou o **esquema guardado** de uma versão (lista no painel; o Super Tool guarda o meta de cada versão) também
   servem — sem as linhas do destino, a coluna nova fica com o padrão do meta. Um `.db` sem o meta ao lado também abre (com o
   meta guardado da versão reconhecida).
3. **Tabelas**: marque à esquerda as que vão ser convertidas (busca e filtro "nos dois jogos"/"só na origem"). Clique numa
   tabela para ver o plano:
   - **Tabela de destino**: normalmente a mesma; troque se ela mudou de nome entre os jogos;
   - **Colunas**: de onde vem cada coluna final — a coluna da origem, o valor mais comum no destino (padrão para colunas
     novas) ou um valor fixo; colunas que o destino não tem são descartadas;
   - **Prévia** das primeiras linhas como vão ficar.
4. **Saída**: pasta, **Só a origem** (a tabela final tem só as linhas convertidas) ou **Mesclar com o destino** (linhas do
   destino + as da origem; na mesma chave, ex. `playerid`, a da origem substitui), formato dos `.txt` (UTF-16 como o
   RDBM/DB Master exportam, ou UTF-8) e, com um destino `.db`, **Gravar também um .db novo** (cópia do banco de destino com
   as tabelas convertidas no lugar). **Converter** (`Ctrl+Enter`) grava tudo e o `relatorio_conversao_tabelas.txt`.

## Regras

- Colunas iguais: copiadas; colunas novas: valor mais comum do destino (ou o que você escolher).
- Inteiros fora da faixa do meta do destino: ajustados para a borda (contados no relatório); textos maiores que o campo: cortados.
- **Para o FC 27** (de qualquer versão): tom de pele ×10 (`players/manager/referee.skintonecode`,
  `teams/competition.crowdskintonecode`: 1..10 → 10..100; fora da escala → valor mais comum). **Do FC 27**: tom de pele ÷10.
- **FIFA 21 … FC 24 → FIFA 16, FC 26 ou FC 27**: `skintypecode` acima de 7 → 0 (nesses jogos ele vai até ~151).
- **FC 26 → FC 27**: `facepsdlayer0/1` 3 ou 4 → 0 (as regras do port BRFP 26 → FC 27).
- **Colunas renomeadas**: `marking` (até o FIFA 22) ↔ `defensiveawareness` (FIFA 23 em diante).
- **Colunas de resumo** (`pacdiv`, `shohan`, `paskic`, `driref`, `defspe`, `phypos`, FIFA 22 em diante): calculadas pelos
  atributos quando a origem não tem (a mesma conta do jogo: iguais aos do banco em 100% dos jogadores para ritmo,
  finalização, passe e físico, e a ±1 em 93–99% para drible e defesa).

## Limitações

- O `.db` novo troca tabelas inteiras; tabelas sem texto saem byte a byte iguais às do jogo e as de texto comprimido
  (Huffman, ex. `playernames`) ganham uma árvore nova (o conteúdo lido de volta é idêntico; verificado em todas as tabelas
  dos bancos do FIFA 16 ao FC 27).
- Testado: BRFP 26 → FC 27 (players, teams, teamplayerlinks, leagues, leagueteamlinks, playernames), substituir e mesclar;
  players FIFA 22 → FC 27, FIFA 16 → FC 26 e FC 27 → FIFA 23. Ainda não testado no jogo.
