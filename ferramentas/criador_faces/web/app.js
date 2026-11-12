// Criador de Faces — interface (BRFP Super Tool). Dois jeitos de criar a partir de fotos: o criador próprio, que roda no
// computador e já grava a face do FC 27 (FBX + textura), e o KeenFace (pago), cuja cabeça é convertida no MG Keen Converter.
import { $, el, esc, aviso, modal, confirmar, barraMenus, abrirMenu, divisorArrastavel, dialogoSobre, interruptor, nota, modalAberto, menuAberto, lerArquivoBase64, copiarTexto } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { PreviaGLB } from './previa.js';
import { instalarComponentes, mb } from './comum/componentes.js';
import { importarReferencias } from './comum/referencias.js';

const S = {
  versao: '', links: {}, fotos: [], tarefa: { fase: 'parado' }, opcoes: {}, saida: '', chave: {}, mg: false, historico: [],
  conta: null, contaErro: null, trocandoChave: false, sel: null, nome: '', nomeSugerido: '', limite: 15,
  polling: null, intervalo: 0, previa: null, previaIdem: null, previaInfo: null, previaErro: null, carregando: false,
  sig: {}, fechadas: new Set(), pendenteConfig: false, ultimaFase: null, imgs: new Map(),
  motor: 'proprio', local: {}, saidaLocal: '', jogador: '', limiteKeen: 15, limiteLocal: 6,
};
const ATIVAS = ['enviando', 'conferindo', 'confirmar', 'criando', 'na_fila', 'processando', 'baixando', 'local'];
const CANCELAVEIS = ['enviando', 'conferindo', 'confirmar', 'local'];
const ETAPAS = [['enviando', 'Enviar fotos'], ['conferindo', 'Conferir custo'], ['confirmar', 'Confirmar'], ['criando', 'Criar'],
  ['na_fila', 'Fila'], ['processando', 'Montar a cabeça'], ['baixando', 'Baixar']];
const STATUS = { enviando: ['Enviando', 'azul'], na_fila: ['Na fila', 'azul'], processando: ['Montando', 'azul'], pronta: ['Pronta', 'verde'],
  falhou: ['Falhou (sem custo)', 'vermelha'], apagada: ['Apagada no KeenFace', 'amarela'], nao_criada: ['Não criada', 'amarela'] };
const MODOS = {
  padrao: ['Fotos variadas', 'Padrão do KeenFace: de 1 a 15 fotos da mesma pessoa, de qualquer lugar (internet, celular, jogos), com luz e fundo diferentes. Textura PBR com limpeza (sem a luz das fotos).'],
  scan: ['Sessão de fotos', 'Scan Reconstruction: de 2 a 15 fotos tiradas na mesma sessão, com a pessoa parada, a mesma expressão e a mesma luz (frente e os dois lados a ~40°; perfis ajudam). A forma sai mais fiel.'],
};

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }
const fmtInt = (n) => Number(n || 0).toLocaleString('pt-BR');
const fmtMB = (b) => (b >= 1e6 ? `${(b / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB` : `${Math.max(1, Math.round((b || 0) / 1e3))} KB`);
const fmtTempo = (s) => (s >= 60 ? `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s` : `${s} s`);
const ativa = () => ATIVAS.includes(S.tarefa.fase);
const itemSel = () => S.historico.find((x) => x.idem === S.sel) || null;
const seguindo = (x) => x && x.seguindo && !['pronto', 'erro'].includes(x.seguindo.fase);
const preco = () => S.conta?.prices?.head || 150;
const proprio = () => S.motor !== 'keenface';
const daqui = (x) => x?.origem === 'local';
function dataCurta(s) {
  if (!s) return '';
  const [d, h] = s.split(' ');
  const [a, m, dia] = (d || '').split('-');
  return dia ? `${dia}/${m}/${a}${h ? ' ' + h.slice(0, 5) : ''}` : s;
}
// append do DOM escreveria "null" no lugar dos itens condicionais vazios
const anexar = (pai, ...fs) => pai.append(...fs.flat().filter((f) => f !== null && f !== undefined && f !== false && f !== ''));
const plural = (n, um, varios) => `${fmtInt(n)} ${n === 1 ? um : varios}`;
function encurtar(caminho, partes = 2) {
  const p = String(caminho || '').split(/[\\/]+/).filter(Boolean);
  return p.length > partes ? '…\\' + p.slice(-partes).join('\\') : String(caminho || '');
}
function mudou(chave, valor) {
  const s = JSON.stringify(valor);
  if (S.sig[chave] === s) return false;
  S.sig[chave] = s;
  return true;
}

// ---------------------------------------------------------------- estado
function aplicar(r) {
  if (!r) return;
  for (const k of ['fotos', 'tarefa', 'opcoes', 'saida', 'chave', 'mg', 'historico', 'local']) if (k in r) S[k] = r[k];
  if ('saida_local' in r) S.saidaLocal = r.saida_local;
  if ('nome_sugerido' in r) S.nomeSugerido = r.nome_sugerido;
  S.motor = S.opcoes.motor === 'keenface' ? 'keenface' : 'proprio';
  S.limite = proprio() ? S.limiteLocal : S.limiteKeen;
  if (r.falha) mostrarFalha(r.falha);
  const fase = S.tarefa.fase;
  if (fase !== S.ultimaFase) {
    const antes = S.ultimaFase;
    S.ultimaFase = fase;
    if (fase === 'pronto' && antes && ATIVAS.includes(antes)) aoFicarPronta();
    if (['pronto', 'erro'].includes(fase) && antes) atualizarConta(true);
  }
  if (S.sel && !itemSel()) { S.sel = null; mostrarPrevia(null); }
  if (mudou('fotos', [S.fotos, S.motor])) desenharFotos();
  desenharConfig();
  desenharVista();
  if (mudou('historico', [S.historico, S.sel])) desenharHistorico();
  desenharTopo();
  desenharStatus();
  vigiar();
}

async function atualizar() { aplicar(await api('estado').catch(() => null)); }

function vigiar() {
  const rapido = ativa() || S.historico.some(seguindo) || S.local?.preparo?.ativa || S.local?.conferindo;
  const ms = rapido ? 1000 : 8000;
  if (S.intervalo === ms) return;
  clearInterval(S.polling);
  S.intervalo = ms;
  S.polling = setInterval(atualizar, ms);
}

async function atualizarConta(silencioso = false) {
  if (!S.chave.definida) { S.conta = null; S.contaErro = null; desenharConfig(); desenharTopo(); return; }
  const r = await api('conta').catch((e) => ({ falha: { mensagem: e.message } }));
  S.conta = r.conta || null;
  S.contaErro = r.falha || null;
  if (!silencioso && r.falha) mostrarFalha(r.falha);
  desenharConfig();
  desenharTopo();
}

function mostrarFalha(f) {
  aviso(f.mensagem || 'Erro do KeenFace', {
    tipo: 'erro', tempo: 12000, detalhe: f.request_id ? `pedido ${f.request_id}` : '',
    acao: f.link ? { rotulo: 'Abrir o site', fn: () => abrirLink(null, f.link) } : null,
  });
}

function abrirLink(qual, url) { tentar(() => api('abrir_link', qual ? { qual } : { url })); }

// ---------------------------------------------------------------- fotos (painel da esquerda)
function imgFoto(f) {
  let img = S.imgs.get(f.id);
  if (!img) {
    img = el('img', { src: `foto?id=${f.id}`, alt: f.nome, loading: 'lazy', draggable: 'false' });
    S.imgs.set(f.id, img);
  }
  return img;
}

function desenharFotos() {
  const box = $('#fotos');
  box.innerHTML = '';
  for (const id of [...S.imgs.keys()]) if (!S.fotos.some((f) => f.id === id)) S.imgs.delete(id);
  if (!S.fotos.length) {
    box.append(el('div', { class: 'fotos-vazio' },
      el('div', { class: 'ic-grande', html: icone('camera', 48) }),
      el('b', {}, 'Arraste as fotos do jogador para cá'),
      el('span', {}, proprio() ? 'Uma de frente e uma de cada lado (de 1 a 6 fotos da mesma pessoa).' : 'De 1 a 15 fotos da mesma pessoa. O ideal é uma de frente e uma de cada lado.'),
      el('div', {}, el('button', { class: 'btn-primario', onclick: adicionarFotos, html: icone('arquivoMais', 15) + 'Adicionar fotos…' }))));
  } else {
    const grade = el('div', { class: 'grade-fotos' });
    S.fotos.forEach((f, i) => {
      const dim = f.largura ? `${f.largura}×${f.altura}` : (f.tipo || '').replace('image/', '').toUpperCase();
      const card = el('div', { class: `foto-card ${f.problema ? 'ruim' : ''}`, title: f.nome,
        oncontextmenu: (e) => { e.preventDefault(); menuFoto(f, i, e.clientX, e.clientY); } },
      el('div', { class: 'foto-img' }, f.previa ? imgFoto(f) : el('div', { class: 'sem-previa', html: icone('imagem', 26) + '<span>sem prévia<br>(o KeenFace lê normalmente)</span>' })),
      el('span', { class: 'foto-num' }, String(i + 1)),
      f.enviada && !proprio() ? el('span', { class: 'foto-enviada', title: 'Já está no KeenFace (vale 24 h): não precisa enviar de novo', html: icone('check', 11) + 'enviada' }) : null,
      el('button', { class: 'foto-tirar', title: 'Tirar da lista', html: icone('x', 13), onclick: () => removerFoto(f.id) }),
      el('div', { class: 'foto-info' }, el('b', {}, f.nome), el('small', {}, `${dim} · ${fmtMB(f.bytes)}`)),
      f.problema ? el('div', { class: 'foto-problema' }, f.problema) : null);
      grade.append(card);
    });
    if (S.fotos.length < S.limite) {
      grade.append(el('button', { class: 'foto-mais', onclick: adicionarFotos, title: 'Adicionar mais fotos (Ctrl+O)' }, el('span', { html: icone('mais', 22) }), 'Adicionar'));
    }
    box.append(grade);
  }
  box.append(el('div', { class: 'dicas-fotos' },
    el('div', { class: 'angulos' }, ...['Esquerda', 'Frente', 'Direita'].map((t, i) => el('span', { html: rostoAngulo(i - 1) + esc(t) }))),
    el('ul', {},
      el('li', {}, 'Nítidas, com o rosto grande e inteiro na foto, sem óculos nem boné.'),
      el('li', {}, 'Expressão neutra, boca fechada e olhos abertos; luz uniforme ajuda.'),
      el('li', {}, proprio() ? 'Os lados entre 40° e 70° (não precisa ser perfil): a mesma luz nas três deixa a pele sem manchas.' : 'Só a mesma pessoa em todas (nada de outra pessoa na foto).'))));
  const tot = S.fotos.reduce((s, f) => s + (f.bytes || 0), 0);
  $('#resumo-fotos').textContent = S.fotos.length ? `${S.fotos.length} de ${S.limite} fotos · ${fmtMB(tot)}` : 'Nenhuma foto';
  $('#resumo-fotos').classList.toggle('demais', S.fotos.length > S.limite);
  $('#btn-limpar').disabled = !S.fotos.length;
}

function rostoAngulo(lado) {
  // desenho simples de uma cabeça virada para o lado (-1 esquerda, 0 frente, 1 direita)
  const dx = lado * 4;
  return `<svg width="34" height="34" viewBox="0 0 34 34" fill="none" stroke="currentColor" stroke-width="1.5">
    <ellipse cx="17" cy="17" rx="10" ry="12.5"/>
    <circle cx="${13 + dx}" cy="15" r="1" fill="currentColor"/><circle cx="${21 + dx}" cy="15" r="1" fill="currentColor"/>
    <path d="M${17 + dx * 1.3} 15.5 l${lado ? lado * 1.6 : 0} 4.5 h${lado ? -lado * 1.6 : -1.5}"/>
    <path d="M${14 + dx} 23.5 q${3} 1.6 ${6} 0"/></svg>`;
}

function menuFoto(f, i, x, y) {
  abrirMenu([
    { rotulo: 'Passar para a frente', icone: 'setaCima', desabilitado: i === 0, fn: () => moverFoto(f.id, -i) },
    { rotulo: 'Uma posição antes', icone: 'seta', desabilitado: i === 0, fn: () => moverFoto(f.id, -1) },
    { rotulo: 'Uma posição depois', icone: 'setaBaixo', desabilitado: i === S.fotos.length - 1, fn: () => moverFoto(f.id, 1) },
    '-',
    { rotulo: 'Tirar da lista', icone: 'x', fn: () => removerFoto(f.id) },
  ], x, y);
}

async function adicionarFotos() {
  if (ativa() && CANCELAVEIS.includes(S.tarefa.fase)) { aviso('Espere o envio terminar (ou cancele) antes de mexer nas fotos.', { tipo: 'aviso' }); return; }
  const r = await tentar(() => api('escolher_fotos', {}));
  if (!r) return;
  aplicar(r);
  avisarAdicionadas(r);
}
function avisarAdicionadas(r) {
  if (r.novos) aviso(`${r.novos} foto(s) adicionada(s)`, { tipo: 'sucesso', tempo: 2200 });
  if (r.recusadas?.length) aviso(`${r.recusadas.length} arquivo(s) não entraram`, { tipo: 'aviso', detalhe: r.recusadas.slice(0, 4).join(' · '), tempo: 9000 });
}
async function removerFoto(id) { aplicar(await tentar(() => api('remover_foto', { id }))); }
async function moverFoto(id, passo) { aplicar(await tentar(() => api('mover_foto', { id, passo }))); }
async function limparFotos() {
  if (!S.fotos.length) return;
  if (!(await confirmar('Tirar todas as fotos?', 'As fotos continuam no seu computador; só saem desta lista.', { rotulo: 'Tirar todas' }))) return;
  aplicar(await tentar(() => api('limpar_fotos', {})));
}

function prepararSoltar() {
  let n = 0;
  const camada = $('#camada-soltar');
  const temArquivo = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  window.addEventListener('dragenter', (e) => { if (!temArquivo(e)) return; e.preventDefault(); n++; camada.hidden = false; });
  window.addEventListener('dragleave', () => { n = Math.max(0, n - 1); if (!n) camada.hidden = true; });
  window.addEventListener('dragover', (e) => { if (temArquivo(e)) e.preventDefault(); });
  window.addEventListener('drop', async (e) => {
    if (!temArquivo(e)) return;
    e.preventDefault();
    n = 0; camada.hidden = true;
    const arqs = [...e.dataTransfer.files].filter((f) => /\.(jpe?g|jfif|png|webp|heic|heif|avif)$/i.test(f.name));
    if (!arqs.length) { aviso('Solte fotos JPG, PNG, WebP, HEIC ou AVIF.', { tipo: 'aviso' }); return; }
    const fechar = aviso(`Recebendo ${arqs.length} foto(s)…`, { tempo: 60000 });
    try {
      const arquivos = [];
      for (const f of arqs) arquivos.push({ nome: f.name, dados: await lerArquivoBase64(f) });
      const r = await api('receber', { arquivos });
      aplicar(r);
      avisarAdicionadas(r);
    } catch (err) { aviso(err.message, { tipo: 'erro' }); } finally { fechar(); }
  });
}

// ---------------------------------------------------------------- painel da direita: conta, opções, criar
function secao(id, ic, titulo, corpo) {
  const d = el('details', { class: 'secao', open: !S.fechadas.has(id) });
  d.addEventListener('toggle', () => { if (d.open) S.fechadas.delete(id); else S.fechadas.add(id); });
  d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo).filter(Boolean)));
  return d;
}
function segmentado(opcoes, atual, aoMudar, desabilitado = false) {
  return el('div', { class: 'segmentado' }, ...opcoes.map(([v, rot, dica]) => el('button', {
    class: v === atual ? 'ativo' : '', title: dica || '', disabled: desabilitado, onclick: () => { if (v !== atual) aoMudar(v); } }, rot)));
}
function link(rotulo, qual) { return el('button', { class: 'link', onclick: () => abrirLink(qual), html: esc(rotulo) + icone('externo', 11) }); }

async function mudarOpcao(k, v) { aplicar(await tentar(() => api('opcoes', { [k]: v }))); }

function desenharConfig() {
  const box = $('#config');
  const { preparo: prep = {}, ...restoLocal } = S.local || {};
  const sig = [S.opcoes, S.saida, S.chave, S.conta, S.contaErro, S.trocandoChave, S.fotos.map((f) => [!!f.problema, f.tipo]), ativa(), S.nomeSugerido,
    S.motor, restoLocal, prep.ativa, prep.erro, S.saidaLocal];
  if (!mudou('config', sig)) {
    if (prep.ativa) {                        // só a barra do preparo anda
      const b = $('#prep-barra'), m = $('#prep-msg');
      if (b) b.firstChild.style.width = `${Math.round(Math.max(0.02, Math.min(1, prep.f || 0)) * 100)}%`;
      if (m) m.textContent = prep.msg || '';
    }
    return;
  }
  if (box.contains(document.activeElement) && document.activeElement.matches('input:not([type]), input[type=text], input[type=password], textarea')) {
    S.sig.config = null;                     // não redesenha com o usuário digitando: tenta no próximo ciclo
    return;
  }
  const rol = box.scrollTop;
  box.innerHTML = '';
  const bloqueado = ativa();
  const op = S.opcoes;
  box.append(el('div', { class: 'campo motor' }, el('label', {}, 'Como criar'),
    segmentado([['proprio', 'Criador próprio', 'Roda no seu computador, sem custo: grava direto a face do FC 27 (FBX + textura)'],
      ['keenface', 'KeenFace', 'Serviço pago (keenface.ai): a forma sai mais fiel; a cabeça é convertida depois no MG Keen Converter']], S.motor, (v) => mudarOpcao('motor', v), bloqueado),
    el('div', { class: 'descricao-modo' }, proprio()
      ? 'Grátis e no seu computador: as fotos não saem daqui. A face já sai pronta para o FET (headmorphpreset + textura careca).'
      : 'Pago (uns € 15 por cabeça, na sua conta): a forma sai mais fiel. A cabeça volta como .glb e é convertida no MG Keen Converter.')));
  if (proprio()) { desenharConfigProprio(box, bloqueado); box.scrollTop = rol; return; }

  // conta
  const conta = [];
  if (!S.chave.definida || S.trocandoChave) {
    const inp = el('input', { type: 'password', class: 'entrada mono', placeholder: 'ak_…', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Chave da API do KeenFace' });
    const guardar = async () => {
      if (!inp.value.trim()) { inp.focus(); return; }
      const r = await tentar(() => api('chave', { chave: inp.value.trim() }));
      if (!r) return;
      if (r.falha && !r.guardada) { mostrarFalha(r.falha); return; }
      S.trocandoChave = false;
      inp.blur();
      S.conta = r.conta || null;
      S.contaErro = r.falha || null;
      aplicar(r);
      aviso(r.conta ? 'Chave guardada e conferida' : 'Chave guardada (sem conexão para conferir agora)', { tipo: r.conta ? 'sucesso' : 'aviso' });
    };
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape' && S.chave.definida) { S.trocandoChave = false; inp.blur(); desenharConfig(); } });
    conta.push(el('p', { class: 'texto' }, 'Cada cabeça usa os créditos da sua conta do KeenFace. Crie uma chave da API no site (API keys) e cole aqui.'),
      el('div', { class: 'linha-chave' }, inp, el('button', { class: 'btn-primario peq', onclick: guardar }, 'Guardar')),
      el('div', { class: 'links-linha' }, link('Criar uma chave da API', 'chaves'), link('Preços', 'precos')),
      el('small', { class: 'mudo' }, 'A chave fica só neste computador.'),
      S.trocandoChave ? el('button', { class: 'btn-fantasma peq', onclick: () => { S.trocandoChave = false; desenharConfig(); } }, 'Manter a chave atual') : null);
  } else {
    const c = S.conta;
    conta.push(el('div', { class: 'conta-linha', html: icone('check', 14) + `<span>Chave <b class="mono">…${esc(S.chave.fim)}</b></span>` }));
    if (c) {
      const cabem = Math.floor((c.credits || 0) / preco());
      conta.push(el('div', { class: 'saldo' }, el('b', {}, fmtInt(c.credits)), el('span', {}, 'créditos'),
        el('small', {}, `${cabem ? `dá para ${cabem} cabeça${cabem > 1 ? 's' : ''}` : 'não dá para nenhuma cabeça'} (cada uma custa ${preco()})` +
          (c.held_credits ? ` · ${fmtInt(c.held_credits)} reservados para cabeças em andamento` : ''))));
    } else if (S.contaErro) {
      conta.push(nota(esc(S.contaErro.mensagem || 'Não deu para ler o saldo.'), 'erro'));
    } else conta.push(el('small', { class: 'mudo' }, 'Conferindo o saldo…'));
    conta.push(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', onclick: () => atualizarConta(), html: icone('recarregar', 12) + 'Atualizar' }),
      el('button', { class: 'btn peq', onclick: () => abrirLink('precos'), html: icone('externo', 12) + 'Comprar créditos' }),
      el('button', { class: 'btn-fantasma peq', onclick: () => { S.trocandoChave = true; desenharConfig(); setTimeout(() => $('#config input[type=password]')?.focus(), 30); } }, 'Trocar a chave')));
  }
  box.append(secao('conta', 'chip', 'Conta do KeenFace', conta));

  // cabeça nova
  const nome = el('input', { class: 'entrada', value: S.nome, placeholder: S.nomeSugerido || 'Nome do jogador', maxlength: '60', spellcheck: 'false', disabled: bloqueado });
  nome.addEventListener('input', () => { S.nome = nome.value; });
  const modo = op.modo === 'scan' ? 'scan' : 'padrao';
  const cab = [
    el('div', { class: 'campo' }, el('label', {}, 'Nome'), nome, el('div', { class: 'ajuda' }, 'Vira o nome da pasta e do arquivo (.glb). O MG Keen Converter usa o nome do arquivo na saída dele.')),
    el('div', { class: 'campo' }, el('label', {}, 'Tipo de fotos'),
      segmentado(Object.entries(MODOS).map(([v, [rot]]) => [v, rot]), modo, (v) => mudarOpcao('modo', v), bloqueado),
      el('div', { class: 'descricao-modo' }, MODOS[modo][1])),
  ];
  if (modo === 'scan') {
    cab.push(el('div', { class: 'campo' }, el('label', {}, 'Textura'),
      segmentado([['pbr', 'PBR', 'Luz das fotos removida, com mapas normal, rugosidade e especular (recomendado para o MG)'],
        ['raw', 'Crua', 'A cor das fotos como está, com a luz e possíveis buracos; só o mapa de cor']], op.textura === 'raw' ? 'raw' : 'pbr', (v) => mudarOpcao('textura', v), bloqueado)));
    if (op.textura !== 'raw') {
      cab.push(interruptor({ titulo: 'Limpeza da textura', descricao: 'Preenche buracos, tira o cabelo da pele e gera os olhos. Desligada, fica o que as fotos mostram.',
        marcado: op.limpeza !== false, desabilitado: bloqueado, aoMudar: (v) => mudarOpcao('limpeza', v) }).el);
    }
    const lente = el('input', { class: 'entrada', value: op.lente || '', placeholder: 'automática', disabled: bloqueado, inputmode: 'decimal', title: 'Distância focal equivalente a 35 mm; vazio = automática (usa o EXIF se todas as fotos tiverem)' });
    lente.addEventListener('change', () => mudarOpcao('lente', lente.value.trim()));
    cab.push(el('div', { class: 'campo' }, el('label', {}, 'Lente (mm, equivalente 35 mm)'), lente,
      el('div', { class: 'ajuda' }, 'Deixe vazio para o KeenFace descobrir. Se souber, um número vale para todas as fotos.')));
  }
  box.append(secao('cabeca', 'rosto', 'Cabeça nova', cab));

  // arquivos
  const arq = [
    el('div', { class: 'campo' }, el('label', {}, 'Pasta de saída'),
      el('div', { class: 'caminho-linha' }, el('input', { value: S.saida, readonly: true, title: S.saida, class: 'mono' }),
        el('button', { class: 'btn peq', onclick: escolherSaida, disabled: bloqueado }, 'Escolher…')),
      el('div', { class: 'ajuda' }, 'Cada cabeça ganha uma pasta com o nome dela.')),
    el('div', { class: 'campo' }, el('label', {}, 'Imagens das texturas'),
      segmentado([['jpg', 'JPG', 'Arquivo menor (recomendado)'], ['png', 'PNG', 'Sem perda, arquivo bem maior']], op.imagens === 'png' ? 'png' : 'jpg', (v) => mudarOpcao('imagens', v), bloqueado)),
    interruptor({ titulo: 'Baixar também o FBX MetaHuman', descricao: 'head.fbx com a pasta texture (o MG também aceita). O .glb, recomendado pelo MG, vem sempre. Os outros formatos podem ser baixados depois, sem custo.',
      marcado: !!op.metahuman, desabilitado: bloqueado, aoMudar: (v) => mudarOpcao('metahuman', v) }).el,
  ];
  box.append(secao('arquivos', 'pasta', 'Arquivos', arq));

  // privacidade
  const priv = [
    nota('As fotos são enviadas aos servidores da <b>KeenTools</b> (keenface.ai), que montam a cabeça. Elas ficam guardadas na sua conta até você apagar a cabeça (dá para apagar aqui, em Minhas cabeças).', 'info'),
    interruptor({ titulo: 'Posso usar estas fotos', descricao: 'Tenho direito de usar as fotos e a pessoa fotografada concordou (exigência dos termos do KeenFace).',
      marcado: !!op.aceite, desabilitado: bloqueado, aoMudar: (v) => mudarOpcao('aceite', v) }).el,
    el('div', { class: 'links-linha' }, link('Termos do KeenFace', 'termos'), link('Privacidade', 'privacidade')),
  ];
  box.append(secao('privacidade', 'olho', 'Privacidade e direitos', priv));

  // criar
  const req = requisitos();
  box.append(el('div', { class: 'criar-caixa' },
    el('ul', { class: 'requisitos' }, ...req.map(([ok, txt]) => el('li', { class: ok ? 'ok' : '', html: icone(ok ? 'check' : 'ponto', 13) + esc(txt) }))),
    el('button', { class: 'btn-primario grande', disabled: bloqueado || req.some(([ok]) => !ok), onclick: criar, html: icone('varinha', 15) + 'Criar cabeça' }),
    el('div', { class: 'custo-linha' }, `${preco()} créditos por cabeça (os arquivos não custam a mais). Se o KeenFace não conseguir montar a cabeça, não cobra nada.`)));
  box.scrollTop = rol;
}

function desenharConfigProprio(box, bloqueado) {
  const L = S.local || {}, prep = L.preparo || {};
  const linha = (ok, titulo, detalhe, botao) => el('div', { class: `prep-linha ${ok ? 'ok' : ''}` },
    el('span', { class: 'ic', html: icone(ok ? 'check' : 'ponto', 14) }),
    el('div', {}, el('b', {}, titulo), detalhe ? el('small', { html: detalhe }) : null), botao || el('span'));
  const comp = L.componentes || {}, ref = L.referencia || {}, jogo = L.jogo || {};
  const itens = [
    linha(comp.ok, 'Componentes', comp.ok ? 'MediaPipe, numpy, SciPy e OpenCV instalados' : `MediaPipe, numpy, SciPy e OpenCV: baixados uma vez (${mb(comp.download || 0)})`,
      comp.ok ? null : el('button', { class: 'btn-primario peq', onclick: baixarComponentes, disabled: bloqueado }, 'Baixar…')),
    linha(ref.ok, 'Face de referência do FC 27', ref.ok ? 'a mesma do Conversor de Faces' : 'vem no pacote completo do Super Tool',
      ref.ok ? null : el('button', { class: 'btn-primario peq', onclick: importarRef, disabled: bloqueado }, 'Importar…')),
  ];
  if (jogo.itens?.length) {
    for (const i of jogo.itens) {
      itens.push(linha(i.ok, i.nome, i.ok ? `<span title="${esc(i.caminho)}">${esc(encurtar(i.caminho, 2))}</span>` : esc(i.detalhe),
        i.ok || i.id === 'cache' ? null : el('button', { class: 'btn peq', onclick: () => escolherPastaJogo(i.id), disabled: bloqueado }, 'Escolher…')));
    }
  } else if (comp.ok) itens.push(linha(false, 'FIFA Editor Tool e FC 27', esc(jogo.erro || L.erro || 'conferindo…')));
  const m = L.modelo;
  const modeloOk = !!m && !L.modelo_velho && !(L.modelos_faltando || []).length;
  const pode = comp.ok && ref.ok && jogo.ok && !prep.ativa && !bloqueado;
  itens.push(linha(modeloOk, 'Modelo das cabeças do jogo',
    modeloOk ? `${fmtInt(m.cabecas)} cabeças do seu jogo · ${esc(dataCurta(m.feito))}` : L.modelo_velho ? 'o jogo mudou: prepare de novo'
      : m ? 'faltam os modelos que acham o rosto nas fotos (20 MB, baixados uma vez)' : 'montado uma vez a partir do jogo instalado (1 a 2 minutos) + 20 MB dos modelos que acham o rosto',
    modeloOk ? null : el('button', { class: 'btn-primario peq', disabled: !pode, onclick: prepararLocal }, 'Preparar')));
  if (prep.ativa) {
    const b = barra(prep.f || 0);
    b.id = 'prep-barra';
    itens.push(el('div', { class: 'prep-andamento' }, b, el('div', { class: 'linha-msg' }, el('span', { id: 'prep-msg' }, prep.msg || ''))));
  }
  if (prep.erro) itens.push(nota(esc(prep.erro), 'erro'));
  if (!L.pronto && !prep.ativa) itens.push(el('div', { class: 'ajuda' }, 'O modelo é feito com as cabeças do seu próprio FC 27 (lidas pelo cache do FIFA Editor Tool) e fica só neste computador.'));
  box.append(secao('preparo', 'chip', 'Preparação (uma vez)', itens));

  const nome = el('input', { class: 'entrada', value: S.nome, placeholder: S.nomeSugerido || 'Nome do jogador', maxlength: '60', spellcheck: 'false', disabled: bloqueado });
  nome.addEventListener('input', () => { S.nome = nome.value; });
  const jog = el('input', { class: 'entrada mono', value: S.jogador, placeholder: '0', maxlength: '9', inputmode: 'numeric', spellcheck: 'false', disabled: bloqueado });
  jog.addEventListener('input', () => { jog.value = jog.value.replace(/[^0-9]/g, ''); S.jogador = jog.value; });
  box.append(secao('cabeca', 'rosto', 'Face nova', [
    el('div', { class: 'campo' }, el('label', {}, 'Nome'), nome, el('div', { class: 'ajuda' }, 'Vira o nome da pasta da face.')),
    el('div', { class: 'campo' }, el('label', {}, 'ID do jogador no jogo'), jog,
      el('div', { class: 'ajuda', html: 'Entra no nome dos arquivos (<span class="mono">headmorphpreset_ID_0_0</span> e <span class="mono">face_ID_0_0_color</span>), como o FET espera. Vazio = 0.' })),
  ]));
  box.append(secao('arquivos', 'pasta', 'Arquivos', [
    el('div', { class: 'campo' }, el('label', {}, 'Pasta de saída'),
      el('div', { class: 'caminho-linha' }, el('input', { value: S.saidaLocal, readonly: true, title: S.saidaLocal, class: 'mono' }),
        el('button', { class: 'btn peq', onclick: async () => aplicar(await tentar(() => api('local_saida', {}))), disabled: bloqueado }, 'Escolher…')),
      el('div', { class: 'ajuda' }, 'Cada face ganha uma pasta com o FBX, a textura, a prévia 3D e as imagens de conferência.')),
  ]));
  const req = requisitos();
  box.append(el('div', { class: 'criar-caixa' },
    el('ul', { class: 'requisitos' }, ...req.map(([ok, txt]) => el('li', { class: ok ? 'ok' : '', html: icone(ok ? 'check' : 'ponto', 13) + esc(txt) }))),
    el('button', { class: 'btn-primario grande', disabled: bloqueado || req.some(([ok]) => !ok), onclick: criar, html: icone('varinha', 15) + 'Criar face' }),
    el('div', { class: 'custo-linha' }, 'Sem custo e sem enviar nada: leva de 1 a 2 minutos neste computador. A forma é uma aproximação pelas cabeças do jogo; a textura vem das suas fotos.')));
}

async function baixarComponentes() { await instalarComponentes({ aoTerminar: () => conferirLocal() }); conferirLocal(); }
async function importarRef() { await importarReferencias({ aoTerminar: () => conferirLocal() }); }
async function conferirLocal() { aplicar(await tentar(() => api('local_conferir', {}))); }
async function prepararLocal(refazer = false) { aplicar(await tentar(() => api('local_preparar', { refazer: refazer === true }))); }
async function escolherPastaJogo(qual) { aplicar(await tentar(() => api('local_pasta', { qual }))); }

function requisitos() {
  if (proprio()) {
    const n = S.fotos.length, L = S.local || {};
    const ruim = S.fotos.find((f) => !['image/jpeg', 'image/png', 'image/webp'].includes(f.tipo));
    return [
      [n >= 1 && n <= S.limiteLocal && !ruim, ruim ? `${ruim.nome}: use JPG, PNG ou WebP` : n > S.limiteLocal ? `No máximo ${S.limiteLocal} fotos (tire ${n - S.limiteLocal})` : n ? `${n} foto(s)` : `Fotos (de 1 a ${S.limiteLocal})`],
      [!!L.pronto, L.pronto ? 'Criador próprio preparado' : L.preparo?.ativa ? 'Preparando o criador próprio…' : 'Falta a preparação (acima)'],
    ];
  }
  const nf = S.fotos.length, scan = S.opcoes.modo === 'scan';
  const ruins = S.fotos.filter((f) => f.problema).length;
  return [
    [nf >= (scan ? 2 : 1) && !ruins, ruins ? `${ruins} foto(s) com problema` : nf ? `${nf} foto(s)` : `Fotos (${scan ? 'de 2' : 'de 1'} a 15)`],
    [!!S.chave.definida, S.chave.definida ? 'Chave da API do KeenFace' : 'Falta a chave da API do KeenFace'],
    [!!S.opcoes.aceite, S.opcoes.aceite ? 'Fotos liberadas para enviar' : 'Falta confirmar que pode usar as fotos'],
  ];
}

async function escolherSaida() { aplicar(await tentar(() => api('escolher_saida', {}))); }

// ---------------------------------------------------------------- criar, confirmar, cancelar
async function criar() {
  if (ativa()) return;
  const falta = requisitos().find(([ok]) => !ok);
  if (falta) { aviso(falta[1], { tipo: 'aviso' }); return; }
  const r = await tentar(() => (proprio() ? api('local_criar', { nome: S.nome.trim(), jogador: S.jogador.trim() }) : api('criar', { nome: S.nome.trim() })));
  if (!r) return;
  S.sel = null;
  mostrarPrevia(null);
  aplicar(r);
}

async function confirmarGasto() { aplicar(await tentar(() => api('confirmar', {}))); }
async function cancelar() { aplicar(await tentar(() => api('cancelar', {}))); }
async function fecharTarefa() { aplicar(await tentar(() => api('fechar_tarefa', {}))); }

function aoFicarPronta(avisar = true) {
  const res = S.tarefa.resultado || {};
  S.nome = '';
  S.sig.config = null;
  const feita = S.historico.find((h) => h.idem === res.idem);
  if (avisar && daqui(feita)) {
    aviso(`Face pronta: ${S.tarefa.nome}`, { tipo: 'sucesso', tempo: 8000, detalhe: 'Importe no FET o FBX e a textura que estão na pasta.',
      acao: { rotulo: 'Abrir a pasta', fn: () => tentar(() => api('abrir', { idem: res.idem })) } });
  } else if (avisar) {
    aviso(`Cabeça pronta: ${S.tarefa.nome}`, { tipo: 'sucesso', tempo: 8000, detalhe: 'O próximo passo é converter no MG Keen Converter.',
      acao: { rotulo: 'Mostrar o .glb', fn: () => tentar(() => api('abrir', { idem: res.idem, formato: 'glb' })) } });
  }
  // a cabeça pronta fica selecionada (cartão e prévia 3D); a tarefa volta a "parado"
  fecharTarefa().then(() => { if (res.idem) selecionar(res.idem); });
}

// ---------------------------------------------------------------- vista central: boas-vindas, tarefa e prévia 3D
function desenharVista() {
  const t = S.tarefa, x = itemSel();
  const temPrevia = !!(S.previaIdem && S.previa && !S.previa.vazia());
  $('#tela3d').style.visibility = temPrevia && !ativa() ? 'visible' : 'hidden';
  $('#barra3d').hidden = !temPrevia || ativa();
  $('#legenda3d').hidden = !temPrevia || ativa();
  const card = $('#cartao-tarefa');
  const ini = $('#inicio-vista');
  // só redesenha o cartão quando o conteúdo muda (redesenhar a cada consulta engoliria cliques nos botões)
  if (t.fase !== 'parado') {
    ini.hidden = true;
    card.hidden = false;
    const { decorrido, ...resto } = t;
    const res = S.historico.find((h) => h.idem === t.resultado?.idem) || null;
    if (mudou('cartao', ['t', resto, temPrevia, res, S.previaInfo, S.previaErro])) desenharCartaoTarefa(card, t, temPrevia);
    else { const tempo = card.querySelector('.tempo'); if (tempo) tempo.textContent = fmtTempo(decorrido || 0); }
    return;
  }
  if (x) {
    ini.hidden = true;
    card.hidden = false;
    if (mudou('cartao', ['x', x, temPrevia, S.previaInfo, S.previaErro])) desenharCartaoItem(card, x, temPrevia);
    return;
  }
  S.sig.cartao = null;
  card.hidden = true;
  ini.hidden = false;
  desenharInicio(ini);
}

function desenharInicio(box) {
  const nf = S.fotos.length, temChave = !!S.chave.definida;
  if (!mudou('inicio', [nf, temChave, S.mg, S.historico.length, S.motor, !!S.local?.pronto, !!S.local?.preparo?.ativa])) return;
  box.innerHTML = '';
  const passo = (n, feito, titulo, texto, botao) => el('div', { class: `passo ${feito ? 'feito' : ''}` },
    el('span', { class: 'n', html: feito ? icone('check', 15) : String(n) }), el('div', {}, el('b', {}, titulo), el('small', { html: texto })), botao || el('span'));
  if (proprio()) {
    const pronto = !!S.local?.pronto;
    box.append(el('div', { class: 'inicio-caixa' },
      el('h1', {}, 'Face do FC 27 a partir de fotos'),
      el('p', {}, 'O criador próprio roda no seu computador: acha o rosto nas fotos, ajusta a cabeça do jogo a ele e monta a textura careca com a pele das fotos. Sai o headmorphpreset (FBX) e a textura, prontos para o FET.'),
      el('div', { class: 'passos' },
        passo(1, pronto, 'Preparação (uma vez)', pronto ? 'Componentes e modelo das cabeças do jogo prontos.' : 'No painel da direita: baixar os componentes e montar o modelo com as cabeças do seu FC 27 (precisa do FIFA Editor Tool com o jogo aberto uma vez).'),
        passo(2, nf > 0, 'Fotos do jogador', nf ? `${nf} foto(s) na lista.` : 'Uma de frente e uma de cada lado (40° a 70°), nítidas e com a mesma luz. Arraste para a janela ou use Adicionar.',
          nf ? null : el('button', { class: 'btn peq', onclick: adicionarFotos }, 'Adicionar fotos…')),
        passo(3, false, 'Criar a face', 'Leva de 1 a 2 minutos e não custa nada. Ponha o ID do jogador para os arquivos já saírem com o nome que o FET espera.'),
        passo(4, false, 'Importar no FET', 'Na pasta do jogador: o <span class="mono">headmorphpreset</span> (FBX) e o <span class="mono">face_color</span> (PNG). O cabelo é o do jogo: a textura sai careca.')),
      el('div', { class: 'rodape-inicio', html: 'Quer a forma mais fiel? Troque para <b>KeenFace</b> em “Como criar” (serviço pago, na sua conta).' })));
    return;
  }
  box.append(el('div', { class: 'inicio-caixa' },
    el('h1', {}, 'Cabeça 3D a partir de fotos'),
    el('p', {}, 'O KeenFace (keenface.ai, da KeenTools) monta a cabeça do jogador a partir das fotos. Ela volta como .glb, pronta para o MG Keen Converter transformar na face do FC 27.'),
    el('div', { class: 'passos' },
      passo(1, nf > 0, 'Fotos do jogador', nf ? `${nf} foto(s) na lista.` : 'Arraste para a janela ou use Adicionar. Uma de frente e uma de cada lado já funcionam.',
        nf ? null : el('button', { class: 'btn peq', onclick: adicionarFotos }, 'Adicionar fotos…')),
      passo(2, temChave, 'Chave da API do KeenFace', temChave ? 'Guardada neste computador.' : 'Crie em keenface.ai (API keys) e cole no painel da direita. Conta nova ganha créditos grátis (confirmando o telefone).',
        temChave ? null : el('button', { class: 'btn peq', onclick: () => abrirLink('chaves'), html: icone('externo', 12) + 'Criar chave' })),
      passo(3, false, 'Criar a cabeça', `Custa ${preco()} créditos (uns € 15). A ferramenta mostra o custo e o saldo e só cria depois da sua confirmação. Leva alguns minutos.`),
      passo(4, false, 'Converter no MG Keen Converter', 'Abra o .glb no MG Keen Converter (de MGthefacemaker, baixado à parte no Ko-fi dele) e importe o resultado no FET.',
        el('button', { class: 'btn peq', onclick: () => abrirMG(null), html: icone('converter', 12) + 'Abrir o MG' }))),
    el('div', { class: 'rodape-inicio', html: S.historico.length ? 'Clique numa cabeça de <b>Minhas cabeças</b>, aqui embaixo, para ver em 3D e converter.' : 'As cabeças criadas ficam em <b>Minhas cabeças</b>, aqui embaixo, e continuam guardadas na sua conta do KeenFace.' })));
}

function etapas(fase) {
  const i = ETAPAS.findIndex(([f]) => f === fase);
  return el('div', { class: 'etapas' }, ...ETAPAS.map(([f, rot], k) => el('span', { class: k < i ? 'feita' : k === i ? 'atual' : '', html: (k < i ? icone('check', 11) : '') + esc(rot) })));
}

function barra(progresso) {
  const b = el('div', { class: `barra-progresso ${progresso == null ? 'indeterminado' : ''}` }, el('div'));
  if (progresso != null) b.firstChild.style.width = `${Math.round(Math.max(0.02, Math.min(1, progresso)) * 100)}%`;
  return b;
}

function desenharCartaoTarefa(card, t, temPrevia) {
  card.className = `cartao-tarefa ${t.fase === 'pronto' && temPrevia ? '' : 'centro'}`;
  card.innerHTML = '';
  if (t.fase === 'confirmar') {
    const o = t.orcamento || {};
    const depois = (o.saldo ?? 0) - (o.custo ?? 0);
    anexar(card, el('h3', { html: icone('varinha', 16) + 'Criar a cabeça de ' + esc(t.nome) + '?' }),
      el('div', { class: 'sub' }, `${o.fotos || S.fotos.length} foto(s) conferidas pelo KeenFace · ${o.modo === 'scan' ? 'Sessão de fotos (Scan)' : 'Fotos variadas'}`),
      el('div', { class: 'orcamento' },
        el('div', {}, el('b', {}, fmtInt(o.custo)), el('span', {}, 'créditos (uns € 15)')),
        el('div', {}, el('b', {}, fmtInt(o.saldo)), el('span', {}, 'saldo agora')),
        el('div', {}, el('b', {}, fmtInt(depois)), el('span', {}, 'saldo depois'))),
      nota('O KeenFace leva alguns minutos. Depois de criada, a cabeça não pode ser cancelada. Se ele não conseguir montar a cabeça, os créditos voltam.', 'info'),
      el('div', { class: 'acoes' },
        el('button', { class: 'btn', onclick: cancelar }, 'Cancelar'),
        el('button', { class: 'btn-primario', id: 'btn-confirmar', onclick: confirmarGasto }, `Criar por ${fmtInt(o.custo)} créditos`)));
    setTimeout(() => { if (!modalAberto() && !$('#config').contains(document.activeElement)) $('#btn-confirmar')?.focus(); }, 30);
    return;
  }
  if (t.fase === 'erro') {
    const e = t.erro || {};
    anexar(card, el('h3', { html: icone('aviso', 16) + esc(t.titulo || 'Não deu certo') }),
      el('div', { class: 'nota erro', style: { marginTop: '10px' }, html: icone('aviso', 15) + `<div>${esc(e.mensagem || 'Erro desconhecido')}</div>` }),
      (e.original && e.original !== e.mensagem) || e.request_id ? el('div', { class: 'sub', style: { marginTop: '8px' } },
        [e.original && `KeenFace: “${e.original}”`, e.request_id && `pedido ${e.request_id}`].filter(Boolean).join(' · ')) : null,
      el('div', { class: 'acoes' },
        e.link ? el('button', { class: 'btn esq', onclick: () => abrirLink(null, e.link), html: icone('externo', 13) + 'Abrir o site do KeenFace' }) : null,
        e.codigo === 'local' ? el('button', { class: 'btn esq', onclick: () => copiarTexto(e.mensagem || ''), html: icone('copiar', 13) + 'Copiar o erro' }) : null,
        el('button', { class: 'btn', onclick: fecharTarefa }, 'Fechar'),
        t.idem ? null : el('button', { class: 'btn-primario', onclick: async () => { await fecharTarefa(); criar(); } }, 'Tentar de novo')));
    return;
  }
  if (t.fase === 'cancelado') {
    card.append(el('h3', { html: icone('info', 16) + 'Cancelado' }), el('div', { class: 'sub' }, t.msg || 'Nada foi criado nem cobrado.'),
      el('div', { class: 'acoes' }, el('button', { class: 'btn-primario', onclick: fecharTarefa }, 'OK')));
    return;
  }
  if (t.fase === 'pronto') {
    const x = S.historico.find((h) => h.idem === t.resultado?.idem);
    if (x) { desenharCartaoItem(card, x, temPrevia, true); return; }
    card.append(el('h3', { html: icone('check', 16) + 'Cabeça pronta' }), el('div', { class: 'acoes' }, el('button', { class: 'btn-primario', onclick: fecharTarefa }, 'OK')));
    return;
  }
  // em andamento
  const espera = { na_fila: 'O KeenFace começa assim que chegar a vez.', processando: 'Costuma levar de 3 a 10 minutos. Pode continuar usando o Super Tool.',
    baixando: 'O arquivo vem direto do KeenFace para a pasta de saída.', criando: 'A partir daqui os créditos ficam reservados (só são cobrados se a cabeça sair).' };
  anexar(card, el('h3', { html: icone('recarregar', 16, 'girando') + esc(t.titulo || '…') }),
    el('div', { class: 'sub', title: t.pasta || '' }, `${t.nome}${t.pasta ? ' → ' + encurtar(t.pasta) : ''}`),
    barra(t.progresso),
    el('div', { class: 'linha-msg' }, el('span', {}, t.msg || espera[t.fase] || ''), el('span', { class: 'mudo tempo' }, fmtTempo(t.decorrido || 0))),
    t.fase === 'local' ? el('div', { class: 'sub', style: { marginTop: '8px' } }, 'Tudo acontece neste computador. A parte mais demorada é o ajuste da forma.') : etapas(t.fase),
    espera[t.fase] && t.msg ? el('div', { class: 'sub', style: { marginTop: '8px' } }, espera[t.fase]) : null,
    CANCELAVEIS.includes(t.fase) ? el('div', { class: 'acoes' }, el('button', { class: 'btn', onclick: cancelar }, 'Cancelar')) : null);
}

function desenharCartaoItem(card, x, temPrevia, daTarefa = false) {
  card.className = `cartao-tarefa ${temPrevia ? '' : 'centro'}`;
  card.innerHTML = '';
  const [rot, cor] = STATUS[x.status] || [x.status || '—', ''];
  const seg = seguindo(x) ? x.seguindo : null;
  const glb = x.arquivos?.glb;
  const fechar = el('button', { class: 'btn-icone peq', title: 'Fechar', style: { marginLeft: 'auto' }, html: icone('x', 14),
    onclick: () => { if (daTarefa) fecharTarefa(); selecionar(null); } });
  if (daqui(x)) {
    const rel = x.relatorio || {};
    anexar(card, el('h3', {}, el('span', { html: icone('check', 16) }), x.nome, el('span', { class: 'etiqueta verde' }, 'Pronta'), fechar),
      el('div', { class: 'sub', title: x.pasta || '' }, [dataCurta(x.criado), plural(x.fotos || 0, 'foto', 'fotos'), 'criador próprio', x.jogador && x.jogador !== '0' ? `ID ${x.jogador}` : '',
        rel.segundos ? `feita em ${fmtTempo(Math.round(rel.segundos))}` : '', x.pasta ? encurtar(x.pasta) : ''].filter(Boolean).join(' · ')));
    if (S.previaErro && S.previaIdem === x.idem) card.append(nota(`Não deu para mostrar a prévia (${esc(S.previaErro)}). Os arquivos estão na pasta.`, 'alerta'));
    card.append(el('div', { class: 'acoes' },
      el('button', { class: 'btn peq esq', disabled: !x.arquivos?.previa_fotos, onclick: () => tentar(() => api('abrir', { idem: x.idem, formato: 'previa_fotos', executar: true })), html: icone('imagem', 13) + 'Comparar com as fotos' }),
      el('button', { class: 'btn peq', disabled: !x.arquivos?.fbx, onclick: () => tentar(() => api('abrir', { idem: x.idem, formato: 'fbx' })), html: icone('arquivo', 13) + 'Mostrar o FBX' }),
      el('button', { class: 'btn-primario peq', onclick: () => tentar(() => api('abrir', { idem: x.idem })), html: icone('pasta', 13) + 'Abrir a pasta' }),
      el('button', { class: 'btn-icone', title: 'Mais opções', html: icone('lista', 16), onclick: (e) => { const r = e.currentTarget.getBoundingClientRect(); menuCabeca(x, r.left, r.top - 8, true); } })));
    card.append(el('div', { class: 'sub', style: { marginTop: '8px' }, html: 'No FET, na pasta do jogador: importe o <span class="mono">headmorphpreset</span> (FBX) e o <span class="mono">face_color</span> (PNG). A textura é careca: o cabelo é o do jogo.' }));
    return;
  }
  anexar(card, el('h3', {}, el('span', { html: icone(glb ? 'check' : 'rosto', 16) }), x.nome, el('span', { class: `etiqueta ${cor}` }, rot), fechar),
    el('div', { class: 'sub', title: x.pasta || '' }, [dataCurta(x.criado), x.fotos ? plural(x.fotos, 'foto', 'fotos') : '', x.modo === 'scan' ? 'Sessão de fotos' : 'Fotos variadas',
      S.previaInfo && temPrevia ? plural(S.previaInfo.vertices, 'vértice', 'vértices') : '', x.pasta ? encurtar(x.pasta) : ''].filter(Boolean).join(' · ')));
  if (seg) {
    anexar(card, barra(seg.progresso), el('div', { class: 'linha-msg' }, el('span', {}, seg.msg || 'Conferindo no KeenFace…')));
  } else if (x.seguindo?.fase === 'erro') {
    card.append(el('div', { class: 'nota erro', style: { marginTop: '10px' }, html: icone('aviso', 15) + `<div>${esc(x.seguindo.erro?.mensagem || 'Erro')}</div>` }));
  } else if (x.status === 'falhou' && x.erro) {
    card.append(el('div', { class: 'nota erro', style: { marginTop: '10px' }, html: icone('aviso', 15) + `<div>${esc(x.erro.mensagem)}</div>` }));
  } else if (x.status === 'nao_criada') {
    card.append(nota('O pedido desta cabeça não chegou ao KeenFace antes de a ferramenta fechar, então nada foi cobrado. Para ter esta cabeça, crie de novo.', 'alerta'));
  } else if (S.previaErro && S.previaIdem === x.idem) {
    card.append(nota(`Não deu para mostrar a prévia (${esc(S.previaErro)}). O arquivo não foi mexido e o MG Keen Converter lê normalmente.`, 'alerta'));
  }
  const acoes = el('div', { class: 'acoes' });
  if (glb) {
    acoes.append(el('button', { class: 'btn peq esq', onclick: () => tentar(() => api('abrir', { idem: x.idem, formato: 'glb' })), html: icone('arquivo', 13) + 'Mostrar o .glb' }),
      el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { idem: x.idem })), html: icone('pasta', 13) + 'Pasta' }),
      el('button', { class: 'btn-primario peq', onclick: () => abrirMG(x), html: icone('converter', 13) + 'Converter no MG Keen Converter' }));
  } else if (!seg && x.id && ['pronta', 'na_fila', 'processando'].includes(x.status)) {
    acoes.append(el('button', { class: 'btn-primario', onclick: () => baixar(x, 'glb'), html: icone('baixar', 13) + (x.status === 'pronta' ? 'Baixar o .glb' : 'Acompanhar e baixar') }));
  } else if (!seg && x.status === 'enviando') {
    acoes.append(el('button', { class: 'btn-primario', onclick: () => atualizarItem(x), html: icone('recarregar', 13) + 'Conferir no KeenFace' }));
  }
  acoes.append(el('button', { class: 'btn-icone', title: 'Mais opções', html: icone('lista', 16), onclick: (e) => { const r = e.currentTarget.getBoundingClientRect(); menuCabeca(x, r.left, r.top - 8, true); } }));
  card.append(acoes);
  if (glb && !seg) card.append(el('div', { class: 'sub', style: { marginTop: '8px' } }, 'No MG: OPEN HEADS, cole o caminho do .glb (vai copiado) e CONVERT ALL. Depois importe no FET o headmorphpreset e as texturas.'));
}

async function selecionar(idem) {
  S.sel = idem;
  mudou('historico', null);
  desenharHistorico();
  const x = itemSel();
  if (!x || !x.arquivos?.glb) { mostrarPrevia(null); desenharVista(); return; }
  if (S.previaIdem === idem && S.previa && !S.previa.vazia()) { desenharVista(); return; }
  await carregarPrevia(x);
}

async function carregarPrevia(x) {
  S.previaIdem = x.idem;
  S.previaErro = null;
  S.previaInfo = null;
  if (!S.previa) {
    try { S.previa = new PreviaGLB($('#tela3d')); } catch (e) { S.previaErro = 'sem WebGL'; desenharVista(); return; }
  }
  S.carregando = true;
  desenharVista();
  const fechar = aviso(`Abrindo a prévia de ${x.nome}…`, { tempo: 60000 });
  try {
    const r = await fetch(`modelo?idem=${encodeURIComponent(x.idem)}`);
    if (!r.ok) throw new Error('arquivo não encontrado');
    const buf = await r.arrayBuffer();
    if (S.previaIdem !== x.idem) return;
    S.previaInfo = await S.previa.mostrar(buf);
    $('#legenda3d').innerHTML = `<b>${esc(x.nome)}</b> · ${plural(S.previaInfo?.vertices || 0, 'vértice', 'vértices')} · ${plural(S.previaInfo?.partes || 0, 'parte', 'partes')}`;
  } catch (e) {
    S.previaErro = e.message;
    S.previa.limpar();
  } finally { S.carregando = false; fechar(); }
  desenharVista();
}

function mostrarPrevia(nada) {
  if (nada === null) {
    S.previaIdem = null;
    S.previaInfo = null;
    S.previaErro = null;
    if (S.previa) S.previa.limpar();
  }
}

function ferramentas3d() {
  const b = (id, ic, fn) => { const e = $(id); e.innerHTML = icone(ic, 16); e.onclick = fn; };
  b('#btn-textura', 'textura', () => alternar3d('textura'));
  b('#btn-arame', 'arame', () => alternar3d('arame'));
  b('#btn-girar', 'girar', () => alternar3d('girar'));
  b('#btn-enquadrar', 'centralizar', () => S.previa?.enquadrar());
  $('#btn-textura').classList.add('ativo');
}
function alternar3d(qual) {
  if (!S.previa) return;
  if (qual === 'textura') { S.previa.definirTextura(!S.previa.comTextura); $('#btn-textura').classList.toggle('ativo', S.previa.comTextura); }
  if (qual === 'arame') { S.previa.definirArame(!S.previa.arame); $('#btn-arame').classList.toggle('ativo', S.previa.arame); }
  if (qual === 'girar') { S.previa.definirGiro(!S.previa.girando); $('#btn-girar').classList.toggle('ativo', S.previa.girando); }
}

// ---------------------------------------------------------------- minhas cabeças
function desenharHistorico() {
  const l = $('#lista-cabecas');
  l.innerHTML = '';
  $('#cabecas-resumo').textContent = S.historico.length ? `${S.historico.length}` : '';
  if (!S.historico.length) {
    l.append(el('div', { class: 'vazio-cabecas' }, 'As faces e cabeças criadas aparecem aqui. Os arquivos vão para a pasta de saída; as do KeenFace continuam guardadas na sua conta (baixar de novo não custa nada).'));
    return;
  }
  for (const x of S.historico) {
    const seg = seguindo(x) ? x.seguindo : null;
    const [rot, cor] = STATUS[x.status] || [x.status || '—', ''];
    const etq = el('div', { class: 'etiquetas' });
    if (seg) etq.append(el('span', { class: 'etiqueta azul', title: seg.msg || '', html: icone('recarregar', 11, 'girando') + (seg.fase === 'baixando' ? 'Baixando' : 'Conferindo') }));
    else etq.append(el('span', { class: `etiqueta ${cor}`, title: x.erro?.mensagem || '' }, rot + (x.status === 'processando' && x.progresso != null ? ` ${x.progresso}%` : '')));
    for (const [k, r] of (daqui(x) ? [['fbx', 'FBX'], ['cor', 'textura']] : [['glb', 'GLB'], ['metahuman', 'MetaHuman'], ['obj', 'OBJ']])) if (x.arquivos?.[k]) etq.append(el('span', { class: 'etiqueta' }, r));
    if (x.seguindo?.fase === 'erro') etq.append(el('span', { class: 'etiqueta vermelha', title: x.seguindo.erro?.mensagem || '' }, 'erro'));
    const sub = [dataCurta(x.criado), x.fotos ? `${x.fotos} foto(s)` : '', daqui(x) ? 'criador próprio' : 'KeenFace', x.modo === 'scan' ? 'Scan' : '', x.de_fora ? 'feita em outro lugar' : ''].filter(Boolean).join(' · ');
    l.append(el('div', { class: `cabeca ${S.sel === x.idem ? 'sel' : ''}`, 'data-idem': x.idem, onclick: () => selecionar(x.idem),
      ondblclick: () => { if (daqui(x)) tentar(() => api('abrir', { idem: x.idem })); else if (x.arquivos?.glb) abrirMG(x); },
      oncontextmenu: (e) => { e.preventDefault(); menuCabeca(x, e.clientX, e.clientY); } },
    el('div', { class: 'ic-cab', html: icone('rosto', 18) }),
    el('div', { class: 'txt' }, el('b', {}, x.nome), el('small', { title: x.pasta || '' }, sub)),
    etq,
    el('button', { class: 'btn-icone peq', title: 'Mais opções', html: icone('lista', 14),
      onclick: (e) => { e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); menuCabeca(x, r.left - 180, r.bottom + 4); } })));
  }
}

function menuCabeca(x, px, py) {
  const glb = !!x.arquivos?.glb;
  const temId = !!x.id && !['apagada', 'falhou', 'nao_criada'].includes(x.status);
  const ocupada = seguindo(x) || (ativa() && S.tarefa.idem === x.idem);
  if (daqui(x)) {
    abrirMenu([
      { rotulo: 'Ver em 3D', icone: 'cubo', desabilitado: !glb, fn: () => selecionar(x.idem) },
      { rotulo: 'Comparar com as fotos', icone: 'imagem', desabilitado: !x.arquivos?.previa_fotos, fn: () => tentar(() => api('abrir', { idem: x.idem, formato: 'previa_fotos', executar: true })) },
      { rotulo: 'Ver a cabeça em três ângulos', icone: 'imagem', desabilitado: !x.arquivos?.previa_3d, fn: () => tentar(() => api('abrir', { idem: x.idem, formato: 'previa_3d', executar: true })) },
      '-',
      { rotulo: 'Mostrar o FBX', icone: 'arquivo', desabilitado: !x.arquivos?.fbx, fn: () => tentar(() => api('abrir', { idem: x.idem, formato: 'fbx' })) },
      { rotulo: 'Mostrar a textura', icone: 'textura', desabilitado: !x.arquivos?.cor, fn: () => tentar(() => api('abrir', { idem: x.idem, formato: 'cor' })) },
      { rotulo: 'Abrir a pasta', icone: 'pasta', desabilitado: !x.pasta_existe, fn: () => tentar(() => api('abrir', { idem: x.idem })) },
      '-',
      { rotulo: 'Tirar da lista', icone: 'x', desabilitado: ocupada, fn: () => esquecer(x) },
    ], px, py);
    return;
  }
  abrirMenu([
    { rotulo: 'Ver em 3D', icone: 'cubo', desabilitado: !glb, fn: () => selecionar(x.idem) },
    { rotulo: 'Converter no MG Keen Converter', icone: 'converter', desabilitado: !glb, fn: () => abrirMG(x) },
    { rotulo: 'Mostrar o .glb', icone: 'arquivo', desabilitado: !glb, fn: () => tentar(() => api('abrir', { idem: x.idem, formato: 'glb' })) },
    { rotulo: 'Abrir a pasta', icone: 'pasta', desabilitado: !x.pasta_existe, fn: () => tentar(() => api('abrir', { idem: x.idem })) },
    '-',
    { cabecalho: 'Baixar do KeenFace (sem custo)' },
    { rotulo: x.arquivos?.glb ? 'GLB (já baixado)' : 'GLB, para o MG Keen Converter', icone: 'baixar', desabilitado: !temId || ocupada || glb, fn: () => baixar(x, 'glb') },
    { rotulo: x.arquivos?.metahuman ? 'MetaHuman (já baixado)' : 'MetaHuman (head.fbx + texturas)', icone: 'baixar', desabilitado: !temId || ocupada || !!x.arquivos?.metahuman, fn: () => baixar(x, 'metahuman') },
    { rotulo: x.arquivos?.obj ? 'OBJ (já baixado)' : 'OBJ (neutral.obj + texturas)', icone: 'baixar', desabilitado: !temId || ocupada || !!x.arquivos?.obj, fn: () => baixar(x, 'obj') },
    '-',
    { rotulo: 'Conferir no KeenFace', icone: 'recarregar', desabilitado: ocupada || !(x.id || x.status === 'enviando') || ['apagada', 'falhou'].includes(x.status), fn: () => atualizarItem(x) },
    { rotulo: 'Renomear…', icone: 'pincel', desabilitado: ocupada || Object.keys(x.arquivos || {}).length > 0, fn: () => renomear(x) },
    { rotulo: 'Apagar no KeenFace…', icone: 'apagar', desabilitado: ocupada || !x.id || !['pronta', 'falhou'].includes(x.status), fn: () => apagarNoKeenFace(x) },
    { rotulo: 'Tirar da lista', icone: 'x', desabilitado: ocupada, fn: () => esquecer(x) },
  ], px, py);
}

async function baixar(x, formato) {
  const r = await tentar(() => api('baixar', { idem: x.idem, formato }));
  if (r) { aplicar(r); aviso(`Baixando ${formato === 'glb' ? 'o .glb' : formato === 'metahuman' ? 'o MetaHuman' : 'o OBJ'} de ${x.nome}`, { tempo: 2500 }); }
}
async function atualizarItem(x) { aplicar(await tentar(() => api('atualizar_item', { idem: x.idem }))); }
async function renomear(x) {
  const inp = el('input', { class: 'entrada', value: x.nome, maxlength: '60', autofocus: true, spellcheck: 'false' });
  const v = await modal({ titulo: 'Renomear a cabeça', corpo: el('div', { class: 'campo' }, el('label', {}, 'Nome (pasta e arquivo)'), inp),
    botoes: [{ rotulo: 'Cancelar', classe: 'btn', valor: null }, { rotulo: 'Renomear', classe: 'btn-primario', padrao: true, fn: () => inp.value.trim() || false }] }).promessa;
  if (v) aplicar(await tentar(() => api('renomear', { idem: x.idem, nome: v })));
}
async function apagarNoKeenFace(x) {
  const ok = await confirmar(`Apagar ${x.nome} no KeenFace?`, 'Apaga as fotos e os arquivos guardados na sua conta do KeenFace. <b>Não devolve créditos</b> e não dá para baixar de novo. Os arquivos já baixados neste computador ficam.',
    { rotulo: 'Apagar no KeenFace', perigo: true });
  if (!ok) return;
  const r = await tentar(() => api('apagar_no_keenface', { idem: x.idem }));
  if (r) { aplicar(r); if (!r.falha) aviso(`${x.nome} apagada no KeenFace`, { tipo: 'sucesso' }); }
}
async function esquecer(x) {
  const txt = daqui(x) ? 'Só sai desta lista: os arquivos continuam na pasta.' : 'Só sai desta lista: os arquivos baixados e a cabeça na conta do KeenFace ficam como estão. Atualizar a lista traz de volta as que estão no KeenFace.';
  if (!(await confirmar(`Tirar ${x.nome} da lista?`, txt, { rotulo: 'Tirar da lista' }))) return;
  if (S.sel === x.idem) { S.sel = null; mostrarPrevia(null); }
  aplicar(await tentar(() => api('esquecer', { idem: x.idem })));
}
async function sincronizar() {
  const b = $('#btn-sincronizar');
  b.disabled = true;
  const r = await tentar(() => api('sincronizar', {}));
  b.disabled = false;
  if (!r) return;
  aplicar(r);
  if (!r.falha) aviso(r.novas ? `${r.novas} cabeça(s) da sua conta entraram na lista` : 'Lista conferida com o KeenFace', { tipo: 'sucesso', tempo: 2500 });
  atualizarConta(true);
}

// ---------------------------------------------------------------- MG Keen Converter
async function abrirMG(x) {
  let r = await tentar(() => api('mg', { idem: x?.idem || '' }));
  if (!r) return;
  if (r.escolher) {
    const ok = await confirmar('Onde está o MG Keen Converter?', 'Não achei o <b>MG Keen Converter.exe</b> neste computador. Ele é de MGthefacemaker e é baixado à parte (só no Ko-fi dele): não vem com o Super Tool. Se já tem, mostre onde ele está.',
      { rotulo: 'Procurar o .exe…' });
    if (!ok) return;
    const e = await tentar(() => api('mg_escolher', {}));
    if (!e || !e.escolhido) return;
    aplicar(e);
    r = await tentar(() => api('mg', { idem: x?.idem || '' }));
    if (!r || r.escolher) return;
  }
  if (r.glb) {
    try { await navigator.clipboard.writeText(r.glb); } catch { /* sem permissão: segue */ }
    aviso('MG Keen Converter aberto', { tipo: 'sucesso', tempo: 9000, detalhe: 'Clique em OPEN HEADS e cole o caminho do .glb (já copiado), depois CONVERT ALL.',
      acao: { rotulo: 'Mostrar o .glb', fn: () => tentar(() => api('abrir', { idem: x.idem, formato: 'glb' })) } });
  } else aviso('MG Keen Converter aberto', { tipo: 'sucesso', tempo: 3000 });
}

// ---------------------------------------------------------------- topo e rodapé
function desenharTopo() {
  const chip = $('#chip-conta');
  if (S.chave.definida && S.conta && !proprio()) {
    chip.hidden = false;
    chip.className = `chip clicavel ${S.conta.credits >= preco() ? '' : 'aviso'}`;
    chip.innerHTML = icone('chip', 12) + `${fmtInt(S.conta.credits)} créditos`;
  } else chip.hidden = true;
  const b = $('#btn-criar');
  b.disabled = ativa();
  $('#btn-criar-txt').textContent = proprio() ? 'Criar face' : 'Criar cabeça';
  b.title = proprio() ? 'Criar a face neste computador (Ctrl+Enter)' : 'Enviar as fotos ao KeenFace e criar a cabeça (Ctrl+Enter)';
  const t = S.tarefa;
  $('#titulo').innerHTML = ativa() ? `<b>${esc(t.titulo || '')}</b>` : '';
}

function desenharStatus() {
  const nf = S.fotos.length;
  $('#status-esq').innerHTML = `<b>${nf}</b> foto(s) · <b>${S.historico.length}</b> na lista`;
  const c = $('#chip-chave');
  if (proprio()) {
    const L = S.local || {};
    c.className = `chip ${L.pronto ? 'ok' : 'aviso'}`;
    c.textContent = L.pronto ? 'Criador próprio pronto' : L.preparo?.ativa ? 'Preparando o criador próprio…' : 'Criador próprio: falta preparar';
  } else {
    c.className = `chip ${S.chave.definida ? (S.contaErro ? 'erro' : 'ok') : 'aviso'}`;
    c.textContent = S.chave.definida ? (S.contaErro ? 'KeenFace: erro na chave/conexão' : 'KeenFace conectado') : 'Sem chave do KeenFace';
  }
  const t = S.tarefa;
  const p = $('#status-progresso');
  if (ativa()) {
    p.hidden = false;
    $('#progresso-barra').style.width = t.progresso == null ? '100%' : `${Math.round(t.progresso * 100)}%`;
    $('#progresso-txt').textContent = t.titulo || '';
  } else p.hidden = true;
}

// ---------------------------------------------------------------- menus e teclado
function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { rotulo: 'Adicionar fotos…', icone: 'arquivoMais', atalho: 'Ctrl+O', fn: adicionarFotos },
      { rotulo: 'Tirar todas as fotos', icone: 'x', desabilitado: !S.fotos.length, fn: limparFotos },
      '-',
      { rotulo: 'Escolher a pasta de saída…', icone: 'pasta', desabilitado: ativa(), fn: () => (proprio() ? tentar(() => api('local_saida', {})).then(aplicar) : escolherSaida()) },
      '-',
      { rotulo: proprio() ? 'Criar face' : 'Criar cabeça', icone: 'varinha', atalho: 'Ctrl+Enter', desabilitado: ativa(), fn: criar },
    ]],
    ['Criador próprio', () => [
      { rotulo: 'Usar o criador próprio', icone: 'check', desabilitado: proprio() || ativa(), fn: () => mudarOpcao('motor', 'proprio') },
      '-',
      { rotulo: 'Baixar os componentes…', icone: 'baixar', desabilitado: !!S.local?.componentes?.ok, fn: baixarComponentes },
      { rotulo: 'Importar a face de referência…', icone: 'baixar', desabilitado: S.local?.referencia?.ok !== false, fn: importarRef },
      { rotulo: S.local?.modelo ? 'Refazer o modelo das cabeças do jogo' : 'Preparar o modelo das cabeças do jogo', icone: 'recarregar',
        desabilitado: ativa() || !!S.local?.preparo?.ativa || !S.local?.componentes?.ok || !S.local?.jogo?.ok, fn: () => prepararLocal(true) },
      { rotulo: 'Conferir de novo o jogo e o FET', icone: 'recarregar', fn: conferirLocal },
      '-',
      { rotulo: 'Escolher a pasta do FIFA Editor Tool…', icone: 'pasta', fn: () => escolherPastaJogo('fet') },
      { rotulo: 'Escolher a pasta do FC 27…', icone: 'pasta', fn: () => escolherPastaJogo('jogo') },
    ]],
    ['KeenFace', () => [
      { rotulo: 'Usar o KeenFace', icone: 'check', desabilitado: !proprio() || ativa(), fn: () => mudarOpcao('motor', 'keenface') },
      '-',
      { rotulo: 'Atualizar o saldo', icone: 'recarregar', desabilitado: !S.chave.definida, fn: () => atualizarConta() },
      { rotulo: 'Conferir Minhas cabeças', icone: 'lista', desabilitado: !S.chave.definida, fn: sincronizar },
      { rotulo: 'Trocar a chave da API…', icone: 'chip', fn: () => { S.trocandoChave = true; S.fechadas.delete('conta'); desenharConfig(); setTimeout(() => $('#config input[type=password]')?.focus(), 30); } },
      { rotulo: 'Esquecer a chave', icone: 'apagar', desabilitado: !S.chave.definida, fn: esquecerChave },
      '-',
      { rotulo: 'Criar uma chave da API (site)', icone: 'externo', fn: () => abrirLink('chaves') },
      { rotulo: 'Comprar créditos (site)', icone: 'externo', fn: () => abrirLink('precos') },
      { rotulo: 'Abrir o keenface.ai', icone: 'externo', fn: () => abrirLink('site') },
    ]],
    ['Converter', () => [
      { rotulo: 'Abrir o MG Keen Converter', icone: 'converter', fn: () => abrirMG(itemSel()?.arquivos?.glb ? itemSel() : null) },
      { rotulo: 'Escolher onde está o MG Keen Converter…', icone: 'pasta', fn: async () => { const e = await tentar(() => api('mg_escolher', {})); if (e?.escolhido) { aplicar(e); aviso('MG Keen Converter encontrado', { tipo: 'sucesso' }); } } },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Atalhos do teclado', icone: 'teclado', atalho: 'F1', fn: atalhos },
      { rotulo: 'Sobre o Criador de Faces', icone: 'info', fn: sobre },
    ]],
  ]);
}

async function esquecerChave() {
  if (!(await confirmar('Esquecer a chave da API?', 'A chave sai deste computador. A conta e as cabeças no KeenFace continuam como estão.', { rotulo: 'Esquecer', perigo: true }))) return;
  S.conta = null; S.contaErro = null;
  aplicar(await tentar(() => api('esquecer_chave', {})));
}

function atalhos() {
  const t = el('div', { class: 'tabela-atalhos' });
  for (const [g, itens] of [['Fotos e cabeças', [['Adicionar fotos', 'Ctrl+O'], ['Criar cabeça', 'Ctrl+Enter']]],
    ['Prévia 3D', [['Textura liga/desliga', 'T'], ['Malha (arame)', 'W'], ['Girar sozinha', 'G'], ['Enquadrar', 'F'], ['Girar a vista', 'arrastar'], ['Zoom', 'roda do mouse']]]]) {
    t.append(el('h4', {}, g));
    for (const [rot, k] of itens) t.append(el('div', {}, el('span', {}, rot), el('span', { html: `<kbd>${esc(k)}</kbd>` })));
  }
  modal({ titulo: 'Atalhos do teclado', corpo: t, largo: true, botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
}

function sobre() {
  dialogoSobre({ nome: 'Criador de Faces', versao: S.versao, html: `
    Cria a face de um jogador a partir de fotos, de dois jeitos.<br><br>
    <b>Criador próprio</b> — roda neste computador, sem custo e sem enviar as fotos: acha o rosto com o MediaPipe (Google, Apache 2.0),
    ajusta a cabeça do FC 27 às fotos com um modelo feito das cabeças do seu próprio jogo e grava o <i>headmorphpreset</i> (FBX) e a
    textura careca, prontos para o FET. Nada do jogo vem com a ferramenta: o modelo é montado aqui e fica só neste computador.<br><br>
    <b>KeenFace</b> — cabeça 3D pela API do KeenFace (keenface.ai, da KeenTools), com a chave e os créditos da sua conta. A cabeça volta
    como <i>.glb</i> (e, se quiser, o FBX MetaHuman ou o OBJ), pronta para o <b>MG Keen Converter</b> (de MGthefacemaker) transformar na
    face do FC 27.<br><br>
    <b>Custo:</b> ${preco()} créditos por cabeça; os arquivos e os downloads repetidos não custam nada, e cabeça que falha não é cobrada.
    Antes de criar, a ferramenta confere com o KeenFace o custo e o saldo e espera a sua confirmação.<br>
    <b>Privacidade:</b> as fotos vão para os servidores da KeenTools e ficam na sua conta até você apagar a cabeça. A chave fica só neste computador.<br>
    <b>Conversão:</b> o MG Keen Converter é baixado à parte (Ko-fi do autor) e não vem com o Super Tool; a ferramenta só abre o programa.<br><br>
    <b>2.0</b> — criador próprio (no computador, sem custo): olhos no padrão do jogo, textura careca, câmera com perspectiva.<br>
    <b>1.0</b> — KeenFace.` });
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  const digitando = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  const ctrl = e.ctrlKey || e.metaKey;
  const k = e.key.toLowerCase();
  if (ctrl && k === 'o') { e.preventDefault(); adicionarFotos(); return; }
  if (ctrl && e.key === 'Enter') { e.preventDefault(); if (S.tarefa.fase === 'confirmar') confirmarGasto(); else criar(); return; }
  if (e.key === 'F1') { e.preventDefault(); atalhos(); return; }
  if (digitando || ctrl) return;
  if (S.previaIdem && !ativa()) {
    if (k === 't') alternar3d('textura');
    else if (k === 'w') alternar3d('arame');
    else if (k === 'g') alternar3d('girar');
    else if (k === 'f') S.previa?.enquadrar();
  }
  if (e.key === 'Escape' && S.sel && !ativa()) selecionar(null);
});

// ---------------------------------------------------------------- início
async function iniciar() {
  $('#btn-add').innerHTML = icone('arquivoMais', 14);
  $('#btn-limpar').innerHTML = icone('apagar', 14);
  $('#btn-criar-ic').innerHTML = icone('varinha', 14);
  $('#btn-sincronizar').innerHTML = icone('recarregar', 12) + 'Atualizar';
  $('#btn-add').onclick = adicionarFotos;
  $('#btn-limpar').onclick = limparFotos;
  $('#btn-criar').onclick = criar;
  $('#btn-sincronizar').onclick = sincronizar;
  $('#chip-conta').onclick = () => atualizarConta();
  ferramentas3d();
  divisorArrastavel($('#div-esq'), '--esq', { min: 240, max: 520 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 290, max: 520, lado: 'dir' });
  prepararSoltar();
  menus();
  const r = await api('inicio');
  S.versao = r.versao;
  S.links = r.links || {};
  S.limiteKeen = r.limite_fotos || 15;
  S.limiteLocal = r.limite_fotos_local || 6;
  $('#versao').textContent = r.versao;
  S.ultimaFase = r.tarefa?.fase || null;
  aplicar(r);
  if (S.tarefa.fase === 'pronto') aoFicarPronta(false);
  if (S.chave.definida) atualizarConta(true);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) atualizar(); });
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
