"""Regression coverage for the Reflex MCP process-local control lease."""
from __future__ import annotations
import json
import queue
from types import SimpleNamespace
from synapse_daemon import mcp_connector

class _FakeStdin:
    def __init__(self, process): self.process=process
    def write(self, data):
        msg=json.loads(data)
        if msg['method']=='initialize': result={'protocolVersion':'2024-11-05'}
        elif msg['method']=='notifications/initialized': return len(data)
        elif msg['method']=='tools/call':
            tool=msg['params']['name']
            if tool=='request_control': self.process.granted=True
            elif tool=='release_control': self.process.granted=False
            result={'granted':self.process.granted}
        else: raise AssertionError(msg)
        self.process.lines.put(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result})+'\n')
        return len(data)
    def flush(self): pass

class _FakeProcess:
    def __init__(self):
        self.granted=False
        self.lines=queue.Queue()
        self.stdin=_FakeStdin(self)
        self.stdout=self
        self.dead=False
    def __iter__(self):
        while True:
            item=self.lines.get(timeout=2)
            if item is None: return
            yield item
    def poll(self): return -9 if self.dead else None
    def kill(self):
        self.dead=True
        self.lines.put(None)

def test_reflex_lease_survives_separate_calls(monkeypatch):
    import subprocess
    created=[]
    def spawn(*args,**kwargs):
        p=_FakeProcess();created.append(p);return p
    monkeypatch.setattr(subprocess,'Popen',spawn)
    monkeypatch.setattr(mcp_connector,'resolve_command',lambda x:x)
    server=SimpleNamespace(id='reflex-test',command='fake',args=[],env={})
    def call(name):
        return mcp_connector._persistent_stdio_mcp(server,'tools/call',{'name':name,'arguments':{}},5)
    try:
        assert call('request_control')['granted'] is True
        assert call('get_control_state')['granted'] is True
        assert len(created)==1
        assert call('release_control')['granted'] is False
    finally:
        session=mcp_connector._persistent_stdio_sessions.pop(server.id,None)
        if session: session[0].kill()
