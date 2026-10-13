// Criador de Minifaces — interface (BRFP Super Tool).
import { $, el, esc, aviso, modal, confirmar, barraMenus, abrirMenu, divisorArrastavel, dialogoSobre, interruptor, nota, modalAberto, menuAberto, lerArquivoBase64 } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { instalarComponentes } from './comum/componentes.js';
import { importarReferencias } from './comum/referencias.js';

const S = {
  itens: [], opcoes: {}, export: {}, analisando: 0, motor: {}, banco: null, time: null, sel: null, item: null, foto: null,
  modo: 'mover', elenco: [], elencoTime: null, times: null, fundoVista: 'xadrez', ref: false, polling: null, ultimoFimExport: null,
};
const FUNDOS = [['auto', 'Automático', 'Usa a transparência da foto se houver; senão separa o jogador do fundo.'],
  ['transparencia', 'Transparência', 'Usa o canal alfa da foto (PNG recortado), limpando o halo semitransparente.'],
  ['remover', 'Remover fundo', 'Separa o jogador do fundo pela cor e pelo rosto (GrabCut). Use o pincel para corrigir.'],
  ['nenhum', 'Manter tudo', 'Não mexe no fundo (a foto entra inteira no quadro).']];

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }
const sel = () => S.itens.find((i) => i.id === S.sel) || null;
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');

// ---------------------------------------------------------------- estado
function aplicar(r) {
  if (!r) return;
  for (const k of ['itens', 'opcoes', 'export', 'analisando', 'motor', 'banco', 'time']) if (k in r) S[k] = r[k];
  if (r.do_criador) aviso(`${r.do_criador} foto(s) do Criador de Ligas e Times`, { tipo: 'sucesso', detalhe: 'Já ligadas aos IDs dos jogadores novos. Confira o enquadramento e exporte.', tempo: 6000 });
  if (S.sel !== null && !S.itens.some((i) => i.id === S.sel)) S.sel = null;
  if (S.sel === null && S.itens.length) selecionar(S.itens[0].id, false);
  desenharLista();
  desenharTopo();
  desenharStatus();
  desenharTime();
  desenharPropriedades();
  $('#vazio-vista').hidden = S.itens.length > 0;
  $('#estudio').hidden = !S.itens.length;
  const it = sel();
  if (it && it.previa) mostrarPrevia(it.previa);
  desenharVizinhos();
  if (S.analisando || S.export.rodando) iniciarPolling();
  if (!S.export.rodando && S.export.fim && S.export.fim !== S.ultimoFimExport) {
    const primeira = S.ultimoFimExport === null && !S._exportando;
    S.ultimoFimExport = S.export.fim;
    if (!primeira) fimExport(S.export.resumo);
  }
}

async function atualizar() { aplicar(await tentar(() => api('estado'))); }

function iniciarPolling() {
  if (S.polling) return;
  S.polling = setInterval(async () => {
    const r = await api('estado').catch(() => null);
    if (!r) return;
    const antes = S.item && S.itens.find((i) => i.id === S.item.id);
    aplicar(r);
    // a foto selecionada terminou de ser analisada: carrega a foto e a prévia
    const agora = sel();
    if (agora && (!S.item || S.item.id !== agora.id || (antes && antes.estado === 'analisando' && agora.estado !== 'analisando'))) carregarItem(agora.id);
    if (!r.analisando && !r.export.rodando) { clearInterval(S.polling); S.polling = null; }
  }, 700);
}

// ---------------------------------------------------------------- time (banco importado no Super Tool)
async function desenharTime() {
  const box = $('#time-linha');
  if (box._editando) return;
  box.innerHTML = '';
  if (!S.banco) {
    box.append(nota('Sem banco do jogo: importe em <b>Dados do jogo</b> no Super Tool para ligar as fotos aos jogadores (p&lt;ID&gt;).', 'alerta'));
    return;
  }
  if (S.time) {
    box.append(el('div', { class: 'time-escolhido' }, icone('trofeu', 16), el('div', { class: 'txt' }, el('b', {}, S.time.nome),
      el('small', {}, `${S.time.liga || 'sem liga'} · teamid ${S.time.teamid}`)),
    el('button', { class: 'btn-fantasma peq', onclick: () => escolherTime() }, 'Trocar')));
  } else {
    box.append(el('button', { class: 'btn peq', style: { width: '100%' }, onclick: () => escolherTime() }, icone('trofeu', 13), 'Escolher o time das fotos…'));
  }
}

async function escolherTime() {
  if (!S.times) { const r = await tentar(() => api('times')); if (!r) return; S.times = r.times; }
  const box = $('#time-linha');
  box._editando = true;
  box.innerHTML = '';
  const inp = el('input', { type: 'search', placeholder: 'Nome do time ou liga…', spellcheck: 'false', autocomplete: 'off' });
  const lista = el('div', { class: 'lista-times' });
  const wrap = el('div', { style: { position: 'relative' } }, el('label', { class: 'campo-busca' }, icone('busca', 14), inp), lista);
  box.append(wrap);
  let foco = 0, visiveis = [];
  const fechar = () => { box._editando = false; desenharTime(); };
  const desenhar = () => {
    const q = inp.value.trim().toLowerCase();
    visiveis = S.times.filter((t) => !q || `${t.nome} ${t.liga} ${t.teamid}`.toLowerCase().includes(q)).slice(0, 80);
    lista.innerHTML = '';
    visiveis.forEach((t, i) => lista.append(el('button', { class: i === foco ? 'foco' : '', onmousedown: (e) => { e.preventDefault(); escolher(t); } }, t.nome, el('small', {}, t.liga || t.teamid))));
  };
  const escolher = async (t) => {
    box._editando = false;
    const r = await tentar(() => api('time', { teamid: t.teamid }));
    if (r) { S.elencoTime = null; aplicar(r); aviso(`${r.ligadas} foto(s) ligada(s) a jogadores do ${t.nome}`, { tipo: 'sucesso', tempo: 3000 }); desenharPropriedades(); }
  };
  inp.oninput = () => { foco = 0; desenhar(); };
  inp.onkeydown = (e) => {
    if (e.key === 'ArrowDown') { foco = Math.min(visiveis.length - 1, foco + 1); desenhar(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { foco = Math.max(0, foco - 1); desenhar(); e.preventDefault(); }
    if (e.key === 'Enter' && visiveis[foco]) escolher(visiveis[foco]);
    if (e.key === 'Escape') fechar();
  };
  inp.onblur = () => setTimeout(() => { if (box._editando) fechar(); }, 150);
  desenhar();
  inp.focus();
}

async function elenco() {
  if (!S.time) return [];
  if (S.elencoTime !== S.time.teamid) {
    const r = await tentar(() => api('jogadores?teamid=' + S.time.teamid));
    S.elenco = r ? r.jogadores : [];
    S.elencoTime = S.time.teamid;
  }
  return S.elenco;
}

// ---------------------------------------------------------------- lista
function filtrados() {
  const q = $('#busca').value.trim().toLowerCase();
  const f = $('#filtro').value;
  return S.itens.filter((it) => {
    if (q && !`${it.nome} ${it.jogador ? it.jogador.nome + ' ' + it.jogador.playerid : ''}`.toLowerCase().includes(q)) return false;
    if (f === 'ligadas') return !!it.jogador;
    if (f === 'sem') return !it.jogador;
    if (f === 'problemas') return it.estado === 'sem_rosto' || it.estado === 'erro';
    return true;
  });
}

function desenharLista() {
  const l = $('#lista');
  const topo = l.scrollTop;
  l.innerHTML = '';
  if (S.motor.instalar && !S.motor.ok) {
    l.append(el('div', { class: 'aviso-motor' }, nota(esc(S.motor.msg), 'alerta'),
      el('button', { class: 'btn-primario peq', onclick: componentesMotor }, icone('baixar', 12), 'Baixar os componentes…')));
  }
  if (!S.itens.length) { l.append(el('div', { class: 'arvore-vazia' }, 'Nenhuma foto. Arraste imagens para a janela ou use os botões acima.')); return; }
  const itens = filtrados();
  if (!itens.length) { l.append(el('div', { class: 'arvore-vazia' }, 'Nada com esse filtro.')); return; }
  for (const it of itens) {
    const mini = el('span', { class: 'mini', style: it.previa ? { backgroundImage: `url(data:image/png;base64,${it.previa})` } : {} });
    if (!it.previa) mini.innerHTML = icone(it.estado === 'analisando' ? 'recarregar' : 'imagem', 16, it.estado === 'analisando' ? 'girando' : '');
    const sub = it.jogador
      ? el('small', { class: 'ligado' }, `p${it.jogador.playerid} · ${it.jogador.nome}${it.jogador.manual ? '' : ` (${Math.round(it.jogador.confianca * 100)}%)`}`)
      : el('small', { class: 'sem' }, S.time ? 'sem jogador ligado' : 'escolha o time para ligar');
    const est = it.estado === 'sem_rosto' || it.estado === 'erro' ? icone('aviso', 14) : it.exportado ? icone('check', 14) : '';
    l.append(el('button', { class: `foto ${S.sel === it.id ? 'sel' : ''}`, 'data-id': it.id, title: it.caminho, onclick: () => selecionar(it.id),
      oncontextmenu: (e) => { e.preventDefault(); selecionar(it.id); menuFoto(e.clientX, e.clientY, it); } },
    mini, el('span', { class: 'txt' }, el('b', {}, it.nome), sub),
    el('span', { class: 'est', style: { color: it.exportado ? 'var(--sucesso)' : 'var(--perigo)' }, title: it.erro || (it.exportado ? 'Exportada: ' + it.exportado : ''), html: est })));
  }
  l.scrollTop = topo;
  $('#resumo-lista').textContent = `${itens.length} de ${S.itens.length} · ${S.itens.filter((i) => i.jogador).length} ligadas`;
}

function menuFoto(x, y, it) {
  abrirMenu([
    { rotulo: 'Restaurar ajustes', icone: 'restaurar', fn: () => restaurar(it.id) },
    { rotulo: 'Desligar o jogador', icone: 'x', desabilitado: !it.jogador, fn: () => ligar(it.id, '') },
    { rotulo: 'Mostrar a foto no Explorer', icone: 'externo', fn: () => tentar(() => api('abrir', { caminho: it.caminho })) },
    { rotulo: 'Mostrar a miniface exportada', icone: 'externo', desabilitado: !it.exportado, fn: () => tentar(() => api('abrir', { caminho: it.exportado })) },
    '-',
    { rotulo: 'Tirar da lista', icone: 'apagar', fn: () => remover([it.id]) },
  ], x, y);
}

async function selecionar(id, carregar = true) {
  S.sel = id;
  document.querySelectorAll('#lista .foto').forEach((e) => e.classList.toggle('sel', +e.dataset.id === id));
  if (carregar) await carregarItem(id);
}

async function carregarItem(id) {
  const it = await tentar(() => api('item?id=' + id));
  if (!it || S.sel !== id) return;
  S.item = it;
  S.tracoAtual = null;
  if (it.foto) {
    const img = new Image();
    img.onload = () => { S.foto = img; desenharFoto(); };
    img.src = 'data:image/png;base64,' + it.foto;
  } else { S.foto = null; desenharFoto(); }
  if (it.previa) mostrarPrevia(it.previa); else $('#img-mini').removeAttribute('src');
  desenharPropriedades();
  desenharVizinhos();
}

function mostrarPrevia(b64) {
  $('#img-mini').src = 'data:image/png;base64,' + b64;
  const it = S.item;
  $('#legenda-mini').textContent = it ? `${S.opcoes.lado || 180}×${S.opcoes.lado || 180} · ${it.jogador ? 'p' + it.jogador.playerid + '.png' : 'sem jogador ligado'}` : '';
}

function desenharVizinhos() {
  const v = $('#vizinhos');
  v.innerHTML = '';
  const its = filtrados();
  const i = its.findIndex((x) => x.id === S.sel);
  if (i < 0) return;
  for (const x of its.slice(Math.max(0, i - 3), i + 4)) {
    if (!x.previa) continue;
    v.append(el('button', { class: `vz ${x.id === S.sel ? 'atual' : ''}`, title: x.nome, onclick: () => selecionar(x.id) }, el('img', { src: 'data:image/png;base64,' + x.previa })));
  }
}

// ---------------------------------------------------------------- foto original (canvas): quadro, rosto e pincel
function geometria() {
  const c = $('#tela-foto');
  const W = c.clientWidth, H = c.clientHeight;
  const it = S.item;
  if (!S.foto || !it || !it.analise) return null;
  const e = it.analise.escala_foto;
  const fw = S.foto.width, fh = S.foto.height;
  const v = Math.min((W - 40) / fw, (H - 70) / fh);
  return { W, H, e, v, ox: (W - fw * v) / 2, oy: (H - fh * v) / 2 + 12, k: e * v };
}
const paraTela = (g, x, y) => [g.ox + x * g.k, g.oy + y * g.k];
const paraFoto = (g, X, Y) => [(X - g.ox) / g.k, (Y - g.oy) / g.k];

function desenharFoto() {
  const c = $('#tela-foto');
  const dpr = window.devicePixelRatio || 1;
  c.width = c.clientWidth * dpr;
  c.height = c.clientHeight * dpr;
  const ctx = c.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, c.clientWidth, c.clientHeight);
  const g = geometria();
  const it = S.item;
  if (!g) {
    $('#legenda-foto').textContent = it && it.estado === 'analisando' ? 'Analisando…' : '';
    return;
  }
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(S.foto, g.ox, g.oy, S.foto.width * g.v, S.foto.height * g.v);
  // traços
  const tracos = [...(it.params.tracos || []), ...(S.tracoAtual ? [S.tracoAtual] : [])];
  for (const t of tracos) {
    ctx.strokeStyle = t.manter ? 'rgba(69,185,124,.75)' : 'rgba(240,86,90,.75)';
    ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = t.raio * 2 * g.k;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath();
    t.pontos.forEach((p, i) => { const [X, Y] = paraTela(g, p[0], p[1]); if (i) ctx.lineTo(X, Y); else ctx.moveTo(X, Y); });
    if (t.pontos.length === 1) { const [X, Y] = paraTela(g, t.pontos[0][0], t.pontos[0][1]); ctx.arc(X, Y, t.raio * g.k, 0, Math.PI * 2); ctx.fill(); } else ctx.stroke();
  }
  // janela da miniface (escurece o resto)
  const jan = S.arrasto && S.arrasto.janela ? S.arrasto.janela : it.janela;
  if (jan) {
    const [X0, Y0] = paraTela(g, jan[0], jan[1]);
    const L = jan[2] * g.k;
    ctx.save();
    ctx.fillStyle = 'rgba(8,10,14,.55)';
    ctx.beginPath();
    ctx.rect(0, 0, g.W, g.H);
    ctx.rect(X0 + L, Y0, -L, L);
    ctx.fill('evenodd');
    ctx.strokeStyle = '#4c8dff';
    ctx.lineWidth = 2;
    ctx.strokeRect(X0, Y0, L, L);
    ctx.restore();
  }
  // rosto
  const r = S.arrasto && S.arrasto.rosto ? S.arrasto.rosto : (it.params.rosto || it.analise.rosto);
  if (r) {
    const [X, Y] = paraTela(g, r[0], r[1]);
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = '#ff9233';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(X, Y, r[2] * g.k, r[2] * g.k);
    ctx.restore();
  }
  const a = it.analise;
  $('#legenda-foto').textContent = `${a.largura}×${a.altura} · ${a.transparente ? 'com transparência' : 'sem transparência'} · rosto: ${it.params.rosto ? 'marcado à mão' : { frente: 'detectado', perfil: 'detectado (perfil)', silhueta: 'estimado pela silhueta', nenhum: 'não encontrado' }[a.origem] || a.origem}`;
}

function prepararCanvas() {
  const c = $('#tela-foto');
  new ResizeObserver(() => desenharFoto()).observe(c);
  c.addEventListener('pointerdown', (e) => {
    const g = geometria();
    const it = S.item;
    if (!g || !it) return;
    const [x, y] = paraFoto(g, e.offsetX, e.offsetY);
    c.setPointerCapture(e.pointerId);
    if (S.modo === 'mover' && it.janela) {
      S.arrasto = { tipo: 'mover', x0: x, y0: y, janela0: it.janela.slice(), janela: it.janela.slice() };
    } else if (S.modo === 'rosto') {
      S.arrasto = { tipo: 'rosto', x0: x, y0: y, rosto: [x, y, 1] };
    } else if (S.modo === 'manter' || S.modo === 'apagar') {
      const raio = +$('#raio').value / g.k;
      S.tracoAtual = { manter: S.modo === 'manter', raio: Math.max(1, raio), pontos: [[Math.round(x), Math.round(y)]] };
      S.arrasto = { tipo: 'traco' };
    }
    desenharFoto();
  });
  c.addEventListener('pointermove', (e) => {
    if (!S.arrasto) return;
    const g = geometria();
    if (!g) return;
    const [x, y] = paraFoto(g, e.offsetX, e.offsetY);
    const a = S.arrasto;
    if (a.tipo === 'mover') {
      a.janela = [a.janela0[0] + (x - a.x0), a.janela0[1] + (y - a.y0), a.janela0[2]];
    } else if (a.tipo === 'rosto') {
      const s = Math.max(Math.abs(x - a.x0), Math.abs(y - a.y0));
      a.rosto = [x < a.x0 ? a.x0 - s : a.x0, y < a.y0 ? a.y0 - s : a.y0, s];
    } else if (a.tipo === 'traco' && S.tracoAtual) {
      const ult = S.tracoAtual.pontos[S.tracoAtual.pontos.length - 1];
      if (Math.hypot(x - ult[0], y - ult[1]) > S.tracoAtual.raio * 0.4) S.tracoAtual.pontos.push([Math.round(x), Math.round(y)]);
    }
    desenharFoto();
  });
  c.addEventListener('pointerup', async () => {
    const a = S.arrasto;
    S.arrasto = null;
    const it = S.item;
    if (!a || !it) return;
    if (a.tipo === 'mover') {
      const lado = it.janela[2];
      const dxs = a.janela[0] - a.janela0[0], dys = a.janela[1] - a.janela0[1];
      if (Math.abs(dxs) + Math.abs(dys) < 0.5) { desenharFoto(); return; }
      const aj = it.params.ajuste;
      // mover o quadro para a direita = o rosto vai para a esquerda na miniface
      await enviar({ ajuste: { dx: aj.dx - dxs * 180 / lado, dy: aj.dy - dys * 180 / lado } });
    } else if (a.tipo === 'rosto') {
      if (a.rosto[2] < 8) { desenharFoto(); return; }
      await enviar({ rosto: a.rosto.map((v) => Math.round(v * 10) / 10), ajuste: { zoom: 1, dx: 0, dy: 0 } });
      definirModo('mover');
    } else if (a.tipo === 'traco' && S.tracoAtual) {
      const t = S.tracoAtual;
      S.tracoAtual = null;
      const extra = it.params.fundo === 'nenhum' ? { fundo: it.analise.transparente ? 'transparencia' : 'remover' } : {};
      await enviar({ tracos: [...(it.params.tracos || []), t], ...extra });
    }
  });
  c.addEventListener('wheel', (e) => {
    const it = S.item;
    if (!it || !it.janela) return;
    e.preventDefault();
    const z = Math.max(0.5, Math.min(2, it.params.ajuste.zoom * (e.deltaY < 0 ? 1.04 : 1 / 1.04)));
    it.params.ajuste.zoom = z;
    clearTimeout(S._zoom);
    S._zoom = setTimeout(() => enviar({ ajuste: { zoom: Math.round(z * 1000) / 1000 } }), 180);
    desenharPropriedadesValores();
  }, { passive: false });
}

function definirModo(m) {
  S.modo = m;
  document.querySelectorAll('#ferramentas [data-modo]').forEach((b) => b.classList.toggle('ativo', b.dataset.modo === m));
  $('#tela-foto').style.cursor = { mover: 'grab', rosto: 'crosshair', manter: 'cell', apagar: 'cell' }[m];
}

let pedido = 0;
async function enviar(params, ids = null) {
  const it = S.item;
  if (!it) return;
  const n = ++pedido;
  const fim = carregando('Gerando…');
  try {
    const r = await api('params', ids ? { ids, params } : { id: it.id, params });
    if (n !== pedido) return;
    if (r.item) {
      Object.assign(it, r.item);
      const li = S.itens.findIndex((x) => x.id === it.id);
      if (li >= 0) S.itens[li] = { ...S.itens[li], ...r.item };
      mostrarPrevia(r.previa);
      desenharFoto();
      desenharLista();
      desenharPropriedadesValores();
      desenharVizinhos();
    } else {
      aplicar(r);
      carregarItem(it.id);
    }
  } catch (e) { aviso(e.message, { tipo: 'erro' }); } finally { fim(); }
}

function carregando(txt) {
  const a = $('#carregando');
  clearTimeout(S._carreg);
  S._carreg = setTimeout(() => { a.hidden = false; a.innerHTML = icone('recarregar', 15, 'girando') + esc(txt); }, 250);
  return () => { clearTimeout(S._carreg); a.hidden = true; };
}

// ---------------------------------------------------------------- painel direito
function secao(chave, titulo, ic, corpo, aberta = true) {
  const d = el('details', { class: 'secao', 'data-k': chave });
  d.open = S._abertas && chave in S._abertas ? S._abertas[chave] : aberta;
  d.addEventListener('toggle', () => { S._abertas = { ...(S._abertas || {}), [chave]: d.open }; });
  d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo)));
  return d;
}

function deslizante(rot, chave, min, max, passo, valor, fmtv, aoSoltar) {
  const span = el('span', {}, fmtv(valor));
  const inp = el('input', { type: 'range', min, max, step: passo, value: valor, 'data-k': chave });
  inp.oninput = () => { span.textContent = fmtv(+inp.value); };
  inp.onchange = () => aoSoltar(+inp.value);
  inp.ondblclick = () => { inp.value = chave === 'zoom' ? 1 : 0; inp.onchange(); inp.oninput(); };
  return el('div', { class: 'deslizante', title: 'Duplo clique volta ao padrão' }, el('label', {}, rot), inp, span);
}

function desenharPropriedadesValores() {
  const it = S.item;
  if (!it) return;
  const p = $('#propriedades');
  const set = (k, v, f) => { const i = p.querySelector(`input[data-k="${k}"]`); if (i && document.activeElement !== i) { i.value = v; i.parentElement.querySelector('span').textContent = f(v); } };
  set('zoom', it.params.ajuste.zoom, (v) => Math.round(v * 100) + '%');
  set('dx', it.params.ajuste.dx, (v) => Math.round(v) + ' px');
  set('dy', it.params.ajuste.dy, (v) => Math.round(v) + ' px');
}

async function desenharPropriedades() {
  const p = $('#propriedades');
  if (p.contains(document.activeElement) && document.activeElement.tagName === 'INPUT' && document.activeElement.type !== 'range') return;
  p.innerHTML = '';
  const it = S.item && S.item.id === S.sel ? { ...S.item, ...(sel() || {}) } : null;
  if (it) {
    const a = it.analise || {};
    const cab = el('div', { class: 'prop-cab' }, el('h3', { title: it.caminho }, it.nome), el('div', { class: 'sub' }, it.caminho));
    const et = el('div', { class: 'etiquetas' });
    if (it.estado === 'analisando') et.append(el('span', { class: 'etiqueta azul' }, 'analisando…'));
    if (a.largura) et.append(el('span', { class: 'etiqueta' }, `${a.largura}×${a.altura}`), el('span', { class: 'etiqueta' }, a.transparente ? 'fundo transparente' : 'fundo opaco'));
    if (it.estado === 'sem_rosto') et.append(el('span', { class: 'etiqueta vermelha' }, 'rosto não encontrado'));
    else if (a.origem && a.origem !== 'frente') et.append(el('span', { class: 'etiqueta amarela', title: 'Confira o enquadramento' }, a.origem === 'perfil' ? 'rosto de perfil' : 'rosto estimado'));
    if (it.exportado) et.append(el('span', { class: 'etiqueta verde', title: it.exportado }, 'exportada'));
    cab.append(et);
    p.append(cab);
    if (it.erro) p.append(el('div', { style: { padding: '10px 14px 0' } }, nota(esc(it.erro), it.estado === 'sem_rosto' ? 'alerta' : 'erro')));
    // jogador
    const cj = [];
    if (!S.banco) cj.push(nota('Importe o banco do jogo em <b>Dados do jogo</b> (Super Tool) para ligar a foto a um jogador.', 'alerta'));
    else if (!S.time) cj.push(nota('Escolha o <b>time</b> no topo da lista de fotos: as fotos são ligadas aos jogadores dele pelo nome do arquivo.'));
    else {
      const jogs = await elenco();
      const s = el('select', { onchange: (e) => { const j = jogs.find((x) => x.playerid === e.target.value); ligar(it.id, e.target.value, j); } },
        el('option', { value: '' }, '— sem jogador —'),
        ...jogs.map((j) => { const o = el('option', { value: j.playerid }, `${j.camisa_num ? j.camisa_num + ' · ' : ''}${j.nome} (${j.playerid})`); o.selected = it.jogador && it.jogador.playerid === j.playerid; return o; }));
      if (it.jogador && !jogs.some((j) => j.playerid === it.jogador.playerid)) {
        const o = el('option', { value: it.jogador.playerid }, `${it.jogador.nome} (${it.jogador.playerid}) — fora do elenco`); o.selected = true; s.append(o);
      }
      cj.push(el('div', { class: 'jogador-sel' }, s));
      cj.push(el('div', { class: 'mudo peq-txt' }, it.jogador ? (it.jogador.manual ? `Escolhido à mão → p${it.jogador.playerid}.png` : `Ligado pelo nome do arquivo (${Math.round(it.jogador.confianca * 100)}% de semelhança) → p${it.jogador.playerid}.png`)
        : 'Nenhum jogador do elenco parecido com o nome do arquivo.'));
    }
    const idm = el('input', { type: 'text', class: 'entrada mono', placeholder: 'ID do jogador (playerid)', value: it.jogador ? it.jogador.playerid : '', style: { flex: 1 } });
    idm.onkeydown = (e) => { if (e.key === 'Enter') ligar(it.id, idm.value.trim()); };
    cj.push(el('div', { class: 'jogador-sel' }, idm, el('button', { class: 'btn peq', onclick: () => ligar(it.id, idm.value.trim()) }, 'Usar ID')));
    p.append(secao('jogador', 'Jogador', 'ligar', cj));
    // enquadramento
    const aj = it.params.ajuste;
    p.append(secao('quadro', 'Enquadramento', 'maximizar', [
      deslizante('Zoom', 'zoom', 0.6, 1.6, 0.01, aj.zoom, (v) => Math.round(v * 100) + '%', (v) => enviar({ ajuste: { zoom: v } })),
      deslizante('Horizontal', 'dx', -60, 60, 1, aj.dx, (v) => Math.round(v) + ' px', (v) => enviar({ ajuste: { dx: v } })),
      deslizante('Vertical', 'dy', -60, 60, 1, aj.dy, (v) => Math.round(v) + ' px', (v) => enviar({ ajuste: { dy: v } })),
      el('div', { class: 'mudo peq-txt' }, 'Na foto: arraste o quadro azul para mover e use a roda do mouse para aproximar.'),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', onclick: () => definirModo('rosto') }, icone('alvo', 12), 'Marcar o rosto'),
        el('button', { class: 'btn peq', onclick: () => restaurar(it.id) }, icone('restaurar', 12), 'Restaurar'),
        el('button', { class: 'btn-fantasma peq', title: 'Usa este zoom e posição em todas as fotos da lista', onclick: () => aplicarATodas({ ajuste: { ...aj } }) }, 'Aplicar a todas')),
    ]));
    // fundo
    const seg = el('div', { class: 'segmentado', style: { flexWrap: 'wrap' } }, ...FUNDOS.map(([v, r, d]) => el('button', { class: it.params.fundo === v ? 'ativo' : '', title: d, onclick: () => enviar({ fundo: v }) }, r)));
    const desc = (FUNDOS.find((f) => f[0] === it.params.fundo) || FUNDOS[0])[2];
    p.append(secao('fundo', 'Fundo', 'pincel', [seg, el('div', { class: 'mudo peq-txt' }, desc),
      deslizante('Limpeza', 'limpeza', 0, 1, 0.05, it.params.limpeza, (v) => Math.round(v * 100) + '%', (v) => enviar({ limpeza: v })),
      el('div', { class: 'mudo peq-txt' }, 'Sobrou fundo ou sumiu parte do jogador? Pinte na foto com o pincel verde (manter) ou vermelho (apagar).'),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', onclick: () => definirModo('manter') }, icone('pincelMais', 12), 'Manter'),
        el('button', { class: 'btn peq', onclick: () => definirModo('apagar') }, icone('borracha', 12), 'Apagar'),
        el('button', { class: 'btn-fantasma peq', disabled: !(it.params.tracos || []).length, onclick: () => enviar({ tracos: [] }) }, 'Limpar traços')),
    ]));
  }
  // saída (vale para todas)
  const op = S.opcoes;
  const caminho = el('input', { type: 'text', class: 'entrada mono', value: op.saida || '', placeholder: 'Escolha a pasta de saída', spellcheck: 'false', onchange: (e) => opcoes({ saida: e.target.value.trim() }) });
  const lado = el('input', { type: 'number', class: 'entrada', min: 64, max: 1024, value: op.lado || 180, style: { width: '90px' }, onchange: (e) => opcoes({ lado: +e.target.value || 180 }) });
  const semLig = el('select', { class: 'seletor', onchange: (e) => opcoes({ sem_ligacao: e.target.value }) },
    ...[['pular', 'não exportar'], ['nome', 'exportar com o nome do arquivo']].map(([v, r]) => { const o = el('option', { value: v }, r); o.selected = op.sem_ligacao === v; return o; }));
  p.append(secao('saida', 'Saída', 'pasta', [
    el('div', { class: 'campo' }, el('label', {}, 'Pasta de saída'), el('div', { class: 'caminho-linha' }, caminho,
      el('button', { class: 'btn', title: 'Escolher…', onclick: escolherSaida }, icone('pasta', 14)))),
    el('div', { class: 'linha-prop' }, el('label', {}, 'Tamanho'), el('div', { style: { display: 'flex', gap: '8px', alignItems: 'center' } }, lado, el('span', { class: 'mudo peq-txt' }, 'px (o jogo usa 180)'))),
    el('div', { class: 'linha-prop' }, el('label', {}, 'Sem jogador'), semLig),
    interruptor({ titulo: 'Sobrescrever existentes', descricao: 'Substitui p&lt;ID&gt;.png que já existam na pasta.', marcado: op.sobrescrever, aoMudar: (v) => opcoes({ sobrescrever: v }) }).el,
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', disabled: !op.saida, onclick: () => tentar(() => api('abrir', {})) }, icone('externo', 12), 'Abrir a pasta')),
  ], !it));
}

async function ligar(id, playerid, j = null) {
  const r = await tentar(() => api('ligar', { id, playerid, nome: j ? j.nome : '', camisa: j ? j.camisa_num : '' }));
  if (!r) return;
  aplicar(r);
  const it = S.itens.find((x) => x.id === id);
  if (S.item && it) S.item.jogador = it.jogador;
  desenharPropriedades();
  if (it) mostrarPrevia(it.previa || '');
}
async function restaurar(id) {
  const r = await tentar(() => api('restaurar', { id }));
  if (r && S.item && S.item.id === id) { Object.assign(S.item, r.item); mostrarPrevia(r.previa); desenharFoto(); desenharPropriedades(); atualizar(); }
}
async function aplicarATodas(params) {
  if (!await confirmar('Aplicar a todas as fotos?', 'O zoom e a posição desta foto passam a valer para todas as fotos da lista.', { rotulo: 'Aplicar' })) return;
  const fim = carregando('Aplicando…');
  const r = await tentar(() => api('params', { ids: S.itens.map((i) => i.id), params }));
  fim();
  if (r) { aplicar(r); aviso('Ajuste aplicado — as prévias se atualizam ao abrir cada foto', { tipo: 'sucesso', tempo: 2600 }); carregarItem(S.sel); }
}
async function opcoes(d) { aplicar(await tentar(() => api('opcoes', d))); }
async function escolherSaida() {
  const r = await tentar(() => api('dialogo', { modo: 'saida' }));
  if (r && r.caminhos.length) await opcoes({ saida: r.caminhos[0] });
}

// ---------------------------------------------------------------- topo / status
function desenharTopo() {
  const prontas = S.itens.filter((i) => i.estado === 'pronto' && (i.jogador || S.opcoes.sem_ligacao === 'nome')).length;
  const b = $('#btn-exportar');
  b.disabled = S.export.rodando || !prontas;
  $('#contador').hidden = !prontas || S.export.rodando;
  $('#contador').textContent = prontas;
  $('#btn-exportar-txt').textContent = S.export.rodando ? `Exportando ${S.export.feitos}/${S.export.total}…` : 'Exportar';
  $('#btn-exportar-ic').innerHTML = icone(S.export.rodando ? 'recarregar' : 'upload', 14, S.export.rodando ? 'girando' : '');
  $('#titulo').innerHTML = `<b>${S.itens.length} ${S.itens.length === 1 ? 'foto' : 'fotos'}</b><span class="pasta">${S.time ? esc(S.time.nome) + ' · ' : ''}saída: ${esc(S.opcoes.saida || 'escolha a pasta')}</span>`;
}

function desenharStatus() {
  const lig = S.itens.filter((i) => i.jogador).length;
  const sem = S.itens.filter((i) => i.estado === 'sem_rosto' || i.estado === 'erro').length;
  $('#status-esq').innerHTML = S.itens.length
    ? `<span><b>${S.itens.length}</b> fotos</span><span><b>${lig}</b> ligadas</span>${sem ? `<span><b>${sem}</b> sem rosto</span>` : ''}${S.analisando ? `<span>analisando ${S.analisando}…</span>` : ''}`
    : '<span>Arraste fotos para a janela ou use Arquivo › Adicionar.</span>';
  const pr = $('#status-progresso');
  pr.hidden = !S.export.rodando;
  if (S.export.rodando) {
    $('#progresso-barra').style.width = `${(100 * S.export.feitos) / Math.max(1, S.export.total)}%`;
    $('#progresso-txt').textContent = `${S.export.feitos}/${S.export.total}`;
  }
  const cb = $('#chip-banco');
  cb.className = 'chip ' + (S.banco ? 'ok' : 'aviso');
  cb.innerHTML = icone('bancoDados', 12) + (S.banco ? `${S.banco.nome_jogo} · ${fmt(S.banco.contagens.teams)} times` : 'sem banco');
  cb.title = S.banco ? S.banco.caminho : 'Importe o banco em Dados do jogo (Super Tool)';
  const cm = $('#chip-motor');
  cm.className = 'chip ' + (S.motor.ok ? 'ok' : S.motor.msg === 'verificando…' ? '' : 'erro');
  cm.innerHTML = icone(S.motor.ok ? 'check' : 'aviso', 12) + (S.motor.ok ? 'Motor pronto' : S.motor.msg === 'verificando…' ? 'verificando o motor…' : 'Motor indisponível');
  cm.title = S.motor.msg || '';
  cm.classList.toggle('clicavel', !!S.motor.instalar);
  cm.onclick = S.motor.instalar ? componentesMotor : null;
}

async function componentesMotor() {
  await instalarComponentes({ aoTerminar: () => esperarMotor() });
}

function esperarMotor() {
  // o servidor sobe o motor e reanalisa as fotos que falharam
  const t = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (e) aplicar(e);
    if (e && e.motor.ok && !e.analisando) clearInterval(t);
  }, 800);
  setTimeout(() => clearInterval(t), 120000);
}

// ---------------------------------------------------------------- ações
async function adicionar(modo) {
  const r = await tentar(() => api('dialogo', { modo }));
  if (!r || !r.caminhos.length) return;
  const a = await tentar(() => api('adicionar', { caminhos: r.caminhos }));
  if (a) { aplicar(a); aviso(a.novos ? `${a.novos} foto(s) adicionada(s) — analisando` : 'Nada novo: essas fotos já estão na lista.', { tipo: a.novos ? 'sucesso' : 'aviso', tempo: 2500 }); }
}
async function remover(ids) { aplicar(await tentar(() => api('remover', { ids }))); if (!S.itens.length) { S.item = null; S.foto = null; } }
async function limpar() {
  if (!S.itens.length || !await confirmar('Limpar a lista?', 'As fotos não são apagadas, só saem da lista.', { rotulo: 'Limpar' })) return;
  aplicar(await tentar(() => api('remover', { todos: true })));
  S.item = null; S.foto = null;
}
async function ligarAuto() {
  const r = await tentar(() => api('ligar_auto', {}));
  if (r) { aplicar(r); aviso(`${r.ligadas} foto(s) ligada(s) pelo nome`, { tipo: 'sucesso', tempo: 2400 }); desenharPropriedades(); }
}
async function exportar() {
  if (!S.opcoes.saida) { await escolherSaida(); if (!S.opcoes.saida) return; }
  const r = await tentar(() => api('exportar', {}));
  if (!r) return;
  S._exportando = true;
  aplicar(r);
  if (!r.iniciado) fimExport({ exportadas: 0, pulados: r.pulados, erros: [] });
}
function fimExport(rs) {
  S._exportando = false;
  if (!rs) return;
  const n = rs.exportadas;
  const prob = (rs.pulados || []).length + (rs.erros || []).length;
  aviso(n ? `${n} minifaces gravadas` : 'Nenhuma miniface gravada', {
    tipo: n ? 'sucesso' : 'aviso', tempo: 7000, detalhe: prob ? `${prob} foto(s) puladas — veja a lista` : S.opcoes.saida,
    acao: prob ? { rotulo: 'Ver', fn: () => verPulados(rs) } : { rotulo: 'Abrir pasta', fn: () => tentar(() => api('abrir', {})) },
  });
  atualizar();
}
function verPulados(rs) {
  const linhas = [...(rs.pulados || []).map(([n, m]) => [n, m, 'amarela']), ...(rs.erros || []).map(([n, m]) => [n, m, 'vermelha'])];
  modal({ titulo: 'Fotos que não foram gravadas', largo: true, corpo: el('div', { class: 'lista', style: { maxHeight: '55vh' } },
    ...linhas.map(([n, m, c]) => el('div', { class: 'problema' }, el('span', { class: `etiqueta ${c}` }, c === 'vermelha' ? 'erro' : 'pulada'), el('span', { class: 'cresce' }, n), el('span', { class: 'mudo' }, m)))),
  botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

// ---------------------------------------------------------------- arrastar e soltar
function prepararSoltar() {
  let n = 0;
  const camada = $('#camada-soltar');
  const temArquivo = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  window.addEventListener('dragenter', (e) => { if (!temArquivo(e)) return; e.preventDefault(); n++; camada.hidden = false; });
  window.addEventListener('dragleave', () => { n = Math.max(0, n - 1); if (!n) camada.hidden = true; });
  window.addEventListener('dragover', (e) => { if (temArquivo(e)) e.preventDefault(); });
  window.addEventListener('drop', async (e) => {
    if (!temArquivo(e)) return;
    e.preventDefault();
    n = 0; camada.hidden = true;
    const arqs = [...e.dataTransfer.files].filter((f) => /\.(png|jpe?g|webp|bmp|tiff?)$/i.test(f.name));
    if (!arqs.length) { aviso('Solte imagens (.png, .jpg, .webp…).', { tipo: 'aviso' }); return; }
    const fim = carregando(`Recebendo ${arqs.length} foto(s)…`);
    try {
      const arquivos = [];
      for (const f of arqs) arquivos.push({ nome: f.name, dados: await lerArquivoBase64(f) });
      const r = await api('receber', { arquivos });
      aplicar(r);
      aviso(`${r.novos} foto(s) adicionada(s) — analisando`, { tipo: 'sucesso', tempo: 2500 });
    } catch (err) { aviso(err.message, { tipo: 'erro' }); } finally { fim(); }
  });
}

// ---------------------------------------------------------------- menus
function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { rotulo: 'Adicionar fotos…', icone: 'arquivoMais', atalho: 'Ctrl+O', fn: () => adicionar('arquivos') },
      { rotulo: 'Adicionar pasta…', icone: 'pastaMais', atalho: 'Ctrl+Shift+O', fn: () => adicionar('pasta') },
      '-',
      { rotulo: 'Escolher pasta de saída…', icone: 'pasta', fn: escolherSaida },
      { rotulo: 'Abrir pasta de saída', icone: 'externo', desabilitado: !S.opcoes.saida, fn: () => tentar(() => api('abrir', {})) },
      { rotulo: 'Exportar', icone: 'upload', atalho: 'Ctrl+E', desabilitado: S.export.rodando, fn: exportar },
      '-',
      { rotulo: 'Limpar a lista', icone: 'x', desabilitado: !S.itens.length, fn: limpar },
    ]],
    ['Jogadores', () => [
      { rotulo: 'Escolher o time…', icone: 'trofeu', desabilitado: !S.banco, fn: () => escolherTime() },
      { rotulo: 'Ligar pelo nome do arquivo', icone: 'ligar', desabilitado: !S.time, fn: ligarAuto },
      { rotulo: 'Desligar a foto selecionada', icone: 'x', desabilitado: !sel()?.jogador, fn: () => ligar(S.sel, '') },
    ]],
    ['Editar', () => [
      { rotulo: 'Mover o quadro', icone: 'mover', marcado: S.modo === 'mover', atalho: 'V', fn: () => definirModo('mover') },
      { rotulo: 'Marcar o rosto', icone: 'alvo', marcado: S.modo === 'rosto', atalho: 'R', fn: () => definirModo('rosto') },
      { rotulo: 'Pincel: manter', icone: 'pincelMais', marcado: S.modo === 'manter', atalho: 'B', fn: () => definirModo('manter') },
      { rotulo: 'Pincel: apagar', icone: 'borracha', marcado: S.modo === 'apagar', atalho: 'E', fn: () => definirModo('apagar') },
      { rotulo: 'Desfazer o último traço', icone: 'desfazer', atalho: 'Ctrl+Z', desabilitado: !(S.item?.params.tracos || []).length, fn: desfazerTraco },
      '-',
      { rotulo: 'Restaurar ajustes da foto', icone: 'restaurar', desabilitado: !S.item, fn: () => restaurar(S.sel) },
    ]],
    ['Exibir', () => [
      { rotulo: 'Fundo xadrez', marcado: S.fundoVista === 'xadrez', fn: () => fundoVista('xadrez') },
      { rotulo: 'Fundo escuro', marcado: S.fundoVista === 'escuro', fn: () => fundoVista('escuro') },
      { rotulo: 'Fundo claro', marcado: S.fundoVista === 'claro', fn: () => fundoVista('claro') },
      '-',
      { rotulo: 'Comparar com a miniface do jogo', marcado: S.ref, atalho: 'C', fn: alternarRef },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Atalhos do teclado', icone: 'teclado', atalho: 'F1', fn: atalhos },
      { rotulo: 'Sobre o Criador de Minifaces', icone: 'info', fn: sobre },
    ]],
  ]);
}
function fundoVista(f) {
  S.fundoVista = f;
  $('#quadro-mini').className = 'quadro-mini ' + f;
  document.querySelectorAll('#seg-fundo button').forEach((b) => b.classList.toggle('ativo', b.dataset.fundo === f));
}
async function alternarRef() {
  if (!S.ref) {   // a miniface de referência é do jogo e não vem no pacote leve
    const r = await importarReferencias();
    if (!r || !r.ok) return;
    if ((r.importados || []).length) $('#img-ref').src = `referencia_p158023.png?t=${Date.now()}`;
  }
  S.ref = !S.ref;
  $('#img-ref').hidden = !S.ref;
  $('#btn-referencia').classList.toggle('ativo', S.ref);
}
async function desfazerTraco() {
  const t = S.item?.params.tracos || [];
  if (t.length) await enviar({ tracos: t.slice(0, -1) });
}
function atalhos() {
  const t = el('div', { class: 'tabela-atalhos' });
  for (const [g, itens] of [['Fotos', [['Adicionar fotos', 'Ctrl+O'], ['Adicionar pasta', 'Ctrl+Shift+O'], ['Foto anterior/próxima', '↑ / ↓'], ['Exportar', 'Ctrl+E']]],
    ['Ferramentas', [['Mover o quadro', 'V'], ['Marcar o rosto', 'R'], ['Pincel manter', 'B'], ['Pincel apagar', 'E'], ['Desfazer traço', 'Ctrl+Z'], ['Pincel menor/maior', '[ / ]']]],
    ['Prévia', [['Comparar com a do jogo', 'C'], ['Zoom', 'roda do mouse na foto']]]]) {
    t.append(el('h4', {}, g));
    for (const [rot, k] of itens) t.append(el('div', {}, el('span', {}, rot), el('span', { html: `<kbd>${esc(k)}</kbd>` })));
  }
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
function sobre() {
  dialogoSobre({ nome: 'Criador de Minifaces', versao: S.versao, html: `
    Transforma fotos de jogadores em minifaces do jogo (<i>p&lt;ID&gt;.png</i>, 180×180 com fundo transparente).<br><br>
    <b>Fundo:</b> usa a transparência da foto quando existe (limpando o halo); senão separa o jogador do fundo com o GrabCut do OpenCV,
    guiado pelo rosto e pela cor do fundo. O pincel verde/vermelho corrige o que sobrar.<br>
    <b>Enquadramento:</b> o rosto é encontrado pelo detector do OpenCV (de frente, de perfil ou pela silhueta) e posto no mesmo lugar e
    tamanho das minifaces originais (medido na p158023 do jogo). O botão de comparar sobrepõe uma miniface do jogo.<br>
    <b>Jogadores:</b> com o banco importado no Super Tool, escolha o time e cada foto é ligada ao jogador pelo nome do arquivo.<br><br>
    <b>1.0</b> — primeira versão.` });
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  const digitando = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName) && document.activeElement.type !== 'range';
  const ctrl = e.ctrlKey || e.metaKey;
  const k = e.key.toLowerCase();
  if (ctrl && k === 'o') { e.preventDefault(); adicionar(e.shiftKey ? 'pasta' : 'arquivos'); return; }
  if (ctrl && k === 'e') { e.preventDefault(); exportar(); return; }
  if (e.key === 'F1') { e.preventDefault(); atalhos(); return; }
  if (digitando) return;
  if (ctrl && k === 'z') { e.preventDefault(); desfazerTraco(); return; }
  if (k === 'v') definirModo('mover');
  else if (k === 'r') definirModo('rosto');
  else if (k === 'b') definirModo('manter');
  else if (k === 'e') definirModo('apagar');
  else if (k === 'c') alternarRef();
  else if (e.key === '[' || e.key === ']') { const r = $('#raio'); r.value = +r.value + (e.key === ']' ? 3 : -3); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const its = filtrados();
    const i = its.findIndex((x) => x.id === S.sel);
    const j = Math.max(0, Math.min(its.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    if (its[j]) { e.preventDefault(); selecionar(its[j].id); document.querySelector(`#lista .foto[data-id="${its[j].id}"]`)?.scrollIntoView({ block: 'nearest' }); }
  } else if (e.key === 'Delete' && S.sel !== null) { e.preventDefault(); remover([S.sel]); }
});

// ---------------------------------------------------------------- início
async function iniciar() {
  $('#btn-add-arq').innerHTML = icone('arquivoMais', 14);
  $('#btn-add-pasta').innerHTML = icone('pastaMais', 14);
  $('#btn-limpar').innerHTML = icone('apagar', 14);
  $('#busca-ic').innerHTML = icone('busca', 14);
  $('#soltar-ic').innerHTML = icone('miniface', 64);
  $('#btn-vazio-arq').innerHTML = icone('arquivoMais', 15) + 'Adicionar fotos…';
  $('#btn-vazio-pasta').innerHTML = icone('pastaMais', 15) + 'Adicionar pasta…';
  $('#btn-referencia').innerHTML = icone('camadas', 16);
  $('#btn-desfazer-traco').innerHTML = icone('desfazer', 15);
  const ics = { mover: 'mover', rosto: 'alvo', manter: 'pincelMais', apagar: 'borracha' };
  document.querySelectorAll('#ferramentas [data-modo]').forEach((b) => { b.innerHTML = icone(ics[b.dataset.modo], 16); b.onclick = () => definirModo(b.dataset.modo); });
  $('#btn-add-arq').onclick = () => adicionar('arquivos');
  $('#btn-add-pasta').onclick = () => adicionar('pasta');
  $('#btn-vazio-arq').onclick = () => adicionar('arquivos');
  $('#btn-vazio-pasta').onclick = () => adicionar('pasta');
  $('#btn-limpar').onclick = limpar;
  $('#btn-exportar').onclick = exportar;
  $('#btn-referencia').onclick = alternarRef;
  $('#btn-desfazer-traco').onclick = desfazerTraco;
  document.querySelectorAll('#seg-fundo button').forEach((b) => { b.onclick = () => fundoVista(b.dataset.fundo); });
  $('#busca').addEventListener('input', () => { desenharLista(); desenharVizinhos(); });
  $('#filtro').addEventListener('change', () => { desenharLista(); desenharVizinhos(); });
  divisorArrastavel($('#div-esq'), '--esq', { min: 230, max: 520 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 270, max: 520, lado: 'dir' });
  prepararCanvas();
  prepararSoltar();
  fundoVista('xadrez');
  definirModo('mover');
  menus();
  const r = await api('inicio');
  S.versao = r.versao;
  $('#versao').textContent = r.versao;
  S.ultimoFimExport = r.export && r.export.fim ? r.export.fim : null;
  aplicar(r);
  if (S.sel !== null) carregarItem(S.sel);
  if (S.motor.msg === 'verificando…') {
    const t = setInterval(async () => {
      const e = await api('estado').catch(() => null);
      if (e && e.motor.msg !== 'verificando…') { clearInterval(t); aplicar(e); }
    }, 800);
  }
  // o banco pode ser importado no Super Tool com a ferramenta aberta
  setInterval(async () => {
    if (S.polling) return;
    const e = await api('estado').catch(() => null);
    if (e && JSON.stringify(e.banco) !== JSON.stringify(S.banco)) { S.times = null; S.elencoTime = null; aplicar(e); }
    // componentes instalados por outra janela (página Componentes do Super Tool): o motor sobe sozinho
    else if (e && (e.motor.ok !== S.motor.ok || e.motor.instalar !== S.motor.instalar)) aplicar(e);
    // fotos mandadas pelo Criador de Ligas e Times
    else if (e && (e.do_criador || e.itens.length !== S.itens.length)) { aplicar(e); if (e.do_criador && S.sel !== null) carregarItem(S.sel); }
  }, 5000);
  // ao voltar para esta ferramenta (o Criador de Ligas e Times pode ter mandado fotos)
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !S.polling) atualizar(); });
  window.addEventListener('focus', () => { if (!S.polling) atualizar(); });
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
