# Architecture

The project has four layers:

1. Metadata in `experiments/*.json` describes benchmarks, experiment sets, and report text.
2. `scripts/run_experiments.py` renders `sim-outorder.cfg`, executes SimpleScalar in isolated benchmark copies, and writes structured results.
3. `scripts/merge_results.py` combines parallel CI shards into a single aggregate result directory.
4. `scripts/generate_report.py` builds the static HTML report and copies raw data into `site/data/`.

## CI Flow

The GitHub Actions workflow is intentionally split into quality, experiment, report, and deploy phases.

```text
plan -> quality -> experiments matrix -> report -> deploy
```

The `plan` job resolves `BENCHMARK_SET`, `EXPERIMENT_SET`, and `SHARD_MODE` into a matrix with `scripts/benchmark_matrix.py`.

The `quality` job fails early if metadata, Python syntax, unit tests, or dry-run site generation are broken.

The `experiments` matrix builds the Docker image and runs one shard per job. The default shard is one benchmark. Manual runs can use `benchmark_task` to split each benchmark into task-level shards for long final simulations.

The `report` job downloads all shard artifacts, merges them, validates results, generates the site, validates the site, uploads artifacts, and optionally creates a GitHub Release.

The `deploy` job publishes the validated `site/` directory to GitHub Pages.

## Data Contract

Every generated report should be traceable to:

- `results.json` for full structured data.
- `results.csv` for tabular analysis.
- `runs/<benchmark>/<experiment>/sim-outorder.cfg` for the exact simulator configuration.
- `runs/<benchmark>/<experiment>/stdout.txt` and `stderr.txt` for simulator logs.
- `provenance` in `results.json` for commit/workflow/runtime metadata.
