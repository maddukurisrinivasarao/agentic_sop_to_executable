"""
Global Tool Functions Wrapper
Creates global function wrappers around PatientIntakeManager methods
so they can be called directly by LLMs without needing class instance
"""

from typing import Dict, Any, List
from tools import PatientIntakeManager

# Create a global singleton instance
_manager_instance = None


def get_manager_instance() -> PatientIntakeManager:
    """
    Get or create the global PatientIntakeManager instance.

    Returns:
        PatientIntakeManager instance
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PatientIntakeManager()
    return _manager_instance


def execute_tool_with_structured_output(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool using the manager's process_tool_call method.
    This returns a structured output with the correct key name.
    
    This is the PRIMARY function that LLM-generated code should use.
    
    Args:
        tool_name: Name of the tool to execute
        tool_input: Dictionary of input parameters
        
    Returns:
        Dictionary with output variable name as key and result as value
        
    Example:
        >>> result = execute_tool_with_structured_output(
        ...     tool_name="validateInsurance",
        ...     tool_input={
        ...         "patient_id": "P123",
        ...         "insurance_provider": "Blue Cross",
        ...         "policy_number": "BC123",
        ...         "group_number": "GRP789",
        ...         "coverage_start_date": "2024-01-01",
        ...         "insurance_type": "Private"
        ...     }
        ... )
        >>> print(result)
        {"insurance_validation": "Valid"}
    """
    manager = get_manager_instance()
    return manager.process_tool_call(tool_name, tool_input)