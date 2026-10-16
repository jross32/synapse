import asyncio
from unittest.mock import Mock

from synapse_daemon.device_presence import DevicePresenceLoop


def test_device_presence_publishes_when_signed_in():
    profile = Mock()
    profile._state_row.return_value = {"user_id": "account"}
    loop = DevicePresenceLoop(profile)
    loop._publish()
    profile.ensure_current_host.assert_called_once()
    profile._sync_to_remote.assert_called_once_with(best_effort=True)


def test_device_presence_does_not_publish_signed_out():
    profile = Mock()
    profile._state_row.return_value = {"user_id": None}
    loop = DevicePresenceLoop(profile)
    loop._publish()
    profile._sync_to_remote.assert_not_called()


def test_device_presence_lifecycle():
    async def exercise():
        profile = Mock()
        profile._state_row.return_value = {"user_id": "account"}
        loop = DevicePresenceLoop(profile, interval_seconds=0.01)
        await loop.start()
        await asyncio.sleep(0.05)
        await loop.stop()
        assert profile._sync_to_remote.call_count >= 2
    asyncio.run(exercise())
