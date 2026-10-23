# 업데이트 보고서: WAMIT 동시 실행(Workers)과 동기식 DE 옵션

- 날짜: 2026-10-23
- 범위: `src/algorithms/common.py`(`evaluate_batch`), `src/algorithms/{de,ga,cma_es,pso,depso}.py`, `src/problems/*.py`(작업 폴더), `src/physics/wamit_handler.py`(`DEFAULT_WORKSPACE`), `main.py`, `config.cfg`(`Workers`, `DEUpdate`), `scripts/experiments/parallel_wamit_bench.py`(신규), `tests/test_parallel_eval.py`·`tests/test_parallel_wamit_bench.py`(신규), `README.md`, `docs/algorithms_and_problems.md`, `docs/architecture.md`

## 1. 개요

32-bit WAMIT은 프로세스 하나가 쓸 수 있는 메모리가 작지만 계산용 PC 메모리는 넉넉하고 동시 실행이 허용된다(사용자 확인). 그래서 서로 독립인 평가를 여러 WAMIT 프로세스로 동시에 돌리는 기능을 넣었다. 기본값(`Workers=1`, `DEUpdate=0`)에서는 동작과 결과가 이전과 같다.

## 2. 변경 내용

- **`CachedEvaluator.evaluate_batch(vectors)`**: 벡터들을 격자 스냅·대칭 정렬하고, 캐시에 없는 서로 다른 설계점만 `Workers`개의 스레드로 동시에 평가한다. 스레드마다 작업 폴더 `workspace/w<k>`를 맡는다(WAMIT은 별도 프로세스라 스레드로 동시에 돈다). 캐시·카운터·시험 로그는 하나씩 평가한 것과 같은 순서로 채운다. `Workers=1`이면 기존 `workspace`에서 하나씩 평가한다.
- **문제 평가 함수**: `config["workspace_dir"]`(기본 `workspace`)를 쓴다.
- **알고리즘**
  - 초기 개체군: 모든 알고리즘이 묶음으로 평가(결과 동일).
  - GA, CMA-ES: 한 세대를 묶음으로 평가(난수·결과 동일).
  - DE: `DEUpdate`(`[AlgorithmSettings]`) 0 = 즉시 교체(기본, 논문), 1 = 세대 단위(동기식, 세대를 묶음 평가). 두 방식은 같은 난수열을 쓴다. 세대 단위는 같은 품질에 약 1.15배 세대가 필요하다(`2026-10-23_10` 보고서).
  - PSO, DEPSO: 즉시 갱신 구조라 세대 안은 하나씩(초기 개체군만 병렬). `main.py`가 이 경우 경고를 낸다.
- **`config.cfg`**: `[WAMIT Settings] Workers`(기본 1; `NCPU`는 WAMIT 하나당 코어 수, `Workers × NCPU` ≤ 코어 수), `[AlgorithmSettings] DEUpdate`(기본 0). `main.py`가 동시 실행 수와 총 코어 수를 출력한다.
- **`parallel_wamit_bench.py`**: 같은 설계(무작위, 간격 제약 만족, 시드 고정) 24개를 `Workers × NCPU` 조합(기본 1×8, 2×4, 4×2, 8×1)으로 평가해 벽시계 시간·속도 향상·발전량 차이를 `logs/parallel_wamit_bench.csv`에 쓴다(계산용 PC용).

## 3. 호환성 영향

- 기본값에서는 WAMIT 입력과 결과가 이전과 같다(작업 폴더 `workspace`).
- `Workers > 1`이면 `workspace/w0`, `w1`, ...이 생긴다(`workspace/`는 gitignore).
- 새 설정 키는 없으면 기본값(`Workers=1`, `DEUpdate=0`).

## 4. 검증

- 테스트 7건: 묶음 평가가 하나씩 평가한 것과 결과·로그·카운터가 같음(캐시 적중·패널티·중복 포함), 동시 실행이 실제로 겹치고(최대 3개 동시, 시간 단축) 작업 폴더가 서로 다름, `Workers=1`은 기본 폴더, DE(즉시·세대)·PSO·GA·CMA-ES·DEPSO가 `Workers=1`과 `4`에서 같은 결과, 세대 단위 DE는 즉시 교체와 다르고 수렴함, 벤치마크 스크립트(가짜 평가)의 표·작업 폴더 정리·설계 재현성.
- 실제 WAMIT 동시 실행 속도는 아직 재지 않았다(계산용 PC가 CMA-ES 작업 중).
- 전체 단위 테스트, `ruff check .`, `ruff format --check .` 통과.

## 5. 남은 이슈 / 후속 작업

- CMA-ES 작업이 끝나면 계산용 PC에서 `parallel_wamit_bench.py`로 조합별 처리량을 잰다. 32-bit 메모리 한계는 NCPU가 작을수록 여유가 있다(1,320 패널은 NCPU 8에서 실패, 4에서 성공).
- 측정 결과 이득이 1.15~1.4배보다 크면 DE도 `DEUpdate=1`로 세대 단위 병렬이 유리하다(논문 DE와의 동작 차이는 사용자 판단).
- `summary.csv`에는 아직 `Workers` 열이 없다.
