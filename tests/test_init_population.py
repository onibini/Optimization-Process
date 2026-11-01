"""초기 개체군(InitPop) 테스트: 균등 난수(기본)와 라틴 하이퍼큐브 (WAMIT 없이 실행)."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.algorithms import run_de, run_ga, run_pso
from src.algorithms.common import (
    DEFAULT_INIT_POP,
    check_init_pop,
    grid_max_indices,
    initial_population,
    lhs_grid_population,
    random_grid_population,
)
from src.utils.config_parser import parse_wec_cfg

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 동시최적화와 같은 7변수 격자 (R, D, X1, X2, Y2, X3, Y3)
CONFIG = {
    "dimensions": 7,
    "bounds": [[0.5, 0.5, 3.0, 3.0, 0.1, 3.0, 0.1], [2.5, 5.0, 25.0, 25.0, 30.0, 25.0, 30.0]],
    "step_size": [0.1] * 7,
    "opt_mode": 1,
    "num_wecs": 1,
    "site_name": "init",
}


def on_grid(population, config):
    lower = np.array(config["bounds"][0])
    steps = (population - lower) / np.array(config["step_size"])
    return np.allclose(steps, np.round(steps), atol=1e-6)


class TestCheckInitPop(unittest.TestCase):
    def test_values(self):
        self.assertEqual(DEFAULT_INIT_POP, 0)
        for value in (0, 1):
            self.assertEqual(check_init_pop(value), value)
        for bad in (2, -1, "1", True, 0.5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                check_init_pop(bad)

    def test_default_config_is_random(self):
        cfg = parse_wec_cfg(os.path.join(PROJECT_ROOT, "config.cfg"))
        self.assertEqual(int(cfg["AlgorithmSettings"]["InitPop"]), 0)


class TestLatinHypercube(unittest.TestCase):
    def test_inside_bounds_and_on_grid(self):
        np.random.seed(0)
        pop = lhs_grid_population(100, CONFIG)
        self.assertEqual(pop.shape, (100, 7))
        self.assertTrue(np.all(pop >= np.array(CONFIG["bounds"][0]) - 1e-9))
        self.assertTrue(np.all(pop <= np.array(CONFIG["bounds"][1]) + 1e-9))
        self.assertTrue(on_grid(pop, CONFIG))

    def test_one_point_per_stratum_in_every_variable(self):
        """변수마다 격자 인덱스 범위를 개체 수만큼 나눈 구간에 정확히 한 점씩 들어갑니다."""
        np.random.seed(1)
        pop_size = 50
        pop = lhs_grid_population(pop_size, CONFIG)
        lower = np.array(CONFIG["bounds"][0])
        index = np.round((pop - lower) / np.array(CONFIG["step_size"])).astype(int)
        n_points = grid_max_indices(CONFIG) + 1
        k = np.arange(pop_size)
        for j in range(7):
            # k번째로 작은 점은 k번째 구간 [k/N, (k+1)/N) x 격자 점 수 안에 있습니다.
            ordered = np.sort(index[:, j])
            self.assertTrue(np.all(ordered >= np.floor(k * n_points[j] / pop_size)), msg=f"variable {j}")
            self.assertTrue(np.all(ordered <= np.floor((k + 1) * n_points[j] / pop_size)), msg=f"variable {j}")

    def test_covers_both_ends_better_than_random(self):
        """LHS는 어느 변수든 맨 아래 1/10 구간에 개체 수의 1/10이 들어갑니다(난수는 0개일 수도 있음)."""
        np.random.seed(2)
        pop = lhs_grid_population(100, CONFIG)
        lower, upper = np.array(CONFIG["bounds"][0]), np.array(CONFIG["bounds"][1])
        low_tenth = pop <= lower + 0.1 * (upper - lower)
        self.assertTrue(np.all(low_tenth.sum(axis=0) >= 9))

    def test_more_individuals_than_grid_points(self):
        config = dict(CONFIG, bounds=[[0.0], [0.5]], step_size=[0.1], dimensions=1)
        np.random.seed(3)
        pop = lhs_grid_population(20, config)
        self.assertEqual(sorted(set(np.round(pop[:, 0], 6))), [0.0, 0.1, 0.2, 0.3, 0.4, 0.5])

    def test_reproducible_with_seed(self):
        np.random.seed(4)
        a = lhs_grid_population(30, CONFIG)
        np.random.seed(4)
        b = lhs_grid_population(30, CONFIG)
        np.testing.assert_array_equal(a, b)


class TestInitialPopulation(unittest.TestCase):
    def test_default_is_the_old_random_population(self):
        np.random.seed(5)
        old = random_grid_population(20, CONFIG)
        for config in (CONFIG, dict(CONFIG, init_pop=0)):
            np.random.seed(5)
            np.testing.assert_array_equal(initial_population(20, config), old)

    def test_lhs_switch(self):
        np.random.seed(6)
        lhs = lhs_grid_population(20, CONFIG)
        np.random.seed(6)
        np.testing.assert_array_equal(initial_population(20, dict(CONFIG, init_pop=1)), lhs)

    def test_algorithms_use_the_setting(self):
        """DE, PSO, GA가 InitPop=1에서 LHS 초기 개체군으로 시작하는지(초기 평가 순서로 확인)."""
        for runner, kwargs in ((run_de, {"F": 0.5, "CR": 0.9}), (run_pso, {}), (run_ga, {})):
            seen = []

            def evaluate(vector, cfg, seen=seen):
                seen.append(np.array(vector))
                return -float(np.sum(np.asarray(vector) ** 2)), [0.0]

            cwd = os.getcwd()
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                try:
                    np.random.seed(7)
                    with contextlib.redirect_stdout(io.StringIO()):
                        runner(dict(CONFIG, init_pop=1), evaluate, 10, 1, **kwargs)
                finally:
                    os.chdir(cwd)
            np.random.seed(7)
            expected = lhs_grid_population(10, CONFIG)
            first = np.array(seen[:10])
            # 대칭 정렬·캐시 때문에 순서가 바뀔 수 있어 정렬해서 비교
            np.testing.assert_allclose(np.sort(first, axis=0), np.sort(expected, axis=0), err_msg=runner.__name__)


if __name__ == "__main__":
    unittest.main()
