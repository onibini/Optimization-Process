"""해석기(WAMIT, Capytaine 등)가 돌려주는 heave 수력 계수의 공통 형식.

RAO와 발전량 계산(``rao_calc.rao_from_hydro``, ``power_calc``)은 이 형식만 보므로 해석기와 독립입니다.
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

# 발전량은 A, B, F를 3차 스플라인으로 POWER_INTERP_STEP 간격까지 보간한 뒤 그 격자에서 PTO 감쇠, RAO,
# 발전량을 계산한다. 해석기 주파수(0.05 rad/s) 그대로 Simpson하던 방식(옛 PowerInterp 0)은
# 1기 공진 설계를 26%까지 많게 세어 2026-11-24에 지웠다.
# POWER_INTERP는 문제 설정과 평가 DB 지문에 남기는 값이다. 키가 없는 옛 기록(Simpson)과 구분된다.
POWER_INTERP = 1
POWER_INTERP_TEXT = "A, B, F cubic interpolation to 0.0025 rad/s, then Simpson"
POWER_INTERP_STEP = 0.0025


@dataclass
class HydroData:
    """N기 WEC의 heave 수력 계수 (차원 있는 값, SI 단위).

    시간 의존성은 WAMIT과 같은 ``exp(+i omega t)`` 기준입니다. 운동 방정식:
    ``(-omega^2 (M + A) + i omega B + C) X = F``.

    :ivar omegas: 각주파수 [rad/s], 오름차순, 모양 (n,)
    :ivar added_mass: 부가질량 [kg], 모양 (n, N, N)
    :ivar damping: 방사감쇠 [N s/m], 모양 (n, N, N)
    :ivar excitation: 단위 파고당 가진력 [N/m] (복소수), 모양 (n, N)
    :ivar mass: 질량 행렬 [kg], 모양 (N, N)
    :ivar stiffness: 복원 강성 행렬 [N/m], 모양 (N, N)
    """

    omegas: np.ndarray
    added_mass: np.ndarray
    damping: np.ndarray
    excitation: np.ndarray
    mass: np.ndarray
    stiffness: np.ndarray

    @property
    def num_wecs(self):
        return self.mass.shape[0]


def check_power_interp(value):
    """옛 설정 파일의 ``PowerInterp`` 줄을 검사합니다.

    줄이 없거나 1(보간)이면 통과하고, 0(Simpson)은 지워진 방식이라 오류입니다.
    """
    if value is None:
        return
    try:
        mode = int(value)
    except (TypeError, ValueError):
        mode = None
    if isinstance(value, bool) or mode != POWER_INTERP:
        raise ValueError(
            f"PowerInterp {value!r} is not supported: Simpson on the solver frequencies (PowerInterp 0) was removed "
            "on 2026-11-24 and the power is always integrated after interpolation. Delete the PowerInterp line."
        )


def refine_hydro(hydro, step=POWER_INTERP_STEP):
    """A, B, F(실수부, 허수부)를 3차 스플라인(not-a-knot)으로 ``step`` 간격의 격자에 보간합니다.

    격자는 해석기 주파수의 처음과 끝을 포함하는 등간격입니다(균일하지 않은 FreqGrid 1 격자도 됨). 계수는 주파수에 따라
    완만하므로 0.05 간격 자료로도 잘 맞고, 날카로운 RAO 봉우리는 보간한 격자에서 운동 방정식을 풀 때 다시 생깁니다.
    질량과 복원 강성은 그대로입니다.
    """
    omegas = np.asarray(hydro.omegas, dtype=float)
    lo, hi = float(omegas[0]), float(omegas[-1])
    fine = np.linspace(lo, hi, math.ceil((hi - lo) / step - 1e-9) + 1)

    def spline(values):
        return CubicSpline(omegas, np.asarray(values), axis=0)(fine)

    excitation = np.asarray(hydro.excitation)
    return HydroData(
        omegas=fine,
        added_mass=spline(hydro.added_mass),
        damping=spline(hydro.damping),
        excitation=spline(excitation.real) + 1j * spline(excitation.imag),
        mass=hydro.mass,
        stiffness=hydro.stiffness,
    )
