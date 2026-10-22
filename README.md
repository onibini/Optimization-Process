# WEC Array Shape and Layout Optimization Process

This repository contains Python-based optimization tools designed to optimize the geometry (shape) and spatial layout of Wave Energy Converters (WECs) in an array using various metaheuristic algorithms. Hydrodynamic coefficients and interactions are calculated using **WAMIT**.

## Key Features
- **Multi-Algorithm Support**: Includes Differential Evolution (DE), Particle Swarm Optimization (PSO), Genetic Algorithm (GA), and CMA-ES.
- **Symmetric Layout Mapping**: Employs coordinate canonicalization and mapping to eliminate geometric redundancy (symmetric placements) and drastically improve optimization convergence.
- **Evaluation Cache (Memory Function)**: Caches evaluation results to prevent redundant WAMIT hydrodynamic simulation runs.
- **Flexible Modes**:
  1. **Geometry Optimization**: Optimize the radius and draft of a single WEC.
  2. **Layout Optimization**: Optimize the 2D coordinates of multiple WECs.
  3. **Joint Optimization**: Simultaneously optimize both geometry and layout variables.

---

## Directory Structure

```
├── .github/               # CI (workflows/python-tests.yml), issue and pull request templates
├── main.py                # Main script to configure and execute optimization
├── config.cfg             # Configuration file (parameters, constraints, settings)
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Development dependencies (ruff)
├── ruff.toml              # Lint / format settings (ruff)
├── CHANGELOG.md           # Change history
├── CLAUDE.md              # Working rules for AI assistants
├── CONTRIBUTING.md        # How to report issues and contribute
├── LICENSE                # MIT
├── data/
│   └── env_data.csv       # Ocean environment wave spectrum parameters by site
├── docs/                  # Design documents and per-update reports (docs/reports/)
├── src/
│   ├── algorithms/        # Optimization engines (DE, PSO, GA, CMA-ES)
│   ├── problems/          # Optimization modes configurations and evaluations
│   ├── physics/           # WAMIT integration, mesh generation, power calculations
│   └── utils/             # Config parser, data loaders, geometric checks, and coordinate mappers
├── tests/                 # Unit / regression tests (no WAMIT required)
├── logs/                  # Optimization histories (created at run time, ignored in Git)
└── workspace/             # WAMIT inputs/outputs (created at run time, ignored in Git)
```

---

## Prerequisites

- **Python**: Version 3.10 or higher.
- **WAMIT**: WAMIT v7 (32-bit), a commercial BEM solver that is **not included** in this repository and requires your own license. Hydrodynamic evaluation is Windows-only. Without WAMIT you can still run the unit tests and lint (`python -m unittest discover -s tests`).
  - The executable is looked up in this order: `WAMITPath` in [config.cfg](config.cfg) → environment variable `WAMIT_EXE` → `C:\WAMITv7\WAMIT.exe`.
  - If the path contains spaces, use the `WAMIT_EXE` environment variable (config values cannot contain spaces).

---

## Getting Started

### 1. Install Python Dependencies
Install the required packages listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 2. Configure Optimization
Edit the [config.cfg](config.cfg) file to adjust the simulation parameters. Each line is `value  name  - comment`. You can change:
- **Optimization Mode** (`OptMode`): 1 (Geometry), 2 (Layout), 3 (Both)
- **Algorithm** (`Algorithm`): 1 (DE), 2 (PSO), 3 (GA), 4 (CMA-ES)
- **WEC Count** (`NumWECs`): 1, 3, or 5
- **WEC Parameters** & boundary constraints.

> **All design variables must be positive.** Every search range (`RadiusMin/Max`, `DraftMin/Max`, `WECn_XMin/Max`, `WECn_YMin/Max`) must satisfy `0 < Min < Max`, and `FixedRadius`, `FixedDraft`, `MinSpacing`, `StepSize` must be `> 0`. Otherwise the run stops at start-up with a `ConfigValidationError` that lists the offending variables.
>
> **Grid step per variable.** `StepSize` is the default grid spacing for every design variable. To use a different spacing for one variable, add (uncomment) a `{Variable}Step` line in `[Constraints]`, e.g. `0.5  WEC2_YStep`. Available keys: `RadiusStep`, `DraftStep`, `WEC1_XStep`, `WEC2_XStep`, `WEC2_YStep`, `WEC3_XStep`, `WEC3_YStep`. Each step must be `> 0` and `<= Max - Min`; if `Max - Min` is not a multiple of the step, a warning shows the actual reachable maximum.
>
> **WAMIT speed/accuracy options** (`[WAMIT Settings]`). `MeshPanels` sets the panels per body (quarter model, default 120: within about 0.5% in total power and 1.2% per WEC for most 5-WEC designs at about 12 s per evaluation; use 160 or more for slender shapes such as small R with large D, tightly spaced arrays or when per-WEC accuracy matters, and 150-250 for a single WEC; evaluation time grows with roughly the 2.5-3rd power of the panel count); `Solver` selects the linear solver (default `0`, iterative: same results as the direct solver `1`, faster for larger runs; a warning lists frequencies where it hit the iteration limit); `OmegaMax` sets the upper end of the frequency grid (0.5 rad/s upward in 0.05 steps, default 3.0). Lowering `OmegaMax` speeds up each run, but small, shallow WECs resonate at high frequency, so keep 3.0 if the search range includes them (a warning is issued when the response is not negligible at the highest frequency). The uniform 0.05 grid can also under-resolve a narrow resonance peak; compare against a finer grid when accuracy matters.
>
> `Draft` is the length of the **cylindrical part only**. A hemispherical bottom of radius `R` is attached below it, so the total draft is `Draft + Radius`.

### 3. Run Optimization
Run the main script:
```bash
python main.py
```
Optimization progress is printed to the terminal (`Hits` = cache hits, `WAMIT` = actual WAMIT runs, `Penalty` = infeasible designs rejected without WAMIT). When the run ends, the best design (vector, radius, draft, body coordinates) is printed.

### 4. Output Logs
Each run writes four files to `logs/` with a unique prefix `{SiteName}_{algorithm}_{YYYYmmdd_HHMMSS}`, so runs never overwrite each other:

| File | Contents |
| :--- | :--- |
| `*_config.json` | Problem configuration used for the run (bounds, environment, etc.) |
| `*_trial_history.csv` | Every unique design evaluated (`penalized` = 1 if rejected by constraints) |
| `*_generation_history.csv` | Best-so-far design per generation and elapsed time |
| `*_summary.json` | Final best design, generations completed, WAMIT/penalty/cache counts (also written if the run is interrupted) |

`algorithm` is one of `de`, `pso`, `ga`, `cmaes`.

---

## Development

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests   # tests (no WAMIT needed)
ruff check .                           # lint
ruff format .                          # format
```

GitHub Actions ([python-tests.yml](.github/workflows/python-tests.yml)) runs the same lint and test steps on Python 3.10 and 3.12 for every push and pull request.

Every update is recorded in [CHANGELOG.md](CHANGELOG.md) with a detailed report under [docs/reports/](docs/reports/).

## License

[MIT](LICENSE)
