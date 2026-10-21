# Changelog

이 프로젝트의 모든 주요 변경 사항을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르며, 각 항목의 자세한 내용은 `docs/reports/`의 보고서를 참고하세요.

## [Unreleased]

### 2026-10-21 — CI 워크플로를 python-tests.yml로 통합
보고서: [docs/reports/2026-10-21_05_ci-workflow.md](docs/reports/2026-10-21_05_ci-workflow.md)

#### Changed
- `.github/workflows/python-tests.yml`을 ruff lint 잡과 Python 3.8/3.12 전체 테스트(`unittest discover`) 매트릭스로 확장. 문서의 `ci.yml` 표기를 모두 `python-tests.yml`로 변경.

### 2026-10-21 — RAO 가진력을 diffraction(.3) 기준으로 변경
보고서: [docs/reports/2026-10-21_04_diffraction-excitation.md](docs/reports/2026-10-21_04_diffraction-excitation.md)

#### Changed
- RAO 계산의 파랑 가진력을 Haskind(`wec.2`)에서 diffraction(`wec.3`)으로 변경. `.frc` 출력 옵션 `1 1 0 …` → `1 0 1 …`.
- `calculate_rao_matrix(..., excitation="diffraction"|"haskind")`, `write_frc_file(..., excitation=...)`로 선택 가능 (기본 diffraction).

#### Added
- `tests/test_excitation.py` 5건.

### 2026-10-21 — 변수별 격자 간격, 영일만항 수심 수정, WAMIT 출력 정리
보고서: [docs/reports/2026-10-21_03_step-size-depth-wamit-output.md](docs/reports/2026-10-21_03_step-size-depth-wamit-output.md)

#### Added
- 설계 변수별 격자 간격 `{Var}Step` (`RadiusStep`, `DraftStep`, `WEC1_XStep`, `WEC2_XStep`, `WEC2_YStep`, `WEC3_XStep`, `WEC3_YStep`). 지정하지 않으면 `StepSize` 사용.
- `tests/test_step_size.py` 12건.

#### Fixed
- 영일만항(Yeongilmanhang) 수심 33 m → 13 m.
- 부동소수점 오차로 격자 상한이 탐색에서 빠지던 문제 (예: Y 0.1~30에서 30.0 누락).

#### Changed
- WAMIT `.frc` 출력 옵션 `1 1 1 …` → `1 1 0 …` (미사용 `.3` 출력 생략).

### 2026-10-21 — 설계 변수 양수 규칙 및 GitHub 구조 정비
보고서: [docs/reports/2026-10-21_02_positive-design-variables-and-github.md](docs/reports/2026-10-21_02_positive-design-variables-and-github.md)

#### Added
- `src/utils/validation.py`: 설계 변수 탐색 범위 `0 < Min < Max`, 형상·격자 파라미터 `> 0` 검증 (`ConfigValidationError`).
- `tests/test_validation.py`: 양수 규칙 테스트 10건.
- GitHub 구성: `.gitignore`, `.gitattributes`, `requirements-dev.txt`, `.github/workflows/python-tests.yml`, `CHANGELOG.md`, `CLAUDE.md`, `docs/reports/`.

#### Changed
- `config.cfg`: `WEC2_YMin`, `WEC3_YMin`을 0에서 0.1로 변경. 설계 변수 주석을 `[Float > 0]`로 표기.
- `get_layout_config`: Y 범위 키가 필수가 됨(기본값 0.0 제거). `NumWECs`는 1/3/5만 허용.
- `write_wamit_inputs`: 반지름·흘수가 양수가 아니면 거부.
- 문서: README, conventions(y_i > 0), architecture, algorithms_and_problems 갱신.

### 2026-10-21 — 버그·위험 항목 수정 및 ruff 도입
보고서: [docs/reports/2026-10-21_01_bugfix-and-ruff.md](docs/reports/2026-10-21_01_bugfix-and-ruff.md)

#### Fixed
- config 파서가 음수 값이 있는 줄을 무시하던 문제 (`src/utils/config_parser.py`).
- 로그가 재실행 시 덮어써지고 DE 로그에만 알고리즘 이름이 없던 문제.
- `main.py`가 최적해를 출력하지 않던 문제.
- PSO와 CMA-ES에서 대칭 정렬이 알고리즘 내부 상태를 뒤섞던 문제.
- 패널티 평가가 WAMIT 실행 수에 섞여 집계되던 문제.
- WAMIT 실패 시 원인 메시지가 숨겨지던 문제. 이전 실행의 출력과 에러 로그를 실행 전에 삭제.
- mesh 모듈이 Python 3.8에서 import되지 않던 문제.

#### Added
- 실행별 `*_config.json`, `*_summary.json` 로그 (중단 시에도 기록).
- `tests/test_fixes.py` 회귀 테스트 14건, `ruff.toml`.

#### Changed
- 전체 코드에 `ruff check` 및 `ruff format` 적용.
