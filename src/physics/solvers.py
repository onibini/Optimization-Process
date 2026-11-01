"""수력 해석기(backend) 선택: WAMIT 또는 Capytaine.

``solve_hydrodynamics``가 설계 벡터와 문제 설정으로 heave 수력 계수(``HydroData``)를 돌려주고, 이후 RAO·발전량
계산은 해석기와 무관합니다.

- WAMIT (기본): 입력 파일을 쓰고 WAMIT을 실행해 출력을 읽습니다. 수직벽(``vertical_wall``)을 지원합니다.
- Capytaine (선택, ``pip install capytaine``): 오픈소스 Python BEM. 이 프로젝트에서는 **개방 해역만** 지원합니다.
"""

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
    write_wamit_inputs,
)

HYDRO_SOLVERS = {1: "WAMIT", 2: "Capytaine"}
DEFAULT_HYDRO_SOLVER = 1
RHO, GRAVITY = 1025.0, 9.80665


def check_hydro_solver(solver):
    """HydroSolver 값을 검증합니다 (1 WAMIT, 2 Capytaine)."""
    if isinstance(solver, bool) or solver not in HYDRO_SOLVERS:
        raise ValueError(f"HydroSolver must be one of {sorted(HYDRO_SOLVERS)} ({HYDRO_SOLVERS}), got {solver!r}")
    return solver


def check_solver_settings(hydro_solver, vertical_wall, opt_mode):
    """해석기와 벽 설정의 조합을 검증합니다. Capytaine은 개방 해역만 지원합니다."""
    check_hydro_solver(hydro_solver)
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


def solve_hydrodynamics(vector, config, positions=None, workspace_dir=None):
    """설계 벡터의 heave 수력 계수를 설정된 해석기로 계산합니다."""
    workspace_dir = workspace_dir or config.get("workspace_dir", DEFAULT_WORKSPACE)
    if (config.get("hydro_solver") or DEFAULT_HYDRO_SOLVER) == 2:
        return capytaine_hydrodynamics(vector, config, positions)
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
