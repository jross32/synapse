"""Regression: default Visual QA is discoverable to all Synapse-connected AI UI workflows."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "templates" / "skills"
ACTIONS = ROOT / "templates" / "quick-actions"

def test_visual_qa_default_skill_and_completion_contract():
    from synapse_daemon import skill_packs
    from synapse_daemon.quick_actions import load_templates
    source = json.loads((SKILLS / "browser-ui-audit" / "manifest.json").read_text(encoding="utf-8"))
    assert source["implicit_invocation"] is True
    assert source["entrypoint"] == "SKILL.md"
    installed = skill_packs.get_installed(ROOT / "data", "browser-ui-audit")
    assert installed.manifest.version == source["version"]
    assert installed.manifest.implicit_invocation is True
    instructions = skill_packs.read_instructions(ROOT / "data", "browser-ui-audit")["instructions_md"]
    assert "visual-qa.mjs" in instructions
    assert "authenticated" in instructions.lower()
    assert "timeout" in instructions.lower()
    contract = skill_packs.read_instructions(ROOT / "data", "completion-contract")
    assert contract["skill"]["manifest"]["implicit_invocation"] is True
    assert "browser-ui-audit" in contract["instructions_md"]
    assert "visual-qa.mjs" in contract["instructions_md"]
    assert (ROOT / "scripts" / "visual-qa.mjs").exists()
    action = next((a for a in load_templates() if a.id == "visual-qa"), None)
    assert action is not None
    assert "browser-ui-audit" in action.prompt

if __name__ == "__main__":
    test_visual_qa_default_skill_and_completion_contract()
    print("VISUAL QA DEFAULT PASS: installed implicit skills, completion contract, runner, action")
