# Synapse Localization Studio

## Mission
Build measurable, reusable, fast, context-aware localization. Start with en-US and es-MX, then expand through the same locale-pack contract.

## Architecture
- General locale packs are standards-based. Never encode one person's idiolect as general language truth.
- Optional personal-language profiles are private overlays.
- Preserve original user-authored text; translations are views, not destructive replacements.
- Use semantic keys such as auth.sign_in rather than English strings as identifiers.
- Support variables, plurals/selects, dates, times, numbers, currency, units, and grammatical selection where required.
- Use explicit fallback, e.g. es-MX -> es -> source.
- A locale is not supported until coverage and browser QA pass.

## Standards
Use BCP 47 locale identifiers and Unicode CLDR data. Prefer MessageFormat-compatible structured dynamic messages. Never assume English plural behavior.

## Locale pack contract
Declare locale id, display name, fallback, direction, terminology/glossary, messages, formatting policy, tone/register guidance, ambiguity guidance, benchmark fixtures, and version/provenance.

## es-MX first
Use natural Mexican Spanish for apps and everyday communication. Prefer meaning and naturalness over calques unless literal mode is requested. Preserve names, amounts, dates, URLs, SKUs, identifiers, and authored emphasis.

## Personal profile
A profile may learn observed spelling variants, recurring expressions, preferred interpretations/output register, correction history, and confidence. It must not alter base es-MX globally. Keep original text and allow profile-off behavior.

## App workflow
Inventory user-visible strings; establish locale framework; migrate to keys; persist locale; localize navigation/forms/auth/errors/toasts/loading/empty states/modals/emails/notifications; format dynamic values; test mobile/desktop; scan for source-language leakage; test overflow/accessibility; verify persistence; emit a coverage receipt.

## Scoreboard
Never invent percentages. Compare Synapse with Google Translate, DeepL, and Microsoft Translator when comparable testing is possible. Measure semantic fidelity, critical-information preservation, naturalness, context, tone/register, locale fit, slang/idioms, terminology, consistency, omission/addition rates, correction rate, confidence calibration, p50/p95 latency, cache hit rate, UI coverage, and untranslated leakage.

Keep development completeness, benchmark coverage, translation quality, competitive win/tie/loss, personalization lift, and speed as separate numbers.

## Development order
1. Language-pack contract + es-MX.
2. Private Nayelley profile + correction loop.
3. Blinded benchmark/competitor harness.
4. Additional locales selected by demand using the same contract.
5. Speed: deterministic formatting, translation memory, exact/semantic cache, batching, streaming, model routing.
6. Hard context: conversation history, ambiguity, tone, code-switching, noisy input.
7. Continuous regression evaluation.

## Claim gate
Never claim global superiority over Google Translate. Any superiority claim must identify tested pair/domain, sample count, method, uncertainty, and retained failures.
