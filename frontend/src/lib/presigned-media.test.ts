import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { presignedRefreshDelayMs, presignedRetryDelayMs } from "../hooks/use-presigned-media.ts";

describe("presigned media refresh", () => {
  it("refreshes a one-hour URL two minutes before expiry", () => {
    assert.equal(presignedRefreshDelayMs(3600), 58 * 60 * 1000);
  });

  it("also refreshes short-lived URLs before they expire", () => {
    assert.equal(presignedRefreshDelayMs(120), 60_000);
    assert.equal(presignedRefreshDelayMs(60), 30_000);
    assert.equal(presignedRefreshDelayMs(30), 15_000);
    assert.equal(presignedRefreshDelayMs(5), 2_500);
    assert.equal(presignedRefreshDelayMs(60, 40_000), 0);
  });

  it("retries before short-lived URLs expire and caps long-lived retries at a minute", () => {
    assert.equal(presignedRetryDelayMs(30, 15_000), 7_500);
    assert.equal(presignedRetryDelayMs(3600, 58 * 60 * 1000), 60_000);
    assert.equal(presignedRetryDelayMs(30, 31_000), 1_000);
  });
});
