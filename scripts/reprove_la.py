"""Re-prove the six lower bounds that closed NR(LA) (the six NR_LA lower-bound lines of 9 Nov), with the paper's
independently written CP-SAT interval model (scripts/reprove_sample.by_cpsat: feasibility at makespan <= L - 1),
SECONDS each and WORKERS CP-SAT workers per claim, all six in parallel. Writes data/reprove_la.tsv.
  nice -n 10 python3 -I scripts/reprove_la.py [--seconds 1200] [--workers 1]
Follow-up for claims left without verdict: --ids 270264,353064 --workers 4 --seconds 1800 --exploit
--out data/reprove_la2.tsv (--exploit adds CP-SAT's exploit_all_precedences, as the search's lower-bound runs had;
the model stays the paper's own)."""
import argparse
import concurrent.futures as cf
import csv
import gzip
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instances as I  # noqa: E402
import reprove_sample as R  # noqa: E402

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")


def run(task):
    from ortools.sat.python import cp_model
    dur, succ, cap, dem = I.instance(task["folder"], task["network"], task["resset"], task["profile"])
    T = task["claim"] - 1
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
    sv.parameters.max_time_in_seconds = float(task["seconds"])
    sv.parameters.num_workers = int(task["workers"])
    sv.parameters.random_seed = 11
    sv.parameters.merge_text_format(R.CUMULATIVE)
    if task.get("exploit"):
        sv.parameters.merge_text_format("exploit_all_precedences: true")
    t0 = time.time()
    status = sv.Solve(m)
    task["secs"] = round(time.time() - t0, 1)
    if status == cp_model.INFEASIBLE:
        task["verdict"] = "infeasible"
    elif status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        task["verdict"] = R.verdict_of_schedule([sv.Value(v) for v in st], dur, succ, cap, dem)
    else:
        task["verdict"] = "no verdict (" + sv.StatusName(status) + ")"
    return task


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=1200.0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--ids", default="")
    ap.add_argument("--exploit", action="store_true")
    ap.add_argument("--out", default=os.path.join(DATA, "reprove_la.tsv"))
    a = ap.parse_args()
    only = {x for x in a.ids.split(",") if x}
    state = {(r["set"], r["id"]): r for r in csv.DictReader(gzip.open(os.path.join(DATA, "state.csv.gz"), "rt"))}
    tasks = []
    for r in csv.DictReader(gzip.open(os.path.join(DATA, "listed_lines.csv.gz"), "rt")):
        if r["set"] == "NR_LA" and r["type"] == "lower bound" and (not only or r["id"] in only):
            st = state[("NR_LA", r["id"])]
            tasks.append({"id": int(r["id"]), "claim": int(r["value"]), "folder": st["folder"], "network": st["network"],
                          "resset": st["resset"], "profile": st["profile"], "ub_1109": st["ub_1109"],
                          "seconds": a.seconds, "workers": a.workers, "exploit": a.exploit})
    print(f"{len(tasks)} NR(LA) lower bounds, {a.seconds:.0f} s, {a.workers} worker(s) each", flush=True)
    done = []
    with cf.ProcessPoolExecutor(max_workers=len(tasks)) as pool:
        for fu in cf.as_completed([pool.submit(run, t) for t in tasks]):
            t = fu.result()
            done.append(t)
            print(f"NR_LA {t['id']} >= {t['claim']} (UB {t['ub_1109']}): {t['verdict']} ({t['secs']} s)", flush=True)
    done.sort(key=lambda t: t["id"])
    with open(a.out, "w") as f:
        f.write("id\tclaim\tub_1109\tverdict\tsecs\tseconds\tworkers\texploit\n")
        for t in done:
            f.write(f"{t['id']}\t{t['claim']}\t{t['ub_1109']}\t{t['verdict']}\t{t['secs']}\t{t['seconds']}\t"
                    f"{t['workers']}\t{t['exploit']}\n")


if __name__ == "__main__":
    main()
