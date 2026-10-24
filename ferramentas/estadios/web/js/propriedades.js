// Painel de propriedades: o que está selecionado, com edição direta.
import * as THREE from 'three';
import { icone } from './icones.js';
import { el, esc, fmtInt, fmtNum, campoNumero, campoRotulado, interruptor, nota, copiarTexto } from './ui.js';
import { ehGrupo, rotuloTipo, mat4De12, m12De } from './modelo.js';
import { nomeParam, PARAM_COR } from './materiais.js';

const ABERTAS = JSON.parse(localStorage.getItem('editor.secoes') || '{}');
const GRAUS = 180 / Math.PI;

function secao(id, titulo, corpo, { aberta = true, acao = null } = {}) {
  const d = el('details', { class: 'secao' });
  d.open = ABERTAS[id] ?? aberta;
  const s = el('summary', { html: icone('seta', 12, 'seta') + `<span>${esc(titulo)}</span>` });
  if (acao) { const a = el('span', { class: 'acao-dir' }); a.append(acao); s.append(a); a.onclick = (e) => e.preventDefault(); }
  d.append(s);
  const c = el('div', { class: 'secao-corpo' });
  if (Array.isArray(corpo)) c.append(...corpo.filter(Boolean)); else if (corpo) c.append(corpo);
  d.append(c);
  d.addEventListener('toggle', () => { ABERTAS[id] = d.open; localStorage.setItem('editor.secoes', JSON.stringify(ABERTAS)); });
  return d;
}

const nomeCurto = (a) => String(a || '').split('/').pop();

export function decompor(local) {
  const m = mat4De12(local);
  const p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
  if (m.determinant() >= 0) {
    m.decompose(p, q, s);
    const e = new THREE.Euler().setFromQuaternion(q, 'XYZ');
    return { pos: [p.x, p.y, p.z], rot: [e.x * GRAUS, e.y * GRAUS, e.z * GRAUS], esc: [s.x, s.y, s.z] };
  }
  // espelhada: escolhe o eixo negativo que deixa a rotação mais simples (ex.: forward = -Z vira escala Z = -1, sem giro)
  let melhor = null;
  for (let k = 0; k < 3; k++) {
    const m2 = m.clone();
    const el = m2.elements;
    for (let i = 0; i < 3; i++) el[k * 4 + i] = -el[k * 4 + i];
    m2.decompose(p, q, s);
    const e = new THREE.Euler().setFromQuaternion(q, 'XYZ');
    const rot = [e.x * GRAUS, e.y * GRAUS, e.z * GRAUS];
    const esc = [s.x, s.y, s.z];
    esc[k] = -esc[k];
    const nota = rot.reduce((a, v) => a + Math.abs(v), 0);
    if (!melhor || nota < melhor.nota - 1e-6) melhor = { nota, pos: [p.x, p.y, p.z], rot, esc };
  }
  return melhor;
}

export function compor({ pos, rot, esc: s }) {
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(rot[0] / GRAUS, rot[1] / GRAUS, rot[2] / GRAUS, 'XYZ'));
  const m = new THREE.Matrix4().compose(new THREE.Vector3(...pos), q, new THREE.Vector3(...s));
  return m12De(m);
}

export class Propriedades {
  constructor(raiz, app) {
    this.raiz = raiz;
    this.app = app;
    this.travarEscala = !!localStorage.getItem('editor.travarEscala');
    this.md = app.modelo;
    this.campos = null;
    for (const ev of ['selecao', 'jogo', 'visEditor', 'gravado', 'material', 'carregado', 'estadio', 'luz']) this.md.addEventListener(ev, () => this.agendar());
    this.md.addEventListener('locais', () => this.atualizarValores());
  }

  agendar() {
    if (this._ag) return;
    this._ag = requestAnimationFrame(() => { this._ag = null; this.montar(); });
  }

  montar() {
    const rolagem = this.raiz.scrollTop;
    this.raiz.innerHTML = '';
    this.campos = null;
    const md = this.md;
    if (!md.nos.length) { this.raiz.append(el('div', { class: 'vazio-prop' }, 'Abra um estádio para ver as propriedades.')); return; }
    const sel = [...md.selecao];
    if (!sel.length) this.visaoGeral();
    else if (sel.length === 1) this.umNo(md.nos[sel[0]]);
    else this.varios(sel.map((i) => md.nos[i]));
    this.raiz.scrollTop = rolagem;
  }

  // ------------------------------------------------------------------ nada selecionado
  visaoGeral() {
    const md = this.md, app = this.app;
    const cab = el('div', { class: 'prop-cab' });
    cab.append(el('div', { class: 'titulo', html: icone('estadio', 18) + `<h3>${esc(md.nos[0].nome)}</h3>` }));
    cab.append(el('div', { class: 'sub' }, md.pastas[0] || ''));
    this.raiz.append(cab);
    const malhas = Object.values(md.malhas);
    const comFbx = malhas.filter((m) => m.fbx).length;
    const objetos = md.nos.filter((n) => !ehGrupo(n)).length;
    const falt = md.nos.filter((n) => n.faltando === 'blueprint').length;
    const tex = Object.values(md.texturas);
    const est = app.viewport.estatisticas();
    const grade = el('div', { class: 'estatisticas' });
    const tile = (v, r) => el('div', { class: 'estatistica' }, el('b', {}, v), el('span', {}, r));
    grade.append(tile(fmtInt(objetos), 'objetos'), tile(`${fmtInt(comFbx)}/${fmtInt(malhas.length)}`, 'malhas com FBX'),
      tile(fmtInt(est.triangulos), 'triângulos visíveis'), tile(`${fmtInt(tex.filter((t) => t.png).length)}/${fmtInt(tex.length)}`, 'texturas exportadas'));
    this.raiz.append(secao('geral', 'Resumo', [grade,
      falt ? nota(`${fmtInt(falt)} objetos usam blueprints que não estão no export (aparecem como losangos roxos). Exporte-os no FET para vê-los.`) : null,
      malhas.length - comFbx ? nota(`${fmtInt(malhas.length - comFbx)} malhas não têm FBX no export (aparecem como caixas tracejadas ou losangos).`) : null]));
    // jogo instalado (texturas)
    const jg = app.jogoInfo || { estado: 'indisponivel' };
    let txtJogo;
    if (jg.estado === 'pronto') txtJogo = `<b>FC 26 conectado</b> · ${fmtInt(jg.texturas)} texturas do jogo disponíveis (imagens e GUIDs).`;
    else if (jg.estado === 'indexando') txtJogo = `Lendo o índice do FC 26… ${Math.round((jg.progresso || 0) * 100)}%`;
    else if (jg.estado === 'erro') txtJogo = `Não foi possível ler o FC 26: ${esc(jg.erro || '')}`;
    else txtJogo = 'FC 26 não configurado: as texturas que não vieram no export aparecem como cores estimadas.';
    this.raiz.append(secao('jogo', 'Texturas do jogo', [nota(txtJogo, jg.estado === 'pronto' ? 'info' : jg.estado === 'erro' ? 'alerta' : ''),
      el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => app.abrirConfiguracoes() }, icone('pincel', 14), 'Configurar…'))]));
    // estádio no jogo (stadiums.txt): espelhamento, medidas do campo, banco
    const e = md.estadio?.atual;
    const corpoEst = [];
    if (!e) corpoEst.push(nota('stadiums.txt deste estádio não encontrado (procure deixá-lo na pasta do export ou na pasta acima): sem ele não dá para ajustar espelhamento, área técnica e medidas do campo.'));
    else {
      corpoEst.push(el('dl', { class: 'kv', html: `<dt>Estádio</dt><dd>${esc(md.campo.id)} · ${esc(md.campo.nome || '')}</dd>
        <dt>Campo</dt><dd>${fmtNum(e.comprimento, 1)} × ${fmtNum(e.largura, 1)} m</dd><dt>Espelhado</dt><dd>${e.espelhado ? 'sim (ismirrored = 1)' : 'não'}</dd>` }));
      if (e.espelhado) corpoEst.push(nota('O jogo mostra este estádio <b>espelhado</b> em relação ao arquivo: no jogo, o que está de um lado aparece do outro (guarda-corpos invertidos, peças deslocadas). Use <b>Ver como no jogo</b> para conferir, ou desligue o espelhamento.', 'alerta'));
    }
    corpoEst.push(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', onclick: () => app.ferramentaBanco('estadio') }, icone('banco', 14), 'Banco, área técnica e campo…'),
      e?.espelhado ? el('button', { class: 'btn peq', onclick: () => app.alternarEspelho() }, icone('espelho', 14), app.viewport.espelhado ? 'Voltar à edição' : 'Ver como no jogo') : null));
    this.raiz.append(secao('estadio', 'Estádio no jogo', corpoEst));
    const ferr = el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', onclick: () => app.ferramentaLuzes() }, icone('luzMais', 14), 'Luzes…'),
      el('button', { class: 'btn peq', onclick: () => app.ferramentaRemapear() }, icone('girar', 14), 'Remapear em anel…'),
      el('button', { class: 'btn peq', onclick: () => app.ferramentaGerarAssentos() }, icone('torcida', 14), 'Gerar assentos…'),
      el('button', { class: 'btn peq', onclick: () => app.alternarCampo() }, icone('campo', 14), app.viewport.mostrarCampo ? 'Esconder linhas do campo' : 'Linhas do campo'),
      el('button', { class: 'btn peq', onclick: () => app.dialogoRenomear() }, icone('externo', 14), 'Exportar com outro nome…'));
    this.raiz.append(secao('ferramentas', 'Ferramentas', [ferr]));
    const pend = md.contarPendentes();
    const corpoAlt = [el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn-primario peq', disabled: !pend, onclick: () => app.salvar() }, icone('salvar', 14), pend ? `Salvar ${pend} alteraç${pend > 1 ? 'ões' : 'ão'}` : 'Nada a salvar'),
      el('button', { class: 'btn peq', onclick: () => app.abrirAlteracoes() }, 'Arquivos alterados…'))];
    this.raiz.append(secao('alteracoes', 'Alterações', corpoAlt));
    if (md.nuvens?.length) {
      const t = md.torcida;
      const vis = !!app.estadoTorcida?.visivel;
      const desc = `${md.nuvens.map((c) => c.nome).join(', ')}${t ? ` · ${fmtInt(t.atual.n)} assentos${t.atual !== t.original ? ' (alterada, não salva)' : ''}` : ''}`;
      const corpo = [interruptor({ titulo: 'Mostrar assentos da torcida', descricao: desc, marcado: vis, icone: 'torcida', aoMudar: (v) => app.alternarTorcida(v) }).el,
        el('div', { class: 'acoes-linha' },
          el('button', { class: 'btn peq', onclick: () => app.abrirPainelTorcida() }, icone('pincel', 14), 'Marcar e colorir…'),
          el('button', { class: 'btn peq', onclick: () => app.ferramentaGerarAssentos() }, icone('torcida', 14), 'Gerar assentos…'))];
      this.raiz.append(secao('torcida', 'Torcida', corpo));
    }
    const dicas = el('div', { class: 'kv', html: `
      <dt><kbd>Clique</kbd></dt><dd>selecionar (Ctrl soma, Ctrl+arrastar = caixa)</dd>
      <dt><kbd>Arrastar</kbd></dt><dd>girar a câmera · <kbd>Shift</kbd> move</dd>
      <dt><kbd>Botão dir.</kbd></dt><dd>olhar em volta + <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> voar</dd>
      <dt><kbd>F</kbd></dt><dd>enquadrar seleção · <kbd>Home</kbd> tudo</dd>
      <dt><kbd>G</kbd></dt><dd>mover livre (X/Y/Z trava o eixo)</dd>
      <dt><kbd>W</kbd> <kbd>R</kbd> <kbd>S</kbd></dt><dd>gizmo de mover, girar, escalar</dd>
      <dt><kbd>H</kbd></dt><dd>ocultar no editor · <kbd>Alt+H</kbd> mostrar tudo</dd>
      <dt><kbd>?</kbd></dt><dd>todos os atalhos</dd>` });
    this.raiz.append(secao('dicas', 'Atalhos principais', dicas));
  }

  // ------------------------------------------------------------------ um nó
  umNo(n) {
    const md = this.md, app = this.app;
    const grupo = ehGrupo(n);
    const cab = el('div', { class: 'prop-cab' });
    const mig = el('div', { class: 'migalhas' });
    for (const a of md.ancestrais(n).reverse()) {
      const b = el('button', { title: a.nome, onclick: () => { md.selecionar(a.id); app.arvore.revelar(a.id); } }, a.rotulo);
      mig.append(b, el('span', { html: icone('seta', 10) }));
    }
    cab.append(mig);
    const icT = grupo ? 'camadas' : n.tipo === 'prefab' ? 'prefab' : 'cubo';
    cab.append(el('div', { class: 'titulo', html: icone(icT, 17) + `<h3 title="${esc(n.nome)}">${esc(n.rotulo)}</h3>` }));
    const sub = n.bp || n.asset || (n.malhas?.[0] ? md.malhas[n.malhas[0].m]?.asset : '');
    if (sub) cab.append(el('div', { class: 'sub' }, sub));
    const tags = el('div', { class: 'etiquetas' });
    tags.append(el('span', { class: 'etiqueta' }, rotuloTipo(n)));
    if (md.alterado(n)) tags.append(el('span', { class: 'etiqueta azul' }, 'Alterado'));
    if (md.ocultoNoJogoProprio(n)) tags.append(el('span', { class: 'etiqueta vermelha' }, n.jogo.rebaixado ? 'Oculto no jogo (150 m abaixo)' : 'Oculto no jogo'));
    else if (md.ocultoNoJogo(n)) tags.append(el('span', { class: 'etiqueta vermelha' }, 'Oculto pelo grupo'));
    if (n.ligado) tags.append(el('span', { class: 'etiqueta amarela', html: icone('ligado', 11) + 'Ligado à lógica' }));
    if (n.malhas?.some((p) => p.oculta)) tags.append(el('span', { class: 'etiqueta', title: 'Visible=false no blueprint: o jogo não desenha, só usa para sombra/iluminação (ex.: shadow seat). No editor aparece em ciano.' }, 'Malha invisível no jogo'));
    if (n.faltando) tags.append(el('span', { class: 'etiqueta' }, n.faltando === 'blueprint' ? 'Blueprint não exportado' : 'XML não exportado'));
    if (n.compartilhado > 1) tags.append(el('span', { class: 'etiqueta laranja' }, `Prefab usado ${n.compartilhado}×`));
    if (grupo && n.nGeo) tags.append(el('span', { class: 'etiqueta' }, `${fmtInt(n.nGeo)} itens`));
    cab.append(tags);
    this.raiz.append(cab);

    // visibilidade
    const vis = [];
    vis.push(interruptor({ titulo: 'Visível no editor', descricao: 'Só muda a visualização; não altera os arquivos.', marcado: n.visEditor, icone: 'olho',
      aoMudar: (v) => app.definirVisEditor([n.id], v) }).el);
    if (n.jogo && 'habilitada' in n.jogo) {
      vis.push(interruptor({ titulo: 'Acesa no jogo', descricao: 'Grava Enabled=true/false na entidade de luz.', marcado: n.jogo.habilitada, icone: 'luz',
        aoMudar: (v) => app.definirJogo([n.id], !v) }).el);
    } else if (n.jogo) {
      let desc;
      const oc = md.ocultoNoJogoProprio(n);
      if ('visivel' in n.jogo) desc = 'Cópia de grupo estático: ao ocultar, fica Visible=false e desce 150 m (assim não projeta sombra).';
      else if (grupo) desc = n.tipo === 'subworld' ? 'Sub-mundo inteiro (Excluded na referência).' : 'Grupo inteiro (Excluded na referência do mundo).';
      else if (n.ligado) desc = 'Ligado à lógica do jogo: em vez de excluir (pode travar), o objeto desce 150 m para baixo do chão.';
      else desc = 'Ao ocultar, a referência fica Excluded=true no XML.';
      vis.push(interruptor({ titulo: 'Aparece no jogo', descricao: desc, marcado: !oc, icone: 'jogo', aoMudar: (v) => app.definirJogo([n.id], !v) }).el);
      if (md.ocultoNoJogo(n) && !oc) vis.push(nota('Um grupo acima deste está oculto no jogo, então ele também não aparece.', 'alerta'));
    } else if (!grupo || n.tipo === 'smg' || n.tipo === 'membro') {
      vis.push(nota(n.avulso ? 'Sub-mundo que o jogo carrega à parte (nenhum outro arquivo do estádio o referencia). Ele aparece na origem; para tirar do jogo, oculte os objetos dentro dele.' : n.tipo === 'smg' || n.tipo === 'membro' ? 'Para ocultar no jogo, use as cópias dentro deste grupo (ou selecione todas e pressione <kbd>Del</kbd>).' : 'Este item não tem referência própria no mundo.'));
    }
    this.raiz.append(secao('visibilidade', 'Visibilidade', vis));

    if (n.tipo === 'luz' && n.luz) {
      const L = n.luz;
      const ids = [n.id];
      const corpoL = [];
      if (n.nova) corpoL.push(nota(`Luz nova (cópia de um modelo do arquivo <b>${esc((n.alvo.arq || '').split('/').pop())}</b>): vai para o arquivo ao salvar.`));
      corpoL.push(el('dl', { class: 'kv', html: `<dt>Tipo</dt><dd>${esc({ spot: 'Spot (cone)', esfera: 'Pontual (esfera)', tubo: 'Tubo', retangulo: 'Retangular' }[L.tipo] || L.tipo)}</dd>` }));
      const cor = el('input', { type: 'color', value: '#' + new THREE.Color(...(L.cor || [1, 1, 1])).getHexString(THREE.SRGBColorSpace) });
      cor.oninput = () => { const c = new THREE.Color().setStyle(cor.value, THREE.SRGBColorSpace); app.alterarLuzes(ids, { cor: [c.r, c.g, c.b] }, 'Cor da luz', 'luzcor:' + n.id); };
      const campo = (rot, k, opts, nome) => campoRotulado(rot, campoNumero({ valor: L[k] ?? 0, passo: opts.passo, casas: opts.casas, passoCtrl: opts.passoCtrl, min: opts.min ?? 0, max: opts.max,
        aoMudar: (x, fim) => app.alterarLuzes(ids, { [k]: x }, nome, fim ? null : `luz${k}:${n.id}`) }).el);
      corpoL.push(campoRotulado('Cor', cor));
      corpoL.push(campo('Intensidade', 'intensidade', { passo: 50, casas: 0, passoCtrl: 500 }, 'Intensidade da luz'));
      corpoL.push(campo('Alcance (m)', 'raio', { passo: 0.5, casas: 1, passoCtrl: 5 }, 'Alcance da luz'));
      if (L.tipo === 'spot') corpoL.push(campo('Abertura (°)', 'angulo', { passo: 0.5, casas: 1, passoCtrl: 5, min: 1, max: 179 }, 'Abertura da luz'));
      corpoL.push(el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', title: 'Ctrl+D', onclick: () => app.duplicarLuzes() }, icone('copiar', 14), 'Duplicar'),
        el('button', { class: 'btn peq', onclick: () => app.apontarLuzes(new THREE.Vector3()) }, icone('alvo', 14), 'Apontar p/ o centro'),
        el('button', { class: 'btn peq', onclick: () => app.ferramentaLuzes() }, icone('luzMais', 14), 'Adicionar luzes…'),
        n.ligado ? null : el('button', { class: 'btn-perigo peq', onclick: () => app.excluirLuzes() }, icone('apagar', 14), 'Excluir')));
      this.raiz.append(secao('luz', 'Luz', corpoL));
    }
    if (n.tipo === 'marcador') {
      const banco = n.categoria === 'choreo_seats';
      this.raiz.append(secao('marcador', banco ? 'Assento do banco' : 'Pessoa da lateral', [
        nota(banco ? 'É aqui que um reserva senta no jogo. Para levar todos ao banco certo de uma vez: <b>Ferramentas › Banco de reservas e área técnica</b>.'
          : 'Posição onde o jogo coloca esta pessoa (gandula, fotógrafo, policial…). Mova com o gizmo ou o <kbd>G</kbd>; para afastar um grupo do campo use o painel do banco.'),
        el('div', { class: 'acoes-linha' }, el('button', { class: 'btn peq', onclick: () => app.ferramentaBanco() }, icone('banco', 14), 'Banco, área técnica e pessoas…'))]));
    }

    // transformação
    if (n.alvo) this.raiz.append(this.secaoTransformacao(n));

    // malha e materiais
    if (n.malhas?.length) {
      this.raiz.append(this.secaoMalha(n));
      this.raiz.append(this.secaoMateriais(n));
    }

    // arquivo
    const kv = el('dl', { class: 'kv' });
    const linha = (k, v, mono = false) => { kv.append(el('dt', {}, k), el('dd', { class: mono ? 'mono' : '' }, v)); };
    const arqRel = (id) => id ? id.split(':').slice(1).join(':') : '—';
    if (n.alvo) {
      linha('Arquivo', arqRel(n.alvo.arq));
      linha('GUID', n.alvo.guid, true);
      if (n.alvo.membro !== undefined) linha('Membro', `${n.alvo.membro} · cópia ${n.alvo.indice}`);
    } else if (n.arq) linha('Arquivo', arqRel(n.arq));
    if (n.bp) linha('Blueprint', n.bp);
    if (n.mvdb) linha('MVDB', nomeCurto(n.mvdb.replace(/\/MeshVariationDb_Win32$/, '')) + '/MeshVariationDb_Win32');
    const acoes = el('div', { class: 'acoes-linha' });
    const arqId = n.alvo?.arq || n.arq;
    if (arqId) acoes.append(el('button', { class: 'btn peq', onclick: () => app.explorer(arqId) }, icone('pasta', 14), 'Mostrar no Explorer'));
    if (n.bp_arq) acoes.append(el('button', { class: 'btn peq', onclick: () => app.explorer(n.bp_arq) }, 'Blueprint'));
    if (n.alvo) acoes.append(el('button', { class: 'btn-icone peq', title: 'Copiar GUID', html: icone('copiar', 14), onclick: () => copiarTexto(n.alvo.guid) }));
    this.raiz.append(secao('arquivo', 'Arquivo de origem', [kv, acoes], { aberta: false }));
  }

  secaoTransformacao(n) {
    const app = this.app;
    const d = decompor(n.local);
    const campos = { n, pos: [], rot: [], esc: [] };
    const corpo = [];
    const linhaTrio = (rotulo, chave, passo, casas, passoCtrl) => {
      const trio = el('div', { class: 'trio' });
      ['x', 'y', 'z'].forEach((eixo, i) => {
        const c = campoNumero({
          valor: d[chave][i], eixo, passo, casas, passoCtrl,
          titulo: `${rotulo} ${eixo.toUpperCase()} — arraste ou clique para digitar`,
          aoMudar: (v) => {
            const atual = decompor(n.local);
            if (chave === 'esc' && (this.travarEscala || app.viewport.shift) && Math.abs(atual.esc[i]) > 1e-9) {
              const f = v / atual.esc[i];
              atual.esc = atual.esc.map((e) => e * f);
              campos.esc.forEach((cc, k) => k !== i && cc.definir(atual.esc[k]));
            } else atual[chave][i] = v;
            let novo = compor(atual);
            if (chave === 'esc') novo = this.ancorarEscala(n, novo);
            app.definirLocal(n, novo, `${rotulo} de ${n.nome}`);
          },
        });
        campos[chave].push(c);
        trio.append(c.el);
      });
      const rot = el('span', { class: 'rot' }, rotulo);
      if (chave === 'esc') {
        const cad = el('button', { class: `btn-icone peq trava ${this.travarEscala ? 'ativo' : ''}`, title: 'Manter proporção (ou segure Shift ao arrastar)', html: icone('ligado', 13) });
        cad.onclick = () => { this.travarEscala = !this.travarEscala; localStorage.setItem('editor.travarEscala', this.travarEscala ? '1' : ''); cad.classList.toggle('ativo', this.travarEscala); };
        rot.append(cad);
      }
      corpo.push(el('div', { class: 'linha-prop' }, rot, trio));
    };
    linhaTrio('Posição', 'pos', 0.05, 3, 1);
    linhaTrio('Rotação', 'rot', 0.5, 2, 15);
    linhaTrio('Escala', 'esc', 0.005, 3, 0.1);
    if (n.tipo !== 'luz' && n.tipo !== 'marcador') {
      const sel = el('select', { class: 'seletor', style: { maxWidth: 'none' } });
      for (const [v, r] of [['chao', 'o chão do campo (y = 0)'], ['base', 'a base do objeto'], ['centro', 'o centro do objeto'], ['origem', 'a origem do objeto']]) {
        const o = el('option', { value: v }, r); if (app.viewport.ancoraEscala === v) o.selected = true; sel.append(o);
      }
      sel.onchange = () => app.definirAncoraEscala(sel.value);
      corpo.push(el('div', { class: 'linha-prop', title: 'Ponto que fica parado quando a escala muda (gizmo e números). Com “chão do campo”, o piso do estádio continua no chão.' },
        el('span', { class: 'rot' }, 'Escalar a partir de'), sel));
    }
    const det = mat4De12(n.local).determinant();
    if (det < 0) corpo.push(nota('Transformação espelhada (escala negativa): é assim que o estádio original usa esta peça.'));
    if (n.compartilhado > 1) corpo.push(nota(`Este item fica dentro de um prefab usado ${n.compartilhado} vezes: mudar aqui muda todas as cópias.`, 'alerta'));
    const alterado = this.md.alterado(n);
    corpo.push(el('div', { class: 'acoes-linha' },
      el('button', { class: 'btn peq', disabled: !n.local.some((v, i) => Math.abs(v - n.local0[i]) > 1e-6), onclick: () => app.definirLocal(n, n.local0.slice(), `Redefinir ${n.nome}`, false) }, icone('restaurar', 14), 'Voltar ao original'),
      el('button', { class: 'btn peq', onclick: () => app.focar([n.id]) }, icone('alvo', 14), 'Enquadrar'),
      n.tipo !== 'luz' && n.tipo !== 'marcador' ? el('button', { class: 'btn peq', title: 'Leva o centro deste objeto para o meio do campo (x = 0, z = 0), sem mudar a altura',
        onclick: () => app.centralizarNoCampo() }, icone('centralizar', 14), 'Centralizar no campo') : null));
    this.campos = campos;
    this.marcarAlterados(campos);
    return secao('transformacao', 'Transformação', corpo, { acao: alterado ? el('span', { class: 'etiqueta azul' }, 'alterada') : null });
  }

  // escala digitada: corrige a posição para que o ponto de âncora (chão do campo, base ou centro) não saia do lugar
  ancorarEscala(n, novoLocal) {
    const v = this.app.viewport, md = this.md;
    const modo = v.ancoraEscala;
    if (modo === 'origem' || !n.alvo) return novoLocal;
    const c = v.caixaDe([n.id]);
    if (c.isEmpty()) return novoLocal;
    const A = c.getCenter(new THREE.Vector3());
    if (modo === 'chao') A.y = 0; else if (modo === 'base') A.y = c.min.y;
    const P = md.paiMundo(n);
    const W0 = new THREE.Matrix4().multiplyMatrices(P, mat4De12(n.local));
    const W1 = new THREE.Matrix4().multiplyMatrices(P, mat4De12(novoLocal));
    const pLocal = A.clone().applyMatrix4(W0.clone().invert());
    const A1 = pLocal.applyMatrix4(W1);
    W1.premultiply(new THREE.Matrix4().makeTranslation(A.x - A1.x, A.y - A1.y, A.z - A1.z));
    return md.localPara(n, W1);
  }

  marcarAlterados(c) {
    const a = decompor(c.n.local), o = decompor(c.n.local0);
    for (const k of ['pos', 'rot', 'esc']) c[k].forEach((campo, i) => campo.marcar(Math.abs(a[k][i] - o[k][i]) > (k === 'rot' ? 0.01 : 1e-4)));
  }

  atualizarValores() {
    const c = this.campos;
    if (!c) return;
    const d = decompor(c.n.local);
    for (const k of ['pos', 'rot', 'esc']) c[k].forEach((campo, i) => campo.definir(d[k][i]));
    this.marcarAlterados(c);
  }

  secaoMalha(n) {
    const md = this.md, app = this.app;
    const corpo = [];
    for (const p of n.malhas) {
      const info = md.malhas[p.m] || { nome: p.m };
      const geo = app.viewport.geos.get(p.m);
      const kv = el('dl', { class: 'kv' });
      kv.append(el('dt', {}, 'Malha'), el('dd', {}, info.nome));
      kv.append(el('dt', {}, 'Tipo'), el('dd', {}, (info.tipo || '—').replace('MeshAsset', '') + (geo?.ossos ? ` · ${geo.ossos} partes` : '')));
      if (geo) {
        const tri = geo.secoes.filter((s) => !s.sombra).reduce((a, s) => a + s.triangulos, 0);
        kv.append(el('dt', {}, 'Geometria'), el('dd', {}, `${fmtInt(tri)} triângulos · ${geo.secoes.filter((s) => !s.sombra).length} seções${geo.secoes.some((s) => s.sombra) ? ' + sombra' : ''}`));
      }
      const usos = md.nos.filter((x) => (x.malhas || []).some((q) => q.m === p.m)).length;
      kv.append(el('dt', {}, 'Cópias'), el('dd', {}, `${fmtInt(usos)} no estádio`));
      kv.append(el('dt', {}, 'FBX'), el('dd', {}, info.fbx ? info.fbx.split(':').slice(1).join(':') : 'não exportado'));
      corpo.push(kv);
      const acoes = el('div', { class: 'acoes-linha' });
      if (usos > 1) acoes.append(el('button', { class: 'btn peq', onclick: () => app.selecionarCopias(p.m) }, icone('copias', 14), 'Selecionar cópias'));
      if (info.fbx) {
        acoes.append(el('button', { class: 'btn peq', onclick: () => app.explorer(info.fbx) }, icone('pasta', 14), 'FBX'));
        acoes.append(el('button', { class: 'btn peq', title: 'Trocar o modelo 3D por outro FBX (ex.: editado no Blender)', onclick: () => app.substituirFBX(p.m) }, icone('upload', 14), 'Substituir FBX…'));
        const removida = md.nos.every((x) => !(x.malhas || []).some((q) => q.m === p.m) || md.ocultoNoJogo(x));
        if (removida && !app.malhaZerada(p.m)) {
          acoes.append(el('button', { class: 'btn peq', title: 'Trocar o FBX por um triângulo minúsculo por seção: o objeto já está fora do jogo e o 3D deixa de pesar no estádio',
            onclick: () => app.dialogoMeshZero([p.m]) }, icone('apagar', 14), 'Mesh zero…'));
        }
      }
      corpo.push(acoes);
      if (info.fbx && app.malhaZerada(p.m)) corpo.push(nota('FBX com <b>mesh zero</b> (um triângulo por seção). O original está em <i>_editor_originais</i>; volte em <b>Alterações</b>.'));
      if (!info.fbx) corpo.push(nota('O FBX desta malha não está no export. No FET, exporte o asset da malha (<i>' + esc(info.asset || '') + '</i>) para a mesma pasta.'));
    }
    return secao('malha', n.malhas.length > 1 ? `Malhas (${n.malhas.length})` : 'Malha', corpo, { aberta: false });
  }

  secaoMateriais(n) {
    const md = this.md, app = this.app;
    const corpo = [];
    let algum = false, semEntrada = false;
    for (const p of n.malhas) {
      const geo = app.viewport.geos.get(p.m);
      if (!geo) continue;
      const regs = app.viewport.registroSecoes(n, p.m, geo);
      const { lista } = md.materiaisDe(n, p.m);
      const novas = regs.filter((r) => r?.particaoNova && !r.outroMvdb);
      const nomeMalha = esc(md.malhas[p.m]?.nome || p.m);
      if (lista && novas.length && md.mvdbs[n.mvdb]?.arq) {
        // seção acrescentada ao FBX (partição nova): a entrada existe, mas sem material para ela
        semEntrada = true;
        const semGuid = novas.filter((r) => r.semGuid).length;
        if (semGuid) {
          corpo.push(nota(`${semGuid === novas.length ? 'A malha' : `${semGuid} das partições novas de`} <b>${nomeMalha}</b> tem mais seções no FBX do que materiais no XML exportado. Depois de importar o FBX no FET, exporte de novo o XML da malha (é lá que a partição nova ganha o GUID) e abra o estádio de novo.`, 'alerta'));
        }
        if (novas.length > semGuid) {
          corpo.push(nota(`${novas.length - semGuid === 1 ? 'Uma partição nova' : `${novas.length - semGuid} partições novas`} de <b>${nomeMalha}</b> não ${novas.length - semGuid === 1 ? 'tem' : 'têm'} material no MeshVariationDb deste sub-mundo, por isso ${novas.length - semGuid === 1 ? 'fica' : 'ficam'} só leitura. O editor cria o material copiando o da partição de cima; depois é só trocar as texturas.`, 'alerta'));
          corpo.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', title: 'Acrescenta à entrada desta malha no MeshVariationDb um material para cada partição nova, copiado da partição de cima',
            onclick: () => app.completarEntradaMvdb(n, p.m) }, icone('mais', 13), 'Criar material das partições novas')));
        }
      } else if (regs.some((r) => r && (!r.editavel || r.outroMvdb)) && md.mvdbs[n.mvdb]?.arq) {
        // asset novo: a malha não tem entrada no MVDB do próprio sub-mundo
        semEntrada = true;
        const outro = regs.some((r) => r?.outroMvdb);
        const nomeMvdb = (a) => esc(String(a || '').split('/').slice(-2, -1)[0] || '');
        corpo.push(nota(outro
          ? `<b>${esc(md.malhas[p.m]?.nome || p.m)}</b> não tem entrada no MeshVariationDb deste sub-mundo (<i>${nomeMvdb(n.mvdb)}</i>); o editor está mostrando a de <i>${nomeMvdb(md.materiaisDe(n, p.m).mvdb)}</i>. Crie a entrada aqui para o jogo usar shader e texturas próprios neste estádio.`
          : `<b>${esc(md.malhas[p.m]?.nome || p.m)}</b> não tem entrada no MeshVariationDb deste sub-mundo (<i>${nomeMvdb(n.mvdb)}</i>), então o jogo não sabe que shader e texturas usar. Crie a entrada a partir de um material que já existe e depois troque as texturas.`, 'alerta'));
        corpo.push(el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', title: 'Acrescenta a malha ao MeshVariationDb deste sub-mundo, com shader e texturas copiados de um material existente',
          onclick: () => app.criarEntradaMvdb(n, p.m) }, icone('mais', 13), 'Criar entrada no MVDB deste sub-mundo')));
      }
      geo.secoes.forEach((s, si) => {
        const r = regs[si];
        if (!r) return;
        algum = true;
        corpo.push(this.cartaoMaterial(n, p, s, r));
      });
    }
    if (!algum) corpo.push(el('div', { class: 'vazio-prop' }, 'Sem materiais (malha não carregada).'));
    const usosMvdb = md.nos.filter((x) => x.mvdb === n.mvdb && (x.malhas || []).some((q) => n.malhas.some((pp) => pp.m === q.m))).length;
    if (algum && !semEntrada) corpo.unshift(nota(`Materiais vêm do <b>MeshVariationDb</b> do sub-mundo. Trocar textura ou cor aqui vale para ${usosMvdb > 1 ? `as ${usosMvdb} cópias desta malha` : 'esta malha'} neste sub-mundo.`));
    return secao('materiais', 'Materiais e texturas', corpo);
  }

  cartaoMaterial(n, p, s, r) {
    const md = this.md, app = this.app, mats = app.materiais;
    const reg = r.reg;
    const base = reg.base || reg.info || {};
    const tex = reg.texturas || base.texturas || {};
    const vet = reg.vetores || Object.fromEntries(Object.entries(base.vetores || {}).map(([k, v]) => [k, v.v]));
    const shader = base.shader || '?';
    const semShader = !shader || shader === 'null' || shader === '?';
    const card = el('div', { class: 'mat' });
    const pCor = PARAM_COR.find((k) => tex[k] && tex[k] !== 'null');
    const mini = pCor ? mats.urlMiniatura(tex[pCor]) : null;
    const corM = app.viewport.objs[n.id] ? this.corAmostra(n, p, r) : '#777';
    const amostra = el('span', { class: 'amostra', style: mini ? { backgroundImage: `url("${mini}")` } : { background: corM } });
    const etiqueta = reg.copiadoDe ? ' · copiado (não salvo)' : (r.editavel ? '' : ' · só leitura');
    const cab = el('div', { class: 'mat-cab' }, amostra,
      el('div', { class: 'txt' }, el('b', {}, s.nome), el('small', {}, `${semShader ? 'sem shader' : shader}${etiqueta}`)),
      el('span', { html: icone('setaBaixo', 14) }));
    card.append(cab);
    const corpo = el('div', { class: 'mat-corpo' });
    const chaveAberta = `${p.m}|${s.nome}`;
    corpo.hidden = !(this.abertosMat?.has(chaveAberta));
    cab.onclick = () => {
      corpo.hidden = !corpo.hidden;
      this.abertosMat = this.abertosMat || new Set();
      corpo.hidden ? this.abertosMat.delete(chaveAberta) : this.abertosMat.add(chaveAberta);
      app.realcarSecao(corpo.hidden ? null : { no: n.id, malha: p.m, secao: s.nome });
    };
    if (reg.copiadoDe) {
      const origem = md.materiais.get(reg.copiadoDe.variacao_origem);
      corpo.append(nota(`Material copiado de <b>${esc(origem ? nomeCurto(origem.malha) : '?')}</b> (${esc(reg.copiadoDe.shader || '')}). Ao salvar, o shader e os parâmetros dele substituem os deste material no MVDB. <kbd>Ctrl+Z</kbd> desfaz.`, 'info'));
    }
    if (semShader && r.editavel) {
      corpo.append(nota('Este material não tem shader (<i>Shader = null</i>), por isso não tem onde colocar textura. Copie o material de outra seção (ex.: um concreto ou metal) e depois troque a textura.', 'alerta'));
    }
    // texturas
    const params = Object.keys(tex);
    if (!params.length && !semShader) corpo.append(el('div', { class: 'tex-txt' }, el('small', {}, 'Sem texturas neste material.')));
    for (const param of params) {
      const asset = tex[param];
      const vazia = !asset || asset === 'null';
      const orig = (base.texturas || {})[param];
      const nova = !(param in (base.texturas || {}));
      const url = vazia ? null : mats.urlMiniatura(asset);
      const desligada = reg.texOcultas?.has(param);
      const linha = el('div', { class: `tex ${asset !== orig ? 'alterada' : ''} ${desligada ? 'desligada' : ''}` });
      const img = el('div', { class: 'tex-img', style: url ? { backgroundImage: `url("${url}")` } : {} }, url ? '' : vazia ? 'vazia' : 'sem imagem');
      linha.append(img, el('div', { class: 'tex-txt', title: vazia ? 'Sem textura (null)' : asset },
        el('b', {}, nomeParam(param) + (nova ? ' (nova)' : '')), el('small', {}, vazia ? 'nenhuma — clique no pincel para escolher' : nomeCurto(asset))));
      const ac = el('div', { class: 'tex-acoes' });
      if (r.editavel) {
        if (!vazia) ac.append(el('button', { class: 'btn-icone peq', title: desligada ? 'Mostrar esta textura no editor' : 'Esconder esta textura no editor (não altera o arquivo)', html: icone(desligada ? 'olhoFechado' : 'olho', 14), onclick: () => app.alternarTexturaEditor(r.chave, param) }));
        ac.append(el('button', { class: 'btn-icone peq', title: 'Escolher a textura (todas as do jogo e as exportadas)', html: icone('pincel', 14), onclick: () => app.escolherTextura(r.chave, param) }));
        const t = md.texturas[asset];
        if (t && t.png) ac.append(el('button', { class: 'btn-icone peq', title: 'Substituir a imagem (PNG) desta textura', html: icone('upload', 14), onclick: () => app.substituirImagem(asset) }));
        if (nova) ac.append(el('button', { class: 'btn-icone peq', title: 'Remover este parâmetro novo', html: icone('x', 14), onclick: () => app.definirTextura(r.chave, param, null) }));
        else if (asset !== orig) ac.append(el('button', { class: 'btn-icone peq', title: 'Voltar à textura original', html: icone('restaurar', 14), onclick: () => app.definirTextura(r.chave, param, orig) }));
      }
      linha.append(ac);
      corpo.append(linha);
    }
    if (r.editavel) {
      corpo.append(el('div', { class: 'acoes-linha' },
        semShader ? null : el('button', { class: 'btn peq', title: 'Acrescentar um parâmetro de textura que o shader deste material usa', onclick: () => app.adicionarParametroTextura(r.chave) }, icone('mais', 13), 'Adicionar textura'),
        el('button', { class: semShader ? 'btn-primario peq' : 'btn peq', title: 'Usar o shader e os parâmetros de outro material', onclick: () => app.escolherMaterialOrigem(r.chave) }, icone('copias', 13), 'Copiar material de…'),
        el('button', { class: 'btn peq', title: 'Pintar com uma cor lisa (textura branca do jogo + cor de tinta)', onclick: () => app.corSolida(r.chave) }, icone('pincel', 13), 'Cor sólida…')));
    }
    // cores e valores
    const tipos = base.vetores || {};
    const nomesVet = Object.keys(vet).filter((k) => tipos[k]);
    if (nomesVet.length) {
      const lista = el('div', { class: 'secao-corpo', style: { padding: '4px 0 0' } });
      for (const k of nomesVet) {
        const tipo = tipos[k].tipo;
        const v = vet[k];
        const alterado = v.some((x, i) => Math.abs(x - tipos[k].v[i]) > 1e-6);
        if (tipo === 'Color') {
          const c = new THREE.Color(v[0], v[1], v[2]);
          const inp = el('input', { type: 'color', value: '#' + c.getHexString(THREE.SRGBColorSpace), disabled: !r.editavel, title: 'Escolher cor' });
          inp.oninput = () => {
            const nc = new THREE.Color().setStyle(inp.value, THREE.SRGBColorSpace);
            app.definirVetor(r.chave, k, [nc.r, nc.g, nc.b, v[3]], true);
          };
          lista.append(el('div', { class: 'linha-prop' }, el('label', { title: k }, k), el('div', { class: 'cor-linha' },
            el('small', { style: { color: 'var(--texto-3)' } }, `${fmtNum(v[0], 2)} ${fmtNum(v[1], 2)} ${fmtNum(v[2], 2)}`),
            el('span', { style: { display: 'flex', gap: '4px', alignItems: 'center' } }, inp,
              alterado ? el('button', { class: 'btn-icone peq', title: 'Original', html: icone('restaurar', 13), onclick: () => app.definirVetor(r.chave, k, tipos[k].v, false) }) : ''))));
        } else {
          const nn = tipo === 'Scalar' ? 1 : tipo === 'Vec2' ? 2 : tipo === 'Vec3' ? 3 : 4;
          const box = el('div', { class: nn === 1 ? '' : nn === 4 ? 'quarteto' : 'trio', style: nn === 2 ? { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' } : {} });
          for (let i = 0; i < nn; i++) {
            const c = campoNumero({ valor: v[i], eixo: nn > 1 ? 'xyzw'[i] : '', passo: 0.01, casas: 3, passoCtrl: 0.1,
              aoMudar: (val) => { const nv = (reg.vetores?.[k] || v).slice(); nv[i] = val; app.definirVetor(r.chave, k, nv, true); } });
            c.marcar(alterado);
            if (!r.editavel) c.el.style.pointerEvents = 'none';
            box.append(c.el);
          }
          lista.append(el('div', { class: 'linha-prop' }, el('label', { title: k, style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, k), box));
        }
      }
      corpo.append(lista);
    }
    if (!r.editavel && r.particaoNova && !r.outroMvdb) corpo.append(nota(r.semGuid ? 'Seção nova do FBX que ainda não está no XML exportado da malha.' : 'Partição nova: ainda sem material no MeshVariationDb deste sub-mundo.'));
    else if (!r.editavel) corpo.append(nota('Sem entrada no MeshVariationDb deste sub-mundo: mostrando os valores do XML da malha, que o jogo não usa para o material.'));
    else if (r.outroMvdb) corpo.append(nota('Valores de outro MeshVariationDb: editar aqui muda aquele arquivo, não o deste sub-mundo.', 'alerta'));
    card.append(corpo);
    return card;
  }

  corAmostra(n, p, r) {
    const m = this.app.materiais.material(r.chave, r.reg, '');
    return '#' + m.color.getHexString(THREE.SRGBColorSpace);
  }

  // ------------------------------------------------------------------ vários
  varios(nos) {
    const md = this.md, app = this.app;
    const cab = el('div', { class: 'prop-cab' });
    cab.append(el('div', { class: 'titulo', html: icone('copias', 17) + `<h3>${fmtInt(nos.length)} itens selecionados</h3>` }));
    const tipos = {};
    nos.forEach((n) => { const t = rotuloTipo(n); tipos[t] = (tipos[t] || 0) + 1; });
    const tags = el('div', { class: 'etiquetas' });
    for (const [t, q] of Object.entries(tipos)) tags.append(el('span', { class: 'etiqueta' }, `${q} × ${t}`));
    const alt = nos.filter((n) => md.alterado(n)).length;
    if (alt) tags.append(el('span', { class: 'etiqueta azul' }, `${alt} alterados`));
    cab.append(tags);
    this.raiz.append(cab);
    const comJogo = nos.filter((n) => n.jogo);
    const ocultos = comJogo.filter((n) => md.ocultoNoJogoProprio(n)).length;
    const vis = [
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', onclick: () => app.definirVisEditor(nos.map((n) => n.id), false) }, icone('olhoFechado', 14), 'Ocultar no editor'),
        el('button', { class: 'btn peq', onclick: () => app.definirVisEditor(nos.map((n) => n.id), true) }, icone('olho', 14), 'Mostrar')),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', disabled: !comJogo.length || ocultos === comJogo.length, onclick: () => app.definirJogo(comJogo.map((n) => n.id), true) }, icone('jogoOff', 14), 'Ocultar no jogo'),
        el('button', { class: 'btn peq', disabled: !ocultos, onclick: () => app.definirJogo(comJogo.map((n) => n.id), false) }, icone('jogo', 14), 'Mostrar no jogo')),
    ];
    if (nos.length - comJogo.length) vis.push(nota(`${nos.length - comJogo.length} itens não podem ser ocultados no jogo sozinhos (grupos estáticos ou itens sem referência própria).`));
    this.raiz.append(secao('visibilidade', 'Visibilidade', vis));
    const movidos = nos.filter((n) => n.alvo && n.local.some((v, i) => Math.abs(v - n.local0[i]) > 1e-6));
    this.raiz.append(secao('transformacao', 'Transformação', [
      nota('Use o gizmo (<kbd>G</kbd> mover, <kbd>R</kbd> girar, <kbd>S</kbd> escalar) para transformar todos juntos, em volta do centro da seleção.'),
      el('div', { class: 'acoes-linha' },
        el('button', { class: 'btn peq', disabled: !movidos.length, onclick: () => app.redefinirTransformacoes(movidos) }, icone('restaurar', 14), `Voltar ao original${movidos.length ? ` (${movidos.length})` : ''}`),
        el('button', { class: 'btn peq', onclick: () => app.focar(nos.map((n) => n.id)) }, icone('alvo', 14), 'Enquadrar'),
        el('button', { class: 'btn peq', onclick: () => app.isolar() }, icone('isolar', 14), 'Isolar')),
    ]));
  }
}
