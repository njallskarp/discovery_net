variable "project_id" {
  description = "Google Cloud project that owns the node."
  type        = string

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id must not be blank."
  }
}

variable "region" {
  description = "Google Cloud region."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Google Cloud zone."
  type        = string
  default     = "us-central1-a"

  validation {
    condition     = startswith(var.zone, "${var.region}-")
    error_message = "zone must be inside region."
  }
}

variable "name" {
  description = "Base name for node resources."
  type        = string
  default     = "discovery-node"

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.name))
    error_message = "name must be a valid Compute Engine resource name."
  }
}

variable "machine_type" {
  description = "Compute Engine machine type."
  type        = string
  default     = "e2-small"
}

variable "boot_disk_size_gb" {
  description = <<-DESC
    Boot disk size in GiB. Docker's images, layers, and build cache live here, not on
    the node-data disk, and deploy.sh builds the node image on the host. A completed
    build leaves roughly 5 GiB of image and cache on top of the base system, so 10 GiB
    fills the root filesystem. A full root filesystem takes the whole host down, not
    just the build: systemd cannot write its state, container health checks fail, and
    sshd cannot open a session, so the symptom looks like a network outage.
  DESC
  type        = number
  default     = 30

  validation {
    condition     = var.boot_disk_size_gb >= 20
    error_message = "boot_disk_size_gb must be at least 20; a host image build does not fit in less."
  }
}

variable "data_disk_size_gb" {
  description = "Persistent node-data disk size in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.data_disk_size_gb >= 10
    error_message = "data_disk_size_gb must be at least 10."
  }
}

variable "enable_inspector" {
  description = "Expose the read-only inspector on public HTTPS ports 80 and 443."
  type        = bool
  default     = true
}

variable "inspector_hostname" {
  description = "Optional DNS hostname for normal HTTPS. Leave blank to use the static public IPv4 certificate."
  type        = string
  default     = ""

  validation {
    condition = (
      trimspace(var.inspector_hostname) == "" ||
      can(regex("^(?i:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\\.(?i:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$", trimspace(var.inspector_hostname)))
    )
    error_message = "inspector_hostname must be blank or a DNS hostname without a scheme, path, or port."
  }
}

variable "acme_email" {
  description = "Let's Encrypt account contact email. Required when enable_inspector is true."
  type        = string
  default     = ""

  validation {
    condition = (
      trimspace(var.acme_email) == "" ||
      can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", trimspace(var.acme_email)))
    )
    error_message = "acme_email must be blank or a valid email address."
  }
}

variable "trusted_p2p_cidrs" {
  description = "Public IPv4 CIDRs permitted to connect to CometBFT P2P port 26656. Use /32 per peer."
  type        = set(string)

  validation {
    condition = (
      length(var.trusted_p2p_cidrs) > 0 &&
      alltrue([
        for cidr in var.trusted_p2p_cidrs :
        can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", cidr)) &&
        try(cidrhost(cidr, 0), "") == split("/", cidr)[0]
      ])
    )
    error_message = "trusted_p2p_cidrs must contain only individual IPv4 addresses in /32 notation."
  }
}

variable "operator_members" {
  description = "IAM members allowed to administer this instance through IAP and OS Login."
  type        = set(string)

  validation {
    condition = (
      length(var.operator_members) > 0 &&
      alltrue([
        for member in var.operator_members :
        can(regex("^(user|group):[^[:space:]]+$", member))
      ])
    )
    error_message = "operator_members must contain at least one user: or group: IAM member."
  }
}

variable "snapshot_retention_days" {
  description = "Number of days to retain automatic data-disk snapshots."
  type        = number
  default     = 7

  validation {
    condition     = var.snapshot_retention_days >= 1
    error_message = "snapshot_retention_days must be positive."
  }
}
