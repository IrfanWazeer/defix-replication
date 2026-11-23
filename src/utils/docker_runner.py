import os
import re
import shlex
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Tuple

def extract_clean_diff(patch_text: str) -> str:
    """Extracts raw git diff from markdown code blocks or raw text."""
    match = re.search(r"```(?:diff)?\n(diff --git.*?)```", patch_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    match_raw = re.search(r"(diff --git|--- a/).*", patch_text, re.DOTALL)
    if match_raw:
        return match_raw.group(0).strip()
    return patch_text.strip()
    return patch_text.strip()

_LOCATE_MARK = "DEFIX-LOCATE"
_LOCATE_HEADER = re.compile(r"^@@ -\d+,(\d+) \+\d+,(\d+) @@ " + _LOCATE_MARK + r"$")


def _norm(line: str) -> str:
    return " ".join(line.split())


def _find_block(file_lines: list, block: list) -> int:
    """Index where block matches file_lines; exact (trailing-space-insensitive) first, then whitespace-insensitive."""
    if not block:
        return -1
    for key in (lambda x: x.rstrip(), _norm):
        target = [key(x) for x in block]
        view = [key(x) for x in file_lines]
        for i in range(len(view) - len(target) + 1):
            if view[i:i + len(target)] == target:
                return i
    return -1


def _hunk_counts(body: list) -> tuple:
    old_n = sum(1 for x in body if x[:1] in (" ", "-"))
    new_n = sum(1 for x in body if x[:1] in (" ", "+"))
    return old_n, new_n


def _emit_located(pending: list, file_lines: list, context: int) -> list:
    """Turn located hunks of one file into numbered hunks. Hunks whose padded
    context would touch or overlap are merged into one hunk."""
    out: list = []
    merged: list = []
    for h in sorted(pending, key=lambda x: x["pos"]):
        if merged:
            prev = merged[-1]
            prev_end = prev["pos"] + prev["old_len"]
            gap = h["pos"] - prev_end
            if 0 <= gap <= 2 * context:
                prev["body"] = (
                    prev["body"]
                    + [" " + x for x in file_lines[prev_end:h["pos"]]]
                    + h["body"]
                )
                prev["old_len"] = prev["old_len"] + gap + h["old_len"]
                continue
        merged.append({"pos": h["pos"], "old_len": h["old_len"], "body": list(h["body"])})
    delta = 0
    for h in merged:
        body, pos = h["body"], h["pos"]
        lead = 0
        for x in body:
            if x[:1] == " ":
                lead += 1
            else:
                break
        trail = 0
        for x in reversed(body):
            if x[:1] == " ":
                trail += 1
            elif x[:1] == "\\":
                continue
            else:
                break
        add_lead = min(max(context - lead, 0), pos)
        end = pos + h["old_len"]
        add_trail = min(max(context - trail, 0), len(file_lines) - end)
        full = (
            [" " + x for x in file_lines[pos - add_lead:pos]]
            + body
            + [" " + x for x in file_lines[end:end + add_trail]]
        )
        old_n, new_n = _hunk_counts(full)
        start_old = pos - add_lead + 1
        out.append(f"@@ -{start_old},{old_n} +{start_old + delta},{new_n} @@")
        out.extend(full)
        delta += new_n - old_n
    return out


def _relocate_bare_hunks(patch: str, workspace: str, context: int = 3) -> str:
    """Give hunks written without line numbers ("@@" only; tagged by the sanitizer)
    their real position, found by matching the hunk's old lines inside the file, and
    pad missing context from the file (git apply needs it for mid-file hunks)."""
    if _LOCATE_MARK not in patch:
        return patch
    lines = patch.split("\n")
    out: list = []
    file_lines: list = []
    pending: list = []

    def flush() -> None:
        if pending:
            out.extend(_emit_located(list(pending), file_lines, context))
            pending.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("+++ b/"):
            flush()
            name = line[6:].strip()
            try:
                with open(os.path.join(workspace, name), encoding="utf-8", errors="replace") as fh:
                    file_lines = fh.read().splitlines()
            except OSError:
                file_lines = []
            out.append(line)
            i += 1
            continue
        if line.startswith(("diff --git", "--- a/")) or (
            line.startswith("@@") and not _LOCATE_HEADER.match(line)
        ):
            flush()
            out.append(line)
            i += 1
            continue
        if not _LOCATE_HEADER.match(line):
            if line != "":
                out.append(line)
            i += 1
            continue
        j = i + 1
        body: list = []
        while j < len(lines) and lines[j][:1] in (" ", "+", "-", "\\"):
            body.append(lines[j])
            j += 1
        old = [x[1:] for x in body if x[:1] in (" ", "-")]
        pos = _find_block(file_lines, old)
        if pos < 0:
            flush()
            out.append(line)
            out.extend(body)
        else:
            pending.append({"pos": pos, "old_len": len(old), "body": body})
        i = j
    flush()
    return "\n".join(out)


def _output_text(output: Any) -> str:
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def run_patch_in_workspace(
    repo_dir: str,
    patch_text: str,
    test_cmd: str,
    timeout_s: int = 120,
    patch_is_sanitized: bool = False,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "patch_applied": False,
        "exit_code": None,
        "exec_passed": False,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "log": ""
    }
    clean_patch = patch_text if patch_is_sanitized else extract_clean_diff(patch_text)

    if not clean_patch or ("--- a/" not in clean_patch and "diff --git" not in clean_patch):
        result["stderr"] = "Patch Application Failed: No valid unified diff headers found in patch text."
        result["log"] = result["stderr"]
        return result

    try:
        with tempfile.TemporaryDirectory(prefix="defix-sandbox-") as temp_dir:
            workspace = os.path.join(temp_dir, "workspace")
            shutil.copytree(
                repo_dir,
                workspace,
                ignore=shutil.ignore_patterns("venv", ".git", "__pycache__", "*.pyc", ".env")
            )

            clean_patch = _relocate_bare_hunks(clean_patch, workspace)

            repo_check = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if repo_check.returncode != 0:
                git_init = subprocess.run(
                    ["git", "init"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                result["stdout"] += git_init.stdout
                result["stderr"] += git_init.stderr
                if git_init.returncode != 0:
                    result["log"] = result["stdout"] + result["stderr"]
                    return result

            patch_path = ""
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".patch",
                    dir=workspace,
                    delete=False,
                    encoding="utf-8"
                ) as patch_file:
                    patch_file.write(clean_patch + "\n")
                    patch_path = patch_file.name

                apply_result = subprocess.run(
                    [
                        "git", "apply", "--ignore-space-change",
                        "--ignore-whitespace", patch_path
                    ],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
            finally:
                if patch_path and os.path.exists(patch_path):
                    os.remove(patch_path)

            result["stdout"] += apply_result.stdout
            result["stderr"] += apply_result.stderr
            if apply_result.returncode != 0:
                result["log"] = result["stdout"] + result["stderr"]
                return result

            result["patch_applied"] = True
            try:
                test_result = subprocess.run(
                    shlex.split(test_cmd),
                    cwd=workspace,
                    shell=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_s
                )
                result["exit_code"] = test_result.returncode
                result["stdout"] += test_result.stdout
                result["stderr"] += test_result.stderr
            except subprocess.TimeoutExpired as error:
                result["timed_out"] = True
                result["stdout"] += _output_text(error.stdout)
                result["stderr"] += _output_text(error.stderr)
                result["stderr"] += f"Test command timed out after {timeout_s} seconds."

            result["exec_passed"] = (
                result["patch_applied"] and result["exit_code"] == 0
            )
            result["log"] = result["stdout"] + result["stderr"]
            return result
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        result["stderr"] += f"Execution Sandbox Error: {error}"
        result["log"] = result["stdout"] + result["stderr"]
        return result


def apply_and_test_patch(
    patch_code: str,
    test_command: str = "python -m unittest discover tests"
) -> Tuple[bool, bool, str]:
    result = run_patch_in_workspace(".", patch_code, test_command)
    return result["exec_passed"], result["patch_applied"], result["log"]