"""Single-WEC mesh check: hydrostatics and power of one body in the open sea for several panel counts.

For each design (R, D) and quarter-panel target the script writes the WAMIT inputs of a single WEC (OptMode 1, no
wall), runs WAMIT and records
    - the displaced volume and heave stiffness from WAMIT against the exact values of the shape,
    - the time-averaged power in the site spectrum (JONSWAP ITTC by default) and its change with the panel count,
    - per-frequency heave added mass, radiation damping, exciting force, RAO and power density (``--dump``).

    python scripts/experiments/shape_mesh_check.py --shape 2
    python scripts/experiments/shape_mesh_check.py --shape 2 --designs 2.5:5.0 0.5:2.0 --panels 60 120 240 --dump

WAMIT dislikes long paths, so the work folder defaults to ``C:\\wec_mesh_check`` (removed afterwards).
Results: ``<out>/shape_mesh_check.csv`` and, with ``--dump``, ``<out>/shape_mesh_dump_<shape>_<R>_<D>_<panels>.csv``.
"""

import argparse
import csv
import importlib.util
import math
import os
import shutil
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.physics import calculate_power, calculate_rao_matrix, run_wamit, write_wamit_inputs  # noqa: E402
from src.physics.mesh_axisymmetric_shape import SHAPES, check_shape, displaced_volume  # noqa: E402
from src.physics.rao_calc import get_volumes_from_out  # noqa: E402
from src.physics.wave_spectrum import get_jonswap_spectrum  # noqa: E402
from src.utils.data_handler import load_env_data  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "freq_grid_study", os.path.join(os.path.dirname(os.path.abspath(__file__)), "freq_grid_study.py")
)
_study = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_study)

RHO, GRAVITY = 1025.0, 9.80665
FIELDS = [
    "shape",
    "R",
    "D",
    "panels_target",
    "panels",
    "volume_ratio",
    "c33_ratio",
    "power_w",
    "change_vs_finest_pct",
    "peak_omega",
    "time_s",
]


def parse_design(text):
    radius, draft = (float(x) for x in text.split(":"))
    return radius, draft


def build_config(shape, panels, site, ncpu, wamit_exe, wave_spec, freq_grid=0):
    env = load_env_data(site, os.path.join(ROOT, "data", "env_data.csv"))
    return {
        "opt_mode": 1,
        "num_wecs": 1,
        "ncpu": ncpu,
        "ram": 16,
        "depth": env["Depth"],
        "mesh_panels": panels,
        "solver": 0,
        "omega_max": 3.0,
        "freq_grid": freq_grid,
        "shape": shape,
        "hs": env["Hs"],
        "tp": env["Tp"],
        "gamma": env["Gamma"],
        "wave_spec": wave_spec,
        "wamit_exe": wamit_exe,
    }


def quarter_panels(workdir):
    with open(os.path.join(workdir, "wec.gdf")) as f:
        return int(f.read().split("\n")[3].split()[0])


def write_dump(path, workdir, rao, config):
    hydro, force = _study.read_hydro(workdir, 1)
    omegas = np.array([r["omega"] for r in rao])
    spectrum = get_jonswap_spectrum(omegas, config["hs"], config["tp"], config["gamma"], config["wave_spec"])
    bpto = rao[0]["b_pto"][0]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["omega", "A33", "B33", "F3_abs", "rao", "bpto", "density"])
        for k, w in enumerate(omegas):
            amp = rao[k]["rao_abs"][0]
            writer.writerow(
                [
                    f"{w:.6f}",
                    f"{hydro[w]['A'][0, 0]:.6e}",
                    f"{hydro[w]['B'][0, 0]:.6e}",
                    f"{abs(force[w][0]):.6e}",
                    f"{amp:.6e}",
                    f"{bpto:.6e}",
                    f"{bpto * w**2 * amp**2 * spectrum[k]:.6e}",
                ]
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--shape", type=int, default=2, help="1 cylinder + hemisphere, 2 flat-bottom cylinder")
    parser.add_argument("--designs", nargs="+", default=["2.5:5.0", "1.5:2.5", "0.5:2.0", "2.5:1.0"], help="R:D")
    parser.add_argument("--panels", nargs="+", type=int, default=[60, 120, 200, 300, 400])
    parser.add_argument("--site", type=int, default=1)
    parser.add_argument("--wave-spec", type=int, default=1)
    parser.add_argument(
        "--freq-grid", type=int, default=0, help="0 uniform 0.05 rad/s, 1 adaptive around the resonance"
    )
    parser.add_argument("--ncpu", type=int, default=8)
    parser.add_argument("--wamit-exe", default=None)
    parser.add_argument("--workdir", default=r"C:\wec_mesh_check")
    parser.add_argument("--out", default="logs")
    parser.add_argument("--dump", action="store_true")
    args = parser.parse_args(argv)

    shape = check_shape(args.shape)
    os.makedirs(args.out, exist_ok=True)
    rows = []
    try:
        for radius, draft in (parse_design(d) for d in args.designs):
            design_rows = []
            for target in sorted(args.panels):
                config = build_config(
                    shape, target, args.site, args.ncpu, args.wamit_exe, args.wave_spec, args.freq_grid
                )
                workdir = os.path.join(args.workdir, f"p{target}")
                start = time.time()
                write_wamit_inputs([radius, draft], config, workdir)
                run_wamit(workdir, config["wamit_exe"])
                rao = calculate_rao_matrix(workdir, 1)
                power, _ = calculate_power(rao, config)
                elapsed = time.time() - start
                volume = get_volumes_from_out(workdir, 1)[0]
                c33 = _study.read_stiffness(workdir)
                peak = max(rao, key=lambda r: r["rao_abs"][0])["omega"]
                row = {
                    "shape": shape,
                    "R": radius,
                    "D": draft,
                    "panels_target": target,
                    "panels": quarter_panels(workdir),
                    "volume_ratio": round(volume / displaced_volume(shape, radius, draft), 5),
                    "c33_ratio": round(c33 / (RHO * GRAVITY * math.pi * radius**2), 5),
                    "power_w": round(power, 3),
                    "peak_omega": peak,
                    "time_s": round(elapsed, 2),
                }
                design_rows.append(row)
                if args.dump:
                    write_dump(
                        os.path.join(args.out, f"shape_mesh_dump_{shape}_{radius}_{draft}_{target}.csv"),
                        workdir,
                        rao,
                        config,
                    )
                print(
                    f"{SHAPES[shape]} R={radius} D={draft} panels {row['panels']:>4}: {power / 1000:8.4f} kW, "
                    f"volume x{row['volume_ratio']}, C33 x{row['c33_ratio']}, peak {peak:g} rad/s, {elapsed:.1f} s",
                    flush=True,
                )
            finest = design_rows[-1]["power_w"]
            for row in design_rows:
                row["change_vs_finest_pct"] = round((row["power_w"] / finest - 1) * 100, 3)
            rows += design_rows
    finally:
        shutil.rmtree(args.workdir, ignore_errors=True)
    path = os.path.join(args.out, "shape_mesh_check.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path}")
    return rows


if __name__ == "__main__":
    main()
