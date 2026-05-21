# Contributing

This repository is a reproducible experiment/reporting pipeline for the UFPel SimpleScalar `sim-outorder` assignment. Changes should preserve reproducibility, measured-data traceability, and generated-report determinism.

## Add Or Change Benchmarks

1. Edit `experiments/benchmarks.json`.
2. Add the benchmark to at least one set in `experiments/benchmark_sets.json`.
3. Ensure the benchmark directory contains the PISA binary, required inputs, and `config_example_assoc1_direct`.
4. Run `python3 scripts/validate_experiments.py`.
5. Run a dry-run report validation before real simulation:

```sh
python3 scripts/run_experiments.py --benchmarks quick --experiment-set smoke --dry-run --output results/dry-run
python3 scripts/validate_results.py --results results/dry-run
python3 scripts/generate_report.py --results results/dry-run --output site
python3 scripts/validate_site.py --site site --results results/dry-run
```

## Add Or Change Experiments

1. Edit `experiments/experiment_sets.json`.
2. Use real `sim-outorder` option names without the leading dash.
3. Keep `ruu:size` and `lsq:size` as powers of two greater than one.
4. Use `res:memport`, not `res:memports`.
5. Add the experiment to the relevant named set.
6. Run metadata validation and tests:

```sh
python3 scripts/validate_experiments.py
python3 -m unittest discover -s tests
```

## Generated Files

Do not commit `results/` or `site/`. They are generated artifacts and are intentionally ignored. Change metadata, scripts, or conclusions, then regenerate.
