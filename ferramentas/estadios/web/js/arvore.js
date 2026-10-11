// Árvore de objetos (outliner) virtualizada: só as linhas visíveis existem no DOM.
import { icone } from './icones.js';
import { esc, fmtInt } from './ui.js';
import { ehGrupo, rotuloTipo } from './modelo.js';

const ALTURA = 26;
const ICONE_TIPO = { mundo: 'estadio', subworld: 'mundo', worldpart: 'camadas', layer: 'camadas', smg: 'grade', membro: 'copias', inst: 'cubo', ref: 'cubo', prefab: 'prefab', luz: 'luz', marcador: 'pessoa' };
const sem = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export class Arvore extends EventTarget {
  constructor(raiz, modelo) {
    super();
    this.raiz = raiz;
    this.modelo = modelo;
    this.espaco = raiz.querySelector('#arvore-espaco');
    this.camada = raiz.querySelector('#arvore-linhas');
    this.abertos = new Set();
    this.texto = '';
    this.filtro = 'tudo';
    this.linhas = [];
    this.foco = -1;
    raiz.addEventListener('scroll', () => this.desenhar());
    new ResizeObserver(() => this.desenhar()).observe(raiz);
    this.camada.addEventListener('click', (e) => this.aoClicar(e));
    this.camada.addEventListener('dblclick', (e) => {
      const lin = e.target.closest('.linha');
      if (lin && !e.target.closest('.tog,.exp')) this.emitir('focar', { id: Number(lin.dataset.id) });
    });
    this.camada.addEventListener('contextmenu', (e) => {
      const lin = e.target.closest('.linha');
      if (!lin) return;
      e.preventDefault();
      const id = Number(lin.dataset.id);
      if (!this.modelo.selecao.has(id)) this.modelo.selecionar(id);
      this.emitir('menu', { id, x: e.clientX, y: e.clientY });
    });
    raiz.addEventListener('keydown', (e) => this.aoTeclar(e));
    for (const ev of ['jogo', 'visEditor', 'locais', 'gravado', 'material']) modelo.addEventListener(ev, () => this.atualizar(false));
    modelo.addEventListener('selecao', () => this.desenhar());
  }

  emitir(tipo, d) { this.dispatchEvent(new CustomEvent(tipo, { detail: d })); }

  carregar() {
    this.abertos = new Set();
    const nos = this.modelo.nos;
    if (nos.length) this.abertos.add(0);
    this.atualizar(true);
    this.raiz.scrollTop = 0;
  }

  definirBusca(t) { this.texto = sem(t.trim()); this.atualizar(true); }
  definirFiltro(f) { this.filtro = f; this.atualizar(true); }

  combina(n) {
    const md = this.modelo;
    if (this.texto) {
      const alvo = sem(n.rotulo + ' ' + n.nome + ' ' + (n.bp || '') + ' ' + (n.malhas || []).map((p) => p.m.split('/').pop()).join(' '));
      if (!alvo.includes(this.texto)) return false;
    }
    switch (this.filtro) {
      case 'geometria': return !!(n.malhas && n.malhas.length);
      case 'luzes': return n.tipo === 'luz';
      case 'pessoas': return n.tipo === 'marcador';
      case 'alterados': return md.alterado(n);
      case 'ocultos': return md.ocultoNoJogoProprio(n);
      case 'faltando': return n.faltando === 'blueprint' || (n.malhas || []).some((p) => !md.malhas[p.m]?.fbx);
      default: return true;
    }
  }

  atualizar(recalcular = true) {
    const nos = this.modelo.nos;
    if (!nos.length) { this.linhas = []; this.desenhar(); return; }
    const filtrando = this.texto || this.filtro !== 'tudo';
    let mostrar = null;
    if (filtrando) {
      mostrar = new Set();
      for (const n of nos) {
        if (n.pai < 0) continue;
        if (this.combina(n)) {
          mostrar.add(n.id);
          for (let p = n.pai; p >= 0 && !mostrar.has(p); p = nos[p].pai) mostrar.add(p);
        }
      }
      mostrar.add(0);
    }
    const linhas = [];
    const visitar = (id) => {
      const n = nos[id];
      if (n.removido || n.excluidaGravada) return;
      if (mostrar && !mostrar.has(id)) return;
      linhas.push(id);
      const aberto = filtrando ? n.filhos.some((f) => mostrar.has(f)) && (this.abertos.has(id) || !this.fechadosFiltro?.has(id)) : this.abertos.has(id);
      if (aberto) for (const f of n.filhos) visitar(f);
    };
    for (const n of nos) if (n.pai < 0) visitar(n.id);
    this.linhas = linhas;
    this.filtrando = filtrando;
    this.espaco.style.height = linhas.length * ALTURA + 'px';
    this.desenhar();
  }

  desenhar() {
    const md = this.modelo;
    const nos = md.nos;
    const h = this.raiz.clientHeight;
    const topo = this.raiz.scrollTop;
    const ini = Math.max(0, Math.floor(topo / ALTURA) - 6);
    const fim = Math.min(this.linhas.length, Math.ceil((topo + h) / ALTURA) + 6);
    if (!this.linhas.length) {
      this.camada.innerHTML = nos.length ? '<div class="arvore-vazia">Nada encontrado com esse filtro.</div>' : '';
      return;
    }
    let html = '';
    for (let i = ini; i < fim; i++) {
      const n = nos[this.linhas[i]];
      html += this.htmlLinha(n, i);
    }
    this.camada.innerHTML = html;
  }

  htmlLinha(n, i) {
    const md = this.modelo;
    const grupo = ehGrupo(n);
    const temFilhos = n.filhos.length > 0;
    const aberto = this.filtrando ? temFilhos && (this.abertos.has(n.id) || !this.fechadosFiltro?.has(n.id)) : this.abertos.has(n.id);
    const ocJ = md.ocultoNoJogoProprio(n);
    const ocJHerdado = !ocJ && md.ocultoNoJogo(n);
    const visE = n.visEditor;
    const falta = n.tipo !== 'luz' && (n.faltando === 'blueprint' || (n.malhas?.length && n.malhas.every((p) => !md.malhas[p.m]?.fbx)));
    const cls = ['linha', grupo ? 'grupo' : '', md.selecao.has(n.id) ? 'sel' : '', md.ativo === n.id ? 'ativa' : '', i === this.foco ? 'foco' : '',
      visE ? '' : 'oculto-editor', ocJ ? 'oculto-jogo' : '', falta ? 'faltando' : ''].join(' ');
    let classeTipo = grupo ? 't-grupo' : n.tipo === 'prefab' ? 't-prefab' : n.tipo === 'luz' || n.tipo === 'marcador' ? 't-luz' : 't-malha';
    if (falta && !grupo) classeTipo = 't-falta';
    const ic = falta && !grupo ? 'caixa' : ICONE_TIPO[n.tipo] || 'cubo';
    const tec = grupo && n.rotulo !== n.nome && ['worldpart', 'layer', 'subworld'].includes(n.tipo) ? `<span class="tec">${esc(n.nome)}</span>` : '';
    let marcas = '';
    if (md.alterado(n)) marcas += '<span class="mod" title="Alterado (não salvo)"></span>';
    if (n.ligado) marcas += `<span title="Ligado à lógica do jogo">${icone('ligado', 12)}</span>`;
    if (falta && !grupo) marcas += `<span title="${n.faltando === 'blueprint' ? 'Blueprint não exportado' : 'FBX não exportado'}">${icone('aviso', 12)}</span>`;
    const qtd = grupo && (n.nGeo || n.nLuz) ? `<span class="qtd">${fmtInt(n.nGeo || n.nLuz)}${!n.nGeo ? ' luzes' : ''}</span>` : '';
    const togJogo = n.jogo
      ? `<button class="tog ${ocJ ? 'jogo-off' : ocJHerdado ? 'off' : ''}" data-acao="jogo" title="${n.tipo === 'luz' ? (ocJ ? 'Apagada no jogo — clique para acender' : 'Acesa no jogo — clique para apagar') : (ocJ ? 'Oculto no jogo — clique para mostrar' : 'Aparece no jogo — clique para ocultar')}">${icone(ocJ ? 'jogoOff' : 'jogo', 15)}</button>`
      : '<span class="tog" style="visibility:hidden"></span>';
    return `<div class="${cls}" data-id="${n.id}" data-i="${i}" role="treeitem" aria-selected="${md.selecao.has(n.id)}" style="top:${i * ALTURA}px;padding-left:${4 + n.prof * 14}px" title="${esc(rotuloTipo(n))}: ${esc(n.nome)}">`
      + (temFilhos ? `<span class="exp ${aberto ? 'aberto' : ''}" data-acao="exp">${icone('seta', 13)}</span>` : '<span class="exp"></span>')
      + `<span class="tipo ${classeTipo}">${icone(ic, 14)}</span>`
      + `<span class="nome">${esc(n.rotulo)}${tec}</span>${qtd}<span class="marcas">${marcas}</span><span class="espaco"></span>`
      + togJogo
      + `<button class="tog ${visE ? '' : 'off'}" data-acao="olho" title="${visE ? 'Ocultar no editor (H)' : 'Mostrar no editor'}">${icone(visE ? 'olho' : 'olhoFechado', 15)}</button>`
      + '</div>';
  }

  alternarAberto(id, abrir) {
    const quer = abrir ?? !(this.filtrando ? (this.abertos.has(id) || !this.fechadosFiltro?.has(id)) : this.abertos.has(id));
    if (this.filtrando) {
      this.fechadosFiltro = this.fechadosFiltro || new Set();
      if (quer) { this.abertos.add(id); this.fechadosFiltro.delete(id); } else { this.abertos.delete(id); this.fechadosFiltro.add(id); }
    } else if (quer) this.abertos.add(id); else this.abertos.delete(id);
    this.atualizar(false);
  }

  aoClicar(e) {
    const lin = e.target.closest('.linha');
    if (!lin) return;
    const id = Number(lin.dataset.id);
    const acao = e.target.closest('[data-acao]')?.dataset.acao;
    this.raiz.focus({ preventScroll: true });
    if (acao === 'exp') {
      if (e.altKey || e.shiftKey) this.expandirTudo(id, !this.abertos.has(id));
      else this.alternarAberto(id);
      return;
    }
    if (acao === 'olho') { this.emitir('olho', { id, solo: e.ctrlKey || e.altKey }); return; }
    if (acao === 'jogo') { this.emitir('jogo', { id }); return; }
    this.foco = Number(lin.dataset.i);
    if (e.shiftKey && this.modelo.ativo >= 0) {
      const a = this.linhas.indexOf(this.modelo.ativo), b = this.linhas.indexOf(id);
      if (a >= 0 && b >= 0) {
        const [x, y] = a < b ? [a, b] : [b, a];
        this.modelo.selecionar(this.linhas.slice(x, y + 1), { modo: e.ctrlKey ? 'adicionar' : 'substituir', ativo: id });
        return;
      }
    }
    this.modelo.selecionar(id, { modo: e.ctrlKey ? 'alternar' : 'substituir' });
  }

  aoTeclar(e) {
    if (!this.linhas.length) return;
    let i = this.foco >= 0 ? this.foco : Math.max(0, this.linhas.indexOf(this.modelo.ativo));
    const id = this.linhas[i];
    const n = this.modelo.nos[id];
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); e.stopPropagation();
      i = Math.max(0, Math.min(this.linhas.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
      this.foco = i;
      this.modelo.selecionar(this.linhas[i], { modo: e.shiftKey ? 'adicionar' : 'substituir' });
      this.rolarPara(i);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault(); e.stopPropagation();
      if (n.filhos.length && !this.abertos.has(id)) this.alternarAberto(id, true);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault(); e.stopPropagation();
      if (this.abertos.has(id) && n.filhos.length) this.alternarAberto(id, false);
      else if (n.pai >= 0) { this.modelo.selecionar(n.pai); this.revelar(n.pai); }
    } else if (e.key === 'Enter') {
      e.preventDefault(); e.stopPropagation();
      this.emitir('focar', { id });
    }
  }

  rolarPara(i) {
    const y = i * ALTURA;
    const r = this.raiz;
    if (y < r.scrollTop) r.scrollTop = y;
    else if (y + ALTURA > r.scrollTop + r.clientHeight) r.scrollTop = y + ALTURA - r.clientHeight;
    this.desenhar();
  }

  revelar(id) {
    const nos = this.modelo.nos;
    let mudou = false;
    for (let p = nos[id].pai; p >= 0; p = nos[p].pai) if (!this.abertos.has(p)) { this.abertos.add(p); mudou = true; }
    if (mudou) this.atualizar(false);
    let i = this.linhas.indexOf(id);
    if (i < 0 && this.filtrando) { this.texto = ''; this.filtro = 'tudo'; this.emitir('filtroLimpo'); this.atualizar(false); i = this.linhas.indexOf(id); }
    if (i >= 0) {
      this.foco = i;
      const r = this.raiz;
      const y = i * ALTURA;
      if (y < r.scrollTop || y > r.scrollTop + r.clientHeight - ALTURA) r.scrollTop = Math.max(0, y - r.clientHeight / 3);
      this.desenhar();
    }
  }

  expandirTudo(id = null, abrir = true) {
    const nos = this.modelo.nos;
    const alvo = id === null ? nos.filter((n) => n.pai < 0) : [nos[id]];
    const limite = id === null ? 2 : 99;
    for (const r of alvo) {
      for (const d of this.modelo.descendentes(r)) {
        if (!d.filhos.length) continue;
        if (abrir && d.prof - r.prof < limite && d.tipo !== 'membro' && d.tipo !== 'smg' || (abrir && id !== null)) this.abertos.add(d.id);
        if (!abrir) this.abertos.delete(d.id);
      }
    }
    if (!abrir && id === null) this.abertos.add(0);
    this.atualizar(false);
  }
}
