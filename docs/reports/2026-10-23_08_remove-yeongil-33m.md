# 업데이트 보고서: 영일만항 수심 33 m 결과를 검증 기준과 도구에서 제거

- 날짜: 2026-10-23
- 범위: `docs/validation/`, `scripts/experiments/paper_check.py`, `tests/test_paper_check.py`

## 1. 개요

사용자가 영일만항의 정답은 수심 13 m라고 확인했다(2026-10-23). 수심 33 m는 옛 `env_data.csv`의 오류 값이므로, 이를 검증 기준과 시험 도구에서 제거했다. 논문 보고서(`2026-10-23_06`)와 커밋된 이전 보고서는 분석 당시 기록이라 그대로 두었다.

## 2. 변경 내용

- `paper_check_reference.csv`: 영일만항 수심 33 m 행 48개를 삭제(192 → 144행). 부안(50 m), 칠발도(33 m, 이 해역의 실제 수심), 영일만항(13 m)만 남음.
- `paper_check.py`: `OLD_DEPTHS`, `--depths` 옵션, `build_config(..., depth=)` 인자 제거. 각 해역은 항상 `env_data.csv`의 수심으로 계산.
- `tests/test_paper_check.py`: 33 m 관련 기대를 제거(실행 4건 × 12조합, 영일만항 수심은 13).
- `docs/validation/README.md`: 33 m 행과 설명 삭제. 영일만항은 13 m가 정답이며 논문 수치(29.23, 29.32 kW)는 잘못된 수심으로 계산된 값으로 보여 비교 대상이 아님을 명시.

## 3. 호환성 영향

- `paper_check.py --depths` 옵션이 없어졌다. 이전 기준 CSV(192행)로 `--reference` 비교를 하면 영일만항 33 m 행은 사용되지 않는다(해당 행이 결과에 없음).

## 4. 검증

- `ruff check .`, `ruff format --check .`, 단위 테스트 통과. 기준 CSV 144행 확인(영일만항은 수심 13만).

## 5. 남은 이슈 / 후속 작업

- 영일만항은 논문값과 비교할 수 없으므로, 논문 설정(ITTC)으로 DE를 다시 돌릴 때 이 해역의 최적해는 논문과 달라질 수 있다.
- 논문 스펙트럼(ITTC형?)과 Goda 식의 Hs 4.1% 과대는 사용자 판단 대기.
