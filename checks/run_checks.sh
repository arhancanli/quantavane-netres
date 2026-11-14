#!/bin/sh
# Quick checks of this repository, a few seconds in all. Run from the repository root:
#   sh checks/run_checks.sh          (PYTHON=/path/to/python3 to choose the interpreter)
# Writes checks/results.txt. Exit 0 only if every step gave the expected result.
#  1. The frozen prediction files of the re-run lane against the SHA-256 digests in their predict_info.json, and the
#     files whose digests the registry extract (data/registry_netres.json) records.
#  2. scripts/make_numbers.py: every number and table it writes from data/; the outputs (numbers.tex, numbers.json,
#     highlights.tex, highlights.txt, tables/) are hashed and then removed.
#  3. scripts/ab_pvalues.py and scripts/rc_rs.py must write data/ab_pvalues.tsv and data/rc_rs.tsv unchanged.
#  4. If OR-Tools is installed: the solver code imports from this layout (no instance is solved).
set -u
PY=${PYTHON:-python3}
bad=0
{
echo "run_checks.sh $(date -u +%Y-%m-%dT%H:%M:%SZ); $($PY --version 2>&1)"

echo "=== 1. frozen predictions and registered files"
$PY -I - <<'PY' || bad=1
import hashlib, json, sys
ok = True
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
for d in ("runs/sched/model_rerun_v2", "runs/sched/model_rerun_x1"):
    info = json.load(open(d + "/predict_info.json"))
    for cell in ("cell_A", "cell_B"):
        f = info[cell]["file"]; same = sha(f) == info[cell]["sha256"]; ok &= same
        print("%s %s rows %d: %s" % (f, info[cell]["sha256"][:16], info[cell]["rows"], "matches predict_info.json" if same else "DIFFERS"))
reg = open("data/registry_netres.json").read()
for f in ("engine/sched/rcpsp_cpsat.py", "engine/models/netres_jobs.py", "runs/sched/netres.py",
          "runs/sched/model_v2/pred_lb6_20261108T172526Z.tsv"):
    h = sha(f); same = h in reg; ok &= same
    print("%s %s: %s" % (f, h[:16], "digest recorded in data/registry_netres.json" if same else "NOT in data/registry_netres.json"))
sys.exit(0 if ok else 1)
PY

echo "=== 2. the paper's numbers from data/"
$PY -I scripts/make_numbers.py || bad=1
for f in numbers.tex numbers.json highlights.tex highlights.txt; do
  [ -f $f ] && echo "$(shasum -a 256 $f | cut -d' ' -f1)  $f" || { bad=1; echo "MISSING $f"; }
done
echo "tables: $(ls tables 2>/dev/null | wc -l | tr -d ' ') files, sha256 of their concatenation in name order: $(cat tables/*.tex 2>/dev/null | shasum -a 256 | cut -d' ' -f1)"
rm -rf numbers.tex numbers.json highlights.tex highlights.txt tables

echo "=== 3. data-only scripts"
for s in ab_pvalues rc_rs; do
  before=$(shasum -a 256 data/$s.tsv | cut -d' ' -f1)
  $PY -I scripts/$s.py > /dev/null || bad=1
  after=$(shasum -a 256 data/$s.tsv | cut -d' ' -f1)
  [ "$before" = "$after" ] && echo "scripts/$s.py: data/$s.tsv unchanged ($after)" || { bad=1; echo "scripts/$s.py: data/$s.tsv CHANGED"; }
done

echo "=== 4. solver code"
if $PY -I -c "import ortools" 2>/dev/null; then
  $PY -I -B -c "
import sys
sys.path.insert(0, 'runs/sched'); import netres, netres_lb
sys.path.insert(0, 'engine/models'); import netres_jobs
import ortools, rcpsp_cpsat
print('imports ok: netres, netres_lb, netres_jobs, rcpsp_cpsat; OR-Tools', ortools.__version__)" || bad=1
else
  echo "OR-Tools is not installed for $PY: import check skipped"
fi

[ $bad = 0 ] && echo "ALL PASS" || echo "SOMETHING FAILED"
} > checks/results.txt 2>&1
tail -1 checks/results.txt
[ $bad = 0 ]
