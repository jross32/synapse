# UI Forge Theme Capsules

Theme Capsules are machine-readable, provenance-backed design-token contracts for reusing a product's semantic CSS theme without blind color replacement.

## Extract

Use:

`node scripts/theme_capsule.mjs extract <project-root> <output.json> --name <name>`

Extraction reads only root-level CSS custom properties declared under `:root` or `html`, records their stylesheet/selector/line provenance, and groups tokens heuristically into color, typography, spacing, radius, shadow, motion, and other categories.

Extraction fails closed when the same root token has conflicting values in multiple locations. Resolve the design-system ambiguity first rather than choosing a value arbitrarily.

## Validate

Use:

`node scripts/theme_capsule.mjs validate <theme.json>`

A valid capsule uses schema `ui-forge-theme-capsule-v1` and contains non-empty CSS custom-property names/values without structural CSS syntax.

## Apply

Use a dry run first:

`node scripts/theme_capsule.mjs apply <target-project> <theme.json> --dry-run`

Then apply:

`node scripts/theme_capsule.mjs apply <target-project> <theme.json>`

The apply path updates only custom properties that already exist in the target project. It does not perform raw hex replacement and does not rewrite component rules. Each target token must have one unambiguous root owner. Missing or ambiguous tokens block application by default.

`--allow-partial` permits an intentional subset only when the caller has reviewed the reported missing tokens. Do not use it merely to force a theme onto an incompatible project.

Writes across multiple stylesheets are atomic: if a write fails, every touched stylesheet is restored.

## AI workflow

Use Theme Capsules when:
- a user wants consistent branding across multiple apps;
- a project already has semantic CSS variables worth preserving;
- a draft needs to explore a known brand/theme safely;
- repeated raw values should be migrated toward a reusable token system.

Do not use Theme Capsules when:
- the source project lacks semantic tokens;
- the target has a fundamentally different token vocabulary and needs a design-system mapping first;
- token names are overloaded or duplicated across runtime/media contexts;
- applying the source theme would erase purposeful product-specific semantics.

After application, run the app and perform desktop/mobile browser proof, contrast/accessibility review, and `design_audit.py`. Token equality is not visual correctness by itself.
