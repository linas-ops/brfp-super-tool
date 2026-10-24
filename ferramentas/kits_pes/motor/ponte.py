"""Ponte entre a interface do Conversor de Kits PES → FC (servidor) e o motor (numpy, SciPy e Pillow).

    python ponte.py detectar <arquivo.json>    arquivo.json = ["kit.png" | "pasta", ...]
    python ponte.py converter <arquivo.json>   arquivo.json = {"base", "saida", "escudo", "tecido", "substituir",
                                                               "itens": [{"id", "entrada", "teamid", "time", "tipo", "variacao"}]}
    python ponte.py previa <arquivo.json>      arquivo.json = {"entrada": "...", "saida": "previa.png"}
    python ponte.py base <pasta do kit>        tamanhos e time do kit base
    python ponte.py malha <jersey|shorts|socks|pes>

Escreve uma linha JSON por evento na saída padrão (o servidor lê ao vivo).
"""
import json
import os
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


def cmd_detectar(entradas):
    import conversor as X
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
            if not c.lower().endswith(X.EXT_IMAGEM):
                outros.append(rel)
                continue
            try:
                inf = X.info(c)
            except Exception as ex:  # noqa: BLE001 — imagem corrompida, formato que o Pillow não lê…
                inf = {"erro": str(ex) or type(ex).__name__}
            emitir(tipo="imagem", caminho=c, rel=rel, raiz=raiz, de_pasta=de_pasta, **inf)
        if os.path.isdir(ent):
            emitir(tipo="pasta", raiz=ent, outros=outros)
    emitir(tipo="fim")


def cmd_converter(job):
    import conversor as X
    for it in job["itens"]:
        emitir(tipo="inicio", id=it["id"])
        t = time.time()
        try:
            r = X.converter(it["entrada"], job["base"], it["saida"], it["teamid"], it["time"], it["tipo"], it.get("variacao") or 0,
                            job.get("escudo") or "apagar", job.get("tecido") or "base", bool(job.get("substituir")),
                            progresso=lambda f, msg, i=it["id"]: emitir(tipo="progresso", id=i, f=round(f, 3), msg=msg))
            emitir(tipo="ok", id=it["id"], s=round(time.time() - t, 1), **{k: r[k] for k in ("pasta", "rel", "previas", "avisos", "entrada_px")},
                   arquivos=len(r["arquivos"]))
        except Exception as ex:  # noqa: BLE001
            msg = str(ex) if isinstance(ex, X.ErroConversao) else traceback.format_exc(limit=4)
            emitir(tipo="erro", id=it["id"], erro=msg, s=round(time.time() - t, 1))
    emitir(tipo="fim")


def cmd_previa(d):
    import conversor as X
    emitir(tipo="previa", caminho=X.previa(d["entrada"], d["saida"]))


def cmd_base(pasta):
    import conversor as X
    emitir(tipo="base", **X.resumo_base(pasta))


def cmd_malha(qual):
    import conversor as X
    emitir(tipo="malha", **X.malha_previa(qual))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, arg = sys.argv[1], sys.argv[2]
    try:
        if cmd in ("detectar", "converter", "previa"):
            with open(arg, encoding="utf-8") as f:
                d = json.load(f)
            {"detectar": cmd_detectar, "converter": cmd_converter, "previa": cmd_previa}[cmd](d)
        elif cmd == "base":
            cmd_base(arg)
        elif cmd == "malha":
            cmd_malha(arg)
        else:
            sys.exit("comando desconhecido: " + cmd)
    except Exception as ex:  # noqa: BLE001
        emitir(tipo="falha", erro=str(ex) if type(ex).__name__ == "ErroConversao" else f"{type(ex).__name__}: {ex}",
               rastro=traceback.format_exc(limit=6))
        sys.exit(1)


if __name__ == "__main__":
    main()
