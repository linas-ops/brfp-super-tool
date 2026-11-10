// Viewport 3D: monta os objetos do modelo, navegação de câmera, seleção, gizmo de transformação e modos de exibição.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { ViewHelper } from 'three/addons/helpers/ViewHelper.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { urlArquivo } from './api.js';
import { m12De } from './modelo.js';

const N_WORKERS = Math.max(2, Math.min(6, (navigator.hardwareConcurrency || 4) - 1));

class PoolFBX {
  constructor() {
    this.workers = [];
    this.fila = [];
    this.ocupados = new Map();
    this.seq = 0;
    for (let i = 0; i < N_WORKERS; i++) {
      const w = new Worker(new URL('./fbx-worker.js', import.meta.url), { type: 'module' });
      w.onmessage = (e) => this.resposta(w, e.data);
      w.onerror = (e) => { console.error(e); };
      this.workers.push(w);
    }
    this.livres = [...this.workers];
  }
  ler(url, buffer = null) {
    return new Promise((res, rej) => { this.fila.push({ url, buffer, res, rej }); this.bombear(); });
  }
  bombear() {
    while (this.livres.length && this.fila.length) {
      const w = this.livres.pop();
      const t = this.fila.shift();
      const id = ++this.seq;
      this.ocupados.set(w, { ...t, id });
      w.postMessage({ id, url: t.url, buffer: t.buffer }, t.buffer ? [t.buffer] : []);
    }
  }
  resposta(w, d) {
    const t = this.ocupados.get(w);
    this.ocupados.delete(w);
    this.livres.push(w);
    if (t) d.ok ? t.res(d.fbx) : t.rej(new Error(d.erro));
    this.bombear();
  }
  cancelar() { for (const t of this.fila) t.rej(new Error('cancelado')); this.fila = []; }
}

export class Viewport extends EventTarget {
  constructor(canvas, modelo, materiais) {
    super();
    this.canvas = canvas;
    this.modelo = modelo;
    this.mats = materiais;
    this.modo = 'material';
    this.ferramenta = 'selecionar';
    this.espaco = 'world';
    this.encaixe = false;
    this.mostrarOcultosJogo = true;
    this.mostrarSombras = false;
    this.mostrarFaltando = true;
    this.mostrarMalhasSombra = false;
    this.mostrarInvisiveis = true;      // peças com Visible=false no blueprint (shadow_seat, proxies de iluminação)
    this.velocidadeVoo = 25;
    this.mostrarLuzes = false;
    this.mostrarCampo = false;
    this.mostrarPessoas = false;
    this.ancoraEscala = 'chao';      // escala a partir do chão do campo (y = 0), da base do objeto ou do centro
    this.espelhado = false;          // pré-visualização do estádio espelhado como o jogo mostra (ismirrored = 1)
    this.shift = false;
    window.addEventListener('keydown', (e) => { if (e.key === 'Shift') this.shift = true; });
    window.addEventListener('keyup', (e) => { if (e.key === 'Shift') this.shift = false; });
    window.addEventListener('blur', () => { this.shift = false; });
    this.objs = [];          // id do nó -> THREE.Group
    this.geos = new Map();   // chave da malha -> {secoes, info} | promessa
    this.sobreposicoes = [];
    this.iso = null;
    this.sujo = true;
    this.pool = new PoolFBX();
    this.teclasVoo = new Set();

    const r = this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    r.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    r.setClearColor(0x000000, 0);
    r.autoClear = false;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.0;
    r.shadowMap.type = THREE.PCFSoftShadowMap;

    const cena = this.cena = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(r);
    cena.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    cena.environmentIntensity = 0.55;
    this.hemi = new THREE.HemisphereLight(0xe4ecf7, 0x3b3f45, 1.15);
    cena.add(this.hemi);
    const sol = this.sol = new THREE.DirectionalLight(0xfff4e6, 2.1);
    sol.position.set(120, 220, 90);
    sol.shadow.mapSize.set(4096, 4096);
    Object.assign(sol.shadow.camera, { left: -230, right: 230, top: 230, bottom: -230, near: 10, far: 700 });
    sol.shadow.bias = -0.0004;
    sol.shadow.normalBias = 0.6;
    cena.add(sol, sol.target);

    this.grade = new THREE.GridHelper(600, 60, 0x3d4652, 0x262b33);
    this.grade.position.y = -0.6;
    this.grade.material.transparent = true;
    this.grade.material.opacity = 0.6;
    cena.add(this.grade);

    this.raiz = new THREE.Group();
    this.raiz.name = 'raiz';
    cena.add(this.raiz);
    this.extras = new THREE.Group();
    this.raiz.add(this.extras);

    const cam = this.camera = new THREE.PerspectiveCamera(50, 1, 0.3, 5000);
    cam.position.set(140, 110, 170);

    this.instalarEntrada();
    const ctl = this.controles = new OrbitControls(cam, canvas);
    ctl.enableDamping = true;
    ctl.dampingFactor = 0.14;
    ctl.zoomToCursor = true;
    ctl.screenSpacePanning = true;
    ctl.maxDistance = 3000;
    ctl.minDistance = 0.5;
    ctl.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: -1 };
    ctl.addEventListener('change', () => { this.sujo = true; });

    const tc = this.gizmo = new TransformControls(cam, canvas);
    tc.setSize(1.15);
    tc.addEventListener('dragging-changed', (e) => { ctl.enabled = !e.value; e.value ? this.iniciarArrasto() : this.terminarArrasto(); });
    tc.addEventListener('objectChange', () => this.duranteArrasto());
    tc.addEventListener('change', () => { this.sujo = true; });
    this.pivo = new THREE.Object3D();
    cena.add(this.pivo);
    this.gizmoHelper = tc.getHelper();
    cena.add(this.gizmoHelper);

    this.ajudante = new ViewHelper(cam, canvas);
    this.ajudante.center = ctl.target;
    this.caixaSel = new THREE.Box3Helper(new THREE.Box3(), 0xff9233);
    this.caixaSel.visible = false;
    this.caixaSel.material.depthTest = false;
    this.caixaSel.material.transparent = true;
    this.caixaSel.material.opacity = 0.7;
    this.caixaSel.renderOrder = 10;
    cena.add(this.caixaSel);

    this.relogio = new THREE.Clock();
    this.fps = 0; this._quadros = 0; this._t0 = performance.now();
    new ResizeObserver(() => this.redimensionar()).observe(canvas.parentElement);
    this.redimensionar();
    this.loop();

    modelo.addEventListener('selecao', () => this.atualizarSelecao());
    modelo.addEventListener('locais', (e) => this.aoMudarLocais(e.detail.ids));
    modelo.addEventListener('jogo', (e) => this.aoMudarJogo(e.detail.ids));
    modelo.addEventListener('visEditor', () => this.atualizarVisibilidade());
    modelo.addEventListener('material', (e) => this.aoMudarMaterial(e.detail.variacao));
    modelo.addEventListener('estrutura', (e) => this.aoMudarEstrutura(e.detail));
    modelo.addEventListener('luz', (e) => this.aoMudarLuz(e.detail.ids));
  }

  // ------------------------------------------------------------------ ciclo
  redimensionar() {
    const p = this.canvas.parentElement;
    const w = p.clientWidth, h = p.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.sujo = true;
  }

  loop() {
    requestAnimationFrame(() => this.loop());
    const dt = Math.min(this.relogio.getDelta(), 0.1);
    let mudou = this.controles.update(dt);
    if (this.voando || this.teclasVoo.size) mudou = this.passoVoo(dt) || mudou;
    if (this.ajudante.animating) { this.ajudante.update(dt); mudou = true; }
    if (this.animacao) { this.animacao(dt); mudou = true; }
    if (mudou || this.sujo) this.render();
    else if (this.fps && performance.now() - this._t0 > 1200) {
      this.fps = 0; this._quadros = 0; this._t0 = performance.now();
      this.dispatchEvent(new CustomEvent('fps', { detail: 0 }));
    }
  }

  render() {
    this.sujo = false;
    const r = this.renderer;
    r.clear();
    r.render(this.cena, this.camera);
    this.ajudante.render(r);
    this._quadros++;
    const agora = performance.now();
    if (agora - this._t0 > 1000) {
      this.fps = Math.round(this._quadros * 1000 / (agora - this._t0));
      this._quadros = 0; this._t0 = agora;
      this.dispatchEvent(new CustomEvent('fps', { detail: this.fps }));
    }
  }

  // ------------------------------------------------------------------ construção
  limpar() {
    this.pool.cancelar();
    this.gizmo.detach();
    for (const o of this.sobreposicoes) o.removeFromParent();
    this.sobreposicoes = [];
    this.raiz.clear();
    this.extras = new THREE.Group();
    this.raiz.add(this.extras);
    for (const g of this.geos.values()) if (g && g.secoes) g.secoes.forEach((s) => s.geometria.dispose());
    this.geos.clear();
    this.objs = [];
    this.iso = null;
    this.torcida = null;
    this.sujo = true;
  }

  async construir(aoProgresso) {
    this.limpar();
    const nos = this.modelo.nos;
    const geoMarcador = this.geoMarcador = this.geoMarcador || new THREE.OctahedronGeometry(0.3, 0);
    for (const n of nos) {
      const g = new THREE.Group();
      g.matrixAutoUpdate = false;
      g.matrix.copy(n.localM);
      g.userData.no = n.id;
      const pecas = new THREE.Group();
      pecas.userData.pecas = true;
      g.add(pecas);
      g.userData.pecasObj = pecas;
      (n.pai >= 0 ? this.objs[n.pai] : this.raiz).add(g);
      this.objs[n.id] = g;
      if (n.tipo === 'luz') this.criarMarcadorLuz(n, pecas);
      if (n.tipo === 'marcador') this.criarMarcadorPessoa(n, pecas);
      if (n.faltando === 'blueprint' && !(n.malhas && n.malhas.length)) {
        const m = new THREE.Mesh(geoMarcador, this.mats.marcador);
        m.userData = { no: n.id, marcador: true };
        pecas.add(m);
      }
    }
    this.raiz.updateMatrixWorld(true);
    // malhas: uma leitura de FBX por malha, compartilhada por todas as cópias
    const usos = new Map();
    nos.forEach((n) => (n.malhas || []).forEach((p, i) => {
      if (!usos.has(p.m)) usos.set(p.m, []);
      usos.get(p.m).push([n, p, i]);
    }));
    const lista = [...usos.keys()];
    let feitos = 0, bytes = 0;
    const total = lista.filter((k) => this.modelo.malhas[k]?.fbx).length;
    const erros = [];
    await Promise.all(lista.map(async (k) => {
      const info = this.modelo.malhas[k];
      if (!info?.fbx) {
        for (const [n, p] of usos.get(k)) this.criarSubstituto(n, p, info);
        return;
      }
      try {
        const fbx = await this.pool.ler(new URL(urlArquivo(info.fbx), location.href).href);
        const geo = this.criarGeometrias(fbx);
        this.geos.set(k, geo);
        for (const [n, p, i] of usos.get(k)) this.criarPeca(n, p, i, geo);
      } catch (err) {
        if (err.message === 'cancelado') return;
        erros.push(`${info.nome}: ${err.message}`);
        for (const [n, p] of usos.get(k)) this.criarSubstituto(n, p, info);
      }
      feitos++;
      aoProgresso && aoProgresso(feitos, total, info.nome);
      this.sujo = true;
    }));
    this.raiz.updateMatrixWorld(true);
    this.atualizarVisibilidade();
    this.aplicarModo();
    this.aplicarSombras();
    this.limiteCena = new THREE.Box3().setFromObject(this.raiz);
    return { erros, malhas: total };
  }

  criarMarcadorLuz(n, pecas) {
    const L = n.luz || {};
    if (!this.geoLuz) {
      this.geoLuz = {
        spot: new THREE.ConeGeometry(0.45, 1.1, 10, 1, true).rotateX(-Math.PI / 2).translate(0, 0, 0.55),
        esfera: new THREE.IcosahedronGeometry(0.35, 1),
        tubo: new THREE.CapsuleGeometry(0.15, 0.9, 3, 8).rotateZ(Math.PI / 2),
        retangulo: new THREE.PlaneGeometry(0.9, 0.6),
      };
      this.matsLuz = new Map();
    }
    const c = new THREE.Color(...(L.cor || [1, 1, 1]));
    const hex = c.getHexString();
    if (!this.matsLuz.has(hex)) {
      const cor = c.clone();
      const hsl = {}; cor.getHSL(hsl);
      cor.setHSL(hsl.h, Math.min(1, hsl.s + 0.2), Math.max(0.55, hsl.l));
      this.matsLuz.set(hex, new THREE.MeshBasicMaterial({ color: cor, wireframe: false, transparent: true, opacity: 0.9, side: THREE.DoubleSide }));
    }
    const m = new THREE.Mesh(this.geoLuz[L.tipo] || this.geoLuz.esfera, this.matsLuz.get(hex));
    m.userData = { no: n.id, luz: true };
    m.matrixAutoUpdate = false;
    pecas.add(m);
    m.updateMatrix();
  }

  // pessoas da lateral e assentos do banco: boneco (ou assento) com a cor da função; seta = para onde olha
  criarMarcadorPessoa(n, pecas) {
    if (!this.geoPessoa) {
      this.geoPessoa = {
        corpo: new THREE.CapsuleGeometry(0.22, 1.1, 3, 8).translate(0, 0.77, 0),
        assento: new THREE.BoxGeometry(0.46, 0.45, 0.46).translate(0, 0.225, 0),
        seta: new THREE.ConeGeometry(0.12, 0.4, 8).rotateZ(Math.PI / 2).translate(-0.42, 0.55, 0),   // -X local = frente do assento
      };
      this.matsPessoa = new Map();
    }
    const CORES = { choreo_seats: 0xffb020, slc_police: 0x3d7bff, slc_steward: 0xf5d90a, slc_photographer: 0xb8bec8, slc_ballboy: 0x37c26b,
      slc_camera_handheld: 0xa66bff, slc_camera_sitting: 0xa66bff, slc_camera_standing: 0xa66bff, slc_medicalofficer: 0xff4d4d,
      slc_generic: 0xffffff, slc_tournamentofficial: 0xff8ad8, slc_managerhome: 0x2ad4d4, slc_manageraway: 0x2ad4d4,
      slc_assistantmanagerhome: 0x2ad4d4, slc_assistantmanageraway: 0x2ad4d4 };
    const cor = CORES[n.categoria] ?? 0xffffff;
    if (!this.matsPessoa.has(cor)) this.matsPessoa.set(cor, new THREE.MeshBasicMaterial({ color: cor, transparent: true, opacity: 0.92 }));
    const mat = this.matsPessoa.get(cor);
    const banco = n.categoria === 'choreo_seats';
    for (const geo of banco ? [this.geoPessoa.assento, this.geoPessoa.seta] : [this.geoPessoa.corpo]) {
      const m = new THREE.Mesh(geo, mat);
      m.userData = { no: n.id, pessoa: true };
      m.matrixAutoUpdate = false;
      pecas.add(m);
      m.updateMatrix();
    }
  }

  // nós criados depois da carga (luzes novas) e nós removidos (desfazer da criação, luzes excluídas)
  aoMudarEstrutura({ adicionados = [] } = {}) {
    for (const id of adicionados) {
      if (this.objs[id]) continue;
      const n = this.modelo.nos[id];
      const g = new THREE.Group();
      g.matrixAutoUpdate = false;
      g.matrix.copy(n.localM);
      g.userData.no = id;
      const pecas = new THREE.Group();
      pecas.userData.pecas = true;
      g.add(pecas);
      g.userData.pecasObj = pecas;
      (n.pai >= 0 ? this.objs[n.pai] : this.raiz).add(g);
      this.objs[id] = g;
      if (n.tipo === 'luz') this.criarMarcadorLuz(n, pecas);
      if (n.tipo === 'marcador') this.criarMarcadorPessoa(n, pecas);
      g.updateMatrixWorld(true);
    }
    this.atualizarVisibilidade();
    this.atualizarSelecao();
  }

  aoMudarLuz(ids) {
    for (const id of ids) {
      const g = this.objs[id];
      if (!g) continue;
      const pecas = g.userData.pecasObj;
      for (const m of [...pecas.children]) if (m.userData.luz) m.removeFromParent();
      this.criarMarcadorLuz(this.modelo.nos[id], pecas);
    }
    this.atualizarSelecao();
    this.sujo = true;
  }

  criarGeometrias(fbx) {
    const secoes = fbx.secoes.map((s) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(s.posicoes, 3));
      if (s.normal) g.setAttribute('normal', new THREE.BufferAttribute(s.normal, 3));
      if (s.uv0) g.setAttribute('uv', new THREE.BufferAttribute(s.uv0, 2));
      if (s.indices) g.setIndex(new THREE.BufferAttribute(s.indices, 1));
      if (!s.normal) g.computeVertexNormals();
      g.computeBoundingBox();
      g.computeBoundingSphere();
      return { nome: s.nome, sombra: s.sombra, geometria: g, triangulos: s.triangulos, vertices: s.vertices, nomesUV: s.nomesUV };
    });
    return { secoes, lods: fbx.lods, ossos: fbx.ossos };
  }

  // material de exibição de cada seção: MVDB do sub-mundo (pelo GUID do material da malha) ou o do XML da malha
  registroSecoes(n, chave, geo) {
    const { lista, xml, mvdb } = this.modelo.materiaisDe(n, chave);
    const outroMvdb = !!lista && mvdb !== n.mvdb;
    // o MVDB liga cada material à partição (MeshMaterial) da malha pelo GUID; partição nova (seção acrescentada ao
    // FBX e importada no FET) não tem material na entrada. Só cai na ordem quando os GUIDs não batem em nada.
    const g = (x) => String(x || '').toLowerCase();
    const guidsXml = new Set(xml.map((x) => g(x.guid)).filter(Boolean));
    const porGuid = !!lista && lista.some((m) => guidsXml.has(g(m.material)));
    const out = [];
    let k = 0;
    for (const s of geo.secoes) {
      if (s.sombra) { out.push(null); continue; }
      const xg = g(xml[k]?.guid);
      let mv = null;
      if (lista) mv = porGuid ? (xg ? lista.find((m) => g(m.material) === xg) : null) : lista[k];
      const reg = mv?.variacao ? this.modelo.materiais.get(mv.variacao) : null;
      out.push({ indice: k, chave: mv?.variacao || `${chave}|${k}`, reg: reg || { info: mv || xml[k] || {} }, editavel: !!reg, outroMvdb,
        particaoNova: !!lista && !mv, semGuid: !xml[k], particaoNula: !!xml[k] && !xg });
      k++;
    }
    return out;
  }

  criarPeca(n, p, i, geo) {
    const pg = new THREE.Group();
    pg.matrixAutoUpdate = false;
    const t = p.t;
    pg.matrix.set(t[0], t[3], t[6], t[9], t[1], t[4], t[7], t[10], t[2], t[5], t[8], t[11], 0, 0, 0, 1);
    pg.userData = { no: n.id, peca: i, malha: p.m };
    const regs = this.registroSecoes(n, p.m, geo);
    geo.secoes.forEach((s, si) => {
      const reg = regs[si];
      const mat = reg ? this.mats.material(reg.chave, reg.reg, s.nome) : this.mats.solido;
      const m = new THREE.Mesh(s.geometria, mat);
      m.matrixAutoUpdate = false;
      m.userData = { no: n.id, peca: i, malha: p.m, secao: si, sombra: s.sombra, chaveMat: reg?.chave, reg: reg?.reg, nomeSecao: s.nome,
        invisivel: !!p.oculta };
      m.userData.matReal = mat;
      m.visible = !s.sombra || this.mostrarMalhasSombra;
      pg.add(m);
    });
    if (p.oculta) pg.userData.ocultaBlueprint = true;
    this.objs[n.id].userData.pecasObj.add(pg);
    pg.updateMatrixWorld(true);
  }

  criarSubstituto(n, p, info) {
    const pecas = this.objs[n.id].userData.pecasObj;
    const pg = new THREE.Group();
    pg.matrixAutoUpdate = false;
    pg.userData = { no: n.id, substituto: true, malha: p.m };
    const t = p.t;
    pg.matrix.set(t[0], t[3], t[6], t[9], t[1], t[4], t[7], t[10], t[2], t[5], t[8], t[11], 0, 0, 0, 1);
    if (info?.caixa) {
      const [lo, hi] = info.caixa;
      const tam = new THREE.Vector3(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]).max(new THREE.Vector3(0.05, 0.05, 0.05));
      const geo = new THREE.BoxGeometry(tam.x, tam.y, tam.z);
      geo.translate((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2);
      const m = new THREE.Mesh(geo, this.mats.faltando);
      m.userData = { no: n.id, substituto: true, malha: p.m };
      const linhas = new THREE.LineSegments(new THREE.EdgesGeometry(geo), this.mats.faltandoLinha);
      linhas.userData = { no: n.id, substituto: true, linha: true };
      pg.add(m, linhas);
    } else {
      const m = new THREE.Mesh(this.geoMarcador, this.mats.marcador);
      m.userData = { no: n.id, marcador: true, malha: p.m };
      pg.add(m);
    }
    pecas.add(pg);
    pg.updateMatrixWorld(true);
  }

  async recarregarMalha(chave, buffer = null) {
    const info = this.modelo.malhas[chave];
    const url = new URL(urlArquivo(info.fbx) + '&t=' + Date.now(), location.href).href;
    const fbx = await this.pool.ler(url, buffer);
    const antigo = this.geos.get(chave);
    const geo = this.criarGeometrias(fbx);
    this.geos.set(chave, geo);
    for (const n of this.modelo.nos) {
      (n.malhas || []).forEach((p, i) => {
        if (p.m !== chave) return;
        const pecas = this.objs[n.id].userData.pecasObj;
        for (const pg of [...pecas.children]) if (pg.userData.peca === i) pg.removeFromParent();
        this.criarPeca(n, p, i, geo);
      });
    }
    if (antigo?.secoes) antigo.secoes.forEach((s) => s.geometria.dispose());
    this.atualizarVisibilidade();
    this.aplicarModo();
    this.atualizarSelecao();
  }

  // ------------------------------------------------------------------ aparência
  definirModo(modo) { this.modo = modo; this.aplicarModo(); }

  aplicarModo() {
    const fantasmas = new Set();
    if (this.mostrarOcultosJogo) {
      for (const n of this.modelo.nos) if (this.modelo.ocultoNoJogoProprio(n)) this.modelo.descendentes(n).forEach((d) => fantasmas.add(d.id));
    }
    this.raiz.traverse((o) => {
      if (!o.isMesh || o.userData.overlay) return;
      const u = o.userData;
      if (u.marcador || u.substituto || u.luz || u.pessoa) return;
      let m;
      if (fantasmas.has(u.no)) m = this.mats.fantasma;
      else if (u.invisivel && this.modo !== 'arame') m = this.mats.invisivel;
      else if (this.modo === 'solido') m = (u.matReal?.userData?.classe === 'vidro' || u.matReal?.userData?.classe === 'recorte') ? this.mats.solidoVidro : this.mats.solido;
      else if (this.modo === 'arame') m = this.mats.arame;
      else if (this.modo === 'raiox') m = this.mats.raiox;
      else m = u.matReal;
      o.material = m;
      o.castShadow = this.mostrarSombras && this.modo !== 'raiox' && m === u.matReal;
      o.receiveShadow = this.mostrarSombras;
    });
    this.grade.visible = this.modo !== 'raiox' && this.mostrarGrade !== false;
    this.sujo = true;
  }

  recriarMateriais() {
    this.raiz.traverse((o) => {
      if (!o.isMesh || !o.userData.chaveMat) return;
      o.userData.matReal = this.mats.material(o.userData.chaveMat, o.userData.reg, o.userData.nomeSecao);
    });
    this.aplicarModo();
  }

  aoMudarMaterial(variacao) {
    this.mats.invalidar(variacao);
    this.raiz.traverse((o) => {
      if (o.isMesh && o.userData.chaveMat === variacao) o.userData.matReal = this.mats.material(variacao, o.userData.reg, o.userData.nomeSecao);
    });
    this.aplicarModo();
  }

  definirSombras(v) {
    this.mostrarSombras = v;
    this.renderer.shadowMap.enabled = v;
    this.aplicarSombras();
  }

  aplicarSombras() {
    this.sol.castShadow = this.mostrarSombras;
    this.renderer.shadowMap.needsUpdate = true;
    this.aplicarModo();
    this.raiz.traverse((o) => { if (o.material) o.material.needsUpdate = true; });
  }

  atualizarVisibilidade() {
    const md = this.modelo;
    const iso = this.iso;
    for (const n of md.nos) {
      const g = this.objs[n.id];
      if (!g) continue;
      let vis = n.visEditor && !n.removido && !(md.ocultoNoJogoProprio(n) && !this.mostrarOcultosJogo) && (n.tipo !== 'luz' || this.mostrarLuzes)
        && (n.tipo !== 'marcador' || this.mostrarPessoas);
      if (iso) vis = vis && (iso.manter.has(n.id) || iso.ancestrais.has(n.id));
      g.visible = vis;
      const pecas = g.userData.pecasObj;
      pecas.visible = !iso || iso.manter.has(n.id);
      for (const pg of pecas.children) {
        if (pg.userData.substituto || pg.userData.marcador) pg.visible = this.mostrarFaltando;
        else if (pg.userData.ocultaBlueprint) pg.visible = this.mostrarInvisiveis;
      }
    }
    this.raiz.traverse((o) => {
      if (o.isMesh && o.userData.sombra) o.visible = this.mostrarMalhasSombra;
    });
    this.sujo = true;
  }

  isolar(ids) {
    if (!ids || !ids.length) { this.iso = null; this.atualizarVisibilidade(); return; }
    const manter = new Set(), ancestrais = new Set();
    for (const id of ids) {
      const n = this.modelo.nos[id];
      this.modelo.descendentes(n).forEach((d) => manter.add(d.id));
      this.modelo.ancestrais(n).forEach((a) => ancestrais.add(a.id));
    }
    this.iso = { manter, ancestrais, ids };
    this.atualizarVisibilidade();
  }

  aoMudarLocais(ids) {
    for (const id of ids) {
      const n = this.modelo.nos[id];
      const g = this.objs[id];
      if (g) { g.matrix.copy(n.localM); g.updateMatrixWorld(true); }
    }
    this.atualizarCaixaSelecao();
    this.posicionarPivo();
    this.sujo = true;
  }

  aoMudarJogo() {
    this.atualizarVisibilidade();
    this.aplicarModo();
    this.aoMudarLocais(this.modelo.nos.filter((n) => n.jogo).map((n) => n.id));
  }

  // ------------------------------------------------------------------ seleção
  atualizarSelecao() {
    for (const o of this.sobreposicoes) o.removeFromParent();
    this.sobreposicoes = [];
    const sel = this.modelo.selecao;
    let total = 0;
    for (const id of sel) {
      const g = this.objs[id];
      if (!g) continue;
      g.traverse((o) => {
        if (total > 6000) return;
        if ((o.isMesh) && !o.userData.overlay && !o.userData.sombra && o.geometry) {
          const s = new THREE.Mesh(o.geometry, this.mats.selecao);
          s.userData.overlay = true;
          s.matrixAutoUpdate = false;
          s.raycast = () => {};
          s.renderOrder = 5;
          o.add(s);
          s.updateMatrixWorld(true);
          this.sobreposicoes.push(s);
          total++;
        }
      });
    }
    this.atualizarCaixaSelecao();
    this.atualizarGizmo();
    this.sujo = true;
  }

  caixaDe(ids) {
    const caixa = new THREE.Box3();
    const tmp = new THREE.Box3();
    for (const id of ids) {
      const g = this.objs[id];
      if (!g) continue;
      g.updateMatrixWorld(true);
      g.traverse((o) => {
        if (o.userData.overlay || !o.geometry || (o.userData.sombra && !this.mostrarMalhasSombra)) return;
        if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
        tmp.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld);
        caixa.union(tmp);
      });
      if (caixa.isEmpty()) {
        const p = new THREE.Vector3().setFromMatrixPosition(g.matrixWorld);
        caixa.expandByPoint(p);
      }
    }
    return caixa;
  }

  atualizarCaixaSelecao() {
    const sel = [...this.modelo.selecao];
    if (!sel.length) { this.caixaSel.visible = false; return; }
    const c = this.caixaDe(sel);
    if (c.isEmpty()) { this.caixaSel.visible = false; return; }
    this.caixaSel.box.copy(c).expandByScalar(0.05);
    this.caixaSel.visible = true;
    this.sujo = true;
  }

  // nós que de fato se movem com o gizmo: editáveis, sem ancestral também na lista, uma cópia por alvo
  nosMoveis() {
    const md = this.modelo;
    const out = [];
    const chaves = new Set();
    const adicionar = (n) => {
      if (n.alvo) {
        if (chaves.has(n.chave)) return;
        chaves.add(n.chave);
        out.push(n);
      } else {
        for (const f of n.filhos) adicionar(md.nos[f]);
      }
    };
    for (const id of md.selecao) adicionar(md.nos[id]);
    const ids = new Set(out.map((n) => n.id));
    return out.filter((n) => !md.ancestrais(n).some((a) => ids.has(a.id)));
  }

  definirFerramenta(f) {
    this.ferramenta = f;
    this.atualizarGizmo();
  }

  atualizarGizmo() {
    const moveis = this.ferramenta !== 'selecionar' && !this.espelhado ? this.nosMoveis() : [];
    if (!moveis.length) { this.gizmo.detach(); this.sujo = true; return; }
    this.gizmo.setMode({ mover: 'translate', girar: 'rotate', escala: 'scale' }[this.ferramenta]);
    this.gizmo.setSpace(this.ferramenta === 'escala' ? 'local' : this.espaco);
    this.aplicarEncaixe();
    this.posicionarPivo();
    if (this.gizmo.object !== this.pivo) this.gizmo.attach(this.pivo);
    this.sujo = true;
  }

  aplicarEncaixe(forcado) {
    const on = forcado ?? this.encaixe;
    this.gizmo.setTranslationSnap(on ? 0.5 : null);
    this.gizmo.setRotationSnap(on ? THREE.MathUtils.degToRad(15) : null);
    this.gizmo.setScaleSnap(on ? 0.1 : null);
  }

  posicionarPivo() {
    if (this.arrastando) return;
    const moveis = this.nosMoveis();
    if (!moveis.length) return;
    const c = this.caixaDe(moveis.map((n) => n.id));
    const centro = c.isEmpty() ? new THREE.Vector3() : c.getCenter(new THREE.Vector3());
    if (moveis.length === 1) {
      // um objeto: pivô na origem dele se ela estiver perto; senão no centro da caixa
      const g = this.objs[moveis[0].id];
      const o = new THREE.Vector3().setFromMatrixPosition(g.matrixWorld);
      if (!c.isEmpty() && c.distanceToPoint(o) < 2) centro.copy(o);
      const q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3();
      g.matrixWorld.decompose(p, q, s);
      this.pivo.quaternion.copy(q);
    } else this.pivo.quaternion.identity();
    if (this.ferramenta === 'escala' && !c.isEmpty()) {
      // escala ancorada: o chão do estádio continua no chão do campo (y = 0)
      if (this.ancoraEscala === 'chao') centro.y = 0;
      else if (this.ancoraEscala === 'base') centro.y = c.min.y;
      else if (this.ancoraEscala === 'centro') c.getCenter(centro);
    }
    this.pivo.position.copy(centro);
    this.pivo.scale.set(1, 1, 1);
    this.pivo.updateMatrixWorld(true);
  }

  iniciarArrasto() {
    this.arrastando = true;
    this.moveis = this.nosMoveis();
    this.pivo.updateMatrixWorld(true);
    this.pivoInicioInv = this.pivo.matrixWorld.clone().invert();
    this.inicio = this.moveis.map((n) => ({ n, mundo: this.objs[n.id].matrixWorld.clone(), local: n.local.slice() }));
  }

  duranteArrasto() {
    if (!this.arrastando) return;
    if (this.gizmo.mode === 'scale' && this.shift) {
      // Shift: o mesmo fator nos três eixos (usa o eixo que mais mudou)
      const s = this.pivo.scale;
      const f = [s.x, s.y, s.z].reduce((a, v) => (Math.abs(v - 1) > Math.abs(a - 1) ? v : a), 1);
      s.set(f, f, f);
    }
    this.pivo.updateMatrixWorld(true);
    const delta = new THREE.Matrix4().multiplyMatrices(this.pivo.matrixWorld, this.pivoInicioInv);
    for (const it of this.inicio) {
      const g = this.objs[it.n.id];
      const paiInv = g.parent.matrixWorld.clone().invert();
      const novo = new THREE.Matrix4().multiplyMatrices(delta, it.mundo).premultiply(paiInv);
      const local = m12De(novo);
      for (const id of this.modelo.porAlvo.get(it.n.chave) || [it.n.id]) {
        const n = this.modelo.nos[id];
        n.local = local;
        n.localM.copy(novo);
        const go = this.objs[id];
        go.matrix.copy(novo);
        go.updateMatrixWorld(true);
      }
    }
    this.atualizarCaixaSelecao();
    this.dispatchEvent(new CustomEvent('arrastando'));
  }

  terminarArrasto() {
    if (!this.arrastando) return;
    this.arrastando = false;
    const antes = new Map(), depois = new Map();
    for (const it of this.inicio) {
      const k = this.modelo.chaveDe(it.n);
      antes.set(k, it.local);
      depois.set(k, it.n.local.slice());
    }
    const mudou = this.inicio.some((it) => it.local.some((v, i) => Math.abs(v - it.n.local[i]) > 1e-7));
    for (const it of this.inicio) this.modelo.calcularMundos(it.n.id);
    if (mudou) {
      const nome = { translate: 'Mover', rotate: 'Girar', scale: 'Redimensionar' }[this.gizmo.mode];
      this.dispatchEvent(new CustomEvent('transformado', { detail: { antes, depois, nome: `${nome} ${this.inicio.length > 1 ? this.inicio.length + ' objetos' : this.inicio[0].n.nome}` } }));
    }
    this.posicionarPivo();
  }

  // ------------------------------------------------------------------ entrada (mouse/teclado)
  instalarEntrada() {
    const c = this.canvas;
    const ray = this.raycaster = new THREE.Raycaster();
    const ndc = (e) => {
      const r = c.getBoundingClientRect();
      return new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    };
    this.ndc = ndc;
    let baixo = null;
    c.addEventListener('pointerdown', (e) => {
      c.focus({ preventScroll: true });
      this.esconderHover();
      if (this.livre) {
        e.preventDefault(); e.stopImmediatePropagation();
        this.terminarLivre(e.button === 0);
        return;
      }
      if (e.button === 2) {
        e.stopImmediatePropagation();
        this.voando = { x: e.clientX, y: e.clientY };
        c.setPointerCapture(e.pointerId);
        return;
      }
      if (e.button !== 0) return;
      if (this.gizmo.axis !== null && this.gizmo.object) { baixo = null; return; }
      if (e.ctrlKey || this.ferramentaCaixa) {
        e.stopImmediatePropagation();
        this.caixaArrasto = { x: e.clientX, y: e.clientY, shift: e.shiftKey, ctrl: e.ctrlKey };
        c.setPointerCapture(e.pointerId);
        return;
      }
      baixo = { x: e.clientX, y: e.clientY, t: performance.now() };
    });
    c.addEventListener('pointermove', (e) => {
      if (this.livre) { this.moverLivre(e); return; }
      if (this.voando) {
        const dx = e.clientX - this.voando.x, dy = e.clientY - this.voando.y;
        this.voando.x = e.clientX; this.voando.y = e.clientY;
        this.olhar(dx, dy);
        return;
      }
      if (this.caixaArrasto) { this.desenharCaixa(e); return; }
      if (!e.buttons) this.agendarHover(e);
    });
    c.addEventListener('pointerup', (e) => {
      if (e.button === 2 && this.voando) {
        this.voando = null;
        this.teclasVoo.clear();
        c.releasePointerCapture(e.pointerId);
        return;
      }
      if (this.caixaArrasto) { this.finalizarCaixa(e); c.releasePointerCapture(e.pointerId); return; }
      if (e.button !== 0 || !baixo) return;
      const moveu = Math.hypot(e.clientX - baixo.x, e.clientY - baixo.y);
      baixo = null;
      if (moveu > 4) return;
      const alvo = this.escolher(ndc(e));
      this.dispatchEvent(new CustomEvent('clique', { detail: { id: alvo ? alvo.no : -1, shift: e.shiftKey, ctrl: e.ctrlKey, alt: e.altKey, duplo: false, objeto: alvo, x: e.clientX, y: e.clientY } }));
    });
    c.addEventListener('dblclick', (e) => {
      const alvo = this.escolher(ndc(e));
      this.dispatchEvent(new CustomEvent('clique', { detail: { id: alvo ? alvo.no : -1, duplo: true, objeto: alvo } }));
    });
    c.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('pointermove', (e) => { this.ultimoMouse = { x: e.clientX, y: e.clientY }; if (this.livre && e.target !== c) this.moverLivre(e); });
    c.addEventListener('pointerleave', () => this.esconderHover());
    c.addEventListener('wheel', (e) => {
      if (this.voando) {
        e.preventDefault(); e.stopImmediatePropagation();
        this.velocidadeVoo = THREE.MathUtils.clamp(this.velocidadeVoo * (e.deltaY < 0 ? 1.25 : 0.8), 2, 400);
        this.dispatchEvent(new CustomEvent('velocidade', { detail: this.velocidadeVoo }));
      }
    }, { capture: true, passive: false });
  }

  olhar(dx, dy) {
    const cam = this.camera, ctl = this.controles;
    const dist = Math.max(cam.position.distanceTo(ctl.target), 1);
    const esf = new THREE.Spherical();
    const dir = new THREE.Vector3().subVectors(ctl.target, cam.position).normalize();
    esf.setFromVector3(dir);
    esf.theta -= dx * 0.0035;
    esf.phi = THREE.MathUtils.clamp(esf.phi + dy * 0.0035, 0.02, Math.PI - 0.02);
    dir.setFromSpherical(esf);
    ctl.target.copy(cam.position).addScaledVector(dir, dist);
    cam.lookAt(ctl.target);
    this.sujo = true;
  }

  passoVoo(dt) {
    if (!this.voando || !this.teclasVoo.size) return false;
    const cam = this.camera, ctl = this.controles;
    const frente = new THREE.Vector3().subVectors(ctl.target, cam.position).normalize();
    const direita = new THREE.Vector3().crossVectors(frente, cam.up).normalize();
    const mov = new THREE.Vector3();
    const k = this.teclasVoo;
    if (k.has('w')) mov.add(frente);
    if (k.has('s')) mov.sub(frente);
    if (k.has('d')) mov.add(direita);
    if (k.has('a')) mov.sub(direita);
    if (k.has('e')) mov.y += 1;
    if (k.has('q')) mov.y -= 1;
    if (!mov.lengthSq()) return false;
    mov.normalize().multiplyScalar(this.velocidadeVoo * dt * (k.has('shift') ? 3 : 1));
    cam.position.add(mov);
    ctl.target.add(mov);
    return true;
  }

  // objetos pegáveis = malhas visíveis (considerando os pais)
  pegaveis() {
    const out = [];
    this.raiz.traverseVisible((o) => {
      if ((o.isMesh || o.isLineSegments) && !o.userData.overlay && !o.userData.linha && o.userData.no !== undefined) out.push(o);
      if (o.isPoints && o.userData.torcida) out.push(o);
    });
    return out;
  }

  escolher(ndc) {
    this.raycaster.setFromCamera(ndc, this.camera);
    this.raycaster.params.Points.threshold = 0.4;
    const hits = this.raycaster.intersectObjects(this.pegaveis(), false);
    const h = hits.find((x) => !(x.object.material && x.object.material.opacity < 0.1 && this.modo !== 'raiox'));
    if (!h) return null;
    if (h.object.userData.torcida) return { no: -1, torcida: true, indice: h.index, ponto: h.point };
    return { no: h.object.userData.no, objeto: h.object, ponto: h.point, secao: h.object.userData.secao };
  }

  agendarHover(e) {
    clearTimeout(this._hover);
    const rot = document.getElementById('rotulo-hover');
    rot.hidden = true;
    this._hover = setTimeout(() => {
      const alvo = this.escolher(this.ndc(e));
      if (!alvo || alvo.torcida) { rot.hidden = true; return; }
      const n = this.modelo.nos[alvo.no];
      const sec = alvo.objeto?.userData?.nomeSecao;
      rot.innerHTML = `${n.rotulo.replace(/</g, '&lt;')}${sec ? `<small>${sec.replace(/</g, '&lt;')}</small>` : ''}`;
      const r = this.canvas.getBoundingClientRect();
      rot.style.left = (e.clientX - r.left) + 'px';
      rot.style.top = (e.clientY - r.top) + 'px';
      rot.hidden = false;
    }, 260);
  }

  esconderHover() {
    clearTimeout(this._hover);
    document.getElementById('rotulo-hover').hidden = true;
  }

  desenharCaixa(e) {
    const r = this.canvas.getBoundingClientRect();
    const a = this.caixaArrasto;
    const x0 = Math.min(a.x, e.clientX) - r.left, y0 = Math.min(a.y, e.clientY) - r.top;
    const caixa = document.getElementById('caixa-selecao');
    Object.assign(caixa.style, { left: x0 + 'px', top: y0 + 'px', width: Math.abs(e.clientX - a.x) + 'px', height: Math.abs(e.clientY - a.y) + 'px' });
    caixa.hidden = false;
    a.fx = e.clientX; a.fy = e.clientY;
  }

  finalizarCaixa(e) {
    const a = this.caixaArrasto;
    this.caixaArrasto = null;
    document.getElementById('caixa-selecao').hidden = true;
    if (a.fx === undefined || Math.hypot(e.clientX - a.x, e.clientY - a.y) < 5) return;
    const r = this.canvas.getBoundingClientRect();
    const xa = Math.min(a.x, a.fx) - r.left, xb = Math.max(a.x, a.fx) - r.left;
    const ya = Math.min(a.y, a.fy) - r.top, yb = Math.max(a.y, a.fy) - r.top;
    const dentro = (v) => {
      const p = v.clone().project(this.camera);
      if (p.z > 1 || p.z < -1) return false;
      const sx = (p.x + 1) / 2 * r.width, sy = (1 - p.y) / 2 * r.height;
      return sx >= xa && sx <= xb && sy >= ya && sy <= yb;
    };
    if (this.ferramentaCaixa === 'torcida' && this.torcida) {
      this.dispatchEvent(new CustomEvent('caixaTorcida', { detail: { dentro, shift: a.shift } }));
      return;
    }
    // escolhe os nós mais profundos com peças visíveis cujo centro cai na caixa
    const ids = [];
    const tmp = new THREE.Box3(), c = new THREE.Vector3();
    for (const n of this.modelo.nos) {
      const g = this.objs[n.id];
      if (!g || !g.userData.pecasObj.children.length) continue;
      let vis = true;
      for (let o = g; o; o = o.parent) if (!o.visible) { vis = false; break; }
      if (!vis || !g.userData.pecasObj.visible) continue;
      tmp.makeEmpty();
      g.userData.pecasObj.traverse((o) => {
        if (!o.geometry || o.userData.overlay) return;
        if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
        const b = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);
        tmp.union(b);
      });
      if (tmp.isEmpty()) continue;
      tmp.getCenter(c);
      if (dentro(c)) ids.push(n.id);
    }
    this.dispatchEvent(new CustomEvent('caixa', { detail: { ids, shift: a.shift } }));
  }

  // ------------------------------------------------------------------ mover livre (G), como no Blender
  // O objeto acompanha o mouse no plano da tela. X/Y/Z travam no eixo; Shift+X/Y/Z travam no plano (Shift+Y = no chão).
  // Clique ou Enter confirma; Esc ou botão direito cancela. Ctrl encaixa em passos de 0,5 m.
  iniciarMoverLivre(xTela, yTela) {
    const moveis = this.espelhado ? [] : this.nosMoveis();
    if (!moveis.length || this.livre) return false;
    this.gizmo.detach();
    const caixa = this.caixaDe(moveis.map((n) => n.id));
    const centro = caixa.isEmpty() ? new THREE.Vector3() : caixa.getCenter(new THREE.Vector3());
    const r = this.canvas.getBoundingClientRect();
    this.livre = {
      moveis, centro, trava: null, plano: false, digitado: '',
      inicio: moveis.map((n) => ({ n, mundo: this.objs[n.id].matrixWorld.clone(), local: n.local.slice() })),
      mouse0: new THREE.Vector2(xTela ?? r.left + r.width / 2, yTela ?? r.top + r.height / 2),
      mouse: new THREE.Vector2(xTela ?? r.left + r.width / 2, yTela ?? r.top + r.height / 2),
    };
    this.livre.ponto0 = this.pontoNoPlano(this.livre.mouse0);
    this.canvas.style.cursor = 'move';
    this.atualizarLivre();
    return true;
  }

  pontoNoPlano(mouse) {
    const L = this.livre;
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((mouse.x - r.left) / r.width) * 2 - 1, -((mouse.y - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const dirCam = this.camera.getWorldDirection(new THREE.Vector3());
    let normal = dirCam.clone().negate();
    if (L.trava && L.plano) {                         // plano que exclui o eixo
      normal = new THREE.Vector3(L.trava === 'x' ? 1 : 0, L.trava === 'y' ? 1 : 0, L.trava === 'z' ? 1 : 0);
    } else if (L.trava) {                             // eixo: plano que contém o eixo e encara a câmera
      const eixo = new THREE.Vector3(L.trava === 'x' ? 1 : 0, L.trava === 'y' ? 1 : 0, L.trava === 'z' ? 1 : 0);
      normal = new THREE.Vector3().crossVectors(eixo, new THREE.Vector3().crossVectors(dirCam, eixo)).normalize();
      if (normal.lengthSq() < 1e-6) normal = dirCam.clone().negate();
    }
    const plano = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, L.centro);
    return this.raycaster.ray.intersectPlane(plano, new THREE.Vector3());
  }

  moverLivre(e) {
    if (!this.livre) return;
    this.livre.mouse.set(e.clientX, e.clientY);
    this.livre.ctrl = e.ctrlKey;
    this.atualizarLivre();
  }

  travarLivre(eixo, plano) {
    const L = this.livre;
    if (!L) return;
    if (L.trava === eixo && L.plano === plano) { L.trava = null; L.plano = false; }
    else { L.trava = eixo; L.plano = plano; }
    L.ponto0 = this.pontoNoPlano(L.mouse0);
    this.atualizarLivre();
  }

  atualizarLivre() {
    const L = this.livre;
    const p0 = L.ponto0 || this.pontoNoPlano(L.mouse0);
    const p1 = this.pontoNoPlano(L.mouse);
    const delta = (p0 && p1) ? p1.clone().sub(p0) : new THREE.Vector3();
    if (L.trava && !L.plano) { const k = { x: 'x', y: 'y', z: 'z' }[L.trava]; delta.set(k === 'x' ? delta.x : 0, k === 'y' ? delta.y : 0, k === 'z' ? delta.z : 0); }
    if (L.trava && L.plano) delta[L.trava] = 0;
    if (L.ctrl || this.encaixe) delta.set(Math.round(delta.x * 2) / 2, Math.round(delta.y * 2) / 2, Math.round(delta.z * 2) / 2);
    L.delta = delta;
    const T = new THREE.Matrix4().makeTranslation(delta.x, delta.y, delta.z);
    for (const it of L.inicio) {
      const g = this.objs[it.n.id];
      const novo = new THREE.Matrix4().multiplyMatrices(T, it.mundo).premultiply(g.parent.matrixWorld.clone().invert());
      const local = m12De(novo);
      for (const id of this.modelo.porAlvo.get(it.n.chave) || [it.n.id]) {
        const n = this.modelo.nos[id];
        n.local = local;
        n.localM.copy(novo);
        this.objs[id].matrix.copy(novo);
        this.objs[id].updateMatrixWorld(true);
      }
    }
    this.atualizarCaixaSelecao();
    this.sujo = true;
    this.dispatchEvent(new CustomEvent('livre', { detail: { delta, trava: L.trava, plano: L.plano } }));
  }

  terminarLivre(confirmar) {
    const L = this.livre;
    if (!L) return;
    this.livre = null;
    this.canvas.style.cursor = '';
    if (!confirmar) {
      for (const it of L.inicio) this.modelo.definirLocais(new Map([[this.modelo.chaveDe(it.n), it.local]]));
    } else {
      for (const it of L.inicio) this.modelo.calcularMundos(it.n.id);
      const antes = new Map(), depois = new Map();
      for (const it of L.inicio) { const k = this.modelo.chaveDe(it.n); antes.set(k, it.local); depois.set(k, it.n.local.slice()); }
      if (L.delta && L.delta.lengthSq() > 1e-10) {
        this.dispatchEvent(new CustomEvent('transformado', { detail: { antes, depois, nome: `Mover livre ${L.inicio.length > 1 ? L.inicio.length + ' objetos' : L.inicio[0].n.nome}` } }));
      }
    }
    this.dispatchEvent(new CustomEvent('livre', { detail: null }));
    this.atualizarGizmo();
    this.sujo = true;
  }

  // ponto da superfície sob o mouse (para colocar uma luz nova): {ponto, normal} no mundo, ou null
  pontoNaCena(xTela, yTela) {
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((xTela - r.left) / r.width) * 2 - 1, -((yTela - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const alvos = this.pegaveis().filter((o) => o.isMesh && !o.userData.luz && !o.userData.pessoa && !o.userData.marcador && !o.isPoints);
    const h = this.raycaster.intersectObjects(alvos, false).find((x) => x.face && !(x.object.material && x.object.material.opacity < 0.1));
    if (!h) {
      const p = this.raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
      return p ? { ponto: p, normal: new THREE.Vector3(0, 1, 0), no: -1 } : null;
    }
    const normal = h.face.normal.clone().transformDirection(h.object.matrixWorld).normalize();
    if (normal.dot(this.raycaster.ray.direction) > 0) normal.negate();
    return { ponto: h.point.clone(), normal, no: h.object.userData.no };
  }

  // áreas técnicas do stadiums.txt (onde técnico e reservas ficam): casa em azul, visitante em vermelho
  definirZonas(zonas, visivel) {
    if (this.zonasObj) { this.zonasObj.removeFromParent(); this.zonasObj.traverse((o) => o.geometry && o.geometry.dispose()); this.zonasObj = null; }
    if (!visivel || !zonas) { this.sujo = true; return; }
    const g = new THREE.Group();
    for (const [lado, cor] of [['casa', 0x4c8dff], ['fora', 0xff5a5f]]) {
      const z = zonas[lado];
      if (!z) continue;
      const [x0, x1, z0, z1] = z;
      const w = Math.abs(x1 - x0), d = Math.abs(z1 - z0);
      const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
      const placa = new THREE.Mesh(new THREE.PlaneGeometry(Math.max(w, 0.2), Math.max(d, 0.2)).rotateX(-Math.PI / 2),
        new THREE.MeshBasicMaterial({ color: cor, transparent: true, opacity: 0.28, depthTest: false, side: THREE.DoubleSide }));
      placa.position.set(cx, 0.06, cz);
      placa.renderOrder = 7;
      const borda = new THREE.LineSegments(new THREE.EdgesGeometry(placa.geometry), new THREE.LineBasicMaterial({ color: cor, depthTest: false }));
      borda.position.copy(placa.position);
      borda.renderOrder = 8;
      placa.userData.overlay = borda.userData.overlay = true;
      g.add(placa, borda);
    }
    this.zonasObj = g;
    this.raiz.add(g);
    this.sujo = true;
  }

  // como o jogo mostra um estádio com ismirrored = 1: tudo espelhado em Z (as laterais trocam de lado)
  definirEspelho(v) {
    this.espelhado = !!v;
    this.raiz.scale.set(1, 1, v ? -1 : 1);
    this.raiz.updateMatrixWorld(true);
    if (v) this.gizmo.detach();
    this.atualizarGizmo();
    this.atualizarCaixaSelecao();
    this.sujo = true;
  }

  // ------------------------------------------------------------------ linhas do campo (regras da FIFA), centradas na origem
  definirCampo(comprimento, largura, visivel) {
    if (this.campoObj) { this.campoObj.removeFromParent(); this.campoObj.traverse((o) => o.geometry && o.geometry.dispose()); this.campoObj = null; }
    this.mostrarCampo = visivel;
    if (!visivel) { this.sujo = true; return; }
    const C = comprimento / 2, L = largura / 2, y = 0.03;
    const pts = [];
    const seg = (a, b) => pts.push(new THREE.Vector3(a[0], y, a[1]), new THREE.Vector3(b[0], y, b[1]));
    const arco = (cx, cz, r, a0, a1, n = 48) => {
      for (let i = 0; i < n; i++) {
        const t0 = a0 + (a1 - a0) * i / n, t1 = a0 + (a1 - a0) * (i + 1) / n;
        seg([cx + r * Math.cos(t0), cz + r * Math.sin(t0)], [cx + r * Math.cos(t1), cz + r * Math.sin(t1)]);
      }
    };
    seg([-C, -L], [C, -L]); seg([C, -L], [C, L]); seg([C, L], [-C, L]); seg([-C, L], [-C, -L]);
    seg([0, -L], [0, L]);
    arco(0, 0, 9.15, 0, Math.PI * 2, 64);
    for (const s of [-1, 1]) {
      const g = s * C;
      seg([g, -20.16], [g - s * 16.5, -20.16]); seg([g - s * 16.5, -20.16], [g - s * 16.5, 20.16]); seg([g - s * 16.5, 20.16], [g, 20.16]);
      seg([g, -9.16], [g - s * 5.5, -9.16]); seg([g - s * 5.5, -9.16], [g - s * 5.5, 9.16]); seg([g - s * 5.5, 9.16], [g, 9.16]);
      const px = g - s * 11;
      arco(px, 0, 0.12, 0, Math.PI * 2, 8);
      const ang = Math.acos(5.5 / 9.15);
      if (s > 0) arco(px, 0, 9.15, Math.PI - ang, Math.PI + ang, 24); else arco(px, 0, 9.15, -ang, ang, 24);
      seg([g, -3.66], [g + s * 1.5, -3.66]); seg([g + s * 1.5, -3.66], [g + s * 1.5, 3.66]); seg([g + s * 1.5, 3.66], [g, 3.66]);
      for (const t of [-1, 1]) {
        const a0 = s > 0 ? (t > 0 ? Math.PI : Math.PI / 2) : (t > 0 ? -Math.PI / 2 : 0);
        arco(g, t * L, 1, a0, a0 + Math.PI / 2, 8);
      }
    }
    arco(0, 0, 0.15, 0, Math.PI * 2, 8);
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95, depthTest: false });
    const linhas = new THREE.LineSegments(geo, mat);
    linhas.renderOrder = 8;
    const grupo = new THREE.Group();
    grupo.add(linhas);
    // traves (7,32 x 2,44)
    const trave = new THREE.LineBasicMaterial({ color: 0xffe08a, depthTest: false });
    for (const s of [-1, 1]) {
      const g = s * C;
      const tp = [new THREE.Vector3(g, 0, -3.66), new THREE.Vector3(g, 2.44, -3.66), new THREE.Vector3(g, 2.44, -3.66), new THREE.Vector3(g, 2.44, 3.66),
        new THREE.Vector3(g, 2.44, 3.66), new THREE.Vector3(g, 0, 3.66)];
      const l = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(tp), trave);
      l.renderOrder = 8;
      grupo.add(l);
    }
    grupo.userData.campo = true;
    this.campoObj = grupo;
    this.raiz.add(grupo);
    this.sujo = true;
  }

  // ------------------------------------------------------------------ câmera
  enquadrar(caixa, { instantaneo = false } = {}) {
    if (!caixa || caixa.isEmpty()) return;
    const centro = caixa.getCenter(new THREE.Vector3());
    const raio = Math.max(caixa.getBoundingSphere(new THREE.Sphere()).radius, 1);
    const cam = this.camera, ctl = this.controles;
    const dir = new THREE.Vector3().subVectors(cam.position, ctl.target).normalize();
    if (!Number.isFinite(dir.x) || dir.lengthSq() < 0.5) dir.set(0.6, 0.5, 0.6).normalize();
    const dist = raio / Math.sin(THREE.MathUtils.degToRad(cam.fov) / 2) * 1.05;
    this.animarPara(centro.clone().addScaledVector(dir, dist), centro, instantaneo);
  }

  animarPara(pos, alvo, instantaneo = false) {
    const cam = this.camera, ctl = this.controles;
    if (instantaneo) { cam.position.copy(pos); ctl.target.copy(alvo); ctl.update(); this.sujo = true; return; }
    const p0 = cam.position.clone(), t0 = ctl.target.clone();
    let t = 0;
    this.animacao = (dt) => {
      t = Math.min(1, t + dt / 0.35);
      const k = 1 - Math.pow(1 - t, 3);
      cam.position.lerpVectors(p0, pos, k);
      ctl.target.lerpVectors(t0, alvo, k);
      if (t >= 1) this.animacao = null;
    };
  }

  enquadrarTudo(instantaneo = false) {
    // caixa robusta: ignora os 3% mais extremos (terrenos e cenários de 1 km em volta do estádio)
    const tmp = new THREE.Box3();
    const lo = [[], [], []], hi = [[], [], []];
    this.raiz.updateMatrixWorld(true);
    this.raiz.traverseVisible((o) => {
      if (!o.isMesh || o.userData.overlay || o.userData.marcador || !o.geometry) return;
      if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
      tmp.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld);
      if (tmp.max.y < -100) return;
      for (let k = 0; k < 3; k++) { lo[k].push(tmp.min.getComponent(k)); hi[k].push(tmp.max.getComponent(k)); }
    });
    const caixa = new THREE.Box3();
    if (lo[0].length) {
      const pct = (arr, p) => { const s = arr.slice().sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.max(0, Math.round(p * (s.length - 1))))]; };
      const q = lo[0].length > 40 ? 0.03 : 0;
      caixa.min.set(pct(lo[0], q), pct(lo[1], q), pct(lo[2], q));
      caixa.max.set(pct(hi[0], 1 - q), pct(hi[1], 1 - q), pct(hi[2], 1 - q));
    }
    if (caixa.isEmpty()) caixa.setFromCenterAndSize(new THREE.Vector3(), new THREE.Vector3(120, 30, 80));
    // estádio inteiro: vista de cima em diagonal
    const centro = caixa.getCenter(new THREE.Vector3());
    const raio = caixa.getBoundingSphere(new THREE.Sphere()).radius;
    const dist = raio / Math.sin(THREE.MathUtils.degToRad(this.camera.fov) / 2) * 0.95;
    const dir = new THREE.Vector3(0.62, 0.55, 0.56).normalize();
    this.animarPara(centro.clone().addScaledVector(dir, dist), centro, instantaneo);
  }

  vista(nome) {
    const ctl = this.controles;
    const alvo = ctl.target.clone();
    const dist = Math.max(this.camera.position.distanceTo(alvo), 40);
    const dirs = { topo: [0, 1, 0.0001], frente: [0, 0.18, 1], tras: [0, 0.18, -1], direita: [1, 0.18, 0], esquerda: [-1, 0.18, 0], perspectiva: [0.62, 0.55, 0.56] };
    const d = new THREE.Vector3(...dirs[nome]).normalize();
    this.animarPara(alvo.clone().addScaledVector(d, dist), alvo);
  }

  centralizarEm(ponto) {
    const ctl = this.controles;
    const desloc = new THREE.Vector3().subVectors(ponto, ctl.target);
    this.animarPara(this.camera.position.clone().add(desloc), ponto.clone());
  }

  // ------------------------------------------------------------------ torcida
  mostrarTorcida(dados, modoCor = 'SeatColor') {
    if (this.torcida) { this.torcida.removeFromParent(); this.torcida.geometry.dispose(); this.torcida = null; }
    if (!dados) { this.sujo = true; return; }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(dados.posicoes, 3));
    const cores = new Float32Array(dados.n * 3);
    g.setAttribute('color', new THREE.BufferAttribute(cores, 3));
    const mat = new THREE.PointsMaterial({ size: 0.42, sizeAttenuation: true, vertexColors: true });
    const p = new THREE.Points(g, mat);
    p.userData.torcida = true;
    p.userData.dados = dados;
    this.torcida = p;
    this.colorirTorcida(modoCor);
    this.raiz.add(p);
    this.sujo = true;
  }

  // prévia de assentos: pontos e, com orientações (graus, atan2(-dz, dx)), uma seta curta para onde cada um olha
  mostrarPrevia(posicoes, orient = null) {
    if (this.previa) { this.previa.removeFromParent(); this.previa.traverse((o) => o.geometry && o.geometry.dispose()); this.previa = null; }
    if (posicoes && posicoes.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(posicoes, 3));
      this.previa = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.38, sizeAttenuation: true, color: 0x3fd0c9 }));
      this.previa.renderOrder = 4;
      if (orient && orient.length) {
        const n = posicoes.length / 3, passo = Math.max(1, Math.floor(n / 6000));
        const pts = [];
        for (let i = 0; i < n; i += passo) {
          const a = orient[i] / 180 * Math.PI;
          const x = posicoes[i * 3], y = posicoes[i * 3 + 1] + 0.05, z = posicoes[i * 3 + 2];
          pts.push(x, y, z, x + Math.cos(a) * 0.55, y, z - Math.sin(a) * 0.55);
        }
        const gl = new THREE.BufferGeometry();
        gl.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
        const setas = new THREE.LineSegments(gl, new THREE.LineBasicMaterial({ color: 0xffb020 }));
        setas.renderOrder = 4;
        this.previa.add(setas);
      }
      this.raiz.add(this.previa);
    }
    this.sujo = true;
  }

  colorirTorcida(modo) {
    const p = this.torcida;
    if (!p) return;
    const d = p.userData.dados;
    const cores = p.geometry.getAttribute('color');
    const c = new THREE.Color();
    const mapa = d.mapas[modo] || [];
    const marcados = p.userData.marcados || new Set();
    const paleta = [0x4c8dff, 0xff9233, 0x45b97c, 0xd65db1, 0xf0b429, 0x6cc0c0];
    for (let i = 0; i < d.n; i++) {
      const v = mapa[i];
      if (marcados.has(i)) c.setHex(0xf0565a);
      else if (modo === 'SeatColor' && v !== undefined) c.setRGB(((v >>> 16) & 255) / 255, ((v >>> 8) & 255) / 255, (v & 255) / 255, THREE.SRGBColorSpace);
      else if (modo === 'SeatTier' && v !== undefined) c.setHex(paleta[v % paleta.length]);
      else if (v !== undefined && typeof v === 'number') { const t = THREE.MathUtils.clamp(v, 0, 1); c.setRGB(0.15 + 0.85 * t, 0.25 + 0.5 * (1 - Math.abs(t - 0.5) * 2), 1 - t, THREE.SRGBColorSpace); }
      else c.setHex(0xc8ccd2);
      cores.setXYZ(i, c.r, c.g, c.b);
    }
    cores.needsUpdate = true;
    p.userData.modoCor = modo;
    this.sujo = true;
  }

  // ------------------------------------------------------------------ captura
  capturar() {
    this.render();
    return new Promise((res) => this.canvas.toBlob(res, 'image/png'));
  }

  estatisticas() {
    let tri = 0, malhas = 0;
    this.raiz.traverseVisible((o) => {
      if (o.isMesh && !o.userData.overlay && o.geometry?.index) { tri += o.geometry.index.count / 3; malhas++; }
      else if (o.isMesh && !o.userData.overlay && o.geometry) { tri += (o.geometry.attributes.position?.count || 0) / 3; malhas++; }
    });
    return { triangulos: Math.round(tri), malhas };
  }
}
