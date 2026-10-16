// Conversor de Tabelas — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, confirmar, barraMenus, divisorArrastavel, dialogoSobre, interruptor, nota, modalAberto, menuAberto } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';

const S = { e: null, foco: null, plano: null, versao: '', polling: null, ultimoRel: null };
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');
async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }

function aplicar(e) {
  if (!e) return;
  const antesRodando = S.e && S.e.rodando;
  S.e = e;
  desenharLista();
  desenharTopo();
  desenharPropriedades();
  desenharStatus();
  if (e.rodando) acompanhar();
  if (antesRodando && !e.rodando && e.relatorio) fimConversao(e.relatorio);
}

async function atualizar() { aplicar(await tentar(() => api('estado'))); }

// ---------------------------------------------------------------- lista
function filtradas() {
  const q = $('#busca').value.trim().toLowerCase();
  const f = $('#filtro').value;
  return (S.e.tabelas || []).filter((t) => {
    if (q && !t.nome.toLowerCase().includes(q)) return false;
    if (f === 'sel') return t.sel;
    if (f === 'ambos') return t.existe_no_destino;
    if (f === 'so') return t.existe_no_destino === false;
    return true;
  });
}

function desenharLista() {
  const l = $('#lista');
  const topo = l.scrollTop;
  l.innerHTML = '';
  if (!S.e.origem) {
    l.append(el('div', { class: 'arvore-vazia' }, 'Sem origem. Importe o banco em Dados do jogo (Super Tool) ou escolha outra origem no painel da direita.'));
    $('#resumo-lista').textContent = '';
    return;
  }
  for (const t of filtradas()) {
    const cb = el('input', { type: 'checkbox', title: 'Converter esta tabela' });
    cb.checked = t.sel;
    cb.onclick = (ev) => { ev.stopPropagation(); selecionar([t.nome], cb.checked); };
    let sub;
    if (!S.e.destino) sub = el('small', {}, `${fmt(t.campos)} campos`);
    else if (t.existe_no_destino === false) sub = el('small', { class: 'so' }, 'não existe no destino');
    else if (t.destino !== t.nome) sub = el('small', { class: 'outra' }, `→ ${t.destino}`);
    else sub = el('small', {}, `destino: ${fmt(t.registros_destino)} linhas${t.ajustada ? ' · ajustada' : ''}`);
    l.append(el('button', { class: `tab ${S.foco === t.nome ? 'foco' : ''}`, 'data-nome': t.nome, onclick: () => focar(t.nome) },
      cb, el('span', { class: 'txt' }, el('b', {}, t.nome), sub), el('span', { class: 'n' }, fmt(t.registros))));
  }
  l.scrollTop = topo;
  const sel = S.e.sel.length;
  $('#resumo-lista').textContent = `${fmt(S.e.tabelas.length)} tabelas · ${sel} marcada${sel === 1 ? '' : 's'}`;
}

async function selecionar(nomes, marcado) { aplicar(await tentar(() => api('selecionar', { tabelas: nomes, marcado }))); }
async function selecionarTodas(v) {
  const nomes = filtradas().map((t) => t.nome);
  aplicar(await tentar(() => api('selecionar', { tabelas: nomes, marcado: v })));
}

async function focar(nome) {
  S.foco = nome;
  document.querySelectorAll('#lista .tab').forEach((b) => b.classList.toggle('foco', b.dataset.nome === nome));
  const p = $('#principal');
  p.innerHTML = '';
  p.append(el('div', { class: 'vazio' }, 'Montando o plano…'));
  const r = await tentar(() => api('plano?tabela=' + encodeURIComponent(nome)));
  if (!r || S.foco !== nome) return;
  S.plano = r;
  desenharPlano();
}

// ---------------------------------------------------------------- plano da tabela
function desenharPlano() {
  const p = $('#principal');
  p.innerHTML = '';
  const r = S.plano;
  if (!r) return;
  const pl = r.plano;
  const t = S.e.tabelas.find((x) => x.nome === pl.tabela) || {};
  const destSel = el('select', { class: 'seletor', style: { maxWidth: '260px' }, disabled: !r.tabelas_destino.length,
    onchange: (e) => mapear({ destino: e.target.value }) },
  ...[...new Set([pl.destino, ...r.tabelas_destino])].sort().map((n) => { const o = el('option', { value: n }, n + (r.tabelas_destino.includes(n) ? '' : ' (não existe no destino)')); o.selected = n === pl.destino; return o; }));
  const cb = el('input', { type: 'checkbox' });
  cb.checked = !!t.sel;
  cb.onchange = () => selecionar([pl.tabela], cb.checked);
  p.append(el('div', { class: 'cab-detalhe' },
    el('div', {}, el('span', { class: 'etiqueta laranja' }, `${pl.nome_origem || pl.jogo_origem} → ${pl.nome_destino || pl.jogo_destino}`),
      el('h1', {}, pl.tabela), el('div', { class: 'sub' }, `${fmt(pl.linhas_origem)} linhas na origem${pl.linhas_destino != null ? ` · ${fmt(pl.linhas_destino)} no destino` : ''}${pl.chave.length ? ` · chave: ${pl.chave.join(', ')}` : ''}`)),
    el('div', { class: 'acoes' }, el('label', { class: 'interruptor', style: { padding: '4px 10px' } }, el('span', { class: 'txt' }, el('b', {}, 'Converter')), el('span', { class: 'chave' }, cb, el('span'))))));
  if (!pl.existe_no_destino && S.e.destino) p.append(nota(`A tabela <b>${esc(pl.destino)}</b> não existe no destino: ela sai com as colunas da origem. Escolha outra tabela de destino abaixo se o nome mudou entre os jogos.`, 'alerta'));
  if (!S.e.destino) p.append(nota('Sem destino escolhido: a tabela sai igual à origem. Escolha o banco (ou só o meta) do jogo de destino no painel da direita para converter o esquema.', 'info'));
  const rel = r.relatorio;
  const novas = pl.colunas.filter((c) => c.nova);
  const fora = Object.values(rel.fora_da_faixa || {}).reduce((a, b) => a + b, 0);
  const regras = Object.values(rel.regras || {}).reduce((a, b) => a + b, 0);
  p.append(el('div', { class: 'estatisticas', style: { margin: '12px 0' } },
    ...[[pl.colunas.length, 'colunas no destino'], [novas.length, 'colunas novas'], [pl.removidas.length, 'colunas descartadas'],
      [regras, 'valores com regra de escala'], [fora, 'valores fora da faixa']].map(([v, k]) => el('div', { class: 'estatistica' }, el('b', {}, fmt(v)), el('span', {}, k)))));
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Tabela de destino'), el('p', { class: 'dica' }, 'Normalmente a mesma; troque se a tabela mudou de nome entre os jogos.')), destSel)));
  if (pl.regras.length) p.append(nota('<b>Regras de escala deste par de jogos:</b> ' + pl.regras.map(esc).join(' · '), 'info'));
  if (pl.removidas.length) p.append(nota(`<b>Colunas que o destino não tem</b> (descartadas): <span class="mono">${pl.removidas.map(esc).join(', ')}</span>`));
  // colunas
  const linhas = pl.colunas.map((c) => {
    const inf = c.info || {};
    const tipo = (inf.tipo || '').replace(/^(DBO)?FIELDTYPE_/, '').toLowerCase();
    const opcoes = [['auto', c.nova ? 'mais comum no destino (padrão)' : `coluna ${c.destino} (padrão)`], ['moda', 'mais comum no destino'], ['fixo', 'valor fixo'],
      ...S.plano.campos_origem.filter((x) => x !== c.destino).map((x) => ['col:' + x, 'coluna ' + x])];
    const atual = c.ajustado ? (c.modo === 'coluna' ? 'col:' + c.origem : c.modo) : 'auto';
    const s = el('select', { onchange: (e) => mudarColuna(c.destino, e.target.value) }, ...opcoes.map(([v, rt]) => { const o = el('option', { value: v }, rt); o.selected = v === atual; return o; }));
    const valor = c.modo !== 'coluna' ? el('input', { type: 'text', class: 'mono', value: c.valor ?? '', style: { width: '110px' }, disabled: c.modo === 'moda',
      onchange: (e) => mapear({ coluna: c.destino, modo: 'fixo', valor: e.target.value }) }) : el('span', { class: 'exemplos', title: (r.exemplos[c.destino] || []).join(', ') }, (r.exemplos[c.destino] || []).join(', '));
    const n_fora = (rel.fora_da_faixa || {})[c.destino];
    return el('tr', { class: `${c.nova ? 'nova' : ''} ${c.ajustado ? 'alterada' : ''}` },
      el('td', { class: 'coluna' }, el('b', {}, c.destino), el('small', {}, tipo ? `${inf.chave ? 'chave · ' : ''}${tipo}${tipo.includes('int') ? ` ${inf.low}…${inf.high}` : ''}` : '')),
      el('td', {}, s), el('td', {}, valor),
      el('td', {}, c.regra ? el('span', { class: 'etiqueta azul' }, c.regra) : c.nova ? el('span', { class: 'etiqueta verde' }, 'nova no destino') : null,
        n_fora ? el('span', { class: 'etiqueta amarela', style: { marginLeft: '4px' } }, `${fmt(n_fora)} fora da faixa`) : null));
  });
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Colunas'), el('p', { class: 'dica' }, 'De onde vem cada coluna da tabela final. Fora da faixa do meta do destino o valor é ajustado para a borda.')),
    el('button', { class: 'btn-fantasma peq', disabled: !pl.colunas.some((c) => c.ajustado), onclick: () => mapear({ limpar: true }) }, icone('restaurar', 12), 'Voltar ao padrão')),
  el('div', { class: 'cartao-corpo justo' }, el('table', { class: 'tabela colunas' },
    el('thead', {}, el('tr', {}, ...['Coluna final', 'Vem de', 'Valor / exemplos', ''].map((h) => el('th', {}, h)))), el('tbody', {}, ...linhas)))));
  // prévia
  const th = r.campos.map((c) => el('th', { class: pl.colunas.find((x) => x.destino === c)?.nova ? 'nova' : '' }, c));
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Prévia'), el('p', { class: 'dica' }, `As primeiras ${r.amostra.length} linhas como vão ficar.`))),
    el('div', { class: 'cartao-corpo' }, el('div', { class: 'grade-previa' }, el('table', {}, el('thead', {}, el('tr', {}, ...th)),
      el('tbody', {}, ...r.amostra.map((l) => el('tr', {}, ...l.map((v) => el('td', {}, v))))))))));
}

function mudarColuna(coluna, v) {
  if (v === 'auto') mapear({ coluna, modo: 'auto' });
  else if (v === 'moda') mapear({ coluna, modo: 'moda' });
  else if (v === 'fixo') mapear({ coluna, modo: 'fixo', valor: '0' });
  else if (v.startsWith('col:')) mapear({ coluna, modo: 'coluna', origem: v.slice(4) });
}

async function mapear(d) {
  if (!S.plano) return;
  const r = await tentar(() => api('mapear', { tabela: S.plano.plano.tabela, ...d }));
  if (!r) return;
  S.plano = r;
  desenharPlano();
  atualizar();
}

// ---------------------------------------------------------------- painel direito
function secao(chave, titulo, ic, corpo) {
  const d = el('details', { class: 'secao' });
  d.open = !(S._fechadas || {})[chave];
  d.addEventListener('toggle', () => { S._fechadas = { ...(S._fechadas || {}), [chave]: !d.open }; });
  d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo)));
  return d;
}

function cartaoBanco(qual, r) {
  if (!r) return [];
  const sel = el('select', { class: 'seletor', onchange: (e) => tentar(async () => { aplicar(await api('jogo', { qual, jogo: e.target.value })); if (S.foco) focar(S.foco); }) },
    ...(S.e.jogos || []).map(({ id, nome }) => { const o = el('option', { value: id }, nome); o.selected = (r.jogo || '').replace('~', '') === id; return o; }));
  return [el('dl', { class: 'kv' },
    el('dt', {}, 'Arquivo'), el('dd', { class: 'mono' }, r.caminho || '—'),
    el('dt', {}, 'Tipo'), el('dd', {}, r.esquema ? `esquema guardado do ${r.nome_jogo}` : { db: 'banco .db', pasta: 'pasta de tabelas .txt', meta: 'só o meta (esquema)' }[r.tipo] || r.tipo),
    el('dt', {}, 'Jogo'), el('dd', {}, sel, (r.jogo || '').endsWith('~') ? el('div', { class: 'mudo peq-txt' }, `versão não guardada; ${r.nome_jogo}`) : null),
    el('dt', {}, 'Tabelas'), el('dd', {}, fmt(r.tabelas)))];
}

function desenharPropriedades() {
  const p = $('#propriedades');
  p.innerHTML = '';
  const e = S.e;
  // origem
  const corpoO = [];
  if (e.origem) corpoO.push(...cartaoBanco('origem', e.origem));
  else corpoO.push(nota('Sem origem. Importe o banco em <b>Dados do jogo</b> no Super Tool, ou escolha um .db / pasta aqui.', 'alerta'));
  corpoO.push(el('div', { class: 'mudo peq-txt' }, e.origem_e_banco ? 'Usando o banco importado no Super Tool (Dados do jogo).' : 'Usando um banco escolhido só nesta ferramenta.'));
  corpoO.push(el('div', { class: 'acoes-linha' },
    !e.origem_e_banco ? el('button', { class: 'btn peq', onclick: () => origem('banco') }, icone('bancoDados', 12), 'Usar o do Super Tool') : null,
    el('button', { class: 'btn peq', onclick: () => origem('arquivo') }, icone('arquivoMais', 12), 'Outro .db…'),
    el('button', { class: 'btn peq', onclick: () => origem('pasta') }, icone('pastaMais', 12), 'Pasta…')));
  p.append(secao('origem', 'Origem', 'bancoDados', corpoO));
  // destino
  const corpoD = [];
  if (e.destino) corpoD.push(...cartaoBanco('destino', e.destino));
  else corpoD.push(nota('Escolha o banco do jogo para onde as tabelas vão (o <b>fifa_ng_db.db</b> do FC 27, por exemplo). Ele dá as colunas finais, as faixas e os valores mais comuns. Só o meta (.xml) — ou o esquema guardado de uma versão — também serve, sem a moda e sem mesclar.'));
  const selEsq = el('select', { class: 'seletor' }, el('option', { value: '' }, 'Esquema guardado…'), ...(e.jogos || []).map(({ id, nome }) => el('option', { value: id }, nome)));
  selEsq.onchange = () => { if (selEsq.value) tentar(async () => { aplicar(await api('destino', { modo: 'esquema', jogo: selEsq.value })); if (S.foco) focar(S.foco); }); };
  corpoD.push(el('div', { class: 'campo' }, el('label', {}, 'Sem o banco do destino? Use o esquema guardado da versão'), selEsq));
  corpoD.push(el('div', { class: 'acoes-linha' },
    el('button', { class: 'btn peq', onclick: () => destino('arquivo') }, icone('arquivoMais', 12), 'Banco .db…'),
    el('button', { class: 'btn peq', onclick: () => destino('pasta') }, icone('pastaMais', 12), 'Pasta…'),
    el('button', { class: 'btn peq', onclick: () => destino('meta') }, icone('relatorio', 12), 'Só o meta…'),
    e.destino ? el('button', { class: 'btn-fantasma peq', onclick: () => destino('limpar') }, icone('x', 12), 'Tirar') : null));
  p.append(secao('destino', 'Destino (tabelas finais)', 'tabela', corpoD));
  // saída
  const op = e.opcoes;
  const caminho = el('input', { type: 'text', class: 'entrada mono', value: op.saida || '', placeholder: 'Escolha a pasta de saída', spellcheck: 'false', onchange: (ev) => opcoes({ saida: ev.target.value.trim() }) });
  const seg = (k, itens) => el('div', { class: 'segmentado' }, ...itens.map(([v, t, d]) => el('button', { class: op[k] === v ? 'ativo' : '', title: d || '', onclick: () => opcoes({ [k]: v }) }, t)));
  const podeDb = e.destino && e.destino.tipo === 'db';
  p.append(secao('saida', 'Saída', 'pasta', [
    el('div', { class: 'campo' }, el('label', {}, 'Pasta de saída'), el('div', { class: 'caminho-linha' }, caminho, el('button', { class: 'btn', onclick: escolherSaida, title: 'Escolher…' }, icone('pasta', 14)))),
    el('div', { class: 'campo' }, el('label', {}, 'Tabelas finais'), seg('modo', [['substituir', 'Só a origem', 'A tabela final tem só as linhas convertidas da origem'], ['mesclar', 'Mesclar com o destino', 'Linhas do destino + as da origem; na mesma chave, a da origem substitui']])),
    el('div', { class: 'campo' }, el('label', {}, 'Formato dos .txt'), seg('formato', [['utf-16', 'UTF-16 (RDBM/DB Master)'], ['utf-8', 'UTF-8']])),
    interruptor({ titulo: 'Gravar também um .db novo', descricao: podeDb ? 'Cópia do banco de destino com as tabelas convertidas no lugar (tabelas com texto comprimido saem só em .txt).' : 'Precisa de um destino .db.',
      marcado: !!op.gravar_db && podeDb, desabilitado: !podeDb, aoMudar: (v) => opcoes({ gravar_db: v }) }).el,
    interruptor({ titulo: 'Sobrescrever existentes', descricao: 'Substitui os .txt que já estiverem na pasta.', marcado: op.sobrescrever, aoMudar: (v) => opcoes({ sobrescrever: v }) }).el,
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', disabled: !op.saida, onclick: () => tentar(() => api('abrir', {})) }, icone('externo', 12), 'Abrir a pasta')),
  ]));
  if (e.relatorio) {
    const rel = e.relatorio;
    p.append(secao('rel', 'Última conversão', 'relatorio', [
      el('div', { class: 'mudo peq-txt' }, `${rel.quando} · ${rel.tabelas.length} tabela(s)${rel.erros.length ? ` · ${rel.erros.length} erro(s)` : ''}`),
      ...rel.tabelas.slice(0, 8).map((t) => el('div', { class: 'peq-txt' }, el('b', {}, t.destino), ` — ${fmt(t.linhas_finais)} linhas`)),
      rel.db ? nota(`Banco novo: <span class="mono">${esc(rel.db.caminho)}</span>`, 'info') : null,
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { caminho: rel.saida + '\\relatorio_conversao_tabelas.txt' })) }, icone('relatorio', 12), 'Relatório')),
    ]));
  }
}

async function origem(modo) { aplicar(await tentar(() => api('origem', { modo }))); S.foco = null; S.plano = null; $('#principal').innerHTML = ''; telaInicial(); }
async function destino(modo) { aplicar(await tentar(() => api('destino', { modo }))); if (S.foco) focar(S.foco); }
async function opcoes(d) { aplicar(await tentar(() => api('opcoes', d))); }
async function escolherSaida() {
  const r = await tentar(() => api('dialogo', {}));
  if (r && r.caminho) await opcoes({ saida: r.caminho });
}

// ---------------------------------------------------------------- topo / status / conversão
function desenharTopo() {
  const e = S.e;
  const n = e.sel.length;
  $('#btn-converter').disabled = e.rodando || !n || !e.origem;
  $('#contador').hidden = !n || e.rodando;
  $('#contador').textContent = n;
  $('#btn-converter-txt').textContent = e.rodando ? `Convertendo ${e.progresso[0]}/${e.progresso[1]}…` : 'Converter';
  $('#btn-converter-ic').innerHTML = icone(e.rodando ? 'recarregar' : 'converter', 14, e.rodando ? 'girando' : '');
  const jo = e.origem ? e.origem.nome_jogo : '—', jd = e.destino ? e.destino.nome_jogo : 'sem destino';
  $('#titulo').innerHTML = `<b>${esc(jo)} → ${esc(jd)}</b><span class="pasta">${esc(e.opcoes.saida || 'escolha a pasta de saída')}</span>`;
}
function desenharStatus() {
  const e = S.e;
  $('#status-esq').innerHTML = e.origem ? `<span><b>${fmt(e.tabelas.length)}</b> tabelas na origem</span><span><b>${e.sel.length}</b> marcadas</span>${e.destino ? `<span><b>${e.tabelas.filter((t) => t.existe_no_destino === false).length}</b> só na origem</span>` : ''}` : '<span>Sem origem</span>';
  const sd = $('#status-dir');
  sd.innerHTML = '';
  sd.append(el('span', { class: `chip ${e.banco ? 'ok' : 'aviso'}`, title: e.banco ? e.banco.caminho : 'Importe em Dados do jogo' }, icone('bancoDados', 12), e.banco ? `Super Tool: ${e.banco.nome_jogo}` : 'sem banco no Super Tool'));
}
async function converter(forcar = false) {
  if (!S.e.opcoes.saida) { await escolherSaida(); if (!S.e.opcoes.saida) return; }
  const r = await tentar(() => api('converter', { forcar }));
  if (!r) return;
  if (r.confirmar) {
    if (await confirmar('Sobrescrever?', `Já existem na pasta: ${r.confirmar.slice(0, 8).map(esc).join(', ')}${r.confirmar.length > 8 ? '…' : ''}.`, { rotulo: 'Sobrescrever', perigo: true })) converter(true);
    return;
  }
  aplicar(r);
}
function acompanhar() {
  if (S.polling) return;
  S.polling = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (!e) return;
    aplicar(e);
    if (!e.rodando) { clearInterval(S.polling); S.polling = null; }
  }, 500);
}
function fimConversao(rel) {
  const n = rel.tabelas.length;
  aviso(rel.erros.length ? `Conversão terminou com ${rel.erros.length} erro(s)` : `${n} tabela(s) convertida(s)`, {
    tipo: rel.erros.length ? 'erro' : 'sucesso', tempo: 8000, detalhe: rel.db ? 'Banco novo gravado junto.' : rel.saida,
    acao: { rotulo: 'Abrir pasta', fn: () => tentar(() => api('abrir', { caminho: rel.saida })) },
  });
}

function telaInicial() {
  const p = $('#principal');
  if (S.foco) return;
  p.innerHTML = '';
  p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('tabela', 64) }), el('h2', {}, 'Converter tabelas entre jogos'),
    el('p', {}, 'Marque à esquerda as tabelas de origem e escolha à direita o banco do jogo de destino. Clique numa tabela para ver de onde vem cada coluna final — colunas novas, renomeadas (marking → defensiveawareness), calculadas (pacdiv…phypos), escalas que mudaram (tom de pele ×10 no FC 27) e valores fora da faixa. Funciona entre FIFA 16, 21, 22, 23, FC 24, 25, 26 e 27.'),
    el('div', { class: 'acoes' }, el('button', { class: 'btn', onclick: () => destino('arquivo') }, icone('tabela', 14), 'Escolher o destino…'),
      el('button', { class: 'btn', onclick: () => { $('#busca').focus(); } }, icone('busca', 14), 'Buscar tabela'))));
}

function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { cabecalho: 'Origem' },
      { rotulo: 'Banco do Super Tool', icone: 'bancoDados', marcado: S.e.origem_e_banco, fn: () => origem('banco') },
      { rotulo: 'Outro banco (.db)…', icone: 'arquivoMais', fn: () => origem('arquivo') },
      { rotulo: 'Pasta de tabelas…', icone: 'pastaMais', fn: () => origem('pasta') },
      { cabecalho: 'Destino' },
      { rotulo: 'Banco (.db)…', icone: 'arquivoMais', fn: () => destino('arquivo') },
      { rotulo: 'Pasta de tabelas…', icone: 'pastaMais', fn: () => destino('pasta') },
      { rotulo: 'Só o meta (.xml)…', icone: 'relatorio', fn: () => destino('meta') },
      '-',
      { rotulo: 'Pasta de saída…', icone: 'pasta', fn: escolherSaida },
      { rotulo: 'Abrir a pasta de saída', icone: 'externo', desabilitado: !S.e.opcoes.saida, fn: () => tentar(() => api('abrir', {})) },
    ]],
    ['Tabelas', () => [
      { rotulo: 'Converter as marcadas', icone: 'converter', atalho: 'Ctrl+Enter', desabilitado: !S.e.sel.length || S.e.rodando, fn: () => converter() },
      '-',
      { rotulo: 'Marcar as que aparecem na lista', icone: 'check', fn: () => selecionarTodas(true) },
      { rotulo: 'Desmarcar todas', icone: 'x', fn: () => tentar(async () => aplicar(await api('selecionar', { tabelas: S.e.sel, marcado: false }))) },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Sobre o Conversor de Tabelas', icone: 'info', fn: () => dialogoSobre({ nome: 'Conversor de Tabelas', versao: S.versao, html: `
        Converte tabelas do banco (fifa_ng_db) entre jogos: escolha as tabelas de origem e o banco do jogo de destino. Para cada tabela,
        as colunas iguais são copiadas, as novas recebem o valor mais comum do destino (ou o que você fixar), as que sumiram são descartadas
        e os valores fora da faixa do meta do destino são ajustados.<br><br>
        <b>Regras de escala FC 26 → FC 27</b> (as do port do BRFP 27): tom de pele ×10 (jogadores, técnicos, árbitros, torcida),
        tipo de pele acima de 7 → 0, camadas de rosto 3/4 → 0. No sentido FC 27 → FC 26, tom de pele ÷10.<br><br>
        <b>Saída:</b> .txt por tabela (UTF-16 como o RDBM/DB Master exportam, ou UTF-8) e, com um destino .db, um banco novo com as
        tabelas trocadas (o gravador reproduz o banco original byte a byte). Tabelas com texto comprimido (Huffman) saem só em .txt.<br><br>
        <b>1.0</b> — primeira versão.` }) },
    ]],
  ]);
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); converter(); }
});

async function iniciar() {
  $('#btn-todas').innerHTML = icone('check', 14);
  $('#btn-nenhuma').innerHTML = icone('x', 14);
  $('#busca-ic').innerHTML = icone('busca', 14);
  $('#btn-todas').onclick = () => selecionarTodas(true);
  $('#btn-nenhuma').onclick = () => selecionarTodas(false);
  $('#btn-converter').onclick = () => converter();
  $('#busca').addEventListener('input', desenharLista);
  $('#filtro').addEventListener('change', desenharLista);
  divisorArrastavel($('#div-esq'), '--esq', { min: 220, max: 480 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 260, max: 520, lado: 'dir' });
  const r = await api('inicio');
  S.versao = r.versao;
  $('#versao').textContent = r.versao;
  menus();
  aplicar(r);
  telaInicial();
  // o banco do Super Tool pode mudar com a ferramenta aberta
  setInterval(async () => {
    if (S.polling) return;
    const e = await api('estado').catch(() => null);
    if (e && JSON.stringify(e.banco) !== JSON.stringify(S.e.banco)) aplicar(e);
  }, 5000);
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
