from src.physics import calculate_power, calculate_rao_matrix, run_wamit, write_wamit_inputs
from src.physics.wamit_handler import DEFAULT_WORKSPACE
from src.utils.geometry import check_min_distance, penalty_result
from src.utils.mapper import decode_symmetric_positions
from src.utils.validation import require_positive, resolve_step_sizes, validate_design_bounds


def get_layout_config(constraints_dict, params_dict, num_wecs, env_data, wamit_data, wave_spec: int):
    if num_wecs not in (1, 3, 5):
        raise ValueError(f"NumWECs must be 1, 3 or 5, got {num_wecs}")

    # 중심 WEC - 항상 존재하며 Y=0으로 고정되므로 X 바운드만 추가
    # 사이드 쌍(WEC2, WEC3) - 3기 이상이면 WEC2, 5기이면 WEC3까지 (x, y) 바운드 추가
    var_names = ["WEC1_X"]
    if num_wecs >= 3:
        var_names += ["WEC2_X", "WEC2_Y"]
    if num_wecs == 5:
        var_names += ["WEC3_X", "WEC3_Y"]

    lower_bounds = [float(constraints_dict[f"{name}Min"]) for name in var_names]
    upper_bounds = [float(constraints_dict[f"{name}Max"]) for name in var_names]
    validate_design_bounds(var_names, lower_bounds, upper_bounds)
    step_size = resolve_step_sizes(constraints_dict, var_names, lower_bounds, upper_bounds)

    return {
        "dimensions": len(lower_bounds),  # 1기: 1차원, 3기: 3차원, 5기: 5차원
        "bounds": [lower_bounds, upper_bounds],
        "step_size": step_size,
        "num_wecs": num_wecs,
        "fixed_radius": require_positive("FixedRadius", params_dict["FixedRadius"]),
        "fixed_draft": require_positive("FixedDraft", params_dict["FixedDraft"]),
        "min_spacing": require_positive("MinSpacing", params_dict["MinSpacing"]),
        "opt_mode": 2,
        "site_name": env_data["SiteName"],
        "hs": env_data["Hs"],
        "tp": env_data["Tp"],
        "gamma": env_data["Gamma"],
        "depth": env_data["Depth"],
        "ncpu": wamit_data["NCPU"],
        "ram": wamit_data["RAMGBMAX"],
        "wamit_exe": wamit_data.get("WAMITPath"),
        "mesh_panels": wamit_data.get("MeshPanels"),
        "solver": wamit_data.get("Solver"),
        "omega_max": wamit_data.get("OmegaMax"),
        "freq_grid": wamit_data.get("FreqGrid"),
        "workers": wamit_data.get("Workers", 1),
        "shape": wamit_data.get("Shape", 1),
        "wave_spec": wave_spec,
    }


def evaluate_layout(vector, config):
    """
    알고리즘이 던져준 1차원 배열을 평가하여 발전량을 반환함
    """
    # 1차원 배열을 물리적 좌표 리스트로 해독
    positions = decode_symmetric_positions(vector, config["num_wecs"])

    # 기하학적 제약 조건 검사
    radius = config["fixed_radius"]
    dist_violation = check_min_distance(positions, radius, config["min_spacing"])

    if dist_violation > 0:
        return penalty_result(dist_violation, config["num_wecs"])  # WAMIT 없이 패널티 반환

    workspace_dir = config.get("workspace_dir", DEFAULT_WORKSPACE)
    write_wamit_inputs(vector, config, workspace_dir, positions=positions)
    run_wamit(workspace_dir, config.get("wamit_exe"))
    rao_results = calculate_rao_matrix(workspace_dir, config["num_wecs"])
    total_power, individual_powers = calculate_power(rao_results, config)

    return total_power, individual_powers
