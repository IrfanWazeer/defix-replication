from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from config.prompts import VALIDATOR_PROMPT
from config.settings import settings
from src.state import DEFIXState
from src.utils.llm_factory import get_llm
from src.utils.docker_runner import run_patch_in_workspace
from src.utils.token_usage import append_token_usage
import os

def validator_node(state: DEFIXState) -> Dict[str, Any]:
    """
    Agent 4 Node: Hybrid Validation with Runtime Execution Priority
    """
    root_cause = state.get("root_cause_analysis", "")
    proposed_patch = state.get("proposed_patch", "")
    current_iteration = state.get("iteration_count", 0) + 1
    
    # 1. Dynamic Sandbox Runtime Execution
    sanitizer_mode = str(
        state.get("sanitizer_mode", os.getenv("DEFIX_SANITIZER", "on"))
    ).lower()
    execution = run_patch_in_workspace(
        state.get("repo_dir", "."),
        proposed_patch,
        state.get("test_cmd", "python -m unittest discover tests"),
        patch_is_sanitized=sanitizer_mode != "off",
    )
    exec_passed = execution["exec_passed"]
    patch_applied = execution["patch_applied"]
    exec_feedback = execution["log"]

    # 2. LLM Reasoning Check
    prompt_input = f"""Root Cause Analysis:\n{root_cause}\n\nProposed Patch:\n{proposed_patch}"""
    llm = get_llm()
    messages = [
        SystemMessage(content=VALIDATOR_PROMPT),
        HumanMessage(content=prompt_input)
    ]
    response = llm.invoke(messages)
    llm_evaluation_text = response.content.strip()
    upper_eval = llm_evaluation_text.upper()
    llm_passed = ("STATUS: PASSED" in upper_eval or "PASSED" in upper_eval) and "FAILED" not in upper_eval
    llm_verdict = "PASSED" if llm_passed else "FAILED"

    validation_mode = state.get("validation_mode", settings.VALIDATION_MODE)
    if validation_mode == "strict":
        final_passed = exec_passed
    else:
        final_passed = exec_passed or llm_passed

    decision_source = "exec" if exec_passed else "llm_only" if final_passed is True else "none"

    combined_feedback = f"--- Sandbox Runtime Execution ---\n{exec_feedback}\n\n--- LLM Verification ---\n{llm_evaluation_text}"

    history_entry = {
        "agent": "ValidatorAgent",
        "action": f"Validation Completed (Passed: {final_passed})",
        "iteration": current_iteration
    }
    
    current_history = state.get("agent_history", [])
    current_history.append(history_entry)
    
    result = {
        "test_passed": final_passed,
        "patch_applied": patch_applied,
        "exec_passed": exec_passed,
        "llm_verdict": llm_verdict,
        "sandbox_stdout": execution["stdout"],
        "sandbox_stderr": execution["stderr"],
        "decision_source": decision_source,
        "validation_feedback": combined_feedback,
        "iteration_count": current_iteration,
        "llm_usage": append_token_usage(state, response),
        "agent_history": current_history
    }
    if final_passed:
        result["final_status"] = "RESOLVED"
    elif current_iteration >= state.get("max_iterations", 3):
        result["final_status"] = "HALTED_MAX_ITER"
    return result