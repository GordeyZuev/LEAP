output "vm_id" {
  value = yandex_compute_instance.vm.id
}

output "public_ip" {
  value = yandex_compute_instance.vm.network_interface[0].nat_ip_address
}

output "internal_ip" {
  value = yandex_compute_instance.vm.network_interface[0].ip_address
}
