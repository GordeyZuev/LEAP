output "main_bucket_name" {
  value = yandex_storage_bucket.main.bucket
}

output "backups_bucket_name" {
  value = yandex_storage_bucket.backups.bucket
}

output "logs_bucket_name" {
  value = yandex_storage_bucket.logs.bucket
}
