# Technical Roadmap

**Last Updated:** 22 января 2026  
**Status:** Active Development

**Version:** v0.9.4 - Storage Structure Migration Complete

---

## ✅ Completed (January 2026)

### v0.9.4 - Storage Structure Migration (January 22, 2026)
- ✅ **ID-based file naming** - No display_name in paths (no Cyrillic!)
- ✅ **Clean architecture** - `file_storage/` (code) + `storage/` (data separation)
- ✅ **StoragePathBuilder** - Single source of truth for all paths
- ✅ **S3-ready backends** - Abstract storage interface (LOCAL implemented)
- ✅ **Legacy code removal** - Deleted UserPathManager, TranscriptionService
- ✅ **user_slug required** - TranscriptionManager no optional parameters
- ✅ **Documentation** - CHANGELOG.md, STORAGE_STRUCTURE_IMPLEMENTED.md

**Impact:**
- Removed: 2 files (~6000 bytes of legacy code)
- Modified: 14 files (11 code + 3 docs)
- Created: 10 files (file_storage/ module + docs)
- Architecture: Clean separation of concerns

### Unified Configuration System
- ✅ Single source of truth: `config/settings.py`
- ✅ Environment-driven (200+ variables in `.env.example`)
- ✅ Pydantic validation with 12 sections
- ✅ Celery retry via env variables
- ✅ Removed legacy: ~1200 lines of code

### Two-Level Recording Deletion
- ✅ Soft delete → Files cleanup → Hard delete
- ✅ Per-user retention settings
- ✅ Maintenance tasks (auto-expire, cleanup, hard-delete)
- ✅ Prevent re-sync of deleted recordings

### Zoom Authentication
- ✅ Pydantic models with discriminator
- ✅ Support for Server-to-Server + OAuth 2.0
- ✅ Type-safe credentials

---

## 🚀 High Priority

### PHASE 1: Structured Logging
**Priority:** CRITICAL  
**Effort:** 1 day

- [ ] Production-ready logging (JSON + text modes)
- [ ] Context propagation (request_id, user_id, task_id)
- [ ] Sentry integration
- [ ] File rotation

### PHASE 2: Security & File Naming
**Priority:** ~~CRITICAL~~ → **COMPLETED v0.9.4** ✅  
**Effort:** 2-3 days → **DONE**

- [x] ID-based file naming (no display_name in paths) - **COMPLETED v0.9.4**
- [x] Storage structure migration - **COMPLETED v0.9.4**
- [x] User ID migration to UUID/ULID - **COMPLETED**
- [ ] Fix OutputTarget queries (add user_id filter) - **TODO**
- [ ] Composite indexes for performance - **TODO**

### PHASE 3: File Lifecycle Management
**Priority:** HIGH  
**Effort:** 1-2 days

- [ ] FileManager with auto quota tracking
- [ ] Orphaned files cleanup
- [ ] Celery periodic tasks (cleanup temp files, expired recordings)
- [ ] Automated quota sync

---

## 📋 Medium Priority

### PHASE 4: Directory Structure Cleanup
**Effort:** 1 day

- [ ] Унифицировать audio directories
- [ ] Optimize thumbnail storage (fallback to templates)
- [ ] Remove legacy directories
- [ ] Migration to new structure

### PHASE 5: Storage Abstraction
**Status:** 🚧 50% Complete (v0.9.4)  
**Effort:** 2-3 days → **1-2 days remaining**

- [x] Abstract storage interface (LocalStorage + S3) - **COMPLETED v0.9.4**
- [x] LocalStorageBackend implementation - **COMPLETED v0.9.4**
- [x] StoragePathBuilder (single source of truth) - **COMPLETED v0.9.4**
- [ ] S3StorageBackend implementation - **TODO** (2-3 hours)
- [ ] Integrate backends into code (replace Path operations) - **TODO**
- [ ] S3 backend with presigned URLs - **TODO**
- [ ] Migration script to S3 - **TODO**
- [ ] Quota integration - **TODO**

### PHASE 6: Architecture Cleanup
**Effort:** 2-3 days

- [ ] Унифицировать модели (only RecordingModel)
- [ ] Remove FileCredentialProvider (use DB only)
- [ ] Split large routers (recordings.py: 2510 lines)
- [ ] Move business logic from routers to services

---

## 🔮 Future Features

### External Sources (5-6 days)
- [ ] yt-dlp integration (download from 1000+ sites)
- [ ] Yandex Disk (input + output)
- [ ] Google Drive support

### Testing (5-7 days)
- [ ] Unit tests (60%+ coverage)
- [ ] Integration tests
- [ ] E2E tests
- [ ] CI/CD pipeline

### Deployment & Monitoring (3-4 days)
- [ ] Docker optimization (multi-stage builds)
- [ ] Kubernetes manifests
- [ ] Prometheus + Grafana
- [ ] Production documentation

---

## 🐛 Quick Fixes (Ready to implement)

1. **Fix Delete Recording** (30 min)  
   Location: `api/repositories/recording_repos.py:566`  
   - Delete files BEFORE DB record
   - Update quota tracking

2. **Security: OutputTarget Queries** (15 min)  
   Location: `api/repositories/recording_repos.py:244, 342`  
   - Add user_id filter to prevent cross-user access

3. **Composite Indexes** (20 min)  
   - recordings(user_id, status)
   - recordings(user_id, template_id)
   - output_targets(user_id, status)

4. **Cleanup Temp Files Script** (20 min)  
   - Remove files older than 24 hours in temp_processing

5. **Remove Duplicate Thumbnails** (15 min)  
   - Find and remove user thumbnails identical to templates

---

## 📊 Metrics & Goals

**Code Quality:**
- Remove legacy code: ✅ 1500+ lines removed
- Reduce file size: Target 500 lines max per file
- Type coverage: Target 100%

**Performance:**
- API response time: <200ms (p95)
- Storage optimization: -20% via cleanup
- Quota accuracy: 100% via auto-tracking

**Security:**
- Multi-tenant isolation: 100%
- Encrypted credentials: ✅ Fernet
- Rate limiting: ✅ Per user

---

## 📖 Documentation

- **Detailed Plan:** `docs/archive/plan_detailed.md` (if needed)
- **Architecture:** `docs/TECHNICAL.md`
- **Media Issues:** `docs/STORAGE_STRUCTURE.md`, `docs/MEDIA_SYSTEM_AUDIT.md`

---

**Next Action:** Implement PHASE 1 (Structured Logging)
