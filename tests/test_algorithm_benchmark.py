"""scripts/experiments/algorithm_benchmark.py 테스트 (WAMIT 없이 실행)."""

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "algorithm_benchmark", os.path.join(ROOT, "scripts", "experiments", "algorithm_benchmark.py")
)
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


class TestAlgorithmBenchmark(unittest.TestCase):
    def test_run_stops_at_the_budget_and_is_monotone(self):
        for algo in bench.ALGORITHMS:
            best = bench.run_task((algo, "sphere", 3, 50, 0, 400))
            self.assertEqual(len(best), 400, algo)
            self.assertTrue(np.all(np.diff(best) <= 0), algo)

    def test_rotation_keeps_the_minimum_and_couples_variables(self):
        q = bench.rotation(4)
        np.testing.assert_allclose(q @ q.T, np.eye(4), atol=1e-12)
        self.assertGreater(np.abs(q - np.diag(np.diag(q))).max(), 0.1)
        plain = bench.run_task(("de", "sphere", 4, 50, 0, 300))
        rotated = bench.run_task(("de", "sphere", 4, 50, 0, 300, True))
        self.assertFalse(np.array_equal(plain, rotated))

    def test_reproducible_and_no_log_files(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                a = bench.run_task(("depso", "rastrigin", 3, 50, 1, 300))
                b = bench.run_task(("depso", "rastrigin", 3, 50, 1, 300))
                self.assertFalse(os.path.exists("logs"))
            finally:
                os.chdir(cwd)
        np.testing.assert_array_equal(a, b)

    def test_small_study_writes_tables(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            args = ["--algorithms", "de", "depso", "--functions", "sphere", "--dims", "3", "--seeds", "2"]
            finals, curves = bench.main([*args, "--budget", "300", "--grid", "50", "--workers", "1", "--out", tmp])
            self.assertTrue(os.path.exists(os.path.join(tmp, "algorithm_curves.csv")))
        self.assertEqual(set(finals), {("de", "sphere", 3), ("depso", "sphere", 3)})
        self.assertEqual(curves[("de", "sphere", 3)].shape, (3, bench.CHECKPOINTS))


if __name__ == "__main__":
    unittest.main()
