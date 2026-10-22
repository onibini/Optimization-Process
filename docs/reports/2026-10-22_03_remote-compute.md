# 업데이트 보고서: 계산용 PC 원격 실행·결과 자동 회수

- 날짜: 2026-10-22
- 범위: `scripts/`(신규), `src/utils/run_summary.py`(신규), `tests/test_run_summary.py`(신규), `docs/remote_compute.md`(신규), `.gitignore`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`

## 1. 개요

폴더 전체를 복사해 계산용 PC에서 돌리고 결과를 다시 가져오던 수작업을, 개인용 PC의 명령 한 줄(`scripts\remote.ps1 submit`)로 대체했습니다. 두 PC는 서로 다른 네트워크이므로 Tailscale(VPN) 위에서 Windows 기본 OpenSSH를 씁니다. 결과는 실행마다 `results\<작업ID>\`에 모이고 `results\summary.csv`에 한 줄씩 요약됩니다.

## 2. 변경 내용

- `scripts/remote.ps1` (개인용 PC): `submit`(코드 스냅샷 tar → scp → 압축 해제 → 시작, `-Wait`이면 상태 폴링 후 자동 회수), `status`, `tail`, `fetch`, `stop`, `list`. 설정은 `scripts/remote.local.psd1`(git 제외, 예시는 `remote.example.psd1`).
- `scripts/remote/job_ctl.ps1` (계산용 PC에서 실행): 작업을 `Win32_Process.Create`로 SSH 세션 밖에서 시작하고 `status.json`(starting/running/done/failed/stopped, pid, 시각, 종료 코드)을 갱신. `tail`, `pack`(결과 zip), `stop`(`taskkill /T`로 WAMIT 포함 종료), `list`.
- 작업마다 `C:\wec_jobs\<작업ID>\`에서 실행하므로 `workspace/`가 작업 간에 겹치지 않습니다.
- `src/utils/run_summary.py`, `scripts/summarize_results.py`: `job.json`, `config.cfg`, `status.json`, `logs/*_summary.json`을 읽어 `summary.csv`를 생성(설정, 최적 파워 kW, 소요 분, WAMIT 평가 수, git 커밋 등).
- `.gitignore`에 `results/`, `scripts/remote.local.psd1` 추가. `docs/remote_compute.md`에 Tailscale/OpenSSH 설정과 사용법.

## 3. 호환성 영향

- `main.py`, `config.cfg`, 로그 형식, WAMIT 입력은 바뀌지 않았습니다 (물리 해석 영향 없음).
- 사용자가 해야 할 일: `docs/remote_compute.md`의 1회 설정(Tailscale, 계산용 PC의 OpenSSH 서버와 Python, SSH 키, `remote.local.psd1`).

## 4. 검증

- `ruff check .`, `ruff format --check .` 통과, 단위 테스트 101건(skip 3) 통과 (요약 테스트 3건 추가).
- `job_ctl.ps1`을 이 PC에서 직접 실행해 확인: 더미 `main.py`로 start → running → done, `tail`, `pack`(logs/run.log/status.json/config 포함), 긴 작업의 `stop`(상태 `stopped`, python 프로세스 남지 않음).
- **실제 두 PC 사이 검증 완료** (Tailscale + OpenSSH, 계산용 PC는 Windows Pro, conda 환경 `py311`, WAMIT `C:\WAMITv7`): `PopSize=4`, `MaxIter=2`의 `config_test.cfg`로 `submit -Wait`를 실행해 업로드, 압축 해제, 원격 시작, 상태 폴링, `scp` 회수, `summary.csv` 생성까지 한 번에 통과했습니다 (state done, 약 0.1분, WAMIT 10회, best 0.6581 kW). 결과 파일은 `results/20261022_102347_test/`.
- 설정 중 겪은 문제와 해결을 `docs/remote_compute.md`에 반영했습니다: PowerShell 실행 정책(`RemoteSigned`), SSH 세션에서 `python`이 안 잡혀 conda `python.exe` 전체 경로 지정, SSH 한 줄 명령의 공백 인자 따옴표 소실, `User`에 계정 이름만 쓸 것, 프로젝트 폴더에서 실행할 것.

## 5. 남은 이슈 / 후속 작업

- 짧은 시험만 검증했습니다. 수 시간짜리 긴 계산에서의 `-Wait` 폴링과 끊김 후 재접속은 아직 검증하지 않았습니다.
- 한 번에 여러 작업을 보내면 같은 CPU/RAM을 나눠 쓰므로 `NCPU`, `RAMGBMAX` 배분은 사용자가 정해야 합니다 (큐 기능은 없음).
- 재부팅/절전으로 중단된 작업은 `running`으로 남습니다 (자동 재개 없음).
