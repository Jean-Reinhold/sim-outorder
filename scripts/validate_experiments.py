#!/usr/bin/env python3
"""Validate benchmark, experiment, and report metadata before simulation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = ROOT / "experiments"
TASKS = {"Tarefa 1", "Tarefa 2", "Tarefa 3", "Tarefa 4"}
ALLOWED_OPTIONS = {
    "fetch:ifqsize",
    "decode:width",
    "issue:width",
    "issue:inorder",
    "ruu:size",
    "commit:width",
    "lsq:size",
    "res:ialu",
    "res:imult",
    "res:fpalu",
    "res:fpmult",
    "res:memport",
    "bpred",
}
INTEGER_OPTIONS = ALLOWED_OPTIONS - {"issue:inorder", "bpred"}
BRANCH_PREDICTORS = {"nottaken", "taken", "bimod", "perfect"}
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class ValidationError(Exception):
    pass


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def is_power_of_two(value: int) -> bool:
    return value > 1 and value & (value - 1) == 0


def validate_benchmarks(doc: dict[str, Any]) -> None:
    require(doc.get("schema_version") == 1, "benchmarks.json schema_version must be 1")
    benchmarks = doc.get("benchmarks")
    require(isinstance(benchmarks, dict) and benchmarks, "benchmarks.json must contain benchmarks")
    for name, bench in benchmarks.items():
        require(SAFE_ID.match(name) is not None, f"benchmark id is not safe: {name}")
        require(isinstance(bench, dict), f"benchmark {name} must be an object")
        for field in ["family", "directory", "program", "input", "description"]:
            require(isinstance(bench.get(field), str) and bench[field], f"benchmark {name} missing string field {field}")
        directory = ROOT / bench["directory"]
        require(directory.is_dir(), f"benchmark {name} directory does not exist: {bench['directory']}")
        require((directory / bench["program"]).exists(), f"benchmark {name} program not found: {bench['program']}")
        require((directory / "config_example_assoc1_direct").exists(), f"benchmark {name} missing base cache config")
        if "stdin" in bench:
            require((directory / bench["stdin"]).exists(), f"benchmark {name} stdin file not found: {bench['stdin']}")
        args = bench.get("args", [])
        require(isinstance(args, list) and all(isinstance(arg, str) for arg in args), f"benchmark {name} args must be strings")
        total = bench.get("total_instructions")
        load_store = bench.get("load_store_instructions")
        require(isinstance(total, int) and total > 0, f"benchmark {name} total_instructions must be a positive int")
        require(isinstance(load_store, int) and 0 <= load_store <= total, f"benchmark {name} load_store_instructions is invalid")


def validate_benchmark_sets(doc: dict[str, Any], benchmark_names: set[str]) -> None:
    require(doc.get("schema_version") == 1, "benchmark_sets.json schema_version must be 1")
    sets = doc.get("sets")
    require(isinstance(sets, dict) and sets, "benchmark_sets.json must contain sets")
    for name, members in sets.items():
        require(SAFE_ID.match(name) is not None, f"benchmark set id is not safe: {name}")
        require(isinstance(members, list) and members, f"benchmark set {name} must be a non-empty list")
        seen: set[str] = set()
        for member in members:
            require(member in benchmark_names, f"benchmark set {name} references unknown benchmark {member}")
            require(member not in seen, f"benchmark set {name} duplicates benchmark {member}")
            seen.add(member)


def validate_options(exp_id: str, options: dict[str, Any]) -> None:
    require(options, f"experiment {exp_id} must define options")
    unknown = sorted(set(options) - ALLOWED_OPTIONS)
    require(not unknown, f"experiment {exp_id} has unknown option(s): {', '.join(unknown)}")
    for name in INTEGER_OPTIONS:
        if name in options:
            value = options[name]
            require(isinstance(value, int) and value > 0, f"experiment {exp_id} option {name} must be a positive int")
    if "issue:inorder" in options:
        require(isinstance(options["issue:inorder"], bool), f"experiment {exp_id} option issue:inorder must be bool")
    if "bpred" in options:
        require(options["bpred"] in BRANCH_PREDICTORS, f"experiment {exp_id} uses unsupported bpred {options['bpred']}")
    for name in ["ruu:size", "lsq:size"]:
        if name in options:
            require(is_power_of_two(options[name]), f"experiment {exp_id} option {name} must be a power of two greater than one")


def validate_experiments(doc: dict[str, Any]) -> None:
    require(doc.get("schema_version") == 1, "experiment_sets.json schema_version must be 1")
    experiments = doc.get("experiments")
    sets = doc.get("sets")
    require(isinstance(experiments, dict) and experiments, "experiment_sets.json must contain experiments")
    require(isinstance(sets, dict) and sets, "experiment_sets.json must contain sets")
    for exp_id, exp in experiments.items():
        require(SAFE_ID.match(exp_id) is not None, f"experiment id is not safe: {exp_id}")
        require(isinstance(exp, dict), f"experiment {exp_id} must be an object")
        require(exp.get("task") in TASKS, f"experiment {exp_id} has invalid task {exp.get('task')}")
        for field in ["title", "summary"]:
            require(isinstance(exp.get(field), str) and exp[field], f"experiment {exp_id} missing string field {field}")
        options = exp.get("options")
        require(isinstance(options, dict), f"experiment {exp_id} options must be an object")
        validate_options(exp_id, options)
    for name, members in sets.items():
        require(SAFE_ID.match(name) is not None, f"experiment set id is not safe: {name}")
        require(isinstance(members, list) and members, f"experiment set {name} must be a non-empty list")
        seen: set[str] = set()
        for member in members:
            require(member in experiments, f"experiment set {name} references unknown experiment {member}")
            require(member not in seen, f"experiment set {name} duplicates experiment {member}")
            seen.add(member)


def validate_report(doc: dict[str, Any]) -> None:
    require(doc.get("schema_version") == 1, "report.json schema_version must be 1")
    for field in ["title", "institution", "unit", "course", "semester", "simulator"]:
        require(isinstance(doc.get(field), str) and doc[field], f"report.json missing string field {field}")
    tasks = doc.get("tasks")
    require(isinstance(tasks, dict), "report.json tasks must be an object")
    require(TASKS <= set(tasks), "report.json must describe every assignment task")
    for task, data in tasks.items():
        require(task in TASKS, f"report.json has unknown task {task}")
        require(isinstance(data.get("title"), str) and data["title"], f"report task {task} missing title")
        require(isinstance(data.get("goal"), str) and data["goal"], f"report task {task} missing goal")
        questions = data.get("questions")
        require(isinstance(questions, list) and all(isinstance(item, str) and item for item in questions), f"report task {task} questions are invalid")


def validate_all() -> None:
    benchmark_doc = read_json(EXPERIMENTS_DIR / "benchmarks.json")
    benchmark_set_doc = read_json(EXPERIMENTS_DIR / "benchmark_sets.json")
    experiment_doc = read_json(EXPERIMENTS_DIR / "experiment_sets.json")
    report_doc = read_json(EXPERIMENTS_DIR / "report.json")
    validate_benchmarks(benchmark_doc)
    validate_benchmark_sets(benchmark_set_doc, set(benchmark_doc["benchmarks"]))
    validate_experiments(experiment_doc)
    validate_report(report_doc)


def main() -> int:
    try:
        validate_all()
    except ValidationError as exc:
        raise SystemExit(f"experiment metadata validation failed: {exc}") from exc
    print("Experiment metadata is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
