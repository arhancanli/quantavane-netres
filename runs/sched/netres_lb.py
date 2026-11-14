"""NetRes lower-bound pass: proven lower bounds on unclosed NetRes instances (every RESULTS.tsv row of the id has a
record without CLOSED or UB), by runs/sched/netres.py solve() with destructive caps (rcpsp_cpsat.destructive(): caps
T = published LB, LB + 1, ... below the published UB, each a model whose one extra constraint is makespan <= T;
INFEASIBLE at T proves the optimum >= T + 1) and the lower-bound propagators (rcpsp_cpsat.LB_PARAMS), SECS seconds per
instance. --plain: one run capped at the published UB with the best known schedule as hint (netres_pass2.py's run).

Rows go to NR_<set>/lb/RESULTS.tsv (RESULTS.tsv's columns and bound), never to NR_<set>/RESULTS.tsv: netres_pass2.py
appends there with buffered writes, so a second writer could land inside one of its lines. Schedules that are records
(UB, CLOSED) go to NR_<set>/lb/SOLUTIONS.txt; check them with
  python3 -I independent/rcpsp_check_netres.py runs/sched/NR_<set>/NR_<set>.csv runs/sched/NR_<set>/lb/SOLUTIONS.txt \
      runs/sched/NR_SP/inst
(writes lb/VALID.txt, which make_upload.py reads). Ids already in lb/RESULTS.tsv are skipped. --sample N takes a
seeded random sample of N ids over the given sets (default all seven), else every unclosed id, set by set.
Nothing is uploaded from here.
  nice -n 10 .venv/bin/python -I runs/sched/netres_lb.py [--workers 3] [--seconds 30] [--sample N] [--seed 1] [--plain]
                                                         [SET ...]"""
import argparse
import concurrent.futures as cf
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netres as N  # noqa: E402
from rcpsp_cpsat import LB_PARAMS  # noqa: E402  (netres puts engine/sched on the path)

COLS = "id\tref1\tref2\tref3\tpub_lb\tpub_ub\tours\tstatus\tsecs\trecord\tbound\n"


def unclosed(ds):
    """[(id, RESULTS row)] of the set's ids without a CLOSED or UB record, minus those already in lb/RESULTS.tsv."""
    d = os.path.join(N.HERE, ds)
    res = os.path.join(d, "RESULTS.tsv")
    if not os.path.exists(res):
        return []
    rows, closed = {}, set()
    for line in open(res).read().splitlines()[1:]:
        c = line.split("\t")
        if len(c) < 10 or not c[4].isdigit() or not c[5].isdigit():   # a partial last line, or no bounds
            continue
        rows[c[0]] = c
        if {"CLOSED", "UB"} & set(c[9].split("+")):
            closed.add(c[0])
    lbres = os.path.join(d, "lb", "RESULTS.tsv")
    done = {l.split("\t")[0] for l in open(lbres).read().splitlines()[1:]} if os.path.exists(lbres) else set()
    return [(ds, i, c) for i, c in rows.items() if i not in closed and i not in done and int(c[4]) < int(c[5])]


def current_bounds(ds):
    """{id: (LB, UB)} of the dataset file on disk (NR_<set>/NR_<set>.csv), as the Solutions Update lists them."""
    out = {}
    for line in open(os.path.join(N.HERE, ds, ds + ".csv"), encoding="latin-1"):
        f = line.split(";")
        if f[0].isdigit() and len(f) > 8 and f[4].isdigit() and f[7].isdigit():
            out[f[0]] = (int(f[4]), int(f[7]))
    return out


def best_known(ds, ids):
    out, on = {}, False
    for line in open(os.path.join(N.HERE, ds, ds + "_BKS.csv"), encoding="latin-1"):
        c = line.rstrip("\r\n").split(";")
        if c[0] == "ID":
            on = True
        elif on and c[0] in ids:
            out[c[0]] = [int(x) for x in c[4:] if x.strip().isdigit()]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sets", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--sample", type=int, default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--plain", action="store_true", help="one run capped at the published UB, hinted (no ascent)")
    ap.add_argument("--current", action="store_true", help="start from the LB and UB of the dataset file on disk "
                    "(refreshed from the site) instead of the RESULTS row's; ids closed there are skipped")
    a = ap.parse_args()
    sets = a.sets or N.SETS
    if any(s not in N.SETS for s in sets):
        sys.exit(f"unknown set in {sets}; known: {' '.join(N.SETS)}")
    cands = [x for s in sets for x in unclosed(s)]
    if a.current:
        # 7 Nov 2026: the site applied our NetRes files of 3 Nov, so the 1 Nov values in RESULTS.tsv start the caps
        # below bounds already proved and listed
        cur = {s: current_bounds(s) for s in sets}
        cands = [(ds, i, c[:4] + [str(cur[ds][i][0]), str(cur[ds][i][1])] + c[6:]) for ds, i, c in cands
                 if i in cur[ds] and cur[ds][i][0] < cur[ds][i][1]]
    if a.sample is not None and a.sample < len(cands):
        cands = random.Random(a.seed).sample(cands, a.sample)
    print(f"{time.strftime('%F %T')}: {len(cands)} unclosed instances, {a.seconds:.0f} s each, {a.workers} workers, "
          f"{'plain' if a.plain else 'destructive'} runs", flush=True)
    tasks = []
    for s in sets:
        mine = [(i, c) for ds, i, c in cands if ds == s]
        if not mine:
            continue
        hints = best_known(s, {i for i, _ in mine}) if a.plain else {}
        for i, c in mine:
            tasks.append({"set": s, "id": int(i), "ref1": c[1], "ref2": c[2], "ref3": int(c[3]), "lb": int(c[4]),
                          "ub": int(c[5]), "hint": hints.get(i), "secs": a.seconds, "params": LB_PARAMS,
                          "destructive": not a.plain})
    files = {}
    for s in {t["set"] for t in tasks}:
        d = os.path.join(N.HERE, s, "lb")
        os.makedirs(d, exist_ok=True)
        res = os.path.join(d, "RESULTS.tsv")
        if not os.path.exists(res):
            open(res, "w").write(COLS)
        files[s] = (open(res, "a"), open(os.path.join(d, "SOLUTIONS.txt"), "a"))
    n_lb = n_rec = 0
    with cf.ProcessPoolExecutor(max_workers=a.workers) as pool:
        for fu in cf.as_completed([pool.submit(N.solve, t) for t in tasks]):
            try:
                t, starts, status, sec = fu.result()
            except Exception as exc:
                print("task failed:", repr(exc)[:200], flush=True)
                continue
            ours, record, note = N.outcome(t, starts, status)
            out, sol = files[t["set"]]
            if {"UB", "CLOSED"} & set(record.split("+")):
                sol.write(f"{t['id']};" + ";".join(map(str, starts)) + "\n")
                sol.flush()
                n_rec += 1
            n_lb += "LB" in record.split("+")
            out.write(N.row(t, ours, status, sec, record))
            out.flush()
            print(f"{t['set']} {t['id']}: LB {t['lb']} UB {t['ub']} bound {t['bound']} ours {ours} {status} "
                  f"{sec:.1f} s {record}{'  ' + note if note else ''}", flush=True)
    for out, sol in files.values():
        out.close()
        sol.close()
    print(f"netres lb pass done {time.strftime('%F %T')}: {n_lb} bounds above the published LB, {n_rec} schedule "
          f"records, of {len(tasks)}", flush=True)


if __name__ == "__main__":
    main()
