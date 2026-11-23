import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_results(results_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, list):
            rows.extend(row for row in data if isinstance(row, dict))
        elif isinstance(data, dict):
            results = data.get("results", [])
            rows.extend(row for row in results if isinstance(row, dict))
    return rows


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.96
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _rate(rows: list[dict[str, Any]]) -> tuple[int, int, float, float, float]:
    total = len(rows)
    passed = sum(bool(row.get("accepted", row.get("resolved", False))) for row in rows)
    rate = passed / total if total else 0.0
    lower, upper = _wilson(passed, total)
    return passed, total, rate, lower, upper


def _configuration(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("mode"),
        row.get("validation_mode"),
        row.get("context_hops"),
        row.get("sanitizer"),
    )


def _latex_escape(value: Any) -> str:
    return str(value if value is not None else "").replace("_", r"\_")


def main() -> int:
    # Optional argument: results folder (default results_v2), e.g. results_model2.
    folder = sys.argv[1] if len(sys.argv) > 1 else "results_v2"
    results_dir = Path(__file__).resolve().parent / folder
    rows = _read_results(results_dir)
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_configuration(row)].append(row)

    summary_lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\begin{tabular}{llllrrrrrrrr}",
        r"Mode & Validation & Hops & Sanitizer & n & Pass rate & 95\% CI & Pass@1 & Mean iter. & Mean time & False+ & Run rate mean $\pm$ std \\",
        r"\hline",
    ]
    stratified_tables: list[tuple[tuple[Any, ...], list[dict[str, Any]]]] = []
    sanitizer_tables: list[tuple[tuple[Any, ...], dict[str, int]]] = []

    for config, group in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        excluded_errors = sum(row.get("final_status") == "ERROR" for row in group)
        valid_group = [row for row in group if row.get("final_status") != "ERROR"]
        passed, total, rate, lower, upper = _rate(valid_group)
        pass_at_1 = (
            sum(bool(row.get("pass_at_1", False)) for row in valid_group) / total
            if total else 0.0
        )
        mean_iterations = statistics.mean(
            float(row.get("iterations", 0) or 0) for row in valid_group
        ) if total else 0.0
        mean_time = statistics.mean(
            float(row.get("execution_time_seconds", 0) or 0) for row in valid_group
        ) if total else 0.0
        false_positives = sum(bool(row.get("false_positive", False)) for row in valid_group)

        per_run: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in valid_group:
            per_run[row.get("run_id")].append(row)
        run_rates = [_rate(run_rows)[2] for run_rows in per_run.values()]
        across_run_mean = statistics.mean(run_rates) if run_rates else 0.0
        across_run_std = statistics.stdev(run_rates) if len(run_rates) > 1 else 0.0
        sanitizer_counts = {
            key: sum(
                bool(row.get("sanitizer_report", {}).get(key, False))
                for row in valid_group
            )
            for key in (
                "had_fence",
                "had_prose",
                "headers_ok",
                "changed",
                "hunk_counts_fixed",
            )
        }

        print(
            f"mode={config[0]} validation={config[1]} hops={config[2]} "
            f"sanitizer={config[3]} n={total} pass_rate={rate:.4f} "
            f"wilson95=[{lower:.4f}, {upper:.4f}] pass@1={pass_at_1:.4f} "
            f"mean_iterations={mean_iterations:.4f} mean_time={mean_time:.4f} "
            f"false_positives={false_positives} "
            f"run_pass_rate_mean_std={across_run_mean:.4f} +/- {across_run_std:.4f} "
            f"excluded_error_rows={excluded_errors} "
            f"sanitizer_report_counts={sanitizer_counts}"
        )
        summary_lines.append(
            " & ".join((
                _latex_escape(config[0]),
                _latex_escape(config[1]),
                _latex_escape(config[2]),
                _latex_escape(config[3]),
                str(total),
                f"{rate:.4f}",
                f"[{lower:.4f}, {upper:.4f}]",
                f"{pass_at_1:.4f}",
                f"{mean_iterations:.4f}",
                f"{mean_time:.4f}",
                str(false_positives),
                f"{across_run_mean:.4f} $\\pm$ {across_run_std:.4f}",
            )) + r" \\"
        )
        stratified_tables.append((config, valid_group))
        sanitizer_tables.append((config, sanitizer_counts))

    summary_lines.extend((r"\end{tabular}", r"\end{table}"))
    for config, group in stratified_tables:
        summary_lines.extend((
            r"\begin{table}[ht]",
            r"\centering",
            r"\begin{tabular}{llrr}",
            r"Stratification & Value & n & Pass rate \\",
            r"\hline",
        ))
        for label, key in (("fault_type", "fault_type"), ("root_cause_hops", "root_cause_hops")):
            strata: dict[Any, list[dict[str, Any]]] = defaultdict(list)
            for row in group:
                strata[row.get(key)].append(row)
            for stratum, stratum_rows in sorted(strata.items(), key=lambda item: str(item[0])):
                stratum_passed, stratum_total, stratum_rate, _, _ = _rate(stratum_rows)
                print(
                    f"  {label}={stratum}: pass_rate={stratum_rate:.4f} "
                    f"({stratum_passed}/{stratum_total})"
                )
                summary_lines.append(
                    f"{label} & {_latex_escape(stratum)} & {stratum_total} & "
                    f"{stratum_rate:.4f} \\\\"
                )
        summary_lines.extend((r"\end{tabular}", r"\end{table}"))
    if sanitizer_tables:
        summary_lines.extend((
            r"\begin{table}[ht]",
            r"\centering",
            r"\begin{tabular}{llllrrrrr}",
            r"Mode & Validation & Hops & Sanitizer & Fenced & Prose & Headers OK & Changed & Recounted \\",
            r"\hline",
        ))
        for config, counts in sanitizer_tables:
            summary_lines.append(
                " & ".join((
                    _latex_escape(config[0]),
                    _latex_escape(config[1]),
                    _latex_escape(config[2]),
                    _latex_escape(config[3]),
                    str(counts["had_fence"]),
                    str(counts["had_prose"]),
                    str(counts["headers_ok"]),
                    str(counts["changed"]),
                    str(counts["hunk_counts_fixed"]),
                )) + r" \\"
            )
        summary_lines.extend((r"\end{tabular}", r"\end{table}"))
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.tex").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not rows:
        print("No result records found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
