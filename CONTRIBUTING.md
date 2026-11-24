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
- Keep Python 3.10 compatibility (`ruff.toml` sets `target-version = "py310"`).
- All design variables (radius, draft, x, y) must be positive; search ranges satisfy `0 < Min < Max`.
- Describe the change and how you checked it in the pull request.
- Do not commit run-time outputs (`logs/`, `workspace/`, `__pycache__/`).

## Reporting issues

Please use the issue templates and include your Python version, the relevant part of `config.cfg`, and (for WAMIT
problems) the tail of `workspace/errorp.log` / `errorf.log`. Do not attach WAMIT binaries or license files.
