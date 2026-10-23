import sys

import numpy as np

from src.algorithms import run_cma_es, run_de, run_depso, run_ga, run_pso
from src.physics.mesh_axisymmetric_shape import DEFAULT_QUARTER_PANELS, MIN_QUARTER_PANELS
from src.physics.wamit_handler import (
    DEFAULT_OMEGA_MAX,
    DEFAULT_SOLVER,
    check_freq_grid,
    check_solver,
    omega_grid,
)
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

    # Draft는 원통부 길이이며, 반구 바닥(반지름 R)이 그 아래에 붙으므로 총 흘수는 D + R
    print(f"Radius R     : {radius:.3f} m")
    print(f"Draft D (cyl): {draft:.3f} m  (total draft D+R = {draft + radius:.3f} m)")

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
    wave_spec = int(cfg["Simulation"]["WaveSpec"])
    num_wecs = int(cfg["WEC Parameters"]["NumWECs"])

    # 3. OptMode에 따른 문제 세팅
    raw_constraints = cfg["Constraints"]
    raw_wec_params = cfg["WEC Parameters"]

    site_id = int(cfg["Environment"]["SiteID"])
    env_data = load_env_data(site_id)
    print(
        f"해양 환경: [{env_data['SiteName']}] - Hs: {env_data['Hs']} m, "
        f"Tp: {env_data['Tp']} s, Depth: {env_data['Depth']} m"
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
    except ValueError as err:
        print(f"Error: {err}")
        sys.exit(1)
    grid_text = "adaptive frequencies around the heave resonance" if freq_grid else f"{n_omega} frequencies"
    print(f"WAMIT: Solver={solver}, {grid_text} up to {omega_top:g} rad/s, MeshPanels={mesh_panels}")
    wamit_data = {
        "NCPU": ncpu,
        "RAMGBMAX": ram,
        "WAMITPath": cfg["WAMIT Settings"].get("WAMITPath"),
        "MeshPanels": mesh_panels,
        "Solver": solver,
        "OmegaMax": omega_max,
        "FreqGrid": freq_grid,
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

    # 5. Algorithm 선택 및 최적화 실행
    pop_size = int(cfg["AlgorithmSettings"]["PopSize"])
    max_iter = int(cfg["AlgorithmSettings"]["MaxIter"])
    algo_settings = cfg["AlgorithmSettings"]

    if algo_type == 1:
        print("Algorithm: [Differential Evolution]")
        best_x, best_f = run_de(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            F=float(algo_settings["F"]),
            CR=float(algo_settings["CR"]),
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
