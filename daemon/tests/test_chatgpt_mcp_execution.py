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


# Captured from the registered authenticated Playwright MCP browser on 2026-10-16.
# Real snapshots are YAML fenced and use an unqualified Stop button while streaming.
AUTHENTICATED_MCP_SNAPSHOT = """### Open tabs
- 0: [ChatGPT - Synapse2GPT Workers](https://chatgpt.com/g/g-p-demo/project)
- 1: (current) [Authenticated MCP Parser Fix](https://chatgpt.com/g/g-p-demo/c/6ad23884-0e98-83e9-8fa3-cf92bd6431db)
### Page
- Page URL: https://chatgpt.com/g/g-p-demo/c/6ad23884-0e98-83e9-8fa3-cf92bd6431db
- Page Title: Authenticated MCP Parser Fix
### Snapshot
```yaml
- generic [ref=e1]:
  - main [ref=e1080]:
    - region "Conversation" [ref=e1113]:
      - heading "You said:" [level=4] [ref=e1126]
      - button "Copy message" [ref=e1140] [cursor=pointer]
      - heading "Latest response" [level=4] [ref=e1160]
      - textbox "Ask ChatGPT" [active] [ref=e1193]:
      - button "Stop" [ref=e1221] [cursor=pointer]
```
"""

def test_real_authenticated_mcp_snapshot_does_not_confirm_streaming_reply():
    assert conversation_url(AUTHENTICATED_MCP_SNAPSHOT).endswith(
        "/c/6ad23884-0e98-83e9-8fa3-cf92bd6431db"
    )
    assert _COMPOSER.search(AUTHENTICATED_MCP_SNAPSHOT).group(1) == "e1193"
    assert not _response_done(AUTHENTICATED_MCP_SNAPSHOT)
    # A misleading completion marker or user-message Copy control must not
    # override the real browser's active Stop button.
    assert not _response_done(
        AUTHENTICATED_MCP_SNAPSHOT.replace(
            'heading "Latest response"', 'status: Response complete\n      - button "Copy" [ref=e1150]\n      - heading "Latest response"'
        )
    )


def test_real_mcp_completed_reply_without_synthetic_status():
    finished = AUTHENTICATED_MCP_SNAPSHOT.replace(
        '      - button "Stop" [ref=e1221] [cursor=pointer]\n',
        '      - button "Copy message" [ref=e1221] [cursor=pointer]\n',
    )
    assert _response_done(finished)
    assert not _response_done(AUTHENTICATED_MCP_SNAPSHOT)

def test_user_copy_message_alone_never_confirms_reply():
    user_only = '''### Page\n- Page URL: https://chatgpt.com/c/123\n### Snapshot\n- heading \"You said:\"\n- button \"Copy message\" [ref=e12]\n'''
    assert not _response_done(user_only)
