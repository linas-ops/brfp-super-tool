// Ferramentas com prévia ao vivo: remapear objetos em anel (luzes da cobertura...), torcida (marcar, colorir,
// pintar com imagem, remover) e geração de assentos a partir de uma malha (shadow_seat).
import * as THREE from 'three';
import { icone } from './icones.js';
import { el, esc, aviso, fmtInt, fmtNum, nota, campoNumero, interruptor, painelFlutuante, fecharPainel, campoRotulado, arquivoLocal } from './ui.js';

const GRAUS = 180 / Math.PI;
// SeatColor guarda a cor em sRGB (como aparece no seletor), no formato ARGB de 32 bits.
const argb = (c) => (0xFF000000 | c.getHex(THREE.SRGBColorSpace)) >>> 0;
const corDeArgb = (v) => new THREE.Color(((v >>> 16) & 255) / 255, ((v >>> 8) & 255) / 255, (v & 255) / 255);
const PALETA = ['#ffffff', '#c8ccd2', '#3a3a3c', '#111111', '#d32f2f', '#ff7a00', '#ffd400', '#2e7d32', '#00a8e8', '#1565c0', '#0d1b4a', '#6a1b9a', '#8d2b2b', '#e91e63'];

function seletor(opcoes, valor, aoMudar) {
  const s = el('select', { class: 'seletor', style: { maxWidth: 'none', width: '100%' } });
  for (const [v, r] of opcoes) { const o = el('option', { value: v }, r); if (String(v) === String(valor)) o.selected = true; s.append(o); }
  s.onchange = () => aoMudar(s.value);
  return s;
}

function num(valor, aoMudar, opts = {}) {
  return campoNumero({ valor, passo: opts.passo ?? 0.1, casas: opts.casas ?? 2, passoCtrl: opts.passoCtrl ?? 1, min: opts.min, max: opts.max, eixo: opts.eixo, aoMudar });
}

// ======================================================================== remapear em anel
export function abrirRemapear(app) {
  const md = app.modelo, v = app.viewport;
  const moveis = v.nosMoveis();
  if (!moveis.length) {
    aviso('Selecione os objetos ou luzes que quer remapear', { tipo: 'aviso', detalhe: 'Ex.: selecione o grupo “Luzes da cobertura” (ou “Cobertura”) na estrutura, ou um refletor e Shift+L para todas as cópias.' });
    return;
  }
  const itens = moveis.map((n) => ({ n, local0: n.local.slice(), W0: n.mundoM.clone(), p0: new THREE.Vector3().setFromMatrixPosition(n.mundoM) }));
  const xs = itens.map((i) => i.p0.x), zs = itens.map((i) => i.p0.z), ys = itens.map((i) => i.p0.y);
  const src = {
    cx: (Math.min(...xs) + Math.max(...xs)) / 2, cz: (Math.min(...zs) + Math.max(...zs)) / 2,
    a: Math.max(0.5, (Math.max(...xs) - Math.min(...xs)) / 2), b: Math.max(0.5, (Math.max(...zs) - Math.min(...zs)) / 2),
    y0: Math.min(...ys), y1: Math.max(...ys),
  };
  const P = { cx: src.cx, cz: src.cz, a: src.a, b: src.b, dy: 0, ky: 1, modo: 'proporcional', girar: true, encostar: 'nao', folga: 0.4, alvo: null };
  const ray = new THREE.Raycaster();
  let malhasAlvo = [];
  const calcular = () => {
    const RY = new THREE.Matrix4();
    for (const it of itens) {
      const dx = it.p0.x - src.cx, dz = it.p0.z - src.cz;
      let x, z;
      if (P.modo === 'borda') {
        const th = Math.atan2(dz / src.b, dx / src.a);
        const S = new THREE.Vector2(src.a * Math.cos(th), src.b * Math.sin(th));
        const N = new THREE.Vector2(Math.cos(th) / src.a, Math.sin(th) / src.b).normalize();
        const d = new THREE.Vector2(dx, dz).sub(S).dot(N);
        const S2 = new THREE.Vector2(P.a * Math.cos(th), P.b * Math.sin(th));
        const N2 = new THREE.Vector2(Math.cos(th) / P.a, Math.sin(th) / P.b).normalize();
        x = P.cx + S2.x + d * N2.x; z = P.cz + S2.y + d * N2.y;
      } else {
        x = P.cx + dx * (P.a / src.a); z = P.cz + dz * (P.b / src.b);
      }
      let y = src.y0 + P.dy + (it.p0.y - src.y0) * P.ky;
      if (P.encostar !== 'nao' && malhasAlvo.length) {
        const cima = P.encostar === 'acima';
        ray.set(new THREE.Vector3(x, y + (cima ? -0.5 : 0.5), z), new THREE.Vector3(0, cima ? 1 : -1, 0));
        ray.far = 80;
        const h = ray.intersectObjects(malhasAlvo, false)[0];
        if (h) y = h.point.y + (cima ? -P.folga : P.folga);
      }
      const R0 = it.W0.clone().setPosition(0, 0, 0);
      let dth = 0;
      if (P.girar) dth = Math.atan2(z - P.cz, x - P.cx) - Math.atan2(dz, dx);
      RY.makeRotationY(-dth);
      const W = new THREE.Matrix4().makeTranslation(x, y, z).multiply(RY).multiply(R0);
      it.local = md.localPara(it.n, W);
    }
    app.aplicarLocaisPrevia(itens.map((it) => [it.n, it.local]));
  };
  let tmr = null;
  const agendar = () => { clearTimeout(tmr); tmr = setTimeout(calcular, P.encostar !== 'nao' ? 120 : 0); };
  const campo = (rot, chave, opts, dica) => campoRotulado(rot, num(P[chave], (x) => { P[chave] = x; agendar(); }, opts).el, dica);
  const txtAlvo = el('small', { style: { color: 'var(--texto-3)' } }, 'nenhum');
  const escolherAlvo = () => {
    app.escolherNaVista('Clique na malha alvo (ex.: a cobertura nova)', (id) => {
      const n = md.nos[id];
      P.alvo = id;
      malhasAlvo = [];
      v.objs[id]?.traverse((o) => { if (o.isMesh && !o.userData.overlay && !o.userData.luz && o.geometry) malhasAlvo.push(o); });
      txtAlvo.textContent = `${n.rotulo} (${malhasAlvo.length} malhas)`;
      if (P.encostar === 'nao') { P.encostar = 'acima'; selEnc.value = 'acima'; }
      agendar();
    });
  };
  const usarCaixaAlvo = () => {
    if (P.alvo == null) { aviso('Escolha a malha alvo primeiro', { tipo: 'aviso' }); return; }
    const c = v.caixaDe([P.alvo]);
    P.cx = (c.min.x + c.max.x) / 2; P.cz = (c.min.z + c.max.z) / 2;
    P.a = (c.max.x - c.min.x) / 2; P.b = (c.max.z - c.min.z) / 2;
    painel.fechar('recriar');
    abrirComValores();
  };
  const selEnc = seletor([['nao', 'Não'], ['acima', 'Pendurar embaixo da malha acima'], ['abaixo', 'Apoiar em cima da malha abaixo']], P.encostar, (x) => { P.encostar = x; agendar(); });
  let painel;
  const abrirComValores = () => {
    painel = painelFlutuante({
      titulo: `Remapear em anel · ${fmtInt(itens.length)} itens`, icone: 'girar', largura: 360,
      corpo: [
        nota(`Anel atual: centro (${fmtNum(src.cx, 1)}, ${fmtNum(src.cz, 1)}), raios ${fmtNum(src.a, 1)} × ${fmtNum(src.b, 1)} m. Ajuste o anel novo; a vista mostra o resultado na hora.`),
        el('h4', {}, 'Anel novo'),
        campo('Centro X', 'cx', { passo: 0.1 }), campo('Centro Z', 'cz', { passo: 0.1 }),
        campo('Raio em X (m)', 'a', { passo: 0.1, min: 0.5 }, 'Metade da largura do anel no eixo X'),
        campo('Raio em Z (m)', 'b', { passo: 0.1, min: 0.5 }, 'Metade da largura do anel no eixo Z'),
        campoRotulado('Mapeamento', seletor([['proporcional', 'Proporcional (estica o anel)'], ['borda', 'Manter distância da borda']], P.modo, (x) => { P.modo = x; agendar(); })),
        el('h4', {}, 'Altura'),
        campo('Subir/descer (m)', 'dy', { passo: 0.05 }), campo('Escala vertical', 'ky', { passo: 0.01, casas: 3 }),
        interruptor({ titulo: 'Girar junto', descricao: 'Cada item gira o mesmo ângulo que andou em volta do centro (refletores continuam apontando para o campo).', marcado: P.girar, aoMudar: (x) => { P.girar = x; agendar(); } }).el,
        el('h4', {}, 'Encostar numa malha'),
        el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: escolherAlvo }, icone('alvo', 13), 'Escolher alvo na vista'),
          el('button', { class: 'btn peq', onclick: usarCaixaAlvo, title: 'Usa a caixa da malha alvo como anel novo' }, 'Anel = caixa do alvo')),
        campoRotulado('Alvo', txtAlvo),
        campoRotulado('Encostar', selEnc),
        campo('Folga (m)', 'folga', { passo: 0.05, min: 0 }),
      ],
      botoes: [
        { rotulo: 'Cancelar', fn: () => painel.fechar('cancelar') },
        { rotulo: 'Aplicar', classe: 'btn-primario peq', icone: 'check', fn: () => painel.fechar('aplicar') },
      ],
      aoFechar: (motivo) => {
        if (motivo === 'recriar') return;
        clearTimeout(tmr);
        app.cancelarEscolhaNaVista();
        if (motivo === 'aplicar') {
          calcular();
          app.confirmarLocais(itens.map((it) => [it.n, it.local0, it.local]), `Remapear ${itens.length} itens em anel`);
        } else {
          app.aplicarLocaisPrevia(itens.map((it) => [it.n, it.local0]));
        }
      },
    });
    agendar();
  };
  abrirComValores();
}

// ======================================================================== torcida
export function abrirTorcida(app) {
  const md = app.modelo, v = app.viewport;
  const t = md.torcida;
  if (!t) { aviso('Este estádio não tem a nuvem de assentos no export', { tipo: 'aviso' }); return; }
  let cor = new THREE.Color('#1565c0');
  const qtd = el('div', { class: 'pf-numero' });
  const sub = el('small', { style: { color: 'var(--texto-3)' } });
  const marc = el('small', { style: { color: 'var(--texto-2)' } });
  const atualizar = () => {
    qtd.textContent = `${fmtInt(t.atual.n)} assentos`;
    sub.textContent = t.atual !== t.original ? 'alterada — Ctrl+S grava no arquivo da torcida' : t.nome || '';
    marc.textContent = app.marcados.size ? `${fmtInt(app.marcados.size)} marcados` : 'nenhum marcado (as ações valem para todos)';
  };
  app.aoMudarTorcida = atualizar;
  const inpCor = el('input', { type: 'color', value: '#' + cor.getHexString(THREE.SRGBColorSpace) });
  inpCor.oninput = () => { cor = new THREE.Color().setStyle(inpCor.value, THREE.SRGBColorSpace); };
  const paleta = el('div', { class: 'paleta' });
  for (const c of PALETA) paleta.append(el('button', { style: { background: c }, title: c, onclick: () => { inpCor.value = c; cor = new THREE.Color().setStyle(c, THREE.SRGBColorSpace); } }));
  const alvos = () => (app.marcados.size ? [...app.marcados] : [...Array(t.atual.n).keys()]);
  const pintar = (indices, corDe, nome) => {
    const d = t.atual;
    const mapa = (d.mapas.SeatColor || new Array(d.n).fill(0xFFFFFFFF)).slice();
    for (const i of indices) mapa[i] = corDe(i);
    app.alterarTorcida({ ...d, mapas: { ...d.mapas, SeatColor: mapa } }, nome);
    if (v.torcida && v.torcida.userData.modoCor !== 'SeatColor') app.colorirTorcida('SeatColor');
  };
  const aplicarCor = () => { const c = argb(cor); pintar(alvos(), () => c, `Cor de ${fmtInt(alvos().length)} assentos`); };
  const porTier = () => {
    const tiers = t.atual.mapas.SeatTier;
    if (!tiers) { aviso('A nuvem não tem o mapa SeatTier', { tipo: 'aviso' }); return; }
    const presentes = [...new Set(tiers)].sort((a, b) => a - b);
    const cores = ['#1565c0', '#d32f2f', '#ffd400', '#2e7d32', '#ffffff', '#6a1b9a'];
    const mapaCor = new Map(presentes.map((tr, i) => [tr, argb(new THREE.Color().setStyle(cores[i % cores.length], THREE.SRGBColorSpace))]));
    pintar(alvos(), (i) => mapaCor.get(tiers[i]), 'Cores por setor');
    aviso(`Setores ${presentes.join(', ')} pintados com cores diferentes`, { detalhe: 'Use “Aplicar cor” com marcação para ajustar cada setor.' });
  };
  const comImagem = async () => {
    const arq = await arquivoLocal('image/png,image/jpeg,image/webp,image/bmp');
    if (!arq) return;
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = URL.createObjectURL(arq); });
    const cv = el('canvas', { width: img.naturalWidth, height: img.naturalHeight });
    const ctx = cv.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const px = ctx.getImageData(0, 0, cv.width, cv.height).data;
    const ids = alvos();
    const r = v.canvas.getBoundingClientRect();
    const pos = t.atual.posicoes;
    const vv = new THREE.Vector3();
    const tela = new Map();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const i of ids) {
      vv.set(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]).project(v.camera);
      if (vv.z > 1 || vv.z < -1) continue;
      const sx = (vv.x + 1) / 2 * r.width, sy = (1 - vv.y) / 2 * r.height;
      if (sx < 0 || sy < 0 || sx > r.width || sy > r.height) continue;   // só o que aparece na tela
      tela.set(i, [sx, sy]);
      x0 = Math.min(x0, sx); y0 = Math.min(y0, sy); x1 = Math.max(x1, sx); y1 = Math.max(y1, sy);
    }
    if (!tela.size) { aviso('Nenhum assento visível na vista atual', { tipo: 'aviso', detalhe: 'Enquadre a arquibancada de frente antes.' }); return; }
    const cvt = new THREE.Color();
    pintar([...tela.keys()], (i) => {
      const [sx, sy] = tela.get(i);
      const u = Math.min(cv.width - 1, Math.max(0, Math.floor((sx - x0) / Math.max(1, x1 - x0) * cv.width)));
      const w = Math.min(cv.height - 1, Math.max(0, Math.floor((sy - y0) / Math.max(1, y1 - y0) * cv.height)));
      const k = (w * cv.width + u) * 4;
      cvt.setRGB(px[k] / 255, px[k + 1] / 255, px[k + 2] / 255, THREE.SRGBColorSpace);
      return argb(cvt);
    }, 'Pintar assentos com imagem');
    aviso(`Imagem aplicada em ${fmtInt(tela.size)} assentos`, { tipo: 'sucesso', detalhe: 'A imagem é projetada como você vê a arquibancada agora.' });
  };
  const remover = () => {
    if (!app.marcados.size) { aviso('Marque os assentos que quer remover', { tipo: 'aviso' }); return; }
    const tirar = app.marcados;
    const d = t.atual;
    const fica = [];
    for (let i = 0; i < d.n; i++) if (!tirar.has(i)) fica.push(i);
    const novo = { n: fica.length, posicoes: [], mapas: {} };
    for (const i of fica) novo.posicoes.push(d.posicoes[i * 3], d.posicoes[i * 3 + 1], d.posicoes[i * 3 + 2]);
    for (const [k, arr] of Object.entries(d.mapas)) novo.mapas[k] = fica.map((i) => arr[i]);
    app.marcados = new Set();
    app.alterarTorcida(novo, `Remover ${fmtInt(tirar.size)} assentos`);
  };
  const painel = painelFlutuante({
    titulo: 'Torcida', icone: 'torcida', largura: 340,
    corpo: [
      el('div', {}, qtd, sub),
      campoRotulado('Colorir a vista por', seletor([['SeatColor', 'Cor do assento'], ['SeatTier', 'Setor (tier)'], ['Attendance', 'Presença'], ['HomeAwayNeutral', 'Mandante / visitante']],
        v.torcida?.userData.modoCor || 'SeatColor', (x) => app.colorirTorcida(x))),
      el('h4', {}, 'Marcar assentos'),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', onclick: () => app.ferramentaTorcida() }, icone('selecao', 13), 'Marcar com caixa'),
        el('button', { class: 'btn peq', onclick: () => { app.marcados = new Set([...Array(t.atual.n).keys()]); app.redesenharMarcados(); } }, 'Todos'),
        el('button', { class: 'btn peq', onclick: () => { app.marcados = new Set(); app.redesenharMarcados(); } }, 'Nenhum')),
      marc,
      el('h4', {}, 'Cores'),
      el('div', { class: 'cor-linha' }, paleta, inpCor),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn-primario peq', onclick: aplicarCor }, icone('pincel', 13), 'Aplicar cor'),
        el('button', { class: 'btn peq', onclick: porTier, title: 'Uma cor por setor (SeatTier)' }, 'Por setor'),
        el('button', { class: 'btn peq', onclick: comImagem, title: 'Projeta uma imagem (escudo, mosaico) nos assentos, como eles aparecem na vista agora' }, icone('imagem', 13), 'Imagem…')),
      el('h4', {}, 'Assentos'),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', onclick: () => { painel.fechar('trocar'); abrirGerarAssentos(app); } }, icone('torcida', 13), 'Gerar a partir de malha…'),
        el('button', { class: 'btn-perigo peq', onclick: remover }, icone('apagar', 13), 'Remover marcados')),
      nota('Tudo aqui entra nas alterações pendentes (com desfazer) e só vai para o arquivo da torcida ao salvar (Ctrl+S).'),
    ],
    aoFechar: () => { app.aoMudarTorcida = null; if (v.ferramentaCaixa === 'torcida') app.sairFerramentaTorcida(); },
  });
  atualizar();
  return painel;
}

// ======================================================================== gerar assentos a partir de uma malha
function malhaFonte(app, id) {
  const md = app.modelo, v = app.viewport;
  const n = md.nos[id];
  const out = [];
  v.objs[id]?.updateMatrixWorld(true);
  v.objs[id]?.userData.pecasObj.traverse((o) => {
    if (o.isMesh && o.geometry && !o.userData.overlay && !o.userData.luz && !o.userData.marcador && o.geometry.attributes.position) out.push(o);
  });
  return { n, malhas: out };
}

export function proxyDosAssentos(app) {
  const md = app.modelo;
  for (const n of md.nos) {
    for (const p of n.malhas || []) {
      const info = md.malhas[p.m];
      if (info?.enlighten === 'Proxy' || /shadow_seat/i.test(info?.nome || '')) return n.id;
    }
  }
  return null;
}

export function gerarDeMalhas(malhas, P, centro = new THREE.Vector3()) {
  const up = new THREE.Vector3(0, 1, 0);
  const grupos = new Map();
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const e1 = new THREE.Vector3(), e2 = new THREE.Vector3(), nn = new THREE.Vector3();
  for (const m of malhas) {
    const pos = m.geometry.attributes.position;
    const idx = m.geometry.index;
    const nt = idx ? idx.count / 3 : pos.count / 3;
    for (let t = 0; t < nt; t++) {
      const i0 = idx ? idx.getX(t * 3) : t * 3, i1 = idx ? idx.getX(t * 3 + 1) : t * 3 + 1, i2 = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
      a.fromBufferAttribute(pos, i0).applyMatrix4(m.matrixWorld);
      b.fromBufferAttribute(pos, i1).applyMatrix4(m.matrixWorld);
      c.fromBufferAttribute(pos, i2).applyMatrix4(m.matrixWorld);
      nn.crossVectors(e1.subVectors(b, a), e2.subVectors(c, a));
      const area = nn.length() / 2;
      if (area < 0.05) continue;
      nn.normalize();
      if (nn.y < 0) nn.negate();
      if (nn.y < 0.25) continue;                    // faces quase verticais não são placas de assento
      const d = nn.dot(a);
      const k = `${Math.round(nn.x * 30)},${Math.round(nn.y * 30)},${Math.round(nn.z * 30)},${Math.round(d * 2)}`;
      if (!grupos.has(k)) grupos.set(k, { n: nn.clone(), tris: [] });
      grupos.get(k).tris.push([a.clone(), b.clone(), c.clone()]);
    }
  }
  const posicoes = [], orient = [];
  const visto = new Set();
  for (const g of grupos.values()) {
    const n = g.n;
    const O = g.tris[0][0];
    const paraCentro = new THREE.Vector3(centro.x - O.x, 0, centro.z - O.z).normalize();
    let tdir = new THREE.Vector3().crossVectors(up, n);
    if (tdir.lengthSq() < 0.02) tdir = new THREE.Vector3().crossVectors(up, paraCentro);
    tdir.normalize();
    let sdir = new THREE.Vector3().crossVectors(n, tdir).normalize();
    if (sdir.y < 0 || (Math.abs(sdir.y) < 0.05 && sdir.dot(paraCentro) > 0)) sdir.negate();
    const horiz = Math.max(0.3, Math.hypot(sdir.x, sdir.z));
    const passoU = P.largura, passoV = P.fileira / horiz;
    // direção para onde os assentos olham
    let olhar = new THREE.Vector3(-sdir.x, 0, -sdir.z);
    if (P.direcao === 'centro' || olhar.lengthSq() < 0.01) olhar = paraCentro.clone();
    olhar.normalize();
    // torcedor olha para o campo: se a placa estiver inclinada "ao contrário", vira
    if (P.paraCampo !== false && olhar.dot(paraCentro) < -0.05) olhar.negate();
    if (P.inverter) olhar.negate();
    const ori = Math.atan2(-olhar.z, olhar.x) * GRAUS;
    // coordenadas (u, v) do grupo
    const uv = (p) => [p.clone().sub(O).dot(tdir), p.clone().sub(O).dot(sdir)];
    let umin = Infinity, umax = -Infinity, vmin = Infinity;
    const tris2 = g.tris.map((tr) => tr.map(uv));
    for (const tr of tris2) for (const [u, w] of tr) { umin = Math.min(umin, u); umax = Math.max(umax, u); vmin = Math.min(vmin, w); }
    const u0 = umin + P.margem + passoU / 2, v0 = vmin + passoV / 2;
    const chaveG = `${n.x.toFixed(2)},${n.y.toFixed(2)},${n.z.toFixed(2)}`;
    for (const tr of tris2) {
      const [[ax, ay], [bx, by], [cx, cy]] = tr;
      const tu0 = Math.min(ax, bx, cx), tu1 = Math.max(ax, bx, cx), tv0 = Math.min(ay, by, cy), tv1 = Math.max(ay, by, cy);
      const den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      if (Math.abs(den) < 1e-9) continue;
      const i0 = Math.max(0, Math.ceil((tu0 - u0) / passoU)), i1 = Math.floor((Math.min(tu1, umax - P.margem - passoU / 2) - u0) / passoU);
      const j0 = Math.max(0, Math.ceil((tv0 - v0) / passoV)), j1 = Math.floor((tv1 - v0) / passoV);
      for (let i = i0; i <= i1; i++) {
        const u = u0 + i * passoU;
        for (let j = j0; j <= j1; j++) {
          const w = v0 + j * passoV;
          const l1 = ((by - cy) * (u - cx) + (cx - bx) * (w - cy)) / den;
          const l2 = ((cy - ay) * (u - cx) + (ax - cx) * (w - cy)) / den;
          const l3 = 1 - l1 - l2;
          if (l1 < -1e-6 || l2 < -1e-6 || l3 < -1e-6) continue;
          const k = `${chaveG}|${Math.round(O.x * 10)}|${Math.round(O.z * 10)}|${i}|${j}`;
          if (visto.has(k)) continue;
          visto.add(k);
          const p = O.clone().addScaledVector(tdir, u).addScaledVector(sdir, w);
          posicoes.push(p.x, p.y - P.altura, p.z);
          orient.push(ori);
        }
      }
    }
  }
  return { posicoes, orient, grupos: grupos.size };
}

// mede, na torcida atual, a largura do assento, a profundidade da fileira e a distância até a placa de cima
export function calibrar(antigas, malhas) {
  const n = antigas.length / 3;
  if (n < 50) return null;
  const T = 1.5;
  const grade = new Map();
  for (let i = 0; i < n; i++) {
    const k = `${Math.floor(antigas[i * 3] / T)},${Math.floor(antigas[i * 3 + 2] / T)}`;
    if (!grade.has(k)) grade.set(k, []);
    grade.get(k).push(i);
  }
  const passo = Math.max(1, Math.floor(n / 1500));
  const larg = [], fil = [], alt = [];
  const ray = new THREE.Raycaster();
  ray.far = 3;
  const lados = malhas.map((m) => m.material);
  const dupla = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
  malhas.forEach((m) => { m.material = dupla; });
  const o = new THREE.Vector3(), cima = new THREE.Vector3(0, 1, 0);
  for (let i = 0; i < n; i += passo) {
    const x = antigas[i * 3], y = antigas[i * 3 + 1], z = antigas[i * 3 + 2];
    let dl = Infinity, df = Infinity;
    const gx = Math.floor(x / T), gz = Math.floor(z / T);
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
      for (const j of grade.get(`${gx + a},${gz + b}`) || []) {
        if (j === i) continue;
        const dh = Math.hypot(antigas[j * 3] - x, antigas[j * 3 + 2] - z);
        const dy = Math.abs(antigas[j * 3 + 1] - y);
        if (dy < 0.06 && dh > 0.2 && dh < dl) dl = dh;
        if (dy > 0.15 && dy < 1.2 && dh > 0.2 && dh < df) df = dh;
      }
    }
    if (dl < 2) larg.push(dl);
    if (df < 2.5) fil.push(df);
    if (malhas.length && i % (passo * 3) === 0) {
      ray.set(o.set(x, y, z), cima);
      const h = ray.intersectObjects(malhas, false)[0];
      if (h) alt.push(h.distance);
    }
  }
  malhas.forEach((m, k) => { m.material = lados[k]; });
  dupla.dispose();
  const med = (a) => { if (!a.length) return null; a.sort((p, q) => p - q); return a[Math.floor(a.length / 2)]; };
  return { largura: med(larg), fileira: med(fil), altura: med(alt) };
}

function vizinhoMaisProximo(antigas) {
  const n = antigas.length / 3;
  const T = 3;
  const grade = new Map();
  for (let i = 0; i < n; i++) {
    const k = `${Math.floor(antigas[i * 3] / T)},${Math.floor(antigas[i * 3 + 2] / T)}`;
    if (!grade.has(k)) grade.set(k, []);
    grade.get(k).push(i);
  }
  return (x, y, z) => {
    const gx = Math.floor(x / T), gz = Math.floor(z / T);
    let melhor = -1, dmin = Infinity;
    for (let r = 0; r <= 12 && melhor < 0; r++) {
      for (let dx = -r; dx <= r; dx++) for (let dz = -r; dz <= r; dz++) {
        if (Math.max(Math.abs(dx), Math.abs(dz)) !== r) continue;
        for (const i of grade.get(`${gx + dx},${gz + dz}`) || []) {
          const d = (antigas[i * 3] - x) ** 2 + (antigas[i * 3 + 1] - y) ** 2 + (antigas[i * 3 + 2] - z) ** 2;
          if (d < dmin) { dmin = d; melhor = i; }
        }
      }
    }
    return melhor;
  };
}

export function abrirGerarAssentos(app) {
  const md = app.modelo, v = app.viewport;
  if (!md.torcida) { aviso('Este estádio não tem a nuvem de assentos no export', { tipo: 'aviso' }); return; }
  if (v.espelhado) app.alternarEspelho(false);
  const P = { largura: 0.5, fileira: 0.8, altura: 0.67, margem: 0.1, direcao: 'inclinacao', paraCampo: true, inverter: false, modo: 'substituir', cor: 'manter', corUnica: '#c8ccd2', fonte: proxyDosAssentos(app) };
  const txtFonte = el('small', { style: { color: 'var(--texto-2)' } });
  const resultado = el('div', { class: 'pf-numero' }, '—');
  const resumo = el('small', { style: { color: 'var(--texto-3)' } });
  let gerado = null;
  const mostrarFonte = () => {
    if (P.fonte == null) { txtFonte.textContent = 'nenhuma — selecione uma malha e clique em “Usar a selecionada”'; return; }
    const { n, malhas } = malhaFonte(app, P.fonte);
    txtFonte.textContent = `${n.rotulo} (${malhas.length} seções)`;
  };
  const previa = () => {
    if (P.fonte == null) { aviso('Escolha a malha de origem', { tipo: 'aviso' }); return null; }
    const { malhas } = malhaFonte(app, P.fonte);
    if (!malhas.length) { aviso('A malha de origem não tem geometria carregada (FBX não exportado?)', { tipo: 'aviso' }); return null; }
    const t0 = performance.now();
    gerado = gerarDeMalhas(malhas, P);
    const n = gerado.posicoes.length / 3;
    resultado.textContent = `${fmtInt(n)} assentos`;
    resumo.textContent = `${gerado.grupos} placas · ${((performance.now() - t0) / 1000).toFixed(1)} s · hoje: ${fmtInt(md.torcida.atual.n)}${n > 70000 ? ' · muitos assentos: aumente a largura ou a fileira' : ''}`;
    v.mostrarPrevia(gerado.posicoes, gerado.orient);
    return gerado;
  };
  const aplicar = () => {
    const g = gerado || previa();
    if (!g) return false;
    const antes = md.torcida.atual;
    const n = g.posicoes.length / 3;
    const proximo = vizinhoMaisProximo(antes.posicoes);
    const mapas = {};
    const nomes = Object.keys(antes.mapas);
    const padrao = { Attendance: 1, SeatTier: 0, CardColor: 0, HomeAwayNeutral: 0.5, HomeAwayUltra: 0.5, HomeAwayFiftyFifty: 0.5, SeatColor: 0xFFC8CCD2 };
    const corU = argb(new THREE.Color().setStyle(P.corUnica, THREE.SRGBColorSpace));
    for (const k of nomes) mapas[k] = new Array(n);
    for (let i = 0; i < n; i++) {
      const j = antes.n ? proximo(g.posicoes[i * 3], g.posicoes[i * 3 + 1], g.posicoes[i * 3 + 2]) : -1;
      for (const k of nomes) {
        if (k === 'Orientation') mapas[k][i] = Math.round(g.orient[i] * 1000) / 1000;
        else if (k === 'SeatColor' && P.cor === 'unica') mapas[k][i] = corU;
        else mapas[k][i] = j >= 0 ? antes.mapas[k][j] : (padrao[k] ?? 0);
      }
    }
    let novo;
    if (P.modo === 'adicionar') {
      novo = { n: antes.n + n, posicoes: antes.posicoes.concat(g.posicoes), mapas: {} };
      for (const k of nomes) novo.mapas[k] = antes.mapas[k].concat(mapas[k]);
    } else novo = { n, posicoes: g.posicoes.slice(), mapas };
    app.marcados = new Set();
    app.alterarTorcida(novo, `Gerar ${fmtInt(n)} assentos`);
    aviso(`${fmtInt(n)} assentos gerados`, { tipo: 'sucesso', detalhe: 'A torcida mudou (pendente). Salve com Ctrl+S para gravar o arquivo da nuvem de assentos.' });
    return true;
  };
  const refs = {};
  const campo = (rot, chave, opts, dica) => {
    const c = num(P[chave], (x) => { P[chave] = x; gerado = null; }, opts);
    refs[chave] = c;
    return campoRotulado(rot, c.el, dica);
  };
  const txtCal = el('small', { style: { color: 'var(--texto-3)' } });
  const calibrarAgora = (silencioso = false) => {
    if (P.fonte == null) return;
    const { malhas } = malhaFonte(app, P.fonte);
    const r = calibrar(md.torcida.atual.posicoes, malhas);
    if (!r) { if (!silencioso) aviso('A torcida atual tem poucos assentos para medir', { tipo: 'aviso' }); return; }
    for (const k of ['largura', 'fileira', 'altura']) {
      if (r[k] != null && Number.isFinite(r[k])) { P[k] = Math.round(r[k] * 100) / 100; refs[k]?.definir(P[k]); }
    }
    gerado = null;
    txtCal.textContent = `Medido na torcida atual: assento ${fmtNum(P.largura, 2)} m · fileira ${fmtNum(P.fileira, 2)} m · placa ${fmtNum(P.altura, 2)} m acima.`;
  };
  const painel = painelFlutuante({
    titulo: 'Gerar assentos a partir de malha', icone: 'torcida', largura: 360,
    corpo: [
      nota('Usa as placas da malha de origem (o <b>shadow_seat</b>, que fica ~0,67 m acima de cada assento) e preenche cada placa com fileiras de assentos. Para um estádio novo, substitua o FBX do shadow_seat pelas suas placas e gere de novo.'),
      campoRotulado('Malha de origem', txtFonte),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', onclick: () => { P.fonte = proxyDosAssentos(app); gerado = null; mostrarFonte(); } }, 'Shadow seat'),
        el('button', { class: 'btn peq', onclick: () => { const id = md.ativo; if (id < 0 || !md.nos[id].malhas?.length) { aviso('Selecione um objeto com malha', { tipo: 'aviso' }); return; } P.fonte = id; gerado = null; mostrarFonte(); } }, 'Usar a selecionada')),
      el('h4', {}, 'Medidas'),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => calibrarAgora(false), title: 'Mede largura, fileira e distância da placa nos assentos atuais' }, icone('alvo', 13), 'Medir na torcida atual')),
      txtCal,
      campo('Largura do assento (m)', 'largura', { passo: 0.01, casas: 2, min: 0.3 }),
      campo('Fileira (m, horizontal)', 'fileira', { passo: 0.01, casas: 2, min: 0.4 }),
      campo('Abaixo da placa (m)', 'altura', { passo: 0.01, casas: 2 }, 'Distância vertical entre a placa e o assento (varia por estádio: use “Medir na torcida atual”)'),
      campo('Margem lateral (m)', 'margem', { passo: 0.01, casas: 2, min: 0 }),
      campoRotulado('Olhando para', seletor([['inclinacao', 'Para baixo da arquibancada'], ['centro', 'O centro do campo']], P.direcao, (x) => { P.direcao = x; gerado = null; })),
      interruptor({ titulo: 'Sempre de frente para o campo', descricao: 'Vira os assentos que ficariam de costas (placa inclinada ao contrário). As setas da prévia mostram para onde cada um olha.', marcado: P.paraCampo, aoMudar: (x) => { P.paraCampo = x; gerado = null; } }).el,
      interruptor({ titulo: 'Virar todos (180°)', descricao: 'Se no jogo a torcida aparecer de costas, ligue e gere de novo.', marcado: P.inverter, aoMudar: (x) => { P.inverter = x; gerado = null; } }).el,
      el('h4', {}, 'Resultado'),
      campoRotulado('Torcida atual', seletor([['substituir', 'Substituir todos os assentos'], ['adicionar', 'Manter e adicionar estes']], P.modo, (x) => { P.modo = x; })),
      campoRotulado('Cor', el('div', { class: 'cor-linha' },
        seletor([['manter', 'Copiar do assento antigo mais próximo'], ['unica', 'Uma cor só']], P.cor, (x) => { P.cor = x; }),
        (() => { const i = el('input', { type: 'color', value: P.corUnica }); i.oninput = () => { P.corUnica = i.value; }; return i; })())),
      el('div', {}, resultado, resumo),
    ],
    botoes: [
      { rotulo: 'Cancelar', fn: () => painel.fechar('cancelar') },
      { rotulo: 'Pré-visualizar', icone: 'olho', fn: () => previa() },
      { rotulo: 'Gerar', classe: 'btn-primario peq', icone: 'check', fn: () => { if (aplicar()) painel.fechar('aplicar'); } },
    ],
    aoFechar: () => { v.mostrarPrevia(null); },
  });
  mostrarFonte();
  calibrarAgora(true);
  if (!app.estadoTorcida?.visivel) app.alternarTorcida(true);
}

// ======================================================================== luzes: adicionar com um clique e editar
const TIPOS_LUZ = [['spot', 'Spot (refletor)'], ['esfera', 'Pontual'], ['tubo', 'Tubo'], ['retangulo', 'Retangular']];

export function abrirLuzes(app) {
  const md = app.modelo, v = app.viewport;
  if (v.espelhado) app.alternarEspelho(false);
  const P = { mirar: localStorage.getItem('editor.luzMirar') || 'centro', afastar: 0.3, reaproveitar: false };
  const corpo = el('div', { class: 'pf-sec' });
  const ativo = () => md.nos[md.ativo];

  const descModelo = el('div', { class: 'tex-txt' });
  const avisoModelo = el('div');
  const atualizarModelo = () => {
    const m = app.modeloLuz();
    descModelo.innerHTML = m ? `<b>${esc(m.nome)}</b><small>${esc(TIPOS_LUZ.find((t) => t[0] === m.luz?.tipo)?.[1] || 'Luz')} · ${esc(m.alvo.arq.split('/').pop())}</small>`
      : '<small>Nenhuma luz no estádio para servir de modelo</small>';
    avisoModelo.replaceChildren(m?.aninhado && (m.compartilhado || 1) > 1
      ? nota(`Este modelo fica dentro de um prefab usado <b>${m.compartilhado}</b> vezes: cada luz nova aparece em todas as cópias dele. Prefira um modelo de um layer de luzes (ex.: “Luzes da cobertura”).`, 'alerta') : '');
    const exc = m ? app.notaGrupoExcluido([m], 'As luzes novas vão para o mesmo arquivo do modelo,') : null;
    if (exc) avisoModelo.append(exc);
  };
  const tipos = [...new Set(md.nos.filter((n) => n.tipo === 'luz' && !n.removido).map((n) => n.luz?.tipo))];
  const escolherTipo = seletor([['', 'Trocar o tipo do modelo…'], ...TIPOS_LUZ.filter(([t]) => tipos.includes(t))], '', (t) => {
    if (!t) return;
    const luzes = md.nos.filter((n) => n.tipo === 'luz' && !n.removido && n.alvo && !n.nova && n.luz?.tipo === t && !n.aninhado);
    const noJogo = luzes.filter((n) => !md.ocultoNoJogo(n));
    const lista = noJogo.length ? noJogo : luzes;
    const m = lista.find((n) => /roof/i.test(n.alvo.arq)) || lista[0];
    if (m) { app.modeloLuzId = m.id; atualizarModelo(); }
    escolherTipo.value = '';
  });
  const usarSel = el('button', { class: 'btn peq', onclick: () => {
    const n = ativo();
    if (n?.tipo === 'luz') { app.modeloLuzId = n.id; atualizarModelo(); } else aviso('Selecione uma luz para usar como modelo', { tipo: 'aviso' });
  } }, icone('alvo', 13), 'Usar a selecionada');

  const botaoAdd = el('button', { class: 'btn-primario', onclick: () => alternarAdicionar() }, icone('luzMais', 14), 'Adicionar com clique');
  const alternarAdicionar = () => {
    if (app.modoLuz?.tipo === 'adicionar') { app.sairModoLuz(); return; }
    if (!app.modeloLuz()) return;
    app.entrarModoLuz({ tipo: 'adicionar', icone: 'luzMais', msg: 'Clique onde a luz deve ficar (encosta na superfície)',
      aoClicar: (d) => { const n = app.adicionarLuzNoPonto(d.x, d.y, P); if (n) md.selecionar(n.id); },
      aoSair: () => botaoAdd.classList.remove('ativo') });
    botaoAdd.classList.add('ativo');
  };

  // edição das selecionadas
  const secSel = el('div');
  const montarSel = () => {
    const luzes = app.luzesSelecionadas();
    secSel.replaceChildren();
    secSel.append(el('h4', {}, luzes.length ? `Selecionadas (${luzes.length})` : 'Selecionadas'));
    if (!luzes.length) { secSel.append(el('small', { class: 'mudo' }, 'Clique numa luz (ligue as luzes na vista) ou selecione várias na estrutura.')); return; }
    const exc = app.notaGrupoExcluido(luzes, luzes.length > 1 ? 'Há luzes selecionadas' : 'Esta luz está');
    if (exc) secSel.append(exc);
    const L = luzes[luzes.length - 1].luz || {};
    const ids = luzes.map((n) => n.id);
    const chave = ids.join(',');
    const cor = el('input', { type: 'color', value: '#' + new THREE.Color(...(L.cor || [1, 1, 1])).getHexString(THREE.SRGBColorSpace) });
    cor.oninput = () => { const c = new THREE.Color().setStyle(cor.value, THREE.SRGBColorSpace); app.alterarLuzes(ids, { cor: [c.r, c.g, c.b] }, 'Cor da luz', 'luzcor:' + chave); };
    secSel.append(campoRotulado('Cor', cor));
    secSel.append(campoRotulado('Intensidade', num(L.intensidade ?? 1, (x, fim) => app.alterarLuzes(ids, { intensidade: x }, 'Intensidade da luz', fim ? null : 'luzint:' + chave), { passo: 50, casas: 0, passoCtrl: 500, min: 0 }).el));
    secSel.append(campoRotulado('Alcance (m)', num(L.raio ?? 10, (x, fim) => app.alterarLuzes(ids, { raio: x }, 'Alcance da luz', fim ? null : 'luzraio:' + chave), { passo: 0.5, casas: 1, passoCtrl: 5, min: 0 }).el));
    if (L.tipo === 'spot') secSel.append(campoRotulado('Abertura (°)', num(L.angulo ?? 45, (x, fim) => app.alterarLuzes(ids, { angulo: x }, 'Abertura da luz', fim ? null : 'luzang:' + chave), { passo: 0.5, casas: 1, passoCtrl: 5, min: 1, max: 179 }).el));
    secSel.append(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', title: 'Ctrl+D', onclick: () => app.duplicarLuzes() }, icone('copiar', 13), 'Duplicar'),
      el('button', { class: 'btn peq', onclick: () => app.iniciarMoverLivre() }, icone('mover', 13), 'Mover (G)'),
      el('button', { class: 'btn peq', onclick: () => app.apontarLuzes(new THREE.Vector3()) }, icone('alvo', 13), 'Apontar p/ o centro'),
      el('button', { class: 'btn peq', onclick: () => {
        app.entrarModoLuz({ tipo: 'mirar', icone: 'alvo', msg: 'Clique no ponto para onde as luzes devem apontar',
          aoClicar: (d) => { const h = v.pontoNaCena(d.x, d.y); const sel = app.luzesSelecionadas(); app.sairModoLuz(); if (h && sel.length) app.apontarLuzes(h.ponto, sel); } });
      } }, icone('alvo', 13), 'Apontar para…'),
      el('button', { class: 'btn-perigo peq', onclick: () => app.excluirLuzes() }, icone('apagar', 13), 'Excluir')));
  };

  corpo.append(
    nota('Clique em <b>Adicionar com clique</b> e depois em qualquer lugar da vista (cobertura, viga, poste…): a luz nasce ali, encostada na superfície, copiando o <b>modelo</b> (tipo, cor, intensidade). Depois dá para arrastar com o gizmo ou o <kbd>G</kbd>, duplicar com <kbd>Ctrl+D</kbd> e apontar.'),
    el('h4', {}, 'Modelo das luzes novas'),
    el('div', { class: 'tex', style: { gridTemplateColumns: '1fr' } }, descModelo),
    el('div', { class: 'acoes-linha' }, usarSel, escolherTipo),
    avisoModelo,
    campoRotulado('Apontar para', seletor([['centro', 'O centro do campo'], ['baixo', 'Para baixo'], ['normal', 'Para fora da superfície'], ['modelo', 'Igual ao modelo']], P.mirar, (x) => { P.mirar = x; localStorage.setItem('editor.luzMirar', x); })),
    campoRotulado('Afastar da superfície (m)', num(P.afastar, (x) => { P.afastar = x; }, { passo: 0.05, casas: 2, passoCtrl: 0.5, min: 0 }).el),
    interruptor({ titulo: 'Reaproveitar luzes apagadas', descricao: 'Antes de criar, usa uma luz apagada (“Acesa no jogo” desligado) do mesmo tipo e arquivo — não cria entidade nova.', marcado: P.reaproveitar, aoMudar: (x) => { P.reaproveitar = x; } }).el,
    el('div', { class: 'acoes-linha' }, botaoAdd),
    secSel,
    nota('Luz nova = cópia da instância do modelo no mesmo arquivo, com GUID novo. Ainda não testado no jogo: comece com poucas.'));
  atualizarModelo();
  montarSel();
  const aoSel = () => { montarSel(); atualizarModelo(); };
  md.addEventListener('selecao', aoSel);
  md.addEventListener('jogo', aoSel);
  md.addEventListener('luz', montarSel);
  if (!v.mostrarLuzes) app.alternarLuzes(true);
  painelFlutuante({ titulo: 'Luzes', icone: 'luzMais', largura: 360, corpo,
    aoFechar: () => { md.removeEventListener('selecao', aoSel); md.removeEventListener('jogo', aoSel); md.removeEventListener('luz', montarSel); if (app.modoLuz) app.sairModoLuz(); } });
}

// ======================================================================== banco de reservas, área técnica, estádio no jogo
// Áreas técnicas do stadiums.txt: [minx, maxx, minz, maxz] em metros; "min" = lado do banco / longe do meio-campo.
export function zonaDoBanco(caixa) {
  const lado = Math.sign((caixa.min.z + caixa.max.z) / 2) || 1;
  const frente = lado > 0 ? caixa.min.z : caixa.max.z;          // borda do banco virada para o campo
  const zLonge = frente - lado * 0.35, zPerto = zLonge - lado * 3;
  const sx = Math.sign((caixa.min.x + caixa.max.x) / 2) || 1;
  const xa = caixa.min.x + 1, xb = caixa.max.x - 1;
  const [xLonge, xPerto] = sx > 0 ? [Math.max(xa, xb), Math.min(xa, xb)] : [Math.min(xa, xb), Math.max(xa, xb)];
  return [xLonge, xPerto, zLonge, zPerto].map((x) => Math.round(x * 100) / 100);
}

// assentos do banco (choreo_seat) distribuídos ao longo do banco, olhando para o campo
export function assentosNoBanco(caixa, n) {
  const lado = Math.sign((caixa.min.z + caixa.max.z) / 2) || 1;
  const frente = lado > 0 ? caixa.min.z : caixa.max.z;
  const z = frente + lado * 0.55, y = caixa.min.y + 0.0375;
  const x0 = caixa.min.x + 0.6, x1 = caixa.max.x - 0.6;
  const f = new THREE.Vector3(0, 0, -lado);                       // para onde o jogador sentado olha
  const r = f.clone().negate(), u = new THREE.Vector3(0, 1, 0);   // o eixo X do assento aponta para trás
  const fw = new THREE.Vector3().crossVectors(r, u);
  return Array.from({ length: n }, (_, i) => new THREE.Matrix4().makeBasis(r, u, fw)
    .setPosition(n > 1 ? x0 + (x1 - x0) * i / (n - 1) : (x0 + x1) / 2, y, z));
}

export function abrirBanco(app, aba = 'banco') {
  const md = app.modelo, v = app.viewport;
  if (v.espelhado) app.alternarEspelho(false);
  if (!v.mostrarPessoas) app.alternarPessoas(true);
  const corpo = el('div', { class: 'pf-sec' });
  const est = () => md.estadio?.atual;
  const assentos = () => md.nos.filter((n) => n.tipo === 'marcador' && n.categoria === 'choreo_seats' && n.alvo);
  const ladoDe = (n) => {
    const z = est()?.zonas;
    const p = new THREE.Vector3().setFromMatrixPosition(n.mundoM);
    if (!z?.casa || !z?.fora) return p.x >= 0 ? 'casa' : 'fora';
    const d = (k) => Math.hypot(p.x - (z[k][0] + z[k][1]) / 2, p.z - (z[k][2] + z[k][3]) / 2);
    return d('casa') <= d('fora') ? 'casa' : 'fora';
  };
  const caixaSelecao = () => {
    const ids = [...md.selecao].filter((i) => md.nos[i].tipo !== 'marcador' && md.nos[i].tipo !== 'luz');
    return ids.length ? v.caixaDe(ids) : null;
  };
  const ajustar = (lado) => {
    const c = caixaSelecao();
    if (!c || c.isEmpty()) { aviso('Selecione na vista o banco (a malha do banco) deste time', { tipo: 'aviso', detalhe: 'Clique no banco; com Shift dá para juntar mais de uma peça.' }); return; }
    const ss = assentos().filter((n) => ladoDe(n) === lado);
    const trios = [];
    if (ss.length) {
      const Ms = assentosNoBanco(c, ss.length);
      ss.sort((a, b) => a.mundoM.elements[12] - b.mundoM.elements[12]).forEach((n, i) => trios.push([n, n.local.slice(), md.localPara(n, Ms[i])]));
    }
    const zonas = JSON.parse(JSON.stringify(est()?.zonas || {}));
    zonas[lado] = zonaDoBanco(c);
    if (trios.length) app.confirmarLocais(trios, `Assentos do banco (${lado === 'casa' ? 'mandante' : 'visitante'})`);
    if (md.estadio) app.alterarEstadio({ zonas }, `Área técnica (${lado === 'casa' ? 'mandante' : 'visitante'})`);
    aviso(`Banco ${lado === 'casa' ? 'do mandante' : 'do visitante'} mapeado`, { tipo: 'sucesso',
      detalhe: `${trios.length} assentos dos reservas movidos para o banco${md.estadio ? ' e área técnica ajustada no stadiums.txt' : ''}. Salve (Ctrl+S) para gravar.` });
    montar();
  };
  const campoZona = (lado, i, rot) => num(est()?.zonas?.[lado]?.[i] ?? 0, (x, fim) => {
    const zonas = JSON.parse(JSON.stringify(est().zonas));
    zonas[lado][i] = x;
    app.alterarEstadio({ zonas }, 'Área técnica', fim ? null : `zona:${lado}:${i}`);
  }, { passo: 0.05, casas: 2, passoCtrl: 0.5, eixo: rot });

  const montar = () => {
    corpo.replaceChildren();
    const e = est();
    if (!md.estadio) corpo.append(nota('Não achei o <b>stadiums.txt</b> com este estádio (pasta do export, pasta acima ou a raiz do workspace). Sem ele dá para mover os assentos do banco, mas não a área técnica, o espelhamento e as medidas do campo.', 'alerta'));
    else corpo.append(el('small', { class: 'mudo' }, `stadiums.txt · estádio ${md.campo.id}${md.campo.nome ? ' — ' + md.campo.nome : ''}`));
    // --- banco
    corpo.append(el('h4', {}, 'Banco de reservas e área técnica'));
    corpo.append(nota('Os reservas sentam nos <b>assentos do banco</b> (coreografia) e o técnico fica na <b>área técnica</b> do stadiums.txt — não na malha do banco. Selecione o banco de um time na vista e clique em <b>Mapear</b>: os assentos vão para cima dele e a área técnica fica na frente.'));
    const ss = assentos();
    for (const [lado, rot, cor] of [['casa', 'Mandante', '#4c8dff'], ['fora', 'Visitante', '#ff5a5f']]) {
      const n = ss.filter((x) => ladoDe(x) === lado).length;
      corpo.append(el('div', { class: 'linha-prop' }, el('label', { html: `<span style="color:${cor}">■</span> ${rot}` }),
        el('div', { class: 'acoes-linha' }, el('small', { class: 'mudo' }, `${n} assentos`),
          el('button', { class: 'btn peq', onclick: () => ajustar(lado) }, icone('banco', 13), 'Mapear no banco selecionado'))));
      if (e?.zonas?.[lado]) {
        corpo.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Área (m)'),
          el('div', { class: 'grade-num' }, campoZona(lado, 0, 'x').el, campoZona(lado, 1, 'x').el, campoZona(lado, 2, 'z').el, campoZona(lado, 3, 'z').el)));
      }
    }
    corpo.append(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', onclick: () => md.selecionar(assentos().map((n) => n.id)) }, icone('selecao', 13), 'Selecionar os assentos'),
      el('button', { class: 'btn peq', onclick: () => app.focar(assentos().map((n) => n.id)) }, icone('alvo', 13), 'Enquadrar')));
    // --- estádio no jogo
    if (e) {
      corpo.append(el('h4', {}, 'Estádio no jogo'));
      corpo.append(interruptor({ titulo: 'Espelhado no jogo (ismirrored)', marcado: e.espelhado,
        descricao: 'Com 1, o jogo mostra o estádio espelhado em relação ao arquivo (as laterais trocam de lado). O 517 herdou 1 da linha do Events Rush (518). Se no jogo as peças aparecem invertidas ou deslocadas em relação ao editor, desligue.',
        aoMudar: (x) => app.alterarEstadio({ espelhado: x }, x ? 'Espelhar no jogo' : 'Não espelhar no jogo') }).el);
      if (e.espelhado) corpo.append(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => app.alternarEspelho() }, icone('espelho', 13), v.espelhado ? 'Voltar à edição' : 'Ver como no jogo')));
      corpo.append(campoRotulado('Comprimento (m)', num(e.comprimento, (x, fim) => app.alterarEstadio({ comprimento: x }, 'Comprimento do campo', fim ? null : 'campoC'), { passo: 0.1, casas: 2, passoCtrl: 1, min: 40, max: 130 }).el,
        'stadiumpitchlength: o jogo desenha as linhas com esta medida, centradas no meio do estádio'));
      corpo.append(campoRotulado('Largura (m)', num(e.largura, (x, fim) => app.alterarEstadio({ largura: x }, 'Largura do campo', fim ? null : 'campoL'), { passo: 0.1, casas: 2, passoCtrl: 1, min: 30, max: 100 }).el));
    }
    // --- pessoas da lateral
    corpo.append(el('h4', {}, 'Pessoas da lateral'));
    const cats = new Map();
    for (const n of md.nos) {
      if (n.tipo !== 'marcador' || n.categoria === 'choreo_seats' || !n.alvo) continue;
      const k = md.nos[n.pai]?.rotulo || n.categoria;
      cats.set(k, [...(cats.get(k) || []), n.id]);
    }
    const lista = el('div', { class: 'acoes-linha', style: { flexWrap: 'wrap' } });
    for (const [k, ids] of [...cats].sort((a, b) => b[1].length - a[1].length)) {
      lista.append(el('button', { class: 'btn peq', onclick: () => md.selecionar(ids) }, `${k} (${ids.length})`));
    }
    corpo.append(lista);
    let dist = 2;
    corpo.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Afastar do campo (m)'),
      el('div', { class: 'acoes-linha' }, num(dist, (x) => { dist = x; }, { passo: 0.1, casas: 1, passoCtrl: 1 }).el,
        el('button', { class: 'btn peq', onclick: () => afastar(dist) }, 'Aplicar às selecionadas'))));
    corpo.append(el('small', { class: 'mudo' }, 'Selecione um grupo (ex.: Fotógrafo) e afaste: cada pessoa anda para fora a partir da linha do campo mais próxima. Para posições exatas, use o G ou o gizmo.'));
  };
  const afastar = (d) => {
    const sel = [...md.selecao].map((i) => md.nos[i]).filter((n) => n.tipo === 'marcador' && n.alvo);
    if (!sel.length) { aviso('Selecione as pessoas que quer afastar', { tipo: 'aviso' }); return; }
    const C = (est()?.comprimento ?? md.campo.comprimento) / 2, L = (est()?.largura ?? md.campo.largura) / 2;
    const trios = sel.map((n) => {
      const p = new THREE.Vector3().setFromMatrixPosition(n.mundoM);
      const dx = Math.abs(p.x) - C, dz = Math.abs(p.z) - L;
      const dir = dx > dz ? new THREE.Vector3(Math.sign(p.x), 0, 0) : new THREE.Vector3(0, 0, Math.sign(p.z));
      const W = n.mundoM.clone().premultiply(new THREE.Matrix4().makeTranslation(dir.x * d, 0, dir.z * d));
      return [n, n.local.slice(), md.localPara(n, W)];
    });
    app.confirmarLocais(trios, `Afastar ${trios.length} pessoas ${d} m`);
  };
  montar();
  md.addEventListener('estadio', montar);
  painelFlutuante({ titulo: aba === 'estadio' ? 'Estádio no jogo e banco' : 'Banco, área técnica e pessoas', icone: 'banco', largura: 380, corpo,
    aoFechar: () => md.removeEventListener('estadio', montar) });
}
