# sop-to-code-agent — program.md

Operating instructions for a coding agent (Claude Code, Codex, etc.) working on
this repo. The repo implements a LangGraph multi-agent pipeline that converts a
plain-text SOP into an executable Python `workflow(input_data)` function,
calling tools via `global_tool_functions.get_manager_instance()`.

Point your agent here with something like:
> "Read program.md and improve the pipeline's test_harness.py score."

---

## 1. What this system is

```
planner → schema → generator → validator → orchestrator
                                    ▲             │
                                    └── retry ─────┘
                                                   │
                                        complete / failed → workflow.py
```

State is a single `SOPConverterState` TypedDict (`sop_state.py`) threaded
through every node. Each of the four LLM-calling agents is a callable class:
read state, call an LLM, parse the response defensively, validate the result,
write back to state, return state. `orchestrator_agent.py` is the exception —
it makes no LLM call at all; it's pure decision logic over the validator's
output (see §3).

| File | Role |
|---|---|
| `sop_state.py` | Shared state schema |
| `planner_agent.py` | SOP → ordered list of tool calls (`api_plan`) |
| `schema_agent.py` | `api_plan` → base-level input parameters (`input_schema`) |
| `codegeneration_agent.py` | `api_plan` + `input_schema` → `generated_code` |
| `validation_agent.py` | LLM review of `generated_code` → `validation_result` + `final_code` |
| `orchestrator_agent.py` | Reads `validation_result`, decides `retry` / `complete` / `failed` |
| `agent_pipeline.py` | Wires the above into a LangGraph `StateGraph` (`SOPToCodeConverter`) |
| `client.py` | LLM client singleton (Groq by default, `_provider`/`_model` class attrs; Anthropic selectable) |
| `tools_helper.py` / `global_tool_functions.py` | Tool spec loading + runtime tool execution shim |
| `main.py` | CLI: convert one `sop_dir` (`sop.txt` + `toolspecs.json`) into `workflow.py` |
| `test_harness.py` | Runs the pipeline against every domain in `eval_sops/`, scores generated code against held-out CSV rows, appends to `results.tsv` |
| `eval_sops/<domain>/` | Golden SOP + toolspecs + `tools.py` (mock manager) + `test_set_{with,without}_outputs.csv` per domain |

---

## 2. Current state

The graph is fully wired and runs end to end — there is no missing plumbing
here. What's actually true right now:

1. **`main.py` doesn't check `result.get("status")` before writing.**
   `converter.convert()` returns `"code": None` on a `failed` pipeline, and
   `main.py` still does `f.write(result["code"])` unconditionally — that
   throws a `TypeError` on any failure instead of surfacing `result["error"]`.
   Fix this before relying on `main.py` for anything unattended.
   (`test_harness.py` already works around this itself by checking
   `result.get("status") == "failed"` before touching `result["code"]`.)

2. **`results.tsv` in this repo predates this checkout and should not be
   trusted as a baseline.** Several of its error messages reference a path
   (`.../agentic_sop_to_executable-main/eval_sops/...`) and domain names
   (`customer_service`, `warehouse_package_inspection_sop`, ...) that don't
   exist in the current `eval_sops/` (which only has `dangerous_goods_sop`,
   `know_your_business_sop`, `patient_intake_sop`). Treat it as leftover
   noise from an earlier clone, not history to compare against. Run
   `python test_harness.py` fresh to get a real baseline before changing
   anything.

3. **The interesting signal in that stale data, if it repeats on a fresh
   run, is worth watching for:** rows where `completed=True` (validator said
   `is_valid: true`, pipeline reached `status="complete"`) but
   `row_pass_rate=0.00` — i.e. the pipeline is confident the code is correct
   and it still produces wrong output on every test row. `validation_agent.py`
   currently trusts the LLM's self-reported `is_valid` boolean directly
   (`state["status"] = "complete" if validation["is_valid"] else "validating"`)
   with no independent recomputation against anything — unlike, say, a score
   threshold. If `row_pass_rate` stays low while `completed` stays `True`,
   that trust boundary is the first place to look, not the planner/generator.

4. **The actual target for improvement is `row_pass_rate` in
   `results.tsv`**, not new architecture. There's no eval-agent layer
   (`planner_eval`, `schema_eval`, etc.) in this codebase and none is planned
   here — if a past note mentioned one, disregard it, it doesn't match this
   code. Improving prompts, guardrails, or the validator's trust of the LLM
   inside the existing five agents is in scope; adding new pipeline stages
   is not, unless you've confirmed with whoever's driving this that it's
   wanted.

---

## 3. Conventions — follow these for any agent you touch or add

`planner_agent.py`, `schema_agent.py`, `codegeneration_agent.py`, and
`validation_agent.py` each follow the same shape in `__call__`. Match it:

1. **Input guardrails** (`_validate_input`) — raise the agent's own
   `<Name>AgentError` on missing/malformed state. Never let a downstream
   agent discover an upstream agent's bug.
2. **Build prompt** (`_build_prompt`) — inject only what's needed; keep the
   "return ONLY JSON/code, no markdown fences" instruction explicit every time.
3. **Call LLM with retry** (`_call_with_retry`) — exponential backoff
   (`2 ** attempt`), max 3 attempts, re-raise the agent's own error type
   without retrying it (it's not transient), retry everything else.
4. **Parse defensively** (`_parse_response`) — strip markdown fences, try
   direct `json.loads`, fall back to regex-extracting the first `{...}` or
   `[...]` block, raise a clear parse error with a snippet of the raw
   response on failure.
5. **Output guardrails** — validate shape, types, and cross-references
   (e.g. tool names must exist in `tools_formatted`; `input_data` keys must
   exist in `input_schema`) before writing to state. Prefer **warn + coerce**
   for recoverable issues (e.g. `"true"` → `True`) and **hard fail** for
   structural ones (missing keys, wrong types, dangerous code patterns).
6. **Commit to state** — write only the fields this agent owns; don't
   overwrite `status` unless you're also updating the router that reads it.

`orchestrator_agent.py` is different by design: no LLM call, no prompt, no
parsing. It only runs input guardrails on `validation_result` /
`retry_count` / `max_retries`, classifies `validation_result["issues"]` by
severity (`UNRECOVERABLE_PATTERNS`, `SEVERITY_WEIGHTS`), and returns
`retry` / `complete` / `failed`. Don't force it into the six-step shape above.

**Exceptions**: one custom exception class per agent (`PlannerAgentError`,
`SchemaAgentError`, `CodeGeneratorAgentError`, `ValidatorAgentError`,
`OrchestratorError`), all caught centrally in `agent_pipeline.py`'s
`AGENT_EXCEPTIONS` tuple. If you add a new agent, add its exception class to
that tuple or failures from it will be swallowed by the generic
`except Exception` branch and misreported as `"agent": "unknown"`.

---

## 4. Security guardrails already in place — don't weaken them

- **Prompt-injection marker checks** on the raw SOP text, in both
  `schema_agent.py` and `codegeneration_agent.py` (`_validate_input`).
- **Dangerous-pattern regex ban** (`eval`, `exec`, `os.system`, `subprocess.*`,
  `__import__`, `open`) on generated and corrected code, checked in both
  `codegeneration_agent.py` and `validation_agent.py`.
- **Import whitelist**: only `ALLOWED_IMPORT_MODULES` (currently
  `global_tool_functions`) may be imported by generated code.
- **Tool-name / input-key whitelist**, AST-based, cross-checked against
  `api_plan` / `input_schema` before code is accepted.

Any new code-producing agent must run through the same
`_check_dangerous_patterns` / whitelist checks that `codegeneration_agent.py`
and `validation_agent.py` already do. Note the gap in §2.3: none of these
existing checks currently second-guess the validator's own `is_valid`
verdict — if you add anything that does, keep the checks above too rather
than replacing them.

---

## 5. Logging

`main.py` calls `setup_logging(level=logging.INFO, log_file="app.log")` once,
before importing anything that creates a logger. Every module does
`logger = logging.getLogger(__name__)` and nothing else — don't call
`basicConfig` or add handlers anywhere but `logger_config.py`.

---

## 6. Definition of done for a change in this repo

Before considering any change here complete:
- [ ] Run `python test_harness.py` and confirm it appends fresh rows to
      `results.tsv` under the *current* git commit — don't reason from the
      stale rows already in the file (§2.2).
- [ ] Compare `row_pass_rate` per domain against the run immediately before
      your change, not against old/stale rows.
- [ ] Run `main.py` against a real SOP + toolspec directory without a stack
      trace, including a directory whose SOP is designed to fail — confirm
      it prints `result["error"]` instead of crashing (§2.1), if you've
      touched `main.py`.
- [ ] Confirm `app.log` shows one clean pass through every stage that ran
      (`grep -E "AGENT:|validation passed|Decision:" app.log`).
- [ ] No dangerous-pattern, import-whitelist, or tool-whitelist check was
      removed or loosened (§4).
