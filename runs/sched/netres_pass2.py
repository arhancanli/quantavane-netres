"""NetRes second pass: the instances the first pass (runs/sched/netres.py, 3 s) tried without a record get SECS seconds
each (default 30), with the same model, bound and hint (runs/sched/netres.py solve()). Results are appended to the
set's RESULTS.tsv and SOLUTIONS.txt in the same format (make_upload.py keeps the best row per id; since 1 Nov 2026 rows
carry the run's proven lower bound as a trailing column and record LB when it beats the published LB); ids tried here
are listed in PASS2.txt so a restart skips them. An id counts as tried without a record when its rows have no CLOSED or
UB record (an LB record alone does not close it). Nothing is uploaded from here.
  .venv/bin/python -I runs/sched/netres_pass2.py [WORKERS] [SECS] [SET ...]"""
import concurrent.futures as cf
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netres as N  # noqa: E402


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    names = sys.argv[3:] or ["NR_LA", "NR_RU", "NR_VAR", "NR_RC", "NR_TF", "NR_SP", "NR_AD"]  # smallest first
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        for ds in names:
            d = os.path.join(N.HERE, ds)
            res, p2 = os.path.join(d, "RESULTS.tsv"), os.path.join(d, "PASS2.txt")
            if not os.path.exists(res):
                continue
            best, rows = {}, {}
            for row in open(res).read().splitlines()[1:]:
                c = row.split("\t")
                if len(c) < 10:      # a partial last line (another writer mid-row)
                    continue
                rows[c[0]] = c
                found = "-" if not ({"CLOSED", "UB"} & set(c[9].split("+"))) else c[9]
                best[c[0]] = best.get(c[0], "-") if found == "-" else found
            done = set(open(p2).read().split()) if os.path.exists(p2) else set()
            bks = {}
            on = False
            for line in open(os.path.join(d, ds + "_BKS.csv"), encoding="latin-1"):
                c = line.rstrip("\r\n").split(";")
                if c[0] == "ID":
                    on = True
                elif on and c[0].isdigit():
                    bks[int(c[0])] = [int(x) for x in c[4:] if x.strip().isdigit()]
            tasks = []
            for i, rec in best.items():
                if rec != "-" or i in done:
                    continue
                c = rows[i]
                tasks.append({"id": int(i), "ref1": c[1], "ref2": c[2], "ref3": int(c[3]), "lb": int(c[4]),
                              "ub": int(c[5]), "hint": bks.get(int(i)), "secs": secs})
            print(f"{ds}: {len(tasks)} instances for the {secs:.0f} s pass ({len(done)} done)", flush=True)
            with open(res, "a") as out, open(os.path.join(d, "SOLUTIONS.txt"), "a") as sol, open(p2, "a") as mark:
                for k in range(0, len(tasks), 2000):
                    for fu in cf.as_completed([pool.submit(N.solve, t) for t in tasks[k:k + 2000]]):
                        try:
                            t, starts, status, sec = fu.result()
                        except Exception as exc:
                            print(ds, "task failed:", repr(exc)[:200], flush=True)
                            continue
                        if starts:
                            sol.write(f"{t['id']};" + ";".join(map(str, starts)) + "\n")
                        ours, record, note = N.outcome(t, starts, status)
                        if note:
                            print(ds, t["id"], note, flush=True)
                        out.write(N.row(t, ours, status, sec, record))
                        mark.write(f"{t['id']}\n")
                    out.flush(); sol.flush(); mark.flush()
    print("netres pass 2 done", time.strftime("%F %T"), flush=True)


if __name__ == "__main__":
    main()
