// Modelo da cena: nós (objetos/grupos/luzes do mundo), materiais, torcida, estado de edição e alterações pendentes.
// Tudo aqui está no espaço do Frostbite (o mesmo dos XML/FBX). A exibição (viewport) aplica a sua própria raiz.
import * as THREE from 'three';

export const NOMES_AMIGAVEIS = {
  standslower: 'Arquibancada inferior', standsupper: 'Arquibancada superior', roof: 'Cobertura', pitch: 'Campo',
  exterior: 'Exterior', exterior_facade: 'Fachada', exterior_cityskirt: 'Entorno (cidade)', exterior_background: 'Fundo',
  scoreclock: 'Placar', vanities_main: 'Bandeiras e faixas da torcida', tifo_player_main: 'Mosaico (tifo)', presentation: 'Apresentação',
  snow: 'Neve', playerbenches: 'Bancos de reservas', adboards: 'Placas de publicidade', entrancetunnel: 'Túnel de entrada',
  stadium_high: 'Detalhes extras', lighting: 'Iluminação', lighting_main: 'Luzes principais', tournament: 'Torneio',
  tournament_main: 'Torneio', railings: 'Guarda-corpos', banners: 'Bandeiras e faixas', tifo_player: 'Mosaico (tifo)', vanities: 'Bandeiras e faixas da torcida',
  default: 'Padrão', streaming: 'Streaming', rain: 'Chuva', sideline: 'Lateral do campo', '5v5_dressing': 'Decoração 5v5',
  events_stadium_517_set: 'Cenário externo', crowd: 'Torcida', trophy: 'Troféu', volume_decals: 'Decalques',
  lighting_roof: 'Luzes da cobertura', lighting_roof_main: 'Luzes da cobertura', lighting_stands: 'Luzes das arquibancadas',
  lighting_stands_main: 'Luzes das arquibancadas', lighting_vip: 'Luzes do camarote', lighting_vip_main: 'Luzes do camarote',
  lighting_tunnels: 'Luzes dos túneis', lighting_tunnels_main: 'Luzes dos túneis', lighting_concourse: 'Luzes do saguão',
  lighting_concourse_main: 'Luzes do saguão', lighting_entrance_tunnel: 'Luzes do túnel de entrada',
  lighting_entrance_tunnel_main: 'Luzes do túnel de entrada', lighting_pitch: 'Luzes do campo', lighting_pitch_main: 'Luzes do campo',
  lighting_volumes: 'Volumes de luz', lighting_lightshow: 'Show de luzes', lighting_lightshow_main: 'Show de luzes',
};
const TIPO_ROTULO = {
  mundo: 'Mundo', subworld: 'Sub-mundo', worldpart: 'World part', layer: 'Camada', smg: 'Grupo estático',
  membro: 'Malha repetida', inst: 'Cópia (grupo estático)', ref: 'Objeto', prefab: 'Prefab', luz: 'Luz', marcador: 'Pessoa da lateral',
};
const TIPO_LUZ = { spot: 'Spot', esfera: 'Pontual', tubo: 'Tubo', retangulo: 'Retangular' };
export const rotuloTipo = (n) => (n.tipo === 'luz' ? `Luz ${(TIPO_LUZ[n.luz?.tipo] || '').toLowerCase()}`.trim()
  : n.tipo === 'marcador' ? (n.categoria === 'choreo_seats' ? 'Assento do banco de reservas' : 'Pessoa da lateral') : TIPO_ROTULO[n.tipo] || n.tipo);
// campos de luz que o editor altera: chave no modelo -> campo no XML
export const CAMPOS_LUZ = { cor: 'Color', intensidade: 'Intensity', raio: 'AttenuationRadius', angulo: 'OuterAngle',
  largura: 'Width', altura: 'Height', comprimento: 'Length' };
// colunas do stadiums.txt que o editor altera
export const COLUNAS_ZONA = { casa: ['stadhometechzoneminx', 'stadhometechzonemaxx', 'stadhometechzoneminz', 'stadhometechzonemaxz'],
  fora: ['stadawaytechzoneminx', 'stadawaytechzonemaxx', 'stadawaytechzoneminz', 'stadawaytechzonemaxz'] };
export const ehGrupo = (n) => ['mundo', 'subworld', 'worldpart', 'layer', 'smg', 'membro'].includes(n.tipo);
const QUEDA = 150;   // metros: o que a lógica do jogo usa não pode ser excluído; vai para baixo do chão
const copia = (o) => JSON.parse(JSON.stringify(o));

export function mat4De12(t, m = new THREE.Matrix4()) {
  return m.set(t[0], t[3], t[6], t[9], t[1], t[4], t[7], t[10], t[2], t[5], t[8], t[11], 0, 0, 0, 1);
}
export function m12De(m) {
  const e = m.elements;
  return [e[0], e[1], e[2], e[4], e[5], e[6], e[8], e[9], e[10], e[12], e[13], e[14]];
}
const iguais12 = (a, b, tol = 1e-5) => a.every((v, i) => Math.abs(v - b[i]) <= tol * Math.max(1, Math.abs(b[i])));
const vetDif = (a, b) => !b || a.some((x, i) => Math.abs(x - b[i]) > 1e-6);

export class Modelo extends EventTarget {
  constructor() {
    super();
    this.limpar();
  }

  limpar() {
    this.nos = [];
    this.malhas = {};
    this.mvdbs = {};
    this.texturas = {};
    this.materiais = new Map();   // variação -> registro editável
    this.selecao = new Set();
    this.ativo = -1;
    this.porAlvo = new Map();
    this.mundo = null;
    this.torcida = null;
    this.campo = { comprimento: 105, largura: 68 };
    this.estadio = null;          // linha do stadiums.txt: {original, atual}
    this.nNovas = 0;
  }

  emitir(tipo, detalhe = {}) { this.dispatchEvent(new CustomEvent(tipo, { detail: detalhe })); }

  carregar(j) {
    this.limpar();
    this.dados = j;
    this.mundo = j.mundo;
    this.malhas = j.malhas;
    this._pastasProprias = null;
    this.mvdbs = j.mvdbs;
    this.texturas = j.texturas;
    this.nuvens = j.nuvens || [];
    this.pastas = j.pastas || [];
    this.campo = j.campo || this.campo;
    if (this.campo.arquivo && this.campo.espelhado !== null && this.campo.espelhado !== undefined) {
      const est = { espelhado: !!this.campo.espelhado, zonas: copia(this.campo.zonas || {}), comprimento: this.campo.comprimento, largura: this.campo.largura };
      this.estadio = { original: est, atual: copia(est) };
    }
    const nos = j.nos;
    for (const n of nos) {
      n.filhos = [];
      n.prof = n.pai >= 0 ? nos[n.pai].prof + 1 : 0;
      n.visEditor = true;
      n.localArquivo = n.local.slice();
      n.jogo0 = n.jogo ? { ...n.jogo } : null;
      if (n.pai >= 0) nos[n.pai].filhos.push(n.id);
      n.chave = n.alvo ? `${n.alvo.arq}|${n.alvo.guid}|${n.alvo.membro ?? ''}|${n.alvo.indice ?? ''}` : null;
      if (n.chave) {
        if (!this.porAlvo.has(n.chave)) this.porAlvo.set(n.chave, []);
        this.porAlvo.get(n.chave).push(n.id);
      }
      n.rotulo = this.rotuloNo(n);
      if (n.luz) n.luz0 = copia(n.luz);
    }
    this.nos = nos;
    this.calcularMundos();
    // objetos que já estão 150 m abaixo do chão (ocultos por rebaixamento, pelo editor ou pelo conversor)
    for (const n of nos) {
      if (!n.alvo || !n.jogo || n.tipo === 'luz') continue;
      if (n.mundoM.elements[13] < -100 && (n.malhas?.length || n.filhos.length)) {
        n.jogo.rebaixado = true;
        n.jogo0.rebaixado = true;
        n.local = this.deslocarY(n, n.local, +QUEDA);
      }
    }
    for (const n of nos) n.local0 = n.local.slice();
    this.calcularMundos();
    // contagens para a árvore
    for (let i = nos.length - 1; i >= 0; i--) {
      const n = nos[i];
      n.nGeo = (n.malhas?.length ? 1 : 0) + (n.faltando === 'blueprint' ? 1 : 0);
      n.nLuz = n.tipo === 'luz' ? 1 : 0;
      for (const f of n.filhos) { n.nGeo += nos[f].nGeo; n.nLuz += nos[f].nLuz; }
    }
    // materiais editáveis (MVDB)
    for (const [mvdb, ent] of Object.entries(this.mvdbs)) {
      for (const [malha, mats] of Object.entries(ent.entradas)) this.registrarMateriais(mvdb, ent.arq, malha, mats);
    }
    this.emitir('carregado');
  }

  registrarMateriais(mvdb, arq, malha, mats) {
    mats.forEach((m, i) => {
      if (!m.variacao || this.materiais.has(m.variacao)) return;
      const base = { shader: m.shader, texturas: { ...(m.texturas || {}) }, vetores: copia(m.vetores || {}) };
      this.materiais.set(m.variacao, {
        variacao: m.variacao, mvdb, arq, malha, indice: i, info: m, base, copiadoDe: null,
        texturas: { ...base.texturas }, vetores: Object.fromEntries(Object.entries(base.vetores).map(([k, v]) => [k, v.v.slice()])),
        texOcultas: new Set(),
      });
    });
  }

  // entrada nova no MVDB do sub-mundo (malha que não tinha): passa a valer para os materiais desta malha
  adicionarEntradaMvdb(mvdb, malha, mats, texturas = {}) {
    const ent = this.mvdbs[mvdb];
    ent.entradas[malha] = mats;
    for (const [a, t] of Object.entries(texturas)) if (!this.texturas[a]) this.texturas[a] = t;
    this.registrarMateriais(mvdb, ent.arq, malha, mats);
  }

  rotuloNo(n) {
    const base = (n.nome || '').toLowerCase();
    if (n.tipo === 'smg') return 'Grupo estático';
    if (n.tipo === 'inst' || n.tipo === 'luz' || n.tipo === 'marcador') return n.nome;
    if (['worldpart', 'layer', 'subworld'].includes(n.tipo)) return NOMES_AMIGAVEIS[base] || n.nome;
    return n.nome;
  }

  calcularMundos(ini = 0) {
    const nos = this.nos;
    const pilha = ini === 0 ? nos.filter((n) => n.pai < 0).map((n) => n.id) : [ini];
    while (pilha.length) {
      const n = nos[pilha.pop()];
      n.localM = mat4De12(n.local, n.localM || new THREE.Matrix4());
      n.mundoM = n.mundoM || new THREE.Matrix4();
      if (n.pai >= 0) n.mundoM.multiplyMatrices(nos[n.pai].mundoM, n.localM);
      else n.mundoM.copy(n.localM);
      for (const f of n.filhos) pilha.push(f);
    }
  }

  paiMundo(n) { return n.pai >= 0 ? this.nos[n.pai].mundoM : new THREE.Matrix4(); }

  deslocarY(n, local, dy) {
    const P = this.paiMundo(n);
    const W = new THREE.Matrix4().multiplyMatrices(P, mat4De12(local));
    W.premultiply(new THREE.Matrix4().makeTranslation(0, dy, 0));
    return m12De(W.premultiply(P.clone().invert()));
  }

  // local que leva n à matriz de mundo W (espaço do arquivo)
  localPara(n, W) {
    return m12De(new THREE.Matrix4().multiplyMatrices(this.paiMundo(n).clone().invert(), W));
  }

  ancestrais(n) {
    const out = [];
    let p = n.pai;
    while (p >= 0) { out.push(this.nos[p]); p = this.nos[p].pai; }
    return out;
  }

  descendentes(n, incluir = true) {
    const out = [];
    const pilha = [n.id];
    while (pilha.length) {
      const i = pilha.pop();
      if (i !== n.id || incluir) out.push(this.nos[i]);
      for (const f of this.nos[i].filhos) pilha.push(f);
    }
    return out;
  }

  // ------------------------------------------------------------ estado
  alterado(n) {
    if (n.nova) return !n.removido;
    if (n.removido) return true;
    if (n.luz && n.luz0 && this.camposLuz(n)) return true;
    if (n.alvo && !iguais12(n.local, n.local0)) return true;
    if (n.jogo && n.jogo0 && (!!n.jogo.excluido !== !!n.jogo0.excluido || n.jogo.visivel !== n.jogo0.visivel
      || !!n.jogo.rebaixado !== !!n.jogo0.rebaixado || n.jogo.habilitada !== n.jogo0.habilitada)) return true;
    return false;
  }

  ocultoNoJogoProprio(n) {
    if (!n.jogo) return false;
    return !!n.jogo.excluido || n.jogo.visivel === false || !!n.jogo.rebaixado || n.jogo.habilitada === false;
  }

  ocultoNoJogo(n) {
    if (this.ocultoNoJogoProprio(n)) return true;
    return this.ancestrais(n).some((a) => this.ocultoNoJogoProprio(a));
  }

  visivelEditor(n) {
    if (!n.visEditor) return false;
    let p = n.pai;
    while (p >= 0) { if (!this.nos[p].visEditor) return false; p = this.nos[p].pai; }
    return true;
  }

  temLigadoAbaixo(n) { return this.descendentes(n).some((d) => d.ligado); }

  // ------------------------------------------------------------ seleção
  selecionar(ids, { modo = 'substituir', ativo = null } = {}) {
    const lista = (Array.isArray(ids) ? ids : [ids]).filter((i) => i >= 0);
    if (modo === 'substituir') this.selecao = new Set(lista);
    else if (modo === 'adicionar') lista.forEach((i) => this.selecao.add(i));
    else if (modo === 'alternar') lista.forEach((i) => (this.selecao.has(i) ? this.selecao.delete(i) : this.selecao.add(i)));
    else if (modo === 'remover') lista.forEach((i) => this.selecao.delete(i));
    this.ativo = ativo ?? (lista.length ? lista[lista.length - 1] : (this.selecao.size ? [...this.selecao].pop() : -1));
    if (!this.selecao.has(this.ativo)) this.ativo = this.selecao.size ? [...this.selecao].pop() : -1;
    this.emitir('selecao');
  }

  // ------------------------------------------------------------ edições (chamadas pelo histórico)
  definirLocais(mapa) {
    // mapa: chave de alvo (ou "id:N" para nós sem alvo) -> local[12]
    const tocados = new Set();
    for (const [k, local] of mapa) {
      const ids = k.startsWith('id:') ? [Number(k.slice(3))] : (this.porAlvo.get(k) || []);
      for (const id of ids) { this.nos[id].local = local.slice(); tocados.add(id); }
    }
    for (const id of tocados) this.calcularMundos(id);
    this.emitir('locais', { ids: [...tocados] });
  }

  chaveDe(n) { return n.chave || `id:${n.id}`; }

  definirJogo(mapa) {
    // mapa: id -> {estado jogo, local}
    const ids = [];
    for (const [id, v] of mapa) {
      const n = this.nos[id];
      for (const outro of (n.chave ? this.porAlvo.get(n.chave) : [id])) {
        this.nos[outro].jogo = { ...v.jogo };
        if (v.local) this.nos[outro].local = v.local.slice();
        ids.push(outro);
      }
    }
    for (const id of ids) this.calcularMundos(id);
    this.emitir('jogo', { ids });
  }

  // ------------------------------------------------------------ luzes criadas / excluídas / campos
  // nó novo (luz criada no editor): fica no fim da lista; desfazer marca como removido (os ids não mudam)
  adicionarNo(n) {
    n.id = this.nos.length;
    n.filhos = [];
    n.prof = n.pai >= 0 ? this.nos[n.pai].prof + 1 : 0;
    n.visEditor = true;
    n.localArquivo = n.local.slice();
    n.local0 = n.local.slice();
    n.jogo0 = n.jogo ? { ...n.jogo } : null;
    n.chave = `${n.alvo.arq}|${n.alvo.guid || 'nova:' + n.chaveNova}||`;
    this.porAlvo.set(n.chave, [n.id]);
    n.rotulo = this.rotuloNo(n);
    n.nGeo = 0; n.nLuz = n.tipo === 'luz' ? 1 : 0;
    this.nos.push(n);
    if (n.pai >= 0) this.nos[n.pai].filhos.push(n.id);
    this.calcularMundos(n.id);
    this.emitir('estrutura', { ids: [n.id], adicionados: [n.id] });
    return n;
  }

  definirRemovidos(ids, removido) {
    for (const id of ids) {
      const n = this.nos[id];
      n.removido = removido;
      if (removido) this.selecao.delete(id);
    }
    this.emitir('estrutura', { ids, removidos: removido ? ids : [] });
    this.emitir('selecao');
  }

  camposLuz(n) {
    // {campoXML: valor} do que mudou numa luz (ou tudo, para luzes novas)
    const out = {};
    for (const [k, campo] of Object.entries(CAMPOS_LUZ)) {
      const v = n.luz?.[k], v0 = n.luz0?.[k];
      if (v === undefined) continue;
      const mudou = Array.isArray(v) ? vetDif(v, v0) : Math.abs(v - (v0 ?? NaN)) > 1e-6 || v0 === undefined;
      if (n.nova ? k in (n.luzTocada || {}) : mudou) out[campo] = Array.isArray(v) ? v.slice() : v;
    }
    return Object.keys(out).length ? out : null;
  }

  definirLuzes(mapa) {
    // mapa: id -> luz (objeto completo)
    const ids = [];
    for (const [id, luz] of mapa) {
      const n = this.nos[id];
      n.luz = copia(luz);
      if (n.nova) n.luzTocada = { ...(n.luzTocada || {}), ...Object.fromEntries(Object.keys(luz).map((k) => [k, true])) };
      ids.push(id);
    }
    this.emitir('luz', { ids });
  }

  definirEstadio(est) {
    if (!this.estadio) return;
    this.estadio.atual = copia(est);
    this.emitir('estadio');
  }

  estadioAlterado() {
    return !!this.estadio && JSON.stringify(this.estadio.atual) !== JSON.stringify(this.estadio.original);
  }

  definirVisEditor(ids, vis) {
    for (const id of ids) this.nos[id].visEditor = vis;
    this.emitir('visEditor', { ids });
  }

  definirTextura(variacao, param, asset) {
    const m = this.materiais.get(variacao);
    if (asset === undefined || asset === null) delete m.texturas[param]; else m.texturas[param] = asset;
    this.emitir('material', { variacao });
  }

  definirVetor(variacao, param, v) {
    const m = this.materiais.get(variacao);
    m.vetores[param] = v.slice();
    this.emitir('material', { variacao });
  }

  // estado completo de um material (para desfazer cópias)
  fotoMaterial(variacao) {
    const m = this.materiais.get(variacao);
    return copia({ base: m.base, copiadoDe: m.copiadoDe, texturas: m.texturas, vetores: m.vetores });
  }

  restaurarMaterial(variacao, foto) {
    const m = this.materiais.get(variacao);
    const f = copia(foto);
    Object.assign(m, { base: f.base, copiadoDe: f.copiadoDe, texturas: f.texturas, vetores: f.vetores });
    this.emitir('material', { variacao });
  }

  // copia shader e parâmetros (como estão no arquivo) da variação origem para a destino
  copiarMaterial(destino, origem) {
    const d = this.materiais.get(destino), o = this.materiais.get(origem);
    d.base = copia(o.base);
    d.copiadoDe = { variacao_origem: origem, arq_origem: o.arq, shader: o.base.shader };
    d.texturas = { ...o.base.texturas };
    d.vetores = Object.fromEntries(Object.entries(o.base.vetores).map(([k, v]) => [k, v.v.slice()]));
    this.emitir('material', { variacao: destino });
  }

  definirTorcida(dados) {
    if (!this.torcida) return;
    this.torcida.atual = dados;
    this.emitir('torcida');
  }

  // ------------------------------------------------------------ ocultar no jogo: decide o mecanismo seguro
  estadoOcultar(n, ocultar) {
    // devolve {jogo, local} ou {erro}
    if (!n.jogo) return { erro: 'Este item não pode ser ocultado no jogo sozinho; oculte o grupo ou os itens dele.' };
    const j = { ...n.jogo };
    const local = n.local;
    if ('habilitada' in j) { j.habilitada = !ocultar; return { jogo: j, local }; }   // luz: Enabled
    if (!ocultar) {
      if (j.rebaixado) j.rebaixado = false;
      if ('excluido' in j) j.excluido = false;
      if ('visivel' in j) j.visivel = true;
      return { jogo: j, local };
    }
    if ('visivel' in j) {               // cópia de grupo estático: Visible=false e 150 m abaixo (ainda projeta sombra)
      j.visivel = false; j.rebaixado = true;
      return { jogo: j, local };
    }
    if (ehGrupo(n)) {
      if (this.temLigadoAbaixo(n)) {
        return { erro: 'Este grupo tem objetos ligados à lógica do jogo (placar, telões, etc.). Excluir o grupo inteiro pode travar o jogo; oculte os itens um a um.' };
      }
      j.excluido = true;
      return { jogo: j, local };
    }
    if (n.ligado) { j.rebaixado = true; return { jogo: j, local, rebaixado: true }; }
    j.excluido = true;
    return { jogo: j, local };
  }

  // ------------------------------------------------------------ alterações pendentes -> lista para o servidor
  localArquivo(n) {
    return n.jogo?.rebaixado ? this.deslocarY(n, n.local, -QUEDA) : n.local;
  }

  materialAlterado(m) {
    if (m.copiadoDe) return true;
    for (const [p, a] of Object.entries(m.texturas)) if (a !== m.base.texturas[p]) return true;
    for (const [p, v] of Object.entries(m.vetores)) if (m.base.vetores[p] && vetDif(v, m.base.vetores[p].v)) return true;
    return false;
  }

  pendentes() {
    const alts = [];
    const vistos = new Set();
    const movidos = [];
    for (const n of this.nos) {
      if (!n.alvo || vistos.has(n.chave)) continue;
      vistos.add(n.chave);
      const a = n.alvo;
      if (n.nova) {
        if (!n.removido) alts.push({ tipo: 'luz_nova', arq: a.arq, modelo: a.modelo, chave: n.chaveNova, t: this.localArquivo(n), valores: this.camposLuz(n) || {} });
        continue;
      }
      if (n.removido) { alts.push({ tipo: 'luz_excluir', arq: a.arq, guid: a.guid }); continue; }
      if (n.luz && n.luz0) {
        const v = this.camposLuz(n);
        if (v) alts.push({ tipo: 'campos', arq: a.arq, guid: a.guid, valores: v });
      }
      const novoT = this.localArquivo(n);
      if (!iguais12(novoT, n.localArquivo)) {
        if (a.membro !== undefined) alts.push({ tipo: 'transform_smg', arq: a.arq, guid: a.guid, membro: a.membro, indice: a.indice, t: novoT });
        else alts.push({ tipo: 'transform', arq: a.arq, guid: a.guid, campo: a.campo, t: novoT });
        if (n.tipo !== 'luz') movidos.push(n);
      }
      if (n.jogo && n.jogo0) {
        if ('excluido' in n.jogo && !!n.jogo.excluido !== !!n.jogo0.excluido) alts.push({ tipo: 'excluido', arq: a.arq, guid: a.guid, valor: !!n.jogo.excluido });
        if ('visivel' in n.jogo && n.jogo.visivel !== n.jogo0.visivel) alts.push({ tipo: 'visivel_smg', arq: a.arq, guid: a.guid, membro: a.membro, indice: a.indice, valor: n.jogo.visivel });
        if ('habilitada' in n.jogo && n.jogo.habilitada !== n.jogo0.habilitada) alts.push({ tipo: 'campo', arq: a.arq, guid: a.guid, campo: 'Enabled', valor: n.jogo.habilitada ? 'true' : 'false' });
      }
    }
    // entradas de iluminação (LightmapGenMeshInstance) das malhas que mudaram de lugar
    for (const n of movidos) {
      const arqs = [n, ...this.ancestrais(n)].filter((x) => x.tipo === 'subworld' || x.tipo === 'mundo').map((x) => x.arq).filter(Boolean);
      const W0 = this.mundoArquivo(n, true), W1 = this.mundoArquivo(n, false);
      for (const d of this.descendentes(n)) {
        for (const p of d.malhas || []) {
          const rel = new THREE.Matrix4().multiplyMatrices(this.relativo(n, d), mat4De12(p.t));
          const de = m12De(new THREE.Matrix4().multiplyMatrices(W0, rel));
          const para = m12De(new THREE.Matrix4().multiplyMatrices(W1, rel));
          alts.push({ tipo: 'lightmap', malha: this.malhas[p.m]?.asset || p.m, de, para, arqs });
        }
      }
    }
    for (const m of this.materiais.values()) {
      if (m.copiadoDe) alts.push({ tipo: 'material_copiar', arq: m.arq, variacao: m.variacao, variacao_origem: m.copiadoDe.variacao_origem, arq_origem: m.copiadoDe.arq_origem });
      for (const [p, asset] of Object.entries(m.texturas)) {
        const naBase = p in m.base.texturas;
        if (naBase && asset === m.base.texturas[p]) continue;
        const t = this.texturas[asset] || this.catalogo?.get(asset);
        if (!t || !t.ref) continue;
        alts.push({ tipo: naBase ? 'textura' : 'textura_adicionar', arq: m.arq, variacao: m.variacao, parametro: p, asset: t.nome || asset, ref: t.ref, pguid: t.pguid });
      }
      for (const [p, v] of Object.entries(m.vetores)) {
        if (m.base.vetores[p] && vetDif(v, m.base.vetores[p].v)) alts.push({ tipo: 'vetor', arq: m.arq, variacao: m.variacao, parametro: p, v });
      }
    }
    if (this.torcida && this.torcida.atual !== this.torcida.original) {
      const t = this.torcida.atual;
      alts.push({ tipo: 'torcida', arq: this.torcida.arq, posicoes: Array.from(t.posicoes), mapas: Object.fromEntries(Object.entries(t.mapas).map(([k, v]) => [k, Array.from(v)])) });
    }
    if (this.estadioAlterado()) alts.push({ tipo: 'estadio', arquivo: this.campo.arquivo, id: this.campo.id, valores: this.colunasEstadio() });
    return alts;
  }

  // colunas do stadiums.txt que mudaram (cm inteiros, como a tabela guarda)
  colunasEstadio() {
    const a = this.estadio.atual, o = this.estadio.original;
    const out = {};
    if (a.espelhado !== o.espelhado) out.ismirrored = a.espelhado ? '1' : '0';
    for (const [lado, cols] of Object.entries(COLUNAS_ZONA)) {
      (a.zonas?.[lado] || []).forEach((v, i) => { if (Math.abs(v - (o.zonas?.[lado]?.[i] ?? NaN)) > 1e-4 || o.zonas?.[lado] === undefined) out[cols[i]] = String(Math.round(v * 100)); });
    }
    if (Math.abs(a.comprimento - o.comprimento) > 1e-4) out.stadiumpitchlength = String(Math.round(a.comprimento * 100));
    if (Math.abs(a.largura - o.largura) > 1e-4) out.stadiumpitchwidth = String(Math.round(a.largura * 100));
    return out;
  }

  // matriz de mundo (espaço do arquivo) de n: original (como está no XML) ou atual
  mundoArquivo(n, original) {
    const cadeia = [n, ...this.ancestrais(n)].reverse();
    const M = new THREE.Matrix4();
    for (const x of cadeia) {
      const t = original ? x.localArquivo : this.localArquivo(x);
      M.multiply(mat4De12(t));
    }
    return M;
  }

  relativo(raiz, d) {
    const M = new THREE.Matrix4();
    const cadeia = [];
    let x = d;
    while (x && x.id !== raiz.id) { cadeia.push(x); x = x.pai >= 0 ? this.nos[x.pai] : null; }
    for (const y of cadeia.reverse()) M.multiply(mat4De12(this.localArquivo(y)));
    return M;
  }

  contarPendentes() {
    let n = 0;
    const vistos = new Set();
    for (const no of this.nos) {
      if (no.chave && !vistos.has(no.chave)) { vistos.add(no.chave); if (this.alterado(no)) n++; }
    }
    for (const m of this.materiais.values()) if (this.materialAlterado(m)) n++;
    if (this.torcida && this.torcida.atual !== this.torcida.original) n++;
    if (this.estadioAlterado()) n++;
    return n;
  }

  // depois de gravar: o estado atual vira o original
  confirmarGravado(novas = {}) {
    for (const n of this.nos) {
      if (n.nova && !n.removido && novas[n.chaveNova]) {
        // a luz criada passa a existir no arquivo com o GUID que o servidor deu
        this.porAlvo.delete(n.chave);
        n.alvo = { ...n.alvo, guid: novas[n.chaveNova] };
        delete n.alvo.modelo;
        n.chave = `${n.alvo.arq}|${n.alvo.guid}||`;
        this.porAlvo.set(n.chave, [n.id]);
        n.nova = false;
        delete n.luzTocada;
      } else if (n.removido && !n.nova) {
        this.porAlvo.delete(n.chave);
        n.alvo = null;
        n.chave = null;
        n.excluidaGravada = true;
      }
      if (n.alvo) n.localArquivo = this.localArquivo(n).slice();
      n.local0 = n.local.slice();
      if (n.jogo) n.jogo0 = { ...n.jogo };
      if (n.luz) n.luz0 = copia(n.luz);
    }
    if (this.estadio) this.estadio.original = copia(this.estadio.atual);
    for (const m of this.materiais.values()) {
      const vet = {};
      for (const [p, v] of Object.entries(m.vetores)) if (m.base.vetores[p]) vet[p] = { tipo: m.base.vetores[p].tipo, v: v.slice() };
      m.base = { shader: m.copiadoDe ? m.copiadoDe.shader : m.base.shader, texturas: { ...m.texturas }, vetores: vet };
      m.copiadoDe = null;
      m.info = { ...m.info, shader: m.base.shader, texturas: { ...m.texturas }, vetores: copia(vet) };
    }
    if (this.torcida) this.torcida.original = this.torcida.atual;
    if (this.estadio) {
      Object.assign(this.campo, { espelhado: this.estadio.atual.espelhado, zonas: copia(this.estadio.atual.zonas),
        comprimento: this.estadio.atual.comprimento, largura: this.estadio.atual.largura });
    }
    this.emitir('gravado');
  }

  // ------------------------------------------------------------ projeto: exporta/importa o que mudou
  exportarEstado() {
    const nos = [];
    const vistos = new Set();
    for (const n of this.nos) {
      if (!n.chave || vistos.has(n.chave)) continue;
      vistos.add(n.chave);
      if (!this.alterado(n)) continue;
      if (n.nova) {
        const pai = this.nos[n.pai];
        nos.push({ nova: true, paiK: pai?.chave || null, paiId: n.pai, arq: n.alvo.arq, modelo: n.alvo.modelo, nome: n.nome,
          local: n.local, luz: n.luz, luzTocada: n.luzTocada || {} });
      } else nos.push({ k: n.chave, local: n.local, jogo: n.jogo, luz: n.luz && this.camposLuz(n) ? n.luz : undefined, removido: n.removido || undefined });
    }
    const materiais = [];
    for (const m of this.materiais.values()) {
      if (this.materialAlterado(m)) materiais.push({ variacao: m.variacao, texturas: m.texturas, vetores: m.vetores, copiadoDe: m.copiadoDe });
    }
    const texturasUsadas = {};
    for (const m of materiais) for (const a of Object.values(m.texturas)) if (this.texturas[a]) texturasUsadas[a] = this.texturas[a];
    let torcida = null;
    if (this.torcida && this.torcida.atual !== this.torcida.original) {
      const t = this.torcida.atual;
      torcida = { arq: this.torcida.arq, posicoes: Array.from(t.posicoes), mapas: Object.fromEntries(Object.entries(t.mapas).map(([k, v]) => [k, Array.from(v)])) };
    }
    const estadio = this.estadioAlterado() ? copia(this.estadio.atual) : null;
    return { nos, materiais, texturas: texturasUsadas, torcida, estadio };
  }

  importarEstado(e) {
    const avisos = [];
    for (const [a, t] of Object.entries(e.texturas || {})) if (!this.texturas[a]) this.texturas[a] = t;
    const novas = [];
    for (const x of e.nos || []) {
      if (x.nova) { novas.push(x); continue; }
      const ids = this.porAlvo.get(x.k);
      if (!ids) { avisos.push(x.k); continue; }
      for (const id of ids) {
        const n = this.nos[id];
        n.local = x.local.slice();
        if (x.jogo && n.jogo) n.jogo = { ...x.jogo };
        if (x.luz && n.luz) n.luz = copia(x.luz);
        if (x.removido) n.removido = true;
      }
    }
    for (const x of novas) {
      const pai = x.paiK ? (this.porAlvo.get(x.paiK) || [])[0] : x.paiId;
      if (pai === undefined || !this.nos[pai]) { avisos.push(x.nome); continue; }
      this.nNovas++;
      this.adicionarNo({ pai, tipo: 'luz', nome: x.nome, local: x.local.slice(), nova: true, chaveNova: `p${Date.now()}_${this.nNovas}`,
        alvo: { arq: x.arq, guid: null, campo: 'Transform', modelo: x.modelo }, jogo: { habilitada: true }, luz: copia(x.luz),
        luz0: copia(x.luz), luzTocada: x.luzTocada });
    }
    if (e.estadio && this.estadio) this.estadio.atual = copia(e.estadio);
    this.calcularMundos();
    for (const x of e.materiais || []) {
      const m = this.materiais.get(x.variacao);
      if (!m) { avisos.push(x.variacao); continue; }
      if (x.copiadoDe && this.materiais.has(x.copiadoDe.variacao_origem)) this.copiarMaterial(x.variacao, x.copiadoDe.variacao_origem);
      m.texturas = { ...x.texturas };
      m.vetores = copia(x.vetores);
    }
    const ids = this.nos.map((n) => n.id);
    this.emitir('locais', { ids });
    this.emitir('jogo', { ids });
    for (const m of this.materiais.values()) this.emitir('material', { variacao: m.variacao });
    return { avisos, torcida: e.torcida || null };
  }

  // ------------------------------------------------------------ materiais de uma peça
  // textura que só outro estádio carrega (fica na pasta de componentes/mundo dele): o jogo não a carrega neste
  // mundo e o material fica sem ela. Devolve o nome do outro estádio, ou null.
  outroEstadio(asset) {
    const m = String(asset || '').toLowerCase().match(/\/(?:components\/stadiums|stadiums)\/([^/]+)\//);
    if (!m) return null;
    const mundo = String(this.mundo || '').toLowerCase().split('/').pop();
    const base = mundo.replace(/_\d+$/, '');
    const nome = m[1].replace(/_\d+$/, '');
    if (!nome || nome === base) return null;
    // pasta que as malhas deste estádio também usam: é deste estádio, mesmo com outro nome
    if (!this._pastasProprias) {
      this._pastasProprias = new Set();
      for (const i of Object.values(this.malhas || {})) {
        const p = String(i.asset || '').toLowerCase().match(/\/(?:components\/stadiums|stadiums)\/([^/]+)\//);
        if (p) this._pastasProprias.add(p[1]);
      }
    }
    return this._pastasProprias.has(m[1]) ? null : m[1];
  }

  materiaisDe(n, chaveMalha) {
    const malha = this.malhas[chaveMalha];
    let ent = this.mvdbs[n.mvdb]?.entradas?.[chaveMalha];
    let mvdb = n.mvdb;
    if (!ent && malha?.mvdb_extra) { ent = this.mvdbs[malha.mvdb_extra]?.entradas?.[chaveMalha]; mvdb = malha.mvdb_extra; }
    return { lista: ent || null, mvdb, xml: malha?.materiais || [] };
  }

  // nomes de parâmetros de textura que outros materiais com o mesmo shader usam
  parametrosDoShader(shader) {
    const s = new Set();
    for (const m of this.materiais.values()) if (m.base.shader === shader) Object.keys(m.base.texturas).forEach((p) => s.add(p));
    return [...s].sort();
  }
}
