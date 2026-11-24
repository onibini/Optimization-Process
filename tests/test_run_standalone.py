"""scripts/run_standalone.py 테스트 (WAMIT, HydroBEM 없이 실행)."""

import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("run_standalone", os.path.join(ROOT, "scripts", "run_standalone.py"))
standalone = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(standalone)

from src.utils.config_parser import parse_wec_cfg  # noqa: E402


class TestRunStandalone(unittest.TestCase):
    def test_candidates_cover_distinct_thread_splits(self):
        # 96 논리 CPU, 주파수 51: 48 x 1, 51 x 1(= NCPU 96과 같은 나눔), 51 x 2
        self.assertEqual(standalone.candidate_ncpus(96, 51), [48, 51, 102])
        self.assertEqual(standalone.candidate_ncpus(20, 51), [10, 20])
        self.assertEqual(standalone.candidate_ncpus(1, 51), [1])

    def test_set_value_changes_only_that_key(self):
        with open(os.path.join(ROOT, "config.cfg"), encoding="utf-8") as fh:
            text = fh.read()
        new = standalone.set_value(standalone.set_value(text, "NCPU", 96), "Workers", 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "job.cfg")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            cfg = parse_wec_cfg(path)
            old = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))
        self.assertEqual(cfg["WAMIT Settings"]["NCPU"], "96")
        self.assertEqual(cfg["WAMIT Settings"]["Workers"], "1")
        for section in old:
            for key, value in old[section].items():
                if key not in ("NCPU", "Workers"):
                    self.assertEqual(cfg[section][key], value, key)
        with self.assertRaises(ValueError):
            standalone.set_value(text, "NoSuchKey", 1)

    def test_newest_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                standalone.newest_checkpoint(tmp)
            for k, name in enumerate(("a_checkpoint.json", "b_checkpoint.json", "c_summary.json")):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("{}")
                os.utime(path, (1000 + k, 1000 + k))
            self.assertEqual(os.path.basename(standalone.newest_checkpoint(tmp)), "b_checkpoint.json")


if __name__ == "__main__":
    unittest.main()
