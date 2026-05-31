# Two Object Storage buckets:
#   - main:    leap-platform-storage   (videos, transcripts, thumbnails) with CORS
#   - backup:  leap-backups            (pg_dump archives)
#
# Object Storage buckets must be created via the S3 API rather than the YC
# resource manager — so we use the storage-sa's static access key (passed in
# from the IAM module) as the principal.

variable "folder_id" {
  type = string
}

variable "project_prefix" {
  type = string
}

variable "domain" {
  type        = string
  description = "Production domain — used for the CORS AllowedOrigins entry."
}

variable "storage_access_key_id" {
  type      = string
  sensitive = true
}

variable "storage_secret_access_key" {
  type      = string
  sensitive = true
}

resource "yandex_storage_bucket" "main" {
  folder_id  = var.folder_id
  bucket     = "${var.project_prefix}-platform-storage"
  access_key = var.storage_access_key_id
  secret_key = var.storage_secret_access_key

  # CORS for direct video streaming from the browser via presigned URL.
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["https://${var.domain}"]
    allowed_headers = ["*"]
    expose_headers  = ["ETag", "Content-Length", "Content-Range"]
    max_age_seconds = 3600
  }
}

resource "yandex_storage_bucket" "backups" {
  folder_id  = var.folder_id
  bucket     = "${var.project_prefix}-backups"
  access_key = var.storage_access_key_id
  secret_key = var.storage_secret_access_key

  # Postgres dumps: keep 30 days, then expire automatically.
  lifecycle_rule {
    id      = "expire-old-dumps"
    enabled = true

    expiration {
      days = 30
    }
  }
}
