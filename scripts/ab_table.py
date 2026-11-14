"""The learned instance rankers' A/B record, from the engine's model registry, with three prospective cells re-scored
here from the frozen predictions and the runs' own result files.

Registry: engine/models/registry.json, lanes sched-netres-lb (which open instances a lower-bound
pass should run first), sched-netres-rerun (which misses of a short pass deserve a longer re-run) and
sched-netres-lb-params (which CP-SAT settings to use per instance). Every A/B record there gives each arm the same
number of runs at the same budget, judged by the runs actually made; verdict rule (engine/models/registry.py): more
finds wins (a find = a run whose proven bound exceeds its starting LB), then best value, then median; a challenger
becomes champion after two wins on two cells, one of them held out, and no loss.

Re-scored here (lane sched-netres-lb, model v1, predictions frozen in runs/sched/model_v1/pred_snapshot_20261107T120228Z
.tsv before the outcomes existed): the pass-3 remainder (lb/ rows that netres_lb_pass3.log printed after its first
22,690 lines), pass 3b (lb3b/) and pass 3c (lb3c/). K = 20% of the cell; model arm = the K highest predictions (ties by
plain order), control = the first K in the plain order (sets in netres.SETS order, ids ascending); finds as above.
The last two cells are scored in runs/sched/model_v1/prospective_pass3{b,c}.json but not yet entered in the registry.
Writes data/ab.tsv, data/ab_rescored.tsv and data/registry_netres.json (the three lanes verbatim, with the sha256 of
registry.json).
  nice -n 10 python3 -I scripts/ab_table.py"""
import hashlib
import json
import os
import re

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repository root
SCHED = os.path.join(ENGINE, "runs", "sched")
REG = os.path.join(ENGINE, "engine", "models", "registry.json")
PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
LANES = ["sched-netres-lb", "sched-netres-rerun", "sched-netres-lb-params"]
PLAIN_SETS = ["NR_SP", "NR_AD", "NR_TF", "NR_RC", "NR_VAR", "NR_RU", "NR_LA"]   # netres.SETS
PRED = os.path.join(SCHED, "model_v1", "pred_snapshot_20261107T120228Z.tsv")


def verdict(m, c):
    if m.get("finds", 0) != c.get("finds", 0):
        return "model" if m.get("finds", 0) > c.get("finds", 0) else "control"
    return "tie"


def kind(cell, lane=""):
    c = cell.lower()
    if lane == "sched-netres-lb-params":
        return "online"
    if "online" in c:
        return "online"
    if "prospective" in c:
        return "prospective"
    return "offline"


def finds_of(c):
    """(find, LB units) of one result row: a proven bound above the row's starting LB (record CLOSED or LB)."""
    rec = set(c[9].split("+"))
    lb = int(c[4])
    if "CLOSED" in rec and c[6].isdigit():
        return 1, int(c[6]) - lb
    if "LB" in rec and len(c) > 10 and c[10].strip().lstrip("-").isdigit():
        return 1, int(c[10]) - lb
    return 0, 0


def rows_of(sub):
    out = []
    for s in PLAIN_SETS:
        p = os.path.join(SCHED, s, sub, "RESULTS.tsv")
        if not os.path.exists(p):
            continue
        for line in open(p).read().splitlines()[1:]:
            c = line.split("\t")
            if len(c) >= 11 and c[4].isdigit() and c[5].isdigit():
                out.append((s, int(c[0]), c))
    return out


def pass3_after(first_lines):
    keys = set()
    for k, line in enumerate(open(os.path.join(SCHED, "netres_lb_pass3.log")), start=1):
        if k <= first_lines:
            continue
        f = line.split()
        if len(f) > 2 and f[0] in PLAIN_SETS and f[1].endswith(":") and f[1][:-1].isdigit():
            keys.add((f[0], int(f[1][:-1])))
    return keys


def score(rows, pred, frac=0.2):
    rows = [r for r in rows if (r[0], r[1]) in pred]
    n = len(rows)
    K = int(frac * n)
    plain = sorted(range(n), key=lambda i: (PLAIN_SETS.index(rows[i][0]), rows[i][1]))
    rank = {i: k for k, i in enumerate(plain)}
    model = sorted(range(n), key=lambda i: (-pred[(rows[i][0], rows[i][1])], rank[i]))
    y = [finds_of(r[2]) for r in rows]
    return {"n": n, "K": K, "base_rate": sum(v[0] for v in y) / n,
            "model_finds": sum(y[i][0] for i in model[:K]), "control_finds": sum(y[i][0] for i in plain[:K]),
            "model_units": sum(y[i][1] for i in model[:K]), "control_units": sum(y[i][1] for i in plain[:K]),
            "random_mean": K * sum(v[0] for v in y) / n}


def curve(rows, pred):
    """Cumulative finds after k runs in the model's order and in the plain order (k = 1..n)."""
    rows = [r for r in rows if (r[0], r[1]) in pred]
    n = len(rows)
    plain = sorted(range(n), key=lambda i: (PLAIN_SETS.index(rows[i][0]), rows[i][1]))
    rank = {i: k for k, i in enumerate(plain)}
    model = sorted(range(n), key=lambda i: (-pred[(rows[i][0], rows[i][1])], rank[i]))
    y = [finds_of(r[2])[0] for r in rows]
    cm = cp = 0
    out = []
    for k in range(n):
        cm += y[model[k]]
        cp += y[plain[k]]
        out.append((k + 1, cm, cp))
    return out


def main():
    blob = open(REG, "rb").read()
    reg = json.loads(blob)
    lanes = {k: reg["lanes"][k] for k in LANES}
    json.dump({"source": os.path.relpath(REG, ENGINE), "sha256": hashlib.sha256(blob).hexdigest(), "lanes": lanes},
              open(os.path.join(DATA, "registry_netres.json"), "w"), indent=1, ensure_ascii=False)
    pred = {}
    for line in open(PRED).read().splitlines()[1:]:
        s, i, lb, ub, p = line.split("\t")
        pred[(s, int(i))] = float(p)
    after = pass3_after(22690)
    cells = {
        "NetRes pass 3 remainder (prospective)": [r for r in rows_of("lb") if (r[0], r[1]) in after],
        "NetRes pass 3b at 40 s (prospective)": rows_of("lb3b"),
        "NetRes pass 3c (prospective)": rows_of("lb3c"),
    }
    with open(os.path.join(DATA, "ab_curves.tsv"), "w") as f:
        f.write("cell\tk\tmodel\tplain\tn\tfinds\n")
        for cell, rows in cells.items():
            cv = curve(rows, pred)
            n, tot = len(cv), cv[-1][1]
            for k, cm, cp in cv:
                if k % 10 == 0 or k == n:
                    f.write(f"{cell}\t{k}\t{cm}\t{cp}\t{n}\t{tot}\n")
    rescored = {}
    with open(os.path.join(DATA, "ab_rescored.tsv"), "w") as f:
        f.write("cell\tn\tK\tbase_rate\tmodel_finds\tcontrol_finds\trandom_mean\tmodel_units\tcontrol_units\t"
                "recorded_model\trecorded_control\tmatch\n")
        for cell, rows in cells.items():
            sc = score(rows, pred)
            ev = {"NetRes pass 3 remainder (prospective)": "prospective_remainder.json",
                  "NetRes pass 3b at 40 s (prospective)": "prospective_pass3b.json",
                  "NetRes pass 3c (prospective)": "prospective_pass3c.json"}[cell]
            rec = json.load(open(os.path.join(SCHED, "model_v1", ev)))["at"]["20%"]
            rm, rc = rec["model"]["finds"], rec["control"]["finds"]
            sc.update(recorded_model=rm, recorded_control=rc,
                      match=(sc["model_finds"], sc["control_finds"], sc["K"]) == (rm, rc, rec["K"]))
            rescored[cell] = sc
            f.write(f"{cell}\t{sc['n']}\t{sc['K']}\t{sc['base_rate']:.4f}\t{sc['model_finds']}\t{sc['control_finds']}\t"
                    f"{sc['random_mean']:.1f}\t{sc['model_units']}\t{sc['control_units']}\t{rm}\t{rc}\t{sc['match']}\n")
    out = []
    m750 = re.search(r"\.sample\((\d+)\)|sample, (\d+)\)", lanes["sched-netres-rerun"]["held_out_note"])
    online_n = (m750.group(1) or m750.group(2)) if m750 else ""
    for lane in LANES:
        for v in lanes[lane]["versions"]:
            for ab in v.get("ab", []):
                m, c = ab["model"], ab["control"]
                rnd = ab.get("random") or {}
                lohi = rnd.get("finds_2_5_to_97_5") or [None, None]
                out.append({"lane": lane, "version": v["version"], "status": v.get("status", ""), "cell": ab["cell"],
                            "kind": kind(ab["cell"], lane),
                            "control_arm": ab.get("control_arm") or ("v1" if "vs v1 champion" in ab["cell"] else "plain"),
                            "n": ab.get("test_rows") or ab.get("scored_rows") or (
                                online_n if "pass-3c misses at 40 s (online" in ab["cell"] else
                                m.get("runs") if lane == "sched-netres-lb-params" else
                                5 * m.get("runs") if "lb6" in ab["cell"] else ""), "K": m.get("runs"),
                            "model_finds": m.get("finds"), "control_finds": c.get("finds"),
                            "random_mean": rnd.get("finds_mean", ""), "random_lo": lohi[0] if lohi[0] is not None else "",
                            "random_hi": lohi[1] if lohi[1] is not None else "", "auc": ab.get("auc", ""),
                            "base_rate": ab.get("base_rate", ""), "verdict": verdict(m, c), "source": "registry",
                            "rules_note": ab.get("rules_note", ""),
                            "ref_lbv1": (ab.get("reference_sched_netres_lb_v1") or {}).get("finds",
                                        (ab.get("references_at_20") or {}).get("reference_sched_netres_lb_v1", {}).get(
                                            "finds", "") if isinstance((ab.get("references_at_20") or {}).get(
                                                "reference_sched_netres_lb_v1"), dict) else
                                        (ab.get("references_at_20") or {}).get("reference_sched_netres_lb_v1", ""))})
        if lane == "sched-netres-lb":
            for cell in ("NetRes pass 3b at 40 s (prospective)", "NetRes pass 3c (prospective)"):
                sc = rescored[cell]
                out.append({"lane": lane, "version": "v1", "status": "former champion", "cell": cell,
                            "kind": "prospective", "control_arm": "plain", "n": sc["n"], "K": sc["K"],
                            "model_finds": sc["model_finds"], "control_finds": sc["control_finds"],
                            "random_mean": round(sc["random_mean"], 1), "random_lo": "", "random_hi": "", "auc": "",
                            "base_rate": round(sc["base_rate"], 4),
                            "verdict": verdict({"finds": sc["model_finds"]}, {"finds": sc["control_finds"]}),
                            "source": "rescored here (registry: pending)", "rules_note": "", "ref_lbv1": ""})
    keys = list(out[0])
    with open(os.path.join(DATA, "ab.tsv"), "w") as f:
        f.write("\t".join(keys) + "\n")
        for r in out:
            f.write("\t".join(str(r[k]) for k in keys) + "\n")
    for cell, sc in rescored.items():
        print(cell, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in sc.items()})
    print(len(out), "A/B records")


if __name__ == "__main__":
    main()
