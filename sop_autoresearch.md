# sop-to-code-agent — sop_autoresearch.md

This is the autonomous experiment loop for this repo, in the spirit of
[autoresearch-macos](https://github.com/karpathy/autoresearch-macos): point
an agent here, let it run unattended for a fixed budget, wake up to a log of
what it tried and a (hopefully) better pipeline.

Read `program.md` first — it describes the architecture, conventions, and
guardrails this loop must respect. This file only describes the loop itself.

> "Read sop_autoresearch.md and run the experiment loop."

---

## 0. One-time setup (run once, not per experiment)

The repo currently has untracked prep files sitting in the working tree
(`.gitignore`, `program.md`, `env_source.sh`, `results.tsv`,
`terminal_output.txt`). The loop below commits and reverts with
`git reset --hard`, so it needs a clean, fully-intentional starting point.
Before the first experiment:

1. Confirm `git status --short` is something you understand — nothing
   accidental in it.
2. `results.tsv` in this checkout is stale (see `program.md` §2.2) —
   truncate it to just its header line so the score history starts clean:
   `commit\tdomain\tcompleted\tretries\trow_pass_rate\terror`
3. Decide what to do with `terminal_output.txt` (looks like a saved terminal
   dump, not source) — don't commit it silently; either add it to
   `.gitignore` or leave it untracked and out of the loop's commits.
4. Add `experiment_log.md` to `.gitignore` — it must stay **untracked**
   (§3 explains why: `git reset --hard` must never touch it).
5. Commit the remaining prep files (`.gitignore`, `program.md`,
   `env_source.sh`, the cleared `results.tsv`) as one plain commit —
   this is your starting point, not an experiment.
6. Run `python test_harness.py` once, untouched, to get the real baseline.
   Compute `S_prev` = mean of the `row_pass_rate` column over the rows this
   run just appended (one row per domain; a failed domain already scores
   `0.0`, so no extra weighting is needed). Commit the resulting
   `results.tsv` as part of that same starting commit, or immediately after.

You now have a HEAD commit and a known `S_prev`. Everything below assumes
that exists.

---

## 1. Scope — what an experiment may touch

**Editable** (this is the thing being iterated on, like `train.py` in
autoresearch-macos):
`planner_agent.py`, `schema_agent.py`, `codegeneration_agent.py`,
`validation_agent.py`, `orchestrator_agent.py`, `agent_pipeline.py`,
`client.py`. `sop_state.py` is editable too but touches a shared contract —
only change it if the experiment updates every agent that reads/writes the
new field in the same commit.

**Fixed** (this is the ground truth and harness, like `prepare.py` — don't
modify to make a score go up):
`eval_sops/` (golden SOPs, toolspecs, and held-out test CSVs), `test_harness.py`,
`tools_helper.py`, `global_tool_functions.py`, `sop_state.py`'s *shape* (fields
may be added, not repurposed).

**Out of scope for this loop**: `main.py`'s known bug (`program.md` §2.1) is
a one-time fix, not an experiment — fix it in the setup commit if you care
about it, not as one of the N experiments below, since it doesn't affect
`test_harness.py`'s score at all (the harness calls `converter.convert()`
directly, never `main.py`).

---

## 2. Budget

Default: **15 experiments**, or **5 consecutive experiments with no kept
improvement**, whichever comes first. Adjust both numbers down if you're
rate-limited (see `results.tsv`'s history of Groq 404/413 errors in
`program.md` §2.2) — each experiment costs a full multi-agent pipeline run
across every domain, which is real API spend, not free local compute like
nanochat's 5-minute GPU budget.

---

## 3. The experiment loop

Repeat until the budget in §2 is hit:

1. **Form one hypothesis.** One idea per experiment, even if it touches
   several files (e.g. "tighten the validator's prompt to catch missing
   None-checks" may require a matching test in `validation_agent.py` and a
   feedback-string change in `orchestrator_agent.py` — that's still one
   hypothesis). Don't bundle unrelated ideas; you can't attribute the score
   change to either one afterward.
2. **Implement it** in the editable files from §1 only.
3. **Commit the candidate**: `git add -- <files you changed>` (not
   `results.tsv`, not `-A`) then
   `git commit -m "experiment: <one-line hypothesis>"`.
   Committing *before* scoring matters — `test_harness.py` tags every row
   with `git rev-parse --short HEAD`, so the score can't be attributed to
   this candidate until it's HEAD.
4. **Run** `python test_harness.py`. It appends fresh rows to `results.tsv`,
   tagged with the commit from step 3.
5. **Score it**: `S_new` = mean `row_pass_rate` over just the rows this run
   appended.
6. **Log it** — append one line to `experiment_log.md` (untracked, never
   committed) *before* any revert, so the record survives even a discard:
   `<commit>  S_prev=<x> S_new=<y>  <keep|discard>  <hypothesis>`
7. **Decide**:
   - `S_new >= S_prev` → **keep**. `git add results.tsv && git commit -m "results: S=<S_new>"` (or amend step 3's commit to include it). Set `S_prev = S_new`.
   - `S_new < S_prev` → **discard**. `git reset --hard HEAD~1`. This drops
     the candidate commit *and* the uncommitted `results.tsv` rows from step
     4 — that's fine, they're already preserved in `experiment_log.md`.
     `S_prev` is unchanged.
8. Go to 1.

Because `experiment_log.md` is untracked and reset --hard never touches
untracked files, it accumulates every attempt — kept and discarded — across
the whole run. Because discards are hard-reset, the git history only ever
shows commits that improved or held the score, so `git log` alone tells you
the winning path.

---

## 4. Noise warning

Unlike nanochat's deterministic local training, the LLM calls here are not
deterministic — the same code can score differently across two runs. A
single-run `S_new` can be a lucky or unlucky sample, not a real signal. This
loop accepts that trade-off for cost reasons (doubling every experiment to
average two runs also doubles API spend and rate-limit exposure). If you see
a kept experiment's score not reproduce on the next run, don't chase it —
note it in `experiment_log.md` and move on; the hard-reset-on-regression
design means a truly bad change gets caught on a later experiment even if it
slipped through once.

---

## 5. End of run

When the budget is hit, append a summary to the top of `experiment_log.md`:
experiments run, kept vs. discarded count, `S_start` vs. final `S_prev`, and
the list of kept commit hashes with their one-line hypotheses — this is what
the human reads in the morning.
