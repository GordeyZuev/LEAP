"use client";

import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, X, Plus, Code2, Loader2, Pencil, Search } from "lucide-react";
import { cn, scrollIntoViewWithin } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { TemplateField } from "@/components/platforms/platform-fields";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TopicTimestamp {
  topic: string;
  start: number;
  end?: number;
}

export interface TopicVersion {
  id?: string;
  main_topics?: string[];
  summary?: string;
  description?: string;
  questions?: string[];
  topic_timestamps?: TopicTimestamp[];
  manually_edited?: boolean;
}

export type AIContentSection = "topics" | "summary" | "chapters" | "questions";

interface AIContentEditorProps {
  recordingId: number;
  version: TopicVersion;
  onUpdated: () => void;
  onSeek?: (time: number) => void;
  /** Current player time — used to seed a new chapter. */
  getCurrentTime?: () => number;
  /** Playback length in seconds; new chapter times must be inside (0, duration). */
  getDuration?: () => number;
  activeChapterIdx?: number;
  readOnly?: boolean;
  /** When set, only these blocks render. Omit for the full editor layout. */
  sections?: AIContentSection[];
  chaptersListClassName?: string;
  /** Share-page sidebar: tab rail carries section names; drop duplicate labels and inner scroll. */
  embeddedInPanel?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function hasJinja(text: string) {
  return text.includes("{{");
}

function formatTimecode(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function parseTimecode(value: string): number | null {
  const parts = value.trim().split(":").map((p) => Number(p));
  if (parts.length === 0 || parts.some((n) => !Number.isFinite(n) || n < 0)) return null;
  if (parts.length === 1) return Math.floor(parts[0]);
  if (parts.length === 2) return Math.floor(parts[0] * 60 + parts[1]);
  if (parts.length === 3) return Math.floor(parts[0] * 3600 + parts[1] * 60 + parts[2]);
  return null;
}

// ---------------------------------------------------------------------------
// Section label
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
    </p>
  );
}

const SEARCH_INPUT =
  "w-full rounded-xl border border-input bg-background py-2 pl-8 pr-8 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30";

const ADD_PILL =
  "flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";

const EDIT_AFFORDANCE =
  "inline-flex size-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-opacity hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:opacity-50";

const EDIT_AFFORDANCE_HOVER =
  "[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 [@media(hover:hover)]:focus-visible:opacity-100";

// ---------------------------------------------------------------------------
// ChapterItem — timecode always seekable; title editable via hover pencil
// ---------------------------------------------------------------------------

function ChapterItem({
  item,
  isActive,
  canRename,
  onSeek,
  onSave,
  onDelete,
  disabled,
  itemRef,
  wrapLabels = false,
}: {
  item: TopicTimestamp;
  isActive: boolean;
  canRename: boolean;
  onSeek: (t: number) => void;
  onSave: (topic: string) => void;
  onDelete?: () => void;
  disabled?: boolean;
  itemRef?: (el: HTMLButtonElement | null) => void;
  wrapLabels?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.topic);

  function commit() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== item.topic) onSave(trimmed);
    setEditing(false);
  }

  function cancelEdit() {
    setDraft(item.topic);
    setEditing(false);
  }

  function startEdit() {
    setDraft(item.topic);
    setEditing(true);
  }

  const dot = (
    <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", isActive ? "bg-primary" : "bg-border")} />
  );
  const time = (
    <span
      className={cn(
        "w-[3.25rem] shrink-0 font-mono text-xs leading-5 tabular-nums transition-colors group-hover:text-primary",
        isActive ? "font-semibold text-primary" : "text-muted-foreground",
      )}
    >
      {formatTimecode(item.start)}
    </span>
  );

  if (editing && canRename) {
    return (
      <div className="flex w-full items-start gap-3 rounded-lg px-2 py-1.5">
        <span className="flex shrink-0 items-center gap-3 pt-1.5">
          {dot}
          <button
            type="button"
            onClick={() => onSeek(item.start)}
            className={cn(
              "text-left font-mono text-xs leading-5 tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
              isActive ? "font-semibold text-primary" : "text-muted-foreground hover:text-primary",
            )}
          >
            {formatTimecode(item.start)}
          </button>
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <textarea
            autoFocus
            aria-label="Chapter title"
            value={draft}
            rows={2}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); }
              if (e.key === "Escape") cancelEdit();
            }}
            disabled={disabled}
            className="min-w-0 w-full resize-y rounded-lg border border-input bg-card px-2 py-1.5 text-sm leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={commit}
              disabled={disabled || !draft.trim()}
              className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Check size={11} /> Save
            </button>
            <button
              type="button"
              onClick={cancelEdit}
              className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <X size={11} /> Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!canRename) {
    return (
      <div
        className={cn(
          "group flex w-full rounded-lg transition-colors",
          isActive ? "bg-primary/6" : "hover:bg-muted/20",
        )}
      >
        <button
          ref={itemRef}
          type="button"
          onClick={() => onSeek(item.start)}
          className="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          <span className="flex shrink-0 items-center gap-3">
            {dot}
            <span className={cn("w-[3.25rem] font-mono text-xs leading-5 tabular-nums transition-colors group-hover:text-primary", isActive ? "font-semibold text-primary" : "text-muted-foreground")}>
              {formatTimecode(item.start)}
            </span>
          </span>
          <span
            className={cn(
              "min-w-0 flex-1 text-sm leading-5",
              wrapLabels ? "break-words" : "truncate",
              isActive ? "font-medium text-foreground" : "text-secondary-foreground",
            )}
          >
            {item.topic}
          </span>
        </button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group relative flex w-full items-center rounded-lg transition-colors",
        isActive ? "bg-primary/6" : "hover:bg-muted/20",
      )}
    >
      <button
        ref={itemRef}
        type="button"
        onClick={() => onSeek(item.start)}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
      >
        <span className="flex shrink-0 items-center gap-3">
          {dot}
          {time}
        </span>
        <span
          className={cn(
            "min-w-0 flex-1 pe-20 text-sm leading-5 break-words",
            isActive ? "font-medium text-foreground" : "text-secondary-foreground",
          )}
        >
          {item.topic}
        </span>
      </button>
      <div className="absolute right-0.5 top-1/2 flex -translate-y-1/2">
        <button
          type="button"
          onClick={startEdit}
          disabled={disabled}
          aria-label={`Rename chapter “${item.topic}”`}
          className={cn(EDIT_AFFORDANCE, EDIT_AFFORDANCE_HOVER)}
        >
          <Pencil size={14} />
        </button>
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            disabled={disabled}
            aria-label={`Delete chapter “${item.topic}”`}
            className={cn(EDIT_AFFORDANCE, "text-muted-foreground/50 hover:text-danger-fg", EDIT_AFFORDANCE_HOVER)}
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AIContentEditor({
  recordingId,
  version,
  onUpdated,
  onSeek,
  getCurrentTime,
  getDuration,
  activeChapterIdx = -1,
  readOnly = false,
  sections,
  chaptersListClassName,
  embeddedInPanel = false,
}: AIContentEditorProps) {
  const canEdit = !readOnly;

  // -- local state (optimistic)
  const [mainTopics, setMainTopics] = useState<string[]>(version.main_topics ?? []);
  const [topicTimestamps, setTopicTimestamps] = useState<TopicTimestamp[]>(version.topic_timestamps ?? []);
  const [questions, setQuestions] = useState<string[]>(version.questions ?? []);

  // -- inline edit state (topic title)
  const [editingTopicIdx, setEditingTopicIdx] = useState<number | null>(null);
  const [topicDraft, setTopicDraft] = useState("");
  const [newTopic, setNewTopic] = useState("");
  const [addingTopic, setAddingTopic] = useState(false);

  // -- inline edit state (questions)
  const [editingQuestionIdx, setEditingQuestionIdx] = useState<number | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [newQuestion, setNewQuestion] = useState("");

  // -- summary edit state
  const [summaryEditing, setSummaryEditing] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState(version.summary ?? "");
  const [summaryIsTemplate, setSummaryIsTemplate] = useState(() => hasJinja(version.summary ?? ""));
  const [renderLoading, setRenderLoading] = useState(false);

  const newQuestionRef = useRef<HTMLTextAreaElement>(null);
  const chaptersRef = useRef<HTMLDivElement>(null);
  const chapterItemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const [chapterQuery, setChapterQuery] = useState("");
  const [addingChapter, setAddingChapter] = useState(false);
  const [newChapterTime, setNewChapterTime] = useState("");
  const [newChapterTitle, setNewChapterTitle] = useState("");
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<
    | { kind: "chapter"; index: number }
    | { kind: "question"; index: number }
    | { kind: "theme"; index: number }
    | null
  >(null);
  const chapterNeedle = chapterQuery.trim().toLowerCase();
  const filteredChapters = useMemo(() => {
    if (!chapterNeedle) return topicTimestamps.map((item, index) => ({ item, index }));
    return topicTimestamps
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => item.topic.toLowerCase().includes(chapterNeedle));
  }, [topicTimestamps, chapterNeedle]);

  // Following playback belongs here, not in the pages: this component owns the
  // chapter scroller, and `scrollIntoView` from outside would scroll the page
  // itself, dragging the reader back to the list every time a chapter changes.
  useEffect(() => {
    if (activeChapterIdx < 0 || chapterQuery.trim()) return;
    scrollIntoViewWithin(chaptersRef.current, chapterItemRefs.current.get(activeChapterIdx) ?? null);
  }, [activeChapterIdx, chapterQuery]);

  // Reset editor fields when the recording or version identity changes. Same-version
  // refetch must not wipe an in-progress edit — store the key, not the payload.
  const versionKey = `${recordingId}:${version.id ?? ""}`;
  const [syncedVersionKey, setSyncedVersionKey] = useState(versionKey);
  if (syncedVersionKey !== versionKey) {
    setSyncedVersionKey(versionKey);
    setMainTopics(version.main_topics ?? []);
    setTopicTimestamps(version.topic_timestamps ?? []);
    setQuestions(version.questions ?? []);
    setEditingTopicIdx(null);
    setAddingTopic(false);
    setNewTopic("");
    setEditingQuestionIdx(null);
    setAddingQuestion(false);
    setNewQuestion("");
    setSummaryEditing(false);
    setSummaryDraft(version.summary ?? "");
    setSummaryIsTemplate(hasJinja(version.summary ?? ""));
    setChapterQuery("");
    setAddingChapter(false);
    setPendingDelete(null);
  }

  const updateTopics = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      apiClient.patch(`/recordings/${recordingId}/topics`, data),
    onSuccess: onUpdated,
  });

  const renderTemplate = useCallback(async (template: string): Promise<string> => {
    const res = await apiClient.post(`/recordings/${recordingId}/topics/render`, { template });
    return (res.data as { rendered: string }).rendered;
  }, [recordingId]);

  const isMutating = updateTopics.isPending;

  // `readOnly` is the public share page, which has no session. apiClient's 401
  // interceptor redirects to /login, so a save that slipped through would throw
  // an anonymous visitor out of the page they were sent a link to. Every write
  // goes through here so no future edit can reintroduce that path.
  const persist = (data: Record<string, unknown>) => {
    if (readOnly) return;
    updateTopics.mutate(data);
  };

  function persistAsync(data: Record<string, unknown>) {
    if (readOnly) return;
    return updateTopics.mutateAsync(data);
  }

  function videoDuration(): number {
    const d = getDuration?.() ?? 0;
    return Number.isFinite(d) && d > 0 ? d : 0;
  }

  function chapterTimeError(raw: string): string | null {
    const start = parseTimecode(raw);
    if (start === null) return "Enter a time like 1:23";
    const duration = videoDuration();
    if (!(duration > 0)) return "Video duration is not available yet";
    if (start <= 0 || start >= duration) {
      return `Time must be after 0:00 and before ${formatTimecode(Math.floor(duration))}`;
    }
    return null;
  }

  // -- topic handlers
  function saveMainTopics(updated: string[]) {
    setMainTopics(updated);
    persist({ main_topics: updated });
  }

  function startTopicEdit(i: number) {
    setAddingTopic(false);
    setTopicDraft(mainTopics[i] ?? "");
    setEditingTopicIdx(i);
  }

  function commitTopic(i: number) {
    const trimmed = topicDraft.trim();
    if (trimmed && trimmed !== mainTopics[i]) {
      saveMainTopics(mainTopics.map((t, j) => (j === i ? trimmed : t)));
    }
    setEditingTopicIdx(null);
  }

  function addTopic() {
    const trimmed = newTopic.trim();
    if (!trimmed) return;
    saveMainTopics([...mainTopics, trimmed]);
    setNewTopic("");
    setAddingTopic(false);
  }

  function openAddTopic() {
    if (readOnly) return;
    setEditingTopicIdx(null);
    setNewTopic("");
    setAddingTopic(true);
  }

  // -- chapter handlers
  function saveChapterTopic(index: number, topic: string) {
    const updated = topicTimestamps.map((t, i) => (i === index ? { ...t, topic } : t));
    setTopicTimestamps(updated);
    persist({ topic_timestamps: updated });
  }

  function deleteChapter(index: number) {
    const next = topicTimestamps.filter((_, i) => i !== index);
    setTopicTimestamps(next);
    persist({ topic_timestamps: next });
  }

  function openAddChapter() {
    if (readOnly) return;
    const duration = videoDuration();
    const now = Math.floor(getCurrentTime?.() ?? 0);
    const seed =
      duration > 0 ? Math.min(Math.max(now, 1), Math.max(1, Math.floor(duration) - 1)) : Math.max(now, 1);
    setNewChapterTime(formatTimecode(seed));
    setNewChapterTitle("");
    setAddingChapter(true);
  }

  function addChapter() {
    const start = parseTimecode(newChapterTime);
    const topic = newChapterTitle.trim();
    if (!topic || chapterTimeError(newChapterTime) || start === null) return;
    const next = [...topicTimestamps, { topic, start }];
    next.sort((a, b) => a.start - b.start);
    setTopicTimestamps(next);
    persist({ topic_timestamps: next });
    setNewChapterTitle("");
    setAddingChapter(false);
  }

  // -- summary handlers
  function openSummaryEdit() {
    if (readOnly) return;
    setSummaryDraft(version.summary ?? "");
    setSummaryIsTemplate(hasJinja(version.summary ?? ""));
    setSummaryEditing(true);
  }

  async function saveSummary() {
    try {
      await persistAsync({ summary: summaryDraft });
      setSummaryEditing(false);
    } catch {
      // error visible via updateTopics.isError; keep edit open
    }
  }

  async function convertSummaryToText() {
    setRenderLoading(true);
    try {
      const rendered = await renderTemplate(summaryDraft);
      setSummaryDraft(rendered);
      setSummaryIsTemplate(false);
      await persistAsync({ summary: rendered });
      setSummaryEditing(false);
    } catch {
      // keep edit open on failure
    } finally {
      setRenderLoading(false);
    }
  }

  // -- question handlers
  function saveQuestions(updated: string[]) {
    setQuestions(updated);
    persist({ questions: updated });
  }

  function commitQuestion(i: number) {
    const trimmed = questionDraft.trim();
    if (trimmed && trimmed !== questions[i]) {
      saveQuestions(questions.map((q, j) => (j === i ? trimmed : q)));
    }
    setEditingQuestionIdx(null);
  }

  function addQuestion() {
    const trimmed = newQuestion.trim();
    if (!trimmed) return;
    saveQuestions([...questions, trimmed]);
    setNewQuestion("");
    setAddingQuestion(false);
  }

  function openAddQuestion() {
    if (readOnly) return;
    setAddingQuestion(true);
  }

  // -- guard
  const hasTopics = mainTopics.length > 0;
  const hasChapters = topicTimestamps.length > 0;
  const hasSummary = !!version.summary;
  const hasQuestions = questions.length > 0;

  const showSection = (section: AIContentSection) =>
    !sections || sections.includes(section);

  const visibleHasTopics = showSection("topics") && (hasTopics || canEdit);
  const visibleHasChapters = showSection("chapters") && (hasChapters || !readOnly);
  const visibleHasSummary = showSection("summary") && hasSummary;
  const visibleHasQuestions = showSection("questions") && (hasQuestions || !readOnly);

  if (readOnly && !visibleHasTopics && !visibleHasChapters && !visibleHasSummary && !visibleHasQuestions) return null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const hideEmbeddedTopicTitle = embeddedInPanel && readOnly;
  const showTopicHeaderBlock = visibleHasTopics && !hideEmbeddedTopicTitle;

  const deleteCopy =
    pendingDelete?.kind === "chapter"
      ? {
          title: "Delete chapter?",
          description: `“${topicTimestamps[pendingDelete.index]?.topic ?? ""}” will be removed.`,
        }
      : pendingDelete?.kind === "question"
        ? {
            title: "Delete question?",
            description: `Question ${pendingDelete.index + 1} will be removed.`,
          }
        : pendingDelete?.kind === "theme"
          ? {
              title: "Delete theme?",
              description: `“${mainTopics[pendingDelete.index] ?? ""}” will be removed.`,
            }
          : null;

  return (
    <>
    <div className={cn("space-y-4", embeddedInPanel && "flex min-h-0 flex-1 flex-col space-y-0")}>

      {showTopicHeaderBlock && (
        <div>
          {!embeddedInPanel && <SectionLabel>Theme</SectionLabel>}
          <div className="space-y-0.5">
            {mainTopics.map((topic, i) => {
              const primary = i === 0;
              if (canEdit && editingTopicIdx === i) {
                return (
                  <div key={i} className="rounded-lg px-2 py-1.5">
                    <div className="flex min-w-0 flex-col gap-2">
                      <textarea
                        autoFocus
                        aria-label={primary ? "Theme" : `Theme ${i + 1}`}
                        value={topicDraft}
                        rows={2}
                        onChange={(e) => setTopicDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commitTopic(i); }
                          if (e.key === "Escape") setEditingTopicIdx(null);
                        }}
                        disabled={isMutating}
                        className="min-w-0 w-full resize-y rounded-lg border border-input bg-card px-2 py-1.5 text-sm leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                      />
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => commitTopic(i)}
                          disabled={isMutating || !topicDraft.trim()}
                          className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                        >
                          <Check size={11} /> Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingTopicIdx(null)}
                          className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                        >
                          <X size={11} /> Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                );
              }
              return (
                <div
                  key={i}
                  className={cn(
                    "group relative rounded-lg px-2 py-1.5 transition-colors",
                    canEdit && "hover:bg-muted/20",
                  )}
                >
                  <div
                    className={cn(
                      "min-w-0 text-sm leading-relaxed break-words whitespace-pre-wrap",
                      primary ? "font-medium text-foreground" : "text-secondary-foreground",
                      canEdit && (primary ? "cursor-text pe-10" : "cursor-text pe-20"),
                    )}
                    onClick={canEdit ? () => startTopicEdit(i) : undefined}
                    role={canEdit ? "button" : undefined}
                    tabIndex={canEdit ? 0 : undefined}
                    onKeyDown={
                      canEdit
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              startTopicEdit(i);
                            }
                          }
                        : undefined
                    }
                  >
                    {topic}
                  </div>
                  {canEdit && (
                    <div className="absolute right-0.5 top-0.5 flex">
                      <button
                        type="button"
                        onClick={() => startTopicEdit(i)}
                        disabled={isMutating}
                        aria-label={primary ? "Edit theme" : `Edit theme “${topic}”`}
                        className={cn(EDIT_AFFORDANCE, EDIT_AFFORDANCE_HOVER)}
                      >
                        <Pencil size={14} />
                      </button>
                      {!primary && (
                        <button
                          type="button"
                          onClick={() => setPendingDelete({ kind: "theme", index: i })}
                          disabled={isMutating}
                          aria-label={`Delete theme “${topic}”`}
                          className={cn(EDIT_AFFORDANCE, "text-muted-foreground/50 hover:text-danger-fg", EDIT_AFFORDANCE_HOVER)}
                        >
                          <X size={14} />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {canEdit && (
              addingTopic ? (
                <div className="flex min-w-0 flex-col gap-2 px-2 py-1.5">
                  <textarea
                    autoFocus
                    aria-label="New theme"
                    value={newTopic}
                    rows={2}
                    onChange={(e) => setNewTopic(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); addTopic(); }
                      if (e.key === "Escape") { setAddingTopic(false); setNewTopic(""); }
                    }}
                    placeholder="Theme…"
                    className="min-w-0 w-full resize-y rounded-lg border border-input bg-card px-2 py-1.5 text-sm leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={addTopic}
                      disabled={isMutating || !newTopic.trim()}
                      className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                      <Check size={11} /> Add
                    </button>
                    <button
                      type="button"
                      onClick={() => { setAddingTopic(false); setNewTopic(""); }}
                      className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <X size={11} /> Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button type="button" onClick={openAddTopic} className={ADD_PILL}>
                  <Plus size={12} /> Add theme
                </button>
              )
            )}
          </div>
        </div>
      )}

      {/* ── Summary ── */}
      {(visibleHasSummary || summaryEditing) && (
        <div>
          <SectionLabel>Summary</SectionLabel>
          {summaryEditing ? (
            <div className="rounded-lg border border-border bg-card p-2">
              {summaryIsTemplate ? (
                <TemplateField
                  label=""
                  value={summaryDraft}
                  onChange={(v) => { setSummaryDraft(v); setSummaryIsTemplate(hasJinja(v)); }}
                  multiline
                  rows={5}
                  placeholder="Summary template…"
                />
              ) : (
                <textarea
                  autoFocus
                  value={summaryDraft}
                  onChange={(e) => {
                    setSummaryDraft(e.target.value);
                    setSummaryIsTemplate(hasJinja(e.target.value));
                  }}
                  rows={5}
                  className="w-full resize-none bg-transparent text-sm outline-none"
                  placeholder="Summary…"
                />
              )}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={saveSummary}
                  disabled={isMutating}
                  className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {isMutating ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                  Save
                </button>
                {summaryIsTemplate && (
                  <button
                    type="button"
                    onClick={convertSummaryToText}
                    disabled={renderLoading || isMutating}
                    className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
                  >
                    {renderLoading ? <Loader2 size={11} className="animate-spin" /> : <Code2 size={11} />}
                    Convert to text
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setSummaryEditing(false)}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  <X size={11} /> Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="group relative">
              <div
                className={cn(
                  "min-w-0 rounded-lg px-2 py-1.5 -mx-2 transition-colors",
                  !readOnly && "cursor-text hover:bg-muted/40",
                )}
                onClick={!readOnly ? openSummaryEdit : undefined}
                role={!readOnly ? "button" : undefined}
                tabIndex={!readOnly ? 0 : undefined}
                onKeyDown={
                  !readOnly
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openSummaryEdit();
                        }
                      }
                    : undefined
                }
              >
                <p className="whitespace-pre-wrap text-sm text-foreground leading-relaxed pe-10">
                  {version.summary}
                </p>
              </div>
              {!readOnly && (
                <button
                  type="button"
                  aria-label="Edit summary"
                  onClick={openSummaryEdit}
                  className={cn("absolute right-0 top-0.5", EDIT_AFFORDANCE, EDIT_AFFORDANCE_HOVER)}
                >
                  <Pencil size={14} />
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Chapters ── */}
      {visibleHasChapters && (
        <div className={cn(embeddedInPanel && "flex min-h-0 flex-1 flex-col gap-3")}>
              {!embeddedInPanel && <SectionLabel>Chapters</SectionLabel>}
          <div
            className={cn(
              "flex min-h-0 flex-col gap-3",
              embeddedInPanel && "flex-1",
              !embeddedInPanel && topicTimestamps.length > 6 && "max-h-[min(36rem,60dvh)] overflow-hidden",
            )}
          >
            {(embeddedInPanel || topicTimestamps.length > 6) && (
            <div className="relative shrink-0">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                type="search"
                aria-label="Search chapters"
                placeholder="Search chapters…"
                value={chapterQuery}
                onChange={(e) => setChapterQuery(e.target.value)}
                className={SEARCH_INPUT}
              />
              {chapterQuery && (
                <button
                  type="button"
                  onClick={() => setChapterQuery("")}
                  aria-label="Clear chapter search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                >
                  <X size={13} />
                </button>
              )}
            </div>
          )}
          {chapterNeedle && (
            <p role="status" className="shrink-0 text-xs text-muted-foreground">
              {filteredChapters.length === 0
                ? `No chapters match “${chapterQuery.trim()}”.`
                : `${filteredChapters.length} of ${topicTimestamps.length} chapters match “${chapterQuery.trim()}”.`}
            </p>
          )}
          <div
            ref={chaptersRef}
            className={cn(
              "min-h-0 overflow-y-auto",
              embeddedInPanel || topicTimestamps.length > 6 ? "flex-1" : undefined,
              chaptersListClassName,
            )}
          >
            {filteredChapters.map(({ item, index }) => (
                <ChapterItem
                  key={`${index}-${item.topic}`}
                  item={item}
                  isActive={index === activeChapterIdx}
                  canRename={!readOnly}
                  onSeek={onSeek ?? (() => {})}
                  onSave={(topic) => saveChapterTopic(index, topic)}
                  onDelete={() => setPendingDelete({ kind: "chapter", index })}
                  disabled={isMutating}
                  itemRef={(el) => {
                    if (el) chapterItemRefs.current.set(index, el);
                    else chapterItemRefs.current.delete(index);
                  }}
                  wrapLabels
                />
            ))}
          </div>
          {!readOnly && (
            addingChapter ? (
              <div className="flex flex-col gap-2">
              <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-2 sm:flex-row sm:items-start">
                <input
                  autoFocus
                  aria-label="Chapter time"
                  aria-invalid={chapterTimeError(newChapterTime) != null}
                  aria-describedby={chapterTimeError(newChapterTime) ? "chapter-time-error" : undefined}
                  value={newChapterTime}
                  onChange={(e) => setNewChapterTime(e.target.value)}
                  placeholder="0:01"
                  className="w-[5.5rem] shrink-0 rounded-lg border border-input bg-background px-2 py-1.5 font-mono text-xs tabular-nums outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                />
                <textarea
                  aria-label="Chapter title"
                  value={newChapterTitle}
                  rows={2}
                  onChange={(e) => setNewChapterTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); addChapter(); }
                    if (e.key === "Escape") setAddingChapter(false);
                  }}
                  placeholder="Chapter title…"
                  className="min-w-0 flex-1 resize-y rounded-lg border border-input bg-background px-2 py-1.5 text-sm leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                />
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={addChapter}
                    disabled={isMutating || !!chapterTimeError(newChapterTime) || !newChapterTitle.trim()}
                    className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    <Check size={11} /> Add
                  </button>
                  <button
                    type="button"
                    onClick={() => setAddingChapter(false)}
                    className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                  >
                    <X size={11} /> Cancel
                  </button>
                </div>
              </div>
              {chapterTimeError(newChapterTime) && (
                <p id="chapter-time-error" role="alert" className="text-xs text-danger-fg">
                  {chapterTimeError(newChapterTime)}
                </p>
              )}
              </div>
            ) : (
              <button type="button" onClick={openAddChapter} className={ADD_PILL}>
                <Plus size={12} /> Add chapter
              </button>
            )
          )}
          </div>
        </div>
      )}

      {/* ── Questions ── */}
      {(visibleHasQuestions || (!readOnly && showSection("questions"))) && (
        <div>
          <SectionLabel>Questions</SectionLabel>
          <div className="space-y-0.5">
            {questions.map((q, i) => (
              <div key={i} className="group relative flex items-start gap-1 rounded-lg px-2 py-1.5 transition-colors hover:bg-muted/20">
                <span className="w-5 shrink-0 text-left text-sm text-muted-foreground tabular-nums select-none py-0.5">
                  {i + 1}.
                </span>
                {!readOnly && editingQuestionIdx === i ? (
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <textarea
                      autoFocus
                      aria-label={`Question ${i + 1}`}
                      value={questionDraft}
                      rows={3}
                      onChange={(e) => setQuestionDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commitQuestion(i); }
                        if (e.key === "Escape") setEditingQuestionIdx(null);
                      }}
                      className="w-full resize-y rounded-lg border border-input bg-card px-2 py-1.5 text-sm leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => commitQuestion(i)}
                        className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                      >
                        <Check size={11} /> Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingQuestionIdx(null)}
                        className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                      >
                        <X size={11} /> Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <span
                      className={cn(
                        "min-w-0 flex-1 text-sm text-foreground rounded px-1 py-0.5 leading-relaxed",
                        !readOnly && "cursor-text pe-20",
                      )}
                      onClick={!readOnly ? () => { setQuestionDraft(q); setEditingQuestionIdx(i); } : undefined}
                    >
                      {q}
                    </span>
                    {!readOnly && (
                      <div className="absolute right-0.5 top-0.5 flex">
                        <button
                          type="button"
                          onClick={() => { setQuestionDraft(q); setEditingQuestionIdx(i); }}
                          aria-label={`Edit question ${i + 1}`}
                          className={cn(EDIT_AFFORDANCE, EDIT_AFFORDANCE_HOVER)}
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingDelete({ kind: "question", index: i })}
                          disabled={isMutating}
                          aria-label={`Delete question ${i + 1}`}
                          className={cn(EDIT_AFFORDANCE, "text-muted-foreground/50 hover:text-danger-fg", EDIT_AFFORDANCE_HOVER)}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}

            {!readOnly && (
              addingQuestion ? (
                <div className="flex items-start gap-1.5 px-1 pt-1">
                  <span className="w-5 shrink-0" />
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <textarea
                      ref={newQuestionRef}
                      autoFocus
                      value={newQuestion}
                      rows={2}
                      onChange={(e) => setNewQuestion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); addQuestion(); }
                        if (e.key === "Escape") { setAddingQuestion(false); setNewQuestion(""); }
                      }}
                      placeholder="Question…"
                      className="min-w-0 w-full resize-y rounded-lg border border-input bg-card px-2 py-1.5 text-sm leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={addQuestion}
                        disabled={isMutating || !newQuestion.trim()}
                        className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        <Check size={11} /> Add
                      </button>
                      <button
                        type="button"
                        onClick={() => { setAddingQuestion(false); setNewQuestion(""); }}
                        className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                      >
                        <X size={11} /> Cancel
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <button type="button" onClick={openAddQuestion} className={ADD_PILL}>
                  <Plus size={12} /> Add question
                </button>
              )
            )}
          </div>
        </div>
      )}

    </div>
    <ConfirmDialog
      open={pendingDelete != null}
      title={deleteCopy?.title ?? "Delete?"}
      description={deleteCopy?.description ?? ""}
      confirmLabel="Delete"
      danger
      onConfirm={() => {
        if (pendingDelete?.kind === "chapter") deleteChapter(pendingDelete.index);
        if (pendingDelete?.kind === "question") {
          saveQuestions(questions.filter((_, j) => j !== pendingDelete.index));
        }
        if (pendingDelete?.kind === "theme") {
          saveMainTopics(mainTopics.filter((_, j) => j !== pendingDelete.index));
        }
        setPendingDelete(null);
      }}
      onCancel={() => setPendingDelete(null)}
    />
    </>
  );
}
