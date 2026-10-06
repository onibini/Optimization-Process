# WEC Array Optimization

Python tools for optimizing the geometry and symmetric array layout of wave energy converters (WECs). The project includes Differential Evolution, Particle Swarm Optimization, Genetic Algorithm, and CMA-ES implementations, and uses WAMIT for hydrodynamic analysis.

## Features

- Geometry, layout, and joint geometry-layout optimization modes
- Grid-aware candidate repair and evaluation caching
- Canonical mapping of symmetric layouts to remove duplicate search states
- WAMIT input generation, execution, RAO processing, and power calculation
- Unit tests and GitHub Actions continuous integration

## Requirements

- Python 3.10 or newer
- WAMIT v7 on Windows (required for a full optimization run)
- A valid WAMIT installation at `C:\WAMITv7`, unless the integration path is customized

WAMIT is proprietary software and is not included in this repository. Unit tests do not invoke WAMIT.

## Installation

Create and activate a virtual environment, then install the project:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

For development and testing:

```powershell
python -m pip install -e ".[dev]"
```

## Configuration and execution

Edit [`config.cfg`](config.cfg) to select the optimization mode, algorithm, WEC count, search bounds, environment, and WAMIT resources. Then run:

```powershell
wec-optimize --config config.cfg
```

The equivalent module command is:

```powershell
python -m wec_optimization --config config.cfg
```

Generated WAMIT files, logs, and optimization results are written to ignored local directories and are not committed.

`AvailableCPUs` and `AvailableRAMGB` are total budgets for all WAMIT processes, while `ConcurrentRuns` controls how many candidate solutions are evaluated simultaneously. Per-process resources are calculated with integer division. For example, 6 CPUs, 16 GB RAM, and 3 concurrent runs allocate 2 CPUs and 5 GB to each WAMIT process. Any remainder is intentionally left unused to avoid oversubscription.

Successful candidate workspaces are deleted by default after their results have been parsed. Failed workspaces remain available for diagnosis. Set `KeepWorkspaces` to `1` when raw WAMIT files must be retained for every candidate; these files can consume significant disk space during long runs.

Optimizer state is saved under `checkpoints/` at generation boundaries. When `Resume=1`, a restarted command resumes only if the algorithm and result-affecting settings exactly match the checkpoint fingerprint. Population state, algorithm-specific state, the in-memory evaluation cache, and NumPy random state are restored together. Checkpoints are deleted after successful completion unless `KeepOnCompletion=1`.

## Tests

```powershell
python -m pytest
```

Run static analysis and formatting checks with Ruff:

```powershell
python -m ruff check src tests
python -m ruff format --check src tests
```

The tests cover coordinate mapping, geometry constraints, environment-data loading, grid quantization, CMA-ES scaling, and evaluation caching. A full WAMIT optimization is intentionally outside the unit-test suite.

## Repository layout

```text
.
├── .github/workflows/       # Continuous integration
├── docs/                    # Architecture and algorithm notes
├── src/wec_optimization/    # Installable Python package
│   ├── algorithms/          # DE, PSO, GA, and CMA-ES
│   ├── data/                # Packaged environmental reference data
│   ├── physics/             # Mesh, WAMIT, RAO, and power calculations
│   ├── problems/            # Shape, layout, and joint problem definitions
│   ├── utils/               # Data, geometry, and mapping helpers
│   └── cli.py               # Command-line entry point
├── tests/                   # Unit tests
├── config.cfg               # Example/runtime configuration
├── pyproject.toml           # Package, dependency, and test configuration
└── LICENSE
```

## Documentation

- [Architecture](docs/architecture.md)
- [Algorithms and optimization problems](docs/algorithms_and_problems.md)
- [Development conventions](docs/conventions.md)
- [Development report](docs/development_report.md)

## License

This project is distributed under the terms in [LICENSE](LICENSE).
