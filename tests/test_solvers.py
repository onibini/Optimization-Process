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
from src.physics.rao_calc import PTO_RAO_PEAK, calculate_rao_matrix, rao_from_hydro, read_wamit_hydro
from src.physics.wamit_handler import write_config_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from fake_wamit import write_two_wec_workspace  # noqa: E402

HAS_CAPYTAINE = importlib.util.find_spec("capytaine") is not None
HAS_HYDROBEM = importlib.util.find_spec("hydrobem_gui") is not None
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
            results = calculate_rao_matrix(tmp, 2, pto_rule=PTO_RAO_PEAK)
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

    def test_frc_format_keyword_is_spelled_for_wamit(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_config_cfg(tmp, 3)
            with open(os.path.join(tmp, "wec.cfg")) as f:
                lines = f.read().splitlines()
        self.assertIn("IALTFRC=1", lines)
        self.assertNotIn("IALTERC=1", lines)

    def test_wall_enabled(self):
        self.assertFalse(solvers.wall_enabled({"opt_mode": 1, "vertical_wall": 1}))
        self.assertTrue(solvers.wall_enabled({"opt_mode": 3}))
        self.assertFalse(solvers.wall_enabled({"opt_mode": 3, "vertical_wall": 0}))

    def test_solver_validation(self):
        solvers.check_solver_settings(1, 1, 3)
        for bad in (0, 4, True):
            with self.assertRaises(ValueError):
                solvers.check_hydro_solver(bad)
        with self.assertRaises(ValueError):
            solvers.check_solver_settings(2, 1, 3)  # Capytaine with the wall

    def test_project_config_defaults(self):
        from src.utils.config_parser import parse_wec_cfg

        cfg = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))
        self.assertEqual(int(cfg["Simulation"]["HydroSolver"]), 3)
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


class TestHydroBEMSettings(unittest.TestCase):
    def test_solver_names(self):
        self.assertEqual(solvers.HYDRO_SOLVERS[3], "HydroBEM")
        solvers.check_hydro_solver(3)

    def test_wave_angle_must_be_zero(self):
        with self.assertRaises(ValueError):
            solvers.check_solver_settings(3, 1, 3, wave_angle=10.0)
        # OptMode 1 ignores the angle (one axisymmetric WEC)
        with mock.patch.object(solvers, "import_hydrobem", return_value=None):
            solvers.check_solver_settings(3, 1, 1, wave_angle=10.0)
            solvers.check_solver_settings(3, 1, 3, wave_angle=0.0)

    def test_missing_package_gives_a_clear_error(self):
        with mock.patch.dict(sys.modules, {"hydrobem_gui": None}), self.assertRaises(ImportError) as ctx:
            solvers.import_hydrobem()
        self.assertIn("hydrobem_gui", str(ctx.exception))

    def test_hydrobem_thread_split(self):
        # 주파수 51개: 주파수 스레드는 51을 넘지 않고, 남는 스레드는 주파수 안 스레드로 간다
        self.assertEqual(solvers.hydrobem_threads(8, 51), (8, 1))  # 이전과 같음
        self.assertEqual(solvers.hydrobem_threads(51, 51), (51, 1))
        self.assertEqual(solvers.hydrobem_threads(96, 51), (51, 1))
        self.assertEqual(solvers.hydrobem_threads(102, 51), (51, 2))
        self.assertEqual(solvers.hydrobem_threads(0, 51), (1, 1))

    def test_high_order_settings(self):
        self.assertEqual(solvers.check_high_order(0, 1, 1), 0)  # 저차는 어떤 해석기·형상이든 됨
        self.assertEqual(solvers.check_high_order(2, 3, 2), 2)
        for bad in (-1, True, 2.5):
            with self.assertRaises(ValueError):
                solvers.check_high_order(bad, 3, 2)
        with self.assertRaises(ValueError):
            solvers.check_high_order(2, 1, 2)  # WAMIT
        self.assertEqual(solvers.check_high_order(1, 3, 1), 1)  # 원통 + 반구 (cad2bem 반구 패치)
        with self.assertRaises(ValueError):
            solvers.check_high_order(1, 3, 3)  # 없는 형상

    def test_hemisphere_patches(self):
        """Shape 1 고차 패치: 반구 3개 + 원통 1개, 흘수만큼 내려가고 모든 패치가 spans x spans."""
        a = solvers.hemisphere_hbg(2.0, 1.0, 1)
        b = solvers.hemisphere_hbg(2.0, 3.5, 2)
        self.assertEqual(len(a["patches"]), 4)
        self.assertEqual(a["symmetry"], "xz_and_yz")
        for pa, pb in zip(a["patches"][:3], b["patches"][:3], strict=True):
            za, zb = np.array(pa["coefficients"])[..., 2], np.array(pb["coefficients"])[..., 2]
            np.testing.assert_allclose(za - zb, 2.5, atol=1e-12)  # 흘수 차이만큼 이동
            self.assertEqual(pb["discretization"], [2, 2, 3, 3, 3, 4])
        bottom = np.array(a["patches"][0]["coefficients"])
        self.assertAlmostEqual(np.linalg.norm(bottom[0, 0] - [0.0, 0.0, -1.0]), 2.0, places=5)  # 반구 위의 점
        wall = np.array(b["patches"][3]["coefficients"])
        self.assertEqual(wall[..., 2].min(), -3.5)
        self.assertEqual(wall[..., 2].max(), 0.0)
        for bad in (0.55, 3.0):
            with self.assertRaises(ValueError):
                solvers.hemisphere_hbg(bad, 1.0, 1)

    def test_high_order_has_its_own_eval_db(self):
        from src.utils.eval_db import fingerprint

        base = {
            "site_name": "Buan", "opt_mode": 1, "num_wecs": 1, "wave_spec": 1, "hs": 1.0, "tp": 6.0, "gamma": 3.3,
            "depth": 50.0, "mesh_panels": 120, "solver": 0, "omega_max": 3.0, "freq_grid": 0, "hydro_solver": 3,
        }  # fmt: skip
        self.assertNotIn("high_order_spans", fingerprint(base))
        self.assertEqual(fingerprint(dict(base, high_order_spans=0)), fingerprint(base))
        self.assertEqual(fingerprint(dict(base, high_order_spans=2))["high_order_spans"], 2)


@unittest.skipUnless(HAS_HYDROBEM, "hydrobem_gui is not installed")
class TestHydroBEMBackend(unittest.TestCase):
    CONFIG: ClassVar[dict] = {
        "opt_mode": 3, "depth": 13.0, "mesh_panels": 60, "shape": 1, "ncpu": 2, "vertical_wall": 1,
        "wave_angle": 0.0, "omega_max": 1.0, "freq_grid": 0, "hydro_solver": 3,
    }  # fmt: skip
    POSITIONS: ClassVar[list] = [(6.0, 0.0), (6.0, 8.0)]

    def solve(self, **changes):
        cfg = dict(self.CONFIG, **changes)
        with tempfile.TemporaryDirectory() as tmp:
            return solvers.solve_hydrodynamics(np.array([2.0, 2.0, 6.0, 6.0, 8.0]), cfg, self.POSITIONS, tmp)

    def test_shapes_mass_and_stiffness(self):
        hydro = self.solve()
        self.assertEqual(hydro.added_mass.shape, (len(hydro.omegas), 2, 2))
        self.assertEqual(hydro.excitation.shape, (len(hydro.omegas), 2))
        volume = mesh.displaced_volume(1, 2.0, 2.0)
        self.assertAlmostEqual(hydro.mass[0, 0] / (solvers.RHO * volume), 1.0, delta=0.03)
        self.assertAlmostEqual(hydro.stiffness[0, 0] / (solvers.RHO * solvers.GRAVITY * math.pi * 4.0), 1.0, delta=0.03)
        self.assertTrue(np.allclose(hydro.added_mass, hydro.added_mass.transpose(0, 2, 1), rtol=1e-6))
        self.assertTrue(np.all(np.diagonal(hydro.damping, axis1=1, axis2=2) > 0))

    def test_heave_arrays_match_coefficient(self):
        # 전체 배열에서 고른 값이 HydroBEM의 coefficient(물체, 모드)와 같아야 한다 (5기, 6자유도 중 heave만)
        hb = solvers.import_hydrobem()
        model = hb.Model()
        solvers.high_order_mesh(model, 1.5, 3.0, 2)
        positions = [(5.0, 0.0), (8.0, 10.0), (8.0, -10.0), (14.0, 20.0), (14.0, -20.0)]
        for k, (x, y) in enumerate(positions):
            model.bodies.add(
                name=f"b{k}", mesh="wec", position=[x, y, 0.0], rotation_center=[0.0, 0.0, 0.0],
                modes=["heave"], interior_surface="none",
            )  # fmt: skip
        model.environment.update(
            depth=13.0, density=solvers.RHO, gravity=solvers.GRAVITY, domain="x_wall",
            frequency_input="omegas", omegas=np.array([0.6, 1.2, 2.4]), headings=[0.0],
        )  # fmt: skip
        model.first_order.update(radiation=True, diffraction=True, motion=False)
        model.options.update(frequency_threads=3, inner_threads=1, higher_order=True)
        results = model.solve()
        added, damping, force = solvers.hydrobem_heave_arrays(results, len(positions))
        for i in range(len(positions)):
            row = (f"b{i}", "heave")
            np.testing.assert_array_equal(force[:, i], results.coefficient("excitation_diffraction", row)[:, 0])
            for j in range(len(positions)):
                column = (f"b{j}", "heave")
                np.testing.assert_array_equal(added[:, i, j], results.coefficient("added_mass", row, column))
                np.testing.assert_array_equal(damping[:, i, j], results.coefficient("radiation_damping", row, column))

    def test_wall_and_open_sea_differ(self):
        wall = self.solve()
        open_sea = self.solve(vertical_wall=0)
        self.assertGreater(
            np.abs(wall.excitation - open_sea.excitation).max(), 1e-3 * np.abs(open_sea.excitation).max()
        )

    def test_thread_count_does_not_change_results(self):
        one, two = self.solve(ncpu=1), self.solve(ncpu=2)
        np.testing.assert_allclose(one.added_mass, two.added_mass, rtol=1e-9)
        np.testing.assert_allclose(one.excitation, two.excitation, rtol=1e-9)

    def test_hemisphere_high_order_matches_a_fine_low_order_mesh(self):
        """원통 + 반구: 고차 1(cad2bem 패치)의 정수압은 정확한 값이고, 계수는 저차 240패널과 가깝다."""
        with tempfile.TemporaryDirectory() as tmp:
            high = self.solve(high_order_spans=1, workspace_dir=tmp)
            self.assertFalse(os.path.exists(os.path.join(tmp, "wec.gdf")))
        low = self.solve(mesh_panels=240)
        volume = math.pi * 4.0 * 2.0 + 2.0 / 3.0 * math.pi * 8.0
        self.assertAlmostEqual(high.mass[0, 0] / (solvers.RHO * volume), 1.0, places=6)
        self.assertAlmostEqual(high.stiffness[0, 0] / (solvers.RHO * solvers.GRAVITY * math.pi * 4.0), 1.0, places=6)
        np.testing.assert_allclose(high.added_mass, low.added_mass, atol=0.02 * np.abs(low.added_mass).max())
        np.testing.assert_allclose(high.damping[:, 0, 0], low.damping[:, 0, 0], rtol=0.03)
        np.testing.assert_allclose(np.abs(high.excitation), np.abs(low.excitation), rtol=0.02)

    def test_high_order_matches_a_fine_low_order_mesh(self):
        """평평한 바닥 원통: 고차 3 spans와 저차 240패널이 가깝고, 고차의 정수압은 정확한 원통 값이다."""
        with tempfile.TemporaryDirectory() as tmp:
            high = self.solve(shape=2, high_order_spans=3, workspace_dir=tmp)
            self.assertFalse(os.path.exists(os.path.join(tmp, "wec.gdf")))  # 고차는 GDF를 쓰지 않음
        low = self.solve(shape=2, mesh_panels=240)
        self.assertAlmostEqual(high.mass[0, 0] / (solvers.RHO * math.pi * 4.0 * 2.0), 1.0, places=9)
        self.assertAlmostEqual(high.stiffness[0, 0] / (solvers.RHO * solvers.GRAVITY * math.pi * 4.0), 1.0, places=9)
        # 결합 항은 0을 지나는 주파수가 있어 상대 오차 대신 대각 크기 기준으로 본다
        np.testing.assert_allclose(high.added_mass, low.added_mass, atol=0.02 * np.abs(low.added_mass).max())
        np.testing.assert_allclose(high.damping[:, 0, 0], low.damping[:, 0, 0], rtol=0.03)
        np.testing.assert_allclose(np.abs(high.excitation), np.abs(low.excitation), rtol=0.02)
