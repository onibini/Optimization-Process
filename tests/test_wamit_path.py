"""WAMIT 실행 파일 경로 결정 테스트 (config.cfg > 환경 변수 WAMIT_EXE > 기본 경로)."""

import os
import sys
import unittest
from unittest import mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.physics.wamit_handler import DEFAULT_WAMIT_EXE, WAMIT_EXE_ENV_VAR, WamitRunError, resolve_wamit_exe, run_wamit


class TestResolveWamitExe(unittest.TestCase):
    def test_default_when_nothing_given(self):
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop(WAMIT_EXE_ENV_VAR, None)
            self.assertEqual(resolve_wamit_exe(), DEFAULT_WAMIT_EXE)

    def test_env_var_overrides_default(self):
        with mock.patch.dict(os.environ, {WAMIT_EXE_ENV_VAR: "D:/tools/WAMIT.exe"}):
            self.assertEqual(resolve_wamit_exe(), "D:/tools/WAMIT.exe")

    def test_configured_path_overrides_env_var(self):
        with mock.patch.dict(os.environ, {WAMIT_EXE_ENV_VAR: "D:/tools/WAMIT.exe"}):
            self.assertEqual(resolve_wamit_exe("E:/wamit/WAMIT.exe"), "E:/wamit/WAMIT.exe")

    def test_missing_configured_executable_is_reported(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(WamitRunError) as ctx:
                run_wamit(tmp, os.path.join(tmp, "no_such_WAMIT.exe"))
            self.assertIn("no_such_WAMIT.exe", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
