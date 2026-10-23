"""DEPSO 테스트: 사용자의 DEPSO 갱신 규칙을 그대로 옮긴 참조 구현과 같은 결과를 내는지 (WAMIT 없이 실행)."""

import contextlib
import io
import itertools
import os
import tempfile
import unittest

import numpy as np

from src.algorithms import run_depso
from src.algorithms.common import quantize_vector, random_grid_population

DIMS = 4
CONFIG = {
    "dimensions": DIMS,
    "bounds": [[-5.0] * DIMS, [5.0] * DIMS],
    "step_size": [0.05] * DIMS,
    "opt_mode": 1,
    "num_wecs": 1,
    "site_name": "Dummy",
}


def score(x):
    x = np.asarray(x, dtype=float)
    return -float(10 * len(x) + np.sum(x**2 - 10 * np.cos(2 * np.pi * x)))  # maximize -rastrigin


def reference_depso(pop, gens, F=0.5, CR=0.9, w=0.5, c1=1.5, c2=1.5, update="greedy"):
    """The core update of the user's DEPSO (optimization_main.py) on the project grid, without a cache.

    ``update="greedy"`` is the original rule; ``"pbest"`` mutates from the personal bests and always moves the particle;
    ``"move"`` mutates from the current positions and always moves the particle (PSO-style).
    """
    lower, upper = np.array(CONFIG["bounds"][0]), np.array(CONFIG["bounds"][1])
    positions = random_grid_population(pop, CONFIG)
    v_max = np.maximum((upper - lower) * 0.1, 0.05)
    velocities = np.random.uniform(-v_max, v_max, (pop, DIMS))
    fit = np.array([score(p) for p in positions])
    pbest, pbest_fit = positions.copy(), fit.copy()
    gbest, gbest_fit = positions[np.argmax(fit)].copy(), fit.max()
    for _ in range(gens):
        for i in range(pop):
            r1, r2 = np.random.rand(DIMS), np.random.rand(DIMS)
            velocities[i] = np.clip(
                w * velocities[i] + c1 * r1 * (pbest[i] - positions[i]) + c2 * r2 * (gbest - positions[i]),
                -v_max,
                v_max,
            )
            candidate = np.clip(positions[i] + velocities[i], lower, upper)
            idxs = [idx for idx in range(pop) if idx != i]
            donors = pbest if update == "pbest" else positions
            a, b, c = donors[np.random.choice(idxs, 3, replace=False)]
            cross = np.random.rand(DIMS) < CR
            if not np.any(cross):
                cross[np.random.randint(0, DIMS)] = True
            trial = quantize_vector(np.where(cross, a + F * (b - c), candidate), CONFIG)
            f = score(trial)
            if update != "greedy" or f > fit[i]:
                positions[i], fit[i] = trial, f
                if f > pbest_fit[i]:
                    pbest[i], pbest_fit[i] = trial, f
                    if f > gbest_fit:
                        gbest, gbest_fit = trial.copy(), f
    return gbest, gbest_fit


class TestDepso(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _run(self, seed, pop=12, gens=15, **kwargs):
        calls = []

        def evaluate(vector, config):
            calls.append(vector.copy())
            value = score(vector)
            return value, [value]

        np.random.seed(seed)
        with contextlib.redirect_stdout(io.StringIO()):
            best_x, best_f = run_depso(CONFIG, evaluate, pop, gens, **kwargs)
        return best_x, best_f, calls

    def test_same_result_as_the_reference_rules(self):
        for update, seed in itertools.product(("pbest", "move", "greedy"), (0, 1, 2)):
            best_x, best_f, _ = self._run(seed, update=update)
            np.random.seed(seed)
            ref_x, ref_f = reference_depso(12, 15, update=update)
            self.assertAlmostEqual(best_f, ref_f, places=12, msg=update)
            np.testing.assert_allclose(best_x, ref_x)

    def test_default_is_the_original_greedy_rule(self):
        _, f_default, _ = self._run(1)
        _, f_greedy, _ = self._run(1, update="greedy")
        self.assertEqual(f_default, f_greedy)

    def test_update_rules_differ_and_unknown_rule_is_rejected(self):
        _, f_pbest, _ = self._run(0, update="pbest")
        _, f_greedy, _ = self._run(0, update="greedy")
        self.assertNotEqual(f_pbest, f_greedy)
        with self.assertRaises(ValueError):
            self._run(0, update="other")

    def test_one_evaluation_per_particle_and_generation(self):
        _, _, calls = self._run(4, pop=10, gens=5)
        self.assertLessEqual(len(calls), 10 + 10 * 5)  # initial swarm + 1 per particle and generation, minus cache hits
        self.assertGreater(len(calls), 10 + 10 * 5 // 2)

    def test_pso_only_and_de_only_limits(self):
        # CR = 0 keeps the PSO move except one forced DE component; the run still improves
        _, best_f, calls = self._run(5, pop=10, gens=10, CR=0.0)
        self.assertGreater(best_f, max(score(c) for c in calls[:10]))

    def test_improves_and_stays_on_the_grid(self):
        best_x, best_f, calls = self._run(7, pop=20, gens=40)
        self.assertGreater(best_f, max(score(c) for c in calls[:20]))
        np.testing.assert_allclose(best_x, quantize_vector(best_x, CONFIG))
        self.assertTrue(np.all(np.abs(best_x) <= 5.0))

    def test_small_population_is_rejected(self):
        with self.assertRaises(ValueError):
            run_depso(CONFIG, lambda v, c: (0.0, [0.0]), 3, 1)


if __name__ == "__main__":
    unittest.main()
