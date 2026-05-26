import numpy as np
import os
import csv
import time
from src.utils import canonicalize_vector_inplace

def run_pso(config, eval_func, pop_size, max_iter, w=0.5, c1=1.5, c2=1.5):
    """
    입자 군집 최적화(PSO) 메인 엔진
    
    :param config: 문제 설정 (dimensions, bounds 등 포함)
    :param eval_func: 평가 함수
    :param pop_size: 군집(Swarm) 크기
    :param max_iter: 최대 세대 수
    :param w: 관성 가중치 (Inertia weight, 현재 속도 유지 비율)
    :param c1: 인지적 계수 (Cognitive coefficient, 개인 최고 기록으로 향하는 힘)
    :param c2: 사회적 계수 (Social coefficient, 전역 최고 기록으로 향하는 힘)
    :return: (최적 설계 변수, 최적 발전량)
    """

    dimensions = config['dimensions']
    lower_bounds, upper_bounds = np.array(config['bounds'][0]), np.array(config['bounds'][1])

    os.makedirs('logs', exist_ok=True)
    site_name = config['site_name']

    trial_file = open(f'logs/{site_name}_pso_trial_history.csv', 'w', newline='')
    gen_file = open(f'logs/{site_name}_pso_generation_history.csv', 'w', newline='')

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
    
    # 1. 초기 군집 생성
    start_time = time.time()
    positions = np.random.rand(pop_size, dimensions)
    positions = lower_bounds + positions * (upper_bounds - lower_bounds)
    positions = np.round(positions, 1)

    v_max = (upper_bounds - lower_bounds) * 0.2
    velocities = np.random.uniform(-v_max, v_max, (pop_size, dimensions))

    print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
    pbest_positions= positions.copy()
    pbest_fitness = np.zeros(pop_size)
    pbest_powers = []

    for i in range(pop_size):
        score, p_list = get_eval_score(positions[i], 0)
        pbest_fitness[i] = score
        pbest_powers.append(p_list)
    
    best_idx = np.argmax(pbest_fitness)
    gbest_position = positions[best_idx].copy()
    gbest_fitness = pbest_fitness[best_idx]
    gbest_powers = pbest_powers[best_idx]

    print(f"초기 세대 최적 발전량: {gbest_fitness/1000:,.4f} kW")

    # 2. 메인 루프
    for gen in range(max_iter):
        gen_start = time.time()

        for i in range(pop_size):
            r1 = np.random.rand(dimensions)
            r2 = np.random.rand(dimensions)

            velocities[i] = (w * velocities[i] +
                            c1 * r1 * (pbest_positions[i] - positions[i]) +
                            c2 * r2 * (gbest_position - positions[i]))
            velocities[i] = np.clip(velocities[i], -v_max, v_max)
            positions[i] += velocities[i]

            positions[i] = np.round(positions[i], 1)
            positions[i] = np.clip(positions[i], lower_bounds, upper_bounds)

            score, p_list = get_eval_score(positions[i], gen)

            if score > pbest_fitness[i]:
                pbest_fitness[i] = score
                pbest_positions[i] = positions[i].copy()
                pbest_powers[i] = p_list

                if score > gbest_fitness:
                    gbest_fitness = score
                    gbest_position = positions[i].copy()
                    gbest_powers = p_list

        gen_time = time.time() - gen_start
        gen_writer.writerow([gen+1] + list(gbest_position) + [gbest_fitness] + list(gbest_powers) + [f"{gen_time:.2f}"])
        gen_file.flush()

        print(f" Gen {gen+1} | Best: {gbest_fitness/1000:,.4f} kW | Hits: {cache_hits} | Evals: {total_evals}")
    trial_file.close()
    gen_file.close()

    return gbest_position, gbest_fitness