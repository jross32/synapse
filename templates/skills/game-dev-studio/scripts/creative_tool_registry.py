"""Read-only creative tool discovery for Synapse Game Dev Studio."""
import argparse
import json
import shutil
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "references" / "creative-tool-registry.json"

def inventory(registry_path=REGISTRY, resolver=shutil.which):
    catalog = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("unsupported registry schema")
    ids = [tool["id"] for tool in catalog["tools"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate tool id")
    output = []
    for tool in catalog["tools"]:
        commands = tool.get("commands", [])
        found = next(((cmd, resolver(cmd)) for cmd in commands if resolver(cmd)), None)
        output.append({
            "id": tool["id"], "category": tool["category"],
            "domains": tool["domains"], "detected_on_path": bool(found),
            "command": found[0] if found else None,
            "path": found[1] if found else None,
            "integration": tool["integration"],
            "usable": False,
            "note": "PATH discovery only; launch, licensing and engine-specific verification required",
        })
    return {"schema_version": 1, "tools": output}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args()
    print(json.dumps(inventory(args.registry), indent=2))

if __name__ == "__main__":
    main()
