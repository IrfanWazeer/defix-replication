from langgraph.graph import StateGraph, END
from src.state import DEFIXState
from src.agents.log_parser import log_parser_node
from src.agents.xai_diagnoser import xai_diagnoser_node
from src.agents.patch_repair import patch_repair_node
from src.agents.validator import validator_node
from src.utils.diff_sanitizer import diff_sanitizer_node


def should_continue(state: DEFIXState) -> str:
    """
    Conditional Edge Router: Decides whether to end workflow or loop back to XAI Diagnoser.
    """
    if state.get("test_passed", False):
        return "end"
    
    if state.get("iteration_count", 0) >= state.get("max_iterations", 3):
        return "end"
    
    return "retry"


def route_after_parser(state: DEFIXState) -> str:
    return "continue" if state.get("parse_ok", False) else "end"


def create_defix_graph():
    """
    Constructs the DEFIX LangGraph Multi-Agent Self-Healing Workflow.
    """
    workflow = StateGraph(DEFIXState)
    
    # Add Agent Nodes
    workflow.add_node("log_parser", log_parser_node)
    workflow.add_node("xai_diagnoser", xai_diagnoser_node)
    workflow.add_node("patch_repair", patch_repair_node)
    workflow.add_node("diff_sanitizer", diff_sanitizer_node)
    workflow.add_node("validator", validator_node)
    
    # Set Sequential Flow
    workflow.set_entry_point("log_parser")
    workflow.add_conditional_edges(
        "log_parser",
        route_after_parser,
        {
            "end": END,
            "continue": "xai_diagnoser",
        },
    )
    workflow.add_edge("xai_diagnoser", "patch_repair")
    workflow.add_edge("patch_repair", "diff_sanitizer")
    workflow.add_edge("diff_sanitizer", "validator")
    
    # Conditional Edge for Self-Healing Iterative Loop
    workflow.add_conditional_edges(
        "validator",
        should_continue,
        {
            "end": END,
            "retry": "xai_diagnoser"
        }
    )
    
    return workflow.compile()