"""발전량 적분(수력 계수 보간 후 적분) 테스트 (WAMIT 없이 실행)."""

import os
import sys
import unittest
from typing import ClassVar
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.physics.hydro import (  # noqa: E402
    POWER_INTERP,
    POWER_INTERP_STEP,
    HydroData,
    check_power_interp,
    refine_hydro,
)
from src.physics.power_calc import calculate_power, power_from_hydro  # noqa: E402
from src.physics.rao_calc import PTO_NATURAL_FREQUENCY, rao_from_hydro  # noqa: E402
from src.problems import evaluate_shape, get_shape_config  # noqa: E402
from src.utils.config_parser import parse_wec_cfg  # noqa: E402
from src.utils.eval_db import db_name, fingerprint  # noqa: E402

ENV = {"SiteName": "Buan", "Hs": 1.07, "Tp": 5.46, "Gamma": 1.4, "Depth": 50.0}

COARSE = np.round(0.5 + 0.05 * np.arange(51), 6)  # 0.5 ~ 3.0
SEA = {"hs": 1.07, "tp": 5.46, "gamma": 1.4, "wave_spec": 1, "pto_rule": PTO_NATURAL_FREQUENCY}


def smooth_wec(omegas, mass=3.0e4, stiffness=1.0e5):
    """완만한 계수를 가진 1기 WEC. 감쇠가 작아 RAO 봉우리가 0.05보다 좁다."""
    w = np.asarray(omegas, dtype=float)
    n = len(w)
    return HydroData(
        omegas=w.copy(),
        added_mass=(1.0e4 + 2.0e3 * np.cos(w)).reshape(n, 1, 1),
        damping=(2000.0 * w**2 * np.exp(-w)).reshape(n, 1, 1),
        excitation=(4.0e4 * np.exp(-0.3 * w) * np.exp(1j * 0.5 * w)).reshape(n, 1),
        mass=np.array([[mass]]),
        stiffness=np.array([[stiffness]]),
    )


class TestRefineHydro(unittest.TestCase):
    def test_grid_keeps_the_ends_and_the_step(self):
        fine = refine_hydro(smooth_wec(COARSE))
        self.assertEqual(len(fine.omegas), 1001)
        self.assertAlmostEqual(fine.omegas[0], 0.5)
        self.assertAlmostEqual(fine.omegas[-1], 3.0)
        self.assertTrue(np.allclose(np.diff(fine.omegas), POWER_INTERP_STEP))

    def test_coefficients_pass_through_the_solver_points(self):
        hydro = smooth_wec(COARSE)
        fine = refine_hydro(hydro)
        idx = np.round((COARSE - 0.5) / POWER_INTERP_STEP).astype(int)
        self.assertTrue(np.allclose(fine.added_mass[idx], hydro.added_mass))
        self.assertTrue(np.allclose(fine.damping[idx], hydro.damping))
        self.assertTrue(np.allclose(fine.excitation[idx], hydro.excitation))
        self.assertIs(fine.mass, hydro.mass)

    def test_smooth_coefficients_are_interpolated_closely(self):
        fine = refine_hydro(smooth_wec(COARSE))
        exact = smooth_wec(fine.omegas)
        self.assertLess(np.max(np.abs(fine.added_mass / exact.added_mass - 1)), 1e-5)
        self.assertLess(np.max(np.abs(fine.excitation / exact.excitation - 1)), 1e-4)

    def test_uneven_grid_is_accepted(self):
        omegas = np.array([0.5, 0.55, 0.6, 0.61, 0.62, 0.7, 0.9, 1.0])
        fine = refine_hydro(smooth_wec(omegas))
        self.assertAlmostEqual(fine.omegas[-1], 1.0)
        self.assertEqual(len(fine.omegas), 201)


class TestPowerFromHydro(unittest.TestCase):
    def power(self, hydro, config=None):
        return power_from_hydro(hydro, SEA | (config or {}))[0]

    def test_power_is_always_integrated_after_interpolation(self):
        hydro = smooth_wec(COARSE)
        expected = calculate_power(rao_from_hydro(refine_hydro(hydro), PTO_NATURAL_FREQUENCY), SEA)[0]
        self.assertEqual(self.power(hydro), expected)
        # 옛 설정 값은 결과를 바꾸지 않는다 (Simpson 방식은 지워짐)
        self.assertEqual(self.power(hydro, {"power_interp": 0}), expected)

    def test_interpolation_is_closer_to_the_dense_result(self):
        dense = self.power(smooth_wec(np.round(0.5 + 0.000625 * np.arange(4001), 7)))
        simpson = calculate_power(rao_from_hydro(smooth_wec(COARSE), PTO_NATURAL_FREQUENCY), SEA)[0]
        interp = self.power(smooth_wec(COARSE))
        self.assertGreater(abs(simpson / dense - 1), 0.05)  # 이 시험 WEC에서 0.05 Simpson은 약 9% 틀림
        self.assertLess(abs(interp / dense - 1), 1e-5)

    def test_problem_configs_record_the_interpolation(self):
        constraints = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))["Constraints"]
        config = get_shape_config(constraints, ENV, {"NCPU": 1, "RAMGBMAX": 1}, 1)
        self.assertEqual(config["power_interp"], POWER_INTERP)

    def test_config_file_has_no_power_interp_line(self):
        self.assertNotIn("PowerInterp", parse_wec_cfg(os.path.join(ROOT, "config.cfg"))["Simulation"])

    def test_check_power_interp(self):
        for ok in (None, 1, "1"):
            check_power_interp(ok)
        for bad in (0, "0", 2, True, "x"):
            with self.assertRaises(ValueError):
                check_power_interp(bad)

    def test_evaluator_interpolates(self):
        hydro = smooth_wec(COARSE)
        with mock.patch("src.problems.shape_opt.solve_hydrodynamics", return_value=hydro):
            value = evaluate_shape([1.0, 1.0], SEA)[0]
        self.assertEqual(value, self.power(hydro))


class TestDatabaseName(unittest.TestCase):
    CONFIG: ClassVar[dict] = {
        "site_name": "Buan",
        "opt_mode": 3,
        "num_wecs": 5,
        "wave_spec": 1,
        "hs": 1.07,
        "tp": 5.46,
        "gamma": 1.4,
        "depth": 50.0,
        "mesh_panels": 120,
        "solver": 0,
        "omega_max": 3.0,
        "freq_grid": 0,
        "min_spacing": 4,
    }

    def test_old_records_without_the_key_keep_their_name(self):
        # 키가 없는 옛 기록(Simpson)은 지문에 power_interp가 없어 옛 이름 그대로 남는다
        self.assertNotIn("power_interp", fingerprint(self.CONFIG))

    def test_interpolation_has_its_own_database(self):
        old = db_name(fingerprint(self.CONFIG))
        self.assertNotEqual(db_name(fingerprint(self.CONFIG | {"power_interp": 1})), old)


if __name__ == "__main__":
    unittest.main()
