# Estádios FC 27

No lugar do antigo Conversor PES → FC:

- **Duplicar estádio**: estádios do FC 27 com ID, nome e identidade próprios, quantos e quantas vezes quiser.
- **Converter FIFA 16 / PES 2021 → FC 27**: um estádio do FIFA 16 ou do PES 2021 vira um estádio novo do FC 27, **sempre
  sobre o El Grandioso (181)**. A aba é a mesma; o jogo de origem é escolhido no alto dela.
- **Converter em lote** (desde a 2.1): vários estádios do FIFA 16 e do PES 2021 de uma vez, achados nas subpastas de uma
  pasta, num projeto só ou num para cada.

O resultado é sempre um **projeto do FET** (`.fifaproject`) novo: a ferramenta nunca sobrescreve um projeto. Depois de
gravado, o projeto é lido de volta e conferido.

## O que precisa

| Item | Para quê |
|---|---|
| FIFA Editor Tool (testado no 2.2.0, interno 17.1.5.0) com o FC 27 aberto nele uma vez | o SDK do FET e o `fc27.cache` (índice do jogo) |
| EA SPORTS FC 27 instalado | os assets nativos (lidos dos arquivos CAS do jogo, conferidos pelo SHA-1) |
| .NET 8 Runtime | os jobs do SDK (dotnet.microsoft.com/download/dotnet/8.0) |
| numpy, SciPy e zstandard | o Python do Super Tool baixa na página Componentes (ou a ferramenta usa o Python 3.12 do computador, se ele tiver os três). A SciPy entrou na versão 1.1: os banners dos times já precisavam dela |

**Nada do FET nem do jogo vem com a ferramenta.** Na primeira vez (botão **Ambiente › Preparar agora**):

1. As DLLs do SDK são tiradas do **seu** `FIFA Editor Tool.exe`.
2. Elas são adaptadas para o .NET 8 numa cópia local (`cache\sdk`). O FET 2.2.0 é compilado para .NET 11, e o
   `motor\bin\PrepararSdk.dll` faz essa adaptação com o Mono.Cecil:
   - versões das referências;
   - `System.Threading.Lock` e mais alguns métodos para o `motor\bin\Compat.dll`.
   O resto do IL não muda.
3. O `fc27.cache` do FET é lido (`cache\jogo`).

Quando o jogo atualiza, abra o FC 27 no FET uma vez (ele refaz o cache) e prepare de novo. A ferramenta percebe sozinha
que o cache mudou.

## Duplicar estádio

1. Escolha onde as cópias vão:
   - **Projeto novo (do zero)**;
   - **Adicionar a um projeto existente**, um projeto seu do FET. Nesse caso, o banco, o mapa de estádios e os loaders
     partem da versão que está no projeto, e um asset nativo que o projeto já editou fica com a sua edição. Nada do seu
     projeto se perde: no banco, só as tabelas `stadiums` e `audiostadium` mudam, e só ganham as linhas dos estádios
     novos. Desde a 2.1, a verificação confere isso no projeto gravado: todo registro do projeto-base continua lá, igual
     (a não ser o banco, o mapa de estádios e os loaders, que só ganham os estádios novos), todas as outras tabelas do
     banco iguais byte a byte, todas as linhas de estádio que já existiam e todas as entradas do mapa de estádios. O
     arquivo do seu projeto nunca é alterado: o resultado é sempre um arquivo novo.
2. Na lista de estádios do jogo, clique em **Adicionar** nos que quiser e escolha **quantas cópias** de cada um.
3. Cada cópia ganha um ID livre (a partir do primeiro ID que você escolher) e o nome `<nome> (Cópia)`. Os dois são
   editáveis; o nome vai para o banco, com até 63 bytes.
4. **Duplicar** pede onde salvar o `.fifaproject` e mostra as etapas ao vivo.

Cada cópia é um estádio completo. A identidade própria vale para tudo o que é do estádio: mundo, meshes, texturas,
blueprints, torcida, física, Enlighten, MeshVariationDb, depósitos de shader e shader states. É o mesmo método das
duplicatas **702 (do 466) e 703 (do 181), testadas em partida**; o motor desta ferramenta reproduz o 703 byte a byte.

Ficam nativos e compartilhados:
- as definições de tipo;
- os presets de shader;
- os assets de biblioteca que outros estádios também usam.

Registro:
- `StadiumCollectionSLM`, e também o mapa Layer1 quando o original está nele;
- os três `StadiumLoader`;
- as linhas `stadiums` e `audiostadium` do banco. A cópia não tem time da casa.

## Converter FIFA 16 → FC 27

A base é **fixa: o El Grandioso (181)**. A ferramenta faz uma duplicata completa dele no ID novo e põe o estádio do
FIFA 16 no lugar da arquitetura dele. O caminho é sempre o mesmo, o do **Morumbi v3, que funcionou em partida**; com as
opções da v3 (peça 9 descartada, pista do El Grandioso mantida, reservas nos marcadores, luzes da torcida no lugar), o
motor desta ferramenta reproduz a v3 byte a byte. Os estádios do FIFA 16 têm todos o mesmo formato:
- `stadium_<id>.rx3`;
- as texturas de dia e de noite;
- `crowd_<id>_1.dat`;
- `glares_<id>_*.lnx`.

1. **Estádio do FIFA 16**: escolha a pasta (a que tem `data\sceneassets`). A ferramenta lê:
   - as peças e as camadas do modelo;
   - a torcida, as lâmpadas dos glares e os marcadores.

   Para um estádio que já tem receita guardada (o Morumbi), dá para usar a receita da conversão testada. Desde
   01/11/2026 ela traz a peça 9 como Banner dos times e as correções abaixo.
2. **Estádio novo**: ID livre e nome. Pode ir num projeto novo ou dentro de um projeto seu.
3. **Peças do FIFA 16**: o papel de cada peça.
   - **Opaco / Alpha**: entram no estádio.
   - **Telão**: as telas, que no FC 27 mostram a transmissão ao vivo.
   - **Grama**: a grama em volta do campo. É tingida e fica 6 cm abaixo do gramado do FC 27.
   - **Banner dos times**: a peça sai e os banners dos times do FC 27 entram no lugar dela (veja abaixo).
   - **Descartar**: a peça não entra.

   As camadas do FIFA 16 já dizem o que sai: placas de publicidade, o gramado, o céu, o relógio que o FIFA 16
   preenchia na hora do jogo e os brilhos (glow). As peças em que o FIFA 16 punha os banners dos times vêm como Banner
   dos times; as faixas e bandeiras do estádio que devem dar lugar a eles precisam ser marcadas. As outras colunas da
   tabela:
   - **Chão** é quanto a peça sobe no nível do piso. O FIFA 16 contava com a ordem de desenho para superfícies no mesmo
     plano; o FC 27 precisa de alturas diferentes.
   - **1 lado** deixa a peça só com a frente.
   - **Piso** marca as peças que dizem até onde vai o gramado do FC 27, como a pista ou a borracha em volta do campo.
4. **Opções**:
   - faces (vista do campo ou dois lados em tudo);
   - máximo de vértices por peça;
   - **ajuste automático de tamanho** (ligado por padrão): um material maior que um mesh do El Grandioso (5,5 MB) é
     repartido entre vários meshes, cada parte com o próprio material e a mesma textura. Os estádios que cabem sem isso
     saem exatamente como antes. Se nem assim couber (os seis meshes somam 33 MB), a mensagem diz quanto o estádio tem e
     quais são as maiores peças: descarte o que não aparece, marque "1 lado" nas peças vistas só de frente ou use faces
     "vista do campo";
   - **personagens laterais** e **reservas no banco** (veja abaixo);
   - **luzes da torcida à noite** e a sombra delas (veja abaixo);
   - recuo do gramado no lado dos bancos;
   - placas baixas de madeira do El Grandioso;
   - rede do gol, colisão em volta do campo e câmeras (veja abaixo);
   - cadeiras da torcida (cores do FIFA 16 ou uma cor);
   - lado da torcida da casa;
   - altura do anel superior.
5. **Converter**.

O que entra no FC 27:

| Parte | Como entra |
|---|---|
| Modelo | Os materiais são divididos entre os seis meshes do El Grandioso que o mundo principal sempre carrega (arquibancadas, teto, grades, túnel, bancos). Cada LOD fica dentro do que os meshes do FC 27 usam: índices de 16 bits, poucos MB e até 40 subsets. Centímetros viram metros, nos mesmos eixos. |
| Materiais | Um MeshMaterial por material (o preset nativo do modelo), uma variação no MeshVariationDb e uma entrada no depósito de shaders com a textura do FIFA 16. Todo EBX gravado fica na ordem de instâncias do FC 27: fora dela o jogo fecha, como aconteceu com o Morumbi v1 e v2. |
| Texturas | BC1/BC3 com os mips do FIFA 16 byte a byte. |
| Telão | As telas do FIFA 16 no mesh do placar, com o material de telão ao vivo do FC 27. |
| Gramado | O gramado do FC 27 é recortado até o piso marcado; fora do campo, ele fica plano. A pista de atletismo do El Grandioso (a borracha do gramado dele) sai. |
| Torcida | Os lugares e a orientação do FIFA 16, com as cadeiras e os setores de casa, organizada e visitante. A faixa de segurança que o FIFA 16 nunca ocupava sai. |
| Luzes da torcida | As luzes da arquibancada do El Grandioso acompanham a torcida do FIFA 16 (opção "Luzes da torcida", abaixo). |
| Banners dos times | Os banners dos times do FC 27 nas peças marcadas como Banner dos times; os do El Grandioso saem. |
| Glares | Brilhos nas lâmpadas do `.lnx`, de dia e de noite, e fachos de luz das lâmpadas da noite. |
| Personagens | Gandulas, fotógrafos e técnicos vão para os marcadores `slc_` do FIFA 16, quando existem; os outros seguem a opção "Personagens laterais". Os reservas sentam nas cadeiras do banco do estádio novo (opção "Reservas no banco"), e as áreas técnicas do banco de dados ficam à frente desse banco. |
| Colisão | O chão e as paredes invisíveis em volta do campo saem do modelo do estádio novo, com as paredes na frente da arquibancada (opção "Colisão em volta do campo", abaixo). |
| Câmeras | As câmeras de replay e de cenas que a arquibancada nova tapa saem do conjunto do jogo para onde a vista fica livre, num conjunto próprio do estádio (opção "Câmeras", abaixo). |
| El Grandioso | A arquitetura dele some. Nenhum subset fica vazio: os que sobram ganham um triângulo de área zero, e as peças que a lógica do jogo liga e desliga vão para baixo do piso. |

## Converter PES 2021 → FC 27

Desde a versão 2.0. Na aba **Converter**, escolha **PES 2021** no alto. O caminho é o mesmo do FIFA 16: uma duplicata
completa do El Grandioso no ID novo, e o estádio do PES no lugar da arquitetura dele. Só muda de onde vêm os dados.
A primeira conversão do Spotify Camp Nou (st002) foi jogada em partida e o estádio abriu; os acertos que vieram desse
teste (banco de reservas, técnicos, setor sem torcida e luz dos anéis de cima) ainda **precisam de teste em partida**.

Os estádios do PES 2021 têm todos o mesmo formato (Fox Engine), e a ferramenta lê os arquivos do jogo diretamente, sem
Blender nem outro programa:

| Arquivo do PES | O que a ferramenta tira dele |
|---|---|
| `Asset\model\bg\st<NNN>\#Win\st<NNN>.fpk` e `.fpkd` | os modelos do estádio (`.fmdl`) e o lugar de cada um na cena |
| `…\tv\#Win\tv_st<NNN>.fpk` | as telas, que viram o telão ao vivo do FC 27 |
| `…\sourceimages\tga\#windx11\*.ftex` | as texturas (BC1/BC3 com os mips do PES byte a byte) e os mapas normal, especular e de metal de cada material |
| `…\audi\#Win\audiarea_st<NNN>.fpk` | as áreas da torcida |
| `…\audi\sourceimages\au_seat.png` | a cor de cada cadeira da torcida |
| `…\effect\#Win\effect_st<NNN>_df.fpk` e `_nf.fpk` | as lâmpadas dos glares, de dia e de noite |

1. **Estádio do PES 2021**: escolha a pasta do estádio, a do mod (a que tem `Asset\model\bg\st<NNN>`). Se ela tiver
   mais de um estádio (`st009` e `st012`, por exemplo), escolha a pasta `Asset\model\bg\st<NNN>` do que você quer.
2. **Estádio novo**, **Peças** e **Opções**: como no FIFA 16. Cada peça é uma malha dos modelos do PES.
3. **Converter**.

O que é diferente do FIFA 16:

- **Lado dos bancos**: o FC 27 e o El Grandioso têm os bancos de reservas em −Z; o PES aceita os dois lados. A análise
  procura as cadeiras do banco dos dois lados do campo e, se elas estiverem em +Z, o estádio todo gira meia volta em torno
  do centro do campo (modelo, torcida e lâmpadas). Dá para mudar nas Opções.
- **O que sai sozinho**: figurantes e equipamentos de transmissão do PES (o FC 27 tem os próprios personagens), o gramado,
  os vidros e os brilhos (materiais com transparência parcial, que os materiais do El Grandioso usados na conversão não
  têm). As placas, as bandeiras, as redes e as variações de dia e de noite do PES ficam em outros pacotes e não são lidas.
- **Faces**: o PES desenha cada malha só pelo lado das normais, a não ser as marcadas como de dois lados. As peças entram
  do mesmo jeito: com "1 lado" marcado, menos nas de dois lados do PES.
- **Tamanho**: os estádios do PES são mais pesados que os do FIFA 16, e os seis meshes do El Grandioso comportam 33 MB de
  geometria. A lista de peças mostra quanto as peças que ficam ocupam. Se os materiais não couberem com peças grandes, a
  preparação é refeita com peças menores (mais subsets, a mesma geometria). Se o estádio passar dos 33 MB, descarte peças
  que não aparecem.
- **Torcida**: o PES não guarda lugar por lugar, guarda áreas inclinadas sobre a arquibancada. A ferramenta as preenche:
  uma fileira no meio de cada degrau do estádio embaixo da área (sem degraus regulares, de 80 em 80 cm), um lugar a cada
  50 cm, cada um na altura do degrau. A cor da cadeira vem do `au_seat.png`. A organizada da casa do FC 27 fica no anel
  inferior atrás do gol da casa. As áreas da torcida foram conferidas em 100 estádios do PES 2021 (o arquivo muda um pouco
  de um mod para outro); se o `audiarea.bin` de um mod não der para ler, a análise avisa e a torcida do El Grandioso fica.
- **Setor marcado no PES**: o PES dá a cada área da torcida um valor de 0 a 5, e as áreas com 5 formam um setor à parte
  (no Camp Nou, todo o anel inferior atrás de um gol; pelo jeito, o setor da torcida organizada). Por padrão esse setor
  entra como torcida comum e enche como o resto. Como bloco de visitantes do FC 27 (opção), ele pode ficar vazio na
  partida, e foi o que ficou sem torcida no primeiro teste do Camp Nou.
- **Luzes da torcida à noite**: o padrão é **Cobrem toda a torcida** (veja "Luz da torcida à noite"). A torcida do PES
  costuma ser maior e mais alta que a do El Grandioso; só acompanhando, o terceiro anel do Camp Nou ficava com 7% da luz.
- **Banco de reservas, técnicos e áreas técnicas**: no El Grandioso tudo isso fica em volta do banco dele (|x| de 3,4 a
  11 m). A conversão acha o banco do estádio novo e leva para ele:
  - os reservas, nas cadeiras. Uma mureta ou um degrau com parede atrás não conta como fileira de cadeiras: à frente de
    um assento o piso tem de ser mais baixo, e o banco é o grupo de fileiras mais perto do meio-campo;
  - os marcadores dos técnicos e dos auxiliares, à mesma distância da ponta do banco que têm no El Grandioso;
  - as áreas técnicas da linha do estádio no banco de dados (`stadiums.stadhometechzone…` e `stadawaytechzone…`), que
    são onde o técnico anda durante a partida. Elas ficam nos eixos do mundo do estádio, como os marcadores dos técnicos:
    na maioria dos estádios do FC 27, a da casa em −X e a do visitante em +X, as duas em −Z, do lado dos bancos (nos
    poucos com os técnicos em +Z, as áreas também ficam em +Z). As do El Grandioso são a exceção: estão com o sinal
    trocado, do outro lado do campo. A 2.0 gravava as áreas novas do mesmo jeito, e os técnicos iam para o lado oposto ao
    do banco (no teste da Neo Química Arena, girando o estádio ou não); desde a 2.1 elas ficam à frente do banco novo, no
    mesmo lado do campo. Um lado sem banco achado fica com a área do El Grandioso com o sinal acertado, em volta do banco
    dele.
- **Personagens laterais**: o PES não tem marcadores no modelo. Os outros partem das posições do El Grandioso e são
  conferidos contra a geometria do estádio novo (opção "Ajustar ao estádio").
- **Texturas** em formato que não seja BC1, BC3 ou 32 bits sem compressão (BC7, por exemplo) entram como um painel cinza,
  e o resultado avisa quais são. O mesmo vale para as poucas texturas de mods com os mips num arquivo `.ftexs` à parte
  (33 das 44.893 dos estádios testados). Muitos mods guardam os mips pequenos sem compressão e sem a marca disso; desde a
  2.1 eles abrem (antes a conversão da Arena Barueri, por exemplo, parava com erro de descompressão).
- **Relevo e acabamento dos materiais** (desde a 2.1): cada material do FC 27 usa três texturas, a de cor, a normal (o
  relevo) e a de coeficientes (vermelho = reflexo, verde = lisura, azul = metal). Até a 2.0 só a de cor vinha do PES, e
  os materiais ficavam com o normal plano e os coeficientes padrão do El Grandioso: o estádio parecia limpo demais no
  jogo. Agora:
  - o mapa normal do PES (`_nrm`) vira o normal do FC 27 (BC5, até 512 px). As do jogo guardam o X no alfa e o verde
    para cima; muitas de mods guardam XYZ no RGB e o verde para baixo, como o FC 27. A ferramenta reconhece o tipo e
    confere o sentido do verde de cada mapa pelo próprio relevo (teste de integrabilidade); mapas planos ficam com o
    normal do El Grandioso;
  - o especular (`_srm`/`_rgm`: rugosidade no verde) e o de metal (`_mtl`) viram os coeficientes do FC 27 (BC1, até
    512 px; os sem variação viram texturas de 16 px): lisura = 255 − rugosidade, metal do mapa de metal;
  - os quadros tangentes da geometria seguem o sentido dos meshes nativos do FC 27, que é o que os mapas normal pedem.

  No Camp Nou, 31 dos 41 materiais ganham relevo e 39 ganham coeficientes do PES; o projeto passa de 170 para 183 MB.
- **Banners dos times** (desde a 2.1): o PES não marca onde eles ficam; por padrão eles vão sozinhos para as frentes dos
  anéis da torcida (veja "Banners dos times").

## Converter em lote

A aba **Converter em lote** (desde a 2.1) converte vários estádios de uma vez, um depois do outro, pelo mesmo caminho da
conversão de um estádio só e com a receita sugerida pela análise de cada um (ou a guardada, como a do Morumbi do FIFA 16).

1. Escolha uma pasta. A ferramenta procura nas subpastas os estádios do FIFA 16 (`data\sceneassets\stadium\
   stadium_<id>.rx3`) e do PES 2021 (`Asset\model\bg\st<número>\#Win\st<número>.fpk`); um pacote como o Brasil MEGA
   Stadium Pack (mais de 90 estádios) entra inteiro. O nome sugerido é o da pasta do estádio, sem o prefixo de país
   ("BRA - "). Arquivos compactados (.rar, .zip, .7z) ficam de fora e são avisados: extraia antes. Um estádio dentro da
   pasta de outro (como o complemento de exterior do Camp Nou) vem desmarcado.
2. Marque os estádios e ajuste o ID novo e o nome de cada um. Os IDs livres vão em sequência a partir do primeiro ID (os
   do jogo e os que a ferramenta já criou ficam de fora). O resumo avisa ID repetido ou que já existe no jogo e estima o
   tempo (~7 min por estádio) e o tamanho do projeto (~180 MB por estádio).
3. Escolha o projeto:
   - **Todos num projeto só** (recomendado): cada estádio entra no projeto dos anteriores, como em "Adicionar a um
     projeto existente"; o primeiro parte do zero ou do seu projeto do FET. É o jeito de jogar com vários estádios
     convertidos, porque no FET só um projeto de estádio fica ativo por vez.
   - **Um projeto para cada estádio**, numa pasta (`Estadio_<ID>_<nome>.fifaproject`).
4. As opções valem para todos: rede do gol, banners dos times (PES), luzes da torcida, personagens laterais e reservas.
   Para mexer nas peças de um estádio, converta-o sozinho na aba Converter.

Um estádio que dá erro, ou cujo projeto não passa na verificação, fica de fora (a etapa dele fica marcada com erro), e
os outros seguem; o resultado lista cada um, com o tempo e o erro. Cada estádio aparece também em Projetos gerados. Tudo
o que a conversão cria leva o ID novo no nome (pastas, GUIDs, chaves de shader), então estádios com o mesmo número no PES
(muitos do pacote são st009) não colidem no mesmo projeto. Cada estádio é verificado contra o projeto dos anteriores (ou
contra o seu projeto, no primeiro): nada do que já estava some ou muda (veja "Adicionar a um projeto existente", em
Duplicar estádio).

Testado com o Allianz Parque do FIFA 16 e a Arena Barueri e o Anacleto Campanella do Brasil MEGA Stadium Pack (os dois
st009) num projeto novo, e com a Arena Barueri e a Neo Química Arena do FIFA 16 sobre um projeto do BRFP 27 com o banco
editado: 473 registros do projeto e 266 tabelas do banco iguais, `stadiums` de 181 para 183 linhas. Cerca de 6 a 7 min
por estádio. **Precisa de teste em partida.**

## Rede do gol

O El Grandioso usa a rede funda (tipo 1, com 3,20 m de fundo: o "véu de noiva"), que no FC 27 só ele e mais quatro
estádios têm; a maioria usa a quadrada (tipo 0, com 2,29 m). Até a 2.0, todo estádio convertido herdava a do El
Grandioso. Desde a 2.1, a conversão grava a quadrada na linha do estádio novo no banco (`stadiums.stadiumgoalnettype` e
`stadiumgloalnetdepth`, com a grafia do próprio jogo); a opção **Rede do gol** volta à do El Grandioso.

## Colisão em volta do campo

Cada estádio do FC 27 tem uma "bacia" de colisão em que a bola bate e os jogadores param: o chão em volta do campo e
paredes invisíveis baixas, viradas para ele (um RES de física do estádio, só com triângulos; no Old Trafford, paredes de
1 a 3 m na frente da arquibancada). A do El Grandioso vai até depois da pista de atletismo (até 88 m do centro nos fundos
e 60 m nas laterais), e até a 2.0 todo estádio convertido ficava com ela: numa arquibancada mais perto do campo, os
jogadores entravam nela até bater na parede invisível do El Grandioso (relatado na comemoração de um gol na Neo Química
Arena do PES).

Desde a 2.1 a conversão faz a bacia do estádio novo: de cada direção a partir do centro do campo, acha no modelo o
primeiro obstáculo na altura dos jogadores (de 0,55 a 2,2 m acima do gramado) a partir de 2 m depois da borda do campo,
e põe ali uma parede de 0,5 m abaixo a 2,5 m acima do gramado; onde não há obstáculo até 25 m da borda (túnel, vão entre
arquibancadas), a parede fica nesse limite. O que é mais baixo que 0,55 m não conta (os tapetes de publicidade atrás do
gol do FIFA 16 têm 46 cm e punham a parede a 2,6 m da linha de fundo do Allianz Parque). O chão vai do centro até as
paredes, na altura do gramado. Os objetos soltos
do El Grandioso que tinham colisão (caixas perto dos abrigos e dos cantos, que não existem no estádio novo) saem; a
colisão das placas de publicidade fica, porque as placas do El Grandioso continuam. O resultado diz a que distância das
linhas as paredes ficaram e avisa se alguma placa ficou além da parede (dentro da arquibancada). Na Neo Química Arena do
PES: paredes a uns 10 m da linha lateral e 9 m da de fundo (as do El Grandioso ficavam a até 26 e 36 m), 474 triângulos;
no Allianz Parque do FIFA 16, 14 e 10 m. A opção **Colisão em volta do campo** volta à do El Grandioso. **Precisa de teste
em partida.**

## Câmeras

Cada estádio do jogo pode ter câmeras próprias para os replays e as cenas (torcida, comemoração, entrada dos times,
pênalti, bancos): um conjunto que troca só as câmeras que mudam naquele estádio, casadas pelo nome com as do conjunto
genérico, e registrado numa tabela do jogo (`Broadcasting/Cameras/CameraOverridesBrt`). Um ID novo não tem conjunto
próprio e usa o genérico (`Broadcasting/Cameras/StadiumCameras`, 1317 câmeras), feito para arquibancadas mais longe do
campo: até a 2.0, numa arquibancada mais perto, algumas câmeras de torcida e de comemoração ficavam atrás ou dentro dela.

Desde a 2.1 a conversão confere cada câmera do conjunto genérico contra o modelo do estádio novo. A vista fica tapada
quando há arquibancada na linha da câmera ao foco (depois do plano de corte da câmera e antes do último trecho, que é a
própria torcida ou o gramado) ou entre a câmera e o campo. Cada câmera tapada vai para onde todas as vistas dela ficam
livres, pelo menor deslocamento entre: câmera e foco juntos na direção do centro do campo (o mesmo enquadramento, mais
para dentro; até 40 m nas câmeras de torcida e só um empurrão de até 3 m nas outras, que filmam bancos, jogadores e
cenas que não mudam de lugar), a câmera mais perto do foco, ou a câmera mais alta. Ficam como estão as câmeras que
acompanham a jogada, as que filmam o estádio por fora e as do interior do túnel (o túnel do conjunto genérico fica onde
está a arquibancada nova, e mover a câmera não traria os jogadores para a vista). As movidas vão num conjunto próprio do
estádio novo, com o bundle e o registro iguais aos dos estádios do jogo; a entrada na tabela é gravada pelo gerenciador
de mods ao aplicar o mod, como nos troféus e uniformes que o próprio FET duplica. Na Neo Química Arena do PES, 24
câmeras do conjunto genérico ficavam tapadas: 22 foram movidas (8 m na mediana, até 28 m) e 2 não têm posição livre e
ficam como estão; no Allianz Parque do FIFA 16, 27 tapadas e 24 movidas. A câmera de jogo (a que você escolhe para
jogar) não muda. A opção **Câmeras** volta ao conjunto do jogo. **Precisa de teste em partida.**

## Personagens laterais

O El Grandioso tem cerca de 240 marcadores de personagens em volta do campo: gandulas, fotógrafos, câmeras, policiais,
seguranças, médicos, oficiais, técnicos e os da cerimônia de entrada. Eles ficam logo atrás das placas dele, a uns 6 a 8 m
das linhas laterais e de fundo. Num estádio do FIFA 16 com a arquibancada mais perto do campo, ficariam dentro dela.

| Opção | O que faz |
|---|---|
| **Ajustar ao estádio** (padrão) | Usa os marcadores `slc_` do FIFA 16 onde eles existem. Os personagens que ficam nas posições do El Grandioso são conferidos contra a geometria do estádio novo: se estiverem dentro dela, embaixo da arquibancada ou atrás do muro, vão para o lugar livre mais próximo do lado do campo (fora das placas, a mais de 1 m das linhas). Sem lugar a até 10 m, saem de vista. |
| **Esconder** | Técnicos e auxiliares ficam (ajustados). Todos os outros saem de vista. |
| **Só os marcadores do FIFA 16** | O comportamento da v3 do Morumbi: o que não tem marcador fica onde o El Grandioso põe. |

"Sair de vista" é ir 100 m para baixo do piso: só a posição muda. Os marcadores são exportados (outros arquivos podem
apontar para eles), então nenhum sai da camada. O resultado da conversão diz quantos ficaram, quantos foram ajustados e
quantos saíram de vista.

Os modos "Ajustar" e "Esconder" ainda **precisam de teste em partida**.

### Reservas no banco

Os 7 reservas de cada time (`choreo_seats`) ficam, no El Grandioso, nas cadeiras do banco dele. Os marcadores
`slc_benchplayer` do FIFA 16 não servem de referência: cada autor os pôs de um jeito, e muitas vezes eles não batem com
as cadeiras.

| Opção | O que faz |
|---|---|
| **Nas cadeiras do banco** (padrão) | A ferramenta acha as cadeiras do banco no modelo do FIFA 16: assento de 30 a 70 cm acima do piso, com encosto atrás, no lado dos bancos, perto da linha lateral. Os reservas sentam na fileira da frente, uma cadeira sim, outra não, a partir do meio, na posição e na orientação dos reservas do El Grandioso (um banco do outro lado do campo gira meia volta). Se não houver cadeiras para todos, os que sobram saem de vista. |
| **Nos marcadores do FIFA 16** | Nos `slc_benchplayerhome` e `slc_benchplayeraway`. |
| **Esconder** | Todos saem de vista. |

O resultado da conversão diz quantas cadeiras achou e quantos reservas sentaram. **Precisa de teste em partida.**

As áreas técnicas da linha do estádio no banco de dados (onde o técnico anda durante a partida) acompanham o banco em
que os reservas sentaram, à frente dele e no mesmo lado do campo; sem banco (ou com os reservas escondidos), ficam em
volta do banco do El Grandioso. Até a 2.0 a conversão do FIFA 16 deixava as do El Grandioso, que estão do outro lado do
campo (veja "Banco de reservas, técnicos e áreas técnicas", em Converter PES 2021 → FC 27).

## Banners dos times

O FIFA 16 punha os banners dos times, na hora do jogo, em peças do estádio (camada `Banner_NoShadowCast`, shaders
`bannergroup…`), e muitos estádios trazem faixas e bandeiras próprias (no Allianz Parque, as das torcidas e as da
Allianz). No FC 27, os banners dos times são objetos do mundo `banners`: o El Grandioso tem 90, em seis formatos (1x1,
2x1, 2x1 grande, 4x1, 6x1 e 8x1), e o jogo põe neles os banners dos times da partida.

As peças marcadas como **Banner dos times** saem do modelo, e os banners do El Grandioso saem do lugar dele. No lugar
delas entram banners do FC 27:
- cada peça é dividida em superfícies planas viradas para o campo (de 0,6 × 0,3 m para cima);
- cada superfície recebe o formato mais parecido com ela (nas compridas, vários em fila), na escala que cabe, 2 cm à
  frente dela;
- as variantes de cada formato se alternam; o limite é de 250 banners (o El Monumental tem 543).

A análise já marca como Banner dos times as peças que o FIFA 16 deixava vazias para os banners dele. As faixas com
textura própria precisam ser marcadas na lista de peças. Sem nenhuma peça marcada, um estádio do FIFA 16 fica sem
banners dos times.

### Banners automáticos (PES 2021, desde a 2.1)

O PES não marca onde ficam os banners dos times. Com a opção **Banners dos times: nas frentes dos anéis da torcida**
(padrão) e nenhuma peça marcada, a ferramenta os põe como o El Grandioso põe os dele (na mureta da frente do anel de
baixo, a uns 2 m do chão, e na frente dos anéis de cima):
- procura faces quase verticais viradas para o campo, fora dele, com lugares da torcida logo atrás e acima e nenhum lugar
  na frente (o que descarta os espelhos dos degraus, as costas de cadeiras e as paredes do fundo dos anéis);
- a parte abaixo de 1,2 m não conta (as placas de publicidade do FC 27 ficam na frente), nem o meio do lado dos bancos
  (túnel e bancos); muretas com menos de 1 m de altura ficam sem banners;
- cada mureta recebe uma fileira de banners de ~2 m de altura (ou a da mureta, se for menor), com 3 m entre eles,
  alternando os formatos; as mais baixas primeiro, até 160 banners.

No Camp Nou, eles ficam na frente do anel do meio (o primeiro anel tem só 0,9 m de mureta); no Maracanã, na frente do anel
de cima, nas laterais (atrás dos gols não há mureta vertical). Peças marcadas como Banner dos times têm prioridade: com
elas, vale o caminho do FIFA 16. **Precisa de teste em partida.**

## Luz da torcida à noite

A luz rebatida da torcida, das cadeiras e do estádio vem do **Enlighten**, que a EA pré-calcula para cada estádio. A
conversão usa sempre o do El Grandioso. Com o pré-cálculo de outro estádio, a partida fica carregando sem fim, por isso
essa opção foi desativada.

À noite, a torcida também é iluminada por luzes do El Grandioso que não são pré-calculadas: 145 spots em volta da
arquibancada (`lighting_stands_main`) e 4 nas torres (`lighting_flood_main`), todos apontados para baixo, com alcance de
3 a 70 m. Nenhuma delas projeta sombra. Numa torcida mais perto do campo que a do El Grandioso (Neo Química Arena, Allianz
Parque), as lâmpadas caíam no meio dela, com o dobro da luz e manchas; numa mais longe (Morumbi), partes dela ficavam no
escuro.

| Opção | O que faz |
|---|---|
| **Cobrem toda a torcida** (padrão no PES 2021, desde a 2.0) | A torcida nova é dividida em tantos trechos quantas são as luzes que iluminam a torcida do El Grandioso (129). Cada luz vai para a frente e para cima do seu trecho, a 22 m, do lado do campo, apontada para ele, com alcance de pelo menos 45 m e a intensidade ajustada para o trecho receber 1,25 vez a luz mediana do El Grandioso. Serve às torcidas maiores ou mais altas que a dele. No Camp Nou, pela conta da ferramenta, o terceiro anel passa de 7% para 126% da luz do El Grandioso, e nenhum lugar fica sem luz (antes, 14%). |
| **Acompanham a torcida** (padrão no FIFA 16) | Cada luz vai para o trecho equivalente da torcida nova: o mesmo ângulo em volta do campo e a mesma fração da profundidade da arquibancada, da primeira fila à última. Ela anda junto, sem girar. No fim, a intensidade das que andaram é ajustada para a luz mediana na torcida nova ser a do El Grandioso. As que não alcançam a torcida do El Grandioso ficam onde estão. |
| **Ficam onde estão** | Como no Morumbi v3. |

O resultado da conversão compara a luz na torcida nova com a do El Grandioso, antes e depois. O que ainda pode diferir é
a luz rebatida, pré-calculada em volta da torcida do El Grandioso. O proxy de sombra da torcida (`shadow_seat`) só serve
a esse pré-cálculo, por isso não é refeito. **Precisa de teste em partida.**

### Sombra das luzes da torcida (desde a 2.2)

Essas luzes não projetam sombra em tempo real, mas 76 das 145 do El Grandioso usam uma máscara de sombra pré-calculada
(`ShadowMask` de 1 a 4): o jogo escurece a luz delas com a sombra calculada na arquitetura do El Grandioso, com as luzes
no lugar antigo. No estádio convertido essa sombra cai em pedaços soltos da arquibancada e da torcida, que ficam escuros
à noite sem nada na frente (relatado em 2026-11-17). Desde a 2.2 a conversão tira a máscara dessas luzes (`ShadowMask`
0, como nas outras 69 do El Grandioso e na maioria das luzes dos estádios do jogo): elas passam a iluminar sem sombra.
A opção **Sombra das luzes da torcida** volta à do El Grandioso. **Precisa de teste em partida.**

## Projetos gerados e teste

A aba **Projetos gerados** lista os últimos trabalhos.

- **Ative no FET um projeto de estádio por vez.** Todos mexem no mapa de estádios, nos loaders e no banco. Para usar
  vários estádios juntos, gere as cópias num projeto só, acrescente cada uma ao mesmo projeto ou use a conversão em lote
  com "Todos num projeto só".
- Se o jogo fechar ao iniciar a partida, o FC 27 grava um dump em `%LOCALAPPDATA%\EA SPORTS FC 27\CrashDumps`.

## Pastas

```
estadios_fc27\
  servidor.py      servidor local da interface (porta 8782); o trabalho roda no motor, num processo à parte
  web\             interface (Duplicar, Converter, Converter em lote, Projetos gerados, Ambiente)
  motor\           python -m motor ambiente | preparar | estadios | duplicar | converter | procurar | lote | analisar16 |
                   analisarpes | luz16
    ambiente.py    FET, jogo, .NET 8, preparação do SDK e índice do cache
    duplicar.py    duplicação (uma ou várias cópias, do zero ou num projeto)
    verificar.py   verificação do projeto gravado
    lote.py        conversão em lote (procura dos estádios numa pasta e conversão em sequência)
    projeto.py     plano e gravação do projeto (codec FETP v4 da skill fet-projects, em motor\fet)
    fifa16\        análise, preparação, conversão, banners, bancos, luzes da torcida, leitor RX3 e codificador BC1/BC3
    fifa16\receitas\  receitas guardadas (morumbi_183.json = a conversão testada em partida)
    pes21\         PES 2021: leitores FPK, FMDL, FTEX e FOX2, áreas da torcida, lâmpadas, mapas normal e de coeficientes,
                   banners automáticos, análise, preparação e conversão
                   (a conversão herda a do FIFA 16)
    csharp\        fontes dos jobs do SDK (StadiumTool, ConvertTool), do PrepararSdk e do Compat
    bin\           os mesmos compilados (só código da ferramenta + Mono.Cecil, licença MIT)
  cache\           SDK preparado, índice e extrações do jogo, miniaturas e trabalhos (fica fora do pacote)
```

Os binários de `motor\bin` são compilados com o .NET 8 SDK:

```
dotnet build motor\csharp\<projeto> -c Release -p:SdkDir=<cache\sdk\…>
```

O `SdkDir` é a pasta do SDK já preparado. O `Compat` e o `PrepararSdk` não precisam dele.
