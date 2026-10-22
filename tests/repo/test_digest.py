"""Markdown digests of one repo and of a workspace."""

from __future__ import annotations

from pathlib import Path

from visio_mcp.repo import digest, discover, scan, workspace_digest


def test_digest_content_and_cap(fastapi_repo: Path):
    info = scan(fastapi_repo)
    d = digest(info)
    assert d.startswith("# orders-api")
    for needle in ("FastAPI", "depends_on db, cache", "Project tree", "requirements.txt", "deploy", "README"):
        assert needle in d
    assert "s3cretpw" not in d
    small = digest(info, max_chars=900)
    assert len(small) <= 900 and small.startswith("# orders-api")


def test_digest_lists_iac_resources(tf_repo: Path, bicep_repo: Path):
    d = digest(scan(tf_repo))
    assert "aws_lambda_function: orders" in d and "aws_sqs_queue" in d
    d = digest(scan(bicep_repo))
    assert "Microsoft.Web/sites" in d and "Microsoft.DocumentDB/databaseAccounts" in d


def test_workspace_digest_links_and_cap(workspace: Path):
    repos = discover(workspace)
    w = workspace_digest(repos)
    assert "3 repositories" in w
    assert "storefront -> orders-api" in w  # API_URL names the other repo
    assert "Shared data store **PostgreSQL**: infra-aws, orders-api" in w
    assert "## Stack" in w
    capped = workspace_digest(repos, max_chars=1500)
    assert len(capped) <= 1500 and "storefront" in capped
