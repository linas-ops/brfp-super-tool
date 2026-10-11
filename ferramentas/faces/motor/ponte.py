"""Ponte entre a interface do Conversor de Faces (servidor em Python padrão) e o motor (numpy/scipy, py -3.12).

    py -3.12 ponte.py detectar <arquivo.json>    arquivo.json = ["caminho.fbx" | "pasta", ...]
    py -3.12 ponte.py converter <arquivo.json>   arquivo.json = {"textura": "fc26", "itens": [{"id", "entrada", "saida", "destino"}]}
    py -3.12 ponte.py previa <arquivo.fbx>

Escreve uma linha JSON por evento na saída padrão (o servidor lê ao vivo).
"""
import json
import os
import re
import sys
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def emitir(**kw):
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def info_fbx(caminho):
    import conversor as C
    from cena import Cena
    cena = Cena(caminho)
    jogo = C.detectar_jogo(cena)
    mats = sorted({m.mat for m in cena.malhas})
    lods = sorted({m.lod for m in cena.malhas})
    cab = cena.malha("head_mat", 0) if jogo else None
    ident = C._id_jogador(caminho, cena) if jogo else None
    out = {"jogo": jogo, "materiais": mats, "lods": len(lods), "vertices": int(len(cab.V)) if cab is not None else 0,
           "id": ident[0] if ident else None, "variacao": ident[1] if ident else None,
           "malha": next((m.mesh_name for m in cena.malhas), "")}
    if jogo:
        out["nomes"] = {d: C.nome_saida(caminho, d, cena) for d in ("fc26", "fc27")}
    return out


def cmd_detectar(entradas):
    for ent in entradas:
        ent = os.path.abspath(ent)
        if os.path.isfile(ent):
            arquivos = [(ent, os.path.basename(ent), os.path.dirname(ent), False)]
        elif os.path.isdir(ent):
            arquivos = []
            for raiz, _, nomes in os.walk(ent):
                for n in sorted(nomes):
                    c = os.path.join(raiz, n)
                    arquivos.append((c, os.path.relpath(c, ent), ent, True))
        else:
            emitir(tipo="erro", entrada=ent, erro="não encontrado")
            continue
        outros = []
        for c, rel, raiz, de_pasta in arquivos:
            if not c.lower().endswith(".fbx"):
                outros.append(rel)
                continue
            t = time.time()
            try:
                inf = info_fbx(c)
            except Exception as ex:  # noqa: BLE001 — FBX ASCII, corrompido...
                inf = {"jogo": None, "erro": str(ex) or type(ex).__name__}
            emitir(tipo="fbx", caminho=c, rel=rel, raiz=raiz, de_pasta=de_pasta, ms=int(1000 * (time.time() - t)), **inf)
        if os.path.isdir(ent):
            emitir(tipo="pasta", raiz=ent, outros=outros)
    emitir(tipo="fim")


def cmd_converter(job):
    import conversor as C
    for it in job["itens"]:
        emitir(tipo="inicio", id=it["id"])
        t = time.time()
        try:
            r = C.converter(it["entrada"], it["saida"], destino=it["destino"], layout_textura=job.get("textura", "fc26"))
            emitir(tipo="ok", id=it["id"], saida=r["saida"], origem=r["origem"], destino=r["destino"], metodos=r["metodos"],
                   avisos=r["avisos"], diferenca_max_cm=round(r.get("diferenca_max_cm", 0), 2), s=round(time.time() - t, 1))
        except Exception as ex:  # noqa: BLE001
            msg = str(ex) if isinstance(ex, C.ErroConversao) else traceback.format_exc(limit=4)
            emitir(tipo="erro", id=it["id"], erro=msg, s=round(time.time() - t, 1))
    emitir(tipo="fim")


def cmd_previa(caminho):
    """LOD0 da cabeça (e dos olhos/dentes) em coordenadas do jogo, para a prévia 3D."""
    from cena import Cena
    cena = Cena(caminho)
    partes = []
    for m in cena.malhas:
        if m.lod != 0 or m.mat not in ("head_mat", "eyes_mat", "teeth_mat"):
            continue
        partes.append({"mat": m.mat, "V": [round(float(x), 5) for x in m.V.ravel()], "T": [int(x) for x in m.T.ravel()]})
    emitir(tipo="previa", partes=partes)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, arg = sys.argv[1], sys.argv[2]
    try:
        if cmd == "detectar":
            with open(arg, encoding="utf-8") as f:
                cmd_detectar(json.load(f))
        elif cmd == "converter":
            with open(arg, encoding="utf-8") as f:
                cmd_converter(json.load(f))
        elif cmd == "previa":
            cmd_previa(arg)
        else:
            sys.exit("comando desconhecido: " + cmd)
    except Exception as ex:  # noqa: BLE001
        emitir(tipo="falha", erro=f"{type(ex).__name__}: {ex}", rastro=traceback.format_exc(limit=6))
        sys.exit(1)


if __name__ == "__main__":
    main()
