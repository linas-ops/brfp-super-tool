// Decodificação de DDS (DXT1/DXT3/DXT5 e 32 bits sem compressão) para RGBA — as texturas dos overlays.

export function lerDDS(buf) {
  const u8 = new Uint8Array(buf);
  const dv = new DataView(buf);
  if (u8.length < 128 || dv.getUint32(0, true) !== 0x20534444) throw new Error('DDS inválido');
  const h = dv.getUint32(12, true), w = dv.getUint32(16, true);
  const pfFlags = dv.getUint32(80, true);
  const fourcc = String.fromCharCode(u8[84], u8[85], u8[86], u8[87]);
  let off = 128;
  const out = new Uint8ClampedArray(w * h * 4);
  if (pfFlags & 4) {
    if (fourcc === 'DX10') off += 20;
    if (fourcc === 'DXT1') dxt(u8, off, w, h, out, 1);
    else if (fourcc === 'DXT3') dxt(u8, off, w, h, out, 3);
    else if (fourcc === 'DXT5') dxt(u8, off, w, h, out, 5);
    else throw new Error('Formato de DDS não suportado: ' + fourcc);
    return { w, h, rgba: out, formato: fourcc };
  }
  const bits = dv.getUint32(88, true);
  if (bits !== 32) throw new Error('DDS de ' + bits + ' bits não suportado');
  const mr = dv.getUint32(92, true), mg = dv.getUint32(96, true), mb = dv.getUint32(100, true), ma = dv.getUint32(104, true);
  const sh = (m) => { let s = 0; if (!m) return -1; while (!((m >>> s) & 1)) s++; return s; };
  const sr = sh(mr), sg = sh(mg), sb = sh(mb), sa = sh(ma);
  const temAlfa = (pfFlags & 1) && ma;
  for (let i = 0, n = w * h; i < n; i++) {
    const v = dv.getUint32(off + i * 4, true);
    out[i * 4] = (v >>> sr) & 255;
    out[i * 4 + 1] = (v >>> sg) & 255;
    out[i * 4 + 2] = (v >>> sb) & 255;
    out[i * 4 + 3] = temAlfa ? (v >>> sa) & 255 : 255;
  }
  return { w, h, rgba: out, formato: 'RGBA32' };
}

function cor565(c, a, i) {
  a[i] = ((c >> 11) & 31) * 255 / 31 | 0;
  a[i + 1] = ((c >> 5) & 63) * 255 / 63 | 0;
  a[i + 2] = (c & 31) * 255 / 31 | 0;
}

function dxt(u8, off, w, h, out, tipo) {
  const bw = Math.max(1, (w + 3) >> 2), bh = Math.max(1, (h + 3) >> 2);
  const tamBloco = tipo === 1 ? 8 : 16;
  const pal = new Uint8Array(16), alfa = new Uint8Array(16);
  for (let by = 0; by < bh; by++) {
    for (let bx = 0; bx < bw; bx++) {
      let p = off + (by * bw + bx) * tamBloco;
      if (p + tamBloco > u8.length) return;
      if (tipo === 3) {
        for (let k = 0; k < 8; k++) {
          const b = u8[p + k];
          alfa[k * 2] = (b & 15) * 17;
          alfa[k * 2 + 1] = (b >> 4) * 17;
        }
        p += 8;
      } else if (tipo === 5) {
        const a0 = u8[p], a1 = u8[p + 1];
        const tab = [a0, a1];
        if (a0 > a1) for (let k = 1; k < 7; k++) tab.push(((7 - k) * a0 + k * a1) / 7 | 0);
        else { for (let k = 1; k < 5; k++) tab.push(((5 - k) * a0 + k * a1) / 5 | 0); tab.push(0, 255); }
        // 48 bits de índices (3 por pixel)
        let bitsLo = u8[p + 2] | (u8[p + 3] << 8) | (u8[p + 4] << 16);
        let bitsHi = u8[p + 5] | (u8[p + 6] << 8) | (u8[p + 7] << 16);
        for (let k = 0; k < 8; k++) { alfa[k] = tab[bitsLo & 7]; bitsLo >>= 3; }
        for (let k = 8; k < 16; k++) { alfa[k] = tab[bitsHi & 7]; bitsHi >>= 3; }
        p += 8;
      }
      const c0 = u8[p] | (u8[p + 1] << 8), c1 = u8[p + 2] | (u8[p + 3] << 8);
      cor565(c0, pal, 0); pal[3] = 255;
      cor565(c1, pal, 4); pal[7] = 255;
      if (c0 > c1 || tipo !== 1) {
        for (let k = 0; k < 3; k++) {
          pal[8 + k] = (2 * pal[k] + pal[4 + k]) / 3 | 0;
          pal[12 + k] = (pal[k] + 2 * pal[4 + k]) / 3 | 0;
        }
        pal[11] = 255; pal[15] = 255;
      } else {
        for (let k = 0; k < 3; k++) { pal[8 + k] = (pal[k] + pal[4 + k]) >> 1; pal[12 + k] = 0; }
        pal[11] = 255; pal[15] = 0;
      }
      let idx = u8[p + 4] | (u8[p + 5] << 8) | (u8[p + 6] << 16) | (u8[p + 7] << 24);
      for (let k = 0; k < 16; k++) {
        const x = bx * 4 + (k & 3), y = by * 4 + (k >> 2);
        const c = (idx >>> (2 * k)) & 3;
        if (x < w && y < h) {
          const o = (y * w + x) * 4;
          out[o] = pal[c * 4]; out[o + 1] = pal[c * 4 + 1]; out[o + 2] = pal[c * 4 + 2];
          out[o + 3] = tipo === 1 ? pal[c * 4 + 3] : alfa[k];
        }
      }
    }
  }
}
