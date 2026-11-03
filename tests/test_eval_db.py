"""평가 기록 데이터베이스(src/utils/eval_db.py, scripts/build_eval_db.py) 테스트 (WAMIT 없이 실행)."""

import contextlib
import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest

import numpy as np

from src.algorithms import run_de
from src.algorithms.common import CachedEvaluator, OptimizationLogger, canonical_copy
from src.utils import eval_db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("build_eval_db", os.path.join(ROOT, "scripts", "build_eval_db.py"))
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

CONFIG = {
    "dimensions": 5,
    "bounds": [[3.0, 3.0, 0.5, 3.0, 0.5], [25.0, 25.0, 30.0, 25.0, 30.0]],
    "step_size": 0.5,
    "num_wecs": 5,
    "opt_mode": 2,
    "fixed_radius": 2.5,
    "fixed_draft": 5.0,
    "min_spacing": 4.0,
    "site_name": "Dummy",
    "wave_spec": 1,
    "hs": 1.0,
    "tp": 5.0,
    "gamma": 1.4,
    "depth": 30.0,
    "mesh_panels": 120,
    "solver": 0,
    "omega_max": 3.0,
    "freq_grid": 0,
    "shape": 1,
    "vertical_wall": 1,
    "wave_angle": 0.0,
    "hydro_solver": 1,
}


def fake_eval(vector, config):
    score = 1000.0 - float(np.sum((np.asarray(vector) - np.array([10.0, 10.0, 12.0, 20.0, 25.0])) ** 2))
    return score, [score / 5] * 5


class InTempDir(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()


class TestFingerprint(unittest.TestCase):
    def test_same_settings_same_file_and_any_change_another(self):
        name = eval_db.db_name(eval_db.fingerprint(CONFIG))
        self.assertEqual(name, eval_db.db_name(eval_db.fingerprint({**CONFIG, "workers": 4, "ncpu": 2})))
        for key, value in [("depth", 13.0), ("mesh_panels", 80), ("wave_spec", 2), ("wave_angle", 10.0), ("hs", 1.1)]:
            self.assertNotEqual(name, eval_db.db_name(eval_db.fingerprint({**CONFIG, key: value})), key)

    def test_old_configs_use_defaults_or_are_rejected(self):
        old = {k: v for k, v in CONFIG.items() if k not in ("shape", "vertical_wall", "wave_angle", "hydro_solver")}
        self.assertEqual(eval_db.fingerprint(old), eval_db.fingerprint(CONFIG))
        self.assertIsNone(eval_db.fingerprint({k: v for k, v in CONFIG.items() if k != "freq_grid"}))
        self.assertIsNone(eval_db.fingerprint({k: v for k, v in CONFIG.items() if k != "fixed_radius"}))

    def test_equal_numbers_give_equal_fingerprints(self):
        self.assertEqual(eval_db.fingerprint({**CONFIG, "depth": 30}), eval_db.fingerprint(CONFIG))


class TestStoredEvaluations(InTempDir):
    def _db(self, rows):
        path = eval_db.db_path(CONFIG, "db")
        records = {}
        eval_db.merge_records(records, rows, "test")
        eval_db.write_records(path, eval_db.fingerprint(CONFIG), records)
        return path

    def test_stored_designs_skip_eval_func_and_are_logged(self):
        stored = canonical_copy(np.array([10.0, 20.0, 25.0, 10.0, 12.0]), CONFIG)  # 정렬하면 [10, 10, 12, 20, 25]
        self._db([(stored, 1234.0, [1.0] * 5, False), ([3.2, 3.0, 1.0, 3.0, 2.0], 1.0, [0.0] * 5, False)])
        calls = []

        def counting_eval(vector, config):
            calls.append(vector.copy())
            return fake_eval(vector, config)

        config = {**CONFIG, "eval_cache": True, "eval_db_dir": "db"}
        logger = OptimizationLogger(config, algorithm="test")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            evaluator = CachedEvaluator(config, counting_eval, logger)
        self.assertIn("Stored evaluations: 1 designs", out.getvalue())  # 격자 밖(3.2) 기록은 건너뜀
        score, _ = evaluator.evaluate(np.array([10.0, 20.0, 25.0, 10.0, 12.0]))
        self.assertEqual(score, 1234.0)
        evaluator.evaluate(np.array([10.0, 10.0, 12.0, 20.0, 25.0]))  # 같은 설계: 이제 캐시 적중
        results = evaluator.evaluate_batch([np.array([11.0, 10.0, 12.0, 20.0, 25.0]), stored.copy()])
        logger.close()
        self.assertEqual(len(calls), 1)
        self.assertEqual(results[1][0], 1234.0)
        self.assertEqual(
            evaluator.stats(),
            {"unique_evals": 1, "physics_evals": 1, "penalty_evals": 0, "cache_hits": 2, "stored_hits": 1},
        )
        with open(logger.trial_path, newline="") as f:
            self.assertEqual(len(list(csv.reader(f))) - 1, 2)  # 저장 기록 1 + 새 평가 1

    def test_batch_uses_store_once_per_design(self):
        stored = np.array([10.0, 10.0, 12.0, 20.0, 25.0])
        self._db([(stored, 500.0, [100.0] * 5, False)])
        config = {**CONFIG, "eval_cache": True, "eval_db_dir": "db", "workers": 2}
        logger = OptimizationLogger(config, algorithm="test")
        with contextlib.redirect_stdout(io.StringIO()):
            evaluator = CachedEvaluator(config, fake_eval, logger)
            seen = []
            results = evaluator.evaluate_batch([stored.copy(), stored.copy()], on_result=seen.append)
        logger.close()
        self.assertEqual([r[0] for r in results], [500.0, 500.0])
        self.assertEqual(seen, [500.0, 500.0])
        self.assertEqual((evaluator.stored_hits, evaluator.cache_hits, evaluator.total_evals), (1, 1, 0))

    def test_de_with_full_store_runs_no_new_evaluation(self):
        """첫 실행 기록으로 데이터베이스를 만들면, 같은 시드의 두 번째 실행은 평가 함수를 한 번도 부르지 않음."""
        with contextlib.redirect_stdout(io.StringIO()):
            np.random.seed(5)
            best_x, best_f = run_de(CONFIG, fake_eval, pop_size=8, max_iter=5, F=0.5, CR=0.9)
            build.main(["logs", "--db-dir", "db"])

            def must_not_run(vector, config):
                raise AssertionError("eval_func called")

            np.random.seed(5)
            best_x2, best_f2 = run_de({**CONFIG, "eval_cache": True, "eval_db_dir": "db"}, must_not_run, 8, 5, 0.5, 0.9)
        self.assertEqual(best_f, best_f2)
        np.testing.assert_array_equal(best_x, best_x2)


class TestBuild(InTempDir):
    def _run_log(self, name, rows, config=CONFIG):
        os.makedirs("logs", exist_ok=True)
        with open(f"logs/{name}_config.json", "w") as f:
            json.dump(config, f)
        with open(f"logs/{name}_trial_history.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["v1", "v2", "v3", "v4", "v5", "fitness", "p1", "p2", "p3", "p4", "p5", "penalized"])
            for v, fit in rows:
                w.writerow([*v, fit, *([fit / 5] * 5), int(fit < 0)])

    def test_merges_runs_keeps_stored_value_and_skips_unknown_settings(self):
        a = [10.0, 10.0, 12.0, 20.0, 25.0]
        b = [12.0, 10.0, 12.0, 20.0, 25.0]
        self._run_log("Dummy_de_1", [(a, 900.0), (b, -5.0)])
        self._run_log("Dummy_de_2", [(a, 950.0), ([14.0, 10.0, 12.0, 20.0, 25.0], 800.0)])
        self._run_log("Old_de_1", [(a, 1.0)], config={k: v for k, v in CONFIG.items() if k != "freq_grid"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            build.main(["logs", "--db-dir", "db"])
        self.assertIn("1 conflicting values", out.getvalue())
        self.assertIn("skipped 1 runs", out.getvalue())
        rows, path = eval_db.load_for(CONFIG, "db")
        values = {tuple(v): f for v, f, _, _ in rows}
        self.assertEqual(len(rows), 3)
        self.assertEqual(values[tuple(a)], 900.0)
        self.assertTrue(any(p for *_, p in rows))  # 간격 위반 기록도 저장
        with open(os.path.splitext(path)[0] + ".json") as f:
            self.assertEqual(json.load(f)["physics_evals"], 2)


if __name__ == "__main__":
    unittest.main()
