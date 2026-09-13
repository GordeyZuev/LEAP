import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  bundleToReplaceBody,
  formatReplaceEditorJson,
  parseReplaceEditorText,
  type TemplateBundle,
} from "./template-bundle.ts";

describe("parseReplaceEditorText", () => {
  it("accepts PUT-shaped body", () => {
    const item = parseReplaceEditorText(
      JSON.stringify({
        name: "T",
        is_draft: false,
        is_active: true,
        matching_rules: null,
        processing_config: null,
        metadata_config: null,
        output_config: null,
      }),
    );
    assert.equal(item.name, "T");
  });

  it("rejects import bundle", () => {
    assert.throws(
      () =>
        parseReplaceEditorText(
          JSON.stringify({ leap_template_bundle: 1, templates: [{ name: "X", is_draft: true, is_active: true }] }),
        ),
      /Import/,
    );
  });
});

describe("formatReplaceEditorJson", () => {
  it("omits matching_rules for base template export item", () => {
    const text = formatReplaceEditorJson({
      leap_template_bundle: 1,
      templates: [
        {
          name: "Default",
          is_draft: false,
          is_active: true,
          is_default: true,
          matching_rules: null,
        },
      ],
    } as TemplateBundle);
    const parsed = JSON.parse(text) as Record<string, unknown>;
    assert.equal("matching_rules" in parsed, false);
    assert.equal(bundleToReplaceBody(parsed as never).matching_rules, null);
  });
});
