"""Does the best known schedule as a hint matter in the 3-second closure runs (stage U1)? A side-by-side ablation on a
seeded random sample of the instances open on 1 Nov 2026 that the site's best known solutions file of 1 Nov covers
(the only ones U1 could hint): the paper's own interval model (scripts/instances.py data,
one cumulative per resource, objective min S_end, cap S_end <= the published UB of 1 Nov), CP-SAT, 1 worker, SECONDS
each, once with the 1 Nov best known schedule as the hint and once without; the two runs of an instance are submitted
next to each other, in alternating order. The hint is checked to be a feasible schedule of makespan UB first.
Hint source: runs/sched/NR_<set>/NR_<set>_BKS.20261101.csv (the site's best known solutions of
1 Nov). Writes data/ablation_hint.tsv.
  nice -n 10 python3 -I scripts/ablation_hint.py [--n 300] [--seconds 3] [--jobs 4]"""
import argparse
import concurrent.futures as cf
import csv
import gzip
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instances as I  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repository root
SCHED = os.path.join(ROOT, "runs", "sched")
PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
SEED = 20261109


def bks(s, ids):
    out, on = {}, False
    for line in open(os.path.join(SCHED, s, f"{s}_BKS.20261101.csv"), encoding="latin-1"):
        c = line.rstrip("\r\n").split(";")
        if c[0] == "ID":
            on = True
        elif on and c[0] in ids:
            out[c[0]] = [int(x) for x in c[4:] if x.strip().isdigit()]
    return out


def run(task):
    from ortools.sat.python import cp_model
    dur, succ, cap, dem = I.instance(task["folder"], task["network"], task["resset"], task["profile"])
    n, U = len(dur), task["ub"]
    m = cp_model.CpModel()
    st = [m.NewIntVar(0, sum(dur), f"s{a}") for a in range(n)]
    iv = [m.NewFixedSizeIntervalVar(st[a], dur[a], f"i{a}") for a in range(n)]
    for a in range(n):
        for b in succ[a]:
            m.Add(st[b] >= st[a] + dur[a])
    for k in range(len(cap)):
        use = [a for a in range(n) if dem[a][k] and dur[a]]
        if use:
            m.AddCumulative([iv[a] for a in use], [dem[a][k] for a in use], cap[k])
    m.Add(st[n - 1] <= U)
    if task["arm"] == "hint":
        for a, v in enumerate(task["hint"]):
            m.AddHint(st[a], v)
    m.Minimize(st[n - 1])
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = task["seconds"]
    sv.parameters.num_workers = 1
    sv.parameters.random_seed = 3
    t0 = time.time()
    status = sv.Solve(m)
    secs = time.time() - t0
    value = sv.Value(st[n - 1]) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    b = sv.BestObjectiveBound()
    bound = min(math.ceil(b - 1e-6), U + 1) if b is not None and math.isfinite(b) else None
    if value is not None and bound is not None:
        bound = min(bound, value)
    return dict(task, status=sv.StatusName(status), value=value, bound=bound, secs=round(secs, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    state = [r for r in csv.DictReader(gzip.open(os.path.join(DATA, "state.csv.gz"), "rt"))
             if int(r["lb_1101"]) < int(r["ub_1101"])]
    hints = {}
    for s in sorted({r["set"] for r in state}):
        hints.update({(s, k): v for k, v in bks(s, {r["id"] for r in state if r["set"] == s}).items()})
    pool = [r for r in state if (r["set"], r["id"]) in hints]      # only instances with a published schedule
    sample = random.Random(SEED).sample(pool, a.n)
    tasks = []
    for k, r in enumerate(sample):
        h = hints.get((r["set"], r["id"]))
        dur, succ, cap, dem = I.instance(r["folder"], r["network"], r["resset"], r["profile"])
        ok = h is not None and I.check(h, dur, succ, cap, dem) is None and max(x + d for x, d in zip(h, dur)) == int(
            r["ub_1101"])
        if not ok:
            print(f"{r['set']} {r['id']}: no valid hint of makespan UB; skipped", flush=True)
            continue
        arms = ["hint", "none"] if k % 2 == 0 else ["none", "hint"]
        for arm in arms:
            tasks.append({"set": r["set"], "id": r["id"], "folder": r["folder"], "network": r["network"],
                          "resset": r["resset"], "profile": r["profile"], "lb": int(r["lb_1101"]),
                          "ub": int(r["ub_1101"]), "hint": h, "arm": arm, "seconds": a.seconds})
    print(f"{len(tasks) // 2} instances x 2 arms, {a.seconds} s, {a.jobs} jobs", flush=True)
    with cf.ProcessPoolExecutor(max_workers=a.jobs) as pool:
        done = list(pool.map(run, tasks))
    with open(os.path.join(DATA, "ablation_hint.tsv"), "w") as f:
        f.write("set\tid\tarm\tlb_1101\tub_1101\tstatus\tvalue\tbound\tsecs\n")
        for d in done:
            f.write(f"{d['set']}\t{d['id']}\t{d['arm']}\t{d['lb']}\t{d['ub']}\t{d['status']}\t{d['value']}\t"
                    f"{d['bound']}\t{d['secs']}\n")
    for arm in ("hint", "none"):
        dd = [d for d in done if d["arm"] == arm]
        print(arm, "closed", sum(d["status"] == "OPTIMAL" for d in dd), "newUB",
              sum(d["value"] is not None and d["value"] < d["ub"] for d in dd), "noschedule",
              sum(d["value"] is None for d in dd), "LB up", sum(d["bound"] is not None and d["bound"] > d["lb"] and
                                                               d["status"] != "OPTIMAL" for d in dd))


if __name__ == "__main__":
    main()
