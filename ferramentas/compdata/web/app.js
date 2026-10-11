// Editor de Compdata — interface (BRFP Super Tool).
// Regra do app: toda edição altera só a memória do servidor. O disco só é tocado pelo Salvar, que grava um backup antes.
import { $, el, esc, aviso, modal, confirmar, barraMenus, campo, divisorArrastavel, dialogoSobre, modalAberto, menuAberto } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api as chamar } from './comum/api.js';

const S = {
  nodes: [], byId: new Map(), kids: new Map(), expanded: new Set(), sel: null, tab: null, node: null,
  vocab: null, teams: [], teamName: new Map(), issues: { errors: [], warnings: [] }, estado: { aberto: false },
  recentes: [], versao: '',
};
const TIPO = { '-1': 'Reservado', 0: 'Mundo', 1: 'Confederação', 2: 'País', 3: 'Competição', 4: 'Estágio', 5: 'Grupo', 6: 'Competição especial' };
const TIPO_IC = { '-1': 'menos', 0: 'mundo', 1: 'camadas', 2: 'campo', 3: 'trofeu', 4: 'lista', 5: 'grade', 6: 'trofeu' };

// ---------------------------------------------------------------- servidor
async function acao(action, dados = {}) {
  const r = await chamar('acao', { action, ...dados });
  if (r.state) aplicarEstado(r.state);
  return r;
}
const get = (rota) => chamar(rota);

async function tentar(fn) {
  try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; }
}

// diálogo com campos [data-k]: devolve {k: valor} ou null
function dialogo(titulo, corpo, rotuloOk = 'Confirmar', { perigo = false, largo = false, texto = '' } = {}) {
  const c = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } }, ...[].concat(corpo));
  return modal({
    titulo, texto, corpo: c, largo,
    botoes: [
      { rotulo: 'Cancelar', classe: 'btn', valor: null },
      { rotulo: rotuloOk, classe: perigo ? 'btn-perigo' : 'btn-primario', padrao: true, fn: () => coletar(c) },
    ],
  }).promessa;
}
function coletar(c) {
  const out = {};
  c.querySelectorAll('[data-k]').forEach((e) => { out[e.dataset.k] = e.type === 'checkbox' ? e.checked : e.value; });
  return out;
}
const inp = (attrs) => el('input', { type: 'text', spellcheck: 'false', autocomplete: 'off', ...attrs });

// ---------------------------------------------------------------- estado / topo / rodapé
function aplicarEstado(st) {
  S.estado = st;
  $('#app').classList.toggle('sem-pasta', !st.aberto);
  if (!st.aberto) {
    $('#titulo').innerHTML = '<span class="mudo">Nenhuma pasta aberta</span>';
    $('#sujo').hidden = true;
    ['#btn-desfazer', '#btn-refazer', '#btn-salvar'].forEach((s) => { $(s).disabled = true; });
    $('#contagens').innerHTML = '';
    $('#chip-validacao').hidden = true;
    return;
  }
  S.issues = { errors: st.errors, warnings: st.warnings };
  S.clip = st.clipboard || null;
  const nome = st.path.split(/[\\/]/).filter(Boolean).pop();
  $('#titulo').innerHTML = `<b>${esc(nome)}</b><span class="pasta" title="${esc(st.path)}">${esc(st.path)}</span>`;
  $('#sujo').hidden = !st.dirty;
  $('#btn-desfazer').disabled = !st.can_undo;
  $('#btn-refazer').disabled = !st.can_redo;
  $('#btn-salvar').disabled = !st.dirty;
  const bc = $('#btn-colar');
  bc.disabled = !S.clip || !S.node;
  bc.title = S.clip ? `Colar “${S.clip}” como filho deste nó (Ctrl+V)` : 'Nada copiado ainda';
  const chip = $('#chip-validacao');
  chip.hidden = false;
  const ne = st.errors.length, nw = st.warnings.length;
  chip.className = 'chip ' + (ne ? 'erro' : nw ? 'aviso' : 'ok');
  chip.innerHTML = icone(ne || nw ? 'aviso' : 'check', 12) + (ne ? `${ne} ${ne === 1 ? 'erro' : 'erros'}${nw ? ` · ${nw} avisos` : ''}`
    : nw ? `${nw} ${nw === 1 ? 'aviso' : 'avisos'}` : 'tudo consistente');
  const cont = $('#contagens');
  cont.innerHTML = '';
  for (const k of ['compobj', 'compids', 'settings', 'standings', 'advancement', 'schedule', 'tasks', 'objectives', 'initteams', 'weather']) {
    if (!(k in st.counts)) continue;
    const d = st.counts[k] - (st.baseline[k] ?? st.counts[k]);
    cont.append(el('span', { title: `${k}.txt — ${st.counts[k]} linhas` }, el('b', {}, k.slice(0, 4)), ' ' + st.counts[k],
      d ? el('span', { class: d > 0 ? 'sobe' : 'desce' }, ` ${d > 0 ? '+' : ''}${d}`) : null));
  }
  const fontes = st.fontes_nomes || [];
  $('#planilha').textContent = fontes.length ? `${st.n_times} times · ${fontes.length > 1 ? fontes.length + ' fontes de nomes' : fontes[0]}` : 'sem nomes (importe o banco e o idioma no Super Tool)';
  $('#planilha').title = fontes.length ? 'Nomes vindos de: ' + fontes.join(', ') + '\n(o banco e o idioma são importados em Dados do jogo, no Super Tool)'
    : 'Importe o banco e o idioma em Dados do jogo (Super Tool), ou coloque a planilha .xlsx com abas "Times" e "Competições" na pasta';
}

// ---------------------------------------------------------------- árvore
async function carregarArvore(manterSel = true) {
  const data = await get('tree');
  S.nodes = data.nodes;
  S.byId = new Map(S.nodes.map((n) => [n.id, n]));
  S.kids = new Map();
  for (const n of S.nodes) {
    if (!S.kids.has(n.parent)) S.kids.set(n.parent, []);
    S.kids.get(n.parent).push(n.id);
  }
  aplicarEstado(data.state);
  $('#contagem-nos').textContent = S.nodes.length.toLocaleString('pt-BR') + ' nós';
  desenharArvore();
  if (manterSel && S.sel !== null && S.byId.has(S.sel)) await selecionar(S.sel);
}

function desenharArvore() {
  const q = $('#busca').value.trim().toLowerCase();
  let achados = null;
  if (q) {
    achados = new Set();
    for (const n of S.nodes) {
      if (`${n.id} ${n.short} ${n.desc} ${n.label}`.toLowerCase().includes(q)) {
        achados.add(n.id);
        let p = n.parent;
        while (p >= 0) { S.expanded.add(p); p = S.byId.get(p)?.parent ?? -1; }
      }
    }
  }
  const arv = $('#arvore');
  arv.innerHTML = '';
  const raizes = (S.kids.get(-1) || []).filter((id) => S.byId.get(id).type !== -1);
  const reserva = (S.kids.get(-1) || []).filter((id) => S.byId.get(id).type === -1);
  for (const r of raizes) andar(r, 0, arv, achados);
  // linhas reservadas (tipo -1) só ocupam posição no compobj: ficam num grupo recolhido
  if (reserva.length && (!achados || reserva.some((id) => achados.has(id)))) {
    const aberto = S.expanded.has('reserva');
    arv.append(el('button', { class: 'linha-arv reservado', style: { paddingLeft: '6px' }, onclick: () => alternar('reserva') },
      el('span', { class: `exp ${aberto ? 'aberto' : ''}`, html: icone('seta', 12) }),
      el('span', { class: 'tipo t-1', html: icone('menos', 14) }),
      el('span', { class: 'nome' }, 'Linhas reservadas'),
      el('span', { class: 'qtd' }, reserva.length)));
    if (aberto) for (const id of reserva) andar(id, 1, arv, achados);
  }
  if (achados && !achados.size) arv.append(el('div', { class: 'arvore-vazia' }, 'Nada encontrado.'));
}

function temAchado(id, achados) {
  if (achados.has(id)) return true;
  for (const k of (S.kids.get(id) || [])) if (temAchado(k, achados)) return true;
  return false;
}

function andar(id, prof, dentro, achados) {
  const n = S.byId.get(id);
  if (!n) return;
  if (achados && !temAchado(id, achados)) return;
  const filhos = S.kids.get(id) || [];
  const aberto = S.expanded.has(id);
  const linha = el('button', {
    class: `linha-arv t${n.type} ${S.sel === id ? 'sel' : ''} ${achados && achados.has(id) ? 'achado' : ''} ${n.type === -1 ? 'reservado' : ''}`,
    role: 'treeitem', 'data-id': id, style: { paddingLeft: `${6 + prof * 14}px` },
    title: `${n.short} — ${n.desc || '—'}  (nó ${n.id})`,
    onclick: (e) => { if (!e.target.closest('.exp')) selecionar(id); },
    ondblclick: (e) => { if (!e.target.closest('.exp') && filhos.length) alternar(id); },
  },
  el('span', { class: `exp ${aberto ? 'aberto' : ''} ${filhos.length ? '' : 'folha'}`, html: icone('seta', 12),
    onclick: (e) => { e.stopPropagation(); alternar(id); } }),
  el('span', { class: `tipo t${n.type}`, html: icone(TIPO_IC[n.type] || 'cubo', 14) }),
  el('span', { class: 'nome' }, n.label, n.type >= 3 && n.short !== n.label ? el('span', { class: 'tec' }, n.short) : null),
  el('span', { class: 'qtd' }, n.type === 5 && n.slots ? `${n.slots}` : (filhos.length ? `${filhos.length}` : '')));
  dentro.append(linha);
  if (aberto) for (const k of filhos) andar(k, prof + 1, dentro, achados);
}

function alternar(id) {
  if (S.expanded.has(id)) S.expanded.delete(id); else S.expanded.add(id);
  desenharArvore();
}

function revelar(id) {
  let p = S.byId.get(id)?.parent ?? -1;
  while (p >= 0) { S.expanded.add(p); p = S.byId.get(p)?.parent ?? -1; }
  desenharArvore();
  selecionar(id);
  const e = $('#arvore .linha-arv.sel');
  if (e) e.scrollIntoView({ block: 'nearest' });
}

// ---------------------------------------------------------------- detalhe do nó
async function selecionar(id) {
  S.sel = id;
  $$('#arvore .linha-arv').forEach((e) => e.classList.toggle('sel', +e.dataset.id === id));
  const d = await tentar(() => get('node?id=' + id));
  if (!d) return;
  S.node = d;
  $('#vazio').hidden = true;
  $('#boas-vindas').hidden = true;
  $('#no').hidden = false;
  $('#no-tipo').textContent = TIPO[d.type] ?? d.type;
  $('#no-tipo').className = 'etiqueta ' + ({ 3: 'laranja', 6: 'laranja', 4: 'azul', 5: '' }[d.type] || '');
  $('#no-titulo').textContent = d.label;
  $('#no-sub').textContent = `nó ${d.id} · sigla ${d.short}` + (d.desc.trim() ? ` · ${d.desc.trim()}` : '');
  const mig = $('#migalhas');
  mig.innerHTML = '';
  d.path.forEach((p, i) => {
    if (i) mig.append(el('span', {}, '›'));
    mig.append(el('button', { onclick: () => revelar(p.id) }, p.label));
  });
  const movel = d.type >= 3;
  $('#btn-cima').disabled = !movel;
  $('#btn-baixo').disabled = !movel;
  $('#btn-excluir').disabled = d.type <= 2;
  $('#btn-copiar').disabled = d.type === 0 || d.type === -1;
  $('#btn-colar').disabled = !S.clip;
  desenharAbas(d);
}

function abasDe(d) {
  const t = [['geral', 'Geral', null, 'info']];
  if (d.type === 5) {
    t.push(['vagas', 'Vagas', d.slots, 'grade']);
    t.push(['times', 'Times', d.teams.length, 'torcida']);
    t.push(['avancos', 'Avanços', d.adv_in.length + d.adv_out.length, 'converter']);
  }
  if (d.type === 4 || d.type === 5) t.push(['calendario', 'Calendário', d.schedule.length, 'calendario']);
  if (d.type === 3 || d.type === 6) t.push(['tasks', 'Tasks', d.tasks.length, 'lista']);
  t.push(['ajustes', 'Ajustes', d.settings.length, 'engrenagem']);
  if (d.children.length || d.type !== 5) t.push(['filhos', rotuloFilhos(d), d.children.length, 'arvore']);
  if (d.type === 5 || d.type === 3 || d.type === 6) t.push(['extras', 'Objetivos', d.objectives.length + d.initteams.length, 'alvo']);
  return t;
}

function rotuloFilhos(d) {
  if (d.type <= 2) return 'Competições';
  if (d.type === 3) return 'Estágios';
  return 'Grupos';   // competição especial (C90001…) pendura grupo direto, sem estágio
}

function desenharAbas(d) {
  const abas = abasDe(d);
  if (!abas.some((t) => t[0] === S.tab)) S.tab = abas[0][0];
  const nav = $('#abas');
  nav.innerHTML = '';
  for (const [k, rot, n, ic] of abas) {
    nav.append(el('button', { class: `aba ${S.tab === k ? 'ativa' : ''}`, role: 'tab', 'aria-selected': String(S.tab === k),
      onclick: () => { S.tab = k; desenharAbas(S.node); } },
    icone(ic, 14), rot, n !== null && n !== undefined ? el('span', { class: 'n' }, n) : null));
  }
  const p = $('#painel-aba');
  p.innerHTML = '';
  ({ geral: abaGeral, ajustes: abaAjustes, vagas: abaVagas, times: abaTimes, calendario: abaCalendario,
    avancos: abaAvancos, tasks: abaTasks, filhos: abaFilhos, extras: abaExtras }[S.tab] || abaGeral)(p, d);
}

function cartao(titulo, dica, corpo, extraCab) {
  const justo = corpo && (corpo.tagName === 'TABLE' || corpo.classList?.contains('lista-links'));
  return el('section', { class: 'cartao' },
    el('header', {}, el('div', {}, el('h3', {}, titulo), dica ? el('p', { class: 'dica' }, dica) : null), extraCab || null),
    el('div', { class: `cartao-corpo ${justo ? 'justo' : ''}` }, corpo));
}
const tabela = (cols, tbody) => el('table', { class: 'tabela' }, el('thead', {}, el('tr', {}, ...cols.map((c) => el('th', {}, c)))), tbody);
const btnLinha = (fn) => el('button', { class: 'btn-linha', title: 'Remover', html: icone('apagar', 14), onclick: fn });
const btnNova = (rot, fn) => el('button', { class: 'btn peq', onclick: fn }, icone('mais', 13), rot);
const vaziaLinha = (n, txt) => el('tr', {}, el('td', { colspan: String(n) }, el('div', { class: 'vazia' }, txt)));

// ---------------------------------------------------------------- aba Geral
function abaGeral(p, d) {
  const sigla = inp({ class: 'mono', value: d.short });
  const desc = inp({ class: 'mono', value: d.desc });
  const gravar = () => tentar(async () => { await acao('update_node', { id: d.id, short: sigla.value, desc: desc.value }); await carregarArvore(); });
  sigla.addEventListener('change', gravar);
  desc.addEventListener('change', gravar);
  p.append(cartao('Identidade', 'A sigla aparece no jogo; a descrição é a chave de tradução.', el('div', { class: 'grade2' },
    campo('Sigla', sigla, d.type >= 3 ? 'C1509, S2, G4…' : ''),
    campo('Descrição / string', desc, 'FCE_Group_A, FCE_Semi_Finals…'),
    campo('Tipo', inp({ readonly: true, value: TIPO[d.type] })),
    campo('ID do nó', inp({ class: 'mono', readonly: true, value: d.id }), 'É o número da linha no compobj — muda sozinho quando algo é inserido antes.'))));
  if (d.type === 3 || d.type === 6) {
    const s = Object.fromEntries(d.settings);
    p.append(cartao('Resumo', null, el('div', { class: 'estatisticas' },
      ...[['asset_id', s.asset_id || '—'], ['comp_type', s.comp_type || '—'], ['Estágios', d.children.length], ['Tasks', d.tasks.length]]
        .map(([k, v]) => el('div', { class: 'estatistica' }, el('b', {}, String(v)), el('span', {}, k))))));
  }
}

// ---------------------------------------------------------------- aba Ajustes (settings)
const DICAS_CHAVE = ['match_stagetype', 'match_matchsituation', 'num_games', 'num_limited_games', 'schedule_matchup_behavior',
  'standings_sort', 'asset_id', 'comp_type', 'info_prize_money', 'info_prize_money_drop', 'info_slot_champ', 'info_slot_promo',
  'info_slot_releg', 'info_label_slot_adv_group', 'info_special_team_id', 'match_endruleko1leg', 'match_endruleko2leg2',
  'match_matchimportance', 'schedule_internationaldependency', 'schedule_checkconflict', 'info_league_promo',
  'info_league_releg', 'rule_suspension', 'nation_id'];
const OPCOES_VALOR = {
  match_stagetype: () => S.vocab.stage_types,
  match_matchsituation: () => S.vocab.situations,
  comp_type: () => S.vocab.comp_kinds,
  standings_sort: () => S.vocab.sort_keys,
  match_endruleko2leg2: () => ['AGG', 'AWAY', 'ET', 'ET_AWAY', 'PENS'],
  match_endruleko1leg: () => ['ET', 'PENS'],
  schedule_internationaldependency: () => ['NONE', '0', '1'],
  schedule_matchup_behavior: () => ['BASIC', 'LIMITED_SHUFFLED_ROUND_ROBIN'],
};

function abaAjustes(p, d) {
  const linhas = d.settings.map((r) => r.slice());
  const gravar = () => tentar(async () => { await acao('set_settings', { id: d.id, rows: linhas.filter((r) => r[0].trim()) }); await selecionar(d.id); });
  const tbody = el('tbody');
  const desenhar = () => {
    tbody.innerHTML = '';
    if (!linhas.length) tbody.append(vaziaLinha(4, 'Nenhum ajuste neste nó.'));
    linhas.forEach((r, i) => {
      const ehNo = S.vocab.setting_node_keys.includes(r[0]);
      const ops = OPCOES_VALOR[r[0]];
      const chave = inp({ class: 'mono', list: 'dicas-chave', value: r[0], onchange: (e) => { linhas[i][0] = e.target.value.trim(); desenhar(); gravar(); } });
      const valor = ops
        ? el('select', { class: 'mono', onchange: (e) => { linhas[i][1] = e.target.value; gravar(); } },
          ...ops().concat(ops().includes(r[1]) ? [] : [r[1]]).map((o) => { const op = el('option', { value: o }, o); op.selected = o === r[1]; return op; }))
        : inp({ class: 'mono', value: r[1], onchange: (e) => { linhas[i][1] = e.target.value.trim(); gravar(); } });
      tbody.append(el('tr', {}, el('td', {}, chave), el('td', {}, valor),
        el('td', { class: 'encolher' }, ehNo ? el('span', { class: 'etiqueta amarela', title: 'O valor é um ID de nó e é remapeado sozinho' }, 'nó') : null),
        el('td', { class: 'encolher' }, btnLinha(() => { linhas.splice(i, 1); desenhar(); gravar(); }))));
    });
  };
  desenhar();
  p.append(cartao('Ajustes', 'Linhas do settings.txt deste nó, na ordem em que serão gravadas.', tabela(['Chave', 'Valor', '', ''], tbody),
    btnNova('Nova linha', () => { linhas.push(['', '']); desenhar(); tbody.querySelector('tr:last-child input')?.focus(); })));
  p.append(el('datalist', { id: 'dicas-chave' }, ...DICAS_CHAVE.map((k) => el('option', { value: k }))));
}

// ---------------------------------------------------------------- aba Vagas
function abaVagas(p, d) {
  const n = inp({ type: 'number', min: '0', max: '128', value: d.slots });
  p.append(cartao('Vagas do grupo', 'Cada vaga é uma linha no standings.txt. Num grupo de liga é o número de times; num confronto de mata-mata, 2.',
    el('div', { class: 'grade2' }, campo('Quantidade de vagas', n),
      campo('', el('button', { class: 'btn-primario', style: { alignSelf: 'flex-start' }, onclick: () => tentar(async () => {
        await acao('set_slots', { id: d.id, count: parseInt(n.value || '0', 10) });
        aviso('Vagas atualizadas', { tipo: 'sucesso', tempo: 1800 });
        await carregarArvore();
      }) }, 'Aplicar')))));
  const s = Object.fromEntries(d.settings);
  const jogos = parseInt(s.num_games || '1', 10);
  if (d.slots >= 3) {
    const porTime = s.num_limited_games ? parseInt(s.num_limited_games, 10) : (d.slots - 1) * jogos;
    const total = Math.floor(d.slots * porTime / 2);
    const rodadas = d.slots % 2 ? d.slots : d.slots - 1;
    p.append(cartao('O que isso gera', d.slots % 2 ? 'Número ímpar de times: uma folga por rodada.' : null, el('div', { class: 'estatisticas' },
      ...[['Jogos por time', porTime], ['Jogos no total', total], ['Rodadas de um turno', rodadas], ['Jogos por rodada', Math.floor(d.slots / 2)]]
        .map(([k, v]) => el('div', { class: 'estatistica' }, el('b', {}, String(v)), el('span', {}, k))))));
  }
}

// ---------------------------------------------------------------- aba Times
function abaTimes(p, d) {
  const ids = d.teams.map((t) => t.id);
  const gravar = () => tentar(async () => { await acao('set_teams', { id: d.id, teams: ids }); await selecionar(d.id); });
  const pil = el('div', { class: 'pilulas' });
  const desenhar = () => {
    pil.innerHTML = '';
    if (!ids.length) pil.append(el('span', { class: 'mudo' }, 'Nenhum time nesta lista.'));
    ids.forEach((id, i) => pil.append(el('span', { class: 'pilula' }, S.teamName.get(id) || 'time desconhecido', el('span', { class: 'id' }, id),
      el('button', { title: 'Remover', html: icone('x', 12), onclick: () => { ids.splice(i, 1); desenhar(); gravar(); } }))));
  };
  desenhar();
  const busca = inp({ list: 'lista-times', placeholder: 'Nome ou ID do time…' });
  const adicionar = () => {
    const v = busca.value.trim();
    if (!v) return;
    let id = /^\d+$/.test(v) ? parseInt(v, 10) : null;
    if (id === null) {
      const m = S.teams.find((t) => t.name.toLowerCase() === v.toLowerCase()) || S.teams.find((t) => t.name.toLowerCase().includes(v.toLowerCase()));
      if (!m) { aviso('Time não encontrado: ' + v, { tipo: 'erro' }); return; }
      id = m.id;
    }
    if (ids.includes(id)) { aviso('Esse time já está na lista', { tipo: 'aviso' }); return; }
    ids.push(id); busca.value = ''; desenhar(); gravar();
  };
  busca.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); adicionar(); } });
  p.append(cartao('Times do grupo', 'Grava como info_special_team_id. O FillFromSpecialTeams puxa daqui.',
    el('div', { style: { display: 'flex', flexDirection: 'column', gap: '14px' } },
      el('div', { class: 'grade2' }, campo('Adicionar time', busca, 'Digite o nome (autocompleta) ou o ID e tecle Enter.'),
        campo('', el('button', { class: 'btn', style: { alignSelf: 'flex-start' }, onclick: adicionar }, icone('mais', 13), 'Adicionar'))),
      pil),
    el('span', { class: 'chip' }, `${ids.length} / ${d.slots} vagas`)));
  const dicas = [];
  if (d.adv_in.length) dicas.push(el('div', { class: 'link-linha' }, el('span', { class: 'chip ok' }, 'avanços'), el('span', { class: 'cresce' }, `${d.adv_in.length} time(s) chegam por classificação — veja a aba Avanços.`)));
  if (d.teams.length) dicas.push(el('div', { class: 'link-linha' }, el('span', { class: 'chip' }, 'lista fixa'), el('span', { class: 'cresce' }, `${d.teams.length} time(s) em info_special_team_id.`)));
  if (!dicas.length) dicas.push(el('div', { class: 'link-linha' }, el('span', { class: 'chip aviso' }, 'vazio'), el('span', { class: 'cresce' }, 'Nada preenche este grupo ainda.')));
  p.append(cartao('Como este grupo é preenchido', 'Sem uma task apontando para cá, a lista acima não entra em campo.', el('div', { class: 'lista-links' }, ...dicas)));
  p.append(el('datalist', { id: 'lista-times' }, ...S.teams.slice(0, 5000).map((t) => el('option', { value: t.name }))));
}

// ---------------------------------------------------------------- aba Calendário
function abaCalendario(p, d) {
  const linhas = d.schedule.map((r) => r.slice());
  const gravar = () => tentar(async () => { await acao('set_rows', { file: 'schedule', id: d.id, rows: linhas }); await selecionar(d.id); });
  const tbody = el('tbody');
  const desenhar = () => {
    tbody.innerHTML = '';
    if (!linhas.length) tbody.append(vaziaLinha(6, 'Sem datas.'));
    linhas.forEach((r, i) => {
      const cel = (j) => el('td', { class: 'num' }, inp({ type: 'number', value: r[j], onchange: (e) => { linhas[i][j] = e.target.value; gravar(); } }));
      tbody.append(el('tr', {}, cel(1), cel(0), cel(2), cel(3),
        el('td', { class: 'num' }, inp({ class: 'mono', value: r[4], onchange: (e) => { linhas[i][4] = e.target.value; gravar(); } })),
        el('td', { class: 'encolher' }, btnLinha(() => { linhas.splice(i, 1); desenhar(); gravar(); }))));
    });
  };
  desenhar();
  p.append(cartao('Calendário', 'O dia é contado a partir do fim de dezembro do ano anterior. Rodada 1, 2, 3…',
    tabela(['Rodada', 'Dia', 'Mín. jogos', 'Máx. jogos', 'Hora', ''], tbody),
    btnNova('Nova data', () => {
      const u = linhas[linhas.length - 1];
      linhas.push(u ? [String(+u[0] + 1), String(+u[1] + 7), u[2], u[3], u[4]] : ['1', '14', '1', '1', '1900']);
      desenhar(); gravar();
    })));
  if (d.type === 4) {
    const filhos = d.children.filter((c) => c.slots > 1);
    const esperado = filhos.reduce((a, c) => a + Math.floor(c.slots / 2), 0);
    if (esperado) {
      p.append(cartao('Conferência', 'Um calendário no estágio vale para todos os grupos dele.', el('div', { class: 'estatisticas' },
        el('div', { class: 'estatistica' }, el('b', {}, String(esperado)), el('span', {}, `jogos por rodada (${filhos.length} grupos, ${filhos.reduce((a, c) => a + c.slots, 0)} vagas)`)),
        el('div', { class: 'estatistica' }, el('b', {}, String(new Set(linhas.map((r) => r[0])).size)), el('span', {}, 'rodadas cadastradas')))));
    }
  }
}

// ---------------------------------------------------------------- aba Avanços
function abaAvancos(p, d) {
  const linhas = d.adv_in.map((r) => [r.src, r.rank, r.slot]);
  const gravar = () => tentar(async () => { await acao('set_adv', { id: d.id, rows: linhas }); await selecionar(d.id); });
  const tbody = el('tbody');
  const desenhar = () => {
    tbody.innerHTML = '';
    if (!linhas.length) tbody.append(vaziaLinha(5, 'Ninguém chega aqui por classificação.'));
    linhas.forEach((r, i) => {
      const src = S.byId.get(r[0]);
      tbody.append(el('tr', {},
        el('td', { class: 'encolher' }, inp({ type: 'number', class: 'mono', value: r[0], style: { width: '6.5em' }, title: src ? src.label : 'nó inexistente',
          onchange: (e) => { linhas[i][0] = +e.target.value; gravar(); } })),
        el('td', {}, src ? el('button', { class: 'btn-fantasma peq', onclick: () => revelar(src.id) }, `${src.label}`, el('span', { class: 'mudo' }, ` · ${S.byId.get(src.parent)?.label || ''}`))
          : el('span', { class: 'etiqueta vermelha' }, 'nó inexistente')),
        el('td', { class: 'num encolher' }, inp({ type: 'number', value: r[1], style: { width: '5.5em' }, title: '0 = sorteio', onchange: (e) => { linhas[i][1] = +e.target.value; gravar(); } })),
        el('td', { class: 'num encolher' }, inp({ type: 'number', value: r[2], style: { width: '5.5em' }, onchange: (e) => { linhas[i][2] = +e.target.value; gravar(); } })),
        el('td', { class: 'encolher' }, btnLinha(() => { linhas.splice(i, 1); desenhar(); gravar(); }))));
    });
  };
  desenhar();
  p.append(cartao('Quem chega neste grupo', 'Posição 0 significa sorteio a partir do grupo de origem.',
    tabela(['Grupo de origem', '', 'Posição', 'Vaga aqui', ''], tbody),
    btnNova('Nova entrada', () => { linhas.push([d.id, 1, linhas.length + 1]); desenhar(); gravar(); })));
  p.append(cartao('Para onde este grupo manda times', null, el('div', { class: 'lista-links' }, ...(d.adv_out.length
    ? d.adv_out.map((o) => el('button', { class: 'link-linha', onclick: () => revelar(o.dst) },
      el('span', { class: 'chip' }, o.rank === 0 ? 'sorteio' : `${o.rank}º`), el('span', { class: 'cresce' }, `${o.dst_path} › ${o.dst_label}`),
      el('span', { class: 'mono mudo' }, 'vaga ' + o.slot)))
    : [el('div', { class: 'vazio' }, 'Este grupo não classifica ninguém.')]))));
}

// ---------------------------------------------------------------- aba Tasks
function abaTasks(p, d) {
  const linhas = d.tasks.map((r) => r.slice());
  const gravar = () => tentar(async () => { await acao('set_tasks', { id: d.id, rows: linhas }); await selecionar(d.id); });
  const tbody = el('tbody');
  const desenhar = () => {
    tbody.innerHTML = '';
    if (!linhas.length) tbody.append(vaziaLinha(7, 'Nenhuma task — a competição vai começar vazia.'));
    linhas.forEach((r, i) => {
      const camposNo = (S.vocab.task_node_fields || {})[r[1]] || [];
      const cel = (j) => {
        const ref = (j === 2 || camposNo.includes(j + 1)) ? S.byId.get(+r[j]) : null;
        return el('td', {}, inp({ class: 'mono', value: r[j], title: ref ? `nó ${ref.id}: ${ref.label}` : '', onchange: (e) => { linhas[i][j] = e.target.value.trim(); gravar(); } }));
      };
      const sel = (ops, j, cls = '') => el('select', { class: cls, onchange: (e) => { linhas[i][j] = e.target.value; gravar(); } },
        ...ops.concat(ops.includes(r[j]) ? [] : [r[j]]).map((o) => { const op = el('option', { value: o }, o); op.selected = o === r[j]; return op; }));
      tbody.append(el('tr', {}, el('td', { class: 'encolher' }, sel(['start', 'end'], 0)), el('td', {}, sel(S.vocab.task_verbs, 1, 'mono')),
        cel(2), cel(3), cel(4), cel(5), el('td', { class: 'encolher' }, btnLinha(() => { linhas.splice(i, 1); desenhar(); gravar(); }))));
    });
  };
  desenhar();
  p.append(cartao('Tasks', 'Como a competição se enche no começo da temporada. O 1º campo é o grupo de destino.',
    tabela(['Quando', 'Verbo', 'Destino', 'Arg 1', 'Arg 2', 'Arg 3', ''], tbody),
    btnNova('Nova task', () => { linhas.push(['start', 'FillFromLeague', String(d.children[0]?.id ?? d.id), '0', '0', '0']); desenhar(); gravar(); })));
}

// ---------------------------------------------------------------- aba Filhos
function abaFilhos(p, d) {
  const lista = el('div', { class: 'lista-links' }, ...(d.children.length
    ? d.children.map((c) => el('button', { class: 'link-linha', onclick: () => revelar(c.id) },
      el('span', { class: `tipo t${c.type}`, html: icone(TIPO_IC[c.type] || 'cubo', 14), style: { color: 'var(--texto-3)' } }),
      el('span', { class: 'mono mudo' }, c.short), el('span', { class: 'cresce' }, c.label),
      c.slots ? el('span', { class: 'chip' }, c.slots + ' vagas') : null, el('span', { class: 'mono mudo' }, '#' + c.id)))
    : [el('div', { class: 'vazio' }, 'Vazio.')]));
  p.append(cartao(rotuloFilhos(d), 'Novos filhos entram no fim da subárvore, e os IDs seguintes são renumerados.', lista,
    btnNova(rotuloNovo(d), () => novoFilho(d))));
}
function rotuloNovo(d) { return d.type <= 2 ? 'Nova competição' : d.type === 3 ? 'Novo estágio' : 'Novo grupo'; }

async function novoFilho(d) {
  if (!d) return;
  if (d.type <= 2) {
    const ops = [];
    if (d.type === 0) ops.push(['conf', 'Confederação']);
    if (d.type <= 1) ops.push(['pais', 'País']);
    ops.push(['comp', 'Competição (assistente)']);
    if (ops.length === 1) return assistente(d);
    const r = await dialogo('Criar dentro de ' + d.label, campo('O que criar', el('select', { 'data-k': 'what' }, ...ops.map(([v, t]) => el('option', { value: v }, t)))), 'Continuar');
    if (!r) return;
    if (r.what === 'comp') return assistente(d);
    const conf = r.what === 'conf';
    const r2 = await dialogo(conf ? 'Nova confederação' : 'Novo país', el('div', { class: 'grade2' },
      campo('Sigla', inp({ 'data-k': 'short', class: 'mono', value: conf ? 'CONF' : 'PAIS' }), conf ? 'UEFA, AFC…' : 'BRAZ, ARGE…'),
      campo('String', inp({ 'data-k': 'desc', class: 'mono', value: conf ? ' ' : 'NationName_0' }), conf ? '' : 'NationName_&lt;id do país no banco&gt;. O nation_id se ajusta na aba Ajustes.')), 'Criar');
    if (!r2) return;
    await tentar(async () => {
      const res = await acao('add_node', { parent: d.id, type: conf ? 1 : 2, short: r2.short, desc: r2.desc });
      await carregarArvore(false); revelar(res.id);
      aviso(conf ? 'Confederação criada' : 'País criado', { tipo: 'sucesso' });
    });
    return;
  }
  const n = d.children.length + 1;
  if (d.type === 3) {
    const r = await dialogo('Novo estágio', el('div', { class: 'grade2' },
      campo('Sigla', inp({ 'data-k': 'short', class: 'mono', value: 'S' + n })), campo('String', inp({ 'data-k': 'desc', class: 'mono', value: 'FCE_Group_Stage' }))), 'Criar');
    if (!r) return;
    await tentar(async () => {
      const res = await acao('add_node', { parent: d.id, type: 4, short: r.short, desc: r.desc });
      await carregarArvore(false); revelar(res.id);
      aviso('Estágio criado', { tipo: 'sucesso' });
    });
    return;
  }
  const r = await dialogo('Novo grupo', el('div', { class: 'grade2' },
    campo('Sigla', inp({ 'data-k': 'short', class: 'mono', value: 'G' + n })), campo('String', inp({ 'data-k': 'desc', class: 'mono', value: ' ' })),
    campo('Vagas', inp({ 'data-k': 'slots', type: 'number', value: '2' }))), 'Criar');
  if (!r) return;
  await tentar(async () => {
    const res = await acao('add_node', { parent: d.id, type: 5, short: r.short, desc: r.desc });
    await acao('set_slots', { id: res.id, count: parseInt(r.slots || '0', 10) });
    await carregarArvore(false); revelar(res.id);
    aviso('Grupo criado', { tipo: 'sucesso' });
  });
}

// ---------------------------------------------------------------- aba Objetivos
function abaExtras(p, d) {
  const mk = (arquivo, titulo, dica, cols, branco) => {
    const linhas = (d[arquivo] || []).map((r) => r.slice());
    const gravar = () => tentar(async () => { await acao('set_rows', { file: arquivo, id: d.id, rows: linhas }); await selecionar(d.id); });
    const tbody = el('tbody');
    const desenhar = () => {
      tbody.innerHTML = '';
      if (!linhas.length) tbody.append(vaziaLinha(cols.length + 1, 'Nada aqui.'));
      linhas.forEach((r, i) => tbody.append(el('tr', {}, ...cols.map((c, j) => el('td', {}, inp({ class: 'mono', value: r[j] ?? '', onchange: (e) => { linhas[i][j] = e.target.value.trim(); gravar(); } }))),
        el('td', { class: 'encolher' }, btnLinha(() => { linhas.splice(i, 1); desenhar(); gravar(); })))));
    };
    desenhar();
    return cartao(titulo, dica, tabela(cols.concat(['']), tbody), btnNova('Nova linha', () => { linhas.push(branco.slice()); desenhar(); gravar(); }));
  };
  p.append(mk('objectives', 'Objetivos', 'Metas de temporada no modo carreira para este nó.', ['Objetivo', 'Valor'], ['CHAMPION', '1']));
  if (d.type === 3 || d.type === 6) p.append(mk('initteams', 'Times iniciais', 'Onde os times terminaram na temporada anterior — usado pelo FillFromCompTable.', ['Posição', 'ID do time'], ['0', '0']));
}

// ---------------------------------------------------------------- assistente
async function assistente(d) {
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } },
    el('div', { class: 'grade2' },
      campo('Código', inp({ 'data-k': 'code', class: 'mono', value: 'C9000' }), 'Vira C####, e o asset_id sai daqui.'),
      campo('Tipo', el('select', { 'data-k': 'kind' }, ...['CUP', 'LEAGUE', 'SUPERCUP', 'PLAYOFF'].map((o) => el('option', { value: o }, o)))),
      campo('Grupos', inp({ 'data-k': 'groups', type: 'number', min: '1', value: '4' })),
      campo('Times por grupo', inp({ 'data-k': 'per_group', type: 'number', min: '2', value: '6' })),
      campo('Classificados por grupo', inp({ 'data-k': 'advancing', type: 'number', min: '1', value: '2' })),
      campo('Rodadas de mata-mata', inp({ 'data-k': 'ko_rounds', type: 'number', min: '0', value: '3' }), '3 = quartas, semi e final.'),
      campo('Liga de origem (opcional)', inp({ 'data-k': 'league', class: 'mono', placeholder: 'ex.: 1509' }), 'Cria a task FillFromLeague. Em branco, defina o preenchimento depois na aba Tasks.')),
    chaveDados('two_legs', 'Mata-mata em ida e volta', true),
    chaveDados('setup', 'Criar estágio de setup com sorteio para os grupos', true));
  const r = await dialogo('Nova competição em ' + d.label, corpo, 'Criar', { largo: true, texto: 'Monta o esqueleto: setup, fase de grupos e as rodadas de mata-mata, já com os avanços ligados.' });
  if (!r) return;
  await tentar(async () => {
    const res = await acao('wizard', { parent: d.id, ...r });
    await carregarArvore(false);
    revelar(res.id);
    aviso('Competição criada — ajuste as datas e as tasks', { tipo: 'sucesso' });
  });
}
function chaveDados(k, titulo, marcado) {
  const i = el('input', { type: 'checkbox', role: 'switch', 'data-k': k });
  i.checked = marcado;
  return el('label', { class: 'interruptor' }, el('span', { class: 'txt' }, el('b', {}, titulo)), el('span', { class: 'chave' }, i, el('span')));
}

// ---------------------------------------------------------------- validação
function mostrarProblemas() {
  const todos = S.issues.errors.map((i) => ['e', i]).concat(S.issues.warnings.map((i) => ['w', i]));
  let m;
  const corpo = todos.length
    ? el('div', { class: 'lista', style: { maxHeight: '56vh' } }, ...todos.map(([k, i]) => el('button', { class: 'problema', onclick: () => { m.fechar(); if (i.node !== null) revelar(i.node); } },
      el('span', { class: `etiqueta ${k === 'e' ? 'vermelha' : 'amarela'}` }, k === 'e' ? 'erro' : 'aviso'), el('span', { class: 'cresce' }, i.msg),
      el('span', { class: 'ref' }, i.node === null ? '' : '#' + i.node))))
    : el('div', { class: 'nota info', html: icone('check', 15) + '<div>Nenhum problema encontrado.</div>' });
  m = modal({ titulo: `Problemas de consistência`, texto: `${S.issues.errors.length} erros · ${S.issues.warnings.length} avisos. Clique num item para ir ao nó.`,
    corpo, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

// ---------------------------------------------------------------- ações do nó
async function excluir() {
  const d = S.node;
  if (!d || d.type <= 2) return;
  const r0 = await tentar(() => acao('impact', { id: d.id }));
  if (!r0) return;
  const linhas = el('div', { class: 'impacto' }, ...Object.entries(r0.impact).filter(([, v]) => v).map(([k, v]) => el('div', {}, el('span', {}, k + '.txt'), el('b', {}, '−' + v))));
  const ok = await dialogo(`Excluir “${d.label}”?`, [el('div', { class: 'mudo' }, 'Some com o nó e tudo abaixo dele. Os IDs seguintes são renumerados e as referências, corrigidas. Dá para desfazer (Ctrl+Z).'), linhas], 'Excluir', { perigo: true });
  if (!ok) return;
  await tentar(async () => {
    const res = await acao('delete_node', { id: d.id });
    await carregarArvore(false);
    aviso(`${res.removed} nó(s) removidos`, { tipo: 'sucesso' });
    if (res.parent !== null && res.parent !== undefined) revelar(res.parent);
    else mostrarVazio();
  });
}
async function mover(delta) {
  if (!S.node || S.node.type < 3) return;
  await tentar(async () => {
    const res = await acao('move_node', { id: S.node.id, delta });
    if (!res.ok) { aviso('Já está na ponta', { tipo: 'aviso', tempo: 1800 }); return; }
    await carregarArvore(false);
    revelar(res.id);
  });
}
async function copiar() {
  if (!S.node || S.node.type === 0 || S.node.type === -1) return;
  await tentar(async () => {
    const res = await acao('copy_node', { id: S.node.id });
    aviso(`“${res.label}” copiado (${res.nodes} nó${res.nodes > 1 ? 's' : ''})`, { tipo: 'sucesso', tempo: 2200 });
  });
}
async function colar() {
  if (!S.node || !S.clip) return;
  await tentar(async () => {
    const res = await acao('paste_node', { parent: S.node.id });
    await carregarArvore(false);
    revelar(res.id);
    aviso('Colado — revise datas, tasks e avanços externos', { tipo: 'sucesso' });
  });
}
async function salvar() {
  if (!S.estado.aberto || !S.estado.dirty) return;
  if (S.issues.errors.length && !await confirmar('Salvar mesmo com erros?', `Há ${S.issues.errors.length} erro(s) de consistência. O jogo pode não abrir a carreira.`, { rotulo: 'Salvar assim mesmo', perigo: true })) return;
  await tentar(async () => {
    const r = await acao('save');
    aviso('Gravado', { tipo: 'sucesso', detalhe: 'Backup dos arquivos anteriores em ' + r.backup });
  });
}
async function recarregar() {
  if (!S.estado.aberto) return;
  if (!await confirmar('Recarregar do disco?', 'Tudo que não foi salvo se perde.', { rotulo: 'Recarregar', perigo: true })) return;
  await tentar(async () => { await acao('reload'); await carregarArvore(); aviso('Recarregado', { tempo: 1800 }); });
}
async function desfazer(refazer = false) {
  if (!S.estado.aberto || (refazer ? !S.estado.can_redo : !S.estado.can_undo)) return;
  await tentar(async () => { await acao(refazer ? 'redo' : 'undo'); await carregarArvore(); });
}

// ---------------------------------------------------------------- abrir pasta
async function abrirPasta(caminho = null) {
  if (!caminho) {
    const campoP = el('input', { 'data-k': 'path', class: 'mono', placeholder: 'C:\\caminho\\da\\compdata', value: S.estado.path || '' });
    const procurar = el('button', { class: 'btn', type: 'button', onclick: async () => {
      procurar.disabled = true;
      const r = await tentar(() => acao('browse_dir'));
      if (r && r.dir) campoP.value = r.dir;
      procurar.disabled = false;
    } }, icone('pasta', 14), 'Procurar…');
    const r = await dialogo('Abrir pasta de compdata', [el('div', { class: 'mudo' }, 'A pasta precisa ter o compobj.txt e os demais arquivos do compdata. Uma planilha .xlsx na pasta dá nomes aos times e competições.'),
      el('div', { class: 'caminho-linha' }, campoP, procurar)], 'Abrir');
    if (!r || !r.path.trim()) return;
    caminho = r.path.trim();
  }
  await tentar(async () => {
    let res = await acao('open_path', { path: caminho });
    if (res.needs_force) {
      if (!await confirmar('Descartar alterações?', 'A pasta atual tem alterações não salvas. Elas serão perdidas.', { rotulo: 'Descartar e abrir', perigo: true })) return;
      res = await acao('open_path', { path: caminho, force: true });
    }
    await aposAbrir();
    aviso('Pasta aberta', { tipo: 'sucesso', tempo: 1800 });
  });
}
async function fecharPasta() {
  let r = await tentar(() => acao('close'));
  if (!r) return;
  if (r.needs_force) {
    if (!await confirmar('Fechar sem salvar?', 'As alterações não salvas serão perdidas.', { rotulo: 'Fechar sem salvar', perigo: true })) return;
    r = await tentar(() => acao('close', { force: true }));
  }
  S.nodes = []; S.sel = null; S.node = null;
  await boasVindas();
}
async function aposAbrir() {
  S.sel = null; S.node = null; S.expanded.clear();
  const t = await get('teams');
  S.teams = t.teams;
  S.teamName = new Map(t.teams.map((x) => [x.id, x.name]));
  await carregarArvore(false);
  for (const r of (S.kids.get(-1) || [])) S.expanded.add(r);
  desenharArvore();
  mostrarVazio();
}
function mostrarVazio() {
  S.sel = null; S.node = null;
  $('#no').hidden = true;
  $('#boas-vindas').hidden = true;
  const v = $('#vazio');
  v.hidden = false;
  v.innerHTML = '';
  v.append(el('div', { class: 'ic-grande', html: icone('arvore', 64) }), el('h2', {}, 'Escolha algo na árvore'),
    el('p', {}, 'Competições, estágios e grupos. As edições ficam na memória até você clicar em ', el('b', {}, 'Salvar'),
      ' — e o Salvar guarda um backup dos dez arquivos antes de gravar.'),
    el('div', { class: 'acoes' }, el('button', { class: 'btn', onclick: () => $('#busca').focus() }, icone('busca', 14), 'Buscar'),
      el('button', { class: 'btn', onclick: mostrarProblemas }, icone('aviso', 14), 'Ver problemas')));
  aplicarEstado(S.estado);
}
async function boasVindas() {
  const ini = await get('inicio');
  S.recentes = ini.recentes || [];
  aplicarEstado(ini.state);
  $('#no').hidden = true;
  $('#vazio').hidden = true;
  const bv = $('#boas-vindas');
  bv.hidden = false;
  bv.className = 'conteudo-interno bv-wrap';
  bv.innerHTML = '';
  bv.append(el('div', { class: 'bv-hero' }, el('div', { class: 'bv-hero-ic' }), el('div', {}, el('h1', {}, 'Editor de Compdata'),
    el('p', {}, 'Edita os arquivos de competição do FC no nível de competição → estágio → grupo. Inserir, remover ou reordenar renumera os nós e corrige sozinho todas as referências nos dez arquivos.'),
    el('div', { class: 'acoes-linha', style: { marginTop: '16px' } }, el('button', { class: 'btn-primario grande', onclick: () => abrirPasta() }, icone('pastaAberta', 16), 'Abrir pasta de compdata…')))));
  const bloco = el('div', { class: 'bv-bloco' }, el('h3', {}, 'Recentes'));
  const lista = el('div', { class: 'bv-lista' });
  if (!S.recentes.length) lista.append(el('div', { class: 'bv-vazio' }, 'Nenhuma pasta aberta ainda. A pasta precisa ter o compobj.txt.'));
  for (const r of S.recentes) {
    const nome = r.split(/[\\/]/).filter(Boolean).pop();
    lista.append(el('button', { class: 'bv-cartao', onclick: () => abrirPasta(r) }, icone('pasta', 18), el('div', { class: 'txt' }, el('b', {}, nome), el('small', {}, r))));
  }
  bloco.append(lista);
  bv.append(bloco);
}

// ---------------------------------------------------------------- menus
function menus() {
  let ab, d;
  const ctx = (fn) => () => { ab = S.estado.aberto; d = S.node; return fn(); };
  barraMenus($('#menus'), [
    ['Arquivo', ctx(() => [
      { rotulo: 'Abrir pasta…', icone: 'pastaAberta', atalho: 'Ctrl+O', fn: () => abrirPasta() },
      ...(S.recentes.length ? [{ cabecalho: 'Recentes' }, ...S.recentes.slice(0, 5).map((r) => ({ rotulo: r.split(/[\\/]/).filter(Boolean).pop(), icone: 'pasta', fn: () => abrirPasta(r) }))] : []),
      '-',
      { rotulo: 'Salvar', icone: 'salvar', atalho: 'Ctrl+S', desabilitado: !ab || !S.estado.dirty, fn: salvar },
      { rotulo: 'Recarregar do disco', icone: 'recarregar', desabilitado: !ab, fn: recarregar },
      { rotulo: 'Mostrar a pasta no Explorer', icone: 'externo', desabilitado: !ab, fn: () => tentar(() => acao('explorer')) },
      '-',
      { rotulo: 'Fechar pasta', icone: 'x', desabilitado: !ab, fn: fecharPasta },
    ])],
    ['Editar', ctx(() => [
      { rotulo: 'Desfazer', icone: 'desfazer', atalho: 'Ctrl+Z', desabilitado: !ab || !S.estado.can_undo, fn: () => desfazer() },
      { rotulo: 'Refazer', icone: 'refazer', atalho: 'Ctrl+Shift+Z', desabilitado: !ab || !S.estado.can_redo, fn: () => desfazer(true) },
      '-',
      { rotulo: 'Copiar nó', icone: 'copiar', atalho: 'Ctrl+C', desabilitado: !d || d.type === 0 || d.type === -1, fn: copiar },
      { rotulo: S.clip ? `Colar “${S.clip}” aqui dentro` : 'Colar', icone: 'colar', atalho: 'Ctrl+V', desabilitado: !d || !S.clip, fn: colar },
      { rotulo: 'Mover para cima', icone: 'setaCima', atalho: 'Alt+↑', desabilitado: !d || d.type < 3, fn: () => mover(-1) },
      { rotulo: 'Mover para baixo', icone: 'setaBaixo', atalho: 'Alt+↓', desabilitado: !d || d.type < 3, fn: () => mover(1) },
      '-',
      { rotulo: d ? rotuloNovo(d) + '…' : 'Novo filho…', icone: 'mais', desabilitado: !d || d.type === 5 || d.type === -1, fn: () => novoFilho(d) },
      { rotulo: 'Nova competição (assistente)…', icone: 'varinha', desabilitado: !d || d.type > 2, fn: () => assistente(d) },
      '-',
      { rotulo: 'Excluir…', icone: 'apagar', atalho: 'Delete', desabilitado: !d || d.type <= 2, fn: excluir },
    ])],
    ['Exibir', ctx(() => [
      { rotulo: 'Expandir confederações e países', icone: 'expandir', desabilitado: !ab, fn: expandirContainers },
      { rotulo: 'Recolher tudo', icone: 'recolher', desabilitado: !ab, fn: () => { S.expanded.clear(); desenharArvore(); } },
      { rotulo: 'Buscar', icone: 'busca', atalho: '/', desabilitado: !ab, fn: () => $('#busca').focus() },
      '-',
      { rotulo: 'Problemas de consistência…', icone: 'aviso', desabilitado: !ab, fn: mostrarProblemas },
    ])],
    ['Ajuda', ctx(() => [
      { rotulo: 'Atalhos do teclado', icone: 'teclado', atalho: 'F1', fn: atalhos },
      { rotulo: 'Como o editor funciona', icone: 'ajuda', fn: comoFunciona },
      { rotulo: 'Sobre o editor', icone: 'info', fn: sobre },
    ])],
  ]);
}
function expandirContainers() {
  for (const n of S.nodes) if (n.type >= 0 && n.type <= 2) S.expanded.add(n.id);
  desenharArvore();
}
function atalhos() {
  const t = el('div', { class: 'tabela-atalhos' });
  for (const [g, itens] of [['Arquivo', [['Salvar', 'Ctrl+S'], ['Abrir pasta', 'Ctrl+O']]],
    ['Edição', [['Desfazer', 'Ctrl+Z'], ['Refazer', 'Ctrl+Shift+Z'], ['Copiar nó', 'Ctrl+C'], ['Colar como filho', 'Ctrl+V'], ['Mover entre irmãos', 'Alt+↑ / Alt+↓'], ['Excluir', 'Delete']]],
    ['Navegação', [['Buscar', '/'], ['Subir/descer na árvore', '↑ / ↓'], ['Abrir/fechar grupo', '← / →']]]]) {
    t.append(el('h4', {}, g));
    for (const [rot, k] of itens) t.append(el('div', {}, el('span', {}, rot), el('span', { html: `<kbd>${esc(k)}</kbd>` })));
  }
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
function comoFunciona() {
  modal({ titulo: 'Como o editor funciona', largo: true, corpo: el('div', { style: { color: 'var(--texto-2)', lineHeight: '1.6' }, html: `
    <b>Por que um editor:</b> no <i>compobj.txt</i> o ID do nó é o número da linha. Inserir, remover ou reordenar renumera tudo que vem
    depois — e cada referência a nó nos outros nove arquivos passaria a apontar para o lugar errado. O editor faz esse remapeamento
    sozinho em compobj, compids, advancement, standings, schedule, objectives, initteams, weather, tasks (campos de nó de cada verbo) e
    settings (só as chaves que são ID de nó).<br><br>
    <b>Nem todo número é nó:</b> <i>info_special_team_id</i>, <i>nation_id</i>, <i>match_stadium</i>, <i>info_league_promo/releg</i>,
    <i>schedule_refcomp</i> e <i>asset_id</i> são IDs de banco ou de asset e nunca são remapeados.<br><br>
    <b>Salvar:</b> as edições ficam na memória; o Salvar copia os dez arquivos para <i>_backup_editor_AAAAMMDD_HHMMSS</i> antes de gravar.
    Gravar sem editar reproduz os arquivos byte a byte.<br><br>
    <b>Validação:</b> o selo no rodapé confere hierarquia, posições do standings, avanços para grupos que existem, vaga preenchida
    duas vezes, schedule com mínimo maior que máximo, task pedindo mais times do que há e referências para nós inexistentes.` }),
  botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
function sobre() {
  dialogoSobre({ nome: 'Editor de Compdata', versao: S.versao, html: `
    Editor visual dos arquivos de competição do FC (compobj, settings, standings, advancement, schedule, tasks…), no nível de
    competição → estágio → grupo.<br><br>
    <b>2.1</b> — nomes de times, competições, estágios e grupos vindos do banco e do idioma importados no Super Tool (Dados do jogo).<br>
    <b>2.0</b> — interface no padrão do BRFP Super Tool (menus, árvore, avisos e diálogos do Editor de Estádios), abre sem pasta e lembra
    as recentes, lê os nomes da planilha .xlsx sem precisar do openpyxl.<br>
    <b>1.0</b> — editor com renumeração automática, copiar/colar de subárvores, assistente de competição e validação.` });
}

// ---------------------------------------------------------------- teclado
function navegarArvore(e) {
  const linhas = [...document.querySelectorAll('#arvore .linha-arv[data-id]')];
  const i = linhas.findIndex((x) => +x.dataset.id === S.sel);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const j = Math.max(0, Math.min(linhas.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    if (linhas[j]) { e.preventDefault(); selecionar(+linhas[j].dataset.id); linhas[j].scrollIntoView({ block: 'nearest' }); }
  } else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && S.sel !== null) {
    const abrir = e.key === 'ArrowRight';
    if (abrir !== S.expanded.has(S.sel) && (S.kids.get(S.sel) || []).length) { e.preventDefault(); alternar(S.sel); }
  }
}
document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  const digitando = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  const ctrl = e.ctrlKey || e.metaKey;
  const k = e.key.toLowerCase();
  if (ctrl && k === 's') { e.preventDefault(); salvar(); return; }
  if (ctrl && k === 'o') { e.preventDefault(); abrirPasta(); return; }
  if (e.key === 'F1') { e.preventDefault(); atalhos(); return; }
  if (digitando) return;
  if (ctrl && k === 'z') { e.preventDefault(); desfazer(e.shiftKey); return; }
  if (ctrl && k === 'y') { e.preventDefault(); desfazer(true); return; }
  if (ctrl && k === 'c') { e.preventDefault(); copiar(); return; }
  if (ctrl && k === 'v') { e.preventDefault(); colar(); return; }
  if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) { e.preventDefault(); mover(e.key === 'ArrowUp' ? -1 : 1); return; }
  if (e.key === 'Delete') { e.preventDefault(); excluir(); return; }
  if (e.key === '/') { e.preventDefault(); $('#busca').focus(); return; }
  if (S.estado.aberto && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) navegarArvore(e);
});
window.addEventListener('beforeunload', (e) => { if (S.estado.aberto && S.estado.dirty) { e.preventDefault(); e.returnValue = ''; } });

function $$(s) { return [...document.querySelectorAll(s)]; }

// ---------------------------------------------------------------- início
async function iniciar() {
  $('#btn-desfazer').innerHTML = icone('desfazer', 17);
  $('#btn-refazer').innerHTML = icone('refazer', 17);
  $('#btn-salvar-ic').innerHTML = icone('salvar', 15);
  $('#btn-expandir').innerHTML = icone('expandir', 14);
  $('#btn-recolher').innerHTML = icone('recolher', 14);
  $('#busca-ic').innerHTML = icone('busca', 14);
  $('#btn-copiar').innerHTML = icone('copiar', 13) + 'Copiar';
  $('#btn-colar').innerHTML = icone('colar', 13) + 'Colar';
  $('#btn-cima').innerHTML = icone('setaCima', 16);
  $('#btn-baixo').innerHTML = icone('setaBaixo', 16);
  $('#btn-excluir').innerHTML = icone('apagar', 13) + 'Excluir';
  $('#btn-desfazer').onclick = () => desfazer();
  $('#btn-refazer').onclick = () => desfazer(true);
  $('#btn-salvar').onclick = salvar;
  $('#btn-expandir').onclick = expandirContainers;
  $('#btn-recolher').onclick = () => { S.expanded.clear(); desenharArvore(); };
  $('#btn-copiar').onclick = copiar;
  $('#btn-colar').onclick = colar;
  $('#btn-cima').onclick = () => mover(-1);
  $('#btn-baixo').onclick = () => mover(1);
  $('#btn-excluir').onclick = excluir;
  $('#chip-validacao').onclick = mostrarProblemas;
  $('#busca').addEventListener('input', desenharArvore);
  $('#busca').addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.target.value = ''; desenharArvore(); e.target.blur(); } });
  divisorArrastavel($('#divisor'), '--esq', { min: 240, max: 640 });
  S.vocab = await get('vocab');
  const ini = await get('inicio');
  S.versao = ini.versao;
  S.recentes = ini.recentes || [];
  $('#versao').textContent = ini.versao;
  menus();
  if (ini.state.aberto) await aposAbrir();
  else await boasVindas();
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
