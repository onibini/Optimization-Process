import numpy as np
import os
import csv
import time
from src.utils import canonicalize_vector_inplace

def run_cma_es(config, eval_func, pop_size, max_iter, sigma_init=0.3):
    """
    CMA-ES (Covariance Matrix Adaptation Evolution Strategy) 메인 엔진
    - 0.1 이산 격자(Discrete Grid) 및 메모이제이션 통합 버전
    
    :param sigma_init: 초기 탐색 보폭 (전체 탐색 범위 대비 비율, 기본 30%)
    """

    dimensions = config['dimensions']
    num_wecs = config['num_wecs']
    lower_bounds, upper_bounds = np.array(config['bounds'][0]), np.array(config['bounds'][1])

    # 📂 로깅 초기화
    os.makedirs('logs', exist_ok=True)
    site_name = config.get('site_name', 'Unknown')
    trial_file = open(f'logs/{site_name}_cmaes_trial_history.csv', 'w', newline='')
    gen_file = open(f'logs/{site_name}_cmaes_generation_history.csv', 'w', newline='')

    trial_writer = csv.writer(trial_file)
    gen_writer = csv.writer(gen_file)

    vec_headers = [f'v{i+1}' for i in range(dimensions)]
    p_headers = [f'p{i+1}' for i in range(num_wecs)]
    trial_writer.writerow(vec_headers + ['fitness'] + p_headers)
    gen_writer.writerow(['iter'] + vec_headers + ['fitness'] + p_headers + ['time'])

    # 🧠 메모리 캐시 초기화
    memory_cache = {}
    cache_hits, total_evals = 0, 0

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
    
    
    # ==========================================
    # CMA-ES 내부 파라미터 셋업 (Canonical Math)
    # ==========================================
    N = dimensions
    lambda_ = pop_size # Offspring 수
    mu = lambda_ // 2  # 부모 수 (일반적으로 λ/2)

    # 가중치 및 실효 선택 질량
    weights = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    weights = weights / np.sum(weights)
    mueff = np.sum(weights)**2 / np.sum(weights**2)

    # 학습률 설정
    cc = (4 + mueff / N) / (N + 4 + 2 * mueff / N)
    cs = (mueff + 2) / (N + mu)
    c1 = 2 / ((N + 1.3)**2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((N + 2)**2 + mueff))
    damps = 1 + 2 * max(0, np.sqrt((mueff - 1) / (N + 1)) - 1) + cs

    # 진화 상태 변수 초기화
    m = lower_bounds + np.random.rand(N) * (upper_bounds - lower_bounds) # 초기 평균
    sigma = sigma_init * np.max(upper_bounds - lower_bounds) # 초기 탐색 보폭

    pc = np.zeros(N) # 공분산 진화 경로
    ps = np.zeros(N) # 보폭 진화 경로
    B = np.eye(N)
    D = np.ones(N)
    C = np.eye(N)
    invsqrtC = np.eye(N)
    echi = np.sqrt(N) * (1 - 1 / (4 * N) + 1 / (21 * N**2))

    best_x, best_f, best_p = None, -np.inf, []

    print(f"최적화 시작: 초기 개체군 {pop_size}개 평가 중...")
    start_time = time.time()

    # 2. 메인 루프
    for gen in range(max_iter):
        gen_start = time.time()

        arx = np.zeros((lambda_, N))
        arz = np.zeros((lambda_, N))
        fitness = np.zeros(lambda_)
        ind_powers_pop = []

        # 1. 자식 개체 생성 및 평가
        for k in range(lambda_):
            arz[k] = np.random.randn(N)
            arx[k] = m + sigma * (B @ (D * arz[k]))

            eval_x = np.round(arx[k], 1)
            eval_x = np.clip(eval_x, lower_bounds, upper_bounds)
            arx[k] = eval_x

            score, p_list = get_eval_score(eval_x, gen + 1)
            fitness[k] = score
            ind_powers_pop.append(p_list)

            if score > best_f:
                best_f = score
                best_x = eval_x.copy()
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
        hsig = np.linalg.norm(ps) / np.sqrt(1 - (1 - cs)**(2 * (gen + 1))) < (1.4 + 2 / (N + 1)) * echi
        pc = (1 - cc) * pc + hsig * np.sqrt(cc * (2 - cc) * mueff) * (m - m_old) / sigma

        # 5. 공분산 행렬 C 업데이트
        artmp = (1 / sigma) * (arx[arindex[:mu]] - m_old)
        C = ((1 - c1 - cmu) * C
             + c1 * (np.outer(pc, pc) + (1 - hsig) * cc * (2 - cc) * C)
             + cmu * artmp.T @ np.diag(weights) @ artmp)
        
        # 6. 보폭 sigma 업데이트
        sigma = sigma * np.exp((cs / damps) * (np.linalg.norm(ps) / echi - 1))

        # 7. 고유값 분해로 B, D, invsqrtC 갱신
        C = (C + C.T) / 2
        D_eig, B = np.linalg.eigh(C)
        D_eig = np.maximum(D_eig, 1e-18)
        D = np.sqrt(D_eig)
        invsqrtC = B @ np.diag(1 / D) @ B.T

        gen_time = time.time() - gen_start
        gen_writer.writerow([gen + 1] + list(best_x) + [best_f] + best_p + [f"{gen_time:.2f}"])
        gen_file.flush()

        print(f" Gen {gen+1} | Best: {best_f/1000:,.4f} kW | Hits: {cache_hits} | Evals: {total_evals}")
    trial_file.close()
    gen_file.close()

    return best_x, best_f