# Thumbnail API Security & Validation

**Date:** 2026-01-23
**Status:** ✅ Implemented

## Security Measures

### 1. URL-Based Responses (No Path Disclosure)

**Problem:** Returning filesystem paths exposes internal structure:
```json
{
  "path": "storage/users/user_000001/thumbnails/ai_hse.jpg"  // ❌ Security issue!
}
```

**Solution:** Return REST API URLs instead:
```json
{
  "name": "ai_hse.jpg",
  "url": "/api/v1/thumbnails/ai_hse.jpg",  // ✅ Secure
  "is_template": false
}
```

**Benefits:**
- ✅ No information disclosure about filesystem structure
- ✅ No user enumeration (user_slug hidden)
- ✅ Encapsulation - can change storage without breaking UI
- ✅ URL works for both user and template thumbnails (API handles routing)

### 2. Path Traversal Protection

**Validation in `_validate_thumbnail_name()`:**

```python
def _validate_thumbnail_name(thumbnail_name: str) -> None:
    """Prevent path traversal attacks."""
    if "/" in thumbnail_name or "\\" in thumbnail_name or thumbnail_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid thumbnail name")
```

**Protected against:**
- ❌ `../../../etc/passwd`
- ❌ `..\\..\\windows\\system32`
- ❌ `.ssh/id_rsa`

### 3. Format Validation

**Supported formats (centralized constant):**

```python
# api/routers/thumbnails.py & utils/thumbnail_manager.py
SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg"}
```

**Validation at upload:**

```python
async def _validate_and_read_file(file: UploadFile):
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(400, detail=f"Unsupported format: {file_ext}")
```

**What's checked:**
- ✅ File extension must be `.png`, `.jpg`, or `.jpeg`
- ✅ Case-insensitive check (`.PNG` → `.png`)
- ✅ Maximum file size: 2MB
- ✅ Filename validation: alphanumeric, dash, underscore only

### 4. User Isolation

**Each user has isolated directory with their own copies:**

```
storage/users/user_000001/thumbnails/  # User 1 (has own copy of all templates + custom)
storage/users/user_000002/thumbnails/  # User 2 (has own copy of all templates + custom)
```

**At registration:** Each new user gets copies of all shared templates (22 files)
- Templates are copied from `storage/shared/thumbnails/` to user's directory
- Users can modify, rename, or delete their copies
- Changes don't affect other users

**Access control:**
- ✅ JWT token required for all operations
- ✅ Users can only access their own thumbnails
- ✅ Each user has independent thumbnail namespace
- ✅ No shared state between users

### 5. Filename Sanitization

**Strict mode (custom filename):**
```python
validate_filename("my_photo", strict=True)
# ✅ Allowed: alphanumeric, dash, underscore
# ❌ Rejected: spaces, special characters, unicode
```

**Permissive mode (original filename):**
```python
validate_filename("Мой фото! 2024.png", strict=False)
# → "______2024"  (sanitized)
```

**Rules:**
- Maximum length: 100 characters
- No path separators or dots at start
- English letters, numbers, `-`, `_` only

## API Endpoints Security

### GET `/api/v1/thumbnails`

**Authentication:** Required (JWT)

**Returns:**
- User's thumbnails (including copies of shared templates from registration)

**No sensitive data exposed:**
```json
{
  "thumbnails": [
    {
      "name": "my_photo.jpg",
      "url": "/api/v1/thumbnails/my_photo.jpg",  // No user_slug!
      "is_template": false
    },
    {
      "name": "ml_extra.png",
      "url": "/api/v1/thumbnails/ml_extra.png",  // Copy of template
      "is_template": false
    }
  ]
}
```

**Note:** Each user gets their own copies of all shared templates at registration (22 files).
Users can modify or delete these copies independently.

### POST `/api/v1/thumbnails` (Create)

**Validation:**
1. ✅ JWT authentication
2. ✅ Format check (`.png`, `.jpg`, `.jpeg`)
3. ✅ Size limit (2MB)
4. ✅ Filename sanitization
5. ✅ Conflict check (409 if exists)

**Security:**
- Fails if file already exists (use PUT to update)
- Saves to user-specific directory only

### PUT `/api/v1/thumbnails/{name}` (Update)

**Validation:**
1. ✅ JWT authentication
2. ✅ Path traversal check on `{name}`
3. ✅ Format check
4. ✅ Extension must match URL parameter

**Security:**
- Idempotent operation
- Can only update user's own thumbnails
- Cannot update templates

### GET `/api/v1/thumbnails/{name}` (Download)

**Access control:**
1. ✅ JWT authentication
2. ✅ Path traversal check
3. ✅ Checks user's directory first
4. ✅ Falls back to templates (if `use_template=true`)

**Security:**
- User can only access their own thumbnails + templates
- Cannot access other users' thumbnails
- Proper MIME type based on extension

### DELETE `/api/v1/thumbnails/{name}`

**Security:**
- ✅ Can only delete user's own thumbnails
- ✅ Cannot delete templates
- ✅ Returns 404 if not found (no info leak)

## Using Thumbnails in Templates & Presets

**✅ Correct way - use filename only:**

```json
{
  "name": "YouTube Lecture Preset",
  "platform": "youtube",
  "preset_metadata": {
    "title_template": "{display_name}",
    "thumbnail_path": "ml_extra.png"
  }
}
```

**How it works:**
1. **At registration:** All shared templates are copied to user's directory
   - `storage/shared/thumbnails/ml_extra.png` → `storage/users/user_000001/thumbnails/ml_extra.png`
   - Users get their own copies of all 22 templates
   - Users can modify, delete, or keep them as-is

2. **In templates/presets:** You specify only the filename: `"ml_extra.png"`

3. **At upload time:** API resolves filename to user's file:
   - Checks: `storage/users/user_000001/thumbnails/ml_extra.png`
   - Uses this file for upload

**Benefits:**
- ✅ No naming conflicts - each user has their own namespace
- ✅ Users can customize templates (rename, replace, delete)
- ✅ No fallback complexity - everything in one place
- ✅ Simple and predictable behavior

**Hierarchy:**
```
metadata_config (template):
  vk.thumbnail_path          # Platform-specific (highest priority)
  youtube.thumbnail_path     # Platform-specific
  thumbnail_path             # Common fallback

preset_metadata (output preset):
  thumbnail_path             # Used if not in template
```

**Examples:**
```json
// Template with common thumbnail
{
  "metadata_config": {
    "thumbnail_path": "python_base.png"
  }
}

// Template with platform-specific thumbnails
{
  "metadata_config": {
    "youtube": {
      "thumbnail_path": "youtube_cover.jpg"
    },
    "vk": {
      "thumbnail_path": "vk_cover.png"
    }
  }
}

// Output preset with thumbnail
{
  "preset_metadata": {
    "thumbnail_path": "hse_ai.jpg"
  }
}
```

## Best Practices for UI

### 1. Use URLs, not paths

```typescript
// ✅ CORRECT:
<img src={thumbnail.url} alt={thumbnail.name} />

// ❌ WRONG (will break):
<img src={`file://${thumbnail.path}`} alt={thumbnail.name} />
```

### 2. Handle 404 gracefully

```typescript
<img
  src={thumbnail.url}
  alt={thumbnail.name}
  onError={(e) => {
    e.currentTarget.src = '/fallback.png';
  }}
/>
```

### 3. Check file format before upload

```typescript
const ALLOWED_FORMATS = ['.png', '.jpg', '.jpeg'];

function isValidFormat(filename: string): boolean {
  const ext = filename.toLowerCase().match(/\.[^.]+$/)?.[0];
  return ext ? ALLOWED_FORMATS.includes(ext) : false;
}
```

### 4. Show upload progress for large files

```typescript
// Max size is 2MB, show warning for files > 1.5MB
if (file.size > 1.5 * 1024 * 1024) {
  showWarning('File is large, upload may take time');
}
```

## Testing Security

### Test Path Traversal

```bash
# Should return 400:
curl -X GET '/api/v1/thumbnails/../../../etc/passwd' -H 'Authorization: Bearer ...'
curl -X GET '/api/v1/thumbnails/.ssh/id_rsa' -H 'Authorization: Bearer ...'
```

### Test Format Validation

```bash
# Should return 400:
curl -X POST '/api/v1/thumbnails' \
  -F 'file=@malicious.exe' \
  -H 'Authorization: Bearer ...'

curl -X POST '/api/v1/thumbnails' \
  -F 'file=@script.sh' \
  -H 'Authorization: Bearer ...'
```

### Test User Isolation

```bash
# User A uploads thumbnail
curl -X POST '/api/v1/thumbnails' \
  -F 'file=@photo.png' \
  -F 'custom_filename=secret' \
  -H 'Authorization: Bearer <USER_A_TOKEN>'

# User B tries to access it (should fail or fallback to template)
curl -X GET '/api/v1/thumbnails/secret.png' \
  -H 'Authorization: Bearer <USER_B_TOKEN>'
# Returns 404 or template (not User A's file)
```

## Migration Notes

**Breaking change in API response:**

**Before (v0.9.3):**
```json
{
  "path": "storage/users/user_000001/thumbnails/photo.jpg"
}
```

**After (v0.9.4+):**
```json
{
  "url": "/api/v1/thumbnails/photo.jpg"
}
```

**UI update required:** Change `thumbnail.path` → `thumbnail.url`

---

**Implementation:** Following OWASP security guidelines
**Reference:** [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
