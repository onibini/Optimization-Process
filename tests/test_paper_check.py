"""scripts/experiments/paper_check.py 테스트: 논문 Table 4 설계의 벡터 변환과 결과 표 (WAMIT 없이 실행)."""

import contextlib
import csv
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from src.physics.power_calc import calculate_power
from src.utils import check_min_distance, decode_symmetric_positions
from src.utils.config_parser import parse_wec_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "paper_check", os.path.join(ROOT, "scripts", "experiments", "paper_check.py")
)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)
CFG = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))


def synthetic_rao(scale=1.0):
    omegas = np.round(np.arange(0.5, 3.0001, 0.05), 6)
    peak = np.exp(-(((omegas - 1.2) / 0.3) ** 2))
    return [
        {"omega": float(w), "rao_abs": scale * np.array([p, 0.8 * p, 0.6 * p, 0.8 * p, p]), "b_pto": np.full(5, 1e5)}
        for w, p in zip(omegas, peak, strict=True)
    ]


class TestPaperDesigns(unittest.TestCase):
    def test_vector_gives_the_five_positions_of_the_paper(self):
        for (site, method), design in check.PAPER_DESIGNS.items():
            x1, y1, x2, y2, x3 = design[:5]
            expected = sorted([(x1, y1), (x1, -y1), (x2, y2), (x2, -y2), (x3, 0.0)])
            vector = check.paper_vector(design)
            got = sorted(decode_symmetric_positions(vector[2:], 5))
            self.assertEqual(got, expected, (site, method))
            self.assertEqual(vector[:2], [design[5], design[6]])

    def test_designs_are_inside_the_search_space_and_the_spacing_rule(self):
        config = check.build_config(CFG, "Buan")
        lower, upper = config["bounds"]
        for key, design in check.PAPER_DESIGNS.items():
            vector = check.paper_vector(design)
            for value, lo, hi in zip(vector, lower, upper, strict=True):
                self.assertTrue(lo <= value <= hi, (key, value, lo, hi))
            positions = decode_symmetric_positions(vector[2:], 5)
            self.assertEqual(check_min_distance(positions, vector[0], config["min_spacing"]), 0.0, key)

    def test_environment_and_mesh_reach_the_problem_config(self):
        base = check.build_config(CFG, "Yeongilmanhang")
        self.assertEqual((base["depth"], base["mesh_panels"], base["freq_grid"]), (13.0, 120, 0))
        other = check.build_config(CFG, "Yeongilmanhang", mesh_panels=200)
        self.assertEqual((other["depth"], other["mesh_panels"]), (13.0, 200))


class TestPower(unittest.TestCase):
    def test_default_combination_equals_calculate_power(self):
        config = check.build_config(CFG, "Buan")
        rao = synthetic_rao()
        total, individual = calculate_power(rao, config)
        got = check.powers(rao, config, config["wave_spec"], "simpson")
        np.testing.assert_allclose(got, individual, rtol=1e-12)
        self.assertAlmostEqual(sum(got), total, places=6)

    def test_integrations_agree_for_smooth_data_and_spectra_differ(self):
        config = check.build_config(CFG, "Buan")
        rao = synthetic_rao()
        simpson, trapz, rect = (sum(check.powers(rao, config, 2, how)) for how in check.INTEGRATIONS)
        self.assertAlmostEqual(trapz / simpson, 1.0, delta=0.01)
        self.assertAlmostEqual(rect / trapz, 1.0, delta=0.01)  # the spectrum is ~0 at both ends
        self.assertNotAlmostEqual(sum(check.powers(rao, config, 1, "simpson")) / simpson, 1.0, places=3)


class TestRun(unittest.TestCase):
    def test_table_with_a_fake_wamit(self):
        def fake(vector, config, workspace_dir="workspace"):
            return {"diffraction": synthetic_rao(), "haskind": synthetic_rao(1.1)}

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(check, "run_hydrodynamics", fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            rows = check.main(["--out", tmp, "--meshes", "120", "--sites", "Buan", "Yeongilmanhang"])
            with open(os.path.join(tmp, "paper_check.csv"), encoding="utf-8") as f:
                table = list(csv.DictReader(f))
        # 12 combinations per run; runs: 2 Buan designs + 2 Yeongilmanhang designs
        self.assertEqual(len(rows), 12 * 4)
        self.assertEqual(len(table), len(rows))
        depths = {r["depth"] for r in table if r["site"] == "Yeongilmanhang"}
        self.assertEqual(depths, {"13.0"})
        first = table[0]
        self.assertEqual((first["excitation"], first["spec"], first["integ"]), ("diffraction", "goda", "simpson"))
        self.assertAlmostEqual(float(first["diff_pct"]), (float(first["power_kw"]) / 47.52 - 1) * 100, places=2)

    def test_reference_comparison(self):
        def fake(vector, config, workspace_dir="workspace"):
            return {"diffraction": synthetic_rao(), "haskind": synthetic_rao(1.1)}

        args = ["--meshes", "120", "--sites", "Buan"]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(check, "run_hydrodynamics", fake):
            with contextlib.redirect_stdout(io.StringIO()):
                check.main(["--out", tmp, *args])
            reference = os.path.join(tmp, "paper_check.csv")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                check.main(["--out", os.path.join(tmp, "again"), *args, "--reference", reference])
            self.assertIn("24 combinations compared, 0 differ", out.getvalue())

            def changed(vector, config, workspace_dir="workspace"):
                return {"diffraction": synthetic_rao(1.01), "haskind": synthetic_rao(1.1)}  # +2% power

            with (
                mock.patch.object(check, "run_hydrodynamics", changed),
                contextlib.redirect_stdout(io.StringIO()) as out,
                self.assertRaises(SystemExit) as raised,
            ):
                check.main(["--out", os.path.join(tmp, "changed"), *args, "--reference", reference])
            self.assertEqual(raised.exception.code, 1)
            self.assertIn("differ by more than 0.2%", out.getvalue())

    def test_dry_run_does_not_run_wamit(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(check, "run_hydrodynamics") as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            check.main(["--out", tmp, "--dry-run"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
