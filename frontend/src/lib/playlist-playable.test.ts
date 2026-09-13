import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { firstPlayable, lastIndexAtOrBefore, nextPlayable } from "./playlist-playable.ts";

describe("playlist playable", () => {
  it("skips a hole in the middle", () => {
    const items = [
      { id: 1, playable: true },
      { id: 2, playable: false },
      { id: 3, playable: true },
    ];
    assert.equal(nextPlayable(items, 1)?.id, 3);
  });

  it("returns undefined at the last playable", () => {
    const items = [
      { id: 1, playable: true },
      { id: 2, playable: false },
    ];
    assert.equal(nextPlayable(items, 1), undefined);
  });

  it("finds the first playable when current is missing", () => {
    const items = [
      { id: 1, playable: false },
      { id: 2, playable: true },
    ];
    assert.equal(firstPlayable(items)?.id, 2);
    assert.equal(nextPlayable(items, 99)?.id, 2);
  });

  it("returns undefined when nothing is playable", () => {
    assert.equal(firstPlayable([{ id: 1, playable: false }]), undefined);
  });

  it("finds the last chapter at or before a time", () => {
    const items = [{ start: 0 }, { start: 10 }, { start: 20 }];
    assert.equal(lastIndexAtOrBefore(items, 10), 1);
    assert.equal(lastIndexAtOrBefore(items, 9), 0);
  });
});
