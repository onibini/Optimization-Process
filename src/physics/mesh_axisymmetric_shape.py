"""
축대칭 WEC의 WAMIT GDF 패널 메쉬 생성 모듈 (mesh_axisymmetric_shape.py)

물에 잠긴 형상의 1/4 모델(x >= 0, y >= 0)을 만듭니다. GDF 헤더에 ISX = ISY = 1을 기록하므로
WAMIT이 나머지 3/4를 대칭으로 처리합니다. 형상은 두 가지입니다(``SHAPES``).

1. 원통 + 반구 (기본): 원통 길이 D 아래에 반지름 R의 반구. 총 흘수 D + R.
    - 반구: 큐브드스피어(등각) 3개 패치. 극점에 삼각형 팬이 없어 패널이 거의 균일합니다.
    - 원통: 반구 적도와 같은 각도 분할(2n열)의 사각형 패널.
    - 1/4 모델 패널 수는 ``3 n^2 + 2 n n_z`` (n: 반구 분할 수, n_z: 원통 세로 분할 수).
2. 원통 (평평한 바닥): 반지름 R, 흘수 D. 총 흘수 D.
    - 옆면: 2n열 x n_z행의 사각형 패널.
    - 바닥: 1/4 원판을 가운데 정사각형(n x n)과, 그 두 변을 둘레 원호(0~45도, 45~90도, 각 n칸)에 잇는
      두 패치(각 n x m)로 나눔. 둘레에서 옆면과 같은 2n칸으로 맞물립니다.
    - 1/4 모델 패널 수는 ``n^2 + 2 n m + 2 n n_z``.

``target_panels``에 가장 가까운 분할이 선택됩니다.

32-bit WAMIT은 (기수 x 기당 패널 수)에 비례하는 메모리 한계가 있고 평가 시간도 패널 수의 약 2.5~3제곱으로
늘어나므로, 패널 수를 직접 지정할 수 있어야 합니다.
"""

import numpy as np

# 5기 배치 기준 전체 패널 약 600개, 평가 약 12초. 80은 일부 형상(가늘고 긴 형상, 넓고 얕은 형상, 촘촘한 배치)에서
# 총 파워 최대 11%, 개별 WEC 최대 18% 틀려서 120으로 정했습니다 (docs/reports/2026-10-22_01_mesh-panels-default-120.md).
DEFAULT_QUARTER_PANELS = 120
MIN_QUARTER_PANELS = 12  # n = 1이 만들 수 있는 가장 작은 격자 근처
_MAX_N = 60  # 후보 탐색 상한 (1/4 패널 약 11,000개 이상)
_ASPECT_WEIGHT = 0.15  # 원통 패널이 정사각형에서 벗어나는 정도에 대한 벌점 가중치
_CORE_FRACTION = 0.55  # 평평한 바닥: 가운데 정사각형의 한 변 / R

# 형상 번호 (config.cfg [WEC Parameters] Shape)
SHAPE_CYLINDER_HEMISPHERE = 1
SHAPE_CYLINDER = 2
SHAPES = {SHAPE_CYLINDER_HEMISPHERE: "cylinder + hemisphere", SHAPE_CYLINDER: "cylinder (flat bottom)"}
DEFAULT_SHAPE = SHAPE_CYLINDER_HEMISPHERE


def check_shape(shape):
    """Shape 값을 검증합니다 (1 원통 + 반구, 2 원통)."""
    if isinstance(shape, bool) or shape not in SHAPES:
        raise ValueError(f"Shape must be one of {sorted(SHAPES)} ({SHAPES}), got {shape!r}")
    return shape


def total_draft(shape, radius, draft):
    """총 흘수: 원통 + 반구는 D + R, 원통은 D."""
    return draft + radius if check_shape(shape) == SHAPE_CYLINDER_HEMISPHERE else draft


def displaced_volume(shape, radius, draft):
    """잠긴 부피(몸체 전체): 원통 + 반구 pi R^2 D + 2/3 pi R^3, 원통 pi R^2 D."""
    volume = np.pi * radius**2 * draft
    if check_shape(shape) == SHAPE_CYLINDER_HEMISPHERE:
        volume += 2.0 / 3.0 * np.pi * radius**3
    return float(volume)


def choose_grid(radius, draft_cylinder, target_panels):
    """목표 1/4 패널 수에 가장 가까운 (n, n_z)를 고릅니다.

    반구 분할 수 n마다 원통 세로 분할 수 n_z를 적도 패널 높이에 맞춘 값(0.5~2배 범위)에서 찾고,
    목표 대비 패널 수 오차와 원통 패널의 종횡비를 함께 최소화합니다.
    """
    best = None
    for n in range(1, _MAX_N + 1):
        nz_ideal = draft_cylinder * 4 * n / (np.pi * radius)
        for nz in range(max(1, int(nz_ideal * 0.5)), int(nz_ideal * 2) + 2):
            panels = count_panels(n, nz)
            aspect = (draft_cylinder / nz) / (np.pi * radius / (4 * n))
            aspect = max(aspect, 1.0 / aspect)
            score = abs(panels - target_panels) / target_panels + _ASPECT_WEIGHT * (aspect - 1.0)
            if best is None or score < best[0]:
                best = (score, n, nz)
    return best[1], best[2]


def count_panels(n, nz):
    """1/4 모델의 패널 수 (반구 3 n^2 + 원통 2 n n_z)."""
    return 3 * n * n + 2 * n * nz


def _outward(corners, draft_cylinder):
    """네 꼭짓점의 순서를 정해 (p3 - p1) x (p4 - p2)가 물 쪽(몸체 바깥)을 향하게 합니다."""
    p = [np.asarray(q, dtype=float) for q in corners]
    normal = np.cross(p[2] - p[0], p[3] - p[1])
    centroid = sum(p) / 4.0
    axis_z = min(0.0, max(-draft_cylinder, centroid[2]))  # 원통부는 축 방향, 반구부는 구 중심 기준
    outward = centroid - np.array([0.0, 0.0, axis_z])
    return p if np.dot(normal, outward) > 0 else [p[0], p[3], p[2], p[1]]


def build_panels(radius, draft_cylinder, n, nz):
    """1/4 모델 패널(꼭짓점 4개씩)의 리스트를 만듭니다. 좌표계: 수면 z = 0, 아래가 음수."""
    panels = []
    center_z = -draft_cylinder  # 반구 중심 높이
    tan_grid = np.tan((np.pi / 4) * np.arange(n + 1) / n)

    def on_sphere(direction):
        unit = np.asarray(direction, dtype=float)
        unit = unit / np.linalg.norm(unit)
        return np.array([radius * unit[0], radius * unit[1], center_z - radius * unit[2]])

    # 반구 1/8 구면 = 큐브 모서리의 세 면(x=1, y=1, z=1)을 구면에 투영
    for face in range(3):
        for i in range(n):
            for j in range(n):
                corners = []
                for a, b in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                    u, w = tan_grid[a], tan_grid[b]
                    direction = {0: (1.0, u, w), 1: (u, 1.0, w), 2: (u, w, 1.0)}[face]
                    corners.append(on_sphere(direction))
                panels.append(_outward(corners, draft_cylinder))

    # 원통: 90도를 2n열, 수면에서 원통 바닥까지 nz행
    z_levels = -draft_cylinder * np.arange(nz + 1) / nz
    theta = (np.pi / 2) * np.arange(2 * n + 1) / (2 * n)
    for k in range(nz):
        for m in range(2 * n):
            x0, y0 = radius * np.cos(theta[m]), radius * np.sin(theta[m])
            x1, y1 = radius * np.cos(theta[m + 1]), radius * np.sin(theta[m + 1])
            corners = [
                (x0, y0, z_levels[k]),
                (x0, y0, z_levels[k + 1]),
                (x1, y1, z_levels[k + 1]),
                (x1, y1, z_levels[k]),
            ]
            panels.append(_outward(corners, draft_cylinder))
    return panels


def _bottom_rim_layers(n):
    """평평한 바닥에서 가운데 정사각형과 둘레 사이의 층 수 m (패널이 정사각형에 가깝게)."""
    return max(1, round((1.0 - _CORE_FRACTION) * 4 * n / np.pi))


def count_cylinder_panels(n, nz):
    """평평한 바닥 원통 1/4 모델의 패널 수 (바닥 n^2 + 2 n m, 옆면 2 n n_z)."""
    return n * n + 2 * n * _bottom_rim_layers(n) + 2 * n * nz


def choose_cylinder_grid(radius, draft, target_panels):
    """평평한 바닥 원통: 목표 1/4 패널 수에 가장 가까운 (n, n_z)를 고릅니다(choose_grid와 같은 방식)."""
    best = None
    for n in range(1, _MAX_N + 1):
        nz_ideal = draft * 4 * n / (np.pi * radius)
        for nz in range(max(1, int(nz_ideal * 0.5)), int(nz_ideal * 2) + 2):
            panels = count_cylinder_panels(n, nz)
            aspect = (draft / nz) / (np.pi * radius / (4 * n))
            aspect = max(aspect, 1.0 / aspect)
            score = abs(panels - target_panels) / target_panels + _ASPECT_WEIGHT * (aspect - 1.0)
            if best is None or score < best[0]:
                best = (score, n, nz)
    return best[1], best[2]


def _oriented(corners, outward):
    """(p3 - p1) x (p4 - p2)가 outward 방향을 향하도록 꼭짓점 순서를 정합니다."""
    p = [np.asarray(q, dtype=float) for q in corners]
    normal = np.cross(p[2] - p[0], p[3] - p[1])
    return p if np.dot(normal, outward) > 0 else [p[0], p[3], p[2], p[1]]


def build_cylinder_panels(radius, draft, n, nz):
    """평평한 바닥 원통 1/4 모델 패널 리스트. 좌표계: 수면 z = 0, 아래가 음수."""
    panels = []
    # 옆면: 원통 + 반구와 같은 분할
    z_levels = -draft * np.arange(nz + 1) / nz
    theta = (np.pi / 2) * np.arange(2 * n + 1) / (2 * n)
    for k in range(nz):
        for j in range(2 * n):
            c0, s0 = np.cos(theta[j]), np.sin(theta[j])
            c1, s1 = np.cos(theta[j + 1]), np.sin(theta[j + 1])
            corners = [
                (radius * c0, radius * s0, z_levels[k]),
                (radius * c0, radius * s0, z_levels[k + 1]),
                (radius * c1, radius * s1, z_levels[k + 1]),
                (radius * c1, radius * s1, z_levels[k]),
            ]
            mid = (theta[j] + theta[j + 1]) / 2
            panels.append(_oriented(corners, (np.cos(mid), np.sin(mid), 0.0)))

    # 바닥: 가운데 정사각형 + 둘레로 잇는 두 패치 (모두 z = -draft, 바깥 = -z)
    core = _CORE_FRACTION * radius
    m = _bottom_rim_layers(n)
    down = (0.0, 0.0, -1.0)
    grid = core * np.arange(n + 1) / n
    for i in range(n):
        for j in range(n):
            corners = [
                (grid[i], grid[j], -draft),
                (grid[i + 1], grid[j], -draft),
                (grid[i + 1], grid[j + 1], -draft),
                (grid[i], grid[j + 1], -draft),
            ]
            panels.append(_oriented(corners, down))

    t_levels = np.arange(m + 1) / m
    for patch in (0, 1):
        for i in range(n):
            for k in range(m):
                quad = []
                for a, b in ((i, k), (i + 1, k), (i + 1, k + 1), (i, k + 1)):
                    if patch == 0:  # 정사각형의 x = core 변 -> 원호 0~45도
                        edge, angle = np.array([core, grid[a]]), (np.pi / 4) * a / n
                    else:  # 정사각형의 y = core 변 -> 원호 90~45도
                        edge, angle = np.array([grid[a], core]), np.pi / 2 - (np.pi / 4) * a / n
                    rim = np.array([radius * np.cos(angle), radius * np.sin(angle)])
                    x, y = (1.0 - t_levels[b]) * edge + t_levels[b] * rim
                    quad.append((x, y, -draft))
                panels.append(_oriented(quad, down))
    return panels


def write_gdf(output_path, panels, gravity=9.80665, title="cylinder + hemisphere, 1/4 model (cubed-sphere octant)"):
    """WAMIT GDF 파일을 씁니다 (ULEN = 1, ISX = ISY = 1, 사각형 패널 4점씩)."""
    with open(output_path, "w") as f:
        f.write(f" WAMIT GDF: {title}\n")
        f.write(f"{1.0:12.6f} {gravity:12.6f}      ULEN GRAV\n")
        f.write(f"{1:12d} {1:12d}      ISX  ISY\n")
        f.write(f"{len(panels):12d}      NEQN\n")
        for corners in panels:
            for x, y, z in corners:
                f.write(f"{x:13.6e} {y:13.6e} {z:13.6e}\n")


def generate_cylinder_hemisphere_mesh(radius, draft_cylinder, target_panels=DEFAULT_QUARTER_PANELS, output_path=None):
    """원통 + 반구 1/4 모델 메쉬를 만들고 실제 1/4 패널 수를 반환합니다.

    :param radius: 반지름 R (> 0)
    :param draft_cylinder: 원통부 흘수 D (> 0). 총 흘수는 D + R.
    :param target_panels: 목표 1/4 패널 수 (>= MIN_QUARTER_PANELS). 실제 수는 격자 구조상 가장 가까운 값입니다.
    :param output_path: GDF 저장 경로. None이면 파일을 쓰지 않습니다.
    """
    if not (radius > 0 and draft_cylinder > 0):
        raise ValueError(f"radius and draft must be positive, got radius={radius}, draft={draft_cylinder}")
    if target_panels < MIN_QUARTER_PANELS:
        raise ValueError(f"target_panels must be >= {MIN_QUARTER_PANELS}, got {target_panels}")

    n, nz = choose_grid(radius, draft_cylinder, target_panels)
    panels = build_panels(radius, draft_cylinder, n, nz)
    if output_path:
        write_gdf(output_path, panels)
    return len(panels)


def generate_cylinder_mesh(radius, draft, target_panels=DEFAULT_QUARTER_PANELS, output_path=None):
    """평평한 바닥 원통 1/4 모델 메쉬를 만들고 실제 1/4 패널 수를 반환합니다.

    :param radius: 반지름 R (> 0)
    :param draft: 흘수 D (> 0) = 총 흘수
    :param target_panels: 목표 1/4 패널 수 (>= MIN_QUARTER_PANELS)
    :param output_path: GDF 저장 경로. None이면 파일을 쓰지 않습니다.
    """
    if not (radius > 0 and draft > 0):
        raise ValueError(f"radius and draft must be positive, got radius={radius}, draft={draft}")
    if target_panels < MIN_QUARTER_PANELS:
        raise ValueError(f"target_panels must be >= {MIN_QUARTER_PANELS}, got {target_panels}")

    n, nz = choose_cylinder_grid(radius, draft, target_panels)
    panels = build_cylinder_panels(radius, draft, n, nz)
    if output_path:
        write_gdf(output_path, panels, title="cylinder with flat bottom, 1/4 model")
    return len(panels)


def generate_mesh(shape, radius, draft, target_panels=DEFAULT_QUARTER_PANELS, output_path=None):
    """shape(1 원통 + 반구, 2 원통)에 맞는 1/4 모델 메쉬를 만들고 실제 1/4 패널 수를 반환합니다."""
    if check_shape(shape) == SHAPE_CYLINDER:
        return generate_cylinder_mesh(radius, draft, target_panels, output_path)
    return generate_cylinder_hemisphere_mesh(radius, draft, target_panels, output_path)
