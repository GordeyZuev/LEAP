output "storage_sa_id" {
  value = yandex_iam_service_account.storage.id
}

output "ci_sa_id" {
  value = yandex_iam_service_account.ci.id
}

output "vm_sa_id" {
  value = yandex_iam_service_account.vm.id
}

output "storage_static_key_id" {
  description = "Static access key ID for boto3 (STORAGE_S3_ACCESS_KEY_ID)"
  value       = yandex_iam_service_account_static_access_key.storage_static_key.access_key
  sensitive   = true
}

output "storage_static_key_secret" {
  description = "Static access key secret for boto3 (STORAGE_S3_SECRET_ACCESS_KEY)"
  value       = yandex_iam_service_account_static_access_key.storage_static_key.secret_key
  sensitive   = true
}

output "ci_authorized_key_json" {
  description = "Authorized key JSON for GitHub Actions yc-cr-login. Write to file and store as YC_SA_JSON_CREDENTIALS GH secret."
  value = jsonencode({
    id                 = yandex_iam_service_account_key.ci_key.id
    service_account_id = yandex_iam_service_account_key.ci_key.service_account_id
    created_at         = yandex_iam_service_account_key.ci_key.created_at
    key_algorithm      = yandex_iam_service_account_key.ci_key.key_algorithm
    public_key         = yandex_iam_service_account_key.ci_key.public_key
    private_key        = yandex_iam_service_account_key.ci_key.private_key
  })
  sensitive = true
}
