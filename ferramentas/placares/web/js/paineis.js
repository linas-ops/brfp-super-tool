// Painéis: lista de arquivos (conjuntos de placares), camadas, imagens e propriedades do que está selecionado.
import { api } from './api.js';
import { M, caminhoNomes, percorrer, texturasDoNo } from './cena.js';
import { S, definirOp, emitir, opPlace, opTexto } from './estado.js';
import { icone } from './icones.js';
import { $, aviso, campoNumero, el, esc, fmtNum, interruptor, nota } from './ui.js';
import { acharBase, pedirDesenho, selecionado } from './vista.js';
import { secaoArquivo, secoesNo } from './codigo.js';

// ================================================================ aba Arquivos
export function desenharArquivos() {
  const sel = $('#sel-fonte');
  const fontes = S.inicio?.fontes || [];
  sel.innerHTML = '';
  for (const f of fontes) {
    const rot = f.tipo === 'jogo' ? 'FC 26 (jogo)' : f.tipo === 'mod' ? 'Mod: ' + f.nome : f.nome;
    sel.append(el('option', { value: f.id }, rot));
  }
  if (!fontes.some((f) => f.id === S.fonteAtual) && fontes.length) S.fonteAtual = fontes[0].id;
  sel.value = S.fonteAtual;
  const lista = $('#lista-arquivos');
  lista.innerHTML = '';
  const fonte = fontes.find((f) => f.id === S.fonteAtual);
  if (fonte && fonte.tipo === 'jogo' && fonte.estado !== 'pronto') {
    lista.append(el('div', { class: 'lista-vazia' }, fonte.estado === 'erro' ? 'Não consegui ler o FC 26: ' + (fonte.erro || '') : 'Lendo os arquivos do FC 26…'));
    return;
  }
  if (!S.conjuntos) { lista.append(el('div', { class: 'lista-vazia' }, 'Carregando…')); return; }
  const termo = ($('#busca-arquivos').value || '').trim().toLowerCase();
  let algum = false;
  for (const g of S.conjuntos) {
    const chave = (g.chave || g.titulo).toLowerCase();
    const casaGrupo = !termo || g.titulo.toLowerCase().includes(termo) || String(g.numero) === termo;
    const ovs = g.overlays.filter((o) => casaGrupo || o.rotulo.toLowerCase().includes(termo) || o.arquivo.toLowerCase().includes(termo));
    const comps = g.componentes.filter((o) => casaGrupo || o.arquivo.toLowerCase().includes(termo));
    if (!ovs.length && !comps.length) continue;
    algum = true;
    const temAberto = S.doc && S.doc.fonte.id === S.fonteAtual && [...g.overlays, ...g.componentes].some((o) => o.arquivo.toLowerCase() === S.doc.arquivo.toLowerCase());
    if (temAberto && !S.abertosArq.has('!' + chave)) { S.abertosArq.add(chave); S.abertosArq.add('!' + chave); }
    const aberto = S.abertosArq.has(chave) || !!termo;
    const editados = [...ovs, ...comps].filter((o) => o.editado).length;
    const cab = el('div', { class: 'grupo-cab' + (aberto ? ' aberto' : ''), html: icone('seta', 12, 'seta') });
    cab.append(el('span', {}, g.titulo));
    if (g.numero !== null && g.numero !== undefined) cab.append(el('span', { class: 'num' }, `nº ${g.numero}`));
    if (editados) cab.append(el('span', { class: 'mod', title: `${editados} editado(s)`, style: { width: '7px', height: '7px', borderRadius: '50%', background: 'var(--acento)' } }));
    cab.append(el('span', { class: 'qtd' }, `${g.overlays.length}`));
    cab.onclick = () => { if (S.abertosArq.has(chave)) S.abertosArq.delete(chave); else S.abertosArq.add(chave); desenharArquivos(); };
    lista.append(cab);
    if (!aberto) continue;
    const corpo = el('div', { class: 'grupo-corpo' });
    const principais = ovs.filter((o) => o.rotulo);
    const outros = ovs.filter((o) => !o.rotulo);
    const item = (o, rotulo, numTxt) => {
      const aberto2 = S.doc && S.doc.arquivo.toLowerCase() === o.arquivo.toLowerCase() && S.doc.fonte.id === S.fonteAtual;
      const it = el('div', { class: 'item-arq' + (aberto2 ? ' aberto' : '') + (o.tipo === 2 ? ' destaque' : ''), title: o.arquivo });
      it.append(el('span', { class: 'n' }, numTxt), el('span', { class: 'r' + (rotulo ? '' : ' vazio') }, rotulo || 'sem descrição'));
      if (o.editado) it.append(el('span', { class: 'mod', title: 'Editado (gravado na saída)' }));
      it.onclick = () => emitir('abrir', { fonte: S.fonteAtual, arquivo: o.arquivo });
      corpo.append(it);
    };
    for (const o of principais) item(o, o.rotulo, String(o.numero));
    if (outros.length) {
      corpo.append(el('div', { class: 'sub-cab' }, 'Outros overlays'));
      for (const o of outros) item(o, '', String(o.numero));
    }
    if (comps.length) {
      corpo.append(el('div', { class: 'sub-cab' }, 'Componentes'));
      for (const o of comps) item(o, o.rotulo, '');
    }
    lista.append(corpo);
  }
  if (!algum) lista.append(el('div', { class: 'lista-vazia' }, termo ? 'Nada encontrado.' : 'Nenhum placar nesta fonte.'));
}

// ================================================================ aba Camadas
export function desenharCamadas() {
  const box = $('#arvore-camadas');
  box.innerHTML = '';
  if (!S.raiz) { box.append(el('div', { class: 'lista-vazia' }, 'Abra um placar para ver as camadas.')); return; }
  const modo = $('#filtro-camadas').value;
  const termo = ($('#busca-camadas').value || '').trim().toLowerCase();
  const sel = selecionado();
  if (sel) for (let n = sel.pai; n; n = n.pai) S.abertosCam.add(n.id);
  const alterado = (n) => n.place && S.doc.ops['place:' + n.place.off];
  const relevante = (n) => {
    if (modo === 'tudo') return true;
    if (modo === 'alterados') return !!alterado(n);
    return !!n.nome;
  };
  const casa = (n) => !termo || (n.nome || '').toLowerCase().includes(termo);
  // filhos visíveis na lista: os sem nome somem e os netos sobem (modo "Com nome")
  const visiveis = (n) => {
    const out = [];
    for (const f of n.filhos) {
      if (f.recorte >= 0 && modo !== 'tudo') continue;
      if (relevante(f)) out.push(f);
      else out.push(...visiveis(f));
    }
    return out;
  };
  const contem = (n) => casa(n) || visiveis(n).some(contem);
  let linhas = 0;
  const linha = (n, nivel) => {
    if (!contem(n) || linhas > 3000) return;
    linhas++;
    const filhos = visiveis(n);
    const aberto = S.abertosCam.has(n.id) || !!termo;
    const tipo = n.ehImport ? 'import' : n.tipo;
    const ic = { forma: 'forma', texto: 'texto', sprite: 'sprite', import: 'componente', filme: 'placar' }[tipo] || 'sprite';
    const invisivel = n.place && (n.place.fl & 8) && n.place.tint[3] === 0;
    const r = el('div', {
      class: `cam${n.id === S.sel ? ' sel' : ''}${n.nome ? '' : ' sem-nome'}${n.importado ? ' importado' : ''}${S.render.ocultos.has(n.id) ? ' oculto' : ''}${invisivel ? ' invisivel' : ''}`,
      style: { paddingLeft: (4 + nivel * 14) + 'px' }, title: caminhoNomes(n).join(' › '),
    });
    const exp = el('span', { class: 'exp' + (aberto ? ' aberto' : ''), html: filhos.length ? icone('seta', 12) : '' });
    exp.onclick = (e) => { e.stopPropagation(); if (S.abertosCam.has(n.id)) S.abertosCam.delete(n.id); else S.abertosCam.add(n.id); desenharCamadas(); };
    r.append(exp, el('span', { class: 'tipo t-' + tipo, html: icone(ic, 14) }));
    const nome = el('span', { class: 'nome' }, n.nome || (n.tipo === 'filme' ? n.nome : rotuloSemNome(n)));
    if (n.ehImport) nome.append(el('span', { class: 'tec' }, (n.nomeImport || '').split('.').pop()));
    r.append(nome);
    if (alterado(n)) r.append(el('span', { class: 'mod', title: 'Alterado' }));
    if (n.pai) {
      const olho = el('button', { class: 'tog', title: 'Esconder só no editor (H)', html: icone(S.render.ocultos.has(n.id) ? 'olhoFechado' : 'olho', 14) });
      olho.onclick = (e) => { e.stopPropagation(); alternarOculto(n); };
      r.append(olho);
    }
    r.onclick = () => { S.sel = n.pai ? n.id : null; emitir('selecao', 'camadas'); };
    r.ondblclick = () => emitir('enquadrar');
    box.append(r);
    if (aberto) for (const f of filhos) linha(f, nivel + 1);
  };
  S.abertosCam.add('raiz');
  linha(S.raiz, 0);
  const s = box.querySelector('.cam.sel');
  if (s) s.scrollIntoView({ block: 'nearest' });
}

function rotuloSemNome(n) {
  const t = { forma: 'forma', texto: 'texto', sprite: 'grupo', import: 'componente' }[n.tipo] || n.tipo;
  return `(${t} #${n.char})`;
}

export function alternarOculto(n) {
  if (S.render.ocultos.has(n.id)) S.render.ocultos.delete(n.id); else S.render.ocultos.add(n.id);
  desenharCamadas();
  pedirDesenho();
}

// ================================================================ aba Imagens
export function desenharImagens() {
  const g = $('#grade-imagens');
  g.innerHTML = '';
  if (!S.doc) { g.append(el('div', { class: 'lista-vazia' }, 'Abra um placar para ver as imagens.')); return; }
  const filme = S.doc.filme;
  const imgs = filme.modelo.chars.map((c, i) => (c && c.t === 'imagem' ? i : null)).filter((i) => i !== null);
  const comps = filme.modelo.imports || [];
  g.append(el('div', { class: 'barra-imagens' },
    el('span', {}, `${imgs.length} imagem(ns)${comps.length ? ` · ${comps.length} componente(s) de outros arquivos` : ''}`),
    el('button', { class: 'btn peq', title: 'Grava todas as imagens deste placar em PNG numa pasta (exportados\\<placar>_imagens) e abre a pasta',
      disabled: !imgs.length && !comps.length, onclick: () => exportarTodas(false) }, 'Exportar todas'),
    comps.length ? el('button', { class: 'btn-fantasma peq', title: 'Também as imagens dos componentes usados (de outros arquivos .big), cada um numa subpasta', onclick: () => exportarTodas(true) }, '+ componentes') : null));
  if (!imgs.length) { g.append(el('div', { class: 'lista-vazia' }, 'Este arquivo não tem imagens próprias (usa as dos componentes).')); return; }
  for (const i of imgs) {
    const c = filme.modelo.chars[i];
    const alterada = !!S.doc.ops['textura:' + i];
    const card = el('div', { class: 'cartao-img' + (S.selImagem === i ? ' sel' : '') + (alterada ? ' alterada' : ''), title: `Imagem #${i} (entrada ${c.ent} do .big)` });
    const cv = el('canvas', { class: 'xadrez', width: 120, height: 76 });
    miniatura(filme, i, cv);
    card.append(cv, el('b', {}, `Imagem #${i}`), el('small', {}, `${c.w}×${c.h} · ${c.fmt}${alterada ? ' · trocada' : ''}`));
    card.onclick = () => { S.selImagem = i; S.sel = null; emitir('selecao', 'imagens'); desenharImagens(); };
    g.append(card);
  }
}

function miniatura(filme, ch, cv) {
  const t = filme.textura(ch);
  const pintar = () => {
    if (!t.canvas) return;
    const g = cv.getContext('2d');
    g.clearRect(0, 0, cv.width, cv.height);
    const k = Math.min(cv.width / t.w, cv.height / t.h);
    const w = t.w * k, h = t.h * k;
    g.imageSmoothingQuality = 'high';
    g.drawImage(t.canvas, (cv.width - w) / 2, (cv.height - h) / 2, w, h);
  };
  if (t.canvas) pintar(); else t.promessa.then(pintar);
}

// ================================================================ propriedades
export function desenharPropriedades() {
  const box = $('#propriedades');
  box.innerHTML = '';
  if (!S.doc) {
    box.append(el('div', { class: 'vazio-prop' }, 'Abra um placar na lista de arquivos.'));
    return;
  }
  if (S.selImagem !== null && S.selImagem !== undefined && !S.sel) { painelImagem(box, S.doc.filme, S.selImagem); return; }
  const no = selecionado();
  if (!no) { painelArquivo(box); return; }
  painelNo(box, no);
}

function cabecalho(box, titulo, sub, icn, etiquetas = [], migalhas = null) {
  const cab = el('div', { class: 'prop-cab' });
  if (migalhas) cab.append(migalhas);
  cab.append(el('div', { class: 'titulo', html: icone(icn, 18) }, el('h3', {}, titulo)));
  if (sub) cab.append(el('div', { class: 'sub' }, sub));
  if (etiquetas.length) cab.append(el('div', { class: 'etiquetas' }, ...etiquetas));
  box.append(cab);
}

function secao(box, titulo, aberta = true) {
  const d = el('details', { class: 'secao' });
  d.open = aberta;
  d.append(el('summary', { html: icone('seta', 12, 'seta') + esc(titulo) }));
  const c = el('div', { class: 'secao-corpo' });
  d.append(c);
  box.append(d);
  return c;
}

function painelArquivo(box) {
  const d = S.doc;
  const m = d.filme.modelo;
  cabecalho(box, d.arquivo.split('/').pop(), d.arquivo, 'placar', [
    el('span', { class: 'etiqueta' }, d.fonte.tipo === 'jogo' ? 'FC 26' : d.fonte.nome),
    Object.keys(d.ops).length ? el('span', { class: 'etiqueta azul' }, `${Object.keys(d.ops).length} alteração(ões)`) : null,
  ]);
  const c = secao(box, 'Arquivo');
  const n = (t) => m.chars.filter((x) => x && x.t === t).length;
  c.append(el('div', { class: 'estatisticas' },
    el('div', { class: 'estatistica' }, el('b', {}, String(n('sprite'))), el('span', {}, 'grupos (sprites)')),
    el('div', { class: 'estatistica' }, el('b', {}, String(n('forma'))), el('span', {}, 'formas')),
    el('div', { class: 'estatistica' }, el('b', {}, String(n('imagem'))), el('span', {}, 'imagens')),
    el('div', { class: 'estatistica' }, el('b', {}, String(n('texto'))), el('span', {}, 'campos de texto'))));
  if (m.imports.length) {
    const lst = el('div', { class: 'bloco-cinza' });
    lst.append(el('div', {}, el('b', {}, 'Componentes usados (de outros arquivos):')));
    for (const imp of m.imports) lst.append(el('div', {}, '• ' + imp.nome.split('.').pop() + ' — ', el('small', {}, imp.filme)));
    c.append(lst);
  }
  c.append(nota('Clique num elemento na prévia (ou na aba <b>Camadas</b>) para mover, mudar cores e trocar imagens. ' +
    'Os textos (nomes dos times, placar, relógio) são preenchidos pelo jogo durante a partida: aqui aparecem exemplos.', 'info'));
  secaoArquivo(box);
  const s = secao(box, 'Onde é gravado');
  s.append(el('div', { class: 'bloco-cinza' }, d.destino || 'Escolha a pasta de saída.'));
  const acoes = el('div', { class: 'acoes-linha' });
  acoes.append(el('button', { class: 'btn peq', onclick: () => emitir('salvar-como') }, 'Salvar como outro arquivo…'));
  if (d.editadoNaSaida) acoes.append(el('button', { class: 'btn-perigo peq', onclick: () => emitir('descartar') }, 'Descartar edição gravada'));
  s.append(acoes);
}

function migalhasDo(no) {
  const m = el('div', { class: 'migalhas' });
  const cadeia = [];
  for (let n = no.pai; n && n.pai; n = n.pai) cadeia.unshift(n);
  for (const n of cadeia.slice(-4)) {
    const b = el('button', {}, n.nome || rotuloSemNome(n));
    b.onclick = () => { S.sel = n.id; emitir('selecao', 'props'); };
    m.append(b, el('span', { class: 'sep' }, '›'));
  }
  return m;
}

function painelNo(box, no) {
  const tipo = no.ehImport ? 'componente' : { forma: 'forma', texto: 'texto', sprite: 'grupo', filme: 'filme' }[no.tipo] || no.tipo;
  const icn = { forma: 'forma', texto: 'texto', grupo: 'sprite', componente: 'componente' }[tipo] || 'sprite';
  const alterado = no.place && S.doc.ops['place:' + no.place.off];
  const usos = no.place ? contarUsos(no.place.dono) : 1;
  cabecalho(box, no.nome || rotuloSemNome(no), null, icn, [
    el('span', { class: 'etiqueta' }, tipo),
    no.importado ? el('span', { class: 'etiqueta amarela' }, 'dentro de componente') : null,
    alterado ? el('span', { class: 'etiqueta azul' }, 'alterado') : null,
  ], migalhasDo(no));

  if (!no.editavel) {
    const c = secao(box, 'Componente de outro arquivo');
    c.append(nota('Este elemento faz parte de um <b>componente</b> que vem de outro arquivo (' + esc(origemDe(no)) + '). ' +
      'Para mexer nele, selecione o componente inteiro ou abra o arquivo do componente.', 'alerta'));
    const ac = el('div', { class: 'acoes-linha' });
    let comp = no; while (comp && comp.importado) comp = comp.pai;
    if (comp && comp.place) ac.append(el('button', { class: 'btn peq', onclick: () => { S.sel = comp.id; emitir('selecao', 'props'); } }, 'Selecionar o componente'));
    const arq = arquivoComponente(no);
    if (arq) ac.append(el('button', { class: 'btn peq', onclick: () => emitir('abrir', arq) }, 'Abrir o arquivo do componente'));
    c.append(ac);
    imagensDoNo(box, no);
    return;
  }

  if (usos > 1) {
    box.append(el('div', { style: { padding: '10px 14px 0' } }, nota(`Este elemento está dentro de um grupo usado em <b>${usos}</b> lugares: mudar aqui muda em todos.`, 'info')));
  }
  if (no.place) {
    transformacao(box, no);
    cores(box, no);
  }
  if (no.tipo === 'forma') formaItens(box, no);
  if (no.tipo === 'texto') textoProps(box, no);
  secoesNo(box, no);
  if (no.ehImport) {
    const c = secao(box, 'Componente');
    c.append(el('div', { class: 'bloco-cinza' }, 'Símbolo ', el('b', {}, (no.nomeImport || '').split('.').pop()), ' de ', el('code', {}, no.origem || '')));
    const arq = arquivoComponente(no.filhos[0] || no);
    if (arq) c.append(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => emitir('abrir', arq) }, 'Abrir o arquivo do componente')));
  }
  imagensDoNo(box, no);
  const d = secao(box, 'Detalhes', false);
  const kv = el('dl', { class: 'kv' });
  const par = (k, v) => kv.append(el('dt', {}, k), el('dd', {}, v));
  par('Character', String(no.char));
  if (no.place) { par('Profundidade', String(no.place.prof)); par('Posição no APT', '0x' + no.place.off.toString(16)); }
  if (no.recorte >= 0) par('Máscara até', String(no.recorte));
  par('Caminho', caminhoNomes(no).join(' › '));
  d.append(kv);
}

function contarUsos(dono) {
  if (dono === undefined || !S.raiz) return 1;
  let n = 0;
  percorrer(S.raiz, (x) => { if (!x.importado && x.place && x.char === dono) n++; });
  return Math.max(1, n);
}

function origemDe(no) {
  for (let n = no; n; n = n.pai) if (n.ehImport) return n.origem;
  return '';
}

function arquivoComponente(no) {
  for (let n = no; n; n = n.pai) {
    const f = n.filmeConteudo;
    if (n.ehImport && f && f !== S.doc.filme) return { fonte: f.fonte.id, arquivo: f.arquivo };
  }
  const f = no.filme;
  if (f && f !== S.doc.filme) return { fonte: f.fonte.id, arquivo: f.arquivo };
  return null;
}

// ---------------------------------------------------------------- posição, escala, rotação
function transformacao(box, no) {
  const c = secao(box, 'Posição e tamanho');
  const base = acharBase(no.place.off) || no.place;
  const p = no.place;
  const dec = M.decompor(p.m);
  let trava = true;
  const aplicar = (mud, nome, final) => {
    const { chave, op } = opPlace(p, base, mud);
    definirOp(nome, chave, op, { fundir: true });
    if (final) emitir('props-externas');
  };
  const xi = campoNumero({ valor: p.tx[0], eixo: 'x', passo: 1, casas: 1, titulo: 'Posição X (pixels, em relação ao grupo de cima)',
    aoMudar: (v) => aplicar({ tx: [v, S.doc.filme.indicePlace.get(p.off).tx[1]] }, 'Mover') });
  const yi = campoNumero({ valor: p.tx[1], eixo: 'y', passo: 1, casas: 1, titulo: 'Posição Y',
    aoMudar: (v) => aplicar({ tx: [S.doc.filme.indicePlace.get(p.off).tx[0], v] }, 'Mover') });
  c.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Posição'), el('div', { class: 'dupla' }, xi.el, yi.el)));
  const atualM = () => M.decompor(S.doc.filme.indicePlace.get(p.off).m);
  let sxC, syC;
  const mudarEscala = (eixo, v) => {
    const d = atualM();
    let sx = d.sx, sy = d.sy;
    if (eixo === 'x') { if (trava && sx) sy = sy * v / sx; sx = v; } else { if (trava && sy) sx = sx * v / sy; sy = v; }
    aplicar({ m: M.compor(sx, sy, d.rot) }, 'Escala');
    if (trava) { sxC.definir(sx * 100); syC.definir(sy * 100); }
  };
  sxC = campoNumero({ valor: dec.sx * 100, eixo: 'x', passo: 0.5, casas: 1, titulo: 'Escala horizontal (%)', aoMudar: (v) => mudarEscala('x', v / 100) });
  syC = campoNumero({ valor: dec.sy * 100, eixo: 'y', passo: 0.5, casas: 1, titulo: 'Escala vertical (%)', aoMudar: (v) => mudarEscala('y', v / 100) });
  const bt = el('button', { class: 'btn-icone peq ativo trava', title: 'Manter a proporção', html: icone('trava', 13) });
  bt.onclick = () => { trava = !trava; bt.classList.toggle('ativo', trava); bt.innerHTML = icone(trava ? 'trava' : 'destrava', 13); };
  c.append(el('div', { class: 'linha-prop' }, el('span', { class: 'rot' }, 'Escala %', bt), el('div', { class: 'dupla' }, sxC.el, syC.el)));
  const rot = campoNumero({ valor: dec.rot, passo: 0.5, casas: 1, titulo: 'Rotação (graus)',
    aoMudar: (v) => { const d = atualM(); aplicar({ m: M.compor(d.sx, d.sy, v) }, 'Girar'); } });
  c.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Rotação'), rot.el));
  const ac = el('div', { class: 'acoes-linha' });
  ac.append(el('button', { class: 'btn peq', title: 'Espelhar na horizontal', onclick: () => { const m = S.doc.filme.indicePlace.get(p.off).m; aplicar({ m: [-m[0], -m[1], m[2], m[3]] }, 'Espelhar', true); } }, 'Espelhar ↔'));
  if (S.doc.ops['place:' + p.off] && (S.doc.ops['place:' + p.off].m || S.doc.ops['place:' + p.off].tx)) {
    ac.append(el('button', { class: 'btn peq', onclick: () => aplicar({ m: null, tx: null }, 'Restaurar posição', true) }, 'Restaurar original'));
  }
  c.append(ac);
  // atualização quando a vista move o elemento
  no._atualizarCampos = () => {
    const it = S.doc.filme.indicePlace.get(p.off);
    if (!it) return;
    xi.definir(it.tx[0]); yi.definir(it.tx[1]);
    const d = M.decompor(it.m);
    sxC.definir(d.sx * 100); syC.definir(d.sy * 100); rot.definir(d.rot);
  };
  S.atualizarCampos = no._atualizarCampos;
}

// ---------------------------------------------------------------- cores (color transform do PlaceObject)
const hex = (r, g, b) => '#' + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
const deHex = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

function cores(box, no) {
  const c = secao(box, 'Cor e visibilidade');
  const p = no.place;
  const base = acharBase(p.off) || p;
  const atual = () => S.doc.filme.indicePlace.get(p.off);
  const temCor = () => (atual().fl & 8) || S.doc.ops['place:' + p.off]?.tint || S.doc.ops['place:' + p.off]?.soma;
  const tint = () => (temCor() ? atual().tint.slice() : [255, 255, 255, 255]);
  const soma = () => (temCor() ? atual().soma.slice() : [0, 0, 0, 0]);
  const aplicar = (mud, nome, final = false) => {
    const { chave, op } = opPlace(p, base, mud);
    definirOp(nome, chave, op);
    if (final) emitir('props-externas');
  };
  const visivel = tint()[3] > 0;
  const iv = interruptor({ titulo: 'Visível no jogo', descricao: 'Desligado, o elemento fica transparente no placar (o jogo ainda o anima, mas não aparece).',
    marcado: visivel, icone: 'olho',
    aoMudar: (v) => { const t = tint(); t[3] = v ? (t[3] || 255) || 255 : 0; if (v && t[3] === 0) t[3] = 255; aplicar({ tint: t, soma: soma() }, v ? 'Mostrar' : 'Esconder', true); } });
  c.append(iv.el);
  // opacidade
  const op = el('input', { type: 'range', min: 0, max: 100, step: 1 });
  op.value = Math.round(tint()[3] / 2.55);
  const opv = el('span', { class: 'valor' }, op.value + '%');
  op.oninput = () => { opv.textContent = op.value + '%'; const t = tint(); t[3] = Math.round(op.value * 2.55); aplicar({ tint: t, soma: soma() }, 'Opacidade'); };
  op.onchange = () => emitir('props-externas');
  c.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Opacidade'), el('div', { class: 'faixa' }, op, opv)));
  // multiplicar (tinge) e somar (pinta por cima)
  const t0 = tint();
  const cm = el('input', { type: 'color', value: hex(t0[0], t0[1], t0[2]), title: 'Multiplica as cores do elemento (branco = original)' });
  cm.oninput = () => { const t = tint(); const [r, g, b] = deHex(cm.value); aplicar({ tint: [r, g, b, t[3]], soma: soma() }, 'Cor (multiplicar)'); };
  cm.onchange = () => emitir('props-externas');
  const s0 = soma();
  const cs = el('input', { type: 'color', value: hex(s0[0], s0[1], s0[2]), title: 'Soma uma cor (preto = nada). Com "multiplicar" preto, vira a cor exata.' });
  cs.oninput = () => { const [r, g, b] = deHex(cs.value); aplicar({ tint: tint(), soma: [r, g, b, soma()[3]] }, 'Cor (somar)'); };
  cs.onchange = () => emitir('props-externas');
  c.append(el('div', { class: 'linha-prop', title: 'Multiplicar: tinge mantendo os detalhes da imagem. Branco = sem mudança.' }, el('label', {}, 'Tingir'),
    el('div', { class: 'cor-amostra' }, cm, el('code', {}, cm.value))));
  c.append(el('div', { class: 'linha-prop', title: 'Somar: clareia/pinta por cima. Preto = sem mudança.' }, el('label', {}, 'Somar cor'),
    el('div', { class: 'cor-amostra' }, cs, el('code', {}, cs.value))));
  const ac = el('div', { class: 'acoes-linha' });
  ac.append(el('button', { class: 'btn peq', title: 'Multiplicar preto + somar a cor = cor sólida exata', onclick: async () => {
    const [r, g, b] = deHex(cs.value === '#000000' ? '#ffffff' : cs.value);
    aplicar({ tint: [0, 0, 0, tint()[3]], soma: [r, g, b, 0] }, 'Cor sólida', true);
  } }, 'Cor sólida'));
  if (S.doc.ops['place:' + p.off]?.tint || S.doc.ops['place:' + p.off]?.soma) {
    ac.append(el('button', { class: 'btn peq', onclick: () => aplicar({ tint: null, soma: null }, 'Restaurar cor', true) }, 'Restaurar cor original'));
  }
  c.append(ac);
  if (base && (base.fl & 8)) c.append(el('div', { class: 'mudo' }, `Original: tingir ${hex(...base.tint.slice(0, 3))} · ${Math.round(base.tint[3] / 2.55)}% · somar ${hex(...base.soma.slice(0, 3))}`));
  c.append(nota('Muitos fundos e barras do placar recebem a cor do time pelo código do jogo durante a partida — a cor daqui pode ser trocada por ele.', ''));
}

// ---------------------------------------------------------------- forma: cores sólidas e texturas dos itens
function formaItens(box, no) {
  const f = no.filmeConteudo || no.filme;
  const c = no.charDef;
  const sec = secao(box, 'Desenho (forma)');
  const baseChar = f.base.chars[no.char];
  c.itens.forEach((it, idx) => {
    if (it.k === 2 || it.k === 3) {
      const chave = `cor_forma:${no.char}:${it.off}`;
      const inp = el('input', { type: 'color', value: hex(it.cor[0], it.cor[1], it.cor[2]) });
      const alfa = el('input', { type: 'range', min: 0, max: 100, step: 1 });
      alfa.value = Math.round(it.cor[3] / 2.55);
      const aplicar = () => {
        const [r, g, b] = deHex(inp.value);
        const nova = [r, g, b, Math.round(alfa.value * 2.55)];
        const orig = baseChar.itens[idx].cor;
        definirOp('Cor da forma', chave, JSON.stringify(nova) === JSON.stringify(orig) ? null : { op: 'cor_forma', char: no.char, item: it.off, cor: nova });
      };
      inp.oninput = aplicar;
      alfa.oninput = aplicar;
      sec.append(el('div', { class: 'cor-linha-item' }, el('span', { class: 'rot' }, it.k === 3 ? `Linha ${idx + 1}` : `Cor sólida ${idx + 1}`), inp,
        el('div', { class: 'faixa', style: { width: '110px' }, title: 'Opacidade' }, alfa)));
    }
  });
  const usadas = [...new Set(c.itens.filter((it) => it.img !== null && it.img !== undefined).map((it) => it.img))];
  if (!usadas.length && !c.itens.some((it) => it.k === 2 || it.k === 3)) sec.append(el('div', { class: 'mudo' }, 'Forma sem cor editável.'));
  if (usadas.length) sec.append(el('div', { class: 'mudo' }, `Usa ${usadas.length} imagem(ns) — veja abaixo.`));
}

// ---------------------------------------------------------------- texto
function textoProps(box, no) {
  const f = no.filmeConteudo || no.filme;
  const c = no.charDef;
  const base = f.base.chars[no.char];
  const sec = secao(box, 'Texto');
  const aplicar = (mud, nome) => { const { chave, op } = opTexto(no.char, base, mud); definirOp(nome, chave, op); };
  const cor = el('input', { type: 'color', value: hex(c.cor[0], c.cor[1], c.cor[2]) });
  cor.oninput = () => { const [r, g, b] = deHex(cor.value); aplicar({ cor: [r, g, b, c.cor[3]] }, 'Cor do texto'); };
  sec.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Cor'), el('div', { class: 'cor-amostra' }, cor)));
  const tam = campoNumero({ valor: c.altura, passo: 0.2, casas: 1, min: 1, max: 400, titulo: 'Tamanho da letra (px)', aoMudar: (v) => aplicar({ altura: v }, 'Tamanho do texto') });
  sec.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Tamanho'), tam.el));
  const seg = el('div', { class: 'seg-alinh' });
  for (const [v, ic, t] of [[0, 'alinharEsq', 'Esquerda'], [2, 'alinharCentro', 'Centro'], [1, 'alinharDir', 'Direita']]) {
    const b = el('button', { class: c.alinh === v ? 'ativo' : '', title: t, html: icone(ic, 14) });
    b.onclick = () => { aplicar({ alinh: v }, 'Alinhamento'); emitir('props-externas'); };
    seg.append(b);
  }
  sec.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Alinhar'), seg));
  const fontes = f.fontes();
  if (fontes.length) {
    const s = el('select', { class: 'seletor largo' });
    for (const ft of fontes) s.append(el('option', { value: ft.i }, ft.nome));
    s.value = String(c.fonte);
    s.onchange = () => aplicar({ fonte: Number(s.value) }, 'Fonte');
    sec.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Fonte'), s));
  }
  const lim = c.limites;
  const caixa = ['x0', 'y0', 'x1', 'y1'].map((k, i) => campoNumero({ valor: lim[i], passo: 1, casas: 1, titulo: ['Esquerda', 'Topo', 'Direita', 'Base'][i] + ' da caixa do texto',
    aoMudar: (v) => { const l = (S.doc.filme.modelo.chars[no.char] || c).limites.slice(); l[i] = v; aplicar({ limites: l }, 'Caixa do texto'); } }));
  sec.append(el('div', { class: 'linha-prop' }, el('label', {}, 'Caixa'), el('div', { class: 'quarteto' }, ...caixa.map((x) => x.el))));
  if (!no.editavel || f !== S.doc.filme) sec.append(nota('Este texto pertence a outro arquivo.', 'alerta'));
  sec.append(nota('O conteúdo (nome do time, placar, relógio) vem do jogo; aqui dá para mudar cor, tamanho, alinhamento, fonte e a caixa.', ''));
}

// ---------------------------------------------------------------- imagens usadas pelo nó
function imagensDoNo(box, no) {
  const lst = texturasDoNo(no);
  if (!lst.length) return;
  const sec = secao(box, `Imagens (${lst.length})`, lst.length <= 6);
  for (const { filme, char } of lst) sec.append(linhaTextura(filme, char));
}

export function linhaTextura(filme, char) {
  const c = filme.modelo.chars[char];
  const editavel = filme === S.doc.filme;
  const alterada = editavel && !!S.doc.ops['textura:' + char];
  const lin = el('div', { class: 'tex-linha' + (alterada ? ' alterada' : '') });
  const cv = el('canvas', { class: 'xadrez', width: 104, height: 104 });
  miniatura(filme, char, cv);
  const txt = el('div', { class: 'txt' });
  txt.append(el('b', {}, `Imagem #${char}`), el('small', {}, `${c.w}×${c.h} · ${c.fmt}${editavel ? '' : ' · de ' + filme.arquivo.split('/').pop()}`));
  const ac = el('div', { class: 'acoes-linha' });
  if (editavel) ac.append(el('button', { class: 'btn peq', onclick: () => emitir('trocar-imagem', char) }, 'Trocar…'));
  ac.append(el('button', { class: 'btn peq', onclick: () => exportarPNG(filme, char) }, 'PNG'));
  if (alterada) ac.append(el('button', { class: 'btn peq', title: 'Voltar à imagem original', onclick: () => definirOp('Restaurar imagem', 'textura:' + char, null) }, 'Original'));
  txt.append(ac);
  lin.append(cv, txt);
  cv.style.cursor = 'pointer';
  cv.onclick = () => { if (editavel) { S.selImagem = char; S.sel = null; emitir('selecao', 'props'); } };
  return lin;
}

function painelImagem(box, filme, char) {
  const c = filme.modelo.chars[char];
  if (!c) return;
  const alterada = !!S.doc.ops['textura:' + char];
  cabecalho(box, `Imagem #${char}`, `Entrada ${c.ent} do .big`, 'imagem', [
    el('span', { class: 'etiqueta' }, `${c.w}×${c.h}`), el('span', { class: 'etiqueta' }, c.fmt),
    alterada ? el('span', { class: 'etiqueta azul' }, 'trocada') : null]);
  const sec = secao(box, 'Imagem');
  const cv = el('canvas', { class: 'xadrez prev-grande', width: 520, height: 300 });
  miniatura(filme, char, cv);
  sec.append(cv);
  const ac = el('div', { class: 'acoes-linha' });
  ac.append(el('button', { class: 'btn-primario peq', onclick: () => emitir('trocar-imagem', char) }, 'Trocar imagem…'));
  ac.append(el('button', { class: 'btn peq', onclick: () => exportarPNG(filme, char) }, 'Exportar PNG'));
  if (alterada) ac.append(el('button', { class: 'btn peq', onclick: () => definirOp('Restaurar imagem', 'textura:' + char, null) }, 'Voltar à original'));
  sec.append(ac);
  sec.append(nota('Dica: exporte o PNG, edite no Photoshop/GIMP (pode até dobrar o tamanho para ficar mais nítido) e troque. ' +
    'O editor encaixa a nova imagem no mesmo lugar da original, ajustando as coordenadas sozinho.', 'info'));
  // onde é usada
  const usos = [];
  if (S.raiz) percorrer(S.raiz, (n) => {
    if (n.tipo !== 'forma' || (n.filmeConteudo || n.filme) !== filme) return;
    if (n.charDef.itens.some((it) => it.img === char)) usos.push(n);
  });
  const u = secao(box, `Usada em ${usos.length} lugar(es)`);
  for (const n of usos.slice(0, 40)) {
    let alvo = n; while (alvo && alvo.place && !alvo.nome && alvo.pai && alvo.pai.place) alvo = alvo.pai;
    const b = el('button', { class: 'btn-fantasma peq', style: { justifyContent: 'flex-start' } }, caminhoNomes(n).slice(-3).join(' › ') || `#${n.char}`);
    b.onclick = () => { S.sel = (alvo || n).id; S.selImagem = null; emitir('selecao', 'props'); emitir('enquadrar'); };
    u.append(b);
  }
}

export async function exportarPNG(filme, char) {
  const t = filme.textura(char);
  if (!t.canvas) await t.promessa;
  if (!t.canvas) { aviso('Não consegui ler esta imagem.', { tipo: 'erro' }); return; }
  const png = t.canvas.toDataURL('image/png').split(',')[1];
  const base = filme.arquivo.split('/').pop().replace(/\.big$/i, '');
  try {
    const r = await api('exportar_png', { nome: `${base}_imagem${char}_${t.w}x${t.h}.png`, png });
    aviso('PNG exportado', { tipo: 'sucesso', detalhe: r.caminho });
  } catch (ex) { aviso(ex.message, { tipo: 'erro' }); }
}

// todas as imagens do placar aberto (e, se pedido, as dos componentes) em PNG, numa pasta só
export async function exportarTodas(comComponentes) {
  if (!S.doc) return;
  const base = S.doc.arquivo.split('/').pop().replace(/\.big$/i, '');
  const pasta = `${base}_imagens`;
  const lista = [];
  const deFilme = (f, sub) => f.modelo.chars.forEach((c, i) => { if (c && c.t === 'imagem') lista.push({ filme: f, char: i, sub }); });
  deFilme(S.doc.filme, '');
  if (comComponentes) {
    for (const imp of S.doc.filme.modelo.imports || []) {
      const f = await S.doc.filme.importar(imp.filme).catch(() => null);
      if (f) deFilme(f, f.arquivo.split('/').pop().replace(/\.big$/i, ''));
    }
  }
  if (!lista.length) { aviso('Nenhuma imagem para exportar.', { tipo: 'aviso' }); return; }
  const fim = aviso(`Exportando ${lista.length} imagem(ns)…`, { tempo: 600000 });
  let ok = 0, destino = null;
  const vistos = new Set();
  try {
    for (const { filme, char, sub } of lista) {
      const chave = `${filme.arquivo}#${char}`;
      if (vistos.has(chave)) continue;
      vistos.add(chave);
      const t = filme.textura(char);
      if (!t.canvas) await t.promessa;
      if (!t.canvas) continue;
      const png = t.canvas.toDataURL('image/png').split(',')[1];
      const r = await api('exportar_png', { nome: `imagem${String(char).padStart(3, '0')}_${t.w}x${t.h}.png`, png, pasta: sub ? `${pasta}/componentes/${sub}` : pasta, mostrar: false });
      if (!sub) destino = r.pasta;
      destino = destino || r.pasta.replace(/[\\/]componentes[\\/].*$/, '');
      ok += 1;
    }
  } catch (ex) {
    fim();
    aviso(ex.message, { tipo: 'erro' });
    return;
  }
  fim();
  aviso(`${ok} imagem(ns) exportada(s)`, { tipo: 'sucesso', detalhe: destino || '' });
  if (destino) api('explorer', { caminho: destino }).catch(() => {});
}

export function atualizarCamposDaVista() {
  if (S.atualizarCampos) S.atualizarCampos();
}

export { fmtNum };
