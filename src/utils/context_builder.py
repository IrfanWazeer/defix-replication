import ast
import keyword
import math
import os
import re
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any


_STDLIB_MODULES = getattr(sys, "stdlib_module_names", set())

# Large files are shown as a deterministic, query-ranked excerpt (function level)
# instead of being dropped. Small files (<= WINDOW_FILE_THRESHOLD characters) are
# shown in full, exactly as before.
WINDOW_FILE_THRESHOLD = 12000
WINDOW_CHARS = int(os.getenv("DEFIX_WINDOW_CHARS", "5000"))
_HEADER_CHARS = 1200
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOP_WORDS = set(keyword.kwlist) | {
    "self", "cls", "line", "file", "traceback", "most", "recent", "call", "last",
    "error", "ran", "test", "tests", "failed", "ok", "none", "true", "false",
    "assert", "raise", "return", "print", "users", "appdata", "local", "temp",
    "python", "lib", "site", "packages", "unittest", "case", "pytest", "repo",
}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _local_module_files(repo_dir: Path, module: str) -> set[Path]:
    if not module:
        return set()
    top_level = module.split(".", 1)[0]
    if top_level in _STDLIB_MODULES:
        return set()

    relative = Path(*module.split("."))
    candidates = (repo_dir / relative.with_suffix(".py"), repo_dir / relative / "__init__.py")
    return {
        candidate.resolve()
        for candidate in candidates
        if candidate.is_file()
        and candidate.suffix == ".py"
        and _is_within(candidate.resolve(), repo_dir)
    }


def _import_modules(node: ast.AST, target: Path, repo_dir: Path) -> set[Path]:
    modules: set[str] = set()
    target_relative = target.relative_to(repo_dir)
    package_parts = list(target_relative.parent.parts)
    if target.name == "__init__.py":
        package_parts = list(target_relative.parent.parts)

    if isinstance(node, ast.Import):
        modules.update(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            retained = max(0, len(package_parts) - node.level + 1)
            base_parts = package_parts[:retained]
            if node.module:
                base_parts.extend(node.module.split("."))
            base = ".".join(base_parts)
        else:
            base = node.module or ""

        if base:
            modules.add(base)
        for alias in node.names:
            if alias.name != "*":
                modules.add(".".join(part for part in (base, alias.name) if part))

    found: set[Path] = set()
    for module in modules:
        found.update(_local_module_files(repo_dir, module))
    return found


def _function_units(tree: ast.AST) -> list[tuple[int, int, str]]:
    """Outermost functions and methods as (start_line, end_line, name)."""
    units: list[tuple[int, int, str]] = []

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                units.append((start, node.end_lineno or node.lineno, node.name))
            elif isinstance(node, ast.ClassDef):
                visit(node.body)

    visit(getattr(tree, "body", []))
    units.sort()
    return units


def _query_counts(query_text: str) -> Counter:
    counts: Counter = Counter()
    for token in _TOKEN_RE.findall(query_text or ""):
        if token.lower() in _STOP_WORDS:
            continue
        counts[token] += 1
    return counts


def _window_source(
    source: str,
    tree: ast.AST,
    query_text: str,
    target_line: int | None,
    budget: int,
) -> tuple[str, str]:
    """Return (excerpt, description) with original line numbers in markers."""
    lines = source.splitlines()
    units = _function_units(tree)
    total = len(lines)
    if not units:
        text = source[:budget]
        return text, f"EXCERPT: first {len(text)} of {len(source)} characters"

    query = _query_counts(query_text)
    unit_tokens = []
    document_frequency: Counter = Counter()
    for start, end, _name in units:
        tokens = Counter(_TOKEN_RE.findall("\n".join(lines[start - 1:end])))
        unit_tokens.append(tokens)
        for token in query:
            if token in tokens:
                document_frequency[token] += 1

    scores = []
    for index, (start, end, name) in enumerate(units):
        score = 0.0
        for token in query:
            count = unit_tokens[index].get(token, 0)
            if count or token == name:
                idf = math.log(1.0 + len(units) / (1.0 + document_frequency[token]))
                score += idf * (min(count, 3) + (5 if token == name else 0))
        if target_line is not None and start <= target_line <= end:
            score += 1000.0
        scores.append(score)

    first_start = units[0][0]
    header_lines = lines[:max(0, first_start - 1)]
    header = "\n".join(header_lines)[:_HEADER_CHARS]
    chunks: list[tuple[int, str]] = []
    used = 0
    if header.strip():
        marker = f"# --- lines 1-{len(header_lines)} ---\n"
        chunks.append((0, marker + header))
        used += len(marker) + len(header)

    order = sorted(range(len(units)), key=lambda i: (-scores[i], units[i][0]))
    shown = 0
    for index in order:
        if scores[index] <= 0:
            break
        start, end, _name = units[index]
        text_lines = lines[start - 1:end]
        text = "\n".join(text_lines)
        marker = f"# --- lines {start}-{end} ---\n"
        remaining = budget - used - len(marker)
        if remaining < 200:
            break
        if len(text) > remaining:
            if shown and not (target_line and start <= target_line <= end):
                continue
            if target_line and start <= target_line <= end:
                offset = sum(len(l) + 1 for l in text_lines[:max(0, target_line - start)])
                begin = max(0, offset - remaining // 2)
                text = text[begin:begin + remaining]
                marker = f"# --- lines {start}-{end} (clipped around line {target_line}) ---\n"
            else:
                text = text[:remaining]
                marker = f"# --- lines {start}-{end} (clipped) ---\n"
        chunks.append((start, marker + text))
        used += len(marker) + len(text) + 1
        shown += 1

    chunks.sort(key=lambda item: item[0])
    description = (
        f"EXCERPT: {shown} of {len(units)} functions, ranked by relevance to the failure "
        f"log; original line numbers in markers; file has {total} lines"
    )
    return "\n".join(text for _start, text in chunks), description


def build_context(
    repo_dir: str | os.PathLike[str],
    target_file: str | os.PathLike[str],
    hops: int,
    max_chars: int = 12000,
    query_text: str = "",
    target_line: int | None = None,
) -> dict[str, Any]:
    """Build bounded, deterministic source context using local Python imports."""
    root = Path(repo_dir).resolve()
    target = Path(target_file)
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if not _is_within(target, root) or target.suffix != ".py" or not target.is_file():
        return {"context": "", "files": [], "truncated": False}

    max_hops = min(2, max(0, int(hops)))
    pending = deque([(target, 0)])
    visited: set[Path] = set()
    sections: list[tuple[str, str]] = []

    while pending:
        current_hop = pending[0][1]
        frontier: list[Path] = []
        while pending and pending[0][1] == current_hop:
            path, _ = pending.popleft()
            if path not in visited:
                visited.add(path)
                frontier.append(path)

        next_files: set[Path] = set()
        for path in sorted(frontier, key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=relative)
            except SyntaxError as error:
                note = (
                    f"### SKIPPED: {relative} (hop {current_hop})\n"
                    f"SyntaxError: {error.msg} at line {error.lineno}\n"
                )
                sections.append((relative, note))
                continue
            except OSError as error:
                note = f"### SKIPPED: {relative} (hop {current_hop})\nRead error: {error}\n"
                sections.append((relative, note))
                continue

            if len(source) > WINDOW_FILE_THRESHOLD:
                excerpt, description = _window_source(
                    source,
                    tree,
                    query_text,
                    target_line if path == target else None,
                    WINDOW_CHARS,
                )
                sections.append((
                    relative,
                    f"### FILE: {relative} (hop {current_hop}) [{description}]\n{excerpt}\n",
                ))
            else:
                sections.append((relative, f"### FILE: {relative} (hop {current_hop})\n{source}"))
            if current_hop < max_hops:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        next_files.update(_import_modules(node, path, root))

        for path in sorted(next_files, key=lambda item: item.relative_to(root).as_posix()):
            if path not in visited:
                pending.append((path, current_hop + 1))

    included_sections: list[str] = []
    files: list[str] = []
    context_length = 0
    truncated = False
    for relative, section in sections:
        if context_length + len(section) > max_chars:
            truncated = True
            break
        included_sections.append(section)
        context_length += len(section)
        if section.startswith("### FILE:"):
            files.append(relative)

    return {
        "context": "".join(included_sections),
        "files": files,
        "truncated": truncated,
    }