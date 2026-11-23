import json
import os
import re
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any, Dict, Optional

from src.state import DEFIXState
from src.utils.context_builder import build_context


_FRAME_PATTERN = re.compile(
    r'^\s*File "(?P<file>.+?)", line (?P<line>\d+), in (?P<function>.+?)\s*$',
    re.MULTILINE,
)
_EXCEPTION_PATTERN = re.compile(
    r"^(?P<type>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?::\s*(?P<message>.*))?$"
)


def _repository_files(repo_dir: Optional[str]) -> dict[str, Path]:
    if not repo_dir:
        return {}
    root = Path(repo_dir).resolve()
    files: dict[str, Path] = {}
    try:
        for candidate in root.rglob("*.py"):
            if candidate.is_file():
                try:
                    resolved = candidate.resolve()
                    relative = resolved.relative_to(root).as_posix()
                except (OSError, ValueError):
                    continue
                files[relative.casefold()] = resolved
    except OSError:
        return files
    return files


def _resolve_frame_file(
    file_name: str,
    repo_dir: Optional[str],
    repository_files: dict[str, Path],
) -> Optional[Path]:
    if not repo_dir:
        return None

    components = [part for part in re.split(r"[\\/]+", file_name) if part]
    root = Path(repo_dir).resolve()
    for first_component in range(len(components)):
        suffix = components[first_component:]
        # A drive prefix cannot be part of a path relative to repo_dir.
        if suffix and re.fullmatch(r"[A-Za-z]:", suffix[0]):
            continue
        relative = "/".join(suffix).casefold()
        resolved = repository_files.get(relative)
        if resolved is not None:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return resolved

    # Also handle paths already expressed relative to repo_dir.
    candidate = Path(file_name)
    if not candidate.is_absolute() and not PureWindowsPath(file_name).is_absolute():
        try:
            resolved = (root / candidate).resolve()
            relative = resolved.relative_to(root).as_posix().casefold()
            return repository_files.get(relative)
        except (OSError, ValueError):
            pass
    return None


def _parse_traceback(raw_log: str, repo_dir: Optional[str]) -> dict[str, Any]:
    repository_files = _repository_files(repo_dir)
    frames = []
    last_frame_end = 0
    for match in _FRAME_PATTERN.finditer(raw_log):
        last_frame_end = match.end()
        frame = {
            "file": match.group("file"),
            "line": int(match.group("line")),
            "function": match.group("function"),
        }
        resolved = _resolve_frame_file(frame["file"], repo_dir, repository_files)
        frame["resolved"] = resolved is not None
        frame["repo_file"] = (
            resolved.relative_to(Path(repo_dir).resolve()).as_posix()
            if resolved is not None and repo_dir
            else None
        )
        frames.append(frame)

    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    if frames:
        # The exception line is the first unindented line after the last frame
        # (frame source and caret lines are indented). This stays correct when
        # the message itself spans many lines (e.g. a long assertion diff).
        for line in raw_log[last_frame_end:].splitlines():
            if not line.strip() or line[0] in " \t":
                continue
            match = _EXCEPTION_PATTERN.fullmatch(line.strip())
            if match:
                exception_type = match.group("type")
                exception_message = match.group("message") or ""
            break
    if exception_type is None:
        for line in reversed(raw_log.splitlines()):
            candidate = line.strip()
            match = _EXCEPTION_PATTERN.fullmatch(candidate)
            if match:
                exception_type = match.group("type")
                exception_message = match.group("message") or ""
                break

    target_frame = next(
        (frame for frame in reversed(frames) if frame["resolved"]),
        None,
    )
    target_file: Optional[str] = (
        target_frame["repo_file"] if target_frame is not None else None
    )
    target_line: Optional[int] = None
    if target_frame is not None:
        target_line = target_frame["line"]

    return {
        "error_type": exception_type,
        "error_message": exception_message,
        "target_file": target_file,
        "target_line": target_line,
        "frames": frames,
    }


def _context_hops(state: DEFIXState) -> int:
    value = state.get("context_hops")
    if value is None:
        try:
            value = int(os.getenv("DEFIX_CONTEXT_HOPS", "2"))
        except ValueError:
            value = 2
    return min(2, max(0, int(value)))


def log_parser_node(state: DEFIXState) -> Dict[str, Any]:
    """Parse Python traceback details and collect bounded local source context."""
    raw_log = state.get("raw_log", "")
    repo_dir = state.get("repo_dir")
    parsed = _parse_traceback(raw_log, repo_dir)
    parse_ok = bool(parsed["error_type"] and parsed["frames"])

    context_result = {"context": "", "files": [], "truncated": False}
    if parsed["target_file"] and repo_dir:
        context_result = build_context(
            repo_dir,
            parsed["target_file"],
            hops=_context_hops(state),
            query_text=raw_log,
            target_line=parsed["target_line"],
        )

    history = list(state.get("agent_history", []))
    history.append({
        "agent": "LogParserAgent",
        "action": "Parsed Python traceback deterministically",
        "iteration": state.get("iteration_count", 0),
    })

    result: Dict[str, Any] = {
        "parsed_error": json.dumps(parsed),
        "parse_ok": parse_ok,
        "target_file": parsed["target_file"],
        "target_line": parsed["target_line"],
        "repository_context": context_result["context"],
        "context_files": context_result["files"],
        "context_truncated": context_result["truncated"],
        "context_hops": _context_hops(state),
        "agent_history": history,
    }
    if not parse_ok:
        result["final_status"] = "FATAL_PARSE_FAIL"
    return result