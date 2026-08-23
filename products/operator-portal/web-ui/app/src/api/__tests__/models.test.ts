// Model catalog client tests (SPEC-024 R-4): discovery failures surface
// as ApiError so the composer can fail open (selector hidden, chat still
// works), and sparse payloads normalize to the catalog contract.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../client";
import { getModelCatalog } from "../models";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getModelCatalog", () => {
  it("throws ApiError on a non-2xx response (selector hides, chat works)", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: () => Promise.resolve({}),
      }),
    );
    await expect(getModelCatalog()).rejects.toBeInstanceOf(ApiError);
    await expect(getModelCatalog()).rejects.toMatchObject({ status: 500 });
  });

  it("throws when the network call itself fails", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("offline")));
    await expect(getModelCatalog()).rejects.toBeInstanceOf(TypeError);
  });

  it("maps a full catalog payload verbatim", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            models: [
              {
                id: "deepseek-chat",
                label: "DeepSeek Chat",
                provider: "deepseek",
                default: true,
              },
            ],
            default: "deepseek-chat",
          }),
      }),
    );
    const catalog = await getModelCatalog();
    expect(catalog.models).toHaveLength(1);
    expect(catalog.models[0]).toMatchObject({
      id: "deepseek-chat",
      provider: "deepseek",
    });
    expect(catalog.default).toBe("deepseek-chat");
  });

  it("normalizes a sparse payload (missing models/default)", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      }),
    );
    const catalog = await getModelCatalog();
    expect(catalog).toEqual({ models: [], default: null });
  });
});
