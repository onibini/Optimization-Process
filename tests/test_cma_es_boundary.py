"""CMA-ES 경계 처리(경계 밖 거리 벌점, 원래 샘플로 갱신) 테스트 (WAMIT 없이 실행)."""

import contextlib
import io
import os
import tempfile
import unittest

import numpy as np

from src.algorithms import run_cma_es
from src.algorithms.cma_es import BoundPenalty

CONFIG = {
    "dimensions": 3,
    "bounds": [[0.0] * 3, [10.0] * 3],
    "step_size": [0.1] * 3,
    "opt_mode": 1,
    "num_wecs": 1,
    "site_name": "Dummy",
}


def run(eval_func, boundary="penalty", seed=0, pop=8, gens=60):
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            np.random.seed(seed)
            with contextlib.redirect_stdout(io.StringIO()):
                return run_cma_es(CONFIG, eval_func, pop, gens, 0.3, boundary=boundary)
        finally:
            os.chdir(cwd)


class TestBoundPenalty(unittest.TestCase):
    def test_no_penalty_inside_and_positive_outside(self):
        bp = BoundPenalty(2, 8, 4.0)
        bp.gamma[:] = 1.0
        arx = np.array([[0.5, 0.5], [1.2, 0.5], [0.5, -0.3]])
        pen = bp.penalties(arx, np.clip(arx, 0, 1))
        self.assertEqual(pen[0], 0.0)
        self.assertAlmostEqual(pen[1], 0.04 / 2)
        self.assertAlmostEqual(pen[2], 0.09 / 2)

    def test_weights_start_when_the_mean_leaves_the_box(self):
        bp = BoundPenalty(2, 8, 4.0)
        fitness = np.arange(8.0)  # IQR 3.5
        bp.update(fitness, np.array([0.5, 0.5]), 0.2, np.eye(2), 1)
        np.testing.assert_array_equal(bp.gamma, 0.0)
        bp.update(fitness, np.array([1.01, 0.5]), 0.2, np.eye(2), 3)
        np.testing.assert_allclose(bp.gamma, 2 * 3.5 / 0.2**2)

    def test_weights_grow_where_the_mean_is_far_outside_and_shrink_when_too_large(self):
        bp = BoundPenalty(2, 8, 4.0)
        fitness = np.arange(8.0)
        bp.update(fitness, np.array([1.01, 0.5]), 0.2, np.eye(2), 3)
        start = bp.gamma.copy()
        bp.update(fitness, np.array([2.0, 0.5]), 0.2, np.eye(2), 4)  # 5 std outside > 3 std
        self.assertGreater(bp.gamma[0], start[0])
        self.assertEqual(bp.gamma[1], start[1])
        bp.gamma[1] = 100 * start[1]
        bp.update(fitness, np.array([1.01, 0.5]), 0.2, np.eye(2), 5)
        self.assertLess(bp.gamma[1], 100 * start[1])

    def test_non_finite_fitness_is_ignored(self):
        bp = BoundPenalty(2, 8, 4.0)
        bp.update(np.array([-np.inf, 1.0, 2.0, 3.0]), np.array([1.5, 0.5]), 0.2, np.eye(2), 1)
        self.assertTrue(np.all(np.isfinite(bp.gamma)))


class TestRunCmaEsBoundary(unittest.TestCase):
    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            run(lambda v, c: (0.0, [0.0]), boundary="mirror")

    def test_optimum_beyond_the_bound_is_reached_at_the_bound(self):
        # maximum at (12, 12, 5): the best point in the box is (10, 10, 5) with value -8
        def f(v, c):
            return -float((v[0] - 12) ** 2 + (v[1] - 12) ** 2 + (v[2] - 5) ** 2), [0.0]

        for boundary in ("penalty", "clip"):
            best_x, best_f = run(f, boundary)
            np.testing.assert_allclose(best_x, [10.0, 10.0, 5.0], atol=0.11, err_msg=boundary)
            self.assertGreater(best_f, -8.05, boundary)

    def test_rotated_problem_with_boundary_optimum_keeps_improving(self):
        # coupled variables, unconstrained maximum outside the box: needs search along the boundary
        q = np.linalg.qr(np.random.default_rng(3).normal(size=(3, 3)))[0]
        target = np.array([13.0, -2.0, 6.0])

        def f(v, c):
            y = q @ (np.asarray(v) - target)
            return -float(y @ (np.array([1.0, 10.0, 100.0]) * y)), [0.0]

        grid = np.stack(np.meshgrid(*[np.arange(0, 10.01, 0.1)] * 3, indexing="ij"), -1).reshape(-1, 3)
        best_in_box = max(f(x, None)[0] for x in grid[np.argsort(np.sum((grid - [10, 0, 6]) ** 2, 1))[:20000]])
        _, best_f = run(f, "penalty", pop=10, gens=150)
        self.assertGreater(best_f, best_in_box - 1.0)

    def test_reproducible(self):
        def f(v, c):
            return -float(np.sum((np.asarray(v) - 11) ** 2)), [0.0]

        self.assertEqual(run(f, seed=5)[1], run(f, seed=5)[1])


if __name__ == "__main__":
    unittest.main()
