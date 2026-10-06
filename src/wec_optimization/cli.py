import argparse
from pathlib import Path

from wec_optimization.algorithms import run_cma_es, run_de, run_ga, run_pso
from wec_optimization.problems import (
    evaluate_joint,
    evaluate_layout,
    evaluate_shape,
    get_joint_config,
    get_layout_config,
    get_shape_config,
)
from wec_optimization.utils.data_handler import load_env_data


def parse_wec_cfg(filepath):
    """
    '값  변수명  - 주석' 형태의 설정 파일을 읽어 딕셔너리로 반환합니다.
    """
    config_dict = {}
    current_section = None

    with open(filepath, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line.strip("[]")
                config_dict[current_section] = {}
                continue
            if current_section:
                data_part = line.split(" - ", maxsplit=1)[0].strip()
                tokens = data_part.split()

                if len(tokens) >= 2:
                    val_str = tokens[0]
                    key_str = tokens[1]
                    config_dict[current_section][key_str] = val_str
                else:
                    raise ValueError(
                        f"Invalid configuration entry at {filepath}:{line_number}: {line}"
                    )

    return config_dict


def get_wamit_runtime_settings(settings):
    """Validate parallel settings and derive the CPU count for each WAMIT run."""
    available_cpus = int(settings.get("AvailableCPUs", settings.get("NCPU", 1)))
    concurrent_runs = int(settings.get("ConcurrentRuns", 1))
    if "AvailableRAMGB" in settings:
        available_ram = int(settings["AvailableRAMGB"])
    else:
        available_ram = int(settings.get("RAMGBMAX", 1)) * concurrent_runs
    keep_workspaces = int(settings.get("KeepWorkspaces", 0))
    if available_cpus < 1:
        raise ValueError("AvailableCPUs must be at least 1.")
    if not 1 <= concurrent_runs <= available_cpus:
        raise ValueError("ConcurrentRuns must be between 1 and AvailableCPUs.")
    if available_ram < concurrent_runs:
        raise ValueError("AvailableRAMGB must provide at least 1 GB per concurrent run.")
    if keep_workspaces not in {0, 1}:
        raise ValueError("KeepWorkspaces must be either 0 or 1.")

    return {
        "NCPU": max(1, available_cpus // concurrent_runs),
        "RAMGBMAX": available_ram // concurrent_runs,
        "ConcurrentRuns": concurrent_runs,
        "KeepWorkspaces": bool(keep_workspaces),
    }


def get_checkpoint_settings(settings):
    """Validate checkpoint configuration and return internal option names."""
    enabled = int(settings.get("EnableCheckpoint", 1))
    resume = int(settings.get("Resume", 1))
    save_every = int(settings.get("SaveEvery", 1))
    keep_completed = int(settings.get("KeepOnCompletion", 0))
    if enabled not in {0, 1} or resume not in {0, 1} or keep_completed not in {0, 1}:
        raise ValueError("Checkpoint switches must be either 0 or 1.")
    if save_every < 1:
        raise ValueError("Checkpoint SaveEvery must be at least 1.")
    return {
        "checkpoint_enabled": bool(enabled),
        "checkpoint_resume": bool(resume),
        "checkpoint_save_every": save_every,
        "checkpoint_keep_completed": bool(keep_completed),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Optimize WEC geometry and array layouts.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.cfg"),
        help="Path to the optimization configuration (default: config.cfg)",
    )
    args = parser.parse_args(argv)

    print("=== WEC Optimization Started ===")

    # 1. Read config file
    cfg_path = args.config
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
        f"해양 환경: [{env_data['SiteName']}] - Hs: {env_data['Hs']} m, Tp: {env_data['Tp']} s, Depth: {env_data['Depth']} m"
    )

    # 4. WAMIT 설정 로드
    wamit_settings = cfg["WAMIT Settings"]
    try:
        wamit_data = get_wamit_runtime_settings(wamit_settings)
    except ValueError as error:
        parser.error(str(error))
    print(
        f"WAMIT parallelism: {wamit_data['ConcurrentRuns']} concurrent runs, "
        f"{wamit_data['NCPU']} CPU(s) and {wamit_data['RAMGBMAX']} GB RAM per run"
    )

    if opt_mode == 1:
        print("Mode: [Geometry Optimization] - Number of WEC: 1")
        problem_config = get_shape_config(raw_constraints, env_data, wamit_data, wave_spec)
        eval_func = evaluate_shape

    elif opt_mode == 2:
        print(f"Mode: [Layout Optimization] - Number of WEC: {num_wecs}")
        problem_config = get_layout_config(
            raw_constraints, raw_wec_params, num_wecs, env_data, wamit_data, wave_spec
        )
        eval_func = evaluate_layout

    elif opt_mode == 3:
        print(f"Mode: [Geometry and Layout Optimization] - Number of WEC: {num_wecs}")
        problem_config = get_joint_config(
            raw_constraints, raw_wec_params, num_wecs, env_data, wamit_data, wave_spec
        )
        eval_func = evaluate_joint

    else:
        parser.error("OptMode must be one of 1 (shape), 2 (layout), or 3 (joint).")

    try:
        problem_config.update(get_checkpoint_settings(cfg.get("Checkpoint", {})))
    except ValueError as error:
        parser.error(str(error))

    # 4. Algorithm 선택 및 최적화 실행
    pop_size = int(cfg["AlgorithmSettings"]["PopSize"])
    max_iter = int(cfg["AlgorithmSettings"]["MaxIter"])
    algo_settings = cfg["AlgorithmSettings"]

    if algo_type == 1:
        print("Algorithm: [Differential Evolution]")
        F = float(algo_settings["F"])
        CR = float(algo_settings["CR"])
        best_x, best_f = run_de(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            F=F,
            CR=CR,
        )

    elif algo_type == 2:
        print("Algorithm: [Particle Swarm Optimization]")
        w = float(algo_settings["w"])
        c1 = float(algo_settings["c1"])
        c2 = float(algo_settings["c2"])
        best_x, best_f = run_pso(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            w=w,
            c1=c1,
            c2=c2,
        )

    elif algo_type == 3:
        print("Algorithm: [Genetic Algorithm]")
        mutation_rate = float(algo_settings.get("MutationRate", 0.1))
        best_x, best_f = run_ga(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            mutation_rate=mutation_rate,
        )

    elif algo_type == 4:
        print("Algorithm: [CMA-ES]")
        sigma_init = float(algo_settings.get("SigmaInit", 0.3))
        best_x, best_f = run_cma_es(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            sigma_init=sigma_init,
        )
    else:
        parser.error("Algorithm must be one of 1 (DE), 2 (PSO), 3 (GA), or 4 (CMA-ES).")

    print(f"Best objective: {best_f / 1000:,.4f} kW")
    print(f"Best design: {best_x}")
    return best_x, best_f
