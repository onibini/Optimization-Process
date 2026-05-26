def decode_symmetric_positions(vector, num_wecs):
    '''
    알고리즘이 1차원 배열(vector)을 규칙에 따라 실제 (x, y) 좌표 리스트로 변환
    x축을 기준으로 대칭되도록 설계
    WEC1은 항상 중앙. WEC2, WEC3 등은 사이드 쌍
    '''

    positions = []

    x1 = vector[0]
    positions.append((x1, 0.0))  # WEC1

    if num_wecs >= 3:
        x2, y2 = vector[1], vector[2]

        if num_wecs == 5:
            x3, y3 = vector[3], vector[4]

            side_wecs = sorted([(x2, y2), (x3, y3)], key=lambda item: (item[0], item[1]))

            s_x2, s_y2 = side_wecs[0]
            s_x3, s_y3 = side_wecs[1]

            positions.append((s_x2, s_y2))  # WEC2
            positions.append((s_x2, -s_y2))  # WEC2 대칭
            positions.append((s_x3, s_y3))  # WEC3
            positions.append((s_x3, -s_y3))  # WEC3 대칭

        else:
            positions.append((x2, y2))  # WEC2
            positions.append((x2, -y2))  # WEC2 대칭
    
    return positions


def canonicalize_vector_inplace(vector, opt_mode, num_wecs):
    """
    대칭성으로 인해 동일한 물리적 구조를 나타내는 임의의 벡터를
    고유한 대표 벡터(Canonical representation)로 인플레이스(in-place) 정렬합니다.
    - 5기 WEC의 경우: WEC2와 WEC3 사이의 기하학적 대칭 및 순서 독립성을 해결하기 위해 (x2, y2)와 (x3, y3)를 정렬합니다.
    """
    if num_wecs == 5:
        if opt_mode == 2:    # Layout 최적화: [x1, x2, y2, x3, y3]
            offset = 0
        elif opt_mode == 3:  # Joint 최적화: [radius, draft, x1, x2, y2, x3, y3]
            offset = 2
        else:
            return
        
        x2, y2 = vector[offset+1], vector[offset+2]
        x3, y3 = vector[offset+3], vector[offset+4]
        
        if (x2, y2) > (x3, y3):
            vector[offset+1], vector[offset+3] = x3, x2
            vector[offset+2], vector[offset+4] = y3, y2

