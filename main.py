import sys

import numpy as np

from src.algorithms import run_cma_es, run_de, run_depso, run_ga, run_pso
from src.physics.mesh_axisymmetric_shape import (
    DEFAULT_QUARTER_PANELS,
    DEFAULT_SHAPE,
    MIN_QUARTER_PANELS,
    SHAPE_CYLINDER,
    SHAPES,
    check_shape,
    total_draft,
)
from src.physics.wamit_handler import (
    DEFAULT_OMEGA_MAX,
    DEFAULT_SOLVER,
    check_freq_grid,
    check_solver,
    highest_heave_omega0,
    omega_grid,
)
from src.physics.wave_spectrum import DEFAULT_WAVE_SPEC, WAVE_SPECTRA, check_wave_spec
from src.problems import (
    evaluate_joint,
    evaluate_layout,
    evaluate_shape,
    get_joint_config,
    get_layout_config,
    get_shape_config,
)
from src.utils import decode_symmetric_positions
from src.utils.config_parser import parse_wec_cfg
from src.utils.data_handler import load_env_data

__all__ = ["main", "parse_wec_cfg", "print_result"]


def print_result(best_x, best_f, config):
    """최적 설계를 사람이 읽기 쉬운 형태로 출력합니다."""
    print("\n=== Optimization Finished ===")
    if best_x is None or not np.isfinite(best_f):
        print("유효한 해를 찾지 못했습니다.")
        return

    best_x = np.asarray(best_x, dtype=float)
    print(f"Best fitness : {best_f / 1000:,.4f} kW")
    print(f"Best vector  : {np.round(best_x, 6).tolist()}")

    opt_mode = config["opt_mode"]
    if opt_mode in (1, 3):
        radius, draft = best_x[0], best_x[1]
        layout_vars = best_x[2:]
    else:
        radius, draft = config["fixed_radius"], config["fixed_draft"]
        layout_vars = best_x

    # 원통 + 반구: Draft는 원통부 길이, 총 흘수 D + R. 원통: Draft가 곧 총 흘수.
    shape = config.get("shape") or DEFAULT_SHAPE
    print(f"Shape        : {SHAPES[shape]}")
    print(f"Radius R     : {radius:.3f} m")
    if shape == SHAPE_CYLINDER:
        print(f"Draft D      : {draft:.3f} m  (total draft)")
    else:
        print(f"Draft D (cyl): {draft:.3f} m  (total draft D+R = {total_draft(shape, radius, draft):.3f} m)")

    if opt_mode in (2, 3):
        positions = decode_symmetric_positions(layout_vars, config["num_wecs"])
        for idx, (x, y) in enumerate(positions, start=1):
            print(f"  Body {idx}: x = {x:8.3f} m, y = {y:8.3f} m")


def main(cfg_path="config.cfg"):
    print("=== WEC Optimization Started ===")

    # 1. Read config file
    cfg = parse_wec_cfg(cfg_path)

    # 2. Separate sections
    opt_mode = int(cfg["Simulation"]["OptMode"])
    algo_type = int(cfg["Simulation"]["Algorithm"])
    try:
        wave_spec = check_wave_spec(int(cfg["Simulation"].get("WaveSpec", DEFAULT_WAVE_SPEC)))
    except ValueError as err:
        print(f"Error: {err}")
        sys.exit(1)
    num_wecs = int(cfg["WEC Parameters"]["NumWECs"])
    try:
        shape = check_shape(int(cfg["WEC Parameters"].get("Shape", DEFAULT_SHAPE)))
    except ValueError as err:
        print(f"Error: {err}")
        sys.exit(1)

    # 3. OptMode에 따른 문제 세팅
    raw_constraints = cfg["Constraints"]
    raw_wec_params = cfg["WEC Parameters"]

    site_id = int(cfg["Environment"]["SiteID"])
    env_data = load_env_data(site_id)
    print(
        f"해양 환경: [{env_data['SiteName']}] - Hs: {env_data['Hs']} m, "
        f"Tp: {env_data['Tp']} s, Depth: {env_data['Depth']} m, Spectrum: {WAVE_SPECTRA[wave_spec]}"
    )

    # 4. WAMIT 설정 로드
    ncpu = int(cfg["WAMIT Settings"]["NCPU"])
    ram = int(cfg["WAMIT Settings"]["RAMGBMAX"])
    mesh_panels = int(cfg["WAMIT Settings"].get("MeshPanels", DEFAULT_QUARTER_PANELS))
    if mesh_panels < MIN_QUARTER_PANELS:
        print(f"Error: MeshPanels must be >= {MIN_QUARTER_PANELS}, got {mesh_panels}.")
        sys.exit(1)
    try:
        solver = check_solver(int(cfg["WAMIT Settings"].get("Solver", DEFAULT_SOLVER)))
        omega_max = float(cfg["WAMIT Settings"].get("OmegaMax", DEFAULT_OMEGA_MAX))
        n_omega, omega_top = omega_grid(omega_max)
        freq_grid = check_freq_grid(int(cfg["WAMIT Settings"].get("FreqGrid", 0)))
        workers = int(cfg["WAMIT Settings"].get("Workers", 1))
        if workers < 1:
            raise ValueError(f"Workers must be >= 1, got {workers}")
    except ValueError as err:
        print(f"Error: {err}")
        sys.exit(1)
    grid_text = "adaptive frequencies around the heave resonance" if freq_grid else f"{n_omega} frequencies"
    print(f"WAMIT: Solver={solver}, {grid_text} up to {omega_top:g} rad/s, MeshPanels={mesh_panels}")
    print(f"WEC shape: {SHAPES[shape]}")
    if workers > 1:
        print(f"WAMIT: {workers} runs at the same time, NCPU={ncpu} each ({workers * ncpu} cores in total)")
    wamit_data = {
        "NCPU": ncpu,
        "RAMGBMAX": ram,
        "WAMITPath": cfg["WAMIT Settings"].get("WAMITPath"),
        "MeshPanels": mesh_panels,
        "Solver": solver,
        "OmegaMax": omega_max,
        "FreqGrid": freq_grid,
        "Workers": workers,
        "Shape": shape,
    }

    if opt_mode == 1:
        print("Mode: [Geometry Optimization] - Number of WEC: 1")
        problem_config = get_shape_config(raw_constraints, env_data, wamit_data, wave_spec)
        eval_func = evaluate_shape

    elif opt_mode == 2:
        print(f"Mode: [Layout Optimization] - Number of WEC: {num_wecs}")
        problem_config = get_layout_config(raw_constraints, raw_wec_params, num_wecs, env_data, wamit_data, wave_spec)
        eval_func = evaluate_layout

    elif opt_mode == 3:
        print(f"Mode: [Geometry and Layout Optimization] - Number of WEC: {num_wecs}")
        problem_config = get_joint_config(raw_constraints, raw_wec_params, num_wecs, env_data, wamit_data, wave_spec)
        eval_func = evaluate_joint

    else:
        print("Error: Invalid OptMode in config file.")
        sys.exit(1)

    # 공진이 주파수 격자 위에 있는 설계가 탐색 범위에 있으면 알림 (PTO 감쇠가 격자 끝에서 정해짐)
    if opt_mode == 2:
        radius_min, draft_min = problem_config["fixed_radius"], problem_config["fixed_draft"]
    else:
        radius_min, draft_min = problem_config["bounds"][0][0], problem_config["bounds"][0][1]
    w0_max = highest_heave_omega0(shape, radius_min, draft_min)
    if w0_max > omega_top:
        print(
            f"Warning: the smallest designs resonate near {w0_max:.2f} rad/s, above the frequency grid "
            f"({omega_top:g} rad/s). Their PTO damping is then taken at the end of the grid. "
            f"Raise OmegaMax to about {1.1 * w0_max:.1f} or raise DraftMin/RadiusMin."
        )

    # 5. Algorithm 선택 및 최적화 실행
    pop_size = int(cfg["AlgorithmSettings"]["PopSize"])
    max_iter = int(cfg["AlgorithmSettings"]["MaxIter"])
    algo_settings = cfg["AlgorithmSettings"]

    de_update = "generation" if int(algo_settings.get("DEUpdate", 0)) == 1 else "immediate"
    batch_algorithms = {3, 4} | ({1} if de_update == "generation" else set())
    if workers > 1 and algo_type not in batch_algorithms:
        print(
            "Warning: Workers > 1 only speeds up the initial population for this algorithm "
            "(parallel generations: DE with DEUpdate=1, GA, CMA-ES)."
        )

    if algo_type == 1:
        print("Algorithm: [Differential Evolution]")
        if de_update == "generation":
            print("  DE update: generation-wise (whole generation evaluated together)")
        best_x, best_f = run_de(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            F=float(algo_settings["F"]),
            CR=float(algo_settings["CR"]),
            update=de_update,
        )

    elif algo_type == 2:
        print("Algorithm: [Particle Swarm Optimization]")
        best_x, best_f = run_pso(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            w=float(algo_settings["w"]),
            c1=float(algo_settings["c1"]),
            c2=float(algo_settings["c2"]),
        )

    elif algo_type == 3:
        print("Algorithm: [Genetic Algorithm]")
        best_x, best_f = run_ga(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            mutation_rate=float(algo_settings.get("MutationRate", 0.1)),
        )

    elif algo_type == 4:
        print("Algorithm: [CMA-ES]")
        best_x, best_f = run_cma_es(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            sigma_init=float(algo_settings.get("SigmaInit", 0.3)),
        )
    elif algo_type == 5:
        print("Algorithm: [DEPSO (DE + PSO)]")
        best_x, best_f = run_depso(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            F=float(algo_settings["F"]),
            CR=float(algo_settings["CR"]),
            w=float(algo_settings["w"]),
            c1=float(algo_settings["c1"]),
            c2=float(algo_settings["c2"]),
        )
    else:
        print("Error: Invalid Algorithm type in config file.")
        sys.exit(1)

    print_result(best_x, best_f, problem_config)
    return best_x, best_f


if __name__ == "__main__":
    main()
