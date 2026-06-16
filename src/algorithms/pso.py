import numpy as np
import time
from src.algorithms.common import CachedEvaluator, OptimizationLogger, get_step_size, quantize_vector, random_grid_population

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
    logger = OptimizationLogger(config, suffix="pso")
    evaluator = CachedEvaluator(config, eval_func, logger)
    
    # 1. 초기 군집 생성
    positions = random_grid_population(pop_size, config)

    step_size = get_step_size(config)
    v_max = np.maximum((upper_bounds - lower_bounds) * 0.2, step_size)
    velocities = np.random.uniform(-v_max, v_max, (pop_size, dimensions))

    try:
        print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
        pbest_positions= positions.copy()
        pbest_fitness = np.zeros(pop_size)
        pbest_powers = []

        for i in range(pop_size):
            score, p_list = evaluator.evaluate(positions[i])
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

                positions[i] = quantize_vector(positions[i], config)

                score, p_list = evaluator.evaluate(positions[i])

                if score > pbest_fitness[i]:
                    pbest_fitness[i] = score
                    pbest_positions[i] = positions[i].copy()
                    pbest_powers[i] = p_list

                    if score > gbest_fitness:
                        gbest_fitness = score
                        gbest_position = positions[i].copy()
                        gbest_powers = p_list

            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, gbest_position, gbest_fitness, gbest_powers, gen_time)

            print(f" Gen {gen+1} | Best: {gbest_fitness/1000:,.4f} kW | Hits: {evaluator.cache_hits} | Evals: {evaluator.total_evals}")
    finally:
        logger.close()

    return gbest_position, gbest_fitness
