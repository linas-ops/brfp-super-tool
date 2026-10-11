// Criador de Ligas e Times — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, confirmar, barraMenus, abrirMenu, divisorArrastavel, dialogoSobre, interruptor, nota, modalAberto, menuAberto } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { instalarComponentes } from './comum/componentes.js';

const TM = 'transfermarkt';
const chavePais = (f) => (f === TM ? 'criador.pais_tm' : 'criador.pais');
const lerLocal = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const gravarLocal = (k, v) => { try { localStorage.setItem(k, v); } catch { /* sem armazenamento */ } };
const novaNav = (f) => ({ fonte: f, paises: null, pais: lerLocal(chavePais(f)) || 'Brazil', ligas: null, liga: null, temporada: null, temporadas: null, times: null, busca: '', resultados: null });
const S = { e: null, versao: '', ligasDb: [], nacoes: [], formacoes: [], estadios: [], aba: 'api', previa: {}, polling: null, tarefaAntes: false,
  nav: novaNav(null), marcados: new Set(), marcadosProj: new Set(),
  atual: { ligas: null, ligasSel: [], sel: null, liga: null, sugestao: null, busca: '', filtro: 'todas', marcadas: new Set(), lote: false,
    loteMarcadas: null, opLote: null, selecoes: null, selLista: null, selMarcadas: new Set() } };
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');
const fonteAtual = () => S.e?.opcoes?.fonte || 'apifootball';
const ehTm = (x) => (x?.fonte || x?.api?.fonte) === TM;
const nomeFonte = (x) => (ehTm(x) ? 'Transfermarkt' : 'API-Football');
const curtaFonte = (x) => (ehTm(x) ? 'Transfermarkt' : 'API');
const tempNome = (i) => i.temporada_nome || i.temporada || 'atual';
const pedidos = (x, n) => (ehTm(x) ? `${n} pedido(s)` : `${n} chamada(s)`);
const euros = (v) => {
  if (!v) return '—';
  if (v >= 1e9) return `€ ${(v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} bi`;
  if (v >= 1e6) return `€ ${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`;
  return `€ ${Math.round(v / 1e3)} mil`;
};
const MODO_TM = { local: 'servidor local', publico: 'instância pública', outro: 'outro endereço' };
const POS = { 0: 'GOL', 2: 'ALD', 3: 'LD', 5: 'ZAG', 7: 'LE', 8: 'ALE', 10: 'VOL', 12: 'MD', 14: 'MC', 16: 'ME', 18: 'MEI', 21: 'SA', 23: 'PD', 25: 'ATA', 27: 'PE' };
const PELE = { 10: '#f3d6c2', 20: '#e8c0a2', 30: '#d8a987', 40: '#c69371', 50: '#b17d5b', 60: '#9a6847', 70: '#825538', 80: '#69432d', 90: '#503223', 100: '#3a2419' };
// cores de cabelo do jogo (nome aproximado, medido nas fotos de jogadores do banco)
const CABELO = { 0: 'Preto', 21: 'Preto-azulado', 3: 'Castanho-escuro', 6: 'Castanho-escuro frio', 4: 'Castanho-acinzentado', 5: 'Castanho', 19: 'Castanho-avermelhado', 2: 'Castanho-claro', 20: 'Cinza-escuro', 1: 'Ruivo', 15: 'Loiro', 12: 'Loiro-escuro', 13: 'Loiro-claro', 18: 'Grisalho', 7: 'Branco' };
const PROF = { 30: 'Recuada', 50: 'Equilibrada', 65: 'Alta', 90: 'Agressiva' };
const SAIDA = { 1: 'Passe curto', 2: 'Equilibrada', 3: 'Bola longa' };
const ATR = [['Ritmo', ['acceleration', 'sprintspeed']], ['Finalização', ['positioning', 'finishing', 'shotpower', 'longshots', 'volleys', 'penalties']],
  ['Passe', ['vision', 'crossing', 'freekickaccuracy', 'shortpassing', 'longpassing', 'curve']], ['Drible', ['agility', 'balance', 'reactions', 'ballcontrol', 'dribbling', 'composure']],
  ['Defesa', ['interceptions', 'headingaccuracy', 'defensiveawareness', 'standingtackle', 'slidingtackle']], ['Físico', ['jumping', 'stamina', 'strength', 'aggression']],
  ['Goleiro', ['gkdiving', 'gkhandling', 'gkkicking', 'gkpositioning', 'gkreflexes']]];
const NOME_ATR = { acceleration: 'Aceleração', sprintspeed: 'Arrancada', positioning: 'Posicionamento', finishing: 'Finalização', shotpower: 'Força do chute', longshots: 'Chute de longe', volleys: 'Voleio', penalties: 'Pênaltis', vision: 'Visão', crossing: 'Cruzamento', freekickaccuracy: 'Falta', shortpassing: 'Passe curto', longpassing: 'Passe longo', curve: 'Curva', agility: 'Agilidade', balance: 'Equilíbrio', reactions: 'Reação', ballcontrol: 'Controle', dribbling: 'Drible', composure: 'Compostura', interceptions: 'Interceptação', headingaccuracy: 'Cabeceio', defensiveawareness: 'Marcação', standingtackle: 'Desarme em pé', slidingtackle: 'Carrinho', jumping: 'Impulsão', stamina: 'Fôlego', strength: 'Força', aggression: 'Agressividade', gkdiving: 'Elasticidade', gkhandling: 'Manejo', gkkicking: 'Chute (GOL)', gkpositioning: 'Posicionamento (GOL)', gkreflexes: 'Reflexos' };
async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro', tempo: 7000 }); return undefined; } }
const classeOv = (v) => (v >= 80 ? 'a' : v >= 70 ? 'b' : v >= 60 ? 'c' : 'd');
const im = (u) => (u ? '/img?u=' + encodeURIComponent(u) : '');
const itemSel = () => (S.e?.itens || []).find((i) => i.id === S.e.sel);
const nomeNacao = (id) => S.nacoes.find((n) => String(n.id) === String(id))?.nome || (id ? `nação ${id}` : '—');
const opt = (v, t, sel) => { const o = el('option', { value: v }, t); o.selected = String(sel) === String(v); return o; };
const idadeDe = (iso) => { if (!iso) return null; const n = new Date(iso + 'T00:00:00'); const h = new Date(); let a = h.getFullYear() - n.getFullYear(); if (h.getMonth() < n.getMonth() || (h.getMonth() === n.getMonth() && h.getDate() < n.getDate())) a -= 1; return a; };

function aplicar(e) {
  if (!e) return;
  const ativa = e.tarefa?.ativa;
  const antes = itemSel();
  S.e = e;
  const depois = itemSel();
  const mudouSel = antes && depois && antes.id === depois.id && (antes.estado !== depois.estado || antes.nivel !== depois.nivel || antes.fotos !== depois.fotos);
  desenharAbas();
  desenharProjeto();
  if (S.aba === 'atualizar') desenharAtualizarEsq();
  desenharTopo();
  desenharPropriedades();
  desenharStatus();
  if (ativa) acompanhar();
  if (S.tarefaAntes && !ativa) fimTarefa(e.tarefa);
  else if (mudouSel && S.aba !== 'atualizar') desenharPrincipal();
  S.tarefaAntes = !!ativa;
}
async function atualizar() { aplicar(await tentar(() => api('estado'))); }

// ---------------------------------------------------------------- painel esquerdo: abas
function desenharAbas() {
  const a = $('#abas-esq');
  a.innerHTML = '';
  const n = S.e.itens.filter((i) => i.tipo === 'time').length;
  const nu = (S.e.atualizacoes || []).reduce((s, x) => s + (x.marcadas || 0), 0);
  for (const [k, rot, ic] of [['api', 'API', 'mundo'], ['projeto', 'Projeto', 'lista'], ['atualizar', 'Atualizar banco', 'recarregar']]) {
    a.append(el('button', { class: S.aba === k ? 'ativa' : '', onclick: () => trocarAba(k) }, el('span', { html: icone(ic, 14) }), rot,
      k === 'projeto' && n ? el('span', { class: 'n' }, fmt(n)) : null, k === 'atualizar' && nu ? el('span', { class: 'n' }, fmt(nu)) : null));
  }
  $('#esq-api').hidden = S.aba !== 'api';
  $('#esq-projeto').hidden = S.aba !== 'projeto';
  $('#esq-atualizar').hidden = S.aba !== 'atualizar';
}
function trocarAba(k) {
  const antes = S.aba;
  S.aba = k;
  desenharAbas();
  if (k === 'atualizar') desenharAtualizarEsq();
  if ((antes === 'atualizar') !== (k === 'atualizar')) desenharPrincipal();
  desenharPropriedades();
}

// ---------------------------------------------------------------- navegação na API
function seletorFonte() {
  return el('div', { class: 'nav-fonte' }, seg(fonteAtual(), [['apifootball', 'API-Football', 'api-sports.io: precisa de chave; o plano grátis dá 100 chamadas por dia e não libera a temporada atual'],
    [TM, 'Transfermarkt', 'transfermarkt-api: sem chave e sem limite diário no servidor local; valor de mercado, posições e pé de cada jogador']], trocarFonte));
}
async function trocarFonte(f) {
  if (f === fonteAtual()) return;
  await opcoes({ fonte: f });
  S.nav = novaNav(f);
  S.marcados = new Set();
  S.atual.sugestao = null;
  desenharApi();
  if (S.aba === 'atualizar') desenharAtualizacao();
}
function falhou(p, msg, fn) {
  p.append(el('div', { class: 'arvore-vazia' }, nota(esc(msg), 'alerta'), el('button', { class: 'btn peq', onclick: fn }, icone('recarregar', 12), 'Tentar de novo')));
}

async function desenharApi() {
  const p = $('#esq-api');
  p.innerHTML = '';
  const f = fonteAtual();
  if (S.nav.fonte !== f) S.nav = novaNav(f);
  const tm = f === TM;
  p.append(seletorFonte());
  if (!tm && !S.e.api.tem_chave) {
    p.append(el('div', { class: 'arvore-vazia' }, nota('Cole a chave da API-Football no painel da direita (dashboard.api-football.com) — ou use a Transfermarkt, que não precisa de chave.', 'alerta')));
    return;
  }
  const nv = S.nav;
  if (!nv.paises) {
    const carregando = el('div', { class: 'arvore-vazia' }, tm ? `Carregando os países (Transfermarkt, ${MODO_TM[S.e.tm?.modo] || '…'})…` : 'Carregando os países…');
    p.append(carregando);
    const r = await tentar(() => api('paises' + (tm ? '?fonte=transfermarkt' : '')));
    if (S.nav !== nv) return;
    if (!r) { carregando.remove(); falhou(p, tm ? 'A Transfermarkt não respondeu. Veja o servidor no painel da direita (Testar).' : 'A API não respondeu.', desenharApi); return; }
    nv.paises = r.paises;
    return desenharApi();
  }
  const intl = tm ? 'Internacional' : 'World';
  const sel = el('select', { class: 'seletor', onchange: (e) => { nv.pais = e.target.value; gravarLocal(chavePais(f), nv.pais); nv.ligas = null; nv.liga = null; nv.resultados = null; desenharApi(); } },
    opt(intl, `${tm ? 'Internacional' : 'Mundo'} — seleções e copas internacionais`, nv.pais), ...nv.paises.filter((x) => x.name !== intl).map((x) => opt(x.name, x.name, nv.pais)));
  const caixaPais = el('div', { class: 'nav-pais' }, el('div', { class: 'linha' }, el('span', { html: icone('mundo', 14) }), sel));
  p.append(caixaPais);
  if (nv.liga) return desenharLigaApi(p);
  if (tm && nv.pais !== intl) {
    caixaPais.append(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', title: 'A seleção principal do país, com a convocação atual', onclick: () => adicionarSelecaoTm(nv.pais) }, icone('mais', 12), `Seleção: ${nv.pais}`)));
  }
  if (!nv.ligas) {
    const carregando = el('div', { class: 'arvore-vazia' }, 'Carregando as competições…');
    p.append(carregando);
    const r = await tentar(() => api(`ligas?pais=${encodeURIComponent(nv.pais)}${tm ? '&fonte=transfermarkt' : ''}`));
    if (S.nav !== nv) return;
    if (!r) { carregando.remove(); falhou(p, 'Não deu para carregar as competições.', desenharApi); return; }
    nv.ligas = r.ligas;
    return desenharApi();
  }
  const busca = el('input', { type: 'search', placeholder: tm ? 'Filtrar (Enter busca em toda a Transfermarkt)…' : 'Buscar competição…', value: nv.busca, spellcheck: 'false' });
  const lista = el('div', { class: 'arvore' });
  const buscarTm = async () => {
    const q = busca.value.trim();
    if (q.length < 3) return;
    lista.innerHTML = '';
    lista.append(el('div', { class: 'arvore-vazia' }, `Buscando “${q}” na Transfermarkt…`));
    const r = await tentar(() => api('buscar_ligas?q=' + encodeURIComponent(q)));
    if (S.nav !== nv) return;
    nv.resultados = r?.ligas || [];
    desenhar();
  };
  const linhaTm = (l) => el('button', { class: 'it-api', title: `${l.nome}${l.pais ? ` — ${l.pais}` : ''} · ID ${l.id}`, onclick: () => abrirLiga(l) },
    el('img', { src: im(l.logo), alt: '', loading: 'lazy', onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
    el('span', { class: 'txt' }, el('b', {}, l.nome), el('small', {}, [l.tipo === 'Cup' ? 'Copa' : 'Liga', nv.resultados ? (l.pais === 'Internacional' ? 'internacional' : l.pais) : null,
      l.clubes ? `${l.clubes} ${l.selecoes ? 'seleções' : 'clubes'}` : null, l.valor ? euros(l.valor) : null].filter(Boolean).join(' · '))),
    el('span', { class: 'lado' }, el('span', { class: 'cob ok', title: 'Valor de mercado, posições e pé de cada jogador' }, 'TM')));
  const desenhar = () => {
    lista.innerHTML = '';
    if (tm && nv.resultados) {
      lista.append(el('div', { class: 'migalha' }, el('button', { onclick: () => { nv.resultados = null; desenhar(); } }, `← competições de ${nv.pais}`), el('span', {}, '/'), el('b', {}, `busca: ${nv.busca}`)));
      for (const l of nv.resultados) lista.append(linhaTm(l));
      if (!nv.resultados.length) lista.append(el('div', { class: 'arvore-vazia' }, 'A Transfermarkt não achou nada com esse nome.'));
      return;
    }
    const q = busca.value.trim().toLowerCase();
    const ls = nv.ligas.filter((l) => !q || l.nome.toLowerCase().includes(q));
    for (const l of ls) {
      if (tm) { lista.append(linhaTm(l)); continue; }
      const fem = /\b(women|feminin|femenin|frauen|ladies)\b|\bw$/i.test(l.nome);
      lista.append(el('button', { class: 'it-api', title: `${l.nome} — temporadas ${l.temporadas[0]}–${l.temporadas[l.temporadas.length - 1]}`, onclick: () => abrirLiga(l) },
        el('img', { src: im(l.logo), alt: '', loading: 'lazy', onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
        el('span', { class: 'txt' }, el('b', {}, l.nome), el('small', {}, `${l.tipo === 'Cup' ? 'Copa' : 'Liga'} · ${l.temporadas[0]}–${l.atual}${fem ? ' · feminino' : ''}`)),
        el('span', { class: 'lado' }, el('span', { class: `cob ${l.jogadores ? 'ok' : ''}`, title: l.jogadores ? 'Tem jogadores com estatísticas' : 'Sem estatísticas de jogadores' }, 'J'),
          el('span', { class: `cob ${l.escalacoes ? 'ok' : ''}`, title: l.escalacoes ? 'Tem escalações (posições dos jogadores)' : 'Sem escalações' }, 'E'))));
    }
    if (!ls.length) lista.append(el('div', { class: 'arvore-vazia' }, 'Nenhuma competição.'));
    if (tm && q.length >= 3) lista.append(el('div', { class: 'acoes-linha', style: { padding: '8px 10px' } }, el('button', { class: 'btn-fantasma peq', onclick: buscarTm }, icone('busca', 12), `Buscar “${busca.value.trim()}” em toda a Transfermarkt`)));
  };
  busca.oninput = () => { nv.busca = busca.value; nv.resultados = null; desenhar(); };
  if (tm) busca.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); buscarTm(); } };
  p.append(el('div', { class: 'busca-linha' }, el('label', { class: 'campo-busca' }, el('span', { html: icone('busca', 14) }), busca)), lista);
  if (nv.pais === intl) p.append(el('div', { class: 'painel-rodape' }, el('span', { class: 'mudo peq-txt' }, tm ? 'Seleções: abra a Copa do Mundo, a Eurocopa, a Copa América… e escolha as seleções — ou escolha um país e use “Seleção”.' : 'Seleções: abra uma competição de seleções (Copa do Mundo, Copa América, Eurocopa…) e escolha as seleções.')));
  desenhar();
}

async function adicionarSelecaoTm(pais) {
  const r = await tentar(() => api('selecao_tm?pais=' + encodeURIComponent(pais)));
  if (!r) return;
  const x = await tentar(() => api('adicionar_times', { times: [r.time], liga: { id: null, nome: `Seleção de ${pais}`, fonte: TM, pais }, temporada: null }));
  if (!x) return;
  aplicar(x);
  desenharApi();
  desenharPrincipal();
  aviso(`${r.time.nome} no projeto`, { tipo: 'sucesso', tempo: 2600, detalhe: 'Seleção com a convocação atual da Transfermarkt. Colete os dados no topo.' });
}

function temporadasLiberadas() {
  const t = S.e.api.temporadas;
  return t ? (a) => a >= t[0] && a <= t[1] : () => true;
}

async function abrirLiga(l) {
  const nv = S.nav;
  nv.liga = l;
  if (ehTm(l)) {
    nv.temporadas = null;
    nv.temporada = null;
  } else {
    const livre = temporadasLiberadas();
    const ok = l.temporadas.filter(livre);
    nv.temporada = (ok.length ? ok[ok.length - 1] : l.atual);
  }
  nv.times = null;
  S.marcados = new Set();
  desenharApi();
}

function ligaComTemporada() {
  const nv = S.nav;
  if (!ehTm(nv.liga)) return nv.liga;
  return { ...nv.liga, temporada_nome: (nv.temporadas || []).find((s) => s.id === nv.temporada)?.nome || null };
}

async function desenharLigaApi(p) {
  const nv = S.nav;
  const l = nv.liga;
  const tm = ehTm(l);
  p.append(el('div', { class: 'migalha' }, el('button', { onclick: () => { nv.liga = null; desenharApi(); } }, nv.resultados ? '← busca' : '← competições'), el('span', {}, '/'), el('b', {}, l.nome)));
  if (tm && !nv.temporadas) {
    const carregando = el('div', { class: 'arvore-vazia' }, 'Carregando as temporadas…');
    p.append(carregando);
    const r = await tentar(() => api('temporadas?liga=' + encodeURIComponent(l.id)));
    if (S.nav !== nv || nv.liga !== l) return;
    if (!r) { carregando.remove(); falhou(p, 'Não deu para carregar as temporadas.', desenharApi); return; }
    nv.temporadas = r.temporadas || [];
    nv.temporada = nv.temporadas[0]?.id ?? null;
    return desenharApi();
  }
  const livre = tm ? () => true : temporadasLiberadas();
  const selT = tm
    ? el('select', { class: 'seletor', disabled: !nv.temporadas.length, onchange: (e) => { nv.temporada = e.target.value; nv.times = null; S.marcados = new Set(); desenharApi(); } },
      ...(nv.temporadas.length ? nv.temporadas.map((x, k) => opt(x.id, `${x.nome}${k === 0 ? ' · atual' : ''}`, nv.temporada)) : [opt('', 'atual', '')]))
    : el('select', { class: 'seletor', onchange: (e) => { nv.temporada = +e.target.value; nv.times = null; S.marcados = new Set(); desenharApi(); } },
      ...[...l.temporadas].reverse().map((a) => opt(a, `${a}${livre(a) ? '' : ' (plano pago)'}${a === l.atual ? ' · atual' : ''}`, nv.temporada)));
  const caixa = el('div', { class: 'nav-pais' }, el('div', { class: 'linha' }, el('span', { class: 'mudo peq-txt' }, 'Temporada'), selT));
  p.append(caixa);
  if (!livre(nv.temporada)) caixa.append(nota(`O plano ${esc(S.e.api.plano || 'grátis')} não libera ${nv.temporada}. Use o elenco atual de uma temporada liberada ou assine um plano maior.`, 'alerta'));
  const lista = el('div', { class: 'arvore' });
  p.append(lista);
  if (!nv.times) {
    lista.append(el('div', { class: 'arvore-vazia' }, 'Carregando os times…'));
    const url = tm ? `times?fonte=transfermarkt&liga=${encodeURIComponent(l.id)}&temporada=${encodeURIComponent(nv.temporada ?? '')}&pais=${encodeURIComponent(l.pais || '')}&selecoes=${l.selecoes ? 1 : 0}`
      : `times?liga=${l.id}&temporada=${nv.temporada}`;
    const r = await tentar(() => api(url));
    if (S.nav !== nv || nv.liga !== l) return;
    if (!r) { lista.innerHTML = ''; return; }
    nv.times = r.times;
    lista.innerHTML = '';
  }
  const selecoes = nv.times.some((t) => t.selecao);
  const noProjeto = new Set(S.e.itens.map((i) => i.id));
  const idDe = (t) => (tm ? (t.selecao ? `TMS${t.id}` : `TMT${t.id}-${nv.temporada}`) : t.selecao ? `S${t.id}-${nv.temporada}` : `T${t.id}-${nv.temporada}`);
  const acoes = el('div', { class: 'acoes-linha' });
  const desenharAcoes = () => {
    acoes.innerHTML = '';
    const k = S.marcados.size;
    if (selecoes) {
      acoes.append(el('button', { class: 'btn-primario peq', disabled: !k, onclick: () => adicionarTimes([...S.marcados]) }, icone('mais', 12), k ? `Pôr ${k} seleção(ões) no projeto` : 'Marque as seleções'));
    } else {
      acoes.append(el('button', { class: 'btn-primario peq', disabled: !nv.times.length, title: k ? 'Liga nova só com os times marcados' : 'Todos os times viram uma liga do projeto', onclick: () => adicionarLiga(ligaComTemporada(), nv.temporada, k ? [...S.marcados] : null) },
        icone('trofeu', 12), k ? `Liga com ${k} marcado(s)` : `Liga inteira (${nv.times.length})`),
      el('button', { class: 'btn peq', disabled: !k, title: 'Cada time marcado entra como time avulso (escolha a liga do banco de cada um)', onclick: () => adicionarTimes([...S.marcados]) }, icone('mais', 12), k ? `${k} avulso(s)` : 'Avulsos'));
    }
    const todos = nv.times.filter((t) => !noProjeto.has(idDe(t)));
    acoes.append(el('button', { class: 'btn-fantasma peq', disabled: !todos.length, onclick: () => { if (S.marcados.size === todos.length) S.marcados = new Set(); else S.marcados = new Set(todos.map((t) => t.id)); desenharApi(); } }, S.marcados.size && S.marcados.size === todos.length ? 'Nenhum' : 'Todos'));
  };
  desenharAcoes();
  caixa.append(acoes);
  for (const t of nv.times) {
    const ja = noProjeto.has(idDe(t));
    const ch = el('input', { type: 'checkbox', title: ja ? 'Já está no projeto' : 'Marcar', disabled: ja });
    ch.checked = S.marcados.has(t.id);
    ch.onchange = () => { if (ch.checked) S.marcados.add(t.id); else S.marcados.delete(t.id); desenharAcoes(); };
    lista.append(el('label', { class: `it-api marcavel ${ja ? 'ja' : ''}`, title: `${t.nome} · ${t.estadio?.nome || ''}` },
      ch,
      el('img', { src: im(t.logo), alt: '', loading: 'lazy', onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
      el('span', { class: 'txt' }, el('b', {}, t.nome), el('small', {}, t.selecao ? 'seleção' : tm ? `clube · ID ${t.id} na Transfermarkt` : `${t.sigla || '—'} · ${t.fundacao || '?'} · ${t.estadio?.nome || 'sem estádio'}`)),
      ja ? el('span', { class: 'mudo', html: icone('check', 14) }) : el('button', { class: 'btn-icone peq', title: 'Pôr só este no projeto', onclick: (ev) => { ev.preventDefault(); adicionarTimes([t.id]); }, html: icone('mais', 14) })));
  }
}

async function adicionarLiga(l, temporada, ids) {
  const r = await tentar(() => api('adicionar_liga', { liga: l, temporada, ids }));
  if (!r) return;
  S.marcados = new Set();
  aplicar(r);
  S.aba = 'projeto';
  desenharAbas();
  desenharPrincipal();
  aviso(`${l.nome} ${l.temporada_nome || temporada || ''} no projeto`, { tipo: 'sucesso', detalhe: 'Agora colete os dados (botão Coletar no topo).' });
}
async function adicionarTimes(ids) {
  const nv = S.nav;
  const times = nv.times.filter((t) => ids.includes(t.id));
  const r = await tentar(() => api('adicionar_times', { times, liga: ligaComTemporada(), temporada: nv.temporada }));
  if (!r) return;
  S.marcados = new Set();
  aplicar(r);
  desenharApi();
  desenharPrincipal();
  aviso(`${r.adicionados} no projeto`, { tipo: 'sucesso', tempo: 2600, detalhe: r.repetidos?.length ? `Já estavam: ${r.repetidos.join(', ')}` : '' });
}

// ---------------------------------------------------------------- projeto (lista)
function desenharProjeto() {
  const p = $('#esq-projeto');
  p.innerHTML = '';
  const its = S.e.itens;
  if (!its.length) {
    p.append(el('div', { class: 'arvore-vazia' }, 'Projeto vazio. Na aba API, escolha uma competição e adicione a liga inteira, times avulsos ou seleções.'));
    return;
  }
  const lista = el('div', { class: 'arvore' });
  const mp = S.marcadosProj;
  for (const id of [...mp]) if (!its.some((x) => x.id === id)) mp.delete(id);
  if (mp.size) {
    lista.append(el('div', { class: 'barra-lote' }, el('span', {}, `${mp.size} marcado(s)`),
      el('span', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: () => { mp.clear(); desenharProjeto(); } }, 'Desmarcar'),
        el('button', { class: 'btn-perigo peq', onclick: () => removerVarios([...mp]) }, icone('apagar', 12), 'Tirar do projeto'))));
  }
  const marca = (i) => {
    const ch = el('input', { type: 'checkbox', class: 'marca-proj', title: 'Marcar para tirar vários do projeto de uma vez' });
    ch.checked = mp.has(i.id);
    ch.onclick = (ev) => ev.stopPropagation();
    ch.onchange = () => { if (ch.checked) mp.add(i.id); else mp.delete(i.id); desenharProjeto(); };
    return ch;
  };
  const linha = (i, filho = false) => el('div', { class: `it-proj marcavel ${filho ? 'filho' : ''} ${S.e.sel === i.id ? 'foco' : ''} ${mp.has(i.id) ? 'marcado' : ''}`, role: 'button', tabindex: 0, onclick: () => selecionar(i.id),
    oncontextmenu: (ev) => { ev.preventDefault(); menuItem(i, ev.clientX, ev.clientY); } },
  marca(i),
  i.tipo === 'liga' ? el('span', { html: icone('trofeu', 14) }) : el('span', { class: `est ${i.estado}`, title: { pendente: 'sem dados', coletando: 'coletando…', pronto: 'dados coletados', erro: i.erro || 'erro' }[i.estado] }),
  el('span', { class: 'txt' }, el('b', {}, i.nome, i.feminino ? el('span', { class: 'selo-f', title: 'Feminino' }, 'F') : null, i.selecao ? el('span', { class: 'selo-s', title: 'Seleção' }, 'SEL') : null,
    ehTm(i) ? el('span', { class: 'selo-tm', title: 'Dados da Transfermarkt' }, 'TM') : null),
    el('small', {}, i.tipo === 'liga'
      ? `${tempNome(i)} · ${i.prontos}/${i.times.length} times prontos · nível ${i.nivel ?? '—'}`
      : `${i.selecao ? 'convocação atual' : tempNome(i)} · ${i.estado === 'pronto' ? `${i.jogadores} jogadores` : i.estado === 'erro' ? 'erro' : `≈${pedidos(i, i.custo)}`} · nível ${i.nivel ?? '—'}`)),
  el('span', { class: 'mudo peq-txt' }, i.tipo === 'liga' ? (i.destino === 'nova' ? 'nova' : 'banco') : ''));
  for (const i of its.filter((x) => x.tipo === 'liga')) {
    lista.append(linha(i));
    for (const t of its.filter((x) => x.liga_item === i.id)) lista.append(linha(t, true));
  }
  const soltos = its.filter((x) => x.tipo === 'time' && !x.liga_item && !x.selecao);
  if (soltos.length) {
    lista.append(el('div', { class: 'painel-cab', style: { padding: '8px 10px 4px' } }, el('h2', {}, 'Times avulsos')));
    for (const t of soltos) lista.append(linha(t));
  }
  const sels = its.filter((x) => x.selecao);
  if (sels.length) {
    lista.append(el('div', { class: 'painel-cab', style: { padding: '8px 10px 4px' } }, el('h2', {}, 'Seleções')));
    for (const t of sels) lista.append(linha(t));
  }
  p.append(lista);
  const prontos = its.filter((x) => x.tipo === 'time' && x.estado === 'pronto').length;
  p.append(el('div', { class: 'painel-rodape' }, el('span', {}, `${prontos}/${its.filter((x) => x.tipo === 'time').length} com dados`)));
}

function menuItem(i, x, y) {
  abrirMenu([
    { cabecalho: i.nome },
    { rotulo: i.tipo === 'liga' ? 'Coletar os times da liga' : (i.estado === 'pronto' ? 'Coletar de novo' : 'Coletar'), icone: 'baixar', fn: () => coletar([i.id], i.estado === 'pronto') },
    { rotulo: 'Analisar as fotos', icone: 'rosto', desabilitado: !S.e.fotos_ok, fn: () => analisarFotos([i.id]) },
    '-',
    { rotulo: 'Tirar do projeto', icone: 'apagar', fn: () => remover(i) },
    S.marcadosProj.size ? { rotulo: `Tirar os ${S.marcadosProj.size} marcados`, icone: 'apagar', fn: () => removerVarios([...S.marcadosProj]) } : null,
  ].filter(Boolean), x, y);
}

async function selecionar(id) {
  aplicar(await tentar(() => api('selecionar', { id })));
  desenharPrincipal();
}
async function removerVarios(ids) {
  const its = S.e.itens.filter((x) => ids.includes(x.id));
  if (!its.length) return;
  const ligas = its.filter((x) => x.tipo === 'liga').length;
  if (!await confirmar(`Tirar ${its.length} item(ns) do projeto?`, `${its.slice(0, 8).map((x) => esc(x.nome)).join(', ')}${its.length > 8 ? '…' : ''}${ligas ? ' (as ligas levam os times delas)' : ''} saem do projeto. O que já foi baixado continua no cache.`, { rotulo: 'Tirar', perigo: true })) return;
  const r = await tentar(() => api('remover', { ids: its.map((x) => x.id) }));
  if (!r) return;
  S.marcadosProj.clear();
  aplicar(r);
  desenharPrincipal();
}
async function remover(i) {
  if (!await confirmar('Tirar do projeto?', `${esc(i.nome)}${i.tipo === 'liga' ? ' e os times dela' : ''} sai(em) do projeto. O que já foi baixado continua no cache.`, { rotulo: 'Tirar', perigo: true })) return;
  aplicar(await tentar(() => api('remover', { id: i.id })));
  desenharPrincipal();
}

// ---------------------------------------------------------------- centro
async function desenharPrincipal() {
  if (S.aba === 'atualizar') return desenharAtualizacao();
  const i = itemSel();
  if (!i) return telaInicial();
  if (i.tipo === 'liga') return desenharLiga(i);
  return desenharTime(i);
}

function telaInicial() {
  const p = $('#principal');
  p.innerHTML = '';
  const e = S.e;
  p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('escudo', 64) }), el('h2', {}, 'Criar ligas, times, seleções e jogadores'),
    el('p', {}, 'Escolha a fonte (API-Football ou Transfermarkt) e uma competição na aba API (à esquerda) e ponha no projeto a liga inteira, só os times marcados ou seleções. Coletar busca os dados (o que já foi baixado fica no cache e não gasta chamadas) e cada time mostra a prévia do elenco com as notas geradas — calibradas no banco importado no Super Tool. Atualizar banco confere os elencos e os participantes das ligas que já existem. Gerar grava um banco novo com tudo.'),
    e.motor && !e.motor.ok ? el('div', { class: 'aviso-motor', style: { border: 0 } }, nota(esc(e.motor.msg), 'alerta'),
      el('button', { class: 'btn-primario peq', onclick: () => instalarComponentes({ aoTerminar: async () => { await atualizar(); await recarregarInicio(); telaInicial(); } }) }, icone('baixar', 12), 'Baixar os componentes…')) : null,
    !e.banco ? nota('Importe o banco do jogo em <b>Dados do jogo</b> no Super Tool: as notas e os modelos de time vêm dele.', 'alerta') : null,
    fonteAtual() !== TM && !e.api.tem_chave ? nota('Falta a chave da API-Football (painel da direita) — ou troque a fonte para a Transfermarkt, que não precisa de chave.', 'alerta') : null,
    fonteAtual() === TM && !e.tm?.local_instalado && e.tm?.modo === 'publico' ? el('div', { class: 'col-gap', style: { alignItems: 'center' } }, nota('A Transfermarkt está pela instância pública: serve para testar, mas é lenta (≈1 pedido a cada 1,6 s) e às vezes recusa pedidos. Para usar de verdade, instale o servidor local (≈4 MB, roda no próprio computador).', 'info'),
      el('button', { class: 'btn-primario peq', onclick: instalarTm }, icone('baixar', 12), 'Instalar o servidor local…')) : null));
}

function desenharLiga(i) {
  const p = $('#principal');
  p.innerHTML = '';
  const times = S.e.itens.filter((x) => x.liga_item === i.id);
  const custo = times.reduce((s, t) => s + (t.estado === 'pronto' ? 0 : t.custo || 0), 0);
  const tm = ehTm(i);
  p.append(el('div', { class: 'cab-time' }, el('img', { class: 'escudo', src: im(i.api?.logo), alt: '' }),
    el('div', {}, el('h1', {}, i.nome, i.feminino ? el('span', { class: 'selo-f grande' }, 'Feminino') : null, tm ? el('span', { class: 'selo-tm grande' }, 'Transfermarkt') : null),
      el('div', { class: 'sub' }, `${i.api?.pais || ''} · temporada ${tempNome(i)} · ${times.length} times · ${i.destino === 'nova' ? 'vira uma liga nova no banco' : 'times entram numa liga do banco'}`))));
  p.append(el('div', { class: 'estatisticas', style: { margin: '6px 0 14px' } },
    ...(tm ? [[i.nivel ?? '—', 'nível da liga'], [`${i.prontos}/${times.length}`, 'times com dados'], [custo, 'pedidos para coletar o resto'], [MODO_TM[S.e.tm?.modo] || '—', 'Transfermarkt']]
      : [[i.nivel ?? '—', 'nível da liga'], [`${i.prontos}/${times.length}`, 'times com dados'], [custo, 'chamadas para coletar o resto'], [S.e.api.uso?.restantes ?? '—', 'chamadas restantes hoje']])
      .map(([v, k]) => el('div', { class: 'estatistica' }, el('b', {}, String(v)), el('span', {}, k)))));
  if (i.nivel_motivo) p.append(nota(tm ? `Nível: ${esc(i.nivel_motivo)}. Depois da coleta, cada time ganha o nível pelo valor de mercado do elenco e a liga fica com a média deles.` : `Nível sugerido: ${esc(i.nivel_motivo)}. É a média dos 14 jogadores mais fortes de um time típico da liga; ajuste no painel da direita.`, 'info'));
  if (tm && custo > 300 && S.e.tm?.modo === 'publico') p.append(nota(`Pela instância pública, ≈${custo} pedidos levam uns ${Math.ceil((custo * 1.7) / 60)} minutos. O servidor local (painel da direita) faz o mesmo bem mais rápido.`, 'alerta'));
  if (!tm && custo > (S.e.api.uso?.restantes ?? 100)) p.append(nota(`Coletar a liga inteira gasta ≈${custo} chamadas e restam ${S.e.api.uso?.restantes}. Colete aos poucos (dá para escolher os times) — o que já foi baixado não gasta de novo.`, 'alerta'));
  const tb = el('tbody');
  for (const t of times) {
    tb.append(el('tr', { onclick: () => selecionar(t.id), style: { cursor: 'pointer' } },
      el('td', {}, el('img', { src: im(t.api?.logo), alt: '' }), t.nome),
      el('td', {}, el('span', { class: `est ${t.estado}`, style: { display: 'inline-block', marginRight: '6px' } }), { pendente: 'sem dados', coletando: 'coletando…', pronto: `${t.jogadores} jogadores`, erro: 'erro' }[t.estado]),
      el('td', { class: 'num' }, t.posicao_tabela ? `${t.posicao_tabela}º` : '—'),
      el('td', { class: 'num' }, t.nivel ?? '—'),
      el('td', { class: 'num' }, t.estado === 'pronto' ? '0' : String(t.custo ?? '—')),
      el('td', {}, el('button', { class: 'btn-icone peq', title: t.estado === 'pronto' ? 'Coletar de novo' : 'Coletar só este', onclick: (ev) => { ev.stopPropagation(); coletar([t.id], t.estado === 'pronto'); }, html: icone('baixar', 13) }))));
  }
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Times'), el('p', { class: 'dica' }, 'Clique num time para ver o elenco gerado.')),
    el('button', { class: 'btn-primario peq', disabled: !custo || S.e.tarefa.ativa, onclick: () => coletar([i.id]) }, icone('baixar', 12), `Coletar os que faltam (≈${custo})`)),
  el('div', { class: 'cartao-corpo justo' }, el('table', { class: 'tabela times-liga' }, el('thead', {}, el('tr', {}, ...['Time', 'Dados', 'Tabela', 'Nível', tm ? 'Pedidos' : 'Chamadas', ''].map((h) => el('th', {}, h)))), tb))));
}

async function desenharTime(i) {
  const p = $('#principal');
  p.innerHTML = '';
  const tm = ehTm(i);
  const sub = i.selecao ? `${nomeNacao(i.nacao)} · convocação atual · nível ${i.nivel ?? '—'}` : `${i.api?.pais || ''} · ${tempNome(i)} · ${i.modo === 'atual' ? 'elenco atual' : `elenco da temporada ${tempNome(i)}`} · nível ${i.nivel ?? '—'}${i.nivel_manual ? ' (manual)' : ''}`;
  const cab = el('div', { class: 'cab-time' }, el('img', { class: 'escudo', src: im(i.api?.logo), alt: '' }),
    el('div', {}, el('h1', {}, i.nome, i.feminino ? el('span', { class: 'selo-f grande' }, 'Feminino') : null, i.selecao ? el('span', { class: 'selo-s grande' }, 'Seleção') : null,
      tm ? el('span', { class: 'selo-tm grande' }, 'Transfermarkt') : null), el('div', { class: 'sub' }, sub)));
  p.append(cab);
  if (i.estado !== 'pronto') {
    p.append(el('div', { class: 'tela-vazia', style: { minHeight: '40vh' } }, el('div', { class: 'ic-grande', html: icone('baixar', 48) }),
      el('h2', {}, i.estado === 'coletando' ? 'Coletando…' : i.estado === 'erro' ? 'A coleta falhou' : 'Ainda sem dados'),
      el('p', {}, i.estado === 'erro' ? i.erro
        : tm ? (i.selecao ? `Coletar busca na Transfermarkt o elenco atual da seleção e o técnico (≈${i.custo} pedido(s)); os jogadores são casados com os do banco pela data de nascimento.`
          : `Coletar busca na Transfermarkt o elenco, o valor de mercado e as posições de cada jogador, o técnico, o estádio e as cores do clube${i.escalacoes ? ` e os ${i.escalacoes} últimos jogos (formação e titulares)` : ''}: ≈${i.custo} pedido(s), sem limite diário.`)
          : i.selecao ? `Coletar busca a convocação atual e o técnico (≈${i.custo} chamada(s)); os jogadores são casados com os do banco.` : `Coletar busca o elenco, as estatísticas, o técnico e as últimas ${i.escalacoes} escalações (posições e cores dos uniformes): ≈${i.custo} chamada(s).`),
      el('div', { class: 'acoes' }, el('button', { class: 'btn-primario', disabled: S.e.tarefa.ativa, onclick: () => coletar([i.id], i.estado === 'erro') }, icone('baixar', 14), 'Coletar'))));
    return;
  }
  const corpo = el('div', { id: 'corpo-previa' }, el('div', { class: 'vazio' }, 'Gerando a prévia…'));
  p.append(corpo);
  const r = await tentar(() => api('previa?id=' + encodeURIComponent(i.id)));
  if (!r || S.e.sel !== i.id) { if (!r) corpo.innerHTML = ''; return; }
  if (r.menos11) {
    corpo.innerHTML = '';
    corpo.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Elenco com menos de 11'), el('p', { class: 'dica' }, r.menos11.msg))),
      el('div', { class: 'cartao-corpo col-gap' },
        el('div', { class: 'acoes-linha' },
          el('button', { class: 'btn-primario peq', title: 'Entram jogadores do Sem Contrato com nota e nacionalidade parecidas com as do elenco (primeiro o que falta para escalar 11: goleiro, defesa, meio e ataque)', onclick: async () => { await setItem(i, { menos11: 'livres' }); desenharPrincipal(); } }, icone('mais', 12), 'Completar com jogadores sem contrato'),
          el('button', { class: 'btn peq', title: 'As vagas que faltam ficam vazias na escalação', onclick: async () => { await setItem(i, { menos11: 'assim' }); desenharPrincipal(); } }, 'Criar assim mesmo')),
        nota('Criar com menos de 11 pode travar o jogo quando esse time entrar em campo; complete o elenco antes de jogar com ele.', 'alerta'))));
    return;
  }
  S.previa[i.id] = r.time;
  desenharPrevia(i, r.time, corpo);
}

const cor = (c) => el('i', { style: { background: `rgb(${c.join(',')})` } });
const swatchPele = (v, extra = {}) => el('span', { class: 'pele', title: `Tom de pele ${v}`, style: { background: PELE[v] || '#888' }, ...extra });

function cartaoTecnico(i, t) {
  const tc = t.tecnico || {};
  const ap = tc.aparencia || {};
  return el('div', { class: 'cartao mini' }, el('header', {}, el('div', {}, el('h3', {}, 'Técnico'), el('p', { class: 'dica' }, tc.mantido ? 'o mesmo do banco (mantido)' : tc.da_api ? `da ${curtaFonte(t)}` : 'do time-modelo')),
    el('button', { class: 'btn-icone peq', title: 'Editar o técnico', onclick: () => modalTecnico(i, t), html: icone('pincel', 14) })),
  el('div', { class: 'cartao-corpo pessoa' },
    tc.foto ? el('img', { class: 'foto', src: im(tc.foto), alt: '' }) : el('div', { class: 'foto vazia', html: icone('pessoa', 26) }),
    el('div', {}, el('b', {}, tc.nome || '—'), el('div', { class: 'mudo peq-txt' }, [tc.nacionalidade, tc.idade ? `${tc.idade} anos` : null, tc.genero ? 'mulher' : null].filter(Boolean).join(' · ')),
      el('div', { class: 'mudo peq-txt' }, ap.skintonecode ? swatchPele(+ap.skintonecode) : null, ` aparência: ${({ foto: 'pela foto', manual: 'manual', banco: 'técnico genérico do banco' })[tc.aparencia_origem] || '—'}`))));
}

function cartaoEstadio(i, t) {
  const e = t.estadio;
  if (!e) return null;
  return el('div', { class: 'cartao mini' }, el('header', {}, el('div', {}, el('h3', {}, 'Estádio'), el('p', { class: 'dica' }, 'sempre um genérico no jogo; o nome real vai em stadiumassignments'))),
    el('div', { class: 'cartao-corpo' }, el('dl', { class: 'kv' },
      el('dt', {}, 'Nome no jogo'), el('dd', {}, e.nome || '— (o do genérico)'),
      el('dt', {}, 'Capacidade'), el('dd', {}, `${fmt(e.capacidade)}${e.capacidade_real ? ' (real)' : ' (estimada pelo nível)'}`),
      el('dt', {}, 'Genérico'), el('dd', {}, `${(e.generico || '—').replace(/^_/, '')} · ${fmt(e.generico_capacidade)} lugares`))));
}

function cartaoTatica(i, t) {
  const tt = t.tatica || {};
  const fa = Object.entries(t.formacoes_api || {}).sort((a, b) => b[1] - a[1]).map(([f, n]) => `${f} ×${n}`).join(', ');
  return el('div', { class: 'cartao mini' }, el('header', {}, el('div', {}, el('h3', {}, 'Formação e tática'), el('p', { class: 'dica' }, fa ? `escalações da ${curtaFonte(t)}: ${fa}` : `sem escalações da ${curtaFonte(t)}`))),
    el('div', { class: 'cartao-corpo' }, el('dl', { class: 'kv' },
      el('dt', {}, 'Formação'), el('dd', {}, t.formacao || '—', tt.manual?.formacao ? ' (escolhida)' : ''),
      el('dt', {}, 'Linha defensiva'), el('dd', {}, `${PROF[tt.profundidade] || tt.profundidade}${tt.manual?.profundidade ? ' (escolhida)' : ' (automática)'}`),
      el('dt', {}, 'Saída de bola'), el('dd', {}, `${SAIDA[tt.saida] || tt.saida}${tt.manual?.saida ? ' (escolhida)' : ' (automática)'}`),
      el('dt', {}, 'Time-modelo'), el('dd', {}, `${t.modelo_nome} (${t.modelo})`))));
}

function desenharPrevia(i, t, corpo) {
  corpo.innerHTML = '';
  if (!t) { corpo.append(nota('Sem dados.', 'alerta')); return; }
  const tm = ehTm(t);
  const est = [[t.geral, 'geral do time (titulares)'], [t.jogadores.length, 'jogadores'], [t.formacao || '—', 'formação'], [t.nivel, 'nível usado'], [t.teamid, t.teamid_manual ? 'teamid (escolhido)' : (t.selecao && t.atualiza ? 'teamid (já existe)' : 'teamid')]];
  if (tm && t.nivel_valor) est.splice(4, 0, [t.nivel_valor, 'nível pelo valor de mercado']);
  if (tm && t.posse) est.splice(est.length - 1, 0, [`${Math.round(t.posse)}%`, 'posse média']);
  corpo.append(el('div', { class: 'estatisticas', style: { margin: '6px 0 12px' } },
    ...est.map(([v, k]) => el('div', { class: 'estatistica' }, el('b', {}, String(v)), el('span', {}, k)))));
  corpo.append(el('div', { class: 'cartoes-time' }, cartaoTecnico(i, t), cartaoTatica(i, t), cartaoEstadio(i, t),
    el('div', { class: 'cartao mini' }, el('header', {}, el('div', {}, el('h3', {}, 'Uniformes'), el('p', { class: 'dica' }, tm ? 'cores do clube na Transfermarkt' : 'cores das escalações da API'))),
      el('div', { class: 'cartao-corpo' }, el('span', { class: 'cores', title: 'casa · fora · goleiro' }, cor(t.cores.casa[0]), cor(t.cores.casa[1]), el('span', { style: { width: '8px' } }), cor(t.cores.fora[0]), cor(t.cores.fora[1]), el('span', { style: { width: '8px' } }), cor(t.cores.goleiro[0]))))));
  for (const a of t.avisos || []) corpo.append(nota(esc(a), 'alerta'));
  if (t.menos11) {
    corpo.append(el('div', { class: 'barra-banco' }, el('span', {}, t.menos11 === 'livres' ? `O elenco da fonte tinha menos de 11: ${t.livres} jogador(es) sem contrato completam o time (selo SEM CONTRATO).` : 'O elenco da fonte tem menos de 11 e será criado assim mesmo.'),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: async () => { await setItem(i, { menos11: t.menos11 === 'livres' ? 'assim' : 'livres' }); desenharPrincipal(); } }, t.menos11 === 'livres' ? 'Criar sem completar' : 'Completar com sem contrato'))));
  }
  if (t.selecao) return desenharPreviaSelecao(i, t, corpo);
  const aj = t.ajustes || {};
  const tb = el('tbody');
  const tit = new Set(t.jogadores.slice(0, 11).map((j) => j.api_id));
  const muda = (j, d) => ajustar(i.id, j.api_id, d);
  for (const j of t.jogadores) tb.append(linhaJogador(i, t, j, aj[String(j.api_id)] || {}, tit.has(j.api_id), muda));
  // tirados do elenco (não serão criados): o nome e o botão de pôr de volta
  const excl = t.excluidos?.length ? t.excluidos : Object.entries(aj).filter(([, v]) => v && v.excluir).map(([k]) => ({ api_id: k, nome: `Jogador ${k}` }));
  for (const x of excl) {
    tb.append(el('tr', { class: 'fora' }, el('td', {}, el('button', { class: 'btn-icone peq', title: 'Pôr de volta no elenco', onclick: () => ajustar(i.id, x.api_id, { excluir: false }), html: icone('restaurar', 12) })),
      el('td', {}), el('td', {}, x.foto ? el('img', { class: 'foto-j', src: im(x.foto), alt: '', loading: 'lazy' }) : null),
      el('td', { colspan: 16 }, el('s', {}, x.nome), el('span', { class: 'mudo peq-txt' }, ' — fora do elenco: não será criado'))));
  }
  const nAj = Object.keys(aj).filter((k) => !k.startsWith('_')).length;
  // jogadores que já estão no banco (mesmo nome e nascimento)
  const noBanco = t.jogadores.filter((j) => j.no_banco);
  const fortes = noBanco.filter((j) => j.no_banco.forte);
  const usando = t.jogadores.filter((j) => j.usar_db).length;
  const barraBanco = noBanco.length ? el('div', { class: 'barra-banco' },
    el('span', { html: icone('bancoDados', 14) }),
    el('span', {}, `${noBanco.length} jogador(es) deste elenco já estão no banco${fortes.length < noBanco.length ? ` (${fortes.length} com o mesmo nascimento)` : ''}. `,
      usando ? el('b', {}, `${usando} usado(s) do banco`) : 'Por enquanto todos serão criados de novo (cópias).',
      ...(t.clubes_afetados || []).filter((c) => c.ficam < 16).map((c) => el('span', { class: 'alerta-txt' },
        ` ${c.nome} (banco) fica com ${c.ficam} jogador(es)${c.ficam < 11 ? ' — menos de 11: ao Gerar, ele é completado com jogadores sem contrato' : ''}.`))),
    el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', disabled: !fortes.length || t.usar_db_todos, title: 'Os jogadores do banco vão para este time (saem do clube atual); nenhum é criado em dobro', onclick: () => ajustar(i.id, null, { _usar_db_todos: true }) }, icone('ligar', 12), 'Usar os do banco'),
      el('button', { class: 'btn-fantasma peq', disabled: !t.usar_db_todos && !usando, title: 'Cria todos de novo, com os dados da fonte', onclick: async () => { await ajustar(i.id, null, { _usar_db_todos: false }); for (const j of t.jogadores.filter((x) => (aj[String(x.api_id)] || {}).usar_db !== undefined)) await api('ajustar', { id: i.id, api_id: j.api_id, usar_db: null }); desenharPrincipal(); } }, icone('mais', 12), 'Criar todos novos'))) : null;
  corpo.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Elenco gerado'), el('p', { class: 'dica' }, 'Titulares marcados em azul (na ordem da formação). Tudo o que vai para o jogo se muda aqui; o nome abre a ficha com nomes, ID, posições, aparência e atributos. Valores mudados ficam em azul. O × no começo da linha tira o jogador do elenco (ele não é criado).')),
    el('div', { class: 'acoes-linha' }, S.e.fotos_ok ? el('button', { class: 'btn peq', title: 'Baixa as fotos (não gasta chamadas) e lê pele, cabelo e barba', onclick: () => analisarFotos([i.id]) }, icone('rosto', 12), i.fotos ? `Fotos analisadas (${i.fotos})` : 'Analisar as fotos') : null,
      el('button', { class: 'btn-fantasma peq', disabled: !nAj && !t.usar_db_todos, onclick: () => ajustar(i.id, null, { limpar: true }) }, icone('restaurar', 12), 'Voltar ao gerado'))),
  barraBanco,
  el('div', { class: 'cartao-corpo justo', style: { overflowX: 'auto' } }, el('table', { class: 'tabela elenco' },
    el('thead', {}, el('tr', {}, ...['', 'Nº', 'Foto', 'Jogador', 'Posição', 'Geral', 'Pot.', 'Nasc.', 'Nacion.', 'Alt.', 'Peso', 'Pé', 'PR', 'Dri', 'Pele', 'Min.', tm ? 'Valor' : 'Nota', 'Gols', ''].map((h) => el('th', { title: { PR: 'Perna ruim (1–5)', Dri: 'Dribles (1–5)', Pele: 'Aparência (tom de pele)', 'Pot.': 'Potencial', Valor: 'Valor de mercado na Transfermarkt (é dele que sai a nota)' }[h] || '' }, h)))), tb))));
}

function linhaJogador(i, t, j, a, titular, muda) {
  const num = (k, valor, min, max, larg, auto) => {
    const x = el('input', { class: `nota ${a[k] !== undefined && a[k] !== null ? 'ajustada' : ''}`, type: 'number', min, max, value: valor ?? '', style: { width: larg },
      title: auto !== undefined ? `Gerado: ${auto}. Apague para voltar ao gerado.` : '', onchange: (e) => muda(j, { [k]: e.target.value ? +e.target.value : null }) });
    return x;
  };
  const pos = el('select', { class: a.pos !== undefined ? 'ajustada' : '', onchange: (e) => muda(j, { pos: +e.target.value }) }, ...Object.entries(POS).map(([k, v]) => opt(k, v, j.pos)));
  const pe = el('select', { class: a.pe ? 'ajustada' : '', onchange: (e) => muda(j, { pe: +e.target.value }) }, opt(1, 'Dir.', j.pe), opt(2, 'Esq.', j.pe));
  const um5 = (k, v) => el('select', { class: a[k] ? 'ajustada' : '', onchange: (e) => muda(j, { [k]: +e.target.value }) }, ...[1, 2, 3, 4, 5].map((n) => opt(n, n, v)));
  const nasc = el('input', { type: 'date', class: `data ${a.nascimento ? 'ajustada' : ''}`, value: (j.nascimento || '').slice(0, 10), title: j.idade ? `${j.idade} anos` : '', onchange: (e) => muda(j, { nascimento: e.target.value || null }) });
  const nac = selectNacao(j.nacao, (v) => muda(j, { nacao: v || null }), a.nacao ? 'ajustada' : '');
  const ap = j.aparencia || {};
  const nb = j.no_banco;
  const livre = j.origem === 'livre';
  const seloBanco = livre ? el('span', { class: 'selo-db usa', title: `Jogador sem contrato do banco (ID ${j.playerid}) que completa o elenco: entra neste time e sai do Sem Contrato` }, 'SEM CONTRATO')
    : nb ? el('span', { class: `selo-db ${j.usar_db ? 'usa' : ''}`, title: `${j.usar_db ? 'Usando o jogador do banco' : 'Já existe no banco'}: ${nb.nome} · ${nb.clube_nome || (nb.idolo ? 'ídolo (Liga Clássica)' : 'sem clube')} · ID ${nb.playerid} · geral ${nb.overall}${nb.forte ? '' : ' (confira: nome ou nascimento não batem por completo)'}` }, j.usar_db ? 'DO BANCO' : 'NO BANCO') : null;
  const trocaBanco = nb && !nb.idolo && !livre ? el('button', { class: 'link-banco', title: j.usar_db ? 'Criar um jogador novo com os dados da fonte' : `Usar ${nb.nome} do banco (sai do ${nb.clube_nome || 'clube atual'} e vem para este time; nada é criado em dobro)`,
    onclick: (ev) => { ev.stopPropagation(); muda(j, { usar_db: !j.usar_db }); } }, j.usar_db ? 'criar novo' : 'usar o do banco') : null;
  const camisaInp = num('camisa', j.camisa, 1, 99, '44px');
  const linha = el('tr', { class: `${titular ? 'tit' : ''} ${j.usar_db ? 'usa-banco' : ''}` },
    el('td', {}, livre ? null : el('button', { class: 'btn-icone peq btn-tirar', title: 'Tirar do elenco (o jogador não é criado)', onclick: () => muda(j, { excluir: true }), html: icone('x', 12) })),
    el('td', {}, camisaInp),
    el('td', {}, j.foto ? el('img', { class: 'foto-j', src: im(j.foto), alt: '', loading: 'lazy', title: 'Abrir a ficha', onclick: () => modalJogador(i, t, j, a), onerror: (e) => { e.target.replaceWith(el('span', { class: 'foto-j vazia', html: icone('pessoa', 14) })); } })
      : el('span', { class: 'foto-j vazia', title: 'Sem foto na fonte', html: icone('pessoa', 14) })),
    el('td', { class: 'nome clicavel', title: 'Abrir a ficha (nomes, ID, posições, aparência e atributos)', onclick: () => modalJogador(i, t, j, a) },
      el('b', {}, j.nome, j.capitao || a.capitao ? el('span', { class: 'selo-c', title: 'Capitão' }, 'C') : null, seloBanco),
      el('small', {}, `${j.primeiro} ${j.sobrenome}`.trim() + ` · ID ${j.playerid}${j.playerid_manual ? ' (escolhido)' : ''}${j.usar_db ? ` · do ${j.clube || 'banco'}` : ''}` + (j.nome_api && j.nome_api !== j.nome ? ` · API: ${j.nome_api}` : ''), trocaBanco ? ' · ' : '', trocaBanco)),
    el('td', {}, pos, el('div', { class: 'origem-pos' }, j.pos_origem, j.posicoes2?.length ? ` · ${j.posicoes2.map((p) => POS[p]).join('/')}` : '')),
    el('td', {}, num('overall', j.overall, 40, 99, '52px', j.overall_auto)),
    el('td', {}, num('potencial', j.potential, 40, 99, '52px', j.potential_auto)),
    el('td', {}, nasc),
    el('td', {}, nac),
    el('td', {}, num('altura', j.altura, 150, 210, '54px')),
    el('td', {}, num('peso', j.peso, 45, 115, '50px')),
    el('td', {}, pe), el('td', {}, um5('perna_ruim', j.perna_ruim)), el('td', {}, um5('dribles', j.dribles)),
    el('td', { title: `Aparência: ${({ foto: 'pela foto', manual: 'manual', 'nação': 'jogador genérico da mesma nação' })[j.aparencia_origem] || '—'}` },
      swatchPele(+ap.skintonecode, { class: `pele ${j.aparencia_origem === 'foto' ? 'foto' : ''} ${a.aparencia ? 'ajustada' : ''}`, onclick: () => modalJogador(i, t, j, a) })),
    el('td', { class: 'num', title: `${j.jogos} jogos` }, ehTm(t) && !j.jogos ? '—' : fmt(j.minutos)),
    ehTm(t) ? el('td', { class: 'num valor' }, euros(j.valor)) : el('td', { class: 'num' }, j.nota_api ? j.nota_api.toFixed(2) : '—'),
    el('td', { class: 'num' }, ehTm(t) && !j.jogos ? '—' : j.gols),
    el('td', {}, el('button', { class: `btn-icone peq ${a.atr || a.nomes || a.playerid || a.posicoes2 ? 'ajustada' : ''}`, title: 'Ficha completa: nomes, ID, posições, aparência e atributos', onclick: () => modalJogador(i, t, j, a), html: icone('pincel', 13) })));
  if (j.usar_db) {                                       // jogador do banco: os dados dele não mudam (só o clube e o número)
    linha.querySelectorAll('input, select').forEach((x) => { if (x !== camisaInp) x.disabled = true; });
    linha.title = 'Jogador do banco: nota, posição, atributos e aparência continuam os dele; só muda o clube (e o número).';
  }
  return linha;
}

function selectNacao(valor, fn, classe = '') {
  const s = el('select', { class: `nacao ${classe}`, onchange: (e) => fn(e.target.value) }, opt('', '—', valor), ...S.nacoes.map((n) => opt(n.id, n.nome, valor)));
  return s;
}

function desenharPreviaSelecao(i, t, corpo) {
  const so = t.sel_opcoes || {};
  const grupos = el('div', { class: 'grupos-sel' }, ...Object.entries(t.grupos || {}).map(([g, v]) => el('span', { class: `grupo ${v.n < v.min ? 'baixo' : v.n > v.max ? 'alto' : 'ok'}`, title: `mínimo ${v.min}, máximo ${v.max}` }, el('b', {}, g), `${v.n}`, el('small', {}, ` ${v.min}–${v.max}`))));
  corpo.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, t.atualiza ? 'Seleção que já existe no banco: o elenco é substituído' : 'Seleção nova (entra na liga de seleções e no internationals.txt)'),
    el('p', { class: 'dica' }, `Convocados casados com o banco + os melhores da nação até o mínimo de cada posição (SQUAD_SELECTION${S.e.internationals ? ' do internationals importado' : ', padrão'}).`))),
  el('div', { class: 'cartao-corpo' }, grupos,
    interruptor({ titulo: 'Criar todos os convocados que não estão no banco', descricao: 'Entram sem clube (Sem Contrato), com nota estimada pela seleção. Dá para escolher um por um na lista abaixo.', marcado: so.criar_faltantes, aoMudar: (v) => selecao(i.id, { criar_faltantes: v }) }).el)));
  const ne = t.nao_encontrados || [];
  if (ne.length) {
    const nCriar = ne.filter((a) => a.criar).length;
    corpo.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, `Convocados que não achei no banco (${ne.length})`), el('p', { class: 'dica' }, `Marque quem criar (${nCriar} de ${ne.length}) ou escolha o jogador do banco que corresponde. Os desmarcados ficam fora da seleção.`)),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', disabled: nCriar === ne.length, onclick: () => selecao(i.id, { criar_faltantes: true }) }, 'Marcar todos'),
        el('button', { class: 'btn-fantasma peq', disabled: !nCriar, onclick: () => selecao(i.id, { criar_faltantes: false }) }, 'Nenhum'))),
    el('div', { class: 'cartao-corpo' }, ...ne.map((a) => {
      const ch = el('input', { type: 'checkbox', title: 'Criar este jogador (novo, sem clube)' });
      ch.checked = !!a.criar;
      ch.onchange = () => selecao(i.id, { criar_um: { api_id: a.id, criar: ch.checked } });
      return el('div', { class: 'linha-faltante' }, el('label', { class: 'faltante-criar' }, ch, el('span', {}, `${a.nome} · ${a.idade ?? '?'} anos · ${a.pos || '?'}`), el('small', { class: 'mudo' }, a.criar ? ' — será criado' : ' — fica fora')),
        el('button', { class: 'btn peq', onclick: () => escolherJogadorDb(i, t, { casar: a }) }, icone('busca', 12), 'Escolher no banco…'));
    }))));
  }
  const tb = el('tbody');
  const tit = new Set(t.jogadores.slice(0, 11).map((j) => j.playerid));
  for (const j of t.jogadores) {
    const chave = j.api_id;
    const fora = el('button', { class: 'btn-icone peq', title: 'Tirar da seleção', onclick: () => (j.existente ? selecao(i.id, { excluir: j.playerid }) : ajustar(i.id, chave, { excluir: true })), html: icone('x', 12) });
    const camisa = el('input', { class: 'nota', type: 'number', min: 1, max: 99, value: j.camisa, style: { width: '44px' }, onchange: (e) => ajustar(i.id, chave, { camisa: e.target.value ? +e.target.value : null }) });
    const cap = el('input', { type: 'radio', name: 'capitao', title: 'Capitão' });
    cap.checked = !!(t.ajustes?.[String(chave)]?.capitao);
    cap.onchange = () => ajustar(i.id, chave, { capitao: true });
    tb.append(el('tr', { class: tit.has(j.playerid) ? 'tit' : '' },
      el('td', {}, camisa),
      el('td', { class: 'nome' }, el('b', {}, j.nome), el('small', {}, `ID ${j.playerid} · ${j.existente ? (j.clube || 'sem clube') : `novo → ${j.clube || 'Passes Livres'}`}`)),
      el('td', {}, POS[j.pos] || j.pos), el('td', { class: 'num' }, el('span', { class: `ov ${classeOv(j.overall)}` }, j.overall)),
      el('td', { class: 'num' }, j.idade ?? '—'),
      el('td', {}, el('span', { class: `origem ${j.origem}` }, { convocado: 'convocado', completado: 'completado pelo banco', manual: 'escolhido', novo: 'novo (criado)' }[j.origem] || j.origem)),
      el('td', {}, cap), el('td', {}, fora)));
  }
  const excl = so.excluir_db || [];
  corpo.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, `Elenco da seleção (${t.jogadores.length})`), el('p', { class: 'dica' }, 'Titulares em azul. Mude o número, o capitão ou tire jogadores; os completados pelo banco são trocados pelo próximo melhor da posição.')),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => escolherJogadorDb(i, t, {}) }, icone('mais', 12), 'Pôr jogador do banco…'),
      excl.length ? el('button', { class: 'btn-fantasma peq', onclick: async () => { for (const pid of excl) await api('selecao', { id: i.id, voltar: pid }); desenharPrincipal(); } }, icone('restaurar', 12), `Devolver ${excl.length} tirado(s)`) : null)),
  el('div', { class: 'cartao-corpo justo', style: { overflowX: 'auto' } }, el('table', { class: 'tabela elenco' },
    el('thead', {}, el('tr', {}, ...['Nº', 'Jogador', 'Pos.', 'Geral', 'Idade', 'Origem', 'Cap.', ''].map((h) => el('th', {}, h)))), tb))));
}

async function escolherJogadorDb(i, t, { casar }) {
  const busca = el('input', { type: 'search', class: 'entrada', placeholder: 'Nome do jogador…', value: casar ? casar.nome.split(' ').slice(-1)[0] : '', autofocus: true, style: { width: '100%' } });
  const so = el('label', { class: 'peq-txt' }, el('input', { type: 'checkbox', checked: true }), ` só da nação (${nomeNacao(t.nacao)})`);
  const lista = el('div', { class: 'lista-busca' });
  let m;
  const buscar = async () => {
    const r = await tentar(() => api(`jogadores_db?q=${encodeURIComponent(busca.value)}&genero=${t.genero}${so.querySelector('input').checked ? `&nacao=${t.nacao}` : ''}`));
    lista.innerHTML = '';
    for (const j of r?.jogadores || []) {
      lista.append(el('button', { class: 'it-busca', onclick: async () => {
        m.fechar(true);
        if (casar) await selecao(i.id, { casar: { api_id: casar.id, playerid: j.playerid } });
        else await selecao(i.id, { incluir: j.playerid });
      } }, el('span', { class: `ov ${classeOv(j.overall)}` }, j.overall), el('b', {}, j.nome), el('span', { class: 'mudo' }, `${j.pos_nome} · ${j.clube || 'sem clube'} · ID ${j.playerid}`)));
    }
    if (!r?.jogadores?.length) lista.append(el('div', { class: 'vazio' }, 'Ninguém encontrado.'));
  };
  let tmr = null;
  busca.oninput = () => { clearTimeout(tmr); tmr = setTimeout(buscar, 250); };
  so.querySelector('input').onchange = buscar;
  m = modal({ titulo: casar ? `Quem é ${casar.nome}?` : 'Pôr jogador do banco na seleção', corpo: el('div', { class: 'col-gap' }, busca, so, lista), botoes: [{ rotulo: 'Fechar', valor: null }] });
  buscar();
}

async function modalJogador(i, t, j, a) {
  const novo = {};
  const campoT = (rot, k, valor, attrs = {}) => {
    const x = el('input', { type: 'text', class: 'entrada', value: valor ?? '', ...attrs });
    x.oninput = () => { novo[k] = x.value; };
    return el('div', { class: 'campo' }, el('label', {}, rot), x);
  };
  const [p0, s0, c0, cm0] = a.nomes || [j.primeiro, j.sobrenome, j.comum, j.camisa_nome];
  const nomes = { p: p0, s: s0, c: c0, cm: cm0 };
  const tNome = (rot, k) => { const x = el('input', { type: 'text', class: 'entrada', value: nomes[k] || '' }); x.oninput = () => { nomes[k] = x.value; novo._nomes = true; }; return el('div', { class: 'campo' }, el('label', {}, rot), x); };
  const id = el('input', { type: 'number', class: 'entrada mono', value: a.playerid || '', placeholder: String(j.playerid), style: { width: '130px' } });
  id.oninput = () => { novo.playerid = id.value ? +id.value : null; };
  const sec = new Set(j.posicoes2 || []);
  const chips = el('div', { class: 'chips' }, ...Object.entries(POS).filter(([k]) => +k !== j.pos).map(([k, v]) => {
    const c = el('button', { class: `chip clicavel ${sec.has(+k) ? 'ativo' : ''}` }, v);
    c.onclick = () => { if (sec.has(+k)) sec.delete(+k); else if (sec.size < 3) sec.add(+k); c.classList.toggle('ativo', sec.has(+k)); novo._pos2 = true; };
    return c;
  }));
  const cap = el('input', { type: 'checkbox' });
  cap.checked = !!a.capitao;
  cap.onchange = () => { novo.capitao = cap.checked; };
  // aparência
  const ap = { ...(j.aparencia || {}) };
  const apA = { ...(a.aparencia || {}) };
  const peles = el('div', { class: 'peles' }, ...Object.keys(PELE).map((v) => {
    const s = swatchPele(+v, { class: `pele grande ${+ap.skintonecode === +v ? 'sel' : ''}` });
    s.onclick = () => { apA.skintonecode = +v; peles.querySelectorAll('.pele').forEach((x) => x.classList.remove('sel')); s.classList.add('sel'); novo._ap = true; };
    return s;
  }));
  const cabelo = el('select', { class: 'seletor' }, ...[...new Set([+ap.haircolorcode, ...Object.keys(CABELO).map(Number)])].filter((x) => !Number.isNaN(x)).map((c) => opt(c, `${CABELO[c] || 'Cor'} (${c})`, ap.haircolorcode)));
  cabelo.onchange = () => { apA.haircolorcode = +cabelo.value; novo._ap = true; };
  const barba = el('select', { class: 'seletor' }, opt('igual', 'Como está', ''), opt('0', 'Sem barba', ''), opt('com', 'Com barba (a do doador ou da foto)', ''));
  barba.onchange = () => { if (barba.value === '0') apA.facialhairtypecode = 0; else delete apA.facialhairtypecode; novo._ap = true; };
  // atributos
  const atrA = { ...(a.atr || {}) };
  const grade = el('div', { class: 'grade-atr' });
  for (const [grupo, ks] of ATR) {
    grade.append(el('div', { class: 'grupo-atr' }, el('h4', {}, grupo), ...ks.filter((k) => k in (j.atr || {})).map((k) => {
      const x = el('input', { type: 'number', min: 1, max: 99, class: `nota ${k in atrA ? 'ajustada' : ''}`, value: j.atr[k] });
      x.onchange = () => { atrA[k] = x.value === '' ? '' : +x.value; x.classList.add('ajustada'); novo._atr = true; };
      return el('label', { class: 'linha-atr' }, el('span', {}, NOME_ATR[k] || k), x);
    })));
  }
  const corpoM = el('div', { class: 'ficha' },
    el('div', { class: 'ficha-topo' }, j.foto ? el('img', { class: 'foto', src: im(j.foto), alt: '' }) : null,
      el('div', { class: 'col-gap' }, el('div', { class: 'grade-2' }, tNome('Nome comum (o que o jogo mostra)', 'c'), tNome('Nome na camisa', 'cm'), tNome('Primeiro nome', 'p'), tNome('Sobrenome', 's')),
        el('div', { class: 'grade-2' }, el('div', { class: 'campo' }, el('label', {}, 'playerid (vazio = automático)'), id), el('label', { class: 'campo linha-cap' }, cap, ' Capitão')))),
    el('div', { class: 'campo' }, el('label', {}, `Posições secundárias (até 3) — principal: ${POS[j.pos]}`), chips),
    el('div', { class: 'grade-2' }, el('div', { class: 'campo' }, el('label', {}, `Tom de pele — ${({ foto: 'lido na foto', manual: 'manual', 'nação': 'do jogador genérico escolhido' })[j.aparencia_origem] || ''}`), peles),
      el('div', { class: 'col-gap' }, el('div', { class: 'campo' }, el('label', {}, 'Cor do cabelo (nome aproximado)'), cabelo), el('div', { class: 'campo' }, el('label', {}, 'Barba'), barba))),
    el('details', { class: 'secao', open: !!a.atr }, el('summary', { html: icone('seta', 12, 'seta') + 'Atributos (vazio = o gerado; a nota geral não é recalculada)' }), grade));
  const nb = j.no_banco;
  if (nb) {
    corpoM.prepend(nota(`${j.usar_db ? '<b>Usando o jogador do banco</b>' : '<b>Já existe no banco</b>'}: ${esc(nb.nome)} · ${esc(nb.clube_nome || (nb.idolo ? 'ídolo (Liga Clássica)' : 'sem clube'))} · ID ${nb.playerid} · geral ${nb.overall}${nb.forte ? ' (mesmo nascimento)' : ' — confira, o nascimento não bate ou falta'}.${j.usar_db ? ' Ele sai do clube atual e vem para este time; nota, atributos e aparência continuam os dele.' : ' Se for ele, use o do banco para não criar o mesmo jogador duas vezes.'}`, j.usar_db ? 'info' : 'alerta'));
  }
  const r = await modal({ titulo: j.nome, texto: `${POS[j.pos]} · ${j.overall} · ${j.idade ?? '?'} anos · ${j.nacionalidade || ''}`, largo: true, corpo: corpoM,
    botoes: [{ rotulo: 'Tirar do elenco', classe: 'btn-fantasma perigo', fn: () => 'tirar' },
      nb && !nb.idolo ? { rotulo: j.usar_db ? 'Criar um novo' : 'Usar o do banco', classe: 'btn-fantasma', fn: () => 'banco' } : null,
      { rotulo: 'Voltar ao gerado', classe: 'btn-fantasma', fn: () => 'limpar' }, { rotulo: 'Cancelar', valor: null }, { rotulo: 'Aplicar', classe: 'btn-primario', padrao: true, fn: () => 'ok' }].filter(Boolean) }).promessa;
  if (!r) return;
  if (r === 'tirar') return ajustar(i.id, j.api_id, { excluir: true });
  if (r === 'banco') return ajustar(i.id, j.api_id, { usar_db: !j.usar_db });
  if (r === 'limpar') {
    const vazio = Object.fromEntries(['overall', 'pos', 'pe', 'potencial', 'nomes', 'camisa', 'nascimento', 'nacao', 'altura', 'peso', 'perna_ruim', 'dribles', 'playerid', 'posicoes2', 'capitao'].map((k) => [k, null]));
    vazio.atr = Object.fromEntries(Object.keys(a.atr || {}).map((k) => [k, '']));
    vazio.aparencia = Object.fromEntries(Object.keys(a.aparencia || {}).map((k) => [k, '']));
    return ajustar(i.id, j.api_id, vazio);
  }
  const d = {};
  if (novo._nomes) d.nomes = [nomes.p || '', nomes.s || '', nomes.c || '', nomes.cm || ''];
  if ('playerid' in novo) d.playerid = novo.playerid;
  if (novo._pos2) d.posicoes2 = [...sec];
  if ('capitao' in novo) d.capitao = novo.capitao;
  if (novo._ap) d.aparencia = { ...Object.fromEntries(Object.keys(a.aparencia || {}).map((k) => [k, ''])), ...apA };
  if (novo._atr) d.atr = atrA;
  if (Object.keys(d).length) ajustar(i.id, j.api_id, d);
}

async function modalTecnico(i, t) {
  const tc = t.tecnico || {};
  const aj = { ...(i.tecnico || {}) };
  const tx = (rot, k, valor, tipo = 'text') => { const x = el('input', { type: tipo, class: 'entrada', value: valor ?? '' }); x.oninput = () => { aj[k] = x.value; }; return el('div', { class: 'campo' }, el('label', {}, rot), x); };
  const nac = selectNacao(aj.nacao || tc.nacao, (v) => { aj.nacao = v; });
  const gen = el('select', { class: 'seletor', onchange: (e) => { aj.genero = +e.target.value; } }, opt(0, 'Homem', aj.genero ?? tc.genero ?? 0), opt(1, 'Mulher', aj.genero ?? tc.genero ?? 0));
  const peles = el('div', { class: 'peles' }, ...Object.keys(PELE).map((v) => {
    const s = swatchPele(+v, { class: `pele grande ${+(aj.aparencia?.skintonecode ?? tc.aparencia?.skintonecode) === +v ? 'sel' : ''}` });
    s.onclick = () => { aj.aparencia = { ...(aj.aparencia || {}), skintonecode: +v }; peles.querySelectorAll('.pele').forEach((x) => x.classList.remove('sel')); s.classList.add('sel'); };
    return s;
  }));
  const r = await modal({ titulo: 'Técnico', texto: tc.da_api ? `Vindo da ${curtaFonte(t)}; o que você mudar aqui vale sobre ela.` : `A ${curtaFonte(t)} não tem o técnico deste time: preencha à mão.`,
    corpo: el('div', { class: 'col-gap' }, tc.foto ? el('img', { class: 'foto', src: im(tc.foto), alt: '', style: { width: '72px', borderRadius: '8px' } }) : null,
      el('div', { class: 'grade-2' }, tx('Nome comum', 'nome', aj.nome ?? tc.nome), tx('Primeiro nome', 'primeiro', aj.primeiro ?? tc.primeiro), tx('Sobrenome', 'sobrenome', aj.sobrenome ?? tc.sobrenome), tx('Nascimento', 'nascimento', (aj.nascimento ?? tc.nascimento ?? '').slice(0, 10), 'date')),
      el('div', { class: 'grade-2' }, el('div', { class: 'campo' }, el('label', {}, 'Nacionalidade'), nac), el('div', { class: 'campo' }, el('label', {}, 'Gênero'), gen)),
      el('div', { class: 'campo' }, el('label', {}, 'Tom de pele (vazio = o do técnico genérico ou o da foto)'), peles)),
    botoes: [{ rotulo: 'Voltar ao da API', classe: 'btn-fantasma', fn: () => 'limpar' }, { rotulo: 'Cancelar', valor: null }, { rotulo: 'Aplicar', classe: 'btn-primario', padrao: true, fn: () => 'ok' }] }).promessa;
  if (!r) return;
  const tecnico = r === 'limpar' ? Object.fromEntries(['nome', 'primeiro', 'sobrenome', 'nascimento', 'nacao', 'genero', 'aparencia'].map((k) => [k, ''])) : aj;
  await setItem(i, { tecnico });
}

async function ajustar(id, apiId, d) {
  const r = await tentar(() => api('ajustar', { id, api_id: apiId, ...d }));
  if (!r || S.e.sel !== id) return;
  S.previa[id] = r.time;
  const corpo = $('#corpo-previa');
  const i = itemSel();
  if (i && corpo) desenharPrevia(i, r.time, corpo);
}
async function selecao(id, d) {
  const r = await tentar(() => api('selecao', { id, ...d }));
  if (!r || S.e.sel !== id) return;
  const corpo = $('#corpo-previa');
  const i = itemSel();
  if (i && corpo) desenharPrevia(i, r.time, corpo);
}
async function setItem(i, d) {
  const r = await tentar(() => api('item', { id: i.id, ...d }));
  if (!r) return;
  aplicar(r);
  if (S.aba !== 'atualizar') desenharPrincipal();
}

// ---------------------------------------------------------------- atualizar banco
function abrirAtual(o) {
  Object.assign(S.atual, { sel: null, liga: null, lote: false, selecoes: null, sugestao: null, selLista: null }, o);
  desenharAtualizarEsq();
  desenharAtualizacao();
}
async function desenharAtualizarEsq() {
  const p = $('#esq-atualizar');
  p.innerHTML = '';
  if (!S.e.banco) { p.append(el('div', { class: 'arvore-vazia' }, nota('Importe o banco em Dados do jogo (Super Tool).', 'alerta'))); return; }
  const at = S.e.atualizacoes || [];
  const lista = el('div', { class: 'arvore' });
  if (at.length) {
    lista.append(el('div', { class: 'painel-cab cab-acao', style: { padding: '8px 10px 4px' } }, el('h2', {}, `Conferências (${at.length})`),
      el('button', { class: `btn-fantasma peq ${S.atual.lote ? 'ativo' : ''}`, title: 'Todas as conferências numa página: casamentos, conferir várias de uma vez', onclick: () => abrirAtual({ lote: true }) }, icone('lista', 12), 'Ver todas')));
    for (const a of at) {
      lista.append(el('button', { class: `it-proj ${S.atual.sel === a.id ? 'foco' : ''}`, onclick: () => abrirAtual({ sel: a.id }),
        oncontextmenu: (ev) => { ev.preventDefault(); abrirMenu([{ cabecalho: a.liga_nome }, { rotulo: 'Tirar', icone: 'apagar', fn: async () => { aplicar(await tentar(() => api('atualizar_remover', { id: a.id }))); if (S.atual.sel === a.id) S.atual.sel = null; desenharAtualizacao(); } }], ev.clientX, ev.clientY); } },
      el('span', { html: icone('recarregar', 14) }), el('span', { class: 'txt' }, el('b', {}, `${a.liga_nome}`, ehTm(a) ? el('span', { class: 'selo-tm', title: 'Transfermarkt' }, 'TM') : null),
        el('small', {}, `× ${a.liga_api_nome} ${a.temporada_nome || a.temporada || 'atual'} · ${a.conferido ? `${a.marcadas}/${a.n} mudanças marcadas` : 'não conferida'}`)), el('span', {})));
    }
  }
  if (!S.atual.ligas) {
    lista.append(el('div', { class: 'arvore-vazia' }, 'Carregando…'));
    p.append(lista);
    const r = await tentar(() => api('atualizar_ligas'));
    S.atual.ligas = r?.ligas || [];
    S.atual.ligasSel = r?.selecoes || [];
    return desenharAtualizarEsq();
  }
  // ligas de seleções: atualizam as seleções do banco (convocação, escalação, técnico) pondo-as no projeto
  if (S.atual.ligasSel.length) {
    lista.append(el('div', { class: 'painel-cab', style: { padding: '10px 10px 4px' } }, el('h2', {}, 'Seleções')));
    for (const l of S.atual.ligasSel) {
      lista.append(el('button', { class: `it-api ${S.atual.selecoes?.leagueid === l.leagueid ? 'foco' : ''}`, onclick: () => abrirAtual({ selecoes: l, selMarcadas: new Set() }) },
        el('span', { html: icone('mundo', 14) }), el('span', { class: 'txt' }, el('b', {}, l.nome), el('small', {}, `${l.times} seleções ${l.feminina ? 'femininas' : 'masculinas'} no banco`)), el('span', {})));
    }
  }
  const mc = S.atual.marcadas;
  lista.append(el('div', { class: 'painel-cab cab-acao', style: { padding: '10px 10px 4px' } }, el('h2', {}, 'Ligas do banco'),
    mc.size ? el('button', { class: 'btn-fantasma peq', onclick: () => { mc.clear(); desenharAtualizarEsq(); } }, 'Desmarcar') : null));
  if (mc.size) {
    lista.append(el('div', { class: 'barra-lote' }, el('span', {}, `${mc.size} liga(s) marcada(s)`),
      el('button', { class: 'btn-primario peq', disabled: S.e.tarefa.ativa, title: `Cada liga é casada com a liga de mesmo país e divisão na ${fonteAtual() === TM ? 'Transfermarkt' : 'API-Football'}, na temporada mais recente ${fonteAtual() === TM ? '' : 'que o plano libera '}(${fonteAtual() === TM ? '1 pedido' : '1 chamada'} por liga)`,
        onclick: async () => { aplicar(await tentar(() => api('atualizar_preparar_varias', { leagueids: [...mc], fonte: fonteAtual() }))); } }, icone('ligar', 12), 'Casar todas')));
  }
  const busca = el('input', { type: 'search', placeholder: 'Buscar liga ou país…', value: S.atual.busca, spellcheck: 'false' });
  const itens = el('div');
  const desenhar = () => {
    itens.innerHTML = '';
    const q = busca.value.trim().toLowerCase();
    let pais = null;
    for (const l of S.atual.ligas.filter((x) => !q || `${x.nome} ${x.pais_en}`.toLowerCase().includes(q))) {
      if (l.pais_en !== pais) { pais = l.pais_en; itens.append(el('div', { class: 'grupo-pais' }, pais || '—')); }
      const ch = el('input', { type: 'checkbox', title: 'Marcar para casar várias ligas de uma vez' });
      ch.checked = mc.has(l.leagueid);
      ch.onclick = (ev) => ev.stopPropagation();
      ch.onchange = () => { if (ch.checked) mc.add(l.leagueid); else mc.delete(l.leagueid); desenharAtualizarEsq(); };
      itens.append(el('div', { class: `it-api marcavel ${S.atual.liga?.leagueid === l.leagueid ? 'foco' : ''}`, onclick: () => abrirAtual({ liga: l }) },
        ch, el('span', { class: 'txt' }, el('b', {}, l.nome), el('small', {}, `${l.divisao}ª divisão · ${l.times} times · nível ${l.nivel ?? '—'}${l.feminina ? ' · feminina' : ''}`)), el('span', {})));
    }
  };
  busca.oninput = () => { S.atual.busca = busca.value; desenhar(); };
  desenhar();
  p.append(el('div', { class: 'busca-linha' }, el('label', { class: 'campo-busca' }, el('span', { html: icone('busca', 14) }), busca)), lista);
  lista.append(itens);
}

async function desenharAtualizacao() {
  const p = $('#principal');
  p.innerHTML = '';
  if (S.atual.sel) return desenharConferencia(S.atual.sel);
  if (S.atual.lote) return desenharLote();
  if (S.atual.selecoes) return desenharSelecoesAtual();
  const l = S.atual.liga;
  if (!l) {
    const tm0 = fonteAtual() === TM;
    p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('recarregar', 60) }), el('h2', {}, `Atualizar o banco pela ${tm0 ? 'Transfermarkt' : 'API-Football'}`),
      el('p', {}, 'Escolha uma liga do banco (à esquerda) — ou marque várias e clique Casar todas. O Criador casa os times dela com os da liga correspondente na fonte escolhida e confere: quem subiu ou caiu (participantes; sem divisão abaixo no banco, o time vai para o Resto do Mundo), transferências, empréstimos, quem saiu, números de camisa e, se quiser, um ajuste pequeno de nota. As ligas de seleções atualizam a convocação, a escalação e o técnico das seleções. Nada muda no banco até Gerar; cada mudança pode ser desmarcada.'),
      seletorFonte(),
      nota(tm0 ? 'Transfermarkt: sem limite diário e com a temporada de agora. 1 pedido para a lista de times; conferir gasta 1 por time, mais o histórico de quem mudou de time e, para as notas, o perfil de cada jogador (valor de mercado).'
        : 'Custo: 1 chamada para a lista de times da liga; conferir os elencos gasta 1 por time (+1 por time para os empréstimos e até 3 por time para as notas).', 'info')));
    return;
  }
  const f = fonteAtual();
  const tm = f === TM;
  p.append(el('div', { class: 'cab-time' }, el('div', { class: 'ic-c', html: icone('trofeu', 40) }), el('div', {}, el('h1', {}, l.nome), el('div', { class: 'sub' }, `${l.pais_en || ''} · ${l.divisao}ª divisão · ${l.times} times no banco`))));
  if (l.sem_pais) {
    p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Liga sem país: casar os times um a um'), el('p', { class: 'dica' }, `Não há uma liga correspondente na fonte: cada time do banco é procurado sozinho na ${tm ? 'Transfermarkt' : 'API-Football'} pelo nome e pela nação dele (${l.times} ${tm ? 'pedidos' : 'chamadas'}; o que já foi casado antes vem do mapa). Depois, confira os pares e confira os elencos como numa liga normal — sem a lista de participantes.`)), seletorFonte()),
      el('div', { class: 'cartao-corpo' }, el('button', { class: 'btn-primario peq', disabled: S.e.tarefa.ativa, onclick: async () => { aplicar(await tentar(() => api('atualizar_preparar_varias', { leagueids: [l.leagueid], fonte: f }))); } }, icone('ligar', 12), `Casar os ${l.times} times`))));
    return;
  }
  const caixa = el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, `Liga correspondente na ${tm ? 'Transfermarkt' : 'API-Football'}`), el('p', { class: 'dica' }, 'A de mesma divisão do país vem primeiro.')), seletorFonte()));
  const corpo = el('div', { class: 'cartao-corpo col-gap' }, el('div', { class: 'vazio' }, 'Buscando as ligas do país…'));
  caixa.append(corpo);
  p.append(caixa);
  if (!S.atual.sugestao || S.atual.sugestao.liga.leagueid !== l.leagueid || (S.atual.sugestao.fonte || 'apifootball') !== f) {
    const r = await tentar(() => api(`atualizar_sugestao?leagueid=${l.leagueid}${tm ? '&fonte=transfermarkt' : ''}`));
    if (S.atual.liga !== l || fonteAtual() !== f) return;
    if (!r) { corpo.innerHTML = ''; return; }
    S.atual.sugestao = { ...r, fonte: f };
  }
  const sg = S.atual.sugestao;
  corpo.innerHTML = '';
  if (tm) return correspondenteTm(l, sg, corpo);
  const selL = el('select', { class: 'seletor' }, ...sg.ligas.map((x) => opt(x.id, `${x.nome} (${x.temporadas[0]}–${x.atual})`, sg.ligas[0]?.id)));
  const livre = temporadasLiberadas();
  const temporadas = () => { const x = sg.ligas.find((y) => String(y.id) === selL.value); return x ? [...x.temporadas].reverse() : []; };
  const selT = el('select', { class: 'seletor' });
  const encher = () => { selT.innerHTML = ''; const ts = temporadas(); const ok = ts.filter(livre); for (const a of ts) selT.append(opt(a, `${a}${livre(a) ? '' : ' (plano pago)'}`, ok[0] ?? ts[0])); };
  selL.onchange = encher;
  encher();
  corpo.append(el('div', { class: 'grade-2' }, el('div', { class: 'campo' }, el('label', {}, `Liga na API (${sg.pais})`), selL), el('div', { class: 'campo' }, el('label', {}, 'Temporada'), selT)),
    nota('Para conferir a temporada de agora (promovidos e elencos atuais) é preciso o plano pago; no grátis, as temporadas liberadas servem para atualizar um banco mais antigo.', 'info'),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', disabled: !sg.ligas.length, onclick: async () => {
      const r = await tentar(() => api('atualizar_preparar', { leagueid: l.leagueid, liga_api: +selL.value, temporada: +selT.value }));
      if (!r) return;
      aplicar(r);
      S.atual.sel = r.atualizacao.id;
      desenharAtualizarEsq();
      desenharAtualizacao();
    } }, icone('ligar', 12), 'Casar os times (1 chamada)')));
}

function correspondenteTm(l, sg, corpo) {
  const porId = new Map(sg.ligas.map((x) => [String(x.id), x]));
  const selL = el('select', { class: 'seletor' });
  const encherLigas = (ls) => { selL.innerHTML = ''; for (const x of ls) selL.append(opt(x.id, `${x.nome}${x.pais && x.pais !== sg.pais ? ` (${x.pais})` : ''}${x.valor ? ` · ${euros(x.valor)}` : ''}`, ls[0]?.id)); };
  encherLigas(sg.ligas);
  const selT = el('select', { class: 'seletor' });
  const btn = el('button', { class: 'btn-primario peq' }, icone('ligar', 12), 'Casar os times (1 pedido)');
  const encherTemporadas = async () => {
    selT.innerHTML = '';
    selT.append(opt('', 'carregando…', ''));
    selT.disabled = true;
    btn.disabled = true;
    if (!selL.value) { selT.innerHTML = ''; return; }
    const r = await tentar(() => api('temporadas?liga=' + encodeURIComponent(selL.value)));
    selT.innerHTML = '';
    const ts = r?.temporadas || [];
    ts.forEach((s, k) => selT.append(opt(s.id, `${s.nome}${k === 0 ? ' · atual' : ''}`, ts[0].id)));
    if (!ts.length) selT.append(opt('', 'atual', ''));
    selT.disabled = false;
    btn.disabled = !selL.value;
  };
  selL.onchange = encherTemporadas;
  encherTemporadas();
  const busca = el('input', { type: 'search', class: 'entrada', placeholder: 'Outra competição: nome e Enter', spellcheck: 'false' });
  busca.onkeydown = async (e) => {
    if (e.key !== 'Enter' || busca.value.trim().length < 3) return;
    e.preventDefault();
    const r = await tentar(() => api('buscar_ligas?q=' + encodeURIComponent(busca.value.trim())));
    const ls = (r?.ligas || []).filter((x) => x.tipo === 'League');
    if (!ls.length) { aviso('Nenhuma liga com esse nome na Transfermarkt', { tipo: 'aviso' }); return; }
    ls.forEach((x) => porId.set(String(x.id), x));
    encherLigas(ls);
    encherTemporadas();
  };
  btn.onclick = async () => {
    const lg = porId.get(selL.value);
    const tn = selT.selectedOptions[0]?.textContent.replace(' · atual', '') || null;
    const r = await tentar(() => api('atualizar_preparar', { fonte: TM, leagueid: l.leagueid, liga_api: selL.value, temporada: selT.value || null, temporada_nome: tn,
      liga_nome: lg?.nome || selL.value, pais: lg?.pais && lg.pais !== 'Internacional' ? lg.pais : sg.pais }));
    if (!r) return;
    aplicar(r);
    S.atual.sel = r.atualizacao.id;
    desenharAtualizarEsq();
    desenharAtualizacao();
  };
  corpo.append(el('div', { class: 'grade-2' }, el('div', { class: 'campo' }, el('label', {}, `Liga na Transfermarkt (${sg.pais})`), selL), el('div', { class: 'campo' }, el('label', {}, 'Temporada'), selT)),
    el('div', { class: 'campo' }, el('label', {}, 'Não é nenhuma dessas?'), busca),
    nota('A Transfermarkt libera a temporada de agora: promovidos, elencos de hoje (com data de nascimento, o que deixa o casamento dos jogadores exato) e transferências. Ela não tem futebol feminino.', 'info'),
    el('div', { class: 'acoes-linha' }, btn));
}

async function desenharConferencia(id) {
  const p = $('#principal');
  const r = await tentar(() => api('atualizacao?id=' + encodeURIComponent(id)));
  if (!r) return;
  const a = r.atualizacao;
  p.innerHTML = '';
  const tm = ehTm(a);
  p.append(el('div', { class: 'cab-time' }, el('img', { class: 'escudo', src: im(a.liga_api_info?.logo), alt: '' }),
    el('div', {}, el('h1', {}, a.liga_nome, tm ? el('span', { class: 'selo-tm grande' }, 'Transfermarkt') : null),
      el('div', { class: 'sub' }, `× ${a.liga_api_nome} ${a.temporada_nome || a.temporada || 'atual'} (${tm ? 'Transfermarkt' : 'API'}) · ${a.pares.length} pares · ${a.sem_par.length} sem par no banco · ${a.fora.length} do banco fora da lista`))));
  // pares
  const op = { participantes: true, elencos: true, emprestimos: true, numeros: true, saidas: true, destino_saidas: true, notas: false, criar: false, tatica: false, tecnicos: false, delta_max: 2, delta_min: 3, ...(a.opcoes || {}) };
  const btn = el('button', { class: 'btn-primario peq' });
  // Transfermarkt: elenco (1) + histórico de quem mudou (≈3) + perfil de cada jogador para as notas (≈28)
  const custo = () => (op.elencos ? S.atual.times.size * (tm ? 1 + (op.emprestimos ? 3 : 0) + (op.notas ? 28 : 0) + (op.saidas && op.destino_saidas ? 3 : 0) + (op.tatica ? 6 : 0) + (op.tecnicos ? 2 : 0)
    : 1 + (op.emprestimos || (op.saidas && op.destino_saidas) ? 1 : 0) + (op.notas ? 3 : 0) + (op.tatica ? 4 : 0) + (op.tecnicos ? 1 : 0)) : 0);
  const rotBtn = () => { btn.innerHTML = icone('baixar', 12) + ` Conferir (≈${custo()} ${tm ? 'pedidos' : 'chamadas'})`; btn.disabled = S.e.tarefa.ativa; };
  const tb = el('tbody');
  if (!S.atual.times || S.atual.timesDe !== a.id) { S.atual.times = new Set(a.opcoes?.times || a.pares.map((x) => x.api_id)); S.atual.timesDe = a.id; }
  const sincronizar = () => { rotBtn(); };
  for (const pr of [...a.pares].sort((x, y) => x.nota - y.nota)) {
    const ch = el('input', { type: 'checkbox', title: tm ? 'Conferir o elenco deste time' : 'Conferir o elenco deste time (1 chamada; +1 com empréstimos)' });
    ch.checked = S.atual.times.has(pr.api_id);
    ch.onchange = () => { if (ch.checked) S.atual.times.add(pr.api_id); else S.atual.times.delete(pr.api_id); sincronizar(); };
    tb.append(el('tr', {}, el('td', {}, ch), el('td', {}, el('img', { src: im(pr.api_logo), alt: '' }), pr.api_nome),
      el('td', {}, pr.nome_db, el('div', { class: 'mudo peq-txt' }, `${pr.liga_db_nome} · teamid ${pr.teamid}`)),
      el('td', { class: 'num' }, pr.origem === 'manual' ? 'manual' : pr.origem === 'mapa' ? 'mapa' : pr.origem === 'elenco' ? el('span', { title: 'Dois times do banco tinham nome parecido: decidido pelos jogadores em comum no elenco' }, `${Math.round(pr.nota * 100)}% · elenco`) : `${Math.round(pr.nota * 100)}%`),
      el('td', {}, el('button', { class: 'btn-icone peq', title: 'Trocar o time do banco', onclick: () => trocarPar(a, pr.api_id, pr.api_nome), html: icone('pincel', 12) }))));
  }
  for (const t of a.sem_par) {
    tb.append(el('tr', { class: 'sem-par' }, el('td', {}), el('td', {}, el('img', { src: im(t.logo), alt: '' }), t.nome), el('td', { class: 'mudo' }, 'não está no banco'), el('td', {}, '—'),
      el('td', {}, el('button', { class: 'btn-icone peq', title: 'Escolher o time do banco', onclick: () => trocarPar(a, t.id, t.nome), html: icone('ligar', 12) }))));
  }
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Times casados'), el('p', { class: 'dica' }, 'Os menos parecidos primeiro: confira e troque se precisar (a troca fica guardada no mapa e vale nas próximas vezes).')),
    a.sem_par.length ? el('button', { class: 'btn peq', onclick: async () => { const x = await tentar(() => api('atualizar_criar', { id: a.id })); if (x) { aplicar(x); aviso(`${x.adicionados} time(s) no projeto`, { tipo: 'sucesso', detalhe: 'Eles entram nesta liga do banco. Colete os dados na aba Projeto.' }); } } }, icone('mais', 12), `Criar os ${a.sem_par.length} que faltam`) : null),
  el('div', { class: 'cartao-corpo justo' }, el('table', { class: 'tabela times-liga' }, el('thead', {}, el('tr', {}, ...['Elenco', tm ? 'Transfermarkt' : 'API', 'Banco', 'Casamento', ''].map((h) => el('th', {}, h)))), tb))));
  // opções e conferir
  const ints = tm
    ? [['participantes', 'Participantes da liga', 'Quem subiu/caiu (mudam de liga no banco).'], ['elencos', 'Elencos atuais', '1 pedido por time; o casamento usa a data de nascimento.'],
      ['emprestimos', 'Transferências e empréstimos', 'Histórico de quem mudou de time (1 pedido por jogador): dono, fim do empréstimo e volta.'], ['numeros', 'Números de camisa', ''],
      ['saidas', 'Saídas', 'Quem não está mais no elenco sai do time.'],
      ['destino_saidas', 'Saídas para o clube novo', 'Cada um que saiu é procurado na Transfermarkt (1 pedido por jogador): se o clube de hoje está no banco, ele vai para lá; senão (ou aposentado), Sem Contrato.'],
      ['notas', 'Notas pelo valor de mercado', 'Perfil de cada jogador (1 pedido): só muda quando a nota estimada fica 3 ou mais longe da do banco, ±2 no máximo.'],
      ['criar', 'Criar os jogadores que faltam', 'Com nota pelo valor de mercado e a posição e o pé da Transfermarkt.'],
      ['tatica', 'Formação e tática', 'A formação mais usada nos últimos 5 jogos (≈6 pedidos por time) e a linha defensiva e a saída de bola pela posição na tabela, como nos times criados.'],
      ['tecnicos', 'Técnicos', 'O técnico de hoje de cada clube (2 pedidos por time). Se ele já está no banco, fica com a cara dele.']]
    : [['participantes', 'Participantes da liga', 'Quem subiu/caiu (mudam de liga no banco).'], ['elencos', 'Elencos atuais', '1 chamada por time.'],
      ['emprestimos', 'Empréstimos', '+1 chamada por time (transferências).'], ['numeros', 'Números de camisa', ''], ['saidas', 'Saídas', 'Quem não está mais no elenco sai do time.'],
      ['destino_saidas', 'Saídas para o clube novo', 'Pelas transferências do time (+1 chamada por time, a mesma dos empréstimos): se o clube novo está no banco, ele vai para lá; senão, Sem Contrato.'],
      ['notas', 'Notas pelo desempenho recente', `±2 no máximo, pela nota da API na última temporada liberada (até 3 chamadas por time).`], ['criar', 'Criar os jogadores que faltam', 'Com nota estimada pelo nível do time.'],
      ['tatica', 'Formação e tática', 'A formação mais usada nas 3 últimas escalações (≈4 chamadas por time) e a linha defensiva e a saída de bola pela posição na tabela.'],
      ['tecnicos', 'Técnicos', 'O técnico atual de cada time (1 chamada por time). Se ele já está no banco, fica com a cara dele.']];
  rotBtn();
  btn.onclick = async () => { aplicar(await tentar(() => api('atualizar_conferir', { id: a.id, ...op, times: [...S.atual.times] }))); };
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'O que conferir'), el('p', { class: 'dica' }, a.conferido ? `Última conferência: ${a.conferido}` : 'Ainda não conferida.')), btn),
    el('div', { class: 'cartao-corpo grade-2' }, ...ints.map(([k, t, d]) => interruptor({ titulo: t, descricao: d, marcado: op[k], aoMudar: (v) => { op[k] = v; rotBtn(); } }).el)),
    camposDelta(op, tm)));
  if (a.individual) p.append(nota(`Liga sem país: cada time do banco foi procurado sozinho na ${tm ? 'Transfermarkt' : 'API-Football'} (sem lista de participantes).${(a.nao_casados || []).length ? ` Não achei: ${a.nao_casados.map((x) => esc(x.nome)).join(', ')}.` : ''}`, 'info'));
  // mudanças
  if (!a.mudancas.length) { if (a.conferido) p.append(nota(`Nenhuma mudança: o banco já está igual à ${tm ? 'Transfermarkt' : 'API'}.`, 'info')); return; }
  const tipos = { liga: 'Participantes', transferencia: 'Transferências', emprestimo: 'Empréstimos', fim_emprestimo: 'Fim de empréstimo', saida: 'Saídas', numero: 'Números', nota: 'Notas', novo: 'Novos', tatica: 'Tática', tecnico: 'Técnicos' };
  const cont = {};
  a.mudancas.forEach((m) => { cont[m.tipo] = (cont[m.tipo] || 0) + 1; });
  const filtros = el('div', { class: 'segmentado' }, el('button', { class: S.atual.filtro === 'todas' ? 'ativo' : '', onclick: () => { S.atual.filtro = 'todas'; desenharConferencia(id); } }, `Todas (${a.mudancas.length})`),
    ...Object.entries(cont).map(([k, n]) => el('button', { class: S.atual.filtro === k ? 'ativo' : '', onclick: () => { S.atual.filtro = k; desenharConferencia(id); } }, `${tipos[k] || k} (${n})`)));
  const lst = el('div', { class: 'lista-mudancas' });
  a.mudancas.forEach((m, n) => {
    if (S.atual.filtro !== 'todas' && m.tipo !== S.atual.filtro) return;
    const ch = el('input', { type: 'checkbox' });
    ch.checked = !!m.aplicar;
    ch.onchange = async () => { const x = await tentar(() => api('atualizar_marcar', { id: a.id, indices: [n], aplicar: ch.checked })); if (x) aplicar(x); };
    lst.append(el('label', { class: `mudanca ${m.tipo} ${m.aplicar ? '' : 'desmarcada'}` }, ch, el('span', { class: 'tipo' }, tipos[m.tipo] || m.tipo),
      el('span', {}, m.descricao, m.tipo === 'tatica' ? editorTatica(a, n, m) : null)));
  });
  for (const av of a.avisos || []) p.append(nota(esc(av), 'alerta'));
  const marcarTodas = async (v) => { const x = await tentar(() => api('atualizar_marcar', { id: a.id, aplicar: v, ...(S.atual.filtro !== 'todas' ? { tipo: S.atual.filtro, indices: [] } : {}) })); if (x) { aplicar(x); desenharConferencia(id); } };
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Mudanças'), el('p', { class: 'dica' }, 'Marcadas entram no banco ao Gerar (junto com o que estiver no projeto). Times que perdem ou ganham jogadores têm a escalação padrão refeita.')),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: () => marcarTodas(true) }, 'Marcar todas'), el('button', { class: 'btn-fantasma peq', onclick: () => marcarTodas(false) }, 'Desmarcar'))),
  el('div', { class: 'cartao-corpo' }, filtros, lst)));
}

function camposDelta(op, tm) {
  const num = (k, min, max) => el('input', { type: 'number', class: 'entrada', min, max, value: op[k], style: { width: '64px' }, onchange: (e) => { op[k] = Math.max(min, Math.min(max, +e.target.value || min)); e.target.value = op[k]; } });
  return el('div', { class: 'cartao-corpo campos-delta' }, el('b', {}, 'Notas:'), ' mudar no máximo ±', num('delta_max', 1, 10),
    tm ? [' e só quando a nota estimada ficar ', num('delta_min', 1, 15), ' ou mais longe da do banco'] : [' e só quando o ajuste for de ', num('delta_min', 1, 10), ' ou mais'],
    el('span', { class: 'mudo peq-txt' }, ' (vale com "Notas" ligado; padrão: ±2', tm ? ', diferença 3)' : ')'));
}

function editorTatica(a, n, m) {
  const muda = async (d) => { const x = await tentar(() => api('atualizar_marcar', { id: a.id, indices: [n], tatica: d })); if (x) { aplicar(x); desenharConferencia(a.id); } };
  const pare = (ev) => ev.stopPropagation();
  const sf = el('select', { onclick: pare, onchange: (e) => muda({ formacao: e.target.value }), title: 'Formação' }, ...S.formacoes.map((f) => opt(f, f, m.formacao)));
  const sp = el('select', { onclick: pare, onchange: (e) => muda({ profundidade: e.target.value }), title: 'Linha defensiva' }, ...Object.entries(PROF).map(([k, v]) => opt(k, v, m.profundidade)));
  const ss = el('select', { onclick: pare, onchange: (e) => muda({ saida: e.target.value }), title: 'Saída de bola' }, ...Object.entries(SAIDA).map(([k, v]) => opt(k, v, m.saida)));
  return el('span', { class: 'editor-tatica' }, sf, sp, ss);
}

async function trocarPar(a, apiId, apiNome, depois = null) {
  const volta = depois || (() => desenharConferencia(a.id));
  const busca = el('input', { type: 'search', class: 'entrada', placeholder: 'Nome do time no banco…', value: apiNome.split(' ')[0], autofocus: true, style: { width: '100%' } });
  const lista = el('div', { class: 'lista-busca' });
  let m;
  if (!S.timesDb) S.timesDb = (await tentar(() => api('times_db')))?.times || [];
  const todos = S.timesDb;
  const desenhar = () => {
    lista.innerHTML = '';
    const q = busca.value.trim().toLowerCase();
    for (const t of todos.filter((x) => !q || x.nome.toLowerCase().includes(q)).slice(0, 60)) {
      lista.append(el('button', { class: 'it-busca', onclick: async () => { m.fechar(true); const x = await tentar(() => api('atualizar_casar', { id: a.id, api_id: apiId, teamid: t.teamid })); if (x) volta(); } },
        el('b', {}, t.nome), el('span', { class: 'mudo' }, `${t.liga || '—'} · teamid ${t.teamid}`)));
    }
  };
  busca.oninput = desenhar;
  m = modal({ titulo: `Time do banco para ${apiNome}`, corpo: el('div', { class: 'col-gap' }, busca, lista),
    botoes: [{ rotulo: 'Sem par (não está no banco)', classe: 'btn-fantasma', fn: async () => { await tentar(() => api('atualizar_casar', { id: a.id, api_id: apiId, teamid: null })); volta(); } }, { rotulo: 'Fechar', valor: null }] });
  desenhar();
}

// ---------------------------------------------------------------- atualizar: várias ligas e seleções
function tabelaPares(a, depois) {
  const tb = el('tbody');
  for (const pr of [...a.pares].sort((x, y) => x.nota - y.nota)) {
    tb.append(el('tr', {}, el('td', {}, el('img', { src: im(pr.api_logo), alt: '' }), pr.api_nome),
      el('td', {}, pr.nome_db, el('div', { class: 'mudo peq-txt' }, `${pr.liga_db_nome} · teamid ${pr.teamid}`)),
      el('td', { class: `num ${pr.origem === 'manual' || pr.origem === 'mapa' || pr.origem === 'elenco' || pr.nota >= 0.85 ? '' : 'alerta-txt'}` }, pr.origem === 'manual' ? 'manual' : pr.origem === 'mapa' ? 'mapa' : pr.origem === 'elenco' ? el('span', { title: 'Dois times do banco tinham nome parecido: decidido pelos jogadores em comum no elenco' }, `${Math.round(pr.nota * 100)}% · elenco`) : `${Math.round(pr.nota * 100)}%`),
      el('td', {}, el('button', { class: 'btn-icone peq', title: 'Trocar o time do banco', onclick: () => trocarPar(a, pr.api_id, pr.api_nome, depois), html: icone('pincel', 12) }))));
  }
  for (const t of a.sem_par) {
    tb.append(el('tr', { class: 'sem-par' }, el('td', {}, el('img', { src: im(t.logo), alt: '' }), t.nome), el('td', { class: 'mudo' }, 'não está no banco'), el('td', {}, '—'),
      el('td', {}, el('button', { class: 'btn-icone peq', title: 'Escolher o time do banco', onclick: () => trocarPar(a, t.id, t.nome, depois), html: icone('ligar', 12) }))));
  }
  for (const t of a.fora || []) {
    tb.append(el('tr', { class: 'sem-par' }, el('td', { class: 'mudo' }, '—'), el('td', {}, t.nome, el('div', { class: 'mudo peq-txt' }, 'do banco, fora da lista da fonte (subiu ou caiu)')), el('td', {}, ''), el('td', {})));
  }
  return el('table', { class: 'tabela times-liga' }, el('thead', {}, el('tr', {}, ...[ehTm(a) ? 'Transfermarkt' : 'API', 'Banco', 'Casamento', ''].map((h) => el('th', {}, h)))), tb);
}

function custoConferir(a, op) {
  const n = a.pares.length;
  if (!op.elencos) return 0;
  const saidas = op.saidas && op.destino_saidas;
  return ehTm(a) ? n * (1 + (op.emprestimos ? 3 : 0) + (op.notas ? 28 : 0) + (saidas ? 3 : 0) + (op.tatica ? 6 : 0) + (op.tecnicos ? 2 : 0))
    : n * (1 + (op.emprestimos || saidas ? 1 : 0) + (op.notas ? 3 : 0) + (op.tatica ? 4 : 0) + (op.tecnicos ? 1 : 0));
}

async function desenharLote() {
  const p = $('#principal');
  p.innerHTML = '';
  const at = S.e.atualizacoes || [];
  if (!at.length) {
    p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('lista', 56) }), el('h2', {}, 'Nenhuma conferência'),
      el('p', {}, 'Marque as ligas do banco à esquerda e clique Casar todas: cada uma é casada com a liga de mesmo país e divisão na fonte escolhida.')));
    return;
  }
  const op = S.atual.opLote || (S.atual.opLote = { participantes: true, elencos: true, emprestimos: true, numeros: true, saidas: true, destino_saidas: true, notas: false, criar: false, tatica: false, tecnicos: false, delta_max: 2, delta_min: 3 });
  if (!S.atual.loteMarcadas) S.atual.loteMarcadas = new Set(at.map((a) => a.id));
  const mk = S.atual.loteMarcadas;
  for (const id of [...mk]) if (!at.some((a) => a.id === id)) mk.delete(id);
  const usaTm = at.filter((a) => mk.has(a.id)).every((a) => ehTm(a));
  p.append(el('div', { class: 'cab-time' }, el('div', { class: 'ic-c', html: icone('lista', 40) }),
    el('div', {}, el('h1', {}, 'Conferências'), el('div', { class: 'sub' }, `${at.length} liga(s) · ${at.filter((a) => a.conferido).length} conferida(s) · ${at.reduce((s2, a) => s2 + (a.marcadas || 0), 0)} mudança(s) marcada(s)`))));
  const btn = el('button', { class: 'btn-primario peq' });
  const rot = () => {
    const c = at.filter((a) => mk.has(a.id)).reduce((s2, a) => s2 + custoConferir(a, op), 0);
    btn.innerHTML = icone('baixar', 12) + ` Conferir ${mk.size} liga(s) (≈${c} ${usaTm ? 'pedidos' : 'chamadas'})`;
    btn.disabled = !mk.size || S.e.tarefa.ativa;
  };
  btn.onclick = async () => { aplicar(await tentar(() => api('atualizar_conferir_varias', { ids: [...mk], ...op }))); };
  rot();
  const ints = [['participantes', 'Participantes da liga', 'Quem subiu/caiu; um time que saiu de uma liga e está na lista de outra conferida junto vai para essa outra.'],
    ['elencos', 'Elencos atuais', 'Todos os times casados de cada liga.'], ['emprestimos', 'Transferências e empréstimos', ''], ['numeros', 'Números de camisa', ''],
    ['saidas', 'Saídas', 'Quem não está mais no elenco sai do time.'], ['destino_saidas', 'Saídas para o clube novo', 'Se o clube de hoje está no banco, ele vai para lá; senão, Sem Contrato.'],
    ['notas', 'Notas', 'API-Football: desempenho recente; Transfermarkt: valor de mercado (±2 no máximo).'],
    ['criar', 'Criar os jogadores que faltam', ''], ['tatica', 'Formação e tática', 'Formação dos últimos jogos e linha/saída de bola pela tabela.'],
    ['tecnicos', 'Técnicos', 'O técnico de hoje de cada time.']];
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'O que conferir'), el('p', { class: 'dica' }, 'As mesmas opções para todas as ligas marcadas abaixo; cada liga também pode ser aberta e conferida sozinha.')), btn),
    el('div', { class: 'cartao-corpo grade-2' }, ...ints.map(([k, t, d]) => interruptor({ titulo: t, descricao: d, marcado: op[k], aoMudar: (v) => { op[k] = v; rot(); } }).el)),
    camposDelta(op, usaTm)));
  const caixa = el('div', { class: 'lista-lote' });
  for (const a of at) {
    const ch = el('input', { type: 'checkbox', title: 'Conferir esta liga junto' });
    ch.checked = mk.has(a.id);
    ch.onclick = (ev) => ev.stopPropagation();
    ch.onchange = () => { if (ch.checked) mk.add(a.id); else mk.delete(a.id); rot(); };
    const det = el('details', { class: 'painel-lote' });
    det.open = !!(S.atual.loteAbertos || {})[a.id];
    det.addEventListener('toggle', () => { S.atual.loteAbertos = { ...(S.atual.loteAbertos || {}), [a.id]: det.open }; });
    const duvidosos = a.pares.filter((x) => !['manual', 'mapa', 'elenco'].includes(x.origem) && x.nota < 0.85).length;
    det.append(el('summary', {}, ch, el('span', { html: icone('seta', 12, 'seta') }),
      el('b', {}, a.liga_nome), ehTm(a) ? el('span', { class: 'selo-tm' }, 'TM') : null,
      el('span', { class: 'mudo' }, ` × ${a.liga_api_nome} ${a.temporada_nome || a.temporada || 'atual'}`),
      el('span', { class: 'chips-lote' },
        el('span', { class: 'chip' }, `${a.pares.length} pares`),
        duvidosos ? el('span', { class: 'chip aviso', title: 'Casamentos com menos de 85% de semelhança: confira' }, `${duvidosos} a conferir`) : null,
        a.sem_par.length ? el('span', { class: 'chip aviso' }, `${a.sem_par.length} sem par`) : null,
        a.fora?.length ? el('span', { class: 'chip' }, `${a.fora.length} saem`) : null,
        el('span', { class: `chip ${a.conferido ? 'ok' : ''}` }, a.conferido ? `${a.marcadas}/${a.n} mudanças` : 'não conferida')),
      el('button', { class: 'btn-fantasma peq', onclick: (ev) => { ev.preventDefault(); abrirAtual({ sel: a.id }); } }, 'Abrir')));
    det.append(el('div', { class: 'corpo-lote' }, tabelaPares(a, async () => { await atualizar(); desenharLote(); })));
    caixa.append(det);
  }
  p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Ligas e casamentos'), el('p', { class: 'dica' }, 'Abra cada liga para conferir os times casados (os menos parecidos primeiro); o lápis troca o time do banco e a troca fica guardada no mapa.')),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: () => { at.forEach((a) => mk.add(a.id)); desenharLote(); } }, 'Marcar todas'),
      el('button', { class: 'btn-fantasma peq', onclick: () => { mk.clear(); desenharLote(); } }, 'Nenhuma'))),
  el('div', { class: 'cartao-corpo justo' }, caixa)));
}

async function desenharSelecoesAtual() {
  const p = $('#principal');
  p.innerHTML = '';
  const l = S.atual.selecoes;
  const f = fonteAtual();
  const tm = f === TM;
  p.append(el('div', { class: 'cab-time' }, el('div', { class: 'ic-c', html: icone('mundo', 40) }),
    el('div', {}, el('h1', {}, l.nome), el('div', { class: 'sub' }, `${l.times} seleções ${l.feminina ? 'femininas' : 'masculinas'} no banco`)), el('div', { style: { marginLeft: 'auto' } }, seletorFonte())));
  if (tm && l.feminina) { p.append(nota('A Transfermarkt não tem futebol feminino: troque a fonte para a API-Football para atualizar as seleções femininas.', 'alerta')); return; }
  p.append(nota(`Marque as seleções e clique <b>Procurar na ${tm ? 'Transfermarkt' : 'API-Football'}</b> (${tm ? 'rápido' : '1 chamada por seleção, depois cache'}). As achadas entram no projeto como <b>seleções que já existem</b>: ao Gerar, a convocação atual (casada com os jogadores do banco e completada até o mínimo de cada posição do internationals), a escalação, os cobradores e o técnico são trocados; o resto da seleção fica. Depois de pôr no projeto, colete na aba Projeto.`, 'info'));
  const corpo = el('div', {}, el('div', { class: 'vazio' }, 'Carregando as seleções…'));
  p.append(corpo);
  const r = await tentar(() => api(`atualizar_selecoes?leagueid=${l.leagueid}&fonte=${f}`));
  if (!r || S.atual.selecoes !== l) return;
  S.atual.selLista = r.selecoes;
  corpo.innerHTML = '';
  const mk = S.atual.selMarcadas;
  const lista = r.selecoes;
  const comPar = lista.filter((x) => x.par);
  const acoes = el('div', { class: 'acoes-linha' });
  const desenharAcoes = () => {
    acoes.innerHTML = '';
    const marcadas = lista.filter((x) => mk.has(x.teamid));
    const prontas = marcadas.filter((x) => x.par && !x.item);
    acoes.append(el('button', { class: 'btn peq', disabled: !marcadas.length || S.e.tarefa.ativa, onclick: async () => { aplicar(await tentar(() => api('atualizar_casar_selecoes', { leagueid: l.leagueid, fonte: f, teamids: marcadas.map((x) => x.teamid) }))); } },
      icone('busca', 12), `Procurar ${marcadas.length || ''} na ${tm ? 'Transfermarkt' : 'API-Football'}`),
    el('button', { class: 'btn-primario peq', disabled: !prontas.length, onclick: async () => {
      const x = await tentar(() => api('atualizar_selecoes_projeto', { leagueid: l.leagueid, fonte: f, teamids: prontas.map((y) => y.teamid) }));
      if (!x) return;
      aplicar(x);
      aviso(`${x.adicionados} seleção(ões) no projeto`, { tipo: 'sucesso', detalhe: `Colete os dados na aba Projeto (Coletar no topo) e gere o banco.${x.sem_par?.length ? ` Sem par: ${x.sem_par.join(', ')}.` : ''}` });
      desenharSelecoesAtual();
    } }, icone('mais', 12), `Pôr ${prontas.length || ''} no projeto`),
    el('span', { class: 'mudo peq-txt' }, `${comPar.length} de ${lista.length} já achadas na fonte`),
    el('button', { class: 'btn-fantasma peq', onclick: () => { lista.forEach((x) => mk.add(x.teamid)); desenharSelecoesAtual(); } }, 'Todas'),
    el('button', { class: 'btn-fantasma peq', onclick: () => { lista.filter((x) => !x.par).forEach((x) => mk.add(x.teamid)); desenharSelecoesAtual(); } }, 'As sem par'),
    el('button', { class: 'btn-fantasma peq', onclick: () => { mk.clear(); desenharSelecoesAtual(); } }, 'Nenhuma'));
  };
  desenharAcoes();
  const tb = el('tbody');
  for (const x of lista) {
    const ch = el('input', { type: 'checkbox' });
    ch.checked = mk.has(x.teamid);
    ch.onchange = () => { if (ch.checked) mk.add(x.teamid); else mk.delete(x.teamid); desenharAcoes(); };
    tb.append(el('tr', {}, el('td', {}, ch), el('td', {}, el('b', {}, x.nome), el('div', { class: 'mudo peq-txt' }, `${x.nacao_en || '—'} · teamid ${x.teamid}`)),
      el('td', {}, x.par ? el('span', {}, el('img', { src: im(x.par.logo), alt: '', style: { width: '18px', verticalAlign: 'middle', marginRight: '6px' } }), x.par.nome, el('span', { class: 'mudo peq-txt' }, ` · ID ${x.par.id}`)) : el('span', { class: 'mudo' }, '—')),
      el('td', {}, x.item ? el('button', { class: 'link-banco', onclick: () => { trocarAba('projeto'); selecionar(x.item); } }, 'no projeto') : '')));
  }
  corpo.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Seleções do banco'), el('p', { class: 'dica' }, 'O par é a seleção principal do país na fonte (nunca sub-20, olímpica ou B).')), acoes),
    el('div', { class: 'cartao-corpo justo' }, el('table', { class: 'tabela times-liga' }, el('thead', {}, el('tr', {}, ...['', 'Seleção no banco', `Na ${tm ? 'Transfermarkt' : 'API-Football'}`, 'Projeto'].map((h) => el('th', {}, h)))), tb))));
}

// ---------------------------------------------------------------- painel direito
function secao(chave, titulo, ic, corpo) {
  const d = el('details', { class: 'secao' });
  d.open = !(S._fechadas || {})[chave];
  d.addEventListener('toggle', () => { S._fechadas = { ...(S._fechadas || {}), [chave]: !d.open }; });
  d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo).filter(Boolean)));
  return d;
}
const campo = (rot, controle, dica = '') => el('div', { class: 'campo' }, el('label', {}, rot), controle, dica ? el('div', { class: 'mudo peq-txt', html: dica }) : null);
const seg = (valor, itens, fn) => el('div', { class: 'segmentado' }, ...itens.map(([v, t, d]) => el('button', { class: String(valor ?? '') === String(v ?? '') ? 'ativo' : '', title: d || '', onclick: () => fn(v) }, t)));

function desenharPropriedades() {
  const p = $('#propriedades');
  p.innerHTML = '';
  const e = S.e;
  const a = e.api;
  const u = a.uso || {};
  const pct = u.limite ? Math.round((100 * (u.restantes ?? 0)) / u.limite) : 0;
  if (fonteAtual() === TM) p.append(secao('tm', 'Transfermarkt', 'mundo', secaoTm()));
  p.append(secao('api', 'API-Football', 'mundo', [
    a.tem_chave ? el('dl', { class: 'kv' },
      el('dt', {}, 'Plano'), el('dd', {}, a.plano || '—'),
      el('dt', {}, 'Chave'), el('dd', { class: 'mono' }, a.chave),
      el('dt', {}, 'Temporadas'), el('dd', {}, a.temporadas ? `${a.temporadas[0]}–${a.temporadas[1]} (estatísticas)` : 'todas'),
      el('dt', {}, 'Hoje'), el('dd', {}, `${u.restantes ?? '—'} de ${u.limite ?? '—'} chamadas restantes`)) : nota('Sem chave. Crie a conta grátis em <b>dashboard.api-football.com</b> e cole a chave.', 'alerta'),
    a.tem_chave ? el('div', { class: `medidor ${pct < 20 ? 'baixo' : ''}` }, el('div', { style: { width: `${pct}%` } })) : null,
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: trocarChave }, icone('ligar', 12), a.tem_chave ? 'Trocar a chave…' : 'Colar a chave…'),
      a.tem_chave ? el('button', { class: 'btn-fantasma peq', title: 'Consulta o plano e o uso (não gasta chamada)', onclick: () => tentar(async () => { await api('status_api'); atualizar(); }) }, icone('recarregar', 12), 'Atualizar') : null),
  ]));
  if (fonteAtual() !== TM) p.append(secao('tm', 'Transfermarkt', 'mundo', secaoTm()));
  const i = itemSel();
  if (i && S.aba !== 'atualizar') {
    p.append(secao('item', i.tipo === 'liga' ? 'Liga' : i.selecao ? 'Seleção' : 'Time', i.tipo === 'liga' ? 'trofeu' : 'escudo', propsItem(i)));
    if (i.tipo === 'time') {
      p.append(secao('tatica', 'Formação e tática', 'campo', propsTatica(i)));
      if (!i.selecao) p.append(secao('estadio', 'Estádio', 'estadio', propsEstadio(i)));
    }
  }
  const op = e.opcoes;
  const caminho = el('input', { type: 'text', class: 'entrada mono', value: op.saida || '', placeholder: 'Pasta onde gravar', spellcheck: 'false', onchange: (ev) => opcoes({ saida: ev.target.value.trim() }) });
  const num = (k, min, max) => el('input', { type: 'number', class: 'entrada', min, max, value: op[k], style: { width: '110px' }, onchange: (ev) => opcoes({ [k]: +ev.target.value }) });
  p.append(secao('gerar', 'Geração', 'engrenagem', [
    campo('Espalhamento das notas', seg(op.espalhamento, [[1.0, 'Preciso', 'Menor erro médio; destaques ficam um pouco baixos'], [1.25, 'Equilibrado', 'Padrão'], [1.5, 'Destaques fortes', 'Estrelas mais altas, reservas mais baixos']], (v) => opcoes({ espalhamento: v })),
      'API-Football. Na Transfermarkt a nota vem direto do valor de mercado (já espalhada como no jogo).'),
    campo('Escalações por time (padrão)', num('escalacoes', 0, 20), 'Cada escalação é 1 chamada (1 pedido na Transfermarkt) e dá a posição exata dos titulares e a formação; na API-Football, também as cores dos uniformes.'),
    campo('Perfis avulsos (elenco atual, API-Football)', num('perfis_faltantes', 0, 60), 'Jogadores do elenco atual que não jogaram na temporada liberada: 1 chamada cada para nascimento, altura e nacionalidade. (A Transfermarkt já traz isso no elenco.)'),
    interruptor({ titulo: 'Completar a API-Football com a Transfermarkt', descricao: 'Ao coletar um time da API-Football, busca o mesmo clube na Transfermarkt (2 pedidos) e preenche o que a API não dá: nascimento, pé, posição exata, altura e nacionalidades. O que a API trouxe não muda.', marcado: op.completar_tm, aoMudar: (v) => opcoes({ completar_tm: v }) }).el,
    interruptor({ titulo: 'Estatísticas da temporada (Transfermarkt)', descricao: 'Jogos, minutos, gols e cartões de cada jogador: 1 pedido por jogador. Só refinam os atributos — a nota vem do valor de mercado.', marcado: op.tm_estatisticas, aoMudar: (v) => opcoes({ tm_estatisticas: v }) }).el,
    interruptor({ titulo: 'Usar a classificação', descricao: 'Times do alto da tabela ficam mais fortes e jogam mais adiantados (1 chamada por liga).', marcado: op.classificacao, aoMudar: (v) => opcoes({ classificacao: v }) }).el,
    interruptor({ titulo: 'Aparência pelas fotos', descricao: e.fotos_ok ? 'Pele, cor e tamanho do cabelo e barba lidos na foto de cada jogador (Analisar as fotos).' : 'Precisa do OpenCV (componentes do Criador de Minifaces, em Componentes no Super Tool).', marcado: op.aparencia_fotos && e.fotos_ok, desabilitado: !e.fotos_ok, aoMudar: (v) => opcoes({ aparencia_fotos: v }) }).el,
    interruptor({ titulo: 'Baixar escudos e fotos', descricao: 'Não gasta chamadas. As fotos vão para o Criador de Minifaces.', marcado: op.baixar_imagens, aoMudar: (v) => opcoes({ baixar_imagens: v }) }).el,
    interruptor({ titulo: 'Mandar as fotos ao Criador de Minifaces', descricao: 'Ao gravar, as fotos dos jogadores novos já entram lá ligadas aos IDs.', marcado: op.minifaces_auto, aoMudar: (v) => opcoes({ minifaces_auto: v }) }).el,
    campo('Escudo no jogo', seg(op.visual, [['proprio', 'Do time novo', 'assetid = teamid novo: importe o escudo no FET'], ['modelo', 'Do time-modelo', 'Usa o escudo do time-modelo até você importar o seu']], (v) => opcoes({ visual: v }))),
    el('details', { class: 'secao', style: { border: 0 } }, el('summary', { html: icone('seta', 12, 'seta') + 'IDs iniciais' }), el('div', { class: 'secao-corpo' },
      campo('Jogadores e técnicos a partir de', num('jogador_inicio', 1, 500000)), campo('Times a partir de', num('time_inicio', 1, 200000)), campo('Ligas a partir de', num('liga_inicio', 1, 4000)))),
    campo('Pasta de saída', el('div', { class: 'caminho-linha' }, caminho, el('button', { class: 'btn', onclick: escolherSaida, title: 'Escolher…' }, icone('pasta', 14)))),
    e.internationals ? el('div', { class: 'mudo peq-txt' }, `internationals.txt: ${e.internationals.masculinas} seleções masculinas e ${e.internationals.femininas} femininas (Dados do jogo).`) : el('div', { class: 'mudo peq-txt', html: 'Seleções novas: importe o <b>internationals.txt</b> em Dados do jogo (Super Tool) para elas entrarem nele.' }),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', disabled: !podeGerar(), onclick: gerar }, icone('bancoDados', 12), 'Gerar banco'),
      el('button', { class: 'btn peq', disabled: !op.saida, onclick: () => tentar(() => api('abrir', {})) }, icone('externo', 12), 'Abrir a pasta')),
  ]));
  const c = e.calibracao || {};
  const ct = e.calibracao_tm || {};
  p.append(secao('calib', 'Calibração das notas', 'alvo', [
    el('div', { class: 'peq-txt', html: `<b>API-Football</b> (nota da API, minutos, idade): ${esc(c.origem || '—')}${c.erro_medio ? ` · erro médio ${c.erro_medio}` : ''}.` }),
    el('div', { class: 'peq-txt', html: `<b>Transfermarkt</b> (valor de mercado e idade): ${esc(ct.origem || '—')}${ct.erro_medio ? ` · erro médio ${ct.erro_medio}` : ''}${ct.amostra ? ` · ${ct.amostra} jogadores` : ''}.` }),
    el('div', { class: 'mudo peq-txt' }, 'Erro médio testado com o time fora da amostra. Recalibrar casa os jogadores do cache (das duas fontes) com os mesmos jogadores do banco e refaz os coeficientes. Colete times que já existem no banco para melhorar.'),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: recalibrar }, icone('alvo', 12), 'Recalibrar com o cache')),
  ]));
}

function propsItem(i) {
  const out = [];
  const set = (d) => setItem(i, d);
  out.push(campo('Nome', el('input', { type: 'text', class: 'entrada', value: i.nome, onchange: (e) => set({ nome: e.target.value }) })));
  if (!i.selecao) out.push(interruptor({ titulo: 'Feminino', descricao: 'Jogadoras com aparência feminina; times, ligas e níveis de referência femininos do banco.', marcado: i.feminino, aoMudar: (v) => set({ feminino: v }) }).el);
  const nv = el('input', { type: 'number', class: 'entrada', step: 0.5, min: 40, max: 92, value: i.nivel ?? '', style: { width: '90px' }, onchange: (e) => set({ nivel: e.target.value }) });
  out.push(campo('Nível', el('div', { class: 'nivel-linha' }, nv,
    i.tipo === 'time' && i.nivel_manual ? el('button', { class: 'btn-fantasma peq', onclick: () => set({ nivel: '' }) }, icone('restaurar', 12), 'Automático') : null),
  `${esc(i.nivel_motivo || '')}${i.tipo === 'time' && !i.selecao ? ` · automático: ${i.nivel_valor ?? i.nivel_auto ?? '—'}` : ''}.${ehTm(i) && i.tipo === 'time' && !i.selecao ? ' Mudar o nível desloca as notas de todo o elenco.' : ''}${i.selecao ? '' : `<br>Referência no banco: ${esc(refNiveis(i))}`}`));
  const ligas = S.ligasDb.filter((l) => !l.internacional && (l.feminina === !!i.feminino || l.times === 0));
  if (i.tipo === 'liga') {
    const s = el('select', { class: 'seletor', onchange: (e) => set({ destino: e.target.value }) },
      opt('nova', 'Criar uma liga nova no banco', i.destino), ...ligas.map((l) => opt(l.leagueid, `${l.nome} (${l.leagueid})`, i.destino)));
    out.push(campo('Destino dos times', s, i.destino === 'nova' ? 'Liga nova (para o modo carreira ela também precisa entrar no compdata).' : 'Os times entram nessa liga do banco.'));
    out.push(campo('Divisão', el('input', { type: 'number', class: 'entrada', min: 1, max: 9, value: i.divisao || 1, style: { width: '80px' }, onchange: (e) => set({ divisao: e.target.value }) })));
    if (i.destino === 'nova') out.push(campo('ID da liga nova', el('input', { type: 'number', class: 'entrada mono', value: i.leagueid || '', placeholder: 'automático', style: { width: '120px' }, onchange: (e) => set({ leagueid: e.target.value || null }) })));
  } else if (!i.liga_item && !i.selecao) {
    const s = el('select', { class: 'seletor', onchange: (e) => set({ destino: e.target.value }) }, ...ligas.map((l) => opt(l.leagueid, `${l.nome} (${l.leagueid})`, i.destino)));
    out.push(campo('Liga do banco onde o time entra', s));
  }
  if (i.tipo === 'time' && !i.selecao) {
    out.push(campo('Elenco', seg(i.modo || 'temporada', [['temporada', `Temporada ${tempNome(i)}`, ehTm(i) ? 'O elenco do clube nessa temporada (valor de mercado da época)' : 'Quem jogou pelo time nessa temporada'],
      ['atual', 'Atual', ehTm(i) ? 'O elenco de hoje, com o valor de mercado de hoje' : 'O elenco de hoje, com estatísticas da última temporada liberada']], (v) => set({ modo: v }))));
  }
  if (i.tipo === 'time') {
    out.push(campo('Escalações', el('input', { type: 'number', class: 'entrada', min: 0, max: 20, value: i.escalacoes ?? 5, style: { width: '80px' }, onchange: (e) => set({ escalacoes: e.target.value }) }),
      i.selecao ? 'Opcional nas seleções: dão a formação e as cores dos uniformes.' : ''));
    if (!i.selecao || !i.api) {
      out.push(campo('ID do time', el('input', { type: 'number', class: 'entrada mono', value: i.teamid || '', placeholder: 'automático', style: { width: '120px' }, onchange: (e) => set({ teamid: e.target.value || null }) }),
        i.selecao ? 'Só vale se a seleção ainda não existir no banco.' : 'Vazio: o próximo livre a partir do início escolhido em Geração.'));
    }
    out.push(campo('Time-modelo (teamid)', el('input', { type: 'text', class: 'entrada mono', value: i.modelo || '', placeholder: 'automático', style: { width: '120px' }, onchange: (e) => set({ modelo: e.target.value.trim() || null }) }),
      i.selecao ? 'Automático: uma seleção do banco da mesma confederação com nível parecido.' : 'Automático: um time do banco do mesmo país e gênero com nível parecido.'));
    const acoes = el('div', { class: 'acoes-linha' });
    if (i.estado === 'pronto') acoes.append(el('button', { class: 'btn peq', disabled: S.e.tarefa.ativa, onclick: () => coletar([i.id], true) }, icone('recarregar', 12), 'Coletar de novo'));
    if (i.estado === 'pronto' && S.e.fotos_ok) acoes.append(el('button', { class: 'btn peq', disabled: S.e.tarefa.ativa, onclick: () => analisarFotos([i.id]) }, icone('rosto', 12), 'Analisar as fotos'));
    out.push(acoes);
  }
  const livre = temporadasLiberadas();
  if (!ehTm(i) && !i.selecao && !livre(i.temporada) && i.modo !== 'atual') out.push(nota(`O plano não libera estatísticas de ${i.temporada}: use "Atual" ou uma temporada entre ${S.e.api.temporadas.join(' e ')}.`, 'alerta'));
  out.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: () => remover(i) }, icone('apagar', 12), 'Tirar do projeto')));
  return out;
}

function propsTatica(i) {
  const t = i.tatica || {};
  const pv = S.previa[i.id];
  const formAPI = pv?.formacao_api;
  const set = (d) => setItem(i, { tatica: d });
  const fs = el('select', { class: 'seletor', onchange: (e) => set({ formacao: e.target.value }) },
    opt('', `Automática${formAPI ? ` (API: ${formAPI})` : ' (a mais usada nas escalações)'}`, t.formacao || ''), ...S.formacoes.map((f) => opt(f, f, t.formacao || '')));
  return [
    campo('Formação', fs),
    campo('Linha defensiva', seg(t.profundidade ?? '', [['', 'Auto', 'Pela força do time na liga'], ...Object.entries(PROF).map(([k, v]) => [+k, v])], (v) => set({ profundidade: v }))),
    campo('Saída de bola', seg(t.saida ?? '', [['', 'Auto', 'Pela força do time na liga'], ...Object.entries(SAIDA).map(([k, v]) => [+k, v])], (v) => set({ saida: v })),
      'Automático: no banco, os times do alto da tabela usam passe curto e linha alta; os de baixo, bola longa e linha recuada.'),
  ];
}

function propsEstadio(i) {
  const e = i.estadio || {};
  const real = i.api?.estadio || {};
  const set = (d) => setItem(i, { estadio: d });
  const gen = el('select', { class: 'seletor', onchange: (ev) => set({ stadiumid: ev.target.value }) },
    opt('', 'Automático (pela capacidade)', e.stadiumid || ''), ...S.estadios.map((s) => opt(s.id, `${s.nome} · ${fmt(s.capacidade)}`, e.stadiumid || '')));
  return [
    campo('Nome no jogo (stadiumassignments)', el('input', { type: 'text', class: 'entrada', value: e.nome ?? '', placeholder: real.nome || 'o do estádio genérico', onchange: (ev) => set({ nome: ev.target.value }) }),
      real.nome ? `${curtaFonte(i)}: ${esc(real.nome)}${real.cidade ? ` · ${esc(real.cidade)}` : ''}${real.capacidade ? ` · ${fmt(real.capacidade)} lugares` : ''}` : `A ${curtaFonte(i)} não tem o estádio deste time${ehTm(i) && i.estado !== 'pronto' ? ' (vem com a coleta)' : ''}.`),
    campo('Capacidade', el('input', { type: 'number', class: 'entrada', min: 1000, max: 120000, value: e.capacidade ?? '', placeholder: real.capacidade ? String(real.capacidade) : 'pelo nível', style: { width: '120px' }, onchange: (ev) => set({ capacidade: ev.target.value ? +ev.target.value : null }) }),
      'A do estádio real quando a API tem; senão a típica do nível do time no banco (ajustada pelo país; menor no feminino).'),
    campo('Estádio genérico', gen),
  ];
}

function refNiveis(i) {
  const com = S.ligasDb.filter((l) => l.nivel && !l.internacional && l.feminina === !!i.feminino);
  const mesmas = com.filter((l) => String(l.pais) === String(i.nacao)).sort((a, b) => a.divisao - b.divisao);
  return (mesmas.length ? mesmas : com.slice(0, 4)).map((l) => `${l.nome} ${l.nivel}`).join(' · ');
}

async function trocarChave() {
  const inp = el('input', { type: 'password', class: 'entrada mono', placeholder: 'chave da API-Football', autocomplete: 'off', style: { width: '100%' } });
  const r = await modal({ titulo: 'Chave da API-Football', texto: 'Fica só neste computador (pasta dados do Super Tool) e não vai no pacote para outro computador.',
    corpo: el('div', {}, inp), botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Gravar', classe: 'btn-primario', padrao: true, fn: () => inp.value.trim() || false }] }).promessa;
  if (!r) return;
  aplicar(await tentar(() => api('chave', { chave: r })));
  S.nav.paises = null;
  desenharApi();
}

function secaoTm() {
  const st = S.e.tm || {};
  const conf = S.tmOutro ? 'outro' : (st.configurado || 'auto');
  const url = el('input', { type: 'text', class: 'entrada mono', value: st.outro_url || '', placeholder: 'http://192.168.0.10:8000/', spellcheck: 'false',
    onchange: (ev) => { if (ev.target.value.trim()) tmConfig('outro', ev.target.value.trim()); } });
  const modos = [['auto', 'Automático', 'O servidor local se estiver instalado; senão a instância pública'], ['local', 'Local', 'Servidor no próprio computador (Componentes): rápido e sem limite'],
    ['publico', 'Pública', 'transfermarkt-api.fly.dev: só para testes, ≈1 pedido a cada 1,6 s'], ['outro', 'Outro', 'Um servidor seu (ex.: o Docker da transfermarkt-api em outro computador)']];
  return [
    el('dl', { class: 'kv' },
      el('dt', {}, 'Usando'), el('dd', {}, `${MODO_TM[st.modo] || st.modo || '—'}${st.configurado === 'auto' ? ' (automático)' : ''}`),
      el('dt', {}, 'Endereço'), el('dd', { class: 'mono', style: { wordBreak: 'break-all' } }, st.url || '—'),
      el('dt', {}, 'Local'), el('dd', {}, st.local_instalado ? (st.modo === 'local' && st.rodando ? 'instalado · ligado' : 'instalado (liga sozinho quando precisar)') : 'não instalado'),
      el('dt', {}, 'Pedidos'), el('dd', {}, `${fmt(st.feitas)} nesta sessão (o resto vem do cache)`)),
    st.erro ? nota(esc(st.erro), 'alerta') : null,
    campo('Servidor', seg(conf, modos, (v) => { if (v === 'outro' && !st.outro_url) { S.tmOutro = true; desenharPropriedades(); return; } S.tmOutro = false; tmConfig(v, v === 'outro' ? st.outro_url : null); })),
    conf === 'outro' ? campo('Endereço do servidor', url, 'O endereço completo, com http:// e a porta.') : null,
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', title: 'Liga o servidor (se for o local) e faz um pedido de teste', onclick: testarTm }, icone('ligar', 12), 'Testar'),
      st.local_instalado ? null : el('button', { class: 'btn-primario peq', title: 'transfermarkt-api + FastAPI e mais 22 bibliotecas (≈4 MB) no Python do Super Tool', onclick: instalarTm }, icone('baixar', 12), 'Instalar o servidor local…')),
    el('div', { class: 'mudo peq-txt', html: 'Dados de <b>transfermarkt.com</b> lidos pela <b>transfermarkt-api</b> (felipeall, licença MIT). Use para fins pessoais e respeite os termos da Transfermarkt. Não tem futebol feminino.' }),
  ];
}
async function tmConfig(modo, url) {
  const r = await tentar(() => api('tm_config', { modo, url }));
  if (!r) return;
  S.tmOutro = false;
  aplicar(r);
}
async function testarTm() {
  const fim = aviso('Testando a Transfermarkt…', { tempo: 60000 });
  const r = await tentar(() => api('tm_testar', {}));
  fim();
  if (!r) return;
  aplicar(r);
  aviso('A Transfermarkt respondeu', { tipo: 'sucesso', detalhe: `${MODO_TM[r.tm?.modo] || ''} · ${r.segundos} s` });
  if (fonteAtual() === TM && !S.nav.paises && S.aba === 'api') desenharApi();
}
function instalarTm() {
  return instalarComponentes({ rota: 'tm_componentes', rotaInstalar: 'tm_componentes_instalar', aoTerminar: async () => { await atualizar(); if (fonteAtual() === TM) { S.nav = novaNav(TM); desenharApi(); } } });
}

async function opcoes(d) { aplicar(await tentar(() => api('opcoes', d))); if (('espalhamento' in d || 'visual' in d || 'aparencia_fotos' in d) && itemSel()?.tipo === 'time' && S.aba !== 'atualizar') desenharPrincipal(); }
async function escolherSaida() { const r = await tentar(() => api('dialogo', {})); if (r) aplicar(r); }
async function recalibrar() {
  const fim = aviso('Recalibrando…', { tempo: 60000 });
  const r = await tentar(() => api('calibrar', {}));
  fim();
  if (!r) return;
  aplicar(r);
  const ct = r.calibracao_tm;
  aviso('Notas recalibradas', { tipo: 'sucesso', detalhe: `API-Football: ${r.calibracao.origem}${r.calibracao.erro_medio ? ` · erro médio ${r.calibracao.erro_medio}` : ''}${ct ? ` · Transfermarkt: ${ct.amostra} jogadores, erro médio ${ct.erro_medio}` : ''}` });
  if (itemSel()?.tipo === 'time') desenharPrincipal();
}
async function analisarFotos(ids) { aplicar(await tentar(() => api('analisar_fotos', { ids }))); }
async function recarregarInicio() {
  const ri = await api('inicio').catch(() => null);
  if (ri) { S.ligasDb = ri.ligas_db || []; S.nacoes = ri.nacoes || []; S.formacoes = ri.formacoes || []; S.estadios = ri.estadios || []; }
}

// ---------------------------------------------------------------- coleta e geração
function custoTotal() { return S.e.itens.filter((x) => x.tipo === 'time' && x.estado !== 'pronto').reduce((s, t) => s + (t.custo || 0), 0); }
function podeGerar() {
  const ts = S.e.itens.filter((x) => x.tipo === 'time');
  const at = (S.e.atualizacoes || []).some((a) => a.marcadas);
  return (ts.length || at) && ts.every((t) => t.estado === 'pronto') && !S.e.tarefa.ativa && !!S.e.banco;
}

async function coletar(ids, refazer = false) {
  aplicar(await tentar(() => api('coletar', { ids, refazer })));
}
async function gerar() {
  const r = await tentar(() => api('gerar', {}));
  if (r) aplicar(r);
}
function desenharTopo() {
  const e = S.e;
  const t = e.tarefa;
  const c = custoTotal();
  const bc = $('#btn-coletar');
  bc.disabled = t.ativa || !e.itens.some((x) => x.tipo === 'time' && x.estado !== 'pronto');
  bc.innerHTML = icone(t.ativa && t.tipo === 'coleta' ? 'recarregar' : 'baixar', 14, t.ativa && t.tipo === 'coleta' ? 'girando' : '') + (t.ativa && t.tipo === 'coleta' ? ` Coletando ${t.feito}/${t.total}…` : ` Coletar${c ? ` (≈${c})` : ''}`);
  const bg = $('#btn-gerar');
  bg.disabled = !podeGerar();
  bg.innerHTML = icone(t.ativa && t.tipo === 'gerar' ? 'recarregar' : 'bancoDados', 14, t.ativa && t.tipo === 'gerar' ? 'girando' : '') + (t.ativa && t.tipo === 'gerar' ? ' Gerando…' : ' Gerar banco');
  const nt = e.itens.filter((x) => x.tipo === 'time').length;
  const nu = (e.atualizacoes || []).reduce((s, x) => s + (x.marcadas || 0), 0);
  $('#titulo').innerHTML = `<b>${nt ? `${nt} time(s) no projeto` : 'Projeto vazio'}${nu ? ` · ${nu} mudança(s) no banco` : ''}</b><span class="pasta">${esc(e.opcoes.saida || 'escolha a pasta de saída')}</span>`;
}
function desenharStatus() {
  const e = S.e;
  const t = e.tarefa;
  const ts = e.itens.filter((x) => x.tipo === 'time');
  $('#status-esq').innerHTML = `<span><b>${ts.length}</b> times</span><span><b>${ts.filter((x) => x.estado === 'pronto').length}</b> com dados</span><span><b>${fmt(ts.reduce((s, x) => s + (x.jogadores || 0), 0))}</b> jogadores</span>${t.ativa ? `<span>${esc(t.msg)}</span>` : ''}`;
  const sd = $('#status-dir');
  sd.innerHTML = '';
  const usaTm = fonteAtual() === TM || e.itens.some(ehTm) || (e.atualizacoes || []).some(ehTm);
  if (fonteAtual() !== TM || e.api.tem_chave) sd.append(el('span', { class: `chip ${e.api.tem_chave ? ((e.api.uso?.restantes ?? 0) > 10 ? 'ok' : 'aviso') : 'erro'}`, title: 'Chamadas restantes hoje na API-Football' }, icone('mundo', 12), e.api.tem_chave ? `${e.api.uso?.restantes ?? '—'}/${e.api.uso?.limite ?? '—'} chamadas` : 'sem chave'));
  if (usaTm) {
    const st = e.tm || {};
    sd.append(el('span', { class: `chip ${st.erro ? 'erro' : st.modo === 'publico' ? 'aviso' : 'ok'}`, title: `Transfermarkt: ${st.url || ''}${st.modo === 'publico' ? ' (instância pública: lenta, só para testes)' : ''}` }, icone('mundo', 12), `Transfermarkt ${({ local: 'local', publico: 'pública', outro: 'remota' })[st.modo] || ''}`));
  }
  sd.append(el('span', { class: `chip ${e.banco ? 'ok' : 'aviso'}`, title: e.banco ? e.banco.caminho : 'Importe em Dados do jogo' }, icone('bancoDados', 12), e.banco ? e.banco.nome_jogo : 'sem banco'));
}
function acompanhar() {
  if (S.polling) return;
  S.polling = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (!e) return;
    aplicar(e);
    if (!e.tarefa.ativa) { clearInterval(S.polling); S.polling = null; }
  }, 700);
}
function abrirMinifaces() {
  if (window.parent && window.parent !== window) window.parent.postMessage({ brfp: 'abrir', id: 'minifaces' }, '*');
  else aviso('Abra o Criador de Minifaces', { tipo: 'info', detalhe: 'As fotos já estão na fila dele, ligadas aos IDs.' });
}
async function enviarMinifaces(pasta) {
  const r = await tentar(() => api('minifaces', { pasta }));
  if (!r) return;
  aviso(`${r.enviadas} foto(s) para o Criador de Minifaces`, { tipo: 'sucesso', detalhe: r.enviadas < r.total ? `${r.total - r.enviadas} já estavam na fila.` : 'Elas entram lá já ligadas aos IDs dos jogadores novos.' });
  abrirMinifaces();
}
function fimTarefa(t) {
  if (t.tipo === 'coleta') {
    aviso(t.erro ? 'Coleta terminou com problemas' : 'Coleta concluída', { tipo: t.erro ? 'aviso' : 'sucesso', detalhe: t.erro || 'Clique nos times para ver os elencos gerados.', tempo: t.erro ? 10000 : 4000 });
    desenharPrincipal();
    S.nav.paises && S.aba === 'api' && desenharApi();
  } else if (t.tipo === 'fotos') {
    aviso(t.erro ? 'A análise das fotos falhou' : 'Fotos analisadas', { tipo: t.erro ? 'erro' : 'sucesso', detalhe: t.erro || 'A aparência dos jogadores segue o que as fotos mostram (dá para corrigir na ficha de cada um).' });
    if (S.aba !== 'atualizar') desenharPrincipal();
  } else if (t.tipo === 'preparar') {
    const r = t.resultado || {};
    aviso(t.msg, { tipo: r.erros?.length ? 'aviso' : 'sucesso', detalhe: r.erros?.length ? r.erros.join(' · ') : 'Confira os casamentos de cada liga e clique Conferir.', tempo: r.erros?.length ? 10000 : 4000 });
    S.atual.marcadas.clear();
    S.atual.loteMarcadas = new Set(r.ids || []);
    if (S.aba === 'atualizar') abrirAtual({ lote: true });
  } else if (t.tipo === 'selecoes') {
    aviso(t.msg, { tipo: t.erro ? 'aviso' : 'sucesso', detalhe: t.erro || 'Marque as achadas e clique Pôr no projeto.', tempo: t.erro ? 10000 : 4000 });
    if (S.aba === 'atualizar' && S.atual.selecoes) desenharSelecoesAtual();
  } else if (t.tipo === 'atualizar') {
    aviso(t.erro ? 'A conferência parou' : 'Conferência pronta', { tipo: t.erro ? 'aviso' : 'sucesso', detalhe: t.erro || t.msg, tempo: t.erro ? 10000 : 4000 });
    if (S.aba === 'atualizar') { desenharAtualizarEsq(); desenharAtualizacao(); }
  } else if (t.tipo === 'gerar') {
    if (t.erro) { aviso('A geração falhou', { tipo: 'erro', detalhe: t.erro, tempo: 12000 }); return; }
    const r = t.resultado || {};
    const fotos = (r.fotos || []).length;
    const deAntes = (r.avisos || []).filter((a) => a.includes('já estava assim'));
    r.avisos = (r.avisos || []).filter((a) => !a.includes('já estava assim'));
    if (deAntes.length) r.avisos.push(`${deAntes.length} detalhe(s) que já vinham do banco importado (números de camisa repetidos etc.) — veja no relatório.`);
    modal({ titulo: 'Banco gerado', texto: esc(r.pasta || ''), corpo: el('div', {},
      el('p', {}, `${r.ligas || 0} liga(s) nova(s), ${r.times} time(s), ${r.selecoes || 0} seleção(ões) e ${fmt(r.jogadores)} jogadores novos. Textos novos de idioma: ${r.idioma}.`),
      r.internationals ? el('p', {}, `internationals.txt: ${r.internationals.linhas.length} seleção(ões) nova(s) — ${esc(r.internationals.arquivo)}`) : null,
      r.minifaces !== undefined ? el('p', {}, `${r.minifaces} foto(s) já foram para o Criador de Minifaces.`) : null,
      ...(r.avisos || []).slice(0, 6).map((a) => nota(esc(a), 'alerta')),
      el('p', { class: 'mudo peq-txt' }, 'Importe db\\fifa_ng_db.db no FET, o idioma (idioma\\LanguageStrings1/2.txt) e, se houver seleções novas, o internationals.txt. Detalhes no relatorio.txt.')),
    botoes: [{ rotulo: 'Relatório', fn: () => { tentar(() => api('abrir', { caminho: r.pasta + '\\relatorio.txt' })); return false; } },
      fotos ? { rotulo: `Fotos → Criador de Minifaces (${fotos})`, fn: () => { enviarMinifaces(r.pasta); } } : null,
      { rotulo: 'Abrir a pasta', classe: 'btn-primario', padrao: true, fn: () => { tentar(() => api('abrir', { caminho: r.pasta })); } }].filter(Boolean) });
  }
}

function menus() {
  barraMenus($('#menus'), [
    ['Projeto', () => [
      { rotulo: 'Coletar o que falta', icone: 'baixar', desabilitado: S.e.tarefa.ativa, fn: () => coletar(null) },
      { rotulo: 'Analisar as fotos de todos', icone: 'rosto', desabilitado: S.e.tarefa.ativa || !S.e.fotos_ok, fn: () => analisarFotos(null) },
      { rotulo: 'Gerar banco', icone: 'bancoDados', atalho: 'Ctrl+Enter', desabilitado: !podeGerar(), fn: gerar },
      '-',
      { rotulo: 'Pasta de saída…', icone: 'pasta', fn: escolherSaida },
      { rotulo: 'Abrir a pasta de saída', icone: 'externo', desabilitado: !S.e.opcoes.saida, fn: () => tentar(() => api('abrir', {})) },
      { rotulo: 'Mandar as fotos do último banco ao Criador de Minifaces', icone: 'miniface', fn: () => enviarMinifaces(null) },
      '-',
      { rotulo: 'Esvaziar o projeto', icone: 'apagar', desabilitado: !S.e.itens.length && !(S.e.atualizacoes || []).length, fn: async () => { if (await confirmar('Esvaziar o projeto?', 'Times, ligas, seleções e conferências saem do projeto. O cache da API continua (nada é baixado de novo).', { rotulo: 'Esvaziar', perigo: true })) { aplicar(await tentar(() => api('limpar', {}))); S.atual.sel = null; desenharPrincipal(); } } },
    ]],
    ['API', () => [
      { rotulo: 'Fonte: API-Football', marcado: fonteAtual() !== TM, fn: () => trocarFonte('apifootball') },
      { rotulo: 'Fonte: Transfermarkt', marcado: fonteAtual() === TM, fn: () => trocarFonte(TM) },
      '-',
      { rotulo: S.e.api.tem_chave ? 'Trocar a chave da API-Football…' : 'Colar a chave da API-Football…', icone: 'ligar', fn: trocarChave },
      { rotulo: 'Atualizar plano e uso', icone: 'recarregar', desabilitado: !S.e.api.tem_chave, fn: () => tentar(async () => { await api('status_api'); atualizar(); }) },
      '-',
      { rotulo: 'Testar a Transfermarkt', icone: 'ligar', fn: testarTm },
      { rotulo: 'Instalar o servidor local da Transfermarkt…', icone: 'baixar', desabilitado: !!S.e.tm?.local_instalado, fn: instalarTm },
      '-',
      { rotulo: 'Recalibrar as notas com o cache', icone: 'alvo', fn: recalibrar },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Sobre o Criador de Ligas e Times', icone: 'info', fn: () => dialogoSobre({ nome: 'Criador de Ligas e Times', versao: S.versao, html: `
        Cria ligas, times, seleções e jogadores no banco do jogo a partir da <b>API-Football</b> (api-sports.io) ou da <b>Transfermarkt</b>
        (pela transfermarkt-api de felipeall, MIT; dados de transfermarkt.com para uso pessoal) e atualiza o que já existe:
        participantes das ligas, elencos (transferências, empréstimos, saídas, números) e notas pelo desempenho recente.<br><br>
        <b>Notas:</b> nível do time (média dos 14 mais fortes, pela liga e pela classificação) + ajuste pela nota média da API, minutos e idade,
        calibrado casando jogadores da API com os mesmos jogadores do banco (erro médio ≈ 2,5). Atributos: perfil da posição no banco +
        estatísticas, acertados para dar a nota geral exata da posição. <b>Aparência:</b> jogador genérico do banco do mesmo gênero e nação,
        ou parecido com a foto (pele, cabelo, barba). Na Transfermarkt a nota vem do valor de mercado e da idade (erro médio ≈ 1,7),
        com a posição e o pé de cada jogador.<br><br>
        <b>Saída:</b> banco novo (cópia do importado + linhas novas, alteradas e removidas), tabelas .txt, idioma, internationals.txt e
        escudos/fotos (com envio ao Criador de Minifaces).<br><br>
        <b>2.2</b> — Atualizar banco com várias ligas de uma vez (painéis, desempate pelo elenco) e ligas de seleções; rebaixado sem
        divisão abaixo vai para o Resto do Mundo; foto na prévia, tirar jogador do elenco, jogadores que já estão no banco; Transfermarkt:
        idade da época, temporadas antigas pela liga e classificação, nacionalidade válida.<br>
        <b>2.1</b> — Transfermarkt como segunda fonte (escolha no topo da aba API): ligas, times, seleções, coleta e Atualizar banco;
        servidor local em Componentes ou instância pública.<br>
        <b>2.0</b> — seleções (convocação + internationals), feminino, atualização de elencos e participantes, aparência pelas fotos, tática,
        técnico, estádio, IDs à mão, todas as colunas editáveis, vários times de uma vez, nomes com acento corrigidos.<br>
        <b>1.0</b> — primeira versão.` }) },
    ]],
  ]);
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && podeGerar()) { e.preventDefault(); gerar(); }
});

async function iniciar() {
  divisorArrastavel($('#div-esq'), '--esq', { min: 230, max: 480 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 260, max: 520, lado: 'dir' });
  const r = await api('inicio');
  S.versao = r.versao;
  S.ligasDb = r.ligas_db || [];
  S.nacoes = r.nacoes || [];
  S.formacoes = r.formacoes || [];
  S.estadios = r.estadios || [];
  $('#versao').textContent = r.versao;
  $('#btn-coletar').onclick = () => coletar(null);
  $('#btn-gerar').onclick = gerar;
  aplicar(r);
  S.nav = novaNav(fonteAtual());
  menus();
  if (r.itens.length) S.aba = 'projeto';
  desenharAbas();
  desenharApi();
  desenharPrincipal();
  // o banco do Super Tool pode mudar com a ferramenta aberta
  setInterval(async () => {
    if (S.polling) return;
    const e = await api('estado').catch(() => null);
    if (e && JSON.stringify(e.banco) !== JSON.stringify(S.e.banco)) { aplicar(e); await recarregarInicio(); S.atual.ligas = null; }
  }, 6000);
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
