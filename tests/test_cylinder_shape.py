"""평평한 바닥 원통 WEC(Shape = 2) 테스트: 메쉬 기하, 형상 선택, WAMIT 입력 (WAMIT 없이 실행)."""

import math
import os
import tempfile
import unittest

import numpy as np

from src.physics import mesh_axisymmetric_shape as mesh
from src.physics.wamit_handler import adaptive_omegas, heave_omega0, write_wamit_inputs
from src.utils.config_parser import parse_wec_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGNS = [(2.5, 5.0), (0.5, 2.0), (2.5, 0.5), (1.0, 1.0), (0.5, 0.5)]


def area_vectors(panels):
    p = np.array(panels, dtype=float)  # (N, 4, 3)
    return 0.5 * np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 1]), p.mean(axis=1)


class TestCylinderMesh(unittest.TestCase):
    def _panels(self, radius, draft, target=120):
        n, nz = mesh.choose_cylinder_grid(radius, draft, target)
        return mesh.build_cylinder_panels(radius, draft, n, nz), n, nz

    def test_count_formula_and_target(self):
        for radius, draft in DESIGNS:
            panels, n, nz = self._panels(radius, draft)
            self.assertEqual(len(panels), mesh.count_cylinder_panels(n, nz))
            self.assertLess(abs(len(panels) - 120) / 120, 0.15, (radius, draft))

    def test_area_and_volume_of_the_quarter_model(self):
        for radius, draft in DESIGNS:
            panels, _, _ = self._panels(radius, draft)
            vectors, centroids = area_vectors(panels)
            area = np.linalg.norm(vectors, axis=1).sum()
            volume = np.sum(centroids[:, 0] * vectors[:, 0])  # divergence theorem, field (x, 0, 0)
            self.assertAlmostEqual(area / (np.pi * radius * draft / 2 + np.pi * radius**2 / 4), 1.0, delta=0.01)
            self.assertAlmostEqual(volume / (np.pi * radius**2 * draft / 4), 1.0, delta=0.015)

    def test_vertices_and_normals(self):
        for radius, draft in DESIGNS:
            panels, _, _ = self._panels(radius, draft)
            pts = np.array(panels).reshape(-1, 3)
            r = np.hypot(pts[:, 0], pts[:, 1])
            self.assertTrue(np.all(pts[:, :2] >= -1e-12))  # quarter model
            self.assertTrue(np.all((pts[:, 2] <= 1e-12) & (pts[:, 2] >= -draft - 1e-12)))
            self.assertTrue(np.all(r <= radius + 1e-9))
            side = np.abs(pts[:, 2] + draft) > 1e-9
            np.testing.assert_allclose(r[side], radius, atol=1e-9)  # side vertices on the cylinder
            vectors, centroids = area_vectors(panels)
            bottom = np.abs(centroids[:, 2] + draft) < 1e-9
            self.assertTrue(np.all(vectors[bottom, 2] < 0))  # bottom normals point down (into the water)
            radial = np.sum(vectors[~bottom, :2] * centroids[~bottom, :2], axis=1)
            self.assertTrue(np.all(radial > 0))

    def test_side_and_bottom_meet_with_the_same_rim_points(self):
        radius, draft = 1.0, 1.0
        panels, n, _ = self._panels(radius, draft)
        pts = np.array(panels).reshape(-1, 3)
        rim = pts[(np.abs(pts[:, 2] + draft) < 1e-9) & (np.abs(np.hypot(pts[:, 0], pts[:, 1]) - radius) < 1e-9)]
        angles = np.unique(np.round(np.arctan2(rim[:, 1], rim[:, 0]), 9))
        np.testing.assert_allclose(angles, (np.pi / 2) * np.arange(2 * n + 1) / (2 * n), atol=1e-9)

    def test_gdf_file_and_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.gdf")
            count = mesh.generate_mesh(mesh.SHAPE_CYLINDER, 1.0, 2.0, 100, path)
            with open(path) as f:
                lines = f.read().splitlines()
            self.assertIn("flat bottom", lines[0])
            self.assertEqual(int(lines[3].split()[0]), count)
            self.assertEqual(len(lines), 4 + 4 * count)
        self.assertEqual(
            mesh.generate_mesh(mesh.SHAPE_CYLINDER_HEMISPHERE, 1.0, 2.0, 100),
            mesh.generate_cylinder_hemisphere_mesh(1.0, 2.0, 100),
        )

    def test_invalid_inputs(self):
        for bad in ((0.0, 1.0, 100), (1.0, -1.0, 100), (1.0, 1.0, 5)):
            with self.assertRaises(ValueError, msg=bad):
                mesh.generate_cylinder_mesh(*bad)
        for bad in (0, 3, True, "1"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                mesh.check_shape(bad)


class TestShapeQuantities(unittest.TestCase):
    def test_total_draft_and_volume(self):
        self.assertEqual(mesh.total_draft(1, 2.0, 3.0), 5.0)
        self.assertEqual(mesh.total_draft(2, 2.0, 3.0), 3.0)
        self.assertAlmostEqual(mesh.displaced_volume(2, 2.0, 3.0), math.pi * 12.0)
        self.assertAlmostEqual(mesh.displaced_volume(1, 2.0, 3.0), math.pi * 12.0 + 2 / 3 * math.pi * 8.0)

    def test_heave_frequency_and_adaptive_grid_follow_the_shape(self):
        self.assertAlmostEqual(heave_omega0(1.5, 2.5, 2), math.sqrt(9.80665 / 2.5))
        self.assertAlmostEqual(heave_omega0(1.5, 2.5, 1), math.sqrt(9.80665 / 3.5))
        self.assertEqual(heave_omega0(1.5, 2.5), heave_omega0(1.5, 2.5, 1))
        self.assertNotEqual(adaptive_omegas(1.5, 2.5, 3.0, 2), adaptive_omegas(1.5, 2.5, 3.0, 1))

    def test_project_default_shape(self):
        cfg = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))
        self.assertEqual(mesh.check_shape(int(cfg["WEC Parameters"]["Shape"])), mesh.DEFAULT_SHAPE)


class TestWamitInputsUseTheShape(unittest.TestCase):
    def _config(self, **extra):
        config = {"opt_mode": 2, "ncpu": 1, "ram": 1, "fixed_radius": 1.5, "fixed_draft": 2.5, "depth": 13.0}
        config.update(extra)
        return config

    def _header(self, workspace):
        with open(os.path.join(workspace, "wec.gdf")) as f:
            return f.readline()

    def test_shape_selects_the_mesh_and_the_cache_follows(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_wamit_inputs(None, self._config(), tmp, positions=[(8.0, 0.0)])
            self.assertIn("hemisphere", self._header(tmp))
            write_wamit_inputs(None, self._config(shape=2), tmp, positions=[(8.0, 0.0)])
            self.assertIn("flat bottom", self._header(tmp))
            write_wamit_inputs(None, self._config(shape=1), tmp, positions=[(8.0, 0.0)])
            self.assertIn("hemisphere", self._header(tmp))

    def test_invalid_shape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            write_wamit_inputs(None, self._config(shape=7), tmp, positions=[(8.0, 0.0)])


if __name__ == "__main__":
    unittest.main()
