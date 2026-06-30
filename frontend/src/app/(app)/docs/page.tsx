"use client";

import { useState } from "react";
import {
  BookOpen,
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

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-xl bg-blue-50 dark:bg-blue-500/10 border border-blue-100 px-4 py-3">
      <Info size={14} className="text-blue-400 mt-0.5 shrink-0" strokeWidth={1.75} />
      <p className="text-xs text-blue-800 leading-relaxed">{children}</p>
    </div>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-100 px-4 py-3">
      <Info size={14} className="text-amber-400 mt-0.5 shrink-0" strokeWidth={1.75} />
      <p className="text-xs text-amber-800 leading-relaxed">{children}</p>
    </div>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-secondary-foreground leading-relaxed">{children}</p>;
}

function H({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{children}</h3>;
}

function List({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm text-secondary-foreground">
          <span className="mt-1.5 w-1 h-1 rounded-full bg-muted shrink-0" />
          <span className="leading-relaxed">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function Steps({ steps }: { steps: { title: string; body: React.ReactNode }[] }) {
  return (
    <ol className="space-y-4">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-white text-[10px] font-bold">
            {i + 1}
          </span>
          <div className="space-y-1">
            <p className="text-sm font-medium text-foreground">{step.title}</p>
            <div className="text-sm text-muted-foreground leading-relaxed">{step.body}</div>
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
  children,
}: {
  id: string;
  icon: React.ElementType;
  title: string;
  color: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section id={id} className="bg-card border border-border rounded-2xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-muted transition-colors"
      >
        <div className="flex items-center gap-3">
          <Icon size={16} strokeWidth={1.75} style={{ color }} />
          <span className="text-sm font-semibold text-foreground">{title}</span>
        </div>
        {open ? (
          <ChevronDown size={16} className="text-muted-foreground" strokeWidth={1.75} />
        ) : (
          <ChevronRight size={16} className="text-muted-foreground" strokeWidth={1.75} />
        )}
      </button>
      {open && (
        <div className="px-6 pb-6 border-t border-border pt-5 space-y-6">{children}</div>
      )}
    </section>
  );
}

function Sub({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <H>{title}</H>
      {children}
    </div>
  );
}

// ─── nav ──────────────────────────────────────────────────────────────────────

const NAV = [
  { id: "recordings", label: "Recordings", icon: Video },
  { id: "credentials", label: "Credentials", icon: Key },
  { id: "sources", label: "Sources", icon: Database },
  { id: "templates", label: "Templates", icon: FileText },
  { id: "presets", label: "Presets", icon: Settings2 },
  { id: "automation", label: "Automation", icon: Zap },
  { id: "settings", label: "Settings", icon: SlidersHorizontal },
  { id: "config-hierarchy", label: "Config hierarchy", icon: Layers },
  { id: "troubleshooting", label: "Troubleshooting", icon: AlertTriangle },
];

// ─── page ─────────────────────────────────────────────────────────────────────

export default function DocsPage() {
  return (
    <div className="min-h-full p-8 max-w-3xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <BookOpen size={24} className="text-primary" strokeWidth={1.75} />
          <h1 className="text-2xl font-semibold text-foreground">Documentation</h1>
        </div>
        <P>
          LEAP processes educational videos from ingestion to publication — automatically.
          Here you&apos;ll find how each section of the platform works.
        </P>
      </div>

      {/* Nav */}
      <div className="flex flex-wrap gap-2 mb-8">
        {NAV.map(({ id, label, icon: Icon }) => (
          <a
            key={id}
            href={`#${id}`}
            onClick={(e) => {
              e.preventDefault();
              document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card text-xs text-secondary-foreground hover:border-primary/40 hover:text-primary transition-colors"
          >
            <Icon size={12} strokeWidth={1.75} />
            {label}
          </a>
        ))}
      </div>

      <div className="space-y-3">

        {/* ── Recordings ── */}
        <Section id="recordings" icon={Video} title="Recordings" color="#2563eb" defaultOpen>
          <Sub title="Overview">
            <P>
              Recordings is the core section of the platform. Each recording goes through a processing pipeline:
              download → silence trimming → transcription → topic extraction → subtitles → publication.
              You control every step.
            </P>
          </Sub>
          <Sub title="How to add a recording">
            <Steps
              steps={[
                {
                  title: "Upload manually",
                  body: "Click «Add recording» and upload a file directly from your computer.",
                },
                {
                  title: "Sync from a source",
                  body: "If Sources are connected (Zoom, Yandex Disk, etc.) — new recordings appear automatically or via the «Sync» button.",
                },
                {
                  title: "Start processing",
                  body: "Select a recording, configure the parameters (or use a template) and click «Run». Status updates in real time.",
                },
              ]}
            />
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
                <><strong>Transcription</strong> — speech recognition via AssemblyAI. Russian and English supported.</>,
                <><strong>Silence trimming</strong> — FFmpeg automatically removes leading and trailing silence.</>,
                <><strong>Topic extraction</strong> — DeepSeek analyses the transcript and produces a topic list with timecodes.</>,
                <><strong>Subtitles</strong> — generated in SRT and VTT formats from the transcript.</>,
                <><strong>Auto-upload</strong> — immediately after processing, the recording is published to selected platforms.</>,
              ]}
            />
            <Tip>
              Default processing options are set in Settings → Processing Defaults. They can be overridden per recording when starting a run.
            </Tip>
          </Sub>
        </Section>

        {/* ── Credentials ── */}
        <Section id="credentials" icon={Key} title="Credentials" color="#059669">
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
                  body: "YouTube, Zoom, Yandex Disk — each has its own authorization flow.",
                },
                {
                  title: "Complete OAuth",
                  body: "For most platforms a provider authorization page opens. Once you grant access, the token is saved automatically.",
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
              ]}
            />
          </Sub>
          <Note>
            All tokens are stored encrypted. No keys are shared with third parties or displayed in the interface after saving.
          </Note>
        </Section>

        {/* ── Sources ── */}
        <Section id="sources" icon={Database} title="Sources" color="#0891b2">
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
                <><strong>Yandex Disk</strong> — watches a specified folder and picks up new video files. Supports public links without authorization.</>,
                <><strong>Google Drive</strong> — monitors a folder with optional filename filtering. Requires a Google credential.</>,
                <><strong>URL / yt-dlp</strong> — downloads video from a YouTube or other platform link. No credential needed.</>,
                <><strong>Local upload</strong> — manual file upload through the interface. No credential needed.</>,
              ]}
            />
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
                  body: "For Zoom, Google Drive, and Yandex Disk (OAuth mode) select a previously added credential.",
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
        <Section id="templates" icon={FileText} title="Templates" color="#7c3aed">
          <Sub title="Overview">
            <P>
              Templates are metadata blueprints for publication. They define the title, description, tags,
              and other settings that are filled in automatically when a video is uploaded to a platform.
            </P>
          </Sub>
          <Sub title="Why use them">
            <P>
              Instead of typing a title and description every time, you create a template once.
              At publish time the platform substitutes real recording data — name, date, topics, transcript.
            </P>
          </Sub>
          <Sub title="Template variables">
            <P>Titles and descriptions support dynamic variables:</P>
            <List
              items={[
                <><strong>{"{{ display_name }}"}</strong> — recording title.</>,
                <><strong>{"{{ record_date }}"}</strong> — recording date in DD.MM.YYYY format.</>,
                <><strong>{"{{ themes }}"}</strong> — topics as a comma-separated string.</>,
                <><strong>{"{{ topics }}"}</strong> — topics with timecodes as a numbered list.</>,
                <><strong>{"{{ summary }}"}</strong> — plain-text summary from the transcript.</>,
                <><strong>{"{{ questions }}"}</strong> — self-check questions if generated.</>,
                <><strong>{"{{ duration_hm }}"}</strong> — video duration (e.g. 1:05:03).</>,
              ]}
            />
            <Tip>
              In the description you can use {"{{ title }}"} — this is the rendered title string. Useful if you want to repeat the title inside the body text.
            </Tip>
          </Sub>
          <Sub title="Example">
            <div className="rounded-xl bg-muted border border-border p-4 space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Title</p>
              <p className="text-sm text-foreground font-mono">{"{{ display_name }} — {{ record_date }}"}</p>
              <p className="text-xs font-medium text-muted-foreground pt-1">Description</p>
              <p className="text-sm text-foreground font-mono whitespace-pre-line">{"{{ title }}\n\n📚 Topics: {{ themes }}\n⏱ Duration: {{ duration_hm }}\n\n{{ topics }}\n\n❓ Questions:\n{{ questions }}"}</p>
            </div>
          </Sub>
          <Sub title="Preview">
            <P>
              While editing a template, use the «Preview» button — pick a specific recording
              to see what the final title and description will look like before saving.
            </P>
          </Sub>
        </Section>

        {/* ── Presets ── */}
        <Section id="presets" icon={Settings2} title="Presets" color="#d97706">
          <Sub title="Overview">
            <P>
              Presets are upload configurations for a specific platform. A preset combines a credential,
              metadata templates, and platform-specific settings (privacy, category, etc.)
              into one named configuration.
            </P>
          </Sub>
          <Sub title="Difference from Templates">
            <P>
              A Template defines <em>what to write</em> (title, description). A Preset defines <em>where and how to upload</em> — platform, account, text templates, privacy settings.
              One preset = one publish destination.
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
              When starting a recording run, select one or more presets — the video will be published
              to each platform. Presets can be set as defaults in Settings so you don&apos;t have to pick them every time.
            </P>
          </Sub>
        </Section>

        {/* ── Automation ── */}
        <Section id="automation" icon={Zap} title="Automation" color="#059669">
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
                  body: "Which template and presets to use, whether to transcribe, trim, and where to publish.",
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
        <Section id="settings" icon={SlidersHorizontal} title="Settings" color="#6b7280">
          <Sub title="Overview">
            <P>
              Settings stores your personal defaults — processing preferences, metadata templates,
              download behaviour, retention policy, and active sessions. Everything here acts as a
              baseline that can be overridden per-recording or per-preset at run time.
            </P>
          </Sub>
          <Sub title="Processing defaults">
            <P>Controls which pipeline stages run by default on every new recording:</P>
            <List
              items={[
                <><strong>Transcription</strong> — enable/disable ASR, set language, vocabulary hints, allow partial errors.</>,
                <><strong>Topic extraction</strong> — generate topic list with timecodes from the transcript.</>,
                <><strong>Subtitles</strong> — generate SRT and VTT subtitle files.</>,
                <><strong>Trimming</strong> — silence detection mode, threshold (dB), min silence duration, padding before/after.</>,
                <><strong>Auto-upload</strong> — automatically push to selected presets after processing completes.</>,
                <><strong>Upload captions</strong> — attach subtitle files when uploading to platforms that support them.</>,
              ]}
            />
          </Sub>
          <Sub title="Download settings">
            <List
              items={[
                <><strong>Auto-download</strong> — automatically download new recordings from synced sources.</>,
                <><strong>Video quality</strong> — preferred quality when downloading (best, 1080p, 720p, 480p).</>,
                <><strong>Max file size</strong> — skip files above a size threshold (MB).</>,
                <><strong>Retry attempts / delay</strong> — how many times and how long to wait before retrying a failed download.</>,
              ]}
            />
          </Sub>
          <Sub title="Metadata defaults">
            <P>
              Default title and description templates applied when no template is explicitly selected.
              Uses the same Jinja2 variable syntax as Templates. Changes here affect all future runs
              that don&apos;t have a template assigned.
            </P>
          </Sub>
          <Sub title="Retention">
            <P>Controls how long recordings are kept before automatic deletion:</P>
            <List
              items={[
                <><strong>Soft delete after N days</strong> — recording is marked as deleted and hidden from the main list, but files are still on storage.</>,
                <><strong>Hard delete after N days</strong> — files are permanently removed from storage after soft-delete grace period.</>,
                <><strong>Auto-expire after N days</strong> — recordings older than this are automatically soft-deleted regardless of status.</>,
              ]}
            />
            <Tip>
              Soft-deleted recordings can be recovered before the hard deletion grace period runs. Set large values (e.g. 9999 days) to effectively disable automatic expiry.
            </Tip>
          </Sub>
          <Sub title="Active sessions">
            <P>
              Shows all devices currently signed in to your account — browser, OS, last seen time, and IP.
              You can revoke individual sessions or sign out all other devices at once.
              Useful if you suspect unauthorised access.
            </P>
          </Sub>
        </Section>

        {/* ── Config hierarchy ── */}
        <Section id="config-hierarchy" icon={Layers} title="Configuration hierarchy" color="#0891b2">
          <Sub title="How it works">
            <P>
              LEAP has four levels of configuration that override each other from broadest to most specific.
              Each level only needs to specify what differs from the level above — everything else is inherited.
            </P>
          </Sub>
          <Sub title="The four levels">
            <div className="space-y-3 mt-1">
              {[
                {
                  level: "1 — Settings defaults",
                  scope: "Account-wide",
                  desc: "The baseline for every recording. Set in Settings → Processing Defaults. Applied when nothing else is specified.",
                },
                {
                  level: "2 — Template",
                  scope: "Per template",
                  desc: "A template can override processing options (transcription language, topic extraction, trimming parameters) and defines metadata (title, description). Assigned to a recording or automation rule.",
                },
                {
                  level: "3 — Preset",
                  scope: "Per platform destination",
                  desc: "A preset targets a specific platform and credential. It can further override metadata templates and platform-specific publish settings (privacy, category). One recording can be sent to multiple presets simultaneously.",
                },
                {
                  level: "4 — Manual run override",
                  scope: "Per run",
                  desc: "When you click «Run» on a recording you can override any processing parameter for that run only. Nothing is saved — it's a one-time adjustment.",
                },
              ].map(({ level, scope, desc }) => (
                <div key={level} className="flex gap-4 p-4 rounded-xl bg-muted border border-border">
                  <div className="min-w-[11rem] shrink-0">
                    <p className="text-xs font-semibold text-foreground">{level}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{scope}</p>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </Sub>
          <Sub title="Practical example">
            <P>
              Your Settings default has transcription enabled in Russian. You create a Template that sets
              the language to English. Any recording using that template will transcribe in English —
              regardless of the Settings default. If you then manually run that recording with
              transcription disabled, it skips transcription for that run only.
            </P>
            <Note>
              The most specific level always wins: Manual run override → Preset → Template → Settings defaults.
            </Note>
          </Sub>
          <Sub title="What each level can override">
            <List
              items={[
                <><strong>Settings</strong> — all processing options, download behaviour, metadata defaults, retention.</>,
                <><strong>Template</strong> — transcription settings, trimming settings, topic/subtitle toggles, title and description templates, default tags.</>,
                <><strong>Preset</strong> — title and description templates (platform-specific), privacy, category, and other platform publish settings.</>,
                <><strong>Manual run</strong> — any single processing option for one run. Does not persist.</>,
              ]}
            />
          </Sub>
        </Section>

        {/* ── Troubleshooting ── */}
        <Section id="troubleshooting" icon={AlertTriangle} title="Troubleshooting" color="#dc2626">
          <Sub title="Recording is stuck">
            <List
              items={[
                <>Check the recording status — if it shows <strong>Downloading</strong> or <strong>Processing</strong> for more than 15 minutes, the background task may have stalled.</>,
                <>Open the recording detail page — the log panel shows the last known step and any error message.</>,
                <>You can cancel a stuck run and start a new one. Previous partial results (e.g. a completed transcript) are reused where possible.</>,
              ]}
            />
          </Sub>
          <Sub title="Recording failed">
            <List
              items={[
                <>Open the recording and read the error message — it usually points to the exact stage that failed (download, trim, transcription, upload).</>,
                <>For <strong>download failures</strong>: check that the source credential is still valid and the source file exists.</>,
                <>For <strong>transcription failures</strong>: verify your AssemblyAI key in Credentials. Check that the audio track is not empty or corrupted.</>,
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
                <>Set the correct language in Settings → Processing Defaults (or in the Template). Mismatched language degrades accuracy significantly.</>,
                <>Add domain-specific terms in <strong>Vocabulary</strong> (Settings → Advanced Transcription). This helps with names, abbreviations, and technical terms.</>,
                <>Enable <strong>Allow transcription errors</strong> if the recording has background noise — strict mode rejects segments with low confidence.</>,
              ]}
            />
          </Sub>
        </Section>

      </div>

      {/* Footer help */}
      <p className="mt-10 text-center text-xs text-muted-foreground">
        Still have questions?{" "}
        <a href="mailto:gordey.zuev@gmail.com" className="text-primary hover:underline">
          Send us a message
        </a>
        .
      </p>
    </div>
  );
}
