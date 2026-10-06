export interface ResetChange {
  label: string;
  from: string;
  to: string;
}

export interface TrimmingDraft {
  enable_trimming: boolean;
  silence_threshold: number;
  min_silence_duration: number;
  padding_before: number;
  padding_after: number;
}

export interface DisplayDraft {
  enabled: boolean;
  format: string;
  max_count: number;
  min_length: number;
  max_length: number;
  prefix: string;
  separator: string;
  show_timestamps?: boolean;
}

export interface LeapDraft {
  title_template: string;
  description_template: string;
  thumbnail_name: string;
  auto_share: boolean | null;
}

export interface YouTubeDraft {
  title_template: string;
  description_template: string;
  privacy: string;
  category_id: string;
  playlist_id: string;
  thumbnail_name: string;
  tags: string[];
  made_for_kids: boolean;
  embeddable: boolean;
  license: string;
  default_language: string;
  publish_at: string;
  disable_comments: boolean;
  rating_disabled: boolean;
  notify_subscribers: boolean;
}

export interface ExtraFileDraft {
  enabled: boolean;
  filename_template: string;
  folder_path_template: string;
  content_template?: string;
}

export interface YandexDraft {
  folder_path_template: string;
  filename_template: string;
  title_template: string;
  description_template: string;
  overwrite: boolean;
  publish: boolean;
  subtitles_srt: ExtraFileDraft;
  subtitles_vtt: ExtraFileDraft;
  transcription: ExtraFileDraft;
  description_txt: ExtraFileDraft;
}

export interface ConfigResetDraft {
  language: string;
  granularity: string;
  enableTranscription: boolean;
  enableTopics: boolean;
  enableSubtitles: boolean;
  allowErrors: boolean;
  questionsCount: number;
  vocabulary: string[];
  prompt: string;
  trimming: TrimmingDraft;
  retentionChecked: boolean;
  publishLeap: boolean;
  autoUpload: boolean;
  uploadCaptions: boolean;
  presetIds: number[];
  playlistIds: number[];
  channelIds: number[];
  titleTemplate: string;
  descriptionTemplate: string;
  thumbnail: string;
  topicsDisplay: DisplayDraft;
  questionsDisplay: DisplayDraft;
  leap: LeapDraft;
  youtube: YouTubeDraft;
  yandex: YandexDraft;
}

interface NamedPreset {
  id: number;
  name: string;
  platform: string;
}

function clip(value: string) {
  const oneLine = value.replace(/\s+/g, " ").trim();
  if (!oneLine) return "Empty";
  return oneLine.length > 72 ? `${oneLine.slice(0, 71)}…` : oneLine;
}

function pushChange(rows: ResetChange[], label: string, from: string, to: string) {
  if (from !== to) rows.push({ label, from, to });
}

function onOff(value: boolean) {
  return value ? "On" : "Off";
}

function words(values: string[]) {
  return values.length ? clip(values.join(", ")) : "None";
}

function ids(values: number[], names?: Map<number, string>) {
  if (!values.length) return "None";
  return values.map((id) => names?.get(id) ?? `#${id}`).join(", ");
}

function presetsOf(idList: number[], presets: NamedPreset[], leap: boolean) {
  const names = new Map(presets.map((preset) => [preset.id, preset.name]));
  const picked = idList.filter((id) => {
    const preset = presets.find((item) => item.id === id);
    if (!preset) return !leap;
    return leap ? preset.platform === "leap" : preset.platform !== "leap";
  });
  return ids(picked, names);
}

function extra(file: ExtraFileDraft) {
  if (!file.enabled) return "Off";
  const name = file.filename_template.trim() || file.folder_path_template.trim() || file.content_template?.trim() || "";
  return name ? clip(name) : "On";
}

function share(value: boolean | null) {
  return value == null ? "Inherit" : onOff(value);
}

/** Differences between the open form and the template it would return to. */
export function configResetChanges(
  draft: ConfigResetDraft,
  template: ConfigResetDraft,
  presets: NamedPreset[] = [],
): ResetChange[] {
  const rows: ResetChange[] = [];
  pushChange(rows, "Do not delete on a schedule", onOff(draft.retentionChecked), onOff(template.retentionChecked));
  pushChange(rows, "Language", draft.language, template.language);
  pushChange(rows, "Granularity", draft.granularity, template.granularity);
  pushChange(rows, "Transcription", onOff(draft.enableTranscription), onOff(template.enableTranscription));
  pushChange(rows, "Topics", onOff(draft.enableTopics), onOff(template.enableTopics));
  pushChange(rows, "Subtitles", onOff(draft.enableSubtitles), onOff(template.enableSubtitles));
  pushChange(rows, "Questions", String(draft.questionsCount), String(template.questionsCount));
  pushChange(rows, "Allow errors", onOff(draft.allowErrors), onOff(template.allowErrors));
  pushChange(rows, "Vocabulary", words(draft.vocabulary), words(template.vocabulary));
  pushChange(rows, "Prompt", clip(draft.prompt), clip(template.prompt));
  pushChange(rows, "Trim silence", onOff(draft.trimming.enable_trimming), onOff(template.trimming.enable_trimming));
  pushChange(rows, "Silence threshold", String(draft.trimming.silence_threshold), String(template.trimming.silence_threshold));
  pushChange(rows, "Minimum silence", String(draft.trimming.min_silence_duration), String(template.trimming.min_silence_duration));
  pushChange(rows, "Padding before", String(draft.trimming.padding_before), String(template.trimming.padding_before));
  pushChange(rows, "Padding after", String(draft.trimming.padding_after), String(template.trimming.padding_after));
  pushChange(rows, "LEAP look", presetsOf(draft.presetIds, presets, true), presetsOf(template.presetIds, presets, true));
  pushChange(rows, "Upload presets", presetsOf(draft.presetIds, presets, false), presetsOf(template.presetIds, presets, false));
  pushChange(rows, "Publish to LEAP", onOff(draft.publishLeap), onOff(template.publishLeap));
  pushChange(rows, "Courses", ids(draft.playlistIds), ids(template.playlistIds));
  pushChange(rows, "Channels", ids(draft.channelIds), ids(template.channelIds));
  pushChange(rows, "Auto-upload", onOff(draft.autoUpload), onOff(template.autoUpload));
  pushChange(rows, "Upload captions", onOff(draft.uploadCaptions), onOff(template.uploadCaptions));
  pushChange(rows, "Title template", clip(draft.titleTemplate), clip(template.titleTemplate));
  pushChange(rows, "Description template", clip(draft.descriptionTemplate), clip(template.descriptionTemplate));
  pushChange(rows, "Cover image", clip(draft.thumbnail), clip(template.thumbnail));
  diffDisplay(rows, "Topics in text", draft.topicsDisplay, template.topicsDisplay);
  diffDisplay(rows, "Questions in text", draft.questionsDisplay, template.questionsDisplay);
  pushChange(rows, "LEAP title", clip(draft.leap.title_template), clip(template.leap.title_template));
  pushChange(rows, "LEAP description", clip(draft.leap.description_template), clip(template.leap.description_template));
  pushChange(rows, "LEAP cover", clip(draft.leap.thumbnail_name), clip(template.leap.thumbnail_name));
  pushChange(rows, "LEAP share link", share(draft.leap.auto_share), share(template.leap.auto_share));
  diffYouTube(rows, draft.youtube, template.youtube);
  diffYandex(rows, draft.yandex, template.yandex);
  return rows;
}

function diffDisplay(rows: ResetChange[], label: string, draft: DisplayDraft, template: DisplayDraft) {
  pushChange(rows, label, onOff(draft.enabled), onOff(template.enabled));
  pushChange(rows, `${label} format`, draft.format, template.format);
  pushChange(rows, `${label} limit`, String(draft.max_count), String(template.max_count));
  pushChange(rows, `${label} shortest`, String(draft.min_length), String(template.min_length));
  pushChange(rows, `${label} longest`, String(draft.max_length), String(template.max_length));
  pushChange(rows, `${label} prefix`, clip(draft.prefix), clip(template.prefix));
  pushChange(rows, `${label} separator`, clip(draft.separator), clip(template.separator));
  if (draft.show_timestamps != null || template.show_timestamps != null) {
    pushChange(
      rows,
      `${label} timestamps`,
      onOff(draft.show_timestamps !== false),
      onOff(template.show_timestamps !== false),
    );
  }
}

function diffYouTube(rows: ResetChange[], draft: YouTubeDraft, template: YouTubeDraft) {
  pushChange(rows, "YouTube title", clip(draft.title_template), clip(template.title_template));
  pushChange(rows, "YouTube description", clip(draft.description_template), clip(template.description_template));
  pushChange(rows, "YouTube privacy", clip(draft.privacy), clip(template.privacy));
  pushChange(rows, "YouTube category", clip(draft.category_id), clip(template.category_id));
  pushChange(rows, "YouTube playlist", clip(draft.playlist_id), clip(template.playlist_id));
  pushChange(rows, "YouTube cover", clip(draft.thumbnail_name), clip(template.thumbnail_name));
  pushChange(rows, "YouTube tags", words(draft.tags), words(template.tags));
  pushChange(rows, "Made for kids", onOff(draft.made_for_kids), onOff(template.made_for_kids));
  pushChange(rows, "YouTube embeddable", onOff(draft.embeddable), onOff(template.embeddable));
  pushChange(rows, "YouTube license", clip(draft.license), clip(template.license));
  pushChange(rows, "YouTube language", clip(draft.default_language), clip(template.default_language));
  pushChange(rows, "YouTube publish time", clip(draft.publish_at), clip(template.publish_at));
  pushChange(rows, "YouTube comments off", onOff(draft.disable_comments), onOff(template.disable_comments));
  pushChange(rows, "YouTube ratings off", onOff(draft.rating_disabled), onOff(template.rating_disabled));
  pushChange(rows, "Notify subscribers", onOff(draft.notify_subscribers), onOff(template.notify_subscribers));
}

function diffYandex(rows: ResetChange[], draft: YandexDraft, template: YandexDraft) {
  pushChange(rows, "Yandex folder", clip(draft.folder_path_template), clip(template.folder_path_template));
  pushChange(rows, "Yandex filename", clip(draft.filename_template), clip(template.filename_template));
  pushChange(rows, "Yandex title", clip(draft.title_template), clip(template.title_template));
  pushChange(rows, "Yandex description", clip(draft.description_template), clip(template.description_template));
  pushChange(rows, "Yandex overwrite", onOff(draft.overwrite), onOff(template.overwrite));
  pushChange(rows, "Yandex publish", onOff(draft.publish), onOff(template.publish));
  pushChange(rows, "Yandex SRT", extra(draft.subtitles_srt), extra(template.subtitles_srt));
  pushChange(rows, "Yandex VTT", extra(draft.subtitles_vtt), extra(template.subtitles_vtt));
  pushChange(rows, "Yandex transcript file", extra(draft.transcription), extra(template.transcription));
  pushChange(rows, "Yandex description file", extra(draft.description_txt), extra(template.description_txt));
}
