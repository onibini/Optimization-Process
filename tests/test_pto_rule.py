"""PTO 감쇠 규칙과 시드 반복 스크립트 테스트 (WAMIT 없이 실행)."""

import json
import os
import sys
import tempfile
import unittest
from typing import ClassVar

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "experiments"))
try:
    from paper_seed_runs import find_run, random_seeds, run_all, stage_settings
except ImportError:  # 연구용 스크립트(scripts/experiments)는 공개 저장소에 없으므로, 없으면 해당 시험만 건너뜀
    find_run = random_seeds = run_all = stage_settings = None

from src.physics.hydro import HydroData  # noqa: E402
from src.physics.rao_calc import (  # noqa: E402
    PTO_NATURAL_FREQUENCY,
    PTO_RAO_PEAK,
    check_pto_rule,
    natural_frequency,
    rao_from_hydro,
)
from src.utils.eval_db import db_name, fingerprint  # noqa: E402

OMEGAS = 0.5 + 0.1 * np.arange(21)


def single_wec(mass=3000.0, stiffness=12000.0, added=1000.0):
    n = len(OMEGAS)
    return HydroData(
        omegas=OMEGAS.copy(),
        added_mass=np.full((n, 1, 1), added),
        damping=(100.0 + 1000.0 * OMEGAS).reshape(n, 1, 1),
        excitation=np.full((n, 1), 5000.0 + 0j),
        mass=np.array([[mass]]),
        stiffness=np.array([[stiffness]]),
    )


class TestNaturalFrequency(unittest.TestCase):
    def test_constant_added_mass_gives_the_closed_form(self):
        hydro = single_wec()
        got = natural_frequency(hydro.omegas, hydro.added_mass[:, 0, 0], 3000.0, 12000.0)
        self.assertAlmostEqual(got, np.sqrt(12000.0 / 4000.0), places=9)

    def test_frequency_dependent_added_mass_satisfies_the_equation(self):
        added = 2000.0 - 300.0 * OMEGAS
        got = natural_frequency(OMEGAS, added, 3000.0, 12000.0)
        self.assertAlmostEqual(got**2 * (3000.0 + np.interp(got, OMEGAS, added)), 12000.0, places=6)

    def test_no_root_on_the_grid_uses_the_nearest_end(self):
        constant = np.full(len(OMEGAS), 1000.0)
        self.assertEqual(natural_frequency(OMEGAS, constant, 100.0, 1e9), OMEGAS[-1])
        self.assertEqual(natural_frequency(OMEGAS, constant, 1e6, 1.0), OMEGAS[0])


class TestPtoRule(unittest.TestCase):
    def test_natural_frequency_rule_interpolates_the_damping(self):
        result = rao_from_hydro(single_wec(), PTO_NATURAL_FREQUENCY)
        omega_n = np.sqrt(3.0)
        self.assertAlmostEqual(result[0]["b_pto"][0], 100.0 + 1000.0 * omega_n, places=6)

    def test_natural_frequency_is_continuous_where_the_peak_rule_jumps(self):
        # 봉우리 두 개의 높이가 바뀌는 두 경우: 예전 규칙은 PTO 감쇠가 크게 바뀌고, 새 규칙은 그대로입니다.
        def two_peaks(left):
            hydro = single_wec()
            force = np.full(len(OMEGAS), 1.0 + 0j)
            force[np.argmin(np.abs(OMEGAS - 1.0))] = left
            force[np.argmin(np.abs(OMEGAS - 2.2))] = 1e6
            hydro.excitation[:, 0] = force
            return hydro

        low, high = two_peaks(1e5), two_peaks(1e9)
        self.assertNotAlmostEqual(
            rao_from_hydro(low, PTO_RAO_PEAK)[0]["b_pto"][0], rao_from_hydro(high, PTO_RAO_PEAK)[0]["b_pto"][0]
        )
        self.assertEqual(
            rao_from_hydro(low, PTO_NATURAL_FREQUENCY)[0]["b_pto"][0],
            rao_from_hydro(high, PTO_NATURAL_FREQUENCY)[0]["b_pto"][0],
        )

    def test_invalid_rule(self):
        self.assertEqual(check_pto_rule(2), 2)
        for bad in (0, 3, True):
            with self.assertRaises(ValueError):
                check_pto_rule(bad)


class TestFingerprint(unittest.TestCase):
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

    def test_old_records_keep_their_database_name(self):
        old = db_name(fingerprint(self.CONFIG))
        self.assertEqual(old, "Buan_mode3_n5_f10292d761")
        self.assertEqual(db_name(fingerprint(self.CONFIG | {"pto_rule": PTO_RAO_PEAK})), old)

    def test_new_rule_has_its_own_database(self):
        old = db_name(fingerprint(self.CONFIG))
        self.assertNotEqual(db_name(fingerprint(self.CONFIG | {"pto_rule": PTO_NATURAL_FREQUENCY})), old)


@unittest.skipIf(run_all is None, "research scripts are not in this copy")
class TestSeedRuns(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = os.path.join(self._tmp.name, "logs")
        self.calls = []
        self.config = os.path.join(self._tmp.name, "config.cfg")
        with open(self.config, "w", encoding="utf-8") as f:
            keys = ("OptMode", "NumWECs", "PopSize", "MaxIter", "Seed", "SiteID", "FixedRadius", "FixedDraft", "Depth")
            for key in keys:
                f.write(f"0   {key}   - text\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _runner(self, path):
        values = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                value, key = line.split()[:2]
                values[key] = value
        self.calls.append(values)
        os.makedirs(self.logs, exist_ok=True)
        stem = os.path.join(self.logs, f"run{len(self.calls)}")
        mode = int(values["OptMode"])
        best = [2.5, 3.8] if mode == 1 else [2.5, 3.8, 3, 3, 13.9, 3, 30]
        if mode == 2:
            best = [3, 3, 13.9, 3, 30]
        with open(stem + "_summary.json", "w", encoding="utf-8") as f:
            json.dump({"best_fitness": 1000.0 * mode, "best_vector": best, "physics_evals": 5}, f)
        config = {"site_name": "Buan", "seed": int(values["Seed"]), "opt_mode": mode}
        if mode == 2:
            config |= {"fixed_radius": float(values["FixedRadius"]), "fixed_draft": float(values["FixedDraft"])}
        with open(stem + "_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f)

    def _run(self):
        return run_all([1], [1, 2], self.config, self.logs, runner=self._runner, after_run=lambda _: None)

    def test_three_stages_per_seed_and_geometry_is_passed_on(self):
        rows, failed = self._run()
        self.assertEqual(failed, [])
        self.assertEqual([r["method"] for r in rows[:3]], ["geometry", "layout", "simultaneous"])
        self.assertEqual(len(self.calls), 6)
        layout = self.calls[1]
        self.assertEqual((layout["FixedRadius"], layout["FixedDraft"]), ("2.5", "3.8"))
        self.assertEqual((layout["PopSize"], layout["MaxIter"], layout["NumWECs"]), ("100", "300", "5"))
        self.assertEqual((self.calls[0]["PopSize"], self.calls[0]["MaxIter"]), ("20", "100"))
        self.assertTrue(os.path.exists(os.path.join(self.logs, "paper_seed_runs.csv")))

    def test_finished_runs_are_skipped_when_submitted_again(self):
        self._run()
        count = len(self.calls)
        rows, _ = self._run()
        self.assertEqual(len(self.calls), count)
        self.assertEqual(len(rows), 6)

    def test_a_failing_seed_does_not_stop_the_others(self):
        def runner(path):
            if "seed1" in path:
                raise RuntimeError("boom")
            self._runner(path)

        import contextlib
        import io

        with contextlib.redirect_stderr(io.StringIO()):
            _, failed = run_all([1], [1, 2], self.config, self.logs, runner=runner, after_run=lambda _: None)
        self.assertEqual(failed, [(1, 1)])
        self.assertIsNotNone(find_run(self.logs, "Buan", 2, 3))

    def test_methods_and_depth(self):
        rows, failed = run_all(
            [1], [1], self.config, self.logs, runner=self._runner, after_run=lambda _: None,
            methods=["simultaneous"], depths={1: 33.0},
        )  # fmt: skip
        self.assertEqual(failed, [])
        self.assertEqual([r["method"] for r in rows], ["simultaneous"])
        self.assertEqual(self.calls[0]["Depth"], "33.0")
        run_all([1], [2], self.config, self.logs, runner=self._runner, after_run=lambda _: None, methods=["sequential"])
        self.assertEqual([c["OptMode"] for c in self.calls[1:]], ["1", "2"])
        self.assertEqual(self.calls[1]["Depth"], "0")  # 지정하지 않은 해역은 그대로

    def test_random_seeds_are_kept_for_a_resubmitted_job(self):
        seeds = random_seeds(3, self.logs)
        self.assertEqual(len(set(seeds)), 3)
        self.assertTrue(all(1 <= s < 2**31 for s in seeds))
        self.assertEqual(random_seeds(3, self.logs), seeds)

    def test_settings(self):
        self.assertEqual(stage_settings("simultaneous", 2, 7)["OptMode"], 3)
        self.assertNotIn("Depth", stage_settings("simultaneous", 2, 7))
        self.assertEqual(stage_settings("geometry", 3, 7, depth=33.0)["Depth"], 33.0)
        with self.assertRaises(ValueError):
            stage_settings("other", 2, 7)


if __name__ == "__main__":
    unittest.main()
