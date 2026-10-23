"""Compare the hydrodynamic solvers (WAMIT and Capytaine) on the same design in the open sea.

For each case the heave added mass, radiation damping, exciting force and the resulting power (site spectrum,
PTO tuned as in the optimizer) are computed with both solvers from the same panel mesh. Both solvers run on this
computer, so WAMIT must be installed for the WAMIT side.

    python scripts/experiments/solver_compare.py                                  # 1 WEC and a 5-WEC array
    python scripts/experiments/solver_compare.py --shape 2 --cases single --panels 120

Results: ``<out>/solver_compare.csv`` (one row per case), ``<out>/solver_compare_<case>_<R>_<D>.csv`` (WEC1 per
frequency) and ``.npz`` with the full added-mass, damping and exciting-force arrays of both solvers.
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

from src.physics import calculate_power  # noqa: E402
from src.physics.rao_calc import rao_from_hydro  # noqa: E402
from src.physics.solvers import solve_hydrodynamics  # noqa: E402
from src.utils.data_handler import load_env_data  # noqa: E402
from src.utils.mapper import decode_symmetric_positions  # noqa: E402

# 5-WEC layout [X1, X2, Y2, X3, Y3] (WEC1 on the centre line, symmetric pairs)
ARRAY_LAYOUT = [10.0, 10.0, 12.0, 16.0, 26.0]
CASES = ("single", "array")


def build_config(case, shape, panels, site, ncpu, solver, freq_grid):
    env = load_env_data(site, os.path.join(ROOT, "data", "env_data.csv"))
    return {
        "opt_mode": 1 if case == "single" else 3,
        "num_wecs": 1 if case == "single" else 5,
        "ncpu": ncpu,
        "ram": 16,
        "depth": env["Depth"],
        "mesh_panels": panels,
        "solver": 0,
        "omega_max": 3.0,
        "freq_grid": freq_grid,
        "shape": shape,
        "vertical_wall": 0,
        "hydro_solver": solver,
        "hs": env["Hs"],
        "tp": env["Tp"],
        "gamma": env["Gamma"],
        "wave_spec": 1,
        "min_spacing": 4,
    }


def run_case(case, radius, draft, args):
    vector = [radius, draft] if case == "single" else [radius, draft, *ARRAY_LAYOUT]
    positions = None if case == "single" else decode_symmetric_positions(ARRAY_LAYOUT, 5)
    out = {}
    for solver, name in ((1, "wamit"), (2, "capytaine")):
        config = build_config(case, args.shape, args.panels, args.site, args.ncpu, solver, args.freq_grid)
        start = time.time()
        hydro = solve_hydrodynamics(vector, config, positions, args.workdir)
        elapsed = time.time() - start
        power, wec_power = calculate_power(rao_from_hydro(hydro), config)
        out[name] = (hydro, power, wec_power, elapsed)
    shutil.rmtree(args.workdir, ignore_errors=True)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cases", nargs="+", default=list(CASES), choices=CASES)
    parser.add_argument("--designs", nargs="+", default=["2.5:5.0", "1.0:2.0"], help="R:D")
    parser.add_argument("--shape", type=int, default=1)
    parser.add_argument("--panels", type=int, default=120)
    parser.add_argument("--site", type=int, default=1)
    parser.add_argument("--ncpu", type=int, default=8)
    parser.add_argument("--freq-grid", type=int, default=0)
    parser.add_argument("--workdir", default=r"C:\wec_solver_compare")
    parser.add_argument("--out", default="logs")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    summary = []
    for case in args.cases:
        for text in args.designs:
            radius, draft = (float(x) for x in text.split(":"))
            res = run_case(case, radius, draft, args)
            (hw, pw, ww, tw), (hc, pc, wc, tc) = res["wamit"], res["capytaine"]
            peak = lambda a: np.max(np.abs(a))  # noqa: E731
            row = {
                "case": case,
                "shape": args.shape,
                "R": radius,
                "D": draft,
                "panels": args.panels,
                "A_max_diff_pct": round(100 * peak(hc.added_mass - hw.added_mass) / peak(hw.added_mass), 3),
                "B_max_diff_pct": round(100 * peak(hc.damping - hw.damping) / peak(hw.damping), 3),
                "F_max_diff_pct": round(100 * peak(hc.excitation - hw.excitation) / peak(hw.excitation), 3),
                "mass_diff_pct": round(100 * (hc.mass[0, 0] / hw.mass[0, 0] - 1), 3),
                "c33_diff_pct": round(100 * (hc.stiffness[0, 0] / hw.stiffness[0, 0] - 1), 3),
                "power_wamit_kw": round(pw / 1000, 4),
                "power_capytaine_kw": round(pc / 1000, 4),
                "power_diff_pct": round(100 * (pc / pw - 1), 3),
                "wec_power_max_diff_pct": round(100 * max(abs(c / w - 1) for c, w in zip(wc, ww, strict=True)), 3),
                "time_wamit_s": round(tw, 1),
                "time_capytaine_s": round(tc, 1),
            }
            summary.append(row)
            # full matrices of both solvers (interaction terms), for plots
            np.savez(
                os.path.join(args.out, f"solver_compare_{case}_{radius}_{draft}.npz"),
                omegas=hw.omegas,
                positions=np.array(decode_symmetric_positions(ARRAY_LAYOUT, 5) if case == "array" else [(0.0, 0.0)]),
                **{
                    f"{name}_{key}": getattr(h, attr)
                    for name, h in (("wamit", hw), ("capytaine", hc))
                    for key, attr in (("A", "added_mass"), ("B", "damping"), ("F", "excitation"))
                },
            )
            print(row, flush=True)
            with open(os.path.join(args.out, f"solver_compare_{case}_{radius}_{draft}.csv"), "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["omega", "A11_wamit", "A11_capytaine", "B11_wamit", "B11_capytaine", "F1_wamit_abs",
                                 "F1_capytaine_abs", "F1_phase_diff_deg"])  # fmt: skip
                for k, w in enumerate(hw.omegas):
                    writer.writerow(
                        [
                            w,
                            hw.added_mass[k, 0, 0],
                            hc.added_mass[k, 0, 0],
                            hw.damping[k, 0, 0],
                            hc.damping[k, 0, 0],
                            abs(hw.excitation[k, 0]),
                            abs(hc.excitation[k, 0]),
                            np.degrees(np.angle(hc.excitation[k, 0] / hw.excitation[k, 0])),
                        ]
                    )
    with open(os.path.join(args.out, "solver_compare.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


if __name__ == "__main__":
    main()
