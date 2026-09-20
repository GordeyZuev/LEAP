import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { extractApiError } from "./utils.ts";

function apiError(status: number, data: unknown = {}, headers: Record<string, string> = {}) {
  return { isAxiosError: true, response: { status, data, headers } };
}

describe("extractApiError", () => {
  it("keeps a specific API sentence, including quota and auth lockouts", () => {
    assert.equal(
      extractApiError(apiError(429, { detail: "Monthly recordings quota exceeded: 10/month" }), "Failed"),
      "Monthly recordings quota exceeded: 10/month",
    );
    assert.equal(
      extractApiError(apiError(429, { detail: "Too many authentication attempts. Try again in a minute." })),
      "Too many authentication attempts. Try again in a minute.",
    );
  });

  it("turns a generic rate limit into a wait time from the body or header", () => {
    assert.equal(
      extractApiError(apiError(429, { detail: "Rate limit exceeded", retry_after: 60 })),
      "Too many requests. Try again in a minute.",
    );
    assert.equal(
      extractApiError(apiError(429, { detail: "Rate limit exceeded" }, { "retry-after": "3600" })),
      "Too many requests. Try again in an hour.",
    );
    assert.equal(extractApiError(apiError(429, {})), "Too many requests. Wait a moment and try again.");
    assert.equal(
      extractApiError({
        isAxiosError: true,
        response: { status: 429, data: { detail: "Rate limit exceeded" }, headers: { get: (name: string) => (name === "retry-after" ? "120" : undefined) } },
      }),
      "Too many requests. Try again in 2 minutes.",
    );
  });

  it("reads FastAPI validation messages", () => {
    assert.equal(
      extractApiError(apiError(422, { detail: [{ msg: "Field required" }] }), "Save failed"),
      "Field required",
    );
  });

  it("explains transport and server failures when the API gave no sentence", () => {
    assert.equal(
      extractApiError({ isAxiosError: true, code: "ERR_NETWORK" }, "Failed to load"),
      "Could not reach the server. Check your connection and try again.",
    );
    assert.equal(
      extractApiError({ isAxiosError: true, code: "ECONNABORTED" }),
      "The request timed out. Try again.",
    );
    assert.equal(
      extractApiError(apiError(500, { detail: "Internal Server Error" }), "Failed to load"),
      "The server had a problem. Try again in a moment.",
    );
    assert.equal(extractApiError(apiError(413, {})), "This file is larger than the upload limit.");
  });

  it("uses the caller fallback when the failure is neither specific nor a known status", () => {
    assert.equal(extractApiError(new Error("boom"), "Failed to load recordings"), "Failed to load recordings");
    assert.equal(extractApiError(apiError(400, {}), "Failed to load recordings"), "Failed to load recordings");
    assert.equal(
      extractApiError({ isAxiosError: true, code: "ERR_CANCELED" }, "Failed to load recordings"),
      "Failed to load recordings",
    );
  });
});
