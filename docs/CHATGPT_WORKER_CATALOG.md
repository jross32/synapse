# Synapse ChatGPT UI Worker Catalog — v0.4 workflow

The **Worker Catalog** is a durable, AI-readable index of ChatGPT UI workers. A Chrome tab is only temporary browser presence; the saved conversation, task, work-item links and handoff survive tab closure.

## Where to find it

Open **Synapse → Apps → AI Workers**. The screen lives in `renderer/pages/WorkerCatalog.tsx`, wired through `renderer/pages/AiCoding.tsx`. It uses the existing Synapse daemon API, not localStorage or a second independent database.

The catalog presents **Current, Open, Working, Parked, Failed, Archived** views, search by project/title/work item/assignment/handoff, and buttons for **Resume**, **Handoff**, **Archive** and **Restore**. Its worker count describes saved records; the Chrome extension badge counts *open browser tabs only*.

## Worker lifecycle

1. **Create/reuse:** Before assigning a new ChatGPT UI subworker, query the catalog and reuse a relevant worker conversation or work item when possible. Use the exact **Synapse2GPT Workers** ChatGPT Project, **Chat mode (not Work mode)**, and **@Synapse** plugin.
2. **Automatic registration:** The updated Chrome extension observes the new worker conversation URL and posts it to `/thread-presence/browser-observe`. Synapse now auto-registers the conversation in the existing worker registry, with its title/current task/status. It does not invent a work-item link; manually registered work-item workers remain authoritative. Only the approved worker-project conversation URL is imported.
3. **Working:** The assistant performs a scoped task and reports actual tools, changed source, tests and errors. Persist real progress in Synapse's work items and **Handoff** field. An observed generation is active presence, not proof the code was correctly modified.
4. **Park:** An idle worker can have its Chrome tab closed. The extension also offers a page context-menu action **Park Synapse worker (close tab, keep saved chat)** and refuses it during generation, with unsent drafts or when it cannot verify state. Closing sends a `gone` observation with canonical URL, does not archive/delete the worker record, and reduces the toolbar count. Crashes/disconnects are handled conservatively using a presence timeout.
5. **Resume:** Find the saved worker, inspect its assignment and handoff, click **Resume** to reopen its original canonical URL in Chrome, then continue the same conversation. The extension rejoins the tab to one existing group. An archived worker should first be explicitly restored.
6. **Archive:** Intentional retirement is separate, auditable and reversible. Use Archive/Restore; do not delete ChatGPT history or copy credentials.
7. **Close an active worker:** Do not automatically close workers that are generating, have unsent drafts, or have uncommitted/unsaved work. Prefer waiting for a handoff and explicit idle state.

## Durable data

Existing `daemon/synapse_daemon/chatgpt_worker_chats.py` is the source of truth. Imported browser-created records have `metadata.source="chrome_observer"` plus `current_task`, `browser_status`. Handoff notes/next step are stored in metadata using the new authenticated handoff API. Work-item-managed workers are never overwritten by the import mechanism.

- `GET /api/v1/chatgpt-workers/catalog?include_archived=true`: worker rows plus `open_in_browser`, `browser_activity`, `parked`, counts.
- `GET /api/v1/chatgpt-workers`: original registry list.
- `POST /api/v1/chatgpt-workers/{id}/handoff`: JSON `{"handoff_md":"...","next_step":"..."}`; up to 6000/2000 characters.
- `POST /api/v1/chatgpt-workers/{id}/archive` and `/unarchive`: reversible explicit lifecycle.
- `POST /api/v1/thread-presence/browser-observe`: idempotent registration/update from Chrome.
- AI discovery: `GET /api/v1/ai/context` advertises the catalog and handoff routes; `docs/api-finds.md` explains usage.
- Browser extension: `browser-extensions/chatgpt-presence-companion`, source v0.4.0.

**Security:** Never extract Chrome cookies, passwords, login tokens or entire private ChatGPT transcripts. Only strict HTTPS URLs for the approved ChatGPT worker project can be automatically indexed.

## Verification and release gates

- `npm run typecheck` validates the renderer and Electron TypeScript.
- `python -m pytest daemon/tests/test_chatgpt_worker_catalog.py daemon/tests/test_chatgpt_worker_chats.py -q` validates durable registration, parked/reopened, archive/unarchive, handoff and malicious URL exclusions.
- `node browser-extensions/chatgpt-presence-companion/test-group-workers.mjs`, `test-service-worker.mjs`, `test-content.mjs` validate mocked Chrome group lifecycle, badges and safe parking.
- Live integration remains a separate gate: Reload unpacked **Synapse ChatGPT Presence** and confirm **v0.4.0** in `chrome://extensions` with no service-worker errors; open two real worker conversations; confirm badge/group, close an idle worker (saved URL intact and count decreases), locate it in Synapse Catalog, Resume same URL into same group, inspect handoff, then verify archive/restore. Do not mark installed/production-verified until this actually happens.
- Existing Synapse daemon may be older than frontend source. Avoid unsafe restarts or rotating the stable MCP URL; verify running backend before claiming catalog live.

See `docs/CHATGPT_CHROME_WORKER_RUNBOOK.md` and the extension README for Reflex and browser details.
