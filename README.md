# DEFIX: replication package

Code, benchmark and result files for the paper
"DEFIX: An Autonomous Multi-Agent Framework for Self-Healing CI/CD Pipelines"
(Wazeer and Ferzund; under review).

## What is here
- `src/` : the DEFIX pipeline (LangGraph graph, Parser, XAI Diagnostic, Repair, Sandbox Validator agents, DiffSanitizer, context builder, single-prompt baselines).
  Note: `src/utils/docker_runner.py` keeps its old name but does NOT use Docker. The sandbox is a temporary copy of the repository, with no network or resource isolation.
- `config/` : prompts and settings (`prompts.py`, `settings.py`).
- `benchmark_v2/` : the 24 synthetic instances (6 each of Type-I to Type-IV). Each instance has the buggy repository, `unittest` tests, a reference patch (never shown to a model) and an automatically generated `failing.log`.
- `results/` : raw per-run result files for every configuration reported in the paper.
- `scripts/` : `evaluate_v2.py`, `analyze_v2.py`, `paper_numbers.py` (rebuild every number in the paper from `results/`), and the BugsInPy pilot scripts (`build_real_instances.py`, `validate_bugsinpy.py`, `build_report.csv`, per-instance `meta.json` and `failing.log`).
- `PAPER_NUMBERS.md` : output of `paper_numbers.py`.

## Not included
- API keys and `.env` files. Create your own `.env` (see `.env.example`).
- The `black` repository and the BugsInPy data. Rebuild them with the scripts; BugsInPy: https://github.com/soarsmu/BugsInPy

## Requirements
Python 3.12; LangGraph 1.2.2, LangChain 1.3.2, langchain-core 1.6.10, langchain-groq 1.1.3, groq 0.37.1, pydantic 2.14.1; `git` on the PATH.
Models used: `qwen/qwen3.8-27b` and `openai/gpt-oss-20b` through the Groq API (temperature 0).

## Reproduce
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and put your own Groq key in it.
3. Run the evaluation, e.g. `python scripts/evaluate_v2.py` (see the script header for options).
4. Rebuild the tables: `python scripts/analyze_v2.py` and `python scripts/paper_numbers.py`.

LLM output is stochastic even at temperature 0 and free-tier rate limits change run times, so counts may differ slightly. The result files in `results/` are the ones behind the paper.

## Code versions
Commits used for the experiments: `848fcce`, `7489929`, `8bf22eb`, `3f93ce7` (see the paper, Section 5.2).

## License
\<choose a license, e.g. MIT\>

## Citation
\<fill in after acceptance\>
