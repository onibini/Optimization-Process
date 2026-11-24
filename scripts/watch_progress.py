"""Show what every compute PC is calculating right now: site, seed, method, generation and particle.

Every compute PC with a ``scripts/remote*.local.psd1`` file gets one status line at the bottom of the terminal, which is
updated about a second after a result is written. Finished generations and started or finished runs are added above the
status lines and stay on the screen, so the record builds up. Nothing else is shown unless it is asked for.

    python scripts/watch_progress.py                 # status lines and events from now on
    python scripts/watch_progress.py --once          # print the status once and exit
    python scripts/watch_progress.py --history       # also show the events of the job so far
    python scripts/watch_progress.py --verbose       # every log line and every evaluation
    python scripts/watch_progress.py --local LOCAL=logs/convergence_study.csv

``particle`` counts the designs newly evaluated in the generation, including those rejected by the spacing rule. Designs
reused from memory are not counted, so the number can stay below the population size late in a run.
``--local LABEL=PATH`` also follows a text file on this PC. A lost connection is retried and continues where it stopped.
Stop with Ctrl+C; this ends the watching only, the jobs keep running. Nothing is written on any PC.
"""

import argparse
import base64
import glob
import os
import re
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RETRY_SECONDS = 5
AGENT_SECONDS = 60  # 끊겨서 남은 감시 루프도 이 시간 안에 사라집니다
POLL_SECONDS = 1
ONCE_TIMEOUT_SECONDS = 60
SSH_OPTIONS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "LogLevel=ERROR",
    "-o",
    "ServerAliveInterval=30",
    "-o",
    "ServerAliveCountMax=3",
]
COMMAND_LIMIT = 8000  # 계산용 PC의 SSH 기본 셸(cmd.exe) 명령 길이 한도 8191자보다 조금 작게
METHODS = {
    "Geometry Optimization": "geometry",
    "Layout Optimization": "layout",
    "Geometry and Layout Optimization": "simultaneous",
}
GENERATION_LINE = re.compile(
    r"^Gen\s+(\d+)/(\d+)\s.*\s(\d+)/(\d+)\s*\|\s*Best\s+([-\d.]+) kW.*WAMIT\s+(\d+).*Penalty\s+(\d+)"
)
INIT_LINE = re.compile(r"^Init\s.*Best\s+([-\d.]+) kW")
PROBLEM_LINE = re.compile(r"Traceback|^\w*Error\b|failed \(site")

# 계산용 PC에서 도는 작은 감시 루프입니다. 파일은 읽기만 합니다. 출력 줄의 앞 글자로 종류를 나눕니다:
# J 작업 ID, L run.log 줄, P run.log 위치, H 평가 파일과 머리글, T 평가 줄, Q 평가 파일 위치, S 작업 상태
# E 정상 종료. Windows에서는 SSH가 끊겨도 쓰기 오류가 나지 않고 표준 입력도 닫히지 않아, 루프가 끊김을 알 수
# 없습니다. 그래서 루프는 ``AGENT_SECONDS``마다 스스로 끝나고 개인 PC가 같은 위치부터 바로 다시 잇습니다.
AGENT = r"""
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$root='@ROOT@';$j='@JOB@';$p=@LOG@;$f='@FILE@';$q=@TRIAL@;$o=[Console]::Out
function N($x,$s){$h=[IO.File]::Open($x,'Open','Read','ReadWrite,Delete');try{if($s -lt 0){$s=$h.Length}
$n=[int]($h.Length-$s);if($n -le 0){return @('',$s)};[void]$h.Seek($s,'Begin');$b=New-Object byte[] $n
$c=$h.Read($b,0,$n)}finally{$h.Close()};if($c -le 0){return @('',$s)};$e=[Array]::LastIndexOf($b,[byte]10,$c-1)
if($e -lt 0){return @('',$s)};@([Text.Encoding]::UTF8.GetString($b,0,$e+1),($s+$e+1))}
$i=0;$w=''
while($i -lt @SECONDS@){$g=Get-ChildItem $root -Directory|Where-Object{$_.Name -ne '_ctl'}|Sort-Object Name|Select-Object -Last 1
if($g -and $g.Name -ne $j){if($j){$p=0};$j=$g.Name;$f='';$w=''}
if($j){$d="$root\$j";$l="$d\run.log";if($w -ne $j){$o.WriteLine("J|$j");$w=$j}
if(Test-Path $l){$r=N $l $p;if($r[0]){foreach($x in ($r[0] -split "`r?`n")){if($x){$o.WriteLine("L|$x")}}};$p=$r[1];$o.WriteLine("P|$p")}
$t=Get-ChildItem "$d\logs\*_trial_history.csv" -EA 0|Sort-Object CreationTime|Select-Object -Last 1
if($t){if($t.Name -ne $f){$q=0;$f=$t.Name;$o.WriteLine("H|$f|"+(Get-Content $t.FullName -TotalCount 1))}
$r=N $t.FullName $q;if($r[0]){foreach($x in ($r[0] -split "`r?`n")){if($x){$o.WriteLine("T|$x")}}};$q=$r[1];$o.WriteLine("Q|$f|$q")}
if($i%30 -eq 0 -and (Test-Path "$d\status.json")){$o.WriteLine("S|"+(Get-Content "$d\status.json" -Raw|ConvertFrom-Json).state)}}
$i++;$o.Flush();Start-Sleep 1}
$o.WriteLine('E|');$o.Flush()
"""  # noqa: E501


def read_settings(path):
    """``remote*.local.psd1``에서 ``(Host, JobsRoot)``를 읽습니다. 주석 줄은 건너뜁니다."""
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    values = dict(re.findall(r'^[ \t]*(Host|JobsRoot)[ \t]*=[ \t]*"([^"]*)"', text, re.M))
    if "Host" not in values:
        raise ValueError(f"no Host in {path}")
    return values["Host"], values.get("JobsRoot", r"C:\wec_jobs")


def settings_label(path):
    """``remote.local.psd1``은 PC1, ``remote.pc2.local.psd1``은 PC2처럼 이름을 붙입니다."""
    parts = os.path.basename(path).split(".")
    return parts[1].upper() if len(parts) > 3 else "PC1"


def find_targets(folder):
    """설정 파일마다 ``(이름, Host, JobsRoot)``를 돌려줍니다."""
    targets = []
    for path in sorted(glob.glob(os.path.join(folder, "remote*.local.psd1"))):
        targets.append((settings_label(path), *read_settings(path)))
    return sorted(targets)


def quote(text):
    return text.replace("'", "''")


def agent_command(root, state):
    """감시 루프를 ``powershell -EncodedCommand`` 명령으로 만듭니다. 따옴표가 SSH에서 깨지지 않습니다."""
    script = (
        AGENT.replace("@ROOT@", quote(root))
        .replace("@JOB@", quote(state["job"]))
        .replace("@LOG@", str(state["log"]))
        .replace("@FILE@", quote(state["file"]))
        .replace("@TRIAL@", str(state["trial"]))
        .replace("@SECONDS@", str(AGENT_SECONDS))
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {encoded}"


def new_state():
    """한 PC의 이어 보기 위치와 지금 계산 중인 내용을 담습니다."""
    return {
        "job": "",
        "log": 0,
        "file": "",
        "trial": 0,
        "fitness": None,
        "run": "",
        "ended": False,
        "live": False,
        "ready": False,
        "site": "",
        "seed": "",
        "method": "",
        "population": 0,
        "generations": 0,
        "rows": 0,
        "generation": 0,
        "rows_done": 0,
        "best": None,
        "finished": False,
    }


def run_name(state):
    """``Buan seed 1 simultaneous`` 형식의 실행 이름."""
    seed = f" seed {state['seed']}" if state["seed"] else ""
    return f"{state['site'] or '?'}{seed} {state['method'] or '?'}"


def reset_run(state, site):
    """새 실행이 시작되면 진행 정보를 비웁니다."""
    state.update(
        site=site,
        seed="",
        method="",
        population=0,
        generations=0,
        rows=0,
        generation=0,
        rows_done=0,
        best=None,
        finished=False,
    )


def read_log_line(line, state):
    """``run.log`` 한 줄로 진행 정보를 갱신하고, 남길 사건 문구를 돌려줍니다 (없으면 None)."""
    if found := re.match(r"Sea state: \[([^\]]+)\]", line):
        reset_run(state, found.group(1))
    elif found := re.match(r"Mode: \[([^\]]+)\]", line):
        state["method"] = METHODS.get(found.group(1), found.group(1))
    elif found := re.match(r"Random seed: (\S+)", line):
        state["seed"] = found.group(1)
        return f"{run_name(state)} started"
    elif found := re.search(r"initial population of (\d+)", line):
        state["population"] = int(found.group(1))
    elif found := INIT_LINE.match(line):
        state["best"] = float(found.group(1))
    elif found := GENERATION_LINE.match(line):
        generation, total, _, population, best, wamit, penalty = found.groups()
        state.update(
            generation=int(generation),
            generations=int(total),
            population=int(population),
            best=float(best),
            rows_done=int(wamit) + int(penalty),
        )
        return f"{run_name(state)} Gen {int(generation)}/{total} done, best {float(best):.2f} kW, WAMIT {wamit}"
    elif line.startswith("=== Optimization Finished"):
        state["finished"] = True
    elif found := re.match(r"Best fitness\s*:\s*([-\d.]+) kW", line):
        state["best"] = float(found.group(1))
        return f"{run_name(state)} finished, best {state['best']:.2f} kW"
    elif PROBLEM_LINE.search(line):
        return line
    return None


def format_trial(line, fitness_index):
    """평가 CSV 한 줄을 문구로 바꿉니다. 간격 위반으로 WAMIT을 돌리지 않은 설계는 None입니다."""
    cols = line.split(",")
    try:
        if fitness_index is None or cols[-1].strip() == "1":
            return None
        design = " ".join(f"{float(v):g}" for v in cols[:fitness_index])
        return f"trial {float(cols[fitness_index]) / 1000:8.3f} kW | {design}"
    except (ValueError, IndexError):
        return None


def handle_agent_line(line, state, verbose=False):
    """감시 루프의 한 줄로 상태를 갱신하고, 화면에 남길 사건 문구를 돌려줍니다 (없으면 None)."""
    kind, _, body = line.rstrip("\r\n").partition("|")
    if kind == "J":
        if body == state["job"]:  # 같은 작업에 다시 연결한 경우
            return None
        state["job"] = body
        return f"job {body}"
    if kind == "E":
        state["ended"] = True
    elif kind == "L":
        event = read_log_line(body, state)
        return body if verbose else event
    elif kind == "P":
        state["log"] = int(body)
        state["live"] = True
    elif kind == "H":
        name, _, header = body.partition("|")
        columns = header.split(",")
        state.update(file=name, rows=0, fitness=columns.index("fitness") if "fitness" in columns else None)
    elif kind == "T":
        if not body.startswith("v1,"):
            state["rows"] += 1
            if verbose and state["live"]:
                return format_trial(body, state["fitness"])
    elif kind == "Q":
        name, _, position = body.partition("|")
        state["file"], state["trial"] = name, int(position)
    elif kind == "S":
        state["ready"] = True
        previous, state["run"] = state["run"], body
        if previous and body != previous:
            return f"job state: {body}"
    return None


def progress_text(state):
    """지금 세대와 그 세대에서 새로 평가한 개체 수.

    평가 파일에는 저장값을 재사용한 설계가 적히지 않으므로, 세대 번호는 줄 수가 아니라 끝난 세대 줄에서 읽습니다.
    """
    if state["finished"]:
        return "finished"
    population = state["population"]
    if not population:
        return "starting"
    particle = max(state["rows"] - state["rows_done"], 0)
    if not state["generations"]:
        return f"Init | particle {particle}/{population}"
    return f"Gen {state['generation'] + 1}/{state['generations']} | particle {particle}/{population}"


def status_text(state):
    """PC 한 대의 상태 한 줄."""
    if not state["job"]:
        return "connecting"
    if state["run"] and state["run"] != "running":
        return f"job {state['run']}: {state['job']}"
    best = f" | best {state['best']:.2f} kW" if state["best"] is not None else ""
    return f"{run_name(state)} | {progress_text(state)}{best}"


class Screen:
    """사건은 위로 쌓고, PC별 상태 줄은 맨 아래에서 그 자리만 고쳐 씁니다.

    터미널이 아니면(파일이나 파이프) 상태 줄을 그리지 않고 사건만 남깁니다.
    """

    def __init__(self, labels, stream=None, live=None):
        self.stream = stream or sys.stdout
        self.live = self.stream.isatty() if live is None else live
        self.lock = threading.Lock()
        self.width = max(len(label) for label in labels)
        self.statuses = dict.fromkeys(labels, "")
        self.drawn = 0

    def _erase(self):
        if self.drawn:
            self.stream.write(f"\033[{self.drawn}A\033[J")
            self.drawn = 0

    def _draw(self):
        rows = [(label, text) for label, text in self.statuses.items() if text]
        for label, text in rows:
            self.stream.write(f"{label:<{self.width}} | {text}\n")
        self.drawn = len(rows)

    def show(self, label, text):
        with self.lock:
            if self.live:
                self._erase()
            self.stream.write(f"[{label:<{self.width}} {time.strftime('%H:%M:%S')}] {text}\n")
            if self.live:
                self._draw()
            self.stream.flush()

    def set_status(self, label, text):
        with self.lock:
            if self.statuses.get(label) == text:
                return
            self.statuses[label] = text
            if self.live:
                self._erase()
                self._draw()
                self.stream.flush()


def follow_remote(label, host, root, screen, state, verbose=False, history=False, stop=None):
    """SSH 연결 하나로 계산용 PC를 따라갑니다. 끊기면 멈춘 위치부터 다시 잇습니다."""
    stop = stop or threading.Event()
    screen.set_status(label, status_text(state))
    while not stop.is_set():
        command = ["ssh", *SSH_OPTIONS, host, agent_command(root, state)]
        state["ended"] = False
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                errors="replace",
            )
            state["process"] = process
            for line in process.stdout:
                was_live = state["live"]
                text = handle_agent_line(line, state, verbose)
                if text is not None and (was_live or history):
                    screen.show(label, text)
                screen.set_status(label, status_text(state))
                if stop.is_set():
                    process.kill()
                    return
            process.wait()
        except OSError as err:
            screen.show(label, f"ssh failed: {err}")
        if state["ended"]:
            continue  # 정해진 시간이 지나 끝난 것이므로 말없이 바로 다시 잇습니다
        if not stop.is_set():
            screen.set_status(label, f"connection lost, retrying in {RETRY_SECONDS} s")
            stop.wait(RETRY_SECONDS)


def read_new_lines(path, position):
    """``position`` 뒤의 완성된 줄과 새 위치를 돌려줍니다. 쓰는 중인 마지막 줄은 다음 번에 읽습니다."""
    try:
        with open(path, "rb") as f:
            f.seek(position)
            data = f.read()
    except OSError:
        return [], position
    end = data.rfind(b"\n")
    if end < 0:
        return [], position
    text = data[: end + 1].decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line], position + end + 1


def follow_local(label, path, screen, history=False, stop=None):
    """이 PC의 텍스트 파일을 따라갑니다. 새 줄은 사건으로 남습니다."""
    stop = stop or threading.Event()
    position = 0 if history or not os.path.exists(path) else os.path.getsize(path)
    screen.set_status(label, f"following {path}")
    while not stop.is_set():
        lines, position = read_new_lines(path, position)
        for line in lines:
            screen.show(label, line)
        stop.wait(POLL_SECONDS)


def parse_local(values):
    """``LABEL=PATH`` 목록을 ``(LABEL, PATH)`` 목록으로 바꿉니다."""
    pairs = []
    for value in values:
        label, separator, path = value.partition("=")
        if not separator or not label or not path:
            raise ValueError(f"--local needs LABEL=PATH, got {value!r}")
        pairs.append((label, path))
    return pairs


def stop_processes(states):
    for state in states.values():
        process = state.get("process")
        if process is not None and process.poll() is None:
            process.kill()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--once", action="store_true", help="print the status of the compute PCs once and exit")
    parser.add_argument("--history", action="store_true", help="also show the events of the job so far")
    parser.add_argument("--verbose", action="store_true", help="show every log line and every evaluation")
    parser.add_argument("--local", nargs="*", default=[], help="LABEL=PATH, a text file on this PC to follow")
    parser.add_argument("--settings-dir", default=os.path.join(ROOT, "scripts"))
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    remotes = find_targets(args.settings_dir)
    try:
        locals_ = parse_local(args.local)
    except ValueError as err:
        parser.error(str(err))
    labels = [target[0] for target in remotes] + [pair[0] for pair in locals_]
    if not labels or (args.once and not remotes):
        parser.error("no scripts/remote*.local.psd1 file and no --local file to watch")

    live = sys.stdout.isatty() and not args.once
    if live and os.name == "nt":
        os.system("")  # Windows 콘솔에서 제어 문자를 켭니다
    screen = Screen(labels, live=live)
    stop = threading.Event()
    states = {label: new_state() for label, _, _ in remotes}
    threads = [
        threading.Thread(
            target=follow_remote,
            args=(label, host, root, screen, states[label], args.verbose, args.history, stop),
            daemon=True,
        )
        for label, host, root in remotes
    ]
    if not args.once:
        threads += [
            threading.Thread(target=follow_local, args=(label, path, screen, args.history, stop), daemon=True)
            for label, path in locals_
        ]
    for thread in threads:
        thread.start()

    if args.once:
        deadline = time.time() + ONCE_TIMEOUT_SECONDS
        while time.time() < deadline and not all(state["ready"] for state in states.values()):
            time.sleep(0.2)
        stop.set()
        stop_processes(states)
        for label, state in states.items():
            text = status_text(state) if state["ready"] else "no answer"
            print(f"{label} | {text}", flush=True)
        return

    print("Ctrl+C stops the watching only; the jobs keep running.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        stop_processes(states)
        print("Stopped watching. The jobs are still running.", flush=True)


if __name__ == "__main__":
    main()
