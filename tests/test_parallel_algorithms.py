from pathlib import Path

import numpy as np
import pytest

from wec_optimization.algorithms import run_cma_es, run_de, run_ga, run_pso


def quadratic_evaluation(vector, config):
    assert config["workspace_dir"]
    score = -float(np.sum((vector - 0.5) ** 2))
    return score, [score]


def interrupt_when_checkpoint_exists(vector, config):
    checkpoint_dir = Path(config["checkpoint_dir"])
    if list(checkpoint_dir.glob("*.pkl")):
        raise RuntimeError("simulated interruption")
    return quadratic_evaluation(vector, config)


def _parallel_config(tmp_path):
    return {
        "bounds": [[0.0, 0.0], [1.0, 1.0]],
        "dimensions": 2,
        "step_size": 0.1,
        "opt_mode": 1,
        "num_wecs": 1,
        "site_name": "Test",
        "concurrent_runs": 2,
        "workspace_root": str(tmp_path / "workspace"),
        "log_dir": str(tmp_path / "logs"),
    }


@pytest.mark.parametrize(
    "optimizer,kwargs",
    [
        (run_de, {"F": 0.5, "CR": 0.9}),
        (run_pso, {"w": 0.5, "c1": 1.5, "c2": 1.5}),
        (run_ga, {"mutation_rate": 0.1}),
        (run_cma_es, {"sigma_init": 0.3}),
    ],
)
def test_optimizer_supports_parallel_batch_evaluation(tmp_path, optimizer, kwargs):
    np.random.seed(7)

    best_vector, best_score = optimizer(
        config=_parallel_config(tmp_path),
        eval_func=quadratic_evaluation,
        pop_size=4,
        max_iter=1,
        **kwargs,
    )

    assert best_vector.shape == (2,)
    assert np.isfinite(best_score)


@pytest.mark.parametrize(
    "optimizer,kwargs",
    [
        (run_de, {"F": 0.5, "CR": 0.9}),
        (run_pso, {"w": 0.5, "c1": 1.5, "c2": 1.5}),
        (run_ga, {"mutation_rate": 0.1}),
        (run_cma_es, {"sigma_init": 0.3}),
    ],
)
def test_optimizer_resumes_after_generation_checkpoint(tmp_path, optimizer, kwargs):
    config = _parallel_config(tmp_path)
    config.update(
        {
            "checkpoint_dir": str(tmp_path / "checkpoints"),
            "checkpoint_enabled": True,
            "checkpoint_resume": True,
            "checkpoint_save_every": 1,
            "checkpoint_keep_completed": False,
            "concurrent_runs": 1,
        }
    )
    np.random.seed(11)

    with pytest.raises(RuntimeError, match="simulated interruption"):
        optimizer(
            config=config,
            eval_func=interrupt_when_checkpoint_exists,
            pop_size=4,
            max_iter=2,
            **kwargs,
        )

    checkpoint_files = list((tmp_path / "checkpoints").glob("*.pkl"))
    assert len(checkpoint_files) == 1

    best_vector, best_score = optimizer(
        config=config,
        eval_func=quadratic_evaluation,
        pop_size=4,
        max_iter=2,
        **kwargs,
    )

    assert best_vector.shape == (2,)
    assert np.isfinite(best_score)
    assert not list((tmp_path / "checkpoints").glob("*.pkl"))
