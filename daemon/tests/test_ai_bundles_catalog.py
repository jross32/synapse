from __future__ import annotations

from synapse_daemon import ai_bundles

_EXPECTED_BUNDLES = {
    "deep-research-council",
    "fullstack-app-factory",
    "fast-money",
    "repo-rescue-lab",
    "parallel-harvest-bakeoff",
}


def test_bundled_ai_bundle_catalog_loads_cleanly() -> None:
    bundles = ai_bundles.load_catalog()
    ids = {bundle.id for bundle in bundles}
    missing = _EXPECTED_BUNDLES - ids
    assert not missing, f"expected bundled AI bundles missing from load: {missing}"

    for bundle in bundles:
        if bundle.id not in _EXPECTED_BUNDLES:
            continue
        assert bundle.name, f"{bundle.id}: empty name"
        assert bundle.description, f"{bundle.id}: empty description"
        assert bundle.tags, f"{bundle.id}: missing tags"
        assert bundle.quick_actions, f"{bundle.id}: missing quick actions"
        assert bundle.recommended_case_modes, f"{bundle.id}: missing recommended case modes"


def test_fast_money_bundle_exposes_launch_assets() -> None:
    bundle = ai_bundles.bundle_by_id("fast-money")
    role_ids = {role.id for role in bundle.roles}
    source_ids = {source.id for source in bundle.sources}
    quick_action_ids = {action.id for action in bundle.quick_actions}

    assert {
        "revenue-architect",
        "client-ops-operator",
        "billing-seam-planner",
    } <= role_ids
    assert "fast-money-monetization-notes" in source_ids
    assert quick_action_ids == {"fast-money-launch"}
    assert bundle.personalities[0].id == "revenue-operator"
    assert bundle.recipes[0].id == "client-ops-revenue-board"
