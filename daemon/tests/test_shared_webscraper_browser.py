import asyncio
import pytest

from synapse_daemon.shared_webscraper_browser import SharedWebscraperBrowser, SharedBrowserError


class FakeMCP:
    def __init__(self):
        self.tabs = {0: "operator"}
        self.current = 0
        self.calls = []

    async def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "browser_tabs":
            action = args["action"]
            if action == "list":
                return "\n".join(f"- {i}: [{url}]" for i, url in self.tabs.items())
            if action == "new":
                index = max(self.tabs) + 1
                self.tabs[index] = args["url"]
                self.current = index
                return "created"
            if action == "select":
                assert args["index"] in self.tabs
                self.current = args["index"]
                return "selected"
            if action == "close":
                del self.tabs[args["index"]]
                return "closed"
        return "ok"


def test_tab_ownership_and_operator_preservation():
    async def run():
        fake = FakeMCP()
        browser = SharedWebscraperBrowser(fake)
        a = await browser.new_tab("worker-a", "https://chatgpt.com/")
        b = await browser.new_tab("worker-b", "https://chatgpt.com/")
        await a.call("browser_snapshot", {})
        assert fake.current == a.index
        with pytest.raises(SharedBrowserError):
            await a.call("browser_close", {})
        await a.close()
        assert fake.tabs == {0: "operator", b.index: "https://chatgpt.com/"}
        await b.close()
        assert fake.tabs == {0: "operator"}
    asyncio.run(run())


def test_refuse_unsafe_urls_and_lost_ownership():
    async def run():
        fake = FakeMCP()
        browser = SharedWebscraperBrowser(fake)
        with pytest.raises(SharedBrowserError):
            await browser.new_tab("w", "https://evil.example/")
        tab = await browser.new_tab("w", "https://chatgpt.com/")
        browser._owned[tab.index] = "other"
        with pytest.raises(SharedBrowserError):
            await tab.close()
        assert tab.index in fake.tabs
    asyncio.run(run())
