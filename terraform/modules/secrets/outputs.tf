output "lockbox_secret_id" {
  description = "ID of the Lockbox secret to fetch on the VM via `yc lockbox payload get --id <this>`"
  value       = yandex_lockbox_secret.main.id
}

output "grafana_password" {
  value     = random_password.grafana_admin_password.result
  sensitive = true
}
