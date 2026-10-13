// BRFP Super Tool — arquivos de referência tirados do jogo (modelos FBX, foto de miniface), que não vêm no pacote
// leve: aviso do que falta e importação do zip completo, de uma pasta ou dos próprios arquivos (rotas referencias /
// referencias_importar do servidor da ferramenta, comum/referencias.py). Usado pelos Conversores de Faces e de Corpos
// e pelo Criador de Minifaces.
import { api } from './api.js';
import { el, esc, modal, aviso, nota } from './ui.js';
import { icone } from './icones.js';

/** Diálogo "faltam as referências": explica e importa. Devolve o estado novo ({ok, faltam, msg}) ou null. */
export async function importarReferencias({ aoTerminar = null } = {}) {
  let ref;
  try { ref = await api('referencias'); } catch (e) { aviso(e.message, { tipo: 'erro' }); return null; }
  if (ref.ok) { if (aoTerminar) aoTerminar(ref); return ref; }
  const lista = el('ul', { class: 'lista-pacotes' }, ...ref.faltam.map((n) => el('li', { class: 'falta' }, el('span', { html: icone('baixar', 13) }), el('span', { class: 'mono' }, n), el('small', {}, 'falta'))));
  const corpo = el('div', { class: 'componentes-dlg' },
    el('p', { html: esc(ref.msg) }), lista,
    el('p', { class: 'mudo', html: 'Os arquivos são copiados para a pasta da ferramenta e ficam lá: as atualizações do Super Tool não apagam.' }));
  let final = null;
  const escolher = (modo) => async (bt) => {
    bt.disabled = true;
    let r;
    try { r = await api('referencias_importar', { modo }); } catch (e) { aviso(e.message, { tipo: 'erro', tempo: 8000 }); bt.disabled = false; return false; }
    bt.disabled = false;
    if (r.cancelado) return false;
    for (const li of lista.querySelectorAll('li')) {
      const n = li.querySelector('.mono').textContent;
      if (!r.faltam.includes(n)) { li.classList.remove('falta'); li.querySelector('span').innerHTML = icone('check', 13); li.querySelector('small').textContent = 'importado'; }
    }
    final = r;
    if (!r.ok) { aviso(`Importado: ${r.importados.join(', ')}. Ainda falta: ${r.faltam.join(', ')}.`, { tipo: 'aviso', tempo: 7000 }); return false; }
    aviso('Referências importadas', { tipo: 'sucesso', detalhe: r.importados.join(', ') });
    if (aoTerminar) aoTerminar(r);
    return true;
  };
  const m = modal({
    titulo: 'Faltam arquivos de referência', corpo,
    botoes: [
      { rotulo: 'Agora não', classe: 'btn', valor: null },
      { rotulo: 'Escolher pasta…', classe: 'btn', fn: escolher('pasta') },
      { rotulo: 'Escolher zip ou arquivos…', classe: 'btn-primario', padrao: true, fn: escolher('arquivos') },
    ],
  });
  await m.promessa;
  return final;
}

/** Nota com o botão "Importar referências…" para o painel da ferramenta (vazio quando não falta nada). */
export function notaReferencias(ref, aoClicar) {
  if (!ref || ref.ok !== false) return [];
  return [nota(esc(ref.msg), 'alerta'),
    el('div', { class: 'acoes-linha' }, el('button', { class: 'btn-primario peq', onclick: aoClicar }, icone('baixar', 12), 'Importar referências…'))];
}
