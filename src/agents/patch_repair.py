from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from config.prompts import PATCH_REPAIR_PROMPT
from src.state import DEFIXState
from src.utils.llm_factory import get_llm
from src.utils.token_usage import append_token_usage

def patch_repair_node(state: DEFIXState) -> Dict[str, Any]:
    """
    Agent 3 Node: Proposes precise code or configuration fixes based on XAI diagnosis.
    """
    parsed_error = state.get("parsed_error", "")
    root_cause = state.get("root_cause_analysis", "")
    repo_context = state.get("repository_context", "")
    
    prompt_input = f"""Error Details:
{parsed_error}

XAI Root Cause Diagnosis:
{root_cause}

Repository Context:
{repo_context}
"""
    
    llm = get_llm()
    
    messages = [
        SystemMessage(content=PATCH_REPAIR_PROMPT),
        HumanMessage(content=prompt_input)
    ]
    
    response = llm.invoke(messages)
    raw_llm_output = response.content
    proposed_patch = raw_llm_output.strip()
    
    history_entry = {
        "agent": "PatchRepairAgent",
        "action": "Generated Repair Patch Candidate",
        "iteration": state.get("iteration_count", 0)
    }
    
    current_history = state.get("agent_history", [])
    current_history.append(history_entry)
    
    return {
        "proposed_patch": proposed_patch,
        "raw_llm_output": raw_llm_output,
        "llm_usage": append_token_usage(state, response),
        "agent_history": current_history
    }