"""Side-by-side NetRes lower-bound runs for model A/B cells (lanes sched-netres-rerun and sched-netres-lb-params).

JOBS.tsv lines (tab-separated): tag, set, id, ref1, ref2, ref3, lb, ub, seconds, setting. The setting names the CP-SAT
parameters: A = LB_PARAMS (the plain setting of every NetRes lower-bound pass), B = LB_PARAMS + linearization_level 2.
Every job is the same procedure as pass 3b (netres.solve: destructive caps from lb upward, below ub, one CP-SAT worker,
no hint); jobs are submitted in file order to one pool of WORKERS processes, so arms written alternately share the load.
Rows go to OUT_DIR/RESULTS.tsv (tag, setting, set, then the columns of NR_*/lb3b/RESULTS.tsv) and schedules that beat the
UB or close an instance to OUT_DIR/SOLUTIONS.txt (set;id;start times). A restart skips the jobs already in RESULTS.tsv.
  nice -n 10 .venv/bin/python -I engine/models/netres_jobs.py JOBS.tsv OUT_DIR [WORKERS]
  .venv/bin/python -I engine/models/netres_jobs.py score OUT_DIR/RESULTS.tsv TAG_PREFIX [OUT.json]
      per tag: runs, finds (a proven bound above the starting LB: record LB or CLOSED), LB units, seconds; and the
      instances two tags share, with each tag's finds on them"""
import concurrent.futures as cf
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED = os.path.join(os.path.dirname(os.path.dirname(HERE)), "runs", "sched")
sys.path.insert(0, SCHED)
import netres as N  # noqa: E402
from rcpsp_cpsat import LB_PARAMS  # noqa: E402

SETTINGS = {"A": LB_PARAMS, "B": LB_PARAMS + " linearization_level: 2"}
COLS = "tag\tsetting\tset\tid\tref1\tref2\tref3\tpub_lb\tpub_ub\tours\tstatus\tsecs\trecord\tbound\n"


def solve(task):
    return N.solve(task)


def score(path, prefix, out=None):
    import json
    arms = {}
    for line in open(path).read().splitlines()[1:]:
        c = line.split("\t")
        if not c[0].startswith(prefix):
            continue
        rec, lb = set(c[12].split("+")), int(c[7])
        y = int(bool({"LB", "CLOSED"} & rec))
        top = int(c[9]) if "CLOSED" in rec and c[9].isdigit() else (int(c[13]) if c[13].lstrip("-").isdigit() else lb)
        arms.setdefault(c[0], {})[(c[2], int(c[3]))] = (y, (top - lb) if y else 0, float(c[11]))
    res = {t: dict(runs=len(v), finds=sum(x[0] for x in v.values()), lb_units=sum(x[1] for x in v.values()),
                   seconds=round(sum(x[2] for x in v.values()), 1)) for t, v in sorted(arms.items())}
    tags = sorted(arms)
    res["shared"] = {f"{a} & {b}": dict(instances=len(set(arms[a]) & set(arms[b])),
                                        finds={a: sum(arms[a][k][0] for k in set(arms[a]) & set(arms[b])),
                                               b: sum(arms[b][k][0] for k in set(arms[a]) & set(arms[b]))})
                     for i, a in enumerate(tags) for b in tags[i + 1:]}
    txt = json.dumps(res, indent=1)
    print(txt)
    if out:
        open(out, "w").write(txt + "\n")


def main():
    if sys.argv[1] == "score":
        return score(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    jobs_path, outdir = sys.argv[1], sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    os.makedirs(outdir, exist_ok=True)
    res = os.path.join(outdir, "RESULTS.tsv")
    done = set()
    if os.path.exists(res):
        for line in open(res).read().splitlines()[1:]:
            c = line.split("\t")
            done.add((c[0], c[1], c[2], c[3]))
    else:
        open(res, "w").write(COLS)
    tasks = []
    for line in open(jobs_path).read().splitlines():
        if not line.strip() or line.startswith("tag\t"):
            continue
        tag, s, i, r1, r2, r3, lb, ub, secs, setting = line.split("\t")
        if (tag, setting, s, i) in done:
            continue
        tasks.append(dict(tag=tag, setting=setting, set=s, id=int(i), ref1=r1, ref2=r2, ref3=int(r3), lb=int(lb),
                          ub=int(ub), hint=None, secs=float(secs), params=SETTINGS[setting], destructive=True))
    print(f"{time.strftime('%F %T')}: {len(tasks)} runs ({len(done)} done before), {workers} workers", flush=True)
    with open(res, "a") as out, open(os.path.join(outdir, "SOLUTIONS.txt"), "a") as sol, \
            cf.ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(solve, t) for t in tasks]
        for fu in cf.as_completed(futs):
            t, starts, status, sec = fu.result()
            ours, record, note = N.outcome(t, starts, status)
            if {"UB", "CLOSED"} & set(record.split("+")):
                sol.write(f"{t['set']};{t['id']};" + ";".join(map(str, starts)) + "\n")
                sol.flush()
            out.write(f"{t['tag']}\t{t['setting']}\t{t['set']}\t" + N.row(t, ours, status, sec, record))
            out.flush()
            print(f"{t['tag']} {t['setting']} {t['set']} {t['id']}: LB {t['lb']} UB {t['ub']} bound {t['bound']} "
                  f"ours {ours} {status} {sec:.1f} s {record} {note}", flush=True)
    print(f"{time.strftime('%F %T')}: done", flush=True)


if __name__ == "__main__":
    main()
