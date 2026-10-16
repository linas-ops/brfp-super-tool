# BRFP Super Tool — versão 3.1

Todas as ferramentas de modding do BRFP numa janela só, com a mesma interface (a do Editor de Estádios):
menus no topo, painéis laterais, avisos, diálogos e atalhos iguais em todas.

## Abrir

Dois cliques em **`BRFP Super Tool.bat`**. Abre uma janela de aplicativo (Edge ou Chrome) com:

- **trilho à esquerda**: uma tecla por ferramenta (passe o mouse para ver o nome e a versão; o ponto verde indica que
  ela está aberta). Botão direito: reiniciar, fechar, guia, pasta e registro da ferramenta;
- **Componentes** (chip, embaixo no trilho): o Python embutido, os pacotes das ferramentas, os programas do computador
  (Blender, RDBM 26…) e o pacote para levar o Super Tool a outro computador;
- **Dados do jogo** (cilindro, embaixo no trilho): banco de dados, idioma e internationals.txt do jogo, importados uma vez para
  todas as ferramentas;
- **Início** (casa, ou `Ctrl+0`): cartões das ferramentas, o que está importado, a tabela de versões e os guias.

Cada ferramenta abre quando você clica nela e continua aberta enquanto você troca de uma para outra (`Ctrl+1` … `Ctrl+9`).
Fechar a janela do Super Tool (o console preto) encerra todas. Abrir o .bat de novo com o Super Tool já aberto só
mostra outra janela.

Não precisa instalar nada: o Super Tool roda num **Python próprio** que fica dentro da pasta dele (`runtime\python`,
Python 3.12 do python.org, isolado — não usa nem altera o Python que estiver instalado no computador).

## Em outro computador (novo na 2.1)

1. Gere o pacote em **Componentes › Levar para outro computador**:
   - **Completo** (≈ 100 MB): já vem com o Python e todos os pacotes — abre sem internet;
   - **Leve** (≈ 5 MB): sem o Python; precisa de internet na primeira vez.
2. No outro computador, extraia o .zip numa pasta sua (ex.: `C:\BRFP Super Tool` ou Documentos — evite caminhos muito
   longos, o Windows limita a 260 caracteres) e dê dois cliques em **`BRFP Super Tool.bat`**.
3. Pacote leve: na primeira vez o .bat pergunta se baixa o Python agora (11 MB, de python.org) ou o Python e todos os
   pacotes (≈ 110 MB); também dá para usar um Python 3.10+ já instalado. Depois disso, abre direto.
4. Se o Windows avisar que o arquivo veio da internet ("O Windows protegeu o computador" ou "O editor não pôde ser
   verificado"), clique em **Mais informações › Executar assim mesmo** (ou **Executar**). Para não ver o aviso: antes de
   extrair, botão direito no .zip › Propriedades › **Desbloquear**.

O pacote leva o motor do Conversor PES → FC e o RDBM 26 · Add-on FC 27 (ficam em `ferramentas\conversor_pes\motor` e
`ferramentas\rdbm`) e **nada deste computador**: preferências, banco e idioma importados, caches, saídas, backups e o
`addon.ini` ficam de fora — cada computador importa os próprios dados.

## Componentes (novo na 2.1)

- **Python embutido**: versão, pasta e se está em uso (o .bat sempre usa ele quando existe).
- **Pacotes das ferramentas**: numpy e SciPy (Conversor de Faces), numpy, SciPy e Pillow (Conversor de Corpos), OpenCV,
  Pillow e numpy (Criador de Minifaces). Versões
  fixas do PyPI, conferidas pelo SHA-256 (`comum\componentes.json`), instaladas em `runtime\python\Lib\site-packages`.
- **Transfermarkt API (servidor local)** (novo na 2.4, opcional): a [transfermarkt-api](https://github.com/felipeall/transfermarkt-api)
  4.2.0 (felipeall, licença MIT) + FastAPI, uvicorn, httpx, pydantic e mais 20 bibliotecas, ≈4 MB. O projeto fica em
  `runtime\apps\transfermarkt-api`; o Criador de Ligas e Times liga o servidor sozinho (porta 8790, só neste computador)
  quando usa a fonte Transfermarkt. Sem ele, o Criador usa a instância pública (lenta, só para testes). Vai no pacote
  completo só se estiver instalado.
  Se faltarem, a própria ferramenta mostra **Baixar os componentes…** (o chip "Motor indisponível" também abre esse
  aviso); instalado por qualquer janela, as outras ferramentas percebem sozinhas.
- **Programas do computador**: Edge/Chrome (janela do Super Tool), texconv (vem junto), Visual C++ 2015–2022 (o texconv
  precisa; normalmente já vem com o jogo), Blender 5.2 (Conversor PES), RDBM 26 e .NET Framework 4.8 (Add-on FC 27). **Localizar…**
  indica o Blender ou o RDBM quando não estão no lugar padrão; **Baixar** abre a página oficial.
- **Levar para outro computador**: o pacote .zip descrito acima.

Os diálogos de abrir, salvar e escolher pasta são os nativos do Windows (o mesmo do Explorer), em todas as ferramentas.

## Dados do jogo (novo na 2.0)

Importe uma vez e todas as ferramentas usam:

- **Banco de dados**: o `fifa_ng_db.db` (com o `fifa_ng_db-meta.xml` na mesma pasta) ou uma pasta com as tabelas exportadas
  em `.txt` (UTF-16 do RDBM/DB Master ou UTF-8). Vale qualquer versão (novo na 2.5): **FIFA 16, 21, 22, 23, FC 24, 26 e
  27** — a versão é reconhecida pelas tabelas e campos do próprio banco (dá para trocar). O Super Tool guarda o esquema
  (meta) de cada uma dessas versões em `comum\esquemas` (tirado dos seus bancos): um `fifa_ng_db.db` **sem o meta ao lado**
  abre com o meta guardado da versão reconhecida, e o Conversor de Tabelas usa esses esquemas como destino.
- **Idioma**: os `LanguageStrings1.txt` e `LanguageStrings2.txt` exportados pelo FET (o `.db` de idioma do FC 27 é
  criptografado; o do FC 26 pode ser importado direto).
- **Internationals** (novo na 2.3): o `internationals.txt` do jogo/mod (fica fora do banco). O Criador de Ligas e Times
  acrescenta nele as seleções novas (TIER_AND_OBJECTIVES) e usa os mínimos e máximos de convocados por posição
  (SQUAD_SELECTION) e a idade-limite. O arquivo importado nunca é alterado: a versão com as seleções novas sai na pasta
  do banco gerado.

A página mostra o que está importado e tem um navegador das tabelas (registros, tipos e faixas do meta) e dos times com
os elencos. Quem usa: o **Editor de Compdata** (nomes de times, competições, estágios e grupos), o **Criador de Minifaces**
(times e jogadores para ligar as fotos aos IDs), o **Conversor de Tabelas** (origem da conversão) e o **Criador de Ligas e
Times** (modelos, notas, seleções e o internationals). As tabelas são lidas
sob demanda e guardadas em cache em `dados\cache`; o registro fica em `dados\fontes.json`.

## Ferramentas e versões

| Ferramenta | Versão | O que faz |
|---|---|---|
| BRFP Super Tool | 3.1 | Janela única, trilho, início com versões e guias; Dados do jogo compartilhados (banco de qualquer versão, FIFA 16 … FC 27, idioma, internationals); Python embutido, Componentes (com o servidor local da Transfermarkt) e pacote para outro computador. |
| Editor de Estádios | 3.0 | Exports do FET em 3D: ocultar/mover peças, texturas do jogo, luzes, torcida, banco e áreas técnicas, stadiums.txt. |
| Editor de Placares | 2.1 | Overlays APT do jogo e de mods: textos, cores, imagens, posições, animações e fontes; grava para o Live Editor. |
| Editor de Compdata | 2.1 | Competições → estágios → grupos com renumeração automática; nomes vindos do banco e do idioma importados. |
| Conversor de Faces | 1.2 | Cabeças (FBX do FET) FC 26 ↔ FC 27: identifica o jogo, pasta de saída, prévia 3D; roda no Python embutido e baixa numpy/SciPy se faltarem. |
| Conversor de Corpos | 1.0 | Textura do corpo (bodyupper: pele, tatuagens, normal) FC 26 ↔ FC 27: identifica o layout de cada imagem, refaz a UV do outro jogo com cada tatuagem no mesmo lugar do corpo, prévia no corpo em 3D e plana. |
| Criador de Minifaces | 1.2 | Foto → miniface do jogo (p&lt;ID&gt;.png 180×180): tira o fundo, enquadra o rosto e liga ao jogador pelo time; recebe as fotos do Criador de Ligas e Times já ligadas aos IDs. |
| Editor de Banco | 1.0 | Times (elenco, escalação, formação, capitão, cobradores, tática, cores, técnico), jogadores, ligas, árbitros, técnicos e qualquer tabela; transferências, empréstimos, liberar; verificação de erros com correção; grava um banco novo. |
| Criador de Ligas e Times | 2.2 | Ligas, times, seleções e jogadores da API-Football ou da Transfermarkt (notas calibradas no banco — pelo valor de mercado na Transfermarkt —, feminino, aparência pelas fotos, tática, técnico, estádio) e atualização do banco: elencos, empréstimos, saídas e participantes das ligas. |
| Atualizador de Squads | 1.1 | Squad do mod + squad mais recente da EA → squad atualizado: times brasileiros inteiros do mod (sem os genéricos da EA), times, ligas e competições novos, jogadores criados pelo mod; duplicados unidos, IDs reusados trocados, escalações refeitas. |
| Conversor de Tabelas | 1.1 | Tabelas do banco entre qualquer par de versões (FIFA 16 … FC 27): colunas novas, renomeadas e calculadas, escalas, faixas; destino pelo esquema guardado; grava .txt ou um .db novo. |
| Conversor PES → FC | 2.0 | Estádios do PES 2021 → FC 26 sem comandos: assistente de nova conversão, configuração em formulário, etapas explicadas, lista do que importar no FET, prévias, ferramentas. |
| RDBM 26 · Add-on FC 27 | 1.0.0 | Programa à parte: abre squads do FC 27 no RDBM 26. O Super Tool abre o add-on e passa os comandos. |

A versão de cada uma aparece no trilho, nos cartões do Início, no selo ao lado do nome (no topo da ferramenta) e em
**Ajuda › Sobre**.

## Pastas

```
stadium conversor\
  BRFP Super Tool\
    BRFP Super Tool.bat     abre tudo (na primeira vez num computador, baixa o Python embutido)
    LEIA-ME PRIMEIRO.txt    como abrir, para quem recebe o pacote
    supertool.py            janela principal (inicia cada ferramenta sob demanda)
    runtime\python\         Python embutido + pacotes (Lib\site-packages)
    runtime\apps\           projetos baixados em Componentes (transfermarkt-api)
    comum\                  base compartilhada: estilo (brfp.css), componentes da interface (ui.js), ícones, three.js,
                            servidor (base.py), banco/idioma do jogo (dados.py), diálogos nativos (dialogos.py),
                            componentes e downloads (componentes.py, componentes.json, instalar_python.ps1) e o
                            gerador do pacote (pacote.py); esquemas\ = o meta de cada versão do jogo
    dados\                  banco, idioma e internationals importados (fontes.json + cache), chave e cache da API-Football,
                            configuração e cache da Transfermarkt (transfermarkt.json, tm_cache) — criado na primeira importação
    web\                    interface da janela principal
    ferramentas\
      estadios\             Editor de Estádios (LEIAME.md)
      placares\             Editor de Placares (LEIAME.md)
      compdata\             Editor de Compdata (README.md)
      faces\                Conversor de Faces (LEIAME.md; motor\ = conversor em numpy e as faces de referência)
      corpos\               Conversor de Corpos (LEIAME.md; motor\ = conversor e os corpos de referência; cache\mapas)
      minifaces\            Criador de Minifaces (LEIAME.md; motor\ = OpenCV)
      tabelas\              Conversor de Tabelas (LEIAME.md)
      banco\                Editor de Banco (LEIAME.md; a edição em andamento fica em banco\cache)
      criador\              Criador de Ligas e Times (LEIAME.md; chave e cache da API ficam em dados\)
      squads\               Atualizador de Squads (LEIAME.md; relatórios em squads\saida)
      conversor_pes\        interface do Conversor PES → FC (no pacote, o motor fica em conversor_pes\motor)
      rdbm\                 (só no pacote) RDBM 26 · Add-on FC 27
  conversor\                motor do Conversor PES → FC (configs, etapas, Blender) — saída em saida\ e work\
  RDBM26 Add-on FC27\       add-on do RDBM (atalho "RDBM26 FC27" na Área de Trabalho)
```

As preferências de cada ferramenta ficam na pasta dela (`preferencias.json`). Os exports, o `stadiums.txt` e as saídas
continuam onde sempre estiveram: a "pasta de trabalho" do Super Tool é a `stadium conversor`.

## Abrir uma ferramenta sozinha

Ainda dá: `runtime\python\python.exe ferramentas\<pasta>\servidor.py` abre só aquela ferramenta numa janela própria (os
editores de estádios e placares mantêm os seus .bat, que também usam o Python embutido). O conversor de faces também funciona pela linha de comando
(`ferramentas\faces\motor\Converter faces.bat`, arrastando arquivos ou pastas).
