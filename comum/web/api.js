// BRFP Super Tool — chamadas ao servidor local da ferramenta (mesmo formato do Editor de Estádios).
export class ErroApi extends Error {}

export async function api(rota, dados = null) {
  let r;
  try {
    r = await fetch('/api/' + rota, dados === null ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados),
    });
  } catch {
    throw new ErroApi('Sem conexão com o servidor da ferramenta. Ela foi fechada? Abra de novo pelo BRFP Super Tool.');
  }
  let j;
  try { j = await r.json(); } catch { throw new ErroApi(`Resposta inválida do servidor (${r.status})`); }
  if (!r.ok) throw new ErroApi(j.erro || `Erro ${r.status}`);
  return j;
}
