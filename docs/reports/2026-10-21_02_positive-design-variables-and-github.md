# 업데이트 보고서: 설계 변수 양수 규칙 및 GitHub 구조 정비

- 날짜: 2026-10-21
- 범위: `src/utils/validation.py`(신규), `src/problems/*`, `src/physics/wamit_handler.py`, `config.cfg`, `tests/test_validation.py`(신규), GitHub 관련 파일, 문서

## 1. 개요

1. **설계 변수 양수 규칙**: 모든 설계 변수(반지름 R, 흘수 D, WEC 좌표 x/y)는 양수(> 0)만 허용합니다. 설정이 이 규칙을 어기면 최적화 시작 전에 중단하고, 어떤 변수가 문제인지 알려줍니다.
2. **GitHub 구조 정비**: 공개 저장소에 맞게 `.gitignore`, CI, CHANGELOG, 작업 규칙 문서를 추가했습니다.

## 2. 변경 내용

### 2.1 설계 변수 양수 검증
- `src/utils/validation.py` (신규)
  - `validate_design_bounds(names, lower, upper)`: 모든 변수에 대해 `0 < Min < Max`를 확인합니다. 위반한 변수를 한 번에 모두 나열하는 `ConfigValidationError`를 냅니다.
  - `require_positive(name, value)`: 값이 0보다 큰지 확인합니다. 숫자가 아니거나 NaN/inf여도 에러입니다.
- 문제 설정 생성 시 검증합니다.
  - `get_shape_config`: Radius, Draft 범위와 StepSize를 검증합니다.
  - `get_layout_config`: 선택한 NumWECs에서 실제로 쓰는 WEC 좌표 범위만 검증합니다(3기면 WEC3은 검사하지 않음). FixedRadius, FixedDraft, MinSpacing, StepSize도 검증합니다.
  - `get_joint_config`: 위 두 함수의 검증을 그대로 거칩니다.
  - 이전에는 `WEC2_YMin` 등이 없으면 0.0을 기본값으로 썼습니다. 이제 필수 키입니다(조용한 기본값 제거).
  - `NumWECs`가 1/3/5가 아니면 에러입니다.
- 실행 중 보장
  - 격자 스냅 시 모든 후보가 [Min, Max]로 클리핑되므로, 하한이 양수면 평가되는 모든 벡터가 양수입니다.
  - 마지막 안전장치로 `write_wamit_inputs`가 R ≤ 0 또는 D ≤ 0을 거부합니다.
- `config.cfg`
  - `WEC2_YMin`, `WEC3_YMin`을 `0`에서 `0.1`(격자 한 칸)로 바꿨습니다. 기존 값 0은 새 규칙에 어긋납니다.
  - 설계 변수와 형상·격자 파라미터 주석을 `[Float > 0]`로 표기하고, `[Constraints]` 섹션에 규칙 설명을 추가했습니다.
  - WEC3_X 주석의 사용 조건 오기를 바로잡았습니다("NumWECs is 3 or 5" → "5").

### 2.2 GitHub 구조

| 파일 | 내용 |
|---|---|
| `.gitignore` | `__pycache__/`, 가상환경, IDE, `logs/`, `workspace/` 제외 |
| `.gitattributes` | 저장소 줄바꿈 LF 통일(Windows 체크아웃 시 자동 변환), `*.p2f` 바이너리 |
| `requirements-dev.txt` | 런타임 의존성 + `ruff==0.16.9` |
| `.github/workflows/python-tests.yml` | push/PR마다 ruff check, ruff format --check, unittest 실행(Python 3.8, 3.12) |
| `CHANGELOG.md` | Keep a Changelog 형식, 보고서 링크 |
| `CLAUDE.md` | AI 어시스턴트 작업 규칙(직접 반영, GitHub 구조, 보고서 필수, 양수 규칙) |
| `docs/reports/` | 업데이트별 보고서(이 문서 포함) |
| `LICENSE` | 기존 MIT 라이선스 유지 |

### 2.3 문서
- `README.md`: 디렉토리 구조, 양수 규칙, 개발/CI, 라이선스 섹션을 갱신했습니다.
- `docs/conventions.md`: "0. Positivity Rule"을 추가하고, y_i ≥ 0을 y_i > 0으로 바꿨습니다.
- `docs/architecture.md`, `docs/algorithms_and_problems.md`: validation 모듈과 양수 규칙을 반영했습니다.

## 3. 호환성 영향

- **설정 파일**: 설계 변수 하한이 0 이하인 기존 config는 이제 시작 시 에러가 납니다. 프로젝트의 `config.cfg`는 이미 고쳐 두었습니다(Y 하한 0 → 0.1).
- **탐색 공간 변화**: y 하한이 0에서 0.1로 바뀌었습니다. 다만 y=0은 사이드 WEC가 자기 대칭 짝과 겹치는 점이라, 원래도 간격 제약 때문에 패널티를 받던 영역입니다. 실현 가능한 해의 집합은 사실상 바뀌지 않습니다.
- **`logs/`, `workspace/`가 Git에서 제외**됩니다. 실험 결과를 저장소에 남기려면 별도 폴더(예: `results/`)로 옮겨 커밋하세요.
- API 변경은 없습니다.

## 4. 검증

- 단위 테스트는 28개에서 38개로 늘었고 모두 통과합니다. 추가된 `tests/test_validation.py`:
  - 프로젝트 config가 모든 모드(1/2/3)와 기기 수(1/3/5)에서 검증을 통과하는지
  - R, D, x, y 하한이 0이거나 음수일 때, 상한 ≤ 하한일 때 에러가 나는지
  - FixedRadius, FixedDraft, MinSpacing, StepSize가 0일 때 에러가 나는지
  - 쓰지 않는 WEC3 범위는 3기 배치에서 검사하지 않는지
  - 숫자가 아니거나 NaN/inf일 때 에러가 나는지
  - 하한 쪽으로 끌어당기는 목적함수로 네 알고리즘을 돌렸을 때, 평가된 모든 벡터가 양수인지
- `ruff check .`, `ruff format --check .` 모두 통과했습니다.
- CI 설정 YAML 문법을 확인했습니다.
- 한계: 이 환경에서는 Python 3.8을 실제로 설치하지 못해 3.8 실행은 확인하지 못했습니다. ruff의 py38 문법 검사는 통과했고, 3.8 실행 확인은 GitHub Actions에서 이뤄집니다.

## 5. 남은 이슈 / 후속 작업

- 2026-10-21_01 보고서의 남은 이슈(벽 조건 의도, 벽 이격 제약, 경계 해, 메시 수렴성)는 그대로입니다.
- GitHub에 올린 뒤 첫 CI 결과를 확인해야 합니다(특히 Python 3.8 + gmsh 설치).
- README에 CI 배지를 달려면 저장소 URL이 필요합니다.
