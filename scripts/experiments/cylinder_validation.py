"""Independent checks of the flat-bottom cylinder (Shape 2) results of WAMIT for one body in the open sea.

1. Semi-analytical solution: heave added mass and radiation damping of a truncated vertical cylinder in water of
   finite depth by matched eigenfunction expansions (the method of Yeung, 1981, Applied Ocean Research 3(3)).
   Region I below the body (r < a) holds a particular solution plus cos(n pi (z + h) / (h - d)) modes, region II
   (r > a) the propagating mode (Hankel function) plus evanescent modes (K0); potential and radial velocity are
   matched at r = a.
2. Haskind relation: the heave exciting force from the diffraction problem (wec.3) must equal the one from the
   radiation potential (Haskind, wec.2).
3. Energy: for an axisymmetric body in heave B33 = k |X3|^2 / (4 rho g Cg) (Newman, Marine Hydrodynamics), and the
   power absorbed in regular waves cannot exceed the point-absorber limit rho g Cg / (2 k) per unit amplitude^2
   (capture width 1/k).

    python scripts/experiments/cylinder_validation.py                       # 4 designs, depth 50 m and 13 m
    python scripts/experiments/cylinder_validation.py --designs 2.5:5.0 --depths 50 --panels 120 800

Results: ``<out>/cylinder_validation.csv`` (per design, depth, panels and frequency) and
``<out>/cylinder_validation_summary.csv``.
"""

import argparse
import csv
import math
import os
import shutil
import sys

import numpy as np
from scipy.optimize import brentq
from scipy.special import hankel1, ive, kve

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.physics import calculate_rao_matrix, run_wamit, write_wamit_inputs  # noqa: E402

RHO, GRAVITY = 1025.0, 9.80665
BOTH_EXCITATIONS, DIFFRACTION_ONLY = "1 1 1 0 0 0 0 0 0", "1 0 1 0 0 0 0 0 0"


# ---------------------------------------------------------------------------------------------------------------
# water waves
# ---------------------------------------------------------------------------------------------------------------
def wavenumber(omega, depth, g=GRAVITY):
    """Real root of k tanh(k h) = omega^2 / g."""
    nu = omega**2 / g
    return brentq(lambda k: k * math.tanh(k * depth) - nu, 1e-12, nu + 10.0 / depth + 10.0)


def evanescent_wavenumbers(omega, depth, count, g=GRAVITY):
    """First ``count`` roots of k tan(k h) = -omega^2 / g, one in each ((m - 1/2) pi / h, m pi / h)."""
    nu = omega**2 / g
    roots = []
    for m in range(1, count + 1):
        lo, hi = (m - 0.5) * math.pi / depth, m * math.pi / depth
        eps = 1e-12 * hi
        roots.append(brentq(lambda k: k * math.tan(k * depth) + nu, lo + eps, hi - eps))
    return np.array(roots)


def group_velocity(omega, depth, g=GRAVITY):
    k = wavenumber(omega, depth, g)
    return 0.5 * omega / k * (1.0 + 2.0 * k * depth / math.sinh(2.0 * k * depth))


# ---------------------------------------------------------------------------------------------------------------
# 1. semi-analytical heave radiation of a truncated cylinder
# ---------------------------------------------------------------------------------------------------------------
def cylinder_heave_radiation(radius, draft, depth, omega, modes=None, rho=RHO, g=GRAVITY):
    """Heave added mass A33 [kg] and radiation damping B33 [N s/m] of a floating truncated cylinder.

    Unit heave velocity, time dependence exp(-i omega t). Region I: 0 <= r <= a, -h <= z <= -d; region II: r >= a.
    All projections are evaluated in closed form. ``modes`` (per region) defaults to about 6 h / min(a, d) so that the
    vertical modes resolve the body corner (at least 40, at most 800).
    """
    a, d, h = radius, draft, depth
    b = h - d  # gap below the body
    if b <= 0:
        raise ValueError("the cylinder must not touch the sea bottom")
    if modes is None:
        modes = int(min(800, max(40, math.ceil(6 * h / min(a, d)))))
    k0 = wavenumber(omega, h, g)
    km = evanescent_wavenumbers(omega, h, modes, g)
    n_b = modes + 1
    lam = np.arange(n_b) * math.pi / b  # region I modes, lam_0 = 0
    sign = np.cos(np.arange(n_b) * math.pi)  # cos(lam_n b) = (-1)^n

    # region II vertical modes: Z_0 = cosh(k0 u) / cosh(k0 h), Z_m = cos(k_m u), u = z + h
    sech = 2 * math.exp(-k0 * h) / (1 + math.exp(-2 * k0 * h))
    norms = np.empty(n_b)
    norms[0] = h / 2 * sech**2 + math.tanh(k0 * h) / (2 * k0)
    norms[1:] = h / 2 + np.sin(2 * km * h) / (4 * km)
    # L[m, n] = int_0^b Z_m cos(lam_n u) du
    big_l = np.empty((n_b, n_b))
    sinh_kb = (math.exp(k0 * (b - h)) - math.exp(-k0 * (b + h))) / (
        1 + math.exp(-2 * k0 * h)
    )  # sinh(k0 b) / cosh(k0 h)
    big_l[0] = sign * k0 * sinh_kb / (k0**2 + lam**2)
    kk, ll = np.meshgrid(km, lam, indexing="ij")
    big_l[1:] = sign[None, :] * kk * np.sin(kk * b) / (kk**2 - ll**2)

    # radial ratios R'(a) / R(a)
    ratio_out = np.empty(n_b, dtype=complex)
    ratio_out[0] = -k0 * hankel1(1, k0 * a) / hankel1(0, k0 * a)
    ratio_out[1:] = -km * kve(1, km * a) / kve(0, km * a)
    ratio_in = lam[1:] * ive(1, lam[1:] * a) / ive(0, lam[1:] * a)  # region I, n >= 1

    # particular solution phi_p = ((z + h)^2 - r^2 / 2) / (2 b): radial derivative and projections at r = a
    dphip_dr = -a / (2 * b)
    p_n = np.empty(n_b)
    p_n[0] = b**2 / 6 - a**2 / 4
    p_n[1:] = sign[1:] / lam[1:] ** 2
    c_n = np.full(n_b, b / 2)
    c_n[0] = b

    # unknowns x = [A_0..A_N, B_0..B_M]
    mat = np.zeros((2 * n_b, 2 * n_b), dtype=complex)
    rhs = np.zeros(2 * n_b, dtype=complex)
    mat[np.arange(n_b), np.arange(n_b)] = c_n  # potential continuity on cos(lam_n u) over the gap
    mat[:n_b, n_b:] = -big_l.T
    rhs[:n_b] = -p_n
    mat[n_b + np.arange(n_b), n_b + np.arange(n_b)] = ratio_out * norms  # radial velocity on Z_m over the depth
    mat[n_b:, 1:n_b] = -ratio_in[None, :] * big_l[:, 1:]
    rhs[n_b:] = dphip_dr * big_l[:, 0]
    coef_a = np.linalg.solve(mat, rhs)[:n_b]

    # integral of phi over the bottom z = -d (u = b)
    integral = 2 * math.pi * ((b**2 * a**2 / 2 - a**4 / 8) / (2 * b) + coef_a[0] * a**2 / 2)
    integral += 2 * math.pi * np.sum(coef_a[1:] * sign[1:] * a / lam[1:] * ive(1, lam[1:] * a) / ive(0, lam[1:] * a))
    return rho * integral.real, rho * omega * integral.imag


# ---------------------------------------------------------------------------------------------------------------
# WAMIT single body with both exciting forces
# ---------------------------------------------------------------------------------------------------------------
def wamit_single(radius, draft, depth, panels, workdir, wamit_exe=None, ncpu=8):
    config = {
        "opt_mode": 1,
        "num_wecs": 1,
        "ncpu": ncpu,
        "ram": 16,
        "depth": depth,
        "mesh_panels": panels,
        "solver": 0,
        "omega_max": 3.0,
        "freq_grid": 0,
        "shape": 2,
        "wamit_exe": wamit_exe,
    }
    write_wamit_inputs([radius, draft], config, workdir)
    frc = os.path.join(workdir, "wec.frc")
    with open(frc) as f:
        text = f.read()
    with open(frc, "w") as f:
        f.write(text.replace(DIFFRACTION_ONLY, BOTH_EXCITATIONS))
    run_wamit(workdir, wamit_exe)

    hydro = {}
    with open(os.path.join(workdir, "wec.1")) as f:
        next(f)
        for line in f:
            cols = line.split()
            if len(cols) >= 5 and int(cols[1]) == 3 and int(cols[2]) == 3:
                w = float(cols[0])
                hydro[w] = {"A33": float(cols[3]) * RHO, "B33": float(cols[4]) * RHO * w}
    for name, key in (("wec.2", "F_haskind"), ("wec.3", "F_diffraction")):
        with open(os.path.join(workdir, name)) as f:
            next(f)
            for line in f:
                cols = line.split()
                if len(cols) >= 7 and int(cols[2]) == 3:
                    hydro[float(cols[0])][key] = complex(float(cols[5]), float(cols[6])) * RHO * GRAVITY
    rao = {r["omega"]: r for r in calculate_rao_matrix(workdir, 1)}
    for w, entry in hydro.items():
        entry["rao"] = rao[w]["rao_abs"][0]
        entry["bpto"] = rao[w]["b_pto"][0]
    return hydro


FIELDS = [
    "R",
    "D",
    "depth",
    "panels",
    "omega",
    "A33_wamit",
    "A33_semi",
    "B33_wamit",
    "B33_semi",
    "F_diff_abs",
    "F_haskind_abs",
    "haskind_diff_pct",
    "B33_from_F",
    "energy_ratio",
    "P_regular",
    "P_limit",
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--designs", nargs="+", default=["2.5:5.0", "1.5:2.5", "2.5:1.0", "0.5:2.0"], help="R:D")
    parser.add_argument("--depths", nargs="+", type=float, default=[50.0, 13.0])
    parser.add_argument("--panels", nargs="+", type=int, default=[120, 800])
    parser.add_argument("--modes", type=int, default=None, help="eigenfunctions per region (default: automatic)")
    parser.add_argument("--wamit-exe", default=None)
    parser.add_argument("--workdir", default=r"C:\wec_cyl_check")
    parser.add_argument("--out", default="logs")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    rows, summary = [], []
    try:
        for text in args.designs:
            radius, draft = (float(x) for x in text.split(":"))
            for depth in args.depths:
                for panels in args.panels:
                    hydro = wamit_single(radius, draft, depth, panels, args.workdir, args.wamit_exe)
                    errs = {"A": [], "B": [], "H": [], "E": [], "P": []}
                    for w in sorted(hydro):
                        e = hydro[w]
                        a_semi, b_semi = cylinder_heave_radiation(radius, draft, depth, w, args.modes)
                        k, cg = wavenumber(w, depth), group_velocity(w, depth)
                        f_abs = abs(e["F_diffraction"])
                        b_from_f = k * f_abs**2 / (4 * RHO * GRAVITY * cg)
                        p_reg = 0.5 * e["bpto"] * w**2 * e["rao"] ** 2
                        p_lim = RHO * GRAVITY * cg / (2 * k)
                        row = {
                            "R": radius,
                            "D": draft,
                            "depth": depth,
                            "panels": panels,
                            "omega": w,
                            "A33_wamit": e["A33"],
                            "A33_semi": a_semi,
                            "B33_wamit": e["B33"],
                            "B33_semi": b_semi,
                            "F_diff_abs": f_abs,
                            "F_haskind_abs": abs(e["F_haskind"]),
                            "haskind_diff_pct": 100 * abs(e["F_haskind"] - e["F_diffraction"]) / f_abs,
                            "B33_from_F": b_from_f,
                            "energy_ratio": e["B33"] / b_from_f,
                            "P_regular": p_reg,
                            "P_limit": p_lim,
                        }
                        rows.append(row)
                        errs["A"].append(abs(e["A33"] / a_semi - 1))
                        errs["B"].append((e["B33"], b_semi))
                        errs["H"].append((abs(e["F_haskind"] - e["F_diffraction"]), f_abs))
                        errs["E"].append((abs(e["B33"] - b_from_f), b_from_f))
                        errs["P"].append(p_reg / p_lim)
                    item = {
                        "R": radius,
                        "D": draft,
                        "depth": depth,
                        "panels": panels,
                        "A33_max_err_pct": round(100 * max(errs["A"]), 3),
                        # damping error relative to its peak (B33 tends to 0 at high frequency)
                        "B33_max_err_pct": round(
                            100 * max(abs(bw - bs) for bw, bs in errs["B"]) / max(bs for _, bs in errs["B"]), 3
                        ),
                        # force and damping differences relative to their peaks (both tend to 0 at high frequency)
                        "haskind_max_diff_pct": round(
                            100 * max(x for x, _ in errs["H"]) / max(f for _, f in errs["H"]), 3
                        ),
                        "energy_max_err_pct": round(
                            100 * max(x for x, _ in errs["E"]) / max(v for _, v in errs["E"]), 3
                        ),
                        "max_power_over_limit": round(max(errs["P"]), 4),
                    }
                    summary.append(item)
                    print(item, flush=True)
    finally:
        shutil.rmtree(args.workdir, ignore_errors=True)
    for name, data in (("cylinder_validation.csv", rows), ("cylinder_validation_summary.csv", summary)):
        with open(os.path.join(args.out, name), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    return rows, summary


if __name__ == "__main__":
    main()
