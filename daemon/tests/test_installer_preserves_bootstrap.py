"""NSIS reinstallation must not clobber existing Synapse bootstrap choices."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "installer" / "installer.nsh"


def _macro() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    return source.split("!macro customInstall", 1)[1].split("!macroend", 1)[0]


def test_bootstrap_bundles_only_created_if_missing():
    text = _macro()
    guard = 'IfFileExists "$APPDATA\\Synapse\\bootstrap-ai-bundles.json" preserve_existing_bundles'
    write = 'FileOpen $0 "$APPDATA\\Synapse\\bootstrap-ai-bundles.json" w'
    assert guard in text
    assert text.index(guard) < text.index(write) < text.index("preserve_existing_bundles:")


def test_optional_tools_only_created_if_missing():
    text = _macro()
    guard = 'IfFileExists "$APPDATA\\Synapse\\bootstrap-optional-tools.json" preserve_existing_optional_tools'
    write = 'FileOpen $1 "$APPDATA\\Synapse\\bootstrap-optional-tools.json" w'
    assert guard in text
    assert text.index(guard) < text.index(write) < text.index("preserve_existing_optional_tools:")


def test_no_other_overwriting_fileopens():
    text = _macro()
    assert text.count("FileOpen") == 2
    assert text.count("IfFileExists") == 2
