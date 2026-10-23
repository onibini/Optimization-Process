import json
import math
import os
import re
import subprocess
import warnings

from src.physics.mesh_axisymmetric_shape import DEFAULT_QUARTER_PANELS, generate_cylinder_hemisphere_mesh

# 32-bit WAMIT은 (기수 x 기당 패널 수)가 약 1,100을 넘으면 메모리 할당 오류가 납니다 (R=2.5, D=5.0, 5기 실측:
# 1,075 성공, 1,120~1,380 실패). 이 값을 넘기면 경고합니다. 실제 한계는 형상·배치에 따라 다를 수 있습니다.
PANEL_MEMORY_WARN = 1000

# 주파수 격자: OMEGA_MIN에서 OMEGA_STEP 간격으로 OmegaMax(config.cfg)까지.
OMEGA_MIN = 0.5
OMEGA_STEP = 0.05
DEFAULT_OMEGA_MAX = 3.0
MIN_OMEGA_POINTS = 3  # Simpson 적분에 필요한 최소 점 수

# 작업 폴더: 기본 "workspace". WAMIT을 여러 개 동시에 돌리면 "workspace/w0", "workspace/w1", ...을 씁니다.
DEFAULT_WORKSPACE = "workspace"

# 선형 시스템 솔버 (WAMIT ISOLVE): 0 = 반복, 1 = 직접, N >= 2 = N개 블록 반복.
# 반복 솔버는 시간이 NEQN^2 x 반복 횟수, 직접 솔버는 NEQN^3에 비례하고 NEQN^2 임시 메모리가 필요합니다.
DEFAULT_SOLVER = 0
MAXITT = 100  # 반복 솔버 최대 반복 횟수 (WAMIT 기본값은 35)


def omega_grid(omega_max=None):
    """(주파수 점 수, 실제 상한)을 돌려줍니다. 점 수는 ``OMEGA_MIN + k * OMEGA_STEP <= omega_max``인 k의 개수입니다."""
    omega_max = DEFAULT_OMEGA_MAX if omega_max is None else float(omega_max)
    if not math.isfinite(omega_max):
        raise ValueError(f"OmegaMax must be finite, got {omega_max}")
    n_points = math.floor((omega_max - OMEGA_MIN) / OMEGA_STEP + 1e-9) + 1
    if n_points < MIN_OMEGA_POINTS:
        smallest = OMEGA_MIN + (MIN_OMEGA_POINTS - 1) * OMEGA_STEP
        raise ValueError(f"OmegaMax must be >= {smallest:g} rad/s ({MIN_OMEGA_POINTS} frequencies), got {omega_max}")
    return n_points, OMEGA_MIN + (n_points - 1) * OMEGA_STEP


# 적응형 주파수 격자 (FreqGrid=1): 기본 0.05 간격에서, 비제어 공진 부근 [LO, HI] x w0만 FINE_STEP 간격으로 촘촘히 하고
# TAIL_RATIO x w0 위쪽은 TAIL_STEP 간격으로 성기게 합니다. w0는 부력 기준 상하동요 고유진동수입니다.
# 근거: docs/frequency_grid_design.md, docs/reports/2026-10-23_03_freq-grid-quick4-study.md
GRAVITY = 9.80665
FREQ_GRID_LO = 0.85
FREQ_GRID_HI = 1.1
FREQ_GRID_FINE_STEP = OMEGA_STEP / 8  # 0.00625 rad/s
FREQ_GRID_TAIL_RATIO = 1.5
FREQ_GRID_TAIL_STEP = 2 * OMEGA_STEP
_LATTICE = OMEGA_STEP / 4  # 0.0125 rad/s: 구간 경계는 이 격자에 맞춥니다


def heave_omega0(radius, draft):
    """부력 기준 상하동요 고유진동수(부가질량 제외) sqrt(g / (draft + 2 radius / 3)) [rad/s]."""
    return math.sqrt(GRAVITY / (draft + 2.0 * radius / 3.0))


def adaptive_omegas(radius, draft, omega_max=None):
    """적응형 주파수 목록(rad/s, 오름차순). 공진 구간이 상한 안에 없으면 균일 격자(``omega_grid``)와 같습니다."""
    n_points, _ = omega_grid(omega_max)
    omega_max = OMEGA_MIN + (n_points - 1) * OMEGA_STEP
    w0 = heave_omega0(radius, draft)

    def snap(value):
        return round(value / _LATTICE) * _LATTICE

    lo = snap(max(OMEGA_MIN, FREQ_GRID_LO * w0))
    hi = snap(min(omega_max, FREQ_GRID_HI * w0))
    tail_from = snap(FREQ_GRID_TAIL_RATIO * w0)
    points = set()
    for k in range(n_points):
        w = OMEGA_MIN + k * OMEGA_STEP
        if lo < w < hi:
            continue
        if w > tail_from:
            j = (w - OMEGA_MIN) / FREQ_GRID_TAIL_STEP
            if abs(j - round(j)) > 1e-6:
                continue
        points.add(round(w, 6))
    if lo < hi:
        n_fine = round((hi - lo) / FREQ_GRID_FINE_STEP)
        points.update(round(lo + k * FREQ_GRID_FINE_STEP, 6) for k in range(n_fine + 1))
    return sorted(points)


def check_freq_grid(freq_grid):
    """FreqGrid 값을 검증합니다 (0: 균일, 1: 적응형)."""
    if isinstance(freq_grid, bool) or not isinstance(freq_grid, int) or freq_grid not in (0, 1):
        raise ValueError(f"FreqGrid must be 0 (uniform) or 1 (adaptive), got {freq_grid}")
    return freq_grid


def check_solver(solver):
    """ISOLVE 값을 검증합니다 (0 이상의 정수)."""
    if isinstance(solver, bool) or not isinstance(solver, int) or solver < 0:
        raise ValueError(
            f"Solver must be an integer >= 0 (0: iterative, 1: direct, N: N-block iterative), got {solver}"
        )
    return solver


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

    solver = DEFAULT_SOLVER if config.get("solver") is None else check_solver(config["solver"])

    # 4. POT 파일 작성
    freq_grid = check_freq_grid(config.get("freq_grid") or 0)
    omegas = adaptive_omegas(radius, draft, config.get("omega_max")) if freq_grid else None
    write_pot_file(workspace_dir, body_positions, config, omegas)

    # 5. FRC 파일 작성
    write_frc_file(workspace_dir, len(body_positions))

    # 6. CFG 파일 작성
    write_config_cfg(workspace_dir, mode, solver)

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


def write_pot_file(workspace_dir, positions, config, omegas=None):
    """``omegas``가 있으면 그 목록(rad/s)을 쓰고, 없으면 균일 격자를 씁니다."""
    depth = config["depth"]
    n_omega, _ = omega_grid(config.get("omega_max"))

    with open(os.path.join(workspace_dir, "wec.pot"), "w") as f:
        f.write("WEC Optimization Array Analysis\n")
        f.write(f"{depth:<20} HBOT\n")
        f.write(f"{'0 0':<20} IRAD IDIFF\n")
        if omegas is None:
            f.write(f"{-n_omega:<20} NPER\n")  # 음수: 시작값과 간격으로 정의하는 균일 격자
            f.write(f"{f'{OMEGA_MIN:g} {OMEGA_STEP:g}':<20} PER\n")
        else:
            f.write(f"{len(omegas):<20} NPER\n")  # 양수: 주파수 [rad/s] 목록 (IPERIN=2)
            for w in omegas:
                f.write(f"{w:.6f}\n")
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


def write_config_cfg(workspace_dir, opt_mode, solver=DEFAULT_SOLVER):
    iwallx_val = 0 if opt_mode == 1 else 1
    with open(os.path.join(workspace_dir, "wec.cfg"), "w") as f:
        f.write("WEC Optimization Configuration\n")
        f.write("ipltdat=1\n")
        f.write("NUMHDR=1\n")
        f.write("IPERIN=2\n")
        f.write("IPEROUT=2\n")
        f.write(f"IWALLX0={iwallx_val}\n")
        f.write("ISOR=0\n")
        f.write(f"ISOLVE={solver}\n")
        f.write(f"MAXITT={MAXITT}\n")
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


_ITERATION_ROW = re.compile(r"^\s*(\d+\.\d+)\s+\d{2}:\d{2}:\d{2}\s+(\d+)\s+(\d+)\s*$")


def find_unconverged(workspace_dir):
    """``wec.out``의 주파수별 반복 횟수 표에서 ``MAXITT``에 도달한 주파수 목록을 돌려줍니다.

    WAMIT은 반복 솔버가 수렴하지 못해도 경고만 하고 계속 진행하므로, 그 결과를 쓰기 전에 확인합니다.
    """
    maxitt = MAXITT
    cfg_path = os.path.join(workspace_dir, "wec.cfg")
    if os.path.exists(cfg_path):
        with open(cfg_path, errors="replace") as f:
            found = re.search(r"^MAXITT=(\d+)", f.read(), re.M)
        if found:
            maxitt = int(found.group(1))

    out_path = os.path.join(workspace_dir, "wec.out")
    if not os.path.exists(out_path):
        return []
    unconverged = []
    with open(out_path, errors="replace") as f:
        for line in f:
            row = _ITERATION_ROW.match(line)
            if row and max(int(row.group(2)), int(row.group(3))) >= maxitt:
                unconverged.append(float(row.group(1)))
    return unconverged


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

    unconverged = find_unconverged(workspace_dir)
    if unconverged:
        warnings.warn(
            f"WAMIT iterative solver reached MAXITT at {len(unconverged)} frequencies "
            f"(first: {unconverged[0]:g} rad/s); results there may be inaccurate. "
            "Increase panels, use Solver=1 (direct), or check for resonance/irregular frequencies.",
            stacklevel=2,
        )
    return proc
