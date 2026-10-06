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

    validate_optimizer_inputs(config, pop_size, max_iter)
    if w < 0 or c1 < 0 or c2 < 0:
        raise ValueError("PSO coefficients w, c1, and c2 must be non-negative.")
    dimensions = config["dimensions"]
    lower_bounds, upper_bounds = np.array(config["bounds"][0]), np.array(config["bounds"][1])
    checkpoint = CheckpointManager(
        config,
        "pso",
        {"c1": c1, "c2": c2, "max_iter": max_iter, "pop_size": pop_size, "w": w},
    )
    restored = checkpoint.load()
    logger = OptimizationLogger(config, suffix="pso", resume=restored is not None)
    evaluator = CachedEvaluator(config, eval_func, logger)

    step_size = get_step_size(config)
    v_max = np.maximum((upper_bounds - lower_bounds) * 0.2, step_size)

    try:
        if restored is None:
            positions = random_grid_population(pop_size, config)
            velocities = np.random.uniform(-v_max, v_max, (pop_size, dimensions))
            print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
            pbest_positions = positions.copy()
            initial_results = evaluator.evaluate_many(positions)
            pbest_fitness = np.array([result[0] for result in initial_results])
            pbest_powers = [result[1] for result in initial_results]
            best_idx = np.argmax(pbest_fitness)
            gbest_position = positions[best_idx].copy()
            gbest_fitness = pbest_fitness[best_idx]
            gbest_powers = pbest_powers[best_idx]
            start_generation = 0
            print(f"초기 세대 최적 발전량: {gbest_fitness / 1000:,.4f} kW")
        else:
            positions = restored["positions"]
            velocities = restored["velocities"]
            pbest_positions = restored["pbest_positions"]
            pbest_fitness = restored["pbest_fitness"]
            pbest_powers = restored["pbest_powers"]
            gbest_position = restored["gbest_position"]
            gbest_fitness = restored["gbest_fitness"]
            gbest_powers = restored["gbest_powers"]
            start_generation = restored["generation"]
            evaluator.set_state(restored["evaluator"])
            np.random.set_state(restored["random_state"])
            print(f"체크포인트에서 {start_generation}세대까지 복원했습니다.")

        # 2. 메인 루프
        for gen in range(start_generation, max_iter):
            gen_start = time.time()

            for i in range(pop_size):
                r1 = np.random.rand(dimensions)
                r2 = np.random.rand(dimensions)

                velocities[i] = (
                    w * velocities[i]
                    + c1 * r1 * (pbest_positions[i] - positions[i])
                    + c2 * r2 * (gbest_position - positions[i])
                )
                velocities[i] = np.clip(velocities[i], -v_max, v_max)
                positions[i] += velocities[i]

                positions[i] = quantize_vector(positions[i], config)

            iteration_results = evaluator.evaluate_many(positions)
            for i, (score, p_list) in enumerate(iteration_results):
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
            checkpoint.save(
                gen + 1,
                {
                    "evaluator": evaluator.get_state(),
                    "gbest_fitness": gbest_fitness,
                    "gbest_position": gbest_position,
                    "gbest_powers": gbest_powers,
                    "generation": gen + 1,
                    "pbest_fitness": pbest_fitness,
                    "pbest_positions": pbest_positions,
                    "pbest_powers": pbest_powers,
                    "positions": positions,
                    "random_state": np.random.get_state(),
                    "velocities": velocities,
                },
            )

            print(
                f" Gen {gen + 1} | Best: {gbest_fitness / 1000:,.4f} kW | Hits: {evaluator.cache_hits} | Evals: {evaluator.total_evals}"
            )
    finally:
        logger.close()

    checkpoint.complete()
    return gbest_position, gbest_fitness
