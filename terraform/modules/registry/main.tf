# Yandex Container Registry. Holds backend + frontend images. IAM is scoped
# at the registry level (not folder) so other resources in the folder don't
# need to be aware of these specific permissions.

variable "folder_id" {
  type = string
}

variable "project_prefix" {
  type = string
}

variable "pusher_service_account_id" {
  type        = string
  description = "Service account allowed to push images (CI)."
}

variable "puller_service_account_id" {
  type        = string
  description = "Service account allowed to pull images (the VM)."
}

resource "yandex_container_registry" "leap" {
  folder_id = var.folder_id
  name      = var.project_prefix
}

resource "yandex_container_registry_iam_binding" "pusher" {
  registry_id = yandex_container_registry.leap.id
  role        = "container-registry.images.pusher"
  members = [
    "serviceAccount:${var.pusher_service_account_id}",
  ]
}

resource "yandex_container_registry_iam_binding" "puller" {
  registry_id = yandex_container_registry.leap.id
  role        = "container-registry.images.puller"
  members = [
    "serviceAccount:${var.puller_service_account_id}",
  ]
}
