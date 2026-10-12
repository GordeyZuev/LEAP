variable "selectel_domain_name" {
  description = "Selectel account number (panel, top-right). Not a Yandex cloud id."
  type        = string
}

variable "selectel_username" {
  description = "Existing service user with roles member (account) and iam.admin. Create it once in IAM."
  type        = string
}

variable "selectel_password" {
  description = "Password of that service user. Set in terraform.tfvars, which is gitignored."
  type        = string
  sensitive   = true
}

variable "pool" {
  description = "Selectel pool. ru-9 is Saint Petersburg. ru-6 is closed for new resources during the incident."
  type        = string
  default     = "ru-9"
}

variable "availability_zone" {
  description = "Pool segment for the VM, the fast SSD volume and the cloud router."
  type        = string
  default     = "ru-9a"
}

variable "flavor_name" {
  description = "Standard line, 8 vCPU, 16 GB RAM, no local disk. Boot disk is a separate volume."
  type        = string
  default     = "SL1.8-16384"
}

variable "volume_type" {
  description = "Fast SSD in the chosen segment."
  type        = string
  default     = "fast.ru-9a"
}

variable "volume_size_gb" {
  description = "Boot volume size. Current Yandex VM uses 100 GB boot + 50 GB data."
  type        = number
  default     = 160
}

variable "image_name" {
  description = "Public Selectel image name."
  type        = string
  default     = "Ubuntu 22.04 LTS 64-bit"
}

variable "ssh_public_key_path" {
  description = "Public key installed on the server. Selectel Ubuntu images log in as root."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}
