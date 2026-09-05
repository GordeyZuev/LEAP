"use client";

import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Search,
  Zap,
  FileText,
  Settings2,
  SlidersHorizontal,
  Database,
  Key,
  Video,
  ChevronDown,
  ChevronRight,
  Info,
  Layers,
  AlertTriangle,
} from "lucide-react";

// ─── primitives ───────────────────────────────────────────────────────────────

/** Shared long-form copy: comfortable measure and line-height for docs body text. */
const BODY = "text-sm leading-[1.6] text-secondary-foreground text-pretty";
const SUBHEAD =
  "text-xs font-semibold uppercase tracking-wide text-muted-foreground";

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 rounded-xl border border-blue-200/80 bg-blue-50 px-4 py-3 dark:border-blue-500/25 dark:bg-blue-500/10">
      <Info size={15} className="mt-0.5 shrink-0 text-blue-500 dark:text-blue-400" strokeWidth={1.75} aria-hidden />
      <p className={`${BODY} text-blue-900 dark:text-blue-100/90`}>{children}</p>
    </div>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 rounded-xl border border-amber-200/80 bg-amber-50 px-4 py-3 dark:border-amber-500/25 dark:bg-amber-500/10">
      <Info size={15} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" strokeWidth={1.75} aria-hidden />
      <p className={`${BODY} text-amber-950 dark:text-amber-100/90`}>{children}</p>
    </div>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className={BODY}>{children}</p>;
}

function H({ children }: { children: React.ReactNode }) {
  return <h3 className={SUBHEAD}>{children}</h3>;
}

function List({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className={`flex gap-2.5 ${BODY}`}>
          <span className="mt-[0.55rem] size-1 shrink-0 rounded-full bg-muted-foreground/50" aria-hidden />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function Steps({ steps }: { steps: { title: string; body: React.ReactNode }[] }) {
  return (
    <ol className="space-y-5">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3.5">
          <span
            className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold tabular-nums text-primary-foreground"
            aria-hidden
          >
            {i + 1}
          </span>
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-medium leading-snug text-foreground">{step.title}</p>
            <div className={`${BODY} text-muted-foreground`}>{step.body}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

// ─── accordion ────────────────────────────────────────────────────────────────

function Section({
  id,
  icon: Icon,
  title,
  color,
  defaultOpen = false,
  search = "",
  children,
}: {
  id: string;
  icon: React.ElementType;
  title: string;
  color: string;
  defaultOpen?: boolean;
  /** Active query; forces the section open so its text can be matched. */
  search?: string;
  children: React.ReactNode;
}) {
  const [userOpen, setUserOpen] = useState(defaultOpen);

  // While searching every section is expanded, both so the reader sees the hit
  // in context and so its text is in the DOM for the page to match against.
  const open = search ? true : userOpen;

  return (
    <section id={id} className="overflow-hidden rounded-2xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setUserOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={`${id}-panel`}
        className="flex w-full items-center justify-between px-5 py-4 transition-colors hover:bg-muted sm:px-6"
      >
        <div className="flex min-w-0 items-center gap-3">
          <Icon size={16} strokeWidth={1.75} style={{ color }} aria-hidden />
          <span className="truncate text-sm font-semibold text-foreground">{title}</span>
        </div>
        {open ? (
          <ChevronDown size={16} className="shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
        ) : (
          <ChevronRight size={16} className="shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
        )}
      </button>
      {open && (
        <div id={`${id}-panel`} className="space-y-8 px-5 pb-6 pt-2 sm:px-6 sm:pb-7">
          {children}
        </div>
      )}
    </section>
  );
}

function Sub({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <H>{title}</H>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function CompareTable({
  rows,
}: {
  rows: { label: string; template: string; preset: string }[];
}) {
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full min-w-[20rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="py-2.5 pe-4 text-start font-semibold text-foreground">
              <span className="sr-only">Category</span>
            </th>
            <th scope="col" className="py-2.5 pe-4 text-start font-semibold text-foreground">
              Template
            </th>
            <th scope="col" className="py-2.5 text-start font-semibold text-foreground">
              Preset
            </th>
          </tr>
        </thead>
        <tbody className="text-secondary-foreground">
          {rows.map(({ label, template, preset }) => (
            <tr key={label} className="border-b border-border last:border-0">
              <th scope="row" className="py-2.5 pe-4 text-start font-medium text-muted-foreground">
                {label}
              </th>
              <td className="py-2.5 pe-4 leading-[1.5]">{template}</td>
              <td className="py-2.5 leading-[1.5]">{preset}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LayerCard({
  level,
  scope,
  desc,
}: {
  level: string;
  scope: string;
  desc: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-muted/50 p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:gap-5">
        <div className="shrink-0 sm:w-40">
          <p className="text-sm font-semibold leading-snug text-foreground">{level}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{scope}</p>
        </div>
        <p className="min-w-0 text-sm leading-[1.55] text-muted-foreground">{desc}</p>
      </div>
    </div>
  );
}

// ─── nav ──────────────────────────────────────────────────────────────────────

const NAV = [
  { id: "getting-started", label: "Start here", icon: BookOpen },
  { id: "recordings", label: "Recordings", icon: Video },
  { id: "templates", label: "Templates", icon: FileText },
  { id: "presets", label: "Presets", icon: Settings2 },
  { id: "config-hierarchy", label: "How settings combine", icon: Layers },
  { id: "credentials", label: "Credentials", icon: Key },
  { id: "sources", label: "Sources", icon: Database },
  { id: "automation", label: "Automation", icon: Zap },
  { id: "settings", label: "Settings", icon: SlidersHorizontal },
  { id: "troubleshooting", label: "Troubleshooting", icon: AlertTriangle },
];

// ─── page ─────────────────────────────────────────────────────────────────────

export default function DocsPage() {
  const [search, setSearch] = useState("");
  const query = search.trim();
  const emptyRef = useRef<HTMLParagraphElement>(null);

  // Matching reads the rendered text and toggles visibility on the DOM directly:
  // the section bodies are the source of truth, and there is no second copy of
  // the docs to keep in sync.
  useEffect(() => {
    const needle = query.toLowerCase();
    let found = 0;
    for (const { id } of NAV) {
      const el = document.getElementById(id);
      if (!el) continue;
      const hit = !needle || (el.textContent ?? "").toLowerCase().includes(needle);
      el.classList.toggle("hidden", !hit);
      if (hit) found += 1;
    }
    emptyRef.current?.classList.toggle("hidden", found > 0 || !needle);
  }, [query]);

  return (
    <div className="mx-auto min-h-full max-w-3xl px-5 py-6 sm:px-8 sm:py-8">
      {/* Header */}
      <header className="mb-8 space-y-4">
        <div className="flex items-center gap-3">
          <BookOpen size={24} className="shrink-0 text-primary" strokeWidth={1.75} aria-hidden />
          <h1 className="text-balance text-2xl font-semibold leading-tight text-foreground">
            Documentation
          </h1>
        </div>
        <P>
          LEAP takes a video from import to publication — trimming, transcription, topics, subtitles,
          and upload to your platforms. This guide explains every part of the app in plain language.
        </P>
        <Note>
          New here? Open <strong>Start here</strong> below, then skim <strong>Templates</strong> — almost
          everything about processing and publishing flows through templates now.
        </Note>
      </header>

      {/* Search — the accordion hides text from the browser's own find, so the
          page needs its own way in. */}
      <div className="relative mb-6">
        <Search
          size={16}
          className="pointer-events-none absolute start-3.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search the documentation…"
          aria-label="Search the documentation"
          className="w-full rounded-xl border border-input bg-card py-2.5 ps-10 pe-3 text-base outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/10 sm:text-sm"
        />
      </div>

      <p
        ref={emptyRef}
        role="status"
        className="mb-6 hidden rounded-xl border border-border bg-card px-4 py-3 text-sm leading-[1.5] text-muted-foreground"
      >
        Nothing matches “{query}”. Try a different word, or clear the search to browse by section.
      </p>

      {/* Nav — section jump links; gap keeps adjacent targets visually distinct. */}
      <nav aria-label="Documentation sections" className="mb-8 flex flex-wrap gap-2.5">
        {NAV.map(({ id, label, icon: Icon }) => (
          <a
            key={id}
            href={`#${id}`}
            onClick={(e) => {
              e.preventDefault();
              document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-secondary-foreground transition-colors hover:border-primary/40 hover:text-primary"
          >
            <Icon size={13} strokeWidth={1.75} aria-hidden />
            {label}
          </a>
        ))}
      </nav>

      <div className="space-y-4">

        {/* ── Start here ── */}
        <Section id="getting-started" search={query} icon={BookOpen} title="Start here" color="#2563eb" defaultOpen>
          <Sub title="What LEAP does">
            <P>
              You bring in a lecture or webinar. LEAP can trim silence, transcribe speech, extract topics
              with timecodes, generate subtitles, and publish the result to YouTube or Yandex Disk — using
              title and description templates you define once.
            </P>
          </Sub>
          <Sub title="Five-minute setup">
            <Steps
              steps={[
                {
                  title: "Connect platforms (if you publish or sync)",
                  body: (
                    <>
                      Go to <strong>Credentials</strong> and authorize YouTube, Zoom, and/or Yandex Disk
                      depending on what you use. You can skip this for a one-off file upload or a public URL.
                    </>
                  ),
                },
                {
                  title: "Set up your base template",
                  body: (
                    <>
                      Open <strong>Settings → Account</strong> and click the <strong>Base template</strong> banner,
                      or find the row marked <strong>Base</strong> on the Templates page. Here you set defaults:
                      transcription language, trimming, metadata templates, and which presets to upload to.
                    </>
                  ),
                },
                {
                  title: "Create presets (destinations)",
                  body: (
                    <>
                      In <strong>Presets</strong>, create one preset per destination — e.g. «My YouTube channel»
                      or «Course folder on Yandex Disk». A preset stores the account, privacy, and platform-specific options.
                    </>
                  ),
                },
                {
                  title: "Add a recording",
                  body: (
                    <>
                      <strong>Recordings → Add recording</strong> — paste a URL, upload a file, or sync from a source.
                    </>
                  ),
                },
                {
                  title: "Run",
                  body: (
                    <>
                      Open the recording and click <strong>Run</strong>. LEAP applies your base template automatically.
                      Link a named template if you need different rules for this series.
                    </>
                  ),
                },
              ]}
            />
          </Sub>
          <Sub title="When you need more">
            <List
              items={[
                <><strong>Many lecture series</strong> — create named templates with matching rules so the right settings apply automatically.</>,
                <><strong>Nightly imports from Zoom</strong> — add a Source and an Automation rule.</>,
                <><strong>One-off tweaks</strong> — use the Run dialog; overrides apply to that run only and stay off until you enable them.</>,
              ]}
            />
          </Sub>
          <Sub title="Templates vs presets — quick comparison">
            <CompareTable
              rows={[
                { label: "Answers", template: "How to process and what to write", preset: "Where to upload" },
                { label: "Examples", template: "Language, trim, title template", preset: "YouTube privacy, Disk folder" },
                { label: "Count", template: "One base + optional named ones", preset: "One per platform/account" },
              ]}
            />
          </Sub>
        </Section>

        {/* ── Recordings ── */}
        <Section id="recordings" search={query} icon={Video} title="Recordings" color="#2563eb">
          <Sub title="Overview">
            <P>
              Recordings is the core section of the platform. Each recording goes through a processing pipeline:
              download → silence trimming → transcription → topic extraction → subtitles → publication.
              You control every step.
            </P>
          </Sub>
          <Sub title="How to add a recording">
            <P>
              Open <strong>Recordings → Add recording</strong>. You can ingest video in four ways:
            </P>
            <List
              items={[
                <><strong>URL</strong> — paste a link to a single video (YouTube, Rutube, Vimeo, and many other sites via yt-dlp). After a short pause the dialog shows the title, duration, thumbnail, and available qualities.</>,
                <><strong>Playlist</strong> — import every item from a playlist URL.</>,
                <><strong>File</strong> — upload directly from your computer (up to 5 GB).</>,
                <><strong>Sync</strong> — pull new items from a configured source (Zoom, MTS Link, Yandex Disk, or a saved Video URL source).</>,
              ]}
            />
            <Steps
              steps={[
                {
                  title: "Add the video",
                  body: "Pick a tab in the Add recording dialog, or let automation sync from a source.",
                },
                {
                  title: "Start processing",
                  body: "Open the recording, attach a template and presets if needed, then click «Run». Status updates in real time.",
                },
                {
                  title: "Publish",
                  body: "When processing finishes, upload to one or more presets — or enable auto-upload in your base template.",
                },
              ]}
            />
          </Sub>
          <Sub title="Share links">
            <P>
              On a recording detail page, use <strong>Share</strong> for a public link (no login required).
              Enable mints the URL once; Disable keeps it (the public page is 404 until you Enable again);
              Rotate issues a new URL. Viewers can watch the processed video in the browser.
              The player remembers the last position in this browser after a refresh.
              Video preparation starts while the page loads; if the temporary link expires or the network stalls,
              the player refreshes it automatically and shows Retry if recovery is not possible.
              View counts stay on the recording (anonymous page opens, deduped ~30 minutes
              per visitor). Opening a playable video from a playlist counts as a view on that recording
              (same window); the playlist landing and processing rows do not. Download buttons on the public page
              can be hidden per recording — playback itself cannot be copy-proof.
            </P>
          </Sub>
          <Sub title="Playlists">
            <P>
              A playlist is a course: an ordered list of recordings with one public link
              (<code className="text-xs">/share/p/…</code>). Create one under <strong>Playlists</strong>,
              then add recordings from the playlist editor or from <strong>Publications</strong> on a recording.
              Named templates can auto-append new matches to LEAP playlists — this is not a YouTube upload.
              Enable / Disable / Rotate work like recording share. Deleting a playlist kills the link; recordings stay.
              The landing page is a cover image and the video list (no Play button). Opening a video goes to watch
              (<code className="text-xs">?v=</code>): player, companion (Videos, Topics, Transcript), then Extra content,
              Files, and Overview for that item. Landing has no Files panel; watch follows the recording&apos;s download flags.
              Opening a playable video counts as a view on that recording.
            </P>
          </Sub>
          <Sub title="Running a recording">
            <P>
              Click <strong>Run</strong> on the recording page (or select several on the list and bulk-run).
              The Run dialog shows the effective config merged from your templates. Override toggles are{" "}
              <strong>off by default</strong> — expand a section and enable it only when you need a one-time change.
            </P>
            <Tip>
              You can pick a different template for a single run without changing the recording&apos;s linked template.
            </Tip>
          </Sub>
          <Sub title="Recording statuses">
            <List
              items={[
                <><strong>Pending</strong> — recording added, waiting to be started.</>,
                <><strong>Downloading</strong> — fetching from the source.</>,
                <><strong>Processing</strong> — trimming, transcription, topics, subtitles.</>,
                <><strong>Ready</strong> — processing complete, ready to publish.</>,
                <><strong>Uploading</strong> — being uploaded to platforms.</>,
                <><strong>Done</strong> — published to all selected platforms.</>,
                <><strong>Failed</strong> — an error occurred. Open the recording to see details.</>,
              ]}
            />
          </Sub>
          <Sub title="Processing options">
            <List
              items={[
                <><strong>Transcription</strong> — speech recognition via AssemblyAI (Universal-2). Language, vocabulary hints, and optional translation are configurable.</>,
                <><strong>Silence trimming</strong> — FFmpeg automatically removes leading and trailing silence.</>,
                <><strong>Topic extraction</strong> — DeepSeek analyses the transcript and produces a topic list with timecodes and optional self-check questions.</>,
                <><strong>Subtitles</strong> — generated in SRT and VTT formats from the transcript.</>,
                <><strong>Auto-upload</strong> — immediately after processing, the recording is published to selected presets.</>,
              ]}
            />
            <Tip>
              Default processing and upload options live in your <strong>base template</strong> (Settings → Account,
              or the template marked <strong>Base</strong>). You can override them per recording in the Run dialog.
            </Tip>
          </Sub>
        </Section>

        {/* ── Credentials ── */}
        <Section id="credentials" search={query} icon={Key} title="Credentials" color="#059669">
          <Sub title="Overview">
            <P>
              Credentials stores OAuth tokens and keys for connected platforms — YouTube, Zoom, Yandex Disk.
              Without credentials the platform cannot download recordings or publish videos.
            </P>
          </Sub>
          <Sub title="How to add a credential">
            <Steps
              steps={[
                {
                  title: "Go to Credentials",
                  body: "Select Credentials in the left menu and click «Add credential».",
                },
                {
                  title: "Choose a platform",
                  body: "YouTube, Zoom, Yandex Disk, MTS Link — each has its own connection flow.",
                },
                {
                  title: "Complete OAuth",
                  body: "For OAuth platforms a provider page opens and the token is saved automatically. MTS Link uses the Manual tab: paste the organization API key.",
                },
              ]}
            />
          </Sub>
          <Sub title="Platform notes">
            <List
              items={[
                <><strong>YouTube</strong> — token lasts 1 hour and refreshes automatically on upload. Re-authorization is not needed.</>,
                <><strong>Zoom</strong> — uses Server-to-Server OAuth. Authorized once at the account level.</>,
                <><strong>Yandex Disk</strong> — token valid for up to 1 year. Can be used both as a recording source and an upload destination.</>,
                <><strong>MTS Link</strong> — organization API key (Credentials → Manual). Not OAuth. Lecturers to sync are listed as emails on the source.</>,
              ]}
            />
          </Sub>
          <Note>
            All tokens are stored encrypted. No keys are shared with third parties or displayed in the interface after saving.
          </Note>
        </Section>

        {/* ── Sources ── */}
        <Section id="sources" search={query} icon={Database} title="Sources" color="#0891b2">
          <Sub title="Overview">
            <P>
              Sources are connected video recording origins. The platform periodically syncs with them
              and automatically adds new recordings to the processing queue.
            </P>
          </Sub>
          <Sub title="Supported sources">
            <List
              items={[
                <><strong>Zoom</strong> — syncs cloud recordings from your account or managed users. Requires a Zoom credential.</>,
                <><strong>MTS Link</strong> — syncs event recordings for lecturers you list by email. Requires an MTS Link organization API key. LEAP asks MTS Link for an MP4 when you download.</>,
                <><strong>Yandex Disk</strong> — watches a folder (OAuth or public link) and picks up new video files. Optional filename filter and recursive scan.</>,
                <><strong>Video URL</strong> — a saved single-video or playlist URL processed via yt-dlp. No platform credential needed for public links.</>,
              ]}
            />
            <Tip>
              One-off uploads do not require a source — use <strong>Recordings → Add recording</strong> (URL, playlist, or file).
            </Tip>
          </Sub>
          <Sub title="Setting up a source">
            <Steps
              steps={[
                {
                  title: "Create a source",
                  body: "Sources → «Add source» → choose a type and fill in the parameters (folder, file filter, recording type).",
                },
                {
                  title: "Attach a credential",
                  body: "For Zoom, MTS Link, and Yandex Disk (OAuth mode) select a previously added credential. Public Yandex Disk links and Video URL sources can work without one.",
                },
                {
                  title: "Set up automation",
                  body: "To have new recordings processed automatically — link the source to a rule in the Automation section.",
                },
              ]}
            />
          </Sub>
          <Sub title="Sync behaviour">
            <P>
              Each source can be synced manually via the «Sync» button or through automation.
              Only new recordings are pulled — existing ones are never duplicated.
            </P>
          </Sub>
        </Section>

        {/* ── Templates ── */}
        <Section id="templates" search={query} icon={FileText} title="Templates" color="#7c3aed">
          <Sub title="Overview">
            <P>
              A template is a reusable recipe: how to process a video, what title and description to generate,
              and where to publish. Templates use Jinja2 variables so text fills in automatically from each
              recording&apos;s data.
            </P>
          </Sub>
          <Sub title="Base template vs named templates">
            <List
              items={[
                <>
                  <strong>Base template</strong> — exactly one per account. Always applied to every recording.
                  Holds your account-wide defaults (processing, metadata, output presets). Shown with a{" "}
                  <strong>Base</strong> badge. Cannot be deleted; open it from <strong>Settings → Account</strong>{" "}
                  or the Templates list.
                </>,
                <>
                  <strong>Named templates</strong> — optional extras for specific courses or sources. Can auto-assign
                  to recordings via matching rules, or you can link one manually on a recording page. When linked,
                  their settings merge on top of the base template.
                </>,
              ]}
            />
            <Tip>
              To switch which named template is your base: open it → <strong>More → Make base template</strong>.
              When creating a new template, enable <strong>Make base template</strong> on save. The previous base
              becomes a regular named template — nothing is copied or lost.
            </Tip>
          </Sub>
          <Sub title="What you configure in a template">
            <List
              items={[
                <><strong>Processing</strong> — transcription on/off, language, vocabulary, topic extraction, subtitles, question count, allow partial ASR errors.</>,
                <><strong>Metadata templates</strong> — Jinja2 title and description; how topics and questions appear in the text (display format).</>,
                <><strong>Output</strong> — which presets to upload to, auto-upload after processing, attach subtitle files. Named templates can also list <strong>LEAP playlists</strong> (not YouTube) so newly matched recordings are appended to a course.</>,
                <><strong>Matching rules</strong> (named templates only) — keywords, exact names, regex, source filters, exclusions. Active templates with matching rules auto-link to new recordings.</>,
                <><strong>Platform overrides</strong> — optional per-platform fields (YouTube privacy, Yandex folder path, thumbnail) layered on top of global metadata.</>,
              ]}
            />
          </Sub>
          <Sub title="Draft, active, and base">
            <List
              items={[
                <><strong>Draft</strong> — work in progress; matching rules do not run.</>,
                <><strong>Active</strong> — matching and rematch apply; can be linked to recordings.</>,
                <><strong>Base</strong> — always active; matching is disabled (it applies to everything already).</>,
              ]}
            />
          </Sub>
          <Sub title="Working with templates day to day">
            <Steps
              steps={[
                {
                  title: "Edit your base template first",
                  body: "Set language, default presets, and title/description patterns once. Most recordings never need anything else.",
                },
                {
                  title: "Add named templates for series",
                  body: "Example: keywords «ML», «Machine Learning» → template with English transcription and a dedicated YouTube preset.",
                },
                {
                  title: "Preview before saving",
                  body: "Use Preview matches to see which existing recordings would link, and metadata Preview to render title/description against a real recording.",
                },
                {
                  title: "Link or unlink on a recording",
                  body: "On the recording page: Link template / Unlink. Manual link beats auto-matching until you rematch.",
                },
              ]}
            />
          </Sub>
          <Sub title="Template variables (Jinja2)">
            <P>
              Use double curly braces in title and description fields. At upload time LEAP substitutes real values
              from the recording:
            </P>
            <List
              items={[
                <><strong>{"{{ display_name }}"}</strong> — recording title.</>,
                <><strong>{"{{ record_date }}"}</strong> — date (DD.MM.YYYY, your timezone from Settings).</>,
                <><strong>{"{{ record_datetime }}"}</strong> — date and time (DD.MM.YYYY HH:MM).</>,
                <><strong>{"{{ themes }}"}</strong> — topics as a comma-separated line.</>,
                <><strong>{"{{ topics }}"}</strong> — numbered list with timecodes (format depends on display settings).</>,
                <><strong>{"{{ summary }}"}</strong> — plain-text summary from the transcript.</>,
                <><strong>{"{{ questions }}"}</strong> — self-check questions if generated.</>,
                <><strong>{"{{ duration_hm }}"}</strong> — duration (e.g. 1:05:03).</>,
                <><strong>{"{{ title }}"}</strong> — the already-rendered title (handy inside the description body).</>,
              ]}
            />
          </Sub>
          <Sub title="Example metadata">
            <div className="space-y-3 rounded-xl border border-border bg-muted p-4">
              <div>
                <p className={SUBHEAD}>Title</p>
                <p className="mt-1.5 overflow-x-auto font-mono text-sm leading-[1.5] text-foreground">
                  {"{{ display_name }} — {{ record_date }}"}
                </p>
              </div>
              <div>
                <p className={SUBHEAD}>Description</p>
                <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap font-mono text-sm leading-[1.5] text-foreground">
                  {"{{ title }}\n\n📚 Topics: {{ themes }}\n⏱ Duration: {{ duration_hm }}\n\n{{ topics }}\n\n❓ Questions:\n{{ questions }}"}
                </pre>
              </div>
            </div>
          </Sub>
        </Section>

        {/* ── Presets ── */}
        <Section id="presets" search={query} icon={Settings2} title="Presets" color="#d97706">
          <Sub title="Overview">
            <P>
              Presets are upload configurations for a specific platform. A preset combines a credential,
              metadata templates, and platform-specific settings (privacy, category, etc.)
              into one named configuration.
            </P>
          </Sub>
          <Sub title="Difference from templates">
            <P>
              A <strong>template</strong> decides how to process and what text to generate.
              A <strong>preset</strong> decides <em>where</em> to upload and platform-specific options
              (privacy, category, Disk folder). Link presets inside a template&apos;s Output section.
            </P>
          </Sub>
          <Sub title="Platform settings">
            <List
              items={[
                <><strong>YouTube</strong> — privacy (public / unlisted / private), category, license, embeddable, language.</>,
                <><strong>Yandex Disk</strong> — destination folder (supports template variables), filename, optional subtitle and transcript sidecar upload.</>,
              ]}
            />
          </Sub>
          <Sub title="How to use">
            <P>
              Attach presets in a template&apos;s <strong>Output</strong> section (base or named), or pick them
              when you click <strong>Run</strong> on a recording. One recording can publish to several presets at once.
            </P>
          </Sub>
        </Section>

        {/* ── Automation ── */}
        <Section id="automation" search={query} icon={Zap} title="Automation" color="#059669">
          <Sub title="Overview">
            <P>
              Automation lets you trigger recording processing on a schedule or when new videos appear
              in a source — without any manual action.
            </P>
          </Sub>
          <Sub title="How it works">
            <Steps
              steps={[
                {
                  title: "Create a rule",
                  body: "Automation → «New rule». Choose a source, trigger, and processing parameters.",
                },
                {
                  title: "Configure the trigger",
                  body: "On a schedule (e.g. every night at 02:00) or when a new recording appears in the source.",
                },
                {
                  title: "Define what to do",
                  body: "Pick a template (or rely on the base template + auto-matching), choose presets, and set processing options.",
                },
                {
                  title: "Enable the rule",
                  body: "Toggle the rule status to Active. Everything runs automatically from that point.",
                },
              ]}
            />
          </Sub>
          <Sub title="Dry Run mode">
            <P>
              Before enabling a rule you can run «Dry Run» — the platform shows which recordings
              would have been processed, without actually running anything. Useful for testing filters.
            </P>
          </Sub>
          <Note>
            Automation requires at least one source with a configured credential to be connected.
          </Note>
        </Section>

        {/* ── Settings ── */}
        <Section id="settings" search={query} icon={SlidersHorizontal} title="Settings" color="#6b7280">
          <Sub title="Overview">
            <P>
              Settings is for your account profile, appearance, security, and data retention — not for
              processing defaults. Those live in your <strong>base template</strong> (see Templates).
            </P>
          </Sub>
          <Sub title="Account">
            <List
              items={[
                <><strong>Profile</strong> — name, email (read-only), timezone (used for {"{{ record_date }}"} in templates).</>,
                <><strong>Base template banner</strong> — shortcut to edit your account defaults for processing, metadata, and uploads.</>,
                <><strong>Usage & plan</strong> — recordings this month, storage, concurrent tasks, automation jobs.</>,
              ]}
            />
          </Sub>
          <Sub title="Appearance">
            <P>Light, dark, or follow system theme.</P>
          </Sub>
          <Sub title="Security">
            <List
              items={[
                <><strong>Password</strong> — change your login password.</>,
                <><strong>Active sessions</strong> — devices signed in to your account; revoke any session or sign out all others.</>,
              ]}
            />
          </Sub>
          <Sub title="Data retention">
            <P>Controls how long recordings are kept before automatic deletion:</P>
            <List
              items={[
                <><strong>Soft delete after N days</strong> — hidden from the main list; files remain on storage.</>,
                <><strong>Hard delete after N days</strong> — permanent removal after the soft-delete grace period.</>,
                <><strong>Auto-expire after N days</strong> — recordings older than this are soft-deleted regardless of status.</>,
              ]}
            />
            <Tip>
              Use large values (e.g. 9999 days) to effectively disable automatic expiry. Soft-deleted items can
              be recovered until hard deletion runs.
            </Tip>
          </Sub>
        </Section>

        {/* ── Config hierarchy ── */}
        <Section id="config-hierarchy" search={query} icon={Layers} title="How settings combine" color="#0891b2">
          <Sub title="The idea">
            <P>
              LEAP merges settings from several layers. You only specify what differs — everything else
              is inherited from the layer below. The most specific layer wins.
            </P>
          </Sub>
          <Sub title="Merge order (lowest → highest priority)">
            <div className="space-y-3">
              {[
                {
                  level: "1 — Base template",
                  scope: "Every recording",
                  desc: "Your account defaults: processing, metadata templates, output presets, auto-upload. Always applied first.",
                },
                {
                  level: "2 — Linked template",
                  scope: "This recording",
                  desc: "A named template attached to the recording (manually or via matching). Merges on top of the base. Skipped if it is the same as the base.",
                },
                {
                  level: "3 — Run-time template",
                  scope: "Single run",
                  desc: "Optional: pick a different template in the Run dialog for one execution only.",
                },
                {
                  level: "4 — Recording preferences",
                  scope: "This recording",
                  desc: "Edits saved on the recording itself (e.g. from the recording page). Uncommon for most users.",
                },
                {
                  level: "5 — Run overrides",
                  scope: "Single run",
                  desc: "Fields you explicitly enable in the Run dialog. Off by default — turn on only what you want to change for this run.",
                },
              ].map((layer) => (
                <LayerCard key={layer.level} {...layer} />
              ))}
            </div>
          </Sub>
          <Sub title="Example">
            <P>
              Your base template transcribes in Russian. You link an «English ML» template to a recording
              (English language). That recording transcribes in English. If you run it once with transcription
              disabled in the Run dialog, that single run skips transcription — the templates themselves do not change.
            </P>
            <Note>
              Priority: Run overrides → recording preferences → run-time template → linked template → base template.
            </Note>
          </Sub>
          <Sub title="Where presets fit">
            <P>
              Presets are selected in a template&apos;s <strong>Output</strong> section (typical) or in the Run dialog.
              Each preset adds platform-specific publish settings (privacy, folder path, etc.) on top of the
              resolved metadata templates.
            </P>
          </Sub>
          <Sub title="What is not in templates">
            <List
              items={[
                <><strong>Retention</strong> — Settings → Account → Data retention.</>,
                <><strong>Timezone</strong> — Settings → Account (affects date variables in templates).</>,
                <><strong>Credentials</strong> — separate; presets reference them by account.</>,
              ]}
            />
          </Sub>
        </Section>

        {/* ── Troubleshooting ── */}
        <Section id="troubleshooting" search={query} icon={AlertTriangle} title="Troubleshooting" color="#dc2626">
          <Sub title="Recording is stuck">
            <List
              items={[
                <>Check the recording status — if it shows <strong>Downloading</strong> or <strong>Processing</strong> for more than 15 minutes, the background task may have stalled.</>,
                <>Open the recording detail page — the log panel shows the last known step and any error message.</>,
                <>Use <strong>Pause</strong> on the recording detail page to stop an in-flight run, or cancel and start a new one. Previous partial results (e.g. a completed transcript) are reused where possible.</>,
              ]}
            />
          </Sub>
          <Sub title="Recording failed">
            <List
              items={[
                <>Open the recording and read the error message — it usually points to the exact stage that failed (download, trim, transcription, upload).</>,
                <>For <strong>download failures</strong>: check that the source credential is still valid and the source file exists.</>,
                <>For <strong>transcription failures</strong>: check that the audio track is not empty or corrupted. Set the correct language and add domain terms in <strong>Vocabulary</strong> on the template. If failures persist, contact your operator — ASR is configured server-side.</>,
                <>For <strong>upload failures</strong>: the platform credential may have expired. Go to Credentials and refresh it, then re-run the upload stage only.</>,
              ]}
            />
          </Sub>
          <Sub title="Upload failed, but processing succeeded">
            <P>
              You don&apos;t need to reprocess the whole recording. On the recording detail page you can
              trigger the upload stage independently — the existing processed video and subtitles are reused.
            </P>
          </Sub>
          <Sub title="Credential expired">
            <List
              items={[
                <>Go to <strong>Credentials</strong> and find the affected credential — it will show an expired or error status.</>,
                <>Click «Refresh» or «Re-authorize» to start a new OAuth flow. The existing credential record is updated in place — no need to reconfigure presets or sources that reference it.</>,
                <>YouTube refreshes automatically. Yandex Disk tokens last up to a year. Zoom Server-to-Server tokens refresh automatically.</>,
              ]}
            />
          </Sub>
          <Sub title="New recordings not appearing from a source">
            <List
              items={[
                <>Trigger a manual sync: open the source and click «Sync now».</>,
                <>Check that the source is Active and the credential has not expired.</>,
                <>For Zoom: confirm the recording exists in Zoom cloud and is not in trash (enable «Include trash» in source config if needed).</>,
                <>For Yandex Disk: verify the folder path is correct and the file matches the filename filter if one is set.</>,
              ]}
            />
          </Sub>
          <Sub title="Transcription quality is poor">
            <List
              items={[
                <>Set the correct language in your base or linked template. Wrong language hurts accuracy a lot.</>,
                <>Add domain terms in <strong>Vocabulary</strong> on the template (Processing section). Helps with names, abbreviations, and jargon.</>,
                <>Enable <strong>Allow transcription errors</strong> for noisy audio — strict mode rejects low-confidence segments.</>,
              ]}
            />
          </Sub>
        </Section>

      </div>

      {/* Footer help */}
      <p className="mt-12 text-center text-sm leading-[1.5] text-muted-foreground">
        Still have questions?{" "}
        <a
          href="mailto:gordey.zuev@gmail.com"
          className="font-medium text-primary underline-offset-2 hover:underline"
        >
          Send us a message
        </a>
        .
      </p>
    </div>
  );
}
