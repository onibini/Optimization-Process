import numpy as np

def calculate_pierson_moskowitz(omega, Hs, Tp):
    '''
    유의파고와 피크주기를 바탕으로 스펙트럼 계산
    '''
    wp = 2.0 * np.pi / Tp

    w = np.maximum(omega, 1e-10)

    a = (5.0 / 16.0) * (Hs ** 2) * (wp ** 4)
    b = -1.25 * ((w / wp) ** -4)

    S_pm = a * (w ** -5) * np.exp(b)

    S_pm[omega == 0] = 0.0
    return S_pm

def get_jonswap_spectrum(omega, Hs, Tp, gamma, spec_type):
    """
    spec_type에 따라 다른 Form의 JONSWAP 스펙트럼을 반환합니다.
    - spec_type == 1: ITTC / DNV Standard
    - spec_type == 2: Goda (1988) High-Precision
    """
    wp = 2.0 * np.pi / Tp
    w = np.maximum(omega, 1e-10)
    S = np.zeros_like(omega)
    
    if spec_type == 1:
        # 1. ITTC 방식
        a = (5.0 / 16.0) * (Hs ** 2) * (wp ** 4)
        b = -1.25 * ((w / wp) ** -4)
        S_pm = a * (w ** -5) * np.exp(b)
        
        A_gamma = 1.0 - 0.287 * np.log(gamma)
        sigma = np.where(w <= wp, 0.07, 0.09)
        power_term = np.exp(-0.5 * (((w - wp) / (sigma * wp)) ** 2))
        S = A_gamma * S_pm * (gamma ** power_term)
        
    elif spec_type == 2:
        # 2. Goda 방식
        sigma = np.where(w <= wp, 0.07, 0.09)
        r = np.exp(-((w - wp)**2) / (2 * sigma**2 * wp**2))

        beta_denominator = 0.23 + 0.0336 * gamma - 0.185 * (1.9 + gamma)**-1
        beta = (0.0624 / beta_denominator) * (1.094 - 0.01915 * np.log(gamma))

        term1 = beta * (Hs ** 2 * wp ** 4) / (w ** 5)
        term2 = np.exp(-1.25 * (w / wp) ** -4)
        term3 = gamma ** r
        
        S = term1 * term2 * term3

    S[omega == 0] = 0.0
    return S