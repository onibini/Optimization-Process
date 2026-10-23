"""수력 해석기 분리(HydroData, WAMIT/Capytaine backend)와 수직벽 설정 테스트. Capytaine 테스트는 설치된 경우에만."""

import importlib.util
import math
import os
import sys
import tempfile
import unittest
from typing import ClassVar
from unittest import mock

import numpy as np

from src.physics import mesh_axisymmetric_shape as mesh
from src.physics import solvers
from src.physics.rao_calc import calculate_rao_matrix, rao_from_hydro, read_wamit_hydro
from src.physics.wamit_handler import write_config_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_freq_grid_study import write_two_wec_workspace  # noqa: E402

HAS_CAPYTAINE = importlib.util.find_spec("capytaine") is not None
OMEGAS = [round(0.5 + 0.1 * k, 6) for k in range(8)]


def frozen_rao(hydro):
    """Step 1-3 of the RAO calculation exactly as it was before the solver split (reference)."""
    omegas, n = list(hydro.omegas), hydro.num_wecs
    base = []
    for k, w in enumerate(omegas):
        z = -(w**2) * (hydro.mass + hydro.added_mass[k]) + 1j * w * hydro.damping[k] + hydro.stiffness
        base.append(np.abs(np.linalg.solve(z, hydro.excitation[k])))
    base = np.array(base)
    bpto = np.array([hydro.damping[np.argmax(base[:, j])][j, j] for j in range(n)])
    out = []
    for k, w in enumerate(omegas):
        z = -(w**2) * (hydro.mass + hydro.added_mass[k]) + 1j * w * (hydro.damping[k] + np.diag(bpto)) + hydro.stiffness
        out.append(np.abs(np.linalg.solve(z, hydro.excitation[k])))
    return np.array(out), bpto


class TestHydroSplit(unittest.TestCase):
    def test_reader_and_rao_match_the_previous_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_two_wec_workspace(tmp, OMEGAS)
            hydro = read_wamit_hydro(tmp, 2)
            results = calculate_rao_matrix(tmp, 2)
        self.assertEqual(hydro.added_mass.shape, (len(OMEGAS), 2, 2))
        self.assertEqual(hydro.excitation.shape, (len(OMEGAS), 2))
        rao, bpto = frozen_rao(hydro)
        np.testing.assert_array_equal(np.array([r["rao_abs"] for r in results]), rao)
        np.testing.assert_array_equal(results[0]["b_pto"], bpto)
        self.assertEqual([r["omega"] for r in results], OMEGAS)

    def test_wamit_backend_runs_wamit_and_reads_its_files(self):
        config = {"opt_mode": 2, "ncpu": 1, "ram": 1, "fixed_radius": 1.5, "fixed_draft": 2.5, "depth": 13.0}
        config["num_wecs"] = 2
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(solvers, "run_wamit", lambda ws, exe=None: write_two_wec_workspace(ws, OMEGAS)):
                hydro = solvers.solve_hydrodynamics(None, config, [(8.0, 0.0), (8.0, 10.0)], tmp)
            expected = calculate_rao_matrix(tmp, 2)
            self.assertTrue(os.path.exists(os.path.join(tmp, "wec.pot")))
        got = rao_from_hydro(hydro)
        np.testing.assert_array_equal([r["rao_abs"] for r in got], [r["rao_abs"] for r in expected])


class TestWallAndSolverSettings(unittest.TestCase):
    def _iwallx(self, opt_mode, wall):
        with tempfile.TemporaryDirectory() as tmp:
            write_config_cfg(tmp, opt_mode, 0, wall)
            with open(os.path.join(tmp, "wec.cfg")) as f:
                return next(line for line in f.read().splitlines() if line.startswith("IWALLX0"))

    def test_wall_switch_in_wamit_input(self):
        self.assertEqual(self._iwallx(3, None), "IWALLX0=1")  # default as before
        self.assertEqual(self._iwallx(3, 1), "IWALLX0=1")
        self.assertEqual(self._iwallx(3, 0), "IWALLX0=0")
        self.assertEqual(self._iwallx(1, 1), "IWALLX0=0")  # geometry mode is always open sea

    def test_wall_enabled(self):
        self.assertFalse(solvers.wall_enabled({"opt_mode": 1, "vertical_wall": 1}))
        self.assertTrue(solvers.wall_enabled({"opt_mode": 3}))
        self.assertFalse(solvers.wall_enabled({"opt_mode": 3, "vertical_wall": 0}))

    def test_solver_validation(self):
        solvers.check_solver_settings(1, 1, 3)
        for bad in (0, 3, True):
            with self.assertRaises(ValueError):
                solvers.check_hydro_solver(bad)
        with self.assertRaises(ValueError):
            solvers.check_solver_settings(2, 1, 3)  # Capytaine with the wall

    def test_project_config_defaults(self):
        from src.utils.config_parser import parse_wec_cfg

        cfg = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))
        self.assertEqual(int(cfg["Simulation"]["HydroSolver"]), 1)
        self.assertEqual(int(cfg["WEC Parameters"]["VerticalWall"]), 1)


class TestCapytaineMesh(unittest.TestCase):
    def test_full_mesh_volume_waterplane_and_normals(self):
        for shape, radius, draft in ((1, 1.5, 2.5), (2, 2.5, 5.0)):
            quarter = mesh.build_mesh_panels(shape, radius, draft, 120)
            full = solvers.full_panels(quarter)
            self.assertEqual(len(full), 4 * len(quarter))
            volume, waterplane = solvers.panel_volume_and_waterplane(full)
            self.assertAlmostEqual(volume / mesh.displaced_volume(shape, radius, draft), 1.0, delta=0.02)
            self.assertAlmostEqual(waterplane / (math.pi * radius**2), 1.0, delta=0.02)
            p = np.array(full)
            vectors = 0.5 * np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 1])
            centroids = p.mean(axis=1)
            outward = np.sum(vectors[:, :2] * centroids[:, :2], axis=1) + vectors[:, 2] * -1.0 * (centroids[:, 2] < 0)
            self.assertTrue(np.all(outward > -1e-9))  # every panel faces the water (away from the axis or down)

    def test_frequency_list_matches_wamit(self):
        config = {"omega_max": 3.0, "freq_grid": 0}
        omegas = solvers.frequency_list(config, 1.0, 1.0, 1)
        self.assertEqual(len(omegas), 51)
        self.assertEqual((omegas[0], omegas[-1]), (0.5, 3.0))


@unittest.skipUnless(HAS_CAPYTAINE, "Capytaine is not installed")
class TestCapytaineBackend(unittest.TestCase):
    CONFIG: ClassVar[dict] = {
        "opt_mode": 1,
        "num_wecs": 1,
        "ncpu": 1,
        "depth": 30.0,
        "mesh_panels": 40,
        "omega_max": 0.7,
        "shape": 2,
    }

    def test_single_body_energy_relation_and_convention(self):
        hydro = solvers.capytaine_hydrodynamics([1.0, 1.5], dict(self.CONFIG))
        self.assertEqual(list(hydro.omegas), [0.5, 0.55, 0.6, 0.65, 0.7])
        self.assertTrue(np.all(hydro.damping[:, 0, 0] > 0))
        for k, w in enumerate(hydro.omegas):
            kw = solvers_wavenumber(w, 30.0)
            cg = 0.5 * w / kw * (1 + 2 * kw * 30.0 / math.sinh(2 * kw * 30.0))
            b_from_f = kw * abs(hydro.excitation[k, 0]) ** 2 / (4 * 1025.0 * 9.80665 * cg)
            self.assertAlmostEqual(hydro.damping[k, 0, 0] / b_from_f, 1.0, delta=0.03)

    def test_two_bodies_are_reciprocal_and_the_wall_is_refused(self):
        config = dict(self.CONFIG, opt_mode=3, num_wecs=2, vertical_wall=0, omega_max=0.6)
        hydro = solvers.capytaine_hydrodynamics([1.0, 1.5], config, positions=[(0.0, 0.0), (0.0, 6.0)])
        np.testing.assert_allclose(hydro.added_mass[:, 0, 1], hydro.added_mass[:, 1, 0], rtol=1e-3)
        np.testing.assert_allclose(hydro.damping[:, 0, 1], hydro.damping[:, 1, 0], rtol=1e-3, atol=1e-6)
        with self.assertRaises(ValueError):
            solvers.capytaine_hydrodynamics([1.0, 1.5], dict(config, vertical_wall=1), [(0.0, 0.0), (0.0, 6.0)])


def solvers_wavenumber(omega, depth, g=9.80665):
    nu = omega**2 / g
    lo, hi = 1e-9, nu + 10.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if mid * math.tanh(mid * depth) < nu else (lo, mid)
    return 0.5 * (lo + hi)


if __name__ == "__main__":
    unittest.main()
