# Closing open NetRes instances with CP-SAT and a learned run order: code and data

This repository holds the solver code, the frozen predictions of the learned run orders, and the scripts and data
extracts behind the paper "Closing open NetRes instances of the resource-constrained project scheduling problem
with CP-SAT and a learned run order" by Arhan Canli (Quantavane), November 2026.

The NetRes sets of Vanhoucke and Coelho (2018) hold 3,810,000 instances of the resource-constrained project
scheduling problem with 30 activities. On 1 November 2026, 113,071 of them were open on Ghent University's
[Solutions Update site](http://solutionsupdate.ugent.be). The paper reports runs of OR-Tools CP-SAT on every open
instance: short runs capped at the best known value, then a destructive-improvement scheme that proves lower
bounds. In the site's files of 9 November 2026, 67,595 of these instances are closed, 29,282 more have a better
bound, and NR(LA) is the first NetRes set with all 720,000 instances closed. The paper also studies the order in
which a lower-bound pass runs its queue: on two cells whose outcomes were not read before the predictions were
frozen (5,582 and 947 re-runs), the first fifth of the learned order found 1.79 and 1.92 times as many new bounds
as random choice.

## What is here

The solver code keeps the folder names of the working tree it ran in, so that its imports work unchanged.

- `engine/sched/rcpsp_cpsat.py`: the CP-SAT model and the destructive procedure for lower bounds.
- `runs/sched/netres.py`, `netres_lb.py`, `netres_pass2.py`: the NetRes runners (first pass, lower-bound passes,
  second pass). `runs/sched/make_upload.py` writes the result files in the format of the Solutions Update site.
- `runs/kaggle_netres/build.py` and `run_template.py`: the packager and the kernel template for the passes that
  ran on Kaggle notebooks.
- `engine/models/netres_jobs.py`: the side-by-side runs for the A/B cells of the learned components.
- Frozen predictions and orders of the three learned components (lanes `sched-netres-lb`, `sched-netres-rerun`
  and `sched-netres-lb-params` of `data/registry_netres.json`):
  `runs/sched/model_v1/pred_snapshot_20261107T120228Z.tsv`, `runs/sched/model_v2/pred_lb6_20261108T172526Z.tsv`,
  `runs/kaggle_netres/order_v1_20261107.tsv`, `order_lb6_20261108.tsv` and `order_lb7_20261109.tsv`,
  `runs/sched/model_rerun/pred/` (`pred_cell2.tsv`, `pred_cell3.tsv`), `runs/sched/model_rerun_v2/` and
  `runs/sched/model_rerun_x1/` (`pred_A.tsv`, `pred_B.tsv`, each with the `predict_info.json` that records their
  SHA-256 digests), and `runs/sched/model_params/picks.tsv`.
- `data/`: the per-instance and per-run extracts behind every number of the paper. Among them:
  `state.csv.gz` (the state of the instances on the three dates), `sent_lines.csv.gz` and `listed_lines.csv.gz`
  (our result lines as sent and as the site lists them), `runs.tsv` and `runs_by_set.tsv` (the stages),
  `reprove.tsv` (the sampled lower bounds proved again), `registry_netres.json` (the registry entries of the three
  learned components, with every A/B cell), `rerun_cells.tsv.gz` (one row per instance of the held-out re-run
  cells: every order's score, the outcome and the CPU time of each run) and `rerun_policy.json`. `sources.tsv`
  and `ours_sources.tsv` give the size and SHA-256 of every file the extracts were read from.
- `scripts/`: the paper's scripts. `make_numbers.py` computes the paper's numbers and tables from `data/`;
  `ab_pvalues.py` and `rc_rs.py` also need only `data/`. `instances.py` is the instance reader of the checking
  scripts, written separately from the reader in `runs/sched/netres.py`.
- `checks/`: `run_checks.sh`, which runs the quick checks below, and its output `results.txt`.

`SHA256SUMS` lists every file.

## How to re-run the checks

Commands are run from the repository root with Python 3. `make_numbers.py`, `ab_pvalues.py` and `rc_rs.py` use the
standard library only; the solver code needs OR-Tools (the runs used version 9.15).

```sh
sh checks/run_checks.sh          # PYTHON=/path/to/python3 to choose the interpreter
```

It checks the four prediction files of `model_rerun_v2` and `model_rerun_x1` against the SHA-256 digests in their
`predict_info.json`, checks that the digests of the solver files recorded in `data/registry_netres.json` are those
of the files here, runs `scripts/make_numbers.py` (which writes `numbers.tex`, `numbers.json`, `highlights.tex`,
`highlights.txt` and `tables/` in the repository root, the files the paper's LaTeX source reads), runs
`ab_pvalues.py` and `rc_rs.py`, and, when OR-Tools is installed, imports the solver code. The last line of
`checks/results.txt` must read `ALL PASS`.

To run a pass again, see the first lines of `runs/sched/netres.py` and `runs/sched/netres_lb.py`. `netres.py`
fetches the dataset files of the Solutions Update site into `runs/sched/NR_<set>/` and expects the site's NetRes
archive unzipped in `runs/sched/NR_SP/inst/`.

## What the other scripts need

The other scripts of `scripts/` show how `data/` was made. They read the campaign's working folder, which is not
part of this repository: the site's dataset files of 1, 6 and 9 November 2026 and the NetRes archive
(`runs/sched/NR_<set>/`, about 1 GB, available from the site), and the per-run result files of the passes in the
same folders. With those files in place:

- `extract_ghent.py`, `extract_design.py` and `extract_runs.py` write the extracts of the site's files, of the
  design of the sets and of the stages;
- `check_schedules.py`, `check_readers.py`, `reprove_sample.py`, `reprove_la.py` and `ablation_hint.py` write the
  checks of Section 6 of the paper and the hint ablation;
- `ab_table.py` and `rerun_policy.py` write the A/B tables and the held-out re-run cells; they also read the lab's
  full model registry, of which `data/registry_netres.json` is the part on these three components;
- `figures.py` draws the figures and `check_refs.py` checks the references against Crossref.

`data/sent_lines.csv.gz`, `listed_lines.csv.gz`, `lead_lines.tsv`, `ours_sources.tsv` and `site_stats.tsv` were
written by a script that is not included, because it reads the lab's own copies of the result files sent to the
site.

## Notes on the files

In the scripts, the paths of the machine that ran them were replaced by paths inside this repository, and the name
of its Python interpreter by `python3`. In `data/sources.tsv`, `data/ours_sources.tsv` and
`data/registry_netres.json`, source paths are given relative to the working tree (`runs/sched/...`,
`engine/models/registry.json`), and the three files sent to the site are named without their folders. Nothing else
was changed. The registry entries in `data/registry_netres.json` name further files of the working tree (training
code, logs, result files) that are not part of this repository.

## Credit and sources

- The NetRes sets are by M. Vanhoucke and J. Coelho (2018). The instances, the best known solutions and the
  results listed for every instance are on the Solutions Update site of Ghent University, maintained by José
  Coelho and Mario Vanhoucke, who also applied the results of this campaign. The values of the site that appear
  in `data/` (published bounds, record sets, the listing of our lines) are the site's and its contributors'.
- The solver is OR-Tools CP-SAT (Google). Some passes ran on Kaggle notebook CPUs.
- The references of the paper were checked against Crossref (`scripts/check_refs.py`, `data/crossref.json`).

## Authorship and the role of AI

Author and maintainer: Arhan Canli (Quantavane, https://quantavane.com), who takes responsibility for the results.

The search code, the checkers, the re-proof models, the learned components, the scripts and the runs were written
and carried out by AI agents (Claude, by Anthropic) working for Quantavane under Arhan Canli's direction. No
researcher outside Quantavane has reviewed this repository; the Solutions Update site lists every result that was
sent, and the results can be checked by anyone with the programs here or with their own.

## How to cite

If you use this code or these data, please cite them as below, with the NetRes sets of Vanhoucke and Coelho (2018) and
the Solutions Update site of Ghent University.

```bibtex
@misc{quantavane-netres,
  author       = {Canli, Arhan},
  title        = {Closing open NetRes instances of the resource-constrained project scheduling problem with CP-SAT and a learned run order: code and data},
  year         = {2026},
  howpublished = {\url{https://github.com/arhancanli/quantavane-netres}},
  note         = {Quantavane; CC BY 4.0 for the data and text, MIT licence for the code}
}
```

[CITATION.cff](CITATION.cff) gives the same reference for GitHub's "Cite this repository" button.

## Licence

The code is under the MIT licence (`LICENSE-CODE`); the data and the text are under CC BY 4.0 (`LICENSE`). To cite:
see `CITATION.cff`.
