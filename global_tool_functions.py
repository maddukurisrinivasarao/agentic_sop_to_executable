"""
Global Tool Functions Wrapper (multi-domain version)

Instead of hardcoding one manager class, the active manager is set by
whatever is currently running (test_harness.py during autoresearch, or
main.py for a normal single-domain run). Generated workflow code calls
get_manager_instance() once and then invokes tool methods directly on
the returned manager, regardless of which domain is active.
"""

from typing import Dict, Any

_manager_instance = None


def set_active_manager(manager: Any) -> None:
    """
    Called by test_harness.py (or main.py) before running a workflow,
    to point tool calls at the correct domain's manager instance.
    """
    global _manager_instance
    _manager_instance = manager


def get_manager_instance() -> Any:
    """
    Returns whatever manager was last set via set_active_manager().
    Falls back to PatientIntakeManager only if nothing was explicitly set,
    so existing single-domain scripts (main.py) keep working unchanged.

    This is the PRIMARY function that LLM-generated code should use — it
    calls this once, then invokes tool methods directly on the returned
    manager (e.g. manager.validateInsurance(...)).
    """
    global _manager_instance
    return _manager_instance


def execute_tool_with_structured_output(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy string-dispatch entry point, kept for workflows generated before
    the switch to direct manager method calls. New generated code should
    use get_manager_instance() instead.
    """
    manager = get_manager_instance()
    return manager.process_tool_call(tool_name, tool_input)
