"""NetRes instances rebuilt from Ghent's original files, written for the paper's checks (separately from the search
code in runs/sched/netres.py and from independent/rcpsp_check_netres.py).

An instance of a NetRes set is a network of the MT30 sets (Patterson .rcp file: activities, durations, successors;
its resource columns are placeholders) with one resource profile of a ResSet file (capacities, then one demand line per
real activity), as the dataset row's Ref1, Ref2 and Ref3 say. Activity 0 is the dummy start, n-1 the dummy end.
INST is the unzipped NetRes archive of the site (folders MT30/<subset>/EV<k>.rcp and ResSet/ResSet<k>.txt)."""
import os
import re

INST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", "sched", "NR_SP", "inst")
_net, _prof = {}, {}


def network(folder, k):
    """(durations, successor lists) of MT30/<folder>/EV<k>.rcp, activities numbered from 0."""
    key = (folder, k)
    if key not in _net:
        tok = [int(x) for x in open(os.path.join(INST, "MT30", folder, f"EV{k}.rcp")).read().split()]
        n, r = tok[0], tok[1]
        p = 2 + r
        dur, succ = [], []
        for _ in range(n):
            dur.append(tok[p])
            m = tok[p + 1 + r]
            succ.append([x - 1 for x in tok[p + 2 + r:p + 2 + r + m]])
            p += 2 + r + m
        if p != len(tok):
            raise ValueError(f"{folder}/EV{k}.rcp: {len(tok) - p} numbers left over")
        _net[key] = (dur, succ)
    return _net[key]


def profile(resset, number):
    """(capacities, demands of the real activities) of profile `number` of ResSet/<resset>."""
    if resset not in _prof:
        text = open(os.path.join(INST, "ResSet", resset), encoding="latin-1").read()
        parts = re.split(r"File number (\d+)", text)
        out = {}
        for i in range(1, len(parts), 2):
            cap, dem, mode = None, [], None
            for line in parts[i + 1].splitlines():
                s = line.strip()
                if s.startswith("Resource availability"):
                    mode = "cap"
                elif s.startswith("Resource demand"):
                    mode = "dem"
                elif s and all(t.isdigit() for t in s.split()):
                    if mode == "cap" and cap is None:
                        cap = [int(t) for t in s.split()]
                    elif mode == "dem":
                        dem.append([int(t) for t in s.split()])
            out[int(parts[i])] = (cap, dem)
        _prof[resset] = out
    return _prof[resset][number]


def instance(folder, k, resset, number):
    """(durations, successors, capacities, demands per activity incl. the two dummies with zero demand)."""
    dur, succ = network(folder, int(k))
    cap, dem30 = profile(resset, int(number))
    if len(dem30) != len(dur) - 2 or any(len(d) != len(cap) for d in dem30):
        raise ValueError(f"{folder}/EV{k} with {resset} #{number}: {len(dem30)} demand lines for {len(dur)} activities")
    zero = [0] * len(cap)
    return dur, succ, cap, [zero] + dem30 + [zero]


def check(starts, dur, succ, cap, dem):
    """None when the start times form a feasible schedule (every precedence, every resource at every time unit),
    else the first violation found."""
    n = len(dur)
    if len(starts) != n:
        return f"{len(starts)} start times for {n} activities"
    if min(starts) < 0:
        return "negative start"
    for a in range(n):
        for b in succ[a]:
            if starts[b] < starts[a] + dur[a]:
                return f"precedence {a + 1}->{b + 1}"
    end = max(starts[a] + dur[a] for a in range(n))
    for k in range(len(cap)):
        use = [0] * (end + 1)
        for a in range(n):
            if dem[a][k]:
                for t in range(starts[a], starts[a] + dur[a]):
                    use[t] += dem[a][k]
        if use and max(use) > cap[k]:
            return f"resource {k + 1} over capacity at t = {use.index(max(use))}"
    return None
