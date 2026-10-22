# 계산용 PC에서 실행되는 작업 제어 스크립트 (개인용 PC의 scripts/remote.ps1 이 SSH로 호출합니다).
# 직접 쓸 일은 거의 없습니다. Windows PowerShell 5.1 호환.
#
#   start   작업을 SSH 세션과 분리해서 시작 (SSH가 끊겨도 계속 실행)
#   run     (내부용) 실제로 main.py 를 돌리고 status.json 을 갱신
#   status  status.json 출력
#   tail    run.log 마지막 줄 출력
#   pack    결과(logs, run.log, status.json, config)를 result.zip 으로 묶기
#   stop    작업 강제 종료 (WAMIT 자식 프로세스 포함)
#   list    작업 폴더 목록
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("start", "run", "status", "tail", "pack", "stop", "list")]
    [string]$Action,
    [string]$JobDir,
    [string]$JobsRoot = "C:\wec_jobs",
    [string]$Python = "python",
    [string]$Config = "config.cfg",
    [int]$Lines = 30,
    [switch]$IncludeWorkspace
)

$ErrorActionPreference = "Stop"

function Write-Status($dir, $state, $extra) {
    $path = Join-Path $dir "status.json"
    $status = @{}
    if (Test-Path $path) {
        $old = Get-Content $path -Raw | ConvertFrom-Json
        foreach ($p in $old.PSObject.Properties) { $status[$p.Name] = $p.Value }
    }
    $status["state"] = $state
    foreach ($k in $extra.Keys) { $status[$k] = $extra[$k] }
    $status | ConvertTo-Json | Set-Content -Path $path -Encoding UTF8
}

switch ($Action) {
    "start" {
        $cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" run " +
        "-JobDir `"$JobDir`" -Python `"$Python`" -Config `"$Config`""
        Write-Status $JobDir "starting" @{ submitted = (Get-Date).ToString("s") }
        # Win32_Process.Create 로 띄운 프로세스는 SSH 세션의 작업 객체 밖이라 로그아웃 후에도 살아남습니다.
        $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
            -Arguments @{ CommandLine = $cmd; CurrentDirectory = $JobDir }
        if ($r.ReturnValue -ne 0) { throw "프로세스 시작 실패 (코드 $($r.ReturnValue))" }
        Write-Output "started pid=$($r.ProcessId)"
    }
    "run" {
        Set-Location $JobDir
        $env:PYTHONUNBUFFERED = "1"
        $env:PYTHONIOENCODING = "utf-8"
        Write-Status $JobDir "running" @{ pid = $PID; started = (Get-Date).ToString("s") }
        $code = 1
        try {
            & cmd.exe /c "`"$Python`" -u main.py `"$Config`" > run.log 2>&1"
            $code = $LASTEXITCODE
        }
        catch {
            $_ | Out-String | Add-Content -Path (Join-Path $JobDir "run.log")
        }
        $state = if ($code -eq 0) { "done" } else { "failed" }
        # stop 으로 이미 stopped 가 기록됐다면 덮어쓰지 않습니다.
        $cur = Get-Content (Join-Path $JobDir "status.json") -Raw | ConvertFrom-Json
        if ($cur.state -ne "stopped") {
            Write-Status $JobDir $state @{ exit_code = $code; finished = (Get-Date).ToString("s") }
        }
    }
    "status" {
        $path = Join-Path $JobDir "status.json"
        if (Test-Path $path) { Get-Content $path -Raw } else { Write-Output '{"state": "missing"}' }
    }
    "tail" {
        $log = Join-Path $JobDir "run.log"
        if (Test-Path $log) { Get-Content $log -Tail $Lines } else { Write-Output "(run.log 아직 없음)" }
    }
    "pack" {
        $zip = Join-Path $JobDir "result.zip"
        if (Test-Path $zip) { Remove-Item $zip -Force }
        Set-Location $JobDir
        $items = @("logs", "run.log", "status.json", $Config) | Where-Object { Test-Path $_ }
        if ($IncludeWorkspace -and (Test-Path "workspace")) { $items += "workspace" }
        & tar.exe -a -cf result.zip @items
        if ($LASTEXITCODE -ne 0) { throw "tar 실패 (코드 $LASTEXITCODE)" }
        Write-Output "packed $zip"
    }
    "stop" {
        $path = Join-Path $JobDir "status.json"
        $cur = Get-Content $path -Raw | ConvertFrom-Json
        if ($cur.state -eq "running" -and $cur.pid) {
            Write-Status $JobDir "stopped" @{ finished = (Get-Date).ToString("s") }
            & taskkill.exe /PID $cur.pid /T /F | Out-Null
            Write-Output "stopped pid=$($cur.pid)"
        }
        else {
            Write-Output "실행 중이 아닙니다 (state=$($cur.state))"
        }
    }
    "list" {
        if (Test-Path $JobsRoot) {
            Get-ChildItem $JobsRoot -Directory | Sort-Object Name | ForEach-Object {
                $s = Join-Path $_.FullName "status.json"
                $state = if (Test-Path $s) { (Get-Content $s -Raw | ConvertFrom-Json).state } else { "?" }
                "{0}`t{1}" -f $_.Name, $state
            }
        }
    }
}
