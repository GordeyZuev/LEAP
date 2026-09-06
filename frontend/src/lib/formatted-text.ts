/** Encapsulated description markup. Markers are an implementation detail of storage. */

export const DESCRIPTION_FORMAT_HINT =
  "Cmd/Ctrl+B bold, I italic, U underline, Shift+X strike, K link. Skips {{ variables }}.";

/** Quieter second line: storage vs public look, one-line marks, platforms. */
export const DESCRIPTION_FORMAT_WHISPER =
  "Marks stay in the box; Public look is what people see. One line at a time. YouTube and VK get plain text.";

export const PLAYLIST_JINJA_VARS: { value: string; description: string }[] = [
  { value: "video_count", description: "Number of videos" },
  { value: "duration_hm", description: "Total duration (M:SS or H:MM:SS)" },
  { value: "items", description: "Numbered list of video titles" },
];

export type FormattedNode =
  | { type: "text"; value: string }
  | { type: "jinja"; value: string }
  | { type: "strong"; children: FormattedNode[] }
  | { type: "em"; children: FormattedNode[] }
  | { type: "underline"; children: FormattedNode[] }
  | { type: "strike"; children: FormattedNode[] }
  | { type: "link"; href: string; children: FormattedNode[] };

export type InlineMark = "strong" | "em" | "underline" | "strike";

const MARK_DELIMS: Record<InlineMark, [string, string]> = {
  strong: ["**", "**"],
  em: ["*", "*"],
  underline: ["++", "++"],
  strike: ["~~", "~~"],
};

const JINJA_RE = /\{\{[^{}]*\}\}/g;

export function isSafeHttpUrl(href: string): boolean {
  try {
    const u = new URL(href);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function trimUrlTrailer(raw: string): string {
  return raw.replace(/[.,;:!?)]+$/, "");
}

function findClose(src: string, openAt: number, marker: string, from: number): number {
  const end = src.indexOf(marker, from);
  if (end === -1) return -1;
  if (src.slice(openAt, end).includes("\n")) return -1;
  return end;
}

function parseMarkup(src: string): FormattedNode[] {
  const out: FormattedNode[] = [];
  let i = 0;
  let buf = "";

  const flush = () => {
    if (buf) {
      out.push({ type: "text", value: buf });
      buf = "";
    }
  };

  while (i < src.length) {
    if (src.startsWith("**", i)) {
      const end = findClose(src, i + 2, "**", i + 2);
      if (end !== -1 && end > i + 2) {
        flush();
        out.push({ type: "strong", children: parseMarkup(src.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    }
    if (src.startsWith("++", i)) {
      const end = findClose(src, i + 2, "++", i + 2);
      if (end !== -1 && end > i + 2) {
        flush();
        out.push({ type: "underline", children: parseMarkup(src.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    }
    if (src.startsWith("~~", i)) {
      const end = findClose(src, i + 2, "~~", i + 2);
      if (end !== -1 && end > i + 2) {
        flush();
        out.push({ type: "strike", children: parseMarkup(src.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    }
    if (src[i] === "[") {
      const closeLabel = src.indexOf("](", i + 1);
      if (closeLabel !== -1 && !src.slice(i, closeLabel).includes("\n")) {
        const closeUrl = src.indexOf(")", closeLabel + 2);
        if (closeUrl !== -1 && !src.slice(closeLabel, closeUrl).includes("\n")) {
          const label = src.slice(i + 1, closeLabel);
          const href = src.slice(closeLabel + 2, closeUrl).trim();
          if (label && isSafeHttpUrl(href)) {
            flush();
            out.push({ type: "link", href, children: parseFormattedText(label) });
            i = closeUrl + 1;
            continue;
          }
        }
      }
    }
    if (src[i] === "*" && src[i + 1] !== "*") {
      const end = findClose(src, i + 1, "*", i + 1);
      if (end !== -1 && end > i + 1) {
        flush();
        out.push({ type: "em", children: parseMarkup(src.slice(i + 1, end)) });
        i = end + 1;
        continue;
      }
    }
    if (src.startsWith("https://", i) || src.startsWith("http://", i)) {
      const m = src.slice(i).match(/^https?:\/\/[^\s<>[\]()]+/i);
      if (m) {
        const href = trimUrlTrailer(m[0]);
        if (isSafeHttpUrl(href)) {
          flush();
          out.push({ type: "link", href, children: [{ type: "text", value: href }] });
          i += href.length;
          continue;
        }
      }
    }
    buf += src[i];
    i += 1;
  }
  flush();
  return out;
}

/** Parse storage string. Jinja tokens are never inside marks. */
export function parseFormattedText(src: string): FormattedNode[] {
  const out: FormattedNode[] = [];
  let last = 0;
  const re = new RegExp(JINJA_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    if (m.index > last) out.push(...parseMarkup(src.slice(last, m.index)));
    out.push({ type: "jinja", value: m[0] });
    last = m.index + m[0].length;
  }
  if (last < src.length) out.push(...parseMarkup(src.slice(last)));
  return out;
}

function walkPlain(nodes: FormattedNode[]): string {
  return nodes
    .map((n) => {
      if (n.type === "text" || n.type === "jinja") return n.value;
      if (n.type === "link") {
        const label = walkPlain(n.children);
        return label === n.href ? n.href : `${label} ${n.href}`;
      }
      return walkPlain(n.children);
    })
    .join("");
}

export function formattedTextToPlain(src: string): string {
  return walkPlain(parseFormattedText(src));
}

function wrapTextSegment(text: string, open: string, close: string): string {
  const lead = text.match(/^\s*/)?.[0] ?? "";
  const trail = text.match(/\s*$/)?.[0] ?? "";
  if (lead.length + trail.length >= text.length) return text;
  const core = text.slice(lead.length, text.length - trail.length);
  if (isAlreadyWrapped(core, open, close)) {
    return lead + core.slice(open.length, core.length - close.length) + trail;
  }
  return lead + open + core + close + trail;
}

/** Do not treat `**bold**` as italic `*…*` wrappers. */
function isAlreadyWrapped(core: string, open: string, close: string): boolean {
  if (!core.startsWith(open) || !core.endsWith(close)) return false;
  if (core.length <= open.length + close.length) return false;
  if (open === "*" && (core.startsWith("**") || core.endsWith("**"))) return false;
  return true;
}

function applyDelimsToChunk(chunk: string, open: string, close: string): string {
  const parts: string[] = [];
  let last = 0;
  const re = new RegExp(JINJA_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(chunk)) !== null) {
    if (m.index > last) parts.push(wrapTextSegment(chunk.slice(last, m.index), open, close));
    parts.push(m[0]);
    last = m.index + m[0].length;
  }
  if (last < chunk.length) parts.push(wrapTextSegment(chunk.slice(last), open, close));
  return parts.join("");
}

export function applyInlineMark(
  src: string,
  start: number,
  end: number,
  mark: InlineMark,
): { next: string; range: [number, number] } {
  const [open, close] = MARK_DELIMS[mark];
  const from = Math.max(0, Math.min(start, end));
  const to = Math.max(0, Math.max(start, end));
  if (from === to) {
    return { next: src, range: [from, to] };
  }
  const inner = applyDelimsToChunk(src.slice(from, to), open, close);
  return { next: src.slice(0, from) + inner + src.slice(to), range: [from, from + inner.length] };
}

export function applyLink(
  src: string,
  start: number,
  end: number,
  href = "https://",
): { next: string; range: [number, number] } {
  const from = Math.max(0, Math.min(start, end));
  const to = Math.max(0, Math.max(start, end));
  if (from === to) {
    const inserted = `[link](${href})`;
    const next = src.slice(0, from) + inserted + src.slice(to);
    const urlAt = from + "[link](".length;
    return { next, range: [urlAt, urlAt + href.length] };
  }
  const selected = src.slice(from, to);
  if (/\{\{[^{}]*\}\}/.test(selected)) {
    return { next: src, range: [from, to] };
  }
  const md = selected.match(/^\[([\s\S]*)\]\((https?:\/\/[^)]*)\)$/);
  if (md) {
    const inner = md[1];
    const next = src.slice(0, from) + inner + src.slice(to);
    return { next, range: [from, from + inner.length] };
  }
  const inner = `[${selected}](${href})`;
  const next = src.slice(0, from) + inner + src.slice(to);
  const urlAt = from + selected.length + 3;
  return { next, range: [urlAt, urlAt + href.length] };
}

export function isDescriptionFormatHotkey(code: string, shift: boolean): boolean {
  if (code === "KeyB" || code === "KeyI" || code === "KeyK") return true;
  if (code === "KeyU") return !shift;
  if (code === "KeyX") return shift;
  return false;
}

export function applyDescriptionHotkey(
  code: string,
  shift: boolean,
  src: string,
  start: number,
  end: number,
): { next: string; range: [number, number] } | null {
  if (code === "KeyB") return applyInlineMark(src, start, end, "strong");
  if (code === "KeyI") return applyInlineMark(src, start, end, "em");
  if (code === "KeyU" && !shift) return applyInlineMark(src, start, end, "underline");
  if (code === "KeyX" && shift) return applyInlineMark(src, start, end, "strike");
  if (code === "KeyK") return applyLink(src, start, end);
  return null;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Same rules as TemplateRenderer._duration_hm_str. */
export function formatDurationHm(seconds: number): string {
  const sec = Math.max(0, Math.floor(seconds));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${pad2(m)}:${pad2(s)}`;
  return `${m}:${pad2(s)}`;
}

export function interpolatePlaylistDescription(
  raw: string,
  ctx: {
    videoCount: number;
    durationSeconds: number;
    titles: string[];
    substituteItems?: boolean;
  },
): string {
  const durationHm = formatDurationHm(ctx.durationSeconds);
  let out = raw
    .replace(/\{\{\s*video_count\s*\}\}/g, String(ctx.videoCount))
    .replace(/\{\{\s*duration_hm\s*\}\}/g, durationHm);
  if (ctx.substituteItems !== false) {
    const items = ctx.titles.map((t, i) => `${i + 1}. ${t}`).join("\n");
    out = out.replace(/\{\{\s*items\s*\}\}/g, items);
  }
  return out;
}
