import csv
import json
import os
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np

from src.utils import canonicalize_vector_inplace

# (상한 - 하한) / step 계산 시 부동소수점 오차 보정용 허용치.
# 예: (30.0 - 0.1) / 0.1 = 298.99999999999994 -> 보정 없이 내림하면 상한 30.0에 도달하지 못함.
GRID_TOLERANCE = 1e-9


def get_step_size(config):
    """설계 변수별 격자 간격을 반환합니다 (스칼라 또는 변수 수 길이의 배열)."""
    step_size = np.asarray(config.get("step_size", 0.1), dtype=float)
    if np.any(step_size <= 0):
        raise ValueError(f"StepSize must be positive, got {step_size}")
    return step_size


def get_bounds(config):
    return np.array(config["bounds"][0]), np.array(config["bounds"][1])


def grid_max_indices(config):
    """각 변수의 최대 격자 인덱스 (하한 = 0번 격자점)."""
    lower_bounds, upper_bounds = get_bounds(config)
    ratio = (upper_bounds - lower_bounds) / get_step_size(config)
    return np.floor(ratio + GRID_TOLERANCE * np.maximum(1.0, np.abs(ratio))).astype(int)


def quantize_vector(vector, config):
    lower_bounds, _ = get_bounds(config)
    step_size = get_step_size(config)
    max_indices = grid_max_indices(config)
    step_indices = np.floor((vector - lower_bounds) / step_size + 0.5).astype(int)
    step_indices = np.clip(step_indices, 0, max_indices)
    quantized = lower_bounds + step_indices * step_size
    return np.round(quantized, 10)


def quantize_vector_inplace(vector, config):
    vector[:] = quantize_vector(vector, config)
    return vector


def random_grid_population(pop_size, config):
    lower_bounds, _ = get_bounds(config)
    step_size = get_step_size(config)
    max_indices = grid_max_indices(config)
    random_indices = np.array([np.random.randint(0, max_idx + 1, size=pop_size) for max_idx in max_indices]).T
    return np.round(lower_bounds + random_indices * step_size, 10)


def make_cache_key(vector, config):
    lower_bounds, _ = get_bounds(config)
    step_size = get_step_size(config)
    return tuple(np.floor((vector - lower_bounds) / step_size + 0.5).astype(int))


def canonical_copy(vector, config):
    """격자 스냅 + 대칭 정렬된 사본을 반환합니다 (원본은 건드리지 않음)."""
    result = quantize_vector(np.asarray(vector, dtype=float), config)
    canonicalize_vector_inplace(result, config["opt_mode"], config["num_wecs"])
    return result


def _json_default(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return str(obj)


class OptimizationLogger:
    """실행 1회분의 trial / generation 기록과 요약을 저장합니다.

    파일 이름: ``logs/{SiteName}_{algorithm}_{YYYYmmdd_HHMMSS}_{kind}.csv``
    - 알고리즘 이름이 항상 들어가므로 DE/PSO/GA/CMA-ES 로그가 섞이지 않습니다.
    - 실행 시각(run id)이 들어가므로 같은 조건으로 다시 돌려도 이전 결과를 덮어쓰지 않습니다.
    - 실행에 사용된 문제 설정은 ``*_config.json``, 최종 결과는 ``*_summary.json``으로 남습니다.
    """

    def __init__(self, config, algorithm, log_dir="logs", run_id=None):
        os.makedirs(log_dir, exist_ok=True)

        dimensions = config["dimensions"]
        num_wecs = config["num_wecs"]
        site_name = config.get("site_name", "Unknown")
        run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # 같은 초에 두 번 실행되는 경우에도 덮어쓰지 않도록 번호를 붙임
        base = os.path.join(log_dir, f"{site_name}_{algorithm}_{run_id}")
        prefix, n = base, 1
        while os.path.exists(f"{prefix}_trial_history.csv"):
            n += 1
            prefix = f"{base}_{n}"
        self.prefix = prefix
        self.algorithm = algorithm
        self.started_at = datetime.now()

        self.trial_path = f"{prefix}_trial_history.csv"
        self.gen_path = f"{prefix}_generation_history.csv"
        self.config_path = f"{prefix}_config.json"
        self.summary_path = f"{prefix}_summary.json"

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"algorithm": algorithm, **config}, f, indent=2, ensure_ascii=False, default=_json_default)

        # 실행 내내 열어두고 매 줄마다 flush 하는 로그 파일 (close()에서 닫음)
        self.trial_file = open(self.trial_path, "x", newline="")  # noqa: SIM115
        self.gen_file = open(self.gen_path, "x", newline="")  # noqa: SIM115
        self.trial_writer = csv.writer(self.trial_file)
        self.gen_writer = csv.writer(self.gen_file)

        vec_headers = [f"v{i + 1}" for i in range(dimensions)]
        p_headers = [f"p{i + 1}" for i in range(num_wecs)]
        self.trial_writer.writerow([*vec_headers, "fitness", *p_headers, "penalized"])
        self.gen_writer.writerow(["iter", *vec_headers, "fitness", *p_headers, "time"])

    def write_trial(self, vector, score, individual_powers, penalized=False):
        self.trial_writer.writerow([*list(vector), score, *list(individual_powers), int(penalized)])
        self.trial_file.flush()

    def write_generation(self, gen_idx, vector, score, individual_powers, elapsed_time):
        self.gen_writer.writerow([gen_idx, *list(vector), score, *list(individual_powers), f"{elapsed_time:.2f}"])
        self.gen_file.flush()

    def write_summary(self, best_x, best_f, best_p, evaluator, generations_completed):
        summary = {
            "algorithm": self.algorithm,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "generations_completed": generations_completed,
            "best_vector": best_x,
            "best_fitness": best_f,
            "best_individual_powers": best_p,
            **evaluator.stats(),
        }
        with open(self.summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=_json_default)

    def close(self):
        self.trial_file.close()
        self.gen_file.close()


class CachedEvaluator:
    """격자 스냅 + 대칭 정렬 후 캐시를 조회하고, 미스일 때만 eval_func를 호출합니다.

    eval_func는 ``(score, individual_powers)`` 또는 ``(score, individual_powers, info)``를 반환합니다.
    ``info.get("penalized")``가 True이면 제약 위반으로 WAMIT을 실행하지 않은 평가로 집계합니다.

    ``config["eval_cache"]``가 참이면 평가 기록 데이터베이스(``src/utils/eval_db.py``)에서 설정 지문이 같은
    기록을 미리 불러옵니다. 저장된 설계는 eval_func 없이 그 값을 쓰고, 처음 쓸 때 trial 기록에 남기며
    ``stored_hits``로 따로 셉니다(WAMIT·캐시 적중 수에는 넣지 않음).
    """

    def __init__(self, config, eval_func, logger):
        self.config = config
        self.eval_func = eval_func
        self.logger = logger
        self.workers = max(1, int(config.get("workers") or 1))  # 동시에 돌리는 WAMIT 수 (evaluate_batch)
        self.memory_cache = {}
        self.cache_hits = 0
        self.total_evals = 0  # 캐시 미스 = 고유 설계점 평가 수 (패널티 포함)
        self.penalty_evals = 0  # 제약 위반으로 물리 해석 없이 패널티를 받은 평가 수
        self.stored = {}  # 불러왔지만 아직 쓰지 않은 기록: 캐시 키 -> (score, powers, penalized, vector)
        self.stored_loaded = 0
        self.stored_hits = 0  # 데이터베이스 값으로 대신한 평가 수
        if config.get("eval_cache"):
            from src.utils.eval_db import ROOT, load_for

            rows, path = load_for(config, config.get("eval_db_dir") or os.path.join(ROOT, "data", "eval_db"))
            self.preload(rows)
            name = os.path.basename(path) if path else "(settings not recorded)"
            print(f"Stored evaluations: {self.stored_loaded} designs from {name}")

    def preload(self, rows):
        """``(vector, score, powers, penalized)`` 목록을 저장 기록으로 등록. 이 문제의 격자 밖인 설계는 건너뜀."""
        for vector, score, powers, penalized in rows:
            canon = canonical_copy(vector, self.config)
            if len(canon) != len(vector) or not np.allclose(canon, vector, atol=1e-9):
                continue
            key = make_cache_key(canon, self.config)
            if key not in self.memory_cache and key not in self.stored:
                self.stored[key] = (score, list(powers), bool(penalized), canon)
        self.stored_loaded = len(self.stored)

    def _use_stored(self, key):
        score, powers, penalized, vector = self.stored.pop(key)
        self.stored_hits += 1
        self.memory_cache[key] = (score, powers)
        self.logger.write_trial(vector, score, powers, penalized=penalized)
        return self.memory_cache[key]

    @property
    def physics_evals(self):
        """실제 물리 해석(WAMIT)이 실행된 횟수."""
        return self.total_evals - self.penalty_evals

    def evaluate(self, vector):
        quantize_vector_inplace(vector, self.config)
        canonicalize_vector_inplace(vector, self.config["opt_mode"], self.config["num_wecs"])
        mem_key = make_cache_key(vector, self.config)

        if mem_key in self.memory_cache:
            self.cache_hits += 1
            return self.memory_cache[mem_key]
        if mem_key in self.stored:
            return self._use_stored(mem_key)

        self.total_evals += 1
        output = self.eval_func(vector, self.config)
        score, individual_powers = output[0], output[1]
        info = output[2] if len(output) > 2 else {}
        penalized = bool(info.get("penalized", False))
        if penalized:
            self.penalty_evals += 1

        result = (score, individual_powers)
        self.memory_cache[mem_key] = result
        self.logger.write_trial(vector, score, individual_powers, penalized=penalized)
        return result

    def evaluate_batch(self, vectors, on_result=None):
        """여러 벡터를 평가합니다. ``evaluate``를 차례로 부른 것과 같은 결과·캐시·로그 순서를 냅니다.

        캐시에 없는 서로 다른 설계점은 ``workers``개의 스레드로 동시에 평가합니다. 스레드마다 작업 폴더
        ``<workspace_dir>/w<k>``를 하나씩 맡으므로 WAMIT 실행이 서로 겹치지 않습니다(WAMIT은 별도 프로세스라
        스레드로도 동시에 실행됩니다). ``workers``가 1이면 기존 작업 폴더에서 차례로 평가합니다.

        ``on_result(score)``를 주면 벡터 하나의 값이 정해질 때마다(캐시 적중 포함, 끝난 순서대로) 메인
        스레드에서 부릅니다. 모두 ``len(vectors)``번 불립니다(진행 막대용).
        """
        keys = []
        for vector in vectors:
            quantize_vector_inplace(vector, self.config)
            canonicalize_vector_inplace(vector, self.config["opt_mode"], self.config["num_wecs"])
            keys.append(make_cache_key(vector, self.config))

        def notify(score):
            if on_result is not None:
                on_result(score)

        cached = [idx for idx, key in enumerate(keys) if key in self.memory_cache]
        for idx in cached:
            notify(self.memory_cache[keys[idx]][0])
        from_store = set()  # 데이터베이스 값으로 정해진 벡터 (같은 키가 다시 나오면 그다음부터는 캐시 적중)
        for idx, key in enumerate(keys):
            if key in self.stored:
                notify(self._use_stored(key)[0])
                from_store.add(idx)

        first = {}  # 캐시에 없는 설계점 -> 처음 나온 위치
        for idx, key in enumerate(keys):
            if key not in self.memory_cache and key not in first:
                first[key] = idx
        todo = list(first.items())
        if self.workers > 1 and len(todo) > 1:
            base = self.config.get("workspace_dir", "workspace")
            slots = queue.Queue()
            for k in range(self.workers):
                slots.put(os.path.join(base, f"w{k}"))

            def run(idx):
                workspace = slots.get()
                try:
                    return self.eval_func(vectors[idx], {**self.config, "workspace_dir": workspace})
                finally:
                    slots.put(workspace)

            outputs = [None] * len(todo)
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {pool.submit(run, idx): n for n, (_, idx) in enumerate(todo)}
                for future in as_completed(futures):
                    outputs[futures[future]] = future.result()
                    notify(outputs[futures[future]][0])
        else:
            outputs = []
            for _, idx in todo:
                outputs.append(self.eval_func(vectors[idx], self.config))
                notify(outputs[-1][0])

        for (key, idx), output in zip(todo, outputs, strict=True):
            self.total_evals += 1
            score, individual_powers = output[0], output[1]
            info = output[2] if len(output) > 2 else {}
            penalized = bool(info.get("penalized", False))
            if penalized:
                self.penalty_evals += 1
            self.memory_cache[key] = (score, individual_powers)
            self.logger.write_trial(vectors[idx], score, individual_powers, penalized=penalized)

        fresh = {idx for _, idx in todo}
        self.cache_hits += sum(1 for idx in range(len(vectors)) if idx not in fresh and idx not in from_store)
        reported = fresh.union(cached, from_store)
        for idx in range(len(vectors)):  # 같은 배치 안에서 앞의 설계점과 겹친 벡터
            if idx not in reported:
                notify(self.memory_cache[keys[idx]][0])
        return [self.memory_cache[key] for key in keys]

    def stats(self):
        return {
            "unique_evals": self.total_evals,
            "physics_evals": self.physics_evals,
            "penalty_evals": self.penalty_evals,
            "cache_hits": self.cache_hits,
            "stored_hits": self.stored_hits,
        }
