from synapse_daemon.mobile_lab import device_plan, system_capabilities


def test_capabilities_are_safe_and_install_free():
    result = system_capabilities()
    assert result["os"]
    assert result["home_disk_free_bytes"] >= 0
    assert result["policy"]["install_performed"] is False
    assert result["policy"]["automatic_downloads"] is False
    assert result["policy"]["secrets_and_device_identifiers_excluded"] is True


def test_windows_never_claims_native_iphone_simulator():
    result = system_capabilities()
    if result["os"] == "Windows":
        assert result["ios"]["native_simulator_supported"] is False
        assert device_plan(result)["selected_provider"] == "unavailable"


def test_remote_mac_provider():
    result = system_capabilities()
    result["ios"].update(native_simulator_ready=False, remote_mac_bridge="configured")
    assert device_plan(result)["selected_provider"] == "remote-macos-xcode"


def test_browser_fallback_is_not_ios():
    result = system_capabilities()
    result["ios"].update(native_simulator_ready=False, remote_mac_bridge="not_configured",
                         physical_iphone_bridge="not_configured")
    plan = device_plan(result)
    assert plan["fallback_is_native_ios"] is False
    assert plan["installation_required_now"] is False
