import numpy as np
import time
from src.algorithms.common import CachedEvaluator, OptimizationLogger, quantize_vector, random_grid_population

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
    
    dimensions = config['dimensions']
    lower_bounds, upper_bounds = np.array(config['bounds'][0]), np.array(config['bounds'][1])
    logger = OptimizationLogger(config)
    evaluator = CachedEvaluator(config, eval_func, logger)

    # 1. 초기 개체군 생성
    population = random_grid_population(pop_size, config)

    try:
        print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
        fitness = []
        ind_powers_pop = []
        for ind in population:
            score, p_list = evaluator.evaluate(ind)
            fitness.append(score)
            ind_powers_pop.append(p_list)

        fitness = np.array(fitness)
        best_idx = np.argmax(fitness)
        best_x = population[best_idx].copy()
        best_f = fitness[best_idx]
        best_p = ind_powers_pop[best_idx]

        print(f"초기 세대 최적 발전량: {best_f/1000:,.4f} kW")

        # 2. 메인 루프
        for gen in range(max_iter):
            gen_start = time.time()

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

                trial = quantize_vector(trial, config)

                score, p_list = evaluator.evaluate(trial)

                if score > fitness[i]:
                    fitness[i] = score
                    population[i] = trial

                    if score > best_f:
                        best_f = score
                        best_x = trial.copy()
                        best_p = p_list
            
            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, best_x, best_f, best_p, gen_time)

            print(f" Gen {gen+1} | Best: {best_f/1000:,.4f} kW | Hits: {evaluator.cache_hits} | Evals: {evaluator.total_evals}")
    finally:
        logger.close()
    
    return best_x, best_f
