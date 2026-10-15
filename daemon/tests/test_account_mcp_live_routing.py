from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from synapse_accounts.relay import choose_device

class Session:
    def __init__(self, selected=None, devices=()):
        self.selected=selected
        self.devices=list(devices)
    def scalar(self, stmt): return self.selected
    def scalars(self, stmt): return iter(self.devices)

def device(id, seconds_ago, revoked=None):
    return SimpleNamespace(device_id=id, last_seen_at=datetime.now(UTC)-timedelta(seconds=seconds_ago), revoked_at=revoked)

def test_selected_device_stays_default_when_fresh():
    a=device('laptop', 10)
    with patch('synapse_accounts.relay._hosts',return_value={'laptop','desktop'}):
        assert choose_device(Session(a,[a,device('desktop',1)]),'account','laptop')=='laptop'

def test_offline_selected_falls_back_to_online_machine():
    stale=device('laptop', 500)
    online=device('desktop',4)
    with patch('synapse_accounts.relay._hosts',return_value={'laptop','desktop'}):
        assert choose_device(Session(stale,[stale,online]),'account','laptop')=='desktop'

def test_no_live_device_fails_instead_of_queueing_to_offline_machine():
    with patch('synapse_accounts.relay._hosts',return_value={'laptop'}):
        with pytest.raises(HTTPException) as err:
            choose_device(Session(device('laptop',500),[device('laptop',500)]),'account','laptop')
    assert err.value.status_code==503
