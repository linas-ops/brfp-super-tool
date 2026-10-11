// Editor de Banco — interface (BRFP Super Tool): times, jogadores, ligas, árbitros, técnicos e qualquer tabela do banco
// importado em Dados do jogo, com transferências, empréstimos, escalação e verificação de erros.
import { $, el, esc, aviso, modal, confirmar, barraMenus, abrirMenu, divisorArrastavel, dialogoSobre, nota, interruptor, modalAberto, menuAberto } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';

const S = { ini: null, e: null, aba: 'times', arvore: null, abertos: JSON.parse(localStorage.getItem('banco.abertos') || '{}'), busca: '',
  vista: null, nacoes: [], pos: {}, polling: null, tarefaAntes: false, buscaJog: '', resJog: null, pessoas: { tabela: 'manager', q: '', lista: null },
  tabelas: null, buscaTab: '', subTime: 'elenco', probs: null, filtroProb: 'todos' };
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');
const opt = (v, t, sel) => { const o = el('option', { value: v }, t); o.selected = String(sel ?? '') === String(v ?? ''); return o; };
async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro', tempo: 8000 }); return undefined; } }
const classeOv = (v) => (v >= 80 ? 'a' : v >= 70 ? 'b' : v >= 60 ? 'c' : 'd');
const BASE_DIA = Date.UTC(1582, 9, 14);
const diaParaData = (n) => { const x = parseInt(n, 10); if (!Number.isFinite(x) || x <= 0) return ''; return new Date(BASE_DIA + x * 86400000).toISOString().slice(0, 10); };
const dataParaDia = (iso) => (iso ? String(Math.round((Date.parse(iso + 'T00:00:00Z') - BASE_DIA) / 86400000)) : '0');
const idade = (iso) => { if (!iso) return null; const n = new Date(iso + 'T00:00:00'); const h = new Date(); let a = h.getFullYear() - n.getFullYear(); if (h.getMonth() < n.getMonth() || (h.getMonth() === n.getMonth() && h.getDate() < n.getDate())) a -= 1; return a; };

// ---------------------------------------------------------------- rótulos dos campos
const ATR = { acceleration: 'Aceleração', sprintspeed: 'Arrancada', positioning: 'Posicionamento', finishing: 'Finalização', shotpower: 'Força do chute',
  longshots: 'Chute de longe', volleys: 'Voleio', penalties: 'Pênaltis', vision: 'Visão', crossing: 'Cruzamento', freekickaccuracy: 'Falta',
  shortpassing: 'Passe curto', longpassing: 'Passe longo', curve: 'Curva', agility: 'Agilidade', balance: 'Equilíbrio', reactions: 'Reação',
  ballcontrol: 'Controle', dribbling: 'Drible', composure: 'Compostura', interceptions: 'Interceptação', headingaccuracy: 'Cabeceio',
  defensiveawareness: 'Marcação', marking: 'Marcação', standingtackle: 'Desarme em pé', slidingtackle: 'Carrinho', jumping: 'Impulsão', stamina: 'Fôlego',
  strength: 'Força', aggression: 'Agressividade', gkdiving: 'Elasticidade', gkhandling: 'Manejo', gkkicking: 'Chute (goleiro)',
  gkpositioning: 'Posicionamento (goleiro)', gkreflexes: 'Reflexos' };
const ROT = { ...ATR,
  overallrating: 'Geral', potential: 'Potencial', birthdate: 'Nascimento', nationality: 'Nacionalidade', height: 'Altura (cm)', weight: 'Peso (kg)',
  preferredfoot: 'Pé preferido', weakfootabilitytypecode: 'Perna ruim (1–5)', skillmoves: 'Dribles (0–4 = 1–5 estrelas)', internationalrep: 'Reputação internacional',
  contractvaliduntil: 'Contrato até (ano)', playerjointeamdate: 'Chegou ao time', attackingworkrate: 'Empenho no ataque', defensiveworkrate: 'Empenho na defesa',
  preferredposition1: 'Posição principal', preferredposition2: 'Posição 2', preferredposition3: 'Posição 3', preferredposition4: 'Posição 4',
  preferredposition5: 'Posição 5', preferredposition6: 'Posição 6', preferredposition7: 'Posição 7', jerseynumber: 'Número', gender: 'Gênero (0 homem, 1 mulher)',
  isretiring: 'Vai se aposentar', skintonecode: 'Tom de pele', haircolorcode: 'Cor do cabelo', hairtypecode: 'Cabelo', headtypecode: 'Cabeça', facialhairtypecode: 'Barba',
  facialhaircolorcode: 'Cor da barba', eyecolorcode: 'Cor dos olhos', bodytypecode: 'Corpo', headassetid: 'Cabeça (asset)', hashighqualityhead: 'Cabeça real',
  value: 'Valor', wage: 'Salário', releaseclause: 'Multa rescisória',
  teamname: 'Nome', foundationyear: 'Fundação', rivalteam: 'Rival', domesticprestige: 'Prestígio nacional', internationalprestige: 'Prestígio internacional',
  popularity: 'Popularidade', clubworth: 'Valor do clube', transferbudget: 'Verba de transferência', youthdevelopment: 'Base', profitability: 'Lucratividade',
  teamstadiumcapacity: 'Capacidade do estádio', overallrating_t: 'Geral', attackrating: 'Ataque', midfieldrating: 'Meio', defenserating: 'Defesa',
  buildupplay: 'Saída de bola', defensivedepth: 'Linha defensiva', captainid: 'Capitão', penaltytakerid: 'Pênaltis', freekicktakerid: 'Faltas',
  leftfreekicktakerid: 'Faltas (esquerda)', rightfreekicktakerid: 'Faltas (direita)', leftcornerkicktakerid: 'Escanteios (esquerda)',
  rightcornerkicktakerid: 'Escanteios (direita)', longkicktakerid: 'Tiro de meta', assetid: 'Escudo (asset)', leaguetitles: 'Títulos da liga', domesticcups: 'Copas',
  leaguename: 'Nome', countryid: 'País', level: 'Divisão', iswomencompetition: 'Feminina', isinternationalleague: 'Internacional', leaguetype: 'Tipo',
  firstname: 'Primeiro nome', surname: 'Sobrenome', commonname: 'Nome comum', teamid: 'Time', leagueid: 'Liga', cardstrictness: 'Rigor nos cartões',
  foulstrictness: 'Rigor nas faltas', managerid: 'ID' };
const GRUPOS_JOGADOR = [
  ['Dados', ['overallrating', 'potential', 'birthdate', 'nationality', 'height', 'weight', 'preferredfoot', 'gender', 'internationalrep', 'isretiring']],
  ['Posições', ['preferredposition1', 'preferredposition2', 'preferredposition3', 'preferredposition4', 'preferredposition5', 'preferredposition6', 'preferredposition7']],
  ['Habilidades', ['skillmoves', 'weakfootabilitytypecode', 'attackingworkrate', 'defensiveworkrate']],
  ['Ritmo e finalização', ['acceleration', 'sprintspeed', 'positioning', 'finishing', 'shotpower', 'longshots', 'volleys', 'penalties']],
  ['Passe e drible', ['vision', 'crossing', 'freekickaccuracy', 'shortpassing', 'longpassing', 'curve', 'agility', 'balance', 'reactions', 'ballcontrol', 'dribbling', 'composure']],
  ['Defesa e físico', ['interceptions', 'headingaccuracy', 'defensiveawareness', 'marking', 'standingtackle', 'slidingtackle', 'jumping', 'stamina', 'strength', 'aggression']],
  ['Goleiro', ['gkdiving', 'gkhandling', 'gkkicking', 'gkpositioning', 'gkreflexes']],
  ['Contrato', ['contractvaliduntil', 'playerjointeamdate', 'value', 'wage', 'releaseclause']],
  ['Aparência', ['skintonecode', 'haircolorcode', 'hairtypecode', 'headtypecode', 'facialhairtypecode', 'facialhaircolorcode', 'eyecolorcode', 'bodytypecode', 'headassetid', 'hashighqualityhead']],
];
const GRUPOS_TIME = [
  ['Clube', ['foundationyear', 'rivalteam', 'assetid', 'teamstadiumcapacity', 'leaguetitles', 'domesticcups']],
  ['Prestígio e finanças', ['domesticprestige', 'internationalprestige', 'popularity', 'clubworth', 'transferbudget', 'youthdevelopment', 'profitability']],
  ['Notas do time', ['overallrating', 'attackrating', 'midfieldrating', 'defenserating']],
];
const DATAS = new Set(['birthdate', 'playerjointeamdate', 'loandateend']);
const NACOES = new Set(['nationality', 'countryid', 'nationalityid']);
const TIMES = new Set(['rivalteam', 'teamidloanedfrom']);
const ESCOLHAS = {
  preferredfoot: [['1', 'Direito'], ['2', 'Esquerdo']],
  attackingworkrate: [['0', 'Médio'], ['1', 'Alto'], ['2', 'Baixo']], defensiveworkrate: [['0', 'Médio'], ['1', 'Alto'], ['2', 'Baixo']],
  buildupplay: [['0', 'Padrão'], ['1', 'Passe curto'], ['2', 'Equilibrada'], ['3', 'Bola longa']],
};

// ---------------------------------------------------------------- controles de campo
function controleCampo(t, campo, info, valor, mudar) {
  const v = valor ?? '';
  const lo = info?.low ?? 0, hi = info?.high ?? 0;
  if (DATAS.has(campo)) return el('input', { type: 'date', class: 'entrada', value: diaParaData(v), onchange: (e) => mudar(dataParaDia(e.target.value)) });
  if (NACOES.has(campo) && S.nacoes.length) return el('select', { class: 'seletor', onchange: (e) => mudar(e.target.value) },
    ...(S.nacoes.some((n) => n.id === String(v)) ? [] : [opt(v, `nação ${v}`, v)]), ...S.nacoes.map((n) => opt(n.id, n.nome, v)));
  if (/^preferredposition\d$/.test(campo)) return el('select', { class: 'seletor', onchange: (e) => mudar(e.target.value) },
    ...(campo !== 'preferredposition1' ? [opt('-1', '—', v)] : []), ...Object.entries(S.pos).filter(([k]) => +k < 28).map(([k, n]) => opt(k, `${n} (${k})`, v)));
  if (ESCOLHAS[campo]) return el('select', { class: 'seletor', onchange: (e) => mudar(e.target.value) },
    ...(ESCOLHAS[campo].some(([k]) => k === String(v)) ? [] : [opt(v, String(v), v)]), ...ESCOLHAS[campo].map(([k, n]) => opt(k, n, v)));
  const tipo = (info?.tipo || '').toLowerCase();
  if ((info?.t3 === 3 || tipo.includes('int')) && lo === 0 && hi === 1) {
    const c = el('input', { type: 'checkbox' });
    c.checked = String(v) === '1';
    c.onchange = () => mudar(c.checked ? '1' : '0');
    return el('label', { class: 'linha-check' }, c, c.checked ? ' sim' : ' não');
  }
  if (info?.t3 === 3 || tipo.includes('int')) return el('input', { type: 'number', class: 'entrada', value: v, min: lo, max: hi || undefined, title: hi ? `${lo}–${hi}` : '', onchange: (e) => mudar(e.target.value) });
  if (info?.t3 === 4 || tipo.includes('real') || tipo.includes('float')) return el('input', { type: 'number', class: 'entrada', step: 'any', value: v, onchange: (e) => mudar(e.target.value) });
  const max = info?.t3 === 13 ? 255 : (info?.bits || 0) / 8 || undefined;
  return el('input', { type: 'text', class: 'entrada', value: v, maxlength: max, spellcheck: 'false', onchange: (e) => mudar(e.target.value) });
}

// formulário de uma linha: grupos com rótulos + "Outros campos"; grava só o que mudou
function formulario({ tabela, ref, dados, campos, grupos = [], excluir = [], rotulo, depois }) {
  const mud = {};
  const wrap = el('div', { class: 'form-linha' });
  const btn = el('button', { class: 'btn-primario peq', disabled: true }, icone('salvar', 12), 'Gravar as mudanças');
  const marcar = (c, v) => { if (String(v) === String(dados[c] ?? '')) delete mud[c]; else mud[c] = v; btn.disabled = !Object.keys(mud).length; btn.textContent = ''; btn.append(el('span', { html: icone('salvar', 12) }), Object.keys(mud).length ? ` Gravar ${Object.keys(mud).length} mudança(s)` : ' Gravar as mudanças'); };
  btn.onclick = async () => {
    const r = await tentar(() => api('linha_salvar', { tabela, ref, valores: mud, rotulo }));
    if (!r) return;
    aplicarEstado(r);
    aviso('Gravado na edição', { tipo: 'sucesso', tempo: 1600, detalhe: 'Vai para o banco quando você usar Gravar banco.' });
    if (depois) depois();
  };
  const usados = new Set(excluir);
  const campoEl = (c) => {
    usados.add(c);
    const info = campos[c] || {};
    const nome = ROT[c] ? `${ROT[c]}` : c;
    const dica = `${c}${info.high ? ` · ${info.low ?? 0}–${info.high}` : ''}${TIMES.has(c) && dados[c] ? ` · time ${dados[c]}` : ''}`;
    return el('div', { class: 'campo-linha', title: dica }, el('label', {}, nome, ROT[c] ? el('small', {}, c) : null), controleCampo(tabela, c, info, dados[c], (v) => marcar(c, v)));
  };
  wrap.append(el('div', { class: 'barra-form' }, el('span', { class: 'mudo peq-txt' }, 'Mudou um campo? Grave para ele entrar na edição (dá para desfazer).'), btn));
  for (const [titulo, cs] of grupos) {
    const lst = cs.filter((c) => c in dados);
    if (!lst.length) continue;
    wrap.append(el('div', { class: 'grupo-form' }, el('h4', {}, titulo), el('div', { class: 'grade-campos' }, ...lst.map(campoEl))));
  }
  const resto = Object.keys(dados).filter((c) => !usados.has(c)).sort();
  if (resto.length) {
    const det = el('details', { class: 'grupo-form outros' }, el('summary', {}, `Outros campos (${resto.length})`));
    det.addEventListener('toggle', () => { if (det.open && det.childElementCount === 1) det.append(el('div', { class: 'grade-campos' }, ...resto.map(campoEl))); }, { once: false });
    wrap.append(det);
  }
  return wrap;
}

// ---------------------------------------------------------------- estado geral
function aplicarEstado(e) {
  if (!e) return;
  const ativa = e.tarefa?.ativa;
  S.e = e;
  desenharTopo();
  desenharPropriedades();
  desenharStatus();
  if (ativa) acompanhar();
  if (S.tarefaAntes && !ativa) fimGravar(e.tarefa);
  S.tarefaAntes = !!ativa;
}
async function atualizarEstado() { aplicarEstado(await tentar(() => api('estado'))); }

function desenharTopo() {
  const e = S.e;
  const n = e?.edicao?.mudancas || 0;
  $('#btn-gravar').disabled = !n || e?.tarefa?.ativa;
  $('#btn-gravar-txt').textContent = e?.tarefa?.ativa ? e.tarefa.msg : n ? `Gravar banco (${fmt(n)})` : 'Gravar banco';
  $('#btn-gravar-ic').innerHTML = icone(e?.tarefa?.ativa ? 'recarregar' : 'bancoDados', 14, e?.tarefa?.ativa ? 'girando' : '');
  $('#btn-desfazer').disabled = !(e?.edicao?.historico || []).length;
  $('#btn-desfazer').innerHTML = icone('desfazer', 14) + ' Desfazer';
  const b = e?.banco;
  $('#titulo').innerHTML = b ? `<b>${esc(b.nome)}</b><span class="pasta">${esc(b.nome_jogo)} · ${fmt(b.contagens.teams)} times · ${fmt(b.contagens.players)} jogadores</span>` : '<span class="mudo">Nenhum banco importado</span>';
}

function desenharStatus() {
  const e = S.e;
  $('#status-esq').innerHTML = e?.banco ? `<span>${esc(e.banco.caminho)}</span>` : '';
  const sd = $('#status-dir');
  sd.innerHTML = '';
  const n = e?.edicao?.mudancas || 0;
  sd.append(el('span', { class: `chip ${n ? 'aviso' : 'ok'}` }, icone('pincel', 12), n ? `${fmt(n)} mudança(s) não gravada(s) no banco` : 'sem mudanças'));
}

function desenharPropriedades() {
  const p = $('#propriedades');
  p.innerHTML = '';
  const e = S.e;
  const sec = (titulo, ic, corpo, aberta = true) => {
    const d = el('details', { class: 'secao', open: aberta });
    d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo).filter(Boolean)));
    return d;
  };
  if (!e?.banco) { p.append(sec('Banco', 'bancoDados', nota('Importe o banco do jogo em <b>Dados do jogo</b> no Super Tool.', 'alerta'))); return; }
  const b = e.banco;
  p.append(sec('Banco', 'bancoDados', [el('dl', { class: 'kv' },
    el('dt', {}, 'Jogo'), el('dd', {}, b.nome_jogo), el('dt', {}, 'Arquivo'), el('dd', { class: 'mono' }, b.caminho),
    el('dt', {}, 'Conteúdo'), el('dd', {}, `${fmt(b.contagens.players)} jogadores · ${fmt(b.contagens.teams)} times · ${fmt(b.contagens.leagues)} ligas`)),
  el('div', { class: 'mudo peq-txt' }, 'O banco original nunca é alterado: as mudanças ficam numa edição (salva sozinha) e o Gravar escreve um banco novo.')]));
  const res = e.edicao?.resumo || {};
  const linhas = Object.entries(res).sort();
  p.append(sec('Mudanças', 'pincel', [
    linhas.length || e.edicao?.idioma ? el('table', { class: 'tabela mini' }, el('thead', {}, el('tr', {}, el('th', {}, 'Tabela'), el('th', {}, 'alt.'), el('th', {}, 'novas'), el('th', {}, 'rem.'))),
      el('tbody', {}, ...linhas.map(([t, r]) => el('tr', { class: 'clicavel', onclick: () => abrir({ tipo: 'tabela', id: t }) }, el('td', {}, t), el('td', { class: 'num' }, r.alteradas || ''), el('td', { class: 'num' }, r.novas || ''), el('td', { class: 'num' }, r.removidas || ''))),
        e.edicao?.idioma ? el('tr', {}, el('td', {}, 'idioma (textos)'), el('td', { class: 'num' }, e.edicao.idioma), el('td', {}), el('td', {})) : null)) : el('div', { class: 'mudo peq-txt' }, 'Nenhuma mudança ainda.'),
    el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn-primario peq', disabled: !e.edicao?.mudancas || e.tarefa?.ativa, onclick: gravar }, icone('bancoDados', 12), 'Gravar banco novo…'),
      el('button', { class: 'btn-fantasma peq', disabled: !e.edicao?.mudancas, onclick: descartar }, icone('apagar', 12), 'Descartar tudo')),
  ]));
  const h = (e.edicao?.historico || []).slice().reverse();
  p.append(sec('Histórico', 'relogio', h.length ? [el('ol', { class: 'historico' }, ...h.slice(0, 20).map((x) => el('li', {}, x))),
    el('button', { class: 'btn peq', onclick: desfazer }, icone('desfazer', 12), `Desfazer “${h[0]}”`)] : el('div', { class: 'mudo peq-txt' }, 'As operações aparecem aqui (dá para desfazer).'), false));
  if (e.tarefa?.resultado) {
    const r = e.tarefa.resultado;
    p.append(sec('Último banco gravado', 'check', [el('div', { class: 'mono peq-txt' }, r.pasta),
      el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { caminho: r.pasta })) }, icone('pasta', 12), 'Abrir a pasta')], false));
  }
}

// ---------------------------------------------------------------- painel esquerdo
function desenharAbas() {
  const a = $('#abas-esq');
  a.innerHTML = '';
  for (const [k, rot, ic] of [['times', 'Times', 'escudo'], ['jogadores', 'Jogadores', 'pessoa'], ['mais', 'Mais', 'lista'], ['problemas', 'Erros', 'aviso']]) {
    a.append(el('button', { class: S.aba === k ? 'ativa' : '', onclick: () => { S.aba = k; desenharAbas(); desenharEsq(); if (k === 'problemas') abrir({ tipo: 'problemas' }); } },
      el('span', { html: icone(ic, 14) }), rot, k === 'problemas' && S.probs ? el('span', { class: 'n' }, fmt(S.probs.filter((x) => x.gravidade === 'erro').length)) : null));
  }
}

async function desenharEsq() {
  const p = $('#esq');
  p.innerHTML = '';
  if (!S.e?.banco) { p.append(el('div', { class: 'arvore-vazia' }, nota('Importe o banco em Dados do jogo (Super Tool).', 'alerta'))); return; }
  if (S.aba === 'times') return esqTimes(p);
  if (S.aba === 'jogadores') return esqJogadores(p);
  if (S.aba === 'mais') return esqMais(p);
  return esqProblemas(p);
}

async function esqTimes(p) {
  if (!S.arvore) {
    p.append(el('div', { class: 'arvore-vazia' }, 'Carregando os times…'));
    const r = await tentar(() => api('arvore'));
    if (!r) return;
    S.arvore = r;
    p.innerHTML = '';
  }
  const busca = el('input', { type: 'search', placeholder: 'Buscar time ou liga…', value: S.busca, spellcheck: 'false' });
  const lista = el('div', { class: 'arvore' });
  const desenhar = () => {
    lista.innerHTML = '';
    const q = busca.value.trim().toLowerCase();
    let pais = null;
    for (const l of S.arvore.ligas) {
      const times = q ? l.times.filter((t) => t.nome.toLowerCase().includes(q) || l.nome.toLowerCase().includes(q)) : l.times;
      if (q && !times.length) continue;
      if (l.pais_nome !== pais) { pais = l.pais_nome; lista.append(el('div', { class: 'grupo-pais' }, pais || '—')); }
      const aberto = !!q || S.abertos[l.leagueid];
      lista.append(el('div', { class: 'it-liga' },
        el('button', { class: 'seta-liga', onclick: () => { S.abertos[l.leagueid] = !S.abertos[l.leagueid]; localStorage.setItem('banco.abertos', JSON.stringify(S.abertos)); desenhar(); }, html: icone(aberto ? 'setaBaixo' : 'seta', 12) }),
        el('button', { class: `nome-liga ${S.vista?.tipo === 'liga' && S.vista.id === l.leagueid ? 'foco' : ''}`, onclick: () => abrir({ tipo: 'liga', id: l.leagueid }) },
          el('b', {}, l.nome), el('small', {}, `${l.times.length} times${l.feminina ? ' · feminina' : ''}`))));
      if (aberto) for (const t of times) lista.append(itemTime(t));
    }
    if (S.arvore.sem_liga.length && (!q || S.arvore.sem_liga.some((t) => t.nome.toLowerCase().includes(q)))) {
      lista.append(el('div', { class: 'grupo-pais' }, 'Sem liga'));
      for (const t of S.arvore.sem_liga.filter((t) => !q || t.nome.toLowerCase().includes(q))) lista.append(itemTime(t));
    }
  };
  busca.oninput = () => { S.busca = busca.value; desenhar(); };
  p.append(el('div', { class: 'busca-linha' }, el('label', { class: 'campo-busca' }, el('span', { html: icone('busca', 14) }), busca)), lista);
  desenhar();
}
const itemTime = (t) => el('button', { class: `it-time ${S.vista?.tipo === 'time' && S.vista.id === t.teamid ? 'foco' : ''}`, onclick: () => abrir({ tipo: 'time', id: t.teamid }) },
  el('span', {}, t.nome), el('small', {}, `${t.jogadores}`));

function esqJogadores(p) {
  const busca = el('input', { type: 'search', placeholder: 'Nome ou ID do jogador…', value: S.buscaJog, spellcheck: 'false', autofocus: true });
  const lista = el('div', { class: 'arvore' });
  let tmr = null;
  const buscar = async () => {
    const q = busca.value.trim();
    S.buscaJog = q;
    if (q.length < 2 && !/^\d+$/.test(q)) { lista.innerHTML = ''; lista.append(el('div', { class: 'arvore-vazia' }, 'Digite pelo menos 2 letras (ou o ID).')); return; }
    lista.innerHTML = '';
    lista.append(el('div', { class: 'arvore-vazia' }, 'Buscando…'));
    const r = await tentar(() => api('buscar_jogadores?q=' + encodeURIComponent(q)));
    if (S.buscaJog !== q) return;
    S.resJog = r?.jogadores || [];
    lista.innerHTML = '';
    for (const j of S.resJog) {
      lista.append(el('button', { class: `it-jog ${S.vista?.tipo === 'jogador' && S.vista.id === j.playerid ? 'foco' : ''}`, onclick: () => abrir({ tipo: 'jogador', id: j.playerid }) },
        el('span', { class: `ov ${classeOv(j.overall)}` }, j.overall), el('span', { class: 'txt' }, el('b', {}, j.nome), el('small', {}, `${j.pos} · ${j.clube_nome} · ID ${j.playerid}`))));
    }
    if (!S.resJog.length) lista.append(el('div', { class: 'arvore-vazia' }, 'Ninguém encontrado.'));
  };
  busca.oninput = () => { clearTimeout(tmr); tmr = setTimeout(buscar, 280); };
  p.append(el('div', { class: 'busca-linha' }, el('label', { class: 'campo-busca' }, el('span', { html: icone('busca', 14) }), busca)), lista);
  if (S.buscaJog) buscar(); else lista.append(el('div', { class: 'arvore-vazia' }, 'Busque pelo nome (comum, primeiro ou sobrenome) ou pelo ID.'));
}

async function esqMais(p) {
  const lista = el('div', { class: 'arvore' });
  p.append(lista);
  lista.append(el('div', { class: 'grupo-pais' }, 'Pessoas'));
  for (const [t, rot, ic] of [['manager', 'Técnicos', 'pessoa'], ['referee', 'Árbitros', 'alvo']]) {
    lista.append(el('button', { class: `it-time ${S.vista?.tipo === 'pessoas' && S.vista.id === t ? 'foco' : ''}`, onclick: () => abrir({ tipo: 'pessoas', id: t }) },
      el('span', { html: icone(ic, 13) + ' ' + rot }), el('small', {}, '')));
  }
  lista.append(el('div', { class: 'grupo-pais' }, 'Tabelas do banco'));
  if (!S.tabelas) {
    const r = await tentar(() => api('tabelas'));
    S.tabelas = r?.tabelas || [];
  }
  const busca = el('input', { type: 'search', placeholder: 'Buscar tabela…', value: S.buscaTab, spellcheck: 'false' });
  const itens = el('div');
  const desenhar = () => {
    itens.innerHTML = '';
    const q = busca.value.trim().toLowerCase();
    for (const t of S.tabelas.filter((x) => !q || x.nome.toLowerCase().includes(q))) {
      itens.append(el('button', { class: `it-time ${S.vista?.tipo === 'tabela' && S.vista.id === t.nome ? 'foco' : ''}`, onclick: () => abrir({ tipo: 'tabela', id: t.nome }) },
        el('span', {}, t.nome, t.mexida ? el('span', { class: 'ponto-mexida', title: 'mexida nesta edição' }, ' ●') : null), el('small', {}, fmt(t.linhas))));
    }
  };
  busca.oninput = () => { S.buscaTab = busca.value; desenhar(); };
  lista.append(el('div', { class: 'busca-linha', style: { padding: '4px 0' } }, el('label', { class: 'campo-busca' }, el('span', { html: icone('busca', 14) }), busca)), itens);
  desenhar();
}

function esqProblemas(p) {
  p.append(el('div', { class: 'arvore-vazia' }, el('p', {}, 'A verificação procura vínculos quebrados (jogador ou time que não existe), jogador em dois clubes, números repetidos, escalação e cobradores fora do elenco, empréstimos inválidos e valores fora da faixa do meta.'),
    el('button', { class: 'btn-primario', onclick: () => { S.probs = null; abrir({ tipo: 'problemas' }); } }, icone('busca', 14), 'Verificar agora')));
}

// ---------------------------------------------------------------- centro
function abrir(v) {
  S.vista = v;
  if (v.tipo === 'time' && S.vista.sub) S.subTime = S.vista.sub;
  desenharPrincipal();
  if (S.aba === 'times' || S.aba === 'mais' || S.aba === 'jogadores') desenharEsqFoco();
}
function desenharEsqFoco() {
  for (const b of document.querySelectorAll('#esq .foco')) b.classList.remove('foco');
}

async function desenharPrincipal() {
  const p = $('#principal');
  p.innerHTML = '';
  if (!S.e?.banco) return telaSemBanco(p);
  const v = S.vista;
  if (!v) return telaInicial(p);
  if (v.tipo === 'time') return vistaTime(p, v.id);
  if (v.tipo === 'jogador') return vistaJogador(p, v.id);
  if (v.tipo === 'liga') return vistaLiga(p, v.id);
  if (v.tipo === 'pessoas') return vistaPessoas(p, v.id);
  if (v.tipo === 'pessoa') return vistaPessoa(p, v.tabela, v.id);
  if (v.tipo === 'tabela') return vistaTabela(p, v.id, v.pagina || 0, v.q || '', v.campo || '');
  if (v.tipo === 'problemas') return vistaProblemas(p);
  telaInicial(p);
}

function telaSemBanco(p) {
  p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('bancoDados', 64) }), el('h2', {}, 'Nenhum banco importado'),
    el('p', {}, 'Importe o fifa_ng_db.db (ou a pasta de tabelas .txt) em Dados do jogo, no Super Tool. Vale qualquer versão: FIFA 16, 21, 22, 23, FC 24, 26 e 27.')));
}

function telaInicial(p) {
  const b = S.e.banco;
  p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('bancoDados', 64) }), el('h2', {}, `Editar o banco do ${b.nome_jogo}`),
    el('p', {}, 'Escolha um time à esquerda (elenco, escalação, dados do clube, técnico), busque um jogador, ou abra Mais para ligas, árbitros, técnicos e qualquer tabela. Transferências, empréstimos, números, escalação e cobradores ficam no time e no jogador; Erros verifica o banco inteiro e corrige com um clique.'),
    el('div', { class: 'fluxo-banco' }, ...[
      ['escudo', 'Times', 'Elenco, escalação, formação, capitão, cobradores, tática, dados do clube e técnico.', () => { S.aba = 'times'; desenharAbas(); desenharEsq(); }],
      ['pessoa', 'Jogadores', 'Nomes, posições, notas, atributos, contrato, aparência; transferir, emprestar, liberar.', () => { S.aba = 'jogadores'; desenharAbas(); desenharEsq(); }],
      ['trofeu', 'Ligas', 'Nome, divisão, país; mover times entre ligas (Resto do Mundo com a nação).', () => { S.aba = 'times'; desenharAbas(); desenharEsq(); }],
      ['tabela', 'Tabelas', `Qualquer uma das ${fmt(b.tabelas)} tabelas numa grade: editar, acrescentar e tirar linhas.`, () => { S.aba = 'mais'; desenharAbas(); desenharEsq(); }],
      ['aviso', 'Erros', 'Vínculos quebrados, jogador em dois clubes, números repetidos, escalações e empréstimos inválidos.', () => { S.aba = 'problemas'; desenharAbas(); desenharEsq(); abrir({ tipo: 'problemas' }); }],
    ].map(([ic, t, d, fn]) => el('button', { class: 'cartao-entrada', onclick: fn }, el('span', { html: icone(ic, 22) }), el('b', {}, t), el('small', {}, d))))));
}

// ---------------------------------------------------------------- time
async function vistaTime(p, tid) {
  p.append(el('div', { class: 'vazio' }, 'Carregando o time…'));
  const r = await tentar(() => api('time?id=' + encodeURIComponent(tid)));
  if (!r || S.vista?.id !== tid || S.vista.tipo !== 'time') return;
  p.innerHTML = '';
  const d = r.dados;
  const n = r.elenco.length;
  const geral = r.escalacao?.titulares ? Math.round(r.escalacao.titulares.filter(Boolean).reduce((s, j) => s + (j.overall || 0), 0) / 11) : null;
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta azul' }, 'Time'), el('h1', {}, r.nome),
    el('div', { class: 'sub' }, `${r.liga_nome || 'sem liga'} · teamid ${tid} · ${n} jogador(es)${geral ? ` · titulares ${geral}` : ''}${r.estadio?.nome ? ` · ${r.estadio.nome}` : ''}`)),
  el('div', { class: 'acoes' },
    el('button', { class: 'btn peq', onclick: () => renomearTime(tid, r) }, icone('pincel', 12), 'Renomear'),
    el('button', { class: 'btn peq', onclick: () => moverLiga(tid, r.nome) }, icone('trofeu', 12), 'Mudar de liga'))));
  const abas = el('nav', { class: 'abas' });
  for (const [k, rot, ic] of [['elenco', `Elenco (${n})`, 'lista'], ['escalacao', 'Escalação', 'campo'], ['dados', 'Dados do clube', 'escudo'], ['tecnico', 'Técnico', 'pessoa']]) {
    abas.append(el('button', { class: `aba ${S.subTime === k ? 'ativa' : ''}`, onclick: () => { S.subTime = k; desenharPrincipal(); } }, icone(ic, 14), rot));
  }
  p.append(abas);
  if (S.subTime === 'escalacao') return abaEscalacao(p, tid, r);
  if (S.subTime === 'dados') {
    p.append(formulario({ tabela: 'teams', ref: r.ref, dados: d, campos: r.campos, grupos: GRUPOS_TIME, rotulo: `Dados do ${r.nome}`,
      excluir: ['teamname', 'teamid', ...Object.keys(d).filter((c) => /^teamcolor\d[rgb]$/.test(c) || /takerid$|^captainid$/.test(c))], depois: () => desenharPrincipal() }));
    p.prepend(cores(r));
    return;
  }
  if (S.subTime === 'tecnico') {
    if (!r.tecnico.length) { p.append(nota('Este time não tem técnico na tabela manager.', 'info')); return; }
    for (const t of r.tecnico) {
      p.append(el('h3', { class: 'titulo-sec' }, t.nome || 'Técnico'));
      p.append(formulario({ tabela: 'manager', ref: t.ref, dados: t.dados, campos: r.campos_tecnico, rotulo: `Técnico do ${r.nome}`,
        grupos: [['Nome', ['firstname', 'surname', 'commonname']], ['Dados', ['nationality', 'birthdate', 'teamid', 'gender', 'height', 'weight']],
          ['Aparência', ['skintonecode', 'haircolorcode', 'hairtypecode', 'headtypecode', 'facialhairtypecode', 'eyecolorcode', 'bodytypecode']]], depois: () => desenharPrincipal() }));
    }
    return;
  }
  // elenco
  const tb = el('tbody');
  for (const j of r.elenco) {
    if (j.erro) { tb.append(el('tr', { class: 'erro-linha' }, el('td', {}, j.numero), el('td', { colspan: 9 }, `Jogador ${j.playerid}: ${j.erro}`))); continue; }
    const num = el('input', { type: 'number', class: 'nota', min: 1, max: 99, value: j.numero, style: { width: '52px' },
      onchange: async (e) => { aplicarEstado(await tentar(() => api('trocar_numero', { teamid: tid, pid: j.playerid, numero: e.target.value }))); desenharPrincipal(); } });
    const sit = j.posicao_time < 28 ? 'titular' : j.posicao_time === 28 ? 'banco' : 'reserva';
    tb.append(el('tr', { class: sit === 'titular' ? 'tit' : '' },
      el('td', {}, num),
      el('td', { class: 'nome clicavel', onclick: () => abrir({ tipo: 'jogador', id: j.playerid }) }, el('b', {}, j.nome), el('small', {}, `ID ${j.playerid}`)),
      el('td', {}, j.pos_nome), el('td', { class: 'num' }, el('span', { class: `ov ${classeOv(j.overall)}` }, j.overall)), el('td', { class: 'num' }, j.potencial),
      el('td', { class: 'num' }, idade(j.nascimento) ?? '—'), el('td', {}, j.nacao_nome),
      el('td', {}, j.emprestado_de ? el('span', { class: 'etiqueta laranja', title: `até ${j.emprestado_ate}` }, `emprestado pelo ${j.emprestado_de_nome || j.emprestado_de}`) : el('span', { class: 'mudo' }, sit)),
      el('td', { class: 'acoes-j' },
        el('button', { class: 'btn-icone peq', title: 'Transferir…', onclick: () => dialogoTransferir(j.playerid, j.nome, tid), html: icone('mover', 13) }),
        el('button', { class: 'btn-icone peq', title: 'Emprestar…', onclick: () => dialogoTransferir(j.playerid, j.nome, tid, true), html: icone('relogio', 13) }),
        j.emprestado_de ? el('button', { class: 'btn-icone peq', title: 'Encerrar o empréstimo (volta ao dono)', onclick: () => opRecarregar('encerrar_emprestimo', { pid: j.playerid }), html: icone('restaurar', 13) }) : null,
        el('button', { class: 'btn-icone peq', title: 'Liberar (Sem Contrato)', onclick: () => liberar(j.playerid, j.nome), html: icone('x', 13) }))));
  }
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Elenco'), el('p', { class: 'dica' }, 'Titulares em azul. O número muda direto na tabela (quem usava fica com o antigo). As escalações dos dois times são refeitas a cada transferência.')),
    el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn-primario peq', onclick: () => contratar(tid, r.nome) }, icone('mais', 12), 'Contratar jogador…'),
      el('button', { class: 'btn peq', onclick: () => criarJogador(tid) }, icone('pessoa', 12), 'Criar jogador'))),
  el('div', { class: 'cartao-corpo justo', style: { overflowX: 'auto' } }, el('table', { class: 'tabela elenco' },
    el('thead', {}, el('tr', {}, ...['Nº', 'Jogador', 'Pos.', 'Geral', 'Pot.', 'Idade', 'Nação', 'Situação', ''].map((h) => el('th', {}, h)))), tb))));
}

function cores(r) {
  const d = r.dados;
  const caixa = el('div', { class: 'cores-time' }, el('h4', {}, 'Cores do clube'));
  for (const i of [1, 2, 3]) {
    if (!(`teamcolor${i}r` in d)) continue;
    const hex = '#' + ['r', 'g', 'b'].map((c) => Number(d[`teamcolor${i}${c}`] || 0).toString(16).padStart(2, '0')).join('');
    const inp = el('input', { type: 'color', value: hex, onchange: async (e) => {
      const v = e.target.value;
      const valores = { [`teamcolor${i}r`]: parseInt(v.slice(1, 3), 16), [`teamcolor${i}g`]: parseInt(v.slice(3, 5), 16), [`teamcolor${i}b`]: parseInt(v.slice(5, 7), 16) };
      aplicarEstado(await tentar(() => api('linha_salvar', { tabela: 'teams', ref: r.ref, valores, rotulo: `Cor ${i} do ${r.nome}` })));
    } });
    caixa.append(el('label', { class: 'cor-time' }, inp, ` Cor ${i}`));
  }
  return caixa;
}

// ---------------------------------------------------------------- escalação
function abaEscalacao(p, tid, r) {
  const esc = r.escalacao;
  if (esc.erro) { p.append(nota(esc.erro, 'alerta')); return; }
  const tit = esc.titulares.map((j) => (j ? String(j.playerid) : null));
  const banco = esc.banco.map((j) => String(j.playerid));
  const cob = { ...esc.cobradores };
  const todos = [...esc.titulares.filter(Boolean), ...esc.banco];
  const nomeDe = (pid) => todos.find((j) => String(j.playerid) === String(pid))?.nome || pid;
  let sujo = false;
  const btnSalvar = el('button', { class: 'btn-primario peq', disabled: true, onclick: async () => {
    const x = await tentar(() => api('definir_escalacao', { teamid: tid, titulares: tit, banco, cobradores: cob }));
    if (x) { aplicarEstado(x); aviso('Escalação gravada na edição', { tipo: 'sucesso', tempo: 1600 }); desenharPrincipal(); }
  } }, icone('salvar', 12), 'Gravar a escalação');
  const marcar = () => { sujo = true; btnSalvar.disabled = false; };
  const selForm = el('select', { class: 'seletor' }, ...r.formacoes.map((f) => opt(f.ref, `${f.nome}`, r.formacoes.find((x) => x.nome === esc.formacao)?.ref)));
  p.append(el('div', { class: 'barra-form' },
    el('div', { class: 'acoes-linha' }, el('span', { class: 'mudo' }, 'Formação'), selForm,
      el('button', { class: 'btn peq', onclick: async () => { const x = await tentar(() => api('trocar_formacao', { teamid: tid, ref: selForm.value })); if (x) { aplicarEstado(x); desenharPrincipal(); } } }, 'Trocar'),
      el('button', { class: 'btn peq', title: 'Os 11 melhores para as vagas da formação, o resto pela nota; cobradores pelos atributos', onclick: async () => { const x = await tentar(() => api('reescalar', { teamid: tid })); if (x) { aplicarEstado(x); desenharPrincipal(); } } }, icone('varinha', 12), 'Escalar sozinho')),
    btnSalvar));
  const campo = el('div', { class: 'campo-futebol' });
  const desenharCampo = () => {
    campo.innerHTML = '';
    esc.vagas.forEach((vg, i) => {
      const x = parseFloat(vg.x ?? 0.5), y = parseFloat(vg.y ?? 0.5);
      const sel = el('select', { class: 'sel-vaga', onchange: (e) => {
        const novo = e.target.value;
        const ant = tit[i];
        const j = tit.indexOf(novo);
        if (j >= 0) tit[j] = ant; else { const k = banco.indexOf(novo); if (k >= 0) banco[k] = ant; }
        tit[i] = novo;
        marcar(); desenharCampo(); desenharBanco();
      } }, ...todos.map((jj) => opt(jj.playerid, `${jj.nome} (${jj.pos_nome || '?'} ${jj.overall || ''})`, tit[i])));
      const jj = todos.find((z) => String(z.playerid) === tit[i]);
      const fora = jj && jj.pos !== undefined && jj.pos !== vg.base && !(jj.pos2 || []).includes(vg.base);
      campo.append(el('div', { class: `vaga ${fora ? 'fora-pos' : ''}`, style: { left: `${x * 100}%`, top: `${(1 - y) * 92 + 4}%` }, title: fora ? 'Fora da posição dele' : '' },
        el('span', { class: 'pos-vaga' }, vg.nome), el('span', { class: 'ov-vaga' }, jj?.overall ?? ''), sel));
    });
  };
  const listaBanco = el('ol', { class: 'lista-banco' });
  const desenharBanco = () => {
    listaBanco.innerHTML = '';
    banco.forEach((pid, i) => {
      listaBanco.append(el('li', { class: i < 12 ? 'no-banco' : '' }, el('span', {}, nomeDe(pid)),
        el('span', { class: 'acoes-j' },
          el('button', { class: 'btn-icone peq', disabled: i === 0, onclick: () => { [banco[i - 1], banco[i]] = [banco[i], banco[i - 1]]; marcar(); desenharBanco(); }, html: icone('setaCima', 12) }),
          el('button', { class: 'btn-icone peq', disabled: i === banco.length - 1, onclick: () => { [banco[i + 1], banco[i]] = [banco[i], banco[i + 1]]; marcar(); desenharBanco(); }, html: icone('setaBaixo', 12) }))));
    });
  };
  const cobr = el('div', { class: 'grade-campos' }, ...Object.keys(cob).map((k) => el('div', { class: 'campo-linha' }, el('label', {}, ROT[k] || k),
    el('select', { class: 'seletor', onchange: (e) => { cob[k] = e.target.value; marcar(); } }, opt('', '—', cob[k]), ...todos.map((jj) => opt(jj.playerid, jj.nome, cob[k]))))));
  const tat = el('div', { class: 'grade-campos' }, ...Object.entries(esc.taticas || {}).map(([k, v]) => el('div', { class: 'campo-linha' }, el('label', {}, ROT[k] || k),
    controleCampo('teams', k, k === 'defensivedepth' ? { t3: 3, low: 1, high: 100 } : { t3: 3, low: 0, high: 3 }, v, async (nv) => { aplicarEstado(await tentar(() => api('definir_tatica', { teamid: tid, valores: { [k]: nv } }))); }))));
  desenharCampo(); desenharBanco();
  p.append(el('div', { class: 'grade-escalacao' },
    el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, `Titulares · ${esc.formacao || ''}`), el('p', { class: 'dica' }, 'Escolha o jogador de cada vaga; quem sai vai para o lugar de quem entrou. Vermelho: fora da posição dele.'))),
      el('div', { class: 'cartao-corpo' }, campo)),
    el('div', { class: 'col-gap' },
      el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Banco e reservas'), el('p', { class: 'dica' }, 'Os 12 primeiros (em azul) vão para o banco; ordene com as setas.'))), el('div', { class: 'cartao-corpo' }, listaBanco)),
      el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Capitão e cobradores'))), el('div', { class: 'cartao-corpo' }, cobr)),
      Object.keys(esc.taticas || {}).length ? el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Tática'), el('p', { class: 'dica' }, 'Grava na hora.'))), el('div', { class: 'cartao-corpo' }, tat)) : null)));
  window.onbeforeunload = () => (sujo ? true : undefined);
}

// ---------------------------------------------------------------- jogador
async function vistaJogador(p, pid) {
  p.append(el('div', { class: 'vazio' }, 'Carregando o jogador…'));
  const r = await tentar(() => api('jogador?id=' + encodeURIComponent(pid)));
  if (!r || S.vista?.id !== pid || S.vista.tipo !== 'jogador') return;
  p.innerHTML = '';
  const d = r.dados;
  const clube = r.vinculos.find((v) => v.teamid === r.clube);
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta laranja' }, 'Jogador'), el('h1', {}, r.nomes.nome),
    el('div', { class: 'sub' }, `${S.pos[d.preferredposition1] || ''} · geral ${d.overallrating} · ${idade(diaParaData(d.birthdate)) ?? '?'} anos · ${r.nacao_nome} · ID ${pid}`)),
  el('div', { class: 'acoes' },
    el('button', { class: 'btn peq', onclick: () => dialogoTransferir(pid, r.nomes.nome, r.clube) }, icone('mover', 12), 'Transferir'),
    el('button', { class: 'btn peq', disabled: !r.clube, onclick: () => dialogoTransferir(pid, r.nomes.nome, r.clube, true) }, icone('relogio', 12), 'Emprestar'),
    r.emprestimo ? el('button', { class: 'btn peq', onclick: () => opRecarregar('encerrar_emprestimo', { pid }) }, icone('restaurar', 12), 'Encerrar empréstimo') : null,
    el('button', { class: 'btn peq', onclick: () => liberar(pid, r.nomes.nome) }, icone('x', 12), 'Liberar'),
    el('button', { class: 'btn-fantasma peq perigo', onclick: () => excluirJogador(pid, r.nomes.nome) }, icone('apagar', 12), 'Excluir'))));
  p.append(el('div', { class: 'chips-vinc' }, ...r.vinculos.map((v) => el('button', { class: 'chip clicavel', onclick: () => { S.subTime = 'elenco'; abrir({ tipo: 'time', id: v.teamid }); } },
    icone('escudo', 12), `${v.nome} · nº ${v.numero}`)), r.emprestimo ? el('span', { class: 'etiqueta laranja' }, `emprestado pelo ${r.emprestimo.dono_nome} até ${r.emprestimo.fim}`) : null,
  !r.vinculos.length ? el('span', { class: 'etiqueta vermelha' }, 'sem time') : null));
  // nomes
  if (r.tem_nomes) {
    const n = { ...r.nomes };
    const campoN = (rot, k) => el('div', { class: 'campo-linha' }, el('label', {}, rot), el('input', { type: 'text', class: 'entrada', value: n[k] || '', oninput: (e) => { n[k] = e.target.value; bt.disabled = false; } }));
    const bt = el('button', { class: 'btn-primario peq', disabled: true, onclick: async () => { const x = await tentar(() => api('editar_nomes', { pid, primeiro: n.primeiro, sobrenome: n.sobrenome, comum: n.comum, camisa: n.camisa })); if (x) { aplicarEstado(x); desenharPrincipal(); } } }, icone('salvar', 12), 'Gravar os nomes');
    p.append(el('div', { class: 'grupo-form' }, el('h4', {}, 'Nomes (editedplayernames)'), el('div', { class: 'grade-campos' }, campoN('Nome comum (o que o jogo mostra)', 'comum'), campoN('Nome na camisa', 'camisa'), campoN('Primeiro nome', 'primeiro'), campoN('Sobrenome', 'sobrenome')), el('div', { class: 'acoes-linha' }, bt)));
  }
  p.append(formulario({ tabela: 'players', ref: r.ref, dados: d, campos: r.campos, grupos: GRUPOS_JOGADOR, excluir: ['playerid', 'firstnameid', 'lastnameid', 'commonnameid', 'playerjerseynameid'],
    rotulo: `Jogador ${r.nomes.nome}`, depois: () => desenharPrincipal() }));
  void clube;
}

// ---------------------------------------------------------------- liga
async function vistaLiga(p, lid) {
  const r = await tentar(() => api('liga?id=' + encodeURIComponent(lid)));
  if (!r || S.vista?.id !== lid) return;
  p.innerHTML = '';
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta verde' }, 'Liga'), el('h1', {}, r.nome), el('div', { class: 'sub' }, `${r.pais_nome} · divisão ${r.dados.level} · leagueid ${lid} · ${r.times.length} times`)),
    el('div', { class: 'acoes' }, el('button', { class: 'btn peq', onclick: () => renomearLiga(lid, r) }, icone('pincel', 12), 'Renomear'),
      el('button', { class: 'btn peq', onclick: () => trazerTime(lid, r.nome) }, icone('mais', 12), 'Trazer time para esta liga…'))));
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Times'))), el('div', { class: 'cartao-corpo lista-times-liga' },
    ...r.times.map((t) => el('button', { class: 'chip clicavel', onclick: () => abrir({ tipo: 'time', id: t.teamid }) }, t.nome)))));
  p.append(formulario({ tabela: 'leagues', ref: r.ref, dados: r.dados, campos: r.campos, rotulo: `Liga ${r.nome}`, grupos: [['Liga', ['countryid', 'level', 'iswomencompetition', 'isinternationalleague', 'leaguetype']]],
    excluir: ['leagueid', 'leaguename'], depois: () => { S.arvore = null; desenharPrincipal(); } }));
}

// ---------------------------------------------------------------- pessoas (técnicos, árbitros)
async function vistaPessoas(p, tabela) {
  const busca = el('input', { type: 'search', class: 'entrada', placeholder: 'Buscar pelo nome…', value: S.pessoas.tabela === tabela ? S.pessoas.q : '', style: { maxWidth: '360px' } });
  const lista = el('div', { class: 'lista-pessoas' });
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta' }, 'Pessoas'), el('h1', {}, tabela === 'manager' ? 'Técnicos' : 'Árbitros'),
    el('div', { class: 'sub' }, tabela === 'manager' ? 'tabela manager — o time de cada um sai do campo teamid' : 'tabela referee — a liga de cada um sai do campo leagueid'))),
  el('div', { class: 'acoes-linha', style: { marginBottom: '10px' } }, busca, el('button', { class: 'btn peq', onclick: async () => { const x = await tentar(() => api('linha_nova', { tabela })); if (x) { aplicarEstado(x); abrir({ tipo: 'pessoa', tabela, id: x.ref }); } } }, icone('mais', 12), 'Nova pessoa')), lista);
  let tmr;
  const carregar = async () => {
    S.pessoas = { tabela, q: busca.value };
    const r = await tentar(() => api(`pessoas?tabela=${tabela}&q=${encodeURIComponent(busca.value)}`));
    lista.innerHTML = '';
    for (const x of r?.pessoas || []) lista.append(el('button', { class: 'it-pessoa', onclick: () => abrir({ tipo: 'pessoa', tabela, id: x.ref }) }, el('b', {}, x.nome), el('small', {}, [x.extra, x.nacao].filter(Boolean).join(' · '))));
    if (r && r.total > r.pessoas.length) lista.append(el('div', { class: 'mudo peq-txt' }, `Mostrando ${r.pessoas.length} de ${r.total}: refine a busca.`));
  };
  busca.oninput = () => { clearTimeout(tmr); tmr = setTimeout(carregar, 250); };
  carregar();
}

async function vistaPessoa(p, tabela, ref) {
  const r = await tentar(() => api(`pessoa?tabela=${tabela}&ref=${encodeURIComponent(ref)}`));
  if (!r) return;
  p.innerHTML = '';
  const d = r.dados;
  const nome = d.commonname || `${d.firstname || ''} ${d.surname || ''}`.trim() || ref;
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('button', { class: 'btn-fantasma peq', onclick: () => abrir({ tipo: 'pessoas', id: tabela }) }, '← ', tabela === 'manager' ? 'Técnicos' : 'Árbitros'),
    el('h1', {}, nome), el('div', { class: 'sub' }, `${tabela} · linha ${ref}`)),
  el('div', { class: 'acoes' }, el('button', { class: 'btn-fantasma peq perigo', onclick: async () => { if (!await confirmar(`Tirar ${nome}?`, 'A linha sai da tabela (dá para desfazer).', { rotulo: 'Tirar', perigo: true })) return; aplicarEstado(await tentar(() => api('linha_remover', { tabela, ref }))); abrir({ tipo: 'pessoas', id: tabela }); } }, icone('apagar', 12), 'Tirar'))));
  p.append(formulario({ tabela, ref, dados: d, campos: r.campos, rotulo: `${tabela === 'manager' ? 'Técnico' : 'Árbitro'} ${nome}`,
    grupos: [['Nome', ['firstname', 'surname', 'commonname']], ['Dados', ['nationality', 'birthdate', 'teamid', 'leagueid', 'gender', 'height', 'weight', 'cardstrictness', 'foulstrictness']],
      ['Aparência', ['skintonecode', 'haircolorcode', 'hairtypecode', 'headtypecode', 'facialhairtypecode', 'eyecolorcode', 'bodytypecode']]], depois: () => desenharPrincipal() }));
}

// ---------------------------------------------------------------- tabela (grade)
async function vistaTabela(p, nome, pagina, q, campo) {
  const r = await tentar(() => api(`tabela?nome=${encodeURIComponent(nome)}&pagina=${pagina}&q=${encodeURIComponent(q)}&campo=${encodeURIComponent(campo)}`));
  if (!r || S.vista?.id !== nome) return;
  p.innerHTML = '';
  const busca = el('input', { type: 'search', class: 'entrada', placeholder: 'Buscar…', value: q, style: { maxWidth: '260px' } });
  const selCampo = el('select', { class: 'seletor' }, opt('', 'em todos os campos', campo), ...r.campos.map((c) => opt(c, c, campo)));
  const ir = (pg) => abrir({ tipo: 'tabela', id: nome, pagina: pg, q: busca.value, campo: selCampo.value });
  busca.onkeydown = (e) => { if (e.key === 'Enter') ir(0); };
  selCampo.onchange = () => ir(0);
  const paginas = Math.max(1, Math.ceil(r.total / 100));
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta' }, 'Tabela'), el('h1', {}, nome),
    el('div', { class: 'sub' }, `${fmt(r.total)} linha(s)${q ? ' encontradas' : ''} · ${r.campos.length} campos${r.resumo?.alteradas || r.resumo?.novas || r.resumo?.removidas ? ` · nesta edição: ${r.resumo.alteradas} alterada(s), ${r.resumo.novas} nova(s), ${r.resumo.removidas} removida(s)` : ''}`))),
  el('div', { class: 'acoes-linha', style: { marginBottom: '8px' } }, busca, selCampo, el('button', { class: 'btn peq', onclick: () => ir(0) }, icone('busca', 12), 'Buscar'),
    el('span', { class: 'mudo peq-txt' }, `página ${pagina + 1} de ${paginas}`),
    el('button', { class: 'btn-fantasma peq', disabled: pagina === 0, onclick: () => ir(pagina - 1) }, '‹'), el('button', { class: 'btn-fantasma peq', disabled: pagina >= paginas - 1, onclick: () => ir(pagina + 1) }, '›'),
    el('button', { class: 'btn peq', onclick: async () => { const x = await tentar(() => api('linha_nova', { tabela: nome })); if (x) { aplicarEstado(x); S.tabelas = null; aviso('Linha nova no fim da tabela', { tipo: 'sucesso', tempo: 1600 }); ir(paginas - 1); } } }, icone('mais', 12), 'Linha nova')));
  const thead = el('tr', {}, el('th', {}, ''), ...r.campos.map((c) => { const i = r.info[c] || {}; return el('th', { title: `${c} · ${i.tipo || ''}${i.high ? ` · ${i.low ?? 0}–${i.high}` : ''}${i.chave ? ' · chave' : ''}` }, c); }));
  const tb = el('tbody');
  for (const l of r.linhas) {
    const mud = new Set(l.mudados);
    const tr = el('tr', { class: mud.has('*') ? 'nova' : '' }, el('td', { class: 'acoes-j' },
      el('button', { class: 'btn-icone peq', title: 'Duplicar (linha nova igual a esta)', onclick: async () => { const x = await tentar(() => api('linha_nova', { tabela: nome, modelo: l.ref })); if (x) { aplicarEstado(x); ir(paginas - 1); } }, html: icone('copias', 12) }),
      el('button', { class: 'btn-icone peq', title: 'Tirar a linha', onclick: async () => { aplicarEstado(await tentar(() => api('linha_remover', { tabela: nome, ref: l.ref }))); ir(pagina); }, html: icone('apagar', 12) })));
    l.valores.forEach((v, k) => {
      const c = r.campos[k];
      const td = el('td', { class: `celula ${mud.has(c) || mud.has('*') ? 'mudada' : ''}`, title: `${c}: ${v}` }, v);
      td.ondblclick = () => editarCelula(td, nome, l.ref, c, v, r.info[c] || {}, () => ir(pagina));
      tr.append(td);
    });
    tb.append(tr);
  }
  p.append(el('div', { class: 'grade-tabela' }, el('table', { class: 'tabela grade' }, el('thead', {}, thead), tb)), el('div', { class: 'mudo peq-txt', style: { marginTop: '6px' } }, 'Dois cliques numa célula para editar (Enter grava, Esc cancela). Os valores são conferidos pela faixa do meta.'));
}

function editarCelula(td, tabela, ref, campo, valor, info, depois) {
  const inp = el('input', { class: 'entrada celula-edit', value: valor });
  td.innerHTML = '';
  td.append(inp);
  inp.focus(); inp.select();
  let feito = false;
  const gravar = async () => {
    if (feito) return;
    feito = true;
    if (inp.value === valor) { depois(); return; }
    const x = await tentar(() => api('linha_salvar', { tabela, ref, valores: { [campo]: inp.value }, rotulo: `${tabela}.${campo}` }));
    if (x) aplicarEstado(x);
    depois();
  };
  inp.onkeydown = (e) => { if (e.key === 'Enter') gravar(); if (e.key === 'Escape') { feito = true; depois(); } };
  inp.onblur = gravar;
  void info;
}

// ---------------------------------------------------------------- problemas
async function vistaProblemas(p) {
  p.append(el('div', { class: 'vazio' }, 'Verificando o banco…'));
  const r = await tentar(() => api('verificar' + (S.probs ? '' : '?forcar=1')));
  if (!r || S.vista?.tipo !== 'problemas') return;
  S.probs = r.problemas;
  desenharAbas();
  p.innerHTML = '';
  const cont = { erro: 0, aviso: 0, info: 0 };
  r.problemas.forEach((x) => { cont[x.gravidade] += 1; });
  const tipos = {};
  r.problemas.forEach((x) => { tipos[x.tipo] = (tipos[x.tipo] || 0) + 1; });
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta vermelha' }, 'Verificação'), el('h1', {}, 'Erros do banco'),
    el('div', { class: 'sub' }, `${cont.erro} erro(s) · ${cont.aviso} aviso(s) · ${cont.info} informação(ões) — com as mudanças desta edição`)),
  el('div', { class: 'acoes' }, el('button', { class: 'btn peq', onclick: () => { S.probs = null; desenharPrincipal(); } }, icone('recarregar', 12), 'Verificar de novo'))));
  if (!r.problemas.length) { p.append(nota('Nenhum problema encontrado.', 'info')); return; }
  const filtro = el('div', { class: 'segmentado' }, ...[['todos', `Todos (${r.problemas.length})`], ['erro', `Erros (${cont.erro})`], ['aviso', `Avisos (${cont.aviso})`], ['info', `Info (${cont.info})`]]
    .map(([k, t]) => el('button', { class: S.filtroProb === k ? 'ativo' : '', onclick: () => { S.filtroProb = k; desenharPrincipal(); } }, t)));
  p.append(filtro);
  const porTipo = {};
  for (const x of r.problemas.filter((x) => S.filtroProb === 'todos' || x.gravidade === S.filtroProb)) (porTipo[x.tipo] = porTipo[x.tipo] || []).push(x);
  for (const [tipo, lst] of Object.entries(porTipo)) {
    const fixaveis = lst.filter((x) => x.correcao).length;
    const det = el('details', { class: 'grupo-prob', open: lst.length <= 12 });
    det.append(el('summary', {}, el('span', { class: `selo-grav ${lst[0].gravidade}` }, lst[0].gravidade), el('b', {}, NOME_PROB[tipo] || tipo), el('span', { class: 'mudo' }, ` (${lst.length})`),
      fixaveis > 1 ? el('button', { class: 'btn peq', style: { marginLeft: 'auto' }, onclick: async (ev) => { ev.preventDefault(); if (!await confirmar(`Corrigir os ${fixaveis}?`, `Aplica a correção sugerida em todos os problemas deste tipo (${NOME_PROB[tipo] || tipo}). Dá para desfazer um a um.`, { rotulo: 'Corrigir todos' })) return; const x = await tentar(() => api('corrigir_tipo', { tipo })); if (x) { aplicarEstado(x); aviso(`${x.feitos} correção(ões) aplicada(s)`, { tipo: 'sucesso' }); S.probs = null; desenharPrincipal(); } } }, icone('varinha', 12), `Corrigir todos (${fixaveis})`) : null));
    const ul = el('div', { class: 'lista-prob' });
    for (const x of lst.slice(0, 300)) {
      ul.append(el('div', { class: 'item-prob' }, el('span', {}, x.descricao),
        el('span', { class: 'acoes-j' },
          x.alvo ? el('button', { class: 'btn-fantasma peq', onclick: () => abrir({ tipo: x.alvo.tipo, id: x.alvo.id }) }, 'Abrir') : null,
          x.correcao ? el('button', { class: 'btn peq', onclick: async () => { const y = await tentar(() => api('corrigir', { acao: x.correcao.acao, args: x.correcao.args })); if (y) { aplicarEstado(y); S.probs = null; desenharPrincipal(); } } }, x.correcao.rotulo) : null)));
    }
    if (lst.length > 300) ul.append(el('div', { class: 'mudo peq-txt' }, `… e mais ${lst.length - 300}.`));
    det.append(ul);
    p.append(det);
  }
}
const NOME_PROB = { tpl_jogador: 'Vínculo com jogador que não existe', tpl_time: 'Vínculo com time que não existe', tpl_dup: 'Jogador duas vezes no mesmo elenco',
  dois_clubes: 'Jogador em dois clubes', sem_time: 'Jogadores sem time', numero: 'Número de camisa repetido', poucos: 'Time com menos de 11', muitos: 'Elenco grande demais',
  escalacao: 'Escalação/cobradores fora do elenco', sem_folha: 'Time sem escalação padrão', sem_formacao: 'Time sem formação', emp_jogador: 'Empréstimo de jogador que não existe',
  emp_dono: 'Empréstimo de time que não existe', emp_proprio: 'Emprestado pelo próprio clube', nomes_orfaos: 'Nomes editados sem jogador', orfao_time: 'Linhas de time que não existe',
  chave: 'Chave repetida', faixa: 'Valores fora da faixa', ltl_time: 'Liga com time que não existe', ltl_liga: 'Time em liga que não existe', time_sem_liga: 'Time sem liga',
  especial: 'Times especiais (seleções de estrelas)' };

// ---------------------------------------------------------------- diálogos e operações
async function escolherTime(titulo, { excluir = null } = {}) {
  return new Promise((ok) => {
    const busca = el('input', { type: 'search', class: 'entrada', placeholder: 'Nome do time…', autofocus: true, style: { width: '100%' } });
    const lista = el('div', { class: 'lista-busca' });
    let tmr;
    const m = modal({ titulo, corpo: el('div', { class: 'col-gap' }, busca, lista), botoes: [{ rotulo: 'Cancelar', valor: null }], aoFechar: (v) => ok(v ?? null) });
    const buscar = async () => {
      const r = await tentar(() => api('buscar_times?q=' + encodeURIComponent(busca.value)));
      lista.innerHTML = '';
      for (const t of (r?.times || []).filter((x) => x.teamid !== excluir)) lista.append(el('button', { class: 'it-busca', onclick: () => m.fechar(t) }, el('b', {}, t.nome), el('span', { class: 'mudo' }, `${t.liga} · ${t.teamid}`)));
    };
    busca.oninput = () => { clearTimeout(tmr); tmr = setTimeout(buscar, 220); };
    buscar();
  });
}
async function escolherJogador(titulo) {
  return new Promise((ok) => {
    const busca = el('input', { type: 'search', class: 'entrada', placeholder: 'Nome ou ID…', autofocus: true, style: { width: '100%' } });
    const lista = el('div', { class: 'lista-busca' });
    let tmr;
    const m = modal({ titulo, corpo: el('div', { class: 'col-gap' }, busca, lista), botoes: [{ rotulo: 'Cancelar', valor: null }], aoFechar: (v) => ok(v ?? null) });
    busca.oninput = () => { clearTimeout(tmr); tmr = setTimeout(async () => {
      const r = await tentar(() => api('buscar_jogadores?q=' + encodeURIComponent(busca.value)));
      lista.innerHTML = '';
      for (const j of r?.jogadores || []) lista.append(el('button', { class: 'it-busca', onclick: () => m.fechar(j) }, el('span', { class: `ov ${classeOv(j.overall)}` }, j.overall), el('b', {}, j.nome), el('span', { class: 'mudo' }, `${j.pos} · ${j.clube_nome} · ID ${j.playerid}`)));
    }, 250); };
  });
}

async function dialogoTransferir(pid, nome, de, emprestimo = false) {
  const t = await escolherTime(emprestimo ? `Emprestar ${nome} para…` : `Transferir ${nome} para…`, { excluir: de });
  if (!t) return;
  const num = el('input', { type: 'number', class: 'entrada', min: 1, max: 99, placeholder: 'livre', style: { width: '100px' } });
  const fim = el('input', { type: 'date', class: 'entrada', value: `${new Date().getFullYear() + 1}-06-30` });
  const tipo = el('select', { class: 'seletor' }, opt('t', 'Transferência', emprestimo ? 'e' : 't'), opt('e', 'Empréstimo', emprestimo ? 'e' : 't'));
  const linhaFim = el('div', { class: 'campo' }, el('label', {}, 'Fim do empréstimo'), fim);
  linhaFim.hidden = !emprestimo;
  tipo.onchange = () => { linhaFim.hidden = tipo.value !== 'e'; };
  const ok = await modal({ titulo: `${nome} → ${t.nome}`, corpo: el('div', { class: 'col-gap' }, el('div', { class: 'campo' }, el('label', {}, 'Tipo'), tipo), linhaFim,
    el('div', { class: 'campo' }, el('label', {}, 'Número (vazio = o primeiro livre)'), num),
    nota('As escalações dos dois times são refeitas sozinhas (dá para ajustar depois na aba Escalação).', 'info')),
  botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Confirmar', classe: 'btn-primario', padrao: true, valor: true }] }).promessa;
  if (!ok) return;
  const x = tipo.value === 'e' ? await tentar(() => api('emprestar', { pid, para: t.teamid, fim: fim.value, dono: de }))
    : await tentar(() => api('transferir', { pid, para: t.teamid, numero: num.value || null }));
  if (!x) return;
  aplicarEstado(x);
  S.arvore = null;
  aviso(tipo.value === 'e' ? 'Empréstimo feito' : 'Transferência feita', { tipo: 'sucesso', detalhe: `${nome} → ${t.nome}` });
  desenharPrincipal();
}
async function contratar(tid, nomeTime) {
  const j = await escolherJogador(`Contratar para o ${nomeTime}`);
  if (!j) return;
  const x = await tentar(() => api('transferir', { pid: j.playerid, para: tid }));
  if (x) { aplicarEstado(x); S.arvore = null; aviso(`${j.nome} contratado`, { tipo: 'sucesso', detalhe: `${j.clube_nome} → ${nomeTime}` }); desenharPrincipal(); }
}
async function criarJogador(tid) {
  const inp = el('input', { type: 'text', class: 'entrada', value: 'Jogador Novo', autofocus: true });
  const nome = await modal({ titulo: 'Criar jogador', texto: 'Ele começa como cópia do jogador de nota mais baixa do elenco (aparência e atributos), com ID e nome novos; depois é só editar.',
    corpo: inp, botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Criar', classe: 'btn-primario', padrao: true, fn: () => inp.value.trim() || 'Jogador Novo' }] }).promessa;
  if (!nome) return;
  const x = await tentar(() => api('criar_jogador', { teamid: tid, nome }));
  if (x) { aplicarEstado(x); abrir({ tipo: 'jogador', id: x.pid }); }
}
async function liberar(pid, nome) {
  if (!await confirmar(`Liberar ${nome}?`, 'Ele vai para Sem Contrato (o time dos livres do jogo). Dá para desfazer.', { rotulo: 'Liberar' })) return;
  await opRecarregar('liberar', { pid });
}
async function excluirJogador(pid, nome) {
  if (!await confirmar(`Excluir ${nome} do banco?`, 'Sai de players, dos elencos, do empréstimo, dos nomes editados e das escalações. Dá para desfazer.', { rotulo: 'Excluir', perigo: true })) return;
  const x = await tentar(() => api('excluir_jogador', { pid }));
  if (x) { aplicarEstado(x); S.vista = null; desenharPrincipal(); }
}
async function opRecarregar(rota, d) {
  const x = await tentar(() => api(rota, d));
  if (x) { aplicarEstado(x); S.arvore = null; desenharPrincipal(); }
}
async function renomearTime(tid, r) {
  const v = { nome: r.nome, abrev15: r.idioma['TeamName_Abbr15_'] || '', abrev10: r.idioma['TeamName_Abbr10_'] || '', sigla: r.idioma['TeamName_Abbr3_'] || '' };
  const c = (rot, k, max) => el('div', { class: 'campo' }, el('label', {}, rot), el('input', { type: 'text', class: 'entrada', value: v[k], maxlength: max, oninput: (e) => { v[k] = e.target.value; } }));
  const ok = await modal({ titulo: 'Nome do time', texto: 'Vai em teams.teamname e no idioma (TeamName_…), que sai junto no Gravar.',
    corpo: el('div', { class: 'col-gap' }, c('Nome', 'nome', 59), c('Abreviado (15)', 'abrev15', 15), c('Abreviado (10)', 'abrev10', 10), c('Sigla (3)', 'sigla', 3)),
    botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Gravar', classe: 'btn-primario', padrao: true, valor: true }] }).promessa;
  if (!ok || !v.nome.trim()) return;
  const x = await tentar(() => api('renomear_time', { teamid: tid, nome: v.nome.trim(), abrev15: v.abrev15 || null, abrev10: v.abrev10 || null, sigla: v.sigla || null }));
  if (x) { aplicarEstado(x); S.arvore = null; desenharEsq(); desenharPrincipal(); }
}
async function renomearLiga(lid, r) {
  const v = { nome: r.nome, abrev15: r.idioma['LeagueName_Abbr15_'] || '' };
  const ok = await modal({ titulo: 'Nome da liga', corpo: el('div', { class: 'col-gap' },
    el('div', { class: 'campo' }, el('label', {}, 'Nome'), el('input', { type: 'text', class: 'entrada', value: v.nome, oninput: (e) => { v.nome = e.target.value; } })),
    el('div', { class: 'campo' }, el('label', {}, 'Abreviado (15)'), el('input', { type: 'text', class: 'entrada', maxlength: 15, value: v.abrev15, oninput: (e) => { v.abrev15 = e.target.value; } }))),
  botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Gravar', classe: 'btn-primario', padrao: true, valor: true }] }).promessa;
  if (!ok || !v.nome.trim()) return;
  const x = await tentar(() => api('renomear_liga', { leagueid: lid, nome: v.nome.trim(), abrev15: v.abrev15 || null }));
  if (x) { aplicarEstado(x); S.arvore = null; desenharEsq(); desenharPrincipal(); }
}
async function moverLiga(tid, nome) {
  if (!S.arvore) S.arvore = await tentar(() => api('arvore'));
  const sel = el('select', { class: 'seletor' }, ...(S.arvore?.ligas || []).map((l) => opt(l.leagueid, `${l.pais_nome} · ${l.nome} (${l.leagueid})`, '')));
  const ok = await modal({ titulo: `${nome}: mudar de liga`, texto: 'No Resto do Mundo (76/2226) o time entra com a nação da liga de onde saiu (teamnationlinks). Para o modo carreira, a liga nova também precisa do compdata.',
    corpo: sel, botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Mudar', classe: 'btn-primario', padrao: true, valor: true }] }).promessa;
  if (!ok) return;
  const x = await tentar(() => api('mover_liga', { teamid: tid, liga: sel.value }));
  if (x) { aplicarEstado(x); S.arvore = null; desenharEsq(); desenharPrincipal(); }
}
async function trazerTime(lid, nomeLiga) {
  const t = await escolherTime(`Trazer um time para a ${nomeLiga}`);
  if (!t) return;
  const x = await tentar(() => api('mover_liga', { teamid: t.teamid, liga: lid }));
  if (x) { aplicarEstado(x); S.arvore = null; desenharEsq(); desenharPrincipal(); }
}

async function desfazer() {
  const x = await tentar(() => api('desfazer', {}));
  if (!x) return;
  aplicarEstado(x);
  aviso(`Desfeito: ${x.desfeito}`, { tipo: 'info', tempo: 2200 });
  S.arvore = null; S.probs = null;
  desenharPrincipal();
}
async function descartar() {
  if (!await confirmar('Descartar todas as mudanças?', 'A edição volta ao banco importado, sem nenhuma mudança. Não dá para desfazer isto.', { rotulo: 'Descartar tudo', perigo: true })) return;
  aplicarEstado(await tentar(() => api('descartar', {})));
  S.arvore = null; S.probs = null; S.tabelas = null;
  desenharEsq(); desenharPrincipal();
}
async function gravar() {
  const e = S.e;
  const pasta = el('input', { type: 'text', class: 'entrada mono', value: e.saida || '', placeholder: 'escolha a pasta…', spellcheck: 'false' });
  const nome = el('input', { type: 'text', class: 'entrada', value: `Banco editado ${new Date().toISOString().slice(0, 16).replace('T', ' ').replace(':', 'h')}` });
  const probs = await api('verificar').catch(() => null);
  const erros = (probs?.problemas || []).filter((x) => x.gravidade === 'erro').length;
  const ok = await modal({ titulo: 'Gravar banco novo', texto: 'Uma cópia do banco importado com as mudanças desta edição: db\\fifa_ng_db.db (+ meta), as tabelas mexidas em .txt, o idioma e um relatório. O banco original não muda.',
    corpo: el('div', { class: 'col-gap' },
      el('div', { class: 'campo' }, el('label', {}, 'Pasta'), el('div', { class: 'caminho-linha' }, pasta, el('button', { class: 'btn', onclick: async () => { const r = await tentar(() => api('dialogo', {})); if (r?.caminho) pasta.value = r.caminho; } }, icone('pasta', 14)))),
      el('div', { class: 'campo' }, el('label', {}, 'Nome da pasta do banco'), nome),
      erros ? nota(`A verificação achou <b>${erros} erro(s)</b> (veja a aba Erros). Dá para gravar assim mesmo, mas o jogo pode fechar com vínculos quebrados.`, 'alerta') : nota('A verificação não achou erros.', 'info')),
    botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Gravar', classe: 'btn-primario', padrao: true, fn: () => (pasta.value.trim() ? true : (aviso('Escolha a pasta', { tipo: 'aviso' }), false)) }] }).promessa;
  if (!ok) return;
  aplicarEstado(await tentar(() => api('gravar', { pasta: pasta.value.trim(), nome: nome.value.trim() })));
}
function fimGravar(t) {
  if (t.erro) { aviso('A gravação falhou', { tipo: 'erro', detalhe: t.erro, tempo: 12000 }); return; }
  const r = t.resultado || {};
  modal({ titulo: 'Banco gravado', texto: esc(r.pasta || ''), corpo: el('div', {},
    el('p', {}, `${Object.keys(r.tabelas || {}).length} tabela(s) mexida(s): ${Object.keys(r.tabelas || {}).join(', ')}. Textos de idioma: ${r.idioma || 0}.`),
    ...(r.avisos || []).slice(0, 6).map((a) => nota(esc(a), 'alerta')),
    el('p', { class: 'mudo peq-txt' }, 'Importe db\\fifa_ng_db.db no FET (ou as tabelas .txt pelo RDBM/DB Master) e, se houver, o idioma. A edição continua aberta: dá para seguir editando e gravar de novo.')),
  botoes: [{ rotulo: 'Abrir a pasta', classe: 'btn-primario', padrao: true, fn: () => { tentar(() => api('abrir', { caminho: r.pasta })); } }] });
}
function acompanhar() {
  if (S.polling) return;
  S.polling = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (!e) return;
    aplicarEstado(e);
    if (!e.tarefa.ativa) { clearInterval(S.polling); S.polling = null; }
  }, 700);
}

// ---------------------------------------------------------------- menus
function menus() {
  barraMenus($('#menus'), [
    ['Banco', () => [
      { rotulo: 'Gravar banco novo…', icone: 'bancoDados', atalho: 'Ctrl+S', desabilitado: !S.e?.edicao?.mudancas, fn: gravar },
      { rotulo: 'Desfazer', icone: 'desfazer', atalho: 'Ctrl+Z', desabilitado: !(S.e?.edicao?.historico || []).length, fn: desfazer },
      '-',
      { rotulo: 'Verificar erros', icone: 'aviso', fn: () => { S.aba = 'problemas'; desenharAbas(); desenharEsq(); S.probs = null; abrir({ tipo: 'problemas' }); } },
      '-',
      { rotulo: 'Descartar todas as mudanças…', icone: 'apagar', desabilitado: !S.e?.edicao?.mudancas, fn: descartar },
    ]],
    ['Exibir', () => [
      { rotulo: 'Times', marcado: S.aba === 'times', fn: () => { S.aba = 'times'; desenharAbas(); desenharEsq(); } },
      { rotulo: 'Jogadores', marcado: S.aba === 'jogadores', fn: () => { S.aba = 'jogadores'; desenharAbas(); desenharEsq(); } },
      { rotulo: 'Mais (pessoas e tabelas)', marcado: S.aba === 'mais', fn: () => { S.aba = 'mais'; desenharAbas(); desenharEsq(); } },
      '-',
      { rotulo: 'Recarregar as listas', icone: 'recarregar', fn: () => { S.arvore = null; S.tabelas = null; desenharEsq(); } },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Sobre o Editor de Banco', icone: 'info', fn: () => dialogoSobre({ nome: 'Editor de Banco', versao: S.ini.versao, html: `
        Edita o banco importado em Dados do jogo (FIFA 16, 21, 22, 23, FC 24, 26 e 27): times (elenco, escalação, formação, capitão,
        cobradores, tática, cores, dados do clube, técnico), jogadores (nomes, posições, notas, atributos, contrato, aparência),
        transferências, empréstimos, liberar, números, ligas (mover times, Resto do Mundo com a nação), árbitros, técnicos e qualquer
        tabela numa grade. A verificação acha vínculos quebrados, jogadores em dois clubes, números repetidos, escalações e
        empréstimos inválidos e valores fora da faixa, com correção. As mudanças ficam numa edição salva sozinha, com desfazer;
        o Gravar escreve um banco novo (o original não muda), com as tabelas em .txt e o idioma.<br><br><b>1.0</b> — primeira versão.` }) },
    ]],
  ]);
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) { e.preventDefault(); desfazer(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (S.e?.edicao?.mudancas) gravar(); }
});

async function iniciar() {
  divisorArrastavel($('#div-esq'), '--esq', { min: 230, max: 520 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 260, max: 520, lado: 'dir' });
  const r = await api('inicio');
  S.ini = r;
  S.nacoes = r.nacoes || [];
  S.pos = r.posicoes || {};
  $('#versao').textContent = r.versao;
  $('#btn-gravar').onclick = gravar;
  $('#btn-desfazer').onclick = desfazer;
  aplicarEstado(r);
  menus();
  desenharAbas();
  desenharEsq();
  desenharPrincipal();
  // o banco do Super Tool pode mudar com a ferramenta aberta
  setInterval(async () => {
    if (S.polling) return;
    const e = await api('estado').catch(() => null);
    if (e && JSON.stringify(e.banco?.caminho) !== JSON.stringify(S.e?.banco?.caminho)) {
      const ri = await api('inicio').catch(() => null);
      if (ri) { S.nacoes = ri.nacoes || []; aplicarEstado(ri); }
      S.arvore = null; S.tabelas = null; S.probs = null; S.vista = null;
      desenharEsq(); desenharPrincipal();
    }
  }, 6000);
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
