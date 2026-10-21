# 업데이트 보고서: RAO 가진력을 diffraction(.3) 기준으로 변경

- 날짜: 2026-10-21
- 범위: `src/physics/rao_calc.py`, `src/physics/wamit_handler.py`, `tests/test_excitation.py`(신규), `tests/test_step_size.py`, `docs/architecture.md`

## 1. 개요

RAO 계산에 쓰는 파랑 가진력을 Haskind 관계식(`wec.2`)에서 diffraction 가진력(`wec.3`, 입사파+산란파 압력 적분)으로 바꿨습니다. 기존 `IDIFF=0`(radiation + diffraction)이라 WAMIT은 이미 diffraction 문제를 풀고 있으므로 추가 해석 비용은 없습니다.

## 2. 변경 내용

- `wamit_handler.py`: `.frc` 출력 옵션을 `1 0 1 0 0 0 0 0 0`으로 변경 (`.1`, `.3` 요청, `.2` 생략). `EXCITATION_OUTPUT_OPTIONS`에 두 방식의 옵션을 정의하고 `write_frc_file(..., excitation="diffraction")`로 선택합니다.
- `rao_calc.py`: `calculate_rao_matrix(..., excitation="diffraction")`가 `wec.3`을 읽습니다. `"haskind"`를 주면 `wec.2`를 읽습니다. 그 외 값은 `ValueError`, 파일이 없으면 파일명이 담긴 `WamitOutputError`입니다.
- `.3`과 `.2`는 열 구성이 같아(주파수, 방향, DOF, 크기, 위상, 실수, 허수) 파싱 코드는 그대로입니다.
- `run_wamit`은 원래 `wec.3`도 실행 전에 지우고 있어 수정이 필요 없었습니다.

## 3. 호환성 영향

- **결과 값이 달라집니다.** 같은 형상이라도 Haskind와 diffraction 값이 완전히 같지 않으므로, 이전 로그의 파워와 직접 비교하지 마세요.
- WAMIT 입력 파일 변경은 `wec.frc`의 출력 옵션 한 줄뿐입니다.
- 사용자가 할 일은 없습니다. 이전 방식이 필요하면 `excitation="haskind"`를 두 함수에 넘기면 됩니다(현재 config 항목은 없습니다).

## 4. 검증

- 단위 테스트 55건 통과(5건 추가), `ruff check` / `ruff format --check` 통과.
- 합성 출력 파일로 기본값이 `.3`을 읽는지, `.2` 없이 동작하는지, `.3`이 없으면 에러가 나는지 확인했습니다.
- 프로젝트에 올라온 예전 실행 파일(`workspace/wec.2`, `wec.3`, 51개 주파수)을 비교했습니다.
  - ω = 2.4 rad/s 이하에서는 크기 차이가 약 1% 이내입니다(1.0 rad/s에서 0.1%).
  - ω 2.5 rad/s 이상부터 차이가 커져 3.0 rad/s에서는 `.3`이 0.293, `.2`가 0.097입니다.
  - 이 구간은 irregular frequency 영향으로 보이지만 원인은 확인하지 못했습니다. 해당 파일의 형상 조건도 알 수 없습니다.
  - 이 구간의 에너지는 대부분 작을 것으로 예상하지만, 파워에 미치는 영향은 계산하지 않았습니다.
- 실제 WAMIT 실행은 이 환경에서 불가능해 확인하지 못했습니다. 첫 실행에서 `wec.3`이 생성되는지 확인해 주세요.

## 5. 남은 이슈 / 후속 작업

- irregular frequency(IRR)는 메모리 문제로 당분간 적용하지 않기로 했습니다. 높은 주파수 구간의 `.2`/`.3` 차이가 그 영향이라면, 두 방식의 파워 차이를 실제 데이터로 비교해 볼 만합니다.
- 사전 점검(preflight)과 주파수 범위 설정은 이전 논의대로 보류입니다.
