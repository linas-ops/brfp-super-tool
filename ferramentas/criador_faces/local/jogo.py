"""Leitura do FC 27 instalado, pelo índice do cache do FIFA Editor Tool (motor dos Estádios FC 27).

Nada do jogo vem com a ferramenta: cabeças, peles e a textura dos olhos são lidas do jogo de quem usa.
"""
import os
import re
import struct

import numpy as np

from . import Erro, caminhos

caminhos()

RES_TEXTURA = 0x6BDE20BA
BASEHEAD_MASC = "content/character/createplayer/male_0/basehead_0_mesh"
PELE_BASE = "content/character/cranium/textures/uvlocked/skin/skin_base_%d_color"
OLHO_COR = "content/character/player/common/eye_common_color"
FORMATOS_BC = {54: "BC1", 55: "BC1", 56: "BC1", 57: "BC1", 58: "BC2", 59: "BC2", 60: "BC3", 61: "BC3"}


class Jogo:
    def __init__(self, fet_dir=None, jogo_dir=None):
        try:
            from motor.ambiente import Ambiente
            from motor.base import Falha
        except ImportError as ex:
            raise Erro("O criador próprio usa o leitor do jogo da ferramenta Estádios FC 27, que não está nesta cópia do "
                       "Super Tool (%s)." % ex) from ex
        self.Falha = Falha
        self.amb = Ambiente(fet_dir or None, jogo_dir or None)
        self._idx = None

    # ------------------------------------------------------------ estado (para a interface)
    def estado(self):
        a = self.amb
        cache = (a.fet / "fc27.cache") if a.fet else None
        tem_cache = bool(cache and cache.is_file())
        oodle = bool(a.jogo and (a.jogo / "oo2core_9_win64.dll").is_file())
        itens = [
            dict(id="fet", nome="FIFA Editor Tool", ok=bool(a.fet), caminho=str(a.fet or ""),
                 detalhe="" if a.fet else "não encontrado: escolha a pasta do FIFA Editor Tool"),
            dict(id="cache", nome="Cache do FC 27 no FET", ok=tem_cache, caminho=str(cache or ""),
                 detalhe="" if tem_cache else "abra o FC 27 no FET uma vez para ele criar o fc27.cache"),
            dict(id="jogo", nome="EA SPORTS FC 27", ok=bool(a.jogo) and oodle, caminho=str(a.jogo or ""),
                 detalhe="" if a.jogo and oodle else "não encontrado: escolha a pasta do jogo (a que tem o FC27.exe)"),
        ]
        return dict(itens=itens, ok=all(i["ok"] for i in itens), indice=self.indice_pronto() if tem_cache else False)

    def exigir(self):
        e = self.estado()
        for i in e["itens"]:
            if not i["ok"]:
                raise Erro("%s: %s." % (i["nome"], i["detalhe"]))

    def indice_pronto(self):
        try:
            return self.amb.indice_pronto()
        except OSError:
            return False

    def chave(self):
        """muda quando o FET refaz o cache (atualização do jogo): o modelo guardado é refeito"""
        return self.amb.chave_cache()

    # ------------------------------------------------------------ leitura
    def indice(self):
        if self._idx is None:
            self.exigir()
            orig = self.amb.exigir
            self.amb.exigir = lambda: None      # o índice não precisa do .NET 8 (só a conversão de estádios precisa)
            try:
                self._idx = self.amb.indice()
            except self.Falha as ex:
                raise Erro(str(ex)) from ex
            except RuntimeError as ex:          # falta o zstandard
                raise Erro(str(ex)) from ex
            finally:
                self.amb.exigir = orig
        return self._idx

    def tem(self, nome):
        return nome.lower() in self.indice()["res_by_name"]

    def res(self, nome):
        e = self.indice()["res_by_name"].get(nome.lower())
        if e is None:
            raise Erro("O jogo não tem %s." % nome)
        try:
            return self.amb.cas().read_asset(e)[0]
        except (ValueError, OSError) as ex:
            raise Erro("Não consegui ler %s do jogo: %s" % (nome.rsplit("/", 1)[-1], ex)) from ex

    def cabecas_masculinas(self):
        """nomes dos RES headmorphblend_<id>_<v>_<n> cujas cabeças usam a basehead_0 masculina"""
        c = self.indice()
        eb, part = c["ebx_by_name"], c["ebx_by_part"]
        out = []
        for n in c["res_by_name"]:
            if not re.search(r"/headmorphblend_\d+_\d+_\d+$", n):
                continue
            e = eb.get(n.replace("/headmorphblend_", "/headmorphpreset_"))
            if e is not None and any(d in part and part[d]["name"].lower() == BASEHEAD_MASC for d in e["dependencies"]):
                out.append(n)
        return sorted(out)

    def nome_blend(self, ident, uv=False):
        """nome do RES do morph (posição ou UV0) da cabeça de um jogador, pela terminação"""
        fim = "/headmorphblend%s_%s_0_0" % ("uv0" if uv else "", ident)
        for n in self.indice()["res_by_name"]:
            if n.endswith(fim):
                return n
        return None

    def textura(self, nome, lado_max=None):
        """textura do jogo -> float32 H x W x 4 (RGBA 0..1, sem correção de gama: os valores do arquivo)"""
        from motor.fifa16 import bcn
        raw = self.res(nome)
        fmt = struct.unpack_from("<I", raw, 0x0C)[0]
        w, h, _, fatias = struct.unpack_from("<HHHH", raw, 0x16)
        mips = raw[0x1E]
        cid = raw[0x28:0x38]
        tam = list(struct.unpack_from("<15I", raw, 0x38))[:max(1, mips)]
        if fmt not in FORMATOS_BC:
            raise Erro("Textura %s num formato que o criador não lê (%d)." % (nome.rsplit("/", 1)[-1], fmt))
        import uuid
        chunks = self.indice()["chunk_by_id"]
        chave = next((k for k in (str(uuid.UUID(bytes_le=cid)), str(uuid.UUID(bytes=cid))) if k in chunks), None)
        if chave is None:
            raise Erro("Não achei os pixels de %s no jogo." % nome.rsplit("/", 1)[-1])
        try:
            dados = self.amb.cas().read_asset(chunks[chave])[0]
        except (ValueError, OSError) as ex:
            raise Erro("Não consegui ler os pixels de %s: %s" % (nome.rsplit("/", 1)[-1], ex)) from ex
        inicio = sum(tam) - len(dados)          # o chunk pode trazer só os mips menores
        m, acum = 0, 0
        while acum < inicio and m < len(tam) - 1:
            acum += tam[m]
            m += 1
        while lado_max and m < len(tam) - 1 and max(w >> m, h >> m) > lado_max:
            acum += tam[m]
            m += 1
        ww, hh = max(1, w >> m), max(1, h >> m)
        bruto = dados[acum - inicio:acum - inicio + tam[m]]
        if FORMATOS_BC[fmt] == "BC2":           # cor como no BC3 (o alfa explícito de 4 bits não é usado aqui)
            nb = max(1, (ww + 3) // 4) * max(1, (hh + 3) // 4)
            blk = np.frombuffer(bruto[:nb * 16], np.uint8).reshape(nb, 16)
            img = bcn._blocks_to_image(bcn.decode_bc1_colour(blk[:, 8:], punch=False), ww, hh)
        else:
            img = bcn.decode(bruto, ww, hh, FORMATOS_BC[fmt])
        return (img / 255.0).astype(np.float32)
