"""
test_harness.py — runs the full SOP-to-code pipeline against every golden
SOP under eval_sops/, executes the generated workflow() against that domain's
real SOP-Bench test cases, scores it against ground truth, and appends one
row per domain to results.tsv.

This is the thing sop_autoresearch.md's experiment loop calls once per
experiment. Run it directly to get a baseline before any agent touches
the code:

    python test_harness.py
"""

import csv
import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import global_tool_functions
from agent_pipeline import SOPToCodeConverter
from tools_helper import load_tools_from_toolspec_json

EVAL_SOPS_DIR = Path("eval_sops")
RESULTS_TSV = Path("results.tsv")


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "nogit"


def load_domain_manager(domain_dir: Path):
    """
    Dynamically import <domain_dir>/tools.py under a unique module name
    (so different domains' `tools` modules don't collide in sys.modules),
    find whichever class defines process_tool_call, and instantiate it.
    """
    tools_path = domain_dir / "tools.py"
    module_name = f"tools_{domain_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, tools_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    for _, obj in inspect.getmembers(module, inspect.isclass):
        if hasattr(obj, "process_tool_call"):
            return obj()

    raise RuntimeError(f"No class with process_tool_call found in {tools_path}")


def load_input_output_columns(domain_dir: Path):
    """
    Diff test_set_without_outputs.csv against test_set_with_outputs.csv
    headers to figure out which columns are inputs vs. expected outputs.
    """
    without_path = domain_dir / "test_set_without_outputs.csv"
    with_path = domain_dir / "test_set_with_outputs.csv"

    with open(without_path, newline="", encoding="utf-8") as f:
        input_cols = next(csv.reader(f))
    with open(with_path, newline="", encoding="utf-8") as f:
        all_cols = next(csv.reader(f))

    output_cols = [c for c in all_cols if c not in input_cols]
    return input_cols, output_cols


def load_test_rows(domain_dir: Path, input_cols, output_cols, max_rows: int = 5):
    """Load up to max_rows test cases as (input_data, expected_output) pairs."""
    with_path = domain_dir / "test_set_with_outputs.csv"
    rows = []
    with open(with_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            input_data = {k: row[k] for k in input_cols if k in row}
            expected = {k: row[k] for k in output_cols if k in row}
            rows.append((input_data, expected))
    return rows


def run_generated_workflow(code: str, input_data: dict):
    """Exec the generated code and call its workflow() function."""
    namespace = {}
    exec(code, namespace)
    workflow_fn = namespace.get("workflow")
    if workflow_fn is None:
        raise RuntimeError("Generated code has no workflow() function")
    return workflow_fn(input_data)


def score_domain(domain_dir: Path, converter: SOPToCodeConverter) -> dict:
    domain = domain_dir.name
    print(f"\n{'#'*80}\n# DOMAIN: {domain}\n{'#'*80}")

    manager = load_domain_manager(domain_dir)
    global_tool_functions.set_active_manager(manager)

    sop = (domain_dir / "sop.txt").read_text(encoding="utf-8")
    tools = load_tools_from_toolspec_json(str(domain_dir / "toolspecs.json"))

    result = converter.convert(sop, tools)

    if result.get("status") == "failed" or not result.get("code"):
        return {
            "domain": domain,
            "completed": False,
            "retries": None,
            "row_pass_rate": 0.0,
            "error": result.get("error"),
        }

    input_cols, output_cols = load_input_output_columns(domain_dir)
    test_rows = load_test_rows(domain_dir, input_cols, output_cols)

    passed = 0
    for input_data, expected in test_rows:
        try:
            actual = run_generated_workflow(result["code"], input_data)
        except Exception as exc:
            print(f"  ✗ row crashed: {exc}")
            continue
        if not isinstance(actual, dict):
            continue
        # Loose match: every expected key/value pair must appear, as strings,
        # somewhere in the actual result (values, or nested dict values).
        actual_values = {str(v).strip().lower() for v in actual.values()}
        row_ok = all(
            str(v).strip().lower() in actual_values for v in expected.values() if v
        )
        if row_ok:
            passed += 1
            print("  ✓ row passed")
        else:
            print(f"  ✗ row mismatch — expected {expected}, got {actual}")

    row_pass_rate = passed / len(test_rows) if test_rows else 0.0

    return {
        "domain": domain,
        "completed": True,
        "retries": result.get("orchestrator_decision", {}).get("retry_count", 0)
        if isinstance(result.get("orchestrator_decision"), dict) else 0,
        "row_pass_rate": row_pass_rate,
        "error": None,
    }


def main():
    domains = sorted(d for d in EVAL_SOPS_DIR.iterdir() if d.is_dir())
    if not domains:
        print(f"No domains found under {EVAL_SOPS_DIR}/")
        return

    converter = SOPToCodeConverter()
    commit = get_git_commit()

    is_new_file = not RESULTS_TSV.exists()
    with open(RESULTS_TSV, "a", newline="", encoding="utf-8") as f:
        if is_new_file:
            f.write("commit\tdomain\tcompleted\tretries\trow_pass_rate\terror\n")

        for domain_dir in domains:
            try:
                r = score_domain(domain_dir, converter)
            except Exception as exc:
                r = {
                    "domain": domain_dir.name,
                    "completed": False,
                    "retries": None,
                    "row_pass_rate": 0.0,
                    "error": str(exc),
                }
            f.write(
                f"{commit}\t{r['domain']}\t{r['completed']}\t{r['retries']}\t"
                f"{r['row_pass_rate']:.2f}\t{json.dumps(r['error']) if r['error'] else ''}\n"
            )
            print(f"\n>>> {r['domain']}: completed={r['completed']} "
                  f"row_pass_rate={r['row_pass_rate']:.2f}")

    print(f"\nResults appended to {RESULTS_TSV}")


if __name__ == "__main__":
    main()
