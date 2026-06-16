# System Architecture Reference (for LLM / AI Assistants)

This document provides a high-level system architecture overview of the WEC Array Shape and Layout Optimization Process project.

---

## 1. System Overview

This project is a scientific optimization framework written in Python. It optimizes the shape and layout of Wave Energy Converters (WECs) to maximize total electrical power output. The system integrates a custom metaheuristic optimization engine with **WAMIT** (Wave Analysis at Massachusetts Institute of Technology), a boundary element method solver used to calculate hydrodynamic coefficients.

---

## 2. Directory and File Map

```
├── main.py                    # Entry point of the optimization process. Parses configs, initializes models, runs engine.
├── config.cfg                 # Optimization parameters, limits, constraints, and physical environment specifications.
├── requirements.txt           # External Python library dependencies (numpy, scipy, matplotlib, gmsh).
│
├── data/
│   └── env_data.csv           # Significant wave heights (Hs), wave periods (Tp), water depths (Depth) by site.
│
├── src/
│   ├── algorithms/            # Optimization algorithms (Metaheuristics)
│   │   ├── common.py          # Shared cached evaluator and CSV logging utilities
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
│   │   ├── wamit_handler.py   # Writes WAMIT configuration/POT/FRC files and runs WAMIT.exe
│   │   ├── mesh_axisymmetric_shape.py # Axisymmetric WEC mesh generation using Gmsh API
│   │   ├── rao_calc.py        # Parses WAMIT output files (.out, .1, etc.) to extract RAO matrices
│   │   ├── power_calc.py      # Calculates power output using wave spectrum integrations
│   │   └── wave_spectrum.py   # Generates JONSWAP wave spectrum density distributions
│   │
│   └── utils/                 # Utilities and helper modules
│       ├── data_handler.py    # Loads ocean environment data from CSV
│       ├── geometry.py        # Checks minimum distance constraints between WECs
│       └── mapper.py          # Maps 1D optimization vectors to 2D coordinates and canonicalizes them
```

---

## 3. Core Execution Flow

The system operates in a sequential pipeline described by the diagram below:

```
[User Execution (python main.py)]
              │
              ▼
    [Load config.cfg] ──► [Load data/env_data.csv (Site ID)]
              │
              ▼
   [Setup Optimization Mode]
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
  │     [Canonicalize Vector In-Place] (utils/mapper.py)
  │           │
  │           ▼
  │     [Check Memory Cache (dict)] ──(Hit)──► [Return Stored Fitness] ──┐
  │           │                                                          │
  │         (Miss)                                                       │
  │           │                                                          │
  │           ▼                                                          │
  │     [Evaluate Vector (eval_func)]                                    │
  │       ├─ Check Constraints (utils/geometry.py) ──(Violated)──► [Penalty]
  │       ├─ Generate Mesh (physics/mesh_axisymmetric_shape.py)          │
  │       ├─ Run WAMIT Solver (physics/wamit_handler.py)                 │
  │       └─ Calculate Power (physics/power_calc.py)                     │
  │           │                                                          │
  │           ▼                                                          │
  │     [Save to Cache & Logs]                                           │
  │           │                                                          │
  │           ▼                                                          │
  │     [Update Selection/Population] ◄──────────────────────────────────┘
  │           │
  └───── [Loop until MaxIter]
              │
              ▼
     [Return Optimal Vector & Fitness]
```

---

## 4. LLM Developer Notes

- **Cache Strategy**: Evaluation is cached by `CachedEvaluator` in `src/algorithms/common.py` on a `StepSize`-based grid-index key. Trial vectors are quantized to the configured grid and canonicalized before cache lookup.
- **Mesh Reuse**: WAMIT GDF mesh generation is skipped when the existing `wec.gdf` metadata matches the requested radius, draft, and mesh density.
- **WAMIT Interface**: Communication with WAMIT is file-based via the `./workspace` directory. Input files (`.pot`, `.frc`, `.gdf`, `fnames.wam`, `wec.cfg`, `config.wam`) are written before execution, and results (`wec.out`, `wec.1`, etc.) are parsed post-execution.
