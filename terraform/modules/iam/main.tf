# Three service accounts with the principle of least privilege:
#
#   storage-sa  → owns the static S3 key used by the app to read/write buckets.
#                 Granted storage.editor + container-registry.images.puller.
#   ci-sa       → exclusively for GitHub Actions to push images.
#                 Granted container-registry.images.pusher. A JSON key is generated
#                 and emitted via outputs for `gh secret set`.
#   vm-sa       → attached to the Compute VM. Granted lockbox.payloadViewer so
#                 cloud-init can fetch all production secrets in one call, plus
#                 container-registry.images.puller so docker compose pull works.

variable "folder_id" {
  type = string
}

variable "project_prefix" {
  type = string
}

# ---------------------------------------------------------------------------
# storage-sa  (S3 + registry pull) — used as the static-key principal
# ---------------------------------------------------------------------------
resource "yandex_iam_service_account" "storage" {
  folder_id   = var.folder_id
  name        = "${var.project_prefix}-storage-sa"
  description = "S3 read/write for application; registry pull for VM."
}

resource "yandex_resourcemanager_folder_iam_member" "storage_editor" {
  folder_id = var.folder_id
  role      = "storage.editor"
  member    = "serviceAccount:${yandex_iam_service_account.storage.id}"
}

# storage.admin is required to PUT CORS rules and lifecycle policies on buckets
# (yandex_storage_bucket with cors_rule / lifecycle_rule blocks). Without it,
# bucket creation succeeds but the subsequent CORS/lifecycle update returns 403.
resource "yandex_resourcemanager_folder_iam_member" "storage_admin" {
  folder_id = var.folder_id
  role      = "storage.admin"
  member    = "serviceAccount:${yandex_iam_service_account.storage.id}"
}

resource "yandex_iam_service_account_static_access_key" "storage_static_key" {
  service_account_id = yandex_iam_service_account.storage.id
  description        = "Used by the LEAP backend (boto3) to access Object Storage"
}

# ---------------------------------------------------------------------------
# ci-sa  (registry push, for GitHub Actions)
# ---------------------------------------------------------------------------
resource "yandex_iam_service_account" "ci" {
  folder_id   = var.folder_id
  name        = "${var.project_prefix}-ci-sa"
  description = "GitHub Actions: push images to Container Registry"
}

resource "yandex_resourcemanager_folder_iam_member" "ci_image_pusher" {
  folder_id = var.folder_id
  role      = "container-registry.images.pusher"
  member    = "serviceAccount:${yandex_iam_service_account.ci.id}"
}

# Authorized key (JSON) for GitHub Actions to authenticate via yc-actions/yc-cr-login.
# This file is written to disk on `terraform apply` and emitted via outputs.
resource "yandex_iam_service_account_key" "ci_key" {
  service_account_id = yandex_iam_service_account.ci.id
  description        = "JSON key for GitHub Actions (YC_SA_JSON_CREDENTIALS secret)"
  format             = "PEM_FILE"
  key_algorithm      = "RSA_2048"
}

# ---------------------------------------------------------------------------
# vm-sa  (Lockbox payload viewer + registry pull) — attached to the VM
# ---------------------------------------------------------------------------
resource "yandex_iam_service_account" "vm" {
  folder_id   = var.folder_id
  name        = "${var.project_prefix}-vm-sa"
  description = "Attached to the VM: read Lockbox secrets at boot; pull images."
}

resource "yandex_resourcemanager_folder_iam_member" "vm_lockbox_viewer" {
  folder_id = var.folder_id
  role      = "lockbox.payloadViewer"
  member    = "serviceAccount:${yandex_iam_service_account.vm.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "vm_image_puller" {
  folder_id = var.folder_id
  role      = "container-registry.images.puller"
  member    = "serviceAccount:${yandex_iam_service_account.vm.id}"
}

# storage.uploader: lets the VM SA write pg_backup dumps to the leap-backups
# bucket (scripts/pg_backup.sh runs nightly via cron). Read access to the
# main app bucket is not granted here — the app uses storage-sa's static
# access key via boto3 instead.
resource "yandex_resourcemanager_folder_iam_member" "vm_storage_uploader" {
  folder_id = var.folder_id
  role      = "storage.uploader"
  member    = "serviceAccount:${yandex_iam_service_account.vm.id}"
}
