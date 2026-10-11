# Editor de Compdata — versão 2.1

Editor visual para os arquivos de competição do FC. Trabalha no nível de
**competição → estágio → grupo**, nunca em linhas soltas.

## Abrir

Pelo **BRFP Super Tool** (troféu no trilho). Na primeira vez, **Arquivo › Abrir pasta…** (`Ctrl+O`) e escolha a pasta
que tem o `compobj.txt`; depois ele reabre a última pasta sozinho, e as recentes ficam na tela inicial e no menu
Arquivo. Sozinho: `python servidor.py ["C:\caminho\compdata"] [--porta 8770]`.

Sem dependências — só a biblioteca padrão do Python. Os nomes vêm, nesta ordem: do **idioma** e do **banco** importados
no Super Tool (Dados do jogo) — times (`TeamName_<id>` / `teams.teamname`), competições (`TrophyName_<id>`), estágios e
grupos (`FCE_Group_A` → "Grupo A"), países (`NationName_54` → "Brasil") — e da planilha `.xlsx` que estiver na pasta
(abas "Times…" e "Competições…"), lida sem precisar do openpyxl. O rodapé da árvore mostra de onde vieram os nomes.

## O problema que ele resolve

Em `compobj.txt` o **ID do nó é o número da linha**. Inserir, remover ou
reordenar qualquer coisa renumera tudo que vem depois — e aí cada referência a
nó espalhada pelos outros nove arquivos passa a apontar para o lugar errado.

O editor faz esse remapeamento sozinho, em `compobj` (coluna 0 e pai),
`compids`, `advancement` (colunas 0 e 2), `standings`, `schedule`, `objectives`,
`initteams`, `weather`, `tasks` (coluna 0 mais os campos de nó de cada verbo) e
`settings` (coluna 0 mais os valores das chaves que são ID de nó).

A distinção que mais importa: **nem todo número é um nó**. `info_special_team_id`,
`nation_id`, `match_stadium`, `info_league_promo`, `info_league_releg`,
`schedule_refcomp` e `asset_id` são IDs de banco ou de asset. Remapear
`info_special_team_id,1041` transformaria o Corinthians em outro clube. A lista
de chaves que realmente são nó está em `SETTING_NODE_KEYS` e a de campos de task
em `TASK_NODE_FIELDS`, ambas em `compdata.py`.

## Como funciona o salvamento

Toda edição altera **só a memória do servidor**. O disco só é tocado quando você
clica em **Salvar**, e o Salvar copia os dez arquivos para
`_backup_editor_AAAAMMDD_HHMMSS/` antes de gravar.

Gravar sem editar nada reproduz os arquivos byte a byte — ordem das linhas,
CRLF e quebra final inclusive.

## O que dá para fazer

| Onde | O quê |
|---|---|
| Árvore | Navegar, buscar por nome ou ID, redimensionar |
| Geral | Renomear sigla e string de tradução |
| Ajustes | Editar as linhas do `settings.txt`, com combo nos campos de vocabulário fechado |
| Vagas | Definir o tamanho do grupo; mostra jogos por time, total e rodadas |
| Times | Montar a lista `info_special_team_id` buscando por nome |
| Calendário | Editar dias, rodadas e limites de jogos; confere o total esperado por rodada |
| Avanços | Ligar grupos entre si (posição 0 = sorteio); mostra as duas pontas |
| Tasks | Editar os verbos de preenchimento com combo |
| Estágios/Grupos | Criar, excluir e reordenar (↑ ↓) |
| Confederações/Países | Criar dentro do Mundo ou de uma confederação |
| Copiar/Colar | Duplicar um nó com tudo abaixo dele |
| Abrir pasta… | Trocar de compdata sem reiniciar (recentes na tela inicial) |
| Assistente | Criar uma competição inteira: setup, grupos e mata-mata já ligados |

### Copiar e colar

Copia o nó e toda a subárvore, junto com `settings`, `standings`, `schedule`,
`advancement`, `tasks`, `objectives` e `initteams`. As referências internas
(um avanço de um grupo para outro dentro do que foi copiado, uma task apontando
para um grupo de dentro) são reapontadas para a cópia. As externas — um avanço
vindo de fora — não são duplicadas, senão a mesma vaga seria preenchida duas
vezes.

Colar respeita a hierarquia: estágio só entra em competição, grupo só em
estágio (ou em competição especial), país em confederação. Fora disso o editor
recusa e diz o porquê.

Excluir mostra antes quantas linhas cada arquivo vai perder. Tudo tem desfazer
(Ctrl+Z) — e o assistente desfaz de uma vez só, não nó por nó.

## Validação

A barra de baixo mostra a contagem de linhas de cada arquivo com a diferença
desde que você abriu, e um selo com os problemas encontrados. Clicando no selo
sai a lista, e cada item leva direto ao nó.

O validador confere hierarquia, posições de `standings` em sequência, avanços
apontando para grupos que existem e com vaga válida, vaga preenchida duas vezes,
`schedule` com mínimo maior que máximo, task pedindo mais times do que há na
lista, e referências para nós inexistentes.

## Atalhos

`Ctrl+S` salvar · `Ctrl+O` abrir pasta · `Ctrl+Z` desfazer · `Ctrl+Shift+Z` refazer · `Ctrl+C`/`Ctrl+V` copiar e colar nó ·
`Alt+↑`/`Alt+↓` mover entre irmãos · `Delete` excluir · `/` buscar · setas navegam na árvore · `F1` lista de atalhos

## Arquivos

```
compdata/
  compdata.py      modelo, leitura/escrita, renumeração e validação (funciona sozinho, dá para importar em scripts)
  servidor.py      servidor HTTP e API JSON (base comum do BRFP Super Tool)
  web/             interface (index.html, app.css, app.js) — estilo e componentes vêm de comum/
```

## Versões

- **2.1** — nomes de times, competições, estágios, grupos e países vindos do banco e do idioma importados no Super Tool.
- **2.0** — interface no padrão do BRFP Super Tool (menus, árvore, avisos e diálogos do Editor de Estádios), abre sem
  pasta e lembra as recentes, lê a planilha .xlsx sem openpyxl, validação ~70× mais rápida (mesmo resultado).
- **1.0** — editor com renumeração automática, copiar/colar de subárvores, assistente de competição e validação.
