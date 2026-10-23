# 업데이트 보고서: 원격 계산에 `-Script` 옵션 추가

- 날짜: 2026-10-22
- 범위: `scripts/remote.ps1`, `scripts/remote/job_ctl.ps1`, `src/utils/run_summary.py`, `tests/test_run_summary.py`, `docs/remote_compute.md`, `docs/frequency_grid_design.md`, `README.md`, `CHANGELOG.md`, `report/`

## 1. 개요

`scripts/remote.ps1 submit`은 항상 `main.py <설정>`만 계산용 PC에서 실행했습니다. 주파수 격자 검증(`scripts/experiments/freq_grid_study.py`)처럼 연구용 스크립트를 보낼 수 있게 `-Script`/`-ScriptArgs`와, 계산용 PC에 연결하지 않고 스냅샷을 확인하는 `-DryRun`을 추가했습니다. 주파수 격자 설계안의 결정(새 격자 기본 끔, 작은 WEC의 상한 자동 확장은 선택 옵션, 판정 기준 0.1%/0.3%/+10%, `-Script` 승인)도 설계 문서에 기록했습니다. 계산용 PC에는 제출하지 않았습니다.

## 2. 변경 내용

- `remote.ps1`: `submit -Script <상대경로.py> -ScriptArgs "<인자>"`. 프로젝트 안의 `.py` 파일이고 스냅샷에 포함되는 폴더(`docs`, `report`, `tests`, `logs`, `workspace`, `results`, `.git`, `.github` 제외)에 있어야 하며 아니면 거부합니다. 스크립트와 인자는 SSH 명령줄 대신 스냅샷 안의 `_job.json`으로 전달합니다(공백이 든 인자의 따옴표가 SSH에서 깨지는 문제 회피). `job.json`에 `script`, `script_args`를 기록합니다. `-DryRun`은 스냅샷을 만들어 파일 수와 실행 명령, `_job.json`·`job_ctl.ps1` 포함 여부를 출력하고 끝냅니다.
- `job_ctl.ps1`: `run`이 작업 폴더의 `_job.json`에 스크립트가 있으면 `python -u <스크립트> <인자>`를, 없으면 이전처럼 `python -u main.py <설정>`을 실행합니다. `status.json`에 `script`를 기록하고 `pack`이 `_job.json`도 묶습니다.
- `run_summary.py`: `summary.csv`에 `script` 칸(스크립트와 인자)을 추가했습니다. 스크립트 작업은 최적화 결과 칸이 비어 있습니다.
- `docs/remote_compute.md` 2-1절, README 사용 예, 설계 문서 7절(결정 사항과 상태)을 갱신했습니다.

## 3. 호환성 영향

- `-Script`를 쓰지 않으면 동작은 이전과 같습니다(`main.py <설정>`, 같은 `status.json`/`result.zip` 구성에 `_job.json`만 없음).
- `summary.csv`에 `script` 칸이 `job_id` 다음에 추가되어 열 순서가 바뀝니다. `summarize_results.py`가 매번 다시 만들므로 기존 `results/summary.csv`는 다음 `fetch` 때 새 형식으로 바뀝니다.
- 계산용 PC의 `C:\wec_jobs\_ctl\job_ctl.ps1`은 다음 `submit`에서 새 버전으로 자동 교체됩니다.

## 4. 검증

- 이 PC에서 계산용 PC나 WAMIT 없이 확인했습니다.
  - `submit -Script ... -DryRun`: 스냅샷 57개 파일, `_job.json`·`job_ctl.ps1` 포함, 실행 명령 `python -u scripts/experiments/freq_grid_study.py --study grids --quick`. `-Script` 없이: 56개, `python -u main.py config.cfg`.
  - 거부 검사: 없는 파일, `tests/` 안 파일, `.py`가 아닌 파일, 프로젝트 밖 경로, `docs/` 경로 모두 오류로 종료(종료 코드 1). `-DryRun`은 `results\.last_job`을 바꾸지 않음.
  - `job_ctl.ps1`을 더미 작업으로 실행: 스크립트 작업은 `state=done`, `script=scripts/dummy.py`, `run.log`에 `['--study', 'grids', '--quick']`가 찍혔고 `result.zip`에 `logs/study.csv`, `_job.json`이 포함. `_job.json`이 없는 작업은 `main.py config.cfg`를 실행하고 `_job.json` 없이 묶임.
- 요약 테스트 2건 추가(스크립트 작업의 `script` 칸, 일반 작업의 빈 칸). `ruff check .`, `ruff format --check .`, 단위 테스트 통과(건수는 최종 확인 참조).
- 실제 SSH 경로(업로드·시작·회수)는 이번에 시험하지 않았습니다. 기존 보고서 03에서 `main.py` 작업으로 검증된 경로를 그대로 쓰고 `_job.json`만 스냅샷에 추가됩니다.

## 5. 남은 이슈 / 후속 작업

- 사용자의 확인 후 계산용 PC에 `grids --quick` 검증을 제출하고, 결과로 구간 비율과 판정 기준을 확인한 뒤 주파수 격자 구현(설계 5절).
- `-Script`를 처음 실제로 보낼 때(`submit` 한 번) 계산용 PC에서 `_job.json` 경로가 정상 동작하는지는 그 실행에서 확인됩니다.
