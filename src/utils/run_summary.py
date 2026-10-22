"""``results/<작업ID>/`` 폴더들을 읽어 실행별 한 줄짜리 요약 표(summary.csv)를 만듭니다.

각 작업 폴더에는 ``scripts/remote.ps1`` 이 남긴 ``job.json``, ``config.cfg`` 와 계산용 PC에서 가져온
``status.json``, ``logs/*_summary.json`` 이 들어 있습니다. 없는 파일은 빈 칸으로 둡니다.
"""

import csv
import glob
import json
import os
from datetime import datetime

from .config_parser import parse_wec_cfg

COLUMNS = [
    "job_id",
    "state",
    "git_commit",
    "git_dirty",
    "duration_min",
    "site_id",
    "opt_mode",
    "algorithm",
    "num_wecs",
    "pop_size",
    "max_iter",
    "mesh_panels",
    "solver",
    "omega_max",
    "best_kw",
    "physics_evals",
    "cache_hits",
    "best_vector",
]


def _read_json(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _duration_min(status):
    try:
        start = datetime.fromisoformat(status["started"])
        end = datetime.fromisoformat(status["finished"])
    except (KeyError, ValueError):
        return ""
    return round((end - start).total_seconds() / 60, 1)


def summarize_job(job_dir):
    """작업 폴더 하나를 요약 딕셔너리(COLUMNS 키)로 만듭니다."""
    job = _read_json(os.path.join(job_dir, "job.json"))
    status = _read_json(os.path.join(job_dir, "status.json"))
    summaries = sorted(glob.glob(os.path.join(job_dir, "logs", "*_summary.json")))
    summary = _read_json(summaries[-1]) if summaries else {}

    row = dict.fromkeys(COLUMNS, "")
    row["job_id"] = job.get("job_id") or os.path.basename(os.path.normpath(job_dir))
    row["state"] = status.get("state", "")
    row["git_commit"] = job.get("git_commit", "")
    row["git_dirty"] = job.get("git_dirty", "")
    row["duration_min"] = _duration_min(status)

    cfg_path = os.path.join(job_dir, "config.cfg")
    if os.path.isfile(cfg_path):
        cfg = parse_wec_cfg(cfg_path)
        sim, algo, wamit = cfg.get("Simulation", {}), cfg.get("AlgorithmSettings", {}), cfg.get("WAMIT Settings", {})
        row["site_id"] = cfg.get("Environment", {}).get("SiteID", "")
        row["opt_mode"] = sim.get("OptMode", "")
        row["algorithm"] = sim.get("Algorithm", "")
        row["num_wecs"] = cfg.get("WEC Parameters", {}).get("NumWECs", "")
        row["pop_size"] = algo.get("PopSize", "")
        row["max_iter"] = algo.get("MaxIter", "")
        row["mesh_panels"] = wamit.get("MeshPanels", "")
        row["solver"] = wamit.get("Solver", "")
        row["omega_max"] = wamit.get("OmegaMax", "")

    if "best_fitness" in summary:
        row["best_kw"] = round(summary["best_fitness"] / 1000, 4)
    row["physics_evals"] = summary.get("physics_evals", "")
    row["cache_hits"] = summary.get("cache_hits", "")
    if "best_vector" in summary:
        row["best_vector"] = json.dumps([round(v, 6) for v in summary["best_vector"]])
    return row


def collect_rows(results_dir):
    """``results_dir`` 아래 모든 작업 폴더를 이름순으로 요약합니다."""
    rows = []
    for name in sorted(os.listdir(results_dir)):
        path = os.path.join(results_dir, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "job.json")):
            rows.append(summarize_job(path))
    return rows


def write_summary_csv(results_dir):
    """``results_dir/summary.csv`` 를 (다시) 만들고 경로와 행 수를 반환합니다."""
    rows = collect_rows(results_dir)
    out_path = os.path.join(results_dir, "summary.csv")
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel에서 바로 열림
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return out_path, len(rows)
