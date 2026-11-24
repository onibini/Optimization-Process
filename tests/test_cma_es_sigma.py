"""CMA-ES 보폭(sigma) 갱신의 상한·하한과 넘침 방지 테스트 (WAMIT 없이 실행)."""

import contextlib
import io
import os
import tempfile
import unittest
import warnings

import numpy as np

from src.algorithms import run_cma_es
from src.algorithms.cma_es import MAX_LOG_SIGMA_CHANGE, MAX_SIGMA, update_sigma

CS, DAMPS, ECHI = 0.4, 1.4, 2.5  # typical values for N = 7


class TestUpdateSigma(unittest.TestCase):
    def test_huge_evolution_path_does_not_overflow(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # an overflow RuntimeWarning would fail the test
            sigma = update_sigma(0.01, 1e300, CS, DAMPS, ECHI, 0.001)
        self.assertTrue(np.isfinite(sigma))
        self.assertAlmostEqual(sigma, 0.01 * np.exp(MAX_LOG_SIGMA_CHANGE))

    def test_bounds(self):
        self.assertEqual(update_sigma(0.9, 1e9, CS, DAMPS, ECHI, 0.001), MAX_SIGMA)
        self.assertEqual(update_sigma(0.0011, 0.0, CS, DAMPS, ECHI, 0.001), 0.001)

    def test_ordinary_update_is_the_standard_formula(self):
        sigma = update_sigma(0.2, 3.0, CS, DAMPS, ECHI, 0.001)
        self.assertAlmostEqual(sigma, 0.2 * np.exp((CS / DAMPS) * (3.0 / ECHI - 1)))


CONFIG = {
    "dimensions": 3,
    "bounds": [[0.0] * 3, [10.0] * 3],
    "step_size": [0.1] * 3,
    "opt_mode": 1,
    "num_wecs": 1,
    "site_name": "Dummy",
}


class TestRunCmaEsSigma(unittest.TestCase):
    def _run(self, sigma_init):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                np.random.seed(0)
                with contextlib.redirect_stdout(io.StringIO()):
                    return run_cma_es(CONFIG, lambda v, c: (-float(np.sum((v - 3.3) ** 2)), [0.0]), 8, 30, sigma_init)
            finally:
                os.chdir(cwd)

    def test_invalid_initial_step_is_rejected(self):
        for bad in (0.0, -0.1, 1.5):
            with self.assertRaises(ValueError, msg=bad):
                self._run(bad)

    def test_largest_initial_step_still_converges(self):
        _, best_f = self._run(1.0)
        self.assertGreater(best_f, -0.5)


if __name__ == "__main__":
    unittest.main()
