from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from config.prompts import XAI_DIAGNOSER_PROMPT
from src.state import DEFIXState
from src.utils.llm_factory import get_llm
from src.utils.token_usage import append_token_usage

def xai_diagnoser_node(state: DEFIXState) -> Dict[str, Any]:
    """
    Agent 2 Node: Performs Explainable Root Cause Analysis (RCA) and maps failure trajectories.
    """
    parsed_error = state.get("parsed_error", "")
    repo_context = state.get("repository_context", "No repository context provided.")
    validation_feedback = state.get("validation_feedback", "")
    
    prompt_input = f"""Extracted Error Context:
{parsed_error}

Repository Context:
{repo_context}
"""
    if validation_feedback:
        prompt_input += f"\nPrevious Patch Validation Feedback (Iterative Retry):\n{validation_feedback}\n"
    
    llm = get_llm()
    
    messages = [
        SystemMessage(content=XAI_DIAGNOSER_PROMPT),
        HumanMessage(content=prompt_input)
    ]
    
    response = llm.invoke(messages)
    diagnosis_output = response.content.strip()
    
    history_entry = {
        "agent": "XAIDiagnoserAgent",
        "action": "Generated Root Cause & XAI Trajectory",
        "iteration": state.get("iteration_count", 0)
    }
    
    current_history = state.get("agent_history", [])
    current_history.append(history_entry)
    
    return {
        "root_cause_analysis": diagnosis_output,
        "llm_usage": append_token_usage(state, response),
        "agent_history": current_history
    }