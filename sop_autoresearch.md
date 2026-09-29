# sop-to-code-agent — sop_autoresearch.md

This is the autonomous experiment loop for this repo, in the spirit of
[autoresearch-macos](https://github.com/karpathy/autoresearch-macos): point
an agent here, let it run unattended for a fixed budget, wake up to a log of
what it tried and a (hopefully) better pipeline.

Read `program.md` first — it describes the architecture, conventions, and
guardrails this loop must respect. This file only describes the loop itself.

> "Read sop_autoresearch.md and run the experiment loop."

---

## Scope: all SOPs, or a provided subset

This loop can run against **every** domain under `eval_sops/`, or against a
**provided subset** — decide which before starting, and know which one is
in effect whenever you read an `S_prev`/`S_new` number, since the two aren't
comparable to each other (a domain-subset score isn't the same quantity as
the all-domains average).

Controlled in two places, either of which can be used per run:
- **`DEFAULT_DOMAINS`** in `test_harness.py` — a persistent scope for every
  plain `python test_harness.py` call until you change it back. Set it to
  `None` for all domains, or a list like `["patient_intake_sop"]` for a
  fixed subset. This is what's actually been used through most of this
  project's history — the loop has run "all SOPs" only rarely; the working
  default has almost always been one domain at a time, deliberately, to
  control token spend while debugging that domain's specific bugs (see
  Section 2 item 4).
- **`--domains name1,name2`** on the command line — a one-off override for
  a single invocation, doesn't touch `DEFAULT_DOMAINS`. Use this to check a
  different domain without losing your current default.

Before quoting or comparing any `S_prev`/`S_new`, check which of these was
actually active for that run — the git history and `experiment_log.md`
entries record which commit was scored, not which domains were in scope at
the time, so this isn't otherwise recoverable after the fact.

### Per-domain triage (added 2026-09-27, when `video_annotation_sop` was
### onboarded as a 6th domain — `eval_sops/` also references
### `content_flagging_sop`/`video_classification_sop`/
### `warehouse_package_inspection_sop`/`aircraft_inspection_sop` in
### `master_croissant.json`'s manifest, but none of those exist as actual
### folders yet, so only 6 domains are runnable today)

When money, not just tokens-per-minute, is the binding constraint (a paid
OpenRouter-style provider with a small dollar balance rather than Groq's
free-tier daily reset), triage domains before spending anything on them:

1. **Score every domain from cache first, at zero cost**: `python
   test_harness.py --domains <all runnable domains> --test`. Any domain
   without a cached `workflow.py` yet (a never-onboarded domain like
   `video_annotation_sop` on the day it's added) can't be scored this way —
   it needs exactly one real generation before it has anything to `--test`.
2. **Skip any domain already at `row_pass_rate >= 0.8`** — don't spend
   tokens re-running or "improving" it further. `dangerous_goods_sop`
   (0.90) and `patient_intake_sop` (1.00) were already here as of
   2026-09-27; leave them alone.
3. **For every domain below 0.8, debug before generating anything.** Do the
   full static-analysis pass — read the cached `workflow.py`, the mismatch
   output from step 1's `--test` run, `tools.py`, `toolspecs.json`, and
   `sop.txt` — and identify the root cause the same way Section 0 item 7
   and this file's fix log describe (toolspec enum/casing gaps, nested
   output-shape gaps, SOP ambiguity, missing early-termination logic,
   schema-agent over/under-inclusion, etc.), entirely offline. Only spend a
   real generation once you have a specific, named fix applied — toolspec
   edit, `sop.txt` disambiguation, or an agent/prompt change — never as a
   blind "try again and see."
4. **Regenerate once, `--test` again at zero cost, decide.** If the score
   improved, keep the fix and either move to the next domain or debug the
   next-largest remaining failure cluster in the same domain. If it didn't
   improve (or regressed — single-run scores are noisy, Section 4), don't
   spend a second blind regeneration chasing the same hypothesis; either
   form a different, more specific hypothesis from the fresh mismatch data,
   or move on and come back later. `customer_service_sop` swung
   0.52 → 0.56 → 0.64 → 0.89 (best) → 0.82 → 0.82 → 0.58 across one session
   of this cycle — the fixes were real and raised the ceiling, but
   individual samples still vary a lot in an 11-step domain, so judge
   progress by the trend across several regenerations, not any single one.
5. **A domain can plateau below 0.8 for reasons prompt engineering won't
   fix.** After 2-3 rounds of debug→fix→regenerate on the same domain with
   no further real movement, that's the signal to stop and move to the next
   domain rather than keep spending — note the plateau and its likely cause
   (e.g. `customer_service_sop`'s residual `bool(auth_records)`-instead-of-
   checking-`login_status` shortcut survived three consecutive rounds of
   increasingly explicit prompt rules, which is the signature of a sampling
   habit rather than a closeable prompt gap) and revisit with a structural
   fix (e.g. a validator-side check) another day, not more prose.

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
7. **Also check that every tool's `toolspecs.json` entry documents its
   actual RETURN shape (`outputSchema`), and that its declared PARAMETERS
   actually match the real Python method signature.** Every domain touched
   so far had `outputSchema` missing entirely for some or all tools, which
   silently produces wrong generated code rather than an error: with no
   documented return shape, the generator has to guess whether a method
   returns a scalar or a dict, and guesses wrong roughly as often as right
   (`customer_service_sop`'s `validateAccount()` returns
   `{"is account id valid": bool, "reason": str}`, but generated code kept
   treating the whole dict as a bare boolean and crashing several steps
   later with "No record found" — the code was doing exactly what the
   prompt tells it to do when Returns is undocumented). The mismatch can
   run the other way too: a spec can declare a parameter the method never
   implemented (`dangerous_goods_sop`'s `assessmentFormId`), or a method can
   require a parameter the spec never declares
   (`email_intent_sop`'s `get_product_price`/`marketplace_id` — the model
   correctly refused to invent an undeclared parameter, so the toolspec was
   the actual bug, not the generated code). None of these raise a loud
   error — they surface as a confusing `TypeError` or silent wrong output
   several LLM calls deep, after real token spend.

   `test_harness.py`'s `verify_toolspec_matches_manager()` already runs this
   check automatically before every real generation and prints a warning —
   read it. When it flags something, fix `toolspecs.json` (not
   `tools.py` — the manager's actual behavior is ground truth) by adding an
   `outputSchema` block matching every field the method's `return`
   statement(s) actually produce, and/or adding any parameter the method
   signature requires that `inputSchema` is missing. This is fixture data
   (gitignored), same as item 6 — a one-time correction per domain, not an
   experiment, and not optional before trusting that domain's score.

   **`verify_toolspec_matches_manager()` only checks top-level parameter
   *names* — it has a blind spot for two narrower mismatches that are just
   as damaging and don't show up as a warning:**
   - **String field casing/enum values.** An `outputSchema` field typed
     `"type": "string"` with no `"enum"` gives the generator zero signal
     about the actual casing convention. `customer_service_sop`'s
     `checkAccountStatus` returns `"account status"` values as
     `"SUSPENDED"`/`"ACTIVE"`/`"TERMINATED"` (all caps), but the generated
     code compared against `"Suspended"`/`"Active"` (title case, a
     plausible-looking guess) — the comparison silently never matched,
     misrouting every suspended/terminated account into the "eligible"
     branch and crashing 3 steps later when it called a diagnostics tool
     with fixture data that was never meant to be reached for that account.
     Fix: add an explicit `"enum": [...]` listing every real value (get them
     with `df[col].unique()` on the domain's CSV, not by guessing).
   - **Nested object shape.** A field typed `"type": "object"` with a
     description like "parsed JSON, shape not further specified" is
     honest but useless — the generator has to guess the inner keys too.
     `customer_service_sop`'s `performTechnicalDiagnostics`/
     `executeTroubleshooting` return a `service metrics` object shaped
     `{"latency": ..., "jitter": ..., "bandwidth": ...}`, but generated
     code read it as `.get("latency_ms", 0)` / `"jitter_ms"` /
     `"bandwidth_mbps"` — a reasonable-sounding guess that was wrong. Every
     `.get(..., default)` silently returned the default instead of raising,
     so every threshold check computed against `0` instead of the real
     value — no crash, just consistently wrong `_issue` flags and a
     resolution status that never escalated when it should have. Fix: add
     a `"properties"` block to the nested object's schema entry naming its
     real keys, plus one concrete `"examples"` value pulled from the actual
     CSV data.

   Neither of these will make `verify_toolspec_matches_manager()` print a
   warning — they only surface by actually reading the generated code's
   comparisons/`.get()` calls against the tool's *real* implementation, or
   by running the full test set and noticing a suspiciously uniform wrong
   value across many rows (all-`False` or all-`True` for one field is a
   strong tell that a key lookup is silently missing, not that the SOP
   logic itself is wrong).
8. **If `client.py._provider` is a reasoning model (e.g. OpenRouter's
   `openai/gpt-oss-120b`), check every agent's `_call_with_retry` treats a
   blank/malformed LLM response as *retryable*, not a hard failure.** A
   reasoning model spends part of its `max_tokens` budget on a hidden
   `reasoning` field before emitting visible `content` — non-deterministically,
   so the same prompt can return real content on one call and an empty
   `content` on the next. All four agents (`planner_agent.py`,
   `schema_agent.py`, `codegeneration_agent.py`, `validation_agent.py`)
   originally wrapped "empty/malformed response" and "blank content" in
   their own `XAgentError`, then immediately re-raised it
   (`except XAgentError: raise`) instead of letting it fall into the
   exponential-backoff retry loop below — so one unlucky sample failed the
   entire node (and, via `agent_pipeline.py`'s `AGENT_EXCEPTIONS` handling,
   sometimes the entire pipeline run) instead of just retrying. Fixed by
   raising a plain `RuntimeError` for those two conditions instead, so they
   go through the same `except Exception` retry path as a network error.
   Applies regardless of provider, but only actually *triggers* on a
   reasoning model — a non-reasoning model's response is essentially never
   blank once the request itself succeeds, which is why this went unnoticed
   until switching providers.

   **Same fix applied to a related gap**: `validation_agent.py`'s
   `_resolve_final_code()` also had this shape — when `corrected_code` failed
   its own post-checks (the `ast.parse` syntax check, missing required
   import/pattern, disallowed import, ...), it let `ValidatorAgentError`
   propagate straight up through `__call__`, ending the *entire* pipeline
   run (via `agent_pipeline.py`'s `AGENT_EXCEPTIONS` handling) instead of
   falling back to `generated_code` — even though that fallback path already
   existed one branch over, for the "no `corrected_code` provided at all"
   case. Reproduced live during a `customer_service_sop` regeneration:
   attempt 2's `corrected_code` had an unclosed paren, and the pipeline
   ended immediately rather than reaching attempt 3. Fixed by wrapping the
   `_validate_corrected_code()` call in a `try/except ValidatorAgentError`
   that falls back to `generated_code` (which already passed
   CodeGeneratorAgent's own guardrails) — same fallback the "no correction
   provided" branch already used, just reached from one more failure path.

   **Root-caused and fixed**: the validator hallucinated a constraint that
   doesn't exist — insisting a tool call's parameter "isn't part of the
   documented signature" by comparing against the planner's `api_plan`
   (which only ever carries `step`/`task`/`tool`/`description`, no parameter
   list at all). Across 3 retries this drove the code generator to
   progressively strip a genuinely *required* parameter until the call broke
   outright. Root cause: `validation_agent.py`'s prompt was the only one of
   the four agents that never included `tools_formatted` (the real per-tool
   parameter documentation) — it had rule "parameters match the tool's
   documented parameters" with no actual documentation of those parameters
   in front of it, so it filled the gap with the only tool-shaped thing it
   *did* have (the API plan) and drew a false conclusion from it. Fixed by
   adding `tools_formatted` to the validator's prompt (matching the other
   three agents) and rewording that rule to name `tools_formatted` as the
   only source of truth, explicitly noting the API plan's silence on a
   parameter isn't evidence anything is wrong.
9. **At larger tool counts (this repo's ceiling so far: 26 tools,
   `video_annotation_sop`), LLM-based enumeration degrades — replace it with
   deterministic code wherever the check is mechanical.** Two concrete
   instances found the same day `video_annotation_sop` was onboarded:
   - `schema_agent.py` asking the model to "list every tool's parameters and
     check what's covered by an earlier Returns" (Section 0 item 8's
     `_build_prompt`) works fine at ~10 tools but produced a schema with
     **invented parameter names that don't exist anywhere in the toolspec**
     at 26 tools, and separately missed several real ones on a different
     attempt. Fixed by adding `_compute_parameter_checklist()`: a plain
     Python function that collects every distinct parameter name required
     by the tools actually in the plan (and every distinct Returns field
     name across those same tools) and hands the LLM that exact list to
     classify, instead of asking it to recall the list from prose. Turns
     "remember N names from a wall of text" (degrades with N) into "sort
     each name in this list into one of two buckets" (doesn't).
   - `verify_toolspec_matches_manager()` (item 7) checked parameter *names*
     matched between toolspec and method signature, but had no way to
     notice that **20 of `video_annotation_sop`'s 26 tool methods were bare
     `pass` stubs** — a docstring plus `pass`, silently returning `None`
     forever. Signature and toolspec matched perfectly on all 20, so every
     existing check passed while 77% of the domain's tools did nothing.
     Only actually calling a method, or reading its source, revealed it.
     Fixed by adding an `ast`-based check to the same function: parse each
     method's source, and if its body is just a docstring followed by a
     single `pass` statement, warn. Like the rest of this function, it's a
     `tools.py`-is-ground-truth check — when it fires, implement the real
     method (matching the pattern of whichever sibling methods in the same
     file already work: load the CSV, filter by `video_id` + this method's
     own parameter(s), raise on empty/multiple matches, return the matched
     row's relevant fields), not a fixed suggestion to apply blindly.
10. **Any tool parameter typed `int`/`float`/`bool` needs to be cast before
    use inside the tool, not assumed to already be that type.** `input_data`
    passed into `workflow()` is always raw CSV-cell strings (from
    `csv.DictReader` in `test_harness.py`, or literally typed text from a
    real caller) — `pandas`' `==` does **not** coerce `"8" == 8` or
    `"True" == True` across a string and a numeric/bool dtype column, both
    silently evaluate to `False` for every row, and the tool raises "no
    matching record found" instead of a clear type error. Found in
    `video_annotation_sop`'s `runAutomatedQC`/`performHumanValidation`,
    both of which compared a raw-string `predicted_iou` against a `float64`
    CSV column and could never match. Fix at the tool boundary, not in the
    generated code: `predicted_iou = float(predicted_iou) if not
    isinstance(predicted_iou, float) else predicted_iou` right after the
    existing null/required-param guard, for every numeric or boolean
    parameter a tool's lookup filters on — this makes the tool robust
    regardless of what type the caller happens to pass, which is more
    reliable than trying to get every future code-generation to remember to
    cast every numeric field itself.
11. **`client.py`'s LLM clients need a `timeout=`, and even that doesn't fully
    solve unattended runs on a laptop that sleeps.** Originally none of the
    three provider branches (`Groq`, `OpenAI`, `Anthropic`) set a request
    timeout, so a connection killed mid-flight (the machine sleeps) hung
    forever — observed directly as a `test_harness.py` run sitting at 0%
    CPU for **9+ hours** with no log output, requiring a manual `kill`.
    Fixed by adding `timeout=120.0` to all three client constructors, so a
    dead connection raises and falls into the existing retry loop instead of
    blocking indefinitely. This is necessary but **not sufficient** for a
    laptop that sleeps repeatedly across a long unattended run: reproduced
    again the same session — the timeout correctly caught the *first* hang
    ("Request timed out... Retrying in 2s" appeared in the log), but the
    retry's own connection hit a *second* sleep cycle and hung again for
    hours with no further log output, past the point a 120s timeout should
    have fired. This matches a known class of problem where a torn-down-and-
    rebuilt network interface after wake doesn't always surface as a clean
    socket error to an HTTP client sitting on an already-established
    connection — the timeout catches a fresh connection attempt reliably,
    less so a read stalled on a connection that was fine when opened. Two
    practical mitigations, neither a full fix: (a) wrap long unattended
    background runs in `caffeinate -i` to prevent idle sleep for the
    run's duration; (b) if a background run shows 0% CPU and no log growth
    for much longer than expected, check `pmset -g log | grep -i wake` for
    a wake event around when it stalled — if found, just `kill` and re-run
    rather than waiting longer, since it won't recover on its own once in
    this state.
12. **CRITICAL — `test_harness.py`'s own scoring loop had two bugs that
    silently *undercounted correct answers*, retroactively invalidating
    every `row_pass_rate` number recorded before 2026-09-28 for any domain
    with a list/array-shaped or a numeric scored output field.** Found while
    onboarding `warehouse_package_inspection_sop` (whose `problem_type`
    field is a list) — after fixing both, `customer_service_sop` went
    0.83→1.00, `dangerous_goods_sop` 0.90→1.00, `email_intent_sop`
    0.95→1.00, `video_annotation_sop` 0.83→1.00, and
    `warehouse_package_inspection_sop` 0.67→1.00, all on already-cached,
    completely unchanged `workflow.py` files — these domains had been
    correct the whole time and the harness was wrongly marking them wrong.
    Both bugs live in the `row_ok = all(...)` loose-match check:
    - **List/array ground truth never matched.** A CSV cell holding a
      stringified list (e.g. `"['Wrong Item']"`) was compared via exact
      string equality against `flatten_values(actual)`'s leaves — but
      `flatten_values` recurses INTO a real list and yields `'Wrong Item'`
      (no brackets), never the bracketed string itself, so this check could
      never pass for a list-shaped field regardless of correctness. Fixed
      by detecting a `[`/`{`-prefixed expected string, `ast.literal_eval`-
      parsing it, and requiring each of ITS OWN flattened elements to
      appear in `actual_values`, instead of the whole bracketed string.
    - **Numeric formatting differences never matched.** `"0.0" == "0"` is
      `False` as strings, so a workflow that defaults an unused numeric
      field to a bare `0` instead of the ground truth's `0.0` failed an
      otherwise-fully-correct row. Fixed by also building a set of
      `float()`-converted leaves from `actual` and accepting a numeric
      match (`float(expected) in actual_numbers`) alongside the string one.

    **Implication for anyone reading `experiment_log.md` or old `git log`
    commit messages from before this fix**: any `S_prev`/`S_new` recorded
    against a domain with a list-shaped or numeric output field understates
    the true score, sometimes substantially — don't trust those numbers at
    face value; re-run `--test` against the domain's current cached
    `workflow.py` to get a corrected reading before assuming a past
    "improvement" or "regression" was real. This also means some of the
    earlier debugging sessions recorded in this file chasing "wrong output"
    bugs may have partly been chasing a scoring artifact instead of (or in
    addition to) a real generation bug — the specific fixes described
    elsewhere in this file (toolspec/SOP/agent changes) were still real and
    still correct, they just weren't getting full credit until now.
13. **Known unsolved failure mode: the validator's own "every API-plan step
    must be implemented" bias can override a genuinely-correct conditional
    skip, no matter how explicitly the SOP states the condition.**
    `video_classification_sop` (24 tools) needs `submitContentModeration`/
    `implementModeration` called ONLY when escalation is actually triggered
    (`detected_categories` non-empty) — calling them unconditionally crashes
    every non-escalated row, since `moderator_id` is genuinely blank/unset
    for those cases in the source data. Disambiguating the SOP to say this
    explicitly (three escalating rounds of increasingly forceful wording —
    up to "MANDATORY, NON-NEGOTIABLE CONDITION... a hard runtime failure,
    not a style preference") never stuck: the validator's own feedback kept
    independently re-asserting "steps 8-24 are missing, call every listed
    tool" each retry, and the code generator kept capitulating to the
    validator's complaint over the SOP's conditional instruction — a
    genuine tug-of-war between two agents reading the same SOP differently,
    not a one-sided prompt gap. Domain plateaued at 0.00-0.33 (0.33 on one
    lucky sample) across 7 regenerations. Not pursued further this session
    per item 5 above (2-3 rounds with no movement → stop). A real fix here
    likely needs a change to `validation_agent.py`'s own prompt (teach it
    that a step legitimately absent from generated code because its
    trigger condition wasn't met is not the same defect as a step omitted
    by oversight) rather than more SOP wording — flagging so the next
    session doesn't re-walk the same three rounds of SOP escalation.
14. Run `python test_harness.py` once, untouched, to get the real baseline.
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

1. **Know your provider's cap — and whether it even has a daily one.** For
   Groq's on-demand free tier this has been a TPM (tokens/minute) *and* TPD
   (tokens/day) limit — both showed up in practice (`program.md` Section
   2.2's stale rows had a TPM 413, the fresh baseline hit the TPD cap).
   Check whichever provider `client.py._provider` is actually set to before
   assuming 200k — it won't always apply:
   - **Groq**: fixed TPM + TPD, as above. The 200k figure below is this
     tier specifically.
   - **OpenRouter**: no fixed daily token quota at all — it's pay-as-you-go
     against account credits, with per-model rate limits instead of a TPD
     number. "90% of your daily cap" in item 3 has no direct equivalent
     here; substitute a **spend limit** (check credit balance before and
     after a session) or a **self-imposed per-session token ceiling** (pick
     a round number like 100k and treat it the same way item 3 treats 90%
     of TPD) — either works, just pick one before starting so the loop has
     an actual stop condition instead of running until the account runs dry.
     Concrete reference point from this project's own account (2026-09-27):
     `openai/gpt-oss-120b` via OpenRouter runs about **$0.12 per 1M tokens**
     — a $5 balance is roughly 40M tokens, which is generous relative to a
     single domain's regeneration cost (25k-95k tokens per
     `customer_service_sop` run this session) but still finite across many
     domains × many debug-fix-regenerate cycles (the "Per-domain triage"
     section above). Don't let "40M tokens sounds huge" turn into skipping the
     free `--test`-first triage discipline — it's still the difference
     between spending on a targeted fix and spending on a blind re-roll.
   - **Anthropic / paid tiers generally**: usually higher numbers than
     Groq's free tier, but check the account's actual limits rather than
     assuming — don't carry the 200k figure over to a different provider
     just because it's what's written here.
2. **Track cumulative usage as you go.** After every `test_harness.py` run,
   its printed `Total tokens used this run: N` line (and the `tokens_used`
   column it appended to `results.tsv`) tells you exactly what that
   experiment cost — no estimating.
3. **Stop with headroom, not at the wall.** Keep a running sum of
   `tokens_used` across every experiment this session. Stop starting new
   experiments once that sum plus one more expected run (~`T_prev` tokens,
   from Section 0 item 14, re-measured after each kept experiment since retries change
   the cost) would cross **~90% of your daily cap** (item 1's TPD figure on
   Groq; your chosen spend limit or self-imposed session ceiling on
   OpenRouter/providers with no fixed daily quota) — hitting the wall mid
   pipeline-run wastes the retry budget on 429s instead of failing cleanly
   between experiments.
4. **Shrink footprint if you need more experiments per session**, in this
   order of preference (least to most invasive):
   - `test_harness.py --domains <name>[,<name>...]` scores a subset instead
     of all of `eval_sops/`, roughly dividing cost by however many domains
     you drop. Useful once you have a hypothesis that's domain-specific.
   - `max_tokens` per call caps completion length, but it's **not one global
     knob**, and its right value is provider-dependent, not just
     domain-dependent. As of this writing: `planner_agent.py` and
     `schema_agent.py` explicitly set 3000 (their JSON can run past
     `client.py`'s bare default of 2000 for a multi-step plan or a
     many-parameter schema); `codegeneration_agent.py` and
     `validation_agent.py` both use 8000, because their JSON can carry a
     full `generated_code`/`corrected_code` field up to
     `MAX_CODE_LINES = 500`. Check the actual values in each file before
     trusting these numbers — they've moved every time the provider or a
     hard domain (`customer_service_sop`) forced a change, and will keep
     moving. **On a reasoning-model provider (e.g. OpenRouter's
     `openai/gpt-oss-120b`), budget generously**: part of `max_tokens` gets
     spent on a hidden `reasoning` field before any visible `content`
     appears, non-deterministically, so a cap that was fine on a
     non-reasoning model can silently return blank `content` on this one
     (see Section 0 item 8) — that failure mode looks like a hang or a
     retry storm, not an obvious truncation, so it's easy to misdiagnose as
     a prompt problem instead of a token-budget one. A first attempt at
     lowering the global default to 2000 for everyone truncated the
     validator's response mid-JSON on a real (pre-reasoning-model) run (see
     `experiment_log.md` / this file's git history) — don't repeat that on
     any provider; only lower an agent's `max_tokens` after confirming its
     real output length with a `--test` re-score, not by guessing.
   - `MAX_TEST_ROWS` in `test_harness.py` (3 as of this setup) only affects
     local pandas lookups, not token spend — don't touch it for budget
     reasons, only for wall-clock ones.
   - `test_harness.py --test` costs zero tokens by design, but it's not a
     lever for running more *experiments* — it re-scores whatever's already
     saved at `eval_sops/<domain>/workflow.py` (written after every real
     run) without touching the LLM, for hand-editing and re-checking a fix
     idea before spending tokens on a real generation. It deliberately does
     not write to `results.tsv`, since cached code isn't tied to the
     current commit — don't use it to produce a `S_new` for keep/discard.
5. Still keep a **hard stop at 5 consecutive experiments with no kept
   improvement**, independent of token budget — if the pipeline isn't
   improving, spending more tokens on the same hypothesis space won't help.
6. **Target score: stop early on success, not just on exhaustion.** Set
   `S_target = 0.9` (mean `row_pass_rate` across domains). Check it after
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
   committed) *before* any revert, so the record survives even a discard.
   Include the domain scope (per the section above) — it's otherwise
   unrecoverable from git history alone:
   `<commit>  domains=<all|name1,name2,...>  S_prev=<x> S_new=<y>  tokens=<n>  <keep|discard>  <hypothesis>`
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
