// Session API client tests for the SPEC-055 R-4 surface: the birth-target
// declaration rides the session create body, the graduation and mid-session
// declaration hit their own paths, and a refusal carries the server's own
// explanation through to the caller — which is what makes a blast-radius
// refusal actionable instead of a bare status code.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../client";
import {
  createSession,
  declareSkillTarget,
  graduateSessionSkill,
  listSessions,
} from "../sessions";

interface FetchCall {
  url: string;
  init: RequestInit;
}

// Captures every request so a body can be asserted on rather than inferred.
function stubFetch(payload: unknown, calls: FetchCall[], ok = true, status = 200) {
  vi.stubGlobal(
    "fetch",
    (url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      return Promise.resolve({
        ok,
        status,
        statusText: ok ? "OK" : "Error",
        json: () => Promise.resolve(payload),
      });
    },
  );
}

// The client prefixes every path with the resolved gateway origin, which under
// jsdom is the test page's own; the assertions care about the path.
function pathOf(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createSession (SPEC-055 R-4 birth declaration)", () => {
  it("sends an empty body when neither an id nor a target is given", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ session_id: "ses-1" }, calls);
    await createSession();
    expect(pathOf(calls[0].url)).toBe("/api/v1/sessions");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({});
  });

  it("declares the target at birth alongside the session", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ session_id: "ses-dev-1" }, calls);
    await createSession(undefined, "https://admin.internal/login");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      skill_target: "https://admin.internal/login",
    });
  });

  it("keeps a named session and its target in one body", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ session_id: "incident-1" }, calls);
    await createSession("incident-1", "https://admin.internal/login");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      session_id: "incident-1",
      skill_target: "https://admin.internal/login",
    });
  });

  it("carries the agent's 422 explanation, so the dialog can say what to fix", async () => {
    const calls: FetchCall[] = [];
    stubFetch(
      {
        detail:
          "skill target must be an absolute http(s) URL — a target with no " +
          "origin can never be corroborated against the session's captured steps",
      },
      calls,
      false,
      422,
    );
    const error = await createSession(undefined, "admin.internal").catch(
      (caught: unknown) => caught,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).detail).toContain("absolute http(s) URL");
  });

  it("leaves the detail absent rather than throwing on a non-JSON error body", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        json: () => Promise.reject(new SyntaxError("Unexpected token <")),
      }),
    );
    const error = await graduateSessionSkill("ses-1").catch(
      (caught: unknown) => caught,
    );
    // A proxy's HTML 502 must still reach the caller as the status it was,
    // not as a parse failure that hides it.
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).detail).toBeUndefined();
  });
});

describe("graduateSessionSkill (SPEC-055 R-4)", () => {
  it("posts to the graduation path with no body", async () => {
    const calls: FetchCall[] = [];
    stubFetch(
      {
        markdown: "---\nkind: executable_flow\n---\n",
        mode: "graduated",
        validation: "passed",
        suggested_filename: "reset-a-password.md",
        step_count: 3,
        web_target: "https://admin.internal/login",
        declaration: "preceded",
      },
      calls,
    );
    const result = await graduateSessionSkill("ses dev/1");
    // The id is encoded, so a session id with a separator cannot reshape the
    // path into another endpoint.
    expect(pathOf(calls[0].url)).toBe(
      "/api/v1/sessions/ses%20dev%2F1/skill-graduate",
    );
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].init.body).toBeUndefined();
    expect(result.declaration).toBe("preceded");
    expect(result.step_count).toBe(3);
  });

  it("surfaces the blast-radius refusal's own words on a 409", async () => {
    stubFetch(
      {
        detail:
          "this session cannot be graduated: step(s) 2 landed outside the " +
          "declared target's origin: 2 (web.click on https://other.internal/x)",
      },
      [],
      false,
      409,
    );
    const error = await graduateSessionSkill("ses-1").catch(
      (caught: unknown) => caught,
    );
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).detail).toContain("landed outside");
  });
});

describe("declareSkillTarget (SPEC-055 R-4 mid-session path)", () => {
  it("posts the target and reports the scope in force", async () => {
    const calls: FetchCall[] = [];
    stubFetch(
      {
        session_id: "ses-1",
        target: "https://admin.internal/login",
        already_declared: false,
      },
      calls,
    );
    const result = await declareSkillTarget(
      "ses-1",
      "https://admin.internal/login?token=abc",
    );
    expect(pathOf(calls[0].url)).toBe("/api/v1/sessions/ses-1/skill-target");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      target: "https://admin.internal/login?token=abc",
    });
    // The agent scopes it and answers with the effective value, never an echo.
    expect(result.target).toBe("https://admin.internal/login");
    expect(result.already_declared).toBe(false);
  });
});

describe("createSession session_type (SPEC-056 R-1 birth discriminator)", () => {
  it("sends session_type=development for a Studio-born session", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ session_id: "ses-dev-1", session_type: "development" }, calls);
    await createSession(undefined, undefined, "development");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      session_type: "development",
    });
  });

  it("sends session_type=operation for a Chat-born session", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ session_id: "ses-op-1", session_type: "operation" }, calls);
    await createSession(undefined, undefined, "operation");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      session_type: "operation",
    });
  });

  it("carries the type alongside a named id and a birth target", async () => {
    // Decoupled from skill_target: a development session may name a target,
    // but the two fields ride independently and neither implies the other.
    const calls: FetchCall[] = [];
    stubFetch({ session_id: "ses-dev-2", session_type: "development" }, calls);
    await createSession(
      "ses-dev-2",
      "https://admin.internal/login",
      "development",
    );
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      session_id: "ses-dev-2",
      skill_target: "https://admin.internal/login",
      session_type: "development",
    });
  });

  it("omits session_type when the caller does not name one", async () => {
    // Backward compatible: the historical one-click shape stays an empty
    // body, defaulting to operation server-side.
    const calls: FetchCall[] = [];
    stubFetch({ session_id: "ses-1", session_type: "operation" }, calls);
    await createSession();
    expect(JSON.parse(String(calls[0].init.body))).toEqual({});
  });
});

describe("listSessions session_type scope (SPEC-056 R-2 / R-4)", () => {
  it("omits the query param when no scope is given (legacy: all sessions)", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ sessions: [] }, calls);
    await listSessions();
    expect(pathOf(calls[0].url)).toBe("/api/v1/sessions");
  });

  it("scopes to ?session_type=operation for the Chat/picker list", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ sessions: [] }, calls);
    await listSessions(undefined, "operation");
    expect(pathOf(calls[0].url)).toBe("/api/v1/sessions?session_type=operation");
  });

  it("scopes to ?session_type=development for the Studio list", async () => {
    const calls: FetchCall[] = [];
    stubFetch({ sessions: [] }, calls);
    await listSessions(undefined, "development");
    expect(pathOf(calls[0].url)).toBe(
      "/api/v1/sessions?session_type=development",
    );
  });

  it("returns the sessions array, defaulting to empty when absent", async () => {
    stubFetch({}, []);
    await expect(listSessions(undefined, "operation")).resolves.toEqual([]);
  });
});
