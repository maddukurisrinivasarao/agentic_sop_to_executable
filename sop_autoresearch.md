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
2. `results.tsv` in this checkout is stale (see `program.md` Section 2.2) —
   truncate it to just its header line so the score history starts clean:
   `commit\tdomain\tcompleted\tretries\trow_pass_rate\ttokens_used\terror`
   (the `tokens_used` column comes from `ClientSingleton.get_usage()`,
   reset per domain inside `score_domain()` — it's what Section 2's budget runs on.)
3. Decide what to do with `terminal_output.txt` (looks like a saved terminal
   dump, not source) — don't commit it silently; either add it to
   `.gitignore` or leave it untracked and out of the loop's commits.
4. Add `experiment_log.md` to `.gitignore` — it must stay **untracked**
   (Section 3 explains why: `git reset --hard` must never touch it).
5. Commit the remaining prep files (`.gitignore`, `program.md`,
   `env_source.sh`, the cleared `results.tsv`) as one plain commit —
   this is your starting point, not an experiment.
6. **Before scoring anything, check that `eval_sops/*/tools.py`'s
   `DATASET_CSV_FILE`/`TOOLSPEC_JSON_FILE` constants actually match files
   present in that domain's folder.** They didn't on the first run of this
   loop (all three domains pointed at filenames like `data.csv` that don't
   exist — only `test_set_with_outputs.csv` does) and every domain scored a
   fixture-driven `0.0` until that was fixed. This is exactly the kind of
   silent floor that makes every experiment afterward meaningless, so it's
   worth a quick sanity check any time you extend `eval_sops/` — even though
   `eval_sops/` itself stays out of scope for the loop's *experiments* (Section 1).
7. Run `python test_harness.py` once, untouched, to get the real baseline.
   Compute `S_prev` = mean of the `row_pass_rate` column over the rows this
   run just appended (one row per domain; a failed domain already scores
   `0.0`, so no extra weighting is needed). Also note `T_prev` = sum of the
   `tokens_used` column for those same rows — this is your first real data
   point for the token budget in Section 2. Commit the resulting `results.tsv` as
   part of that same starting commit, or immediately after.

You now have a HEAD commit, a known `S_prev`, and a known per-run token cost
`T_prev`. Everything below assumes that exists.

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
may be added, not repurposed). `test_harness.py` already gained a
`--domains` filter and per-domain `tokens_used` tracking as part of Section 0
setup — that's harness infrastructure for the loop to *read*, not something
an experiment should touch to influence its own score.

**Out of scope for this loop**: `main.py`'s known bug (`program.md` Section 2.1) is
a one-time fix, not an experiment — fix it in the setup commit if you care
about it, not as one of the N experiments below, since it doesn't affect
`test_harness.py`'s score at all (the harness calls `converter.convert()`
directly, never `main.py`).

---

## 2. Budget: tokens, not experiment count

An experiment-count budget doesn't fit this repo. On the first real
baseline run here (2026-09-18, Groq `openai/gpt-oss-120b`, all 3 domains),
a single `test_harness.py` pass used **~199,000 of a 200,000 tokens-per-day
(TPD)** quota — one run came within a few thousand tokens of the *entire
daily* limit. A count-based budget like "15 experiments" would have burned
the whole day's quota on experiment #1 and failed silently on experiment #2
with a 429. Budget on tokens instead:

1. **Know your provider's cap.** For Groq's on-demand free tier this has
   been a TPM (tokens/minute) *and* TPD (tokens/day) limit — both showed up
   in practice (`program.md` Section 2.2's stale rows had a TPM 413, the fresh
   baseline hit the TPD cap). Anthropic and paid tiers will have different,
   usually higher, numbers — check whichever provider `client.py._provider`
   is actually set to before assuming 200k.
2. **Track cumulative usage as you go.** After every `test_harness.py` run,
   its printed `Total tokens used this run: N` line (and the `tokens_used`
   column it appended to `results.tsv`) tells you exactly what that
   experiment cost — no estimating.
3. **Stop with headroom, not at the wall.** Keep a running sum of
   `tokens_used` across every experiment this session. Stop starting new
   experiments once that sum plus one more expected run (~`T_prev` tokens,
   from Section 0.7, re-measured after each kept experiment since retries change
   the cost) would cross **~90% of your daily cap** — hitting the wall mid
   pipeline-run wastes the retry budget on 429s instead of failing cleanly
   between experiments.
4. **Shrink footprint if you need more experiments per session**, in this
   order of preference (least to most invasive):
   - `test_harness.py --domains <name>[,<name>...]` scores a subset instead
     of all of `eval_sops/`, roughly dividing cost by however many domains
     you drop. Useful once you have a hypothesis that's domain-specific.
   - `max_tokens` per call caps completion length, but it's **not one global
     knob** — planner/schema use `client.py`'s default (2000, they only ever
     emit short JSON), while `codegeneration_agent.py` (3000) and
     `validation_agent.py` (3500) override it higher because their JSON can
     carry a full `corrected_code` field up to `MAX_CODE_LINES = 500`. A
     first attempt at lowering the global default to 2000 for everyone
     truncated the validator's response mid-JSON on a real run (see
     `experiment_log.md` / this file's git history) — don't repeat that;
     only lower the planner/schema default further, and only after
     confirming their outputs aren't close to whatever cap you pick.
   - `MAX_TEST_ROWS` in `test_harness.py` (3 as of this setup) only affects
     local pandas lookups, not token spend — don't touch it for budget
     reasons, only for wall-clock ones.
5. Still keep a **hard stop at 5 consecutive experiments with no kept
   improvement**, independent of token budget — if the pipeline isn't
   improving, spending more tokens on the same hypothesis space won't help.
6. **Target score: stop early on success, not just on exhaustion.** Set
   `S_target = 0.6` (mean `row_pass_rate` across domains). Check it after
   every kept experiment, same place you check the token sum in step 3 —
   there's no reason to keep spending tokens once the pipeline is already
   good enough. Be realistic about the gap: the first real baseline here
   (2026-09-19, post-fixture-fix) was `S_prev = 0.11`. Reaching `0.6` is
   roughly a 6x improvement, not a few prompt tweaks — expect it to take
   many sessions and multiple token budgets, not one. Treat `0.6` as the
   loop's actual goal, not something to chase into diminishing returns: if
   you're well short of it and out of budget/stagnant, stopping per items 3
   or 5 above is still the right call, not a failure.

So the loop stops on the **first** of: token budget from item 3, 5
consecutive no-improvement experiments from item 5, or `S_prev >= 0.6`.

---

## 3. The experiment loop

Repeat until one of Section 2's three stop conditions is hit (token budget,
5 no-improvement in a row, or `S_prev >= 0.6`):

1. **Form one hypothesis.** One idea per experiment, even if it touches
   several files (e.g. "tighten the validator's prompt to catch missing
   None-checks" may require a matching test in `validation_agent.py` and a
   feedback-string change in `orchestrator_agent.py` — that's still one
   hypothesis). Don't bundle unrelated ideas; you can't attribute the score
   change to either one afterward.
2. **Implement it** in the editable files from Section 1 only.
3. **Commit the candidate**: `git add -- <files you changed>` (not
   `results.tsv`, not `-A`) then
   `git commit -m "experiment: <one-line hypothesis>"`.
   Committing *before* scoring matters — `test_harness.py` tags every row
   with `git rev-parse --short HEAD`, so the score can't be attributed to
   this candidate until it's HEAD.
4. **Run** `python test_harness.py` (or with `--domains` per Section 2.4 if you're
   managing token budget). It appends fresh rows to `results.tsv`, tagged
   with the commit from step 3, and prints `Total tokens used this run: N`.
5. **Score it**: `S_new` = mean `row_pass_rate` over just the rows this run
   appended. Add this run's token total to your session's running sum for
   the Section 2 budget check.
6. **Log it** — append one line to `experiment_log.md` (untracked, never
   committed) *before* any revert, so the record survives even a discard:
   `<commit>  S_prev=<x> S_new=<y>  tokens=<n>  <keep|discard>  <hypothesis>`
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

When any of the three stop conditions is hit, append a summary to the top of
`experiment_log.md`: **which condition stopped it** (token budget /
stagnation / target reached), experiments run, kept vs. discarded count,
`S_start` vs. final `S_prev`, total tokens spent this session vs. the daily
cap, and the list of kept commit hashes with their one-line hypotheses —
this is what the human reads in the morning.
