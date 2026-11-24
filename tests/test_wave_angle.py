"""입사파 방향(WaveAngle) 옵션 테스트 (WAMIT 없이 실행)."""

import os
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.physics.wamit_handler import (
    DEFAULT_WAVE_ANGLE,
    check_wave_angle,
    wall_enabled,
    wamit_beta,
    write_wamit_inputs,
)
from src.problems import get_joint_config
from src.utils.config_parser import parse_wec_cfg

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_config(**extra):
    config = {"opt_mode": 2, "ncpu": 1, "ram": 1, "fixed_radius": 1.5, "fixed_draft": 2.5, "depth": 13.0}
    config.update(extra)
    return config


class TestCheckWaveAngle(unittest.TestCase):
    def test_default_is_head_on(self):
        self.assertEqual(DEFAULT_WAVE_ANGLE, 0.0)

    def test_valid_values_with_wall(self):
        for value in (0, 0.0, 30, -45.5, 89.9, -89.9):
            self.assertEqual(check_wave_angle(value), float(value))

    def test_out_of_range(self):
        for bad in (90, -90, 120, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                check_wave_angle(bad)

    def test_open_sea_layout_accepts_only_zero(self):
        self.assertEqual(check_wave_angle(0, wall=False, opt_mode=3), 0.0)
        with self.assertRaises(ValueError):
            check_wave_angle(30, wall=False, opt_mode=3)

    def test_shape_mode_ignores_the_angle(self):
        self.assertEqual(check_wave_angle(30, wall=False, opt_mode=1), 30.0)


class TestWamitBeta(unittest.TestCase):
    def test_wall_uses_minus_angle(self):
        """벽이 있으면 BETA = -WaveAngle (반사를 포함하면 진행 방향 180 + WaveAngle과 같은 파동장)."""
        self.assertEqual(wamit_beta(base_config(wave_angle=30.0)), -30.0)
        self.assertEqual(wamit_beta(base_config(wave_angle=-20.0)), 20.0)

    def test_zero_is_not_negative_zero(self):
        beta = wamit_beta(base_config(wave_angle=0.0))
        self.assertEqual(f"{beta:g}", "0")

    def test_missing_angle_is_zero(self):
        self.assertEqual(wamit_beta(base_config()), 0.0)

    def test_shape_mode_writes_zero(self):
        self.assertEqual(wamit_beta(base_config(opt_mode=1, wave_angle=30.0)), 0.0)

    def test_open_sea_layout_rejects_angle(self):
        with self.assertRaises(ValueError):
            wamit_beta(base_config(vertical_wall=0, wave_angle=30.0))

    def test_wall_enabled(self):
        self.assertTrue(wall_enabled({"opt_mode": 3}))
        self.assertFalse(wall_enabled({"opt_mode": 1, "vertical_wall": 1}))
        self.assertFalse(wall_enabled({"opt_mode": 2, "vertical_wall": 0}))


class TestPotFile(unittest.TestCase):
    def _beta_line(self, **extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_wamit_inputs(None, base_config(**extra), tmp.name, positions=[(8.0, 0.0), (8.0, 6.0)])
        with open(os.path.join(tmp.name, "wec.pot")) as f:
            lines = f.read().splitlines()
        return lines[next(i for i, line in enumerate(lines) if line.endswith(" NBETA")) + 1]

    def test_default_pot_is_unchanged(self):
        self.assertEqual(self._beta_line(), f"{'0':<20} BETA")

    def test_angle_is_written_with_minus_sign(self):
        self.assertEqual(self._beta_line(wave_angle=30.0), f"{'-30':<20} BETA")
        self.assertEqual(self._beta_line(wave_angle=-12.5), f"{'12.5':<20} BETA")


class TestConfigFile(unittest.TestCase):
    def test_default_config_has_zero_angle(self):
        cfg = parse_wec_cfg(os.path.join(PROJECT_ROOT, "config.cfg"))
        self.assertEqual(float(cfg["WEC Parameters"]["WaveAngle"]), 0.0)

    def test_problem_config_carries_angle(self):
        constraints = {
            "StepSize": 0.1,
            "RadiusMin": 0.5,
            "RadiusMax": 2.5,
            "DraftMin": 0.5,
            "DraftMax": 5.0,
            "WEC1_XMin": 3.0,
            "WEC1_XMax": 25.0,
        }
        env = {"SiteName": "Test", "Hs": 1.0, "Tp": 6.0, "Gamma": 3.3, "Depth": 13.0}
        wamit = {"NCPU": 1, "RAMGBMAX": 1, "WaveAngle": 15.0}
        params = {"MinSpacing": 4, "FixedRadius": 2.5, "FixedDraft": 5.0}
        config = get_joint_config(constraints, params, 1, env, wamit, 1)
        self.assertEqual(config["wave_angle"], 15.0)


if __name__ == "__main__":
    unittest.main()
