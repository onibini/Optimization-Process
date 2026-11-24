"""Build data/hemisphere_patches.json: the hemisphere spline patches of the Shape 1 body (cylinder + hemisphere),
made by cad2bem, for HydroBEM high order (``HighOrderSpans`` > 0 with ``Shape`` 1).

For every radius of the grid, ``scripts/make_hemisphere_step.py`` (gmsh) writes the body as
STEP and ``cad2bem convert --mode ho --cut-waterline --symmetry xz_and_yz`` turns it into HBG patches (quarter
model). The three hemisphere patches are stored with their z measured from the cylinder bottom (the sphere centre):
they depend on the radius only, and a draft D moves them down by D (checked: 3e-14 m). The cylinder wall is one
exact rational patch that ``src/physics/solvers.py`` writes itself.

Needs cad2bem (https://github.com/winsccssvly/cad2bem, release 0.1.0) and gmsh in this Python; the optimization
itself needs neither.

    python scripts/make_hemisphere_patches.py --cad2bem PATH\\cad2bem.exe [--rmin 0.5 --rmax 2.5 --step 0.1]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP_SCRIPT = os.path.join(ROOT, "scripts", "make_hemisphere_step.py")
OUT = os.path.join(ROOT, "data", "hemisphere_patches.json")
GEN_DRAFT = 1.0  # 패치를 만들 때 쓰는 원통 길이 (결과는 원통 바닥 기준으로 저장하므로 값과 무관)


def convert(cad2bem, radius, folder):
    step = os.path.join(folder, f"r{radius:.3f}.step")
    hbg = os.path.join(folder, f"r{radius:.3f}.hbg")
    subprocess.run([sys.executable, STEP_SCRIPT, str(radius), str(GEN_DRAFT), step], check=True, capture_output=True)
    cmd = [cad2bem, "convert", step, "--mode", "ho", "--unit", "m", "--cut-waterline", "--symmetry", "xz_and_yz"]
    cmd += ["--patch-size", "8", "--json", "--out", hbg]
    result = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
    if result["state"] != "ok":
        raise RuntimeError(f"cad2bem state {result['state']} for radius {radius}")
    with open(hbg, encoding="utf-8") as fh:
        data = json.load(fh)
    sphere = [p for p in data["patches"] if "weights" not in p]
    if len(sphere) != 3 or len(data["patches"]) != 4:
        raise RuntimeError(f"unexpected patch layout for radius {radius}: {[p['name'] for p in data['patches']]}")
    for patch in sphere:
        patch["coefficients"] = [[[x, y, z + GEN_DRAFT] for x, y, z in row] for row in patch["coefficients"]]
    return sphere, result["engine_version"], max(p["cad_error_m"] for p in result["patch_checks"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cad2bem", required=True)
    ap.add_argument("--rmin", type=float, default=0.5)
    ap.add_argument("--rmax", type=float, default=2.5)
    ap.add_argument("--step", type=float, default=0.1)
    args = ap.parse_args()
    cad2bem = os.path.abspath(args.cad2bem)
    count = round((args.rmax - args.rmin) / args.step) + 1
    radii = [round(args.rmin + k * args.step, 6) for k in range(count)]
    patches, version, worst = {}, None, 0.0
    with tempfile.TemporaryDirectory() as folder:
        for radius in radii:
            sphere, version, err = convert(cad2bem, radius, folder)
            patches[f"{radius:.3f}"] = sphere
            worst = max(worst, err)
            print(f"radius {radius:.3f}: {len(sphere)} hemisphere patches, cad error {err:.1e} m", flush=True)
    data = {
        "description": "Quarter-model hemisphere patches (x, y >= 0) of the Shape 1 body; z from the cylinder bottom.",
        "generator": f"cad2bem {version} --mode ho --cut-waterline --symmetry xz_and_yz --patch-size 8",
        "max_cad_error_m": worst,
        "patches": patches,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"Saved {OUT} ({len(patches)} radii, {os.path.getsize(OUT) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
