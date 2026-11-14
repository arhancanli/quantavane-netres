"""The ranked re-run policy on its held-out cells (12 Nov 2026 revision): every number of Section 8.

Reads only frozen files written before the cells were scored, plus the runs' own result rows:
  cell A (time split, 5,582 instances) and cell B (instance set held out, 947 instances) of lane sched-netres-rerun,
  registered 2026-11-09T03:51:42Z before any fit: the frozen predictions of v2 (with the reference columns: v1's
  features refit, lane sched-netres-lb v1's first-pass probability) and of the cross-lane model x1
  (runs/sched/model_rerun_{v2,x1}/pred_{A,B}.tsv, SHA-256 checked against predict_info.json), and the outcome of every
  instance of the cell (pass 3b at 40 s on the Mac for A, Kaggle lb5 at 90 s for B: NR_*/{lb3b,lb5}/RESULTS.tsv);
  cell C, the online head-to-head x1 vs v2 (autoloop c1, registered 2026-11-09T04:45:02Z): frozen scores of both models
  on the 500-instance pool and the 40 s runs of the union of the arms.
Writes data/rerun_cells.tsv.gz (one row per instance and cell), data/rerun_policy.json, tables/rerun.tex,
tables/rerun_calib.tex and numbers_rr.tex (\\qvset{rr-...}).
  python3 -I scripts/rerun_policy.py"""
import gzip
import hashlib
import json
import math
import os

import re

import numpy as np

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = PAPER  # the repository root
SCHED = os.path.join(ENGINE, "runs", "sched")
CELLC = os.path.join(ENGINE, "runs", "autoloop", "cells", "sched-netres-rerun",
                     "NetRes-re-runs-second-chances-at-40-s-x1-vs-v2-head-to-head--313ab5babce4342f")
P3B_SETS = ["NR_RU", "NR_VAR", "NR_RC", "NR_TF", "NR_AD"]     # the plain order: sets in pass 3b's order, ids ascending
N = {}


def put(k, v):
    N["rr-" + k] = v


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def label(c, off=0):
    """(find, LB units) of a RESULTS row, as lane sched-netres-lb labels it; off = 1 for rows with a set column."""
    rec = set(c[9 + off].split("+"))
    lb = int(c[4 + off])
    if "CLOSED" in rec and c[6 + off].isdigit():
        return 1, int(c[6 + off]) - lb
    if "LB" in rec and c[10 + off].strip().lstrip("-").isdigit():
        return 1, int(c[10 + off]) - lb
    return 0, 0


def outcomes(sub, keys):
    out = {}
    for s in P3B_SETS:
        path = os.path.join(SCHED, s, sub, "RESULTS.tsv")
        if not os.path.exists(path):
            continue
        for line in open(path).read().splitlines()[1:]:
            c = line.split("\t")
            if len(c) >= 11 and c[0].isdigit() and (s, int(c[0])) in keys and c[4].isdigit():
                y, g = label(c)
                out[(s, int(c[0]))] = (y, g, float(c[8]), int("CLOSED" in c[9]), c[1], c[2] + "#" + c[3])
    return out


def read_pred(path, cols):
    rows = {}
    lines = open(path).read().splitlines()
    head = lines[0].split("\t")
    for line in lines[1:]:
        c = dict(zip(head, line.split("\t")))
        rows[(c["set"], int(c["id"]))] = {k: (float(c[k]) if c.get(k, "") not in ("", "nan") else math.nan) for k in cols
                                          if k in c} | {"lb": int(c["lb"]), "ub": int(c["ub"])}
    return rows


def cell_rows(name):
    v2dir, x1dir = os.path.join(SCHED, "model_rerun_v2"), os.path.join(SCHED, "model_rerun_x1")
    for d in (v2dir, x1dir):
        info = json.load(open(os.path.join(d, "predict_info.json")))
        ci = info[f"cell_{name}"]
        assert sha(os.path.join(ENGINE, ci["file"])) == ci["sha256"], f"{d} cell {name}: predictions changed"
    v2 = read_pred(os.path.join(v2dir, f"pred_{name}.tsv"), ["p", "p_v1_refit", "p_lb_v1"])
    x1 = read_pred(os.path.join(x1dir, f"pred_{name}.tsv"), ["p"])
    assert set(v2) == set(x1)
    out = outcomes("lb3b" if name == "A" else "lb5", set(v2))
    assert set(out) == set(v2), f"cell {name}: {len(set(v2) - set(out))} instances without an outcome"
    rows = []
    for key in v2:
        y, g, secs, closed, net, prof = out[key]
        rows.append(dict(cell=name, set=key[0], id=key[1], lb=v2[key]["lb"], ub=v2[key]["ub"], x1=x1[key]["p"],
                         v2=v2[key]["p"], v1refit=v2[key]["p_v1_refit"], lbv1=v2[key]["p_lb_v1"], y=y, gain=g,
                         secs=secs, run=1, closed=closed, net=key[0] + ":" + net, prof=key[0] + ":" + prof))
    return rows


def cell_c_rows():
    sc = {}
    for m in ("x1", "v2"):
        for line in open(os.path.join(CELLC, f"scores_{m}.tsv")).read().splitlines()[1:]:
            k, v = line.split("\t")
            st, i = k.split()
            sc.setdefault((st, int(i)), {})[m] = float(v)
    pool = json.load(open(os.path.join(CELLC, "pool.json")))
    bounds = {(e["set"], int(e["id"])): (int(e["lb"]), int(e["ub"])) for e in pool}
    assert set(bounds) == set(sc), "cell C: pool and scores differ"
    runs = {}
    for f in sorted(os.listdir(os.path.join(CELLC, "runs"))):
        if not f.startswith("RESULTS_"):
            continue
        for line in open(os.path.join(CELLC, "runs", f)).read().splitlines()[1:]:
            c = line.split("\t")
            if len(c) >= 12 and c[1].isdigit() and c[5].isdigit():
                key = (c[0], int(c[1]))
                if key not in runs:                      # the first complete row of an instance, as the scorer reads it
                    y, g = label(c, off=1)
                    runs[key] = (y, g, float(c[9]))
    rows = []
    for key, s in sc.items():
        y, g, secs = runs.get(key, (math.nan, math.nan, math.nan))
        rows.append(dict(cell="C", set=key[0], id=key[1], lb=bounds[key][0], ub=bounds[key][1], x1=s.get("x1", math.nan), v2=s.get("v2", math.nan),
                         v1refit=math.nan, lbv1=math.nan, y=y, gain=g, secs=secs, run=int(key in runs)))
    return rows, pool


def plain_key(r):
    return (P3B_SETS.index(r["set"]), r["id"])


def order(rows, score):
    rank = {i: k for k, i in enumerate(sorted(range(len(rows)), key=lambda i: plain_key(rows[i])))}
    if score == "plain":
        return sorted(range(len(rows)), key=lambda i: rank[i])
    return sorted(range(len(rows)), key=lambda i: (-(score(rows[i]) if not math.isnan(score(rows[i])) else -1.0), rank[i]))


def log_comb(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def hyper_upper(N_, K_, n_, x):
    """P(X >= x) for X ~ Hypergeometric(population N_, successes K_, draws n_)."""
    lo, hi = max(0, n_ - (N_ - K_)), min(n_, K_)
    if x <= lo:
        return 1.0
    if x > hi:
        return 0.0
    den = log_comb(N_, n_)
    terms = [log_comb(K_, j) + log_comb(N_ - K_, n_ - j) - den for j in range(x, hi + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))


def discordant_test(y, top_a, top_b):
    """Exact one-sided test that arm a's own instances find more than arm b's own (same size): conditional on the
    finds among the instances in exactly one arm, a's share is hypergeometric under exchangeability."""
    A, B = set(top_a) - set(top_b), set(top_b) - set(top_a)
    a, b = int(sum(y[i] for i in A)), int(sum(y[i] for i in B))
    return len(A), a, b, hyper_upper(len(A) + len(B), a + b, len(A), a)


def auc(y, s):
    y = np.asarray(y); s = np.asarray(s)
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg):
        return math.nan
    allv = np.concatenate([pos, neg])
    ranks = np.argsort(np.argsort(allv, kind="mergesort"), kind="mergesort") + 1.0
    # average ranks for ties
    _, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt)); np.add.at(sums, inv, ranks)
    ranks = (sums / cnt)[inv]
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


RANKINGS = [("x1", "cross-lane model x1", lambda r: r["x1"]),
            ("v2", "re-run model v2", lambda r: r["v2"]),
            ("lbv1", "first-pass ranker v1 (reference)", lambda r: r["lbv1"]),
            ("v1refit", "v1 features refit (reference)", lambda r: r["v1refit"]),
            ("relgap", "rule: relative gap (U-L)/U, largest first", lambda r: (r["ub"] - r["lb"]) / r["ub"]),
            ("gap", "rule: gap U-L, largest first", lambda r: float(r["ub"] - r["lb"])),
            ("plain", "plain order", "plain")]


def analyse(rows, name, boots=2000):
    y = np.array([r["y"] for r in rows], dtype=int)
    gain = np.array([r["gain"] for r in rows], dtype=int)
    secs = np.array([r["secs"] for r in rows])
    n, F = len(rows), int(y.sum())
    res = dict(n=n, finds=F, base_rate=F / n, cpu_hours=float(secs.sum() / 3600), secs_median=float(np.median(secs)),
               secs_min=float(secs.min()), secs_max=float(secs.max()), arms={})
    orders = {k: order(rows, f) for k, _, f in RANKINGS}
    for frac in (0.1, 0.2, 0.5):
        K = int(frac * n)
        for k, lab, f in RANKINGS:
            top = orders[k][:K]
            d = res["arms"].setdefault(k, dict(label=lab))
            d[f"finds{int(frac * 100)}"] = int(y[top].sum())
            d[f"units{int(frac * 100)}"] = int(gain[top].sum())
            d[f"cpuh{int(frac * 100)}"] = float(secs[top].sum() / 3600)
            if frac == 0.2:
                d["K"] = K
                d["p_vs_random"] = hyper_upper(n, F, K, int(y[top].sum()))
                if k != "plain":
                    m, a, b, p = discordant_test(y, top, orders["plain"][:K])
                    d.update(disc_m=m, disc_a=a, disc_b=b, p_vs_plain=p)
                if k not in ("lbv1", "plain"):
                    m, a, b, p = discordant_test(y, top, orders["lbv1"][:K])
                    _, _, _, p2 = discordant_test(y, orders["lbv1"][:K], top)
                    d.update(ref_m=m, ref_a=a, ref_b=b, p_vs_lbv1=p, p_lbv1_vs=p2)
                if callable(f):
                    s = [f(r) for r in rows]
                    d["auc"] = auc(y, s)
                    if k in ("x1", "v2", "lbv1", "v1refit"):
                        pr = np.array(s)
                        d["brier"] = float(np.mean((pr - y) ** 2))
                        d["mean_p"] = float(pr.mean())
                        d["pred_finds20"] = float(pr[top].sum())
    # a closure: the run's new bound reaches the instance's upper bound (record LB up to the UB, or CLOSED)
    closed = np.array([int(r["y"] == 1 and (r["closed"] or r["lb"] + r["gain"] >= r["ub"])) for r in rows], dtype=int)
    res["closures"] = int(closed.sum())
    res["one_unit"] = int(((gain == 1) & (y == 1)).sum())
    res["brier_const"] = float(res["base_rate"] * (1 - res["base_rate"]))
    for frac in (0.2, 0.5):
        K = int(frac * n)
        for k, _, f in RANKINGS:
            res["arms"][k][f"closed{int(frac * 100)}"] = int(closed[orders[k][:K]].sum())
    K20 = int(0.2 * n)
    res["random20"] = K20 * F / n
    for k in ("x1", "v2", "lbv1", "relgap"):
        res["arms"][k]["x_random"] = res["arms"][k]["finds20"] / res["random20"]
    res["arms"]["v2"]["x_rule"] = res["arms"]["v2"]["finds20"] / res["arms"]["relgap"]["finds20"]
    res["arms"]["lbv1"]["x_rule"] = res["arms"]["lbv1"]["finds20"] / res["arms"]["relgap"]["finds20"]
    res["arms"]["v2"]["units_x_rule"] = res["arms"]["v2"]["units20"] / res["arms"]["relgap"]["units20"]
    # cluster bootstrap: resample whole networks (or whole resource profiles), K = 20% of the resampled cell
    rngc = np.random.default_rng(20261113)
    sc = {k: np.nan_to_num(np.array([f(r) for r in rows], dtype=float), nan=-1.0) for k, _, f in RANKINGS if callable(f)}
    prank0 = np.empty(n); prank0[np.array(orders["plain"])] = np.arange(n)
    for cl in ("net", "prof"):
        groups = {}
        for i, r in enumerate(rows):
            groups.setdefault(r[cl], []).append(i)
        glist = [np.array(v) for v in groups.values()]
        res[f"clusters_{cl}"] = len(glist)
        diffs = {"v2_plain": [], "v2_rule": [], "lbv1_rule": []}
        for _ in range(boots):
            pick = rngc.integers(0, len(glist), len(glist))
            idx = np.concatenate([glist[j] for j in pick])
            m = len(idx); K = int(0.2 * m)
            yb = y[idx]
            top = lambda key: np.lexsort((prank0[idx], -sc[key][idx]))[:K]
            plain_top = np.argsort(prank0[idx], kind="mergesort")[:K]
            fv2, frule, flb = yb[top("v2")].sum(), yb[top("relgap")].sum(), yb[top("lbv1")].sum()
            diffs["v2_plain"].append(int(fv2 - yb[plain_top].sum()))
            diffs["v2_rule"].append(int(fv2 - frule))
            diffs["lbv1_rule"].append(int(flb - frule))
        res[f"cboot_{cl}"] = {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) for k, v in diffs.items()}
    # bootstrap over instances: 95% interval of (finds of each arm - finds of the plain order) at K = 20%
    rng = np.random.default_rng(20261112)
    keys = {k: (np.array([f(r) for r in rows], dtype=float) if callable(f) else None) for k, _, f in RANKINGS}
    prank = np.empty(n); prank[np.array(orders["plain"])] = np.arange(n)
    diffs = {k: [] for k, _, _ in RANKINGS if k != "plain"}
    for _ in range(boots):
        idx = rng.integers(0, n, n)
        K = int(0.2 * n)
        yb, pb = y[idx], prank[idx]
        plain_top = np.lexsort((np.arange(n), pb))[:K]
        base = yb[plain_top].sum()
        for k in diffs:
            s = np.nan_to_num(keys[k][idx], nan=-1.0)
            top = np.lexsort((pb, -s))[:K]
            diffs[k].append(int(yb[top].sum() - base))
    for k, v in diffs.items():
        res["arms"][k]["boot_lo"], res["arms"][k]["boot_hi"] = (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))
    # calibration by deciles of the predicted probability (probability models only)
    res["calib"] = {}
    for k in ("x1", "v2", "lbv1"):
        s = np.array([RANKINGS[[a for a, _, _ in RANKINGS].index(k)][2](r) for r in rows])
        qs = np.quantile(s, np.linspace(0, 1, 11))
        b = np.clip(np.searchsorted(qs, s, side="right") - 1, 0, 9)
        res["calib"][k] = [(float(s[b == j].mean()), float(y[b == j].mean()), int((b == j).sum())) for j in range(10)]
    return res


def analyse_c(rows, pool):
    """The online head-to-head: only the union of the arms was run, so each arm's finds are counted on its own top 100."""
    n = len(rows)
    K = int(0.2 * n)
    y = np.array([r["y"] if r["run"] else -1 for r in rows], dtype=int)
    orders = {"x1": order(rows, lambda r: r["x1"]), "v2": order(rows, lambda r: r["v2"]), "plain": order(rows, "plain")}
    res = dict(n=n, K=K, union_run=int(sum(r["run"] for r in rows)), arms={})
    for k, o in orders.items():
        top = o[:K]
        assert all(y[i] >= 0 for i in top), f"cell C: arm {k} has an instance without a run"
        res["arms"][k] = dict(finds=int(y[top].sum()), cpuh=float(sum(rows[i]["secs"] for i in top) / 3600))
    for a, b in (("x1", "v2"), ("v2", "x1"), ("x1", "plain"), ("v2", "plain")):
        m, fa, fb, p = discordant_test(np.maximum(y, 0), orders[a][:K], orders[b][:K])
        res[f"{a}_vs_{b}"] = dict(m=m, a=fa, b=fb, p=p)
    return res


def fmtp(p):
    if p == 0 or p < 1e-300:
        return "$<10^{-300}$"
    if p < 1e-3:
        e = math.floor(math.log10(p))
        return f"${p / 10 ** e:.1f}\\cdot10^{{{e}}}$"
    return f"{p:.3f}" if p < 0.1 else f"{p:.2f}"


def main():
    A, B = cell_rows("A"), cell_rows("B")
    C, pool = cell_c_rows()
    with gzip.open(os.path.join(PAPER, "data", "rerun_cells.tsv.gz"), "wt") as f:
        cols = ["cell", "set", "id", "lb", "ub", "x1", "v2", "v1refit", "lbv1", "y", "gain", "secs", "run"]
        f.write("\t".join(cols) + "\n")
        for r in A + B + C:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    res = {"A": analyse(A, "A"), "B": analyse(B, "B"), "C": analyse_c(C, pool)}
    # the registry's recorded numbers must be reproduced exactly
    rec = {"A": dict(v2=701, x1=665, plain=423, lbv1=698, v1refit=663), "B": dict(v2=129, x1=126, plain=49, lbv1=133, v1refit=117)}
    for c, d in rec.items():
        for k, v in d.items():
            assert res[c]["arms"][k]["finds20"] == v, (c, k, res[c]["arms"][k]["finds20"], v)
    assert (res["C"]["arms"]["x1"]["finds"], res["C"]["arms"]["v2"]["finds"], res["C"]["arms"]["plain"]["finds"]) == (46, 63, 21), res["C"]["arms"]
    json.dump(res, open(os.path.join(PAPER, "data", "rerun_policy.json"), "w"), indent=1)
    # table: cells A and B, every ranking at K = 20%
    lines = []
    for c in ("A", "B"):
        r = res[c]
        for k, lab, _ in RANKINGS:
            d = r["arms"][k]
            lines.append(" & ".join([
                f"{c}" if k == "x1" else "", lab.replace("(U-L)/U", "$(U-L)/U$").replace("U-L,", "$U-L$,"),
                str(d["finds10"]), str(d["finds20"]), str(d["finds50"]),
                f"{d['auc']:.3f}" if "auc" in d else "--",
                fmtp(d["p_vs_random"]),
                fmtp(d["p_vs_plain"]) if "p_vs_plain" in d else "--",
                f"[{d['boot_lo']:+.0f}, {d['boot_hi']:+.0f}]" if "boot_lo" in d else "--",
                fmtp(d["p_vs_lbv1"]) if "p_vs_lbv1" in d else "--"]) + " \\\\")
        if c == "A":
            lines.append("\\midrule")
    open(os.path.join(PAPER, "tables", "rerun.tex"), "w").write("\n".join(lines) + "\n")
    cal = []
    for c in ("A", "B"):
        for k in ("x1", "v2", "lbv1"):
            cal.append(f"{c} & {k.replace('lbv1', 'first-pass v1')} & " + " & ".join(
                f"{100 * p:.0f}/{100 * o:.0f}" for p, o, _ in res[c]["calib"][k][::-1][:5]) +
                f" & {res[c]['arms'][k]['brier']:.3f} \\\\")
    open(os.path.join(PAPER, "tables", "rerun_calib.tex"), "w").write("\n".join(cal) + "\n")
    # numbers for the text
    fmt = lambda x: f"{x:,}".replace(",", "{,}")
    for c in ("A", "B"):
        r = res[c]
        put(f"{c}-n", fmt(r["n"])); put(f"{c}-finds", fmt(r["finds"])); put(f"{c}-base", f"{100 * r['base_rate']:.1f}")
        put(f"{c}-cpuh", f"{r['cpu_hours']:.1f}"); put(f"{c}-secs-med", f"{r['secs_median']:.2f}")
        put(f"{c}-secs-min", f"{r['secs_min']:.1f}"); put(f"{c}-secs-max", f"{r['secs_max']:.1f}")
        lim = 40.0 if c == "A" else 90.0
        rows_c = A if c == "A" else B
        put(f"{c}-atlimit", f"{100 * sum(1 for x in rows_c if x['secs'] >= lim - 1) / len(rows_c):.1f}")
        put(f"{c}-atlimit-finds", f"{100 * sum(1 for x in rows_c if x['secs'] >= lim - 1 and x['y']) / max(1, sum(x['y'] for x in rows_c)):.1f}")
        for k, _, _ in RANKINGS:
            d = r["arms"][k]
            put(f"{c}-{k}-f20", fmt(d["finds20"])); put(f"{c}-{k}-f10", fmt(d["finds10"])); put(f"{c}-{k}-f50", fmt(d["finds50"]))
            put(f"{c}-{k}-cpuh20", f"{d['cpuh20']:.1f}")
            put(f"{c}-{k}-perh", f"{d['finds20'] / d['cpuh20']:.1f}")
            if "auc" in d: put(f"{c}-{k}-auc", f"{d['auc']:.3f}")
            if "p_vs_plain" in d:
                put(f"{c}-{k}-pplain", fmtp(d["p_vs_plain"]).strip("$")); put(f"{c}-{k}-disc", f"{d['disc_a']}/{d['disc_b']}")
                put(f"{c}-{k}-disc-m", str(d["disc_m"]))
                put(f"{c}-{k}-blo", f"{d['boot_lo']:+.0f}"); put(f"{c}-{k}-bhi", f"{d['boot_hi']:+.0f}")
            if "p_vs_lbv1" in d:
                put(f"{c}-{k}-plbv1", fmtp(d["p_vs_lbv1"]).strip("$")); put(f"{c}-{k}-plbv1-rev", fmtp(d["p_lbv1_vs"]).strip("$"))
                put(f"{c}-{k}-ref", f"{d['ref_a']}/{d['ref_b']}")
            if "brier" in d:
                put(f"{c}-{k}-brier", f"{d['brier']:.3f}"); put(f"{c}-{k}-predf20", f"{d['pred_finds20']:.0f}")
            put(f"{c}-{k}-K", fmt(d["K"]))
    for c in ("A", "B"):
        ar = res[c]["arms"]
        ch = [d["cpuh20"] for d in ar.values()]
        put(f"{c}-cpuh-min", f"{min(ch):.2f}"); put(f"{c}-cpuh-max", f"{max(ch):.2f}")
        put(f"{c}-cpuh-spread", f"{100 * (max(ch) - min(ch)) / min(ch):.2f}")
        gain = ar["v2"]["finds20"] - ar["plain"]["finds20"]
        put(f"{c}-relgap-share", f"{100 * (ar['relgap']['finds20'] - ar['plain']['finds20']) / gain:.0f}")
        put(f"{c}-x1-share", f"{100 * ar['x1']['finds20'] / ar['v2']['finds20']:.0f}")
        put(f"{c}-v2-ratio", f"{ar['v2']['finds20'] / ar['plain']['finds20']:.2f}")
    for c in ("A", "B"):
        r = res[c]
        put(f"{c}-closures", fmt(r["closures"])); put(f"{c}-oneunit", fmt(r["one_unit"]))
        put(f"{c}-random20", f"{r['random20']:.0f}"); put(f"{c}-brier-const", f"{r['brier_const']:.3f}")
        for k in ("x1", "v2", "lbv1", "relgap"):
            put(f"{c}-{k}-xrandom", f"{r['arms'][k]['x_random']:.2f}")
        put(f"{c}-v2-xrule", f"{r['arms']['v2']['x_rule']:.2f}"); put(f"{c}-lbv1-xrule", f"{r['arms']['lbv1']['x_rule']:.2f}")
        put(f"{c}-v2-units-xrule", f"{r['arms']['v2']['units_x_rule']:.2f}")
        for k in ("v2", "plain", "relgap", "lbv1"):
            put(f"{c}-{k}-closed20", str(r["arms"][k]["closed20"])); put(f"{c}-{k}-closed50", str(r["arms"][k]["closed50"]))
        for cl in ("net", "prof"):
            put(f"{c}-nclust-{cl}", fmt(r[f"clusters_{cl}"]))
            for key, (lo, hi) in r[f"cboot_{cl}"].items():
                put(f"{c}-cb-{cl}-{key.replace('_', '-')}", f"{lo:+.0f} to {hi:+.0f}")
    # the first-pass ranker's fourth prospective cell (lb7), from the registry record (data/ab.tsv)
    for line in open(os.path.join(PAPER, "data", "ab.tsv")).read().splitlines()[1:]:
        c = line.split("\t")
        if c[0] == "sched-netres-lb" and c[1] == "v1" and c[3].startswith("NetRes lb7"):
            put("lb7-n", fmt(int(c[6]))); put("lb7-model", fmt(int(c[8]))); put("lb7-plain", fmt(int(c[9])))
            put("lb7-random", f"{float(c[10]):.0f}"); put("lb7-base", f"{100 * float(c[14]):.0f}")
            put("lb7-ratio", f"{int(c[8]) / int(c[9]):.2f}")
    # closures in the two passes that ran the top of the learned ranking (data/runs.tsv), against all closures
    st = {l.split("\t")[0]: l.split("\t") for l in open(os.path.join(PAPER, "data", "runs.tsv")).read().splitlines()[1:]}
    base_n = json.load(open(os.path.join(PAPER, "numbers.json")))
    allc = int(str(base_n["values"]["closed-all"]).replace(",", "").replace("{", "").replace("}", ""))
    k67 = int(st["K6"][6]) + int(st["K7"][6])
    put("K6-closed", st["K6"][6]); put("K7-closed", st["K7"][6]); put("K67-share", f"{100 * k67 / allc:.1f}")
    # rule of three for the re-proof sample: no contradiction among the re-proved claims
    rp = int(str(base_n["values"]["rp-either"]).replace(",", ""))
    put("rp-rule3", f"{100 * 3 / rp:.1f}")
    # x1's training rows, from its registry entry
    reg = json.load(open(os.path.join(ENGINE, "engine", "models", "registry.json")))
    x1v = next(v for v in reg["lanes"]["sched-netres-rerun"]["versions"] if v.get("version") == "x1")
    put("x1-rows", re.search(r"([\d,]+) rows", x1v["model"]).group(1).replace(",", "{,}"))
    rc = res["C"]
    put("C-n", str(rc["n"])); put("C-K", str(rc["K"])); put("C-union", str(rc["union_run"]))
    for k in ("x1", "v2", "plain"):
        put(f"C-{k}", str(rc["arms"][k]["finds"]))
    for a, b in (("x1", "v2"), ("v2", "x1"), ("x1", "plain"), ("v2", "plain")):
        put(f"C-{a}-{b}-p", fmtp(rc[f"{a}_vs_{b}"]["p"]).strip("$"))
        put(f"C-{a}-{b}-disc", f"{rc[f'{a}_vs_{b}']['a']}/{rc[f'{a}_vs_{b}']['b']}")
        put(f"C-{a}-{b}-m", str(rc[f"{a}_vs_{b}"]["m"]))
    with open(os.path.join(PAPER, "numbers_rr.tex"), "w") as f:
        f.write("% written by scripts/rerun_policy.py from the frozen predictions and run rows; do not edit\n")
        for k in sorted(N):
            f.write(f"\\qvset{{{k}}}{{{N[k]}}}\n")
    # figure: cumulative finds against CPU hours spent, every ranking, cells A and B
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    style = {"v2": ("re-run model v2", "-", "C0"), "x1": ("cross-lane model x1", "-", "C1"),
             "lbv1": ("first-pass ranker v1", "--", "C2"), "relgap": ("rule: relative gap", ":", "C3"),
             "plain": ("plain order", "-", "0.5")}
    for ax, (c, rows) in zip(axes, (("A", A), ("B", B))):
        y = np.array([r["y"] for r in rows]); secs = np.array([r["secs"] for r in rows])
        for k, (lab, ls, col) in style.items():
            f = dict((a, g) for a, _, g in RANKINGS)[k]
            o = order(rows, f)
            ax.plot(np.cumsum(secs[o]) / 3600, np.cumsum(y[o]), ls=ls, color=col, label=lab, lw=1.3)
        tot = secs.sum() / 3600
        ax.plot([0, tot], [0, y.sum()], color="0.75", lw=1, label="random (expected)")
        ax.axvline(0.2 * tot, color="0.6", ls=":", lw=0.8)
        ax.set_title(f"cell {c}: {len(rows):,} re-runs at {'40' if c == 'A' else '90'} s", fontsize=9)
        ax.set_xlabel("run hours spent (one worker per run)", fontsize=8); ax.set_ylabel("new bounds found", fontsize=8)
        ax.tick_params(labelsize=7)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(PAPER, "figures", "rerun.pdf"))
    print(json.dumps({c: {k: {kk: vv for kk, vv in v.items() if kk in ("finds20", "auc", "p_vs_plain", "p_vs_lbv1", "boot_lo", "boot_hi", "brier")}
                          for k, v in res[c]["arms"].items()} for c in ("A", "B")}, indent=0)[:3500])
    print("C", json.dumps(res["C"])[:800])


if __name__ == "__main__":
    main()
