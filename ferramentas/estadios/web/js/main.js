// Editor de Estádios FC — controlador da interface.
import * as THREE from 'three';
import { api, urlArquivo } from './api.js';
import { icone } from './icones.js';
import { $, el, esc, aviso, modal, confirmar, abrirMenu, fecharMenu, modalAberto, menuAberto, arquivoLocal, blobParaBase64, fmtInt, nota, painelAberto, fecharPainel } from './ui.js';
import { Modelo, ehGrupo, m12De } from './modelo.js';
import { Materiais } from './materiais.js';
import { Viewport } from './viewport.js';
import { Arvore } from './arvore.js';
import { Propriedades } from './propriedades.js';
import { Historico } from './historico.js';
import * as D from './dialogos.js';
import * as F from './ferramentas.js';
import { lerFBX } from './fbx.js';

const PREF = (k, padrao) => { try { const v = localStorage.getItem('editor.' + k); return v === null ? padrao : JSON.parse(v); } catch { return padrao; } };
const GUARDA = (k, v) => { try { localStorage.setItem('editor.' + k, JSON.stringify(v)); } catch { /* sem armazenamento */ } };
const MODOS = [['solido', 'Sólido', 'solido'], ['material', 'Material', 'material'], ['arame', 'Arame', 'arame'], ['raiox', 'Raio-X', 'raiox']];
const INTERVALO_AUTOSALVO = 60000;
const ESPERA_AUTOSALVO = 4000;   // grava alguns segundos depois da última alteração

class App {
  constructor() {
    this.modelo = new Modelo();
    this.materiais = new Materiais(this.modelo);
    this.historico = new Historico();
    this.viewport = new Viewport($('#tela'), this.modelo, this.materiais);
    this.arvore = new Arvore($('#arvore'), this.modelo);
    this.props = new Propriedades($('#propriedades'), this);
    this.estadoTorcida = null;
    this.marcados = new Set();
    this.carregado = false;
    this.jogoInfo = { estado: 'indisponivel' };
    this.projeto = null;
    this.materiais.aoCarregar = () => { this.viewport.sujo = true; };
    this.aplicarPreferencias();
    this.montarTopo();
    this.montarFerramentas();
    this.montarBarraVista();
    this.montarDivisores();
    this.ligarEventos();
    this.teclado();
    this.atualizarTudo();
    D.telaInicial(this);
    this.verificarJogo();
    setInterval(() => this.autosalvar(), INTERVALO_AUTOSALVO);
    window.addEventListener('beforeunload', (e) => { if (this.modelo.contarPendentes()) { this.autosalvar(true); e.preventDefault(); e.returnValue = ''; } });
    this._autoEscritos = new Set();
  }

  aplicarPreferencias() {
    const v = this.viewport;
    v.modo = PREF('modo', 'material');
    this.materiais.definirTexturasLigadas(PREF('texturas', true));
    v.mostrarOcultosJogo = PREF('ocultosJogo', true);
    v.mostrarFaltando = PREF('faltando', true);
    v.mostrarInvisiveis = PREF('invisiveis', true);
    v.mostrarGrade = PREF('grade', true);
    v.mostrarLuzes = PREF('luzes', false);
    v.mostrarPessoas = PREF('pessoas', false);
    v.ancoraEscala = PREF('ancoraEscala', 'chao');
    v.encaixe = PREF('encaixe', false);
    v.espaco = PREF('espaco', 'world');
    if (PREF('sombras', false)) v.definirSombras(true);
    const esq = PREF('larguraEsq', null), dir = PREF('larguraDir', null);
    if (esq) document.documentElement.style.setProperty('--esq', esq + 'px');
    if (dir) document.documentElement.style.setProperty('--dir', dir + 'px');
  }

  // ------------------------------------------------------------------ jogo instalado (texturas)
  async verificarJogo() {
    try {
      const i = await api('jogo');
      this.aoMudarJogo(i);
      if (i.estado === 'indexando') setTimeout(() => this.verificarJogo(), 900);
    } catch { setTimeout(() => this.verificarJogo(), 5000); }
  }

  aoMudarJogo(info, forcar = false) {
    const antes = this.jogoInfo || {};
    this.jogoInfo = info;
    const pronto = info.estado === 'pronto' && info.ativo !== false;
    const mudou = forcar || (!!antes.pronto !== pronto) || (antes.qualidade !== info.qualidade);
    info.pronto = pronto;
    this.materiais.jogo = { pronto, qualidade: info.qualidade || 1024 };
    if (mudou && this.carregado) {
      this.materiais.esquecerTudo();
      this.viewport.recriarMateriais();
      if (pronto && antes.estado === 'indexando') aviso('Texturas do FC 26 disponíveis', { tipo: 'sucesso', detalhe: `${fmtInt(info.texturas)} texturas do jogo; as que faltavam no export aparecem agora.` });
    }
    if (info.estado === 'indexando') {
      $('#status-jogo').textContent = `Lendo o FC 26… ${Math.round((info.progresso || 0) * 100)}%`;
      if (forcar) setTimeout(() => this.verificarJogo(), 900);
    } else if (pronto) $('#status-jogo').textContent = 'FC 26 conectado';
    else $('#status-jogo').textContent = info.estado === 'erro' ? 'FC 26: erro' : '';
    $('#status-jogo').title = info.estado === 'erro' ? info.erro : info.mensagem || '';
    if (this.carregado && !this.props._ag && !this.modelo.selecao.size) this.props.agendar();
  }

  abrirConfiguracoes() { D.dialogoConfiguracoes(this); }

  // ------------------------------------------------------------------ montagem da interface
  montarTopo() {
    const menus = $('#menus');
    const defs = [['Arquivo', () => this.menuArquivo()], ['Editar', () => this.menuEditar()], ['Exibir', () => this.menuExibir()],
      ['Ferramentas', () => this.menuFerramentas()], ['Ajuda', () => this.menuAjuda()]];
    for (const [rot, fn] of defs) {
      const b = el('button', { class: 'menu-botao', 'aria-haspopup': 'menu' }, rot);
      const abrir = () => {
        const r = b.getBoundingClientRect();
        b.classList.add('aberto');
        abrirMenu(fn(), r.left, r.bottom + 4, { origem: b, aoFechar: () => b.classList.remove('aberto') });
      };
      b.onclick = () => (b.classList.contains('aberto') ? fecharMenu() : abrir());
      b.onmouseenter = () => { if (menuAberto() && !b.classList.contains('aberto') && document.querySelector('.menu-botao.aberto')) abrir(); };
      menus.append(b);
    }
    $('#btn-desfazer').innerHTML = icone('desfazer', 17);
    $('#btn-refazer').innerHTML = icone('refazer', 17);
    $('#btn-desfazer').onclick = () => this.desfazer();
    $('#btn-refazer').onclick = () => this.refazer();
    $('.btn-salvar-ic').innerHTML = icone('salvar', 15);
    $('#btn-salvar').onclick = () => this.salvar();
    $('#btn-alteracoes').onclick = () => this.abrirAlteracoes();
    $('#btn-expandir').innerHTML = icone('expandir', 14);
    $('#btn-recolher').innerHTML = icone('recolher', 14);
    $('#btn-expandir').onclick = () => this.arvore.expandirTudo(null, true);
    $('#btn-recolher').onclick = () => this.arvore.expandirTudo(null, false);
    $('.campo-busca-ic').innerHTML = icone('busca', 14);
    let t;
    $('#busca').addEventListener('input', (e) => { clearTimeout(t); t = setTimeout(() => this.arvore.definirBusca(e.target.value), 140); });
    $('#busca').addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.target.value = ''; this.arvore.definirBusca(''); $('#arvore').focus(); } e.stopPropagation(); });
    $('#filtro').onchange = (e) => this.arvore.definirFiltro(e.target.value);
    this.arvore.addEventListener('filtroLimpo', () => { $('#busca').value = ''; $('#filtro').value = 'tudo'; });
    $('#legenda').innerHTML = `<span>${icone('jogo', 13)} aparece no jogo</span><span>${icone('olho', 13)} visível no editor</span><span><i style="width:7px;height:7px;border-radius:50%;background:var(--acento);display:inline-block"></i> alterado</span><span>${icone('ligado', 12)} ligado à lógica</span>`;
  }

  montarFerramentas() {
    const f = $('#ferramentas');
    const defs = [
      ['selecionar', 'cursor', 'Selecionar (Q)'], ['mover', 'mover', 'Mover com gizmo (W) · G move livre'], ['girar', 'girar', 'Girar (R)'], ['escala', 'escala', 'Escalar (S) · Shift = por igual'],
    ];
    this.botoesFerramenta = {};
    for (const [id, ic, tit] of defs) {
      const b = el('button', { class: 'btn-icone', title: tit, 'aria-label': tit, html: icone(ic, 18), onclick: () => this.definirFerramenta(id) });
      this.botoesFerramenta[id] = b;
      f.append(b);
    }
    f.append(el('div', { class: 'sep-h' }));
    this.btnEspaco = el('button', { class: 'btn-icone', onclick: () => this.alternarEspaco() });
    this.btnEncaixe = el('button', { class: 'btn-icone', title: 'Encaixe em passos: 0,5 m · 15° · 0,1 (X, ou segure Ctrl)', html: icone('ima', 18), onclick: () => this.alternarEncaixe() });
    this.btnCaixa = el('button', { class: 'btn-icone', title: 'Selecionar em caixa (ou Ctrl + arrastar)', html: icone('selecao', 18), onclick: () => this.alternarFerramentaCaixa() });
    f.append(this.btnEspaco, this.btnEncaixe, this.btnCaixa);
    this.atualizarFerramentas();
  }

  montarBarraVista() {
    const b = $('#barra-vista');
    const seg = el('div', { class: 'segmentado', role: 'radiogroup', 'aria-label': 'Modo de exibição' });
    this.botoesModo = {};
    for (const [id, rot, ic] of MODOS) {
      const bt = el('button', { title: `${rot} (Z alterna)`, role: 'radio', html: icone(ic, 15) + `<span>${rot}</span>`, onclick: () => this.definirModo(id) });
      this.botoesModo[id] = bt;
      seg.append(bt);
    }
    b.append(seg);
    b.append(el('span', { class: 'sep-v' }));
    this.btnTex = el('button', { class: 'btn-icone', title: 'Texturas (T)', html: icone('textura', 17), onclick: () => this.alternarTexturas() });
    this.btnSombras = el('button', { class: 'btn-icone', title: 'Sombras do sol', html: icone('sol', 17), onclick: () => this.alternarSombras() });
    this.btnLuzes = el('button', { class: 'btn-icone', title: 'Luzes do estádio (posições)', html: icone('luz', 17), onclick: () => this.alternarLuzes() });
    this.btnCampo = el('button', { class: 'btn-icone', title: 'Linhas do campo (tamanho do stadiums.txt)', html: icone('campo', 17), onclick: () => this.alternarCampo() });
    this.btnTorcida = el('button', { class: 'btn-icone', title: 'Torcida: mostrar, marcar, colorir e gerar assentos', html: icone('torcida', 17), onclick: () => this.abrirPainelTorcida() });
    this.btnPessoas = el('button', { class: 'btn-icone', title: 'Pessoas da lateral, assentos do banco e áreas técnicas', html: icone('pessoa', 17), onclick: () => this.alternarPessoas() });
    this.btnEspelho = el('button', { class: 'btn-icone', title: 'Ver como o jogo mostra (estádio espelhado, ismirrored = 1)', html: icone('espelho', 17), onclick: () => this.alternarEspelho() });
    const vistas = el('button', { class: 'btn-icone', title: 'Vistas prontas', html: icone('camera', 17) });
    vistas.onclick = () => {
      const r = vistas.getBoundingClientRect();
      abrirMenu([
        { rotulo: 'Perspectiva', atalho: 'Num 5', fn: () => this.viewport.vista('perspectiva') },
        { rotulo: 'De cima', atalho: 'Num 7', fn: () => this.viewport.vista('topo') },
        { rotulo: 'De frente', atalho: 'Num 1', fn: () => this.viewport.vista('frente') },
        { rotulo: 'De trás', atalho: 'Ctrl+Num 1', fn: () => this.viewport.vista('tras') },
        { rotulo: 'Lateral direita', atalho: 'Num 3', fn: () => this.viewport.vista('direita') },
        { rotulo: 'Lateral esquerda', atalho: 'Ctrl+Num 3', fn: () => this.viewport.vista('esquerda') },
        '-', { rotulo: 'Enquadrar tudo', atalho: 'Home', icone: 'maximizar', fn: () => this.viewport.enquadrarTudo() },
      ], r.right - 220, r.bottom + 6, { origem: vistas });
    };
    const tudo = el('button', { class: 'btn-icone', title: 'Enquadrar tudo (Home)', html: icone('maximizar', 17), onclick: () => this.viewport.enquadrarTudo() });
    b.append(this.btnTex, this.btnSombras, this.btnLuzes, this.btnCampo, this.btnPessoas, this.btnTorcida, this.btnEspelho, el('span', { class: 'sep-v' }), vistas, tudo);
    const dica = $('#dica-navegacao');
    if (PREF('dicaFechada2', false)) dica.hidden = true;
    dica.innerHTML = `<span><kbd>Arrastar</kbd> girar</span><span><kbd>Shift</kbd>+arrastar mover</span><span><kbd>Roda</kbd> zoom</span><span><kbd>Botão dir.</kbd>+<kbd>WASD</kbd> voar</span><span><kbd>G</kbd> mover livre</span><span><kbd>F</kbd> enquadrar</span><span><kbd>?</kbd> atalhos</span>`;
    const x = el('button', { class: 'fechar', title: 'Esconder dica', html: icone('x', 13), onclick: () => { dica.hidden = true; GUARDA('dicaFechada2', true); } });
    dica.append(x);
    if (!$('#status-jogo')) $('.status-dir').prepend(el('span', { id: 'status-jogo', style: { cursor: 'pointer' }, onclick: () => this.abrirConfiguracoes() }));
  }

  montarDivisores() {
    for (const d of document.querySelectorAll('.divisor')) {
      d.addEventListener('pointerdown', (e) => {
        d.setPointerCapture(e.pointerId);
        d.classList.add('arrastando');
        const lado = d.dataset.lado;
        const mover = (ev) => {
          const w = lado === 'esq' ? ev.clientX : window.innerWidth - ev.clientX;
          const v = Math.max(200, Math.min(560, w));
          document.documentElement.style.setProperty(lado === 'esq' ? '--esq' : '--dir', v + 'px');
          GUARDA(lado === 'esq' ? 'larguraEsq' : 'larguraDir', v);
        };
        const soltar = () => { d.classList.remove('arrastando'); d.removeEventListener('pointermove', mover); d.removeEventListener('pointerup', soltar); };
        d.addEventListener('pointermove', mover);
        d.addEventListener('pointerup', soltar);
      });
    }
  }

  ligarEventos() {
    const v = this.viewport, md = this.modelo;
    v.addEventListener('clique', (e) => this.aoClicarViewport(e.detail));
    v.addEventListener('caixa', (e) => { md.selecionar(e.detail.ids, { modo: e.detail.shift ? 'adicionar' : 'substituir' }); if (this.ferramentaCaixaAtiva) this.alternarFerramentaCaixa(false); });
    v.addEventListener('caixaTorcida', (e) => this.marcarAssentos(e.detail));
    v.addEventListener('transformado', (e) => {
      const { antes, depois, nome } = e.detail;
      this.historico.executar({ nome, desfazer: () => md.definirLocais(antes), refazer: () => md.definirLocais(depois) });
    });
    v.addEventListener('arrastando', () => this.props.atualizarValores());
    v.addEventListener('livre', (e) => this.aoMoverLivre(e.detail));
    v.addEventListener('fps', (e) => { $('#status-fps').textContent = e.detail ? `${e.detail} fps` : ''; });
    v.addEventListener('velocidade', (e) => this.dicaViewport(`Velocidade do voo: ${Math.round(e.detail)} m/s`, 1200));
    this.arvore.addEventListener('olho', (e) => {
      const n = md.nos[e.detail.id];
      if (e.detail.solo && n.pai >= 0) {
        const irmaos = md.nos[n.pai].filhos.filter((f) => f !== n.id);
        md.definirVisEditor(irmaos, false);
        md.definirVisEditor([n.id], true);
      } else {
        const alvos = md.selecao.has(n.id) ? [...md.selecao] : [n.id];
        md.definirVisEditor(alvos, !n.visEditor);
      }
    });
    this.arvore.addEventListener('jogo', (e) => {
      const n = md.nos[e.detail.id];
      const alvos = md.selecao.has(n.id) ? [...md.selecao].filter((i) => md.nos[i].jogo) : [n.id];
      this.definirJogo(alvos, !md.ocultoNoJogoProprio(n));
    });
    this.arvore.addEventListener('focar', (e) => this.focar([e.detail.id]));
    this.arvore.addEventListener('menu', (e) => this.menuContexto(e.detail.x, e.detail.y));
    md.addEventListener('selecao', () => { this.atualizarStatus(); if (md.ativo >= 0 && document.activeElement !== $('#arvore')) this.arvore.revelar(md.ativo); });
    for (const ev of ['locais', 'jogo', 'material', 'gravado', 'torcida', 'luz', 'estadio']) md.addEventListener(ev, () => this.atualizarPendentes());
    md.addEventListener('estrutura', () => { this.arvore.atualizar(true); this.atualizarPendentes(); this.props.agendar(); });
    md.addEventListener('luz', () => this.props.atualizarValores?.());
    md.addEventListener('estadio', () => this.aoMudarEstadio());
    md.addEventListener('visEditor', () => this.guardarOcultosEditor());
    md.addEventListener('torcida', () => this.aoAlterarTorcida());
    this.historico.addEventListener('mudou', () => {
      this.atualizarPendentes();
      this._sujoAuto = true;
      clearTimeout(this._tAuto);
      this._tAuto = setTimeout(() => this.autosalvar(), ESPERA_AUTOSALVO);
    });
  }

  // ------------------------------------------------------------------ abrir / carregar
  async abrir(pastas, mundo = null, depois = null) {
    if (this.modelo.contarPendentes() && !await confirmar('Descartar alterações?', 'Há alterações não salvas no estádio aberto. (Elas ficam guardadas no salvamento automático.)', { rotulo: 'Descartar e abrir', perigo: true })) return false;
    await this.autosalvar(false);
    fecharPainel();
    this.carregando('Lendo a pasta…', 'Indexando arquivos do export', -1);
    let r;
    try { r = await api('abrir', { pastas }); } catch (e) { this.carregando(null); aviso(e.message, { tipo: 'erro' }); return false; }
    this.pastas = r.pastas;
    this.mundos = r.mundos;
    this.carregando(null);
    if (!r.mundos.length) {
      modal({ titulo: 'Nenhum estádio nesta pasta', texto: `Procurei um mundo de estádio (<i>worlds/stadiums/&lt;nome&gt;/&lt;nome&gt;.xml</i>) em <b>${esc(pastas[0])}</b> e não encontrei.`,
        corpo: nota('No FET, exporte a pasta do mundo do estádio (ex.: <i>content/worlds/stadiums/events_stadium_517</i>) junto com a dos componentes (<i>content/worlds/components/stadiums/…</i>). Depois abra a pasta raiz desse export.'),
        botoes: [{ rotulo: 'Escolher outra pasta', classe: 'btn', fn: () => { D.abrirPasta(this); } }, { rotulo: 'Fechar', classe: 'btn-primario', padrao: true }] });
      return false;
    }
    let alvo = mundo && r.mundos.find((m) => m.nome === mundo || m.asset === mundo);
    if (!alvo) {
      const estadios = r.mundos.filter((m) => !/loader|cinematic/i.test(m.asset));
      if (r.mundos.length === 1) alvo = r.mundos[0];
      else if (estadios.length === 1 && !mundo) alvo = estadios[0];
      else {
        const asset = await D.escolherMundo(r.mundos, r.pastas, r.ultimo);
        if (!asset) return false;
        alvo = r.mundos.find((m) => m.asset === asset);
      }
    }
    return this.carregarMundo(alvo.asset, depois);
  }

  async carregarMundo(asset, depois = null) {
    fecharPainel();
    this.carregando('Montando o estádio…', 'Lendo mundo, world parts, blueprints, luzes e MeshVariationDb', -1);
    let j;
    const t0 = performance.now();
    try { j = await api('cena', { mundo: asset }); } catch (e) { this.carregando(null); aviso(e.message, { tipo: 'erro' }); return false; }
    this.estadoTorcida = null;
    this.marcados = new Set();
    this.catalogo = null;
    this.modelo.catalogo = null;
    this.materiais.esquecerTudo();
    this.modelo.carregar(j);
    this.restaurarOcultosEditor(asset);
    this.historico.limpar();
    this.arvore.carregar();
    document.getElementById('app').classList.remove('sem-cena');
    this.carregado = true;
    this.mundoAtual = asset;
    if (!depois) this.projeto = null;
    this.viewport.camera.position.set(160, 120, 190);
    this.viewport.controles.target.set(0, 0, 0);
    this.carregando(null);
    const camInicial = this.viewport.camera.position.clone();
    const pill = (txt) => this.dicaViewport(txt, 0);
    pill('Carregando malhas…');
    const r = await this.viewport.construir((feitos, total, nome) => pill(`Carregando malhas ${feitos}/${total} · ${nome}`));
    this.dicaViewport(this._nOcultos ? `${this._nOcultos} item(ns) continuam ocultos no editor desde a última vez · Alt+H mostra tudo` : null, 5000);
    this._nOcultos = 0;
    if (this.viewport.camera.position.distanceTo(camInicial) < 0.01) this.viewport.enquadrarTudo(true);
    if (PREF('campo', false)) this.viewport.definirCampo(this.modelo.campo.comprimento, this.modelo.campo.largura, true);
    this.viewport.definirEspelho(false);
    this.viewport.definirZonas(this.modelo.estadio?.atual.zonas, this.viewport.mostrarPessoas);
    this.atualizarTudo();
    this.props.montar();
    const seg = ((performance.now() - t0) / 1000).toFixed(1);
    const objs = this.modelo.nos.filter((n) => !ehGrupo(n) && n.tipo !== 'luz').length;
    if (depois) await depois();
    else {
      aviso(`${j.nos[0].nome} carregado`, { tipo: 'sucesso', detalhe: `${fmtInt(objs)} objetos · ${fmtInt(r.malhas)} malhas em ${seg}s${r.erros.length ? ` · ${r.erros.length} FBX com erro` : ''}` });
      this.oferecerRecuperacao();
    }
    if (r.erros.length) aviso('Alguns FBX não puderam ser lidos', { tipo: 'aviso', detalhe: r.erros.slice(0, 4).join(' · ') });
    return true;
  }

  recarregar() {
    if (!this.pastas) return;
    this.abrir(this.pastas, this.mundoAtual);
  }

  async fechar() {
    if (this.modelo.contarPendentes() && !await confirmar('Descartar alterações?', 'Há alterações não salvas. (Elas ficam guardadas no salvamento automático.)', { rotulo: 'Descartar', perigo: true })) return;
    await this.autosalvar(false);
    fecharPainel();
    this.viewport.limpar();
    this.modelo.limpar();
    this.modelo.carregar({ nos: [], malhas: {}, mvdbs: {}, texturas: {}, mundo: null });
    this.historico.limpar();
    this.arvore.carregar();
    this.carregado = false;
    this.projeto = null;
    document.getElementById('app').classList.add('sem-cena');
    D.telaInicial(this);
    this.atualizarTudo();
  }

  carregando(titulo, detalhe = '', progresso = -1) {
    const c = $('#carregando');
    if (!titulo) { c.hidden = true; return; }
    c.hidden = false;
    $('#carregando-titulo').textContent = titulo;
    $('#carregando-detalhe').textContent = detalhe;
    const barra = $('#carregando-barra').parentElement;
    barra.classList.toggle('indeterminado', progresso < 0);
    if (progresso >= 0) $('#carregando-barra').style.width = Math.round(progresso * 100) + '%';
  }

  dicaViewport(txt, tempo = 2500) {
    const a = $('#aviso-viewport');
    clearTimeout(this._dicaVp);
    if (!txt) { a.hidden = true; return; }
    a.innerHTML = '';
    a.append(...(Array.isArray(txt) ? txt : [document.createTextNode(txt)]));
    a.hidden = false;
    if (tempo) this._dicaVp = setTimeout(() => { a.hidden = true; }, tempo);
  }

  // ------------------------------------------------------------------ projeto (trabalho em andamento) e salvamento automático
  estadoProjeto() {
    const v = this.viewport;
    return {
      formato: 'editor-estadios', versao: 2, salvoEm: new Date().toISOString(),
      pastas: this.pastas, mundo: this.mundoAtual,
      estado: this.modelo.exportarEstado(),
      visao: {
        camera: v.camera.position.toArray(), alvo: v.controles.target.toArray(), modo: v.modo,
        ocultosEditor: this.modelo.nos.filter((n) => !n.visEditor).map((n) => this.chaveVis(n)),
        campo: v.mostrarCampo, luzes: v.mostrarLuzes,
      },
    };
  }

  async salvarProjeto(comoNovo = false) {
    if (!this.carregado) return;
    let caminho = this.projeto;
    if (!caminho || comoNovo) {
      const nome = `${(this.mundoAtual || 'estadio').split('/').pop()}.estadio.json`;
      const r = await api('dialogo_arquivo', { modo: 'salvar', nome, inicial: this.pastas?.[0] ? this.pastas[0].replace(/[\\/][^\\/]*$/, '') : '' });
      if (!r.caminho) return;
      caminho = r.caminho;
    }
    try {
      const r = await api('projeto_salvar', { caminho, dados: this.estadoProjeto() });
      this.projeto = r.caminho;
      aviso('Projeto salvo', { tipo: 'sucesso', detalhe: `${r.caminho} · os arquivos do jogo não foram alterados (para isso use Salvar / Ctrl+S).` });
      this.atualizarPendentes();
    } catch (e) { aviso('Não foi possível salvar o projeto', { tipo: 'erro', detalhe: e.message }); }
  }

  async abrirProjeto(caminho = null) {
    if (!caminho) {
      const r = await api('dialogo_arquivo', { modo: 'abrir' });
      if (!r.caminho) return;
      caminho = r.caminho;
    }
    let dados;
    try { dados = (await api('projeto_ler', { caminho })).dados; } catch (e) { aviso('Não foi possível abrir o projeto', { tipo: 'erro', detalhe: e.message }); return; }
    await this.abrir(dados.pastas, dados.mundo, async () => {
      this.projeto = caminho;
      await this.aplicarEstadoProjeto(dados);
      aviso(`Projeto ${caminho.split(/[\\/]/).pop()} aberto`, { tipo: 'sucesso', detalhe: `${this.modelo.contarPendentes()} alteração(ões) do projeto prontas — salve (Ctrl+S) quando quiser gravar nos arquivos.` });
    });
  }

  async aplicarEstadoProjeto(dados) {
    const md = this.modelo, v = this.viewport;
    if (dados.estado?.torcida) await this.carregarTorcida();
    const r = md.importarEstado(dados.estado || {});
    if (r.torcida && md.torcida) {
      md.torcida.atual = { n: r.torcida.posicoes.length / 3, posicoes: r.torcida.posicoes, mapas: r.torcida.mapas };
      this.aoAlterarTorcida();
    }
    const vis = dados.visao || {};
    if (vis.ocultosEditor) {
      const lista = new Set(vis.ocultosEditor);
      md.definirVisEditor(md.nos.filter((n) => lista.has(this.chaveVis(n))).map((n) => n.id), false);
    }
    if (vis.camera) { v.camera.position.fromArray(vis.camera); v.controles.target.fromArray(vis.alvo); v.controles.update(); }
    if (vis.modo) this.definirModo(vis.modo);
    if (vis.campo) v.definirCampo(md.campo.comprimento, md.campo.largura, true);
    if (vis.luzes) { v.mostrarLuzes = true; v.atualizarVisibilidade(); }
    if (r.avisos.length) aviso(`${r.avisos.length} item(ns) do projeto não existem mais neste export`, { tipo: 'aviso', detalhe: 'O export mudou desde que o projeto foi salvo.' });
    this.atualizarTudo();
    this.props.agendar();
  }

  chaveAutosalvo() { return `${(this.pastas || [])[0]}|${this.mundoAtual}`; }

  // agora: ao fechar a aba (sendBeacon, que só leva até 64 KB — por isso o normal é gravar logo após cada alteração).
  // limpar: depois de salvar no export, apaga o autosalvo mesmo que ele venha de outra sessão.
  autosalvar(agora = false, limpar = false) {
    clearTimeout(this._tAuto);
    if (!this.carregado || (!this._sujoAuto && !agora && !limpar)) return Promise.resolve();
    this._sujoAuto = false;
    const chave = this.chaveAutosalvo();
    const pend = this.modelo.contarPendentes();
    // Sem pendências, um autosalvo de outra sessão continua guardado até a pessoa decidir se quer recuperá-lo.
    if (!pend && !limpar && !this._autoEscritos.has(chave)) return Promise.resolve();
    const dados = pend ? this.estadoProjeto() : null;
    if (dados) this._autoEscritos.add(chave); else this._autoEscritos.delete(chave);
    if (agora) {
      const corpo = JSON.stringify({ chave, dados });
      if (corpo.length < 60000 && navigator.sendBeacon) navigator.sendBeacon('/api/autosalvar', new Blob([corpo], { type: 'application/json' }));
      return Promise.resolve();
    }
    return api('autosalvar', { chave, dados }).catch(() => {});
  }

  async oferecerRecuperacao() {
    let r;
    try { r = await api('autosalvo', { chave: this.chaveAutosalvo() }); } catch { return; }
    if (!r.dados || !r.dados.estado) return;
    const e = r.dados.estado;
    const n = (e.nos?.length || 0) + (e.materiais?.length || 0) + (e.torcida ? 1 : 0);
    if (!n) return;
    aviso(`Há trabalho não salvo de ${r.quando} (${n} alteração(ões))`, { tempo: 20000, detalhe: 'O editor guardou automaticamente antes de fechar.',
      acao: { rotulo: 'Recuperar', fn: () => this.aplicarEstadoProjeto(r.dados).then(() => aviso('Trabalho recuperado', { tipo: 'sucesso', detalhe: 'Confira e salve (Ctrl+S) ou guarde como projeto (Ctrl+Shift+S).' })) } });
  }

  // ------------------------------------------------------------------ estado da interface
  atualizarTudo() {
    this.atualizarFerramentas();
    this.atualizarBarraVista();
    this.atualizarPendentes();
    this.atualizarStatus();
  }

  atualizarFerramentas() {
    const v = this.viewport;
    for (const [id, b] of Object.entries(this.botoesFerramenta || {})) b.classList.toggle('ativo', v.ferramenta === id);
    if (this.btnEspaco) {
      this.btnEspaco.innerHTML = icone(v.espaco === 'local' ? 'local' : 'mundo', 18);
      this.btnEspaco.title = v.espaco === 'local' ? 'Eixos do objeto (L para eixos do mundo)' : 'Eixos do mundo (L para eixos do objeto)';
      this.btnEncaixe.classList.toggle('ativo', v.encaixe);
      this.btnCaixa.classList.toggle('ativo', !!this.ferramentaCaixaAtiva);
    }
  }

  atualizarBarraVista() {
    const v = this.viewport;
    for (const [id, b] of Object.entries(this.botoesModo || {})) { b.classList.toggle('ativo', v.modo === id); b.setAttribute('aria-checked', v.modo === id); }
    this.btnTex?.classList.toggle('ativo', this.materiais.texturasLigadas);
    this.btnSombras?.classList.toggle('ativo', v.mostrarSombras);
    this.btnLuzes?.classList.toggle('ativo', v.mostrarLuzes);
    this.btnCampo?.classList.toggle('ativo', v.mostrarCampo);
    this.btnPessoas?.classList.toggle('ativo', v.mostrarPessoas);
    if (this.btnEspelho) {
      const est = this.modelo.estadio?.atual;
      this.btnEspelho.classList.toggle('ativo', v.espelhado);
      this.btnEspelho.hidden = !this.carregado || (!est?.espelhado && !v.espelhado);
    }
    if (this.btnTorcida) {
      this.btnTorcida.classList.toggle('ativo', !!this.estadoTorcida?.visivel);
      this.btnTorcida.disabled = !this.modelo.nuvens?.length;
      this.btnTorcida.title = this.modelo.nuvens?.length ? 'Torcida: mostrar, marcar, colorir e gerar assentos' : 'Este export não tem a nuvem de assentos da torcida';
    }
  }

  atualizarPendentes() {
    const n = this.modelo.contarPendentes();
    const c = $('#contador-pendentes');
    c.hidden = !n;
    c.textContent = n;
    $('#btn-salvar').disabled = !n;
    $('#btn-salvar').title = n ? `Gravar ${n} alteraç${n > 1 ? 'ões' : 'ão'} nos arquivos (Ctrl+S)` : 'Nada a salvar';
    $('#btn-desfazer').disabled = !this.historico.podeDesfazer;
    $('#btn-refazer').disabled = !this.historico.podeRefazer;
    $('#btn-desfazer').title = this.historico.podeDesfazer ? `Desfazer: ${this.historico.proximoDesfazer} (Ctrl+Z)` : 'Desfazer (Ctrl+Z)';
    $('#btn-refazer').title = this.historico.podeRefazer ? `Refazer: ${this.historico.proximoRefazer} (Ctrl+Shift+Z)` : 'Refazer (Ctrl+Shift+Z)';
    const t = $('#titulo-mundo');
    if (this.carregado) {
      const proj = this.projeto ? `<span class="etiqueta" title="${esc(this.projeto)}">${icone('arquivo', 11)}${esc(this.projeto.split(/[\\/]/).pop())}</span>` : '';
      t.innerHTML = `${icone('estadio', 15)}<b>${esc(this.modelo.nos[0]?.nome || '')}</b><span class="pasta" title="${esc((this.pastas || []).join('\n'))}">${esc(this.pastas?.[0] || '')}</span>${proj}${n ? '<span class="etiqueta azul">não salvo</span>' : ''}`;
      document.title = `${n ? '● ' : ''}${this.modelo.nos[0]?.nome} — Editor de Estádios FC`;
    } else { t.innerHTML = ''; document.title = 'Editor de Estádios FC'; }
  }

  atualizarStatus() {
    const md = this.modelo;
    const sel = md.selecao.size;
    $('#status-selecao').textContent = sel ? (sel === 1 ? `Selecionado: ${md.nos[md.ativo]?.rotulo || ''}` : `${fmtInt(sel)} selecionados`) : '';
    if (this.carregado) {
      const objs = md.nos.filter((n) => !ehGrupo(n) && n.tipo !== 'luz').length;
      $('#status-cena').textContent = `${fmtInt(objs)} objetos`;
    } else $('#status-cena').textContent = '';
    if (this.viewport.livre) return;
    const dicas = {
      selecionar: 'Clique para selecionar · Ctrl+arrastar seleciona em caixa · G move livre · R/S giram e escalam',
      mover: 'Arraste as setas do gizmo · G move livre seguindo o mouse · segure Ctrl para passos de 0,5 m',
      girar: 'Arraste os anéis para girar · segure Ctrl para passos de 15°',
      escala: 'Arraste os cubos para escalar · segure Shift para escalar por igual',
    };
    $('#status-dica').textContent = this.carregado ? (this.modoEscolha ? this.modoEscolha.msg : this.ferramentaCaixaAtiva ? 'Arraste uma caixa na vista para selecionar' : dicas[this.viewport.ferramenta]) : 'Abra uma pasta exportada pelo FET para começar';
  }

  // ------------------------------------------------------------------ ferramentas e exibição
  definirFerramenta(f) {
    this.viewport.definirFerramenta(f);
    if (f !== 'selecionar' && this.carregado && !this.viewport.nosMoveis().length && this.modelo.selecao.size) this.dicaViewport('A seleção não tem objetos que possam ser movidos (grupos sem referência própria).');
    this.atualizarFerramentas();
    this.atualizarStatus();
  }

  alternarEspaco() {
    const v = this.viewport;
    v.espaco = v.espaco === 'world' ? 'local' : 'world';
    GUARDA('espaco', v.espaco);
    v.atualizarGizmo();
    this.atualizarFerramentas();
    this.dicaViewport(v.espaco === 'local' ? 'Gizmo nos eixos do objeto' : 'Gizmo nos eixos do mundo', 1400);
  }

  alternarEncaixe() {
    const v = this.viewport;
    v.encaixe = !v.encaixe;
    GUARDA('encaixe', v.encaixe);
    v.aplicarEncaixe();
    this.atualizarFerramentas();
    this.dicaViewport(v.encaixe ? 'Encaixe ligado: 0,5 m · 15° · 0,1' : 'Encaixe desligado', 1400);
  }

  alternarFerramentaCaixa(v = !this.ferramentaCaixaAtiva) {
    this.ferramentaCaixaAtiva = v;
    this.viewport.ferramentaCaixa = v ? 'objetos' : null;
    this.atualizarFerramentas();
    this.atualizarStatus();
  }

  definirModo(m) {
    this.viewport.definirModo(m);
    GUARDA('modo', m);
    this.atualizarBarraVista();
  }

  alternarTexturas() {
    this.materiais.definirTexturasLigadas(!this.materiais.texturasLigadas);
    GUARDA('texturas', this.materiais.texturasLigadas);
    this.viewport.recriarMateriais();
    this.atualizarBarraVista();
    this.dicaViewport(this.materiais.texturasLigadas ? 'Texturas ligadas' : 'Texturas desligadas (só cores)', 1400);
  }

  alternarSombras() {
    const v = !this.viewport.mostrarSombras;
    this.viewport.definirSombras(v);
    GUARDA('sombras', v);
    this.atualizarBarraVista();
  }

  alternarLuzes(v = !this.viewport.mostrarLuzes) {
    this.viewport.mostrarLuzes = v;
    GUARDA('luzes', v);
    this.viewport.atualizarVisibilidade();
    this.atualizarBarraVista();
    const n = this.modelo.nos.filter((x) => x.tipo === 'luz').length;
    this.dicaViewport(v ? `${fmtInt(n)} luzes à mostra (spot = cone, pontual = esfera) · filtre “Luzes” na estrutura` : 'Luzes escondidas', 2200);
  }

  alternarCampo(v = !this.viewport.mostrarCampo) {
    const c = this.modelo.campo;
    this.viewport.definirCampo(c.comprimento, c.largura, v);
    GUARDA('campo', v);
    this.atualizarBarraVista();
    if (v) this.dicaViewport(`Linhas do campo: ${c.comprimento} × ${c.largura} m${c.fonte ? ` (${c.fonte}${c.nome ? ' · ' + c.nome : ''})` : ' (padrão FIFA; stadiums.txt não encontrado)'}`, 4000);
    this.props.agendar();
  }

  alternarOpcao(chave, pref) {
    const v = this.viewport;
    v[chave] = !v[chave];
    GUARDA(pref, v[chave]);
    v.atualizarVisibilidade();
    v.aplicarModo();
  }

  // ------------------------------------------------------------------ seleção e visibilidade
  aoClicarViewport(d) {
    const md = this.modelo;
    if (this.viewport.ferramentaCaixa === 'torcida') return;
    if (this.modoLuz && !d.duplo) { this.modoLuz.aoClicar(d); return; }
    if (this.modoEscolha) {
      if (d.id >= 0) { const cb = this.modoEscolha.cb; this.cancelarEscolhaNaVista(); cb(d.id); }
      return;
    }
    if (d.duplo) {
      if (d.id < 0) return;
      let n = md.nos[d.id];
      while (n.pai >= 0 && !ehGrupo(md.nos[n.pai])) n = md.nos[n.pai];
      md.selecionar(n.id);
      this.arvore.revelar(n.id);
      return;
    }
    if (d.id < 0) { if (!d.ctrl && !d.shift) md.selecionar([]); return; }
    md.selecionar(d.id, { modo: d.ctrl ? 'alternar' : d.shift ? 'adicionar' : 'substituir' });
    this.arvore.revelar(d.id);
  }

  escolherNaVista(msg, cb) {
    this.modoEscolha = { msg, cb };
    const sair = el('button', { onclick: () => this.cancelarEscolhaNaVista() }, 'Cancelar');
    this.dicaViewport([el('span', { html: icone('alvo', 14) }), document.createTextNode(msg + ' · '), sair], 0);
    this.atualizarStatus();
  }

  cancelarEscolhaNaVista() {
    if (!this.modoEscolha) return;
    this.modoEscolha = null;
    this.dicaViewport(null);
    this.atualizarStatus();
  }

  focar(ids = [...this.modelo.selecao]) {
    if (!ids.length) { this.viewport.enquadrarTudo(); return; }
    this.viewport.enquadrar(this.viewport.caixaDe(ids));
  }

  isolar() {
    const v = this.viewport;
    if (v.iso) { v.isolar(null); this.dicaViewport(null); return; }
    const sel = [...this.modelo.selecao];
    if (!sel.length) { this.dicaViewport('Selecione algo para isolar', 1600); return; }
    v.isolar(sel);
    const sair = el('button', { onclick: () => this.isolar() }, 'Sair');
    this.dicaViewport([el('span', { html: icone('isolar', 14) }), document.createTextNode(`Modo isolado: ${sel.length} item(ns) — `), sair, document.createTextNode(' ou /')], 0);
    this.focar(sel);
  }

  definirVisEditor(ids, vis) {
    this.modelo.definirVisEditor(ids, vis);
    this.props.agendar();
  }

  // o que foi escondido no editor volta escondido na próxima vez (por pasta + mundo)
  chaveVis(n) {
    const md = this.modelo;
    return n.chave || n.asset || `${n.tipo}:${n.nome}:${n.pai >= 0 ? (md.nos[n.pai].chave || md.nos[n.pai].asset || md.nos[n.pai].nome) : ''}`;
  }

  restaurarOcultosEditor(asset) {
    this.chaveOcultos = `ocultos:${(this.pastas || [])[0]}|${asset}`;
    const lista = new Set(PREF(this.chaveOcultos, []));
    this._nOcultos = 0;
    if (!lista.size) return;
    const ids = this.modelo.nos.filter((n) => lista.has(this.chaveVis(n))).map((n) => n.id);
    for (const id of ids) this.modelo.nos[id].visEditor = false;
    this._nOcultos = ids.length;
  }

  guardarOcultosEditor() {
    if (!this.chaveOcultos) return;
    GUARDA(this.chaveOcultos, this.modelo.nos.filter((n) => !n.visEditor).map((n) => this.chaveVis(n)));
  }

  ocultarSelecaoEditor(resto = false) {
    const md = this.modelo;
    const sel = [...md.selecao];
    if (!resto) { if (sel.length) md.definirVisEditor(sel, false); md.selecionar([]); return; }
    if (!sel.length) return;
    const manter = new Set();
    sel.forEach((id) => { manter.add(id); md.ancestrais(md.nos[id]).forEach((a) => manter.add(a.id)); md.descendentes(md.nos[id]).forEach((d) => manter.add(d.id)); });
    const esconder = md.nos.filter((n) => !manter.has(n.id) && n.pai >= 0 && manter.has(n.pai)).map((n) => n.id);
    md.definirVisEditor(esconder, false);
  }

  mostrarTudoEditor() {
    const md = this.modelo;
    md.definirVisEditor(md.nos.filter((n) => !n.visEditor).map((n) => n.id), true);
    if (this.viewport.iso) this.isolar();
  }

  definirJogo(ids, ocultar) {
    const md = this.modelo;
    const antes = new Map(), depois = new Map();
    const erros = [];
    let rebaixados = 0;
    for (const id of ids) {
      const n = md.nos[id];
      if (md.ocultoNoJogoProprio(n) === ocultar) continue;
      const r = md.estadoOcultar(n, ocultar);
      if (r.erro) { erros.push([n, r.erro]); continue; }
      antes.set(id, { jogo: { ...n.jogo }, local: n.local.slice() });
      depois.set(id, { jogo: r.jogo, local: r.local.slice() });
      if (r.rebaixado) rebaixados++;
    }
    if (erros.length) aviso(erros.length === 1 ? erros[0][1] : `${erros.length} itens não puderam ser ocultados no jogo`, { tipo: 'aviso', detalhe: erros.length > 1 ? erros[0][1] : erros[0][0].rotulo });
    if (!antes.size) return;
    const luzes = [...antes.keys()].every((id) => md.nos[id].tipo === 'luz');
    const nome = `${luzes ? (ocultar ? 'Apagar' : 'Acender') : (ocultar ? 'Ocultar' : 'Mostrar')} no jogo: ${antes.size > 1 ? antes.size + ' itens' : md.nos[[...antes.keys()][0]].rotulo}`;
    this.historico.executar({ nome, desfazer: () => md.definirJogo(antes), refazer: () => md.definirJogo(depois) });
    if (rebaixados) aviso(`${rebaixados} objeto(s) ligado(s) à lógica foram rebaixados 150 m em vez de excluídos`, { detalhe: 'Excluir algo que a lógica do jogo usa pode travar a partida.' });
  }

  alternarJogoSelecao() {
    const md = this.modelo;
    const ids = [...md.selecao].filter((i) => md.nos[i].jogo);
    if (!ids.length) { if (md.selecao.size) aviso('A seleção não tem itens que possam ser ocultados no jogo sozinhos', { tipo: 'aviso', detalhe: 'Selecione as cópias dentro de um grupo estático ou os objetos.' }); return; }
    const todosOcultos = ids.every((i) => md.ocultoNoJogoProprio(md.nos[i]));
    this.definirJogo(ids, !todosOcultos);
  }

  selecionarCopias(chaveMalha) {
    const md = this.modelo;
    const n = md.nos[md.ativo];
    if (!chaveMalha && n?.tipo === 'luz') {
      const ids = md.nos.filter((x) => x.tipo === 'luz' && x.pai === n.pai && x.luz?.tipo === n.luz?.tipo).map((x) => x.id);
      md.selecionar(ids);
      aviso(`${ids.length} luzes do mesmo tipo neste grupo selecionadas`, { tempo: 2000 });
      return;
    }
    if (!chaveMalha) {
      chaveMalha = n?.malhas?.[0]?.m;
      if (!chaveMalha) {
        if (n?.bp) { const ids = md.nos.filter((x) => x.bp === n.bp).map((x) => x.id); md.selecionar(ids); aviso(`${ids.length} cópias de ${n.nome} selecionadas`, { tempo: 2000 }); }
        return;
      }
    }
    const ids = md.nos.filter((x) => (x.malhas || []).some((p) => p.m === chaveMalha)).map((x) => x.id);
    md.selecionar(ids);
    aviso(`${ids.length} cópias de ${md.malhas[chaveMalha]?.nome || 'malha'} selecionadas`, { tempo: 2000 });
  }

  selecionarTudo() {
    const md = this.modelo;
    md.selecionar(md.nos.filter((n) => !ehGrupo(n) && md.visivelEditor(n) && (n.tipo !== 'luz' || this.viewport.mostrarLuzes)).map((n) => n.id));
  }

  inverterSelecao() {
    const md = this.modelo;
    md.selecionar(md.nos.filter((n) => !ehGrupo(n) && md.visivelEditor(n) && !md.selecao.has(n.id) && (n.tipo !== 'luz' || this.viewport.mostrarLuzes)).map((n) => n.id));
  }

  // ------------------------------------------------------------------ edições (com histórico)
  definirLocal(n, local, nome, fundir = true) {
    const md = this.modelo;
    const k = md.chaveDe(n);
    const antes = n.local.slice();
    const depois = local.slice();
    this.historico.executar({ nome, fundir: fundir ? 'local:' + k : null,
      desfazer: () => md.definirLocais(new Map([[k, antes]])), refazer: () => md.definirLocais(new Map([[k, depois]])) });
  }

  // prévia ao vivo (ferramentas): muda locais sem histórico
  aplicarLocaisPrevia(pares) {
    const md = this.modelo;
    md.definirLocais(new Map(pares.map(([n, local]) => [md.chaveDe(n), local])));
  }

  confirmarLocais(trios, nome) {
    const md = this.modelo;
    const antes = new Map(trios.map(([n, a]) => [md.chaveDe(n), a]));
    const depois = new Map(trios.map(([n, , d]) => [md.chaveDe(n), d]));
    this.historico.executar({ nome, desfazer: () => md.definirLocais(antes), refazer: () => md.definirLocais(depois) });
  }

  redefinirTransformacoes(nos) {
    const md = this.modelo;
    const antes = new Map(), depois = new Map();
    for (const n of nos) { const k = md.chaveDe(n); antes.set(k, n.local.slice()); depois.set(k, n.local0.slice()); }
    this.historico.executar({ nome: `Voltar ${nos.length} transformações`, desfazer: () => md.definirLocais(antes), refazer: () => md.definirLocais(depois) });
  }

  redefinirSelecao() {
    const md = this.modelo;
    const nos = [...md.selecao].map((i) => md.nos[i]).filter((n) => n.alvo && n.local.some((v, i) => Math.abs(v - n.local0[i]) > 1e-6));
    if (nos.length) this.redefinirTransformacoes(nos);
  }

  definirTextura(variacao, param, asset) {
    const md = this.modelo;
    const m = md.materiais.get(variacao);
    const antes = m.texturas[param];
    if (antes === asset) return;
    this.historico.executar({ nome: asset ? `Textura ${param}` : `Remover ${param}`, desfazer: () => md.definirTextura(variacao, param, antes), refazer: () => md.definirTextura(variacao, param, asset) });
  }

  definirVetor(variacao, param, v, fundir = false) {
    const md = this.modelo;
    const m = md.materiais.get(variacao);
    const antes = m.vetores[param].slice();
    this.historico.executar({ nome: `Valor ${param}`, fundir: fundir ? `vet:${variacao}:${param}` : null,
      desfazer: () => md.definirVetor(variacao, param, antes), refazer: () => md.definirVetor(variacao, param, v) });
  }

  alternarTexturaEditor(variacao, param) {
    const m = this.modelo.materiais.get(variacao);
    if (m.texOcultas.has(param)) m.texOcultas.delete(param); else m.texOcultas.add(param);
    this.modelo.emitir('material', { variacao });
  }

  async catalogoTexturas() {
    if (!this.catalogo) {
      const r = await api('texturas');
      this.catalogo = r.texturas;
      this.modelo.catalogo = new Map(r.texturas.map((t) => [t.asset, t]));
    }
    return this.catalogo;
  }

  async escolherTextura(variacao, param) {
    const m = this.modelo.materiais.get(variacao);
    let asset;
    try { asset = await D.escolherTextura(this, { param, atual: m.texturas[param] }); } catch (e) { aviso(e.message, { tipo: 'erro' }); return; }
    if (!asset) return;
    this.definirTextura(variacao, param, asset);
  }

  async escolherMaterialOrigem(variacao) {
    const origem = await D.escolherMaterialOrigem(this, variacao);
    if (!origem) return;
    const md = this.modelo;
    const antes = md.fotoMaterial(variacao);
    md.copiarMaterial(variacao, origem);
    const depois = md.fotoMaterial(variacao);
    md.restaurarMaterial(variacao, antes);
    this.historico.executar({ nome: 'Copiar material', desfazer: () => md.restaurarMaterial(variacao, antes), refazer: () => md.restaurarMaterial(variacao, depois) });
    aviso('Material copiado', { tipo: 'sucesso', detalhe: 'Agora dá para trocar a textura dele. Salve (Ctrl+S) para gravar no MVDB.' });
  }

  // malha sem entrada no MVDB do próprio sub-mundo (asset novo): cria a entrada, com o shader e as texturas
  // da mesma malha em outro MVDB do export (se houver) ou de um material escolhido
  async criarEntradaMvdb(n, chave) {
    const md = this.modelo;
    const ent = md.mvdbs[n.mvdb];
    if (!ent?.arq) { aviso('O MeshVariationDb deste sub-mundo não está no export', { tipo: 'erro' }); return; }
    const info = md.malhas[chave] || {};
    const { lista, mvdb } = md.materiaisDe(n, chave);
    let origens;
    if (lista && mvdb !== n.mvdb && md.mvdbs[mvdb]?.arq) {
      const ok = await confirmar('Criar entrada no MVDB deste sub-mundo?',
        `<b>${esc(info.nome || chave)}</b> ganha uma entrada própria no MeshVariationDb de <b>${esc(n.mvdb.split('/').slice(-2, -1)[0] || '')}</b>, com os mesmos shaders e texturas que ela tem em <i>${esc(mvdb.split('/').slice(-2, -1)[0] || '')}</i>. Depois dá para trocar textura e shader de cada seção. O arquivo é gravado na hora (o original fica em <i>_editor_originais</i>).`,
        { rotulo: 'Criar entrada' });
      if (!ok) return;
      origens = lista.map((m) => ({ arq: md.mvdbs[mvdb].arq, variacao: m.variacao }));
    } else {
      aviso('Escolha o material de partida', { detalhe: 'Todas as seções da malha começam com o shader e as texturas dele; depois dá para trocar cada uma.', tempo: 5000 });
      const origem = await D.escolherMaterialOrigem(this, null, ent.arq);
      if (!origem) return;
      const o = md.materiais.get(origem);
      origens = [{ arq: o.arq, variacao: origem }];
    }
    this.carregando('Criando a entrada no MeshVariationDb…', info.nome || chave, -1);
    try {
      const r = await api('mvdb_entrada', { mvdb: n.mvdb, malha: chave, origens });
      md.adicionarEntradaMvdb(n.mvdb, chave, r.materiais, r.texturas);
      await this.viewport.recarregarMalha(chave);
      this.carregando(null);
      this.props.agendar();
      aviso('Entrada criada no MeshVariationDb', { tipo: 'sucesso', tempo: 7000,
        detalhe: `${r.materiais.length} material(is) de ${info.nome || chave}. Troque texturas/shader nas seções e importe o ${r.arq.split('/').pop()} no FET.` });
    } catch (e) {
      this.carregando(null);
      aviso('Não consegui criar a entrada', { tipo: 'erro', detalhe: e.message });
    }
  }

  async adicionarParametroTextura(variacao) {
    const param = await D.escolherParametro(this, variacao);
    if (!param) return;
    await this.escolherTextura(variacao, param);
  }

  realcarSecao(alvo) {
    const v = this.viewport;
    for (const o of v.realces || []) o.removeFromParent();
    v.realces = [];
    if (!alvo) { v.sujo = true; return; }
    const mat = v.matRealce || (v.matRealce = new THREE.MeshBasicMaterial({ color: 0x4c8dff, transparent: true, opacity: 0.45, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3, side: THREE.DoubleSide }));
    v.objs[alvo.no]?.userData.pecasObj.traverse((o) => {
      if (o.isMesh && o.userData.malha === alvo.malha && o.userData.nomeSecao === alvo.secao && !o.userData.overlay) {
        const s = new THREE.Mesh(o.geometry, mat);
        s.userData.overlay = true; s.matrixAutoUpdate = false; s.raycast = () => {}; s.renderOrder = 6;
        o.add(s); s.updateMatrixWorld(true); v.realces.push(s);
      }
    });
    v.sujo = true;
  }

  desfazer() {
    const c = this.historico.desfazer();
    if (c) this.dicaViewport(`Desfeito: ${c.nome}`, 1500);
  }

  refazer() {
    const c = this.historico.refazer();
    if (c) this.dicaViewport(`Refeito: ${c.nome}`, 1500);
  }

  // ------------------------------------------------------------------ mover livre (G)
  iniciarMoverLivre() {
    if (!this.carregado) return;
    const m = this.viewport.ultimoMouse;
    if (!this.viewport.iniciarMoverLivre(m?.x, m?.y)) {
      this.dicaViewport(this.modelo.selecao.size ? 'A seleção não tem objetos que possam ser movidos' : 'Selecione algo para mover (G)', 1800);
    }
  }

  aoMoverLivre(d) {
    if (!d) { this.dicaViewport(null); this.atualizarStatus(); return; }
    const eixo = d.trava ? (d.plano ? `plano sem ${d.trava.toUpperCase()}` : `eixo ${d.trava.toUpperCase()}`) : 'livre';
    const txt = `Mover (${eixo}): ${d.delta.x.toFixed(2)}, ${d.delta.y.toFixed(2)}, ${d.delta.z.toFixed(2)} m · X/Y/Z trava · Shift+eixo trava plano · clique/Enter confirma · Esc cancela`;
    $('#status-dica').textContent = txt;
    this.dicaViewport(`Mover ${eixo}: ${Math.hypot(d.delta.x, d.delta.y, d.delta.z).toFixed(2)} m`, 0);
  }

  // ------------------------------------------------------------------ salvar
  async salvar() {
    if (this.salvando) return;
    const alts = this.modelo.pendentes();
    if (!alts.length) { aviso('Nada para salvar', { tempo: 1600 }); return; }
    this.salvando = true;
    this.carregando('Gravando alterações…', `${alts.filter((a) => a.tipo !== 'lightmap').length} alterações`, -1);
    try {
      const r = await api('salvar', { alteracoes: alts });
      this.modelo.confirmarGravado(r.novas || {});
      this.carregando(null);
      const nomes = r.arquivos.map((a) => a.split('/').pop());
      aviso(`${r.arquivos.length} arquivo${r.arquivos.length !== 1 ? 's' : ''} gravado${r.arquivos.length !== 1 ? 's' : ''}`, {
        tipo: 'sucesso', tempo: 7000,
        detalhe: `${nomes.slice(0, 4).join(', ')}${nomes.length > 4 ? ` e mais ${nomes.length - 4}` : ''}${r.lightmap ? ` · ${r.lightmap} entrada(s) de iluminação atualizadas` : ''}. Importe-os no FET.`,
        acao: { rotulo: 'Ver lista', fn: () => this.abrirAlteracoes() },
      });
      if (r.erros.length) aviso('Algumas alterações não foram aplicadas', { tipo: 'erro', detalhe: r.erros.slice(0, 5).join(' · ') });
      this.autosalvar(false, true);
    } catch (e) {
      this.carregando(null);
      aviso('Não foi possível salvar', { tipo: 'erro', detalhe: e.message });
    }
    this.salvando = false;
  }

  abrirAlteracoes() {
    if (!this.pastas) { aviso('Abra uma pasta primeiro'); return; }
    D.dialogoAlteracoes(this);
  }

  dialogoRenomear() {
    if (!this.carregado) { aviso('Abra um estádio primeiro'); return; }
    D.dialogoRenomear(this);
  }

  async explorer(id) {
    try { await api('explorer', { id }); } catch (e) { aviso(e.message, { tipo: 'erro' }); }
  }

  async capturar() {
    const blob = await this.viewport.capturar();
    const a = el('a', { href: URL.createObjectURL(blob), download: `${this.modelo.nos[0]?.nome || 'estadio'}_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png` });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  // ------------------------------------------------------------------ substituir FBX / PNG
  async substituirFBX(chave) {
    const info = this.modelo.malhas[chave];
    const atual = this.viewport.geos.get(chave);
    const arq = await arquivoLocal('.fbx');
    if (!arq) return;
    const buf = await arq.arrayBuffer();
    let novo;
    try { novo = await lerFBX(buf.slice(0)); } catch (e) {
      aviso('Não consegui ler esse FBX', { tipo: 'erro', detalhe: `${e.message}. Exporte do Blender como FBX binário (o padrão).` });
      return;
    }
    const a = atual ? atual.secoes : [], b = novo.secoes;
    const tabela = el('table', { class: 'comparacao' });
    tabela.innerHTML = '<tr><th>#</th><th>Seção atual</th><th>Seção nova</th><th>Triângulos</th></tr>';
    const n = Math.max(a.length, b.length);
    for (let i = 0; i < n; i++) {
      const x = a[i], y = b[i];
      const ok = x && y && (!!x.sombra === !!y.sombra);
      tabela.innerHTML += `<tr><td>${i}</td><td>${x ? esc(x.nome) : '—'}</td><td class="${ok ? 'ok' : 'ruim'}">${y ? esc(y.nome) : '—'}</td><td>${x ? fmtInt(x.triangulos) : '—'} → ${y ? fmtInt(y.triangulos) : '—'}</td></tr>`;
    }
    const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
    corpo.append(nota('O FET liga as seções do FBX às do asset <b>pela ordem</b>, não pelo nome. Mantenha a mesma quantidade e ordem (incluindo as seções <i>_Shadow</i>).'));
    if (a.length !== b.length) corpo.append(nota(`Quantidade de seções diferente (${a.length} → ${b.length}). O FET pode recusar o arquivo ou trocar os materiais.`, 'alerta'));
    if (novo.lods > 1 || (atual && atual.lods > 1)) corpo.append(nota(`LODs: atual ${atual?.lods || 1}, novo ${novo.lods || 1}. O editor mostra só o LOD0.`));
    corpo.append(tabela);
    const ok = await modal({ titulo: 'Substituir o FBX da malha?', texto: `<b>${esc(info.nome)}</b> ← ${esc(arq.name)}`, corpo, largo: true,
      botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Substituir', classe: 'btn-primario', padrao: true, valor: true }] }).promessa;
    if (!ok) return;
    try {
      const dados = await blobParaBase64(new Blob([buf]));
      await api('substituir', { id: info.fbx, dados });
      await this.viewport.recarregarMalha(chave);
      this.props.agendar();
      aviso('FBX substituído', { tipo: 'sucesso', detalhe: `${info.fbx.split('/').pop()} gravado (original em _editor_originais). Importe-o no FET sobre a malha.` });
    } catch (e) { aviso('Falha ao substituir o FBX', { tipo: 'erro', detalhe: e.message }); }
  }

  // ------------------------------------------------------------------ mesh zero (malhas removidas do jogo)
  // Malha "zerada": um triângulo de 1 mm por seção. O objeto continua removido (Excluded / 150 m abaixo) e o 3D
  // original deixa de pesar no estádio depois de importado no FET.
  malhaZerada(chave) {
    const geo = this.viewport.geos.get(chave);
    return !!geo?.secoes?.length && geo.secoes.every((s) => s.triangulos <= 1);
  }

  candidatosMeshZero() {
    const md = this.modelo;
    const usos = new Map();
    for (const n of md.nos) {
      for (const p of n.malhas || []) {
        if (!usos.has(p.m)) usos.set(p.m, { total: 0, ocultos: 0 });
        const u = usos.get(p.m);
        u.total++;
        if (n.removido || md.ocultoNoJogo(n)) u.ocultos++;
      }
    }
    // malha "deste estádio": o caminho tem o nome do mundo (sem o número), ex.: components/stadiums/pro_stadium_tier1/
    const mundo = (md.mundo || '').toLowerCase().split('/').pop();
    const base = mundo.replace(/_\d+$/, '');
    const out = [];
    for (const [chave, u] of usos) {
      if (u.ocultos !== u.total) continue;
      const info = md.malhas[chave] || {};
      const asset = (info.asset || chave).toLowerCase();
      const geo = this.viewport.geos.get(chave);
      out.push({
        chave, info, copias: u.total, fbx: info.fbx || null, zerada: this.malhaZerada(chave),
        proprio: !!base && (asset.includes(`/${base}/`) || asset.includes(`/${mundo}/`)),
        triangulos: geo ? geo.secoes.reduce((a, s) => a + s.triangulos, 0) : null,
      });
    }
    out.sort((a, b) => (b.triangulos || 0) - (a.triangulos || 0));
    const parciais = [...usos.values()].filter((u) => u.ocultos && u.ocultos < u.total).length;
    return { lista: out, parciais };
  }

  async dialogoMeshZero(chaves = null) {
    const { lista: todos, parciais } = this.candidatosMeshZero();
    const lista = chaves ? todos.filter((c) => chaves.includes(c.chave)) : todos;
    if (!lista.length) {
      aviso(chaves ? 'Esta malha ainda aparece no jogo' : 'Nenhuma malha removida do jogo', { tipo: 'aviso',
        detalhe: chaves ? 'O mesh zero só vale para malhas que estão ocultas no jogo em todas as cópias deste estádio.'
          : 'Oculte objetos no jogo (Del) e depois aplique o mesh zero neles.' });
      return;
    }
    const marcados = new Set(lista.filter((c) => c.fbx && !c.zerada && (c.proprio || chaves)).map((c) => c.chave));
    const corpo = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '10px' } });
    corpo.append(nota('Troca o FBX de cada malha por um <b>mesh zero</b> (um triângulo de 1 mm por seção, mesmas seções, partes e materiais). O objeto continua removido do jogo e o 3D original deixa de pesar no estádio. O FBX original fica em <i>_editor_originais</i> e volta em <b>Alterações</b>.'));
    const lst = el('div', { class: 'lista', style: { maxHeight: '380px' } });
    const botao = () => mm.caixa.querySelector('.btn-primario');
    const atualizar = () => { const b = botao(); if (b) { b.disabled = !marcados.size; b.textContent = `Aplicar mesh zero (${marcados.size})`; } };
    for (const c of lista) {
      const pode = c.fbx && !c.zerada;
      const cx = el('input', { type: 'checkbox', disabled: !pode });
      cx.checked = marcados.has(c.chave);
      cx.onchange = () => { cx.checked ? marcados.add(c.chave) : marcados.delete(c.chave); atualizar(); };
      const det = [`${fmtInt(c.copias)} cópia${c.copias > 1 ? 's' : ''}`];
      if (c.triangulos !== null) det.push(`${fmtInt(c.triangulos)} triângulos`);
      if (c.zerada) det.push('já zerada');
      else if (!c.fbx) det.push('FBX não exportado');
      else if (!c.proprio) det.push('pode ser usada por outros estádios (o FBX é o mesmo em todos)');
      const it = el('label', { class: 'lista-item', style: { opacity: pode ? '' : '0.55' } }, cx,
        el('div', { class: 'txt' }, el('b', {}, c.info.nome || c.chave.split('/').pop()), el('small', { title: c.info.asset || '' }, det.join(' · '))));
      lst.append(it);
    }
    corpo.append(lst);
    if (lista.some((c) => c.fbx && !c.zerada && !c.proprio)) corpo.append(nota('Malhas fora da pasta deste estádio podem ser usadas por outros mundos: zerar o FBX delas some com o objeto em todos. Por isso vêm desmarcadas.', 'alerta'));
    if (!chaves && parciais) corpo.append(nota(`${fmtInt(parciais)} malha(s) ficaram de fora porque ainda têm cópias visíveis no jogo.`));
    if (this.modelo.pendentes().length) corpo.append(nota('Há alterações não salvas: salve também (<kbd>Ctrl+S</kbd>) para gravar a remoção dos objetos.', 'alerta'));
    const mm = modal({ titulo: 'Mesh zero nos removidos do jogo', corpo, largo: true,
      botoes: [{ rotulo: 'Cancelar', valor: null }, { rotulo: 'Aplicar mesh zero', classe: 'btn-primario', padrao: true, fn: () => [...marcados] }] });
    atualizar();
    const escolhidas = await mm.promessa;
    if (!escolhidas?.length) return;
    const porId = new Map(lista.map((c) => [c.fbx, c]));
    this.carregando('Aplicando mesh zero…', `${escolhidas.length} malha(s)`, -1);
    let r;
    try { r = await api('mesh_zero', { ids: escolhidas.map((k) => this.modelo.malhas[k].fbx) }); } catch (e) { this.carregando(null); aviso('Falha no mesh zero', { tipo: 'erro', detalhe: e.message }); return; }
    for (const f of r.feitos) {
      const c = porId.get(f.id);
      if (c) { try { await this.viewport.recarregarMalha(c.chave); } catch { /* a malha recarrega ao abrir de novo */ } }
    }
    this.carregando(null);
    this.props.agendar();
    const antes = r.feitos.reduce((a, f) => a + f.antes, 0), depois = r.feitos.reduce((a, f) => a + f.depois, 0);
    if (r.feitos.length) {
      aviso(`Mesh zero em ${r.feitos.length} malha${r.feitos.length > 1 ? 's' : ''}`, { tipo: 'sucesso', tempo: 8000,
        detalhe: `FBX de ${(antes / 1048576).toFixed(1)} MB para ${(depois / 1048576).toFixed(1)} MB. Importe os FBX no FET sobre as malhas.`,
        acao: { rotulo: 'Ver lista', fn: () => this.abrirAlteracoes() } });
    }
    if (r.erros.length) aviso('Algumas malhas não foram zeradas', { tipo: 'erro', detalhe: r.erros.slice(0, 5).join(' · ') });
  }

  async substituirImagem(asset) {
    const t = this.modelo.texturas[asset];
    if (!t?.png) return;
    const arq = await arquivoLocal('image/png,image/jpeg,image/webp,image/bmp');
    if (!arq) return;
    const carregar = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
    try {
      const orig = await carregar(urlArquivo(t.png));
      const nova = await carregar(URL.createObjectURL(arq));
      const W = orig.naturalWidth, H = orig.naturalHeight;
      const ajustar = nova.naturalWidth !== W || nova.naturalHeight !== H;
      if (ajustar && !await confirmar('Ajustar o tamanho?', `A textura original tem <b>${W}×${H}</b> e a imagem nova <b>${nova.naturalWidth}×${nova.naturalHeight}</b>. Ela será redimensionada para ${W}×${H}.`, { rotulo: 'Redimensionar e substituir' })) return;
      const cv = el('canvas', { width: W, height: H });
      const ctx = cv.getContext('2d');
      ctx.drawImage(nova, 0, 0, W, H);
      const blob = await new Promise((res) => cv.toBlob(res, 'image/png'));
      await api('substituir', { id: t.png, dados: await blobParaBase64(blob) });
      t.versao = Date.now();
      this.materiais.recarregarTextura(asset);
      this.viewport.recriarMateriais();
      this.props.agendar();
      aviso('Imagem substituída', { tipo: 'sucesso', detalhe: `${t.png.split('/').pop()} (${W}×${H}). No FET, importe o PNG sobre a textura ${asset.split('/').pop()}.` });
    } catch (e) { aviso('Falha ao substituir a imagem', { tipo: 'erro', detalhe: e.message || String(e) }); }
  }

  // ------------------------------------------------------------------ torcida (alterações pendentes, com desfazer)
  async carregarTorcida() {
    const md = this.modelo;
    if (md.torcida) return md.torcida;
    const nuvem = md.nuvens?.[0];
    if (!nuvem) return null;
    if (!nuvem.arq) { aviso('A nuvem de assentos não está no export', { tipo: 'aviso', detalhe: nuvem.asset }); return null; }
    this.dicaViewport('Carregando assentos da torcida…', 0);
    try {
      const dados = await api('torcida', { arq: nuvem.arq });
      md.torcida = { arq: nuvem.arq, nome: nuvem.nome, original: dados, atual: dados };
      this.dicaViewport(`${fmtInt(dados.n)} assentos`, 1500);
      return md.torcida;
    } catch (e) { this.dicaViewport(null); aviso(e.message, { tipo: 'erro' }); return null; }
  }

  async alternarTorcida(v) {
    const md = this.modelo;
    if (!md.nuvens?.length) return;
    if (v && !(await this.carregarTorcida())) return;
    const t = this.estadoTorcida = this.estadoTorcida || { visivel: false, modoCor: 'SeatColor' };
    t.visivel = v;
    if (v) this.redesenharTorcida();
    else { this.viewport.mostrarTorcida(null); if (this.viewport.ferramentaCaixa === 'torcida') this.sairFerramentaTorcida(); }
    this.atualizarBarraVista();
    this.props.agendar();
  }

  redesenharTorcida() {
    const md = this.modelo;
    if (!md.torcida || !this.estadoTorcida?.visivel) return;
    this.viewport.mostrarTorcida(md.torcida.atual, this.estadoTorcida.modoCor);
    this.viewport.torcida.userData.marcados = this.marcados;
    this.viewport.colorirTorcida(this.estadoTorcida.modoCor);
  }

  redesenharMarcados() {
    if (this.viewport.torcida) { this.viewport.torcida.userData.marcados = this.marcados; this.viewport.colorirTorcida(this.estadoTorcida?.modoCor || 'SeatColor'); }
    this.aoMudarTorcida && this.aoMudarTorcida();
  }

  aoAlterarTorcida() {
    this.redesenharTorcida();
    this.aoMudarTorcida && this.aoMudarTorcida();
    this.atualizarPendentes();
  }

  alterarTorcida(novo, nome) {
    const md = this.modelo;
    const antes = md.torcida.atual;
    this.historico.executar({ nome, desfazer: () => { this.marcados = new Set(); md.definirTorcida(antes); }, refazer: () => { md.definirTorcida(novo); } });
  }

  colorirTorcida(modo) {
    this.estadoTorcida = this.estadoTorcida || { visivel: false, modoCor: modo };
    this.estadoTorcida.modoCor = modo;
    this.viewport.colorirTorcida(modo);
  }

  async abrirPainelTorcida() {
    if (painelAberto()?.el?.getAttribute('aria-label') === 'Torcida') { fecharPainel(); return; }
    if (!this.estadoTorcida?.visivel) await this.alternarTorcida(true);
    if (this.modelo.torcida) F.abrirTorcida(this);
  }

  ferramentaTorcida() {
    this.viewport.ferramentaCaixa = 'torcida';
    const sair = el('button', { onclick: () => this.sairFerramentaTorcida() }, 'Concluir');
    this.dicaViewport([el('span', { html: icone('torcida', 14) }), document.createTextNode('Arraste caixas sobre os assentos para marcá-los (Shift desmarca) · '), sair], 0);
  }

  sairFerramentaTorcida() {
    this.viewport.ferramentaCaixa = this.ferramentaCaixaAtiva ? 'objetos' : null;
    this.dicaViewport(null);
  }

  marcarAssentos({ dentro, shift }) {
    const t = this.modelo.torcida;
    if (!t) return;
    const p = t.atual.posicoes;
    const v = new THREE.Vector3();
    const raiz = this.viewport.raiz.matrixWorld;
    for (let i = 0; i < t.atual.n; i++) {
      v.set(p[i * 3], p[i * 3 + 1], p[i * 3 + 2]).applyMatrix4(raiz);
      if (dentro(v)) { if (shift) this.marcados.delete(i); else this.marcados.add(i); }
    }
    this.redesenharMarcados();
    this.dicaViewport([el('span', { html: icone('torcida', 14) }), document.createTextNode(`${fmtInt(this.marcados.size)} assentos marcados · `), el('button', { onclick: () => this.sairFerramentaTorcida() }, 'Concluir')], 0);
  }

  ferramentaRemapear() {
    if (!this.carregado) return;
    F.abrirRemapear(this);
  }

  async ferramentaGerarAssentos() {
    if (!this.carregado) return;
    if (!(await this.carregarTorcida())) { aviso('Este estádio não tem a nuvem de assentos no export', { tipo: 'aviso' }); return; }
    F.abrirGerarAssentos(this);
  }

  // ------------------------------------------------------------------ luzes: criar, duplicar, excluir, apontar, editar
  ferramentaLuzes() {
    if (!this.carregado) return;
    F.abrirLuzes(this);
  }

  // luz que serve de modelo para as novas: a selecionada, a escolhida no painel ou o spot mais comum da cobertura
  modeloLuz() {
    const md = this.modelo;
    const sel = md.nos[md.ativo];
    if (sel?.tipo === 'luz' && !sel.removido) return sel;
    if (this.modeloLuzId !== undefined && md.nos[this.modeloLuzId] && !md.nos[this.modeloLuzId].removido) return md.nos[this.modeloLuzId];
    const luzes = md.nos.filter((n) => n.tipo === 'luz' && !n.removido && n.alvo && !n.aninhado);
    const cobertura = luzes.filter((n) => n.luz?.tipo === 'spot' && /roof/i.test(n.alvo.arq));
    return cobertura[0] || luzes.find((n) => n.luz?.tipo === 'spot') || luzes[0] || null;
  }

  // matriz de mundo de uma luz em 'pos' apontando para 'alvo' (eixo +Z do Frostbite = para onde o spot ilumina)
  matrizLuz(pos, alvo, base = null) {
    const f = alvo ? new THREE.Vector3().subVectors(alvo, pos).normalize() : new THREE.Vector3(0, -1, 0);
    if (!alvo && base) {   // mesma rotação do modelo
      const m = new THREE.Matrix4().extractRotation(base);
      return m.setPosition(pos);
    }
    let up = new THREE.Vector3(0, 1, 0);
    if (Math.abs(f.dot(up)) > 0.98) up = new THREE.Vector3(0, 0, 1);
    const r = new THREE.Vector3().crossVectors(up, f).normalize();
    const u = new THREE.Vector3().crossVectors(f, r).normalize();
    return new THREE.Matrix4().makeBasis(r, u, f).setPosition(pos);
  }

  // cria a luz (nó novo) a partir do modelo, com matriz de mundo W; devolve o nó
  criarLuz(modelo, W, nome) {
    const md = this.modelo;
    const P = modelo.pai >= 0 ? md.nos[modelo.pai].mundoM : new THREE.Matrix4();
    const local = m12De(new THREE.Matrix4().multiplyMatrices(P.clone().invert(), W));
    md.nNovas++;
    const TIPO = { spot: 'Spot', esfera: 'Pontual', tubo: 'Tubo', retangulo: 'Retangular' };
    const n = md.adicionarNo({
      pai: modelo.pai, tipo: 'luz', nome: nome || `${TIPO[modelo.luz?.tipo] || 'Luz'} nova #${md.nNovas}`, local, nova: true,
      chaveNova: `n${Date.now().toString(36)}_${md.nNovas}`, aninhado: modelo.aninhado, compartilhado: modelo.compartilhado,
      alvo: { arq: modelo.alvo.arq, guid: null, campo: 'Transform', modelo: modelo.nova ? modelo.alvo.modelo : modelo.alvo.guid },
      jogo: { habilitada: true }, luz: JSON.parse(JSON.stringify(modelo.luz || {})), luz0: JSON.parse(JSON.stringify(modelo.luz || {})),
    });
    return n;
  }

  registrarCriadas(ids, nome) {
    const md = this.modelo;
    this.historico.executar({ nome, refazer: () => md.definirRemovidos(ids, false), desfazer: () => md.definirRemovidos(ids, true) });
    if (!this.viewport.mostrarLuzes) this.alternarLuzes(true);
  }

  // clique na vista no modo "adicionar": a luz nasce encostada na superfície, apontando conforme o painel
  adicionarLuzNoPonto(x, y, opc) {
    const md = this.modelo, v = this.viewport;
    const modelo = this.modeloLuz();
    if (!modelo) { aviso('Este estádio não tem nenhuma luz para servir de modelo', { tipo: 'aviso' }); return null; }
    const hit = v.pontoNaCena(x, y);
    if (!hit) return null;
    const pos = hit.ponto.clone().addScaledVector(hit.normal, opc.afastar ?? 0.3);
    const alvo = opc.mirar === 'centro' ? new THREE.Vector3(0, 0, 0) : opc.mirar === 'baixo' ? pos.clone().add(new THREE.Vector3(0, -1, 0))
      : opc.mirar === 'normal' ? pos.clone().add(hit.normal) : null;
    const W = this.matrizLuz(pos, alvo, modelo.mundoM);
    // reaproveitar uma luz apagada do mesmo tipo e arquivo (não cria entidade nova)
    if (opc.reaproveitar) {
      const livre = md.nos.find((n) => n.tipo === 'luz' && !n.nova && !n.removido && n.alvo && n.jogo?.habilitada === false
        && n.jogo0?.habilitada === false && n.alvo.arq === modelo.alvo.arq && n.luz?.tipo === modelo.luz?.tipo && !n.ligado && !n.aninhado);
      if (livre) {
        const k = md.chaveDe(livre);
        const antesL = livre.local.slice(), depoisL = md.localPara(livre, W);
        const antesJ = new Map([[livre.id, { jogo: { ...livre.jogo }, local: antesL }]]);
        const depoisJ = new Map([[livre.id, { jogo: { ...livre.jogo, habilitada: true }, local: depoisL }]]);
        this.historico.executar({ nome: `Reaproveitar ${livre.nome}`, refazer: () => { md.definirJogo(depoisJ); md.definirLocais(new Map([[k, depoisL]])); },
          desfazer: () => { md.definirJogo(antesJ); md.definirLocais(new Map([[k, antesL]])); } });
        if (!v.mostrarLuzes) this.alternarLuzes(true);
        return livre;
      }
    }
    const n = this.criarLuz(modelo, W);
    this.registrarCriadas([n.id], `Adicionar ${n.nome}`);
    return n;
  }

  entrarModoLuz(cfg) {
    this.sairModoLuz();
    this.modoLuz = cfg;
    this.viewport.canvas.style.cursor = 'crosshair';
    const sair = el('button', { onclick: () => this.sairModoLuz() }, 'Concluir');
    this.dicaViewport([el('span', { html: icone(cfg.icone || 'luzMais', 14) }), document.createTextNode(cfg.msg + ' · Esc termina · '), sair], 0);
    this.atualizarStatus();
  }

  sairModoLuz() {
    if (!this.modoLuz) return;
    const cb = this.modoLuz.aoSair;
    this.modoLuz = null;
    this.viewport.canvas.style.cursor = '';
    this.dicaViewport(null);
    this.atualizarStatus();
    cb && cb();
  }

  luzesSelecionadas() {
    const md = this.modelo;
    return [...md.selecao].map((i) => md.nos[i]).filter((n) => n.tipo === 'luz' && !n.removido && n.alvo);
  }

  duplicarLuzes() {
    const md = this.modelo;
    const luzes = this.luzesSelecionadas();
    if (!luzes.length) { if (md.selecao.size) this.dicaViewport('Ctrl+D duplica luzes; selecione uma luz', 1800); return; }
    const novas = luzes.map((n) => {
      const W = n.mundoM.clone().premultiply(new THREE.Matrix4().makeTranslation(1, 0, 0));
      const c = this.criarLuz(n, W);
      c.luzTocada = Object.fromEntries(Object.keys(c.luz || {}).map((k) => [k, true]));   // a cópia leva cor/intensidade atuais
      return c;
    });
    this.registrarCriadas(novas.map((n) => n.id), `Duplicar ${luzes.length > 1 ? luzes.length + ' luzes' : luzes[0].nome}`);
    md.selecionar(novas.map((n) => n.id));
    this.dicaViewport('Cópia criada 1 m ao lado · use G para levar ao lugar', 2500);
  }

  excluirLuzes() {
    const md = this.modelo;
    const luzes = this.luzesSelecionadas();
    if (!luzes.length) return;
    const ligadas = luzes.filter((n) => n.ligado);
    if (ligadas.length) {
      aviso(`${ligadas.length} luz(es) estão ligadas à lógica do jogo (show de luzes etc.)`, { tipo: 'aviso', detalhe: 'Essas não podem ser excluídas; use “Acesa no jogo” para apagá-las.' });
    }
    const ids = luzes.filter((n) => !n.ligado).map((n) => n.id);
    if (!ids.length) return;
    this.historico.executar({ nome: `Excluir ${ids.length > 1 ? ids.length + ' luzes' : md.nos[ids[0]].nome}`,
      refazer: () => md.definirRemovidos(ids, true), desfazer: () => md.definirRemovidos(ids, false) });
  }

  apontarLuzes(alvo, luzes = this.luzesSelecionadas()) {
    const md = this.modelo;
    if (!luzes.length) return;
    const trios = luzes.map((n) => {
      const pos = new THREE.Vector3().setFromMatrixPosition(n.mundoM);
      return [n, n.local.slice(), md.localPara(n, this.matrizLuz(pos, alvo))];
    });
    this.confirmarLocais(trios, `Apontar ${luzes.length > 1 ? luzes.length + ' luzes' : luzes[0].nome}`);
  }

  alterarLuzes(ids, mudancas, nome, fundir = null) {
    const md = this.modelo;
    const antes = new Map(ids.map((id) => [id, JSON.parse(JSON.stringify(md.nos[id].luz))]));
    const depois = new Map(ids.map((id) => [id, { ...md.nos[id].luz, ...mudancas }]));
    this.historico.executar({ nome, fundir, desfazer: () => md.definirLuzes(antes), refazer: () => md.definirLuzes(depois) });
  }

  definirAncoraEscala(modo) {
    this.viewport.ancoraEscala = modo;
    GUARDA('ancoraEscala', modo);
    this.viewport.posicionarPivo();
    this.viewport.sujo = true;
    this.dicaViewport({ chao: 'Escala a partir do chão do campo: o piso fica no chão', base: 'Escala a partir da base do objeto', centro: 'Escala a partir do centro', origem: 'Escala a partir da origem do objeto' }[modo], 1800);
  }

  // ------------------------------------------------------------------ cor sólida num material
  // Textura de cor = branca padrão do jogo + cor de tinta do shader (tintColor...). Sem tinta no shader: copia antes um
  // material do mesmo sub-mundo que tenha tinta (ex.: worlds_tint_multiply). Tudo num passo só de desfazer.
  async corSolida(variacao) {
    const md = this.modelo;
    const reg = md.materiais.get(variacao);
    if (!reg) return;
    const BRANCA = 'content/worlds/textures/default/default_white_color';
    const temTinta = (m) => Object.entries(m.base.vetores || {}).find(([k, x]) => /color/i.test(x.tipo || '') && /tint|albedo|basecolor/i.test(k))?.[0];
    let tinta = temTinta(reg);
    let origem = null;
    if (!tinta) {
      const cands = [...md.materiais.values()].filter((m) => m.arq === reg.arq && m.variacao !== variacao && temTinta(m) && Object.keys(m.base.texturas).some((p) => PARAM_COR_MAIN.includes(p)));
      origem = cands.find((m) => /tint_multiply/i.test(m.base.shader || '')) || cands[0];
      if (!origem) { aviso('Nenhum material deste sub-mundo tem cor de tinta para copiar', { tipo: 'aviso', detalhe: 'Use “Copiar material de…” com um material de outro sub-mundo e tente de novo.' }); return; }
    }
    const atual = tinta ? (reg.vetores[tinta] || reg.base.vetores[tinta].v) : null;
    const corIni = atual ? '#' + new THREE.Color(atual[0], atual[1], atual[2]).getHexString(THREE.SRGBColorSpace) : '#d32f2f';
    const inp = el('input', { type: 'color', value: corIni, style: { width: '100%', height: '44px' } });
    const corpo = el('div', { class: 'pf-sec' }, inp,
      nota(origem ? `Este material não tem cor de tinta: antes, ele vai copiar o shader de <b>${esc(nomeCurtoMain(origem.malha))}</b> (${esc(origem.base.shader || '')}), do mesmo sub-mundo.`
        : `A textura de cor vira a <b>branca padrão</b> do jogo e a cor vai para <b>${esc(tinta)}</b>. Os relevos (normal) continuam.`));
    const ok = await modal({ titulo: 'Cor sólida', corpo, botoes: [{ rotulo: 'Cancelar', classe: 'btn', valor: false }, { rotulo: 'Aplicar', classe: 'btn-primario', valor: true, padrao: true }] }).promessa;
    if (!ok) return;
    if (!md.texturas[BRANCA]) {
      try {
        const g = await api('jogo_guids', { asset: BRANCA });
        md.texturas[BRANCA] = { png: null, ref: g.ref, pguid: g.pguid, jogo: true, nome: g.asset };
      } catch (e) { aviso('Preciso do FC 26 conectado para usar a textura branca padrão', { tipo: 'erro', detalhe: e.message }); return; }
    }
    const c = new THREE.Color().setStyle(inp.value, THREE.SRGBColorSpace);
    const antes = md.fotoMaterial(variacao);
    if (origem) md.copiarMaterial(variacao, origem.variacao);
    tinta = tinta || temTinta(md.materiais.get(variacao));
    const m = md.materiais.get(variacao);
    const paramCor = Object.keys(m.texturas).find((p) => PARAM_COR_MAIN.includes(p)) || 'colorTexture';
    const w = (m.vetores[tinta] || m.base.vetores[tinta]?.v || [1, 1, 1, 1])[3] ?? 1;
    m.texturas[paramCor] = BRANCA;
    m.vetores[tinta] = [c.r, c.g, c.b, w];
    const depois = md.fotoMaterial(variacao);
    md.restaurarMaterial(variacao, antes);
    this.historico.executar({ nome: 'Cor sólida', desfazer: () => md.restaurarMaterial(variacao, antes), refazer: () => md.restaurarMaterial(variacao, depois) });
  }

  // ------------------------------------------------------------------ centralizar no campo
  centralizarNoCampo(apoiar = false) {
    const md = this.modelo, v = this.viewport;
    const moveis = v.nosMoveis();
    if (!moveis.length) { this.dicaViewport('Selecione os objetos (com referência própria) que quer centralizar', 2000); return; }
    const c = v.caixaDe(moveis.map((n) => n.id));
    if (c.isEmpty()) return;
    const centro = c.getCenter(new THREE.Vector3());
    const T = new THREE.Matrix4().makeTranslation(-centro.x, apoiar ? -c.min.y : 0, -centro.z);
    const trios = moveis.map((n) => [n, n.local.slice(), md.localPara(n, n.mundoM.clone().premultiply(T))]);
    this.confirmarLocais(trios, `Centralizar ${moveis.length > 1 ? moveis.length + ' objetos' : moveis[0].nome} no campo`);
    this.dicaViewport(`Movido ${Math.hypot(centro.x, centro.z).toFixed(2)} m: o centro da seleção agora está no meio do campo (0, 0)`, 3000);
  }

  // ------------------------------------------------------------------ estádio no jogo (stadiums.txt), pessoas e espelho
  ferramentaBanco(aba) {
    if (!this.carregado) return;
    F.abrirBanco(this, aba);
  }

  alterarEstadio(mudancas, nome, fundir = null) {
    const md = this.modelo;
    if (!md.estadio) { aviso('stadiums.txt não encontrado para este estádio', { tipo: 'aviso', detalhe: 'Ponha o stadiums.txt (tabela do banco do jogo) na pasta do export ou na pasta acima.' }); return; }
    const antes = JSON.parse(JSON.stringify(md.estadio.atual));
    const depois = { ...antes, ...JSON.parse(JSON.stringify(mudancas)) };
    this.historico.executar({ nome, fundir, desfazer: () => md.definirEstadio(antes), refazer: () => md.definirEstadio(depois) });
  }

  aoMudarEstadio() {
    const md = this.modelo, v = this.viewport;
    const est = md.estadio?.atual;
    if (!est) return;
    v.definirZonas(est.zonas, v.mostrarPessoas);
    if (v.mostrarCampo) v.definirCampo(est.comprimento, est.largura, true);
    md.campo.comprimento = est.comprimento;
    md.campo.largura = est.largura;
    if (!est.espelhado && v.espelhado) this.alternarEspelho(false);
    this.atualizarBarraVista();
    this.props.agendar();
  }

  alternarPessoas(v = !this.viewport.mostrarPessoas) {
    const vp = this.viewport;
    vp.mostrarPessoas = v;
    GUARDA('pessoas', v);
    vp.atualizarVisibilidade();
    vp.definirZonas(this.modelo.estadio?.atual.zonas, v);
    this.atualizarBarraVista();
    const n = this.modelo.nos.filter((x) => x.tipo === 'marcador').length;
    this.dicaViewport(v ? `${fmtInt(n)} pessoas e assentos do banco à mostra · áreas técnicas: casa em azul, visitante em vermelho` : 'Pessoas escondidas', 2600);
  }

  alternarEspelho(v = !this.viewport.espelhado) {
    const vp = this.viewport;
    if (v && this.viewport.livre) return;
    vp.definirEspelho(v);
    this.atualizarBarraVista();
    if (v) {
      const sair = el('button', { onclick: () => this.alternarEspelho(false) }, 'Voltar à edição');
      this.dicaViewport([el('span', { html: icone('espelho', 14) }), document.createTextNode('Como o jogo mostra (ismirrored = 1): espelhado em Z. Edição pausada · '), sair], 0);
    } else this.dicaViewport(null);
  }

  // ------------------------------------------------------------------ menus
  menuArquivo() {
    const c = this.carregado;
    return [
      { rotulo: 'Abrir pasta exportada…', icone: 'pastaAberta', atalho: 'Ctrl+O', fn: () => D.abrirPasta(this) },
      { rotulo: 'Abrir projeto…', icone: 'arquivo', fn: () => this.abrirProjeto() },
      { rotulo: 'Adicionar pasta de apoio…', icone: 'mais', desabilitado: !c, fn: () => this.adicionarApoio() },
      { rotulo: 'Trocar de mundo…', icone: 'estadio', desabilitado: !c || !(this.mundos?.length > 1), fn: async () => { const a = await D.escolherMundo(this.mundos, this.pastas); if (a) { if (this.modelo.contarPendentes() && !await confirmar('Descartar alterações?', 'Há alterações não salvas.', { rotulo: 'Descartar', perigo: true })) return; this.carregarMundo(a); } } },
      { rotulo: 'Recarregar do disco', icone: 'restaurar', desabilitado: !c, fn: () => this.recarregar() },
      '-',
      { rotulo: 'Salvar nos arquivos do jogo', icone: 'salvar', atalho: 'Ctrl+S', desabilitado: !this.modelo.contarPendentes(), fn: () => this.salvar() },
      { rotulo: this.projeto ? 'Salvar projeto' : 'Salvar projeto…', icone: 'arquivo', atalho: 'Ctrl+Shift+S', desabilitado: !c, fn: () => this.salvarProjeto() },
      { rotulo: 'Salvar projeto como…', desabilitado: !c, fn: () => this.salvarProjeto(true) },
      { rotulo: 'Arquivos alterados…', icone: 'arquivo', desabilitado: !this.pastas, fn: () => this.abrirAlteracoes() },
      { rotulo: 'Exportar com outro nome…', icone: 'externo', desabilitado: !c, fn: () => this.dialogoRenomear() },
      '-',
      { rotulo: 'Capturar imagem da vista', icone: 'camera', desabilitado: !c, fn: () => this.capturar() },
      { rotulo: 'Mostrar pasta no Explorer', icone: 'pasta', desabilitado: !this.pastas, fn: () => api('explorer', { caminho: this.pastas[0] }).catch((e) => aviso(e.message, { tipo: 'erro' })) },
      { rotulo: 'Configurações (jogo e texturas)…', icone: 'pincel', fn: () => this.abrirConfiguracoes() },
      '-',
      { rotulo: 'Fechar estádio', icone: 'x', desabilitado: !c, fn: () => this.fechar() },
    ];
  }

  async adicionarApoio() {
    const p = await D.abrirPasta(this, { titulo: 'Adicionar pasta de apoio', paraDestino: true });
    if (!p) return;
    if (this.pastas.includes(p)) return;
    aviso('Pasta de apoio adicionada', { detalhe: 'Malhas e texturas que faltam serão procuradas nela (só leitura).' });
    this.abrir([...this.pastas, p], this.mundoAtual);
  }

  menuEditar() {
    const md = this.modelo, h = this.historico, c = this.carregado;
    const sel = md.selecao.size;
    return [
      { rotulo: h.podeDesfazer ? `Desfazer ${h.proximoDesfazer}` : 'Desfazer', icone: 'desfazer', atalho: 'Ctrl+Z', desabilitado: !h.podeDesfazer, fn: () => this.desfazer() },
      { rotulo: h.podeRefazer ? `Refazer ${h.proximoRefazer}` : 'Refazer', icone: 'refazer', atalho: 'Ctrl+Shift+Z', desabilitado: !h.podeRefazer, fn: () => this.refazer() },
      '-',
      { rotulo: 'Selecionar tudo', atalho: 'Ctrl+A', desabilitado: !c, fn: () => this.selecionarTudo() },
      { rotulo: 'Inverter seleção', atalho: 'Ctrl+I', desabilitado: !c, fn: () => this.inverterSelecao() },
      { rotulo: 'Limpar seleção', atalho: 'Esc', desabilitado: !sel, fn: () => md.selecionar([]) },
      { rotulo: 'Selecionar cópias (mesma malha/luz)', atalho: 'Shift+L', icone: 'copias', desabilitado: !sel, fn: () => this.selecionarCopias() },
      '-',
      { rotulo: 'Mover livre', atalho: 'G', icone: 'mover', desabilitado: !sel, fn: () => this.iniciarMoverLivre() },
      { rotulo: 'Ocultar / mostrar no jogo', icone: 'jogo', atalho: 'Del', desabilitado: !sel, fn: () => this.alternarJogoSelecao() },
      { rotulo: 'Voltar transformação ao original', icone: 'restaurar', desabilitado: !sel, fn: () => this.redefinirSelecao() },
    ];
  }

  menuExibir() {
    const v = this.viewport, c = this.carregado;
    return [
      { cabecalho: 'Modo' },
      ...MODOS.map(([id, rot]) => ({ rotulo: rot, marcado: v.modo === id, fn: () => this.definirModo(id) })),
      '-',
      { rotulo: 'Texturas', atalho: 'T', marcado: this.materiais.texturasLigadas, fn: () => this.alternarTexturas() },
      { rotulo: 'Sombras do sol', marcado: v.mostrarSombras, fn: () => this.alternarSombras() },
      { rotulo: 'Luzes do estádio', marcado: v.mostrarLuzes, desabilitado: !c, fn: () => this.alternarLuzes() },
      { rotulo: 'Linhas do campo', marcado: v.mostrarCampo, desabilitado: !c, fn: () => this.alternarCampo() },
      { rotulo: 'Pessoas da lateral, banco e áreas técnicas', marcado: v.mostrarPessoas, desabilitado: !c, fn: () => this.alternarPessoas() },
      { rotulo: 'Ver como no jogo (espelhado)', marcado: v.espelhado, desabilitado: !c, fn: () => this.alternarEspelho() },
      { rotulo: 'Grade do chão', marcado: v.mostrarGrade !== false, fn: () => { v.mostrarGrade = v.mostrarGrade === false; GUARDA('grade', v.mostrarGrade); v.aplicarModo(); } },
      { rotulo: 'Itens não exportados', marcado: v.mostrarFaltando, fn: () => this.alternarOpcao('mostrarFaltando', 'faltando') },
      { rotulo: 'Ocultos no jogo (em vermelho)', marcado: v.mostrarOcultosJogo, fn: () => this.alternarOpcao('mostrarOcultosJogo', 'ocultosJogo') },
      { rotulo: 'Malhas de sombra (_Shadow)', marcado: v.mostrarMalhasSombra, fn: () => this.alternarOpcao('mostrarMalhasSombra', 'malhasSombra') },
      { rotulo: 'Malhas invisíveis no jogo (shadow seat, em ciano)', marcado: v.mostrarInvisiveis, fn: () => this.alternarOpcao('mostrarInvisiveis', 'invisiveis') },
      { rotulo: 'Assentos da torcida', marcado: !!this.estadoTorcida?.visivel, desabilitado: !this.modelo.nuvens?.length, fn: () => this.alternarTorcida(!this.estadoTorcida?.visivel) },
      '-',
      { rotulo: 'Enquadrar tudo', icone: 'maximizar', atalho: 'Home', desabilitado: !c, fn: () => v.enquadrarTudo() },
      { rotulo: 'Enquadrar seleção', icone: 'alvo', atalho: 'F', desabilitado: !this.modelo.selecao.size, fn: () => this.focar() },
      { rotulo: v.iso ? 'Sair do modo isolado' : 'Isolar seleção', icone: 'isolar', atalho: '/', desabilitado: !c, fn: () => this.isolar() },
      { rotulo: 'Ocultar seleção no editor', icone: 'olhoFechado', atalho: 'H', desabilitado: !this.modelo.selecao.size, fn: () => this.ocultarSelecaoEditor() },
      { rotulo: 'Mostrar tudo no editor', icone: 'olho', atalho: 'Alt+H', desabilitado: !c, fn: () => this.mostrarTudoEditor() },
    ];
  }

  menuFerramentas() {
    const c = this.carregado;
    return [
      { rotulo: 'Luzes: adicionar e editar…', icone: 'luzMais', desabilitado: !c, fn: () => this.ferramentaLuzes() },
      { rotulo: 'Remapear em anel (luzes, refletores…)', icone: 'girar', desabilitado: !c, fn: () => this.ferramentaRemapear() },
      { rotulo: 'Mover livre', icone: 'mover', atalho: 'G', desabilitado: !c || !this.modelo.selecao.size, fn: () => this.iniciarMoverLivre() },
      { rotulo: 'Centralizar no campo', icone: 'centralizar', desabilitado: !c || !this.modelo.selecao.size, fn: () => this.centralizarNoCampo() },
      '-',
      { rotulo: 'Banco de reservas e área técnica…', icone: 'banco', desabilitado: !c, fn: () => this.ferramentaBanco() },
      { rotulo: 'Estádio no jogo (stadiums.txt)…', icone: 'estadio', desabilitado: !c, fn: () => this.ferramentaBanco('estadio') },
      '-',
      { rotulo: 'Torcida: marcar e colorir…', icone: 'torcida', desabilitado: !c || !this.modelo.nuvens?.length, fn: () => this.abrirPainelTorcida() },
      { rotulo: 'Gerar assentos a partir de malha…', icone: 'torcida', desabilitado: !c || !this.modelo.nuvens?.length, fn: () => this.ferramentaGerarAssentos() },
      '-',
      { rotulo: 'Mesh zero nos removidos do jogo…', icone: 'apagar', desabilitado: !c, fn: () => this.dialogoMeshZero() },
      { rotulo: 'Linhas do campo', icone: 'campo', marcado: this.viewport.mostrarCampo, desabilitado: !c, fn: () => this.alternarCampo() },
      { rotulo: 'Exportar com outro nome (batch import)…', icone: 'externo', desabilitado: !c, fn: () => this.dialogoRenomear() },
      { rotulo: 'Configurações (jogo e texturas)…', icone: 'pincel', fn: () => this.abrirConfiguracoes() },
    ];
  }

  menuAjuda() {
    return [
      { rotulo: 'Atalhos do teclado e mouse', icone: 'teclado', atalho: '?', fn: () => D.dialogoAtalhos() },
      { rotulo: 'Tela inicial', icone: 'estadio', fn: () => { if (this.carregado) this.fechar(); } },
      { rotulo: 'Sobre o editor', icone: 'info', fn: () => D.dialogoSobre() },
    ];
  }

  menuContexto(x, y) {
    const md = this.modelo;
    const n = md.nos[md.ativo];
    if (!n) return;
    const sel = [...md.selecao];
    const comJogo = sel.filter((i) => md.nos[i].jogo);
    const todosOcultos = comJogo.length && comJogo.every((i) => md.ocultoNoJogoProprio(md.nos[i]));
    abrirMenu([
      { cabecalho: sel.length > 1 ? `${sel.length} itens` : n.rotulo },
      { rotulo: 'Enquadrar', icone: 'alvo', atalho: 'F', fn: () => this.focar() },
      { rotulo: 'Isolar', icone: 'isolar', atalho: '/', fn: () => this.isolar() },
      { rotulo: 'Mover livre', icone: 'mover', atalho: 'G', fn: () => this.iniciarMoverLivre() },
      '-',
      { rotulo: 'Ocultar no editor', icone: 'olhoFechado', atalho: 'H', fn: () => this.ocultarSelecaoEditor() },
      { rotulo: 'Ocultar o resto', atalho: 'Shift+H', fn: () => this.ocultarSelecaoEditor(true) },
      { rotulo: todosOcultos ? 'Mostrar no jogo' : 'Ocultar no jogo', icone: todosOcultos ? 'jogo' : 'jogoOff', atalho: 'Del', desabilitado: !comJogo.length, fn: () => this.alternarJogoSelecao() },
      '-',
      { rotulo: 'Selecionar cópias', icone: 'copias', fn: () => this.selecionarCopias() },
      { rotulo: 'Selecionar itens dentro', desabilitado: !n.filhos.length, fn: () => md.selecionar(md.descendentes(n, false).filter((d) => !ehGrupo(d)).map((d) => d.id)) },
      { rotulo: 'Centralizar no campo', icone: 'centralizar', fn: () => this.centralizarNoCampo() },
      ...(sel.some((i) => md.nos[i].tipo === 'luz') ? [
        { rotulo: 'Duplicar luz', atalho: 'Ctrl+D', icone: 'copiar', fn: () => this.duplicarLuzes() },
        { rotulo: 'Apontar para o centro do campo', icone: 'alvo', fn: () => this.apontarLuzes(new THREE.Vector3()) },
        { rotulo: 'Excluir luz', icone: 'apagar', fn: () => this.excluirLuzes() },
      ] : []),
      { rotulo: 'Remapear em anel…', icone: 'girar', fn: () => this.ferramentaRemapear() },
      { rotulo: 'Expandir tudo abaixo', desabilitado: !n.filhos.length, fn: () => this.arvore.expandirTudo(n.id, true) },
      '-',
      { rotulo: 'Voltar transformação ao original', icone: 'restaurar', desabilitado: !sel.some((i) => md.nos[i].alvo && md.alterado(md.nos[i])), fn: () => this.redefinirSelecao() },
      { rotulo: 'Mostrar arquivo no Explorer', icone: 'pasta', desabilitado: !(n.alvo?.arq || n.arq), fn: () => this.explorer(n.alvo?.arq || n.arq) },
    ], x, y);
  }

  // ------------------------------------------------------------------ teclado
  teclado() {
    const digitando = (e) => ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.target.isContentEditable;
    document.addEventListener('keydown', (e) => {
      const v = this.viewport, md = this.modelo;
      const k = e.key.toLowerCase();
      const ctrl = e.ctrlKey || e.metaKey;
      if (modalAberto()) return;
      if (ctrl && e.shiftKey && k === 's') { e.preventDefault(); this.salvarProjeto(); return; }
      if (ctrl && k === 's') { e.preventDefault(); this.salvar(); return; }
      if (ctrl && k === 'o') { e.preventDefault(); D.abrirPasta(this); return; }
      if (digitando(e) || menuAberto()) return;
      // mover livre ativo: eixos, confirmar, cancelar
      if (v.livre) {
        if (['x', 'y', 'z'].includes(k)) { v.travarLivre(k, e.shiftKey); e.preventDefault(); return; }
        if (e.key === 'Enter') { v.terminarLivre(true); e.preventDefault(); return; }
        if (e.key === 'Escape') { v.terminarLivre(false); e.preventDefault(); return; }
        if (e.key === 'Control') { v.livre.ctrl = true; v.atualizarLivre(); }
        return;
      }
      if (v.voando && ['w', 'a', 's', 'd', 'q', 'e', 'shift'].includes(k)) { v.teclasVoo.add(k); e.preventDefault(); return; }
      if (e.key === 'Control' && v.arrastando) v.aplicarEncaixe(!v.encaixe);
      if (ctrl && k === 'z') { e.preventDefault(); e.shiftKey ? this.refazer() : this.desfazer(); return; }
      if (ctrl && k === 'y') { e.preventDefault(); this.refazer(); return; }
      if (e.key === 'F1' || e.key === '?') { e.preventDefault(); D.dialogoAtalhos(); return; }
      if (!this.carregado) return;
      if (ctrl && k === 'f') { e.preventDefault(); $('#busca').focus(); $('#busca').select(); return; }
      if (ctrl && k === 'a') { e.preventDefault(); this.selecionarTudo(); return; }
      if (ctrl && k === 'i') { e.preventDefault(); this.inverterSelecao(); return; }
      if (ctrl && k === 'd') { e.preventDefault(); this.duplicarLuzes(); return; }
      if (ctrl) {
        if (e.code === 'Numpad1') { e.preventDefault(); v.vista('tras'); }
        if (e.code === 'Numpad3') { e.preventDefault(); v.vista('esquerda'); }
        return;
      }
      switch (e.code) {
        case 'Numpad7': v.vista('topo'); return;
        case 'Numpad1': v.vista('frente'); return;
        case 'Numpad3': v.vista('direita'); return;
        case 'Numpad5': v.vista('perspectiva'); return;
        case 'NumpadDecimal': this.focar(); return;
        case 'NumpadDivide': this.isolar(); return;
        default: break;
      }
      if (e.altKey && k === 'h') { e.preventDefault(); this.mostrarTudoEditor(); return; }
      if (e.shiftKey && k === 'h') { this.ocultarSelecaoEditor(true); return; }
      if (e.shiftKey && k === 'l') { this.selecionarCopias(); return; }
      if (e.altKey) return;
      switch (k) {
        case 'q': this.definirFerramenta('selecionar'); break;
        case 'g': this.iniciarMoverLivre(); break;
        case 'w': this.definirFerramenta('mover'); break;
        case 'r': case 'e': this.definirFerramenta('girar'); break;
        case 's': this.definirFerramenta('escala'); break;
        case 'l': this.alternarEspaco(); break;
        case 'x': this.alternarEncaixe(); break;
        case 'f': this.focar(); break;
        case 'home': v.enquadrarTudo(); break;
        case 'h': this.ocultarSelecaoEditor(); break;
        case '/': this.isolar(); break;
        case 'delete': case 'backspace': this.alternarJogoSelecao(); break;
        case 'z': { const i = MODOS.findIndex(([id]) => id === v.modo); this.definirModo(MODOS[(i + 1) % MODOS.length][0]); this.dicaViewport(`Modo: ${MODOS[(i + 1) % MODOS.length][1]}`, 1200); break; }
        case 't': this.alternarTexturas(); break;
        case 'escape':
          if (this.modoLuz) this.sairModoLuz();
          else if (this.modoEscolha) this.cancelarEscolhaNaVista();
          else if (v.ferramentaCaixa === 'torcida') this.sairFerramentaTorcida();
          else if (this.ferramentaCaixaAtiva) this.alternarFerramentaCaixa(false);
          else if (painelAberto()) fecharPainel();
          else if (v.iso) this.isolar();
          else md.selecionar([]);
          break;
        default: return;
      }
      e.preventDefault();
    });
    document.addEventListener('keyup', (e) => {
      const v = this.viewport;
      const k = e.key.toLowerCase();
      v.teclasVoo.delete(k);
      if (e.key === 'Control' && v.arrastando) v.aplicarEncaixe();
      if (e.key === 'Control' && v.livre) { v.livre.ctrl = false; v.atualizarLivre(); }
    });
    window.addEventListener('blur', () => this.viewport.teclasVoo.clear());
  }
}

const PARAM_COR_MAIN = ['colorTexture', 'colorAnisoTexture', 'facadeColorTexture', 'frameColorTexture', 'adboardTexture', 'decalTexture', 'color2Texture'];
const nomeCurtoMain = (a) => (a || '').split('/').pop().replace(/_mesh$/, '');

window.app = new App();
