"""Build benchmark_real instances from BugsInPy bugs that passed validation.

Reads ..\\bugsinpy_work\\validated.csv (status VALID), and for every bug creates
benchmark_real\\instances\\<id>\\{repo, meta.json, failing.log, reference_patch.diff}.
Each instance is checked with the real sandbox (run_patch_in_workspace):
  * the unpatched repo must FAIL its test command,
  * the reference patch (never shown to any model) must make it PASS.
Instances failing a check are skipped and reported. The reference patch is stored
next to (not inside) repo/ and is never read by the evaluation pipeline.
"""
import argparse
import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.agents.log_parser import _parse_traceback  # noqa: E402
from src.utils.docker_runner import run_patch_in_workspace  # noqa: E402

TEST_TIMEOUT_SECONDS = 120
LOG_HEAD_CHARS = 3500
LOG_TAIL_CHARS = 2000
MESSAGE_CHARS = 1500
IGNORE = shutil.ignore_patterns(
    "venv", ".git", "__pycache__", "*.pyc", ".pytest_cache", ".env", ".tox"
)


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def build_test_cmd(run_test: Path, python: Path) -> str:
    commands = []
    for line in run_test.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        tokens = shlex.split(line, comments=True)
        if tokens:
            commands.append(tokens)
    if len(commands) != 1:
        raise ValueError(f"run_test.sh has {len(commands)} commands; exactly 1 is required")
    tokens = commands[0]
    executable = Path(tokens[0]).name.lower()
    rest = tokens[1:]
    if executable in {"pytest", "py.test"}:
        arguments = ["-m", "pytest", "--tb=native", *rest]
    elif executable in {"python", "python3"}:
        if rest[:2] == ["-m", "pytest"]:
            arguments = ["-m", "pytest", "--tb=native", *rest[2:]]
        else:
            arguments = rest
    else:
        raise ValueError(f"Unsupported test command: {tokens[0]}")
    # Forward slashes + quotes survive shlex.split(posix) on Windows.
    quoted_python = '"' + Path(os.path.abspath(python)).as_posix() + '"'
    return " ".join([quoted_python, *[shlex.quote(a) for a in arguments]])


def shorten_log(text: str) -> str:
    """Keep the failing test header and every traceback frame; cap the long message.

    Output noise printed before the failure (e.g. tree dumps) is dropped, and the
    exception message is cut to MESSAGE_CHARS. If no traceback is found, fall back
    to keeping the head and tail of the log.
    """
    text = text.replace("\r\n", "\n")
    if len(text) <= LOG_HEAD_CHARS + LOG_TAIL_CHARS:
        return text
    marker = "Traceback (most recent call last):"
    start = text.rfind(marker)
    if start < 0:
        return text[:LOG_HEAD_CHARS] + "\n...[log truncated]...\n" + text[-LOG_TAIL_CHARS:]
    # Include the FAIL:/ERROR:/test-name header line(s) just before the traceback.
    header_start = start
    for _ in range(4):
        previous = text.rfind("\n", 0, max(0, header_start - 1))
        line = text[previous + 1:header_start]
        if line.startswith(("FAIL:", "ERROR:", "=====", "_____", "-----")) or not line.strip():
            header_start = previous + 1 if previous >= 0 else 0
            if line.startswith(("FAIL:", "ERROR:")):
                break
        else:
            break
    lines = text[start:].split("\n")
    index = 1
    while index < len(lines) and (not lines[index] or lines[index][0] in " \t"):
        index += 1
    frames_text = "\n".join(lines[:index])
    rest = "\n".join(lines[index:])
    separator = re.search(r"\n(?:-{20,}|={5,})", rest)
    message = rest[:separator.start()] if separator else rest
    summary = rest[separator.start():] if separator else ""
    if len(message) > MESSAGE_CHARS:
        message = message[:MESSAGE_CHARS] + "\n[... message truncated ...]"
    shortened = text[header_start:start] + frames_text + "\n" + message + summary[-400:]
    return shortened


def run_unpatched(repo: Path, test_cmd: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="defix-real-base-") as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        shutil.copytree(repo, workspace, ignore=IGNORE)
        completed = subprocess.run(
            shlex.split(test_cmd),
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TEST_TIMEOUT_SECONDS,
            shell=False,
        )
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def build_instance(row, work_root, bugs_root, out_root, uninstall):
    project, bug_id = row["project"], row["bug_id"]
    instance_id = f"real-{project.lower()}-{int(bug_id):02d}"
    work = work_root / f"{project}-{bug_id}"
    buggy = work / "buggy"
    python = venv_python(work / "venv")
    bug_dir = bugs_root / project / "bugs" / bug_id
    if not buggy.is_dir() or not python.is_file():
        return instance_id, "SKIP", "missing buggy folder or venv", {}
    test_cmd = build_test_cmd(bug_dir / "run_test.sh", python)
    reference_patch = (bug_dir / "bug_patch.txt").read_text(encoding="utf-8", errors="replace")

    if uninstall:
        # Editable installs made during validation could shadow the sandbox copy.
        subprocess.run(
            [str(python), "-m", "pip", "uninstall", "-y", project],
            capture_output=True, text=True, timeout=300, check=False,
        )

    final = out_root / instance_id
    staging = out_root / f".staging-{instance_id}"
    if staging.exists():
        shutil.rmtree(staging)
    (staging).mkdir(parents=True)
    shutil.copytree(buggy, staging / "repo", ignore=IGNORE)

    code, output = run_unpatched(staging / "repo", test_cmd)
    if code == 0:
        shutil.rmtree(staging)
        return instance_id, "SKIP", "unpatched repo PASSES its test command", {}
    log_text = shorten_log(output)

    check = run_patch_in_workspace(
        str(staging / "repo"), reference_patch, test_cmd, patch_is_sanitized=True
    )
    if not check.get("exec_passed"):
        shutil.rmtree(staging)
        tail = (check.get("log") or "")[-300:].replace("\n", " | ")
        return instance_id, "SKIP", f"reference patch does not pass in sandbox: {tail}", {}

    parsed = _parse_traceback(log_text, str(staging / "repo"))
    parse_ok = bool(parsed["error_type"] and parsed["frames"])
    patch_files = sorted({
        line[6:].strip() for line in reference_patch.splitlines() if line.startswith("+++ b/")
    })
    info = {}
    info_path = bug_dir / "bug.info"
    if info_path.is_file():
        for line in info_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info[key.strip()] = value.strip().strip("\"'")
    meta = {
        "instance_id": instance_id,
        "test_cmd": test_cmd,
        "fault_type": "Real",
        "root_cause_hops": -1,
        "source": "BugsInPy",
        "project": project,
        "bug_id": int(bug_id),
        "buggy_commit_id": info.get("buggy_commit_id"),
        "fixed_commit_id": info.get("fixed_commit_id"),
        "reference_patch_files": patch_files,
        "log_chars": len(log_text),
    }
    (staging / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (staging / "failing.log").write_text(log_text, encoding="utf-8")
    (staging / "reference_patch.diff").write_text(reference_patch, encoding="utf-8")
    if final.exists():
        shutil.rmtree(final)
    staging.replace(final)
    detail = f"parse_ok={parse_ok} target={parsed['target_file']} patch_files={patch_files}"
    return instance_id, "BUILT", detail, {"parse_ok": parse_ok, "target": parsed["target_file"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bugsinpy-work", type=Path, default=ROOT.parent / "bugsinpy_work")
    parser.add_argument("--out", type=Path, default=ROOT / "benchmark_real")
    parser.add_argument("--only", nargs="+", help="Bug ids (e.g. 10 11) to build.")
    parser.add_argument("--project", default=None, help="Restrict to one project.")
    parser.add_argument("--no-uninstall", action="store_true")
    args = parser.parse_args()

    work_root = args.bugsinpy_work / "work"
    bugs_root = args.bugsinpy_work / "BugsInPy" / "projects"
    out_root = args.out / "instances"
    out_root.mkdir(parents=True, exist_ok=True)
    with (args.bugsinpy_work / "validated.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "VALID"]
    if args.project:
        rows = [r for r in rows if r["project"] == args.project]
    if args.only:
        rows = [r for r in rows if r["bug_id"] in set(args.only)]
    rows.sort(key=lambda r: (r["project"], int(r["bug_id"])))

    report = []
    for row in rows:
        try:
            result = build_instance(row, work_root, bugs_root, out_root, not args.no_uninstall)
        except Exception as error:  # report and continue
            result = (f"real-{row['project'].lower()}-{int(row['bug_id']):02d}",
                      "SKIP", f"{type(error).__name__}: {error}", {})
        report.append(result)
        print(f"{result[0]}: {result[1]} {result[2]}", flush=True)

    with (args.out / "build_report.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["instance_id", "status", "detail"])
        for r in report:
            writer.writerow(r[:3])
    built = sum(1 for r in report if r[1] == "BUILT")
    print(f"\nBuilt {built} of {len(report)} instances -> {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())