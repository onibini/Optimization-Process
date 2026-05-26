import sys
from src.problems import *
from src.algorithms import run_de, run_pso, run_ga, run_cma_es
from src.utils.data_handler import load_env_data

def parse_wec_cfg(filepath):
    """
    '값  변수명  - 주석' 형태의 설정 파일을 읽어 딕셔너리로 반환합니다.
    """
    config_dict = {}
    current_section = None

    with open(filepath, 'r', encoding = 'utf-8') as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith('#'):
                continue
            if line.startswith('[') and line.endswith(']'):
                current_section = line.strip('[]')
                config_dict[current_section] = {}
                continue
            if current_section:
                data_part = line.split('-')[0].strip()
                tokens = data_part.split()

                if len(tokens) >= 2:
                    val_str = tokens[0]
                    key_str = tokens[1]
                    config_dict[current_section][key_str] = val_str
    
    return config_dict

def main():
    print("=== WEC Optimization Startd ===")

    # 1. Read config file
    cfg_path = "config.cfg"
    cfg = parse_wec_cfg(cfg_path)

    # 2. Separate sections
    opt_mode = int(cfg['Simulation']['OptMode'])
    algo_type = int(cfg['Simulation']['Algorithm'])
    wave_spec = int(cfg['Simulation']['WaveSpec'])
    num_wecs = int(cfg['WEC Parameters']['NumWECs'])

    # 3. OptMode에 따른 문제 세팅
    raw_constraints = cfg['Constraints']
    raw_wec_params = cfg['WEC Parameters']

    site_id = int(cfg['Environment']['SiteID'])
    env_data = load_env_data(site_id)
    print(f"해양 환경: [{env_data['SiteName']}] - Hs: {env_data['Hs']} m, Tp: {env_data['Tp']} s, Depth: {env_data['Depth']} m")

    # 4. WAMIT 설정 로드
    ncpu = int(cfg['WAMIT Settings']['NCPU'])
    ram = int(cfg['WAMIT Settings']['RAMGBMAX'])
    wamit_data = {'NCPU': ncpu, 'RAMGBMAX': ram}

    if opt_mode == 1:
        print(f"Mode: [Geometry Optimization] - Number of WEC: 1")
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
    
    # 4. Algorithm 선택 및 최적화 실행
    pop_size = int(cfg['AlgorithmSettings']['PopSize'])
    max_iter = int(cfg['AlgorithmSettings']['MaxIter'])
    algo_settings = cfg['AlgorithmSettings']

    best_x, best_f = None, None

    if algo_type == 1:
        print("Algorithm: [Differential Evolution]")
        F = float(algo_settings['F'])
        CR = float(algo_settings['CR'])
        best_x, best_f = run_de(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            F=F,
            CR=CR
        )

    elif algo_type == 2:
        print("Algorithm: [Particle Swarm Optimization]")
        w = float(algo_settings['w'])
        c1 = float(algo_settings['c1'])
        c2 = float(algo_settings['c2'])
        best_x, best_f = run_pso(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            w=w,
            c1=c1,
            c2=c2
        )

    elif algo_type == 3:
        print("Algorithm: [Genetic Algorithm]")
        mutation_rate = float(algo_settings['MutationRate'])
        best_x, best_f = run_ga(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter,
            mutation_rate=mutation_rate
        )

    elif algo_type == 4:
        print("Algorithm: [CMA-ES]")
        best_x, best_f = run_cma_es(
            config=problem_config,
            eval_func=eval_func,
            pop_size=pop_size,
            max_iter=max_iter
        )
    else:
        print("Error: Invalid Algorithm type in config file.")
        sys.exit(1)

if __name__ == "__main__":
    main()