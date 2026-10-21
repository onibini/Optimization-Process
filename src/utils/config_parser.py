"""config.cfg 파서.

설정 파일의 각 줄은 ``값  변수명  - 주석`` 형태입니다. 예::

    [Constraints]
    -5.0  WEC1_XMin     - [Float] Minimum X position for WEC 1

값과 변수명은 공백으로 구분된 앞의 두 토큰이며, 세 번째 토큰부터는 주석으로 취급합니다.
이전 구현은 ``line.split('-')`` 로 주석을 잘랐기 때문에 ``-5.0`` 같은 음수 값이 있는 줄이
통째로 무시되고, 나중에 KeyError로 이어졌습니다.
"""


class ConfigParseError(ValueError):
    """설정 파일 형식이 잘못되었을 때 발생합니다."""


def parse_wec_cfg(filepath):
    """'값  변수명  - 주석' 형태의 설정 파일을 읽어 {섹션: {변수명: 값(str)}} 딕셔너리로 반환합니다."""
    config_dict = {}
    current_section = None

    with open(filepath, encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                config_dict[current_section] = {}
                continue

            if current_section is None:
                raise ConfigParseError(f"{filepath}:{line_no}: 섹션([...]) 밖에 값이 정의되어 있습니다: {line!r}")

            tokens = line.split()
            if len(tokens) < 2:
                raise ConfigParseError(f"{filepath}:{line_no}: '값 변수명' 형식이 아닙니다: {line!r}")

            val_str, key_str = tokens[0], tokens[1]
            section = config_dict[current_section]
            if key_str in section:
                raise ConfigParseError(
                    f"{filepath}:{line_no}: [{current_section}] 섹션에 '{key_str}'가 중복 정의되었습니다."
                )
            section[key_str] = val_str

    return config_dict
