"""적응형 주파수 격자 옵션(FreqGrid) 테스트 (WAMIT 없이 실행)."""

import importlib.util
import itertools
import os
import sys
import tempfile
import unittest

from src.physics.rao_calc import calculate_rao_matrix
from src.physics.wamit_handler import (
    OMEGA_MIN,
    OMEGA_STEP,
    adaptive_omegas,
    check_freq_grid,
    heave_omega0,
    omega_grid,
    write_wamit_inputs,
)
from src.utils.config_parser import parse_wec_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "freq_grid_study", os.path.join(ROOT, "scripts", "experiments", "freq_grid_study.py")
)
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)

DESIGNS = [(2.5, 5.0), (1.5, 2.5), (0.5, 0.5), (0.5, 2.0), (1.0, 1.0), (3.0, 8.0)]


def read_lines(workspace, name):
    with open(os.path.join(workspace, name)) as f:
        return f.read().splitlines()


class TestAdaptiveOmegas(unittest.TestCase):
    def test_matches_the_validated_candidate_of_the_study(self):
        for radius, draft in DESIGNS:
            for omax in (3.0, 2.45):
                expected = study.adaptive_grid(radius, draft, omax, 0.85, 1.1, fine_step=study.REF_STEP, tail_ratio=1.5)
                self.assertEqual(adaptive_omegas(radius, draft, omax), expected, (radius, draft, omax))

    def test_heave_frequency_matches_the_study(self):
        for radius, draft in DESIGNS:
            self.assertAlmostEqual(heave_omega0(radius, draft), study.heave_omega0(radius, draft))

    def test_points_are_sorted_unique_and_inside_the_range(self):
        for radius, draft in DESIGNS:
            grid = adaptive_omegas(radius, draft)
            self.assertEqual(grid, sorted(set(grid)))
            self.assertGreaterEqual(grid[0], OMEGA_MIN)
            self.assertLessEqual(grid[-1], 3.0 + 1e-9)

    def test_resonance_window_is_fine_and_the_rest_keeps_the_coarse_grid(self):
        grid = adaptive_omegas(2.5, 5.0)
        w0 = heave_omega0(2.5, 5.0)
        window = [w for w in grid if 0.86 * w0 <= w <= 1.09 * w0]
        steps = {round(b - a, 6) for a, b in itertools.pairwise(window)}
        self.assertEqual(steps, {OMEGA_STEP / 8})
        self.assertIn(0.5, grid)
        self.assertEqual(round(grid[1] - grid[0], 6), OMEGA_STEP)

    def test_small_bodies_resonating_above_the_limit_fall_back_to_a_thinned_uniform_grid(self):
        grid = adaptive_omegas(0.5, 0.5, 2.0)  # 0.85 w0 = 2.9 > 2.0: no fine window
        self.assertEqual(grid, [round(OMEGA_MIN + k * OMEGA_STEP, 6) for k in range(omega_grid(2.0)[0])])

    def test_invalid_upper_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            adaptive_omegas(1.0, 1.0, 0.55)


class TestFreqGridOption(unittest.TestCase):
    def test_values(self):
        self.assertEqual(check_freq_grid(0), 0)
        self.assertEqual(check_freq_grid(1), 1)
        for bad in (2, -1, 0.5, "1", True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                check_freq_grid(bad)

    def _write(self, **extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = {"opt_mode": 2, "ncpu": 1, "ram": 1, "fixed_radius": 1.5, "fixed_draft": 2.5, "depth": 13.0}
        config.update(extra)
        write_wamit_inputs(None, config, tmp.name, positions=[(8.0, 0.0)])
        return tmp.name

    def test_default_and_off_write_the_uniform_grid(self):
        for extra in ({}, {"freq_grid": 0}, {"freq_grid": None}):
            pot = read_lines(self._write(**extra), "wec.pot")
            self.assertTrue(any(line.startswith("-51") and "NPER" in line for line in pot), extra)
            self.assertTrue(any(line.startswith("0.5 0.05") for line in pot), extra)

    def test_adaptive_writes_an_explicit_frequency_list(self):
        pot = read_lines(self._write(freq_grid=1), "wec.pot")
        omegas = adaptive_omegas(1.5, 2.5)
        start = next(i for i, line in enumerate(pot) if line.rstrip().endswith("NPER"))
        self.assertEqual(int(pot[start].split()[0]), len(omegas))  # positive: a list, not start/step
        self.assertEqual([float(x) for x in pot[start + 1 : start + 1 + len(omegas)]], omegas)
        self.assertTrue(pot[start + 1 + len(omegas)].rstrip().endswith("NBETA"))

    def test_adaptive_follows_omega_max(self):
        pot = read_lines(self._write(freq_grid=1, omega_max=2.0), "wec.pot")
        start = next(i for i, line in enumerate(pot) if line.rstrip().endswith("NPER"))
        self.assertEqual(int(pot[start].split()[0]), len(adaptive_omegas(1.5, 2.5, 2.0)))
        self.assertLessEqual(float(pot[start + int(pot[start].split()[0])]), 2.0)

    def test_other_inputs_do_not_change(self):
        a, b = self._write(), self._write(freq_grid=1)
        for name in ("wec.cfg", "wec.frc", "wec.gdf", "fnames.wam"):
            self.assertEqual(read_lines(a, name), read_lines(b, name), name)

    def test_invalid_value_is_rejected(self):
        with self.assertRaises(ValueError):
            self._write(freq_grid=2)

    def test_project_config_default_is_off(self):
        wamit = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))["WAMIT Settings"]
        self.assertEqual(check_freq_grid(int(wamit["FreqGrid"])), 0)


class TestNonUniformGridIsReadBack(unittest.TestCase):
    def test_rao_reader_sorts_a_non_uniform_frequency_list(self):
        # 합성 출력(연구 도구의 가짜 WAMIT 헬퍼)으로 비균일 목록을 읽을 수 있는지 확인
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        from test_freq_grid_study import write_two_wec_workspace

        omegas = adaptive_omegas(1.5, 2.5)[:12]
        with tempfile.TemporaryDirectory() as tmp:
            write_two_wec_workspace(tmp, omegas)
            result = calculate_rao_matrix(tmp, 2)
        self.assertEqual([r["omega"] for r in result], omegas)


if __name__ == "__main__":
    unittest.main()
