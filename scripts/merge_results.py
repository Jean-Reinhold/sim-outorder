#!/usr/bin/env python3
"""Merge per-benchmark experiment shards into one reportable results directory."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import Any

from run_experiments import CSV_FIELDS, csv_row, now_iso, read_json, write_json


ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: Path, runs: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for run in runs:
            writer.writerow(csv_row(run))


def unique_extend(target: list[str], values: list[str]) -> None:
    seen = set(target)
    for value in values:
        if value not in seen:
            target.append(value)
            seen.add(value)


def merge_results(inputs: list[Path], output: Path, benchmark_selection: str | None, experiment_selection: str | None) -> dict[str, Any]:
    shard_paths = [path for path in inputs if (path / "results.json").exists()]
    if not shard_paths:
        raise FileNotFoundError("No shard results.json files found")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    selected_benchmarks: list[str] = []
    selected_experiments: list[str] = []
    benchmarks: dict[str, Any] = {}
    experiments: dict[str, Any] = {}
    runs: list[dict[str, Any]] = []
    shard_summaries: list[dict[str, Any]] = []
    first: dict[str, Any] | None = None

    for shard_path in sorted(shard_paths):
        shard = read_json(shard_path / "results.json")
        if first is None:
            first = shard
        unique_extend(selected_benchmarks, shard.get("selected_benchmarks", []))
        unique_extend(selected_experiments, shard.get("selected_experiments", []))
        benchmarks.update(shard.get("benchmarks", {}))
        experiments.update(shard.get("experiments", {}))
        runs.extend(shard.get("runs", []))
        shard_summaries.append(
            {
                "path": str(shard_path),
                "selected_benchmarks": shard.get("selected_benchmarks", []),
                "selected_experiments": shard.get("selected_experiments", []),
                "run_count": len(shard.get("runs", [])),
                "provenance": shard.get("provenance", {}),
            }
        )

        runs_source = shard_path / "runs"
        if runs_source.exists():
            shutil.copytree(runs_source, output / "runs", dirs_exist_ok=True)

    assert first is not None
    aggregate = {
        "schema_version": first.get("schema_version", 1),
        "generated_at": now_iso(),
        "started_at": first.get("started_at"),
        "repo_root": str(ROOT),
        "sim_bin": first.get("sim_bin"),
        "max_instructions": first.get("max_instructions"),
        "timeout_sec": first.get("timeout_sec"),
        "benchmark_selection": benchmark_selection or ",".join(selected_benchmarks),
        "experiment_selection": experiment_selection or first.get("experiment_selection"),
        "selected_benchmarks": selected_benchmarks,
        "selected_experiments": selected_experiments,
        "benchmarks": benchmarks,
        "experiments": experiments,
        "provenance": {
            **first.get("provenance", {}),
            "generated_by": "scripts/merge_results.py",
            "merged_at": now_iso(),
            "merged_shard_count": len(shard_summaries),
            "shards": shard_summaries,
        },
        "runs": sorted(runs, key=lambda run: (run.get("benchmark", ""), run.get("experiment", ""))),
    }
    write_json(output / "results.json", aggregate)
    write_csv(output / "results.csv", aggregate["runs"])
    return aggregate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True, help="Shard result directories")
    parser.add_argument("--output", default="results/ci", help="Merged output directory")
    parser.add_argument("--benchmark-selection", help="Original benchmark selection label")
    parser.add_argument("--experiment-selection", help="Original experiment selection label")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    inputs = [(ROOT / path).resolve() if not Path(path).is_absolute() else Path(path) for path in args.inputs]
    aggregate = merge_results(inputs, output, args.benchmark_selection, args.experiment_selection)
    print(f"Merged {len(aggregate['runs'])} runs from {len(inputs)} shard path(s) into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
