"""Exact one-sided p-values for the A/B records (data/ab.tsv): under a uniformly random choice of K of the n instances
of a cell, the number of finds is hypergeometric with F = round(random_mean * n / K) finds in the cell; the p-value of
an arm is P(X >= its finds).  Also the paired test for the hint ablation (data/ablation_hint.tsv): exact two-sided
binomial (McNemar) test on the discordant instances.  Writes data/ab_pvalues.tsv; prints a summary.
  python3 -I scripts/ab_pvalues.py"""
import csv
import math
import os

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")


def log_comb(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def hyper_sf(x, n, F, K):
    """P(X >= x), X ~ Hypergeometric(population n, successes F, draws K)."""
    lo, hi = max(x, 0, K - (n - F)), min(K, F)
    if lo > hi:
        return 0.0
    den = log_comb(n, K)
    terms = [log_comb(F, i) + log_comb(n - F, K - i) - den for i in range(lo, hi + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))


rows = list(csv.DictReader(open(os.path.join(DATA, "ab.tsv")), delimiter="\t"))
out = []
for r in rows:
    if not r["random_mean"] or r["kind"] == "online":
        continue
    n, K = int(r["n"]), int(r["K"])
    F = round(float(r["random_mean"]) * n / K)
    pm = hyper_sf(int(r["model_finds"]), n, F, K)
    pc = hyper_sf(int(r["control_finds"]), n, F, K)
    out.append([r["lane"], r["version"], r["cell"], r["kind"], r["control_arm"], n, K, F, r["model_finds"],
                r["control_finds"], f"{pm:.3g}", f"{pc:.3g}"])
with open(os.path.join(DATA, "ab_pvalues.tsv"), "w", newline="") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(["lane", "version", "cell", "kind", "control_arm", "n", "K", "finds_in_cell", "model_finds",
                "control_finds", "p_model_vs_random", "p_control_vs_random"])
    w.writerows(out)
for o in out:
    print("\t".join(str(x) for x in o))
hint = list(csv.DictReader(open(os.path.join(DATA, "ablation_hint.tsv")), delimiter="\t"))
by = {}
for r in hint:
    by.setdefault((r["set"], r["id"]), {})[r["arm"]] = r["status"] == "OPTIMAL" and int(r["value"]) == int(r["bound"]) or r["status"] == "OPTIMAL"
b = sum(1 for v in by.values() if v.get("hint") and not v.get("none"))
c = sum(1 for v in by.values() if v.get("none") and not v.get("hint"))
m = b + c
p = min(1.0, 2 * sum(math.comb(m, i) for i in range(0, min(b, c) + 1)) / 2 ** m) if m else 1.0
print(f"hint ablation: {len(by)} instances, closed only with hint {b}, only without {c}, exact McNemar p = {p:.3f}")
