"""Regression tests for authenticated MCP ChatGPT observation behavior."""
import asyncio
from synapse_daemon.chatgpt_mcp_execution import (
    _COMPOSER, _SEND, conversation_url, _response_done, execute_mcp_chat
)

PROJECT_SNAPSHOT = '''### Page
- Page URL: https://chatgpt.com/g/g-p-demo/project
### Snapshot
- textbox "New chat in Synapse2GPT Workers" [active] [ref=e862]:
  - paragraph: New chat in Synapse2GPT Workers
'''
COMPOSER_SNAPSHOT = '''### Page
- Page URL: https://chatgpt.com/g/g-p-demo/project
### Snapshot
- textbox "New chat in Synapse2GPT Workers" [ref=e862]:
  - paragraph: bounded task
- button "Send" [ref=e908]
'''
COMPLETED = '''### Page
- Page URL: https://chatgpt.com/g/g-p-demo/c/1234-abcd
### Snapshot
- status: Response complete
- button "Copy" [ref=e101]
'''

def test_actual_project_composer_snapshot_parses():
    assert _COMPOSER.search(PROJECT_SNAPSHOT).group(1) == "e862"
    assert _SEND.search(COMPOSER_SNAPSHOT).group(1) == "e908"

def test_conversation_url_requires_page_url_and_not_sidebar_link():
    sidebar = "### Page\n- Page URL: https://chatgpt.com/g/g-p-demo/project\n### Snapshot\n- link: https://chatgpt.com/c/old"
    assert conversation_url(sidebar) == ""
    assert conversation_url(COMPLETED) == "https://chatgpt.com/g/g-p-demo/c/1234-abcd"
    assert _response_done(COMPLETED)

def test_recovery_does_not_resend():
    calls = []
    class Tab:
        async def call(self, name, args):
            calls.append(name)
            assert name == "browser_snapshot"
            return COMPLETED
        async def close(self):
            calls.append("close")
    class Browser:
        async def new_tab(self, worker_id, url):
            assert url == "https://chatgpt.com/g/g-p-demo/c/1234-abcd"
            return Tab()
    result = asyncio.run(execute_mcp_chat(
        Browser(), "worker", "NOT TO SEND", "https://chatgpt.com/g/g-p-demo/c/1234-abcd",
        timeout=20, observe_only=True
    ))
    assert result["ok"] and result["sent"] is False
    assert calls == ["browser_snapshot", "browser_snapshot", "browser_snapshot", "close"]
