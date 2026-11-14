"""NetRes lane: OR-Tools CP-SAT over the OPEN instances (published LB < UB) of the seven NetRes sets on Ghent's
Solutions Update site (NR_SP, NR_AD, NR_LA, NR_RC, NR_RU, NR_TF, NR_VAR; 270,000-720,000 instances each, 30
activities). An instance is a network file of NetRes.zip (MT30 sets: durations and precedences; its resource
columns are placeholders) with a resource profile of a ResSet file (capacities and the 30 activities' demands), as
the dataset file's Ref1, Ref2, Ref3 say. Built in memory; checked against the published optimum on NR_SP 1 (28).
Each open instance gets SECS seconds, bounded by the published UB and hinted with the best known schedule when the
BKS record set has one. RESULTS.tsv per set: id, ref1, ref2, ref3, published LB, published UB, ours, status, secs,
record, bound (CLOSED: proven optimum; +UB when it is also below the published UB; UB: a better schedule, not proven;
LB: the run's proven lower bound is above the published LB and the instance is not closed; bound: that proven lower
bound, see engine/sched/rcpsp_cpsat.py lower_bound(): the model's one extra constraint is the cap at the published
UB, so the bound holds for the instance; rows written before 1 Nov 2026 have no bound column).
Schedules go to SOLUTIONS.txt (id;start times); independent/rcpsp_check_netres.py checks them all.
solve() keeps its interface (task, starts, status, seconds) and returns the bound in task["bound"]; a task with
"destructive" set tests caps from the published LB upward instead (rcpsp_cpsat.destructive(), runs/sched/netres_lb.py),
and "params" adds CP-SAT parameters.
  .venv/bin/python -I runs/sched/netres.py [WORKERS] [SECS] [SET ...]"""
import concurrent.futures as cf
import os
import re
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine", "sched"))  # rcpsp_cpsat: the shared bound rule
SITE = "http://solutionsupdate.ugent.be/sites/default/files/datasets/"
INST = os.path.join(HERE, "NR_SP", "inst")  # NetRes.zip, unzipped (networks and resource sets for every set)
SETS = ["NR_SP", "NR_AD", "NR_TF", "NR_RC", "NR_VAR", "NR_RU", "NR_LA"]
_cache = {}


def fetch(url, path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)


def network(ref1):
    """(n, r, durations, successors) of a network file, from its Ref1 (e.g. 'Set 1 SP\\EV1.rcp')."""
    if ref1 not in _cache:
        folder, name = ref1.replace("\\", "/").split("/")[-2:]
        d = os.path.join(INST, "MT30", folder)
        if not os.path.isdir(d) and os.path.exists(d + ".zip"):
            zipfile.ZipFile(d + ".zip").extractall(os.path.join(INST, "MT30"))
        nums = [int(x) for x in open(os.path.join(d, name)).read().split()]
        n, r = nums[0], nums[1]
        pos, dur, succ = 2 + r, [], []
        for _ in range(n):
            dur.append(nums[pos])
            k = nums[pos + 1 + r]
            succ.append([s - 1 for s in nums[pos + 2 + r:pos + 2 + r + k]])
            pos += 2 + r + k
        _cache[ref1] = (n, r, dur, succ)
    return _cache[ref1]


def resset(ref2):
    """{profile: (capacities, demands of the 30 real activities)} of a ResSet file."""
    if ref2 not in _cache:
        blocks, cur, mode = {}, None, None
        for line in open(os.path.join(INST, "ResSet", ref2), encoding="latin-1"):
            s = line.strip()
            m = re.match(r"File number (\d+)", s)
            if m:
                cur = {"cap": None, "dem": []}
                blocks[int(m.group(1))] = cur
                mode = None
                continue
            if cur is None:
                continue
            if s.startswith("Resource availability"):
                mode = "cap"
                continue
            if s.startswith("Resource demand"):
                mode = "dem"
                continue
            nums = s.split()
            if nums and all(x.isdigit() for x in nums):
                if mode == "cap" and cur["cap"] is None:
                    cur["cap"] = list(map(int, nums))
                elif mode == "dem":
                    cur["dem"].append(list(map(int, nums)))
        _cache[ref2] = {k: (b["cap"], b["dem"]) for k, b in blocks.items()}
    return _cache[ref2]


def run_once(task, limit, secs, hint=True):
    """One CP-SAT run on the instance with the one extra constraint makespan <= limit: dict(status, starts, bound)."""
    from ortools.sat.python import cp_model
    from rcpsp_cpsat import bound_ok, lower_bound
    n, r, dur, succ = network(task["ref1"])
    cap, dem30 = resset(task["ref2"])[task["ref3"]]
    dem = [[0] * len(cap)] + dem30 + [[0] * len(cap)]
    assert len(dem) == n, (task, len(dem), n)
    m = cp_model.CpModel()
    horizon = sum(dur)
    st = [m.NewIntVar(0, horizon, f"s{i}") for i in range(n)]
    iv = [m.NewFixedSizeIntervalVar(st[i], dur[i], f"i{i}") for i in range(n)]
    for i in range(n):
        for j in succ[i]:
            m.Add(st[j] >= st[i] + dur[i])
    for k in range(len(cap)):
        items = [(iv[i], dem[i][k]) for i in range(n) if dem[i][k] > 0 and dur[i] > 0]
        if items:
            m.AddCumulative([a for a, _ in items], [d for _, d in items], cap[k])
    m.Add(st[n - 1] <= limit)
    if hint and task["hint"] and len(task["hint"]) == n:
        for i, s in enumerate(task["hint"]):
            m.AddHint(st[i], s)
    m.Minimize(st[n - 1])
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = secs
    sv.parameters.num_workers = 1
    if task.get("params"):
        sv.parameters.merge_text_format(task["params"])
    status = sv.Solve(m)
    starts = [sv.Value(s) for s in st] if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    return dict(status=sv.StatusName(status), starts=starts, value=starts[-1] if starts else None,
                bound=lower_bound(sv, status, limit) if bound_ok(task.get("params")) else None)


def solve(task):
    """Worker: (task, start times or None, status, seconds), as before; the run's proven lower bound comes back in
    task["bound"]. task["destructive"]: caps from the published LB upward (no hint), else one run capped at the
    published UB and hinted with the best known schedule."""
    from rcpsp_cpsat import destructive
    t0 = time.time()
    if task.get("destructive"):
        res = destructive(lambda lim, left: run_once(task, lim, left, hint=False), task["lb"], task["ub"], task["secs"])
    else:
        res = run_once(task, task["ub"], task["secs"])
    task["bound"] = res["bound"]
    return task, res["starts"], res["status"], time.time() - t0


def outcome(t, starts, status):
    """(ours, record, note) of one run: CLOSED (proven optimum; +UB when below the published UB), UB (a better
    schedule, not proven), LB (proven bound above the published LB, not closed; never above the published UB: that
    would be a conflict, noted, not a record)."""
    ours, record, note = "-", "-", ""
    if status == "BOUND_CONFLICT":
        note = "CONFLICT: a destructive refutation above our own schedule; bound dropped"
    if starts:
        ours = starts[-1]
        if status == "OPTIMAL":
            record = "CLOSED+UB" if ours < t["ub"] else "CLOSED"
        elif ours < t["ub"]:
            record = "UB"
    b = t.get("bound")
    if b is not None and status != "OPTIMAL" and b > t["lb"]:
        if b > t["ub"]:
            note = f"CONFLICT: bound {b} above the published UB {t['ub']}"
        else:
            record = "LB" if record == "-" else record + "+LB"
    return ours, record, note


def row(t, ours, status, sec, record):
    b = t.get("bound")
    return (f"{t['id']}\t{t['ref1']}\t{t['ref2']}\t{t['ref3']}\t{t['lb']}\t{t['ub']}\t{ours}\t{status}\t{sec:.2f}"
            f"\t{record}\t{'-' if b is None else b}\n")


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    names = sys.argv[3:] or SETS
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        for ds in names:
            d = os.path.join(HERE, ds)
            os.makedirs(d, exist_ok=True)
            try:
                fetch(SITE + ds + ".csv", os.path.join(d, ds + ".csv"))
                fetch(SITE + ds + "_BKS.csv", os.path.join(d, ds + "_BKS.csv"))
            except Exception as exc:
                print(ds, "download failed:", exc, flush=True)
                continue
            bks = {}
            on = False
            for line in open(os.path.join(d, ds + "_BKS.csv"), encoding="latin-1"):
                c = line.rstrip("\r\n").split(";")
                if c[0] == "ID":
                    on = True
                elif on and c[0].isdigit():
                    bks[int(c[0])] = [int(x) for x in c[4:] if x.strip().isdigit()]
            res = os.path.join(d, "RESULTS.tsv")
            done = set()
            if os.path.exists(res):
                done = {int(l.split("\t")[0]) for l in open(res).read().splitlines()[1:]}
            else:
                open(res, "w").write("id\tref1\tref2\tref3\tpub_lb\tpub_ub\tours\tstatus\tsecs\trecord\tbound\n")
            tasks, on = [], False
            for line in open(os.path.join(d, ds + ".csv"), encoding="latin-1"):
                c = line.rstrip("\r\n").split(";")
                if c[0] == "ID":
                    on = True
                    continue
                if not on or not c[0].isdigit():
                    continue
                i, lb, ub = int(c[0]), int(c[4]), int(c[7])
                if lb < ub and i not in done:
                    tasks.append({"id": i, "ref1": c[1], "ref2": c[2], "ref3": int(c[3]), "lb": lb, "ub": ub,
                                  "hint": bks.get(i), "secs": secs})
            print(f"{ds}: {len(tasks)} open instances to try ({len(done)} done)", flush=True)
            sol = open(os.path.join(d, "SOLUTIONS.txt"), "a")
            out = open(res, "a")
            for k in range(0, len(tasks), 5000):  # in chunks, so a stop loses little
                for fu in cf.as_completed([pool.submit(solve, t) for t in tasks[k:k + 5000]]):
                    try:
                        t, starts, status, sec = fu.result()
                    except Exception as exc:
                        print(ds, "task failed:", repr(exc)[:200], flush=True)
                        continue
                    if starts:
                        sol.write(f"{t['id']};" + ";".join(map(str, starts)) + "\n")
                    ours, record, note = outcome(t, starts, status)
                    if note:
                        print(ds, t["id"], note, flush=True)
                    out.write(row(t, ours, status, sec, record))
                sol.flush()
                out.flush()
            sol.close()
            out.close()
    print("netres lane done", time.strftime("%F %T"), flush=True)


if __name__ == "__main__":
    main()
