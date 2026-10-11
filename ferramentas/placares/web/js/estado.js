// Estado compartilhado do editor e as operações de edição (com desfazer/refazer).
import { Historico } from './historico.js';

export const S = {
  inicio: null,          // resposta de /api/inicio
  fonteAtual: 'jogo',
  conjuntos: null,       // conjuntos da fonte atual
  doc: null,             // { filme, arquivo, alvo, fonte, ops, salvo, destino, saida }
  raiz: null,            // árvore de exibição
  sel: null,             // id do nó selecionado
  selImagem: null,       // char da imagem selecionada (aba Imagens)
  hist: new Historico(),
  render: null,
  abertosArq: new Set(['generic']),
  abertosCam: new Set(['raiz']),
  aba: 'arquivos',
  animando: false,       // a vista mostra a prévia da animação (não dá para arrastar elementos)
  ouvintes: {},
};

export function ouvir(evento, fn) { (S.ouvintes[evento] ||= []).push(fn); }
export function emitir(evento, ...args) { for (const fn of S.ouvintes[evento] || []) fn(...args); }

const igual = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function pendentes() {
  if (!S.doc) return 0;
  return igual(S.doc.ops, S.doc.salvo) ? 0 : Object.keys(S.doc.ops).length || 1;
}

// Troca (ou remove) uma operação, registrando no histórico. 'fundir' junta ajustes contínuos num passo só.
export function definirOp(nome, chave, op, { fundir = true, semHistorico = false, antes: antesDado } = {}) {
  if (!S.doc) return;
  const antes = antesDado !== undefined ? antesDado : (S.doc.ops[chave] ? JSON.parse(JSON.stringify(S.doc.ops[chave])) : null);
  const depois = op ? JSON.parse(JSON.stringify(op)) : null;
  const aplicar = (v) => {
    if (v) S.doc.ops[chave] = JSON.parse(JSON.stringify(v));
    else delete S.doc.ops[chave];
    emitir('ops');
  };
  if (semHistorico) { aplicar(depois); return; }
  S.hist.executar({ nome, fundir: fundir ? chave + '|' + nome : null, refazer: () => aplicar(depois), desfazer: () => aplicar(antes) });
}

// Operação de PlaceObject: guarda só os campos diferentes do original
export function opPlace(place, base, mudancas) {
  const chave = 'place:' + place.off;
  const atual = { ...(S.doc.ops[chave] || { op: 'place', off: place.off }) };
  for (const [k, v] of Object.entries(mudancas)) {
    if (v === null || igual(v, base[k])) delete atual[k];
    else atual[k] = v;
  }
  const temAlgo = ['m', 'tx', 'tint', 'soma'].some((k) => atual[k] !== undefined);
  return { chave, op: temAlgo ? atual : null };
}

export function opTexto(charId, base, mudancas) {
  const chave = 'texto:' + charId;
  const atual = { ...(S.doc.ops[chave] || { op: 'texto', char: charId }) };
  for (const [k, v] of Object.entries(mudancas)) {
    if (v === null || igual(v, base[k])) delete atual[k];
    else atual[k] = v;
  }
  const temAlgo = ['cor', 'altura', 'alinh', 'limites', 'fonte'].some((k) => atual[k] !== undefined);
  return { chave, op: temAlgo ? atual : null };
}
