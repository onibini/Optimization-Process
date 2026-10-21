# 업데이트 보고서: 버그·위험 항목 수정 및 ruff 도입

- 날짜: 2026-10-21
- 범위: `main.py`, `src/algorithms/*`, `src/physics/wamit_handler.py`, `src/problems/*`, `src/utils/*`, `tests/*`, `ruff.toml`, `README.md`, `docs/*`

## 1. 개요

프로젝트 분석에서 찾은 버그·위험 항목 5건과 추가로 발견한 문제들을 수정했습니다.
전체 코드에 ruff lint/format을 적용했습니다.
물리 해석 입력(WAMIT 입력 파일)은 바뀌지 않았습니다.

## 2. 변경 내용

| # | 문제 | 수정 | 파일 |
|---|---|---|---|
| 1 | config 파서가 `line.split('-')`로 주석을 잘라서 음수 값이 있는 줄이 조용히 무시됨 (나중에 KeyError) | 공백 기준 앞 두 토큰을 값/이름으로 읽는 파서로 교체. 중복 키·섹션 밖 값은 줄 번호와 함께 `ConfigParseError` | `src/utils/config_parser.py` (신규), `main.py` |
| 2 | 로그 파일명에 DE만 알고리즘 이름이 없음. `'w'` 모드라 재실행 시 이전 결과가 덮어써짐 | `logs/{Site}_{algorithm}_{YYYYmmdd_HHMMSS}_*` 형식으로 통일. 배타 생성 모드를 쓰고 충돌 시 번호를 붙임. `*_config.json`, `*_summary.json` 추가. summary는 중단돼도 기록 | `src/algorithms/common.py`, 각 알고리즘 |
| 3 | `main.py`가 최적해를 받기만 하고 출력·저장하지 않음 | 최적 적합도, 벡터, R, D, 총 흘수(D+R), 각 기기 좌표를 출력하는 `print_result` 추가 | `main.py` |
| 4 | PSO: 평가 중 입자 위치가 제자리 정렬됨. 5기 배치에서 (x2,y2)↔(x3,y3)가 바뀌는데 속도는 그대로 → 순간이동 | 정렬된 사본으로 평가. 반환하는 최적해는 정렬된 형태 | `src/algorithms/pso.py` |
| 5 | CMA-ES: 정렬·격자화된 벡터로 평균/공분산을 갱신 → 샘플과 갱신 벡터의 대응이 깨짐 | 평가는 격자화·정렬된 사본으로, 분포 갱신은 클리핑된 연속 샘플로 수행 | `src/algorithms/cma_es.py` |
| 6 | 진행 표시의 `Evals`에 패널티 평가가 섞여 있어 실제 WAMIT 실행 수를 알 수 없음 | `eval_func`가 `info={"penalized": True}`를 반환할 수 있게 하고(`penalty_result`), `Hits / WAMIT / Penalty`로 분리 집계. trial 로그에 `penalized` 열 추가 | `src/utils/geometry.py`, `src/algorithms/common.py`, `src/problems/*` |
| 7 | WAMIT 실패 시 출력이 숨겨지고, 이전 실행의 에러 로그가 남음 | `WamitRunError`에 stdout/stderr와 `errorp.log`/`errorf.log` 마지막 부분을 포함. 실행 전에 이전 출력과 에러 로그 삭제. 실행 파일이 없으면 즉시 에러 | `src/physics/wamit_handler.py` |
| 8 | mesh 모듈의 `list[...]` 타입 표기 때문에 Python 3.8에서 import 실패 | `from __future__ import annotations` 추가 | `src/physics/mesh_axisymmetric_shape.py` |
| 9 | PopSize < 4이면 DE/GA/CMA-ES가 실행 중 비정상 동작 | 시작 시 `ValueError` | `de.py`, `ga.py`, `cma_es.py` |
| 10 | `data\env_data.csv` 경로가 Windows 전용 | `os.path.join` 사용 | `src/utils/data_handler.py` |

**ruff**
- `ruff.toml`을 추가했습니다. 줄 길이 120, py38, 규칙 E/W/F/I/B/UP/SIM/C4/RUF.
- lint 지적은 68건에서 0건이 됐습니다.
- 실질적인 항목은 `power_calc.py`의 미사용 `depth` 변수 하나였습니다. 스펙트럼이 심해 형태라 수심을 쓰지 않습니다.
- `ruff format`을 전체 파일에 적용했습니다.

## 3. 호환성 영향

- `OptimizationLogger(config, algorithm=...)`: 이제 `algorithm` 인자가 필요합니다.
- 로그 파일 이름 형식이 바뀌었습니다. 기존 `logs/` 파일은 그대로 남습니다.
- `eval_func`는 `(score, powers)`와 `(score, powers, info)` 둘 다 허용합니다. 기존 형식도 그대로 동작합니다.
- 알고리즘 함수의 반환값 `(best_x, best_f)`는 바뀌지 않았습니다.

## 4. 검증

- 단위 테스트는 14개에서 28개로 늘었고 모두 통과합니다. 추가된 `tests/test_fixes.py`는 WAMIT 없이 실행됩니다.
  - 파서의 음수·중복·섹션 처리
  - 로그 파일 이름 충돌 방지와 summary 기록(중단 시 포함)
  - 패널티 집계
  - 네 알고리즘이 정렬된 최적해를 반환하는지와 수렴 여부
  - PSO 입자 순서 보존
  - WAMIT 실패 메시지와 이전 출력 삭제
- WAMIT 입력 파일 비교: OptMode 1/2/3에서 수정 전후의 `.pot/.frc/.cfg/config.wam/fnames.wam` 15개 파일이 바이트 단위로 동일합니다.
- `main.py`를 더미 평가 함수로 끝까지 실행해 결과 출력과 로그 4종 생성을 확인했습니다.
- 한계: 이 환경에는 WAMIT과 gmsh가 없어서 실제 WAMIT 실행은 검증하지 못했습니다.

## 5. 남은 이슈 / 후속 작업

- Layout/Joint 모드에서만 x=0 벽(`IWALLX0=1`)이 켜집니다. 의도인지 확인이 필요합니다.
- 벽과 기기 사이의 이격(x − R > 0) 제약이 없습니다.
- 최적해가 탐색 경계에 붙는 경향이 있습니다(Buan: D=DraftMax, Chilbaldo: R=RadiusMax). 목적함수 정규화나 범위 확장을 검토할 필요가 있습니다.
- 메시 수렴성(`max_elements=300`) 근거 자료가 아직 없습니다.
