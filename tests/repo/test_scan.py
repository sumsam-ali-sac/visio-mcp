"""Profiling a repo folder: languages, frameworks, IaC, CI, data stores."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from visio_mcp.repo import RepoInfo, discover, heuristic_spec, scan


def test_scan_fastapi_repo(fastapi_repo: Path):
    info = scan(fastapi_repo)
    assert isinstance(info, RepoInfo)
    assert info.name == "orders-api" and info.is_git
    assert next(iter(info.languages)) == "Python"
    assert "FastAPI" in info.frameworks and "Celery" in info.frameworks
    assert "requirements.txt" in info.manifests
    assert info.containers == ["Dockerfile"]
    assert "docker-compose.yml" in info.iac
    assert ".github/workflows/ci.yml" in info.ci
    assert "app/main.py" in info.entrypoints
    assert {"PostgreSQL", "Redis"} <= set(info.databases)
    assert "Celery" in info.messaging
    assert {"Stripe", "OpenAI"} <= set(info.external_apis)
    assert info.readme.startswith("# Orders")
    assert info.suggested_types[0] == "architecture"
    assert {"deployment", "pipeline", "erd"} <= set(info.suggested_types)
    assert "FastAPI" in info.summary and "PostgreSQL" in info.summary
    # .gitignore and noise dirs are honored
    assert "generated/big.py" not in " ".join(info.entrypoints)
    assert info.file_count < 20


def test_compose_services_parsed(fastapi_repo: Path):
    info = scan(fastapi_repo)
    svc = info.compose_services
    assert set(svc) == {"api", "db", "cache", "worker"}
    assert svc["api"]["build"] == "." and svc["api"]["depends_on"] == ["db", "cache"]
    assert svc["api"]["ports"] == ["8000:8000"]
    assert svc["db"]["image"] == "postgres:16"
    assert svc["worker"]["depends_on"] == ["db", "cache"]  # flow-style list
    hints = " ".join(svc["api"]["environment_hints"])
    assert "DATABASE_URL" in hints and "s3cretpw" not in hints and "supersecretvalue" not in hints


def test_ci_jobs_ordered_with_needs(fastapi_repo: Path):
    info = scan(fastapi_repo)
    jobs = {j["id"]: j for j in info.ci_jobs}
    assert list(jobs) == ["test", "build", "deploy"]
    assert jobs["build"]["needs"] == ["test"] and jobs["deploy"]["needs"] == ["build"]
    assert jobs["deploy"]["deploy"] and not jobs["test"]["deploy"]
    assert "azure" in info.cloud  # azure/webapps-deploy action


def test_scan_next_repo(next_repo: Path):
    info = scan(next_repo)
    assert info.frameworks[:2] == ["Next.js", "React"]
    assert "MongoDB" in info.databases and "Stripe" in info.external_apis
    assert "package.json" in info.manifests
    assert next(iter(info.languages)) == "TypeScript"
    assert "src/index.ts" in info.entrypoints
    assert "web app" in info.summary


def test_scan_terraform_aws(tf_repo: Path):
    info = scan(tf_repo)
    assert info.cloud == ["aws"]
    assert info.iac_kinds == ["terraform"] and {"main.tf", "variables.tf"} <= set(info.iac)
    types = {r["type"] for r in info.resources}
    assert {"aws_lambda_function", "aws_dynamodb_table", "aws_sqs_queue", "aws_s3_bucket"} <= types
    assert {"DynamoDB", "PostgreSQL"} <= set(info.databases)  # engine = "postgres" on aws_db_instance
    assert "SQS" in info.messaging and "S3" in info.storage
    assert "Terraform" in info.summary and "AWS" in info.summary


def test_scan_bicep_azure(bicep_repo: Path):
    info = scan(bicep_repo)
    assert info.cloud == ["azure"] and info.iac_kinds == ["bicep"]
    types = {r["type"] for r in info.resources}
    assert "Microsoft.Web/sites" in types and "Microsoft.Storage/storageAccounts" in types
    assert {"Cosmos DB"} <= set(info.databases) and "Azure Service Bus" in info.messaging
    assert "Bicep" in info.summary and "Azure" in info.summary


def test_scan_cloudformation_k8s_and_gitlab(tmp_path: Path, write, assert_valid):
    root = tmp_path / "mix"
    write(root, "template.yaml", """\
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  Fn:
    Type: AWS::Serverless::Function
    Properties:
      Handler: app.handler
  Table:
    Type: AWS::DynamoDB::Table
""")
    write(root, "k8s/app.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: web
          image: ghcr.io/acme/web:1.0
          ports:
            - containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  selector:
    app: web
  ports:
    - port: 80
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web
spec:
  rules:
    - http:
        paths:
          - backend:
              service:
                name: web
""")
    write(root, ".gitlab-ci.yml", """\
stages: [build, test, deploy]
build-job:
  stage: build
  script: [make]
test-job:
  stage: test
  script: [make test]
deploy-job:
  stage: deploy
  script: [make deploy]
""")
    info = scan(root)
    assert set(info.iac_kinds) >= {"sam", "kubernetes"}
    assert "AWS Lambda" in info.frameworks and "DynamoDB" in info.databases
    kinds = {(o["kind"], o["name"]) for o in info.k8s_objects}
    assert {("Deployment", "web"), ("Service", "web"), ("Ingress", "web")} <= kinds
    jobs = {j["id"]: j for j in info.ci_jobs}
    assert jobs["test-job"]["needs"] == ["build-job"] and jobs["deploy-job"]["needs"] == ["test-job"]
    spec = heuristic_spec([info], "deployment")
    assert_valid(spec)
    assert any(e.label == "routes" for e in spec.edges)


def test_scan_errors_and_path_forms(tmp_path: Path, fastapi_repo: Path, write):
    with pytest.raises(FileNotFoundError, match="not found"):
        scan(tmp_path / "nope")
    f = write(tmp_path, "file.txt", "x")
    with pytest.raises(NotADirectoryError, match="Not a folder"):
        discover(f)
    # pasted Windows-style quoting and env vars / ~ are accepted
    assert scan(f'"{fastapi_repo}"').name == "orders-api"
    os.environ["VISIO_TEST_REPO"] = str(fastapi_repo)
    assert scan("$VISIO_TEST_REPO").name == "orders-api"
    assert scan(f"'{fastapi_repo}{os.sep}'").name == "orders-api"


def test_scan_performance_20k_files(tmp_path: Path, write):
    root = tmp_path / "big"
    (root / ".git").mkdir(parents=True)
    write(root, "package.json", json.dumps({"dependencies": {"express": "4"}}))
    for d in range(100):
        base = root / "src" / f"pkg{d}"
        base.mkdir(parents=True)
        for i in range(200):
            (base / f"m{i}.ts").write_text("export const a = 1\n")
    (root / "node_modules" / "x").mkdir(parents=True)
    for i in range(500):
        (root / "node_modules" / "x" / f"{i}.js").write_text("x")
    t0 = time.perf_counter()
    info = scan(root)
    elapsed = time.perf_counter() - t0
    assert info.file_count >= 20000 and "Express" in info.frameworks
    assert elapsed < 2.0, elapsed
