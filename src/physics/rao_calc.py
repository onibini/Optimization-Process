import os

import numpy as np
from scipy.optimize import brentq

from src.physics.hydro import HydroData

# PTO 감쇠 규칙. 1: WEC별 고유주파수의 B_kk, 2: PTO 없는 RAO가 가장 큰 격자점의 B_kk(2026-11 이전 결과와 논문 첫 원고).
PTO_NATURAL_FREQUENCY = 1
PTO_RAO_PEAK = 2
PTO_RULES = {PTO_NATURAL_FREQUENCY: "radiation damping at the natural frequency", PTO_RAO_PEAK: "RAO peak (legacy)"}
DEFAULT_PTO_RULE = PTO_NATURAL_FREQUENCY

# 가진력 출력 파일: diffraction(.3, 기본) 또는 Haskind(.2).
# wamit_handler.EXCITATION_OUTPUT_OPTIONS와 같은 키를 사용합니다.
EXCITATION_FILES = {"diffraction": "wec.3", "haskind": "wec.2"}


class WamitOutputError(RuntimeError):
    """Raised when WAMIT finishes without the output needed for RAO calculation."""


def _require_output_file(filepath):
    if not os.path.exists(filepath):
        raise WamitOutputError(f"Required WAMIT output file was not found: {filepath}")


def get_volumes_from_out(workspace_dir, num_wecs):
    """.out 파일에서 첫 번째 부피 라인의 마지막 값(VOLZ)을 찾아 모든 기기에 동일하게 적용"""
    out_file = os.path.join(workspace_dir, "wec.out")
    _require_output_file(out_file)
    volume_val = None

    with open(out_file, encoding="utf-8") as f:
        for line in f:
            if "Volumes (VOLX,VOLY,VOLZ):" in line:
                parts = line.split(":")[-1].split()
                if parts:
                    volume_val = float(parts[-1])
                    break

    if volume_val is None:
        raise WamitOutputError(f"Could not find VOLZ volume data in WAMIT output: {out_file}")

    return [volume_val] * num_wecs


def get_c_mat_from_hst(workspace_dir, num_wecs, heave_dofs, rho, g):
    """WAMIT .hst 파일에서 첫 번째 대각(Heave) 강성 값을 찾아 모든 기기에 동일하게 적용"""
    C_mat = np.zeros((num_wecs, num_wecs))
    file_hst = os.path.join(workspace_dir, "wec.hst")
    _require_output_file(file_hst)
    c33_val = None

    with open(file_hst) as f:
        next(f)  # 헤더 스킵
        for line in f:
            if not line.strip() or line.startswith(("C", "*")):
                continue

            cols = line.split()
            if len(cols) >= 3:
                i, j = int(cols[0]), int(cols[1])
                if i == j and i in heave_dofs:
                    c33_val = float(cols[2]) * (rho * g)
                    break

    if c33_val is None:
        raise WamitOutputError(f"Could not find heave hydrostatic stiffness data in WAMIT output: {file_hst}")

    C_mat = np.eye(num_wecs) * c33_val

    return C_mat


def read_wamit_hydro(workspace_dir, num_wecs, rho=1025.0, g=9.80665, excitation="diffraction"):
    """WAMIT 출력(.out, .hst, .1, 가진력 .3 또는 .2)을 읽어 차원 있는 heave 계수(``HydroData``)로 만듭니다.

    - Added Mass (A): rho 곱함
    - Damping (B): rho * omega 곱함
    - Restoring (C): rho * g 곱함
    - Force (F): rho * g 곱함
    - Mass (M): rho * Volume

    :param excitation: 파랑 가진력의 출처. "diffraction"(기본, wec.3: 입사파+산란파 압력 적분) 또는
        "haskind"(wec.2: radiation 해로부터 계산).
    """
    if excitation not in EXCITATION_FILES:
        raise ValueError(f"excitation must be one of {sorted(EXCITATION_FILES)}, got {excitation!r}")
    heave_dofs = {3 + 6 * k: k for k in range(num_wecs)}

    # 질량 행렬(M)과 강성 행렬(C)
    volumes = get_volumes_from_out(workspace_dir, num_wecs)
    M_mat = np.diag([rho * v for v in volumes])
    C_mat = get_c_mat_from_hst(workspace_dir, num_wecs, heave_dofs, rho, g)

    file_1 = os.path.join(workspace_dir, "wec.1")
    file_2 = os.path.join(workspace_dir, EXCITATION_FILES[excitation])
    _require_output_file(file_1)
    _require_output_file(file_2)
    hydro_dict, force_dict = {}, {}

    with open(file_1) as f:
        for idx, line in enumerate(f):
            if idx == 0:  # 헤더 스킵
                continue
            if not line.strip() or line.startswith(("C", "*")):
                continue

            cols = line.split()
            omega = float(cols[0])
            i, j = int(cols[1]), int(cols[2])

            if i in heave_dofs and j in heave_dofs:
                if omega not in hydro_dict:
                    hydro_dict[omega] = {
                        "A_dim": np.zeros((num_wecs, num_wecs)),
                        "B_dim": np.zeros((num_wecs, num_wecs)),
                    }

                hydro_dict[omega]["A_dim"][heave_dofs[i], heave_dofs[j]] = float(cols[3]) * rho
                hydro_dict[omega]["B_dim"][heave_dofs[i], heave_dofs[j]] = float(cols[4]) * (rho * omega)

    with open(file_2) as f:
        for idx, line in enumerate(f):
            if idx == 0:  # 헤더 스킵
                continue
            if not line.strip() or line.startswith(("C", "*")):
                continue

            cols = line.split()
            omega = float(cols[0])
            i = int(cols[2])

            if i in heave_dofs:
                if omega not in force_dict:
                    force_dict[omega] = np.zeros(num_wecs, dtype=complex)

                force_dict[omega][heave_dofs[i]] = complex(float(cols[5]), float(cols[6])) * (rho * g)

    omega_list = sorted(hydro_dict.keys())
    if not omega_list:
        raise WamitOutputError(f"Could not find heave added-mass/damping data in WAMIT output: {file_1}")

    missing_force_omegas = [w for w in omega_list if w not in force_dict]
    if missing_force_omegas:
        raise WamitOutputError(
            f"Could not find excitation force data for {len(missing_force_omegas)} frequencies "
            f"in WAMIT output: {file_2}"
        )

    return HydroData(
        omegas=np.array(omega_list),
        added_mass=np.array([hydro_dict[w]["A_dim"] for w in omega_list]),
        damping=np.array([hydro_dict[w]["B_dim"] for w in omega_list]),
        excitation=np.array([force_dict[w] for w in omega_list]),
        mass=M_mat,
        stiffness=C_mat,
    )


def check_pto_rule(rule):
    """PTORule 값을 검증합니다."""
    if isinstance(rule, bool) or rule not in PTO_RULES:
        raise ValueError(f"PTORule must be one of {sorted(PTO_RULES)} ({PTO_RULES}), got {rule!r}")
    return rule


def natural_frequency(omegas, added_mass, mass, stiffness):
    """``omega^2 (m + A(omega)) = K``의 해를 돌려줍니다. A는 격자점 사이에서 선형 보간합니다.

    해가 여럿이면 가장 낮은 주파수를 씁니다. 격자 안에 해가 없으면(작은 WEC는 공진이 상한보다 높음) 가까운 격자 끝을
    돌려줍니다.
    """
    omegas = np.asarray(omegas, dtype=float)
    residual = omegas**2 * (mass + np.asarray(added_mass, dtype=float)) - stiffness
    crossings = np.flatnonzero((residual[:-1] < 0) & (residual[1:] >= 0))
    if crossings.size == 0:
        return float(omegas[-1] if residual[-1] < 0 else omegas[0])

    def at(omega):
        added = np.interp(omega, omegas, added_mass)
        return omega**2 * (mass + added) - stiffness

    return float(brentq(at, omegas[crossings[0]], omegas[crossings[0] + 1]))


def pto_at_natural_frequency(hydro):
    """WEC마다 자기 고유주파수(배열 안의 A_kk 기준)의 방사감쇠 B_kk를 PTO 감쇠로 돌려줍니다."""
    b_pto = np.zeros(hydro.num_wecs)
    for k in range(hydro.num_wecs):
        omega_n = natural_frequency(hydro.omegas, hydro.added_mass[:, k, k], hydro.mass[k, k], hydro.stiffness[k, k])
        b_pto[k] = np.interp(omega_n, hydro.omegas, hydro.damping[:, k, k])
    return b_pto


def pto_at_rao_peak(hydro):
    """WEC마다 PTO 없는 RAO가 가장 큰 격자점의 방사감쇠 B_kk를 PTO 감쇠로 돌려줍니다(예전 규칙)."""
    M_mat, C_mat = hydro.mass, hydro.stiffness
    base_rao = []
    for k, w in enumerate(float(w) for w in hydro.omegas):
        Z_base = -(w**2) * (M_mat + hydro.added_mass[k]) + 1j * w * hydro.damping[k] + C_mat
        base_rao.append(np.abs(np.linalg.solve(Z_base, hydro.excitation[k])))
    peak = np.argmax(np.array(base_rao), axis=0)
    return np.array([hydro.damping[peak[k]][k, k] for k in range(hydro.num_wecs)])


def rao_from_hydro(hydro, pto_rule=DEFAULT_PTO_RULE):
    """heave 계수(``HydroData``)로 PTO 감쇠를 정하고 최종 RAO를 계산합니다(해석기와 무관)."""
    omega_list = [float(w) for w in hydro.omegas]
    M_mat, C_mat = hydro.mass, hydro.stiffness
    check_pto_rule(pto_rule)
    b_pto_list = pto_at_natural_frequency(hydro) if pto_rule == PTO_NATURAL_FREQUENCY else pto_at_rao_peak(hydro)

    # PTO를 얹어서 최종 RAO 도출
    final_rao_results = []
    B_pto_mat = np.diag(b_pto_list)
    for k, w in enumerate(omega_list):
        B_total = hydro.damping[k] + B_pto_mat
        Z_final = -(w**2) * (M_mat + hydro.added_mass[k]) + 1j * w * B_total + C_mat
        X_final = np.linalg.solve(Z_final, hydro.excitation[k])
        final_rao_results.append({"omega": w, "rao_abs": np.abs(X_final), "b_pto": b_pto_list.copy()})

    return final_rao_results


def calculate_rao_matrix(
    workspace_dir, num_wecs, rho=1025.0, g=9.80665, excitation="diffraction", pto_rule=DEFAULT_PTO_RULE
):
    """WAMIT 출력 폴더에서 바로 최종 RAO를 계산합니다(``read_wamit_hydro`` + ``rao_from_hydro``)."""
    return rao_from_hydro(read_wamit_hydro(workspace_dir, num_wecs, rho, g, excitation), pto_rule)


if __name__ == "__main__":
    # 테스트용 워크스페이스 디렉토리와 기기 수
    workspace_dir = "workspace"
    num_wecs = 5

    rao = calculate_rao_matrix(workspace_dir, num_wecs)
