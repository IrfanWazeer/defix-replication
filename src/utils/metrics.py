import json
import time
import os
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from config.settings import settings

@dataclass
class BenchmarkResult:
    instance_id: str
    pass_at_1: bool
    resolved: bool
    iterations: int
    execution_time_seconds: float
    estimated_prompt_tokens: int
    estimated_completion_tokens: int
    patch_generated: str
    error_type: str
    exec_passed: Optional[bool]
    patch_applied: Optional[bool]
    llm_verdict: str
    decision_source: str
    model_name: Optional[str]
    temperature: float
    mode: Optional[str] = None
    validation_mode: Optional[str] = None
    context_hops: Optional[int] = None
    sanitizer: Optional[str] = None
    final_status: Optional[str] = None
    parse_ok: Optional[bool] = None
    context_truncated: Optional[bool] = None
    accepted: bool = False
    true_exec_pass: Optional[bool] = None
    false_positive: bool = False
    fault_type: Optional[str] = None
    root_cause_hops: Optional[int] = None
    run_id: Optional[str] = None
    prompt_tokens_actual: Optional[int] = None
    completion_tokens_actual: Optional[int] = None


def actual_token_totals(final_state: Dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    usage = final_state.get("llm_usage", [])
    if not usage:
        return None, None
    prompt_values = [entry.get("prompt_tokens") for entry in usage]
    completion_values = [entry.get("completion_tokens") for entry in usage]
    if any(type(value) is not int for value in prompt_values + completion_values):
        return None, None
    return sum(prompt_values), sum(completion_values)


def build_v2_metrics(
    instance_id: str,
    final_state: Dict[str, Any],
    duration: float,
    *,
    mode: str,
    validation_mode: str,
    context_hops: int,
    sanitizer: str,
    fault_type: Optional[str],
    root_cause_hops: Optional[int],
    run_id: str,
) -> Dict[str, Any]:
    accepted = bool(final_state.get("test_passed", False))
    true_exec_pass = final_state.get("exec_passed")
    prompt_tokens, completion_tokens = actual_token_totals(final_state)
    return {
        "instance_id": instance_id,
        "mode": mode,
        "validation_mode": validation_mode,
        "context_hops": context_hops,
        "sanitizer": sanitizer,
        "sanitizer_report": {
            "had_fence": bool(final_state.get("sanitizer_report", {}).get("had_fence", False)),
            "had_prose": bool(final_state.get("sanitizer_report", {}).get("had_prose", False)),
            "headers_ok": bool(final_state.get("sanitizer_report", {}).get("headers_ok", False)),
            "changed": bool(final_state.get("sanitizer_report", {}).get("changed", False)),
            "hunk_counts_fixed": bool(
                final_state.get("sanitizer_report", {}).get("hunk_counts_fixed", False)
            ),
        },
        "final_status": final_state.get("final_status"),
        "parse_ok": final_state.get("parse_ok"),
        "context_truncated": final_state.get("context_truncated", False),
        "accepted": accepted,
        "true_exec_pass": true_exec_pass,
        "false_positive": accepted and not bool(true_exec_pass),
        "fault_type": fault_type,
        "root_cause_hops": root_cause_hops,
        "run_id": run_id,
        "prompt_tokens_actual": prompt_tokens,
        "completion_tokens_actual": completion_tokens,
        "iterations": final_state.get("iteration_count", 0),
        "execution_time_seconds": duration,
        "pass_at_1": accepted and final_state.get("iteration_count", 0) <= 1,
        "error": None,
    }

class MetricsCollector:
    def __init__(self, output_file: str = "benchmark_results.json"):
        self.output_file = output_file
        self.results: List[BenchmarkResult] = []

    def record_run(
        self,
        instance_id: str,
        final_state: Dict[str, Any],
        duration: float,
        error_type: str = "ImportError"
    ) -> BenchmarkResult:
        iterations = final_state.get("iteration_count", 0)
        passed = final_state.get("test_passed", False)
        
        # Pass@1 check: Resolved on or before 1st iteration
        pass_at_1 = passed and (iterations <= 1)

        approx_prompt_tokens = len(str(final_state)) // 4
        approx_completion_tokens = len(str(final_state.get("proposed_patch", ""))) // 4
        prompt_tokens_actual, completion_tokens_actual = actual_token_totals(final_state)
        true_exec_pass = final_state.get("exec_passed")

        result = BenchmarkResult(
            instance_id=instance_id,
            pass_at_1=pass_at_1,
            resolved=passed,
            iterations=iterations,
            execution_time_seconds=round(duration, 2),
            estimated_prompt_tokens=approx_prompt_tokens,
            estimated_completion_tokens=approx_completion_tokens,
            patch_generated=str(final_state.get("proposed_patch", "")),
            error_type=error_type,
            exec_passed=final_state.get("exec_passed"),
            patch_applied=final_state.get("patch_applied"),
            llm_verdict=final_state.get("llm_verdict", ""),
            decision_source=final_state.get("decision_source", ""),
            model_name=os.getenv("DEFIX_MODEL"),
            temperature=settings.TEMPERATURE,
            mode=final_state.get("mode"),
            validation_mode=final_state.get("validation_mode"),
            context_hops=final_state.get("context_hops"),
            sanitizer=final_state.get("sanitizer_mode"),
            final_status=final_state.get("final_status"),
            parse_ok=final_state.get("parse_ok"),
            context_truncated=final_state.get("context_truncated"),
            accepted=passed,
            true_exec_pass=true_exec_pass,
            false_positive=passed and not bool(true_exec_pass),
            fault_type=final_state.get("fault_type"),
            root_cause_hops=final_state.get("root_cause_hops"),
            run_id=final_state.get("run_id"),
            prompt_tokens_actual=prompt_tokens_actual,
            completion_tokens_actual=completion_tokens_actual,
        )
        self.results.append(result)
        self._save_to_disk()
        return result

    def _save_to_disk(self):
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self.results], f, indent=2)

    def print_summary(self):
        if not self.results:
            print("No evaluation runs recorded.")
            return

        total_runs = len(self.results)
        passed_runs = sum(1 for r in self.results if r.resolved)
        pass_1_runs = sum(1 for r in self.results if r.pass_at_1)
        avg_time = sum(r.execution_time_seconds for r in self.results) / total_runs
        avg_iterations = sum(r.iterations for r in self.results) / total_runs

        print("\n" + "="*60)
        print("               DEFIX BENCHMARK EVALUATION REPORT             ")
        print("="*60)
        print(f"Total Test Instances : {total_runs}")
        print(f"Overall Pass Rate    : {passed_runs / total_runs * 100:.2f}% ({passed_runs}/{total_runs})")
        print(f"Pass@1 Rate          : {pass_1_runs / total_runs * 100:.2f}% ({pass_1_runs}/{total_runs})")
        print(f"Mean Time to Repair  : {avg_time:.2f} seconds")
        print(f"Avg Iterations/Run   : {avg_iterations:.2f}")
        print("="*60 + "\n")