#!/usr/bin/env python3
"""Validate that generated Pages output contains complete report data."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SECTIONS = [
    'id="overview"',
    'id="tasks"',
    'id="benchmarks"',
    'id="experiments"',
    'id="visuals"',
    'id="analysis"',
    'id="conclusions"',
    'id="methodology"',
]


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    raise SystemExit(f"site validation failed: {message}")


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def validate(site: Path, results_dir: Path) -> None:
    index = site / "index.html"
    style = site / "assets" / "style.css"
    site_json = site / "data" / "results.json"
    site_csv = site / "data" / "results.csv"
    source_json = results_dir / "results.json"

    for path in [index, style, site_json, site_csv, source_json, site / ".nojekyll"]:
        if not path.exists():
            fail(f"missing required file {path}")

    html = index.read_text(encoding="utf-8")
    for marker in REQUIRED_SECTIONS:
        if marker not in html:
            fail(f"missing report section marker {marker}")
    for asset in ['href="assets/style.css"', 'href="data/results.json"', 'href="data/results.csv"']:
        if asset not in html:
            fail(f"missing report link {asset}")

    source = read_json(source_json)
    copied = read_json(site_json)
    runs = copied.get("runs", [])
    expected_runs = len(copied.get("selected_benchmarks", [])) * len(copied.get("selected_experiments", []))
    if expected_runs and len(runs) != expected_runs:
        fail(f"expected {expected_runs} runs, found {len(runs)}")
    if len(runs) != len(source.get("runs", [])):
        fail("site data/results.json run count differs from source results.json")
    if count_csv_rows(site_csv) != len(runs):
        fail("site data/results.csv row count differs from results.json run count")

    bad_runs = [run for run in runs if run.get("status") not in {"completed", "planned"}]
    if bad_runs:
        names = ", ".join(f"{run.get('benchmark')}:{run.get('experiment')}" for run in bad_runs[:5])
        fail(f"report contains failed or timed-out runs: {names}")

    if 'id="visuals"' in html and "plot-card" not in html:
        fail("visual section exists but no plot cards were rendered")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="site", help="Generated site directory")
    parser.add_argument("--results", default="results/latest", help="Source results directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    site = (ROOT / args.site).resolve() if not Path(args.site).is_absolute() else Path(args.site)
    results = (ROOT / args.results).resolve() if not Path(args.results).is_absolute() else Path(args.results)
    validate(site, results)
    print(f"Validated generated site at {site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
