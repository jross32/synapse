from pathlib import Path
import pytest
from synapse_daemon.mesh_transfer import preview_project_copy,copy_project

def test_preview_and_atomic_copy(tmp_path:Path):
    source=tmp_path/"source"
    source.mkdir()
    (source/"src").mkdir()
    (source/"src"/"app.py").write_text("print(1)")
    (source/"node_modules").mkdir()
    (source/"node_modules"/"large.dat").write_bytes(b"x"*500)
    preview=preview_project_copy(source)
    assert preview["files"]==1
    result=copy_project(source,tmp_path/"destination",tmp_path)
    assert result["verified"] and result["files"]==1
    assert (tmp_path/"destination"/"src"/"app.py").read_text()=="print(1)"
    assert not (tmp_path/"destination"/"node_modules").exists()
    with pytest.raises(FileExistsError):
        copy_project(source,tmp_path/"destination",tmp_path)

def test_refuses_parent_escape(tmp_path:Path):
    source=tmp_path/"source"
    source.mkdir()
    (source/"a.txt").write_text("ok")
    with pytest.raises(ValueError):
        copy_project(source,tmp_path.parent/"outside",tmp_path)
    assert not (tmp_path.parent/"outside").exists()

def test_refuses_links(tmp_path:Path):
    source=tmp_path/"source"
    source.mkdir()
    (source/"real").write_text("ok")
    try:
        (source/"link").symlink_to(source/"real")
    except (OSError,NotImplementedError):
        pytest.skip("Host cannot create symlink")
    with pytest.raises(ValueError):
        preview_project_copy(source)
