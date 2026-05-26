import numpy as np

def check_min_distance(positions, radius, min_spacing):
    '''
    N x N 거리 행렬을 생성하여 WEC 간 최소 거리 위반량을 계산
    - positions: [(x1, y1), (x2, y2), ...] 형태의 WEC 좌표 리스트
    - radius: 각 WEC의 반지름
    - min_spacing: 최소 간격 계수
    - 반환값: 총 거리 위반량의 합
    '''

    num_wecs = len(positions)
    if num_wecs <= 1:
        return 0.0
    
    # 1. 리스트를 numpy 배열로 변환 (Shape: N x 2)
    pos_array = np.array(positions)

    # 2. 브로드캐스팅을 이용해 N x N 차이 행렬 계산 (Shape: N x N x 2)
    diff = pos_array[:, np.newaxis, :] - pos_array[np.newaxis, :, :]

    # 3. 유클리드 거리 계산 (Shape: N x N)
    dist_matrix = np.linalg.norm(diff, axis=-1)

    # 4. 상삼각 행렬 마스크 생성
    # k=1을 주어 대각을 제외하고, 중복 계산을 막기 위해 절반의 삼각형 영역만 True로 만듬
    mask = np.triu(np.ones((num_wecs, num_wecs), dtype=bool), k=1)

    # 5. 마스크를 적용해 필요한 거리값만 1차원 배열로 추출
    valid_dists = dist_matrix[mask]

    # 6. 최소 거리 위반량 계산
    min_allowed_dist = radius * min_spacing

    violations = np.maximum(0, min_allowed_dist - valid_dists)

    # 7. 총 위반량 반환
    return np.sum(violations)