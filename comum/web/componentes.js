// BRFP Super Tool — componentes: baixar o Python embutido e os pacotes que uma ferramenta usa (numpy, SciPy, OpenCV,
// Pillow), com progresso. Usado pelo Conversor de Faces e pelo Criador de Minifaces (rotas componentes /
// componentes_instalar do servidor da ferramenta) e pela página Componentes do Super Tool.
import { api } from './api.js';
import { el, esc, modal, aviso, nota } from './ui.js';
import { icone } from './icones.js';

export const mb = (n) => (n >= 1048576 ? `${Math.round(n / 1048576)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`);

/** Barra de progresso de uma tarefa {fase, msg, baixado, total}; devolve {el, atualizar(t)}. */
export function barraTarefa() {
  const msg = el('div', { class: 'tarefa-msg' });
  const barra = el('div', { class: 'barra-progresso' }, el('div'));
  const det = el('div', { class: 'tarefa-det mudo' });
  const raiz = el('div', { class: 'tarefa' }, msg, barra, det);
  const atualizar = (t) => {
    if (!t) return;
    msg.textContent = t.msg || '';
    const baixando = t.fase === 'baixando' && t.total;
    barra.classList.toggle('indeterminado', !baixando && t.ativa !== false && t.fase !== 'pronto' && t.fase !== 'erro');
    barra.firstChild.style.width = baixando ? `${(100 * t.baixado) / t.total}%` : t.fase === 'pronto' ? '100%' : '0%';
    det.textContent = baixando ? `${mb(t.baixado)} de ${mb(t.total)}` : t.fase === 'instalando' ? 'Extraindo na pasta runtime\\python…' : '';
  };
  return { el: raiz, atualizar };
}

/** Acompanha a tarefa de instalação pela rota GET 'componentes' até terminar. */
export async function acompanhar(rota, aoAtualizar) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 400));
    let info;
    try { info = await api(rota); } catch { continue; }
    const t = info.tarefa || {};
    aoAtualizar(t, info);
    if (!t.ativa) return { tarefa: t, info };
  }
}

/** Diálogo "faltam componentes" da ferramenta: mostra o que falta, baixa e instala. Devolve true se instalou. */
export async function instalarComponentes({ aoTerminar = null, rota = 'componentes', rotaInstalar = 'componentes_instalar' } = {}) {
  let info;
  try { info = await api(rota); } catch (e) { aviso(e.message, { tipo: 'erro' }); return false; }
  const g = info.grupo;
  const corpo = el('div', { class: 'componentes-dlg' });
  if (info.problema) corpo.append(nota(esc(info.problema), 'erro'));
  const lista = el('ul', { class: 'lista-pacotes' });
  const nomes = { numpy: 'numpy', scipy: 'SciPy', opencv: 'OpenCV', pillow: 'Pillow' };
  if (g.resumo) {                             // grupo grande (ex.: servidor da Transfermarkt): uma linha só
    const falta = !g.ok;
    lista.append(el('li', { class: falta ? 'falta' : '' }, el('span', { html: icone(falta ? 'baixar' : 'check', 13) }), g.resumo, el('small', {}, falta ? 'falta' : 'instalado')));
  } else {
    for (const p of g.pacotes) {
      const falta = g.faltam.includes(p) || g.desatualizados.includes(p);
      lista.append(el('li', { class: falta ? 'falta' : '' }, el('span', { html: icone(falta ? 'baixar' : 'check', 13) }), nomes[p] || p, el('small', {}, falta ? 'falta' : 'instalado')));
    }
  }
  if (!info.python.ok) lista.prepend(el('li', { class: 'falta' }, el('span', { html: icone('baixar', 13) }), `Python ${info.python.esperada} embutido`, el('small', {}, `${mb(info.python.tamanho)} · python.org`)));
  const total = g.download + (info.python.ok ? 0 : info.python.tamanho);
  corpo.append(el('p', { html: `O <b>${esc(g.nome)}</b> roda num Python próprio do Super Tool, dentro da pasta <span class="mono">runtime</span>. `
    + 'Os pacotes vêm do PyPI (versões fixas, conferidas pelo SHA-256) e ficam guardados: o download é feito uma vez só.' }), lista);
  const prog = barraTarefa();
  prog.el.hidden = true;
  corpo.append(prog.el);
  let instalou = false;
  let rodando = false;
  const ja = info.tarefa && info.tarefa.ativa;
  const m = modal({
    titulo: 'Componentes necessários', texto: g.ok ? 'Tudo instalado.' : `Download: ${mb(total)}`, corpo,
    botoes: [
      { rotulo: 'Fechar', classe: 'btn', valor: null },
      { rotulo: g.ok ? 'Reconferir' : `Baixar e instalar (${mb(total)})`, classe: 'btn-primario', padrao: true, desabilitado: !!info.problema,
        fn: async (bt) => {
          if (instalou) return true;
          if (rodando) return false;
          rodando = true;
          bt.disabled = true;
          prog.el.hidden = false;
          prog.atualizar({ ativa: true, fase: 'iniciando', msg: 'Preparando…' });
          try { await api(rotaInstalar, {}); } catch (e) { aviso(e.message, { tipo: 'erro' }); bt.disabled = false; rodando = false; return false; }
          const { tarefa: t } = await acompanhar(rota, (tt) => prog.atualizar(tt));
          rodando = false;
          if (t.fase === 'erro') {
            prog.atualizar(t);
            corpo.append(nota(esc(t.erro || 'Falhou.'), 'erro'));
            bt.disabled = false;
            bt.textContent = 'Tentar de novo';
            return false;
          }
          instalou = true;
          prog.atualizar({ ...t, fase: 'pronto', msg: t.msg || 'Componentes instalados.' });
          for (const li of lista.querySelectorAll('li.falta')) {
            li.classList.remove('falta');
            li.querySelector('span').innerHTML = icone('check', 13);
            li.querySelector('small').textContent = 'instalado';
          }
          bt.disabled = false;
          bt.textContent = 'Concluir';
          if (aoTerminar) aoTerminar();
          return false;
        } },
    ],
  });
  if (ja) {                                   // já há uma instalação em andamento (desta ou de outra janela)
    prog.el.hidden = false;
    acompanhar(rota, (tt) => prog.atualizar(tt)).then(({ tarefa }) => { if (tarefa.fase !== 'erro' && aoTerminar) aoTerminar(); });
  }
  await m.promessa;
  return instalou;
}
