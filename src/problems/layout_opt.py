from src.utils.mapper import decode_symmetric_positions
from src.utils.geometry import check_min_distance
from src.physics import write_wamit_inputs, run_wamit, calculate_rao_matrix, calculate_power


def get_layout_config(constraints_dict, params_dict, num_wecs, env_data, wamit_data, wave_spec:int):
    lower_bounds = []
    upper_bounds = []

    # 중심 WEC - 항상 존재하며 Y=0으로 고정되므로 X 바운드만 추가
    lower_bounds.append(float(constraints_dict['WEC1_XMin']))
    upper_bounds.append(float(constraints_dict['WEC1_XMax']))

    # 첫 번째 사이드 쌍 (WEC2) - 3기 이상일 때 추가
    if num_wecs >= 3:
        lower_bounds.extend([float(constraints_dict['WEC2_XMin']), float(constraints_dict.get('WEC2_YMin', 0.0))])
        upper_bounds.extend([float(constraints_dict['WEC2_XMax']), float(constraints_dict.get('WEC2_YMax', 30.0))])

    # 두 번째 사이드 쌍 (WEC3) - 5기일 때 추가
    if num_wecs == 5:
        lower_bounds.extend([float(constraints_dict['WEC3_XMin']), float(constraints_dict.get('WEC3_YMin', 0.0))])
        upper_bounds.extend([float(constraints_dict['WEC3_XMax']), float(constraints_dict.get('WEC3_YMax', 30.0))])

    return {
        'dimensions': len(lower_bounds), # 1기: 1차원, 3기: 3차원, 5기: 5차원
        'bounds': [lower_bounds, upper_bounds],
        'num_wecs': num_wecs,
        'fixed_radius': float(params_dict['FixedRadius']),
        'fixed_draft': float(params_dict['FixedDraft']),
        'min_spacing': float(params_dict['MinSpacing']),
        'opt_mode': 2,
        'site_name': env_data['SiteName'],
        'hs': env_data['Hs'],
        'tp': env_data['Tp'],
        'gamma': env_data['Gamma'],
        'depth': env_data['Depth'],
        'ncpu': wamit_data['NCPU'],
        'ram': wamit_data['RAMGBMAX'],
        'wave_spec': wave_spec
    }

def evaluate_layout(vector, config):
    '''
    알고리즘이 던져준 1차원 배열을 평가하여 발전량을 반환함
    '''
    # 1차원 배열을 물리적 좌표 리스트로 해독
    positions = decode_symmetric_positions(vector, config['num_wecs'])

    # 기하학적 제약 조건 검사
    radius = config['fixed_radius']
    dist_violation = check_min_distance(positions, radius, config['min_spacing'])
    
    if dist_violation > 0:
        return -1e6 * dist_violation, [0.0] * config['num_wecs']  # 큰 패널티 반환
    
    config['positions'] = positions
    workspace_dir = 'workspace'
    write_wamit_inputs(vector, config, workspace_dir)
    run_wamit(workspace_dir)
    rao_results = calculate_rao_matrix(workspace_dir, config['num_wecs'])
    total_power, individual_powers = calculate_power(rao_results, config)

    return total_power, individual_powers
    