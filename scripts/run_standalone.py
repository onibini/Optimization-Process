# ruff: noqa: E402
"""Run one optimization on a PC that has no remote access (files copied by hand), with HydroBEM threads set
from a short on-site timing.

From the project (or package) root::

    python scripts/run_standalone.py --config job.cfg            # time the thread splits, then run
    python scripts/run_standalone.py --config job.cfg --ncpu 51  # skip the timing
    python scripts/run_standalone.py --config job.cfg --ncpu 102 --resume auto  # continue a stopped run

What it does:

1. Prints the PC (logical CPUs, Python, hydrobem_gui).
2. ``--ncpu auto`` (default, ``HydroSolver`` 3 only): solves the 5-WEC + wall case of the config's site
   (Shape and ``HighOrderSpans`` of the config) with a few ``NCPU`` values and keeps the fastest.
   HydroBEM splits ``NCPU`` into frequency threads (at most the number of frequencies, 51 by default) and
   threads inside one frequency (``hydrobem_threads``). Candidates: half the CPUs, all CPUs, the number of
   frequencies and twice that (when the PC has more CPUs than frequencies). Results: logs/standalone_threads.json.
3. Writes ``<config>_run.cfg`` with that ``NCPU`` and ``Workers`` 1 (``DEUpdate`` unchanged, so the run follows
   the same path as the same config elsewhere), then runs ``main.main`` with its output also in run.log.
"""

import argparse
import json
import os
import platform
import re
import sys
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import numpy as np

from src.physics.solvers import GRAVITY, RHO, frequency_list, hydrobem_threads
from src.utils.config_parser import parse_wec_cfg
from src.utils.data_handler import load_env_data
from src.utils.mapper import decode_symmetric_positions

BENCH_RADIUS, BENCH_DRAFT = 2.5, 4.8
BENCH_LAYOUT = [24.8, 3.6, 30.0, 21.9, 30.0]  # 5 WECs near the wall (Buan optimum of an earlier run)


class Tee:
    """Writes to the console and to a log file."""

    def __init__(self, stream, path):
        self.stream = stream
        self.file = open(path, "a", encoding="utf-8")  # noqa: SIM115

    def write(self, text):
        self.stream.write(text)
        self.file.write(text)
        self.file.flush()

    def flush(self):
        self.stream.flush()
        self.file.flush()


def candidate_ncpus(logical, num_frequencies):
    """Distinct thread splits to time, as NCPU values (smallest first)."""
    values = {max(1, logical // 2), logical, min(logical, num_frequencies)}
    if logical > num_frequencies:
        values.update({num_frequencies, 2 * num_frequencies})
    chosen, seen = [], set()
    for ncpu in sorted(values):
        split = hydrobem_threads(ncpu, num_frequencies)
        if split not in seen:
            seen.add(split)
            chosen.append(ncpu)
    return chosen


def bench_solve(hb, ncpu, omegas, depth, shape, spans, wall):
    model = hb.Model()
    if spans:
        model.meshes.analytic(
            name="wec", shape="circular_cylinder",
            discretization=[(spans, spans, 3, 3, 3, 4), (spans, max(1, spans // 2), 3, 3, 3, 4)],
            parts=["side", "bottom"], mapping="nonuniform", radius=BENCH_RADIUS, draft=BENCH_DRAFT,
            reference_length=1.0, symmetry="xz_and_yz",
        )  # fmt: skip
    else:
        from src.physics.mesh_axisymmetric_shape import generate_mesh

        os.makedirs(os.path.join(ROOT, "workspace"), exist_ok=True)
        gdf = os.path.join(ROOT, "workspace", "standalone_bench.gdf")
        generate_mesh(shape, BENCH_RADIUS, BENCH_DRAFT, target_panels=120, output_path=gdf)
        model.meshes.load("wec", gdf)
    for k, (x, y) in enumerate(decode_symmetric_positions(BENCH_LAYOUT, 5)):
        model.bodies.add(
            name=f"b{k}", mesh="wec", position=[float(x), float(y), 0.0], rotation_center=[0.0, 0.0, 0.0],
            modes=["heave"], interior_surface="none",
        )  # fmt: skip
    model.environment.update(
        depth=depth, density=RHO, gravity=GRAVITY, domain="x_wall" if wall else "open_sea",
        frequency_input="omegas", omegas=omegas, headings=[0.0],
    )  # fmt: skip
    model.first_order.update(radiation=True, diffraction=True, motion=False)
    frequency_threads, inner_threads = hydrobem_threads(ncpu, len(omegas))
    model.options.update(frequency_threads=frequency_threads, inner_threads=inner_threads, higher_order=bool(spans))
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.solve()
    return time.perf_counter() - t0


def time_thread_splits(cfg, logical, repeat):
    import hydrobem_gui as hb

    shape = int(cfg["WEC Parameters"].get("Shape", 1))
    spans = int(cfg["Simulation"].get("HighOrderSpans", 0))
    wall = int(cfg["WEC Parameters"].get("VerticalWall", 1)) == 1
    depth = float(load_env_data(int(cfg["Environment"]["SiteID"]))["Depth"])
    config = {
        "omega_max": float(cfg["WAMIT Settings"].get("OmegaMax", 3.0)),
        "freq_grid": int(cfg["WAMIT Settings"].get("FreqGrid", 0)),
    }
    omegas = np.array(frequency_list(config, BENCH_RADIUS, BENCH_DRAFT, shape), dtype=float)
    print(f"Timing HydroBEM thread splits: 5 WECs, {len(omegas)} frequencies, depth {depth:g} m", flush=True)
    bench_solve(hb, min(logical, len(omegas)), omegas, depth, shape, spans, wall)  # warm up
    runs = []
    for ncpu in candidate_ncpus(logical, len(omegas)):
        times = [bench_solve(hb, ncpu, omegas, depth, shape, spans, wall) for _ in range(repeat)]
        frequency_threads, inner_threads = hydrobem_threads(ncpu, len(omegas))
        runs.append(
            {
                "ncpu": ncpu,
                "frequency_threads": frequency_threads,
                "inner_threads": inner_threads,
                "seconds": min(times),
            }
        )
        print(
            f"  NCPU {ncpu:4d} = {frequency_threads:3d} frequency x {inner_threads} inner threads: "
            f"{min(times):7.2f} s per solve",
            flush=True,
        )
    fastest = min(run["seconds"] for run in runs)
    # 거의 같으면(3% 이내) 스레드가 적은 쪽을 고른다
    best = next(run for run in runs if run["seconds"] <= fastest * 1.03)
    return best, runs, len(omegas)


def set_value(text, key, value):
    """Replaces the value of ``key`` in a config file (the first token of its line)."""
    pattern = re.compile(rf"^(\s*)\S+(\s+{re.escape(key)}\s+-)", re.MULTILINE)
    new, count = pattern.subn(lambda m: f"{m.group(1)}{value}{m.group(2)}", text)
    if count != 1:
        raise ValueError(f"{key} not found once in the config")
    return new


def newest_checkpoint(folder):
    """The newest ``*_checkpoint.json`` in a folder (by modification time)."""
    import glob

    found = glob.glob(os.path.join(folder, "*_checkpoint.json"))
    if not found:
        raise FileNotFoundError(f"No *_checkpoint.json in {folder}")
    return max(found, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--ncpu", default="auto", help="'auto' (time the splits) or an integer")
    ap.add_argument("--repeat", type=int, default=2, help="solves per split; the minimum time is used")
    ap.add_argument("--log", default="run.log")
    ap.add_argument(
        "--resume", default=None, help="checkpoint to continue from, or 'auto' for the newest logs/*_checkpoint.json"
    )
    args = ap.parse_args()

    os.chdir(ROOT)
    sys.stdout = Tee(sys.stdout, args.log)
    logical = os.cpu_count() or 1
    print(f"=== Standalone run {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"PC: {platform.node()}, {platform.processor()}, {logical} logical CPUs, Python {platform.python_version()}")
    cfg = parse_wec_cfg(args.config)
    solver = int(cfg["Simulation"].get("HydroSolver", 1))
    if solver == 3:
        import hydrobem_gui

        print(f"hydrobem_gui {getattr(hydrobem_gui, '__version__', '?')}")

    if args.ncpu == "auto" and solver == 3:
        best, runs, num_frequencies = time_thread_splits(cfg, logical, args.repeat)
        ncpu = best["ncpu"]
        os.makedirs("logs", exist_ok=True)
        with open(os.path.join("logs", "standalone_threads.json"), "w", encoding="utf-8") as fh:
            record = {"logical_cpus": logical, "frequencies": num_frequencies, "runs": runs, "chosen": best}
            json.dump(record, fh, indent=2)
        print(f"Chosen NCPU {ncpu} ({best['frequency_threads']} frequency x {best['inner_threads']} inner threads)")
    elif args.ncpu == "auto":
        ncpu = int(cfg["WAMIT Settings"]["NCPU"])
        print(f"NCPU {ncpu} from the config (thread timing is for HydroSolver 3 only)")
    else:
        ncpu = int(args.ncpu)
        print(f"NCPU {ncpu} from --ncpu")

    with open(args.config, encoding="utf-8") as fh:
        text = fh.read()
    text = set_value(set_value(text, "NCPU", ncpu), "Workers", 1)
    if args.resume:
        checkpoint = newest_checkpoint("logs") if args.resume == "auto" else args.resume
        if " " in os.path.abspath(checkpoint):
            raise ValueError(f"Resume path must not contain spaces: {os.path.abspath(checkpoint)}")
        text = set_value(text, "Resume", os.path.abspath(checkpoint))
        print(f"Resume: {checkpoint}")
    run_cfg = os.path.splitext(args.config)[0] + "_run.cfg"
    with open(run_cfg, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"Config: {run_cfg}", flush=True)

    import main as project_main

    t0 = time.time()
    project_main.main(run_cfg)
    print(f"Wall time: {(time.time() - t0) / 3600:.2f} h", flush=True)


if __name__ == "__main__":
    main()
