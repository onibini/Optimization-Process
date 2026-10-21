"""설계 변수 및 형상/격자 파라미터 검증.

이 프로젝트의 모든 설계 변수(반지름, 흘수, WEC 좌표)는 **양수(> 0)** 여야 합니다.
탐색 범위의 하한이 양수이면, 모든 후보 벡터는 격자 스냅 시 [하한, 상한] 안으로
클리핑되므로 최적화 도중에도 양수가 보장됩니다.
"""

import math
import warnings

# (상한-하한)/step 이 정수인지 판정할 때의 부동소수점 허용치
_GRID_TOLERANCE = 1e-9


class ConfigValidationError(ValueError):
    """설정 값이 허용 범위를 벗어났을 때 발생합니다."""


def _to_float(name, value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ConfigValidationError(f"'{name}' 값이 숫자가 아닙니다: {value!r}") from None
    if not math.isfinite(number):
        raise ConfigValidationError(f"'{name}' 값이 유한한 숫자가 아닙니다: {value!r}")
    return number


def require_positive(name, value):
    """value > 0 인지 확인하고 float로 반환합니다."""
    number = _to_float(name, value)
    if number <= 0:
        raise ConfigValidationError(f"'{name}'는 양수(> 0)여야 합니다. 현재 값: {number}")
    return number


def validate_design_bounds(names, lower_bounds, upper_bounds):
    """설계 변수 탐색 범위를 검증합니다: 0 < 하한 < 상한.

    :param names: 변수 이름 목록 (에러 메시지용, 예: ["RadiusMin/RadiusMax", ...])
    """
    if not (len(names) == len(lower_bounds) == len(upper_bounds)):
        raise ConfigValidationError("설계 변수 이름/하한/상한의 개수가 서로 다릅니다.")

    errors = []
    for name, lo, hi in zip(names, lower_bounds, upper_bounds):
        lo_f, hi_f = _to_float(f"{name} (min)", lo), _to_float(f"{name} (max)", hi)
        if lo_f <= 0:
            errors.append(f"  - {name}: 하한 {lo_f}은(는) 양수(> 0)여야 합니다.")
        if hi_f <= lo_f:
            errors.append(f"  - {name}: 상한 {hi_f}은(는) 하한 {lo_f}보다 커야 합니다.")
    if errors:
        raise ConfigValidationError("설계 변수 탐색 범위가 올바르지 않습니다:\n" + "\n".join(errors))


def resolve_step_sizes(constraints_dict, names, lower_bounds, upper_bounds):
    """설계 변수별 격자 간격(StepSize)을 config에서 읽어 검증합니다.

    변수 ``name``의 간격은 ``{name}Step`` 키(예: ``RadiusStep``, ``WEC2_YStep``)로 지정하고,
    없으면 공통 ``StepSize`` 값을 사용합니다.

    검증 규칙:
      - 간격 > 0
      - 간격 <= (상한 - 하한)
      - (상한 - 하한)이 간격으로 나누어떨어지지 않으면 경고 (실제 도달 가능한 상한을 알려줌)

    :return: 변수 순서대로의 간격 리스트 (float)
    """
    has_default = "StepSize" in constraints_dict
    steps = []
    for name, lo, hi in zip(names, lower_bounds, upper_bounds):
        key = f"{name}Step"
        if key in constraints_dict:
            step = require_positive(key, constraints_dict[key])
        elif has_default:
            step = require_positive("StepSize", constraints_dict["StepSize"])
        else:
            raise ConfigValidationError(f"'{key}' 또는 공통 'StepSize' 중 하나는 지정해야 합니다.")

        span = float(hi) - float(lo)
        ratio = span / step
        n_steps = math.floor(ratio + _GRID_TOLERANCE * max(1.0, abs(ratio)))
        if n_steps < 1:
            raise ConfigValidationError(f"'{key}' = {step}이(가) {name}의 탐색 범위 폭 {span:g}보다 큽니다.")
        if abs(ratio - round(ratio)) > _GRID_TOLERANCE * max(1.0, abs(ratio)):
            reachable_max = float(lo) + n_steps * step
            warnings.warn(
                f"{name}: 범위 폭 {span:g}이(가) 간격 {step:g}로 나누어떨어지지 않아 "
                f"실제 탐색 상한은 {reachable_max:g}입니다 (설정 상한 {float(hi):g}).",
                stacklevel=2,
            )
        steps.append(step)
    return steps
