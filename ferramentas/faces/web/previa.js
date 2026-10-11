// Prévia 3D da cabeça (LOD0: pele, olhos e dentes) com three.js — mesma base do Editor de Estádios.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const CORES = { head_mat: 0xc9ab98, eyes_mat: 0xeeeeee, teeth_mat: 0xf1ead6 };

export class Previa {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.cena = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(28, 1, 0.01, 50);
    this.camera.position.set(0, 1.7, 1.2);
    this.cena.add(new THREE.HemisphereLight(0xdfe7ff, 0x3a3027, 1.1));
    const chave = new THREE.DirectionalLight(0xffffff, 2.2);
    chave.position.set(1.2, 2.5, 2);
    this.cena.add(chave);
    const recorte = new THREE.DirectionalLight(0x9fc0ff, 1.2);
    recorte.position.set(-2, 1.5, -1.5);
    this.cena.add(recorte);
    this.camera.add(new THREE.PointLight(0xffffff, 0.6, 0, 0));
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
    if (this.girando) { this.grupo.rotation.y += 0.008; }
    const mexeu = this.controles.update();
    this.renderer.render(this.cena, this.camera);
    if (this.girando || mexeu) this.pedir();
  }

  limpar() {
    for (const m of [...this.grupo.children]) { m.geometry.dispose(); m.material.dispose(); this.grupo.remove(m); }
    this.pedir();
  }

  mostrar(partes, { manterCamera = false } = {}) {
    this.limpar();
    for (const p of partes) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(p.V, 3));
      g.setIndex(p.T);
      g.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({ color: CORES[p.mat] ?? 0xbbbbbb, roughness: p.mat === 'eyes_mat' ? 0.25 : 0.62,
        metalness: 0, wireframe: this.arame, side: THREE.DoubleSide });
      const m = new THREE.Mesh(g, mat);
      m.userData.mat = p.mat;
      this.grupo.add(m);
    }
    if (!manterCamera) this.enquadrar();
    this.pedir();
  }

  enquadrar() {
    this.grupo.rotation.y = 0;
    const caixa = new THREE.Box3().setFromObject(this.grupo);
    if (caixa.isEmpty()) return;
    const c = caixa.getCenter(new THREE.Vector3());
    const tam = caixa.getSize(new THREE.Vector3()).length();
    const dist = tam / (2 * Math.tan((this.camera.fov * Math.PI) / 360)) * 1.05;
    this.controles.target.copy(c);
    this.camera.position.set(c.x + dist * 0.35, c.y + dist * 0.08, c.z + dist * 0.94);
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
