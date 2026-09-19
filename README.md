# Agentic SOP-to-Executable

Convert a plain-English Standard Operating Procedure (SOP) plus a set of tool
specs into a runnable, self-contained Python `workflow()` function — using a
multi-agent [LangGraph](https://github.com/langchain-ai/langgraph) pipeline
that plans, generates, validates, and self-corrects the code it writes.

```
SOP text + toolspecs.json  ─▶  Planner ─▶ Schema ─▶ Generator ─▶ Validator ─▶ Orchestrator
                                                          ▲                        │
                                                          └──────── retry ─────────┘
                                                                     │
                                                          complete / failed ─▶ workflow.py
```

## How it works

Each stage is an independent agent (`__call__`-able class) that reads and
writes a shared `SOPConverterState` (see [sop_state.py](sop_state.py)), wired
together as a LangGraph state graph in
[agent_pipeline.py](agent_pipeline.py):

| Agent | File | Responsibility |
|---|---|---|
| **Planner** | [planner_agent.py](planner_agent.py) | Reads the SOP + available tools, produces an ordered `api_plan` (which tool to call, in what order). |
| **Schema** | [schema_agent.py](schema_agent.py) | Determines the base-level input parameters the workflow needs from the caller (i.e. values that aren't produced by an earlier step). |
| **Code Generator** | [codegeneration_agent.py](codegeneration_agent.py) | Generates a single Python `workflow(input_data)` function that calls the planned tools via `global_tool_functions.get_manager_instance()`. |
| **Validator** | [validation_agent.py](validation_agent.py) | Statically checks the generated code (AST parse, banned-pattern scan for `eval`/`exec`/`os.system`/etc.) and asks the LLM to review it for logical correctness. |
| **Orchestrator** | [orchestrator_agent.py](orchestrator_agent.py) | Reads the validation report, classifies issues by severity, and decides whether to `retry` (with feedback fed back into the Generator), mark `complete`, or `failed` (unrecoverable issue or retry budget exhausted). |

Every agent also enforces its own **input/output guardrails** (schema checks,
prompt-injection heuristics, retry-with-backoff on transient LLM failures,
tool-name whitelisting, etc.) and raises a dedicated `*AgentError` on
unrecoverable problems, so a bad LLM response fails loudly instead of
silently corrupting state.

The LLM backend is pluggable via [client.py](client.py)'s `ClientSingleton`
(currently configured for [Groq](https://groq.com/); Anthropic is wired in
and selectable by changing `_provider`).

## Repository layout

```
agent_pipeline.py         LangGraph wiring — the SOPToCodeConverter entry point
sop_state.py               Shared TypedDict state passed between agents
planner_agent.py           Agent 1: SOP -> ordered API plan
schema_agent.py             Agent 2: API plan -> required input schema
codegeneration_agent.py     Agent 3: plan + schema -> Python workflow() code
validation_agent.py         Agent 4: static + LLM review of generated code
orchestrator_agent.py       Agent 5: retry / complete / failed decision
client.py                   LLM client singleton (Groq / Anthropic)
tools_helper.py             Loads and formats toolspecs.json for prompts
global_tool_functions.py    Runtime shim generated code calls to reach the active tool manager
logger_config.py            Logging setup
main.py                     CLI: convert a single SOP directory into workflow.py
test_harness.py             Benchmark runner: scores the pipeline across all eval_sops/ domains
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set the API key for whichever provider `client.py` is configured to use
(defaults to Groq):

```bash
export GROQ_API_KEY=your_key_here
# or, if you switch ClientSingleton._provider to "anthropic":
export ANTHROPIC_API_KEY=your_key_here
```

## Usage

### Convert a single SOP

Point it at a directory containing a `sop.txt` and a `toolspecs.json`:

```bash
python main.py path/to/your_sop_dir
```

This writes the generated code to `path/to/your_sop_dir/workflow.py`.

### Run the benchmark harness

[test_harness.py](test_harness.py) runs the pipeline against every domain
directory under `eval_sops/`, executes each generated `workflow()` against
that domain's held-out test rows, scores it against ground truth, and
appends one row per domain to `results.tsv`:

```bash
python test_harness.py
```

Each row records the git commit, domain, whether generation completed,
retry count, and row-level pass rate, so `results.tsv` doubles as a
before/after log across code changes to the pipeline.

> This repo does not include an `eval_sops/` dataset — it's ignored via
> `.gitignore` since SOP-Bench-style benchmark data is typically distributed
> under a CC BY-NC license that restricts redistribution and AI-training
> use. Drop a compatible `eval_sops/<domain>/{sop.txt,toolspecs.json,
> tools.py,test_set_with_outputs.csv,test_set_without_outputs.csv}` tree in
> locally to use `test_harness.py`.

## Status

This is a research prototype. Guardrails are strict by design — a plan step
referencing an unknown tool, a schema violation, or a banned code pattern
fails the run rather than being silently patched — so pipeline runs can and
do fail loudly on model errors (bad JSON, wrong model name, rate limits)
rather than producing incorrect workflows silently.

## Autonomous experiment loop

This repo also supports an unattended experiment loop in the spirit of
[karpathy/autoresearch-macos](https://github.com/karpathy/autoresearch-macos):
point a coding agent at [program.md](program.md) and
[sop_autoresearch.md](sop_autoresearch.md), let it repeatedly tweak the
pipeline, run [test_harness.py](test_harness.py), and keep or discard each
change based on whether `row_pass_rate` improved. The mapping between the
two isn't 1:1, since autoresearch-macos' "model" is a single script that can
train and score itself, while this repo's "model" is a 5-agent pipeline
spread across several files that needs a separate harness to run and score
it:

| Karpathy file | This repo | Role |
|---|---|---|
| `prepare.py` | `eval_sops/`<br>`tools_helper.py`<br>`global_tool_functions.py` | Fixed setup and data — never edited by the agent. |
| `train.py` | `planner_agent.py`<br>`schema_agent.py`<br>`codegeneration_agent.py`<br>`validation_agent.py`<br>`orchestrator_agent.py`<br>`agent_pipeline.py`<br>`client.py` | The system being improved — edited every experiment. |
| `program.md` | [program.md](program.md)<br>[sop_autoresearch.md](sop_autoresearch.md) | Agent instructions. His single file covers both "what the system is" and "how to run experiments" — this repo splits them: `program.md` covers the former, `sop_autoresearch.md` the latter. |

One thing has no direct peer: **[test_harness.py](test_harness.py)**. In
autoresearch-macos, `train.py` scores itself — it trains *and* prints
`val_bpb` in the same run. Here, the "model" is split across seven files
that can't score themselves, so `test_harness.py` exists purely to run the
pipeline against `eval_sops/` and measure `row_pass_rate`.

Budgeting is token-based rather than a fixed experiment count — see
`sop_autoresearch.md` Section 2 — since a single `test_harness.py` pass across all
`eval_sops/` domains can use most of a free-tier daily token quota in one
run.


