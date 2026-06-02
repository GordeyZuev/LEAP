# Root module: wires every sub-module together.
#
# Single source of truth for the LEAP production infrastructure on Yandex Cloud.
# Run from this directory:  terraform init && terraform apply

provider "yandex" {
  token     = var.yc_token != "" ? var.yc_token : null
  cloud_id  = var.yc_cloud_id
  folder_id = var.yc_folder_id
  zone      = var.yc_zone
}

# ---------------------------------------------------------------------------
# Read OAuth + AI credentials from local files in backend/config/.
#
# Terraform `.tfvars` doesn't allow function calls, so we read the files here
# instead. These paths are stable (relative to the `terraform/` directory).
# Override via `var.oauth_*_json` / `var.fireworks_*` / `var.deepseek_api_key`
# in tfvars if you want to inject creds without keeping files on disk.
# ---------------------------------------------------------------------------
locals {
  config_dir = "${path.module}/../backend/config"

  oauth_zoom_json    = var.oauth_zoom_json != "" ? var.oauth_zoom_json : try(file("${local.config_dir}/oauth_zoom.json"), "")
  oauth_youtube_json = var.oauth_youtube_json != "" ? var.oauth_youtube_json : try(file("${local.config_dir}/oauth_google.json"), "")
  oauth_vk_json      = var.oauth_vk_json != "" ? var.oauth_vk_json : try(file("${local.config_dir}/oauth_vk.json"), "")
  oauth_yadisk_json  = var.oauth_yadisk_json != "" ? var.oauth_yadisk_json : try(file("${local.config_dir}/oauth_yandex_disk.json"), "")

  fireworks_creds      = try(jsondecode(file("${local.config_dir}/fireworks_creds.json")), {})
  fireworks_api_key    = var.fireworks_api_key != "" ? var.fireworks_api_key : try(local.fireworks_creds.api_key, "")
  fireworks_account_id = var.fireworks_account_id != "" ? var.fireworks_account_id : try(local.fireworks_creds.account_id, "")

  deepseek_creds   = try(jsondecode(file("${local.config_dir}/deepseek_creds.json")), {})
  deepseek_api_key = var.deepseek_api_key != "" ? var.deepseek_api_key : try(local.deepseek_creds.api_key, "")
}

# ---------------------------------------------------------------------------
# IAM — service accounts + bindings
# ---------------------------------------------------------------------------
module "iam" {
  source = "./modules/iam"

  folder_id      = var.yc_folder_id
  project_prefix = var.project_prefix
}

# ---------------------------------------------------------------------------
# Object Storage — main bucket + backups bucket
# ---------------------------------------------------------------------------
module "storage" {
  source = "./modules/storage"

  folder_id      = var.yc_folder_id
  project_prefix = var.project_prefix
  domain         = var.domain

  # Static access key created by IAM module — needed to create buckets via S3 API
  storage_access_key_id     = module.iam.storage_static_key_id
  storage_secret_access_key = module.iam.storage_static_key_secret
}

# ---------------------------------------------------------------------------
# Container Registry — backend + frontend images
# ---------------------------------------------------------------------------
module "registry" {
  source = "./modules/registry"

  folder_id      = var.yc_folder_id
  project_prefix = var.project_prefix

  pusher_service_account_id = module.iam.ci_sa_id
  puller_service_account_id = module.iam.vm_sa_id
}

# ---------------------------------------------------------------------------
# Lockbox — every production secret in one place
# ---------------------------------------------------------------------------
module "secrets" {
  source = "./modules/secrets"

  folder_id      = var.yc_folder_id
  project_prefix = var.project_prefix

  # Auto-generated random secrets are computed inside the module.
  # User-supplied secrets are passed through.
  storage_access_key_id     = module.iam.storage_static_key_id
  storage_secret_access_key = module.iam.storage_static_key_secret

  oauth_zoom_json    = local.oauth_zoom_json
  oauth_youtube_json = local.oauth_youtube_json
  oauth_vk_json      = local.oauth_vk_json
  oauth_yadisk_json  = local.oauth_yadisk_json

  fireworks_api_key    = local.fireworks_api_key
  fireworks_account_id = local.fireworks_account_id
  deepseek_api_key     = local.deepseek_api_key

  grafana_admin_user = var.grafana_admin_user

  loki_s3_bucket = module.storage.logs_bucket_name

  # Grant the VM service account permission to read this secret
  vm_service_account_id = module.iam.vm_sa_id
}

# ---------------------------------------------------------------------------
# DNS — Yandex DNS zone + A record (optional; can be skipped if user manages DNS elsewhere)
# ---------------------------------------------------------------------------
module "dns" {
  count  = var.manage_dns ? 1 : 0
  source = "./modules/dns"

  folder_id    = var.yc_folder_id
  domain       = var.domain
  vm_public_ip = module.compute.public_ip
}

# ---------------------------------------------------------------------------
# Compute — the VM that runs the docker compose stack
# ---------------------------------------------------------------------------
module "compute" {
  source = "./modules/compute"

  folder_id      = var.yc_folder_id
  zone           = var.yc_zone
  project_prefix = var.project_prefix

  platform_id  = var.vm_platform_id
  cores        = var.vm_cores
  memory_gb    = var.vm_memory_gb
  disk_gb      = var.vm_disk_gb
  disk_type    = var.vm_disk_type
  image_family = var.vm_image_family

  ssh_public_key   = var.ssh_public_key
  ssh_allowed_cidr = var.ssh_allowed_cidr

  service_account_id = module.iam.vm_sa_id

  cloud_init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    folder_id         = var.yc_folder_id
    domain            = var.domain
    cert_email        = var.cert_email
    lockbox_secret_id = module.secrets.lockbox_secret_id
    registry_id       = module.registry.registry_id
    s3_bucket         = module.storage.main_bucket_name
    github_owner      = var.github_owner
    github_repo       = var.github_repo
    github_branch     = var.github_branch
  })
}
