# Reproducibility

## Local Validation

Run cheap checks before simulation:

```sh
python3 scripts/validate_experiments.py
python3 -m unittest discover -s tests
python3 scripts/run_experiments.py --benchmarks short --experiment-set smoke --dry-run --output results/dry-run
python3 scripts/validate_results.py --results results/dry-run
python3 scripts/generate_report.py --results results/dry-run --output site
python3 scripts/validate_site.py --site site --results results/dry-run
```

Run a capped real check with Docker:

```sh
make docker-build
make run BENCHMARKS=quick EXPERIMENTS=assignment MAX_INST=1000 TIMEOUT_SEC=300 JOBS=4 RESULTS=results/check
python3 scripts/validate_results.py --results results/check
make report RESULTS=results/check
make validate-site RESULTS=results/check
```

## Capped And Final Runs

Capped runs are useful for fast feedback and CI. Treat them as preliminary unless the cap is explicitly part of the experiment.

Use `MAX_INST=0` only when full uncapped runtime is acceptable:

```sh
make run BENCHMARKS=all EXPERIMENTS=assignment MAX_INST=0 TIMEOUT_SEC=0 JOBS=4 RESULTS=results/final
```

For GitHub Actions, run the workflow manually and choose:

```text
benchmark_set=all
experiment_set=assignment
max_instructions=0
timeout_sec=0
worker_jobs=2
shard_mode=benchmark_task
```

Set `release_tag` during a manual final run to preserve the validated report and data as GitHub Release assets.
