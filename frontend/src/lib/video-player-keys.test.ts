import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  handlePlayerKey,
  playbackFocusControl,
  playbackRangeControl,
  playerRangeFocused,
  type PlayerKeysTarget,
} from "../components/ui/video-player-keys.ts";

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

  it("pauses on Space while a seek or volume slider is focused", () => {
    const p = player();
    const event = key(" ", {
      closest: (sel) => (sel.includes("plyr") || sel.includes("range") ? {} : null),
    });
    handlePlayerKey(event, p, { isOpen: () => false, toggle() {}, close() {} });
    assert.equal(p.plays, 1);
    assert.equal(playerRangeFocused(event), true);
  });

  it("does not steal Space from a custom button", () => {
    const p = player();
    const event = key(" ", { closest: (sel) => (sel.includes("[role='button']") ? {} : null) });
    handlePlayerKey(event, p, { isOpen: () => false, toggle() {}, close() {} });
    assert.equal(p.plays, 0);
  });
});

function focusable(kind: "button" | "overlay" | "dialog" | "range" | "plain" | "combobox") {
  return {
    closest(sel: string) {
      if (kind === "overlay" && sel.includes("plyr__leap-overlay")) return this;
      if (kind === "dialog" && sel.includes("dialog")) return this;
      if (kind === "combobox" && sel.includes("combobox")) return this;
      if (kind === "button" && sel.startsWith("button")) return this;
      if (kind === "range" && sel.includes("range")) return this;
      return null;
    },
    blur() {},
  };
}

describe("playback focus", () => {
  it("releases a pointer-focused control", () => {
    const button = focusable("button");
    assert.equal(playbackFocusControl(button), button);
  });

  it("keeps the end card, dialogs, and comboboxes", () => {
    assert.equal(playbackFocusControl(focusable("overlay")), null);
    assert.equal(playbackFocusControl(focusable("dialog")), null);
    assert.equal(playbackFocusControl(focusable("combobox")), null);
  });

  it("releases a seek or volume slider only as a range", () => {
    const range = focusable("range");
    assert.equal(playbackFocusControl(range), null);
    assert.equal(playbackRangeControl(range), range);
    assert.equal(playbackRangeControl(focusable("overlay")), null);
  });

  it("ignores plain targets", () => {
    assert.equal(playbackFocusControl(focusable("plain")), null);
    assert.equal(playbackRangeControl(focusable("plain")), null);
    assert.equal(playbackFocusControl(null), null);
  });
});
