"""Measure the throughput of several WAMIT runs at the same time (``Workers``) against the cores per run (``NCPU``).

The same set of 5-WEC joint designs (random, feasible, fixed by ``--seed``) is evaluated with each ``Workers x NCPU``
combination through ``CachedEvaluator.evaluate_batch`` -- the path the optimizers use -- and the wall time is recorded.
The powers of every combination are compared with the first one (they should agree; NCPU does not change the
physics).

Run on the compute PC (WAMIT is needed, nothing else should be running)::

    python scripts/experiments/parallel_wamit_bench.py                       # 1x8, 2x4, 4x2, 8x1, 24 designs
    python scripts/experiments/parallel_wamit_bench.py --combos 1x8 2x4 --designs 16

Results: ``logs/parallel_wamit_bench.csv``.
"""

import argparse
import csv
import os
import shutil
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.algorithms.common import CachedEvaluator, random_grid_population  # noqa: E402
from src.problems import evaluate_joint, get_joint_config  # noqa: E402
from src.utils import check_min_distance, decode_symmetric_positions  # noqa: E402
from src.utils.config_parser import parse_wec_cfg  # noqa: E402
from src.utils.data_handler import load_env_data  # noqa: E402

FIELDS = ["workers", "ncpu", "designs", "wall_s", "s_per_design", "speedup", "max_power_diff_pct"]


class _NoLogger:
    def write_trial(self, *args, **kwargs):
        pass


def build_config(cfg, workers, ncpu, workspace):
    wamit = cfg["WAMIT Settings"]
    wamit_data = {
        "NCPU": ncpu,
        "RAMGBMAX": int(wamit["RAMGBMAX"]),
        "WAMITPath": wamit.get("WAMITPath"),
        "MeshPanels": int(wamit.get("MeshPanels", 120)),
        "Solver": int(wamit.get("Solver", 0)),
        "OmegaMax": float(wamit.get("OmegaMax", 3.0)),
        "FreqGrid": int(wamit.get("FreqGrid", 0)),
        "Workers": workers,
    }
    env = load_env_data(int(cfg["Environment"]["SiteID"]), os.path.join(ROOT, "data", "env_data.csv"))
    config = get_joint_config(
        cfg["Constraints"], cfg["WEC Parameters"], 5, env, wamit_data, int(cfg["Simulation"]["WaveSpec"])
    )
    config["workspace_dir"] = workspace
    return config


def feasible_designs(config, count, seed):
    np.random.seed(seed)
    designs = []
    while len(designs) < count:
        for vector in random_grid_population(4 * count, config):
            positions = decode_symmetric_positions(vector[2:], 5)
            if check_min_distance(positions, vector[0], config["min_spacing"]) == 0 and len(designs) < count:
                designs.append(vector)
    return designs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--combos", nargs="+", default=["1x8", "2x4", "4x2", "8x1"], help="WORKERSxNCPU")
    parser.add_argument("--designs", type=int, default=24)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--config", default=os.path.join(ROOT, "config.cfg"))
    parser.add_argument("--out", default="logs")
    args = parser.parse_args(argv)

    cfg = parse_wec_cfg(args.config)
    os.makedirs(args.out, exist_ok=True)
    reference, base_time, rows = None, None, []
    with open(os.path.join(args.out, "parallel_wamit_bench.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for combo in args.combos:
            workers, ncpu = (int(x) for x in combo.lower().split("x"))
            workspace = os.path.join("workspace", f"pb_{workers}x{ncpu}")
            config = build_config(cfg, workers, ncpu, workspace)
            designs = [d.copy() for d in feasible_designs(config, args.designs, args.seed)]
            evaluator = CachedEvaluator(config, evaluate_joint, _NoLogger())
            start = time.time()
            powers = np.array([score for score, _ in evaluator.evaluate_batch(designs)])
            wall = time.time() - start
            shutil.rmtree(workspace, ignore_errors=True)
            if reference is None:
                reference, base_time = powers, wall
            row = {
                "workers": workers,
                "ncpu": ncpu,
                "designs": len(designs),
                "wall_s": round(wall, 1),
                "s_per_design": round(wall / len(designs), 2),
                "speedup": round(base_time / wall, 2) if wall > 0 else float("nan"),
                "max_power_diff_pct": round(float(np.max(np.abs(powers / reference - 1))) * 100, 4),
            }
            writer.writerow(row)
            f.flush()
            rows.append(row)
            print(
                f"{workers} x NCPU {ncpu}: {row['wall_s']} s for {row['designs']} designs "
                f"({row['s_per_design']} s each, speedup {row['speedup']}, power diff {row['max_power_diff_pct']}%)",
                flush=True,
            )
    return rows


if __name__ == "__main__":
    main()
