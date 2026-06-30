"use client";

import { Fragment, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { TagInput } from "@/components/ui/tag-input";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { NativeSelect } from "@/components/ui/native-select";
import { ThumbnailPicker } from "@/components/platforms/thumbnail-picker";
import { PlatformToggle } from "@/components/platforms/platform-toggle";
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
export { PlatformToggle };

// ---------------------------------------------------------------------------
// Jinja2 variable definitions (shown in autocomplete dropdown)
// ---------------------------------------------------------------------------

const JINJA_VARS: { value: string; description: string }[] = [
  { value: "display_name",       description: "Recording title" },
  { value: "topics",             description: "All topics block" },
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
}

export function TemplateField({
  label,
  value,
  onChange,
  multiline = false,
  placeholder,
  rows = 1,
}: TemplateFieldProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fieldId = useId();
  const listboxId = useId();
  const [acOpen, setAcOpen] = useState(false);
  const [acQuery, setAcQuery] = useState("");

  const filtered = useMemo(
    () =>
      JINJA_VARS.filter((v) =>
        v.value.toLowerCase().startsWith(acQuery.toLowerCase()),
      ),
    [acQuery],
  );

  useLayoutEffect(() => {
    if (!multiline || !textareaRef.current) return;
    syncMultilineHeight(textareaRef.current);
  }, [value, multiline]);

  function updateAcFromCaret(text: string, caret: number) {
    const before = text.slice(0, caret);
    const match = before.match(/\{\{\s*(\w*)$/);
    if (match) {
      setAcOpen(true);
      setAcQuery(match[1]);
    } else {
      setAcOpen(false);
      setAcQuery("");
    }
  }

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
    updateAcFromCaret(next, ta.selectionStart);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !multiline) {
      e.preventDefault();
    }
  }

  function handleScroll(e: React.UIEvent<HTMLTextAreaElement>) {
    const overlay = overlayRef.current;
    if (!overlay) return;
    overlay.scrollTop = e.currentTarget.scrollTop;
    overlay.scrollLeft = e.currentTarget.scrollLeft;
  }

  function handleBlur() {
    blurTimer.current = setTimeout(() => setAcOpen(false), 150);
  }

  function insertVar(varName: string) {
    const ta = textareaRef.current;
    if (!ta) return;
    const caret = ta.selectionStart;
    const before = value.slice(0, caret);
    const after = value.slice(caret);
    const newBefore = before.replace(/\{\{\s*\w*$/, `{{ ${varName} }}`);
    const newVal = newBefore + after;
    onChange(newVal);
    setAcOpen(false);
    setAcQuery("");
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(newBefore.length, newBefore.length);
      }
    });
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
      <label htmlFor={fieldId} className={FILTER_LABEL}>
        {label}
      </label>
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
          onSelect={(e) => updateAcFromCaret(value, e.currentTarget.selectionStart)}
          rows={multiline ? rows : 1}
          spellCheck={false}
          aria-autocomplete="list"
          aria-controls={acOpen ? listboxId : undefined}
          placeholder={placeholder}
          className={cn(
            fieldSurface,
            "relative z-10 m-0 block w-full appearance-none bg-transparent text-transparent caret-gray-900 placeholder:text-muted-foreground",
            multiline
              ? "resize-y overflow-x-hidden whitespace-pre-wrap break-words"
              : "resize-none overflow-x-auto overflow-y-hidden whitespace-pre",
          )}
        />

        {acOpen && filtered.length > 0 && (
          <ul
            id={listboxId}
            role="listbox"
            className="absolute left-0 right-0 top-full z-50 mt-1 max-h-44 overflow-y-auto rounded-xl border border-border bg-card shadow-lg"
          >
            {filtered.map((v) => (
              <li key={v.value} role="option" aria-selected={false}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    if (blurTimer.current) clearTimeout(blurTimer.current);
                    insertVar(v.value);
                  }}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-muted"
                >
                  <code className="shrink-0 font-mono text-xs text-primary">{`{{ ${v.value} }}`}</code>
                  <span className="text-xs text-muted-foreground">{v.description}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <Info size={11} className="shrink-0" />
        Jinja2 — type <code className="font-mono">{"{{ "}</code> to autocomplete variables
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Layout helpers — keep dense forms friendly: collapsible advanced sections and
// a 2-column toggle grid so switches sit next to their labels.
// ---------------------------------------------------------------------------

function Disclosure({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-background">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-secondary-foreground hover:text-foreground"
      >
        {title}
        <ChevronDown size={15} className={cn("shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="space-y-4 border-t border-border px-4 pb-4 pt-3">{children}</div>}
    </div>
  );
}

/** Lay out toggle rows in two columns so the switch hugs its label. */
function ToggleGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">{children}</div>;
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
        <PlatformToggle
          label="Made for kids"
          checked={value.made_for_kids}
          onChange={(v) => onChange({ made_for_kids: v })}
        />
      )}

      {showExtended && (
        <Disclosure title="Advanced">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
              <input
                type="text"
                value={value.default_language}
                onChange={(e) => onChange({ default_language: e.target.value })}
                placeholder="ru"
                className={FILTER_CONTROL}
              />
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
            <p className="text-[11px] text-muted-foreground">Leave empty to publish per the privacy setting.</p>
          </div>
          <ToggleGrid>
            <PlatformToggle label="Embeddable" checked={value.embeddable} onChange={(v) => onChange({ embeddable: v })} />
            <PlatformToggle label="Notify subscribers" checked={value.notify_subscribers} onChange={(v) => onChange({ notify_subscribers: v })} />
            <PlatformToggle label="Disable comments" checked={value.disable_comments} onChange={(v) => onChange({ disable_comments: v })} />
            <PlatformToggle label="Disable ratings" checked={value.rating_disabled} onChange={(v) => onChange({ rating_disabled: v })} />
            <PlatformToggle label="Made for kids" checked={value.made_for_kids} onChange={(v) => onChange({ made_for_kids: v })} />
          </ToggleGrid>
        </Disclosure>
      )}

      {showDisplayConfig && (
        <>
          <DisplayConfigFields
            label="Topics in description"
            kind="topics"
            value={value.topics_display}
            onChange={(patch) => onChange({ topics_display: { ...value.topics_display, ...patch } })}
          />
          <DisplayConfigFields
            label="Questions in description"
            kind="questions"
            value={value.questions_display}
            onChange={(patch) => onChange({ questions_display: { ...value.questions_display, ...patch } })}
          />
        </>
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
        <PlatformToggle
          label="Post to wall"
          checked={value.wallpost}
          onChange={(v) => onChange({ wallpost: v })}
        />
      )}

      {showExtended && (
        <Disclosure title="Advanced">
          <ToggleGrid>
            <PlatformToggle label="Loop playback" checked={value.repeat} onChange={(v) => onChange({ repeat: v })} />
            <PlatformToggle label="VK-side compression" checked={value.compression} onChange={(v) => onChange({ compression: v })} />
            <PlatformToggle label="Disable comments" checked={value.disable_comments} onChange={(v) => onChange({ disable_comments: v })} />
          </ToggleGrid>
        </Disclosure>
      )}

      {showDisplayConfig && (
        <>
          <DisplayConfigFields
            label="Topics in description"
            kind="topics"
            value={value.topics_display}
            onChange={(patch) => onChange({ topics_display: { ...value.topics_display, ...patch } })}
          />
          <DisplayConfigFields
            label="Questions in description"
            kind="questions"
            value={value.questions_display}
            onChange={(patch) => onChange({ questions_display: { ...value.questions_display, ...patch } })}
          />
        </>
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
}: {
  label: string;
  value: YandexExtraFile | YandexDescriptionTxt;
  onChange: (patch: Partial<YandexDescriptionTxt>) => void;
  withContent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-background px-4 py-3">
      <PlatformToggle label={label} checked={value.enabled} onChange={(v) => onChange({ enabled: v })} />
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
}: {
  value: YandexDiskFieldsValue;
  onChange: (patch: Partial<YandexDiskFieldsValue>) => void;
  /** Presets only: title/description templates + sidecar files (template-level
   *  YandexDiskMetadataConfig has none of these). */
  showExtended?: boolean;
}) {
  return (
    <div className="space-y-4">
      <TemplateField
        label="Folder path template"
        value={value.folder_path_template}
        onChange={(v) => onChange({ folder_path_template: v })}
        placeholder="/Video/{{ display_name }}"
      />
      <TemplateField
        label="Filename template"
        value={value.filename_template}
        onChange={(v) => onChange({ filename_template: v })}
        placeholder="{{ display_name }}.mp4"
      />
      {showExtended && (
        <>
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
        </>
      )}
      <div className="divide-y divide-muted">
        <PlatformToggle
          label="Overwrite existing"
          checked={value.overwrite}
          onChange={(v) => onChange({ overwrite: v })}
        />
        <PlatformToggle
          label="Publish publicly"
          checked={value.publish}
          onChange={(v) => onChange({ publish: v })}
        />
      </div>

      {showExtended && (
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Extra files</p>
          <YandexExtraFileBlock
            label="Upload subtitles (.srt)"
            value={value.subtitles_srt}
            onChange={(patch) => onChange({ subtitles_srt: { ...value.subtitles_srt, ...patch } })}
          />
          <YandexExtraFileBlock
            label="Upload subtitles (.vtt)"
            value={value.subtitles_vtt}
            onChange={(patch) => onChange({ subtitles_vtt: { ...value.subtitles_vtt, ...patch } })}
          />
          <YandexExtraFileBlock
            label="Upload transcription (.txt)"
            value={value.transcription}
            onChange={(patch) => onChange({ transcription: { ...value.transcription, ...patch } })}
          />
          <YandexExtraFileBlock
            label="Upload description (.txt)"
            value={value.description_txt}
            onChange={(patch) => onChange({ description_txt: { ...value.description_txt, ...patch } })}
            withContent
          />
        </div>
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
