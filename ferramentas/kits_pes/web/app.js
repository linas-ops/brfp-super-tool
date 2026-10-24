// Conversor de Kits PES → FC — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, confirmar, barraMenus, abrirMenu, divisorArrastavel, dialogoSobre, interruptor, nota, modalAberto, menuAberto, lerArquivoBase64 } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { instalarComponentes } from './comum/componentes.js';
import { importarReferencias } from './comum/referencias.js';
import { Previa } from './previa.js';

const S = { itens: [], job: {}, opcoes: {}, base: {}, ambiente: {}, referencias: {}, tipos: [], times: [], raizTimes: null, sel: null, versao: '',
  qual: 'entrada', peca: 'jersey', modo: 'plano', previa: null, polling: null, ultimoResumo: null, malhas: {} };
const EXT = ['.png', '.dds', '.tga', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'];
const PECAS = [['jersey', 'Camisa'], ['shorts', 'Calção'], ['socks', 'Meião']];
const MALHA_ARQ = { jersey: 'jersey_0_0_0_0_1_0_0_mesh.fbx', shorts: 'shorts_0_0_0_mesh.fbx', socks: 'sock_0_0_1_0_0_mesh.fbx', pes: 'pes2021_kit.obj' };
const TIPO_CURTO = { home: 'home', away: 'away', goalie_home: 'goleiro', third: 'third', fourth: 'fourth' };
const EST = {
  pronto: ['ponto', 'Pronto para converter'], na_fila: ['relogio', 'Na fila'], convertendo: ['recarregar', 'Convertendo…'],
  ok: ['check', 'Convertido'], erro: ['aviso', 'Erro'], ignorado: ['menos', 'Pulado'],
};

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }
const nomeArq = (c) => (c || '').split(/[\\/]/).filter(Boolean).pop() || '';
const tipoTag = (t) => el('span', { class: `tipo-kit ${t || ''}` }, TIPO_CURTO[t] || '—');
const nomeTipo = (t) => (S.tipos.find((x) => x.id === t) || {}).nome || t;
const temTime = (it) => !!(String(it.teamid || '').match(/^\d+$/) && +it.teamid > 0 && it.time);
const faltaRef = (qual) => (S.referencias.faltam || []).includes(MALHA_ARQ[qual]);
const pode3d = (qual) => (qual === 'entrada' ? !faltaRef('pes') : !['jersey', 'shorts', 'socks'].some(faltaRef));

// ---------------------------------------------------------------- estado
function aplicar(r) {
  if (!r) return;
  if (r.itens) S.itens = r.itens;
  if (r.job) S.job = r.job;
  if (r.opcoes) S.opcoes = r.opcoes;
  if (r.base) S.base = r.base;
  if (r.ambiente) S.ambiente = r.ambiente;
  if (r.referencias) S.referencias = r.referencias;
  if (r.tipos) S.tipos = r.tipos;
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
  bRes.title = bRes.disabled ? 'Converta este kit para ver o resultado' : 'O kit convertido para o FC 27 (Tab alterna)';
  if (S.job.rodando) iniciarPolling();
  if (!S.job.rodando && S.job.resumo && S.job.fim && S.job.fim !== S.ultimoResumo) {
    const primeiro = S.ultimoResumo === null && !S._acompanhando;
    S.ultimoResumo = S.job.fim;
    if (!primeiro) {
      const rs = S.job.resumo;
      aviso(rs.erros ? `Conversão terminou com ${rs.erros} erro(s)` : `${rs.convertidos} kit(s) convertido(s)`, {
        tipo: rs.erros ? 'erro' : 'sucesso', tempo: 7000,
        detalhe: `${rs.avisos ? rs.avisos + ' aviso(s) · ' : ''}${rs.segundos} s`,
        acao: rs.pastas && rs.pastas.length ? { rotulo: 'Abrir saída', fn: () => tentar(() => api('abrir', { caminho: rs.pastas[0] })) } : null,
      });
      S._acompanhando = false;
      if (itemSel()?.saida_feita) definirQual('saida');
      carregarTimes();
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
  }, 500);
}

async function carregarTimes() {
  const r = await api('times').catch(() => null);
  if (!r) return;
  S.times = r.times || [];
  S.raizTimes = r.raiz;
  const dl = $('#lista-times');
  dl.innerHTML = '';
  for (const t of S.times) dl.append(el('option', { value: t.time }, `${t.teamid}${t.tipos.length ? ' · ' + t.tipos.join(', ') : ''}`));
}

// ---------------------------------------------------------------- lista
function filtrados() {
  const q = $('#busca').value.trim().toLowerCase();
  const f = $('#filtro').value;
  return S.itens.filter((it) => {
    if (q && !`${it.rel} ${it.caminho} ${it.time || ''} ${it.teamid || ''}`.toLowerCase().includes(q)) return false;
    if (f === 'faltando') return !temTime(it);
    if (f === 'feitas') return it.estado === 'ok';
    if (f === 'problemas') return it.estado === 'erro' || !!it.erro || it.quadrada === false || (it.avisos || []).length;
    return true;
  });
}

function desenharLista() {
  const lista = $('#lista');
  lista.innerHTML = '';
  const itens = filtrados();
  if (!S.itens.length) {
    lista.append(el('div', { class: 'arvore-vazia' }, 'Nenhum kit na lista.', el('br'), 'Arraste texturas de kits do PES para a janela ou use os botões acima.'));
    return;
  }
  if (!itens.length) { lista.append(el('div', { class: 'arvore-vazia' }, 'Nada com esse filtro.')); return; }
  const grupos = new Map();
  for (const it of itens) {
    const g = it.recebido ? 'Arrastados para a janela' : it.de_pasta ? it.raiz : 'Arquivos avulsos';
    if (!grupos.has(g)) grupos.set(g, []);
    grupos.get(g).push(it);
  }
  for (const [g, its] of grupos) {
    if (grupos.size > 1 || its[0].de_pasta) {
      lista.append(el('div', { class: 'grupo-lista', title: g }, el('span', {}, its[0].de_pasta ? nomeArq(g) : g), el('span', {}, String(its.length))));
    }
    for (const it of its) lista.append(linhaKit(it));
  }
}

function linhaKit(it) {
  const [ic, rot] = EST[it.estado] || EST.pronto;
  const comAviso = it.estado === 'ok' && (it.avisos || []).length;
  const estCls = comAviso ? 'est-aviso' : `est-${it.estado}`;
  const parado = it.estado === 'pronto' && it.motivo;
  const estado = parado ? ['menos', it.motivo] : [comAviso ? 'aviso' : ic, comAviso ? `Convertido com ${it.avisos.length} aviso(s)` : (it.mensagem || rot)];
  const sub = el('small', {});
  if (!it.erro) {
    sub.append(tipoTag(it.tipo));
    if (temTime(it)) sub.append(el('span', { class: 'time-kit' }, `${it.time} · ${it.teamid}`));
    else sub.append(el('span', { class: 'falta-time' }, 'falta o time'));
    sub.append(el('span', {}, `${it.largura}×${it.altura}`));
    if (it.quadrada === false) sub.append(el('span', { class: 'duvida', title: 'A textura do kit do PES é quadrada: confira se é mesmo um kit', html: icone('aviso', 11) }));
  } else sub.append(el('span', {}, 'imagem ilegível'));
  return el('button', { class: `tex ${S.sel === it.id ? 'sel' : ''}`, role: 'option', 'data-id': it.id, onclick: () => selecionar(it.id),
    oncontextmenu: (e) => { e.preventDefault(); selecionar(it.id); menuItem(e.clientX, e.clientY, it); } },
  el('span', { class: 'ic-tex', html: icone('imagem', 18) }),
  el('span', { class: 'txt' }, el('b', { title: it.caminho }, it.rel), sub),
  el('span', { class: `est ${parado ? 'est-ignorado' : estCls}`, title: estado[1],
    html: icone(estado[0], 15, it.estado === 'convertendo' ? 'girando' : '') }));
}

function menuItem(x, y, it) {
  abrirMenu([
    { rotulo: 'Converter este kit', icone: 'play', desabilitado: S.job.rodando || !!it.motivo, fn: () => converter([it.id]) },
    '-',
    { cabecalho: 'Tipo do kit' },
    ...S.tipos.map((t) => ({ rotulo: t.nome, marcado: it.tipo === t.id, desabilitado: S.job.rodando, fn: () => editar([it.id], { tipo: t.id }) })),
    '-',
    { rotulo: 'Usar este time nos kits sem time', icone: 'copiar', desabilitado: !temTime(it) || S.job.rodando, fn: () => copiarTime(it, false) },
    { rotulo: 'Mostrar o arquivo no Explorer', icone: 'externo', fn: () => tentar(() => api('abrir', { caminho: it.caminho })) },
    { rotulo: 'Mostrar o kit convertido no Explorer', icone: 'externo', desabilitado: !it.saida_feita, fn: () => tentar(() => api('abrir', { caminho: it.saida_feita })) },
    '-',
    { rotulo: 'Tirar da lista', icone: 'x', desabilitado: S.job.rodando, fn: () => remover([it.id]) },
  ], x, y);
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

async function editar(ids, campos) {
  const r = await tentar(() => api('editar', { ids, ...campos }));
  if (r) aplicar(r);
}
async function copiarTime(it, todos) {
  const ids = S.itens.filter((x) => x.id !== it.id && (todos || !temTime(x))).map((x) => x.id);
  if (!ids.length) { aviso('Todos os kits já têm time.', { tipo: 'info' }); return; }
  await editar(ids, { teamid: it.teamid, time: it.time });
  aviso(`Time ${it.time} (${it.teamid}) em ${ids.length} kit(s)`, { tipo: 'sucesso', tempo: 2500 });
}

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
  $('#titulo').innerHTML = `<b>${S.itens.length} ${S.itens.length === 1 ? 'kit' : 'kits'}</b><span class="pasta" title="${esc(saida || '')}">saída: ${esc(saida || '“Kits FC 27” ao lado de cada textura')}</span>`;
}

function desenharStatus() {
  const est = $('#status-esq');
  if (S.job.rodando && S.job.mensagem) est.innerHTML = `<span>${icone('recarregar', 12, 'girando')} ${esc(S.job.mensagem)}</span>`;
  else if (S.itens.length) {
    const sem = S.itens.filter((i) => !i.erro && !temTime(i)).length;
    est.innerHTML = `<span><b>${S.itens.length}</b> na lista</span>${sem ? `<span><b>${sem}</b> sem time</span>` : ''}<span>${S.itens.filter((i) => i.estado === 'ok').length} convertidos</span>`
      + `<span>${S.base.ok ? `kit base: ${esc(S.base.info.time)} · ${esc(S.base.info.tipo || '')}` : 'sem kit base'}</span>`;
  } else est.innerHTML = '<span>Arraste kits do PES para a janela, ou use Arquivo › Adicionar.</span>';
  est.classList.add('contagem');
  const pr = $('#status-progresso');
  pr.hidden = !S.job.rodando;
  if (S.job.rodando) {
    $('#progresso-barra').style.width = `${(100 * (S.job.feitos + (S.job.fracao || 0))) / Math.max(1, S.job.total)}%`;
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

function campoTime(it) {
  const travado = S.job.rodando;
  const idIn = el('input', { type: 'text', class: 'entrada mono', value: it.teamid || '', placeholder: 'ex.: 111329', inputmode: 'numeric', disabled: travado,
    onchange: (e) => {
      const tid = e.target.value.trim();
      const t = S.times.find((x) => String(x.teamid) === tid);
      editar([it.id], t && !it.time ? { teamid: tid, time: t.time } : { teamid: tid });
    } });
  const nomeIn = el('input', { type: 'text', class: 'entrada', value: it.time || '', placeholder: 'ex.: guarani', list: 'lista-times', spellcheck: 'false', disabled: travado,
    onchange: (e) => {
      const nome = e.target.value.trim();
      const t = S.times.find((x) => x.time === nome);
      editar([it.id], t ? { time: nome, teamid: String(t.teamid) } : { time: nome });
    } });
  const tipo = el('select', { class: 'seletor', disabled: travado, onchange: (e) => editar([it.id], { tipo: e.target.value }) },
    ...S.tipos.map((t) => el('option', { value: t.id, selected: it.tipo === t.id, title: t.id }, t.nome)));
  const variacao = el('input', { type: 'number', class: 'entrada mono', min: 0, max: 99, value: it.variacao || 0, disabled: travado,
    onchange: (e) => editar([it.id], { variacao: e.target.value }) });
  const conhecido = S.times.find((x) => String(x.teamid) === String(it.teamid));
  const ajudaTime = conhecido ? `Já existe na pasta dos kits: <b>${esc(conhecido.time)}_${conhecido.teamid}</b>${conhecido.tipos.length ? ` (${esc(conhecido.tipos.join(', '))})` : ''}.`
    : S.times.length ? `Digite o nome para ver os times que já estão na pasta dos kits (${S.times.length}).` : 'O ID é o teamid do banco do FC 27; a pasta, o nome do time em minúsculas (ex.: guarani).';
  return [
    el('div', { class: 'linha-campos' },
      el('div', { class: 'campo' }, el('label', {}, 'ID do time'), idIn),
      el('div', { class: 'campo' }, el('label', {}, 'Pasta do time'), nomeIn)),
    el('div', { class: 'ajuda', html: ajudaTime }),
    el('div', { class: 'linha-campos' },
      el('div', { class: 'campo' }, el('label', {}, 'Tipo'), tipo),
      el('div', { class: 'campo' }, el('label', {}, 'Variação'), variacao)),
    el('div', { class: 'ajuda', html: it.tipo_sugerido ? `Tipo sugerido pelo nome do arquivo: ${esc(nomeTipo(it.tipo_sugerido))}.` : 'Variação 0 é o kit normal; outros números são versões alternativas do mesmo tipo.' }),
  ];
}

function desenharPropriedades() {
  const p = $('#propriedades');
  const aberto = {};
  p.querySelectorAll('details.secao').forEach((d) => { aberto[d.dataset.k] = d.open; });
  const foco = document.activeElement && p.contains(document.activeElement) ? document.activeElement : null;
  if (foco && foco.tagName === 'INPUT') return;      // não redesenha enquanto o usuário digita
  p.innerHTML = '';
  const it = itemSel();
  if (it) {
    const cab = el('div', { class: 'prop-cab' }, el('h3', { title: it.caminho }, nomeArq(it.caminho)), el('div', { class: 'sub' }, it.caminho));
    const et = el('div', { class: 'etiquetas' });
    if (!it.erro) et.append(tipoTag(it.tipo), el('span', { class: 'etiqueta' }, `${it.largura}×${it.altura}`));
    else et.append(el('span', { class: 'etiqueta' }, 'imagem ilegível'));
    const [, rot] = EST[it.estado] || EST.pronto;
    et.append(el('span', { class: `etiqueta ${it.estado === 'ok' ? 'verde' : it.estado === 'erro' ? 'vermelha' : it.estado === 'convertendo' ? 'azul' : ''}` }, rot));
    cab.append(et);
    p.append(cab);
    const det = [];
    if (!it.erro) {
      det.push(...campoTime(it));
      if (it.quadrada === false) det.push(nota('A textura do kit do PES é quadrada (2048×2048 ou 1024×1024): esta não é. Confira se é mesmo um kit do PES.', 'alerta'));
    } else det.push(nota(`Não foi possível ler a imagem: ${esc(it.erro)}`, 'alerta'));
    if (it.saida) {
      det.push(el('div', { class: 'campo' }, el('label', {}, it.estado === 'ok' ? 'Gravado em' : 'Vai ser gravado em'), el('div', { class: 'caminho-saida' }, it.saida_feita || it.saida)));
      if (it.existe && it.estado !== 'ok') det.push(nota(S.opcoes.substituir ? 'Esse kit já existe na saída: a pasta dele será substituída.' : 'Esse kit já existe na saída: ligue <b>Substituir kits existentes</b> ou ele será pulado.', 'alerta'));
    }
    if (it.motivo && !it.erro) det.push(nota(esc(it.motivo[0].toUpperCase() + it.motivo.slice(1)) + '.', 'alerta'));
    if (it.estado === 'erro' && it.mensagem) det.push(nota(`<b>Erro:</b> <span class="mono">${esc(it.mensagem).replace(/\n/g, '<br>')}</span>`, 'erro'));
    if (it.estado === 'ignorado' && it.mensagem) det.push(nota(esc(it.mensagem)));
    if ((it.avisos || []).length) det.push(el('ul', { class: 'lista-avisos' }, ...it.avisos.map((a) => el('li', {}, a))));
    if (it.estado === 'ok') det.push(el('dl', { class: 'kv' }, el('dt', {}, 'Tempo'), el('dd', {}, `${it.segundos} s`)));
    det.push(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', disabled: S.job.rodando || !!it.motivo || !S.ambiente.ok, onclick: () => converter([it.id]) }, icone('play', 12), 'Converter este'),
      el('button', { class: 'btn peq', disabled: !temTime(it) || S.job.rodando || S.itens.length < 2, title: 'Copia o ID e a pasta do time para os kits da lista que ainda não têm time', onclick: () => copiarTime(it, false) }, icone('copiar', 12), 'Time nos outros'),
      el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { caminho: it.saida_feita || it.caminho })) }, icone('externo', 12), it.saida_feita ? 'Mostrar kit' : 'Mostrar arquivo'),
      el('button', { class: 'btn-fantasma peq', disabled: S.job.rodando, onclick: () => remover([it.id]) }, icone('x', 12), 'Tirar da lista')));
    const s1 = secao('Kit selecionado', 'imagem', det);
    s1.dataset.k = 'kit';
    p.append(s1);
  } else {
    p.append(el('div', { class: 'vazio' }, 'Adicione kits do PES para ver os detalhes de cada um aqui.'));
  }
  const s2 = secao('Saída e opções', 'engrenagem', opcoes());
  s2.dataset.k = 'opcoes';
  p.append(s2);
  const s3 = secao('Como funciona', 'ajuda', [el('div', { class: 'mudo', style: { lineHeight: '1.55', fontSize: '12px' }, html: `
    O kit do PES tem camisa, mangas (curtas e longas), gola, calção e meião numa textura só; no FC 27 cada peça tem a sua textura e
    outra UV. A correspondência foi medida nos uniformes em 3D dos dois jogos: cada pixel do FC pega a cor do ponto do kit do PES que
    veste o mesmo lugar do corpo, então listras, escudo, patrocínios e logos das mangas ficam no mesmo lugar e na mesma proporção.<br><br>
    As mangas são medidas em volta do braço (da cava ao punho), porque os braços dos dois jogos têm tamanhos diferentes; onde o FC
    encolhe a textura (calção e meião) a cor é filtrada para não serrilhar.<br><br>
    Do kit base do FC 27 vêm o relevo do tecido (normal, coeff, taa, weave), a braçadeira de capitão e o hotspot; o escudo e a marca
    do kit base são apagados, porque o kit do PES já traz os seus desenhados. Os números e nomes nas costas são os do jogo (kitnumbers).` })], false);
  s3.dataset.k = 'ajuda';
  p.append(s3);
  p.querySelectorAll('details.secao').forEach((d) => { if (d.dataset.k in aberto) d.open = aberto[d.dataset.k]; });
}

function opcoes() {
  const op = S.opcoes;
  const out = [];
  const b = S.base;
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Kit base do FC 27'),
    el('div', { class: 'caminho-linha' },
      el('input', { type: 'text', class: 'entrada mono', value: op.base || '', placeholder: '…\\kit\\kit_111000\\guarani_111329\\home_0_0', spellcheck: 'false',
        onchange: (e) => salvarOpcoes({ base: e.target.value.trim() }) }),
      el('button', { class: 'btn', title: 'Escolher a pasta do kit…', onclick: escolherBase }, icone('pasta', 14))),
    b.ok ? el('div', { class: 'base-ok', html: `${icone('check', 12)} ${esc(b.info.time)} · ${esc(nomeTipo(b.info.tipo) || b.info.tipo || '')} · ${b.info.arquivos} arquivos` })
      : el('div', { class: 'ajuda' }, b.erro || ''),
    el('div', { class: 'ajuda', html: 'Um kit qualquer exportado pelo FET (a pasta <i>home_0_0</i>, <i>away_1_0</i>…): dele vêm o tecido, a braçadeira e o hotspot. Prefira um kit liso, sem relevo de listras.' })));
  if (!b.ok && op.base) out.push(nota(esc(b.erro), 'alerta'));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Pasta dos kits (saída)'),
    el('div', { class: 'caminho-linha' },
      el('input', { type: 'text', class: 'entrada mono', value: op.saida || '', placeholder: '“Kits FC 27” ao lado de cada textura (padrão)', spellcheck: 'false',
        onchange: (e) => salvarOpcoes({ saida: e.target.value.trim() }) }),
      el('button', { class: 'btn', title: 'Escolher a pasta…', onclick: escolherSaida }, icone('pasta', 14)),
      el('button', { class: 'btn', title: 'Voltar ao padrão', disabled: !op.saida, onclick: () => salvarOpcoes({ saida: '' }) }, icone('x', 14))),
    el('div', { class: 'ajuda', html: 'Cada kit vai para <i>kit_&lt;faixa&gt;\\&lt;time&gt;_&lt;id&gt;\\&lt;tipo&gt;_&lt;n&gt;_&lt;v&gt;</i>, como o FET exporta. Escolha a pasta <i>kit</i> do mod para gravar direto nela, ou outra para conferir antes.' })));
  const seg = (k, ops) => el('div', { class: 'segmentado' }, ...ops.map(([v, r]) => el('button', { class: op[k] === v ? 'ativo' : '', onclick: () => salvarOpcoes({ [k]: v }) }, r)));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Escudo e marca do kit base'), seg('escudo', [['apagar', 'Apagar'], ['base', 'Manter']]),
    el('div', { class: 'ajuda' }, op.escudo === 'apagar' ? 'O kit do PES já traz escudo e marca desenhados: os do kit base ficam transparentes para não aparecerem duas vezes.'
      : 'Mantém o escudo e a marca do kit base por cima da textura (use se o kit do PES não tiver escudo desenhado).')));
  out.push(el('div', { class: 'campo' }, el('label', {}, 'Tecido (coeff e taa)'), seg('tecido', [['base', 'Do kit base'], ['generico', 'Liso']]),
    el('div', { class: 'ajuda' }, op.tecido === 'base' ? 'Brilho e oclusão do tecido iguais aos do kit base.' : 'Brilho e oclusão lisos (o valor mais comum do kit base), sem os desenhos dele: use se aparecerem sombras de listras que não são do kit do PES.')));
  out.push(interruptor({ titulo: 'Substituir kits existentes', descricao: 'Apaga e grava de novo a pasta de um kit que já existe na saída. Desligado, ele é pulado.',
    marcado: op.substituir, aoMudar: (v) => salvarOpcoes({ substituir: v }) }).el);
  out.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', disabled: !op.saida, onclick: () => tentar(() => api('abrir', {})) }, icone('externo', 12), 'Abrir pasta dos kits'),
    el('button', { class: 'btn peq', disabled: !(S.job.resumo && (S.job.resumo.pastas || []).length), onclick: () => tentar(() => api('relatorio', {})) }, icone('relatorio', 12), 'Relatório')));
  if (S.referencias.ok === false) {
    out.push(nota('A prévia em 3D usa os modelos dos uniformes tirados dos jogos, que não vêm no pacote leve (a conversão não precisa deles).', ''),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: referenciasFaltando }, icone('baixar', 12), 'Importar referências…')));
  }
  if (!S.ambiente.ok && S.ambiente.msg !== 'verificando…') {
    out.push(nota(esc(S.ambiente.msg), 'alerta'));
    if (S.ambiente.instalar) out.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', onclick: componentesMotor }, icone('baixar', 12), 'Baixar os componentes…')));
  }
  return out;
}

async function referenciasFaltando() {
  await importarReferencias({ aoTerminar: () => { S.malhas = {}; atualizar(); } });
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
  const r = await tentar(() => api('opcoes', d));
  if (!r) return;
  aplicar(r);
  if ('saida' in d || 'base' in d) carregarTimes();
}
async function escolherSaida() {
  const r = await tentar(() => api('dialogo', { modo: 'saida' }));
  if (r && r.caminhos.length) await salvarOpcoes({ saida: r.caminhos[0] });
}
async function escolherBase() {
  const r = await tentar(() => api('dialogo', { modo: 'base' }));
  if (r && r.caminhos.length) await salvarOpcoes({ base: r.caminhos[0] });
}

// ---------------------------------------------------------------- ações
async function adicionar(modo) {
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
  aviso(`${novos} ${novos === 1 ? 'kit adicionado' : 'kits adicionados'}`, { tipo: 'sucesso', tempo: 2600,
    detalhe: S.itens.slice(-novos).some((i) => !temTime(i)) ? 'Informe o ID e a pasta do time de cada kit (painel à direita).' : null });
  if (ult) { S.sel = null; selecionar(ult.id); desenharLista(); }
  if (!S.base.ok) aviso('Escolha o kit base do FC 27', { tipo: 'aviso', tempo: 8000, detalhe: 'A pasta de um kit exportado pelo FET: dele vêm o tecido, a braçadeira e o hotspot.', acao: { rotulo: 'Escolher…', fn: escolherBase } });
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
  if (!S.base.ok) {
    aviso('Escolha antes o kit base do FC 27.', { tipo: 'aviso' });
    await escolherBase();
    if (!S.base.ok) return;
  }
  if (S.itens.some((i) => i.recebido) && !S.opcoes.saida) {
    aviso('Escolha a pasta dos kits: arquivos arrastados para a janela não têm “pasta ao lado”.', { tipo: 'aviso' });
    await escolherSaida();
    if (!S.opcoes.saida) return;
  }
  const r = await tentar(() => api('converter', ids ? { ids } : {}));
  if (!r) return;
  S._acompanhando = true;
  aplicar(r);
  if (!r.iniciado) aviso(r.ignorados ? `Nada para converter: ${r.ignorados} kit(s) pulados (veja o motivo em cada um).` : 'Nada para converter.', { tipo: 'aviso' });
  else if (r.ignorados) aviso(`${r.ignorados} kit(s) pulados (sem time ou já existentes).`, { tipo: 'info' });
}
async function cancelar() { aplicar(await tentar(() => api('cancelar', {}))); }

// ---------------------------------------------------------------- prévia (3D ou plana)
function definirQual(q, recarregar = true) {
  S.qual = q;
  document.querySelectorAll('#seg-qual button').forEach((b) => b.classList.toggle('ativo', b.dataset.qual === q));
  $('#seg-peca').hidden = q !== 'saida' || S.modo !== 'plano';
  if (recarregar) carregarPrevia();
}
function definirPeca(p) {
  S.peca = p;
  document.querySelectorAll('#seg-peca button').forEach((b) => b.classList.toggle('ativo', b.dataset.peca === p));
  carregarPrevia();
}
function definirModo(m) {
  if (m === '3d' && !pode3d(S.qual)) {
    aviso('A prévia 3D precisa dos modelos dos uniformes', { tipo: 'aviso', tempo: 8000, detalhe: 'Eles não vêm no pacote leve: importe do pacote completo.', acao: { rotulo: 'Importar…', fn: referenciasFaltando } });
    return;
  }
  S.modo = m;
  document.querySelectorAll('#seg-modo button').forEach((b) => b.classList.toggle('ativo', b.dataset.modo === m));
  $('#btn-girar').disabled = $('#btn-enquadrar').disabled = m !== '3d';
  $('#seg-peca').hidden = S.qual !== 'saida' || m !== 'plano';
  carregarPrevia();
}
async function malha(qual) {
  if (!S.malhas[qual]) S.malhas[qual] = await api(`malha?qual=${qual}`);
  return S.malhas[qual];
}
async function textura(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).erro || 'Não foi possível carregar a textura.');
  return URL.createObjectURL(await r.blob());
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
  let modo = S.modo;
  if (modo === '3d' && !pode3d(qual)) modo = 'plano';
  const n = ++pedidoPrevia;
  const plano = modo === 'plano';
  $('#plano').hidden = !plano;
  $('#tela').style.visibility = plano ? 'hidden' : '';
  $('#seg-peca').hidden = qual !== 'saida' || !plano;
  const v = encodeURIComponent(qual === 'saida' ? S.job.fim || '' : '');
  const url = (q) => `imagem?id=${it.id}&qual=${q}&t=${v}`;
  const fim = carregando(plano ? 'Carregando a textura…' : 'Vestindo o kit…');
  try {
    if (plano) {
      const img = $('#plano-img');
      const u = url(qual === 'saida' ? S.peca : 'entrada');
      img.classList.toggle('retangulo', qual === 'saida' && S.peca !== 'jersey');
      await new Promise((ok, falha) => {
        img.onload = ok;
        img.onerror = async () => { const r = await fetch(u).then((x) => x.json()).catch(() => null); falha(new Error(r?.erro || 'Não foi possível carregar a imagem.')); };
        img.src = u;
      });
    } else {
      if (!S.previa) S.previa = new Previa($('#tela'));
      const quais = qual === 'saida' ? ['jersey', 'shorts', 'socks'] : ['pes'];
      const malhas = await Promise.all(quais.map(malha));
      if (n !== pedidoPrevia) return;
      const blobs = await Promise.all(quais.map((q) => textura(url(q === 'pes' ? 'entrada' : q))));
      if (n !== pedidoPrevia) { blobs.forEach(URL.revokeObjectURL); return; }
      await S.previa.mostrar(qual, quais.map((q, i) => ({ malha: malhas[i], url: blobs[i] })));
      blobs.forEach(URL.revokeObjectURL);
    }
    if (n !== pedidoPrevia) return;
    rot.hidden = false;
    const nome = qual === 'saida' ? `${it.time}_${it.teamid} · ${TIPO_CURTO[it.tipo]}` : nomeArq(it.caminho);
    rot.innerHTML = `<b>${esc(nome)}</b> · ${qual === 'saida' ? 'convertido para o FC 27' : 'kit do PES 2021'}${plano ? (qual === 'saida' ? ' · ' + PECAS.find((x) => x[0] === S.peca)[1].toLowerCase() : '') : ' · 3D'}`;
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
    if (!arqs.length) { aviso('Solte imagens (.png, .dds, .tga, .jpg). Para pastas inteiras, use Adicionar pasta.', { tipo: 'aviso' }); return; }
    const fim = carregando(`Recebendo ${arqs.length} arquivo(s)…`);
    try {
      const arquivos = [];
      for (const f of arqs) arquivos.push({ nome: f.name, dados: await lerArquivoBase64(f) });
      const r = await api('receber', { arquivos });
      aplicar(r);
      posAdicionar(r.novos);
      if (!S.opcoes.saida) aviso('Arquivos arrastados não têm caminho de origem: escolha a pasta dos kits antes de converter.', { tipo: 'info', tempo: 6000 });
    } catch (err) { aviso(err.message, { tipo: 'erro' }); } finally { fim(); }
  });
}

// ---------------------------------------------------------------- menus / ajuda
function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { rotulo: 'Adicionar kits do PES…', icone: 'arquivoMais', atalho: 'Ctrl+O', fn: () => adicionar('arquivos') },
      { rotulo: 'Adicionar pasta…', icone: 'pastaMais', atalho: 'Ctrl+Shift+O', fn: () => adicionar('pasta') },
      '-',
      { rotulo: 'Escolher kit base do FC 27…', icone: 'pasta', fn: escolherBase },
      { rotulo: 'Escolher pasta dos kits…', icone: 'pasta', fn: escolherSaida },
      { rotulo: 'Importar referências (prévia 3D)…', icone: 'baixar', desabilitado: S.referencias.ok !== false, fn: referenciasFaltando },
      { rotulo: 'Abrir pasta dos kits', icone: 'externo', desabilitado: !S.opcoes.saida, fn: () => tentar(() => api('abrir', {})) },
      { rotulo: 'Abrir relatório da última conversão', icone: 'relatorio', desabilitado: !(S.job.resumo && (S.job.resumo.pastas || []).length), fn: () => tentar(() => api('relatorio', {})) },
      '-',
      { rotulo: 'Limpar a lista', icone: 'x', desabilitado: !S.itens.length || S.job.rodando, fn: limpar },
    ]],
    ['Converter', () => [
      { rotulo: 'Converter todos', icone: 'play', atalho: 'Ctrl+Enter', desabilitado: S.job.rodando || !S.ambiente.ok, fn: () => converter() },
      { rotulo: 'Converter o selecionado', icone: 'play', desabilitado: S.job.rodando || !itemSel() || !!itemSel()?.motivo, fn: () => converter([S.sel]) },
      { rotulo: 'Parar', icone: 'parar', desabilitado: !S.job.rodando, fn: cancelar },
      '-',
      { cabecalho: 'Escudo e marca do kit base' },
      { rotulo: 'Apagar (o kit do PES já tem)', marcado: S.opcoes.escudo === 'apagar', fn: () => salvarOpcoes({ escudo: 'apagar' }) },
      { rotulo: 'Manter', marcado: S.opcoes.escudo === 'base', fn: () => salvarOpcoes({ escudo: 'base' }) },
    ]],
    ['Exibir', () => [
      { rotulo: 'Kit do PES', marcado: S.qual === 'entrada', fn: () => definirQual('entrada') },
      { rotulo: 'Kit convertido (FC 27)', marcado: S.qual === 'saida', desabilitado: !itemSel()?.saida_feita, fn: () => definirQual('saida') },
      '-',
      { rotulo: 'Vestido (3D)', marcado: S.modo === '3d', fn: () => definirModo('3d') },
      { rotulo: 'Textura plana', marcado: S.modo === 'plano', fn: () => definirModo('plano') },
      '-',
      { rotulo: 'Girar sozinho', marcado: S.previa?.girando, desabilitado: S.modo !== '3d', fn: alternarGiro },
      { rotulo: 'Enquadrar', atalho: 'F', desabilitado: S.modo !== '3d', fn: () => S.previa?.enquadrar() },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Atalhos do teclado', icone: 'teclado', atalho: 'F1', fn: atalhos },
      { rotulo: 'Sobre o conversor', icone: 'info', fn: sobre },
    ]],
  ]);
}
function alternarGiro() { if (!S.previa) return; S.previa.definirGiro(!S.previa.girando); $('#btn-girar').classList.toggle('ativo', S.previa.girando); }
function atalhos() {
  const t = el('div', { class: 'tabela-atalhos' });
  for (const [g, itens] of [['Lista', [['Adicionar kits', 'Ctrl+O'], ['Adicionar pasta', 'Ctrl+Shift+O'], ['Kit anterior/próximo', '↑ / ↓'], ['Tirar da lista', 'Delete']]],
    ['Conversão', [['Converter todos', 'Ctrl+Enter']]],
    ['Prévia', [['Girar a câmera', 'arrastar'], ['Aproximar', 'roda do mouse'], ['Enquadrar', 'F'], ['PES / FC 27', 'Tab'], ['3D / plana', 'P']]]]) {
    t.append(el('h4', {}, g));
    for (const [rot, k] of itens) t.append(el('div', {}, el('span', {}, rot), el('span', { html: `<kbd>${esc(k)}</kbd>` })));
  }
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
function sobre() {
  dialogoSobre({ nome: 'Conversor de Kits PES → FC', versao: S.versao, html: `
    Converte kits do PES 2021 (a textura única com camisa, mangas, gola, calção e meião) em kits do FC 27: camisa, calção e meião
    no layout do jogo, refeitos pela superfície 3D dos uniformes dos dois jogos, na pasta do kit no formato do FET, com o tecido e
    o hotspot de um kit base.<br><br>
    <b>1.0</b> — lista de kits com time, tipo e variação, kit base, pasta dos kits, escudo/marca do kit base apagados ou mantidos,
    prévia plana e em 3D (com as referências do pacote completo), arrastar e soltar.<br><br>
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
  $('#soltar-ic').innerHTML = icone('converter', 64);
  $('#btn-vazio-arq').innerHTML = icone('arquivoMais', 15) + 'Adicionar kits…';
  $('#btn-vazio-pasta').innerHTML = icone('pastaMais', 15) + 'Adicionar pasta…';
  $('#btn-cancelar').innerHTML = icone('parar', 13) + 'Parar';
  $('#btn-girar').innerHTML = icone('girar', 16);
  $('#btn-enquadrar').innerHTML = icone('maximizar', 16);
  $('#btn-add-arq').onclick = () => adicionar('arquivos');
  $('#btn-add-pasta').onclick = () => adicionar('pasta');
  $('#btn-vazio-arq').onclick = () => adicionar('arquivos');
  $('#btn-vazio-pasta').onclick = () => adicionar('pasta');
  $('#btn-limpar').onclick = limpar;
  $('#btn-converter').onclick = () => converter();
  $('#btn-cancelar').onclick = cancelar;
  $('#btn-girar').onclick = alternarGiro;
  $('#btn-enquadrar').onclick = () => S.previa?.enquadrar();
  $('#btn-girar').disabled = $('#btn-enquadrar').disabled = true;
  document.querySelectorAll('#seg-qual button').forEach((b) => { b.onclick = () => definirQual(b.dataset.qual); });
  document.querySelectorAll('#seg-peca button').forEach((b) => { b.onclick = () => definirPeca(b.dataset.peca); });
  document.querySelectorAll('#seg-modo button').forEach((b) => { b.onclick = () => definirModo(b.dataset.modo); });
  $('#busca').addEventListener('input', () => { desenharLista(); desenharStatus(); });
  $('#filtro').addEventListener('change', () => { desenharLista(); desenharStatus(); });
  divisorArrastavel($('#div-esq'), '--esq', { min: 240, max: 560 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 300, max: 560, lado: 'dir' });
  prepararSoltar();
  menus();
  const r = await api('inicio');
  S.versao = r.versao;
  $('#versao').textContent = r.versao;
  S.ultimoResumo = r.job && r.job.fim ? r.job.fim : null;
  aplicar(r);
  if (pode3d('entrada')) definirModo('3d');
  else if (S.itens.length) carregarPrevia();
  carregarTimes();
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
