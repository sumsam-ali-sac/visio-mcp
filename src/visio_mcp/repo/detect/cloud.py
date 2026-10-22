"""Cloud provider detection (Azure / AWS / GCP) from dependencies, IaC and config markers."""

from __future__ import annotations

from ..lists import add_unique
from ..model import RepoInfo


CLOUD_PREFIXES = {
    "azure": ("azure-", "@azure/", "azure.", "microsoft.azure", "com.azure", "msal", "azure:"),
    "aws": ("boto3", "botocore", "aws-sdk", "@aws-sdk/", "awssdk.", "aws-lambda", "software.amazon.awssdk",
            "github.com/aws/aws-sdk-go", "aws-cdk", "aws_cdk", "@aws-cdk/", "amazon."),
    "gcp": ("google-cloud-", "@google-cloud/", "google.cloud", "cloud.google.com/go", "firebase-admin",
            "com.google.cloud", "google-auth"),
}


CLOUD_PRETTY = {"azure": "Azure", "aws": "AWS", "gcp": "GCP"}


def detect_cloud(info: RepoInfo, deps: set[str], clouds: list[str], markers: set[str]) -> None:
    """Fill info.cloud (ordered Azure, AWS, GCP); `clouds` are providers already seen in IaC."""
    for cloud, prefixes in CLOUD_PREFIXES.items():
        if any(d.startswith(prefixes) for d in deps):
            add_unique(info.cloud, cloud)
    for c in clouds:
        add_unique(info.cloud, c)
    if {"azd", "azure-functions"} & markers:
        add_unique(info.cloud, "azure")
    if {"gae", "firebase"} & markers:
        add_unique(info.cloud, "gcp")
    if "sam" in markers:
        add_unique(info.cloud, "aws")
    if any("cloudbuild" in ci for ci in info.ci):
        add_unique(info.cloud, "gcp")
    if any(ci.endswith("buildspec.yml") for ci in info.ci):
        add_unique(info.cloud, "aws")
    info.cloud.sort(key=lambda c: ["azure", "aws", "gcp"].index(c))
