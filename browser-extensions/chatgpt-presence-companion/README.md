# Synapse ChatGPT Presence

Read-only Chrome companion for normal ChatGPT tabs on this PC.

It does not send prompts, click conversations, read cookies, or contain a Synapse token.
Its background worker asks the running local Synapse daemon for the loopback-only token
and reports only to http://127.0.0.1:7878.

Observed fields: conversation URL/id, title, generating/idle/error state, latest visible
user message as a task hint, generation start time, and visible "Worked for ..." duration.

This is for already-open/manual browser threads. Synapse-managed headless ChatGPT workers
use the same backend records directly from Playwright and do not require the extension.

Load unpacked from chrome://extensions and select this folder. Existing chatgpt.com tabs
then begin reporting without opening or focusing each conversation.