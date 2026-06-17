# A single Lockbox secret holds every production credential in one payload.
#
# Two kinds of entries live here:
#
#   1. Env vars         — keys without `FILE__` prefix.
#                         Materialized into /opt/leap/.env on the VM.
#                         Example: DB_PASSWORD, SECURITY_JWT_SECRET_KEY, etc.
#
#   2. Config files     — keys prefixed with `FILE__<name>.json`.
#                         Materialized to backend/config/<name>.json on the VM.
#                         Required for OAuth (Zoom, Google/YouTube, VK, Yandex
#                         Disk) and AI providers (Fireworks, DeepSeek) — these
#                         modules ONLY accept file paths, not env vars.
#
# Rotation: `yc lockbox secret add-version --payload-from-file=...` then SSH to
# the VM and run /opt/leap/refresh-env.sh; the script re-fetches the latest
# version and re-materializes both .env and config/*.json files.

variable "folder_id" {
  type = string
}

variable "project_prefix" {
  type = string
}

variable "vm_service_account_id" {
  description = "Service account on the VM that needs read access to this secret"
  type        = string
}

# S3 access (from IAM module's static key)
variable "storage_access_key_id" {
  type      = string
  sensitive = true
}
variable "storage_secret_access_key" {
  type      = string
  sensitive = true
}

# OAuth provider credentials — raw JSON content for each provider's config file.
# See variables.tf in the root module for the source-of-truth comment.
variable "oauth_zoom_json" {
  type      = string
  sensitive = true
}
variable "oauth_youtube_json" {
  type      = string
  sensitive = true
}
variable "oauth_vk_json" {
  type      = string
  sensitive = true
}
variable "oauth_yadisk_json" {
  type      = string
  sensitive = true
}

# ---------------------------------------------------------------------------
# Helpers — pull individual fields out of the OAuth JSON blobs so we can also
# expose them as env vars (the OAuthSettings validator in backend/config/settings.py
# checks OAUTH_<provider>_CLIENT_ID/SECRET to decide whether the provider is
# "enabled").  We tolerate empty / malformed JSON by defaulting to "".
# ---------------------------------------------------------------------------
locals {
  zoom    = try(jsondecode(var.oauth_zoom_json), {})
  youtube = try(jsondecode(var.oauth_youtube_json), {})
  vk      = try(jsondecode(var.oauth_vk_json), {})

  zoom_client_id        = try(local.zoom.client_id, "")
  zoom_client_secret    = try(local.zoom.client_secret, "")
  youtube_client_id     = try(local.youtube.web.client_id, "")
  youtube_client_secret = try(local.youtube.web.client_secret, "")
  vk_client_id          = try(local.vk.app_id, "")
  vk_client_secret      = try(local.vk.client_secret, "")
}

# Email (SMTP) — only the password is a secret; the rest goes into .env.static
variable "email_smtp_user" {
  type        = string
  sensitive   = true
  description = "SMTP login (e.g. leap.platform@yandex.ru)"
}
variable "email_smtp_password" {
  type        = string
  sensitive   = true
  description = "SMTP password (app password, not the mailbox password)"
}

# AI providers
variable "assemblyai_api_key" {
  type      = string
  sensitive = true
}
variable "deepseek_api_key" {
  type      = string
  sensitive = true
}

# Grafana admin
variable "grafana_admin_user" {
  type = string
}

# Loki S3 backend — bucket name comes from the storage module; the same
# storage SA static key is reused (it has full S3 access in the folder).
variable "loki_s3_bucket" {
  type        = string
  description = "Object Storage bucket holding Loki chunks + TSDB index"
}

# ---------------------------------------------------------------------------
# Auto-generated secrets
# ---------------------------------------------------------------------------
resource "random_password" "db_password" {
  length  = 32
  special = false # avoid edge cases in docker-compose env var parsing
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "random_password" "grafana_admin_password" {
  length  = 24
  special = false
}

resource "random_password" "grafana_ro_password" {
  length  = 24
  special = false
}

# Fernet key for SECURITY_ENCRYPTION_KEY. `random_id.b64_url` produces a
# URL-safe base64 string of `byte_length` random bytes — exactly the format
# Fernet expects (urlsafe-base64-encoded 32 bytes). Stateful: the value is
# stored in Terraform state and persists across plans/applies, so the
# encryption key never silently rotates (encrypted DB rows stay decryptable).
resource "random_id" "fernet_key" {
  byte_length = 32
}

# ---------------------------------------------------------------------------
# Lockbox secret + version
# ---------------------------------------------------------------------------
resource "yandex_lockbox_secret" "main" {
  folder_id   = var.folder_id
  name        = "${var.project_prefix}-prod-secrets"
  description = "All production credentials for the LEAP stack (fetched at VM boot)"
}

resource "yandex_lockbox_secret_version" "v1" {
  secret_id   = yandex_lockbox_secret.main.id
  description = "Initial version managed by Terraform"

  # ============ Env vars (go into /opt/leap/.env) ============

  entries {
    key        = "DB_PASSWORD"
    text_value = random_password.db_password.result
  }
  entries {
    key        = "SECURITY_JWT_SECRET_KEY"
    text_value = random_password.jwt_secret.result
  }
  entries {
    key = "SECURITY_ENCRYPTION_KEY"
    # `random_id.b64_url` uses Go's base64.RawURLEncoding which omits the `=`
    # padding. Python's Fernet validator (cryptography lib) requires standard
    # urlsafe-base64 *with* padding (44 chars for 32-byte key). We append the
    # one missing `=` so the value is a valid Fernet key.
    text_value = "${random_id.fernet_key.b64_url}="
  }
  entries {
    key        = "GRAFANA_USER"
    text_value = var.grafana_admin_user
  }
  entries {
    key        = "GRAFANA_PASSWORD"
    text_value = random_password.grafana_admin_password.result
  }
  # Postgres role used by Grafana's LEAP-DB datasource (provisioned by
  # alembic migration 023). Migration is a no-op when this is unset, so
  # bootstrapping order is: terraform apply → refresh-env.sh → migrate.
  entries {
    key        = "GRAFANA_RO_PASSWORD"
    text_value = random_password.grafana_ro_password.result
  }

  # S3 credentials
  entries {
    key        = "STORAGE_S3_ACCESS_KEY_ID"
    text_value = var.storage_access_key_id
  }
  entries {
    key        = "STORAGE_S3_SECRET_ACCESS_KEY"
    text_value = var.storage_secret_access_key
  }

  # Loki S3 backend — chunks + index in the dedicated logs bucket.
  # Re-uses the storage SA static key (already authorised in the folder).
  entries {
    key        = "LOKI_S3_BUCKET"
    text_value = var.loki_s3_bucket
  }
  entries {
    key        = "LOKI_S3_ACCESS_KEY_ID"
    text_value = var.storage_access_key_id
  }
  entries {
    key        = "LOKI_S3_SECRET_ACCESS_KEY"
    text_value = var.storage_secret_access_key
  }

  # OAuthSettings (settings.py) checks OAUTH_<provider>_CLIENT_ID/SECRET to
  # decide whether each provider is enabled. We mirror the file-based creds as
  # env vars so the validator doesn't warn "X OAuth enabled but credentials missing".
  entries {
    key        = "OAUTH_ZOOM_CLIENT_ID"
    text_value = local.zoom_client_id
  }
  entries {
    key        = "OAUTH_ZOOM_CLIENT_SECRET"
    text_value = local.zoom_client_secret
  }
  entries {
    key        = "OAUTH_YOUTUBE_CLIENT_ID"
    text_value = local.youtube_client_id
  }
  entries {
    key        = "OAUTH_YOUTUBE_CLIENT_SECRET"
    text_value = local.youtube_client_secret
  }
  entries {
    key        = "OAUTH_VK_CLIENT_ID"
    text_value = local.vk_client_id
  }
  entries {
    key        = "OAUTH_VK_CLIENT_SECRET"
    text_value = local.vk_client_secret
  }

  # ============ Config files (materialized to backend/config/<name>.json) ============
  #
  # Each `FILE__<name>` entry is decoded by /opt/leap/refresh-env.sh and
  # written verbatim to /opt/leap/backend/config/<name>.json. The application
  # reads only the file (OAuth modules, FireworksConfig.from_file, etc.), so
  # provider-specific extras (VK's `use_vk_id`, etc.) are preserved.

  entries {
    key        = "FILE__oauth_zoom.json"
    text_value = var.oauth_zoom_json
  }
  entries {
    key        = "FILE__oauth_google.json"
    text_value = var.oauth_youtube_json
  }
  entries {
    key        = "FILE__oauth_vk.json"
    text_value = var.oauth_vk_json
  }
  entries {
    key        = "FILE__oauth_yandex_disk.json"
    text_value = var.oauth_yadisk_json
  }

  entries {
    key = "FILE__assemblyai_creds.json"
    text_value = jsonencode({
      api_key = var.assemblyai_api_key
    })
  }

  entries {
    key = "FILE__deepseek_creds.json"
    text_value = jsonencode({
      api_key = var.deepseek_api_key
    })
  }

  # Email SMTP credentials — appended last to avoid shifting existing entries
  entries {
    key        = "EMAIL_SMTP_USER"
    text_value = var.email_smtp_user
  }
  entries {
    key        = "EMAIL_SMTP_PASSWORD"
    text_value = var.email_smtp_password
  }
}

# ---------------------------------------------------------------------------
# Grant the VM SA read access to this specific secret
# ---------------------------------------------------------------------------
resource "yandex_lockbox_secret_iam_binding" "vm_viewer" {
  secret_id = yandex_lockbox_secret.main.id
  role      = "lockbox.payloadViewer"
  members = [
    "serviceAccount:${var.vm_service_account_id}",
  ]
}
