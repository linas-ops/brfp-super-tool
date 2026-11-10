# Criador de Faces — versão 1.0

Cria a **cabeça 3D de um jogador a partir de fotos** com a API do **KeenFace** (keenface.ai, da KeenTools), usando a
chave e os créditos da sua conta. A cabeça volta como **.glb** (o formato que o MG Keen Converter recomenda), com prévia
3D aqui mesmo, e o **MG Keen Converter** (de MGthefacemaker) transforma o .glb na face do FC 27
(headmorphpreset + face color + face normal) para importar no FET.

## Antes de começar

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

## Usar

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

## Minhas cabeças

A lista embaixo da prévia guarda todas as cabeças criadas aqui (e, com **Atualizar**, as feitas pela API em outro
computador com a mesma conta). Clique para ver em 3D (`T` textura, `W` malha, `G` girar, `F` enquadrar); duplo clique
abre o MG Keen Converter. No menu de cada uma:

- **Baixar do KeenFace (sem custo)**: o GLB, o MetaHuman (`head.fbx` + texturas 4K) ou o OBJ (`neutral.obj` + texturas).
- **Conferir no KeenFace**: continua de onde parou se a ferramenta fechou ou a internet caiu no meio (a cabeça segue no
  KeenFace e o pedido é refeito com a mesma chave de idempotência, sem cobrar de novo).
- **Apagar no KeenFace**: apaga as fotos e os arquivos guardados na sua conta (não devolve créditos; os arquivos já
  baixados ficam).
- **Tirar da lista**: só tira daqui.

## Privacidade e direitos

As fotos vão para os servidores da **KeenTools** (keenface.ai), que montam a cabeça, e ficam guardadas na sua conta até
você apagar a cabeça (dá para apagar em **Minhas cabeças**). Fotos enviadas que não viraram cabeça (cancelado ou tiradas
da lista) são apagadas do KeenFace na hora; as que sobrarem expiram em 24 h. Fotos soltas na janela ficam numa cópia
temporária da ferramenta, apagada quando saem da lista ou quando a ferramenta abre de novo.

Pelos termos do KeenFace, quem envia garante que tem direito de usar as fotos e o consentimento das pessoas fotografadas:
por isso a confirmação **Posso usar estas fotos** antes de criar.

## Erros comuns

- **Chave recusada**: copie a chave inteira (começa com `ak_`) ou crie outra em API keys.
- **Créditos insuficientes**: compre créditos no site; as fotos já enviadas ficam guardadas por 24 h, então é só criar de
  novo.
- **Confirmar telefone**: créditos grátis só depois de confirmar um telefone no Studio do KeenFace.
- **Aceitar os termos**: o KeenFace às vezes pede para a conta aceitar termos atualizados; o botão **Abrir o site do
  KeenFace** leva direto à página.
- **Fotos recusadas / não deu para montar a cabeça**: troque as fotos (mais nítidas, rosto inteiro, uma pessoa só, luz
  uniforme). Cabeça que falha não é cobrada.

## Técnico

Só biblioteca padrão do Python (roda no Python embutido do Super Tool). API v2 do KeenFace
(`https://api.keenface.ai/v2`): cada foto vai por `POST /v2/photos` (com progresso), o custo vem de
`POST /v2/heads?dry_run=true`, a cabeça é criada com `POST /v2/heads` e `Idempotency-Key`, acompanhada por
`GET /v2/heads/{id}?wait=10` e baixada por `GET /v2/heads/{id}/model` (o link assinado é baixado sem a chave). A prévia 3D
lê o .glb com um leitor próprio (three.js do Super Tool) e não mexe no arquivo: o MG Keen Converter pede o arquivo
exatamente como saiu do KeenFace. `BRFP_KEENFACE_API` troca o endereço da API (testes com um servidor falso).
