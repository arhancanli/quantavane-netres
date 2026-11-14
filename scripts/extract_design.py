"""The NetRes design as Ghent's original instance files state it: per ResSet file the number of resource profiles, of
resources, and the nominal RU, RC and RC-interval levels of its profile headers. Writes data/design.json (the networks
per set follow from data/totals.tsv: instances / profiles).
  nice -n 10 python3 -I scripts/extract_design.py"""
import collections
import hashlib
import json
import os
import re

INST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", "sched", "NR_SP", "inst")
PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    out = {}
    for fn in sorted(os.listdir(os.path.join(INST, "ResSet"))):
        if not re.fullmatch(r"ResSet\d+\.txt", fn):
            continue
        raw = open(os.path.join(INST, "ResSet", fn), "rb").read()
        text = raw.decode("latin-1")
        parts = re.split(r"File number (\d+)", text)
        ru, rc, iv, nres = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
        for k in range(1, len(parts), 2):
            b = parts[k + 1]
            nres[re.search(r"Number of Resources: (\d+)", b).group(1)] += 1
            ru[re.search(r"Resource Use \(RU\): (\d+)", b).group(1)] += 1
            rc[re.search(r"Constrainedness \(RC\): ([\d.]+)", b).group(1)] += 1
            m = re.search(r"interval: \[([\d.]+); ([\d.]+)\]", b)
            iv[f"{m.group(1)}-{m.group(2)}" if m else "fixed"] += 1
        out[fn] = {"profiles": (len(parts) - 1) // 2, "resources": dict(nres), "RU": dict(sorted(ru.items())),
                   "RC": dict(sorted(rc.items())), "RC interval": dict(sorted(iv.items())),
                   "sha256": hashlib.sha256(raw).hexdigest()}
    nets = {}
    for d in sorted(os.listdir(os.path.join(INST, "MT30"))):
        p = os.path.join(INST, "MT30", d)
        if os.path.isdir(p) and d.startswith("Set "):
            nets[d] = len([f for f in os.listdir(p) if f.endswith(".rcp")])
    out["MT30 subsets"] = nets
    json.dump(out, open(os.path.join(PAPER, "data", "design.json"), "w"), indent=1)
    print(json.dumps(out, indent=1)[:1500])


if __name__ == "__main__":
    main()
