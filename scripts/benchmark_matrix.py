#!/usr/bin/env python3
"""Create a GitHub Actions matrix from benchmark set metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = ROOT / "experiments"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_selection(raw: str, sets: dict[str, list[str]], available: set[str]) -> list[str]:
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
            raise ValueError(f"Unknown benchmark '{token}'. Known values: {known}")

    unique: list[str] = []
    seen: set[str] = set()
    for name in selected:
        if name not in available:
            raise ValueError(f"Benchmark set references unknown benchmark '{name}'")
        if name not in seen:
            unique.append(name)
            seen.add(name)
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", default="all", help="Benchmark set/name list")
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
    selected = resolve_selection(args.benchmarks, benchmark_set_doc["sets"], set(benchmark_doc["benchmarks"]))
    matrix = {"include": [{"benchmark": name} for name in selected]}

    if args.github_output:
        print(f"matrix={json.dumps(matrix, separators=(',', ':'))}")
        print(f"count={len(selected)}")
        print(f"benchmarks={','.join(selected)}")
    else:
        print(json.dumps(matrix, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
