// Markdown simples -> HTML (títulos, listas, tabelas, código, negrito, itálico, links). Para LEIAME e PASSOS_FET.
import { esc } from './ui.js';

function inline(t) {
  let s = esc(t);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?!\w)/g, '$1<em>$2</em>');
  s = s.replace(/(^|\W)_([^_\s][^_]*)_(?=\W|$)/g, '$1<em>$2</em>');
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => /^https?:/.test(url)
    ? `<a href="${url}" target="_blank" rel="noopener">${txt}</a>` : `<span class="link-local" title="${url}">${txt}</span>`);
  return s;
}

export function markdown(texto) {
  const linhas = String(texto || '').replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let i = 0;
  let lista = null;
  const fecharLista = () => { if (lista) { out.push(`</${lista}>`); lista = null; } };
  while (i < linhas.length) {
    const l = linhas[i];
    if (/^```/.test(l)) {
      fecharLista();
      const bloco = [];
      i++;
      while (i < linhas.length && !/^```/.test(linhas[i])) bloco.push(linhas[i++]);
      i++;
      out.push(`<pre><code>${esc(bloco.join('\n'))}</code></pre>`);
      continue;
    }
    const h = l.match(/^(#{1,4})\s+(.*)$/);
    if (h) { fecharLista(); out.push(`<h${Math.min(3, h[1].length)}>${inline(h[2])}</h${Math.min(3, h[1].length)}>`); i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < linhas.length && /^\s*\|[\s:|-]+\|\s*$/.test(linhas[i + 1])) {
      fecharLista();
      const cel = (x) => x.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
      const cab = cel(l);
      i += 2;
      const corpo = [];
      while (i < linhas.length && /^\s*\|.*\|\s*$/.test(linhas[i])) corpo.push(cel(linhas[i++]));
      out.push('<table><thead><tr>' + cab.map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
        + corpo.map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
      continue;
    }
    const li = l.match(/^\s*([-*]|\d+\.)\s+(.*)$/);
    if (li) {
      const tipo = /\d/.test(li[1]) ? 'ol' : 'ul';
      if (lista !== tipo) { fecharLista(); out.push(`<${tipo}>`); lista = tipo; }
      let txt = li[2];
      while (i + 1 < linhas.length && /^\s{2,}\S/.test(linhas[i + 1]) && !/^\s*([-*]|\d+\.)\s/.test(linhas[i + 1])) txt += ' ' + linhas[++i].trim();
      out.push(`<li>${inline(txt)}</li>`);
      i++;
      continue;
    }
    if (!l.trim()) { fecharLista(); i++; continue; }
    fecharLista();
    const par = [l];
    while (i + 1 < linhas.length && linhas[i + 1].trim() && !/^(#{1,4}\s|```|\s*([-*]|\d+\.)\s|\s*\|)/.test(linhas[i + 1])) par.push(linhas[++i]);
    out.push(`<p>${inline(par.join(' '))}</p>`);
    i++;
  }
  fecharLista();
  return out.join('\n');
}
