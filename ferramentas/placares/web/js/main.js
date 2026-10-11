// Editor de Placares FC — interface principal.
import { api } from './api.js';
import { Filme, M, montarArvore } from './cena.js';
import { S, emitir, ouvir, pendentes, definirOp } from './estado.js';
import { icone } from './icones.js';
import {
  atualizarCamposDaVista, desenharArquivos, desenharCamadas, desenharImagens, desenharPropriedades, alternarOculto,
} from './paineis.js';
import { Render } from './render.js';
import { $, $$, abrirMenu, arquivoLocal, aviso, confirmar, el, esc, fecharMenu, menuAberto, modal, modalAberto, nota } from './ui.js';
import { acharBase, enquadrarConteudo, enquadrarSelecao, iniciarVista, pedirDesenho, selecionado } from './vista.js';
import { opPlace } from './estado.js';
import {
  A, aoNovaArvore, ativar, atualizarBarra, duracao, irPara, limpar as limparAnimacao, montarBarraTempo, pausar, simular, simularDepois, tocar,
} from './animacao.js';
import { carregarCatalogo, desenharAnimacao, desenharFontes, estiloTexto } from './codigo.js';

// ================================================================ início
async function iniciar() {
  $('#btn-desfazer').innerHTML = icone('desfazer', 16);
  $('#btn-refazer').innerHTML = icone('refazer', 16);
  $('.btn-salvar-ic').innerHTML = icone('salvar', 15);
  $('#btn-fontes').innerHTML = icone('config', 16);
  for (const c of $$('.campo-busca-ic')) c.innerHTML = icone('busca', 14);
  try {
    S.render = new Render($('#tela'));
  } catch (ex) {
    aviso('Este navegador não consegue desenhar a prévia (WebGL2): ' + ex.message, { tipo: 'erro' });
    return;
  }
  iniciarVista(S.render);
  S.render.estiloTexto = estiloTexto;
  montarBarraTempo();
  montarMenus();
  ligarInterface();
  divisores();
  await carregarInicio();
  boasVindas();
  if (S.inicio.jogo.estado === 'carregando') esperarJogo();
}

async function carregarInicio() {
  S.inicio = await api('inicio');
  atualizarTopo();
  desenharArquivos();
  carregarConjuntos();
}

async function esperarJogo() {
  for (let i = 0; i < 240; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const r = await api('inicio');
    S.inicio = r;
    if (r.jogo.estado !== 'carregando') break;
  }
  atualizarTopo();
  desenharArquivos();
  carregarConjuntos();
  if ($('#app').classList.contains('sem-arquivo')) boasVindas();
}

async function carregarConjuntos() {
  S.conjuntos = null;
  desenharArquivos();
  const f = (S.inicio.fontes || []).find((x) => x.id === S.fonteAtual);
  if (!f || (f.tipo === 'jogo' && f.estado !== 'pronto')) return;
  try {
    const r = await api('conjuntos', { fonte: S.fonteAtual });
    S.conjuntos = r.conjuntos;
  } catch (ex) {
    S.conjuntos = [];
    aviso('Não consegui listar os placares: ' + ex.message, { tipo: 'erro' });
  }
  desenharArquivos();
}

function atualizarTopo() {
  const sai = S.inicio?.saida || {};
  const b = $('#btn-saida');
  b.innerHTML = icone(sai.eh_le ? 'jogo' : 'pasta', 15) + `<span>${esc(sai.eh_le ? 'Saída: Live Editor' : sai.caminho ? 'Saída: ' + sai.nome : 'Escolher saída')}</span>`;
  b.title = sai.caminho ? 'Os placares editados são gravados em\n' + sai.caminho : 'Escolha onde gravar os placares editados';
  const j = S.inicio?.jogo || {};
  $('#status-jogo').innerHTML = '';
  $('#status-jogo').append(el('span', { class: 'estado-ponto ' + (j.estado === 'pronto' ? 'ok' : j.estado === 'carregando' ? 'carregando' : 'erro') }),
    ' ' + (j.estado === 'pronto' ? `FC 26: ${j.arquivos.toLocaleString('pt-BR')} arquivos` : j.estado === 'carregando' ? 'Lendo o FC 26…' : 'FC 26 não encontrado'));
  const t = $('#titulo-arquivo');
  t.innerHTML = '';
  if (S.doc) {
    t.append(el('b', {}, S.doc.arquivo.split('/').pop()), el('span', { class: 'pasta' }, '· ' + (S.doc.fonte.tipo === 'jogo' ? 'FC 26' : S.doc.fonte.nome)));
    if (S.doc.alvo.toLowerCase() !== S.doc.arquivo.toLowerCase()) t.append(el('span', { class: 'pasta' }, '→ ' + S.doc.alvo.split('/').slice(-2).join('/')));
  }
  const n = pendentes();
  $('#btn-salvar').disabled = !S.doc;
  $('#contador-pendentes').hidden = !n;
  $('#contador-pendentes').textContent = '●';
  $('#btn-desfazer').disabled = !S.hist.podeDesfazer;
  $('#btn-refazer').disabled = !S.hist.podeRefazer;
  $('#btn-desfazer').title = S.hist.podeDesfazer ? `Desfazer: ${S.hist.proximoDesfazer} (Ctrl+Z)` : 'Desfazer (Ctrl+Z)';
  $('#btn-refazer').title = S.hist.podeRefazer ? `Refazer: ${S.hist.proximoRefazer} (Ctrl+Shift+Z)` : 'Refazer (Ctrl+Shift+Z)';
  document.title = (n ? '● ' : '') + (S.doc ? S.doc.arquivo.split('/').pop() + ' — ' : '') + 'Editor de Placares FC';
}

// ================================================================ abrir / reconstruir
let geracao = 0;

async function abrirArquivo({ fonte, arquivo, alvo = null, continuar = true }) {
  if (S.doc && pendentes() && !(await confirmar('Descartar as alterações não salvas?', `O arquivo <b>${esc(S.doc.arquivo.split('/').pop())}</b> tem alterações que ainda não foram gravadas.`, { rotulo: 'Descartar e abrir', perigo: true }))) return;
  carregando(true, 'Abrindo ' + arquivo.split('/').pop());
  try {
    const r = await api('abrir', { fonte, arquivo, alvo, continuar });
    const filme = new Filme(r, { editavel: true });
    S.doc = { filme, arquivo: r.arquivo, alvo: r.alvo, fonte: r.fonte, ops: r.ops || {}, salvo: JSON.parse(JSON.stringify(r.ops || {})),
      destino: r.destino, saida: r.saida, editadoNaSaida: r.projeto };
    S.hist.limpar();
    S.sel = null;
    S.selImagem = null;
    ativar(false);
    limparAnimacao();
    S.render.ocultos.clear();
    S.render.limparCaches();
    S.abertosCam = new Set(['raiz']);
    const mudouFonte = S.fonteAtual !== fonte;
    S.fonteAtual = fonte;
    $('#app').classList.remove('sem-arquivo');
    await reconstruir({ enquadrar: true });
    simular();
    carregarCatalogo();
    trocarAba('camadas');
    if (mudouFonte) carregarConjuntos(); else desenharArquivos();
    if (r.projeto) aviso('Continuando a edição gravada antes', { detalhe: 'As alterações salvas deste placar foram carregadas. Para começar do zero use "Descartar edição gravada".' });
    else if (r.projeto_outro) aviso('Já existe uma versão editada deste placar na saída', { tipo: 'aviso', detalhe: 'Ela veio de outra fonte; salvar aqui vai substituí-la.' });
  } catch (ex) {
    aviso('Não consegui abrir o placar: ' + ex.message, { tipo: 'erro' });
  } finally { carregando(false); }
}

async function reconstruir({ enquadrar = false, props = true } = {}) {
  if (!S.doc) return;
  const g = ++geracao;
  S.doc.filme.aplicar(S.doc.ops);
  const raiz = await montarArvore(S.doc.filme);
  if (g !== geracao) return;
  S.raiz = raiz;
  S.render.definirCena(raiz);
  aoNovaArvore(raiz);
  if (enquadrar) {
    S.render.desenhar();       // calcula os limites antes de enquadrar
    enquadrarConteudo();
    setTimeout(() => { S.render.desenhar(); enquadrarConteudo(); }, 400);  // texturas e componentes chegando
  }
  pedirDesenho();
  desenharCamadas();
  if (S.aba === 'imagens') desenharImagens();
  if (props) desenharPropriedades(); else atualizarCamposDaVista();
  atualizarTopo();
}

ouvir('ops', () => { reconstruir({ props: false }); simularDepois(); });
// resultado novo da simulação (ou prévia ligada/desligada): abas e propriedades que mostram o código
ouvir('animacao', () => {
  if (S.aba === 'animacao') desenharAnimacao();
  if (S.aba === 'fontes') desenharFontes();
  redesenharPropriedades();
  atualizarBarra();
  pedirDesenho();
});
ouvir('catalogo', () => {
  if (S.aba === 'fontes') desenharFontes();
  redesenharPropriedades();
  pedirDesenho();
});

function redesenharPropriedades() {
  const box = $('#propriedades');
  if (box.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') return;
  const r = box.scrollTop;
  desenharPropriedades();
  box.scrollTop = r;
}
ouvir('props-externas', () => desenharPropriedades());
ouvir('abrir', (a) => abrirArquivo(a));
ouvir('selecao', (origem) => {
  if (origem !== 'imagens' && S.sel) S.selImagem = null;
  desenharPropriedades();
  desenharCamadas();
  if (S.aba === 'imagens') desenharImagens();
  if (S.aba === 'animacao' && origem !== 'codigo') desenharAnimacao();
  pedirDesenho();
});
ouvir('enquadrar', () => enquadrarSelecao());
ouvir('aba', (aba) => trocarAba(aba));
ouvir('salvar-como', () => salvarComo());
ouvir('descartar', () => descartar());
ouvir('trocar-imagem', (ch) => trocarImagem(ch));
ouvir('menu-vista', (e) => menuVista(e));
S.hist.addEventListener('mudou', () => atualizarTopo());

function carregando(sim, titulo = '', detalhe = '') {
  $('#carregando').hidden = !sim;
  if (sim) { $('#carregando-titulo').textContent = titulo; $('#carregando-detalhe').textContent = detalhe; }
}

// ================================================================ salvar
async function salvar(alvo = null) {
  if (!S.doc) return;
  if (!S.inicio.saida.caminho) { await escolherSaida(); if (!S.inicio.saida.caminho) return; }
  carregando(true, 'Gravando o placar…');
  try {
    const r = await api('salvar', { sessao: S.doc.filme.sessao, ops: S.doc.ops, alvo: alvo || S.doc.alvo });
    S.doc.salvo = JSON.parse(JSON.stringify(S.doc.ops));
    S.doc.alvo = r.alvo;
    S.doc.destino = r.destino;
    S.doc.editadoNaSaida = true;
    atualizarTopo();
    const le = S.inicio.saida.eh_le;
    aviso('Placar gravado', { tipo: 'sucesso', detalhe: r.destino + (le ? ' — abra o jogo pelo Live Editor para ver.' : ''),
      acao: { rotulo: 'Abrir pasta', fn: () => api('explorer', { caminho: r.destino }) }, tempo: 7000 });
    S.inicio.editados = (await api('editados')).editados;
    carregarConjuntos();
  } catch (ex) {
    aviso('Não consegui gravar: ' + ex.message, { tipo: 'erro' });
  } finally { carregando(false); }
}

async function salvarComo() {
  if (!S.doc) return;
  const atual = S.doc.alvo;
  const m = /overlay_(\d+)\.big$/i.exec(atual);
  const tipo = m ? m[1].slice(-3) : null;
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } });
  corpo.append(nota('Grava este placar com <b>outro caminho</b> na pasta de saída — por exemplo, usar o placar de um conjunto ' +
    'no lugar do placar de outra competição. O arquivo original não muda.', 'info'));
  const inp = el('input', { type: 'text', value: atual, spellcheck: 'false', style: { width: '100%', height: '32px', padding: '0 10px', background: 'var(--bg)', border: '1px solid var(--borda)', borderRadius: '6px', color: 'var(--texto)', font: '12px var(--mono)' } });
  if (tipo && S.conjuntos) {
    const sel = el('select', { class: 'seletor largo' });
    sel.append(el('option', { value: '' }, 'Usar no lugar do mesmo overlay de outro conjunto…'));
    const vistos = new Set();
    for (const g of S.conjuntos) {
      if (g.numero === null || g.numero === undefined || vistos.has(g.numero)) continue;
      vistos.add(g.numero);
      const caminho = g.pasta ? `data/ui/game/overlays/${g.pasta}/overlay_${g.numero}${tipo}.big` : `data/ui/game/overlays/overlay_${g.numero}${tipo}.big`;
      sel.append(el('option', { value: caminho }, `${g.titulo} (nº ${g.numero}) → overlay_${g.numero}${tipo}`));
    }
    sel.onchange = () => { if (sel.value) inp.value = sel.value; };
    corpo.append(sel);
  }
  corpo.append(el('label', { class: 'mudo' }, 'Caminho dentro da pasta de saída:'), inp);
  const v = await modal({
    titulo: 'Salvar como outro arquivo', corpo, largo: true,
    botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Salvar', classe: 'btn-primario', padrao: true, fn: () => inp.value.trim() }],
  }).promessa;
  if (!v) return;
  await salvar(v);
}

async function descartar() {
  if (!S.doc) return;
  if (!(await confirmar('Descartar a edição gravada?', `Apaga <b>${esc(S.doc.destino || S.doc.alvo)}</b> da pasta de saída (ou devolve o arquivo que estava lá antes). O jogo volta a usar o original.`, { rotulo: 'Descartar', perigo: true }))) return;
  try {
    const r = await api('descartar', { alvo: S.doc.alvo });
    S.inicio.editados = r.editados;
    aviso(r.restaurado ? 'O arquivo anterior foi devolvido à saída' : 'Edição descartada', { tipo: 'sucesso' });
    const { fonte, arquivo } = { fonte: S.doc.fonte.id, arquivo: S.doc.arquivo };
    S.doc.ops = {}; S.doc.salvo = {};
    await abrirArquivo({ fonte, arquivo, continuar: false });
    carregarConjuntos();
  } catch (ex) { aviso(ex.message, { tipo: 'erro' }); }
}

// ================================================================ trocar imagem
function base64DeBytes(u8) {
  let s = '';
  const passo = 0x8000;
  for (let i = 0; i < u8.length; i += passo) s += String.fromCharCode.apply(null, u8.subarray(i, i + passo));
  return btoa(s);
}

async function trocarImagem(char) {
  if (!S.doc) return;
  const arq = await arquivoLocal('image/png,image/jpeg,image/webp,image/bmp');
  if (!arq) return;
  let bmp;
  try { bmp = await createImageBitmap(arq); } catch { aviso('Não consegui ler essa imagem.', { tipo: 'erro' }); return; }
  if (bmp.width > 4096 || bmp.height > 4096) { aviso('Imagem grande demais (máximo 4096 px).', { tipo: 'erro' }); return; }
  const c = S.doc.filme.base.chars[char];
  const razaoOrig = c.w / c.h, razaoNova = bmp.width / bmp.height;
  const cv = document.createElement('canvas');
  cv.width = bmp.width; cv.height = bmp.height;
  const g = cv.getContext('2d', { willReadFrequently: true });
  g.drawImage(bmp, 0, 0);
  const px = g.getImageData(0, 0, cv.width, cv.height).data;
  carregando(true, 'Enviando a imagem…');
  try {
    const r = await api('imagem_enviar', { w: cv.width, h: cv.height, rgba: base64DeBytes(new Uint8Array(px.buffer)) });
    definirOp('Trocar imagem', 'textura:' + char, { op: 'textura', char, img: r.id, w: r.w, h: r.h }, { fundir: false });
    S.selImagem = char;
    emitir('props-externas');
    if (S.aba === 'imagens') desenharImagens();
    const det = `${c.w}×${c.h} → ${bmp.width}×${bmp.height}`;
    if (Math.abs(razaoOrig - razaoNova) / razaoOrig > 0.03) aviso('Imagem trocada (proporção diferente)', { tipo: 'aviso', detalhe: det + '. Ela foi esticada para caber no mesmo espaço da original.' });
    else aviso('Imagem trocada', { tipo: 'sucesso', detalhe: det });
  } catch (ex) { aviso('Não consegui trocar: ' + ex.message, { tipo: 'erro' }); } finally { carregando(false); }
}

// ================================================================ saída, fontes e configurações
async function escolherSaida() {
  const le = S.inicio.saida.padrao_le;
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } });
  corpo.append(nota('O editor <b>nunca altera o jogo nem os mods</b>: grava os placares editados numa pasta de saída, com a mesma árvore ' +
    '<code>data/ui/...</code>. A mais prática é a pasta <b>mods\\legacy do Live Editor</b>: o jogo carrega dali quando é aberto pelo Live Editor. ' +
    'Para usar no FIFA Editor Tool, escolha outra pasta e importe pelo Legacy Explorer.', 'info'));
  const lista = el('div', { class: 'lista' });
  if (le) {
    const it = el('div', { class: 'lista-item' + (S.inicio.saida.eh_le ? ' sel' : ''), html: icone('jogo', 18) });
    it.append(el('div', { class: 'txt' }, el('b', {}, 'Live Editor — mods\\legacy (recomendado)'), el('small', {}, le)));
    it.onclick = async () => { await api('saida', { caminho: '' }); fechar(); };
    lista.append(it);
  }
  const outra = el('div', { class: 'lista-item' + (!S.inicio.saida.eh_le && S.inicio.saida.caminho ? ' sel' : ''), html: icone('pasta', 18) });
  outra.append(el('div', { class: 'txt' }, el('b', {}, 'Outra pasta…'), el('small', {}, !S.inicio.saida.eh_le && S.inicio.saida.caminho ? S.inicio.saida.caminho : 'Para importar depois no FET (Legacy Explorer › Importar pasta)')));
  outra.onclick = async () => {
    const r = await api('dialogo', { modo: 'pasta', titulo: 'Pasta de saída dos placares editados' });
    if (r.caminho) { await api('saida', { caminho: r.caminho }); fechar(); }
  };
  lista.append(outra);
  corpo.append(lista);
  const m = modal({ titulo: 'Onde gravar os placares editados', corpo, largo: true, botoes: [{ rotulo: 'Fechar', valor: null }] });
  function fechar() { m.fechar(null); }
  await m.promessa;
  await carregarInicio();
}

async function gerenciarFontes() {
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } });
  const desenhar = () => {
    corpo.innerHTML = '';
    corpo.append(nota('Fontes são os lugares de onde o editor lê placares: o <b>FC 26</b> instalado, <b>mods .fifamod</b> (como o pack de placares do LTA) ' +
      'e <b>pastas</b> com a árvore <code>data/ui/...</code>. Mods e o jogo são só leitura.', 'info'));
    const lista = el('div', { class: 'lista' });
    for (const f of S.inicio.fontes) {
      const lin = el('div', { class: 'linha-fonte', html: icone(f.tipo === 'jogo' ? 'jogo' : f.tipo === 'mod' ? 'pacote' : 'pasta', 18) });
      const det = f.tipo === 'jogo' ? (f.pasta || '') + (f.estado === 'pronto' ? ` · ${f.arquivos} arquivos` : ' · ' + (f.estado || '')) :
        f.tipo === 'mod' ? `${f.autor || ''} · ${f.versao || ''} · ${f.arquivos} arquivos` : f.caminho || '';
      lin.append(el('div', { class: 'txt' }, el('b', {}, f.tipo === 'jogo' ? 'FC 26 (jogo instalado)' : f.nome), el('small', {}, det)));
      if (f.tipo === 'mod' || (f.tipo === 'pasta' && f.id !== 'saida')) {
        const x = el('button', { class: 'btn-icone peq', title: 'Remover da lista', html: icone('x', 14) });
        x.onclick = async () => { S.inicio = await api('fonte_remover', { id: f.id }); if (S.fonteAtual === f.id) S.fonteAtual = 'jogo'; desenhar(); };
        lin.append(x);
      }
      if (f.tipo === 'jogo') {
        const b = el('button', { class: 'btn peq' }, 'Trocar pasta…');
        b.onclick = async () => {
          const r = await api('dialogo', { modo: 'pasta', titulo: 'Pasta do EA SPORTS FC 26' });
          if (!r.caminho) return;
          try { S.inicio = await api('jogo_config', { pasta: r.caminho }); desenhar(); esperarJogo(); } catch (ex) { aviso(ex.message, { tipo: 'erro' }); }
        };
        lin.append(b);
      }
      lista.append(lin);
    }
    corpo.append(lista);
    const ac = el('div', { class: 'acoes-linha' });
    ac.append(el('button', { class: 'btn', html: icone('pacote', 15) + 'Adicionar mod .fifamod…', onclick: () => adicionarFonte('mod', desenhar) }));
    ac.append(el('button', { class: 'btn', html: icone('pasta', 15) + 'Adicionar pasta…', onclick: () => adicionarFonte('pasta', desenhar) }));
    corpo.append(ac);
  };
  desenhar();
  await modal({ titulo: 'Fontes de placares', corpo, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', valor: null, padrao: true }] }).promessa;
  desenharArquivos();
  carregarConjuntos();
}

async function adicionarFonte(tipo, depois = null) {
  const r = await api('dialogo', { modo: tipo === 'mod' ? 'mod' : 'pasta', titulo: tipo === 'pasta' ? 'Pasta com data\\ui\\... (ex.: C:\\FC 26 Live Editor\\mods\\legacy)' : '' });
  if (!r.caminho) return;
  carregando(true, 'Lendo ' + r.caminho.split(/[\\/]/).pop());
  try {
    S.inicio = await api('fonte_adicionar', { tipo, caminho: r.caminho });
    const nova = S.inicio.fontes.find((f) => f.tipo === tipo && (f.caminho || '').toLowerCase().startsWith(r.caminho.toLowerCase().slice(0, 3)) && (f.caminho || '').toLowerCase().includes(r.caminho.split(/[\\/]/).pop().toLowerCase()));
    if (nova) S.fonteAtual = nova.id;
    aviso(tipo === 'mod' ? 'Mod adicionado' : 'Pasta adicionada', { tipo: 'sucesso', detalhe: nova ? nova.nome : r.caminho });
    desenharArquivos();
    carregarConjuntos();
    if (depois) depois();
  } catch (ex) { aviso(ex.message, { tipo: 'erro' }); } finally { carregando(false); }
}

// ================================================================ tela inicial
function boasVindas() {
  const bv = $('#boas-vindas');
  bv.innerHTML = '';
  const c = el('div', { class: 'bv-conteudo' });
  const hero = el('div', { class: 'bv-hero' }, el('div', { class: 'bv-hero-ic' }));
  const txt = el('div', {});
  txt.append(el('h1', {}, 'Editor de Placares FC'),
    el('p', {}, 'Abra os placares e overlays de transmissão do EA SPORTS FC 26 (do jogo ou de mods como o pack do LTA), veja como ficam na tela, mova os elementos, mude cores, troque imagens e grave para usar no jogo com o Live Editor.'));
  const acoes = el('div', { class: 'bv-acoes' });
  const j = S.inicio.jogo;
  const btPlacar = el('button', { class: 'btn-primario grande', html: icone('placar', 18) + 'Abrir o placar do jogo' });
  btPlacar.disabled = j.estado !== 'pronto';
  btPlacar.title = 'Generic / overlay_9002 — o placar padrão usado na maioria das competições';
  btPlacar.onclick = () => abrirArquivo({ fonte: 'jogo', arquivo: 'data/ui/game/overlays/Generic/overlay_9002.big' });
  const btLista = el('button', { class: 'btn grande', html: icone('camadas', 18) + 'Ver todos os placares' });
  btLista.onclick = () => { $('#app').classList.remove('sem-arquivo'); trocarAba('arquivos'); };
  const btMod = el('button', { class: 'btn grande', html: icone('pacote', 18) + 'Abrir mod .fifamod…' });
  btMod.onclick = async () => { await adicionarFonte('mod'); $('#app').classList.remove('sem-arquivo'); trocarAba('arquivos'); };
  acoes.append(btPlacar, btLista, btMod);
  txt.append(acoes);
  hero.append(txt);
  c.append(hero);

  const grade = el('div', { class: 'bv-grade' });
  const esq = el('div', { class: 'bv-bloco' });
  esq.append(el('h3', {}, 'Situação'));
  const cartoes = el('div', { class: 'bv-cartoes' });
  const cartao = (ic, titulo, sub, cor = '') => {
    const k = el('div', { class: 'bv-cartao', html: icone(ic, 20) });
    k.append(el('div', { class: 'txt' }, el('b', {}, titulo), el('small', { title: sub }, sub)));
    if (cor) k.querySelector('.ic').style.color = cor;
    return k;
  };
  cartoes.append(cartao('jogo', j.estado === 'pronto' ? `FC 26 encontrado — ${j.arquivos.toLocaleString('pt-BR')} arquivos de interface` : j.estado === 'carregando' ? 'Lendo o FC 26…' : 'FC 26 não encontrado',
    j.pasta || 'Configure a pasta do jogo em Arquivo › Fontes', j.estado === 'pronto' ? 'var(--sucesso)' : j.estado === 'carregando' ? 'var(--alerta)' : 'var(--perigo)'));
  const sai = S.inicio.saida;
  const kSai = cartao(sai.eh_le ? 'jogo' : 'pasta', sai.caminho ? (sai.eh_le ? 'Gravando na pasta do Live Editor' : 'Gravando em ' + sai.nome) : 'Escolha onde gravar', sai.caminho || '');
  kSai.style.cursor = 'pointer';
  kSai.onclick = escolherSaida;
  cartoes.append(kSai);
  const mods = S.inicio.fontes.filter((f) => f.tipo === 'mod');
  if (mods.length) for (const m of mods) cartoes.append(cartao('pacote', 'Mod: ' + m.nome, `${m.autor || ''} · ${m.arquivos} arquivos`));
  esq.append(cartoes);
  if (S.inicio.editados.length) {
    esq.append(el('h4', {}, 'Editados'));
    const lst = el('div', { class: 'bv-cartoes' });
    for (const p of S.inicio.editados.slice(0, 8)) {
      const k = el('button', { class: 'bv-cartao', html: icone('placar', 18) });
      k.append(el('div', { class: 'txt' }, el('b', {}, p.alvo.split('/').slice(-2).join('/')), el('small', {}, `${p.quando} · ${p.fonte?.nome || ''}${p.existe ? '' : ' · arquivo não está mais na saída'}`)));
      k.onclick = () => abrirArquivo({ fonte: p.fonte.id, arquivo: p.arquivo, alvo: p.alvo });
      lst.append(k);
    }
    esq.append(lst);
  }
  const dir = el('div', { class: 'bv-bloco' });
  dir.append(el('h3', {}, 'Como funciona'));
  const passos = el('div', { class: 'bv-passos' });
  const passo = (html) => passos.append(el('div', { class: 'bv-passo', html: `<span>${html}</span>` }));
  passo('<b>Escolha um conjunto.</b> Cada competição usa um conjunto de overlays (Generic = nº 9, Premier League = 6, Champions = 10…). No pack do LTA cada liga tem o seu (Brasileirão = 35).');
  passo('<b>Abra o placar</b> (o overlay terminado em <b>002</b>) ou outro overlay: escalação, substituição, cartões…');
  passo('<b>Edite</b>: clique e arraste, mude escala, cores e visibilidade, troque as imagens (aba Imagens) por PNGs seus.');
  passo('<b>Salve</b>: o arquivo vai para a pasta de saída. Com o Live Editor, basta abrir o jogo por ele.');
  dir.append(passos);
  dir.append(el('div', { style: { marginTop: '14px' } }, nota('Os textos (times, placar, relógio) e as cores dos times são aplicados pelo jogo durante a partida — na prévia aparecem exemplos.', '')));
  grade.append(esq, dir);
  c.append(grade);
  bv.append(c);
}

// ================================================================ menus, abas e atalhos
function montarMenus() {
  const nav = $('#menus');
  const menus = {
    Arquivo: () => [
      { rotulo: 'Início', icone: 'placar', fn: () => { boasVindas(); $('#app').classList.add('sem-arquivo'); } },
      '-',
      { rotulo: 'Salvar', icone: 'salvar', atalho: 'Ctrl+S', desabilitado: !S.doc, fn: () => salvar() },
      { rotulo: 'Salvar como outro arquivo…', desabilitado: !S.doc, fn: salvarComo },
      { rotulo: 'Descartar edição gravada…', desabilitado: !S.doc || !S.doc.editadoNaSaida, fn: descartar },
      '-',
      { rotulo: 'Fontes (jogo, mods, pastas)…', icone: 'config', fn: gerenciarFontes },
      { rotulo: 'Adicionar mod .fifamod…', icone: 'pacote', fn: () => adicionarFonte('mod') },
      { rotulo: 'Adicionar pasta…', icone: 'pasta', fn: () => adicionarFonte('pasta') },
      '-',
      { rotulo: 'Pasta de saída…', icone: 'jogo', fn: escolherSaida },
      { rotulo: 'Abrir a pasta de saída no Explorer', icone: 'externo', desabilitado: !S.inicio?.saida?.caminho, fn: () => api('explorer', { caminho: S.doc?.destino || S.inicio.saida.caminho }) },
    ],
    Editar: () => [
      { rotulo: 'Desfazer', icone: 'desfazer', atalho: 'Ctrl+Z', desabilitado: !S.hist.podeDesfazer, fn: desfazer },
      { rotulo: 'Refazer', icone: 'refazer', atalho: 'Ctrl+Shift+Z', desabilitado: !S.hist.podeRefazer, fn: refazer },
      '-',
      { rotulo: 'Selecionar o grupo de cima', atalho: 'Esc', desabilitado: !S.sel, fn: subirSelecao },
      { rotulo: 'Esconder no editor', atalho: 'H', desabilitado: !S.sel, fn: () => { const n = selecionado(); if (n) alternarOculto(n); } },
      { rotulo: 'Mostrar tudo no editor', atalho: 'Alt+H', fn: () => { S.render.ocultos.clear(); desenharCamadas(); pedirDesenho(); } },
    ],
    Exibir: () => [
      { rotulo: 'Enquadrar a seleção', atalho: 'F', fn: enquadrarSelecao },
      { rotulo: 'Enquadrar o placar inteiro', atalho: 'Home', fn: enquadrarConteudo },
      { rotulo: 'Tela inteira do jogo (1920×1080)', fn: () => { S.render.enquadrar(); pedirDesenho(); } },
      '-',
      { rotulo: 'Textos de exemplo', marcado: S.render.mostrarTextos, fn: () => { S.render.mostrarTextos = !S.render.mostrarTextos; pedirDesenho(); } },
      { rotulo: 'Prévia da animação', atalho: 'Espaço', marcado: S.animando, desabilitado: !S.doc, fn: () => { if (S.animando) ativar(false); else { ativar(true); irPara(0); tocar(); } } },
      { rotulo: 'Salvar imagem da prévia (PNG)…', fn: capturaPrevia },
    ],
    Ajuda: () => [
      { rotulo: 'Atalhos do teclado', icone: 'teclado', atalho: 'F1', fn: atalhos },
      { rotulo: 'Sobre os placares do FC e o pack do LTA', icone: 'info', fn: sobre },
      { rotulo: 'Sobre o editor', icone: 'info', fn: sobreEditor },
    ],
  };
  for (const [nome, itens] of Object.entries(menus)) {
    const b = el('button', { class: 'menu-botao' }, nome);
    b.onclick = () => {
      if (menuAberto()) { fecharMenu(); return; }
      const r = b.getBoundingClientRect();
      b.classList.add('aberto');
      abrirMenu(itens(), r.left, r.bottom + 4, { origem: b, aoFechar: () => b.classList.remove('aberto') });
    };
    nav.append(b);
  }
}

function menuVista(e) {
  const no = selecionado();
  abrirMenu([
    { rotulo: 'Selecionar o grupo de cima', desabilitado: !no, fn: subirSelecao },
    { rotulo: 'Enquadrar a seleção', atalho: 'F', desabilitado: !no, fn: enquadrarSelecao },
    { rotulo: 'Esconder no editor', atalho: 'H', desabilitado: !no, fn: () => alternarOculto(no) },
    '-',
    { rotulo: 'Restaurar posição e cor originais', desabilitado: !no || !no.place || !S.doc.ops['place:' + no.place.off], fn: () => definirOp('Restaurar', 'place:' + no.place.off, null) },
  ], e.clientX, e.clientY);
}

function trocarAba(aba) {
  S.aba = aba;
  for (const b of $$('.aba')) b.classList.toggle('ativa', b.dataset.aba === aba);
  $('#aba-arquivos').hidden = aba !== 'arquivos';
  $('#aba-camadas').hidden = aba !== 'camadas';
  $('#aba-imagens').hidden = aba !== 'imagens';
  $('#aba-animacao').hidden = aba !== 'animacao';
  $('#aba-fontes').hidden = aba !== 'fontes';
  if (aba === 'imagens') desenharImagens();
  if (aba === 'animacao') { desenharAnimacao(); if (S.doc && !A.dados && !A.carregando) simular(); }
  if (aba === 'fontes') desenharFontes();
  if (aba === 'camadas') desenharCamadas();
  if (aba === 'arquivos') desenharArquivos();
}

function ligarInterface() {
  for (const b of $$('.aba')) b.onclick = () => trocarAba(b.dataset.aba);
  $('#sel-fonte').onchange = () => { S.fonteAtual = $('#sel-fonte').value; carregarConjuntos(); };
  $('#btn-fontes').onclick = gerenciarFontes;
  let tb;
  $('#busca-arquivos').oninput = () => { clearTimeout(tb); tb = setTimeout(desenharArquivos, 150); };
  $('#busca-camadas').oninput = () => { clearTimeout(tb); tb = setTimeout(desenharCamadas, 150); };
  $('#filtro-camadas').onchange = desenharCamadas;
  $('#btn-salvar').onclick = () => salvar();
  $('#btn-saida').onclick = escolherSaida;
  $('#btn-desfazer').onclick = desfazer;
  $('#btn-refazer').onclick = refazer;
  $('.marca').style.cursor = 'pointer';
  $('.marca').onclick = () => { boasVindas(); $('#app').classList.add('sem-arquivo'); };
  window.addEventListener('keydown', teclado);
  window.addEventListener('beforeunload', (e) => { if (pendentes()) { e.preventDefault(); e.returnValue = ''; } });
  desenharPropriedades();
}

function desfazer() { if (S.hist.desfazer()) setTimeout(() => desenharPropriedades(), 30); }
function refazer() { if (S.hist.refazer()) setTimeout(() => desenharPropriedades(), 30); }

function subirSelecao() {
  const n = selecionado();
  if (!n) return;
  let p = n.pai;
  while (p && p.importado) p = p.pai;
  S.sel = p && p.place ? p.id : null;
  emitir('selecao', 'teclado');
}

function teclado(e) {
  const alvo = e.target;
  const digitando = alvo && (alvo.tagName === 'INPUT' || alvo.tagName === 'TEXTAREA' || alvo.tagName === 'SELECT' || alvo.isContentEditable);
  if (modalAberto()) return;
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === 's') { e.preventDefault(); salvar(); return; }
  if (digitando) return;
  if (ctrl && e.key.toLowerCase() === 'z') { e.preventDefault(); if (e.shiftKey) refazer(); else desfazer(); return; }
  if (ctrl && e.key.toLowerCase() === 'y') { e.preventDefault(); refazer(); return; }
  if (e.key === 'F1' || e.key === '?') { e.preventDefault(); atalhos(); return; }
  if (!S.doc) return;
  if (e.code === 'Space' && (S.animando || document.activeElement !== $('#tela'))) {
    e.preventDefault();
    if (!S.animando) { ativar(true); irPara(0); tocar(); } else if (A.tocando) pausar(); else tocar();
    return;
  }
  if (S.animando && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
    e.preventDefault();
    irPara(A.t + (e.key === 'ArrowRight' ? 1 : -1) * (e.shiftKey ? 10 : 1));
    return;
  }
  if (S.animando && (e.key === 'Home' || e.key === 'End')) { irPara(e.key === 'Home' ? 0 : duracao()); return; }
  if (e.key === 'f' || e.key === 'F') { enquadrarSelecao(); return; }
  if (e.key === 'Home') { enquadrarConteudo(); return; }
  if (e.key === 'Escape') { if (S.sel) subirSelecao(); return; }
  if ((e.key === 'h' || e.key === 'H') && e.altKey) { S.render.ocultos.clear(); desenharCamadas(); pedirDesenho(); return; }
  if (e.key === 'h' || e.key === 'H') { const n = selecionado(); if (n) alternarOculto(n); return; }
  if (e.key.startsWith('Arrow')) {
    const n = selecionado();
    if (!n || !n.editavel || !n.place || S.animando) return;
    e.preventDefault();
    const passo = e.shiftKey ? 10 : 1;
    const d = { ArrowLeft: [-passo, 0], ArrowRight: [passo, 0], ArrowUp: [0, -passo], ArrowDown: [0, passo] }[e.key];
    // a seta move na tela: converte para o espaço do grupo de cima
    const inv = M.inv(n.pai.mundo) || M.id();
    const [dx, dy] = M.vetor(inv, d[0], d[1]);
    const it = S.doc.filme.indicePlace.get(n.place.off);
    const { chave, op } = opPlace(n.place, acharBase(n.place.off) || n.place, { tx: [Math.round((it.tx[0] + dx) * 100) / 100, Math.round((it.tx[1] + dy) * 100) / 100] });
    definirOp('Mover', chave, op);
  }
}

function atalhos() {
  const t = el('div', { class: 'tabela-atalhos' });
  const linha = (txt, ...ks) => t.append(el('div', {}, el('span', {}, txt), el('span', {}, ...ks.map((k) => el('kbd', {}, k)))));
  t.append(el('h4', {}, 'Vista'));
  linha('Zoom', 'Roda do mouse'); linha('Arrastar a vista', 'Botão direito'); linha('Arrastar a vista', 'Espaço', 'Arrastar');
  linha('Enquadrar seleção', 'F'); linha('Enquadrar o placar', 'Home');
  t.append(el('h4', {}, 'Seleção e edição'));
  linha('Selecionar', 'Clique'); linha('Peça interna', 'Alt', 'Clique'); linha('Mover', 'Arrastar'); linha('Mover só num eixo', 'Shift', 'Arrastar');
  linha('Mover 1 px', '← → ↑ ↓'); linha('Mover 10 px', 'Shift', 'Setas'); linha('Grupo de cima', 'Esc');
  linha('Esconder no editor', 'H'); linha('Mostrar tudo', 'Alt', 'H');
  t.append(el('h4', {}, 'Prévia da animação'));
  linha('Tocar / pausar', 'Espaço'); linha('Quadro anterior / seguinte', '←', '→'); linha('10 quadros', 'Shift', '← →');
  linha('Início / fim', 'Home', 'End');
  t.append(el('h4', {}, 'Arquivo'));
  linha('Salvar', 'Ctrl', 'S'); linha('Desfazer', 'Ctrl', 'Z'); linha('Refazer', 'Ctrl', 'Shift', 'Z');
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', valor: null, padrao: true }] });
}

async function sobreEditor() {
  let versao = '';
  try { versao = (await api('versao')).versao; } catch { /* servidor fechado */ }
  modal({ titulo: 'Editor de Placares FC', texto: `Versão ${versao} · parte do <b>BRFP Super Tool</b>`,
    corpo: el('div', { style: { color: 'var(--texto-2)', lineHeight: '1.6' }, html: `
      Abre os placares (overlays APT) do jogo e de mods (.fifamod, pastas do Live Editor) e grava as edições na pasta de saída.<br><br>
      <b>2.0</b> — simulador das animações do jogo (ActionScript) com linha do tempo, constantes e curvas de animação, fontes (famílias do FIFA.xml e importação de TTF).<br>
      <b>1.0</b> — prévia e edição de textos, cores, imagens e posições.` }),
    botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

function sobre() {
  const c = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px', lineHeight: '1.55' } });
  c.innerHTML = `
  <p><b>Como o FC 26 guarda os placares.</b> Cada overlay de transmissão é um arquivo <code>data/ui/game/overlays/&lt;conjunto&gt;/overlay_&lt;N&gt;&lt;tipo&gt;.big</code>
  (um arquivo "legacy"). Dentro dele há uma animação no formato <b>APT da EA</b> (parecido com Flash): grupos, formas, textos, posições e cores,
  mais as imagens (DDS). O número do conjunto vem antes dos 3 últimos dígitos (Generic = 9, então <code>overlay_9002</code> é o placar do conjunto 9).
  Peças comuns ficam em <code>data/ui/game/globalComponents/</code> e são importadas pelos overlays.</p>
  <p><b>Qual conjunto cada competição usa</b> é definido por arquivos EBX <code>broadcasting/attribsys/presentation/overlays/overlays_tournament_&lt;id&gt;</code>
  (e <code>overlays_country_…</code>), que trazem o número do conjunto e uma paleta de cores. Esses EBX só mudam pelo FIFA Editor Tool.</p>
  <p><b>O pack do LTA</b> ("Pack de TV Total y Switcher") traz ${'~'}8.180 arquivos legacy: os overlays de dezenas de conjuntos novos (30 a 99, um por liga ou copa:
  35 = Brasileirão A, 37 = Copa do Brasil, 61 = Liga MX…) gravados direto em <code>overlays/overlay_&lt;N&gt;&lt;tipo&gt;.big</code>, os componentes de cada um,
  fontes novas (<code>data/ui/fonts/*.ttf</code> + <code>FIFA.xml</code>), escudos e 134 EBX que ligam as competições aos conjuntos.
  O add-on "Setpieces OFF" troca 319 overlays para esconder o menu de botões nas bolas paradas.</p>
  <p><b>O script do Live Editor</b> (<code>lua/autorun/AdrianScriptsRunner.lua</code>) é só um carregador: ele executa os 4 scripts cifrados
  (<code>.ltab</code>) da pasta <code>lua/autorun/LTA</code>, usando uma chave que vem no banco de dados do próprio mod. A lógica do "switcher"
  (trocar o placar conforme a competição) está nesses scripts fechados.</p>
  <p><b>Este editor</b> lê os placares do jogo ou de mods, mostra como ficam e grava a versão editada na pasta de saída — por padrão
  <code>C:\\FC 26 Live Editor\\mods\\legacy</code>, que o Live Editor carrega por cima do jogo e dos mods.</p>`;
  modal({ titulo: 'Sobre os placares do FC', corpo: c, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', valor: null, padrao: true }] });
}

async function capturaPrevia() {
  S.render.desenhar();
  const png = S.render.capturar().split(',')[1];
  try {
    const r = await api('exportar_png', { nome: (S.doc ? S.doc.arquivo.split('/').pop().replace(/\.big$/i, '') : 'previa') + '_previa.png', png });
    aviso('Prévia salva', { tipo: 'sucesso', detalhe: r.caminho });
  } catch (ex) { aviso(ex.message, { tipo: 'erro' }); }
}

function divisores() {
  for (const d of $$('.divisor')) {
    d.addEventListener('pointerdown', (e) => {
      d.setPointerCapture(e.pointerId);
      d.classList.add('arrastando');
      const lado = d.dataset.lado;
      const mover = (ev) => {
        const w = lado === 'esq' ? ev.clientX : window.innerWidth - ev.clientX;
        document.documentElement.style.setProperty(lado === 'esq' ? '--esq' : '--dir', Math.max(220, Math.min(560, w)) + 'px');
        pedirDesenho();
      };
      const soltar = () => { d.classList.remove('arrastando'); d.removeEventListener('pointermove', mover); d.removeEventListener('pointerup', soltar); };
      d.addEventListener('pointermove', mover);
      d.addEventListener('pointerup', soltar);
    });
  }
}

iniciar();
