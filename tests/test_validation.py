import math
from pathlib import Path

import numpy as np
import pytest

from wec_optimization.algorithms.common import (
    CachedEvaluator,
    get_bounds,
    validate_optimizer_inputs,
)
from wec_optimization.cli import get_wamit_runtime_settings, parse_wec_cfg
from wec_optimization.physics.mesh_axisymmetric_shape import (
    get_cylinder_hemisphere_profile,
    revolve_profile,
)
from wec_optimization.physics.power_calc import calculate_power
from wec_optimization.problems.layout_opt import get_layout_config


class NullLogger:
    def write_trial(self, vector, score, individual_powers):
        pass


def parallel_workspace_evaluation(vector, config):
    return float(np.sum(vector)), [config["workspace_dir"]]


def workspace_creating_evaluation(vector, config):
    workspace = Path(config["workspace_dir"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "result.out").write_text("completed", encoding="utf-8")
    return float(np.sum(vector)), [0.0]


def failing_workspace_evaluation(vector, config):
    workspace = Path(config["workspace_dir"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "failure.log").write_text("failed", encoding="utf-8")
    raise RuntimeError("simulated WAMIT failure")


def _base_config():
    return {
        "bounds": [[0.0, 0.0], [1.0, 1.0]],
        "dimensions": 2,
        "step_size": 0.1,
        "opt_mode": 1,
        "num_wecs": 1,
    }


def test_config_parser_preserves_negative_values(tmp_path):
    config_path = tmp_path / "negative.cfg"
    config_path.write_text(
        "[Constraints]\n-10.5 WEC1_XMin - negative lower bound\n",
        encoding="utf-8",
    )

    parsed = parse_wec_cfg(config_path)

    assert parsed["Constraints"]["WEC1_XMin"] == "-10.5"


def test_config_parser_rejects_malformed_entries(tmp_path):
    config_path = tmp_path / "invalid.cfg"
    config_path.write_text("[Simulation]\ninvalid\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid configuration entry"):
        parse_wec_cfg(config_path)


def test_bounds_reject_inverted_interval():
    with pytest.raises(ValueError, match="upper bound"):
        get_bounds({"bounds": [[1.0], [0.0]]})


def test_optimizer_validation_rejects_dimension_mismatch():
    config = _base_config()
    config["dimensions"] = 3

    with pytest.raises(ValueError, match="do not match"):
        validate_optimizer_inputs(config, pop_size=4, max_iter=1)


def test_optimizer_validation_rejects_zero_iterations():
    with pytest.raises(ValueError, match="at least 1"):
        validate_optimizer_inputs(_base_config(), pop_size=4, max_iter=0)


def test_cached_evaluator_rejects_non_finite_score():
    evaluator = CachedEvaluator(
        _base_config(),
        lambda _vector, _config: (math.nan, [0.0]),
        NullLogger(),
    )

    with pytest.raises(ValueError, match="non-finite"):
        evaluator.evaluate(np.array([0.5, 0.5]))


def test_power_calculation_rejects_empty_results():
    with pytest.raises(ValueError, match="must not be empty"):
        calculate_power([], {})


def test_layout_config_rejects_unsupported_wec_count():
    constraints = {"StepSize": "0.1", "WEC1_XMin": "0", "WEC1_XMax": "1"}

    with pytest.raises(ValueError, match="1, 3, or 5"):
        get_layout_config(constraints, {}, 2, {}, {}, 1)


def test_hemisphere_profile_has_single_exact_pole():
    profile = get_cylinder_hemisphere_profile(2.0, 3.0, 3, 4)

    assert np.count_nonzero(profile[:, 0] == 0.0) == 1
    np.testing.assert_allclose(profile[-1], [0.0, -5.0])
    assert not np.any(np.all(np.diff(profile, axis=0) == 0.0, axis=1))


def test_revolved_profile_uses_triangles_at_pole():
    profile = get_cylinder_hemisphere_profile(2.0, 3.0, 2, 2)

    nodes, quads, triangles = revolve_profile(profile, num_angular_segments=4)

    assert len(nodes) % 3 == 0
    assert len(quads) // 4 == 12
    assert len(triangles) // 3 == 4


def test_wamit_cpu_budget_is_split_across_concurrent_runs():
    settings = get_wamit_runtime_settings(
        {
            "AvailableCPUs": "6",
            "AvailableRAMGB": "16",
            "ConcurrentRuns": "3",
            "KeepWorkspaces": "0",
        }
    )

    assert settings == {
        "NCPU": 2,
        "RAMGBMAX": 5,
        "ConcurrentRuns": 3,
        "KeepWorkspaces": False,
    }


def test_wamit_parallelism_rejects_cpu_oversubscription():
    with pytest.raises(ValueError, match="between 1 and AvailableCPUs"):
        get_wamit_runtime_settings(
            {"AvailableCPUs": "2", "ConcurrentRuns": "3", "AvailableRAMGB": "8"}
        )


def test_batch_evaluator_deduplicates_and_uses_distinct_workspaces(tmp_path):
    config = _base_config()
    config.update({"concurrent_runs": 2, "workspace_root": str(tmp_path)})
    logger = NullLogger()
    evaluator = CachedEvaluator(config, parallel_workspace_evaluation, logger)
    vectors = [
        np.array([0.1, 0.2]),
        np.array([0.8, 0.9]),
        np.array([0.11, 0.19]),
    ]

    results = evaluator.evaluate_many(vectors)

    assert evaluator.total_evals == 2
    assert evaluator.cache_hits == 1
    assert results[0] == results[2]
    assert results[0][1][0] != results[1][1][0]


def test_successful_candidate_workspaces_are_removed(tmp_path):
    workspace_root = tmp_path / "workspace"
    config = _base_config()
    config.update({"workspace_root": str(workspace_root), "keep_workspaces": False})
    evaluator = CachedEvaluator(config, workspace_creating_evaluation, NullLogger())

    evaluator.evaluate_many([np.array([0.2, 0.3])])

    assert not list(workspace_root.glob("eval_*"))


def test_candidate_workspace_can_be_retained(tmp_path):
    workspace_root = tmp_path / "workspace"
    config = _base_config()
    config.update({"workspace_root": str(workspace_root), "keep_workspaces": True})
    evaluator = CachedEvaluator(config, workspace_creating_evaluation, NullLogger())

    evaluator.evaluate_many([np.array([0.2, 0.3])])

    assert len(list(workspace_root.glob("eval_*"))) == 1


def test_failed_candidate_workspace_is_retained(tmp_path):
    workspace_root = tmp_path / "workspace"
    config = _base_config()
    config.update({"workspace_root": str(workspace_root), "keep_workspaces": False})
    evaluator = CachedEvaluator(config, failing_workspace_evaluation, NullLogger())

    with pytest.raises(RuntimeError, match="simulated WAMIT failure"):
        evaluator.evaluate_many([np.array([0.2, 0.3])])

    assert len(list(workspace_root.glob("eval_*"))) == 1
