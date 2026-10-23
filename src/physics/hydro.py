"""해석기(WAMIT, Capytaine 등)가 돌려주는 heave 수력 계수의 공통 형식.

RAO와 발전량 계산(``rao_calc.rao_from_hydro``, ``power_calc``)은 이 형식만 보므로 해석기와 독립입니다.
"""

from dataclasses import dataclass

import numpy as np


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
