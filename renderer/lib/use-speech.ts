// Browser speech-to-text via the Web Speech API (ADR-0015, Phase V).
//
// Works in real Chrome + on the phone (mobile Chrome/Safari), which is exactly
// where remote voice control matters. It is NOT reliable inside packaged
// Electron (Chromium ships without the Google speech backend), so this hook
// feature-detects and the UI hides the mic when unsupported -- no broken button.

import { useCallback, useEffect, useRef, useState } from 'react';

// The Web Speech API isn't in the stock TS DOM lib; describe just what we use.
interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  0: SpeechRecognitionAlternativeLike;
  isFinal: boolean;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export interface SpeechDictation {
  /** True only when the browser exposes the Web Speech API. */
  supported: boolean;
  listening: boolean;
  /** In-progress (not yet finalized) transcript, for a live hint. */
  interim: string;
  error: string | null;
  start: () => void;
  stop: () => void;
  toggle: () => void;
}

/**
 * Dictation hook. ``onText`` is called with each *finalized* phrase so the
 * caller can append it (e.g. to a command draft). Interim text is exposed
 * separately for a live "listening…" hint and never duplicated into onText.
 */
export function useSpeechDictation(onText: (text: string) => void): SpeechDictation {
  const [supported] = useState<boolean>(() => getCtor() !== null);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);
  const recogRef = useRef<SpeechRecognitionLike | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const stop = useCallback(() => {
    recogRef.current?.stop();
  }, []);

  const start = useCallback(() => {
    const Ctor = getCtor();
    if (!Ctor || recogRef.current) return;
    const recog = new Ctor();
    recog.lang = 'en-US';
    recog.continuous = true;
    recog.interimResults = true;
    recog.onresult = (event) => {
      let pending = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? '';
        if (result.isFinal) {
          const clean = text.trim();
          if (clean) onTextRef.current(clean);
        } else {
          pending += text;
        }
      }
      setInterim(pending);
    };
    recog.onerror = (event) => {
      // "no-speech"/"aborted" are benign; surface real ones (e.g. not-allowed).
      if (event.error && event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(event.error === 'not-allowed' ? 'Microphone permission denied.' : event.error);
      }
    };
    recog.onend = () => {
      setListening(false);
      setInterim('');
      recogRef.current = null;
    };
    recogRef.current = recog;
    setError(null);
    setInterim('');
    try {
      recog.start();
      setListening(true);
    } catch {
      recogRef.current = null;
    }
  }, []);

  const toggle = useCallback(() => {
    if (listening) stop();
    else start();
  }, [listening, start, stop]);

  useEffect(() => () => recogRef.current?.abort(), []);

  return { supported, listening, interim, error, start, stop, toggle };
}
