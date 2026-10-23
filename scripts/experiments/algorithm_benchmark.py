"""Benchmark the project's optimizers (DE, PSO, DEPSO, CMA-ES, GA) on standard test functions with an equal budget.

Each algorithm is the project implementation in ``src/algorithms`` (grid quantization and evaluation cache included).
Test functions come from ``de_update_benchmark.py`` and are minimized (global minimum 0); the project optimizers
maximize, so they receive ``-f``. The variables lie on a lattice of ``--grid`` steps (the WEC design variables are on a
0.1 m grid). The budget is the number of calls of the evaluation function, i.e. the number of WAMIT runs in a real
optimization (cache hits are free); every run stops when it reaches ``--budget`` calls. DEPSO evaluates one trial
per particle like DE. ``depso`` is the default greedy rule; ``depso_pbest``, ``depso_pbest_c1zero`` and
``depso_move`` are the comparison variants.

    python scripts/experiments/algorithm_benchmark.py --plot
    python scripts/experiments/algorithm_benchmark.py --algorithms de depso --dims 7 --seeds 5 --budget 5000

Results: ``<out>/algorithm_final.csv`` (best value of every run), ``<out>/algorithm_curves.csv`` (median and quartiles
of the best value against the number of calls) and, with ``--plot`` (needs matplotlib), PNG figures. The optimizer log
files are not written (the logger is replaced by a no-op inside the worker processes).
"""

import argparse
import contextlib
import csv
import importlib.util
import io
import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.stats import mannwhitneyu

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.algorithms import cma_es, de, depso, ga, pso  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "de_update_benchmark", os.path.join(os.path.dirname(__file__), "de_update_benchmark.py")
)
_bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bench)
FUNCTIONS = _bench.FUNCTIONS

ALGORITHMS = {
    # name: (module, runner, keyword arguments, population)
    "de": (de, "run_de", {"F": 0.5, "CR": 0.9}, 100),
    "pso": (pso, "run_pso", {"w": 0.5, "c1": 1.5, "c2": 1.5}, 100),
    "depso": (depso, "run_depso", {"F": 0.5, "CR": 0.9, "w": 0.5, "c1": 1.5, "c2": 1.5}, 100),  # default (greedy)
    "depso_pbest": (
        depso,
        "run_depso",
        {"F": 0.5, "CR": 0.9, "w": 0.5, "c1": 1.5, "c2": 1.5, "update": "pbest"},
        100,
    ),
    "depso_pbest_c1zero": (
        depso,
        "run_depso",
        {"F": 0.5, "CR": 0.9, "w": 0.5, "c1": 0.0, "c2": 1.5, "update": "pbest"},
        100,
    ),
    "depso_move": (depso, "run_depso", {"F": 0.5, "CR": 0.9, "w": 0.5, "c1": 1.5, "c2": 1.5, "update": "move"}, 100),
    "cmaes": (cma_es, "run_cma_es", {"sigma_init": 0.3}, 72),
    "cmaes_minstd0.3": (cma_es, "run_cma_es", {"sigma_init": 0.3, "min_std_factor": 0.3}, 72),
    "cmaes_minstd0.5": (cma_es, "run_cma_es", {"sigma_init": 0.3, "min_std_factor": 0.5}, 72),
    "cmaes_minstd1": (cma_es, "run_cma_es", {"sigma_init": 0.3, "min_std_factor": 1.0}, 72),
    "ga": (ga, "run_ga", {"mutation_rate": 0.1}, 100),
}
CHECKPOINTS = 100  # points of the convergence curve
# lattice steps per variable of the 5-WEC joint problem (0.1 m grid): R 0.5-2.5, D 0.5-5.0, X 3-25, Y 0.1-30
WEC_STEPS = [20, 45, 220, 220, 299, 220, 299]


def lattice_steps(grid, dims):
    """Steps per variable: ``grid`` for every variable, or the WEC pattern (repeated) when ``grid`` is 0."""
    if grid:
        return np.full(dims, float(grid))
    return np.array([WEC_STEPS[k % len(WEC_STEPS)] for k in range(dims)], dtype=float)


class _NoLogger:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _BudgetReached(Exception):
    pass


OPTIMA = {"rosenbrock": 1.0, "schwefel": 420.9687463}  # minimizer coordinate (0 for the other functions)


def rotation(dims):
    """Fixed random orthogonal matrix for ``--rotate`` (non-separable versions of the test functions)."""
    q, r = np.linalg.qr(np.random.default_rng(1000 + dims).normal(size=(dims, dims)))
    return q * np.sign(np.diag(r))


def run_task(task):
    """One optimization run; returns the best value (minimization) after every evaluation call, padded to the budget.

    ``task = (algorithm, function, dims, grid, seed, budget[, rotate])``; with ``rotate`` the function is evaluated at
    ``Q (x - x*) + x*`` (same minimum, variables coupled).
    """
    algo, name, dims, grid, seed, budget, *rest = task
    rotate = bool(rest and rest[0])
    module, runner, kwargs, pop = ALGORITHMS[algo]
    func, lo, hi = FUNCTIONS[name]
    q, x_star = rotation(dims), OPTIMA.get(name, 0.0)
    config = {
        "dimensions": dims,
        "bounds": [[lo] * dims, [hi] * dims],
        "step_size": list((hi - lo) / lattice_steps(grid, dims)),
        "opt_mode": 1,
        "num_wecs": 1,
        "site_name": "bench",
    }
    best = []

    def evaluate(vector, config):
        x = np.asarray(vector, dtype=float)
        if rotate:
            x = q @ (x - x_star) + x_star
        value = float(func(x[np.newaxis, :])[0])
        best.append(min(value, best[-1]) if best else value)
        if len(best) >= budget:
            raise _BudgetReached
        return -value, [-value]

    np.random.seed(seed)
    max_iter = 4 * budget // pop + 10  # enough generations; runs stop at the budget (or earlier if only cache hits)
    logger_class = module.OptimizationLogger
    module.OptimizationLogger = _NoLogger  # no log files for benchmark runs; restored below
    try:
        with contextlib.suppress(_BudgetReached), contextlib.redirect_stdout(io.StringIO()):
            getattr(module, runner)(config, evaluate, pop, max_iter, **kwargs)
    finally:
        module.OptimizationLogger = logger_class
    best += [best[-1]] * (budget - len(best))
    return np.array(best[:budget])


def plot(curves, finals, algorithms, functions, dims_list, budget, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {
        "de": "#2a6fdb",
        "pso": "#3aa655",
        "depso": "#c0392b",
        "depso_pbest": "#e0712c",
        "depso_pbest_c1zero": "#f1c40f",
        "depso_move": "#16a085",
        "cmaes": "#8e44ad",
        "cmaes_minstd0.3": "#5dade2",
        "cmaes_minstd0.5": "#1abc9c",
        "cmaes_minstd1": "#d35400",
        "ga": "#7f7f7f",
    }
    x = np.linspace(budget / CHECKPOINTS, budget, CHECKPOINTS)
    paths = []
    for dims in dims_list:
        fig, axes = plt.subplots(2, 3, figsize=(13, 7.5))
        for ax, name in zip(axes.flat, functions, strict=False):
            for algo in algorithms:
                q = np.maximum(curves[(algo, name, dims)], 1e-12)
                ax.plot(x, q[1], color=colors[algo], label=algo.upper())
                ax.fill_between(x, q[0], q[2], color=colors[algo], alpha=0.15)
            ax.set_yscale("log")
            ax.set_title(name)
            ax.set_xlabel("evaluations (WAMIT runs)")
            ax.set_ylabel("best f (median, quartiles)")
            ax.grid(alpha=0.3)
        axes.flat[0].legend(fontsize=8)
        fig.suptitle(f"Project optimizers, D = {dims}, equal budget {budget} evaluations")
        fig.tight_layout()
        path = os.path.join(out, f"algorithm_curves_D{dims}.png")
        fig.savefig(path, dpi=120)
        plt.close(fig)
        paths.append(path)

        fig, axes = plt.subplots(1, len(functions), figsize=(2.6 * len(functions), 3.6))
        for ax, name in zip(np.atleast_1d(axes), functions, strict=True):
            data = [np.maximum(finals[(algo, name, dims)], 1e-12) for algo in algorithms]
            box = ax.boxplot(data, patch_artist=True, widths=0.6)
            for patch, algo in zip(box["boxes"], algorithms, strict=True):
                patch.set_facecolor(colors[algo])
                patch.set_alpha(0.5)
            ax.set_xticks(range(1, len(algorithms) + 1), [a.upper() for a in algorithms], rotation=45, fontsize=8)
            ax.set_yscale("log")
            ax.set_title(name, fontsize=10)
            ax.grid(alpha=0.3)
        fig.suptitle(f"Final best value after {budget} evaluations, D = {dims}")
        fig.tight_layout()
        path = os.path.join(out, f"algorithm_final_D{dims}.png")
        fig.savefig(path, dpi=120)
        plt.close(fig)
        paths.append(path)
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--algorithms", nargs="+", default=["de", "pso", "depso", "cmaes"], choices=list(ALGORITHMS))
    parser.add_argument("--functions", nargs="+", default=list(FUNCTIONS), choices=list(FUNCTIONS))
    parser.add_argument("--dims", nargs="+", type=int, default=[7, 20])
    parser.add_argument(
        "--grid", type=int, default=300, help="lattice steps per variable (0: steps of the WEC problem, 20 to 299)"
    )
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--budget", type=int, default=30000, help="evaluation calls per run")
    parser.add_argument("--rotate", action="store_true", help="rotated (non-separable) test functions")
    parser.add_argument("--workers", type=int, default=0, help="processes (0: all CPU cores, 1: no parallelism)")
    parser.add_argument("--out", default="logs")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    tasks = [
        (algo, name, dims, args.grid, seed, args.budget, args.rotate)
        for algo, name, dims, seed in itertools.product(args.algorithms, args.functions, args.dims, range(args.seeds))
    ]
    start = time.time()
    workers = args.workers or os.cpu_count() or 1
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run_task, tasks, chunksize=2))
    else:
        results = [run_task(task) for task in tasks]
    print(f"{len(tasks)} runs on {workers} processes in {time.time() - start:.0f} s", flush=True)

    marks = np.linspace(args.budget / CHECKPOINTS, args.budget, CHECKPOINTS).astype(int) - 1
    grouped = {}
    with open(os.path.join(args.out, "algorithm_final.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["algorithm", "function", "dims", "grid", "seed", "best", "budget"])
        for task, best in zip(tasks, results, strict=True):
            algo, name, dims, grid, seed, budget, _ = task
            writer.writerow([algo, name, dims, grid, seed, f"{best[-1]:.6e}", budget])
            grouped.setdefault((algo, name, dims), []).append(best[marks])
    finals, curves = {}, {}
    with open(os.path.join(args.out, "algorithm_curves.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["algorithm", "function", "dims", "evaluations", "q25", "median", "q75"])
        for key, runs in grouped.items():
            runs = np.array(runs)
            finals[key] = runs[:, -1]
            curves[key] = np.percentile(runs, [25, 50, 75], axis=0)
            for m, (q25, q50, q75) in zip(marks + 1, curves[key].T, strict=True):
                writer.writerow([*key, m, f"{q25:.6e}", f"{q50:.6e}", f"{q75:.6e}"])

    for name, dims in itertools.product(args.functions, args.dims):
        medians = "  ".join(f"{a} {np.median(finals[(a, name, dims)]):.3e}" for a in args.algorithms)
        line = f"{name:<10} D={dims:<3} {medians}"
        if "de" in args.algorithms:
            tests = []
            for a in args.algorithms:
                if a != "de":
                    x, y = finals[(a, name, dims)], finals[("de", name, dims)]
                    p = mannwhitneyu(x, y).pvalue if np.any(x != y) else 1.0
                    tests.append(f"{a} vs de p={p:.2g}")
            line += "  | " + ", ".join(tests)
        print(line, flush=True)
    if args.plot:
        for path in plot(curves, finals, args.algorithms, args.functions, args.dims, args.budget, args.out):
            print(f"wrote {path}")
    return finals, curves


if __name__ == "__main__":
    main()
