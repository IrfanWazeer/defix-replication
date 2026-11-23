import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config.prompts import SINGLE_PROMPT
from config.settings import settings
from src.agents.log_parser import log_parser_node
from src.state import DEFIXState
from src.utils.diff_sanitizer import sanitize_patch
from src.utils.docker_runner import run_patch_in_workspace
from src.utils.llm_factory import get_llm
from src.utils.token_usage import append_token_usage

_RETRY_SYSTEM_PROMPT = (
    SINGLE_PROMPT
    + "When a previous patch and sandbox feedback are provided, use them to improve your next patch.\n"
)


def _sanitize_and_execute(
    state: dict[str, Any],
    raw_llm_output: str,
) -> tuple[str, dict[str, bool], dict[str, Any]]:
    proposed_patch = raw_llm_output.strip()
    sanitizer_mode = str(
        state.get("sanitizer_mode", os.getenv("DEFIX_SANITIZER", "on"))
    ).lower()
    clean_patch, sanitizer_report = sanitize_patch(proposed_patch)
    if sanitizer_mode != "off":
        proposed_patch = clean_patch
    else:
        sanitizer_report["changed"] = False
        sanitizer_report["hunk_counts_fixed"] = False

    execution = run_patch_in_workspace(
        state.get("repo_dir") or ".",
        proposed_patch,
        state.get("test_cmd") or "python -m unittest discover tests",
        patch_is_sanitized=sanitizer_mode != "off",
    )
    return proposed_patch, sanitizer_report, execution


def run_single_prompt(initial_state: DEFIXState) -> dict[str, Any]:
    """Run one repair-model call and one sandbox validation."""
    state = dict(initial_state)
    state["context_hops"] = 0
    state.update(log_parser_node(state))
    prompt_input = (
        f"Raw failure log:\n{state.get('raw_log', '')}\n\n"
        f"Target file source (the only repository source provided):\n"
        f"{state.get('repository_context', '')}"
    )
    response = get_llm().invoke([
        SystemMessage(content=SINGLE_PROMPT),
        HumanMessage(content=prompt_input),
    ])
    raw_llm_output = response.content
    proposed_patch, sanitizer_report, execution = _sanitize_and_execute(
        state, raw_llm_output
    )
    sanitizer_mode = str(
        state.get("sanitizer_mode", os.getenv("DEFIX_SANITIZER", "on"))
    ).lower()
    accepted = bool(execution["exec_passed"])
    history = list(state.get("agent_history", []))
    history.append({
        "agent": "SinglePromptAgent",
        "action": "Generated and validated one repair patch",
        "iteration": 1,
    })
    state.update({
        "proposed_patch": proposed_patch,
        "raw_llm_output": raw_llm_output,
        "sanitizer_mode": sanitizer_mode,
        "sanitizer_report": sanitizer_report,
        "patch_applied": execution["patch_applied"],
        "sandbox_stdout": execution["stdout"],
        "sandbox_stderr": execution["stderr"],
        "exec_passed": execution["exec_passed"],
        "test_passed": accepted,
        "validation_feedback": execution["log"],
        "decision_source": "exec" if accepted else "none",
        "llm_verdict": "NOT_RUN",
        "iteration_count": 1,
        "final_status": "RESOLVED" if accepted else "HALTED_MAX_ITER",
        "llm_usage": append_token_usage(state, response),
        "agent_history": history,
    })
    return state


def run_single_prompt_loop(initial_state: DEFIXState) -> dict[str, Any]:
    """Retry a single-prompt repair using only deterministic sandbox feedback."""
    state = dict(initial_state)
    state.update(log_parser_node(state))
    prompt_input = (
        f"Raw failure log:\n{state.get('raw_log', '')}\n\n"
        f"Target file source and repository context:\n"
        f"{state.get('repository_context', '')}"
    )
    history = list(state.get("agent_history", []))
    llm_usage = list(state.get("llm_usage", []))
    previous_patch = ""
    previous_execution: dict[str, Any] | None = None

    for iteration in range(1, settings.MAX_RETRY_ITERATIONS + 1):
        attempt_input = prompt_input
        if previous_execution is not None:
            stdout = str(previous_execution.get("stdout", ""))[:3000]
            stderr = str(previous_execution.get("stderr", ""))[:3000]
            attempt_input += (
                f"\n\nPrevious patch:\n{previous_patch}\n\n"
                "Previous sandbox feedback:\n"
                f"stdout (truncated to 3000 characters):\n{stdout}\n"
                f"stderr (truncated to 3000 characters):\n{stderr}"
            )

        response = get_llm().invoke([
            SystemMessage(
                content=SINGLE_PROMPT if iteration == 1 else _RETRY_SYSTEM_PROMPT
            ),
            HumanMessage(content=attempt_input),
        ])
        raw_llm_output = response.content
        proposed_patch, sanitizer_report, execution = _sanitize_and_execute(
            state, raw_llm_output
        )
        llm_usage = append_token_usage({"llm_usage": llm_usage}, response)
        history.append({
            "agent": "SinglePromptLoopAgent",
            "action": "Generated and validated a repair patch",
            "iteration": iteration,
        })

        accepted = bool(execution["exec_passed"])
        state.update({
            "proposed_patch": proposed_patch,
            "raw_llm_output": raw_llm_output,
            "sanitizer_mode": str(
                state.get("sanitizer_mode", os.getenv("DEFIX_SANITIZER", "on"))
            ).lower(),
            "sanitizer_report": sanitizer_report,
            "patch_applied": execution["patch_applied"],
            "sandbox_stdout": execution["stdout"],
            "sandbox_stderr": execution["stderr"],
            "exec_passed": execution["exec_passed"],
            "test_passed": accepted,
            "validation_feedback": execution["log"],
            "decision_source": "exec" if accepted else "none",
            "llm_verdict": "NOT_RUN",
            "iteration_count": iteration,
            "final_status": (
                "RESOLVED"
                if accepted
                else (
                    "HALTED_MAX_ITER"
                    if iteration == settings.MAX_RETRY_ITERATIONS
                    else ""
                )
            ),
            "llm_usage": llm_usage,
            "agent_history": history,
        })
        if accepted:
            break
        previous_patch = proposed_patch
        previous_execution = execution

    return state
