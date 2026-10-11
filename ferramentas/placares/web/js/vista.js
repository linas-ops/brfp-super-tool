// A vista central: zoom e arrasto da câmera, clique para selecionar, arrastar para mover o elemento, desenho da
// moldura de seleção e a barra de exibição (fundo, textos de exemplo, enquadrar).
import { M, caminhoNomes } from './cena.js';
import { S, definirOp, opPlace, emitir } from './estado.js';
import { icone } from './icones.js';
import { $, el, abrirMenu, arquivoLocal } from './ui.js';

let tela, sobre, ctx2;
let hover = null;
let quadroPedido = false;

export function iniciarVista(render) {
  tela = $('#tela');
  sobre = $('#sobre');
  ctx2 = sobre.getContext('2d');
  render.aoPrecisarDesenhar = pedirDesenho;
  try {
    const p = JSON.parse(localStorage.getItem('placares.vista') || '{}');
    if (p.fundo) render.fundo = p.fundo;
    if (p.textos === false) render.mostrarTextos = false;
    if (p.mascaras === true) render.usarMascaras = true;
  } catch { /* sem preferências */ }
  new ResizeObserver(() => pedirDesenho()).observe($('#viewport'));
  ligarEventos(render);
  montarBarra(render);
  dica();
}

export function pedirDesenho() {
  if (quadroPedido) return;
  quadroPedido = true;
  requestAnimationFrame(() => {
    quadroPedido = false;
    desenharTudo();
  });
}

function desenharTudo() {
  const r = S.render;
  if (!r) return;
  r.desenhar();
  desenharSobre();
  const z = $('#status-zoom');
  if (z) z.textContent = `Zoom ${Math.round(r.vista.s * 100)}%`;
  const zt = $('#zoom-txt');
  if (zt) zt.textContent = `${Math.round(r.vista.s * 100)}%`;
}

function desenharSobre() {
  const r = S.render;
  const dpr = window.devicePixelRatio || 1;
  const rr = sobre.getBoundingClientRect();
  if (sobre.width !== Math.round(rr.width * dpr) || sobre.height !== Math.round(rr.height * dpr)) {
    sobre.width = Math.round(rr.width * dpr); sobre.height = Math.round(rr.height * dpr);
  }
  ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx2.clearRect(0, 0, rr.width, rr.height);
  // borda da tela do jogo (1920×1080)
  const [x0, y0] = r.palcoParaTela(0, 0), [x1, y1] = r.palcoParaTela(r.palco.w, r.palco.h);
  ctx2.strokeStyle = 'rgba(255,255,255,.18)';
  ctx2.lineWidth = 1;
  ctx2.strokeRect(Math.round(x0) + .5, Math.round(y0) + .5, Math.round(x1 - x0), Math.round(y1 - y0));
  if (!S.raiz) return;
  if (hover && hover.id !== S.sel) caixa(r.limites(hover), 'rgba(76,141,255,.9)', [4, 3]);
  const sel = selecionado();
  if (sel) {
    const b = r.limites(sel);
    caixa(b, '#ff9233', []);
    if (b) {
      const [ax, ay] = r.palcoParaTela(b[0], b[1]);
      const rot = sel.nome || `#${sel.char}`;
      ctx2.font = '600 11px "Segoe UI", system-ui, sans-serif';
      const w = ctx2.measureText(rot).width + 10;
      ctx2.fillStyle = '#ff9233';
      ctx2.fillRect(ax, ay - 18, w, 17);
      ctx2.fillStyle = '#1a1206';
      ctx2.fillText(rot, ax + 5, ay - 5.5);
      // ponto de origem do elemento (onde fica o x/y)
      const [ox, oy] = r.palcoParaTela(sel.mundo[4], sel.mundo[5]);
      ctx2.strokeStyle = '#ff9233';
      ctx2.beginPath(); ctx2.moveTo(ox - 6, oy); ctx2.lineTo(ox + 6, oy); ctx2.moveTo(ox, oy - 6); ctx2.lineTo(ox, oy + 6); ctx2.stroke();
    }
  }
}

function caixa(b, cor, tracejado) {
  if (!b) return;
  const r = S.render;
  const [x0, y0] = r.palcoParaTela(b[0], b[1]), [x1, y1] = r.palcoParaTela(b[2], b[3]);
  ctx2.setLineDash(tracejado);
  ctx2.strokeStyle = cor;
  ctx2.lineWidth = 1.5;
  ctx2.strokeRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
  ctx2.setLineDash([]);
}

export function selecionado() {
  if (!S.sel || !S.raiz) return null;
  let achado = null;
  const busca = (n) => { if (achado) return; if (n.id === S.sel) { achado = n; return; } n.filhos.forEach(busca); };
  busca(S.raiz);
  return achado;
}

// nó editável mais próximo, de preferência com nome (o que o usuário quer mexer)
function alvoDoClique(no, profundo) {
  if (!no) return null;
  let n = no;
  while (n && (n.importado || !n.place)) n = n.pai;        // conteúdo importado: sobe até o componente
  if (!n) return null;
  if (profundo) return n;
  let m = n;
  while (m && m.place && !m.nome) m = m.pai;
  return (m && m.place) ? m : n;
}

function ligarEventos(render) {
  let arrasto = null;
  tela.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = tela.getBoundingClientRect();
    render.zoom(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    pedirDesenho();
  }, { passive: false });
  tela.addEventListener('contextmenu', (e) => e.preventDefault());
  tela.addEventListener('pointerdown', (e) => {
    tela.focus();
    const r = tela.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    if (e.button === 1 || e.button === 2 || (e.button === 0 && espaco)) {
      arrasto = { tipo: 'pan', x, y, ox: render.vista.ox, oy: render.vista.oy, moveu: false, botao: e.button };
      tela.setPointerCapture(e.pointerId);
      return;
    }
    if (e.button !== 0 || !S.raiz) return;
    const acerto = render.acertar(x, y);
    const atual = selecionado();
    // arrastar o selecionado (ou algo dentro dele) move o selecionado
    let dentro = false;
    for (let n = acerto; n; n = n.pai) if (atual && n === atual) { dentro = true; break; }
    if (atual && dentro && atual.editavel && !e.altKey && !S.animando) {
      iniciarMover(atual, x, y, e);
      return;
    }
    const alvo = alvoDoClique(acerto, e.altKey || e.detail >= 2);
    S.sel = alvo ? alvo.id : null;
    emitir('selecao', 'vista');
    pedirDesenho();
    if (alvo && alvo.editavel && !S.animando) iniciarMover(alvo, x, y, e);
  });
  function iniciarMover(no, x, y, e) {
    const pai = no.pai;
    const inv = M.inv(pai.mundo);
    if (!inv) return;
    const chave = 'place:' + no.place.off;
    arrasto = { tipo: 'mover', no, x, y, tx0: no.place.tx.slice(), inv, chave,
      antes: S.doc.ops[chave] ? JSON.parse(JSON.stringify(S.doc.ops[chave])) : null, moveu: false,
      base: acharBase(no.place.off) };
    tela.setPointerCapture(e.pointerId);
  }
  tela.addEventListener('pointermove', (e) => {
    const r = tela.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const [px, py] = render.telaParaPalco(x, y);
    $('#status-cursor').textContent = `x ${Math.round(px)}  y ${Math.round(py)}`;
    if (arrasto && arrasto.tipo === 'pan') {
      if (Math.abs(x - arrasto.x) + Math.abs(y - arrasto.y) > 2) arrasto.moveu = true;
      render.vista.ox = arrasto.ox + (x - arrasto.x);
      render.vista.oy = arrasto.oy + (y - arrasto.y);
      pedirDesenho();
      return;
    }
    if (arrasto && arrasto.tipo === 'mover') {
      const dxs = (x - arrasto.x) / render.vista.s, dys = (y - arrasto.y) / render.vista.s;
      if (!arrasto.moveu && Math.hypot(x - arrasto.x, y - arrasto.y) < 3) return;
      arrasto.moveu = true;
      let [dx, dy] = M.vetor(arrasto.inv, dxs, dys);
      if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
      let nx = arrasto.tx0[0] + dx, ny = arrasto.tx0[1] + dy;
      if (!e.ctrlKey) { nx = Math.round(nx); ny = Math.round(ny); }
      const { chave, op } = opPlace(arrasto.no.place, arrasto.base || {}, { tx: [nx, ny] });
      definirOp('Mover', chave, op, { semHistorico: true });
      return;
    }
    // passar o mouse: realça o que seria selecionado
    const ac = S.raiz ? alvoDoClique(render.acertar(x, y), e.altKey) : null;
    if (ac !== hover && (ac?.id !== hover?.id)) {
      hover = ac;
      const rot = $('#rotulo-hover');
      if (hover) {
        rot.hidden = false;
        rot.innerHTML = '';
        rot.append(hover.nome || `(sem nome) #${hover.char}`, el('small', {}, caminhoNomes(hover).slice(0, -1).slice(-3).join(' › ')));
      } else rot.hidden = true;
      pedirDesenho();
    }
    const rot = $('#rotulo-hover');
    if (!rot.hidden) { rot.style.left = x + 'px'; rot.style.top = y + 'px'; }
  });
  const soltar = (e) => {
    if (!arrasto) return;
    try { tela.releasePointerCapture(e.pointerId); } catch { /* já solto */ }
    if (arrasto.tipo === 'mover' && arrasto.moveu) {
      const atual = S.doc.ops[arrasto.chave] || null;
      definirOp('Mover', arrasto.chave, atual, { antes: arrasto.antes, fundir: false });
    }
    if (arrasto.tipo === 'pan' && !arrasto.moveu && arrasto.botao === 2) emitir('menu-vista', e);
    arrasto = null;
  };
  tela.addEventListener('pointerup', soltar);
  tela.addEventListener('pointercancel', soltar);
  tela.addEventListener('pointerleave', () => { if (!arrasto) { hover = null; $('#rotulo-hover').hidden = true; pedirDesenho(); } });
  let espaco = false;
  window.addEventListener('keydown', (e) => { if (e.code === 'Space' && document.activeElement === tela && !S.animando) { espaco = true; e.preventDefault(); } });
  window.addEventListener('keyup', (e) => { if (e.code === 'Space') espaco = false; });
}

// valores originais de um PlaceObject (para saber o que mudou)
export function acharBase(off) {
  for (const c of S.doc.filme.base.chars) {
    if (!c || !c.quadros) continue;
    for (const q of c.quadros) for (const it of q) if (it.t === 'place' && it.off === off) return it;
  }
  return null;
}

export function enquadrarSelecao() {
  const r = S.render;
  const sel = selecionado();
  const b = sel ? r.limites(sel) : r.limitesConteudo();
  if (b) {
    const pad = Math.max(20, (b[2] - b[0]) * 0.15);
    r.enquadrar([b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad]);
  } else r.enquadrar();
  pedirDesenho();
}

export function enquadrarConteudo() {
  const r = S.render;
  const b = r.limitesConteudo();
  if (b) {
    const pad = 30;
    r.enquadrar([Math.max(-200, b[0] - pad), Math.max(-200, b[1] - pad), Math.min(r.palco.w + 200, b[2] + pad), Math.min(r.palco.h + 200, b[3] + pad)]);
  } else r.enquadrar();
  pedirDesenho();
}

// a prévia da animação liga as máscaras: a barra precisa refletir isso
export function remontarBarra() { if (S.render) montarBarra(S.render); }

function salvarPrefsVista() {
  try { localStorage.setItem('placares.vista', JSON.stringify({ fundo: S.render.fundo, textos: S.render.mostrarTextos, mascaras: S.render.usarMascaras })); } catch { /* sem armazenamento */ }
}

function montarBarra(render) {
  const b = $('#barra-vista');
  b.innerHTML = '';
  const fundos = [['campo', 'Campo'], ['xadrez', 'Xadrez'], ['escuro', 'Escuro'], ['imagem', 'Captura do jogo…']];
  const sel = el('select', { class: 'seletor', title: 'Fundo atrás do placar' });
  for (const [v, t] of fundos) sel.append(el('option', { value: v }, t));
  sel.value = render.fundo === 'imagem' && !render.imagemFundo ? 'campo' : render.fundo;
  sel.onchange = async () => {
    if (sel.value === 'imagem') {
      const arq = await arquivoLocal('image/*');
      if (!arq) { sel.value = render.fundo; return; }
      const bmp = await createImageBitmap(arq);
      const cv = document.createElement('canvas');
      cv.width = bmp.width; cv.height = bmp.height;
      cv.getContext('2d').drawImage(bmp, 0, 0);
      render.imagemFundo = cv;
    }
    render.fundo = sel.value;
    salvarPrefsVista();
    pedirDesenho();
  };
  const btTextos = el('button', { class: 'btn-icone' + (render.mostrarTextos ? ' ativo' : ''), title: 'Textos de exemplo (o jogo preenche os textos durante a partida)', html: icone('texto', 16) });
  btTextos.onclick = () => {
    render.mostrarTextos = !render.mostrarTextos;
    btTextos.classList.toggle('ativo', render.mostrarTextos);
    salvarPrefsVista();
    pedirDesenho();
  };
  const btMasc = el('button', { class: 'btn-icone' + (render.usarMascaras ? ' ativo' : ''), title: 'Máscaras (recortes). O jogo anima as máscaras durante a partida; desligadas, aparece tudo o que existe no placar.', html: icone('alvo', 16) });
  btMasc.onclick = () => {
    render.usarMascaras = !render.usarMascaras;
    btMasc.classList.toggle('ativo', render.usarMascaras);
    salvarPrefsVista();
    pedirDesenho();
  };
  const btMenos = el('button', { class: 'btn-icone', title: 'Diminuir zoom', html: icone('zoomMenos', 16) });
  const btMais = el('button', { class: 'btn-icone', title: 'Aumentar zoom', html: icone('zoomMais', 16) });
  const centro = () => { const r = tela.getBoundingClientRect(); return [r.width / 2, r.height / 2]; };
  btMenos.onclick = () => { render.zoom(1 / 1.25, ...centro()); pedirDesenho(); };
  btMais.onclick = () => { render.zoom(1.25, ...centro()); pedirDesenho(); };
  const zt = el('span', { class: 'zoom-txt', id: 'zoom-txt', title: 'Clique: 100%' });
  zt.onclick = () => { const [cx, cy] = centro(); render.zoom(1 / render.vista.s, cx, cy); pedirDesenho(); };
  const btEnq = el('button', { class: 'btn-icone', title: 'Enquadrar (F = seleção, Home = placar inteiro)', html: icone('enquadrar', 16) });
  btEnq.onclick = (e) => abrirMenu([
    { rotulo: 'Enquadrar a seleção', atalho: 'F', fn: enquadrarSelecao },
    { rotulo: 'Enquadrar o placar inteiro', atalho: 'Home', fn: enquadrarConteudo },
    { rotulo: 'Tela inteira do jogo (1920×1080)', fn: () => { render.enquadrar(); pedirDesenho(); } },
  ], e.clientX - 200, e.clientY + 14);
  b.append(sel, el('span', { class: 'sep-v' }), btTextos, btMasc, el('span', { class: 'sep-v' }), btMenos, zt, btMais, btEnq);
}

function dica() {
  const d = $('#dica-navegacao');
  if (localStorage.getItem('placares.dica-ok')) { d.hidden = true; return; }
  d.innerHTML = '';
  d.append(
    el('span', {}, el('kbd', {}, 'Clique'), 'seleciona'),
    el('span', {}, el('kbd', {}, 'Arrastar'), 'move'),
    el('span', {}, el('kbd', {}, 'Alt'), '+clique: peça interna'),
    el('span', {}, el('kbd', {}, 'Roda'), 'zoom'),
    el('span', {}, el('kbd', {}, 'Botão direito'), 'arrasta a vista'),
    el('span', {}, el('kbd', {}, '← → ↑ ↓'), '1 px (Shift: 10)'),
  );
  const x = el('button', { class: 'fechar', title: 'Esconder dica', html: icone('x', 13) });
  x.onclick = () => { d.hidden = true; try { localStorage.setItem('placares.dica-ok', '1'); } catch { /* ok */ } };
  d.append(x);
}
