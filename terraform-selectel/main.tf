resource "selectel_vpc_keypair_v2" "main" {
  name       = "leap-prod"
  public_key = file(pathexpand(var.ssh_public_key_path))
  user_id    = selectel_iam_serviceuser_v1.openstack.id
}

resource "openstack_networking_network_v2" "private" {
  name           = "leap"
  admin_state_up = true

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
  ]
}

resource "openstack_networking_subnet_v2" "private" {
  name        = "leap"
  network_id  = openstack_networking_network_v2.private.id
  cidr        = "10.10.2.0/24"
  ip_version  = 4
  enable_dhcp = true

  # Yandex DNS plus a public resolver, so the VM can reach Object Storage and Container Registry.
  dns_nameservers = ["77.88.8.8", "8.8.8.8"]
}

data "openstack_networking_network_v2" "external" {
  name     = "external-network"
  external = true

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
  ]
}

resource "openstack_networking_router_v2" "main" {
  name                = "leap"
  admin_state_up      = true
  external_network_id = data.openstack_networking_network_v2.external.id

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
  ]
}

resource "openstack_networking_router_interface_v2" "main" {
  router_id = openstack_networking_router_v2.main.id
  subnet_id = openstack_networking_subnet_v2.private.id
}

resource "openstack_networking_secgroup_v2" "main" {
  name        = "leap-prod"
  description = "SSH, HTTP and HTTPS for the LEAP VM"

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
  ]
}

resource "openstack_networking_secgroup_rule_v2" "ingress" {
  for_each = toset(["22", "80", "443"])

  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = tonumber(each.value)
  port_range_max    = tonumber(each.value)
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.main.id
}

resource "openstack_networking_port_v2" "main" {
  name       = "leap-prod"
  network_id = openstack_networking_network_v2.private.id

  fixed_ip {
    subnet_id = openstack_networking_subnet_v2.private.id
  }

  security_group_ids = [openstack_networking_secgroup_v2.main.id]

  depends_on = [openstack_networking_router_interface_v2.main]
}

resource "openstack_networking_floatingip_v2" "main" {
  pool = data.openstack_networking_network_v2.external.name

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
  ]
}

resource "openstack_networking_floatingip_associate_v2" "main" {
  floating_ip = openstack_networking_floatingip_v2.main.address
  port_id     = openstack_networking_port_v2.main.id
}

data "openstack_images_image_v2" "boot" {
  name        = var.image_name
  most_recent = true
  visibility  = "public"

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
  ]
}

resource "openstack_blockstorage_volume_v3" "boot" {
  name                 = "leap-prod-boot"
  size                 = var.volume_size_gb
  image_id             = data.openstack_images_image_v2.boot.id
  volume_type          = var.volume_type
  availability_zone    = var.availability_zone
  enable_online_resize = true

  lifecycle {
    ignore_changes = [image_id]
  }

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
  ]
}

resource "openstack_compute_instance_v2" "vm" {
  name              = "leap-prod"
  flavor_name       = var.flavor_name
  key_pair          = selectel_vpc_keypair_v2.main.name
  availability_zone = var.availability_zone

  network {
    port = openstack_networking_port_v2.main.id
  }

  block_device {
    uuid                  = openstack_blockstorage_volume_v3.boot.id
    source_type           = "volume"
    destination_type      = "volume"
    boot_index            = 0
    delete_on_termination = true
  }

  vendor_options {
    ignore_resize_confirmation = true
  }

  lifecycle {
    ignore_changes = [image_id]
  }

  depends_on = [
    selectel_vpc_project_v2.leap,
    selectel_iam_serviceuser_v1.openstack,
    openstack_networking_floatingip_associate_v2.main,
  ]
}
