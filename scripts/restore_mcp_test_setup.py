from pathlib import Path
p = Path("daemon/tests/test_mcp_connector.py")
s = p.read_text(encoding="utf-8")
old_import = "from pathlib import Path\nimport shutil\nimport tempfile\n\n_MIGRATED_DB_TEMPLATE = None\n"
old_start = '''    global _MIGRATED_DB_TEMPLATE
    if _MIGRATED_DB_TEMPLATE is None:
        template_dir = Path(tempfile.mkdtemp(prefix="synapse-mcp-test-schema-"))
        template = Storage(template_dir)
        template.open()
        template.migrate()
        template.close()
        _MIGRATED_DB_TEMPLATE = template_dir / "synapse.sqlite"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_MIGRATED_DB_TEMPLATE, data_dir / "synapse.sqlite")
    storage = Storage(data_dir)
    storage.open()
    storage.migrate()
'''
assert s.count(old_import) == 1 and s.count(old_start) == 1, "File changed, no modification"
s = s.replace(old_import, "from pathlib import Path\n", 1)
s = s.replace(old_start, '''    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
''', 1)
p.write_text(s, encoding="utf-8")
print("RESTORED")
