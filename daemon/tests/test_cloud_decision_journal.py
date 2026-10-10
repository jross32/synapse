from __future__ import annotations

import pytest
from synapse_daemon import cloud_decision_journal as j


def test_proposal_and_immutable_events(tmp_path):
    row = j.create_proposal(tmp_path, project="Synapse", workload="heartbeat",
                            reason="remote coordination", placement="hybrid", max_estimate_usd=2.5)
    assert row["status"] == "proposed"
    assert len(row["events"]) == 1
    assert j.list_decisions(tmp_path)[0]["id"] == row["id"]
    row = j.change_status(tmp_path, row["id"], "approved", actor="owner", note="Budget OK")
    assert len(row["events"]) == 2
    assert row["events"][-1]["actor"] == "owner"
    assert row["events"][0]["to_status"] == "proposed"
    row = j.change_status(tmp_path, row["id"], "deployed", actor="operator")
    assert len(row["events"]) == 3


def test_invalid_transition_rejected_without_mutation(tmp_path):
    row = j.create_proposal(tmp_path, project="Synapse", workload="cloud",
                            reason="availability", placement="railway")
    with pytest.raises(ValueError):
        j.change_status(tmp_path, row["id"], "deployed", actor="ai")
    assert j.get_decision(tmp_path, row["id"])["status"] == "proposed"
    assert len(j.get_decision(tmp_path, row["id"])["events"]) == 1


@pytest.mark.parametrize("price", [-1, float("nan"), float("inf"), True])
def test_invalid_price(tmp_path, price):
    with pytest.raises(ValueError):
        j.create_proposal(tmp_path, project="a", workload="b", reason="c",
                          placement="railway", max_estimate_usd=price)


def test_rejected_cannot_be_reopened(tmp_path):
    row = j.create_proposal(tmp_path, project="a", workload="b", reason="c", placement="local")
    j.change_status(tmp_path, row["id"], "rejected", actor="owner")
    with pytest.raises(ValueError):
        j.change_status(tmp_path, row["id"], "approved", actor="ai")


def test_invalid_id_and_placement(tmp_path):
    with pytest.raises(ValueError):
        j.get_decision(tmp_path, "../other")
    with pytest.raises(ValueError):
        j.create_proposal(tmp_path, project="a", workload="b", reason="c", placement="unknown")
