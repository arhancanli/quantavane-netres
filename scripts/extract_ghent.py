"""Extract what the paper needs from the seven NetRes dataset files of Ghent University's Solutions Update site
(http://solutionsupdate.ugent.be) at three dates, so the tables and figures regenerate from small files:

  2026-11-01  runs/sched/NR_<set>/NR_<set>.20261101.csv  (downloaded 1 Nov, before any result of
              ours was applied; the check below confirms that no row credits reference 4, ours)
  2026-11-06  runs/sched/NR_<set>/NR_<set>.csv           (downloaded 7 Nov 00:20 +04, the site's
              files of 6 Nov)
  2026-11-09  http://solutionsupdate.ugent.be/sites/default/files/datasets/NR_<set>.csv (Last-Modified 9 Nov 2026,
              about 12:00 GMT; streamed, never stored whole)

Each dataset row: ID;Ref1 (network file);Ref2 (ResSet file);Ref3 (profile);LB value;LB ref;LB time;UB value;UB ref;
UB time;OPT value;OPT ref;OPT time;CPM;Sum PT;# Act;CNC;OS;SP/I2;AD/I3;LA/I4;I5;TF/I6;# RR;RF/RR;RU/RR;RS/RR;RC/RR;...
"LB ref"/"UB ref" name the record set that holds the bound (1 Demeulemeester-Herroelen, 2 Klein-Scholl, 3
Debels-Vanhoucke, 4 Quantavane, or CPM, Capacity LB, Sum PT).

Writes (data/):
  sources.tsv     every file read: date, set, source, bytes, sha256, rows, last-modified/mtime
  summary.tsv     per date and set: rows, closed (LB = UB), open, sum LB, sum UB, open units, LB/UB credits by ref
  totals.tsv      per set and design cell (controlled level, nominal RC, nominal RU, RC spread, RS decile): instances
  state.csv.gz    one row per instance that is open at some date, changes between dates or credits reference 4:
                  design cell, measured indicators, and LB, LB ref, UB, UB ref at each date
  checks.json     identity of the instance columns across the three dates, parse anomalies
A 2026-11-09 source whose sha256 differs from the one in sources.tsv stops the run (the site has moved on), unless
--refresh is given; the 1 and 6 Nov copies must match too.
  nice -n 10 python3 -I scripts/extract_ghent.py [--refresh]"""
import array
import collections
import csv
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repository root
SCHED = os.path.join(ROOT, "runs", "sched")
RESSET = os.path.join(SCHED, "NR_SP", "inst", "ResSet")
PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
SETS = ["NR_SP", "NR_AD", "NR_LA", "NR_TF", "NR_RC", "NR_RU", "NR_VAR"]
DATES = ["2026-11-01", "2026-11-06", "2026-11-09"]
URL = "http://solutionsupdate.ugent.be/sites/default/files/datasets/{}.csv"
CTRL = {"NR_SP": "SP", "NR_AD": "AD", "NR_LA": "LA", "NR_TF": "TF", "NR_RC": "RC", "NR_RU": "RU", "NR_VAR": "RCspread"}
# measured indicator columns of a dataset row (0-based)
IND = {"CPM": 13, "SumPT": 14, "CNC": 16, "OS": 17, "SP": 18, "AD": 19, "LA": 20, "I5": 21, "TF": 22, "nRR": 23,
       "RF": 24, "RU": 25, "RS": 26, "RC": 27}


def source(date, s):
    if date == "2026-11-01":
        return os.path.join(SCHED, s, s + ".20261101.csv")
    if date == "2026-11-06":
        return os.path.join(SCHED, s, s + ".csv")
    return URL.format(s)


def lines_of(src, meta):
    """Yield the raw lines (bytes) of a local file or a URL, filling meta with bytes, sha256 and headers."""
    h, n = hashlib.sha256(), 0
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=900)
        meta["last_modified"] = resp.headers.get("Last-Modified", "")
        meta["content_length"] = resp.headers.get("Content-Length", "")
        stream = resp
    else:
        meta["last_modified"] = time.strftime("%Y-%m-%dT%H:%M:%SZ (mtime)", time.gmtime(os.path.getmtime(src)))
        stream = open(src, "rb")
    try:
        for raw in stream:
            h.update(raw)
            n += len(raw)
            yield raw
    finally:
        stream.close()
    meta["bytes"] = n
    meta["sha256"] = h.hexdigest()


def resset_headers():
    """{(ResSet file, profile): (nominal RU, nominal RC, RC interval or '')} from the ResSet files' headers."""
    out = {}
    for fn in sorted(os.listdir(RESSET)):
        if not fn.startswith("ResSet") or not fn.endswith(".txt"):
            continue
        text = open(os.path.join(RESSET, fn), encoding="latin-1").read()
        parts = re.split(r"File number (\d+)", text)
        for k in range(1, len(parts), 2):
            b = parts[k + 1]
            ru = re.search(r"Resource Use \(RU\): (\d+)", b).group(1)
            rc = re.search(r"Constrainedness \(RC\): ([\d.]+)", b).group(1)
            iv = re.search(r"interval: \[([\d.]+); ([\d.]+)\]", b)
            out[(fn, int(parts[k]))] = (int(ru), float(rc), f"{iv.group(1)}-{iv.group(2)}" if iv else "")
    return out


def level(s, ind, nom):
    """The design level of the set's controlled factor: network indicators rounded to their design grid (SP in steps
    of 0.1, AD, LA and TF in steps of 0.2), resource factors from the ResSet header (RC, RU; NR_VAR: whether each
    resource's RC is drawn from the wide interval 0.10-0.90 or a narrow one)."""
    c = CTRL[s]
    if c == "SP":
        return f"{round(ind['SP'] * 10) / 10:.1f}"
    if c in ("AD", "LA", "TF"):
        return f"{round(ind[c] * 5) / 5:.1f}"
    ru, rc, iv = nom
    if c == "RC":
        return f"{rc:.2f}"
    if c == "RU":
        return str(ru)
    return "wide" if iv == "0.10-0.90" else "narrow"


def fnum(x):
    return float(x.replace(",", ".")) if x.strip() else float("nan")


def main():
    refresh = "--refresh" in sys.argv
    os.makedirs(DATA, exist_ok=True)
    old = {}
    sp = os.path.join(DATA, "sources.tsv")
    if os.path.exists(sp):
        for r in csv.DictReader(open(sp), delimiter="\t"):
            old[(r["date"], r["set"])] = r["sha256"]
    nom_of = resset_headers()
    sources, summary, totals, checks = [], [], [], {}
    st_rows = []
    record_sets = []
    for s in SETS:
        n_rows = None
        arr = {}                 # date -> (lb, ub, lbref, ubref) arrays indexed by id
        crc0 = None
        refcode = {}             # ref string -> small int
        ind_cols = {k: None for k in IND}
        refs = None
        anomalies = collections.Counter()
        for di, date in enumerate(DATES):
            src = source(date, s)
            meta = {}
            started = False
            rset = None
            lb = ub = lbr = ubr = crc = None
            nrows = 0
            for raw in lines_of(src, meta):
                line = raw.decode("latin-1").rstrip("\r\n")
                f = line.split(";")
                if f[0] == "Number" and n_rows is None:
                    n_rows = int(f[1])
                if f[0] == "ID" and len(f) > 1 and f[1].strip().isdigit():
                    rset = {"date": date, "set": s, "ref": f[1].strip()}      # trailer: one record set
                    record_sets.append(rset)
                    continue
                if line.startswith("# ") and rset is not None:
                    rset[f[0][2:].strip()] = f[1].strip() if len(f) > 1 else ""
                    continue
                if f[0] == "ID":
                    if started:
                        sys.exit(f"{s} {date}: a second header line")
                    started = True
                    N = n_rows
                    lb, ub = array.array("h", [0]) * (N + 1), array.array("h", [0]) * (N + 1)
                    lbr, ubr = array.array("b", [0]) * (N + 1), array.array("b", [0]) * (N + 1)
                    crc = array.array("I", [0]) * (N + 1)
                    if di == 0:
                        for k in ind_cols:
                            ind_cols[k] = array.array("f", [0.0]) * (N + 1)
                        refs = (array.array("H", [0]) * (N + 1), array.array("H", [0]) * (N + 1),
                                array.array("H", [0]) * (N + 1))
                        folders, ressets = {}, {}
                    continue
                if not started or not f[0].isdigit():
                    continue
                i = int(f[0])
                if i > N or len(f) < 28:
                    anomalies[f"{date} bad row"] += 1
                    continue
                nrows += 1
                try:
                    lb[i], ub[i] = int(f[4]), int(f[7])
                except ValueError:
                    anomalies[f"{date} non-integer LB/UB"] += 1
                    continue
                lbr[i] = refcode.setdefault(f[5].strip(), len(refcode) + 1)
                ubr[i] = refcode.setdefault(f[8].strip(), len(refcode) + 1)
                crc[i] = zlib.crc32(";".join(f[1:4] + f[13:34]).encode("latin-1"))
                if di == 0:
                    for k, j in IND.items():
                        ind_cols[k][i] = fnum(f[j])
                    folder, name = f[1].replace("\\", "/").split("/")[-2:]
                    refs[0][i] = folders.setdefault(folder, len(folders))
                    refs[1][i] = int(re.sub(r"\D", "", name))
                    refs[2][i] = int(f[3])
                    ressets.setdefault(f[2].strip(), 0)
                    ressets[f[2].strip()] += 1
            if src.startswith("http") and meta.get("content_length") and int(meta["content_length"]) != meta["bytes"]:
                sys.exit(f"{s} {date}: read {meta['bytes']} bytes of {meta['content_length']}")
            key = (date, s)
            if key in old and old[key] != meta["sha256"] and not refresh:
                sys.exit(f"{s} {date}: sha256 {meta['sha256']} differs from sources.tsv ({old[key]}); "
                         "the source changed: rerun with --refresh only on purpose")
            sources.append({"date": date, "set": s, "source": src.replace(ROOT + os.sep, ""), "bytes": meta["bytes"],
                            "sha256": meta["sha256"], "rows": nrows, "last_modified": meta["last_modified"],
                            "read_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(f"{s} {date}: {nrows} rows, {meta['bytes']} bytes, sha256 {meta['sha256'][:16]}", flush=True)
            if nrows != N:
                anomalies[f"{date} rows {nrows} != Number {N}"] += 1
            if di == 0:
                crc0 = crc
                checks[s] = {"folders": {v: k for k, v in folders.items()}, "ressets": ressets}
            else:
                diff = sum(1 for i in range(1, N + 1) if crc[i] != crc0[i])
                checks[s][f"instance columns differing {DATES[0]} vs {date}"] = diff
            arr[date] = (lb, ub, lbr, ubr)
        inv = {v: k for k, v in refcode.items()}
        q = refcode.get("4")
        ressets = list(checks[s]["ressets"])
        if len(ressets) != 1:
            sys.exit(f"{s}: several ResSet files {ressets}")
        rs_file = ressets[0]
        folders = checks[s]["folders"]
        cell_n = collections.Counter()
        for i in range(1, N + 1):
            ind = {k: ind_cols[k][i] for k in IND}
            nom = nom_of[(rs_file, refs[2][i])]
            rsb = min(9, int(ind["RS"] * 10)) if ind["RS"] == ind["RS"] else -1
            cell = (level(s, ind, nom), f"{nom[1]:.2f}", str(nom[0]), nom[2] or "-", str(rsb))
            cell_n[cell] += 1
            vals = [arr[d] for d in DATES]
            opens = [v[0][i] < v[1][i] for v in vals]
            changed = any((v[0][i], v[1][i]) != (vals[0][0][i], vals[0][1][i]) for v in vals[1:])
            ours = q is not None and any(v[2][i] == q or v[3][i] == q for v in vals)
            if any(opens) or changed or ours:
                row = [s, i, folders[refs[0][i]], refs[1][i], rs_file, refs[2][i]] + list(cell)
                row += [("%.4g" % ind[k]) for k in IND]
                for v in vals:
                    row += [v[0][i], inv[v[2][i]], v[1][i], inv[v[3][i]]]
                st_rows.append(row)
        for cell, n in sorted(cell_n.items()):
            totals.append([s] + list(cell) + [n])
        for d in DATES:
            lb, ub, lbr, ubr = arr[d]
            closed = sum(1 for i in range(1, N + 1) if lb[i] == ub[i])
            bad = sum(1 for i in range(1, N + 1) if lb[i] > ub[i])
            rec = {"date": d, "set": s, "rows": N, "closed": closed, "open": N - closed - bad, "lb_above_ub": bad,
                   "sum_lb": sum(lb[1:]), "sum_ub": sum(ub[1:]),
                   "open_units": sum(ub[i] - lb[i] for i in range(1, N + 1) if ub[i] > lb[i])}
            lbc = collections.Counter(inv[lbr[i]] for i in range(1, N + 1))
            ubc = collections.Counter(inv[ubr[i]] for i in range(1, N + 1))
            rec["lb_refs"] = json.dumps(dict(sorted(lbc.items())), sort_keys=True)
            rec["ub_refs"] = json.dumps(dict(sorted(ubc.items())), sort_keys=True)
            summary.append(rec)
        checks[s]["anomalies"] = dict(anomalies)
        checks[s]["refs"] = sorted(refcode)
        del arr, ind_cols, refs
    with open(sp, "w") as f:
        w = csv.DictWriter(f, fieldnames=list(sources[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(sources)
    with open(os.path.join(DATA, "summary.tsv"), "w") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(summary)
    with open(os.path.join(DATA, "totals.tsv"), "w") as f:
        f.write("set\tlevel\trc_nom\tru_nom\trc_interval\trs_decile\tn\n")
        for r in totals:
            f.write("\t".join(map(str, r)) + "\n")
    head = ["set", "id", "folder", "network", "resset", "profile", "level", "rc_nom", "ru_nom", "rc_interval",
            "rs_decile"] + list(IND)
    for d in DATES:
        t = d[5:].replace("-", "")
        head += [f"lb_{t}", f"lbref_{t}", f"ub_{t}", f"ubref_{t}"]
    with gzip.open(os.path.join(DATA, "state.csv.gz"), "wt", compresslevel=9, newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(head)
        w.writerows(st_rows)
    json.dump(checks, open(os.path.join(DATA, "checks.json"), "w"), indent=1, sort_keys=True)
    keys = ["date", "set", "ref", "Author(s)", "Reference", "Date", "Hardware / software", "Stop criteria",
            "Submission date"]
    with open(os.path.join(DATA, "record_sets.tsv"), "w") as f:
        w = csv.DictWriter(f, fieldnames=keys, delimiter="\t", lineterminator="\n", extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(record_sets)
    print(f"state rows {len(st_rows)}; totals cells {len(totals)}", flush=True)


if __name__ == "__main__":
    main()
