import os
import subprocess
import numpy as np
from src.physics.mesh_axisymmetric_shape import generate_cylinder_hemisphere_mesh

def write_wamit_inputs(vector, config, workspace_dir):
    """
    OptMode에 따라 WAMIT 입력 파일(fnames.wam, .pot, .frc, .gdf)을 생성합니다.
    """
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)

    mode = config['opt_mode']
    num_wecs = config['num_wecs']
    NCPU = config['ncpu']
    RAMGBMAX = config['ram']
    
    # 1. 최적화 모드별 형상 및 위치 확정
    if mode == 1: # Shape Only
        radius, draft = vector[0], vector[1]
        positions = [(0.0, 0.0)]
    elif mode == 2: # Layout Only
        radius, draft = config['fixed_radius'], config['fixed_draft']
        positions = config['positions']
    else: # Shape + Layout
        radius, draft = vector[0], vector[1]
        positions = config['positions']

    gdf_filename = 'wec.gdf'
    gdf_path = os.path.join(workspace_dir, gdf_filename)

    # 2. GDF 파일 생성
    generate_cylinder_hemisphere_mesh(
        radius=radius,
        draft_cylinder=draft,
        max_elements=300,
        output_path=gdf_path,
        display_mesh=False
    )

    # 3. fnames.wam 작성
    with open(os.path.join(workspace_dir, 'fnames.wam'), 'w') as f:
        f.write("wec.cfg\n")
        f.write("wec.pot\n")
        f.write("wec.frc\n")
    
    # 4. POT 파일 작성
    write_pot_file(workspace_dir, positions, config)

    # 5. FRC 파일 작성
    write_frc_file(workspace_dir, len(positions))

    # 6. CFG 파일 작성
    write_config_cfg(workspace_dir, mode)

    # 7. WAMIT 설정 파일 작성
    write_config_wam(workspace_dir, NCPU, RAMGBMAX)

def write_pot_file(workspace_dir, positions, config):
    depth = config['depth']

    with open(os.path.join(workspace_dir, 'wec.pot'), 'w') as f:
        f.write("WEC Optimization Array Analysis\n")
        f.write(f"{depth:<20} HBOT\n")
        f.write(f"{'0 0':<20} IRAD IDIFF\n")
        f.write(f"{'-51':<20} NPER\n")
        f.write(f"{'0.5 0.05':<20} PER\n")
        f.write(f"{'1':<20} NBETA\n")
        f.write(f"{'0':<20} BETA\n")
        f.write(f"{len(positions):<20} NBODY\n")
        for x, y in positions:
            f.write("wec.gdf\n")
            f.write(f"{x} {y} 0 0\n")
            f.write(f"{'0 0 1 0 0 0':<20} IMODE\n")

def write_frc_file(workspace_dir, nbody):
    with open(os.path.join(workspace_dir, 'wec.frc'), 'w') as f:
        f.write("WEC Force Configuration\n")
        f.write(f"{'1 1 1 0 0 0 0 0 0':<20} OutputFile\n")
        for i in range(nbody):
            f.write(f"{'0':<20} VCG{i+1}\n")
            f.write(f"{'1 0 0':<20}\n")
            f.write(f"{'0 1 0':<20}\n")
            f.write(f"{'0 0 1':<20}\n")
        f.write(f"{'0':<20} NBETAH\n")
        f.write(f"{'0':<20} NFIELD\n")

def write_config_wam(workspace_dir, NCPU, RAMGBMAX):
    with open(os.path.join(workspace_dir, 'config.wam'), 'w') as f:
        f.write("WEC Configuration\n")
        f.write(f"NCPU={NCPU}\n")
        f.write(f"RAMGBMAX={RAMGBMAX}\n")
        f.write(f"USERID_PATH=C:\\WAMITv7\n")

def write_config_cfg(workspace_dir, opt_mode):
    iwallx_val = 0 if opt_mode == 1 else 1
    with open(os.path.join(workspace_dir, 'wec.cfg'), 'w') as f:
        f.write("WEC Optimization Configuration\n")
        f.write(f"ipltdat=1\n")
        f.write(f"NUMHDR=1\n")
        f.write(f"IPERIN=2\n")
        f.write(f"IPEROUT=2\n")
        f.write(f"IWALLX0={iwallx_val}\n")
        f.write(f"ISOR=0\n")
        f.write(f"ISOLVE=1\n")
        f.write(f"MAXITT=100\n")
        f.write(f"ISCATT=0\n")
        f.write(f"IALTERC=1\n")
        f.write(f"ILOC=1\n")



def run_wamit(workspace_dir, exe_path=r"C:\WAMITv7\WAMIT.exe"):
    """작업 디렉토리에서 WAMIT을 직접 실행합니다."""
    del_files = ['wec.1', 'wec.2', 'wec.3', 'wec.out', 'wec.p2f', 'wec.hst']
    for filename in del_files:
        file_path = os.path.join(workspace_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    subprocess.run([exe_path, 'fnames.wam'], cwd=workspace_dir, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
