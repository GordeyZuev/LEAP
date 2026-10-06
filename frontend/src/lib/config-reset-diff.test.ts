import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { configResetChanges, type ConfigResetDraft } from "./config-reset-diff.ts";

const trimming = {
  enable_trimming: true,
  silence_threshold: -40,
  min_silence_duration: 2,
  padding_before: 5,
  padding_after: 5,
};

const display = {
  enabled: true,
  format: "numbered_list",
  max_count: 999,
  min_length: 0,
  max_length: 999,
  prefix: "",
  separator: "\n",
  show_timestamps: true,
};

const draft: ConfigResetDraft = {
  language: "ru",
  granularity: "long",
  enableTranscription: true,
  enableTopics: true,
  enableSubtitles: true,
  allowErrors: false,
  questionsCount: 3,
  vocabulary: [],
  prompt: "",
  trimming,
  retentionChecked: false,
  publishLeap: true,
  autoUpload: true,
  uploadCaptions: true,
  presetIds: [],
  playlistIds: [],
  channelIds: [],
  titleTemplate: "",
  descriptionTemplate: "",
  thumbnail: "",
  topicsDisplay: display,
  questionsDisplay: { ...display, show_timestamps: undefined },
  leap: { title_template: "", description_template: "", thumbnail_name: "", auto_share: null },
  youtube: {
    title_template: "",
    description_template: "",
    privacy: "",
    category_id: "",
    playlist_id: "",
    thumbnail_name: "",
    tags: [],
    made_for_kids: false,
    embeddable: true,
    license: "",
    default_language: "",
    publish_at: "",
    disable_comments: false,
    rating_disabled: false,
    notify_subscribers: true,
  },
  yandex: {
    folder_path_template: "",
    filename_template: "",
    title_template: "",
    description_template: "",
    overwrite: false,
    publish: false,
    subtitles_srt: { enabled: false, filename_template: "", folder_path_template: "" },
    subtitles_vtt: { enabled: false, filename_template: "", folder_path_template: "" },
    transcription: { enabled: false, filename_template: "", folder_path_template: "" },
    description_txt: { enabled: false, filename_template: "", folder_path_template: "", content_template: "" },
  },
};

describe("reset to template diff", () => {
  it("stays empty when the form already matches the template", () => {
    assert.deepEqual(configResetChanges(draft, structuredClone(draft)), []);
  });

  it("lists a retention edit and a question-count edit as current to template", () => {
    const edited = {
      ...draft,
      retentionChecked: true,
      questionsCount: 8,
      trimming: { ...draft.trimming, enable_trimming: false },
    };
    const rows = configResetChanges(edited, draft);
    assert.deepEqual(
      rows.map((row) => `${row.label}: ${row.from} → ${row.to}`),
      [
        "Do not delete on a schedule: On → Off",
        "Questions: 8 → 3",
        "Trim silence: Off → On",
      ],
    );
  });

  it("names presets on the side they belong to", () => {
    const edited = { ...draft, presetIds: [2, 5] };
    const rows = configResetChanges(edited, draft, [
      { id: 2, name: "Course look", platform: "leap" },
      { id: 5, name: "YouTube", platform: "youtube" },
    ]);
    assert.deepEqual(
      rows.map((row) => `${row.label}: ${row.from} → ${row.to}`),
      [
        "LEAP look: Course look → None",
        "Upload presets: YouTube → None",
      ],
    );
  });
});
