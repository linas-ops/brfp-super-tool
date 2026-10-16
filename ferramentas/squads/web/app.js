// Atualizador de Squads — interface (BRFP Super Tool).
import { $, el, esc, aviso, barraMenus, divisorArrastavel, dialogoSobre, nota, modalAberto, menuAberto } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';

const S = { e: null, versao: '', polling: null };
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');
async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro' }); return undefined; } }

function aplicar(e) {
  if (!e) return;
  const antes = S.e;
  S.e = e;
  desenharArquivos();
  desenharTopo();
  desenharPrincipal();
  desenharStatus();
  if (e.rodando) acompanhar();
  if (antes && antes.rodando && !e.rodando) {
    if (e.erro) aviso(e.erro, { tipo: 'erro', tempo: 9000 });
    else if (e.relatorio && (!antes.relatorio || antes.relatorio.destino !== e.relatorio.destino || antes.relatorio.quando !== e.relatorio.quando)) {
      aviso('Squad atualizado gravado', { tipo: 'sucesso', tempo: 8000, detalhe: e.relatorio.destino,
        acao: { rotulo: 'Abrir pasta', fn: () => abrir(e.relatorio.destino, true) } });
    }
  }
}
async function atualizar() { aplicar(await tentar(() => api('estado'))); }

// ---------------------------------------------------------------- arquivos (painel esquerdo)
const ROTULOS = {
  ea: ['Squad da EA (mais recente)', 'Base do squad final: tudo que não vem do mod fica como a EA mandou.', 'azul'],
  mod: ['Squad do mod', 'De onde vêm os times brasileiros, os times novos e o que o mod criou.', 'laranja'],
  base: ['Squad em que o mod foi feito', 'Opcional. O squad da EA que o mod usou como ponto de partida: separa com certeza o que o mod criou do que a EA tirou depois.', ''],
};

function cartaoArquivo(qual) {
  const a = S.e[qual];
  const [titulo, dica, cor] = ROTULOS[qual];
  if (!a) {
    return el('div', { class: 'arq vazio-arq' }, el('div', { class: 'arq-cab' }, icone('arquivo', 14), el('b', {}, titulo), qual === 'base' ? el('span', { class: 'etiqueta' }, 'opcional') : null),
      el('div', { class: 'arq-det' }, dica),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', disabled: S.e.rodando, onclick: () => escolher(qual) }, icone('arquivoMais', 12), 'Escolher…')));
  }
  return el('div', { class: `arq ${a.erro ? 'erro-arq' : ''}` },
    el('div', { class: 'arq-cab' }, icone('arquivo', 14), el('b', {}, titulo), cor ? el('span', { class: `etiqueta ${cor}` }, qual === 'ea' ? 'EA' : 'mod') : el('span', { class: 'etiqueta' }, 'base')),
    el('div', { class: 'arq-nome', title: a.caminho }, a.nome || a.caminho),
    a.erro ? nota(esc(a.erro), 'erro') : el('div', { class: 'arq-det' }, `"${a.nome_jogo}" · ${a.quando} · ${(a.tamanho / 1048576).toFixed(1)} MB`),
    a.erro ? null : el('div', { class: 'arq-det' }, `${fmt(a.times)} times · ${fmt(a.jogadores)} jogadores`),
    el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', disabled: S.e.rodando, onclick: () => escolher(qual) }, icone('arquivoMais', 12), 'Trocar…'),
      qual === 'base' ? el('button', { class: 'btn-fantasma peq', disabled: S.e.rodando, onclick: () => limpar(qual) }, icone('x', 12), 'Tirar') : null,
      el('button', { class: 'btn-fantasma peq', onclick: () => abrir(a.caminho, true) }, icone('externo', 12), 'Pasta')));
}

function desenharArquivos() {
  const p = $('#propriedades');
  p.innerHTML = '';
  const e = S.e;
  p.append(el('div', { class: 'painel-cab' }, el('h2', {}, 'Squads')));
  const corpo = el('div', { style: { padding: '10px 12px' } }, cartaoArquivo('ea'), cartaoArquivo('mod'), cartaoArquivo('base'));
  const n = e.nomes || {};
  corpo.append(el('div', { class: 'arq' },
    el('div', { class: 'arq-cab' }, icone('idioma', 14), el('b', {}, 'Nomes dos jogadores')),
    n.caminho ? el('div', { class: 'arq-det' }, `Do banco do FC 27: ${n.fonte}`) : nota('Sem o banco do FC 27, os nomes dos jogadores da EA não são lidos e os duplicados só são achados pelo ID. Importe o banco do FC 27 em <b>Dados do jogo</b> ou escolha um aqui.', 'alerta'),
    n.caminho ? el('div', { class: 'arq-nome', title: n.caminho, style: { fontSize: '11px' } }, n.caminho) : null,
    el('div', { class: 'arq-det' }, 'Servem para achar o mesmo jogador com IDs diferentes (nome, nascimento e nacionalidade).'),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', disabled: e.rodando, onclick: () => tentar(async () => aplicar(await api('nomes', {}))) }, icone('bancoDados', 12), 'Outro banco…'),
      n.fonte === 'escolhido aqui' ? el('button', { class: 'btn-fantasma peq', onclick: () => limpar('nomes') }, icone('x', 12), 'Automático') : null)));
  if (e.ultimo) {
    corpo.append(el('div', { class: 'arq' }, el('div', { class: 'arq-cab' }, icone('salvar', 14), el('b', {}, 'Último squad gerado')),
      el('div', { class: 'arq-nome', title: e.ultimo }, e.ultimo),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: () => abrir(e.ultimo, true) }, icone('externo', 12), 'Abrir a pasta'))));
  }
  p.append(corpo);
}

async function escolher(qual) { aplicar(await tentar(() => api('escolher', { qual }))); }
async function limpar(qual) { aplicar(await tentar(() => api('limpar', { qual }))); }
async function abrir(caminho, pasta = false) { await tentar(() => api('abrir', { caminho, pasta })); }

// ---------------------------------------------------------------- conteúdo
function desenharPrincipal() {
  const p = $('#principal');
  const topo = $('#conteudo').scrollTop;
  p.innerHTML = '';
  const e = S.e;
  if (e.rodando) {
    p.append(el('div', { class: 'progresso-caixa' }, el('h2', {}, e.etapa || 'Trabalhando…'),
      el('div', { class: 'barra-progresso' }, el('div', { style: { width: `${Math.round((e.frac || 0) * 100)}%` } })),
      el('p', {}, 'Os squads têm dezenas de milhares de registros: leva alguns segundos.')));
    return;
  }
  if (e.erro) p.append(nota(esc(e.erro), 'erro'));
  if (!e.ea || !e.mod || e.ea.erro || e.mod.erro) { telaInicial(p); return; }
  if (!e.analise) {
    p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('recarregar', 56) }), el('h2', {}, 'Pronto para analisar'),
      el('p', {}, 'Lê os dois squads, acha os times brasileiros do mod, os times novos e os jogadores repetidos. Nada é gravado até você clicar em Gerar.'),
      el('div', { class: 'acoes' }, el('button', { class: 'btn-primario', onclick: analisar }, icone('busca', 14), 'Analisar os squads'))));
    return;
  }
  if (e.relatorio) p.append(...relatorio(e.relatorio));
  p.append(...analise(e.analise));
  $('#conteudo').scrollTop = topo;
}

function telaInicial(p) {
  p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('escudo', 64) }), el('h2', {}, 'Atualizar o squad do mod com o da EA'),
    el('p', {}, 'Quando a EA solta uma atualização de elencos, o squad do mod fica velho. Esta ferramenta pega o squad oficial mais recente da EA e coloca nele o que o mod acrescentou: os times brasileiros inteiros (com os jogadores do mod no lugar dos genéricos da EA), os times, ligas e competições que só existem no mod e os jogadores que o mod criou — sem jogadores duplicados.'),
    el('div', { class: 'acoes' },
      el('button', { class: 'btn', onclick: () => escolher('ea') }, icone('arquivoMais', 14), S.e.ea ? 'Trocar o squad da EA…' : 'Squad da EA…'),
      el('button', { class: 'btn', onclick: () => escolher('mod') }, icone('arquivoMais', 14), S.e.mod ? 'Trocar o squad do mod…' : 'Squad do mod…')),
    el('p', { class: 'mudo peq-txt' }, `Os squads do FC 27 ficam em ${S.e.pasta_fc27}. Para pegar o mais recente da EA, baixe a atualização de elencos no jogo e salve (Personalizar › Elencos) — o arquivo novo é o Squads<data> mais novo da pasta.`)));
}

function analise(a) {
  const br = new Set(S.e.br || []);
  const out = [];
  const naEa = a.brasileiros.filter((b) => b.na_ea);
  out.push(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta laranja' }, 'Análise'), el('h1', {}, 'O que vai mudar'),
    el('div', { class: 'sub' }, `EA: ${fmt(a.times_ea)} times, ${fmt(a.jogadores_ea)} jogadores · mod: ${fmt(a.times_mod)} times, ${fmt(a.jogadores_mod)} jogadores`))));
  out.push(el('div', { class: 'estatisticas', style: { margin: '12px 0' } },
    ...[[br.size, 'times brasileiros com os dados do mod'], [naEa.filter((b) => br.has(b.id)).length, 'deles já existem na EA (genéricos saem)'],
      [a.novos, 'times que só existem no mod'], [a.nomes_do_jogo ? fmt(a.nomes_do_jogo) : 'sem', 'nomes do banco do jogo']]
      .map(([v, k]) => el('div', { class: 'estatistica' }, el('b', {}, typeof v === 'number' ? fmt(v) : v), el('span', {}, k)))));
  if (!a.nomes_do_jogo) out.push(nota('Sem o banco do FC 27 os nomes dos jogadores da EA ficam vazios: o mesmo jogador com IDs diferentes não é encontrado. Escolha o banco no painel da esquerda.', 'alerta'));
  out.push(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Como a mescla funciona'))),
    el('div', { class: 'cartao-corpo' }, el('ul', { class: 'regras' },
      el('li', { html: '<b>Base:</b> o squad da EA. Tudo que não está abaixo fica como a EA mandou (times, jogadores e escalações de fora do Brasil).' }),
      el('li', { html: '<b>Times brasileiros</b> (marcados abaixo): vêm inteiros do mod — dados do time, liga, uniformes, estádio, técnico, formação, tática, escalação, rivais e o elenco. Os jogadores que a EA tinha neles saem (genéricos e reais).' }),
      el('li', { html: '<b>Times, ligas, competições, árbitros e patrocinadores que só existem no mod</b> entram como estão no mod.' }),
      el('li', { html: '<b>Jogadores duplicados:</b> o mesmo jogador nos dois squads (mesmo ID, ou nome + nascimento + nacionalidade) vira um só, com o ID da EA. Se ele está num time brasileiro no mod, ficam os dados do mod e ele sai do clube que tinha na EA; senão, ficam os dados da EA. Um ID que a EA passou a usar para outro jogador dá um ID novo ao do mod.' }),
      el('li', { html: '<b>Jogadores criados pelo mod</b> em times da EA entram; jogadores que a EA tirou depois que o mod foi feito não voltam.' }),
      el('li', { html: '<b>Escalações</b> dos times que perderam ou ganharam jogadores são refeitas (titulares pela posição, banco, capitão e cobradores).' })))));
  // times brasileiros
  const grupos = [['Já existem no squad da EA (substituídos pelo mod)', a.brasileiros.filter((b) => b.na_ea)], ['Só no mod (acrescentados)', a.brasileiros.filter((b) => !b.na_ea)]];
  const corpo = el('div', { class: 'cartao-corpo' });
  for (const [titulo, lista] of grupos) {
    if (!lista.length) continue;
    corpo.append(el('div', { class: 'grupo-times' }, `${titulo} · ${lista.length}`));
    corpo.append(el('div', { class: 'lista-times' }, ...lista.map((b) => {
      const cb = el('input', { type: 'checkbox' });
      cb.checked = br.has(b.id);
      cb.onchange = () => tentar(async () => aplicar(await api('times', { id: b.id, marcado: cb.checked })));
      return el('label', { title: `${b.nome} (${b.id})${b.na_ea ? ` — na EA: ${b.liga_ea}` : ''}` }, cb,
        el('span', { class: 't-txt' }, el('span', { class: 't-nome' }, b.nome), el('span', { class: 't-liga' }, b.na_ea ? `${b.liga_nome} · na EA: ${b.liga_ea || '?'}` : b.liga_nome)));
    })));
  }
  out.push(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Times brasileiros'),
    el('p', { class: 'dica' }, 'Times das ligas do Brasil no mod. Desmarque um time para ele ficar como a EA mandou (ou, se só existe no mod, para entrar só como time novo).')),
  el('div', { class: 'acoes-linha' },
    el('button', { class: 'btn-fantasma peq', onclick: () => tentar(async () => aplicar(await api('times', { todos: true }))) }, icone('check', 12), 'Todos'),
    el('button', { class: 'btn-fantasma peq', onclick: () => tentar(async () => aplicar(await api('times', { todos: false, so_na_ea: true }))) }, icone('x', 12), 'Nenhum dos da EA'))), corpo));
  if (a.novos_por_liga.length) {
    out.push(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Times que só existem no mod'), el('p', { class: 'dica' }, `${fmt(a.novos)} times entram como estão no mod (com elenco, uniformes e escalação).`))),
      el('div', { class: 'cartao-corpo justo' }, el('table', { class: 'tabela' }, el('tbody', {}, ...a.novos_por_liga.map(([liga, n]) => el('tr', {}, el('td', {}, liga), el('td', { class: 'num' }, fmt(n)))))))));
  }
  out.push(el('div', { class: 'acoes', style: { margin: '16px 0 30px', display: 'flex', gap: '8px' } },
    el('button', { class: 'btn-primario', disabled: S.e.rodando, onclick: gerar }, icone('salvar', 14), 'Gerar squad atualizado…')));
  return out;
}

function relatorio(r) {
  const out = [];
  out.push(el('div', { class: 'cartao', style: { borderColor: 'rgba(80, 200, 120, .45)' } },
    el('header', {}, el('div', {}, el('h3', {}, 'Squad atualizado gravado'), el('p', { class: 'dica mono' }, r.destino)),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', onclick: () => abrir(r.destino, true) }, icone('externo', 12), 'Abrir a pasta'),
        el('button', { class: 'btn peq', onclick: () => abrir(r.arquivo_relatorio) }, icone('relatorio', 12), 'Relatório completo'))),
    el('div', { class: 'cartao-corpo' },
      el('div', { class: 'estatisticas' }, ...[[r.times_brasileiros, 'times brasileiros do mod'], [r.times_novos, 'times novos'], [r.jogadores_importados, 'jogadores do mod acrescentados'],
        [r.jogadores_excluidos, 'jogadores da EA excluídos'], [r.duplicados.length, 'duplicados unidos'], [r.escalacoes.length, 'escalações refeitas'], [r.jogadores_finais, 'jogadores no squad']]
        .map(([v, k]) => el('div', { class: 'estatistica' }, el('b', {}, fmt(v)), el('span', {}, k)))),
      r.conferido && r.conferido.erro ? nota('O arquivo gravado não releu: ' + esc(r.conferido.erro), 'erro')
        : nota(`Arquivo relido e conferido: ${fmt(r.conferido?.times)} times, ${fmt(r.conferido?.jogadores)} jogadores, ${fmt(r.conferido?.vinculos)} vínculos. Para jogar, escolha esse elenco no jogo (Personalizar › Elencos › Carregar). Teste também no RDBM: Verificar squad.`, 'info'))));
  if (r.duplicados.length) {
    out.push(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Jogadores duplicados unidos'), el('p', { class: 'dica' }, 'O mesmo jogador com outro ID. Fica o ID da EA.'))),
      el('div', { class: 'cartao-corpo justo lista-curta' }, el('table', { class: 'tabela' },
        el('thead', {}, el('tr', {}, ...['Jogador', 'ID no mod', 'Fica', 'Dados'].map((h) => el('th', {}, h)))),
        el('tbody', {}, ...r.duplicados.map((d) => el('tr', {}, el('td', {}, d.nome), el('td', { class: 'mono' }, d.mod),
          el('td', { class: 'mono' }, d.tipo === 'ea' ? `${d.ea} (EA)` : `${d.fica} (mod)`),
          el('td', {}, d.tipo === 'ea' ? (d.dados === 'mod' ? 'do mod — sai do clube da EA' : 'da EA') : 'estava duas vezes no mod'))))))));
  }
  if (r.ids_trocados.length) {
    out.push(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'IDs trocados'), el('p', { class: 'dica' }, 'A EA passou a usar o ID para outro jogador: o do mod ganhou um ID livre.'))),
      el('div', { class: 'cartao-corpo justo lista-curta' }, el('table', { class: 'tabela' },
        el('thead', {}, el('tr', {}, ...['Jogador do mod', 'ID antigo', 'ID novo', 'Na EA o ID é'].map((h) => el('th', {}, h)))),
        el('tbody', {}, ...r.ids_trocados.map((d) => el('tr', {}, el('td', {}, d.nome), el('td', { class: 'mono' }, d.mod), el('td', { class: 'mono' }, d.novo), el('td', {}, d.nome_ea))))))));
  }
  if (r.escalacoes.length) {
    out.push(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Escalações refeitas'), el('p', { class: 'dica' }, 'Times da EA que perderam ou ganharam jogadores.'))),
      el('div', { class: 'cartao-corpo justo lista-curta' }, el('table', { class: 'tabela' },
        el('thead', {}, el('tr', {}, el('th', {}, 'Time'), el('th', { class: 'num' }, 'Jogadores'), el('th', { class: 'num' }, 'Entraram'), el('th', { class: 'num' }, 'Titulares trocados'))),
        el('tbody', {}, ...r.escalacoes.map((x) => el('tr', {}, el('td', {}, x.nome), el('td', { class: 'num' }, x.jogadores), el('td', { class: 'num' }, x.entraram), el('td', { class: 'num' }, x.titulares_trocados))))))));
  }
  const avisos = [...(r.avisos || []), ...(r.avisos_gravacao || [])];
  if (avisos.length) out.push(nota('<b>Avisos:</b><br>' + avisos.slice(0, 30).map(esc).join('<br>') + (avisos.length > 30 ? `<br>… e mais ${avisos.length - 30} (no relatório)` : ''), 'alerta'));
  return out;
}

// ---------------------------------------------------------------- topo, status e ações
function desenharTopo() {
  const e = S.e;
  const pronto = e.ea && e.mod && !e.ea.erro && !e.mod.erro;
  $('#btn-analisar').disabled = e.rodando || !pronto;
  $('#btn-gerar').disabled = e.rodando || !e.analise;
  $('#btn-gerar-txt').textContent = e.rodando ? (e.etapa || 'Trabalhando…') : 'Gerar squad atualizado';
  $('#btn-gerar-ic').innerHTML = icone(e.rodando ? 'recarregar' : 'salvar', 14, e.rodando ? 'girando' : '');
  $('#btn-analisar-ic').innerHTML = icone('busca', 14);
  $('#titulo').innerHTML = pronto ? `<b>${esc(e.mod.nome)} → ${esc(e.ea.nome)}</b><span class="pasta">mod + EA mais recente</span>` : '<b>Escolha os squads</b>';
}

function desenharStatus() {
  const e = S.e;
  const a = e.analise;
  $('#status-esq').innerHTML = a ? `<span><b>${fmt((e.br || []).length)}</b> times brasileiros</span><span><b>${fmt(a.novos)}</b> times novos</span><span><b>${fmt(a.jogadores_mod)}</b> jogadores no mod</span>` : '<span>Sem análise</span>';
  const sd = $('#status-dir');
  sd.innerHTML = '';
  sd.append(el('span', { class: `chip ${e.nomes && e.nomes.caminho ? 'ok' : 'aviso'}`, title: (e.nomes && e.nomes.caminho) || 'Sem o banco do FC 27' }, icone('idioma', 12), e.nomes && e.nomes.caminho ? `nomes: ${e.nomes.fonte}` : 'sem nomes do jogo'));
}

async function analisar() { aplicar(await tentar(() => api('analisar', {}))); }
async function gerar() {
  if (!S.e.analise || S.e.rodando) return;
  aplicar(await tentar(() => api('gerar', {})));
}

function acompanhar() {
  if (S.polling) return;
  S.polling = setInterval(async () => {
    const e = await api('estado').catch(() => null);
    if (!e) return;
    aplicar(e);
    if (!e.rodando) { clearInterval(S.polling); S.polling = null; }
  }, 400);
}

function menus() {
  barraMenus($('#menus'), [
    ['Arquivo', () => [
      { cabecalho: 'Squads' },
      { rotulo: 'Squad da EA (mais recente)…', icone: 'arquivoMais', fn: () => escolher('ea') },
      { rotulo: 'Squad do mod…', icone: 'arquivoMais', fn: () => escolher('mod') },
      { rotulo: 'Squad em que o mod foi feito (opcional)…', icone: 'arquivoMais', fn: () => escolher('base') },
      { rotulo: 'Banco do FC 27 para os nomes…', icone: 'bancoDados', fn: () => tentar(async () => aplicar(await api('nomes', {}))) },
      '-',
      { rotulo: 'Analisar', icone: 'busca', desabilitado: !S.e.ea || !S.e.mod || S.e.rodando, fn: analisar },
      { rotulo: 'Gerar squad atualizado…', icone: 'salvar', atalho: 'Ctrl+Enter', desabilitado: !S.e.analise || S.e.rodando, fn: gerar },
      '-',
      { rotulo: 'Abrir a pasta de squads do FC 27', icone: 'externo', fn: () => abrir(S.e.pasta_fc27, true) },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Sobre o Atualizador de Squads', icone: 'info', fn: () => dialogoSobre({ nome: 'Atualizador de Squads', versao: S.versao, html: `
        Coloca no squad oficial mais recente da EA o que o mod acrescentou. Os times brasileiros do mod substituem os da EA
        por inteiro (dados, uniformes, estádio, técnico, tática, escalação e elenco — os genéricos da EA saem); times, ligas,
        competições, árbitros e patrocinadores que só existem no mod entram; jogadores repetidos (mesmo ID, ou nome, nascimento
        e nacionalidade) viram um só; escalações que mudaram são refeitas.<br><br>
        O squad gravado é conferido relendo o arquivo (cabeçalho, CRC e todas as tabelas). Os squads de entrada nunca são alterados.<br><br>
        <b>1.0</b> — primeira versão (FC 27; o formato do squad é o mesmo do FC 26).` }) },
    ]],
  ]);
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); gerar(); }
});

async function iniciar() {
  $('#btn-analisar').onclick = analisar;
  $('#btn-gerar').onclick = gerar;
  divisorArrastavel($('#div-esq'), '--esq', { min: 260, max: 520 });
  const r = await api('inicio');
  S.versao = r.versao;
  $('#versao').textContent = r.versao;
  menus();
  aplicar(r);
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
