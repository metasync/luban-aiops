// Transport tests (SPEC-023 R-2): URL construction, byte-level consumption,
// and the open-failure mapping.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  StreamOpenError,
  chatStreamPath,
  consumeStream,
  openStream,
} from "../transport";

const encoder = new TextEncoder();

function chunksOf(...parts: string[]): AsyncGenerator<Uint8Array> {
  return (async function* () {
    for (const part of parts) {
      yield encoder.encode(part);
    }
  })();
}

describe("chatStreamPath", () => {
  it("carries message and user_id", () => {
    const path = chatStreamPath({ message: "hello world", userId: "amy" });
    expect(path).toBe(
      "/api/v1/chat/stream?message=hello+world&user_id=amy",
    );
  });

  it("adds session_id when present and omits the text default modality", () => {
    const path = chatStreamPath({
      message: "hi",
      userId: "amy",
      sessionId: "s-1",
      inputModality: "text",
    });
    expect(path).toContain("session_id=s-1");
    expect(path).not.toContain("input_modality");
  });

  it("rides voice modality as a query parameter (audit metadata only)", () => {
    const path = chatStreamPath({
      message: "hi",
      userId: "amy",
      inputModality: "voice",
    });
    expect(path).toContain("input_modality=voice");
  });
});

describe("consumeStream", () => {
  it("decodes frames split across arbitrary chunk boundaries", async () => {
    const stream =
      'data: {"type":"message_delta","delta":"he","session_id":"s-1"}\n\n' +
      'data: {"type":"message_delta","delta":"llo"}\n\n' +
      'data: {"type":"message_end"}\n\n';
    const split = Math.floor(stream.length / 2);
    const events: unknown[] = [];
    await consumeStream(
      chunksOf(stream.slice(0, split), stream.slice(split)),
      (event) => events.push(event.frame),
    );
    expect(events).toEqual([
      { kind: "delta", text: "he" },
      { kind: "delta", text: "llo" },
      { kind: "terminal" },
    ]);
  });
});

describe("openStream", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws StreamOpenError with the response status on failure", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({ ok: false, status: 401, body: null }),
    );
    await expect(openStream("/api/v1/chat/stream")).rejects.toMatchObject({
      name: "StreamOpenError",
      status: 401,
    });
  });

  it("throws when the response has no body", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({ ok: true, status: 200, body: null }),
    );
    await expect(openStream("/api/v1/chat/stream")).rejects.toBeInstanceOf(
      StreamOpenError,
    );
  });

  it("sends x-request-id and JSON body for POST streams", async () => {
    let capturedUrl: string | undefined;
    let capturedInit: RequestInit | undefined;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      capturedUrl = url;
      capturedInit = init;
      return Promise.resolve({ ok: true, status: 200, body: chunksOf() });
    });
    await openStream("/api/v1/chat/confirm", {
      method: "POST",
      body: { session_id: "s-1", confirm_id: "cf-1", decision: "approve" },
    });
    expect(String(capturedUrl)).toContain("/api/v1/chat/confirm");
    const headers = capturedInit?.headers as Record<string, string>;
    expect(headers["x-request-id"]).toMatch(/^req-/);
    expect(headers["content-type"]).toBe("application/json");
    expect(JSON.parse(String(capturedInit?.body))).toEqual({
      session_id: "s-1",
      confirm_id: "cf-1",
      decision: "approve",
    });
  });
});
