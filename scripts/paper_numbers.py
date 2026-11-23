"""Collects the remaining numbers needed for the paper. Reads result files only (no Groq calls).
Usage: python paper_numbers.py results_v2 results_model2 results_real"""
import json, sys, collections
from pathlib import Path

def rows_of(p):
    d = json.loads(p.read_text(encoding="utf-8"))
    d = d.get("results", d) if isinstance(d, dict) else d
    return [r for r in d if isinstance(r, dict)]

def tok(r):
    return (r.get("prompt_tokens_actual") or 0) + (r.get("completion_tokens_actual") or 0)

for folder in sys.argv[1:]:
    print("=" * 100); print("FOLDER", folder)
    for p in sorted(Path(folder).glob("*.json")):
        rows = rows_of(p)
        runs = collections.defaultdict(list)
        for r in rows:
            runs[r.get("run_id")].append(r)
        print("-" * 100); print("FILE", p.name, "| rows", len(rows))
        for rid, rr in sorted(runs.items(), key=lambda x: str(x[0])):
            res = sum(1 for r in rr if r.get("final_status") == "RESOLVED")
            acc = sum(1 for r in rr if r.get("accepted"))
            err = sum(1 for r in rr if r.get("final_status") == "ERROR")
            p1 = sum(1 for r in rr if r.get("pass_at_1"))
            its = [float(r.get("iterations") or 0) for r in rr]
            ts = [float(r.get("execution_time_seconds") or 0) for r in rr]
            tk = sum(tok(r) for r in rr)
            failed = sorted(r.get("instance_id") for r in rr if r.get("final_status") not in ("RESOLVED", "ERROR"))
            commits = sorted({str(r.get("git_commit"))[:7] for r in rr})
            models = sorted({str(r.get("model")) for r in rr})
            print(f"  {rid}: n={len(rr)} resolved={res} accepted={acc} error={err} pass@1={p1} "
                  f"mean_iter={sum(its)/max(len(its),1):.3f} mean_time={sum(ts)/max(len(ts),1):.1f}s "
                  f"tokens_total={tk} tokens_per_run={tk/max(len(rr),1):.0f}")
            print(f"      not_resolved={failed}")
            print(f"      commits={commits} models={models}")
