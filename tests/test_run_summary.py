"""results/ 요약(summary.csv) 테스트 (WAMIT 없이 실행)."""

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.run_summary import COLUMNS, collect_rows, write_summary_csv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_job(results_dir, job_id, best_fitness=12345.0):
    job_dir = os.path.join(results_dir, job_id)
    os.makedirs(os.path.join(job_dir, "logs"))
    with open(os.path.join(job_dir, "job.json"), "w", encoding="utf-8-sig") as f:
        json.dump({"job_id": job_id, "git_commit": "abc1234", "git_dirty": False}, f)
    with open(os.path.join(job_dir, "status.json"), "w", encoding="utf-8-sig") as f:
        json.dump({"state": "done", "started": "2026-10-22T10:00:00", "finished": "2026-10-22T11:30:00"}, f)
    shutil.copy(os.path.join(PROJECT_ROOT, "config.cfg"), os.path.join(job_dir, "config.cfg"))
    summary = {"best_fitness": best_fitness, "best_vector": [1.5, 3.25], "physics_evals": 10, "cache_hits": 2}
    with open(os.path.join(job_dir, "logs", "Site_de_x_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f)


class RunSummaryTest(unittest.TestCase):
    def test_summarize_complete_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_job(tmp, "20261022_100000_a")
            rows = collect_rows(tmp)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["state"], "done")
        self.assertEqual(row["duration_min"], 90.0)
        self.assertEqual(row["best_kw"], 12.345)
        self.assertEqual(row["mesh_panels"], "120")
        self.assertEqual(row["physics_evals"], 10)
        self.assertEqual(json.loads(row["best_vector"]), [1.5, 3.25])

    def test_missing_files_leave_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "j1"))
            with open(os.path.join(tmp, "j1", "job.json"), "w", encoding="utf-8") as f:
                json.dump({"job_id": "j1"}, f)
            rows = collect_rows(tmp)
        self.assertEqual(rows[0]["job_id"], "j1")
        self.assertEqual(rows[0]["best_kw"], "")
        self.assertEqual(rows[0]["state"], "")

    def test_ignores_non_job_folders_and_writes_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_job(tmp, "b_job", best_fitness=2000.0)
            make_job(tmp, "a_job", best_fitness=1000.0)
            os.makedirs(os.path.join(tmp, "not_a_job"))
            path, count = write_summary_csv(tmp)
            self.assertEqual(count, 2)
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = list(csv.DictReader(f))
        self.assertEqual([r["job_id"] for r in reader], ["a_job", "b_job"])
        self.assertEqual(list(reader[0].keys()), COLUMNS)

    def test_script_jobs_show_the_script_and_leave_config_and_result_columns_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = os.path.join(tmp, "20261022_120000_fgrid")
            os.makedirs(os.path.join(job_dir, "logs"))
            with open(os.path.join(job_dir, "job.json"), "w", encoding="utf-8-sig") as f:
                json.dump(
                    {
                        "job_id": "20261022_120000_fgrid",
                        "script": "scripts/experiments/freq_grid_study.py",
                        "script_args": "--study grids --quick",
                    },
                    f,
                )
            with open(os.path.join(job_dir, "status.json"), "w", encoding="utf-8-sig") as f:
                json.dump({"state": "done", "started": "2026-10-22T12:00:00", "finished": "2026-10-22T12:09:00"}, f)
            shutil.copy(os.path.join(PROJECT_ROOT, "config.cfg"), os.path.join(job_dir, "config.cfg"))
            row = collect_rows(tmp)[0]
        self.assertEqual(row["script"], "scripts/experiments/freq_grid_study.py --study grids --quick")
        self.assertEqual(row["state"], "done")
        self.assertEqual(row["duration_min"], 9.0)
        for column in (
            "site_id",
            "opt_mode",
            "algorithm",
            "num_wecs",
            "pop_size",
            "max_iter",
            "mesh_panels",
            "solver",
            "omega_max",
            "freq_grid",
            "best_kw",
        ):
            self.assertEqual(row[column], "", column)

    def test_normal_jobs_have_an_empty_script_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_job(tmp, "20261022_100000_a")
            self.assertEqual(collect_rows(tmp)[0]["script"], "")


if __name__ == "__main__":
    unittest.main()
