import os
import sys

import numpy as np

from src.algorithms import run_cma_es, run_de, run_depso, run_ga, run_pso
from src.algorithms.de import DE_STRATEGIES, STALL_ACTIONS, update_block_size
from src.physics.hydro import POWER_INTERP_TEXT, check_power_interp
from src.physics.mesh_axisymmetric_shape import (
    DEFAULT_QUARTER_PANELS,
    DEFAULT_SHAPE,
    MIN_QUARTER_PANELS,
    SHAPE_CYLINDER,
    SHAPES,
    check_shape,
    total_draft,
)
from src.physics.rao_calc import DEFAULT_PTO_RULE, PTO_RULES, check_pto_rule
from src.physics.solvers import DEFAULT_HYDRO_SOLVER, HYDRO_SOLVERS, check_high_order, check_solver_settings
from src.physics.wamit_handler import (
    DEFAULT_OMEGA_MAX,
    DEFAULT_SOLVER,
    DEFAULT_WAVE_ANGLE,
    check_freq_grid,
    check_solver,
    check_wave_angle,
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

# config.cfg DEUpdate -> run_de(update=...)
DE_UPDATE_SWITCH = {0: "immediate", 1: "generation", 2: "block"}
MAX_SEED = 2**32 - 1


def resolve_seed(value):
    """설정의 Seed를 실제 시드로 바꿉니다. -1이면 새로 뽑아서, 어느 실행이든 로그의 값으로 다시 돌릴 수 있게 합니다."""
    seed = int(value)
    if seed == -1:
        return int(np.random.SeedSequence().entropy % (MAX_SEED + 1))
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"Seed must be -1 or between 0 and {MAX_SEED}, got {value}")
    return seed


def read_de_options(settings):
    """[AlgorithmSettings]의 DE 전용 옵션을 run_de 인자로 바꿉니다. 없으면 모두 논문과 같은 기본 동작입니다."""
    strategy = int(settings.get("DEStrategy", 0))
    if not 0 <= strategy < len(DE_STRATEGIES):
        raise ValueError(f"DEStrategy must be 0 or 1, got {strategy}")
    stall_gens = int(settings.get("StallGens", 0))
    if stall_gens < 0:
        raise ValueError(f"StallGens must be >= 0, got {stall_gens}")
    stall_action = int(settings.get("StallAction", 0))
    if not 0 <= stall_action < len(STALL_ACTIONS):
        raise ValueError(f"StallAction must be 0 or 1, got {stall_action}")
    local_search_evals = int(settings.get("LocalSearchEvals", 0))
    if local_search_evals < 0:
        raise ValueError(f"LocalSearchEvals must be >= 0, got {local_search_evals}")
    resume = settings.get("Resume", "0")
    return {
        "strategy": DE_STRATEGIES[strategy],
        "stall_gens": stall_gens,
        "stall_action": STALL_ACTIONS[stall_action],
        "local_search_evals": local_search_evals,
        "resume": None if resume == "0" else resume,
    }


def print_result(best_x, best_f, config):
    """최적 설계를 사람이 읽기 쉬운 형태로 출력합니다."""
    print("\n=== Optimization Finished ===")
    if best_x is None or not np.isfinite(best_f):
        print("No valid solution was found.")
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
        vertical_wall = int(cfg["WEC Parameters"].get("VerticalWall", 1))
        hydro_solver = int(cfg["Simulation"].get("HydroSolver", DEFAULT_HYDRO_SOLVER))
        wave_angle = float(cfg["WEC Parameters"].get("WaveAngle", DEFAULT_WAVE_ANGLE))
        check_solver_settings(hydro_solver, vertical_wall, opt_mode, wave_angle)
        high_order_spans = check_high_order(int(cfg["Simulation"].get("HighOrderSpans", 0)), hydro_solver, shape)
        check_wave_angle(wave_angle, opt_mode != 1 and bool(vertical_wall), opt_mode)
    except (ValueError, ImportError) as err:
        print(f"Error: {err}")
        sys.exit(1)

    # 3. OptMode에 따른 문제 세팅
    raw_constraints = cfg["Constraints"]
    raw_wec_params = cfg["WEC Parameters"]

    site_id = int(cfg["Environment"]["SiteID"])
    env_data = load_env_data(site_id)
    depth = float(cfg["Environment"].get("Depth", 0) or 0)
    if depth < 0 or depth != depth:
        print(f"Error: Depth must be 0 (the env_data.csv value) or a positive number, got {depth}")
        sys.exit(1)
    if depth > 0:
        env_data = dict(env_data, Depth=depth)
    print(
        f"Sea state: [{env_data['SiteName']}] - Hs: {env_data['Hs']} m, "
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
        pto_rule = check_pto_rule(int(cfg["Simulation"].get("PTORule", DEFAULT_PTO_RULE)))
        check_power_interp(cfg["Simulation"].get("PowerInterp"))  # 지워진 Simpson(0)을 적은 옛 설정은 오류
        eval_cache = int(cfg["WAMIT Settings"].get("EvalCache", 0))
        if eval_cache not in (0, 1):
            raise ValueError(f"EvalCache must be 0 or 1, got {eval_cache}")
    except ValueError as err:
        print(f"Error: {err}")
        sys.exit(1)
    grid_text = "adaptive frequencies around the heave resonance" if freq_grid else f"{n_omega} frequencies"
    print(f"WAMIT: Solver={solver}, {grid_text} up to {omega_top:g} rad/s, MeshPanels={mesh_panels}")
    print(f"WEC shape: {SHAPES[shape]}")
    wall_text = "vertical wall at x = 0" if opt_mode != 1 and vertical_wall else "open sea"
    if opt_mode != 1 and vertical_wall:
        wall_text += f", waves arriving at {wave_angle:g} deg from the wall normal"
    print(f"Hydrodynamics: {HYDRO_SOLVERS[hydro_solver]}, {wall_text}")
    if high_order_spans:
        print(f"HydroBEM higher order: {high_order_spans} spans per patch edge (MeshPanels is not used)")
    print(f"PTO damping: {PTO_RULES[pto_rule]}")
    print(f"Power integration: {POWER_INTERP_TEXT}")
    if opt_mode == 1 and wave_angle != 0:
        print("Note: WaveAngle is ignored in OptMode 1 (one axisymmetric WEC in the open sea).")
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
        "VerticalWall": vertical_wall,
        "WaveAngle": wave_angle,
        "HydroSolver": hydro_solver,
        "HighOrderSpans": high_order_spans,
        "PTORule": pto_rule,
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
    problem_config["eval_cache"] = bool(eval_cache)  # CachedEvaluator가 data/eval_db의 기록을 미리 불러옴

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
    try:
        de_update = DE_UPDATE_SWITCH[int(algo_settings.get("DEUpdate", 0))]
    except KeyError:
        print(f"Error: DEUpdate must be one of {sorted(DE_UPDATE_SWITCH)}, got {algo_settings.get('DEUpdate')}.")
        sys.exit(1)
    try:
        de_options = read_de_options(algo_settings)
        seed = resolve_seed(algo_settings.get("Seed", -1))
    except ValueError as err:
        print(f"Error: {err}")
        sys.exit(1)
    if de_options["resume"] and not os.path.isfile(de_options["resume"]):
        print(f"Error: Resume file not found: {de_options['resume']}")
        sys.exit(1)
    de_only_used = (
        de_options["strategy"] != DE_STRATEGIES[0]
        or de_options["stall_gens"]
        or de_options["local_search_evals"]
        or de_options["resume"]
    )
    if algo_type != 1 and de_only_used:
        print("Warning: DEStrategy, StallGens, LocalSearchEvals and Resume only apply to DE (Algorithm 1).")
    problem_config["seed"] = seed
    np.random.seed(seed)
    print(f"Random seed: {seed}")
    batch_algorithms = {3, 4} | ({1} if de_update != "immediate" else set())
    if workers > 1 and algo_type not in batch_algorithms:
        print(
            "Warning: Workers > 1 only speeds up the initial population for this algorithm "
            "(parallel generations: DE with DEUpdate=1 or 2, GA, CMA-ES)."
        )

    if algo_type == 1:
        print("Algorithm: [Differential Evolution]")
        if de_update == "generation":
            print("  DE update: generation-wise (whole generation evaluated together)")
        elif de_update == "block":
            print(f"  DE update: immediate in blocks of {update_block_size('block', pop_size, workers)} trials")
        best_x, best_f = run_de(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            F=float(algo_settings["F"]),
            CR=float(algo_settings["CR"]),
            update=de_update,
            **de_options,
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
