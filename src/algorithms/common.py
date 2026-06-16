import csv
import os

import numpy as np

from src.utils import canonicalize_vector_inplace


def get_step_size(config):
    step_size = float(config.get('step_size', 0.1))
    if step_size <= 0:
        raise ValueError(f"StepSize must be positive, got {step_size}")
    return step_size


def get_bounds(config):
    return np.array(config['bounds'][0]), np.array(config['bounds'][1])


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
    random_indices = np.array([
        np.random.randint(0, max_idx + 1, size=pop_size)
        for max_idx in max_indices
    ]).T
    return lower_bounds + random_indices * step_size


def make_cache_key(vector, config):
    lower_bounds, _ = get_bounds(config)
    step_size = get_step_size(config)
    return tuple(np.floor((vector - lower_bounds) / step_size + 0.5).astype(int))


class OptimizationLogger:
    def __init__(self, config, suffix=""):
        os.makedirs('logs', exist_ok=True)

        dimensions = config['dimensions']
        num_wecs = config['num_wecs']
        site_name = config.get('site_name', 'Unknown')
        name_suffix = f"_{suffix}" if suffix else ""

        self.trial_file = open(f'logs/{site_name}{name_suffix}_trial_history.csv', 'w', newline='')
        self.gen_file = open(f'logs/{site_name}{name_suffix}_generation_history.csv', 'w', newline='')
        self.trial_writer = csv.writer(self.trial_file)
        self.gen_writer = csv.writer(self.gen_file)

        vec_headers = [f'v{i+1}' for i in range(dimensions)]
        p_headers = [f'p{i+1}' for i in range(num_wecs)]
        self.trial_writer.writerow(vec_headers + ['fitness'] + p_headers)
        self.gen_writer.writerow(['iter'] + vec_headers + ['fitness'] + p_headers + ['time'])

    def write_trial(self, vector, score, individual_powers):
        self.trial_writer.writerow(list(vector) + [score] + list(individual_powers))
        self.trial_file.flush()

    def write_generation(self, gen_idx, vector, score, individual_powers, elapsed_time):
        self.gen_writer.writerow(
            [gen_idx] + list(vector) + [score] + list(individual_powers) + [f"{elapsed_time:.2f}"]
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

    def evaluate(self, vector):
        quantize_vector_inplace(vector, self.config)
        canonicalize_vector_inplace(vector, self.config['opt_mode'], self.config['num_wecs'])
        mem_key = make_cache_key(vector, self.config)

        if mem_key in self.memory_cache:
            self.cache_hits += 1
            return self.memory_cache[mem_key]

        self.total_evals += 1
        score, individual_powers = self.eval_func(vector, self.config)
        result = (score, individual_powers)
        self.memory_cache[mem_key] = result
        self.logger.write_trial(vector, score, individual_powers)
        return result
