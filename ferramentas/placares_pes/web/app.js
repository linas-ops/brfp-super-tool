// Conversor de Placares PES → FC — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, barraMenus, divisorArrastavel, dialogoSobre, nota, campo, entrada, interruptor } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { instalarComponentes } from './comum/componentes.js';

const S = { inicio: null, pasta: '', placares: [], sel: null, info: {}, moldes: null, molde: null, pos: { x: 64, y: 48, escala: 1 },
  alvo: 'molde', alvoOutro: '', fontePes: true, subst: true, telasEsc: {}, fontes: {}, previa: null, ultimo: null, ocupado: false, tPrevia: null };

const GENERIC = 'data/ui/game/overlays/Generic/overlay_9002.big';
async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }
const nomeArq = (c) => (c || '').split(/[\\/]/).filter(Boolean).pop() || '';
const chaveMolde = (m) => (m ? `${m.fonte}|${m.arquivo}` : '');
// destino do placar (o mesmo cálculo do servidor) e o da substituição do mesmo conjunto (…002.big -> …021.big)
const alvoPlacar = () => ({ molde: S.molde?.arquivo, generic: GENERIC }[S.alvo] || S.alvoOutro || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
const alvoTela = (alvo, numero) => { const m = /^(.*overlay_\d+)002\.big$/i.exec(alvo || ''); return m ? m[1] + String(+numero % 1000).padStart(3, '0') + '.big' : ''; };
const alvoSubst = (alvo) => alvoTela(alvo, 9021);
// as outras telas do pacote (pênaltis…) que vão junto: todas, menos as desmarcadas
const extras = () => S.info[S.sel]?.telas_extras || [];
const extraMarcada = (x) => S.telasEsc[x.chave] !== false;

function carregando(txt) {
  const c = $('#carregando');
  c.hidden = !txt;
  c.innerHTML = txt ? `<span class="girando">${icone('recarregar', 14)}</span>${esc(txt)}` : '';
}

// ---------------------------------------------------------------- pacote e placares
async function abrirPasta(pasta) {
  if (!pasta) return;
  carregando('Procurando placares…');
  const r = await tentar(() => api('pacote', { pasta }));
  carregando('');
  if (!r) return;
  S.pasta = r.pasta;
  S.placares = r.placares.map((p) => ({ ...p, estado: 'novo' }));
  S.info = {};
  S.ultimo = null;
  desenharLista();
  desenharTudo();
  if (S.placares.length) await selecionar(S.placares[0].pasta);
  // os outros carregam em seguida (a primeira leitura de cada um descomprime as texturas: alguns segundos)
  for (const p of S.placares.slice(1)) await carregarPlacar(p.pasta, false);
}

async function carregarPlacar(pasta, mostrar = true) {
  const it = S.placares.find((p) => p.pasta === pasta);
  if (!it) return null;
  if (S.info[pasta]) return S.info[pasta];
  it.estado = 'lendo';
  desenharLista();
  if (mostrar) carregando(`Lendo ${it.nome}…`);
  try {
    const r = await api('placar', { pasta });
    S.info[pasta] = r;
    it.estado = 'ok';
    return r;
  } catch (e) {
    it.estado = 'erro';
    it.erro = e.message;
    if (mostrar) aviso(e.message, { tipo: 'erro' });
    return null;
  } finally {
    if (mostrar) carregando('');
    desenharLista();
  }
}

async function selecionar(pasta) {
  S.sel = pasta;
  S.ultimo = null;
  desenharLista();
  const r = await carregarPlacar(pasta);
  desenharTudo();
  if (r) { atualizarPrevia(); carregarTelas(pasta); }
}

async function carregarTelas(pasta) {
  const t = $('#telas');
  S.telas = null;
  t.innerHTML = '<div class="mudo">Montando as telas…</div>';
  const r = await api('telas', { pasta }).catch((e) => ({ erro: e.message }));
  if (S.sel !== pasta) return;
  t.innerHTML = '';
  if (r.erro) { t.append(nota(esc(r.erro), 'erro')); return; }
  S.telas = r.telas;
  desenharTelas();
}

function desenharTelas() {
  const t = $('#telas');
  if (!S.telas) return;
  t.innerHTML = '';
  const subst = S.info[S.sel]?.subst && S.subst;
  const filmes = new Set(extras().filter(extraMarcada).map((x) => x.filme));
  for (const x of S.telas) {
    const conv = x.nome === 'game2d_score' || (subst && x.nome === 'game2d_memberChange') || filmes.has(x.nome);
    t.append(el('figure', { class: 'tela-mini' + (conv ? ' convertida' : ''), title: `${x.nome} · ${x.w}×${x.h}` },
      el('div', { class: 'tela-img xadrez' }, el('img', { src: x.imagem, alt: x.titulo })),
      el('figcaption', {}, el('b', {}, x.titulo), el('small', {}, conv ? 'convertida' : `${x.w}×${x.h}`))));
  }
}

async function exportar() {
  if (!S.sel) return;
  carregando('Exportando as imagens…');
  const r = await tentar(() => api('exportar', { pasta: S.sel }));
  carregando('');
  if (r) aviso(`${r.telas} telas e ${r.recortes} recortes exportados`, { tipo: 'sucesso', detalhe: r.pasta, tempo: 7000 });
}

async function escolherPasta() {
  const r = await tentar(() => api('dialogo', { modo: 'pasta', inicial: S.pasta }));
  if (r && r.caminho) abrirPasta(r.caminho);
}

// ---------------------------------------------------------------- moldes do FC
async function carregarMoldes(atualizar = false) {
  carregando('Procurando placares do FC que servem de molde…');
  const r = await tentar(() => api('moldes', { atualizar }));
  carregando('');
  if (!r) { S.moldes = []; desenharPropriedades(); return; }
  S.moldes = r.moldes;
  const atual = r.atual && S.moldes.find((m) => chaveMolde(m) === chaveMolde(r.atual));
  S.molde = atual || S.moldes[0] || null;
  desenharPropriedades();
}

// ---------------------------------------------------------------- prévia do FC
function pedirPrevia() {
  clearTimeout(S.tPrevia);
  S.tPrevia = setTimeout(atualizarPrevia, 250);
}

async function atualizarPrevia() {
  const info = S.info[S.sel];
  $('#img-pes').src = info?.previa || '';
  $('#img-pes').style.width = info ? `${info.w * 2}px` : '';       // o placar do PES é pequeno: em dobro
  $('#bloco-subst').hidden = !info?.subst;
  $('#img-subst-pes').src = info?.subst?.previa || '';
  desenharExtras(null);
  if (!info || !S.molde) { $('#img-fc').src = ''; $('#img-tela').src = ''; $('#img-subst-fc').src = ''; return; }
  const r = await api('previa', { pasta: S.sel, molde: S.molde, ...S.pos, fonte_pes: S.fontePes }).catch((e) => { aviso(e.message, { tipo: 'erro' }); return null; });
  if (!r) return;
  S.previa = r;
  $('#img-fc').src = r.recorte;
  $('#img-tela').src = r.tela;
  $('#img-subst-fc').src = r.subst || '';
  desenharExtras(r.telas_extras || {});
  $('#dica-fc').textContent = S.molde.tipo === 'generic'
    ? `fundo do PES no Generic (${nomeArq(S.molde.arquivo)}), com textos de exemplo`
    : `fundo do PES no molde ${nomeArq(S.molde.arquivo)} (imagem ${r.fundo.w}×${r.fundo.h}), com textos de exemplo`;
}

// as outras telas: à esquerda como o PES desenha, à direita como deve ficar no FC ('fc': {chave: imagem}, ou null
// enquanto a prévia do FC não chega)
function desenharExtras(fc) {
  const lst = extras();
  const b = $('#extras');
  $('#bloco-extras').hidden = !lst.length;
  b.innerHTML = '';
  for (const x of lst) {
    const ligada = extraMarcada(x);
    b.append(el('div', { class: 'extra' + (ligada ? '' : ' desligada') },
      el('div', { class: 'extra-tit' }, el('b', {}, x.titulo), el('small', {}, ligada ? `vai para …${String(+x.numero % 1000).padStart(3, '0')}.big` : 'não será convertida')),
      el('div', { class: 'previa-par' },
        el('div', { class: 'previa-img xadrez' }, el('img', { src: x.previa || '', alt: `${x.titulo} no PES` })),
        el('div', { class: 'previa-img' }, el('img', { src: fc?.[x.chave] || '', alt: `${x.titulo} no FC` })))));
  }
}

// ---------------------------------------------------------------- converter
async function converter() {
  if (S.ocupado || !S.sel || !S.molde) return;
  S.ocupado = true;
  desenharTopo();
  carregando('Convertendo e gravando…');
  const r = await tentar(() => api('converter', { pasta: S.sel, molde: S.molde, ...S.pos, alvo: S.alvo, alvo_outro: S.alvoOutro, fonte_pes: S.fontePes, subst: S.subst, telas: S.telasEsc }));
  carregando('');
  S.ocupado = false;
  if (r) {
    S.ultimo = r;
    const gravadas = [r.subst && !r.subst.erro ? 'substituição' : null, ...(r.telas || []).filter((t) => !t.erro).map((t) => t.titulo.toLowerCase())].filter(Boolean);
    aviso(gravadas.length ? `Placar gravado, com ${gravadas.join(', ')}` : 'Placar gravado', { tipo: 'sucesso', tempo: 7000,
      detalhe: [r.alvo, ...(r.subst && !r.subst.erro ? [nomeArq(r.subst.alvo)] : []), ...(r.telas || []).filter((t) => !t.erro).map((t) => nomeArq(t.alvo))].join(' · '),
      acao: { rotulo: 'Mostrar arquivo', fn: () => tentar(() => api('abrir', { caminho: r.destino })) } });
    if (r.subst?.erro) aviso(`A substituição não foi gravada: ${r.subst.erro}`, { tipo: 'erro', tempo: 10000 });
    for (const t of (r.telas || []).filter((x) => x.erro)) aviso(`${t.titulo}: não foi gravada. ${t.erro}`, { tipo: 'erro', tempo: 10000 });
  }
  desenharTudo();
}

// ---------------------------------------------------------------- desenho
function desenharLista() {
  const l = $('#lista');
  l.innerHTML = '';
  $('#pasta-atual').textContent = S.pasta || '';
  for (const p of S.placares) {
    const info = S.info[p.pasta];
    const ic = { novo: ['ponto', ''], lendo: ['recarregar', 'girando'], ok: ['check', 'ok'], erro: ['aviso', 'erro'] }[p.estado] || ['ponto', ''];
    const b = el('button', { class: 'placar-item' + (p.pasta === S.sel ? ' sel' : ''), title: p.pasta, onclick: () => selecionar(p.pasta) },
      el('b', {}, p.nome), el('span', { class: `est ${ic[1]}`, html: icone(ic[0], 14) }));
    if (info?.previa) b.append(el('span', { class: 'mini', style: { backgroundImage: `url(${info.previa})` } }));
    if (p.estado === 'erro') b.append(el('small', {}, p.erro || 'não abriu'));
    else if (info) b.append(el('small', {}, info.arquivos.join(' · ')));
    l.append(b);
  }
  $('#resumo-lista').textContent = S.placares.length ? `${S.placares.length} placar(es)` : '';
}

function desenharTopo() {
  $('#versao').textContent = S.inicio ? 'v' + S.inicio.versao : '';
  const info = S.info[S.sel];
  $('#titulo').textContent = info ? info.nome : '';
  $('#btn-converter').disabled = S.ocupado || !info || !S.molde || !S.inicio?.motor?.ok;
}

function desenharStatus() {
  const m = S.inicio?.motor;
  const chip = $('#chip-motor');
  chip.innerHTML = m ? (m.ok ? icone('check', 12) + ' leitor do PES pronto' : icone('aviso', 12) + ' faltam numpy e Pillow') : '';
  chip.title = m?.msg || '';
  const ed = S.inicio?.editor;
  const ce = $('#chip-editor');
  ce.innerHTML = ed?.ok ? icone('pasta', 12) + ' ' + esc(ed.saida_nome || 'sem pasta de saída') : icone('aviso', 12) + ' Editor de Placares';
  ce.title = ed?.ok ? `Grava na pasta de saída do Editor de Placares:\n${ed.saida || '(nenhuma)'}` : (ed?.erro || '');
  $('#status-esq').textContent = S.ultimo ? `Gravado: ${S.ultimo.destino}` : (S.pasta ? '' : 'Abra a pasta de um placar do PES');
}

function secao(titulo, ic, corpo, aberta = true) {
  const d = el('details', { class: 'secao' });
  d.open = aberta;
  d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo).filter(Boolean)));
  return d;
}

function numero(rotulo, chave, passo, dica) {
  const i = entrada({ type: 'number', step: String(passo), value: String(S.pos[chave]), title: dica });
  i.onchange = () => { const v = parseFloat(i.value); if (Number.isFinite(v)) { S.pos[chave] = v; pedirPrevia(); } };
  return campo(rotulo, i);
}

function desenharPropriedades() {
  const p = $('#propriedades');
  const foco = document.activeElement && p.contains(document.activeElement) ? document.activeElement : null;
  if (foco && foco.tagName === 'INPUT' && foco.type !== 'radio') return;
  p.innerHTML = '';
  const info = S.info[S.sel];
  if (!S.inicio) return;
  if (!S.inicio.motor.ok) {
    p.append(el('div', { style: { padding: '14px' } }, nota(esc(S.inicio.motor.msg), 'alerta'),
      el('button', { class: 'btn-primario', style: { marginTop: '10px' }, onclick: () => instalarComponentes({ aoTerminar: iniciar }) }, el('span', { html: icone('baixar', 13) }), 'Instalar componentes')));
    return;
  }
  if (info) {
    p.append(el('div', { class: 'prop-cab' }, el('h3', { title: info.pasta }, info.nome), el('div', { class: 'sub' }, info.pasta)));
  }
  // molde
  const corpoMolde = [];
  if (S.moldes === null) corpoMolde.push(el('div', { class: 'mudo' }, 'Procurando…'));
  else if (!S.moldes.length) {
    corpoMolde.push(nota('Nenhum placar do FC serve de molde. O <b>Generic</b> (overlay_9002) vem do jogo: confira a pasta do jogo no Editor de Placares. Também servem os placares do <b>pack do LTA</b> (fundo numa imagem grande e textos soltos): adicione o <span class="mono">Pack de TV Total y Switcher.fifamod</span> como fonte no Editor de Placares (Arquivo › Fontes) e clique em Atualizar.', 'alerta'));
  } else {
    const sel = el('select', { class: 'seletor largo' });
    for (const m of S.moldes) {
      const o = el('option', { value: chaveMolde(m) }, m.tipo === 'generic'
        ? `${nomeArq(m.arquivo)} · Generic (${m.fonte === 'jogo' ? 'do jogo' : m.fonte_nome})`
        : `${nomeArq(m.arquivo)} · ${m.nome || m.conjunto || ''} (${m.fundo.w}×${m.fundo.h})`);
      if (chaveMolde(m) === chaveMolde(S.molde)) o.selected = true;
      sel.append(o);
    }
    sel.onchange = () => { S.molde = S.moldes.find((m) => chaveMolde(m) === sel.value); pedirPrevia(); desenharPropriedades(); };
    corpoMolde.push(campo('Placar do FC usado como molde', sel, S.molde ? `${esc(S.molde.fonte_nome)} · <span class="mono">${esc(S.molde.arquivo)}</span>` : ''));
    if (S.molde && S.molde.tipo === 'generic') {
      corpoMolde.push(nota('O placar padrão do jogo, sem depender de mod. O desenho do PES vai para a imagem do logo do FC (atrás dos textos), as caixas do Generic somem, e nomes, gols, relógio, faixas de cor, acréscimos e cartões vão para os lugares do PES — pelos lugares e pelas constantes do código, que posiciona tudo na animação. Use os nomes abreviados (3 letras): com os nomes longos o código alarga o placar. A placa dos acréscimos do PES não aparece, só o "+3".'));
    } else if (S.molde && S.molde.fundo.w * S.molde.fundo.h < 1920 * 1080) {
      corpoMolde.push(nota('A imagem de fundo deste molde não cobre a tela toda: partes do placar do PES fora dela não aparecem. Os moldes de fundo 1920×1080 (como o overlay_35002) aceitam o placar em qualquer lugar.', 'alerta'));
    }
  }
  corpoMolde.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => carregarMoldes(true) }, el('span', { html: icone('recarregar', 12) }), 'Atualizar a lista')));
  p.append(secao('Molde do FC', 'placar', corpoMolde));
  // posição
  p.append(secao('Posição na tela', 'mover', [
    el('div', { class: 'linha-num' }, numero('X', 'x', 1, 'Distância da borda esquerda da tela (1920×1080)'), numero('Y', 'y', 1, 'Distância do topo da tela'), numero('Escala', 'escala', 0.05, '1 = o tamanho do PES')),
    el('div', { class: 'mudo peq-txt' }, 'Canto do placar na tela de 1920×1080. Depois dá para mover tudo junto no Editor de Placares (o grupo mcClassOverlay).'),
  ]));
  // fonte dos números
  const fn = S.fontes[S.sel];
  if (info && fn === undefined) {
    const pasta = S.sel;
    S.fontes[pasta] = null;
    api('fonte_png', { pasta }).then((r) => { S.fontes[pasta] = r || { tem: false }; desenharPropriedades(); })
      .catch(() => { S.fontes[pasta] = { tem: false }; desenharPropriedades(); });
  }
  if (info) {
    const corpoFonte = [];
    if (fn && fn.tem) {
      const iv = interruptor({ titulo: 'Números com a fonte do PES', descricao: `Relógio e gols com os números desenhados do PES, como a fonte <span class="mono">${esc(fn.face)}.ttf</span> (vai para data/ui/fonts da saída, com família no FIFA.xml). Os nomes continuam com a fonte do molde.`,
        marcado: S.fontePes, aoMudar: (v) => { S.fontePes = v; pedirPrevia(); } });
      corpoFonte.push(iv.el, el('div', { class: 'amostra-fonte' }, el('img', { src: fn.imagem, alt: 'Números do PES' })),
        el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => tentar(async () => { const r = await api('fonte_png', { pasta: S.sel, salvar: true }); if (r.salvo) aviso('Fonte salva', { tipo: 'sucesso', detalhe: r.salvo }); }) }, el('span', { html: icone('baixar', 12) }), 'Salvar o .ttf…')));
    } else if (fn && !fn.tem) corpoFonte.push(el('div', { class: 'mudo' }, 'Este pacote não traz os números desenhados do PES.'));
    else corpoFonte.push(el('div', { class: 'mudo' }, 'Gerando a fonte…'));
    p.append(secao('Fonte dos números', 'textura', corpoFonte));
    // substituição
    const corpoSubst = [];
    if (info.subst) {
      const iv = interruptor({ titulo: 'Converter também a substituição', descricao: 'A tela de substituição do pacote vai para a substituição do mesmo conjunto do placar (<span class="mono">…021.big</span>), com a do Generic do jogo como molde: a placa do PES, o escudo do time e quem entra e quem sai nas caixas do PES.',
        marcado: S.subst, aoMudar: (v) => { S.subst = v; desenharTelas(); desenharPropriedades(); } });
      corpoSubst.push(iv.el);
      if (S.subst) {
        corpoSubst.push(nota('Com 2 ou 3 trocas ao mesmo tempo aparecem só a primeira que entra e a primeira que sai: a placa do PES tem lugar para uma.'
          + (info.subst.titulo ? ' A faixa do título da placa fica vazia (o FC não escreve título nessa tela).' : '')
          + (info.subst.escudo ? '' : ' A placa não tem lugar para o escudo: o do FC fica escondido.')));
      }
    } else corpoSubst.push(el('div', { class: 'mudo' }, 'Este pacote não traz a tela de substituição com as caixas de quem entra e de quem sai.'));
    p.append(secao('Substituição', 'converter', corpoSubst));
    // outras telas
    const corpoExtras = [];
    if (extras().length) {
      corpoExtras.push(el('div', { class: 'mudo peq-txt' }, 'Cada uma vai para a tela do mesmo conjunto do placar, com a do Generic do jogo como molde: a arte do PES atrás, e os textos, escudos e marcadores do FC nos lugares do PES.'));
      for (const x of extras()) {
        const iv = interruptor({ titulo: x.titulo, descricao: `<span class="mono">${esc(x.filme)}</span> → a tela <span class="mono">…${String(+x.numero % 1000).padStart(3, '0')}.big</span> do conjunto (no Generic, <span class="mono">overlay_${esc(x.numero)}</span>)`,
          marcado: extraMarcada(x), aoMudar: (v) => { S.telasEsc[x.chave] = v; desenharTelas(); desenharExtras(S.previa?.telas_extras || {}); desenharPropriedades(); } });
        corpoExtras.push(iv.el);
      }
    } else corpoExtras.push(el('div', { class: 'mudo' }, 'Este pacote não traz outras telas que o conversor saiba levar para o FC.'));
    p.append(secao('Outras telas', 'camadas', corpoExtras));
  }
  // destino
  const radio = (valor, titulo, sub) => {
    const r = el('input', { type: 'radio', name: 'alvo', value: valor });
    r.checked = S.alvo === valor;
    r.onchange = () => { S.alvo = valor; desenharPropriedades(); };
    return el('label', {}, r, el('span', {}, el('b', {}, titulo), el('small', { html: sub })));
  };
  const destino = [el('div', { class: 'opcoes-radio' },
    radio('molde', 'No lugar do molde', S.molde ? `<span class="mono">${esc(S.molde.arquivo)}</span>: a competição que usa este placar passa a mostrar o do PES` : ''),
    radio('generic', 'No placar Generic', '<span class="mono">Generic/overlay_9002.big</span>: o placar padrão das partidas sem placar próprio'),
    radio('outro', 'Outro caminho', 'um <span class="mono">data/ui/…/….big</span> à sua escolha'))];
  if (S.alvo === 'outro') {
    const i = entrada({ value: S.alvoOutro, placeholder: 'data/ui/game/overlays/overlay_35002.big' });
    i.oninput = () => { S.alvoOutro = i.value; };
    i.onchange = () => desenharPropriedades();
    destino.push(i);
  }
  if (info?.subst && S.subst) {
    const as = alvoSubst(alvoPlacar());
    destino.push(as
      ? el('div', { class: 'mudo peq-txt', html: `A substituição vai para <span class="mono">${esc(as)}</span>.` })
      : nota('Esse destino não termina em <span class="mono">…002.big</span>: não sei qual é a substituição dele, e ela não será gravada.', 'alerta'));
  }
  const marcadas = extras().filter(extraMarcada);
  if (marcadas.length) {
    const ap = alvoPlacar();
    destino.push(alvoTela(ap, 9003)
      ? el('div', { class: 'mudo peq-txt', html: marcadas.map((x) => `${esc(x.titulo)}: <span class="mono">${esc(alvoTela(ap, x.numero))}</span>`).join('<br>') })
      : nota('Esse destino não termina em <span class="mono">…002.big</span>: não sei quais são as outras telas dele, e elas não serão gravadas.', 'alerta'));
  }
  const ed = S.inicio.editor;
  destino.push(campo('Pasta de saída do Editor de Placares', el('div', { class: 'caminho-saida' }, ed?.saida || '(não escolhida: abra o Editor de Placares e escolha em Arquivo › Pasta de saída)')));
  p.append(secao('Gravar', 'salvar', destino));
  // resultado
  if (S.ultimo) {
    const u = S.ultimo;
    const corpoGravado = [
      el('div', { class: 'mudo peq-txt' }, 'Placar'),
      el('div', { class: 'caminho-saida' }, u.destino),
      el('ul', { class: 'lista-resumo' }, ...u.resumo.map((t) => el('li', {}, t))),
    ];
    if (u.subst && !u.subst.erro) {
      corpoGravado.push(el('div', { class: 'mudo peq-txt' }, 'Substituição'), el('div', { class: 'caminho-saida' }, u.subst.destino),
        el('ul', { class: 'lista-resumo' }, ...u.subst.resumo.map((t) => el('li', {}, t))));
    } else if (u.subst?.erro) corpoGravado.push(nota(`A substituição não foi gravada: ${esc(u.subst.erro)}`, 'erro'));
    for (const t of u.telas || []) {
      if (t.erro) { corpoGravado.push(nota(`${esc(t.titulo)}: não foi gravada. ${esc(t.erro)}`, 'erro')); continue; }
      corpoGravado.push(el('div', { class: 'mudo peq-txt' }, t.titulo), el('div', { class: 'caminho-saida' }, t.destino),
        el('ul', { class: 'lista-resumo' }, ...t.resumo.map((x) => el('li', {}, x))));
    }
    const varias = (u.subst && !u.subst.erro) || (u.telas || []).some((t) => !t.erro);
    corpoGravado.push(
      nota('Abra o <b>Editor de Placares</b>: ' + (varias ? 'as telas gravadas aparecem' : 'o placar aparece') + ' em <b>Editados</b> e abrem com as alterações, para mover, trocar cores e fontes. Para ver no jogo, a pasta de saída precisa ser a <span class="mono">mods\\legacy</span> do Live Editor.'),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { caminho: u.destino })) }, el('span', { html: icone('externo', 12) }), 'Mostrar arquivo')));
    p.append(secao('Gravado', 'check', corpoGravado));
  }
  if (info) {
    const c = info.campos || {};
    const nomes = { nome_casa: 'Nome do mandante', nome_fora: 'Nome do visitante', gols_casa: 'Gols do mandante', gols_fora: 'Gols do visitante', relogio: 'Relógio', acrescimos: 'Acréscimos' };
    p.append(secao('O que o placar do PES tem', 'info', [
      el('dl', { class: 'kv' }, ...Object.keys(nomes).flatMap((k) => [el('dt', {}, nomes[k]), el('dd', {}, c[k] ? 'sim' : 'não achei')]),
        el('dt', {}, 'Substituição'), el('dd', {}, info.subst ? 'sim' : 'não achei'),
        el('dt', {}, 'Outras telas'), el('dd', {}, extras().length ? extras().map((x) => x.titulo).join(', ') : 'nenhuma')),
      el('div', { class: 'mudo peq-txt' }, `Arquivos: ${info.arquivos.join(', ')}. Filmes: ${info.filmes.join(', ')}. São convertidos o placar da partida (game2d_score), a substituição (game2d_memberChange) e as outras telas listadas acima.`),
    ], false));
  }
}

function desenharTudo() {
  const tem = S.placares.length > 0;
  $('#vazio-vista').hidden = tem;
  $('#previas').hidden = !tem;
  desenharTopo();
  desenharStatus();
  desenharPropriedades();
}

// ---------------------------------------------------------------- menus e início
function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { rotulo: 'Abrir pasta do placar ou do pacote…', icone: 'pasta', atalho: 'Ctrl+O', fn: escolherPasta },
      { rotulo: 'Ler a pasta de novo', icone: 'recarregar', desabilitado: !S.pasta, fn: () => abrirPasta(S.pasta) },
      '-',
      { rotulo: 'Mostrar a pasta do placar', icone: 'externo', desabilitado: !S.sel, fn: () => tentar(() => api('abrir', { caminho: S.sel })) },
      { rotulo: 'Exportar as telas, recortes e a fonte…', icone: 'baixar', desabilitado: !S.sel, fn: exportar },
      { rotulo: 'Mostrar o último arquivo gravado', icone: 'externo', desabilitado: !S.ultimo, fn: () => tentar(() => api('abrir', { caminho: S.ultimo.destino })) },
    ]],
    ['Converter', () => [
      { rotulo: 'Converter e gravar', icone: 'play', atalho: 'Ctrl+Enter', desabilitado: $('#btn-converter').disabled, fn: converter },
      { rotulo: 'Atualizar a lista de moldes', icone: 'recarregar', fn: () => carregarMoldes(true) },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Como funciona', icone: 'ajuda', fn: ajuda },
      { rotulo: 'Sobre', icone: 'info', fn: () => dialogoSobre({ nome: 'Conversor de Placares PES → FC', versao: S.inicio?.versao || '',
        html: 'Lê os placares do PES 2021 (os arquivos AFP/TXP2 da Konami em <span class="mono">common\\menu\\licence</span>) e monta o placar num molde do FC, como projeto do Editor de Placares. O formato AFP foi descrito pelo projeto bemaniutils (domínio público).' }) },
    ]],
  ]);
}

function ajuda() {
  modal({ titulo: 'Como funciona', largo: true, corpo: el('div', { style: { lineHeight: '1.6', color: 'var(--texto-2)' }, html: `
    <p><b>1. Abra o placar do PES.</b> A pasta com <span class="mono">common\\menu\\licence\\game2dPes.bin</span> (e os outros .bin do placar; num placar feito para uma licença o nome dela fica no lugar de Pes, como <span class="mono">game2dEngland.bin</span>) ou a pasta de um pacote com vários placares: cada um aparece na lista.</p>
    <p><b>2. Escolha o molde.</b> O <b>Generic</b> do próprio jogo (overlay_9002, o primeiro da lista) ou um placar do pack do LTA (overlay_35002 Brasileirão e os outros iguais, com o fundo numa imagem grande e os textos soltos). O conversor desenha o placar do PES no molde (no Generic, na imagem do logo do FC, atrás dos textos), apaga as decorações do molde e leva os nomes, o placar, o relógio, os acréscimos, as faixas das cores dos times e os cartões para os lugares do PES — inclusive as constantes do código que posicionam essas peças na animação.</p>
    <p><b>3. Grave.</b> O placar vai para a pasta de saída do Editor de Placares, como um projeto dele: abra o Editor de Placares, o placar está em <b>Editados</b>. Lá dá para ajustar tudo e ver a animação.</p>
    <p><b>Substituição.</b> Se o pacote tiver a tela de substituição, ela vai junto para a substituição do mesmo conjunto do placar (<span class="mono">…021.big</span>; no Generic, <span class="mono">overlay_9021</span>), com a do Generic do jogo como molde: a placa do PES aparece de cima para baixo, o escudo do time fica na caixa do escudo do PES e quem entra e quem sai, nas caixas do PES, com a cor que contrasta com cada uma. O painel aparece também com uma troca só (no FC, uma troca usa duas tarjas que outras telas também usam). Gravada fora do Generic, a classe do código ganha nome próprio, para não se misturar com a do Generic que as outras competições usam.</p>
    <p><b>Outras telas.</b> Vão junto, cada uma com um interruptor: os <b>pênaltis</b> (<span class="mono">…003.big</span>; no Generic, <span class="mono">overlay_9003</span>: a arte do PES, os nomes, os gols, os escudos e as bolinhas das cobranças nas lâmpadas do PES, com a entrada do FC) e o <b>gol</b> (<span class="mono">…075.big</span>; no Generic, <span class="mono">overlay_9075</span>, a tela que o FC mostra nos replays de gol e de expulsão: a arte do PES com o sobrenome do jogador, o lance e o minuto nas caixas do PES; ela aparece e some de uma vez). As telas de cartões, estatísticas e tarja do jogador do FC são desenhadas por componentes que muitas telas usam juntas, e não dá para vestir só uma delas com a arte do PES.</p>
    <p><b>Limites:</b> os nomes são escritos pelo FC com a fonte dele (gols e relógio podem usar os números desenhados do PES); são convertidos o placar da partida, a substituição, os pênaltis e o gol (escalação, intervalo e narradores ainda não); no Generic, a placa dos acréscimos do PES não aparece e os nomes longos alargam o placar; na substituição, com 2 ou 3 trocas ao mesmo tempo aparecem só a primeira que entra e a primeira que sai, e a faixa do título da placa (quando o PES escreve o título nela) fica vazia; e o resultado não foi conferido dentro do jogo em todos os moldes.</p>` }),
    botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

async function iniciar() {
  const r = await tentar(() => api('inicio'));
  if (!r) return;
  S.inicio = r;
  const pr = r.prefs || {};
  S.pos = { x: +pr.x || 64, y: +pr.y || 48, escala: +pr.escala || 1 };
  S.alvo = pr.alvo || 'molde';
  S.fontePes = pr.fonte_pes !== false;
  S.subst = pr.subst !== false;
  S.telasEsc = pr.telas && typeof pr.telas === 'object' ? { ...pr.telas } : {};
  S.alvoOutro = pr.alvo_outro || '';
  desenharTudo();
  if (!r.motor.ok) return;
  if (pr.pasta && !S.placares.length) abrirPasta(pr.pasta);
  if (S.moldes === null) carregarMoldes(false).then(() => { if (S.sel) atualizarPrevia(); desenharTopo(); });
}

$('#btn-pasta').innerHTML = icone('pasta', 15);
$('#btn-recarregar').innerHTML = icone('recarregar', 15);
$('#btn-converter-ic').innerHTML = icone('play', 14);
$('#soltar-ic').innerHTML = icone('placar', 64);
$('#btn-vazio-pasta').innerHTML = icone('pasta', 14) + ' Abrir pasta…';
$('#btn-pasta').onclick = escolherPasta;
$('#btn-vazio-pasta').onclick = escolherPasta;
$('#btn-recarregar').onclick = () => S.pasta && abrirPasta(S.pasta);
$('#btn-converter').onclick = converter;
$('#btn-exportar').innerHTML = icone('baixar', 12) + ' Exportar imagens';
$('#btn-exportar').onclick = exportar;
divisorArrastavel($('#div-esq'), '--esq', { min: 220, max: 480, lado: 'esq' });
divisorArrastavel($('#div-dir'), '--dir', { min: 280, max: 560, lado: 'dir' });
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); converter(); }
  if (e.ctrlKey && e.key.toLowerCase() === 'o') { e.preventDefault(); escolherPasta(); }
});
menus();
iniciar();
