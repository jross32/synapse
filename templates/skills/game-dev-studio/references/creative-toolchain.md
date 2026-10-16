# Game Dev Studio creative toolchain (discovery phase)

This is an extension of the existing Game Dev Studio pack, **not** another execution framework. The registry at `references/creative-tool-registry.json` lists candidate tools by capability. The inventory helper is safe and read-only:

```powershell
python templates/skills/game-dev-studio/scripts/creative_tool_registry.py
python -m unittest discover -s templates/skills/game-dev-studio/tests -v
```

## Workflow routing

- **2D engines:** Godot, GameMaker, Defold, Construct 3, Unity.
- **3D engines:** Unity, Unreal, Godot, Roblox Studio, Open 3D Engine.
- **3D art and animation:** Blender (existing first-class pack), Blockbench, Maya, Houdini.
- **2D sprites, graphics and textures:** Aseprite, Krita, GIMP, Inkscape, Photoshop.
- **Audio and interactive music:** Audacity, REAPER, FMOD Studio, Wwise.
- **Maps and level authoring:** Tiled, LDtk, engine-native editors, Blender/Houdini.

For a new game, inspect the engine and installed assets first; select only tools that fit the game and platform. An executable on PATH is **not** proof of a valid licensed installation, automated integration, successful export, or runtime support. GUI-only / commercial products require their own supported adapter and user authorization. Never install paid software or accept terms automatically.

## Required pipeline contracts for future adapters

1. Detect app/version, compatibility, license and local paths without modifying the machine.
2. Declare supported inputs, outputs, automation mode (CLI/editor/API/manual), and interop formats (PNG, SVG, WAV, GLB, FBX as applicable).
3. Generate or edit original/user-authorized assets; preserve native editable sources.
4. Import through verified engine-native paths and capture errors and output hashes.
5. Track usage rights, source, attribution, modifications, export settings, and asset destination using the existing provenance system.
6. Test with engine-specific import/build/playtest evidence and screenshots. Never mark a registry entry as an implemented adapter before real proof.
7. Reuse Synapse AI workers, checkpoint/approval gates, and existing game-dev-events.jsonl. Do not spawn duplicate schedulers.

**Next implementation gates:** real adapter smoke tests for Godot, Blender->engine asset handoff, Krita/Aseprite sprite import, Tiled/LDtk level import, and Audacity/REAPER audio import; then extend to proprietary applications when installed and authorized.
