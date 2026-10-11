# -*- coding: utf-8 -*-
"""Editor de Compdata (BRFP Super Tool) — servidor local. Só biblioteca padrão.

    python servidor.py [pasta_do_compdata] [--porta 8770] [--sem-janela]

Toda edição altera só a memória do servidor; o disco só é tocado pelo Salvar, que copia os dez arquivos para
_backup_editor_AAAAMMDD_HHMMSS/ antes de gravar. Sem pasta na linha de comando, reabre a última usada.
"""
import argparse
import os
import sys
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "comum"))

import base  # noqa: E402
import compdata as M  # noqa: E402
import dados  # noqa: E402

VERSAO = "2.1"
PREFS = base.Prefs(os.path.join(AQUI, "preferencias.json"))
STATE = {"cd": None, "names": None, "path": None, "clipboard": None}
LOCK = threading.Lock()
ARQUIVOS = ("compobj", "compids", "settings", "standings", "advancement", "schedule", "tasks", "objectives",
            "initteams", "weather")


class Nomes(M.Names):
    """Nomes de times e competições: idioma e banco importados no Super Tool primeiro, a planilha .xlsx da pasta depois."""

    def __init__(self, path):
        super().__init__(path)
        self.planilha_times, self.planilha_comps = dict(self.teams), dict(self.comps)
        self.idioma = dados.idioma_atual()
        self.banco = dados.banco_atual()
        times = {}
        if self.banco:
            try:
                times = {int(t["teamid"]): t["nome"] for t in self.banco.times(self.idioma)}
            except (dados.ErroDados, KeyError, ValueError, OSError):
                times = {}
        self.teams = {**self.planilha_times, **times}
        self.n_banco = len(times)

    def comp(self, aid):
        if self.idioma:
            nm = self.idioma.competicao(aid)
            if nm:
                return nm
        return super().comp(aid)

    def texto(self, chave):
        return self.idioma.texto(chave) if self.idioma else None

    def fontes(self):
        out = []
        if self.banco:
            out.append(f"banco {dados.NOME_JOGO.get(self.banco.jogo, '')} ({self.n_banco} times)".replace(" ()", ""))
        if self.idioma:
            out.append(f"idioma ({len(self.idioma.textos):,} textos)".replace(",", "."))
        if self.planilha:
            out.append(f"planilha {self.planilha}")
        return out


def dados_mudaram():
    """True se o banco/idioma do Super Tool mudou desde que os nomes foram montados."""
    try:
        mt = os.path.getmtime(dados.FONTES)
    except OSError:
        mt = 0
    if STATE.get("dados_mtime") != mt:
        STATE["dados_mtime"] = mt
        return True
    return False


def atualizar_nomes():
    if STATE["path"] and dados_mudaram():
        STATE["names"] = Nomes(STATE["path"])


def eh_compdata(pasta):
    return bool(pasta) and os.path.isfile(os.path.join(pasta, "compobj.txt"))


def exige():
    if STATE["cd"] is None:
        raise base.ErroUsuario("Nenhuma pasta de compdata aberta.")
    return STATE["cd"]


def abrir(pasta):
    pasta = os.path.abspath(pasta)
    if not eh_compdata(pasta):
        raise base.ErroUsuario(f"Não achei compobj.txt em {pasta}")
    STATE["path"] = pasta
    STATE["cd"] = M.Compdata(pasta)
    dados_mudaram()
    STATE["names"] = Nomes(pasta)
    STATE["clipboard"] = None
    p = PREFS.ler()
    rec = [pasta] + [x for x in p.get("recentes", []) if os.path.normcase(x) != os.path.normcase(pasta)]
    PREFS.atualizar(ultima=pasta, recentes=rec[:8])


# ------------------------------------------------------------------ serialização
def tree_payload():
    cd, names = STATE["cd"], STATE["names"]
    kids = {}
    for i, n in enumerate(cd.nodes):
        kids.setdefault(n["parent"], []).append(i)
    slots = {}
    for r in cd.rows["standings"]:
        slots[int(r[0])] = slots.get(int(r[0]), 0) + 1
    return [{"id": i, "type": n["type"], "short": n["short"], "desc": n["desc"].strip(), "parent": n["parent"],
             "label": M.label_for(cd, names, i), "kids": len(kids.get(i, [])), "slots": slots.get(i, 0)}
            for i, n in enumerate(cd.nodes)]


def stage_label(nid):
    cd, names = STATE["cd"], STATE["names"]
    p = cd.nodes[nid]["parent"]
    return "" if p == -1 else M.label_for(cd, names, p)


def node_payload(nid):
    cd, names = STATE["cd"], STATE["names"]
    n = cd.nodes[nid]
    return {
        "id": nid, "type": n["type"], "short": n["short"], "desc": n["desc"], "parent": n["parent"],
        "label": M.label_for(cd, names, nid),
        "path": [{"id": a, "label": M.label_for(cd, names, a)} for a in reversed(cd.ancestors(nid))],
        "children": [{"id": c, "type": cd.nodes[c]["type"], "short": cd.nodes[c]["short"],
                      "label": M.label_for(cd, names, c), "slots": cd.slots_of(c)} for c in cd.children(nid)],
        "settings": cd.settings_of(nid), "slots": cd.slots_of(nid),
        "schedule": cd.rows_of("schedule", nid), "objectives": cd.rows_of("objectives", nid),
        "initteams": cd.rows_of("initteams", nid), "tasks": cd.tasks_of(nid),
        "teams": [{"id": t, "name": names.team(t) if names else None} for t in cd.teams_of(nid)],
        "adv_in": [{"src": s, "rank": r, "slot": sl, "src_label": M.label_for(cd, names, s), "src_path": stage_label(s)}
                   for s, r, sl in cd.adv_in(nid)],
        "adv_out": [{"rank": r, "dst": d, "slot": sl, "dst_label": M.label_for(cd, names, d), "dst_path": stage_label(d)}
                    for r, d, sl in cd.adv_out(nid)],
        "comp": cd.owning_comp(nid),
    }


def state_payload():
    cd = STATE["cd"]
    if cd is None:
        return {"aberto": False}
    v = cd.validate()
    clip = STATE["clipboard"]
    names = STATE["names"]
    return {"aberto": True, "path": STATE["path"], "dirty": cd.dirty, "can_undo": bool(cd._history),
            "can_redo": bool(cd._future), "counts": cd.line_counts(), "baseline": cd.baseline,
            "errors": v["errors"], "warnings": v["warnings"], "clipboard": clip["label"] if clip else None,
            "planilha": names.planilha if names else None, "n_times": len(names.teams) if names else 0,
            "fontes_nomes": names.fontes() if names else []}


# ------------------------------------------------------------------ rotas
def api_inicio(_):
    p = PREFS.ler()
    rec = [x for x in p.get("recentes", []) if eh_compdata(x)]
    return {"versao": VERSAO, "recentes": rec, "state": state_payload()}


def api_versao(_):
    return {"versao": VERSAO}


def api_tree(_):
    with LOCK:
        exige()
        atualizar_nomes()
        return {"nodes": tree_payload(), "state": state_payload()}


def api_node(q):
    with LOCK:
        exige()
        return node_payload(int(q["id"]))


def api_state(_):
    with LOCK:
        return state_payload()


def api_teams(_):
    with LOCK:
        atualizar_nomes()
    names = STATE["names"]
    items = [{"id": k, "name": v} for k, v in (names.teams if names else {}).items()]
    items.sort(key=lambda x: x["name"])
    return {"teams": items}


def api_vocab(_):
    return {"stage_types": M.STAGE_TYPES, "situations": M.MATCH_SITUATIONS, "comp_kinds": M.COMP_KINDS,
            "sort_keys": M.SORT_KEYS, "task_verbs": sorted(M.TASK_NODE_FIELDS), "node_types": M.NODE_TYPES,
            "setting_node_keys": sorted(M.SETTING_NODE_KEYS),
            # posições na linha completa do tasks.txt (comp, quando, verbo, f3, f4, f5, f6) que são ID de nó
            "task_node_fields": {k: list(v) for k, v in M.TASK_NODE_FIELDS.items()}}


def api_acao(p):
    """Todas as edições passam por aqui: {action, ...}. Responde com o resultado + o estado novo."""
    action = p.pop("action")
    with LOCK:
        res = act(action, p) or {}
        res["state"] = state_payload()
    return res


def act(action, p):
    if action == "open_path":
        path = os.path.abspath(p["path"])
        if not eh_compdata(path):
            raise base.ErroUsuario(f"Não achei compobj.txt em {path}")
        if STATE["cd"] is not None and STATE["cd"].dirty and not p.get("force"):
            return {"needs_force": True}
        abrir(path)
        return {"ok": True}
    if action == "browse_dir":
        return {"dir": base.dialogo("pasta", "Escolha a pasta do compdata (com compobj.txt)", STATE["path"])}
    if action == "explorer":
        base.abrir_no_explorer(STATE["path"] or base.raiz_trabalho())
        return {}
    if action == "close":
        if STATE["cd"] is not None and STATE["cd"].dirty and not p.get("force"):
            return {"needs_force": True}
        STATE.update(cd=None, names=None, path=None, clipboard=None)
        return {"ok": True}

    cd = exige()
    if action == "update_node":
        cd.update_node(int(p["id"]), p.get("short"), p.get("desc"))
    elif action == "add_node":
        return {"id": cd.add_node(int(p["parent"]), int(p["type"]), p.get("short") or "G1", p.get("desc") or " ")}
    elif action == "delete_node":
        return cd.delete_node(int(p["id"]))
    elif action == "move_node":
        nid = cd.move_node(int(p["id"]), int(p["delta"]))
        return {"id": nid, "ok": nid is not None}
    elif action == "set_slots":
        cd.set_slots(int(p["id"]), max(0, int(p["count"])))
    elif action == "set_settings":
        cd.set_settings(int(p["id"]), [[k, v] for k, v in p["rows"]])
    elif action == "set_teams":
        nid = int(p["id"])
        rows = [[k, v] for k, v in cd.settings_of(nid) if k != "info_special_team_id"]
        cd.set_settings(nid, [["info_special_team_id", str(int(t))] for t in p["teams"]] + rows)
    elif action == "set_rows":
        cd.set_file_rows(p["file"], int(p["id"]), p["rows"])
    elif action == "set_adv":
        cd.set_advancement(int(p["id"]), p["rows"])
    elif action == "set_tasks":
        cd.set_tasks(int(p["id"]), p["rows"])
    elif action == "copy_node":
        nid = int(p["id"])
        STATE["clipboard"] = {"data": cd.export_subtree(nid), "label": M.label_for(cd, STATE["names"], nid)}
        return {"label": STATE["clipboard"]["label"], "nodes": len(STATE["clipboard"]["data"]["nodes"])}
    elif action == "paste_node":
        if not STATE["clipboard"]:
            raise base.ErroUsuario("Nada copiado ainda.")
        return {"id": cd.import_subtree(int(p["parent"]), STATE["clipboard"]["data"])}
    elif action == "undo":
        return {"ok": cd.undo()}
    elif action == "redo":
        return {"ok": cd.redo()}
    elif action == "save":
        return {"backup": os.path.basename(cd.save() or "")}
    elif action == "reload":
        cd.load()
    elif action == "impact":
        return {"impact": cd.impact(int(p["id"]))}
    elif action == "wizard":
        return wizard(cd, p)
    else:
        raise base.ErroUsuario(f"Ação desconhecida: {action}")
    return {}


def wizard(cd, p):
    """Cria o esqueleto de uma competição: setup + grupos + mata-mata."""
    parent = int(p["parent"])
    code = (p.get("code") or "").strip()
    if not code.startswith("C"):
        code = "C" + code
    n_groups = max(1, int(p.get("groups") or 1))
    per_group = max(2, int(p.get("per_group") or 2))
    ko = max(0, int(p.get("ko_rounds") or 0))
    advancing = max(1, min(per_group, int(p.get("advancing") or 2)))
    two_legs = bool(p.get("two_legs", True))
    setup = bool(p.get("setup", True))
    kind = p.get("kind") or "CUP"

    cd.begin_batch()
    try:
        comp = cd.add_node(parent, 3, code, "TrophyName_Abbr15_" + code[1:])
        cd.set_settings(comp, [["asset_id", code[1:]], ["comp_type", kind], ["schedule_internationaldependency", "NONE"],
                               ["match_matchimportance", "65"]])
        stage_no = 0
        setup_group = None
        if setup:
            stage_no += 1
            st = cd.add_node(comp, 4, "S%d" % stage_no, "FCE_Setup_Stage")
            cd.set_settings(st, [["match_stagetype", "SETUP"]])
            setup_group = cd.add_node(st, 5, "G1", " ")
            cd.set_slots(setup_group, n_groups * per_group)

        stage_no += 1
        gs_stage = cd.add_node(comp, 4, "S%d" % stage_no, "FCE_Group_Stage" if n_groups > 1 else "FCE_League_Stage")
        cd.set_settings(gs_stage, [["match_stagetype", "LEAGUE"], ["match_matchsituation", "GROUP"]])
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        groups = []
        for k in range(n_groups):
            g = cd.add_node(gs_stage, 5, "G%d" % (k + 1), "FCE_Group_%s" % letters[k] if n_groups > 1 else " ")
            cd.set_slots(g, per_group)
            rows = [["num_games", "1"]] + [["standings_sort", s] for s in ("POINTS", "WINS", "GOALDIFF", "GOALSFOR")]
            rows += [["info_label_slot_adv_group", str(i)] for i in range(1, advancing + 1)]
            cd.set_settings(g, rows)
            groups.append(g)
        if setup_group is not None:
            for g in groups:
                for slot in range(1, per_group + 1):
                    cd.advancement.append([setup_group, 0, g, slot])

        prev = None
        names_by_size = {1: "FCE_Final", 2: "FCE_Semi_Finals", 4: "FCE_Quarter_Finals", 8: "FCE_Round_of_16",
                         16: "FCE_Round_of_32"}
        sit_by_size = {1: "FINAL", 2: "SEMI", 4: "QUARTER"}
        for r in range(ko):
            ties = 2 ** (ko - r - 1)
            stage_no += 1
            st = cd.add_node(comp, 4, "S%d" % stage_no, names_by_size.get(ties, "FCE_Round_1"))
            rows = [["match_stagetype", "KO2LEGS" if two_legs else "KO1LEG"],
                    ["match_matchsituation", sit_by_size.get(ties, "ROUNDX")]]
            rows += [["match_endruleko2leg2", "AGG"], ["match_endruleko2leg2", "PENS"]] if two_legs else \
                [["match_endruleko1leg", "PENS"]]
            cd.set_settings(st, rows)
            cur = []
            for t in range(ties):
                g = cd.add_node(st, 5, "G%d" % (t + 1), " ")
                cd.set_slots(g, 2)
                cd.set_settings(g, [["num_games", "2" if two_legs else "1"]])
                cur.append(g)
            if prev is None:
                feed = [(g, rank) for g in groups for rank in range(1, advancing + 1)]
                for i, tie in enumerate(cur):
                    for slot in (1, 2):
                        k = i * 2 + slot - 1
                        if k < len(feed):
                            cd.advancement.append([feed[k][0], feed[k][1], tie, slot])
            else:
                for i, tie in enumerate(cur):
                    if 2 * i < len(prev):
                        cd.advancement.append([prev[2 * i], 1, tie, 1])
                    if 2 * i + 1 < len(prev):
                        cd.advancement.append([prev[2 * i + 1], 1, tie, 2])
            prev = cur
        if prev and len(prev) == 1:
            cd.set_settings(prev[0], cd.settings_of(prev[0]) + [["info_slot_champ", "1"]])
        # só cria a task se houver de onde puxar os times (uma task pedindo N times sem lista nasceria quebrada)
        league = str(p.get("league") or "").strip()
        if league.isdigit():
            target = setup_group if setup_group is not None else groups[0]
            cd.tasks.append([str(comp), "start", "FillFromLeague", str(target), league, "0", "0"])
    finally:
        cd.end_batch()
    return {"id": comp}


ROTAS_GET = {"inicio": api_inicio, "versao": api_versao, "tree": api_tree, "node": api_node, "state": api_state,
             "teams": api_teams, "vocab": api_vocab}
ROTAS_POST = {"acao": api_acao, "inicio": api_inicio}


def main():
    ap = argparse.ArgumentParser(description="Editor de Compdata (BRFP Super Tool)")
    ap.add_argument("pasta", nargs="?", help="pasta com compobj.txt, settings.txt etc.")
    ap.add_argument("--porta", type=int, default=8770)
    ap.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    a = ap.parse_args()
    pasta = a.pasta or PREFS.ler().get("ultima")
    if pasta and eh_compdata(pasta):
        try:
            abrir(pasta)
            print(f"compdata: {STATE['path']} ({len(STATE['cd'].nodes)} nós, {len(STATE['names'].teams)} times)", flush=True)
        except Exception as ex:  # noqa: BLE001
            print(f"Não foi possível abrir {pasta}: {ex}", flush=True)
    handler = base.criar_handler(os.path.join(AQUI, "web"), ROTAS_GET, ROTAS_POST, nome="EditorCompdata/" + VERSAO)
    base.servir(handler, a.porta, "Editor de Compdata", VERSAO, sem_janela=a.sem_janela)


if __name__ == "__main__":
    main()
