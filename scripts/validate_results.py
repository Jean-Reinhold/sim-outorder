#!/usr/bin/env python3
"""Validate generated results.json/results.csv structure and consistency."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALID_STATUSES = {"completed", "planned"}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    raise SystemExit(f"results validation failed: {message}")


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def validate_results(results_dir: Path) -> None:
    results_json = results_dir / "results.json"
    results_csv = results_dir / "results.csv"
    if not results_json.exists():
        fail(f"missing {results_json}")
    if not results_csv.exists():
        fail(f"missing {results_csv}")

    data = read_json(results_json)
    runs = data.get("runs")
    selected_benchmarks = data.get("selected_benchmarks")
    selected_experiments = data.get("selected_experiments")
    benchmarks = data.get("benchmarks")
    experiments = data.get("experiments")
    if not isinstance(runs, list):
        fail("runs must be a list")
    if not isinstance(selected_benchmarks, list) or not selected_benchmarks:
        fail("selected_benchmarks must be a non-empty list")
    if not isinstance(selected_experiments, list) or not selected_experiments:
        fail("selected_experiments must be a non-empty list")
    if not isinstance(benchmarks, dict) or set(selected_benchmarks) - set(benchmarks):
        fail("benchmarks metadata does not cover selected_benchmarks")
    if not isinstance(experiments, dict) or set(selected_experiments) - set(experiments):
        fail("experiments metadata does not cover selected_experiments")

    expected_runs = len(selected_benchmarks) * len(selected_experiments)
    if len(runs) != expected_runs:
        fail(f"expected {expected_runs} runs, found {len(runs)}")

    seen: set[tuple[str, str]] = set()
    for run in runs:
        benchmark = run.get("benchmark")
        experiment = run.get("experiment")
        if benchmark not in selected_benchmarks:
            fail(f"run references unknown benchmark {benchmark}")
        if experiment not in selected_experiments:
            fail(f"run references unknown experiment {experiment}")
        key = (benchmark, experiment)
        if key in seen:
            fail(f"duplicate run {benchmark}/{experiment}")
        seen.add(key)
        status = run.get("status")
        if status not in VALID_STATUSES:
            fail(f"run {benchmark}/{experiment} has invalid status {status}")
        if status == "completed":
            stats = run.get("stats", {})
            for stat in ["sim_num_insn", "sim_cycle", "sim_CPI", "sim_IPC"]:
                if not numeric(stats.get(stat)):
                    fail(f"completed run {benchmark}/{experiment} missing numeric {stat}")
        files = run.get("files", {})
        if not isinstance(files, dict) or "config" not in files or "stdout" not in files:
            fail(f"run {benchmark}/{experiment} missing file links")
        for file_key in ["config", "stdout", "stderr", "program_output"]:
            rel_path = files.get(file_key)
            if rel_path and not (results_dir / rel_path).exists():
                fail(f"run {benchmark}/{experiment} references missing {file_key}: {rel_path}")

    with results_csv.open("r", encoding="utf-8", newline="") as handle:
        row_count = sum(1 for _ in csv.DictReader(handle))
    if row_count != len(runs):
        fail(f"CSV row count {row_count} does not match run count {len(runs)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="results/latest", help="Results directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results_dir = (ROOT / args.results).resolve() if not Path(args.results).is_absolute() else Path(args.results)
    validate_results(results_dir)
    print(f"Validated results at {results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
