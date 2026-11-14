"""Resource-constrained project scheduling (RCPSP) by OR-Tools CP-SAT, for the benchmark sets of Ghent's Solutions
Update site (http://solutionsupdate.ugent.be). Reads a Patterson-format .rcp instance (n activities and r renewable
resources; capacities; per activity: duration, r demands, successor count, successors, 1-based, activity 1 the dummy
start and n the dummy end) or a PSPLIB single-mode .sm file (the same data in labelled sections; jobs include the
supersource and the supersink), starts from the best known start times when given (a hint, so the first solution is
at least as good), minimises the makespan and writes the start times in the site's order (activity 1 first).

Lower bound: every solve also reports a proven lower bound on the optimal makespan (lower_bound()). The model is the
instance plus one extra constraint, makespan <= cap (cap = the best known value, or none). CP-SAT's best objective
bound b means no schedule of that capped model ends before b, so no schedule at all ends before min(b, cap + 1);
INFEASIBLE means none ends within the cap, so the optimum is at least cap + 1 (a cap of best known - 1 that comes back
INFEASIBLE proves the best known value optimal). The bound is ceil(b) (less a 1e-6 guard against float noise), never
above cap + 1 and never above a schedule found in the same run. Hints and search parameters (LB_PARAMS) do not
change the model, so they do not change what the bound means. destructive() turns this into a lower-bound pass: caps
from the published LB upward, each refuted cap T proving the optimum >= T + 1 (the lanes' --lb mode).
  .venv/bin/python -I engine/sched/rcpsp_cpsat.py INSTANCE [--hint "s1;s2;..."] [--ub BEST] [--seconds S]
                                                  [--workers W] [--out FILE] [--lb] [--params TEXT]
Prints one line: instance makespan status seconds bound (status OPTIMAL, FEASIBLE, INFEASIBLE or UNKNOWN)."""
import argparse
import math
import os
import re
import time

from ortools.sat.python import cp_model

# Search settings for lower-bound passes (one CP-SAT worker each): CP-SAT's stronger cumulative propagators, off by
# default (with them the 30 s bound on open RG300/J120/DC2 instances rose from about half the published LB to within
# a few units of it). Only the search and propagation change, never the model.
LB_PARAMS = ("use_overload_checker_in_cumulative: true use_timetable_edge_finding_in_cumulative: true "
             "use_hard_precedences_in_cumulative: true exploit_all_precedences: true")


def read_rcp(path):
    nums = [int(x) for x in open(path).read().split()]
    n, r = nums[0], nums[1]
    cap, pos = nums[2:2 + r], 2 + r
    dur, dem, succ = [], [], []
    for _ in range(n):
        dur.append(nums[pos]); dem.append(nums[pos + 1:pos + 1 + r])
        k = nums[pos + 1 + r]
        succ.append([s - 1 for s in nums[pos + 2 + r:pos + 2 + r + k]])
        pos += 2 + r + k
    return n, r, cap, dur, dem, succ


def read_sm(path):
    """PSPLIB single-mode .sm file -> (n, r, capacities, durations, demands, successors from 0), as read_rcp."""
    txt = open(path, encoding="latin-1").read().replace("\r", "")
    lines = txt.split("\n")

    def count(pattern):
        m = re.search(pattern + r"\s*:\s*(\d+)", txt)
        if not m:
            raise ValueError("%s: no line matching %r" % (path, pattern))
        return int(m.group(1))

    n = count(r"jobs \(incl\. supersource/sink\s*\)")
    r = count(r"-\s*renewable")
    if count(r"-\s*nonrenewable") or count(r"-\s*doubly constrained"):
        raise ValueError("%s: nonrenewable or doubly constrained resources (not a single-mode RCPSP)" % path)

    def section(title):
        """Integers of the lines after the line starting with title, up to the next line of asterisks; column
        headers and dashed lines (first token not an integer) are skipped."""
        k = next((i for i, l in enumerate(lines) if l.strip().startswith(title)), None)
        if k is None:
            raise ValueError("%s: no %s section" % (path, title))
        out = []
        for line in lines[k + 1:]:
            if line.startswith("*"):
                break
            tok = line.split()
            if tok and tok[0].isdigit():
                out.extend(int(x) for x in tok)
        return out

    prec, p, succ = section("PRECEDENCE RELATIONS:"), 0, []
    for j in range(n):
        if prec[p] != j + 1 or prec[p + 1] != 1:
            raise ValueError("%s: precedence line of job %d expected (one mode), found %r"
                             % (path, j + 1, prec[p:p + 3]))
        k = prec[p + 2]
        succ.append([s - 1 for s in prec[p + 3:p + 3 + k]])
        p += 3 + k
    if p != len(prec):
        raise ValueError("%s: %d numbers left in the precedence section" % (path, len(prec) - p))
    req, p, dur, dem = section("REQUESTS/DURATIONS:"), 0, [], []
    for j in range(n):
        if req[p] != j + 1 or req[p + 1] != 1:
            raise ValueError("%s: request line of job %d expected (mode 1), found %r" % (path, j + 1, req[p:p + 2]))
        dur.append(req[p + 2])
        dem.append(req[p + 3:p + 3 + r])
        p += 3 + r
    if p != len(req):
        raise ValueError("%s: %d numbers left in the requests section" % (path, len(req) - p))
    cap = section("RESOURCEAVAILABILITIES:")
    if len(cap) != r:
        raise ValueError("%s: %d resource availabilities for %d resources" % (path, len(cap), r))
    return n, r, cap, dur, dem, succ


def read_instance(path):
    """.sm (PSPLIB) or .rcp (Patterson), told apart by the content."""
    with open(path, encoding="latin-1") as f:
        head = f.read(8192)
    return read_sm(path) if "PRECEDENCE RELATIONS" in head or head.lstrip().startswith("*") else read_rcp(path)


def bound_ok(params):
    """False for extra CP-SAT parameters that change the model the bound refers to (fixing variables to the hint)."""
    return "fix_variables_to_their_hinted_value" not in (params or "")


def lower_bound(solver, status, cap=None):
    """A proven lower bound on the optimal makespan from one run on a model whose only extra constraint is
    makespan <= cap (cap None: no cap); None when the run proves nothing."""
    if status == cp_model.INFEASIBLE:
        return None if cap is None else cap + 1
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE, cp_model.UNKNOWN):
        return None
    b = solver.BestObjectiveBound()
    if b is None or not math.isfinite(b):
        return None
    lb = math.ceil(b - 1e-6)
    if cap is not None:
        lb = min(lb, cap + 1)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        lb = min(lb, int(round(solver.ObjectiveValue())))
    return int(lb)


def destructive(run, first, ub, seconds):
    """Lower bound by destructive improvement (Klein and Scholl 1999): test caps T from first (normally the published
    LB) upward, below ub, while time remains. run(T, seconds) solves the instance with the one extra constraint
    makespan <= T and returns a dict with status, starts, value (the makespan of its schedule, None without one) and
    bound (lower_bound() of that run). INFEASIBLE at T proves that no schedule ends by T, so the optimum is at least
    T + 1, whatever first was (first only picks the caps tested); an UNKNOWN run still gives its own bound
    min(ceil(b), T + 1). Steps: +1, doubled after each refutation that took under a tenth of the time left (a weak
    published LB is passed quickly); a doubled step gets a quarter of the time left, and when it proves nothing the
    ascent goes back to the last refuted cap + 1 with step 1; a step-1 run that proves nothing ends it. A schedule
    found (value v < ub) becomes the incumbent and the caps between the last refuted one and v are still tested, so
    a refuted v - 1 makes it optimal (status OPTIMAL); a bound above it would mean a wrong refutation: the bound is
    dropped and the status is BOUND_CONFLICT. Returns the incumbent's run dict (else the last run's) with bound = the
    best bound of all runs, secs = the total time, tests = caps tried."""
    t0, best, last, found, tests = time.time(), None, None, None, 0
    refuted, step, limit = first - 1, 1, ub
    while True:
        cap = refuted + step
        if limit is not None and cap >= limit:
            if step == 1:
                break                     # every cap below the limit refuted: the limit is optimal
            step = 1
            continue
        left = seconds - (time.time() - t0)
        if left < 0.2:
            break
        t1 = time.time()
        last, tests = run(cap, left if step == 1 else left / 4), tests + 1
        if last["bound"] is not None:
            best = last["bound"] if best is None else max(best, last["bound"])
        if last["status"] == "INFEASIBLE":
            refuted = cap
            step = step * 2 if time.time() - t1 < left / 10 else 1
        elif last.get("starts") is not None:
            found = last                  # a schedule ending by cap: the caps below its value stay to be tested
            if last["status"] == "OPTIMAL" or last.get("value") is None:
                break
            limit, step = last["value"], 1
        elif step > 1:
            step = 1                      # the long step proved nothing: back to the last refuted cap + 1
        else:
            break
    out = dict(found or last or dict(starts=None, status="UNKNOWN", bound=None, value=None))
    value = out.get("value") if found else None
    if value is not None and best is not None:
        if best > value:
            best, out["status"] = None, "BOUND_CONFLICT"
        elif best == value:
            out["status"] = "OPTIMAL"
    out.update(bound=best, secs=time.time() - t0, tests=tests)
    return out


def solve_full(path, hint=None, seconds=60.0, workers=1, ub=None, params=None, lb=False):
    """One CP-SAT run. Returns dict(starts (None without a schedule), status, secs, bound, cap)."""
    n, r, cap, dur, dem, succ = read_instance(path)
    horizon = sum(dur)
    m = cp_model.CpModel()
    start = [m.NewIntVar(0, horizon, f"s{i}") for i in range(n)]
    iv = [m.NewFixedSizeIntervalVar(start[i], dur[i], f"i{i}") for i in range(n)]
    for i in range(n):
        for j in succ[i]:
            m.Add(start[j] >= start[i] + dur[i])
    for k in range(r):
        items = [(iv[i], dem[i][k]) for i in range(n) if dem[i][k] > 0 and dur[i] > 0]
        if items:
            m.AddCumulative([a for a, _ in items], [d for _, d in items], cap[k])
    makespan = start[n - 1]
    for i in range(n - 1):
        if not succ[i]:  # no successor (none in well-formed files): the dummy end still waits for it
            m.Add(makespan >= start[i] + dur[i])
    if hint and len(hint) == n:
        for i, s in enumerate(hint):
            m.AddHint(start[i], s)
    if ub is not None:
        m.Add(makespan <= ub)  # never worse than the best known value: the only extra constraint
    m.Minimize(makespan)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = workers
    if lb and LB_PARAMS:
        solver.parameters.merge_text_format(LB_PARAMS)
    if params:
        solver.parameters.merge_text_format(params)
    t0 = time.time()
    status = solver.Solve(m)
    secs = time.time() - t0
    starts = [solver.Value(s) for s in start] if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    bound = lower_bound(solver, status, ub) if bound_ok(params) else None
    return dict(starts=starts, status=solver.StatusName(status), secs=secs, bound=bound, cap=ub,
                value=starts[-1] if starts else None)


def solve(path, hint=None, seconds=60.0, workers=1, ub=None):
    """The original interface: (start times or None, status name, seconds)."""
    res = solve_full(path, hint, seconds, workers, ub)
    return res["starts"], res["status"], res["secs"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instance")
    ap.add_argument("--hint", default=None)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default=None)
    ap.add_argument("--ub", type=int, default=None)
    ap.add_argument("--lb", action="store_true", help="search settings for lower bounds (LB_PARAMS)")
    ap.add_argument("--params", default=None, help="extra CP-SAT parameters (text format)")
    a = ap.parse_args()
    hint = [int(x) for x in a.hint.strip(";").split(";")] if a.hint else None
    res = solve_full(a.instance, hint, a.seconds, a.workers, a.ub, a.params, a.lb)
    name = os.path.basename(a.instance)
    bound = "-" if res["bound"] is None else res["bound"]
    if res["starts"] is None:
        print(name, "-", res["status"], f"{res['secs']:.1f}", bound, flush=True)
        return
    if a.out:
        open(a.out, "w").write(";".join(map(str, res["starts"])) + "\n")
    print(name, res["starts"][-1], res["status"], f"{res['secs']:.1f}", bound, flush=True)


if __name__ == "__main__":
    main()
