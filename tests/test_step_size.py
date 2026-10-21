"""설계 변수별 격자 간격(StepSize) 및 WAMIT 출력 설정 테스트."""

import io
import os
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.algorithms import run_cma_es, run_de, run_ga, run_pso
from src.algorithms.common import grid_max_indices, make_cache_key, quantize_vector, random_grid_population
from src.physics.wamit_handler import write_frc_file
from src.problems import get_joint_config, get_layout_config, get_shape_config
from src.utils import ConfigValidationError, parse_wec_cfg, resolve_step_sizes
from src.utils.data_handler import load_env_data

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = {"SiteName": "Test", "Hs": 1.0, "Tp": 6.0, "Gamma": 1.4, "Depth": 30.0}
WAMIT = {"NCPU": 1, "RAMGBMAX": 1}


def project_cfg():
    return parse_wec_cfg(os.path.join(PROJECT_ROOT, "config.cfg"))


class TestGridReachesUpperBound(unittest.TestCase):
    """(30 - 0.1) / 0.1 = 298.999... 같은 부동소수점 오차로 상한을 놓치지 않는지."""

    def test_upper_bound_is_reachable(self):
        for lo, hi, step in [(0.1, 30.0, 0.1), (0.0, 0.3, 0.1), (0.5, 0.7, 0.1), (3.0, 25.0, 0.1)]:
            config = {"bounds": [[lo], [hi]], "step_size": [step]}
            expected = round((hi - lo) / step)
            self.assertEqual(int(grid_max_indices(config)[0]), expected, (lo, hi, step))
            self.assertAlmostEqual(float(quantize_vector(np.array([hi]), config)[0]), hi)

    def test_project_config_y_upper_bound(self):
        cfg = project_cfg()
        problem = get_layout_config(cfg["Constraints"], cfg["WEC Parameters"], 3, ENV, WAMIT, 2)
        self.assertAlmostEqual(float(quantize_vector(np.array([25.0, 25.0, 30.0]), problem)[2]), 30.0)


class TestPerVariableStepSize(unittest.TestCase):
    def test_default_step_used_when_not_overridden(self):
        cfg = project_cfg()
        shape = get_shape_config(cfg["Constraints"], ENV, WAMIT, 2)
        self.assertEqual(shape["step_size"], [0.1, 0.1])

    def test_overrides_are_applied_in_vector_order(self):
        cfg = project_cfg()
        cfg["Constraints"].update({"DraftStep": "0.5", "WEC1_XStep": "1.0", "WEC2_YStep": "0.5", "WEC3_XStep": "2.0"})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Y 범위 29.9는 0.5로 나누어떨어지지 않음 (의도된 경고)
            joint = get_joint_config(cfg["Constraints"], cfg["WEC Parameters"], 5, ENV, WAMIT, 2)
        # [R, D, x1, x2, y2, x3, y3]
        self.assertEqual(joint["step_size"], [0.1, 0.5, 1.0, 0.1, 0.5, 2.0, 0.1])

    def test_quantize_and_cache_use_each_variables_step(self):
        config = {"bounds": [[0.5, 3.0], [2.5, 25.0]], "step_size": [0.1, 1.0]}
        q = quantize_vector(np.array([1.234, 10.4]), config)
        np.testing.assert_array_almost_equal(q, [1.2, 10.0])
        self.assertEqual(
            make_cache_key(q, config), make_cache_key(quantize_vector(np.array([1.24, 9.6]), config), config)
        )

    def test_random_population_on_each_grid(self):
        np.random.seed(0)
        config = {"bounds": [[0.5, 3.0], [2.5, 25.0]], "step_size": [0.1, 1.0]}
        pop = random_grid_population(200, config)
        idx = (pop - np.array([0.5, 3.0])) / np.array([0.1, 1.0])
        np.testing.assert_array_almost_equal(idx, np.round(idx))
        self.assertTrue(np.all(pop <= np.array([2.5, 25.0]) + 1e-12))

    def test_invalid_steps(self):
        names, lo, hi = ["Radius"], [0.5], [2.5]
        for bad in ("0", "-0.1", "abc"):
            with self.assertRaises(ConfigValidationError, msg=bad):
                resolve_step_sizes({"RadiusStep": bad}, names, lo, hi)
        with self.assertRaises(ConfigValidationError):  # 범위 폭(2.0)보다 큰 간격
            resolve_step_sizes({"RadiusStep": "3.0"}, names, lo, hi)
        with self.assertRaises(ConfigValidationError):  # StepSize도 변수별 값도 없음
            resolve_step_sizes({}, names, lo, hi)

    def test_non_divisible_range_warns_with_reachable_max(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            resolve_step_sizes({"RadiusStep": "0.3"}, ["Radius"], [0.5], [2.5])
        self.assertEqual(len(caught), 1)
        self.assertIn("2.3", str(caught[0].message))

    def test_divisible_range_does_not_warn(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            resolve_step_sizes({"StepSize": "0.1"}, ["WEC2_Y"], [0.1], [30.0])


class TestAlgorithmsRespectPerVariableGrid(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_every_evaluated_vector_is_on_its_grid(self):
        cfg = project_cfg()
        cfg["Constraints"].update({"RadiusStep": "0.25", "WEC1_XStep": "0.5", "WEC2_YStep": "2.0"})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 의도된 '나누어떨어지지 않음' 경고
            problem = get_joint_config(cfg["Constraints"], cfg["WEC Parameters"], 3, ENV, WAMIT, 2)
        lower, steps = np.array(problem["bounds"][0]), np.array(problem["step_size"])
        seen = []

        def eval_func(vector, _config):
            seen.append(vector.copy())
            return float(-np.sum((vector - 7.0) ** 2)), [0.0] * 3

        np.random.seed(11)
        with redirect_stdout(io.StringIO()):
            for runner, kwargs in [(run_de, {"F": 0.5, "CR": 0.9}), (run_pso, {}), (run_ga, {}), (run_cma_es, {})]:
                runner(problem, eval_func, pop_size=8, max_iter=8, **kwargs)
        idx = (np.array(seen) - lower) / steps
        np.testing.assert_array_almost_equal(idx, np.round(idx))


class TestWamitOutputsAndSiteData(unittest.TestCase):
    def test_frc_requests_only_used_outputs(self):
        # 기본: .1(부가질량/감쇠) + .3(diffraction 가진력). Haskind(.2)는 요청하지 않음.
        with tempfile.TemporaryDirectory() as d:
            write_frc_file(d, 3)
            with open(os.path.join(d, "wec.frc")) as f:
                options = f.readlines()[1].split()[:9]
        self.assertEqual(options, ["1", "0", "1", "0", "0", "0", "0", "0", "0"])

    def test_yeongilmanhang_depth(self):
        data = load_env_data(3, filepath=os.path.join(PROJECT_ROOT, "data", "env_data.csv"))
        self.assertEqual(data["SiteName"], "Yeongilmanhang")
        self.assertEqual(data["Depth"], 13.0)


if __name__ == "__main__":
    unittest.main()
