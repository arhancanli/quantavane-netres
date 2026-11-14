# Quantavane NetRes lower-bound pass on a Kaggle session (7 Nov 2026). The dataset holds code/netres.py,
# code/rcpsp_cpsat.py and tasks.jsonl (each task carries its network and resource profile). This kernel takes shard
# SHARD of NSHARD, runs the same destructive CP-SAT caps as runs/sched/netres_lb.py with every core, in chunks with a
# fresh pool (a broken pool loses one chunk, retried once), and stops starting new chunks before BUDGET_HOURS.
# Output: /kaggle/working/RESULTS.tsv (netres_lb.py's columns plus set), SOLUTIONS.txt, summary.json.
SHARD = 0
NSHARD = 1
BUDGET_HOURS = 11.3
KERNEL_SLUG = "qv-netres-lb4-s0"
import concurrent.futures as cf, glob, json, os, subprocess, sys, time

ROOT = os.environ.get("NR_KAGGLE_ROOT", "/kaggle")
OUT = os.environ.get("NR_OUT", os.path.join(ROOT, "working"))
PKG = os.path.dirname(glob.glob(os.path.join(ROOT, "input", "**", "tasks.jsonl"), recursive=True)[0])
try:
    import ortools  # noqa: F401
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ortools==9.15.6755"], check=True)
sys.path.insert(0, os.path.join(PKG, "code"))
import netres as N  # noqa: E402

COLS = "id\tref1\tref2\tref3\tpub_lb\tpub_ub\tours\tstatus\tsecs\trecord\tbound\tset\n"


def solve_seeded(t):
    """Worker: seed netres's cache from the task itself (no instance files), then the lane's own solve()."""
    N._cache[t["ref1"]] = tuple(t["net"])
    N._cache.setdefault(t["ref2"], {})[t["ref3"]] = tuple(t["res"])
    return N.solve(t)


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    tasks = [json.loads(l) for l in open(os.path.join(PKG, "tasks.jsonl"))][SHARD::NSHARD]
    workers = max(1, os.cpu_count() or 2)
    res_f = open(os.path.join(OUT, "RESULTS.tsv"), "w")
    res_f.write(COLS)
    sol_f = open(os.path.join(OUT, "SOLUTIONS.txt"), "w")
    st = {"done": 0, "lb": 0, "rec": 0}

    def run_chunk(batch):
        ok, bad = [], []
        with cf.ProcessPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(solve_seeded, t): t for t in batch}
            for fu in cf.as_completed(futs):
                try:
                    ok.append(fu.result())
                except Exception as exc:
                    bad.append(futs[fu])
                    print("task failed:", repr(exc)[:160], flush=True)
        return ok, bad

    def record(results):
        for t, starts, status, sec in results:
            t2 = dict(t, lb=t["pub_lb"])  # judged against the published LB, as the site reads it
            ours, rec, note = N.outcome(t2, starts, status)
            if {"UB", "CLOSED"} & set(rec.split("+")):
                sol_f.write(f"{t['id']};" + ";".join(map(str, starts)) + "\n")
                st["rec"] += 1
            st["lb"] += "LB" in rec.split("+")
            res_f.write(N.row(t2, ours, status, sec, rec).rstrip("\n") + f"\t{t['set']}\n")
            st["done"] += 1
        res_f.flush()
        sol_f.flush()

    chunk = max(workers * 4, 16)
    retry, k = [], 0
    while k < len(tasks):
        left = BUDGET_HOURS * 3600 - (time.time() - t0)
        secs = max(t["secs"] for t in tasks[k:k + chunk])
        if left < secs * 6 + 300:
            print(f"budget: stopping before task {k} of {len(tasks)}", flush=True)
            break
        ok, bad = run_chunk(tasks[k:k + chunk])
        record(ok)
        retry += bad
        k += chunk
        print(f"{time.strftime('%H:%M:%S')} {st['done']}/{len(tasks)} done, {st['lb']} new bounds, {st['rec']} schedule records", flush=True)
    if retry and BUDGET_HOURS * 3600 - (time.time() - t0) > 900:
        ok, bad = run_chunk(retry)
        record(ok)
    summary = {"kernel": KERNEL_SLUG, "shard": SHARD, "nshard": NSHARD, "tasks": len(tasks), "done": st["done"],
               "new_bounds": st["lb"], "schedule_records": st["rec"], "workers": workers,
               "hours": round((time.time() - t0) / 3600, 3)}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    print("summary:", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
