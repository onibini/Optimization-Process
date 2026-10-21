import json
import os
import subprocess
import warnings

from src.physics.mesh_axisymmetric_shape import DEFAULT_QUARTER_PANELS, generate_cylinder_hemisphere_mesh

# 32-bit WAMIT은 (기수 x 기당 패널 수)가 약 1,100을 넘으면 메모리 할당 오류가 납니다 (R=2.5, D=5.0, 5기 실측:
# 1,075 성공, 1,120~1,380 실패). 이 값을 넘기면 경고합니다. 실제 한계는 형상·배치에 따라 다를 수 있습니다.
PANEL_MEMORY_WARN = 1000


def write_wamit_inputs(vector, config, workspace_dir, positions=None):
    """
    OptMode에 따라 WAMIT 입력 파일(fnames.wam, .pot, .frc, .gdf)을 생성합니다.
    """
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)

    mode = config["opt_mode"]
    NCPU = config["ncpu"]
    RAMGBMAX = config["ram"]

    # 1. 최적화 모드별 형상 및 위치 확정
    if mode == 1:  # Shape Only
        radius, draft = vector[0], vector[1]
        body_positions = [(0.0, 0.0)]
    elif mode == 2:  # Layout Only
        radius, draft = config["fixed_radius"], config["fixed_draft"]
        body_positions = positions
    else:  # Shape + Layout
        radius, draft = vector[0], vector[1]
        body_positions = positions

    if body_positions is None:
        raise ValueError("WEC positions must be provided for layout or joint optimization modes.")
    if not (radius > 0 and draft > 0):
        raise ValueError(f"Radius and draft must be positive, got radius={radius}, draft={draft}")

    gdf_filename = "wec.gdf"
    gdf_path = os.path.join(workspace_dir, gdf_filename)
    target_panels = int(config.get("mesh_panels") or DEFAULT_QUARTER_PANELS)
    total_panels = target_panels * len(body_positions)
    if total_panels > PANEL_MEMORY_WARN:
        warnings.warn(
            f"MeshPanels({target_panels}) x {len(body_positions)} bodies = {total_panels} panels "
            f"exceeds {PANEL_MEMORY_WARN}; 32-bit WAMIT may fail with an allocation error.",
            stacklevel=2,
        )

    # 2. GDF 파일 생성
    write_gdf_if_needed(gdf_path, radius, draft, target_panels)

    # 3. fnames.wam 작성
    with open(os.path.join(workspace_dir, "fnames.wam"), "w") as f:
        f.write("wec.cfg\n")
        f.write("wec.pot\n")
        f.write("wec.frc\n")

    # 4. POT 파일 작성
    write_pot_file(workspace_dir, body_positions, config)

    # 5. FRC 파일 작성
    write_frc_file(workspace_dir, len(body_positions))

    # 6. CFG 파일 작성
    write_config_cfg(workspace_dir, mode)

    # 7. WAMIT 설정 파일 작성
    write_config_wam(workspace_dir, NCPU, RAMGBMAX)


def write_gdf_if_needed(gdf_path, radius, draft, target_panels):
    meta_path = f"{gdf_path}.meta.json"
    mesh_meta = {
        "radius": round(float(radius), 10),
        "draft": round(float(draft), 10),
        "target_panels": int(target_panels),
        "mesh": "cubed-sphere-v1",
    }

    if os.path.exists(gdf_path) and os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                if json.load(f) == mesh_meta:
                    return
        except (OSError, json.JSONDecodeError):
            pass

    generate_cylinder_hemisphere_mesh(radius, draft, target_panels=target_panels, output_path=gdf_path)

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(mesh_meta, f, indent=2)


def write_pot_file(workspace_dir, positions, config):
    depth = config["depth"]

    with open(os.path.join(workspace_dir, "wec.pot"), "w") as f:
        f.write("WEC Optimization Array Analysis\n")
        f.write(f"{depth:<20} HBOT\n")
        f.write(f"{'0 0':<20} IRAD IDIFF\n")
        f.write(f"{'-51':<20} NPER\n")
        f.write(f"{'0.5 0.05':<20} PER\n")
        f.write(f"{'1':<20} NBETA\n")
        f.write(f"{'0':<20} BETA\n")
        f.write(f"{len(positions):<20} NBODY\n")
        for x, y in positions:
            f.write("wec.gdf\n")
            f.write(f"{x} {y} 0 0\n")
            f.write(f"{'0 0 1 0 0 0':<20} IMODE\n")


# .frc OutputFile 옵션(IOPTN 1..9): 1 = .1 부가질량/감쇠, 2 = .2 Haskind 가진력, 3 = .3 diffraction 가진력.
# .1은 항상 필요하고, 가진력은 rao_calc가 쓰는 한 가지만 요청합니다 (나머지는 계산·파일 쓰기 생략).
EXCITATION_OUTPUT_OPTIONS = {
    "diffraction": "1 0 1 0 0 0 0 0 0",
    "haskind": "1 1 0 0 0 0 0 0 0",
}


def write_frc_file(workspace_dir, nbody, excitation="diffraction"):
    with open(os.path.join(workspace_dir, "wec.frc"), "w") as f:
        f.write("WEC Force Configuration\n")
        f.write(f"{EXCITATION_OUTPUT_OPTIONS[excitation]:<20} OutputFile\n")
        for i in range(nbody):
            f.write(f"{'0':<20} VCG{i + 1}\n")
            f.write(f"{'1 0 0':<20}\n")
            f.write(f"{'0 1 0':<20}\n")
            f.write(f"{'0 0 1':<20}\n")
        f.write(f"{'0':<20} NBETAH\n")
        f.write(f"{'0':<20} NFIELD\n")


def write_config_wam(workspace_dir, NCPU, RAMGBMAX):
    with open(os.path.join(workspace_dir, "config.wam"), "w") as f:
        f.write("WEC Configuration\n")
        f.write(f"NCPU={NCPU}\n")
        f.write(f"RAMGBMAX={RAMGBMAX}\n")
        f.write("USERID_PATH=C:\\WAMITv7\n")


def write_config_cfg(workspace_dir, opt_mode):
    iwallx_val = 0 if opt_mode == 1 else 1
    with open(os.path.join(workspace_dir, "wec.cfg"), "w") as f:
        f.write("WEC Optimization Configuration\n")
        f.write("ipltdat=1\n")
        f.write("NUMHDR=1\n")
        f.write("IPERIN=2\n")
        f.write("IPEROUT=2\n")
        f.write(f"IWALLX0={iwallx_val}\n")
        f.write("ISOR=0\n")
        f.write("ISOLVE=1\n")
        f.write("MAXITT=100\n")
        f.write("ISCATT=0\n")
        f.write("IALTERC=1\n")
        f.write("ILOC=1\n")


class WamitRunError(RuntimeError):
    """WAMIT 실행 파일이 없거나 비정상 종료했을 때 발생합니다."""


def _tail(text, n_lines=20):
    lines = (text or "").strip().splitlines()
    return "\n".join(lines[-n_lines:])


DEFAULT_WAMIT_EXE = r"C:\WAMITv7\WAMIT.exe"
WAMIT_EXE_ENV_VAR = "WAMIT_EXE"


def resolve_wamit_exe(configured=None):
    """WAMIT 실행 파일 경로를 정합니다. 우선순위: 인자(config.cfg의 WAMITPath) > 환경 변수 WAMIT_EXE > 기본 경로."""
    return configured or os.environ.get(WAMIT_EXE_ENV_VAR) or DEFAULT_WAMIT_EXE


def run_wamit(workspace_dir, exe_path=None):
    """작업 디렉토리에서 WAMIT을 직접 실행합니다.

    ``exe_path``를 생략하면 환경 변수 ``WAMIT_EXE``, 그것도 없으면 ``DEFAULT_WAMIT_EXE``를 사용합니다.

    이전 실행의 출력이 남아 있으면 이번 실행이 실패해도 옛 결과를 읽을 수 있으므로 먼저 지웁니다.
    실패 시에는 WAMIT의 stdout/stderr와 errorp.log/errorf.log 마지막 부분을 예외 메시지에 담습니다.
    """
    del_files = ["wec.1", "wec.2", "wec.3", "wec.4", "wec.out", "wec.p2f", "wec.hst", "errorp.log", "errorf.log"]
    for filename in del_files:
        file_path = os.path.join(workspace_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    exe_path = resolve_wamit_exe(exe_path)
    if not os.path.exists(exe_path):
        raise WamitRunError(f"WAMIT executable not found: {exe_path}")

    proc = subprocess.run([exe_path, "fnames.wam"], cwd=workspace_dir, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        details = [f"WAMIT exited with code {proc.returncode} (workspace: {workspace_dir})"]
        if proc.stdout:
            details.append("--- stdout (tail) ---\n" + _tail(proc.stdout))
        if proc.stderr:
            details.append("--- stderr (tail) ---\n" + _tail(proc.stderr))
        for log_name in ("errorp.log", "errorf.log"):
            log_path = os.path.join(workspace_dir, log_name)
            if os.path.exists(log_path):
                with open(log_path, errors="replace") as f:
                    log_text = _tail(f.read())
                if log_text:
                    details.append(f"--- {log_name} (tail) ---\n{log_text}")
        raise WamitRunError("\n".join(details))
    return proc
