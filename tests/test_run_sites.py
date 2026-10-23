"""scripts/experiments/run_sites.py 테스트 (WAMIT 없이 실행)."""

import contextlib
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from src.utils.config_parser import parse_wec_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("run_sites", os.path.join(ROOT, "scripts", "experiments", "run_sites.py"))
run_sites = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_sites)


class TestRunSites(unittest.TestCase):
    def test_site_id_is_replaced_and_the_rest_kept(self):
        with open(os.path.join(ROOT, "config.cfg"), encoding="utf-8") as f:
            text = f.read()
        new = run_sites.site_config(text, 2)
        self.assertEqual(len(new.splitlines()), len(text.splitlines()))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.cfg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            cfg = parse_wec_cfg(path)
        self.assertEqual(cfg["Environment"]["SiteID"], "2")
        self.assertEqual(cfg["Simulation"], parse_wec_cfg(os.path.join(ROOT, "config.cfg"))["Simulation"])

    def test_sites_run_in_order_and_a_failure_does_not_stop_the_rest(self):
        seen = []

        def fake_main(path):
            site = parse_wec_cfg(path)["Environment"]["SiteID"]
            seen.append(site)
            if site == "2":
                raise SystemExit(1)

        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "config.cfg")
            shutil.copy(os.path.join(ROOT, "config.cfg"), config)
            with (
                mock.patch.object(run_sites.wec_main, "main", fake_main),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                run_sites.main(["--sites", "1", "2", "3", "--config", config])
            self.assertTrue(os.path.exists(os.path.join(tmp, "config_site3.cfg")))
        self.assertEqual(seen, ["1", "2", "3"])
        self.assertEqual(raised.exception.code, 1)

    def test_missing_site_line_is_an_error(self):
        with self.assertRaises(ValueError):
            run_sites.site_config("[Environment]\n", 1)


if __name__ == "__main__":
    unittest.main()
