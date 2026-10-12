# Synapse ChatGPT Presence — Chrome extension v0.4.0

Synapse's owner-controlled Chrome companion for ChatGPT UI workers. It manages **one reusable Chrome tab group**, counts open workers, observes generation activity, and lets you **park** an idle worker without losing the saved conversation. It is a browser organizer/presence bridge, not a separate ChatGPT execution runtime.

## Worker workflow

1. Open the owner’s already-signed-in Chrome profile. Use the ChatGPT Project **Synapse2GPT Workers**:
   `https://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e/project`
2. Remain in **Chat mode (not Work)** and select the **@Synapse** plugin for coding tasks.
3. New project-scoped worker chats join the existing **Synapse Workers** Chrome tab group automatically. The toolbar button prepares the group and collapses it when needed; it does **not** reopen parked conversations automatically.
4. Toolbar badge = number of **open worker chat tabs**. Purple indicates no currently observed active generation; green indicates at least one observed active generation. The group title and tooltip include the active count.
5. When generating, the ChatGPT worker page briefly displays an activity notice. It does not claim that source-code changes succeeded.
6. To **park** a finished worker, close its browser tab normally, or right-click **inside the worker ChatGPT page** and choose **Park Synapse worker (close tab, keep saved chat)**. The menu refuses to close a worker that is generating, has an unsent draft, or cannot be inspected safely.
7. The Chrome extension reports canonical conversation URL and gone/idle status to Synapse; the durable Synapse Worker Catalog preserves the conversation and assignment. Resume later from **Synapse → AI Coding → ChatGPT → Worker Catalog → Resume**. Opening the saved URL rejoins the group.
8. **Archive** is a separate explicit catalog action and does not delete the conversation in ChatGPT.

## Install/upgrade in existing Chrome

The unpacked extension source is:
`C:\Users\justi\synapse\browser-extensions\chatgpt-presence-companion`.

Open `chrome://extensions`, keep Developer mode enabled, find **Synapse ChatGPT Presence**, and click the card’s **Reload** icon. Confirm it displays **0.4.0**, enabled, without extension errors. After reloading an unpacked extension, refresh any already-open ChatGPT worker pages once so the new content script is loaded.

If Chrome still shows an earlier version, inspect the extension's **Details → Extension path** (or the profile's recorded install path) and confirm that it matches the source path above. Do not delete the user’s existing tabs, cookies, Chrome profile, or worker conversations.

**Note:** Source version 0.4.0 and automated test results do not prove that Chrome has loaded 0.4.0. Live reload and visual verification must be recorded separately.

## Development and checks

Run from cwd `C:\Users\justi\synapse`:

```powershell
node --check browser-extensions/chatgpt-presence-companion/group-workers.js
node --check browser-extensions/chatgpt-presence-companion/service-worker.js
node --check browser-extensions/chatgpt-presence-companion/content.js
node browser-extensions/chatgpt-presence-companion/test-group-workers.mjs
node browser-extensions/chatgpt-presence-companion/test-service-worker.mjs
node browser-extensions/chatgpt-presence-companion/test-content.mjs
```

The Node tests simulate Chrome's APIs, including two open workers, badge counting, active/idle transition, safe park refusal, successful park with saved conversation URL, and group reuse. Actual Synapse catalog persistence is separately tested in `daemon/tests/test_chatgpt_worker_catalog.py`.

## Boundaries and privacy

No Chrome credentials, authentication cookies, copied browser profiles, or full chat transcripts are stored by this extension. `chrome.storage.session` holds only the conversation URL and worker key needed for reliable close observations across Manifest V3 service-worker suspension. The Synapse daemon's worker registry, not Chrome tabs, is the durable Worker Catalog.

Do not close actively generating or unsent workers. Never confuse `idle` with `complete`, or `tab closed` with `worker archived`. A future AI should search the Worker Catalog and existing work-item links before creating a duplicate worker.

See `docs/CHATGPT_CHROME_WORKER_RUNBOOK.md` and `docs/CHATGPT_WORKER_CATALOG.md`.
