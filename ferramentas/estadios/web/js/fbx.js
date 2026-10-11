// Leitor de FBX binário (7.x) exportado pelo FET: geometria por seção (Model:Mesh), só o LOD0.
// Os FBX do FET são uniformes: triângulos, atributos ByVertice/Direct, sem transformação local nas seções.
// Mesmo assim o leitor trata ByPolygonVertex/IndexToDirect e polígonos maiores (leque).

const td = new TextDecoder('utf-8');

async function inflar(bytes) {
  const ds = new DecompressionStream('deflate');
  const buf = await new Response(new Blob([bytes]).stream().pipeThrough(ds)).arrayBuffer();
  return buf;
}

function lerPropriedades(dv, u8, p, n, arrays) {
  const props = [];
  for (let i = 0; i < n; i++) {
    const t = String.fromCharCode(u8[p]); p += 1;
    switch (t) {
      case 'Y': props.push(dv.getInt16(p, true)); p += 2; break;
      case 'C': props.push(u8[p] !== 0); p += 1; break;
      case 'I': props.push(dv.getInt32(p, true)); p += 4; break;
      case 'F': props.push(dv.getFloat32(p, true)); p += 4; break;
      case 'D': props.push(dv.getFloat64(p, true)); p += 8; break;
      case 'L': props.push(Number(dv.getBigInt64(p, true))); p += 8; break;
      case 'S': case 'R': {
        const len = dv.getUint32(p, true); p += 4;
        const raw = u8.subarray(p, p + len); p += len;
        props.push(t === 'S' ? td.decode(raw) : raw);
        break;
      }
      case 'f': case 'd': case 'l': case 'i': case 'b': case 'c': {
        const cnt = dv.getUint32(p, true), enc = dv.getUint32(p + 4, true), clen = dv.getUint32(p + 8, true);
        p += 12;
        const a = { arr: true, tipo: t, n: cnt, enc, bytes: u8.subarray(p, p + clen) };
        arrays.push(a);
        props.push(a);
        p += clen;
        break;
      }
      default:
        throw new Error('FBX: tipo de propriedade desconhecido ' + t);
    }
  }
  return [props, p];
}

function lerNo(dv, u8, p, v64, arrays) {
  let fim, np;
  if (v64) {
    fim = Number(dv.getBigUint64(p, true)); np = Number(dv.getBigUint64(p + 8, true)); p += 24;
  } else {
    fim = dv.getUint32(p, true); np = dv.getUint32(p + 4, true); p += 12;
  }
  const nlen = u8[p]; p += 1;
  if (fim === 0) return [null, p];
  const nome = td.decode(u8.subarray(p, p + nlen)); p += nlen;
  let props;
  [props, p] = lerPropriedades(dv, u8, p, np, arrays);
  const filhos = [];
  const sentinela = v64 ? 25 : 13;
  while (p < fim - sentinela) {
    let f;
    [f, p] = lerNo(dv, u8, p, v64, arrays);
    if (!f) break;
    filhos.push(f);
  }
  return [{ nome, props, filhos }, fim];
}

async function valores(a) {
  if (!a.dados) {
    let buf = a.enc === 1 ? await inflar(a.bytes) : a.bytes.slice().buffer;
    switch (a.tipo) {
      case 'd': a.dados = new Float64Array(buf, 0, a.n); break;
      case 'f': a.dados = new Float32Array(buf, 0, a.n); break;
      case 'i': a.dados = new Int32Array(buf, 0, a.n); break;
      case 'l': a.dados = new BigInt64Array(buf, 0, a.n); break;
      default: a.dados = new Uint8Array(buf, 0, a.n);
    }
  }
  return a.dados;
}

const filho = (no, nome) => no.filhos.find((f) => f.nome === nome);
const nomeObj = (s) => String(s).split('\u0000')[0];

export async function lerFBX(buffer) {
  const u8 = new Uint8Array(buffer);
  const dv = new DataView(buffer);
  const assinatura = td.decode(u8.subarray(0, 18));
  if (!assinatura.startsWith('Kaydara FBX Binary')) throw new Error('Não é um FBX binário');
  const versao = dv.getUint32(23, true);
  const v64 = versao >= 7500;
  const arrays = [];
  const topo = [];
  let p = 27;
  while (p < u8.length - 160) {
    let no;
    [no, p] = lerNo(dv, u8, p, v64, arrays);
    if (!no) break;
    topo.push(no);
  }
  const objetos = topo.find((n) => n.nome === 'Objects');
  const conexoes = topo.find((n) => n.nome === 'Connections');
  if (!objetos) throw new Error('FBX sem Objects');
  const porId = new Map();
  for (const o of objetos.filhos) porId.set(o.props[0], o);
  const paiDe = new Map();   // filho -> [pais] (conexões OO)
  const filhosDe = new Map();
  for (const c of conexoes ? conexoes.filhos : []) {
    if (c.props[0] !== 'OO') continue;
    const [, f, pai] = c.props;
    if (!paiDe.has(f)) paiDe.set(f, []);
    paiDe.get(f).push(pai);
    if (!filhosDe.has(pai)) filhosDe.set(pai, []);
    filhosDe.get(pai).push(f);
  }
  // LODs: Model Null "<malha>_lodN"; seções = Model:Mesh filhos do LOD0 (ou todas, se não houver LOD)
  const nulls = objetos.filhos.filter((o) => o.nome === 'Model' && o.props[2] === 'Null');
  const lod0 = nulls.find((o) => /_lod0$/i.test(nomeObj(o.props[1])));
  const lods = nulls.filter((o) => /_lod\d+$/i.test(nomeObj(o.props[1]))).length;
  const modelos = objetos.filhos.filter((o) => o.nome === 'Model' && o.props[2] === 'Mesh');
  const doLod0 = (m) => {
    if (!lod0) return true;
    let atual = m.props[0];
    for (let k = 0; k < 8; k++) {
      const pais = paiDe.get(atual) || [];
      if (pais.includes(lod0.props[0])) return true;
      const prox = pais.find((x) => porId.has(x) && porId.get(x).nome === 'Model');
      if (prox === undefined) return false;
      atual = prox;
    }
    return false;
  };
  const ossos = objetos.filhos.filter((o) => o.nome === 'Model' && o.props[2] === 'LimbNode').length;
  const secoes = [];
  for (const m of modelos) {
    if (!doLod0(m)) continue;
    const nome = nomeObj(m.props[1]);
    const geoId = (filhosDe.get(m.props[0]) || []).find((x) => porId.has(x) && porId.get(x).nome === 'Geometry');
    if (geoId === undefined) continue;
    const geo = porId.get(geoId);
    secoes.push(await geometria(nome, geo, m));
  }
  return { versao, lods, ossos, secoes };
}

function propriedade70(no, nome) {
  const p70 = filho(no, 'Properties70');
  if (!p70) return null;
  const p = p70.filhos.find((x) => x.props[0] === nome);
  return p ? p.props.slice(-3) : null;
}

async function camada(geo, tipoCamada, campo, campoIndice) {
  const out = [];
  for (const c of geo.filhos) {
    if (c.nome !== tipoCamada) continue;
    const nomeCamada = filho(c, 'Name') ? filho(c, 'Name').props[0] : '';
    const map = filho(c, 'MappingInformationType')?.props[0] || 'ByVertice';
    const ref = filho(c, 'ReferenceInformationType')?.props[0] || 'Direct';
    const dados = filho(c, campo) ? await valores(filho(c, campo).props[0]) : null;
    const idx = campoIndice && filho(c, campoIndice) ? await valores(filho(c, campoIndice).props[0]) : null;
    if (dados) out.push({ nome: nomeCamada, map, ref, dados, idx });
  }
  return out;
}

async function geometria(nome, geo, modelo) {
  const verts = await valores(filho(geo, 'Vertices').props[0]);
  const pvi = await valores(filho(geo, 'PolygonVertexIndex').props[0]);
  const normais = (await camada(geo, 'LayerElementNormal', 'Normals', 'NormalsIndex'))[0] || null;
  const uvs = await camada(geo, 'LayerElementUV', 'UV', 'UVIndex');
  const cores = (await camada(geo, 'LayerElementColor', 'Colors', 'ColorIndex'))[0] || null;
  const nv = verts.length / 3;
  const porVertice = (c) => !c || (c.map === 'ByVertice' || c.map === 'ByControlPoint') && c.ref === 'Direct';
  const simples = porVertice(normais) && uvs.every(porVertice) && porVertice(cores);

  // triângulos (leque para polígonos maiores)
  const tris = [];
  const cantos = [];   // índice do canto (polygon-vertex) de cada vértice do triângulo
  let ini = 0;
  for (let i = 0; i < pvi.length; i++) {
    if (pvi[i] < 0) {
      for (let k = ini + 1; k < i; k++) {
        tris.push(ini, k, k + 1);
      }
      ini = i + 1;
    }
  }
  const cp = (i) => { const v = pvi[i]; return v < 0 ? ~v : v; };
  let posicoes, normal, uv0, uv1, cor, indices;
  const caixa = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  const t = propriedade70(modelo, 'Lcl Translation');
  const temT = t && (t[0] || t[1] || t[2]);
  if (simples) {
    posicoes = new Float32Array(nv * 3);
    for (let i = 0; i < nv * 3; i++) posicoes[i] = verts[i] + (temT ? t[i % 3] : 0);
    if (normais) normal = Float32Array.from(normais.dados.subarray(0, nv * 3));
    if (uvs[0]) uv0 = Float32Array.from(uvs[0].dados.subarray(0, nv * 2));
    if (uvs[1]) uv1 = Float32Array.from(uvs[1].dados.subarray(0, nv * 2));
    if (cores) cor = Float32Array.from(cores.dados.subarray(0, nv * 4));
    indices = new Uint32Array(tris.length);
    for (let i = 0; i < tris.length; i++) indices[i] = cp(tris[i]);
  } else {
    // expande por canto
    const n = tris.length;
    posicoes = new Float32Array(n * 3);
    const pegar = (c, canto, comp) => {
      const vi = cp(canto);
      let k = c.map === 'ByPolygonVertex' ? canto : vi;
      if (c.ref !== 'Direct' && c.idx) k = c.idx[k];
      return k * comp;
    };
    if (normais) normal = new Float32Array(n * 3);
    if (uvs[0]) uv0 = new Float32Array(n * 2);
    if (uvs[1]) uv1 = new Float32Array(n * 2);
    if (cores) cor = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) {
      const canto = tris[i];
      const vi = cp(canto);
      for (let a = 0; a < 3; a++) posicoes[i * 3 + a] = verts[vi * 3 + a] + (temT ? t[a] : 0);
      if (normal) { const k = pegar(normais, canto, 3); for (let a = 0; a < 3; a++) normal[i * 3 + a] = normais.dados[k + a]; }
      if (uv0) { const k = pegar(uvs[0], canto, 2); uv0[i * 2] = uvs[0].dados[k]; uv0[i * 2 + 1] = uvs[0].dados[k + 1]; }
      if (uv1) { const k = pegar(uvs[1], canto, 2); uv1[i * 2] = uvs[1].dados[k]; uv1[i * 2 + 1] = uvs[1].dados[k + 1]; }
      if (cor) { const k = pegar(cores, canto, 4); for (let a = 0; a < 4; a++) cor[i * 4 + a] = cores.dados[k + a]; }
    }
    indices = null;
  }
  for (let i = 0; i < posicoes.length; i += 3) {
    for (let a = 0; a < 3; a++) {
      const v = posicoes[i + a];
      if (v < caixa[a]) caixa[a] = v;
      if (v > caixa[a + 3]) caixa[a + 3] = v;
    }
  }
  const baixo = nome.toLowerCase();
  return {
    nome,
    sombra: baixo.endsWith('_shadow') || baixo.endsWith('_zonly'),
    posicoes, normal, uv0, uv1, cor, indices,
    nomesUV: uvs.map((u) => u.nome),
    vertices: nv,
    triangulos: tris.length / 3,
    caixa,
  };
}
