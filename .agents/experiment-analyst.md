# Experiment Analyst Agent Task

You are analyzing the UFPel SimpleScalar `sim-outorder` assignment results. Your job is to run the existing scripts, inspect the structured outputs, infer why each experiment behaved as it did, and write conclusions for the report.

Do not add a new analysis script unless explicitly asked. This is an agentic interpretation task: use the scripts that already exist, read the results, compare configurations, inspect logs when needed, and write a concise human explanation.

## Inputs

Read these first:

```text
experiments/benchmarks.json
experiments/benchmark_sets.json
experiments/experiment_sets.json
experiments/report.json
.agents/experiment-rationale.md
```

Use the benchmark PDFs only as source material for context. Prefer the JSON files when deciding exact benchmark names, commands, and experiment IDs.

## Required Commands

Build the simulator image if it is not already available:

```sh
make docker-build
```

Run a capped full-matrix validation across every benchmark:

```sh
make run BENCHMARKS=all EXPERIMENTS=assignment MAX_INST=100000 TIMEOUT_SEC=1800 RESULTS=results/agent-analysis
```

Generate the report after writing conclusions:

```sh
python3 scripts/generate_report.py --results results/agent-analysis --output site
```

If time is constrained, first run a small cap to validate all benchmark commands and experiment configs:

```sh
make run BENCHMARKS=all EXPERIMENTS=assignment MAX_INST=1000 TIMEOUT_SEC=300 RESULTS=results/agent-validation
```

Mark any capped run as preliminary. Do not present capped results as final full-benchmark measurements unless the instruction cap is intentionally part of the analysis.

## Analysis Procedure

Use `results/<run>/results.json` and `results/<run>/results.csv` as the primary data sources.

For each benchmark:

- Identify the best CPI in each task.
- Compare in-order vs out-of-order at the same width for Task 1.
- Compare width scaling in Task 1 and note diminishing returns.
- Compare RUU/LSQ sizes in Task 2 and identify the first size that reaches most of the benefit.
- Compare predictors in Task 3 against the `perfect` baseline and explain the relative overhead.
- Compare Task 4 custom candidates and decide whether the fastest one is also cost-effective.

Use supporting stats when explaining behavior:

- `sim_cycle`, `sim_CPI`, `sim_IPC`, `sim_num_insn`, `sim_num_refs`, and `sim_num_branches`.
- `bpred_*.bpred_dir_rate` and `bpred_*.misses` for branch behavior.
- `il1.miss_rate` and `dl1.miss_rate` for cache behavior.
- `ruu_full`, `lsq_full`, `ruu_occupancy`, and `lsq_occupancy` when available.
- Benchmark load/store fraction from `experiments/benchmarks.json`.

Interpolate cautiously. You can infer bottlenecks from patterns, but distinguish measured facts from interpretation.

## Output

Write your conclusions to:

```text
reports/conclusions.md
```

Use this structure:

```markdown
# Agentic Conclusions

## Run Context

- Results directory: results/agent-analysis
- Benchmark set: all
- Experiment set: assignment
- Instruction cap: 100000 or uncapped
- Status: preliminary or final

## Cross-Benchmark Summary

- State the broad performance patterns.
- Explain which architectural limits appeared most often.

## Tarefa 1: In-Order vs Out-of-Order

- Compare width scaling.
- Explain where out-of-order mattered most and least.

## Tarefa 2: Window Size

- Identify which benchmarks benefited from larger windows.
- Explain saturation points.

## Tarefa 3: Branch Prediction

- Compare nottaken, taken, bimod, and perfect.
- Explain the relative value of bimod.

## Tarefa 4: Custom Processors

- For each benchmark or benchmark family, choose a preferred candidate.
- Explain the CPI/cost tradeoff.

## Caveats

- Mention instruction caps, timeouts, failed runs, or noisy/limited data.
```

Do not modify generated `site/` files directly. Regenerate them after updating `reports/conclusions.md`.
