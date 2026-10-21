# System Architecture Reference (for LLM / AI Assistants)

This document provides a high-level system architecture overview of the WEC Array Shape and Layout Optimization Process project.

---

## 1. System Overview

This project is a scientific optimization framework written in Python. It optimizes the shape and layout of Wave Energy Converters (WECs) to maximize the total absorbed power (ideal linear PTO). The system integrates a custom metaheuristic optimization engine with **WAMIT** (Wave Analysis at Massachusetts Institute of Technology), a boundary element method solver used to calculate hydrodynamic coefficients.

---

## 2. Directory and File Map

```
├── main.py                    # Entry point. Parses config, builds the problem, runs the engine, prints the best design.
├── config.cfg                 # Optimization parameters, limits, constraints, and physical environment specifications.
├── requirements.txt           # External Python library dependencies (numpy, scipy, gmsh).
├── requirements-dev.txt       # Development dependencies (ruff).
├── ruff.toml                  # Ruff lint/format configuration.
├── CHANGELOG.md               # Change history ([Unreleased] + released versions).
├── CLAUDE.md                  # Working rules for AI assistants (read first).
├── CONTRIBUTING.md            # Contribution guide (setup, checks, report/CHANGELOG rules).
├── .github/workflows/python-tests.yml  # GitHub Actions: ruff lint/format + unittest (Python 3.10, 3.12).
├── .github/ISSUE_TEMPLATE/, pull_request_template.md  # Issue / PR templates.
│
├── data/
│   └── env_data.csv           # Significant wave heights (Hs), wave periods (Tp), water depths (Depth) by site.
│
├── src/
│   ├── algorithms/            # Optimization algorithms (Metaheuristics)
│   │   ├── common.py          # Shared CachedEvaluator, OptimizationLogger, grid quantization helpers
│   │   ├── de.py              # Differential Evolution (DE/rand/1/bin)
│   │   ├── pso.py             # Particle Swarm Optimization (PSO)
│   │   ├── ga.py              # Genetic Algorithm (GA)
│   │   └── cma_es.py          # Covariance Matrix Adaptation Evolution Strategy (CMA-ES)
│   │
│   ├── problems/              # Optimization problem configurations & evaluation functions
│   │   ├── shape_opt.py       # Geometry optimization (Single WEC radius & draft)
│   │   ├── layout_opt.py      # Layout optimization (Multi WEC coordinates)
│   │   └── joint_opt.py       # Joint shape & layout optimization
│   │
│   ├── physics/               # Hydrodynamic simulation wrapper and calculations
│   │   ├── wamit_handler.py   # Writes WAMIT configuration/POT/FRC files and runs WAMIT.exe (WamitRunError on failure)
│   │   ├── mesh_axisymmetric_shape.py # Axisymmetric WEC mesh generation (profile revolve + Gmsh export to GDF)
│   │   ├── rao_calc.py        # Parses WAMIT output files (.out, .hst, .1, .3) to extract RAO matrices
│   │   ├── power_calc.py      # Calculates power output using wave spectrum integrations
│   │   └── wave_spectrum.py   # Generates JONSWAP wave spectrum density distributions
│   │
│   └── utils/                 # Utilities and helper modules
│       ├── config_parser.py   # Parses config.cfg ("value name - comment"), supports negative values
│       ├── data_handler.py    # Loads ocean environment data from CSV
│       ├── geometry.py        # Minimum distance constraint check and penalty_result()
│       ├── mapper.py          # Maps 1D optimization vectors to 2D coordinates and canonicalizes them
│       └── validation.py      # Positivity checks (0 < Min < Max) and per-variable grid step resolution
│
└── tests/
    ├── test_utils.py          # Mapper, geometry, data loader, quantization, cache tests
    ├── test_fixes.py          # Regression tests: config parser, logging, penalty counting, canonical consistency, WAMIT errors
    ├── test_validation.py     # Positive design-variable rule (config validation + optimizers stay positive)
    └── test_step_size.py      # Per-variable grid steps, upper-bound reachability, WAMIT output options, site data

docs/
├── architecture.md / algorithms_and_problems.md / conventions.md
└── reports/                   # One report per update: YYYY-MM-DD_NN_<title>.md
```

---

## 3. Core Execution Flow

```
[User Execution (python main.py)]
              │
              ▼
    [Load config.cfg] ──► [Load data/env_data.csv (Site ID)]
              │
              ▼
   [Setup Optimization Mode + validate bounds (0 < Min < Max)]
     ├─ Mode 1 (Geometry): shape_opt.py (eval_func = evaluate_shape)
     ├─ Mode 2 (Layout): layout_opt.py (eval_func = evaluate_layout)
     └─ Mode 3 (Joint): joint_opt.py (eval_func = evaluate_joint)
              │
              ▼
   [Initialize Algorithm Engine (de.py, pso.py, ga.py, cma_es.py)]
              │
              ▼
  ┌───► [Generate/Update Trial Vector]
  │           │
  │           ▼
  │     [Quantize + Canonicalize (CachedEvaluator)] (utils/mapper.py)
  │           │
  │           ▼
  │     [Check Memory Cache (dict)] ──(Hit)──► [Return Stored Fitness] ──┐
  │           │                                                          │
  │         (Miss)                                                       │
  │           │                                                          │
  │           ▼                                                          │
  │     [Evaluate Vector (eval_func)]                                    │
  │       ├─ Check Constraints (utils/geometry.py) ──(Violated)──► [Penalty, no WAMIT]
  │       ├─ Generate Mesh (physics/mesh_axisymmetric_shape.py)          │
  │       ├─ Run WAMIT Solver (physics/wamit_handler.py)                 │
  │       └─ Calculate Power (physics/power_calc.py)                     │
  │           │                                                          │
  │           ▼                                                          │
  │     [Save to Cache & Trial Log]                                      │
  │           │                                                          │
  │           ▼                                                          │
  │     [Update Selection/Population] ◄──────────────────────────────────┘
  │           │
  └───── [Loop until MaxIter]
              │
              ▼
     [Write summary.json, print best design]
```

---

## 4. LLM Developer Notes

- **Evaluation function contract**: `eval_func(vector, config)` returns `(score, individual_powers)` or `(score, individual_powers, info)`. Constraint-violating designs return `penalty_result(...)`, whose `info = {"penalized": True}` lets `CachedEvaluator` count them separately from real WAMIT runs (`physics_evals` vs `penalty_evals`).
- **Cache Strategy**: Evaluation is cached by `CachedEvaluator` in `src/algorithms/common.py` on a `StepSize`-based grid-index key. Trial vectors are quantized to the configured grid and canonicalized (in place) before cache lookup. PSO and CMA-ES pass a *copy* to the evaluator so that their internal state (particle position/velocity, distribution samples) is not reordered by canonicalization.
- **Logging**: `OptimizationLogger(config, algorithm=...)` writes `logs/{Site}_{algorithm}_{YYYYmmdd_HHMMSS}_{config.json|trial_history.csv|generation_history.csv|summary.json}`. Files are opened in exclusive-create mode and a numeric suffix is added on collision, so runs never overwrite each other. The summary is written in a `finally` block, so interrupted runs still record their best design.
- **Mesh Reuse**: WAMIT GDF mesh generation is skipped when the existing `wec.gdf` metadata matches the requested radius, draft, and mesh density.
- **WAMIT Interface**: Communication with WAMIT is file-based via the `./workspace` directory. Input files (`.pot`, `.frc`, `.gdf`, `fnames.wam`, `wec.cfg`, `config.wam`) are written before execution, and results (`wec.out`, `wec.1`, etc.) are parsed post-execution. Previous outputs and `errorp.log`/`errorf.log` are deleted before each run; a non-zero exit raises `WamitRunError` with WAMIT's stdout/stderr and error-log tails.
- **Wall condition**: `wec.cfg` sets `IWALLX0=0` for OptMode 1 and `IWALLX0=1` (vertical wall on x=0) for OptMode 2 and 3.
- **Grid steps**: `config['step_size']` is a list with one step per design variable (`resolve_step_sizes`: `{Var}Step` key, else `StepSize`). `grid_max_indices` adds a small tolerance so float error never drops the upper bound (e.g. (30-0.1)/0.1).
- **WAMIT outputs**: `.frc` requests only `.1` (added mass/damping) and `.3` (diffraction exciting force, used for the RAO). `.2` (Haskind) is off by default; `calculate_rao_matrix(..., excitation="haskind")` and `write_frc_file(..., excitation="haskind")` switch back.
- **Positivity rule**: all design variables (R, D, x, y) are strictly positive. `get_*_config` calls `validate_design_bounds` / `require_positive` and raises `ConfigValidationError`; `write_wamit_inputs` also refuses non-positive radius/draft as a last guard.
- **Geometry convention**: `Draft` is the cylindrical length; total draft = `Draft + Radius` (hemispherical bottom).
