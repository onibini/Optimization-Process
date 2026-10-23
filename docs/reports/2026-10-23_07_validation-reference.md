# 업데이트 보고서: 검증 기준 결과 정리와 `paper_check.py --reference`

- 날짜: 2026-10-23
- 범위: `docs/validation/`(신규), `scripts/experiments/paper_check.py`, `tests/test_paper_check.py`

## 1. 개요

현재 최신 프로세스로 계산한 논문 최적해 6개의 결과를 기준 자료로 정리해, 이후 파일(주파수 격자·메쉬·스펙트럼·물리·환경 데이터)을 바꿨을 때 결과가 바뀌었는지 확인할 수 있게 했다.

## 2. 변경 내용

- `docs/validation/paper_check_reference.csv`: 계산용 PC 결과 192행(2026-10-23, 커밋 `ee65e22` + `paper_check.py`).
- `docs/validation/README.md`: 기준의 조건(설정·코드 상태), 논문과의 비교표, 해석(Goda +8%, 영일만항 수심 오류), 바꾼 항목별 기대 결과, 재실행 명령, 한계.
- `paper_check.py --reference <csv> [--tolerance 0.2]`: 같은 조합의 총 발전량을 기준과 비교해 허용 오차(%)를 넘는 조합을 출력하고 종료 코드 1을 반환(겹치는 조합이 없으면 실패). `compare_with_reference` 함수.
- 테스트 1건 추가(같은 결과는 통과, 1% 진폭 변화는 실패).

## 3. 호환성 영향

없음(새 문서와 시험 스크립트 옵션).

## 4. 검증

- `ruff check .`, `ruff format --check .`, 단위 테스트 통과.
- 기준 CSV의 열·행 수(192)를 확인했고, 비교 함수는 가짜 WAMIT으로 테스트했다. 실제 WAMIT으로 `--reference` 실행은 하지 않았다(파일을 바꾼 뒤에 사용).

## 5. 남은 이슈 / 후속 작업

- 사용자 판단 대기: 논문 계산의 스펙트럼(ITTC형?). 코드의 Goda 식 정규화 문제.
- 영일만항 환경 파일 수심 오류 확인 결과(논문 계산이 33 m였는지)는 사용자가 판단함. 논문 영일만항 수치는 13 m 참값이 아님.
- 이후: 논문 설정으로 DE 재실행, `FreqGrid` 적용 전후 `--reference` 비교.
