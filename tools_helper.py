"""
tools_helper.py

Tools metadata extraction from toolsspcs.json
"""

import json
from typing import List, Dict, Any


# ============================================================================
# TOOL FORMATTING FOR LLM
# ============================================================================

def _extract_schema_fields(schema_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively extract a JSON-schema 'properties' block into a plain dict
    {field_name: {type, description, enum?, properties?}}, walking into any
    nested object's own 'properties' so a tool's FULL Returns shape is
    captured — not just its top-level field names. Without this recursion, a
    Returns field documented as an object (e.g. a parsed-JSON result with
    several named sub-fields and enum values) renders to every downstream
    agent as just "type: object", with its real sub-field names silently
    dropped — looking identical to a genuinely undocumented shape.
    """
    properties = schema_json.get("properties", {})
    result = {}
    for field_name, field_spec in properties.items():
        entry = {
            "type": field_spec.get("type", "string"),
            "description": field_spec.get("description", ""),
        }
        if "enum" in field_spec:
            entry["enum"] = field_spec["enum"]
        if field_spec.get("type") == "object" and "properties" in field_spec:
            entry["properties"] = _extract_schema_fields(field_spec)
        if "examples" in field_spec:
            entry["examples"] = field_spec["examples"]
        result[field_name] = entry
    return result


def _render_returns(fields: Dict[str, Any], indent: int = 6, access_prefix: str = "") -> str:
    """
    Recursively render a Returns field dict (see _extract_schema_fields) into
    readable indented lines. A nested field's displayed name is its FULL
    bracket access chain relative to the tool's raw response (e.g.
    "['authentication records']['login_status']"), not just its bare name —
    indentation alone showed a field was nested but not HOW to reach it, and
    codegen reached for a flat `resp['login_status']` and got a KeyError
    instead of the required `resp['authentication records']['login_status']`.
    """
    pad = " " * indent
    lines = []
    for field_name, spec in fields.items():
        type_str = spec.get("type", "string")
        enum_str = f" [enum: {', '.join(repr(v) for v in spec['enum'])}]" if spec.get("enum") else ""
        desc = spec.get("description", "")
        desc_str = f": {desc}" if desc else ""
        display = f"{access_prefix}['{field_name}']" if access_prefix else field_name
        lines.append(f"{pad}- {display} ({type_str}){enum_str}{desc_str}")
        if spec.get("properties"):
            child_prefix = f"{access_prefix}['{field_name}']" if access_prefix else f"['{field_name}']"
            lines.append(_render_returns(spec["properties"], indent + 3, child_prefix))
        if spec.get("examples"):
            lines.append(f"{pad}  examples: {spec['examples']}")
    return "\n".join(lines)


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

        if tool['returns']:
            formatted += "   Returns:\n"
            formatted += _render_returns(tool['returns']) + "\n"
        else:
            # An empty dict here previously rendered as "Returns: {}", which
            # reads as "returns an empty dict" rather than "undocumented" —
            # some tools (e.g. patient_intake_sop's) have no outputSchema at
            # all and actually return a bare string/scalar at runtime, and
            # that misleading rendering was feeding codegen prompts a false
            # signal that biased them toward assuming a dict shape.
            formatted += "   Returns: (not documented in toolspec — do not assume a dict shape)\n"
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
                entry = {
                    "type": param_spec.get("type", "string"),
                    "required": param_name in required_params,
                    "description": param_spec.get("description", "")
                }
                if "default" in param_spec:
                    entry["default"] = param_spec["default"]
                tool["parameters"][param_name] = entry

        if "outputSchema" in tool_spec:
            output_schema = tool_spec["outputSchema"]

            # FORMAT has .json nested inside
            if "json" in output_schema:
                schema_json = output_schema["json"]
            else:
                schema_json = output_schema

            # Recurse into any nested object's own 'properties' (see
            # _extract_schema_fields) — a Returns field documented as an
            # object with named sub-fields (e.g. a parsed-JSON result)
            # previously only had its OWN type/description captured here,
            # silently dropping every sub-field name/enum one level down.
            # That left codegen/schema/validator prompts unable to see the
            # real field names at all, indistinguishable from a genuinely
            # undocumented shape — they'd invent a plausible-sounding field
            # name instead, differently every time, because there was
            # nothing real to ground it in.
            tool["returns"] = _extract_schema_fields(schema_json)
        tools.append(tool)
    
    return tools