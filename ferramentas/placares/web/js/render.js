// Desenho do overlay em WebGL2: formas (triângulos com textura ou cor sólida), linhas, textos e máscaras
// (recortes do APT, com stencil). Também faz o "clique para selecionar" e calcula os limites dos elementos.
import { M, nomesAcima, textoExemplo } from './cena.js';

const VS = `#version 300 es
in vec2 aPos;
uniform mat3 uMvp;     // local -> clip
uniform mat3 uUV;      // local -> uv (0..1)
out vec2 vUV;
out vec2 vPalco;
uniform mat3 uPalco;   // local -> palco (fundo procedural)
void main() {
  vec3 p = uMvp * vec3(aPos, 1.0);
  gl_Position = vec4(p.xy, 0.0, 1.0);
  vUV = (uUV * vec3(aPos, 1.0)).xy;
  vPalco = (uPalco * vec3(aPos, 1.0)).xy;
}`;

const FS = `#version 300 es
precision highp float;
in vec2 vUV;
in vec2 vPalco;
uniform sampler2D uTex;
uniform int uModo;      // 0 cor, 1 textura, 2 xadrez, 3 campo
uniform vec4 uCor;
uniform vec4 uMult;
uniform vec4 uSoma;
out vec4 cor;
void main() {
  vec4 c;
  if (uModo == 1) c = texture(uTex, vUV) * uCor;
  else if (uModo == 2) {
    float q = mod(floor(vPalco.x / 24.0) + floor(vPalco.y / 24.0), 2.0);
    c = vec4(mix(vec3(0.16), vec3(0.22), q), 1.0);
  } else if (uModo == 3) {
    float faixa = mod(floor(vPalco.x / 96.0), 2.0);
    vec3 g = mix(vec3(0.16, 0.42, 0.20), vec3(0.19, 0.47, 0.23), faixa);
    float y = vPalco.y;
    float linha = step(abs(vPalco.x - 960.0), 2.0) + step(abs(length(vPalco - vec2(960.0, 640.0)) - 150.0), 2.0)
      + step(abs(y - 300.0), 2.0) * step(abs(vPalco.x - 960.0), 820.0);
    float luz = 1.0 - smoothstep(0.0, 1300.0, length(vPalco - vec2(960.0, 300.0))) * 0.35;
    c = vec4(mix(g * luz, vec3(0.85), clamp(linha, 0.0, 1.0) * 0.6), 1.0);
  }
  else c = uCor;
  c = c * uMult + uSoma;
  if (c.a <= 0.001) discard;
  cor = c;
}`;

export class Render {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', { stencil: true, antialias: true, premultipliedAlpha: false, alpha: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error('Este navegador não tem WebGL2.');
    this.gl = gl;
    this.prog = this._programa(VS, FS);
    this.loc = {};
    for (const n of ['uMvp', 'uUV', 'uPalco', 'uTex', 'uModo', 'uCor', 'uMult', 'uSoma']) this.loc[n] = gl.getUniformLocation(this.prog, n);
    this.aPos = gl.getAttribLocation(this.prog, 'aPos');
    this.vao = gl.createVertexArray();
    this.buffers = new Map();     // chave -> {buf, n}
    this.texGL = new Map();       // canvas -> WebGLTexture
    this.textos = new Map();      // chave -> canvas
    this.vista = { s: 0.5, ox: 0, oy: 0 };
    this.palco = { w: 1920, h: 1080 };
    this.fundo = 'campo';
    this.imagemFundo = null;
    this.raiz = null;
    this.alvos = [];              // para o clique: {no, mundo, tris|ret, bbox}
    this.mostrarTextos = true;
    this.usarMascaras = false;     // o jogo anima as máscaras; parado, elas escondem textos e barras
    this.ocultos = new Set();     // ids ocultos só no editor
    this.aoPrecisarDesenhar = null;
    this.quad = this._buffer('quad', new Float32Array([0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1]));
  }

  _programa(vs, fs) {
    const gl = this.gl;
    const sh = (t, src) => {
      const s = gl.createShader(t);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, sh(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  _buffer(chave, dados) {
    let b = this.buffers.get(chave);
    if (b) return b;
    const gl = this.gl;
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, dados, gl.STATIC_DRAW);
    b = { buf, n: dados.length / 2 };
    this.buffers.set(chave, b);
    return b;
  }

  _texturaDeCanvas(cv, versao = 0) {
    const gl = this.gl;
    let t = this.texGL.get(cv);
    if (t && t.versao === versao) return t.tex;
    if (!t) { t = { tex: gl.createTexture(), versao: -1 }; this.texGL.set(cv, t); }
    gl.bindTexture(gl.TEXTURE_2D, t.tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, cv);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    t.versao = versao;
    return t.tex;
  }

  limparCaches() {
    const gl = this.gl;
    for (const b of this.buffers.values()) if (b !== this.quad) gl.deleteBuffer(b.buf);
    this.buffers = new Map([['quad', this.quad]]);
    for (const t of this.texGL.values()) gl.deleteTexture(t.tex);
    this.texGL.clear();
    this.textos.clear();
  }

  // ------------------------------------------------------------ vista
  tamanho() {
    const dpr = window.devicePixelRatio || 1;
    const r = this.canvas.getBoundingClientRect();
    const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
    return { w: r.width, h: r.height, dpr };
  }

  enquadrar(bbox = null, margem = 40) {
    const { w, h } = this.tamanho();
    const b = bbox || [0, 0, this.palco.w, this.palco.h];
    const bw = Math.max(1, b[2] - b[0]), bh = Math.max(1, b[3] - b[1]);
    const s = Math.min((w - margem * 2) / bw, (h - margem * 2) / bh, 8);
    this.vista = { s, ox: (w - bw * s) / 2 - b[0] * s, oy: (h - bh * s) / 2 - b[1] * s };
  }

  zoom(fator, cx, cy) {
    const v = this.vista;
    const s = Math.min(40, Math.max(0.05, v.s * fator));
    const k = s / v.s;
    this.vista = { s, ox: cx - (cx - v.ox) * k, oy: cy - (cy - v.oy) * k };
  }

  palcoParaTela(x, y) { const v = this.vista; return [v.ox + v.s * x, v.oy + v.s * y]; }
  telaParaPalco(x, y) { const v = this.vista; return [(x - v.ox) / v.s, (y - v.oy) / v.s]; }

  _mvp(mundo) {
    // palco -> css px -> clip
    const { w, h } = this._tam || this.tamanho();
    const v = this.vista;
    const t = M.mul([v.s, 0, 0, v.s, v.ox, v.oy], mundo);
    const sx = 2 / w, sy = -2 / h;
    const a = t[0] * sx, b = t[1] * sy, c = t[2] * sx, d = t[3] * sy, tx = t[4] * sx - 1, ty = t[5] * sy + 1;
    return new Float32Array([a, b, 0, c, d, 0, tx, ty, 1]);
  }

  // ------------------------------------------------------------ desenho
  definirCena(raiz) { this.raiz = raiz; }

  desenhar() {
    const gl = this.gl;
    const { w, h, dpr } = this._tam = this.tamanho();
    gl.viewport(0, 0, Math.round(w * dpr), Math.round(h * dpr));
    gl.clearColor(0.055, 0.063, 0.075, 1);
    gl.clearStencil(0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.STENCIL_BUFFER_BIT);
    gl.useProgram(this.prog);
    gl.bindVertexArray(this.vao);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.enable(gl.STENCIL_TEST);
    gl.stencilFunc(gl.EQUAL, 0, 0xff);
    gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
    this.nivel = 0;
    this.alvos = [];
    this.pendente = false;
    // fundo do palco
    const palcoM = [this.palco.w, 0, 0, this.palco.h, 0, 0];
    gl.uniform1i(this.loc.uTex, 0);
    if (this.fundo === 'imagem' && this.imagemFundo) {
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this._texturaDeCanvas(this.imagemFundo));
      this._quad(palcoM, 1, [1, 1, 1, 1], [1, 0, 0, 1, 0, 0]);
    } else {
      this._quad(palcoM, { escuro: 0, xadrez: 2, campo: 3 }[this.fundo] ?? 0, [0.11, 0.12, 0.15, 1], null);
    }
    if (this.raiz) this._no(this.raiz, false);
    gl.disable(gl.STENCIL_TEST);
    this._tam = null;
  }

  _quad(mundo, modo, cor, uvMat) {
    const gl = this.gl;
    gl.uniformMatrix3fv(this.loc.uMvp, false, this._mvp(mundo));
    gl.uniformMatrix3fv(this.loc.uPalco, false, new Float32Array([mundo[0], mundo[1], 0, mundo[2], mundo[3], 0, mundo[4], mundo[5], 1]));
    gl.uniformMatrix3fv(this.loc.uUV, false, new Float32Array(uvMat ? [uvMat[0], uvMat[1], 0, uvMat[2], uvMat[3], 0, uvMat[4], uvMat[5], 1] : [1, 0, 0, 0, 1, 0, 0, 0, 1]));
    gl.uniform1i(this.loc.uModo, modo);
    gl.uniform4fv(this.loc.uCor, cor);
    gl.uniform4fv(this.loc.uMult, [1, 1, 1, 1]);
    gl.uniform4fv(this.loc.uSoma, [0, 0, 0, 0]);
    this._vertices(this.quad);
  }

  _vertices(b) {
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, b.buf);
    gl.enableVertexAttribArray(this.aPos);
    gl.vertexAttribPointer(this.aPos, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, b.n);
  }

  // desenha um nó e os filhos, com as máscaras do APT (um filho com "recorte" esconde o que estiver fora dele
  // para os irmãos com profundidade até o valor do recorte)
  _no(no, mascara) {
    if (!mascara && (this.ocultos.has(no.id) || no.animOculto)) return;
    if (!mascara && no.mult[3] <= 0.002 && no.soma[3] <= 0.002 && !no.filhos.length && no.tipo !== 'texto') return;
    if (no.tipo === 'forma') this._forma(no, mascara);
    else if (no.tipo === 'texto') { if (!mascara) this._texto(no); }
    if (no.marcador && !mascara) this._marcador(no);
    const mascaras = [];
    const gl = this.gl;
    for (const f of no.filhos) {
      while (mascaras.length && mascaras[mascaras.length - 1].clip < f.prof) this._tirarMascara(mascaras.pop());
      if (f.recorte >= 0) {
        if (mascara || !this.usarMascaras) continue;
        gl.colorMask(false, false, false, false);
        gl.stencilFunc(gl.EQUAL, this.nivel, 0xff);
        gl.stencilOp(gl.KEEP, gl.KEEP, gl.INCR);
        this._no(f, true);
        gl.colorMask(true, true, true, true);
        this.nivel++;
        gl.stencilFunc(gl.EQUAL, this.nivel, 0xff);
        gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
        mascaras.push({ no: f, clip: f.recorte });
        continue;
      }
      this._no(f, mascara);
    }
    while (mascaras.length) this._tirarMascara(mascaras.pop());
  }

  _tirarMascara(m) {
    const gl = this.gl;
    gl.colorMask(false, false, false, false);
    gl.stencilFunc(gl.EQUAL, this.nivel, 0xff);
    gl.stencilOp(gl.KEEP, gl.KEEP, gl.DECR);
    this._no(m.no, true);
    gl.colorMask(true, true, true, true);
    this.nivel--;
    gl.stencilFunc(gl.EQUAL, this.nivel, 0xff);
    gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP);
  }

  _forma(no, mascara) {
    const gl = this.gl;
    const c = no.charDef;
    const filme = no.filmeConteudo || no.filme;
    const mvp = this._mvp(no.mundo);
    gl.uniformMatrix3fv(this.loc.uMvp, false, mvp);
    gl.uniform4fv(this.loc.uMult, mascara ? [1, 1, 1, 1] : no.mult);
    gl.uniform4fv(this.loc.uSoma, mascara ? [0, 0, 0, 0] : no.soma);
    c.itens.forEach((it, idx) => {
      if (it.k < 0 || !it.v || !it.v.length) return;
      const chave = `${filme.sessao}:${no.char}:${idx}`;
      let b;
      if (it.k === 3) b = this._buffer(chave, linhasParaTriangulos(it.v, Math.max(1, it.larg || 1)));
      else b = this._buffer(chave, new Float32Array(it.v));
      const cor = [it.cor[0] / 255, it.cor[1] / 255, it.cor[2] / 255, it.cor[3] / 255];
      if (!mascara) this.alvos.push({ no, mundo: no.mundo, tris: it.k === 3 ? null : it.v, bbox: c.limites, item: idx });
      if (mascara) {
        gl.uniform1i(this.loc.uModo, 0);
        gl.uniform4fv(this.loc.uCor, [1, 1, 1, 1]);
        this._vertices(b);
        return;
      }
      if ((it.k === 0 || it.k === 1) && it.img !== null && it.img !== undefined) {
        const t = filme.textura(it.img);
        if (!t.canvas) {
          if (!t.erro) { this.pendente = true; t.promessa.then(() => this.aoPrecisarDesenhar && this.aoPrecisarDesenhar()); }
          return;
        }
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, this._texturaDeCanvas(t.canvas, t.versao));
        const [a, bb, cc, d, tx, ty] = it.m;
        const sx = 1 / t.w, sy = 1 / t.h;
        gl.uniformMatrix3fv(this.loc.uUV, false, new Float32Array([a * sx, bb * sy, 0, cc * sx, d * sy, 0, tx * sx, ty * sy, 1]));
        gl.uniform1i(this.loc.uModo, 1);
      } else {
        gl.uniform1i(this.loc.uModo, 0);
      }
      gl.uniform4fv(this.loc.uCor, cor);
      this._vertices(b);
    });
  }

  _texto(no) {
    if (!this.mostrarTextos) return;
    const c = no.charDef;
    const filme = no.filmeConteudo || no.filme;
    const [x0, y0, x1, y1] = c.limites;
    const w = Math.max(1, x1 - x0), h = Math.max(1, y1 - y0);
    const fonte = filme.modelo.chars[c.fonte];
    const nomeFonte = fonte && fonte.t === 'fonte' ? fonte.nome : 'Arial';
    const texto = c.conteudo || textoExemplo(nomesAcima(no));
    if (!texto) return;
    const escala = Math.min(4, Math.max(1, Math.hypot(no.mundo[0], no.mundo[1]) * this.vista.s * 1.5));
    const q = Math.ceil(escala * 2) / 2;
    const chave = [texto, nomeFonte, c.altura, c.cor.join(','), c.alinh, w, h, q, c.multilinha, carregadas.has(nomeFonte)].join('|');
    let cv = this.textos.get(chave);
    if (!cv) {
      cv = desenharTexto(texto, nomeFonte, c, w, h, q);
      this.textos.set(chave, cv);
      if (this.textos.size > 600) this.textos.delete(this.textos.keys().next().value);
      if (!carregadas.has(nomeFonte)) carregarFonte(nomeFonte).then((ok) => { if (ok && this.aoPrecisarDesenhar) this.aoPrecisarDesenhar(); });
    }
    const gl = this.gl;
    const mundo = M.mul(no.mundo, [w, 0, 0, h, x0, y0]);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this._texturaDeCanvas(cv));
    gl.uniformMatrix3fv(this.loc.uMvp, false, this._mvp(mundo));
    gl.uniformMatrix3fv(this.loc.uUV, false, new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]));
    gl.uniform1i(this.loc.uModo, 1);
    gl.uniform4fv(this.loc.uCor, [1, 1, 1, 1]);
    gl.uniform4fv(this.loc.uMult, no.mult);
    gl.uniform4fv(this.loc.uSoma, no.soma);
    this._vertices(this.quad);
    this.alvos.push({ no, mundo: no.mundo, ret: [x0, y0, x1, y1], bbox: [x0, y0, x1, y1] });
  }

  // componente vazio preenchido pelo jogo: texto de exemplo (caixa 200×100) ou escudo (100×100)
  _marcador(no) {
    const gl = this.gl;
    const texto = no.marcador === 'texto';
    if (texto && !this.mostrarTextos) return;
    const w = texto ? 200 : 100, h = texto ? 50 : 100;
    const sx = Math.hypot(no.mundo[0], no.mundo[1]) * w, sy = Math.hypot(no.mundo[2], no.mundo[3]) * h;
    const q = Math.min(4, Math.max(1, this.vista.s * 2));
    let conteudo = texto ? textoExemplo(nomesAcima(no)) : '';
    if (sx < 80) conteudo = { MANDANTE: 'CAS', VISITANTE: 'VIS', JOGADOR: 'NOME', 'TÍTULO': 'TÍT.' }[conteudo] || conteudo;
    // fonte, alinhamento e cor que o código do placar passa ao componente (quando a simulação achou)
    const est = texto && this.estiloTexto ? this.estiloTexto(no) : null;
    const face = est && est.face;
    if (face && !carregadas.has(face)) carregarFonte(face).then((ok) => { if (ok && this.aoPrecisarDesenhar) this.aoPrecisarDesenhar(); });
    const chave = ['marcador', no.marcador, conteudo, Math.round(sx), Math.round(sy), q, face, carregadas.has(face), est && est.alinh, est && est.cor].join('|');
    let cv = this.textos.get(chave);
    if (!cv) {
      cv = document.createElement('canvas');
      cv.width = Math.max(2, Math.ceil(sx * q)); cv.height = Math.max(2, Math.ceil(sy * q));
      const g = cv.getContext('2d');
      g.scale(q, q);
      if (texto) {
        let alt = Math.max(6, Math.min(sy * 0.8, sx * 1.6));
        const fonte = (a) => (face && carregadas.has(face) ? `${a}px "apt_${face}", sans-serif` : `600 ${a}px "Segoe UI", system-ui, sans-serif`);
        g.font = fonte(alt);
        g.fillStyle = est && est.cor ? `rgba(${est.cor[0]},${est.cor[1]},${est.cor[2]},.95)` : 'rgba(255,255,255,.92)';
        // centraliza pela tinta real das letras (as fontes do jogo e as importadas têm métricas fora do padrão)
        g.textBaseline = 'alphabetic';
        let med = g.measureText(conteudo);
        let asc = med.actualBoundingBoxAscent || alt * 0.7, desc = med.actualBoundingBoxDescent || 0;
        if (asc + desc > sy * 0.85) {
          alt *= sy * 0.85 / (asc + desc);
          g.font = fonte(alt);
          med = g.measureText(conteudo);
          asc = med.actualBoundingBoxAscent || alt * 0.7; desc = med.actualBoundingBoxDescent || 0;
        }
        const al = est && est.alinh ? est.alinh : 'center';
        g.textAlign = al;
        g.fillText(conteudo, al === 'left' ? 0 : al === 'right' ? sx : sx / 2, sy / 2 + (asc - desc) / 2, sx);
      } else {
        const r = Math.min(sx, sy) / 2 * 0.86, cx = sx / 2, cy = sy / 2;
        g.fillStyle = 'rgba(255,255,255,.16)';
        g.strokeStyle = 'rgba(255,255,255,.55)';
        g.lineWidth = Math.max(1, r * 0.08);
        g.beginPath();
        g.moveTo(cx - r * .8, cy - r * .85); g.lineTo(cx + r * .8, cy - r * .85); g.lineTo(cx + r * .8, cy);
        g.quadraticCurveTo(cx + r * .7, cy + r * .7, cx, cy + r); g.quadraticCurveTo(cx - r * .7, cy + r * .7, cx - r * .8, cy); g.closePath();
        g.fill(); g.stroke();
      }
      this.textos.set(chave, cv);
    }
    const mundo = M.mul(no.mundo, [w, 0, 0, h, 0, 0]);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this._texturaDeCanvas(cv));
    gl.uniformMatrix3fv(this.loc.uMvp, false, this._mvp(mundo));
    gl.uniformMatrix3fv(this.loc.uUV, false, new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]));
    gl.uniform1i(this.loc.uModo, 1);
    gl.uniform4fv(this.loc.uCor, [1, 1, 1, 1]);
    gl.uniform4fv(this.loc.uMult, no.mult);
    gl.uniform4fv(this.loc.uSoma, no.soma);
    this._vertices(this.quad);
    this.alvos.push({ no, mundo: no.mundo, ret: [0, 0, w, h], bbox: [0, 0, w, h] });
  }

  // ------------------------------------------------------------ seleção
  acertar(xCss, yCss, filtro = null) {
    const [px, py] = this.telaParaPalco(xCss, yCss);
    for (let i = this.alvos.length - 1; i >= 0; i--) {
      const a = this.alvos[i];
      if (filtro && !filtro(a.no)) continue;
      const inv = M.inv(a.mundo);
      if (!inv) continue;
      const [lx, ly] = M.ponto(inv, px, py);
      if (a.ret) {
        if (lx >= a.ret[0] && lx <= a.ret[2] && ly >= a.ret[1] && ly <= a.ret[3]) return a.no;
        continue;
      }
      if (a.tris) {
        const v = a.tris;
        for (let k = 0; k + 5 < v.length; k += 6) {
          if (dentroTriangulo(lx, ly, v[k], v[k + 1], v[k + 2], v[k + 3], v[k + 4], v[k + 5])) return a.no;
        }
      } else if (a.bbox) {
        const b = a.bbox;
        if (lx >= b[0] && lx <= b[2] && ly >= b[1] && ly <= b[3]) return a.no;
      }
    }
    return null;
  }

  // limites (no palco) de um nó, juntando tudo o que foi desenhado dentro dele
  limites(no) {
    let b = null;
    for (const a of this.alvos) {
      let n = a.no;
      let dentro = false;
      while (n) { if (n === no) { dentro = true; break; } n = n.pai; }
      if (!dentro || !a.bbox) continue;
      const [x0, y0, x1, y1] = a.ret || a.bbox;
      for (const [x, y] of [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) {
        const [px, py] = M.ponto(a.mundo, x, y);
        if (!b) b = [px, py, px, py];
        else { b[0] = Math.min(b[0], px); b[1] = Math.min(b[1], py); b[2] = Math.max(b[2], px); b[3] = Math.max(b[3], py); }
      }
    }
    return b;
  }

  limitesConteudo() {
    let b = null;
    for (const a of this.alvos) {
      if (!a.bbox) continue;
      const [x0, y0, x1, y1] = a.ret || a.bbox;
      for (const [x, y] of [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) {
        const [px, py] = M.ponto(a.mundo, x, y);
        if (!b) b = [px, py, px, py];
        else { b[0] = Math.min(b[0], px); b[1] = Math.min(b[1], py); b[2] = Math.max(b[2], px); b[3] = Math.max(b[3], py); }
      }
    }
    return b;
  }

  // PNG da tela atual (para comparar com o jogo)
  capturar() { return this.canvas.toDataURL('image/png'); }
}

function dentroTriangulo(px, py, ax, ay, bx, by, cx, cy) {
  const d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by);
  const d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy);
  const d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay);
  const neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0;
  return !(neg && pos);
}

function linhasParaTriangulos(v, larg) {
  const out = [];
  const meia = larg / 2;
  for (let k = 0; k + 3 < v.length; k += 4) {
    const x0 = v[k], y0 = v[k + 1], x1 = v[k + 2], y1 = v[k + 3];
    const dx = x1 - x0, dy = y1 - y0, l = Math.hypot(dx, dy) || 1;
    const nx = -dy / l * meia, ny = dx / l * meia;
    out.push(x0 + nx, y0 + ny, x1 + nx, y1 + ny, x1 - nx, y1 - ny, x0 + nx, y0 + ny, x1 - nx, y1 - ny, x0 - nx, y0 - ny);
  }
  return new Float32Array(out);
}

// ---------------------------------------------------------------- fontes do jogo (data/ui/fonts/*.ttf)
const carregadas = new Set();
const tentativas = new Map();

const FONTES_SISTEMA = new Set(['arial', 'times new roman', 'verdana', 'tahoma', 'helvetica', 'courier new', '_sans', '_serif']);

export function carregarFonte(nome) {
  if (FONTES_SISTEMA.has(String(nome).toLowerCase())) return Promise.resolve(false);
  if (!tentativas.has(nome)) {
    tentativas.set(nome, (async () => {
      try {
        const f = new FontFace('apt_' + nome, `url(/api/fonte_ttf?nome=${encodeURIComponent(nome)})`);
        await f.load();
        document.fonts.add(f);
        carregadas.add(nome);
        return true;
      } catch { return false; }
    })());
  }
  return tentativas.get(nome);
}

function desenharTexto(texto, nomeFonte, c, w, h, q) {
  const cv = document.createElement('canvas');
  cv.width = Math.max(2, Math.ceil(w * q));
  cv.height = Math.max(2, Math.ceil(h * q));
  const g = cv.getContext('2d');
  g.scale(q, q);
  const familia = carregadas.has(nomeFonte) ? `"apt_${nomeFonte}", sans-serif` : `"${nomeFonte}", "Segoe UI", sans-serif`;
  const altura = Math.max(4, c.altura || 12);
  g.font = `${altura}px ${familia}`;
  g.fillStyle = `rgba(${c.cor[0]},${c.cor[1]},${c.cor[2]},${(c.cor[3] ?? 255) / 255})`;
  // as fontes do jogo têm métricas fora do padrão: posiciona pela tinta real dos glifos, alinhada ao topo da
  // caixa (como o campo de texto do Flash: 2 px de margem)
  g.textBaseline = 'alphabetic';
  const al = c.alinh === 2 ? 'center' : c.alinh === 1 ? 'right' : 'left';
  g.textAlign = al;
  const x = al === 'center' ? w / 2 : al === 'right' ? w - 2 : 2;
  const linhas = c.multilinha ? String(texto).split('\n') : [String(texto)];
  const med = g.measureText('HÁ0' + linhas.join(''));
  const asc = med.actualBoundingBoxAscent || altura * 0.75, desc = med.actualBoundingBoxDescent || altura * 0.2;
  const passo = Math.max(altura, asc + desc) * 1.1;
  let y = 2 + altura * 0.1 + asc;
  for (const l of linhas) { g.fillText(l, x, y, w - 4); y += passo; }
  return cv;
}
