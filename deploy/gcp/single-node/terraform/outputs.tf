output "instance_name" {
  description = "Compute Engine instance name."
  value       = google_compute_instance.node.name
}

output "public_ip" {
  description = "Static public IPv4 used by P2P and HTTPS."
  value       = google_compute_address.node.address
}

output "zone" {
  description = "Compute Engine instance zone."
  value       = var.zone
}

output "iap_ssh_command" {
  description = "Administrative SSH command."
  value       = "gcloud compute ssh ${google_compute_instance.node.name} --project ${var.project_id} --zone ${var.zone} --tunnel-through-iap"
}

output "rpc_tunnel_command" {
  description = "Keep this command running to expose the private RPC on local port 26657."
  value       = "gcloud compute ssh ${google_compute_instance.node.name} --project ${var.project_id} --zone ${var.zone} --tunnel-through-iap -- -N -L 26657:127.0.0.1:26657"
}
