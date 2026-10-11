// Tela inicial e diálogos (abrir pasta, escolher mundo, alterações, texturas, atalhos).
import { api, urlArquivo } from './api.js';
import { icone } from './icones.js';
import { el, esc, modal, aviso, fmtInt, nota, confirmar, copiarTexto, interruptor } from './ui.js';
import { nomeParam, PARAM_COR } from './materiais.js';

// ------------------------------------------------------------------ tela inicial
export async function telaInicial(app) {
  const raiz = document.getElementById('boas-vindas');
  raiz.innerHTML = '';
  let ini = { exports: [], recentes: [] };
  try { ini = await api('inicio'); } catch (e) { aviso(e.message, { tipo: 'erro' }); }
  const c = el('div', { class: 'bv-conteudo' });
  const hero = el('div', { class: 'bv-hero' }, el('div', { class: 'bv-hero-ic' }));
  const txt = el('div', {}, el('h1', {}, 'Editor de Estádios'),
    el('p', {}, 'Abra um estádio exportado pelo FIFA Editor Tool, veja o estádio inteiro em 3D, esconda partes, mova objetos, troque texturas e grave tudo direto nos arquivos — pronto para importar de volta no FET.'));
  const acoes = el('div', { class: 'bv-acoes' },
    el('button', { class: 'btn-primario grande', onclick: () => abrirPasta(app) }, icone('pastaAberta', 18), 'Abrir pasta exportada…'),
    el('button', { class: 'btn grande', onclick: () => app.abrirProjeto() }, icone('arquivo', 18), 'Abrir projeto…'));
  txt.append(acoes);
  hero.append(txt);
  c.append(hero);
  const grade = el('div', { class: 'bv-grade' });
  const esq = el('div', { class: 'bv-bloco' });
  esq.append(el('h3', {}, 'Estádios encontrados'));
  const cartoes = el('div', { class: 'bv-cartoes' });
  const vistos = new Set();
  for (const ex of ini.exports) {
    vistos.add(ex.pasta);
    const cart = el('div', { class: 'bv-cartao', role: 'group' });
    cart.innerHTML = icone('estadio', 22);
    const t = el('div', { class: 'txt' }, el('b', {}, ex.nome), el('small', { title: ex.pasta }, ex.pasta));
    const chips = el('div', { class: 'chips' });
    for (const m of ex.mundos) chips.append(el('button', { class: 'chip', title: 'Abrir este mundo', onclick: () => app.abrir([ex.pasta], m) }, m));
    t.append(chips);
    cart.append(t);
    cartoes.append(cart);
  }
  for (const r of ini.recentes || []) {
    if (r.pastas.length === 1 && vistos.has(r.pastas[0])) continue;
    const cart = el('button', { class: 'bv-cartao', onclick: () => app.abrir(r.pastas) });
    cart.innerHTML = icone('pasta', 22);
    cart.append(el('div', { class: 'txt' }, el('b', {}, r.nome), el('small', { title: r.pastas.join('\n') }, `${r.pastas[0]}${r.pastas.length > 1 ? ` + ${r.pastas.length - 1} de apoio` : ''} · ${r.quando}`)));
    cartoes.append(cart);
  }
  for (const pj of ini.projetos || []) {
    const cart = el('button', { class: 'bv-cartao', onclick: () => app.abrirProjeto(pj) });
    cart.innerHTML = icone('arquivo', 22);
    cart.append(el('div', { class: 'txt' }, el('b', {}, pj.split(/[\\/]/).pop().replace(/\.estadio\.json$/i, '')), el('small', { title: pj }, `Projeto · ${pj}`)));
    cartoes.append(cart);
  }
  if (!cartoes.children.length) cartoes.append(el('div', { class: 'bv-vazio' }, 'Nenhum export encontrado perto do editor. Use “Abrir pasta exportada…” e escolha a pasta onde o FET salvou os arquivos.'));
  esq.append(cartoes);
  const dir = el('div', { class: 'bv-bloco' });
  dir.append(el('h3', {}, 'Como funciona'));
  dir.append(el('div', { class: 'bv-passos', html: `
    <div class="bv-passo"><div><b>Exporte do FET</b> a pasta do estádio (o mundo em <i>worlds/stadiums/…</i> e os componentes em <i>worlds/components/stadiums/…</i>), com FBX, XML e PNG.</div></div>
    <div class="bv-passo"><div><b>Abra e edite aqui.</b> Esconda peças no jogo, mova e gire objetos, troque texturas e cores. Tudo tem desfazer (<kbd>Ctrl+Z</kbd>).</div></div>
    <div class="bv-passo"><div><b>Salve</b> (<kbd>Ctrl+S</kbd>). Os arquivos são gravados na própria pasta e o original fica guardado em <i>_editor_originais</i>.</div></div>
    <div class="bv-passo"><div><b>Importe no FET</b> os arquivos da lista <b>Alterações</b> (XML por cima do asset de mesmo nome).</div></div>` }));
  grade.append(esq, dir);
  c.append(grade);
  raiz.append(c);
}

// ------------------------------------------------------------------ navegador de pastas
export async function abrirPasta(app, { inicial = '', titulo = 'Abrir pasta exportada pelo FET', paraDestino = false } = {}) {
  let atual = null;
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  const linhaCaminho = el('div', { class: 'caminho-linha' });
  const inp = el('input', { type: 'text', placeholder: 'Cole o caminho da pasta ou navegue abaixo', spellcheck: 'false' });
  const ir = el('button', { class: 'btn' }, 'Ir');
  const nativo = el('button', { class: 'btn', title: 'Usar a janela de pastas do Windows' }, icone('pasta', 15), 'Procurar…');
  linhaCaminho.append(inp, ir, nativo);
  const info = el('div');
  const lista = el('div', { class: 'lista', style: { height: '320px' } });
  corpo.append(linhaCaminho, info, lista);
  let botaoAbrir;
  const m = modal({
    titulo, texto: paraDestino ? 'Escolha a pasta de destino.' : 'Escolha a pasta raiz do export (a que contém <i>worlds</i> ou <i>content</i>). Pastas reconhecidas aparecem com o ícone verde.',
    corpo, largo: true,
    botoes: [
      { rotulo: 'Cancelar', valor: null },
      { rotulo: paraDestino ? 'Usar esta pasta' : 'Abrir', classe: 'btn-primario', padrao: true, fn: () => atual?.caminho || inp.value.trim() || false },
    ],
  });
  botaoAbrir = m.caixa.querySelector('.btn-primario');
  async function navegar(caminho) {
    lista.innerHTML = '<div class="lista-item"><div class="txt"><small>Carregando…</small></div></div>';
    try {
      const r = await api('navegar', { caminho });
      atual = r;
      inp.value = r.caminho;
      lista.innerHTML = '';
      if (r.pai !== null && r.caminho) {
        const up = el('div', { class: 'lista-item', onclick: () => navegar(r.pai) });
        up.innerHTML = icone('recolher', 16);
        up.append(el('div', { class: 'txt' }, el('b', {}, '..'), el('small', {}, 'pasta acima')));
        lista.append(up);
      }
      for (const p of r.pastas) {
        const it = el('div', { class: 'lista-item', ondblclick: () => navegar(p.caminho), onclick: () => { lista.querySelectorAll('.sel').forEach((x) => x.classList.remove('sel')); it.classList.add('sel'); inp.value = p.caminho; atual = { caminho: p.caminho }; } });
        it.innerHTML = icone('pasta', 16);
        it.append(el('div', { class: 'txt' }, el('b', {}, p.nome)));
        lista.append(it);
      }
      if (!r.pastas.length) lista.append(el('div', { class: 'lista-item' }, el('div', { class: 'txt' }, el('small', {}, 'Pasta vazia'))));
      info.innerHTML = '';
      if (r.export && !paraDestino) info.append(nota(`Export do FET reconhecido: <b>${esc(r.export.mundos.join(', '))}</b>`, 'info'));
      botaoAbrir.disabled = !r.caminho;
    } catch (e) {
      lista.innerHTML = '';
      lista.append(el('div', { class: 'lista-item' }, el('div', { class: 'txt' }, el('small', {}, e.message))));
    }
  }
  ir.onclick = () => navegar(inp.value.trim());
  inp.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); navegar(inp.value.trim()); } };
  nativo.onclick = async () => {
    nativo.disabled = true;
    try {
      const r = await api('dialogo_pasta', { inicial: inp.value.trim() });
      if (r.caminho) { await navegar(r.caminho); if (!paraDestino) m.fechar(r.caminho); }
    } catch (e) { aviso(e.message, { tipo: 'erro' }); }
    nativo.disabled = false;
  };
  navegar(inicial || '');
  const escolhida = await m.promessa;
  if (!escolhida) return null;
  if (paraDestino) return escolhida;
  app.abrir([escolhida]);
  return escolhida;
}

// ------------------------------------------------------------------ escolher mundo
export function escolherMundo(mundos, pastas, ultimo = null) {
  return new Promise((res) => {
    const lista = el('div', { class: 'lista' });
    let escolhido = (mundos.find((m) => m.asset === ultimo) || mundos.find((m) => !/loader|cinematic/i.test(m.asset)) || mundos[0])?.asset;
    for (const m of mundos) {
      const it = el('div', { class: `lista-item export ${m.asset === escolhido ? 'sel' : ''}` });
      it.innerHTML = icone('estadio', 18);
      const desc = (m.asset.includes('cinematic') || m.nome.includes('loader') ? 'Cena de cinemática (exterior)' : m.principal ? 'Estádio' : 'Na pasta de apoio')
        + (m.asset === ultimo ? ' · aberto da última vez' : '');
      it.append(el('div', { class: 'txt' }, el('b', {}, m.nome), el('small', {}, `${desc} · ${m.asset}`)));
      it.onclick = () => { lista.querySelectorAll('.sel').forEach((x) => x.classList.remove('sel')); it.classList.add('sel'); escolhido = m.asset; };
      it.ondblclick = () => { escolhido = m.asset; md.fechar(escolhido); };
      lista.append(it);
    }
    const md = modal({
      titulo: 'Qual mundo abrir?', texto: `A pasta tem ${mundos.length} mundos de estádio.`, corpo: lista,
      botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Abrir', classe: 'btn-primario', padrao: true, fn: () => escolhido }],
    });
    md.promessa.then(res);
  });
}

// ------------------------------------------------------------------ alterações gravadas
export async function dialogoAlteracoes(app) {
  let dados;
  try { dados = await api('alteracoes'); } catch (e) { aviso(e.message, { tipo: 'erro' }); return; }
  const arquivos = dados.arquivos;
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  const pend = app.modelo.contarPendentes();
  if (pend) corpo.append(nota(`Há ${pend} alteraç${pend > 1 ? 'ões' : 'ão'} ainda não salva${pend > 1 ? 's' : ''} no editor. Salve (Ctrl+S) para elas entrarem nesta lista.`, 'alerta'));
  if (!arquivos.length) {
    corpo.append(el('div', { class: 'bv-vazio' }, 'Nenhum arquivo foi alterado pelo editor nesta pasta.'));
  } else {
    corpo.append(el('div', { style: { color: 'var(--texto-2)' }, html: `Estes arquivos diferem do original guardado em <i>_editor_originais</i>. No FET, importe cada um por cima do asset de mesmo nome (o caminho do asset está abaixo do nome).` }));
    const lista = el('div', { class: 'lista', style: { maxHeight: '360px' } });
    for (const a of arquivos) {
      const it = el('div', { class: 'lista-item' });
      it.innerHTML = icone(a.tipo === 'fbx' ? 'cubo' : a.tipo === 'png' ? 'imagem' : 'arquivo', 16);
      it.append(el('div', { class: 'txt' }, el('b', {}, a.rel.split('/').pop()), el('small', { title: a.rel }, `${a.asset} · ${a.quando}`)));
      it.append(el('button', { class: 'btn-icone peq', title: 'Mostrar no Explorer', html: icone('pasta', 14), onclick: (e) => { e.stopPropagation(); app.explorer(a.id); } }));
      it.append(el('button', { class: 'btn-icone peq', title: 'Copiar caminho do asset', html: icone('copiar', 14), onclick: (e) => { e.stopPropagation(); copiarTexto(a.asset); } }));
      it.append(el('button', { class: 'btn-icone peq', title: 'Restaurar o original deste arquivo', html: icone('restaurar', 14), onclick: async (e) => {
        e.stopPropagation();
        if (!await confirmar('Restaurar o original?', `<b>${esc(a.rel)}</b> volta a ser como foi exportado do FET. As edições gravadas nele se perdem.`, { rotulo: 'Restaurar', perigo: true })) return;
        await api('restaurar', { ids: [a.id] });
        aviso('Arquivo restaurado', { tipo: 'sucesso', detalhe: 'Recarregue o estádio para ver o estado original.', acao: { rotulo: 'Recarregar', fn: () => app.recarregar() } });
        m.fechar(); dialogoAlteracoes(app);
      } }));
      lista.append(it);
    }
    corpo.append(lista);
  }
  const m = modal({
    titulo: 'Arquivos alterados', corpo, largo: true,
    rodapeEsq: arquivos.length ? `${arquivos.length} arquivo${arquivos.length > 1 ? 's' : ''}` : '',
    botoes: [
      arquivos.length ? { rotulo: 'Restaurar todos', classe: 'btn-perigo', fn: async () => {
        if (!await confirmar('Restaurar todos os originais?', 'Todos os arquivos desta lista voltam a ser como foram exportados do FET.', { rotulo: 'Restaurar todos', perigo: true })) return false;
        await api('restaurar', { ids: arquivos.map((a) => a.id) });
        aviso('Originais restaurados', { tipo: 'sucesso' });
        app.recarregar();
      } } : null,
      arquivos.length ? { rotulo: 'Copiar para pasta…', classe: 'btn', fn: async () => {
        const destino = await abrirPasta(app, { titulo: 'Copiar arquivos alterados para…', paraDestino: true, inicial: app.pastas?.[0] ? app.pastas[0].replace(/[\\/][^\\/]*$/, '') : '' });
        if (!destino) return false;
        const r = await api('exportar', { destino });
        aviso(`${r.copiados} arquivo(s) copiados`, { tipo: 'sucesso', detalhe: r.destino, acao: { rotulo: 'Abrir pasta', fn: () => api('explorer', { caminho: r.destino }) } });
        return false;
      } } : null,
      { rotulo: 'Fechar', classe: 'btn-primario', valor: null, padrao: true },
    ].filter(Boolean),
  });
}

// ------------------------------------------------------------------ seletor de texturas
// Junta as texturas que os MVDBs exportados usam com TODAS as texturas do FC 26 instalado (quando conectado).
const LISTAS_JOGO = new Map();   // 'cache|prefixo' -> [[asset, pguid]] — o índice do jogo não muda com o editor aberto
export async function escolherTextura(app, { param, atual }) {
  const md = app.modelo;
  let exportadas = [];
  try { exportadas = await app.catalogoTexturas(); } catch (e) { aviso(e.message, { tipo: 'erro' }); }
  const porChave = new Map();
  for (const t of exportadas) porChave.set(t.asset.toLowerCase(), { asset: t.asset, ref: t.ref, pguid: t.pguid, png: t.png, exportada: true });
  for (const [a, t] of Object.entries(md.texturas)) {
    const k = a.toLowerCase();
    if (!porChave.has(k)) porChave.set(k, { asset: a, ref: t.ref, pguid: t.pguid, png: t.png });
    porChave.get(k).usada = true;
  }
  const jogoPronto = app.jogoInfo?.estado === 'pronto';
  let carregouTudo = false;
  async function juntarJogo(prefixo) {
    const chave = `${app.jogoInfo?.cache}|${prefixo}`;
    if (!LISTAS_JOGO.has(chave)) {
      app.carregando('Abrindo as texturas do jogo…', 'Só na primeira vez; depois a lista fica guardada', -1);
      try { LISTAS_JOGO.set(chave, (await api('jogo_texturas', { prefixo })).texturas); } finally { app.carregando(null); }
    }
    for (const [a, pg] of LISTAS_JOGO.get(chave)) {
      const k = a.toLowerCase();
      const e = porChave.get(k);
      if (e) e.jogo = true; else porChave.set(k, { asset: a, pguid: pg, jogo: true });
    }
  }
  if (jogoPronto) {
    try { await juntarJogo('content/worlds/'); } catch (e) { aviso('Não consegui listar as texturas do jogo', { tipo: 'aviso', detalhe: e.message }); }
  }
  const sufixo = /normal/i.test(param) ? 'normal' : /coef/i.test(param) ? 'coeff' : /color|adboard|decal/i.test(param) ? 'color' : '';
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  const barra = el('div', { class: 'caminho-linha' });
  const busca = el('input', { type: 'search', placeholder: 'Buscar textura pelo nome (ex.: concrete, seat, grass)…', autofocus: true, spellcheck: 'false' });
  const filtro = el('select', { class: 'seletor', style: { maxWidth: '260px' } });
  const opcoes = [['mundo', 'Usadas neste estádio (seguro)'], ['tipo', `Mesmo tipo (${sufixo || 'todas'})`]];
  if (jogoPronto) opcoes.push(['estadios', 'Todas de estádios e mundos (jogo)'], ['jogo', 'Todas do jogo (inclui kits, rostos…)']);
  opcoes.push(['default', 'Padrão do jogo (default)'], ['png', 'Só as exportadas (PNG)'], ['todas', 'Todas as conhecidas']);
  for (const [v, r] of opcoes) filtro.append(el('option', { value: v }, r));
  barra.append(busca, filtro);
  const grade = el('div', { class: 'grade-texturas', style: { maxHeight: '440px', overflow: 'auto', padding: '2px' } });
  const info = el('div', { style: { color: 'var(--texto-3)', fontSize: '12px' } });
  const explicacao = jogoPronto
    ? `Escolha a nova textura para <b>${esc(nomeParam(param))}</b>. A lista inclui as ${fmtInt(app.jogoInfo.texturas)} texturas do FC 26 instalado, com imagem. As que este estádio já usa vêm primeiro: elas já são carregadas pelo mundo no jogo. Uma textura que só outro mundo carrega aparece <b>branca</b> no jogo.`
    : `Escolha a nova textura para <b>${esc(nomeParam(param))}</b>. Conecte o FC 26 em <b>Configurações</b> para ver e usar todas as texturas do jogo, com imagem.`;
  corpo.append(nota(explicacao), barra, info, grade);
  let escolhida = null;
  let lista = [];
  const ordenar = () => {
    lista = [...porChave.values()].sort((a, b) => (!!b.usada - !!a.usada) || (!!(b.png || b.jogo) - !!(a.png || a.jogo))
      || (b.asset.includes('/worlds/') - a.asset.includes('/worlds/')) || a.asset.localeCompare(b.asset));
  };
  ordenar();
  const desenhar = async () => {
    const q = busca.value.trim().toLowerCase();
    const f = filtro.value;
    if (f === 'jogo' && !carregouTudo) {
      info.textContent = 'Carregando a lista completa do jogo…';
      try { await juntarJogo(''); carregouTudo = true; ordenar(); } catch (e) { aviso(e.message, { tipo: 'erro' }); }
    }
    const termos = q.split(/\s+/).filter(Boolean);
    let itens = lista.filter((t) => {
      const nome = t.asset.toLowerCase();
      if (termos.length && !termos.every((x) => nome.includes(x))) return false;
      if ((f === 'tipo' || f === 'mundo') && sufixo && !nome.includes(sufixo)) return false;
      if (f === 'mundo' && !t.usada) return false;
      if (f === 'estadios' && !nome.startsWith('content/worlds/')) return false;
      if (f === 'png' && !t.png) return false;
      if (f === 'default' && !nome.includes('/textures/default/')) return false;
      return true;
    });
    info.textContent = `${fmtInt(itens.length)} texturas${itens.length > 300 ? ' (mostrando 300; refine a busca)' : ''}`;
    itens = itens.slice(0, 300);
    grade.innerHTML = '';
    for (const t of itens) {
      const cart = el('div', { class: `cartao-tex ${t.asset === atual ? 'sel' : ''}`, title: t.asset });
      const url = app.materiais.urlTextura(t.asset, 128);
      const img = el('div', { class: 'tex-img' });
      if (url) {
        const im = el('img', { src: url, loading: 'lazy', alt: '', style: { width: '100%', height: '100%', objectFit: 'cover', borderRadius: '4px' } });
        im.onerror = () => { im.remove(); img.textContent = 'sem imagem'; };
        img.append(im);
      } else img.textContent = 'sem imagem';
      cart.append(img, el('b', {}, t.asset.split('/').pop()), el('small', {}, t.asset.replace(/^content\/worlds\//i, '').split('/').slice(0, -1).join('/')));
      if (t.usada) cart.append(el('small', { style: { color: 'var(--sucesso)' } }, '● já usada neste estádio'));
      cart.onclick = () => { grade.querySelectorAll('.sel').forEach((x) => x.classList.remove('sel')); cart.classList.add('sel'); escolhida = t; m.caixa.querySelector('.btn-primario').disabled = false; };
      cart.ondblclick = () => { escolhida = t; m.caixa.querySelector('.btn-primario').click(); };
      grade.append(cart);
    }
  };
  let tmr;
  busca.oninput = () => { clearTimeout(tmr); tmr = setTimeout(desenhar, 120); };
  filtro.onchange = desenhar;
  const m = modal({ titulo: 'Escolher textura', corpo, largo: true,
    botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Usar esta textura', classe: 'btn-primario', padrao: true, desabilitado: true, fn: async (bt) => {
      if (!escolhida) return false;
      if (!escolhida.ref) {
        bt.disabled = true;
        try {
          const g = await api('jogo_guids', { asset: escolhida.asset });
          escolhida.ref = g.ref; escolhida.pguid = g.pguid;
        } catch (e) { aviso('Não consegui ler o GUID da textura no jogo', { tipo: 'erro', detalhe: e.message }); bt.disabled = false; return false; }
      }
      if (!md.texturas[escolhida.asset]) md.texturas[escolhida.asset] = { png: escolhida.png || null, ref: escolhida.ref, pguid: escolhida.pguid, jogo: !!escolhida.jogo };
      return escolhida.asset;
    } }] });
  if (!sufixo || ![...porChave.values()].some((t) => t.usada && t.asset.toLowerCase().includes(sufixo))) filtro.value = jogoPronto ? 'estadios' : 'todas';
  desenhar();
  return m.promessa;
}

// ------------------------------------------------------------------ configurações (jogo / texturas)
export async function dialogoConfiguracoes(app) {
  let info;
  try { info = await api('jogo'); } catch (e) { aviso(e.message, { tipo: 'erro' }); return; }
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '12px' } });
  const estado = el('div');
  const desenharEstado = (i) => {
    estado.innerHTML = '';
    let html, tipo = '';
    if (i.estado === 'pronto') { html = `<b>Conectado ao FC 26.</b> ${fmtInt(i.texturas)} texturas disponíveis (imagens extraídas na hora e guardadas em <i>editor/cache</i>)${i.fonte === 'fmt' ? ' — pelo índice do FMT' : ' — lidas direto do jogo'}.`; tipo = 'info'; }
    else if (i.estado === 'indexando') html = `Lendo o índice do jogo… ${Math.round(i.progresso * 100)}% — ${esc(i.mensagem || '')}`;
    else if (i.estado === 'erro') { html = `Erro: ${esc(i.erro || '')}`; tipo = 'alerta'; }
    else { html = 'Não conectado. Informe a pasta do FC 26 abaixo (a que tem FC26.exe e a pasta Data).'; tipo = 'alerta'; }
    estado.append(nota(html, tipo));
  };
  desenharEstado(info);
  const linhaCaminho = (rot, valor, detectado, aoProcurar) => {
    const inp = el('input', { type: 'text', value: valor || '', placeholder: detectado ? `Detectado: ${detectado}` : 'Não encontrado', spellcheck: 'false' });
    const bt = el('button', { class: 'btn' }, icone('pasta', 14), 'Procurar…');
    bt.onclick = async () => { const v = await aoProcurar(inp.value); if (v) inp.value = v; };
    corpo.append(el('div', { style: { display: 'flex', flexDirection: 'column', gap: '4px' } }, el('b', { style: { fontSize: '12px' } }, rot), el('div', { class: 'caminho-linha' }, inp, bt)));
    return inp;
  };
  corpo.append(estado);
  const inpPasta = linhaCaminho('Pasta do FC 26 (onde fica FC26.exe)', info.pasta, info.detectado?.pasta, async (ini) => (await api('dialogo_pasta', { inicial: ini })).caminho);
  const inpCache = linhaCaminho('Opcional — índice do FMT (FC26.cache), só se a leitura direta falhar', info.cache, info.detectado?.cache, async (ini) => (await api('dialogo_arquivo', { modo: 'cache', inicial: ini ? ini.replace(/[\\/][^\\/]*$/, '') : '' })).caminho);
  const qual = el('select', { class: 'seletor', style: { maxWidth: 'none' } });
  for (const [v, r] of [[512, '512 px (mais leve)'], [1024, '1024 px (recomendado)'], [2048, '2048 px (mais nítido)'], [4096, '4096 px (máximo)']]) {
    const o = el('option', { value: v }, r);
    if (Number(info.qualidade) === v) o.selected = true;
    qual.append(o);
  }
  corpo.append(el('div', { class: 'linha-prop', style: { gridTemplateColumns: '180px 1fr' } }, el('label', {}, 'Tamanho das texturas na vista'), qual));
  const sw = interruptor({ titulo: 'Usar as texturas do jogo', descricao: 'Mostra as texturas reais nas malhas e permite escolher qualquer textura do FC 26.', marcado: info.ativo !== false, aoMudar: () => {} });
  corpo.append(sw.el);
  corpo.append(nota('O editor lê o catálogo do FC 26 direto da pasta do jogo (só leitura, uns 20 s na primeira vez; depois fica guardado em <i>editor/cache</i> e é refeito sozinho quando o jogo atualiza). Não precisa do FMT nem de exportar a pasta Content.'));
  let poll = setInterval(async () => {
    try { const i = await api('jogo'); desenharEstado(i); if (i.estado !== 'indexando') { app.aoMudarJogo(i); } } catch { /* servidor fechado */ }
  }, 1200);
  const m = modal({ titulo: 'Configurações', corpo, largo: true, aoFechar: () => clearInterval(poll),
    botoes: [{ rotulo: 'Fechar', valor: null }, { rotulo: 'Aplicar', classe: 'btn-primario', padrao: true, fn: async () => {
      try {
        const i = await api('jogo_config', { pasta: inpPasta.value, cache: inpCache.value, qualidade: Number(qual.value), ativo: sw.inp.checked });
        desenharEstado(i);
        app.aoMudarJogo(i, true);
        aviso('Configurações aplicadas', { tipo: 'sucesso', tempo: 1800 });
      } catch (e) { aviso(e.message, { tipo: 'erro' }); }
      return false;
    } }] });
  return m.promessa;
}

// ------------------------------------------------------------------ copiar material de outra seção
export function escolherMaterialOrigem(app, destino) {
  const md = app.modelo;
  const d = md.materiais.get(destino);
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  const busca = el('input', { type: 'search', placeholder: 'Buscar por malha, shader ou textura…', autofocus: true });
  const filtro = el('select', { class: 'seletor', style: { maxWidth: '240px' } });
  for (const [v, r] of [['mesmo', 'Mesmo sub-mundo (seguro)'], ['todos', 'Todos os sub-mundos']]) filtro.append(el('option', { value: v }, r));
  const lista = el('div', { class: 'lista', style: { maxHeight: '420px' } });
  corpo.append(nota('O material escolhido empresta o <b>shader</b>, as <b>texturas</b> e os <b>valores</b> para este. Depois dá para trocar a textura. Materiais de outro sub-mundo podem usar texturas que este mundo não carrega (ficam brancas no jogo).'),
    el('div', { class: 'caminho-linha' }, busca, filtro), lista);
  let escolhido = null;
  const todos = [...md.materiais.values()].filter((m) => m.variacao !== destino && m.base.shader && m.base.shader !== 'null');
  const desenhar = () => {
    const q = busca.value.trim().toLowerCase();
    lista.innerHTML = '';
    let n = 0;
    for (const m of todos) {
      if (filtro.value === 'mesmo' && m.arq !== d.arq) continue;
      const texto = `${m.malha} ${m.base.shader} ${Object.values(m.base.texturas).join(' ')}`.toLowerCase();
      if (q && !q.split(/\s+/).every((x) => texto.includes(x))) continue;
      if (++n > 400) break;
      const pCor = PARAM_COR.find((k) => m.base.texturas[k]);
      const url = pCor ? app.materiais.urlTextura(m.base.texturas[pCor], 128) : null;
      const it = el('div', { class: 'lista-item' });
      const sw = el('span', { class: 'amostra', style: url ? { backgroundImage: `url("${url}")` } : { background: '#666' } });
      it.append(sw, el('div', { class: 'txt' }, el('b', {}, `${m.base.shader}`),
        el('small', {}, `${m.malha.split('/').pop()} · ${Object.values(m.base.texturas).map((t) => t.split('/').pop()).slice(0, 3).join(', ') || 'sem texturas'}`)));
      it.onclick = () => { lista.querySelectorAll('.sel').forEach((x) => x.classList.remove('sel')); it.classList.add('sel'); escolhido = m.variacao; mm.caixa.querySelector('.btn-primario').disabled = false; };
      it.ondblclick = () => { escolhido = m.variacao; mm.fechar(escolhido); };
      lista.append(it);
    }
    if (!n) lista.append(el('div', { class: 'lista-item' }, el('div', { class: 'txt' }, el('small', {}, 'Nenhum material encontrado.'))));
  };
  busca.oninput = desenhar;
  filtro.onchange = desenhar;
  const mm = modal({ titulo: 'Copiar material de…', corpo, largo: true,
    botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Copiar para este material', classe: 'btn-primario', padrao: true, desabilitado: true, fn: () => escolhido || false }] });
  desenhar();
  return mm.promessa;
}

// ------------------------------------------------------------------ escolher parâmetro de textura novo
export function escolherParametro(app, variacao) {
  const md = app.modelo;
  const m = md.materiais.get(variacao);
  const existentes = new Set(Object.keys(m.texturas));
  const sugeridos = md.parametrosDoShader(m.base.shader).filter((p) => !existentes.has(p));
  const comuns = ['colorTexture', 'normalTexture', 'coefficientTexture', 'detailTexture'].filter((p) => !existentes.has(p) && !sugeridos.includes(p));
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  const lista = el('div', { class: 'lista' });
  let escolhido = null;
  const item = (p, desc) => {
    const it = el('div', { class: 'lista-item' }, el('div', { class: 'txt' }, el('b', {}, `${nomeParam(p)} (${p})`), el('small', {}, desc)));
    it.onclick = () => { lista.querySelectorAll('.sel').forEach((x) => x.classList.remove('sel')); it.classList.add('sel'); escolhido = p; inp.value = p; };
    it.ondblclick = () => { escolhido = p; mm.fechar(p); };
    lista.append(it);
  };
  sugeridos.forEach((p) => item(p, `Usado por outros materiais com o shader ${m.base.shader}`));
  comuns.forEach((p) => item(p, 'Parâmetro comum; confirme se o shader usa'));
  const inp = el('input', { type: 'text', placeholder: 'ou digite o nome do parâmetro (ex.: colorTexture)', spellcheck: 'false' });
  corpo.append(nota(`O shader <b>${esc(m.base.shader)}</b> só lê os parâmetros que ele conhece. Os sugeridos primeiro são os que outros materiais com o mesmo shader já usam.`), lista, el('div', { class: 'caminho-linha' }, inp));
  const mm = modal({ titulo: 'Adicionar textura', corpo, botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Escolher a textura…', classe: 'btn-primario', padrao: true, fn: () => (inp.value.trim() || escolhido || false) }] });
  return mm.promessa;
}

// ------------------------------------------------------------------ exportar com outro nome (batch import)
export async function dialogoRenomear(app) {
  const md = app.modelo;
  const mundo = (md.mundo || '').split('/').pop();
  const comp = mundo.replace(/_\d+$/, '');
  const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
  corpo.append(nota('Gera uma cópia dos arquivos com os nomes trocados (pastas, arquivos e o texto dentro dos XML), para fazer <b>batch import</b> no FET em outro estádio. Os originais não mudam. Atenção: os GUIDs internos continuam os do estádio de origem — teste com poucos arquivos primeiro.'));
  const pares = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '6px' } });
  const addPar = (de = '', para = '') => {
    const a = el('input', { type: 'text', value: de, placeholder: 'nome atual (ex.: events_stadium_517)', spellcheck: 'false' });
    const b = el('input', { type: 'text', value: para, placeholder: 'novo nome (ex.: maracana_999)', spellcheck: 'false' });
    const x = el('button', { class: 'btn-icone', title: 'Remover', html: icone('x', 14), onclick: () => { linha.remove(); previa(); } });
    const linha = el('div', { class: 'caminho-linha' }, a, el('span', { style: { alignSelf: 'center', color: 'var(--texto-3)' } }, '→'), b, x);
    a.oninput = b.oninput = () => { clearTimeout(tmr); tmr = setTimeout(previa, 300); };
    pares.append(linha);
  };
  let tmr;
  addPar(mundo, '');
  if (comp && comp !== mundo) addPar(comp, '');
  const maisPar = el('button', { class: 'btn peq', onclick: () => addPar() }, icone('mais', 13), 'Outra troca');
  const escopo = el('select', { class: 'seletor', style: { maxWidth: 'none' } });
  for (const [v, r] of [['alterados', 'Só os arquivos alterados pelo editor'], ['mundo', 'O estádio inteiro (mundo + componentes)'], ['tudo', 'Tudo que está na pasta do export']]) escopo.append(el('option', { value: v }, r));
  escopo.onchange = () => previa();
  const conteudo = interruptor({ titulo: 'Trocar também dentro dos XML', descricao: 'Nome dos assets e referências (recomendado).', marcado: true, aoMudar: () => {} });
  const lista = el('div', { class: 'lista', style: { maxHeight: '240px', fontSize: '12px' } });
  const resumo = el('div', { style: { color: 'var(--texto-3)', fontSize: '12px' } });
  corpo.append(el('b', { style: { fontSize: '12px' } }, 'Trocas de nome'), pares, maisPar,
    el('div', { class: 'linha-prop', style: { gridTemplateColumns: '120px 1fr' } }, el('label', {}, 'Arquivos'), escopo), conteudo.el, resumo, lista);
  const trocas = () => [...pares.children].map((l) => { const i = l.querySelectorAll('input'); return [i[0].value, i[1].value]; }).filter(([a, b]) => a.trim() && b.trim());
  async function previa() {
    const t = trocas();
    try {
      const r = await api('renomear_previa', { trocas: t, escopo: escopo.value });
      resumo.textContent = `${fmtInt(r.total)} arquivos · ${fmtInt(r.mudam)} mudam de nome${t.length ? '' : ' (preencha o novo nome)'}`;
      lista.innerHTML = '';
      for (const it of r.itens.slice(0, 200)) {
        lista.append(el('div', { class: 'lista-item', style: { padding: '5px 10px', cursor: 'default' } },
          el('div', { class: 'txt' }, el('small', { title: it.de }, it.de), it.muda ? el('b', { style: { fontSize: '12px', fontWeight: '500', color: 'var(--acento)' } }, '→ ' + it.para) : '')));
      }
    } catch (e) { resumo.textContent = e.message; }
  }
  previa();
  modal({ titulo: 'Exportar com outro nome', corpo, largo: true,
    botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Escolher destino e exportar…', classe: 'btn-primario', padrao: true, fn: async () => {
      const t = trocas();
      if (!t.length) { aviso('Preencha pelo menos um novo nome', { tipo: 'aviso' }); return false; }
      const destino = await abrirPasta(app, { titulo: 'Pasta de destino da exportação', paraDestino: true, inicial: (app.pastas?.[0] || '').replace(/[\\/][^\\/]*$/, '') });
      if (!destino) return false;
      try {
        const r = await api('renomear_exportar', { trocas: t, escopo: escopo.value, destino, conteudo: conteudo.inp.checked });
        aviso(`${fmtInt(r.arquivos)} arquivos exportados`, { tipo: 'sucesso', detalhe: `${r.xml_alterados} XML com nomes trocados · ${r.destino}`, acao: { rotulo: 'Abrir pasta', fn: () => api('explorer', { caminho: r.destino }) } });
      } catch (e) { aviso('Falha ao exportar', { tipo: 'erro', detalhe: e.message }); return false; }
    } }] });
}

// ------------------------------------------------------------------ atalhos
export function dialogoAtalhos() {
  const grupos = [
    ['Câmera', [['Girar em volta', 'Arrastar'], ['Mover (pan)', 'Shift + arrastar', 'Botão do meio'], ['Zoom', 'Roda do mouse'], ['Olhar em volta', 'Botão direito'], ['Voar', 'Botão direito + W A S D'], ['Subir / descer voando', 'E / Q'], ['Mais rápido', 'Shift'], ['Velocidade do voo', 'Roda com botão direito'], ['Enquadrar seleção', 'F', 'Numpad .'], ['Enquadrar tudo', 'Home'], ['Vista de cima', 'Numpad 7'], ['Vista de frente', 'Numpad 1'], ['Vista lateral', 'Numpad 3'], ['Perspectiva', 'Numpad 5']]],
    ['Seleção', [['Selecionar', 'Clique'], ['Somar / tirar', 'Ctrl + clique'], ['Selecionar em caixa', 'Ctrl + arrastar'], ['Selecionar tudo', 'Ctrl + A'], ['Inverter seleção', 'Ctrl + I'], ['Limpar seleção', 'Esc'], ['Selecionar o grupo acima', 'Duplo clique'], ['Selecionar cópias da malha', 'Shift + L']]],
    ['Ferramentas', [['Selecionar (sem gizmo)', 'Q'], ['Mover com gizmo', 'W'], ['Mover livre (segue o mouse)', 'G'], ['Mover livre: travar eixo', 'X / Y / Z'], ['Mover livre: travar plano (Shift+Y = no chão)', 'Shift + X / Y / Z'], ['Mover livre: confirmar / cancelar', 'Clique ou Enter / Esc'], ['Girar', 'R', 'E'], ['Escalar', 'S'], ['Escalar por igual', 'Shift ao arrastar'], ['Encaixe (passos)', 'Segurar Ctrl', 'X'], ['Espaço local / global', 'L']]],
    ['Luzes', [['Adicionar com clique', 'Ferramentas › Luzes'], ['Duplicar luz selecionada', 'Ctrl + D'], ['Sair do modo adicionar', 'Esc']]],
    ['Visibilidade', [['Ocultar no editor', 'H'], ['Ocultar o resto', 'Shift + H'], ['Mostrar tudo', 'Alt + H'], ['Isolar seleção', '/', 'Numpad /'], ['Ocultar / mostrar no jogo', 'Delete'], ['Modo de exibição', 'Z'], ['Texturas liga/desliga', 'T']]],
    ['Arquivo', [['Salvar nos arquivos do jogo', 'Ctrl + S'], ['Salvar projeto (trabalho em andamento)', 'Ctrl + Shift + S'], ['Desfazer', 'Ctrl + Z'], ['Refazer', 'Ctrl + Shift + Z', 'Ctrl + Y'], ['Buscar na estrutura', 'Ctrl + F'], ['Abrir pasta', 'Ctrl + O'], ['Esta ajuda', '?', 'F1']]],
  ];
  const t = el('div', { class: 'tabela-atalhos' });
  for (const [g, itens] of grupos) {
    t.append(el('h4', {}, g));
    for (const [rot, ...teclas] of itens) {
      t.append(el('div', {}, el('span', {}, rot), el('span', { html: teclas.map((k) => `<kbd>${esc(k)}</kbd>`).join(' ou ') })));
    }
  }
  modal({ titulo: 'Atalhos do teclado e mouse', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

export async function dialogoSobre() {
  let versao = '';
  try { versao = (await (await fetch('/api/versao')).json()).versao; } catch { /* servidor fechado */ }
  modal({ titulo: 'Editor de Estádios FC', texto: `Versão ${versao} · parte do <b>BRFP Super Tool</b>`,
    corpo: el('div', { style: { color: 'var(--texto-2)', lineHeight: '1.6' }, html: `
      Lê exports do FIFA Editor Tool (mundo, world parts, blueprints, grupos estáticos, MeshVariationDb, FBX e PNG) e grava as edições direto nos XML.<br><br>
      <b>O que é gravado</b><br>
      • Ocultar no jogo: <i>Excluded</i> da referência, <i>Visible</i> + 150 m abaixo em grupos estáticos, ou 150 m abaixo em objetos ligados à lógica.<br>
      • Mover/girar/escalar: <i>BlueprintTransform</i> / <i>InstanceTransforms</i>, e a entrada de iluminação (<i>LightmapGenMeshInstance</i>) da malha.<br>
      • Texturas e cores: o <i>MeshVariationDb</i> do sub-mundo (é o que o jogo usa; o XML da malha é ignorado).<br>
      • Substituir FBX/PNG e remover assentos da torcida: o próprio arquivo.<br><br>
      O original de cada arquivo fica em <i>_editor_originais</i> na pasta do export.` }),
    botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}
