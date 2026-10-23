import time

import numpy as np

from src.algorithms.common import (
    CachedEvaluator,
    OptimizationLogger,
    canonical_copy,
    get_step_size,
    quantize_vector,
    random_grid_population,
)


def run_depso(config, eval_func, pop_size, max_iter, F=0.5, CR=0.9, w=0.5, c1=1.5, c2=1.5, update="greedy"):
    """
    DE-PSO 혼합 알고리즘 메인 엔진 (사용자의 예전 DEPSO 구현 중 갱신 규칙만 옮긴 것)

    출처: Lee, O.-B., Heo, S., Koo, W., 2026. Metaheuristic-based layout optimization of multiple heaving
    point-absorber wave energy converters near a vertical wall. Ocean Engineering 355, 125173.

    입자마다 매 세대:
      1. PSO 이동: 속도 갱신(관성 w, pbest 쪽 c1, gbest 쪽 c2, 범위의 10%로 제한) 후 위치 + 속도 = 이동 후보
      2. DE 변이: 다른 입자 셋의 DE/rand/1 변이 벡터 a + F(b - c)
      3. DE 교차: 이동 후보를 기준으로 변이 벡터와 이항 교차(CR) → 시험 벡터
      4. 평가(입자당 1회)와 갱신
    속도는 갱신 결과와 관계없이 1의 값을 유지합니다.
    한 입자의 결과는 같은 세대의 다음 입자에 바로 쓰입니다(run_de와 같음).

    ``update``가 2와 4를 정합니다.
      - "greedy"(기본, 원래 구현): 변이 재료는 다른 입자의 현재 위치. 입자는 더 좋을 때만 이동합니다(DE의 탐욕
        선택, 엘리트 보존). 그래서 pbest가 늘 현재 위치와 같고 c1 항은 사실상 0입니다.
      - "pbest"(비교용): 변이 재료는 다른 입자의 pbest. 입자는 항상 이동하고 pbest는 더 좋을 때만 바뀝니다.
      - "move"(비교용): 변이 재료는 다른 입자의 현재 위치. 입자는 원래 PSO처럼 항상 이동합니다.
    벤치마크(docs/reports/2026-10-23_11)에서 "greedy"가 가장 좋았고 "move"는 수렴하지 못했습니다.

    초기화·격자 스냅·제약 패널티·캐시·로그는 다른 알고리즘과 같은 프로젝트 공통 기능을 씁니다.

    :param F: DE 변이 가중치
    :param CR: DE 교차 확률 (1 - CR의 비율로 PSO 이동 후보의 성분이 남음)
    :param w: PSO 관성 가중치
    :param c1: PSO 인지적 계수 (pbest 쪽)
    :param c2: PSO 사회적 계수 (gbest 쪽)
    :param update: "greedy"(기본, 원래 구현), "pbest" 또는 "move", 위 설명 참조
    :return: (최적 설계 변수, 최적 발전량)

    Note:
        평가는 위치의 '사본'을 대칭 정렬해서 합니다(run_pso와 같은 이유: 위치 자체를 정렬하면 속도와 어긋남).
    """
    if pop_size < 4:
        raise ValueError("DEPSO requires PopSize >= 4 (DE/rand/1 needs three other particles).")
    if update not in ("pbest", "move", "greedy"):
        raise ValueError(f"DEPSO update must be 'pbest', 'move' or 'greedy', got {update!r}")

    dimensions = config["dimensions"]
    lower_bounds, upper_bounds = np.array(config["bounds"][0]), np.array(config["bounds"][1])
    logger = OptimizationLogger(config, algorithm="depso")
    evaluator = CachedEvaluator(config, eval_func, logger)

    # 1. 초기 군집 (위치는 격자 위, 속도와 속도 상한은 범위의 10%)
    positions = random_grid_population(pop_size, config)
    step_size = get_step_size(config)
    v_max = np.maximum((upper_bounds - lower_bounds) * 0.1, step_size)
    velocities = np.random.uniform(-v_max, v_max, (pop_size, dimensions))

    gbest_position, gbest_fitness, gbest_powers = None, -np.inf, []
    gens_done = 0
    try:
        print(f"최적화 시작: 초기 군집 {pop_size}개 평가 중...")
        fitness = np.zeros(pop_size)
        for i, (score, p_list) in enumerate(evaluator.evaluate_batch([p.copy() for p in positions])):
            fitness[i] = score
            if fitness[i] > gbest_fitness:
                gbest_fitness, gbest_position, gbest_powers = fitness[i], positions[i].copy(), p_list
        pbest_positions, pbest_fitness = positions.copy(), fitness.copy()
        print(f"초기 세대 최적 발전량: {gbest_fitness / 1000:,.4f} kW")

        # 2. 메인 루프
        for gen in range(max_iter):
            gen_start = time.time()

            for i in range(pop_size):
                # PSO 이동
                r1 = np.random.rand(dimensions)
                r2 = np.random.rand(dimensions)
                velocities[i] = np.clip(
                    w * velocities[i]
                    + c1 * r1 * (pbest_positions[i] - positions[i])
                    + c2 * r2 * (gbest_position - positions[i]),
                    -v_max,
                    v_max,
                )
                moved = np.clip(positions[i] + velocities[i], lower_bounds, upper_bounds)

                # DE 변이 (다른 입자의 pbest 또는 현재 위치) + 이동 후보를 기준으로 교차
                idxs = [idx for idx in range(pop_size) if idx != i]
                donors = pbest_positions if update == "pbest" else positions
                a, b, c = donors[np.random.choice(idxs, 3, replace=False)]
                mutant = a + F * (b - c)
                cross_points = np.random.rand(dimensions) < CR
                if not np.any(cross_points):
                    cross_points[np.random.randint(0, dimensions)] = True
                trial = quantize_vector(np.where(cross_points, mutant, moved), config)

                score, p_list = evaluator.evaluate(trial.copy())
                if update != "greedy" or score > fitness[i]:
                    fitness[i] = score
                    positions[i] = trial
                    if score > pbest_fitness[i]:
                        pbest_fitness[i] = score
                        pbest_positions[i] = trial
                        if score > gbest_fitness:
                            gbest_fitness = score
                            gbest_position = trial.copy()
                            gbest_powers = p_list

            gen_time = time.time() - gen_start
            logger.write_generation(
                gen + 1, canonical_copy(gbest_position, config), gbest_fitness, gbest_powers, gen_time
            )
            gens_done = gen + 1

            print(f" Gen {gen + 1} | Best: {gbest_fitness / 1000:,.4f} kW | {evaluator.progress_text()}")
    finally:
        if gbest_position is not None:
            gbest_position = canonical_copy(gbest_position, config)
        logger.write_summary(gbest_position, gbest_fitness, gbest_powers, evaluator, gens_done)
        logger.close()

    return gbest_position, gbest_fitness
