from synapse_daemon.project_git_policy import provision_new_project_policy


def test_creates_policy_for_new_project(tmp_path):
    assert provision_new_project_policy(tmp_path)
    content = (tmp_path / 'AGENTS.md').read_text(encoding='utf-8')
    assert 'coordination session' in content
    assert 'GitHub' in content


def test_existing_policy_is_never_overwritten(tmp_path):
    policy = tmp_path / 'AGENTS.md'
    policy.write_text('custom policy', encoding='utf-8')
    assert not provision_new_project_policy(tmp_path)
    assert policy.read_text(encoding='utf-8') == 'custom policy'
