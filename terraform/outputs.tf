# ---------------------------------------------------------------------------
# What you need after `terraform apply`
# ---------------------------------------------------------------------------

output "vm_public_ip" {
  description = "Public IPv4 of the VM"
  value       = module.compute.public_ip
}

output "vm_ssh_command" {
  description = "Quick SSH access"
  value       = "ssh ubuntu@${module.compute.public_ip}"
}

output "domain_url" {
  value = "https://${var.domain}"
}

output "registry_id" {
  description = "Container Registry ID — used by GitHub Actions to push images"
  value       = module.registry.registry_id
}

output "lockbox_secret_id" {
  description = "Lockbox secret holding all production credentials. Rotate via `yc lockbox secret add-version`."
  value       = module.secrets.lockbox_secret_id
}

output "main_bucket" {
  value = module.storage.main_bucket_name
}

output "backups_bucket" {
  value = module.storage.backups_bucket_name
}

output "ns_servers" {
  description = "NS records to set at the registrar (reg.ru) for DNS delegation"
  value       = var.manage_dns ? module.dns[0].ns_servers : null
}

# ---------------------------------------------------------------------------
# Setup hints (next-steps printed at the end of `terraform apply`)
# ---------------------------------------------------------------------------

output "github_secrets_commands" {
  description = "Ready-to-paste shell commands to populate GitHub Actions secrets"
  value       = <<-EOT
    # 1. Write the YC service account key for CI:
    terraform -chdir=terraform output -raw ci_authorized_key_json > ci-sa-key.json

    # 2. Push everything into GitHub Secrets (requires `gh auth login`):
    gh secret set YC_SA_JSON_CREDENTIALS < ci-sa-key.json
    gh secret set YC_REGISTRY_ID --body "${module.registry.registry_id}"
    gh secret set VPS_HOST       --body "${var.domain}"
    gh secret set VPS_USER       --body "ubuntu"
    gh secret set VPS_SSH_KEY    < $HOME/.ssh/id_ed25519     # private key matching var.ssh_public_key
    gh secret set VPS_DEPLOY_PATH --body "/opt/leap"

    # 3. Remove the local CI key file (it's also stored in tfstate):
    rm -f ci-sa-key.json
  EOT
}

output "ci_authorized_key_json" {
  description = "Authorized key JSON for CI (used by github_secrets_commands above). Treat as sensitive."
  value       = module.iam.ci_authorized_key_json
  sensitive   = true
}

output "grafana_admin_password" {
  description = "Initial Grafana admin password. Also lives in Lockbox; change after first login."
  value       = module.secrets.grafana_password
  sensitive   = true
}

output "next_steps" {
  value = <<-EOT

    ============================================================
     LEAP infrastructure created. Next steps:
    ============================================================

    1) DNS delegation
       Sign in to https://www.reg.ru/ → leap-platform.ru → DNS
       Replace NS records with:
         - ns1.yandexcloud.net
         - ns2.yandexcloud.net
       Wait 1–24h for propagation (check: dig ${var.domain})

    2) GitHub Secrets
       Run the commands printed in `terraform output github_secrets_commands`

    3) VM bootstrap progress
       SSH to ${module.compute.public_ip} and tail:
         sudo tail -f /var/log/leap-bootstrap.log

    4) Smoke test (after DNS + bootstrap complete)
       curl -fsS https://${var.domain}/api/v1/health    # 200 OK
       open https://${var.domain}                       # frontend
       open https://${var.domain}/grafana/              # basic auth: admin / (terraform output grafana_admin_password)

    5) Push to main → automatic deploys via GitHub Actions

  EOT
}
