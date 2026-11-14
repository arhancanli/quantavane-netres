"""Share of NR(RC) instances with resource strength below 0.1 (RS decile 0) at each nominal RC level, from
data/totals.tsv; used in Section 7 to test whether RS explains the non-monotone open counts.  Writes data/rc_rs.tsv.
  python3 -I scripts/rc_rs.py"""
import collections
import csv
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
tot, low = collections.Counter(), collections.Counter()
for r in csv.DictReader(open(os.path.join(DATA, "totals.tsv")), delimiter="\t"):
    if r["set"] == "NR_RC":
        tot[r["level"]] += int(r["n"])
        low[r["level"]] += int(r["n"]) if r["rs_decile"] == "0" else 0
with open(os.path.join(DATA, "rc_rs.tsv"), "w") as fh:
    fh.write("rc_level\tinstances\trs_below_0.1\tshare_pct\n")
    for lv in sorted(tot):
        fh.write(f"{lv}\t{tot[lv]}\t{low[lv]}\t{100 * low[lv] / tot[lv]:.1f}\n")
print(open(os.path.join(DATA, "rc_rs.tsv")).read())
