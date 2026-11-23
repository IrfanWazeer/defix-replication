import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from config.settings import settings
from src.graph import create_defix_graph
from src.single_prompt import run_single_prompt, run_single_prompt_loop
from src.utils.metrics import build_v2_metrics


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run benchmark_v2 instances.")
    parser.add_argument(
        "--mode",
        choices=("full", "single_prompt", "single_prompt_loop"),
        default="full",
    )
    parser.add_argument(
        "--validation-mode",
        choices=("strict", "hybrid"),
        default=settings.VALIDATION_MODE,
    )
    parser.add_argument("--hops", type=int, choices=(0, 1, 2), default=2)
    parser.add_argument("--sanitizer", choices=("on", "off"), default="on")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("results_v2/results.json"))
    parser.add_argument("--only", nargs="+", help="Limit to these instance IDs.")
    parser.add_argument(
        "--benchmark",
        default="benchmark_v2",
        help="Benchmark folder containing instances/ (default: benchmark_v2).",
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return args


def _load_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        contents = json.load(file)
    if not isinstance(contents, list) or not all(isinstance(row, dict) for row in contents):
        raise ValueError(f"{path} must contain a JSON list of result objects")
    return contents


def _save_results(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(rows, file, indent=2)
            file.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _run_id(mode: str, validation_mode: str, hops: int, sanitizer: str, index: int) -> str:
    return f"{mode}-{validation_mode}-h{hops}-s{sanitizer}-r{index:03d}"


def _is_retryable_error(error: Exception) -> bool:
    error_details = f"{type(error).__name__} {error}".lower()
    return any(
        marker in error_details
        for marker in ("connection", "timeout", "429", "rate limit", "ratelimit")
    )


def _initial_state(
    instance_dir: Path,
    metadata: dict[str, Any],
    raw_log: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "raw_log": raw_log,
        "repository_context": "",
        "repo_dir": str(instance_dir / "repo"),
        "test_cmd": metadata["test_cmd"],
        "parsed_error": None,
        "root_cause_analysis": None,
        "proposed_patch": None,
        "parse_ok": False,
        "target_file": None,
        "target_line": None,
        "context_files": [],
        "context_truncated": False,
        "context_hops": args.hops,
        "sanitizer_mode": args.sanitizer,
        "sanitizer_report": {},
        "validation_mode": args.validation_mode,
        "final_status": "",
        "llm_usage": [],
        "test_passed": False,
        "exec_passed": None,
        "patch_applied": None,
        "llm_verdict": "",
        "decision_source": "",
        "validation_feedback": None,
        "iteration_count": 0,
        "max_iterations": settings.MAX_RETRY_ITERATIONS,
        "agent_history": [],
    }


def main() -> int:
    args = _arguments()
    repository_root = Path(__file__).resolve().parent
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    instances_root = repository_root / args.benchmark / "instances"
    instance_dirs = sorted(path for path in instances_root.iterdir() if path.is_dir())
    if args.only:
        requested = set(args.only)
        known = {path.name for path in instance_dirs}
        unknown = requested - known
        if unknown:
            raise ValueError(f"Unknown benchmark instance IDs: {', '.join(sorted(unknown))}")
        instance_dirs = [path for path in instance_dirs if path.name in requested]

    rows = _load_existing(args.out)
    retry_rows = [row for row in rows if row.get("final_status") == "ERROR"]
    if retry_rows:
        print(f"Retrying {len(retry_rows)} previously errored result row(s).")
    rows = [row for row in rows if row.get("final_status") != "ERROR"]
    _save_results(args.out, rows)
    existing_pairs = {
        (row.get("run_id"), row.get("instance_id"))
        for row in rows
    }

    for run_index in range(1, args.runs + 1):
        run_id = _run_id(
            args.mode,
            args.validation_mode,
            args.hops,
            args.sanitizer,
            run_index,
        )
        for instance_dir in instance_dirs:
            pair = (run_id, instance_dir.name)
            if pair in existing_pairs:
                continue

            started = time.perf_counter()
            metadata: dict[str, Any] = {}
            final_state: dict[str, Any] | None = None
            try:
                metadata = json.loads(
                    (instance_dir / "meta.json").read_text(encoding="utf-8")
                )
                raw_log = (instance_dir / "failing.log").read_text(encoding="utf-8")
                state = _initial_state(instance_dir, metadata, raw_log, args)
                for wait_seconds in (20, 60, None):
                    try:
                        if args.mode == "full":
                            final_state = create_defix_graph().invoke(state)
                        elif args.mode == "single_prompt_loop":
                            final_state = run_single_prompt_loop(state)
                        else:
                            final_state = run_single_prompt(state)
                        break
                    except Exception as error:
                        if wait_seconds is None or not _is_retryable_error(error):
                            raise
                        time.sleep(wait_seconds)
                duration = time.perf_counter() - started
                result = build_v2_metrics(
                    instance_dir.name,
                    final_state,
                    duration,
                    mode=args.mode,
                    validation_mode=args.validation_mode,
                    context_hops=0 if args.mode == "single_prompt" else args.hops,
                    sanitizer=args.sanitizer,
                    fault_type=metadata.get("fault_type"),
                    root_cause_hops=metadata.get("root_cause_hops"),
                    run_id=run_id,
                )
            except Exception as error:
                duration = time.perf_counter() - started
                result = {
                    "instance_id": instance_dir.name,
                    "mode": args.mode,
                    "validation_mode": args.validation_mode,
                    "context_hops": 0 if args.mode == "single_prompt" else args.hops,
                    "sanitizer": args.sanitizer,
                    "sanitizer_report": {
                        "had_fence": False,
                        "had_prose": False,
                        "headers_ok": False,
                        "changed": False,
                        "hunk_counts_fixed": False,
                    },
                    "final_status": "ERROR",
                    "parse_ok": None,
                    "context_truncated": False,
                    "accepted": False,
                    "true_exec_pass": None,
                    "false_positive": False,
                    "fault_type": metadata.get("fault_type"),
                    "root_cause_hops": metadata.get("root_cause_hops"),
                    "run_id": run_id,
                    "prompt_tokens_actual": None,
                    "completion_tokens_actual": None,
                    "iterations": 0,
                    "execution_time_seconds": duration,
                    "pass_at_1": False,
                    "error": str(error),
                }

            state_for_logging = final_state or {}
            result.update({
                "patch_text": str(state_for_logging.get("proposed_patch") or ""),
                "raw_llm_output": str(state_for_logging.get("raw_llm_output") or ""),
                "patch_applied": bool(state_for_logging.get("patch_applied", False)),
                "sandbox_stdout": str(state_for_logging.get("sandbox_stdout") or "")[:20000],
                "sandbox_stderr": str(state_for_logging.get("sandbox_stderr") or "")[:20000],
                "llm_verdict": (
                    (state_for_logging.get("llm_verdict") or None)
                    if args.mode == "full"
                    else "NOT_RUN" if args.mode == "single_prompt_loop"
                    else None
                ),
                "git_commit": git_commit,
                "model": settings.DEFAULT_MODEL,
                "llm_provider": settings.LLM_PROVIDER,
            })
            rows.append(result)
            existing_pairs.add(pair)
            _save_results(args.out, rows)
            print(f"{instance_dir.name}: {result.get('final_status')} ({result.get('error') or 'ok'})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())