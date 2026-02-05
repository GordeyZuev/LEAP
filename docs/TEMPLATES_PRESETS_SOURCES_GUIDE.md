# Templates, Presets & Sources - Complete Guide

**Version:** 0.9.4
**Last Updated:** January 2026

Complete reference for configuring Recording Templates, Output Presets, and Input Sources in LEAP Platform.

---

## Table of Contents

1. [Input Sources](#input-sources)
2. [Output Presets](#output-presets)
3. [Recording Templates](#recording-templates)
4. [Matching Logic](#matching-logic)
5. [Use Cases & Examples](#use-cases--examples)

---

## Input Sources

Input Sources define where recordings come from (Zoom, Google Drive, local files, etc.).

### Schema

```json
{
  "id": 1,
  "user_id": "01HX...",
  "name": "My Zoom Account",
  "description": "Main Zoom account for lectures",
  "source_type": "ZOOM",
  "credential_id": 1,
  "is_active": true,
  "last_sync_at": "2024-01-15T10:00:00Z",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "config": {
    // Platform-specific configuration
  }
}
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string(3-255) | ✅ | Source name |
| `description` | string(0-1000) | ❌ | Source description |
| `platform` | enum | ✅ | Platform type: `ZOOM`, `GOOGLE_DRIVE`, `YANDEX_DISK`, `LOCAL` |
| `credential_id` | integer | ⚠️ | Credential ID (required for all except LOCAL) |
| `is_active` | boolean | ❌ | Active status (default: true) |
| `config` | object | ❌ | Platform-specific configuration |

### Platform Configurations

#### ZOOM Source Config

```json
{
  "user_id": "me",
  "include_trash": false,
  "recording_type": "cloud"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_id` | string | null | Zoom user ID filter (null = all users) |
| `include_trash` | boolean | false | Include deleted recordings |
| `recording_type` | enum | "cloud" | `"cloud"` or `"all"` |

#### Google Drive Source Config

```json
{
  "folder_id": "1abc...xyz",
  "recursive": true,
  "file_pattern": ".*\\.mp4$"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | ✅ | Google Drive folder ID |
| `recursive` | boolean | ❌ | Search in subfolders (default: true) |
| `file_pattern` | string (regex) | ❌ | Regex pattern for file filtering |

#### Yandex Disk Source Config

```json
{
  "folder_path": "/Видео/Лекции",
  "recursive": true,
  "file_pattern": "Лекция.*\\.mp4"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_path` | string | ✅ | Path to folder on Yandex.Disk |
| `recursive` | boolean | ❌ | Search in subfolders (default: true) |
| `file_pattern` | string (regex) | ❌ | Regex pattern for file filtering |

#### LOCAL Source Config

```json
{}
```

No configuration needed for local file sources.

---

## Output Presets

Output Presets define where and how to upload processed recordings.

### Schema

```json
{
  "id": 1,
  "user_id": "01HX...",
  "name": "YouTube Main Channel",
  "description": "Main channel for course lectures",
  "platform": "youtube",
  "credential_id": 1,
  "is_active": true,
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "preset_metadata": {
    // Platform-specific metadata
  }
}
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string(1-255) | ✅ | Preset name |
| `description` | string(0-1000) | ❌ | Preset description |
| `platform` | enum | ✅ | Platform: `"youtube"` or `"vk"` |
| `credential_id` | integer(>0) | ✅ | Credential ID for platform |
| `is_active` | boolean | ❌ | Active status (default: true) |
| `preset_metadata` | object | ✅ | Platform-specific metadata |

### YouTube Preset Metadata

```json
{
  "title_template": "{display_name} | {themes}",
  "description_template": "{summary}\n\n{topics}",
  "privacy": "unlisted",
  "made_for_kids": false,
  "embeddable": true,
  "category_id": "27",
  "license": "youtube",
  "default_language": "ru",
  "playlist_id": "PLxxxxxxxxxxxxxxxxxxxxx",
  "tags": ["AI", "ML", "лекция"],
  "thumbnail_name": "ml_extra.png",
  "topics_display": {
    "enabled": true,
    "format": "numbered_list",
    "max_count": 999,
    "min_length": 0,
    "max_length": 999,
    "prefix": "Темы лекции:",
    "separator": "\n",
    "show_timestamps": false
  },
  "publish_at": "2024-02-15T10:00:00Z",
  "disable_comments": false,
  "rating_disabled": false,
  "notify_subscribers": true
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title_template` | string(0-500) | null | Title template with variables |
| `description_template` | string(0-5000) | null | Description template |
| `privacy` | enum | "unlisted" | `"public"`, `"private"`, `"unlisted"` |
| `made_for_kids` | boolean | false | COPPA compliance |
| `embeddable` | boolean | true | Allow embedding |
| `category_id` | string | "27" | YouTube category (27 = Education) |
| `license` | enum | "youtube" | `"youtube"` or `"creativeCommon"` |
| `default_language` | string | null | Language code (e.g., "ru", "en") |
| `playlist_id` | string | null | YouTube playlist ID |
| `tags` | string[] | null | Video tags (max 500) |
| `thumbnail_name` | string | null | Thumbnail filename (e.g., "ml_extra.png") - resolved to user's directory |
| `topics_display` | object | null | Topics display configuration |
| `publish_at` | string (ISO 8601) | null | Scheduled publish time |
| `disable_comments` | boolean | false | Disable comments |
| `rating_disabled` | boolean | false | Disable likes/dislikes |
| `notify_subscribers` | boolean | true | Notify subscribers |

### VK Preset Metadata

```json
{
  "title_template": "{display_name}",
  "description_template": "{summary}\n\n{topics}",
  "privacy_view": 0,
  "privacy_comment": 0,
  "group_id": 123456,
  "album_id": "123456",
  "thumbnail_name": "applied_python.png",
  "topics_display": {
    "enabled": true,
    "format": "bullet_list"
  },
  "disable_comments": false,
  "repeat": false,
  "compression": false,
  "wallpost": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title_template` | string(0-500) | null | Title template with variables |
| `description_template` | string(0-5000) | null | Description template |
| `privacy_view` | integer | 0 | Who can view: 0=all, 1=friends, 2=friends of friends, 3=only me |
| `privacy_comment` | integer | 0 | Who can comment: 0=all, 1=friends, 2=friends of friends, 3=only me |
| `group_id` | integer(>0) | null | VK group ID for publishing |
| `album_id` | string | null | VK album ID |
| `thumbnail_name` | string | null | Thumbnail filename (e.g., "applied_python.png") - resolved to user's directory |
| `topics_display` | object | null | Topics display configuration |
| `disable_comments` | boolean | false | Completely disable comments |
| `repeat` | boolean | false | Loop playback |
| `compression` | boolean | false | VK-side video compression |
| `wallpost` | boolean | false | Post to wall on upload |

### Topics Display Configuration

```json
{
  "enabled": true,
  "format": "numbered_list",
  "max_count": 10,
  "min_length": 20,
  "max_length": 500,
  "prefix": "Темы лекции:",
  "separator": "\n",
  "show_timestamps": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | boolean | true | Enable topics display |
| `format` | enum | "numbered_list" | Format: `"numbered_list"`, `"bullet_list"`, `"dash_list"`, `"comma_separated"`, `"inline"` |
| `max_count` | integer(1-999) | null | Max number of topics to show (default: 999 = show all) |
| `min_length` | integer(0-500) | null | Min topic length in chars (default: 0 = no filter) |
| `max_length` | integer(10-1000) | null | Max topic length in chars |
| `prefix` | string(0-200) | null | Prefix before topic list |
| `separator` | string(0-10) | "\n" | Separator between topics |
| `show_timestamps` | boolean | false | Show timestamps for topics |

---

## Recording Templates

Recording Templates automate processing and uploading based on matching rules.

### Schema

```json
{
  "id": 1,
  "user_id": "01HX...",
  "name": "ML Course Template",
  "description": "Template for Machine Learning course",
  "is_draft": false,
  "is_active": true,
  "used_count": 15,
  "last_used_at": "2024-01-15T10:00:00Z",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "matching_rules": {
    // Matching configuration
  },
  "processing_config": {
    // Processing configuration
  },
  "metadata_config": {
    // Metadata configuration
  },
  "output_config": {
    // Output configuration
  }
}
```

### Core Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string(3-255) | - | Template name (required) |
| `description` | string(0-1000) | null | Template description |
| `is_draft` | boolean | false | Draft mode (not auto-applied) |
| `is_active` | boolean | true | Active status |
| `matching_rules` | object | null | Matching rules (required for non-draft) |
| `processing_config` | object | null | Processing configuration |
| `metadata_config` | object | null | Content metadata configuration |
| `output_config` | object | null | Output configuration |

### Matching Rules

Defines which recordings match this template.

```json
{
  "exact_matches": ["Лекция 101"],
  "keywords": ["машинное обучение", "ML"],
  "patterns": ["^Лекция \\d+"],
  "source_ids": [1, 2],
  "exclude_keywords": ["тест", "черновик"],
  "exclude_patterns": [".*_temp$"],
  "case_sensitive": false
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `exact_matches` | string[] | Exact name matches |
| `keywords` | string[] | Keywords to search for (OR logic) |
| `patterns` | string[] (regex) | Regex patterns to match (OR logic) |
| `source_ids` | integer[] | Bind to specific input sources |
| `exclude_keywords` | string[] | **Exclude** records with these words |
| `exclude_patterns` | string[] (regex) | **Exclude** records matching regex |
| `case_sensitive` | boolean | Case sensitivity (default: false) |

**Matching order per template:**
1. `source_ids` filter → skip if not matched
2. `exclude_keywords` → **SKIP template** if any match
3. `exclude_patterns` → **SKIP template** if any match
4. `exact_matches` → **RETURN template** if any match
5. `keywords` → **RETURN template** if any match
6. `patterns` → **RETURN template** if any match

**Template evaluation:**
- Templates sorted by `created_at ASC` (older first)
- First matched template is applied
- No further templates are checked

### Processing Config

```json
{
  "transcription": {
    "enable_transcription": true,
    "prompt": "Technical lecture on AI",
    "language": "ru",
    "enable_topics": true,
    "granularity": "long",
    "enable_subtitles": true
  }
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `transcription.enable_transcription` | boolean | true | Enable audio transcription |
| `transcription.prompt` | string | null | Prompt to improve transcription quality |
| `transcription.language` | string | null | Audio language ("ru", "en", etc.) |
| `transcription.enable_topics` | boolean | true | Extract topics from transcription |
| `transcription.granularity` | enum | "long" | Topic detail: `"short"` or `"long"` |
| `transcription.enable_subtitles` | boolean | true | Generate subtitles (SRT/VTT) |

### Metadata Config

```json
{
  "title_template": "Курс ИИ | {themes} ({record_time:DD.MM.YY})",
  "description_template": "Лекция\n\n{topics}\n\nЗаписано: {record_time}",
  "thumbnail_name": "python_base.png",
  "topics_display": {
    "enabled": true,
    "format": "numbered_list"
  },
  "youtube": {
    "privacy": "unlisted",
    "playlist_id": "PLxxxxx",
    "title_template": "YouTube specific title"
  },
  "vk": {
    "album_id": "123456",
    "group_id": 123456
  }
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `title_template` | string(0-500) | Title template (common for all platforms) |
| `description_template` | string(0-5000) | Description template (common) |
| `thumbnail_name` | string | Thumbnail filename (e.g., "python_base.png") - resolved to user's directory |
| `topics_display` | object | Topics display config (common) |
| `youtube` | object | YouTube-specific overrides |
| `vk` | object | VK-specific overrides |

**Template Variables:**
- `{display_name}` - Recording name
- `{themes}`, `{topic}`, `{topics}`, `{topics_list}` - Topics
- `{summary}` - Summary
- `{record_time}`, `{publish_time}`, `{date}` - Dates
- `{duration}` - Duration
- `{record_time:DD.MM.YY}` - Date formatting

**Thumbnail Resolution:**
1. Platform-specific (`youtube.thumbnail_name` / `vk.thumbnail_name`)
2. Common (`thumbnail_name`)
3. From preset (`preset.preset_metadata.thumbnail_name`)

**Note:** All `thumbnail_name` values should be just filenames (e.g., "ml_extra.png"), not full paths.
API automatically resolves filename to user's thumbnail directory: `storage/users/user_XXXXXX/thumbnails/`
Each user gets their own copies of all shared templates at registration.

### Output Config

```json
{
  "preset_ids": [1, 2],
  "auto_upload": true,
  "upload_captions": true
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `preset_ids` | integer[1-10] | ✅ | Output preset IDs |
| `auto_upload` | boolean | ❌ | Auto-upload after processing (default: false) |
| `upload_captions` | boolean | ❌ | Upload subtitles with video (default: true) |

**Validation:**
- `preset_ids` must have 1-10 unique positive integers
- If `auto_upload=true` → requires `processing_config`
- If `title_template` exists → requires `output_config` with `preset_ids`

---

## Matching Logic

### How Templates are Applied

**Step 1: Get Active Templates**
```sql
SELECT * FROM recording_templates
WHERE user_id = ? AND is_active = true AND is_draft = false
ORDER BY created_at ASC
```

**Step 2: For Each Recording, Find First Match**

For each template (in order):
1. Check `source_ids` filter
2. Check `exclude_keywords` (negative)
3. Check `exclude_patterns` (negative)
4. Check `exact_matches` (positive)
5. Check `keywords` (positive)
6. Check `patterns` (positive)

**First matched template wins. No further templates are checked.**

### Case Sensitivity

- `case_sensitive = false` (default):
  - Keywords compared as lowercase
  - Exact matches compared as lowercase
  - Patterns use `re.IGNORECASE`

- `case_sensitive = true`:
  - All comparisons are case-sensitive
  - Exact case must match

### Negative Matching (Exclude Rules)

Exclude rules are checked **before** positive rules:

```json
{
  "keywords": ["лекция"],
  "exclude_keywords": ["тест", "черновик"]
}
```

**Result:**
- ✅ "Лекция по ML" → matched
- ❌ "Тест лекция" → excluded by `exclude_keywords`
- ❌ "Лекция черновик" → excluded by `exclude_keywords`

---

## Use Cases & Examples

### Example 1: Catch-All Template with Exclusions

```json
{
  "name": "Default Processing",
  "matching_rules": {
    "patterns": [".*"],
    "exclude_keywords": ["тест", "draft", "temp"]
  },
  "processing_config": {
    "transcription": {
      "enable_transcription": true,
      "enable_topics": true,
      "enable_subtitles": true
    }
  },
  "output_config": {
    "preset_ids": [1],
    "auto_upload": false
  }
}
```

**Use case:** Process all recordings except tests and drafts.

### Example 2: Course-Specific Template

```json
{
  "name": "ML Course",
  "matching_rules": {
    "keywords": ["машинное обучение", "ML", "нейронные сети"],
    "source_ids": [1]
  },
  "processing_config": {
    "transcription": {
      "enable_transcription": true,
      "prompt": "Technical lecture on Machine Learning",
      "language": "ru",
      "granularity": "long"
    }
  },
  "metadata_config": {
    "title_template": "Курс МО | {themes} ({record_time:DD.MM.YY})",
    "description_template": "Лекция по курсу Машинное обучение\n\n{topics}",
    "youtube": {
      "playlist_id": "PLxxx_ML_Course",
      "privacy": "unlisted"
    }
  },
  "output_config": {
    "preset_ids": [1, 2],
    "auto_upload": true
  }
}
```

**Use case:** Automatically process and upload ML course lectures to specific playlist.

### Example 3: Pattern-Based Matching

```json
{
  "name": "Lecture Series",
  "matching_rules": {
    "patterns": ["^Лекция \\d+:", "^Lecture \\d+:"],
    "exclude_patterns": [".*_backup$", ".*\\(копия\\)"]
  },
  "processing_config": {
    "transcription": {
      "enable_transcription": true,
      "enable_topics": true,
      "enable_subtitles": true
    }
  }
}
```

**Use case:** Match lectures by number, exclude backups and copies.

### Example 4: Multi-Platform Upload

```json
{
  "name": "Public Lectures",
  "matching_rules": {
    "keywords": ["public", "публичная"]
  },
  "metadata_config": {
    "title_template": "{display_name}",
    "description_template": "{summary}\n\nТемы:\n{topics}",
    "youtube": {
      "privacy": "public",
      "playlist_id": "PLxxx_Public"
    },
    "vk": {
      "group_id": 123456,
      "album_id": "public_lectures"
    }
  },
  "output_config": {
    "preset_ids": [1, 2],
    "auto_upload": true
  }
}
```

**Use case:** Upload public lectures to both YouTube and VK.

### Example 5: Case-Sensitive Matching

```json
{
  "name": "API Lectures",
  "matching_rules": {
    "keywords": ["API", "REST", "GraphQL"],
    "case_sensitive": true,
    "exclude_keywords": ["api testing"]
  }
}
```

**Use case:** Match "API" but not "api", exclude "api testing".

---

## Best Practices

### Template Organization

1. **Order Matters**: Create specific templates first, catch-all templates last
2. **Use Exclusions**: Prevent catch-all templates from matching everything
3. **Draft Mode**: Test templates in draft mode before activating
4. **Descriptive Names**: Use clear, descriptive template names

### Matching Rules

1. **Start Simple**: Use `keywords` for most cases
2. **Use Patterns Carefully**: Regex patterns are powerful but can be confusing
3. **Test Exclusions**: Use `exclude_keywords` to prevent unwanted matches
4. **Source Binding**: Use `source_ids` to bind templates to specific sources

### Processing Config

1. **Provide Context**: Use `prompt` to improve transcription quality
2. **Set Language**: Specify `language` for better accuracy
3. **Topic Granularity**: Use `"long"` for detailed topics, `"short"` for summaries

### Metadata Config

1. **Template Variables**: Use variables for dynamic content
2. **Platform Specificity**: Override common settings per platform
3. **Topics Display**: Configure format and filtering for clean output

### Output Config

1. **Test First**: Start with `auto_upload=false`, test manually
2. **Multiple Presets**: Use multiple presets for multi-platform uploads
3. **Caption Control**: Set `upload_captions=true` for better accessibility

---

## API Endpoints

### Input Sources
- `GET /api/v1/input-sources` - List sources
- `POST /api/v1/input-sources` - Create source
- `GET /api/v1/input-sources/{id}` - Get source
- `PATCH /api/v1/input-sources/{id}` - Update source
- `DELETE /api/v1/input-sources/{id}` - Delete source
- `POST /api/v1/input-sources/{id}/sync` - Sync recordings

### Output Presets
- `GET /api/v1/output-presets` - List presets
- `POST /api/v1/output-presets` - Create preset
- `GET /api/v1/output-presets/{id}` - Get preset
- `PATCH /api/v1/output-presets/{id}` - Update preset
- `DELETE /api/v1/output-presets/{id}` - Delete preset

### Recording Templates
- `GET /api/v1/templates` - List templates
- `POST /api/v1/templates` - Create template
- `GET /api/v1/templates/{id}` - Get template
- `PATCH /api/v1/templates/{id}` - Update template
- `DELETE /api/v1/templates/{id}` - Delete template
- `POST /api/v1/templates/from-recording/{recording_id}` - Create from recording

---

## Troubleshooting

### Recording Not Matched by Template

**Check:**
1. Template is `is_active=true` and `is_draft=false`
2. Recording matches `source_ids` (if specified)
3. Recording not excluded by `exclude_keywords` or `exclude_patterns`
4. Template order (older templates checked first)

### Template Matches Wrong Recordings

**Fix:**
1. Add `exclude_keywords` to prevent unwanted matches
2. Make `patterns` more specific
3. Add `source_ids` filter
4. Reorder templates (recreate in correct order)

### Upload Fails

**Check:**
1. Credential is valid and not expired
2. Preset `is_active=true`
3. Platform-specific requirements met (e.g., playlist exists)
4. File size within platform limits

---

**For more information, see:**
- [TECHNICAL.md](./TECHNICAL.md) - Technical architecture
- [TECHNICAL.md](./TECHNICAL.md) - API documentation
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment guide
