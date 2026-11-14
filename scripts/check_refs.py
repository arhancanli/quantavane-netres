"""Every reference of the paper, checked against Crossref's metadata (api.crossref.org, one request at a time, plain
user agent) and written to refs.bib from that metadata only: authors, title, container, volume, issue, pages, year and
DOI as Crossref has them. A DOI whose Crossref title does not contain the expected words is reported and left out.
Non-DOI items (software, web pages) are written from the CANDIDATES text and marked as such in data/crossref.json.
  python3 -I scripts/check_refs.py"""
import html
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
# key, DOI, words that must appear in the Crossref title (lower case)
CANDIDATES = [
    ("vanhoucke2018tool", "10.1016/j.cie.2018.02.001", "tool to test and validate"),
    ("kolisch1997psplib", "10.1016/S0377-2217(96)00170-1", "psplib"),
    ("kolisch1995progen", "10.1287/mnsc.41.10.1693", "characterization and generation"),
    ("demeulemeester1992bb", "10.1287/mnsc.38.12.1803", "branch-and-bound"),
    ("klein1999destructive", "10.1016/S0377-2217(97)00442-6", "destructive improvement"),
    ("debels2007decomposition", "10.1287/opre.1060.0358", "decomposition-based genetic algorithm"),
    ("vanhoucke2008adequacy", "10.1016/j.ejor.2007.03.032", "adequacy of project network generators"),
    ("vanhoucke2007evm", "10.1057/palgrave.jors.2602296", "earned value"),
    ("demeulemeester2003rangen", "10.1023/A:1022283403119", "rangen"),
    ("schutt2011cumulative", "10.1007/s10601-010-9103-2", "cumulative propagator"),
    ("schutt2013rcpspmax", "10.1007/s10951-012-0285-x", "lazy clause generation"),
    ("vilim2015fds", "10.1007/978-3-319-18008-3_30", "failure-directed search"),
    ("laborie2018cpo", "10.1007/s10601-018-9281-x", "cp optimizer for scheduling"),
    ("brucker1999survey", "10.1016/S0377-2217(98)00204-5", "notation, classification"),
    ("hartmann2022survey", "10.1016/j.ejor.2021.05.004", "updated survey"),
    ("kolisch2006heuristics", "10.1016/j.ejor.2005.01.065", "experimental investigation"),
    ("blazewicz1983complexity", "10.1016/0166-218X(83)90012-4", "classification and complexity"),
    ("coelho2018composite", "10.1016/j.cor.2018.01.017", "lower bound"),
    ("coelho2020core", "10.1016/j.cor.2020.104976", "core"),
    ("messelis2014selection", "10.1016/j.ejor.2013.08.021", "algorithm selection"),
    ("smithmiles2012difficulty", "10.1016/j.cor.2011.07.006", "instance difficulty"),
    ("rice1976selection", "10.1016/S0065-2458(08)60520-3", "algorithm selection"),
    ("kerschke2019selection", "10.1162/evco_a_00242", "automated algorithm selection"),
    ("bengio2021mlco", "10.1016/j.ejor.2020.07.063", "machine learning for combinatorial optimization"),
    ("pritsker1969multiproject", "10.1287/mnsc.16.1.93", "multiproject scheduling"),
    ("horbach2010sat", "10.1007/s10479-010-0693-2", "boolean satisfiability"),
    ("berthold2010cip", "10.1007/978-3-642-13520-0_34", "constraint integer programming"),
    ("baptiste2000constraint", "10.1023/A:1009822502231", "constraint propagation and decomposition"),
    ("brucker2000lp", "10.1016/S0377-2217(99)00489-0", "linear programming"),
    ("mingozzi1998exact", "10.1287/mnsc.44.5.714", "exact algorithm"),
    ("vilim2011ttef", "10.1007/978-3-642-21311-3_22", "timetable edge finding"),
    ("herroelen1998survey", "10.1016/S0305-0548(97)00055-5", "resource-constrained project scheduling"),
    ("patterson1976structure", "10.1002/nav.3800230110", "problem structure"),
    ("tavares1999morphology", "10.1016/S0377-2217(99)00150-2", "morphology"),
    ("mastor1970line", "10.1287/mnsc.16.11.728", "line balancing"),
    ("vanhoucke2010measuring", "10.1007/978-1-4419-1014-1", "measuring time"),
    ("perron2023cpsatlp", "10.4230/LIPIcs.CP.2023.3", "cp-sat-lp"),
    ("huangfu2018highs", "10.1007/s12532-017-0130-5", "dual revised simplex"),
    ("gocht2022auditable", "10.4230/LIPIcs.CP.2022.25", "auditable constraint programming"),
    ("flippo2024proof", "10.4230/LIPIcs.CP.2024.11", "proof logging"),
    ("coelho2023newinstances", "10.1016/j.cor.2023.106165", "instances"),
    ("guo2023ranking", None, "a prediction model for ranking branch-and-bound procedures for the resource-constrained "
                             "project scheduling problem"),
]
PARTICLES = {"Pape, Claude Le": "{Le Pape}, Claude", "Kan, A.H.G.Rinnooy": "{Rinnooy Kan}, A. H. G."}
SOFTWARE = {
    "ortools": "@misc{ortools,\n  author = {Perron, Laurent and Didier, Fr{\\'e}d{\\'e}ric},\n  title = {{OR-Tools} {CP-SAT}, "
               "version 9.15},\n  howpublished = {Google, \\url{https://developers.google.com/optimization}},\n  "
               "year = {2026}\n}",
    "solutionsupdate": "@misc{solutionsupdate,\n  author = {Vanhoucke, Mario and Coelho, Jos{\\'e}},\n  title = {Solutions "
                       "Update: best known solutions for project scheduling datasets},\n  howpublished = {Ghent "
                       "University, \\url{http://solutionsupdate.ugent.be}, dataset files of 1, 6 and 9 November "
                       "2026},\n  year = {2026}\n}",
    "sklearn": "@article{pedregosa2011sklearn,\n  author = {Pedregosa, Fabian and Varoquaux, Ga{\\\"e}l and Gramfort, "
               "Alexandre and others},\n  title = {Scikit-learn: Machine Learning in {P}ython},\n  journal = {Journal "
               "of Machine Learning Research},\n  volume = {12},\n  pages = {2825--2830},\n  year = {2011}\n}",
}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"<[^>]+>", "", s or "").lower()).strip()


def query(title):
    """Crossref search by title; the item whose title equals it (ignoring case and punctuation), else None."""
    url = "https://api.crossref.org/works?rows=5&query.bibliographic=" + urllib.parse.quote(title)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        items = json.load(r)["message"]["items"]
    for m in items:
        if norm((m.get("title") or [""])[0]) == norm(title):
            return m
    return None


def datacite(doi):
    """A DataCite DOI (LIPIcs) as a Crossref-like record."""
    url = "https://api.datacite.org/dois/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        a = json.load(r)["data"]["attributes"]
    cont = ""
    for it in a.get("relatedItems") or []:
        if it.get("relationType") == "IsPublishedIn" and it.get("titles"):
            cont = it["titles"][0].get("title", "")
    if not cont and a.get("container"):
        cont = a["container"].get("title", "")
    return {"type": "proceedings-article", "title": [a["titles"][0]["title"]], "DOI": doi,
            "container-title": [cont], "issued": {"date-parts": [[a.get("publicationYear")]]},
            "author": [{"given": c.get("givenName", ""), "family": c.get("familyName", c.get("name", ""))}
                       for c in a.get("creators", [])], "publisher": a.get("publisher", "")}


def get(doi):
    if doi.startswith("10.4230/"):
        return datacite(doi)
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["message"]


def tex(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", s or ""))
    s = unicodedata.normalize("NFC", s)
    rep = {"&": "\\&", "%": "\\%", "_": "\\_", "#": "\\#", "\u2013": "--", "\u2014": "---", "\u2010": "-",
           "\u2019": "'", "\u2018": "`", "\u201c": "``", "\u201d": "''", "\u00a0": " "}
    for a, b in rep.items():
        s = s.replace(a, b)
    acc = {"é": "{\\'e}", "è": "{\\`e}", "á": "{\\'a}", "ó": "{\\'o}", "í": "{\\'i}", "ú": "{\\'u}", "ö": '{\\"o}',
           "ü": '{\\"u}', "ä": '{\\"a}', "ç": "{\\c c}", "ñ": "{\\~n}", "ł": "{\\l}", "ż": "{\\.z}", "É": "{\\'E}",
           "Ö": '{\\"O}', "Ü": '{\\"U}', "ã": "{\\~a}", "ê": "{\\^e}", "ë": '{\\"e}', "ï": '{\\"i}', "š": "{\\v s}",
           "č": "{\\v c}", "ř": "{\\v r}", "ž": "{\\v z}", "Š": "{\\v S}", "Č": "{\\v C}", "ı": "{\\i}", "ğ": "{\\u g}",
           "å": "{\\aa}", "ø": "{\\o}", "æ": "{\\ae}", "ß": "{\\ss}"}
    return "".join(acc.get(ch, ch) for ch in s)


def entry(key, m):
    kind = m.get("type")
    authors = " and ".join(f"{tex(a.get('family', ''))}, {tex(a.get('given', ''))}".strip(", ")
                           for a in m.get("author", []) if a.get("family"))
    for wrong, right in PARTICLES.items():   # surname particles that Crossref files under the given name
        authors = authors.replace(wrong, right)
    title = tex((m.get("title") or [""])[0])
    year = None
    for k in ("published-print", "issued"):          # the volume's year where Crossref has it, else the first date
        dp = (m.get(k) or {}).get("date-parts") or [[None]]
        if dp[0] and dp[0][0]:
            year = dp[0][0]
            break
    cont = tex((m.get("container-title") or [""])[0])
    f = {"author": authors, "title": "{{" + title + "}}", "year": str(year), "doi": m.get("DOI", "")}
    if kind == "journal-article":
        bt = "article"
        f["journal"] = cont
    elif kind in ("proceedings-article", "book-chapter"):
        bt = "inproceedings" if kind == "proceedings-article" else "incollection"
        conts = [tex(c) for c in (m.get("container-title") or [])]
        main_c = [c for c in conts if "Lecture Notes" not in c]
        f["booktitle"] = main_c[0] if main_c else cont
        if any("Lecture Notes" in c for c in conts):
            f["series"] = "Lecture Notes in Computer Science"
    elif kind in ("book", "monograph"):
        bt = "book"
        f["publisher"] = tex(m.get("publisher", ""))
    else:
        bt = "misc"
        f["howpublished"] = cont
    for a, b in (("volume", "volume"), ("issue", "number"), ("page", "pages")):
        if m.get(a):
            f[b] = tex(str(m[a])).replace("-", "--").replace("----", "--")
    body = ",\n".join(f"  {k} = {{{v}}}" if not v.startswith("{") else f"  {k} = {v}" for k, v in f.items() if v)
    return f"@{bt}{{{key},\n{body}\n}}"


def main():
    out, bib = {}, []
    for key, doi, words in CANDIDATES:
        try:
            m = get(doi) if doi else query(words)
            if m is None:
                raise ValueError("no Crossref item with exactly this title")
            doi = m.get("DOI", doi)
        except Exception as exc:
            out[key] = {"doi": doi, "ok": False, "error": repr(exc)[:200]}
            print(f"{key}: {doi} FAILED ({exc})", flush=True)
            time.sleep(1.2)
            continue
        title = (m.get("title") or [""])[0]
        ok = words.lower() in title.lower()
        out[key] = {"doi": doi, "ok": ok, "title": title, "type": m.get("type"),
                    "container": (m.get("container-title") or [""])[0], "volume": m.get("volume"),
                    "issue": m.get("issue"), "page": m.get("page"),
                    "year": (m.get("issued", {}).get("date-parts") or [[None]])[0][0],
                    "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in m.get("author", [])]}
        print(f"{key}: {'ok ' if ok else 'TITLE MISMATCH'} {title[:90]} | {out[key]['container'][:50]} "
              f"{out[key]['volume']} {out[key]['page']} {out[key]['year']}", flush=True)
        if ok:
            bib.append(entry(key, m))
        time.sleep(1.2)
    for k, v in SOFTWARE.items():
        bib.append(v)
        out[k] = {"ok": True, "note": "not a DOI item; written by hand in check_refs.py"}
    json.dump(out, open(os.path.join(DATA, "crossref.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(PAPER, "refs.bib"), "w").write("% written by scripts/check_refs.py from Crossref metadata\n\n"
                                                     + "\n\n".join(bib) + "\n")
    print(sum(1 for v in out.values() if v.get("ok")), "of", len(out), "references kept")


if __name__ == "__main__":
    main()
