from typing import TypedDict, List, Optional, Dict, Any

class DEFIXState(TypedDict):
    """
    Global Shared State for DEFIX Multi-Agent Orchestration Framework.
    Maintains dynamic execution traces, diagnosis summaries, patches, and validation results.
    """
    # Raw Inputs
    raw_log: str                       # Original failing CI/CD build or execution log
    repository_context: str            # Relevant source code snippets or file paths
    repo_dir: Optional[str]
    test_cmd: Optional[str]
    target_file: Optional[str]
    target_line: Optional[int]
    parse_ok: bool
    context_files: List[str]
    context_truncated: bool
    context_hops: int
    sanitizer_mode: str
    sanitizer_report: Dict[str, bool]
    validation_mode: str
    final_status: str
    llm_usage: List[Dict[str, Optional[int]]]

    # Agent Processing Artifacts
    parsed_error: Optional[str]        # Filtered stack trace & error message (Log Parser)
    root_cause_analysis: Optional[str] # Detailed XAI explanation of the failure (XAI Diagnoser)
    proposed_patch: Optional[str]      # Generated code or config patch (Patch Repair Agent)
    raw_llm_output: Optional[str]
    
    # Execution Tracking & Retry Loop
    test_passed: bool                  # Status from Validator Agent
    exec_passed: Optional[bool]
    patch_applied: Optional[bool]
    sandbox_stdout: Optional[str]
    sandbox_stderr: Optional[str]
    llm_verdict: str
    decision_source: str
    validation_feedback: Optional[str] # Error feedback if proposed patch fails validation
    iteration_count: int               # Current retry loop iteration
    max_iterations: int                # Safety threshold to prevent infinite agent loops

    # Agent Trajectory / Memory Trace
    agent_history: List[Dict[str, Any]] # Audit trail of agent reasoning and tool executions