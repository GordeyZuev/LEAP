# ============================================================================
# Yandex Cloud auth
# ============================================================================

variable "yc_token" {
  description = "Yandex Cloud OAuth token or IAM token. Leave empty to use `yc` CLI default profile."
  type        = string
  sensitive   = true
  default     = ""
}

variable "yc_cloud_id" {
  description = "Yandex Cloud ID (yc config get cloud-id)"
  type        = string
}

variable "yc_folder_id" {
  description = "Yandex Cloud folder ID (yc config get folder-id)"
  type        = string
}

variable "yc_zone" {
  description = "Default availability zone for VM and zonal resources"
  type        = string
  default     = "ru-central1-a"
}

# ============================================================================
# Application — naming + domain
# ============================================================================

variable "project_prefix" {
  description = "Short name used as the prefix for every created resource (bucket, SA, VM, registry, etc.)"
  type        = string
  default     = "leap"
}

variable "domain" {
  description = "Production domain, e.g. leap-platform.ru. Drives DNS records, CORS, OAuth callbacks, certbot."
  type        = string
}

variable "cert_email" {
  description = "Email address Let's Encrypt sends expiry notices to."
  type        = string
}

# ============================================================================
# VM
# ============================================================================

variable "vm_platform_id" {
  description = "Compute platform. standard-v3 is the current Cascade Lake generation."
  type        = string
  default     = "standard-v3"
}

variable "vm_cores" {
  description = "vCPUs allocated to the VM"
  type        = number
  default     = 8
}

variable "vm_memory_gb" {
  description = "Memory (GB) allocated to the VM"
  type        = number
  default     = 16
}

variable "vm_disk_gb" {
  description = "Boot disk size (GB)"
  type        = number
  default     = 100
}

variable "vm_disk_type" {
  description = "Disk type: network-ssd (default), network-hdd (cheaper), network-ssd-nonreplicated"
  type        = string
  default     = "network-ssd"
}

variable "vm_image_family" {
  description = "Image family for the boot disk. Ubuntu 22.04 LTS by default."
  type        = string
  default     = "ubuntu-2204-lts"
}

variable "ssh_public_key" {
  description = "SSH public key (single line, e.g. `ssh-ed25519 AAAA...`) granted to the `ubuntu` user."
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "Source CIDR ranges allowed to SSH (port 22). Default open; tighten to your IP/32 for production."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ============================================================================
# DNS
# ============================================================================

variable "manage_dns" {
  description = "When true, Terraform creates a Yandex DNS zone + A record. Requires NS delegation at the registrar."
  type        = bool
  default     = true
}

# ============================================================================
# GitHub repo (for cloud-init `git clone`)
# ============================================================================

variable "github_owner" {
  description = "GitHub owner (user or org) hosting the LEAP repository"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "ZoomUploader"
}

variable "github_branch" {
  description = "Branch to clone on first boot (rolling deploys are handled by GitHub Actions, not cloud-init)"
  type        = string
  default     = "main"
}

# ============================================================================
# OAuth provider credentials — raw JSON content of each provider's config file.
#
# Each variable holds the entire JSON written verbatim into Lockbox as a
# `FILE__oauth_<provider>.json` entry; on the VM, cloud-init materializes it
# back into backend/config/oauth_<provider>.json. The application reads only
# the file (see backend/api/services/oauth_platforms.py), so this preserves
# provider-specific keys (e.g. VK's `use_vk_id`, `implicit_flow_app_id`,
# Google's `web` wrapper).
#
# Usage in terraform.tfvars:
#   oauth_zoom_json    = file("../backend/config/oauth_zoom.json")
#   oauth_youtube_json = file("../backend/config/oauth_google.json")
#   oauth_vk_json      = file("../backend/config/oauth_vk.json")
#   oauth_yadisk_json  = file("../backend/config/oauth_yandex_disk.json")
# ============================================================================

variable "oauth_zoom_json" {
  description = "Raw JSON content of backend/config/oauth_zoom.json"
  type        = string
  sensitive   = true
  default     = ""
}

variable "oauth_youtube_json" {
  description = "Raw JSON content of backend/config/oauth_google.json (Google OAuth client_secrets.json)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "oauth_vk_json" {
  description = "Raw JSON content of backend/config/oauth_vk.json"
  type        = string
  sensitive   = true
  default     = ""
}

variable "oauth_yadisk_json" {
  description = "Raw JSON content of backend/config/oauth_yandex_disk.json"
  type        = string
  sensitive   = true
  default     = ""
}

# ============================================================================
# AI providers (AssemblyAI ASR, DeepSeek topic extraction)
# ============================================================================

variable "assemblyai_api_key" {
  description = "AssemblyAI API key for speech-to-text transcription."
  type        = string
  sensitive   = true
  default     = ""
}

variable "deepseek_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

# ============================================================================
# Grafana basic-auth
# ============================================================================

variable "grafana_admin_user" {
  type    = string
  default = "admin"
}

# ============================================================================
# Email / SMTP
# ============================================================================

variable "email_smtp_user" {
  description = "SMTP login for transactional email (e.g. leap.platform@yandex.ru)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "email_smtp_password" {
  description = "SMTP app-password for the email account"
  type        = string
  sensitive   = true
  default     = ""
}
