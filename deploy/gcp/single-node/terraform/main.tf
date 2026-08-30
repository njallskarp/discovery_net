locals {
  data_device_name = "${var.name}-data"
  labels = {
    application = "discovery-net"
    managed_by  = "terraform"
  }
  network_tag = "${var.name}-host"
}

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iap" {
  project            = var.project_id
  service            = "iap.googleapis.com"
  disable_on_destroy = false
}

resource "google_compute_network" "node" {
  name                    = "${var.name}-network"
  auto_create_subnetworks = false

  depends_on = [google_project_service.compute]
}

resource "google_compute_subnetwork" "node" {
  name                     = "${var.name}-subnet"
  ip_cidr_range            = "10.80.0.0/24"
  region                   = var.region
  network                  = google_compute_network.node.id
  private_ip_google_access = true
}

resource "google_compute_address" "node" {
  name         = "${var.name}-ipv4"
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"
  region       = var.region
}

resource "google_compute_firewall" "inspector" {
  name      = "${var.name}-inspector"
  network   = google_compute_network.node.name
  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = [local.network_tag]
}

resource "google_compute_firewall" "p2p" {
  name      = "${var.name}-p2p"
  network   = google_compute_network.node.name
  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["26656"]
  }

  source_ranges = sort(tolist(var.trusted_p2p_cidrs))
  target_tags   = [local.network_tag]
}

resource "google_compute_firewall" "iap_ssh" {
  name      = "${var.name}-iap-ssh"
  network   = google_compute_network.node.name
  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = [local.network_tag]
}

data "google_compute_image" "debian" {
  family  = "debian-12"
  project = "debian-cloud"
}

resource "google_compute_disk" "data" {
  name = local.data_device_name
  type = "pd-standard"
  zone = var.zone
  size = var.data_disk_size_gb

  labels = local.labels

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_resource_policy" "daily_snapshots" {
  name   = "${var.name}-daily-snapshots"
  region = var.region

  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "04:00"
      }
    }

    retention_policy {
      max_retention_days    = var.snapshot_retention_days
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }

    snapshot_properties {
      guest_flush       = false
      storage_locations = [var.region]
      labels            = local.labels
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "daily_snapshots" {
  name = google_compute_resource_policy.daily_snapshots.name
  disk = google_compute_disk.data.name
  zone = var.zone
}

resource "google_compute_instance" "node" {
  name                      = var.name
  machine_type              = var.machine_type
  zone                      = var.zone
  allow_stopping_for_update = true
  can_ip_forward            = false
  deletion_protection       = true
  tags                      = [local.network_tag]
  labels                    = local.labels

  boot_disk {
    auto_delete = true

    initialize_params {
      image = data.google_compute_image.debian.self_link
      size  = var.boot_disk_size_gb
      type  = "pd-standard"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = local.data_device_name
    mode        = "READ_WRITE"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.node.id

    access_config {
      nat_ip       = google_compute_address.node.address
      network_tier = "PREMIUM"
    }
  }

  metadata = {
    block-project-ssh-keys = "TRUE"
    enable-oslogin         = "TRUE"
    serial-port-enable     = "FALSE"
    startup-script = templatefile("${path.module}/../scripts/bootstrap-host.sh.tftpl", {
      data_device_name = local.data_device_name
    })
  }

  shielded_instance_config {
    enable_integrity_monitoring = true
    enable_secure_boot          = true
    enable_vtpm                 = true
  }

  depends_on = [google_project_service.compute]
}

resource "google_iap_tunnel_instance_iam_member" "operator" {
  for_each = var.operator_members

  project  = var.project_id
  zone     = var.zone
  instance = google_compute_instance.node.name
  role     = "roles/iap.tunnelResourceAccessor"
  member   = each.value

  depends_on = [google_project_service.iap]
}

resource "google_compute_instance_iam_member" "operator" {
  for_each = var.operator_members

  project       = var.project_id
  zone          = var.zone
  instance_name = google_compute_instance.node.name
  role          = "roles/compute.osAdminLogin"
  member        = each.value
}

resource "google_project_iam_member" "operator_compute_viewer" {
  for_each = var.operator_members

  project = var.project_id
  role    = "roles/compute.viewer"
  member  = each.value
}
