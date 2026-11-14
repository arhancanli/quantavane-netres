"""Re-prove a seeded random sample of our lower bounds, two ways, from the instances as the paper's own reader builds
them (scripts/instances.py), with model code written for the paper (not the search code):

  HiGHS  a different solver and a different model: the time-indexed 0-1 program (Pritsker, Watters and Wolfe 1969) with
         disaggregated precedence rows, feasibility only;
  CP-SAT the same solver family as the search, but an independently written interval model (start variables, fixed
         size intervals, one cumulative constraint per resource), feasibility only, 1 worker, seed 11, CP-SAT's
         cumulative propagators on (overload checker, timetable edge finding, hard precedences).

A claim "the optimum is at least L" (a listed lower bound line, or an optimal line of value L) is confirmed when the
model with makespan <= L - 1 is proved infeasible; a feasible answer would contradict it (the schedule found is
checked by scripts/instances.check and printed); a time limit gives no verdict. If an activity's earliest start (forward
pass) exceeds its latest start for the cap (backward pass), the critical path alone refutes the cap.
Sample: for each set, SEED-seeded random choice of PER claims of each kind (optimal, lower bound) among our distinct
listed claims (data/listed_lines.csv.gz; per instance only the highest bound). Writes data/reprove.tsv.
  nice -n 10 python3 -I scripts/reprove_sample.py [--per 5] [--highs 30] [--cpsat 120]
                                                                               [--jobs 3]"""
import argparse
import collections
import concurrent.futures as cf
import csv
import gzip
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instances as I  # noqa: E402

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
SETS = ["NR_SP", "NR_AD", "NR_LA", "NR_TF", "NR_RC", "NR_RU", "NR_VAR"]
SEED = 20261109
CUMULATIVE = ("use_overload_checker_in_cumulative: true use_timetable_edge_finding_in_cumulative: true "
              "use_hard_precedences_in_cumulative: true")


def windows(dur, succ, T):
    n = len(dur)
    pred = [[] for _ in range(n)]
    for a in range(n):
        for b in succ[a]:
            pred[b].append(a)
    order, indeg, q = [], [len(p) for p in pred], [a for a in range(n) if not pred[a]]
    while q:
        a = q.pop()
        order.append(a)
        for b in succ[a]:
            indeg[b] -= 1
            if indeg[b] == 0:
                q.append(b)
    if len(order) != n:
        raise ValueError("cycle in the network")
    es = [0] * n
    for a in order:
        for b in succ[a]:
            es[b] = max(es[b], es[a] + dur[a])
    ls = [T - dur[a] for a in range(n)]
    for a in reversed(order):
        for b in succ[a]:
            ls[a] = min(ls[a], ls[b] - dur[a])
    return es, ls


def verdict_of_schedule(starts, dur, succ, cap, dem):
    bad = I.check(starts, dur, succ, cap, dem)
    return "FEASIBLE: claim contradicted" if bad is None else f"feasible answer fails the check: {bad}"


def by_highs(inst, T, seconds):
    import highspy
    import numpy as np
    dur, succ, cap, dem = inst
    n = len(dur)
    es, ls = windows(dur, succ, T)
    if any(es[a] > ls[a] for a in range(n)):
        return "infeasible (critical path)", 0, 0
    real = range(1, n - 1)
    col = {}
    for a in real:
        for t in range(es[a], ls[a] + 1):
            col[(a, t)] = len(col)
    rows, lo, hi = [], [], []
    inf = highspy.kHighsInf
    for a in real:
        rows.append(([col[(a, t)] for t in range(es[a], ls[a] + 1)], [1.0] * (ls[a] - es[a] + 1)))
        lo.append(1.0)
        hi.append(1.0)
    for a in real:
        for b in succ[a]:
            if b == n - 1:
                continue                          # the dummy end: covered by the latest starts
            for t in range(es[b], ls[b] + 1):
                pre = [col[(a, s)] for s in range(es[a], min(ls[a], t - dur[a]) + 1)]
                if len(pre) == ls[a] - es[a] + 1:
                    continue                      # always satisfied
                idx = [col[(b, s)] for s in range(es[b], t + 1)]
                rows.append((idx + pre, [1.0] * len(idx) + [-1.0] * len(pre)))
                lo.append(-inf)
                hi.append(0.0)
    for k in range(len(cap)):
        for t in range(T):
            idx, val = [], []
            for a in real:
                if dem[a][k] and dur[a]:
                    for s in range(max(es[a], t - dur[a] + 1), min(ls[a], t) + 1):
                        idx.append(col[(a, s)])
                        val.append(float(dem[a][k]))
            if idx and sum(val) > cap[k]:
                rows.append((idx, val))
                lo.append(-inf)
                hi.append(float(cap[k]))
    start, index, value = [0], [], []
    for idx, val in rows:
        index += idx
        value += val
        start.append(len(index))
    nc = len(col)
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = nc, len(rows)
    lp.col_cost_ = np.zeros(nc)
    lp.col_lower_, lp.col_upper_ = np.zeros(nc), np.ones(nc)
    lp.row_lower_, lp.row_upper_ = np.array(lo), np.array(hi)
    mat = highspy.HighsSparseMatrix()
    mat.format_ = highspy.MatrixFormat.kRowwise
    mat.num_col_, mat.num_row_ = nc, len(rows)
    mat.start_, mat.index_, mat.value_ = np.array(start), np.array(index), np.array(value)
    lp.a_matrix_ = mat
    lp.integrality_ = [highspy.HighsVarType.kInteger] * nc
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("threads", 1)
    h.setOptionValue("time_limit", float(seconds))
    h.setOptionValue("random_seed", 0)
    h.passModel(lp)
    h.run()
    st = h.getModelStatus()
    if st == highspy.HighsModelStatus.kInfeasible:
        return "infeasible", nc, len(rows)
    if st == highspy.HighsModelStatus.kOptimal:
        x = h.getSolution().col_value
        starts = [0] * n
        for (a, t), j in col.items():
            if x[j] > 0.5:
                starts[a] = t
        starts[n - 1] = max(starts[a] + dur[a] for a in range(n - 1))
        return verdict_of_schedule(starts, *inst), nc, len(rows)
    return "no verdict (" + h.modelStatusToString(st) + ")", nc, len(rows)


def by_cpsat(inst, T, seconds):
    from ortools.sat.python import cp_model
    dur, succ, cap, dem = inst
    n = len(dur)
    m = cp_model.CpModel()
    st = [m.NewIntVar(0, max(0, T - dur[a]), f"s{a}") for a in range(n)]
    iv = [m.NewFixedSizeIntervalVar(st[a], dur[a], f"i{a}") for a in range(n)]
    for a in range(n):
        for b in succ[a]:
            m.Add(st[b] >= st[a] + dur[a])
    for k in range(len(cap)):
        use = [a for a in range(n) if dem[a][k] and dur[a]]
        if use:
            m.AddCumulative([iv[a] for a in use], [dem[a][k] for a in use], cap[k])
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = float(seconds)
    sv.parameters.num_workers = 1
    sv.parameters.random_seed = 11
    sv.parameters.merge_text_format(CUMULATIVE)
    status = sv.Solve(m)
    if status == cp_model.INFEASIBLE:
        return "infeasible"
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return verdict_of_schedule([sv.Value(v) for v in st], *inst)
    return "no verdict (" + sv.StatusName(status) + ")"


def refute(task):
    inst = I.instance(task["folder"], task["network"], task["resset"], task["profile"])
    T = task["claim"] - 1
    task["T"] = T
    t0 = time.time()
    task["cpsat"] = by_cpsat(inst, T, task["cpsat_s"])
    task["cpsat_secs"] = round(time.time() - t0, 2)
    t0 = time.time()
    task["highs"], task["cols"], task["rows"] = by_highs(inst, T, task["highs_s"])
    task["highs_secs"] = round(time.time() - t0, 2)
    return task


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=5)
    ap.add_argument("--highs", type=float, default=30.0)
    ap.add_argument("--cpsat", type=float, default=120.0)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    state = {(r["set"], r["id"]): r for r in csv.DictReader(gzip.open(os.path.join(DATA, "state.csv.gz"), "rt"))}
    best = {}
    for r in csv.DictReader(gzip.open(os.path.join(DATA, "listed_lines.csv.gz"), "rt")):
        if r["type"] in ("optimal", "lower bound"):
            k = (r["set"], r["id"])
            v = int(r["value"])
            if k not in best or v > best[k][1] or (v == best[k][1] and r["type"] == "optimal"):
                best[k] = (r["type"], v)
    rng = random.Random(SEED)
    tasks = []
    for s in SETS:
        for kind in ("optimal", "lower bound"):
            pool = sorted((int(i), v) for (ss, i), (t, v) in best.items() if ss == s and t == kind)
            for i, v in rng.sample(pool, min(a.per, len(pool))):
                st = state[(s, str(i))]
                tasks.append({"set": s, "id": i, "kind": kind, "claim": v, "folder": st["folder"],
                              "network": st["network"], "resset": st["resset"], "profile": st["profile"],
                              "lb_1101": st["lb_1101"], "ub_1109": st["ub_1109"], "highs_s": a.highs,
                              "cpsat_s": a.cpsat})
    print(f"{len(tasks)} claims; CP-SAT {a.cpsat:.0f} s, HiGHS {a.highs:.0f} s each; {a.jobs} jobs", flush=True)
    done = []
    with cf.ProcessPoolExecutor(max_workers=a.jobs) as pool:
        for fu in cf.as_completed([pool.submit(refute, t) for t in tasks]):
            t = fu.result()
            done.append(t)
            print(f"{t['set']} {t['id']} {t['kind']} >= {t['claim']}: CP-SAT {t['cpsat']} ({t['cpsat_secs']} s); "
                  f"HiGHS {t['highs']} ({t['highs_secs']} s, {t['cols']} x {t['rows']})", flush=True)
    done.sort(key=lambda t: (SETS.index(t["set"]), t["kind"], t["id"]))
    keys = ["set", "id", "kind", "claim", "lb_1101", "ub_1109", "T", "cpsat", "cpsat_secs", "highs", "highs_secs",
            "cols", "rows", "cpsat_s", "highs_s"]
    with open(os.path.join(DATA, "reprove.tsv"), "w") as f:
        f.write("\t".join(keys) + "\n")
        for t in done:
            f.write("\t".join(str(t.get(k, "")) for k in keys) + "\n")
    print("CP-SAT", collections.Counter(t["cpsat"].split(" (")[0] for t in done))
    print("HiGHS", collections.Counter(t["highs"].split(" (")[0] for t in done))


if __name__ == "__main__":
    main()
