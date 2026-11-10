// Prévia 3D do .glb do KeenFace com o three.js do Super Tool. O GLTFLoader não vem no pacote, então aqui vai um leitor
// de GLB próprio e mínimo: nós com transformações, malhas de triângulos, UV, normais e texturas embutidas (cor, normal e
// rugosidade). Extensões que só mudam a aparência (ior, clearcoat, specular) são ignoradas; as que mudam a geometria
// (Draco, meshopt) fazem a prévia desistir com uma mensagem, sem mexer no arquivo.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const COMPONENTES = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 };
const TIPOS = { 5120: Int8Array, 5121: Uint8Array, 5122: Int16Array, 5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array };
const LEITURA = { 5120: 'getInt8', 5121: 'getUint8', 5122: 'getInt16', 5123: 'getUint16', 5125: 'getUint32', 5126: 'getFloat32' };
const NORMALIZA = { 5120: 127, 5121: 255, 5122: 32767, 5123: 65535 };
const SO_APARENCIA = new Set(['KHR_materials_ior', 'KHR_materials_clearcoat', 'KHR_materials_specular', 'KHR_texture_transform',
  'KHR_materials_emissive_strength', 'KHR_materials_sheen', 'KHR_materials_transmission', 'KHR_materials_volume', 'KHR_materials_unlit']);
const COR_ARGILA = 0xc9ab98;

export function lerGLB(buf) {
  const dv = new DataView(buf);
  if (buf.byteLength < 20 || dv.getUint32(0, true) !== 0x46546c67) throw new Error('o arquivo não é um .glb');
  let off = 12, json = null, bin = null;
  while (off + 8 <= buf.byteLength) {
    const tam = dv.getUint32(off, true), tipo = dv.getUint32(off + 4, true);
    if (tipo === 0x4e4f534a) json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, off + 8, tam)));
    else if (tipo === 0x004e4942 && !bin) bin = new Uint8Array(buf, off + 8, tam);
    off += 8 + tam;
  }
  if (!json) throw new Error('o .glb não tem a parte JSON');
  const faltam = (json.extensionsRequired || []).filter((e) => !SO_APARENCIA.has(e));
  if (faltam.length) throw new Error(`a prévia não lê ${faltam.join(', ')}`);
  return { json, bin };
}

function lerAcessor(glb, i) {
  const { json, bin } = glb;
  const a = json.accessors[i];
  const n = COMPONENTES[a.type], Tipo = TIPOS[a.componentType];
  if (!n || !Tipo) throw new Error('acessor de tipo desconhecido');
  const total = a.count * n;
  let out;
  if (a.bufferView === undefined) out = new Tipo(total);
  else {
    if (!bin) throw new Error('o .glb não tem a parte binária');
    const bv = json.bufferViews[a.bufferView];
    const tamEl = Tipo.BYTES_PER_ELEMENT;
    const ini = bin.byteOffset + (bv.byteOffset || 0) + (a.byteOffset || 0);
    const passo = bv.byteStride || n * tamEl;
    if (passo === n * tamEl && ini % tamEl === 0) out = new Tipo(bin.buffer, ini, total).slice();
    else {
      out = new Tipo(total);
      const dv = new DataView(bin.buffer);
      const ler = LEITURA[a.componentType];
      for (let k = 0; k < a.count; k++) for (let c = 0; c < n; c++) out[k * n + c] = dv[ler](ini + k * passo + c * tamEl, true);
    }
  }
  if (a.normalized && NORMALIZA[a.componentType]) {
    const f = new Float32Array(total), d = NORMALIZA[a.componentType];
    for (let j = 0; j < total; j++) f[j] = Math.max(out[j] / d, -1);
    out = f;
  }
  return { dados: out, n };
}

function matrizDoNo(no) {
  const m = new THREE.Matrix4();
  if (no.matrix) return m.fromArray(no.matrix);
  return m.compose(new THREE.Vector3(...(no.translation || [0, 0, 0])), new THREE.Quaternion(...(no.rotation || [0, 0, 0, 1])),
    new THREE.Vector3(...(no.scale || [1, 1, 1])));
}

async function imagem(glb, i, cache) {
  if (cache.has(i)) return cache.get(i);
  const p = (async () => {
    const { json, bin } = glb;
    const img = json.images[i];
    if (img.bufferView === undefined) return null;          // imagem externa: o .glb do KeenFace vem com tudo dentro
    const bv = json.bufferViews[img.bufferView];
    const bytes = new Uint8Array(bin.buffer, bin.byteOffset + (bv.byteOffset || 0), bv.byteLength);
    const blob = new Blob([bytes], { type: img.mimeType || 'image/jpeg' });
    return createImageBitmap(blob, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
  })();
  cache.set(i, p);
  return p;
}

async function textura(glb, info, cor, cache) {
  if (!info) return null;
  const t = glb.json.textures?.[info.index];
  if (!t) return null;
  const fonte = t.source ?? t.extensions?.EXT_texture_webp?.source;
  if (fonte === undefined) return null;
  const bmp = await imagem(glb, fonte, cache).catch(() => null);
  if (!bmp) return null;
  const tex = new THREE.Texture(bmp);
  tex.flipY = false;                                          // UV do glTF: origem em cima
  tex.colorSpace = cor ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return tex;
}

async function material(glb, i, temTangente, cache) {
  const def = (i !== undefined && glb.json.materials?.[i]) || {};
  const pbr = def.pbrMetallicRoughness || {};
  const f = pbr.baseColorFactor || [1, 1, 1, 1];
  const nome = def.name || '';
  const cornea = /cornea/i.test(nome);
  const m = new THREE.MeshStandardMaterial({
    color: new THREE.Color().setRGB(f[0], f[1], f[2], THREE.LinearSRGBColorSpace),
    metalness: 0,                                             // o modo Raw marca metallicFactor 1: fica escuro na prévia
    roughness: Math.min(1, Math.max(0.3, pbr.roughnessFactor ?? 0.6)),
    side: def.doubleSided ? THREE.DoubleSide : THREE.FrontSide,
  });
  m.name = nome;
  const [mapa, normal, rug] = await Promise.all([textura(glb, pbr.baseColorTexture, true, cache), textura(glb, def.normalTexture, false, cache),
    textura(glb, pbr.metallicRoughnessTexture, false, cache)]);
  if (mapa) m.map = mapa;
  if (normal) {
    m.normalMap = normal;
    const s = def.normalTexture.scale ?? 1;
    m.normalScale = new THREE.Vector2(s, temTangente ? s : -s);
  }
  if (rug) m.roughnessMap = rug;
  if (cornea || def.alphaMode === 'BLEND') {
    m.transparent = true;
    m.depthWrite = false;
    m.opacity = cornea ? Math.min(f[3], 0.12) : f[3];
  } else if (def.alphaMode === 'MASK') {
    m.alphaTest = def.alphaCutoff ?? 0.5;
  }
  m.userData.original = { map: m.map, color: m.color.clone() };
  return m;
}

export class PreviaGLB {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.cena = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.cena.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.cena.environmentIntensity = 0.55;
    this.camera = new THREE.PerspectiveCamera(26, 1, 0.01, 50);
    const chave = new THREE.DirectionalLight(0xffffff, 1.6);
    chave.position.set(1.2, 2.2, 2.4);
    this.cena.add(chave);
    const recorte = new THREE.DirectionalLight(0x9fc0ff, 0.7);
    recorte.position.set(-2, 1.2, -1.6);
    this.cena.add(recorte);
    this.cena.add(this.camera);
    this.grupo = new THREE.Group();
    this.cena.add(this.grupo);
    this.controles = new OrbitControls(this.camera, canvas);
    this.controles.enableDamping = true;
    this.controles.dampingFactor = 0.12;
    this.controles.addEventListener('change', () => this.pedir());
    this.girando = false;
    this.arame = false;
    this.comTextura = true;
    this._pedido = false;
    this._carga = 0;
    new ResizeObserver(() => this.ajustar()).observe(canvas.parentElement);
    this.ajustar();
  }

  ajustar() {
    const p = this.canvas.parentElement;
    const w = Math.max(1, p.clientWidth), h = Math.max(1, p.clientHeight);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.pedir();
  }

  pedir() {
    if (this._pedido) return;
    this._pedido = true;
    requestAnimationFrame(() => this._quadro());
  }

  _quadro() {
    this._pedido = false;
    if (this.girando) this.grupo.rotation.y += 0.008;
    const mexeu = this.controles.update();
    this.renderer.render(this.cena, this.camera);
    if (this.girando || mexeu) this.pedir();
  }

  limpar() {
    this._carga++;
    const texs = new Set();
    this.grupo.traverse((o) => {
      if (!o.isMesh) return;
      o.geometry.dispose();
      for (const k of ['map', 'normalMap', 'roughnessMap']) if (o.material[k]) texs.add(o.material[k]);
      if (o.material.userData.original?.map) texs.add(o.material.userData.original.map);
      o.material.dispose();
    });
    for (const t of texs) { t.image?.close?.(); t.dispose(); }
    this.grupo.clear();
    this.grupo.rotation.set(0, 0, 0);
    this.pedir();
  }

  /** Lê o .glb (ArrayBuffer) e mostra. -> {vertices, triangulos, partes} */
  async mostrar(buf) {
    this.limpar();
    const carga = this._carga;
    const glb = lerGLB(buf);
    const { json } = glb;
    const cache = new Map(), materiais = new Map();
    const raiz = new THREE.Group();
    let vertices = 0, triangulos = 0, partes = 0;
    const cenaDef = json.scenes?.[json.scene ?? 0];
    const filhos = new Set((json.nodes || []).flatMap((n) => n.children || []));
    const raizes = cenaDef?.nodes || (json.nodes || []).map((_, i) => i).filter((i) => !filhos.has(i));
    const visitar = async (i, pai, profundidade) => {
      const no = json.nodes[i];
      if (!no || profundidade > 64) return;
      const m = new THREE.Matrix4().multiplyMatrices(pai, matrizDoNo(no));
      if (no.mesh !== undefined) {
        for (const p of json.meshes[no.mesh].primitives || []) {
          if ((p.mode ?? 4) !== 4 || p.attributes.POSITION === undefined) continue;
          if (p.extensions?.KHR_draco_mesh_compression) throw new Error('a prévia não lê malhas com Draco');
          const g = new THREE.BufferGeometry();
          const pos = lerAcessor(glb, p.attributes.POSITION);
          g.setAttribute('position', new THREE.BufferAttribute(pos.dados, 3));
          if (p.attributes.NORMAL !== undefined) g.setAttribute('normal', new THREE.BufferAttribute(lerAcessor(glb, p.attributes.NORMAL).dados, 3));
          if (p.attributes.TEXCOORD_0 !== undefined) g.setAttribute('uv', new THREE.BufferAttribute(lerAcessor(glb, p.attributes.TEXCOORD_0).dados, 2));
          if (p.attributes.TANGENT !== undefined) g.setAttribute('tangent', new THREE.BufferAttribute(lerAcessor(glb, p.attributes.TANGENT).dados, 4));
          if (p.indices !== undefined) g.setIndex(new THREE.BufferAttribute(lerAcessor(glb, p.indices).dados, 1));
          if (!g.getAttribute('normal')) g.computeVertexNormals();
          const chaveMat = `${p.material}|${p.attributes.TANGENT !== undefined}`;
          if (!materiais.has(chaveMat)) materiais.set(chaveMat, material(glb, p.material, p.attributes.TANGENT !== undefined, cache));
          const malha = new THREE.Mesh(g, await materiais.get(chaveMat));
          malha.matrixAutoUpdate = false;
          malha.matrix.copy(m);
          if (malha.material.transparent) malha.renderOrder = 2;
          raiz.add(malha);
          vertices += pos.dados.length / 3;
          triangulos += (g.index ? g.index.count : pos.dados.length / 3) / 3;
          partes++;
        }
      }
      for (const c of no.children || []) await visitar(c, m, profundidade + 1);
    };
    for (const r of raizes) await visitar(r, new THREE.Matrix4(), 0);
    if (carga !== this._carga) { raiz.traverse((o) => { if (o.isMesh) { o.geometry.dispose(); o.material.dispose(); } }); return null; }
    if (!partes) throw new Error('o .glb não tem malhas');
    this.grupo.add(raiz);
    this.aplicarModo();
    this.enquadrar();
    return { vertices, triangulos: Math.round(triangulos), partes };
  }

  enquadrar() {
    this.grupo.rotation.y = 0;
    this.grupo.updateMatrixWorld(true);
    const caixa = new THREE.Box3().setFromObject(this.grupo);
    if (caixa.isEmpty()) return;
    const c = caixa.getCenter(new THREE.Vector3());
    const tam = caixa.getSize(new THREE.Vector3()).length();
    const dist = tam / (2 * Math.tan((this.camera.fov * Math.PI) / 360)) * 1.1;
    this.controles.target.copy(c);
    this.camera.position.set(c.x + dist * 0.32, c.y + dist * 0.06, c.z + dist * 0.95);   // o rosto olha para +Z
    this.camera.near = dist / 200;
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controles.update();
    this.pedir();
  }

  aplicarModo() {
    this.grupo.traverse((o) => {
      if (!o.isMesh) return;
      const m = o.material, orig = m.userData.original || {};
      m.wireframe = this.arame;
      if (this.comTextura) { m.map = orig.map || null; m.color.copy(orig.color || new THREE.Color(1, 1, 1)); }
      else if (!m.transparent) { m.map = null; m.color.set(COR_ARGILA); }
      m.needsUpdate = true;
    });
    this.pedir();
  }

  definirGiro(v) { this.girando = v; this.pedir(); }
  definirArame(v) { this.arame = v; this.aplicarModo(); }
  definirTextura(v) { this.comTextura = v; this.aplicarModo(); }
  vazia() { return !this.grupo.children.length; }
}
