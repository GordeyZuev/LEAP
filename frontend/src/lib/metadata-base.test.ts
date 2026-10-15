import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { metadataBaseFromHeaders } from "./metadata-base.ts";

function headers(values: Record<string, string>): { get(name: string): string | null } {
  return { get: (name) => values[name] ?? null };
}

describe("metadata base", () => {
  it("uses the public host and forwarded https proto", () => {
    const url = metadataBaseFromHeaders(
      headers({ host: "leap-platform.ru", "x-forwarded-proto": "https" }),
    );
    assert.equal(url.href, "https://leap-platform.ru/");
  });

  it("keeps local requests on http", () => {
    const url = metadataBaseFromHeaders(headers({ host: "localhost:3000" }));
    assert.equal(url.href, "http://localhost:3000/");
  });

  it("ignores client-supplied forwarded host and takes the first forwarded proto", () => {
    const url = metadataBaseFromHeaders(
      headers({
        host: "leap-platform.ru",
        "x-forwarded-host": "untrusted.example",
        "x-forwarded-proto": "https, http",
      }),
    );
    assert.equal(url.href, "https://leap-platform.ru/");
  });

  it("falls back when the host is not a URL", () => {
    const url = metadataBaseFromHeaders(headers({ host: "bad host" }));
    assert.equal(url.href, "http://localhost:3000/");
  });
});
