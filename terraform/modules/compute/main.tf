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
# Static (reserved) public IPv4 — survives VM recreation, so DNS A record
# stays valid and end-user browser caches don't break across redeploys.
# ---------------------------------------------------------------------------
resource "yandex_vpc_address" "main" {
  folder_id = var.folder_id
  name      = "${var.project_prefix}-prod-ip"

  external_ipv4_address {
    zone_id = var.zone
  }
}

# ---------------------------------------------------------------------------
# Persistent secondary disk — mounted at /var/lib/docker/volumes on the VM by
# scripts/vm-init.sh. Holds all docker named volumes (postgres, redis, loki,
# prometheus, grafana). `auto_delete = false` on the attachment + this
# resource's `prevent_destroy` together guarantee the disk outlives the VM.
# ---------------------------------------------------------------------------
resource "yandex_compute_disk" "data" {
  folder_id = var.folder_id
  name      = "${var.project_prefix}-prod-data"
  zone      = var.zone
  type      = "network-ssd"
  # Start at 50GB; Yandex supports online grow without downtime —
  # bump this number and run `sudo resize2fs /dev/vdb` on the VM when usage
  # crosses ~70%. Alert wired in Grafana → Disk usage.
  size = 50

  lifecycle {
    prevent_destroy = true
  }
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

  # Persistent data disk for docker volumes (see yandex_compute_disk.data).
  # auto_delete = false: when the VM is destroyed, the disk stays.
  secondary_disk {
    disk_id     = yandex_compute_disk.data.id
    auto_delete = false
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.main.id
    nat                = true
    nat_ip_address     = yandex_vpc_address.main.external_ipv4_address[0].address
    security_group_ids = [yandex_vpc_security_group.main.id]
  }

  metadata = {
    user-data = var.cloud_init
    ssh-keys  = "ubuntu:${var.ssh_public_key}"
  }

  # Durability layer 3 — block accidental destroy and freeze attributes that
  # force replacement, so changes to Ubuntu / cloud-init / ssh-keys no longer
  # trigger a silent destroy+create. To re-run the bootstrap script on the
  # live VM after editing the cloud-init template, use `make deploy-vm-init`.
  # To intentionally replace the VM, comment out `prevent_destroy` first.
  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      metadata,
      boot_disk[0].initialize_params[0].image_id,
    ]
  }
}
