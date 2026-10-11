// Modelo do overlay aberto: filmes (o arquivo e os componentes importados), operações de edição e a árvore
// de exibição (o que aparece na tela, com matrizes e cores já compostas).
import { api } from './api.js';
import { lerDDS } from './dds.js';

const F_RECORTE = 64;
const RX_TEXTO = /(MultiText|TextBox|AnimatedText|ButtonText|Text)$/i;
const RX_IMAGEM = /(ImageLoader|PlayerHead|LeagueLogo|PlayerDisplay|Crest|Logo)$/i;

// ---------------------------------------------------------------- matrizes 2D (a, b, c, d, tx, ty)
// x' = a·x + c·y + tx ; y' = b·x + d·y + ty  (convenção do Flash/APT)
export const M = {
  id: () => [1, 0, 0, 1, 0, 0],
  mul(p, l) { // p ∘ l
    return [p[0] * l[0] + p[2] * l[1], p[1] * l[0] + p[3] * l[1], p[0] * l[2] + p[2] * l[3], p[1] * l[2] + p[3] * l[3],
      p[0] * l[4] + p[2] * l[5] + p[4], p[1] * l[4] + p[3] * l[5] + p[5]];
  },
  inv(m) {
    const det = m[0] * m[3] - m[1] * m[2];
    if (Math.abs(det) < 1e-12) return null;
    const a = m[3] / det, b = -m[1] / det, c = -m[2] / det, d = m[0] / det;
    return [a, b, c, d, -(a * m[4] + c * m[5]), -(b * m[4] + d * m[5])];
  },
  ponto(m, x, y) { return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]; },
  vetor(m, x, y) { return [m[0] * x + m[2] * y, m[1] * x + m[3] * y]; },
  // escala, rotação (graus) e inclinação a partir de a b c d
  decompor(m) {
    const [a, b, c, d] = m;
    const sx = Math.hypot(a, b);
    const rot = Math.atan2(b, a);
    const det = a * d - b * c;
    const sy = sx ? det / sx : Math.hypot(c, d);
    return { sx, sy, rot: rot * 180 / Math.PI };
  },
  compor(sx, sy, rotGraus) {
    const r = rotGraus * Math.PI / 180, cs = Math.cos(r), sn = Math.sin(r);
    return [cs * sx, sn * sx, -sn * sy, cs * sy];
  },
};

const clonar = (o) => (typeof structuredClone === 'function' ? structuredClone(o) : JSON.parse(JSON.stringify(o)));

// ---------------------------------------------------------------- filme (um .big aberto no servidor)
export class Filme {
  constructor(resposta, { editavel = false } = {}) {
    this.sessao = resposta.sessao;
    this.arquivo = resposta.arquivo;
    this.fonte = resposta.fonte;
    this.base = resposta.modelo;
    this.editavel = editavel;
    this.modelo = clonar(this.base);
    this.texturas = new Map();     // char da imagem -> {w, h, canvas | null, promessa}
    this.imports = new Map();      // nome do filme -> Promise<Filme|null>
    this.indicePlace = new Map();
    this.reindexar();
  }

  reindexar() {
    this.indicePlace.clear();
    this.modelo.chars.forEach((c, i) => {
      if (!c || !c.quadros) return;
      for (const q of c.quadros) for (const it of q) if (it.t === 'place') { it.dono = i; this.indicePlace.set(it.off, it); }
    });
  }

  // aplica as operações sobre uma cópia do modelo original
  aplicar(ops) {
    this.modelo = clonar(this.base);
    this.reindexar();
    const trocas = new Map();
    for (const op of Object.values(ops)) {
      if (op.op === 'place') {
        const it = this.indicePlace.get(op.off);
        if (!it) continue;
        if (op.m) { it.m = op.m.slice(); it.fl |= 4; }
        if (op.tx) { it.tx = op.tx.slice(); it.fl |= 4; }
        if (op.tint) { it.tint = op.tint.slice(); it.fl |= 8; }
        if (op.soma) { it.soma = op.soma.slice(); it.fl |= 8; }
      } else if (op.op === 'texto') {
        const c = this.modelo.chars[op.char];
        if (!c) continue;
        for (const k of ['cor', 'altura', 'alinh', 'limites', 'fonte']) if (op[k] !== undefined) c[k] = Array.isArray(op[k]) ? op[k].slice() : op[k];
      } else if (op.op === 'fonte_char') {
        const c = this.modelo.chars[op.char];
        if (c && c.t === 'fonte') c.nome = op.nome;
      } else if (op.op === 'cor_forma') {
        const c = this.modelo.chars[op.char];
        const it = c && c.itens.find((x) => x.off === op.item);
        if (it) it.cor = op.cor.slice();
      } else if (op.op === 'textura') {
        const c = this.modelo.chars[op.char];
        if (!c) continue;
        const w0 = this.base.chars[op.char].w, h0 = this.base.chars[op.char].h;
        c.w = op.w; c.h = op.h; c.img = op.img; c.fmt = 'RGBA32';
        trocas.set(op.char, op.img);
        if (w0 && h0 && (w0 !== op.w || h0 !== op.h)) {
          const sx = op.w / w0, sy = op.h / h0;
          for (const f of this.modelo.chars) {
            if (!f || f.t !== 'forma') continue;
            for (const it of f.itens) {
              if (it.img === op.char && (it.k === 0 || it.k === 1)) {
                const [a, b, cc, d, tx, ty] = it.m;
                it.m = [a * sx, b * sy, cc * sx, d * sy, tx * sx, ty * sy];
              }
            }
          }
        }
      }
    }
    // texturas trocadas: invalida o cache das que mudaram
    for (const [ch, t] of this.texturas) {
      const img = trocas.get(ch) || null;
      if ((t.img || null) !== img) this.texturas.delete(ch);
    }
  }

  // ------------------------------------------------------------ texturas
  textura(ch) {
    let t = this.texturas.get(ch);
    if (t) return t;
    const c = this.modelo.chars[ch];
    t = { w: c?.w || 0, h: c?.h || 0, canvas: null, img: c?.img || null, versao: 0, erro: null };
    this.texturas.set(ch, t);
    t.promessa = (async () => {
      try {
        if (t.img) {
          const r = await fetch('/api/imagem?id=' + encodeURIComponent(t.img));
          const bmp = await createImageBitmap(await r.blob());
          const cv = document.createElement('canvas');
          cv.width = bmp.width; cv.height = bmp.height;
          cv.getContext('2d').drawImage(bmp, 0, 0);
          t.canvas = cv; t.w = bmp.width; t.h = bmp.height;
        } else {
          const r = await fetch(`/api/entrada?sessao=${encodeURIComponent(this.sessao)}&ent=${encodeURIComponent(c.ent)}`);
          if (!r.ok) throw new Error('textura não encontrada');
          const d = lerDDS(await r.arrayBuffer());
          const cv = document.createElement('canvas');
          cv.width = d.w; cv.height = d.h;
          cv.getContext('2d').putImageData(new ImageData(d.rgba, d.w, d.h), 0, 0);
          t.canvas = cv; t.w = d.w; t.h = d.h;
        }
      } catch (ex) { t.erro = String(ex.message || ex); }
      t.versao++;
      return t;
    })();
    return t;
  }

  // ------------------------------------------------------------ componentes importados
  importar(nomeFilme) {
    if (!this.imports.has(nomeFilme)) {
      this.imports.set(nomeFilme, api('componente', { sessao: this.sessao, filme: nomeFilme })
        .then((r) => (r.sessao ? new Filme(r) : null)).catch(() => null));
    }
    return this.imports.get(nomeFilme);
  }

  exportado(nome) {
    const e = this.modelo.exports.find((x) => x.nome === nome);
    return e ? e.char : null;
  }

  fontes() {
    return this.modelo.chars.map((c, i) => (c && c.t === 'fonte' ? { i, nome: c.nome } : null)).filter(Boolean);
  }
}

// ---------------------------------------------------------------- textos de exemplo (o jogo preenche na hora)
const EXEMPLOS = [
  [/txtHundredMin/i, ''], [/txtTenMin/i, '4'], [/txtMin/i, '5'], [/txtColon/i, ':'], [/txtTenSec/i, '0'], [/txtSec/i, '0'],
  [/extra|added|injury/i, '+3'], [/agg/i, '(3)'],
  [/home.*score|score.*home/i, '2'], [/away.*score|score.*away/i, '1'], [/score/i, '0'],
  [/home.*(team|name|club)|(team|club).*home/i, 'MANDANTE'], [/away.*(team|name|club)|(team|club).*away/i, 'VISITANTE'],
  [/clock|timer|time/i, '45:00'], [/coach|manager/i, 'TÉCNICO'], [/commentator/i, 'NARRADOR'],
  [/first.?name/i, 'NOME'], [/last.?name|player.*name|name/i, 'JOGADOR'],
  [/number|num/i, '10'], [/rating|ovr/i, '87'], [/formation/i, '4-3-3'],
  [/header|title|label/i, 'TÍTULO'], [/team/i, 'TIME'],
];

export function textoExemplo(nomes) {
  for (const n of nomes) {
    if (!n) continue;
    for (const [rx, t] of EXEMPLOS) if (rx.test(n)) return t;
  }
  return 'Texto';
}

// ---------------------------------------------------------------- árvore de exibição
// nó: { id, filme, place, char, tipo, nome, filhos, local, mundo, mult, soma, prof, recorte, pai, importado }
export async function montarArvore(filme, opcoes = {}) {
  const pendentes = [];
  const raiz = { id: 'raiz', filme, place: null, char: 0, tipo: 'filme', nome: filme.arquivo.split('/').pop(), filhos: [],
    local: M.id(), mundo: M.id(), mult: [1, 1, 1, 1], soma: [0, 0, 0, 0], multProprio: [1, 1, 1, 1], somaProprio: [0, 0, 0, 0],
    caminho: '', prof: 0, recorte: -1, pai: null, importado: false };
  const limite = { n: 0 };
  await expandir(raiz, filme, 0, 0, pendentes, limite, opcoes);
  return raiz;
}

function listaExibicao(char) {
  // acumula os PlaceObject/RemoveObject do quadro 0 (os overlays do FC são animados por código, quase todos têm 1 quadro)
  const lst = new Map();
  const q = (char.quadros || [])[0] || [];
  for (const it of q) {
    if (it.t === 'place') {
      if ((it.fl & 2) || !lst.has(it.prof)) lst.set(it.prof, it);
      else lst.set(it.prof, { ...lst.get(it.prof), ...it, char: lst.get(it.prof).char });
    } else if (it.t === 'remove') lst.delete(it.prof);
  }
  return [...lst.values()].sort((a, b) => a.prof - b.prof);
}

async function expandir(no, filme, charId, nivel, pendentes, limite, opcoes) {
  const c = filme.modelo.chars[charId];
  if (!c || nivel > 40 || limite.n > 20000) return;
  if (c.t === 'import') {
    const outro = await filme.importar(c.filme);
    no.ehImport = true;
    no.origem = c.filme;
    no.nomeImport = c.nome;
    if (!outro) { no.tipo = 'import'; no.faltando = true; return; }
    const alvo = outro.exportado(c.nome);
    if (alvo === null || alvo === undefined) { no.tipo = 'import'; no.faltando = true; return; }
    no.filmeConteudo = outro;
    await expandir(no, outro, alvo, nivel + 1, pendentes, limite, opcoes);
    // componentes que o código do jogo preenche na hora (textos e escudos): sem conteúdo no arquivo
    if (!no.filhos.length) {
      if (RX_TEXTO.test(c.nome)) no.marcador = 'texto';
      else if (RX_IMAGEM.test(c.nome)) no.marcador = 'imagem';
    }
    return;
  }
  no.tipo = c.t;
  no.charDef = c;
  no.filmeConteudo = no.filmeConteudo || filme;
  if (c.t !== 'filme' && c.t !== 'sprite') return;
  for (const it of listaExibicao(c)) {
    limite.n++;
    const local = [it.m[0], it.m[1], it.m[2], it.m[3], it.tx[0], it.tx[1]];
    const mult = (it.fl & 8) ? it.tint.map((v) => v / 255) : [1, 1, 1, 1];
    const soma = (it.fl & 8) ? it.soma.map((v) => v / 255) : [0, 0, 0, 0];
    const importado = !!(no.importado || no.ehImport);
    const caminho = it.nome && no.caminho !== null ? (no.caminho ? no.caminho + '.' : '') + it.nome : null;
    const filho = {
      id: no.id + '/' + (importado ? 'i' : '') + it.off,
      filme, place: it, char: it.char, nome: it.nome || '', filhos: [], local,
      mundo: M.mul(no.mundo, local),
      mult: no.mult.map((v, k) => v * mult[k]),
      soma: soma.map((v, k) => v * no.mult[k] + no.soma[k]),
      multProprio: mult, somaProprio: soma,
      caminho,   // "mcClassOverlay.mcTeamHolder.mcHomeTeamName": como o código do placar chama o clipe
      prof: it.prof, recorte: (it.fl & F_RECORTE) ? it.clip : -1, pai: no,
      importado, editavel: filme.editavel && !importado,
    };
    no.filhos.push(filho);
    await expandir(filho, filme, it.char, nivel + 1, pendentes, limite, opcoes);
  }
}

// nomes do nó e dos ancestrais (para textos de exemplo e rótulos)
export function nomesAcima(no) {
  const out = [];
  for (let n = no; n; n = n.pai) if (n.nome) out.push(n.nome);
  return out;
}

export function caminhoNomes(no) {
  const out = [];
  for (let n = no; n && n.pai; n = n.pai) out.unshift(n.nome || `#${n.char}`);
  return out;
}

export function percorrer(no, fn) {
  fn(no);
  for (const f of no.filhos) percorrer(f, fn);
}

export function acharNo(raiz, id) {
  let achado = null;
  percorrer(raiz, (n) => { if (!achado && n.id === id) achado = n; });
  return achado;
}

// texturas usadas por um nó (para o painel): [{filme, char}]
export function texturasDoNo(no) {
  const vistos = new Set();
  const out = [];
  percorrer(no, (n) => {
    const c = n.charDef;
    if (!c || c.t !== 'forma') return;
    const f = n.filmeConteudo || n.filme;
    for (const it of c.itens) {
      if (it.img === null || it.img === undefined) continue;
      const k = f.sessao + ':' + it.img;
      if (vistos.has(k)) continue;
      vistos.add(k);
      out.push({ filme: f, char: it.img });
    }
  });
  return out;
}
