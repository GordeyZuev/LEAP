import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resumeTimeWithinDuration, retryTimeWithinDuration } from "./video-resume.ts";

describe("video position recovery", () => {
  it("starts a new visit at the beginning when the saved position is near the end", () => {
    assert.equal(resumeTimeWithinDuration(98, 100), null);
  });

  it("keeps the current position when a stream fails near the end", () => {
    assert.equal(retryTimeWithinDuration(98, 100), 98);
    assert.equal(retryTimeWithinDuration(100, 100), 99.75);
  });

  it("rejects invalid positions", () => {
    assert.equal(retryTimeWithinDuration(Number.NaN, 100), null);
    assert.equal(retryTimeWithinDuration(10, Number.POSITIVE_INFINITY), null);
  });
});
