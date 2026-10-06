import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { cssLengthToPx, scrollThumbGeometry } from "./scroll-thumb.ts";

describe("scroll thumb inset", () => {
  it("stays clear of the corner at both ends", () => {
    const inset = 28;
    const view = 400;
    const total = 1200;
    const atTop = scrollThumbGeometry(0, total, view, inset);
    const atEnd = scrollThumbGeometry(total - view, total, view, inset);
    assert.ok(atTop);
    assert.ok(atEnd);
    assert.equal(atTop.top, inset);
    assert.ok(atEnd.top + atEnd.height <= view - inset + 0.01);
  });

  it("clears only the corner the scroller actually touches", () => {
    const view = 400;
    const total = 900;
    const atTop = scrollThumbGeometry(0, total, view, 0, 28);
    const atEnd = scrollThumbGeometry(total - view, total, view, 0, 28);
    assert.ok(atTop);
    assert.ok(atEnd);
    assert.equal(atTop.top, 0);
    assert.ok(atEnd.top + atEnd.height <= view - 28 + 0.01);
  });

  it("draws nothing when the content fits", () => {
    assert.equal(scrollThumbGeometry(0, 200, 400, 28), null);
  });

  it("converts rem using the root font size", () => {
    assert.equal(cssLengthToPx("1.75rem", 16), 28);
    assert.equal(cssLengthToPx("28px", 16), 28);
  });
});
