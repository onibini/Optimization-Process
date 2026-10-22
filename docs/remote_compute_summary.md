# 원격 계산 구축 정리 (2026-10-22)

계산용 PC에 계산을 보내고 결과를 자동으로 가져오는 환경을 구축한 과정과 현재 상태의 요약입니다. 설정 절차는 [remote_compute.md](remote_compute.md), 변경 상세는 [reports/2026-10-22_03_remote-compute.md](reports/2026-10-22_03_remote-compute.md)를 보세요.

## 1. 배경과 목표
- 기존: 개인용 PC에서 코드 수정 → 폴더 전체 복사 → 계산용 PC에서 실행 → 결과 다시 복사. 비효율적이고 결과 정리가 어려웠음.
- 목표: 개인용 PC에서 명령 한 줄로 계산을 보내고, 끝나면 결과를 자동으로 가져와 정리.
- 조건: 두 PC가 서로 다른 네트워크, 계산용 PC는 Windows Pro, WAMIT은 두 PC 모두 `C:\WAMITv7`.

## 2. 선택한 구조
```
개인용 PC (AMHL)                          계산용 PC (nwt, Windows Pro)
scripts\remote.ps1 ── Tailscale + SSH ──▶ C:\wec_jobs\<작업ID>\ 에서 main.py 실행
results\<작업ID>\  ◀──────── scp ────────  logs, run.log, status.json, config
```
- Tailscale(무료 개인 플랜)로 다른 네트워크의 두 PC를 연결, Windows 기본 OpenSSH로 접속.
- 작업마다 별도 폴더에서 실행하므로 `workspace/`가 겹치지 않음. SSH가 끊겨도 계산은 계속됨.

## 3. 만든 것
| 파일 | 역할 |
| --- | --- |
| `scripts/remote.ps1` | 개인용 PC용 명령: `submit` / `status` / `tail` / `fetch` / `stop` / `list` |
| `scripts/remote/job_ctl.ps1` | 계산용 PC에서 실행되는 작업 제어 (시작, 상태, 로그, 결과 묶기, 중지) |
| `scripts/remote.example.psd1` | 접속 설정 예시 (`remote.local.psd1`로 복사해 사용, git 제외) |
| `scripts/summarize_results.py`, `src/utils/run_summary.py` | `results/summary.csv` 생성 |
| `tests/test_run_summary.py` | 요약 기능 테스트 3건 |
| `docs/remote_compute.md` | 설정·사용 가이드 |
| `docs/reports/2026-10-22_03_remote-compute.md` | 기술 보고서 |
| `report/2026-10-22_02_멀리 있는 컴퓨터에서 계산시키기.md` | 쉬운 설명 리포트 |

## 4. 이번에 한 설정
1. 개인용 PC: `ssh-keygen -t ed25519`로 키 생성 (암호 없이).
2. 계산용 PC: OpenSSH 서버 실행 확인, 관리자 계정이라 `C:\ProgramData\ssh\administrators_authorized_keys`에 공개키 등록 + `icacls` 권한 정리.
3. 두 PC에 Tailscale 설치, 계산용 PC의 Tailscale IP로 `~/.ssh/config`에 `wec-compute` 별칭 등록.
4. `scripts/remote.local.psd1`의 `Python`을 conda 환경 `C:\Users\NWT\anaconda3\envs\py311\python.exe`로 지정.
5. 개인용 PC에서 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 5. 겪은 문제와 해결
| 문제 | 원인 | 해결 |
| --- | --- | --- |
| `.ssh\config` 추가 실패 | 계산용 PC에서 실행함 | 개인용 PC(AMHL)에서 실행 |
| SSH `User`가 안 맞음 | `PC이름\계정` 형식으로 씀 | 계정 이름만 (`nwt`) |
| `python --version`이 한글 오류문 | SSH 세션에서 `python`이 Store 별칭 | conda `python.exe` 전체 경로 지정 |
| `python -c "import numpy"` SyntaxError | SSH 한 줄에서 공백 든 인자의 따옴표 소실 (안내 명령이 잘못이었음) | 공백 없는 명령(`-m pip show`)으로 확인 |
| `running scripts is disabled` | PowerShell 실행 정책 | `RemoteSigned` (CurrentUser) |
| `Cannot find path scripts\...` | 프로젝트 폴더 밖에서 실행 | 프로젝트 폴더로 `cd` |
| `config_test.cfg` 없음 | 만들지 않고 실행 | `PopSize 4`, `MaxIter 2` 사본 생성 |

## 6. 검증 결과
- 로컬: `job_ctl.ps1`의 start / status / tail / pack / stop을 더미 작업으로 확인. `ruff check`, `ruff format --check`, 단위 테스트 101건(skip 3) 통과.
- 실제 두 PC 사이 짧은 시험 (`config_test.cfg`, 작업 ID `20261022_102347_test`): 업로드 → 원격 실행 → 상태 폴링 → 결과 회수 → `summary.csv` 생성까지 통과.

| 항목 | 값 |
| --- | --- |
| state | done (약 0.1분) |
| 설정 | 형상 최적화(OptMode 1), DE, WEC 1기, PopSize 4, MaxIter 2, MeshPanels 120 |
| WAMIT 실행 / 캐시 적중 | 10 / 2 |
| 최적 (시험값, 의미 없음) | 0.6581 kW, R=2.0, D=1.4 |

## 7. 사용법 요약
프로젝트 폴더에서 실행합니다.
```powershell
.\scripts\remote.ps1 submit -Name site3_de -Wait    # 보내고 기다렸다가 결과까지 가져옴
.\scripts\remote.ps1 submit -Config config_b.cfg -Name b   # 보내기만
.\scripts\remote.ps1 list | status | tail | fetch | stop
```
cmd에서는 `powershell -ExecutionPolicy Bypass -File scripts\remote.ps1 submit ...`. 결과는 `results\<작업ID>\`와 `results\summary.csv`.

## 8. 남은 일과 주의
- 긴 계산(수 시간)과 연결 끊김 후 재접속은 아직 시험하지 않았음.
- 동시에 여러 작업을 보내면 CPU/RAM을 나눠 쓰므로 `NCPU`, `RAMGBMAX`를 조정하거나 순서대로 보낼 것 (큐 기능 없음).
- 계산용 PC가 잠들면 계산이 멈추므로 절전을 끌 것.
- 결과 재현을 위해 본 계산 전에 변경을 커밋해 두면 `summary.csv`의 `git_dirty`가 `False`로 남음.
- 선택 확장: 더블클릭용 `.bat`, 여러 설정을 자동으로 순서대로 돌리는 큐, 종료 알림.
- 이 세션의 모든 변경은 아직 커밋되지 않았음.
