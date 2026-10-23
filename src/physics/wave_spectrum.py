import numpy as np

WAVE_SPECTRA = {1: "JONSWAP (ITTC)", 2: "JONSWAP (Goda)", 3: "Pierson-Moskowitz"}
DEFAULT_WAVE_SPEC = 1


def check_wave_spec(spec_type):
    """WaveSpec 값을 검증합니다 (1, 2, 3)."""
    if isinstance(spec_type, bool) or spec_type not in WAVE_SPECTRA:
        raise ValueError(f"WaveSpec must be one of {sorted(WAVE_SPECTRA)} ({WAVE_SPECTRA}), got {spec_type!r}")
    return spec_type


def get_jonswap_spectrum(omega, Hs, Tp, gamma, spec_type):
    """
    spec_type에 따라 다른 형식의 파랑 스펙트럼 S(omega) [m^2 s/rad]를 반환합니다.
    - spec_type == 1: JONSWAP, ITTC / DNV 형식 (기본). 적분하면 입력 Hs와 0.2% 이내로 맞습니다(gamma = 1.4).
    - spec_type == 2: JONSWAP, Goda (1988) 근사식. gamma = 1.4에서 적분한 Hs가 입력보다 약 4% 커서
      발전량이 약 8% 크게 나옵니다(docs/reports/2026-10-23_06 보고서). 비교용으로 남겨 둡니다.
    - spec_type == 3: Pierson-Moskowitz (Hs, Tp로 쓴 Bretschneider 형식, 완전 발달 해). gamma는 쓰지 않으며
      ITTC 형식에서 gamma = 1인 것과 같습니다.
    """
    wp = 2.0 * np.pi / Tp
    w = np.maximum(omega, 1e-10)
    S = np.zeros_like(omega)

    if spec_type == 1:
        # 1. ITTC 방식
        a = (5.0 / 16.0) * (Hs**2) * (wp**4)
        b = -1.25 * ((w / wp) ** -4)
        S_pm = a * (w**-5) * np.exp(b)

        A_gamma = 1.0 - 0.287 * np.log(gamma)
        sigma = np.where(w <= wp, 0.07, 0.09)
        power_term = np.exp(-0.5 * (((w - wp) / (sigma * wp)) ** 2))
        S = A_gamma * S_pm * (gamma**power_term)

    elif spec_type == 2:
        # 2. Goda 방식
        sigma = np.where(w <= wp, 0.07, 0.09)
        r = np.exp(-((w - wp) ** 2) / (2 * sigma**2 * wp**2))

        beta_denominator = 0.23 + 0.0336 * gamma - 0.185 * (1.9 + gamma) ** -1
        beta = (0.0624 / beta_denominator) * (1.094 - 0.01915 * np.log(gamma))

        term1 = beta * (Hs**2 * wp**4) / (w**5)
        term2 = np.exp(-1.25 * (w / wp) ** -4)
        term3 = gamma**r

        S = term1 * term2 * term3
    elif spec_type == 3:
        # 3. Pierson-Moskowitz (Bretschneider): 5/16 Hs^2 wp^4 w^-5 exp(-1.25 (wp / w)^4)
        S = (5.0 / 16.0) * (Hs**2) * (wp**4) * (w**-5) * np.exp(-1.25 * ((w / wp) ** -4))
    else:
        raise ValueError(f"Invalid wave spectrum type: {spec_type}. Use 1 (JONSWAP ITTC), 2 (JONSWAP Goda) or 3 (PM).")

    S[omega == 0] = 0.0
    return S
