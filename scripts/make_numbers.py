"""Every number of the paper, from the files in data/ (written by the extract_*, check_*, reprove_sample and ab_table
scripts). Writes numbers.tex (\\qvset{key}{value}; the paper prints them with \\val{key}), numbers.json and the tables
in tables/. Stops if a cross-check fails (the parse of the dataset files against the site's own statistics, the
reflection of every line we sent, the schedule re-check).
  python3 -I scripts/make_numbers.py"""
import collections
import csv
import gzip
import json
import math
import os
import sys

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
TAB = os.path.join(PAPER, "tables")
SETS = ["NR_SP", "NR_AD", "NR_LA", "NR_TF", "NR_RC", "NR_RU", "NR_VAR"]
SHORT = {s: s[3:] for s in SETS}
DATES = {"A": "2026-11-01", "B": "2026-11-06", "C": "2026-11-09"}
TAG = {"A": "1101", "B": "1106", "C": "1109"}
CTRL = {"NR_SP": "SP", "NR_AD": "AD", "NR_LA": "LA", "NR_TF": "TF", "NR_RC": "RC", "NR_RU": "RU",
        "NR_VAR": "RC spread"}
V = {}
CHECKS = []


def fi(n):
    return f"{int(n):,}"


def pc(x, d=1):
    return f"{100 * x:.{d}f}\\%"


def put(key, value):
    if key in V and V[key] != value:
        sys.exit(f"{key} set twice: {V[key]} and {value}")
    V[key] = value


def need(ok, what):
    CHECKS.append((bool(ok), what))
    if not ok:
        sys.exit("CHECK FAILED: " + what)


def tsv(name):
    return list(csv.DictReader(open(os.path.join(DATA, name)), delimiter="\t"))


def gz(name):
    return list(csv.DictReader(gzip.open(os.path.join(DATA, name), "rt")))


def table(name, head, rows, align, foot=None):
    out = ["\\begin{tabular}{" + align + "}", "\\toprule", " & ".join(head) + " \\\\", "\\midrule"]
    for r in rows:
        if r == "MID":
            out.append("\\midrule")
        else:
            out.append(" & ".join(str(x) for x in r) + " \\\\")
    if foot:
        out.append("\\midrule")
        for r in foot:
            out.append(" & ".join(str(x) for x in r) + " \\\\")
    out += ["\\bottomrule", "\\end{tabular}"]
    open(os.path.join(TAB, name), "w").write("\n".join(out) + "\n")


def main():
    os.makedirs(TAB, exist_ok=True)
    summ = {(r["set"], r["date"]): r for r in tsv("summary.tsv")}
    site = {r["set"]: r for r in tsv("site_stats.tsv")}
    srcs = tsv("sources.tsv")
    design = json.load(open(os.path.join(DATA, "design.json")))
    checks = json.load(open(os.path.join(DATA, "checks.json")))
    totals = tsv("totals.tsv")
    state = gz("state.csv.gz")

    # ---------------------------------------------------------------- sources
    lm = sorted({r["last_modified"] for r in srcs if r["date"] == DATES["C"]})
    put("lastmod-first", lm[0].replace(" GMT", "").split(", ")[1] + " GMT")
    put("lastmod-last", lm[-1].replace(" GMT", "").split(", ")[1] + " GMT")
    put("dataset-bytes-C", f"{sum(int(r['bytes']) for r in srcs if r['date'] == DATES['C']) / 1e6:.0f}")
    for s in SETS:
        for k in ("instance columns differing 2026-11-01 vs 2026-11-06", "instance columns differing 2026-11-01 vs 2026-11-09"):
            need(checks[s][k] == 0, f"{s}: {k} = 0")
        need(not checks[s]["anomalies"], f"{s}: no parse anomalies")

    # ---------------------------------------------------------------- status by date
    tot = collections.Counter()
    rows = []
    for s in SETS:
        sh = SHORT[s]
        n = int(summ[(s, DATES["A"])]["rows"])
        put(f"inst-{sh}", fi(n))
        tot["inst"] += n
        for d, date in DATES.items():
            r = summ[(s, date)]
            need(int(r["lb_above_ub"]) == 0, f"{s} {date}: no LB above UB")
            put(f"open-{sh}-{d}", fi(r["open"]))
            put(f"units-{sh}-{d}", fi(r["open_units"]))
            tot[f"open-{d}"] += int(r["open"])
            tot[f"units-{d}"] += int(r["open_units"])
            need("4" not in json.loads(r["lb_refs"]) or d != "A", f"{s}: no reference 4 on 1 Nov")
        oa, oc = int(summ[(s, DATES["A"])]["open"]), int(summ[(s, DATES["C"])]["open"])
        ua, uc = int(summ[(s, DATES["A"])]["open_units"]), int(summ[(s, DATES["C"])]["open_units"])
        put(f"closed-{sh}", fi(oa - oc))
        put(f"closedpct-{sh}", pc((oa - oc) / oa))
        put(f"unitsdrop-{sh}", pc((ua - uc) / ua))
        rows.append([f"NR({sh})", fi(n), fi(oa), fi(summ[(s, DATES["B"])]["open"]), fi(oc), fi(oa - oc),
                     pc((oa - oc) / oa), fi(ua), fi(uc)])
        # the site's statistics block of 9 Nov against our parse of its dataset file
        st, r = site[s], summ[(s, DATES["C"])]
        for a, b in (("closed", "closed"), ("open", "open"), ("sum_lb", "sum_lb"), ("sum_ub", "sum_ub"),
                     ("open_units", "open_units"), ("instances", "rows")):
            need(int(st[a]) == int(r[b]), f"{s}: site statistics {a} = parse {b}")
        need(int(st["ref4_lower"]) == json.loads(r["lb_refs"]).get("4", 0), f"{s}: ref 4 lower bounds")
        need(int(st["ref4_upper"]) == json.loads(r["ub_refs"]).get("4", 0), f"{s}: ref 4 upper bounds")
    put("inst-all", fi(tot["inst"]))
    for d in DATES:
        put(f"open-all-{d}", fi(tot[f"open-{d}"]))
        put(f"units-all-{d}", fi(tot[f"units-{d}"]))
        put(f"openpct-all-{d}", pc(tot[f"open-{d}"] / tot["inst"], 2))
    put("closed-all", fi(tot["open-A"] - tot["open-C"]))
    put("closedpct-all", pc((tot["open-A"] - tot["open-C"]) / tot["open-A"]))
    put("closed-BC", fi(tot["open-B"] - tot["open-C"]))
    put("closed-AB", fi(tot["open-A"] - tot["open-B"]))
    put("unitsdrop-all", pc((tot["units-A"] - tot["units-C"]) / tot["units-A"]))
    fully = [s for s in SETS if int(summ[(s, DATES["C"])]["open"]) == 0]
    need(fully == ["NR_LA"], "NR_LA is the only set without open instances on 9 Nov")
    need(all(int(summ[(s, DATES[d])]["open"]) > 0 for s in SETS for d in "AB"), "every set had open instances on 1 and 6 Nov")
    rows_foot = [["All", fi(tot["inst"]), fi(tot["open-A"]), fi(tot["open-B"]), fi(tot["open-C"]),
                  fi(tot["open-A"] - tot["open-C"]), pc((tot["open-A"] - tot["open-C"]) / tot["open-A"]),
                  fi(tot["units-A"]), fi(tot["units-C"])]]
    table("status.tex", ["Set", "Instances", "Open 1 Nov", "Open 6 Nov", "Open 9 Nov", "Closed", "Share",
                         "Gap 1 Nov", "Gap 9 Nov"], rows, "lrrrrrrrr", rows_foot)

    # ---------------------------------------------------------------- design
    rs_of = {s: list(checks[s]["ressets"])[0] for s in SETS}
    drows = []
    for s in SETS:
        sh = SHORT[s]
        rs = rs_of[s]
        prof = design[rs]["profiles"]
        n = int(summ[(s, DATES["A"])]["rows"])
        need(n % prof == 0, f"{s}: instances divisible by profiles")
        nets = n // prof
        folders = sorted(checks[s]["folders"].values())
        put(f"nets-{sh}", fi(nets))
        put(f"profiles-{sh}", fi(prof))
        levels = sorted({r["level"] for r in totals if r["set"] == s}, key=lambda x: (len(x), x))
        res = list(design[rs]["resources"])[0]
        ru = ", ".join(sorted(design[rs]["RU"], key=float))
        rcv = sorted((float(x) for x in design[rs]["RC"]))
        rc = ", ".join(f"{x:.2f}".rstrip("0").rstrip(".") for x in rcv)
        if len(rcv) > 4 and all(abs(b - a - (rcv[1] - rcv[0])) < 1e-9 for a, b in zip(rcv, rcv[1:])):
            rc = f"{rcv[0]:g}--{rcv[-1]:g} (step {rcv[1] - rcv[0]:.1f})"
        sub = "; ".join(f.replace("Set ", "") for f in folders) if len(folders) > 1 else folders[0].replace("Set ", "")
        if s in ("NR_RC", "NR_RU", "NR_VAR"):
            sub = f"Set 1 SP (subset)"
        drows.append([f"NR({sh})", sub.replace("Set ", ""), fi(nets), rs.replace(".txt", ""), fi(prof), res, ru, rc,
                      (CTRL[s] + " (" + ", ".join(levels) + ")" if len(levels) <= 4 else
                       CTRL[s] + " (" + levels[0] + "--" + levels[-1] + ")") if s != "NR_SP" else "SP (0.1--0.9)", fi(n)])
    table("design.tex", ["Set", "Networks", "\\#", "Profiles", "\\#", "$K$", "RU", "RC", "Factor (levels)", "Instances"],
          drows, "lp{3.1cm}rlrrllp{2.6cm}r")
    mt = design["MT30 subsets"]
    put("mt-networks", fi(sum(mt.values())))
    put("mt-sp", fi(mt["Set 1 SP"]))
    others = sorted({v for k, v in mt.items() if k != "Set 1 SP"})
    need(len(others) == 1, "the other MT30 subsets have one size")
    put("mt-sub", fi(others[0]))
    put("mt-subn", fi(len(mt) - 1))
    sizes = [int(summ[(s, DATES["A"])]["rows"]) for s in SETS]
    put("inst-min", fi(min(sizes)))
    put("inst-max", fi(max(sizes)))

    # ---------------------------------------------------------------- prior bounds of the open instances (1 Nov)
    lbc, ubc = collections.Counter(), collections.Counter()
    for r in state:
        if int(r["lb_1101"]) < int(r["ub_1101"]):
            lbc[r["lbref_1101"]] += 1
            ubc[r["ubref_1101"]] += 1
    names = {"1": "DH", "2": "KS", "3": "DV", "CPM": "CPM", "Capacity LB": "CAP", "Sum PT": "SUM"}
    for k, v in lbc.items():
        put(f"prior-lb-{names[k]}", fi(v))
        put(f"prior-lbpct-{names[k]}", pc(v / tot["open-A"]))
    for k, v in ubc.items():
        put(f"prior-ub-{names[k]}", fi(v))
        put(f"prior-ubpct-{names[k]}", pc(v / tot["open-A"]))
    need(sum(lbc.values()) == tot["open-A"], "every open instance has an LB reference")

    # ---------------------------------------------------------------- our results per instance (9 Nov)
    cat = collections.defaultdict(collections.Counter)
    units = collections.defaultdict(collections.Counter)
    gaps = {"A": collections.Counter(), "C": collections.Counter()}
    relgap = []
    others_changed = 0
    for r in state:
        s = r["set"]
        lb0, ub0, lb2, ub2 = (int(r[k]) for k in ("lb_1101", "ub_1101", "lb_1109", "ub_1109"))
        l2, u2 = r["lbref_1109"] == "4", r["ubref_1109"] == "4"
        need(lb0 < ub0, "state rows are the instances open on 1 Nov") if False else None
        if lb2 == ub2:
            k = "c-both" if l2 and u2 else "c-lb" if l2 else "c-ub" if u2 else "c-other"
        else:
            k = "o-both" if l2 and u2 else "o-lb" if l2 else "o-ub" if u2 else ("o-none" if (lb2, ub2) == (lb0, ub0)
                                                                              else "o-other")
            relgap.append((ub2 - lb2) / lb2)
        cat[s][k] += 1
        cat["all"][k] += 1
        others_changed += (lb2 != lb0 and not l2) or (ub2 != ub0 and not u2)
        if l2 or u2:
            units[s]["lb"] += lb2 - lb0
            units[s]["ub"] += ub0 - ub2
            units["all"]["lb"] += lb2 - lb0
            units["all"]["ub"] += ub0 - ub2
        for d, (lb, ub) in (("A", (lb0, ub0)), ("C", (lb2, ub2))):
            if ub > lb:
                g = ub - lb
                gaps[d]["1" if g == 1 else "2" if g == 2 else "3" if g == 3 else "4-5" if g <= 5 else "6-10" if g <= 10
                        else "gt10"] += 1
    need(len(state) == tot["open-A"], "state rows = instances open on 1 Nov")
    need(others_changed == 0, "no bound of an instance open on 1 Nov changed between 1 and 9 Nov except to one of ours")
    need(cat["all"]["c-other"] == 0 and cat["all"]["o-other"] == 0, "no bound changed by anyone else since 1 Nov")
    orows = []
    for s in SETS + ["all"]:
        c = cat[s]
        closed = c["c-both"] + c["c-lb"] + c["c-ub"]
        opened = c["o-both"] + c["o-lb"] + c["o-ub"]
        imp = closed + opened
        key = SHORT.get(s, "all")
        put(f"improved-{key}", fi(imp))
        put(f"oursclosed-{key}", fi(closed))
        for k in ("c-both", "c-lb", "c-ub", "o-both", "o-lb", "o-ub", "o-none"):
            put(f"{k}-{key}", fi(c[k]))
        put(f"oursopen-{key}", fi(opened))
        put(f"lbunits-{key}", fi(units[s]["lb"]))
        put(f"ubunits-{key}", fi(units[s]["ub"]))
        row = ["All" if s == "all" else f"NR({key})", fi(imp), fi(c["c-lb"]), fi(c["c-both"]), fi(c["c-ub"]),
               fi(c["o-lb"]), fi(c["o-ub"] + c["o-both"]), fi(c["o-none"]), fi(units[s]["lb"]), fi(units[s]["ub"])]
        orows.append(row) if s != "all" else None
        if s == "all":
            ofoot = [row]
    table("ours.tex", ["Set", "Improved", "Proof", "Both", "Schedule", "LB up", "UB down", "Untouched", "LB units",
                       "UB units"], orows, "lrrrrrrrrr", ofoot)
    for d in "AC":
        for b, v in gaps[d].items():
            put(f"gap-{d}-{b}", fi(v))
    put("gap1-share-C", pc(gaps["C"]["1"] / tot["open-C"]))
    put("gap1-share-A", pc(gaps["A"]["1"] / tot["open-A"]))
    relgap.sort()
    put("relgap-median-C", pc(relgap[len(relgap) // 2], 2))
    put("relgap-max-C", pc(relgap[-1], 1))

    # ---------------------------------------------------------------- lines sent and listed
    sent = gz("sent_lines.csv.gz")
    listed = gz("listed_lines.csv.gz")
    bysend = collections.Counter(r["send"] for r in sent)
    for d, n in bysend.items():
        put(f"sent-{d[-2:]}", fi(n))
    s04 = {(r["set"], r["id"], r["type"], r["value"]) for r in sent if r["send"] == "2026-11-04"}
    need(all((r["set"], r["id"], r["type"], r["value"]) in s04 for r in sent if r["send"] == "2026-11-06"),
         "every line of the 6 Nov additions repeats a line of the 4 Nov files")
    put("sent-all", fi(len(sent)))
    put("sent-distinct", fi(len({(r["set"], r["id"], r["type"], r["value"]) for r in sent})))
    put("sent-repeated", fi(len(sent) - len({(r["set"], r["id"], r["type"], r["value"]) for r in sent})))
    sent_types = collections.Counter(r["type"] for r in sent)
    for t, n in sent_types.items():
        put("sent-" + t.replace(" ", ""), fi(n))
    put("listed-lines", fi(sum(int(r["copies"]) for r in listed)))
    put("listed-distinct", fi(len(listed)))
    put("listed-twice", fi(sum(1 for r in listed if r["copies"] == "2")))
    need(max(int(r["copies"]) for r in listed) <= 2, "no line listed more than twice")
    sk = {(r["set"], r["id"], r["type"], r["value"]) for r in sent}
    lk = {(r["set"], r["id"], r["type"], r["value"]) for r in listed}
    need(sk <= lk, "every line sent on 4, 6 and 9 Nov is in the site's copies of our files")
    extra = lk - sk
    put("listed-older", fi(len(extra)))
    best = collections.defaultdict(dict)
    for (s, i, t, v) in lk:
        cur = best[(s, i)].get(t)
        v = int(v)
        best[(s, i)][t] = v if cur is None else (max(cur, v) if t == "lower bound" else min(cur, v))
    sup = 0
    for (s, i, t, v) in extra:
        b = best[(s, i)]
        v = int(v)
        if (t == "lower bound" and (b["lower bound"] > v or "optimal" in b)) or \
           (t == "heuristic" and (b["heuristic"] < v or "optimal" in b)) or (t == "optimal" and b["optimal"] < v):
            sup += 1
    put("listed-older-superseded", fi(sup))
    earlier = {(r["set"], r["id"], r["type"], r["value"]) for r in gz("earlier_lines.csv.gz")}
    need(extra <= earlier, "every listed line not sent on 4, 6 or 9 Nov is a line of our 3 Nov files")
    twice = {(r["set"], r["id"], r["type"], r["value"]) for r in listed if r["copies"] == "2"}
    put("twice-in-earlier", fi(len(twice & earlier)))
    s06 = {(r["set"], r["id"], r["type"], r["value"]) for r in sent if r["send"] == "2026-11-06"}
    put("twice-in-06", fi(len(twice & s06)))
    need(twice <= (earlier | s06) and not (twice & earlier & s06),
         "every line listed twice is a line of our 3 Nov files or of the 6 Nov additions (which repeat 4 Nov lines)")
    need(sup == len(extra), "every listed line not in the 4/6/9 Nov sends is superseded by a better line of ours")
    inst_sent = {(r["set"], r["id"]) for r in sent}
    inst_listed = {(r["set"], r["id"]) for r in listed}
    need(inst_sent == inst_listed, "the same instances sent and listed")
    put("instances-ours", fi(len(inst_listed)))
    lt = collections.Counter()
    for (s, i), b in best.items():
        lt["optimal" if "optimal" in b else ("heuristic+lb" if "heuristic" in b and "lower bound" in b else
                                             "heuristic" if "heuristic" in b else "lb")] += 1
    for k, v in lt.items():
        put(f"ourtype-{k.replace('+', '')}", fi(v))
    put("listed-results", fi(sum(len(b) for b in best.values())))
    # reflection of every sent line in the dataset files of 6 and 9 Nov
    st_by = {(r["set"], r["id"]): r for r in state}
    for d in "BC":
        ok = 0
        okinst = collections.defaultdict(lambda: True)
        for r in sent:
            x = st_by[(r["set"], r["id"])]
            lb, ub, v = int(x[f"lb_{TAG[d]}"]), int(x[f"ub_{TAG[d]}"]), int(r["value"])
            good = (lb >= v and ub <= v) if r["type"] == "optimal" else (ub <= v) if r["type"] == "heuristic" else lb >= v
            ok += good
            okinst[(r["set"], r["id"])] &= good
        put(f"reflected-lines-{d}", fi(ok))
        put(f"reflected-inst-{d}", fi(sum(okinst.values())))
        if d == "C":
            need(ok == len(sent), "every sent line reflected in the 9 Nov dataset files")
            need(sum(okinst.values()) == len(inst_listed) == cat["all"]["c-both"] + cat["all"]["c-lb"] +
                 cat["all"]["c-ub"] + cat["all"]["o-both"] + cat["all"]["o-lb"] + cat["all"]["o-ub"],
                 "96,877 = instances credited to reference 4")
    # the site counter as our status files read it (lines, duplicates included)
    put("site-lines-NR", fi(sum(int(r["copies"]) for r in listed)))

    # ---------------------------------------------------------------- schedules, readers, re-proofs
    sc = tsv("schedule_check.tsv")
    for k, key in (("lines", "sched-lines"), ("feasible", "sched-feasible"), ("infeasible", "sched-infeasible"),
                   ("makespan differs", "sched-mkdiff"), ("optimal = published LB = UB", "sched-optreflected"),
                   ("heuristic: since beaten", "sched-beaten")):
        put(key, fi(sum(int(r[k]) for r in sc)))
    need(V["sched-infeasible"] == "0" and V["sched-mkdiff"] == "0", "every listed schedule valid with its value")
    put("sched-opt", fi(sum(int(r["lines"]) for r in sc if r["type"] == "optimal")))
    put("sched-heur", fi(sum(int(r["lines"]) for r in sc if r["type"] == "heuristic")))
    rd = tsv("reader_check.tsv")
    put("reader-inst", fi(sum(int(r["instances"]) for r in rd)))
    put("reader-same", fi(sum(int(r["identical"]) for r in rd)))
    need(V["reader-inst"] == V["reader-same"] == V["instances-ours"], "both readers agree on every instance of ours")
    rp_path = os.path.join(DATA, "reprove.tsv")
    if os.path.exists(rp_path):
        rp = tsv("reprove.tsv")
        put("rp-n", fi(len(rp)))
        put("rp-per", fi(len(rp) // (2 * len(SETS)) if len(rp) >= 2 * len(SETS) else 0))
        put("rp-cpsat-s", f"{float(rp[0]['cpsat_s']):.0f}")
        put("rp-highs-s", f"{float(rp[0]['highs_s']):.0f}")
        for arm in ("cpsat", "highs"):
            c = collections.Counter(r[arm].split(" (")[0] for r in rp)
            put(f"rp-{arm}-inf", fi(c["infeasible"]))
            put(f"rp-{arm}-none", fi(c["no verdict"]))
            put(f"rp-{arm}-contra", fi(sum(v for k, v in c.items() if k.startswith("FEASIBLE"))))
            need(not any(k.startswith("FEASIBLE") or k.startswith("feasible answer") for k in c),
                 f"no re-proof contradicts a claim ({arm})")
        either = sum(1 for r in rp if r["cpsat"].startswith("infeasible") or r["highs"].startswith("infeasible"))
        put("rp-either", fi(either))
        put("rp-cpsat-maxs", f"{max(float(r['cpsat_secs']) for r in rp if r['cpsat'].startswith('infeasible')):.0f}")
        rrows = []
        for s in SETS:
            for kind in ("optimal", "lower bound"):
                g = [r for r in rp if r["set"] == s and r["kind"] == kind]
                if g:
                    rrows.append([f"NR({SHORT[s]})", kind, len(g),
                                  sum(r["cpsat"].startswith("infeasible") for r in g),
                                  sum(r["highs"].startswith("infeasible") for r in g),
                                  sum(r["cpsat"].startswith("FEASIBLE") or r["highs"].startswith("FEASIBLE") for r in g)])
        rfoot = [["All", "", len(rp), sum(r[3] for r in rrows), sum(r[4] for r in rrows), sum(r[5] for r in rrows)]]
        table("reprove.tex", ["Set", "Claim", "Sampled", "CP-SAT", "HiGHS", "Contradicted"], rrows, "llrrrr", rfoot)

    # ---------------------------------------------------------------- runs
    runs = tsv("runs.tsv")
    trows = []
    tr = collections.Counter()
    names = {"U1": "U1: capped at UB", "U2": "U2: re-run of U1 misses", "L1": "L1: destructive, pass 1",
             "L3": "L3: destructive, pass 3", "LA": "LA: last six NR(LA)", "L3b": "L3b: L3 misses",
             "L3c": "L3c: L3 not reached", "K4": "K4: push our bounds", "K5": "K5: pass-3 misses",
             "K6": "K6: ranked (v1)", "K7": "K7: ranked (v1)", "M": "M: model A/B re-runs"}
    for r in runs:
        st = r["stage"]
        tr["runs"] += int(r["runs"])
        tr["cpu"] += float(r["cpu_hours"])
        tr["find"] += int(r["find"])
        tr["closed"] += int(r["closed"])
        tr["ub"] += int(r["ub"])
        tr["lbup"] = tr.get("lbup", 0) + int(r["lb"])
        if st != "K7":
            tr["runs-applied"] += int(r["runs"])
            tr["cpu-applied"] += float(r["cpu_hours"])
        put(f"runs-{st}", fi(r["runs"]))
        put(f"cpu-{st}", f"{float(r['cpu_hours']):,.1f}")
        put(f"find-{st}", fi(r["find"]))
        put(f"findrate-{st}", pc(int(r["find"]) / int(r["runs"]), 0))
        trows.append([names.get(st, st), r["platform"], r["budget"].replace(", destructive", "").replace(
            ", UB cap", "").replace("; one run 3600 s x 8 workers", "; 3600 s$\\times$8"), fi(r["runs"]),
            f"{float(r['cpu_hours']):,.1f}", fi(r["closed"]), fi(r["ub"]), fi(r["lb"]), fi(r["find"]),
            pc(int(r["find"]) / int(r["runs"]), 0)])
    put("u1-share", pc(int(V["find-U1"].replace(",", "")) / (tot["open-A"] - tot["open-C"]), 0))
    put("runs-all", fi(tr["runs"]))
    put("cpu-all", f"{tr['cpu']:,.0f}")
    put("runs-applied", fi(tr["runs-applied"]))
    put("cpu-applied", f"{tr['cpu-applied']:,.0f}")
    put("cpu-kaggle", f"{sum(float(r['cpu_hours']) for r in runs if r['platform'] == 'Kaggle'):,.0f}")
    put("cpu-mac", f"{sum(float(r['cpu_hours']) for r in runs if r['platform'] == 'Mac'):,.0f}")
    table("stages.tex", ["Stage", "Where", "Budget", "Runs", "CPU h", "Closed", "New UB", "LB up", "Finds", "Rate"],
          trows, "lllrrrrrrr", [["All", "", "", fi(tr["runs"]), f"{tr['cpu']:,.1f}", fi(tr["closed"]), fi(tr["ub"]),
                                 fi(tr["lbup"]), fi(tr["find"]), ""]])

    # ---------------------------------------------------------------- A/B
    ab = tsv("ab.tsv")
    resc = tsv("ab_rescored.tsv")
    need(all(r["match"] == "True" for r in resc), "the three re-scored prospective cells match their records")
    put("ab-n", fi(len(ab)))
    wins = collections.Counter(r["verdict"] for r in ab)
    put("ab-model", fi(wins["model"]))
    put("ab-control", fi(wins["control"]))
    put("ab-tie", fi(wins["tie"]))
    short_cell = {
        "NetRes NR_TF pass 3 (set held out)": "NR(TF) held out",
        "NetRes pass 1 to pass 3 (time split)": "pass 1 $\\to$ pass 3 (time split)",
        "NetRes pass 3 remainder (prospective)": "pass 3 remainder",
        "NetRes re-runs: pass-3c misses at 40 s (online, side by side)": "L3c misses, 40 s",
        "NetRes lb7 (prospective; autoloop c1: v1 vs plain, v2 and the generated challenger vs v1)": "K7",
        "NetRes lb6 (prospective, v2 vs plain)": "K6",
        "NetRes lb6 (prospective, v2 vs v1 champion)": "K6",
        "NetRes pass 3b at 40 s (prospective)": "L3b",
        "NetRes pass 3c (prospective)": "L3c",
        "NetRes re-runs: NR_VAR held out": "NR(VAR) held out",
        "NetRes re-runs: pass 3b after the snapshot (prospective)": "L3b after snapshot",
        "NetRes re-runs: pass 3b lines after v1's cell 2 (NR_TF from its 282nd line, NR_AD; time split)":
            "L3b later lines (time split)",
        "NetRes re-runs: lb5 90 s Kaggle re-runs of the 947 pass-3 misses pass 3b never ran (instance set held out)":
            "K5 instances held out",
        "NetRes re-runs: second chances at 40 s, x1 vs v2 head-to-head (online; autoloop c1)": "second chances, 40 s",
        "NetRes settings: pass-3c misses (fresh, top 200 by lane sched-netres-lb v1)": "L3c misses (S1)",
        "NetRes settings: NR_TF pass-3 misses (set held out, top 200 by lane sched-netres-lb v1)": "NR(TF) misses (S2)"}
    lane_name = {"sched-netres-lb": "First-pass order", "sched-netres-rerun": "Re-run order",
                 "sched-netres-lb-params": "Setting choice"}
    arows, last = [], None
    order = {"sched-netres-lb": 0, "sched-netres-rerun": 1, "sched-netres-lb-params": 2}
    vorder = {"v1": 0, "v2": 1, "a1": 2, "x1": 3}
    korder = {"offline": 0, "online": 1, "prospective": 2}
    for r in sorted(ab, key=lambda r: (order[r["lane"]], vorder.get(r["version"], 9), korder[r["kind"]])):
        if last is not None and r["lane"] != last:
            arows.append("MID")
        last = r["lane"]
        rnd = r["random_mean"]
        rnd = f"{float(rnd):,.0f}" if rnd not in ("", "None") else "--"
        ctrl = {"plain": "plain", "v1": "v1", "v2": "v2"}.get(r["control_arm"], r["control_arm"])
        verdict = {"model": "win", "control": "\\textbf{loss}", "tie": "tie"}[r["verdict"]]
        n = r["n"] if r["n"] not in ("", "None") else "--"
        arows.append([lane_name[r["lane"]] + " " + r["version"], short_cell[r["cell"]], r["kind"],
                      fi(n) if n != "--" else n, fi(r["K"]), fi(r["model_finds"]),
                      f"{fi(r['control_finds'])} ({ctrl})", rnd, verdict + ("$^{*}$" if r["source"] != "registry" else "")])
    table("ab.tex", ["Model", "Cell", "Kind", "$n$", "$K$", "Model", "Control (arm)", "Random", "Verdict"], arows,
          "lllrrrrrl")
    by = {(r["lane"], r["version"], r["cell"], r["control_arm"]): r for r in ab}
    for cell, key in (("NetRes pass 3b at 40 s (prospective)", "p3b"), ("NetRes pass 3c (prospective)", "p3c"),
                      ("NetRes pass 3 remainder (prospective)", "rem")):
        r = [x for x in resc if x["cell"] == cell][0]
        put(f"ab-{key}-n", fi(r["n"]))
        put(f"ab-{key}-K", fi(r["K"]))
        put(f"ab-{key}-model", fi(r["model_finds"]))
        put(f"ab-{key}-plain", fi(r["control_finds"]))
        put(f"ab-{key}-random", f"{float(r['random_mean']):,.0f}")
        put(f"ab-{key}-ratio", f"{int(r['model_finds']) / int(r['control_finds']):.2f}")
        put(f"ab-{key}-ratiorandom", f"{int(r['model_finds']) / float(r['random_mean']):.2f}")
    k7 = by[("sched-netres-lb", "v1", "NetRes lb7 (prospective; autoloop c1: v1 vs plain, v2 and the generated challenger vs v1)", "plain")]
    put("ab-k7-auc", f"{float(k7['auc']):.2f}")
    put("ab-k7-base", pc(float(k7["base_rate"]), 0))
    lb_v1 = [r for r in ab if r["lane"] == "sched-netres-lb" and r["version"] == "v1"]
    put("ab-lbv1-cells", fi(len(lb_v1)))
    put("ab-lbv1-wins", fi(sum(r["verdict"] == "model" for r in lb_v1)))
    rr = [r for r in ab if r["lane"] == "sched-netres-rerun"]
    put("ab-rerun-cells", fi(len(rr)))
    put("ab-rerun-losses", fi(sum(r["verdict"] == "control" for r in rr)))
    for r in rr:
        if r["ref_lbv1"] not in ("", "None"):
            tag = {"NetRes re-runs: NR_VAR held out": "var", "NetRes re-runs: pass-3c misses at 40 s (online, side by side)":
                   "online", "NetRes re-runs: pass 3b after the snapshot (prospective)": "p3b"}.get(r["cell"])
            if r["version"] == "v1" and tag:
                put(f"rr-v1-{tag}", fi(r["model_finds"]))
                put(f"rr-v1-{tag}-ref", fi(r["ref_lbv1"]))
            if r["version"] == "v2":
                tag = "A" if "time split" in r["cell"] else "B"
                put(f"rr-v2-{tag}", fi(r["model_finds"]))
                put(f"rr-v2-{tag}-ref", fi(r["ref_lbv1"]))
    pr = [r for r in ab if r["lane"] == "sched-netres-lb-params"]
    put("ab-params-cells", fi(len(pr)))
    put("ab-losses", fi(wins["control"]))
    put("ab-modelctrl", fi(sum(r["control_arm"] != "plain" for r in ab)))
    need(all(int(r["n"]) == int(V["runs-K6"].replace(",", "")) for r in ab if "lb6" in r["cell"]),
         "K6 cells cover the 7,200 K6 runs")
    # record-set descriptions for the prior bounds (from the dataset files' trailer)
    rs = tsv("record_sets.tsv")
    prow = []
    for s in SETS:
        st = {r["ref"]: r for r in rs if r["date"] == DATES["A"] and r["set"] == s}
        need(set(st) == {"1", "2", "3"}, f"{s}: record sets 1-3 on 1 Nov")
        dh = st["1"]["Stop criteria"].replace("1 second(s) and 1 minute", "1 s and 1 min").replace(
            "1 second(s)", "1 s").replace("up to 1 hour", "up to 1 h")
        put(f"dh-stop-{SHORT[s]}", dh)
        prow.append([f"NR({SHORT[s]})", dh, fi(json.loads(summ[(s, DATES['A'])]["ub_refs"]).get("1", 0)),
                     fi(json.loads(summ[(s, DATES['A'])]["lb_refs"]).get("2", 0)),
                     fi(json.loads(summ[(s, DATES['A'])]["ub_refs"]).get("3", 0)), fi(summ[(s, DATES['A'])]["open"])])
    table("priors.tex", ["Set", "DH stop criterion", "UB by DH", "LB by KS", "UB by DV", "Open 1 Nov"], prow, "llrrrr")
    put("dv-stop", [r for r in rs if r["ref"] == "3"][0]["Stop criteria"].replace("500k", "500{,}000"))
    put("dh-hw", [r for r in rs if r["ref"] == "1"][0]["Hardware / software"])
    put("ks-hw", [r for r in rs if r["ref"] == "2"][0]["Hardware / software"])

    # ---------------------------------------------------------------- indicator levels (table and figure data)
    lvl_tot = collections.Counter()
    for r in totals:
        lvl_tot[(r["set"], r["level"])] += int(r["n"])
    lvl = collections.defaultdict(collections.Counter)
    for r in state:
        k = (r["set"], r["level"])
        lvl[k]["openA"] += 1
        lvl[k]["openC"] += int(r["lb_1109"]) < int(r["ub_1109"])
    lrows, fig = [], []
    for s in SETS:
        levels = sorted({k[1] for k in lvl_tot if k[0] == s}, key=lambda x: (x.isalpha(), float(x) if not x.isalpha() else 0, x))
        for i, L in enumerate(levels):
            n, a, c = lvl_tot[(s, L)], lvl[(s, L)]["openA"], lvl[(s, L)]["openC"]
            lrows.append([f"NR({SHORT[s]})" if i == 0 else "", CTRL[s] if i == 0 else "", L, fi(n), fi(a),
                          f"{1000 * a / n:.1f}", fi(c), f"{1000 * c / n:.1f}"])
            fig.append([s, CTRL[s], L, n, a, c])
        lrows.append("MID") if s != SETS[-1] else None
    sp_open = [float(L) for (s, L), k in lvl.items() if s == "NR_SP" and k["openC"] > 0]
    need(max(sp_open) <= 0.4, "every open NR(SP) instance on 9 Nov has SP <= 0.4")
    for s in ("NR_AD", "NR_TF"):
        seq = [lvl[(s, L)]["openC"] for L in sorted({L for (ss, L) in lvl_tot if ss == s}, key=float)]
        need(all(a <= b for a, b in zip(seq, seq[1:])), f"{s}: open instances rise with the factor")
    for (s, L), k in lvl.items():
        put(f"lvlA-{SHORT[s]}-{L}", fi(k["openA"]))
        put(f"lvlC-{SHORT[s]}-{L}", fi(k["openC"]))
    table("levels.tex", ["Set", "Factor", "Level", "Instances", "Open 1 Nov", "\\textperthousand", "Open 9 Nov",
                         "\\textperthousand"], lrows, "lllrrrrr")
    with open(os.path.join(DATA, "fig_levels.tsv"), "w") as f:
        f.write("set\tfactor\tlevel\tn\topen_1101\topen_1109\n")
        for r in fig:
            f.write("\t".join(map(str, r)) + "\n")
    # extremes quoted in the text
    shares = {(r[0], r[2]): r[5] / r[3] for r in fig}
    hardest = max(((s, L) for (s, L) in shares if s != "NR_LA"), key=lambda k: shares[k])
    put("hardest-cell", f"NR({SHORT[hardest[0]]}) at {CTRL[hardest[0]]} = {hardest[1]}")
    put("hardest-share", pc(shares[hardest], 1))
    rsd = collections.defaultdict(collections.Counter)
    for r in totals:
        rsd[r["rs_decile"]]["n"] += int(r["n"])
    for r in state:
        rsd[r["rs_decile"]]["A"] += 1
        rsd[r["rs_decile"]]["C"] += int(r["lb_1109"]) < int(r["ub_1109"])
    with open(os.path.join(DATA, "fig_rs.tsv"), "w") as f:
        f.write("rs_decile\tn\topen_1101\topen_1109\n")
        for k in sorted(rsd, key=int):
            f.write(f"{k}\t{rsd[k]['n']}\t{rsd[k]['A']}\t{rsd[k]['C']}\n")
    low = rsd["0"]
    put("rs0-n", fi(low["n"]))
    put("rs0-openC", fi(low["C"]))
    put("rs0-shareofopen", pc(low["C"] / tot["open-C"]))
    with open(os.path.join(DATA, "fig_gaps.tsv"), "w") as f:
        f.write("gap\topen_1101\topen_1109\n")
        for b in ["1", "2", "3", "4-5", "6-10", "gt10"]:
            f.write(f"{b}\t{gaps['A'][b]}\t{gaps['C'][b]}\n")

    # ---------------------------------------------------------------- the last six NR(LA) instances
    la = tsv("la_last.tsv")
    st_la = {r["id"]: r for r in state if r["set"] == "NR_LA"}
    rla = {r["id"]: r for r in tsv("reprove_la.tsv")} if os.path.exists(os.path.join(DATA, "reprove_la.tsv")) else {}
    rla2 = {r["id"]: r for r in tsv("reprove_la2.tsv")} if os.path.exists(os.path.join(DATA, "reprove_la2.tsv")) else {}
    lrows, seen = [], set()
    for r in la:
        x = st_la[r["id"]]
        final = [y for y in la if y["id"] == r["id"]][-1]
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        runs_txt = " + ".join(f"{float(y['secs']):,.0f} s" + (f" ($\\times${y['workers']})" if y["workers"] != "1" else "")
                              for y in la if y["id"] == r["id"])
        rp, rp2 = rla.get(r["id"]), rla2.get(r["id"])
        rp_txt = "--" if rp is None else (f"{float(rp['secs']):,.0f} s" if rp["verdict"] == "infeasible"
                                          else "none in " + f"{float(rp['seconds']):,.0f} s")
        if rp2 is not None:
            w2 = f"$\\times${rp2['workers']}" if rp2["workers"] != "1" else ""
            rp_txt += "; " + (f"{float(rp2['secs']):,.0f} s ({w2})" if rp2["verdict"] == "infeasible"
                              else f"none in {float(rp2['seconds']):,.0f} s ({w2})")
        lrows.append([r["id"], x["lb_1101"], x["ub_1101"], final["bound"], runs_txt, rp_txt])
        need(int(final["bound"]) == int(x["lb_1109"]) == int(x["ub_1109"]), f"NR_LA {r['id']}: closed at our bound")
    table("la.tex", ["Instance", "LB 1 Nov", "UB", "Our LB", "Our runs", "Re-proof"], lrows, "rrrrll")
    big = [r for r in la if r["workers"] != "1"][0]
    put("la-big-cap", str(int(big["bound"]) - 1))
    rbs = tsv("runs_by_set.tsv")
    put("la-closure", fi(sum(int(r["closed"]) for r in rbs if r["set"] == "NR_LA" and r["stage"] in ("U1", "U2"))))
    need(int(V["la-closure"].replace(",", "")) + len(seen) == int(V["open-LA-A"].replace(",", "")),
         "NR(LA): closure runs plus the last six = the open instances of 1 Nov")
    put("la-big-id", big["id"])
    put("la-big-secs", f"{float(big['secs']):,.0f}")
    put("la-big-min", f"{float(big['secs']) / 60:.0f}")
    if rla:
        put("rpla-n", fi(len(rla)))
        put("rpla-inf", fi(sum(r["verdict"] == "infeasible" for r in rla.values())))
        put("rpla-inf-all", fi(sum(r["verdict"] == "infeasible" or rla2.get(i, {}).get("verdict") == "infeasible"
                                   for i, r in rla.items())))
        need(not any(r["verdict"].startswith("FEASIBLE") for r in rla2.values()), "no NR(LA) bound contradicted (2)")
        k_all = int(V["rpla-inf-all"].replace(",", ""))
        put("rpla-inf-all-words", "all six" if k_all == len(rla) == 6 else f"{k_all} of the six")
        if rla2:
            put("rpla2-s", f"{float(list(rla2.values())[0]['seconds']):,.0f}")
            put("rpla2-w", list(rla2.values())[0]["workers"])
        put("rpla-s", f"{float(list(rla.values())[0]['seconds']):,.0f}")
        put("rpla-maxs", f"{max(float(r['secs']) for r in rla.values() if r['verdict'] == 'infeasible'):,.0f}"
            if any(r["verdict"] == "infeasible" for r in rla.values()) else "--")
        need(not any(r["verdict"].startswith("FEASIBLE") for r in rla.values()), "no NR(LA) bound contradicted")

    bc = tsv("bks_coverage.tsv")
    put("bks-open", fi(sum(int(r["open_with_bks"]) for r in bc)))
    put("bks-pct", pc(sum(int(r["open_with_bks"]) for r in bc) / tot["open-A"]))
    need(sum(int(r["open_1101"]) for r in bc) == tot["open-A"], "U1 ran every instance open on 1 Nov")

    # ---------------------------------------------------------------- hint ablation (3 s closure runs)
    if os.path.exists(os.path.join(DATA, "ablation_hint.tsv")):
        hb = tsv("ablation_hint.tsv")
        for arm in ("hint", "none"):
            dd = [r for r in hb if r["arm"] == arm]
            put(f"abl-{arm}-n", fi(len(dd)))
            put(f"abl-{arm}-closed", fi(sum(r["status"] == "OPTIMAL" for r in dd)))
            put(f"abl-{arm}-newub", fi(sum(r["value"] not in ("None", "") and int(r["value"]) < int(r["ub_1101"])
                                           for r in dd)))
            put(f"abl-{arm}-nosched", fi(sum(r["value"] in ("None", "") for r in dd)))
            put(f"abl-{arm}-lbup", fi(sum(r["bound"] not in ("None", "") and int(r["bound"]) > int(r["lb_1101"])
                                          and r["status"] != "OPTIMAL" for r in dd)))
        both = {}
        for r in hb:
            both.setdefault((r["set"], r["id"]), {})[r["arm"]] = r["status"] == "OPTIMAL"
        put("abl-only-hint", fi(sum(v.get("hint") and not v.get("none") for v in both.values())))
        put("abl-only-none", fi(sum(v.get("none") and not v.get("hint") for v in both.values())))
        put("abl-secs", f"{round(max(float(r['secs']) for r in hb)):.0f}")

    # ---------------------------------------------------------------- one-feature rules (registry notes)
    import re
    for r in ab:
        note = r.get("rules_note") or ""
        if not note:
            continue
        nums = [int(x.replace(",", "")) for x in re.findall(r" (\d[\d,]*)(?:,| \(|$)", note)]
        key = "tf" if "NR_TF" in r["cell"] else "time"
        put(f"rule-{key}-best", fi(max(nums)))
        put(f"rule-{key}-model", fi(r["model_finds"]))
        put(f"rule-{key}-plain", fi(r["control_finds"]))

    # ---------------------------------------------------------------- highlights (Elsevier: 3-5 bullets, <= 85 chars)
    hl = [(lambda r: f"Learned run order: {r['A']['arms']['v2']['x_random']:.1f}-"
                     f"{r['B']['arms']['v2']['x_random']:.1f}x random choice and {r['A']['arms']['v2']['x_rule']:.2f}x a gap rule in new bounds")(json.load(open(os.path.join(PAPER, "data", "rerun_policy.json")))),
          f"CP-SAT closed {V['closed-all']} of {V['open-all-A']} open NetRes RCPSP instances",
          f"NR(LA) is the first NetRes set with all {V['inst-LA']} instances closed",
          "Every listed schedule re-checked; sampled lower bounds re-proved separately",
          f"Instances with resource strength below 0.1 hold {V['rs0-shareofopen'].replace(chr(92), '')} of the open ones"]
    for h in hl:
        need(len(h) <= 85, f"highlight within 85 characters: {h} ({len(h)})")
    open(os.path.join(PAPER, "highlights.txt"), "w").write("\n".join(hl) + "\n")
    with open(os.path.join(PAPER, "highlights.tex"), "w") as f:
        f.write("% written by scripts/make_numbers.py\n\\begin{highlights}\n")
        for h in hl:
            f.write("\\item " + h.replace("%", "\\%") + "\n")
        f.write("\\end{highlights}\n")

    # ---------------------------------------------------------------- write
    with open(os.path.join(PAPER, "numbers.tex"), "w") as f:
        f.write("% written by scripts/make_numbers.py from data/; do not edit\n")
        for k in sorted(V):
            f.write(f"\\qvset{{{k}}}{{{V[k]}}}\n")
    json.dump({"values": V, "checks": [{"ok": ok, "check": w} for ok, w in CHECKS]},
              open(os.path.join(PAPER, "numbers.json"), "w"), indent=1, sort_keys=True)
    print(f"{len(V)} values, {len(CHECKS)} checks passed")


if __name__ == "__main__":
    main()
