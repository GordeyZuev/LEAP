import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { CATALOG_PAGE_SIZE, paginateItems, parseCatalogPage } from "./catalog-page.ts";

describe("catalog page", () => {
  it("defaults invalid page numbers to 1", () => {
    assert.equal(parseCatalogPage(null), 1);
    assert.equal(parseCatalogPage("0"), 1);
    assert.equal(parseCatalogPage("1.5"), 1);
    assert.equal(parseCatalogPage("3"), 3);
  });

  it("slices and clamps past the last page", () => {
    const rows = Array.from({ length: 50 }, (_, i) => i);
    const first = paginateItems(rows, 1);
    assert.equal(first.items.length, CATALOG_PAGE_SIZE);
    assert.equal(first.items[0], 0);
    assert.equal(first.totalPages, 3);

    const last = paginateItems(rows, 99);
    assert.equal(last.page, 3);
    assert.deepEqual(last.items, [48, 49]);
  });
});
