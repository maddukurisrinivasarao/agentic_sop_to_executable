# -*- coding: utf-8 -*-
"""
LangGraph-based SOP to Executable Code Converter
Uses multi-agent system with state graph for workflow conversion

Architecture:
- PlannerAgent: Analyzes SOP and creates execution plan
- SchemaAgent: Identifies input parameters needed
- CodeGeneratorAgent: Generates executable Python code
- ValidatorAgent: Validates and refines generated code
- Orchestrator: Orchestrates
"""


from typing import List, Dict, Any, Literal
from langgraph.graph import StateGraph, END
#from langchain_anthropic import ChatAnthropic
from tools_helper import format_tools_for_llm
from langgraph.checkpoint.memory import MemorySaver
from planner_agent import PlannerAgent
from schema_agent import SchemaAgent
from codegeneration_agent import CodeGeneratorAgent
from validation_agent import ValidatorAgent
from sop_state import SOPConverterState
import logging
logger = logging.getLogger(__name__)

memory = MemorySaver()


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
        if retry_count >= max_retries or 1:
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

