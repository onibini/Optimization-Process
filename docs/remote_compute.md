# 계산용 PC 원격 실행 가이드

개인용 PC(코드 작성)에서 명령 한 줄로 계산용 PC에 최적화를 보내고, 끝나면 결과를 자동으로 가져옵니다. 두 PC가 서로 다른 네트워크에 있어도 Tailscale(무료 VPN)로 같은 가상 네트워크에 묶어 SSH로 접속합니다.

```
개인용 PC                                   계산용 PC (Windows Pro)
scripts\remote.ps1 submit  ── SSH/Tailscale ──▶  C:\wec_jobs\<작업ID>\  (코드 스냅샷, main.py 실행)
results\<작업ID>\  ◀── scp ──  logs, run.log, status.json, config.cfg
```

- 작업마다 별도 폴더(`C:\wec_jobs\<작업ID>`)에서 실행하므로 `workspace/`가 겹치지 않고 코드를 고쳐도 실행 중인 작업에 영향이 없습니다.
- SSH가 끊기거나 개인용 PC를 꺼도 계산은 계속됩니다 (`Win32_Process.Create`로 SSH 세션 밖에서 시작).
- WAMIT은 계산용 PC에 설치된 것(`C:\WAMITv7`)을 씁니다. 개인용 PC에서 `WAMITPath`/`WAMIT_EXE` 설정이 있으면 계산용 PC 경로와 같아야 합니다.

## 1. 한 번만 설정

### 1-1. 두 PC에 Tailscale 설치 (다른 네트워크 연결)
1. <https://tailscale.com/download> 에서 두 PC 모두 설치하고 **같은 계정**으로 로그인합니다.
2. 계산용 PC의 Tailscale IP(`100.x.y.z`)나 기기 이름을 확인합니다 (`tailscale ip -4`). 이후 공유기 설정(포트포워딩) 없이 이 주소로 접속됩니다.

### 1-2. 계산용 PC: OpenSSH 서버 + Python
관리자 PowerShell에서:
```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic
Start-Service sshd
```
- Python 3.10+ 와 `pip install -r requirements.txt` 가 설치되어 있어야 합니다 (`python --version`을 SSH 안에서도 확인).
- **절전/최대 절전 끄기**: 설정 → 시스템 → 전원에서 전원 연결 시 절전 "안 함". 계산 중 잠자면 작업이 멈춥니다.
- 방화벽은 Tailscale 네트워크에서만 열어두는 것을 권장합니다 (공용 인터넷에 22번 포트를 열지 마세요).

### 1-3. 개인용 PC: SSH 키로 비밀번호 없이 접속
```powershell
ssh-keygen -t ed25519            # 이미 있으면 생략
type $env:USERPROFILE\.ssh\id_ed25519.pub   # 이 한 줄을 복사
```
계산용 PC에 공개키 등록:
- 계산용 PC 로그인 계정이 **일반 사용자**: `C:\Users\<계정>\.ssh\authorized_keys` 파일에 한 줄 추가.
- 계정이 **관리자 그룹**(보통 이쪽): `C:\ProgramData\ssh\administrators_authorized_keys` 에 추가하고 관리자 PowerShell에서 권한 정리:
  ```powershell
  icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
  ```

`C:\Users\<개인용 계정>\.ssh\config` 에 별칭을 만듭니다:
```
Host wec-compute
    HostName 100.x.y.z
    User <계산용 PC 계정>
    IdentityFile ~/.ssh/id_ed25519
```
`ssh wec-compute hostname` 이 비밀번호 없이 계산용 PC 이름을 출력하면 성공입니다.

### 1-4. 설정 파일
```powershell
Copy-Item scripts\remote.example.psd1 scripts\remote.local.psd1
```
`Host`(위 별칭), `JobsRoot`, `Python`을 확인합니다. `remote.local.psd1`은 git에 올라가지 않습니다.

- `Host`: 위 SSH 별칭. 별칭의 `User`에는 `PC이름\계정`이 아니라 **계정 이름만** 씁니다.
- `Python`: conda 환경이면 그 안의 `python.exe` 전체 경로 (예: `C:\Users\NWT\anaconda3\envs\py311\python.exe`). SSH 세션의 PATH에는 Store 별칭만 잡혀 `python`이 동작하지 않는 경우가 많습니다.
- `JobsRoot`와 경로에는 **공백을 넣지 마세요** (SSH 명령 인용 문제).

### 1-5. PowerShell 실행 정책 (개인용 PC, 한 번만)
`이 시스템에서 스크립트를 실행할 수 없으므로` 오류가 나면:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 1-6. 접속 확인
`scripts\...` 상대 경로 명령은 모두 **프로젝트 폴더에서** 실행해야 합니다.
```powershell
ssh wec-compute hostname
ssh wec-compute dir C:\WAMITv7\WAMIT.exe
ssh wec-compute C:\Users\NWT\anaconda3\envs\py311\python.exe -m pip show numpy scipy
```
SSH 한 줄로 `python -c "import numpy"`처럼 **공백이 든 인자**를 넘기면 따옴표가 사라져 오류가 납니다. 이 가이드의 확인 명령은 공백이 없는 형태만 씁니다.

### 1-7. 첫 시험 (짧은 계산)
`config.cfg`를 복사해 `PopSize`를 4, `MaxIter`를 2로 줄인 `config_test.cfg`를 만들고:
```powershell
.\scripts\remote.ps1 submit -Config config_test.cfg -Name test -Wait
```
`결과를 가져왔습니다`가 출력되고 `results\summary.csv`에 한 줄이 생기면 설정이 끝난 것입니다.

## 2. 사용법

```powershell
.\scripts\remote.ps1 submit -Name site3 -Wait   # 보내고, 끝날 때까지 기다리고, 결과까지 가져옴
.\scripts\remote.ps1 submit -Config config_b.cfg -Name caseB   # 기다리지 않고 보내기만
.\scripts\remote.ps1 list                        # 계산용 PC의 작업과 상태
.\scripts\remote.ps1 status [-JobId ID]          # 생략하면 마지막 작업
.\scripts\remote.ps1 tail   [-JobId ID] -Lines 40
.\scripts\remote.ps1 fetch  [-JobId ID]          # 중간/완료 결과 가져오기 (-IncludeWorkspace: WAMIT 파일 포함)
.\scripts\remote.ps1 stop   [-JobId ID]          # 강제 종료 (WAMIT 포함)
python scripts\summarize_results.py              # results\summary.csv 다시 만들기 (fetch 때 자동 실행)
```

- 작업 ID는 `YYYYMMDD_HHMMSS_<이름>` 입니다. `-Config`로 다른 설정 파일을 주면 그 파일이 계산용 PC에서 `config.cfg`로 쓰입니다.
- `submit`은 `logs/ workspace/ results/ docs/ report/ tests/ .git`을 제외한 코드 스냅샷을 보냅니다.
- 상태 값: `starting` → `running` → `done` / `failed` / `stopped`.

### 2-1. `main.py` 대신 다른 스크립트 실행 (`-Script`)

WAMIT 검증 같은 연구용 스크립트를 계산용 PC에서 돌릴 때 씁니다. 프로젝트 안의 `.py` 파일을 프로젝트 폴더 기준 상대 경로로 주고, 인자는 `-ScriptArgs`에 한 문자열로 줍니다.

```powershell
.\scripts\remote.ps1 submit -Name fgrid_quick -Script scripts/experiments/freq_grid_study.py -ScriptArgs "--study grids --quick" -Wait
.\scripts\remote.ps1 submit ... -DryRun    # 계산용 PC에 연결하지 않고 스냅샷만 만들어 내용(_job.json, 파일 수)을 확인
```

- 스크립트는 작업 폴더(`C:\wec_jobs\<작업ID>`)에서 `python -u <스크립트> <인자>`로 실행되고, `-Config` 파일은 그대로 `config.cfg`로 올라가 스크립트가 읽을 수 있습니다(`main.py`는 실행되지 않습니다).
- 스크립트와 인자는 따옴표가 SSH 명령줄에서 깨지지 않도록 스냅샷 안의 `_job.json`으로 전달됩니다. 결과는 `logs/` 아래에 쓰면 기존 `fetch`가 가져오고, `summary.csv`의 `script` 칸에 스크립트와 인자가 적힙니다.
- `docs/ report/ tests/ logs/ workspace/ results/ .git/ .github/` 안의 파일, `.py`가 아닌 파일, 프로젝트 밖의 파일은 거부됩니다.

## 3. 결과 구조

```
results\
├── summary.csv                      # 실행당 한 줄 (설정, 최적 파워, 시간, git 커밋 ...)
└── 20261022_100000_site3\
    ├── job.json                     # 보낸 시각, 이름, git 커밋/수정 여부
    ├── config.cfg                   # 실제로 쓴 설정
    ├── status.json                  # 상태, 시작/종료 시각, 종료 코드
    ├── run.log                      # 콘솔 출력 전체
    └── logs\                        # *_trial_history.csv, *_generation_history.csv, *_summary.json ...
```

## 4. 문제 해결

| 증상 | 확인 |
| --- | --- |
| `ssh 실패` | `ssh wec-compute hostname` 직접 실행. Tailscale 연결(양쪽 `tailscale status`), `sshd` 서비스 실행 여부 |
| 비밀번호를 물어봄 | 공개키 등록 위치(일반/관리자 계정 구분)와 `administrators_authorized_keys` 권한 |
| 상태가 `failed` | `remote.ps1 tail -Lines 80` 또는 가져온 `run.log`. 계산용 PC에 Python 패키지/WAMIT 경로 확인 |
| `python`을 못 찾음 / 한글 오류문 | `remote.local.psd1`의 `Python`에 전체 경로 지정 (conda 환경 `python.exe` 등) |
| `running scripts is disabled` | 1-5의 `Set-ExecutionPolicy` |
| `Cannot find path ...scripts\...` | 프로젝트 폴더로 `cd` 한 뒤 실행 |
| 재부팅 후 작업이 `running`으로 남음 | 계산용 PC가 재부팅/절전으로 중단된 것. `fetch`로 중간 로그를 받고 다시 `submit` |
