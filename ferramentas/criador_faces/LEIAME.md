# Criador de Faces — versão 2.0

Cria a **face de um jogador a partir de fotos**, de dois jeitos (escolha em **Como criar**, no painel da direita):

- **Criador próprio** — roda no seu computador, sem custo e sem enviar as fotos a ninguém. Acha o rosto nas fotos, ajusta
  a cabeça do FC 27 a ele e grava direto o **headmorphpreset (FBX)** e a **textura careca** (`face_color`), prontos para
  o FET. A forma é uma aproximação feita com as cabeças do próprio jogo; a textura vem das suas fotos.
- **KeenFace** — serviço pago (keenface.ai, da KeenTools), na sua conta: a forma sai mais fiel. A cabeça volta como
  **.glb** e o **MG Keen Converter** (de MGthefacemaker) a transforma na face do FC 27.

## Criador próprio

### Preparação (uma vez)

O painel da direita mostra o que falta, com um botão em cada linha:

1. **Componentes**: MediaPipe (Google, Apache 2.0), numpy, SciPy, OpenCV e zstandard, baixados para o Python embutido do
   Super Tool (uns 25 MB a mais para quem já usa as outras ferramentas).
2. **Face de referência do FC 27** (`messi_158023_fc27.fbx`): a mesma do Conversor de Faces. Vem no pacote completo do
   Super Tool; no pacote leve, use **Importar…**.
3. **FIFA Editor Tool, o cache do FC 27 nele e o jogo**: o criador lê as cabeças do seu próprio jogo pelo `fc27.cache`
   que o FET cria quando abre o FC 27 (abra o jogo no FET uma vez). Se não achar as pastas sozinho, use **Escolher…**.
4. **Modelo das cabeças do jogo** (**Preparar**): baixa os dois modelos do MediaPipe que acham o rosto (20 MB) e monta,
   em 1 a 2 minutos, o modelo com as cabeças masculinas do seu jogo (mais de 4.000), as peles de base carecas e a textura
   dos olhos. Tudo fica em `cache/`, só neste computador, e é refeito quando o jogo muda (o criador avisa).

Nada do jogo vem com a ferramenta nem vai para o GitHub: o modelo é feito aí, do seu jogo.

### Usar

1. **Fotos**: de 1 a 6, JPG, PNG ou WebP. O ideal são três: uma de frente e uma de cada lado, entre 40° e 70° (não precisa
   ser perfil), nítidas, com o rosto grande e inteiro, boca fechada, olhos abertos, sem óculos nem boné, e **a mesma luz
   nas três** (fotos com luz diferente deixam a pele manchada). A ordem não importa: o criador acha a de frente.
2. **Nome** e **ID do jogador no jogo**: o ID entra no nome dos arquivos, como o FET espera
   (`headmorphpreset_<ID>_0_0.fbx` e `face_<ID>_0_0_color.png`). Vazio = 0.
3. **Criar face** (`Ctrl+Enter`): leva de 1 a 3 minutos (a parte demorada é o ajuste da forma). Dá para cancelar.
4. A face pronta aparece em 3D e fica na lista. Na pasta dela (padrão `Faces criadas`, na pasta de trabalho):
   - `headmorphpreset_<ID>_0_0.fbx` e `face_<ID>_0_0_color.png`: **importe os dois no FET**, na pasta do jogador;
   - `previa_fotos.png`: cada foto ao lado da cabeça na mesma pose (**Comparar com as fotos**), para conferir o encaixe;
   - `previa_3d.png`, `previa.glb` (a prévia 3D) e `relatorio.json` (ângulo e distância de cada foto, erro do ajuste).

### O que esperar

- **Textura careca**: a pele vem das fotos (barba e sobrancelhas ficam) e tudo o que o cabelo cobre ou as fotos não
  mostram vem de uma pele de base do próprio jogo, com a cor acertada pela pele das fotos. O cabelo é o do jogo.
- **Olhos**: os globos e o desenho da íris saem no padrão das cabeças do jogo (olhando para a frente), encaixados nas
  pálpebras da face criada.
- **Forma**: o criador combina as cabeças do jogo até os pontos do rosto e o contorno do perfil baterem com as fotos, com
  a perspectiva de cada foto. Nariz, boca, queixo e proporções saem parecidos; detalhes finos (bochechas, mandíbula) ficam
  perto da média. Na cabeça de teste, a diferença média para a do KeenFace ficou em 1,1 mm no rosto (a cabeça média do
  jogo dá 1,35 mm). Se precisar de mais fidelidade, use o KeenFace.
- O criador grava só a textura de cor: o mapa normal e o specmask continuam os que o jogador já tinha no jogo.

## KeenFace

### Antes de começar

- **Conta no KeenFace e chave da API**: entre em [keenface.ai](https://keenface.ai), abra **API keys** e crie uma chave
  (começa com `ak_`). Cole no painel da direita, em **Conta do KeenFace**: a ferramenta confere a chave e mostra o saldo.
  A chave fica só neste computador (`preferencias.json` desta pasta, que não vai para o pacote nem para o GitHub).
- **Créditos**: cada cabeça custa **150 créditos**, com todos os arquivos incluídos (baixar de novo ou em outro formato não
  custa nada). Na data desta versão (nov/2026) o crédito custava € 0,10 sem impostos (uns € 15 por cabeça), sem
  assinatura e sem validade; conta nova ganha 450 créditos grátis, que só podem ser usados depois de **confirmar um
  telefone** no Studio do KeenFace. Cabeça que falha não é cobrada. Preços atualizados em keenface.ai/pricing.
- **MG Keen Converter**: programa à parte, baixado no Ko-fi do autor (MGthefacemaker). Ele não vem com o Super Tool; a
  ferramenta só abre o programa que você já tem (ela procura o `MG Keen Converter.exe` na pasta de trabalho, em
  Downloads, Documentos e Área de Trabalho, ou você mostra onde está).

### Usar

1. **Fotos** (painel da esquerda): `Ctrl+O`, o botão **Adicionar** ou arrastar para a janela. De 1 a 15 fotos JPG, PNG,
   WebP, HEIC ou AVIF da mesma pessoa. O ideal: uma de frente e uma de cada lado (três quartos ou perfil), nítidas, com o
   rosto grande e inteiro, sem óculos nem boné, expressão neutra e olhos abertos. Clique com o botão direito numa foto
   para mudar a ordem.
2. **Tipo de fotos** (painel da direita, **Cabeça nova**):
   - **Fotos variadas** (padrão do KeenFace): fotos de qualquer lugar (internet, celular, prints), com luz e fundo
     diferentes. Textura PBR com limpeza (sem a luz das fotos).
   - **Sessão de fotos** (Scan Reconstruction): de 2 a 15 fotos tiradas na mesma sessão, com a pessoa parada, a mesma
     expressão e a mesma luz. A forma sai mais fiel. Opções: textura **PBR** (com ou sem limpeza) ou **Crua** (a cor das
     fotos, com a luz delas), e a lente em mm (vazio = automática).
3. **Nome**: vira o nome da pasta e do arquivo (`Nome.glb`). O MG Keen Converter usa o nome do arquivo na saída dele.
4. **Arquivos**: pasta de saída (padrão `Cabeças KeenFace`, na pasta de trabalho), imagens JPG ou PNG e, se quiser,
   também o **FBX MetaHuman** (`head.fbx` com a pasta `texture`, que o MG também aceita).
5. **Privacidade e direitos**: marque **Posso usar estas fotos** (veja abaixo).
6. **Criar cabeça** (`Ctrl+Enter`): a ferramenta envia as fotos, confere com o KeenFace o **custo e o saldo** e espera a
   sua confirmação (**Criar por 150 créditos**). Só então a cabeça é criada; ela leva alguns minutos (a barra mostra a
   fila e o progresso) e o .glb é baixado sozinho para `pasta de saída\Nome\Nome.glb`, com um `keenface.json` (id da
   cabeça no KeenFace, fotos usadas e modo).
7. **Converter**: com a cabeça pronta, **Converter no MG Keen Converter** abre o programa e copia o caminho do .glb. No MG:
   **OPEN HEADS**, cole o caminho, **CONVERT ALL** (o ID do jogador pode ser digitado no cartão da cabeça para os arquivos
   saírem com os nomes do jogo). Depois, no FET, importe na pasta do jogador: `headmorphpreset_<ID>_0_0` (FBX),
   `face_<ID>_0_0_color` e `face_<ID>_0_0_normal` (PNG).

## Minhas faces e cabeças

A lista embaixo da prévia guarda as faces do criador próprio e as cabeças do KeenFace criadas aqui (e, com **Atualizar**,
as feitas pela API em outro computador com a mesma conta). Nas do criador próprio, o menu mostra o FBX, a textura e as
imagens de conferência; duplo clique abre a pasta. Nas do KeenFace: Clique para ver em 3D (`T` textura, `W` malha, `G` girar, `F` enquadrar); duplo clique
abre o MG Keen Converter. No menu de cada uma:

- **Baixar do KeenFace (sem custo)**: o GLB, o MetaHuman (`head.fbx` + texturas 4K) ou o OBJ (`neutral.obj` + texturas).
- **Conferir no KeenFace**: continua de onde parou se a ferramenta fechou ou a internet caiu no meio (a cabeça segue no
  KeenFace e o pedido é refeito com a mesma chave de idempotência, sem cobrar de novo).
- **Apagar no KeenFace**: apaga as fotos e os arquivos guardados na sua conta (não devolve créditos; os arquivos já
  baixados ficam).
- **Tirar da lista**: só tira daqui.

## Privacidade e direitos

No **criador próprio** nada sai do computador. No **KeenFace**, as fotos vão para os servidores da **KeenTools**
(keenface.ai), que montam a cabeça, e ficam guardadas na sua conta até
você apagar a cabeça (dá para apagar em **Minhas cabeças**). Fotos enviadas que não viraram cabeça (cancelado ou tiradas
da lista) são apagadas do KeenFace na hora; as que sobrarem expiram em 24 h. Fotos soltas na janela ficam numa cópia
temporária da ferramenta, apagada quando saem da lista ou quando a ferramenta abre de novo.

Pelos termos do KeenFace, quem envia garante que tem direito de usar as fotos e o consentimento das pessoas fotografadas:
por isso a confirmação **Posso usar estas fotos** antes de criar.

## Erros comuns do KeenFace

- **Chave recusada**: copie a chave inteira (começa com `ak_`) ou crie outra em API keys.
- **Créditos insuficientes**: compre créditos no site; as fotos já enviadas ficam guardadas por 24 h, então é só criar de
  novo.
- **Confirmar telefone**: créditos grátis só depois de confirmar um telefone no Studio do KeenFace.
- **Aceitar os termos**: o KeenFace às vezes pede para a conta aceitar termos atualizados; o botão **Abrir o site do
  KeenFace** leva direto à página.
- **Fotos recusadas / não deu para montar a cabeça**: troque as fotos (mais nítidas, rosto inteiro, uma pessoa só, luz
  uniforme). Cabeça que falha não é cobrada.

## Técnico

**Criador próprio** (`local/`, roda num processo à parte pelo `local/criar.py`): MediaPipe Face Landmarker (478 pontos) e
Selfie Multiclass (pele, cabelo, fundo); modelo estatístico (PCA, 150 componentes) dos `headmorphblend` das cabeças
masculinas do jogo, lidos pelo índice do cache do FET (o mesmo leitor dos Estádios FC 27); cabeça base = face de
referência menos o morph do mesmo jogador; ajuste por mínimos quadrados dos coeficientes e de uma câmera com perspectiva
por foto (pontos com tabela por ângulo + silhueta do perfil); olhos com a orientação e a UV médias das cabeças do jogo
(no morph de UV0 dos olhos o V do jogo é invertido em relação ao FBX do FET); textura projetada na UV da cabeça e
completada com a `skin_base` do jogo de cor mais próxima. O FBX é a face de referência com as posições novas em todos os
LODs e é relido para conferir.

**KeenFace**: só biblioteca padrão do Python. API v2 do KeenFace
(`https://api.keenface.ai/v2`): cada foto vai por `POST /v2/photos` (com progresso), o custo vem de
`POST /v2/heads?dry_run=true`, a cabeça é criada com `POST /v2/heads` e `Idempotency-Key`, acompanhada por
`GET /v2/heads/{id}?wait=10` e baixada por `GET /v2/heads/{id}/model` (o link assinado é baixado sem a chave). A prévia 3D
lê o .glb com um leitor próprio (three.js do Super Tool) e não mexe no arquivo: o MG Keen Converter pede o arquivo
exatamente como saiu do KeenFace. `BRFP_KEENFACE_API` troca o endereço da API (testes com um servidor falso).
