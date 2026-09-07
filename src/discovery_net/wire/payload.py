"""Payloads supported by the application protocol."""

from discovery_net.artifacts.edge_revocation import EdgeRevocation
from discovery_net.domains.math.models import Contribution, ContributionRelation

type Artifact = Contribution | ContributionRelation | EdgeRevocation
