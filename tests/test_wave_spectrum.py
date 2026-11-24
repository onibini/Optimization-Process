"""파랑 스펙트럼(JONSWAP ITTC·Goda, Pierson-Moskowitz) 테스트."""

import os
import unittest

import numpy as np

from src.physics.wave_spectrum import DEFAULT_WAVE_SPEC, WAVE_SPECTRA, check_wave_spec, get_jonswap_spectrum
from src.utils.config_parser import parse_wec_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = [(1.07, 5.46), (0.87, 4.48), (0.92, 6.66)]  # Buan, Chilbaldo, Yeongilmanhang (Hs, Tp)
OMEGA = np.linspace(0.01, 15.0, 300001)


def hs_from_spectrum(hs, tp, spec, gamma=1.4):
    return 4.0 * np.sqrt(np.trapezoid(get_jonswap_spectrum(OMEGA, hs, tp, gamma, spec), OMEGA))


class TestSpectra(unittest.TestCase):
    def test_ittc_and_pm_reproduce_the_significant_wave_height(self):
        for hs, tp in SITES:
            self.assertAlmostEqual(hs_from_spectrum(hs, tp, 1) / hs, 1.0, delta=0.003)
            self.assertAlmostEqual(hs_from_spectrum(hs, tp, 3) / hs, 1.0, delta=0.003)

    def test_goda_form_overestimates_hs_at_gamma_1_4(self):
        for hs, tp in SITES:
            self.assertAlmostEqual(hs_from_spectrum(hs, tp, 2) / hs, 1.041, delta=0.005)

    def test_pm_is_ittc_without_peak_enhancement(self):
        np.testing.assert_allclose(
            get_jonswap_spectrum(OMEGA, 1.0, 6.0, 1.0, 1), get_jonswap_spectrum(OMEGA, 1.0, 6.0, 3.3, 3), rtol=1e-12
        )

    def test_peak_is_at_the_peak_frequency(self):
        tp = 5.46
        for spec in WAVE_SPECTRA:
            s = get_jonswap_spectrum(OMEGA, 1.0, tp, 1.4, spec)
            self.assertAlmostEqual(OMEGA[np.argmax(s)], 2 * np.pi / tp, delta=0.01, msg=spec)

    def test_zero_frequency_is_zero(self):
        for spec in WAVE_SPECTRA:
            self.assertEqual(get_jonswap_spectrum(np.array([0.0, 1.0]), 1.0, 6.0, 1.4, spec)[0], 0.0)

    def test_validation(self):
        for spec in WAVE_SPECTRA:
            self.assertEqual(check_wave_spec(spec), spec)
        for bad in (0, 4, True, "1"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                check_wave_spec(bad)
        with self.assertRaises(ValueError):
            get_jonswap_spectrum(OMEGA[:5], 1.0, 6.0, 1.4, 4)

    def test_project_default_is_ittc(self):
        self.assertEqual(DEFAULT_WAVE_SPEC, 1)
        cfg = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))
        self.assertEqual(check_wave_spec(int(cfg["Simulation"]["WaveSpec"])), 1)


if __name__ == "__main__":
    unittest.main()
