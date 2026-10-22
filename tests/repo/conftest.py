"""Shared repo fixtures: small on-disk repositories (FastAPI+compose, Next.js, Terraform, Bicep) and helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from visio_mcp import catalog
from visio_mcp.spec import DiagramSpec


def _write(root: Path, rel: str, text: str = "") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _assert_valid(spec: DiagramSpec) -> None:
    DiagramSpec.model_validate(spec.model_dump())
    ids = [n.id for n in spec.nodes]
    assert len(ids) == len(set(ids))
    for e in spec.edges:
        assert e.source in ids and e.target in ids
    for n in spec.nodes:
        assert catalog.lookup(n.kind) is not None, n.kind
        assert len(n.label) <= 30


@pytest.fixture
def write() -> Callable[..., Path]:
    return _write


@pytest.fixture
def assert_valid() -> Callable[[DiagramSpec], None]:
    return _assert_valid



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
    _write(root, "requirements.txt", "fastapi==0.110\nuvicorn\npsycopg2-binary\nredis>=5\ncelery\nstripe\nopenai\n")
    _write(root, "app/main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    _write(root, "app/models.py", "class Order: ...\n")
    _write(root, "app/__init__.py")
    _write(root, "Dockerfile", "FROM python:3.12\n")
    _write(root, "docker-compose.yml", COMPOSE)
    _write(root, ".github/workflows/ci.yml", WORKFLOW)
    _write(root, "README.md", "# Orders\n\nThe orders service.\n")
    _write(root, ".gitignore", "generated/\n*.log\n")
    _write(root, "generated/big.py", "x = 1\n")
    _write(root, "node_modules/junk/index.js", "x\n")
    return root


@pytest.fixture
def next_repo(tmp_path: Path) -> Path:
    root = tmp_path / "storefront"
    (root / ".git").mkdir(parents=True)
    _write(root, "package.json", json.dumps({
        "name": "storefront",
        "dependencies": {"next": "14", "react": "18", "react-dom": "18", "@stripe/stripe-js": "1", "mongoose": "8"},
    }))
    _write(root, "next.config.js", "module.exports = {}\n")
    _write(root, "src/index.ts", "export {}\n")
    _write(root, "src/app/page.tsx", "export default function P(){return null}\n")
    return root


@pytest.fixture
def tf_repo(tmp_path: Path) -> Path:
    root = tmp_path / "infra-aws"
    _write(root, "main.tf", '''\
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
    _write(root, "variables.tf", 'variable "x" {}\n')
    return root


@pytest.fixture
def bicep_repo(tmp_path: Path) -> Path:
    root = tmp_path / "infra-azure"
    _write(root, "main.bicep", """\
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
    _write(ws / "storefront", ".env.example", "API_URL=http://orders-api:8000\nSTRIPE_SECRET_KEY=sk_test\n")
    return ws
