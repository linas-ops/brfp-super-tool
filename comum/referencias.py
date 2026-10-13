"""BRFP Super Tool — arquivos de referência tirados do jogo (modelos FBX do Messi e dos corpos, foto de miniface).

Eles ficam fora do repositório e do pacote leve públicos (direitos da EA) e vêm só no pacote completo. Sem eles a
ferramenta avisa o que falta e importa os arquivos do zip completo, de uma pasta ou deles mesmos escolhidos à mão.

    REF = referencias.Referencias("Conversor de Faces", {"messi_158023_fc26.fbx": caminho, ...}, "converter as faces")
    REF.estado()   -> {"ok", "faltam", "msg"}       (vai no estado da ferramenta)
    REF.exigir()   -> ErroUsuario com a mensagem, se faltar algo
    REF.rotas()    -> GET referencias, POST referencias_importar
"""
import os
import shutil
import zipfile

import base

PASTAS_PULAR = {"runtime", ".git", "__pycache__", "node_modules", "cache", "$recycle.bin", "windows", "appdata"}
MAX_ARQUIVOS = 200000      # pasta escolhida muito grande (ex.: o disco inteiro): para de procurar


class Referencias:
    def __init__(self, ferramenta, arquivos, uso):
        self.ferramenta = ferramenta
        self.arquivos = dict(arquivos)          # nome do arquivo -> onde ele tem que ficar
        self.uso = uso

    def faltam(self):
        return [n for n, c in self.arquivos.items() if not os.path.isfile(c)]

    def msg(self, faltam=None):
        faltam = self.faltam() if faltam is None else faltam
        if not faltam:
            return ""
        return (f"Para {self.uso}, o {self.ferramenta} precisa de {'um arquivo' if len(faltam) == 1 else 'arquivos'} "
                f"de referência tirado{'' if len(faltam) == 1 else 's'} do jogo ({', '.join(faltam)}), que não "
                f"{'vem' if len(faltam) == 1 else 'vêm'} no pacote leve do Super Tool. Peça o pacote completo a quem te passou a ferramenta e clique em "
                "Importar referências: dá para escolher o zip completo, a pasta dele ou os próprios arquivos.")

    def estado(self):
        f = self.faltam()
        return {"ok": not f, "faltam": f, "msg": self.msg(f)}

    def exigir(self):
        f = self.faltam()
        if f:
            raise base.ErroUsuario(self.msg(f))

    # -------------------------------------------------------------- importar
    def _de_zip(self, caminho, procurar, achados):
        try:
            with zipfile.ZipFile(caminho) as z:
                for i in z.infolist():
                    nome = i.filename.rsplit("/", 1)[-1].lower()
                    if nome in procurar and nome not in achados and not i.is_dir():
                        achados[nome] = ("zip", caminho, i.filename)
        except (zipfile.BadZipFile, OSError):
            pass

    def _de_pasta(self, pasta, procurar, achados):
        vistos = 0
        zips = []
        for dp, dn, fn in os.walk(pasta):
            dn[:] = [d for d in dn if d.lower() not in PASTAS_PULAR]
            for f in fn:
                n = f.lower()
                if n in procurar and n not in achados:
                    achados[n] = ("arquivo", os.path.join(dp, f), None)
                elif n.endswith(".zip") and "super tool" in n:
                    zips.append(os.path.join(dp, f))
            vistos += len(fn)
            if len(achados) == len(procurar) or vistos > MAX_ARQUIVOS:
                break
        for z in zips:                          # zip do pacote completo guardado dentro da pasta
            if len(achados) < len(procurar):
                self._de_zip(z, procurar, achados)

    def importar(self, origens):
        """Procura os arquivos que faltam (pelo nome) nos arquivos, zips e pastas escolhidos e copia para o lugar."""
        procurar = {n.lower(): n for n in self.faltam()}
        achados = {}
        for o in origens:
            o = os.path.abspath(o)
            if os.path.isdir(o):
                self._de_pasta(o, procurar, achados)
            elif o.lower().endswith(".zip"):
                self._de_zip(o, procurar, achados)
            elif os.path.basename(o).lower() in procurar:
                achados.setdefault(os.path.basename(o).lower(), ("arquivo", o, None))
        importados = []
        for chave, (tipo, origem, membro) in achados.items():
            nome = procurar[chave]
            destino = self.arquivos[nome]
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            tmp = destino + ".novo"
            if tipo == "zip":
                with zipfile.ZipFile(origem) as z, z.open(membro) as src, open(tmp, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            else:
                shutil.copyfile(origem, tmp)
            os.replace(tmp, destino)
            importados.append(nome)
        return importados

    # -------------------------------------------------------------- rotas
    def rotas(self, ao_importar=None):
        def get(_):
            return self.estado()

        def post(d):
            faltavam = self.faltam()
            if not faltavam:
                return {"importados": [], **self.estado()}
            if d.get("modo") == "pasta":
                r = base.dialogo("pasta", "Pasta do pacote completo do BRFP Super Tool (ou com os arquivos de referência)")
                origens = [r] if r else []
            else:
                exts = sorted({os.path.splitext(n)[1].lower() for n in faltavam})
                r = base.dialogo("abrir", "Zip completo do BRFP Super Tool ou os arquivos de referência",
                                 tipos=[("Zip completo ou referências", ";".join(["*.zip"] + ["*" + e for e in exts])),
                                        ("Todos", "*.*")], multiplo=True)
                origens = r or []
            if not origens:
                return {"cancelado": True, "importados": [], **self.estado()}
            importados = self.importar(origens)
            if not importados:
                raise base.ErroUsuario(f"Não achei {', '.join(faltavam)} no que foi escolhido. Eles vêm no pacote "
                                       "completo do Super Tool (pasta ferramentas, dentro de motor/referencia ou web).")
            if ao_importar:
                ao_importar()
            return {"importados": importados, **self.estado()}
        return {"referencias": get}, {"referencias_importar": post}
