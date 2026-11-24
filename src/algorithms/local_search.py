"""최적화가 끝난 설계를 격자 위에서 다듬는 지역 탐색 (compass search, 난수 없음)."""

import numpy as np

from src.algorithms.common import canonical_copy, get_step_size, grid_max_indices, make_cache_key


def _first_level(config):
    """가장 큰 이동 칸 수: 가장 긴 변수의 전체 범위. 격자 밖은 경계로 잘리므로 첫 단계는 변수를 경계로 옮겨 봅니다."""
    return max(1, int(np.max(grid_max_indices(config))))


def _neighbours(x, level, config):
    """변수 하나를 ±level칸 옮긴 설계들. 대칭 정렬하면 같아지는 설계와 ``x`` 자신은 뺍니다."""
    steps = np.broadcast_to(get_step_size(config), x.shape)
    seen = {make_cache_key(x, config)}
    result = []
    for i in range(len(x)):
        for sign in (-1, 1):
            moved = x.copy()
            moved[i] += sign * level * steps[i]
            candidate = canonical_copy(moved, config)
            key = make_cache_key(candidate, config)
            if key not in seen:
                seen.add(key)
                result.append(candidate)
    return result


def compass_search(best_x, best_f, best_p, evaluator, config, max_evals):
    """변수를 하나씩 옮겨 보며 더 좋은 설계로 갑니다. 물리 해석을 ``max_evals``번까지만 씁니다.

    이웃(변수 수 x 2개)을 함께 평가하고(``Workers`` > 1이면 동시 실행) 가장 좋은 이웃이 더 좋으면 옮겨 갑니다.
    더 좋은 이웃이 없으면 이동 폭을 반으로 줄이고, 한 칸에서도 없으면 끝납니다. 전체 범위에서 시작하므로
    "한 변수만 경계로 옮기면 좋아지는" 경우도 찾습니다. 캐시에 있는 설계와 제약 위반 설계는 예산에 넣지 않습니다.

    :return: (설계, 값, WEC별 값, 요약 사전)
    """
    x = canonical_copy(best_x, config)
    f, p = best_f, best_p
    start_evals = evaluator.physics_evals
    level = _first_level(config)
    moves = 0
    while level >= 1:
        remaining = max_evals - (evaluator.physics_evals - start_evals)
        if remaining <= 0:
            break
        candidates = _neighbours(x, level, config)[:remaining]
        results = evaluator.evaluate_batch(candidates) if candidates else []
        scores = [result[0] for result in results]
        if scores and max(scores) > f:
            top = int(np.argmax(scores))
            x, f, p = candidates[top].copy(), scores[top], results[top][1]
            moves += 1
        else:
            level //= 2
    summary = {
        "start_fitness": best_f,
        "end_fitness": f,
        "moves": moves,
        "physics_evals": evaluator.physics_evals - start_evals,
        "finished": level < 1,  # False: 예산을 다 써서 끝남
    }
    return x, f, p, summary
