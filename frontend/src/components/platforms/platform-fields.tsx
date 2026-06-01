"use client";

import { Fragment, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { TagInput } from "@/components/ui/tag-input";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { NativeSelect } from "@/components/ui/native-select";
import { ThumbnailPicker } from "@/components/platforms/thumbnail-picker";

// ---------------------------------------------------------------------------
// Jinja2 variable definitions (shown in autocomplete dropdown)
// ---------------------------------------------------------------------------

const JINJA_VARS: { value: string; description: string }[] = [
  { value: "display_name",    description: "Recording title" },
  { value: "date",            description: "Record date" },
  { value: "topic",           description: "Primary topic" },
  { value: "topics",          description: "All topics block" },
  { value: "summary",         description: "Text summary" },
  { value: "themes",          description: "Comma-separated themes" },
  { value: "duration_hm",     description: "Duration HH:MM:SS" },
  { value: "questions",       description: "Self-check questions" },
  { value: "record_date",     description: "Record date (locale)" },
  { value: "publish_date",    description: "Publish date" },
  { value: "record_datetime", description: "Date + time" },
  { value: "record_time_hm",  description: "Time HH:MM" },
  { value: "title",           description: "Rendered title (use in desc)" },
  { value: "recording_id",    description: "Recording ID" },
  { value: "duration",        description: "Duration in seconds" },
];

// ---------------------------------------------------------------------------
// TemplateField — textarea-backed editor with overlay-based Jinja2 highlighting.
//
// The previous implementation used contentEditable + innerHTML which is a
// classic XSS surface (any future relaxation of the escape step becomes an
// injection point) and inconsistent across browsers. This version uses a
// hidden-text textarea with a React-rendered overlay div — no string→HTML.
// ---------------------------------------------------------------------------

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
      <span key={`v-${key++}`} className="font-medium text-[#224C87]">
        {match[0]}
      </span>,
    );
    lastIndex = TOKEN_REGEX.lastIndex;
  }
  if (lastIndex < text.length) {
    out.push(<Fragment key={`t-${key++}`}>{text.slice(lastIndex)}</Fragment>);
  }
  // Trailing newlines aren't measured by inline content in the overlay div —
  // append a zero-width space so the last empty line stays visible.
  if (text.endsWith("\n")) {
    out.push(<Fragment key="trail">{"​"}</Fragment>);
  }
  return out;
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
  rows = 3,
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
      // Strip newlines so a paste of multi-line content doesn't break the
      // single-line layout. Replace with a space to preserve word boundaries.
      const stripped = next.replace(/\r?\n/g, " ");
      if (stripped !== next) {
        const caret = ta.selectionStart;
        next = stripped;
        // Schedule caret restoration after React applies the new value.
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
    // Restore focus + place caret right after the inserted token.
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(newBefore.length, newBefore.length);
      }
    });
  }

  const sharedTextStyle = "px-3 py-2 text-sm leading-[1.4]";
  const fontClass = multiline ? "font-mono text-xs leading-[1.5]" : "";

  return (
    <div className="space-y-1">
      <label htmlFor={fieldId} className={FILTER_LABEL}>
        {label}
      </label>
      <div className="relative">
        {/* Overlay: renders highlighted tokens. aria-hidden — textarea is the
            accessible/keyboardable surface. Padding + font must match the
            textarea exactly so glyphs align under the (invisible) text. */}
        <div
          ref={overlayRef}
          aria-hidden="true"
          className={cn(
            FILTER_CONTROL,
            sharedTextStyle,
            fontClass,
            "pointer-events-none absolute inset-0 select-none overflow-hidden whitespace-pre-wrap break-words text-gray-900",
            multiline ? "" : "whitespace-pre",
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
          // The textarea is the source of truth and the focusable surface.
          // `text-transparent` hides the typed text so only the overlay is
          // visible; `caret-current` shows the caret so the user sees where
          // they're typing.
          className={cn(
            FILTER_CONTROL,
            sharedTextStyle,
            fontClass,
            "relative z-10 block w-full resize-none bg-transparent text-transparent caret-current placeholder:text-gray-400",
            multiline ? "whitespace-pre-wrap break-words" : "whitespace-pre overflow-x-auto",
          )}
          style={multiline ? { minHeight: "4.5rem" } : undefined}
        />

        {acOpen && filtered.length > 0 && (
          <ul
            id={listboxId}
            role="listbox"
            className="absolute left-0 right-0 top-full z-50 mt-1 max-h-44 overflow-y-auto rounded-xl border border-[#D9D9D9] bg-white shadow-lg"
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
                  className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-gray-50"
                >
                  <code className="shrink-0 font-mono text-xs text-[#224C87]">{`{{ ${v.value} }}`}</code>
                  <span className="text-xs text-gray-400">{v.description}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="flex items-center gap-1 text-[11px] text-gray-400">
        <Info size={11} className="shrink-0" />
        Jinja2 — type <code className="font-mono">{"{{ "}</code> to autocomplete variables
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PlatformToggle — shared boolean toggle row used inside platform forms
// ---------------------------------------------------------------------------

export function PlatformToggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between py-1.5">
      <span className="text-sm text-gray-700">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          checked ? "bg-[#224C87]" : "bg-gray-200"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all duration-150",
            checked ? "left-[1.125rem]" : "left-0.5"
          )}
        />
      </button>
    </label>
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
};

const YT_PRIVACY_OPTIONS = [
  { value: "",         label: "— default —" },
  { value: "public",   label: "Public" },
  { value: "unlisted", label: "Unlisted" },
  { value: "private",  label: "Private" },
];

export function YouTubeFields({
  value,
  onChange,
  showThumbnail = false,
  showMadeForKids = false,
}: {
  value: YouTubeFieldsValue;
  onChange: (patch: Partial<YouTubeFieldsValue>) => void;
  showThumbnail?: boolean;
  showMadeForKids?: boolean;
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
        rows={4}
        placeholder={"Recording from {{ date }}\n\n{{ topics }}"}
      />
      <div className="grid grid-cols-2 gap-3">
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
      {showMadeForKids && (
        <PlatformToggle
          label="Made for kids"
          checked={value.made_for_kids}
          onChange={(v) => onChange({ made_for_kids: v })}
        />
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
}: {
  value: VkFieldsValue;
  onChange: (patch: Partial<VkFieldsValue>) => void;
  showThumbnail?: boolean;
  showPrivacyComment?: boolean;
  showWallpost?: boolean;
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
        rows={3}
        placeholder={"Recording from {{ date }}\n\n{{ topics }}"}
      />
      <div className="grid grid-cols-2 gap-3">
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
      <div className={cn("grid gap-3", showPrivacyComment ? "grid-cols-2" : "grid-cols-1 max-w-[50%]")}>
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Yandex Disk fields
// ---------------------------------------------------------------------------

export interface YandexDiskFieldsValue {
  folder_path_template: string;
  filename_template: string;
  overwrite: boolean;
  publish: boolean;
}

export const DEFAULT_YANDEX_DISK_FIELDS: YandexDiskFieldsValue = {
  folder_path_template: "",
  filename_template: "",
  overwrite: false,
  publish: false,
};

export function YandexDiskFields({
  value,
  onChange,
}: {
  value: YandexDiskFieldsValue;
  onChange: (patch: Partial<YandexDiskFieldsValue>) => void;
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
      <div className="divide-y divide-[#F5F5F5]">
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
    </div>
  );
}
