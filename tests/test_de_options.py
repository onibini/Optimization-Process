"""DE 옵션(변이 전략, 정체 처리, 지역 탐색, 이어 돌리기)과 Seed 테스트 (WAMIT 없이 실행)."""

import contextlib
import csv
import glob
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

import main as main_module
from src.algorithms.common import CachedEvaluator
from src.algorithms.de import read_trial_rows, run_de
from src.algorithms.local_search import compass_search

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "experiments"))
try:
    from de_options_benchmark import VARIANTS, run_task, table
except ImportError:  # 연구용 스크립트(scripts/experiments)는 공개 저장소에 없으므로, 없으면 해당 시험만 건너뜀
    VARIANTS = run_task = table = None


def config(dims=4, step=0.5, high=10.0):
    return {
        "dimensions": dims,
        "bounds": [[0.0] * dims, [high] * dims],
        "step_size": [step] * dims,
        "opt_mode": 1,
        "num_wecs": 1,
        "site_name": "Dummy",
    }


class Counter:
    """평가 함수: 호출 수를 세고, 지정한 횟수에서 멈출 수 있습니다."""

    def __init__(self, stop_after=None):
        self.calls = 0
        self.stop_after = stop_after
        self.seen = []

    def __call__(self, vector, _config):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise KeyboardInterrupt
        self.calls += 1
        self.seen.append(tuple(np.round(vector, 6)))
        # 봉우리가 여럿인 함수 (최댓값은 모든 변수가 7.5일 때)
        value = -float(np.sum((vector - 7.5) ** 2)) + 3.0 * float(np.sum(np.cos(2 * np.pi * vector / 2.5)))
        return value, [value]


def flat(_vector, _config):
    return 1.0, [1.0]


class NullLogger:
    def write_trial(self, vector, score, powers, penalized=False):
        pass


def quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


class InTempDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def summary(self):
        paths = glob.glob("logs/*_summary.json")
        with open(max(paths, key=os.path.getmtime), encoding="utf-8") as f:
            return json.load(f)


class TestSeedAndOptions(unittest.TestCase):
    def test_resolve_seed(self):
        self.assertEqual(main_module.resolve_seed("0"), 0)
        self.assertEqual(main_module.resolve_seed("123"), 123)
        drawn = main_module.resolve_seed("-1")
        self.assertTrue(0 <= drawn <= main_module.MAX_SEED)
        for bad in ("-2", str(main_module.MAX_SEED + 1)):
            with self.assertRaises(ValueError):
                main_module.resolve_seed(bad)

    def test_defaults_are_the_paper_behaviour(self):
        self.assertEqual(
            main_module.read_de_options({}),
            {
                "strategy": "rand1",
                "stall_gens": 0,
                "stall_action": "stop",
                "local_search_evals": 0,
                "resume": None,
            },
        )

    def test_values_and_errors(self):
        options = main_module.read_de_options(
            {"DEStrategy": "1", "StallGens": "30", "StallAction": "1", "LocalSearchEvals": "200", "Resume": "a.json"}
        )
        self.assertEqual(options["strategy"], "current-to-best1")
        self.assertEqual(options["stall_action"], "restart")
        self.assertEqual(options["resume"], "a.json")
        for key, value in (
            ("DEStrategy", "2"),
            ("StallGens", "-1"),
            ("StallAction", "2"),
            ("LocalSearchEvals", "-1"),
        ):
            with self.assertRaises(ValueError):
                main_module.read_de_options({key: value})


class TestDeOptions(InTempDir):
    def _de(self, seed=5, pop=8, gens=12, evaluate=None, **kwargs):
        np.random.seed(seed)
        evaluate = evaluate or Counter()
        return quiet(run_de, config(), evaluate, pop, gens, 0.5, 0.9, **kwargs), evaluate

    def test_same_seed_gives_same_designs(self):
        (x1, f1), e1 = self._de()
        (x2, f2), e2 = self._de()
        self.assertEqual(e1.seen, e2.seen)
        self.assertEqual(f1, f2)
        np.testing.assert_array_equal(x1, x2)

    def test_summary_records_seed_and_settings(self):
        np.random.seed(77)
        quiet(run_de, {**config(), "seed": 77}, Counter(), 6, 2, 0.5, 0.9)
        summary = self.summary()
        self.assertEqual(summary["seed"], 77)
        self.assertEqual(summary["de_settings"]["strategy"], "rand1")
        self.assertEqual(summary["restarts"], 0)
        self.assertIsNone(summary["local_search"])

    def test_current_to_best_runs_and_rejects_unknown_strategy(self):
        (_, f), _ = self._de(strategy="current-to-best1")
        self.assertTrue(np.isfinite(f))
        with self.assertRaises(ValueError):
            self._de(strategy="nope")

    def test_stall_stop_ends_early(self):
        # 설계가 9개뿐이라 곧 새 설계가 없어짐
        np.random.seed(5)
        quiet(run_de, config(dims=2, high=1.0), flat, 8, 50, 0.5, 0.9, stall_gens=3, stall_action="stop")
        self.assertLess(self.summary()["generations_completed"], 50)

    def test_no_improvement_alone_is_not_a_stall(self):
        # 최고값이 그대로여도 새 설계가 계속 나오면 끝내지 않음
        self._de(gens=10, evaluate=flat, stall_gens=3, stall_action="stop")
        self.assertEqual(self.summary()["generations_completed"], 10)

    def test_stall_restart_runs_to_max_iter_and_keeps_best(self):
        (_, f0), _ = self._de(gens=5)
        (_, f), _ = self._de(gens=60, stall_gens=2, stall_action="restart")
        summary = self.summary()
        self.assertEqual(summary["generations_completed"], 60)
        self.assertGreater(summary["restarts"], 0)
        self.assertGreaterEqual(f, f0)

    def test_no_restart_on_the_last_generation(self):
        np.random.seed(1)
        quiet(run_de, config(dims=1, high=0.5), flat, 4, 2, 0.5, 0.9, stall_gens=2, stall_action="restart")
        self.assertEqual(self.summary()["restarts"], 0)

    def test_local_search_improves_and_is_recorded(self):
        (_, f_plain), _ = self._de(seed=3, pop=4, gens=1)
        (x, f), _ = self._de(seed=3, pop=4, gens=1, local_search_evals=100)
        self.assertGreater(f, f_plain)
        summary = self.summary()
        info = summary["local_search"]
        self.assertEqual(info["start_fitness"], f_plain)
        self.assertEqual(info["end_fitness"], f)
        self.assertLessEqual(info["physics_evals"], 100)
        self.assertEqual(summary["best_vector"], list(x))


class TestCompassSearch(unittest.TestCase):
    def _search(self, start, max_evals, evaluate=None):
        cfg = config()
        evaluate = evaluate or (lambda v, _c: (-float(np.sum((v - 7.5) ** 2)), [0.0]))
        evaluator = CachedEvaluator(cfg, evaluate, NullLogger())
        start = np.array(start, dtype=float)
        f0, p0 = evaluator.evaluate(start.copy())
        return compass_search(start, f0, p0, evaluator, cfg, max_evals), evaluator

    def test_reaches_the_peak_of_a_smooth_function(self):
        (x, f, _, info), _ = self._search([0.0, 10.0, 0.5, 3.0], 1000)
        np.testing.assert_allclose(x, [7.5] * 4)
        self.assertEqual(f, 0.0)
        self.assertTrue(info["finished"])

    def test_budget_is_not_exceeded(self):
        for budget in (1, 5, 7):
            (_, _, _, info), evaluator = self._search([0.0] * 4, budget)
            self.assertLessEqual(info["physics_evals"], budget)
            self.assertFalse(info["finished"])
            self.assertEqual(evaluator.physics_evals, info["physics_evals"] + 1)

    def test_finds_a_far_single_variable_move(self):
        # 한 변수만 멀리 옮겨야 좋아지는 경우 (한 칸씩 옮기면 값이 나빠짐)
        def trap(vector, _config):
            value = -float(np.sum((vector[1:] - 5.0) ** 2))
            value += 10.0 if vector[0] <= 1.0 else -((float(vector[0]) - 6.0) ** 2)
            return value, [0.0]

        (x, _, _, _), _ = self._search([6.0, 5.0, 5.0, 5.0], 200, evaluate=trap)
        self.assertLessEqual(x[0], 1.0)

    def test_stays_on_grid_and_in_bounds(self):
        seen = []

        def evaluate(vector, _config):
            seen.append(vector.copy())
            return float(np.sum(vector)), [0.0]

        (x, _, _, _), _ = self._search([9.5, 0.0, 0.0, 0.0], 100, evaluate=evaluate)
        np.testing.assert_allclose(x, [10.0] * 4)
        values = np.array(seen)
        self.assertTrue(np.all(values >= 0) and np.all(values <= 10))
        np.testing.assert_allclose(values / 0.5, np.round(values / 0.5))


class TestResume(InTempDir):
    def _checkpoint(self):
        return max(glob.glob("logs/*_checkpoint.json"), key=os.path.getmtime)

    def _interrupted(self, stop_after, seed=9, **kwargs):
        np.random.seed(seed)
        with self.assertRaises(KeyboardInterrupt):
            quiet(run_de, config(), Counter(stop_after), 8, 20, 0.5, 0.9, **kwargs)
        return self._checkpoint()

    def _full(self, seed=9, **kwargs):
        np.random.seed(seed)
        evaluate = Counter()
        return quiet(run_de, config(), evaluate, 8, 20, 0.5, 0.9, **kwargs), evaluate

    def test_resume_matches_an_uninterrupted_run(self):
        for kwargs in ({}, {"stall_gens": 3, "stall_action": "restart"}):
            with self.subTest(kwargs=kwargs):
                (x_full, f_full), full = self._full(**kwargs)
                checkpoint = self._interrupted(min(40, full.calls - 1), **kwargs)
                np.random.seed(123)  # 이어 돌리면 체크포인트의 난수 상태로 돌아가야 함
                x, f = quiet(run_de, config(), Counter(), 8, 20, 0.5, 0.9, resume=checkpoint, **kwargs)
                self.assertEqual(f, f_full)
                np.testing.assert_array_equal(x, x_full)
                summary = self.summary()
                self.assertEqual(summary["resumed_from"], checkpoint)
                self.assertEqual(summary["generations_completed"], 20)

    def test_resume_after_a_restart_matches(self):
        # 설계가 적어 금방 수렴하고 재시작이 일어나는 문제. 재시작 뒤에 끊어도 같은 결과여야 함
        cfg = config(dims=3, high=2.0)
        options = {"stall_gens": 2, "stall_action": "restart"}
        np.random.seed(4)
        full = Counter()
        x_full, f_full = quiet(run_de, cfg, full, 8, 60, 0.5, 0.9, **options)
        restarts = self.summary()["restarts"]
        self.assertGreater(restarts, 0)
        np.random.seed(4)
        with self.assertRaises(KeyboardInterrupt):
            quiet(run_de, cfg, Counter(full.calls - 1), 8, 60, 0.5, 0.9, **options)
        x, f = quiet(run_de, cfg, Counter(), 8, 60, 0.5, 0.9, resume=self._checkpoint(), **options)
        self.assertEqual(f, f_full)
        np.testing.assert_array_equal(x, x_full)
        self.assertEqual(self.summary()["restarts"], restarts)

    def test_resume_does_not_repeat_recorded_evaluations(self):
        _, full = self._full()
        stop = min(40, full.calls - 1)
        checkpoint = self._interrupted(stop)
        evaluate = Counter()
        quiet(run_de, config(), evaluate, 8, 20, 0.5, 0.9, resume=checkpoint)
        self.assertEqual(evaluate.calls, full.calls - stop)

    def test_second_resume_still_sees_the_first_records(self):
        (_, f_full), full = self._full()
        stop = min(30, full.calls - 2)
        first = self._interrupted(stop)
        with self.assertRaises(KeyboardInterrupt):
            quiet(run_de, config(), Counter(1), 8, 20, 0.5, 0.9, resume=first)
        evaluate = Counter()
        _, f = quiet(run_de, config(), evaluate, 8, 20, 0.5, 0.9, resume=self._checkpoint())
        self.assertEqual(f, f_full)
        self.assertEqual(evaluate.calls, full.calls - stop - 1)

    def test_more_generations_can_be_added(self):
        checkpoint = self._interrupted(30)
        quiet(run_de, config(), Counter(), 8, 25, 0.5, 0.9, resume=checkpoint)
        self.assertEqual(self.summary()["generations_completed"], 25)

    def test_changed_settings_are_rejected(self):
        checkpoint = self._interrupted(30)
        with self.assertRaisesRegex(ValueError, "CR"):
            quiet(run_de, config(), Counter(), 8, 20, 0.5, 0.8, resume=checkpoint)
        with self.assertRaisesRegex(ValueError, "pop_size"):
            quiet(run_de, config(), Counter(), 10, 20, 0.5, 0.9, resume=checkpoint)
        with self.assertRaisesRegex(ValueError, "bounds"):
            quiet(run_de, config(high=20.0), Counter(), 8, 20, 0.5, 0.9, resume=checkpoint)

    def test_cut_off_trial_line_is_skipped(self):
        with open("trial.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["v1", "v2", "fitness", "p1", "penalized"])
            writer.writerow([1.0, 2.0, 3.0, 3.0, 0])
            writer.writerow([1.5, 2.0, -9.0, 0.0, 1])
            f.write("2.0,2.5,3.")
        self.assertEqual(
            read_trial_rows("trial.csv"),
            [([1.0, 2.0], 3.0, [3.0], False), ([1.5, 2.0], -9.0, [0.0], True)],
        )


class TestMainWiring(InTempDir):
    """config.cfg의 값이 main을 거쳐 실제로 쓰이는지 확인합니다 (평가 함수만 가짜로 바꿈)."""

    def _main(self, **values):
        os.makedirs("data", exist_ok=True)
        shutil.copy(os.path.join(ROOT, "data", "env_data.csv"), os.path.join("data", "env_data.csv"))
        with open(os.path.join(ROOT, "config.cfg"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        # 평가 함수가 가짜이므로 해석기는 상관없다. HydroBEM이 없는 환경(CI)에서도 돌도록 WAMIT으로 둔다.
        values = {"PopSize": 6, "MaxIter": 3, "HydroSolver": 1, **values}
        for k, line in enumerate(lines):
            tokens = line.split()
            if len(tokens) >= 2 and not line.startswith("#") and tokens[1] in values:
                lines[k] = f"{values[tokens[1]]}  {tokens[1]}  - test"
        with open("test.cfg", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        with mock.patch.object(main_module, "evaluate_shape", Counter()):
            return quiet(main_module.main, "test.cfg")

    def test_seed_and_options_reach_the_run(self):
        x1, f1 = self._main(Seed=42)
        self.assertEqual(self.summary()["seed"], 42)
        x2, f2 = self._main(Seed=42, LocalSearchEvals=0)
        np.testing.assert_array_equal(x1, x2)
        self.assertEqual(f1, f2)

        self._main(Seed=42, DEStrategy=1, StallGens=1, StallAction=1, LocalSearchEvals=5)
        summary = self.summary()
        self.assertEqual(summary["de_settings"]["strategy"], "current-to-best1")
        self.assertEqual(summary["de_settings"]["stall_action"], "restart")
        self.assertLessEqual(summary["local_search"]["physics_evals"], 5)

    def test_drawn_seed_is_recorded(self):
        self._main(Seed=-1)
        self.assertGreaterEqual(self.summary()["seed"], 0)

    def test_resume_through_the_config_file(self):
        self._main(Seed=42, MaxIter=2)
        checkpoint = max(glob.glob("logs/*_checkpoint.json"), key=os.path.getmtime)
        self._main(Seed=42, MaxIter=4, Resume=checkpoint.replace(os.sep, "/"))
        summary = self.summary()
        self.assertEqual(summary["generations_completed"], 4)
        self.assertIn("checkpoint.json", summary["resumed_from"])

    def test_missing_resume_file_stops_with_an_error(self):
        with self.assertRaises(SystemExit):
            self._main(Resume="missing.json")


@unittest.skipIf(VARIANTS is None, "research scripts are not in this copy")
class TestBenchmarkScript(InTempDir):
    def test_one_run_of_each_variant(self):
        for variant in VARIANTS:
            row = run_task(("sphere", variant, 3, 0, 8, 3, 50))
            self.assertEqual(row["variant"], variant)
            self.assertGreaterEqual(row["best_f"], 0.0)
            self.assertGreater(row["evals"], 0)
        self.assertEqual(len(table([row])), 1)


if __name__ == "__main__":
    unittest.main()
