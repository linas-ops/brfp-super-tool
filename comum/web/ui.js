// BRFP Super Tool — peças de interface compartilhadas (as mesmas do Editor de Estádios):
// avisos (toasts), modais, menus flutuantes, barra de menus, campos numéricos arrastáveis, interruptores.
import { icone } from './icones.js';

export const $ = (sel, raiz = document) => raiz.querySelector(sel);
export const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

export function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false || f === '') continue;
    if (typeof f === 'string' && f.startsWith('<svg')) { e.insertAdjacentHTML('beforeend', f); continue; }
    e.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return e;
}

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function fmtNum(v, casas = 3) {
  if (!Number.isFinite(v)) return '—';
  const s = v.toFixed(casas);
  return s.replace(/\.?0+$/, '') .replace(/^-0$/, '0') || '0';
}

export function fmtInt(n) {
  return Number(n || 0).toLocaleString('pt-BR');
}

// ---------------------------------------------------------------- toasts
export function aviso(msg, { tipo = 'info', detalhe = '', acao = null, tempo = 4200 } = {}) {
  const ic = { sucesso: 'check', erro: 'aviso', aviso: 'aviso', info: 'info' }[tipo] || 'info';
  const t = el('div', { class: `toast ${tipo}`, role: tipo === 'erro' ? 'alert' : 'status' });
  t.innerHTML = icone(ic, 16);
  const m = el('div', { class: 'msg' }, msg);
  if (detalhe) m.append(el('small', {}, detalhe));
  t.append(m);
  if (acao) {
    const b = el('button', { class: 'acao' }, acao.rotulo);
    b.onclick = () => { acao.fn(); fechar(); };
    t.append(b);
  }
  const x = el('button', { class: 'btn-icone peq', title: 'Fechar', html: icone('x', 14) });
  x.onclick = () => fechar();
  t.append(x);
  $('#toasts').append(t);
  let timer = setTimeout(fechar, tipo === 'erro' ? Math.max(tempo, 8000) : tempo);
  t.onmouseenter = () => clearTimeout(timer);
  t.onmouseleave = () => { timer = setTimeout(fechar, 2000); };
  function fechar() { t.remove(); }
  return fechar;
}

// ---------------------------------------------------------------- modais
let pilhaModais = [];

export function modal({ titulo, texto = '', corpo = null, botoes = [], largo = false, aoFechar = null, rodapeEsq = '' }) {
  const camada = $('#camada-modal');
  const caixa = el('div', { class: `modal ${largo ? 'largo' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': titulo });
  const cab = el('div', { class: 'modal-cab' });
  const tit = el('div', {}, el('h2', {}, titulo));
  if (texto) tit.append(el('p', { html: texto }));
  cab.append(tit);
  const x = el('button', { class: 'btn-icone', title: 'Fechar (Esc)', html: icone('x', 16) });
  cab.append(x);
  caixa.append(cab);
  const c = el('div', { class: 'modal-corpo' });
  if (corpo) c.append(corpo);
  caixa.append(c);
  let resolver;
  const promessa = new Promise((r) => { resolver = r; });
  const fechar = (valor) => {
    caixa.remove();
    pilhaModais = pilhaModais.filter((m) => m !== reg);
    if (!camada.children.length) camada.innerHTML = '';
    document.removeEventListener('keydown', tecla, true);
    if (aoFechar) aoFechar(valor);
    resolver(valor);
  };
  x.onclick = () => fechar(null);
  if (botoes.length || rodapeEsq) {
    const rod = el('div', { class: 'modal-rodape' });
    if (rodapeEsq) rod.append(el('span', { class: 'esq', html: rodapeEsq }));
    for (const b of botoes) {
      const bt = el('button', { class: b.classe || 'btn' }, b.rotulo);
      if (b.desabilitado) bt.disabled = true;
      bt.onclick = async () => {
        if (b.fn) {
          const r = await b.fn(bt);
          if (r === false) return;
          fechar(r === undefined ? b.valor : r);
        } else fechar(b.valor);
      };
      b.el = bt;
      rod.append(bt);
    }
    caixa.append(rod);
  }
  const tecla = (e) => {
    if (pilhaModais[pilhaModais.length - 1] !== reg) return;
    if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); fechar(null); }
    if (e.key === 'Enter' && !e.shiftKey && e.target.tagName !== 'TEXTAREA') {
      const prim = botoes.find((b) => b.padrao);
      if (prim && !prim.el.disabled) { e.preventDefault(); e.stopPropagation(); prim.el.click(); }
    }
  };
  document.addEventListener('keydown', tecla, true);
  camada.append(caixa);
  const reg = { caixa, fechar };
  pilhaModais.push(reg);
  camada.onmousedown = (e) => { if (e.target === camada) fechar(null); };
  setTimeout(() => (caixa.querySelector('[autofocus]') || caixa.querySelector('.btn-primario') || x).focus(), 30);
  return { promessa, fechar, caixa, corpo: c };
}

export function confirmar(titulo, texto, { rotulo = 'Confirmar', perigo = false, cancelar = 'Cancelar' } = {}) {
  return modal({
    titulo, texto,
    botoes: [
      { rotulo: cancelar, classe: 'btn', valor: false },
      { rotulo, classe: perigo ? 'btn-perigo' : 'btn-primario', valor: true, padrao: true },
    ],
  }).promessa.then((v) => v === true);
}

export const modalAberto = () => pilhaModais.length > 0;

// ---------------------------------------------------------------- menus flutuantes
let menuAtual = null;

export function abrirMenu(itens, x, y, { origem = null, aoFechar = null } = {}) {
  fecharMenu();
  const m = $('#menu-contexto');
  m.innerHTML = '';
  const botoes = [];
  for (const it of itens) {
    if (!it) continue;
    if (it === '-') { m.append(el('div', { class: 'sep' })); continue; }
    if (it.cabecalho) { m.append(el('div', { class: 'cab' }, it.cabecalho)); continue; }
    const b = el('button', { class: 'item', role: 'menuitem' });
    b.innerHTML = `<span class="ic-esp">${it.marcado ? icone('check', 14) : it.icone ? icone(it.icone, 15) : ''}</span>`;
    b.append(el('span', { class: 'rot' }, it.rotulo));
    if (it.atalho) b.append(el('span', { class: 'atalho' }, it.atalho));
    if (it.desabilitado) b.disabled = true;
    b.onclick = (e) => { e.stopPropagation(); fecharMenu(); it.fn && it.fn(); };
    botoes.push(b);
    m.append(b);
  }
  m.hidden = false;
  const r = m.getBoundingClientRect();
  const W = window.innerWidth, H = window.innerHeight;
  m.style.left = Math.max(4, Math.min(x, W - r.width - 4)) + 'px';
  m.style.top = Math.max(4, (y + r.height > H - 4 ? Math.max(4, y - r.height) : y)) + 'px';
  let foco = -1;
  const tecla = (e) => {
    const ativos = botoes.filter((b) => !b.disabled);
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); fecharMenu(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); e.stopPropagation();
      foco = (foco + (e.key === 'ArrowDown' ? 1 : -1) + ativos.length) % ativos.length;
      ativos.forEach((b, i) => b.classList.toggle('foco', i === foco));
    }
    if (e.key === 'Enter' && foco >= 0) { e.preventDefault(); e.stopPropagation(); ativos[foco].click(); }
  };
  const fora = (e) => { if (!m.contains(e.target) && (!origem || !origem.contains(e.target))) fecharMenu(); };
  setTimeout(() => document.addEventListener('mousedown', fora, true), 0);
  document.addEventListener('keydown', tecla, true);
  menuAtual = { fechar: () => { document.removeEventListener('mousedown', fora, true); document.removeEventListener('keydown', tecla, true); m.hidden = true; aoFechar && aoFechar(); } };
}

export function fecharMenu() {
  if (menuAtual) { const f = menuAtual; menuAtual = null; f.fechar(); }
}

export const menuAberto = () => !!menuAtual;

// ---------------------------------------------------------------- campo numérico arrastável
// Arrastar na horizontal muda o valor (Shift = fino, Ctrl = passos de 'passoCtrl'); clique para digitar.
export function campoNumero({ valor, eixo = '', passo = 0.05, casas = 3, aoMudar, aoConfirmar, titulo = '', min = -Infinity, max = Infinity, passoCtrl = 1 }) {
  const caixa = el('div', { class: 'num', title: titulo });
  if (eixo) caixa.append(el('span', { class: `eixo ${eixo}` }, eixo.toUpperCase()));
  const inp = el('input', { type: 'text', inputmode: 'decimal', spellcheck: 'false' });
  caixa.append(inp);
  let atual = valor;
  const mostrar = () => { inp.value = fmtNum(atual, casas); };
  mostrar();
  let arrastando = false, x0 = 0, v0 = 0, moveu = false, inicioValor = 0;
  caixa.addEventListener('pointerdown', (e) => {
    if (document.activeElement === inp) return;
    e.preventDefault();
    arrastando = true; moveu = false; x0 = e.clientX; v0 = atual; inicioValor = atual;
    caixa.setPointerCapture(e.pointerId);
  });
  caixa.addEventListener('pointermove', (e) => {
    if (!arrastando) return;
    const dx = e.clientX - x0;
    if (!moveu && Math.abs(dx) < 3) return;
    moveu = true;
    let v = v0 + dx * passo * (e.shiftKey ? 0.1 : 1);
    if (e.ctrlKey) v = Math.round(v / passoCtrl) * passoCtrl;
    v = Math.min(max, Math.max(min, v));
    atual = v; mostrar();
    aoMudar && aoMudar(v, false);
  });
  caixa.addEventListener('pointerup', (e) => {
    if (!arrastando) return;
    arrastando = false;
    caixa.releasePointerCapture(e.pointerId);
    if (!moveu) { inp.focus(); inp.select(); return; }
    aoConfirmar && aoConfirmar(atual, inicioValor);
  });
  const confirmarTexto = () => {
    const txt = inp.value.trim().replace(',', '.');
    let v;
    try {
      // aceita expressões simples: 10+2.5, 90/2
      if (!/^[-+*/().\d\se]+$/i.test(txt)) throw new Error();
      v = Function(`"use strict";return (${txt})`)();
    } catch { v = NaN; }
    if (!Number.isFinite(v)) { mostrar(); return; }
    v = Math.min(max, Math.max(min, v));
    const antes = atual;
    atual = v; mostrar();
    if (v !== antes) { aoMudar && aoMudar(v, true); aoConfirmar && aoConfirmar(v, antes); }
  };
  inp.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') { inp.blur(); }
    if (e.key === 'Escape') { mostrar(); inp.blur(); }
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const antes = atual;
      atual = Math.min(max, Math.max(min, atual + (e.key === 'ArrowUp' ? 1 : -1) * (e.shiftKey ? passoCtrl * 10 : passoCtrl)));
      mostrar(); aoMudar && aoMudar(atual, true); aoConfirmar && aoConfirmar(atual, antes);
    }
  });
  inp.addEventListener('blur', confirmarTexto);
  return {
    el: caixa,
    definir(v) { atual = v; if (document.activeElement !== inp) mostrar(); },
    marcar(alterado) { caixa.classList.toggle('alterado', !!alterado); },
  };
}

// ---------------------------------------------------------------- painel flutuante sobre a vista 3D
// Não bloqueia a vista: serve para ferramentas com prévia ao vivo (remapear luzes, gerar assentos...).
let painelAtual = null;

export function painelFlutuante({ titulo, icone: ic = null, corpo, botoes = [], aoFechar = null, largura = 340 }) {
  fecharPainel();
  const vp = document.getElementById('viewport') || document.body;
  const p = el('div', { class: 'painel-flutuante', role: 'dialog', 'aria-label': titulo, style: { width: largura + 'px' } });
  const cab = el('div', { class: 'pf-cab', html: (ic ? icone(ic, 16) : '') + `<b>${esc(titulo)}</b>` });
  const x = el('button', { class: 'btn-icone peq', title: 'Fechar', html: icone('x', 14) });
  cab.append(x);
  const c = el('div', { class: 'pf-corpo' });
  if (corpo) c.append(...[].concat(corpo).filter(Boolean));
  p.append(cab, c);
  const rod = el('div', { class: 'pf-rodape' });
  const refs = {};
  for (const b of botoes) {
    const bt = el('button', { class: b.classe || 'btn peq' }, ...(b.icone ? [icone(b.icone, 13)] : []), b.rotulo);
    if (b.desabilitado) bt.disabled = true;
    bt.onclick = () => b.fn(bt);
    refs[b.id || b.rotulo] = bt;
    rod.append(bt);
  }
  if (botoes.length) p.append(rod);
  vp.append(p);
  // arrastar pelo cabeçalho
  cab.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;
    const r = p.getBoundingClientRect(), rv = vp.getBoundingClientRect();
    const ox = e.clientX - r.left, oy = e.clientY - r.top;
    cab.setPointerCapture(e.pointerId);
    const mover = (ev) => {
      p.style.left = Math.max(0, Math.min(rv.width - 60, ev.clientX - rv.left - ox)) + 'px';
      p.style.top = Math.max(0, Math.min(rv.height - 40, ev.clientY - rv.top - oy)) + 'px';
    };
    const soltar = () => { cab.removeEventListener('pointermove', mover); cab.removeEventListener('pointerup', soltar); };
    cab.addEventListener('pointermove', mover);
    cab.addEventListener('pointerup', soltar);
  });
  const reg = {
    el: p, corpo: c, botoes: refs,
    fechar: (motivo = 'fechar') => {
      if (painelAtual !== reg) return;
      painelAtual = null;
      p.remove();
      aoFechar && aoFechar(motivo);
    },
  };
  x.onclick = () => reg.fechar('cancelar');
  painelAtual = reg;
  return reg;
}

export function fecharPainel(motivo = 'cancelar') { if (painelAtual) painelAtual.fechar(motivo); }
export const painelAberto = () => painelAtual;

export function campoRotulado(rotulo, controle, dica = '') {
  return el('div', { class: 'linha-prop', title: dica }, el('label', {}, rotulo), controle);
}

export function interruptor({ titulo, descricao = '', marcado, aoMudar, desabilitado = false, icone: ic = null }) {
  const lin = el('label', { class: 'interruptor' });
  const txt = el('span', { class: 'txt' });
  const b = el('b', { html: (ic ? icone(ic, 14) : '') + esc(titulo) });
  txt.append(b);
  const small = el('small', { html: descricao });
  if (descricao) txt.append(small);
  const ch = el('span', { class: 'chave' });
  const inp = el('input', { type: 'checkbox', role: 'switch' });
  inp.checked = !!marcado;
  inp.disabled = desabilitado;
  inp.onchange = () => aoMudar(inp.checked);
  ch.append(inp, el('span'));
  lin.append(txt, ch);
  return { el: lin, inp, descricao: small };
}

export function nota(html, tipo = '') {
  const ic = tipo === 'alerta' || tipo === 'erro' ? 'aviso' : 'info';
  return el('div', { class: `nota ${tipo}`, html: icone(ic, 15) + `<div>${html}</div>` });
}

export async function copiarTexto(t) {
  try { await navigator.clipboard.writeText(t); aviso('Copiado para a área de transferência', { tipo: 'sucesso', tempo: 1800 }); }
  catch { aviso('Não foi possível copiar', { tipo: 'erro' }); }
}

export function arquivoLocal(aceita) {
  return new Promise((res) => {
    const inp = el('input', { type: 'file', accept: aceita });
    inp.onchange = () => res(inp.files[0] || null);
    inp.click();
  });
}

export function lerArquivoBase64(arquivo) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(',')[1]);
    r.onerror = rej;
    r.readAsDataURL(arquivo);
  });
}

export function blobParaBase64(blob) { return lerArquivoBase64(blob); }

// ---------------------------------------------------------------- barra de menus do topo
// defs: [['Arquivo', () => [itens…]], …] — os itens são montados na hora (refletem o estado atual).
export function barraMenus(nav, defs) {
  nav.innerHTML = '';
  for (const [rot, fn] of defs) {
    const b = el('button', { class: 'menu-botao', 'aria-haspopup': 'menu' }, rot);
    const abrir = () => {
      const r = b.getBoundingClientRect();
      b.classList.add('aberto');
      abrirMenu(fn(), r.left, r.bottom + 4, { origem: b, aoFechar: () => b.classList.remove('aberto') });
    };
    b.onclick = () => (b.classList.contains('aberto') ? fecharMenu() : abrir());
    b.onmouseenter = () => { if (menuAberto() && !b.classList.contains('aberto') && document.querySelector('.menu-botao.aberto')) abrir(); };
    nav.append(b);
  }
}

// ---------------------------------------------------------------- campo de formulário (rótulo + controle + ajuda)
export function campo(rotulo, controle, ajuda = '') {
  return el('div', { class: 'campo' }, rotulo ? el('label', {}, rotulo) : null, controle, ajuda ? el('div', { class: 'ajuda', html: ajuda }) : null);
}

export function entrada(attrs = {}) {
  return el('input', { type: 'text', class: 'entrada', spellcheck: 'false', autocomplete: 'off', ...attrs });
}

// ---------------------------------------------------------------- "Sobre" padrão das ferramentas
export function dialogoSobre({ nome, versao, html = '', icone: ic = 'info' }) {
  const corpo = el('div', { style: { color: 'var(--texto-2)', lineHeight: '1.6' }, html });
  return modal({ titulo: nome, texto: `Versão ${esc(versao)} · parte do <b>BRFP Super Tool</b>`, corpo,
    botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

// ---------------------------------------------------------------- divisor arrastável entre painéis (muda uma variável CSS)
export function divisorArrastavel(div, variavel, { min = 200, max = 640, lado = 'esq' } = {}) {
  div.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    div.setPointerCapture(e.pointerId);
    div.classList.add('arrastando');
    const x0 = e.clientX;
    const v0 = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(variavel)) || 300;
    const mover = (ev) => {
      const dx = ev.clientX - x0;
      const v = Math.max(min, Math.min(max, v0 + (lado === 'esq' ? dx : -dx)));
      document.documentElement.style.setProperty(variavel, v + 'px');
    };
    const soltar = () => { div.classList.remove('arrastando'); div.removeEventListener('pointermove', mover); div.removeEventListener('pointerup', soltar); };
    div.addEventListener('pointermove', mover);
    div.addEventListener('pointerup', soltar);
  });
}
