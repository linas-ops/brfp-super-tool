// Prévia 3D do kit: o uniforme do PES 2021 (uma malha, uma textura) ou o do FC 27 (camisa, calção e meião, cada um com
// a sua textura) — mesma base da prévia do Conversor de Corpos.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class Previa {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.cena = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(28, 1, 0.01, 50);
    this.cena.add(new THREE.HemisphereLight(0xe6ecff, 0x30302c, 1.3));
    const chave = new THREE.DirectionalLight(0xffffff, 1.9);
    chave.position.set(1.2, 2.5, 2);
    this.cena.add(chave);
    const recorte = new THREE.DirectionalLight(0xa9c6ff, 1.0);
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
    this._pedido = false;
    this._chave = null;
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
      m.material.dispose();
      this.grupo.remove(m);
    }
    this._chave = null;
    this.pedir();
  }

  // partes = [{ malha: {V, UV, T}, url }]; chave = qual uniforme (a câmera só é enquadrada de novo quando ele muda)
  async mostrar(chave, partes) {
    const texs = await Promise.all(partes.map((p) => this.carregador.loadAsync(p.url)));
    const trocou = this._chave !== chave;
    this.limpar();
    partes.forEach((p, i) => {
      const tex = texs[i];
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(p.malha.V, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(p.malha.UV, 2));
      g.setIndex(p.malha.T);
      g.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.72, metalness: 0, side: THREE.DoubleSide });
      this.grupo.add(new THREE.Mesh(g, mat));
    });
    this._chave = chave;
    if (trocou) this.enquadrar();
    this.pedir();
  }

  enquadrar() {
    this.grupo.rotation.y = 0;
    const caixa = new THREE.Box3().setFromObject(this.grupo);
    if (caixa.isEmpty()) return;
    const c = caixa.getCenter(new THREE.Vector3());
    const tam = caixa.getSize(new THREE.Vector3()).length();
    const dist = tam / (2 * Math.tan((this.camera.fov * Math.PI) / 360));
    this.controles.target.copy(c);
    this.camera.position.set(c.x + dist * 0.3, c.y + dist * 0.1, c.z + dist * 0.95);
    this.camera.near = dist / 100;
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controles.update();
    this.pedir();
  }

  definirGiro(v) { this.girando = v; this.pedir(); }
}
