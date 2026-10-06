import csv
import shutil
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from wec_optimization.utils import canonicalize_vector_inplace


def _evaluate_in_workspace(eval_func, vector, config, workspace_dir):
    """Run one picklable evaluation inside a worker process."""
    worker_config = dict(config)
    worker_config["workspace_dir"] = workspace_dir
    result = eval_func(vector, worker_config)
    if not worker_config.get("keep_workspaces", False):
        _remove_successful_workspace(
            workspace_dir, worker_config.get("workspace_root", "workspace")
        )
    return result


def _remove_successful_workspace(workspace_dir, workspace_root):
    """Safely remove a completed candidate workspace below the configured root."""
    target = Path(workspace_dir).resolve()
    root = Path(workspace_root).resolve()
    if target.parent != root or not target.name.startswith("eval_"):
        raise RuntimeError(f"Refusing to remove unsafe workspace path: {target}")
    if not target.exists():
        return
    try:
        shutil.rmtree(target)
    except OSError as error:
        warnings.warn(f"Could not remove completed workspace {target}: {error}", stacklevel=2)


def get_step_size(config):
    step_size = float(config.get("step_size", 0.1))
    if step_size <= 0:
        raise ValueError(f"StepSize must be positive, got {step_size}")
    return step_size


def get_bounds(config):
    lower_bounds = np.asarray(config["bounds"][0], dtype=float)
    upper_bounds = np.asarray(config["bounds"][1], dtype=float)
    if lower_bounds.shape != upper_bounds.shape:
        raise ValueError("Lower and upper bounds must have the same shape.")
    if lower_bounds.ndim != 1 or lower_bounds.size == 0:
        raise ValueError("Bounds must be non-empty one-dimensional sequences.")
    if np.any(upper_bounds < lower_bounds):
        raise ValueError("Every upper bound must be greater than or equal to its lower bound.")
    return lower_bounds, upper_bounds


def validate_optimizer_inputs(config, pop_size, max_iter, *, min_pop_size=1):
    dimensions = int(config["dimensions"])
    lower_bounds, _ = get_bounds(config)
    if dimensions != lower_bounds.size:
        raise ValueError(
            f"Configured dimensions ({dimensions}) do not match bounds ({lower_bounds.size})."
        )
    if pop_size < min_pop_size:
        raise ValueError(f"Population size must be at least {min_pop_size}.")
    if max_iter < 1:
        raise ValueError("Maximum iterations must be at least 1.")


def quantize_vector(vector, config):
    lower_bounds, upper_bounds = get_bounds(config)
    step_size = get_step_size(config)
    max_indices = np.floor((upper_bounds - lower_bounds) / step_size).astype(int)
    step_indices = np.floor((vector - lower_bounds) / step_size + 0.5).astype(int)
    step_indices = np.clip(step_indices, 0, max_indices)
    quantized = lower_bounds + step_indices * step_size
    return np.round(quantized, 10)


def quantize_vector_inplace(vector, config):
    vector[:] = quantize_vector(vector, config)
    return vector


def random_grid_population(pop_size, config):
    lower_bounds, upper_bounds = get_bounds(config)
    step_size = get_step_size(config)
    max_indices = np.floor((upper_bounds - lower_bounds) / step_size).astype(int)
    random_indices = np.array(
        [np.random.randint(0, max_idx + 1, size=pop_size) for max_idx in max_indices]
    ).T
    return lower_bounds + random_indices * step_size


def make_cache_key(vector, config):
    lower_bounds, _ = get_bounds(config)
    step_size = get_step_size(config)
    return tuple(np.floor((vector - lower_bounds) / step_size + 0.5).astype(int))


class OptimizationLogger:
    def __init__(self, config, suffix="", resume=False):
        log_dir = Path(config.get("log_dir", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)

        dimensions = config["dimensions"]
        num_wecs = config["num_wecs"]
        site_name = config.get("site_name", "Unknown")
        name_suffix = f"_{suffix}" if suffix else ""

        trial_path = log_dir / f"{site_name}{name_suffix}_trial_history.csv"
        generation_path = log_dir / f"{site_name}{name_suffix}_generation_history.csv"
        mode = "a" if resume else "w"
        write_trial_header = not resume or not trial_path.exists() or trial_path.stat().st_size == 0
        write_generation_header = (
            not resume or not generation_path.exists() or generation_path.stat().st_size == 0
        )
        self.trial_file = trial_path.open(mode, newline="", encoding="utf-8")
        self.gen_file = generation_path.open(
            mode,
            newline="",
            encoding="utf-8",
        )
        self.trial_writer = csv.writer(self.trial_file)
        self.gen_writer = csv.writer(self.gen_file)

        vec_headers = [f"v{i + 1}" for i in range(dimensions)]
        p_headers = [f"p{i + 1}" for i in range(num_wecs)]
        if write_trial_header:
            self.trial_writer.writerow([*vec_headers, "fitness", *p_headers])
        if write_generation_header:
            self.gen_writer.writerow(["iter", *vec_headers, "fitness", *p_headers, "time"])

    def write_trial(self, vector, score, individual_powers):
        self.trial_writer.writerow([*vector, score, *individual_powers])
        self.trial_file.flush()

    def write_generation(self, gen_idx, vector, score, individual_powers, elapsed_time):
        self.gen_writer.writerow(
            [gen_idx, *vector, score, *individual_powers, f"{elapsed_time:.2f}"]
        )
        self.gen_file.flush()

    def close(self):
        self.trial_file.close()
        self.gen_file.close()


class CachedEvaluator:
    def __init__(self, config, eval_func, logger):
        self.config = config
        self.eval_func = eval_func
        self.logger = logger
        self.memory_cache = {}
        self.cache_hits = 0
        self.total_evals = 0

    def get_state(self):
        return {
            "cache_hits": self.cache_hits,
            "memory_cache": self.memory_cache,
            "total_evals": self.total_evals,
        }

    def set_state(self, state):
        self.cache_hits = int(state["cache_hits"])
        self.memory_cache = dict(state["memory_cache"])
        self.total_evals = int(state["total_evals"])

    def evaluate(self, vector):
        return self.evaluate_many([vector])[0]

    def evaluate_many(self, vectors):
        """Quantize, deduplicate, and evaluate a batch, possibly in parallel."""
        vectors = list(vectors)
        results = [None] * len(vectors)
        pending = {}

        for index, vector in enumerate(vectors):
            quantize_vector_inplace(vector, self.config)
            canonicalize_vector_inplace(
                vector,
                self.config["opt_mode"],
                self.config["num_wecs"],
            )
            cache_key = make_cache_key(vector, self.config)
            if cache_key in self.memory_cache:
                self.cache_hits += 1
                results[index] = self.memory_cache[cache_key]
            elif cache_key in pending:
                self.cache_hits += 1
                pending[cache_key][1].append(index)
            else:
                pending[cache_key] = (vector.copy(), [index])

        if not pending:
            return results

        concurrent_runs = int(self.config.get("concurrent_runs", 1))
        if concurrent_runs < 1:
            raise ValueError("ConcurrentRuns must be at least 1.")

        workspace_root = Path(self.config.get("workspace_root", "workspace"))
        work_items = []
        for cache_key, (vector, indices) in pending.items():
            workspace_name = "eval_" + "_".join(map(str, cache_key))
            work_items.append(
                (
                    cache_key,
                    vector,
                    indices,
                    str(workspace_root / workspace_name),
                )
            )

        if concurrent_runs == 1 or len(work_items) == 1:
            evaluated = [
                _evaluate_in_workspace(self.eval_func, vector, self.config, workspace_dir)
                for _, vector, _, workspace_dir in work_items
            ]
        else:
            worker_count = min(concurrent_runs, len(work_items))
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                futures = [
                    executor.submit(
                        _evaluate_in_workspace,
                        self.eval_func,
                        vector,
                        self.config,
                        workspace_dir,
                    )
                    for _, vector, _, workspace_dir in work_items
                ]
                evaluated = [future.result() for future in futures]

        for (cache_key, vector, indices, _), (score, individual_powers) in zip(
            work_items,
            evaluated,
            strict=True,
        ):
            if not np.isfinite(score):
                raise ValueError(f"Evaluation returned a non-finite score: {score}")
            result = (score, individual_powers)
            self.memory_cache[cache_key] = result
            self.total_evals += 1
            self.logger.write_trial(vector, score, individual_powers)
            for index in indices:
                results[index] = result

        return results
