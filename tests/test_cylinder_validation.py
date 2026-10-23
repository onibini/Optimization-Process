"""scripts/experiments/cylinder_validation.py 테스트: 원통 heave 반해석해와 파랑 관계식 (WAMIT 없이 실행)."""

import importlib.util
import math
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "cylinder_validation", os.path.join(ROOT, "scripts", "experiments", "cylinder_validation.py")
)
cv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cv)
G = 9.80665


class TestWaves(unittest.TestCase):
    def test_dispersion_roots(self):
        for omega, depth in ((0.5, 13.0), (1.5, 50.0), (3.0, 13.0)):
            k = cv.wavenumber(omega, depth)
            self.assertAlmostEqual(k * math.tanh(k * depth), omega**2 / G, places=10)
            roots = cv.evanescent_wavenumbers(omega, depth, 5)
            for m, km in enumerate(roots, start=1):
                self.assertAlmostEqual(km * math.tan(km * depth), -(omega**2) / G, places=6)
                self.assertTrue((m - 0.5) * math.pi / depth < km < m * math.pi / depth)

    def test_group_velocity_limits(self):
        omega = 2.0
        k = cv.wavenumber(omega, 200.0)
        self.assertAlmostEqual(cv.group_velocity(omega, 200.0), 0.5 * omega / k, places=6)  # deep water
        shallow = cv.group_velocity(0.05, 5.0)
        self.assertAlmostEqual(shallow, math.sqrt(G * 5.0), delta=0.01 * math.sqrt(G * 5.0))


class TestSemiAnalytical(unittest.TestCase):
    def test_converges_with_the_number_of_modes(self):
        for radius, draft, depth in ((2.5, 5.0, 50.0), (0.5, 2.0, 13.0)):
            fine = cv.cylinder_heave_radiation(radius, draft, depth, 1.5, modes=400)
            auto = cv.cylinder_heave_radiation(radius, draft, depth, 1.5)
            self.assertAlmostEqual(auto[0] / fine[0], 1.0, delta=0.005)
            self.assertAlmostEqual(auto[1] / fine[1], 1.0, delta=0.005)

    def test_damping_is_positive_and_deep_water_limit(self):
        a50 = cv.cylinder_heave_radiation(2.5, 5.0, 50.0, 1.2)
        a100 = cv.cylinder_heave_radiation(2.5, 5.0, 100.0, 1.2)
        self.assertGreater(a50[1], 0)
        self.assertAlmostEqual(a50[0] / a100[0], 1.0, delta=0.005)
        self.assertAlmostEqual(a50[1] / a100[1], 1.0, delta=0.005)

    def test_agrees_with_wamit_800_panels(self):
        # WAMIT v7, flat cylinder R 2.5 m, D 5.0 m, depth 50 m, 800 quarter panels (2026-10-23 run)
        for omega, a_wamit, b_wamit in ((0.5, 3.496e4, 1688.0), (1.3, 2.889e4, 4060.0)):
            a_semi, b_semi = cv.cylinder_heave_radiation(2.5, 5.0, 50.0, omega)
            self.assertAlmostEqual(a_wamit / a_semi, 1.0, delta=0.01)
            self.assertAlmostEqual(b_wamit / b_semi, 1.0, delta=0.01)

    def test_body_touching_the_bottom_is_rejected(self):
        with self.assertRaises(ValueError):
            cv.cylinder_heave_radiation(1.0, 13.0, 13.0, 1.0)


if __name__ == "__main__":
    unittest.main()
