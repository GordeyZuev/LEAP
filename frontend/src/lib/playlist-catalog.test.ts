import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  catalogPlaylistItems,
  parsePlaylistVideoSort,
  playlistItemMatchesQuery,
} from "./playlist-catalog.ts";

const items = [
  { title: "2026-01-02 Intro", duration: 10, start_time: "2026-01-02T10:00:00Z" },
  { title: "Middle lecture", duration: 30, start_time: "2026-01-01T10:00:00Z" },
  { title: "Zeta wrap", duration: 20, start_time: "2026-01-03T10:00:00Z" },
];

describe("playlist catalog", () => {
  it("defaults unknown sort to playlist order", () => {
    assert.equal(parsePlaylistVideoSort(null), "order");
    assert.equal(parsePlaylistVideoSort("bogus"), "order");
    assert.equal(parsePlaylistVideoSort("newest"), "newest");
  });

  it("keeps playlist order as the default sort", () => {
    const out = catalogPlaylistItems(items, "", "order");
    assert.deepEqual(
      out.map((i) => i.title),
      items.map((i) => i.title),
    );
  });

  it("sorts newest and oldest by start_time", () => {
    assert.deepEqual(
      catalogPlaylistItems(items, "", "newest").map((i) => i.start_time),
      ["2026-01-03T10:00:00Z", "2026-01-02T10:00:00Z", "2026-01-01T10:00:00Z"],
    );
    assert.deepEqual(
      catalogPlaylistItems(items, "", "oldest").map((i) => i.start_time),
      ["2026-01-01T10:00:00Z", "2026-01-02T10:00:00Z", "2026-01-03T10:00:00Z"],
    );
  });

  it("sorts by stripped name and duration", () => {
    assert.deepEqual(
      catalogPlaylistItems(items, "", "name").map((i) => i.title),
      ["2026-01-02 Intro", "Middle lecture", "Zeta wrap"],
    );
    assert.deepEqual(
      catalogPlaylistItems(items, "", "duration").map((i) => i.duration),
      [30, 20, 10],
    );
  });

  it("filters by title, ignoring a leading timestamp", () => {
    assert.equal(playlistItemMatchesQuery("2026-01-02 Intro", "intro"), true);
    assert.deepEqual(
      catalogPlaylistItems(items, "wrap", "order").map((i) => i.title),
      ["Zeta wrap"],
    );
  });
});
