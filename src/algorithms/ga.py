import numpy as np
import os
import csv
import time
from src.utils import canonicalize_vector_inplace

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

    # 📂 로깅 초기화
    os.makedirs('logs', exist_ok=True)
    site_name = config['site_name']
    trial_file = open(f'logs/{site_name}_ga_trial_history.csv', 'w', newline='')
    gen_file = open(f'logs/{site_name}_ga_generation_history.csv', 'w', newline='')

    trial_writer = csv.writer(trial_file)
    gen_writer = csv.writer(gen_file)

    vec_headers = [f'v{i+1}' for i in range(dimensions)]
    p_headers = [f'p{i+1}' for i in range(config['num_wecs'])]
    trial_writer.writerow(vec_headers + ['fitness'] + p_headers)
    gen_writer.writerow(['iter'] + vec_headers + ['fitness'] + p_headers + ['time'])

    # 🧠 메모리 캐시 초기화
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
            trial_file.flush()
        return res
    
    # 1. 초기 군집 생성
    start_time = time.time()
    population = np.random.rand(pop_size, dimensions)
    population = lower_bounds + population * (upper_bounds - lower_bounds)
    population = np.round(population, 1)

    print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
    fitness = np.zeros(pop_size)
    ind_powers_pop = []

    for i in range(pop_size):
        score, p_list = get_eval_score(population[i], 0)
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
                noise_scale = (upper_bounds - lower_bounds) * 0.1
                mutation_step = np.random.normal(0, noise_scale, dimensions)

                mutation_mask = np.random.rand(dimensions) < 0.5
                child = child + np.where(mutation_mask, mutation_step, 0)

            child = np.round(child, 1)
            child = np.clip(child, lower_bounds, upper_bounds)

            score, p_list = get_eval_score(child, gen + 1)
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
        gen_writer.writerow([gen + 1] + list(population[gen_best_idx]) + [fitness[gen_best_idx]] + list(ind_powers_pop[gen_best_idx]) + [gen_time])
        gen_file.flush()

        print(f" Gen {gen+1} | Best: {best_f/1000:,.4f} kW | Hits: {cache_hits} | Evals: {total_evals}")
    trial_file.close()
    gen_file.close()

    return best_x, best_f
