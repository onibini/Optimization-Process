"""설계 변수 양수 규칙(0 < Min < Max) 검증 테스트."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.algorithms import run_cma_es, run_de, run_ga, run_pso
from src.problems import get_joint_config, get_layout_config, get_shape_config
from src.utils import ConfigValidationError, parse_wec_cfg, require_positive, validate_design_bounds

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = {"SiteName": "Test", "Hs": 1.0, "Tp": 6.0, "Gamma": 1.4, "Depth": 30.0}
WAMIT = {"NCPU": 1, "RAMGBMAX": 1}


def project_cfg():
    return parse_wec_cfg(os.path.join(PROJECT_ROOT, "config.cfg"))


class TestProjectConfigIsValid(unittest.TestCase):
    def test_all_modes_and_wec_counts_pass_validation(self):
        cfg = project_cfg()
        constraints, params = cfg["Constraints"], cfg["WEC Parameters"]
        shape = get_shape_config(constraints, ENV, WAMIT, 2)
        self.assertTrue(all(lo > 0 for lo in shape["bounds"][0]))
        for n in (1, 3, 5):
            for builder in (get_layout_config, get_joint_config):
                problem = builder(constraints, params, n, ENV, WAMIT, 2)
                lower, upper = problem["bounds"]
                self.assertTrue(all(lo > 0 for lo in lower), (builder.__name__, n))
                self.assertTrue(all(hi > lo for lo, hi in zip(lower, upper, strict=True)), (builder.__name__, n))


class TestRejectsNonPositive(unittest.TestCase):
    def _with(self, section, **overrides):
        cfg = project_cfg()
        cfg[section].update({k: str(v) for k, v in overrides.items()})
        return cfg

    def test_shape_bounds(self):
        for key, value in [("RadiusMin", 0), ("RadiusMin", -0.5), ("DraftMin", 0.0)]:
            cfg = self._with("Constraints", **{key: value})
            with self.assertRaises(ConfigValidationError, msg=key):
                get_shape_config(cfg["Constraints"], ENV, WAMIT, 2)

    def test_layout_bounds(self):
        for key, value in [("WEC1_XMin", 0), ("WEC2_YMin", 0), ("WEC3_YMin", -1.0), ("WEC2_XMin", -3.0)]:
            cfg = self._with("Constraints", **{key: value})
            with self.assertRaises(ConfigValidationError, msg=key):
                get_layout_config(cfg["Constraints"], cfg["WEC Parameters"], 5, ENV, WAMIT, 2)

    def test_joint_bounds(self):
        cfg = self._with("Constraints", WEC2_YMin=0)
        with self.assertRaises(ConfigValidationError):
            get_joint_config(cfg["Constraints"], cfg["WEC Parameters"], 3, ENV, WAMIT, 2)

    def test_max_must_exceed_min(self):
        cfg = self._with("Constraints", RadiusMin=2.5, RadiusMax=2.5)
        with self.assertRaises(ConfigValidationError):
            get_shape_config(cfg["Constraints"], ENV, WAMIT, 2)

    def test_fixed_geometry_and_grid_parameters(self):
        for section, key in [
            ("WEC Parameters", "FixedRadius"),
            ("WEC Parameters", "FixedDraft"),
            ("WEC Parameters", "MinSpacing"),
            ("Constraints", "StepSize"),
        ]:
            cfg = self._with(section, **{key: 0})
            with self.assertRaises(ConfigValidationError, msg=key):
                get_layout_config(cfg["Constraints"], cfg["WEC Parameters"], 3, ENV, WAMIT, 2)

    def test_unused_wec3_bounds_are_not_required_for_three_wecs(self):
        cfg = self._with("Constraints", WEC3_YMin=-1.0)
        get_layout_config(cfg["Constraints"], cfg["WEC Parameters"], 3, ENV, WAMIT, 2)  # no error

    def test_error_message_lists_every_bad_variable(self):
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_design_bounds(["A", "B"], [0.0, -1.0], [1.0, 1.0])
        self.assertIn("A", str(ctx.exception))
        self.assertIn("B", str(ctx.exception))

    def test_require_positive_rejects_non_numbers(self):
        for bad in ("abc", "nan", "inf"):
            with self.assertRaises(ConfigValidationError):
                require_positive("X", bad)


class TestOptimizersStayPositive(unittest.TestCase):
    """양수 하한이면 모든 알고리즘의 모든 평가 벡터가 양수로 유지되는지 확인."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_every_evaluated_vector_is_positive(self):
        cfg = project_cfg()
        problem = get_joint_config(cfg["Constraints"], cfg["WEC Parameters"], 5, ENV, WAMIT, 2)
        seen = []

        def eval_func(vector, _config):
            seen.append(vector.copy())
            # 하한 쪽으로 강하게 끌어당기는 목적함수 (경계 근처 탐색 유도)
            return -float(np.sum(vector)), [0.0] * 5

        np.random.seed(7)
        with redirect_stdout(io.StringIO()):
            run_de(problem, eval_func, pop_size=10, max_iter=15, F=0.9, CR=0.9)
            run_pso(problem, eval_func, pop_size=10, max_iter=15)
            run_ga(problem, eval_func, pop_size=10, max_iter=15)
            run_cma_es(problem, eval_func, pop_size=10, max_iter=15)
        all_vectors = np.array(seen)
        self.assertGreater(len(all_vectors), 0)
        self.assertTrue(np.all(all_vectors > 0), all_vectors.min(axis=0))


if __name__ == "__main__":
    unittest.main()
