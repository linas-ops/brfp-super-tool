// Conversor de Corpos FC 26 ↔ FC 27 — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, confirmar, barraMenus, abrirMenu, divisorArrastavel, dialogoSobre, interruptor, nota, modalAberto, menuAberto, lerArquivoBase64 } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { instalarComponentes } from './comum/componentes.js';
import { importarReferencias, notaReferencias } from './comum/referencias.js';
import { Previa } from './previa.js';

const S = { itens: [], job: {}, opcoes: {}, ambiente: {}, referencias: {}, sel: null, versao: '', qual: 'entrada', modo: '3d', previa: null, polling: null, ultimoResumo: null, malhas: {} };
const NOME_JOGO = { fc26: 'FC 26', fc27: 'FC 27' };
const EXT = ['.png', '.dds', '.tga', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'];
const EST = {
  pronto: ['ponto', 'Pronta para converter'], na_fila: ['relogio', 'Na fila'], convertendo: ['recarregar', 'Convertendo…'],
  ok: ['check', 'Convertida'], erro: ['aviso', 'Erro'], ignorado: ['menos', 'Ignorada'],
};

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }
const nomeArq = (c) => (c || '').split(/[\\/]/).filter(Boolean).pop() || '';
const jogoTag = (j) => el('span', { class: `jogo ${j || 'nada'}` }, NOME_JOGO[j] || '—');
const tipoTag = (t) => el('span', { class: `tipo-tex ${t === 'normal' ? 'normal' : ''}` }, t === 'normal' ? 'normal' : 'cor');
// tipo efetivo: a opção global manda; em "automático" vale o que foi reconhecido em cada imagem
const tipoDe = (it) => (S.opcoes.tipo && S.opcoes.tipo !== 'auto' ? S.opcoes.tipo : it.tipo) || 'cor';

// ---------------------------------------------------------------- estado
function aplicar(r) {
  if (!r) return;
  if (r.itens) S.itens = r.itens;
  if (r.job) S.job = r.job;
  if (r.opcoes) S.opcoes = r.opcoes;
  if (r.ambiente) S.ambiente = r.ambiente;
  if (r.referencias) S.referencias = r.referencias;
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
  bRes.title = bRes.disabled ? 'Converta esta textura para ver o resultado' : 'Textura convertida (Tab alterna)';
  if (S.job.rodando) iniciarPolling();
  if (!S.job.rodando && S.job.resumo && S.job.fim && S.job.fim !== S.ultimoResumo) {
    const primeiro = S.ultimoResumo === null && !S._acompanhando;
    S.ultimoResumo = S.job.fim;
    if (!primeiro) {
      const rs = S.job.resumo;
      aviso(rs.erros ? `Conversão terminou com ${rs.erros} erro(s)` : `${rs.convertidos} textura(s) convertida(s)`, {
        tipo: rs.erros ? 'erro' : 'sucesso', tempo: 7000,
        detalhe: `${rs.avisos ? rs.avisos + ' aviso(s) · ' : ''}${rs.segundos} s`,
        acao: rs.pastas && rs.pastas.length ? { rotulo: 'Abrir saída', fn: () => tentar(() => api('abrir', { caminho: rs.pastas[0] })) } : null,
      });
      S._acompanhando = false;
      // mostra o resultado da selecionada assim que fica pronto
      if (itemSel()?.saida_feita) definirQual('saida');
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
    if (q && !`${it.rel} ${it.caminho}`.toLowerCase().includes(q)) return false;
    if (f === 'fc26' || f === 'fc27') return it.origem === f;
    if (f === 'cor' || f === 'normal') return !it.erro && tipoDe(it) === f;
    if (f === 'feitas') return it.estado === 'ok';
    if (f === 'problemas') return it.estado === 'erro' || !!it.erro || !!it.motivo || it.confianca === 'baixa' || (it.avisos || []).length;
    return true;
  });
}

function desenharLista() {
  const lista = $('#lista');
  lista.innerHTML = '';
  const itens = filtrados();
  if (!S.itens.length) {
    lista.append(el('div', { class: 'arvore-vazia' }, 'Nenhuma textura na lista.', el('br'), 'Arraste imagens para a janela ou use os botões acima.'));
    return;
  }
  if (!itens.length) { lista.append(el('div', { class: 'arvore-vazia' }, 'Nada com esse filtro.')); return; }
  const grupos = new Map();
  for (const it of itens) {
    const g = it.recebido ? 'Arrastadas para a janela' : it.de_pasta ? it.raiz : 'Arquivos avulsos';
    if (!grupos.has(g)) grupos.set(g, []);
    grupos.get(g).push(it);
  }
  for (const [g, its] of grupos) {
    if (grupos.size > 1 || its[0].de_pasta) {
      lista.append(el('div', { class: 'grupo-lista', title: g }, el('span', {}, its[0].de_pasta ? nomeArq(g) : g), el('span', {}, String(its.length))));
    }
    for (const it of its) lista.append(linhaTextura(it));
  }
}

function linhaTextura(it) {
  const [ic, rot] = EST[it.estado] || EST.pronto;
  const comAviso = it.estado === 'ok' && (it.avisos || []).length;
  const estCls = comAviso ? 'est-aviso' : `est-${it.estado}`;
  const estado = it.estado === 'pronto' && it.motivo ? ['menos', it.motivo] : [comAviso ? 'aviso' : ic, comAviso ? `Convertida com ${it.avisos.length} aviso(s)` : (it.mensagem || rot)];
  const sub = el('small', {});
  if (!it.erro) {
    sub.append(jogoTag(it.origem));
    if (it.destino && it.destino !== it.origem) sub.append(el('span', { html: icone('seta', 11) }), jogoTag(it.destino));
    sub.append(tipoTag(tipoDe(it)), el('span', {}, `${it.largura}×${it.altura}`));
    if (it.confianca === 'baixa' && !it.jogo_forcado) sub.append(el('span', { class: 'duvida', title: 'Layout identificado com pouca certeza: confira (botão direito › Está no layout do…)', html: icone('aviso', 11) }));
  } else sub.append(el('span', {}, 'imagem ilegível'));
  return el('button', { class: `tex ${S.sel === it.id ? 'sel' : ''}`, role: 'option', 'data-id': it.id, onclick: () => selecionar(it.id),
    oncontextmenu: (e) => { e.preventDefault(); selecionar(it.id); menuItem(e.clientX, e.clientY, it); } },
  el('span', { class: 'ic-tex', html: icone(tipoDe(it) === 'normal' ? 'textura' : 'imagem', 18) }),
  el('span', { class: 'txt' }, el('b', { title: it.caminho }, it.rel), sub),
  el('span', { class: `est ${it.motivo && it.estado === 'pronto' ? 'est-ignorado' : estCls}`, title: estado[1],
    html: icone(estado[0], 15, it.estado === 'convertendo' ? 'girando' : '') }));
}

function menuItem(x, y, it) {
  abrirMenu([
    { rotulo: 'Converter esta textura', icone: 'play', desabilitado: S.job.rodando || !!it.motivo, fn: () => converter([it.id]) },
    '-',
    { cabecalho: 'A textura está no layout do…' },
    { rotulo: `FC 26${it.jogo === 'fc26' ? ' (identificado)' : ''}`, marcado: it.origem === 'fc26', desabilitado: !!it.erro || S.job.rodando, fn: () => forcarJogo([it.id], 'fc26') },
    { rotulo: `FC 27${it.jogo === 'fc27' ? ' (identificado)' : ''}`, marcado: it.origem === 'fc27', desabilitado: !!it.erro || S.job.rodando, fn: () => forcarJogo([it.id], 'fc27') },
    '-',
    { rotulo: 'Mostrar o arquivo no Explorer', icone: 'externo', fn: () => tentar(() => api('abrir', { caminho: it.caminho })) },
    { rotulo: 'Mostrar a convertida no Explorer', icone: 'externo', desabilitado: !it.saida_feita, fn: () => tentar(() => api('abrir', { caminho: it.saida_feita })) },
    '-',
    { rotulo: 'Tirar da lista', icone: 'x', desabilitado: S.job.rodando, fn: () => remover([it.id]) },
  ], x, y);
}

async function forcarJogo(ids, jogo) {
  aplicar(await tentar(() => api('forcar_jogo', { ids, jogo })));
  carregarPrevia();
}

function selecionar(id) {
  if (S.sel === id) return;
  S.sel = id;
  document.querySelectorAll('#lista .tex').forEach((e) => e.classList.toggle('sel', +e.dataset.id === id));
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
  $('#titulo').innerHTML = `<b>${S.itens.length} ${S.itens.length === 1 ? 'textura' : 'texturas'}</b><span class="pasta" title="${esc(saida || '')}">saída: ${esc(saida || 'ao lado de cada entrada')}</span>`;
}

function desenharStatus() {
  const c = { fc26: 0, fc27: 0, erro: 0 };
  for (const it of S.itens) c[it.erro ? 'erro' : it.origem]++;
  const est = $('#status-esq');
  if (S.job.rodando && S.job.mensagem) est.innerHTML = `<span>${icone('recarregar', 12, 'girando')} ${esc(S.job.mensagem)}</span>`;
  else est.innerHTML = S.itens.length
    ? `<span><b>${c.fc26}</b> FC 26</span><span><b>${c.fc27}</b> FC 27</span>${c.erro ? `<span><b>${c.erro}</b> ilegíveis</span>` : ''}<span>${S.itens.filter((i) => i.estado === 'ok').length} convertidas</span>`
    : '<span>Arraste texturas do corpo para a janela, ou use Arquivo › Adicionar.</span>';
  est.classList.add('contagem');
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
    if (!it.erro) et.append(el('span', { class: 'seta-jogo' }, jogoTag(it.origem), icone('seta', 12), jogoTag(it.destino)), tipoTag(tipoDe(it)));
    else et.append(el('span', { class: 'etiqueta' }, 'imagem ilegível'));
    const [, rot] = EST[it.estado] || EST.pronto;
    et.append(el('span', { class: `etiqueta ${it.estado === 'ok' ? 'verde' : it.estado === 'erro' ? 'vermelha' : it.estado === 'convertendo' ? 'azul' : ''}` }, rot));
    cab.append(et);
    p.append(cab);
    const det = [];
    if (!it.erro) {
      const seg = el('div', { class: 'segmentado' }, ...['fc26', 'fc27'].map((j) => el('button', { class: it.origem === j ? 'ativo' : '', disabled: S.job.rodando,
        title: j === it.jogo ? 'Identificado pela imagem' : 'Escolher à mão', onclick: () => forcarJogo([it.id], j) }, NOME_JOGO[j] + (j === it.jogo ? ' ✓' : ''))));
      const n = it.notas || {};
      det.push(el('div', { class: 'campo' }, el('label', {}, 'Layout da textura'), seg,
        el('div', { class: 'ajuda', html: it.jogo_forcado ? `Escolhido à mão (a identificação automática disse ${NOME_JOGO[it.jogo]}).`
          : `Identificado pelas costuras da UV: diferença de cor nas emendas ${n.fc26 ?? '?'} no FC 26 e ${n.fc27 ?? '?'} no FC 27 (menor = layout certo).` })));
      if (it.confianca === 'baixa' && !it.jogo_forcado) det.push(nota('Identificação com pouca certeza (textura lisa ou que não é do corpo?). Confira na prévia 3D e escolha o layout acima se estiver errado.', 'alerta'));
      det.push(el('dl', { class: 'kv' },
        el('dt', {}, 'Tamanho'), el('dd', {}, `${it.largura}×${it.altura}${it.canais === 4 ? ' · com alfa' : ''}`),
        el('dt', {}, 'Tipo'), el('dd', {}, tipoDe(it) === 'normal' ? 'mapa normal (as direções giram com a UV)' : 'cor (pele, tatuagens…)')));
    } else det.push(nota(`Não foi possível ler a imagem: ${esc(it.erro)}`, 'alerta'));
    if (it.saida) {
      det.push(el('div', { class: 'campo' }, el('label', {}, it.estado === 'ok' ? 'Gravada em' : 'Vai ser gravada em'), el('div', { class: 'caminho-saida' }, it.saida_feita || it.saida)));
      if (it.existe && it.estado !== 'ok') det.push(nota(S.opcoes.sobrescrever ? 'Já existe um arquivo com esse nome na saída: será substituído.' : 'Já existe um arquivo com esse nome na saída: ligue <b>Sobrescrever</b> ou ele será pulado.', 'alerta'));
    }
    if (it.motivo && !it.erro) det.push(nota(esc(it.motivo), 'alerta'));
    if (it.estado === 'erro' && it.mensagem) det.push(nota(`<b>Erro:</b> <span class="mono">${esc(it.mensagem).replace(/\n/g, '<br>')}</span>`, 'erro'));
    if (it.estado === 'ignorado' && it.mensagem) det.push(nota(esc(it.mensagem)));
    if ((it.avisos || []).length) det.push(el('ul', { class: 'lista-avisos' }, ...it.avisos.map((a) => el('li', {}, a))));
    for (const n of it.notas_saida || []) det.push(nota(esc(n)));
    if (it.estado === 'ok' && it.feito) {
      det.push(el('dl', { class: 'kv' }, el('dt', {}, 'Tempo'), el('dd', {}, `${it.segundos} s`),
        el('dt', {}, 'Resultado'), el('dd', {}, `${NOME_JOGO[it.feito.destino]} · ${it.feito.saida_px[0]}×${it.feito.saida_px[1]} · ${it.feito.tipo === 'normal' ? 'normal' : 'cor'}`)));
    }
    det.push(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', disabled: S.job.rodando || !!it.motivo || !S.ambiente.ok, onclick: () => converter([it.id]) }, icone('play', 12), 'Converter esta'),
      el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { caminho: it.saida_feita || it.caminho })) }, icone('externo', 12), it.saida_feita ? 'Mostrar convertida' : 'Mostrar arquivo'),
      el('button', { class: 'btn-fantasma peq', disabled: S.job.rodando, onclick: () => remover([it.id]) }, icone('x', 12), 'Tirar da lista')));
    const s1 = secao('Textura selecionada', 'imagem', det);
    s1.dataset.k = 'tex';
    p.append(s1);
  } else {
    p.append(el('div', { class: 'vazio' }, 'Adicione texturas para ver os detalhes de cada uma aqui.'));
  }
  const s2 = secao('Saída e opções', 'engrenagem', opcoes());
  s2.dataset.k = 'opcoes';
  p.append(s2);
  const s3 = secao('Como funciona', 'ajuda', [el('div', { class: 'mudo', style: { lineHeight: '1.55', fontSize: '12px' }, html: `
    O corpo (<i>bodyupper</i>) é o mesmo nos dois jogos, mas a UV mudou toda: no FC 26 os braços ficam nas laterais e as costas aparecem
    divididas ao lado do peito; no FC 27 os braços são duas colunas e costas e peito ficam inteiros.<br><br>
    Cada pixel do layout de destino é levado ao ponto do corpo em 3D e pintado com a cor da textura de origem naquele ponto. As tatuagens
    caem no mesmo lugar do corpo. Mapas normais têm as direções giradas junto com a UV.<br><br>
    O layout de cada imagem é identificado pelas emendas da UV (nos dois lados de uma emenda a cor tem que ser a mesma).
    A primeira conversão de cada tamanho calcula a correspondência (≈15 s em 1024, ≈45 s em 2048); depois leva 1 a 2 s por textura.` })], false);
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
    el('div', { class: 'ajuda', html: op.saida ? 'Pastas adicionadas mantêm a estrutura de subpastas dentro desta pasta.'
      : 'Padrão: “&lt;pasta&gt;_FC27” (ou _FC26) ao lado da pasta adicionada; para arquivos avulsos, “Convertidos_FC27” ao lado do arquivo. Sempre em PNG, com o mesmo nome.' })));
  const seg = (k, ops) => el('div', { class: 'segmentado' }, ...ops.map(([v, r]) => el('button', { class: op[k] === v ? 'ativo' : '', onclick: () => salvarOpcoes({ [k]: v }) }, r)));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Converter para'), seg('destino', [['auto', 'O outro jogo'], ['fc27', 'FC 27'], ['fc26', 'FC 26']]),
    el('div', { class: 'ajuda' }, op.destino === 'auto' ? 'Cada textura vai para o jogo que ela não é.' : `Texturas que já estão no ${NOME_JOGO[op.destino]} são puladas.`)));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Tamanho da saída'), seg('tamanho', [[0, 'Igual à entrada'], [1024, '1024'], [2048, '2048'], [4096, '4096']]),
    el('div', { class: 'ajuda' }, 'A textura original do jogo tem 1024×1024. Maior que a entrada não ganha detalhe, só ocupa mais espaço.')));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Tipo de textura'), seg('tipo', [['auto', 'Automático'], ['cor', 'Cor'], ['normal', 'Normal']]),
    el('div', { class: 'ajuda', html: op.tipo === 'auto' ? 'Mapa normal reconhecido pelo nome (<i>…normal</i>, <i>…_n</i>) ou pelas cores azuladas; o resto é cor.'
      : op.tipo === 'normal' ? 'Todas tratadas como mapa normal (DirectX): as direções giram junto com a UV.' : 'Todas tratadas como cor: os pixels só mudam de lugar.' })));
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
// sem os corpos de referência não dá para identificar o layout nem converter
function semReferencias() {
  if (S.referencias.ok !== false) return false;
  referenciasFaltando();
  return true;
}

async function componentesMotor() {
  await instalarComponentes({ aoTerminar: () => esperarMotor() });
}

function esperarMotor() {
  const t = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (e) aplicar(e);
    if (e && (e.ambiente.ok || !e.ambiente.instalar)) clearInterval(t);
  }, 700);
  setTimeout(() => clearInterval(t), 60000);
}

async function salvarOpcoes(d) {
  const tipoAntes = S.opcoes.tipo;
  aplicar(await tentar(() => api('opcoes', d)));
  if (S.opcoes.tipo !== tipoAntes) carregarPrevia();
}
async function escolherSaida() {
  const r = await tentar(() => api('dialogo', { modo: 'saida' }));
  if (r && r.caminhos.length) await salvarOpcoes({ saida: r.caminhos[0] });
}

// ---------------------------------------------------------------- ações
async function adicionar(modo) {
  if (semReferencias()) return;
  const r = await tentar(() => api('dialogo', { modo }));
  if (!r || !r.caminhos.length) return;
  await adicionarCaminhos(r.caminhos);
}
async function adicionarCaminhos(caminhos) {
  const fim = carregando('Lendo as texturas…');
  const r = await tentar(() => api('adicionar', { caminhos }));
  fim();
  if (!r) return;
  aplicar(r);
  posAdicionar(r.novos);
}
function posAdicionar(novos) {
  if (!novos) { aviso('Nada novo: nenhuma imagem nova (ou elas já estão na lista).', { tipo: 'aviso' }); return; }
  const ult = S.itens[S.itens.length - novos];
  const duvida = S.itens.slice(-novos).filter((i) => i.confianca === 'baixa').length;
  aviso(`${novos} ${novos === 1 ? 'textura adicionada' : 'texturas adicionadas'}`, { tipo: 'sucesso', tempo: 2600,
    detalhe: duvida ? `${duvida} com o layout identificado com pouca certeza: confira` : null });
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
  if (!S.itens.length) limparPrevia();
  else carregarPrevia();
}
function limparPrevia() {
  if (S.previa) S.previa.limpar();
  $('#plano').hidden = true;
  $('#rotulo-previa').hidden = true;
}
async function limpar() {
  if (!S.itens.length) return;
  if (!await confirmar('Limpar a lista?', 'Os arquivos não são apagados, só saem da lista.', { rotulo: 'Limpar' })) return;
  aplicar(await tentar(() => api('remover', { todos: true })));
  limparPrevia();
}

async function converter(ids = null) {
  if (S.job.rodando) return;
  if (!S.ambiente.ok) {
    if (S.ambiente.instalar) { componentesMotor(); return; }
    aviso(S.ambiente.msg || 'Motor indisponível', { tipo: 'erro' });
    return;
  }
  if (semReferencias()) return;
  if (S.itens.some((i) => i.recebido) && !S.opcoes.saida) {
    aviso('Escolha a pasta de saída: arquivos arrastados para a janela não têm “pasta ao lado”.', { tipo: 'aviso' });
    await escolherSaida();
    if (!S.opcoes.saida) return;
  }
  const r = await tentar(() => api('converter', ids ? { ids } : {}));
  if (!r) return;
  S._acompanhando = true;
  aplicar(r);
  if (!r.iniciado) aviso(r.ignorados ? `Nada para converter: ${r.ignorados} textura(s) puladas (veja o motivo em cada uma).` : 'Nada para converter.', { tipo: 'aviso' });
  else if (r.ignorados) aviso(`${r.ignorados} textura(s) puladas (já no layout de destino ou já existentes).`, { tipo: 'info' });
}
async function cancelar() { aplicar(await tentar(() => api('cancelar', {}))); }

// ---------------------------------------------------------------- prévia (3D no corpo ou plana)
function definirQual(q, recarregar = true) {
  S.qual = q;
  document.querySelectorAll('#seg-qual button').forEach((b) => b.classList.toggle('ativo', b.dataset.qual === q));
  if (recarregar) carregarPrevia();
}
function definirModo(m) {
  S.modo = m;
  document.querySelectorAll('#seg-modo button').forEach((b) => b.classList.toggle('ativo', b.dataset.modo === m));
  $('#btn-girar').disabled = $('#btn-arame').disabled = $('#btn-enquadrar').disabled = m !== '3d';
  carregarPrevia();
}
async function malha(jogo) {
  if (!S.malhas[jogo]) S.malhas[jogo] = await api(`malha?jogo=${jogo}`);
  return S.malhas[jogo];
}
let pedidoPrevia = 0;
async function carregarPrevia() {
  const it = itemSel();
  const rot = $('#rotulo-previa');
  if (!it || it.erro) {
    limparPrevia();
    rot.hidden = !it;
    if (it) rot.innerHTML = `<b>${esc(nomeArq(it.caminho))}</b> · sem prévia (imagem ilegível)`;
    return;
  }
  const qual = S.qual === 'saida' && it.saida_feita ? 'saida' : 'entrada';
  if (qual !== S.qual) definirQual(qual, false);
  const jogo = qual === 'saida' ? it.feito?.destino || it.destino : it.origem;
  const normal = qual === 'saida' ? it.feito?.tipo === 'normal' : tipoDe(it) === 'normal';
  const url = `imagem?id=${it.id}&qual=${qual}&t=${encodeURIComponent(it.saida_feita && qual === 'saida' ? S.job.fim || '' : '')}`;
  const n = ++pedidoPrevia;
  const plano = S.modo === 'plano';
  $('#plano').hidden = !plano;
  $('#tela').style.visibility = plano ? 'hidden' : '';
  const fim = carregando(plano ? 'Carregando a textura…' : 'Montando o corpo…');
  try {
    if (plano) {
      const img = $('#plano-img');
      await new Promise((ok, falha) => {
        img.onload = ok;
        img.onerror = async () => { const r = await fetch(url).then((x) => x.json()).catch(() => null); falha(new Error(r?.erro || 'Não foi possível carregar a imagem.')); };
        img.src = url;
      });
    } else {
      if (!S.previa) S.previa = new Previa($('#tela'));
      const m = await malha(jogo);
      if (n !== pedidoPrevia) return;
      const r = await fetch(url);
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).erro || 'Não foi possível carregar a textura.');
      const blob = URL.createObjectURL(await r.blob());
      if (n !== pedidoPrevia) { URL.revokeObjectURL(blob); return; }
      await S.previa.mostrar(jogo, m, blob, { normal, manterCamera: true });
      URL.revokeObjectURL(blob);
    }
    if (n !== pedidoPrevia) return;
    rot.hidden = false;
    rot.innerHTML = `<b>${esc(nomeArq(qual === 'saida' ? it.saida_feita : it.caminho))}</b> · ${qual === 'saida' ? 'resultado' : 'entrada'} · layout ${NOME_JOGO[jogo]}${plano ? '' : ' · no corpo do ' + NOME_JOGO[jogo]}`;
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
    const arqs = [...e.dataTransfer.files].filter((f) => EXT.some((x) => f.name.toLowerCase().endsWith(x)));
    if (semReferencias()) return;
    if (!arqs.length) { aviso('Solte imagens (.png, .dds, .tga, .jpg). Para pastas inteiras, use Adicionar pasta.', { tipo: 'aviso' }); return; }
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
      { rotulo: 'Adicionar texturas…', icone: 'arquivoMais', atalho: 'Ctrl+O', fn: () => adicionar('arquivos') },
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
      { rotulo: 'No corpo (3D)', marcado: S.modo === '3d', fn: () => definirModo('3d') },
      { rotulo: 'Textura plana', marcado: S.modo === 'plano', fn: () => definirModo('plano') },
      '-',
      { rotulo: 'Girar sozinho', marcado: S.previa?.girando, desabilitado: S.modo !== '3d', fn: alternarGiro },
      { rotulo: 'Malha (arame)', marcado: S.previa?.arame, desabilitado: S.modo !== '3d', fn: alternarArame },
      { rotulo: 'Enquadrar', atalho: 'F', desabilitado: S.modo !== '3d', fn: () => S.previa?.enquadrar() },
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
  for (const [g, itens] of [['Lista', [['Adicionar texturas', 'Ctrl+O'], ['Adicionar pasta', 'Ctrl+Shift+O'], ['Textura anterior/próxima', '↑ / ↓'], ['Tirar da lista', 'Delete']]],
    ['Conversão', [['Converter todas', 'Ctrl+Enter']]],
    ['Prévia', [['Girar a câmera', 'arrastar'], ['Aproximar', 'roda do mouse'], ['Enquadrar', 'F'], ['Entrada / resultado', 'Tab'], ['3D / plana', 'P']]]]) {
    t.append(el('h4', {}, g));
    for (const [rot, k] of itens) t.append(el('div', {}, el('span', {}, rot), el('span', { html: `<kbd>${esc(k)}</kbd>` })));
  }
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
function sobre() {
  dialogoSobre({ nome: 'Conversor de Corpos FC 26 ↔ FC 27', versao: S.versao, html: `
    Converte a textura do corpo (<i>bodyupper</i>: pele, tatuagens e mapa normal) entre os layouts de UV do FC 26 e do FC 27,
    passando cada pixel pela superfície 3D do corpo. Usa os corpos de referência exportados pelo FET de cada jogo (pasta
    <i>motor/referencia</i>).<br><br>
    <b>1.1</b> — sem os corpos de referência (pacote leve), avisa o que falta e importa do pacote completo.<br>
    <b>1.0</b> — lista de texturas com o layout identificado sozinho, cor e mapa normal, tamanho da saída, prévia no corpo em 3D e plana,
    arrastar e soltar.<br><br>
    Ainda não testado no jogo.` });
}

// ---------------------------------------------------------------- teclado
document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  const digitando = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === 'o') { e.preventDefault(); adicionar(e.shiftKey ? 'pasta' : 'arquivos'); return; }
  if (ctrl && e.key === 'Enter') { e.preventDefault(); converter(); return; }
  if (e.key === 'F1') { e.preventDefault(); atalhos(); return; }
  if (digitando || ctrl) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const its = filtrados();
    const i = its.findIndex((x) => x.id === S.sel);
    const j = Math.max(0, Math.min(its.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    if (its[j]) { e.preventDefault(); selecionar(its[j].id); document.querySelector(`#lista .tex[data-id="${its[j].id}"]`)?.scrollIntoView({ block: 'nearest' }); }
  } else if (e.key === 'Delete' && S.sel !== null && !S.job.rodando) { e.preventDefault(); remover([S.sel]); }
  else if (e.key.toLowerCase() === 'f') { S.previa?.enquadrar(); }
  else if (e.key.toLowerCase() === 'p' && S.itens.length) { definirModo(S.modo === '3d' ? 'plano' : '3d'); }
  else if (e.key === 'Tab' && (document.activeElement === document.body || document.activeElement.id === 'tela')) {
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
  $('#soltar-ic').innerHTML = icone('pessoa', 64);
  $('#btn-vazio-arq').innerHTML = icone('arquivoMais', 15) + 'Adicionar texturas…';
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
  document.querySelectorAll('#seg-modo button').forEach((b) => { b.onclick = () => definirModo(b.dataset.modo); });
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
    aviso('Faltam os corpos de referência do jogo', { tipo: 'aviso', tempo: 10000, detalhe: 'Eles não vêm no pacote leve: importe do pacote completo para converter.',
      acao: { rotulo: 'Importar…', fn: referenciasFaltando } });
  }
  setInterval(async () => {
    if (S.ambiente.ok || !S.ambiente.instalar || S.job.rodando) return;
    const e = await api('estado').catch(() => null);
    if (e && (e.ambiente.ok || !e.ambiente.instalar)) aplicar(e);
  }, 4000);
  if (S.ambiente.msg === 'verificando…') {
    const t = setInterval(async () => {
      const e = await api('estado').catch(() => null);
      if (e && e.ambiente.msg !== 'verificando…') { clearInterval(t); aplicar(e); }
    }, 700);
  }
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
