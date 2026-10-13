// BRFP Super Tool — janela principal: trilho de ferramentas, início com versões e as ferramentas abertas em quadros.
import { $, el, esc, aviso, modal, confirmar, abrirMenu, nota, modalAberto } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { markdown } from './comum/markdown.js';
import { mb, barraTarefa, acompanhar } from './comum/componentes.js';

const S = { versao: '', raiz: '', pasta: '', ferramentas: [], ativo: null, quadros: new Map(), esperando: null, dados: null, comp: null,
  nav: { aba: 'tabelas', tabela: null, time: null, busca: '', ini: 0 } };
const porId = (id) => S.ferramentas.find((f) => f.id === id);

const NOVIDADES = {
  estadios: 'v3: luzes com um clique, banco de reservas e áreas técnicas, stadiums.txt (espelhamento, medidas do campo), escala ancorada no chão, texturas lidas direto do jogo, cor sólida.',
  placares: 'v2.1: exportar todas as imagens do placar (e dos componentes) de uma vez. v2: simulador das animações do jogo com linha do tempo, constantes e curvas de animação, fontes (famílias do FIFA.xml e importação de TTF).',
  compdata: 'v2.1: nomes de times, competições, estágios e grupos vindos do banco e do idioma importados; v2: interface no padrão do Super Tool, recentes, validação ~70× mais rápida.',
  minifaces: 'v1.2: recebe as fotos do Criador de Ligas e Times já ligadas aos IDs novos. v1.1: roda no Python embutido e baixa OpenCV/Pillow se faltarem. v1.0: tira o fundo da foto, enquadra o rosto como as minifaces do jogo e liga cada foto ao ID do jogador pelo time do banco.',
  banco: 'v1.0: times (elenco, escalação, formação, capitão, cobradores, tática, cores, dados do clube, técnico), jogadores, ligas, árbitros, técnicos e qualquer tabela; transferências, empréstimos, liberar, números; verificação de erros com correção; edição salva sozinha com desfazer; grava um banco novo (FIFA 16 … FC 27).',
  criador: 'v2.2: Atualizar banco com várias ligas de uma vez (painéis de casamento, desempate pelo elenco) e ligas de seleções; time rebaixado sem divisão abaixo vai para o Resto do Mundo; coluna de foto, tirar jogador do elenco, jogadores que já estão no banco (usar o do banco); Transfermarkt: idade da época e nível de temporadas antigas pela liga e classificação, nacionalidade válida, elenco com jogador sem foto. v2.1: Transfermarkt como segunda fonte (escolha no topo da aba API) — ligas, times, seleções, coleta com nota pelo valor de mercado e Atualizar banco; servidor local em Componentes ou instância pública. v2.0: seleções (convocação casada com o banco + internationals.txt), feminino, Atualizar banco (elencos, empréstimos, saídas, números, notas e participantes das ligas), aparência pelas fotos, tática, técnico, estádio, IDs à mão, todas as colunas editáveis, vários times de uma vez, fotos para o Criador de Minifaces. v1.0: ligas, times e jogadores da API-Football com notas calibradas no banco.',
  tabelas: 'v1.1: qualquer par de versões (FIFA 16, 21, 22, 23, FC 24, 26, 27), colunas renomeadas e de resumo calculadas, destino pelo esquema guardado. v1.0: converte tabelas entre FC 26 e FC 27 — colunas novas, escalas que mudaram, faixas do meta — e grava .txt ou um .db novo.',
  corpos: 'v1.0: texturas do corpo (pele e tatuagens do bodyupper) FC 26 ↔ FC 27: identifica o layout de cada imagem, refaz a UV do outro jogo (cor e mapa normal), prévia 3D da entrada e do resultado no corpo.',
  faces: 'v1.2: roda no Python embutido e baixa numpy/SciPy se faltarem. v1.1: interface com lista de faces e jogo identificado, pasta de saída, prévia 3D da entrada e do resultado, arrastar e soltar.',
  conversor_pes: 'v2.0: sem comandos — assistente de nova conversão (acha o estádio do mod e o mundo do export), configuração em formulário, etapas explicadas com progresso e dicas de erro, lista do que importar no FET, prévias, ferramentas em cartões. v1.0: interface para o conversor de linha de comando — etapas, registro ao vivo, PASSOS_FET.md e entregas.',
  rdbm: 'v1.0: abre squads do FC 27 no RDBM 26; verificação de squad e importação de banco/idioma.',
};
const NOVIDADES_ST = 'v2.9: Conversor de Faces 1.3, Conversor de Corpos 1.1 e Criador de Minifaces 1.3 — no pacote leve, que não traz os arquivos de referência tirados do jogo, as ferramentas avisam o que falta (em vez do erro "FileNotFoundError") e importam as referências do pacote completo com um clique (zip, pasta ou os próprios arquivos). v2.8: Criador de Ligas e Times 2.3 — casamento de jogadores pelo nome (não só pela data de nascimento), saídas para o clube novo, formação, tática e técnicos no Atualizar banco, ligas sem país casadas time a time, times com menos de 11 completados com passes livres (corrige o erro "escalado fora do elenco"), completar a API-Football com a Transfermarkt, escolher quais convocados criar, tirar vários itens do projeto de uma vez; Editor de Banco 1.1. v2.7: avisa no Início quando sai uma versão nova (Releases do GitHub) e atualiza com um clique, sem mexer nos seus dados. v2.6: Conversor de Corpos (textura do corpo e tatuagens FC 26 ↔ FC 27). v2.5: Editor de Banco; Dados do jogo reconhece e abre bancos de todas as versões (FIFA 16 … FC 27), até sem o meta ao lado (esquemas guardados); gravação de tabelas com textos comprimidos (Huffman) no .db. v2.4: Componentes instala o servidor local da Transfermarkt (transfermarkt-api) para o Criador de Ligas e Times 2.1. v2.3: internationals.txt em Dados do jogo; Criador de Ligas e Times 2.0 (seleções, feminino, atualização do banco) com envio das fotos ao Criador de Minifaces. v2.2: Criador de Ligas e Times (API-Football). v2.1: Python embutido (runtime) e página Componentes — baixa o que faltar, acha Blender e RDBM e gera o pacote para outro computador; diálogos nativos do Windows. v2.0: Dados do jogo.';

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }

// ---------------------------------------------------------------- trilho
function desenharTrilho() {
  const t = $('#trilho-ferramentas');
  t.innerHTML = '';
  S.ferramentas.forEach((f, i) => {
    const b = el('button', { class: `trilho-btn ${S.ativo === f.id ? 'ativo' : ''}`, 'data-id': f.id, 'aria-label': `${f.nome} ${f.versao}`,
      onclick: () => abrir(f.id), oncontextmenu: (e) => { e.preventDefault(); menuFerramenta(f, e.clientX, e.clientY); } }, icone(f.icone, 20));
    if (f.tipo === 'web' && f.estado && f.estado !== 'parado') b.append(el('span', { class: `ponto ${f.estado}` }));
    dica(b, f.nome, `${f.versao}${i < 9 ? ` · Ctrl+${i + 1}` : ''}`);
    t.append(b);
  });
  $('#btn-inicio').classList.toggle('ativo', S.ativo === 'inicio');
}

let dicaEl = null;
function dica(b, txt, extra = '') {
  b.addEventListener('mouseenter', () => {
    dicaEl?.remove();
    const r = b.getBoundingClientRect();
    dicaEl = el('div', { class: 'dica-trilho', style: { top: `${r.top + r.height / 2 - 14}px` } }, txt, extra ? el('small', {}, extra) : null);
    document.body.append(dicaEl);
  });
  b.addEventListener('mouseleave', () => { dicaEl?.remove(); dicaEl = null; });
}

function menuFerramenta(f, x, y) {
  const web = f.tipo === 'web';
  const ligada = web && f.estado && f.estado !== 'parado';
  abrirMenu([
    { cabecalho: `${f.nome} ${f.versao}` },
    { rotulo: 'Abrir', icone: 'janela', fn: () => abrir(f.id) },
    web ? { rotulo: 'Reiniciar a ferramenta', icone: 'recarregar', desabilitado: !ligada, fn: () => reiniciar(f) } : null,
    web ? { rotulo: 'Fechar a ferramenta', icone: 'parar', desabilitado: !ligada, fn: () => fechar(f) } : null,
    '-',
    { rotulo: 'Guia', icone: 'ajuda', fn: () => guia(f.id, f.nome) },
    { rotulo: 'Abrir a pasta', icone: 'pasta', fn: () => tentar(() => api('abrir_pasta', { id: f.id })) },
    web ? { rotulo: 'Ver o registro', icone: 'terminal', desabilitado: !ligada && f.estado !== 'erro', fn: () => verLog(f) } : null,
  ], x, y);
}

// ---------------------------------------------------------------- navegação
function mostrar(id) {
  S.ativo = id;
  $('#tela-inicio').hidden = id !== 'inicio';
  $('#tela-rdbm').hidden = id !== 'rdbm';
  $('#tela-dados').hidden = id !== 'dados';
  $('#tela-componentes').hidden = id !== 'componentes';
  $('#btn-dados').classList.toggle('ativo', id === 'dados');
  $('#btn-componentes').classList.toggle('ativo', id === 'componentes');
  for (const [k, q] of S.quadros) q.hidden = k !== id;
  $('#abrindo').hidden = !(S.esperando && S.esperando === id);
  const f = porId(id);
  document.title = f ? `${f.nome} — BRFP Super Tool` : id === 'dados' ? 'Dados do jogo — BRFP Super Tool'
    : id === 'componentes' ? 'Componentes — BRFP Super Tool' : 'BRFP Super Tool';
  if (location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
  desenharTrilho();
  api('lembrar', { id }).catch(() => {});
}

async function abrir(id) {
  if (id === 'inicio') { desenharInicio(); mostrar('inicio'); return; }
  if (id === 'dados') { await paginaDados(); mostrar('dados'); return; }
  if (id === 'componentes') { await paginaComponentes(); mostrar('componentes'); return; }
  const f = porId(id);
  if (!f) { mostrar('inicio'); return; }
  if (f.tipo === 'nativo') { await paginaRdbm(); mostrar('rdbm'); return; }
  if (!f.existe) { aviso(`${f.nome}: arquivos não encontrados em ${f.pasta}`, { tipo: 'erro' }); return; }
  if (f.estado === 'rodando' && f.url && S.quadros.has(id)) {
    mostrar(id);
    S.quadros.get(id).focus();
    return;
  }
  if (f.estado !== 'rodando' || !f.url) {
    const r = await tentar(() => api('iniciar', { id }));
    if (!r) return;
    Object.assign(f, r);
  }
  S.esperando = id;
  telaAbrindo(f);
  mostrar(id);
  await esperar(f);
}

function telaAbrindo(f, erro = null) {
  const a = $('#abrindo');
  a.innerHTML = '';
  const caixa = el('div', { class: 'abrindo-caixa' }, el('div', { class: 'ic-grande', html: icone(erro ? 'aviso' : f.icone, 56) }));
  if (!erro) {
    caixa.append(el('h2', {}, `Abrindo o ${f.nome}…`), el('div', {}, `versão ${f.versao}`),
      el('div', { class: 'barra-progresso indeterminado' }, el('div')));
  } else {
    caixa.querySelector('.ic-grande').style.color = 'var(--perigo)';
    caixa.append(el('h2', {}, `O ${f.nome} não abriu`), el('div', {}, erro),
      (f.log || []).length ? el('div', { class: 'console' }, f.log.join('\n')) : null,
      el('div', { class: 'acoes' }, el('button', { class: 'btn-primario', onclick: () => abrir(f.id) }, icone('recarregar', 14), 'Tentar de novo'),
        el('button', { class: 'btn', onclick: () => tentar(() => api('abrir_pasta', { id: f.id })) }, icone('pasta', 14), 'Abrir a pasta'),
        el('button', { class: 'btn-fantasma', onclick: () => abrir('inicio') }, 'Voltar ao início')));
  }
  a.append(caixa);
  a.hidden = false;
}

async function esperar(f) {
  const t0 = Date.now();
  while (Date.now() - t0 < 60000) {
    const r = await api('ferramentas').catch(() => null);
    if (r) {
      S.ferramentas = r.ferramentas;
      const g = porId(f.id);
      desenharTrilho();
      if (g.estado === 'rodando' && g.url) {
        criarQuadro(g);
        S.esperando = null;
        if (S.ativo === f.id) { mostrar(f.id); S.quadros.get(f.id).focus(); }
        return;
      }
      if (g.estado === 'erro' || g.estado === 'parado') {
        S.esperando = f.id;
        if (S.ativo === f.id) telaAbrindo(g, g.erro || 'A ferramenta fechou ao iniciar.');
        return;
      }
    }
    await new Promise((res) => setTimeout(res, 350));
  }
  if (S.ativo === f.id) telaAbrindo(f, 'Demorou demais para abrir.');
}

function criarQuadro(f) {
  let q = S.quadros.get(f.id);
  if (q && q.dataset.url === f.url) return q;
  if (q) q.remove();
  q = el('iframe', { src: f.url, title: f.nome, 'data-url': f.url, allow: 'clipboard-read; clipboard-write' });
  q.hidden = S.ativo !== f.id;
  $('#quadros').append(q);
  S.quadros.set(f.id, q);
  return q;
}

function tirarQuadro(id) {
  const q = S.quadros.get(id);
  if (q) { q.remove(); S.quadros.delete(id); }
}

async function fechar(f) {
  if (!await confirmar(`Fechar o ${f.nome}?`, 'O que não foi salvo nessa ferramenta será perdido. Ela abre de novo quando você clicar nela.', { rotulo: 'Fechar', perigo: true })) return;
  tirarQuadro(f.id);
  await tentar(() => api('parar', { id: f.id }));
  await atualizar();
  if (S.ativo === f.id) abrir('inicio');
}

async function reiniciar(f) {
  if (!await confirmar(`Reiniciar o ${f.nome}?`, 'A ferramenta é fechada e aberta de novo. O que não foi salvo nela será perdido.', { rotulo: 'Reiniciar', perigo: true })) return;
  tirarQuadro(f.id);
  const r = await tentar(() => api('reiniciar', { id: f.id }));
  if (!r) return;
  Object.assign(porId(f.id), r);
  S.esperando = f.id;
  telaAbrindo(f);
  mostrar(f.id);
  await esperar(f);
}

async function verLog(f) {
  const r = await tentar(() => api('log?id=' + f.id));
  if (!r) return;
  modal({ titulo: `Registro — ${f.nome}`, largo: true, corpo: el('div', { class: 'console', style: { maxHeight: '60vh' } }, r.linhas.join('\n') || '(vazio)'),
    botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

async function atualizar() {
  const r = await api('ferramentas').catch(() => null);
  if (!r) return;
  const antes = new Map(S.ferramentas.map((f) => [f.id, f.estado]));
  S.ferramentas = r.ferramentas;
  desenharTrilho();
  if (S.ativo === 'inicio') {
    S.dados = await api('dados').catch(() => S.dados);
    desenharInicio();
  }
  // a ferramenta aberta caiu: mostra o erro no lugar do quadro
  for (const f of S.ferramentas) {
    if (f.tipo !== 'web') continue;
    if (antes.get(f.id) === 'rodando' && f.estado === 'erro') {
      tirarQuadro(f.id);
      aviso(`${f.nome} fechou sozinho`, { tipo: 'erro', detalhe: f.erro || '', acao: { rotulo: 'Abrir de novo', fn: () => abrir(f.id) } });
      if (S.ativo === f.id) { S.esperando = f.id; telaAbrindo(f, f.erro); mostrar(f.id); }
    }
  }
}

// ---------------------------------------------------------------- início
function desenharInicio() {
  const t = $('#tela-inicio');
  t.innerHTML = '';
  const i = el('div', { class: 'inicio' });
  i.append(el('div', { class: 'bv-hero' }, el('div', { class: 'bv-hero-ic' }), el('div', {},
    el('h1', {}, 'BRFP Super Tool', el('span', { class: 'marca-versao' }, S.versao)),
    el('p', {}, 'Todas as ferramentas de modding do BRFP numa janela só, com a mesma interface: estádios, placares, competições, faces, corpos (tatuagens), minifaces, tabelas do banco e o conversor de estádios do PES. O banco e o idioma do jogo são importados uma vez em Dados do jogo e valem para todas.'))));
  i.append(faixaAtualizacao());
  const grade = el('div', { class: 'grade-ferramentas' });
  S.ferramentas.forEach((f, n) => {
    const web = f.tipo === 'web';
    const est = web ? (f.estado || 'parado') : 'nativo';
    const rotEst = { parado: 'fechada', iniciando: 'abrindo…', rodando: 'aberta', erro: 'com erro', nativo: 'programa à parte' }[est];
    grade.append(el('div', { class: `cartao-ferr ${web ? '' : 'nativo'}` },
      el('div', { class: 'topo-c' }, el('div', { class: 'ic-c', html: icone(f.icone, 22) }),
        el('div', { class: 'nome-c' }, el('b', {}, f.nome, el('span', { class: 'marca-versao' }, f.versao)),
          el('small', {}, el('span', { class: `estado-c ${est}` }, rotEst), n < 9 ? el('span', {}, `· Ctrl+${n + 1}`) : null))),
      el('p', {}, f.descricao),
      el('div', { class: 'acoes-c' },
        el('button', { class: 'btn-primario peq', disabled: !f.existe, onclick: () => abrir(f.id) }, icone(web ? 'janela' : 'externo', 13), f.existe ? 'Abrir' : 'Não encontrado'),
        el('button', { class: 'btn-fantasma peq', onclick: () => guia(f.id, f.nome) }, icone('ajuda', 13), 'Guia'),
        el('button', { class: 'btn-icone peq', title: 'Mais opções', onclick: (e) => { const r = e.currentTarget.getBoundingClientRect(); menuFerramenta(f, r.left, r.bottom + 4); } }, icone('lista', 14)))));
  });
  i.append(faixaDados());
  i.append(el('div', { class: 'bv-bloco' }, el('h3', {}, 'Ferramentas'), grade));
  i.append(el('div', { class: 'bv-bloco' }, el('h3', {}, 'Versões'), tabelaVersoes()));
  i.append(el('div', { class: 'rodape-inicio' },
    el('span', {}, `Pasta de trabalho: ${S.raiz}`),
    el('button', { onclick: () => tentar(() => api('abrir_pasta', { id: 'supertool' })) }, 'Abrir a pasta do Super Tool'),
    el('button', { onclick: () => guia('supertool', 'BRFP Super Tool') }, 'Guia do Super Tool')));
  t.append(i);
}

// aviso de versão nova (última Release do GitHub); sem internet não mostra nada
function faixaAtualizacao() {
  const caixa = el('div', { class: 'faixa-atualizacao' });
  api('atualizacao').then((r) => {
    if (!r.nova && !(r.estado && (r.estado.ativo || r.estado.fase === 'pronto'))) return;
    const desenhar = (e) => {
      caixa.innerHTML = '';
      if (e && e.fase === 'pronto') {
        caixa.append(nota(esc(e.msg) + (e.falhas && e.falhas.length ? `<br><small>${e.falhas.map(esc).join('<br>')}</small>` : ''), e.falhas && e.falhas.length ? 'alerta' : ''));
        return;
      }
      const ocupado = e && e.ativo;
      const pct = ocupado && e.total ? Math.round((e.feito * 100) / e.total) : 0;
      const n = nota(`<b>Versão ${esc(r.ultima)} disponível</b> (você está na ${esc(r.atual)}). ${ocupado ? esc(`${e.fase === 'baixando' ? 'Baixando' : 'Copiando'}… ${pct}%`) : 'Seus dados, preferências e o Python ficam como estão.'}`
        + (e && e.fase === 'erro' ? `<br><small>${esc(e.msg)}</small>` : ''), e && e.fase === 'erro' ? 'erro' : '');
      n.append(el('div', { class: 'acoes-linha', style: { marginLeft: 'auto' } },
        r.notas ? el('button', { class: 'btn peq', onclick: () => modal({ titulo: `Novidades da versão ${r.ultima}`, largo: true, corpo: el('div', { class: 'md', html: markdown(r.notas) }), botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] }) }, 'Novidades') : null,
        el('button', { class: 'btn-primario peq', disabled: ocupado, onclick: atualizar }, icone('recarregar', 12), ocupado ? 'Atualizando…' : 'Atualizar')));
      caixa.append(n);
    };
    const acompanharEstado = async () => {
      const x = await tentar(() => api('atualizar_estado'));
      if (!x) return;
      desenhar(x.estado);
      if (x.estado.ativo) setTimeout(acompanharEstado, 500);
      else if (x.estado.fase === 'pronto') aviso(x.estado.msg, { tipo: x.estado.falhas.length ? 'aviso' : 'sucesso', tempo: 10000 });
    };
    const atualizar = async () => {
      if (!await confirmar(`Atualizar para a versão ${r.ultima}?`, 'Baixa o pacote leve do GitHub e troca os arquivos das ferramentas. Banco e idioma importados, preferências, saídas e o Python embutido não mudam. Depois, feche e abra o Super Tool.', { rotulo: 'Atualizar' })) return;
      const x = await tentar(() => api('atualizar', {}));
      if (x) acompanharEstado();
    };
    desenhar(r.estado);
    if (r.estado && r.estado.ativo) acompanharEstado();
  }).catch(() => {});
  return caixa;
}

function tabelaVersoes() {
  const tb = el('tbody');
  tb.append(el('tr', {}, el('td', {}, 'BRFP Super Tool'), el('td', { class: 'v' }, S.versao), el('td', {}, NOVIDADES_ST)));
  for (const f of S.ferramentas) tb.append(el('tr', {}, el('td', {}, f.nome), el('td', { class: 'v' }, f.versao), el('td', {}, NOVIDADES[f.id] || '')));
  return el('table', { class: 'tabela-versoes' }, el('thead', {}, el('tr', {}, el('th', {}, 'Ferramenta'), el('th', {}, 'Versão'), el('th', {}, 'Novidades da versão'))), tb);
}

function sobre() {
  const guias = [['supertool', 'BRFP Super Tool'], ...S.ferramentas.map((f) => [f.id, f.nome])]
    .map(([id, nome]) => el('button', { class: 'btn peq', onclick: () => guia(id, nome) }, icone('ajuda', 12), nome));
  const corpo = el('div', {}, tabelaVersoes(), el('div', { class: 'acoes-linha', style: { marginTop: '12px' } }, ...guias));
  modal({ titulo: 'BRFP Super Tool', texto: `Versão ${esc(S.versao)}`, largo: true, corpo,
    botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

async function guia(id, nome) {
  const r = await tentar(() => api('guia?id=' + encodeURIComponent(id)));
  if (!r) return;
  const corpo = r.markdown ? el('div', { class: 'md', html: markdown(r.texto) }) : el('div', { class: 'texto-puro' }, r.texto);
  modal({ titulo: `Guia — ${nome}`, texto: esc(r.caminho), largo: true, corpo, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

// ---------------------------------------------------------------- RDBM 26 · Add-on FC 27 (programa nativo)
async function paginaRdbm() {
  const r = await tentar(() => api('rdbm'));
  const t = $('#tela-rdbm');
  t.innerHTML = '';
  if (!r) return;
  const p = el('div', { class: 'pagina' });
  p.append(el('div', { class: 'bv-hero' }, el('div', { class: 'ic-c', style: { width: '64px', height: '64px', borderRadius: '14px', display: 'grid', placeItems: 'center', background: 'var(--selecao-suave)', color: 'var(--selecao)' }, html: icone('bancoDados', 34) }),
    el('div', {}, el('h1', {}, r.nome, ' ', el('span', { class: 'marca-versao' }, r.versao)),
      el('p', {}, 'Abre e edita squads do FC 27 no RDBM 26 sem modificar a instalação do RDBM. É um programa à parte (Windows): o Super Tool só o abre e passa os comandos.'))));
  if (!r.existe) p.append(nota(`Não encontrei o add-on em <span class="mono">${esc(r.pasta)}</span>.`, 'alerta'));
  if (!r.rdbm_ok) p.append(nota(`O RDBM 26 não foi encontrado em <span class="mono">${esc(r.ini.rdbm_dir || '')}</span>.`, 'alerta'));
  const acao = (a, extra = {}) => async () => {
    const fim = aviso(a === 'abrir' || a === 'abrir_modo' ? 'Abrindo…' : 'Rodando o add-on…', { tipo: 'info', tempo: 60000 });
    const res = await tentar(() => api('rdbm', { acao: a, ...extra }));
    fim();
    if (res && !res.cancelado) { if (a !== 'abrir' && a !== 'abrir_modo') aviso('Pronto — o resultado está no registro abaixo', { tipo: 'sucesso' }); paginaRdbmCom(res); }
  };
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Abrir'), el('p', { class: 'dica' }, 'No RDBM: File › Open FC 26 (Ctrl+F6) lê o FC 27. O caminho da pasta de squads do FC 27 vai para a área de transferência.'))),
    el('div', { class: 'cartao-corpo' }, el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn-primario', disabled: !r.existe, onclick: acao('abrir_modo') }, icone('play', 14), 'Abrir RDBM 26 em modo FC 27'),
      el('button', { class: 'btn', disabled: !r.existe, onclick: acao('abrir') }, icone('janela', 14), 'Abrir o add-on'),
      el('button', { class: 'btn', onclick: () => tentar(() => api('abrir_pasta', { id: 'rdbm' })) }, icone('pasta', 14), 'Pasta do add-on')))));
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Verificar e atualizar'), el('p', { class: 'dica' }, 'Depois de um patch do FC 27, importe de novo o banco e o idioma exportados do jogo.'))),
    el('div', { class: 'cartao-corpo' }, el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn', disabled: !r.existe, onclick: acao('verificar') }, icone('busca', 14), 'Verificar squad…'),
      el('button', { class: 'btn', disabled: !r.existe, onclick: acao('verificar', { teste: true }) }, icone('busca', 14), 'Verificar + teste de gravação…'),
      el('button', { class: 'btn', disabled: !r.existe, onclick: acao('importar_banco') }, icone('bancoDados', 14), 'Importar banco FC 27…'),
      el('button', { class: 'btn', disabled: !r.existe, onclick: acao('importar_idioma') }, icone('relatorio', 14), 'Importar idioma FC 27…')))));
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Configuração (addon.ini)'))),
    el('div', { class: 'cartao-corpo' }, el('dl', { class: 'kv' }, ...Object.entries(r.ini).flatMap(([k, v]) => [el('dt', {}, k), el('dd', { class: 'mono' }, v)]),
      el('dt', {}, 'backups'), el('dd', {}, `${r.backups} na pasta backups`)))));
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Registro (addon.log)'))),
    el('div', { class: 'cartao-corpo' }, el('div', { class: 'console', id: 'rdbm-log', style: { maxHeight: '300px' } }, (r.log || []).join('\n') || '(vazio)'))));
  p.append(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: () => guia('rdbm', r.nome) }, icone('ajuda', 12), 'Guia completo (LEIA-ME)')));
  t.append(p);
}
function paginaRdbmCom(r) {
  const log = $('#rdbm-log');
  if (log) { log.textContent = (r.log || []).join('\n') || '(vazio)'; log.scrollTop = log.scrollHeight; }
}

// ---------------------------------------------------------------- dados do jogo (banco e idioma compartilhados)
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');

function faixaDados() {
  const d = S.dados || {};
  const f = el('div', { class: 'faixa-dados' });
  const b = d.banco, i = d.idioma;
  f.append(el('button', { class: `chip ${b ? 'ok' : d.erro_banco ? 'erro' : ''}`, title: b ? b.caminho : d.erro_banco || 'Importar o banco do jogo', onclick: () => abrir('dados') },
    icone('bancoDados', 13), b ? `Banco: ${b.nome_jogo} · ${fmt(b.contagens.teams)} times · ${fmt(b.contagens.players)} jogadores` : d.erro_banco ? 'Banco com erro' : 'Nenhum banco importado'));
  f.append(el('button', { class: `chip ${i ? 'ok' : d.erro_idioma ? 'erro' : ''}`, title: i ? i.arquivos.join('\n') : d.erro_idioma || 'Importar o idioma', onclick: () => abrir('dados') },
    icone('idioma', 13), i ? `Idioma: ${fmt(i.textos)} textos` : d.erro_idioma ? 'Idioma com erro' : 'Nenhum idioma importado'));
  const c = S.comp;
  if (c) {
    const faltam = Object.values(c.grupos).filter((g) => !g.ok);
    const ok = c.python.ok && !faltam.length;
    f.append(el('button', { class: `chip ${ok ? 'ok' : 'aviso'}`, title: 'Python embutido e pacotes das ferramentas', onclick: () => abrir('componentes') },
      icone('chip', 13), !c.python.ok ? 'Python embutido não baixado' : ok ? `Componentes: Python ${c.python.versao} · pacotes prontos`
        : `Faltam pacotes: ${faltam.map((g) => g.nome).join(', ')}`));
  }
  return f;
}

async function acaoDados(rota, corpo, msg) {
  const fim = aviso(msg, { tipo: 'info', tempo: 120000 });
  try {
    const r = await api(rota, corpo);
    fim();
    if (!r.cancelado) {
      S.dados = r;
      if (r.faltam && r.faltam.length) aviso(`Banco importado, mas sem as tabelas: ${r.faltam.join(', ')}`, { tipo: 'aviso' });
      else aviso(rota === 'dados_remover' ? 'Removido' : 'Pronto', { tipo: 'sucesso', tempo: 2200, detalhe: 'As ferramentas passam a usar estes dados.' });
      S.nav = { aba: S.nav.aba, tabela: null, time: null, busca: '', ini: 0 };
    }
  } catch (e) { fim(); aviso(e.message, { tipo: 'erro' }); }
  await paginaDados();
}

async function paginaDados() {
  S.dados = await api('dados').catch(() => S.dados);
  const d = S.dados || {};
  const t = $('#tela-dados');
  t.innerHTML = '';
  const p = el('div', { class: 'pagina', style: { maxWidth: '1180px' } });
  p.append(el('div', { class: 'bv-hero' }, el('div', { class: 'ic-c', style: { width: '64px', height: '64px', borderRadius: '14px', display: 'grid', placeItems: 'center', background: 'var(--acento-suave)', color: 'var(--acento)' }, html: icone('bancoDados', 34) }),
    el('div', {}, el('h1', {}, 'Dados do jogo'),
      el('p', {}, 'Importe o banco de dados e o idioma uma vez: todas as ferramentas passam a usar. O Editor de Compdata mostra os nomes de times e competições, o Criador de Minifaces liga as fotos aos jogadores de cada time e o Conversor de Tabelas parte deste banco.'))));
  const b = d.banco, i = d.idioma;
  const corpoB = el('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  if (b) {
    const selJogo = el('select', { class: 'seletor', onchange: (e) => acaoDados('dados_jogo', { jogo: e.target.value }, 'Gravando…') },
      ...(d.jogos || []).map(({ id, nome }) => { const o = el('option', { value: id }, nome); o.selected = (b.jogo || '').replace('~', '') === id; return o; }));
    corpoB.append(el('dl', { class: 'kv' },
      el('dt', {}, 'Origem'), el('dd', { class: 'mono' }, b.caminho),
      el('dt', {}, 'Tipo'), el('dd', {}, b.tipo === 'db' ? (b.meta_guardado ? `banco t3db (sem meta ao lado: usando o esquema guardado do ${b.nome_jogo})` : 'banco t3db (.db + meta)') : 'pasta de tabelas .txt'),
      el('dt', {}, 'Jogo'), el('dd', {}, selJogo, el('span', { class: 'mudo', style: { marginLeft: '8px' } }, 'identificado pelas tabelas; troque se estiver errado')),
      el('dt', {}, 'Tabelas'), el('dd', {}, fmt(b.tabelas)),
      el('dt', {}, 'Conteúdo'), el('dd', {}, `${fmt(b.contagens.players)} jogadores · ${fmt(b.contagens.teams)} times · ${fmt(b.contagens.leagues)} ligas`),
      el('dt', {}, 'Importado em'), el('dd', {}, b.importado_em || '—')));
  } else {
    corpoB.append(d.erro_banco ? nota(esc(d.erro_banco), 'erro') : nota('Nenhum banco importado. Use o <b>fifa_ng_db.db</b> (com o <b>fifa_ng_db-meta.xml</b> na mesma pasta) ou uma pasta com as tabelas exportadas em .txt.'));
  }
  corpoB.append(el('div', { class: 'acoes-linha' },
    el('button', { class: 'btn-primario peq', onclick: () => acaoDados('dados_banco', { modo: 'arquivo' }, 'Importando o banco…') }, icone('arquivoMais', 13), 'Importar banco (.db)…'),
    el('button', { class: 'btn peq', onclick: () => acaoDados('dados_banco', { modo: 'pasta' }, 'Importando as tabelas…') }, icone('pastaMais', 13), 'Importar pasta de tabelas…'),
    b ? el('button', { class: 'btn-fantasma peq', onclick: () => acaoDados('dados_remover', { qual: 'banco' }, 'Removendo…') }, icone('x', 12), 'Remover') : null));
  const corpoI = el('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  if (i) {
    corpoI.append(el('dl', { class: 'kv' },
      el('dt', {}, 'Arquivos'), el('dd', { class: 'mono' }, i.arquivos.join('\n')),
      el('dt', {}, 'Textos'), el('dd', {}, fmt(i.textos)),
      el('dt', {}, 'Importado em'), el('dd', {}, i.importado_em || '—')));
  } else {
    corpoI.append(d.erro_idioma ? nota(esc(d.erro_idioma), 'erro') : nota('Nenhum idioma importado. Use os <b>LanguageStrings1.txt</b> e <b>LanguageStrings2.txt</b> exportados pelo FET (o .db de idioma do FC 27 é criptografado; o do FC 26 pode ser usado direto).'));
  }
  corpoI.append(el('div', { class: 'acoes-linha' },
    el('button', { class: 'btn-primario peq', onclick: () => acaoDados('dados_idioma', { modo: 'arquivos' }, 'Importando o idioma…') }, icone('arquivoMais', 13), 'Importar LanguageStrings / .db…'),
    el('button', { class: 'btn peq', onclick: () => acaoDados('dados_idioma', { modo: 'pasta' }, 'Importando o idioma…') }, icone('pastaMais', 13), 'Importar pasta…'),
    i ? el('button', { class: 'btn-fantasma peq', onclick: () => acaoDados('dados_remover', { qual: 'idioma' }, 'Removendo…') }, icone('x', 12), 'Remover') : null));
  const n = d.internationals;
  const corpoN = el('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  if (n) {
    corpoN.append(el('dl', { class: 'kv' },
      el('dt', {}, 'Arquivo'), el('dd', { class: 'mono' }, n.caminho),
      el('dt', {}, 'Seleções'), el('dd', {}, `${fmt(n.masculinas)} masculinas · ${fmt(n.femininas)} femininas`),
      el('dt', {}, 'Convocação'), el('dd', {}, Object.entries(n.squad || {}).map(([g, [a, b]]) => `${g} ${a}–${b}`).join(' · ') + ` · até ${n.idade_maxima} anos`),
      el('dt', {}, 'Importado em'), el('dd', {}, n.importado_em || '—')));
  } else {
    corpoN.append(d.erro_internationals ? nota(esc(d.erro_internationals), 'erro') : nota('Nenhum internationals.txt importado. Ele fica fora do banco (pasta do mod ou exportado pelo FET) e lista as seleções do modo carreira: o <b>Criador de Ligas e Times</b> acrescenta as seleções novas nele e usa os mínimos e máximos de convocados por posição.'));
  }
  corpoN.append(el('div', { class: 'acoes-linha' },
    el('button', { class: 'btn-primario peq', onclick: () => acaoDados('dados_internationals', { modo: 'arquivo' }, 'Importando o internationals…') }, icone('arquivoMais', 13), 'Importar internationals.txt…'),
    n ? el('button', { class: 'btn-fantasma peq', onclick: () => acaoDados('dados_remover', { qual: 'internationals' }, 'Removendo…') }, icone('x', 12), 'Remover') : null));
  p.append(el('div', { class: 'cartoes-dados' },
    el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Banco de dados'), el('p', { class: 'dica' }, 'fifa_ng_db: jogadores, times, ligas…'))), corpoB),
    el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Idioma'), el('p', { class: 'dica' }, 'Nomes de competições, times, ligas e textos do jogo'))), corpoI),
    el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Internationals'), el('p', { class: 'dica' }, 'internationals.txt: seleções do modo carreira e convocação'))), corpoN)));
  if (b) p.append(await navegador());
  t.append(p);
}

async function navegador() {
  const box = el('div', { class: 'bv-bloco' });
  const abas = el('nav', { class: 'abas' });
  for (const [k, rot, ic] of [['tabelas', 'Tabelas', 'tabela'], ['times', 'Times e jogadores', 'torcida']]) {
    abas.append(el('button', { class: `aba ${S.nav.aba === k ? 'ativa' : ''}`, onclick: () => { S.nav.aba = k; paginaDados(); } }, icone(ic, 14), rot));
  }
  box.append(abas);
  const nav = el('div', { class: 'navegador' });
  box.append(nav);
  if (S.nav.aba === 'tabelas') await navTabelas(nav); else await navTimes(nav);
  return box;
}

async function navTabelas(nav) {
  const r = await api('dados_tabelas').catch((e) => { aviso(e.message, { tipo: 'erro' }); return { tabelas: [] }; });
  const busca = el('input', { type: 'search', placeholder: 'Buscar tabela…', spellcheck: 'false' });
  const itens = el('div', { class: 'itens' });
  const g = el('div', { class: 'nav-grade' });
  const desenhar = () => {
    itens.innerHTML = '';
    const q = busca.value.trim().toLowerCase();
    for (const t of r.tabelas.filter((x) => !q || x.nome.toLowerCase().includes(q))) {
      itens.append(el('button', { class: `nav-item ${S.nav.tabela === t.nome ? 'sel' : ''}`, onclick: () => { S.nav.tabela = t.nome; S.nav.ini = 0; S.nav.busca = ''; desenhar(); grade(); } },
        icone('tabela', 13), el('span', { class: 'cresce' }, t.nome), el('small', {}, fmt(t.registros))));
    }
  };
  const grade = async () => {
    g.innerHTML = '';
    if (!S.nav.tabela) { g.append(el('div', { class: 'vazio' }, `${fmt(r.tabelas.length)} tabelas. Escolha uma para ver os registros.`)); return; }
    const filtro = el('input', { type: 'search', class: 'entrada', style: { width: '220px' }, placeholder: 'Filtrar registros…', value: S.nav.busca });
    const dados = await api(`dados_tabela?nome=${encodeURIComponent(S.nav.tabela)}&ini=${S.nav.ini}&n=200&busca=${encodeURIComponent(S.nav.busca)}`).catch((e) => { aviso(e.message, { tipo: 'erro' }); return null; });
    if (!dados) return;
    filtro.onchange = () => { S.nav.busca = filtro.value; S.nav.ini = 0; grade(); };
    const ant = el('button', { class: 'btn-icone peq', disabled: S.nav.ini === 0, title: 'Anteriores', onclick: () => { S.nav.ini = Math.max(0, S.nav.ini - 200); grade(); } }, icone('seta', 14));
    ant.querySelector('svg').style.transform = 'rotate(180deg)';
    const prox = el('button', { class: 'btn-icone peq', disabled: S.nav.ini + 200 >= dados.achadas, title: 'Próximos', onclick: () => { S.nav.ini += 200; grade(); } }, icone('seta', 14));
    g.append(el('header', {}, el('b', {}, dados.nome), el('span', { class: 'mudo' },
      `${fmt(dados.achadas)}${dados.achadas !== dados.total ? ' de ' + fmt(dados.total) : ''} registros · ${dados.campos.length} campos · ${fmt(Math.min(dados.ini + 1, dados.achadas))}–${fmt(Math.min(dados.ini + 200, dados.achadas))}`), filtro, ant, prox));
    const th = dados.campos.map((c) => {
      const inf = dados.info[c] || {};
      const tipo = (inf.tipo || '').replace(/^(DBO)?FIELDTYPE_/, '').toLowerCase();
      return el('th', { class: inf.chave ? 'chave' : '', title: inf.tipo ? `${tipo} · ${inf.low}…${inf.high}` : '' }, c, tipo ? el('small', {}, inf.chave ? 'chave' : tipo) : null);
    });
    const tb = el('tbody', {}, ...dados.linhas.map((l) => el('tr', {}, ...l.map((v) => el('td', { title: v }, v)))));
    g.append(el('div', { class: 'rolagem' }, el('table', { class: 'grade-dados' }, el('thead', {}, el('tr', {}, ...th)), tb)));
  };
  busca.oninput = desenhar;
  nav.append(el('div', { class: 'nav-lista' }, el('div', { class: 'busca-linha' }, el('label', { class: 'campo-busca' }, icone('busca', 14), busca)), itens), g);
  desenhar();
  grade();
}

async function navTimes(nav) {
  const r = await api('dados_times').catch((e) => { aviso(e.message, { tipo: 'erro' }); return { times: [] }; });
  const busca = el('input', { type: 'search', placeholder: 'Buscar time ou liga…', spellcheck: 'false' });
  const itens = el('div', { class: 'itens' });
  const g = el('div', { class: 'nav-grade' }, el('div', { class: 'vazio' }, `${fmt(r.times.length)} times. Escolha um para ver o elenco.`));
  const elenco = async (t) => {
    const j = await api('dados_jogadores?teamid=' + t.teamid).catch((e) => { aviso(e.message, { tipo: 'erro' }); return null; });
    if (!j) return;
    g.innerHTML = '';
    g.append(el('header', {}, el('b', {}, t.nome), el('span', { class: 'mudo' }, `${t.liga || 'sem liga'} · ${j.jogadores.length} jogadores · teamid ${t.teamid}`)));
    const tb = el('tbody', {}, ...j.jogadores.map((x) => el('tr', {}, el('td', {}, x.camisa_num), el('td', {}, x.nome), el('td', {}, `${x.primeiro} ${x.sobrenome}`.trim()), el('td', {}, x.playerid), el('td', {}, x.overall))));
    g.append(el('div', { class: 'rolagem' }, el('table', { class: 'grade-dados' },
      el('thead', {}, el('tr', {}, ...['Nº', 'Nome', 'Nome completo', 'playerid', 'Geral'].map((c) => el('th', {}, c)))), tb)));
  };
  const desenhar = () => {
    itens.innerHTML = '';
    const q = busca.value.trim().toLowerCase();
    for (const t of r.times.filter((x) => !q || `${x.nome} ${x.liga} ${x.teamid}`.toLowerCase().includes(q)).slice(0, 600)) {
      itens.append(el('button', { class: `nav-item ${S.nav.time === t.teamid ? 'sel' : ''}`, title: t.liga, onclick: () => { S.nav.time = t.teamid; desenhar(); elenco(t); } },
        icone('trofeu', 13), el('span', { class: 'cresce' }, t.nome), el('small', {}, t.teamid)));
    }
  };
  busca.oninput = desenhar;
  nav.append(el('div', { class: 'nav-lista' }, el('div', { class: 'busca-linha' }, el('label', { class: 'campo-busca' }, icone('busca', 14), busca)), itens), g);
  desenhar();
}

// ---------------------------------------------------------------- componentes (Python embutido, pacotes, programas, pacote)
const NOMES_PAC = { numpy: 'numpy', scipy: 'SciPy', opencv: 'OpenCV', pillow: 'Pillow' };
let acompanhando = false;

async function instalarComp(corpo, rotulo) {
  if (acompanhando) return;
  try { await api('componentes_instalar', corpo); } catch (e) { aviso(e.message, { tipo: 'erro' }); return; }
  await paginaComponentes();
  acompanharTarefa(rotulo);
}

async function acompanharTarefa(rotulo = 'Componentes instalados') {
  if (acompanhando) return;
  acompanhando = true;
  const { tarefa } = await acompanhar('componentes', (t, info) => {
    S.comp = info;
    const b = $('#comp-tarefa');
    if (b && b._prog) b._prog.atualizar(t);
  });
  acompanhando = false;
  if (tarefa.fase === 'erro') aviso(tarefa.erro || 'A instalação falhou', { tipo: 'erro', tempo: 9000 });
  else if (tarefa.fase === 'pronto') aviso(rotulo, { tipo: 'sucesso', detalhe: tarefa.msg });
  if (S.ativo === 'componentes') await paginaComponentes();
}

let acompanhandoPacote = false;
async function acompanharPacote() {
  if (acompanhandoPacote) return;
  acompanhandoPacote = true;
  for (;;) {
    await new Promise((r) => setTimeout(r, 500));
    const info = await api('componentes').catch(() => null);
    if (!info) continue;
    S.comp = info;
    const p = info.pacote;
    const caixa = $('#pacote-prog');
    if (caixa && caixa._prog) caixa._prog.atualizar({ ativa: p.ativo, fase: p.fase === 'compactando' ? 'baixando' : p.fase, msg: p.fase === 'compactando' ? `Compactando… ${p.msg}` : p.msg, baixado: p.feito, total: p.total });
    if (!p.ativo) break;
  }
  acompanhandoPacote = false;
  const p = S.comp.pacote;
  if (p.fase === 'erro') aviso(p.erro, { tipo: 'erro', tempo: 9000 });
  else if (p.fase === 'pronto') aviso('Pacote gerado', { tipo: 'sucesso', detalhe: `${p.arquivo} (${mb(p.tamanho)})`, acao: { rotulo: 'Mostrar', fn: () => tentar(() => api('pacote_abrir', {})) } });
  if (S.ativo === 'componentes') await paginaComponentes();
}

function linhaPrograma(pr) {
  const est = pr.ok ? (pr.aviso ? 'aviso' : 'ok') : pr.obrigatorio ? 'erro' : 'falta';
  const acoes = el('div', { class: 'acoes-prog' });
  if (pr.localizar) acoes.append(el('button', { class: 'btn peq', onclick: async () => { const r = await tentar(() => api('componentes_local', { programa: pr.id })); if (r && !r.cancelado) { S.comp = r; paginaComponentes(); } } }, icone('pasta', 12), 'Localizar…'));
  if (pr.link && !pr.ok) acoes.append(el('a', { class: 'btn peq', href: pr.link, target: '_blank', rel: 'noopener' }, icone('baixar', 12), 'Baixar'));
  return el('div', { class: `prog-linha ${est}` },
    el('span', { class: 'prog-ic', html: icone(pr.ok ? (pr.aviso ? 'aviso' : 'check') : 'aviso', 15) }),
    el('div', { class: 'prog-txt' }, el('b', {}, pr.nome), el('small', {}, `${pr.detalhe}${pr.usado ? ' · usado por: ' + pr.usado : ''}`),
      pr.caminho ? el('span', { class: 'mono prog-cam' }, pr.caminho) : null),
    acoes);
}

async function paginaComponentes() {
  S.comp = await api('componentes').catch((e) => { aviso(e.message, { tipo: 'erro' }); return S.comp; });
  const c = S.comp;
  const t = $('#tela-componentes');
  t.innerHTML = '';
  if (!c) return;
  const p = el('div', { class: 'pagina', style: { maxWidth: '1100px' } });
  p.append(el('div', { class: 'bv-hero' }, el('div', { class: 'ic-c', style: { width: '64px', height: '64px', borderRadius: '14px', display: 'grid', placeItems: 'center', background: 'var(--acento-suave)', color: 'var(--acento)' }, html: icone('chip', 34) }),
    el('div', {}, el('h1', {}, 'Componentes'),
      el('p', {}, 'Tudo de que o Super Tool precisa fica dentro da pasta dele: um Python próprio (runtime\\python) e os pacotes de cada ferramenta. Nada é instalado no Windows. Programas de fora, como o Blender e o RDBM 26, são procurados no computador.'))));
  if (c.problema) p.append(nota(esc(c.problema), 'erro'));
  const t0 = c.tarefa || {};
  if (t0.ativa) {
    const prog = barraTarefa();
    prog.atualizar(t0);
    const caixa = el('div', { class: 'cartao', id: 'comp-tarefa' }, el('header', {}, el('div', {}, el('h3', {}, 'Instalando'), el('p', { class: 'dica' }, t0.externa ? 'Iniciado por uma ferramenta aberta.' : 'Pode continuar usando o Super Tool enquanto isso.'))),
      el('div', { class: 'cartao-corpo' }, prog.el));
    caixa._prog = prog;
    p.append(caixa);
    setTimeout(() => acompanharTarefa(), 0);
  }

  // Python embutido
  const py = c.python;
  const corpoPy = el('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  if (py.ok) {
    corpoPy.append(el('dl', { class: 'kv' },
      el('dt', {}, 'Versão'), el('dd', {}, `Python ${py.versao} (python.org, pacote “embeddable”, isolado)`),
      el('dt', {}, 'Pasta'), el('dd', { class: 'mono' }, py.caminho),
      el('dt', {}, 'Em uso'), el('dd', {}, py.em_uso ? 'sim — o Super Tool e as ferramentas rodam nele' : `não — o Super Tool foi aberto com o Python ${c.python_atual.versao} do computador`)));
    if (!py.em_uso) corpoPy.append(nota('Feche o Super Tool e abra de novo pelo <b>BRFP Super Tool.bat</b> para usar o Python embutido.', 'info'));
  } else {
    corpoPy.append(nota(`O Python embutido ainda não foi baixado. O Super Tool está rodando no Python ${esc(c.python_atual.versao)} do computador (<span class="mono">${esc(c.python_atual.caminho)}</span>).`, 'alerta'),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', disabled: !!t0.ativa || !!c.problema, onclick: () => instalarComp({ tipo: 'python' }, 'Python embutido baixado') }, icone('baixar', 13), `Baixar o Python ${py.esperada} (${mb(py.tamanho)})`)));
  }

  // pacotes por ferramenta
  const corpoPac = el('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '8px' } });
  const inst = Object.fromEntries(c.pacotes.map((x) => [x.id, x]));
  for (const g of Object.values(c.grupos)) {
    const falta = g.faltam.concat(g.desatualizados);
    corpoPac.append(el('div', { class: `prog-linha ${g.ok ? 'ok' : 'falta'}` },
      el('span', { class: 'prog-ic', html: icone(g.ok ? 'check' : 'baixar', 15) }),
      el('div', { class: 'prog-txt' }, el('b', {}, g.nome),
        // grupos grandes (o servidor da Transfermarkt tem 24 bibliotecas) mostram o resumo em vez da lista
        el('small', {}, g.resumo || g.pacotes.map((id) => `${NOMES_PAC[id] || id} ${inst[id]?.instalado || '—'}`).join(' · ')),
        g.usado_por ? el('span', { class: 'mudo' }, `usado por: ${[].concat(g.usado_por).join(', ')}`) : null,
        !g.ok ? el('span', { class: 'mudo' }, `falta: ${g.resumo ? `${falta.length + (g.faltam_projetos || []).length} de ${g.pacotes.length + (g.projetos || []).length} itens` : falta.map((id) => NOMES_PAC[id] || id).join(', ')} — ${mb(g.download)}`) : null),
      el('div', { class: 'acoes-prog' }, g.ok
        ? el('button', { class: 'btn-fantasma peq', disabled: !!t0.ativa, title: 'Baixa e instala de novo (feche a ferramenta antes)', onclick: () => instalarComp({ ids: [g.id], forcar: true }, 'Pacotes reinstalados') }, icone('recarregar', 12), 'Reinstalar')
        : el('button', { class: 'btn-primario peq', disabled: !!t0.ativa || !!c.problema, onclick: () => instalarComp({ ids: [g.id] }, `Pacotes do ${g.nome} instalados`) }, icone('baixar', 12), `Instalar (${mb(g.download)})`))));
  }
  const faltaTudo = c.pacotes.filter((x) => x.instalado !== x.versao).reduce((s, x) => s + x.tamanho, 0)
    + (c.projetos || []).filter((x) => x.instalado !== x.versao).reduce((s, x) => s + x.tamanho, 0);
  corpoPac.append(el('div', { class: 'acoes-linha' },
    faltaTudo ? el('button', { class: 'btn peq', disabled: !!t0.ativa || !!c.problema, onclick: () => instalarComp({ ids: ['tudo'] }, 'Todos os pacotes instalados') }, icone('baixar', 12), `Instalar tudo (${mb(faltaTudo)})`) : null,
    el('span', { class: 'mudo', style: { fontSize: '12px' } }, 'Versões fixas do PyPI, conferidas pelo SHA-256. As ferramentas também oferecem o download quando abrem sem eles.')));

  // programas do computador
  const corpoProg = el('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '8px' } }, ...c.programas.map(linhaPrograma));

  // pacote para outro computador
  const pk = c.pacote || {};
  const corpoZip = el('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  corpoZip.append(el('p', { class: 'mudo', style: { margin: 0, fontSize: '12.5px', lineHeight: '1.55' }, html:
    'Gera um <b>.zip</b> com a pasta <b>BRFP Super Tool</b> pronta para outro computador: é só extrair e abrir o <b>BRFP Super Tool.bat</b>. '
    + 'Leva também o motor do Conversor PES e o add-on do RDBM. <b>Não leva nada deste computador</b>: preferências, banco e idioma importados, caches, saídas e backups ficam de fora.' }));
  const resumo = el('div', { class: 'pacote-opcoes' });
  const opcao = (tipo, titulo, texto, tam) => el('div', { class: 'pacote-op' },
    el('b', {}, titulo), el('p', {}, texto), el('small', { class: 'mudo' }, tam),
    el('button', { class: tipo === 'completo' ? 'btn-primario peq' : 'btn peq', disabled: !!pk.ativo, onclick: async () => {
      const r = await tentar(() => api('pacote_gerar', { tipo }));
      if (!r || r.cancelado) return;
      await paginaComponentes();
      acompanharPacote();
    } }, icone('maleta', 13), `Gerar pacote ${tipo}…`));
  resumo.append(opcao('completo', 'Completo', 'Com o Python embutido e todos os pacotes: abre sem internet.', 'calculando o tamanho…'),
    opcao('leve', 'Leve', 'Sem o Python: na primeira vez o .bat baixa o Python (11 MB) e cada ferramenta baixa os pacotes quando precisar.', 'calculando o tamanho…'));
  corpoZip.append(resumo);
  const caixaProg = el('div', { id: 'pacote-prog' });
  if (pk.ativo || pk.fase === 'pronto' || pk.fase === 'erro') {
    const prog = barraTarefa();
    prog.atualizar({ ativa: pk.ativo, fase: pk.fase === 'compactando' ? 'baixando' : pk.fase, msg: pk.fase === 'compactando' ? `Compactando… ${pk.msg}` : pk.msg, baixado: pk.feito, total: pk.total });
    caixaProg._prog = prog;
    caixaProg.append(prog.el);
    if (pk.fase === 'pronto') caixaProg.append(el('div', { class: 'acoes-linha', style: { marginTop: '8px' } }, el('span', { class: 'mono', style: { fontSize: '12px' } }, `${pk.arquivo} · ${mb(pk.tamanho)}`),
      el('button', { class: 'btn peq', onclick: () => tentar(() => api('pacote_abrir', {})) }, icone('pasta', 12), 'Mostrar na pasta')));
    if (pk.ativo) setTimeout(acompanharPacote, 0);
  }
  corpoZip.append(caixaProg);

  p.append(el('div', { class: 'cartoes-dados' },
    el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Python embutido'), el('p', { class: 'dica' }, 'Roda o Super Tool e todas as ferramentas'))), corpoPy),
    el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Pacotes das ferramentas'), el('p', { class: 'dica' }, 'Baixados uma vez, ficam em runtime\\python'))), corpoPac)));
  p.append(el('div', { class: 'cartao', style: { marginTop: '16px' } }, el('header', {}, el('div', {}, el('h3', {}, 'Programas do computador'), el('p', { class: 'dica' }, 'Usados por algumas ferramentas; não vêm no Super Tool'))), corpoProg));
  p.append(el('div', { class: 'cartao', style: { marginTop: '16px' } }, el('header', {}, el('div', {}, el('h3', {}, 'Levar para outro computador'), el('p', { class: 'dica' }, 'Pacote .zip do Super Tool'))), corpoZip));
  t.append(p);
  api('pacote_resumo').then((r) => {
    const [a, b] = resumo.querySelectorAll('.pacote-op small');
    if (a) a.textContent = r.completo ? `≈ ${mb(r.completo * 0.45)} compactado (${mb(r.completo)} extraído)` : (r.motivo_completo || '');
    if (b) b.textContent = `≈ ${mb(r.leve * 0.6)} compactado`;
    if (!r.completo) resumo.querySelector('.pacote-op .btn-primario')?.setAttribute('disabled', '');
  }).catch(() => {});
}

// ---------------------------------------------------------------- teclado
document.addEventListener('keydown', (e) => {
  if (modalAberto()) return;
  if ((e.ctrlKey || e.metaKey) && /^[0-9]$/.test(e.key)) {
    e.preventDefault();
    const n = +e.key;
    if (n === 0) abrir('inicio');
    else if (S.ferramentas[n - 1]) abrir(S.ferramentas[n - 1].id);
  }
});
window.addEventListener('hashchange', () => { const id = location.hash.slice(1); if (id && id !== S.ativo) abrir(id); });
// uma ferramenta pede para abrir outra (ex.: o Criador de Ligas e Times manda as fotos para o Criador de Minifaces)
window.addEventListener('message', (ev) => {
  const d = ev.data || {};
  if (d.brfp !== 'abrir' || !d.id) return;
  const vem = [...S.quadros.values()].some((q) => q.contentWindow === ev.source);
  if (vem && (porId(d.id) || d.id === 'dados' || d.id === 'componentes' || d.id === 'inicio')) abrir(d.id);
});

// ---------------------------------------------------------------- início
async function iniciar() {
  $('#btn-inicio').innerHTML = icone('casa', 20);
  $('#btn-dados').innerHTML = icone('bancoDados', 20);
  $('#btn-dados').onclick = () => abrir('dados');
  dica($('#btn-dados'), 'Dados do jogo', 'banco e idioma');
  $('#btn-componentes').innerHTML = icone('chip', 20);
  $('#btn-componentes').onclick = () => abrir('componentes');
  dica($('#btn-componentes'), 'Componentes', 'Python, pacotes, programas, pacote');
  $('#btn-sobre').innerHTML = icone('info', 20);
  $('#btn-inicio').onclick = () => abrir('inicio');
  $('#btn-logo').onclick = () => abrir('inicio');
  $('#btn-sobre').onclick = sobre;
  dica($('#btn-inicio'), 'Início', 'Ctrl+0');
  dica($('#btn-sobre'), 'Versões e guias');
  const r = await api('inicio');
  S.versao = r.versao;
  S.raiz = r.raiz;
  S.pasta = r.pasta;
  S.ferramentas = r.ferramentas;
  S.dados = await api('dados').catch(() => null);
  S.comp = await api('componentes').catch(() => null);
  desenharInicio();
  const alvo = location.hash.slice(1);
  if (alvo && alvo !== 'inicio' && (porId(alvo) || alvo === 'dados' || alvo === 'componentes')) abrir(alvo);
  else mostrar('inicio');
  setInterval(atualizar, 3000);
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
