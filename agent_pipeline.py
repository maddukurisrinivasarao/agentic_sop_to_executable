# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

"""
LangGraph-based SOP to Executable Code Converter
Uses multi-agent system with state graph for workflow conversion

Architecture:
- PlannerAgent: Analyzes SOP and creates execution plan
- SchemaAgent: Identifies input parameters needed
- CodeGeneratorAgent: Generates executable Python code
- ValidatorAgent: Validates and refines generated code
"""

import os
import json
from typing import TypedDict, Annotated, List, Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from tools_helper import format_tools_for_llm
from client import ClientSingleton
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()

# ============================================================================
# STATE DEFINITION
# ============================================================================

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

# ============================================================================
# AGENT 1: PLANNER AGENT
# ============================================================================

class PlannerAgent:
    """
    Agent responsible for analyzing SOP and creating API execution plan
    """
    
    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        """
        Analyze SOP and create API plan
        """
        print("\n" + "=" * 80)
        print("🤖 PLANNER AGENT: Analyzing SOP...")
        print("=" * 80)
        
        prompt = f"""You are a workflow planning expert. Analyze this SOP and create an execution plan.

SOP:
{state['sop']}

Available Tools:
{state['tools_formatted']}

Create a step-by-step API execution plan. For each step:
1. Identify the task description
2. Match it to the appropriate tool
3. Determine the logical sequence

Return a JSON array:
[
  {{
    "step": 1,
    "task": "Validate patient insurance",
    "tool": "validateInsurance",
    "description": "Verify insurance coverage details"
  }},
  ...
]

Return ONLY the JSON array, no explanation."""

        messages = [
            SystemMessage(content="You are an expert workflow planner."),
            HumanMessage(content=prompt)
        ]
        messages = [
                    {
                      "role": "system",
                      "content": "You are an expert workflow planner."
                    },
                    {
                      "role": "user",
                      "content": prompt
                    }
                  ]
        response = ClientSingleton.execute(messages)
        print(response)
        # Parse JSON from response
        import re
        json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
        if json_match:
            api_plan = json.loads(json_match.group(0))
        else:
            api_plan = json.loads(response.content)
        
        print(f"✓ Created plan with {len(api_plan)} steps")
        for step in api_plan:
            print(f"  Step {step['step']}: {step['tool']}")
        
        state['api_plan'] = api_plan
        state['status'] = "planning"
        return state


# ============================================================================
# AGENT 2: SCHEMA AGENT
# ============================================================================

class SchemaAgent:
    """
    Agent responsible for identifying input parameters
    """
    
    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        """
        Identify all base-level input parameters
        """
        print("\n" + "=" * 80)
        print("🤖 SCHEMA AGENT: Identifying input parameters...")
        print("=" * 80)
        
        prompt = f"""Identify all BASE-LEVEL input parameters for this workflow.

SOP:
{state['sop']}

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Available Tools:
{state['tools_formatted']}

Base-level inputs are parameters that:
- Are NOT outputs from other tools
- Must be provided by the user at workflow start
- Cannot be derived from other steps

Return a JSON array:
[
  {{
    "name": "patient_id",
    "type": "string",
    "required": true,
    "description": "Unique identifier for the patient"
  }},
  ...
]

Return ONLY the JSON array."""

        messages = [
            SystemMessage(content="You are an expert data schema analyst."),
            HumanMessage(content=prompt)
        ]
        messages = [
                    {
                      "role": "system",
                      "content": "You are an expert data schema analyst."
                    },
                    {
                      "role": "user",
                      "content": prompt
                    }
                  ]        
        response = ClientSingleton.execute(messages)
        
        # Parse JSON
        import re
        json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
        if json_match:
            input_schema = json.loads(json_match.group(0))
        else:
            input_schema = json.loads(response.content)
        
        print(f"✓ Identified {len(input_schema)} input parameters")
        for param in input_schema:
            req = "required" if param.get('required') else "optional"
            print(f"  • {param['name']} ({param['type']}, {req})")
        
        state['input_schema'] = input_schema
        return state


# ============================================================================
# AGENT 3: CODE GENERATOR AGENT
# ============================================================================

class CodeGeneratorAgent:
    """
    Agent responsible for generating executable Python code
    """
    
    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        """
        Generate executable Python code from the plan
        """
        print("\n" + "=" * 80)
        print("🤖 CODE GENERATOR AGENT: Generating Python code...")
        print("=" * 80)
        
        prompt = f"""Generate executable Python code for this workflow.

SOP:
{state['sop']}

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Input Parameters:
{json.dumps(state['input_schema'], indent=2)}

Available Tools:
{state['tools_formatted']}

CRITICAL REQUIREMENTS:
1. Import: from global_tool_functions import execute_tool_with_structured_output
2. ALWAYS use execute_tool_with_structured_output(tool_name, tool_input)
3. Extract results from returned dictionary using correct key names
4. Create a function called 'workflow' that takes input_data dict
5. Include proper error handling with try-except
6. Add descriptive comments for each step
7. Return the final result

TEMPLATE:
```python
from global_tool_functions import execute_tool_with_structured_output

def workflow(input_data):
    \"\"\"
    Auto-generated workflow from SOP
    
    Args:
        input_data: Dictionary containing all required inputs
        
    Returns:
        Final workflow result
    \"\"\"
    try:
        # Step 1: [Description]
        result1 = execute_tool_with_structured_output(
            tool_name="toolName",
            tool_input={{
                "param1": input_data["param1"],
                "param2": input_data["param2"]
            }}
        )
        var1 = result1["output_key"]
        
        # Continue for all steps...
        
        return final_result
        
    except Exception as e:
        return {{"error": str(e), "status": "failed"}}
```

Generate the complete code. Return ONLY the Python code, no markdown formatting."""

        messages = [
            SystemMessage(content="You are an expert Python code generator specializing in workflow automation."),
            HumanMessage(content=prompt),
        ]
        
        messages = [
                    {
                      "role": "system",
                      "content": "You are an expert Python code generator specializing in workflow automation."
                    },
                    {
                      "role": "user",
                      "content": prompt
                    }
                  ]
        response = ClientSingleton.execute(messages)
        code = response.content
        
        # Extract from markdown if present
        import re
        code_match = re.search(r'```python\s*(.*?)\s*```', code, re.DOTALL)
        if code_match:
            code = code_match.group(1)
        
        print(f"✓ Generated {len(code.split(chr(10)))} lines of code")
        
        state['generated_code'] = code
        state['status'] = "generating"
        return state


# ============================================================================
# AGENT 4: VALIDATOR AGENT
# ============================================================================

class ValidatorAgent:
    """
    Agent responsible for validating and refining generated code
    """

    
    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        """
        Validate the generated code and suggest improvements
        """
        print("\n" + "=" * 80)
        print("🤖 VALIDATOR AGENT: Validating code...")
        print("=" * 80)
        
        prompt = f"""Review this generated code for correctness and best practices.

Generated Code:
```python
{state['generated_code']}
```

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Input Schema:
{json.dumps(state['input_schema'], indent=2)}

Check for:
1. All steps from API plan are implemented
2. Correct use of execute_tool_with_structured_output
3. Proper extraction of output values with correct keys
4. All input parameters are used correctly
5. Error handling is present
6. No syntax errors
7. Logical flow matches the SOP

Return a JSON object:
{{
    "is_valid": true/false,
    "issues": ["issue1", "issue2", ...],
    "suggestions": ["suggestion1", ...],
    "corrected_code": "...corrected Python code if needed..."
}}

Return ONLY the JSON object."""

        #messages = [
        #    SystemMessage(content="You are an expert code reviewer and validator."),
        #    HumanMessage(content=prompt)
        #]
        messages = [
                    {
                      "role": "system",
                      "content": "You are an expert code reviewer and validator."
                    },
                    {
                      "role": "user",
                      "content": prompt
                    }
                  ]     
        print('ValidatorAgent#####################################')
        response = ClientSingleton.execute(messages)
        print(f'response={response}')
        try:
            # Parse JSON
            import re
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                validation = json.loads(json_match.group(0))
            else:
                validation = json.loads(response.content)
            
            state['validation_result'] = validation
            
            if validation.get('is_valid'):
                print("✓ Code validation passed")
                state['final_code'] = state['generated_code']
                state['status'] = "validating"
            else:
                print(f"⚠️  Found {len(validation.get('issues', []))} issues")
                for issue in validation.get('issues', []):
                    print(f"  - {issue}")
                
                if validation.get('corrected_code'):
                    print("✓ Using corrected code")
                    state['final_code'] = validation['corrected_code']
                    state['status'] = "complete"
                else:
                    state['final_code'] = state['generated_code']
                    state['status'] = "validating"
        except:
            state['status'] = "validating"
        
        return state

def should_retry(state: SOPConverterState) -> Literal["retry", "complete", "failed"]:
    """
    Routing function that determines next step based on orchestrator decision
    """
    status = state.get('status', '')
    
    if status == "complete":
        return "complete"
    elif status == "failed":
        return "failed"
    elif status == "retry":
        return "retry"
    else:
        return "complete"
# ============================================================================
# AGENT 5: ORCHESTRATOR AGENT (NEW!)
# ============================================================================

class OrchestratorAgent:
    """
    Orchestrator agent that makes decisions about workflow routing
    Decides whether to retry, continue, or fail
    """
    
    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        print("\n" + "=" * 80)
        print("🎯 ORCHESTRATOR AGENT: Making decision...")
        print("=" * 80)
        
        validation = state.get('validation_result', {})
        retry_count = state.get('retry_count', 0)
        max_retries = state.get('max_retries', 3)
        
        print(f"  Current retry count: {retry_count}/{max_retries}")
        print(f"  Validation status: {'PASS' if validation.get('is_valid') else 'FAIL'}")
        
        if validation.get('is_valid'):
            print("  Decision: ✅ ACCEPT - Code is valid")
            state['status'] = "complete"
            return state
        
        # Check if we should retry
        if retry_count >= max_retries:
            print(f"  Decision: ❌ FAIL - Max retries ({max_retries}) reached")
            state['status'] = "failed"
            state['error'] = f"Failed to generate valid code after {max_retries} attempts"
            return state
        
        # Analyze severity
        state['retry_count'] = retry_count + 1
        state['status'] = "retry"
        
        return state
# ============================================================================
# LANGGRAPH WORKFLOW DEFINITION
# ============================================================================

class SOPToCodeConverter:
    """
    Main LangGraph workflow orchestrator
    """
    
    def __init__(self):
        
        # Initialize agents
        self.planner = PlannerAgent()
        self.schema_agent = SchemaAgent()
        self.code_generator = CodeGeneratorAgent()
        self.validator = ValidatorAgent()
        self.orchestrator = OrchestratorAgent()
        
        # Build graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph state graph
        """
        # Create graph
        workflow = StateGraph(SOPConverterState)
        
        # Add nodes (agents)
        workflow.add_node("planner", self.planner)
        workflow.add_node("schema", self.schema_agent)
        workflow.add_node("generator", self.code_generator)
        workflow.add_node("validator", self.validator)
        workflow.add_node("orchestrator", self.orchestrator)
        
        # Define edges (workflow)
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "schema")
        workflow.add_edge("schema", "generator")
        workflow.add_edge("generator", "validator")
        workflow.add_edge("validator", "orchestrator")

       # Conditional routing from orchestrator
        workflow.add_conditional_edges(
            "orchestrator",
            should_retry,
            {
                "retry": "generator",      # Go back to generator
                "complete": END,           # Success - end workflow
                "failed": END              # Max retries - end workflow
            }
        )
        
        #return workflow.compile(checkpointer=memory)
        return workflow.compile()
    
    def convert(self, sop: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert SOP to executable code using multi-agent workflow
        
        Args:
            sop: Standard Operating Procedure text
            tools: List of available tools
            
        Returns:
            Dictionary with final code and metadata
        """
        print("\n" + "=" * 80)
        print("🚀 STARTING LANGGRAPH WORKFLOW")
        print("=" * 80)
        
        # Initialize state
        initial_state = {
            "sop": sop,
            "tools": tools,
            "tools_formatted": format_tools_for_llm(tools),
            "api_plan": [],
            "input_schema": [],
            "generated_code": "",
            "validation_result": {},
            "final_code": "",
            "error": "",
            "max_retries" : 3,
            "retry_count" : 0,
            "status" : "planning"            
        }
        
        # Run the graph
        #final_state = self.graph.invoke(initial_state,  
        #                                config={"configurable": {"thread_id": "1"}},
        #                                interrupt_before=["validator"])
        final_state = self.graph.invoke(initial_state)        
        print("\n" + "=" * 80)
        print("✅ WORKFLOW COMPLETE")
        print("=" * 80)
        
        return {
            "code": final_state['final_code'],
            "api_plan": final_state['api_plan'],
            "input_schema": final_state['input_schema'],
            "validation": final_state['validation_result']
        }


# ============================================================================
# VISUALIZATION HELPER
# ============================================================================

def visualize_graph(converter: SOPToCodeConverter):
    """
    Visualize the LangGraph workflow
    """
    try:
        from IPython.display import Image, display
        display(Image(converter.graph.get_graph().draw_mermaid_png()))
    except:
        print("\nWorkflow Graph:")
        print("  planner → schema → generator → validator → END")

