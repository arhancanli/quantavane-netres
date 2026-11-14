"""Package the next NetRes lower-bound pass for Kaggle (7 Nov 2026): every instance still open on the dataset files on
disk (the values the Solutions Update lists now), starting its destructive caps at the best lower bound proved so far
(published LB, or ours from lb/ and lb3b/ when higher), SECS seconds each. Each task carries its own network and
resource profile, so the kernel needs no instance files: dataset/ = code/netres.py, code/rcpsp_cpsat.py, tasks.jsonl.
  .venv/bin/python -I runs/kaggle_netres/build.py [--seconds 120] [--sets NR_SP NR_AD ...] [--order FILE] [--out DIR]
Then: kaggle datasets version/create -p runs/kaggle_netres/dataset, and push the kernels made by make_kernels.py.
--order FILE (optional; without it the order is unchanged: sets in netres.SETS order, ids ascending): a TSV with
columns set, id (a header line and further columns are ignored), e.g. the lane's champion model's ranking
(engine/models/registry.json lane sched-netres-lb; engine/models/sched_netres_rank.py order SNAPSHOT TASKS.jsonl FILE).
The tasks it lists come first in its order, then every other task in the default order. --out DIR writes the package
somewhere else than dataset/ (default dataset/), so a ranked build never overwrites a package already pushed."""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED = os.path.join(HERE, "..", "sched")
sys.path.insert(0, SCHED)
import netres as N  # noqa: E402
import netres_lb as L  # noqa: E402
from rcpsp_cpsat import LB_PARAMS  # noqa: E402

ENGINE_SCHED = os.path.join(HERE, "..", "..", "engine", "sched")


def proved(s):
    """{id: highest lower bound we proved} from lb/, lb3b/, lb3c/ and lb4/ (Kaggle, split.py) RESULTS.tsv (column
    'bound'; a CLOSED row's value)."""
    out = {}
    for sub in ("lb", "lb3b", "lb3c", "lb4", "lb5", "lb6", "lb7", "lb8", "lbm"):
        p = os.path.join(SCHED, s, sub, "RESULTS.tsv")
        if not os.path.exists(p):
            continue
        for line in open(p).read().splitlines()[1:]:
            c = line.split("\t")
            if len(c) < 10:
                continue
            vals = []
            if len(c) > 10 and c[10].strip().lstrip("-").isdigit():
                vals.append(int(c[10]))
            if "CLOSED" in c[9].split("+") and c[6].isdigit():
                vals.append(int(c[6]) + 10**9)  # closed by us: drop it
            if vals:
                out[c[0]] = max(out.get(c[0], 0), max(vals))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--sets", nargs="*", default=N.SETS)
    ap.add_argument("--improved-only", action="store_true",
                    help="only instances where we already proved a bound above the published LB (push them further)")
    ap.add_argument("--order", default=None, help="TSV of set, id: these tasks first, in this order (default: none)")
    ap.add_argument("--out", default=os.path.join(HERE, "dataset"), help="package folder (default: dataset/)")
    ap.add_argument("--only-ordered", action="store_true", help="package only the tasks the --order file lists")
    ap.add_argument("--params-extra", default="", help="CP-SAT settings appended to LB_PARAMS (from the 7 Nov A/B, e.g. \"linearization_level: 2\")")
    a = ap.parse_args()
    out = a.out
    os.makedirs(os.path.join(out, "code"), exist_ok=True)
    shutil.copy(os.path.join(SCHED, "netres.py"), os.path.join(out, "code", "netres.py"))
    shutil.copy(os.path.join(ENGINE_SCHED, "rcpsp_cpsat.py"), os.path.join(out, "code", "rcpsp_cpsat.py"))
    rank = {}
    if a.order:
        for line in open(a.order):
            c = line.rstrip("\n").split("\t")
            if len(c) >= 2 and c[1].isdigit() and (c[0], int(c[1])) not in rank:
                rank[(c[0], int(c[1]))] = len(rank)
    n = skipped = 0
    lines = []
    with open(os.path.join(out, "tasks.jsonl"), "w") as f:
        for s in a.sets:
            cur = L.current_bounds(s)
            ours = proved(s)
            rows = {}
            for line in open(os.path.join(SCHED, s, "RESULTS.tsv")).read().splitlines()[1:]:
                c = line.split("\t")
                if len(c) >= 10:
                    rows[c[0]] = c
            for i, (lb, ub) in sorted(cur.items(), key=lambda kv: int(kv[0])):
                if lb >= ub or i not in rows:
                    continue
                start = max(lb, ours.get(i, 0))
                if a.improved_only and not ours.get(i, 0) > lb:
                    continue
                if a.only_ordered and (s, int(i)) not in rank:
                    continue
                if start >= ub:
                    skipped += 1
                    continue
                c = rows[i]
                net = N.network(c[1])
                cap, dem = N.resset(c[2])[int(c[3])]
                lines.append(((s, int(i)), json.dumps({"set": s, "id": int(i), "ref1": c[1], "ref2": c[2],
                                                       "ref3": int(c[3]), "pub_lb": lb, "lb": start, "ub": ub,
                                                       "hint": None, "secs": a.seconds, "params": (LB_PARAMS + " " + a.params_extra).strip(),
                                                       "destructive": True, "net": list(net), "res": [cap, dem]})))
                n += 1
        if rank:  # a stable sort: listed tasks by their rank, the rest after them in the default order
            lines.sort(key=lambda kv: rank.get(kv[0], len(rank)))
        for _, text in lines:
            f.write(text + "\n")
    print(f"{n} tasks ({a.seconds:.0f} s each) in {out}/tasks.jsonl; {skipped} skipped (closed or proved by us)"
          + (f"; {sum(1 for k, _ in lines if k in rank)} ordered by {a.order}" if rank else ""))


if __name__ == "__main__":
    main()
