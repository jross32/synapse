# Synapse ChatGPT Presence — Chrome extension v0.3.0

**Purpose:** Keep ChatGPT UI workers in **one reusable, collapsible Chrome tab group** in the owner's existing signed-in Chrome profile. The workers use the **Synapse2GPT Workers** ChatGPT Project and **Chat mode, NOT Work mode**. This extension organizes tabs; it does not itself send ChatGPT prompts or create AI sessions.

## What is implemented

- **Automatic organization:** When a ChatGPT conversation in the exact worker project is opened or navigated to, the extension detects it and joins it to the existing Synapse worker group. If no matching group exists, Chrome's `tabs.group()` and `tabGroups.update()` create a cyan **Synapse Workers** group.
- **Reuse:** Matches existing user group names such as `Synapseworkers ChatGPT automation setup`. Never creates one group per worker. Grouping an already grouped tab is skipped.
- **Start empty:** Clicking the extension button with zero chats creates a group containing the Synapse2GPT Workers project home; badge remains `0`.
- **Badge:** Number of **open worker conversation tabs** in all Chrome windows. Purple means no observed active generation; green means one or more observed active generations. Tooltip and group title include current **active** count.
- **Active notice:** During an observed ChatGPT generation in the worker project, a small, temporary in-page notice says `Synapse is active in this worker group`. It is not a system-wide toast. It requires the ChatGPT page content script to see the generation state.
- **Button:** Clicking the extension also looks up durable worker conversation URLs from the authenticated local Synapse daemon and opens missing worker chats into the single group. Existing tabs in other windows are not moved. If the daemon is unavailable, grouping **open** ChatGPT worker tabs remains possible.
- **Collapse:** Extension button collapses the group; automatic grouping while chatting does not collapse your active tab.
- **Privacy:** No Chrome login data, cookies, passwords, or browser profile copies. Only approved ChatGPT project URLs and local Synapse presence API.

## Install or upgrade in current Chrome

1. Open `chrome://extensions` in the user's existing signed-in Chrome window.
2. Leave Developer mode enabled. The unpacked extension is at `C:\Users\justi\synapse\browser-extensions\chatgpt-presence-companion`.
3. **Click Reload** on the **Synapse ChatGPT Presence** extension card. Confirm it reports **0.3.0**, enabled, and no manifest/service worker error.
4. Pin the toolbar extension if not already pinned.
5. Visit `https://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e/project`. Start a new chat **in Chat mode**, explicitly select `@Synapse`, and send a bounded worker task.
6. Verify the created conversation is joined to the **existing cyan worker group** and the extension badge reads the correct number.
7. While the worker is generating, verify green badge, active-count title and temporary notice. Verify idle recovery when it completes.
8. Click extension icon to collect and collapse the group. Expand from Chrome's group label as desired.

## Tests

From cwd `C:\Users\justi\synapse`:

```powershell
node --check browser-extensions/chatgpt-presence-companion/group-workers.js
node --check browser-extensions/chatgpt-presence-companion/service-worker.js
node --check browser-extensions/chatgpt-presence-companion/content.js
node browser-extensions/chatgpt-presence-companion/test-group-workers.mjs
node browser-extensions/chatgpt-presence-companion/test-service-worker.mjs
```

The Node tests mock Chrome's APIs to verify URL filtering, group creation/reuse, count, active/idle transitions, offline fallback, and idempotence. **Passing mocks is not evidence that the new unpacked extension was reloaded or verified in real Chrome.** The latest live Chrome verification prior to v0.3.0 showed the installed version 0.2.0 and a zero badge, despite two open worker conversations. A real Chrome v0.3.0 reload plus smoke test is still required.

## Limits / workflow boundary

The extension is a **Chrome UI organizer and presence observer**, not the ChatGPT browser task executor. Use Reflex for real browser navigation, entering prompts and reviewing replies. A ChatGPT worker chat reporting a Synapse tool call is not independent proof of source modifications or test results; check the reported evidence. Do not silently switch to Work mode, assume five workers exist, or alter unrelated tabs. See `docs/CHATGPT_CHROME_WORKER_RUNBOOK.md`.
