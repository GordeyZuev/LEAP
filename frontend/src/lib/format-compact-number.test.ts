import assert from "node:assert/strict";
import test from "node:test";
import { formatCompactNumber } from "./format-compact-number.ts";

test("keeps zero, small counts and fractional hours exact", () => {
  for (const value of [0, 1, 58.1, 9999]) {
    assert.equal(formatCompactNumber(value), String(value));
  }
});

test("large metrics fit dashboard columns", () => {
  assert.equal(formatCompactNumber(10_000), "10K");
  assert.equal(formatCompactNumber(12_345_678), "12.3M");
  assert.equal(formatCompactNumber(205_761.3), "206K");
});
