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
from planner_agent import PlannerAgent, PlannerAgentError
from schema_agent import SchemaAgent, SchemaAgentError
from codegeneration_agent import CodeGeneratorAgent, CodeGeneratorAgentError
from validation_agent import ValidatorAgent, ValidatorAgentError
from orchestrator_agent import OrchestratorAgent, OrchestratorError
from sop_state import SOPConverterState
import logging
logger = logging.getLogger(__name__)

memory = MemorySaver()

# Map every custom exception to a clean exit message
AGENT_EXCEPTIONS = (
    PlannerAgentError,
    SchemaAgentError,
    CodeGeneratorAgentError,
    ValidatorAgentError,
    OrchestratorError,
)

# ============================================================================
# ROUTING FUNCTION
# ============================================================================

def should_retry(state: SOPConverterState) -> Literal["retry", "complete", "failed"]:
    """
    Routing function for LangGraph edge.
    Reads the status set by OrchestratorAgent and directs the graph accordingly.
    """
    status = state.get("status", "")
    decision = state.get("orchestrator_decision", {})

    logger.info(
        f"Router: status='{status}' | reason='{decision.get('reason', 'n/a')}'"
    )

    if status == "complete":
        return "complete"
    elif status == "failed":
        return "failed"
    elif status == "retry":
        return "retry"
    else:
        logger.warning(f"Router: Unrecognised status '{status}' — defaulting to failed.")
        return "failed"

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
        try:
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

        except AGENT_EXCEPTIONS as exc:
                # Known agent failure
                agent_name = type(exc).__name__.replace("Error", "Agent")
                logger.error(f"Pipeline stopped at {agent_name}: {exc}")
                return {
                    **initial_state,
                    "status": "failed",
                    "error": {
                        "agent":   agent_name,
                        "type":    type(exc).__name__,
                        "message": str(exc),
                    },
                    "final_code": None,
                }
        except Exception as exc:
            # Truly unexpected — log full traceback
            logger.exception(f"Pipeline crashed unexpectedly: {exc}")
            return {
                **initial_state,
                "status": "failed",
                "error": {
                    "agent":   "unknown",
                    "type":    type(exc).__name__,
                    "message": str(exc),
                },
                "final_code": None,
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

