"""Compare the WAMIT linear solvers (ISOLVE) on 5-WEC designs: time, power and iteration counts.

For every site, design and mesh the same 5-WEC evaluation (vertical wall, uniform 0.05 rad/s grid) is run with each
``Solver`` value of ``config.cfg`` (0 iterative, 1 direct, N >= 2 block iterative with N blocks). Each combination is
repeated and the shortest wall time is reported. Powers are compared with the direct solver (Solver 1).

Run where WAMIT is installed::

    python scripts/experiments/solver_timing.py
    python scripts/experiments/solver_timing.py --solvers 0 1 --meshes 120 --sites Buan --repeats 1

Results: ``logs/solver_timing.csv`` (one row per run) and a summary table on stdout.
"""

import argparse
import csv
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.problems import evaluate_joint, get_joint_config  # noqa: E402
from src.utils import check_min_distance, decode_symmetric_positions  # noqa: E402
from src.utils.config_parser import parse_wec_cfg  # noqa: E402
from src.utils.data_handler import load_env_data  # noqa: E402

SITE_IDS = {"Buan": 1, "Chilbaldo": 2, "Yeongilmanhang": 3}
# [R, D, X1, X2, Y2, X3, Y3]; every design keeps the 4R minimum spacing
DESIGNS = {
    "paper_buan": [2.5, 3.8, 3.0, 3.0, 13.9, 3.0, 30.0],  # paper DE design, Buan simultaneous
    "cmaes_buan": [2.5, 4.8, 24.8, 3.6, 30.0, 21.9, 30.0],  # CMA-ES (boundary penalty) best, Buan
    "tight_line": [2.5, 5.0, 3.0, 3.0, 10.0, 3.0, 20.0],  # five large WECs at 4R along the wall
    "small_tight": [0.5, 0.5, 3.0, 3.0, 2.0, 3.0, 4.0],  # small shallow WECs at 4R
    "medium": [1.5, 2.5, 10.0, 6.0, 8.0, 15.0, 20.0],
}
FIELDS = [
    "site",
    "design",
    "mesh_panels",
    "solver",
    "repeat",
    "time_s",
    "power_kw",
    "wec_kw",
    "max_iter_rad",
    "max_iter_diff",
]
_ITERATION_ROW = re.compile(r"^\s*(\d+\.\d+)\s+\d{2}:\d{2}:\d{2}\s+(\d+)\s+(\d+)\s*$")


def iteration_counts(out_path):
    """Largest RAD and DIFF iteration counts in the iteration table of ``wec.out`` (``None`` when there is none)."""
    rad = diff = None
    if not os.path.exists(out_path):
        return rad, diff
    with open(out_path, errors="replace") as f:
        for line in f:
            row = _ITERATION_ROW.match(line)
            if row:
                rad = max(rad or 0, int(row.group(2)))
                diff = max(diff or 0, int(row.group(3)))
    return rad, diff


def build_config(cfg, site, mesh_panels, solver, workspace_dir):
    wamit = cfg["WAMIT Settings"]
    wamit_data = {
        "NCPU": int(wamit["NCPU"]),
        "RAMGBMAX": int(wamit["RAMGBMAX"]),
        "WAMITPath": wamit.get("WAMITPath"),
        "MeshPanels": mesh_panels,
        "Solver": solver,
        "OmegaMax": float(wamit.get("OmegaMax", 3.0)),
        "FreqGrid": 0,
        "Shape": 1,
        "VerticalWall": 1,
        "HydroSolver": 1,
    }
    config = get_joint_config(
        cfg["Constraints"], cfg["WEC Parameters"], 5, load_env_data(SITE_IDS[site]), wamit_data, 1
    )
    config["workspace_dir"] = workspace_dir
    return config


def summarize(rows):
    """Per (site, design, mesh, solver): shortest time, power and the largest change against Solver 1 [%]."""
    best = {}
    for row in rows:
        key = (row["site"], row["design"], row["mesh_panels"], row["solver"])
        if key not in best or row["time_s"] < best[key]["time_s"]:
            best[key] = row
    out = []
    for (site, design, mesh, _solver), row in best.items():
        ref = best.get((site, design, mesh, 1))
        total_pct = wec_pct = speedup = None
        if ref is not None:
            total_pct = (row["power_kw"] / ref["power_kw"] - 1) * 100
            pairs = zip(row["wec_kw"].split(), ref["wec_kw"].split(), strict=True)
            wec_pct = max(abs(float(a) / float(b) - 1) * 100 for a, b in pairs)
            speedup = ref["time_s"] / row["time_s"] if row["time_s"] > 0 else None
        out.append({**row, "total_pct": total_pct, "wec_pct": wec_pct, "speedup_vs_direct": speedup})
    return out


def main(argv=None, evaluate=evaluate_joint):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--solvers", nargs="+", type=int, default=[0, 1, 2, 5])
    parser.add_argument("--meshes", nargs="+", type=int, default=[120, 180])
    parser.add_argument("--sites", nargs="+", default=["Buan", "Yeongilmanhang"], choices=list(SITE_IDS))
    parser.add_argument("--designs", nargs="+", default=list(DESIGNS), choices=list(DESIGNS))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--config", default=os.path.join(ROOT, "config.cfg"))
    parser.add_argument("--out", default="logs")
    parser.add_argument("--workspace", default=os.path.join("workspace", "solver_timing"))
    args = parser.parse_args(argv)

    cfg = parse_wec_cfg(args.config)
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.workspace, exist_ok=True)
    path = os.path.join(args.out, "solver_timing.csv")
    rows = []
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for site in args.sites:
            for name in args.designs:
                vector = DESIGNS[name]
                if check_min_distance(decode_symmetric_positions(vector[2:], 5), vector[0], 4.0) > 0:
                    raise ValueError(f"design {name} violates the 4R spacing")
                for mesh in args.meshes:
                    for repeat in range(args.repeats):
                        for solver in args.solvers:  # solvers alternate so that drifts affect all of them alike
                            config = build_config(cfg, site, mesh, solver, args.workspace)
                            start = time.perf_counter()
                            total, wec = evaluate(vector, config)
                            elapsed = time.perf_counter() - start
                            rad, diff = iteration_counts(os.path.join(args.workspace, "wec.out"))
                            row = {
                                "site": site,
                                "design": name,
                                "mesh_panels": mesh,
                                "solver": solver,
                                "repeat": repeat,
                                "time_s": round(elapsed, 3),
                                "power_kw": round(total / 1000, 6),
                                "wec_kw": " ".join(f"{p / 1000:.6f}" for p in wec),
                                "max_iter_rad": rad if solver != 1 else None,
                                "max_iter_diff": diff if solver != 1 else None,
                            }
                            writer.writerow(row)
                            f.flush()
                            rows.append(row)
                            print(
                                f"{site:<15} {name:<12} mesh {mesh} solver {solver} #{repeat}: "
                                f"{elapsed:6.2f} s {total / 1000:10.4f} kW iterations {rad}/{diff}",
                                flush=True,
                            )
    print(f"wrote {path}\n")
    summary = summarize(rows)
    print(f"{'site':<15} {'design':<12} {'mesh':>4} {'solver':>6} {'time s':>7}", end=" ")
    print(f"{'x direct':>8} {'total %':>9} {'WEC %':>7}")
    for s in summary:
        pct = "" if s["total_pct"] is None else f"{s['total_pct']:+9.4f}"
        wec = "" if s["wec_pct"] is None else f"{s['wec_pct']:7.4f}"
        speed = "" if s["speedup_vs_direct"] is None else f"{s['speedup_vs_direct']:8.2f}"
        head = f"{s['site']:<15} {s['design']:<12} {s['mesh_panels']:>4} {s['solver']:>6} {s['time_s']:7.2f}"
        print(f"{head} {speed} {pct} {wec}")
    return rows, summary


if __name__ == "__main__":
    main()
