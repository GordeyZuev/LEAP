import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  parseChannelPlaylistSort,
  parseChannelVideoSort,
  sortChannelPlaylists,
  sortChannelVideos,
} from "./channel-catalog.ts";

const videos = [
  { title: "2026-01-02 Intro", duration: 10, start_time: "2026-01-02T10:00:00Z" },
  { title: "Middle lecture", duration: 30, start_time: "2026-01-01T10:00:00Z" },
  { title: "Zeta wrap", duration: 20, start_time: "2026-01-03T10:00:00Z" },
];

const playlists = [
  { name: "Zeta", video_count: 2, duration_sum: 40 },
  { name: "Alpha", video_count: 8, duration_sum: 10 },
  { name: "Mu", video_count: 3, duration_sum: 90 },
];

describe("channel catalog", () => {
  it("defaults unknown sort to channel order", () => {
    assert.equal(parseChannelVideoSort(null), "order");
    assert.equal(parseChannelVideoSort("bogus"), "order");
    assert.equal(parseChannelPlaylistSort("videos"), "videos");
  });

  it("sorts videos by date, stripped name, and duration", () => {
    assert.deepEqual(
      sortChannelVideos(videos, "newest").map((v) => v.start_time),
      ["2026-01-03T10:00:00Z", "2026-01-02T10:00:00Z", "2026-01-01T10:00:00Z"],
    );
    assert.deepEqual(
      sortChannelVideos(videos, "name").map((v) => v.title),
      ["2026-01-02 Intro", "Middle lecture", "Zeta wrap"],
    );
    assert.deepEqual(
      sortChannelVideos(videos, "duration").map((v) => v.duration),
      [30, 20, 10],
    );
  });

  it("sorts playlists by name, video count, and duration", () => {
    assert.deepEqual(
      sortChannelPlaylists(playlists, "name").map((p) => p.name),
      ["Alpha", "Mu", "Zeta"],
    );
    assert.deepEqual(
      sortChannelPlaylists(playlists, "videos").map((p) => p.video_count),
      [8, 3, 2],
    );
    assert.deepEqual(
      sortChannelPlaylists(playlists, "duration").map((p) => p.duration_sum),
      [90, 40, 10],
    );
  });
});
