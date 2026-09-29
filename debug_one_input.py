"""
debug_one_input.py — run a domain's cached workflow.py against ONE custom
input, without the LLM pipeline and without the CSV.

Imports workflow.py as a REAL module (importlib, tied to its actual file
path) instead of test_harness.py's exec(code, namespace) — exec'd code has
no genuine file identity, so a debugger (VSCode, pdb) can't set breakpoints
in it. This way you can put a breakpoint directly in workflow.py and step
into it normally when this script calls workflow(INPUT_DATA).

Costs zero tokens — this never calls converter.convert().

Usage:
    python debug_one_input.py                       # uses DEFAULT_DOMAIN below
    python debug_one_input.py --domain email_intent_sop   # overrides it

Edit INPUT_DATA and DEFAULT_DOMAIN below for whatever domain/scenario
you're debugging.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import global_tool_functions
import test_harness as th

# <-- Edit this: used whenever --domain isn't passed on the command line.
DEFAULT_DOMAIN = "customer_service_sop"

# <-- Edit this for whatever domain/scenario you're debugging.
INPUT_DATA = {
    "account_id": "BCD-89012",
    "authentication_history": '{"timestamp_last_login": "2025-05-02T07:00:00Z", "login_status": "SUCCESS", "account_recovery_status": ""}',
    "session_token": "SES-20250510-BCD89012-001",
    "ticket_id": "TKT-2025051266",
    "account_status": "ACTIVE",
    "reason_for_account_status": "",
    "overdue_payment_status": "",
    "account_suspension_status": "",
    "service_area_code": "SA-89012",
    "outage_detected": "True",
    "outage_id": "OUT-2025051241",
    "radius_miles": "5.6",
    "outage_impact_score": "1.0",
    "expected_outage_resolution_time": "6 hours",
    "service_type": "video",
    "subscribed_bandwidth": "500 Mbps",
    "service_metrics": "{}",
    "timestamp_diagnostics_started": "",
    "timestamp_diagnostics_completed": "",
    "root_causes": "[]",
    "timestamp_troubleshooting_started": "",
    "timestamp_troubleshooting_completed": "",
    "troubleshooting_steps": "[]",
    "service_metrics_post_troubleshooting": "{}",
    "escalation_ticket_id": "",
    "escalation_team": "",
    "escalation_reason": "",
}


def import_workflow_module(workflow_path: Path):
    """
    Load workflow.py as a real module tied to its actual file path (same
    technique test_harness.py's load_domain_manager() uses for tools.py) so
    a debugger can set breakpoints in it and step through normally, unlike
    exec()'d code which has no file identity to attach to.
    """
    module_name = f"workflow_{workflow_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, workflow_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domain",
        default=DEFAULT_DOMAIN,
        help=f"Domain folder name under eval_sops/ (default: {DEFAULT_DOMAIN!r}, from DEFAULT_DOMAIN in this file)",
    )
    args = parser.parse_args()

    domain_dir = Path("eval_sops") / args.domain
    workflow_path = domain_dir / th.WORKFLOW_FILENAME
    if not workflow_path.exists():
        print(f"No cached {th.WORKFLOW_FILENAME} at {workflow_path} — "
              f"run `python test_harness.py --domains {args.domain}` once "
              f"(without --test) to generate one first.")
        return

    manager = th.load_domain_manager(domain_dir)
    global_tool_functions.set_active_manager(manager)

    # Set a breakpoint anywhere inside workflow.py itself (or right here,
    # then step in with F11/"Step Into") — this call is a real function in
    # a real module, not a string being exec'd, so the debugger can follow.
    workflow_module = import_workflow_module(workflow_path)
    result = workflow_module.workflow(INPUT_DATA)

    print(f"\ninput_data={INPUT_DATA}\n")
    print(f"actual={result}\n")


if __name__ == "__main__":
    main()
