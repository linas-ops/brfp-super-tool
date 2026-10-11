# Editor de Banco — versão 1.1

Edita o banco do jogo importado em **Dados do jogo** (Super Tool) — qualquer versão: FIFA 16, 21, 22, 23, FC 24, 26 e 27.
O banco original **nunca é alterado**: as mudanças ficam numa edição (salva sozinha, com desfazer) e **Gravar banco**
escreve um banco novo numa pasta escolhida.

## O que dá para editar

**Times** (aba Times, à esquerda: país › liga › time)

- **Elenco**: número, posição, geral, potencial, idade (muda o ano de nascimento) e nação direto na tabela (Enter ou
  sair do campo grava; quem usava o número fica com o antigo). Mudar o **geral** leva junto os atributos que pesam na
  nota da posição (+N no geral = +N neles; o potencial sobe se ficar abaixo). Clique no nome para abrir o jogador; **Transferir**, **Emprestar**
  (com o fim do empréstimo), **Encerrar empréstimo** (volta ao dono) e **Liberar** (vai para o time dos livres do mesmo
  gênero: NG - FA ou NG - FA Women); **Contratar jogador…** (busca qualquer jogador do banco) e **Criar jogador** (começa
  como cópia do jogador de nota mais baixa do elenco, com ID e nome novos).
- **Escalação**: o campo com as 11 vagas da formação — escolha o jogador de cada vaga (quem sai vai para o lugar de quem
  entrou; vermelho = fora da posição dele); banco e reservas em ordem (os 12 primeiros vão para o banco); capitão,
  pênaltis, faltas, escanteios e tiro de meta; **Trocar** a formação (qualquer uma do banco); **Escalar sozinho** (os 11
  melhores para as vagas, cobradores pelos atributos); tática (saída de bola e linha defensiva).
- **Dados do clube**: cores (seletor de cor), fundação, rival, prestígio, finanças, capacidade do estádio e todos os outros
  campos de `teams`. **Renomear** muda `teamname` e o idioma (TeamName, abreviações e sigla). **Mudar de liga**: no Resto do
  Mundo (76 / 2226) o time entra com a nação da liga de onde saiu (`teamnationlinks`).
- **Técnico**: o da tabela `manager`.

**Jogadores** (aba Jogadores: busca pelo nome ou ID; na aba Times a busca também aceita o ID do time ou da liga):
nomes (`editedplayernames`), dados (mudar o geral ajusta na hora os atributos da posição, marcados em azul até gravar), posições (até 7), habilidades,
atributos agrupados, contrato, aparência e todos os outros campos; transferir, emprestar, liberar, excluir.

**Mais**: técnicos e árbitros (lista com busca, formulário, nova pessoa) e **qualquer tabela** do banco numa grade —
busca num campo ou em todos, dois cliques numa célula para editar, duplicar e tirar linhas. Células mudadas ficam em azul,
linhas novas em verde.

Datas aparecem como data (o banco guarda dias desde 14/10/1582); nacionalidades, posições, pé e empenho como listas;
campos 0/1 como caixa. Todo valor é conferido pela faixa do meta antes de entrar na edição.

## Erros (verificação)

A aba **Erros** confere o banco inteiro, já com as mudanças da edição:

| Erro | Correção |
|---|---|
| vínculo (`teamplayerlinks`) com jogador ou time que não existe | tirar o vínculo |
| jogador duas vezes no mesmo elenco | tirar a cópia |
| jogador em dois clubes | abrir o jogador (os times especiais, como o MLS All Stars, ficam de fora) |
| jogadores sem time nenhum | mandar para Sem Contrato |
| número de camisa repetido | dar números livres |
| escalação padrão, mentalidade ou capitão/cobradores com jogador fora do elenco | refazer a escalação |
| time com menos de 11 (ou mais de 52), sem formação ou sem escalação | — |
| empréstimo de jogador/time que não existe, ou pelo próprio clube | tirar o empréstimo |
| linhas de tabelas ligadas a um time que não existe (estádio, nação, técnico, uniformes…) | tirar a linha |
| liga com time que não existe, time sem liga | tirar o vínculo |
| chave repetida (playerid, teamid, leagueid) | — |
| valores fora da faixa do meta | levar para a borda da faixa |

**Corrigir todos** aplica a correção em todos os problemas de um tipo; cada correção entra no histórico (dá para desfazer).

## Edição, desfazer e gravar

- Cada operação (transferência, escalação, mudança de campo…) entra no **Histórico** e pode ser desfeita (Ctrl+Z ou o botão
  no topo). A edição fica em `ferramentas\banco\cache\edicao_<banco>.json` e volta quando você abre a ferramenta de novo —
  a mesma edição vale enquanto o banco importado for o mesmo.
- **Gravar banco** (Ctrl+S) pede a pasta e escreve: `db\fifa_ng_db.db` + meta (cópia do importado com as mudanças),
  `tabelas\<mexidas>.txt` (UTF-16, para o RDBM/DB Master), `idioma\` (os textos novos e, se o idioma importado for .txt,
  os LanguageStrings completos) e `relatorio.txt`. Antes, mostra quantos erros a verificação acha. Depois de gravar, a
  edição continua aberta.
- Tabelas com textos comprimidos (`playernames`, `commentarynames`…) também são gravadas no .db (a árvore de Huffman é
  refeita: o conteúdo lido de volta é idêntico).
- **Descartar tudo** volta a edição ao banco importado.

## Limitações

- **Ainda não testado no jogo.** Testado: FC 27 — transferência, empréstimo e volta, liberar (masculino e feminino),
  números, formação 4-4-2, escalação à mão com capitão, criar e excluir jogador, renomear, desfazer, recarregar a edição,
  gravar e ler de volta; regravação de todas as tabelas dos bancos do FIFA 16 ao FC 27 lida de volta igual.
- Criar jogador copia a aparência de um jogador do elenco (a cabeça real não vem junto).
- Liga nova ou time novo para o modo carreira também precisam do compdata (Editor de Compdata).

**Voltar**: o botão Voltar (no topo), Alt+←, Backspace (fora de um campo) ou o botão de voltar do mouse levam para a
tela anterior (com a aba do time em que você estava); se a tela tiver mudanças não gravadas, ele pergunta antes.
