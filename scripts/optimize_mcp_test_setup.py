"""Apply a guarded optimization to MCP connector test database setup."""
from pathlib import Path
p=Path("daemon/tests/test_mcp_connector.py")
s=p.read_text(encoding="utf-8")
anchor="from pathlib import Path\n"
assert s.count(anchor)==1
s=s.replace(anchor,anchor+"import shutil\nimport tempfile\n\n_MIGRATED_DB_TEMPLATE = None\n",1)
old='''    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
'''
new='''    global _MIGRATED_DB_TEMPLATE
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
assert s.count(old)==1
p.write_text(s.replace(old,new,1),encoding="utf-8")
print("OPTIMIZED")
