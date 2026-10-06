import time

import numpy as np

from wec_optimization.algorithms.checkpoint import CheckpointManager
from wec_optimization.algorithms.common import (
    CachedEvaluator,
    OptimizationLogger,
    get_step_size,
    quantize_vector,
    random_grid_population,
    validate_optimizer_inputs,
)


def run_ga(config, eval_func, pop_size, max_iter, mutation_rate=0.1):
    """
    유전 알고리즘(Genetic Algorithm) 메인 엔진

    :param config: 문제 설정 (dimensions, bounds 등 포함)
    :param eval_func: 평가 함수
    :param pop_size: 개체군 크기
    :param max_iter: 최대 세대 수
    :param mutation_rate: 돌연변이 발생 확률 (기본값 0.1)
    :return: (최적 설계 변수, 최적 발전량)
    """

    validate_optimizer_inputs(config, pop_size, max_iter, min_pop_size=4)
    if not 0 <= mutation_rate <= 1:
        raise ValueError("GA mutation rate must be in the interval [0, 1].")
    dimensions = config["dimensions"]
    lower_bounds, upper_bounds = np.array(config["bounds"][0]), np.array(config["bounds"][1])
    checkpoint = CheckpointManager(
        config,
        "ga",
        {
            "max_iter": max_iter,
            "mutation_rate": mutation_rate,
            "pop_size": pop_size,
        },
    )
    restored = checkpoint.load()
    logger = OptimizationLogger(config, suffix="ga", resume=restored is not None)
    evaluator = CachedEvaluator(config, eval_func, logger)
    step_size = get_step_size(config)

    try:
        if restored is None:
            population = random_grid_population(pop_size, config)
            print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
            initial_results = evaluator.evaluate_many(population)
            fitness = np.array([result[0] for result in initial_results])
            ind_powers_pop = [result[1] for result in initial_results]
            best_idx = np.argmax(fitness)
            best_x = population[best_idx].copy()
            best_f = fitness[best_idx]
            best_p = ind_powers_pop[best_idx]
            start_generation = 0
            print(f"초기 세대 최적 발전량: {best_f / 1000:,.4f} kW")
        else:
            population = restored["population"]
            fitness = restored["fitness"]
            ind_powers_pop = restored["individual_powers"]
            best_x = restored["best_x"]
            best_f = restored["best_f"]
            best_p = restored["best_p"]
            start_generation = restored["generation"]
            evaluator.set_state(restored["evaluator"])
            np.random.set_state(restored["random_state"])
            print(f"체크포인트에서 {start_generation}세대까지 복원했습니다.")

        for gen in range(start_generation, max_iter):
            gen_start = time.time()

            new_population = np.zeros((pop_size, dimensions))
            current_best_idx = np.argmax(fitness)
            new_population[0] = population[current_best_idx].copy()

            for i in range(1, pop_size):
                competitors = np.random.choice(pop_size, 4, replace=False)
                parent1_idx = (
                    competitors[0]
                    if fitness[competitors[0]] > fitness[competitors[1]]
                    else competitors[1]
                )
                parent2_idx = (
                    competitors[2]
                    if fitness[competitors[2]] > fitness[competitors[3]]
                    else competitors[3]
                )

                p1 = population[parent1_idx]
                p2 = population[parent2_idx]

                cross_mask = np.random.rand(dimensions) < 0.5
                child = np.where(cross_mask, p1, p2)

                if np.random.rand() < mutation_rate:
                    mutation_span = np.maximum(
                        1, np.ceil((upper_bounds - lower_bounds) * 0.1 / step_size).astype(int)
                    )
                    mutation_mask = np.random.rand(dimensions) < 0.5
                    step_offsets = np.array(
                        [np.random.randint(-span, span + 1) for span in mutation_span]
                    )
                    child = child + np.where(mutation_mask, step_offsets * step_size, 0)

                child = quantize_vector(child, config)

                new_population[i] = child

            generation_results = evaluator.evaluate_many(new_population)
            new_fitness = np.array([result[0] for result in generation_results])
            new_ind_powers = [result[1] for result in generation_results]

            population = new_population.copy()
            fitness = new_fitness.copy()
            ind_powers_pop = new_ind_powers[:]

            gen_best_idx = np.argmax(fitness)
            if fitness[gen_best_idx] > best_f:
                best_f = fitness[gen_best_idx]
                best_x = population[gen_best_idx].copy()
                best_p = ind_powers_pop[gen_best_idx]

            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, best_x, best_f, best_p, gen_time)
            checkpoint.save(
                gen + 1,
                {
                    "best_f": best_f,
                    "best_p": best_p,
                    "best_x": best_x,
                    "evaluator": evaluator.get_state(),
                    "fitness": fitness,
                    "generation": gen + 1,
                    "individual_powers": ind_powers_pop,
                    "population": population,
                    "random_state": np.random.get_state(),
                },
            )

            print(
                f" Gen {gen + 1} | Best: {best_f / 1000:,.4f} kW | Hits: {evaluator.cache_hits} | Evals: {evaluator.total_evals}"
            )
    finally:
        logger.close()

    checkpoint.complete()
    return best_x, best_f
