"""Leitor das cenas .fox2 do Fox Engine (PES 2021): entidades com as propriedades e os nomes resolvidos.

Layout (conferido nas cenas do Camp Nou do PES 2021):
  0x00  u32 0x786F62F2, u32 0x35, u32 entidades, u32 deslocamento da tabela de textos, u32 0x20 (início das entidades)
  entidade   u16 tamanho do cabeçalho (0x40), +0x06 'ent', +0x0A u32 endereço, +0x1A u16 versão, +0x1C u64 classe,
             +0x24 u16 propriedades fixas, u16 propriedades dinâmicas, +0x28 u32 início das propriedades, +0x2C u32 tamanho
             das fixas, +0x30 u32 tamanho de tudo
  propriedade  u64 nome, u8 tipo, u8 recipiente (0 lista fixa, 1 lista, 2 mapa por texto, 3 lista), u16 valores,
               u16 início dos valores (0x20), u16 tamanho da propriedade; os valores alinhados a 16 bytes
  textos     (u64 código, u32 tamanho, texto) até o código 0: nomes de classes, de propriedades e os valores de texto
Os nomes vêm como códigos de 48 bits; a tabela do próprio arquivo traz o texto de cada um.
"""
import struct

VAZIO = 0xB8A0BF169F98  # código do texto vazio
TIPOS = {0: ('b', 1), 1: ('B', 1), 2: ('h', 2), 3: ('H', 2), 4: ('i', 4), 5: ('I', 4), 6: ('q', 8), 7: ('Q', 8), 8: ('f', 4), 9: ('d', 8),
         10: ('?', 1)}
TAMANHO = {11: 8, 12: 8, 13: 8, 14: 16, 15: 16, 16: 16, 17: 36, 18: 64, 19: 16, 20: 8, 21: 8, 22: 32, 24: 16}


class Entidade:
    def __init__(self, endereco, classe, versao, props):
        self.endereco, self.classe, self.versao, self.props = endereco, classe, versao, props

    def __getitem__(self, k):
        return self.props.get(k)

    def um(self, k, padrao=None):
        v = self.props.get(k)
        if isinstance(v, list):
            return v[0] if v else padrao
        return padrao if v is None else v

    def __repr__(self):
        return f'<{self.classe} {self.endereco:#x} {self.um("name", "")!r}>'


class Fox2:
    def __init__(self, dados, nome=''):
        b = self.b = bytes(dados)
        self.nome = nome
        if len(b) < 0x20 or struct.unpack_from('<I', b, 0)[0] != 0x786F62F2:
            raise ValueError('não é FOX2: ' + nome)
        _, n, ptextos, pent = struct.unpack_from('<IIII', b, 4)
        self.textos = {VAZIO: ''}
        q = ptextos
        while q + 12 <= len(b):
            cod, ln = struct.unpack_from('<QI', b, q)
            if cod == 0:
                break
            self.textos[cod] = b[q + 12:q + 12 + ln].decode('utf8', 'replace')
            q += 12 + ln
        self.entidades = []
        q = pent
        for _ in range(n):
            cab, = struct.unpack_from('<H', b, q)
            if b[q + 6:q + 9] != b'ent':
                raise ValueError('entidade inválida em ' + nome)
            end, = struct.unpack_from('<I', b, q + 0x0A)
            versao, classe, nfix, ndin, pprop, tfix, ttudo = struct.unpack_from('<HQHHIII', b, q + 0x1A)
            props = {}
            p = q + pprop
            for _ in range(nfix + ndin):
                cod, tipo, rec, nval, pval, tprop = struct.unpack_from('<QBBHHH', b, p)
                props[self.texto(cod)] = self._valores(p + pval, tipo, rec, nval)
                p += tprop
            self.entidades.append(Entidade(end, self.texto(classe), versao, props))
            q += ttudo
        self.por_endereco = {e.endereco: e for e in self.entidades}

    def texto(self, cod):
        return self.textos.get(cod, f'#{cod:012x}')

    def _valor(self, q, tipo):
        b = self.b
        if tipo in TIPOS:
            f, t = TIPOS[tipo]
            return struct.unpack_from('<' + f, b, q)[0], t
        if tipo in (11, 12, 20):
            return self.texto(struct.unpack_from('<Q', b, q)[0]), 8
        if tipo in (13, 21):
            return ('@', struct.unpack_from('<Q', b, q)[0]), 8
        if tipo in (14, 24):
            return struct.unpack_from('<3f', b, q), 16
        if tipo in (15, 16, 19):
            return struct.unpack_from('<4f', b, q), 16
        if tipo == 17:
            return struct.unpack_from('<9f', b, q), 36
        if tipo == 18:
            return struct.unpack_from('<16f', b, q), 64
        if tipo == 22:
            a, c, d, e = struct.unpack_from('<QQQQ', b, q)
            return ('link', self.texto(a), self.texto(c), self.texto(d), e), 32
        raise ValueError(f'tipo de propriedade {tipo} desconhecido em {self.nome}')

    def _valores(self, q, tipo, rec, n):
        if rec == 2:  # mapa: código do texto + valor, cada par alinhado a 16 bytes
            out = {}
            for _ in range(n):
                k = self.texto(struct.unpack_from('<Q', self.b, q)[0])
                v, t = self._valor(q + 8, tipo)
                out[k] = v
                q += (8 + t + 15) // 16 * 16
            return out
        out = []
        for _ in range(n):
            v, t = self._valor(q, tipo)
            out.append(v)
            q += t
        return out

    def da_classe(self, classe):
        return [e for e in self.entidades if e.classe == classe]

    def ref(self, v):
        """Entidade apontada por um valor de ponteiro ('@', endereço), ou None."""
        if isinstance(v, tuple) and len(v) == 2 and v[0] == '@':
            return self.por_endereco.get(v[1])
        return None
