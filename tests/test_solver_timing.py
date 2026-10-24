"""scripts/experiments/solver_timing.py 테스트 (WAMIT 없이 실행)."""

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "solver_timing", os.path.join(ROOT, "scripts", "experiments", "solver_timing.py")
)
timing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(timing)

OUT = """ Frequency     Time           RAD      DIFF  (max iterations)
    0.5000    20:35:57           7       6
    0.5500    20:35:58          12       9
"""


class TestSolverTiming(unittest.TestCase):
    def test_iteration_counts_takes_the_largest_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "wec.out")
            self.assertEqual(timing.iteration_counts(path), (None, None))
            with open(path, "w") as f:
                f.write(OUT)
            self.assertEqual(timing.iteration_counts(path), (12, 9))

    def test_designs_keep_the_spacing_and_bounds(self):
        for name, v in timing.DESIGNS.items():
            positions = timing.decode_symmetric_positions(v[2:], 5)
            self.assertEqual(timing.check_min_distance(positions, v[0], 4.0), 0.0, name)
            self.assertTrue(all(x > 0 for x in v), name)

    def test_main_writes_runs_and_compares_with_direct(self):
        calls = []

        def fake(vector, config):
            calls.append(config["solver"])
            scale = 1.001 if config["solver"] == 0 else 1.0
            return 5000.0 * scale, [1000.0 * scale] * 5

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            args = ["--solvers", "0", "1", "--meshes", "120", "--sites", "Buan", "--designs", "medium"]
            args += ["--repeats", "2", "--out", tmp, "--workspace", os.path.join(tmp, "ws")]
            rows, summary = timing.main(args, evaluate=fake)
            self.assertTrue(os.path.exists(os.path.join(tmp, "solver_timing.csv")))
        self.assertEqual(calls, [0, 1, 0, 1])
        self.assertEqual(len(rows), 4)
        by_solver = {s["solver"]: s for s in summary}
        self.assertAlmostEqual(by_solver[0]["total_pct"], 0.1, places=6)
        self.assertAlmostEqual(by_solver[0]["wec_pct"], 0.1, places=6)
        self.assertEqual(by_solver[1]["total_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
