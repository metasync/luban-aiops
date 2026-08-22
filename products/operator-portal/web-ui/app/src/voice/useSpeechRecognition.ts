// Web Speech API wrapper (SPEC-023 R-4): browser-side speech-to-text only.
// No audio is captured, stored, or transmitted — the recognizer yields
// transcript text that the composer appends to the draft like typing.
import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionErrorEventLike {
  error: string;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const candidate = (window as unknown as Record<string, unknown>)
    .SpeechRecognition ??
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  return typeof candidate === "function"
    ? (candidate as SpeechRecognitionCtor)
    : null;
}

const ERROR_MESSAGES: Record<string, string> = {
  "not-allowed":
    "Microphone access was denied. Allow microphone permission to use voice input.",
  "service-not-allowed":
    "Speech recognition is not allowed in this browser context.",
  "no-speech": "No speech was detected. Try again.",
  "audio-capture": "No microphone was found. Check your audio device.",
  network: "Speech recognition failed due to a network error.",
};

export interface SpeechRecognitionApi {
  supported: boolean;
  listening: boolean;
  error: string | null;
  // Starts a recognition pass; each final transcript chunk is delivered to
  // `onText` as it arrives. The recognizer `lang` is the operator's
  // explicit selection (never sent to the backend).
  start: (language: string, onText: (text: string) => void) => void;
  stop: () => void;
}

export function useSpeechRecognition(): SpeechRecognitionApi {
  const [supported] = useState(() => Boolean(getSpeechRecognitionCtor()));
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setListening(false);
  }, []);

  const start = useCallback(
    (language: string, onText: (text: string) => void) => {
      const Ctor = getSpeechRecognitionCtor();
      if (!Ctor) return;
      recognitionRef.current?.abort();

      const recognition = new Ctor();
      recognition.lang = language;
      recognition.interimResults = false;
      recognition.continuous = false;
      recognition.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i];
          if (result.isFinal) {
            const text = result[0]?.transcript?.trim();
            if (text) onText(text);
          }
        }
      };
      recognition.onerror = (event) => {
        // "aborted" fires when we intentionally switch sessions/turns.
        if (event.error !== "aborted") {
          setError(
            ERROR_MESSAGES[event.error] ??
              "Speech recognition failed. Try again.",
          );
        }
        setListening(false);
      };
      recognition.onend = () => {
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null;
        }
        setListening(false);
      };

      recognitionRef.current = recognition;
      setError(null);
      setListening(true);
      recognition.start();
    },
    [],
  );

  // Abort any in-flight pass on unmount.
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  return { supported, listening, error, start, stop };
}
