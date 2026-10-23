"""Benchmark: DE with immediate replacement (the project's DE) versus generation-wise replacement.

The project's ``run_de`` (DE/rand/1/bin) replaces individual i in the population as soon as its trial is better, so the
mutants of individuals i+1, i+2, ... of the same generation already see the improved member ("immediate", also called
asynchronous or steady-state DE). The textbook DE of Storn and Price builds all trials of a generation from the old
population and replaces afterwards ("generation", synchronous DE); only that form lets a whole generation be evaluated
in parallel.

Both variants below use exactly the same operators, random-number calls and parameters as ``run_de`` (the immediate
variant reproduces ``run_de`` step by step, see tests/test_de_update_benchmark.py); they differ only in when the
population is updated. Standard test functions are minimized (global minimum 0):

    sphere, rosenbrock, rastrigin, ackley, griewank, schwefel

``--grid N`` also runs every case on a lattice of N steps per variable (the WEC design variables are on a 0.1 m grid).

    python scripts/experiments/de_update_benchmark.py                       # D = 7 and 20, 30 seeds, 300 generations
    python scripts/experiments/de_update_benchmark.py --dims 7 --seeds 5 --gens 50 --plot

Results: ``<out>/de_update_final.csv`` (best value of every run), ``<out>/de_update_curves.csv`` (median and quartiles
of the best value per generation) and, with ``--plot`` (needs matplotlib, not a project dependency), PNG figures.
"""

import argparse
import csv
import itertools
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.stats import mannwhitneyu

FUNCTIONS = {
    # name: (function of a 2-D array (n, D) -> (n,), lower bound, upper bound)
    "sphere": (lambda x: np.sum(x**2, axis=1), -5.12, 5.12),
    "rosenbrock": (lambda x: np.sum(100 * (x[:, 1:] - x[:, :-1] ** 2) ** 2 + (1 - x[:, :-1]) ** 2, axis=1), -5.0, 10.0),
    "rastrigin": (lambda x: 10 * x.shape[1] + np.sum(x**2 - 10 * np.cos(2 * np.pi * x), axis=1), -5.12, 5.12),
    "ackley": (
        lambda x: (
            -20 * np.exp(-0.2 * np.sqrt(np.mean(x**2, axis=1)))
            - np.exp(np.mean(np.cos(2 * np.pi * x), axis=1))
            + 20
            + np.e
        ),
        -32.768,
        32.768,
    ),
    "griewank": (
        lambda x: 1 + np.sum(x**2, axis=1) / 4000 - np.prod(np.cos(x / np.sqrt(np.arange(1, x.shape[1] + 1))), axis=1),
        -600.0,
        600.0,
    ),
    "schwefel": (
        lambda x: 418.9828872724338 * x.shape[1] - np.sum(x * np.sin(np.sqrt(np.abs(x))), axis=1),
        -500.0,
        500.0,
    ),
}
MODES = ("immediate", "generation")


def evaluate(func, x):
    return float(func(np.asarray(x, dtype=float)[np.newaxis, :])[0])


def quantize(x, lower, step, max_index):
    """Same rule as ``src.algorithms.common.quantize_vector``."""
    index = np.clip(np.floor((x - lower) / step + 0.5).astype(int), 0, max_index)
    return np.round(lower + index * step, 10)


def run(objective, lower, upper, dims, pop_size, gens, F, CR, mode, step=None):
    """Minimize ``objective``; returns the best value after the initial population and after every generation.

    The random-number calls are those of ``run_de`` (global ``np.random``; seed it before calling).
    """
    lower = np.full(dims, float(lower))
    upper = np.full(dims, float(upper))
    if step is not None:
        step = np.full(dims, float(step))
        ratio = (upper - lower) / step
        max_index = np.floor(ratio + 1e-9 * np.maximum(1.0, np.abs(ratio))).astype(int)  # grid_max_indices
        index = np.array([np.random.randint(0, m + 1, size=pop_size) for m in max_index]).T
        population = np.round(lower + index * step, 10)
    else:
        population = lower + np.random.rand(pop_size, dims) * (upper - lower)
    fitness = np.array([objective(ind) for ind in population])
    history = [float(fitness.min())]
    for _ in range(gens):
        trials = []
        for i in range(pop_size):
            idxs = [idx for idx in range(pop_size) if idx != i]
            a, b, c = population[np.random.choice(idxs, 3, replace=False)]
            mutant = a + F * (b - c)
            cross_points = np.random.rand(dims) < CR
            if not np.any(cross_points):
                cross_points[np.random.randint(0, dims)] = True
            trial = np.where(cross_points, mutant, population[i])
            trial = quantize(trial, lower, step, max_index) if step is not None else np.clip(trial, lower, upper)
            if mode == "immediate":
                score = objective(trial)
                if score < fitness[i]:
                    fitness[i] = score
                    population[i] = trial
            else:
                trials.append(trial)
        if mode == "generation":
            for i, trial in enumerate(trials):  # evaluated together (in parallel in a real run), then replaced
                score = objective(trial)
                if score < fitness[i]:
                    fitness[i] = score
                    population[i] = trial
        history.append(float(fitness.min()))
    return history


def run_task(task):
    """One run (picklable for the process pool); every run seeds its own generator, so results do not depend on
    the number of processes."""
    name, dims, grid, mode, seed, pop, gens, F, CR = task
    func, lo, hi = FUNCTIONS[name]
    step = (hi - lo) / grid if grid else None
    np.random.seed(seed)  # same initial population for both modes
    return run(lambda x: evaluate(func, x), lo, hi, dims, pop, gens, F, CR, mode, step)


def plot(curves, finals, functions, dims_list, grids, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"immediate": "#2a6fdb", "generation": "#e0712c"}
    labels = {"immediate": "immediate (project DE)", "generation": "generation-wise"}
    paths = []
    for grid, dims in itertools.product(grids, dims_list):
        fig, axes = plt.subplots(2, 3, figsize=(13, 7.5))
        for ax, name in zip(axes.flat, functions, strict=False):
            for mode in MODES:
                q = curves[(name, dims, grid, mode)]
                x = np.arange(len(q[1]))
                floor = 1e-12
                ax.plot(x, np.maximum(q[1], floor), color=colors[mode], label=labels[mode])
                ax.fill_between(x, np.maximum(q[0], floor), np.maximum(q[2], floor), color=colors[mode], alpha=0.2)
            ax.set_yscale("log")
            ax.set_title(name)
            ax.set_xlabel("generation")
            ax.set_ylabel("best f (median, quartiles)")
            ax.grid(alpha=0.3)
        axes.flat[0].legend(fontsize=8)
        tag = f"D{dims}" + (f"_grid{grid}" if grid else "")
        fig.suptitle(f"DE update rule, D = {dims}" + (f", lattice {grid} steps" if grid else ", continuous"))
        fig.tight_layout()
        path = os.path.join(out, f"de_update_curves_{tag}.png")
        fig.savefig(path, dpi=120)
        plt.close(fig)
        paths.append(path)

        fig, axes = plt.subplots(1, len(functions), figsize=(2.3 * len(functions), 3.4))
        for ax, name in zip(axes, functions, strict=True):
            data = [np.maximum(finals[(name, dims, grid, mode)], 1e-12) for mode in MODES]
            box = ax.boxplot(data, patch_artist=True, widths=0.6)
            for patch, mode in zip(box["boxes"], MODES, strict=True):
                patch.set_facecolor(colors[mode])
                patch.set_alpha(0.5)
            ax.set_xticks([1, 2], ["imm.", "gen."])
            ax.set_yscale("log")
            ax.set_title(name, fontsize=10)
            ax.grid(alpha=0.3)
        fig.suptitle(f"Final best value, D = {dims}" + (f", lattice {grid}" if grid else ""))
        fig.tight_layout()
        path = os.path.join(out, f"de_update_final_{tag}.png")
        fig.savefig(path, dpi=120)
        plt.close(fig)
        paths.append(path)
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--functions", nargs="+", default=list(FUNCTIONS), choices=list(FUNCTIONS))
    parser.add_argument("--dims", nargs="+", type=int, default=[7, 20])
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--pop", type=int, default=100)
    parser.add_argument("--gens", type=int, default=300)
    parser.add_argument("--F", type=float, default=0.5)
    parser.add_argument("--CR", type=float, default=0.9)
    parser.add_argument("--grid", type=int, default=0, help="also run on a lattice of this many steps per variable")
    parser.add_argument("--out", default="logs")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--workers", type=int, default=0, help="processes (0: all CPU cores, 1: no parallelism)")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    grids = [0] + ([args.grid] if args.grid else [])
    cases = list(itertools.product(args.functions, args.dims, grids))
    tasks = [
        (name, dims, grid, mode, seed, args.pop, args.gens, args.F, args.CR)
        for (name, dims, grid), mode, seed in itertools.product(cases, MODES, range(args.seeds))
    ]
    start = time.time()
    workers = args.workers or os.cpu_count() or 1
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            histories = list(pool.map(run_task, tasks, chunksize=4))
    else:
        histories = [run_task(task) for task in tasks]
    print(f"{len(tasks)} runs on {workers} processes in {time.time() - start:.0f} s", flush=True)

    finals, curves = {}, {}
    by_case = {}
    final_path = os.path.join(args.out, "de_update_final.csv")
    with open(final_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["function", "dims", "grid", "mode", "seed", "best", "evals"])
        for task, history in zip(tasks, histories, strict=True):
            name, dims, grid, mode, seed = task[:5]
            writer.writerow([name, dims, grid, mode, seed, f"{history[-1]:.6e}", args.pop * (args.gens + 1)])
            by_case.setdefault((name, dims, grid, mode), []).append(history)
    for key, runs in by_case.items():
        runs = np.array(runs)
        finals[key] = runs[:, -1]
        curves[key] = np.percentile(runs, [25, 50, 75], axis=0)
    for name, dims, grid in cases:
        a, b = finals[(name, dims, grid, "immediate")], finals[(name, dims, grid, "generation")]
        p = mannwhitneyu(a, b).pvalue if np.any(a != b) else 1.0
        print(
            f"{name:<10} D={dims:<3} grid={grid:<4} median immediate {np.median(a):.3e}"
            f"  generation {np.median(b):.3e}  p={p:.3g}",
            flush=True,
        )
    curve_path = os.path.join(args.out, "de_update_curves.csv")
    with open(curve_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["function", "dims", "grid", "mode", "generation", "q25", "median", "q75"])
        for (name, dims, grid, mode), q in curves.items():
            for g in range(q.shape[1]):
                writer.writerow([name, dims, grid, mode, g, f"{q[0, g]:.6e}", f"{q[1, g]:.6e}", f"{q[2, g]:.6e}"])
    print(f"wrote {final_path} and {curve_path}")
    if args.plot:
        for path in plot(curves, finals, args.functions, args.dims, grids, args.out):
            print(f"wrote {path}")
    return finals, curves


if __name__ == "__main__":
    main()
