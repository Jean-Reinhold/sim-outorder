#!/usr/bin/env python3
"""Create a GitHub Actions matrix from benchmark set metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from task4_search_space import add_task4_search_space


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = ROOT / "experiments"
TASK_SLUGS = {"Tarefa 1": "task1", "Tarefa 2": "task2", "Tarefa 3": "task3", "Tarefa 4": "task4"}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_selection(raw: str, sets: dict[str, list[str]], available: set[str], kind: str) -> list[str]:
    selected: list[str] = []
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        raise ValueError("No benchmarks selected")
    for token in tokens:
        if token in sets:
            selected.extend(sets[token])
        elif token in available:
            selected.append(token)
        else:
            known = ", ".join(sorted(set(sets) | available))
            raise ValueError(f"Unknown {kind} '{token}'. Known values: {known}")

    unique: list[str] = []
    seen: set[str] = set()
    for name in selected:
        if name not in available:
            raise ValueError(f"{kind} set references unknown {kind} '{name}'")
        if name not in seen:
            unique.append(name)
            seen.add(name)
    return unique


def matrix_for_mode(benchmarks: list[str], experiments: list[str], experiment_doc: dict[str, Any], mode: str) -> dict[str, Any]:
    include: list[dict[str, str]] = []
    if mode == "benchmark":
        experiment_selection = ",".join(experiments)
        include.extend(
            {
                "benchmark": benchmark,
                "experiment_selection": experiment_selection,
                "shard": benchmark,
            }
            for benchmark in benchmarks
        )
    elif mode == "benchmark_task":
        by_task: dict[str, list[str]] = {}
        for experiment_id in experiments:
            task = experiment_doc["experiments"][experiment_id]["task"]
            by_task.setdefault(task, []).append(experiment_id)
        for benchmark in benchmarks:
            for task in sorted(by_task, key=lambda name: TASK_SLUGS.get(name, name)):
                slug = TASK_SLUGS.get(task, task.lower().replace(" ", "-"))
                include.append(
                    {
                        "benchmark": benchmark,
                        "experiment_selection": ",".join(by_task[task]),
                        "shard": f"{benchmark}-{slug}",
                    }
                )
    else:
        raise ValueError(f"Unsupported shard mode: {mode}")
    return {"include": include}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", default="all", help="Benchmark set/name list")
    parser.add_argument("--experiment-set", default="assignment", help="Experiment set/name list")
    parser.add_argument("--mode", choices=["benchmark", "benchmark_task"], default="benchmark", help="Matrix sharding mode")
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Print key=value lines suitable for GITHUB_OUTPUT",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    benchmark_doc = read_json(EXPERIMENTS_DIR / "benchmarks.json")
    benchmark_set_doc = read_json(EXPERIMENTS_DIR / "benchmark_sets.json")
    experiment_doc = add_task4_search_space(read_json(EXPERIMENTS_DIR / "experiment_sets.json"))
    selected = resolve_selection(args.benchmarks, benchmark_set_doc["sets"], set(benchmark_doc["benchmarks"]), "benchmark")
    selected_experiments = resolve_selection(args.experiment_set, experiment_doc["sets"], set(experiment_doc["experiments"]), "experiment")
    matrix = matrix_for_mode(selected, selected_experiments, experiment_doc, args.mode)

    if args.github_output:
        print(f"matrix={json.dumps(matrix, separators=(',', ':'))}")
        print(f"count={len(selected)}")
        print(f"shards={len(matrix['include'])}")
        print(f"benchmarks={','.join(selected)}")
        print(f"experiments={','.join(selected_experiments)}")
    else:
        print(json.dumps(matrix, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
