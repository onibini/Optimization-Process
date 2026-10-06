import time

import numpy as np

from wec_optimization.algorithms.checkpoint import CheckpointManager
from wec_optimization.algorithms.common import (
    CachedEvaluator,
    OptimizationLogger,
    quantize_vector,
    random_grid_population,
    validate_optimizer_inputs,
)


def run_de(config, eval_func, pop_size, max_iter, F, CR):
    """
    차분 진화 알고리즘(DE/rand/1/bin) 메인 엔진

    :param config: 문제 설정 (dimensions, bounds 등 포함)
    :param eval_func: 평가 함수 (evaluate_shape, evaluate_layout 등)
    :param pop_size: 개체군 크기
    :param max_iter: 최대 세대 수
    :param F: 변이 가중치 (Mutation factor, 0.5 ~ 1.0)
    :param CR: 교차 확률 (Crossover rate, 0.8 ~ 1.0)
    :return: (최적 설계 변수, 최적 발전량)
    """

    validate_optimizer_inputs(config, pop_size, max_iter, min_pop_size=4)
    if not 0 < F <= 2:
        raise ValueError("DE mutation factor F must be in the interval (0, 2].")
    if not 0 <= CR <= 1:
        raise ValueError("DE crossover rate CR must be in the interval [0, 1].")
    dimensions = config["dimensions"]
    checkpoint = CheckpointManager(
        config,
        "de",
        {"CR": CR, "F": F, "max_iter": max_iter, "pop_size": pop_size},
    )
    restored = checkpoint.load()
    logger = OptimizationLogger(config, resume=restored is not None)
    evaluator = CachedEvaluator(config, eval_func, logger)

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

        # 2. 메인 루프
        for gen in range(start_generation, max_iter):
            gen_start = time.time()

            trials = np.empty_like(population)
            for i in range(pop_size):
                # Mutation
                idxs = [idx for idx in range(pop_size) if idx != i]
                a, b, c = population[np.random.choice(idxs, 3, replace=False)]
                mutant = a + F * (b - c)

                # Crossover
                cross_points = np.random.rand(dimensions) < CR
                if not np.any(cross_points):
                    cross_points[np.random.randint(0, dimensions)] = True

                trial = np.where(cross_points, mutant, population[i])

                trials[i] = quantize_vector(trial, config)

            trial_results = evaluator.evaluate_many(trials)
            for i, (score, p_list) in enumerate(trial_results):
                if score > fitness[i]:
                    fitness[i] = score
                    population[i] = trials[i]
                    ind_powers_pop[i] = p_list

                    if score > best_f:
                        best_f = score
                        best_x = trials[i].copy()
                        best_p = p_list

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
