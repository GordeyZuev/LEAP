output "zone_id" {
  value = yandex_dns_zone.main.id
}

output "ns_servers" {
  description = "NS records to enter at the registrar (reg.ru) for delegation"
  # Yandex Cloud's public DNS uses these four servers across all zones.
  value = [
    "ns1.yandexcloud.net",
    "ns2.yandexcloud.net",
  ]
}
