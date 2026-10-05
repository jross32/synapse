# UI Forge source tagging for React + Vite

UI Forge can operate without source tagging by matching rendered DOM fingerprints back to source heuristically. For precise visual-edit workflows, React/Vite projects can opt into **development-only source tags**.

The bundled Babel plugin is:

`scripts/babel_source_tags.mjs`

It adds two attributes to intrinsic JSX elements during development transforms:

- `data-ui-forge-id` — deterministic element identity based on relative file, owner component, intrinsic tag, and ordinal.
- `data-ui-forge-source` — direct `relative/file.tsx:line:column` pointer.

These attributes are for local development/preview only. Do not ship them in production builds unless the project explicitly wants that metadata exposed.

## Vite React integration

Copy or reference the plugin from the project tooling area, then add it to the existing React plugin rather than introducing a second JSX compiler.

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import uiForgeSourceTags from './tools/ui-forge/babel_source_tags.mjs'

export default defineConfig(({ mode }) => ({
  plugins: [
    react({
      babel: {
        plugins: mode === 'development'
          ? [[uiForgeSourceTags, { root: process.cwd() }]]
          : [],
      },
    }),
  ],
}))
```

If the project already provides Babel plugins through `@vitejs/plugin-react`, append UI Forge to that list rather than overwriting existing transforms.

## Visual edit loop

1. Run the app in development mode with source tags enabled.
2. Select or target the rendered element using Playwright/Reflex/browser tools.
3. Capture `scripts/dom_probe.js` evidence or equivalent fields.
4. If `data-ui-forge-source` exists, `scripts/source_locator.py` resolves it directly.
5. Change the smallest owning token/class/prop/source region.
6. Let hot reload render the result.
7. Re-probe the element and verify surrounding layout/behavior.
8. Run responsive/browser evidence before completion.

## Safety and cleanliness

- Enable only in development/preview by default.
- Never treat source tags as authentication or authorization data.
- Do not expose absolute local paths; the plugin emits project-relative paths when the configured root matches.
- Do not use the tags to bypass project rules or edit generated/vendor files.
- Remove/circumventing tags is not a failure: fall back to semantic DOM fingerprint matching.

## Stability note

`data-ui-forge-id` is designed to remain stable across ordinary line-number changes. It can change when element ordering within the same owner/tag group changes. The source pointer is intentionally exact rather than stable; it should move with current source. Treat both as development aids, not permanent database identifiers.

## Preview-before-commit loop

When `visual_edit_bridge.js` is injected into a development preview, UI Forge can test a safe visual change before touching source:

1. select the rendered element (`UIForge.select(...)` or point selection)
2. call `UIForge.preview({type: ...})` for a supported text/class/allowlisted attribute change
3. inspect geometry/computed-style effects in the real browser
4. call `UIForge.commitSpec()`; it is commit-ready only when the element carries an exact `data-ui-forge-source`
5. feed that `source_edit` to `direct_ast_edit.mjs --dry-run`
6. apply only when the direct editor accepts the exact static JSX target and syntax reparse passes
7. rerender/re-probe the real app; use `revertPreview()` or Escape to cancel the temporary browser change

The preview never mutates source by itself and must not be treated as evidence that the source edit has landed.

## Atomic multi-select edits

For repeated safe visual changes, select multiple exact-tagged DOM nodes with `visual_edit_bridge.js`, preview the operation across the group, and request `commitBatchSpec()`. Commit with `scripts/batch_ast_edit.mjs`, not a loop of independent writes. The batch path dry-validates every operation, rejects duplicate source pointers, applies same-file edits in descending source position, and restores all touched files if any write fails.

A batch is commit-ready only when every selection has a unique exact source pointer. Runtime-owned state still requires runtime-owner tracing rather than static batch editing.

## CSS ownership editing

Source tags identify the JSX element, but visual style may be owned by a stylesheet rule. For safe direct style adjustments, use the browser probe from `visual_edit_bridge.js` with `scripts/css_style_editor.mjs`. It ranks the rightmost selector compound using id/class/tag evidence and fails closed on tied ownership unless the caller supplies explicit `file` and `selector`. Browser `style_props` previews must be reverted before commit; the persistent change belongs in CSS, not the preview inline style.
