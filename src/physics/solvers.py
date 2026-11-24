"""수력 해석기(backend) 선택: WAMIT, Capytaine 또는 HydroBEM.

``solve_hydrodynamics``가 설계 벡터와 문제 설정으로 heave 수력 계수(``HydroData``)를 돌려주고, 이후 RAO·발전량
계산은 해석기와 무관합니다.

- WAMIT (기본): 입력 파일을 쓰고 WAMIT을 실행해 출력을 읽습니다. 수직벽(``vertical_wall``)을 지원합니다.
- Capytaine (선택, ``pip install capytaine``): 오픈소스 Python BEM. 이 프로젝트에서는 **개방 해역만** 지원합니다.
- HydroBEM (선택, ``hydrobem_gui`` wheel, Windows x64 + AVX2, Python 3.11+): 주파수 영역 패널법. WAMIT과 같은 GDF
  메쉬를 쓰고 수직벽(``x_wall``)을 지원합니다. 평가 하나가 ``NCPU``개 스레드를 주파수 병렬로 모두 씁니다.
"""

import functools
import json
import os

import numpy as np

from src.physics.hydro import HydroData
from src.physics.mesh_axisymmetric_shape import DEFAULT_QUARTER_PANELS, DEFAULT_SHAPE, build_mesh_panels, check_shape
from src.physics.rao_calc import read_wamit_hydro
from src.physics.wamit_handler import (
    DEFAULT_WORKSPACE,
    adaptive_omegas,
    check_freq_grid,
    check_wave_angle,
    omega_grid,
    resolve_geometry,
    run_wamit,
    wall_enabled,
    write_gdf_if_needed,
    write_wamit_inputs,
)

HYDRO_SOLVERS = {1: "WAMIT", 2: "Capytaine", 3: "HydroBEM"}
DEFAULT_HYDRO_SOLVER = 1
RHO, GRAVITY = 1025.0, 9.80665
# HydroBEM 고차(B-스플라인 패치)를 쓸 수 있는 형상.
# Shape 2(평평한 바닥 원통): 엔진의 해석적 원통.
# Shape 1(원통 + 반구): cad2bem으로 만든 반구 패치(data/hemisphere_patches.json) + 정확한 원통 패치.
HIGH_ORDER_SHAPES = (1, 2)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEMISPHERE_PATCHES = os.path.join(_ROOT, "data", "hemisphere_patches.json")
HIGH_ORDER_SPLINE = 3  # 스플라인 차수(u, v)
HIGH_ORDER_GAUSS = (3, 4)  # 바깥, 안쪽 가우스 차수


def check_hydro_solver(solver):
    """HydroSolver 값을 검증합니다 (1 WAMIT, 2 Capytaine, 3 HydroBEM)."""
    if isinstance(solver, bool) or solver not in HYDRO_SOLVERS:
        raise ValueError(f"HydroSolver must be one of {sorted(HYDRO_SOLVERS)} ({HYDRO_SOLVERS}), got {solver!r}")
    return solver


def check_high_order(spans, hydro_solver, shape):
    """HighOrderSpans를 검증합니다. 0은 저차(MeshPanels), N > 0은 HydroBEM 고차(면마다 N spans)."""
    if isinstance(spans, bool) or not isinstance(spans, (int, np.integer)) or spans < 0:
        raise ValueError(f"HighOrderSpans must be an integer >= 0, got {spans!r}")
    if spans and hydro_solver != 3:
        raise ValueError("HighOrderSpans > 0 needs HydroSolver 3 (HydroBEM).")
    if spans and shape not in HIGH_ORDER_SHAPES:
        raise ValueError(f"HighOrderSpans > 0 needs Shape {' or '.join(map(str, HIGH_ORDER_SHAPES))}, got {shape}.")
    return int(spans)


@functools.lru_cache(maxsize=1)
def hemisphere_patch_table(path=HEMISPHERE_PATCHES):
    """``data/hemisphere_patches.json``(scripts/make_hemisphere_patches.py, cad2bem): 반지름별 반구 패치 3개."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} is missing; build it with scripts/make_hemisphere_patches.py (needs cad2bem).")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["patches"]


def hemisphere_hbg(radius, draft, spans):
    """Shape 1(원통 길이 ``draft`` + 반구)의 1/4 모델 HBG 사전. 모든 패치가 ``spans x spans`` 입니다.

    - 반구: cad2bem이 만든 반지름별 패치 3개(원통 바닥 기준 z)를 ``draft``만큼 내립니다(흘수에 무관하게 같은 패치).
    - 원통 옆면: 정확한 유리 2차 패치 하나(높이 방향 1차, 둘레 방향 2차, cad2bem이 쓰는 것과 같은 형식).
    반지름은 패치를 만든 격자(기본 0.5~2.5 m, 0.1 m 간격)에 있어야 합니다.
    """
    table = hemisphere_patch_table()
    key = f"{float(radius):.3f}"
    if key not in table or abs(float(radius) - round(float(radius), 3)) > 1e-9:
        known = sorted(float(k) for k in table)
        raise ValueError(
            f"HighOrderSpans with Shape 1 needs a radius from data/hemisphere_patches.json ({known[0]:g} to "
            f"{known[-1]:g} m), got {radius}; add it with scripts/make_hemisphere_patches.py."
        )
    r, d = float(radius), float(draft)
    discretization = [int(spans), int(spans), HIGH_ORDER_SPLINE, HIGH_ORDER_SPLINE, *HIGH_ORDER_GAUSS]
    patches = []
    for patch in table[key]:
        moved = dict(patch)
        moved["coefficients"] = [[[x, y, z - d] for x, y, z in row] for row in patch["coefficients"]]
        moved["discretization"] = discretization
        patches.append(moved)
    patches.append(
        {
            "name": "cylinder_wall",
            "coefficients": [[[r, 0.0, -d], [r, 0.0, 0.0]], [[r, r, -d], [r, r, 0.0]], [[0.0, r, -d], [0.0, r, 0.0]]],
            "u_knots": [0.0, 0.0, 1.0, 1.0],
            "u_order": 2,
            "v_knots": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
            "v_order": 3,
            "weights": [[1.0, 1.0], [0.5**0.5, 0.5**0.5], [1.0, 1.0]],
            "discretization": discretization,
        }
    )
    return {"format": "hbg", "version": 3, "kind": "spline_patches", "symmetry": "xz_and_yz", "patches": patches}


def high_order_mesh(model, radius, draft, spans, shape=2):
    """고차 패치를 ``wec`` 메쉬에 넣습니다(1/4 대칭).

    - Shape 2: 엔진의 해석적 원통(옆면 + 바닥). 옆면은 둘레 x 높이 ``spans x spans``, 바닥은 둘레 x 반지름
      ``spans x max(1, spans // 2)`` 패치입니다.
    - Shape 1: ``hemisphere_hbg``(cad2bem 반구 패치 3개 + 원통 옆면 1개, 모두 ``spans x spans``).
    """
    if shape == 1:
        model.meshes.from_hbg("wec", hemisphere_hbg(radius, draft, spans))
        return
    order = (HIGH_ORDER_SPLINE, HIGH_ORDER_SPLINE, *HIGH_ORDER_GAUSS)
    model.meshes.analytic(
        name="wec",
        shape="circular_cylinder",
        discretization=[(spans, spans, *order), (spans, max(1, spans // 2), *order)],
        parts=["side", "bottom"],
        mapping="nonuniform",
        radius=float(radius),
        draft=float(draft),
        reference_length=1.0,
        symmetry="xz_and_yz",
    )


def check_solver_settings(hydro_solver, vertical_wall, opt_mode, wave_angle=0.0):
    """해석기와 벽 설정의 조합을 검증합니다. Capytaine은 개방 해역만, HydroBEM은 입사각 0만 지원합니다."""
    check_hydro_solver(hydro_solver)
    if hydro_solver == 3:
        if float(wave_angle) != 0 and opt_mode != 1:
            raise ValueError("HydroSolver 3 (HydroBEM) supports WaveAngle 0 only in this project.")
        import_hydrobem()
    if hydro_solver == 2:
        if opt_mode != 1 and vertical_wall:
            raise ValueError(
                "Capytaine supports the open sea only in this project: set VerticalWall to 0 "
                "(or use HydroSolver 1, WAMIT, for the vertical wall)."
            )
        import_capytaine()


def import_capytaine():
    try:
        import capytaine
    except ImportError as err:  # 선택 의존성
        raise ImportError("HydroSolver 2 needs Capytaine: pip install capytaine") from err
    return capytaine


def import_hydrobem():
    try:
        import hydrobem_gui
    except ImportError as err:  # 선택 의존성
        raise ImportError(
            "HydroSolver 3 needs HydroBEM: install the hydrobem_gui wheel (Windows x64, AVX2, Python 3.11+)."
        ) from err
    return hydrobem_gui


def solve_hydrodynamics(vector, config, positions=None, workspace_dir=None):
    """설계 벡터의 heave 수력 계수를 설정된 해석기로 계산합니다."""
    workspace_dir = workspace_dir or config.get("workspace_dir", DEFAULT_WORKSPACE)
    solver = config.get("hydro_solver") or DEFAULT_HYDRO_SOLVER
    if solver == 2:
        return capytaine_hydrodynamics(vector, config, positions)
    if solver == 3:
        return hydrobem_hydrodynamics(vector, config, positions, workspace_dir)
    write_wamit_inputs(vector, config, workspace_dir, positions=positions)
    run_wamit(workspace_dir, config.get("wamit_exe"))
    return read_wamit_hydro(workspace_dir, config["num_wecs"], RHO, GRAVITY)


# ---------------------------------------------------------------------------------------------------------------
# Capytaine (open sea)
# ---------------------------------------------------------------------------------------------------------------
def full_panels(quarter_panels):
    """1/4 모델 패널(x >= 0, y >= 0)을 x, y 대칭으로 펼친 전체 패널. 법선은 계속 물 쪽을 향합니다."""
    panels = []
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        for quad in quarter_panels:
            mirrored = [np.array([sx * p[0], sy * p[1], p[2]]) for p in quad]
            panels.append(mirrored[::-1] if sx * sy < 0 else mirrored)  # 한 번 뒤집으면 꼭짓점 순서도 뒤집기
    return panels


def panel_volume_and_waterplane(panels):
    """패널로 잠긴 부피와 수선면적을 구합니다(발산 정리, 법선은 물 쪽). WAMIT처럼 메쉬에 맞춘 값을 씁니다."""
    p = np.array(panels, dtype=float)
    area_vectors = 0.5 * np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 1])  # 물 쪽 법선 x 넓이
    centroids = p.mean(axis=1)
    volume = np.sum(centroids[:, 2] * area_vectors[:, 2])  # field (0, 0, z): 수선면(z = 0)은 0
    waterplane = -np.sum(area_vectors[:, 2])
    return float(volume), float(waterplane)


def frequency_list(config, radius, draft, shape):
    """WAMIT과 같은 주파수 목록(균일 또는 적응형)."""
    if check_freq_grid(config.get("freq_grid") or 0):
        return adaptive_omegas(radius, draft, config.get("omega_max"), shape)
    n_points, _ = omega_grid(config.get("omega_max"))
    return [round(0.5 + 0.05 * k, 6) for k in range(n_points)]


def capytaine_hydrodynamics(vector, config, positions=None, wave_direction=0.0):
    """Capytaine으로 개방 해역의 N기 heave 계수를 계산합니다.

    - 메쉬: 이 프로젝트의 1/4 모델 메쉬를 펼쳐 각 WEC 위치로 옮깁니다(WAMIT과 같은 패널).
    - 자유도: WEC마다 그 WEC 패널만 위아래로 움직이는 heave 하나.
    - 풀이: ``method="direct"``(모서리가 있는 형상에서 indirect보다 정확), 주파수·문제는 ``NCPU``개 프로세스로 나눔.
    - Capytaine은 ``exp(-i omega t)`` 기준이라 가진력을 켤레 복소수로 바꿔 WAMIT 기준(``HydroData``)에 맞춥니다.
    """
    cpt = import_capytaine()
    if wall_enabled(config):
        raise ValueError("Capytaine supports the open sea only in this project (vertical_wall must be off).")
    check_wave_angle(config.get("wave_angle") or 0.0, False, config.get("opt_mode"))
    radius, draft, body_positions = resolve_geometry(vector, config, positions)
    shape = check_shape(config.get("shape") or DEFAULT_SHAPE)
    target = int(config.get("mesh_panels") or DEFAULT_QUARTER_PANELS)
    body = full_panels(build_mesh_panels(shape, radius, draft, target))
    volume, waterplane = panel_volume_and_waterplane(body)

    vertices, faces, owner = [], [], []
    for k, (x, y) in enumerate(body_positions):
        offset = np.array([x, y, 0.0])
        for quad in body:
            faces.append([len(vertices) + i for i in range(4)])
            vertices.extend(np.asarray(q) + offset for q in quad)
            owner.append(k)
    owner = np.array(owner)
    mesh = cpt.Mesh(vertices=np.array(vertices), faces=np.array(faces), name="wec_array")
    num = len(body_positions)
    dofs = {f"Heave_{k}": np.where((owner == k)[:, None], [0.0, 0.0, 1.0], 0.0) for k in range(num)}
    floating = cpt.FloatingBody(mesh=mesh, dofs=dofs, name="wec_array")

    omegas = frequency_list(config, radius, draft, shape)
    common = {"water_depth": float(config["depth"]), "rho": RHO, "g": GRAVITY}
    problems = []
    for w in omegas:
        problems += [cpt.RadiationProblem(body=floating, omega=w, radiating_dof=d, **common) for d in dofs]
        problems.append(cpt.DiffractionProblem(body=floating, omega=w, wave_direction=wave_direction, **common))
    n_jobs = max(1, int(config.get("ncpu") or 1))
    results = cpt.BEMSolver().solve_all(problems, method="direct", n_jobs=n_jobs, n_threads=1, progress_bar=False)
    data = cpt.assemble_dataset(results, hydrostatics=False)

    names = list(dofs)
    added = data["added_mass"].sel(radiating_dof=names, influenced_dof=names).transpose("omega", ...).values
    damping = data["radiation_damping"].sel(radiating_dof=names, influenced_dof=names).transpose("omega", ...).values
    force = data["excitation_force"].sel(influenced_dof=names).isel(wave_direction=0).transpose("omega", ...).values
    # added[w, i, j]: 자유도 j가 움직일 때 자유도 i에 걸리는 힘 (대칭 행렬이라 순서와 무관)
    return HydroData(
        omegas=np.asarray(data["omega"].values, dtype=float),
        added_mass=np.real(added),
        damping=np.real(damping),
        excitation=np.conj(force),
        mass=np.eye(num) * RHO * volume,
        stiffness=np.eye(num) * RHO * GRAVITY * waterplane,
    )


# ---------------------------------------------------------------------------------------------------------------
# HydroBEM (open sea or the wall at x = 0)
# ---------------------------------------------------------------------------------------------------------------
def hydrobem_threads(ncpu, num_frequencies):
    """``NCPU``개 스레드를 HydroBEM의 (주파수 스레드, 주파수 안 스레드)로 나눕니다.

    주파수 스레드는 주파수 수보다 많아도 쓸 데가 없으므로 ``min(NCPU, 주파수 수)``입니다. 남는 스레드는
    주파수 하나를 여러 스레드로 푸는 ``inner_threads``로 씁니다(NCPU 96, 주파수 51 -> 51 x 1; NCPU 102 -> 51 x 2).
    NCPU가 주파수 수보다 작으면 이전과 같습니다(``NCPU`` x 1).
    """
    ncpu = max(1, int(ncpu))
    frequency_threads = max(1, min(ncpu, int(num_frequencies)))
    return frequency_threads, max(1, ncpu // frequency_threads)


def hydrobem_heave_arrays(results, num):
    """HydroBEM 결과에서 N기 heave의 부가질량·방사감쇠 [F, N, N]과 diffraction 가진력 [F, N]을 꺼냅니다.

    ``results.coefficient``는 부를 때마다 모델의 좌표 목록을 다시 만들어(5기에서 한 번에 약 0.1 s, 평가 하나에
    55번) 해석 시간보다 오래 걸렸습니다. 여기서는 전체 배열(``added_mass`` [F, D, K], ``excitation_diffraction``
    [F, H, D])을 한 번 읽고, ``coordinates``(행: 물체, 종류, 모드 1..6, 회전)에서 물체 k의 heave(종류 0, 모드 3)
    위치 D와 ``radiation_mode_ids``에서 그 방사 열 K를 찾아 고릅니다. 값은 ``coefficient``와 같습니다.
    """
    coords = np.asarray(results.quantity("coordinates"))
    rows = []
    for body in range(num):
        found = np.flatnonzero((coords[:, 0] == body) & (coords[:, 1] == 0) & (coords[:, 2] == 3))
        if found.size != 1:
            raise ValueError(f"HydroBEM results have no single heave coordinate for body {body}")
        rows.append(int(found[0]))
    ids = np.asarray(results.quantity("radiation_mode_ids"))
    columns = []
    for d in rows:
        found = np.flatnonzero(ids == d + 1)
        if found.size != 1:
            raise ValueError("HydroBEM results have no radiation column for a heave coordinate")
        columns.append(int(found[0]))
    pick = np.ix_(rows, columns)
    added = np.asarray(results.quantity("added_mass"))[:, pick[0], pick[1]].real.astype(float)
    damping = np.asarray(results.quantity("radiation_damping"))[:, pick[0], pick[1]].real.astype(float)
    force = np.asarray(results.quantity("excitation_diffraction"))[:, 0, rows].astype(complex)
    return added, damping, force


def hydrobem_hydrodynamics(vector, config, positions=None, workspace_dir=None):
    """HydroBEM으로 N기 heave 계수를 계산합니다 (WAMIT과 같은 GDF 메쉬, 주파수 목록, 벽 설정).

    - 메쉬: ``write_gdf_if_needed``가 WAMIT과 같은 1/4 모델 GDF를 작업 폴더에 씁니다(``ISX = ISY = 1`` 대칭).
    - 자유도: WEC마다 heave 하나. 가진력은 diffraction(입사파 + 산란파 압력 적분)이며 WAMIT과 같은 위상 기준입니다.
    - 병렬: ``hydrobem_threads``로 NCPU를 주파수 스레드(최대 주파수 수)와 주파수 안 스레드로 나눕니다.
      ``Workers`` x ``NCPU``가 코어 수를 넘지 않게 하세요.
    - 입사각은 0만 지원합니다. 질량과 복원 강성은 HydroBEM의 메쉬 기준 정수압 값(WAMIT .out/.hst와 같은 값)입니다.
    - ``high_order_spans`` > 0이면 GDF 대신 고차 패치로 풉니다(``high_order_mesh``; Shape 2 해석적 원통,
      Shape 1 cad2bem 반구 패치). 이때 ``MeshPanels``는 쓰지 않습니다.
    """
    hb = import_hydrobem()
    radius, draft, body_positions = resolve_geometry(vector, config, positions)
    shape = check_shape(config.get("shape") or DEFAULT_SHAPE)
    if float(config.get("wave_angle") or 0.0) != 0 and config.get("opt_mode") != 1:
        raise ValueError("HydroSolver 3 (HydroBEM) supports WaveAngle 0 only in this project.")
    spans = check_high_order(int(config.get("high_order_spans") or 0), 3, shape)

    omegas = np.array(frequency_list(config, radius, draft, shape), dtype=float)
    num = len(body_positions)
    model = hb.Model()
    if spans:
        high_order_mesh(model, radius, draft, spans, shape)
    else:
        workspace_dir = workspace_dir or config.get("workspace_dir", DEFAULT_WORKSPACE)
        os.makedirs(workspace_dir, exist_ok=True)
        gdf_path = os.path.join(workspace_dir, "wec.gdf")
        write_gdf_if_needed(gdf_path, radius, draft, int(config.get("mesh_panels") or DEFAULT_QUARTER_PANELS), shape)
        model.meshes.load("wec", gdf_path)
    for k, (x, y) in enumerate(body_positions):
        model.bodies.add(
            name=f"b{k}",
            mesh="wec",
            position=[float(x), float(y), 0.0],
            rotation_center=[0.0, 0.0, 0.0],
            modes=["heave"],
            interior_surface="none",
        )
    model.environment.update(
        depth=float(config["depth"]),
        density=RHO,
        gravity=GRAVITY,
        domain="x_wall" if wall_enabled(config) else "open_sea",
        frequency_input="omegas",
        omegas=omegas,
        headings=[0.0],
    )
    model.first_order.update(radiation=True, diffraction=True, motion=False)
    frequency_threads, inner_threads = hydrobem_threads(int(config.get("ncpu") or 1), len(omegas))
    model.options.update(frequency_threads=frequency_threads, inner_threads=inner_threads, higher_order=bool(spans))
    results = model.solve()

    added, damping, force = hydrobem_heave_arrays(results, num)
    volume = np.asarray(results.quantity("hydrostatics_volume"), dtype=float).reshape(-1)
    stiffness = np.asarray(results.quantity("hydrostatics_stiffness"), dtype=float).reshape(num, 6, 6)
    return HydroData(
        omegas=omegas,
        added_mass=added,
        damping=damping,
        excitation=force,
        mass=np.diag(RHO * volume),
        stiffness=np.diag(stiffness[:, 2, 2]),
    )
