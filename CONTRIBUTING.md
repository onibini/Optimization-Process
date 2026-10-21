# Contributing

Thanks for your interest in this project! Bug reports, questions and pull requests are welcome.

## Setup

```bash
pip install -r requirements-dev.txt
```

WAMIT is **not** needed for development: the unit tests run without it. Running a real optimization needs your own
WAMIT v7 license (see [README.md](README.md#prerequisites)).

## Before opening a pull request

Run all of the following and make sure they pass:

```bash
ruff check .
ruff format --check .
python -m unittest discover -s tests
```

- Add or update tests in `tests/` for every behavior change. Tests must not require WAMIT or a display.
- Keep Python 3.8 compatibility (`ruff.toml` sets `target-version = "py38"`).
- All design variables (radius, draft, x, y) must be positive; search ranges satisfy `0 < Min < Max`.
- Record each change in [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]` and add a report
  `docs/reports/YYYY-MM-DD_NN_<topic>.md` (see existing reports for the format).
- Do not commit run-time outputs (`logs/`, `workspace/`, `__pycache__/`).

## Reporting issues

Please use the issue templates and include your Python version, the relevant part of `config.cfg`, and (for WAMIT
problems) the tail of `workspace/errorp.log` / `errorf.log`. Do not attach WAMIT binaries or license files.
