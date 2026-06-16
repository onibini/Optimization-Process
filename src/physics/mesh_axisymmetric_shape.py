"""
회전체 형상 3차원 surface mesh를 생성하는 모듈 (mesh_axisymmetric_shape.py)

이 모듈은 회전체 단면(profile)을 정의한 후 \theta 회전 각도만큼 회전한 회전체의 
surface mesh를 생성한다.

기본적으로 사각형(quadrilateral) 메쉬를 생성하나, 회전축 상에 있는 노드를 갖는 
메쉬의 경우 삼각형(triangular) 메쉬로 생성된다.

주요 기능:
    - 회전체 형상의 메쉬 생성 (Generate Mesh of Axisymmetric Geometry)
    - 회전체 정의를 위한 단면 생성 (Get Profile of Axisymmetric Geometry)
    - 회전체 단면 정의를 위한 선 메쉬 생성 (Get Line)
    - 길이 및 메쉬 개수 처리를 위한 Helper 함수 (Helper functions for Length & Allocation)
    - 회전체 단면을 회전시켜 회전체 메쉬 생성 (Convert Profile to Revolved Mesh)
    - gmsh를 활용한 시각화 및 파일 출력
"""

import numpy as np

# ============================================================================
# Generate Mesh of Axisymmetric Geometry
# ============================================================================
def generate_cone_mesh(radius, draft, output_path=None, display_mesh=False):
    
    # 설정 값
    MESH_SIZE = radius * 0.05

    # 1. 격자 수 계산 (적절한 위치에 배치)
    arc_len = radius * (np.pi / 2)
    N_VERTICAL = max(2, int(arc_len / MESH_SIZE))
    N_HORIZONTAL = max(2, int(arc_len / MESH_SIZE)//4)

    print(f">>> Generating Cone Mesh with {N_VERTICAL} divisions...")

    # [Step 1] 프로파일 생성 (나중에 B-spline으로 교체 가능)
    profile = get_cone_profile(radius=radius, draft=draft, 
                               num_segments=N_VERTICAL)

    # [Step 2] 회전체 메쉬 데이터 생성 (순수 수학)
    mesh_nodes, mesh_quads, mesh_triangles = revolve_profile(
        profile_points=profile, num_angular_segments=N_HORIZONTAL
    )

    # [Step 3] Gmsh로 시각화
    process_in_gmsh(
        mesh_nodes, mesh_quads, mesh_triangles, 
        output_path=output_path, display=display_mesh
    )


def generate_hemisphere_mesh(radius, draft, output_path=None, display_mesh=False):
    
    # 설정 값
    MESH_SIZE = radius * 0.5

    # 1. 격자 수 계산 (적절한 위치에 배치)
    arc_len = radius * (np.pi / 2)
    N_VERTICAL = max(2, int(arc_len / MESH_SIZE))
    N_HORIZONTAL = max(2, int(arc_len / MESH_SIZE)//4)

    print(f">>> Generating Mesh with {N_VERTICAL} divisions...")

    # [Step 1] 프로파일 생성 (나중에 B-spline으로 교체 가능)
    profile = get_hemisphere_profile_advanced(radius=radius, draft=draft, 
                                              num_segments=N_VERTICAL,
                                              spacing_method="linear")

    # [Step 2] 회전체 메쉬 데이터 생성 (순수 수학)
    # angular_segments도 N_DIV와 같게 하거나 다르게 설정 가능
    mesh_nodes, mesh_quads, mesh_triangles = revolve_profile(
        profile_points=profile, num_angular_segments=N_HORIZONTAL
    )

    # [Step 3] Gmsh로 시각화
    process_in_gmsh(
        mesh_nodes, mesh_quads, mesh_triangles, 
        output_path=output_path, display=display_mesh
    )


def generate_cylinder_mesh(radius, draft, output_path=None, display_mesh=False):
    
    # 설정 값
    MESH_SIZE = radius * 0.05

    # 1. 격자 수 계산 (적절한 위치에 배치)
    arc_len = radius * (np.pi / 2)
    N_VERTICAL = max(2, int(arc_len / MESH_SIZE))
    N_HORIZONTAL = max(2, int(arc_len / MESH_SIZE)//4)

    print(f">>> Generating Cylinder Mesh with {N_VERTICAL} divisions...")

    # [Step 1] 프로파일 생성 (나중에 B-spline으로 교체 가능)
    profile = get_cylinder_profile(radius=radius, draft=draft, 
                                   num_segments_z=N_VERTICAL,
                                   num_segments_r=N_VERTICAL)

    # [Step 2] 회전체 메쉬 데이터 생성 (순수 수학)
    mesh_nodes, mesh_quads, mesh_triangles = revolve_profile(
        profile_points=profile, num_angular_segments=N_HORIZONTAL
    )

    # [Step 3] Gmsh로 시각화
    process_in_gmsh(
        mesh_nodes, mesh_quads, mesh_triangles, 
        output_path=output_path, display=display_mesh
    )
    

def generate_cylinder_cone_mesh(radius, draft_cylinder, draft_cone, 
                                output_path=None, display_mesh=False):
    
    # 설정 값
    MESH_SIZE = radius * 0.05

    # 1. 격자 수 계산 (적절한 위치에 배치)
    arc_len = radius * (np.pi / 2)
    N_VERTICAL = max(2, int(arc_len / MESH_SIZE))
    N_HORIZONTAL = max(2, int(arc_len / MESH_SIZE)//4)

    print(f">>> Generating Cylinder-Cone Mesh with {N_VERTICAL} divisions...")

    # [Step 1] 프로파일 생성 (나중에 B-spline으로 교체 가능)
    profile = get_cylinder_cone_profile(radius=radius, 
                                        draft_cylinder=draft_cylinder,
                                        draft_cone=draft_cone,
                                        num_segments_z=N_VERTICAL,
                                        num_segments_r=N_VERTICAL)

    # [Step 2] 회전체 메쉬 데이터 생성 (순수 수학)
    mesh_nodes, mesh_quads, mesh_triangles = revolve_profile(
        profile_points=profile, num_angular_segments=N_HORIZONTAL
    )

    # [Step 3] Gmsh로 시각화
    process_in_gmsh(
        mesh_nodes, mesh_quads, mesh_triangles, 
        output_path=output_path, display=display_mesh
    )
    

def generate_cylinder_hemisphere_mesh(
    radius, 
    draft_cylinder,
    max_elements=500,
    output_path=None, 
    display_mesh=False
):
    
    # 설정 값
    # MESH_SIZE = radius * 0.05

    # 1. 격자 수 계산 (적절한 위치에 배치)
    # arc_len = radius * (np.pi / 2)
    # N_VERTICAL = max(2, int(draft_cylinder / 0.5))
    # N_HORIZONTAL = max(2, int(arc_len / MESH_SIZE)//4)

    len_side = draft_cylinder
    len_arc = radius * (np.pi / 2)
    len_circumference = 2 * np.pi * radius

    area_proxy = (len_side + len_arc) * len_circumference
    TARGET_MESH_SIZE = np.sqrt(area_proxy / max_elements)
    MESH_SIZE = TARGET_MESH_SIZE

    N_SIDE_Z = max(2, int(len_side / MESH_SIZE))
    N_HEMI_R = max(2, int(len_arc / MESH_SIZE))
    N_HORIZONTAL = max(2, int(len_circumference / MESH_SIZE)//2)

    # print(f"    >>> Generating Cylinder-Hemisphere Mesh with {N_VERTICAL} divisions...")

    # 프로파일 생성
    profile = get_cylinder_hemisphere_profile(
        radius=radius, 
        draft_cylinder=draft_cylinder,
        num_segments_z=N_SIDE_Z,
        num_segments_r=N_HEMI_R
    )

    # 프로파일 회전 + 메쉬 생성
    mesh_nodes, mesh_quads, mesh_triangles = revolve_profile(
        profile_points=profile, 
        num_angular_segments=N_HORIZONTAL
    )

    # gmsh 출력
    process_in_gmsh(
        mesh_nodes, 
        mesh_quads, 
        mesh_triangles, 
        output_path=output_path, 
        display=display_mesh
    )


def generate_cylinder_bspline_mesh(radius: float, 
                                   draft_cylinder: float, 
                                   draft_bspline: float,
                                   radius_corner: float,
                                   ctrl_points: list[tuple[float, float]], 
                                   degree: int,
                                   output_path=None, display_mesh=False):
    
    # 설정 값
    MESH_SIZE = radius * 0.05
    arc_len = radius * (np.pi / 2)
    # N_VERTICAL을 전체 프로파일 경계의 총 요소 개수로 사용
    N_VERTICAL = max(2, int(arc_len / MESH_SIZE))
    N_HORIZONTAL = max(2, int(arc_len / MESH_SIZE)//4)

    print(f">>> Generating Cylinder-BSpline (Flat Bottom) Mesh with Total {N_VERTICAL} divisions...")

    # [Step 1] B-spline 프로파일 생성
    profile = get_cylinder_bspline_profile(
        radius=radius, 
        draft_cylinder=draft_cylinder,
        draft_bspline=draft_bspline,
        radius_corner=radius_corner,
        n_vertical_segments=N_VERTICAL, 
        ctrl_points=ctrl_points,
        degree=degree
    )

    # [Step 2] 회전체 메쉬 데이터 생성
    mesh_nodes, mesh_quads, mesh_triangles = revolve_profile(
        profile_points=profile, num_angular_segments=N_HORIZONTAL
    )

    # [Step 3] Gmsh로 시각화
    process_in_gmsh(
        mesh_nodes, mesh_quads, mesh_triangles, 
        output_path=output_path, display=display_mesh
    )
    

def generate_bspline1_mesh(radius: float, 
                           cylinder_draft: float, 
                           bspline_draft: float,
                           c_x_nondim: list, 
                           tangent_len: float = 0.0,
                           output_path=None, 
                           display_mesh=None):
    
    MESH_SIZE = radius * 0.05
    arc_len = radius * (np.pi / 2)
    N_VERTICAL = max(2, int(arc_len / MESH_SIZE)*2)
    N_HORIZONTAL = max(2, int(arc_len / MESH_SIZE)//2)
    
    # [Step 1] B-spline 프로파일 생성
    profile, _ = get_bspline1_profile(
        radius=radius, 
        cylinder_draft=cylinder_draft,
        bspline_draft=bspline_draft,
        c_x_nondim=c_x_nondim,
        n_segments=N_VERTICAL,
        tangent_len=tangent_len
    )

    # [Step 2] 회전체 메쉬 데이터 생성
    mesh_nodes, mesh_quads, mesh_triangles = revolve_profile(
        profile_points=profile, num_angular_segments=N_HORIZONTAL
    )
    
    # [Step 3] Gmsh로 시각화
    process_in_gmsh(
        mesh_nodes, mesh_quads, mesh_triangles, 
        output_path=output_path, display=display_mesh
    )



# ============================================================================
# Get Profile of Axisymmetric Geometry
# ============================================================================
def get_flat_circle_profile(radius: float, z_level: float, num_segments: int):
    """
    평평한 원형 단면(Flat Disk)을 만들기 위한 프로파일 생성기
    (바깥쪽 r=R 에서 시작하여 안쪽 r=0 으로 끝남)
    """
    profile_points = []
    
    for i in range(num_segments + 1):
        # t: 0 (시작) -> 1 (끝)
        t = i / num_segments
        
        # r: Radius -> 0 (선형 감소)
        r = radius * (1 - t)
        
        # z: 고정된 높이 (예: -Draft)
        z = z_level
        
        profile_points.append((r, z))
        
    return np.array(profile_points)


def get_cone_profile(radius: float, draft: float, num_segments: int):
    """
    원뿔형 프로파일 생성기
    (수면에서 바닥까지 직선으로 연결)
    """
    profile_points = []
    
    for i in range(num_segments + 1):
        # t: 0 -> 1
        t = i / num_segments
        
        r = radius * (1 - t)  # 반지름 선형 감소
        z = -draft * t        # 깊이 선형 증가 (음수 방향)
        
        profile_points.append((r, z))
        
    return np.array(profile_points)


def get_hemisphere_profile_advanced(radius: float, draft: float, num_segments: int, spacing_method='linear'):
    """
    점 분포를 제어할 수 있는 반구 프로파일 생성기
    """
    profile_points = []
    
    # 예: spacing_method='cosine' -> 양 끝단 밀집
    # 예: spacing_method='power' -> 수면(phi=0) 근처 밀집
    
    for i in range(num_segments + 1):
        # 0 ~ 1 사이의 매개변수 t 생성
        t = _get_distribution_t(i, num_segments, method=spacing_method, bias=3.0)
        
        # phi: 0(적도) -> pi/2(남극)
        # t를 phi 계산에 적용하여 각도 간격을 조절함
        phi = (np.pi / 2) * t
        
        r_base = radius * np.cos(phi)
        z_base = -radius * np.sin(phi)
        
        if radius > 0:
            z = z_base * (draft / radius)
        else:
            z = z_base
        r = r_base
        
        profile_points.append((r, z))
        
    return np.array(profile_points)


def get_cylinder_profile(radius: float, draft: float, num_segments_z: int, num_segments_r: int):
    """
    옆면(Side)과 바닥(Bottom)이 이어진 'L'자 프로파일 생성
    순서: 수면(Side Top) -> 모서리(Corner) -> 바닥 중심(Center)
    """
    profile_points = []
    
    # 1. 옆면 (Side): (R, 0) -> (R, -Draft)
    for i in range(num_segments_z):
        # t: 0 -> 1
        t = i / num_segments_z
        z = -draft * t
        r = radius
        profile_points.append((r, z))
        
    # 2. 바닥 (Bottom): (R, -Draft) -> (0, -Draft)
    
    for i in range(num_segments_r + 1):
        t = i / num_segments_r
        r = radius * (1 - t)
        z = -draft
        profile_points.append((r, z))
    
    return np.array(profile_points)


def get_cylinder_cone_profile(radius: float, draft_cylinder: float, draft_cone: float, 
                              num_segments_z: int, num_segments_r: int):
    """
    원통부(Side)와 원뿔부(Bottom Cone)가 이어진 프로파일 생성
    수면(Z=0) -> 원통 바닥(Z=-draft_cylinder) -> 바닥 중심(Z=-draft_total)
    """
    profile_points = []
    draft_total = draft_cylinder + draft_cone
    
    # 1. 옆면 (Side): (R, 0) -> (R, -draft_cylinder)
    # 원통 옆면을 따라 내려옵니다.
    for i in range(num_segments_z + 1):
        if i == num_segments_z + 1: continue # 중복 방지
        t = i / num_segments_z
        z = -draft_cylinder * t
        r = radius
        profile_points.append((r, z))
        
    # 2. 원뿔부 (Cone): (R, -draft_cylinder) -> (0, -draft_total)
    # 원통 바닥 점에서 원뿔 중심으로 이어집니다.
    
    # 시작점 (원통 바닥)은 이미 추가되었으므로 1부터 시작
    for i in range(1, num_segments_r + 1): 
        # t: 0 -> 1 (원뿔부의 시작부터 끝)
        t = i / num_segments_r
        
        # r: Radius -> 0 (선형 감소)
        r = radius * (1 - t) 
        
        # z: -draft_cylinder -> -draft_total (선형 감소)
        z = -draft_cylinder - (draft_cone * t)
        
        profile_points.append((r, z))
        
    # 마지막 점이 (0, -draft_total)인지 확인
    if profile_points[-1][0] != 0.0:
        profile_points.append((0.0, -draft_total)) # 중심점을 명시적으로 추가
        
    return np.array(profile_points)


def get_cylinder_hemisphere_profile(radius: float, draft_cylinder: float, num_segments_z: int, num_segments_r: int):
    """
    원통부(Side)와 반구 바닥(Hemisphere, R=Draft)이 이어진 프로파일 생성
    수면(Z=0) -> 원통 바닥(Z=-draft_cylinder) -> 반구 중심(Z=-draft_total)
    """
    profile_points = []
    # 반구의 깊이는 반지름 R과 같습니다.
    draft_hemisphere = radius 
    draft_total = draft_cylinder + draft_hemisphere
    
    # 1. 옆면 (Side): (R, 0) -> (R, -draft_cylinder)
    for i in range(num_segments_z + 1):
        if i == num_segments_z + 1: continue
        t = i / num_segments_z
        z = -draft_cylinder * t
        r = radius
        profile_points.append((r, z))
        
    # 2. 반구부 (Hemisphere): (R, -draft_cylinder) -> (0, -draft_total)
    # 시작점 (원통 바닥)은 이미 추가되었으므로 1부터 시작
    for i in range(1, num_segments_r + 1):
        # phi: 0 (적도) -> pi/2 (남극)
        # i/num_segments_r이 0에서 1로 변하는 t 역할
        phi = (np.pi / 2) * (i / num_segments_r)
        
        # 반구의 r과 z 좌표 (중심이 (0, 0)일 때)
        r_base = radius * np.cos(phi)
        z_base = -radius * np.sin(phi)
        
        # 실제 좌표계로 이동: 반구 중심을 Z = -draft_cylinder - radius (즉, -draft_total)로 이동
        r = r_base
        z = z_base + radius - draft_cylinder
        
        # 참고: z_base의 정의에 따라 이동 변수가 달라질 수 있음. 
        # Z-축 이동을 정확히 하려면 Z_center = -draft_cylinder - R 이 되도록 합니다.
        # Z_hemisphere_start = -draft_cylinder (phi=0), Z_hemisphere_end = -draft_total (phi=pi/2)
        
        z = -draft_cylinder - (radius * np.sin(phi)) # Z-offset 0.0을 가정한 일반적인 수식
        
        profile_points.append((r, z))
        
    # 마지막 점이 (0, -draft_total)인지 확인
    if profile_points[-1][0] != 0.0 or profile_points[-1][1] != -draft_total:
        profile_points.append((0.0, -draft_total)) 
        
    return np.array(profile_points)


def get_cylinder_bspline_profile(radius: float, draft_cylinder: float, 
                                 draft_bspline: float, 
                                 radius_corner: float,
                                 n_vertical_segments: int, # num_segments_z 대신 총 세그먼트 수
                                 ctrl_points: list[tuple[float, float]] = None, 
                                 degree: int = 2) -> list[tuple[float, float]]:
    """
    원통부(Side) -> B-spline 필렛 -> 수평 바닥이 이어진 프로파일 생성.
    전체 요소 개수(n_total_segments)를 길이 비율에 따라 분배
    """
    profile_points = []
    
    # ----------------------------------------------------
    # 1. 포인트 정의 및 길이 계산
    # ----------------------------------------------------
    draft_total = draft_cylinder + draft_bspline
    
    P1 = (radius, 0.0)
    P2 = (radius, -draft_cylinder)
    P3 = (radius_corner, -draft_total)
    P4 = (0.0, -draft_total) # 중앙점
    
    # 세그먼트 길이 계산 (B-spline은 직선 거리로 근사)
    L1 = dist(P1, P2) # Side (수직선)
    # L2: B-spline 길이 (폴리라인 근사로 계산)
    # 임시로 충분히 많은 점을 생성하여 길이를 계산
    n_temp_points = 50
    temp_bspline_pts = get_bspline_points(
        P2, P3, 
        num_points=n_temp_points, 
        ctrl_points=ctrl_points, 
        degree=degree, 
        include_start=True
    )
    L2 = calc_polyline_length(temp_bspline_pts)
    L3 = dist(P3, P4) # Flat Bottom (수평선)
    
    side_len = [L1, L2, L3]
    
    # 요소 개수 분배
    n_elem_side, n_elem_bspline, n_elem_bottom = alloc_elem_num(n_vertical_segments, side_len)
    
    # 요소 개수가 0이 되지 않도록 최소 1개 보장 (필요한 경우)
    n_elem_side = max(3, n_elem_side)
    n_elem_bspline = max(3, n_elem_bspline)
    n_elem_bottom = max(3, n_elem_bottom)
    
    print(f"  > Elements allocated (Side/BSpline/Bottom): {n_elem_side}/{n_elem_bspline}/{n_elem_bottom}")

    # ----------------------------------------------------
    # 2. 옆면 (Side): P1(R, 0) -> P2(R, -D_cyl)
    # ----------------------------------------------------
    # get_line_points 사용 (pts_side[0] = P1, pts_side[-1] = P2)
    pts_side = get_line_points(P1, P2, n_elem_side + 1, 
                               include_start=True, spacing_mode='uniform')
    profile_points.extend(pts_side)
    
    # ----------------------------------------------------
    # 3. B-spline 필렛: P2(R, -D_cyl) -> P3(R_corner, -D_total)
    # ----------------------------------------------------
    # get_bspline_points 사용 (bspline_pts_list[0] = P2, bspline_pts_list[-1] = P3)
    bspline_pts_list = get_bspline_points(
        P2, P3, 
        num_points=n_elem_bspline + 1, 
        ctrl_points=ctrl_points, 
        degree=degree, 
        include_start=False
    )
    profile_points.extend(bspline_pts_list)
    
    # ----------------------------------------------------
    # 4. 수평 바닥 (Flat Bottom): P3(R_corner, -D_total) -> P4(0, -D_total)
    # ----------------------------------------------------
    # get_line_points 사용 (pts_bottom[0] = P3, pts_bottom[-1] = P4)
    # 수평선을 따라 중앙 축까지 이동합니다.
    pts_bottom_list = get_line_points(
        P3, P4, n_elem_bottom + 1, 
        include_start=False, spacing_mode='uniform'
    )
    profile_points.extend(pts_bottom_list)
    
    return np.array(profile_points)


def get_bspline1_profile(radius, cylinder_draft, bspline_draft, c_x_nondim, n_segments, tangent_len=0.0):
    """
    [수정됨] B-spline 프로파일 생성기 + 부드러운 연결부(Smooth Transition)
    
    Args:
        tangent_len (float): 원통 연결부에서 R=radius를 유지하며 수직으로 내려오는 길이.
                             이 값이 > 0 이면 Cylinder와 B-spline이 부드럽게 연결됨.
    """
    from scipy.interpolate import BSpline
    import numpy as np
    
    draft_total = cylinder_draft + bspline_draft
    
    # ---------------------------------------------------------
    # 1. 제어점 생성 (Smooth Transition 로직 추가)
    # ---------------------------------------------------------
    control_points = []
    
    # P0: 시작점 (원통 바닥)
    start_z = -cylinder_draft
    control_points.append((radius, start_z))
    
    # [핵심] 접선 제어점 추가 (P1)
    # tangent_len이 있으면, R을 유지한 채 아래로 살짝 내린 점을 추가하여 수직 접선 형성
    current_z = start_z
    remaining_bspline_draft = bspline_draft
    
    if tangent_len > 1e-6: # 0보다 크면
        # P1: (R, -cylinder_draft - tangent_len)
        current_z -= tangent_len
        control_points.append((radius, current_z))
        
        # 남은 B-spline 깊이 계산 (전체 깊이 넘지 않도록 방어 코드 필요)
        remaining_bspline_draft -= tangent_len
        if remaining_bspline_draft < 0:
            print("Warning: tangent_len is too large for bspline_draft!")
            remaining_bspline_draft = 0

    # 나머지 제어점 (c_x_nondim) 배치
    # 남은 깊이(remaining_bspline_draft)를 등분하여 배치
    if len(c_x_nondim) > 0:
        z_step = remaining_bspline_draft / len(c_x_nondim)
        
        for i, x in enumerate(c_x_nondim):
            # z 위치: 현재 위치(current_z)에서 z_step만큼 씩 내려감
            z = current_z - z_step * (i + 1)
            control_points.append((radius * x, z))
        
    # ---------------------------------------------------------
    # 2. 구간별 길이 대략 계산 및 격자 수 분배 (기존 동일)
    # ---------------------------------------------------------
    len_cylinder = cylinder_draft
    len_bspline = calc_polyline_length(control_points)
    last_pt = control_points[-1]
    bottom_center = (0.0, -draft_total)
    len_bottom = dist(last_pt, bottom_center)
    
    n_cy, n_bs, n_bot = alloc_elem_num(n_segments, [len_cylinder, len_bspline, len_bottom])
    
    # ---------------------------------------------------------
    # 3. 프로파일 포인트 생성 (기존 동일)
    # ---------------------------------------------------------
    
    # [Part 1] Cylinder
    pts_cylinder = get_line_points(
        (radius, 0.0), 
        (radius, -cylinder_draft), 
        n_cy + 1, 
        include_start=True, 
        spacing_mode='uniform'
    )
    
    # [Part 2] B-spline
    k = 2  # Degree (2차)
    n = len(control_points)
    
    # 점 개수가 degree + 1보다 적으면 에러 나므로 방어 코드
    if n <= k:
        # 제어점이 부족할 경우 직선으로 대체하거나 예외 처리
        print("Not enough control points for B-spline. Falling back to line.")
        pts_bspline = np.array(control_points)
    else:
        # Knot Vector 생성
        t = np.r_[[0]*k, np.arange(n - k + 1), [n - k]*k]
        spl = BSpline(t, control_points, k)
        
        xx = np.linspace(0, n - k, n_bs + 1)
        pts_bspline = spl(xx)
    
    # [Part 3] Bottom Line
    pts_bottom = get_line_points(
        pts_bspline[-1], 
        bottom_center, 
        n_bot + 1,
        include_start=True,
        spacing_mode='uniform'
    )

    # ---------------------------------------------------------
    # 4. 병합 (중복 점 제거)
    # ---------------------------------------------------------
    final_profile = np.vstack([
        pts_cylinder[:-1], 
        pts_bspline[:-1], 
        pts_bottom
    ])
    
    return final_profile, np.array(control_points)
    
    

# ============================================================================
# Get Line
# ============================================================================
def get_line_points(start_point: tuple[float, float], end_point: tuple[float, float], 
                    num_points: int, include_start: bool = True, 
                    spacing_mode: str = 'uniform', increasing: bool = True) -> np.ndarray:
    """
    두 점 사이에서 num_points개의 points를 생성
    (include_start=True이면 총 num_points개의 점을 반환하며, 시작점은 포함됨.)
    
    spacing_mode 옵션:
      'uniform'    : 선형 균등 간격 (기본)
      'sine'       : 전체 범위에 대해 sin 함수를 이용하여 간격을 조정 (sin 곡선 형태)
      'progression': 등비급수를 이용하여 간격이 점점 커지도록 생성 (increasing=True) 또는
                     반대로 점점 작아지도록 생성 (increasing=False)
      'half_sine'  : 0부터 π/4까지의 구간에 대해 1-cos 함수를 적용해 간격을 생성,
                     increasing=True이면 점점 커지고, False이면 점점 작아짐.
                     
    increasing 인수:
      True이면 시작점에서부터 점간 간격이 점점 커지도록, False이면 점점 좁아지도록 함.
    """
    if spacing_mode == 'uniform':
        t = np.linspace(0, 1, num_points)
    elif spacing_mode == 'sine':
        t = np.linspace(0, 1, num_points)
        t = (np.sin(np.pi * t - np.pi/2) + 1) / 2
    elif spacing_mode == 'progression':
        # 등비급수: increasing=True이면 q>1, False이면 q<1 (예: 1.1 또는 0.9)
        n_intervals = num_points - 1
        q = 1.1
        increments = np.array([q**i for i in range(n_intervals)])
        S = increments.sum()
        t = np.concatenate(([0], np.cumsum(increments)/S))
    elif spacing_mode == 'half_sine':
        # x를 0부터 π/4까지 선형 분할한 후, 1-cos(x)를 적용하여 점을 생성
        x = np.linspace(0, np.pi/4, num_points)
        t = (1 - np.cos(x)) / (1 - np.cos(np.pi/4))
    else:
        raise ValueError("Invalid spacing_mode. Choose among ['uniform', 'sine', 'progression', 'half_sine'].")
    
    # 만약 increasing가 False인 경우, 계산된 t를 반전시켜서 전체적으로 낮은 값부터 높은 값으로 정렬
    if not increasing:
        t = np.sort(1 - t)
    
    pts = np.column_stack((start_point[0] + t * (end_point[0] - start_point[0]),
                            start_point[1] + t * (end_point[1] - start_point[1])))
    if not include_start:
        pts = pts[1:]
    return pts

def de_boor(k: int, u: float, degree: int, knots: np.ndarray, ctrl_points: np.ndarray, 
            eps: float = 1e-14) -> np.ndarray:
    """
    de Boor 알고리즘을 사용해 u에서 B-spline 곡선을 평가
    (Parameters 및 Returns는 mesh.py와 동일)
    """
    d = ctrl_points[k - degree : k + 1].copy()
    for r in range(1, degree + 1):
        for i in range(degree, r - 1, -1):
            den = knots[k + 1 + i - r] - knots[k - degree + i]
            alpha = 0.0 if abs(den) < eps else (u - knots[k - degree + i]) / den
            d[i] = (1 - alpha) * d[i - 1] + alpha * d[i]
    return d[degree]


def get_bspline_points(start_point: tuple[float, float], end_point: tuple[float, float], 
                       num_points: int, ctrl_points: list[tuple[float, float]] = None, 
                       degree: int = 2, include_start: bool = True) -> np.ndarray:
    """
    시작점과 끝점을 반드시 지나도록 하는 B-spline 곡선의 points를 생성합니다.
    (Returns는 mesh.py와 동일)
    """
    if ctrl_points is None:
        mid = (0.5 * (start_point[0] + end_point[0]), 0.5 * (start_point[1] + end_point[1]))
        ctrl_points = [start_point, mid, end_point]
    else:
        ctrl_points = [start_point] + ctrl_points + [end_point]
    
    ctrl_points_arr = np.array(ctrl_points, dtype=float)
    n = len(ctrl_points_arr)
    p = degree
    
    # Knot 벡터 생성
    if n == p + 1:
        knots = np.array([0] * (p + 1) + [1] * (p + 1), dtype=float)
        start_u, end_u = 0.0, 1.0
    else:
        knots_list = [0] * (p + 1) + list(range(n - p - 1)) + [n - p - 1] * (p + 1)
        knots = np.array(knots_list, dtype=float)
        knots = knots / float(n - p - 1)
        start_u = knots[p]
        end_u = knots[n - p - 1]
    
    us = np.linspace(start_u, end_u, num_points)
    pts = np.empty((num_points, 2), dtype=float)
    for idx, u in enumerate(us):
        k = None
        for i in range(p, n):
            if u >= knots[i] and u <= knots[i + 1]:
                k = i
                break
        if k is None:
            k = n - 2
        pts[idx] = de_boor(k, u, p, knots, ctrl_points_arr)
    
    if not include_start:
        pts = pts[1:]
        
    # Profile 함수가 List[Tuple[float, float]]을 반환하도록 재형식화
    return [tuple(pt) for pt in pts]


# ========================================
# Helper functions for Length & Allocation
# ========================================
def _get_distribution_t(i, n, method='linear', bias=1.2):
    """
    0부터 1 사이의 매개변수 t를 생성하는 함수
    i: 현재 인덱스 (0 ~ n)
    n: 전체 분할 수
    method: 'linear', 'cosine', 'power' (한쪽 쏠림)
    bias: 'power' 사용 시 쏠림 강도 (1.0 = linear, >1.0 = 시작점에 밀집)
    """
    linear_t = i / n
    
    if method == 'linear':
        return linear_t
    
    elif method == 'cosine':
        # 양 끝(0과 1)에 밀집
        return (1 - np.cos(np.pi * linear_t)) / 2
    
    elif method == 'power':
        # 0(시작점) 근처에 밀집하고 1로 갈수록 넓어짐 (혹은 그 반대)
        # bias > 1: 0 쪽에 밀집 (수면 집중)
        # bias < 1: 1 쪽에 밀집
        return (np.power(bias, linear_t) - 1) / (bias - 1)
        # 또는 단순하게: return np.power(linear_t, bias) 
        
    return linear_t


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    """두 점 사이의 직선 거리를 계산"""
    return np.hypot(a[0] - b[0], a[1] - b[1])


def alloc_elem_num(n_elem: int, side_len: list[float]) -> list[int]:
    """
    전체 element 개수(n_elem)를 각 변의 길이에 비례하여 분배
    (mesh.py에서 복사됨)
    """
    total_len = sum(side_len)
    side_n_elem = np.zeros(len(side_len), dtype=int)
    
    # 길이가 0인 경우를 대비하여 total_len이 0이 아닌지 확인
    if total_len == 0:
        if n_elem > 0:
            return [n_elem] + [0] * (len(side_len) - 1)
        return [0] * len(side_len)
        
    for i in range(len(side_len) - 1):
        # 반올림하여 분배
        side_n_elem[i] = round(side_len[i] / total_len * n_elem)
        
    # 마지막 세그먼트에는 나머지 개수를 할당하여 합계가 정확히 n_elem이 되도록 보장
    side_n_elem[-1] = n_elem - int(sum(side_n_elem[:-1]))
    
    # 분배된 요소 개수는 최소 1개 이상이 되도록 강제할 수 있지만, 여기서는 원본 로직을 따릅니다.
    return side_n_elem.tolist()


def calc_polyline_length(points: list[tuple[float, float]]) -> float:
    """주어진 점들로 이루어진 폴리라인의 총 길이를 계산"""
    length = 0.0
    for i in range(len(points) - 1):
        length += dist(points[i], points[i+1])
    return length


# ============================================================================
# Convert Profile to Revolved Mesh
# ============================================================================
def revolve_profile(
    profile_points: list[tuple], 
    num_angular_segments: int,
    theta_revolve=90
):
    """
    (r, z) 프로파일을 회전시켜 3D 메쉬를 생성 (개선된 버전).
    반지름(r)이 0에 가까우면 위치(Top/Bottom)에 상관없이 자동으로 극점(Triangle Fan) 처리.
    """
    nodes = []
    quads = []
    triangles = []
    
    # (i, j) 인덱스가 가리키는 노드 태그를 저장하는 맵
    # key: (i, j), value: node_tag (1-based)
    idx_map = {} 
    
    num_vertical = len(profile_points)
    num_angular = num_angular_segments
    
    node_tag_counter = 1
    EPSILON = 1e-9  # 극점 판별을 위한 허용 오차
    
    # ------------------
    # 1. 노드 생성 (Node Generation)
    # ------------------
    # 각 줄(row)이 극점인지 아닌지 기록해둠 (Element 생성 때 사용)
    is_pole = [] 

    for i, (r, z) in enumerate(profile_points):
        # 반지름이 거의 0이면 극점으로 처리
        if abs(r) < EPSILON:
            is_pole.append(True)
            
            # 단일 노드 생성
            nodes.extend([0.0, 0.0, z])
            polar_node_tag = node_tag_counter
            
            # 이 줄(Row i)의 모든 각도 j는 동일한 polar_node_tag를 가리킴
            for j in range(num_angular + 1): # 닫힌 원이므로 시작점=끝점 고려
                idx_map[(i, j)] = polar_node_tag
            
            node_tag_counter += 1
            
        else:
            is_pole.append(False)
            
            # 링(Ring) 노드 생성
            for j in range(num_angular + 1):
                theta = np.deg2rad(theta_revolve) * (j / num_angular) # 0 to 2pi
                x = r * np.cos(theta)
                y = r * np.sin(theta)
                
                nodes.extend([x, y, z])
                idx_map[(i, j)] = node_tag_counter
                node_tag_counter += 1

    # ------------------
    # 2. 요소 연결 (Element Connectivity)
    # ------------------
    for i in range(num_vertical - 1):
        row_curr_is_pole = is_pole[i]
        row_next_is_pole = is_pole[i+1]
        
        # 두 줄이 모두 극점이면 (축을 따라 이동하는 선분) 면을 만들 수 없음 -> Skip
        if row_curr_is_pole and row_next_is_pole:
            continue

        for j in range(num_angular):
            # 현재 j와 다음 j (원통형으로 닫힘 처리)
            # j가 num_angular-1 일 때, next_j는 num_angular (위에서 생성한 마지막 노드)
            # 만약 노드를 공유(merge)하고 싶다면 여기서 % 연산 사용.
            # 현재 코드 구조상 num_angular+1개의 노드를 만들었으므로 j+1 사용.
            
            j_curr = j
            j_next = j + 1
            
            n1 = idx_map[(i, j_curr)]
            n2 = idx_map[(i, j_next)]
            n3 = idx_map[(i+1, j_next)]
            n4 = idx_map[(i+1, j_curr)]
            
            if row_curr_is_pole:
                # [Top Pole Case] 위쪽이 점, 아래쪽이 링 -> 삼각형 (퍼짐)
                # n1과 n2는 동일한 pole node
                # 유효한 점: n1(pole), n4, n3 (반시계 방향 주의)
                triangles.extend([n1, n4, n3])
                
            elif row_next_is_pole:
                # [Bottom Pole Case] 위쪽이 링, 아래쪽이 점 -> 삼각형 (모임)
                # n3와 n4는 동일한 pole node
                # 유효한 점: n1, n2, n3(pole)
                triangles.extend([n1, n3, n2])
                
            else:
                # [Cylinder/Ring Case] 둘 다 링 -> 사각형
                quads.extend([n1, n4, n3, n2])
                
    return nodes, quads, triangles


def visualize_profile(profile_points, title="Axisymmetric Profile (r vs z)",
                      points=None):
    """
    (r, z) 프로파일 포인트를 시각화하는 헬퍼 함수
    """
    import matplotlib.pyplot as plt

    r_coords = [p[0] for p in profile_points]
    z_coords = [p[1] for p in profile_points]
    
    plt.figure(figsize=(6, 8))
    
    # 1사분면 (r > 0) 플롯
    plt.plot(r_coords, z_coords, 'ro-', markersize=4, label='Profile Points')
    if points is not None:
        plt.plot(points[:,0], points[:,1], 'gs', markersize=6, label='Additional Points')
    
    # 대칭성을 고려하여 2사분면 (r < 0) 미러 플롯 (선택 사항)
    plt.plot([-r for r in r_coords], z_coords, 'bo--', alpha=0.5, label='Mirrored Profile')
    
    plt.xlabel("Radius (r)")
    plt.ylabel("Depth (z)")
    plt.title(title)
    plt.grid(True)
    plt.axhline(0, color='black', linestyle='--', linewidth=0.8) # 수면 (Z=0)
    plt.gca().set_aspect('equal', adjustable='box') # 종횡비 유지
    plt.legend()
    plt.tight_layout()
    plt.show()
    plt.close()


# ============================================================================
# gmsh 처리 및 내보내기
# ============================================================================
def process_in_gmsh(nodes, quads, triangles, output_path=None, display=True):
    """
    Raw Mesh Data (Nodes, Quads, Triangles)를 받아서 Gmsh로 시각화하거나 내보내는 함수
    """
    import gmsh

    gmsh.initialize()
    try:
        model_name = "Discrete_Mesh_Fixed_Pole"
        gmsh.model.add(model_name)
        gmsh.option.setNumber("General.Terminal", 0)

        # 1. Discrete Entity 생성
        s_tag = 1
        gmsh.model.addDiscreteEntity(2, s_tag)

        # 2. 노드 입력
        num_nodes = len(nodes) // 3
        node_tags = list(range(1, num_nodes + 1))
        gmsh.model.mesh.addNodes(2, s_tag, node_tags, nodes)

        # 3. 요소 입력
        current_element_tag = 1

        # 3-1. 사각형 요소 (Type 3: 4-node quadrangle)
        if quads:
            num_quads = len(quads) // 4
            quad_tags = list(range(current_element_tag, current_element_tag + num_quads))
            gmsh.model.mesh.addElements(2, s_tag, [3], [quad_tags], [quads])
            current_element_tag += num_quads

        # 3-2. 삼각형 요소 (Type 2: 3-node triangle)
        if triangles:
            num_triangles = len(triangles) // 3
            triangle_tags = list(range(current_element_tag, current_element_tag + num_triangles))
            gmsh.model.mesh.addElements(2, s_tag, [2], [triangle_tags], [triangles])

        # 노드 정보 가져오기
        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()

        # 요소 정보 가져오기 (Connectivity)
        panel_types, panel_tags, panel_nodes = gmsh.model.mesh.getElements(dim=2)

        # 4. 내보내기 (옵션)
        if output_path:
            if output_path.lower().endswith('.msh'):
                gmsh.write(output_path)
            elif output_path.lower().endswith('.gdf'):
                _write_gdf(
                    output_path,
                    node_tags,
                    node_coords,
                    panel_types,
                    panel_tags,
                    panel_nodes,
                    gravity=9.80665,
                    symmetry_x=1,
                    symmetry_y=1
                )

        # 5. 시각화 및 종료
        if display:
            gmsh.option.setNumber('Mesh.SurfaceEdges', 1)
            gmsh.option.setNumber('Mesh.Normals', 20)
            gmsh.fltk.run()
    finally:
        gmsh.finalize()


def _write_gdf(
    output_path: str, 
    node_tags: list[int],
    node_coords: list[float],
    panel_types: list[int], 
    panel_tags: list[int],
    panel_nodes: list[np.ndarray],
    gravity: float=9.80665, 
    symmetry_x: int=0,
    symmetry_y: int=0
) -> None:
    """
    Exports a mesh to the WAMIT GDF (Geometry Data File) format.

    Parameters
    ----------
    output_path : str
        Path to save the GDF file.
    node_tags : list[int]
        List of unique node IDs (tags).
    node_coords : list[float]
        List of node coordinates in the order [x1, y1, z1, x2, y2, z2, ...].
    panel_types : list[int]
        List of element types (e.g., 2 for triangles, 3 for quadrangles), one per panel group.
    panel_tags : list[int]
        List of element tags (IDs) or physical group tags for each element type group.
    panel_nodes : list[np.ndarray]
        List of 1D NumPy arrays containing the node tags defining the connectivity for each panel group.
    gravity : float, optional
        Gravity value (GRAV) to include in the GDF header. Default is 9.80665.
    symmetry_x : int, optional
        Symmetry code (ISX) for the x-axis. Default is 0 (no symmetry).
    symmetry_y : int, optional
        Symmetry code (ISY) for the y-axis. Default is 0 (no symmetry).

    Notes
    -----
    The characteristic length (ULEN) is hardcoded to 1.0.
    Triangle panels (Type 2) are defined using the four-point sequence (n1, n1, n2, n3)
    as required by the specific WAMIT GDF implementation used.
    """

    node_map = {}
    for i, tag in enumerate(node_tags):
        # 좌표는 (x, y, z) 튜플로 저장
        node_map[tag] = (node_coords[3*i], node_coords[3*i+1], node_coords[3*i+2])

    # 3. 전체 패널 개수 계산
    num_panels = 0
    for i, etype in enumerate(panel_types):
        # etype 2: 3-node triangle, etype 3: 4-node quadrangle
        if etype == 2 or etype == 3:
            num_panels += len(panel_tags[i])
            
    if num_panels == 0:
            print("Warning: No Triangle or Quad elements found.")
            return

    with open(output_path, 'w') as f:
        # 헤더 작성
        # ULEN(특성 길이)은 1.0으로 가정 (필요시 수정), GRAV는 입력값
        f.write(" WAMIT GDF file exported from Gmsh\n")
        f.write(f"{1.0:12.6f} {gravity:12.6f}      ULEN GRAV\n")
        f.write(f"{symmetry_x:12d} {symmetry_y:12d}      ISX  ISY\n")
        f.write(f"{num_panels:12d}      NEQN\n")

        # 각 요소별 좌표 쓰기
        for i, etype in enumerate(panel_types):
            # 요소별 노드 태그 리스트
            # panel_nodes[i]는 [e1_n1, e1_n2, ..., e2_n1, ...] 처럼 1차원 배열임
            tags = panel_nodes[i]
            
            if etype == 2: # 3-node Triangle
                num_nodes = 3
                for j in range(0, len(tags), num_nodes):
                    n1 = tags[j]
                    n2 = tags[j+1]
                    n3 = tags[j+2]
                    
                    # 좌표 가져오기
                    c1 = node_map[n1]
                    c2 = node_map[n2]
                    c3 = node_map[n3]
                    
                    # GDF 포맷: x y z (4개 점, 삼각형은 마지막 점 중복)
                    f.write(f"{c1[0]:13.6e} {c1[1]:13.6e} {c1[2]:13.6e}\n")
                    f.write(f"{c1[0]:13.6e} {c1[1]:13.6e} {c1[2]:13.6e}\n")
                    f.write(f"{c2[0]:13.6e} {c2[1]:13.6e} {c2[2]:13.6e}\n")
                    f.write(f"{c3[0]:13.6e} {c3[1]:13.6e} {c3[2]:13.6e}\n") # 4번째 점 중복

            elif etype == 3: # 4-node Quadrangle
                num_nodes = 4
                for j in range(0, len(tags), num_nodes):
                    n1 = tags[j]
                    n2 = tags[j+1]
                    n3 = tags[j+2]
                    n4 = tags[j+3]
                    
                    c1 = node_map[n1]
                    c2 = node_map[n2]
                    c3 = node_map[n3]
                    c4 = node_map[n4]
                    
                    f.write(f"{c1[0]:13.6e} {c1[1]:13.6e} {c1[2]:13.6e}\n")
                    f.write(f"{c2[0]:13.6e} {c2[1]:13.6e} {c2[2]:13.6e}\n")
                    f.write(f"{c3[0]:13.6e} {c3[1]:13.6e} {c3[2]:13.6e}\n")
                    f.write(f"{c4[0]:13.6e} {c4[1]:13.6e} {c4[2]:13.6e}\n")

    # print(f"    Successfully exported GDF file: {output_path}")
