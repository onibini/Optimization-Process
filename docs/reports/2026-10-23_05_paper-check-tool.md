# 업데이트 보고서: 논문 최적해 재현 확인 도구 (`paper_check.py`)

- 날짜: 2026-10-23
- 범위: `scripts/experiments/paper_check.py`, `tests/test_paper_check.py` (`src/` 변경 없음)

## 1. 개요

`adaptive_omegas`(FreqGrid)를 쓰기 전에, 현재 평가 과정이 논문(동시 최적화 논문 ver14) 결과를 재현하는지 확인한다. 논문 Table 4의 부안·칠발도·영일만항 최적해(순차·동시 각 3개, 총 6개)를 최적화 없이 `evaluate_joint`(최적화기가 쓰는 같은 평가 함수)로 평가해 논문의 총 발전량과 비교한다. 아직 계산용 PC에 제출하지 않았다.

## 2. 변경 내용

- `scripts/experiments/paper_check.py`: Table 4의 설계 6개와 논문 발전량(kW)을 담고, 변형별로 평가해 `logs/paper_check.csv`(논문값, 계산값, 차이 %, WEC별 kW, 시간)를 쓴다. 변형: `base`(config.cfg 설정, 균일 0.05), `fg`(FreqGrid=1), `mesh200`(패널 200), `mesh200fg`. `--variants`, `--sites`, `--dry-run`.
- **설계 변수 대응(중요):** 논문은 WEC3이 중심선(y=0), WEC1 (x1, ±y1), WEC2 (x2, ±y2)이고, 프로젝트 벡터 `[R, D, X1, X2, Y2, X3, Y3]`는 WEC1이 중심선, 쌍이 (X2, ±Y2), (X3, ±Y3)이다. 따라서 논문 (x1, y1, x2, y2, x3, r, d)는 `[r, d, x3, x2, y2, x1, y1]`로 넣는다(같은 5개 위치; 테스트로 확인). 환경(Hs, Tp, γ=1.4, 수심)은 `env_data.csv`가 논문 Table 1과 같고, `WaveSpec=2`(Goda)이다.
- `tests/test_paper_check.py`(5건): 벡터가 논문의 5개 위치를 만드는지, 6개 설계가 탐색 범위와 최소 간격 규칙 안에 있는지, 변형 설정이 문제 설정에 전달되는지, 가짜 평가로 결과 표 작성, `--dry-run`은 평가하지 않음.

## 3. 호환성 영향

없음(새 시험 스크립트와 테스트).

## 4. 검증

- `ruff check .`, `ruff format --check .`, 단위 테스트 171건(skip 3) 통과. `--dry-run`으로 6개 설계의 벡터와 위치를 확인했다.
- WAMIT은 실행하지 않았다.

## 5. 남은 이슈 / 후속 작업

- 확인 후 계산용 PC에서 `python scripts/experiments/paper_check.py`를 실행(평가 24건, 예상 수십 분). 결과가 논문과 얼마나 다른지에 따라: (가) 격자·메쉬 차이인지 변형별 차이로 판단, (나) 논문 당시 물리 코드(보고서 01~04의 수정 이전)와의 차이인지 그 이전 커밋과 비교.
- 그 다음 단계: 논문과 같은 설정으로 DE를 다시 돌려 같은 최적해가 나오는지 확인(비용이 커서 별도 확인 필요).
- 논문의 주파수 개수·메쉬 사양은 문서에 없어 알 수 없다. 논문 당시 코드의 설정과 대조해야 한다.
