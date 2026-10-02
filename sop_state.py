# ============================================================================
# STATE DEFINITION
# ============================================================================

from typing import TypedDict, List, Dict, Any

class SOPConverterState(TypedDict):
    """State passed between agents in the graph"""
    sop: str                          # Input SOP text
    tools: List[Dict[str, Any]]       # Available tools
    tools_formatted: str              # Formatted tools for LLM
    api_plan: List[Dict[str, Any]]    # Planned API calls
    input_schema: List[Dict[str, Any]] # Required input parameters
    generated_code: str               # Generated Python code
    validation_result: Dict[str, Any] # Validation feedback
    final_code: str                   # Final validated code
    error: str                        # Error messages if any

   # Control flow
    retry_count: int
    max_retries: int
    error: str
    status: str  # "planning", "generating", "validating", "complete", "failed"

    # Escalation routing (orchestrator may route a retry to generator,
    # schema, or planner instead of always regenerating code)
    retry_target: str          # "generator" | "schema" | "planner" | None
    last_retry_target: str     # what the previous retry targeted, for persistence detection
    issue_history: list        # one entry per orchestrator pass: that round's validation issues
    plan_retries: int
    schema_retries: int
    max_plan_retries: int
    max_schema_retries: int
    previous_api_plan: list    # snapshot taken right before a planner-escalation retry
    plan_diff_status: str      # "n/a" | "changed" | "unchanged" — set by PlanDiffChecker