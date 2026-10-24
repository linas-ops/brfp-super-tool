// Editor da textura (2D): a cor da peça (vinda do motor) com os logos, o escudo e a marca por cima. Arrastar move,
// o canto redimensiona (proporção mantida), a alça de cima gira (Shift: de 15 em 15°). Roda do mouse aproxima,
// botão do meio (ou espaço + arrastar) move a vista.

const COSTAS = { u0: 0.36, u1: 0.64 };

export function rotacaoAuto(peca, lg) {
  if (peca !== 'jersey' || lg.rot_auto === false) return false;
  return lg.v < 0.5 && lg.u >= COSTAS.u0 - 0.02 && lg.u <= COSTAS.u1 + 0.02;
}

export class Editor2D {
  constructor(canvas, { aoSelecionar, aoMudar, aoConfirmar, urlDe }) {
    this.c = canvas;
    this.ctx = canvas.getContext('2d');
    this.cb = { aoSelecionar, aoMudar, aoConfirmar, urlDe };
    this.base = null;            // HTMLImageElement da textura de cor
    this.peca = 'jersey';
    this.itens = [];             // [{id, tipo: 'logo'|'escudo'|'marca', obj}]
    this.sel = null;
    this.imgs = new Map();       // url -> Image
    this.zoom = 1; this.pan = [0, 0];
    this.molde = null; this.verMolde = false;
    this.composto = document.createElement('canvas');
    this.arrasto = null;
    this.espaco = false;
    this._pedido = false;
    new ResizeObserver(() => this.desenhar()).observe(canvas.parentElement);
    canvas.addEventListener('pointerdown', (e) => this._baixo(e));
    canvas.addEventListener('pointermove', (e) => this._mover(e));
    canvas.addEventListener('pointerup', (e) => this._cima(e));
    canvas.addEventListener('wheel', (e) => this._roda(e), { passive: false });
    canvas.addEventListener('dblclick', () => this.enquadrar());
    window.addEventListener('keydown', (e) => { if (e.code === 'Space' && document.activeElement === canvas) { this.espaco = true; e.preventDefault(); } });
    window.addEventListener('keyup', (e) => { if (e.code === 'Space') this.espaco = false; });
  }

  // ---------------------------------------------------------------- dados
  definir({ peca, base, itens }) {
    const trocouPeca = peca !== this.peca;
    this.peca = peca;
    if (base) this.base = base;
    this.itens = itens;
    if (this.sel && !this.itens.some((i) => i.id === this.sel)) this.sel = null;
    if (trocouPeca) this.enquadrar(); else this.desenhar();
  }

  imagem(url) {
    if (!url) return null;
    let im = this.imgs.get(url);
    if (!im) {
      im = new Image();
      im.onload = () => this.desenhar();
      im.src = url;
      this.imgs.set(url, im);
    }
    return im.complete && im.naturalWidth ? im : null;
  }

  // caixa de um item em pixels da textura: centro, largura, altura, rotação (graus), espelhos
  caixa(it) {
    const W = this.base?.naturalWidth || 1, H = this.base?.naturalHeight || 1;
    if (it.tipo === 'logo') {
      const o = it.obj;
      return { cx: o.u * W, cy: o.v * H, w: o.largura * W, h: o.altura * H, rot: (o.rot || 0) + (rotacaoAuto(this.peca, o) ? 180 : 0), fx: 1, fy: 1 };
    }
    const b = it.obj.caixa;
    return { cx: (b.x0 + b.x1) / 2 * W, cy: (b.y0 + b.y1) / 2 * H, w: Math.abs(b.x1 - b.x0) * W, h: Math.abs(b.y1 - b.y0) * H, rot: 0,
      fx: b.x1 >= b.x0 ? 1 : -1, fy: b.y1 >= b.y0 ? 1 : -1 };
  }

  // ---------------------------------------------------------------- composição (também vira a textura do 3D)
  compor() {
    const b = this.base;
    if (!b || !b.naturalWidth) return null;
    const cv = this.composto;
    if (cv.width !== b.naturalWidth || cv.height !== b.naturalHeight) { cv.width = b.naturalWidth; cv.height = b.naturalHeight; }
    const g = cv.getContext('2d');
    g.clearRect(0, 0, cv.width, cv.height);
    g.drawImage(b, 0, 0);
    for (const it of this.itens) {
      const o = it.obj;
      if (it.tipo === 'hotspot') continue;             // número e nome: o jogo escreve; aqui só a caixa (por cima)
      if (it.tipo === 'logo' && o.visivel === false) continue;
      const im = this.imagem(this.cb.urlDe(o.arquivo));
      if (!im) continue;
      const k = this.caixa(it);
      g.save();
      g.globalAlpha = it.tipo === 'logo' ? (o.opacidade ?? 1) : 1;
      g.translate(k.cx, k.cy);
      g.rotate((k.rot * Math.PI) / 180);
      g.scale(k.fx, k.fy);
      if (it.tipo === 'logo') g.drawImage(im, -k.w / 2, -k.h / 2, k.w, k.h);
      else {
        // escudo/marca: o jogo estica o quadrado 256×256 dentro da caixa; aqui o logo vai centralizado como no quadrado
        const lado = Math.max(im.naturalWidth, im.naturalHeight) / 0.88;
        const sx = k.w / lado, sy = k.h / lado;
        g.drawImage(im, -im.naturalWidth * sx / 2, -im.naturalHeight * sy / 2, im.naturalWidth * sx, im.naturalHeight * sy);
      }
      g.restore();
    }
    return cv;
  }

  // ---------------------------------------------------------------- vista
  _dims() {
    const p = this.c.parentElement;
    return [Math.max(1, p.clientWidth), Math.max(1, p.clientHeight)];
  }

  _escala() {
    const [w, h] = this._dims();
    const W = this.base?.naturalWidth || 1, H = this.base?.naturalHeight || 1;
    const fit = Math.min((w - 40) / W, (h - 100) / H);
    return fit * this.zoom;
  }

  // textura -> tela
  _tela(x, y) {
    const [w, h] = this._dims();
    const s = this._escala();
    const W = this.base?.naturalWidth || 1, H = this.base?.naturalHeight || 1;
    return [w / 2 + this.pan[0] + (x - W / 2) * s, h / 2 + 10 + this.pan[1] + (y - H / 2) * s];
  }

  _textura(px, py) {
    const [w, h] = this._dims();
    const s = this._escala();
    const W = this.base?.naturalWidth || 1, H = this.base?.naturalHeight || 1;
    return [(px - w / 2 - this.pan[0]) / s + W / 2, (py - h / 2 - 10 - this.pan[1]) / s + H / 2];
  }

  enquadrar() { this.zoom = 1; this.pan = [0, 0]; this.desenhar(); }

  desenhar() {
    if (this._pedido) return;
    this._pedido = true;
    requestAnimationFrame(() => { this._pedido = false; this._desenhar(); });
  }

  _desenhar() {
    const [w, h] = this._dims();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (this.c.width !== Math.round(w * dpr) || this.c.height !== Math.round(h * dpr)) { this.c.width = Math.round(w * dpr); this.c.height = Math.round(h * dpr); }
    const g = this.ctx;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const cv = this.compor();
    if (!cv) return;
    const s = this._escala();
    const [x0, y0] = this._tela(0, 0);
    g.save();
    g.shadowColor = 'rgba(0,0,0,.5)'; g.shadowBlur = 18;
    g.fillStyle = '#111'; g.fillRect(x0, y0, cv.width * s, cv.height * s);
    g.restore();
    g.imageSmoothingQuality = 'high';
    g.drawImage(cv, x0, y0, cv.width * s, cv.height * s);
    if (this.verMolde && this.molde) this._desenharMolde(g, cv.width, cv.height);
    // contornos do escudo/marca (sempre) e do selecionado
    for (const it of this.itens) {
      const sel = it.id === this.sel;
      if (it.tipo === 'hotspot') this._amostra(g, it);
      if (!sel && it.tipo === 'logo') continue;
      this._contorno(g, it, sel);
    }
  }

  _desenharMolde(g, W, H) {
    const m = this.molde;
    g.save();
    g.lineWidth = 1.2;
    g.setLineDash([5, 4]);
    g.strokeStyle = 'rgba(255, 230, 0, .85)';
    for (const pol of Object.values(m.regioes || {})) {
      g.beginPath();
      pol.forEach(([u, v], i) => { const [x, y] = this._tela(u * W, v * H); if (i) g.lineTo(x, y); else g.moveTo(x, y); });
      g.closePath(); g.stroke();
    }
    if (m.gola) {
      for (const [ru, rv] of [[m.gola.ru, m.gola.rv], [m.gola.ru_in, m.gola.rv_in]]) {
        const [cx, cy] = this._tela(m.gola.cu * W, m.gola.cv * H);
        const s = this._escala();
        g.beginPath(); g.ellipse(cx, cy, ru * W * s, rv * H * s, 0, 0, Math.PI * 2); g.stroke();
      }
    }
    g.strokeStyle = 'rgba(80, 200, 255, .85)';
    for (const [nome, b] of [['frente', m.frente], ['costas', m.costas]]) {
      if (!b) continue;
      const [ax, ay] = this._tela(b.u0 * W, b.v0 * H), [bx, by] = this._tela(b.u1 * W, b.v1 * H);
      g.strokeRect(ax, ay, bx - ax, by - ay);
      g.setLineDash([]);
      g.fillStyle = 'rgba(80, 200, 255, .95)'; g.font = '11px system-ui';
      g.fillText(nome === 'frente' ? 'frente' : 'costas (de cabeça para baixo)', ax + 4, nome === 'frente' ? by - 6 : ay + 14);
      g.setLineDash([5, 4]);
    }
    g.restore();
  }

  _cantos(k) {
    const r = (k.rot * Math.PI) / 180, c = Math.cos(r), s = Math.sin(r);
    return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => {
      const x = (a * k.w) / 2, y = (b * k.h) / 2;
      return [k.cx + x * c - y * s, k.cy + x * s + y * c];
    });
  }

  _contorno(g, it, sel) {
    const k = this.caixa(it);
    const pts = this._cantos(k).map(([x, y]) => this._tela(x, y));
    g.save();
    g.lineWidth = sel ? 1.6 : 1;
    g.setLineDash(sel ? [] : [4, 3]);
    g.strokeStyle = sel ? '#4c8dff' : it.tipo === 'escudo' ? 'rgba(255,120,120,.9)' : it.tipo === 'hotspot' ? 'rgba(90,220,255,.9)' : 'rgba(255,190,90,.9)';
    g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.closePath(); g.stroke();
    if (!sel && it.tipo !== 'logo') {
      g.fillStyle = g.strokeStyle; g.font = '11px system-ui';
      const nome = it.tipo === 'escudo' ? 'escudo' : it.tipo === 'hotspot' ? it.rotulo.toLowerCase() : 'marca';
      const [lx, ly] = pts.reduce((a, b) => (b[1] < a[1] || (b[1] === a[1] && b[0] < a[0]) ? b : a));
      g.fillText(nome, lx, ly - 4);
    }
    if (sel) {
      g.setLineDash([]);
      g.fillStyle = '#fff';
      for (const [x, y] of pts) { g.beginPath(); g.rect(x - 4, y - 4, 8, 8); g.fill(); g.stroke(); }
      if (it.tipo === 'logo') {
        const [hx, hy] = this._alcaGiro(k);
        const [tx, ty] = [(pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2];
        g.beginPath(); g.moveTo(tx, ty); g.lineTo(hx, hy); g.stroke();
        g.beginPath(); g.arc(hx, hy, 5, 0, Math.PI * 2); g.fill(); g.stroke();
      }
    }
    g.restore();
  }

  // número/nome de exemplo dentro da caixa do hotspot (de cabeça para baixo quando a caixa está invertida)
  _amostra(g, it) {
    const k = this.caixa(it);
    const [cx, cy] = this._tela(k.cx, k.cy);
    const s = this._escala();
    const w = k.w * s, h = k.h * s;
    if (w < 6 || h < 6) return;
    g.save();
    g.translate(cx, cy);
    if (k.fx < 0 && k.fy < 0) g.rotate(Math.PI);
    else g.scale(k.fx, k.fy);
    g.font = `800 ${Math.max(6, h * 0.86)}px system-ui, sans-serif`;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    const larg = g.measureText(it.amostra).width || 1;
    if (larg > w) g.scale(w / larg, 1);
    g.fillStyle = 'rgba(255,255,255,.55)';
    g.strokeStyle = 'rgba(0,0,0,.45)';
    g.lineWidth = Math.max(1, h * 0.04);
    g.strokeText(it.amostra, 0, h * 0.04);
    g.fillText(it.amostra, 0, h * 0.04);
    g.restore();
  }

  _alcaGiro(k) {
    const pts = this._cantos(k).map(([x, y]) => this._tela(x, y));
    const [tx, ty] = [(pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2];
    const [cx, cy] = this._tela(k.cx, k.cy);
    const d = Math.hypot(tx - cx, ty - cy) || 1;
    return [tx + ((tx - cx) / d) * 22, ty + ((ty - cy) / d) * 22];
  }

  // ---------------------------------------------------------------- interação
  _local(e) { const r = this.c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }

  _dentro(it, x, y) {
    const k = this.caixa(it);
    const r = (-k.rot * Math.PI) / 180;
    const dx = x - k.cx, dy = y - k.cy;
    const lx = dx * Math.cos(r) - dy * Math.sin(r), ly = dx * Math.sin(r) + dy * Math.cos(r);
    return Math.abs(lx) <= k.w / 2 && Math.abs(ly) <= k.h / 2;
  }

  _alvo(px, py) {
    const selIt = this.itens.find((i) => i.id === this.sel);
    if (selIt) {
      const k = this.caixa(selIt);
      if (selIt.tipo === 'logo') {
        const [hx, hy] = this._alcaGiro(k);
        if (Math.hypot(px - hx, py - hy) < 9) return { it: selIt, modo: 'girar' };
      }
      const pts = this._cantos(k).map(([x, y]) => this._tela(x, y));
      if (pts.some(([x, y]) => Math.abs(px - x) < 7 && Math.abs(py - y) < 7)) return { it: selIt, modo: 'redim' };
    }
    const [tx, ty] = this._textura(px, py);
    for (let i = this.itens.length - 1; i >= 0; i--) {
      const it = this.itens[i];
      if (it.tipo === 'logo' && it.obj.visivel === false) continue;
      if (this._dentro(it, tx, ty)) return { it, modo: 'mover' };
    }
    return null;
  }

  _baixo(e) {
    this.c.focus();
    const [px, py] = this._local(e);
    if (e.button === 1 || e.button === 2 || this.espaco) {
      this.arrasto = { modo: 'pan', x: px, y: py, pan: [...this.pan] };
      this.c.setPointerCapture(e.pointerId);
      return;
    }
    const a = this._alvo(px, py);
    if (!a) {
      if (this.sel) { this.sel = null; this.cb.aoSelecionar(null); this.desenhar(); }
      this.arrasto = { modo: 'pan', x: px, y: py, pan: [...this.pan] };
      this.c.setPointerCapture(e.pointerId);
      return;
    }
    if (this.sel !== a.it.id) { this.sel = a.it.id; this.cb.aoSelecionar(a.it.id); }
    const k = this.caixa(a.it);
    this.arrasto = { modo: a.modo, it: a.it, x: px, y: py, k, ini: JSON.parse(JSON.stringify(a.it.obj)), mexeu: false };
    this.c.setPointerCapture(e.pointerId);
    this.desenhar();
  }

  _mover(e) {
    const [px, py] = this._local(e);
    const a = this.arrasto;
    if (!a) {
      const t = this._alvo(px, py);
      this.c.className = t ? t.modo : '';
      return;
    }
    if (a.modo === 'pan') { this.pan = [a.pan[0] + px - a.x, a.pan[1] + py - a.y]; this.desenhar(); return; }
    const W = this.base.naturalWidth, H = this.base.naturalHeight;
    const s = this._escala();
    const o = a.it.obj;
    a.mexeu = true;
    if (a.modo === 'mover') {
      const du = (px - a.x) / s / W, dv = (py - a.y) / s / H;
      if (a.it.tipo === 'logo') { o.u = a.ini.u + du; o.v = a.ini.v + dv; } else {
        const b = a.ini.caixa;
        o.caixa = { x0: b.x0 + du, x1: b.x1 + du, y0: b.y0 + dv, y1: b.y1 + dv };
      }
    } else if (a.modo === 'redim') {
      const [cx, cy] = this._tela(a.k.cx, a.k.cy);
      const d0 = Math.hypot(a.x - cx, a.y - cy) || 1;
      const f = Math.max(0.05, Math.hypot(px - cx, py - cy) / d0);
      if (a.it.tipo === 'logo') { o.largura = a.ini.largura * f; o.altura = a.ini.altura * f; } else {
        const b = a.ini.caixa, mx = (b.x0 + b.x1) / 2, my = (b.y0 + b.y1) / 2;
        o.caixa = { x0: mx + (b.x0 - mx) * f, x1: mx + (b.x1 - mx) * f, y0: my + (b.y0 - my) * f, y1: my + (b.y1 - my) * f };
      }
    } else if (a.modo === 'girar') {
      const [cx, cy] = this._tela(a.k.cx, a.k.cy);
      const ang0 = Math.atan2(a.y - cy, a.x - cx), ang = Math.atan2(py - cy, px - cx);
      let r = (a.ini.rot || 0) + ((ang - ang0) * 180) / Math.PI;
      if (e.shiftKey) r = Math.round(r / 15) * 15;
      o.rot = ((r % 360) + 360) % 360;
    }
    this.cb.aoMudar(a.it);
    this.desenhar();
  }

  _cima(e) {
    const a = this.arrasto;
    this.arrasto = null;
    try { this.c.releasePointerCapture(e.pointerId); } catch { /* já solto */ }
    if (a && a.it && a.mexeu) this.cb.aoConfirmar(a.it);
  }

  _roda(e) {
    e.preventDefault();
    const [px, py] = this._local(e);
    const [tx, ty] = this._textura(px, py);
    this.zoom = Math.max(0.3, Math.min(12, this.zoom * Math.exp(-e.deltaY * 0.0015)));
    const [nx, ny] = this._tela(tx, ty);
    this.pan = [this.pan[0] + px - nx, this.pan[1] + py - ny];
    this.desenhar();
  }

  // empurrar o selecionado com as setas (em pixels da textura)
  empurrar(dx, dy) {
    const it = this.itens.find((i) => i.id === this.sel);
    if (!it) return false;
    const W = this.base.naturalWidth, H = this.base.naturalHeight;
    if (it.tipo === 'logo') { it.obj.u += dx / W; it.obj.v += dy / H; } else {
      const b = it.obj.caixa;
      it.obj.caixa = { x0: b.x0 + dx / W, x1: b.x1 + dx / W, y0: b.y0 + dy / H, y1: b.y1 + dy / H };
    }
    this.desenhar();
    return true;
  }
}
