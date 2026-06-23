# ADR-0015: Voice — browser dictation now, local Whisper later

- Status: Accepted (Phase V1 shipping: dictation → command pad + assistant)
- Date: 2026-06-23
- Deciders: Justin (owner), Claude

## Context

The owner wants to drive Synapse by voice from the phone: "voice → command pad
working very well, using the best recognition," and "a voice assistant in the
app where you can ask what the boss is doing." Remote control from a phone is the
headline use case.

The decision recorded in the roadmap: **browser Web Speech API now, local Whisper
later** (Whisper shipped as a downloadable "private mode" model in the Phase M
marketplace).

## Decision

### Engine: the Web Speech API (`SpeechRecognition`)
Zero-install, high-quality recognition that works **in real Chrome and on the
phone** (mobile Chrome/Safari) — exactly where remote voice control happens. It
is *not* reliable inside packaged Electron (Chromium ships without the Google
speech backend), so the integration **feature-detects and hides the mic when
unsupported** — never a broken button. This is honest about where it works: the
phone/web, which is the point.

### `useSpeechDictation` hook (`renderer/lib/use-speech.ts`)
One reusable hook owns it: feature-detect (`SpeechRecognition` ||
`webkitSpeechRecognition`), start/stop/toggle, `continuous` + `interimResults`,
and a callback fired with each **finalized** phrase plus a separate `interim`
string for a live hint. Benign errors (`no-speech`, `aborted`) are swallowed;
`not-allowed` surfaces as a clear "microphone permission denied."

### V1 surfaces (input dictation)
- **Command pad** (`SessionTerminal.tsx`): a mic toggle that appends spoken
  phrases to the command draft, then the existing Send line/text path runs them
  into the live terminal. A "🎙 listening…" hint shows interim text.
- **Assistant composer** (`Assistant.tsx`): the same mic dictates a message to
  the local LLM — voice in for the in-app assistant.

### Later (own increments)
- **V2 — voice assistant out + confirmation cards:** the global "Ask Synapse"
  quick-ask speaks answers (Speech Synthesis) and, for *action* requests
  ("restart the scraper", "ask Codex to fix the crash"), shows a **confirmation
  card** before calling the REST endpoint — never auto-running a dangerous action
  from a misheard phrase.
- **Local Whisper** ("private mode"): a marketplace model for offline
  recognition, swapped in behind the same hook interface.

## Consequences
- Voice input works today where it matters (phone/web) with no install, and
  degrades invisibly where it doesn't (Electron).
- A single hook means new voice surfaces are a few lines each.
- Action-by-voice is deferred behind confirmation cards — safety before
  convenience.

## Alternatives considered
- *Bundle Whisper now* — heavier; not needed for input dictation, and the Web
  Speech API is better on the phone today. Whisper becomes the offline upgrade.
- *Server-side STT in the daemon* — adds a model dependency + audio plumbing for
  no gain over the browser's built-in recognizer for V1.
