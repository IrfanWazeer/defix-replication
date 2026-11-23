import re
from typing import Any


_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<section>.*)$"
)
_FILE_START = re.compile(r"^(?:diff --git |--- a/)")
# Some models (e.g. gpt-oss) write hunk headers without line numbers ("@@" alone).
# Such a hunk is kept and tagged; the sandbox later finds its real position in the file.
_BARE_HEADER = re.compile(r"^@@\s*(?:@@)?\s*$")
LOCATE_MARK = "DEFIX-LOCATE"


def _is_file_metadata(line: str) -> bool:
    return _FILE_START.match(line) is not None or line.startswith((
        "+++ b/",
        "index ",
        "new file mode ",
        "deleted file mode ",
        "old mode ",
        "new mode ",
        "similarity index ",
        "rename from ",
        "rename to ",
        "GIT binary patch",
    ))


def _repair_hunk_counts(lines: list[str]) -> tuple[list[str], bool, bool]:
    repaired = list(lines)
    changed = False
    bare_found = False
    index = 0
    while index < len(repaired):
        header = _HUNK_HEADER.match(repaired[index])
        bare = _BARE_HEADER.match(repaired[index]) is not None
        if header is None and not bare:
            index += 1
            continue

        old_count = 0
        new_count = 0
        body_end = index + 1
        while body_end < len(repaired):
            line = repaired[body_end]
            if (
                _HUNK_HEADER.match(line)
                or _BARE_HEADER.match(line)
                or _is_file_metadata(line)
            ):
                break
            if line == "":
                line = " "
                repaired[body_end] = line
                old_count += 1
                new_count += 1
            elif line.startswith(" "):
                old_count += 1
                new_count += 1
            elif line.startswith("-"):
                old_count += 1
            elif line.startswith("+"):
                new_count += 1
            elif line.startswith("\\ No newline at end of file"):
                pass
            else:
                break
            body_end += 1

        if bare:
            repaired[index] = f"@@ -1,{old_count} +1,{new_count} @@ {LOCATE_MARK}"
            changed = True
            bare_found = True
            index = body_end
            continue

        declared_old_count = int(header.group("old_count") or 1)
        declared_new_count = int(header.group("new_count") or 1)
        if (declared_old_count, declared_new_count) != (old_count, new_count):
            repaired[index] = (
                f"@@ -{header.group('old_start')},{old_count} "
                f"+{header.group('new_start')},{new_count} @@{header.group('section')}"
            )
            changed = True
        index = body_end

    return repaired, changed, bare_found


def sanitize_patch(raw: str) -> tuple[str, dict[str, bool]]:
    """Remove wrappers and prose while retaining unified-diff content."""
    normalized = raw.replace("\r\n", "\n")
    lines = normalized.splitlines()
    had_fence = any(re.match(r"^\s*```", line) for line in lines)
    if had_fence:
        lines = [line for line in lines if not re.match(r"^\s*```", line)]

    start_index = next(
        (index for index, line in enumerate(lines) if _FILE_START.match(line)),
        None,
    )
    had_prose = bool(
        start_index is not None
        and any(line.strip() for line in lines[:start_index])
    )
    if start_index is None:
        clean = ""
        report = {
            "had_fence": had_fence,
            "had_prose": bool(normalized.strip()) or had_fence,
            "headers_ok": False,
            "changed": clean != raw,
            "hunk_counts_fixed": False,
        }
        return clean, report

    patch_lines = lines[start_index:]
    last_diff_line: int | None = None
    in_hunk = False
    for index, line in enumerate(patch_lines):
        if _HUNK_HEADER.match(line) or _BARE_HEADER.match(line):
            last_diff_line = index
            in_hunk = True
            continue
        if _is_file_metadata(line):
            last_diff_line = index
            in_hunk = False
            continue
        if in_hunk:
            if (
                line == ""
                or line.startswith((" ", "+", "-", "\\ No newline at end of file"))
            ):
                last_diff_line = index
                continue
            in_hunk = False

    if last_diff_line is None:
        patch_lines = []
        had_prose = True
    else:
        if any(line.strip() for line in patch_lines[last_diff_line + 1:]):
            had_prose = True
        patch_lines = patch_lines[:last_diff_line + 1]

    while patch_lines and patch_lines[-1] == "":
        patch_lines.pop()
    patch_lines, hunk_counts_fixed, bare_hunks = _repair_hunk_counts(patch_lines)

    headers: list[str] = []
    for index, line in enumerate(patch_lines):
        if line.startswith("--- a/"):
            if (
                index + 1 >= len(patch_lines)
                or not patch_lines[index + 1].startswith("+++ b/")
                or line.removeprefix("--- a/")
                != patch_lines[index + 1].removeprefix("+++ b/")
            ):
                headers.append("unpaired")
            else:
                headers.append("paired")
        elif line.startswith("+++ b/"):
            if index == 0 or not patch_lines[index - 1].startswith("--- a/"):
                headers.append("unpaired")
    headers_ok = bool(headers) and all(header == "paired" for header in headers)

    clean = "\n".join(patch_lines)
    if clean:
        clean += "\n"
    report: dict[str, Any] = {
        "had_fence": had_fence,
        "had_prose": had_prose,
        "headers_ok": headers_ok,
        "changed": clean != raw,
        "hunk_counts_fixed": hunk_counts_fixed,
        "bare_hunks": bare_hunks,
    }
    return clean, report


def diff_sanitizer_node(state: dict[str, Any]) -> dict[str, Any]:
    import os

    raw_patch = state.get("proposed_patch") or ""
    mode = str(state.get("sanitizer_mode", os.getenv("DEFIX_SANITIZER", "on"))).lower()
    clean_patch, report = sanitize_patch(raw_patch)
    if mode == "off":
        report["changed"] = False
        report["hunk_counts_fixed"] = False
    return {
        "proposed_patch": clean_patch if mode != "off" else raw_patch,
        "sanitizer_report": report,
        "sanitizer_mode": mode,
    }