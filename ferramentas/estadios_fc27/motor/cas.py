"""Leitura dos assets nativos do FC 27 nos arquivos CAS do jogo, localizados pelo índice do cache do FET.

Toda leitura é conferida: os bytes guardados no offset do cache precisam ter o SHA-1 do cache (EBX/RES; chunks
quando o cache guarda um) e descomprimir para o tamanho original. A pasta de cada install chunk é descoberta por
essa conferência, nunca adivinhada. Os blocos Oodle são decodificados com o oo2core_9_win64.dll do próprio jogo.
"""
from __future__ import annotations
import ctypes
import hashlib
import struct
from pathlib import Path


class Cas:
    def __init__(self, jogo_dir, oodle_dll):
        self.jogo = Path(jogo_dir)
        self.oodle_dll = Path(oodle_dll)
        self._fn = None
        self._dirs = {}
        self._candidates = {}

    def _oodle(self):
        if self._fn is None:
            lib = ctypes.CDLL(str(self.oodle_dll))
            fn = lib.OodleLZ_Decompress
            fn.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_ssize_t, ctypes.c_int]
            fn.restype = ctypes.c_ssize_t
            self._fn = fn
        return self._fn

    def decompress(self, data):
        out = bytearray()
        p = 0
        while p < len(data):
            a, b = struct.unpack_from('>II', data, p)
            p += 8
            size, codec, n = a & 0xffffff, b >> 24, b & 0xfffff
            if a >> 24 or ((b >> 20) & 15) != 7:
                raise ValueError('cabeçalho de bloco CAS inválido')
            src = data[p:p + n]
            p += n
            if len(src) != n:
                raise ValueError('bloco CAS truncado')
            if codec == 0:
                raw = src
            elif codec in (17, 21, 25):
                dest = ctypes.create_string_buffer(size)
                got = self._oodle()(src, n, dest, size, 1, 0, 0, None, 0, None, None, None, 0, 3)
                if got != size:
                    raise ValueError(f'oodle devolveu {got}, esperado {size}')
                raw = dest.raw
            else:
                raise ValueError(f'codec CAS não suportado {codec}')
            if len(raw) != size:
                raise ValueError('tamanho do bloco CAS não confere')
            out += raw
        return bytes(out)

    def cas_files(self, patch, cas):
        key = (patch, cas)
        if key not in self._candidates:
            base = self.jogo / ('Patch' if patch else 'Data') / 'Win32'
            self._candidates[key] = sorted(base.rglob(f'cas_{cas:02d}.cas'))
        return self._candidates[key]

    def read_encoded(self, meta):
        """Bytes guardados (comprimidos) e o caminho do CAS, conferidos pelo SHA-1 quando o cache tem um."""
        patch = int(bool(meta['patch']))
        known = self._dirs.get((meta['installchunk'], patch))
        files = [known / f'cas_{meta["cas"]:02d}.cas'] if known else self.cas_files(patch, meta['cas'])
        sha1 = meta.get('sha1')
        for path in files:
            if not path.exists() or path.stat().st_size < meta['offset'] + meta['size']:
                continue
            with path.open('rb') as f:
                f.seek(meta['offset'])
                raw = f.read(meta['size'])
            if sha1 is None:
                if known:
                    return raw, path
                continue
            if hashlib.sha1(raw).hexdigest() == sha1:
                self._dirs[(meta['installchunk'], patch)] = path.parent
                return raw, path
        if known and sha1 is not None:
            self._dirs.pop((meta['installchunk'], patch))
            return self.read_encoded(meta)
        raise ValueError(f'dados CAS conferidos não encontrados para {meta.get("name", meta.get("id"))} '
                         '(o jogo foi atualizado depois do cache do FET? abra o FET para refazer o cache)')

    def read_asset(self, meta):
        encoded, path = self.read_encoded(meta)
        raw = self.decompress(encoded)
        if 'original_size' in meta and len(raw) != meta['original_size']:
            raise ValueError(f'descomprimido {len(raw)} != {meta["original_size"]} para {meta.get("name")}')
        return raw, encoded, path
