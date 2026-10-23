"""scripts/experiments/freq_grid_study.py 의 주파수 격자 후보 함수 테스트 (WAMIT 없이 실행)."""

import contextlib
import csv
import importlib.util
import io
import itertools
import math
import os
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "freq_grid_study", os.path.join(ROOT, "scripts", "experiments", "freq_grid_study.py")
)
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


def on_lattice(w):
    k = w / study.LATTICE
    return abs(k - round(k)) < 1e-6


class TestHeaveFrequency(unittest.TestCase):
    def test_hydrostatic_values(self):
        self.assertAlmostEqual(study.heave_omega0(2.5, 5.0), 1.2128, places=3)
        self.assertAlmostEqual(study.heave_omega0(1.5, 2.5), 1.6739, places=3)
        self.assertAlmostEqual(study.heave_omega0(0.5, 0.5), 3.4304, places=3)

    def test_deeper_and_larger_bodies_resonate_lower(self):
        self.assertLess(study.heave_omega0(1.5, 4.0), study.heave_omega0(1.5, 1.0))
        self.assertLess(study.heave_omega0(2.5, 2.0), study.heave_omega0(0.5, 2.0))


class TestUniformGrid(unittest.TestCase):
    def test_current_grid(self):
        grid = study.uniform_grid(3.0)
        self.assertEqual(len(grid), 51)
        self.assertEqual((grid[0], grid[-1]), (0.5, 3.0))

    def test_fine_reference_grid(self):
        self.assertEqual(len(study.uniform_grid(3.0, study.LATTICE)), 201)


class TestAdaptiveGrid(unittest.TestCase):
    def test_basic_properties(self):
        grid = study.adaptive_grid(2.5, 5.0, 3.0)
        self.assertEqual(grid, sorted(set(grid)))
        self.assertGreaterEqual(grid[0], 0.5)
        self.assertLessEqual(grid[-1], 3.0)
        self.assertTrue(all(on_lattice(w) for w in grid))

    def test_coarse_points_outside_window_are_kept(self):
        grid = set(study.adaptive_grid(2.5, 5.0, 3.0))
        for w in study.uniform_grid(3.0):
            if w <= 0.8 or w >= 1.25:
                self.assertIn(round(w, 6), grid)

    def test_window_is_dense_around_the_resonance(self):
        grid = study.adaptive_grid(2.5, 5.0, 3.0)
        window = [w for w in grid if 0.85 <= w <= 1.2125]
        gaps = {round(b - a, 4) for a, b in itertools.pairwise(window)}
        self.assertEqual(gaps, {study.LATTICE})
        self.assertGreater(len(window), 25)

    def test_fine_step_controls_number_of_points(self):
        n_fine = len(study.adaptive_grid(2.5, 5.0, 3.0))
        n_coarse = len(study.adaptive_grid(2.5, 5.0, 3.0, fine_step=2 * study.LATTICE))
        self.assertLess(n_coarse, n_fine)

    def test_tail_thinning_keeps_multiples_of_the_tail_step(self):
        grid = study.adaptive_grid(2.5, 5.0, 3.0, tail_ratio=1.5)
        tail = [w for w in grid if w > 1.85]
        self.assertTrue(tail)
        self.assertTrue(all(abs((w - 0.5) / 0.1 - round((w - 0.5) / 0.1)) < 1e-6 for w in tail))
        self.assertNotIn(1.95, grid)
        self.assertLess(len(grid), len(study.adaptive_grid(2.5, 5.0, 3.0)))

    def test_resonance_above_the_grid_limit_keeps_a_window_at_the_top(self):
        grid = study.adaptive_grid(0.5, 0.5, 3.0)  # omega0 = 3.43 > 3.0
        self.assertIn(2.4125, grid)
        self.assertLessEqual(grid[-1], 3.0)

    def test_without_window_equals_uniform_grid(self):
        grid = study.adaptive_grid(2.5, 5.0, 3.0, lo_ratio=2.5, hi_ratio=3.0)  # window above omega_max
        self.assertEqual(grid, study.uniform_grid(3.0))


class TestAlignToNcpu(unittest.TestCase):
    def setUp(self):
        self.grid = study.uniform_grid(3.0)  # 51 points

    def test_off_and_already_aligned_are_unchanged(self):
        self.assertEqual(study.align_to_ncpu(self.grid, 8, "off", 1.2), self.grid)
        aligned = self.grid[:48]
        self.assertEqual(study.align_to_ncpu(aligned, 8, "up", 1.2), aligned)
        self.assertEqual(study.align_to_ncpu(aligned, 8, "down", 1.2), aligned)

    def test_down_drops_the_highest_frequencies(self):
        result = study.align_to_ncpu(self.grid, 8, "down", 1.2)
        self.assertEqual(len(result), 48)
        self.assertEqual(result, self.grid[:48])

    def test_up_adds_points_and_keeps_all_original_ones(self):
        result = study.align_to_ncpu(self.grid, 8, "up", 1.2)
        self.assertEqual(len(result) % 8, 0)
        self.assertEqual(len(result), 56)
        self.assertTrue(set(self.grid) <= set(result))
        self.assertEqual(result, sorted(set(result)))

    def test_up_prefers_gaps_near_the_focus_frequency(self):
        result = study.align_to_ncpu(self.grid, 8, "up", 1.2)
        added = sorted(set(result) - set(self.grid))
        self.assertTrue(all(0.9 <= w <= 1.6 for w in added), added)

    def test_works_for_any_ncpu(self):
        for ncpu in (1, 2, 4, 6, 8, 12, 16):
            self.assertEqual(len(study.align_to_ncpu(self.grid, ncpu, "up", 1.2)) % ncpu, 0)


class TestCandidateGrids(unittest.TestCase):
    def setUp(self):
        self.grids = study.candidate_grids(2.5, 5.0, 3.0, 8)

    def test_reference_is_first_and_finest(self):
        names = list(self.grids)
        self.assertEqual(names[0], "ref_uniform_0.00625")
        self.assertEqual(len(self.grids[names[0]]), 401)
        self.assertEqual(max(len(g) for g in self.grids.values()), 401)

    def test_uniform_candidates(self):
        sizes = [len(self.grids[k]) for k in ("uniform_0.05", "uniform_0.025", "uniform_0.0125")]
        self.assertEqual(sizes, [51, 101, 201])

    def test_narrower_windows_have_fewer_points(self):
        n07 = len(self.grids["adaptive_0.7_1.0_tail0.1"])
        n08 = len(self.grids["adaptive_0.8_1.0_tail0.1"])
        n085 = len(self.grids["adaptive_0.85_1.0_tail0.1"])
        self.assertGreater(n07, n08)
        self.assertGreater(n08, n085)

    def test_finer_window_step_adds_points(self):
        finer = self.grids["adaptive_0.8_1.0_fine0.00625_tail0.1"]
        self.assertGreater(len(finer), len(self.grids["adaptive_0.8_1.0_tail0.1"]))
        self.assertTrue(all(abs(w / study.REF_STEP - round(w / study.REF_STEP)) < 1e-6 for w in finer))

    def test_aligned_variants_are_multiples_of_ncpu(self):
        for ncpu in (4, 8):
            grids = study.candidate_grids(2.5, 5.0, 3.0, ncpu)
            self.assertEqual(len(grids["adaptive_0.85_1.0_tail0.1_aligned_up"]) % ncpu, 0)
            self.assertEqual(len(grids["adaptive_0.85_1.0_tail0.1_aligned_down"]) % ncpu, 0)

    def test_narrow_window_resolves_the_measured_resonances(self):
        measured = [(2.5, 5.0, 0.928), (1.5, 2.5, 0.919), (0.5, 0.5, 0.907), (0.5, 2.0, 0.957)]  # peak / omega0
        for radius, draft, ratio in measured:
            w0 = study.heave_omega0(radius, draft)
            omax = max(3.0, math.ceil(1.2 * w0 / study.OMEGA_STEP) * study.OMEGA_STEP)
            grid = study.adaptive_grid(radius, draft, omax, 0.85, 1.0)
            peak = ratio * w0
            near = sorted(w for w in grid if abs(w - peak) <= 0.04)
            gaps = {round(b - a, 5) for a, b in itertools.pairwise(near)}
            self.assertTrue(near, (radius, draft))
            self.assertLessEqual(max(gaps), study.LATTICE + 1e-9, (radius, draft))


def case(grid, time_s, err, worst, n_freq=10, layout="A"):
    return {
        "R": 2.5,
        "D": 5.0,
        "layout": layout,
        "grid": grid,
        "n_freq": n_freq,
        "time_s": time_s,
        "err_total_pct": err,
        "worst_wec_err_pct": worst,
    }


class TestVerdicts(unittest.TestCase):
    def verdicts(self):
        rows = [
            case("ref_uniform_0.00625", 50.0, 0.0, 0.0),
            case("uniform_0.05", 8.0, 3.0, 6.0),
            case("uniform_0.0125", 26.0, 0.05, 0.1),
            case("adaptive_fast", 12.0, 0.02, 0.1),
            case("adaptive_slow", 30.0, 0.02, 0.1),
            case("adaptive_inaccurate", 10.0, 0.5, 2.0),
            case("uniform_0.05_aligned_up", 8.0, 0.01, 0.01),
        ]
        return {v["grid"]: v for v in study.evaluate_verdicts(rows)}

    def test_reference_is_not_judged(self):
        self.assertNotIn("ref_uniform_0.00625", self.verdicts())

    def test_time_yardstick_is_the_cheapest_accurate_uniform_grid(self):
        v = self.verdicts()
        self.assertEqual(v["adaptive_fast"]["equal_accuracy_uniform_time_s"], 26.0)
        self.assertAlmostEqual(v["adaptive_fast"]["time_ratio_vs_equal_accuracy_uniform"], 12.0 / 26.0)
        self.assertAlmostEqual(v["adaptive_fast"]["time_ratio_vs_current_uniform_0.05"], 1.5)

    def test_pass_needs_accuracy_and_time(self):
        v = self.verdicts()
        self.assertEqual(v["adaptive_fast"]["verdict"], "PASS")
        self.assertEqual(v["adaptive_slow"]["verdict"], "fail")  # accurate but slower than the accurate uniform grid
        self.assertTrue(v["adaptive_slow"]["accurate"])
        self.assertFalse(v["adaptive_slow"]["time_ok"])
        self.assertEqual(v["adaptive_inaccurate"]["verdict"], "fail")
        self.assertFalse(v["adaptive_inaccurate"]["accurate"])

    def test_accuracy_thresholds(self):
        rows = [
            case("ref_uniform_0.00625", 50.0, 0.0, 0.0),
            case("a", 5.0, 0.1, 0.3),
            case("b", 5.0, -0.1, 0.31),
            case("c", 5.0, 0.11, 0.1),
        ]
        v = {x["grid"]: x["accurate"] for x in study.evaluate_verdicts(rows)}
        self.assertEqual(v, {"a": True, "b": False, "c": False})

    def test_aligned_uniform_grids_do_not_set_the_yardstick(self):
        v = self.verdicts()
        self.assertEqual(v["adaptive_fast"]["equal_accuracy_uniform_time_s"], 26.0)  # not the 8 s aligned grid

    def test_reference_time_is_the_yardstick_when_no_other_uniform_grid_is_accurate(self):
        rows = [
            case("ref_uniform_0.00625", 50.0, 0.0, 0.0),
            case("uniform_0.05", 8.0, 3.0, 6.0),
            case("uniform_0.0125", 26.0, 0.4, 0.9),
            case("adaptive", 20.0, 0.01, 0.05),
        ]
        v = {x["grid"]: x for x in study.evaluate_verdicts(rows)}
        self.assertEqual(v["adaptive"]["equal_accuracy_uniform_time_s"], 50.0)
        self.assertEqual(v["adaptive"]["verdict"], "PASS")

    def test_cases_are_judged_separately_and_summarized(self):
        rows = [
            case("ref_uniform_0.00625", 50.0, 0.0, 0.0, layout="A"),
            case("uniform_0.05", 8.0, 3.0, 6.0, layout="A"),
            case("adaptive", 12.0, 0.01, 0.05, layout="A"),
            case("ref_uniform_0.00625", 50.0, 0.0, 0.0, layout="B"),
            case("uniform_0.05", 8.0, 3.0, 6.0, layout="B"),
            case("adaptive", 60.0, 0.01, 0.05, layout="B"),
        ]
        verdicts = study.evaluate_verdicts(rows)
        self.assertEqual([v["verdict"] for v in verdicts if v["grid"] == "adaptive"], ["PASS", "fail"])
        lines = study.summarize_verdicts(verdicts)
        self.assertEqual(len(lines), 3)  # header, uniform_0.05, adaptive
        self.assertTrue(lines[2].split()[0] == "adaptive" and lines[2].split()[-1] == "(2)")


class TestDiagnostics(unittest.TestCase):
    def write_wec1(self, tmp):
        lines = ["WAMIT Numeric Output -- wec.1"]
        # omega, i, j, A, B (nondimensional); WEC1 = dof 3, WEC2 = dof 9; dof 1 and off-diagonal terms must be ignored
        for w, b1, b2 in ((1.0, 0.10, 0.30), (1.1, 0.20, 0.25), (1.2, 0.15, 0.40)):
            lines.append(f"{w} 3 3 0.5 {b1}")
            lines.append(f"{w} 9 9 0.5 {b2}")
            lines.append(f"{w} 1 1 0.5 9.9")
            lines.append(f"{w} 3 9 0.5 9.9")
        with open(os.path.join(tmp, "wec.1"), "w") as f:
            f.write("\n".join(lines) + "\n")

    def test_radiation_damping_scaling_and_dof_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write_wec1(tmp)
            damping = study.radiation_damping(tmp, num_wecs=2)
        self.assertEqual(sorted(damping[0]), [1.0, 1.1, 1.2])
        self.assertAlmostEqual(damping[0][1.1], 0.20 * 1025.0 * 1.1)
        self.assertAlmostEqual(damping[1][1.2], 0.40 * 1025.0 * 1.2)

    def test_uncontrolled_peaks_recover_the_frequency_behind_b_pto(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write_wec1(tmp)
            damping = study.radiation_damping(tmp, num_wecs=2)
        b_pto = [0.20 * 1025.0 * 1.1, 0.40 * 1025.0 * 1.2]
        self.assertEqual(study.uncontrolled_peaks(damping, b_pto), [1.1, 1.2])

    def test_dump_has_one_row_per_frequency_and_four_columns_per_wec(self):
        omegas = np.array([1.0, 1.1, 1.2])
        spectrum = np.array([0.5, 0.4, 0.3])
        rao = np.arange(6, dtype=float).reshape(3, 2)
        b_pto = np.array([10.0, 20.0])
        damping = [{1.0: 1.0, 1.1: 2.0, 1.2: 3.0}, {1.0: 4.0, 1.1: 5.0, 1.2: 6.0}]
        density = rao**2
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dump.csv")
            study.write_dump(path, omegas, spectrum, rao, b_pto, damping, density)
            with open(path, newline="") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["omega", "S", "B1", "rao1", "bpto1", "density1", "B2", "rao2", "bpto2", "density2"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(float(rows[2][0]), 1.1)
        self.assertEqual(float(rows[2][2]), 2.0)  # B1 at 1.1
        self.assertEqual(float(rows[2][3]), 2.0)  # rao1 at 1.1 (row 1, column 0)
        self.assertEqual(float(rows[2][8]), 20.0)  # bpto2


RHO, G = 1025.0, 9.80665


def write_two_wec_workspace(path, omegas, damping_scale=1.0):
    """Synthetic WAMIT output for two heaving WECs: heave resonance near 0.63 rad/s, B(omega) rising with omega."""
    with open(os.path.join(path, "wec.out"), "w") as f:
        f.write(" Volumes (VOLX,VOLY,VOLZ):   0.0  0.0  2.0\n")
    with open(os.path.join(path, "wec.hst"), "w") as f:
        f.write(" header\n   3   3   0.1\n   9   9   0.1\n")
    with open(os.path.join(path, "wec.1"), "w") as f:
        f.write(" header\n")
        for w in omegas:
            b = damping_scale * (0.05 + 0.2 * w * w)
            f.write(f"{w:.6f} 3 3 0.5 {b:.9f}\n")
            f.write(f"{w:.6f} 9 9 0.5 {1.1 * b:.9f}\n")
            f.write(f"{w:.6f} 3 9 0.05 0.01\n")
            f.write(f"{w:.6f} 9 3 0.05 0.01\n")
            f.write(f"{w:.6f} 1 1 9.9 9.9\n")
    with open(os.path.join(path, "wec.3"), "w") as f:
        f.write(" header\n")
        for w in omegas:
            f.write(f"{w:.6f} 0.0 3 0.0 0.0 {w:.6f} 0.1\n")
            f.write(f"{w:.6f} 0.0 9 0.0 0.0 {0.8 * w:.6f} 0.05\n")


class TestNewCandidates(unittest.TestCase):
    def test_upper_edge_1_1_adds_points_and_includes_the_right_flank(self):
        grids = study.candidate_grids(0.5, 2.0, 3.0, 8)
        w0 = study.heave_omega0(0.5, 2.0)
        n_10 = len(grids["adaptive_0.85_1.0_tail0.1"])
        n_11 = len(grids["adaptive_0.85_1.1_tail0.1"])
        self.assertGreater(n_11, n_10)
        window = [w for w in grids["adaptive_0.85_1.1_tail0.1"] if w > 1.0 * w0]
        self.assertTrue(
            any(w > 1.0 * w0 + 0.05 and abs(w * 80 - round(w * 80)) < 1e-6 for w in window)
        )  # 0.0125 lattice above w0

    def test_finer_window_for_the_1_1_candidate(self):
        grids = study.candidate_grids(2.5, 5.0, 3.0, 8)
        self.assertGreater(len(grids["adaptive_0.85_1.1_fine0.00625_tail0.1"]), len(grids["adaptive_0.85_1.1_tail0.1"]))

    def test_check_grid_is_optional_and_second(self):
        self.assertNotIn("check_uniform_0.003125", study.candidate_grids(0.5, 2.0, 3.0, 8))
        grids = study.candidate_grids(0.5, 2.0, 3.0, 8, include_check=True)
        names = list(grids)
        self.assertEqual(names[:2], ["ref_uniform_0.00625", "check_uniform_0.003125"])
        self.assertEqual(len(grids["check_uniform_0.003125"]), 801)


COARSE_GRID = [round(0.5 + 0.1 * k, 6) for k in range(6)]  # 0.5 ... 1.0


class TestResonanceEstimates(unittest.TestCase):
    def test_peak_node_and_width_come_from_the_stage_1_coefficients(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_two_wec_workspace(tmp, COARSE_GRID)
            estimates = study.resonance_estimates(tmp, 2)
        self.assertEqual(len(estimates), 2)
        for k, e in enumerate(estimates):
            w = e["omega_peak"]
            self.assertIn(round(w, 6), COARSE_GRID)
            self.assertAlmostEqual(w, 0.6)  # synthetic heave resonance near 0.63 rad/s
            b_nondim = (1.0 if k == 0 else 1.1) * (0.05 + 0.2 * w * w)
            # fwhm = 2 B_kk / (M + A_kk) with B_kk = rho w b, M = rho x 2.0 (volume), A_kk = rho x 0.5
            self.assertAlmostEqual(e["fwhm"], 2.0 * w * b_nondim / 2.5, places=9)

    def test_stiffness_and_dof_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_two_wec_workspace(tmp, COARSE_GRID)
            self.assertAlmostEqual(study.read_stiffness(tmp), 0.1 * RHO * G)


class TestDensityFwhm(unittest.TestCase):
    def test_recovers_the_width_of_lorentzian_peaks(self):
        w = np.arange(0.5, 1.5, 0.0025)
        density = np.column_stack([1.0 / (1.0 + ((w - 1.0) / 0.05) ** 2), 3.0 / (1.0 + ((w - 0.9) / 0.1) ** 2)])
        widths = study.density_fwhm(w, density)
        self.assertAlmostEqual(widths[0], 0.1, delta=0.002)
        self.assertAlmostEqual(widths[1], 0.2, delta=0.004)


class TestTwoStageGrid(unittest.TestCase):
    EXISTING = study.uniform_grid(3.0)

    def plan(self, estimates, per_fwhm=8.0, **kwargs):
        return study.two_stage_grid(estimates, self.EXISTING, per_fwhm, 3.0, **kwargs)

    def test_step_follows_the_narrowest_resonance(self):
        _, step, _ = self.plan([{"omega_peak": 1.125, "fwhm": 0.07}])
        self.assertEqual(step, study.REF_STEP)  # 0.07 / 8 = 0.00875 -> largest allowed step not above it
        _, step, _ = self.plan([{"omega_peak": 1.125, "fwhm": 0.03}])
        self.assertEqual(step, study.REF_STEP / 2)
        _, step, _ = self.plan([{"omega_peak": 1.125, "fwhm": 0.5}])
        self.assertEqual(step, study.LATTICE)
        _, step, _ = self.plan([{"omega_peak": 1.0, "fwhm": 0.2}, {"omega_peak": 1.1, "fwhm": 0.03}])
        self.assertEqual(step, study.REF_STEP / 2)
        _, step, _ = self.plan([{"omega_peak": 1.125, "fwhm": 0.0}])
        self.assertEqual(step, study.REF_STEP / 2)

    def test_a_broad_resonance_keeps_a_coarser_step_than_a_narrow_one(self):
        new, finest, _ = self.plan([{"omega_peak": 1.0, "fwhm": 0.2}, {"omega_peak": 2.0, "fwhm": 0.03}])
        self.assertEqual(finest, study.REF_STEP / 2)
        near_broad = [w for w in new if 0.6 < w < 1.4]
        near_narrow = [w for w in new if 1.9 < w < 2.1]
        self.assertTrue(all(abs(w / study.LATTICE - round(w / study.LATTICE)) < 1e-6 for w in near_broad))  # 0.0125
        self.assertTrue(any(abs(w / study.LATTICE - round(w / study.LATTICE)) > 1e-6 for w in near_narrow))  # finer
        self.assertLess(len(near_broad), 3 * len(near_narrow))

    def test_new_frequencies_fill_the_window_without_repeating_stage_1(self):
        new, step, windows = self.plan([{"omega_peak": 1.125, "fwhm": 0.07}])
        self.assertEqual(len(windows), 1)
        lo, hi = windows[0]
        self.assertAlmostEqual(lo, 1.125 - 0.28)
        self.assertAlmostEqual(hi, 1.125 + 0.28)
        self.assertEqual(new, sorted(set(new)))
        self.assertTrue(all(lo - 1e-9 <= w <= hi + 1e-9 for w in new))
        self.assertTrue(all(abs(w / step - round(w / step)) < 1e-6 for w in new))
        self.assertFalse(set(new) & {round(w, 6) for w in self.EXISTING})
        self.assertIn(1.13125, new)
        self.assertEqual(len(new), 77)

    def test_minimum_half_window(self):
        _, _, windows = self.plan([{"omega_peak": 1.5, "fwhm": 0.01}])
        lo, hi = windows[0]
        self.assertAlmostEqual(hi - lo, 0.2)

    def test_windows_merge_when_they_overlap_and_stay_separate_otherwise(self):
        _, _, windows = self.plan([{"omega_peak": 1.0, "fwhm": 0.05}, {"omega_peak": 1.1, "fwhm": 0.05}])
        self.assertEqual(len(windows), 1)
        _, _, windows = self.plan([{"omega_peak": 0.8, "fwhm": 0.05}, {"omega_peak": 2.5, "fwhm": 0.05}])
        self.assertEqual(len(windows), 2)

    def test_windows_are_clipped_to_the_frequency_range(self):
        new, _, windows = self.plan([{"omega_peak": 2.95, "fwhm": 0.05}])
        self.assertLessEqual(windows[0][1], 3.0)
        self.assertLessEqual(max(new), 3.0)
        new, _, windows = self.plan([{"omega_peak": 0.55, "fwhm": 0.05}])
        self.assertGreaterEqual(windows[0][0], study.OMEGA_MIN)
        self.assertGreaterEqual(min(new), study.OMEGA_MIN)

    def test_step_is_made_coarser_when_too_many_frequencies_are_needed(self):
        estimates = [{"omega_peak": 1.125, "fwhm": 0.03}]
        fine, fine_step, _ = self.plan(estimates)
        capped, capped_step, _ = self.plan(estimates, max_new=40)
        self.assertGreater(len(fine), 40)
        self.assertGreater(capped_step, fine_step)
        self.assertTrue(len(capped) <= 40 or capped_step == study.LATTICE)

    def test_nothing_new_when_the_stage_1_grid_already_covers_the_window(self):
        dense = study.uniform_grid(3.0, study.REF_STEP / 2)
        new, _, _ = study.two_stage_grid([{"omega_peak": 1.125, "fwhm": 0.5}], dense, 8.0, 3.0)
        self.assertEqual(new, [])


class TestMergeOutputs(unittest.TestCase):
    def test_two_runs_merge_into_the_result_of_one_run(self):
        from src.physics import calculate_rao_matrix

        stage1 = COARSE_GRID
        stage2 = [0.55, 0.625, 0.65, 0.95]
        with tempfile.TemporaryDirectory() as tmp:
            d1, d2, merged, whole = (os.path.join(tmp, n) for n in ("d1", "d2", "merged", "whole"))
            for d, omegas in ((d1, stage1), (d2, stage2), (whole, sorted(stage1 + stage2))):
                os.makedirs(d)
                write_two_wec_workspace(d, omegas)
            study.merge_wamit_outputs(d1, d2, merged)
            a = calculate_rao_matrix(merged, 2)
            b = calculate_rao_matrix(whole, 2)
            with open(os.path.join(merged, "wec.1")) as f:
                n_lines = len(f.read().splitlines())
            with open(os.path.join(d1, "wec.1")) as f1, open(os.path.join(d2, "wec.1")) as f2:
                expected = len(f1.read().splitlines()) + len(f2.read().splitlines()) - 1
        self.assertEqual(n_lines, expected)
        self.assertEqual([r["omega"] for r in a], [r["omega"] for r in b])
        for x, y in zip(a, b, strict=True):
            np.testing.assert_allclose(x["rao_abs"], y["rao_abs"], rtol=1e-12)
            np.testing.assert_allclose(x["b_pto"], y["b_pto"], rtol=1e-12)


def fake_run_wamit(workdir, exe_path=None):
    """Stand-in for WAMIT: smooth synthetic outputs (heave resonance near 1.2 rad/s) for the frequencies in wec.pot."""
    with open(os.path.join(workdir, "wec.pot")) as f:
        lines = f.read().splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip().endswith("NPER"))
    n_freq = abs(int(lines[start].split()[0]))
    omegas = [float(x) for x in lines[start + 1 : start + 1 + n_freq]]
    n_body = int(next(line.split()[0] for line in lines if line.rstrip().endswith("NBODY")))
    with open(os.path.join(workdir, "wec.out"), "w") as f:
        f.write(" Volumes (VOLX,VOLY,VOLZ):   0.0  0.0  2.0\n")
    with open(os.path.join(workdir, "wec.hst"), "w") as f:
        f.write(" header\n   3   3   0.367\n")
    with open(os.path.join(workdir, "wec.1"), "w") as f1, open(os.path.join(workdir, "wec.3"), "w") as f3:
        f1.write(" header\n")
        f3.write(" header\n")
        for w in omegas:
            b = 0.05 + 0.02 * w * w
            for i in range(n_body):
                dof_i = 3 + 6 * i
                f1.write(f"{w:.6f} {dof_i} {dof_i} 0.5 {b:.9f}\n")
                for j in range(n_body):
                    if j != i:
                        f1.write(f"{w:.6f} {dof_i} {3 + 6 * j} 0.02 0.005\n")
                f3.write(f"{w:.6f} 0.0 {dof_i} 0.0 0.0 {0.1 * w:.9f} 0.01\n")


class TestStudyPlumbing(unittest.TestCase):
    """The ``grids`` study end to end with a fake WAMIT: CSV rows, two-stage bookkeeping, verdict file, clean-up."""

    def test_grids_quick_with_fake_wamit(self):
        import argparse
        from unittest import mock

        with tempfile.TemporaryDirectory() as out:
            args = argparse.Namespace(
                quick=True, dry_run=False, no_dump=False, out=out, panels=60, ncpu=8, study="grids"
            )
            with mock.patch.object(study, "run_wamit", fake_run_wamit), contextlib.redirect_stdout(io.StringIO()):
                study.study_grids(args)
            with open(os.path.join(out, "freq_grid_study_grids.csv"), newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            with open(os.path.join(out, "freq_grid_study_grids_verdict.csv"), newline="", encoding="utf-8") as f:
                verdicts = list(csv.DictReader(f))
            dumps = [name for name in os.listdir(out) if name.startswith("dump_")]
        self.assertEqual(len(rows), 4 * 12 + 1 + 4 * len(study.TWO_STAGE_VARIANTS))  # + check grid + two-stage rows
        self.assertEqual(len(dumps), len(rows))
        for r in rows:
            if r["grid"].startswith("ref_"):
                self.assertEqual(float(r["err_total_pct"]), 0.0)
        for design in {(r["R"], r["D"]) for r in rows}:
            group = {r["grid"]: r for r in rows if (r["R"], r["D"]) == design}
            stage1 = group["uniform_0.05"]
            for name in study.TWO_STAGE_VARIANTS:
                row = group[name]
                self.assertGreater(int(row["n_stage2"]), 0)
                self.assertEqual(int(row["n_freq"]), int(stage1["n_freq"]) + int(row["n_stage2"]))
                self.assertGreaterEqual(float(row["time_s"]), float(stage1["time_s"]))  # stage 1 + stage 2
                self.assertIn(float(row["stage2_step"]), study.FINE_STEPS)
                self.assertTrue(row["fwhm_est_min"])
        self.assertTrue(all(name.startswith("check_") is False for name in (v["grid"] for v in verdicts)))
        self.assertTrue({v["grid"] for v in verdicts} >= set(study.TWO_STAGE_VARIANTS))
        leftovers = [d for d in os.listdir(os.path.join(study.ROOT, "workspace")) if d.startswith("sg_")]
        self.assertEqual(leftovers, [])


class TestPercentErrors(unittest.TestCase):
    def test_errors_and_missing_base(self):
        err, worst = study.percent_errors(101.0, [51.0, 50.0], 100.0, [50.0, 50.0])
        self.assertAlmostEqual(err, 1.0)
        self.assertAlmostEqual(worst, 2.0)
        self.assertTrue(math.isnan(study.percent_errors(1.0, [1.0], 1.0, [])[0]))


if __name__ == "__main__":
    unittest.main()
