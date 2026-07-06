# Synapse — UI screenshots

Real screenshots of the running app, captured from the live renderer (Vite `:5173` + daemon `:7878`) via Playwright. **These evolve as Synapse is built** — when a change alters a user-visible surface, the affected image here is refreshed in the same commit (see the screenshot rule in `AGENTS.md`).

_Captured 2026-07-06 against daemon `v0.1.37`, 29 registered projects, with live browser proof for the AI Coding cockpit, the ChatGPT companion, and the Web Scraper harvest workspace. The ChatGPT companion captures honestly show the browser-preview fallback message; the signed-in embedded bridge runs in the desktop Electron app._

## Home — mission control (desktop, 1280×800)

![Home desktop](./home-desktop.png)

Featured-app slideshow, running/not-running/errored counts, live recent-activity feed, "Jump in" quick actions, and the "Built for AI agents too" panel. "Connected to daemon" — real data rendering.

## Home — mobile (375×812)

![Home mobile](./home-mobile.png)

## AI Coding — the coder cockpit (desktop, 1280×800)

![AI Coding cockpit](./cockpit-ai-coding-desktop.png)

Project-thread workspace focused on the bundled **Synapse Self** project, showing the self-improvement cockpit and the review-driven coding surface where UX/QA/token-efficiency/judge passes live.

## ChatGPT Companion — desktop (1280×800)

![ChatGPT companion desktop](./chatgpt-companion-desktop.png)

The new AI Coding sub-tab for browser-managed ChatGPT work: project-targeted save-back, draft/revise controls, and the live bridge area that upgrades to the signed-in embedded experience in the desktop app.

## ChatGPT Companion — mobile (375×812)

![ChatGPT companion mobile](./chatgpt-companion-mobile.png)

Phone-width proof for the same companion surface, captured at 375 px wide from the live renderer.

## Web Scraper — design harvest workspace (desktop, 1280×800)

![Web Scraper harvest desktop](./web-scraper-harvest-desktop.png)

The dedicated installed-page workspace for reference capture, provenance/adaptation labeling, generated component previews, and adopted project artifacts.

## Web Scraper — design harvest workspace (mobile, 375×812)

![Web Scraper harvest mobile](./web-scraper-harvest-mobile.png)

### Verified finding (2026-07-05) — feeds the cockpit work

The cockpit still **works** but remains **project-scoped only**: you pick a registered project first, then start a thread inside it. The new Synapse Self project makes that workable for self-improvement, but the project-free "New chat" idea is still a real future polish target rather than something this wave solved.
