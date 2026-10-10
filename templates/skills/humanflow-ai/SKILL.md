---
name: humanflow-ai
description: Invoke for requests to explore, test, evaluate, audit, or click through a website as a human visitor. Open and establish website access BEFORE asking the user to choose Levels 1–5.
---
# HumanFlow AI — human-oriented website journey testing

## Mandatory conversational gate
1. Receive a website URL (or resolve an authorized project URL) and user goal. Use the real website; do not pretend screenshots, clicks or successful login occurred.
2. Discover the browser tools currently available via Synapse MCP list, preferably Playwright; optionally leverage Web Scraper and Reflex. Open site and observe initial rendering/navigation. Check whether the requested journey requires auth. If login is required, reuse an authorized test session or ask for permission and test account information; do not create an account without approval or bypass CAPTCHAs, MFA, access restrictions. Never log or include secrets in artifacts. Account creation is a separate approval-gated operation.
3. As soon as access is established (whether public or authenticated), STOP BEFORE SUBSTANTIVE AUDIT and present the five selectable audit levels below in the conversation. Say which site/session was successfully accessed. A real interactive selector is preferred when the host supports it; otherwise ask the user to reply with a number 1–5. Do not choose for them, assume level 3, or silently continue. Persist/reuse the authorized browser session and audit state across this pause; if the browser session expires, reopen and report.
4. After the user chooses the depth, carry out that depth of journey and report witnessed results, issues, priority, reproduction steps and evidence, labeling anything not tested clearly.

## Audit depth menu (show AFTER browser access)
**Choose your HumanFlow audit depth:**
1. **First Impression** — visual clarity, messaging, hierarchy, typography, colors, primary CTA, trust and perceived polish.
2. **Human Exploration** — level 1 plus menus, content discovery, navigation, links, affordances, user confusion and dead ends.
3. **Complete User Journey** — level 2 plus execute the user's objective with safe dummy data, forms, uploads, editing, saving and verifying persisted results.
4. **Full UX/UI Audit** — level 3 plus desktop/mobile widths, keyboard and accessibility checks, errors, loading, contrast, overflow, usability and consistency.
5. **Autonomous Deep Audit** — level 4 plus multiple user roles/paths, boundary states, repeatable regression suites, comparative screenshots, issue tickets, and evidenced re-tests where applicable.
Audit levels build cumulatively; do not claim native Safari testing based on browser emulation.

## Human-perspective decision loop
For each step, write internally: user intent -> visible affordance -> predicted behavior -> action -> observed result -> friction -> next step. Evaluate whether a new user could discover, understand and recover from each action, NOT just whether a click succeeded. Follow the product's intended task, rather than indiscriminate crawling. Use semantic locators and actual screenshot/layout inspection, with computed styles and element bounds for visual defects. For each visual issue, record viewport, screenshot reference, observed bounds/contrast when available and human impact. Detect blockers, hidden or overlapping UI, color/theme inconsistencies, inaccessible controls, confusing microcopy, error/empty/loading states and feedback.

## Routing and safety
Use Playwright/Reflex for interaction, Web Scraper for discovery and HTTP/links; reuse UI Lab for responsive/accessibility screenshots, FirstRun Studio for login/onboarding, UI Forge for reference/design contracts, Visual Fidelity Loop for comparisons. Discover exact tool names and arguments rather than guessing. Never bypass bot protection, verification or rate limits. Only test websites the user is authorized to access; stay in stated scope and rate-limit exploration. Before financial transactions, destructive changes, invitations, public postings, external messages or other material side effects, pause for explicit approval. Avoid password/token leakage, sanitize artifacts and preserve test data boundaries. Do not fabricate successful actions when tools fail. Stop and ask when a blocked action needs user input, resuming from a checkpoint afterward.

## Output / machine-readable contract
Return site URL, goal, level chosen, session/access status, device/browser provenance, actual pages and interactions visited, achieved or blocked goal, usability and functional findings separately, screenshots/evidence and missing coverage. Each finding: id, severity (critical/high/medium/low), location/viewport, user impact, reproduction steps, observed vs expected, supporting evidence, proposed fix and retest status. Include prioritized next fixes and suggested automated regression steps. Use status values passed, failed, blocked and not-tested. Never present estimates or unobserved paths as verified results.

## AI invocation examples
- 'HumanFlow this website' -> open site -> auth if needed -> ask 1–5 menu.
- 'Use HumanFlow on ResellTogether' -> resolve running authorized URL -> open site -> ask 1–5 menu.
- 'HumanFlow level 5 on this site' -> open site -> check access -> honor explicit level 5 without reasking, then audit.
- If user has already selected a level during a paused audit, resume the same browser session and start immediately.

## Integration
Pack should be installed into Synapse portable skill registry. Quick action 'Run HumanFlow AI' advertises chat-first execution. A skill alone cannot force a selector in unrelated ChatGPT sessions without this skill being discovered and tools connected; never claim universal account-level integration until verified.
