# Agent Instructions

This repository is for the UFPel 2026/1 SimpleScalar `sim-outorder` assignment. Treat it as a reproducible experiment/reporting project, not as a generic application.

## Project Goals

Maintain a Dockerized workflow that can:

1. Build and run `sim-outorder` consistently.
2. Execute the assignment experiments against the supplied PISA benchmarks.
3. Store machine-readable results in `results/<run>/`.
4. Generate a UFPel-themed static report in `site/`.
5. Publish the report through GitHub Actions and GitHub Pages.

## Important Files

```text
Dockerfile                         Builds the SimpleScalar runtime image
experiments/benchmarks.json        Benchmark commands, inputs, descriptions, instruction counts
experiments/benchmark_sets.json    Named benchmark groups, including course pairs
experiments/experiment_sets.json   Assignment experiment configurations
experiments/report.json            Report title, task descriptions, and questions
scripts/run_experiments.py         Only supported experiment runner
scripts/generate_report.py         Only supported static report generator
.github/workflows/experiments.yml  CI and Pages deployment workflow
.opencode/agents/experiment-analyst.md       OpenCode subagent for interpreting measured results
.opencode/commands/analyze-experiments.md    OpenCode slash command for the analysis workflow
reports/conclusions.md             Agent-authored conclusions embedded in the HTML report
```

## Editing Rules

Prefer small, data-driven changes.

Do not manually edit generated `results/` or `site/` output. Change `experiments/*.json` or the scripts, rerun the pipeline, and let generated files be regenerated.

When adding a benchmark, update `experiments/benchmarks.json` and at least one set in `experiments/benchmark_sets.json`.

When adding an experiment, update `experiments/experiment_sets.json`. Keep option names as actual `sim-outorder` options without the leading dash, for example `issue:width` and `res:memport`.

The assignment PDF says `res:memports`, but the simulator option is `res:memport`. Use the simulator option in code and generated config files.

Keep reports reproducible. If a table or analysis is needed in the HTML report, derive it from `results.json`; do not hard-code measured values.

Conclusion writing is intentionally agentic. Use the OpenCode command `/analyze-experiments`, backed by `.opencode/agents/experiment-analyst.md`, to guide a human/AI analysis pass that runs the scripts, reads `results.json`/`results.csv`, inspects logs, and updates `reports/conclusions.md`. Do not replace that reasoning pass with hard-coded scripted conclusions.

## Validation

Use Docker for simulator validation:

```sh
make docker-build
make smoke
```

Use dry-run mode for metadata-only validation:

```sh
python3 scripts/run_experiments.py --benchmarks quick --experiment-set assignment --dry-run --output results/dry-run
python3 scripts/generate_report.py --results results/dry-run --output site
```

For final runs, use the selected course pair benchmark set and `EXPERIMENTS=assignment`. Use `MAX_INST=0` only when full uncapped simulation time is acceptable.

Before changing experiment definitions, validate the whole matrix cheaply:

```sh
docker run --rm -v "$PWD:/workspace" -w /workspace sim-outorder:local python3 scripts/run_experiments.py --benchmarks all --experiment-set assignment --max-instructions 1000 --timeout-sec 300 --output results/verify-all
```
