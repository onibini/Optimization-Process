"""WAMIT 솔버(ISOLVE)와 주파수 상한(OmegaMax) 옵션 테스트 (WAMIT 없이 실행)."""

import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from typing import ClassVar
from unittest import mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.physics.power_calc import calculate_power
from src.physics.wamit_handler import (
    DEFAULT_OMEGA_MAX,
    DEFAULT_SOLVER,
    MAXITT,
    check_solver,
    find_unconverged,
    omega_grid,
    run_wamit,
    write_wamit_inputs,
)
from src.utils.config_parser import parse_wec_cfg

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_lines(workspace, name):
    with open(os.path.join(workspace, name)) as f:
        return f.read().splitlines()


class TestOmegaGrid(unittest.TestCase):
    def test_default_is_the_original_grid(self):
        self.assertEqual(omega_grid(), (51, 3.0))
        self.assertEqual(omega_grid(DEFAULT_OMEGA_MAX), (51, 3.0))

    def test_upper_limit_sets_number_of_points(self):
        self.assertEqual(omega_grid(2.45), (40, 2.45))
        self.assertEqual(omega_grid(2.0), (31, 2.0))
        self.assertEqual(omega_grid(0.6), (3, 0.6))

    def test_limit_between_grid_points_rounds_down(self):
        n, top = omega_grid(2.47)
        self.assertEqual(n, 40)
        self.assertAlmostEqual(top, 2.45)

    def test_invalid_limits(self):
        for bad in (0.55, 0.5, 0.0, -1.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError, msg=str(bad)):
                omega_grid(bad)


class TestSolver(unittest.TestCase):
    def test_valid_values(self):
        for value in (0, 1, 2, 8):
            self.assertEqual(check_solver(value), value)

    def test_invalid_values(self):
        for bad in (-1, 1.5, "0", True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                check_solver(bad)

    def test_default_is_iterative(self):
        self.assertEqual(DEFAULT_SOLVER, 0)


class TestInputsFollowConfig(unittest.TestCase):
    def _config(self, **extra):
        config = {"opt_mode": 2, "ncpu": 1, "ram": 1, "fixed_radius": 1.5, "fixed_draft": 2.5, "depth": 13.0}
        config.update(extra)
        return config

    def _write(self, **extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_wamit_inputs(None, self._config(**extra), tmp.name, positions=[(8.0, 0.0)])
        return tmp.name

    def test_defaults_use_iterative_solver_and_full_grid(self):
        ws = self._write()
        cfg = read_lines(ws, "wec.cfg")
        self.assertIn("ISOLVE=0", cfg)
        self.assertIn(f"MAXITT={MAXITT}", cfg)
        pot = read_lines(ws, "wec.pot")
        self.assertTrue(any(line.startswith("-51") and "NPER" in line for line in pot))
        self.assertTrue(any(line.startswith("0.5 0.05") and "PER" in line for line in pot))

    def test_solver_zero_is_not_replaced_by_default(self):
        self.assertIn("ISOLVE=0", read_lines(self._write(solver=0), "wec.cfg"))

    def test_direct_and_block_solver(self):
        self.assertIn("ISOLVE=1", read_lines(self._write(solver=1), "wec.cfg"))
        self.assertIn("ISOLVE=4", read_lines(self._write(solver=4), "wec.cfg"))

    def test_omega_max_changes_number_of_periods(self):
        pot = read_lines(self._write(omega_max=2.45), "wec.pot")
        self.assertTrue(any(line.startswith("-40") and "NPER" in line for line in pot))
        self.assertTrue(any(line.startswith("0.5 0.05") and "PER" in line for line in pot))

    def test_invalid_options_are_rejected(self):
        with self.assertRaises(ValueError):
            self._write(solver=-1)
        with self.assertRaises(ValueError):
            self._write(omega_max=0.55)

    def test_project_config_options_parse(self):
        wamit = parse_wec_cfg(os.path.join(PROJECT_ROOT, "config.cfg"))["WAMIT Settings"]
        self.assertEqual(check_solver(int(wamit["Solver"])), 0)
        self.assertEqual(omega_grid(float(wamit["OmegaMax"])), (51, 3.0))


OUT_TEMPLATE = """ POTEN run date and starting time:        21-Oct-2026  --  20:08:11
  Frequency     Time           RAD      DIFF  (max iterations)
    0.5000    20:08:12           9       9
    0.5500    20:08:12          12      {diff}
    0.6000    20:08:13         {rad}      10

 Gravity:     9.80665                Length scale:        1.00000
"""


class TestConvergenceCheck(unittest.TestCase):
    def _workspace(self, rad=10, diff=11, maxitt=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "wec.out"), "w") as f:
            f.write(OUT_TEMPLATE.format(rad=rad, diff=diff))
        if maxitt is not None:
            with open(os.path.join(tmp.name, "wec.cfg"), "w") as f:
                f.write(f"WEC\nISOLVE=0\nMAXITT={maxitt}\n")
        return tmp.name

    def test_converged_run_reports_nothing(self):
        self.assertEqual(find_unconverged(self._workspace()), [])

    def test_iteration_limit_is_detected_in_rad_and_diff(self):
        self.assertEqual(find_unconverged(self._workspace(rad=MAXITT, diff=5)), [0.6])
        self.assertEqual(find_unconverged(self._workspace(rad=5, diff=MAXITT)), [0.55])

    def test_limit_is_read_from_wec_cfg(self):
        self.assertEqual(find_unconverged(self._workspace(maxitt=12)), [0.55])

    def test_missing_output_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(find_unconverged(tmp), [])

    def test_run_wamit_warns_on_unconverged_frequencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "WAMIT.exe")
            open(exe, "w").close()

            def fake_run(cmd, cwd=None, **kwargs):
                with open(os.path.join(cwd, "wec.out"), "w") as f:
                    f.write(OUT_TEMPLATE.format(rad=MAXITT, diff=10))
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with (
                mock.patch("src.physics.wamit_handler.subprocess.run", side_effect=fake_run),
                warnings.catch_warnings(record=True) as caught,
            ):
                warnings.simplefilter("always")
                run_wamit(tmp, exe)
        self.assertTrue(any("reached MAXITT" in str(w.message) for w in caught))

    def test_run_wamit_silent_when_converged(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "WAMIT.exe")
            open(exe, "w").close()

            def fake_run(cmd, cwd=None, **kwargs):
                with open(os.path.join(cwd, "wec.out"), "w") as f:
                    f.write(OUT_TEMPLATE.format(rad=10, diff=10))
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with (
                mock.patch("src.physics.wamit_handler.subprocess.run", side_effect=fake_run),
                warnings.catch_warnings(record=True) as caught,
            ):
                warnings.simplefilter("always")
                run_wamit(tmp, exe)
        self.assertFalse(caught)


class TestTruncationWarning(unittest.TestCase):
    CONFIG: ClassVar[dict] = {"hs": 0.92, "tp": 6.66, "gamma": 1.4, "wave_spec": 2}

    def _results(self, rao_of_omega):
        omegas = [0.5 + 0.05 * i for i in range(51)]
        return [{"omega": w, "rao_abs": [rao_of_omega(w)], "b_pto": [1000.0]} for w in omegas]

    def test_warns_when_response_is_large_at_the_top_of_the_grid(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            calculate_power(self._results(lambda w: w**6), self.CONFIG)
        self.assertTrue(any("OmegaMax" in str(w.message) for w in caught))

    def test_silent_when_response_dies_out(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            calculate_power(self._results(lambda w: 5.0 * (w < 1.5)), self.CONFIG)
        self.assertFalse(caught)


if __name__ == "__main__":
    unittest.main()
