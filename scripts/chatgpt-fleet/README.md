# ChatGPT UI fleet (manual toolkit)

Copy config.example.json to config.json (gitignored), set your own project URL, local Synapse auth-token file, and owned chat-list file. Do not commit config.json or tokens. Requires an authenticated shared Playwright MCP registered as playwright in Synapse.

1. Create worker worktrees sequentially, with explicit ownership and a separate integrator lane.
2. Render worker-preamble.template.txt per lane. Dispatch with PowerShell: `./dispatch.ps1 -PromptFile lane.txt`.
3. Read the browser tab list after dispatch and record actual /c/ URLs in chatsFile as `lane|url`. Never control unowned tabs.
4. For follow-ups use `./followup.ps1 -ChatId <id> -PromptFile continue-worker.txt`.
5. For a manual pass run `./nudge.ps1`. This is not a daemon scheduler.

Selectors and browser session behavior are version-dependent. Stop on missing connector, generating worker, or browser restart. Do not use the dispatch result URL as durable identity until confirmed in tab list.
