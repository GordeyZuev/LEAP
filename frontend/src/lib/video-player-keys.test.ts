import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { handlePlayerKey, type PlayerKeysTarget } from "../components/ui/video-player-keys.ts";

function player(): PlayerKeysTarget & { plays: number } {
  const p = {
    plays: 0,
    togglePlay() { p.plays += 1; },
    rewind() {},
    forward() {},
    increaseVolume() {},
    decreaseVolume() {},
    muted: false,
    volume: 1,
    speed: 1,
    currentTime: 0,
    duration: 100,
    fullscreen: { toggle() {} },
    toggleCaptions() {},
  };
  return p;
}

function key(key: string, target: { closest: (sel: string) => unknown }) {
  return {
    key,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    isComposing: false,
    target,
    preventDefault() {},
  } as unknown as KeyboardEvent;
}

describe("player keys", () => {
  it("does not steal Space from a button", () => {
    const p = player();
    const event = key(" ", { closest: (sel) => (sel.includes("button") ? {} : null) });
    handlePlayerKey(event, p, { isOpen: () => false, toggle() {}, close() {} });
    assert.equal(p.plays, 0);
  });

  it("plays on Space when the target is not a control", () => {
    const p = player();
    const event = key(" ", { closest: () => null });
    handlePlayerKey(event, p, { isOpen: () => false, toggle() {}, close() {} });
    assert.equal(p.plays, 1);
  });

  it("does not steal Space from a text field", () => {
    const p = player();
    const event = key(" ", { closest: (sel) => (sel.includes("textarea") ? {} : null) });
    handlePlayerKey(event, p, { isOpen: () => false, toggle() {}, close() {} });
    assert.equal(p.plays, 0);
  });
});
