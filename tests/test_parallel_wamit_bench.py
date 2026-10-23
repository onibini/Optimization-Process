"""scripts/experiments/parallel_wamit_bench.py 테스트 (가짜 평가 함수, WAMIT 없이 실행)."""

import contextlib
import csv
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "parallel_wamit_bench", os.path.join(ROOT, "scripts", "experiments", "parallel_wamit_bench.py")
)
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


def fake_evaluate(vector, config):
    assert config["ncpu"] in (8, 2)
    return float(sum(vector)), [0.0] * 5


class TestParallelWamitBench(unittest.TestCase):
    def test_table_and_identical_powers(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with (
                    mock.patch.object(bench, "evaluate_joint", fake_evaluate),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    rows = bench.main(["--combos", "1x8", "4x2", "--designs", "6", "--config", f"{ROOT}/config.cfg"])
                with open("logs/parallel_wamit_bench.csv", encoding="utf-8") as f:
                    table = list(csv.DictReader(f))
                self.assertFalse(os.path.exists(os.path.join("workspace", "pb_4x2")))
            finally:
                os.chdir(cwd)
        self.assertEqual([(r["workers"], r["ncpu"]) for r in rows], [(1, 8), (4, 2)])
        self.assertEqual(len(table), 2)
        self.assertEqual(rows[1]["max_power_diff_pct"], 0.0)

    def test_designs_are_feasible_and_reproducible(self):
        cfg = bench.parse_wec_cfg(os.path.join(ROOT, "config.cfg"))
        config = bench.build_config(cfg, 1, 8, "ws")
        a = bench.feasible_designs(config, 5, 3)
        b = bench.feasible_designs(config, 5, 3)
        self.assertEqual([list(x) for x in a], [list(x) for x in b])
        for d in a:
            positions = bench.decode_symmetric_positions(d[2:], 5)
            self.assertEqual(bench.check_min_distance(positions, d[0], config["min_spacing"]), 0)


if __name__ == "__main__":
    unittest.main()
