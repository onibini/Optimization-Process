# 업데이트 보고서: 묶음 즉시 교체 DE(`DEUpdate 2`)와 계산용 PC의 WAMIT 동시 실행 측정

- 날짜: 2026-11-01
- 범위:
  - 코드: `src/algorithms/de.py`, `main.py`, `config.cfg`(`DEUpdate` 2)
  - 실험 스크립트: `scripts/experiments/de_update_benchmark.py`(묶음 방식 추가)
  - 요약: `src/utils/run_summary.py`(`de_update`, `workers` 칸)
- WAMIT 입력 파일은 바뀌지 않는다.
- 그림 `docs/reports/images/2026-11-01_02_de_block_parallel.png`
  - (a) 계산용 PC 작업 `20261101_193752_parallel_bench`(`results/`에 가져옴)의 `logs/parallel_wamit_bench.csv`.
  - (b) 이 PC에서 `python scripts/experiments/de_update_benchmark.py --grid 300 --plot`으로 만든 `de_update_final_D7_grid300.png`.

## 1. 개요

사용자 요청: 앞으로 계산용 PC에서는 WAMIT을 여러 개 동시에 돌린다.

문제는 이 프로젝트의 주 알고리즘인 DE의 기본 방식(`DEUpdate` 0, 즉시 교체, 논문과 같음)이다.
- 즉시 교체는 개체 i의 결과를 보고 나서 개체 i+1의 변이를 만든다.
- 그래서 개체를 하나씩 차례로 평가해야 하고, 동시 실행은 초기 개체군에서만 된다.

기존 `DEUpdate` 1(세대 단위 교체)은 세대 전체를 함께 평가할 수 있다. 하지만 즉시 교체와 동작이 달라서 같은 품질에 약 1.15배 세대가 필요했다([보고서 2026-10-23_10](2026-10-23_10_de-update-rule-benchmark.md)).

그래서 사용자와 상의해 두 방식의 중간인 **묶음 즉시 교체**를 추가했다.
- 개체 B개(B = `Workers`)의 시험 벡터를 현재 개체군에서 만들어 함께 평가하고, 결과가 나오면 바로 교체한다.
- 같은 묶음 안의 개체끼리만 서로의 교체를 보지 못하고, 다음 묶음은 바뀐 개체군을 쓴다.
- B = 1이면 즉시 교체와 완전히 같다.

## 2. 변경 내용

**`run_de(update="block")`** (`src/algorithms/de.py`)
- `DE_UPDATES = ("immediate", "generation", "block")`.
- `update_block_size(update, pop_size, workers)`는 함께 평가하는 시험 벡터 수를 돌려준다. 즉시 교체는 1, 세대 단위는 개체 수, 묶음은 `Workers`(개체 수 이하)다.
- 세 방식을 같은 반복문 하나로 정리했다. 묶음마다 시험 벡터를 만들고, 묶음 평가(`evaluate_batch`)를 한 뒤 교체한다.
  - 난수 호출 순서는 세 방식이 같다.
  - 즉시 교체(`evaluate` 하나씩)와 세대 단위의 동작과 결과는 이전과 같다(기존 테스트 통과).

**설정** (`config.cfg` `[AlgorithmSettings]`)
- `DEUpdate`: 0 즉시 교체(기본, 논문), 1 세대 단위, 2 묶음 즉시 교체.
- `main.py`가 0, 1, 2 이외의 값을 거부하고, 2이면 `DE update: immediate in blocks of 4 trials`처럼 출력한다.

**벤치마크** (`de_update_benchmark.py`)
- 방식에 `block2`, `block4`, `block8`을 추가했다(`MODES`).
- 실행마다 즉시 교체와 비교한 Mann-Whitney p값을 출력한다.

**요약표**: `summary.csv`에 `de_update`, `workers` 칸을 추가했다(`init_pop`은 [보고서 2026-11-01_03](2026-11-01_03_lhs-initial-population.md)).

**테스트**
- `tests/test_de_update_benchmark.py`:
  - 벤치마크의 `blockB`가 `run_de(update="block", workers=B)`와 같은 궤적인지 확인(B = 2, 3).
  - `block1`이 즉시 교체와 같은지 확인.
- `tests/test_parallel_eval.py`:
  - `Workers` 1의 묶음 DE가 즉시 교체와 같은지 확인.
  - `Workers` 4에서는 결과가 다르지만 수렴하는지 확인.
  - `update_block_size` 값 확인.

## 3. 호환성 영향

- 기본값(`DEUpdate` 0)의 동작과 결과는 같다.
- `summary.csv`에 칸이 늘었다(`init_pop`, `de_update`, `workers`).
- 사용자가 할 일은 없다. WAMIT을 동시에 돌리려면 `DEUpdate` 2와 `Workers` ≥ 2를 함께 쓴다.

## 4. 검증

### 4.1 계산용 PC 처리량 (그림 (a))

- 측정 조건:
  - 작업은 `parallel_wamit_bench.py --combos 1x8 2x4 4x2 8x1 2x8 4x4 --designs 24`다.
  - 무작위로 고른 5기 설계 24개(간격 제약 만족)를 각 조합으로 평가했다.
  - 계산용 PC는 Ryzen 7 9700X(물리 8코어, 16스레드)다.

| `Workers` × `NCPU` | 1 × 8 | 2 × 4 | 4 × 2 | 8 × 1 | 2 × 8 | **4 × 4** |
| --- | --- | --- | --- | --- | --- | --- |
| 설계 1개당 시간 [s] | 7.40 | 6.58 | 6.63 | 6.57 | 6.24 | **6.23** |
| 속도 향상 | 1.00 | 1.12 | 1.12 | 1.13 | 1.19 | **1.19** |
| 출력 최대 차이 | — | 0.0001% | 0.0002% | 0.0002% | 0.0% | 0.0001% |

- 동시 실행의 이득은 **최대 1.19배로 작다.**
  - 물리 코어 8개를 나눠 쓰는 조합(2×4, 4×2, 8×1)이 모두 1.12~1.13배로 거의 같다.
  - 16스레드를 모두 쓰는 조합(2×8, 4×4)은 1.19배다.
- WAMIT 하나가 `NCPU` 8로 이미 코어를 대부분 쓰고 있다. 그리고 8×1(코어당 WAMIT 하나)도 8배가 아니라 1.13배에 그쳤다.
  - 따라서 시간은 CPU보다 다른 공유 자원에서 정해지는 것으로 보인다. 디스크 입출력(WAMIT의 임시 파일)이나 메모리 대역폭으로 추정한다.
  - 원인은 확인하지 않았다(5절).
- 출력 차이는 0.0002% 이하로, 반복 솔버의 수렴 오차 수준이다.
- **계산용 PC 설정은 `Workers` 4, `NCPU` 4로 정했다.**
  - 2×8과 속도는 같다.
  - 32-bit WAMIT은 `NCPU`가 작을수록 메모리 여유가 크다([보고서 2026-10-23_16](2026-10-23_16_parallel-wamit.md)).
  - DE 묶음 크기 4는 아래 4.2절에서 품질 차이가 없었다.
- 예상 효과: 칠발도 DE 100 × 300(18.97 h)이 약 16 h로 줄어든다.

### 4.2 DE 교체 방식의 품질 (그림 (b))

- 측정 조건:
  - 실행은 `de_update_benchmark.py --grid 300 --plot`이다(이 PC, 20 프로세스, 743 s).
  - 함수 6개 × 차원 7·20 × 연속/격자 300칸 × 방식 5 × 시드 30이다.
  - DE는 논문 설정(개체 100, 300세대, F 0.5, CR 0.9)이다.
- 비교 방법:
  - 각 방식의 마지막 최고값을 즉시 교체와 비교했다(Mann-Whitney).
  - 같은 시드에서 초기 개체군은 같다.

| 방식 | p < 0.05인 경우 (24개 중) | 방향 |
| --- | --- | --- |
| 세대 단위 (`DEUpdate` 1) | 11 | 모두 나쁨. 연속 변수에서 뚜렷함(sphere, rosenbrock, ackley는 p ≤ 1e-6) |
| 묶음 2 | 3 | 섞임 |
| 묶음 4 | 4 | 섞임(rastrigin 격자, griewank D20 격자는 좋음, schwefel D7은 나쁨) |
| 묶음 8 | 2 | 섞임 |

- 묶음 방식은 72번 비교에서 9번 p < 0.05가 나왔다. 아무 차이가 없어도 우연히 나오는 비율(5%, 약 4번)보다 조금 많지만, 좋아진 경우와 나빠진 경우가 섞여 있고 중앙값 차이도 작다.
- 반면 세대 단위는 11번 모두 나빠지는 쪽이었다.
- WEC 문제와 비슷한 7차원 격자(그림 (b))에서는 묶음 2·4·8의 분포가 즉시 교체와 겹친다.
- 결론: 개체 100에 묶음 4는 즉시 교체와 품질이 같다고 본다. 세대 단위보다 논문 방식에 훨씬 가깝다.

### 4.3 코드 검사

- `ruff check .`, `ruff format --check .` 통과.
- `python -m unittest discover -s tests`: 292건 통과(3건 건너뜀). [보고서 2026-11-01_03](2026-11-01_03_lhs-initial-population.md)의 변경과 함께 실행했다.

## 5. 남은 이슈 / 후속 작업

- **동시 실행 이득이 작은 원인**: 디스크 입출력 때문인지 확인한다.
  - 예: `workspace`를 RAM 디스크에 두거나, 작업 중 디스크와 CPU 사용률을 기록한다.
  - 원인이 디스크라면 동시 실행보다 그쪽 개선이 더 클 수 있다.
- 실제 WEC 최적화에서 `DEUpdate` 2와 0을 같은 시드로 비교한 결과는 아직 없다. 벤치마크 함수 결과로 판단했다.
- 결과를 논문과 비교할 때는 `DEUpdate`(0 또는 2)를 함께 적는다.
