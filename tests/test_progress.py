"""세대 진행 막대(src/algorithms/progress.py)와 evaluate_batch의 on_result 테스트 (WAMIT 없이 실행)."""

import contextlib
import io
import os
import re
import tempfile
import unittest
from unittest import mock

import numpy as np

from src.algorithms import progress as progress_module
from src.algorithms import run_cma_es, run_de, run_depso, run_ga, run_pso
from src.algorithms.common import CachedEvaluator
from src.algorithms.progress import GenerationProgress, format_seconds


class Stats:
    physics_evals, cache_hits, penalty_evals = 436, 7, 140


class Terminal(io.StringIO):
    """터미널처럼 보이는 출력 (isatty True, UTF-8)."""

    encoding = "utf-8"

    def isatty(self):
        return True


class NullLogger:
    def write_trial(self, *args, **kwargs):
        pass


def run_generation(progress, gen, scores, best_before, best_after):
    progress.start(gen, len(scores), best_before)
    for s in scores:
        progress.advance(s)
    progress.finish(best_after, Stats())


class TestGenerationProgress(unittest.TestCase):
    def test_lines_keep_the_same_columns_for_one_to_three_digit_generations(self):
        out = io.StringIO()
        progress = GenerationProgress(300, 72, stream=out, live=False)
        run_generation(progress, 0, [1.0e4] * 72, -np.inf, 1.0e4)
        for gen in (1, 9, 10, 99, 100, 300):
            run_generation(progress, gen, [2.0e4] * 72, 1.0e4, 3.16645e4 if gen == 9 else 1.0e4)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 7)
        self.assertEqual(len({len(line) for line in lines}), 1, lines)
        self.assertEqual(len({line.index("[") for line in lines}), 1)
        self.assertEqual(len({line.index("| Best") for line in lines}), 1)
        self.assertTrue(lines[0].startswith("Init "))
        self.assertTrue(lines[1].startswith("Gen   1/300 ["))
        self.assertTrue(lines[-1].startswith("Gen 300/300 ["))
        self.assertIn("[####################] 100% 72/72", lines[1])
        self.assertIn("Best   31.6645 kW +", lines[2])  # 9세대에서 개선
        self.assertIn("Best   10.0000 kW   ", lines[3])
        self.assertIn("WAMIT   436  Hits     7  Penalty   140", lines[1])
        self.assertNotIn("\r", out.getvalue())
        out.getvalue().encode("ascii")  # 파일 출력은 ASCII만 씀

    def test_file_output_writes_only_the_finished_line(self):
        out = io.StringIO()
        progress = GenerationProgress(5, 4, stream=out)  # StringIO는 터미널이 아님
        progress.start(1, 4)
        progress.advance(1.0)
        progress.advance(2.0)
        self.assertEqual(out.getvalue(), "")
        progress.advance(3.0)
        progress.advance(4.0)
        progress.finish(4.0)
        self.assertEqual(out.getvalue().count("\n"), 1)

    @mock.patch.object(progress_module, "REFRESH_SECONDS", 0.0)
    def test_terminal_redraws_the_same_line_per_individual(self):
        out = Terminal()
        progress = GenerationProgress(300, 72, stream=out)
        self.assertTrue(progress.live)
        progress.start(7, 72, 3.0e4)
        for k in range(72):
            progress.advance(3.0e4 + (k == 40) * 1664.5)
            if k == 36:
                partial = out.getvalue().rsplit("\r", 1)[-1]
        progress.finish(3.16645e4, Stats())
        text = out.getvalue()
        self.assertIn("\r", text)
        self.assertEqual(text.count("\n"), 1)
        self.assertTrue(text.endswith("\n"))
        self.assertRegex(partial, r"^Gen   7/300 \[█+[ ▏▎▍▌▋▊▉]* *\]  51% 37/72 \| Best   30\.0000 kW")
        final = text.rsplit("\r", 1)[-1]
        self.assertIn("[████████████████████] 100% 72/72 | Best   31.6645 kW ▲", final)

    def test_terminal_without_unicode_falls_back_to_ascii(self):
        out = Terminal()
        out.encoding = "cp949"  # 한국어 콘솔의 옛 코드 페이지: 1/8 블록 문자가 없음
        progress = GenerationProgress(10, 4, stream=out)
        run_generation(progress, 1, [1.0, 2.0, 3.0, 4.0], 0.0, 4.0)
        self.assertIn("[####################] 100% 4/4", out.getvalue())
        self.assertIn("kW +", out.getvalue())

    def test_percent_rounds_down_until_the_generation_is_done(self):
        progress = GenerationProgress(300, 72, stream=io.StringIO(), live=False)
        progress.start(1, 72)
        for _ in range(71):
            progress.advance(1.0)
        self.assertIn("  98% 71/72", progress._line())

    def test_format_seconds(self):
        self.assertEqual(format_seconds(0), " 0:00")
        self.assertEqual(format_seconds(483.4), " 8:03")
        self.assertEqual(format_seconds(3725), "1:02:05")


class TestEvaluateBatchCallback(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_called_once_per_vector_with_cache_hits_and_repeats(self):
        for workers in (1, 2):
            config = {
                "dimensions": 2,
                "bounds": [[0.0, 0.0], [10.0, 10.0]],
                "step_size": [1.0, 1.0],
                "opt_mode": 1,
                "num_wecs": 1,
                "workers": workers,
                "workspace_dir": os.path.join(self._tmp.name, f"ws{workers}"),
            }
            evaluator = CachedEvaluator(config, lambda v, cfg: (float(v.sum()), [0.0]), NullLogger())
            evaluator.evaluate(np.array([1.0, 1.0]))
            seen = []
            vectors = [np.array(v) for v in ([1.0, 1.0], [2.0, 3.0], [4.0, 4.0], [2.0, 3.0])]
            results = evaluator.evaluate_batch(vectors, on_result=seen.append)
            self.assertEqual(sorted(seen), sorted(r[0] for r in results), workers)
            self.assertEqual(seen[0], 2.0)  # 이미 캐시에 있던 설계가 먼저 끝남


class TestAlgorithmsPrintOneLinePerGeneration(unittest.TestCase):
    def test_each_algorithm(self):
        config = {
            "dimensions": 3,
            "bounds": [[0.0] * 3, [10.0] * 3],
            "step_size": [0.5] * 3,
            "opt_mode": 1,
            "num_wecs": 1,
            "site_name": "Dummy",
        }

        def evaluate(vector, cfg):
            return -float(np.sum((vector - 3.5) ** 2)), [0.0]

        runs = {
            "de": lambda: run_de(config, evaluate, 6, 3, 0.5, 0.9),
            "pso": lambda: run_pso(config, evaluate, 6, 3),
            "depso": lambda: run_depso(config, evaluate, 6, 3),
            "ga": lambda: run_ga(config, evaluate, 6, 3),
            "cmaes": lambda: run_cma_es(config, evaluate, 6, 3),
        }
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                for name, run in runs.items():
                    np.random.seed(0)
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        run()
                    lines = [line for line in out.getvalue().splitlines() if re.match(r"^(Init|Gen )", line)]
                    expected = ["Gen 1/3", "Gen 2/3", "Gen 3/3"] if name == "cmaes" else ["Init", "Gen 1/3"]
                    for label in expected:
                        self.assertTrue(any(line.startswith(label) for line in lines), (name, lines))
                    self.assertEqual(len(lines), 3 if name == "cmaes" else 4, name)
                    self.assertTrue(all("100%" in line and "WAMIT" in line for line in lines), name)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
