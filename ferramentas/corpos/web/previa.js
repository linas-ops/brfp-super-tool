// Prévia 3D do corpo (bodyupper LOD0 de referência) com a textura aplicada — mesma base do Conversor de Faces.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const PELE = 0xc9a48e;

export class Previa {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.cena = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(28, 1, 0.01, 50);
    this.camera.position.set(0, 1.3, 2.4);
    this.cena.add(new THREE.HemisphereLight(0xdfe7ff, 0x3a3027, 1.3));
    const chave = new THREE.DirectionalLight(0xffffff, 2.0);
    chave.position.set(1.2, 2.5, 2);
    this.cena.add(chave);
    const recorte = new THREE.DirectionalLight(0x9fc0ff, 1.1);
    recorte.position.set(-2, 1.5, -1.5);
    this.cena.add(recorte);
    this.camera.add(new THREE.PointLight(0xffffff, 0.5, 0, 0));
    this.cena.add(this.camera);
    this.grupo = new THREE.Group();
    this.cena.add(this.grupo);
    this.controles = new OrbitControls(this.camera, canvas);
    this.controles.enableDamping = true;
    this.controles.dampingFactor = 0.12;
    this.controles.addEventListener('change', () => this.pedir());
    this.girando = false;
    this.arame = false;
    this._pedido = false;
    this._jogo = null;
    this.carregador = new THREE.TextureLoader();
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
    for (const m of [...this.grupo.children]) {
      m.geometry.dispose();
      if (m.material.map) m.material.map.dispose();
      if (m.material.normalMap) m.material.normalMap.dispose();
      m.material.dispose();
      this.grupo.remove(m);
    }
    this._jogo = null;
    this.pedir();
  }

  // malha = { V, UV, T } do corpo do jogo; url = PNG da textura; normal = usar como mapa normal (DirectX)
  async mostrar(jogo, malha, url, { normal = false, manterCamera = false } = {}) {
    const tex = await this.carregador.loadAsync(url);
    tex.colorSpace = normal ? THREE.NoColorSpace : THREE.SRGBColorSpace;
    tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
    const trocouCorpo = this._jogo !== jogo;
    const camera = trocouCorpo ? null : true;
    this.limpar();
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(malha.V, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(malha.UV, 2));
    g.setIndex(malha.T);
    g.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: normal ? PELE : 0xffffff, roughness: 0.62, metalness: 0,
      wireframe: this.arame, side: THREE.DoubleSide });
    if (normal) { mat.normalMap = tex; mat.normalScale = new THREE.Vector2(1, -1); } else mat.map = tex;
    this.grupo.add(new THREE.Mesh(g, mat));
    this._jogo = jogo;
    if (!(manterCamera && camera)) this.enquadrar();
    this.pedir();
  }

  enquadrar() {
    this.grupo.rotation.y = 0;
    const caixa = new THREE.Box3().setFromObject(this.grupo);
    if (caixa.isEmpty()) return;
    const c = caixa.getCenter(new THREE.Vector3());
    const tam = caixa.getSize(new THREE.Vector3()).length();
    const dist = tam / (2 * Math.tan((this.camera.fov * Math.PI) / 360)) * 1.0;
    this.controles.target.copy(c);
    this.camera.position.set(c.x + dist * 0.3, c.y + dist * 0.1, c.z + dist * 0.95);
    this.camera.near = dist / 100;
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controles.update();
    this.pedir();
  }

  definirGiro(v) { this.girando = v; this.pedir(); }

  definirArame(v) {
    this.arame = v;
    for (const m of this.grupo.children) m.material.wireframe = v;
    this.pedir();
  }
}
