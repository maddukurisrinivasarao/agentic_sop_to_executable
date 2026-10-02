import json
import logging
from sop_state import SOPConverterState

logger = logging.getLogger(__name__)


class PlanDiffChecker:
    """
    Mechanical (no LLM call) gate that runs right after PlannerAgent, on
    every pipeline run.

    On a normal run there's nothing to compare against, so this is a pure
    pass-through. It only does real work right after an orchestrator-
    triggered planner escalation: it compares the freshly regenerated plan
    against the plan that led to that escalation. If the LLM reproduced the
    identical plan, continuing on to schema/codegen/validator would just
    spend a full extra cycle reproducing the identical failure — so this
    fails the run immediately instead. If the plan actually changed, the
    run continues normally.
    """

    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        previous_plan = state.get("previous_api_plan")

        if previous_plan is None:
            # Not a planner-escalation retry (the initial run, or a retry
            # that targeted generator/schema instead) — nothing to diff
            # against, so just pass through.
            state["plan_diff_status"] = "n/a"
            return state

        new_plan = state.get("api_plan")
        unchanged = (
            json.dumps(previous_plan, sort_keys=True)
            == json.dumps(new_plan, sort_keys=True)
        )

        # Consumed — clear it so a later, separate escalation starts fresh.
        state["previous_api_plan"] = None

        if unchanged:
            state["plan_diff_status"] = "unchanged"
            state["status"] = "failed"
            state["orchestrator_decision"] = {
                "status": "failed",
                "reason": (
                    "Plan diff check: the re-planned attempt is identical to "
                    "the plan that caused the escalation — regenerating "
                    "schema/code/validation against the same plan would only "
                    "reproduce the same failure. Stopping here instead of "
                    "spending another full cycle on it."
                ),
                "retry_count": state.get("retry_count", 0),
                "issues": state.get("validation_result", {}).get("issues", []),
                "retry_target": None,
            }
            print("\n" + "=" * 80)
            print("🛑 PLAN DIFF CHECK: re-plan unchanged — failing fast")
            print("=" * 80)
        else:
            state["plan_diff_status"] = "changed"
            print("\n" + "=" * 80)
            print("✓ PLAN DIFF CHECK: plan changed — continuing to schema")
            print("=" * 80)

        return state
