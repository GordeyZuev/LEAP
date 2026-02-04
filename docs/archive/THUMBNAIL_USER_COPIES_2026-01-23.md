# Thumbnail User Copies Approach

**Date:** 2026-01-23
**Status:** ✅ Implemented
**Decision:** Each user gets their own copies of shared templates

## Problem Solved

**Original issue:** Name collision risk when user uploads thumbnail with same name as shared template.

**Example scenario:**
```
shared: storage/shared/thumbnails/applied_python.png
user uploads: applied_python.png
→ Collision! Which one to use?
```

## Solution: User Copies at Registration

**Simple approach:** Each user gets their own copies of all templates.

### Implementation

**1. At registration (`api/routers/auth.py`):**
```python
# Copy all 22 shared templates to user's directory
thumbnail_manager.initialize_user_thumbnails(user.user_slug, copy_templates=True)
```

**Result:**
```
storage/shared/thumbnails/          # Source (22 templates)
  ├── applied_python.png
  ├── ml_extra.png
  └── ...

storage/users/user_000001/thumbnails/  # User 1 copies
  ├── applied_python.png            # Own copy
  ├── ml_extra.png                  # Own copy
  └── ...

storage/users/user_000002/thumbnails/  # User 2 copies
  ├── applied_python.png            # Own copy
  ├── ml_extra.png                  # Own copy
  └── ...
```

**2. User can:**
- ✅ Keep templates as-is
- ✅ Rename them
- ✅ Delete unwanted ones
- ✅ Upload custom thumbnails with any name (no conflicts!)
- ✅ Modify/replace template copies

**3. In templates/presets:**
```json
{
  "metadata_config": {
    "thumbnail_name": "ml_extra.png"  // Just filename
  }
}
```

**4. API resolves to user's file:**
```python
# api/tasks/upload.py
resolved_path = thumbnail_manager.get_thumbnail_path(
    user_slug=user.user_slug,
    thumbnail_name="ml_extra.png",
    fallback_to_template=True  # For backward compatibility only
)
# → storage/users/user_000001/thumbnails/ml_extra.png
```

## Benefits

### 1. No Naming Conflicts
Each user has their own namespace - no collisions possible.

### 2. User Autonomy
Users can fully customize their thumbnails:
- Delete templates they don't need
- Rename to better names
- Replace with custom versions

### 3. Simplicity
- No complex fallback logic needed
- Predictable behavior: filename → user's file
- Easy to understand and debug

### 4. Backward Compatible
- Old users (without copies) still work via fallback
- New users get copies automatically
- Gradual migration possible

## Code Changes

### Files Modified

1. **`api/routers/auth.py`**
   - Changed: `copy_templates=False` → `copy_templates=True`
   - Effect: New users get template copies

2. **`api/routers/thumbnails.py`**
   - Removed: Template collision check (no longer needed)
   - Simplified: No special handling for template names

3. **`utils/thumbnail_manager.py`**
   - Updated docstrings to recommend `copy_templates=True`
   - Kept fallback for backward compatibility

4. **`api/tasks/upload.py`**
   - No changes needed (already uses `get_thumbnail_path()`)

### Documentation Updated

1. **`docs/THUMBNAILS_SECURITY.md`**
   - Added section on user copies approach
   - Updated isolation explanation
   - Added registration flow description

2. **`docs/CHANGELOG.md`**
   - Documented new user registration behavior
   - Explained backward compatibility

3. **`docs/TEMPLATES.md`**
   - Updated all examples to use filename only
   - Removed old `media/templates/thumbnails/` paths
   - Added note about thumbnail_name format

## Migration Guide

### For New Users
✅ Nothing to do! Templates copied automatically at registration.

### For Existing Users (without copies)
Two options:

**Option 1: Automatic (lazy copy)**
- System uses fallback to shared templates
- Works transparently
- Copy templates manually if want to customize:
  ```bash
  cp -r storage/shared/thumbnails/* storage/users/user_XXXXXX/thumbnails/
  ```

**Option 2: One-time migration script** (if needed)
```python
from utils.thumbnail_manager import get_thumbnail_manager
from database.auth_models import UserModel

# For each user without thumbnail copies
for user in users:
    manager = get_thumbnail_manager()
    manager.initialize_user_thumbnails(user.user_slug, copy_templates=True)
```

## Testing

### Verify New User Registration
```bash
# 1. Register new user
curl -X POST '/api/v1/auth/register' \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "..."}'

# 2. Check thumbnails directory
ls storage/users/user_000XXX/thumbnails/
# Should see 22 template files

# 3. List thumbnails via API
curl -X GET '/api/v1/thumbnails' -H 'Authorization: Bearer ...'
# Should return all 22 templates as user_thumbnails
```

### Verify Upload Works
```bash
# Upload video with template using thumbnail
curl -X POST '/api/v1/recordings/123/upload' \
  -H 'Authorization: Bearer ...' \
  -d '{
    "platform": "youtube",
    "preset_id": 1
  }'

# Check logs for thumbnail resolution
# Should show: "Using thumbnail: storage/users/user_XXXXXX/thumbnails/ml_extra.png"
```

### Verify No Collisions
```bash
# User uploads file with template name
curl -X POST '/api/v1/thumbnails' \
  -F 'file=@my_custom.png' \
  -F 'custom_filename=applied_python' \
  -H 'Authorization: Bearer ...'

# Should succeed (no collision error)
# Overwrites user's copy, not shared template
```

## FAQ

**Q: What if I delete all my templates?**
A: You can re-copy them anytime or upload custom ones.

**Q: Can I share thumbnails with other users?**
A: No. Each user has independent copies. Upload to shared templates (admin only).

**Q: Do existing templates get updated?**
A: No. Each user's copy is independent. Updates to shared templates don't affect users.

**Q: How much storage does this use?**
A: 22 templates × ~1MB each × N users ≈ 22MB per user. Negligible for most cases.

**Q: What happens if shared templates change?**
A: New users get new versions. Existing users keep their copies unchanged.

## Alternatives Considered

### ❌ Alternative 1: Validation against templates
Check if uploaded filename matches template, reject it.

**Rejected because:**
- Users can't override templates
- Inflexible
- More complex validation logic

### ❌ Alternative 2: Namespacing (user_*, template_*)
Prefix files with `user_` or `template_`.

**Rejected because:**
- Ugly filenames
- Harder to use in templates
- Still need resolution logic

### ✅ Alternative 3: User copies (chosen)
Each user gets their own copies.

**Chosen because:**
- Simple and intuitive
- No special cases
- Users have full control
- No conflicts possible

---

**Implementation:** KISS principle - simplest solution that works
**Related:** docs/THUMBNAILS_SECURITY.md, docs/STORAGE_STRUCTURE_IMPLEMENTED.md
