import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { nextPublicTheme } from "./theme.ts";

describe("nextPublicTheme", () => {
  it("leaves an automatic page for the opposite of the OS", () => {
    assert.equal(nextPublicTheme("system", true), "light");
    assert.equal(nextPublicTheme("system", false), "dark");
  });

  it("returns to system when the switch lands on the OS appearance", () => {
    assert.equal(nextPublicTheme("light", true), "system");
    assert.equal(nextPublicTheme("dark", false), "system");
  });

  it("switches a pinned mode that already matches the OS to the other appearance", () => {
    assert.equal(nextPublicTheme("dark", true), "light");
    assert.equal(nextPublicTheme("light", false), "dark");
  });
});
