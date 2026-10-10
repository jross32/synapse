# Synapse Distribution & Fleet Vision

## Product promise
Install Synapse on any supported computer, sign into one Synapse account, name the machine, and immediately recover the user's shared Synapse world: projects, AI context, preferences, connector catalog, machine inventory, and permitted account integrations. Machine-local capabilities remain discoverable and targetable.

## Machine model
A Synapse **machine** is an installed host (Windows/macOS/Linux), not a paired browser. Each install owns a stable random machine ID and advertises OS, architecture, Synapse version, last-seen heartbeat, and capabilities. Browsers/phones remain paired clients of a machine.

## Sync boundaries
Cloud/account sync: project metadata, AI context, preferences, machine registry, connector definitions, grants, collaboration/friends metadata, release/update settings.
Machine-local by default: raw filesystem paths, OS keychain entries, local browser sessions, private SSH keys, local model weights.
Portable secrets: only through an encrypted account vault with per-connector opt-in and revocation. Never copy plaintext tokens between machines.

## Distribution
- Windows: signed NSIS .exe first.
- macOS: signed/notarized universal DMG/PKG target.
- Linux: AppImage first, then deb/rpm if demand warrants.
- Download page: latest stable, platform detection, file size, checksum/signature, release date, release notes, previous versions, installation guides.
- Updates page in app and web: current version, channel (Stable/Beta), automatic updates, release history, download/restart progress, rollback metadata.

## Installer experience
A calm Synapse-brain visualization maps real stages to neural activity:
1. Preparing system — sparse orbiting signal particles.
2. Installing core — central brain nodes wake and connect.
3. AI + MCP tools — signals travel to additional lobes/nodes.
4. Machine identity — a distinct machine node joins the network.
5. Account connection — shared account halo/network appears.
6. Health check — completed paths glow; success pulse resolves into Launch Synapse.

Animation is progress-driven, not fake time. Always pair visuals with exact stage text, percent/indeterminate state, current action, and useful failure/retry detail. Respect prefers-reduced-motion and keep a static accessible fallback.

## Visual language
Near-black/navy foundation, luminous electric blue/violet as primary energy, occasional magenta/red accents only for meaningful transitions or alerts. Soft volumetric glows, thin neural paths, restrained glass surfaces, fast smooth transitions. Avoid noisy gamer aesthetics and excessive bloom.

## Navigation
Website: Product · Download · Features · Integrations · Pricing · Support · Sign in.
App: Home · AI · Accounts/Integrations · MCP · My machines · Updates · Settings.
Mobile: Home · Ask · Tools · Machines · Account; optimize for monitoring, approvals, quick actions, and remote control rather than cloning the desktop layout.

## Acceptance criteria for multi-machine v1
- Install on a second Windows PC from a public/private download page.
- Sign into the same Synapse account.
- Give machine a friendly name.
- Both machines appear under My machines with online/offline state and capabilities.
- Shared project/AI context is visible on both.
- An AI can target an eligible machine explicitly and never silently run on the wrong host.
- Revoking a machine invalidates its account session.
- Connector grants state whether they are account-portable or machine-local.
- Updates can be downloaded, verified, installed, and rolled back safely.
