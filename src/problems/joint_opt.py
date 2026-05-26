from .shape_opt import get_shape_config
from .layout_opt import get_layout_config
from src.utils import decode_symmetric_positions, check_min_distance
from src.physics import write_wamit_inputs, run_wamit, calculate_rao_matrix, calculate_power


def get_joint_config(constraints_dict, params_dict, num_wecs, env_data, wamit_data, wave_spec:int):
    '''
    항상 변수(2개)와 대칭 변수 (1~5개)를 합쳐 전체 최적화 범위를 정의
    최종 벡터 구조: [Radius, Draft, X1, X2, Y2, X3, Y3]
    '''
    
    # 형상 바운드 가져오기
    shape_cfg = get_shape_config(constraints_dict, env_data, wamit_data, wave_spec)

    # 배치 바운드 가져오기
    layout_cfg = get_layout_config(constraints_dict, params_dict, num_wecs, env_data, wamit_data, wave_spec)

    # 바운드 통합
    lower_bounds = shape_cfg['bounds'][0] + layout_cfg['bounds'][0]
    upper_bounds = shape_cfg['bounds'][1] + layout_cfg['bounds'][1]

    return {
        'dimensions': len(lower_bounds),
        'bounds': [lower_bounds, upper_bounds],
        'shape_dim': 2,
        'num_wecs': num_wecs,
        'min_spacing': float(params_dict['MinSpacing']),
        'opt_mode': 3,
        'wave_spec': wave_spec,
        'site_name': env_data['SiteName'],
        'hs': env_data['Hs'],
        'tp': env_data['Tp'],
        'gamma': env_data['Gamma'],
        'depth': env_data['Depth'],
        'ncpu': wamit_data['NCPU'],
        'ram': wamit_data['RAMGBMAX']
    }

def evaluate_joint(vector, config):
    '''
    알고리즘이 던져준 벡터를 해석하여 최종 발전량을 반환함
    '''

    # 벡터 분리
    shape_vars = vector[:config['shape_dim']]
    layout_vars = vector[config['shape_dim']:]

    radius, draft = shape_vars[0], shape_vars[1]

    # 좌표 해독
    positions = decode_symmetric_positions(layout_vars, config['num_wecs'])

    # 기하학적 제약 조건 검사
    dist_violation = check_min_distance(positions, radius, config['min_spacing'])
    if dist_violation > 0:
        return -1e6 * dist_violation, [0.0] * config['num_wecs']  # 큰 패널티 반환
    
    config['positions'] = positions
    
    workspace_dir = 'workspace'
    write_wamit_inputs(vector, config, workspace_dir)
    run_wamit(workspace_dir)
    rao_values = calculate_rao_matrix(workspace_dir, config['num_wecs'])
    total_power, individual_powers = calculate_power(rao_values, config)
    

    return total_power, individual_powers