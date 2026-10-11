// Conversor PES → FC — interface completa do conversor de estádios (BRFP Super Tool): cria e edita as conversões num
// formulário, roda as etapas, mostra os passos no FET como lista de conferência e as prévias. Nenhum comando.
import { $, el, esc, aviso, modal, confirmar, barraMenus, divisorArrastavel, dialogoSobre, nota, interruptor, modalAberto, menuAberto, abrirMenu } from './comum/ui.js';
import { icone } from './comum/icones.js';
import { api } from './comum/api.js';
import { markdown } from './comum/markdown.js';

const S = { ini: null, configs: [], etapas: [], sel: null, exec: null, seq: 0, linhas: [], polling: null, aba: 'geral', ambiente: [],
  form: null, scanPes: null, scanFc: null, sujo: false };

async function tentar(fn) { try { return await fn(); } catch (e) { aviso(e.message, { tipo: 'erro', tempo: 8000 }); return undefined; } }
const cfgSel = () => S.configs.find((c) => c.arquivo === S.sel) || null;
const fmt = (n) => Number(n || 0).toLocaleString('pt-BR');
const opt = (v, t, sel) => { const o = el('option', { value: v }, t); o.selected = String(sel ?? '') === String(v ?? ''); return o; };
const seg = (valor, itens, fn) => el('div', { class: 'segmentado' }, ...itens.map(([v, t, d]) => el('button', { type: 'button', class: String(valor ?? '') === String(v ?? '') ? 'ativo' : '', title: d || '', onclick: () => fn(v) }, t)));

// o que cada etapa faz, em palavras simples (a ordem e os scripts vêm do converter.py)
const ETAPA = {
  inventario: ['Ler o estádio base', 'Lê o export do FET: peças, materiais, partes e quais texturas podem receber o estádio novo.'],
  extrair: ['Abrir o estádio do PES', 'Modelos (.fmdl), texturas (.ftex → DDS) e a área da torcida do mod.'],
  neutro: ['Tirar o que é de time', 'Compara com as variantes (outros clubes) e tira faixas, placas e texturas de time.'],
  importar: ['Levar para o Blender', 'Importa os modelos do PES no Blender.'],
  classificar: ['Organizar as peças', 'Separa arquibancadas, cobertura, fachada… e gira o estádio para os bancos baterem com os do FC.'],
  atlas: ['Montar o atlas de texturas', 'Junta todas as texturas numa imagem só, com sombreamento — a etapa mais demorada.'],
  plano: ['Escolher as malhas do FC', 'Escolhe as malhas que recebem o estádio e divide em pedaços que o FET aceita (até 60 mil vértices).'],
  mundo: ['Tirar o estádio base', 'Exclui ou esvazia as peças do estádio base que ficam dentro do estádio novo.'],
  fbx: ['Gerar os FBX', 'Os modelos para importar no FET.'],
  blueprints: ['Ajustar as caixas', 'Para o jogo não esconder o estádio conforme a câmera.'],
  mvdb: ['Materiais no jogo', 'Põe o atlas nas seções e desliga a textura doadora dos modelos originais (MeshVariationDb).'],
  teste_textura: ['Teste de textura (opcional)', 'Só roda se a configuração pedir: confirma de onde uma textura pode vir.'],
  torcida: ['Pôr a torcida', 'Assentos nos degraus do estádio novo e os caminhantes.'],
  proxy_torcida: ['Proxy de luz (teste)', 'Só roda se a configuração pedir.'],
  torcida_xml: ['Gravar a torcida', 'A nuvem de assentos e os grupos (casa, fora, organizadas).'],
  verificar: ['Conferir tudo', 'FBX, XML e texturas antes de você importar.'],
  previews: ['Prévias', 'Imagens do que vai para o FET.'],
  passos: ['Escrever os passos', 'O PASSOS_FET.md: o que importar e em que ordem.'],
};

// ---------------------------------------------------------------- lista de conversões
function desenharConfigs() {
  const l = $('#lista-configs');
  l.innerHTML = '';
  l.append(el('div', { class: 'nova-conv' }, el('button', { class: 'btn-primario', style: { width: '100%' }, onclick: assistente }, icone('mais', 14), 'Nova conversão')));
  if (!S.configs.length) {
    l.append(el('div', { class: 'arvore-vazia' }, 'Nenhuma conversão ainda. Clique em Nova conversão: o assistente acha o estádio do mod do PES e o mundo do export do FET para você.'));
    return;
  }
  for (const c of S.configs) {
    const et = el('div', { class: 'etiquetas' }, el('span', { class: 'etiqueta' }, c.modo === 'multi_mesh' ? 'várias malhas' : 'malha única'));
    if (c.entregue) et.append(el('span', { class: 'etiqueta verde', title: 'Entrega marcada em ' + c.entregue_quando }, 'entregue'));
    if (c.passos) et.append(el('span', { class: 'etiqueta azul', title: 'PASSOS_FET.md de ' + c.passos_quando }, 'passos prontos'));
    if (c.erro) et.append(el('span', { class: 'etiqueta vermelha' }, 'configuração com erro'));
    l.append(el('button', { class: `cfg ${S.sel === c.arquivo ? 'sel' : ''}`, onclick: () => selecionar(c.arquivo),
      oncontextmenu: (ev) => { ev.preventDefault(); menuConfig(c, ev.clientX, ev.clientY); } },
    el('b', {}, c.nome), el('small', {}, c.descricao || ''), el('small', {}, `${c.pes ? c.pes.split('/').pop() : '—'} → ${c.fc_estadio || '—'}`), et));
  }
  $('#rodape-esq').textContent = `${S.configs.length} conversão(ões)`;
}

function menuConfig(c, x, y) {
  abrirMenu([
    { cabecalho: c.nome },
    { rotulo: 'Duplicar…', icone: 'copias', fn: () => duplicar(c) },
    { rotulo: 'Mostrar o arquivo no Explorer', icone: 'pasta', fn: () => tentar(() => api('abrir', { caminho: c.arquivo })) },
    '-',
    { rotulo: 'Excluir (vai para a Lixeira)…', icone: 'apagar', fn: () => excluir(c) },
  ], x, y);
}

async function selecionar(arq) {
  if (S.sujo && !await confirmar('Descartar as mudanças?', 'A configuração tem mudanças que não foram gravadas.', { rotulo: 'Descartar', perigo: true })) return;
  S.sujo = false;
  S.sel = arq;
  S.form = null;
  desenharConfigs();
  desenharPrincipal();
  desenharPropriedades();
  desenharTopo();
}

// ---------------------------------------------------------------- área principal
function desenharPrincipal() {
  const p = $('#principal');
  p.innerHTML = '';
  const c = cfgSel();
  if (!S.ini.existe) {
    p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('aviso', 64) }), el('h2', {}, 'Motor do conversor não encontrado'),
      el('p', {}, `Esperado em ${S.ini.conversor}. A ferramenta usa o motor que fica na pasta de trabalho (conversor) ou dentro do pacote do Super Tool.`)));
    return;
  }
  if (!c) return telaBoasVindas(p);
  const abas = el('nav', { class: 'abas' });
  for (const [k, rot, ic] of [['geral', 'Visão geral', 'casa'], ['config', 'Configuração', 'engrenagem'], ['execucao', 'Converter', 'play'],
    ['passos', 'Importar no FET', 'relatorio'], ['ferramentas', 'Ferramentas', 'maleta']]) {
    abas.append(el('button', { class: `aba ${S.aba === k ? 'ativa' : ''}`, onclick: () => trocarAba(k) }, icone(ic, 14), rot,
      k === 'config' && S.sujo ? el('span', { class: 'n', style: { color: 'var(--aviso)' } }, '●') : null));
  }
  p.append(el('div', { class: 'cab-detalhe' }, el('div', {}, el('span', { class: 'etiqueta laranja' }, 'Conversão'), el('h1', {}, c.nome),
    el('div', { class: 'sub' }, c.descricao || `${c.pes || '—'} → ${c.fc_estadio || '—'}`))), abas);
  const corpo = el('div', { class: 'corpo-aba' });
  p.append(corpo);
  ({ geral: abaGeral, config: abaConfig, execucao: abaExecucao, passos: abaPassos, ferramentas: abaFerramentas }[S.aba] || abaGeral)(corpo, c);
}

async function trocarAba(k) {
  if (S.aba === 'config' && k !== 'config' && S.sujo && !await confirmar('Sair sem gravar?', 'A configuração tem mudanças que não foram gravadas.', { rotulo: 'Sair sem gravar', perigo: true })) return;
  if (S.aba === 'config' && k !== 'config') { S.sujo = false; S.form = null; }
  S.aba = k;
  desenharPrincipal();
}

function telaBoasVindas(p) {
  p.append(el('div', { class: 'tela-vazia' }, el('div', { class: 'ic-grande', html: icone('converter', 64) }), el('h2', {}, 'Converter um estádio do PES 2021 para o FC 26'),
    el('p', {}, 'O conversor pega o estádio de um mod do PES e põe dentro de um estádio do FC 26 exportado pelo FIFA Editor Tool: malhas, texturas (num atlas), a torcida nos degraus novos e o que precisa sair do estádio base. No fim ele diz exatamente o que importar no FET.'),
    el('div', { class: 'fluxo' }, ...[
      ['1', 'Exporte no FET', 'O estádio base do FC 26 inteiro (worlds\\stadiums e worlds\\components\\stadiums, com os MeshVariationDb).'],
      ['2', 'Crie a conversão', 'O assistente acha o estádio do mod do PES e o mundo do export.'],
      ['3', 'Converta', 'Um clique roda todas as etapas (Python e Blender).'],
      ['4', 'Importe no FET', 'Siga a lista de conferência; as prévias mostram o resultado.'],
      ['5', 'Teste e marque a entrega', 'A próxima rodada lista só o que mudou.'],
    ].map(([n, t, d]) => el('div', { class: 'passo-fluxo' }, el('span', { class: 'n' }, n), el('b', {}, t), el('small', {}, d)))),
    el('div', { class: 'acoes' }, el('button', { class: 'btn-primario', onclick: assistente }, icone('mais', 14), 'Nova conversão'))));
}

// ---------------------------------------------------------------- visão geral
async function abaGeral(p, c) {
  const ex = S.exec && S.exec.config === c.arquivo ? S.exec : null;
  const rodou = ex && !ex.rodando && ex.fim;
  let feitos = [], total = 0;
  if (c.passos) {
    const [r1, r2] = await Promise.all([api('passos?config=' + encodeURIComponent(c.arquivo)).catch(() => null), api('passos_feitos?config=' + encodeURIComponent(c.arquivo)).catch(() => null)]);
    total = r1 ? itensRodada(r1.texto).length : 0;
    feitos = r2?.itens || [];
  }
  if (S.sel !== c.arquivo || S.aba !== 'geral') return;
  const etapasOk = ex ? Object.values(ex.etapas || {}).filter((e) => e.estado === 'ok').length : 0;
  const cartao = (n, titulo, estado, tipo, texto, botoes) => el('div', { class: `passo-geral ${tipo}` },
    el('div', { class: 'n' }, tipo === 'ok' ? el('span', { html: icone('check', 16) }) : n),
    el('div', { class: 'txt' }, el('b', {}, titulo), el('span', { class: 'estado' }, estado), el('p', {}, texto)),
    el('div', { class: 'acoes-linha' }, ...botoes));
  p.append(el('div', { class: 'lista-geral' },
    cartao(1, 'Exportar o estádio base no FET', c.fc_export ? `export: ${c.fc_export}` : 'sem export', c.fc_export ? 'ok' : 'falta',
      'Exporte o estádio do FC 26 inteiro pelo FIFA Editor Tool, com os arquivos originais (worlds\\stadiums\\<mundo> e worlds\\components\\stadiums\\<componentes>, todos os MeshVariationDb_Win32). Um export do estádio já modificado vai para outra pasta.',
      []),
    cartao(2, 'Configurar', c.erro ? 'configuração com erro' : `${c.pes ? c.pes.split('/').pop() : '—'} → ${c.fc_estadio || '—'}`, c.erro ? 'falta' : 'ok',
      'Estádio do PES, estádio base do FC, modo das malhas, atlas e torcida — cada campo explicado no formulário.',
      [el('button', { class: 'btn peq', onclick: () => trocarAba('config') }, icone('engrenagem', 12), 'Abrir a configuração')]),
    cartao(3, 'Converter', ex?.rodando ? `rodando: ${ETAPA[ex.etapa]?.[0] || ex.etapa || '…'}` : rodou ? (ex.codigo === 0 ? `concluída em ${Math.round(ex.fim - ex.inicio)} s` : 'parou com erro') : c.passos ? `última saída: ${c.passos_quando}` : 'ainda não rodou',
      ex?.rodando ? 'rodando' : (rodou && ex.codigo !== 0) ? 'erro' : c.passos ? 'ok' : '',
      `As ${S.etapas.length} etapas rodam uma depois da outra (Python e Blender); dá para refazer a partir de qualquer uma.${ex ? ` Nesta sessão: ${etapasOk} etapa(s) concluída(s).` : ''}`,
      [el('button', { class: 'btn-primario peq', disabled: ex?.rodando || S.exec?.rodando, onclick: () => { trocarAba('execucao'); executar('tudo'); } }, icone('play', 12), c.passos ? 'Converter de novo' : 'Converter'),
        el('button', { class: 'btn peq', onclick: () => trocarAba('execucao') }, 'Ver as etapas')]),
    cartao(4, 'Importar no FET', c.passos ? `${feitos.length} de ${total} item(ns) desta rodada marcados` : 'depois de converter', !c.passos ? '' : total && feitos.length >= total ? 'ok' : 'rodando',
      'A lista diz o que importar (FBX, XML, DDS) e em que ordem; marque cada item conforme importa. As prévias mostram o que vai para o FET.',
      [el('button', { class: 'btn peq', disabled: !c.passos, onclick: () => trocarAba('passos') }, icone('relatorio', 12), 'Abrir a lista')]),
    cartao(5, 'Testar no jogo e marcar a entrega', c.entregue ? `entregue em ${c.entregue_quando}` : 'não marcada', c.entregue ? 'ok' : '',
      'Depois de importar e testar, marque a entrega: a próxima conversão lista só o que mudou desde ela (e traz XML originais para desfazer o que não funcionou).',
      [el('button', { class: 'btn peq', disabled: !c.existe_saida || S.exec?.rodando, onclick: marcarEntrega }, icone('check', 12), 'Marcar entrega')])));
}

// ---------------------------------------------------------------- configuração (formulário)
const CAMPOS = [
  ['Geral', 'arquivo', [
    { k: 'nome', t: 'texto', rot: 'Nome da conversão', ajuda: 'Vira as pastas work\\<nome> e saida\\<nome>. Mudar o nome começa do zero (as etapas rodam de novo).' },
    { k: 'descricao', t: 'texto', rot: 'Descrição', ajuda: 'Só para você reconhecer a conversão na lista.' }]],
  ['Estádio do PES', 'estadio', [
    { k: 'pes.mod', t: 'pasta', rot: 'Pasta do mod do PES', ajuda: 'A pasta que tem Asset\\model\\bg\\stNNN (e às vezes AddOn).', scan: 'pes' },
    { k: 'pes.estadio', t: 'estadioPes', rot: 'Estádio (id)', ajuda: 'O id do estádio no PES (st024 = Maracanã). Os achados na pasta do mod aparecem aqui.' },
    { k: 'pes.variantes', t: 'pastas', rot: 'Variantes (outros clubes)', ajuda: 'Outras versões do mesmo estádio (FLA, FLU, final…). O que muda entre elas é conteúdo de time e sai — o estádio fica neutro.' },
    { k: 'pes.excluir_modelos', t: 'lista', rot: 'Modelos a excluir', ajuda: 'Exclusões manuais extras (nomes de modelo do PES), um por linha.' },
    { k: 'pes.excluir_texturas', t: 'lista', rot: 'Texturas a excluir', ajuda: 'Um nome por linha.' }]],
  ['Estádio base do FC', 'estadio', [
    { k: 'fc.export', t: 'pasta', rot: 'Pasta do export do FET', ajuda: 'A pasta que contém worlds\\ (os arquivos originais do estádio base).', scan: 'fc' },
    { k: 'fc.estadio', t: 'mundo', rot: 'Mundo do estádio', ajuda: 'O mundo (worlds\\stadiums\\<mundo>) que recebe o estádio.' },
    { k: 'fc.componentes', t: 'componentes', rot: 'Componentes que o mundo usa', ajuda: 'A pasta de componentes que o mundo carrega (o Events 517 usa events_stadium). A mais citada pelo mundo vem primeiro.' },
    { k: 'fc.exports_extras', t: 'pastas', rot: 'Outros exports', ajuda: 'Pastas de export que espelham content/: os sistemas da torcida (content/common/…, iguais em todo estádio) e texturas exportadas à parte.' }]],
  ['Malhas e texturas', 'cubo', [
    { k: 'modo', t: 'seg', rot: 'Modo', ops: [['malha_unica', 'Malha única', 'O estádio inteiro em um mesh do FC'], ['multi_mesh', 'Várias malhas', 'Repartido entre vários meshes rígidos (foi o que funcionou no Events)']],
      ajuda: 'Várias malhas evita o estádio sumir conforme a câmera quando nenhum mesh do base cobre o estádio novo.' },
    { k: 'hospedeiro', t: 'hospedeiro', rot: 'Malha que recebe o estádio', ajuda: 'auto (recomendado) ou o nome do mesh do FC; vários separados por vírgula.' },
    { k: 'hospedeiro_excluir', t: 'lista', rot: 'Malhas que não podem receber', ajuda: 'Ex.: standsupper_railings_glass_mirror_mesh (o FET recusa o FBX).' },
    { k: 'hospedeiro_copias', t: 'bool', rot: 'Aceitar mesh repetido num grupo estático', ajuda: 'Fica uma cópia com o estádio e as outras são escondidas (padrão: sim).' },
    { k: 'doadoras', t: 'doadoras', rot: 'Texturas doadoras', ajuda: 'auto: texturas exclusivas do componente que o mundo carrega. Ou caminhos de texturas do FC, um por linha; com uma só, tudo vai num atlas (use 8192).' },
    { k: 'atlas.tamanho', t: 'seg', rot: 'Tamanho do atlas', ops: [[2048, '2048'], [4096, '4096'], [8192, '8192']], ajuda: '8192 fica mais nítido (e pesa mais).' },
    { k: 'atlas.ao', t: 'bool', rot: 'Sombreamento de ambiente no atlas', ajuda: 'Dá profundidade às texturas (padrão: sim).' }]],
  ['Posição', 'mover', [
    { k: 'giro', t: 'seg', rot: 'Giro', ops: [['auto', 'Automático', 'Alinha os bancos do PES com os do FC'], [0, '0°'], [180, '180°']], ajuda: 'Automático procura os bancos e gira para baterem.' },
    { k: 'offset_chao', t: 'numero', rot: 'Altura (m)', passo: 0.01, ajuda: 'O estádio desce um pouco para não brigar com o gramado do FC (padrão −0,05).' }]],
  ['Peças do estádio base', 'estadio', [
    { k: 'manter', t: 'lista', rot: 'Peças que ficam', ajuda: 'Nomes de blueprint: túnel, bancos, gramado, redes, placas… (também ficam fora da escolha da malha).' },
    { k: 'nunca_excluir', t: 'lista', rot: 'World parts que nunca saem', ajuda: 'As cadeiras da torcida dependem da arquibancada (lição do 193).' },
    { k: 'excluir_world_parts', t: 'lista', rot: 'World parts excluídos inteiros', ajuda: 'Ex.: banners (as faixas dinâmicas mostram estandartes de clube).' },
    { k: 'manter_camadas', t: 'lista', rot: 'Camadas do mundo que não são tocadas', ajuda: 'Apresentação e partida: bancos, túnel, gramado, placas, lateral.' }]],
  ['Torcida', 'torcida', [
    { k: 'torcida', t: 'presetTorcida', rot: 'Ajuste rápido', ajuda: 'A luz da torcida é pré-calculada pela EA para a área do estádio base: nada criado no FET faz luz nova.' },
    { k: 'torcida.max_assentos', t: 'assentos', rot: 'Assentos', ajuda: 'Vazio = todos os do PES; "base" = o número do estádio base; ou um número.' },
    { k: 'torcida.modo_gi', t: 'select', rot: 'Luz indireta (GlobalIlluminationMode)', ops: [['', 'A do estádio base'], ['DynamicProbes', 'DynamicProbes (recomendado)'], ['StaticProbes', 'StaticProbes (original da EA)'], ['DefaultProbe', 'DefaultProbe'], ['None', 'Nenhuma'], ['TerrainProjected', 'TerrainProjected']],
      ajuda: 'Vale para os sistemas da torcida, comuns a todos os estádios.' },
    { k: 'torcida.buffer_visibilidade', t: 'tri', rot: 'Buffer de visibilidade', ajuda: 'Ligado: torcedores pretos por assento fora da área do base. Desligado com DynamicProbes funcionou no 483.' },
    { k: 'torcida.so_com_luz', t: 'tri3', rot: 'Só os assentos com luz', ajuda: 'Automático: só os com luz, a não ser que você troque a luz indireta/buffer.' },
    { k: 'torcida.regiao_luz', t: 'seg', rot: 'Onde tem luz', ops: [['volumes', 'Dentro dos volumes'], ['caixa', 'Dentro da caixa dos volumes']], ajuda: 'Caixa: toda a área que envolve os volumes de luz (com DynamicProbes sem buffer).' },
    { k: 'torcida.margem_caixa', t: 'numero', rot: 'Margem da caixa (m)', passo: 0.5 },
    { k: 'torcida.caixa_luz_calculada', t: 'bool', rot: 'Aumentar a área de luz calculada', ajuda: 'Aumenta GridExtents/BakedShadowExtents do ambiente de luz (comum a todos os estádios) até cobrir os assentos novos.' },
    { k: 'torcida.cine', t: 'seg', rot: 'Prefabs Cine_ da arquibancada', ops: [['mover', 'Mover'], ['esconder', 'Esconder'], ['baixar', 'Baixar']], ajuda: 'Cadeiras coloridas e pessoas cinzas das cinemáticas: para o assento equivalente, 6 m abaixo dele, ou 150 m abaixo.' },
    { k: 'torcida.sombra_no_bake', t: 'bool', rot: 'Sombra no cálculo da luz', ajuda: 'Desligar tira CastShadow das malhas do LightmapGen (teste que fechou o jogo no Events — deixe ligado).' },
    { k: 'torcida.altura_visibilidade', t: 'numero', rot: 'Altura do ponto de visibilidade (m)', passo: 0.1, ajuda: 'VisibilityHeightOffset dos sistemas da torcida (vazio = o do base).' }]],
  ['Testes (avançado)', 'alvo', [
    { k: 'torcida.testes_luz', t: 'json', rot: 'Testes de luz da torcida', ajuda: 'Lista de {nome, modo_gi, buffer_visibilidade, altura_visibilidade, o_que_ver}: um par de XML por teste em saida\\<nome>\\teste_torcida, para importar um de cada vez.' },
    { k: 'teste_textura', t: 'json', rot: 'Teste de textura', ajuda: '{"<seção do hospedeiro>": "<caminho de uma textura do FC>"}: gera um MeshVariationDb de teste.' }]],
];

const pegar = (o, k) => k.split('.').reduce((a, x) => (a == null ? undefined : a[x]), o);
function pôr(o, k, v) {
  const ps = k.split('.');
  let a = o;
  for (const x of ps.slice(0, -1)) { if (a[x] == null || typeof a[x] !== 'object') a[x] = {}; a = a[x]; }
  if (v === undefined) delete a[ps[ps.length - 1]]; else a[ps[ps.length - 1]] = v;
}

async function abaConfig(p, c) {
  if (!S.form || S.form.arquivo !== c.arquivo) {
    p.append(el('div', { class: 'vazio' }, 'Carregando…'));
    const r = await tentar(() => api('config_ler?config=' + encodeURIComponent(c.arquivo)));
    if (!r || S.sel !== c.arquivo) return;
    S.form = { arquivo: r.arquivo, dados: r.dados, padroes: r.padroes };
    S.scanPes = null; S.scanFc = null;
    p.innerHTML = '';
  }
  desenharForm(p, S.form, async (dados) => {
    const r = await tentar(() => api('config_salvar', { arquivo: S.form.arquivo, dados }));
    if (!r) return;
    S.sujo = false;
    S.configs = r.configs;
    S.sel = r.arquivo;
    S.form = null;
    aviso('Configuração gravada', { tipo: 'sucesso', detalhe: r.avisos?.length ? r.avisos.join(' · ') : '' });
    desenharConfigs(); desenharPrincipal(); desenharPropriedades(); desenharTopo();
  });
}

// formulário de uma configuração (usado na aba e no fim do assistente)
function desenharForm(p, form, salvar) {
  const d = form.dados;
  const pad = form.padroes || {};
  const marcarSujo = () => { if (!S.sujo) { S.sujo = true; const b = $('#principal .aba.ativa'); if (b && !b.querySelector('.n')) b.append(el('span', { class: 'n', style: { color: 'var(--aviso)' } }, '●')); } btnSalvar.disabled = false; };
  const btnSalvar = el('button', { class: 'btn-primario peq', disabled: !S.sujo, onclick: () => salvar(JSON.parse(JSON.stringify(d))) }, icone('salvar', 12), 'Gravar');
  p.append(el('div', { class: 'barra-form' }, el('span', { class: 'mudo peq-txt' }, 'Campos vazios usam o padrão do conversor (mostrado em cinza).'), btnSalvar));
  const corpoSec = {};
  for (const [titulo, ic, campos] of CAMPOS) {
    const det = el('details', { class: 'secao-form', open: !titulo.startsWith('Testes') });
    det.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }));
    const g = el('div', { class: 'grade-form' });
    for (const f of campos) g.append(controle(f, d, pad, marcarSujo, () => redesenhar()));
    det.append(g);
    corpoSec[titulo] = g;
    p.append(det);
  }
  const avancado = el('details', { class: 'secao-form' }, el('summary', { html: icone('seta', 12, 'seta') + icone('terminal', 14) + 'Avançado: o JSON da configuração' }));
  const ta = el('textarea', { class: 'entrada mono json-cfg', spellcheck: 'false' });
  ta.value = JSON.stringify(d, null, 1);
  avancado.append(el('div', { class: 'secao-corpo' }, nota('O mesmo que o formulário, como o conversor lê. Edite aqui só se precisar de algo que o formulário não tem.', 'info'), ta,
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => {
      try { const novo = JSON.parse(ta.value); for (const k of Object.keys(d)) delete d[k]; Object.assign(d, novo); marcarSujo(); redesenhar(); aviso('JSON aplicado ao formulário', { tipo: 'sucesso', tempo: 1800 }); }
      catch (e) { aviso('JSON inválido: ' + e.message, { tipo: 'erro' }); }
    } }, 'Aplicar no formulário'))));
  p.append(avancado);
  function redesenhar() {
    for (const [titulo, , campos] of CAMPOS) {
      const g = corpoSec[titulo];
      g.innerHTML = '';
      for (const f of campos) g.append(controle(f, d, pad, marcarSujo, redesenhar));
    }
    ta.value = JSON.stringify(d, null, 1);
  }
  // escaneia as pastas para preencher as listas (estádios do PES, mundos e componentes do FC)
  if (d.pes?.mod && !S.scanPes) api('escanear_pes?mod=' + encodeURIComponent(d.pes.mod)).then((r) => { S.scanPes = r; redesenhar(); }).catch(() => { S.scanPes = { erro: true }; });
  if (d.fc?.export && !S.scanFc) api('escanear_fc?export=' + encodeURIComponent(d.fc.export)).then((r) => { S.scanFc = r; redesenhar(); }).catch(() => { S.scanFc = { erro: true }; });
}

function controle(f, d, pad, sujo, redesenhar) {
  const v = pegar(d, f.k);
  const vp = pegar(pad, f.k);
  const mudar = (nv) => { pôr(d, f.k, nv); sujo(); };
  const ph = vp === undefined || vp === null ? '' : (Array.isArray(vp) ? vp.join(', ') : String(vp));
  let ctl;
  const lista = (arr) => (Array.isArray(arr) ? arr.join('\n') : arr && arr !== 'auto' ? String(arr) : '');
  const deLista = (txt) => txt.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  switch (f.t) {
    case 'texto':
      ctl = el('input', { type: 'text', class: 'entrada', value: v ?? '', placeholder: ph, spellcheck: 'false', oninput: (e) => mudar(e.target.value.trim() || undefined) });
      break;
    case 'numero':
      ctl = el('input', { type: 'number', class: 'entrada', step: f.passo || 1, value: v ?? '', placeholder: ph, style: { width: '140px' }, oninput: (e) => mudar(e.target.value === '' ? undefined : Number(e.target.value)) });
      break;
    case 'pasta': {
      const inp = el('input', { type: 'text', class: 'entrada mono', value: v ?? '', spellcheck: 'false', placeholder: 'escolha a pasta…', onchange: (e) => { mudar(e.target.value.trim() || undefined); escanear(); } });
      const escanear = () => {
        if (f.scan === 'pes') { S.scanPes = null; if (pegar(d, f.k)) api('escanear_pes?mod=' + encodeURIComponent(pegar(d, f.k))).then((r) => { S.scanPes = r; redesenhar(); }).catch((e) => { S.scanPes = { erro: e.message }; redesenhar(); }); }
        if (f.scan === 'fc') { S.scanFc = null; if (pegar(d, f.k)) api('escanear_fc?export=' + encodeURIComponent(pegar(d, f.k))).then((r) => { S.scanFc = r; redesenhar(); }).catch((e) => { S.scanFc = { erro: e.message }; redesenhar(); }); }
      };
      ctl = el('div', { class: 'caminho-linha' }, inp, el('button', { type: 'button', class: 'btn', title: 'Escolher…', onclick: async () => {
        const r = await tentar(() => api('dialogo', { modo: 'pasta', titulo: f.rot, inicial: pegar(d, f.k) }));
        if (r && !r.cancelado) { inp.value = r.caminho; mudar(r.caminho); escanear(); }
      } }, icone('pasta', 14)));
      break;
    }
    case 'pastas': {
      const ta = el('textarea', { class: 'entrada mono', rows: Math.max(2, (v || []).length + 1), spellcheck: 'false', placeholder: 'uma pasta por linha', oninput: (e) => mudar(deLista(e.target.value).length ? deLista(e.target.value) : undefined) });
      ta.value = lista(v);
      const sug = f.k === 'pes.variantes' && S.scanPes?.variantes ? (S.scanPes.variantes[pegar(d, 'pes.estadio')] || []).filter((x) => !(v || []).includes(x)) : [];
      ctl = el('div', { class: 'col-gap' }, ta, el('div', { class: 'acoes-linha' },
        el('button', { type: 'button', class: 'btn peq', onclick: async () => {
          const r = await tentar(() => api('dialogo', { modo: 'pasta', titulo: f.rot }));
          if (r && !r.cancelado) { mudar([...(pegar(d, f.k) || []), r.caminho]); redesenhar(); }
        } }, icone('pastaMais', 12), 'Acrescentar pasta…'),
        sug.length ? el('button', { type: 'button', class: 'btn-fantasma peq', title: sug.join('\n'), onclick: () => { mudar([...(pegar(d, f.k) || []), ...sug]); redesenhar(); } }, icone('mais', 12), `Usar as ${sug.length} achada(s) ao lado do mod`) : null));
      break;
    }
    case 'lista':
      ctl = el('textarea', { class: 'entrada mono', rows: Math.min(8, Math.max(2, (Array.isArray(v) ? v.length : 0) + 1)), spellcheck: 'false', placeholder: ph ? `padrão: ${ph}` : 'um por linha', oninput: (e) => mudar(deLista(e.target.value).length ? deLista(e.target.value) : undefined) });
      ctl.value = lista(v);
      break;
    case 'seg':
      ctl = seg(v ?? vp ?? '', f.ops, (nv) => { mudar(nv); redesenhar(); });
      break;
    case 'select':
      ctl = el('select', { class: 'seletor', onchange: (e) => mudar(e.target.value || undefined) }, ...f.ops.map(([ov, ot]) => opt(ov, ot, v ?? '')));
      break;
    case 'bool':
      ctl = interruptor({ titulo: v === undefined ? `${vp !== false ? 'Sim' : 'Não'} (padrão)` : v ? 'Sim' : 'Não', marcado: v ?? (vp !== false), aoMudar: (nv) => { mudar(nv); redesenhar(); } }).el;
      break;
    case 'tri':
      ctl = seg(v === undefined || v === null ? '' : String(v), [['', 'O do base'], ['true', 'Ligado'], ['false', 'Desligado']], (nv) => { mudar(nv === '' ? undefined : nv === 'true'); redesenhar(); });
      break;
    case 'tri3':
      ctl = seg(v === undefined || v === 'auto' ? 'auto' : String(v), [['auto', 'Automático'], ['true', 'Sim'], ['false', 'Não']], (nv) => { mudar(nv === 'auto' ? undefined : nv === 'true'); redesenhar(); });
      break;
    case 'assentos':
      ctl = el('input', { type: 'text', class: 'entrada', value: v ?? '', placeholder: 'todos', style: { width: '160px' }, oninput: (e) => { const x = e.target.value.trim(); mudar(x === '' ? undefined : x === 'base' ? 'base' : Number.isFinite(+x) ? +x : x); } });
      break;
    case 'hospedeiro':
      ctl = el('input', { type: 'text', class: 'entrada mono', value: Array.isArray(v) ? v.join(', ') : v ?? '', placeholder: 'auto', spellcheck: 'false', oninput: (e) => {
        const xs = e.target.value.split(',').map((x) => x.trim()).filter(Boolean);
        mudar(!xs.length ? undefined : xs.length === 1 ? xs[0] : xs);
      } });
      break;
    case 'doadoras':
      ctl = el('textarea', { class: 'entrada mono', rows: 2, spellcheck: 'false', placeholder: 'auto (vazio) — ou caminhos de textura do FC, um por linha', oninput: (e) => { const xs = deLista(e.target.value); mudar(!xs.length || (xs.length === 1 && xs[0] === 'auto') ? undefined : xs); } });
      ctl.value = lista(v);
      break;
    case 'json': {
      ctl = el('textarea', { class: 'entrada mono', rows: 5, spellcheck: 'false', placeholder: 'vazio = não usar' });
      ctl.value = v === undefined ? '' : JSON.stringify(v, null, 1);
      ctl.onchange = () => { if (!ctl.value.trim()) { mudar(undefined); return; } try { mudar(JSON.parse(ctl.value)); ctl.classList.remove('erro'); } catch { ctl.classList.add('erro'); aviso('JSON inválido neste campo', { tipo: 'erro' }); } };
      break;
    }
    case 'estadioPes': {
      const ids = S.scanPes?.estadios || [];
      if (ids.length) ctl = el('select', { class: 'seletor', onchange: (e) => { mudar(e.target.value); redesenhar(); } }, ...(v && !ids.some((x) => x.id === v) ? [opt(v, v, v)] : []),
        ...ids.map((x) => opt(x.id, `${x.id} · ${x.fpk} arquivo(s) de modelo${x.audi ? ' · com torcida' : ''}`, v)));
      else ctl = el('input', { type: 'text', class: 'entrada mono', value: v ?? '', placeholder: S.scanPes?.erro ? 'não achei estádios na pasta' : 'st024', style: { width: '160px' }, oninput: (e) => mudar(e.target.value.trim() || undefined) });
      break;
    }
    case 'mundo': {
      const ms = S.scanFc?.mundos || [];
      if (ms.length) ctl = el('select', { class: 'seletor', onchange: (e) => {
        mudar(e.target.value);
        const m = ms.find((x) => x.nome === e.target.value);
        if (m?.componentes?.length) pôr(d, 'fc.componentes', m.componentes[0][0]);
        redesenhar();
      } }, ...(v && !ms.some((x) => x.nome === v) ? [opt(v, v, v)] : []), ...ms.map((x) => opt(x.nome, `${x.nome}${x.mvdb ? ` · ${x.mvdb} MeshVariationDb` : ''}`, v)));
      else ctl = el('input', { type: 'text', class: 'entrada mono', value: v ?? '', placeholder: S.scanFc?.erro ? 'não achei worlds\\stadiums' : 'events_stadium_517', oninput: (e) => mudar(e.target.value.trim() || undefined) });
      break;
    }
    case 'componentes': {
      const cs = S.scanFc?.componentes || [];
      const usados = (S.scanFc?.mundos || []).find((x) => x.nome === pegar(d, 'fc.estadio'))?.componentes || [];
      const ordem = [...usados.map(([n]) => n), ...cs.filter((x) => !usados.some(([n]) => n === x))];
      if (ordem.length) ctl = el('select', { class: 'seletor', onchange: (e) => mudar(e.target.value) }, ...(v && !ordem.includes(v) ? [opt(v, v, v)] : []),
        ...ordem.map((n) => { const u = usados.find(([x]) => x === n); return opt(n, `${n}${u ? ` · citado ${fmt(u[1])}× pelo mundo` : ''}`, v); }));
      else ctl = el('input', { type: 'text', class: 'entrada mono', value: v ?? '', placeholder: 'events_stadium', oninput: (e) => mudar(e.target.value.trim() || undefined) });
      break;
    }
    case 'presetTorcida':
      ctl = el('div', { class: 'acoes-linha' },
        el('button', { type: 'button', class: 'btn peq', title: 'DynamicProbes sem o buffer de visibilidade, só os assentos dentro da caixa de luz: o que funcionou no 483', onclick: () => {
          Object.assign(d.torcida = d.torcida || {}, { modo_gi: 'DynamicProbes', buffer_visibilidade: false, so_com_luz: true, regiao_luz: 'caixa' }); sujo(); redesenhar();
        } }, 'Recomendado'),
        el('button', { type: 'button', class: 'btn peq', title: 'Toda a torcida do PES, com a área de luz aumentada (o que a conversão do Events usa)', onclick: () => {
          Object.assign(d.torcida = d.torcida || {}, { modo_gi: 'DynamicProbes', buffer_visibilidade: false, so_com_luz: false, caixa_luz_calculada: true }); sujo(); redesenhar();
        } }, 'Torcida cheia'),
        el('button', { type: 'button', class: 'btn-fantasma peq', title: 'A luz da torcida como o estádio base (sem trocar nada)', onclick: () => {
          for (const k of ['modo_gi', 'buffer_visibilidade', 'so_com_luz', 'regiao_luz', 'caixa_luz_calculada']) delete (d.torcida || {})[k]; sujo(); redesenhar();
        } }, 'Como o base'));
      break;
    default:
      ctl = el('span', {}, '—');
  }
  const atual = v === undefined && ph && !['pasta', 'pastas', 'presetTorcida', 'bool', 'seg', 'json'].includes(f.t) ? el('span', { class: 'padrao' }, `padrão: ${ph.length > 70 ? ph.slice(0, 70) + '…' : ph}`) : null;
  return el('div', { class: `campo-form t-${f.t}` }, el('label', {}, f.rot), ctl, f.ajuda ? el('div', { class: 'ajuda' }, f.ajuda) : null, atual);
}

// ---------------------------------------------------------------- assistente (nova conversão)
async function assistente(base = null) {
  const d = base ? JSON.parse(JSON.stringify(base)) : { nome: '', descricao: '', pes: { mod: '', estadio: '', variantes: [] }, fc: { export: '', estadio: '', componentes: '', exports_extras: [] },
    modo: 'multi_mesh', atlas: { tamanho: 8192 }, torcida: { modo_gi: 'DynamicProbes', buffer_visibilidade: false, so_com_luz: true, regiao_luz: 'caixa' } };
  let passo = 0;
  let scanP = null, scanF = null;
  const corpo = el('div', { class: 'assistente' });
  const m = modal({ titulo: base ? 'Duplicar conversão' : 'Nova conversão', largo: true, corpo });
  const passos = ['Estádio do PES', 'Estádio base do FC', 'Opções', 'Nome'];
  const desenhar = () => {
    corpo.innerHTML = '';
    corpo.append(el('div', { class: 'passos-ass' }, ...passos.map((t, i) => el('span', { class: i === passo ? 'atual' : i < passo ? 'feito' : '' }, `${i + 1}. ${t}`))));
    const area = el('div', { class: 'area-ass' });
    corpo.append(area);
    const nav = el('div', { class: 'nav-ass' });
    corpo.append(nav);
    if (passo === 0) {
      area.append(el('p', {}, 'Escolha a pasta do mod do PES 2021 que tem o estádio (a que contém a pasta Asset). O assistente procura os estádios dentro dela e as variantes (outros clubes) nas pastas ao lado.'));
      area.append(campoPasta('Pasta do mod do PES', d.pes.mod, async (c) => { d.pes.mod = c; scanP = await tentar(() => api('escanear_pes?mod=' + encodeURIComponent(c))); if (scanP) { d.pes.estadio = scanP.estadios[0]?.id || ''; d.pes.variantes = scanP.variantes[d.pes.estadio] || []; if (!d.nome) d.nome = (scanP.nome || '').replace(/\W+/g, '_').toLowerCase(); } desenhar(); }));
      if (scanP?.estadios?.length) {
        area.append(el('div', { class: 'campo' }, el('label', {}, 'Estádio'), el('div', { class: 'opcoes-ass' }, ...scanP.estadios.map((e) => el('button', { type: 'button', class: `op-ass ${d.pes.estadio === e.id ? 'sel' : ''}`, onclick: () => { d.pes.estadio = e.id; d.pes.variantes = scanP.variantes[e.id] || []; desenhar(); } },
          el('b', {}, e.id), el('small', {}, `${e.fpk} arquivo(s) de modelo${e.audi ? ' · com torcida' : ''}`))))));
        const vs = scanP.variantes[d.pes.estadio] || [];
        if (vs.length) {
          area.append(el('div', { class: 'campo' }, el('label', {}, 'Variantes (outros clubes): o que muda entre elas sai, e o estádio fica neutro'),
            ...vs.map((x) => { const ch = el('input', { type: 'checkbox' }); ch.checked = d.pes.variantes.includes(x); ch.onchange = () => { d.pes.variantes = ch.checked ? [...d.pes.variantes, x] : d.pes.variantes.filter((y) => y !== x); }; return el('label', { class: 'linha-check' }, ch, ' ', x); })));
        } else area.append(nota('Sem variantes ao lado do mod: as texturas de time são achadas pelos nomes.', 'info'));
      }
      nav.append(el('button', { class: 'btn', onclick: () => m.fechar(null) }, 'Cancelar'), el('button', { class: 'btn-primario', disabled: !d.pes.mod || !d.pes.estadio, onclick: () => { passo = 1; desenhar(); } }, 'Próximo'));
    } else if (passo === 1) {
      area.append(el('p', {}, 'Escolha a pasta do export do FET do estádio base do FC 26 (a que contém worlds\\). Exporte os arquivos originais: worlds\\stadiums\\<mundo>, worlds\\components\\stadiums\\<componentes> com todos os MeshVariationDb_Win32 e o volume base em worlds\\lightingisenviros.'));
      area.append(campoPasta('Pasta do export do FET', d.fc.export, async (c) => { d.fc.export = c; scanF = await tentar(() => api('escanear_fc?export=' + encodeURIComponent(c))); if (scanF) { d.fc.export = scanF.export; const m0 = scanF.mundos[0]; d.fc.estadio = m0?.nome || ''; d.fc.componentes = m0?.componentes?.[0]?.[0] || scanF.componentes[0] || ''; } desenhar(); }));
      if (scanF?.mundos?.length) {
        area.append(el('div', { class: 'campo' }, el('label', {}, 'Mundo do estádio'), el('div', { class: 'opcoes-ass' }, ...scanF.mundos.map((x) => el('button', { type: 'button', class: `op-ass ${d.fc.estadio === x.nome ? 'sel' : ''}`, onclick: () => { d.fc.estadio = x.nome; d.fc.componentes = x.componentes?.[0]?.[0] || d.fc.componentes; desenhar(); } },
          el('b', {}, x.nome), el('small', {}, `${x.mvdb} MeshVariationDb · usa ${x.componentes?.[0]?.[0] || '?'}`))))));
        const usados = scanF.mundos.find((x) => x.nome === d.fc.estadio)?.componentes || [];
        const ordem = [...usados.map(([n]) => n), ...scanF.componentes.filter((x) => !usados.some(([n]) => n === x))];
        area.append(el('div', { class: 'campo' }, el('label', {}, 'Componentes que o mundo usa (o mais citado vem primeiro)'),
          el('select', { class: 'seletor', onchange: (e) => { d.fc.componentes = e.target.value; } }, ...ordem.map((n) => opt(n, n, d.fc.componentes)))));
        if (!scanF.tem_luz) area.append(nota('Não achei o volume de luz (worlds\\lightingisenviros) neste export: exporte junto se for usar o ajuste da luz da torcida.', 'alerta'));
      }
      area.append(el('div', { class: 'campo' }, el('label', {}, 'Outros exports (opcional): os sistemas da torcida (content\\common) vêm de um export completo, como o do Pro Stadium Tier1'),
        el('textarea', { class: 'entrada mono', rows: 2, placeholder: 'uma pasta por linha', oninput: (e) => { d.fc.exports_extras = e.target.value.split(/\r?\n/).map((x) => x.trim()).filter(Boolean); } }, (d.fc.exports_extras || []).join('\n')),
        el('div', { class: 'acoes-linha' }, el('button', { type: 'button', class: 'btn peq', onclick: async () => { const r = await tentar(() => api('dialogo', { modo: 'pasta', titulo: 'Outro export do FET' })); if (r && !r.cancelado) { d.fc.exports_extras = [...(d.fc.exports_extras || []), r.caminho]; desenhar(); } } }, icone('pastaMais', 12), 'Acrescentar…'))));
      nav.append(el('button', { class: 'btn', onclick: () => { passo = 0; desenhar(); } }, 'Voltar'), el('button', { class: 'btn-primario', disabled: !d.fc.export || !d.fc.estadio || !d.fc.componentes, onclick: () => { passo = 2; desenhar(); } }, 'Próximo'));
    } else if (passo === 2) {
      area.append(el('div', { class: 'campo' }, el('label', {}, 'Como o estádio entra no FC'), seg(d.modo, [['multi_mesh', 'Várias malhas (recomendado)'], ['malha_unica', 'Malha única']], (v) => { d.modo = v; desenhar(); }),
        el('div', { class: 'mudo peq-txt' }, d.modo === 'multi_mesh' ? 'O estádio é repartido entre meshes rígidos do base: o jogo não o esconde conforme a câmera (o que aconteceu com malha única no Events).' : 'O estádio inteiro num mesh do FC: só serve se algum mesh do base já cobrir o estádio novo.')));
      area.append(el('div', { class: 'campo' }, el('label', {}, 'Atlas de texturas'), seg(d.atlas.tamanho, [[4096, '4096'], [8192, '8192 (mais nítido)']], (v) => { d.atlas.tamanho = v; desenhar(); })));
      const t = d.torcida;
      const preset = t.so_com_luz === false && t.caixa_luz_calculada ? 'cheia' : t.modo_gi === 'DynamicProbes' ? 'rec' : 'base';
      area.append(el('div', { class: 'campo' }, el('label', {}, 'Torcida'), seg(preset, [['rec', 'Recomendado'], ['cheia', 'Torcida cheia'], ['base', 'Como o estádio base']], (v) => {
        d.torcida = v === 'rec' ? { modo_gi: 'DynamicProbes', buffer_visibilidade: false, so_com_luz: true, regiao_luz: 'caixa' }
          : v === 'cheia' ? { modo_gi: 'DynamicProbes', buffer_visibilidade: false, so_com_luz: false, caixa_luz_calculada: true } : {};
        desenhar();
      }), el('div', { class: 'mudo peq-txt' }, { rec: 'Só os assentos dentro da área de luz do estádio base, com DynamicProbes e sem o buffer de visibilidade — o que funcionou no 483.', cheia: 'Todos os assentos do PES, com a área de luz aumentada até eles (alguns podem ficar escuros).', base: 'A luz da torcida como o estádio base, sem trocar nada.' }[preset])));
      area.append(nota('Todo o resto (peças que ficam, doadoras, giro, testes) começa no padrão e pode ser mudado depois na aba Configuração.', 'info'));
      nav.append(el('button', { class: 'btn', onclick: () => { passo = 1; desenhar(); } }, 'Voltar'), el('button', { class: 'btn-primario', onclick: () => { passo = 3; desenhar(); } }, 'Próximo'));
    } else {
      const nome = el('input', { type: 'text', class: 'entrada', value: d.nome, placeholder: 'maracana_events', autofocus: true, oninput: (e) => { d.nome = e.target.value; } });
      const desc = el('input', { type: 'text', class: 'entrada', value: d.descricao || '', placeholder: 'Maracanã do PES no Events 517', oninput: (e) => { d.descricao = e.target.value; } });
      area.append(el('div', { class: 'campo' }, el('label', {}, 'Nome (pastas work\\<nome> e saida\\<nome>)'), nome), el('div', { class: 'campo' }, el('label', {}, 'Descrição'), desc),
        el('dl', { class: 'kv' }, el('dt', {}, 'PES'), el('dd', {}, `${d.pes.mod} · ${d.pes.estadio}${d.pes.variantes?.length ? ` · ${d.pes.variantes.length} variante(s)` : ''}`),
          el('dt', {}, 'FC'), el('dd', {}, `${d.fc.export} · ${d.fc.estadio} (${d.fc.componentes})`),
          el('dt', {}, 'Modo'), el('dd', {}, `${d.modo === 'multi_mesh' ? 'várias malhas' : 'malha única'} · atlas ${d.atlas.tamanho}`)));
      nav.append(el('button', { class: 'btn', onclick: () => { passo = 2; desenhar(); } }, 'Voltar'), el('button', { class: 'btn-primario', onclick: async () => {
        if (!d.descricao) delete d.descricao;
        const r = await tentar(() => api('config_salvar', { dados: d }));
        if (!r) return;
        m.fechar(true);
        S.configs = r.configs;
        S.sel = r.arquivo; S.form = null; S.aba = 'geral';
        desenharConfigs(); desenharPrincipal(); desenharPropriedades(); desenharTopo();
        aviso('Conversão criada', { tipo: 'sucesso', detalhe: (r.avisos || []).join(' · ') || 'Confira a configuração e clique Converter.' });
      } }, icone('check', 14), 'Criar'));
    }
  };
  desenhar();
}

function campoPasta(rot, valor, aoEscolher) {
  const inp = el('input', { type: 'text', class: 'entrada mono', value: valor || '', spellcheck: 'false', placeholder: 'escolha a pasta…', onchange: (e) => { if (e.target.value.trim()) aoEscolher(e.target.value.trim()); } });
  return el('div', { class: 'campo' }, el('label', {}, rot), el('div', { class: 'caminho-linha' }, inp, el('button', { type: 'button', class: 'btn', onclick: async () => {
    const r = await tentar(() => api('dialogo', { modo: 'pasta', titulo: rot, inicial: inp.value || undefined }));
    if (r && !r.cancelado) { inp.value = r.caminho; aoEscolher(r.caminho); }
  } }, icone('pasta', 14), 'Escolher…')));
}

async function duplicar(c) {
  const r = await tentar(() => api('config_ler?config=' + encodeURIComponent(c.arquivo)));
  if (!r) return;
  const d = r.dados;
  d.nome = `${d.nome}_copia`;
  assistente(d);
}

async function excluir(c) {
  const ch = el('input', { type: 'checkbox' });
  const ok = await modal({ titulo: `Excluir ${c.nome}?`, texto: 'O arquivo da configuração vai para a Lixeira (dá para restaurar).',
    corpo: el('label', { class: 'linha-check' }, ch, ' Também mandar para a Lixeira as pastas work\\' + c.nome + ' e saida\\' + c.nome),
    botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Excluir', classe: 'btn-perigo', valor: true }] }).promessa;
  if (!ok) return;
  const r = await tentar(() => api('config_excluir', { config: c.arquivo, pastas: ch.checked }));
  if (!r) return;
  S.configs = r.configs;
  if (S.sel === c.arquivo) { S.sel = S.configs[0]?.arquivo || null; S.form = null; }
  desenharConfigs(); desenharPrincipal(); desenharPropriedades(); desenharTopo();
  aviso('Mandado para a Lixeira', { tipo: 'sucesso' });
}

// ---------------------------------------------------------------- execução
function estadoEtapa(nome) {
  const ex = S.exec;
  if (!ex || ex.config !== S.sel) return null;
  return ex.etapas[nome] || null;
}

function gradeEtapas() {
  const grade = el('div', { class: 'etapas' });
  S.etapas.forEach((e, i) => {
    const st = estadoEtapa(e.nome);
    const [titulo, explica] = ETAPA[e.nome] || [e.nome, e.descricao];
    grade.append(el('div', { class: `etapa ${st ? st.estado : ''}`, title: `${e.nome} — ${e.script} (${e.tipo})\n${e.descricao}` },
      el('span', { class: 'n' }, String(i + 1)),
      el('div', { class: 'txt' }, el('b', {}, el('span', { class: e.tipo === 'Blender' ? 'tipo-bl' : 'tipo-py', html: icone(e.tipo === 'Blender' ? 'cubo' : 'terminal', 12) }), titulo),
        el('small', {}, explica)),
      el('div', { class: 'acoes' },
        el('button', { class: 'btn-icone peq', title: `Rodar a partir daqui (${titulo} e as seguintes)`, disabled: S.exec?.rodando, onclick: () => executar('de', e.nome) }, icone('play', 13)),
        el('button', { class: 'btn-icone peq', title: `Rodar só esta etapa`, disabled: S.exec?.rodando, onclick: () => executar('so', e.nome) }, icone('ponto', 13))),
      st ? el('span', { class: 'estado' }, st.estado === 'rodando' ? 'rodando…' : st.estado === 'ok' ? `${st.s}s` : 'falhou') : null));
  });
  return grade;
}

function progresso() {
  const ex = S.exec && S.exec.config === S.sel ? S.exec : null;
  const n = S.etapas.length || 1;
  const feitas = ex ? Object.values(ex.etapas || {}).filter((e) => e.estado === 'ok').length : 0;
  const atual = ex?.rodando ? ETAPA[ex.etapa]?.[0] || ex.etapa : null;
  const erro = ex && !ex.rodando && ex.codigo && ex.codigo !== 0;
  return el('div', { class: 'progresso-conv' },
    el('div', { class: 'barra' }, el('div', { class: erro ? 'erro' : '', style: { width: `${Math.round((100 * feitas) / n)}%` } })),
    el('span', {}, ex?.rodando ? `Etapa ${feitas + 1} de ${n}: ${atual} · ${Math.round(Date.now() / 1000 - ex.inicio)} s` : ex?.fim ? (ex.codigo === 0 ? `Concluída em ${Math.round(ex.fim - ex.inicio)} s` : 'Parou com erro — veja a dica e o registro abaixo') : 'Pronta para converter'));
}

function dicaErro() {
  const ex = S.exec && S.exec.config === S.sel ? S.exec : null;
  if (!ex || ex.rodando || !ex.codigo) return null;
  const txt = S.linhas.slice(-120).join('\n');
  const dicas = [];
  if (/blender/i.test(txt) && /(não encontrado|not found|No such file|cannot find)/i.test(txt)) dicas.push('O Blender não foi encontrado: instale o Blender 5.2 ou indique o blender.exe em Componentes, no Super Tool.');
  if (/texconv/i.test(txt) && /(não encontrado|not found|No such file)/i.test(txt)) dicas.push('O texconv não foi encontrado (ele vem com o Super Tool, no Editor de Estádios).');
  if (/(FileNotFoundError|No such file or directory|não existe)/i.test(txt)) dicas.push('Faltou um arquivo ou pasta: confira na Configuração as pastas do mod do PES e do export do FET (e se o export tem os MeshVariationDb_Win32).');
  if (/MemoryError|out of memory/i.test(txt)) dicas.push('Faltou memória: feche outros programas (o atlas 8192 pede bastante) ou use o atlas 4096.');
  if (/KeyError|IndexError|TypeError/i.test(txt)) dicas.push('O motor encontrou algo que não esperava neste estádio. Copie o registro (botão Copiar) e me mande junto com a configuração.');
  if (/\[parado pelo usuário\]/.test(txt)) dicas.push('Você parou a conversão. Use ▶ numa etapa para continuar a partir dela.');
  if (!dicas.length) dicas.push('Veja as últimas linhas do registro (em vermelho). Para tentar de novo a partir da etapa que falhou, use ▶ nela.');
  return nota(dicas.map(esc).join('<br>'), 'alerta');
}

function abaExecucao(p, c) {
  p.append(el('div', { class: 'acoes-linha', style: { marginBottom: '10px' } },
    el('button', { class: 'btn-primario', disabled: S.exec?.rodando, onclick: () => executar('tudo') }, icone('play', 14), 'Converter (todas as etapas)'),
    S.exec?.rodando ? el('button', { class: 'btn', onclick: parar }, icone('parar', 13), 'Parar') : null,
    el('span', { class: 'mudo peq-txt' }, 'Passe o mouse numa etapa: ▶ roda a partir dela, ● roda só ela. Cada etapa usa o que as anteriores gravaram.')));
  p.append(progresso());
  const d = dicaErro();
  if (d) p.append(d);
  p.append(gradeEtapas());
  const bloco = el('section', { class: 'bloco-log' }, el('header', {}, el('h3', {}, 'Registro'),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-fantasma peq', onclick: copiarLog }, icone('copiar', 12), 'Copiar'))),
  el('div', { class: 'console', id: 'console' }));
  p.append(bloco);
  desenharLog(true);
}

function classeLinha(l) {
  if (/^== /.test(l)) return 'l-etapa';
  if (/falhou|Traceback|Error|ERRO|erro:/i.test(l)) return 'l-erro';
  if (/aviso|warning/i.test(l)) return 'l-aviso';
  if (/^pronto:|\[fim: concluído/.test(l)) return 'l-ok';
  return '';
}

function desenharLog(tudo = false) {
  const con = $('#console');
  if (!con) return;
  const meu = S.exec && (S.exec.config === S.sel || S.exec.config === null);
  if (tudo) con.innerHTML = '';
  if (!meu) {
    con.innerHTML = '';
    con.append(el('span', { class: 'mudo' }, S.exec?.rodando ? 'Outra conversão está rodando.' : 'Nada rodou ainda nesta sessão.'));
    return;
  }
  const embaixo = con.scrollTop + con.clientHeight >= con.scrollHeight - 30;
  const frag = document.createDocumentFragment();
  const desde = tudo ? 0 : con.childElementCount;
  for (const l of S.linhas.slice(desde)) frag.append(el('div', { class: classeLinha(l) }, l || ' '));
  con.append(frag);
  if (embaixo || tudo) con.scrollTop = con.scrollHeight;
}

// ---------------------------------------------------------------- importar no FET (lista de conferência + prévias)
function itensRodada(md) {
  // os itens de "Nesta rodada": - `content/...` ← `importar_x\...` — nota
  const ini = md.search(/^##\s+Nesta rodada/m);
  if (ini < 0) return [];
  const resto = md.slice(ini).split('\n').slice(1);
  const out = [];
  for (const l of resto) {
    if (/^##\s/.test(l) || /^\*\*Ordem/.test(l)) break;
    const m = l.match(/^- `([^`]+)`(?:\s*←\s*`([^`]+)`)?\s*(?:—\s*(.*))?$/);
    if (m) out.push({ chave: m[1], asset: m[1], arquivo: m[2] || '', nota: m[3] || '' });
  }
  return out;
}

async function abaPassos(p, c) {
  if (!c.passos) {
    p.append(nota('Ainda não há <i>PASSOS_FET.md</i>: converta primeiro (a última etapa escreve a lista do que importar).', 'info'));
    return;
  }
  const [r, rf, rp] = await Promise.all([tentar(() => api('passos?config=' + encodeURIComponent(c.arquivo))), api('passos_feitos?config=' + encodeURIComponent(c.arquivo)).catch(() => ({ itens: [] })),
    api('previews?config=' + encodeURIComponent(c.arquivo)).catch(() => ({ previews: [] }))]);
  if (!r || S.sel !== c.arquivo || S.aba !== 'passos') return;
  const itens = itensRodada(r.texto);
  const feitos = new Set(rf.itens || []);
  p.append(el('div', { class: 'acoes-linha', style: { marginBottom: '10px' } },
    el('button', { class: 'btn peq', disabled: !c.existe_saida, onclick: () => tentar(() => api('abrir', { caminho: c.saida })) }, icone('pasta', 12), 'Pasta de saída (o que importar)'),
    el('button', { class: 'btn-fantasma peq', onclick: () => tentar(() => api('abrir', { caminho: c.passos, editar: true })) }, icone('externo', 12), 'Abrir o PASSOS_FET.md')));
  if (itens.length) {
    const cont = el('span', { class: 'mudo' });
    const atualizarCont = () => { cont.textContent = `${feitos.size} de ${itens.length} importado(s)`; };
    atualizarCont();
    const lista = el('div', { class: 'checklist' });
    for (const it of itens) {
      const ch = el('input', { type: 'checkbox' });
      ch.checked = feitos.has(it.chave);
      ch.onchange = async () => { if (ch.checked) feitos.add(it.chave); else feitos.delete(it.chave); atualizarCont(); lin.classList.toggle('feito', ch.checked); await api('passos_marcar', { config: c.arquivo, itens: [it.chave], feito: ch.checked }).catch(() => {}); };
      const tipo = /\.fbx$/i.test(it.arquivo) ? 'FBX' : /\.xml$/i.test(it.arquivo) ? 'XML' : /\.dds$/i.test(it.arquivo) ? 'DDS' : '';
      const lin = el('label', { class: `item-check ${ch.checked ? 'feito' : ''}` }, ch,
        el('div', {}, el('div', {}, tipo ? el('span', { class: `etiqueta ${tipo === 'FBX' ? 'laranja' : tipo === 'XML' ? 'azul' : ''}` }, tipo) : null, el('code', {}, it.asset)),
          it.arquivo ? el('small', { class: 'mono' }, '← ' + it.arquivo) : null, it.nota ? el('small', {}, it.nota) : null));
      lista.append(lin);
    }
    p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, 'Nesta rodada: o que (re)importar'), el('p', { class: 'dica' }, 'Marque cada item conforme importa no FET (fica guardado). FBX com "scaled centimeters"; XML por cima do asset de mesmo nome; DDS por cima da textura.')), cont),
      el('div', { class: 'cartao-corpo' }, lista)));
  }
  if (rp.previews?.length) {
    const gal = el('div', { class: 'galeria' });
    for (const pv of rp.previews) {
      const src = '/arquivo?caminho=' + encodeURIComponent(pv.caminho);
      gal.append(el('button', { class: 'prev', title: pv.nome, onclick: () => modal({ titulo: pv.nome, largo: true, corpo: el('img', { src, style: { width: '100%', borderRadius: '6px' } }) }) },
        el('img', { src, loading: 'lazy', alt: pv.nome }), el('span', {}, pv.nome)));
    }
    p.append(el('div', { class: 'cartao' }, el('header', {}, el('div', {}, el('h3', {}, `Prévias (${rp.previews.length})`), el('p', { class: 'dica' }, 'O que vai para o FET, renderizado pelo Blender. Clique para ampliar.'))),
      el('div', { class: 'cartao-corpo' }, gal)));
  }
  const det = el('details', { class: 'secao-form', open: !itens.length }, el('summary', { html: icone('seta', 12, 'seta') + icone('relatorio', 14) + 'Passos completos (PASSOS_FET.md)' }),
    el('div', { class: 'md', html: markdown(r.texto) }));
  p.append(det);
}

// ---------------------------------------------------------------- ferramentas
function abaFerramentas(p, c) {
  const cartao = (ic, titulo, texto, botao) => el('div', { class: 'cartao ferramenta' }, el('div', { class: 'cartao-corpo' },
    el('div', { class: 'ic', html: icone(ic, 26) }), el('div', {}, el('h3', {}, titulo), el('p', {}, texto), botao)));
  p.append(el('div', { class: 'grade-ferramentas' },
    cartao('torcida', 'Avaliar outro estádio base', 'A luz da torcida só existe onde o estádio base já tem torcida. Exporte do FET só a nuvem de assentos de cada candidato (…/crowd/crowd/<componente>_crowd_0) e veja quantos assentos do estádio novo ficariam com luz em cada um.',
      el('button', { class: 'btn peq', disabled: S.exec?.rodando, onclick: async () => { const r = await tentar(() => api('avaliar', { config: c.arquivo })); if (r && !r.cancelado) { trocarAba('execucao'); receberExec(r, true); acompanhar(); } } }, icone('busca', 12), 'Escolher as nuvens (crowd_N.xml)…')),
    cartao('cubo', 'Modelo vazio', 'O mesmo mesh do FET com cada seção reduzida a um triângulo escondido 100 m abaixo do campo. Serve para "apagar" uma peça exclusiva de um estádio sem excluir o objeto (objetos ligados à lógica não podem ser excluídos).',
      el('button', { class: 'btn peq', disabled: S.exec?.rodando, onclick: async () => { const r = await tentar(() => api('vazio', {})); if (r && !r.cancelado) { trocarAba('execucao'); receberExec(r, true); acompanhar(); } } }, icone('arquivoMais', 12), 'Escolher o FBX…')),
    cartao('check', 'Marcar a entrega', 'Depois de importar tudo e testar no jogo. A próxima conversão lista só o que mudar a partir desta saída e traz os XML originais para desfazer edições que não funcionaram.',
      el('button', { class: 'btn peq', disabled: !c.existe_saida || S.exec?.rodando, onclick: marcarEntrega }, icone('check', 12), c.entregue ? `Marcar de novo (última: ${c.entregue_quando})` : 'Marcar entrega')),
    cartao('pasta', 'Pastas', 'Trabalho: o que cada etapa grava (work\\<nome>). Saída: o que vai para o FET (saida\\<nome>).',
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { caminho: c.trabalho })) }, 'Trabalho'),
        el('button', { class: 'btn peq', disabled: !c.existe_saida, onclick: () => tentar(() => api('abrir', { caminho: c.saida })) }, 'Saída'),
        el('button', { class: 'btn peq', onclick: () => tentar(() => api('abrir', { o_que: 'conversor' })) }, 'Motor')))));
}

// ---------------------------------------------------------------- painel direito
function desenharPropriedades() {
  const p = $('#propriedades');
  p.innerHTML = '';
  const c = cfgSel();
  const sec = (titulo, ic, corpo) => {
    const d = el('details', { class: 'secao', open: true });
    d.append(el('summary', { html: icone('seta', 12, 'seta') + icone(ic, 14) + esc(titulo) }), el('div', { class: 'secao-corpo' }, ...[].concat(corpo)));
    return d;
  };
  if (c) {
    p.append(sec('Conversão', 'converter', [el('dl', { class: 'kv' },
      el('dt', {}, 'PES'), el('dd', {}, c.pes || '—'),
      el('dt', {}, 'FC'), el('dd', {}, `${c.fc_estadio || '—'}`),
      el('dt', {}, 'Export'), el('dd', { class: 'mono' }, c.fc_export || '—'),
      el('dt', {}, 'Modo'), el('dd', {}, c.modo === 'multi_mesh' ? 'várias malhas' : 'malha única'),
      el('dt', {}, 'Passos'), el('dd', {}, c.passos_quando || 'ainda não gerados'),
      el('dt', {}, 'Entrega'), el('dd', {}, c.entregue_quando || 'não marcada'))]));
  }
  const amb = S.ambiente.map((a) => el('div', { class: `nota ${a.ok ? '' : 'alerta'}`, title: a.caminho,
    html: icone(a.ok ? 'check' : 'aviso', 15) + `<div><b>${esc(a.nome)}</b><br><span class="mono">${esc(a.caminho)}</span></div>` }));
  if (S.ambiente.some((a) => !a.ok)) amb.push(el('div', { class: 'mudo', style: { fontSize: '12px', lineHeight: '1.5' }, html:
    'Instale o <b>Blender 5.2</b> (blender.org/download) ou indique o <i>blender.exe</i> na página <b>Componentes</b> do Super Tool. O texconv vem com o Super Tool.' }));
  p.append(sec('Programas', 'engrenagem', amb));
  p.append(sec('Como funciona', 'ajuda', el('div', { class: 'mudo', style: { fontSize: '12px', lineHeight: '1.55' }, html: `
    <b>1.</b> Exporte o estádio base no FET. <b>2.</b> Crie a conversão (o assistente acha o estádio do PES e o mundo do FC).
    <b>3.</b> Converta — as etapas rodam sozinhas e cada uma usa o que as anteriores gravaram. <b>4.</b> Importe no FET seguindo
    a lista (aba Importar no FET). <b>5.</b> Teste no jogo e marque a entrega.<br><br>
    A luz da torcida é pré-calculada pela EA para a área do estádio base: use <b>Ferramentas › Avaliar outro estádio base</b>
    para escolher o base que cobre mais assentos.` })));
}

// ---------------------------------------------------------------- topo / status
function desenharTopo() {
  const c = cfgSel();
  const ex = S.exec || {};
  $('#titulo').innerHTML = c ? `<b>${esc(c.nome)}</b><span class="pasta">${esc(c.pes ? c.pes.split('/').pop() : '')} → ${esc(c.fc_estadio || '')}</span>` : '<span class="mudo">Nenhuma conversão selecionada</span>';
  $('#btn-executar').disabled = !c || ex.rodando || !S.ini.existe;
  $('#btn-executar-txt').textContent = ex.rodando ? `Rodando: ${ETAPA[ex.etapa]?.[0] || ex.etapa || '…'}` : 'Converter';
  $('#btn-executar-ic').innerHTML = icone(ex.rodando ? 'recarregar' : 'play', 14, ex.rodando ? 'girando' : '');
  $('#btn-parar').hidden = !ex.rodando;
  const se = $('#status-esq');
  if (ex.rodando) se.textContent = `Rodando ${ex.etapa ? '“' + (ETAPA[ex.etapa]?.[0] || ex.etapa) + '”' : ''} · ${Math.round(Date.now() / 1000 - ex.inicio)} s`;
  else if (ex.fim) se.textContent = `Última execução: ${ex.codigo === 0 ? 'concluída' : 'falhou (código ' + ex.codigo + ')'} em ${Math.round(ex.fim - ex.inicio)} s`;
  else se.textContent = S.ini ? `Pasta de trabalho: ${S.ini.raiz}` : '';
  const sd = $('#status-dir');
  sd.innerHTML = '';
  const falta = S.ambiente.filter((a) => !a.ok);
  sd.append(el('span', { class: `chip ${falta.length ? 'aviso' : 'ok'}`, title: S.ambiente.map((a) => `${a.nome}: ${a.caminho}`).join('\n'),
    html: icone(falta.length ? 'aviso' : 'check', 12) + (falta.length ? `falta: ${falta.map((a) => a.nome).join(', ')}` : 'Blender e texconv prontos') }));
}

// ---------------------------------------------------------------- execução (servidor)
async function executar(modo, etapa = null) {
  const c = cfgSel();
  if (!c) return;
  if (S.sujo && !await confirmar('Gravar antes?', 'A configuração tem mudanças que não foram gravadas: a conversão vai usar a versão gravada.', { rotulo: 'Converter assim' })) return;
  const r = await tentar(() => api('executar', { config: c.arquivo, modo, etapa }));
  if (!r) return;
  aviso(modo === 'tudo' ? 'Conversão iniciada' : modo === 'entregue' ? 'Marcando a entrega…' : `Rodando ${modo === 'so' ? 'só' : 'a partir de'} “${ETAPA[etapa]?.[0] || etapa}”`, { tipo: 'info', tempo: 2000 });
  if (S.aba !== 'execucao' && modo !== 'entregue') { S.aba = 'execucao'; desenharPrincipal(); }
  receberExec(r, true);
  acompanhar();
}
async function marcarEntrega() {
  if (!await confirmar('Marcar a saída como entregue?', 'A próxima conversão vai listar só o que mudar a partir desta saída. Faça isso depois de importar tudo no FET e testar.', { rotulo: 'Marcar entrega' })) return;
  await executar('entregue');
}
async function parar() {
  if (!await confirmar('Parar a conversão?', 'A etapa em andamento (e o Blender, se estiver aberto por ela) é encerrada. As etapas já concluídas ficam guardadas.', { rotulo: 'Parar', perigo: true })) return;
  receberExec(await tentar(() => api('parar', {})));
}
function receberExec(r, reiniciar = false) {
  if (!r || r.cancelado) return;
  const antes = S.exec;
  if (reiniciar || r.desde === 0 && S.seq > r.seq) { S.linhas = []; S.seq = 0; }
  if (r.desde > S.seq) S.linhas = [];
  S.linhas.push(...r.linhas);
  S.seq = r.seq;
  S.exec = r;
  const terminou = antes && antes.rodando && !r.rodando;
  desenharTopo();
  if (S.aba === 'execucao') {
    const grade = $('#principal .etapas');
    if (grade) grade.replaceWith(gradeEtapas());
    const pg = $('#principal .progresso-conv');
    if (pg) pg.replaceWith(progresso());
    desenharLog();
  }
  if (terminou) {
    aviso(r.codigo === 0 ? 'Conversão concluída' : 'A conversão parou com erro', { tipo: r.codigo === 0 ? 'sucesso' : 'erro', tempo: 7000,
      detalhe: r.codigo === 0 ? 'Veja a aba Importar no FET.' : 'Veja a dica e o registro.' });
    recarregarConfigs().then(() => { if (S.aba === 'execucao' || S.aba === 'geral') desenharPrincipal(); });
  }
}
function acompanhar() {
  if (S.polling) return;
  S.polling = setInterval(async () => {
    const r = await api('exec?desde=' + S.seq).catch(() => null);
    if (!r) return;
    receberExec(r);
    if (!r.rodando) { clearInterval(S.polling); S.polling = null; }
  }, 700);
}
async function copiarLog() {
  try { await navigator.clipboard.writeText(S.linhas.join('\n')); aviso('Registro copiado', { tipo: 'sucesso', tempo: 1600 }); }
  catch { aviso('Não foi possível copiar', { tipo: 'erro' }); }
}
async function recarregarConfigs() {
  const r = await tentar(() => api('configs'));
  if (!r) return;
  S.configs = r.configs;
  desenharConfigs();
  desenharPropriedades();
  desenharTopo();
}

// ---------------------------------------------------------------- menus
function menus() {
  barraMenus($('#menus'), [
    ['Conversão', () => [
      { rotulo: 'Nova conversão…', icone: 'mais', fn: assistente },
      { rotulo: 'Duplicar…', icone: 'copias', desabilitado: !cfgSel(), fn: () => duplicar(cfgSel()) },
      '-',
      { rotulo: 'Converter (todas as etapas)', icone: 'play', desabilitado: !cfgSel() || S.exec?.rodando, fn: () => executar('tudo') },
      { rotulo: 'Parar', icone: 'parar', desabilitado: !S.exec?.rodando, fn: parar },
      { rotulo: 'Marcar entrega', icone: 'check', desabilitado: !cfgSel()?.existe_saida || S.exec?.rodando, fn: marcarEntrega },
      '-',
      { rotulo: 'Abrir a pasta de saída', icone: 'pasta', desabilitado: !cfgSel()?.existe_saida, fn: () => tentar(() => api('abrir', { caminho: cfgSel().saida })) },
      { rotulo: 'Excluir (Lixeira)…', icone: 'apagar', desabilitado: !cfgSel(), fn: () => excluir(cfgSel()) },
    ]],
    ['Exibir', () => [
      ...[['geral', 'Visão geral'], ['config', 'Configuração'], ['execucao', 'Converter'], ['passos', 'Importar no FET'], ['ferramentas', 'Ferramentas']]
        .map(([k, t]) => ({ rotulo: t, marcado: S.aba === k, fn: () => trocarAba(k) })),
      '-',
      { rotulo: 'Recarregar a lista', icone: 'recarregar', fn: recarregarConfigs },
    ]],
    ['Ajuda', () => [
      { rotulo: 'Sobre o conversor', icone: 'info', fn: () => dialogoSobre({ nome: 'Conversor de Estádios PES 2021 → FC 26', versao: S.ini.versao, html: `
        Converte o estádio de um mod do PES 2021 num estádio do FC 26 importável pelo FIFA Editor Tool: malhas, atlas de texturas, a
        torcida nos degraus novos e o que sai do estádio base — e diz exatamente o que importar.<br><br>
        <b>2.0</b> — sem comandos: assistente de nova conversão (acha o estádio do mod e o mundo do export), configuração em formulário,
        etapas explicadas com progresso e dicas de erro, lista de conferência do que importar, prévias, ferramentas em cartões e excluir
        para a Lixeira.<br>
        <b>1.0</b> — primeira interface no BRFP Super Tool (o motor é o das rodadas do Maracanã no 483 e no Events 517).` }) },
    ]],
  ]);
}

document.addEventListener('keydown', (e) => {
  if (modalAberto() || menuAberto()) return;
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); executar('tudo'); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && S.aba === 'config') { e.preventDefault(); $('#principal .barra-form .btn-primario')?.click(); }
});
window.addEventListener('beforeunload', (e) => { if (S.sujo) { e.preventDefault(); e.returnValue = ''; } });

// ---------------------------------------------------------------- início
async function iniciar() {
  $('#btn-pasta-configs').innerHTML = icone('pasta', 14);
  $('#btn-recarregar').innerHTML = icone('recarregar', 14);
  $('#btn-parar').innerHTML = icone('parar', 13) + 'Parar';
  $('#btn-pasta-configs').onclick = () => tentar(() => api('abrir', { caminho: S.ini.conversor + '\\configs' }));
  $('#btn-recarregar').onclick = recarregarConfigs;
  $('#btn-executar').onclick = () => executar('tudo');
  $('#btn-parar').onclick = parar;
  divisorArrastavel($('#div-esq'), '--esq', { min: 220, max: 520 });
  divisorArrastavel($('#div-dir'), '--dir', { min: 260, max: 520, lado: 'dir' });
  S.ini = await api('inicio');
  $('#versao').textContent = S.ini.versao;
  S.configs = S.ini.configs;
  S.etapas = S.ini.etapas;
  S.ambiente = S.ini.ambiente;
  S.exec = S.ini.exec;
  S.linhas = S.ini.exec.linhas;
  S.seq = S.ini.exec.seq;
  S.sel = S.exec.config || (S.configs.some((c) => c.arquivo === S.ini.ultima) ? S.ini.ultima : S.configs[0]?.arquivo || null);
  if (S.exec.rodando) S.aba = 'execucao';
  menus();
  desenharConfigs();
  desenharPrincipal();
  desenharPropriedades();
  desenharTopo();
  if (S.exec.rodando) acompanhar();
  setInterval(() => { if (S.exec?.rodando) { desenharTopo(); const pg = $('#principal .progresso-conv'); if (pg) pg.replaceWith(progresso()); } }, 1000);
}

iniciar().catch((e) => { console.error(e); aviso('Erro ao iniciar: ' + e.message, { tipo: 'erro' }); });
