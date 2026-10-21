"""원통 + 반구 GDF 메쉬 테스트 (WAMIT 없이 실행)."""

import json
import os
import sys
import tempfile
import unittest
import warnings

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.physics.mesh_axisymmetric_shape import (
    DEFAULT_QUARTER_PANELS,
    MIN_QUARTER_PANELS,
    build_panels,
    choose_grid,
    count_panels,
    generate_cylinder_hemisphere_mesh,
)
from src.physics.wamit_handler import PANEL_MEMORY_WARN, write_wamit_inputs

SHAPES = [(0.5, 0.5), (0.5, 5.0), (1.5, 2.5), (2.5, 0.5), (2.5, 5.0)]


def read_gdf(path):
    with open(path) as f:
        lines = f.read().split("\n")
    header = {"isx_isy": tuple(int(v) for v in lines[2].split()[:2]), "neqn": int(lines[3].split()[0])}
    points = [[float(v) for v in line.split()] for line in lines[4 : 4 + 4 * header["neqn"]]]
    return header, np.array(points).reshape(header["neqn"], 4, 3)


class TestChooseGrid(unittest.TestCase):
    def test_panel_count_formula_matches_built_mesh(self):
        for radius, draft in SHAPES:
            n, nz = choose_grid(radius, draft, 100)
            self.assertEqual(len(build_panels(radius, draft, n, nz)), count_panels(n, nz))

    def test_actual_count_is_close_to_target(self):
        for radius, draft in SHAPES:
            for target in (40, 80, 150, 250):
                n, nz = choose_grid(radius, draft, target)
                self.assertLessEqual(abs(count_panels(n, nz) - target) / target, 0.25, (radius, draft, target))

    def test_more_target_panels_never_gives_fewer(self):
        counts = [count_panels(*choose_grid(1.5, 2.5, t)) for t in (30, 60, 120, 240, 480)]
        self.assertEqual(counts, sorted(counts))


class TestMeshGeometry(unittest.TestCase):
    def _mesh(self, radius, draft, target=130):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "wec.gdf")
            count = generate_cylinder_hemisphere_mesh(radius, draft, target, path)
            header, panels = read_gdf(path)
        return count, header, panels

    def test_header_symmetry_and_panel_count(self):
        count, header, panels = self._mesh(1.5, 2.5)
        self.assertEqual(header["isx_isy"], (1, 1))
        self.assertEqual(header["neqn"], count)
        self.assertEqual(len(panels), count)

    def test_quarter_model_only(self):
        _, _, panels = self._mesh(1.5, 2.5)
        self.assertGreaterEqual(panels[..., 0].min(), -1e-9)
        self.assertGreaterEqual(panels[..., 1].min(), -1e-9)
        self.assertLessEqual(panels[..., 2].max(), 1e-9)

    def test_vertices_lie_on_cylinder_and_sphere(self):
        for radius, draft in SHAPES:
            _, _, panels = self._mesh(radius, draft)
            for x, y, z in panels.reshape(-1, 3):
                if z >= -draft - 1e-9:
                    self.assertAlmostEqual(np.hypot(x, y), radius, delta=1e-5)  # GDF는 유효숫자 7자리
                else:
                    self.assertAlmostEqual(np.linalg.norm([x, y, z + draft]), radius, delta=1e-5)
            self.assertAlmostEqual(panels[..., 2].min(), -(draft + radius), delta=1e-5)

    def test_normals_point_outward(self):
        for radius, draft in SHAPES:
            _, _, panels = self._mesh(radius, draft)
            for p in panels:
                normal = np.cross(p[2] - p[0], p[3] - p[1])
                centroid = p.mean(axis=0)
                axis_z = min(0.0, max(-draft, centroid[2]))
                self.assertGreater(np.dot(normal, centroid - np.array([0.0, 0.0, axis_z])), 0.0)

    def test_wetted_area_close_to_exact(self):
        for radius, draft in SHAPES:
            _, _, panels = self._mesh(radius, draft, target=200)
            area = sum(0.5 * np.linalg.norm(np.cross(p[2] - p[0], p[3] - p[1])) for p in panels) * 4
            exact = 2 * np.pi * radius * draft + 2 * np.pi * radius**2
            self.assertAlmostEqual(area / exact, 1.0, delta=0.01, msg=(radius, draft))

    def test_no_degenerate_pole_panels_and_uniform_sizes(self):
        for radius, draft in SHAPES:
            _, _, panels = self._mesh(radius, draft)
            areas = []
            for p in panels:
                self.assertEqual(len({tuple(np.round(q, 9)) for q in p}), 4)  # 삼각형 팬(중복 꼭짓점) 없음
                areas.append(0.5 * np.linalg.norm(np.cross(p[2] - p[0], p[3] - p[1])))
            self.assertLess(max(areas) / min(areas), 4.0, (radius, draft))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            generate_cylinder_hemisphere_mesh(1.0, 1.0, MIN_QUARTER_PANELS - 1)
        with self.assertRaises(ValueError):
            generate_cylinder_hemisphere_mesh(0.0, 1.0)
        with self.assertRaises(ValueError):
            generate_cylinder_hemisphere_mesh(1.0, -1.0)

    def test_no_file_written_without_output_path(self):
        self.assertEqual(generate_cylinder_hemisphere_mesh(1.0, 1.0, 60), count_panels(*choose_grid(1.0, 1.0, 60)))


class TestWamitInputsUseMeshPanels(unittest.TestCase):
    def _config(self, **extra):
        config = {
            "opt_mode": 2,
            "ncpu": 1,
            "ram": 1,
            "fixed_radius": 1.5,
            "fixed_draft": 2.5,
            "depth": 13.0,
        }
        config.update(extra)
        return config

    def test_panel_target_is_taken_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_wamit_inputs(None, self._config(mesh_panels=60), tmp, positions=[(8.0, 0.0)])
            with open(os.path.join(tmp, "wec.gdf.meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            header, _ = read_gdf(os.path.join(tmp, "wec.gdf"))
        self.assertEqual(meta["target_panels"], 60)
        self.assertLessEqual(abs(header["neqn"] - 60) / 60, 0.2)

    def test_default_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_wamit_inputs(None, self._config(mesh_panels=None), tmp, positions=[(8.0, 0.0)])
            header, _ = read_gdf(os.path.join(tmp, "wec.gdf"))
        self.assertLessEqual(abs(header["neqn"] - DEFAULT_QUARTER_PANELS) / DEFAULT_QUARTER_PANELS, 0.2)

    def test_gdf_is_cached_and_regenerated_when_panel_target_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            gdf = os.path.join(tmp, "wec.gdf")
            write_wamit_inputs(None, self._config(mesh_panels=60), tmp, positions=[(8.0, 0.0)])
            stamp = os.stat(gdf).st_mtime_ns
            write_wamit_inputs(None, self._config(mesh_panels=60), tmp, positions=[(9.0, 0.0)])
            self.assertEqual(os.stat(gdf).st_mtime_ns, stamp)  # 같은 형상·패널 수는 재생성하지 않음
            write_wamit_inputs(None, self._config(mesh_panels=120), tmp, positions=[(9.0, 0.0)])
            header, _ = read_gdf(gdf)
        self.assertGreater(header["neqn"], 100)

    def test_warns_when_total_panels_exceed_memory_guideline(self):
        positions = [(8.0 + 6.0 * i, 0.0) for i in range(5)]
        per_body = PANEL_MEMORY_WARN // 5 + 20
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            write_wamit_inputs(None, self._config(mesh_panels=per_body), tmp, positions=positions)
        self.assertTrue(any("allocation error" in str(w.message) for w in caught))

    def test_no_warning_for_default_five_bodies(self):
        positions = [(8.0 + 6.0 * i, 0.0) for i in range(5)]
        with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            write_wamit_inputs(None, self._config(mesh_panels=None), tmp, positions=positions)
        self.assertFalse(caught)


if __name__ == "__main__":
    unittest.main()
