# Compute VM + Security Group + network glue.
#
# The VM picks up its identity from `service_account_id` so the on-host `yc`
# CLI authenticates automatically (no keys baked into the image / cloud-init).
# All bootstrap logic lives in `cloud-init.yaml.tftpl`, rendered by the root
# module and passed in via `var.cloud_init`.

variable "folder_id" {
  type = string
}

variable "zone" {
  type = string
}

variable "project_prefix" {
  type = string
}

variable "platform_id" {
  type = string
}

variable "cores" {
  type = number
}

variable "memory_gb" {
  type = number
}

variable "disk_gb" {
  type = number
}

variable "disk_type" {
  type = string
}

variable "image_family" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "ssh_allowed_cidr" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "service_account_id" {
  type        = string
  description = "Service account attached to the VM (must have lockbox.payloadViewer + container-registry.images.puller)"
}

variable "cloud_init" {
  type        = string
  description = "Rendered cloud-init YAML content (#cloud-config ...)"
  sensitive   = true # because we may embed secret references inside
}

# ---------------------------------------------------------------------------
# VPC: a default network + subnet for the VM
# ---------------------------------------------------------------------------
resource "yandex_vpc_network" "main" {
  folder_id = var.folder_id
  name      = "${var.project_prefix}-net"
}

resource "yandex_vpc_subnet" "main" {
  folder_id      = var.folder_id
  name           = "${var.project_prefix}-subnet"
  zone           = var.zone
  network_id     = yandex_vpc_network.main.id
  v4_cidr_blocks = ["10.10.0.0/24"]
}

# ---------------------------------------------------------------------------
# Security group
# ---------------------------------------------------------------------------
resource "yandex_vpc_security_group" "main" {
  folder_id  = var.folder_id
  name       = "${var.project_prefix}-sg"
  network_id = yandex_vpc_network.main.id

  ingress {
    description    = "SSH"
    protocol       = "TCP"
    port           = 22
    v4_cidr_blocks = var.ssh_allowed_cidr
  }

  ingress {
    description    = "HTTP (ACME challenges + redirect)"
    protocol       = "TCP"
    port           = 80
    v4_cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description    = "HTTPS"
    protocol       = "TCP"
    port           = 443
    v4_cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description    = "Outbound all"
    protocol       = "ANY"
    v4_cidr_blocks = ["0.0.0.0/0"]
    from_port      = 0
    to_port        = 65535
  }
}

# ---------------------------------------------------------------------------
# Image lookup
# ---------------------------------------------------------------------------
data "yandex_compute_image" "boot" {
  family = var.image_family
}

# ---------------------------------------------------------------------------
# VM
# ---------------------------------------------------------------------------
resource "yandex_compute_instance" "vm" {
  folder_id   = var.folder_id
  name        = "${var.project_prefix}-prod-01"
  zone        = var.zone
  platform_id = var.platform_id

  service_account_id = var.service_account_id

  resources {
    cores  = var.cores
    memory = var.memory_gb
  }

  boot_disk {
    initialize_params {
      image_id = data.yandex_compute_image.boot.id
      size     = var.disk_gb
      type     = var.disk_type
    }
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.main.id
    nat                = true
    security_group_ids = [yandex_vpc_security_group.main.id]
  }

  metadata = {
    user-data = var.cloud_init
    ssh-keys  = "ubuntu:${var.ssh_public_key}"
  }
}
