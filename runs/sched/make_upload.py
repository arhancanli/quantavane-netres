"""Results files for Ghent's Solutions Update site from the lanes' RESULTS.tsv, in the site's format (node/68): six
lead lines, then ID;Type;Value;Time;Solution. Type "optimal" (proven by CP-SAT, with our schedule), "heuristic" (a
schedule below the published UB, not proven) or "lower bound" (CP-SAT's proven bound above the published LB, no
schedule: ID;lower bound;value;time, the BNF's empty Solution); Time in milliseconds; Solution = every activity's start
time. Only new results go in, each re-derived from its row (value, status, bound) against the dataset file on disk,
so a row recorded against an older dataset file counts only if it still beats the current one: a schedule below the
published UB or a proven optimum above the published LB, with a passed independent check; a bound above the
published LB of an instance open there, never above its UB. Per instance at most one schedule line (the best) and
one lower-bound line (the highest; none when the instance has an optimal line). Lower-bound lines are counted
separately from schedules. Rows whose best known value is the dataset's sum of durations (a placeholder) stay out,
as before. Writes runs/sched/upload/<dataset>_Quantavane.csv (or $QV_UPLOAD_OUT/...); nothing is sent.
Single-mode sets (runs/sched/lane.py): RESULTS.tsv id, file, pub_lb, bks, ours, status, secs, check, record[, bound],
schedules in sol/<id>_<value>.sol (older rows: sol/<id>.sol), each re-checked here by independent/rcpsp_check.py; the
ID written is the dataset's file name, or its number when the name holds a folder (DC2: npv25\\rcpspdc1.rcp).
NetRes sets (runs/sched/netres.py, netres_pass2.py, netres_lb.py): RESULTS.tsv id, ref1, ref2, ref3, pub_lb, pub_ub,
ours, status, secs, record[, bound], in the set's folder and in its lb/ folder; schedules in SOLUTIONS.txt (id;starts)
of the same folder, which VALID.txt (independent/rcpsp_check_netres.py) must list, ending at the row's value.
Multi-mode sets (runs/sched/mmlane.py, results in runs/sched/mm/<SET>/) use the site's multi-mode Solution field:
the mode of each real activity, then every start time (node/68: <Mod1>;...;<Modn>;<ST0>;...;<STn+1>); each of their
schedules is re-checked here by independent/mrcpsp_check.py before it goes in. A strict run's proof without a schedule
of ours (record LB, no bound column) is a lower bound at the best known value.
The lead lines are public words: the owner approves them before any upload.
  .venv/bin/python -I runs/sched/make_upload.py"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("QV_UPLOAD_OUT") or os.path.join(HERE, "upload")  # 7 Nov: a new folder per batch keeps upload/ as sent on 4 Nov
MM = os.path.join(HERE, "mm")
MM_SETS = ["MMplus", "MM50", "MM100", "Boct100"]
CHECK = os.path.join(HERE, "..", "..", "independent", "rcpsp_check.py")
MM_CHECK = os.path.join(HERE, "..", "..", "independent", "mrcpsp_check.py")
# 1 Nov: the summary table counts one gap-1 instance in each of these sets as closed while their files show it open
MM_ONE_CLOSED_UNNAMED = {"MM50", "MM100"}
LEAD = ["# Author(s);Arhan Canli (Quantavane)",
        "# Reference;Working paper: OR-Tools CP-SAT 9.15, hinted with and bounded by the best known schedule",
        "# Date;" + time.strftime("%Y/%m/%d"),
        "# Hardware / software;Apple M5 Pro, one core per instance; OR-Tools CP-SAT 9.15 (Python)",
        "# Stop criteria;5 to 60 seconds per instance by size (or a proof of optimality)",
        "# Submission date;" + time.strftime("%Y/%m/%d"),
        "ID;Type;Value;Time;Solution"]


def num(x):
    x = x.strip()
    return int(x) if x.lstrip("-").isdigit() else None


def dataset(path):
    """id -> (Ref1, LB, UB, Sum PT) of a dataset file (UB None when 0 or missing)."""
    out, on = {}, False
    for line in open(path, encoding="utf-8", errors="replace"):
        c = line.rstrip("\r\n").split(";")
        if c[0].lstrip("\ufeff") == "ID":
            on = True
        elif on and c[0].isdigit() and len(c) > 14:
            out[c[0]] = (c[1].strip(), num(c[4]), num(c[7]) or None, num(c[14]))
    return out


def lines_for(ds, sched, lbs, solution, lead=None):
    """Write one set's file from sched {id: (value, status, secs, rid)} and lbs {id: (bound, secs, rid)};
    solution(id, value) returns the checked Solution field or None. Returns (schedule lines, lower-bound lines)."""
    out, n_s, n_lb = [], 0, 0
    for i in sorted(set(sched) | set(lbs), key=int):
        opt = False
        if i in sched:
            v, status, secs, rid = sched[i]
            sol = solution(i, v)
            if sol is not None:
                opt = status == "OPTIMAL"
                out.append(f"{rid};{'optimal' if opt else 'heuristic'};{v};{round(float(secs) * 1000)};{sol}")
                n_s += 1
        if i in lbs and not opt:
            b, secs, rid = lbs[i]
            if i in sched and b > sched[i][0]:
                print(f"{ds} {rid}: bound {b} above our schedule {sched[i][0]}; left out")
                continue
            out.append(f"{rid};lower bound;{b};{round(float(secs) * 1000)}")
            n_lb += 1
    if out:
        lead = list(lead or LEAD)
        if n_lb:
            lead[1] += "; lower bounds: CP-SAT proves no schedule ends within a cap (caps from the published LB up)"
        open(os.path.join(OUT, f"{ds}_Quantavane.csv"), "w").write("\n".join(lead + out) + "\n")
        print(f"{ds}: {n_s} schedules (optimal or heuristic), {n_lb} lower bounds")
    return n_s, n_lb


def single_mode(ds):
    d = os.path.join(HERE, ds)
    data = dataset(os.path.join(d, ds + ".csv"))
    sched, lbs = {}, {}
    for row in open(os.path.join(d, "RESULTS.tsv")).read().splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 9 or c[8] == "-" or c[0] not in data:
            continue
        i, fname, lb, bks, ours, status, secs, check, record = c[:9]
        bound = num(c[9]) if len(c) > 9 else None
        ref, cur_lb, cur_ub, sumpt = data[i]
        # 1 Nov: some variant sets (J60highRD, J120lowRU, CVhighRD) have no real best known schedules yet: their BKS
        # file repeats the dataset's sum of durations (a placeholder). Beating that is a first schedule, not a record,
        # so such rows are left out here.
        if num(bks) is not None and num(bks) == sumpt:
            continue
        rid = i if ("\\" in ref or "/" in ref) else ref
        tags, v = set(record.split("+")), num(ours)
        if tags & {"UB", "CLOSED"} and v is not None and check == f"makespan {v} valid":
            if (cur_ub is not None and v < cur_ub) or (status == "OPTIMAL" and cur_lb < v):
                key = (v, 0 if status == "OPTIMAL" else 1)
                if i not in sched or key < (sched[i][0], 0 if sched[i][1] == "OPTIMAL" else 1):
                    sched[i] = (v, status, secs, rid)
        if "LB" in tags and bound is not None and cur_ub is not None and cur_lb < bound <= cur_ub:
            if i not in lbs or bound > lbs[i][0]:
                lbs[i] = (bound, secs, rid)

    files = [os.path.join(r, f) for r, _, fs in os.walk(os.path.join(d, "inst")) for f in fs] if sched else []

    def solution(i, v):
        path = os.path.join(d, "sol", f"{i}_{v}.sol")
        if not os.path.exists(path):
            path = os.path.join(d, "sol", f"{i}.sol")
        ref = "/" + data[i][0].replace("\\", "/")
        inst = [f for f in files if f.replace(os.sep, "/").endswith(ref)]
        if len(inst) != 1 or not os.path.exists(path):
            print(f"{ds} {i}: instance or schedule file not found; left out")
            return None
        run = subprocess.run([sys.executable, "-I", CHECK, inst[0], path], capture_output=True, text=True)
        if run.stdout.strip() != f"makespan {v} valid":
            print(f"{ds} {i}: schedule {v} fails the re-check ({run.stdout.strip()}); left out")
            return None
        return open(path).read().strip()

    return lines_for(ds, sched, lbs, solution)


def netres(ds):
    d = os.path.join(HERE, ds)
    sched, lbs, sols = {}, {}, {}
    for sub in ("", "lb", "lb3b", "lb3c", "lb4", "lb5", "lb6", "lb7", "lb8", "lbm"):  # 7 Nov: later passes write their own folders (single writer each); 8 Nov: lb6; 9 Nov: lb7, lb8
        res = os.path.join(d, sub, "RESULTS.tsv")
        if not os.path.exists(res):
            continue
        valid_path, sol_path = os.path.join(d, sub, "VALID.txt"), os.path.join(d, sub, "SOLUTIONS.txt")
        ok = set()
        if os.path.exists(valid_path):
            ok = {tuple(l.split(";")[:2]) for l in open(valid_path).read().splitlines()}
        sol = {}
        if os.path.exists(sol_path):
            for l in open(sol_path):
                i, _, rest = l.strip().partition(";")
                sol[(i, rest.split(";")[-1])] = rest      # per id and makespan
        for row in open(res).read().splitlines()[1:]:
            c = row.split("\t")
            if len(c) < 10 or c[9] == "-":   # a partial last line of a file being appended is skipped too
                continue
            i, _, _, _, lb, ub, ours, status, secs, record = c[:10]
            bound, tags = (num(c[10]) if len(c) > 10 else None), set(record.split("+"))
            if num(lb) is None or num(ub) is None:
                continue
            if tags & {"UB", "CLOSED"} and (i, ours) in ok and (i, ours) in sol:
                key = (int(ours), 0 if status == "OPTIMAL" else 1)
                if i not in sched or key < (sched[i][0], 0 if sched[i][1] == "OPTIMAL" else 1):
                    sched[i] = (int(ours), status, secs, i)
                    sols[i] = sol[(i, ours)]
            if "LB" in tags and bound is not None and num(lb) < bound <= num(ub):
                if i not in lbs or bound > lbs[i][0]:
                    lbs[i] = (bound, secs, i)
    return lines_for(ds, sched, lbs, lambda i, v: sols.get(i))


def mm_set(ds):
    """Multi-mode sets: the best checked schedule per instance (lowest value, a proof first at equal value) and the
    highest bound."""
    d = os.path.join(MM, ds)
    data = dataset(os.path.join(d, ds + ".csv"))
    sched, lbs, secs_used = {}, {}, []
    for row in open(os.path.join(d, "RESULTS.tsv")).read().splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 9 or c[8] == "-" or c[0] not in data:
            continue
        i, fname, lb, bks, ours, status, secs, check, record = c[:9]
        bound = num(c[9]) if len(c) > 9 else None
        ref, cur_lb, cur_ub, sumpt = data[i]
        if num(bks) is not None and num(bks) == sumpt:   # placeholder guard as above (none in these sets on 1 Nov)
            continue
        tags, v = set(record.split("+")), num(ours)
        if tags & {"UB", "CLOSED"} and v is not None and check.startswith("makespan %s valid" % ours) \
                and "not below" not in check:
            if (cur_ub is not None and v < cur_ub) or (status == "OPTIMAL" and cur_lb < v):
                key = (v, 0 if status == "OPTIMAL" else 1)
                if i not in sched or key < (sched[i][0], 0 if sched[i][1] == "OPTIMAL" else 1):
                    sched[i] = (v, status, secs, fname)
        if "LB" in tags:
            b = bound if bound is not None else num(bks)   # a strict run's INFEASIBLE: the best known value
            if b is not None and cur_ub is not None and cur_lb < b <= cur_ub and (i not in lbs or b > lbs[i][0]):
                lbs[i] = (b, secs, fname)
    for i in set(sched) | set(lbs):
        secs_used.append(float(sched[i][2] if i in sched else lbs[i][1]))
        if ds in MM_ONE_CLOSED_UNNAMED and data[i][2] is not None and data[i][2] - data[i][1] == 1:
            print(f"{ds} {data[i][0]}: gap-1 instance; the venue already counts one such instance in {ds} as closed: "
                  "re-read its result files before claiming this one")

    def solution(i, v):
        fname, bks = sched[i][3], data[i][2]
        path = os.path.join(d, "sol", f"{i}_{v}.sol")
        run = subprocess.run([sys.executable, "-I", MM_CHECK, os.path.join(d, "inst", fname), path]
                             + (["--best", str(bks)] if bks is not None and v < bks else []),
                             capture_output=True, text=True)
        if run.returncode != 0 or not run.stdout.startswith(f"makespan {v} valid"):
            print(f"{ds} {fname}: schedule {v} fails the re-check ({run.stdout.strip()}); left out")
            return None
        return open(path).read().strip()

    if not secs_used:
        return 0, 0
    lead = list(LEAD)
    lead[1] = ("# Reference;Working paper: OR-Tools CP-SAT 9.15, multi-mode model hinted with the best known "
               "schedule where one is published")
    lo, hi = round(min(secs_used)), round(max(secs_used))
    lead[4] = ("# Stop criteria;a time limit of %s seconds per instance (or a proof of optimality)"
               % (lo if lo == hi else "%d to %d" % (lo, hi)))
    return lines_for(ds, sched, lbs, solution, lead)


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):  # written afresh each time, so a set that no longer has records leaves no file
        if f.endswith("_Quantavane.csv"):
            os.remove(os.path.join(OUT, f))
    n_s = n_lb = 0
    for ds in sorted(os.listdir(HERE)):
        if not os.path.exists(os.path.join(HERE, ds, "RESULTS.tsv")):
            continue
        if ds.startswith("NR_"):
            a, b = netres(ds)
        elif os.path.exists(os.path.join(HERE, ds, ds + ".csv")):
            a, b = single_mode(ds)
        else:
            continue
        n_s, n_lb = n_s + a, n_lb + b
    for ds in MM_SETS:
        if os.path.exists(os.path.join(MM, ds, "RESULTS.tsv")):
            a, b = mm_set(ds)
            n_s, n_lb = n_s + a, n_lb + b
    print(f"{n_s} schedules and {n_lb} lower bounds in {OUT}")


if __name__ == "__main__":
    main()
