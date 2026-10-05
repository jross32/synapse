# UI Forge Interaction State Lab

Interaction State Lab makes CSS pseudo-state edits explicit, ownership-aware, and browser-proven.

Supported direct state owners:
- `:hover`
- `:focus`
- `:focus-visible`
- `:active`
- `:disabled`
- `:checked`

## Why state editing is separate

The base rule for an element and its interaction-state rules are different source owners. UI Forge base-state CSS resolution intentionally ignores pseudo selectors, so a normal visual adjustment can never silently land in `:hover` or `:focus`.

For a state edit, pass `state` in the style request sent to `scripts/css_style_editor.mjs`. Automatic resolution requires exactly that one pseudo-state in the rightmost selector compound. Combined/structural selectors such as `.button:hover:focus`, `:not(...)`, `:has(...)`, or pseudo-elements require an explicit file + selector or the main coding path.

## Preview versus proof

`visual_edit_bridge.js` can preview a state design with:

`UIForge.preview({type: "style_props", state: "hover", properties: {...}})`

The browser preview is a **simulated inline design preview**. It answers “does this visual treatment look right?” without changing source. It does not prove the real pseudo selector works.

`styleCommitSpec()` returns the selected probe, declarations, state, and `preview_mode="simulated-inline-state-design-preview"`. Commit through `css_style_editor.mjs`, then exercise the real browser state.

Examples of real proof:
- hover: use Playwright `hover()` and verify computed style while pointer is over the element, then move away and verify base state remains unchanged;
- focus/focus-visible: focus or keyboard-tab to the element and verify visible focus styling;
- disabled: verify the control is actually disabled and inspect computed style/operability;
- checked: check a real checkbox/radio and verify the state-specific styling;
- active: hold pointer/key activation while capturing the computed state.

## Completion rule

A pseudo-state edit is not complete until:
1. exact state owner resolved or explicit owner declared;
2. source commit reparses successfully;
3. real browser state is exercised;
4. base/neighbor states are rechecked for regressions;
5. source identity remains stable where source tags are available;
6. desktop/mobile proof and console/runtime health remain acceptable.

Do not substitute an inline preview or static screenshot for real state proof.
