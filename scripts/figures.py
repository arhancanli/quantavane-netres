"""The paper's figures, from data/ (run scripts/make_numbers.py first: it writes fig_levels.tsv, fig_rs.tsv, fig_gaps.tsv).
  python3 -I scripts/figures.py
Writes figures/status.pdf, levels.pdf, remaining.pdf, ranking.pdf. Colours: grey for 1 Nov (before), blue for 9 Nov
(after); in the ranking figure blue for the model's order, orange for the plain order, grey dashed for random."""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PAPER, "data")
FIG = os.path.join(PAPER, "figures")
SETS = ["NR_SP", "NR_AD", "NR_LA", "NR_TF", "NR_RC", "NR_RU", "NR_VAR"]
BEFORE, AFTER, PLAIN, INK, MUTED = "#a3a29c", "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7, "axes.edgecolor": MUTED,
                     "axes.linewidth": 0.6, "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": INK,
                     "text.color": INK, "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False})


def tsv(name):
    return list(csv.DictReader(open(os.path.join(DATA, name)), delimiter="\t"))


def status():
    summ = {(r["set"], r["date"]): r for r in tsv("summary.tsv")}
    fig, ax = plt.subplots(figsize=(6.3, 2.3))
    y = list(range(len(SETS)))[::-1]
    for k, s in enumerate(SETS):
        n = int(summ[(s, "2026-11-01")]["rows"])
        a = 1000 * int(summ[(s, "2026-11-01")]["open"]) / n
        c = 1000 * int(summ[(s, "2026-11-09")]["open"]) / n
        ax.barh(y[k] + 0.18, a, height=0.34, color=BEFORE, edgecolor="white", linewidth=0.8)
        ax.barh(y[k] - 0.18, c, height=0.34, color=AFTER, edgecolor="white", linewidth=0.8)
        ax.text(a + 1, y[k] + 0.18, f"{int(summ[(s, '2026-11-01')]['open']):,}", va="center", fontsize=6.5, color=MUTED)
        ax.text(c + 1, y[k] - 0.18, f"{int(summ[(s, '2026-11-09')]['open']):,}", va="center", fontsize=6.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([f"NR({s[3:]})" for s in SETS])
    ax.set_xlabel("open instances per 1,000 (labels: number open)")
    ax.barh([], [], color=BEFORE, label="1 Nov 2026")
    ax.barh([], [], color=AFTER, label="9 Nov 2026")
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="x", color="#e4e3df", linewidth=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "status.pdf"))
    plt.close(fig)


def levels():
    rows = tsv("fig_levels.tsv")
    fig, axes = plt.subplots(2, 4, figsize=(6.3, 3.4))
    for ax, s in zip(axes.flat, SETS):
        rr = [r for r in rows if r["set"] == s]
        lab = [r["level"] for r in rr]
        x = list(range(len(rr)))
        a = [1000 * int(r["open_1101"]) / int(r["n"]) for r in rr]
        c = [1000 * int(r["open_1109"]) / int(r["n"]) for r in rr]
        ax.plot(x, a, color=BEFORE, marker="o", markersize=3, linewidth=1.2, label="1 Nov")
        ax.plot(x, c, color=AFTER, marker="o", markersize=3, linewidth=1.2, label="9 Nov")
        ax.set_xticks(x)
        ax.set_xticklabels(lab, rotation=0 if len(x) <= 4 else 90)
        ax.set_title(f"NR({s[3:]}): {rr[0]['factor']}", loc="left")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color="#e4e3df", linewidth=0.5)
        ax.set_axisbelow(True)
    axes.flat[0].set_ylabel("open per 1,000")
    axes.flat[4].set_ylabel("open per 1,000")
    leg = axes.flat[7]
    leg.axis("off")
    leg.plot([], [], color=BEFORE, marker="o", markersize=3, label="1 Nov 2026")
    leg.plot([], [], color=AFTER, marker="o", markersize=3, label="9 Nov 2026")
    leg.legend(frameon=False, loc="center")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "levels.pdf"))
    plt.close(fig)


def remaining():
    g = tsv("fig_gaps.tsv")
    rs = tsv("fig_rs.tsv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.3, 2.3))
    x = list(range(len(g)))
    a1.bar([v - 0.2 for v in x], [int(r["open_1101"]) for r in g], width=0.38, color=BEFORE, label="1 Nov 2026")
    a1.bar([v + 0.2 for v in x], [int(r["open_1109"]) for r in g], width=0.38, color=AFTER, label="9 Nov 2026")
    a1.set_xticks(x)
    a1.set_xticklabels([r["gap"].replace("gt", ">") for r in g])
    a1.set_xlabel("gap UB $-$ LB of an open instance")
    a1.set_ylabel("open instances")
    a1.legend(frameon=False)
    a1.grid(axis="y", color="#e4e3df", linewidth=0.5)
    a1.set_axisbelow(True)
    rs = [r for r in rs if int(r["n"]) > 0]
    x = list(range(len(rs)))
    a2.plot(x, [1000 * int(r["open_1101"]) / int(r["n"]) for r in rs], color=BEFORE, marker="o", markersize=3,
            linewidth=1.2, label="1 Nov 2026")
    a2.plot(x, [1000 * int(r["open_1109"]) / int(r["n"]) for r in rs], color=AFTER, marker="o", markersize=3,
            linewidth=1.2, label="9 Nov 2026")
    a2.set_xticks(x)
    a2.set_xticklabels([f"{int(r['rs_decile']) / 10:.1f}" for r in rs])
    a2.set_xlabel("resource strength RS (lower edge of decile)")
    a2.set_ylabel("open per 1,000")
    a2.grid(axis="y", color="#e4e3df", linewidth=0.5)
    a2.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "remaining.pdf"))
    plt.close(fig)


def ranking():
    rows = tsv("ab_curves.tsv")
    cells = [("NetRes pass 3 remainder (prospective)", "pass-3 remainder, 15 s"),
             ("NetRes pass 3b at 40 s (prospective)", "L3b, 40 s"),
             ("NetRes pass 3c (prospective)", "L3c, 15 s")]
    fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.5))
    for ax, (cell, title) in zip(axes, cells):
        rr = [r for r in rows if r["cell"] == cell]
        n, tot = int(rr[0]["n"]), int(rr[0]["finds"])
        k = [int(r["k"]) / n for r in rr]
        ax.plot(k, [int(r["model"]) for r in rr], color=AFTER, linewidth=1.3, label="model order (v1)")
        ax.plot(k, [int(r["plain"]) for r in rr], color=PLAIN, linewidth=1.3, label="plain order")
        ax.plot([0, 1], [0, tot], color=BEFORE, linewidth=1.0, linestyle="--", label="random (expected)")
        ax.axvline(0.2, color=MUTED, linewidth=0.6, linestyle=":")
        ax.set_title(title, loc="left")
        ax.set_xlabel("share of the cell's runs")
        ax.grid(color="#e4e3df", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, tot * 1.03)
    axes[0].set_ylabel("cumulative finds")
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, frameon=False, loc="lower center", ncol=3)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(os.path.join(FIG, "ranking.pdf"))
    plt.close(fig)


def main():
    os.makedirs(FIG, exist_ok=True)
    status()
    levels()
    remaining()
    ranking()
    print("figures written:", sorted(os.listdir(FIG)))


if __name__ == "__main__":
    main()
