import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { authorizationStatus, resetAuthorizationBrowser, startAuthorization } from "../authorizations";
import { saveAuthSession } from "../../auth/storage";

const id = "11111111-1111-4111-8111-111111111111";
const fetchMock = vi.fn();
beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

it("never sends a request without human authentication", async () => {
  await expect(authorizationStatus(id)).rejects.toThrow("Sign in");
  await resetAuthorizationBrowser();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("uses same-origin, noncaching, nonredirecting cookie-bound transport", async () => {
  saveAuthSession({ access_token: "human-fixture" });
  localStorage.setItem("luban.portal.gatewayUrl", "https://untrusted.test");
  fetchMock.mockResolvedValue(new Response(JSON.stringify({
    challenge_id: id, status: "pending", session_id: "ses-1", target: "Automation",
    updated_at: "2030-01-01T00:00:00Z", expires_at: "2030-01-01T00:10:00Z",
  })));
  expect((await authorizationStatus(id)).status).toBe("pending");
  expect(fetchMock).toHaveBeenCalledWith(`/api/v1/targets/authorizations/${id}`, expect.objectContaining({
    cache: "no-store", redirect: "error", credentials: "same-origin", referrerPolicy: "no-referrer",
    headers: expect.objectContaining({ authorization: "Bearer human-fixture" }),
  }));
});

it("rejects provider URLs and echoed backend details without exposing them", async () => {
  saveAuthSession({ access_token: "human-fixture" });
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
    start_url: "https://oauth.test?state=secret-canary", expires_at: "2030-01-01T00:00:00Z",
  })));
  await expect(startAuthorization(id)).rejects.toThrow(/^Target authorization unavailable\.$/);
  fetchMock.mockResolvedValueOnce(new Response("secret-canary", { status: 502 }));
  await expect(authorizationStatus(id)).rejects.toThrow(/^Target authorization unavailable\.$/);
});

it("handles reset 204 without JSON and never sends a caller-owned body", async () => {
  saveAuthSession({ access_token: "human-fixture" });
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
  await resetAuthorizationBrowser();
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/targets/authorizations/browser-reset", expect.objectContaining({
    method: "POST", body: undefined,
  }));
});

it.each(["../callback?code=canary", id + "\n", id + "\r\n"])("invalid opaque identifier %j fails before fetch", async (value) => {
  saveAuthSession({ access_token: "human-fixture" });
  await expect(authorizationStatus(value)).rejects.toThrow();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("rejects a non-string status even when it coerces to an allowed value", async () => {
  saveAuthSession({ access_token: "human-fixture" });
  fetchMock.mockResolvedValue(new Response(JSON.stringify({
    challenge_id: id, status: ["authorized"], session_id: "ses-1", target: "Automation",
    updated_at: "2030-01-01T00:00:00Z", expires_at: "2030-01-01T00:10:00Z",
  })));
  await expect(authorizationStatus(id)).rejects.toThrow(/^Target authorization unavailable\.$/);
});

it("rejects a start path containing a trailing newline", async () => {
  saveAuthSession({ access_token: "human-fixture" });
  fetchMock.mockResolvedValue(new Response(JSON.stringify({
    start_url: `/api/v1/targets/authorizations/start/${id}\n`, expires_at: "2030-01-01T00:00:00Z",
  })));
  await expect(startAuthorization(id)).rejects.toThrow(/^Target authorization unavailable\.$/);
});
