"""Make a folder to copy to a PC without remote access and run one optimization there.

From the project root::

    python scripts/make_standalone_package.py --config job.cfg --out C:/temp/wec_job \
        --wheel path/to/hydrobem_gui-0.3.0-py3-none-win_amd64.whl [--download-wheels]

The folder holds the program (main.py, src/, data/env_data.csv, scripts/run_standalone.py), the config as job.cfg,
wheels/ (the HydroBEM wheel, and with --download-wheels numpy and scipy for Python 3.11 to 3.13 on Windows x64 so the
PC needs no internet), setup.bat, run.bat and README.txt. Copy the whole folder, run setup.bat once, then run.bat.
Bring back run.log and logs/ (put them under results/<name>/ to use scripts/summarize_results.py).
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYTHONS = ("3.11", "3.12", "3.13")

SETUP_BAT = r"""@echo off
rem One-time setup: makes venv\ and installs hydrobem_gui, numpy and scipy (from wheels\ first, then the internet).
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"
%PY% -c "import sys; assert sys.version_info >= (3, 11), sys.version" || (
    echo Python 3.11 or newer is needed. Install it from python.org and run setup.bat again.
    exit /b 1
)
if not exist venv\Scripts\python.exe %PY% -m venv venv || exit /b 1
venv\Scripts\python.exe -m pip install --no-index --find-links wheels hydrobem_gui numpy scipy
if errorlevel 1 venv\Scripts\python.exe -m pip install --find-links wheels hydrobem_gui numpy scipy || exit /b 1
venv\Scripts\python.exe -c "import hydrobem_gui, numpy, scipy; print('Setup OK')"
"""

RUN_BAT = r"""@echo off
rem Times the HydroBEM thread splits on this PC, then runs job.cfg. Output: run.log, logs\.
rem Extra options go to scripts\run_standalone.py, e.g. run.bat --ncpu 51 (skip the timing).
cd /d "%~dp0"
venv\Scripts\python.exe scripts\run_standalone.py --config job.cfg %*
"""

README = r"""WEC optimization, standalone run ({name})
=========================================

A folder to run one optimization on a PC without remote access. Copy the whole folder.

Setup (once)
  1. Python 3.11 or newer (64-bit) is needed. Install it from python.org if missing.
  2. Run setup.bat. The last line should be "Setup OK".
     With numpy and scipy in wheels\ no internet is needed; otherwise they are downloaded.

Run
  1. Turn sleep off (Settings > System > Power: sleep "Never"). The run takes hours.
  2. Run run.bat (from a command prompt, so the window stays open).
     - It first times a few HydroBEM thread splits on this PC for 1-3 minutes and keeps the fastest NCPU
       (logs\standalone_threads.json and the top of run.log).
     - Then it runs job_run.cfg (job.cfg with only NCPU and Workers changed).
     - To set NCPU yourself: run.bat --ncpu 51
     - To continue a stopped run from its last generation: run.bat --ncpu 102 --resume auto
  3. At the end run.log shows "Optimization Finished" and "Wall time".

Bring back
  run.log, the logs folder and job_run.cfg.
  (Put them under results\{name}\ in the project to read them with scripts\summarize_results.py.)

Settings
{summary}
"""


def summarize(cfg_path):
    sys.path.insert(0, ROOT)
    from src.utils.config_parser import parse_wec_cfg

    cfg = parse_wec_cfg(cfg_path)
    keys = [
        ("Simulation", "OptMode"),
        ("Simulation", "Algorithm"),
        ("Simulation", "HydroSolver"),
        ("Simulation", "HighOrderSpans"),
        ("Simulation", "PTORule"),
        ("WEC Parameters", "NumWECs"),
        ("WEC Parameters", "Shape"),
        ("WEC Parameters", "VerticalWall"),
        ("AlgorithmSettings", "PopSize"),
        ("AlgorithmSettings", "MaxIter"),
        ("AlgorithmSettings", "DEUpdate"),
        ("AlgorithmSettings", "Seed"),
        ("Environment", "SiteID"),
    ]
    return "\n".join(f"  {key:15s} {cfg[section].get(key, '-')}" for section, key in keys)


def copy_program(out):
    shutil.copy2(os.path.join(ROOT, "main.py"), out)
    shutil.copy2(os.path.join(ROOT, "requirements.txt"), out)
    shutil.copytree(
        os.path.join(ROOT, "src"), os.path.join(out, "src"), ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "data", "env_data.csv"), os.path.join(out, "data"))
    os.makedirs(os.path.join(out, "scripts"), exist_ok=True)
    shutil.copy2(os.path.join(HERE, "run_standalone.py"), os.path.join(out, "scripts"))


def download_wheels(wheels):
    for version in PYTHONS:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "numpy",
                "scipy",
                "--only-binary=:all:",
                "--platform",
                "win_amd64",
                "--python-version",
                version,
                "-d",
                wheels,
            ],
            check=True,
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True, help="new folder to create")
    ap.add_argument("--wheel", help="hydrobem_gui wheel to include (HydroSolver 3)")
    ap.add_argument("--download-wheels", action="store_true", help="also put numpy and scipy wheels in wheels/")
    args = ap.parse_args()

    if os.path.exists(args.out) and os.listdir(args.out):
        sys.exit(f"Error: {args.out} exists and is not empty")
    os.makedirs(args.out, exist_ok=True)
    copy_program(args.out)
    shutil.copy2(args.config, os.path.join(args.out, "job.cfg"))
    wheels = os.path.join(args.out, "wheels")
    os.makedirs(wheels, exist_ok=True)
    if args.wheel:
        shutil.copy2(args.wheel, wheels)
    if args.download_wheels:
        download_wheels(wheels)
    name = os.path.basename(os.path.normpath(args.out))
    for file_name, text in (
        ("setup.bat", SETUP_BAT),
        ("run.bat", RUN_BAT),
        ("README.txt", README.format(name=name, summary=summarize(args.config))),
    ):
        with open(os.path.join(args.out, file_name), "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(text)
    print(f"Package: {args.out}")
    for wheel in sorted(os.listdir(wheels)):
        print(f"  wheels/{wheel}")


if __name__ == "__main__":
    main()
