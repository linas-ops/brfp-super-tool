# Criador de Ligas e Times — versão 2.3

Cria ligas, times, seleções e jogadores no banco do jogo (FC 26 / FC 27) a partir da **API-Football** (api-sports.io) —
mais de 1.200 ligas e copas no mundo; só no Brasil, 109 competições — ou da **Transfermarkt** (pela transfermarkt-api) e
**atualiza o banco que você já tem**: quem subiu ou caiu de divisão, transferências, empréstimos, saídas, números de
camisa e, se quiser, um ajuste pequeno de nota.

## Fontes: API-Football ou Transfermarkt

A fonte se escolhe no topo da aba **API** (e no menu *API › Fonte*); o resto da ferramenta funciona igual com as duas, e
um mesmo projeto pode ter times de uma e de outra (os da Transfermarkt têm o selo **TM**).

| | API-Football | Transfermarkt |
|---|---|---|
| Conta / chave | precisa (grátis em dashboard.api-football.com) | não precisa |
| Limite | 100 chamadas/dia no grátis | nenhum no servidor local; a instância pública aceita ≈1 pedido a cada 1,6 s |
| Temporada atual | só no plano pago | sim (elencos de hoje, promovidos, transferências) |
| Nota do jogador | nota média da API + minutos + idade (erro médio ≈ 2,5) | **valor de mercado** + idade (erro médio ≈ 1,7) |
| Posição e pé | posição pelas escalações/estatísticas; pé vem do modelo | posição exata de cada jogador, posições secundárias e pé (ambos → perna ruim 4+) |
| Data de nascimento nos elencos | não (casamento por nome + idade) | sim (casamento exato) |
| Estádio, cores, técnico | estádio e técnico; cores pelas escalações | estádio, cores do clube, técnico |
| Futebol feminino | sim | **não** |
| Notas por jogo, peso | sim / não | não / não (peso vem do modelo) |

**Servidor da Transfermarkt** (painel da direita, seção *Transfermarkt*):

- **Automático** (padrão): usa o servidor local se estiver instalado; senão, a instância pública.
- **Local**: a [transfermarkt-api](https://github.com/felipeall/transfermarkt-api) (felipeall, licença MIT) roda no próprio
  computador, no Python do Super Tool. Instale em **Instalar o servidor local…** (ou em *Super Tool › Componentes*,
  grupo *Transfermarkt API*): ≈4 MB, a versão 4.2.0 do projeto + FastAPI, uvicorn, httpx, pydantic e mais 20 bibliotecas,
  todas com versão fixa e conferidas pelo SHA-256. Ele liga sozinho quando o Criador precisa (porta 8790) e desliga junto.
- **Pública**: `transfermarkt-api.fly.dev`, mantida pelo autor do projeto **só para testes** — lenta e às vezes recusa
  pedidos (o Criador espera e tenta de novo).
- **Outro**: o endereço de um servidor seu (ex.: o Docker da transfermarkt-api em outro computador).
- **Testar** liga o servidor (se for o local) e faz um pedido de teste.

Tudo o que vem da Transfermarkt fica em `dados\tm_cache` (temporadas encerradas e jogos valem para sempre; elencos da
temporada atual e transferências, 1 dia; perfis e valores de mercado, 7 dias).
Os dados são da **Transfermarkt** (transfermarkt.com): use para fins pessoais e respeite os termos do site.

## Antes de começar

1. **Banco do jogo**: importe em **Dados do jogo** (Super Tool). As notas são calibradas nele e cada time novo copia um
   time-modelo dele.
2. **Idioma** (opcional, recomendado): também em Dados do jogo — o idioma completo sai já mesclado com os nomes novos.
3. **internationals.txt** (para seleções novas): também em Dados do jogo. Dele vêm os mínimos e máximos de convocados por
   posição e a idade-limite; as seleções novas entram nele (a versão nova sai na pasta do banco gerado).
4. **Chave da API-Football** (só para essa fonte): crie a conta grátis em **dashboard.api-football.com** e cole a chave
   em *API › Colar a chave…*. Ela fica só neste computador (`dados\api_football.json`) e nunca vai no pacote para outro
   computador. A **Transfermarkt** não precisa de chave; para usá-la sem o limite da instância pública, instale o servidor
   local (veja acima).
5. **Aparência pelas fotos** (opcional): usa o OpenCV, que vem com os componentes do Criador de Minifaces
   (Super Tool › Componentes).

**Completar a API-Football com a Transfermarkt** (Geração, no painel da direita): ao coletar um time da API-Football, o
Criador procura o mesmo clube na Transfermarkt (2 pedidos: a busca e o elenco da temporada) e preenche o que a API não dá —
nascimento, pé, posição exata, altura e nacionalidades —, casando os jogadores por nome e idade. O que a API trouxe não
muda; o resumo ("N de M jogadores completados") aparece nos avisos do time.

**Projeto**: marque vários itens (caixa à esquerda de cada um) e **Tirar do projeto** tira todos de uma vez (também no
menu do botão direito).

## API-Football: plano grátis × pago

| | Grátis | Pro (US$ 19/mês) |
|---|---|---|
| Chamadas por dia | 100 (10 por minuto) | 7.500 |
| Estatísticas, listas de times e classificação | só das temporadas 2022–2024 | todas, inclusive a atual |
| Elenco atual e convocação (`players/squads`) | sim | sim |
| Jogadores por consulta | 60 (3 páginas) | todos |

Tudo o que é baixado fica em `dados\api_cache`: a mesma consulta não gasta outra chamada (temporadas encerradas valem para
sempre; elencos atuais, 1 dia). A barra embaixo mostra as chamadas que restam hoje. Escudos e fotos não gastam chamadas.

## Criar

1. **API** (aba à esquerda): escolha a fonte, o país e a competição (temporada: na API-Football, a mais recente liberada
   no plano; na Transfermarkt, a atual — dá para escolher qualquer uma).
   - Marque os times que quiser: **Liga com N marcados** cria uma liga nova só com eles; **N avulsos** põe cada um como
     time avulso; sem marcar nada, **Liga inteira**.
   - **Seleções**: país **Mundo** (*Internacional* na Transfermarkt) › uma competição de seleções (Copa do Mundo, Copa
     América, Eurocopa…) › marque as seleções. Na Transfermarkt também há o botão **Seleção: <país>** em cada país.
   - Na Transfermarkt, a lista de cada país vem de um catálogo com 1.496 competições (ligas primeiro, pelo valor de mercado;
     fases e categorias de base no fim). Não achou? Digite o nome e tecle **Enter** para buscar em toda a Transfermarkt.
2. **Projeto** (aba à esquerda). Para cada item, no painel da direita:
   - **Feminino**: detectado pelo nome ("Women", "W", "Feminino"…), dá para trocar. Jogadoras com aparência feminina
     (sempre de jogadoras genéricas do banco), times-modelo, ligas de destino e níveis de referência femininos.
   - **Nível**: média dos 14 jogadores mais fortes de um time típico. Vem da liga do banco de mesmo país, gênero e divisão;
     sem ela, da 1ª divisão do país menos 4,5 por divisão; sem liga do país, da seleção do país no banco menos a diferença
     típica entre seleção e liga (ex.: Brasileiro feminino ≈ 66,8). A classificação soma até ±3,5 em cada time.
     **Transfermarkt**: depois da coleta, o nível de cada time é a média das 14 maiores notas que o valor de mercado dá
     (bate com os níveis do banco a ±1); a liga fica com a média dos times. Mudar o nível à mão desloca as notas do elenco.
   - **Destino**: liga nova no banco ou uma liga que já existe; times avulsos sem liga do país vão para o Resto do Mundo
     (masculino 76, feminino 2226) já com a nação (teamnationlinks).
   - **Elenco** (*temporada* ou *atual*), **Escalações** (cada uma é 1 chamada: posição exata dos titulares, formação e
     cores dos uniformes), **ID do time**, **ID da liga** e **time-modelo** à mão.
   - **Formação e tática**: formação (a mais usada nas escalações ou qualquer uma do banco), linha defensiva (recuada,
     equilibrada, alta, agressiva) e saída de bola (passe curto, equilibrada, bola longa). No automático seguem a força do
     time na liga — no banco, os de cima usam passe curto e linha alta; os de baixo, bola longa e linha recuada.
   - **Estádio**: sempre um **genérico** do jogo, com a capacidade do estádio real (ou a típica do nível do time no banco,
     ajustada pelo país e menor no feminino). O nome do estádio real vai em `stadiumassignments` — o jogo mostra esse nome
     no genérico. Dá para trocar nome, capacidade e o genérico.
3. **Coletar** (topo) busca o que falta, mostrando antes quantas chamadas (pedidos, na Transfermarkt) vai gastar. Na
   Transfermarkt: elenco da temporada, perfil de cada jogador (valor de mercado, posições, nacionalidade), clube (estádio,
   cores, sigla), técnico, classificação e os últimos jogos (formação e titulares) — Palmeiras: ≈37 pedidos, ≈20 s pelo
   servidor local. *Estatísticas da temporada (Transfermarkt)*, em Geração, busca também jogos, minutos e gols de cada um
   (1 pedido por jogador; só refinam os atributos).
4. **Prévia** (clique no time): elenco gerado com **todas as colunas que vão para o jogo editáveis** — número, foto,
   posição, nota, potencial, nascimento, nacionalidade, altura, peso, pé, perna ruim, dribles e aparência. O **×** no começo
   da linha tira o jogador do elenco (ele não é criado; os tirados aparecem no fim da tabela, com o botão de pôr de volta —
   também na ficha, em *Tirar do elenco*). Clicar no nome (ou na foto) abre a
   **ficha**: nomes (comum, camisa, primeiro, sobrenome), playerid à mão, posições secundárias, capitão, tom de pele, cor
   do cabelo, barba e os 34 atributos. O que foi mudado fica em azul; *Voltar ao gerado* desfaz. Cartões do **técnico**
   (editável: nome, nascimento, nacionalidade, gênero, tom de pele), da tática, do estádio e dos uniformes.
   **Jogadores que já estão no banco**: cada jogador é procurado no banco carregado e ganha o selo **NO BANCO** (passe o
   mouse: nome, clube, ID e nota do jogador do banco). O **nome tem de bater** (todo o nome da fonte no do banco, ou o
   contrário; uma palavra comum como "Silva" ou "da" não basta) e o nascimento só confirma; uma nacionalidade diferente de
   todas as do jogador na fonte pesa contra. No banco BRFP 27 inteiro, os jogadores confundidos com outro nascido no mesmo
   dia caíram de 838 para 29 (2.3). *Usar o do banco* (em cada um, na ficha ou *Usar os do banco* para todos com nome e
   nascimento iguais) põe o jogador do banco no time novo em vez de criar outro igual: ele **é transferido** — sai do clube
   atual (e do Sem Contrato), que tem a escalação refeita — e mantém nota, atributos e aparência; só o número muda. Se um
   clube do banco ficar com menos de 11, ao Gerar ele é completado com jogadores sem contrato (veja abaixo).
   **Elenco com menos de 11** (a fonte trouxe poucos jogadores): a prévia oferece **Completar com jogadores sem contrato**
   (do time Sem Contrato — no feminino, das jogadoras sem clube —, com nota perto da média do elenco e a nação mais comum
   dele; primeiro o que falta para escalar: goleiro, defesa, meio e ataque; selo SEM CONTRATO) ou **Criar assim mesmo**
   (as vagas que faltam ficam vazias na escalação; o jogo pode travar quando esse time entrar em campo).
5. **Analisar as fotos** (botão na prévia): baixa as fotos e lê de cada jogador (e do técnico) o tom de pele, a cor e o
   tamanho do cabelo e se tem barba. A aparência passa a vir de um jogador genérico do banco parecido com a foto, com a
   pele, a cor do cabelo, o penteado e a barba da foto. Fotos genéricas da API ("sem foto") são ignoradas.
6. **Gerar banco** grava na pasta de saída tudo o que está no projeto e as mudanças marcadas em *Atualizar banco*.

## Seleções

- O elenco são jogadores **que já existem no banco**: cada convocado da API é procurado pelo nome e pela idade entre os
  jogadores da **mesma nacionalidade** (nunca ídolos da Liga Clássica). Faltando gente numa posição, entram os melhores da
  nação no banco até o **mínimo** de cada grupo do internationals (GK 3–5, LB 2–4, CB 6–8, RB 2–4, LM 2–4, CM 6–10,
  RM 2–4, ST 5–8, até 35 anos); acima do **máximo**, saem primeiro os completados. Os grupos aparecem em verde/vermelho.
- Convocados que não estão no banco: **Escolher no banco…** (casar à mão) ou marcar **quem criar** — um por um, ou todos
  com *Criar todos os convocados que não estão no banco* (com nota estimada); os desmarcados ficam fora. Os criados vão para
  o **clube deles, se o clube estiver no banco** (Transfermarkt: o clube do perfil do jogador; colete a seleção de novo para
  ter esse dado), senão para os Passes Livres (Sem Contrato).
  **Pôr jogador do banco…** inclui qualquer um; o **×** tira (os completados são trocados pelo próximo da posição). Número
  e capitão editáveis.
- **Seleção que já existe** (pela nação na liga de seleções): o elenco, a escalação, os cobradores e o técnico (se a API
  tiver outro) são substituídos; o resto do time fica.
- **Seleção nova**: copia uma seleção do banco da mesma confederação e nível parecido, entra na liga de seleções
  (78 / 2136 no feminino) com a nação e ganha uma linha no **internationals.txt** (nível pelo das seleções de força
  parecida, confederação da nação e os objetivos mais comuns desse nível).

## Atualizar banco

**Várias ligas de uma vez**: marque as ligas do banco à esquerda e clique **Casar todas** — cada uma é casada com a liga de
mesmo país e divisão na fonte, na temporada mais recente (que o plano libera, na API-Football). A página **Conferências**
mostra cada liga num painel que abre com os times casados (os menos parecidos primeiro, com o lápis para trocar), e
**Conferir N ligas** confere todas com as mesmas opções. Um time que saiu de uma liga e está na lista de outra conferida
junto (subiu da Série B para a Série A) vai para essa outra.

Quando dois times do banco têm nome parecido com o da fonte ("Botafogo FC" na Transfermarkt é o Botafogo-SP, não o do Rio;
"Grêmio Novorizontino"), o Criador **desempata pelo elenco**: compara o elenco atual da fonte com o de cada candidato no banco
(nascimentos na Transfermarkt, nomes na API-Football; 1 pedido a mais só nesses casos). Esses pares aparecem como
"% · elenco".

**Ligas sem país** (Resto do Mundo, ou uma Libertadores/Sul-Americana com clubes de vários países): não há uma liga
correspondente na fonte, então **Casar os N times** procura cada time do banco sozinho (1 pedido/chamada por time) pelo nome,
pela nação dele e pelas grafias em inglês ("Sparta Praga" → Sparta Prague); o que já foi casado antes vem do mapa. Depois a
conferência é igual, sem a lista de participantes. No Resto do Mundo do BRFP 27, 68 de 74 times foram achados.

**Sem par**: no lápis de um par, *Sem par (não está no banco)* põe o time da fonte na lista dos sem par com o nome e o escudo
(antes ficava só o id) e tira o par guardado no mapa.

**Seleções**: as ligas de seleções do banco (masculina e feminina) aparecem no alto da lista. Marque as seleções,
**Procurar** na fonte (Transfermarkt: rápido, só masculino; API-Football: 1 chamada por seleção, depois cache) e **Pôr no
projeto**: elas entram como seleções que já existem — ao Gerar, a convocação atual (casada com o banco e completada até o
mínimo de cada posição), a escalação, os cobradores e o técnico são trocados. Colete na aba Projeto.

1. Aba **Atualizar banco** › escolha uma liga do banco e a fonte. A liga correspondente (mesmo país, mesma divisão) vem
   sugerida; escolha a temporada e **Casar os times** (1 chamada). Na Transfermarkt dá para buscar outra competição pelo
   nome, e a temporada atual está liberada.
2. Confira os pares (os menos parecidos aparecem primeiro; o lápis troca — a troca fica guardada no mapa e vale nas
   próximas vezes). Times da API que não estão no banco: **Criar os que faltam** põe no projeto, já nessa liga.
3. Marque o que conferir e quais times terão o elenco conferido (1 chamada por time; +1 com empréstimos; até +3 com as
   notas) e **Conferir**:
   - **Participantes**: times que estão em outra liga no banco mudam para esta; os que não estão na lista da fonte vão para a
     divisão de baixo do mesmo país — e, se o banco não tiver divisão abaixo, para o **Resto do Mundo** (76, ou 2226 no
     feminino), com a nação do time em `teamnationlinks`;
   - **Transferências** e **empréstimos** (com o clube dono e o fim estimado do empréstimo em `playerloans`), **fim de
     empréstimo**, **números de camisa**;
   - **Saídas**: quem não está mais no elenco. Com *Saídas para o clube novo* (ligado por padrão), cada um é procurado na
     fonte — na Transfermarkt, pela busca de jogadores (casado por nome, idade e nacionalidade e **confirmado pela data de
     nascimento** no perfil: ≈2 pedidos por jogador); na API-Football, pelas transferências do time — e vai para o **clube de
     hoje, se ele estiver no banco** (a saída vira uma transferência ou um empréstimo). O clube é achado pelo nome entre os do
     mesmo gênero (o West Ham masculino e o feminino têm o mesmo nome). Se o clube de destino já tem no banco um jogador com o
     nome e a idade do achado, o achado é ele (não quem saiu) e a saída fica Sem Contrato. No sub-20/B do mesmo clube, a
     saída vem desmarcada; sem clube, aposentado ou num clube que não está no banco, vai para Sem Contrato;
   - **Formação e tática** (opcional): a formação mais usada nos últimos jogos da fonte (Transfermarkt: 5 jogos, ≈6 pedidos
     por time; API-Football: 3 escalações, ≈4 chamadas) e a linha defensiva e a saída de bola pela posição na tabela, como
     nos times criados. Cada time vira uma mudança com a formação, a linha e a saída de bola editáveis na própria lista;
   - **Técnicos** (opcional): o técnico de hoje de cada time (Transfermarkt: 2 pedidos; API-Football: 1 chamada). Se for
     outro, a linha do técnico do time recebe o nome, o nascimento e a nacionalidade dele; se ele já está no banco (mesmo
     nome e nascimento, em outro time ou sem time), com a aparência dele — senão, a de um técnico genérico;
   - **Notas** (opcional): ±2 no máximo, pela nota da API na última temporada liberada em relação à média do time. O
     máximo (±1 a ±10) e a diferença mínima para mudar (na Transfermarkt, entre a nota estimada e a do banco; padrão 3) se
     escolhem embaixo das opções;
   - **Novos** (opcional): jogadores do elenco atual que não existem no banco, criados com nota estimada pelo nível.
4. Cada mudança tem uma caixa; as duvidosas (nome de uma palavra só em outro clube) vêm desmarcadas. As marcadas entram
   ao **Gerar**, junto com o projeto. Times que perdem ou ganham jogadores têm a escalação padrão, os cobradores e o
   capitão refeitos — ninguém que saiu fica escalado. Um time que **ficaria com menos de 11** aparece num aviso na
   conferência e, ao Gerar, é completado com jogadores sem contrato (nota perto da média do time, mesma nação). Antes da
   2.3, esse time ficava com a escalação antiga, apontando para quem saiu, e a conferência final barrava o banco com o erro
   "default_mentalities do time …: jogador … escalado fora do elenco".

Na API-Football, conferir a temporada de agora (promovidos e elencos atuais da liga) exige o plano pago; no grátis, as
temporadas liberadas servem para atualizar um banco mais antigo (ex.: um banco do FC 24).

**Pela Transfermarkt** a temporada de agora está liberada e os elencos trazem a data de nascimento (o casamento dos
jogadores é exato). Transferências e empréstimos vêm do histórico de cada jogador que mudou de time (dono do empréstimo e
fim do contrato); as **notas** vêm do valor de mercado de hoje (perfil de cada jogador) e só mudam quando a estimativa
fica 3 ou mais longe da nota do banco (±2 no máximo); os **novos** são criados com a nota pelo valor de mercado e a
posição e o pé da Transfermarkt. Os pares trocados à mão ficam no mapa separados por fonte.

## O que sai na pasta

- `db\fifa_ng_db.db` + meta: cópia do banco importado com as linhas novas, alteradas e removidas (o original nunca é
  alterado). Antes de gravar, o Criador confere elenco, escalação, cobradores, ids e vínculos dos times mexidos e só grava
  se não houver problema novo (o que já vinha do banco importado vai só para o relatório);
- `tabelas\*.txt`: as tabelas mexidas inteiras, para importar pelo RDBM/DB Master;
- `idioma\LanguageStrings1.txt` e `2.txt` (o idioma importado + os nomes novos) e `LanguageStrings_novos.txt`;
- `internationals.txt` (o importado + as seleções novas) — ou `internationals_linhas_novas.txt` sem internationals importado;
- `imagens\escudos\<teamid>.png` e `imagens\jogadores\<playerid>.png/.jpg`: **Fotos → Criador de Minifaces** manda as
  fotos para lá já ligadas aos IDs (ou ative "Mandar as fotos ao Criador de Minifaces" para ir sozinho);
- `relatorio.txt` e `projeto.json` (mapa API → ids do jogo, também guardado em `dados\criador_mapa.json`).

## Como as notas e a aparência são feitas

- **Nota geral** = nível do time + ajuste pela nota média da API (ponderada pelos minutos), pelos minutos e pela idade.
  Coeficientes calibrados casando jogadores da API com os mesmos jogadores do banco: erro médio de **2,5 pontos** (5 times
  da Série A 2024, cada um fora da amostra). *Espalhamento* estica as notas em volta da média do time.
- **Nota geral (Transfermarkt)** = 35,97 + 5,67 × log10(valor de mercado em €) + 2,06 × (idade − 23, se menor que 23) +
  1,30 × (idade − 31, se maior que 31). Calibrada com 147 jogadores de 6 times da Série A 2026 casados com o banco: erro
  médio de **1,7 pontos** com cada time fora da amostra (2,5 na API-Football com os mesmos times). Sem valor de mercado,
  o jogador vale 60% do menor valor do elenco. Não há espalhamento: a escala já sai como a do jogo. A idade é a que o
  jogador tinha **no fim da temporada** escolhida (num elenco de 2012, a de 2012), e o bônus de veterano para nos 35 anos.
- **Temporadas antigas da Transfermarkt** (terminadas há mais de 2 anos): os valores de mercado de então são bem menores que
  os de hoje, então o nível do time vem da **liga do banco + a classificação final** (até ±3,5, como na API-Football) e o
  valor de mercado da época só distribui as notas dentro do elenco. Ex.: Palmeiras 2012 (18º) → 72,4; Fluminense 2012
  (campeão) → 76,5, com a Série A do banco em 74,1.
- **Nacionalidade (Transfermarkt)**: a primeira das nacionalidades do jogador que existe no banco (Steve Solvet: Guadalupe,
  França → França); só sem nenhuma vai para o Resto do Mundo.
- **Atributos**: mediana dos jogadores do banco da mesma posição, gênero e faixa de nota + estatísticas (gols →
  finalização, desarmes → marcação…), físico e idade, acertados para dar a nota geral exata da posição.
- **Aparência**: de um jogador genérico "completo" do banco (tipo de cabeça, corpo e pele em `skins` — copiada para o
  jogador novo), do mesmo gênero e nação (ou da mesma confederação). Com a foto analisada: pele por regressão nas cores do
  rosto (81% a até um tom do código do banco; fotos muito escuras ou avermelhadas erram — corrija na ficha), cor do cabelo
  pelos vizinhos mais parecidos, penteado e barba pelos jogadores de referência. As fotos da Transfermarkt (retrato
  fechado, fundo de qualquer cor) têm referências próprias (160 jogadores; pele a até um tom em 86%) e não mudam o
  penteado, porque cortam o alto da cabeça. **Recalibrar com o cache** refaz as notas (das duas fontes) e as referências
  da aparência com tudo o que estiver no cache.
- **Técnico**: nome, nascimento e nacionalidade da API; aparência de um técnico genérico do banco do mesmo gênero (nunca
  a cabeça de um técnico real), ou pela foto. Numa seleção que já tem o mesmo técnico, ele fica como está.

## Limitações

- **Liga nova no modo carreira**: precisa também entrar no compdata (Editor de Compdata).
- **Escudo e uniformes**: importe o escudo baixado pelo FET; até lá o escudo fica em branco (ou use *Escudo do
  time-modelo*). Os uniformes usam as cores, sem textura própria.
- A API-Football não tem pé preferido, perna ruim nem estilo de jogo: vêm do modelo do banco (editáveis na prévia).
- Na API-Football, elencos atuais e convocações não trazem a data de nascimento: o casamento usa nome + idade + clube;
  confira as mudanças marcadas como duvidosas.
- **Transfermarkt**: sem futebol feminino; sem peso, notas por jogo nem estatísticas detalhadas (passes, desarmes…) — os
  atributos saem do perfil da posição no banco. A instância pública é só para testes: para ligas inteiras, instale o
  servidor local. A transfermarkt-api lê a Transfermarkt por dentro; se o site mudar, ela pode parar até ser atualizada.
- **Ainda não testado no jogo.** Testado: Palmeiras e Corinthians W (feminino) gerados; seleção do Brasil atualizada
  (25 de 26 convocados casados) e Costa Rica criada (com a linha no internationals); Série A do banco conferida com a
  Série A 2024 da API (10 mudanças de liga) e o elenco atual do Palmeiras; fotos enviadas ao Criador de Minifaces.
  Transfermarkt (2.1): Palmeiras 2026 coletado e gerado (nível 75,7 pelo valor de mercado, 2º na tabela, estádio e cores
  do clube), seleção do Brasil atualizada pela convocação atual (30 jogadores, todos os grupos no mínimo), Série A do banco
  casada com a Série A 2026 (20 de 20 pares) e o elenco do Palmeiras conferido (saídas, novos com nota pelo valor).
  2.2: Palmeiras e Fluminense 2012 (níveis 72,4 e 76,5), Sabah FK (nacionalidades), Palmeiras 2026 com 23 de 29 jogadores
  achados no banco (usar 3 do banco e gerar; usar todos → o Gerar para com o aviso), Série A + Série B conferidas juntas
  (Botafogo-SP e Novorizontino desempatados pelo elenco), 70 de 70 seleções masculinas achadas na Transfermarkt.
