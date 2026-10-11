from synapse_daemon.mesh_inventory import development_tools, disk_inventory, hardware_inventory

def test_inventory_has_bounded_structured_fields():
    info=hardware_inventory()
    assert info["hostname"] and info["platform"]
    assert isinstance(info["cpu_logical"], int)
    assert isinstance(info["tools"], list)
    assert {x["name"] for x in info["tools"]} >= {"git", "node", "python"}
    for tool in info["tools"]:
        assert isinstance(tool["available"], bool)
        assert tool["version"] is None or len(tool["version"]) <= 160
    for disk in info["disks"]:
        assert disk["free_bytes"] <= disk["total_bytes"]

def test_disk_usage_positive():
    disks=disk_inventory()
    assert disks and all(d["total_bytes"] > 0 for d in disks)

def test_tools_do_not_depend_on_git_installed():
    names={x["name"] for x in development_tools()}
    assert "git" in names
