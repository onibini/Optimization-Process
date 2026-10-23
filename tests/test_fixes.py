"""버그·위험 수정사항 회귀 테스트 (WAMIT 없이 더미 목적함수로 실행)."""

import glob
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.algorithms import run_cma_es, run_de, run_depso, run_ga, run_pso
from src.algorithms.common import CachedEvaluator, OptimizationLogger
from src.physics.wamit_handler import WamitRunError, run_wamit
from src.utils import PENALTY_FACTOR, check_min_distance, decode_symmetric_positions, penalty_result
from src.utils.config_parser import ConfigParseError, parse_wec_cfg

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class InTempDir(unittest.TestCase):
    """logs/ 가 임시 폴더에 생기도록 작업 디렉토리를 옮겨서 실행."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# 1. config 파서
# ---------------------------------------------------------------------------
class TestConfigParser(InTempDir):
    def _write(self, text):
        with open("test.cfg", "w", encoding="utf-8") as f:
            f.write(text)
        return "test.cfg"

    def test_negative_values_are_parsed(self):
        path = self._write("[Constraints]\n-5.0  WEC1_XMin   - [Float] min x (can be -ve)\n0.1 StepSize\n")
        cfg = parse_wec_cfg(path)
        self.assertEqual(cfg["Constraints"]["WEC1_XMin"], "-5.0")
        self.assertEqual(cfg["Constraints"]["StepSize"], "0.1")

    def test_project_config_parses_all_sections(self):
        cfg = parse_wec_cfg(os.path.join(PROJECT_ROOT, "config.cfg"))
        expected_sections = {
            "Simulation",
            "WEC Parameters",
            "AlgorithmSettings",
            "Constraints",
            "Environment",
            "WAMIT Settings",
        }
        self.assertEqual(set(cfg), expected_sections)
        self.assertEqual(len(cfg["Constraints"]), 15)

    def test_duplicate_key_raises(self):
        path = self._write("[A]\n1 X\n2 X\n")
        with self.assertRaises(ConfigParseError):
            parse_wec_cfg(path)

    def test_value_outside_section_raises(self):
        path = self._write("1 X\n[A]\n")
        with self.assertRaises(ConfigParseError):
            parse_wec_cfg(path)


# ---------------------------------------------------------------------------
# 2. 로그 이름 / 덮어쓰기 / 요약
# ---------------------------------------------------------------------------
LAYOUT5 = {
    "dimensions": 5,
    "bounds": [[3.0, 3.0, 0.5, 3.0, 0.5], [25.0, 25.0, 30.0, 25.0, 30.0]],
    "step_size": 0.5,
    "num_wecs": 5,
    "opt_mode": 2,
    "fixed_radius": 2.5,
    "min_spacing": 4.0,
    "site_name": "Dummy",
}


def dummy_layout_eval(vector, config):
    """간격 제약 + 매끄러운 목적함수. 최적점은 대칭 정렬 기준 [10, 10, 12, 20, 25] 부근."""
    positions = decode_symmetric_positions(vector, config["num_wecs"])
    violation = check_min_distance(positions, config["fixed_radius"], config["min_spacing"])
    if violation > 0:
        return penalty_result(violation, config["num_wecs"])
    target = np.array([10.0, 10.0, 12.0, 20.0, 25.0])
    score = 1000.0 - float(np.sum((np.asarray(vector) - target) ** 2))
    return score, [score / 5] * 5


class TestLogger(InTempDir):
    def test_name_contains_algorithm_and_never_overwrites(self):
        a = OptimizationLogger(LAYOUT5, algorithm="de", run_id="20260101_000000")
        b = OptimizationLogger(LAYOUT5, algorithm="de", run_id="20260101_000000")
        a.close()
        b.close()
        self.assertNotEqual(a.trial_path, b.trial_path)
        self.assertIn("Dummy_de_20260101_000000", a.trial_path)
        self.assertTrue(os.path.exists(a.config_path))

    def test_every_algorithm_writes_distinct_files_and_summary(self):
        np.random.seed(0)
        with redirect_stdout(io.StringIO()):
            run_de(LAYOUT5, dummy_layout_eval, pop_size=8, max_iter=3, F=0.5, CR=0.9)
            run_pso(LAYOUT5, dummy_layout_eval, pop_size=8, max_iter=3)
            run_ga(LAYOUT5, dummy_layout_eval, pop_size=8, max_iter=3)
            run_cma_es(LAYOUT5, dummy_layout_eval, pop_size=8, max_iter=3)
            run_depso(LAYOUT5, dummy_layout_eval, pop_size=8, max_iter=3)
        for algo in ("de", "pso", "ga", "cmaes", "depso"):
            summaries = glob.glob(f"logs/Dummy_{algo}_*_summary.json")
            self.assertEqual(len(summaries), 1, algo)
            with open(summaries[0]) as f:
                summary = json.load(f)
            self.assertEqual(summary["generations_completed"], 3)
            self.assertEqual(summary["unique_evals"], summary["physics_evals"] + summary["penalty_evals"])

    def test_summary_written_even_when_interrupted(self):
        calls = {"n": 0}

        def flaky_eval(vector, config):
            calls["n"] += 1
            if calls["n"] > 20:
                raise KeyboardInterrupt
            return dummy_layout_eval(vector, config)

        np.random.seed(1)
        with redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            run_cma_es(LAYOUT5, flaky_eval, pop_size=8, max_iter=50)
        (summary_path,) = glob.glob("logs/Dummy_cmaes_*_summary.json")
        with open(summary_path) as f:
            summary = json.load(f)
        self.assertLess(summary["generations_completed"], 50)
        self.assertIsNotNone(summary["best_vector"])


# ---------------------------------------------------------------------------
# 3. 패널티 / WAMIT 실행 수 분리 집계
# ---------------------------------------------------------------------------
class TestPenaltyCounting(unittest.TestCase):
    def test_penalty_evals_are_not_counted_as_physics_runs(self):
        class NullLogger:
            def write_trial(self, *args, **kwargs):
                pass

        evaluator = CachedEvaluator(LAYOUT5, dummy_layout_eval, NullLogger())
        score, powers = evaluator.evaluate(np.array([10.0, 10.0, 1.0, 20.0, 25.0]))  # WEC1-WEC2 너무 가까움
        self.assertLess(score, 0)
        self.assertEqual(powers, [0.0] * 5)
        evaluator.evaluate(np.array([10.0, 10.0, 12.0, 20.0, 25.0]))  # feasible
        self.assertEqual(evaluator.total_evals, 2)
        self.assertEqual(evaluator.penalty_evals, 1)
        self.assertEqual(evaluator.physics_evals, 1)

    def test_penalty_scale(self):
        score, _, info = penalty_result(0.5, 3)
        self.assertEqual(score, -0.5 * PENALTY_FACTOR)
        self.assertTrue(info["penalized"])


# ---------------------------------------------------------------------------
# 4. 대칭 정렬과 알고리즘 상태의 일관성 (PSO / CMA-ES)
# ---------------------------------------------------------------------------
class TestCanonicalConsistency(InTempDir):
    def _is_canonical(self, x):
        return (x[1], x[2]) <= (x[3], x[4])

    def test_all_algorithms_return_canonical_best_and_converge(self):
        target = np.array([10.0, 10.0, 12.0, 20.0, 25.0])
        for name, runner, kwargs in [
            ("de", run_de, {"F": 0.5, "CR": 0.9}),
            ("pso", run_pso, {}),
            ("ga", run_ga, {}),
            ("cmaes", run_cma_es, {}),
            ("depso", run_depso, {"F": 0.5, "CR": 0.9}),
        ]:
            np.random.seed(42)
            with redirect_stdout(io.StringIO()):
                best_x, best_f = runner(LAYOUT5, dummy_layout_eval, pop_size=20, max_iter=60, **kwargs)
            self.assertTrue(self._is_canonical(best_x), name)
            self.assertGreater(best_f, 1000.0 - 60.0, f"{name}: best_x={best_x}")
            self.assertLess(np.linalg.norm(best_x - target), 8.0, f"{name}: best_x={best_x}")

    def test_pso_does_not_mutate_particle_order(self):
        """PSO 입자 위치가 평가 중 제자리 정렬되지 않아야 속도 벡터와 짝이 유지됨."""
        seen = []

        def recording_eval(vector, config):
            seen.append(vector.copy())
            return dummy_layout_eval(vector, config)

        np.random.seed(3)
        with redirect_stdout(io.StringIO()):
            run_pso(LAYOUT5, recording_eval, pop_size=10, max_iter=5)
        self.assertTrue(all(self._is_canonical(v) for v in seen))


# ---------------------------------------------------------------------------
# 5. WAMIT 실행 실패 메시지
# ---------------------------------------------------------------------------
@unittest.skipIf(os.name == "nt", "shell-script fake executable is POSIX-only")
class TestRunWamit(InTempDir):
    def _fake_exe(self, body):
        path = os.path.abspath("fake_wamit.sh")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def test_missing_executable(self):
        os.makedirs("ws")
        with self.assertRaises(WamitRunError):
            run_wamit("ws", exe_path="/nonexistent/WAMIT.exe")

    def test_failure_includes_wamit_output(self):
        os.makedirs("ws")
        exe = self._fake_exe("echo 'panel normal error' >&2\necho 'ERROR in GDF' > errorp.log\nexit 3\n")
        with self.assertRaises(WamitRunError) as ctx:
            run_wamit("ws", exe_path=exe)
        msg = str(ctx.exception)
        self.assertIn("code 3", msg)
        self.assertIn("panel normal error", msg)
        self.assertIn("ERROR in GDF", msg)

    def test_stale_outputs_are_removed_before_run(self):
        os.makedirs("ws")
        for name in ("wec.1", "wec.out", "errorp.log"):
            with open(os.path.join("ws", name), "w") as f:
                f.write("stale")
        run_wamit("ws", exe_path=self._fake_exe("exit 0\n"))
        for name in ("wec.1", "wec.out", "errorp.log"):
            self.assertFalse(os.path.exists(os.path.join("ws", name)), name)


if __name__ == "__main__":
    unittest.main()
