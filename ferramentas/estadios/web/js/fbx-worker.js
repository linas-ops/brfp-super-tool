// Worker: baixa e lê FBX fora da thread da interface.
import { lerFBX } from './fbx.js';

self.onmessage = async (e) => {
  const { id, url, buffer } = e.data;
  try {
    const buf = buffer || await (await fetch(url)).arrayBuffer();
    const r = await lerFBX(buf);
    const transf = [];
    for (const s of r.secoes) {
      for (const k of ['posicoes', 'normal', 'uv0', 'uv1', 'cor', 'indices']) if (s[k]) transf.push(s[k].buffer);
    }
    self.postMessage({ id, ok: true, fbx: r, tamanho: buf.byteLength }, transf);
  } catch (err) {
    self.postMessage({ id, ok: false, erro: String(err && err.message || err) });
  }
};
