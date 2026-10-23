"""WAMIT 동시 실행(Workers)과 묶음 평가(evaluate_batch) 테스트 (WAMIT 없이 실행)."""

import contextlib
import io
import os
import tempfile
import threading
import time
import unittest

import numpy as np

from src.algorithms import run_cma_es, run_de, run_depso, run_ga, run_pso
from src.algorithms.common import CachedEvaluator


def config(workers=1, dims=4):
    return {
        "dimensions": dims,
        "bounds": [[0.0] * dims, [10.0] * dims],
        "step_size": [0.5] * dims,
        "opt_mode": 1,
        "num_wecs": 1,
        "site_name": "Dummy",
        "workers": workers,
    }


def score(vector):
    return -float(np.sum((np.asarray(vector) - 3.5) ** 2))


class RecordingLogger:
    def __init__(self):
        self.trials = []

    def write_trial(self, vector, score, powers, penalized=False):
        self.trials.append((tuple(vector), score, penalized))


class InTempDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()


class TestEvaluateBatch(InTempDir):
    VECTORS = ((1.0, 2.0, 3.0, 4.0), (1.2, 2.0, 3.0, 4.0), (5.0, 5.0, 5.0, 5.0), (1.0, 2.0, 3.0, 4.0))

    def _evaluate(self, workers, batch):
        logger = RecordingLogger()

        def evaluate(vector, cfg):
            return score(vector), [0.0], ({"penalized": True} if vector[0] > 4 else {})

        evaluator = CachedEvaluator(config(workers), evaluate, logger)
        evaluator.evaluate(np.array([5.0, 5.0, 5.0, 5.0]))  # already cached before the batch
        vectors = [np.array(v) for v in self.VECTORS]
        results = evaluator.evaluate_batch(vectors) if batch else [evaluator.evaluate(v) for v in vectors]
        return results, logger.trials, evaluator.stats(), [tuple(v) for v in vectors]

    def test_batch_equals_one_by_one(self):
        serial = self._evaluate(1, batch=False)
        for workers in (1, 3):
            self.assertEqual(self._evaluate(workers, batch=True), serial, workers)
        _, _, stats, vectors = serial
        self.assertEqual(stats["cache_hits"], 3)  # 1.2 snaps to 1.0, the 5.0 point and the repeat
        self.assertEqual(stats["unique_evals"], 2)
        self.assertEqual(stats["penalty_evals"], 1)
        self.assertEqual(vectors[1], (1.0, 2.0, 3.0, 4.0))  # snapped in place as before

    def test_runs_overlap_in_separate_workspaces(self):
        seen, active, peak = [], [0], [0]
        lock = threading.Lock()

        def slow(vector, cfg):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                seen.append(cfg["workspace_dir"])
            time.sleep(0.2)
            with lock:
                active[0] -= 1
            return score(vector), [0.0]

        evaluator = CachedEvaluator({**config(3), "workspace_dir": "ws"}, slow, RecordingLogger())
        start = time.time()
        evaluator.evaluate_batch([np.full(4, float(k)) for k in range(6)])
        elapsed = time.time() - start
        self.assertEqual(peak[0], 3)
        self.assertLess(elapsed, 0.2 * 6 * 0.75)
        self.assertEqual(set(seen), {os.path.join("ws", f"w{k}") for k in range(3)})

    def test_single_worker_keeps_the_default_workspace(self):
        seen = []

        def evaluate(vector, cfg):
            seen.append(cfg.get("workspace_dir"))
            return score(vector), [0.0]

        CachedEvaluator(config(1), evaluate, RecordingLogger()).evaluate_batch([np.zeros(4), np.ones(4)])
        self.assertEqual(seen, [None, None])


class TestAlgorithmsWithWorkers(InTempDir):
    def _run(self, runner, workers, **kwargs):
        def evaluate(vector, cfg):
            return score(vector), [0.0]

        np.random.seed(11)
        with contextlib.redirect_stdout(io.StringIO()):
            best_x, best_f = runner(config(workers), evaluate, 10, 12, **kwargs)
        return list(best_x), best_f

    def test_parallel_runs_give_the_same_result(self):
        cases = [
            (run_de, {"F": 0.5, "CR": 0.9}),
            (run_de, {"F": 0.5, "CR": 0.9, "update": "generation"}),
            (run_pso, {}),
            (run_ga, {}),
            (run_cma_es, {}),
            (run_depso, {}),
        ]
        for runner, kwargs in cases:
            self.assertEqual(self._run(runner, 1, **kwargs), self._run(runner, 4, **kwargs), (runner.__name__, kwargs))

    def test_generation_wise_de_differs_and_still_converges(self):
        immediate = self._run(run_de, 1, F=0.5, CR=0.9)
        generation = self._run(run_de, 1, F=0.5, CR=0.9, update="generation")
        self.assertNotEqual(immediate, generation)
        self.assertGreater(generation[1], -5.0)  # random start is around -40
        with self.assertRaises(ValueError):
            self._run(run_de, 1, F=0.5, CR=0.9, update="other")


if __name__ == "__main__":
    unittest.main()
