import csv
import json
import os
import time

import numpy as np

from src.algorithms.common import (
    CachedEvaluator,
    OptimizationLogger,
    canonical_copy,
    json_default,
    make_cache_key,
    quantize_vector,
    random_grid_population,
)
from src.algorithms.local_search import compass_search
from src.algorithms.progress import GenerationProgress

DE_UPDATES = ("immediate", "generation", "block")
DE_STRATEGIES = ("rand1", "current-to-best1")
STALL_ACTIONS = ("stop", "restart")
CHECKPOINT_VERSION = 1


def update_block_size(update, pop_size, workers):
    """한 번에 만들고 함께 평가하는 시험 벡터 수: 즉시 교체 1, 묶음 즉시 교체 ``workers``, 세대 단위 개체 수."""
    if update == "immediate":
        return 1
    if update == "generation":
        return pop_size
    return max(1, min(int(workers), pop_size))


def _settings_for_resume(config, pop_size, F, CR, update, strategy):
    """이어 돌릴 때 같아야 하는 값. 문제가 다르면 저장된 개체군과 평가값을 쓸 수 없습니다."""
    from src.utils.eval_db import fingerprint

    return json.loads(
        json.dumps(
            {
                "pop_size": pop_size,
                "F": F,
                "CR": CR,
                "update": update,
                "strategy": strategy,
                "dimensions": config["dimensions"],
                "bounds": config["bounds"],
                "step_size": config.get("step_size"),
                "fingerprint": fingerprint(config),
            },
            default=json_default,
        )
    )


def _design_key(vector, config):
    """지금까지 본 설계를 기억하는 키 (체크포인트에 그대로 저장되는 정수 목록)."""
    return tuple(int(value) for value in make_cache_key(vector, config))


def _rng_state_to_json(state):
    return [state[0], state[1].tolist(), int(state[2]), int(state[3]), float(state[4])]


def _rng_state_from_json(state):
    return (state[0], np.array(state[1], dtype=np.uint32), state[2], state[3], state[4])


def read_trial_rows(path):
    """``*_trial_history.csv``를 ``CachedEvaluator.preload`` 형식으로 읽습니다. 끊겨서 망가진 줄은 건너뜁니다."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return rows
        fit_col = header.index("fitness")
        for row in reader:
            if len(row) != len(header):
                continue
            try:
                values = [float(value) for value in row]
            except ValueError:
                continue
            rows.append((values[:fit_col], values[fit_col], values[fit_col + 1 : -1], bool(values[-1])))
    return rows


def _load_checkpoint(path, settings, evaluator):
    """체크포인트를 읽어 난수 상태를 되돌리고, 지난 실행의 평가값을 불러옵니다(WAMIT을 다시 돌리지 않음)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("version") != CHECKPOINT_VERSION:
        raise ValueError(f"Unsupported checkpoint version in {path}: {data.get('version')}")
    changed = sorted(key for key in settings if settings[key] != data["settings"].get(key))
    if changed:
        raise ValueError(f"Cannot resume from {path}: these settings changed: {', '.join(changed)}")

    folder = os.path.dirname(path)
    rows = []
    for name in data["trial_files"]:
        trial_path = os.path.join(folder, name)
        if os.path.exists(trial_path):
            rows.extend(read_trial_rows(trial_path))
        else:
            print(f"Warning: {trial_path} was not found; designs recorded there are evaluated again.")
    evaluator.preload(rows)
    np.random.set_state(_rng_state_from_json(data["rng_state"]))
    return data


def run_de(
    config,
    eval_func,
    pop_size,
    max_iter,
    F,
    CR,
    update="immediate",
    strategy="rand1",
    stall_gens=0,
    stall_action="stop",
    local_search_evals=0,
    resume=None,
):
    """
    차분 진화 알고리즘(DE) 메인 엔진

    :param config: 문제 설정 (dimensions, bounds 등 포함)
    :param eval_func: 평가 함수 (evaluate_shape, evaluate_layout 등)
    :param pop_size: 개체군 크기
    :param max_iter: 최대 세대 수
    :param F: 변이 가중치 (Mutation factor, 0.5 ~ 1.0)
    :param CR: 교차 확률 (Crossover rate, 0.8 ~ 1.0)
    :param update: "immediate"(기본, 논문과 같음) - 시험 벡터가 좋으면 같은 세대 안에서 바로 개체군을 바꿈.
        "generation" - 한 세대의 시험 벡터를 모두 옛 개체군에서 만들고 한꺼번에 평가한 뒤 바꿈(Storn-Price의
        동기식 DE). WAMIT을 동시에 돌릴 수 있지만(Workers > 1) 같은 품질에 약 1.15배 세대가 필요함.
        "block" - 개체 i, i+1, ..., i+B-1(B = ``Workers``)의 시험 벡터를 현재 개체군에서 만들어 함께 평가하고
        바로 바꿈. 묶음 안끼리만 서로의 교체를 못 보므로 즉시 교체에 가장 가깝고, B = 1이면 즉시 교체와 같음.
        세 방식은 같은 난수열을 씁니다.
    :param strategy: 변이 전략. "rand1"(기본, 논문): a + F(b - c). "current-to-best1": x_i + F(best - x_i) + F(b - c).
    :param stall_gens: 이 세대 수만큼 연달아 새 설계가 하나도 나오지 않으면(개체군 수렴) ``stall_action``을 합니다.
        0(기본)이면 끝까지 돌립니다. 최고값 정체로 판단하면 아직 탐색 중인 개체군을 버려 결과가 나빠졌습니다.
    :param stall_action: "stop" - 끝냄. "restart" - 최고 개체만 남기고 나머지를 다시 뽑아 ``max_iter``까지 계속함.
    :param local_search_evals: 0보다 크면 끝난 뒤 최고 설계를 지역 탐색으로 다듬습니다(물리 해석 횟수 상한).
    :param resume: 이어 돌릴 ``*_checkpoint.json`` 경로. 개체군, 난수 상태와 지난 평가값을 되살립니다.
    :return: (최적 설계 변수, 최적 발전량)

    평가와 캐시는 대칭 정렬한 '사본'으로 하고, 개체군에는 정렬하지 않은 벡터를 그대로 둡니다(논문 계산과 같음).
    정렬된 벡터를 개체군에 넣으면 두 대칭 쌍의 x가 비슷할 때(예: 둘 다 벽 옆) 작은 변화에도 쌍의 순서가 뒤바뀌어
    개체끼리 같은 자리에 다른 쌍의 값이 들어가므로, 차분 변이가 두 쌍을 따로 다듬지 못합니다.
    돌려주는 최적 설계는 정렬된 형태입니다.
    """
    if pop_size < 4:
        raise ValueError("DE/rand/1 requires PopSize >= 4.")
    if update not in DE_UPDATES:
        raise ValueError(f"DE update must be one of {DE_UPDATES}, got {update!r}")
    if strategy not in DE_STRATEGIES:
        raise ValueError(f"DE strategy must be one of {DE_STRATEGIES}, got {strategy!r}")
    if stall_action not in STALL_ACTIONS:
        raise ValueError(f"Stall action must be one of {STALL_ACTIONS}, got {stall_action!r}")
    if stall_gens < 0 or local_search_evals < 0:
        raise ValueError("StallGens and LocalSearchEvals must be >= 0.")
    block = update_block_size(update, pop_size, config.get("workers") or 1)

    dimensions = config["dimensions"]
    settings = _settings_for_resume(config, pop_size, F, CR, update, strategy)
    logger = OptimizationLogger(config, algorithm="de")
    evaluator = CachedEvaluator(config, eval_func, logger)
    progress = GenerationProgress(max_iter, pop_size)
    trial_files = [logger.trial_name()]

    best_x, best_f, best_p = None, -np.inf, []
    gens_done = 0
    start_gen = 0
    stalled = 0
    restarts = 0
    seen = set()
    ls_summary = None

    def save_checkpoint(gens):
        logger.write_checkpoint(
            {
                "version": CHECKPOINT_VERSION,
                "settings": settings,
                "gens_done": gens,
                "population": population,
                "fitness": fitness,
                "best_x": best_x,
                "best_f": best_f,
                "best_p": best_p,
                "stalled": stalled,
                "seen": list(seen),
                "restarts": restarts,
                "rng_state": _rng_state_to_json(np.random.get_state()),
                "trial_files": trial_files,
            },
        )

    try:
        if resume:
            data = _load_checkpoint(resume, settings, evaluator)
            population = np.array(data["population"], dtype=float)
            fitness = np.array(data["fitness"], dtype=float)
            best_x, best_f, best_p = np.array(data["best_x"], dtype=float), data["best_f"], data["best_p"]
            start_gen = gens_done = data["gens_done"]
            stalled, restarts = data["stalled"], data["restarts"]
            seen = {tuple(key) for key in data["seen"]}
            trial_files = [*data["trial_files"], *trial_files]
            print(
                f"Resuming from generation {start_gen} of {resume}: "
                f"{evaluator.stored_loaded} recorded designs, best {best_f / 1000:,.4f} kW"
            )
            save_checkpoint(gens_done)  # 또 끊겨도 이번 실행의 평가 기록까지 이어지도록
        else:
            # 1. 초기 개체군 생성
            population = random_grid_population(pop_size, config)
            print(f"Optimization started: evaluating the initial population of {pop_size}...")
            fitness = []
            ind_powers_pop = []
            progress.start(0, pop_size)
            evaluated = [canonical_copy(ind, config) for ind in population]
            for score, p_list in evaluator.evaluate_batch(evaluated, on_result=progress.advance):
                fitness.append(score)
                ind_powers_pop.append(p_list)

            seen.update(_design_key(canon, config) for canon in evaluated)
            fitness = np.array(fitness)
            best_idx = np.argmax(fitness)
            best_x = evaluated[best_idx].copy()
            best_f = fitness[best_idx]
            best_p = ind_powers_pop[best_idx]

            progress.finish(best_f, evaluator)
            save_checkpoint(0)

        # 2. 메인 루프
        for gen in range(start_gen, max_iter):
            gen_start = time.time()
            found_new = False
            progress.start(gen + 1, pop_size, best_f)

            for start in range(0, pop_size, block):
                members = range(start, min(start + block, pop_size))
                trials = []
                for i in members:
                    # Mutation
                    idxs = [idx for idx in range(pop_size) if idx != i]
                    if strategy == "rand1":
                        a, b, c = population[np.random.choice(idxs, 3, replace=False)]
                        mutant = a + F * (b - c)
                    else:
                        b, c = population[np.random.choice(idxs, 2, replace=False)]
                        leader = population[int(np.argmax(fitness))]
                        mutant = population[i] + F * (leader - population[i]) + F * (b - c)

                    # Crossover
                    cross_points = np.random.rand(dimensions) < CR
                    if not np.any(cross_points):
                        cross_points[np.random.randint(0, dimensions)] = True

                    trial = np.where(cross_points, mutant, population[i])
                    trials.append(quantize_vector(trial, config))

                evaluated = [canonical_copy(trial, config) for trial in trials]
                keys = {_design_key(canon, config) for canon in evaluated}
                found_new = found_new or not keys <= seen
                seen |= keys
                if block == 1:
                    results = [evaluator.evaluate(evaluated[0])]
                    progress.advance(results[0][0])
                else:
                    results = evaluator.evaluate_batch(evaluated, on_result=progress.advance)

                # Selection: 묶음이 끝나면 바로 교체 (다음 묶음의 변이가 바뀐 개체를 씀)
                for i, trial, canon, (score, p_list) in zip(members, trials, evaluated, results, strict=True):
                    if score > fitness[i]:
                        fitness[i] = score
                        population[i] = trial
                        if score > best_f:
                            best_f = score
                            best_x = canon.copy()
                            best_p = p_list

            gen_time = time.time() - gen_start
            logger.write_generation(gen + 1, best_x, best_f, best_p, gen_time)
            gens_done = gen + 1

            progress.finish(best_f, evaluator)

            # 수렴 판단: 세대 수가 다 찼을 때는 재시작하지 않음
            stalled = 0 if found_new else stalled + 1
            if stall_gens and stalled >= stall_gens and gens_done < max_iter:
                if stall_action == "stop":
                    print(f"Stopping early: no new design for {stalled} generations.")
                    save_checkpoint(gens_done)
                    break
                restarts += 1
                stalled = 0
                print(f"Restart {restarts}: keeping the best individual and drawing {pop_size - 1} new ones.")
                keep = int(np.argmax(fitness))
                kept_vector, kept_fitness = population[keep].copy(), fitness[keep]
                population = random_grid_population(pop_size, config)
                population[keep] = kept_vector
                others = [i for i in range(pop_size) if i != keep]
                evaluated = [canonical_copy(population[i], config) for i in others]
                seen.update(_design_key(canon, config) for canon in evaluated)
                for i, canon, (score, p_list) in zip(
                    others, evaluated, evaluator.evaluate_batch(evaluated), strict=True
                ):
                    fitness[i] = score
                    if score > best_f:
                        best_f = score
                        best_x = canon.copy()
                        best_p = p_list
                fitness[keep] = kept_fitness

            save_checkpoint(gens_done)

        # 3. 지역 탐색
        if local_search_evals:
            print(f"Local search: up to {local_search_evals} evaluations from {best_f / 1000:,.4f} kW...")
            ls_start = time.time()
            best_x, best_f, best_p, ls_summary = compass_search(
                best_x, best_f, best_p, evaluator, config, local_search_evals
            )
            logger.write_generation(gens_done + 1, best_x, best_f, best_p, time.time() - ls_start)
            print(
                f"Local search: {best_f / 1000:,.4f} kW after {ls_summary['moves']} moves "
                f"and {ls_summary['physics_evals']} evaluations."
            )
    finally:
        logger.write_summary(
            best_x,
            best_f,
            best_p,
            evaluator,
            gens_done,
            extra={
                "de_settings": {
                    "F": F,
                    "CR": CR,
                    "update": update,
                    "strategy": strategy,
                    "stall_gens": stall_gens,
                    "stall_action": stall_action,
                    "local_search_evals": local_search_evals,
                },
                "restarts": restarts,
                "local_search": ls_summary,
                "resumed_from": resume,
                "checkpoint": logger.checkpoint_name(),
            },
        )
        logger.close()

    return best_x, best_f
