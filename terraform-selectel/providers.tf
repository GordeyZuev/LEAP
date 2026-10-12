provider "selectel" {
  domain_name = var.selectel_domain_name
  username    = var.selectel_username
  password    = var.selectel_password
  auth_region = var.pool
  auth_url    = "https://cloud.api.selcloud.ru/identity/v3/"
}

resource "selectel_vpc_project_v2" "leap" {
  name = "leap"

  # Project quotas are the cap we set ourselves. These match what is already
  # stored for ru-9a: 8 cores and 16 GB RAM.
  quotas {
    resource_name = "compute_cores"
    resource_quotas {
      region = "ru-9"
      zone   = "ru-9a"
      value  = 8
    }
  }

  quotas {
    resource_name = "compute_ram"
    resource_quotas {
      region = "ru-9"
      zone   = "ru-9a"
      value  = 16384
    }
  }
}

resource "random_password" "openstack_user" {
  length           = 24
  special          = true
  override_special = "!@#%^*-_=+"
  min_upper        = 1
  min_lower        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "selectel_iam_serviceuser_v1" "openstack" {
  name     = "leap-openstack"
  password = random_password.openstack_user.result

  # Product roles for the server, the fast SSD, the private network,
  # the floating public IP and security groups.
  dynamic "role" {
    for_each = toset([
      "compute.admin",
      "vpc.admin",
      "vpc.external_access.admin",
      "vpc.network_security.admin",
    ])
    content {
      role_name  = role.value
      scope      = "project"
      project_id = selectel_vpc_project_v2.leap.id
    }
  }
}

provider "openstack" {
  auth_url    = "https://cloud.api.selcloud.ru/identity/v3"
  domain_name = var.selectel_domain_name
  tenant_id   = selectel_vpc_project_v2.leap.id
  user_name   = selectel_iam_serviceuser_v1.openstack.name
  password    = selectel_iam_serviceuser_v1.openstack.password
  region      = var.pool
}
