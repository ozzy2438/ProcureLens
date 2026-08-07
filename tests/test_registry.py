from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from procurelens.models.registry import promote_model_if_better


def _metrics(*, auc: float = 0.86, brier: float = 0.11, ece: float = 0.03) -> dict:
    return {
        "holdout_auc_roc": auc,
        "holdout_brier_score": brier,
        "holdout_ece": ece,
    }


def _client_with_champion(metrics: dict) -> MagicMock:
    client = MagicMock()
    client.get_model_version_by_alias.return_value = SimpleNamespace(version="1", run_id="run-1")
    client.get_run.return_value = SimpleNamespace(data=SimpleNamespace(metrics=metrics))
    return client


def test_promotion_accepts_non_regressing_candidate():
    client = _client_with_champion(_metrics())
    decision = promote_model_if_better(
        client,
        model_name="risk",
        challenger_version="2",
        challenger_run_id="run-2",
        challenger_metrics=_metrics(auc=0.86, brier=0.10, ece=0.04),
    )
    assert decision.accepted is True
    assert call("risk", "challenger", "2") in client.set_registered_model_alias.call_args_list
    assert call("risk", "champion", "2") in client.set_registered_model_alias.call_args_list
    client.set_tag.assert_any_call("run-2", "promotion.applied", "true")


@pytest.mark.parametrize(
    ("candidate", "failed_gate"),
    [
        (_metrics(auc=0.85), "auc_not_lower"),
        (_metrics(brier=0.12), "brier_not_worse"),
        (_metrics(ece=0.051), "ece_within_threshold"),
    ],
)
def test_promotion_rejects_failed_gate_without_changing_champion(candidate, failed_gate):
    client = _client_with_champion(_metrics())
    decision = promote_model_if_better(
        client,
        model_name="risk",
        challenger_version="2",
        challenger_run_id="run-2",
        challenger_metrics=candidate,
    )
    assert decision.accepted is False
    assert failed_gate in decision.reason
    assert call("risk", "champion", "2") not in client.set_registered_model_alias.call_args_list
    client.set_tag.assert_any_call("run-2", "promotion.applied", "false")


def test_first_model_promotes_only_when_absolute_ece_gate_passes():
    client = MagicMock()
    client.get_model_version_by_alias.side_effect = RuntimeError("alias missing")
    decision = promote_model_if_better(
        client,
        model_name="risk",
        challenger_version="1",
        challenger_run_id="run-1",
        challenger_metrics=_metrics(ece=0.04),
    )
    assert decision.accepted is True
    assert decision.champion_version is None
    assert call("risk", "champion", "1") in client.set_registered_model_alias.call_args_list


def test_registry_connectivity_error_is_not_treated_as_missing_champion():
    client = MagicMock()
    client.get_model_version_by_alias.side_effect = ConnectionError("connection refused")
    with pytest.raises(ConnectionError, match="connection refused"):
        promote_model_if_better(
            client,
            model_name="risk",
            challenger_version="2",
            challenger_run_id="run-2",
            challenger_metrics=_metrics(),
        )
    assert call("risk", "champion", "2") not in client.set_registered_model_alias.call_args_list
