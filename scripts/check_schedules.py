"""Re-check every schedule the Solutions Update lists under our name (data/listed_lines.csv.gz: the distinct optimal and
heuristic lines of the site's copies of our NetRes files, 9 Nov 2026) on instances rebuilt from Ghent's original files
(scripts/instances.py), and compare each with the dataset files of 9 Nov (data/state.csv.gz).

Per line: feasible (every precedence, every resource at every time unit), makespan (latest finish) equal to the
stated value, the dummy end's start equal to it too; for an optimal line, the published LB and UB of 9 Nov both equal
the value; for a heuristic line, the published UB is at most the value. Writes data/schedule_check.tsv (per set and
type) and lists every failure in logs/check_schedules.log.
  nice -n 10 python3 -I scripts/check_schedules.py"""
import collections
import csv
import gzip
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instances as I  # noqa: E402

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")


def main():
    state = {}
    for r in csv.DictReader(gzip.open(os.path.join(DATA, "state.csv.gz"), "rt")):
        state[(r["set"], r["id"])] = r
    out = collections.defaultdict(collections.Counter)
    fails = []
    for r in csv.DictReader(gzip.open(os.path.join(DATA, "listed_lines.csv.gz"), "rt")):
        if r["type"] not in ("optimal", "heuristic"):
            continue
        key = (r["set"], r["id"])
        c = out[(r["set"], r["type"])]
        c["lines"] += 1
        st = state.get(key)
        if st is None:
            c["instance not in state"] += 1
            fails.append(f"{key}: not in data/state.csv.gz")
            continue
        dur, succ, cap, dem = I.instance(st["folder"], st["network"], st["resset"], st["profile"])
        starts = [int(x) for x in r["starts"].split(";")]
        bad = I.check(starts, dur, succ, cap, dem)
        v = int(r["value"])
        if bad:
            c["infeasible"] += 1
            fails.append(f"{key} {r['type']} {v}: {bad}")
            continue
        c["feasible"] += 1
        mk = max(s + d for s, d in zip(starts, dur))
        if mk != v:
            c["makespan differs"] += 1
            fails.append(f"{key} {r['type']} {v}: latest finish {mk}")
        if starts[-1] != v:
            c["end start differs"] += 1
        lb, ub = int(st["lb_1109"]), int(st["ub_1109"])
        if r["type"] == "optimal":
            if lb == ub == v:
                c["optimal = published LB = UB"] += 1
            else:
                c["optimal not reflected"] += 1
                fails.append(f"{key} optimal {v}: published LB {lb} UB {ub} on 9 Nov")
        elif ub <= v:
            c["heuristic: published UB <= value"] += 1
            if ub < v:
                c["heuristic: since beaten"] += 1
        else:
            c["heuristic not reflected"] += 1
            fails.append(f"{key} heuristic {v}: published UB {ub} on 9 Nov")
    keys = ["lines", "feasible", "infeasible", "makespan differs", "end start differs", "optimal = published LB = UB",
            "optimal not reflected", "heuristic: published UB <= value", "heuristic: since beaten",
            "heuristic not reflected", "instance not in state"]
    with open(os.path.join(DATA, "schedule_check.tsv"), "w") as f:
        f.write("set\ttype\t" + "\t".join(keys) + "\n")
        for (s, t), c in sorted(out.items()):
            f.write(f"{s}\t{t}\t" + "\t".join(str(c[k]) for k in keys) + "\n")
    os.makedirs(os.path.join(PAPER, "logs"), exist_ok=True)
    with open(os.path.join(PAPER, "logs", "check_schedules.log"), "w") as f:
        f.write("\n".join(fails) + ("\n" if fails else ""))
    tot = collections.Counter()
    for c in out.values():
        tot.update(c)
    print(dict(tot))
    print(f"{len(fails)} failures listed in logs/check_schedules.log")


if __name__ == "__main__":
    main()
