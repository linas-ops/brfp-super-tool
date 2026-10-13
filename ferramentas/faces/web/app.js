// Conversor de Faces FC 26 ↔ FC 27 — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, confirmar, barraMenus, abrirMenu, divisorArrastavel, dialogoSobre, interruptor, nota, modalAberto, menuAberto, lerArquivoBase64 } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { instalarComponentes } from './comum/componentes.js';
import { importarReferencias, notaReferencias } from './comum/referencias.js';
import { Previa } from './previa.js';

const S = { itens: [], job: {}, opcoes: {}, ambiente: {}, referencias: {}, raizes: {}, sel: null, versao: '', qual: 'entrada', previa: null, polling: null, ultimoResumo: null };
const NOME_JOGO = { fc26: 'FC 26', fc27: 'FC 27' };
const EST = {
  pronto: ['ponto', 'Pronta para converter'], na_fila: ['relogio', 'Na fila'], convertendo: ['recarregar', 'Convertendo…'],
  ok: ['check', 'Convertida'], erro: ['aviso', 'Erro'], ignorado: ['menos', 'Ignorada'],
};

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }
const nomeArq = (c) => (c || '').split(/[\\/]/).filter(Boolean).pop() || '';
const jogoTag = (j) => el('span', { class: `jogo ${j || 'nada'}` }, NOME_JOGO[j] || '—');

// ---------------------------------------------------------------- estado
function aplicar(r) {
  if (!r) return;
  if (r.itens) S.itens = r.itens;
  if (r.job) S.job = r.job;
  if (r.opcoes) S.opcoes = r.opcoes;
  if (r.ambiente) S.ambiente = r.ambiente;
  if (r.referencias) S.referencias = r.referencias;
  if (r.raizes) S.raizes = r.raizes;
  if (S.sel !== null && !S.itens.some((i) => i.id === S.sel)) S.sel = null;
  if (S.sel === null && S.itens.length) S.sel = S.itens[0].id;
  desenharLista();
  desenharTopo();
  desenharPropriedades();
  desenharStatus();
  $('#vazio-vista').hidden = S.itens.length > 0;
  $('#barra-vista').hidden = !S.itens.length;
  const bRes = document.querySelector('#seg-qual [data-qual="saida"]');
  bRes.disabled = !itemSel()?.saida_feita;
  bRes.title = bRes.disabled ? 'Converta esta face para ver o resultado' : 'Malha convertida (Tab alterna)';
  if (S.job.rodando) iniciarPolling();
  // fim de uma conversão: aviso com o resumo
  if (!S.job.rodando && S.job.resumo && S.job.fim && S.job.fim !== S.ultimoResumo) {
    const primeiro = S.ultimoResumo === null && !S._acompanhando;
    S.ultimoResumo = S.job.fim;
    if (!primeiro) {
      const rs = S.job.resumo;
      aviso(rs.erros ? `Conversão terminou com ${rs.erros} erro(s)` : `${rs.convertidos} face(s) convertida(s)`, {
        tipo: rs.erros ? 'erro' : 'sucesso', tempo: 7000,
        detalhe: `${rs.copiados ? rs.copiados + ' arquivo(s) copiados · ' : ''}${rs.avisos ? rs.avisos + ' aviso(s) · ' : ''}${rs.segundos} s`,
        acao: rs.pastas && rs.pastas.length ? { rotulo: 'Abrir saída', fn: () => tentar(() => api('abrir', { caminho: rs.pastas[0] })) } : null,
      });
      S._acompanhando = false;
      if (S.qual === 'saida') carregarPrevia();
    }
  }
}

async function atualizar() { aplicar(await tentar(() => api('estado'))); }

function iniciarPolling() {
  if (S.polling) return;
  S._acompanhando = true;
  S.polling = setInterval(async () => {
    const r = await api('estado').catch(() => null);
    if (!r) return;
    aplicar(r);
    if (!r.job.rodando) { clearInterval(S.polling); S.polling = null; }
  }, 600);
}

// ---------------------------------------------------------------- lista
function filtrados() {
  const q = $('#busca').value.trim().toLowerCase();
  const f = $('#filtro').value;
  return S.itens.filter((it) => {
    if (q && !`${it.rel} ${it.id_jogador || ''} ${it.caminho}`.toLowerCase().includes(q)) return false;
    if (f === 'fc26' || f === 'fc27') return it.jogo === f;
    if (f === 'feitas') return it.estado === 'ok';
    if (f === 'problemas') return it.estado === 'erro' || !!it.erro || (it.motivo && it.jogo) || (it.avisos || []).length;
    return true;
  });
}

function desenharLista() {
  const lista = $('#lista');
  lista.innerHTML = '';
  const itens = filtrados();
  if (!S.itens.length) {
    lista.append(el('div', { class: 'arvore-vazia' }, 'Nenhuma face na lista.', el('br'), 'Arraste .fbx para a janela ou use os botões acima.'));
    return;
  }
  if (!itens.length) { lista.append(el('div', { class: 'arvore-vazia' }, 'Nada com esse filtro.')); return; }
  // agrupa por pasta de origem
  const grupos = new Map();
  for (const it of itens) {
    const g = it.recebido ? 'Arrastados para a janela' : it.de_pasta ? it.raiz : 'Arquivos avulsos';
    if (!grupos.has(g)) grupos.set(g, []);
    grupos.get(g).push(it);
  }
  for (const [g, its] of grupos) {
    if (grupos.size > 1 || its[0].de_pasta) {
      const outros = S.raizes[g];
      lista.append(el('div', { class: 'grupo-lista', title: g }, el('span', {}, its[0].de_pasta ? nomeArq(g) : g),
        el('span', {}, `${its.length}${outros ? ` + ${outros} outros` : ''}`)));
    }
    for (const it of its) lista.append(linhaFace(it));
  }
}

function linhaFace(it) {
  const [ic, rot] = EST[it.estado] || EST.pronto;
  const comAviso = it.estado === 'ok' && (it.avisos || []).length;
  const estCls = comAviso ? 'est-aviso' : `est-${it.estado}`;
  const estado = it.estado === 'pronto' && it.motivo ? ['menos', it.motivo] : [comAviso ? 'aviso' : ic, comAviso ? `Convertida com ${it.avisos.length} aviso(s)` : (it.mensagem || rot)];
  const sub = el('small', {});
  if (it.jogo) {
    sub.append(jogoTag(it.jogo));
    if (it.destino && it.destino !== it.jogo) sub.append(el('span', { html: icone('seta', 11) }), jogoTag(it.destino));
    sub.append(el('span', {}, it.id_jogador ? `ID ${it.id_jogador}` : 'sem ID'));
  } else sub.append(el('span', {}, it.erro ? 'FBX ilegível' : 'não é cabeça'));
  return el('button', { class: `face ${S.sel === it.id ? 'sel' : ''}`, role: 'option', 'data-id': it.id, onclick: () => selecionar(it.id),
    oncontextmenu: (e) => { e.preventDefault(); selecionar(it.id); menuItem(e.clientX, e.clientY, it); } },
  el('span', { class: 'ic-face', html: icone('rosto', 18) }),
  el('span', { class: 'txt' }, el('b', { title: it.caminho }, it.rel), sub),
  el('span', { class: `est ${it.motivo && it.estado === 'pronto' ? 'est-ignorado' : estCls}`, title: estado[1],
    html: icone(estado[0], 15, it.estado === 'convertendo' ? 'girando' : '') }));
}

function menuItem(x, y, it) {
  abrirMenu([
    { rotulo: 'Converter esta face', icone: 'play', desabilitado: S.job.rodando || !!it.motivo, fn: () => converter([it.id]) },
    { rotulo: 'Mostrar o arquivo no Explorer', icone: 'externo', fn: () => tentar(() => api('abrir', { caminho: it.caminho })) },
    { rotulo: 'Mostrar o convertido no Explorer', icone: 'externo', desabilitado: !it.saida_feita, fn: () => tentar(() => api('abrir', { caminho: it.saida_feita })) },
    '-',
    { rotulo: 'Tirar da lista', icone: 'x', desabilitado: S.job.rodando, fn: () => remover([it.id]) },
  ], x, y);
}

function selecionar(id) {
  if (S.sel === id) return;
  S.sel = id;
  document.querySelectorAll('#lista .face').forEach((e) => e.classList.toggle('sel', +e.dataset.id === id));
  desenharPropriedades();
  const it = itemSel();
  if (S.qual === 'saida' && !(it && it.saida_feita)) definirQual('entrada', false);
  carregarPrevia();
}
const itemSel = () => S.itens.find((i) => i.id === S.sel) || null;

// ---------------------------------------------------------------- topo / status
function desenharTopo() {
  const conv = S.itens.filter((i) => !i.motivo && i.estado !== 'ok').length;
  const b = $('#btn-converter');
  b.disabled = S.job.rodando || !S.ambiente.ok || !S.itens.some((i) => !i.motivo);
  $('#contador').hidden = !conv || S.job.rodando;
  $('#contador').textContent = conv;
  $('#btn-converter-txt').textContent = S.job.rodando ? `Convertendo ${S.job.feitos}/${S.job.total}…` : 'Converter';
  $('#btn-converter-ic').innerHTML = icone(S.job.rodando ? 'recarregar' : 'play', 14, S.job.rodando ? 'girando' : '');
  $('#btn-cancelar').hidden = !S.job.rodando;
  const saida = S.opcoes.saida;
  $('#titulo').innerHTML = `<b>${S.itens.length} ${S.itens.length === 1 ? 'face' : 'faces'}</b><span class="pasta" title="${esc(saida || '')}">saída: ${esc(saida || 'ao lado de cada entrada')}</span>`;
}

function desenharStatus() {
  const c = { fc26: 0, fc27: 0, outro: 0 };
  for (const it of S.itens) c[it.jogo || 'outro']++;
  $('#status-esq').innerHTML = S.itens.length
    ? `<span><b>${c.fc26}</b> FC 26</span><span><b>${c.fc27}</b> FC 27</span>${c.outro ? `<span><b>${c.outro}</b> não são cabeça</span>` : ''}<span>${S.itens.filter((i) => i.estado === 'ok').length} convertidas</span>`
    : '<span>Arraste FBX de cabeça para a janela, ou use Arquivo › Adicionar.</span>';
  $('#status-esq').classList.add('contagem');
  const pr = $('#status-progresso');
  pr.hidden = !S.job.rodando;
  if (S.job.rodando) {
    $('#progresso-barra').style.width = `${(100 * S.job.feitos) / Math.max(1, S.job.total)}%`;
    $('#progresso-txt').textContent = `${S.job.feitos}/${S.job.total}`;
  }
  const ch = $('#chip-python');
  ch.className = 'chip ' + (S.ambiente.ok ? 'ok' : S.ambiente.msg === 'verificando…' ? '' : 'erro');
  ch.innerHTML = icone(S.ambiente.ok ? 'check' : 'aviso', 12) + (S.ambiente.ok ? 'Motor pronto' : S.ambiente.msg === 'verificando…' ? 'verificando o motor…' : 'Motor indisponível');
  ch.title = S.ambiente.msg || '';
  ch.classList.toggle('clicavel', !!S.ambiente.instalar);
  ch.onclick = S.ambiente.instalar ? componentesMotor : null;
  $('#resumo-lista').textContent = S.itens.length ? `${filtrados().length} de ${S.itens.length}` : '';
}

// ---------------------------------------------------------------- painel direito
function secao(titulo, ic, corpo, aberta = true) {
  const d = el('details', { class: 'secao' });
  d.open = aberta;
  d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo)));
  return d;
}

function desenharPropriedades() {
  const p = $('#propriedades');
  const aberto = {};
  p.querySelectorAll('details.secao').forEach((d) => { aberto[d.dataset.k] = d.open; });
  p.innerHTML = '';
  const it = itemSel();
  if (it) {
    const cab = el('div', { class: 'prop-cab' }, el('h3', { title: it.caminho }, nomeArq(it.caminho)), el('div', { class: 'sub' }, it.caminho));
    const et = el('div', { class: 'etiquetas' });
    if (it.jogo) et.append(el('span', { class: 'seta-jogo' }, jogoTag(it.jogo), icone('seta', 12), jogoTag(it.destino)));
    else et.append(el('span', { class: 'etiqueta' }, it.erro ? 'FBX ilegível' : 'não é cabeça'));
    if (it.id_jogador) et.append(el('span', { class: 'etiqueta' }, `ID ${it.id_jogador}`));
    const [, rot] = EST[it.estado] || EST.pronto;
    et.append(el('span', { class: `etiqueta ${it.estado === 'ok' ? 'verde' : it.estado === 'erro' ? 'vermelha' : it.estado === 'convertendo' ? 'azul' : ''}` }, rot));
    cab.append(et);
    p.append(cab);
    const det = [];
    if (it.jogo) {
      det.push(el('dl', { class: 'kv' },
        el('dt', {}, 'Jogo detectado'), el('dd', {}, `${NOME_JOGO[it.jogo]} — ${it.jogo === 'fc27' ? 'morph head (basehead_0)' : 'cabeça própria (head_mat + eyes_mat)'}`),
        el('dt', {}, 'Malha'), el('dd', { class: 'mono' }, it.malha || '—'),
        el('dt', {}, 'LODs'), el('dd', {}, String(it.lods)),
        el('dt', {}, 'Vértices (LOD0)'), el('dd', {}, Number(it.vertices).toLocaleString('pt-BR')),
        el('dt', {}, 'Materiais'), el('dd', {}, (it.materiais || []).join(', '))));
    } else if (it.erro) det.push(nota(`Não foi possível ler o FBX: ${esc(it.erro)}. Só FBX binário (o padrão do FET e do Blender) é lido.`, 'alerta'));
    else det.push(nota('Este FBX não tem malha <i>head_mat</i>: não é uma cabeça (cabelo, mouthbag…). Com “Copiar os outros arquivos” ligado, ele vai para a saída sem mudança quando estiver dentro de uma pasta adicionada.'));
    if (it.saida) {
      det.push(el('div', { class: 'campo' }, el('label', {}, it.estado === 'ok' ? 'Gravado em' : 'Vai ser gravado em'), el('div', { class: 'caminho-saida' }, it.saida_feita || it.saida)));
      if (it.existe && it.estado !== 'ok') det.push(nota(S.opcoes.sobrescrever ? 'Já existe um arquivo com esse nome na saída: será substituído.' : 'Já existe um arquivo com esse nome na saída: ligue <b>Sobrescrever</b> ou ele será pulado.', 'alerta'));
    }
    if (it.motivo && it.jogo) det.push(nota(esc(it.motivo), 'alerta'));
    if (it.estado === 'erro' && it.mensagem) det.push(nota(`<b>Erro:</b> <span class="mono">${esc(it.mensagem).replace(/\n/g, '<br>')}</span>`, 'erro'));
    if (it.estado === 'ignorado' && it.mensagem) det.push(nota(esc(it.mensagem)));
    if ((it.avisos || []).length) det.push(el('ul', { class: 'lista-avisos' }, ...it.avisos.map((a) => el('li', {}, a))));
    if (it.estado === 'ok') {
      det.push(el('dl', { class: 'kv' }, el('dt', {}, 'Tempo'), el('dd', {}, `${it.segundos} s`),
        el('dt', {}, 'Maior deslocamento'), el('dd', {}, it.diferenca_cm != null ? `${it.diferenca_cm} cm em relação ao modelo` : '—'),
        ...Object.entries(it.metodos || {}).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)])));
    }
    const acoes = el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', disabled: S.job.rodando || !!it.motivo || !S.ambiente.ok, onclick: () => converter([it.id]) }, icone('play', 12), 'Converter esta'),
      el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { caminho: it.saida_feita || it.caminho })) }, icone('externo', 12), it.saida_feita ? 'Mostrar convertido' : 'Mostrar arquivo'),
      el('button', { class: 'btn-fantasma peq', disabled: S.job.rodando, onclick: () => remover([it.id]) }, icone('x', 12), 'Tirar da lista'));
    det.push(acoes);
    const s1 = secao('Face selecionada', 'rosto', det);
    s1.dataset.k = 'face';
    p.append(s1);
  } else {
    p.append(el('div', { class: 'vazio' }, 'Adicione faces para ver os detalhes de cada uma aqui.'));
  }
  const s2 = secao('Saída e opções', 'engrenagem', opcoes());
  s2.dataset.k = 'opcoes';
  p.append(s2);
  const s3 = secao('Como funciona', 'ajuda', [el('div', { class: 'mudo', style: { lineHeight: '1.55', fontSize: '12px' }, html: `
    O jogo de origem de cada FBX é detectado pelas malhas (FC 27 = morph head com <i>teeth_mat</i> e 4 LODs; FC 26 = <i>head_mat</i> + <i>eyes_mat</i>, 3 LODs) e o destino é o outro jogo.<br><br>
    A saída é o modelo do jogo de destino (esqueleto, pesos, LODs e nomes da face de referência) deformado para ter o formato da face de entrada, com o nome que o FET usa:
    <span class="mono">headmorphpreset_&lt;id&gt;_0_0</span> no FC 27, <span class="mono">head_&lt;id&gt;_0_0_mesh</span> no FC 26.<br><br>
    Só cabeças masculinas (basehead_0). Cabelo e mouthbag não são convertidos.` })], false);
  s3.dataset.k = 'ajuda';
  p.append(s3);
  p.querySelectorAll('details.secao').forEach((d) => { if (d.dataset.k in aberto) d.open = aberto[d.dataset.k]; });
}

function opcoes() {
  const op = S.opcoes;
  const out = [];
  const caminho = el('input', { type: 'text', class: 'entrada mono', value: op.saida || '', placeholder: 'Ao lado de cada entrada (padrão)', spellcheck: 'false',
    onchange: (e) => salvarOpcoes({ saida: e.target.value.trim() }) });
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Pasta de saída'),
    el('div', { class: 'caminho-linha' }, caminho,
      el('button', { class: 'btn', title: 'Escolher a pasta…', onclick: escolherSaida }, icone('pasta', 14)),
      el('button', { class: 'btn', title: 'Voltar ao padrão (ao lado de cada entrada)', disabled: !op.saida, onclick: () => salvarOpcoes({ saida: '' }) }, icone('x', 14))),
    el('div', { class: 'ajuda', html: op.saida ? 'Pastas adicionadas mantêm a estrutura de subpastas (uma por jogador) dentro desta pasta.'
      : 'Padrão: “&lt;pasta&gt;_FC27” (ou _FC26) ao lado da pasta adicionada; para arquivos avulsos, “Convertidos_FC27” ao lado do arquivo.' })));
  const seg = (k, ops) => el('div', { class: 'segmentado' }, ...ops.map(([v, r]) => el('button', { class: op[k] === v ? 'ativo' : '', onclick: () => salvarOpcoes({ [k]: v }) }, r)));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Converter para'), seg('destino', [['auto', 'O outro jogo'], ['fc27', 'FC 27'], ['fc26', 'FC 26']]),
    el('div', { class: 'ajuda' }, op.destino === 'auto' ? 'Cada face vai para o jogo que ela não é.' : `Faces que já são ${NOME_JOGO[op.destino]} são puladas.`)));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Layout de textura da pele'), seg('textura', [['fc26', 'FC 26'], ['fc27', 'FC 27']]),
    el('div', { class: 'ajuda', html: op.textura === 'fc26'
      ? 'A UV da pele segue o FC 26: as texturas de face do FC 26 (<i>face_&lt;id&gt;_0_0_color</i>, normal…) servem direto no FC 27.'
      : 'A UV da pele segue o FC 27: use se as texturas já estiverem no layout do FC 27 (pescoço e faixa de baixo mudaram).' })));
  out.push(interruptor({ titulo: 'Copiar os outros arquivos', descricao: 'Texturas, cabelo etc. das pastas adicionadas vão para a saída sem mudança — pasta pronta para o Batch Import Faces. Mouthbag fica de fora no FC 27.',
    marcado: op.copiar_outros, aoMudar: (v) => salvarOpcoes({ copiar_outros: v }) }).el);
  out.push(interruptor({ titulo: 'Sobrescrever existentes', descricao: 'Substitui arquivos que já existem na saída. Desligado, eles são pulados.',
    marcado: op.sobrescrever, aoMudar: (v) => salvarOpcoes({ sobrescrever: v }) }).el);
  out.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', disabled: !op.saida, onclick: () => tentar(() => api('abrir', {})) }, icone('externo', 12), 'Abrir pasta de saída'),
    el('button', { class: 'btn peq', disabled: !(S.job.resumo && (S.job.resumo.pastas || []).length), onclick: () => tentar(() => api('relatorio', {})) }, icone('relatorio', 12), 'Relatório')));
  out.push(...notaReferencias(S.referencias, referenciasFaltando));
  if (!S.ambiente.ok && S.ambiente.msg !== 'verificando…') {
    out.push(nota(esc(S.ambiente.msg), 'alerta'));
    if (S.ambiente.instalar) out.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', onclick: componentesMotor }, icone('baixar', 12), 'Baixar os componentes…')));
  }
  return out;
}

async function referenciasFaltando() {
  await importarReferencias({ aoTerminar: () => atualizar() });
}

async function componentesMotor() {
  await instalarComponentes({ aoTerminar: () => esperarMotor() });
}

function esperarMotor() {
  // o servidor reconfere o motor depois da instalação
  const t = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (e) aplicar(e);
    if (e && (e.ambiente.ok || !e.ambiente.instalar)) clearInterval(t);
  }, 700);
  setTimeout(() => clearInterval(t), 60000);
}

async function salvarOpcoes(d) { aplicar(await tentar(() => api('opcoes', d))); }
async function escolherSaida() {
  const r = await tentar(() => api('dialogo', { modo: 'saida' }));
  if (r && r.caminhos.length) await salvarOpcoes({ saida: r.caminhos[0] });
}

// ---------------------------------------------------------------- ações
async function adicionar(modo) {
  const r = await tentar(() => api('dialogo', { modo }));
  if (!r || !r.caminhos.length) return;
  await adicionarCaminhos(r.caminhos);
}
async function adicionarCaminhos(caminhos) {
  const fim = carregando('Lendo as faces…');
  const r = await tentar(() => api('adicionar', { caminhos }));
  fim();
  if (!r) return;
  aplicar(r);
  posAdicionar(r.novos);
}
function posAdicionar(novos) {
  if (!novos) { aviso('Nada novo: esses arquivos já estão na lista.', { tipo: 'aviso' }); return; }
  const ult = S.itens[S.itens.length - novos];
  aviso(`${novos} ${novos === 1 ? 'arquivo adicionado' : 'arquivos adicionados'}`, { tipo: 'sucesso', tempo: 2200 });
  if (ult) { S.sel = null; selecionar(ult.id); desenharLista(); }
}
function carregando(txt) {
  const a = $('#carregando-previa');
  a.hidden = false;
  a.innerHTML = icone('recarregar', 15, 'girando') + esc(txt);
  return () => { a.hidden = true; };
}

async function remover(ids) {
  aplicar(await tentar(() => api('remover', { ids })));
  if (!S.itens.length && S.previa) S.previa.limpar();
  else carregarPrevia();
}
async function limpar() {
  if (!S.itens.length) return;
  if (!await confirmar('Limpar a lista?', 'Os arquivos não são apagados, só saem da lista.', { rotulo: 'Limpar' })) return;
  aplicar(await tentar(() => api('remover', { todos: true })));
  if (S.previa) S.previa.limpar();
  $('#rotulo-previa').hidden = true;
}

async function converter(ids = null) {
  if (S.job.rodando) return;
  if (!S.ambiente.ok) {
    if (S.ambiente.instalar) { componentesMotor(); return; }
    aviso(S.ambiente.msg || 'Motor indisponível', { tipo: 'erro' });
    return;
  }
  if (S.referencias.ok === false) { referenciasFaltando(); return; }
  const sem_saida = S.itens.some((i) => i.recebido && !S.opcoes.saida);
  if (sem_saida && !S.opcoes.saida) {
    aviso('Escolha a pasta de saída: arquivos arrastados para a janela não têm “pasta ao lado”.', { tipo: 'aviso' });
    await escolherSaida();
    if (!S.opcoes.saida) return;
  }
  const r = await tentar(() => api('converter', ids ? { ids } : {}));
  if (!r) return;
  S._acompanhando = true;
  aplicar(r);
  if (!r.iniciado) aviso(r.ignorados ? `Nada para converter: ${r.ignorados} face(s) puladas (veja o motivo em cada uma).` : 'Nada para converter.', { tipo: 'aviso' });
  else if (r.ignorados) aviso(`${r.ignorados} face(s) puladas (já no formato de destino, já existentes ou sem cabeça).`, { tipo: 'info' });
}
async function cancelar() { aplicar(await tentar(() => api('cancelar', {}))); }

// ---------------------------------------------------------------- prévia 3D
function definirQual(q, recarregar = true) {
  S.qual = q;
  document.querySelectorAll('#seg-qual button').forEach((b) => b.classList.toggle('ativo', b.dataset.qual === q));
  if (recarregar) carregarPrevia();
}
let pedidoPrevia = 0;
async function carregarPrevia() {
  const it = itemSel();
  const rot = $('#rotulo-previa');
  if (!it || !it.jogo) {
    if (S.previa) S.previa.limpar();
    rot.hidden = !it;
    if (it) rot.innerHTML = `<b>${esc(nomeArq(it.caminho))}</b> · sem prévia (${it.erro ? 'FBX ilegível' : 'não é cabeça'})`;
    return;
  }
  if (!S.previa) S.previa = new Previa($('#tela'));
  const qual = S.qual === 'saida' && it.saida_feita ? 'saida' : 'entrada';
  if (qual !== S.qual) definirQual(qual, false);
  const n = ++pedidoPrevia;
  const fim = carregando('Carregando a malha…');
  try {
    const r = await api(`previa?id=${it.id}&qual=${qual}`);
    if (n !== pedidoPrevia) return;
    S.previa.mostrar(r.partes, { manterCamera: S._ultimaPrevia === it.id });
    S._ultimaPrevia = it.id;
    rot.hidden = false;
    const jogo = qual === 'saida' ? it.destino : it.jogo;
    rot.innerHTML = `<b>${esc(r.arquivo)}</b> · ${qual === 'saida' ? 'resultado' : 'entrada'} · ${NOME_JOGO[jogo]} · LOD0`;
  } catch (e) {
    if (n === pedidoPrevia) aviso('Prévia: ' + e.message, { tipo: 'erro' });
  } finally { fim(); }
}

// ---------------------------------------------------------------- arrastar e soltar
function prepararSoltar() {
  let n = 0;
  const camada = $('#camada-soltar');
  const temArquivo = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  window.addEventListener('dragenter', (e) => { if (!temArquivo(e)) return; e.preventDefault(); n++; camada.hidden = false; });
  window.addEventListener('dragleave', () => { n = Math.max(0, n - 1); if (!n) camada.hidden = true; });
  window.addEventListener('dragover', (e) => { if (temArquivo(e)) e.preventDefault(); });
  window.addEventListener('drop', async (e) => {
    if (!temArquivo(e)) return;
    e.preventDefault();
    n = 0; camada.hidden = true;
    const arqs = [...e.dataTransfer.files].filter((f) => f.name.toLowerCase().endsWith('.fbx'));
    if (!arqs.length) { aviso('Solte arquivos .fbx. Para pastas inteiras, use Adicionar pasta (assim as texturas vêm junto).', { tipo: 'aviso' }); return; }
    const fim = carregando(`Recebendo ${arqs.length} arquivo(s)…`);
    try {
      const arquivos = [];
      for (const f of arqs) arquivos.push({ nome: f.name, dados: await lerArquivoBase64(f) });
      const r = await api('receber', { arquivos });
      aplicar(r);
      posAdicionar(r.novos);
      if (!S.opcoes.saida) aviso('Arquivos arrastados não têm caminho de origem: escolha a pasta de saída antes de converter.', { tipo: 'info', tempo: 6000 });
    } catch (err) { aviso(err.message, { tipo: 'erro' }); } finally { fim(); }
  });
}

// ---------------------------------------------------------------- menus / ajuda
function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { rotulo: 'Adicionar faces (.fbx)…', icone: 'arquivoMais', atalho: 'Ctrl+O', fn: () => adicionar('arquivos') },
      { rotulo: 'Adicionar pasta…', icone: 'pastaMais', atalho: 'Ctrl+Shift+O', fn: () => adicionar('pasta') },
      '-',
      { rotulo: 'Escolher pasta de saída…', icone: 'pasta', fn: escolherSaida },
      { rotulo: 'Importar referências…', icone: 'baixar', desabilitado: S.referencias.ok !== false, fn: referenciasFaltando },
      { rotulo: 'Abrir pasta de saída', icone: 'externo', desabilitado: !S.opcoes.saida, fn: () => tentar(() => api('abrir', {})) },
      { rotulo: 'Abrir relatório da última conversão', icone: 'relatorio', desabilitado: !(S.job.resumo && (S.job.resumo.pastas || []).length), fn: () => tentar(() => api('relatorio', {})) },
      '-',
      { rotulo: 'Limpar a lista', icone: 'x', desabilitado: !S.itens.length || S.job.rodando, fn: limpar },
    ]],
    ['Converter', () => [
      { rotulo: 'Converter todas', icone: 'play', atalho: 'Ctrl+Enter', desabilitado: S.job.rodando || !S.ambiente.ok, fn: () => converter() },
      { rotulo: 'Converter a selecionada', icone: 'play', desabilitado: S.job.rodando || !itemSel() || !!itemSel()?.motivo, fn: () => converter([S.sel]) },
      { rotulo: 'Parar', icone: 'parar', desabilitado: !S.job.rodando, fn: cancelar },
      '-',
      { cabecalho: 'Destino' },
      { rotulo: 'O outro jogo (automático)', marcado: S.opcoes.destino === 'auto', fn: () => salvarOpcoes({ destino: 'auto' }) },
      { rotulo: 'Tudo para FC 27', marcado: S.opcoes.destino === 'fc27', fn: () => salvarOpcoes({ destino: 'fc27' }) },
      { rotulo: 'Tudo para FC 26', marcado: S.opcoes.destino === 'fc26', fn: () => salvarOpcoes({ destino: 'fc26' }) },
    ]],
    ['Exibir', () => [
      { rotulo: 'Entrada', marcado: S.qual === 'entrada', fn: () => definirQual('entrada') },
      { rotulo: 'Resultado', marcado: S.qual === 'saida', desabilitado: !itemSel()?.saida_feita, fn: () => definirQual('saida') },
      '-',
      { rotulo: 'Girar sozinho', marcado: S.previa?.girando, fn: alternarGiro },
      { rotulo: 'Malha (arame)', marcado: S.previa?.arame, fn: alternarArame },
      { rotulo: 'Enquadrar', atalho: 'F', fn: () => S.previa?.enquadrar() },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Atalhos do teclado', icone: 'teclado', atalho: 'F1', fn: atalhos },
      { rotulo: 'Sobre o conversor', icone: 'info', fn: sobre },
    ]],
  ]);
}
function alternarGiro() { if (!S.previa) return; S.previa.definirGiro(!S.previa.girando); $('#btn-girar').classList.toggle('ativo', S.previa.girando); }
function alternarArame() { if (!S.previa) return; S.previa.definirArame(!S.previa.arame); $('#btn-arame').classList.toggle('ativo', S.previa.arame); }
function atalhos() {
  const t = el('div', { class: 'tabela-atalhos' });
  for (const [g, itens] of [['Lista', [['Adicionar faces', 'Ctrl+O'], ['Adicionar pasta', 'Ctrl+Shift+O'], ['Face anterior/próxima', '↑ / ↓'], ['Tirar da lista', 'Delete']]],
    ['Conversão', [['Converter todas', 'Ctrl+Enter']]],
    ['Prévia', [['Girar a câmera', 'arrastar'], ['Aproximar', 'roda do mouse'], ['Enquadrar', 'F'], ['Entrada / resultado', 'Tab']]]]) {
    t.append(el('h4', {}, g));
    for (const [rot, k] of itens) t.append(el('div', {}, el('span', {}, rot), el('span', { html: `<kbd>${esc(k)}</kbd>` })));
  }
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
function sobre() {
  dialogoSobre({ nome: 'Conversor de Faces FC 26 ↔ FC 27', versao: S.versao, html: `
    Converte o FBX de cabeça exportado pelo FIFA Editor Tool de um jogo para o outro: FC 26 → FC 27 (morph head
    <i>headmorphpreset_&lt;id&gt;_0_0</i>, 4 LODs, head/eyes/teeth) e FC 27 → FC 26 (<i>head_&lt;id&gt;_0_0_mesh</i>, 3 LODs).
    Usa o par de referência do Messi (pasta <i>motor/referencia</i>) como correspondência; precisão típica de 0,2 mm na pele.<br><br>
    <b>1.3</b> — sem as faces de referência (pacote leve), avisa o que falta e importa do pacote completo.<br>
    <b>1.1</b> — interface no BRFP Super Tool: lista de faces com o jogo identificado, pasta de saída, destino, layout de textura,
    copiar outros arquivos, prévia 3D da entrada e do resultado, arrastar e soltar.<br>
    <b>1.0</b> — conversor de linha de comando (arrastar para o .bat).<br><br>
    Ainda não testado no FET nem no jogo.` });
}

// ---------------------------------------------------------------- teclado
document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  const digitando = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === 'o') { e.preventDefault(); adicionar(e.shiftKey ? 'pasta' : 'arquivos'); return; }
  if (ctrl && e.key === 'Enter') { e.preventDefault(); converter(); return; }
  if (e.key === 'F1') { e.preventDefault(); atalhos(); return; }
  if (digitando) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const its = filtrados();
    const i = its.findIndex((x) => x.id === S.sel);
    const j = Math.max(0, Math.min(its.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    if (its[j]) { e.preventDefault(); selecionar(its[j].id); document.querySelector(`#lista .face[data-id="${its[j].id}"]`)?.scrollIntoView({ block: 'nearest' }); }
  } else if (e.key === 'Delete' && S.sel !== null && !S.job.rodando) { e.preventDefault(); remover([S.sel]); }
  else if (e.key.toLowerCase() === 'f') { S.previa?.enquadrar(); }
  else if (e.key === 'Tab' && document.activeElement === document.body || e.key === 'Tab' && document.activeElement.id === 'tela') {
    const it = itemSel();
    if (it && it.saida_feita) { e.preventDefault(); definirQual(S.qual === 'entrada' ? 'saida' : 'entrada'); }
  }
});

// ---------------------------------------------------------------- início
async function iniciar() {
  $('#btn-add-arq').innerHTML = icone('arquivoMais', 14);
  $('#btn-add-pasta').innerHTML = icone('pastaMais', 14);
  $('#btn-limpar').innerHTML = icone('apagar', 14);
  $('#busca-ic').innerHTML = icone('busca', 14);
  $('#soltar-ic').innerHTML = icone('rosto', 64);
  $('#btn-vazio-arq').innerHTML = icone('arquivoMais', 15) + 'Adicionar faces…';
  $('#btn-vazio-pasta').innerHTML = icone('pastaMais', 15) + 'Adicionar pasta…';
  $('#btn-cancelar').innerHTML = icone('parar', 13) + 'Parar';
  $('#btn-girar').innerHTML = icone('girar', 16);
  $('#btn-arame').innerHTML = icone('arame', 16);
  $('#btn-enquadrar').innerHTML = icone('maximizar', 16);
  $('#btn-add-arq').onclick = () => adicionar('arquivos');
  $('#btn-add-pasta').onclick = () => adicionar('pasta');
  $('#btn-vazio-arq').onclick = () => adicionar('arquivos');
  $('#btn-vazio-pasta').onclick = () => adicionar('pasta');
  $('#btn-limpar').onclick = limpar;
  $('#btn-converter').onclick = () => converter();
  $('#btn-cancelar').onclick = cancelar;
  $('#btn-girar').onclick = alternarGiro;
  $('#btn-arame').onclick = alternarArame;
  $('#btn-enquadrar').onclick = () => S.previa?.enquadrar();
  document.querySelectorAll('#seg-qual button').forEach((b) => { b.onclick = () => definirQual(b.dataset.qual); });
  $('#busca').addEventListener('input', () => { desenharLista(); desenharStatus(); });
  $('#filtro').addEventListener('change', () => { desenharLista(); desenharStatus(); });
  divisorArrastavel($('#div-esq'), '--esq', { min: 240, max: 560 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 280, max: 560, lado: 'dir' });
  prepararSoltar();
  menus();
  const r = await api('inicio');
  S.versao = r.versao;
  $('#versao').textContent = r.versao;
  S.ultimoResumo = r.job && r.job.fim ? r.job.fim : null;
  aplicar(r);
  if (S.itens.length) carregarPrevia();
  if (S.referencias.ok === false) {
    aviso('Faltam as faces de referência do jogo', { tipo: 'aviso', tempo: 10000, detalhe: 'Elas não vêm no pacote leve: importe do pacote completo para converter.',
      acao: { rotulo: 'Importar…', fn: referenciasFaltando } });
  }
  // componentes instalados por outra janela (página Componentes do Super Tool): o servidor reconfere o motor
  setInterval(async () => {
    if (S.ambiente.ok || !S.ambiente.instalar || S.job.rodando) return;
    const e = await api('estado').catch(() => null);
    if (e && (e.ambiente.ok || !e.ambiente.instalar)) aplicar(e);
  }, 4000);
  // o motor é verificado em segundo plano logo que o servidor sobe
  if (S.ambiente.msg === 'verificando…') {
    const t = setInterval(async () => {
      const e = await api('estado').catch(() => null);
      if (e && e.ambiente.msg !== 'verificando…') { clearInterval(t); aplicar(e); }
    }, 700);
  }
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
