"""평가 기록 데이터베이스: 이미 계산한 설계의 발전량을 저장하고 다시 씁니다.

평가 결과(발전량)는 해역 환경, 스펙트럼, 형상, 메쉬, 솔버, 주파수, 벽, 입사각에 따라 달라집니다. 이 값들을
모은 **설정 지문**(``fingerprint``)이 같은 기록만 같은 파일에 모으고, 같은 지문의 실행에서만 불러옵니다.
지문이 하나라도 다르면 쓰지 않으므로, 평가 방식을 바꾼 뒤 옛 값을 잘못 쓰지 않습니다.

평가 코드 자체를 바꿔 같은 설정에서도 값이 달라지면(예: 메쉬 생성, RAO, 발전량 공식) ``EVAL_VERSION``을
올립니다. 그러면 이전 파일은 더 이상 불러오지 않습니다.

파일: ``data/eval_db/<site>_mode<opt>_n<wecs>_<id>.csv``와 지문을 적은 ``.json``.
열: ``v1..vD``(정렬된 설계 변수), ``fitness``, ``p1..pN``, ``penalized``, ``source``(처음 기록한 실행).
"""

import csv
import hashlib
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_DIR = os.path.join(ROOT, "data", "eval_db")

# 평가 코드의 판. 같은 설정에서 발전량이 달라지는 변경을 하면 올림 (1: 2026-10-23 이후, 메쉬 120 기본)
EVAL_VERSION = 1

# 지문에 들어가는 문제 설정 키. 값이 None인 키는 예전 기록에 없을 때 쓰는 기본값이 없다는 뜻이며,
# 그런 기록(키가 없는 옛 실행)은 지문을 만들 수 없어 데이터베이스에 넣지 않음.
FINGERPRINT_DEFAULTS = {
    "site_name": None,
    "opt_mode": None,
    "num_wecs": None,
    "wave_spec": None,
    "hs": None,
    "tp": None,
    "gamma": None,
    "depth": None,
    "mesh_panels": None,
    "solver": None,
    "omega_max": None,
    "freq_grid": None,
    "shape": 1,
    "vertical_wall": 1,
    "wave_angle": 0.0,
    "hydro_solver": 1,
}
# 해당 모드에서만 결과에 영향을 주는 키 (없으면 지문에서 뺌)
MODE_KEYS = {1: (), 2: ("min_spacing", "fixed_radius", "fixed_draft"), 3: ("min_spacing",)}


def _normalize(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = round(float(value), 10)
        return int(value) if value.is_integer() else value
    return value


def fingerprint(config):
    """문제 설정에서 평가 결과를 정하는 값만 모은 사전. 정할 수 없으면 None."""
    fp = {}
    for key, default in FINGERPRINT_DEFAULTS.items():
        value = config.get(key, default)
        if value is None:
            value = default
        if value is None:
            return None
        fp[key] = _normalize(value)
    for key in MODE_KEYS.get(fp["opt_mode"], ()):
        if config.get(key) is None:
            return None
        fp[key] = _normalize(config[key])
    if fp["opt_mode"] == 1:
        fp["vertical_wall"] = 0  # OptMode 1은 항상 개방 해역
        fp["wave_angle"] = 0
    if not fp["vertical_wall"]:
        fp["wave_angle"] = 0  # 개방 해역은 입사각 0만 허용
    fp["eval_version"] = EVAL_VERSION
    return fp


def db_name(fp):
    digest = hashlib.sha1(json.dumps(fp, sort_keys=True).encode()).hexdigest()[:10]
    return f"{fp['site_name']}_mode{fp['opt_mode']}_n{fp['num_wecs']}_{digest}"


def db_path(config, db_dir=DEFAULT_DB_DIR):
    """이 설정의 데이터베이스 CSV 경로. 지문을 만들 수 없으면 None."""
    fp = fingerprint(config)
    return None if fp is None else os.path.join(db_dir, db_name(fp) + ".csv")


def _row_key(vector):
    return tuple(np.round(np.asarray(vector, dtype=float), 6))


def read_records(path):
    """CSV를 ``{정렬 벡터 키: (vector, fitness, powers, penalized, source)}``로 읽음."""
    records = {}
    if not os.path.exists(path):
        return records
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        v_cols = [c for c in reader.fieldnames if c.startswith("v")]
        p_cols = [c for c in reader.fieldnames if c.startswith("p") and c[1:].isdigit()]
        for row in reader:
            vector = [float(row[c]) for c in v_cols]
            records[_row_key(vector)] = (
                vector,
                float(row["fitness"]),
                [float(row[c]) for c in p_cols],
                bool(int(row["penalized"])),
                row.get("source", ""),
            )
    return records


def write_records(path, fp, records):
    """기록 전체를 CSV와 지문 JSON으로 씀 (벡터 순으로 정렬)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    items = sorted(records.values(), key=lambda r: tuple(r[0]))
    dims = len(items[0][0]) if items else 0
    n_p = len(items[0][2]) if items else 0
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [*(f"v{i + 1}" for i in range(dims)), "fitness", *(f"p{i + 1}" for i in range(n_p)), "penalized", "source"]
        )
        for vector, fitness, powers, penalized, source in items:
            writer.writerow([*vector, fitness, *powers, int(penalized), source])
    os.replace(tmp, path)
    meta = {"fingerprint": fp, "designs": len(items), "physics_evals": sum(1 for r in items if not r[3])}
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def merge_records(records, new_rows, source, tolerance=1e-4):
    """``new_rows``((vector, fitness, powers, penalized) 목록)를 더함. 반환: (추가 수, 값이 다른 중복 수)."""
    added = conflicts = 0
    for vector, fitness, powers, penalized in new_rows:
        key = _row_key(vector)
        old = records.get(key)
        if old is None:
            records[key] = (list(vector), float(fitness), list(powers), bool(penalized), source)
            added += 1
        elif abs(old[1] - fitness) > tolerance * max(abs(old[1]), 1.0):
            conflicts += 1
    return added, conflicts


def load_for(config, db_dir=DEFAULT_DB_DIR):
    """이 설정과 지문이 같은 기록을 ``(vector, fitness, powers, penalized)`` 목록으로. 없으면 빈 목록."""
    path = db_path(config, db_dir)
    if path is None:
        return [], None
    return [r[:4] for r in read_records(path).values()], path
