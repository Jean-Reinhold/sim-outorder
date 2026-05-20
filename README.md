# Sim-OutOrder Experiments

Reproducible SimpleScalar `sim-outorder` setup for the UFPel 2026/1 advanced computer architecture assignment.

The repository is organized so experiments can run locally in Docker and in GitHub Actions. The same structured results are then converted into a UFPel-themed static HTML report for GitHub Pages.

## Repository Layout

```text
Benchmarks/                         PISA binaries, inputs, and cache config examples
experiments/                        Benchmark metadata, experiment definitions, report metadata
scripts/run_experiments.py          Runs sim-outorder and writes structured results
scripts/generate_report.py          Builds the static HTML report from results
.opencode/                         OpenCode agent and command configuration
reports/conclusions.md             Agent-authored conclusions included in the HTML report
results/                            Generated experiment results, ignored by git
site/                               Generated GitHub Pages site, ignored by git
.github/workflows/experiments.yml   CI and Pages workflow
Dockerfile                          Reproducible SimpleScalar runtime image
compose.yaml                        Local smoke-run convenience service
```

## Docker Setup

The Docker image builds `sim-outorder`, `sim-cache`, and `sim-safe` from a pinned snapshot of `khaledhassan/simplescalar-docker`:

```sh
docker build -t sim-outorder:local .
```

Open a shell inside the simulator environment:

```sh
docker run --rm -it -v "$PWD:/workspace" -w /workspace sim-outorder:local bash
```

Run the default smoke test and generate a report:

```sh
make smoke
```

The smoke target caps each run at `100000` committed instructions so local and CI feedback remains fast.

## Running Experiments

Run a selected benchmark group and experiment set:

```sh
make docker-build
make run BENCHMARKS=andressa_eduarda EXPERIMENTS=assignment MAX_INST=100000 RESULTS=results/andressa_eduarda
make report RESULTS=results/andressa_eduarda
```

Use `MAX_INST=0` only when you want full benchmark execution with no instruction cap:

```sh
make run BENCHMARKS=andressa_eduarda EXPERIMENTS=assignment MAX_INST=0 RESULTS=results/final
make report RESULTS=results/final
```

Full uncapped runs can be very slow because some workloads exceed 500 million simulated instructions. Use capped runs while designing configurations, then run uncapped final measurements when ready.

List all available benchmark and experiment sets:

```sh
docker run --rm -v "$PWD:/workspace" -w /workspace sim-outorder:local python3 scripts/run_experiments.py --list
```

## Benchmark Sets

Predefined sets live in `experiments/benchmark_sets.json`.

Common sets:

```text
quick              GCC_4 only, useful for smoke runs
short              GCC_4, LI_2, PERL_1
all                every benchmark in the supplied bundle
andressa_eduarda   GCC_4, VORTEX_1
max_barn           LI_1, VORTEX_2
```

You can also pass explicit benchmark names:

```sh
make run BENCHMARKS=GCC_4,VORTEX_1 EXPERIMENTS=task1 RESULTS=results/task1
```

## Experiment Sets

Predefined sets live in `experiments/experiment_sets.json`.

```text
smoke       Two quick configurations for infrastructure checks
task1       In-order vs out-of-order, widths 1, 2, 4, and 8
task2       Out-of-order window/RUU-size sweep
task3       Branch predictors nottaken, taken, bimod, and perfect baseline
task4       Three custom processor candidates per benchmark
assignment  All task1, task2, task3, and task4 configurations
```

Each run writes:

```text
results/<name>/results.json
results/<name>/results.csv
results/<name>/runs/<benchmark>/<experiment>/sim-outorder.cfg
results/<name>/runs/<benchmark>/<experiment>/stdout.txt
results/<name>/runs/<benchmark>/<experiment>/stderr.txt
results/<name>/runs/<benchmark>/<experiment>/program.out
results/<name>/runs/<benchmark>/<experiment>/result.json
```

The runner executes each benchmark from an isolated temporary copy of its benchmark directory. This keeps simulator/program side effects out of the checked-in `Benchmarks/` files while preserving the relative paths expected by the supplied command lines.

## Report Generation

Generate the UFPel-themed static report from a results directory:

```sh
python3 scripts/generate_report.py --results results/andressa_eduarda --output site
```

The report includes:

```text
site/index.html
site/assets/style.css
site/data/results.json
site/data/results.csv
site/data/runs/...
```

The generated page includes a `Visualizacoes` section with static SVG plots for cross-benchmark CPI ranking, load/store mix versus CPI, per-task trends, branch-predictor overhead, and custom processor cost/performance comparisons.

Do not manually edit files in `site/`. Edit `experiments/*.json`, rerun experiments, and regenerate the report.

## GitHub Actions And Pages

The workflow at `.github/workflows/experiments.yml` does this automatically:

```text
1. Resolve the selected benchmark set into a GitHub Actions matrix.
2. Build the Docker image inside each matrix job so image builds and benchmark shards both run in parallel.
3. Run one benchmark per matrix job.
4. Upload each shard as an artifact.
5. Merge shards with `scripts/merge_results.py`.
6. Generate the static report with `scripts/generate_report.py`.
7. Validate the generated website with `scripts/validate_site.py`.
8. Upload results as a workflow artifact.
9. Deploy `site/` to GitHub Pages on `main` or manual runs.
```

Enable Pages in the repository settings:

```text
Settings -> Pages -> Build and deployment -> Source -> GitHub Actions
```

By default the workflow runs every benchmark with the complete assignment experiment set using a capped instruction count. Recommended repository variables if you want to override those defaults:

```text
BENCHMARK_SET=all
EXPERIMENT_SET=assignment
MAX_INSTRUCTIONS=100000
TIMEOUT_SEC=1800
```

For the final report, run the workflow manually and set `MAX_INSTRUCTIONS=0` if the full run time is acceptable.

## Agentic Conclusions

The HTML report has an "Interpretacao Agentica" section sourced from:

```text
reports/conclusions.md
```

That file is not generated by a script. It is meant to be written by an analysis agent after the experiments run. In OpenCode, run:

```text
/analyze-experiments
```

The command lives at `.opencode/commands/analyze-experiments.md` and delegates to the subagent in `.opencode/agents/experiment-analyst.md` so the main conversation does not absorb the full analysis context.

The expected workflow is:

```text
1. Run the full experiment matrix with a chosen cap or uncapped final mode.
2. Read `results/<run>/results.json` and `results/<run>/results.csv`.
3. Inspect per-run stdout/config files when a result needs explanation.
4. Use `/analyze-experiments` to invoke the OpenCode subagent and reason about expected architecture behavior.
5. Update `reports/conclusions.md` with measured conclusions and caveats.
6. Regenerate `site/` with `scripts/generate_report.py`.
```

This keeps measured data reproducible while leaving the interpretation as a deliberate reasoning task.

## Source Documents

The implementation follows the PDFs in this repository:

```text
Arq_Avan_Trabalho_Sim-OutOrder_2026_1.pdf
Descricao das caracteristicas dos benchmarks.pdf
```

The benchmark metadata in `experiments/benchmarks.json` was seeded from the supplied benchmark description PDF and `Benchmarks/LinhasComandoTrabalho.txt`.

## Notes

SimpleScalar is licensed for academic and non-commercial use. Keep the Docker image and generated artifacts for this course/research context unless you have the rights to use it otherwise.
