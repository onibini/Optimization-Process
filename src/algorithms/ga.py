import numpy as np
import time
from src.algorithms.common import CachedEvaluator, OptimizationLogger, get_step_size, quantize_vector, random_grid_population

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
    
    dimensions = config['dimensions']
    lower_bounds, upper_bounds = np.array(config['bounds'][0]), np.array(config['bounds'][1])
    logger = OptimizationLogger(config, suffix="ga")
    evaluator = CachedEvaluator(config, eval_func, logger)
    
    # 1. 초기 군집 생성
    population = random_grid_population(pop_size, config)
    step_size = get_step_size(config)

    try:
        print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
        fitness = np.zeros(pop_size)
        ind_powers_pop = []

        for i in range(pop_size):
            score, p_list = evaluator.evaluate(population[i])
            fitness[i] = score
            ind_powers_pop.append(p_list)

        best_idx = np.argmax(fitness)
        best_x = population[best_idx]
        best_f = fitness[best_idx]
        best_p = ind_powers_pop[best_idx]

        print(f"초기 세대 최적 발전량: {best_f/1000:,.4f} kW")

        for gen in range(max_iter):
            gen_start = time.time()

            new_population = np.zeros((pop_size, dimensions))
            new_fitness = np.zeros(pop_size)
            new_ind_powers = []

            current_best_idx = np.argmax(fitness)
            new_population[0] = population[current_best_idx].copy()
            new_fitness[0] = fitness[current_best_idx]
            new_ind_powers.append(ind_powers_pop[current_best_idx])

            for i in range(1, pop_size):
                competitors = np.random.choice(pop_size, 4, replace=False)
                parent1_idx = competitors[0] if fitness[competitors[0]] > fitness[competitors[1]] else competitors[1]
                parent2_idx = competitors[2] if fitness[competitors[2]] > fitness[competitors[3]] else competitors[3]

                p1 = population[parent1_idx]
                p2 = population[parent2_idx]

                cross_mask = np.random.rand(dimensions) < 0.5
                child = np.where(cross_mask, p1, p2)

                if np.random.rand() < mutation_rate:
                    mutation_span = np.maximum(1, np.ceil((upper_bounds - lower_bounds) * 0.1 / step_size).astype(int))
                    mutation_mask = np.random.rand(dimensions) < 0.5
                    step_offsets = np.array([
                        np.random.randint(-span, span + 1)
                        for span in mutation_span
                    ])
                    child = child + np.where(mutation_mask, step_offsets * step_size, 0)

                child = quantize_vector(child, config)

                score, p_list = evaluator.evaluate(child)
                new_population[i] = child
                new_fitness[i] = score
                new_ind_powers.append(p_list)

            population = new_population.copy()
            fitness = new_fitness.copy()
            ind_powers_pop = new_ind_powers[:]

            gen_best_idx = np.argmax(fitness)
            if fitness[gen_best_idx] > best_f:
                best_f = fitness[gen_best_idx]
                best_x = population[gen_best_idx].copy()
                best_p = ind_powers_pop[gen_best_idx]

            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, population[gen_best_idx], fitness[gen_best_idx], ind_powers_pop[gen_best_idx], gen_time)

            print(f" Gen {gen+1} | Best: {best_f/1000:,.4f} kW | Hits: {evaluator.cache_hits} | Evals: {evaluator.total_evals}")
    finally:
        logger.close()

    return best_x, best_f
