"""
tools_helper.py

Tools metadata extraction from toolsspcs.json
"""

import json
from typing import List, Dict, Any


# ============================================================================
# TOOL FORMATTING FOR LLM
# ============================================================================

def format_tools_for_llm(tools: List[Dict[str, Any]]) -> str:
    """
    Format the tools list into a string that can be used in LLM prompts
    for the Clarifier module (question_generation_agent)
    """
    formatted = "Available Tools:\n\n"

    for i, tool in enumerate(tools, 1):
        formatted += f"{i}. Tool: {tool['name']}\n"
        formatted += f"   Description: {tool['description']}\n"
        formatted += "   Parameters:\n"

        for param_name, param_info in tool['parameters'].items():
            required = "required" if param_info.get('required', False) else "optional"
            formatted += f"      - {param_name} ({param_info['type']}, {required})"
            if 'description' in param_info:
                formatted += f": {param_info['description']}"
            formatted += "\n"

        formatted += f"   Returns: {tool['returns']}\n"
        formatted += "-" * 80 + "\n\n"

    return formatted

# ============================================================================
# LOAD FROM JSON FILE
# ============================================================================

def load_tools_from_toolspec_json(json_file_path: str) -> List[Dict[str, Any]]:
    """
    Load tools from YOUR toolspecs.json format
    """
    with open(json_file_path, 'r') as f:
        toolspec_data = json.load(f)
    
    # Handle single tool or list
    if isinstance(toolspec_data, dict) and "toolSpec" in toolspec_data:
        toolspec_data = [toolspec_data]
    
    tools = []
    
    for tool_entry in toolspec_data:
        # FORMAT: Navigate to toolSpec
        if "toolSpec" in tool_entry:
            tool_spec = tool_entry["toolSpec"]
        else:
            tool_spec = tool_entry
        
        tool = {
            "name": tool_spec.get("name", ""),
            "description": tool_spec.get("description", ""),
            "domain": ["healthcare"],
            "parameters": {},
            "returns": {}
        }
        
        # FORMAT: inputSchema.json (note the capital S and nested json)
        if "inputSchema" in tool_spec:
            input_schema = tool_spec["inputSchema"]
            
            # FORMAT has .json nested inside
            if "json" in input_schema:
                schema_json = input_schema["json"]
            else:
                schema_json = input_schema
            
            # Now extract normally
            properties = schema_json.get("properties", {})
            required_params = schema_json.get("required", [])
            
            for param_name, param_spec in properties.items():
                tool["parameters"][param_name] = {
                    "type": param_spec.get("type", "string"),
                    "required": param_name in required_params,
                    "description": param_spec.get("description", "")
                }

        if "outputSchema" in tool_spec:
            output_schema = tool_spec["outputSchema"]
            
            # FORMAT has .json nested inside
            if "json" in output_schema:
                schema_json = output_schema["json"]
            else:
                schema_json = output_schema
            
            # Now extract normally
            properties = schema_json.get("properties", {})
            required_params = schema_json.get("required", [])
            
            for param_name, param_spec in properties.items():
                tool["returns"][param_name] = {
                    "type": param_spec.get("type", "string"),
                    "description": param_spec.get("description", "")
                }        
        tools.append(tool)
    
    return tools