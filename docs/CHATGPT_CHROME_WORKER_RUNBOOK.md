# ChatGPT Chrome worker runbook (Synapse / Reflex)

Last live verification: 2026-10-12. Project: Synapse Self. This is an **observed, partially automated workflow**, not yet an autonomous five-worker system.

## Canonical locations

- Windows source cwd: `C:\Users\justi\synapse`.
- ChatGPT Project: **Synapse2GPT Workers**, NOT the similarly named Synapse2GPT.
- Project URL: `https://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e/project`.
- Worker 1 (connector smoke): `https://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e-synapse2gpt-workers/c/6acd53ef-fde0-83e9-a7f4-471a9257fa2c`.
- Worker 2 (read-only inspection): `https://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e-synapse2gpt-workers/c/6acd5519-c1cc-83e9-94da-d28c4c01edbd`.
- Existing Chrome tab group label seen: `Synapseworkers Ch...`. **Reuse this one group**, don't make a group for every worker.
- Chrome companion extension: `browser-extensions/chatgpt-presence-companion`; source v0.3.0 (installed Chrome version requires reload/verification).
- Reflex MCP through Synapse: `synapse_list_mcp_tools(server="reflex")` for schemas, `synapse_call_mcp_tool(server="reflex",tool=...,arguments=...)`.

## Proven browser flow

1. Call `synapse_get_context`, bootstrap the durable Synapse Self thread, begin turn. Ask Reflex `request_control({agentName:"Synapse ChatGPT Worker",showOverlay:true})`. User can stop it at any time.
2. `take_screenshot({})`, inspect the **actual** full-resolution image. Chrome must be foreground. Reflex mouse coordinates are desktop screen coordinates; avoid deriving them from a downscaled preview. If Chrome is not foreground, use `list_windows_detailed` and `focus_window`.
3. Open a new tab with `press_key({key:"^t"})`; `type_text({text: PROJECT_URL})`; `press_key({key:"{ENTER}"})`. Wait for the project page to render. Verify **Chat** is selected, **not Work**.
4. In the project page, click the project-scoped composer (seen at approx x 700-1300, y 300 on a 1648x928 screenshot; these are **observations, not portable click coordinates**). To avoid unreliable long simulated typing, `write_clipboard({text: PROMPT})` then click composer and `press_key({key:"^v"})`. Confirm exact prompt visible in screenshot.
5. Type `@Synapse` or explicitly select the **Synapse** plugin from the composer mention menu. The mention UI can consume Enter and/or cause duplicate paste: **inspect screenshots after selecting the plugin** and before submitting. The selected Synapse chip is shown above composer. Prefer mention selection before pasting the body. Ensure the full prompt appears **once**.
6. Click the blue send arrow after screenshot confirmation. Verify the URL changes to a canonical `/c/<conversation-id>` and the message appears. Do not mistake a composer Enter that only selected a plugin for actual submission.
7. Await response via fresh `take_screenshot`; read the answer, inspect tool-call claims, independently verify material changes/tests. Record canonical chat URL, assignment, project, result, tools used, and status in Synapse AI context/work items.
8. Keep the new worker tab inside the **existing single Chrome group**. Chrome group insertion may not happen automatically when using Ctrl+T from the final group tab; inspect the tab strip. If necessary use Chrome tab context menu **Add tab to group > existing Synapse group**, or Chrome extension `chrome.tabs.group({tabIds:[newTabId],groupId:existingGroupId})`. Do not create a second group.
9. `release_control({})` on completion. Finish the Synapse thread turn with evidence and any limitations.

## Live proof and gaps

- Worker 1 chat visibly reported `Connector test passed` and successful Synapse Self read-only access; no code writes.
- Worker 2 chat visibly reported `Synapse connector invoked successfully` and showed Synapse backend v0.1.209, Synapse Self source path. Full response still requires inspection for tool details.
- Worker 2 was created in a **new Chrome tab** from the correct ChatGPT Project and **manually joined to the existing Chrome group** using right-click tab > Add tab to group > `Synapseworkers ChatGPT automation setup`. The cyan group outline was visually verified. Extension auto-grouping is not yet live-verified.
- The second chat had duplicate prompt text in a preliminary attempt due to `@Synapse` mention handling and clipboard paste; final submitted prompt also showed duplicated segment. Improve this by first selecting the plugin, then clear composer, then paste only body once and inspect.
- Manual Chrome grouping was verified. Extension v0.3.0 source passed Chrome-API mock tests, but requires Chrome reload and live verification. Five concurrent workers, source-write capability, independent agent execution, worker URL registration and recovery **remain unverified**. No credentials or cookies should be extracted.

## Worker prompt template

```text
You are ChatGPT Worker <N> in the Synapse2GPT Workers project.
Remain in Chat mode; do not switch to Work mode.
Use the @Synapse plugin and make real Synapse tool calls to inspect the specified project.
Task: <bounded task>.
Source cwd: C:\Users\justi\synapse. Preserve unrelated concurrent changes.
Before editing, inspect relevant source and existing instructions. For code tasks, edit only scoped files,
run actual tests, and report changed paths, tests, errors, and a concise handoff.
Never claim success without evidence. Do not perform unrelated changes.
```

Use a read-only version for smoke tests. Use separate bounded scopes for concurrent workers; avoid conflicting files. Reuse existing chat URL when continuing same worker.



## Synapse default AI worker interpretation

When a user asks for `AI worker`, `sub-worker`, `subagent`, `ChatGPT UI worker`, `ChatGPT browser worker`, `ChatGPT in Synapse`, or `open another AI to help` **and the context is ChatGPT UI**, default to this exact workflow, not Codex, Work mode, or an unrelated child browser profile. Use Reflex for desktop-control operations by default; assume it should be available but still check its real control state and release control afterward.

1. Prefer the existing signed-in Chrome profile/session (never copy cookies, tokens or passwords). Chrome may be minimized/behind other apps. Use Reflex `get_active_window`, `list_windows_detailed`, `get_screen_size`, `take_screenshot` to identify it, then restore/focus without closing other windows. Beware Windows DPI scaling and user concurrent input; do not click from unverified rescaled screenshot coordinates.
2. Find or create the ONE existing **Synapse Workers** group. With extension source v0.3.0 loaded, opening a worker ChatGPT conversation should **automatically add it**. The extension toolbar click can also create an empty group and collect saved worker URLs. If the extension is not installed/reloaded, use right-click worker tab > Add tab to group > existing **Synapseworkers ChatGPT automation setup**. Do **not** add a duplicate group.
3. Open a new **Chrome tab inside the group** when possible. Navigate directly to the exact project URL above; don't use the similarly named non-worker Synapse2GPT project.
4. Confirm the **Chat** segment is selected (not Work). Select actual **@Synapse** plugin via autocomplete/chip first, then paste *one* scoped prompt through Reflex clipboard and send.
5. Wait for completion; inspect full response, verify actual Synapse connector activity and source/test evidence where warranted. Record worker conversation URL, assignment, status, tests, errors, tool calls and owner context in Synapse. Reuse that chat for continuing the same worker.
6. Confirm the Chrome group and toolbar badge are consistent. **Badge counts open chat tabs, not autonomous jobs.** Green indicates observed active generation, and group label includes number active. Active in-tab toast is informative; not proof a source-code operation succeeded.
7. Call Reflex `release_control`. Always return a short truthful handoff. Avoid altering other Chrome tabs or windows.

### Extension v0.3.0 verification status and quality gates

- Source: `browser-extensions/chatgpt-presence-companion/{manifest.json,group-workers.js,service-worker.js,content.js}`.
- Regression tests: `node browser-extensions/chatgpt-presence-companion/test-group-workers.mjs`, `node browser-extensions/chatgpt-presence-companion/test-service-worker.mjs`.
- Tests cover canonical URL with `-synapse2gpt-workers` slug, one-group reuse, no duplicates, empty registry, auto group, badge count=2, active=1, idle=0, button group collapse. Mock tests passed on 2026-10-12.
- Live Chrome still requires confirming **v0.3.0** appears in `chrome://extensions`, service worker has no errors, two real workers show badge `2`, opening a third chat automatically joins the existing group, active notice appears while working, and click collapses without closing anything.
- When the desktop isn't in a stable state (another application foreground, user using the PC, Reflex mouse/DPI issues), do not claim live verification or click into unrelated apps. Use programmatic tests and report the explicit blocker.
