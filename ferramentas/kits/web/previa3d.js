// Prévia 3D da peça (malha LOD0 exportada pelo FET) com a textura composta do editor.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class Previa3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.cena = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(28, 1, 0.01, 50);
    this.cena.add(new THREE.HemisphereLight(0xe6ecff, 0x30302c, 1.25));
    const chave = new THREE.DirectionalLight(0xffffff, 1.9);
    chave.position.set(1.2, 2.5, 2);
    this.cena.add(chave);
    const recorte = new THREE.DirectionalLight(0xa9c6ff, 1.0);
    recorte.position.set(-2, 1.5, -1.5);
    this.cena.add(recorte);
    this.cena.add(this.camera);
    this.grupo = new THREE.Group();
    this.cena.add(this.grupo);
    this.controles = new OrbitControls(this.camera, canvas);
    this.controles.enableDamping = true;
    this.controles.dampingFactor = 0.12;
    this.controles.addEventListener('change', () => this.pedir());
    this.textura = null;
    this.peca = null;
    this._pedido = false;
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
    requestAnimationFrame(() => {
      this._pedido = false;
      const mexeu = this.controles.update();
      this.renderer.render(this.cena, this.camera);
      if (mexeu) this.pedir();
    });
  }

  mostrar(peca, malha, canvasTextura) {
    if (this.peca !== peca) {
      for (const m of [...this.grupo.children]) { m.geometry.dispose(); m.material.dispose(); this.grupo.remove(m); }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(malha.V, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(malha.UV, 2));
      g.setIndex(malha.T);
      g.computeVertexNormals();
      if (!this.textura) {
        this.textura = new THREE.CanvasTexture(canvasTextura);
        this.textura.colorSpace = THREE.SRGBColorSpace;
        this.textura.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
      }
      const mat = new THREE.MeshStandardMaterial({ map: this.textura, roughness: 0.7, metalness: 0, side: THREE.DoubleSide });
      this.grupo.add(new THREE.Mesh(g, mat));
      this.peca = peca;
      this.enquadrar();
    }
    this.atualizarTextura(canvasTextura);
  }

  atualizarTextura(canvasTextura) {
    if (!this.textura) return;
    if (this.textura.image !== canvasTextura || this.textura.image.width !== canvasTextura.width) {
      this.textura.dispose();
      this.textura = new THREE.CanvasTexture(canvasTextura);
      this.textura.colorSpace = THREE.SRGBColorSpace;
      for (const m of this.grupo.children) m.material.map = this.textura;
    }
    this.textura.needsUpdate = true;
    this.pedir();
  }

  enquadrar() {
    const caixa = new THREE.Box3().setFromObject(this.grupo);
    if (caixa.isEmpty()) return;
    const c = caixa.getCenter(new THREE.Vector3());
    const tam = caixa.getSize(new THREE.Vector3()).length();
    const dist = tam / (2 * Math.tan((this.camera.fov * Math.PI) / 360));
    this.controles.target.copy(c);
    this.camera.position.set(c.x + dist * 0.25, c.y + dist * 0.1, c.z + dist * 0.97);
    this.camera.near = dist / 100;
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controles.update();
    this.pedir();
  }
}
