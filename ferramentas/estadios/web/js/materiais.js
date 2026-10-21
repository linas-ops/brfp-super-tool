// Materiais de exibição a partir do MeshVariationDb (shader, texturas, cores).
// Só uma parte das texturas vem no export do FET; as que faltam viram uma cor estimada pelo nome da textura.
import * as THREE from 'three';
import { urlArquivo } from './api.js';

export const PARAM_COR = ['colorTexture', 'colorAnisoTexture', 'facadeColorTexture', 'frameColorTexture', 'adboardTexture', 'decalTexture', 'color2Texture'];
export const PARAM_NORMAL = ['normalTexture', 'facadeNormalTexture'];
export const NOMES_PARAM = {
  colorTexture: 'Cor', color2Texture: 'Cor 2', normalTexture: 'Relevo (normal)', normal2Texture: 'Relevo 2',
  coefficientTexture: 'Coeficientes', coefficient2Texture: 'Coeficientes 2', detailTexture: 'Detalhe', tintMaskTexture: 'Máscara de tinta',
  facadeColorTexture: 'Cor da fachada', facadeNormalTexture: 'Relevo da fachada', facadeCoeffTexture: 'Coef. da fachada',
  frameColorTexture: 'Cor da moldura', adboardTexture: 'Placa', decalTexture: 'Decalque', dataTexture: 'Dados', roomTexture: 'Interior',
  planeTexture: 'Plano', glassNormalTexture: 'Relevo do vidro', colorAnisoTexture: 'Cor (aniso)', Gradient_Texture: 'Gradiente',
  pitchlinesTexture: 'Linhas do campo',
};
export const nomeParam = (p) => NOMES_PARAM[p] || p.replace(/Texture$/, '');

// palavras inteiras dos nomes de textura/seção (ex.: "metal_painted_01_clean" -> metal, painted, clean)
const PALAVRAS = [
  [['grass', 'turf', 'lawn', 'farmland', 'field', 'foliage', 'hedge', 'tree', 'leaves'], 0x4f8a3c], [['asphalt', 'tarmac', 'road', 'street'], 0x4a4b4e],
  [['concrete', 'cement', 'stairs', 'stair', 'pavement', 'curb'], 0x9c9c98], [['brick', 'bricks'], 0x9a5a44],
  [['wood', 'wooden', 'plank', 'planks', 'timber', 'woodfloor'], 0x8b6a4a], [['rubber'], 0x3a3a3c], [['carpet'], 0x5a3b3b],
  [['glass', 'window', 'windows', 'mirror'], 0x9fc3d6], [['galvanized', 'aluminum', 'aluminium', 'steel', 'chrome', 'silver', 'brushed', 'anodized'], 0xb0b4b9],
  [['metal', 'metallic', 'iron'], 0x8e949b], [['plastic'], 0xd0d2d5], [['fabric', 'canvas', 'cloth', 'net', 'netting', 'banner'], 0xc9c9c9],
  [['led', 'screen', 'videoboard', 'videoboards', 'display', 'jumbotron'], 0x1c2a36], [['seat', 'seats', 'chair', 'chairs'], 0x3a5a9a],
  [['black', 'dark'], 0x2a2b2e], [['white'], 0xe8e8e8], [['red'], 0xb3332e], [['blue'], 0x2f5fb3], [['green'], 0x3f8a46],
  [['yellow', 'gold'], 0xd8b23a], [['orange'], 0xd8782f], [['grey', 'gray'], 0x8a8c90], [['purple', 'violet'], 0x6d4aa8],
  [['sand', 'dirt', 'soil', 'gravel', 'terrain'], 0xa58a62], [['tile', 'tiles'], 0xb8b8b4], [['painted', 'paint'], 0xb5b7ba],
];

export function corEstimada(...nomes) {
  const tokens = new Set(nomes.filter(Boolean).join(' ').toLowerCase().split(/[^a-z]+/).filter(Boolean));
  for (const [palavras, cor] of PALAVRAS) if (palavras.some((p) => tokens.has(p))) return cor;
  return 0xb4b6ba;
}

export function classeShader(shader = '', secao = '') {
  const t = new Set((shader + ' ' + secao).toLowerCase().split(/[^a-z]+/).filter(Boolean));
  const tem = (...p) => p.some((x) => t.has(x));
  if (tem('glass', 'window', 'windows', 'mirror', 'transparent')) return 'vidro';
  if (tem('alphatest', 'cutout', 'foliage', 'chainlink', 'banner', 'tifo', 'net', 'netting', 'decal', 'planar', 'grunge', 'fence', 'alpha')) return 'recorte';
  if (tem('led', 'screen', 'videoboard', 'videoboards', 'emissive', 'scoreclock', 'neon', 'jumbotron') || (tem('light') && tem('strip'))) return 'emissivo';
  if (tem('stripe', 'stripes', 'marking', 'markings', 'line', 'lines', 'logo', 'sticker')) return 'sobreposto';
  if (tem('pitch')) return 'campo';
  return 'opaco';
}

export class Materiais {
  constructor(modelo) {
    this.modelo = modelo;
    this.loader = new THREE.TextureLoader();
    this.texCache = new Map();
    this.cache = new Map();
    this.texturasLigadas = true;
    this.solido = new THREE.MeshStandardMaterial({ color: 0xb9bcc2, roughness: 0.82, metalness: 0.0 });
    this.solidoVidro = new THREE.MeshStandardMaterial({ color: 0xb9d2e0, roughness: 0.2, transparent: true, opacity: 0.3, depthWrite: false });
    this.arame = new THREE.MeshBasicMaterial({ color: 0x8fa3bf, wireframe: true, transparent: true, opacity: 0.55 });
    this.raiox = new THREE.MeshBasicMaterial({ color: 0x86a8e8, transparent: true, opacity: 0.08, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending });
    this.fantasma = new THREE.MeshBasicMaterial({ color: 0xf0565a, transparent: true, opacity: 0.18, depthWrite: false, side: THREE.DoubleSide });
    this.invisivel = new THREE.MeshBasicMaterial({ color: 0x3fc6d8, transparent: true, opacity: 0.32, depthWrite: false, side: THREE.DoubleSide });
    this.faltando = new THREE.MeshBasicMaterial({ color: 0x9d8be8, transparent: true, opacity: 0.18, depthWrite: false, side: THREE.DoubleSide });
    this.faltandoLinha = new THREE.LineBasicMaterial({ color: 0x9d8be8, transparent: true, opacity: 0.8 });
    this.selecao = new THREE.MeshBasicMaterial({ color: 0xff9233, transparent: true, opacity: 0.38, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, side: THREE.DoubleSide });
    this.marcador = new THREE.MeshBasicMaterial({ color: 0xa58cf0, transparent: true, opacity: 0.6, depthWrite: false });
  }

  // URL da imagem: PNG exportado pelo FET (se houver) ou extraído do jogo instalado
  urlTextura(asset, max) {
    if (!asset || asset === 'null') return null;
    const t = this.modelo.texturas[asset] || this.modelo.catalogo?.get(asset);
    if (t && t.png) return urlArquivo(t.png) + (t.versao ? '&v=' + t.versao : '');
    if (this.jogo?.pronto) return `/api/jogo/png?asset=${encodeURIComponent(asset)}&max=${max || this.jogo.qualidade || 1024}`;
    return null;
  }

  textura(asset, cor) {
    const url = this.urlTextura(asset);
    if (!url) return null;
    const k = asset + (cor ? '|c' : '|n') + '|' + url;
    if (!this.texCache.has(k)) {
      const tex = this.loader.load(url, () => { this.aoCarregar && this.aoCarregar(); }, undefined, () => { tex.userData.falhou = true; });
      tex.colorSpace = cor ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
      tex.anisotropy = 8;
      this.texCache.set(k, tex);
    }
    return this.texCache.get(k);
  }

  recarregarTextura(asset) {
    for (const [k, t] of this.texCache) {
      if (k.startsWith(asset + '|')) { t.dispose(); this.texCache.delete(k); }
    }
    for (const [chave, m] of this.cache) if (m.userData.texturas?.includes(asset)) { m.dispose(); this.cache.delete(chave); }
  }

  // todas as texturas e materiais são refeitos (ex.: o jogo ficou disponível ou a qualidade mudou)
  esquecerTudo() {
    for (const t of this.texCache.values()) t.dispose();
    this.texCache.clear();
    for (const m of this.cache.values()) m.dispose();
    this.cache.clear();
  }

  urlMiniatura(asset) {
    return this.urlTextura(asset, 128);
  }

  // registro: {texturas, vetores, info} editável (modelo.materiais) ou info crua do XML da malha
  material(chave, reg, secao) {
    const k = chave + (this.texturasLigadas ? '' : '|semtex');
    if (this.cache.has(k)) return this.cache.get(k);
    const m = this.criar(reg, secao);
    m.userData.chave = chave;
    this.cache.set(k, m);
    return m;
  }

  invalidar(chave) {
    for (const k of [chave, chave + '|semtex']) {
      const m = this.cache.get(k);
      if (m) { m.dispose(); this.cache.delete(k); }
    }
  }

  criar(reg, secao) {
    const info = reg?.base || reg?.info || reg || {};
    const tex = reg?.texturas || info.texturas || {};
    const vet = reg?.vetores ? Object.fromEntries(Object.entries(reg.vetores).map(([k, v]) => [k, { v, tipo: info.vetores?.[k]?.tipo }]))
      : (info.vetores || {});
    const ocultas = reg?.texOcultas || new Set();
    const shader = info.shader || '';
    const classe = classeShader(shader, secao);
    const pCor = PARAM_COR.find((p) => tex[p]);
    const pNormal = PARAM_NORMAL.find((p) => tex[p]);
    const usarTex = this.texturasLigadas;
    const mapa = usarTex && pCor && !ocultas.has(pCor) ? this.textura(tex[pCor], true) : null;
    const mapaN = usarTex && pNormal && !ocultas.has(pNormal) ? this.textura(tex[pNormal], false) : null;
    const nomeTex = pCor ? tex[pCor].split('/').pop() : Object.values(tex).map((t) => String(t).split('/').pop()).join(' ');
    const p = { roughness: 0.78, metalness: 0.0, side: THREE.FrontSide };
    const cor = new THREE.Color(mapa ? 0xffffff : corEstimada(nomeTex, secao, shader));
    const tint = vet.tintColor || vet.color || vet.Color;
    if (tint && (tint.tipo === 'Color' || tint.tipo === undefined) && tint.v) {
      const t = new THREE.Color(tint.v[0], tint.v[1], tint.v[2]);
      if (mapa || vet.tintColor) cor.multiply(t); else cor.copy(t);
    }
    p.color = cor;
    if (mapa) {
      p.map = mapa;
      const tile = vet[pCor.replace('Texture', 'Tile')]?.v;
      if (tile && (tile[0] !== 1 || tile[1] !== 1) && tile[0] > 0 && tile[1] > 0) {
        p.map = mapa.clone(); p.map.repeat.set(tile[0], tile[1]); p.map.needsUpdate = true;
      }
    }
    if (mapaN) { p.normalMap = mapaN; p.normalScale = new THREE.Vector2(1, -1); }
    if (classe === 'vidro') Object.assign(p, { transparent: true, opacity: 0.28, roughness: 0.08, depthWrite: false, side: THREE.DoubleSide });
    if (classe === 'recorte') {
      if (mapa) Object.assign(p, { alphaTest: 0.5, side: THREE.DoubleSide });
      else Object.assign(p, { transparent: true, opacity: 0.45, depthWrite: false, side: THREE.DoubleSide });
      Object.assign(p, { polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
    }
    if (classe === 'sobreposto') Object.assign(p, { polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, side: THREE.DoubleSide });
    if (classe === 'emissivo') { p.emissive = cor.clone().multiplyScalar(0.35); if (mapa) p.emissiveMap = p.map; }
    if (/metal|steel|alumin|galvan/.test(nomeTex.toLowerCase())) p.metalness = 0.25;
    const m = new THREE.MeshStandardMaterial(p);
    m.userData.texturas = Object.values(tex);
    m.userData.classe = classe;
    return m;
  }

  definirTexturasLigadas(v) {
    this.texturasLigadas = v;
  }
}
