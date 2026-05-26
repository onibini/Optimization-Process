import os
import numpy as np

def get_volumes_from_out(workspace_dir, num_wecs):
    """ .out 파일에서 첫 번째 부피 라인의 마지막 값(VOLZ)을 찾아 모든 기기에 동일하게 적용 """
    out_file = os.path.join(workspace_dir, 'wec.out')
    volume_val = None
    
    with open(out_file, 'r', encoding='utf-8') as f:
        for line in f:
            if "Volumes (VOLX,VOLY,VOLZ):" in line:
                parts = line.split(':')[-1].split()
                if parts: 
                    volume_val = float(parts[-1]) 
                    break 
        
    return [volume_val] * num_wecs

def get_c_mat_from_hst(workspace_dir, num_wecs, heave_dofs, rho, g):
    """ WAMIT .hst 파일에서 첫 번째 대각(Heave) 강성 값을 찾아 모든 기기에 동일하게 적용 """
    C_mat = np.zeros((num_wecs, num_wecs)) 
    file_hst = os.path.join(workspace_dir, 'wec.hst')
    c33_val = None
    
    with open(file_hst, 'r') as f:
        next(f)  # 헤더 스킵
        for line in f:
            if not line.strip() or line.startswith(('C', '*')): continue
            
            cols = line.split()
            if len(cols) >= 3:
                i, j = int(cols[0]), int(cols[1])
                if i == j and i in heave_dofs:
                    c33_val = float(cols[2]) * (rho * g)
                    break 

    C_mat = np.eye(num_wecs) * c33_val
        
    return C_mat


def calculate_rao_matrix(workspace_dir, num_wecs, rho=1025.0, g=9.80665):
    """
    WAMIT 출력 데이터에 물리적 스케일링을 적용하여 차원화된 RAO를 계산합니다.
    - Added Mass (A): rho 곱함
    - Damping (B): rho * omega 곱함
    - Restoring (C): rho * g 곱함
    - Force (F): rho * g 곱함
    - Mass (M): rho * Volume
    """
    heave_dofs = {3 + 6*k: k for k in range(num_wecs)}

    # 1. 질량 행렬(M)과 강성 행렬(C) 구성
    volumes = get_volumes_from_out(workspace_dir, num_wecs)
    M_mat = np.diag([rho * v for v in volumes])
    C_mat = get_c_mat_from_hst(workspace_dir, num_wecs, heave_dofs, rho, g)

    file_1, file_2 = os.path.join(workspace_dir, 'wec.1'), os.path.join(workspace_dir, 'wec.2')
    hydro_dict, force_dict = {}, {}

    # ==========================================================
    # [Step 0] 파일 읽기 (.1, .2) 및 차원화 (대칭화 삭제)
    # ==========================================================
    with open(file_1, 'r') as f:
        for idx, line in enumerate(f):
            if idx == 0: continue # 헤더 스킵
            if not line.strip() or line.startswith(('C', '*')): continue
            
            cols = line.split()
            omega = float(cols[0]) 
            i, j = int(cols[1]), int(cols[2])
            
            if i in heave_dofs and j in heave_dofs:
                if omega not in hydro_dict:
                    hydro_dict[omega] = {'A_dim': np.zeros((num_wecs, num_wecs)), 
                                         'B_dim': np.zeros((num_wecs, num_wecs))}
                
                hydro_dict[omega]['A_dim'][heave_dofs[i], heave_dofs[j]] = float(cols[3]) * rho             
                hydro_dict[omega]['B_dim'][heave_dofs[i], heave_dofs[j]] = float(cols[4]) * (rho * omega)   

    with open(file_2, 'r') as f:
        for idx, line in enumerate(f):
            if idx == 0: continue # 헤더 스킵
            if not line.strip() or line.startswith(('C', '*')): continue
            
            cols = line.split()
            omega = float(cols[0])
            i = int(cols[2])
            
            if i in heave_dofs:
                if omega not in force_dict: 
                    force_dict[omega] = np.zeros(num_wecs, dtype=complex)
                
                force_dict[omega][heave_dofs[i]] = complex(float(cols[5]), float(cols[6])) * (rho * g)

    omega_list = sorted(list(hydro_dict.keys()))

    # ==========================================================
    # [Step 1] 1차 해석: Base RAO 
    # ==========================================================
    base_rao_results = []
    
    for w in omega_list:
        A_dim = hydro_dict[w]['A_dim']
        B_rad_dim = hydro_dict[w]['B_dim']
        F_dim = force_dict[w]

        Z_base = -(w**2) * (M_mat + A_dim) + 1j * w * B_rad_dim + C_mat
        X_base = np.linalg.solve(Z_base, F_dim)
        base_rao_results.append(np.abs(X_base)) 

    base_rao_arr = np.array(base_rao_results)

    # ==========================================================
    # [Step 2] 실제 피크 탐색 및 차원화된 B_pto 추출
    # ==========================================================
    b_pto_list = np.zeros(num_wecs)
    
    for k in range(num_wecs):
        peak_idx = np.argmax(base_rao_arr[:, k])
        wn = omega_list[peak_idx] 
        b_pto_list[k] = hydro_dict[wn]['B_dim'][k, k]

    # ==========================================================
    # [Step 3] 2차 해석: 튜닝된 PTO를 얹어서 최종 RAO 도출
    # ==========================================================
    final_rao_results = []
    B_pto_mat = np.diag(b_pto_list) 
    
    for w in omega_list:
        A_dim = hydro_dict[w]['A_dim']
        B_rad_dim = hydro_dict[w]['B_dim']
        F_dim = force_dict[w]

        B_total = B_rad_dim + B_pto_mat
        Z_final = -(w**2) * (M_mat + A_dim) + 1j * w * B_total + C_mat
        
        X_final = np.linalg.solve(Z_final, F_dim)
        final_rao_results.append({
            'omega': w,
            'rao_abs': np.abs(X_final), 
            'b_pto': b_pto_list.copy() 
        })

    return final_rao_results

if __name__ == "__main__":
    # 테스트용 워크스페이스 디렉토리와 기기 수
    workspace_dir = 'workspace'
    num_wecs = 5

    rao = calculate_rao_matrix(workspace_dir, num_wecs)