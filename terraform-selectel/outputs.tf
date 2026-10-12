output "public_ip" {
  description = "Floating public IPv4 of leap-prod. SSH user on the Selectel Ubuntu image is root."
  value       = openstack_networking_floatingip_v2.main.address
}

output "pool" {
  value = var.pool
}

output "availability_zone" {
  value = var.availability_zone
}
