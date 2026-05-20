---
description: Run and interpret the sim-outorder assignment experiments with the experiment-analyst subagent.
agent: experiment-analyst
subtask: true
---
Run the agentic experiment analysis workflow for this repository.

If `$ARGUMENTS` is provided, treat it as operator guidance for benchmark set, instruction cap, result directory, or final-report mode. If no arguments are provided, use the default capped full-matrix workflow:

```text
BENCHMARKS=all
EXPERIMENTS=assignment
MAX_INST=100000
TIMEOUT_SEC=1800
RESULTS=results/agent-analysis
```

The goal is not merely to run commands. Run the existing experiment scripts, inspect `results.json`, `results.csv`, and per-run logs/configs, reason about why the results behaved as they did, update `reports/conclusions.md`, and regenerate the static report.

Do not edit generated `site/` files manually.
