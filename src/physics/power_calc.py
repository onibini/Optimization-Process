import numpy as np
from scipy.integrate import simpson
from src.physics.wave_spectrum import get_jonswap_spectrum

def calculate_power(rao_results, config):
    """
    RAO 결과와 해양 스펙트럼(JONSWAP)을 심슨 법칙으로 적분하여 최종 발전량을 산출합니다.
    """

    # 1. 해양 환경 데이터 추출
    hs = float(config['hs'])  # Significant Wave Height (m)
    tp = float(config['tp'])  # Peak Period (s)
    depth = float(config['depth'])  # Water Depth (m)
    gamma = float(config['gamma'])
    wave_spec = int(config['wave_spec'])

    # 2. 주파수 배열 추출
    omegas = np.array([res['omega'] for res in rao_results])

    # 3. JONSWAP 스펙트럼 계산
    S_wave = get_jonswap_spectrum(omegas, hs, tp, gamma, wave_spec)

    num_wecs = len(rao_results[0]['rao_abs'])
    total_power = 0.0
    individual_powers = []

    # 4. 각 WEC에 대해 RAO와 스펙트럼을 곱하여 발전량 계산
    for k in range(num_wecs):
        b_pto = rao_results[0]['b_pto'][k]  # PTO 감쇠 계수 (튜닝된 값)
        rao_abs = np.array([res['rao_abs'][k] for res in rao_results])  # RAO 진폭 배열

        # 주파수별 발전량 계산
        power_density = b_pto * (omegas**2) * (rao_abs**2) * S_wave
        wec_power = simpson(y=power_density, x=omegas)  # 심슨 법칙으로 적분

        individual_powers.append(wec_power)
        total_power += wec_power
    
    return total_power, individual_powers