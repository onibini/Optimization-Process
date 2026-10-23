"""WAMIT frequency-grid, NCPU and memory-limit studies for the compute PC.

Nothing in ``src/`` is changed by this script. It writes the normal WAMIT inputs with ``write_wamit_inputs`` and then
replaces the frequency list in ``wec.pot`` with the candidate grid, so candidate grids can be compared against a dense
reference grid before any of them is implemented in ``src/physics/wamit_handler.py``
(see ``docs/frequency_grid_design.md``).

Studies (5 WECs, vertical wall on, iterative solver):
    grids  compare candidate frequency grids against a dense uniform reference (0.00625 rad/s): power error, time,
           resonance position, and a verdict per candidate (criterion (a): accuracy first, time compared with the
           cheapest *uniform* grid that reaches the same accuracy). Designs with a very narrow resonance also get a
           0.003125 check grid to test whether the 0.00625 reference itself has converged.
           Two-stage candidates (``two_stage_fwhm*``): stage 1 is the uniform 0.05 run; the resonance of every WEC is
           located from its uncontrolled RAO and its width is estimated from the hydrodynamic coefficients
           (FWHM ~ 2 B_kk / (M + A_kk)); stage 2 adds frequencies around the resonances with a step of FWHM / n
           (0.003125, 0.00625 or 0.0125 rad/s). Time and number of frequencies are the sum of both stages.
    ncpu   time versus NCPU and number of frequencies (find the best NCPU / NPER combination)
    limit  largest total panel count that WAMIT accepts for each NCPU (32-bit memory limit)

Run on the compute PC (never needed on the personal PC)::

    python scripts/experiments/freq_grid_study.py --study grids --quick
    python scripts/experiments/freq_grid_study.py --study all

``--dry-run`` writes the inputs and prints the grids without starting WAMIT (the two-stage candidates need stage-1
results and are skipped). Results go to ``logs/freq_grid_study_<study>.csv`` (``freq_grid_study_grids_verdict.csv`` for
the verdicts) and are printed as they are produced. For the ``grids`` study every case also writes
``logs/dump_<R>_<D>_<layout>_<grid>.csv`` with the per-frequency radiation damping, RAO, PTO damping and power density
of the five WECs (disable with ``--no-dump``).
"""

import argparse
import csv
import math
import os
import shutil
import sys
import time
import warnings

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.physics import calculate_power, calculate_rao_matrix, run_wamit, write_wamit_inputs  # noqa: E402
from src.physics.rao_calc import EXCITATION_FILES, get_volumes_from_out  # noqa: E402
from src.physics.wamit_handler import OMEGA_MIN, OMEGA_STEP  # noqa: E402
from src.physics.wave_spectrum import get_jonswap_spectrum  # noqa: E402
from src.problems.layout_opt import get_layout_config  # noqa: E402
from src.utils.config_parser import parse_wec_cfg  # noqa: E402
from src.utils.data_handler import load_env_data  # noqa: E402
from src.utils.mapper import decode_symmetric_positions  # noqa: E402

LATTICE = OMEGA_STEP / 4  # 0.0125 rad/s: fine points always lie on this lattice, so coarse points coincide with it
REF_STEP = LATTICE / 2  # 0.00625 rad/s: step of the reference grid
FINE_STEPS = (REF_STEP / 2, REF_STEP, LATTICE)  # allowed stage-2 steps: 0.003125, 0.00625, 0.0125 rad/s
GRAVITY = 9.80665
RHO = 1025.0
# criterion (a): accuracy first; time is compared with the cheapest uniform grid of the same accuracy
ACC_TOTAL_PCT = 0.1
ACC_WEC_PCT = 0.3
TIME_RATIO_MAX = 1.0  # candidate time <= TIME_RATIO_MAX x time of the cheapest accurate uniform grid
LAYOUTS = {"A": [8.0, 14.0, 6.0, 22.0, 12.0], "B": [5.0, 9.0, 4.5, 13.0, 9.0]}  # x1, x2, y2, x3, y3 (A: gap 8.5 m)
# two-stage candidates: stage-2 step = estimated FWHM / n; window = +- WINDOW_FWHM x FWHM (at least MIN_HALF_WINDOW)
TWO_STAGE_VARIANTS = {"two_stage_fwhm6": 6.0, "two_stage_fwhm10": 10.0}
WINDOW_FWHM = 4.0
MIN_HALF_WINDOW = 0.1
MAX_NEW_POINTS = 250  # if a stage-2 plan needs more new frequencies, the step is made coarser


# ---------------------------------------------------------------------------------------------
# candidate grids (prototypes of what the design proposes; the production code comes after review)
# ---------------------------------------------------------------------------------------------
def heave_omega0(radius, draft):
    """Hydrostatic heave natural frequency without added mass: sqrt(C33 / m) = sqrt(g / (D + 2R/3))."""
    return math.sqrt(GRAVITY / (draft + 2.0 * radius / 3.0))


def snap(value):
    return round(value / LATTICE) * LATTICE


def uniform_grid(omega_max, step=OMEGA_STEP):
    n = math.floor((omega_max - OMEGA_MIN) / step + 1e-9) + 1
    return [round(OMEGA_MIN + k * step, 6) for k in range(n)]


def adaptive_grid(
    radius,
    draft,
    omega_max,
    lo_ratio=0.7,
    hi_ratio=1.0,
    fine_step=LATTICE,
    coarse_step=OMEGA_STEP,
    tail_ratio=None,
    tail_step=2 * OMEGA_STEP,
):
    """Coarse grid everywhere, fine grid in ``[lo_ratio, hi_ratio] * omega0``, optional thinning above the resonance."""
    w0 = heave_omega0(radius, draft)
    lo = snap(max(OMEGA_MIN, lo_ratio * w0))
    hi = snap(min(omega_max, hi_ratio * w0))
    tail_from = snap(tail_ratio * w0) if tail_ratio else None
    points = set()
    for w in uniform_grid(omega_max, coarse_step):
        if lo < w < hi:
            continue
        if tail_from is not None and w > tail_from:
            k = (w - OMEGA_MIN) / tail_step
            if abs(k - round(k)) > 1e-6:
                continue
        points.add(round(w, 6))
    if lo < hi:
        n_fine = round((hi - lo) / fine_step)
        points.update(round(lo + k * fine_step, 6) for k in range(n_fine + 1))
    return sorted(points)


def align_to_ncpu(grid, ncpu, mode, focus):
    """Make the number of frequencies a multiple of ``ncpu``: ``up`` bisects the widest gaps (near ``focus`` first),
    ``down`` drops the highest frequencies. WAMIT runs the frequencies in rounds of ``ncpu``, so a partial round costs
    as much as a full one."""
    grid = sorted(grid)
    if mode == "off" or len(grid) % ncpu == 0:
        return grid
    if mode == "down":
        return grid[: len(grid) - len(grid) % ncpu]
    while len(grid) % ncpu:
        gaps = [
            (round(grid[i + 1] - grid[i], 6), -abs(0.5 * (grid[i + 1] + grid[i]) - focus), i)
            for i in range(len(grid) - 1)
        ]
        _, _, i = max(gaps)
        grid.insert(i + 1, round(0.5 * (grid[i] + grid[i + 1]), 6))
    return grid


# ---------------------------------------------------------------------------------------------
# two-stage grid: locate the resonances in the stage-1 results, add frequencies where they are narrow
# ---------------------------------------------------------------------------------------------
def read_hydro(workdir, num_wecs, rho=RHO, g=GRAVITY, excitation="diffraction"):
    """Heave A(omega), B(omega) matrices and exciting force F(omega) from the WAMIT files (``rao_calc`` scaling)."""
    heave_dofs = {3 + 6 * k: k for k in range(num_wecs)}
    hydro, force = {}, {}
    with open(os.path.join(workdir, "wec.1")) as f:
        next(f)
        for line in f:
            if not line.strip() or line.startswith(("C", "*")):
                continue
            cols = line.split()
            omega, i, j = float(cols[0]), int(cols[1]), int(cols[2])
            if i in heave_dofs and j in heave_dofs:
                entry = hydro.setdefault(
                    omega, {"A": np.zeros((num_wecs, num_wecs)), "B": np.zeros((num_wecs, num_wecs))}
                )
                entry["A"][heave_dofs[i], heave_dofs[j]] = float(cols[3]) * rho
                entry["B"][heave_dofs[i], heave_dofs[j]] = float(cols[4]) * rho * omega
    with open(os.path.join(workdir, EXCITATION_FILES[excitation])) as f:
        next(f)
        for line in f:
            if not line.strip() or line.startswith(("C", "*")):
                continue
            cols = line.split()
            omega, i = float(cols[0]), int(cols[2])
            if i in heave_dofs:
                value = complex(float(cols[5]), float(cols[6])) * (rho * g)
                force.setdefault(omega, np.zeros(num_wecs, dtype=complex))[heave_dofs[i]] = value
    return hydro, force


def read_stiffness(workdir, heave_dof=3, rho=RHO, g=GRAVITY):
    """Heave hydrostatic stiffness C33 (same for all WECs) from ``wec.hst``, ``rao_calc`` scaling."""
    with open(os.path.join(workdir, "wec.hst")) as f:
        next(f)
        for line in f:
            if not line.strip() or line.startswith(("C", "*")):
                continue
            cols = line.split()
            if len(cols) >= 3 and int(cols[0]) == int(cols[1]) == heave_dof:
                return float(cols[2]) * rho * g
    raise ValueError(f"no heave stiffness found in {workdir}")


def resonance_estimates(workdir, num_wecs=5, rho=RHO, g=GRAVITY):
    """Per WEC: uncontrolled RAO peak node and an estimate of the resonance width from the stage-1 coefficients.

    The uncontrolled response is ``X = F / (-w^2 (M + A) + i w B + C)`` (the first step of ``calculate_rao_matrix``).
    For a single oscillator the half-power width is ``(B + B_pto) / (M + A)``; ``B_pto`` equals ``B_kk`` at the peak, so
    ``fwhm = 2 B_kk / (M_k + A_kk)`` evaluated at the peak node.
    """
    volumes = get_volumes_from_out(workdir, num_wecs)
    mass = np.array([rho * v for v in volumes])
    stiffness = read_stiffness(workdir, rho=rho, g=g)
    hydro, force = read_hydro(workdir, num_wecs, rho, g)
    omegas = sorted(hydro)
    base = np.array(
        [
            np.abs(
                np.linalg.solve(
                    -(w**2) * (np.diag(mass) + hydro[w]["A"]) + 1j * w * hydro[w]["B"] + stiffness * np.eye(num_wecs),
                    force[w],
                )
            )
            for w in omegas
        ]
    )
    estimates = []
    for k in range(num_wecs):
        i = int(np.argmax(base[:, k]))
        w = omegas[i]
        estimates.append(
            {
                "omega_peak": float(w),
                "fwhm": float(2.0 * hydro[w]["B"][k, k] / (mass[k] + hydro[w]["A"][k, k])),
                "index": i,
            }
        )
    return estimates


def merge_windows(windows):
    """Union of ``(lo, hi)`` intervals."""
    merged = []
    for lo, hi in sorted(windows):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(lo, hi) for lo, hi in merged]


def two_stage_grid(
    estimates,
    existing,
    per_fwhm,
    omega_max,
    window_fwhm=WINDOW_FWHM,
    min_half=MIN_HALF_WINDOW,
    max_new=MAX_NEW_POINTS,
):
    """Stage-2 frequencies for the resonances in ``estimates`` (dicts with ``omega_peak`` and ``fwhm``).

    Every resonance gets its own window ``omega_peak +- max(window_fwhm * fwhm, min_half)`` filled with multiples of the
    largest of ``FINE_STEPS`` not exceeding ``fwhm / per_fwhm`` (a broad resonance is not forced to the step of a
    narrow one; all steps are multiples of 0.003125, so the lattices nest). Frequencies already in ``existing`` are
    not repeated. If more than ``max_new`` frequencies would be needed, every step is made one level coarser (never
    beyond 0.0125). Returns ``(new_frequencies, finest_step, merged_windows)``.
    """
    steps = sorted(FINE_STEPS)

    def step_for(fwhm, shift):
        fits = [i for i, s in enumerate(steps) if s <= fwhm / per_fwhm]
        return steps[min((fits[-1] if fits else 0) + shift, len(steps) - 1)]

    taken = {round(w, 6) for w in existing}
    shift = 0
    while True:
        points, windows = set(), []
        for e in estimates:
            half = max(window_fwhm * e["fwhm"], min_half)
            lo, hi = max(OMEGA_MIN, e["omega_peak"] - half), min(omega_max, e["omega_peak"] + half)
            step = step_for(e["fwhm"], shift)
            windows.append((lo, hi))
            points.update(
                round(k * step, 6) for k in range(math.ceil(lo / step - 1e-9), math.floor(hi / step + 1e-9) + 1)
            )
        new = sorted(points - taken)
        if len(new) <= max_new or all(step_for(e["fwhm"], shift) == steps[-1] for e in estimates):
            return new, min(step_for(e["fwhm"], shift) for e in estimates), merge_windows(windows)
        shift += 1


def merge_wamit_outputs(dir1, dir2, dest, excitation="diffraction"):
    """Combine the frequency-dependent outputs of two runs (same geometry) so ``calculate_rao_matrix`` can read them."""
    os.makedirs(dest, exist_ok=True)
    for name in ("wec.out", "wec.hst"):
        shutil.copy2(os.path.join(dir1, name), os.path.join(dest, name))
    for name in ("wec.1", EXCITATION_FILES[excitation]):
        with open(os.path.join(dir1, name)) as f:
            first = f.read().splitlines()
        with open(os.path.join(dir2, name)) as f:
            second = f.read().splitlines()
        with open(os.path.join(dest, name), "w") as f:
            f.write("\n".join(first + second[1:]) + "\n")  # the second file's header line is dropped


def density_fwhm(omegas, density):
    """Full width at half maximum of every column of ``density`` (linear interpolation of the half-height crossings)."""
    omegas = np.asarray(omegas)
    widths = []
    for k in range(density.shape[1]):
        d = density[:, k]
        i = int(np.argmax(d))
        half = d[i] / 2.0
        lo = i
        while lo > 0 and d[lo] > half:
            lo -= 1
        hi = i
        while hi < len(d) - 1 and d[hi] > half:
            hi += 1
        w_lo = omegas[lo]
        if d[lo] <= half < d[lo + 1]:
            w_lo = omegas[lo] + (half - d[lo]) * (omegas[lo + 1] - omegas[lo]) / (d[lo + 1] - d[lo])
        w_hi = omegas[hi]
        if d[hi] <= half < d[hi - 1]:
            w_hi = omegas[hi] + (half - d[hi]) * (omegas[hi - 1] - omegas[hi]) / (d[hi - 1] - d[hi])
        widths.append(float(w_hi - w_lo))
    return widths


# ---------------------------------------------------------------------------------------------
# diagnostics: where did B_pto come from, per-frequency dump, verdicts
# ---------------------------------------------------------------------------------------------
def radiation_damping(workdir, num_wecs=5, rho=RHO):
    """Dimensional diagonal heave radiation damping B_kk(omega) read from ``wec.1`` (same scaling as ``rao_calc``)."""
    damping = [{} for _ in range(num_wecs)]
    with open(os.path.join(workdir, "wec.1")) as f:
        next(f)
        for line in f:
            if not line.strip() or line.startswith(("C", "*")):
                continue
            cols = line.split()
            if len(cols) < 5:
                continue
            w, i, j = float(cols[0]), int(cols[1]), int(cols[2])
            if i == j and i >= 3 and (i - 3) % 6 == 0 and (i - 3) // 6 < num_wecs:
                damping[(i - 3) // 6][w] = float(cols[4]) * rho * w
    return damping


def uncontrolled_peaks(damping, b_pto):
    """Frequency where B_kk equals the PTO damping chosen by ``calculate_rao_matrix`` (= the uncontrolled RAO peak)."""
    return [min(d, key=lambda w, d=d, b=b: abs(d[w] - b)) for d, b in zip(damping, b_pto, strict=True)]


def write_dump(path, omegas, spectrum, rao, b_pto, damping, density):
    """Per-frequency table of one case: omega, S(omega), and for each WEC k: B_k, rao_k, bpto_k, density_k."""
    n_wec = rao.shape[1]
    header = ["omega", "S"]
    for k in range(1, n_wec + 1):
        header += [f"B{k}", f"rao{k}", f"bpto{k}", f"density{k}"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i, w in enumerate(omegas):
            row = [f"{w:.6f}", f"{spectrum[i]:.9g}"]
            for k in range(n_wec):
                b_k = damping[k].get(float(w), float("nan"))
                row += [f"{b_k:.9g}", f"{rao[i, k]:.9g}", f"{b_pto[k]:.9g}", f"{density[i, k]:.9g}"]
            writer.writerow(row)


def percent_errors(total, per_wec, base_total, base_per_wec):
    """(total error %, worst single-WEC error %) versus a base result; NaN when there is no base."""
    if not base_per_wec or not per_wec:
        return float("nan"), float("nan")
    err = (total / base_total - 1) * 100
    worst = max(abs(a / b - 1) for a, b in zip(per_wec, base_per_wec, strict=True)) * 100
    return err, worst


def evaluate_verdicts(rows):
    """Criterion (a) per case.

    ``rows``: dicts with R, D, layout, grid, n_freq, time_s, err_total_pct, worst_wec_err_pct; ``check_*`` rows are
    ignored.

    A grid is *accurate* if |total error| <= ACC_TOTAL_PCT and the worst WEC error <= ACC_WEC_PCT versus the reference.
    The time yardstick is the cheapest accurate *uniform* grid (the reference itself is always accurate). A candidate
    passes if it is accurate and its time <= TIME_RATIO_MAX x that yardstick.
    """
    groups = {}
    for r in rows:
        groups.setdefault((r["R"], r["D"], r["layout"]), []).append(r)
    verdicts = []
    for (radius, draft, layout), group in groups.items():
        for r in group:
            r["accurate"] = abs(r["err_total_pct"]) <= ACC_TOTAL_PCT and r["worst_wec_err_pct"] <= ACC_WEC_PCT
        uniform = [r for r in group if r["grid"].startswith(("uniform_", "ref_uniform")) and "aligned" not in r["grid"]]
        accurate_uniform = [r["time_s"] for r in uniform if r["accurate"]]
        current = next((r for r in group if r["grid"] == "uniform_0.05"), None)
        yardstick = min(accurate_uniform) if accurate_uniform else float("nan")
        for r in group:
            if r["grid"].startswith(("ref_", "check_")):
                continue
            ratio_equal = r["time_s"] / yardstick if yardstick == yardstick else float("nan")
            ratio_current = r["time_s"] / current["time_s"] if current else float("nan")
            time_ok = bool(ratio_equal <= TIME_RATIO_MAX)
            verdicts.append(
                {
                    "R": radius,
                    "D": draft,
                    "layout": layout,
                    "grid": r["grid"],
                    "n_freq": r["n_freq"],
                    "time_s": r["time_s"],
                    "err_total_pct": r["err_total_pct"],
                    "worst_wec_err_pct": r["worst_wec_err_pct"],
                    "accurate": r["accurate"],
                    "equal_accuracy_uniform_time_s": yardstick,
                    "time_ratio_vs_equal_accuracy_uniform": ratio_equal,
                    "time_ratio_vs_current_uniform_0.05": ratio_current,
                    "time_ok": time_ok,
                    "verdict": "PASS" if r["accurate"] and time_ok else "fail",
                }
            )
    return verdicts


def summarize_verdicts(verdicts):
    """Pass counts per candidate grid, as printable lines."""
    names = list(dict.fromkeys(v["grid"] for v in verdicts))
    lines = ["candidate                                   accurate  time_ok  PASS   (cases)"]
    for name in names:
        group = [v for v in verdicts if v["grid"] == name]
        lines.append(
            f"{name:<43} {sum(v['accurate'] for v in group):>5}   {sum(v['time_ok'] for v in group):>6}  "
            f"{sum(v['verdict'] == 'PASS' for v in group):>4}   ({len(group)})"
        )
    return lines


# ---------------------------------------------------------------------------------------------
# running one case
# ---------------------------------------------------------------------------------------------
def make_context(panels, ncpu):
    cfg = parse_wec_cfg(os.path.join(ROOT, "config.cfg"))
    env = load_env_data(int(cfg["Environment"]["SiteID"]))
    wamit = {"NCPU": ncpu, "RAMGBMAX": int(cfg["WAMIT Settings"]["RAMGBMAX"]), "MeshPanels": panels, "Solver": 0}
    return cfg, env, wamit


def case_config(ctx, radius, draft, panels, ncpu):
    cfg, env, wamit = ctx
    wamit = dict(wamit, NCPU=ncpu, MeshPanels=panels)
    config = get_layout_config(
        cfg["Constraints"], cfg["WEC Parameters"], 5, env, wamit, int(cfg["Simulation"]["WaveSpec"])
    )
    config.update(fixed_radius=radius, fixed_draft=draft, solver=0, mesh_panels=panels)
    return config


def prepare_case(config, workdir, layout, grid):
    """Write the WAMIT inputs for ``config`` with the explicit frequency list ``grid``; returns the quarter panels."""
    positions = decode_symmetric_positions(LAYOUTS[layout], 5)
    write_wamit_inputs(None, config, workdir, positions=positions)
    pot_path = os.path.join(workdir, "wec.pot")
    with open(pot_path) as f:
        lines = f.read().splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip().endswith("NPER"))
    lines[start : start + 2] = [f"{len(grid):<20} NPER"] + [f"{w:.6f}" for w in grid]  # explicit list (IPERIN=2: rad/s)
    with open(pot_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(workdir, "wec.gdf")) as gdf_file:
        return int(gdf_file.read().split("\n")[3].split()[0])


def evaluate_workdir(workdir, config, quarter, n_freq, elapsed, dump_path=None):
    """RAO, power and diagnostics of the WAMIT outputs in ``workdir`` (``elapsed`` = WAMIT time of the run(s))."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        results = calculate_rao_matrix(workdir, 5)
        total, per_wec = calculate_power(results, config)
    omegas = np.array([r["omega"] for r in results])
    rao = np.array([r["rao_abs"] for r in results])
    b_pto = np.array(results[0]["b_pto"])
    peaks = [float(omegas[int(np.argmax(rao[:, k]))]) for k in range(5)]
    damping = radiation_damping(workdir)
    spectrum = get_jonswap_spectrum(
        omegas, float(config["hs"]), float(config["tp"]), float(config["gamma"]), int(config["wave_spec"])
    )
    density = b_pto[None, :] * omegas[:, None] ** 2 * rao**2 * spectrum[:, None]
    if dump_path:
        write_dump(dump_path, omegas, spectrum, rao, b_pto, damping, density)
    return {
        "quarter_panels": quarter,
        "n_freq": n_freq,
        "time_s": elapsed,
        "total_W": float(total),
        "per_wec_W": [float(p) for p in per_wec],
        "peak_omega": peaks,
        "peak_unctrl": uncontrolled_peaks(damping, b_pto),
        "bpto": [float(b) for b in b_pto],
        "omegas": omegas,
        "density": density,
    }


def run_case(ctx, workdir, radius, draft, layout, grid, panels, ncpu, dry_run=False, dump_path=None, evaluate=True):
    config = case_config(ctx, radius, draft, panels, ncpu)
    quarter = prepare_case(config, workdir, layout, grid)
    if dry_run:
        return {
            "quarter_panels": quarter,
            "n_freq": len(grid),
            "time_s": 0.0,
            "total_W": float("nan"),
            "per_wec_W": [],
            "peak_omega": [],
            "peak_unctrl": [],
            "bpto": [],
            "omegas": None,
            "density": None,
            "config": config,
        }
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_wamit(workdir)
    elapsed = time.time() - t0
    if not evaluate:
        return {"quarter_panels": quarter, "n_freq": len(grid), "time_s": elapsed, "config": config}
    result = evaluate_workdir(workdir, config, quarter, len(grid), elapsed, dump_path)
    result["config"] = config
    return result


class Csv:
    def __init__(self, name, out_dir, fields):
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, f"freq_grid_study_{name}.csv")
        self.f = open(self.path, "w", newline="", encoding="utf-8")  # noqa: SIM115
        self.w = csv.DictWriter(self.f, fieldnames=fields)
        self.w.writeheader()

    def row(self, **kw):
        self.w.writerow(kw)
        self.f.flush()
        print("  " + "  ".join(f"{k}={v}" for k, v in kw.items()), flush=True)


# ---------------------------------------------------------------------------------------------
# studies
# ---------------------------------------------------------------------------------------------
def candidate_grids(radius, draft, omax, ncpu, include_check=False):
    """Ordered candidate grids for one design. The first entry is the reference.

    ``include_check`` adds a 0.003125 grid right after the reference (for very narrow resonances), used to test whether
    the 0.00625 reference itself has converged. The two-stage candidates are not listed here: they are built from the
    stage-1 results of ``uniform_0.05`` (see ``study_grids``).
    """
    w0 = heave_omega0(radius, draft)
    adaptive = adaptive_grid
    grids = {"ref_uniform_0.00625": uniform_grid(omax, REF_STEP)}
    if include_check:
        grids["check_uniform_0.003125"] = uniform_grid(omax, REF_STEP / 2)
    grids.update(
        {
            "uniform_0.05": uniform_grid(omax),
            "uniform_0.025": uniform_grid(omax, 2 * LATTICE),
            "uniform_0.0125": uniform_grid(omax, LATTICE),
            "adaptive_0.7_1.0_tail0.1": adaptive(radius, draft, omax, 0.7, 1.0, tail_ratio=1.5),
            "adaptive_0.8_1.0_tail0.1": adaptive(radius, draft, omax, 0.8, 1.0, tail_ratio=1.5),
            "adaptive_0.85_1.0_tail0.1": adaptive(radius, draft, omax, 0.85, 1.0, tail_ratio=1.5),
            "adaptive_0.8_1.0_fine0.00625_tail0.1": adaptive(
                radius, draft, omax, 0.8, 1.0, fine_step=REF_STEP, tail_ratio=1.5
            ),
            "adaptive_0.85_1.1_tail0.1": adaptive(radius, draft, omax, 0.85, 1.1, tail_ratio=1.5),
            "adaptive_0.85_1.1_fine0.00625_tail0.1": adaptive(
                radius, draft, omax, 0.85, 1.1, fine_step=REF_STEP, tail_ratio=1.5
            ),
        }
    )
    narrow = grids["adaptive_0.85_1.0_tail0.1"]
    grids["adaptive_0.85_1.0_tail0.1_aligned_up"] = align_to_ncpu(narrow, ncpu, "up", w0)
    grids["adaptive_0.85_1.0_tail0.1_aligned_down"] = align_to_ncpu(narrow, ncpu, "down", w0)
    return grids


GRID_FIELDS = [
    "R",
    "D",
    "layout",
    "w0",
    "grid",
    "n_freq",
    "time_s",
    "total_W",
    "err_total_pct",
    "worst_wec_err_pct",
    "peak_omega_median",
    "peak_over_w0",
    "peak_unctrl_median",
    "peak_unctrl_over_w0",
    "err_total_vs_check_pct",
    "worst_wec_err_vs_check_pct",
    "bpto",
    "stage2_step",
    "n_stage2",
    "fwhm_est_min",
    "fwhm_meas_min",
]


def study_grids(args):
    ctx = make_context(args.panels, args.ncpu)
    if args.quick:
        designs = [(2.5, 5.0), (1.5, 2.5), (0.5, 0.5), (0.5, 2.0)]
        layouts = ["A"]
    else:
        designs = [(r, d) for r in (0.5, 1.5, 2.5) for d in (0.5, 2.0, 5.0)]
        layouts = ["A", "B"]
    out = Csv("grids", args.out, GRID_FIELDS)
    collected = []
    nan = float("nan")
    for radius, draft in designs:
        w0 = heave_omega0(radius, draft)
        omax = max(3.0, math.ceil(1.2 * w0 / OMEGA_STEP) * OMEGA_STEP)  # make sure the resonance is inside the grid
        candidates = candidate_grids(radius, draft, omax, args.ncpu, include_check=(radius, draft) == (0.5, 2.0))
        for layout in layouts:
            print(f"== R={radius} D={draft} layout {layout}: w0={w0:.3f} rad/s, omega_max={omax:.2f}", flush=True)
            base_dir = os.path.join(ROOT, "workspace", f"sg_{radius}_{draft}_{layout}")
            shutil.rmtree(base_dir, ignore_errors=True)
            results, dirs, extras = {}, {}, {}
            for idx, (name, grid) in enumerate(candidates.items()):
                dirs[name] = os.path.join(base_dir, f"c{idx:02d}")  # short paths: 32-bit WAMIT dislikes long ones
                dump = None
                if not (args.no_dump or args.dry_run):
                    os.makedirs(args.out, exist_ok=True)
                    dump = os.path.join(args.out, f"dump_{radius}_{draft}_{layout}_{name}.csv")
                results[name] = run_case(
                    ctx, dirs[name], radius, draft, layout, grid, args.panels, args.ncpu, args.dry_run, dump
                )
            # two-stage candidates: stage 1 = the uniform 0.05 run above, stage 2 = frequencies around the resonances
            if args.dry_run:
                print("  (dry run: two-stage candidates need stage-1 results and are skipped)", flush=True)
            else:
                stage1, grid1 = results["uniform_0.05"], candidates["uniform_0.05"]
                estimates = resonance_estimates(dirs["uniform_0.05"])
                fwhm_est = min(e["fwhm"] for e in estimates)
                print(
                    "  stage 1 resonances: "
                    + ", ".join(f"{e['omega_peak']:.3f} (fwhm~{e['fwhm']:.3f})" for e in estimates),
                    flush=True,
                )
                for name, per_fwhm in TWO_STAGE_VARIANTS.items():
                    new, step, _ = two_stage_grid(estimates, grid1, per_fwhm, omax)
                    if new:
                        stage2_dir = os.path.join(base_dir, f"{name}_stage2")
                        stage2 = run_case(
                            ctx, stage2_dir, radius, draft, layout, new, args.panels, args.ncpu, evaluate=False
                        )
                        merged_dir = os.path.join(base_dir, f"{name}_merged")
                        merge_wamit_outputs(dirs["uniform_0.05"], stage2_dir, merged_dir)
                    else:  # nothing to add: the stage-1 grid is already fine enough
                        stage2, merged_dir = {"time_s": 0.0}, dirs["uniform_0.05"]
                    dump = (
                        None if args.no_dump else os.path.join(args.out, f"dump_{radius}_{draft}_{layout}_{name}.csv")
                    )
                    results[name] = evaluate_workdir(
                        merged_dir,
                        stage1["config"],
                        stage1["quarter_panels"],
                        len(grid1) + len(new),
                        stage1["time_s"] + stage2["time_s"],
                        dump,
                    )
                    extras[name] = {"stage2_step": step, "n_stage2": len(new), "fwhm_est_min": fwhm_est}
            ref = results["ref_uniform_0.00625"]
            check = results.get("check_uniform_0.003125")
            fwhm_meas = min(density_fwhm(ref["omegas"], ref["density"])) if ref["omegas"] is not None else nan
            for name, res in results.items():
                err = worst = err_c = worst_c = nan
                if not args.dry_run:
                    err, worst = percent_errors(res["total_W"], res["per_wec_W"], ref["total_W"], ref["per_wec_W"])
                if check and not args.dry_run:
                    err_c, worst_c = percent_errors(
                        res["total_W"], res["per_wec_W"], check["total_W"], check["per_wec_W"]
                    )
                peak = float(np.median(res["peak_omega"])) if res["peak_omega"] else nan
                peak_u = float(np.median(res["peak_unctrl"])) if res["peak_unctrl"] else nan
                extra = extras.get(name, {})
                out.row(
                    R=radius,
                    D=draft,
                    layout=layout,
                    w0=round(w0, 4),
                    grid=name,
                    n_freq=res["n_freq"],
                    time_s=round(res["time_s"], 1),
                    total_W=round(res["total_W"], 1),
                    err_total_pct=round(err, 3),
                    worst_wec_err_pct=round(worst, 3),
                    peak_omega_median=round(peak, 4),
                    peak_over_w0=round(peak / w0, 3) if peak == peak else "",
                    peak_unctrl_median=round(peak_u, 4),
                    peak_unctrl_over_w0=round(peak_u / w0, 3) if peak_u == peak_u else "",
                    err_total_vs_check_pct=round(err_c, 3),
                    worst_wec_err_vs_check_pct=round(worst_c, 3),
                    bpto=";".join(f"{b:.2f}" for b in res["bpto"]),
                    stage2_step=extra.get("stage2_step", ""),
                    n_stage2=extra.get("n_stage2", ""),
                    fwhm_est_min=round(extra["fwhm_est_min"], 4) if extra else "",
                    fwhm_meas_min=round(fwhm_meas, 4) if extra and fwhm_meas == fwhm_meas else "",
                )
                if not name.startswith("check_"):
                    collected.append(
                        {
                            "R": radius,
                            "D": draft,
                            "layout": layout,
                            "grid": name,
                            "n_freq": res["n_freq"],
                            "time_s": res["time_s"],
                            "err_total_pct": err,
                            "worst_wec_err_pct": worst,
                        }
                    )
            shutil.rmtree(base_dir, ignore_errors=True)  # keep the job folder small
    print("csv:", out.path)
    if args.dry_run:
        return
    verdicts = evaluate_verdicts(collected)
    verdict_out = Csv("grids_verdict", args.out, list(verdicts[0].keys()) if verdicts else ["grid"])
    for v in verdicts:
        verdict_out.w.writerow({k: (round(x, 3) if isinstance(x, float) else x) for k, x in v.items()})
    verdict_out.f.flush()
    print(
        f"\n##### verdict (criterion (a): total <= {ACC_TOTAL_PCT}%, worst WEC <= {ACC_WEC_PCT}%, "
        f"time <= {TIME_RATIO_MAX:g} x cheapest accurate uniform grid)"
    )
    for line in summarize_verdicts(verdicts):
        print(line, flush=True)
    print("csv:", verdict_out.path)


def study_ncpu(args):
    ctx = make_context(args.panels, args.ncpu)
    radius, draft = 2.5, 5.0
    out = Csv("ncpu", args.out, ["NCPU", "n_freq", "n_freq_mod_ncpu", "time_s", "total_W"])
    for ncpu in (1, 2, 4, 6, 8, 12, 16):
        if args.quick and ncpu in (1, 2, 12):
            continue
        for n_freq in (48, 51, 56, 64):
            grid = uniform_grid(OMEGA_MIN + OMEGA_STEP * (n_freq - 1))
            workdir = os.path.join(ROOT, "workspace", f"study_ncpu_{ncpu}_{n_freq}")
            res = run_case(ctx, workdir, radius, draft, "A", grid, args.panels, ncpu, args.dry_run)
            out.row(
                NCPU=ncpu,
                n_freq=n_freq,
                n_freq_mod_ncpu=n_freq % ncpu,
                time_s=round(res["time_s"], 1),
                total_W=round(res["total_W"], 1),
            )
    print("csv:", out.path)


def study_limit(args):
    ctx = make_context(args.panels, args.ncpu)
    out = Csv("limit", args.out, ["R", "D", "NCPU", "quarter_panels", "total_panels", "status", "time_s"])
    grid = uniform_grid(3.0)
    for radius, draft in ((2.5, 5.0), (2.5, 0.5), (0.5, 2.0)):
        for ncpu in (4, 8, 16):
            for target in (160, 190, 220, 250, 280, 320, 400):
                workdir = os.path.join(ROOT, "workspace", f"study_limit_{radius}_{draft}_{ncpu}")
                try:
                    res = run_case(ctx, workdir, radius, draft, "A", grid, target, ncpu, args.dry_run)
                    status = "dry-run" if args.dry_run else "ok"
                except Exception as err:  # WAMIT allocation error shows up as a missing output file
                    out.row(
                        R=radius,
                        D=draft,
                        NCPU=ncpu,
                        quarter_panels="",
                        total_panels="",
                        status=f"FAILED ({type(err).__name__})",
                        time_s="",
                    )
                    break
                out.row(
                    R=radius,
                    D=draft,
                    NCPU=ncpu,
                    quarter_panels=res["quarter_panels"],
                    total_panels=res["quarter_panels"] * 5,
                    status=status,
                    time_s=round(res["time_s"], 1),
                )
                if args.quick and res["quarter_panels"] >= 250:
                    break
    print("csv:", out.path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--study", choices=["grids", "ncpu", "limit", "all"], default="grids")
    parser.add_argument("--panels", type=int, default=120, help="quarter-model panels per body (default 120)")
    parser.add_argument("--ncpu", type=int, default=8, help="NCPU for WAMIT (Ryzen 7 9700X: 8 physical cores)")
    parser.add_argument("--out", default=os.path.join(ROOT, "logs"))
    parser.add_argument("--quick", action="store_true", help="fewer cases (smoke test, several minutes)")
    parser.add_argument("--dry-run", action="store_true", help="write inputs only, do not start WAMIT")
    parser.add_argument("--no-dump", action="store_true", help="grids study: no per-frequency dump files")
    args = parser.parse_args(argv)
    studies = {"grids": study_grids, "ncpu": study_ncpu, "limit": study_limit}
    for name in studies if args.study == "all" else [args.study]:
        print(f"##### study: {name}", flush=True)
        studies[name](args)


if __name__ == "__main__":
    main()
