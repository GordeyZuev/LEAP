# `terraform/` — Yandex Cloud infra

Full deployment walkthrough lives in
**[backend/docs/guides/DEPLOYMENT.md](../backend/docs/guides/DEPLOYMENT.md)**.

Day-to-day:

```bash
make deploy        # terraform apply  (from repo root)
make plan          # preview
make status        # show all outputs
make destroy       # ⚠ wipes production
```

This directory creates, in YC:

- 3 Service Accounts (storage / CI / VM) with least-privilege IAM
- 2 Object Storage buckets (main + backups, with CORS)
- Container Registry
- Lockbox secret with every production credential
- Compute VM with cloud-init bootstrap
- VPC + Security Group + DNS zone

## Files

```
main.tf                  — provider + module composition
variables.tf             — all input variables (~25)
outputs.tf               — VM IP, registry ID, NS servers, GH secrets commands
versions.tf              — required providers
terraform.tfvars.example — copy → terraform.tfvars (gitignored)
cloud-init.yaml.tftpl    — first-boot script for the VM
modules/iam              — service accounts + bindings + access keys
modules/storage          — buckets + CORS
modules/registry         — Container Registry + IAM
modules/secrets          — Lockbox secret (env vars + FILE__ entries)
modules/compute          — VM + VPC + security group
modules/dns              — DNS zone + A record (optional, on by default)
```

## Local dev notes

- `terraform fmt -recursive` — autoformat
- The `external` data source in `modules/secrets/scripts/generate_fernet.py`
  runs Python 3 (stdlib only) to mint a Fernet key. Make sure `python3` is on PATH.
- State is local by default. For team use, configure a remote backend in
  Object Storage (see DEPLOYMENT.md §Operational).
