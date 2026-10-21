# 업데이트 보고서: GitHub 공개 준비 보강

- 날짜: 2026-10-21
- 범위: `config.cfg`, `main.py`, `src/physics/wamit_handler.py`, `src/problems/*`, `tests/test_wamit_path.py`(신규), `README.md`, `CONTRIBUTING.md`(신규), `.github/` 템플릿(신규), `docs/architecture.md`, `CLAUDE.md`

## 1. WAMIT 경로 설정화

코드에 `C:\WAMITv7\WAMIT.exe`가 고정되어 있던 것을 설정으로 뺐습니다. 우선순위는 `config.cfg`의 `WAMITPath` > 환경 변수 `WAMIT_EXE` > 기본 경로입니다. config 값은 공백 없는 한 토큰이라 공백이 있는 경로는 환경 변수를 쓰도록 `config.cfg`와 README에 안내했습니다. `resolve_wamit_exe`와 테스트 4건(`tests/test_wamit_path.py`)을 추가했고, 세 문제 모듈의 `run_wamit` 호출이 `config["wamit_exe"]`를 넘깁니다. `WAMITPath`를 쓰지 않으면 기존과 동작이 같습니다.

## 2. 공개 저장소 문서

- README Prerequisites에 WAMIT이 상용이며 저장소에 포함되지 않고 별도 라이선스가 필요하다는 점, Windows 전용 평가, WAMIT 없이 가능한 작업(테스트, lint)을 명시했습니다. 구조도에 `CONTRIBUTING.md`와 `.github/` 구성을 반영했습니다.
- `CONTRIBUTING.md`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/`(bug_report, feature_request, config)를 추가했습니다.
- `CLAUDE.md`와 `docs/architecture.md`의 구조도를 맞췄습니다.

## 3. 하지 않은 것

`pyproject.toml`은 이 저장소가 설치 가능한 패키지가 아니라 스크립트 모음이고 설정이 `ruff.toml`에 이미 있어 추가하지 않았습니다.

## 4. 검증

py311에서 `ruff check .`, `ruff format --check .`, 단위 테스트 59건(skip 3) 통과.
