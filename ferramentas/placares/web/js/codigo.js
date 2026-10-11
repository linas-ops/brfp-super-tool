// O que vem do código (ActionScript) do placar: as animações (constantes de tempo, posições e curvas) e as fontes
// dos textos (TextFormat com as famílias do tema FIFA.xml). Abas "Animação" e "Fontes" e as seções do painel
// de propriedades de um elemento.
import {
  A, CURVAS_ROTULO, ROTULO_PROP, curva, duracao, fmtQuadros, fps, irPara, resumoErros, tweensDe, usosDoSlot, ativar, tocar,
} from './animacao.js';
import { api } from './api.js';
import { S, definirOp, emitir } from './estado.js';
import { icone } from './icones.js';
import { carregarFonte } from './render.js';
import { $, aviso, campoNumero, confirmar, el, esc, fmtNum, modal, nota } from './ui.js';

export const C = {
  catalogo: null,       // resposta de /api/fontes_tema
  twSel: null,          // animação aberta na lista (chave estável)
};

// ---------------------------------------------------------------- utilidades
function secao(box, titulo, aberta = true, extra = null) {
  const d = el('details', { class: 'secao' });
  d.open = aberta;
  const s = el('summary', { html: icone('seta', 12, 'seta') + esc(titulo) });
  if (extra) s.append(extra);
  d.append(s);
  const c = el('div', { class: 'secao-corpo' });
  d.append(c);
  box.append(d);
  return c;
}

const ultimo = (cam) => String(cam || '').split('.').pop();
// "m:<slot>|ALPHA_FULL": valor que vem do tema (FIFA.xml) pelo nome — o número não fica no placar
const doTema = (slot) => String(slot || '').startsWith('m:');
const editavel = (slot) => !!slot && !doTema(slot);

function limitesSlot(slot) {
  const t = String(slot).split(':')[0];
  if (t === 'pb') return { min: 0, max: 255, inteiro: true, dica: 'Este número fica num byte do código: inteiro de 0 a 255.' };
  if (t === 'ps') return { min: 0, max: 65535, inteiro: true, dica: 'Inteiro de 0 a 65535.' };
  if (t === 'pl') return { min: 0, max: 4294967295, inteiro: true, dica: 'Inteiro positivo.' };
  return { min: -1e7, max: 1e7, inteiro: false, dica: '' };
}

function valorAtual(slot, valorSim) {
  const op = S.doc.ops['const:' + slot];
  return op ? op.valor : valorSim;
}

export function definirConst(slot, v, valorSim, nome = '') {
  const lim = limitesSlot(slot);
  v = Math.min(lim.max, Math.max(lim.min, lim.inteiro ? Math.round(v) : Math.round(v * 1000) / 1000));
  const chave = 'const:' + slot;
  const op = S.doc.ops[chave];
  const orig = op ? op.orig : valorSim;
  definirOp(nome ? `Constante ${nome}` : 'Valor da animação', chave, v === orig ? null : { op: 'const', slot, valor: v, orig, nome }, { fundir: false });
}

export function definirTexto(slot, texto, textoSim, rotulo) {
  const chave = 'const_txt:' + slot;
  const op = S.doc.ops[chave];
  const orig = op ? op.orig : textoSim;
  definirOp(rotulo, chave, texto === orig ? null : { op: 'const_txt', slot, texto, orig }, { fundir: false });
}

function campoConst(slot, valorSim, { nome = '', titulo = '', passo = 1, casas = 2 } = {}) {
  const lim = limitesSlot(slot);
  const op = S.doc.ops['const:' + slot];
  const c = campoNumero({ valor: valorAtual(slot, valorSim), passo, casas, min: lim.min, max: lim.max, passoCtrl: 1,
    titulo: [titulo, lim.dica, op ? `Original: ${fmtNum(op.orig, 3)}` : ''].filter(Boolean).join('\n'),
    aoConfirmar: (v) => definirConst(slot, v, valorSim, nome) });
  c.marcar(!!op);
  return c;
}

function noDoCaminho(cam) {
  const l = A.mapa.get(cam);
  return l && l.length ? l[0] : null;
}

function selecionarCaminho(cam) {
  const n = noDoCaminho(cam);
  if (!n) return;
  S.sel = n.id;
  S.selImagem = null;
  emitir('selecao', 'codigo');
}

const chaveTw = (tw, i, lista) => {
  let n = 0;
  for (let k = 0; k < i; k++) if (lista[k].alvo === tw.alvo && lista[k].prop === tw.prop) n++;
  return `${tw.alvo}|${tw.prop}|${n}`;
};

// ---------------------------------------------------------------- aba Animação
export function desenharAnimacao() {
  const box = $('#aba-animacao-corpo');
  if (!box) return;
  const rolagem = box.scrollTop;
  box.innerHTML = '';
  if (!S.doc) { box.append(el('div', { class: 'lista-vazia' }, 'Abra um placar para ver as animações.')); return; }
  const d = A.dados;
  if (!d) {
    box.append(el('div', { class: 'lista-vazia' }, A.erro ? 'A simulação falhou: ' + A.erro : 'Simulando o código do placar…'));
    return;
  }
  const topo = el('div', { class: 'anim-topo' });
  const btVer = el('button', { class: S.animando ? 'btn peq ativo-azul' : 'btn-primario peq', html: icone(S.animando ? 'x' : 'play', 13) + (S.animando ? 'Sair da prévia' : 'Ver a animação') });
  btVer.onclick = () => { if (S.animando) ativar(false); else { ativar(true); irPara(0); tocar(); } };
  topo.append(btVer);
  const tws = d.tweens || [];
  if (d.classe) {
    topo.append(el('div', { class: 'anim-resumo' },
      el('b', {}, `${tws.length} animaç${tws.length === 1 ? 'ão' : 'ões'}`),
      ` · ${fmtQuadros(d.duracao || 0)} · ${fps()} qps`));
  }
  box.append(topo);
  if (!d.classe) {
    box.append(el('div', { style: { padding: '0 10px' } }, nota('Este arquivo não tem uma classe de placar com animações (é estático ou só guarda peças usadas por outros).', 'info')));
    return;
  }
  const errosHtml = resumoErros();
  if (errosHtml) box.append(el('div', { style: { padding: '0 10px 8px' } }, nota('A simulação é aproximada e encontrou trechos que não entendeu:<br><small>' + errosHtml + '</small>', 'alerta')));
  if (!d.bibliotecas) box.append(el('div', { style: { padding: '0 10px 8px' } }, nota('Não achei o AnimationManager do jogo: as curvas da prévia são aproximadas.', 'alerta')));
  if (!tws.length) {
    box.append(el('div', { class: 'lista-vazia' }, 'O método escolhido não anima nada.'));
  } else {
    box.append(gantt(tws));
  }
  // constantes
  const usadas = new Map();
  for (const tw of tws) for (const k of ['dur', 'atraso', 'para']) if (tw[k + '_const'] && tw[k + '_slot']) usadas.set(tw[k + '_slot'], tw[k + '_const']);
  const consts = (d.constantes || []).filter((c) => typeof c.valor === 'number');
  const naAnim = consts.filter((c) => usadas.has(c.slot));
  const outras = consts.filter((c) => !usadas.has(c.slot));
  const s1 = secao(box, `Constantes usadas nas animações (${naAnim.length})`, true);
  if (!naAnim.length) s1.append(el('div', { class: 'mudo' }, 'As animações deste placar usam números escritos direto no código (edite pela lista acima).'));
  for (const c of naAnim) s1.append(linhaConst(c));
  if (outras.length) {
    const s2 = secao(box, `Outras constantes da classe (${outras.length})`, false);
    s2.append(nota('Números que o código do placar usa para outras coisas (posições, tamanhos, tempos de espera…). Mudar pode ter efeitos inesperados.', ''));
    for (const c of outras) s2.append(linhaConst(c));
  }
  box.scrollTop = rolagem;
  atualizarCabeca();
}

function linhaConst(c) {
  const usos = usosDoSlot(c.slot);
  const lin = el('div', { class: 'linha-const' + (S.doc.ops['const:' + c.slot] ? ' alterada' : ''), title: `${c.classe}.${c.nome}${usos ? `\nusada em ${usos} animação(ões)` : ''}` });
  const nome = el('span', { class: 'nome' }, c.nome);
  const campo = campoConst(c.slot, c.valor, { nome: c.nome, titulo: c.nome, casas: 2 });
  lin.append(nome, campo.el);
  if (/DUR|DELAY|TIME|WAIT/i.test(c.nome)) lin.append(el('span', { class: 'unid', title: 'quadros' }, 'q'));
  return lin;
}

function gantt(tws) {
  const dur = duracao();
  const g = el('div', { class: 'gantt', id: 'gantt' });
  const regua = el('div', { class: 'gantt-regua' });
  regua.append(el('span', {}, '0'), el('span', {}, (dur / fps()).toFixed(2).replace('.', ',') + ' s'));
  g.append(regua);
  const corpo = el('div', { class: 'gantt-corpo' });
  const cabeca = el('div', { class: 'gantt-cabeca', id: 'gantt-cabeca' });
  corpo.append(cabeca);
  // clique na régua/barras: vai para o instante
  const tempoDoClique = (e, alvo) => {
    const r = alvo.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * dur;
  };
  regua.onclick = (e) => irPara(tempoDoClique(e, regua));
  const selNo = S.sel;
  tws.forEach((tw, i) => {
    const chave = chaveTw(tw, i, tws);
    const no = noDoCaminho(tw.alvo);
    const ab = C.twSel === chave;
    const lin = el('div', { class: 'gantt-lin' + (ab ? ' aberta' : '') + (no && no.id === selNo ? ' sel' : ''),
      title: `${tw.alvo}\n${ROTULO_PROP[tw.prop_original || tw.prop] || tw.prop}: ${fmtNum(tw.de, 1)} → ${fmtNum(tw.para_original ?? tw.para, 1)}\ncomeça no quadro ${fmtNum(tw.t0, 1)}, dura ${fmtNum(tw.dur, 1)} · curva ${tw.ease}` });
    const rot = el('span', { class: 'rot' }, el('b', {}, ultimo(tw.alvo)), ' ', el('small', {}, ROTULO_PROP[tw.prop_original || tw.prop] || tw.prop));
    const trilho = el('span', { class: 'trilho' });
    const editado = [tw.dur_slot, tw.atraso_slot, tw.para_slot].some((s) => s && S.doc.ops['const:' + s]) || (tw.ease_slot && S.doc.ops['const_txt:' + tw.ease_slot]);
    trilho.append(el('span', { class: 'barra p' + (tw.prop || '').replace(/[^a-z]/g, '') + (editado ? ' editada' : ''),
      style: { left: (tw.t0 / dur * 100) + '%', width: Math.max(0.8, tw.dur / dur * 100) + '%' } }));
    lin.append(rot, trilho);
    lin.onclick = (e) => {
      C.twSel = ab ? null : chave;
      if (!ab) {
        irPara(e.target.closest('.trilho') ? tempoDoClique(e, trilho) : tw.t0);
        if (no) { S.sel = no.id; S.selImagem = null; emitir('selecao', 'codigo'); }
      }
      desenharAnimacao();
    };
    corpo.append(lin);
    if (ab) corpo.append(editorTween(tw));
  });
  g.append(corpo);
  return g;
}

export function atualizarCabeca() {
  const c = $('#gantt-cabeca');
  if (!c) return;
  c.style.setProperty('--p', Math.min(1, A.t / duracao()));
  c.hidden = !S.animando;
}

// editor de uma animação: duração, atraso, destino e curva — cada um ligado ao lugar do código de onde vem
function editorTween(tw) {
  const box = el('div', { class: 'tw-editor' });
  const prop = tw.prop_original || tw.prop;
  box.append(el('div', { class: 'tw-tit' }, el('b', {}, ultimo(tw.alvo)), ' · ', ROTULO_PROP[prop] || prop,
    el('small', {}, ` ${tw.metodo || ''}`)));
  const linha = (rot, ctrl, info = '') => {
    const l = el('div', { class: 'linha-prop' }, el('label', {}, rot), el('div', { class: 'tw-ctrl' }, ctrl, info ? el('small', { class: 'mudo' }, info) : null));
    box.append(l);
  };
  const origem = (slot, nomeConst) => {
    if (!slot) return 'calculado pelo código';
    if (doTema(slot)) return `valor do tema: ${String(slot).split('|')[1]} (FIFA.xml)`;
    const n = usosDoSlot(slot);
    return (nomeConst ? `constante ${nomeConst}` : 'número no código') + (n > 1 ? ` · vale para ${n} animações` : '');
  };
  const destino = tw.para_original ?? tw.para;
  if (typeof destino === 'number') {
    linha('Destino', editavel(tw.para_slot) ? campoConst(tw.para_slot, destino, { nome: tw.para_const || '', titulo: 'Valor final' }).el : el('span', {}, fmtNum(destino, 2)),
      `de ${fmtNum(tw.de_original ?? tw.de, 1)} · ${origem(tw.para_slot, tw.para_const)}`);
  }
  linha('Duração', editavel(tw.dur_slot) ? campoConst(tw.dur_slot, tw.dur, { nome: tw.dur_const || '', titulo: 'Duração em quadros' }).el : el('span', {}, fmtNum(tw.dur, 1)),
    `${fmtQuadros(tw.dur)} · ${origem(tw.dur_slot, tw.dur_const)}`);
  if (editavel(tw.atraso_slot)) {
    linha('Atraso', campoConst(tw.atraso_slot, valorDoSlot(tw), { nome: tw.atraso_const || '', titulo: 'Espera antes de começar (quadros)' }).el,
      origem(tw.atraso_slot, tw.atraso_const));
  }
  linha('Começa', el('span', {}, fmtQuadros(tw.t0)));
  // curva
  const nomes = (A.dados && A.dados.curvas_nomes) || {};
  const prev = el('canvas', { class: 'curva-prev', width: 120, height: 64 });
  if (tw.ease_slot && Object.keys(nomes).length) {
    const sel = el('select', { class: 'seletor largo' });
    const opAtual = S.doc.ops['const_txt:' + tw.ease_slot];
    const atualTxt = opAtual ? opAtual.texto : (tw.ease_literal ? tw.ease : tw.ease_const);
    const vistos = new Set();
    for (const [k, v] of Object.entries(nomes).sort((a, b) => a[1].localeCompare(b[1]))) {
      const valor = tw.ease_literal ? v : k;
      if (vistos.has(valor) || v === 'custom') continue;
      vistos.add(valor);
      sel.append(el('option', { value: valor }, `${v} — ${CURVAS_ROTULO[v] || ''}`));
    }
    sel.value = atualTxt;
    sel.onchange = () => definirTexto(tw.ease_slot, sel.value, tw.ease_literal ? tw.ease : tw.ease_const, 'Curva da animação');
    const valorCurva = () => (tw.ease_literal ? sel.value : nomes[sel.value]) || tw.ease;
    sel.oninput = () => desenharCurva(prev, valorCurva());
    linha('Curva', sel, origem(tw.ease_slot, null).replace('número no código', 'trecho do código'));
    desenharCurva(prev, valorCurva());
  } else {
    linha('Curva', el('span', {}, `${tw.ease} — ${CURVAS_ROTULO[tw.ease] || ''}`), tw.ease_slot ? '' : 'definida em outro lugar');
    desenharCurva(prev, tw.ease);
  }
  box.append(el('div', { class: 'curva-caixa' }, prev));
  return box;
}

// valor do atraso como a simulação viu (campoConst mostra o da operação, se houver)
function valorDoSlot(tw) {
  if (typeof tw.atraso === 'number') return tw.atraso;
  const c = (A.dados.constantes || []).find((x) => x.slot === tw.atraso_slot);
  return c ? c.valor : 0;
}

function desenharCurva(cv, nome) {
  const g = cv.getContext('2d');
  const w = cv.width, h = cv.height, m = 8;
  g.clearRect(0, 0, w, h);
  g.strokeStyle = 'rgba(255,255,255,.12)';
  g.lineWidth = 1;
  g.strokeRect(m + 0.5, m + 0.5, w - 2 * m - 1, h - 2 * m - 1);
  g.strokeStyle = '#4c8dff';
  g.lineWidth = 2;
  g.beginPath();
  for (let i = 0; i <= 60; i++) {
    const p = i / 60;
    const y = h - m - curva(nome, p) * (h - 2 * m);
    const x = m + p * (w - 2 * m);
    if (i) g.lineTo(x, y); else g.moveTo(x, y);
  }
  g.stroke();
}

// ---------------------------------------------------------------- seções do painel de propriedades
export function secoesNo(box, no) {
  if (!S.doc || !A.dados || !no.caminho) return;
  const tws = tweensDe(no.caminho);
  if (tws.length) {
    const c = secao(box, `Animação (${tws.length})`, true);
    const pos = tws.filter((t) => (t.prop === '_x' || t.prop === '_y') && typeof t.para === 'number');
    if (pos.length && no.editavel) {
      const txt = pos.map((t) => `${ROTULO_PROP[t.prop]} = ${fmtNum(t.para, 1)}${t.para_const ? ` (${t.para_const})` : ''}`).join(', ');
      c.append(nota(`No jogo a animação leva este elemento até <b>${esc(txt)}</b>. ` +
        (pos.some((t) => t.para_slot) ? 'Para mudar onde ele termina, mude o destino abaixo — mover na prévia muda a posição antes da animação.' :
          'O destino é calculado pelo código a partir da posição do arquivo.'), 'info'));
    }
    const lista = A.dados.tweens;
    for (const tw of tws) {
      const i = lista.indexOf(tw);
      const k = chaveTw(tw, i, lista);
      const lin = el('button', { class: 'tw-mini' + (C.twSel === k ? ' aberta' : '') });
      lin.append(el('span', {}, ROTULO_PROP[tw.prop_original || tw.prop] || tw.prop), el('small', {}, `${fmtNum(tw.de, 1)} → ${fmtNum(tw.para_original ?? tw.para, 1)} · q ${fmtNum(tw.t0, 1)}–${fmtNum(tw.t0 + tw.dur, 1)} · ${tw.ease}`));
      lin.onclick = () => { C.twSel = C.twSel === k ? null : k; irPara(tw.t0); emitir('props-externas'); };
      c.append(lin);
      if (C.twSel === k) c.append(editorTween(tw));
    }
    const ac = el('div', { class: 'acoes-linha' });
    ac.append(el('button', { class: 'btn peq', html: icone('play', 12) + 'Ver a animação', onclick: () => { ativar(true); irPara(0); tocar(); } }));
    c.append(ac);
  }
  const cfg = A.dados.textos && A.dados.textos[no.caminho];
  if (cfg && cfg.config && cfg.config.formato) {
    const c = secao(box, 'Fonte do texto (código do placar)', true);
    c.append(editorFormato(cfg.config.formato, { compacto: true }));
    const al = alinhamentoDe(cfg.config);
    if (al) c.append(el('div', { class: 'mudo' }, `Alinhamento definido pelo código: ${{ left: 'esquerda', center: 'centro', right: 'direita' }[al]}.`));
  }
}

// painel do arquivo (nada selecionado): resumo do que o código faz
export function secaoArquivo(box) {
  const c = secao(box, 'Animação e fontes (código do placar)', true);
  const d = A.dados;
  if (!d) { c.append(el('div', { class: 'mudo' }, A.erro ? 'A simulação falhou: ' + A.erro : 'Lendo o código do placar…')); return; }
  if (!d.classe) { c.append(el('div', { class: 'mudo' }, 'Este arquivo não tem código de placar (é estático ou só guarda peças).')); return; }
  const n = (d.tweens || []).length, f = (d.formatos || []).length;
  c.append(el('div', { class: 'estatisticas' },
    el('div', { class: 'estatistica' }, el('b', {}, String(n)), el('span', {}, `animações · ${fmtQuadros(d.duracao || 0).split(' · ')[1]}`)),
    el('div', { class: 'estatistica' }, el('b', {}, String(f)), el('span', {}, 'formatos de texto'))));
  c.append(nota('As animações do placar são feitas pelo código (não por quadros desenhados): a prévia roda esse código e mostra o resultado. ' +
    'Na aba <b>Animação</b> dá para mudar tempos, posições e curvas; na aba <b>Fontes</b>, as fontes e tamanhos dos textos.', 'info'));
  const ac = el('div', { class: 'acoes-linha' });
  if (n) ac.append(el('button', { class: 'btn-primario peq', html: icone('play', 12) + 'Ver a animação', onclick: () => { ativar(true); irPara(0); tocar(); } }));
  ac.append(el('button', { class: 'btn peq', onclick: () => emitir('aba', 'animacao') }, 'Aba Animação'));
  ac.append(el('button', { class: 'btn peq', onclick: () => emitir('aba', 'fontes') }, 'Aba Fontes'));
  c.append(ac);
}

// ---------------------------------------------------------------- fontes
export async function carregarCatalogo() {
  try { C.catalogo = await api('fontes_tema'); } catch (ex) { C.catalogo = { erro: ex.message, familias: [], faces: [] }; }
  emitir('catalogo');
  return C.catalogo;
}

function faceDaChave(chave) {
  const f = C.catalogo && (C.catalogo.familias || []).find((x) => x.chave === chave);
  return f ? f.face : null;
}

function chaveEfetiva(fmt) {
  const op = fmt.fonte_slot && S.doc.ops['const_txt:' + fmt.fonte_slot];
  return op ? op.texto : fmt.fonte_chave;
}

function alinhamentoDe(config) {
  const p = (config && config.partes) || [];
  if (p.includes('H_ALIGN_LEFT')) return 'left';
  if (p.includes('H_ALIGN_RIGHT')) return 'right';
  if (p.includes('H_ALIGN_CENTER')) return 'center';
  return null;
}

// estilo de um componente de texto (MultiText) para a prévia: face da fonte, alinhamento e cor
export function estiloTexto(no) {
  if (!A.dados || !no.caminho || !A.dados.textos) return null;
  const t = A.dados.textos[no.caminho];
  if (!t || !t.config || !t.config.formato) return null;
  const f = t.config.formato;
  const cor = typeof f.cor === 'number' ? [(f.cor >> 16) & 255, (f.cor >> 8) & 255, f.cor & 255] : null;
  return { face: faceDaChave(chaveEfetiva(f)), alinh: alinhamentoDe(t.config), cor };
}

function usosDoFormato(fmt) {
  const out = [];
  for (const [cam, t] of Object.entries((A.dados && A.dados.textos) || {})) {
    const f = t.config && t.config.formato;
    if (f && f.fonte_slot === fmt.fonte_slot && f.tamanho_slot === fmt.tamanho_slot) out.push(cam);
  }
  return out;
}

function amostra(face, tamanho = 18) {
  const s = el('div', { class: 'amostra-fonte', title: face ? `data/ui/fonts/${face}.ttf` : '' }, 'MANDANTE 2×1 VISITANTE 45:00');
  if (face) {
    carregarFonte(face).then((ok) => { s.style.fontFamily = ok ? `"apt_${face}", sans-serif` : ''; if (!ok) s.classList.add('sem-ttf'); });
  }
  s.style.fontSize = Math.max(11, Math.min(17, tamanho)) + 'px';
  return s;
}

function editorFormato(fmt, { compacto = false } = {}) {
  const box = el('div', { class: 'cartao-fmt' });
  const chave = chaveEfetiva(fmt);
  const face = faceDaChave(chave);
  const opFonte = fmt.fonte_slot && S.doc.ops['const_txt:' + fmt.fonte_slot];
  const opTam = fmt.tamanho_slot && S.doc.ops['const:' + fmt.tamanho_slot];
  if (opFonte || opTam) box.classList.add('alterado');
  // família
  const fams = (C.catalogo && C.catalogo.familias) || [];
  if (fmt.fonte_slot && fams.length) {
    const sel = el('select', { class: 'seletor largo' });
    const grupoUsadas = el('optgroup', { label: 'Famílias do tema (FIFA.xml)' });
    for (const f of fams) grupoUsadas.append(el('option', { value: f.chave }, `${f.chave.replace(/^FONT_NAME_/, '')} — ${f.face}${f.ttf ? '' : ' (sem arquivo!)'}${f.minha ? ' ★' : ''}`));
    sel.append(grupoUsadas);
    if (!fams.some((f) => f.chave === chave)) sel.append(el('option', { value: chave }, chave));
    sel.value = chave;
    sel.onchange = () => definirTexto(fmt.fonte_slot, sel.value, fmt.fonte_chave, 'Fonte do texto');
    box.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Fonte'), sel));
  } else {
    box.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Fonte'), el('span', {}, `${chave}${face ? ' — ' + face : ''}`)));
  }
  if (typeof fmt.tamanho === 'number') {
    const tam = editavel(fmt.tamanho_slot) ? campoConst(fmt.tamanho_slot, fmt.tamanho, { nome: '', titulo: 'Tamanho da letra (o componente ainda ajusta ao espaço)', casas: 1 }).el : el('span', {}, fmtNum(fmt.tamanho, 1));
    box.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Tamanho'), tam));
  }
  box.append(amostra(face, fmt.tamanho || 18));
  if (!compacto) {
    const usos = usosDoFormato(fmt);
    if (usos.length) {
      const u = el('div', { class: 'usos' }, el('small', { class: 'mudo' }, 'Usado em: '));
      for (const cam of usos) {
        const b = el('button', { class: 'chip', title: cam }, ultimo(cam));
        b.onclick = () => selecionarCaminho(cam);
        u.append(b);
      }
      box.append(u);
    }
  }
  if (opFonte || opTam) {
    const r = el('button', { class: 'btn-fantasma peq', onclick: () => {
      if (opFonte) definirOp('Restaurar fonte', 'const_txt:' + fmt.fonte_slot, null);
      if (opTam) definirOp('Restaurar tamanho', 'const:' + fmt.tamanho_slot, null);
    } }, 'Restaurar original');
    box.append(r);
  }
  return box;
}

export function desenharFontes() {
  const box = $('#aba-fontes-corpo');
  if (!box) return;
  const rolagem = box.scrollTop;
  box.innerHTML = '';
  if (!S.doc) { box.append(el('div', { class: 'lista-vazia' }, 'Abra um placar para ver as fontes.')); return; }
  const cat = C.catalogo;
  if (!cat) { box.append(el('div', { class: 'lista-vazia' }, 'Lendo as fontes do tema…')); carregarCatalogo(); return; }
  // formatos do código
  const fmts = (A.dados && A.dados.formatos) || [];
  const s1 = secao(box, `Textos do placar (${fmts.length})`, true);
  if (!A.dados) s1.append(el('div', { class: 'mudo' }, A.erro ? 'A simulação falhou: ' + A.erro : 'Lendo o código do placar…'));
  else if (!fmts.length) s1.append(el('div', { class: 'mudo' }, 'O código deste arquivo não cria formatos de texto (os textos usam as fontes dos componentes).'));
  else {
    s1.append(nota('Cada formato é um <code>new TextFormat(família, tamanho)</code> no código do placar. Trocar a família muda a fonte dos textos que usam o formato (nomes dos times, placar, relógio…).', ''));
    for (const f of fmts) s1.append(editorFormato(f));
  }
  // fontes embutidas (campos de texto do próprio arquivo)
  const fontesArq = S.doc.filme.fontes();
  if (fontesArq.length) {
    const s2 = secao(box, `Campos de texto do arquivo (${fontesArq.length})`, false);
    s2.append(nota('Fontes usadas pelos campos de texto desenhados no próprio arquivo (o nome é o do arquivo .ttf em data/ui/fonts). ' +
      'Prefira fontes que tenham uma família no FIFA.xml — é assim que o jogo carrega a fonte (importar uma fonte já cria a família).', ''));
    const comFamilia = new Set((cat.familias || []).map((f) => f.face.toLowerCase()));
    for (const ft of fontesArq) {
      const base = S.doc.filme.base.chars[ft.i].nome;
      const sel = el('select', { class: 'seletor largo' });
      const faces = [...new Set([base, ...(cat.faces || [])])];
      for (const f of faces) {
        sel.append(el('option', { value: f }, f + (f === base ? ' (original)' : '') + (comFamilia.has(f.toLowerCase()) ? '' : ' · sem família no FIFA.xml')));
      }
      sel.value = ft.nome;
      sel.onchange = () => definirOp('Fonte do campo de texto', 'fonte_char:' + ft.i, sel.value === base ? null : { op: 'fonte_char', char: ft.i, nome: sel.value }, { fundir: false });
      s2.append(el('div', { class: 'linha-prop' }, el('label', {}, `Fonte #${ft.i}`), sel));
    }
  }
  // tema
  const s3 = secao(box, 'Fontes do tema (FIFA.xml)', true);
  const imp = el('div', { class: 'acoes-linha' });
  imp.append(el('button', { class: 'btn-primario peq', html: icone('upload', 13) + 'Importar fonte (.ttf)…', onclick: () => importarFonte() }));
  s3.append(imp);
  const base = cat.base && cat.base.xml;
  const mods = cat.mods || [];
  s3.append(nota(`As fontes novas vão para <code>data/ui/fonts</code> na pasta de saída, junto com um <b>FIFA.xml</b> e um <b>font_extents.txt</b> ` +
    `montados a partir da versão em uso${base ? ` (<b>${esc(base)}</b>)` : cat.xml_origem ? ` (<b>${esc(cat.xml_origem)}</b>)` : ''}. ` +
    (mods.length ? 'Os mods da lista de fontes entram como base, então as fontes e cores deles continuam valendo.' :
      'Se você usa o pack do LTA, adicione o .fifamod em <b>Arquivo › Fontes</b> antes de importar: o FIFA.xml da saída substitui o dos mods.'), mods.length ? 'info' : 'alerta'));
  if (cat.desatualizado) {
    const b = el('button', { class: 'btn peq', onclick: async () => { try { C.catalogo = await api('fonte_tema_atualizar'); emitir('catalogo'); aviso('FIFA.xml refeito', { tipo: 'sucesso' }); } catch (ex) { aviso(ex.message, { tipo: 'erro' }); } } }, 'Refazer com a base atual');
    s3.append(nota('A base do FIFA.xml mudou desde que ele foi gravado na saída (um mod foi adicionado ou trocado).', 'alerta'), b);
  }
  if (cat.erro) s3.append(nota(esc(cat.erro), 'alerta'));
  const usadas = new Set(fmts.map((f) => chaveEfetiva(f)));
  const lista = (cat.familias || []);
  const emUso = lista.filter((f) => usadas.has(f.chave) || f.minha);
  const resto = lista.filter((f) => !usadas.has(f.chave) && !f.minha);
  const linhaFam = (f) => {
    const lin = el('div', { class: 'linha-fam' + (f.minha ? ' minha' : '') + (f.ttf ? '' : ' falta') });
    lin.append(el('span', { class: 'k', title: f.chave }, f.chave.replace(/^FONT_NAME_/, '')), el('span', { class: 'v', title: f.ttf ? '' : 'Não achei data/ui/fonts/' + f.face + '.ttf' }, f.face));
    const b = el('button', { class: 'btn-icone peq', title: 'Trocar o arquivo de fonte desta família (vale para todos os placares)', html: icone('pincel', 13) });
    b.onclick = () => trocarFaceFamilia(f);
    lin.append(b);
    if (f.minha) {
      const x = el('button', { class: 'btn-icone peq', title: 'Desfazer (tira do FIFA.xml da saída)', html: icone('x', 13) });
      x.onclick = async () => {
        if (!(await confirmar('Desfazer esta família?', `Tira <b>${esc(f.chave)}</b> → ${esc(f.face)} do FIFA.xml da saída.`, { rotulo: 'Desfazer' }))) return;
        try { C.catalogo = await api('fonte_tema_remover', { chave: f.chave }); emitir('catalogo'); } catch (ex) { aviso(ex.message, { tipo: 'erro' }); }
      };
      lin.append(x);
    }
    return lin;
  };
  if (emUso.length) {
    s3.append(el('div', { class: 'sub-cab' }, 'Usadas neste placar e as suas'));
    for (const f of emUso) s3.append(linhaFam(f));
  }
  if (resto.length) {
    const d = el('details', { class: 'mais-fams' });
    d.append(el('summary', {}, `Todas as famílias (${resto.length})`));
    for (const f of resto) d.append(linhaFam(f));
    s3.append(d);
  }
  box.scrollTop = rolagem;
}

async function trocarFaceFamilia(f) {
  const cat = C.catalogo;
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } });
  corpo.append(nota(`Troca o arquivo de fonte da família <b>${esc(f.chave)}</b> no FIFA.xml da saída. ` +
    '<b>Vale para todos os placares e menus</b> que usam essa família. Para mudar só este placar, escolha outra família no texto.', 'alerta'));
  const sel = el('select', { class: 'seletor largo' });
  for (const face of cat.faces || []) sel.append(el('option', { value: face }, `${face}  · ${(cat.faces_origem || {})[face] || ''}`));
  sel.value = f.face;
  const prev = el('div', {});
  const mostrar = () => { prev.innerHTML = ''; prev.append(amostra(sel.value, 22)); };
  sel.onchange = mostrar;
  mostrar();
  corpo.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Fonte'), sel), prev);
  const v = await modal({ titulo: 'Trocar a fonte de uma família', corpo, largo: true,
    botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Gravar no FIFA.xml da saída', classe: 'btn-primario', padrao: true, fn: () => sel.value }] }).promessa;
  if (!v || v === f.face) return;
  try {
    C.catalogo = await api('fonte_tema_definir', { chave: f.chave, face: v });
    emitir('catalogo');
    aviso('Família atualizada', { tipo: 'sucesso', detalhe: `${f.chave} → ${v}` });
  } catch (ex) { aviso(ex.message, { tipo: 'erro' }); }
}

async function importarFonte() {
  if (!S.inicio.saida.caminho) { aviso('Escolha a pasta de saída primeiro (Arquivo › Pasta de saída).', { tipo: 'erro' }); return; }
  const r = await api('dialogo', { modo: 'fonte' });
  if (!r.caminho) return;
  const nomeArq = r.caminho.split(/[\\/]/).pop().replace(/\.(ttf|otf)$/i, '');
  const face0 = nomeArq.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 60) || 'MinhaFonte';
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } });
  corpo.append(nota(`Arquivo: <code>${esc(r.caminho)}</code>`, ''));
  const inpFace = el('input', { type: 'text', class: 'campo-texto', value: face0, spellcheck: 'false' });
  const inpChave = el('input', { type: 'text', class: 'campo-texto', value: 'FONT_NAME_' + face0.toUpperCase().replace(/[^A-Z0-9]/g, '_'), spellcheck: 'false' });
  inpFace.oninput = () => { inpChave.value = 'FONT_NAME_' + inpFace.value.toUpperCase().replace(/[^A-Z0-9]/g, '_'); };
  corpo.append(el('div', { class: 'linha-prop larga' }, el('label', {}, 'Nome do arquivo'), inpFace),
    el('small', { class: 'mudo' }, 'Vira data/ui/fonts/<nome>.ttf. Use letras, números, - e _ (o nome interno da fonte não importa).'),
    el('div', { class: 'linha-prop larga' }, el('label', {}, 'Família'), inpChave),
    el('small', { class: 'mudo' }, 'O nome que o código do placar usa (StyleManager.FONT_NAME_…).'));
  const fmts = (A.dados && A.dados.formatos || []).filter((f) => f.fonte_slot);
  const marcas = [];
  if (fmts.length) {
    corpo.append(el('b', {}, 'Usar nos textos deste placar:'));
    for (const f of fmts) {
      const cb = el('input', { type: 'checkbox' });
      cb.checked = true;
      marcas.push([cb, f]);
      const usos = usosDoFormato(f).map(ultimo).join(', ');
      corpo.append(el('label', { class: 'check-linha' }, cb, el('span', {}, `${chaveEfetiva(f).replace(/^FONT_NAME_/, '')} ${fmtNum(f.tamanho, 1)} px`), el('small', { class: 'mudo' }, usos ? ' — ' + usos : '')));
    }
  }
  const v = await modal({ titulo: 'Importar fonte', corpo, largo: true,
    botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Importar', classe: 'btn-primario', padrao: true, fn: () => ({ face: inpFace.value.trim(), chave: inpChave.value.trim() }) }] }).promessa;
  if (!v) return;
  try {
    let resp;
    try {
      resp = await api('fonte_importar', { caminho: r.caminho, face: v.face, chave: v.chave });
    } catch (ex) {
      if (!/Já existe uma fonte/.test(ex.message)) throw ex;
      if (!(await confirmar('Substituir a fonte do jogo?', esc(ex.message) + '<br>Substituir troca essa fonte em <b>todo o jogo</b>.', { rotulo: 'Substituir', perigo: true }))) return;
      resp = await api('fonte_importar', { caminho: r.caminho, face: v.face, chave: v.chave, substituir: true });
    }
    C.catalogo = resp;
    const chave = (resp.minhas || []).find((x) => x.face.toLowerCase() === v.face.replace(/[^A-Za-z0-9_-]/g, '').toLowerCase());
    const k = chave ? chave.chave : v.chave;
    let n = 0;
    for (const [cb, f] of marcas) if (cb.checked) { definirTexto(f.fonte_slot, k, f.fonte_chave, 'Fonte do texto'); n++; }
    emitir('catalogo');
    aviso('Fonte importada', { tipo: 'sucesso', detalhe: `${k} → data/ui/fonts/${v.face}.ttf na saída` + (n ? ` · aplicada em ${n} formato(s): salve o placar para gravar.` : '') });
  } catch (ex) { aviso('Não consegui importar: ' + ex.message, { tipo: 'erro' }); }
}

