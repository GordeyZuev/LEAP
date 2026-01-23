# Documentation Index

**Production-Ready Multi-tenant SaaS for Video Processing**

---

## 🚀 Quick Start

**New to the project?** Start here:

1. [PLAN.md](PLAN.md) - Project overview & roadmap
2. [DEPLOYMENT.md](DEPLOYMENT.md) - Setup guide (dev → production)
3. [OAUTH.md](OAUTH.md) - OAuth setup (YouTube, VK, Zoom)

---

## 📚 Documentation Structure

### 🏗️ Architecture & Design

**Core architecture:**
- [ADR_OVERVIEW.md](ADR_OVERVIEW.md) - Architecture Decision Records
- [ADR_FEATURES.md](ADR_FEATURES.md) - Feature-specific ADRs
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Database schema & migrations
- [TECHNICAL.md](TECHNICAL.md) - Complete technical reference

### ✨ Features & Integration

**Templates & Automation:**
- [TEMPLATES.md](TEMPLATES.md) - Template-driven automation
- [BULK_OPERATIONS_GUIDE.md](BULK_OPERATIONS_GUIDE.md) - Batch processing API

**OAuth & Credentials:**
- [OAUTH.md](OAUTH.md) - Complete OAuth guide
- [OAUTH_MULTIPLE_ACCOUNTS.md](OAUTH_MULTIPLE_ACCOUNTS.md) - Multi-account setup
- [VK_INTEGRATION.md](VK_INTEGRATION.md) - VK Implicit Flow

**Processing:**
- [FIREWORKS_BATCH_API.md](FIREWORKS_BATCH_API.md) - Fireworks Batch API

**Storage:**
- [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md) - Storage architecture
- [MEDIA_SYSTEM_AUDIT.md](MEDIA_SYSTEM_AUDIT.md) - Media system audit

### 🔧 API & Development

**API Documentation:**
- [API_GUIDE.md](API_GUIDE.md) - Pydantic schemas, best practices, admin/quota API
- [TECHNICAL.md](TECHNICAL.md) - REST API endpoints reference

### 🚀 Deployment & Operations

**Setup & Deploy:**
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide
- [PLAN.md](PLAN.md) - Project roadmap (thesis)
- [ROADMAP.md](../ROADMAP.md) - Technical roadmap & TODO

### 🔒 Security

- [security/ARCHITECTURE_DECISION.md](security/ARCHITECTURE_DECISION.md) - Security architecture
- [THUMBNAILS_SECURITY.md](THUMBNAILS_SECURITY.md) - Thumbnail API security & validation
- [security/MULTI_TENANCY_FIXES.md](security/MULTI_TENANCY_FIXES.md) - Multi-tenancy security
- [security/TASK_MIGRATION_GUIDE.md](security/TASK_MIGRATION_GUIDE.md) - Task isolation

### 📜 History

- [CHANGELOG.md](CHANGELOG.md) - Project history

---

## 🗂️ By Task

### "I want to setup OAuth"
→ [OAUTH.md](OAUTH.md) - Complete guide from setup to troubleshooting

### "I want to deploy to production"
→ [DEPLOYMENT.md](DEPLOYMENT.md) - Infrastructure, configuration, monitoring

### "I want to understand templates"
→ [TEMPLATES.md](TEMPLATES.md) - Template system, matching, automation

### "I want to understand the architecture"
→ [ADR_OVERVIEW.md](ADR_OVERVIEW.md) - Core decisions  
→ [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Database structure

### "I want to use the API"
→ [API_GUIDE.md](API_GUIDE.md) - Schemas & best practices  
→ [TECHNICAL.md](TECHNICAL.md) - Endpoints reference

### "I want to process recordings in bulk"
→ [BULK_OPERATIONS_GUIDE.md](BULK_OPERATIONS_GUIDE.md) - Bulk API

### "I want to integrate VK"
→ [VK_INTEGRATION.md](VK_INTEGRATION.md) - VK Implicit Flow setup

---

## 📖 Recommended Learning Path

### For Developers

1. **Architecture:**
   - [ADR_OVERVIEW.md](ADR_OVERVIEW.md) - Understand core decisions
   - [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Database structure
   - [TECHNICAL.md](TECHNICAL.md) - Modules & API

2. **Features:**
   - [TEMPLATES.md](TEMPLATES.md) - Template system
   - [OAUTH.md](OAUTH.md) - OAuth integration

3. **Development:**
   - [API_GUIDE.md](API_GUIDE.md) - Pydantic schemas
   - [DEPLOYMENT.md](DEPLOYMENT.md) - Local setup

### For Users

1. **Setup:**
   - [DEPLOYMENT.md](DEPLOYMENT.md) - Installation
   - [OAUTH.md](OAUTH.md) - Connect accounts

2. **Usage:**
   - [TEMPLATES.md](TEMPLATES.md) - Automate with templates
   - [BULK_OPERATIONS_GUIDE.md](BULK_OPERATIONS_GUIDE.md) - Bulk processing

### For DevOps

1. [DEPLOYMENT.md](DEPLOYMENT.md) - Infrastructure setup
2. [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Database optimization
3. [TECHNICAL.md](TECHNICAL.md) - Monitoring & health checks

---

## 📁 File Overview

| File | Size | Description |
|------|------|-------------|
| [PLAN.md](PLAN.md) | 17K | Project roadmap (thesis) |
| [ROADMAP.md](../ROADMAP.md) | 5K | Technical roadmap & TODO |
| [CHANGELOG.md](CHANGELOG.md) | 15K | Project history |
| [ADR_OVERVIEW.md](ADR_OVERVIEW.md) | 24K | Core architecture decisions |
| [ADR_FEATURES.md](ADR_FEATURES.md) | 19K | Feature-specific ADRs |
| [DATABASE_DESIGN.md](DATABASE_DESIGN.md) | 25K | Database schema & migrations |
| [TECHNICAL.md](TECHNICAL.md) | 44K | Complete technical docs |
| [OAUTH.md](OAUTH.md) | 14K | OAuth setup & integration |
| [VK_INTEGRATION.md](VK_INTEGRATION.md) | 11K | VK Implicit Flow guide |
| [TEMPLATES.md](TEMPLATES.md) | 15K | Template system guide |
| [BULK_OPERATIONS_GUIDE.md](BULK_OPERATIONS_GUIDE.md) | 18K | Bulk processing API |
| [API_GUIDE.md](API_GUIDE.md) | 9K | Pydantic schemas & API |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 16K | Deployment guide |
| [FIREWORKS_BATCH_API.md](FIREWORKS_BATCH_API.md) | 4K | Fireworks Batch API |
| [OAUTH_MULTIPLE_ACCOUNTS.md](OAUTH_MULTIPLE_ACCOUNTS.md) | 3K | Multi-account OAuth |
| [STORAGE_STRUCTURE.md](STORAGE_STRUCTURE.md) | 12K | Storage architecture |
| [MEDIA_SYSTEM_AUDIT.md](MEDIA_SYSTEM_AUDIT.md) | 8K | Media system audit |
| [security/ARCHITECTURE_DECISION.md](security/ARCHITECTURE_DECISION.md) | 4K | Security architecture |
| [security/MULTI_TENANCY_FIXES.md](security/MULTI_TENANCY_FIXES.md) | 3K | Multi-tenancy security |
| [security/TASK_MIGRATION_GUIDE.md](security/TASK_MIGRATION_GUIDE.md) | 2K | Task isolation guide |

**Total:** 20 active documents (~250KB)  
**Roadmap:** 1 technical roadmap (5KB)

---

## 🗄️ Archive

Legacy documentation and historical records: [archive/](archive/)

**Archived:** 9 files (essential history only, cleaned Jan 2026)

---

## 📝 Documentation Guidelines

### Naming Convention

- `UPPERCASE.md` - Core documentation
- `lowercase.md` - Supplementary guides (не используется)

### When to Update

- Architecture changes → Update ADR_OVERVIEW.md or ADR_FEATURES.md
- New features → Update TECHNICAL.md, create examples
- API changes → Update API_GUIDE.md
- Database changes → Update DATABASE_DESIGN.md

### Creating New Docs

**Before creating new file:**
1. Check if content fits into existing docs
2. If truly unique → create with clear scope
3. Update this INDEX.md

**Prefer:** Sections in existing docs over new files

---

## 🔍 Search Tips

**Find by keyword:**
```bash
# OAuth related
grep -r "OAuth" docs/*.md

# Template features
grep -r "template" docs/*.md

# API endpoints
grep -r "POST /api" docs/*.md
```

**Find by file size:**
```bash
ls -lh docs/*.md | sort -h -k5
```

---

## ✅ Quality Metrics

- ✅ **20 active documents** (core + security + storage)
- ✅ **Minimal duplication** (reduced by ~750 lines)
- ✅ **Clear structure** (Architecture, Features, API, Deployment)
- ✅ **Comprehensive guides** (OAuth, Templates, API)
- ✅ **Up-to-date** (January 2026)
- ✅ **Accurate metrics** (verified 19 Jan 2026)

---

**Index last updated:** 19 января 2026  
**Total docs:** 20 active + 1 roadmap + 9 archived  
**Status:** ✅ Clean & optimized (-64% archive size)
