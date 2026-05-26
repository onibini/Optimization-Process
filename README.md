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
├── main.py                # Main script to configure and execute optimization
├── config.cfg             # Configuration file (parameters, constraints, settings)
├── requirements.txt       # List of Python dependencies
├── data/
│   └── env_data.csv       # Ocean environment wave spectrum parameters by site
├── src/
│   ├── algorithms/        # Optimization engines (DE, PSO, GA, CMA-ES)
│   ├── problems/          # Optimization modes configurations and evaluations
│   ├── physics/           # WAMIT integration, mesh generation, power calculations
│   └── utils/             # Data loaders, geometric checks, and coordinate mappers
└── workspace/             # Directory where WAMIT inputs/outputs are written (ignored in Git)
```

---

## Prerequisites

- **Python**: Version 3.8 or higher.
- **WAMIT**: WAMIT v7 (installed by default in `C:\WAMITv7` on Windows).

---

## Getting Started

### 1. Install Python Dependencies
Install the required packages listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 2. Configure Optimization
Edit the [config.cfg](config.cfg) file to adjust the simulation parameters. You can change:
- **Optimization Mode** (`OptMode`): 1 (Geometry), 2 (Layout), 3 (Both)
- **Algorithm** (`Algorithm`): 1 (DE), 2 (PSO), 3 (GA), 4 (CMA-ES)
- **WEC Count** (`NumWECs`): 1, 3, or 5
- **WEC Parameters** & boundary constraints.

### 3. Run Optimization
Run the main script:
```bash
python main.py
```
Optimization progress will be printed to the terminal, and generation/trial histories will be saved under the `logs/` directory.
