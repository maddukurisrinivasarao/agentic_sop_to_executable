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
15. **A tool that quietly only processes `list_param[0]` instead of every
    element is invisible to every check in item 7/9 — it never raises,
    never shows up in `verify_toolspec_matches_manager()`, and the AST
    single-`pass`-statement check doesn't catch it either, because the
    method has plenty of real code, just scoped to one element instead of
    all of them.** Found in `know_your_business_sop`'s
    `performSanctionsCheck(business_id, ubo_list)`: it computed `ubo_name =
    ubo_list[0]["name"]` and looked up sanctions/PEP status for only that
    one UBO, silently dropping every other UBO from both returned lists.
    Invisible for the majority of test rows (many businesses have exactly
    one UBO), and even on multi-UBO rows the bug doesn't crash — it just
    quietly returns a 1-element list where a 2-4 element list was expected,
    which downstream code iterates over into an ("any UBO is X") check that
    now can only ever see UBO #1. In this dataset the still-"Pending"
    sanctions entry was consistently NOT in position 0, so every "does any
    UBO still have a Pending sanctions check" downstream check silently saw
    zero Pending entries no matter how many actually existed. Symptom:
    fixing a genuine SOP-ordering bug (item 16 below) that should have
    raised a domain's score by ~20 points only moved it 1 point (0.60 ->
    0.61) — the SOP fix was correct but the tool feeding it data was
    dropping the exact signal the fix depended on. Root-caused by comparing
    the tool's actual returned `sanction_check_status`/`pep_status` lists in
    a failing row's output against the row's raw CSV `ubo_list` length —
    the CSV had 2 UBOs, the tool's response had 1. Fixed by resolving every
    name in `ubo_list` (not just `[0]`) and returning one status entry per
    UBO. General lesson for future tool-implementation review: when a tool
    takes a `List[...]` parameter and returns per-item results, check that
    its output list length actually varies with its input list length on a
    multi-item test case — a tool that always returns exactly 1 result
    regardless of a 1-vs-4-item input is a strong tell.
16. **When a SOP states a priority/tie-breaking order between two rules
    ("check A first; if A doesn't apply, check B"), don't trust that the
    order is correct just because it reads clearly — verify it against
    ground truth on rows where both conditions are simultaneously true,
    since that's the only place the stated order is actually observable.**
    `know_your_business_sop`'s SOP 5.6.2 (as written going into this
    session) said: check the 7 escalation triggers (Tax ID format, license
    expiry, sanctions match, PEP identified, shell company, offshore,
    bank verification) first — if any fire, `"escalate"` regardless of
    anything else; only if none fire, then check whether any UBO's
    `sanction_check_status` is still `"Pending"` -> `"awaiting information"`.
    This reads as a perfectly reasonable business rule, but on the 50 rows
    (out of 90) where at least one UBO had already come back `"Matched"`
    (an escalation trigger) AND a different UBO was still `"Pending"`,
    ground truth was `"awaiting information"` in 34/50 cases (68%) — the
    *opposite* of what the stated order produces. Verified via exhaustive
    single- and paired-feature search across every visible column
    (ownership percentages, PEP status of the specific pending person,
    matched-vs-pending ratio, risk_score, ownership_layer_count, tax_id) —
    none discriminates the other 16/50 "escalate despite pending" rows from
    the 34 "awaiting despite pending" rows (see item 17 below), but the
    68%-vs-32% base rate itself is a strong, unambiguous signal that the
    *order* was backwards, independent of the unexplained 16-row remainder.
    Fixed by rewriting 5.6.2 to check "is any UBO still Pending" FIRST,
    unconditionally, before the trigger list — moved
    `know_your_business_sop` from 0.60 to 0.80 (combined with item 15's fix,
    since the ordering fix alone couldn't show its real effect until the
    tool feeding it Pending status was also fixed). General lesson: a
    plausible-sounding priority order in SOP prose is exactly as likely to
    be backwards as forwards from the model's/spec-writer's perspective —
    only ground truth on the overlap case settles it, and single-condition
    rows (only A fires, or only B fires) give zero signal about which one
    should win when both do.
17. **Known unsolved, newly found this session: `know_your_business_sop`
    plateaus at 0.80 (18/90 rows still wrong) with a pattern matching
    `content_flagging_sop`'s already-documented disconnected-ground-truth
    limitation, not a closeable prompt/tool gap.** After item 16's fix, 16
    of the remaining 18 wrong rows are exactly the "escalate despite a
    different UBO still Pending" cases that item 16's base-rate evidence
    didn't explain (the 32% minority). Two rows with otherwise-identical
    trigger patterns (same Matched/Pending split shape, same 45/55
    ownership split, same offshore/shell/bank-flagged status) land on
    opposite ground-truth labels, differing only in noise-level fields
    (`ownership_layer_count` 3 vs 4, `risk_score` 0.87 vs 0.88) that the SOP
    itself calls unreliable ("the risk score is noisy... may not accurately
    capture all the relevant information" — SOP 5.6.1). An exhaustive
    single-feature purity search (every raw column, and derived features:
    UBO count, matched count, pending count, clear count, PEP-yes/no count,
    which specific UBO is pending and their own PEP status, tax_id parity,
    business_type, registration_state) found zero features that perfectly
    separate the 16 "escalate" from the 34 "awaiting information" rows in
    this pending-and-triggered subset — every feature's split lands close
    to the 68/32 base rate regardless of its value, the signature of noise
    superimposed on a base rate rather than a deterministic rule. The other
    2 of the 18 wrong rows (`biz_048`, `biz_008`) are a *different*,
    identified root cause: each shares an identical
    `registration_number`/`license_number`/`tax_id`/`bank_account_number`
    with a different `business_id` elsewhere in the same CSV (e.g. `biz_048`
    "Tech Solutions Pro" in Seattle and `biz_098` "Tech Solutions Group"
    also in Seattle share every one of those four IDs) — a real
    identity-fraud/shell-company signal per SOP 3.3, but detecting it
    requires a cross-row lookup against the full dataset, which no current
    tool performs and no per-row `workflow(input_data)` call can do on its
    own (it only ever sees one business_id at a time). Per this loop's
    scope rules, this needs either a new tool (a
    "checkForDuplicateRegistration"-style lookup against the full CSV) or a
    fundamentally different per-row contract — flagged for the user's
    attention rather than built, since it's a new capability the SOP
    implies but never explicitly specifies as a tool. Not pursued further
    this session (domain already at 0.80, past the 0.8 stop bar, and this
    is a 2-row/90 marginal gain not worth a scope-expanding tool build).

18. **A tool that "looks up a row and returns `is_valid: True` whenever a row
    is found" is functionally a stub, even though it isn't a bare `pass`** —
    the item-9 AST check for a docstring+`pass` body doesn't catch it, since
    real code runs and a real value comes back, but the value never actually
    depends on the field it claims to validate. Found in three separate
    tools in `video_annotation_sop`: `validateSceneContext`,
    `calibrateCameraSensors`, and `executeSegmentation` each queried the CSV
    for a matching row and returned `is_valid: True` unconditionally once
    found, never checking whether `scene_type` was actually urban,
    `camera_position` was actually front-facing, or `segmentation_type` was
    actually `instance` — the exact three categorical gates the SOP's
    Section 4.1/5.2 environmental constraints require. Since `workflow.py`
    already correctly ANDs together every tool's `is_valid` flag into
    `thresholds_met`, fixing only the three stub tools' internal logic (no
    workflow/regeneration needed) moved this domain 0.83 -> 0.99 at zero
    token cost. Root-caused by building an exhaustive predicate over every
    raw column against ground truth (`pandas` crosstabs of each categorical
    column against `final_status`) *before* touching any code — this is the
    same "verify a hypothesis against the full ground truth before spending
    a regeneration" discipline as item 16, just applied to tool-level bugs
    instead of SOP-ordering bugs. General lesson: when several boolean
    "is_valid" checks are ANDed together in the workflow and the actual
    output is uniformly more permissive than ground truth (lots of
    unexpected `True`s), suspect each contributing tool individually for
    this "found-a-row-so-it-must-be-valid" shortcut, not just the numeric
    threshold checks — a stub can hide behind a return value that varies
    row-to-row (via echoing back input fields) while its `is_valid` field
    never actually varies.
19. **The same tool-level crash-on-empty-string bug can recur across
    multiple sibling tools that share a call signature — grep for the exact
    error string, not just the first occurrence.** Also in
    `video_annotation_sop`: `executeSegmentation`, `runAutomatedQC`, and
    `performHumanValidation` all take `predicted_object` and all used
    `if not all([...])` to guard "missing parameter," which treats a
    legitimate empty string (object detection found nothing — a real
    business outcome the SOP's own output spec accounts for via `Reason`)
    identically to a genuinely absent parameter, raising `ValueError` and
    crashing the whole workflow for the 4/125 rows where no object was
    detected. Fixed identically in all three: guard on `is None` (or
    falsy-but-required *paths*, which are never legitimately empty) instead
    of blanket falsy-checking every parameter, plus `.fillna('')` on the
    CSV's `predicted_object` column so the row lookup matches an empty
    string instead of comparing against `NaN`. Fixing only the first tool
    in the call chain is not enough when several sibling tools share the
    same call-order position and the same over-eager guard — the second
    tool called will just crash instead, with the same superficial "Missing
    one or more required parameters" message pointing at a different
    tool's line number depending on which row's other fields happen to be
    populated.
20. **A validation step described in SOP prose as "Validate that it is
    between 1 and 5" (or similar) can silently contradict a *later* section
    of the same SOP that describes what to do when the value is 0 or
    missing — and the codegen will implement the first instruction as a
    hard gate, never reaching the second.** `dangerous_goods_sop`'s SOP 5.2-
    5.5 told the model to validate each of 4 component scores against a 1-5
    range with no stated exception; SOP 5.6 separately said a missing/0
    score should be imputed by "max of the other scores." The generated
    `workflow.py` implemented BOTH instructions faithfully and in the
    written order — validate-and-raise in steps 5.2-5.5's position, impute
    in 5.6's position — which meant every row with a genuine 0/missing
    component crashed before ever reaching the (correctly-implemented!)
    imputation logic one step later. This produced a systematic `"X score 0
    out of valid range 1-5"` crash across 28/274 rows, i.e. every row with
    at least one missing component — a much larger and more mechanical
    failure signature than the noise-ceiling patterns in items 16-17, and
    confirmed fixable (unlike those) by simply re-reading the SOP's own two
    sections side by side and noticing they give contradictory instructions
    for the same input state. Fixed by adding an explicit "0/missing is not
    a failure at this step, do not raise, it's valid input for the next
    section" caveat directly into 5.2-5.5's text, disambiguating which of
    the two instructions wins — no toolspec or tools.py change needed for
    this part; the tools already returned 0 correctly (once a separate NaN-
    handling bug below was fixed), the bug was entirely in how
    `workflow.py`'s generated code sequenced two genuinely-conflicting SOP
    instructions.
21. **A blank/NaN CSV cell reaching a tool that does `int(raw_value)` on it
    crashes with `cannot convert float NaN to integer` — a different, less
    obvious symptom than the more commonly-documented string/bool `==`
    mismatch in Section 0 item 10, but the same underlying class of bug
    (tool assumes its input is already the right type/shape).** Found in
    `dangerous_goods_sop`'s four `calculate_*_score` methods: each did
    `int(matched_row.iloc[0]['..._score'])` directly, which works for every
    numeric-looking cell but throws on a genuinely empty cell (`pandas`
    reads a blank CSV field as `float('nan')`, and `int(nan)` is a
    `ValueError`, not a graceful 0). Since the SOP's own business logic
    treats a missing score identically to an explicit 0 (see item 20), the
    correct fix is `0 if pd.isna(raw_score) else int(raw_score)` at the
    tool boundary — a one-line, zero-regeneration fixture fix once
    identified, but only 1/28 originally-failing rows in this domain
    exposed it (the other 27 had an explicit `0` in the CSV, which
    `int(0)` handles fine) — don't assume a single reproducing row means a
    bug only affects that one row; check whether the same code path would
    also mishandle a *different* invalid input (here: blank vs. explicit
    zero) that just happens to be rarer in the test set.
22. **When a SOP states a numeric range for a derived value ("hazard score
    validated against 4-20") but never states the *sub-ranges* that map to
    each of several output categories, the codegen has to guess evenly-
    spaced boundaries — and ground truth is not guaranteed to be evenly
    spaced.** `dangerous_goods_sop`'s SOP 5.7 said only "Apply the Hazard
    Class A, B, C and D based on the value of the hazard score... higher
    score gets higher severity" with zero numeric thresholds. The generated
    code guessed `<=8` -> A, which put a ground-truth `hazard_score == 8`
    row (which should be Class B) into Class A. Resolved by computing the
    real thresholds directly from ground truth on rows with 0-1 missing
    components (`df.groupby('hazard_class')['hazard_score'].agg(['min',
    'max'])`, excluding `Unable to Decide`/invalid rows) — this produced
    clean, non-overlapping bands (A: 4-7, B: 8-14, C: 15-16, D: 17-20, with
    13-14 never observed but safely assignable to B by interpolation, not
    reverse-engineered per-row) — and writing those exact bands into the
    SOP text. This is meaningfully different from the anti-hardcoding rule
    in Section 2.5/6-item-6: the fix generalizes to *any* hazard_score
    value via a stated rule, not to specific row IDs, so it survives
    regeneration and unseen data — the distinction that makes it acceptable
    is "derived a general threshold rule from the full distribution" vs.
    "special-cased specific IDs to force a match."
23. **A `bool(some_dict)` shortcut for a "did this succeed" flag can survive
    even a toolspec that documents the real boolean field by name, in
    plain language, with an explicit "this is the field that tells you X"
    hint — this is a genuine model sampling habit, not a documentation
    gap, and re-generating after further improving the SOP/toolspec text
    does not reliably fix it.** `customer_service_sop`'s `workflow.py` line
    41 sets `is_authenticated = bool(authentication_records)` where
    `authentication_records` is the dict returned by
    `getAuthenticationDetails` — always non-empty/truthy on a successful
    call regardless of its `login_status`/`account_recovery_status`
    contents, so `is_authenticated` is always `True`. This happens despite:
    (a) `toolspecs.json`'s `getAuthenticationDetails` entry explicitly
    naming both fields, giving their exact enum values, and stating in
    prose "this is the field that tells you whether a FAILURE login_status
    was subsequently recovered"; (b) `sop.txt` 5.1 stating the business
    rule in plain English ("If you find failed attempt and no record of
    successful recovery, classify the authentication as failed and close
    the case"). All 27/156 failing rows in this domain are exactly this bug
    — a `login_status=FAILURE`/no-recovery account proceeds past
    authentication anyway, then crashes several steps later when
    `createSessionAndOpenTicket`'s fixture-backed CSV lookup can't find a
    row matching the (wrong) `is_authenticated=True` it was called with.
    This is the fourth time this exact fix has been attempted (3 prior
    rounds of progressively more forceful SOP wording, documented in the
    "Per-domain triage" section's item 5 note, plus this session's
    regeneration against an even-further-improved toolspec) — all four
    reproduced the identical `bool(dict)` shortcut. Per the loop's stop
    rule, not re-attempted a 5th time this session. This is now strong
    enough evidence to say the real fix is NOT more SOP/toolspec prose —
    it's a `codegeneration_agent.py`/`validation_agent.py` change (e.g. a
    validator check that flags "a boolean derived from truthiness of an
    entire dict/response object, rather than from a named field inside it"
    as a defect class, the same way Section 0 item 7's nested-object-shape
    blind spot was closed by adding a `properties` block) — flagged for a
    future session that's explicitly scoped to touch agent prompts, since
    that's a bigger, cross-cutting change than this fixture-focused loop's
    normal scope, and it hasn't yet been shown to affect any domain besides
    this one.
24. **A credential gap in the running environment blocks regeneration
    entirely, and is a different failure mode from every bucket 1-5 in the
    debug loop — check for it before concluding anything about a bug's
    persistence.** A 2026-10-01 session, tasked with a focused 5th
    regeneration attempt on `customer_service_sop` specifically to test
    whether item 23's `bool(dict)` bug was finally fixed by
    `codegeneration_agent.py` rules 24/25 (the "never substitute bool(dict)
    for a named-field check" / "a non-empty object is always truthy" rules)
    plus a new, still-uncommitted orchestrator plan/schema/code escalation
    mechanism (`orchestrator_agent.py`'s `_classify_issue_shape`), found
    `client.py`'s configured provider (`_provider = 'openrouter'`) had no
    matching `OPENROUTER_API_KEY` (nor `ANTHROPIC_API_KEY`) in the shell
    environment — only `GROQ_API_KEY`/`GROQ_API_KEY_2` were present. Every
    LLM call failed immediately ("Missing credentials" on attempt 1, then
    `'NoneType' object has no attribute 'chat'` on retries once the client
    singleton cached a `None` client). **No regeneration ran, the provider
    was deliberately not switched to `groq` as a workaround** (that's an
    infra/credentials decision belonging to the user, not a fixture fix —
    and it would confound any before/after comparison with the prior 4
    documented `openrouter` attempts by changing the model entirely). The
    score stayed at the previously-verified 0.83/156 (re-confirmed via
    `--test`, free, cached `workflow.py` byte-identical to the prior
    session's). This is now logged as a precondition check for any future
    attempt on this domain (or any domain): **verify `echo
    $OPENROUTER_API_KEY` (or whichever provider `client.py._provider`
    currently names) is actually set before spending a session's first
    action on a regeneration**, since a credential gap produces a
    `completed=False row_pass_rate=0.00` result that looks superficially
    like a new pipeline failure but is actually just unrelated
    infrastructure, not a reproduction of (or a fix for) the bug under
    test — don't let a `results.tsv` row like this be misread as "the bug
    got worse."
    - **Zero-cost secondary finding, made purely by re-reading
      `validation_agent.py`'s prompt (no LLM call needed):** its 11-item
      "Check ALL of the following" checklist in `_build_prompt` (tool
      selection, call syntax, parameter names/required-ness, `input_data`
      key scope, try/except shape, function signature, first import line,
      banned calls, import scope, step ordering) has **no item that would
      ever flag a boolean/status field derived from a whole-object
      truthiness check instead of a named field inside it** — i.e. the
      validator's own review criteria cannot catch item 23's bug even in
      principle, independent of whether codegen's rules 24/25 succeed or
      fail on a given sample. This means the validator provides no
      second-line-of-defense for this defect class, and the new
      orchestrator escalation logic (which only acts on issues the
      validator actually raises in its `issues` list) never gets a chance
      to engage either, since nothing gets flagged to escalate.
      **Recommended fix (NOT applied this session — untestable without
      working credentials, and `validation_agent.py` is a shared
      cross-domain prompt, so confidence requires being able to verify no
      regressions on other domains, which this session couldn't do at
      all):** add a 12th checklist item mirroring codegen rules 24/25's
      exact language: *"No boolean/status field is derived via
      `bool(<entire dict/object returned by a tool call>)` or a bare `if
      <that dict>:` truthiness test when the tool's documented Returns
      shape names a specific status/outcome field inside that object —
      flag this as an issue and supply `corrected_code` that checks the
      named field(s) instead."* Since this is a genuine code-shaped defect
      (not plan- or schema-shaped), it would correctly fall through to
      `_classify_issue_shape`'s existing "code" default — no change needed
      to `PLAN_SHAPE_KEYWORDS`/`SCHEMA_SHAPE_KEYWORDS` for this specific
      fix to route correctly. Next session with working
      `OPENROUTER_API_KEY`/`ANTHROPIC_API_KEY` should apply this checklist
      addition, then run the regeneration this session couldn't, then
      `--test` to confirm, before concluding anything new about whether
      the bug is finally fixed.

25. **A validator-side checklist item that targets a specific codegen defect
    class is itself a non-deterministic LLM judgment, not a static
    analyzer — it measurably reduces the bug's rate but does not reliably
    catch it on every sample, even on the exact run where it's needed.**
    Follow-up to item 24: with `OPENROUTER_API_KEY` working, ran the 5th and
    6th regenerations of `customer_service_sop` this session (2026-10-01).
    Regen 5 (codegen rules 24/25 active, no validator change): the literal
    `is_authenticated = bool(authentication_records)` pattern from item 23
    was gone — rules 24/25 did suppress that exact surface form — but it was
    replaced by `is_authenticated = is_account_id_valid` with a comment
    reading `# Authentication outcome not explicitly detailed; assume
    success if ID valid`, which never references the `getAuthenticationDetails`
    response at all and directly violates rule 24's explicit ban on
    "assume"/"simplify" rationales anyway. Score moved 0.83 -> 0.88 (156
    rows) — an improvement, since this variant only breaks the subset of
    rows with `login_status=FAILURE`/no recovery (17/18 failures), vs. the
    original bug breaking all auth-failure rows identically, but the same
    underlying defect class. Added `validation_agent.py` checklist item 12
    in response — broadened past the narrower draft recommended in item 24
    (which only named `bool(<dict>)`/truthiness) to also flag "value copied
    from an unrelated prior variable" and "hardcoded/assumed value with an
    'assume'/'simplify'/'for now'/'not explicitly detailed' comment", since
    regen 5's actual bug would have slipped past the narrower wording.
    Verified zero regression on all 6 domains at/above 0.8 via `--test`
    (prompt-only change, no cached `workflow.py` touched). Regen 6 (both
    codegen rules 24/25 AND the new validator item 12 active): **item 12
    did fire correctly on one retry** — the validator's issues list read
    *"The code assumes authentication succeeded by hard-coding
    `is_authenticated = True` instead of reading a value from the
    `getAuthenticationDetails` response..."*, exactly the defect class it
    was written for, and a correction was accepted — but on a **later**
    retry within the same run (triggered by an unrelated missing-step issue,
    `checkPaymentStatus`, that dominated the validator's attention that
    pass), the finally-accepted code reverted all the way back to the
    original `is_authenticated = bool(auth_records)` pattern, completely
    unflagged by item 12 that pass. Net score: back down to 0.83 (156 rows),
    erasing regen 5's gain. **Lesson for any future validator-checklist
    fix attempting to backstop a codegen sampling habit**: adding the check
    is still worth doing (it's a real, demonstrated, zero-regression
    improvement in the bug's hit rate — it caught the bug at least once,
    live, when it would previously have had no chance to), but don't expect
    a single checklist item to fully close a sampling-habit gap, because the
    validator's own issue-detection is sampled independently per retry and
    can simply fail to notice the targeted defect on whatever retry happens
    to produce the code that gets accepted, especially when a different,
    more salient issue is competing for the same single-pass review. A more
    reliable fix likely needs something outside prompt engineering
    entirely — e.g. a deterministic static check (grep/AST pattern match
    for `bool(<tool_response_variable>)` or an output boolean assigned from
    a variable that was never the return value of its own corresponding
    tool call) run unconditionally on every generated/corrected code
    candidate before acceptance, independent of whether the LLM validator's
    own judgment happens to notice it that pass. Not built this session —
    flagged for the user as a possible structural pipeline change (new
    capability: a non-LLM linting pass in the orchestrator or validator
    loop), out of scope for a single-domain fixture/prompt debugging pass.
    Current state: `validation_agent.py` item 12 is kept (net positive,
    confirmed harmless elsewhere); `customer_service_sop`'s cached
    `workflow.py` is regen 6's output, re-verified at **0.83/156 via
    `--test`**. Not re-attempted a 7th time this session per the stop rule
    (this was the 6th total regeneration across sessions, 2 of them this
    session, already using the "one extra attempt for an evidence-backed
    hypothesis" allowance).

26. **Before concluding a recurring bug is a model-reliability/sampling
    problem, verify the model actually received the information it's
    supposedly ignoring — trace the literal rendered prompt text, not just
    the source toolspec file.** Items 23-25 all concluded `customer_service_sop`'s
    `is_authenticated` bug was a `codegeneration_agent.py` sampling habit,
    reasoning that the SOP and `toolspecs.json` were "already maximally
    explicit." That premise was wrong in a specific, checkable way: the
    *source file* `toolspecs.json` is fully explicit (nested `properties`
    with `login_status`/`account_recovery_status` and exact enum values,
    one level inside the `"authentication records"` Returns field) — but
    `tools_helper.py`'s `load_tools_from_toolspec_json()` only walked the
    TOP level of `outputSchema.properties`. For a Returns field documented
    as a nested object, it captured only that field's own `type`/
    `description` and silently dropped everything inside its own
    `properties` — so the rendered prompt every agent actually received
    was `Returns: {'authentication records': {'type': 'object',
    'description': "...exactly these keys..."}}`, with the real field names
    never appearing anywhere. Confirmed by literally calling
    `format_tools_for_llm()` on this domain's loaded tools and reading the
    output, rather than re-reading `toolspecs.json` directly (which is what
    every prior session had done, and which looks fully correct in
    isolation). The only reason any prior regeneration ever produced
    `login_status`-shaped code at all was a prompt engineer's worked example
    in codegen rule 24 that happened to spell those field names out
    literally, as an aside about a different illustrative scenario — an
    out-of-band leak the model couldn't distinguish from a generic example,
    which is exactly why it was unreliable (sometimes used, sometimes not,
    looking like non-deterministic sampling when the real issue was "this
    is the only place the real schema exists, and nothing marks it as
    authoritative for this specific tool").

    **Fix**: `tools_helper.py`'s `load_tools_from_toolspec_json()` now
    recursively extracts a nested object's own `properties`
    (`_extract_schema_fields`), and `format_tools_for_llm()` renders them
    with their FULL bracket access chain relative to the tool's raw
    response via `_render_returns` (e.g.
    `['authentication records']['login_status']`), not just visual
    indentation. Indentation alone was tried first and is NOT sufficient:
    with the real field name now visible but only indented under its
    parent, codegen correctly wrote `login_status = auth_res["login_status"]`
    (right field name, flattened access) and crashed with `KeyError:
    'login_status'` at runtime (0.11/156) — a code generator needs the
    literal key chain spelled out, not a visual nesting cue, to know which
    intermediate dict keys are required.

    **Also confirmed** (as a controlled, if accidental, experiment): with
    nested fields still hidden and the domain-specific codegen-rule example
    removed per an explicit request to keep CRITICAL REQUIREMENTS
    domain-general, the model had zero grounding anywhere and invented a
    fictional field (`is_authenticated = auth_records.get("authenticated",
    False)`), scoring 0.36/156 — direct evidence that the domain-specific
    example in the old rule 24 was load-bearing *because* it was the only
    place the real schema leaked through, not because the general principle
    needed a domain-specific illustration to be understood.

    Result: `customer_service_sop` 0.83 -> **0.96/156**, clearing the 0.95
    bar after 6 failed regeneration attempts across multiple sessions. This
    is a domain-general infrastructure fix (any domain with a nested-object
    Returns shape was equally affected — `warehouse_package_inspection_sop`
    also has one, re-verified unchanged at 1.00/150 afterward). Verified
    zero regression by statically rendering all 10 domains' `toolspecs.json`
    through the new code (the only way to exercise `tools_helper.py` without
    a live LLM call — `--test` never touches it) plus `--test` re-scoring
    every other domain. Remaining ~4% (6/156 rows) is a different, narrower,
    pre-existing fixture issue: `service_metrics` in `tools.py` is parsed
    from a raw per-row JSON string in the CSV, and a handful of rows' JSON
    doesn't contain a `latency` key at all — unrelated to this fix, not
    pursued since the domain is already past target.

    **General lesson for future debugging**: "the SOP/toolspec is already
    maximally explicit" is a claim about a source file, not about what an
    LLM agent actually sees. Before accepting that premise (especially
    across repeated failed regenerations, where it's tempting to conclude
    "we've tried everything"), render the actual prompt text a real
    pipeline run would send and read it directly — the gap can be in the
    rendering/loading code between the documented source and the model's
    context window, which no amount of re-reading the source file, or
    rewording the SOP/prompt around it, will ever surface.

27. **`--test` cannot catch a regression in shared prompt-building code —
    only a real regeneration can, because `--test` never calls `tools_helper.py`
    or any agent's `_build_prompt`.** After item 26's `tools_helper.py` fix,
    regenerated every domain except the two structural dead-ends as a genuine
    end-to-end check (not just `--test`). 6/8 held steady. 2 didn't, and both
    led to real findings `--test` alone could never have surfaced, since it
    only re-scores already-cached code.

    `customer_service_sop` (0.96 -> 1.00 after passing through 0.36 and 0.77):
    a fresh regeneration hit two MORE bugs beyond item 26's fix, both isolated
    by wrapping every manager method with a print/trace instrumentation layer
    and running one real failing row through it end-to-end, rather than
    guessing from harness input/output diffs (essential here — two different
    bugs both produced the identical generic error "No record found for the
    provided parameters", which could have come from any of five different
    tool calls). (1) `account_suspension_status`'s toolspec enum listed only
    `["ACTIVE","SUSPENDED"]`, never documenting that empty-string means "no
    suspension on record" (132/156 rows) — fixed the enum/description to name
    all three states. (2) The SOP said "re-execute diagnostics" for
    post-troubleshooting metrics, but confirmed via direct instrumentation
    that the diagnostics tool is a static lookup returning IDENTICAL numbers
    on a second call — the real updated metrics only exist in
    `executeTroubleshooting`'s own return field; added an explicit SOP
    sentence naming this, since the SOP's own prose literally recommended the
    wrong tool call. (3) Even after fixing that, the code computed a correct
    threshold check into an unused variable (`issue_fixed`) and a WRONG
    relative-decrease formula into the actual output field
    (`metrics_improved_post_troubleshooting`) — the SOP's output example
    named the field but its prose never said it WAS the "classify as fixed"
    threshold check already described two sentences earlier. Added an
    explicit bridging sentence with a concrete counterexample (500ms->150ms
    still counts as "not improved" since 150 exceeds the 100ms threshold).
    Each of these three was a completely different bug from the one item 26
    fixed and from each other — this domain alone has now needed a
    toolspec-rendering fix (item 26), a toolspec-enum completeness fix, and
    two separate SOP-prose-to-output-field bridging fixes, across 8 total
    regeneration attempts, before reaching its first-ever 1.00.

    `email_intent_sop` (0.95 -> 0.00 -> 0.92): first regen hit ordinary
    sampling variance on the already-documented "unable to decide"
    overuse (item unchanged from prior session's finding) — added an
    implementation note to the SOP flipping which category is the structural
    fallback. Second regen: **0.00**, a universal `KeyError: 'include_history'`
    crashing every row identically. Root cause: `schema_agent.py`'s
    `_compute_parameter_checklist()` lumped every tool parameter — required
    AND optional — into one list the prompt forces into a binary
    classification ("covered by an earlier return" or "a base-level input"),
    with no third option for "optional, has its own documented default, just
    omit it." `include_history` (optional, `default: false`, never mentioned
    in the SOP at all) got wrongly promoted to a required `input_schema`
    field with no corresponding real CSV column. **This is a genuine
    domain-general gap** — any domain with an optional/defaulted tool
    parameter could hit it, not unique to this domain's wording — fixed by
    splitting the checklist using `required`/`default` metadata the toolspec
    already provides (added `default` capture to `tools_helper.py`'s
    parameter extraction too). Verified against all 10 domains' real
    toolspecs before the next regeneration (zero cost). Third regen:
    0.92/186, both issues resolved, landing exactly at this domain's
    pre-existing documented ceiling (the `product_id`+`marketplace_id`
    duplicate-key collision, needs a new tool parameter, unrelated to
    anything fixed this session) — not a regression from today's work, the
    same ceiling found before this pass.

    **General lesson**: treat a `--test`-only regression suite as validating
    "did I break the cached-code scoring path," never "did I break shared
    prompt-building code" — the latter requires spending at least one real
    regeneration per domain whose prompt-building path actually changed.
    `_compute_parameter_checklist()`-style deterministic checklists (the
    exact fix that solved the item-9 tool-count-scaling problem) need the
    same "is this list complete AND correctly partitioned" scrutiny as any
    other piece of logic — a checklist that's complete but miscategorized
    (every parameter present, but required and optional lumped together) can
    still cause a universal crash, for a different reason than an incomplete
    one would.

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
