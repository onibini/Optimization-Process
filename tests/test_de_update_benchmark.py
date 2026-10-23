"""scripts/experiments/de_update_benchmark.py 테스트: 즉시 교체 DE가 프로젝트 run_de와 같은지 (WAMIT 없이 실행)."""

import contextlib
import importlib.util
import io
import itertools
import os
import tempfile
import unittest

import numpy as np

from src.algorithms import run_de

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "de_update_benchmark", os.path.join(ROOT, "scripts", "experiments", "de_update_benchmark.py")
)
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


def rastrigin(x):
    x = np.asarray(x, dtype=float)
    return float(10 * len(x) + np.sum(x**2 - 10 * np.cos(2 * np.pi * x)))


class TestImmediateEqualsProjectDE(unittest.TestCase):
    def test_same_trajectory_as_run_de_on_a_grid(self):
        dims, pop, gens = 3, 8, 6
        config = {
            "dimensions": dims,
            "bounds": [[-5.0] * dims, [5.0] * dims],
            "step_size": [0.1] * dims,
            "opt_mode": 1,
            "num_wecs": 1,
            "site_name": "bench",
        }
        project_best = []

        def project_eval(vector, config):
            value = -rastrigin(vector)  # run_de maximizes
            project_best.append(value)
            return value, [value]

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                np.random.seed(3)
                with contextlib.redirect_stdout(io.StringIO()):
                    _, best_f = run_de(config, project_eval, pop, gens, 0.5, 0.9)
            finally:
                os.chdir(cwd)
        np.random.seed(3)
        history = bench.run(rastrigin, -5.0, 5.0, dims, pop, gens, 0.5, 0.9, "immediate", step=0.1)
        self.assertAlmostEqual(-best_f, history[-1], places=9)

    def test_modes_share_the_initial_population_and_differ_later(self):
        hist = {}
        for mode in bench.MODES:
            np.random.seed(0)
            hist[mode] = bench.run(rastrigin, -5.12, 5.12, 5, 20, 30, 0.5, 0.9, mode)
        self.assertEqual(hist["immediate"][0], hist["generation"][0])
        self.assertNotEqual(hist["immediate"], hist["generation"])
        for h in hist.values():
            self.assertTrue(all(b <= a for a, b in itertools.pairwise(h)))  # best never gets worse

    def test_functions_have_their_minimum_zero(self):
        optima = {"rosenbrock": 1.0, "schwefel": 420.9687463}
        for name, (func, _, _) in bench.FUNCTIONS.items():
            x = np.full((1, 7), optima.get(name, 0.0))
            self.assertAlmostEqual(float(func(x)[0]), 0.0, places=4, msg=name)

    def test_small_run_writes_tables(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            finals, curves = bench.main(
                [
                    "--functions",
                    "sphere",
                    "--dims",
                    "3",
                    "--seeds",
                    "2",
                    "--pop",
                    "8",
                    "--gens",
                    "3",
                    "--out",
                    tmp,
                    "--workers",
                    "1",
                ]
            )
            self.assertTrue(os.path.exists(os.path.join(tmp, "de_update_final.csv")))
        self.assertEqual(len(finals), 2)
        self.assertEqual(curves[("sphere", 3, 0, "immediate")].shape, (3, 4))

    def test_run_task_is_reproducible(self):
        task = ("rastrigin", 4, 0, "generation", 5, 10, 5, 0.5, 0.9)
        self.assertEqual(bench.run_task(task), bench.run_task(task))


if __name__ == "__main__":
    unittest.main()
