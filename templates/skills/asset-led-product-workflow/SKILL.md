# Asset-Led Product Workflow

This pack is the reusable asset-production layer for Synapse UI work. It complements UI Forge, Image Studio, Blender Studio, FirstRun Studio, and the autonomous development loop.

Its job is to make rich product visuals repeatable instead of relying on one-off manual asset creation.

## When to use

Use when a web/app experience needs any non-trivial visual asset system: hero scenes, persona art, category imagery, device mockups, product renders, environmental backgrounds, trust/status graphics, empty states, social/marketing images, or recurring image families.

For a locked screenshot/reference target, read UI Forge's Visual Target Contract first.

## Asset decision ladder

For every material visual slot, classify the requirement before implementation:

1. **Existing project asset** — reuse when it already meets the target.
2. **CSS primitive** — only for genuinely simple geometry, borders, glow, gradients, separators, or tiny iconographic shapes.
3. **Vector asset** — logos, icons, diagrams, controlled line art.
4. **Image Studio** — people, environments, photoreal scenes, detailed 2D illustration, reference-guided transformations.
5. **Blender Studio** — deterministic 3D objects, device/laptop/phone mockups, stylized scene families, reusable camera/lighting setups, perspective-critical objects, transparent rendered assets.
6. **Licensed/imported asset** — when provenance and license are explicit.
7. **Blocked** — when none of the above can honestly meet the target.

A production illustration, photoreal image, 3D render, or device mockup must never be silently replaced by CSS circles/ovals/gradients because a generator is unavailable.

## Required asset manifest

Maintain a project-scoped manifest for meaningful visual work. Each asset entry should include:

- semantic id
- target surface(s)
- asset class
- intended dimensions/aspect ratio
- mobile/desktop crop policy
- producer: existing / CSS / vector / Image Studio / Blender Studio / imported
- source file and rendered/exported file
- provenance/license
- version/hash when available
- alt/decorative policy
- status: planned / blocked / draft / approved / integrated / superseded
- target-reference note
- review evidence

Prefer stable paths such as:
- `assets/generated/...`
- `public/images/generated/...`
- `art/source/...` for editable Blender/image source
- `.synapse/ui-forge/assets/...` for UI Forge staging/provenance

## Production loop

1. Inspect current UI and the locked target/reference.
2. Decompose the screen into asset slots before styling around missing art.
3. Check producer readiness. If Image Studio is unconfigured, determine whether Blender can honestly satisfy that asset. If not, mark it blocked.
4. Generate/build one strong asset per slot before creating many variants.
5. Store source + output + provenance.
6. Integrate the real asset path through UI Forge Asset Slots or the project's asset system.
7. Verify browser decode, dimensions, crop/object-fit, MIME, CSP, caching, responsive composition, and alt policy.
8. Capture desktop and phone evidence with the asset rendered in context.
9. Compare against the visual target; repair the asset or composition rather than adding compensating CSS clutter.
10. Persist the final manifest and supersede rejected variants instead of losing history.

## Device mockups

When a target shows the product inside a phone/laptop/tablet:

- capture the **real running product** at the intended viewport
- create or reuse a device frame with Image Studio/Blender Studio/imported licensed asset
- composite the real screenshot into the screen area
- preserve readable perspective and avoid fake UI screenshots
- keep editable source if perspective/composition may need future revisions
- verify the final mockup at actual landing-page size

A generic rectangle with a border is not equivalent to a premium device mockup when the target visibly depends on hardware presentation.

## Human / character imagery

When a target depends on people or emotional presence:

- prefer Image Studio for rich human scenes/portraits
- use Blender for intentionally stylized/abstract 3D characters or reusable posed scenes
- preserve a character/style bible when the same person appears across multiple assets
- do not imply a generated person is a real person
- do not use crude geometric stand-ins as final production art when facial/body language is central to the experience

## Browser and deployment verification

HTTP 200 is not asset proof.

Verify:
- correct MIME
- decoded dimensions > 0
- CSP compatibility
- cache behavior/versioned URL after replacement
- no broken or duplicated images
- correct crop at target breakpoints
- no important subject clipped by mobile safe area
- rendered glyph/icon correctness
- screenshot evidence at target desktop/mobile sizes

## Completion gate

Do not call the asset system complete when:
- a required manifest entry is blocked/planned/draft
- a target slot is filled by a lower-fidelity class than the Visual Target Contract permits
- a required device mockup uses fake UI instead of a real capture
- an image exists on disk but is not proven in the running product
- provenance or intended use is unknown
- mobile composition is unverified

The asset manifest should make it possible for a future AI to reuse, regenerate, edit, or replace the asset without rediscovering the whole workflow.
