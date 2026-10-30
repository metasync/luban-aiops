import { afterEach, expect, it, vi } from "vitest";
import { completeLoginFromCallback, logout } from "./oidc";
import { loadAuthSession, saveAuthSession } from "./storage";
import { resetAuthorizationBrowser } from "../api/authorizations";

vi.mock("../api/authorizations", () => ({ resetAuthorizationBrowser: vi.fn(async () => {}) }));
vi.mock("../api/client", () => ({ currentGateway: () => "https://portal.test", requestJson: vi.fn(async () => { throw new Error("offline"); }) }));
afterEach(() => { sessionStorage.clear(); history.replaceState({}, "", "/"); vi.clearAllMocks(); });

it("resets browser transactions before discarding the authenticated bearer", async () => {
  saveAuthSession({ access_token: "human-fixture" });
  vi.mocked(resetAuthorizationBrowser).mockImplementationOnce(async () => {
    expect(loadAuthSession()?.access_token).toBe("human-fixture");
  });
  await logout();
  expect(resetAuthorizationBrowser).toHaveBeenCalledOnce();
  expect(loadAuthSession()).toBeNull();
});

it("never interprets the target return as the portal OIDC callback", async () => {
  history.replaceState({}, "", "/authorizations/return/11111111-1111-4111-8111-111111111111?error=private-canary");
  saveAuthSession({ access_token: "human-fixture" });
  await expect(completeLoginFromCallback()).resolves.toBeNull();
  expect(loadAuthSession()?.access_token).toBe("human-fixture");
});
