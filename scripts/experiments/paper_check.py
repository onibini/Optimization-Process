"""Evaluate the optimal designs of the simultaneous-optimization paper with the current evaluation process.

For the three sites of the paper (Buan, Chilbaldo, Yeongilmanhang) and both strategies (sequential, simultaneous) the
optimal design of Table 4 is evaluated with the settings of the current process (5 WECs, vertical wall, uniform 0.05
rad/s grid of 51 frequencies, JONSWAP Goda, gamma 1.4). The total power is compared with the value of the paper.
Nothing is optimized here.

Each WAMIT run (one per design and mesh) writes both exciting-force files, so every power below is computed from
the same hydrodynamic data and differs only in how the data are used:

    excitation  diffraction (wec.3, current default) or haskind (wec.2, the process before 2026-10-21)
    spec        wave spectrum: goda (WaveSpec 2, current) or ittc (WaveSpec 1)
    integ       frequency integration: simpson (current), trapz, or rect (sum of S * d_omega over the 51 points)

The environment (Hs, Tp, gamma, depth) of the three sites comes from data/env_data.csv.

Run on the compute PC (WAMIT is needed)::

    python scripts/experiments/paper_check.py                       # meshes 120 and 200
    python scripts/experiments/paper_check.py --meshes 120 --sites Buan

Results: ``logs/paper_check.csv`` (one row per combination). ``--dry-run`` only prints the designs.

Regression check after changing the evaluation process (frequency grid, mesh, spectrum, physics, environment data)::

    python scripts/experiments/paper_check.py --reference docs/validation/paper_check_reference.csv

compares every combination that is in both tables with the stored reference and exits with status 1 if a power differs
by more than ``--tolerance`` percent (default 0.2). See docs/validation/README.md.
"""

import argparse
import csv
import itertools
import os
import sys

import numpy as np
from scipy.integrate import simpson

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.physics import calculate_rao_matrix, run_wamit, write_wamit_inputs  # noqa: E402
from src.physics.wave_spectrum import get_jonswap_spectrum  # noqa: E402
from src.problems import get_joint_config  # noqa: E402
from src.utils.config_parser import parse_wec_cfg  # noqa: E402
from src.utils.data_handler import load_env_data  # noqa: E402
from src.utils.mapper import decode_symmetric_positions  # noqa: E402

SITE_IDS = {"Buan": 1, "Chilbaldo": 2, "Yeongilmanhang": 3}
# Table 4 of the paper: WEC1 (x1, y1), WEC2 (x2, y2), WEC3 x3 (WEC3 on the centre line), r, d, total power [kW]
PAPER_DESIGNS = {
    ("Buan", "sequential"): (3.0, 30.0, 3.0, 11.9, 3.0, 2.5, 4.8, 47.52),
    ("Buan", "simultaneous"): (3.0, 30.0, 3.0, 13.9, 3.0, 2.5, 3.8, 50.36),
    ("Chilbaldo", "sequential"): (15.0, 30.0, 15.2, 15.3, 15.3, 2.5, 2.0, 31.33),
    ("Chilbaldo", "simultaneous"): (3.0, 23.5, 3.0, 10.8, 3.0, 2.5, 2.4, 31.91),
    ("Yeongilmanhang", "sequential"): (3.0, 30.0, 3.0, 11.9, 3.0, 2.5, 4.8, 29.23),
    ("Yeongilmanhang", "simultaneous"): (3.0, 30.0, 3.0, 11.7, 3.0, 2.5, 4.9, 29.32),
}
EXCITATIONS = ("diffraction", "haskind")
SPECS = {"goda": 2, "ittc": 1}
INTEGRATIONS = ("simpson", "trapz", "rect")
FIELDS = [
    "site",
    "method",
    "mesh_panels",
    "depth",
    "excitation",
    "spec",
    "integ",
    "paper_kw",
    "power_kw",
    "diff_pct",
    "wec_kw",
]
BOTH_EXCITATIONS = "1 1 1 0 0 0 0 0 0"  # .1 + Haskind (.2) + diffraction (.3)
DIFFRACTION_ONLY = "1 0 1 0 0 0 0 0 0"
PRINTED = (("diffraction", "goda", "simpson"), ("haskind", "goda", "simpson"))


def paper_vector(design):
    """Project design vector ``[R, D, X1, X2, Y2, X3, Y3]`` of a Table 4 row.

    The project puts WEC1 on the centre line and the two symmetric pairs at (x2, +-y2) and (x3, +-y3); the paper puts
    WEC3 on the centre line and the pairs at WEC1 (x1, +-y1) and WEC2 (x2, +-y2). The same five positions result.
    """
    x1, y1, x2, y2, x3, radius, draft, _ = design
    return [radius, draft, x3, x2, y2, x1, y1]


def build_config(cfg, site, mesh_panels=None):
    wamit = cfg["WAMIT Settings"]
    wamit_data = {
        "NCPU": int(wamit["NCPU"]),
        "RAMGBMAX": int(wamit["RAMGBMAX"]),
        "WAMITPath": wamit.get("WAMITPath"),
        "MeshPanels": int(mesh_panels or wamit.get("MeshPanels", 120)),
        "Solver": int(wamit.get("Solver", 0)),
        "OmegaMax": float(wamit.get("OmegaMax", 3.0)),
        "FreqGrid": 0,  # the paper used the uniform 0.05 rad/s grid
    }
    env = load_env_data(SITE_IDS[site])
    wave_spec = int(cfg["Simulation"]["WaveSpec"])
    return get_joint_config(cfg["Constraints"], cfg["WEC Parameters"], 5, env, wamit_data, wave_spec)


def run_hydrodynamics(vector, config, workspace_dir="workspace"):
    """One WAMIT run; returns the RAO results computed with each exciting-force file."""
    positions = decode_symmetric_positions(vector[2:], config["num_wecs"])
    write_wamit_inputs(vector, config, workspace_dir, positions=positions)
    frc_path = os.path.join(workspace_dir, "wec.frc")
    with open(frc_path) as f:
        text = f.read()
    if DIFFRACTION_ONLY not in text:
        raise RuntimeError(f"unexpected output options in {frc_path}")
    with open(frc_path, "w") as f:
        f.write(text.replace(DIFFRACTION_ONLY, BOTH_EXCITATIONS))
    run_wamit(workspace_dir, config.get("wamit_exe"))
    return {
        excitation: calculate_rao_matrix(workspace_dir, config["num_wecs"], excitation=excitation)
        for excitation in EXCITATIONS
    }


def integrate(y, omegas, how):
    if how == "simpson":
        return float(simpson(y=y, x=omegas))
    if how == "trapz":
        return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(omegas)))
    if how == "rect":
        return float(np.sum(y) * (omegas[1] - omegas[0]))
    raise ValueError(how)


def powers(rao_results, config, spec, integ):
    """Per-WEC power [W] from RAO results (same formula as ``calculate_power``, selectable spectrum and integration)."""
    omegas = np.array([r["omega"] for r in rao_results])
    spectrum = get_jonswap_spectrum(omegas, float(config["hs"]), float(config["tp"]), float(config["gamma"]), spec)
    out = []
    for k in range(len(rao_results[0]["rao_abs"])):
        b_pto = rao_results[0]["b_pto"][k]
        rao = np.array([r["rao_abs"][k] for r in rao_results])
        out.append(integrate(b_pto * omegas**2 * rao**2 * spectrum, omegas, integ))
    return out


def compare_with_reference(rows, reference_path, tolerance_pct):
    """Rows whose total power differs from the reference by more than ``tolerance_pct``; also counts the matches."""
    key = ("site", "method", "mesh_panels", "depth", "excitation", "spec", "integ")
    with open(reference_path, newline="", encoding="utf-8") as f:
        reference = {tuple(str(r[k]) for k in key): float(r["power_kw"]) for r in csv.DictReader(f)}
    compared, mismatches = 0, []
    for row in rows:
        ref = reference.get(tuple(str(row[k]) for k in key))
        if ref is None:
            continue
        compared += 1
        change = (row["power_kw"] / ref - 1) * 100
        if abs(change) > tolerance_pct:
            mismatches.append((tuple(row[k] for k in key), ref, row["power_kw"], round(change, 3)))
    return compared, mismatches


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--meshes", nargs="+", type=int, default=[120, 200])
    parser.add_argument("--sites", nargs="+", default=list(SITE_IDS), choices=list(SITE_IDS))
    parser.add_argument("--config", default=os.path.join(ROOT, "config.cfg"))
    parser.add_argument("--out", default="logs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reference", help="stored results (CSV of this script) to compare with")
    parser.add_argument("--tolerance", type=float, default=0.2, help="allowed power change in percent")
    args = parser.parse_args(argv)

    cfg = parse_wec_cfg(args.config)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "paper_check.csv")
    rows = []
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for (site, method), design in PAPER_DESIGNS.items():
            if site not in args.sites:
                continue
            vector = paper_vector(design)
            positions = decode_symmetric_positions(vector[2:], 5)
            print(f"== {site} {method}: vector {vector}", flush=True)
            print("   positions " + ", ".join(f"({x:g}, {y:g})" for x, y in positions), flush=True)
            if args.dry_run:
                continue
            for mesh in args.meshes:
                config = build_config(cfg, site, mesh)
                raos = run_hydrodynamics(vector, config)
                combos = itertools.product(EXCITATIONS, SPECS.items(), INTEGRATIONS)
                for excitation, (spec_name, spec), integ in combos:
                    wec = powers(raos[excitation], config, spec, integ)
                    total = sum(wec) / 1000
                    row = {
                        "site": site,
                        "method": method,
                        "mesh_panels": mesh,
                        "depth": config["depth"],
                        "excitation": excitation,
                        "spec": spec_name,
                        "integ": integ,
                        "paper_kw": design[-1],
                        "power_kw": round(total, 4),
                        "diff_pct": round((total / design[-1] - 1) * 100, 3),
                        "wec_kw": " ".join(f"{p / 1000:.3f}" for p in wec),
                    }
                    writer.writerow(row)
                    rows.append(row)
                    if (excitation, spec_name, integ) in PRINTED:
                        print(
                            f"   mesh {mesh} depth {config['depth']:g} {excitation:<11} {spec_name} {integ}: "
                            f"{total:8.3f} kW (paper {design[-1]:.2f}, {row['diff_pct']:+.2f}%)",
                            flush=True,
                        )
                f.flush()
    print(f"wrote {path}")
    if args.reference and not args.dry_run:
        compared, mismatches = compare_with_reference(rows, args.reference, args.tolerance)
        print(f"reference: {compared} combinations compared, {len(mismatches)} differ by more than {args.tolerance}%")
        for key, ref, now, change in mismatches:
            print(f"   {key}: reference {ref:.4f} kW, now {now:.4f} kW ({change:+.3f}%)")
        if mismatches or compared == 0:
            sys.exit(1)
    return rows


if __name__ == "__main__":
    main()
