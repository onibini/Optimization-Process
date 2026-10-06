import time

import numpy as np

from wec_optimization.algorithms.checkpoint import CheckpointManager
from wec_optimization.algorithms.common import (
    CachedEvaluator,
    OptimizationLogger,
    get_step_size,
    quantize_vector,
    validate_optimizer_inputs,
)


def _normalize_vector(vector, lower_bounds, bounds_range):
    return (vector - lower_bounds) / bounds_range


def _denormalize_vector(vector, lower_bounds, bounds_range):
    return lower_bounds + vector * bounds_range


def run_cma_es(config, eval_func, pop_size, max_iter, sigma_init=0.3):
    """
    CMA-ES (Covariance Matrix Adaptation Evolution Strategy) 메인 엔진
    - 0.1 이산 격자(Discrete Grid) 및 메모이제이션 통합 버전
    - 설계변수별 범위 차이에 강건하도록 [0, 1] 정규화 공간에서 분포를 적응

    :param sigma_init: 초기 탐색 보폭 (전체 탐색 범위 대비 비율, 기본 30%)
    """

    validate_optimizer_inputs(config, pop_size, max_iter, min_pop_size=2)
    if sigma_init <= 0:
        raise ValueError("CMA-ES initial sigma must be positive.")
    dimensions = config["dimensions"]
    lower_bounds, upper_bounds = np.array(config["bounds"][0]), np.array(config["bounds"][1])
    bounds_range = upper_bounds - lower_bounds
    if np.any(bounds_range <= 0):
        raise ValueError("CMA-ES requires every upper bound to be greater than its lower bound.")

    # ==========================================
    # CMA-ES 내부 파라미터 셋업 (Canonical Math)
    # ==========================================
    N = dimensions
    step_size = get_step_size(config)
    lambda_ = pop_size  # Offspring 수
    mu = lambda_ // 2  # 부모 수 (일반적으로 λ/2)

    # 가중치 및 실효 선택 질량
    weights = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    weights = weights / np.sum(weights)
    mueff = np.sum(weights) ** 2 / np.sum(weights**2)

    # 학습률 설정
    cc = (4 + mueff / N) / (N + 4 + 2 * mueff / N)
    cs = (mueff + 2) / (N + mu)
    c1 = 2 / ((N + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((N + 2) ** 2 + mueff))
    damps = 1 + 2 * max(0, np.sqrt((mueff - 1) / (N + 1)) - 1) + cs

    min_sigma = np.min(step_size / bounds_range)
    echi = np.sqrt(N) * (1 - 1 / (4 * N) + 1 / (21 * N**2))

    checkpoint = CheckpointManager(
        config,
        "cmaes",
        {"max_iter": max_iter, "pop_size": pop_size, "sigma_init": sigma_init},
    )
    restored = checkpoint.load()
    logger = OptimizationLogger(config, suffix="cmaes", resume=restored is not None)
    evaluator = CachedEvaluator(config, eval_func, logger)

    if restored is None:
        m = np.random.rand(N)
        sigma = float(sigma_init)
        pc = np.zeros(N)
        ps = np.zeros(N)
        B = np.eye(N)
        D = np.ones(N)
        C = np.eye(N)
        invsqrtC = np.eye(N)
        best_x, best_f, best_p = None, -np.inf, []
        start_generation = 0
        print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
    else:
        m = restored["m"]
        sigma = restored["sigma"]
        pc = restored["pc"]
        ps = restored["ps"]
        B = restored["B"]
        D = restored["D"]
        C = restored["C"]
        invsqrtC = restored["invsqrtC"]
        best_x = restored["best_x"]
        best_f = restored["best_f"]
        best_p = restored["best_p"]
        start_generation = restored["generation"]
        evaluator.set_state(restored["evaluator"])
        np.random.set_state(restored["random_state"])
        print(f"체크포인트에서 {start_generation}세대까지 복원했습니다.")

    try:
        # 2. 메인 루프
        for gen in range(start_generation, max_iter):
            gen_start = time.time()

            arx = np.zeros((lambda_, N))  # 정규화 공간의 평가 완료 후보
            arz = np.zeros((lambda_, N))
            fitness = np.zeros(lambda_)

            candidates = np.zeros((lambda_, N))
            # 1. 자식 개체 생성
            for k in range(lambda_):
                arz[k] = np.random.randn(N)
                candidate_z = m + sigma * (B @ (D * arz[k]))
                candidate_z = np.clip(candidate_z, 0.0, 1.0)

                candidates[k] = quantize_vector(
                    _denormalize_vector(candidate_z, lower_bounds, bounds_range), config
                )

            generation_results = evaluator.evaluate_many(candidates)
            for k, (score, p_list) in enumerate(generation_results):
                fitness[k] = score
                arx[k] = _normalize_vector(candidates[k], lower_bounds, bounds_range)

                if score > best_f:
                    best_f = score
                    best_x = candidates[k].copy()
                    best_p = p_list

            # 2. 적합도 기준 내림차순 정렬
            arindex = np.argsort(fitness)[::-1]
            # 3. 평균 업데이트
            m_old = m.copy()
            # 상위 m개의 원래 분포 샘플을 사용하여 평균 이동
            m = np.sum(weights[:, np.newaxis] * arx[arindex[:mu]], axis=0)

            # 4. 진화 경로
            ps = (1 - cs) * ps + np.sqrt(cs * (2 - cs) * mueff) * invsqrtC @ (m - m_old) / sigma

            # hsig: Step size가 너무 커지는 것을 막는 Heuristic Trigger
            hsig = (
                np.linalg.norm(ps) / np.sqrt(1 - (1 - cs) ** (2 * (gen + 1)))
                < (1.4 + 2 / (N + 1)) * echi
            )
            pc = (1 - cc) * pc + hsig * np.sqrt(cc * (2 - cc) * mueff) * (m - m_old) / sigma

            # 5. 공분산 행렬 C 업데이트
            artmp = (1 / sigma) * (arx[arindex[:mu]] - m_old)
            C = (
                (1 - c1 - cmu) * C
                + c1 * (np.outer(pc, pc) + (1 - hsig) * cc * (2 - cc) * C)
                + cmu * artmp.T @ np.diag(weights) @ artmp
            )

            # 6. 보폭 sigma 업데이트
            sigma = sigma * np.exp((cs / damps) * (np.linalg.norm(ps) / echi - 1))
            sigma = max(sigma, min_sigma)

            # 7. 고유값 분해로 B, D, invsqrtC 갱신
            C = (C + C.T) / 2
            D_eig, B = np.linalg.eigh(C)
            D_eig = np.maximum(D_eig, 1e-18)
            D = np.sqrt(D_eig)
            invsqrtC = B @ np.diag(1 / D) @ B.T

            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, best_x, best_f, best_p, gen_time)
            checkpoint.save(
                gen + 1,
                {
                    "B": B,
                    "C": C,
                    "D": D,
                    "best_f": best_f,
                    "best_p": best_p,
                    "best_x": best_x,
                    "evaluator": evaluator.get_state(),
                    "generation": gen + 1,
                    "invsqrtC": invsqrtC,
                    "m": m,
                    "pc": pc,
                    "ps": ps,
                    "random_state": np.random.get_state(),
                    "sigma": sigma,
                },
            )

            print(
                f" Gen {gen + 1} | Best: {best_f / 1000:,.4f} kW | Hits: {evaluator.cache_hits} | Evals: {evaluator.total_evals}"
            )
    finally:
        logger.close()

    checkpoint.complete()
    return best_x, best_f
