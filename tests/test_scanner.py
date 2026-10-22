"""Repository scanner: discovery, profiling, digests, sandboxed file access and the no-AI fallback spec."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from visio_mcp import catalog
from visio_mcp.scanner import (
    RepoFS,
    RepoInfo,
    digest,
    discover,
    heuristic_spec,
    redact,
    scan,
    tree,
    workspace_digest,
)
from visio_mcp.spec import DiagramSpec

# --------------------------------------------------------------------------- fixtures


def write(root: Path, rel: str, text: str = "") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


COMPOSE = """\
version: "3.9"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://app:s3cretpw@db:5432/app
      REDIS_URL: redis://cache:6379/0
      SECRET_KEY: supersecretvalue
    depends_on:
      - db
      - cache
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: example
  cache:
    image: redis:7-alpine
  worker:
    build: ./worker
    depends_on: [db, cache]
"""

WORKFLOW = """\
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          pip install -r requirements.txt
          pytest
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - run: docker build -t api .
  deploy:
    needs: [build]
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to Azure
        uses: azure/webapps-deploy@v3
"""


@pytest.fixture
def fastapi_repo(tmp_path: Path) -> Path:
    root = tmp_path / "orders-api"
    (root / ".git").mkdir(parents=True)
    write(root, "requirements.txt", "fastapi==0.110\nuvicorn\npsycopg2-binary\nredis>=5\ncelery\nstripe\nopenai\n")
    write(root, "app/main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    write(root, "app/models.py", "class Order: ...\n")
    write(root, "app/__init__.py")
    write(root, "Dockerfile", "FROM python:3.12\n")
    write(root, "docker-compose.yml", COMPOSE)
    write(root, ".github/workflows/ci.yml", WORKFLOW)
    write(root, "README.md", "# Orders\n\nThe orders service.\n")
    write(root, ".gitignore", "generated/\n*.log\n")
    write(root, "generated/big.py", "x = 1\n")
    write(root, "node_modules/junk/index.js", "x\n")
    return root


@pytest.fixture
def next_repo(tmp_path: Path) -> Path:
    root = tmp_path / "storefront"
    (root / ".git").mkdir(parents=True)
    write(root, "package.json", json.dumps({
        "name": "storefront",
        "dependencies": {"next": "14", "react": "18", "react-dom": "18", "@stripe/stripe-js": "1", "mongoose": "8"},
    }))
    write(root, "next.config.js", "module.exports = {}\n")
    write(root, "src/index.ts", "export {}\n")
    write(root, "src/app/page.tsx", "export default function P(){return null}\n")
    return root


@pytest.fixture
def tf_repo(tmp_path: Path) -> Path:
    root = tmp_path / "infra-aws"
    write(root, "main.tf", '''\
provider "aws" { region = "us-east-1" }
resource "aws_lambda_function" "orders" { function_name = "orders" }
resource "aws_dynamodb_table" "orders" { name = "orders" }
resource "aws_sqs_queue" "events" { name = "events" }
resource "aws_s3_bucket" "assets" { bucket = "assets" }
resource "aws_api_gateway_rest_api" "gw" { name = "gw" }
resource "aws_db_instance" "main" {
  engine = "postgres"
}
''')
    write(root, "variables.tf", 'variable "x" {}\n')
    return root


@pytest.fixture
def bicep_repo(tmp_path: Path) -> Path:
    root = tmp_path / "infra-azure"
    write(root, "main.bicep", """\
param location string = resourceGroup().location
resource plan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: 'plan'
}
resource func 'Microsoft.Web/sites@2022-03-01' = {
  name: 'func'
  kind: 'functionapp'
}
resource store 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'store'
}
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' = {
  name: 'cosmos'
}
resource bus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'bus'
}
""")
    return root


@pytest.fixture
def workspace(tmp_path: Path, fastapi_repo: Path, next_repo: Path, tf_repo: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    for src in (fastapi_repo, next_repo, tf_repo):
        src.rename(ws / src.name)
    # make the frontend point at the API
    write(ws / "storefront", ".env.example", "API_URL=http://orders-api:8000\nSTRIPE_SECRET_KEY=sk_test\n")
    return ws


def assert_valid(spec: DiagramSpec) -> None:
    DiagramSpec.model_validate(spec.model_dump())
    ids = [n.id for n in spec.nodes]
    assert len(ids) == len(set(ids))
    for e in spec.edges:
        assert e.source in ids and e.target in ids
    for n in spec.nodes:
        assert catalog.lookup(n.kind) is not None, n.kind
        assert len(n.label) <= 30


# --------------------------------------------------------------------------- scan


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


def test_scan_cloudformation_k8s_and_gitlab(tmp_path: Path):
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


def test_scan_errors_and_path_forms(tmp_path: Path, fastapi_repo: Path):
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


def test_scan_performance_20k_files(tmp_path: Path):
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


# --------------------------------------------------------------------------- discover


def test_discover_single_repo(fastapi_repo: Path):
    repos = discover(fastapi_repo)
    assert [r.name for r in repos] == ["orders-api"]


def test_discover_repo_without_git_but_manifest(tmp_path: Path):
    root = tmp_path / "plain"
    write(root, "pyproject.toml", '[project]\nname="x"\ndependencies=["flask"]\n')
    repos = discover(root)
    assert len(repos) == 1 and "Flask" in repos[0].frameworks


def test_discover_folder_of_repos(workspace: Path):
    repos = discover(workspace)
    assert [r.name for r in repos] == ["infra-aws", "orders-api", "storefront"]
    assert discover(workspace, max_depth=1)[0].name == "infra-aws"


def test_discover_depth_limit_and_ignored_dirs(tmp_path: Path):
    ws = tmp_path / "ws"
    write(ws, "a/b/c/d/package.json", "{}")  # depth 4
    write(ws, "node_modules/pkg/package.json", "{}")
    write(ws, "x/package.json", "{}")
    names = [r.path.relative_to(ws).as_posix() for r in discover(ws, max_depth=3)]
    assert names == ["x"]
    assert "a/b/c/d" in [r.path.relative_to(ws).as_posix() for r in discover(ws, max_depth=5)]


# --------------------------------------------------------------------------- tree


def test_tree_skips_noise_and_orders_dirs_first(fastapi_repo: Path):
    out = tree(fastapi_repo)
    lines = out.splitlines()
    assert lines[0] == "orders-api/"
    assert "node_modules" not in out and ".git/" not in out and "generated" not in out
    assert "  app/" in lines and "    main.py" in lines
    assert lines.index("  app/") < lines.index("  Dockerfile")  # dirs before files
    assert ".github/" in out


def test_tree_collapses_huge_dirs_and_truncates(tmp_path: Path):
    root = tmp_path / "t"
    for i in range(150):
        write(root, f"data/f{i:03}.txt")
    for i in range(30):
        write(root, f"d{i:02}/sub/file.py")
    out = tree(root, max_entries=40)
    assert "… 142 more files" in tree(root, max_entries=400) or "more files" in tree(root, max_entries=400)
    assert len(out.splitlines()) <= 42
    deep = tmp_path / "deep"
    write(deep, "a/b/c/d/e/f.txt")
    out = tree(deep, max_depth=2)
    assert "f.txt" not in out and "b/ …" in out


# --------------------------------------------------------------------------- digest


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


# --------------------------------------------------------------------------- RepoFS


def test_repofs_single_root_read_list_find(fastapi_repo: Path):
    fs = RepoFS([fastapi_repo])
    listing = fs.list_dir(".")
    assert "app/" in listing and "node_modules" not in listing
    assert "main.py" in fs.list_dir("app")
    text = fs.read_file("app/main.py")
    assert "1: from fastapi import FastAPI" in text
    part = fs.read_file("docker-compose.yml", start_line=3, max_lines=2)
    assert "more lines" in part and "lines 3-4" in part
    found = fs.find_files("**/*.py")
    assert "app/main.py" in found and "generated" not in found and "node_modules" not in found
    assert "Dockerfile" in fs.find_files("Dockerfile")


def test_repofs_rejects_traversal_and_symlink_escape(tmp_path: Path, fastapi_repo: Path):
    secret = write(tmp_path, "outside.txt", "top secret")
    fs = RepoFS([fastapi_repo])
    for bad in ("../outside.txt", "app/../../outside.txt", "/etc/passwd", str(secret), "C:\\Windows\\win.ini", "~/x"):
        with pytest.raises(ValueError):
            fs.read_file(bad)
    with pytest.raises(ValueError):
        fs.list_dir("..")
    (fastapi_repo / "link.txt").symlink_to(secret)
    (fastapi_repo / "linkdir").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        fs.read_file("link.txt")
    with pytest.raises(ValueError, match="escapes"):
        fs.list_dir("linkdir")
    assert "link.txt" not in fs.find_files("*.txt")  # symlinks are not followed in walks
    assert "top secret" not in fs.search("secret")


def test_repofs_multi_root_paths(workspace: Path):
    fs = RepoFS([workspace / "orders-api", workspace / "storefront"])
    assert fs.list_dir(".").splitlines() == ["orders-api/", "storefront/"]
    assert "from fastapi" in fs.read_file("orders-api/app/main.py")
    assert "next" in fs.read_file("storefront/package.json")
    with pytest.raises(ValueError, match="Unknown repository"):
        fs.read_file("nope/x")
    with pytest.raises(ValueError):
        fs.read_file("orders-api/../storefront/package.json")
    hits = fs.search("FastAPI", glob="*.py")
    assert hits.startswith("orders-api/app/main.py:1:")


def test_repofs_refuses_binary_huge_and_keys(tmp_path: Path):
    root = tmp_path / "r"
    write(root, "ok.txt", "hello")
    (root / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    (root / "image.png").write_bytes(b"\x89PNG")
    (root / "huge.log").write_text("x" * 1_200_000)
    write(root, "server.pem", "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----")
    fs = RepoFS([root])
    for name in ("blob.bin", "image.png", "huge.log", "server.pem"):
        with pytest.raises(ValueError):
            fs.read_file(name)
    with pytest.raises(FileNotFoundError):
        fs.read_file("missing.txt")
    with pytest.raises(ValueError, match="directory"):
        fs.read_file(".")


def test_redaction():
    src = '''\
DB_PASSWORD = "hunter2hunter2"
api_key: abcdef123456
conn = "Server=tcp:x.database.windows.net;Database=d;User Id=u;Password=Sup3rS3cret!;"
url = "postgresql://app:s3cretpw@db:5432/app"
token = os.environ["TOKEN"]
password: ${DB_PASSWORD}
aws = "AKIAABCDEFGHIJKLMNOP"
key = "sk-abcdefghijklmnopqrstuvwxyz123456"
max_tokens: 4096
name: public-value
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA
-----END RSA PRIVATE KEY-----
'''
    out = redact(src)
    for leaked in ("hunter2hunter2", "abcdef123456", "Sup3rS3cret", "s3cretpw", "AKIAABCDEFGHIJKLMNOP",
                   "abcdefghijklmnopqrstuvwxyz123456", "MIIEowIBAAKCAQEA"):
        assert leaked not in out, leaked
    assert 'os.environ["TOKEN"]' in out and "${DB_PASSWORD}" in out
    assert "max_tokens: 4096" in out and "name: public-value" in out
    assert "postgresql://app:" in out and "@db:5432/app" in out


def test_repofs_redacts_on_read_and_search(tmp_path: Path):
    root = tmp_path / "r"
    write(root, "settings.py", 'SECRET_KEY = "djangoinsecurekey12345"\nDEBUG = True\n')
    write(root, ".env", "API_URL=http://svc\nSTRIPE_KEY=sk_live_abcdefghijklmnop1234\n")
    write(root, ".env.example", "API_URL=http://svc\n")
    fs = RepoFS([root])
    assert "djangoinsecurekey12345" not in fs.read_file("settings.py")
    assert "DEBUG = True" in fs.read_file("settings.py")
    env = fs.read_file(".env")
    assert "STRIPE_KEY=***REDACTED***" in env and "sk_live" not in env and "http://svc" not in env
    assert "http://svc" in fs.read_file(".env.example")
    hits = fs.search("KEY")
    assert "djangoinsecurekey12345" not in hits and "sk_live" not in hits
    assert "settings.py:1:" in hits


def test_repofs_search_options(fastapi_repo: Path):
    fs = RepoFS([fastapi_repo])
    out = fs.search(r"class\s+Order", glob="*.py")
    assert out == "app/models.py:1: class Order: ..."
    assert fs.search("fastapi").count("\n") >= 1  # lowercase pattern is case-insensitive
    assert fs.search("zzz-not-there").startswith("No matches")
    many = fs.search(".", max_hits=3)
    assert len([l for l in many.splitlines() if ":" in l]) >= 3 and "stopped at" in many
    with pytest.raises(ValueError, match="Invalid regex"):
        fs.search("(")
    assert "node_modules" not in fs.search("x")


# --------------------------------------------------------------------------- heuristic_spec


@pytest.mark.parametrize("dtype", ["architecture", "cloud", "deployment", "pipeline", "erd", "c4-container", "mindmap"])
def test_heuristic_spec_valid_for_every_type(workspace: Path, bicep_repo: Path, dtype: str):
    repos = discover(workspace) + [scan(bicep_repo)]
    for subset in (repos, repos[:1], []):
        spec = heuristic_spec(subset, dtype)
        assert_valid(spec)
        assert spec.subtitle == "Generated from repository scan"


def test_architecture_spec_single_repo(fastapi_repo: Path):
    spec = heuristic_spec([scan(fastapi_repo)])
    assert spec.type == "architecture" and spec.title == "orders-api architecture"
    assert_valid(spec)
    nodes = {n.id: n for n in spec.nodes}
    labels = {n.label: n for n in spec.nodes}
    assert {"orders-api", "PostgreSQL", "Redis", "Stripe", "OpenAI", "Users"} <= set(labels)
    assert labels["PostgreSQL"].kind == "database" and labels["Redis"].kind in ("cache", "database")
    assert labels["Stripe"].kind == "external"
    groups = {g.id: g for g in spec.groups}
    assert {g.label for g in groups.values()} >= {"Clients", "Data", "External", "orders-api"}
    assert groups[labels["Stripe"].group].kind == "external"
    assert groups[labels["PostgreSQL"].group].label == "Data"
    pairs = {(nodes[e.source].label, nodes[e.target].label) for e in spec.edges}
    assert ("Users", "orders-api") in pairs
    assert ("orders-api", "PostgreSQL") in pairs and ("orders-api", "Redis") in pairs
    # compose: separate worker service depends on the stores
    assert ("worker", "PostgreSQL") in pairs and ("worker", "Redis") in pairs
    assert any(n.label == "Celery worker" for n in spec.nodes) is True


def test_architecture_spec_cloud_kinds(tf_repo: Path, bicep_repo: Path):
    spec = heuristic_spec([scan(tf_repo)], "cloud")
    assert_valid(spec)
    kinds = [n.kind for n in spec.nodes]
    # provider kinds only when the catalog knows them; otherwise base kinds
    expect_lambda = "aws-lambda" if catalog.lookup("aws-lambda") else "function"
    assert expect_lambda in kinds
    assert any(g.kind == "cloud" and g.label == "AWS" for g in spec.groups)
    assert spec.type == "cloud"
    pairs = {(e.source, e.target) for e in spec.edges}
    events = next(n.id for n in spec.nodes if n.label == "events")
    lam = next(n.id for n in spec.nodes if n.kind in ("aws-lambda", "function"))
    assert (lam, events) in pairs

    spec = heuristic_spec([scan(bicep_repo)], "architecture")
    assert_valid(spec)
    assert any(g.kind == "cloud" and g.label == "Azure" for g in spec.groups)
    assert len({n.id for n in spec.nodes}) == len(spec.nodes)
    expect_fn = "azure-functions" if catalog.lookup("azure-functions") else "function"
    assert expect_fn in {n.kind for n in spec.nodes}


def test_architecture_spec_multi_repo_links(workspace: Path):
    spec = heuristic_spec(discover(workspace))
    assert_valid(spec)
    labels = {n.label: n.id for n in spec.nodes}
    assert {"orders-api", "storefront"} <= set(labels)
    assert any(e.source == labels["storefront"] and e.target == labels["orders-api"] and e.style == "dashed"
               for e in spec.edges)
    assert len([g for g in spec.groups if g.kind == "system"]) >= 2
    assert spec.title == "ws architecture"


def test_pipeline_spec(fastapi_repo: Path):
    spec = heuristic_spec([scan(fastapi_repo)], "pipeline")
    assert spec.type == "pipeline" and spec.title == "orders-api pipeline"
    assert_valid(spec)
    by_label = {n.label: n for n in spec.nodes}
    ids = {n.label: n.id for n in spec.nodes}
    pairs = {(e.source, e.target) for e in spec.edges}
    assert (ids["test"], ids["build"]) in pairs and (ids["build"], ids["deploy"]) in pairs
    assert by_label["deploy"].emphasis
    assert any(e.label == "deploys" for e in spec.edges)


def test_pipeline_spec_without_ci_is_suggested(next_repo: Path):
    spec = heuristic_spec([scan(next_repo)], "pipeline")
    assert_valid(spec)
    assert {"Commit", "Build", "Deploy"} <= {n.label for n in spec.nodes}


def test_deployment_spec_compose(fastapi_repo: Path):
    spec = heuristic_spec([scan(fastapi_repo)], "deployment")
    assert spec.type == "deployment"
    assert_valid(spec)
    assert any(g.kind == "environment" and g.label == "Docker Compose" for g in spec.groups)
    ids = {n.label: n.id for n in spec.nodes}
    pairs = {(e.source, e.target) for e in spec.edges}
    assert (ids["api"], ids["db"]) in pairs and (ids["api"], ids["cache"]) in pairs
    assert ("internet" in {n.id for n in spec.nodes}) and (ids["Internet"], ids["api"]) in pairs


def test_unknown_kinds_fall_back(monkeypatch: pytest.MonkeyPatch, tf_repo: Path):
    real = catalog.lookup
    monkeypatch.setattr(catalog, "lookup", lambda k: None if k.startswith(("aws-", "dynamodb", "topic")) else real(k))
    spec = heuristic_spec([scan(tf_repo)], "cloud")
    assert not any(n.kind.startswith("aws-") for n in spec.nodes)
    assert any(n.kind == "function" for n in spec.nodes)
