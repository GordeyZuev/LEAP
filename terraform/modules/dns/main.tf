# Yandex DNS zone + A record. Requires NS delegation at the registrar (reg.ru).
# Terraform creates the zone; the user copies NS values into reg.ru.
#
# After `terraform apply`, run `terraform output dns_ns_servers` and paste those
# four NS records into reg.ru's panel. Propagation: 1-24 hours.

variable "folder_id" {
  type = string
}

variable "domain" {
  description = "Domain, e.g. leap-platform.ru — the zone will be created for this."
  type        = string
}

variable "vm_public_ip" {
  description = "Public IPv4 of the VM — used as the A record value."
  type        = string
}

resource "yandex_dns_zone" "main" {
  folder_id   = var.folder_id
  name        = replace(var.domain, ".", "-")
  description = "Public DNS zone for ${var.domain}"
  zone        = "${var.domain}."
  public      = true
}

# Apex A record  (yourdomain.com → VM)
resource "yandex_dns_recordset" "apex" {
  zone_id = yandex_dns_zone.main.id
  name    = "${var.domain}."
  type    = "A"
  ttl     = 300
  data    = [var.vm_public_ip]
}

# www → same VM
resource "yandex_dns_recordset" "www" {
  zone_id = yandex_dns_zone.main.id
  name    = "www.${var.domain}."
  type    = "CNAME"
  ttl     = 300
  data    = ["${var.domain}."]
}
