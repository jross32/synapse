# ADR-0021: AI Bundles as Marketplace-Installable Intelligence Packs

- **Status:** accepted
- **Date:** 2026-06-27
- **Deciders:** Justin Ross, Codex
- **Related contracts:** #1, #2, #8, #9, #11, #26

## Context

AI Factory and the advanced case engine gave Synapse a strong substrate for
structured AI work, but the reusable intelligence still needed a user-facing
distribution shape. Roles, personalities, quick actions, recipe add-ons, and
case-oriented workflow guidance should be installable the same way tools are,
because the primary operator is often another AI using Synapse, not only a
human browsing cards manually.

At the same time, these packs need stronger lifecycle tracking than loose JSON
files:

- installs must be attributable and removable
- bundle-owned assets must not be confused with user-authored assets
- quick actions installed by a bundle must show up automatically in Sessions
- the installer should be able to pre-select a known-good AI bundle set on day 1

## Decision

Synapse gains a first-class **AI Bundle** model.

An AI bundle is a Marketplace-installable pack that can contain:

- role templates
- personalities
- quick-action templates
- AI Factory recipes
- AI Factory sources
- metadata about overlap, efficiency, and intended case modes

The daemon becomes the source of truth for installs:

- `ai_bundle_installs` stores installed manifests
- `ai_bundle_assets` stores concrete owned assets for deterministic uninstall
- bundle install/uninstall routes live at `/api/v1/ai-bundles`
- installed bundle quick actions load from the daemon data directory and merge
  into the normal quick-action catalog
- profile catalog state tracks bundle installs the same way it tracks tool installs

The Marketplace and AI Factory both surface bundle state directly, and the
Windows installer can preselect bundles by writing a bootstrap file that the
Electron shell consumes on first launch.

## Consequences

### Positive

- Synapse now has an AI-native distribution layer, not only a human tool shelf.
- Reusable intelligence can be installed, compared, and removed cleanly.
- The app can ship opinionated AI starter packs from **The WhatIf Company**
  without hardcoding those roles or quick actions into the renderer.
- The installer path becomes a practical onboarding surface for AI-focused packs.

### Negative / trade-offs

- Bundle ownership bookkeeping adds one more catalog domain to maintain.
- Uninstall logic has to respect shared ownership carefully to avoid removing
  assets another bundle still depends on.
- The first iteration ships curated bundled samples; author-upload/publish flows
  still need a deeper follow-up.

### Follow-ups

- Add author/upload/download flows for user-created bundles.
- Promote scraper/browser evidence into bundle authoring and harvesting lanes.
- Expand installer bundle selection beyond a bootstrap file into a richer setup UX.
