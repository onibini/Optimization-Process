"""가진력 출처 선택(diffraction .3 / Haskind .2) 테스트. WAMIT 없이 합성 출력 파일로 검증합니다."""

import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.physics.rao_calc import WamitOutputError, calculate_rao_matrix  # noqa: E402
from src.physics.wamit_handler import write_frc_file  # noqa: E402

OMEGAS = [0.5, 1.0, 1.5]
RHO, G = 1025.0, 9.80665


def _write_force(path, re_im_by_omega):
    with open(path, "w") as f:
        f.write(" WAMIT Numeric Output\n")
        for w, (re, im) in zip(OMEGAS, re_im_by_omega):
            f.write(f"  {w:.6E}  0.000000E+00     3  0.0  0.0  {re:.6E}  {im:.6E}\n")


def _make_workspace(d, with_haskind=True, with_diffraction=True):
    with open(os.path.join(d, "wec.out"), "w") as f:
        f.write(" Volumes (VOLX,VOLY,VOLZ):   0.0  0.0  2.0\n")
    with open(os.path.join(d, "wec.hst"), "w") as f:
        f.write(" header\n")
        f.write("   3   3   3.0\n")
    with open(os.path.join(d, "wec.1"), "w") as f:
        f.write(" header\n")
        for w in OMEGAS:
            f.write(f"  {w:.6E}  3  3  0.5  0.2\n")
    if with_haskind:
        _write_force(os.path.join(d, "wec.2"), [(1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])
    if with_diffraction:
        _write_force(os.path.join(d, "wec.3"), [(2.0, 0.0), (4.0, 0.0), (6.0, 0.0)])


def _rao(d, **kwargs):
    return [r["rao_abs"][0] for r in calculate_rao_matrix(d, 1, rho=RHO, g=G, **kwargs)]


class TestExcitationSource(unittest.TestCase):
    def test_default_uses_diffraction_file(self):
        with tempfile.TemporaryDirectory() as d:
            _make_workspace(d)
            default = _rao(d)
            diffraction = _rao(d, excitation="diffraction")
            haskind = _rao(d, excitation="haskind")
        self.assertEqual(default, diffraction)
        # 합성 데이터에서 .3의 가진력은 .2의 정확히 2배 -> RAO(선형)도 2배
        for diff, hask in zip(diffraction, haskind):
            self.assertAlmostEqual(diff / hask, 2.0, places=9)

    def test_default_does_not_need_haskind_file(self):
        with tempfile.TemporaryDirectory() as d:
            _make_workspace(d, with_haskind=False)
            self.assertEqual(len(_rao(d)), len(OMEGAS))

    def test_missing_diffraction_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            _make_workspace(d, with_diffraction=False)
            with self.assertRaises(WamitOutputError) as ctx:
                _rao(d)
        self.assertIn("wec.3", str(ctx.exception))

    def test_unknown_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            _make_workspace(d)
            with self.assertRaises(ValueError):
                _rao(d, excitation="froude-krylov")

    def test_frc_haskind_option_still_available(self):
        with tempfile.TemporaryDirectory() as d:
            write_frc_file(d, 1, excitation="haskind")
            with open(os.path.join(d, "wec.frc")) as f:
                options = f.readlines()[1].split()[:9]
        self.assertEqual(options, ["1", "1", "0", "0", "0", "0", "0", "0", "0"])


if __name__ == "__main__":
    unittest.main()
