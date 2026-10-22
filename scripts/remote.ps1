# 개인용 PC에서 계산용 PC로 최적화를 보내고, 진행을 보고, 결과를 가져옵니다 (SSH 사용).
# 처음 설정은 docs/remote_compute.md 를 보세요. 설정 파일: scripts/remote.local.psd1
#
#   .\scripts\remote.ps1 submit [-Config config.cfg] [-Name 이름] [-Wait]
#   .\scripts\remote.ps1 status [-JobId ID]     # 생략하면 마지막 작업
#   .\scripts\remote.ps1 tail   [-JobId ID] [-Lines 30]
#   .\scripts\remote.ps1 fetch  [-JobId ID] [-IncludeWorkspace]
#   .\scripts\remote.ps1 stop   [-JobId ID]
#   .\scripts\remote.ps1 list
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("submit", "status", "tail", "fetch", "stop", "list")]
    [string]$Action,
    [string]$JobId,
    [string]$Config = "config.cfg",
    [string]$Name = "run",
    [int]$Lines = 30,
    [switch]$Wait,
    [switch]$IncludeWorkspace
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ResultsDir = Join-Path $ProjectRoot "results"
$LastJobFile = Join-Path $ResultsDir ".last_job"

$settingsPath = Join-Path $PSScriptRoot "remote.local.psd1"
if (-not (Test-Path $settingsPath)) {
    throw "scripts\remote.example.psd1 을 scripts\remote.local.psd1 로 복사하고 값을 채우세요."
}
$S = Import-PowerShellDataFile $settingsPath
$RemoteHost = $S.Host
$JobsRoot = if ($S.JobsRoot) { $S.JobsRoot } else { "C:\wec_jobs" }
$Python = if ($S.Python) { $S.Python } else { "python" }
$PollSeconds = if ($S.PollSeconds) { [int]$S.PollSeconds } else { 60 }
$SshOpts = @("-o", "BatchMode=yes", "-o", "ServerAliveInterval=30")
$RemoteCtl = "$JobsRoot\_ctl\job_ctl.ps1"

function Invoke-Ssh {
    # 원격 명령을 실행하고 출력을 반환합니다. 실패하면 예외를 던집니다.
    $out = & ssh @SshOpts $RemoteHost @args
    if ($LASTEXITCODE -ne 0) { throw "ssh 실패 (코드 $LASTEXITCODE): $args" }
    $out
}

function Invoke-Ctl([string]$ctlAction, [string[]]$more) {
    Invoke-Ssh powershell -NoProfile -ExecutionPolicy Bypass -File $RemoteCtl $ctlAction @more
}

function Resolve-JobId {
    if ($JobId) { return $JobId }
    if (Test-Path $LastJobFile) { return (Get-Content $LastJobFile -Raw).Trim() }
    throw "-JobId 를 지정하세요 (마지막 작업 기록이 없습니다)."
}

function Get-State([string]$id) {
    $json = (Invoke-Ctl "status" @("-JobDir", "$JobsRoot\$id")) -join "`n"
    ($json | ConvertFrom-Json).state
}

function Receive-Result([string]$id) {
    $dest = Join-Path $ResultsDir $id
    New-Item -ItemType Directory -Force $dest | Out-Null
    $more = @("-JobDir", "$JobsRoot\$id")
    if ($IncludeWorkspace) { $more += "-IncludeWorkspace" }
    Invoke-Ctl "pack" $more | Out-Null
    $zip = Join-Path $dest "result.zip"
    & scp @SshOpts "${RemoteHost}:$($JobsRoot -replace '\\','/')/$id/result.zip" $zip
    if ($LASTEXITCODE -ne 0) { throw "scp 실패" }
    & tar.exe -xf $zip -C $dest
    Remove-Item $zip
    Write-Host "결과를 가져왔습니다: $dest"
    $py = (Get-Command python -ErrorAction SilentlyContinue)
    if ($py) {
        & python (Join-Path $PSScriptRoot "summarize_results.py") $ResultsDir
    }
}

switch ($Action) {
    "submit" {
        $cfgPath = Resolve-Path (Join-Path $ProjectRoot $Config) -ErrorAction SilentlyContinue
        if (-not $cfgPath) { $cfgPath = Resolve-Path $Config }
        $safeName = $Name -replace "[^A-Za-z0-9_-]", "_"
        $id = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), $safeName

        # 1. 코드 스냅샷 (실행 산출물과 개발용 폴더는 제외)
        $stage = Join-Path ([IO.Path]::GetTempPath()) "wec_stage_$id"
        robocopy $ProjectRoot $stage /E /NFL /NDL /NJH /NJS /NP `
            /XD .git .github logs workspace results docs report tests __pycache__ .venv venv .ruff_cache .pytest_cache `
            | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy 실패 (코드 $LASTEXITCODE)" }
        Copy-Item $cfgPath (Join-Path $stage "config.cfg") -Force
        $zip = Join-Path ([IO.Path]::GetTempPath()) "$id.zip"
        & tar.exe -a -cf $zip -C $stage .
        if ($LASTEXITCODE -ne 0) { throw "tar 실패" }
        Remove-Item $stage -Recurse -Force

        # 2. 업로드 및 풀기, 제어 스크립트 설치
        $rootFwd = $JobsRoot -replace "\\", "/"
        Invoke-Ssh "if not exist $JobsRoot\_ctl mkdir $JobsRoot\_ctl" | Out-Null
        & scp @SshOpts $zip "${RemoteHost}:$rootFwd/$id.zip"
        if ($LASTEXITCODE -ne 0) { throw "scp 업로드 실패" }
        Invoke-Ssh "mkdir $JobsRoot\$id && tar -xf $JobsRoot\$id.zip -C $JobsRoot\$id && del $JobsRoot\$id.zip" | Out-Null
        Invoke-Ssh "copy /Y $JobsRoot\$id\scripts\remote\job_ctl.ps1 $RemoteCtl" | Out-Null
        Remove-Item $zip

        # 3. 시작
        Invoke-Ctl "start" @("-JobDir", "$JobsRoot\$id", "-JobsRoot", $JobsRoot, "-Python", $Python, "-Config", "config.cfg") | Write-Host

        # 4. 로컬 기록 (어떤 설정/코드로 보냈는지)
        $dest = Join-Path $ResultsDir $id
        New-Item -ItemType Directory -Force $dest | Out-Null
        Copy-Item $cfgPath (Join-Path $dest "config.cfg")
        $commit = (& git -C $ProjectRoot rev-parse --short HEAD 2>$null)
        $dirty = (& git -C $ProjectRoot status --porcelain 2>$null)
        @{ job_id = $id; name = $safeName; host = $RemoteHost; submitted = (Get-Date).ToString("s");
            git_commit = "$commit"; git_dirty = [bool]$dirty } | ConvertTo-Json | Set-Content (Join-Path $dest "job.json") -Encoding UTF8
        Set-Content $LastJobFile $id -Encoding ASCII
        Write-Host "작업 ID: $id"

        if ($Wait) {
            while ($true) {
                Start-Sleep -Seconds $PollSeconds
                try { $state = Get-State $id } catch { Write-Warning "연결 실패, 재시도: $_"; continue }
                Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $state)
                if ($state -in @("done", "failed", "stopped")) { break }
            }
            $JobId = $id
            Receive-Result $id
        }
        else {
            Write-Host "나중에: .\scripts\remote.ps1 status / tail / fetch"
        }
    }
    "status" { $id = Resolve-JobId; Invoke-Ctl "status" @("-JobDir", "$JobsRoot\$id") }
    "tail" { $id = Resolve-JobId; Invoke-Ctl "tail" @("-JobDir", "$JobsRoot\$id", "-Lines", "$Lines") }
    "fetch" { $id = Resolve-JobId; Receive-Result $id }
    "stop" { $id = Resolve-JobId; Invoke-Ctl "stop" @("-JobDir", "$JobsRoot\$id") }
    "list" { Invoke-Ctl "list" @("-JobsRoot", $JobsRoot) }
}
