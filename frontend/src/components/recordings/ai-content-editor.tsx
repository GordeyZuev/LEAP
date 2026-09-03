"use client";

import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, X, Plus, Code2, Loader2, Pencil, Search, Settings2 } from "lucide-react";
import { cn, scrollIntoViewWithin } from "@/lib/utils";
import { apiClient } from "@/api/client";
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

// ---------------------------------------------------------------------------
// ChapterItem — timecode always seekable; name editable only when isManaging
// ---------------------------------------------------------------------------

function ChapterItem({
  item,
  isActive,
  isManaging,
  onSeek,
  onSave,
  disabled,
  itemRef,
  wrapLabels = false,
}: {
  item: TopicTimestamp;
  isActive: boolean;
  isManaging: boolean;
  onSeek: (t: number) => void;
  onSave: (topic: string) => void;
  disabled?: boolean;
  itemRef?: (el: HTMLButtonElement | null) => void;
  /** Share sidebar: wrap long chapter titles instead of clipping them. */
  wrapLabels?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.topic);

  function commit() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== item.topic) onSave(trimmed);
    setEditing(false);
  }

  const showEditing = editing && isManaging;

  // While editing, the row can't be a button — it holds a text input. Outside
  // manage mode the whole row is one seek control, so keyboard users get the
  // same target the pointer affordance advertises.
  if (showEditing) {
    return (
      <div className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5">
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", isActive ? "bg-primary" : "bg-border")} />
        <span
          className={cn(
            "w-11 shrink-0 text-left font-mono text-xs",
            isActive ? "font-semibold text-primary" : "text-muted-foreground"
          )}
        >
          {formatTimecode(item.start)}
        </span>
        <input
          autoFocus
          aria-label="Chapter title"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
            if (e.key === "Escape") { setDraft(item.topic); setEditing(false); }
          }}
          onBlur={commit}
          disabled={disabled}
          className="min-w-0 flex-1 rounded border border-input bg-card px-1.5 py-0 text-sm outline-none focus:border-primary"
        />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group flex w-full gap-3 rounded-lg transition-colors",
        wrapLabels ? "items-start" : "items-center",
        isActive ? "bg-primary/6" : isManaging ? "hover:bg-muted/30" : "hover:bg-muted/20"
      )}
    >
      <button
        ref={itemRef}
        type="button"
        onClick={() => onSeek(item.start)}
        className={cn(
          "flex min-w-0 flex-1 gap-3 rounded-lg px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
          wrapLabels ? "items-start" : "items-center",
        )}
      >
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", isActive ? "bg-primary" : "bg-border", wrapLabels && "mt-2")} />
        <span
          className={cn(
            "shrink-0 font-mono text-xs tabular-nums transition-colors group-hover:text-primary",
            wrapLabels ? "min-w-[3.25rem] pt-0.5" : "w-11",
            isActive ? "font-semibold text-primary" : "text-muted-foreground"
          )}
        >
          {formatTimecode(item.start)}
        </span>
        <span
          className={cn(
            "min-w-0 flex-1 py-0.5 text-sm",
            wrapLabels ? "break-words leading-relaxed" : "truncate",
            isActive ? "font-medium text-foreground" : "text-secondary-foreground"
          )}
        >
          {item.topic}
        </span>
      </button>

      {/* Renaming is a second action on the row, so it needs its own control
          rather than a click handler nested inside the seek button. */}
      {isManaging && (
        <button
          type="button"
          onClick={() => { setDraft(item.topic); setEditing(true); }}
          disabled={disabled}
          aria-label={`Rename chapter “${item.topic}”`}
          className="mr-2 shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:opacity-50"
        >
          <Pencil size={12} />
        </button>
      )}
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
  activeChapterIdx = -1,
  readOnly = false,
  sections,
  chaptersListClassName,
  embeddedInPanel = false,
}: AIContentEditorProps) {
  // isManaging enables all editing (text + structural controls)
  const [isManaging, setIsManaging] = useState(false);

  // -- local state (optimistic)
  const [mainTopics, setMainTopics] = useState<string[]>(version.main_topics ?? []);
  const [topicTimestamps, setTopicTimestamps] = useState<TopicTimestamp[]>(version.topic_timestamps ?? []);
  const [questions, setQuestions] = useState<string[]>(version.questions ?? []);

  // -- inline edit state (topic title)
  const [editingTopicIdx, setEditingTopicIdx] = useState<number | null>(null);
  const [topicDraft, setTopicDraft] = useState("");
  const [newTopic, setNewTopic] = useState("");

  // -- inline edit state (questions)
  const [editingQuestionIdx, setEditingQuestionIdx] = useState<number | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [newQuestion, setNewQuestion] = useState("");

  // -- summary edit state
  const [summaryEditing, setSummaryEditing] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState(version.summary ?? "");
  const [summaryIsTemplate, setSummaryIsTemplate] = useState(() => hasJinja(version.summary ?? ""));
  const [renderLoading, setRenderLoading] = useState(false);

  const newTopicRef = useRef<HTMLInputElement>(null);
  const newQuestionRef = useRef<HTMLInputElement>(null);
  const chaptersRef = useRef<HTMLDivElement>(null);
  const chapterItemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const [chapterQuery, setChapterQuery] = useState("");
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

  const persistAsync = async (data: Record<string, unknown>) => {
    if (readOnly) return;
    await updateTopics.mutateAsync(data);
  };

  // Close all edits when leaving manage mode
  function exitManageMode() {
    setEditingTopicIdx(null);
    setEditingQuestionIdx(null);
    setSummaryEditing(false);
    setIsManaging(false);
  }

  // -- topic handlers
  function saveMainTopics(updated: string[]) {
    setMainTopics(updated);
    persist({ main_topics: updated });
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
    newTopicRef.current?.focus();
  }

  // -- chapter handlers
  function saveChapterTopic(index: number, topic: string) {
    const updated = topicTimestamps.map((t, i) => (i === index ? { ...t, topic } : t));
    setTopicTimestamps(updated);
    persist({ topic_timestamps: updated });
  }

  // -- summary handlers
  function openSummaryEdit() {
    if (!isManaging) return;
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
    newQuestionRef.current?.focus();
  }

  // -- guard
  const hasTopics = mainTopics.length > 0;
  const hasChapters = topicTimestamps.length > 0;
  const hasSummary = !!version.summary;
  const hasQuestions = questions.length > 0;

  const showSection = (section: AIContentSection) =>
    !sections || sections.includes(section);

  const visibleHasTopics = showSection("topics") && hasTopics;
  const visibleHasChapters = showSection("chapters") && hasChapters;
  const visibleHasSummary = showSection("summary") && hasSummary;
  const visibleHasQuestions = showSection("questions") && hasQuestions;

  if (!visibleHasTopics && !visibleHasChapters && !visibleHasSummary && !visibleHasQuestions) return null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const hideEmbeddedTopicTitle =
    embeddedInPanel && readOnly && !isManaging;
  const showTopicHeaderBlock =
    !readOnly || (visibleHasTopics && !hideEmbeddedTopicTitle);

  return (
    <div className="space-y-4">

      {/* ── Header: Manage toggle ── */}
      {showTopicHeaderBlock && (
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Topics label + main topic title */}
          {visibleHasTopics && !hideEmbeddedTopicTitle && (
            <>
              {!embeddedInPanel && <SectionLabel>Topics</SectionLabel>}

              {/* Primary topic title */}
              {isManaging && editingTopicIdx === 0 ? (
                <input
                  autoFocus
                  value={topicDraft}
                  onChange={(e) => setTopicDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") { e.preventDefault(); commitTopic(0); }
                    if (e.key === "Escape") setEditingTopicIdx(null);
                  }}
                  onBlur={() => commitTopic(0)}
                  className="w-full rounded border border-primary bg-card px-2 py-0.5 text-base font-semibold outline-none"
                />
              ) : (
                <p
                  className={cn(
                    "text-base font-semibold leading-snug text-foreground rounded px-1 py-0.5 -mx-1 transition-colors",
                    embeddedInPanel && "break-words",
                    isManaging && "cursor-text hover:bg-muted/50"
                  )}
                  onClick={isManaging ? () => { setTopicDraft(mainTopics[0]); setEditingTopicIdx(0); } : undefined}
                >
                  {mainTopics[0]}
                </p>
              )}

              {/* Subtitle topics */}
              {(mainTopics.length > 1 || isManaging) && (
                <div className="mt-0.5 flex flex-wrap items-center gap-x-1 gap-y-0.5 min-h-[1.25rem]">
                  {mainTopics.slice(1).map((topic, rawIdx) => {
                    const i = rawIdx + 1;
                    return (
                      <span key={i} className="flex items-center gap-0.5">
                        {rawIdx > 0 && <span className="text-muted-foreground/40 select-none">·</span>}
                        {isManaging && editingTopicIdx === i ? (
                          <input
                            autoFocus
                            value={topicDraft}
                            onChange={(e) => setTopicDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") { e.preventDefault(); commitTopic(i); }
                              if (e.key === "Escape") setEditingTopicIdx(null);
                            }}
                            onBlur={() => commitTopic(i)}
                            className="rounded border border-primary bg-card px-1.5 py-0 text-sm outline-none"
                          />
                        ) : (
                          <span
                            className={cn(
                              "text-sm text-muted-foreground rounded px-1 transition-colors",
                              isManaging && "cursor-text hover:bg-muted/50 hover:text-foreground"
                            )}
                            onClick={isManaging ? () => { setTopicDraft(topic); setEditingTopicIdx(i); } : undefined}
                          >
                            {topic}
                          </span>
                        )}
                        {isManaging && editingTopicIdx !== i && (
                          <button
                            type="button"
                            onClick={() => saveMainTopics(mainTopics.filter((_, j) => j !== i))}
                            disabled={isMutating}
                            className="text-muted-foreground/50 transition-colors hover:text-danger-fg"
                          >
                            <X size={10} />
                          </button>
                        )}
                      </span>
                    );
                  })}
                  {isManaging && (
                    <span className="flex items-center gap-0.5">
                      {mainTopics.length > 1 && <span className="text-muted-foreground/40 select-none">·</span>}
                      <input
                        ref={newTopicRef}
                        value={newTopic}
                        onChange={(e) => setNewTopic(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTopic(); } }}
                        placeholder="Add…"
                        className="w-16 rounded border border-transparent bg-transparent px-1 py-0 text-sm text-muted-foreground placeholder:text-muted-foreground/30 outline-none focus:border-border focus:text-foreground transition-colors"
                      />
                      {newTopic.trim() && (
                        <button type="button" onClick={addTopic} disabled={isMutating} className="text-primary">
                          <Plus size={11} />
                        </button>
                      )}
                    </span>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Manage / Done toggle */}
        {(version.manually_edited || !readOnly) && (
        <div className="flex shrink-0 items-center gap-2">
          {version.manually_edited && (
            <span className="rounded-full bg-primary/10 px-1.5 py-px text-[10px] font-medium text-primary">
              Edited
            </span>
          )}
          {!readOnly && (
            <button
              type="button"
              onClick={() => isManaging ? exitManageMode() : setIsManaging(true)}
              className={cn(
                "flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                isManaging
                  ? "border-primary bg-primary/10 text-primary hover:bg-primary/15"
                  : "border-border bg-card text-muted-foreground hover:text-foreground hover:border-foreground/20"
              )}
            >
              {isManaging ? (
                <><Check size={11} /> Done</>
              ) : (
                <><Settings2 size={11} /> Manage</>
              )}
            </button>
          )}
        </div>
        )}
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
            <div
              className={cn(
                "rounded-lg px-2 py-1.5 -mx-2 transition-colors",
                isManaging && "cursor-text hover:bg-muted/40"
              )}
              onClick={isManaging ? openSummaryEdit : undefined}
              role={isManaging ? "button" : undefined}
              tabIndex={isManaging ? 0 : undefined}
              onKeyDown={isManaging ? (e) => { if (e.key === "Enter" || e.key === " ") openSummaryEdit(); } : undefined}
            >
              <p className="whitespace-pre-wrap text-sm text-foreground leading-relaxed">
                {version.summary}
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Chapters ── */}
      {visibleHasChapters && (
        <div className={cn(embeddedInPanel && "space-y-3")}>
          {!embeddedInPanel && <SectionLabel>Chapters</SectionLabel>}
          {embeddedInPanel && (
            <div className="relative">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                type="search"
                aria-label="Search topics"
                placeholder="Search topics…"
                value={chapterQuery}
                onChange={(e) => setChapterQuery(e.target.value)}
                className="w-full rounded-xl border border-input bg-card py-2 pl-8 pr-8 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
              />
              {chapterQuery && (
                <button
                  type="button"
                  onClick={() => setChapterQuery("")}
                  aria-label="Clear topic search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                >
                  <X size={13} />
                </button>
              )}
            </div>
          )}
          {embeddedInPanel && chapterNeedle && (
            <p role="status" className="text-xs text-muted-foreground">
              {filteredChapters.length === 0
                ? `No topics match “${chapterQuery.trim()}”.`
                : `${filteredChapters.length} of ${topicTimestamps.length} topics match “${chapterQuery.trim()}”.`}
            </p>
          )}
          <div
            ref={chaptersRef}
            className={cn(
              embeddedInPanel ? "overflow-visible" : "max-h-52 overflow-y-auto",
              chaptersListClassName,
            )}
          >
            {(embeddedInPanel ? filteredChapters : topicTimestamps.map((item, index) => ({ item, index }))).map(
              ({ item, index }) => (
                <ChapterItem
                  key={`${index}-${isManaging}`}
                  item={item}
                  isActive={index === activeChapterIdx}
                  isManaging={isManaging}
                  onSeek={onSeek ?? (() => {})}
                  onSave={(topic) => saveChapterTopic(index, topic)}
                  disabled={isMutating}
                  itemRef={(el) => {
                    if (el) chapterItemRefs.current.set(index, el);
                    else chapterItemRefs.current.delete(index);
                  }}
                  wrapLabels={embeddedInPanel}
                />
              ),
            )}
          </div>
        </div>
      )}

      {/* ── Questions ── */}
      {(visibleHasQuestions || (isManaging && showSection("questions"))) && (
        <div>
          <SectionLabel>Questions</SectionLabel>
          <div className="space-y-0.5">
            {questions.map((q, i) => (
              <div key={i} className="flex items-start gap-3 rounded-lg px-2 py-1.5">
                <span className="w-5 shrink-0 text-left text-sm text-muted-foreground tabular-nums select-none py-0.5">
                  {i + 1}.
                </span>
                {isManaging && editingQuestionIdx === i ? (
                  <input
                    autoFocus
                    value={questionDraft}
                    onChange={(e) => setQuestionDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") { e.preventDefault(); commitQuestion(i); }
                      if (e.key === "Escape") setEditingQuestionIdx(null);
                    }}
                    onBlur={() => commitQuestion(i)}
                    className="flex-1 rounded border border-primary bg-card px-2 py-0 text-sm outline-none"
                  />
                ) : (
                  <>
                    <span
                      className={cn(
                        "flex-1 text-sm text-foreground rounded px-1 py-0.5 transition-colors",
                        isManaging && "cursor-text hover:bg-muted/50"
                      )}
                      onClick={isManaging ? () => { setQuestionDraft(q); setEditingQuestionIdx(i); } : undefined}
                    >
                      {q}
                    </span>
                    {isManaging && (
                      <button
                        type="button"
                        onClick={() => saveQuestions(questions.filter((_, j) => j !== i))}
                        disabled={isMutating}
                        className="mt-0.5 shrink-0 text-muted-foreground/50 transition-colors hover:text-danger-fg"
                      >
                        <X size={12} />
                      </button>
                    )}
                  </>
                )}
              </div>
            ))}

            {/* Add question — only in manage mode */}
            {isManaging && (
              <div className="flex items-center gap-1.5 px-1 pt-0.5">
                <span className="w-5 shrink-0" />
                <input
                  ref={newQuestionRef}
                  value={newQuestion}
                  onChange={(e) => setNewQuestion(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addQuestion(); } }}
                  placeholder="Add question…"
                  className="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1.5 py-0.5 text-sm text-muted-foreground placeholder:text-muted-foreground/40 outline-none focus:border-border focus:text-foreground transition-colors"
                />
                {newQuestion.trim() && (
                  <button type="button" onClick={addQuestion} disabled={isMutating} className="text-primary hover:text-primary/80">
                    <Plus size={13} />
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
