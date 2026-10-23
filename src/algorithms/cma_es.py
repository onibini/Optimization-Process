import time

import numpy as np

from src.algorithms.common import CachedEvaluator, OptimizationLogger, get_step_size, quantize_vector


def _normalize_vector(vector, lower_bounds, bounds_range):
    return (vector - lower_bounds) / bounds_range


def _denormalize_vector(vector, lower_bounds, bounds_range):
    return lower_bounds + vector * bounds_range


# 보폭 sigma의 상한(정규화 공간 [0, 1]에서). 샘플은 [0, 1]로 잘리므로 범위 전체(1.0)보다 큰 보폭은 의미가 없습니다.
MAX_SIGMA = 1.0
# 좌표별 최소 표준편차 = MIN_STD_FACTOR x (격자 한 칸 / 범위). 0이면 끔.
MIN_STD_FACTOR = 0.0
# 한 세대의 보폭 변화량 상한: sigma *= exp(min(MAX_LOG_SIGMA_CHANGE, ...)). pycma와 같은 방식으로,
# 보폭이 격자 하한에 묶여 진화 경로 ps가 커져도 exp가 넘치지(overflow) 않게 합니다.
MAX_LOG_SIGMA_CHANGE = 1.0


def update_sigma(sigma, ps_norm, cs, damps, echi, min_sigma, max_sigma=MAX_SIGMA):
    """CSA 보폭 갱신. 변화량(로그)을 MAX_LOG_SIGMA_CHANGE 이하로, 결과를 [min_sigma, max_sigma]로 제한합니다."""
    log_change = min((cs / damps) * (ps_norm / echi - 1), MAX_LOG_SIGMA_CHANGE)
    return float(np.clip(sigma * np.exp(log_change), min_sigma, max_sigma))


def raise_min_std(C, sigma, min_std):
    """좌표별 표준편차 sigma * sqrt(C_ii)가 min_std보다 작으면 그 대각 성분만 키웁니다(양의 정부호 유지).

    격자 간격이 변수마다 다르면(정규화 공간에서 R 한 칸 0.05, y 한 칸 0.0033) 수렴 후반에 큰 칸을 가진 변수의 샘플이
    늘 같은 격자점으로 반올림되어 그 방향 탐색이 멈춥니다. pycma의 'minstd'(정수 변수 처리)와 같은 방식입니다.
    """
    floor = (np.asarray(min_std, dtype=float) / sigma) ** 2
    diag = np.diag(C)
    low = diag < floor
    if np.any(low):
        C = C.copy()
        C[low, low] = floor[low]
    return C


def run_cma_es(config, eval_func, pop_size, max_iter, sigma_init=0.3, min_std_factor=MIN_STD_FACTOR):
    """
    CMA-ES (Covariance Matrix Adaptation Evolution Strategy) 메인 엔진
    - 이산 격자(StepSize) 및 메모이제이션 통합 버전
    - 설계변수별 범위 차이에 강건하도록 [0, 1] 정규화 공간에서 분포를 적응

    격자/대칭 처리 방식:
        분포에서 뽑은 연속 샘플을 [0, 1]로 클리핑한 뒤, 그 '사본'을 격자 스냅 + 대칭 정렬하여
        평가(캐시 조회)합니다. 평균·공분산·진화경로 갱신에는 클리핑된 연속 샘플을 그대로 사용합니다.
        (이전에는 대칭 정렬로 (x2, y2)<->(x3, y3)가 뒤바뀐 벡터를 갱신에 사용해서,
        5기 배치에서 샘플과 갱신 벡터의 대응이 깨지고 분포가 왜곡될 수 있었습니다.)

    :param sigma_init: 초기 탐색 보폭 (전체 탐색 범위 대비 비율, 기본 30%)
    :param min_std_factor: 좌표별 최소 표준편차(격자 한 칸 대비 배수, 0이면 끔). ``raise_min_std`` 참조
    """
    if pop_size < 4:
        raise ValueError("CMA-ES requires PopSize >= 4.")
    if not 0 < sigma_init <= MAX_SIGMA:
        raise ValueError(f"SigmaInit must be in (0, {MAX_SIGMA:g}] (fraction of the search range), got {sigma_init}")

    dimensions = config["dimensions"]
    lower_bounds, upper_bounds = np.array(config["bounds"][0]), np.array(config["bounds"][1])
    bounds_range = upper_bounds - lower_bounds
    if np.any(bounds_range <= 0):
        raise ValueError("CMA-ES requires every upper bound to be greater than its lower bound.")

    logger = OptimizationLogger(config, algorithm="cmaes")
    evaluator = CachedEvaluator(config, eval_func, logger)

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
    cs = (mueff + 2) / (N + mueff + 5)  # Hansen, "The CMA Evolution Strategy: A Tutorial" (2016)
    c1 = 2 / ((N + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((N + 2) ** 2 + mueff))
    damps = 1 + 2 * max(0, np.sqrt((mueff - 1) / (N + 1)) - 1) + cs

    # 진화 상태 변수 초기화
    m = np.random.rand(N)  # 초기 평균 ([0, 1] 정규화 공간)
    sigma = float(sigma_init)  # 초기 탐색 보폭 (정규화 공간 비율)
    min_sigma = np.min(step_size / bounds_range)
    min_std = min_std_factor * step_size / bounds_range  # 좌표별 최소 표준편차 (정규화 공간)

    pc = np.zeros(N)  # 공분산 진화 경로
    ps = np.zeros(N)  # 보폭 진화 경로
    B = np.eye(N)
    D = np.ones(N)
    C = np.eye(N)
    invsqrtC = np.eye(N)
    echi = np.sqrt(N) * (1 - 1 / (4 * N) + 1 / (21 * N**2))

    best_x, best_f, best_p = None, -np.inf, []
    gens_done = 0

    print(f"최적화 시작: 세대당 {lambda_}개 샘플, 최대 {max_iter}세대")

    try:
        # 2. 메인 루프
        for gen in range(max_iter):
            gen_start = time.time()

            arx = np.zeros((lambda_, N))  # 정규화 공간의 (클리핑된) 연속 샘플
            fitness = np.zeros(lambda_)

            # 1. 자식 개체 생성 후 한꺼번에 평가 (Workers > 1이면 WAMIT 동시 실행; 결과는 차례로 평가한 것과 같음)
            eval_xs = []
            for k in range(lambda_):
                z = np.random.randn(N)
                candidate = np.clip(m + sigma * (B @ (D * z)), 0.0, 1.0)
                arx[k] = candidate
                # 평가용 사본: 격자 스냅 후 CachedEvaluator가 제자리에서 대칭 정렬함
                eval_xs.append(quantize_vector(_denormalize_vector(candidate, lower_bounds, bounds_range), config))

            for k, (eval_x, (score, p_list)) in enumerate(zip(eval_xs, evaluator.evaluate_batch(eval_xs), strict=True)):
                fitness[k] = score
                if score > best_f:
                    best_f = score
                    best_x = eval_x.copy()
                    best_p = p_list

            # 2. 적합도 기준 내림차순 정렬
            arindex = np.argsort(fitness)[::-1]
            # 3. 평균 업데이트 (상위 mu개 연속 샘플의 가중 평균)
            m_old = m.copy()
            m = np.sum(weights[:, np.newaxis] * arx[arindex[:mu]], axis=0)

            # 4. 진화 경로
            ps = (1 - cs) * ps + np.sqrt(cs * (2 - cs) * mueff) * invsqrtC @ (m - m_old) / sigma

            # hsig: Step size가 너무 커지는 것을 막는 Heuristic Trigger
            hsig = np.linalg.norm(ps) / np.sqrt(1 - (1 - cs) ** (2 * (gen + 1))) < (1.4 + 2 / (N + 1)) * echi
            pc = (1 - cc) * pc + hsig * np.sqrt(cc * (2 - cc) * mueff) * (m - m_old) / sigma

            # 5. 공분산 행렬 C 업데이트
            artmp = (1 / sigma) * (arx[arindex[:mu]] - m_old)
            C = (
                (1 - c1 - cmu) * C
                + c1 * (np.outer(pc, pc) + (1 - hsig) * cc * (2 - cc) * C)
                + cmu * artmp.T @ np.diag(weights) @ artmp
            )

            # 6. 보폭 sigma 업데이트 (하한: 격자 한 칸, 상한: 범위 전체, 한 세대 변화량 제한)
            sigma = update_sigma(sigma, np.linalg.norm(ps), cs, damps, echi, min_sigma)

            # 7. 고유값 분해로 B, D, invsqrtC 갱신
            C = (C + C.T) / 2
            if min_std_factor > 0:
                C = raise_min_std(C, sigma, min_std)
            D_eig, B = np.linalg.eigh(C)
            D_eig = np.maximum(D_eig, 1e-18)
            D = np.sqrt(D_eig)
            invsqrtC = B @ np.diag(1 / D) @ B.T

            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, best_x, best_f, best_p, gen_time)
            gens_done = gen + 1

            print(f" Gen {gen + 1} | Best: {best_f / 1000:,.4f} kW | {evaluator.progress_text()}")
    finally:
        logger.write_summary(best_x, best_f, best_p, evaluator, gens_done)
        logger.close()

    return best_x, best_f
