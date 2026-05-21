from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import merge_results  # noqa: E402
import validate_experiments  # noqa: E402
import validate_results  # noqa: E402
import validate_site  # noqa: E402


class ScriptTests(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def test_metadata_validation_passes(self) -> None:
        validate_experiments.validate_all()

    def test_benchmark_matrix_modes(self) -> None:
        benchmark = self.run_script("scripts/benchmark_matrix.py", "--benchmarks", "short", "--experiment-set", "smoke")
        benchmark_matrix = json.loads(benchmark.stdout)
        self.assertEqual(len(benchmark_matrix["include"]), 3)
        self.assertEqual(benchmark_matrix["include"][0]["experiment_selection"], "task1_width1_ooo,task3_bimod")

        benchmark_task = self.run_script(
            "scripts/benchmark_matrix.py",
            "--benchmarks",
            "quick",
            "--experiment-set",
            "assignment",
            "--mode",
            "benchmark_task",
        )
        benchmark_task_matrix = json.loads(benchmark_task.stdout)
        self.assertEqual(len(benchmark_task_matrix["include"]), 4)
        self.assertEqual({entry["benchmark"] for entry in benchmark_task_matrix["include"]}, {"GCC_4"})

    def test_dry_run_merge_report_and_site_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sim-outorder-test-") as raw_tmp:
            tmp = Path(raw_tmp)
            shard_a = tmp / "GCC_4"
            shard_b = tmp / "LI_2"
            merged = tmp / "merged"
            site = tmp / "site"

            self.run_script(
                "scripts/run_experiments.py",
                "--benchmarks",
                "GCC_4",
                "--experiment-set",
                "smoke",
                "--dry-run",
                "--output",
                str(shard_a),
            )
            self.run_script(
                "scripts/run_experiments.py",
                "--benchmarks",
                "LI_2",
                "--experiment-set",
                "smoke",
                "--dry-run",
                "--output",
                str(shard_b),
            )

            aggregate = merge_results.merge_results([shard_a, shard_b], merged, "GCC_4,LI_2", "smoke")
            self.assertEqual(len(aggregate["runs"]), 4)
            self.assertEqual(aggregate["provenance"]["merged_shard_count"], 2)
            validate_results.validate_results(merged)

            self.run_script("scripts/generate_report.py", "--results", str(merged), "--output", str(site))
            validate_site.validate(site, merged)


if __name__ == "__main__":
    unittest.main()
