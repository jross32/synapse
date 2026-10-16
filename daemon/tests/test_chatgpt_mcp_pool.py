import asyncio
from synapse_daemon.chatgpt_child_agents import ChatGPTBrowserPool

def test_mcp_pool_does_not_launch_separate_profile(tmp_path, monkeypatch):
    from synapse_daemon import chatgpt_mcp_execution
    seen = {}
    async def fake_execute(browser, worker_id, prompt, start_url, timeout):
        seen.update(worker=worker_id, url=start_url, prompt=prompt)
        return {"ok": True, "reply": "Response complete", "conversation_url": "https://chatgpt.com/c/abc"}
    monkeypatch.setattr(chatgpt_mcp_execution, "execute_mcp_chat", fake_execute)
    (tmp_path / "chatgpt-worker-project-url.txt").write_text("https://chatgpt.com/g/g-p-example/project")
    async def fake_tool(name, arguments):
        raise AssertionError("unexpected live browser tool")
    pool = ChatGPTBrowserPool(tmp_path, mcp_call_tool=fake_tool)
    result = asyncio.run(pool.run_child("worker1", "Do bounded coding task"))
    assert result.ok
    assert result.conversation_url == "https://chatgpt.com/c/abc"
    assert seen["worker"] == "worker1"
    assert "Do bounded coding task" in seen["prompt"]
    assert pool._context is None
    assert pool._playwright is None

def test_mcp_pool_refuses_unconfigured_project(tmp_path):
    async def fake_tool(name, arguments):
        raise AssertionError("no tool should be called")
    pool = ChatGPTBrowserPool(tmp_path, mcp_call_tool=fake_tool)
    result = asyncio.run(pool.run_child("worker2", "task"))
    assert not result.ok
    assert "project URL" in result.error
    assert pool._context is None
