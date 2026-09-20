import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mergePosterFieldsInItems, posterRefreshDelayMs } from "./poster-stable.ts";

const refreshAt = Date.UTC(2026, 9, 4, 13, 0, 0);

describe("poster URL stability", () => {
  it("schedules the next refresh from API deadlines", () => {
    assert.equal(posterRefreshDelayMs([], refreshAt - 60_000), false);
    assert.equal(posterRefreshDelayMs([{ poster_refresh_at_ms: refreshAt }], refreshAt - 60_000), 60_000);
    assert.equal(posterRefreshDelayMs([{ poster_refresh_at_ms: refreshAt }], refreshAt), 10_000);
  });

  it("uses the new URL when the API supplies no refresh deadline", () => {
    const [item] = mergePosterFieldsInItems(
      [{ id: 1, poster_asset_key: "users/1/cover.jpg", poster_url: "old" }],
      [{ id: 1, poster_asset_key: "users/1/cover.jpg", poster_url: "new" }],
    );
    assert.equal(item.poster_url, "new");
  });

  it("keeps the old URL and its deadline together on a list refetch", () => {
    const oldNow = Date.now;
    Date.now = () => refreshAt - 1;
    try {
      const [item] = mergePosterFieldsInItems(
        [{ id: 1, poster_asset_key: "users/1/cover.jpg", poster_url: "old", poster_refresh_at_ms: refreshAt }],
        [{ id: 1, poster_asset_key: "users/1/cover.jpg", poster_url: "new", poster_refresh_at_ms: refreshAt + 60_000 }],
      );
      assert.equal(item.poster_url, "old");
      assert.equal(item.poster_refresh_at_ms, refreshAt);
    } finally {
      Date.now = oldNow;
    }
  });

  it("accepts a fresh URL and deadline after the old deadline", () => {
    const oldNow = Date.now;
    Date.now = () => refreshAt;
    try {
      const [item] = mergePosterFieldsInItems(
        [{ id: 1, poster_asset_key: "users/1/cover.jpg", poster_url: "old", poster_refresh_at_ms: refreshAt }],
        [{ id: 1, poster_asset_key: "users/1/cover.jpg", poster_url: "new", poster_refresh_at_ms: refreshAt + 60_000 }],
      );
      assert.equal(item.poster_url, "new");
      assert.equal(item.poster_refresh_at_ms, refreshAt + 60_000);
    } finally {
      Date.now = oldNow;
    }
  });
});
