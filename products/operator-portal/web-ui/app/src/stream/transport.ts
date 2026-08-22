// Stream transport (SPEC-023 R-2): fetch + body reader with abort support.
// The platform's SSE surfaces are GET /api/v1/chat/stream and POST
// /api/v1/chat/confirm (whose response body IS the resumed stream).
import { authHeaders, buildRequestId, currentGateway } from "../api/client";
import { SseLineDecoder } from "./decoder";
import type { DecodedEvent } from "./models";

export class StreamOpenError extends Error {
  constructor(
    public readonly status: number,
    message?: string,
  ) {
    super(message || `Stream request failed (${status}).`);
    this.name = "StreamOpenError";
  }
}

export type ChunkSource = AsyncIterable<Uint8Array>;

export interface StreamOpenOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
}

export interface OpenedStream {
  requestId: string;
  chunks: ChunkSource;
}

export function chatStreamPath(options: {
  message: string;
  userId: string;
  sessionId?: string | null;
  // SPEC-023 R-4: modality rides as metadata only (voice turns are
  // transcribed text before send; the backend records it for audit).
  inputModality?: "text" | "voice";
}): string {
  const params = new URLSearchParams({
    message: options.message,
    user_id: options.userId,
  });
  if (options.sessionId) {
    params.set("session_id", options.sessionId);
  }
  if (options.inputModality && options.inputModality !== "text") {
    params.set("input_modality", options.inputModality);
  }
  return `/api/v1/chat/stream?${params.toString()}`;
}

async function* readableToChunks(
  body: ReadableStream<Uint8Array> | ChunkSource,
): AsyncGenerator<Uint8Array> {
  const stream = body as ReadableStream<Uint8Array>;
  if (typeof stream.getReader === "function") {
    const reader = stream.getReader();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return;
        yield value;
      }
    } finally {
      reader.releaseLock();
    }
  } else {
    yield* body as ChunkSource;
  }
}

// Open an SSE stream. Throws StreamOpenError on any non-OK response or a
// missing body; callers map status 401 to the sign-in prompt (legacy
// parity) and 410 to confirmation expiry on the confirm route.
export async function openStream(
  path: string,
  options: StreamOpenOptions = {},
): Promise<OpenedStream> {
  const requestId = buildRequestId();
  const headers: Record<string, string> = {
    "x-request-id": requestId,
    ...authHeaders(),
  };
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${currentGateway()}${path}`, {
    method: options.method || "GET",
    headers,
    signal: options.signal,
    body,
  });
  if (!response.ok || !response.body) {
    throw new StreamOpenError(response.status);
  }
  return { requestId, chunks: readableToChunks(response.body) };
}

// Drive a chunk source through the SSE decoder. Events are only emitted
// once their "\n\n" separator arrives (legacy parity — a trailing partial
// block is discarded, matching the gateway's frame-per-line contract).
export async function consumeStream(
  chunks: ChunkSource,
  onEvent: (event: DecodedEvent) => void,
): Promise<void> {
  const decoder = new SseLineDecoder();
  const text = new TextDecoder();
  for await (const chunk of chunks) {
    for (const event of decoder.push(text.decode(chunk, { stream: true }))) {
      onEvent(event);
    }
  }
}
