from synapse_daemon.coder_runtimes import select_worker_runtime


def test_codex_is_default_first_choice():
    available = dict.fromkeys(['codex','claude','copilot','gemini','local'], True)
    assert select_worker_runtime([], available, available) == 'codex'


def test_local_only_after_all_remote_unavailable():
    capacity = dict.fromkeys(['codex','claude','copilot','gemini','local'], False)
    capacity['local'] = True
    installed = dict.fromkeys(capacity, True)
    assert select_worker_runtime(['local','claude'], capacity, installed) == 'local'
    capacity['gemini'] = True
    assert select_worker_runtime(['local','claude'], capacity, installed) == 'gemini'


def test_respects_remote_role_preference_and_installed_state():
    capacity = dict.fromkeys(['codex','claude','copilot','gemini','local'], True)
    installed = dict(capacity)
    assert select_worker_runtime(['gemini','codex'], capacity, installed) == 'gemini'
    installed['gemini'] = False
    assert select_worker_runtime(['gemini','codex'], capacity, installed) == 'codex'
    assert select_worker_runtime([], {}, {}) is None

def test_chatgpt_ui_first_when_ready():
    available = dict.fromkeys(["codex", "claude", "copilot", "gemini", "local"], True)
    assert select_worker_runtime(["codex"], available, available, chatgpt_ui_ready=True) == "chatgpt_web"
    available["chatgpt_web"] = False
    assert select_worker_runtime([], available, available, chatgpt_ui_ready=True) == "codex"
