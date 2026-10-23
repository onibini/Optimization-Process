import time

import numpy as np

from src.algorithms.common import CachedEvaluator, OptimizationLogger, quantize_vector, random_grid_population


def run_de(config, eval_func, pop_size, max_iter, F, CR, update="immediate"):
    """
    차분 진화 알고리즘(DE/rand/1/bin) 메인 엔진

    :param config: 문제 설정 (dimensions, bounds 등 포함)
    :param eval_func: 평가 함수 (evaluate_shape, evaluate_layout 등)
    :param pop_size: 개체군 크기
    :param max_iter: 최대 세대 수
    :param F: 변이 가중치 (Mutation factor, 0.5 ~ 1.0)
    :param CR: 교차 확률 (Crossover rate, 0.8 ~ 1.0)
    :param update: "immediate"(기본, 논문과 같음) - 시험 벡터가 좋으면 같은 세대 안에서 바로 개체군을 바꿈.
        "generation" - 한 세대의 시험 벡터를 모두 옛 개체군에서 만들고 한꺼번에 평가한 뒤 바꿈(Storn-Price의
        동기식 DE). WAMIT을 동시에 돌릴 수 있지만(Workers > 1) 같은 품질에 약 1.15배 세대가 필요함
        (docs/reports/2026-10-23_10 보고서). 두 방식은 같은 난수열을 씁니다.
    :return: (최적 설계 변수, 최적 발전량)
    """
    if pop_size < 4:
        raise ValueError("DE/rand/1 requires PopSize >= 4.")
    if update not in ("immediate", "generation"):
        raise ValueError(f"DE update must be 'immediate' or 'generation', got {update!r}")

    dimensions = config["dimensions"]
    logger = OptimizationLogger(config, algorithm="de")
    evaluator = CachedEvaluator(config, eval_func, logger)

    # 1. 초기 개체군 생성
    population = random_grid_population(pop_size, config)

    best_x, best_f, best_p = None, -np.inf, []
    gens_done = 0
    try:
        print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
        fitness = []
        ind_powers_pop = []
        for score, p_list in evaluator.evaluate_batch(list(population)):  # 행 뷰라 제자리 정렬이 개체군에 반영됨
            fitness.append(score)
            ind_powers_pop.append(p_list)

        fitness = np.array(fitness)
        best_idx = np.argmax(fitness)
        best_x = population[best_idx].copy()
        best_f = fitness[best_idx]
        best_p = ind_powers_pop[best_idx]

        print(f"초기 세대 최적 발전량: {best_f / 1000:,.4f} kW")

        # 2. 메인 루프
        for gen in range(max_iter):
            gen_start = time.time()

            trials = []
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
                if update == "generation":
                    trials.append(trial)
                    continue

                score, p_list = evaluator.evaluate(trial)
                if score > fitness[i]:
                    fitness[i] = score
                    population[i] = trial

                    if score > best_f:
                        best_f = score
                        best_x = trial.copy()
                        best_p = p_list

            if update == "generation":
                for i, (trial, (score, p_list)) in enumerate(
                    zip(trials, evaluator.evaluate_batch(trials), strict=True)
                ):
                    if score > fitness[i]:
                        fitness[i] = score
                        population[i] = trial
                        if score > best_f:
                            best_f = score
                            best_x = trial.copy()
                            best_p = p_list

            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, best_x, best_f, best_p, gen_time)
            gens_done = gen + 1

            print(f" Gen {gen + 1} | Best: {best_f / 1000:,.4f} kW | {evaluator.progress_text()}")
    finally:
        logger.write_summary(best_x, best_f, best_p, evaluator, gens_done)
        logger.close()

    return best_x, best_f
