# 업데이트 보고서: 주파수 격자 설계안과 검증 스크립트

- 날짜: 2026-10-22
- 범위: `docs/frequency_grid_design.md`(신규), `scripts/experiments/freq_grid_study.py`(신규), `tests/test_freq_grid_study.py`(신규), `CHANGELOG.md`, `report/`

## 1. 개요

알고리즘(DE)과 동시 최적화를 유지한 채 WAMIT 평가 시간을 줄이기 위해 (A) 주파수 점 수를 NCPU의 배수로 맞추는 옵션과 (B) 공진 부근만 촘촘한 주파수 격자를 설계했습니다. 구현 전에 설계안을 `docs/frequency_grid_design.md`에 정리했고, 계산용 PC(Ryzen 7 9700X)에서 검증할 스크립트를 준비했습니다. `src/` 코드와 WAMIT 입력은 바뀌지 않았습니다.

## 2. 변경 내용

- `docs/frequency_grid_design.md`: 배경, 현재 동작, 설계 A(`FreqAlign`), 설계 B(`FreqGrid=adaptive`, `ω0 = sqrt(g / (D + 2R/3))` 기반 구간), 점 수 예산, 구현 범위, 검증 계획과 판정 기준, 결정이 필요한 항목.
- `scripts/experiments/freq_grid_study.py`: `grids`(후보 격자 대 201점 기준격자), `ncpu`(NCPU×점 수 시간), `limit`(NCPU별 메모리 한계) 연구와 `--quick`, `--dry-run`. 후보 격자 생성 함수(균일, 적응형, 꼬리 성기게, NCPU 정렬)를 포함합니다. 결과는 `logs/freq_grid_study_<연구>.csv`에 씁니다.
- `tests/test_freq_grid_study.py`: 위 격자 함수 16건(공진 주파수 값, 균일 51/201점, 미세 구간의 간격과 포함 여부, 꼬리 성기게, 구간이 상한 밖일 때, NCPU 정렬 up/down과 모든 NCPU).

## 3. 호환성 영향

없습니다. 새 파일만 추가되었고 `config.cfg`, `main.py`, WAMIT 입력, 로그 형식은 그대로입니다.

## 4. 검증

- 이 PC에서 WAMIT은 실행하지 않았습니다(계산용 PC에서 하기로 함). `--dry-run`으로 입력 생성과 격자 점 수만 확인했습니다.
- `ruff check .`, `ruff format --check .`, 단위 테스트 117건(skip 3) 통과.
- 근거가 된 실측(보고서 10): 공진 부근 0.0125 간격 비균일 49점이 201점과 0.02% 차이, 균일 51점은 +4.1%, 0.025 간격은 +0.3%.

## 5. 남은 이슈 / 후속 작업

- 설계안 승인과 결정 4건(기본값, 작은 WEC의 상한 자동 확장, 판정 기준, `remote.ps1`의 `-Script` 옵션).
- 계산용 PC에서 `grids`, `ncpu`, `limit` 연구 실행과 결과 분석, 그 후 구현.
