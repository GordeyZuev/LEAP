import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { applyHudAction, HUD_STACK_MS } from "./player-hud.ts";

describe("player HUD", () => {
  it("stacks seeks in the same direction within the window", () => {
    const first = applyHudAction(null, 0, 0, { type: "seek", seconds: 10 });
    const stacked = applyHudAction(first, 0, HUD_STACK_MS - 1, { type: "seek", seconds: 10 });
    assert.deepEqual(stacked, { kind: "seek", dir: 1, seconds: 20 });
  });

  it("resets the stack after the window", () => {
    const first = applyHudAction(null, 0, 0, { type: "seek", seconds: 10 });
    const next = applyHudAction(first, 0, HUD_STACK_MS + 1, { type: "seek", seconds: 10 });
    assert.deepEqual(next, { kind: "seek", dir: 1, seconds: 10 });
  });

  it("resets when the direction changes", () => {
    const first = applyHudAction(null, 0, 0, { type: "seek", seconds: 10 });
    const back = applyHudAction(first, 0, 10, { type: "seek", seconds: -5 });
    assert.deepEqual(back, { kind: "seek", dir: -1, seconds: 5 });
  });
});
