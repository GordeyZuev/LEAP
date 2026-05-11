# Media integrity: Yandex (and other) downloads, trim, and “short / broken” video

This guide explains **three distinct problem classes** that all look like *“the video is broken after a few minutes”* or *“a huge part is missing”*, how we **verified** them in the lab, which **code paths** are involved, and what **we can do on the LEAP side** to process more videos reliably.

---

## Executive summary

| Symptom | Typical cause | Where it happens |
|--------|-----------------|------------------|
| Output is **~12–18 min** but the lecture was much longer; `video.mp4` decodes **cleanly to EOF** and duration matches `ffprobe` | **Auto-trim by silence** (`silencedetect` on a **heavily compressed** MP3 analysis track) | **After download**, in `trim_video_task` |
| `ffprobe` shows **a long** duration, but `ffmpeg` **stops** mid-file with *“File ended prematurely”* / Opus errors; desktop players also fail | **Truncated or badly muxed source** (often **WebM/Matroska**); metadata **lies** | **Ingestion** (file on disk **before** or **independent of** trim) — download, upload to Disk, or original recorder output |
| File “works in Chrome” but not in QuickTime / some apps; our `video.mp4` is **short** and **intentional** from trim, not corrupt | **VP9 + Opus inside `.mp4`** via **stream copy** is valid for **FFmpeg** but **poor** for some players | **After trim** (`VideoProcessor` defaults to `copy`) |

**Nothing in the pipeline “randomly corrupts the file at minute N”** in the 2494/2495 case: those outputs were **intentional trim windows**. The **2489** example combined **(a)** a **bad source** (decode << header duration) and **(b)** product trim. Addressing “process everything” means **hardening download validation**, **tuning or disabling trim**, and optionally **re-encoding to H.264/AAC** for compatibility.

---

## 1. How we investigated (reproducible checks)

We used a small diagnostic script in the repo:

- Path: `backend/scripts/diagnose_video_file.py`
- Usage (from `backend/`):

  ```bash
  uv run python scripts/diagnose_video_file.py /path/to/file.mp4 --full-decode
  ```

**What it does**

1. **`ffprobe`**: `format.duration`, stream codecs, size.
2. **Full pass**: `ffmpeg -i FILE -f null -` (optionally only first 60s without `--full-decode` for a quick check).
3. Compare **header duration** vs **last `time=`** in decode stats; grep stderr for *premature* / *Opus* / *corrupt*.

### Example: trimmed outputs (e.g. recordings **2494**, **2495**)

- `ffprobe` duration and **full decode** **match** (e.g. ~766s vs ~1097s) — the file is **self-consistent and not “broken at minute N”**; it is simply **shorter** than the real-world meeting because **trim** cut it.
- Codecs are often **VP9 + Opus** even though the name is `video.mp4` (mux was done with **stream copy** from WebM-like sources).

### Example: **2489** `source` (on-disk copy used by the worker)

- `ffprobe` **reported** ~**4733 s** (~79 min) for `format.duration`.
- **Full decode** progressed only to ~**550 s** (~9 min) and logged **`File ended prematurely`**, **Opus packet header** errors.
- So the problem is **not** “FFmpeg trim invented missing data” — the **file bytes** are **inconsistent** (metadata vs payload). A browser can still **play from URL** or **tolerate** partial data differently than a **full-file** decode.

---

## 2. Pipeline stages and where the issue can appear

High-level: **Download → local path = `.../source.<ext>` (pipeline ingress) → TRIM → `video.mp4` + `audio.mp3` → ASR, subs, upload.** Legacy folders may still have **`source.mp4`** only.

```text
[Origin: WebM on Yandex or screen recorder]
        │
        ▼
┌───────────────────┐
│ Download (Celery) │  httpx stream; size validation; path from StoragePathBuilder
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ TRIM (Celery)     │  extract full audio → MP3 64k/16k/mono; silencedetect; trim window
│                   │  trim_video: ffmpeg -i … -ss … -t … -c copy (by default)
└─────────┬─────────┘
          │
          ▼
  transcription, topics, upload …
```

### 2.1 Download (`_download_via_external` → Yandex / yt-dlp / …)

- Entry: `backend/api/tasks/processing.py` (`_download_via_external` calls `downloader.download()`).
- Yandex: `backend/video_download_module/platforms/yadisk/downloader.py` — **streaming** GET, `Content-Length` / `Content-Range`, resume (`Range` in API path), public-share fallbacks, headers for CDN.
- **Target path** is `storage/.../recordings/{id}/source.<ext>` where **`<ext>`** comes from the remote filename (Yandex), upload filename (local API), or Zoom `video_file_type` when present. **Extension does not guarantee** H.264 — VP9/Opus in an MP4-compatible mux is still possible.
- **Whitelist** — **`StorageSettings.supported_video_formats`** (defaults: tuple **`STORAGE_DEFAULT_VIDEO_FORMATS`** in `config/settings.py`; **not** overridable via `STORAGE_*` env). Same entries filter Yandex picker results (`YandexDiskClient._is_video_file`) when MIME is ambiguous.

### 2.2 Post-download validation (`ingress_validate_saved_media` / `BaseDownloader._validate_file`)

- Path: `backend/utils/pipeline_video_formats.py` (+ thin wrapper in `backend/video_download_module/core/base.py`).
- Checks:
  - file exists, **size ≥ 1 KiB**;
  - if a **reference size** is known: **downloaded < reference → fail** (incomplete);
  - first chunk is not **HTML**;
  - magic-byte **sniff**: **EBML** (WebM/MKV family) vs **ISO BMFF** (`ftyp` anywhere in the first 4 KiB);
  - when a **source filename** is available, its **suffix** must be in the ingress whitelist and must be **consistent** with the sniff (`.webm`/`.mkv` require EBML; `.mp4`/`.mov` normally require ISO — **mismatch WebM bytes + `.mp4` name** logs a **warning** but is allowed until every writer uses matching names).

**Gap (still relevant for “truncated but accepted”)**

- If **`Content-Length` / `Content-Range` total** and **`expected_size` from `source_meta`** are **missing or zero**, the strict size check is weakened — sniff + HTML guard still run.

### 2.3 TRIM (`trim_video_task` + `VideoProcessor` + `AudioDetector`)

- `extract_audio_full`: decodes **only the first audio stream** (`ffmpeg -map 0:a:0`) and **re-encodes** to **64 kbps, 16 kHz, mono** MP3 for ASR analysis.
- `silencedetect` on that MP3; `AudioDetector._find_last_sound` can treat **trailing** “silence” to EOF as *end of speech* → **short `end` timestamp**.
- `trim_video`: `ffmpeg -i INPUT -ss START -t DURATION -c:v copy -c:a copy` (defaults in `ProcessingConfig`) → output **`video.mp4`** often = **VP9+Opus in MP4** if input was that.

### 2.4 “Broken on desktop, fine in browser”

- **Codec**: VP9/Opus in MP4: **VLC / IINA** usually OK; **QuickTime** often **not**.
- **File**: true **corruption** (2489 source) is visible in **FFmpeg** stderr, not just in a player.

---

## 3. Root causes in detail

### 3.1 A — Truncated or invalid **source** (rare but severe)

- **Sign:** `ffprobe` duration **≫** position where **decode** dies; `File ended prematurely`, codec parse errors.
- **Origin** may be: incomplete upload to Yandex, bad public link, recorder crash, or **our download** if validation did not catch partial body (see gap above).
- **LEAP trim** does not repair this; it can only work on what **decodes**.

### 3.2 B — **Aggressive trim** (very common in long lectures)

- **Sign:** `video.mp4` is **consistently short**, logs show `Audio boundaries: ... - ...` and topics/transcription **duration** matches ~trim length; **no** premature EOF in decode of **`video.mp4`**.
- **Fix levers** (product/config): `trimming.enable_trimming`, `silence_threshold`, `min_silence_duration`, padding; or **disable** trim for certain templates; optionally **run silence detection** on a **less** compressed **PCM/WAV** slice (future code change).

### 3.3 C — **Player / container compatibility** (not “LEAP broke the file”)

- **Sign:** `ffmpeg -f null -` on **`video.mp4`** **exits 0**; same file fails in a given desktop player.
- **Fix:** re-encode to **H.264 + AAC** (or ship two outputs) in processing config (today defaults are `copy`).

---

## 4. What we can do on the LEAP side (action list)

**Hardening ingestion**

1. **After download:** require **`expected_size`** from API when available; **fail** or **retry** if `on_disk < expected` (already implemented when `reference_size` is set — ensure `source_meta["size"]` is populated for Yandex resources).
2. **Optional second gate:** run **`ffprobe` duration** + **`ffmpeg` decode** (or a **tail seek** + short decode) in the worker; **flag** or **block** if stderr contains *premature* / repeated codec errors.
   *Cost: CPU/time; use for large files or spot checks.*
3. **Real filenames on disk** — `source.<ext>` is now preferred; EBML vs ISO sniff happens in `ingress_validate_saved_media` (see `utils/pipeline_video_formats.py`).

**Trim behavior**

4. Expose in templates: **softer** `silence_threshold` (e.g. **−50 dB**), **longer** `min_silence_duration**, or **`enable_trimming: false`** for long “always keep full” workflows.
5. (Code change) Run **silencedetect** on a **WAV/PCM** extract or **higher** bitrate MP3 for boundary detection only (keep 64k for ASR).

**Compatibility**

6. After trim, **re-encode** in the processing stage remains a separate template knob (`video_codec` / `copy` defaults).
7. **Upload-time FFmpeg normalization** is **not** implemented in LEAP right now (YAGNI); add explicitly when a platform policy requires it.

**Operations**

8. Use `scripts/diagnose_video_file.py` for support tickets: distinguish **A vs B vs C** in minutes.

## 5. References (code)

| Area | File |
|------|------|
| Download orchestration | `backend/api/tasks/processing.py` (`_download_via_external`) |
| Yandex download & streams | `backend/video_download_module/platforms/yadisk/downloader.py` |
| Pipeline ingress sniff + whitelist | `backend/utils/pipeline_video_formats.py` |
| YaDisk MIME-or-extension picker filter | `config.settings.storage_video_ingress_suffixes()` / `yandex_disk_module/client.py` |
| Generic URL download + validation | `backend/video_download_module/core/base.py` (`_download_url`, `_validate_file`) |
| Trim pipeline | `backend/api/tasks/processing.py` (`_async_process_video` / `trim_video_task` region) |
| Audio extract + trim command | `backend/video_processing_module/video_processor.py` |
| Silence detection | `backend/video_processing_module/audio_detector.py` |
| Trimming config keys | `trimming` in template / `resolve_full_config` (see `TEMPLATES_PRESETS_SOURCES_GUIDE.md`) |
| On-disk layout | `backend/docs/guides/STORAGE_STRUCTURE.md` |
| Yandex integration | `backend/docs/guides/YANDEX_DISK_GUIDE.md` |
| Diagnostic script | `backend/scripts/diagnose_video_file.py` |

---

## 6. Conclusion

- **“Everything must be processed”** means: (1) **Don’t accept** under-sized or **integrity-failed** downloads when metadata allows it. (2) **Don’t treat** a **short output** as corruption when **ffprobe and full decode agree** — it is often **trim**. (3) For **universal playback**, plan **H.264/AAC** or warn about **VP9-in-MP4** + **stream copy**.
- The **most misleading** case is **2489-like** sources: **header duration OK**, **stream bad** — only **full decode** or the diagnostic script makes it obvious; **player vs browser** behavior will continue to differ until the **source** is fixed or re-muxed **outside** LEAP.
