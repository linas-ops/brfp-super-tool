// Prévia das animações. Os placares do FC não têm animação desenhada em quadros: a classe do placar chama
// AnimationManager.Animate(clipe, propriedade, destino, duração, curva, callback, atraso) — em quadros. O servidor
// roda esse código num simulador e devolve a linha do tempo (interpolações e mudanças de propriedades); aqui ela é
// tocada sobre a árvore de exibição, recalculando as matrizes e cores de cada nó a cada quadro.
import { api } from './api.js';
import { M, percorrer } from './cena.js';
import { S, emitir } from './estado.js';
import { icone } from './icones.js';
import { $, el, esc } from './ui.js';
import { pedirDesenho, remontarBarra } from './vista.js';

export const A = {
  dados: null,          // resposta de /api/animacao
  erro: null,
  carregando: false,
  t: 0,                 // quadro atual
  tocando: false,
  vel: 1,
  fps: null,            // null = o do arquivo (60 ou 30)
  repetir: true,
  metodos: ['AnimateIn'],
  linha: [],            // eventos e interpolações em ordem de início
  mapa: new Map(),      // caminho do clipe -> [nós]
  mascarasAntes: null,
};

// ---------------------------------------------------------------- curvas
// As curvas vêm do AnimationManager do próprio jogo (o servidor roda EaseOutCubic, EaseBounce... e amostra);
// estas fórmulas só valem se o arquivo dele não foi encontrado.
const P = {
  Linear: (p) => p,
  In: (p) => p * p,
  Out: (p) => 1 - (1 - p) * (1 - p),
  InOut: (p) => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2),
  InCubic: (p) => p ** 3,
  OutCubic: (p) => 1 - (1 - p) ** 3,
  InOutCubic: (p) => (p < 0.5 ? 4 * p ** 3 : 1 - (-2 * p + 2) ** 3 / 2),
  InQuartic: (p) => p ** 4,
  OutQuartic: (p) => 1 - (1 - p) ** 4,
  InOutQuartic: (p) => (p < 0.5 ? 8 * p ** 4 : 1 - (-2 * p + 2) ** 4 / 2),
  InQuintic: (p) => p ** 5,
  OutQuintic: (p) => 1 - (1 - p) ** 5,
  InOutQuintic: (p) => (p < 0.5 ? 16 * p ** 5 : 1 - (-2 * p + 2) ** 5 / 2),
  InCircle: (p) => 1 - Math.sqrt(1 - p * p),
  OutCircle: (p) => Math.sqrt(1 - (p - 1) ** 2),
  InOutCircle: (p) => (p < 0.5 ? (1 - Math.sqrt(1 - (2 * p) ** 2)) / 2 : (Math.sqrt(1 - (-2 * p + 2) ** 2) + 1) / 2),
  OverShoot: (p) => { const c = 1.70158; return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2; },
  Elastic: (p) => (p === 0 || p === 1 ? p : 2 ** (-10 * p) * Math.sin((p * 10 - 0.75) * (2 * Math.PI) / 3) + 1),
  Bounce: (p) => {
    const n = 7.5625, d = 2.75;
    if (p < 1 / d) return n * p * p;
    if (p < 2 / d) return n * (p -= 1.5 / d) * p + 0.75;
    if (p < 2.5 / d) return n * (p -= 2.25 / d) * p + 0.9375;
    return n * (p -= 2.625 / d) * p + 0.984375;
  },
};

export const CURVAS_ROTULO = {
  Linear: 'constante', LinearRound: 'constante (px inteiros)', In: 'acelera (suave)', Out: 'desacelera (suave)',
  InOut: 'acelera e desacelera', InRound: 'acelera (px inteiros)', OutRound: 'desacelera (px inteiros)', InOutRound: 'acelera e desacelera (px inteiros)',
  InCubic: 'acelera', OutCubic: 'desacelera', InOutCubic: 'acelera e desacelera', InQuartic: 'acelera forte',
  OutQuartic: 'desacelera forte', InOutQuartic: 'acelera e desacelera forte', InQuintic: 'acelera muito',
  OutQuintic: 'desacelera muito', InOutQuintic: 'acelera e desacelera muito', InCircle: 'acelera (circular)',
  OutCircle: 'desacelera (circular)', InOutCircle: 'circular', OverShoot: 'passa do ponto e volta', Elastic: 'elástica',
  Bounce: 'quica', custom: 'personalizada',
};

export function curva(nome, p) {
  if (p <= 0) return 0;
  if (p >= 1) return 1;
  const am = A.dados && A.dados.curvas && A.dados.curvas[nome];
  if (am && am.length > 1) {
    const x = p * (am.length - 1), i = Math.floor(x), f = x - i;
    return am[i] + (am[Math.min(i + 1, am.length - 1)] - am[i]) * f;
  }
  const base = String(nome || 'Linear').replace(/Round$/, '');
  return (P[base] || P.Linear)(p);
}

// ---------------------------------------------------------------- simulação (servidor)
let seq = 0;
let timer = 0;

export function simularDepois(atraso = 280) {
  clearTimeout(timer);
  timer = setTimeout(simular, atraso);
}

export async function simular() {
  clearTimeout(timer);
  if (!S.doc) return;
  const pedido = ++seq;
  A.carregando = true;
  emitir('animacao');
  try {
    const r = await api('animacao', { sessao: S.doc.filme.sessao, ops: S.doc.ops, metodos: A.metodos });
    if (pedido !== seq) return;
    A.dados = r;
    A.erro = null;
    prepararLinha();
    A.t = Math.min(A.t, duracao());
  } catch (ex) {
    if (pedido !== seq) return;
    A.erro = ex.message;
  } finally {
    if (pedido === seq) {
      A.carregando = false;
      aplicar();
      emitir('animacao');
    }
  }
}

export function limpar() {
  seq++;
  A.dados = null;
  A.erro = null;
  A.t = 0;
  A.linha = [];
  pausar();
}

function prepararLinha() {
  const d = A.dados;
  const itens = [];
  for (const e of d.eventos || []) if (!String(e.prop).startsWith('@')) itens.push({ t: e.t, ev: e });
  for (const tw of d.tweens || []) itens.push({ t: tw.t0, tw });
  itens.sort((a, b) => a.t - b.t || (a.ev ? 0 : 1) - (b.ev ? 0 : 1));
  A.linha = itens;
}

export function duracao() { return Math.max(1, (A.dados && A.dados.duracao) || 0); }
export function fps() { return A.fps || (A.dados && A.dados.fps) || 30; }

// ---------------------------------------------------------------- estado num instante
function estadoNoTempo(t) {
  const est = new Map();
  const pr = (alvo) => { let o = est.get(alvo); if (!o) est.set(alvo, o = {}); return o; };
  for (const i of A.dados.inicial || []) pr(i.alvo)[i.prop] = i.valor;
  for (const it of A.linha) {
    if (it.t > t) break;
    if (it.ev) { pr(it.ev.alvo)[it.ev.prop] = it.ev.valor; continue; }
    const tw = it.tw;
    const p = tw.dur > 0 ? Math.min(1, (t - tw.t0) / tw.dur) : 1;
    if (tw.prop === '_visible') pr(tw.alvo)._visible = p >= 1 ? tw.para : tw.de;
    else if (typeof tw.de === 'number' && typeof tw.para === 'number') pr(tw.alvo)[tw.prop] = tw.de + (tw.para - tw.de) * curva(tw.ease, p);
  }
  return est;
}

// ---------------------------------------------------------------- aplicar na árvore
export function mapear(raiz) {
  A.mapa = new Map();
  if (!raiz) return;
  percorrer(raiz, (n) => {
    if (!n.caminho) return;
    let l = A.mapa.get(n.caminho);
    if (!l) A.mapa.set(n.caminho, l = []);
    l.push(n);
  });
}

function localAnimado(no) {
  const a = no.anim;
  if (!a) return no.local;
  let [ma, mb, mc, md, tx, ty] = no.local;
  if ('_xscale' in a || '_yscale' in a || '_rotation' in a) {
    const d = M.decompor(no.local);
    [ma, mb, mc, md] = M.compor('_xscale' in a ? a._xscale / 100 : d.sx, '_yscale' in a ? a._yscale / 100 : d.sy,
      '_rotation' in a ? a._rotation : d.rot);
  }
  if ('_x' in a) tx = a._x;
  if ('_y' in a) ty = a._y;
  return [ma, mb, mc, md, tx, ty];
}

function recompor(no) {
  for (const f of no.filhos) {
    f.mundo = M.mul(no.mundo, localAnimado(f));
    const mp = f.multProprio || [1, 1, 1, 1], sp = f.somaProprio || [0, 0, 0, 0];
    const alfa = f.anim && '_alpha' in f.anim ? Math.max(0, Math.min(1, f.anim._alpha / 100)) : mp[3];
    f.mult = [no.mult[0] * mp[0], no.mult[1] * mp[1], no.mult[2] * mp[2], no.mult[3] * alfa];
    f.soma = sp.map((v, k) => v * no.mult[k] + no.soma[k]);
    f.animOculto = !!(f.anim && f.anim._visible === false);
    recompor(f);
  }
}

export function aplicar() {
  const raiz = S.raiz;
  if (!raiz) return;
  percorrer(raiz, (n) => { n.anim = null; });
  if (S.animando && A.dados && A.dados.tweens) {
    for (const [cam, props] of estadoNoTempo(A.t)) {
      for (const n of A.mapa.get(cam) || []) n.anim = props;
    }
  }
  recompor(raiz);
  pedirDesenho();
}

export function aoNovaArvore(raiz) {
  mapear(raiz);
  if (S.animando) aplicar();
}

// ---------------------------------------------------------------- tocar
let raf = 0;
let ultimo = 0;
let espera = 0;

export function tocar() {
  if (!A.dados) return;
  if (!S.animando) ativar(true);
  if (A.t >= duracao()) A.t = 0;
  A.tocando = true;
  ultimo = performance.now();
  espera = 0;
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(passo);
  atualizarBarra();
}

export function pausar() {
  A.tocando = false;
  cancelAnimationFrame(raf);
  atualizarBarra();
}

function passo(agora) {
  if (!A.tocando) return;
  const dt = Math.min(0.1, (agora - ultimo) / 1000);
  ultimo = agora;
  const dur = duracao();
  if (A.t >= dur) {
    if (!A.repetir) { A.tocando = false; atualizarBarra(); return; }
    espera += dt;
    if (espera > 0.9) { A.t = 0; espera = 0; }
  } else {
    A.t = Math.min(dur, A.t + dt * fps() * A.vel);
  }
  aplicar();
  atualizarBarra();
  raf = requestAnimationFrame(passo);
}

export function irPara(t, { parar = true } = {}) {
  if (parar && A.tocando) pausar();
  if (!S.animando) ativar(true);
  A.t = Math.max(0, Math.min(duracao(), t));
  aplicar();
  atualizarBarra();
}

// liga/desliga a prévia na vista; liga as máscaras junto (as animações revelam o placar por máscaras)
export function ativar(sim) {
  if (S.animando === sim) return;
  S.animando = sim;
  if (sim) {
    A.mascarasAntes = S.render.usarMascaras;
    S.render.usarMascaras = true;
    if (!A.dados && !A.carregando) simular();
  } else {
    pausar();
    if (A.mascarasAntes !== null) S.render.usarMascaras = A.mascarasAntes;
    A.mascarasAntes = null;
  }
  $('#viewport').classList.toggle('animando', sim);
  remontarBarra();
  aplicar();
  atualizarBarra();
  emitir('animacao');
}

export function trocarMetodos(lst) {
  A.metodos = lst;
  A.t = 0;
  simular();
}

// ---------------------------------------------------------------- consultas para os painéis
export const ROTULO_PROP = { _x: 'X', _y: 'Y', _xscale: 'escala X', _yscale: 'escala Y', _alpha: 'opacidade', _visible: 'visível',
  _rotation: 'rotação', _width: 'largura', _height: 'altura', _scale: 'escala' };

export function tweensDe(caminho) {
  return ((A.dados && A.dados.tweens) || []).filter((t) => t.alvo === caminho);
}

// quantas animações usam o mesmo valor do código (constante ou trecho)
export function usosDoSlot(slot) {
  if (!slot || !A.dados) return 0;
  let n = 0;
  for (const t of A.dados.tweens || []) {
    if (t.dur_slot === slot || t.atraso_slot === slot || t.para_slot === slot || t.ease_slot === slot) n++;
  }
  return n;
}

export function fmtQuadros(q) {
  const s = q / fps();
  return `${Math.round(q * 10) / 10} q · ${s.toFixed(2).replace('.', ',')} s`;
}

// ---------------------------------------------------------------- barra da linha do tempo (embaixo da vista)
const OPCOES_METODO = (m) => {
  const tem = (n) => m.includes(n);
  const out = [];
  if (tem('AnimateIn')) out.push({ v: 'AnimateIn', r: 'Entrada (AnimateIn)' });
  const saida = ['Remove', 'AnimateOut', 'Hide'].find(tem);
  if (tem('AnimateIn') && saida) out.push({ v: 'AnimateIn|' + saida, r: `Entrada e saída (${saida})` });
  return out;
};

export function montarBarraTempo() {
  let b = $('#linha-tempo');
  if (!b) {
    b = el('div', { id: 'linha-tempo', class: 'linha-tempo', role: 'toolbar', 'aria-label': 'Prévia da animação' });
    $('#viewport').append(b);
  }
  b.innerHTML = '';
  const btInicio = el('button', { class: 'btn-icone', title: 'Voltar ao início', html: icone('inicio', 15) });
  btInicio.onclick = () => irPara(0);
  const btPlay = el('button', { class: 'btn-icone play', id: 'lt-play', title: 'Tocar / pausar (barra de espaço)', html: icone('play', 16) });
  btPlay.onclick = () => (A.tocando ? pausar() : tocar());
  const btFim = el('button', { class: 'btn-icone', title: 'Ir para o fim (placar montado)', html: icone('fim', 15) });
  btFim.onclick = () => irPara(duracao());
  const sel = el('select', { class: 'seletor', id: 'lt-metodo', title: 'Qual animação do placar simular' });
  sel.onchange = () => trocarMetodos(sel.value.split('|'));
  const tempo = el('span', { class: 'lt-tempo', id: 'lt-tempo' });
  const faixa = el('div', { class: 'lt-faixa' });
  const marcas = el('div', { class: 'lt-marcas', id: 'lt-marcas' });
  const range = el('input', { type: 'range', id: 'lt-range', min: 0, max: 100, step: 0.05, value: 0, title: 'Arraste para ver quadro a quadro' });
  range.oninput = () => irPara(Number(range.value));
  faixa.append(marcas, range);
  const vel = el('select', { class: 'seletor', title: 'Velocidade' });
  for (const v of [0.1, 0.25, 0.5, 1, 2]) vel.append(el('option', { value: v }, v === 1 ? '1×' : String(v).replace('.', ',') + '×'));
  vel.value = String(A.vel);
  vel.onchange = () => { A.vel = Number(vel.value); };
  const qps = el('select', { class: 'seletor', id: 'lt-fps', title: 'Quadros por segundo da animação. O arquivo diz o ritmo do placar; troque para comparar.' });
  qps.onchange = () => { A.fps = qps.value === 'arquivo' ? null : Number(qps.value); atualizarBarra(); emitir('animacao'); };
  const btRep = el('button', { class: 'btn-icone' + (A.repetir ? ' ativo' : ''), title: 'Repetir', html: icone('repetir', 15) });
  btRep.onclick = () => { A.repetir = !A.repetir; btRep.classList.toggle('ativo', A.repetir); };
  const btX = el('button', { class: 'btn-icone', title: 'Sair da prévia (volta ao placar parado, para editar)', html: icone('x', 15) });
  btX.onclick = () => ativar(false);
  b.append(btInicio, btPlay, btFim, sel, tempo, faixa, vel, qps, btRep, btX);
  atualizarBarra();
}

export function atualizarBarra() {
  const b = $('#linha-tempo');
  if (!b) return;
  b.hidden = !S.animando || !S.doc;
  if (b.hidden) return;
  const d = A.dados;
  const dur = duracao();
  $('#lt-play').innerHTML = icone(A.tocando ? 'pausa' : 'play', 16);
  const range = $('#lt-range');
  range.max = dur;
  if (document.activeElement !== range || A.tocando) range.value = A.t;
  range.style.setProperty('--p', (A.t / dur * 100) + '%');
  const cab = $('#gantt-cabeca');
  if (cab) { cab.style.setProperty('--p', Math.min(1, A.t / dur)); cab.hidden = false; }
  $('#lt-tempo').textContent = d ? `${(A.t / fps()).toFixed(2).replace('.', ',')} s · quadro ${Math.round(A.t)} de ${Math.round(dur)}` : (A.carregando ? 'simulando…' : '—');
  // métodos
  const sel = $('#lt-metodo');
  const atual = A.metodos.join('|');
  const metodos = (d && d.metodos) || [];
  const chaveOpcoes = metodos.join(',');
  if (sel.dataset.chave !== chaveOpcoes) {
    sel.dataset.chave = chaveOpcoes;
    sel.innerHTML = '';
    const base = OPCOES_METODO(metodos);
    for (const o of base) sel.append(el('option', { value: o.v }, o.r));
    const animado = (m) => /anim|show|hide|remove|intro|out|goal|card|in[A-Z]/i.test(m);
    const jaListados = new Set(base.flatMap((o) => o.v.split('|')));
    const outros = metodos.filter((m) => !['constructor', 'Init', 'Initialize'].includes(m) && !jaListados.has(m))
      .sort((x, y) => (animado(y) - animado(x)) || x.localeCompare(y));
    if (outros.length) {
      const g = el('optgroup', { label: 'Outros métodos do placar' });
      for (const m of outros) g.append(el('option', { value: 'AnimateIn|' + m }, m));
      sel.append(g);
    }
    if (!sel.options.length) sel.append(el('option', { value: 'AnimateIn' }, 'Entrada (AnimateIn)'));
  }
  if ([...sel.options].some((o) => o.value === atual)) sel.value = atual;
  const qps = $('#lt-fps');
  const arq = (d && d.fps) || 30;
  const chaveQ = String(arq);
  if (qps.dataset.chave !== chaveQ) {
    qps.dataset.chave = chaveQ;
    qps.innerHTML = '';
    qps.append(el('option', { value: 'arquivo' }, `${arq} qps (arquivo)`));
    for (const v of [30, 60]) if (v !== arq) qps.append(el('option', { value: v }, `${v} qps`));
  }
  qps.value = A.fps ? String(A.fps) : 'arquivo';
  // marcas: início de cada método (entrada, saída...) e das animações
  const marcas = $('#lt-marcas');
  const chaveM = d ? `${dur}|${(d.tweens || []).length}|${(d.marcas || []).map((m) => m.t).join(',')}` : '';
  if (marcas.dataset.chave !== chaveM) {
    marcas.dataset.chave = chaveM;
    marcas.innerHTML = '';
    if (d) {
      for (const tw of d.tweens || []) {
        marcas.append(el('span', { class: 'lt-tw', style: { left: (tw.t0 / dur * 100) + '%', width: Math.max(0.4, tw.dur / dur * 100) + '%' } }));
      }
      for (const m of (d.marcas || []).slice(1)) {
        marcas.append(el('span', { class: 'lt-metodo', style: { left: (m.t / dur * 100) + '%' }, title: m.metodo }, m.metodo));
      }
    }
  }
}

export function resumoErros() {
  const d = A.dados;
  if (!d) return '';
  const e = (d.erros || []).filter((x) => !/^laço interrompido/.test(x));
  return e.length ? e.map((x) => esc(x)).join('<br>') : '';
}
