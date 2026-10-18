// Criador de Kits — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, confirmar, barraMenus, divisorArrastavel, dialogoSobre, nota, modalAberto, menuAberto, lerArquivoBase64, campo, entrada } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { instalarComponentes } from './comum/componentes.js';
import { importarReferencias } from './comum/referencias.js';
import { Editor2D } from './editor.js';
import { Previa3D } from './previa3d.js';

const S = {
  projeto: null, doador: null, analise: null, job: {}, opcoes: {}, ambiente: {}, referencias: {}, malhas: {}, biblioteca: {},
  padroes: [], tipos: [], versao: '', peca: 'jersey', modo: '2d', sel: null, urls: {}, bases: {}, chaves: {}, hist: [], futuro: [],
  molde: null, kits: [], malhasDados: {}, ultimoFim: null,
};
const NOME_PECA = { jersey: 'Camisa', shorts: 'Calção', socks: 'Meião' };
const NOME_TIPO = { home: 'Casa (home)', away: 'Fora (away)', goalie_home: 'Goleiro (goalie_home)', third: 'Terceiro (third)', fourth: 'Quarto (fourth)' };
const NOME_PADRAO = {
  lisa: 'Lisa', listras_v: 'Listras verticais', listras_h: 'Listras horizontais (aros)', xadrez: 'Xadrez', metades: 'Metades',
  faixa_diagonal: 'Faixa diagonal', faixa_peito: 'Faixa no peito', v: 'V no peito', degrade: 'Degradê',
};
const PARAMS = {   // [chave, rótulo, min, max, passo, formato]
  listras_v: [['periodo', 'Distância', 0.04, 0.6, 0.005], ['largura', 'Espessura', 0.05, 0.95, 0.01], ['fase', 'Posição', -0.5, 0.5, 0.01]],
  listras_h: [['periodo', 'Distância', 0.04, 0.6, 0.005], ['largura', 'Espessura', 0.05, 0.95, 0.01], ['fase', 'Posição', -0.5, 0.5, 0.01]],
  xadrez: [['periodo', 'Tamanho', 0.04, 0.6, 0.005], ['largura', 'Espessura', 0.05, 0.95, 0.01], ['fase', 'Posição', -0.5, 0.5, 0.01]],
  metades: [['fase', 'Divisão', -0.4, 0.4, 0.01]],
  faixa_diagonal: [['largura', 'Largura', 0.03, 0.6, 0.005], ['angulo', 'Inclinação', -70, 70, 1], ['fase', 'Posição', -0.5, 0.5, 0.01]],
  faixa_peito: [['largura', 'Altura', 0.02, 0.5, 0.005], ['fase', 'Posição', -0.3, 0.6, 0.01]],
  v: [['largura', 'Espessura', 0.02, 0.4, 0.005], ['angulo', 'Abertura', 5, 70, 1], ['fase', 'Altura', -0.1, 0.8, 0.01]],
  degrade: [['fase', 'Começo', -0.2, 1, 0.01], ['largura', 'Comprimento', 0.05, 1.2, 0.01]],
};

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }
const clone = (o) => JSON.parse(JSON.stringify(o));
const nomeArq = (c) => (c || '').split(/[\\/]/).filter(Boolean).pop() || '';
const slug = (s) => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'time';
const cfg = () => S.projeto?.pecas?.[S.peca];

// ---------------------------------------------------------------- estado vindo do servidor
function aplicar(r) {
  if (!r) return;
  for (const k of ['projeto', 'doador', 'analise', 'job', 'opcoes', 'ambiente', 'referencias', 'malhas', 'biblioteca']) if (k in r) S[k] = r[k];
  desenharTudo();
  if (S.job.rodando) acompanharJob();
}

function desenharTudo() {
  $('#vazio-vista').hidden = !!S.projeto;
  $('#abas-peca').hidden = !S.projeto;
  $('#barra-vista').hidden = !S.projeto;
  desenharKit();
  desenharPropriedades();
  desenharTopo();
  desenharStatus();
  if (S.projeto) { atualizarEditor(); previaDepois(0); }
}

// ---------------------------------------------------------------- histórico (desfazer/refazer) e gravação
function antes() {
  S.hist.push(JSON.stringify(S.projeto));
  if (S.hist.length > 80) S.hist.shift();
  S.futuro = [];
}
let tSalvar = null;
function depois({ previa = true, painel = true } = {}) {
  clearTimeout(tSalvar);
  tSalvar = setTimeout(() => tentar(() => api('projeto', { projeto: S.projeto })), 350);
  if (painel) { desenharKit(); desenharPropriedades(); }
  desenharTopo();
  atualizarEditor();
  if (previa) previaDepois();
}
function desfazer() {
  if (!S.hist.length) return;
  S.futuro.push(JSON.stringify(S.projeto));
  S.projeto = JSON.parse(S.hist.pop());
  depois();
}
function refazer() {
  if (!S.futuro.length) return;
  S.hist.push(JSON.stringify(S.projeto));
  S.projeto = JSON.parse(S.futuro.pop());
  depois();
}

// ---------------------------------------------------------------- endereços dos arquivos (logos)
let pedidoUrls = null;
function urlDe(caminho) {
  if (!caminho) return null;
  if (S.urls[caminho]) return S.urls[caminho];
  if (!pedidoUrls) {
    pedidoUrls = new Set();
    setTimeout(async () => {
      const lista = [...pedidoUrls];
      pedidoUrls = null;
      const r = await api('url', { caminhos: lista }).catch(() => null);
      if (r) { Object.assign(S.urls, r.urls); editor.desenhar(); desenharKit(); atualizar3D(); }
    }, 30);
  }
  pedidoUrls.add(caminho);
  return null;
}

// ---------------------------------------------------------------- editor 2D / 3D
let editor = null, previa3d = null;

function itensEditor() {
  const p = S.projeto;
  const it = (cfg()?.logos || []).map((o) => ({ id: o.id, tipo: 'logo', obj: o }));
  if (S.peca === 'jersey') {
    for (const k of ['escudo', 'marca']) if (p[k]?.arquivo && p[k].caixa) it.push({ id: k, tipo: k, obj: p[k] });
  } else if (S.peca === 'shorts') {
    for (const k of ['escudo', 'marca']) {
      if (p[k]?.arquivo && p[k].caixa_calcao && p[k].no_calcao !== false) {
        it.push({ id: k + '_calcao', tipo: k, obj: { arquivo: p[k].arquivo, get caixa() { return p[k].caixa_calcao; }, set caixa(v) { p[k].caixa_calcao = v; } } });
      }
    }
  }
  return it;
}

function atualizarEditor() {
  if (!S.projeto || !editor) return;
  editor.definir({ peca: S.peca, base: S.bases[S.peca] || null, itens: itensEditor() });
  editor.sel = S.sel;
  atualizar3D();
}

let tPrevia = null, pedidoPrevia = 0;
function chaveRender(peca) {
  const c = S.projeto.pecas[peca];
  return JSON.stringify([S.projeto.doador, c.camadas, c.cores, c.padrao, c.detalhe]);
}
function previaDepois(atraso = 220) {
  clearTimeout(tPrevia);
  tPrevia = setTimeout(() => carregarPrevia(S.peca), atraso);
}
async function carregarPrevia(peca) {
  if (!S.projeto) return;
  const chave = chaveRender(peca);
  if (S.chaves[peca] === chave && S.bases[peca]) { atualizarEditor(); return; }
  const n = ++pedidoPrevia;
  const fim = S.bases[peca] ? () => {} : carregando('Desenhando a textura…');
  try {
    const r = await api('previa', { projeto: S.projeto, peca });
    const im = new Image();
    await new Promise((ok, falha) => { im.onload = ok; im.onerror = () => falha(new Error('Não foi possível carregar a prévia.')); im.src = r.url; });
    S.bases[peca] = im;
    S.chaves[peca] = chave;
    if (n === pedidoPrevia || peca === S.peca) atualizarEditor();
  } catch (e) { aviso('Prévia: ' + e.message, { tipo: 'erro' }); } finally { fim(); }
}

async function atualizar3D() {
  if (S.modo !== '3d' || !S.projeto) return;
  const cv = editor.compor();
  if (!cv) return;
  if (!S.malhasDados[S.peca]) {
    const fim = carregando('Lendo a malha…');
    try { S.malhasDados[S.peca] = await api(`malha?peca=${S.peca}`); } catch (e) { aviso(e.message, { tipo: 'erro' }); definirModo('2d'); return; } finally { fim(); }
  }
  if (!previa3d) previa3d = new Previa3D($('#tela3d'));
  previa3d.mostrar(S.peca, S.malhasDados[S.peca], cv);
}

function definirPeca(p) {
  S.peca = p;
  S.sel = null;
  document.querySelectorAll('#seg-peca button').forEach((b) => b.classList.toggle('ativo', b.dataset.peca === p));
  if (previa3d) previa3d.peca = null;
  desenharKit();
  desenharPropriedades();
  atualizarEditor();
  editor.enquadrar();
  previaDepois(0);
}

function definirModo(m) {
  if (m === '3d' && !S.malhas[S.peca]) {
    modalMalhas();
    return;
  }
  S.modo = m;
  document.querySelectorAll('#seg-modo button').forEach((b) => b.classList.toggle('ativo', b.dataset.modo === m));
  $('#tela2d').hidden = m !== '2d';
  $('#tela3d').hidden = m !== '3d';
  if (m === '3d') atualizar3D(); else editor.desenhar();
}

function modalMalhas() {
  const corpo = el('div', { class: 'mudo', style: { lineHeight: '1.6' }, html: `
    A prévia 3D precisa das malhas dos uniformes exportadas pelo FET do FC 27 (FBX), que não vêm no Super Tool:<br>
    <span class="mono" style="font-size:11.5px">content/character/body/body_simhigh_0/jersey_0_round_short_noband_untucked_regular_male/jersey_0_0_0_0_1_0_0_mesh<br>
    content/character/body/body_simhigh_0/shorts_regular_male/shorts_0_0_0_mesh<br>
    content/character/body/body_simhigh_0/socks_regular_medium_male/sock_0_0_1_0_0_mesh</span><br><br>
    Exporte as três e use <b>Importar referências</b> apontando a pasta onde elas ficaram. O resto da ferramenta funciona sem elas.` });
  modal({ titulo: 'Malhas para a prévia 3D', corpo, largo: true, botoes: [
    { rotulo: 'Fechar', classe: 'btn' },
    { rotulo: 'Importar referências…', classe: 'btn-primario', padrao: true, fn: () => importarReferencias({ aoTerminar: () => atualizar() }) },
  ] });
}

// ---------------------------------------------------------------- topo / status
function desenharTopo() {
  const p = S.projeto;
  $('#titulo').innerHTML = p ? `<b>${esc(p.time?.nome || 'Novo time')}</b><span class="pasta">${esc(NOME_TIPO[p.tipo] || p.tipo)} · teamid ${esc(p.time?.teamid || '?')}</span>` : '';
  const b = $('#btn-exportar');
  b.disabled = !p || S.job.rodando || !S.ambiente.ok;
  $('#btn-exportar-txt').textContent = S.job.rodando ? `Exportando ${Math.round((S.job.progresso || 0) * 100)}%…` : 'Exportar kit';
  $('#btn-exportar-ic').innerHTML = icone(S.job.rodando ? 'recarregar' : 'baixar', 14, S.job.rodando ? 'girando' : '');
  $('#btn-desfazer').disabled = !S.hist.length;
  $('#btn-refazer').disabled = !S.futuro.length;
}

function desenharStatus() {
  const est = $('#status-esq');
  if (S.job.rodando) est.innerHTML = `<span>${icone('recarregar', 12, 'girando')} ${esc(S.job.mensagem || 'Exportando…')}</span>`;
  else if (S.projeto) {
    const n = (S.projeto.pecas.jersey.logos || []).length + (S.projeto.pecas.shorts.logos || []).length + (S.projeto.pecas.socks.logos || []).length;
    est.innerHTML = `<span>Doador: <b>${esc(nomeDoador())}</b></span><span>${n} logo(s)</span>${S.projeto.escudo?.arquivo ? '<span>com escudo</span>' : ''}${S.projeto.marca?.arquivo ? '<span>com marca</span>' : ''}`;
  } else est.innerHTML = '<span>Arraste a foto de uma camisa para a janela, ou comece do zero.</span>';
  const pr = $('#status-progresso');
  pr.hidden = !S.job.rodando;
  if (S.job.rodando) { $('#progresso-barra').style.width = `${100 * (S.job.progresso || 0)}%`; $('#progresso-txt').textContent = `${Math.round(100 * (S.job.progresso || 0))}%`; }
  const ch = $('#chip-python');
  ch.className = 'chip ' + (S.ambiente.ok ? 'ok' : S.ambiente.msg === 'verificando…' ? '' : 'erro');
  ch.innerHTML = icone(S.ambiente.ok ? 'check' : 'aviso', 12) + (S.ambiente.ok ? 'Motor pronto' : S.ambiente.msg === 'verificando…' ? 'verificando o motor…' : 'Motor indisponível');
  ch.title = S.ambiente.msg || '';
  ch.classList.toggle('clicavel', !!S.ambiente.instalar);
  ch.onclick = S.ambiente.instalar ? componentesMotor : null;
}

function nomeDoador() {
  const d = S.projeto?.doador || '';
  const partes = d.split(/[\\/]/).filter(Boolean);
  return partes.length >= 2 ? `${partes[partes.length - 2].replace(/_?\d+$/, '').replace(/_/g, ' ')} · ${partes[partes.length - 1].replace(/_\d+_\d+$/, '')}` : d;
}

// ---------------------------------------------------------------- painel esquerdo (kit)
function secao(titulo, ic, corpo, k, aberta = true) {
  const d = el('details', { class: 'secao', 'data-k': k });
  d.open = aberta;
  d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo)));
  return d;
}
function manterAbertas(raiz, fn) {
  const aberto = {};
  raiz.querySelectorAll('details.secao').forEach((d) => { aberto[d.dataset.k] = d.open; });
  const rol = raiz.scrollTop;
  fn();
  raiz.querySelectorAll('details.secao').forEach((d) => { if (d.dataset.k in aberto) d.open = aberto[d.dataset.k]; });
  raiz.scrollTop = rol;
}

function desenharKit() {
  const raiz = $('#kit');
  manterAbertas(raiz, () => {
    raiz.innerHTML = '';
    const p = S.projeto;
    if (!p) {
      raiz.append(el('div', { class: 'vazio' }, 'Comece por uma foto ou do zero: a ferramenta pede um kit doador do jogo.'));
      if (S.analise) raiz.append(secaoFoto());
      return;
    }
    raiz.append(secaoTime(), secaoDoador(), secaoFoto(), secaoLogos());
  });
}

function secaoTime() {
  const p = S.projeto;
  const t = p.time;
  const nome = entrada({ value: t.nome || '', placeholder: 'Nome do time' });
  nome.onchange = () => { antes(); t.nome = nome.value.trim(); t.pasta = slug(t.nome); depois({ previa: false }); };
  const tid = entrada({ value: t.teamid || '', placeholder: 'ex.: 131234', inputmode: 'numeric' });
  tid.onchange = () => { antes(); t.teamid = parseInt(tid.value, 10) || 0; depois({ previa: false }); };
  const tipo = el('select', { class: 'seletor' }, ...S.tipos.map((x) => el('option', { value: x, selected: x === p.tipo }, NOME_TIPO[x] || x)));
  tipo.onchange = () => { antes(); p.tipo = tipo.value; depois({ previa: false }); };
  const vari = entrada({ value: p.variacao || 0, inputmode: 'numeric' });
  vari.onchange = () => { antes(); p.variacao = Math.max(0, parseInt(vari.value, 10) || 0); depois({ previa: false }); };
  const n = { home: 0, away: 1, goalie_home: 2, third: 3, fourth: 4 }[p.tipo];
  const tidN = parseInt(t.teamid, 10) || 0;
  const rel = `kit_${Math.floor(tidN / 500) * 500}/${slug(t.pasta || t.nome)}_${tidN}/${p.tipo}_${n}_${p.variacao || 0}`;
  return secao('Time', 'escudo', [
    campo('Nome', nome),
    el('div', { class: 'linha-2' }, campo('teamid', tid), campo('Variação', vari)),
    campo('Uniforme', tipo),
    el('div', { class: 'ajuda', html: `Pasta: <span class="mono">${esc(rel)}</span>` }),
    !tidN ? nota('Informe o <b>teamid</b> do time (o mesmo do banco): ele vai no nome de todos os arquivos.', 'alerta') : null,
  ], 'time');
}

function secaoDoador() {
  const p = S.projeto;
  const card = el('div', { class: 'doador-cartao' },
    el('img', { src: `miniatura?pasta=${encodeURIComponent(p.doador)}`, alt: '' }),
    el('div', {}, el('b', {}, nomeDoador()), el('small', {}, p.doador)));
  const seg = el('div', { class: 'segmentado' }, ...[['doador', 'Do doador'], ['generico', 'Genéricos']].map(([v, r]) =>
    el('button', { class: (p.mapas || 'doador') === v ? 'ativo' : '', onclick: () => { antes(); p.mapas = v; depois({ previa: false }); } }, r)));
  return secao('Kit doador', 'camadas', [
    card,
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => escolherDoador('trocar') }, icone('recarregar', 12), 'Trocar doador…')),
    campo('Mapas de tecido (normal, coeff, taa, trama)', seg, (p.mapas || 'doador') === 'generico'
      ? 'Coeff e taa preenchidos com o valor mais comum do doador (tecido uniforme). Normal e trama vêm do doador.'
      : 'Copiados do doador. Se o doador tem patrocinadores estampados, o tecido deles pode aparecer: escolha um doador liso ou use Genéricos.'),
  ], 'doador', false);
}

function secaoFoto() {
  const an = S.analise;
  const corpo = [];
  if (!an) {
    corpo.push(el('div', { class: 'ajuda' }, 'Uma foto da camisa de frente preenche cores, padrão e logos. Dá para arrastar a foto para a janela.'));
    corpo.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', onclick: abrirFoto }, icone('imagem', 12), 'Abrir foto…')));
    return secao('Foto de referência', 'camera', corpo, 'foto');
  }
  corpo.push(el('div', { class: 'foto-cartao' }, el('img', { src: urlDe(an.conferencia) || '', alt: 'Conferência da foto', title: 'Rosa: recorte · azul: tronco · verde: axila · caixas: logos achados' })));
  corpo.push(el('div', { class: 'ajuda', html: `<b>${esc(an.nome_foto || '')}</b> · recorte por ${esc(an.metodo_recorte)}` }));
  const c = an.cores;
  corpo.push(el('div', { class: 'paleta', title: 'Cores achadas' }, ...[['base', c.base], ['padrão', c.padrao], ['manga', c.manga], ['gola', c.gola]].filter((x) => x[1])
    .map(([r, h]) => el('span', { style: { background: h }, title: `${r}: ${h}` }))));
  const pd = an.padrao;
  corpo.push(el('div', { class: 'ajuda', html: `Padrão: <b>${esc(NOME_PADRAO[pd.tipo] || pd.tipo)}</b>${pd.tipo.startsWith('listras') ? ` · distância ${pd.periodo} · espessura ${pd.largura}` : ''}${pd.nota ? ' · ' + esc(pd.nota) : ''}` }));
  const lista = el('div', { class: 'lista-logos' });
  for (const lg of an.logos) {
    const sel = el('select', { class: 'seletor', style: { height: '24px' } },
      ...[['escudo', 'Escudo'], ['marca', 'Marca'], ['patrocinador', 'Patrocinador'], ['ignorar', 'Ignorar']].map(([v, r]) =>
        el('option', { value: v, selected: (lg.ignorar ? 'ignorar' : lg.papel) === v }, r)));
    sel.onchange = async () => aplicar(await tentar(() => api('papel_logo', { id: lg.id, papel: sel.value })));
    lista.append(el('div', { class: `logo-linha ${lg.ignorar ? 'oculto' : ''}` },
      el('span', { class: 'mini' }, el('img', { src: urlDe(lg.arquivo) || '', alt: '' })),
      el('span', { class: 'txt' }, lg.nome, el('small', {}, lg.modo === 'bloco' ? 'recorte em bloco' : 'recorte por cor')), sel));
  }
  if (an.logos.length) corpo.push(campo(`Logos achados (${an.logos.length})`, lista));
  else corpo.push(nota('Nenhum logo achado. Adicione os logos à mão na seção Logos.'));
  corpo.push(el('div', { class: 'acoes-linha' },
    el('button', { class: 'btn-primario peq', disabled: !S.projeto, onclick: () => aplicarFoto() }, icone('varinha', 12), 'Aplicar ao kit'),
    el('button', { class: 'btn peq', onclick: abrirFoto }, icone('imagem', 12), 'Outra foto…')));
  corpo.push(el('div', { class: 'ajuda' }, 'Aplicar troca as cores da camisa, o padrão e os logos tirados da foto (os logos que você adicionou à mão ficam).'));
  return secao('Foto de referência', 'camera', corpo, 'foto');
}

function secaoLogos() {
  const p = S.projeto;
  const lista = el('div', { class: 'lista-logos' });
  const linha = (id, img, nome, sub, oculto, acoes) => {
    const l = el('div', { class: `logo-linha ${S.sel === id ? 'sel' : ''} ${oculto ? 'oculto' : ''}`, onclick: () => selecionar(id) },
      el('span', { class: 'mini' }, img ? el('img', { src: img, alt: '' }) : icone('imagem', 14)),
      el('span', { class: 'txt' }, nome, el('small', {}, sub)), el('span', { class: 'acoes' }, ...acoes));
    lista.append(l);
  };
  const btn = (ic, titulo, fn) => el('button', { class: 'btn-icone peq', title: titulo, html: icone(ic, 13), onclick: (e) => { e.stopPropagation(); fn(); } });
  if (S.peca === 'jersey' || S.peca === 'shorts') {
    for (const k of ['escudo', 'marca']) {
      const info = p[k] || {};
      const id = S.peca === 'shorts' ? k + '_calcao' : k;
      const nome = k === 'escudo' ? 'Escudo' : 'Marca';
      const sub = info.arquivo ? (S.peca === 'shorts' ? 'no calção (arquivo do jogo à parte)' : 'arquivo do jogo à parte (hotspot)') : 'sem imagem';
      linha(id, info.arquivo ? urlDe(info.arquivo) : null, nome, sub, !info.arquivo, [
        btn('upload', `Escolher a imagem do ${nome.toLowerCase()}…`, () => adicionarLogo(k)),
        info.arquivo ? btn('x', 'Tirar', () => { antes(); info.arquivo = null; depois({ previa: false }); }) : null,
      ].filter(Boolean));
    }
  }
  for (const lg of cfg().logos || []) {
    linha(lg.id, urlDe(lg.arquivo), lg.nome || 'Logo', `${Math.round(lg.largura * 1000) / 10}% de largura${lg.origem_foto ? ' · da foto' : ''}`, lg.visivel === false, [
      btn(lg.visivel === false ? 'olhoFechado' : 'olho', lg.visivel === false ? 'Mostrar' : 'Esconder', () => { antes(); lg.visivel = lg.visivel === false; depois({ previa: false }); }),
      btn('apagar', 'Tirar o logo', () => removerLogo(lg.id)),
    ]);
  }
  return secao(`Logos · ${NOME_PECA[S.peca]}`, 'imagem', [
    lista,
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => adicionarLogo('logo') }, icone('mais', 12), 'Adicionar logo…')),
    el('div', { class: 'ajuda' }, S.peca === 'jersey'
      ? 'Patrocinadores ficam pintados na textura. Escudo e marca vão em arquivos à parte que o jogo cola na caixa do hotspot. Nas costas, o logo gira 180° sozinho (as costas estão de cabeça para baixo na textura).'
      : 'Arraste os logos na textura; o canto redimensiona e a alça de cima gira.'),
  ], 'logos');
}

// ---------------------------------------------------------------- painel direito (peça)
function corCampo(rotulo, valor, aoMudar, { opcional = false, ligado = true, aoLigar = null } = {}) {
  const inp = el('input', { type: 'color', value: valor || '#ffffff' });
  inp.oninput = () => aoMudar(inp.value, false);
  inp.onchange = () => aoMudar(inp.value, true);
  const am = el('span', { class: `amostra ${ligado ? '' : 'vazia'}`, title: valor || '' }, ligado ? inp : null);
  const filhos = [am, el('label', { title: rotulo }, rotulo)];
  if (opcional) {
    const ch = el('input', { type: 'checkbox' });
    ch.checked = ligado;
    ch.onchange = () => aoLigar(ch.checked);
    filhos.push(el('label', { class: 'chk-mini', title: 'Usar uma cor própria' }, ch));
  }
  return el('div', { class: `cor-campo ${ligado ? '' : 'off'}` }, ...filhos);
}

// mudança de cor ao vivo: o histórico só registra quando o seletor fecha
let corAntes = null;
function mudarCor(fn) {
  return (v, fim) => {
    if (corAntes === null) corAntes = JSON.stringify(S.projeto);
    fn(v);
    if (fim) { S.hist.push(corAntes); S.futuro = []; corAntes = null; depois(); } else previaDepois(120);
  };
}

function deslizante(rotulo, valor, min, max, passo, aoMudar) {
  const inp = el('input', { type: 'range', min, max, step: passo, value: valor });
  const out = el('output', {}, String(valor));
  let snap = null;
  inp.oninput = () => { if (snap === null) snap = JSON.stringify(S.projeto); out.textContent = inp.value; aoMudar(parseFloat(inp.value)); previaDepois(120); };
  inp.onchange = () => { if (snap !== null) { S.hist.push(snap); S.futuro = []; snap = null; } depois(); };
  return el('div', { class: 'deslizante' }, el('span', {}, rotulo), inp, out);
}

function desenharPropriedades() {
  const raiz = $('#propriedades');
  manterAbertas(raiz, () => {
    raiz.innerHTML = '';
    if (!S.projeto) {
      raiz.append(el('div', { class: 'vazio' }, 'As cores, o padrão e os logos de cada peça aparecem aqui.'));
      return;
    }
    const c = cfg();
    const it = itensEditor().find((i) => i.id === S.sel);
    if (it) raiz.append(secaoSelecionado(it));
    raiz.append(secaoCores(c), secaoPadrao(c), secaoCamadas(c));
  });
}

function secaoCores(c) {
  const cores = c.cores;
  const grade = el('div', { class: 'cores-grade' });
  const set = (k) => mudarCor((v) => { cores[k] = v; });
  grade.append(corCampo('Base', cores.base, set('base')));
  grade.append(corCampo('Padrão / detalhes', cores.padrao, set('padrao')));
  const opc = (k, rot) => corCampo(rot, cores[k] || cores.base, set(k), { opcional: true, ligado: !!cores[k],
    aoLigar: (on) => { antes(); cores[k] = on ? (cores.padrao || cores.base) : null; depois(); } });
  if (S.peca === 'jersey') { grade.append(opc('manga', 'Mangas'), opc('gola', 'Gola'), opc('punho', 'Punhos')); }
  if (S.peca === 'shorts') grade.append(opc('cos', 'Cós'));
  if (S.peca === 'socks' && S.malhas.socks) grade.append(opc('cano', 'Cano (faixa de cima)'));
  return secao(`Cores · ${NOME_PECA[S.peca]}`, 'pincel', [grade,
    deslizante('Detalhe do tecido', c.detalhe ?? 1, 0, 1.5, 0.05, (v) => { c.detalhe = v; }),
    el('div', { class: 'ajuda' }, S.peca === 'jersey' ? 'Mangas, gola e punhos desligados ficam com a cor base. O detalhe mantém dobras, costuras e a trama do doador.' : 'O detalhe mantém dobras, costuras e a trama do doador.')], 'cores');
}

function secaoPadrao(c) {
  const pd = c.padrao || (c.padrao = { tipo: 'lisa' });
  const sel = el('select', { class: 'seletor' }, ...S.padroes.map((x) => el('option', { value: x, selected: x === pd.tipo }, NOME_PADRAO[x] || x)));
  sel.onchange = () => {
    antes();
    pd.tipo = sel.value;
    const pad = { listras_v: { periodo: 0.2, largura: 0.5, fase: 0 }, listras_h: { periodo: 0.18, largura: 0.5, fase: 0 }, xadrez: { periodo: 0.12, largura: 0.5, fase: 0 },
      metades: { fase: 0 }, faixa_diagonal: { largura: 0.2, angulo: 35, fase: 0 }, faixa_peito: { largura: 0.12, fase: 0 }, v: { largura: 0.08, angulo: 35, fase: 0 }, degrade: { fase: 0.2, largura: 0.7 } }[pd.tipo] || {};
    Object.assign(pd, pad);
    depois();
  };
  const corpo = [campo('Tipo', sel)];
  for (const [k, rot, mn, mx, ps] of PARAMS[pd.tipo] || []) corpo.push(deslizante(rot, pd[k] ?? 0, mn, mx, ps, (v) => { pd[k] = v; }));
  if (pd.tipo !== 'lisa') corpo.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', title: 'Troca a cor base com a do padrão', onclick: () => {
    antes(); const t = c.cores.base; c.cores.base = c.cores.padrao; c.cores.padrao = t; depois(); } }, icone('recarregar', 12), 'Inverter cores')));
  corpo.push(el('div', { class: 'ajuda' }, S.peca === 'jersey' ? 'O padrão vai no tronco (frente e costas, contínuo nas costuras); mangas e gola ficam com as cores delas.' : 'O padrão cobre a peça toda.'));
  return secao('Padrão', 'grade', corpo, 'padrao');
}

function secaoCamadas(c) {
  const doa = S.doador?.pecas?.[S.peca]?.camadas || [];
  const lista = el('div', {});
  c.camadas.forEach((cam, i) => {
    const info = doa[i] || {};
    const papel = el('select', { class: 'seletor' }, el('option', { value: 'base', selected: cam.papel === 'base' }, 'Segue a peça'), el('option', { value: 'fixa', selected: cam.papel !== 'base' }, 'Cor própria'));
    papel.onchange = () => { antes(); cam.papel = papel.value; depois(); };
    const ctl = el('span', { class: 'ctl' }, papel);
    if (cam.papel !== 'base') {
      const inp = el('input', { type: 'color', value: cam.cor || cam.origem });
      inp.oninput = () => mudarCor((v) => { cam.cor = v; })(inp.value, false);
      inp.onchange = () => mudarCor((v) => { cam.cor = v; })(inp.value, true);
      ctl.append(el('span', { class: 'amostra' }, inp));
    }
    lista.append(el('div', { class: 'camada' }, el('span', { class: 'orig', style: { background: cam.origem }, title: `Cor no doador: ${cam.origem}` }),
      el('span', { class: 'txt' }, i === 0 ? 'Principal do doador' : `Detalhe ${i}`, el('small', {}, `${Math.round((info.fracao || 0) * 1000) / 10}% da textura`)), ctl));
  });
  return secao('Cores do doador', 'camadas', [lista, el('div', { class: 'ajuda' },
    '“Segue a peça” recebe a cor base, o padrão e as cores de manga/gola/punho. “Cor própria” mantém o desenho daquele detalhe do doador (frisos, faixas, logos estampados) numa cor escolhida.')], 'camadas', false);
}

function secaoSelecionado(it) {
  const o = it.obj;
  const corpo = [];
  if (it.tipo === 'logo') {
    const nome = entrada({ value: o.nome || '' });
    nome.onchange = () => { antes(); o.nome = nome.value; depois({ previa: false }); };
    corpo.push(campo('Nome', nome));
    corpo.push(deslizante('Largura (%)', +(o.largura * 100).toFixed(2), 0.5, 80, 0.1, (v) => { const f = v / 100 / o.largura; o.largura *= f; o.altura *= f; editor.desenhar(); atualizar3D(); }));
    corpo.push(deslizante('Rotação (°)', Math.round(o.rot || 0), 0, 359, 1, (v) => { o.rot = v; editor.desenhar(); atualizar3D(); }));
    corpo.push(deslizante('Opacidade', o.opacidade ?? 1, 0.1, 1, 0.05, (v) => { o.opacidade = v; editor.desenhar(); atualizar3D(); }));
    if (S.peca === 'jersey') {
      corpo.push(el('label', { class: 'chk-mini', style: { margin: '4px 0 8px' } }, (() => { const ch = el('input', { type: 'checkbox' }); ch.checked = o.rot_auto !== false; ch.onchange = () => { antes(); o.rot_auto = ch.checked; depois({ previa: false }); }; return ch; })(), 'Girar 180° sozinho nas costas'));
    }
    if (o.origem_foto) {
      const seg = el('div', { class: 'segmentado' }, ...[['cor', 'Por cor'], ['bloco', 'Em bloco'], ['foto', 'Retângulo']].map(([v, r]) =>
        el('button', { class: (o.modo || 'cor') === v ? 'ativo' : '', onclick: () => recortarLogo(o, v) }, r)));
      corpo.push(campo('Recorte da foto', seg, 'Por cor: só o que destoa da camisa. Em bloco: a forma preenchida (bom para escudos). Retângulo: o pedaço inteiro da foto.'));
    }
    corpo.push(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', onclick: () => centralizar(o) }, icone('centralizar', 12), 'Centralizar'),
      el('button', { class: 'btn peq', onclick: () => trocarImagem(o) }, icone('upload', 12), 'Trocar imagem…'),
      el('button', { class: 'btn-fantasma peq', onclick: () => removerLogo(o.id) }, icone('apagar', 12), 'Tirar')));
  } else {
    corpo.push(el('div', { class: 'ajuda' }, `Arquivo à parte (${it.tipo === 'escudo' ? 'crest' : 'brand'}_…, 256×256) que o jogo cola nesta caixa (hotspot “${it.tipo === 'escudo' ? 'team' : 'brand'}”). A proporção da caixa é a do doador.`));
    const base = it.id.endsWith('_calcao') ? S.projeto[it.tipo] : o;
    corpo.push(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', onclick: () => adicionarLogo(it.tipo) }, icone('upload', 12), 'Trocar imagem…'),
      it.id.endsWith('_calcao') ? el('button', { class: 'btn peq', onclick: () => { antes(); base.no_calcao = false; S.sel = null; depois({ previa: false }); } }, icone('olhoFechado', 12), 'Tirar do calção') : null));
  }
  return secao(it.tipo === 'logo' ? 'Logo selecionado' : it.tipo === 'escudo' ? 'Escudo' : 'Marca', 'cursor', corpo, 'sel');
}

function centralizar(o) { antes(); o.u = 0.5; depois({ previa: false }); }

// ---------------------------------------------------------------- seleção e logos
function selecionar(id) {
  S.sel = id;
  editor.sel = id;
  editor.desenhar();
  desenharKit();
  desenharPropriedades();
}

function removerLogo(id) {
  const c = cfg();
  const i = (c.logos || []).findIndex((l) => l.id === id);
  if (i < 0) return;
  antes();
  c.logos.splice(i, 1);
  if (S.sel === id) S.sel = null;
  depois({ previa: false });
}

async function escolherImagem() {
  const r = await tentar(() => api('dialogo', { modo: 'logo' }));
  return r && r.caminhos.length ? r.caminhos[0] : null;
}

async function adicionarLogo(papel, arquivoB64 = null) {
  let r;
  if (arquivoB64) r = await tentar(() => api('importar_logo', { arquivo: arquivoB64 }));
  else {
    const c = await escolherImagem();
    if (!c) return;
    r = await tentar(() => api('importar_logo', { caminho: c }));
  }
  if (!r) return;
  S.urls[r.arquivo] = r.url;
  antes();
  const p = S.projeto;
  if (papel === 'escudo' || papel === 'marca') {
    const info = p[papel] || (p[papel] = {});
    info.arquivo = r.arquivo;
    info.no_calcao = info.no_calcao ?? true;
    if (!info.caixa) info.caixa = papel === 'escudo' ? { x0: 0.522, y0: 0.571, x1: 0.598, y1: 0.633 } : { x0: 0.405, y0: 0.585, x1: 0.454, y1: 0.627 };
    S.sel = S.peca === 'shorts' ? papel + '_calcao' : papel;
    if (S.peca === 'socks') definirPeca('jersey');
  } else {
    const [w, h] = r.tamanho;
    const W = S.bases[S.peca]?.naturalWidth || 1024, H = S.bases[S.peca]?.naturalHeight || 1024;
    const esticar = S.peca === 'jersey' ? (S.molde?.jersey?.esticar || 1.2) : 1;
    const largura = S.peca === 'jersey' ? 0.16 : 0.08;
    const lg = { id: 'l' + Date.now().toString(36), nome: r.nome, arquivo: r.arquivo, u: 0.5, v: S.peca === 'jersey' ? 0.68 : 0.7, largura,
      altura: (largura * W * (h / w)) / esticar / H, rot: 0, visivel: true };
    cfg().logos.push(lg);
    S.sel = lg.id;
  }
  depois({ previa: false });
  if (r.tirou_fundo) aviso('Fundo liso tirado da imagem', { tipo: 'info', detalhe: 'Se não queria, use Trocar imagem com um PNG transparente.' });
}

async function trocarImagem(o) {
  const c = await escolherImagem();
  if (!c) return;
  const r = await tentar(() => api('importar_logo', { caminho: c }));
  if (!r) return;
  S.urls[r.arquivo] = r.url;
  antes();
  o.arquivo = r.arquivo;
  o.altura = o.largura * (r.tamanho[1] / r.tamanho[0]) * ((S.bases[S.peca]?.naturalWidth || 1) / (S.bases[S.peca]?.naturalHeight || 1)) / (S.peca === 'jersey' ? 1.2 : 1);
  delete o.origem_foto;
  depois({ previa: false });
}

async function recortarLogo(o, modo) {
  const r = await tentar(() => api('recorte_logo', { origem: o.origem_foto, modo }));
  if (!r) return;
  S.urls[r.arquivo] = r.url;
  antes();
  o.arquivo = r.arquivo;
  o.modo = modo;
  depois({ previa: false });
}

// ---------------------------------------------------------------- doador / biblioteca
async function escolherDoador(motivo) {
  let bib = await tentar(() => api('biblioteca'));
  if (!bib) return null;
  if (!bib.kits.length) {
    const ok = await confirmar('Onde estão os kits do jogo?', 'Escolha a pasta com os kits exportados pelo FET (a pasta <b>kit</b>, com kit_1000, kit_111000…). Um deles vai servir de doador: a ferramenta usa o molde e o tecido dele.', { rotulo: 'Escolher a pasta…' });
    if (!ok) return null;
    const d = await tentar(() => api('dialogo', { modo: 'biblioteca' }));
    if (!d || !d.caminhos.length) return null;
    bib = await tentar(() => api('definir_biblioteca', { pasta: d.caminhos[0] }));
    if (!bib) return null;
  }
  S.kits = bib.kits;
  return new Promise((resolver) => {
    let escolhido = S.projeto?.doador || null;
    const busca = entrada({ placeholder: 'Buscar time…', type: 'search' });
    const grade = el('div', { class: 'grade-kits' });
    const desenhar = () => {
      const q = busca.value.trim().toLowerCase();
      grade.innerHTML = '';
      for (const k of S.kits.filter((k) => !q || `${k.time} ${k.tipo} ${k.teamid}`.toLowerCase().includes(q))) {
        grade.append(el('button', { class: `cartao-kit ${escolhido === k.pasta ? 'sel' : ''}`, title: k.pasta,
          onclick: (e) => { escolhido = k.pasta; grade.querySelectorAll('.cartao-kit').forEach((b) => b.classList.toggle('sel', b === e.currentTarget)); },
          ondblclick: () => { escolhido = k.pasta; m.fechar(true); } },
          el('img', { src: `miniatura?pasta=${encodeURIComponent(k.pasta)}`, loading: 'lazy', alt: '' }), el('b', {}, k.time), el('small', {}, `${k.tipo} · ${k.teamid}`)));
      }
    };
    busca.oninput = desenhar;
    const corpo = el('div', {}, el('div', { class: 'ajuda', style: { marginBottom: '8px' } }, 'O doador dá o molde, as costuras, o tecido e as posições de escudo, marca e números. Prefira um kit liso (sem patrocinadores estampados): as cores e o desenho são trocados depois.'),
      el('div', { class: 'caminho-linha', style: { marginBottom: '10px' } }, busca,
        el('button', { class: 'btn', title: 'Outra pasta de kits…', onclick: async () => {
          const d = await tentar(() => api('dialogo', { modo: 'biblioteca' }));
          if (d && d.caminhos.length) { const b = await tentar(() => api('definir_biblioteca', { pasta: d.caminhos[0] })); if (b) { S.kits = b.kits; desenhar(); } }
        } }, icone('pasta', 14))), grade);
    desenhar();
    const m = modal({ titulo: motivo === 'trocar' ? 'Trocar o kit doador' : 'Escolha o kit doador', corpo, largo: true, botoes: [
      { rotulo: 'Cancelar', classe: 'btn', valor: false },
      { rotulo: 'Usar este doador', classe: 'btn-primario', padrao: true, valor: true },
    ], rodapeEsq: `${S.kits.length} kits em ${esc(nomeArq(bib.pasta))}` });
    m.promessa.then(async (ok) => {
      if (!ok || !escolhido) { resolver(null); return; }
      const fim = carregando('Lendo o doador…');
      try {
        if (motivo === 'trocar' && S.projeto) { antes(); aplicar(await api('trocar_doador', { pasta: escolhido })); S.chaves = {}; }
        else aplicar(await api('novo', { doador: escolhido }));
        resolver(escolhido);
      } catch (e) { aviso(e.message, { tipo: 'erro' }); resolver(null); } finally { fim(); }
    });
  });
}

async function comecarDoZero() {
  if (S.projeto && !await confirmar('Começar um kit novo?', 'O kit atual é substituído (a foto analisada continua).', { rotulo: 'Começar' })) return;
  S.hist = []; S.futuro = []; S.chaves = {}; S.bases = {};
  await escolherDoador('novo');
}

// ---------------------------------------------------------------- foto
async function abrirFoto() {
  const r = await tentar(() => api('dialogo', { modo: 'foto' }));
  if (!r || !r.caminhos.length) return;
  await analisarFoto(() => api('foto', { caminho: r.caminhos[0] }));
}

async function analisarFoto(fn) {
  const fim = carregando('Lendo a foto (recorte, cores, padrão e logos)…');
  let r;
  try { r = await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return; } finally { fim(); }
  aplicar(r);
  const an = S.analise;
  aviso('Foto analisada', { tipo: 'sucesso', detalhe: `${NOME_PADRAO[an.padrao.tipo] || an.padrao.tipo} · ${an.logos.length} logo(s). Confira os papéis e clique em Aplicar ao kit.`, tempo: 6000 });
  if (!S.projeto) {
    const d = await escolherDoador('novo');
    if (d) await aplicarFoto();
  }
}

async function aplicarFoto() {
  if (!S.projeto) { await escolherDoador('novo'); if (!S.projeto) return; }
  antes();
  const r = await tentar(() => api('aplicar_foto', {}));
  if (!r) { S.hist.pop(); return; }
  aplicar(r);
  definirPeca('jersey');
  aviso('Foto aplicada à camisa', { tipo: 'sucesso', detalhe: 'Ajuste cores, padrão e logos à vontade. Calção e meião ficaram com a cor base: mude na aba deles.', tempo: 6000 });
}

// ---------------------------------------------------------------- exportar
async function exportar() {
  if (!S.projeto || S.job.rodando) return;
  if (!S.ambiente.ok) { if (S.ambiente.instalar) componentesMotor(); else aviso(S.ambiente.msg, { tipo: 'erro' }); return; }
  const p = S.projeto;
  const saida = entrada({ value: S.opcoes.saida || '', placeholder: 'Pasta onde a estrutura kit_…/ vai ser criada', class: 'entrada mono' });
  const corpo = el('div', {},
    campo('Pasta de saída', el('div', { class: 'caminho-linha' }, saida, el('button', { class: 'btn', title: 'Escolher…', onclick: async () => {
      const d = await tentar(() => api('dialogo', { modo: 'saida' })); if (d && d.caminhos.length) saida.value = d.caminhos[0]; } }, icone('pasta', 14))),
    'Dentro dela é criada a mesma estrutura do jogo (<span class="mono">kit_&lt;faixa&gt;/&lt;time&gt;_&lt;teamid&gt;/&lt;tipo&gt;_n_v</span>), pronta para importar no FET.'),
    !(p.time.teamid > 0) ? nota('Falta o <b>teamid</b> (seção Time, à esquerda).', 'alerta') : null,
    el('dl', { class: 'kv' }, el('dt', {}, 'Time'), el('dd', {}, `${p.time.nome || '—'} (teamid ${p.time.teamid || '?'})`),
      el('dt', {}, 'Uniforme'), el('dd', {}, NOME_TIPO[p.tipo]), el('dt', {}, 'Mapas de tecido'), el('dd', {}, p.mapas === 'generico' ? 'genéricos' : 'do doador')));
  const ok = await modal({ titulo: 'Exportar o kit', corpo, botoes: [{ rotulo: 'Cancelar', classe: 'btn', valor: false },
    { rotulo: 'Exportar', classe: 'btn-primario', padrao: true, valor: true, desabilitado: !(p.time.teamid > 0) }] }).promessa;
  if (!ok) return;
  clearTimeout(tSalvar);
  aplicar(await tentar(() => api('exportar', { projeto: p, saida: saida.value.trim() })));
}

let tJob = null;
function acompanharJob() {
  if (tJob) return;
  tJob = setInterval(async () => {
    const r = await api('estado').catch(() => null);
    if (!r) return;
    S.job = r.job;
    desenharTopo(); desenharStatus();
    if (!r.job.rodando) {
      clearInterval(tJob); tJob = null;
      if (r.job.fim !== S.ultimoFim) {
        S.ultimoFim = r.job.fim;
        if (r.job.erro) aviso('A exportação falhou', { tipo: 'erro', detalhe: r.job.erro });
        else if (r.job.resumo) aviso('Kit exportado', { tipo: 'sucesso', tempo: 9000, detalhe: `${r.job.resumo.arquivos} arquivos em ${r.job.resumo.rel} · ${r.job.resumo.segundos} s`,
          acao: { rotulo: 'Abrir pasta', fn: () => tentar(() => api('abrir', { caminho: r.job.resumo.pasta })) } });
      }
    }
  }, 500);
}

// ---------------------------------------------------------------- diversos
function carregando(txt) {
  const a = $('#carregando-previa');
  a.hidden = false;
  a.innerHTML = icone('recarregar', 15, 'girando') + esc(txt);
  return () => { a.hidden = true; };
}
async function atualizar() { aplicar(await tentar(() => api('estado'))); }
async function componentesMotor() { await instalarComponentes({ aoTerminar: () => esperarMotor() }); }
function esperarMotor() {
  const t = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (e) { S.ambiente = e.ambiente; desenharStatus(); desenharTopo(); }
    if (e && (e.ambiente.ok || !e.ambiente.instalar)) { clearInterval(t); aplicar(e); }
  }, 700);
  setTimeout(() => clearInterval(t), 60000);
}

function prepararSoltar() {
  let n = 0;
  const camada = $('#camada-soltar');
  const temArquivo = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  window.addEventListener('dragenter', (e) => {
    if (!temArquivo(e)) return;
    e.preventDefault(); n++; camada.hidden = false;
    $('#camada-soltar-txt').textContent = S.projeto ? 'Solte: foto da camisa → analisa · imagem sobre a textura → vira logo' : 'Solte a foto da camisa';
  });
  window.addEventListener('dragleave', () => { n = Math.max(0, n - 1); if (!n) camada.hidden = true; });
  window.addEventListener('dragover', (e) => { if (temArquivo(e)) e.preventDefault(); });
  window.addEventListener('drop', async (e) => {
    if (!temArquivo(e)) return;
    e.preventDefault();
    n = 0; camada.hidden = true;
    const f = [...e.dataTransfer.files].find((x) => /\.(png|jpe?g|webp|bmp|tga|tiff?|gif)$/i.test(x.name));
    if (!f) { aviso('Solte uma imagem (.png, .jpg, .webp…).', { tipo: 'aviso' }); return; }
    const arquivo = { nome: f.name, dados: await lerArquivoBase64(f) };
    const sobreTextura = S.projeto && e.target.closest && e.target.closest('#viewport') && S.modo === '2d';
    if (sobreTextura && await escolhaSoltar() === 'logo') { await adicionarLogo('logo', arquivo); return; }
    await analisarFoto(() => api('receber_foto', { arquivo }));
  });
}

function escolhaSoltar() {
  return modal({ titulo: 'O que é esta imagem?', texto: 'Uma foto da camisa inteira (para ler cores, padrão e logos) ou um logo para colocar na peça?',
    botoes: [{ rotulo: 'Foto da camisa', classe: 'btn', valor: 'foto' }, { rotulo: 'Logo nesta peça', classe: 'btn-primario', valor: 'logo', padrao: true }] }).promessa;
}

function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { rotulo: 'Novo kit (escolher doador)…', icone: 'arquivoMais', fn: comecarDoZero },
      { rotulo: 'Abrir foto da camisa…', icone: 'imagem', atalho: 'Ctrl+O', fn: abrirFoto },
      { rotulo: 'Trocar o kit doador…', icone: 'camadas', desabilitado: !S.projeto, fn: () => escolherDoador('trocar') },
      '-',
      { rotulo: 'Adicionar logo…', icone: 'mais', desabilitado: !S.projeto, fn: () => adicionarLogo('logo') },
      { rotulo: 'Escolher escudo…', icone: 'escudo', desabilitado: !S.projeto, fn: () => adicionarLogo('escudo') },
      { rotulo: 'Escolher marca…', icone: 'imagem', desabilitado: !S.projeto, fn: () => adicionarLogo('marca') },
      '-',
      { rotulo: 'Exportar kit…', icone: 'baixar', atalho: 'Ctrl+E', desabilitado: !S.projeto || S.job.rodando, fn: exportar },
      { rotulo: 'Abrir pasta de saída', icone: 'externo', desabilitado: !S.opcoes.saida, fn: () => tentar(() => api('abrir', {})) },
      { rotulo: 'Importar malhas para o 3D…', icone: 'cubo', fn: () => importarReferencias({ aoTerminar: () => atualizar() }) },
    ]],
    ['Editar', () => [
      { rotulo: 'Desfazer', icone: 'desfazer', atalho: 'Ctrl+Z', desabilitado: !S.hist.length, fn: desfazer },
      { rotulo: 'Refazer', icone: 'refazer', atalho: 'Ctrl+Y', desabilitado: !S.futuro.length, fn: refazer },
      '-',
      { rotulo: 'Tirar o logo selecionado', icone: 'apagar', atalho: 'Delete', desabilitado: !S.sel || !cfg()?.logos?.some((l) => l.id === S.sel), fn: () => removerLogo(S.sel) },
    ]],
    ['Exibir', () => [
      ...['jersey', 'shorts', 'socks'].map((p, i) => ({ rotulo: NOME_PECA[p], atalho: String(i + 1), marcado: S.peca === p, desabilitado: !S.projeto, fn: () => definirPeca(p) })),
      '-',
      { rotulo: 'Textura (editor)', marcado: S.modo === '2d', fn: () => definirModo('2d') },
      { rotulo: '3D', marcado: S.modo === '3d', fn: () => definirModo('3d') },
      { rotulo: 'Partes do molde', atalho: 'M', marcado: editor?.verMolde, fn: alternarMolde },
      { rotulo: 'Enquadrar', atalho: 'F', fn: enquadrar },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Atalhos do teclado', icone: 'teclado', atalho: 'F1', fn: atalhos },
      { rotulo: 'Sobre o Criador de Kits', icone: 'info', fn: sobre },
    ]],
  ]);
}

async function alternarMolde() {
  if (!S.molde) S.molde = await tentar(() => api('molde'));
  editor.molde = S.molde?.[S.peca] || null;
  editor.verMolde = !editor.verMolde;
  $('#btn-molde').classList.toggle('ativo', editor.verMolde);
  editor.desenhar();
}
function enquadrar() { if (S.modo === '3d') previa3d?.enquadrar(); else editor.enquadrar(); }

function atalhos() {
  const t = el('div', { class: 'tabela-atalhos' });
  for (const [g, itens] of [['Kit', [['Abrir foto', 'Ctrl+O'], ['Exportar', 'Ctrl+E'], ['Desfazer / refazer', 'Ctrl+Z / Ctrl+Y'], ['Camisa / calção / meião', '1 / 2 / 3']]],
    ['Editor', [['Mover logo', 'arrastar'], ['Redimensionar', 'canto'], ['Girar (15° com Shift)', 'alça de cima'], ['Empurrar (×10 com Shift)', 'setas'], ['Tirar logo', 'Delete'],
      ['Aproximar', 'roda do mouse'], ['Mover a vista', 'botão do meio / espaço'], ['Enquadrar', 'F ou duplo clique'], ['Partes do molde', 'M']]]]) {
    t.append(el('h4', {}, g));
    for (const [rot, k] of itens) t.append(el('div', {}, el('span', {}, rot), el('span', { html: `<kbd>${esc(k)}</kbd>` })));
  }
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
function sobre() {
  dialogoSobre({ nome: 'Criador de Kits do FC 27', versao: S.versao, html: `
    Monta um uniforme do FC 27 a partir de um <b>kit doador</b> exportado pelo FET: recolore a camisa, o calção e o meião,
    desenha o padrão do tronco (listras, faixas, metades…) e coloca patrocinadores, escudo e marca. Uma foto da camisa de frente
    preenche cores, padrão e logos sozinha. A saída é a pasta no formato do jogo, com o hotspot.<br><br>
    <b>1.0</b> — primeira versão: foto → cores, listras e logos; editor da textura com logos arrastáveis; prévia 3D com as malhas do FET.<br><br>
    Ainda não testado no jogo.` });
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  const digitando = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === 'o') { e.preventDefault(); abrirFoto(); return; }
  if (ctrl && e.key.toLowerCase() === 'e') { e.preventDefault(); exportar(); return; }
  if (e.key === 'F1') { e.preventDefault(); atalhos(); return; }
  if (digitando) return;
  if (ctrl && e.key.toLowerCase() === 'z') { e.preventDefault(); if (e.shiftKey) refazer(); else desfazer(); return; }
  if (ctrl && e.key.toLowerCase() === 'y') { e.preventDefault(); refazer(); return; }
  if (ctrl || !S.projeto) return;
  if (['1', '2', '3'].includes(e.key)) { definirPeca(['jersey', 'shorts', 'socks'][+e.key - 1]); return; }
  if (e.key.toLowerCase() === 'm') { alternarMolde(); return; }
  if (e.key.toLowerCase() === 'f') { enquadrar(); return; }
  if (e.key === 'Delete' && S.sel) { removerLogo(S.sel); return; }
  if (e.key.startsWith('Arrow') && S.sel && S.modo === '2d') {
    e.preventDefault();
    const p = e.shiftKey ? 10 : 1;
    if (!tEmpurrar) antes();
    const d = { ArrowLeft: [-p, 0], ArrowRight: [p, 0], ArrowUp: [0, -p], ArrowDown: [0, p] }[e.key];
    editor.empurrar(...d);
    clearTimeout(tEmpurrar);
    tEmpurrar = setTimeout(() => { tEmpurrar = null; depois({ previa: false }); }, 400);
  }
});
let tEmpurrar = null;

// ---------------------------------------------------------------- início
async function iniciar() {
  $('#btn-desfazer').innerHTML = icone('desfazer', 16);
  $('#btn-refazer').innerHTML = icone('refazer', 16);
  $('#btn-molde').innerHTML = icone('grade', 16);
  $('#btn-enquadrar').innerHTML = icone('maximizar', 16);
  $('#soltar-ic').innerHTML = icone('camisa', 64);
  $('#btn-vazio-foto').innerHTML = icone('imagem', 15) + 'Abrir foto da camisa…';
  $('#btn-vazio-zero').innerHTML = icone('arquivoMais', 15) + 'Começar do zero…';
  $('#vazio-dica').textContent = 'Saída: a pasta do kit no formato do jogo (texturas, escudo, marca e hotspot), pronta para o FET.';
  $('#btn-vazio-foto').onclick = abrirFoto;
  $('#btn-vazio-zero').onclick = comecarDoZero;
  $('#btn-desfazer').onclick = desfazer;
  $('#btn-refazer').onclick = refazer;
  $('#btn-exportar').onclick = exportar;
  $('#btn-molde').onclick = alternarMolde;
  $('#btn-enquadrar').onclick = enquadrar;
  document.querySelectorAll('#seg-peca button').forEach((b) => { b.onclick = () => definirPeca(b.dataset.peca); });
  document.querySelectorAll('#seg-modo button').forEach((b) => { b.onclick = () => definirModo(b.dataset.modo); });
  divisorArrastavel($('#div-esq'), '--esq', { min: 260, max: 560 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 280, max: 560, lado: 'dir' });
  editor = new Editor2D($('#tela2d'), {
    urlDe,
    aoSelecionar: (id) => { S.sel = id; desenharKit(); desenharPropriedades(); },
    aoMudar: () => { if (!editor._snap) editor._snap = JSON.stringify(S.projeto); atualizar3D(); },
    aoConfirmar: () => { if (editor._snap) { S.hist.push(editor._snap); S.futuro = []; editor._snap = null; } depois({ previa: false }); },
  });
  // o instantâneo para desfazer é tirado no começo do arrasto
  $('#tela2d').addEventListener('pointerdown', () => { editor._snap = JSON.stringify(S.projeto); }, true);
  $('#tela2d').addEventListener('contextmenu', (e) => e.preventDefault());
  prepararSoltar();
  menus();
  const r = await api('inicio');
  S.versao = r.versao; S.padroes = r.padroes; S.tipos = r.tipos;
  $('#versao').textContent = r.versao;
  S.ultimoFim = r.job?.fim || null;
  aplicar(r);
  api('molde').then((m) => { S.molde = m; }).catch(() => {});
  if (S.ambiente.msg === 'verificando…') {
    const t = setInterval(async () => {
      const e = await api('estado').catch(() => null);
      if (e && e.ambiente.msg !== 'verificando…') { clearInterval(t); aplicar(e); }
    }, 700);
  }
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
