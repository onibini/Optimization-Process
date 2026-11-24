"""시험용 가짜 WAMIT 출력 (WAMIT 없이 읽기 경로를 시험)."""

import os


def write_two_wec_workspace(path, omegas, damping_scale=1.0):
    """Synthetic WAMIT output for two heaving WECs: heave resonance near 0.63 rad/s, B(omega) rising with omega."""
    with open(os.path.join(path, "wec.out"), "w") as f:
        f.write(" Volumes (VOLX,VOLY,VOLZ):   0.0  0.0  2.0\n")
    with open(os.path.join(path, "wec.hst"), "w") as f:
        f.write(" header\n   3   3   0.1\n   9   9   0.1\n")
    with open(os.path.join(path, "wec.1"), "w") as f:
        f.write(" header\n")
        for w in omegas:
            b = damping_scale * (0.05 + 0.2 * w * w)
            f.write(f"{w:.6f} 3 3 0.5 {b:.9f}\n")
            f.write(f"{w:.6f} 9 9 0.5 {1.1 * b:.9f}\n")
            f.write(f"{w:.6f} 3 9 0.05 0.01\n")
            f.write(f"{w:.6f} 9 3 0.05 0.01\n")
            f.write(f"{w:.6f} 1 1 9.9 9.9\n")
    with open(os.path.join(path, "wec.3"), "w") as f:
        f.write(" header\n")
        for w in omegas:
            f.write(f"{w:.6f} 0.0 3 0.0 0.0 {w:.6f} 0.1\n")
            f.write(f"{w:.6f} 0.0 9 0.0 0.0 {0.8 * w:.6f} 0.05\n")
