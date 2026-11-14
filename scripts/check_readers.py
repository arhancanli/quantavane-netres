"""Do the search code and the paper's checks read the same instances? For every NetRes instance with a result of ours
listed on the Solutions Update (data/listed_lines.csv.gz), build it twice: with the search code's reader
(runs/sched/netres.py network() and resset(), which every CP-SAT run of ours used, on the Mac and,
through runs/kaggle_netres/build.py, on Kaggle) and with scripts/instances.py (written separately for the paper), and
compare durations, successors, capacities and demands. A lower bound is only as good as the instance it was proved
on; the schedule checks cannot see a capacity read too low. Writes data/reader_check.tsv.
  nice -n 10 python3 -I scripts/check_readers.py"""
import collections
import csv
import gzip
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repository root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(ROOT, "runs", "sched"))
import instances as I  # noqa: E402
import netres as N  # noqa: E402

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")


def main():
    ours = {(r["set"], r["id"]) for r in csv.DictReader(gzip.open(os.path.join(DATA, "listed_lines.csv.gz"), "rt"))}
    out = collections.defaultdict(collections.Counter)
    for r in csv.DictReader(gzip.open(os.path.join(DATA, "state.csv.gz"), "rt")):
        if (r["set"], r["id"]) not in ours:
            continue
        c = out[r["set"]]
        dur, succ, cap, dem = I.instance(r["folder"], r["network"], r["resset"], r["profile"])
        n, rr, dur2, succ2 = N.network(f"{r['folder']}\\EV{r['network']}.rcp")
        cap2, dem30 = N.resset(r["resset"])[int(r["profile"])]
        dem2 = [[0] * len(cap2)] + dem30 + [[0] * len(cap2)]
        c["instances"] += 1
        c["same"] += (dur, succ, cap, dem) == (dur2, succ2, cap2, dem2)
    with open(os.path.join(DATA, "reader_check.tsv"), "w") as f:
        f.write("set\tinstances\tidentical\n")
        for s, c in sorted(out.items()):
            f.write(f"{s}\t{c['instances']}\t{c['same']}\n")
    print({s: (c["instances"], c["same"]) for s, c in out.items()})


if __name__ == "__main__":
    main()
