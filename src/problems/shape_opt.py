from src.physics import calculate_power, calculate_rao_matrix, run_wamit, write_wamit_inputs
from src.physics.wamit_handler import DEFAULT_WORKSPACE
from src.utils.validation import resolve_step_sizes, validate_design_bounds


def get_shape_config(constraints_dict: dict, env_data: dict, wamit_data: dict, wave_spec: int):
    """
    main.py가 넘겨준 제약 조건 딕셔너리에서 형상 변수만 뽑아냅니다.
    단일 WEC이므로 변수는 반지름, 흘수 2개 입니다.
    """
    r_min = float(constraints_dict["RadiusMin"])
    r_max = float(constraints_dict["RadiusMax"])
    d_min = float(constraints_dict["DraftMin"])
    d_max = float(constraints_dict["DraftMax"])
    var_names = ["Radius", "Draft"]
    lower_bounds = [r_min, d_min]
    upper_bounds = [r_max, d_max]
    validate_design_bounds(var_names, lower_bounds, upper_bounds)
    step_size = resolve_step_sizes(constraints_dict, var_names, lower_bounds, upper_bounds)

    return {
        "dimensions": 2,
        "bounds": [lower_bounds, upper_bounds],
        "step_size": step_size,
        "num_wecs": 1,
        "opt_mode": 1,
        "wave_spec": wave_spec,
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
    }


def evaluate_shape(vector, config):
    """
    알고리즘이 vector를 입력하면 점수를 반환하는 함수입니다
    - vector: [radius_value, draft_value]
    """
    workspace_dir = config.get("workspace_dir", DEFAULT_WORKSPACE)

    write_wamit_inputs(vector, config, workspace_dir)
    run_wamit(workspace_dir, config.get("wamit_exe"))
    rao_data = calculate_rao_matrix(workspace_dir, config["num_wecs"])
    total_power, individual_powers = calculate_power(rao_data, config)

    return total_power, individual_powers
