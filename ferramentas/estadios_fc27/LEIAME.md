# Estádios FC 27

Duas ferramentas numa só, no lugar do antigo Conversor PES → FC:

- **Duplicar estádio**: estádios do FC 27 com ID, nome e identidade próprios, quantos e quantas vezes quiser.
- **Converter FIFA 16 / PES 2021 → FC 27**: um estádio do FIFA 16 ou do PES 2021 vira um estádio novo do FC 27, **sempre
  sobre o El Grandioso (181)**. A aba é a mesma; o jogo de origem é escolhido no alto dela.

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
     partem da versão que está no projeto, e um asset nativo que o projeto já editou fica com a sua edição.
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
   - **luzes da torcida à noite** (veja abaixo);
   - recuo do gramado no lado dos bancos;
   - placas baixas de madeira do El Grandioso;
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
| Personagens | Gandulas, fotógrafos e técnicos vão para os marcadores `slc_` do FIFA 16, quando existem; os outros seguem a opção "Personagens laterais". Os reservas sentam nas cadeiras do banco do estádio novo (opção "Reservas no banco"). |
| El Grandioso | A arquitetura dele some. Nenhum subset fica vazio: os que sobram ganham um triângulo de área zero, e as peças que a lógica do jogo liga e desliga vão para baixo do piso. |

## Converter PES 2021 → FC 27

Desde a versão 1.1. Na aba **Converter**, escolha **PES 2021** no alto. O caminho é o mesmo do FIFA 16: uma duplicata
completa do El Grandioso no ID novo, e o estádio do PES no lugar da arquitetura dele. Só muda de onde vêm os dados.
**Precisa de teste em partida**: a conversão foi feita e conferida com o Spotify Camp Nou (st002), mas ainda não foi jogada.

Os estádios do PES 2021 têm todos o mesmo formato (Fox Engine), e a ferramenta lê os arquivos do jogo diretamente, sem
Blender nem outro programa:

| Arquivo do PES | O que a ferramenta tira dele |
|---|---|
| `Asset\model\bg\st<NNN>\#Win\st<NNN>.fpk` e `.fpkd` | os modelos do estádio (`.fmdl`) e o lugar de cada um na cena |
| `…\tv\#Win\tv_st<NNN>.fpk` | as telas, que viram o telão ao vivo do FC 27 |
| `…\sourceimages\tga\#windx11\*.ftex` | as texturas (BC1/BC3 com os mips do PES byte a byte) |
| `…\audi\#Win\audiarea_st<NNN>.fpk` | as áreas da torcida |
| `…\audi\sourceimages\au_seat.png` | a cor de cada cadeira da torcida |
| `…\effect\#Win\effect_st<NNN>_df.fpk` e `_nf.fpk` | as lâmpadas dos glares, de dia e de noite |

1. **Estádio do PES 2021**: escolha a pasta do estádio, a do mod (a que tem `Asset\model\bg\st<NNN>`). Ela precisa ter
   um estádio só.
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
  50 cm, cada um na altura do degrau. A cor da cadeira vem do `au_seat.png`. O setor que o PES marca à parte entra como
  visitantes. A organizada da casa, que o PES não marca, fica no anel inferior atrás do gol da casa.
- **Personagens laterais**: o PES não tem marcadores no modelo. Todos partem das posições do El Grandioso e são conferidos
  contra a geometria do estádio novo (opção "Ajustar ao estádio").
- **Texturas** em formato que não seja BC1, BC3 ou 32 bits sem compressão (BC7, por exemplo) entram como um painel cinza,
  e o resultado avisa quais são.

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
textura própria precisam ser marcadas na lista de peças. Sem nenhuma peça marcada, o estádio fica sem banners dos times.
**Precisa de teste em partida.**

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
| **Acompanham a torcida** (padrão) | Cada luz vai para o trecho equivalente da torcida nova: o mesmo ângulo em volta do campo e a mesma fração da profundidade da arquibancada, da primeira fila à última. Ela anda junto, sem girar. No fim, a intensidade das que andaram é ajustada para a luz mediana na torcida nova ser a do El Grandioso. As que não alcançam a torcida do El Grandioso ficam onde estão. |
| **Ficam onde estão** | Como no Morumbi v3. |

O resultado da conversão compara a luz na torcida nova com a do El Grandioso, antes e depois. O que ainda pode diferir é
a luz rebatida, pré-calculada em volta da torcida do El Grandioso. O proxy de sombra da torcida (`shadow_seat`) só serve
a esse pré-cálculo, por isso não é refeito. **Precisa de teste em partida.**

## Projetos gerados e teste

A aba **Projetos gerados** lista os últimos trabalhos.

- **Ative no FET um projeto de estádio por vez.** Todos mexem no mapa de estádios, nos loaders e no banco. Para usar
  vários estádios juntos, gere as cópias num projeto só, ou acrescente cada uma ao mesmo projeto.
- Se o jogo fechar ao iniciar a partida, o FC 27 grava um dump em `%LOCALAPPDATA%\EA SPORTS FC 27\CrashDumps`.

## Pastas

```
estadios_fc27\
  servidor.py      servidor local da interface (porta 8782); o trabalho roda no motor, num processo à parte
  web\             interface (Duplicar, Converter, Projetos gerados, Ambiente)
  motor\           python -m motor ambiente | preparar | estadios | duplicar | converter | analisar16 | analisarpes | luz16
    ambiente.py    FET, jogo, .NET 8, preparação do SDK e índice do cache
    duplicar.py    duplicação (uma ou várias cópias, do zero ou num projeto)
    verificar.py   verificação do projeto gravado
    projeto.py     plano e gravação do projeto (codec FETP v4 da skill fet-projects, em motor\fet)
    fifa16\        análise, preparação, conversão, banners, bancos, luzes da torcida, leitor RX3 e codificador BC1/BC3
    fifa16\receitas\  receitas guardadas (morumbi_183.json = a conversão testada em partida)
    pes21\         PES 2021: leitores FPK, FMDL, FTEX e FOX2, áreas da torcida, lâmpadas, análise, preparação e conversão
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
