import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { firstCredentialForPlatform } from "./preset-credentials.ts";

describe("firstCredentialForPlatform", () => {
  it("returns the first selected credential for the requested platform", () => {
    assert.equal(
      firstCredentialForPlatform([3, 1, 2], {
        1: { platform: "youtube", credential_id: 41 },
        2: { platform: "yandex_disk", credential_id: 52 },
        3: { platform: "youtube", credential_id: 43 },
      }, "youtube"),
      43,
    );
  });

  it("skips presets without credentials and returns null if none match", () => {
    assert.equal(
      firstCredentialForPlatform([1, 2], {
        1: { platform: "youtube" },
        2: { platform: "yandex_disk", credential_id: 52 },
      }, "youtube"),
      null,
    );
  });
});
