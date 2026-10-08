# Optional Browser UI Audit

Use this optional reusable Synapse utility when checking a web app's desktop/mobile layout, navigable public pages, visible controls, bottom scroll behavior, accessibility names, JavaScript errors, and horizontal overflow.

Run from Synapse repository:

```powershell
node scripts/ui-audit.mjs http://127.0.0.1:5215 .tmp-my-audit
```

For a public site, substitute its actual URL. Results include JSON evidence and full-page desktop/mobile screenshots. Nonzero exit means errors or overflow. This is a **smoke audit**, not a certification that every button works: it does not click state-changing controls, submit forms, log in, or perform destructive actions. AI workers should use Playwright/Reflex manually for those flows with isolated test accounts, then add deterministic regression tests for discovered bugs.

The script uses Synapse's existing Playwright dependency, is read-only, and does not require the tool to be used. Improve it incrementally when a reproducible test gap appears, without modifying other concurrent worktrees.
