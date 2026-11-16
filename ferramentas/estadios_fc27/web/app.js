// Estádios FC 27 — duplicar estádios do FC 27 e converter estádios do FIFA 16 e do PES 2021 (sempre sobre o El Grandioso).
import { api } from './comum/api.js';
import { $, $$, el, esc, aviso, modal, nota, fmtInt } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { instalarComponentes } from './comum/componentes.js';

const BASE = { id: 181, nome: 'El Grandioso' };
const S = {
  inicio: null, ambiente: null, cat: null, catErro: null, aba: 'duplicar',
  dup: { modo: 'novo', projeto: '', grupos: [], busca: '', inicioIds: 700 },
  conv: { origem: 'fifa16', pasta: '', analise: null, pronta: null, usarPronta: true, modo: 'novo', projeto: '', novoId: '', nome: '', filtro: 'todas',
          pecas: {}, opcoes: {} },
  lote: { raiz: '', achados: null, itens: [], filtro: '', inicioIds: 700, modo: 'junto', projetoModo: 'novo', projeto: '',
          opcoes: { rede: 'quadrada', colisao: 'estadio', cameras: 'ajustar', banners: 'automaticos', luzes: 'padrao', personagens: 'padrao', reservas: 'padrao' } },
  exec: null,
};

// ------------------------------------------------------------------ início
async function iniciar() {
  for (const b of $$('[data-ic]')) b.innerHTML = icone(b.dataset.ic, 15);
  $('#btn-guia').innerHTML = icone('ajuda', 16);
  $('#btn-guia').onclick = guia;
  $('#chip-ambiente').onclick = () => janelaAmbiente();
  for (const b of $$('.aba-topo')) b.onclick = () => irPara(b.dataset.aba);
  try {
    S.inicio = await api('inicio');
  } catch (e) { aviso(e.message, { tipo: 'erro' }); return; }
  $('#versao').textContent = 'v' + S.inicio.versao;
  if (!S.inicio.python) {
    const ok = await instalarComponentes({});
    if (!ok) { statusEsq('Faltam componentes (numpy, SciPy, zstandard): use "Instalar componentes".'); }
    S.inicio = await api('inicio');
  }
  renderDuplicar(); renderConverter(); renderLote(); renderResultados();
  if (S.inicio.exec?.rodando) abrirExec();
  await carregarAmbiente(true);
}

function irPara(aba) {
  S.aba = aba;
  for (const b of $$('.aba-topo')) b.classList.toggle('ativa', b.dataset.aba === aba);
  for (const p of $$('.pagina')) p.hidden = p.id !== 'pag-' + aba;
  if (aba === 'resultados') renderResultados();
}

function statusEsq(t) { $('#status-esq').textContent = t; }

async function carregarAmbiente(abrirSeFalta = false) {
  const chip = $('#chip-ambiente');
  chip.className = 'chip clicavel';
  chip.innerHTML = icone('recarregar', 12) + ' Ambiente…';
  try { S.ambiente = await api('ambiente'); } catch (e) { S.ambiente = null; chip.classList.add('erro'); chip.textContent = 'Ambiente com erro'; aviso(e.message, { tipo: 'erro' }); return; }
  const a = S.ambiente;
  chip.classList.add(a.pronto ? 'ok' : (a.ok ? 'aviso' : 'erro'));
  chip.innerHTML = icone(a.pronto ? 'check' : 'aviso', 12) + (a.pronto ? ' Ambiente pronto' : a.ok ? ' Preparar ambiente' : ' Falta algo no ambiente');
  if (a.pronto) await carregarEstadios();
  else if (abrirSeFalta) janelaAmbiente();
}

async function carregarEstadios() {
  statusEsq('Lendo o catálogo de estádios do jogo…');
  try { S.cat = await api('estadios'); S.catErro = null; } catch (e) { S.cat = null; S.catErro = e.message; }
  statusEsq(S.cat ? `${S.cat.estadios.length} estádios no jogo` : 'Catálogo indisponível');
  renderDuplicar(); renderConverter(); renderLote();
}

function janelaAmbiente() {
  const a = S.ambiente;
  const corpo = el('div', { class: 'ambiente-itens' });
  if (!a) corpo.append(nota('Não foi possível ler o ambiente. Confira se o Super Tool tem os componentes da ferramenta (numpy, SciPy e zstandard).', 'erro'));
  for (const it of a?.itens || []) {
    corpo.append(el('div', { class: 'ambiente-item' }, el('span', { class: 'ic ' + (it.ok ? 'ok' : 'falta'), html: icone(it.ok ? 'check' : 'x', 15) }),
      el('div', { class: 'txt' }, el('b', {}, it.nome), el('small', { title: it.caminho }, it.caminho ? `${it.detalhe} · ${it.caminho}` : it.detalhe))));
  }
  corpo.append(nota('Nada do FET nem do jogo vem com a ferramenta: o SDK é tirado do <b>seu</b> FIFA Editor Tool e adaptado para o .NET 8 numa cópia local, e o índice é lido do <span class="mono">fc27.cache</span> do FET. Quando o jogo atualiza, abra o FET uma vez (ele refaz o cache) e prepare de novo.', 'info'));
  const m = modal({ titulo: 'Ambiente', texto: 'O que a ferramenta usa do seu computador', corpo, largo: true, botoes: [
    { rotulo: 'Pasta do FET…', fn: async () => { await escolherPasta('fet'); return false; } },
    { rotulo: 'Pasta do jogo…', fn: async () => { await escolherPasta('jogo'); return false; } },
    { rotulo: 'Fechar' },
    { rotulo: a?.pronto ? 'Preparar de novo' : 'Preparar agora', classe: 'btn-primario', padrao: true, desabilitado: !a?.ok, fn: () => { tarefa('preparar', {}); } },
  ] });
  return m;
}

async function escolherPasta(qual) {
  try {
    const r = await api('ambiente_pasta', { qual });
    if (r.cancelado) return;
    await carregarAmbiente();
    janelaAmbiente();
  } catch (e) { aviso(e.message, { tipo: 'erro' }); }
}

function guia() {
  modal({ titulo: 'Estádios FC 27', largo: true, corpo: el('div', { style: { color: 'var(--texto-2)', lineHeight: '1.6' }, html: `
    <p><b>Duplicar estádio</b>: escolha um ou mais estádios do FC 27 e quantas cópias de cada. Cada cópia é um estádio novo, com ID e nome próprios, e tudo o que é do estádio (meshes, texturas, mundo, torcida, física, luz) ganha identidade própria, como as duplicatas 702 e 703 testadas em partida. Pode criar um projeto do zero ou acrescentar as cópias a um projeto seu do FET (o banco, o mapa de estádios e os loaders partem da versão do projeto).</p>
    <p><b>Converter FIFA 16 → FC 27</b>: a base é <b>sempre o El Grandioso (181)</b>. A ferramenta duplica o El Grandioso no ID novo e põe o estádio do FIFA 16 no lugar da arquitetura dele: modelo, texturas, telão, torcida, glares e personagens laterais (os reservas nas cadeiras do banco do estádio novo), com o gramado do FC 27 recortado até o piso do estádio e sem a pista de atletismo do El Grandioso. O caminho é o mesmo do Morumbi v3, que funcionou em partida.</p>
    <p><b>Converter PES 2021 → FC 27</b>: o mesmo caminho, com a pasta do estádio do PES 2021 (a do mod, com <span class="mono">Asset\\model\\bg\\st…</span>). A ferramenta lê os modelos, as texturas, as telas, as áreas da torcida e os brilhos das lâmpadas do PES; se os bancos de reservas estiverem do outro lado do campo, o estádio gira meia volta. Os materiais levam o relevo (mapa normal) e o brilho, a rugosidade e o metal (coeficientes) dos mapas do PES. Placas, figurantes, vidros e brilhos do PES não entram. <b>Precisa de teste em partida.</b></p>
    <p><b>Converter em lote</b>: escolha uma pasta, e a ferramenta acha nas subpastas os estádios do FIFA 16 e do PES 2021 (um pacote inteiro, como o Brasil MEGA Stadium Pack, de uma vez). Marque os que quer, ajuste o ID e o nome de cada um, e eles são convertidos um depois do outro, com a receita sugerida pela análise de cada estádio. Num projeto só (o recomendado: no FET só um projeto de estádio fica ativo por vez), cada estádio entra no projeto dos anteriores; um estádio que der erro fica de fora e os outros seguem.</p>
    <p><b>Rede do gol</b>: o El Grandioso tem a rede funda ("véu de noiva"), que só ele e mais quatro estádios do FC 27 usam. Desde a 2.1 o estádio convertido sai com a rede quadrada da maioria dos estádios (dá para voltar à do El Grandioso nas Opções).</p>
    <p><b>Câmeras</b>: todo estádio novo usa o mesmo conjunto de câmeras de replay e de cenas do jogo (torcida, comemoração, entrada), feito para arquibancadas mais longe do campo; numa arquibancada mais perto, algumas câmeras de torcida ficavam atrás ou dentro dela. Desde a 2.1 a ferramenta acha as que a arquibancada nova tapa e as move para onde a vista fica livre, num conjunto próprio do estádio, registrado como os dos estádios do jogo (dá para voltar ao conjunto do jogo nas Opções).</p>
    <p><b>Colisão em volta do campo</b>: o chão e as paredes invisíveis em que a bola bate e os jogadores param. Os do El Grandioso vão até depois da pista de atletismo, e numa arquibancada mais perto do campo os jogadores entravam nela (na comemoração, por exemplo). Desde a 2.1 a ferramenta acha a frente da arquibancada no modelo do estádio novo e põe as paredes ali (dá para voltar à do El Grandioso nas Opções).</p>
    <p><b>Banners dos times</b>: na lista de peças, marque como <b>Banner dos times</b> as faixas e bandeiras do estádio que devem dar lugar aos banners dos times. Elas saem do modelo e os banners dos times do FC 27 entram no lugar delas. No FIFA 16, a análise já marca as peças que ele deixava vazias para os banners dele. No PES 2021, que não marca nada, os banners vão sozinhos para as muretas na frente dos anéis da torcida (ou nas peças que você marcar).</p>
    <p><b>Luz da torcida à noite</b>: o pré-cálculo de luz é sempre o do El Grandioso (com o de outro estádio a partida fica carregando sem fim). As luzes da arquibancada do El Grandioso acompanham a torcida do estádio novo, para ela ficar iluminada como a do El Grandioso.</p>
    <p>A ferramenta nunca sobrescreve um projeto: o resultado é sempre um arquivo novo, conferido de volta depois de gravado (ordem das instâncias de cada EBX, referências, RES, chunks, shaders, banco).</p>` }),
    botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

// ------------------------------------------------------------------ duplicar
function idsUsados() {
  const s = new Set([...(S.cat?.ids_usados || []), ...(S.inicio?.ids_gerados || [])]);
  for (const g of S.dup.grupos) for (const c of g.copias) if (c.id) s.add(Number(c.id));
  if (S.conv.novoId) s.add(Number(S.conv.novoId));
  for (const it of S.lote.itens) if (it.marcado && it.id) s.add(Number(it.id));
  return s;
}

function proximoId(extra = new Set()) {
  const u = idsUsados();
  let x = Number(S.dup.inicioIds) || 700;
  while (u.has(x) || extra.has(x)) x++;
  return x;
}

function nomeCopia(est, k) { return `${est.nome} (Cópia${k > 0 ? ' ' + (k + 1) : ''})`.slice(0, 63); }

function adicionarGrupo(est) {
  const ja = S.dup.grupos.find((g) => g.est.id === est.id);
  if (ja) ajustarCopias(ja, ja.copias.length + 1);  // o mesmo estádio de novo = mais uma cópia
  else { const g = { est, copias: [] }; S.dup.grupos.push(g); ajustarCopias(g, 1); }
  renderDuplicar();
}

function ajustarCopias(g, n) {
  n = Math.max(1, Math.min(20, n | 0));
  while (g.copias.length > n) g.copias.pop();
  while (g.copias.length < n) {
    const usados = new Set(g.copias.map((c) => Number(c.id)));
    g.copias.push({ id: proximoId(usados), nome: nomeCopia(g.est, g.copias.length) });
  }
}

function renderDuplicar() {
  const pag = $('#pag-duplicar');
  pag.innerHTML = '';
  pag.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('h1', {}, 'Duplicar estádio'),
    el('div', { class: 'sub' }, 'Cada cópia vira um estádio novo, com ID e nome próprios, e identidade própria em tudo o que é do estádio.'))));
  // onde salvar
  const cOnde = cartao('Projeto do FET', 'Crie um projeto do zero ou acrescente as cópias a um projeto seu (o banco e o mapa de estádios partem do projeto).');
  cOnde.corpo.append(segmentado([['novo', 'Projeto novo (do zero)'], ['projeto', 'Adicionar a um projeto existente']], S.dup.modo, (v) => { S.dup.modo = v; renderDuplicar(); }));
  if (S.dup.modo === 'projeto') cOnde.corpo.append(linhaCaminho(S.dup.projeto, 'Escolha ou cole o caminho do .fifaproject', async () => {
    const r = await api('dialogo', { modo: 'abrir', tipo: 'projeto', titulo: 'Projeto do FET em que as cópias vão entrar' });
    if (!r.cancelado) { S.dup.projeto = r.caminho; renderDuplicar(); }
  }, (v) => { S.dup.projeto = v; }));
  pag.append(cOnde.el);
  // estádios do jogo
  const cLista = cartao('Estádios do FC 27', 'Clique em Adicionar para escolher um estádio; ajuste quantas cópias e o ID de cada uma abaixo.');
  if (!S.cat) {
    cLista.corpo.append(S.catErro ? nota(esc(S.catErro), 'erro') : nota('Prepare o ambiente para ver os estádios do jogo (botão Ambiente, no alto).', 'alerta'));
  } else {
    const busca = el('input', { type: 'search', placeholder: 'Buscar por nome, pasta ou ID…', value: S.dup.busca });
    busca.oninput = () => { S.dup.busca = busca.value; preencher(); };
    cLista.corpo.append(el('div', { class: 'linha-acoes', style: { marginBottom: '8px' } }, el('div', { class: 'cresce' }, busca)));
    const tb = el('tbody');
    const wrap = el('div', { class: 'lista-estadios' }, el('table', { class: 'tabela' },
      el('thead', {}, el('tr', {}, el('th', {}, 'ID'), el('th', {}, 'Estádio'), el('th', { class: 'num' }, 'Bundles'), el('th', { class: 'num' }, 'Tamanho'), el('th', {}, ''), el('th', {}, ''))), tb));
    cLista.corpo.append(wrap);
    const preencher = () => {
      tb.innerHTML = '';
      const q = S.dup.busca.trim().toLowerCase();
      const ja = new Set(S.dup.grupos.map((g) => g.est.id));
      for (const e of S.cat.estadios) {
        if (q && !(`${e.id} ${e.nome} ${e.token}`.toLowerCase().includes(q))) continue;
        const etq = [];
        if (e.confirmado) etq.push(el('span', { class: 'etiqueta verde', title: e.confirmado }, 'testado em partida'));
        if (e.base_fifa16) etq.push(el('span', { class: 'etiqueta azul' }, 'base FIFA 16'));
        tb.append(el('tr', { class: ja.has(e.id) ? 'ja' : '' }, el('td', { class: 'mono' }, String(e.id)),
          el('td', { class: 'nome-est' }, el('b', {}, e.nome), el('small', {}, e.token)), el('td', { class: 'num' }, String(e.bundles)),
          el('td', { class: 'num' }, `${fmtInt(Math.round(e.mb))} MB`), el('td', {}, el('div', { class: 'etiquetas' }, etq)),
          el('td', { class: 'encolher' }, el('button', { class: 'btn peq', onclick: () => adicionarGrupo(e), html: icone('mais', 13) + 'Adicionar' }))));
      }
      if (!tb.children.length) tb.append(el('tr', {}, el('td', { colspan: 6, class: 'vazia' }, 'Nenhum estádio com esse filtro.')));
    };
    preencher();
  }
  pag.append(cLista.el);
  // cópias
  const cCop = cartao('Cópias', 'IDs livres a partir de ' + (S.dup.inicioIds || 700) + '. O nome é o que aparece no banco (até 63 bytes).');
  const ini = el('input', { type: 'number', min: 1, max: 32767, value: S.dup.inicioIds, style: { width: '90px' } });
  ini.onchange = () => { S.dup.inicioIds = Number(ini.value) || 700; for (const g of S.dup.grupos) g.copias = []; for (const g of S.dup.grupos) ajustarCopias(g, 1); renderDuplicar(); };
  cCop.cab.append(el('label', { class: 'peq-txt mudo', style: { display: 'flex', gap: '6px', alignItems: 'center' } }, 'Primeiro ID', ini));
  cCop.corpo.classList.add('justo');
  if (!S.dup.grupos.length) cCop.corpo.append(el('div', { class: 'vazio' }, 'Nenhum estádio escolhido ainda.'));
  for (const g of S.dup.grupos) {
    const n = el('input', { type: 'number', min: 1, max: 20, value: g.copias.length });
    n.onchange = () => { ajustarCopias(g, Number(n.value)); renderDuplicar(); };
    const grupo = el('div', { class: 'copia-grupo' }, el('div', { class: 'copia-cab' }, el('b', {}, `${g.est.nome}`), el('span', { class: 'mono mudo' }, `${g.est.id} · ${g.est.token}`),
      g.est.confirmado ? el('span', { class: 'etiqueta verde' }, 'testado em partida') : null, el('span', { class: 'cresce' }),
      el('span', { class: 'qtd' }, 'Cópias', n), el('button', { class: 'btn-linha', title: 'Tirar', html: icone('x', 14), onclick: () => { S.dup.grupos.splice(S.dup.grupos.indexOf(g), 1); renderDuplicar(); } })));
    const linhas = el('div', { class: 'copia-linhas' });
    g.copias.forEach((c, k) => {
      const id = el('input', { type: 'number', min: 1, max: 32767, value: c.id, class: 'mono' });
      id.onchange = () => { c.id = Number(id.value); renderResumoDup(); };
      const nome = el('input', { type: 'text', value: c.nome, maxlength: 63 });
      nome.oninput = () => { c.nome = nome.value; };
      linhas.append(el('span', { class: 'rot' }, `Cópia ${k + 1}`), el('div', { style: { display: 'grid', gridTemplateColumns: '100px 1fr', gap: '8px' } }, id, nome));
    });
    grupo.append(linhas);
    cCop.corpo.append(grupo);
  }
  pag.append(cCop.el);
  const resumo = el('span', { class: 'resumo', id: 'resumo-dup' });
  const btn = el('button', { class: 'btn-primario grande', html: icone('copias', 16) + 'Duplicar' });
  btn.onclick = duplicar;
  pag.append(el('div', { class: 'rodape-acao' }, resumo, btn));
  renderResumoDup();
}

function renderResumoDup() {
  const r = $('#resumo-dup');
  if (!r) return;
  const todas = S.dup.grupos.flatMap((g) => g.copias);
  const ids = todas.map((c) => Number(c.id));
  const rep = ids.filter((x, i) => ids.indexOf(x) !== i);
  const usados = new Set(S.cat?.ids_usados || []);
  const oc = ids.filter((x) => usados.has(x));
  r.innerHTML = todas.length ? `${todas.length} estádio${todas.length > 1 ? 's' : ''} novo${todas.length > 1 ? 's' : ''}: <span class="mono">${ids.join(', ')}</span>`
    + (rep.length ? ` <span class="etiqueta vermelha">ID repetido: ${rep.join(', ')}</span>` : '')
    + (oc.length ? ` <span class="etiqueta vermelha">já existe no jogo: ${oc.join(', ')}</span>` : '') : 'Escolha os estádios acima.';
}

async function duplicar() {
  const copias = S.dup.grupos.flatMap((g) => g.copias.map((c) => ({ origem: g.est.id, novo_id: Number(c.id), nome: c.nome.trim() })));
  if (!copias.length) { aviso('Escolha pelo menos um estádio.', { tipo: 'aviso' }); return; }
  await tarefa('duplicar', { copias, modo: S.dup.modo, projeto_base: S.dup.modo === 'projeto' ? S.dup.projeto : null });
}

// ------------------------------------------------------------------ converter
const PAPEIS = [['opaco', 'Opaco'], ['alpha', 'Alpha'], ['telao', 'Telão'], ['grama', 'Grama'], ['banner', 'Banner dos times'], ['descartar', 'Descartar']];
const sai = (v) => v.papel === 'descartar' || v.papel === 'banner';
const ehPes = () => S.conv.origem === 'pes21';
const J = () => (ehPes() ? 'PES 2021' : 'FIFA 16');
const ORCAMENTO_MB = 33;  // os seis meshes do El Grandioso que recebem o estádio (5,5 MB cada)
const REDES_DO_GOL = [['quadrada', 'Quadrada (a da maioria dos estádios do FC 27)'], ['veu', 'Funda, "véu de noiva" (a do El Grandioso)']];
const AJUDA_REDE = 'O El Grandioso usa a rede funda (3,20 m de fundo), que só ele e mais quatro estádios do FC 27 têm; a quadrada (2,29 m) é a da maioria. Até a 2.0 todo estádio convertido saía com a rede do El Grandioso.';
const COLISOES = [['estadio', 'Paredes na frente da arquibancada (recomendado)'], ['el_grandioso', 'A do El Grandioso']];
const CAMERAS = [['ajustar', 'Mover as que a arquibancada tapa (recomendado)'], ['genericas', 'As do jogo, sem mudar']];
const AJUDA_CAMERAS = 'Câmeras de replay e de cenas (torcida, comemoração, entrada). O jogo usa o mesmo conjunto em todo estádio novo, feito para arquibancadas mais longe do campo. Recomendado: a ferramenta acha as que a arquibancada nova tapa e as move para onde a vista fica livre, num conjunto próprio do estádio. Até a 2.0 ficavam as do jogo, e algumas câmeras de torcida apareciam atrás ou dentro da arquibancada.';
const AJUDA_COLISAO = 'O chão e as paredes invisíveis em volta do campo, em que a bola bate e os jogadores param. Recomendado: a ferramenta acha a frente da arquibancada no modelo do estádio novo e põe as paredes ali. A do El Grandioso vai até depois da pista de atletismo: numa arquibancada mais perto do campo, os jogadores entram nela (até a 2.0 era sempre assim).';

function trocarOrigem(o) {
  if (S.conv.origem === o) return;
  Object.assign(S.conv, { origem: o, pasta: '', analise: null, pronta: null, usarPronta: true, pecas: {}, opcoes: {}, filtro: 'todas' });
  renderConverter();
}

// Geometria que as peças que ficam ocupam nos meshes do El Grandioso (MB). No PES cada peça tem um lado só, a não ser
// as de dois lados (sem "1 lado") e as alpha.
function geometriaEstimada() {
  const c = S.conv;
  let b = 0;
  for (const p of c.analise?.pecas || []) {
    const v = c.pecas[p.prim];
    if (!v || sai(v) || v.papel === 'telao') continue;
    const lados = v.papel === 'alpha' || c.opcoes.faces === 'double' || !v.umLado ? 2 : 1;
    b += lados * (p.vertices * (v.papel === 'alpha' ? 40 : 36) + (p.triangulos || 0) * 6);
  }
  return b / 1048576;
}

function receitaBase() {
  return S.conv.usarPronta && S.conv.pronta ? S.conv.pronta : S.conv.analise?.receita;
}

function carregarPecas() {
  const an = S.conv.analise;
  const r = receitaBase() || {};
  const desc = r.descartar || {}, telao = new Set(r.telao || []), grama = new Set(r.grama || []), umLado = new Set(r.um_lado || []);
  const pista = new Set(r.pista || []), chao = r.chao || {}, papel = r.papel || {};
  S.conv.pecas = {};
  for (const p of an.pecas) {
    let pp = desc[p.prim] !== undefined ? 'descartar' : telao.has(p.prim) ? 'telao' : grama.has(p.prim) ? 'grama' : papel[p.prim] === 'banner' ? 'banner'
      : (papel[p.prim] === 'alpha' || (papel[p.prim] === undefined && p.shader === 'diffusealpha')) ? 'alpha' : 'opaco';
    S.conv.pecas[p.prim] = { papel: pp, motivo: desc[p.prim] ?? p.motivo, dy: chao[p.prim] ?? '', umLado: umLado.has(p.prim), piso: pista.has(p.prim) };
  }
  const o = S.conv.opcoes = {
    faces: r.faces || 'view', max_vertices: r.max_vertices || 60000,
    giro: r.giro ?? 0,
    recorte: !!r.recorte_bancos, recorte_z: r.recorte_bancos?.z ?? -37.8, recorte_x: r.recorte_bancos?.x ?? 30,
    placas: r.placas_madeira_bancos || 'manter', cadeiras: r.torcida?.cadeiras || 'fifa16', cor: '#c81e1e',
    lado_casa: r.torcida?.lado_casa || '-x', tier2: r.torcida?.tier2_acima_de ?? 14,
    ajuste: r.ajuste_automatico ?? true, personagens: r.personagens || 'ajustar',
    reservas: r.reservas || 'cadeiras', luzes: r.luzes_torcida || (ehPes() ? 'cobrir' : 'acompanhar'),
    setor: r.torcida?.setor_pes || 'comum', banners: r.banners || 'automaticos', rede: r.rede_gol || 'quadrada',
    colisao: r.colisao || 'estadio', cameras: r.cameras || 'ajustar',
  };
  if (o.cadeiras !== 'fifa16') { o.cor = o.cadeiras; o.cadeiras = 'cor'; }
}

function receitaDaTela() {
  const r = {};
  const P = S.conv.pecas;
  r.descartar = {}; r.papel = {}; r.telao = []; r.grama = []; r.chao = {}; r.um_lado = []; r.pista = [];
  for (const [k, v] of Object.entries(P)) {
    const i = Number(k);
    if (v.papel === 'descartar') r.descartar[k] = v.motivo || 'descartada na conversão';
    else if (v.papel === 'telao') r.telao.push(i);
    else if (v.papel === 'grama') r.grama.push(i);
    else r.papel[k] = v.papel;
    if (v.dy !== '' && v.dy !== null && Number.isFinite(Number(v.dy))) r.chao[k] = Number(v.dy);
    if (v.umLado) r.um_lado.push(i);
    if (v.piso) r.pista.push(i);
  }
  const o = S.conv.opcoes;
  r.faces = o.faces; r.max_vertices = Number(o.max_vertices) || 60000;
  r.recorte_bancos = o.recorte ? { z: Number(o.recorte_z), x: Number(o.recorte_x) } : null;
  r.placas_madeira_bancos = o.placas;
  r.torcida = { cadeiras: o.cadeiras === 'cor' ? o.cor : 'fifa16', lado_casa: o.lado_casa, tier2_acima_de: Number(o.tier2) };
  if (ehPes()) r.torcida.setor_pes = o.setor;
  if (ehPes()) r.banners = o.banners;
  r.ajuste_automatico = !!o.ajuste;
  r.personagens = o.personagens;
  r.reservas = o.reservas;
  r.luzes_torcida = o.luzes;
  r.rede_gol = o.rede;
  r.colisao = o.colisao;
  r.cameras = o.cameras;
  r.luz = BASE.id;
  if (ehPes()) r.giro = Number(o.giro) || 0;
  const b = receitaBase() || {};
  for (const k of ['prefixo', 'pasta_nome', 'identidade', 'sombra_mesclada', 'tom_grama', 'vista', 'deslocamento_alpha']) if (b[k] !== undefined) r[k] = b[k];
  if (r.chao && b.chao && JSON.stringify(r.chao) === JSON.stringify(Object.fromEntries(Object.entries(b.chao).map(([k, v]) => [k, Number(v)])))) r.chao = b.chao;
  return r;
}

async function analisar(pasta = null) {
  statusEsq(`Lendo o estádio do ${J()}…`);
  try {
    const an = await api(ehPes() ? 'analisarpes' : 'analisar16', pasta ? { pasta } : {});
    if (an.cancelado) { statusEsq('Pronto'); return; }
    S.conv.analise = an; S.conv.pasta = an.pasta; S.conv.pronta = an.receita_pronta; S.conv.usarPronta = !!an.receita_pronta;
    if (!S.conv.nome) S.conv.nome = an.receita_pronta?.nome || '';
    if (!S.conv.novoId) S.conv.novoId = proximoId();
    carregarPecas();
    statusEsq(`Estádio ${an.fifa16_id} do ${J()}: ${an.resumo.pecas} peças`);
  } catch (e) { aviso(e.message, { tipo: 'erro' }); statusEsq('Pronto'); }
  renderConverter();
}

function renderConverter() {
  const pag = $('#pag-converter');
  pag.innerHTML = '';
  const c = S.conv;
  const pes = ehPes();
  pag.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('h1', {}, `Converter estádio do ${J()} para o FC 27`),
    el('div', { class: 'sub' }, `Modelo, texturas, telão, torcida, glares e personagens laterais do ${J()} num estádio novo do FC 27.`)),
    segmentado([['fifa16', 'FIFA 16'], ['pes21', 'PES 2021']], c.origem, trocarOrigem)));
  pag.append(el('div', { class: 'faixa-base' }, el('span', { html: icone('estadio', 30) }),
    el('div', {}, el('b', {}, `Base fixa: ${BASE.nome} (estádio ${BASE.id} do FC 27)`),
      el('p', {}, pes
        ? 'Toda conversão é feita sobre uma duplicata completa do El Grandioso no ID novo: o estádio do PES 2021 entra no lugar da arquitetura dele, pelo mesmo caminho da conversão do FIFA 16 que funcionou em partida (Morumbi v3). Os estádios do PES 2021 têm todos o mesmo formato. Não há como escolher outra base, para evitar erros.'
        : 'Toda conversão é feita sobre uma duplicata completa do El Grandioso no ID novo: o estádio do FIFA 16 entra no lugar da arquitetura dele. Os estádios do FIFA 16 têm todos o mesmo formato, e com a base fixa também, o caminho é sempre o mesmo que funcionou em partida (Morumbi v3). Não há como escolher outra base, para evitar erros.')),
    pes ? el('span', { class: 'etiqueta amarela' }, 'precisa de teste em partida') : el('span', { class: 'etiqueta verde' }, 'testado em partida')));
  // pasta do estádio de origem
  const c1 = pes
    ? cartao('Estádio do PES 2021', 'A pasta do estádio (a do mod, com Asset\\model\\bg\\st<número>: modelos, texturas, telão, áreas da torcida e brilhos das lâmpadas).')
    : cartao('Estádio do FIFA 16', 'A pasta do estádio (com data\\sceneassets: stadium_<id>.rx3, texturas de dia e noite, torcida e glares).');
  c1.corpo.append(linhaCaminho(c.pasta, `Escolha ou cole a pasta do estádio do ${J()}`, () => analisar(), (v) => analisar(v)));
  if (c.analise) {
    const an = c.analise;
    const est = (n, t) => el('div', { class: 'estatistica' }, el('b', {}, n), el('span', {}, t));
    c1.corpo.append(el('div', { class: 'resumo16', style: { marginTop: '10px' } },
      est(String(an.fifa16_id), pes ? 'estádio no PES 2021' : 'ID no FIFA 16'), est(fmtInt(an.resumo.pecas), 'peças no modelo'),
      est(fmtInt(Object.values(c.pecas).filter(sai).length), 'peças que saem'),
      est(an.torcida ? fmtInt(an.torcida.lugares) : '—', 'lugares da torcida'), est(String(Math.max(0, ...Object.values(an.glares || { x: 0 }))), 'lâmpadas (glares)'),
      pes ? est(an.giro === 180 ? '+Z' : '−Z', 'lado dos bancos no PES')
        : est(fmtInt(Object.values(an.localizadores || {}).reduce((a, b) => a + b, 0)), 'marcadores (slc…)')));
    if (c.pronta) {
      const t = el('div', { style: { marginTop: '10px' } });
      t.append(segmentado([['pronta', 'Receita guardada: ' + (c.pronta.nome || 'estádio ' + an.fifa16_id) + ' (a da conversão testada)'], ['auto', 'Receita sugerida pela análise']],
        c.usarPronta ? 'pronta' : 'auto', (v) => { c.usarPronta = v === 'pronta'; carregarPecas(); renderConverter(); }));
      c1.corpo.append(t);
    } else if (pes) {
      c1.corpo.append(el('div', { style: { marginTop: '10px' } }, nota('Receita sugerida pela análise: os materiais do PES dizem o que sai (figurantes e equipamentos de transmissão, vidros e brilhos), o que é telão, grama em volta do campo, opaco ou alpha. Os banners dos times do FC 27 vão sozinhos para as frentes dos anéis da torcida; se o estádio tiver faixas próprias que devem dar lugar a eles, marque-as como Banner dos times na lista de peças abaixo.', 'info')));
      if (an.giro === 180) c1.corpo.append(nota(`Os bancos de reservas deste estádio ficam em +Z (${an.bancos.cadeiras_em_mais_z} cadeiras de banco achadas, contra ${an.bancos.cadeiras_em_menos_z} do outro lado): o estádio gira meia volta, porque o FC 27 tem os bancos em −Z. Dá para mudar em "Lado dos bancos", nas Opções.`, 'info'));
      if (!an.existe?.torcida) c1.corpo.append(nota('Sem audiarea.bin: a torcida do El Grandioso fica.', 'alerta'));
      else if (!an.torcida?.cores_das_cadeiras) c1.corpo.append(nota('Sem audi\\sourceimages\\au_seat.png: as cadeiras da torcida ficam cinza (ou escolha uma cor nas Opções).', 'alerta'));
      for (const a of [...(an.torcida?.avisos || []), ...(an.avisos || [])]) c1.corpo.append(nota(esc(a), 'alerta'));
      if (!Object.keys(an.glares || {}).length) c1.corpo.append(nota('Sem brilhos de lâmpadas no PES (effect_st…_df/_nf.fpk): os glares do El Grandioso ficam.', 'alerta'));
      c1.corpo.append(nota('O PES não tem marcadores de personagens laterais: gandulas, fotógrafos e técnicos partem das posições do El Grandioso e são conferidos contra o estádio novo (veja "Personagens laterais" nas Opções).', 'info'));
    } else c1.corpo.append(el('div', { style: { marginTop: '10px' } }, nota('Receita sugerida pela análise: as camadas do FIFA 16 dizem o que sai (placas, gramado, céu e relógio que o FIFA 16 preenchia na hora do jogo) e onde entram os banners dos times. Confira a lista de peças abaixo e marque como Banner dos times as faixas e bandeiras do estádio que devem dar lugar a eles.', 'info')));
    if (!pes && !an.existe?.torcida) c1.corpo.append(nota('Sem crowd_<id>_1.dat: a torcida do El Grandioso fica.', 'alerta'));
    if (!pes && !Object.keys(an.localizadores || {}).some((k) => k.startsWith('slc_'))) c1.corpo.append(nota('Sem marcadores slc: gandulas, fotógrafos e técnicos partem das posições do El Grandioso (veja "Personagens laterais" nas Opções).', 'alerta'));
  }
  pag.append(c1.el);
  // estádio novo
  const c2 = cartao('Estádio novo no FC 27', 'ID livre e o nome que aparece no jogo (banco).');
  const id = el('input', { type: 'number', min: 1, max: 32767, value: c.novoId, class: 'mono' });
  id.onchange = () => { c.novoId = Number(id.value); };
  const nome = el('input', { type: 'text', value: c.nome, maxlength: 63, placeholder: 'Ex.: Estádio do Morumbi' });
  nome.oninput = () => { c.nome = nome.value; };
  c2.corpo.append(el('div', { class: 'grade2' }, campo2('ID novo', id, 'Livre no jogo e no projeto.'), campo2('Nome', nome, 'Até 63 bytes.')));
  c2.corpo.append(el('div', { style: { marginTop: '12px' } }, segmentado([['novo', 'Projeto novo (do zero)'], ['projeto', 'Adicionar a um projeto existente']], c.modo, (v) => { c.modo = v; renderConverter(); })));
  if (c.modo === 'projeto') c2.corpo.append(linhaCaminho(c.projeto, 'Escolha ou cole o caminho do .fifaproject', async () => {
    const r = await api('dialogo', { modo: 'abrir', tipo: 'projeto', titulo: 'Projeto do FET em que o estádio convertido vai entrar' });
    if (!r.cancelado) { c.projeto = r.caminho; renderConverter(); }
  }, (v) => { c.projeto = v; }));
  pag.append(c2.el);
  if (c.analise) { pag.append(cartaoPecas().el); pag.append(cartaoOpcoes().el); }
  const btn = el('button', { class: 'btn-primario grande', html: icone('converter', 16) + 'Converter', disabled: !c.analise });
  btn.onclick = converter;
  pag.append(el('div', { class: 'rodape-acao' }, el('span', { class: 'resumo' }, c.analise ? `${J()} ${c.analise.fifa16_id} → FC 27 ${c.novoId || '?'} sobre o ${BASE.nome}` : `Escolha a pasta do estádio do ${J()}.`), btn));
}

function cartaoPecas() {
  const c = S.conv, an = c.analise;
  const cp = ehPes()
    ? cartao('Peças do PES 2021', 'O papel de cada peça (malha dos modelos do estádio e do telão). 1 lado: só o lado das normais, como o PES desenha (desmarcado nas malhas de dois lados do PES). Chão: quanto a peça sobe no nível do piso. Piso: as peças que marcam até onde vai o gramado do FC 27.')
    : cartao('Peças do FIFA 16', 'O papel de cada peça (primitiva do RX3). Chão: quanto a peça sobe no nível do piso (o FIFA 16 contava com a ordem de desenho; o FC 27 precisa de alturas diferentes). Piso: as peças que marcam até onde vai o gramado do FC 27.');
  const medidor = el('div', { class: 'medidor-geometria' });
  const medir = () => {
    if (!ehPes()) return;
    const mb = geometriaEstimada();
    medidor.className = 'medidor-geometria' + (mb > ORCAMENTO_MB ? ' passou' : mb > 0.93 * ORCAMENTO_MB ? ' justo' : '');
    medidor.textContent = `Geometria das peças que ficam: cerca de ${mb.toFixed(1).replace('.', ',')} de ${ORCAMENTO_MB} MB que os meshes do El Grandioso comportam`
      + (mb > ORCAMENTO_MB ? ': descarte peças que não aparecem ou marque "1 lado" nas que só são vistas de frente.' : '.');
  };
  const filtro = segmentado([['todas', 'Todas'], ['ficam', 'Ficam'], ['saem', 'Saem'], ['chao', 'No chão']], c.filtro, (v) => { c.filtro = v; renderConverter(); });
  cp.cab.append(filtro);
  cp.corpo.classList.add('justo');
  const tb = el('tbody');
  for (const p of an.pecas) {
    const v = c.pecas[p.prim];
    if (c.filtro === 'ficam' && sai(v)) continue;
    if (c.filtro === 'saem' && !sai(v)) continue;
    if (c.filtro === 'chao' && (v.dy === '' || v.dy === null)) continue;
    const sel = el('select', {}, PAPEIS.map(([k, t]) => el('option', { value: k, selected: v.papel === k }, t)));
    sel.onchange = () => { v.papel = sel.value; tr.classList.toggle('descartada', v.papel === 'descartar'); medir(); };
    const dy = el('input', { type: 'number', step: '0.002', class: 'dy mono', value: v.dy, placeholder: '—' });
    dy.onchange = () => { v.dy = dy.value === '' ? '' : Number(dy.value); };
    const um = el('input', { type: 'checkbox', checked: v.umLado, title: 'Só a frente (sem o verso)' });
    um.onchange = () => { v.umLado = um.checked; medir(); };
    const piso = el('input', { type: 'checkbox', checked: v.piso, title: 'Esta peça marca até onde vai o gramado do FC 27' });
    piso.onchange = () => { v.piso = piso.checked; };
    const img = p.miniatura ? el('img', { src: 'imagem?arq=' + encodeURIComponent(p.miniatura), loading: 'lazy', title: p.textura }) : el('div', { class: 'sem-img', title: p.textura_no_arquivo ? '' : 'sem textura no arquivo' });
    const tr = el('tr', { class: v.papel === 'descartar' ? 'descartada' : '' }, el('td', { class: 'mini' }, img), el('td', { class: 'mono' }, String(p.prim)),
      el('td', {}, el('div', { title: p.nome || '' }, ehPes() && p.nome ? `${p.camada} · ${p.nome}` : (p.camada || '—')), el('div', { class: 'mono mudo', style: { fontSize: '11px' } }, p.shader)),
      el('td', { class: 'num mono' }, fmtInt(p.vertices)), el('td', { class: 'papel' }, sel), el('td', {}, dy), el('td', { class: 'encolher', style: { textAlign: 'center' } }, um),
      el('td', { class: 'encolher', style: { textAlign: 'center' } }, piso), el('td', {}, el('div', { class: 'motivo', title: v.motivo }, v.papel === 'descartar' ? v.motivo : p.textura)));
    tb.append(tr);
  }
  if (ehPes()) { medir(); cp.corpo.append(medidor); }
  cp.corpo.append(el('div', { class: 'tabela-pecas' }, el('table', { class: 'tabela' }, el('thead', {}, el('tr', {}, el('th', {}, ''), el('th', {}, '#'), el('th', {}, ehPes() ? 'Modelo · malha / shader' : 'Camada / shader'),
    el('th', { class: 'num' }, 'Vértices'), el('th', {}, 'Papel'), el('th', {}, 'Chão (m)'), el('th', {}, '1 lado'), el('th', {}, 'Piso'), el('th', {}, 'Textura / motivo'))), tb)));
  return cp;
}

function cartaoOpcoes() {
  const o = S.conv.opcoes;
  const co = cartao('Opções', ehPes() ? 'Os padrões são os da conversão do FIFA 16 testada em partida, com o que a análise do PES sugere.' : 'Os padrões são os da conversão testada em partida.');
  const faces = segmentado([['view', 'Vista do campo'], ['double', 'Dois lados']], o.faces, (v) => { o.faces = v; });
  const maxv = el('input', { type: 'number', min: 10000, max: 65000, step: 1000, value: o.max_vertices });
  maxv.onchange = () => { o.max_vertices = Number(maxv.value); };
  const recorte = el('input', { type: 'checkbox', checked: o.recorte });
  const rz = el('input', { type: 'number', step: '0.1', value: o.recorte_z, style: { width: '80px' } });
  const rx = el('input', { type: 'number', step: '0.5', value: o.recorte_x, style: { width: '80px' } });
  recorte.onchange = () => { o.recorte = recorte.checked; };
  rz.onchange = () => { o.recorte_z = Number(rz.value); };
  rx.onchange = () => { o.recorte_x = Number(rx.value); };
  const placas = el('select', {}, el('option', { value: 'manter', selected: o.placas === 'manter' }, 'Manter no lugar'), el('option', { value: 'abaixo_do_piso', selected: o.placas === 'abaixo_do_piso' }, 'Esconder (10 m abaixo do piso)'));
  placas.onchange = () => { o.placas = placas.value; };
  const pes = ehPes();
  const cad = segmentado([['fifa16', pes ? 'Cores do PES (au_seat.png)' : 'Cores do FIFA 16'], ['cor', 'Cor única']], o.cadeiras, (v) => { o.cadeiras = v; cor.disabled = v !== 'cor'; });
  const cor = el('input', { type: 'color', value: o.cor, disabled: o.cadeiras !== 'cor', style: { width: '48px', height: '30px', padding: '0', border: '0', background: 'none' } });
  cor.oninput = () => { o.cor = cor.value; };
  const lado = el('select', {}, el('option', { value: '-x', selected: o.lado_casa === '-x' }, 'Casa em −X (como o El Grandioso)'), el('option', { value: '+x', selected: o.lado_casa === '+x' }, 'Casa em +X (inverter)'));
  lado.onchange = () => { o.lado_casa = lado.value; };
  const tier = el('input', { type: 'number', step: '0.5', value: o.tier2 });
  tier.onchange = () => { o.tier2 = Number(tier.value); };
  const ajuste = el('input', { type: 'checkbox', checked: o.ajuste });
  ajuste.onchange = () => { o.ajuste = ajuste.checked; };
  const pers = el('select', {}, [['ajustar', 'Ajustar ao estádio (recomendado)'], ['esconder', 'Esconder (ficam só os técnicos)'], ['fifa16', 'Só os marcadores do FIFA 16']]
    .filter(([k]) => !pes || k !== 'fifa16').map(([k, t]) => el('option', { value: k, selected: o.personagens === k }, t)));
  pers.onchange = () => { o.personagens = pers.value; };
  const res = el('select', {}, [['cadeiras', 'Nas cadeiras do banco (recomendado)'], ['marcadores', 'Nos marcadores do FIFA 16'], ['esconder', 'Esconder']]
    .filter(([k]) => !pes || k !== 'marcadores').map(([k, t]) => el('option', { value: k, selected: o.reservas === k }, t)));
  res.onchange = () => { o.reservas = res.value; };
  const luzes = el('select', {}, (pes
    ? [['cobrir', 'Cobrem toda a torcida (recomendado)'], ['acompanhar', 'Acompanham a torcida'], ['manter', 'Ficam onde estão no El Grandioso']]
    : [['acompanhar', 'Acompanham a torcida (recomendado)'], ['cobrir', 'Cobrem toda a torcida (estádios grandes)'], ['manter', 'Ficam onde estão no El Grandioso']])
    .map(([k, t]) => el('option', { value: k, selected: o.luzes === k }, t)));
  luzes.onchange = () => { o.luzes = luzes.value; };
  const an = S.conv.analise;
  const setor = el('select', {}, [['comum', 'Torcida comum (recomendado)'], ['visitantes', 'Bloco de visitantes']]
    .map(([k, t]) => el('option', { value: k, selected: o.setor === k }, t)));
  setor.onchange = () => { o.setor = setor.value; };
  const bann = el('select', {}, [['automaticos', 'Nas frentes dos anéis da torcida (recomendado)'], ['nenhum', 'Sem banners dos times']]
    .map(([k, t]) => el('option', { value: k, selected: o.banners === k }, t)));
  bann.onchange = () => { o.banners = bann.value; };
  const giro = el('select', {}, [[0, 'Não girar (bancos em −Z no PES)'], [180, 'Girar meia volta (bancos em +Z no PES)']]
    .map(([k, t]) => el('option', { value: k, selected: Number(o.giro) === k }, t)));
  giro.onchange = () => { o.giro = Number(giro.value); };
  const rede = el('select', {}, REDES_DO_GOL.map(([k, t]) => el('option', { value: k, selected: o.rede === k }, t)));
  rede.onchange = () => { o.rede = rede.value; };
  const colisao = el('select', {}, COLISOES.map(([k, t]) => el('option', { value: k, selected: o.colisao === k }, t)));
  colisao.onchange = () => { o.colisao = colisao.value; };
  const cams = el('select', {}, CAMERAS.map(([k, t]) => el('option', { value: k, selected: o.cameras === k }, t)));
  cams.onchange = () => { o.cameras = cams.value; };
  co.corpo.append(el('div', { class: 'grade2' },
    pes ? campo2('Lado dos bancos', giro, `O FC 27 e o El Grandioso têm os bancos de reservas em −Z. A análise achou ${an?.bancos?.cadeiras_em_mais_z ?? 0} cadeiras de banco em +Z e ${an?.bancos?.cadeiras_em_menos_z ?? 0} em −Z, e sugeriu ${an?.giro === 180 ? 'girar' : 'não girar'}.`) : null,
    campo2('Faces', faces, pes
      ? 'Vista do campo (recomendado): cada face entra pelo lado das normais, como o PES desenha; nas peças sem "1 lado", o verso entra onde é visto do campo. Dois lados: tudo com frente e verso (dobra a geometria; um estádio do PES raramente cabe assim).'
      : 'Vista do campo (recomendado): cada face entra pelo lado das normais do FIFA 16, e o verso só onde é visto do campo. Dois lados: tudo com frente e verso, como o FIFA 16 desenhava.'),
    campo2('Máximo de vértices por peça', maxv, 'Acima disso a peça é dividida (índices de 16 bits, como os meshes do FC 27).'),
    campo2('Ajuste automático de tamanho', el('label', { class: 'linha-acoes' }, ajuste, 'Repartir materiais grandes entre os meshes'), pes
      ? 'Um material maior que um mesh do El Grandioso (5,5 MB) é repartido entre vários, e as peças ficam menores se for preciso para tudo caber.'
      : 'Um material maior que um mesh do El Grandioso (5,5 MB) é repartido entre vários. Estádios que cabem sem isso saem iguais.'),
    campo2('Personagens laterais', pers, pes
      ? 'Gandulas, fotógrafos, câmeras, policiais e seguranças. Ajustar: partem das posições do El Grandioso; os que ficariam dentro da arquibancada vão para o lugar livre mais perto do campo, ou saem de vista. Esconder: todos menos técnicos e auxiliares saem de vista.'
      : 'Gandulas, fotógrafos, câmeras, policiais e seguranças. Ajustar: os marcadores do FIFA 16 onde existem; os que ficariam dentro da arquibancada vão para o lugar livre mais perto do campo, ou saem de vista. Esconder: todos menos técnicos e auxiliares saem de vista.'),
    campo2('Reservas no banco', res, pes
      ? 'Cadeiras: os reservas sentam nas cadeiras do banco achadas no modelo do PES, uma sim, uma não, a partir do meio. Esconder: saem de vista.'
      : 'Cadeiras: os reservas sentam nas cadeiras do banco achadas no modelo do FIFA 16, uma sim, uma não, a partir do meio. Marcadores: nos marcadores do FIFA 16, que muitas vezes não batem com as cadeiras. Esconder: saem de vista.'),
    campo2('Luzes da torcida à noite', luzes, `Cobrem: as luzes da arquibancada do El Grandioso são redistribuídas por toda a torcida do ${J()} e apontadas para ela, para os anéis de cima não ficarem no escuro. Acompanham: cada luz vai para o trecho equivalente da torcida nova, sem girar (o que foi testado no FIFA 16); numa torcida maior ou mais alta que a do El Grandioso, os anéis de cima ficam escuros.`),
    campo2('Recuo do gramado no lado dos bancos', el('div', { class: 'linha-acoes' }, recorte, 'z ≥', rz, '|x| <', rx), 'Para bancos rebaixados (Morumbi: z −37,8 m, |x| < 30 m).'),
    campo2('Placas baixas de madeira do El Grandioso (lado dos bancos)', placas, 'Esconda se cruzarem os bancos do estádio novo.'),
    campo2('Cadeiras da torcida', el('div', { class: 'linha-acoes' }, cad, cor), ''),
    campo2('Rede do gol', rede, AJUDA_REDE),
    campo2('Colisão em volta do campo', colisao, AJUDA_COLISAO),
    campo2('Câmeras', cams, AJUDA_CAMERAS),
    pes ? campo2('Banners dos times', bann, 'O PES não marca onde ficam os banners dos times. Automático: eles vão para as muretas na frente dos anéis da torcida (faces viradas para o campo, com a torcida logo atrás e acima, acima das placas de publicidade e fora do meio do lado dos bancos), em fileiras de banners de ~2 m de altura, como no El Grandioso. Peças marcadas como Banner dos times na lista têm prioridade.') : null,
    pes ? campo2('Setor marcado no PES', setor, `O PES marca à parte as áreas da torcida com o valor 5 (${fmtInt(an?.torcida?.visitantes_areas ?? 0)} áreas neste estádio; no Camp Nou, o anel inferior atrás de um gol). Torcida comum: elas enchem como o resto. Bloco de visitantes: vira o setor dos visitantes do FC 27, que pode ficar vazio na partida.`) : null,
    campo2('Torcida da casa', lado, pes ? 'O El Grandioso põe a casa em −X. A organizada da casa fica no anel inferior atrás do gol da casa.' : 'O FIFA 16 e o El Grandioso põem a casa em −X.'),
    campo2('Anel superior da torcida acima de (m)', tier, 'Lugares mais altos que isso contam como anel superior.')));
  return co;
}

async function converter() {
  const c = S.conv;
  if (!c.analise) return;
  if (!c.nome.trim()) { aviso('Dê um nome ao estádio novo.', { tipo: 'aviso' }); return; }
  if (!c.novoId) { aviso('Escolha o ID novo.', { tipo: 'aviso' }); return; }
  await tarefa('converter', { origem: c.origem, [ehPes() ? 'pasta_pes' : 'pasta16']: c.pasta, novo_id: Number(c.novoId), nome: c.nome.trim(), receita: receitaDaTela(), modo: c.modo,
    projeto_base: c.modo === 'projeto' ? c.projeto : null });
}

// ------------------------------------------------------------------ converter em lote
const MIN_POR_ESTADIO = 7;    // minutos de uma conversão (Camp Nou: 6 a 7)
const MB_POR_ESTADIO = 180;   // quanto um estádio convertido ocupa no projeto (Camp Nou: 183 MB)

function idLivreLote() {
  const u = idsUsados();
  let x = Number(S.lote.inicioIds) || 700;
  while (u.has(x)) x++;
  return x;
}

function numerarLote() {
  for (const it of S.lote.itens) it.id = '';
  for (const it of S.lote.itens) if (it.marcado) it.id = idLivreLote();
}

async function procurarLote(pasta = null) {
  statusEsq('Procurando estádios nas subpastas…');
  const L = S.lote;
  try {
    const r = await api('procurar', pasta ? { pasta } : {});
    if (r.cancelado) { statusEsq('Pronto'); return; }
    L.raiz = r.raiz; L.achados = r; L.filtro = '';
    L.itens = r.estadios.map((e) => ({ ...e, marcado: !e.problema && e.sugerido !== false, id: '', nomeNovo: e.nome }));
    numerarLote();
    const n = r.estadios.length;
    statusEsq(`${n} estádio${n === 1 ? '' : 's'} achado${n === 1 ? '' : 's'} em ${r.raiz}`);
  } catch (e) { aviso(e.message, { tipo: 'erro' }); statusEsq('Pronto'); }
  renderLote();
}

function renderLote() {
  const pag = $('#pag-lote');
  if (!pag) return;
  pag.innerHTML = '';
  const L = S.lote;
  pag.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('h1', {}, 'Converter em lote'),
    el('div', { class: 'sub' }, 'Vários estádios do FIFA 16 e do PES 2021 de uma vez, um depois do outro, cada um sobre uma duplicata do El Grandioso e com a receita sugerida pela análise dele.'))));
  const c1 = cartao('Estádios de origem', 'Escolha uma pasta: a ferramenta procura nas subpastas os estádios do FIFA 16 (data\\sceneassets\\stadium) e do PES 2021 (Asset\\model\\bg\\st<número>). Um pacote com vários estádios, como o Brasil MEGA Stadium Pack, entra inteiro.');
  c1.corpo.append(linhaCaminho(L.raiz, 'Escolha ou cole a pasta com os estádios', () => procurarLote(), (v) => procurarLote(v)));
  const a = L.achados;
  if (a) {
    if (!a.estadios.length) c1.corpo.append(nota('Nenhum estádio do FIFA 16 ou do PES 2021 nessa pasta.', 'alerta'));
    if (a.total_compactados) {
      const n = a.total_compactados;
      const z = nota(`${n} arquivo${n > 1 ? 's' : ''} compactado${n > 1 ? 's' : ''} (.rar, .zip, .7z) fic${n > 1 ? 'aram' : 'ou'} de fora: extraia antes para a ferramenta achar os estádios ${n > 1 ? 'deles' : 'dele'}.`, 'info');
      z.title = a.compactados.join('\n');
      c1.corpo.append(z);
    }
  }
  if (a && a.estadios.length) {
    const busca = el('input', { type: 'search', placeholder: 'Filtrar por nome ou pasta…', value: L.filtro });
    const ini = el('input', { type: 'number', min: 1, max: 32767, value: L.inicioIds, style: { width: '90px' } });
    const visiveis = () => {
      const q = L.filtro.trim().toLowerCase();
      return L.itens.filter((it) => !q || `${it.nomeNovo} ${it.rotulo} ${it.fonte_id}`.toLowerCase().includes(q));
    };
    const marcar = (v) => {
      for (const it of visiveis()) if (!it.problema) { it.marcado = v; if (v && !it.id) it.id = idLivreLote(); }
      preencher(); renderResumoLote();
    };
    c1.corpo.append(el('div', { class: 'linha-acoes', style: { margin: '10px 0 8px' } }, el('div', { class: 'cresce' }, busca),
      el('button', { class: 'btn peq', onclick: () => marcar(true) }, 'Marcar todos'), el('button', { class: 'btn peq', onclick: () => marcar(false) }, 'Desmarcar todos'),
      el('label', { class: 'peq-txt mudo', style: { display: 'flex', gap: '6px', alignItems: 'center' } }, 'Primeiro ID', ini),
      el('button', { class: 'btn peq', title: 'Dá IDs livres em sequência aos estádios marcados, a partir do primeiro ID', onclick: () => { L.inicioIds = Number(ini.value) || 700; numerarLote(); preencher(); renderResumoLote(); } }, 'Numerar')));
    const tb = el('tbody');
    c1.corpo.append(el('div', { class: 'lista-estadios lista-lote' }, el('table', { class: 'tabela' },
      el('thead', {}, el('tr', {}, el('th', {}, ''), el('th', {}, 'Jogo'), el('th', {}, 'Na origem'), el('th', {}, 'Pasta'), el('th', {}, 'ID novo'), el('th', {}, 'Nome no FC 27'))), tb)));
    const linha = (it) => {
      const ck = el('input', { type: 'checkbox', checked: it.marcado, disabled: !!it.problema });
      const id = el('input', { type: 'number', min: 1, max: 32767, value: it.id, class: 'mono', disabled: !it.marcado });
      const nome = el('input', { type: 'text', value: it.nomeNovo, maxlength: 63, disabled: !it.marcado });
      const tr = el('tr', { class: it.marcado ? '' : 'desmarcado' }, el('td', { class: 'encolher' }, ck),
        el('td', { class: 'encolher' }, el('span', { class: 'etiqueta ' + (it.origem === 'pes21' ? 'azul' : 'amarela') }, it.origem === 'pes21' ? 'PES 2021' : 'FIFA 16')),
        el('td', { class: 'mono encolher' }, String(it.fonte_id)),
        el('td', { class: 'pasta-lote' }, el('div', { class: 'mono', title: it.pasta }, it.rotulo),
          it.problema ? el('div', { class: 'problema' }, it.problema) : it.nota ? el('div', { class: 'mudo' }, it.nota) : null),
        el('td', { class: 'id-lote' }, id), el('td', { class: 'nome-lote' }, nome));
      ck.onchange = () => {
        it.marcado = ck.checked;
        if (it.marcado && !it.id) { it.id = idLivreLote(); id.value = it.id; }
        id.disabled = nome.disabled = !it.marcado;
        tr.classList.toggle('desmarcado', !it.marcado);
        renderResumoLote();
      };
      id.onchange = () => { it.id = Number(id.value) || ''; renderResumoLote(); };
      nome.oninput = () => { it.nomeNovo = nome.value; renderResumoLote(); };
      return tr;
    };
    const preencher = () => {
      tb.innerHTML = '';
      for (const it of visiveis()) tb.append(linha(it));
      if (!tb.children.length) tb.append(el('tr', {}, el('td', { colspan: 6, class: 'vazia' }, 'Nenhum estádio com esse filtro.')));
    };
    busca.oninput = () => { L.filtro = busca.value; preencher(); };
    preencher();
  }
  pag.append(c1.el);
  // projeto do FET
  const c2 = cartao('Projeto do FET', 'Num projeto só, cada estádio entra no projeto dos anteriores (ele cresce cerca de 180 MB por estádio). Um estádio que der erro fica de fora, e os outros seguem.');
  c2.corpo.append(segmentado([['junto', 'Todos num projeto só (recomendado)'], ['separados', 'Um projeto para cada estádio']], L.modo, (v) => { L.modo = v; renderLote(); }));
  if (L.modo === 'junto') {
    c2.corpo.append(el('div', { style: { marginTop: '10px' } }, segmentado([['novo', 'Projeto novo (do zero)'], ['projeto', 'Adicionar a um projeto existente']], L.projetoModo, (v) => { L.projetoModo = v; renderLote(); })));
    if (L.projetoModo === 'projeto') c2.corpo.append(linhaCaminho(L.projeto, 'Escolha ou cole o caminho do .fifaproject', async () => {
      const r = await api('dialogo', { modo: 'abrir', tipo: 'projeto', titulo: 'Projeto do FET em que os estádios convertidos vão entrar' });
      if (!r.cancelado) { L.projeto = r.caminho; renderLote(); }
    }, (v) => { L.projeto = v; }));
  } else {
    c2.corpo.append(el('div', { style: { marginTop: '10px' } }, nota('Cada estádio vai para um .fifaproject próprio, na pasta que você escolher. No FET só um projeto de estádio fica ativo por vez (todos mexem no mapa de estádios, nos loaders e no banco): para jogar com vários estádios convertidos, use um projeto só.', 'alerta')));
  }
  pag.append(c2.el);
  // opções para todos
  const o = L.opcoes;
  const sel = (chave, ops) => {
    const s = el('select', {}, ops.map(([k, t]) => el('option', { value: k, selected: o[chave] === k }, t)));
    s.onchange = () => { o[chave] = s.value; };
    return s;
  };
  const co = cartao('Opções para todos os estádios', 'O resto vem da análise de cada estádio (ou da receita guardada, quando há, como a do Morumbi do FIFA 16). Para mexer nas peças de um estádio, converta-o sozinho na aba Converter.');
  co.corpo.append(el('div', { class: 'grade2' },
    campo2('Rede do gol', sel('rede', REDES_DO_GOL), AJUDA_REDE),
    campo2('Colisão em volta do campo', sel('colisao', COLISOES), AJUDA_COLISAO),
    campo2('Câmeras', sel('cameras', CAMERAS), AJUDA_CAMERAS),
    campo2('Banners dos times (PES 2021)', sel('banners', [['automaticos', 'Nas frentes dos anéis da torcida (recomendado)'], ['nenhum', 'Sem banners dos times']]),
      'O PES não marca onde eles ficam: vão sozinhos para as muretas na frente dos anéis da torcida. No FIFA 16, vão para as peças que a análise marca.'),
    campo2('Luzes da torcida à noite', sel('luzes', [['padrao', 'O padrão de cada jogo (recomendado)'], ['cobrir', 'Cobrem toda a torcida'], ['acompanhar', 'Acompanham a torcida']]),
      'Padrão: no PES 2021 as luzes da arquibancada do El Grandioso cobrem toda a torcida; no FIFA 16, acompanham a torcida (o que foi testado em partida).'),
    campo2('Personagens laterais', sel('personagens', [['padrao', 'Ajustar a cada estádio (recomendado)'], ['esconder', 'Esconder (ficam só os técnicos)']]),
      'Gandulas, fotógrafos, câmeras, policiais e seguranças: os que ficariam dentro da arquibancada vão para o lugar livre mais perto do campo, ou saem de vista.'),
    campo2('Reservas no banco', sel('reservas', [['padrao', 'Nas cadeiras do banco (recomendado)'], ['esconder', 'Esconder']]),
      'As cadeiras do banco são achadas no modelo de cada estádio.')));
  pag.append(co.el);
  const btn = el('button', { class: 'btn-primario grande', id: 'btn-lote', html: icone('converter', 16) + 'Converter em lote' });
  btn.onclick = converterLote;
  pag.append(el('div', { class: 'rodape-acao' }, el('span', { class: 'resumo', id: 'resumo-lote' }), btn));
  renderResumoLote();
}

function faixaDeIds(ids) {
  const s = [...ids].sort((x, y) => x - y);
  if (s.length > 1 && s.every((x, k) => !k || x === s[k - 1] + 1)) return `${s[0]}–${s[s.length - 1]}`;
  return s.length > 8 ? s.slice(0, 8).join(', ') + '…' : s.join(', ');
}

function renderResumoLote() {
  const r = $('#resumo-lote');
  if (!r) return;
  const L = S.lote;
  const m = L.itens.filter((i) => i.marcado);
  const btn = $('#btn-lote');
  if (btn) btn.disabled = !m.length;
  if (!m.length) { r.textContent = L.achados ? 'Marque os estádios que vão ser convertidos.' : 'Escolha a pasta com os estádios.'; return; }
  const ids = m.map((i) => Number(i.id)).filter(Boolean);
  const rep = [...new Set(ids.filter((x, k) => ids.indexOf(x) !== k))];
  const usados = new Set(S.cat?.ids_usados || []);
  const oc = ids.filter((x) => usados.has(x));
  const falta = m.filter((i) => !i.id || !String(i.nomeNovo).trim()).length;
  const min = m.length * MIN_POR_ESTADIO;
  const tempo = min >= 90 ? `${(min / 60).toFixed(1).replace('.', ',')} h` : `${min} min`;
  const gb = (m.length * MB_POR_ESTADIO / 1024).toFixed(1).replace('.', ',');
  r.innerHTML = `${m.length} estádio${m.length > 1 ? 's' : ''} → FC 27 <span class="mono">${faixaDeIds(ids)}</span> · cerca de ${tempo}`
    + (L.modo === 'junto' ? ` · projeto de ~${gb} GB` : '')
    + (rep.length ? ` <span class="etiqueta vermelha">ID repetido: ${rep.join(', ')}</span>` : '')
    + (oc.length ? ` <span class="etiqueta vermelha">já existe no jogo: ${oc.join(', ')}</span>` : '')
    + (falta ? ` <span class="etiqueta vermelha">${falta} sem ID ou nome</span>` : '');
}

async function converterLote() {
  const L = S.lote;
  const m = L.itens.filter((i) => i.marcado);
  if (!m.length) { aviso('Marque pelo menos um estádio.', { tipo: 'aviso' }); return; }
  if (m.some((i) => !i.id || !String(i.nomeNovo).trim())) { aviso('Cada estádio marcado precisa de um ID novo e de um nome.', { tipo: 'aviso' }); return; }
  const o = L.opcoes;
  const receita = { rede_gol: o.rede, colisao: o.colisao || 'estadio', cameras: o.cameras || 'ajustar', banners: o.banners };
  if (o.luzes !== 'padrao') receita.luzes_torcida = o.luzes;
  if (o.personagens !== 'padrao') receita.personagens = o.personagens;
  if (o.reservas !== 'padrao') receita.reservas = o.reservas;
  await tarefa('lote', { itens: m.map((i) => ({ origem: i.origem, pasta: i.pasta, novo_id: Number(i.id), nome: i.nomeNovo.trim() })), modo: L.modo,
    projeto_modo: L.projetoModo, projeto_base: L.modo === 'junto' && L.projetoModo === 'projeto' ? L.projeto : null, receita });
}

function mostrarLote(alvo, r) {
  const junto = r.modo === 'junto';
  const n = r.convertidos + r.falharam;
  const box = el('div', { class: 'cartao ' + (r.ok ? 'resultado-ok' : 'resultado-erro'), style: { marginTop: '12px' } });
  const corpo = el('div', { class: 'cartao-corpo' });
  corpo.append(el('div', { class: 'linha-acoes' }, el('span', { html: icone(r.ok ? 'check' : 'aviso', 18) }),
    el('b', { class: 'cresce' }, r.ok ? `${n} estádio${n > 1 ? 's' : ''} convertido${n > 1 ? 's' : ''} e verificado${n > 1 ? 's' : ''}` : `${r.convertidos} de ${n} estádios convertidos; ${r.falharam} fic${r.falharam > 1 ? 'aram' : 'ou'} de fora`),
    el('button', { class: 'btn peq', onclick: () => api('abrir', { caminho: r.saida }) }, junto ? 'Mostrar na pasta' : 'Abrir a pasta')));
  const min = Math.round((r.segundos || 0) / 60);
  corpo.append(el('dl', { class: 'kv', style: { marginTop: '10px' } }, el('dt', {}, junto ? 'Projeto' : 'Pasta'), el('dd', { class: 'mono' }, r.saida),
    junto ? el('dt', {}, 'SHA-256') : null, junto ? el('dd', { class: 'mono' }, r.sha256 || '') : null,
    el('dt', {}, 'Tempo'), el('dd', {}, min >= 1 ? `${min} min` : `${r.segundos} s`)));
  const tb = el('tbody');
  for (const it of r.itens) {
    tb.append(el('tr', {}, el('td', { class: 'mono' }, String(it.novo_id)), el('td', {}, el('b', {}, it.nome)),
      el('td', {}, el('span', { class: 'etiqueta ' + (it.ok ? 'verde' : 'vermelha') }, it.ok ? 'verificado' : 'ficou de fora')),
      el('td', { class: 'num' }, `${Math.round((it.segundos || 0) / 60)} min`),
      el('td', { class: it.ok ? 'mono mudo' : '' }, it.ok ? (junto ? '' : it.saida || '') : it.erro || '')));
  }
  corpo.append(el('div', { class: 'tabela-lote' }, el('table', { class: 'tabela' }, el('thead', {}, el('tr', {}, el('th', {}, 'ID'), el('th', {}, 'Estádio'), el('th', {}, ''),
    el('th', { class: 'num' }, 'Tempo'), el('th', {}, junto ? '' : 'Projeto'))), tb)));
  corpo.append(el('div', { style: { marginTop: '10px' } }, nota(junto
    ? 'Antes de testar: no FET, deixe ativo só este projeto (ele tem todos os estádios do lote). Se o jogo fechar ao iniciar a partida, o FC 27 grava um dump em %LOCALAPPDATA%\\EA SPORTS FC 27\\CrashDumps.'
    : 'No FET, só um projeto de estádio pode ficar ativo por vez (todos mexem no mapa de estádios, nos loaders e no banco). Para jogar com vários estádios convertidos, converta-os num projeto só.', 'info')));
  box.append(corpo);
  alvo.append(box);
  statusEsq(r.ok ? 'Lote convertido e verificado' : 'Lote convertido em parte');
}

// ------------------------------------------------------------------ resultados
async function renderResultados() {
  const pag = $('#pag-resultados');
  pag.innerHTML = '';
  pag.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('h1', {}, 'Projetos gerados'), el('div', { class: 'sub' }, 'Os últimos trabalhos desta ferramenta. Ative no FET um projeto por vez (todos mexem no mapa de estádios e no banco), ou junte as cópias num projeto só.'))));
  const cr = cartao('Projetos', '');
  cr.corpo.classList.add('justo');
  pag.append(cr.el);
  let r;
  try { r = await api('resultados'); } catch (e) { cr.corpo.append(nota(esc(e.message), 'erro')); return; }
  if (!r.resultados.length) { cr.corpo.append(el('div', { class: 'vazio' }, 'Nenhum projeto gerado ainda.')); return; }
  const lista = el('div', { class: 'lista-links' });
  for (const x of r.resultados) {
    lista.append(el('div', { class: 'link-linha' }, el('span', { html: icone(x.tipo === 'converter' ? 'converter' : 'copias', 15) }),
      el('div', { class: 'cresce' }, el('b', {}, x.nome || x.saida), el('div', { class: 'mono mudo', style: { fontSize: '11px' } }, x.saida)),
      el('span', { class: 'etiqueta ' + (x.ok ? 'verde' : 'vermelha') }, x.ok ? 'verificado' : 'com erros'), el('span', { class: 'mudo' }, x.quando),
      x.existe ? el('button', { class: 'btn peq', onclick: () => api('abrir', { caminho: x.saida }) }, 'Mostrar') : el('span', { class: 'mudo' }, 'arquivo movido')));
  }
  cr.corpo.append(lista);
}

// ------------------------------------------------------------------ tarefas (execução com registro ao vivo)
async function tarefa(rota, dados) {
  try {
    const r = await api(rota, dados);
    if (r.cancelado) return;
  } catch (e) { aviso(e.message, { tipo: 'erro' }); return; }
  abrirExec();
}

function abrirExec() {
  const etapas = el('div', { class: 'etapas' });
  const barra = el('div', { class: 'barra-progresso' }, el('div'));
  const texto = el('div', { class: 'carregando-detalhe' });
  const cons = el('div', { class: 'console' });
  const final = el('div');
  const corpo = el('div', {}, el('div', { class: 'exec' }, el('div', {}, etapas, el('div', { style: { marginTop: '10px' } }, barra, texto)), cons), final);
  let desde = 0, vivo = true;
  const m = modal({ titulo: 'Trabalhando…', corpo, largo: true, aoFechar: () => { vivo = false; }, botoes: [
    { rotulo: 'Parar', classe: 'btn-perigo', fn: async () => { await api('parar', {}); return false; } },
    { rotulo: 'Fechar', classe: 'btn-primario' }] });
  const titulo = document.querySelector('#camada-modal .modal-cab h2');
  (async function laco() {
    while (vivo) {
      let e;
      try { e = await api('exec?desde=' + desde); } catch { await espera(800); continue; }
      if (titulo) titulo.textContent = e.titulo || 'Trabalhando…';
      etapas.innerHTML = '';
      for (const s of e.etapas) etapas.append(el('div', { class: 'etapa ' + s.estado }, el('span', { class: 'ic', html: icone(s.estado === 'ok' ? 'check' : s.estado === 'erro' ? 'x' : 'relogio', 14) }), el('div', {}, s.descricao)));
      barra.firstChild.style.width = `${e.progresso || 0}%`;
      barra.classList.toggle('indeterminado', e.rodando && !e.progresso);
      texto.textContent = e.texto || '';
      for (const l of e.linhas) {
        const cls = l.startsWith('@@ETAPA') ? 'l-etapa' : l.startsWith('@@ERRO') || l.startsWith('@@FALHOU') || l.includes('Traceback') ? 'l-erro' : l.startsWith('@@AVISO') ? 'l-aviso' : '';
        if (l.startsWith('@@PROGRESSO')) continue;
        cons.append(el('div', { class: cls }, l.replace(/^@@(ETAPA|AVISO|ERRO|FALHOU) /, '').replace('|', ' — ')));
      }
      if (e.linhas.length) cons.scrollTop = cons.scrollHeight;
      desde = e.seq;
      if (!e.rodando) { mostrarResultado(final, e); return; }
      await espera(700);
    }
  })();
  return m;
}

function mostrarResultado(alvo, e) {
  alvo.innerHTML = '';
  const r = e.resultado;
  if (e.erro || !r) {
    alvo.append(el('div', { class: 'cartao resultado-erro', style: { marginTop: '12px' } }, el('div', { class: 'cartao-corpo' }, nota('Parou com erro: ' + esc(e.erro || 'sem resultado'), 'erro'),
      el('p', { class: 'mudo' }, 'Nada foi gravado no destino. O registro acima mostra onde parou.'))));
    statusEsq('Erro na tarefa');
    return;
  }
  if (e.tarefa === 'preparar') { aviso('Ambiente pronto.', { tipo: 'sucesso' }); carregarAmbiente(); return; }
  if (r.tipo === 'lote') { mostrarLote(alvo, r); return; }
  const v = r.verificacao;
  const box = el('div', { class: 'cartao ' + (r.ok ? 'resultado-ok' : 'resultado-erro'), style: { marginTop: '12px' } });
  const corpo = el('div', { class: 'cartao-corpo' });
  corpo.append(el('div', { class: 'linha-acoes' }, el('span', { html: icone(r.ok ? 'check' : 'aviso', 18) }), el('b', { class: 'cresce' }, r.ok ? 'Projeto gravado e verificado' : 'Projeto gravado, mas a verificação achou problemas'),
    el('button', { class: 'btn peq', onclick: () => api('abrir', { caminho: r.saida }) }, 'Mostrar na pasta')));
  corpo.append(el('dl', { class: 'kv', style: { marginTop: '10px' } }, el('dt', {}, 'Projeto'), el('dd', { class: 'mono' }, r.saida), el('dt', {}, 'SHA-256'), el('dd', { class: 'mono' }, r.sha256),
    el('dt', {}, 'Tempo'), el('dd', {}, `${r.segundos} s`)));
  if (v) {
    const n = v.notas || {};
    corpo.append(el('p', { class: 'mudo', style: { margin: '8px 0 0' } }, `Verificação lida do próprio arquivo: ${v.ok ? 'sem erros' : v.total_erros + ' erro(s)'} · ${fmtInt(n.ordem_ebx?.conferidos || 0)} EBX na ordem do FC 27 (${n.ordem_ebx?.fora_de_ordem || 0} fora) · ${fmtInt(v.registros?.ebx || 0)} EBX, ${fmtInt(v.registros?.res || 0)} RES, ${fmtInt(v.registros?.chunks || 0)} chunks.`));
    if (v.erros?.length) corpo.append(el('div', { class: 'erros-lista' }, v.erros.join('\n')));
  }
  corpo.append(el('div', { style: { marginTop: '10px' } }, nota('Antes de testar: no FET, deixe ativo só este projeto (todos os projetos de estádio mexem no mapa de estádios, nos loaders e no banco). Se o jogo fechar ao iniciar a partida, o FC 27 grava um dump em %LOCALAPPDATA%\\EA SPORTS FC 27\\CrashDumps.', 'info')));
  box.append(corpo);
  alvo.append(box);
  statusEsq(r.ok ? 'Projeto gravado e verificado' : 'Projeto gravado com avisos');
}

// ------------------------------------------------------------------ peças de interface
function cartao(titulo, dica) {
  const cab = el('header', {}, el('div', {}, el('h3', {}, titulo), dica ? el('p', { class: 'dica' }, dica) : null));
  const corpo = el('div', { class: 'cartao-corpo' });
  return { el: el('section', { class: 'cartao' }, cab, corpo), cab, corpo };
}

function campo2(rot, controle, ajuda) {
  return el('div', { class: 'campo' }, el('label', {}, rot), controle, ajuda ? el('div', { class: 'ajuda' }, ajuda) : null);
}

function segmentado(opcoes, atual, aoMudar) {
  const s = el('div', { class: 'segmentado' });
  for (const [v, t] of opcoes) {
    const b = el('button', { class: v === atual ? 'ativo' : '' }, t);
    b.onclick = () => { for (const x of s.children) x.classList.remove('ativo'); b.classList.add('ativo'); aoMudar(v); };
    s.append(b);
  }
  return s;
}

function linhaCaminho(valor, placeholder, aoEscolher, aoDigitar = null) {
  const inp = el('input', { type: 'text', readonly: !aoDigitar, value: valor || '', placeholder, class: 'mono', spellcheck: 'false' });
  if (aoDigitar) inp.onchange = () => { const v = inp.value.trim().replace(/^"|"$/g, ''); if (v) aoDigitar(v); };
  return el('div', { class: 'caminho-linha', style: { marginTop: '10px' } }, inp, el('button', { class: 'btn', html: icone('pasta', 14) + 'Escolher…', onclick: aoEscolher }));
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

iniciar();
