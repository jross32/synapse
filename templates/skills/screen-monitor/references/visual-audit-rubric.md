# Screen Monitor visual audit rubric

Use this rubric to turn a screenshot into an actionable finding instead of a vague opinion.

## Severity

**P0 — blocking**
- app cannot be used or reached
- crash or fatal dialog
- primary workflow is visibly impossible to complete

**P1 — major**
- primary action hidden, off-screen, or covered
- modal or overlay traps the user
- severe clipping or overflow makes core content unreadable
- intended action produces no visible feedback and appears failed

**P2 — moderate**
- confusing hierarchy
- important text truncated
- obvious responsive spacing or layout defect
- state change is visible but unclear
- inconsistent controls that materially slow the task

**P3 — polish**
- small alignment or spacing issue
- cosmetic inconsistency
- non-blocking visual roughness

## Finding contract

Every actionable finding should include:

- **Target:** app, window, page, or state
- **Trigger:** what immediately preceded the frame
- **Expected:** what a normal user should visibly see
- **Actual:** what is visibly present
- **Severity:** P0-P3
- **Evidence:** screenshot or frame timestamp, or a precise visual description
- **Confidence:** high, medium, or low
- **Next evidence:** only when confidence is not high

## Human-view checks

Look for:

- first-screen hierarchy
- primary action visibility
- readable typography
- clipping or truncation
- horizontal overflow
- overlapping panes, cards, or modals
- unexpected blank regions
- duplicated UI
- stale loading indicators
- missing feedback after actions
- disabled state that looks enabled, or the reverse
- focus or selection visibility when relevant
- obvious touch-target or spacing issues
- desktop or mobile mismatch
- window resizing problems
- toast or dialog placement
- error text actually visible to the user

## Avoid false certainty

A screenshot alone cannot prove:

- keyboard order
- screen-reader labels
- ARIA correctness
- backend persistence
- network success
- hidden data correctness
- behavior over time beyond the captured transition

Pair visual evidence with Playwright, logs, API state, tests, or project data when those claims matter.
