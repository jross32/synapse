# Synapse — Connected Brain design and release acceptance

Status: **implementation in progress**, not a production release certificate.  
Approved source: the owner's multi-surface “Your Connected Brain” concept collage (October 2026). The original chat attachment is **not yet present in the Synapse project file store**. This document preserves the visual requirements without pretending the attachment was registered.

## Design target

- Deep navy, blue, and violet canvas; fine luminous neural lines; blue/cyan and violet/pink node highlights; quiet glassy borders.
- Clear information hierarchy. Dashboard is operational software, **not** a screenshot of the marketing collage.
- Hero reads “Your Connected Brain”, real project counts, links to existing projects, tools, AI sessions, machines, and Updates.
- Visual assets remain original and local to the repository. The dashboard's neural illustration is an SVG/CSS component: `renderer/components/ConnectedBrainHero.tsx`.
- Screen reader: the diagram is decorative, linked areas are native buttons, meaningful status remains text.
- Mobile: hero reflows to one column and remains usable at 375px; tablet and desktop are responsive. Respect reduced-motion preferences.
- Dark and light: use the theme token contract from `renderer/lib/theme-tokens.css`. Do not hardcode foreground/background states into application controls.

## Implementation map

| Surface | Source | Required functional proof |
|---|---|---|
| Desktop homepage | `renderer/pages/Home.tsx`, `renderer/components/ConnectedBrainHero.tsx` | Live counts, buttons navigate to intended sections, projects continue loading/launching |
| Download and Updates | `renderer/pages/Updates.tsx`, `renderer/lib/releases-client.ts` | All OS cards, only published artifacts enabled, visible download errors |
| Release service | `daemon/synapse_daemon/release_manifest.py`, `routes_about.py` | Auth required, allowlisted exact filenames, SHA-256 matches bytes, no arbitrary file access |
| Installer | `installer/installer.nsh`, `package.json` electron-builder settings | NSIS output generated, exact SHA-256 recorded, fresh Windows install/start/quit/uninstall pass |
| Devices and account | `renderer/components/MyMachinesPanel.tsx`, `daemon/synapse_daemon/machine_fleet.py` | Sign in on independent second machine and prove shared account/project state, correct machine online/offline and name persistence |
| Global reference system | `daemon/synapse_daemon/routes_design_references.py`, `renderer/components/ProjectDesignReferences.tsx` | Upload reference bytes, register `proposed_ui`, AI-visible MCP read from another agent, no cross-project leakage |
| Mobile | Existing mobile shell and app routes | 375px screenshots, keyboard/touch, no clipped CTA or unexpected sideways scrolling |
| Installer visuals | NSIS custom pages and Electron first-run | Progress comes from actual installation phases, not a timed fake percentage |

## Release invariants

1. A button must never advertise an unbuilt artifact. A planned macOS/Linux entry remains disabled until the corresponding package exists.
2. Release downloads use the same authenticated daemon origin and local token, and the backend serves only allowlisted files.
3. A checksum is derived from actual file bytes, not copied from documentation.
4. The Windows unsigned diagnostic build is not a signed production release. Code signing, notarization (macOS), update feed security, and rollback require separate evidence.
5. No live account sync, Gmail integration, automatic updating, or two-machine behavior may be shown as verified without real testing.

## Suggested test sequence

1. Run `git diff --check`, frontend TypeScript check, Vite production build, and Python compilation.
2. Run `daemon/tests/test_release_manifest.py` and `daemon/tests/test_machine_routes.py`.
3. Launch local daemon and renderer. In Chromium/Electron capture desktop and mobile visual references and assert dashboard navigation plus Updates states. Compare against approved collage.
4. Build Windows NSIS into a **fresh isolated output directory** with no other concurrent electron-builder jobs. Record logs, process exit code, artifact path, size, and SHA-256.
5. Install the built package into a clean Windows profile or VM. Launch, sign in, restart, sign out, and uninstall. Inspect Windows event log for startup faults.
6. Test sign-in and sync from a second machine with different machine ID and online/offline transitions. Check data isolation and error recovery.
7. Record real screenshots and close relevant Quality OS gates only when linked passing proof exists. Keep unresolved gates open.

## Reusable production workflow

**Concept → Visual tokens → Real components → Functional tests → Browser screenshots → Repair → Release proof → Durable handoff.**

After each cycle, reuse the design rules across projects by storing a project-scoped, AI-visible design reference in Synapse and ensuring agents read it before UI changes.

## Current blockers to certify 100%

- Installer packaging failures previously included locked output, missing app.asar, Windows symlink privilege failure, and low disk space. Each new attempt needs a clean, logged build and smoke test.
- Approved collage image bytes still need binary transfer to Synapse's project file store.
- Account-to-machine cloud synchronization and Mac/Linux installation have not been verified.
- The platform-wide Quality OS reports unresolved gates, which must not be silently waived.
