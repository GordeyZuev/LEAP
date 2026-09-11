"use client";

import { Fragment, useId, useLayoutEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { applyDescriptionHotkey, isDescriptionFormatHotkey } from "@/lib/formatted-text";
import { TagInput } from "@/components/ui/tag-input";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { NativeSelect } from "@/components/ui/native-select";
import { PlaylistPicker } from "@/components/playlists/playlist-picker";
import { ThumbnailPicker } from "@/components/platforms/thumbnail-picker";
import { YandexFolderPicker } from "@/components/platforms/yandex-folder-picker";
import { Field } from "@/components/ui/field";
import { Toggle } from "@/components/ui/toggle";
import { AboutFormatting } from "@/components/ui/about-formatting";
import { AdvancedBlock, ToggleGrid } from "@/components/ui/disclosure";
import { useLanguages } from "@/hooks/use-references";
import { insertJinjaVar, useJinjaCombobox } from "@/hooks/use-jinja-combobox";
import {
  DisplayConfigFields,
  type DisplayConfig,
  defaultTopicsDisplay,
  defaultQuestionsDisplay,
  toDisplayPayload,
  fromDisplayPayload,
} from "@/components/platforms/display-config-fields";
import type { DisplayConfigDefaultsPayload } from "@/lib/display-config-defaults";
import { DISPLAY_CONFIG_PLACEHOLDER } from "@/lib/display-config-defaults";

// Re-exported for existing importers.
export { Toggle as PlatformToggle };

// ---------------------------------------------------------------------------
// Jinja2 variable definitions (shown in autocomplete dropdown)
// ---------------------------------------------------------------------------

const JINJA_VARS: { value: string; description: string }[] = [
  { value: "display_name",       description: "Recording title" },
  { value: "topics",             description: "Formatted timestamps" },
  { value: "summary",            description: "Text summary" },
  { value: "themes",             description: "Comma-separated themes" },
  { value: "questions",          description: "Self-check questions" },
  { value: "duration_hm",        description: "Duration H:MM:SS" },
  { value: "duration",           description: "Duration in seconds (raw float)" },
  { value: "record_date",        description: "Record date DD.MM.YYYY" },
  { value: "record_date_iso",    description: "Record date YYYY-MM-DD" },
  { value: "record_date_short",  description: "Record date DD.MM.YY" },
  { value: "record_datetime",    description: "Record date+time DD.MM.YYYY HH:MM" },
  { value: "record_datetime_iso",description: "Record date+time YYYY-MM-DD HH:MM" },
  { value: "record_time_hm",     description: "Record time HH:MM" },
  { value: "publish_date",       description: "Publish date DD.MM.YYYY" },
  { value: "publish_date_iso",   description: "Publish date YYYY-MM-DD" },
  { value: "publish_date_short", description: "Publish date DD.MM.YY" },
  { value: "publish_datetime",   description: "Publish date+time DD.MM.YYYY HH:MM" },
  { value: "publish_datetime_iso",description: "Publish date+time YYYY-MM-DD HH:MM" },
  { value: "publish_time_hm",    description: "Publish time HH:MM" },
  { value: "title",              description: "Rendered title (use in description only)" },
  { value: "recording_id",       description: "Recording ID" },
];

// TemplateField — textarea + overlay for Jinja2 highlighting (no innerHTML).

const TOKEN_REGEX = /(\{\{[^}]*\}\})/g;

function renderHighlightedTokens(text: string): ReactNode[] {
  if (!text) return [];
  const out: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  TOKEN_REGEX.lastIndex = 0;
  while ((match = TOKEN_REGEX.exec(text)) !== null) {
    if (match.index > lastIndex) {
      out.push(<Fragment key={`t-${key++}`}>{text.slice(lastIndex, match.index)}</Fragment>);
    }
    out.push(
      <span key={`v-${key++}`} className="text-primary">
        {match[0]}
      </span>,
    );
    lastIndex = TOKEN_REGEX.lastIndex;
  }
  if (lastIndex < text.length) {
    out.push(<Fragment key={`t-${key++}`}>{text.slice(lastIndex)}</Fragment>);
  }
  if (text.endsWith("\n")) {
    out.push(<Fragment key="trail">{"​"}</Fragment>);
  }
  return out;
}

function syncMultilineHeight(ta: HTMLTextAreaElement) {
  ta.style.height = "auto";
  const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 18;
  ta.style.height = `${ta.scrollHeight + lineHeight}px`;
}

interface TemplateFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
  rows?: number;
  labelExtra?: ReactNode;
}

export function TemplateField({
  label,
  value,
  onChange,
  multiline = false,
  placeholder,
  rows = 1,
  labelExtra,
}: TemplateFieldProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fieldId = useId();
  const listboxId = useId();
  const optionIdPrefix = useId();
  const ac = useJinjaCombobox(JINJA_VARS);

  useLayoutEffect(() => {
    if (!multiline || !textareaRef.current) return;
    syncMultilineHeight(textareaRef.current);
  }, [value, multiline]);

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const ta = e.currentTarget;
    let next = ta.value;
    if (!multiline) {
      const stripped = next.replace(/\r?\n/g, " ");
      if (stripped !== next) {
        const caret = ta.selectionStart;
        next = stripped;
        requestAnimationFrame(() => {
          if (textareaRef.current) {
            textareaRef.current.setSelectionRange(caret, caret);
          }
        });
      }
    }
    onChange(next);
    ac.updateFromCaret(next, ta.selectionStart);
  }

  function commitInsert(varName: string) {
    const ta = textareaRef.current;
    if (!ta) return;
    const { next, caret } = insertJinjaVar(value, ta.selectionStart, ta.selectionEnd, varName);
    onChange(next);
    ac.setAcOpen(false);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(caret, caret);
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const listOpen = ac.acOpen && ac.filtered.length > 0;
    if (listOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        ac.moveHighlight(1);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        ac.moveHighlight(-1);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        if (ac.active) {
          e.preventDefault();
          commitInsert(ac.active.value);
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        ac.setAcOpen(false);
        return;
      }
    }
    if (e.key === "Enter" && !multiline) {
      e.preventDefault();
      return;
    }
    if (multiline && (e.metaKey || e.ctrlKey) && !e.altKey) {
      if (!isDescriptionFormatHotkey(e.code, e.shiftKey)) return;
      e.preventDefault();
      const ta = e.currentTarget;
      const applied = applyDescriptionHotkey(e.code, e.shiftKey, ta.value, ta.selectionStart, ta.selectionEnd);
      if (!applied || applied.next === ta.value) return;
      onChange(applied.next);
      const [a, b] = applied.range;
      requestAnimationFrame(() => {
        textareaRef.current?.focus();
        textareaRef.current?.setSelectionRange(a, b);
      });
    }
  }

  function handleScroll(e: React.UIEvent<HTMLTextAreaElement>) {
    const overlay = overlayRef.current;
    if (!overlay) return;
    overlay.scrollTop = e.currentTarget.scrollTop;
    overlay.scrollLeft = e.currentTarget.scrollLeft;
  }

  function handleBlur() {
    blurTimer.current = setTimeout(() => ac.setAcOpen(false), 150);
  }

  const singleLineTypography = "text-sm font-medium leading-7";
  const multiLineTypography = "font-mono text-xs font-medium leading-[1.5]";
  const typography = multiline ? multiLineTypography : singleLineTypography;

  const fieldSurface = cn(
    FILTER_CONTROL,
    typography,
    multiline ? "min-h-[2.875rem] max-h-[40vh]" : "h-[2.875rem] min-h-0",
  );

  return (
    <div className="space-y-1">
      {labelExtra ? (
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <label htmlFor={fieldId} className="text-xs font-medium text-muted-foreground">
            {label}
          </label>
          {labelExtra}
        </div>
      ) : (
        <label htmlFor={fieldId} className={FILTER_LABEL}>
          {label}
        </label>
      )}
      <div className="relative">
        <div
          ref={overlayRef}
          aria-hidden="true"
          className={cn(
            fieldSurface,
            "pointer-events-none absolute inset-0 select-none overflow-hidden text-foreground",
            multiline ? "whitespace-pre-wrap break-words" : "whitespace-pre",
          )}
        >
          {renderHighlightedTokens(value)}
        </div>

        <textarea
          ref={textareaRef}
          id={fieldId}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onScroll={handleScroll}
          onBlur={handleBlur}
          onSelect={(e) => ac.updateFromCaret(value, e.currentTarget.selectionStart)}
          rows={multiline ? rows : 1}
          spellCheck={false}
          aria-autocomplete="list"
          aria-expanded={ac.acOpen && ac.filtered.length > 0}
          aria-controls={ac.acOpen && ac.filtered.length > 0 ? listboxId : undefined}
          aria-activedescendant={
            ac.acOpen && ac.active ? `${optionIdPrefix}-${ac.active.value}` : undefined
          }
          placeholder={placeholder}
          className={cn(
            fieldSurface,
            "relative z-10 m-0 block w-full appearance-none bg-transparent text-transparent caret-gray-900 placeholder:text-muted-foreground",
            multiline
              ? "resize-y overflow-x-hidden whitespace-pre-wrap break-words"
              : "resize-none overflow-x-auto overflow-y-hidden whitespace-pre",
          )}
        />

        {ac.acOpen && ac.filtered.length > 0 && (
          <ul
            id={listboxId}
            role="listbox"
            className="absolute left-0 right-0 top-full z-50 mt-1 max-h-44 overflow-y-auto rounded-xl border border-border bg-card shadow-lg"
          >
            {ac.filtered.map((v) => (
              <li
                key={v.value}
                id={`${optionIdPrefix}-${v.value}`}
                role="option"
                aria-selected={ac.active?.value === v.value}
              >
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    if (blurTimer.current) clearTimeout(blurTimer.current);
                    commitInsert(v.value);
                  }}
                  className={cn(
                    "flex w-full items-center gap-3 px-3 py-2 text-left",
                    ac.active?.value === v.value ? "bg-muted" : "hover:bg-muted",
                  )}
                >
                  <code className="shrink-0 font-mono text-xs text-primary">{`{{ ${v.value} }}`}</code>
                  <span className="text-xs text-muted-foreground">{v.description}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <AboutFormatting multiline={multiline} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// LEAP look (course/share) — title, description, cover
// ---------------------------------------------------------------------------

export interface LeapFieldsValue {
  title_template: string;
  description_template: string;
  thumbnail_name: string;
  playlist_ids: number[];
  auto_share: boolean | null;
}

export const DEFAULT_LEAP_FIELDS: LeapFieldsValue = {
  title_template: "",
  description_template: "",
  thumbnail_name: "",
  playlist_ids: [],
  auto_share: null,
};

export function leapFieldsFromApi(raw: unknown): LeapFieldsValue {
  const obj = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const ids = Array.isArray(obj.playlist_ids)
    ? obj.playlist_ids.filter((n): n is number => typeof n === "number" && n > 0)
    : [];
  return {
    title_template: typeof obj.title_template === "string" ? obj.title_template : "",
    description_template: typeof obj.description_template === "string" ? obj.description_template : "",
    thumbnail_name: typeof obj.thumbnail_name === "string" ? obj.thumbnail_name : "",
    playlist_ids: ids,
    auto_share: typeof obj.auto_share === "boolean" ? obj.auto_share : null,
  };
}

export interface LeapLookPresetDefaults {
  title_template?: string;
  description_template?: string;
  thumbnail_name?: string;
  auto_share?: boolean;
}

export function LeapLookFields({
  value,
  onChange,
  showPublish = false,
  showAutoShareOverride = false,
  presetDefaults,
}: {
  value: LeapFieldsValue;
  onChange: (patch: Partial<LeapFieldsValue>) => void;
  showPublish?: boolean;
  showAutoShareOverride?: boolean;
  /** Resolved LEAP preset values shown when override fields are empty / inherit. */
  presetDefaults?: LeapLookPresetDefaults | null;
}) {
  const presetShareOn = presetDefaults?.auto_share ?? false;
  return (
    <div className="space-y-4">
      {showPublish ? (
        <>
          <Toggle
            label="Auto-publish share link"
            hint="On after processing unless sharing is off."
            checked={Boolean(value.auto_share)}
            onChange={(v) => onChange({ auto_share: v })}
          />
          <Field
            label="LEAP playlists"
            hint="Default playlists; templates and Run can replace this list."
          >
            <PlaylistPicker mode="form" selectedIds={value.playlist_ids} onChange={(ids) => onChange({ playlist_ids: ids })} />
          </Field>
        </>
      ) : null}
      {showAutoShareOverride ? (
        <div className="space-y-1">
          <span className={FILTER_LABEL}>Auto-publish share link</span>
          <NativeSelect
            ariaLabel="Auto-publish share link"
            value={value.auto_share === null ? "" : value.auto_share ? "on" : "off"}
            onChange={(e) => {
              const v = e.target.value;
              onChange({ auto_share: v === "" ? null : v === "on" });
            }}
          >
            <option value="">
              Same as preset ({presetShareOn ? "On" : "Off"})
            </option>
            <option value="on">On</option>
            <option value="off">Off</option>
          </NativeSelect>
          <p className="text-xs text-muted-foreground">
            Preset default is {presetShareOn ? "on" : "off"}. Choose On/Off to override.
          </p>
        </div>
      ) : null}
      <TemplateField
        label="Title template"
        value={value.title_template}
        onChange={(v) => onChange({ title_template: v })}
        placeholder={presetDefaults?.title_template?.trim() || "{{ display_name }}"}
      />
      <TemplateField
        label="Description template"
        value={value.description_template}
        onChange={(v) => onChange({ description_template: v })}
        multiline
        rows={6}
        placeholder={
          presetDefaults?.description_template?.trim()
          || "{{ summary }}\n\n{{ topics }}"
        }
      />
      <ThumbnailPicker
        label="Cover image"
        placeholder={presetDefaults?.thumbnail_name?.trim() || "No cover image"}
        value={value.thumbnail_name}
        onChange={(name) => onChange({ thumbnail_name: name })}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// YouTube fields
// ---------------------------------------------------------------------------

export interface YouTubeFieldsValue {
  title_template: string;
  description_template: string;
  privacy: string;
  category_id: string;
  playlist_id: string;
  thumbnail_name: string;
  tags: string[];
  made_for_kids: boolean;
  // Extended (presets only): null/empty => inherit base default.
  embeddable: boolean;
  license: string;
  default_language: string;
  publish_at: string; // datetime-local string; serialised to ISO on save
  disable_comments: boolean;
  rating_disabled: boolean;
  notify_subscribers: boolean;
  topics_display: DisplayConfig;
  questions_display: DisplayConfig;
}

export const DEFAULT_YOUTUBE_FIELDS: YouTubeFieldsValue = {
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
  topics_display: defaultTopicsDisplay(),
  questions_display: defaultQuestionsDisplay(),
};

const YT_PRIVACY_OPTIONS = [
  { value: "",         label: "— default —" },
  { value: "public",   label: "Public" },
  { value: "unlisted", label: "Unlisted" },
  { value: "private",  label: "Private" },
];

const YT_LICENSE_OPTIONS = [
  { value: "",               label: "— default —" },
  { value: "youtube",        label: "Standard YouTube" },
  { value: "creativeCommon", label: "Creative Commons" },
];

export function YouTubeFields({
  value,
  onChange,
  showThumbnail = false,
  showMadeForKids = false,
  showExtended = false,
  showDisplayConfig = false,
}: {
  value: YouTubeFieldsValue;
  onChange: (patch: Partial<YouTubeFieldsValue>) => void;
  showThumbnail?: boolean;
  showMadeForKids?: boolean;
  showExtended?: boolean;
  showDisplayConfig?: boolean;
}) {
  const { data: languages = [] } = useLanguages();
  return (
    <div className="space-y-4">
      <TemplateField
        label="Title template"
        value={value.title_template}
        onChange={(v) => onChange({ title_template: v })}
        placeholder="{{ display_name }} | {{ topics }}"
      />
      <TemplateField
        label="Description template"
        value={value.description_template}
        onChange={(v) => onChange({ description_template: v })}
        multiline
        placeholder={"Recording from {{ date }}\n\n{{ topics }}"}
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <span className={FILTER_LABEL}>Privacy</span>
          <NativeSelect
            value={value.privacy}
            onChange={(e) => onChange({ privacy: e.target.value })}
          >
            {YT_PRIVACY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1">
          <span className={FILTER_LABEL}>Category ID</span>
          <input
            type="text"
            value={value.category_id}
            onChange={(e) => onChange({ category_id: e.target.value })}
            placeholder="27"
            className={FILTER_CONTROL}
          />
        </div>
      </div>
      <div className="space-y-1">
        <span className={FILTER_LABEL}>Playlist ID</span>
        <input
          type="text"
          value={value.playlist_id}
          onChange={(e) => onChange({ playlist_id: e.target.value })}
          placeholder="PLxxxxxxxxxxxxxxxx"
          className={FILTER_CONTROL}
        />
      </div>
      {showThumbnail && (
        <ThumbnailPicker
          value={value.thumbnail_name}
          onChange={(name) => onChange({ thumbnail_name: name })}
        />
      )}
      <div className="space-y-1">
        <span className={FILTER_LABEL}>Tags</span>
        <TagInput
          tags={value.tags}
          onChange={(tags) => onChange({ tags })}
          placeholder="Add tag…"
        />
      </div>
      {showMadeForKids && !showExtended && (
        <Toggle
          label="Made for kids"
          checked={value.made_for_kids}
          onChange={(v) => onChange({ made_for_kids: v })}
        />
      )}

      {showDisplayConfig && (
        <>
          <DisplayConfigFields
            kind="topics"
            value={value.topics_display}
            onChange={(patch) => onChange({ topics_display: { ...value.topics_display, ...patch } })}
          />
          <DisplayConfigFields
            kind="questions"
            value={value.questions_display}
            onChange={(patch) => onChange({ questions_display: { ...value.questions_display, ...patch } })}
          />
        </>
      )}

      {showExtended && (
        <AdvancedBlock title="Extra YouTube settings">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <span className={FILTER_LABEL}>License</span>
              <NativeSelect value={value.license} onChange={(e) => onChange({ license: e.target.value })}>
                {YT_LICENSE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1">
              <span className={FILTER_LABEL}>Default language</span>
              <NativeSelect
                value={value.default_language}
                onChange={(e) => onChange({ default_language: e.target.value })}
              >
                <option value="">— default —</option>
                {languages.filter((l) => l.value !== "auto").map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </NativeSelect>
            </div>
          </div>
          <div className="space-y-1">
            <span className={FILTER_LABEL}>Scheduled publish</span>
            <input
              type="datetime-local"
              value={value.publish_at}
              onChange={(e) => onChange({ publish_at: e.target.value })}
              className={FILTER_CONTROL}
            />
            <p className="text-xs text-muted-foreground">Leave empty to publish per the privacy setting.</p>
          </div>
          <ToggleGrid>
            <Toggle label="Embeddable" checked={value.embeddable} onChange={(v) => onChange({ embeddable: v })} />
            <Toggle label="Notify subscribers" checked={value.notify_subscribers} onChange={(v) => onChange({ notify_subscribers: v })} />
            <Toggle label="Disable comments" checked={value.disable_comments} onChange={(v) => onChange({ disable_comments: v })} />
            <Toggle label="Disable ratings" checked={value.rating_disabled} onChange={(v) => onChange({ rating_disabled: v })} />
            <Toggle label="Made for kids" checked={value.made_for_kids} onChange={(v) => onChange({ made_for_kids: v })} />
          </ToggleGrid>
        </AdvancedBlock>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// VK fields
// ---------------------------------------------------------------------------

export interface VkFieldsValue {
  title_template: string;
  description_template: string;
  privacy_view: string;
  privacy_comment: string;
  group_id: string;
  album_id: string;
  thumbnail_name: string;
  wallpost: boolean;
  // Extended (presets only)
  repeat: boolean;
  compression: boolean;
  disable_comments: boolean;
  topics_display: DisplayConfig;
  questions_display: DisplayConfig;
}

export const DEFAULT_VK_FIELDS: VkFieldsValue = {
  title_template: "",
  description_template: "",
  privacy_view: "",
  privacy_comment: "",
  group_id: "",
  album_id: "",
  thumbnail_name: "",
  wallpost: false,
  repeat: false,
  compression: false,
  disable_comments: false,
  topics_display: defaultTopicsDisplay(),
  questions_display: defaultQuestionsDisplay(),
};

const VK_PRIVACY_OPTIONS = [
  { value: "",  label: "— default —" },
  { value: "0", label: "All users" },
  { value: "1", label: "Friends" },
  { value: "2", label: "Friends of friends" },
  { value: "3", label: "Only me" },
];

export function VkFields({
  value,
  onChange,
  showThumbnail = false,
  showPrivacyComment = false,
  showWallpost = false,
  showExtended = false,
  showDisplayConfig = false,
}: {
  value: VkFieldsValue;
  onChange: (patch: Partial<VkFieldsValue>) => void;
  showThumbnail?: boolean;
  showPrivacyComment?: boolean;
  showWallpost?: boolean;
  showExtended?: boolean;
  showDisplayConfig?: boolean;
}) {
  return (
    <div className="space-y-4">
      <TemplateField
        label="Title template"
        value={value.title_template}
        onChange={(v) => onChange({ title_template: v })}
        placeholder="{{ display_name }}"
      />
      <TemplateField
        label="Description template"
        value={value.description_template}
        onChange={(v) => onChange({ description_template: v })}
        multiline
        placeholder={"Recording from {{ date }}\n\n{{ topics }}"}
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <span className={FILTER_LABEL}>Group ID</span>
          <input
            type="text"
            value={value.group_id}
            onChange={(e) => onChange({ group_id: e.target.value })}
            placeholder="123456"
            className={FILTER_CONTROL}
          />
        </div>
        <div className="space-y-1">
          <span className={FILTER_LABEL}>Album ID</span>
          <input
            type="text"
            value={value.album_id}
            onChange={(e) => onChange({ album_id: e.target.value })}
            placeholder="123456"
            className={FILTER_CONTROL}
          />
        </div>
      </div>
      {showThumbnail && (
        <ThumbnailPicker
          value={value.thumbnail_name}
          onChange={(name) => onChange({ thumbnail_name: name })}
        />
      )}
      <div className={cn("grid gap-3", showPrivacyComment ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1 sm:max-w-[50%]")}>
        <div className="space-y-1">
          <span className={FILTER_LABEL}>Privacy — view</span>
          <NativeSelect
            value={value.privacy_view}
            onChange={(e) => onChange({ privacy_view: e.target.value })}
          >
            {VK_PRIVACY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </NativeSelect>
        </div>
        {showPrivacyComment && (
          <div className="space-y-1">
            <span className={FILTER_LABEL}>Privacy — comments</span>
            <NativeSelect
              value={value.privacy_comment}
              onChange={(e) => onChange({ privacy_comment: e.target.value })}
            >
              {VK_PRIVACY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </NativeSelect>
          </div>
        )}
      </div>
      {showWallpost && (
        <Toggle
          label="Post to wall"
          checked={value.wallpost}
          onChange={(v) => onChange({ wallpost: v })}
        />
      )}

      {showDisplayConfig && (
        <>
          <DisplayConfigFields
            kind="topics"
            value={value.topics_display}
            onChange={(patch) => onChange({ topics_display: { ...value.topics_display, ...patch } })}
          />
          <DisplayConfigFields
            kind="questions"
            value={value.questions_display}
            onChange={(patch) => onChange({ questions_display: { ...value.questions_display, ...patch } })}
          />
        </>
      )}

      {showExtended && (
        <AdvancedBlock title="Extra VK settings">
          <ToggleGrid>
            <Toggle label="Loop playback" checked={value.repeat} onChange={(v) => onChange({ repeat: v })} />
            <Toggle label="VK-side compression" checked={value.compression} onChange={(v) => onChange({ compression: v })} />
            <Toggle label="Disable comments" checked={value.disable_comments} onChange={(v) => onChange({ disable_comments: v })} />
          </ToggleGrid>
        </AdvancedBlock>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Yandex Disk fields
// ---------------------------------------------------------------------------

/** Optional sidecar file on Disk. `enabled` mirrors backend "presence => upload". */
export interface YandexExtraFile {
  enabled: boolean;
  filename_template: string;
  folder_path_template: string;
}

export interface YandexDescriptionTxt extends YandexExtraFile {
  content_template: string;
}

export const DEFAULT_YANDEX_EXTRA_FILE: YandexExtraFile = {
  enabled: false,
  filename_template: "",
  folder_path_template: "",
};

export const DEFAULT_YANDEX_DESCRIPTION_TXT: YandexDescriptionTxt = {
  ...DEFAULT_YANDEX_EXTRA_FILE,
  content_template: "",
};

export interface YandexDiskFieldsValue {
  folder_path_template: string;
  filename_template: string;
  title_template: string;
  description_template: string;
  overwrite: boolean;
  publish: boolean;
  subtitles_srt: YandexExtraFile;
  subtitles_vtt: YandexExtraFile;
  transcription: YandexExtraFile;
  description_txt: YandexDescriptionTxt;
}

export const DEFAULT_YANDEX_DISK_FIELDS: YandexDiskFieldsValue = {
  folder_path_template: "",
  filename_template: "",
  title_template: "",
  description_template: "",
  overwrite: false,
  publish: false,
  subtitles_srt: { ...DEFAULT_YANDEX_EXTRA_FILE },
  subtitles_vtt: { ...DEFAULT_YANDEX_EXTRA_FILE },
  transcription: { ...DEFAULT_YANDEX_EXTRA_FILE },
  description_txt: { ...DEFAULT_YANDEX_DESCRIPTION_TXT },
};

/** Collapsible sidecar-file editor (enable toggle → filename/folder [+ content]). */
function YandexExtraFileBlock({
  label,
  value,
  onChange,
  withContent = false,
  credentialId,
}: {
  label: string;
  value: YandexExtraFile | YandexDescriptionTxt;
  onChange: (patch: Partial<YandexDescriptionTxt>) => void;
  withContent?: boolean;
  credentialId?: number | "";
}) {
  return (
    <div className="rounded-xl border border-border bg-background px-4 py-3">
      <Toggle label={label} checked={value.enabled} onChange={(v) => onChange({ enabled: v })} />
      {value.enabled && (
        <div className="space-y-3 border-t border-border pt-3">
          <TemplateField
            label="Filename template"
            value={value.filename_template}
            onChange={(v) => onChange({ filename_template: v })}
            placeholder="{{ display_name }}"
          />
          <TemplateField
            label="Folder path template"
            value={value.folder_path_template}
            onChange={(v) => onChange({ folder_path_template: v })}
            placeholder="(same folder as video)"
            labelExtra={
              credentialId ? (
                <YandexFolderPicker
                  compact
                  value={value.folder_path_template}
                  onChange={(v) => onChange({ folder_path_template: v })}
                  credentialId={credentialId}
                  mode="path"
                />
              ) : undefined
            }
          />
          {withContent && (
            <TemplateField
              label="Content template"
              value={(value as YandexDescriptionTxt).content_template}
              onChange={(v) => onChange({ content_template: v })}
              multiline
              placeholder="{{ summary }}\n\n{{ topics }}"
            />
          )}
        </div>
      )}
    </div>
  );
}

export function YandexDiskFields({
  value,
  onChange,
  showExtended = false,
  credentialId,
}: {
  value: YandexDiskFieldsValue;
  onChange: (patch: Partial<YandexDiskFieldsValue>) => void;
  /** Presets only: title/description templates + sidecar files (template-level
   *  YandexDiskMetadataConfig has none of these). */
  showExtended?: boolean;
  credentialId?: number | "";
}) {
  return (
    <div className="space-y-4">
      <TemplateField
        label="Folder path template"
        value={value.folder_path_template}
        onChange={(v) => onChange({ folder_path_template: v })}
        placeholder="/Video/{{ display_name }}"
        labelExtra={
          credentialId ? (
            <YandexFolderPicker
              compact
              value={value.folder_path_template}
              onChange={(v) => onChange({ folder_path_template: v })}
              credentialId={credentialId}
              mode="path"
            />
          ) : undefined
        }
      />
      {!credentialId && (
        <p className="text-xs text-muted-foreground">
          Link a Yandex Disk output preset with a credential to browse folders.
        </p>
      )}
      <TemplateField
        label="Filename template"
        value={value.filename_template}
        onChange={(v) => onChange({ filename_template: v })}
        placeholder="{{ display_name }}.mp4"
      />
      <ToggleGrid>
        <Toggle
          label="Overwrite existing"
          checked={value.overwrite}
          onChange={(v) => onChange({ overwrite: v })}
        />
        <Toggle
          label="Publish publicly"
          checked={value.publish}
          onChange={(v) => onChange({ publish: v })}
        />
      </ToggleGrid>

      {showExtended && (
        <AdvancedBlock title="Extra Yandex Disk settings">
          <TemplateField
            label="Title template"
            value={value.title_template}
            onChange={(v) => onChange({ title_template: v })}
            placeholder="{{ display_name }}"
          />
          <TemplateField
            label="Description template"
            value={value.description_template}
            onChange={(v) => onChange({ description_template: v })}
            multiline
            placeholder={"Recording from {{ date }}\n\n{{ topics }}"}
          />
          <YandexExtraFileBlock
            label="Upload subtitles (.srt)"
            value={value.subtitles_srt}
            onChange={(patch) => onChange({ subtitles_srt: { ...value.subtitles_srt, ...patch } })}
            credentialId={credentialId}
          />
          <YandexExtraFileBlock
            label="Upload subtitles (.vtt)"
            value={value.subtitles_vtt}
            onChange={(patch) => onChange({ subtitles_vtt: { ...value.subtitles_vtt, ...patch } })}
            credentialId={credentialId}
          />
          <YandexExtraFileBlock
            label="Upload transcription (.txt)"
            value={value.transcription}
            onChange={(patch) => onChange({ transcription: { ...value.transcription, ...patch } })}
            credentialId={credentialId}
          />
          <YandexExtraFileBlock
            label="Upload description (.txt)"
            value={value.description_txt}
            onChange={(patch) => onChange({ description_txt: { ...value.description_txt, ...patch } })}
            credentialId={credentialId}
            withContent
          />
        </AdvancedBlock>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Serde helpers — single source of truth for field <-> API mapping, shared by
// the Preset editor, Template editor and Run-with-config modal.
//
//   *FromApi  : hydrate editor state from a stored metadata object (or null)
//   *ToApi    : serialise editor state, dropping empty optionals
//
// `includeDisplay` controls per-platform topics/questions (presets store them
// inside the platform object; templates/run store them at the common level).
// `includeExtended` (Yandex) gates title/description templates + sidecar files
// (template-level YandexDiskMetadataConfig does not support them).
// ---------------------------------------------------------------------------

export function youtubeFieldsFromApi(
  raw: unknown,
  defaults: DisplayConfigDefaultsPayload = DISPLAY_CONFIG_PLACEHOLDER,
): YouTubeFieldsValue {
  const base = { ...DEFAULT_YOUTUBE_FIELDS };
  if (!raw || typeof raw !== "object") return base;
  const o = raw as Record<string, unknown>;
  const priv = o.privacy;
  const tagList = o.tags;
  return {
    ...base,
    title_template:       o.title_template       != null ? String(o.title_template)       : "",
    description_template: o.description_template != null ? String(o.description_template) : "",
    privacy:        priv === "public" || priv === "private" || priv === "unlisted" ? priv : "",
    category_id:    o.category_id    != null ? String(o.category_id)    : "",
    playlist_id:    o.playlist_id    != null ? String(o.playlist_id)    : "",
    thumbnail_name: o.thumbnail_name != null ? String(o.thumbnail_name) : "",
    tags:           Array.isArray(tagList) ? tagList.filter((t): t is string => typeof t === "string") : [],
    made_for_kids:  Boolean(o.made_for_kids),
    embeddable:         o.embeddable != null ? Boolean(o.embeddable) : true,
    license:            typeof o.license === "string" ? o.license : "",
    default_language:   o.default_language != null ? String(o.default_language) : "",
    publish_at:         o.publish_at != null ? String(o.publish_at).slice(0, 16) : "",
    disable_comments:   Boolean(o.disable_comments),
    rating_disabled:    Boolean(o.rating_disabled),
    notify_subscribers: o.notify_subscribers != null ? Boolean(o.notify_subscribers) : true,
    topics_display:     fromDisplayPayload(o.topics_display, "topics", defaults),
    questions_display:  fromDisplayPayload(o.questions_display, "questions", defaults),
  };
}

export function youtubeFieldsToApi(
  v: YouTubeFieldsValue,
  opts: { includeDisplay?: boolean } = {},
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    made_for_kids: v.made_for_kids,
    embeddable: v.embeddable,
    disable_comments: v.disable_comments,
    rating_disabled: v.rating_disabled,
    notify_subscribers: v.notify_subscribers,
  };
  if (v.title_template.trim()) out.title_template = v.title_template;
  if (v.description_template.trim()) out.description_template = v.description_template;
  if (v.privacy) out.privacy = v.privacy;
  if (v.category_id.trim()) out.category_id = v.category_id;
  if (v.playlist_id.trim()) out.playlist_id = v.playlist_id;
  if (v.thumbnail_name.trim()) out.thumbnail_name = v.thumbnail_name;
  if (v.tags.length > 0) out.tags = v.tags;
  if (v.license) out.license = v.license;
  if (v.default_language.trim()) out.default_language = v.default_language;
  if (v.publish_at) out.publish_at = new Date(v.publish_at).toISOString();
  if (opts.includeDisplay) {
    const td = toDisplayPayload(v.topics_display, "topics");
    if (td) out.topics_display = td;
    const qd = toDisplayPayload(v.questions_display, "questions");
    if (qd) out.questions_display = qd;
  }
  return out;
}

export function vkFieldsFromApi(
  raw: unknown,
  defaults: DisplayConfigDefaultsPayload = DISPLAY_CONFIG_PLACEHOLDER,
): VkFieldsValue {
  const base = { ...DEFAULT_VK_FIELDS };
  if (!raw || typeof raw !== "object") return base;
  const o = raw as Record<string, unknown>;
  return {
    ...base,
    title_template:       o.title_template       != null ? String(o.title_template)       : "",
    description_template: o.description_template != null ? String(o.description_template) : "",
    privacy_view:    o.privacy_view    != null ? String(o.privacy_view)    : "",
    privacy_comment: o.privacy_comment != null ? String(o.privacy_comment) : "",
    group_id:        o.group_id    != null ? String(o.group_id)    : "",
    album_id:        o.album_id    != null ? String(o.album_id)    : "",
    thumbnail_name:  o.thumbnail_name != null ? String(o.thumbnail_name) : "",
    wallpost:        Boolean(o.wallpost),
    repeat:          Boolean(o.repeat),
    compression:     Boolean(o.compression),
    disable_comments: Boolean(o.disable_comments),
    topics_display:    fromDisplayPayload(o.topics_display, "topics", defaults),
    questions_display: fromDisplayPayload(o.questions_display, "questions", defaults),
  };
}

export function vkFieldsToApi(
  v: VkFieldsValue,
  opts: { includeDisplay?: boolean; sparseBools?: boolean } = {},
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const boolFields = ["wallpost", "repeat", "compression", "disable_comments"] as const;
  for (const key of boolFields) {
    if (opts.sparseBools) {
      if (v[key]) out[key] = true;
    } else {
      out[key] = v[key];
    }
  }
  if (v.title_template.trim()) out.title_template = v.title_template;
  if (v.description_template.trim()) out.description_template = v.description_template;
  if (v.privacy_view !== "") out.privacy_view = Number(v.privacy_view);
  if (v.privacy_comment !== "") out.privacy_comment = Number(v.privacy_comment);
  if (v.group_id.trim()) out.group_id = Number(v.group_id);
  if (v.album_id.trim()) out.album_id = v.album_id;
  if (v.thumbnail_name.trim()) out.thumbnail_name = v.thumbnail_name;
  if (opts.includeDisplay) {
    const td = toDisplayPayload(v.topics_display, "topics");
    if (td) out.topics_display = td;
    const qd = toDisplayPayload(v.questions_display, "questions");
    if (qd) out.questions_display = qd;
  }
  return out;
}

function yandexExtraFromApi(raw: unknown): YandexExtraFile {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_YANDEX_EXTRA_FILE };
  const o = raw as Record<string, unknown>;
  return {
    enabled: true,
    filename_template:    o.filename_template    != null ? String(o.filename_template)    : "",
    folder_path_template: o.folder_path_template != null ? String(o.folder_path_template) : "",
  };
}

function yandexDescriptionTxtFromApi(raw: unknown): YandexDescriptionTxt {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_YANDEX_DESCRIPTION_TXT };
  const o = raw as Record<string, unknown>;
  return {
    ...yandexExtraFromApi(raw),
    content_template: o.content_template != null ? String(o.content_template) : "",
  };
}

/** Sidecar payload: presence enables the upload; omit empty templates. */
function yandexExtraToApi(f: YandexExtraFile, content?: string): Record<string, unknown> | undefined {
  if (!f.enabled) return undefined;
  const out: Record<string, unknown> = {};
  if (f.filename_template.trim()) out.filename_template = f.filename_template;
  if (f.folder_path_template.trim()) out.folder_path_template = f.folder_path_template;
  if (content != null && content.trim()) out.content_template = content;
  return out;
}

export function yandexFieldsFromApi(raw: unknown): YandexDiskFieldsValue {
  const base = { ...DEFAULT_YANDEX_DISK_FIELDS };
  if (!raw || typeof raw !== "object") return base;
  const o = raw as Record<string, unknown>;
  return {
    ...base,
    folder_path_template: o.folder_path_template != null ? String(o.folder_path_template) : "",
    filename_template:    o.filename_template    != null ? String(o.filename_template)    : "",
    title_template:       o.title_template       != null ? String(o.title_template)       : "",
    description_template: o.description_template != null ? String(o.description_template) : "",
    overwrite: Boolean(o.overwrite),
    publish:   Boolean(o.publish),
    subtitles_srt:   yandexExtraFromApi(o.subtitles_srt),
    subtitles_vtt:   yandexExtraFromApi(o.subtitles_vtt),
    transcription:   yandexExtraFromApi(o.transcription),
    description_txt: yandexDescriptionTxtFromApi(o.description_txt),
  };
}

export function yandexFieldsToApi(
  v: YandexDiskFieldsValue,
  opts: { includeExtended?: boolean } = {},
): Record<string, unknown> {
  const out: Record<string, unknown> = { overwrite: v.overwrite, publish: v.publish };
  if (v.folder_path_template.trim()) out.folder_path_template = v.folder_path_template;
  if (v.filename_template.trim()) out.filename_template = v.filename_template;
  if (opts.includeExtended) {
    if (v.title_template.trim()) out.title_template = v.title_template;
    if (v.description_template.trim()) out.description_template = v.description_template;
    const srt = yandexExtraToApi(v.subtitles_srt);
    if (srt) out.subtitles_srt = srt;
    const vtt = yandexExtraToApi(v.subtitles_vtt);
    if (vtt) out.subtitles_vtt = vtt;
    const tr = yandexExtraToApi(v.transcription);
    if (tr) out.transcription = tr;
    const dtxt = yandexExtraToApi(v.description_txt, v.description_txt.content_template);
    if (dtxt) out.description_txt = dtxt;
  }
  return out;
}
