"""Our NetRes runs, stage by stage, from the lanes' own result files in runs/sched (local only).

Stages (budgets from the scripts and their logs; CP-SAT 9.15, one worker per run unless noted):
  U1   netres.py: every instance open on 1 Nov, 3 s, capped at the published UB, hinted with the best known schedule
       where the site's BKS file of 1 Nov has one (data/bks_coverage.tsv) (first row of each id in NR_<set>/RESULTS.tsv)
  U2   netres_pass2.py: the U1 instances without a record, 30 s, same model (the id's later rows there)
  L1   netres_lb.py pass 1 (1-3 Nov): destructive caps from the published LB, 30 s (first rows of NR_<set>/lb/RESULTS.tsv,
       as many per set as netres_lb.log printed)
  L3   netres_lb.py pass 3 (7 Nov, --current): 15 s (the other rows of lb/, NR_LA excepted)
  LA   NR_LA's last six instances: 600 s (netres_lb_la.log) and one run of 3600 s on 8 workers (close_la.log)
  L3b  pass3b.py: the pass-3 misses, 40 s;  L3c  pass3b.py --missing: what pass 3 never reached, 15 s
  K4, K5, K6, K7  Kaggle notebook CPUs (runs/kaggle_netres), 90 s, caps from our best proven bound
  M    online A/B re-runs of the learned rankers (merged into NR_<set>/lbm), 40 s
A run's record: CLOSED (proven optimum), UB (schedule below the published UB), LB (proven bound above the LB the run
was judged against). Writes data/runs.tsv (per stage: runs, instances, CPU hours, records) and data/runs_by_set.tsv.
  nice -n 10 python3 -I scripts/extract_runs.py"""
import collections
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repository root
SCHED = os.path.join(ROOT, "runs", "sched")
PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
SETS = ["NR_SP", "NR_AD", "NR_LA", "NR_TF", "NR_RC", "NR_RU", "NR_VAR"]
FOLDER = {"lb3b": "L3b", "lb3c": "L3c", "lb4": "K4", "lb5": "K5", "lb6": "K6", "lb7": "K7", "lb8": "K8", "lbm": "M"}
INFO = {"U1": ("Mac", "3 s, UB cap"), "U2": ("Mac", "30 s, UB cap"),
        "L1": ("Mac", "30 s, destructive"), "L3": ("Mac", "15 s, destructive"),
        "LA": ("Mac", "600 s; one run 3600 s x 8 workers"), "L3b": ("Mac", "40 s, destructive"),
        "L3c": ("Mac", "15 s, destructive"), "K4": ("Kaggle", "90 s, destructive"), "K5": ("Kaggle", "90 s, destructive"),
        "K6": ("Kaggle", "90 s, destructive"), "K7": ("Kaggle", "90 s, destructive"),
        "K8": ("Kaggle", "90 s, destructive"), "M": ("Mac", "40 s, destructive")}


def rows(path):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path).read().splitlines()[1:]:
        c = line.split("\t")
        if len(c) >= 10 and c[4].isdigit() and c[5].isdigit():
            out.append(c)
    return out


def pass1_counts():
    n = collections.Counter()
    for line in open(os.path.join(SCHED, "netres_lb.log")):
        m = re.match(r"(NR_\w+) (\d+): LB ", line)
        if m:
            n[m.group(1)] += 1
    return n


def main():
    staged = []        # (stage, set, row)
    p1 = pass1_counts()
    for s in SETS:
        seen = set()
        for c in rows(os.path.join(SCHED, s, "RESULTS.tsv")):
            staged.append(("U1" if c[0] not in seen else "U2", s, c))
            seen.add(c[0])
        lb = rows(os.path.join(SCHED, s, "lb", "RESULTS.tsv"))
        for k, c in enumerate(lb):
            stage = "LA" if s == "NR_LA" else ("L1" if k < p1[s] else "L3")
            staged.append((stage, s, c))
        for sub, stage in FOLDER.items():
            for c in rows(os.path.join(SCHED, s, sub, "RESULTS.tsv")):
                staged.append((stage, s, c))
    agg = collections.defaultdict(lambda: collections.Counter())
    ids = collections.defaultdict(set)
    budget_max = collections.defaultdict(float)
    for stage, s, c in staged:
        tags = set(c[9].split("+"))
        secs = float(c[8])
        workers = 8 if stage == "LA" and secs > 1000 else 1
        for key in (stage, (stage, s)):
            a = agg[key]
            a["runs"] += 1
            a["cpu_s"] += secs * workers
            a["closed"] += "CLOSED" in tags
            a["ub"] += "UB" in tags
            a["lb"] += "LB" in tags
            a["find"] += bool(tags & {"CLOSED", "LB"})
            a["infeasible"] += c[7] == "INFEASIBLE"
            ids[key].add((s, c[0]))
            budget_max[key] = max(budget_max[key], secs)
    order = ["U1", "U2", "L1", "L3", "LA", "L3b", "L3c", "K4", "K5", "K6", "K7", "K8", "M"]
    with open(os.path.join(DATA, "runs.tsv"), "w") as f:
        f.write("stage\tplatform\tbudget\truns\tinstances\tcpu_hours\tclosed\tub\tlb\tfind\tinfeasible\tmax_secs\n")
        for st in order:
            if st not in agg:
                continue
            a = agg[st]
            f.write(f"{st}\t{INFO[st][0]}\t{INFO[st][1]}\t{a['runs']}\t{len(ids[st])}\t{a['cpu_s'] / 3600:.1f}\t"
                    f"{a['closed']}\t{a['ub']}\t{a['lb']}\t{a['find']}\t{a['infeasible']}\t{budget_max[st]:.1f}\n")
    with open(os.path.join(DATA, "runs_by_set.tsv"), "w") as f:
        f.write("stage\tset\truns\tinstances\tcpu_hours\tclosed\tub\tlb\tfind\n")
        for st in order:
            for s in SETS:
                a = agg.get((st, s))
                if a:
                    f.write(f"{st}\t{s}\t{a['runs']}\t{len(ids[(st, s)])}\t{a['cpu_s'] / 3600:.1f}\t{a['closed']}\t"
                            f"{a['ub']}\t{a['lb']}\t{a['find']}\n")
    with open(os.path.join(DATA, "la_last.tsv"), "w") as f:
        f.write("id\tpub_lb\tpub_ub\tbound\tstatus\tsecs\tworkers\n")
        for stage, s, c in staged:
            if stage == "LA":
                f.write(f"{c[0]}\t{c[4]}\t{c[5]}\t{c[10]}\t{c[7]}\t{float(c[8]):.1f}\t"
                        f"{8 if float(c[8]) > 1000 else 1}\n")
    # which open instances had a published best known schedule to hint U1 with (the site's BKS file of 1 Nov)
    with open(os.path.join(DATA, "bks_coverage.tsv"), "w") as f:
        f.write("set\tbks_lines\topen_1101\topen_with_bks\n")
        for s in SETS:
            ids, on = set(), False
            for line in open(os.path.join(SCHED, s, f"{s}_BKS.20261101.csv"), encoding="latin-1"):
                c = line.split(";")
                if c[0] == "ID":
                    on = True
                elif on and c[0].isdigit():
                    ids.add(c[0])
            u1 = {c[0] for stage, ss, c in staged if stage == "U1" and ss == s}
            f.write(f"{s}\t{len(ids)}\t{len(u1)}\t{len(u1 & ids)}\n")
    tot = collections.Counter()
    for st in order:
        if st in agg:
            tot.update(agg[st])
    print(f"runs {tot['runs']}, CPU hours {tot['cpu_s'] / 3600:.1f}; pass-1 rows per set {dict(p1)}")


if __name__ == "__main__":
    main()
