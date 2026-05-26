import numpy as np
import os
import csv
import time
from src.utils import canonicalize_vector_inplace

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

    os.makedirs('logs', exist_ok=True)
    site_name = config['site_name']
    trial_file = open(f'logs/{site_name}_trial_history.csv', 'w', newline='')
    gen_file = open(f'logs/{site_name}_generation_history.csv', 'w', newline='')

    trial_writer = csv.writer(trial_file)
    gen_writer = csv.writer(gen_file)

    vec_headers = [f'v{i+1}' for i in range(dimensions)]
    p_headers = [f'p{i+1}' for i in range(config['num_wecs'])]
    trial_writer.writerow(vec_headers + ['fitness'] + p_headers)
    gen_writer.writerow(['iter'] + vec_headers + ['fitness'] + p_headers + ['time'])

    memory_cache = {}
    cache_hits = 0
    total_evals = 0
    
    def get_eval_score(vector:np.ndarray, gen_idx):
        nonlocal cache_hits, total_evals
        canonicalize_vector_inplace(vector, config['opt_mode'], config['num_wecs'])
        mem_key = tuple(np.round(vector * 10).astype(int))

        if mem_key in memory_cache:
            cache_hits += 1
            res = memory_cache[mem_key]
        else:
            total_evals += 1
            score, ind_powers = eval_func(vector, config)
            res = (score, ind_powers)
            memory_cache[mem_key] = res

            trial_writer.writerow(list(vector) + [score] + list(ind_powers))
            trial_file.flush() # 매 평가마다 파일에 기록
        return res

    # 1. 초기 개체군 생성
    start_time = time.time()
    population = np.random.rand(pop_size, dimensions)
    population = lower_bounds + population * (upper_bounds - lower_bounds)
    population = np.round(population, 1)

    print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
    fitness = []
    ind_powers_pop = []
    for ind in population:
        score, p_list = get_eval_score(ind, 0)
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

            trial = np.round(trial, 1)
            trial = np.clip(trial, lower_bounds, upper_bounds)

            score, p_list = get_eval_score(trial, gen + 1)

            if score > fitness[i]:
                fitness[i] = score
                population[i] = trial

                if score > best_f:
                    best_f = score
                    best_x = trial.copy()
                    best_p = p_list
        
        gen_time = time.time() - gen_start
        gen_writer.writerow([gen+1] + list(best_x) + [best_f] + list(best_p) + [f"{gen_time:.2f}"])
        gen_file.flush()

        print(f" Gen {gen+1} | Best: {best_f/1000:,.4f} kW | Hits: {cache_hits} | Evals: {total_evals}")
    trial_file.close()
    gen_file.close()
    
    return best_x, best_f